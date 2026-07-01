"""
Documentation Search Plugin — FTS5 full-text index + document metadata store.

Provides the SQLite schema (doc_metadata, doc_search_fts virtual table)
and a /api/doc_search/status health-check endpoint.  Extraction and
indexing logic live in Phase 6 — this is the schema foundation.

Exports:
    DocSearchPlugin  — plugin class (auto-discovered by main.py)
    plugin           — module-level singleton
    SCHEMA_VERSION   — current schema version string
    DB_PATH          — filesystem path to doc_search.db
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone

from fastapi import FastAPI

from app import config
from app.plugins.base import ToolkitPlugin
from app.plugins.doc_extraction import compute_sha256, extract_text

logger = logging.getLogger("doc_search")

# ── Constants ──────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "doc_search.db")
SCHEMA_VERSION = "1"

# ── Module-level state ─────────────────────────────────────
_db_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════
#  SQLite helpers
# ═══════════════════════════════════════════════════════════

def _get_db() -> sqlite3.Connection:
    """Open (or create) the doc_search SQLite database with WAL mode."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _db_get(key: str) -> str | None:
    """Read a single value from the sync_state key-value store."""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT value FROM sync_state WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()


def _db_set(key: str, value: str) -> None:
    """Write (insert or replace) a value into the sync_state store."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()


# ═══════════════════════════════════════════════════════════
#  Sync engine — config, git, state helpers
# ═══════════════════════════════════════════════════════════

def _load_doc_repos() -> list[dict]:
    """Read doc_repos from toolkit_settings.json via config.load().

    Each entry must have both ``name`` and ``path`` keys (both non-empty).
    Entries missing either key are silently skipped.

    Returns:
        List of ``{name, path}`` dicts, or empty list if key is missing/empty.
    """
    cfg = config.load()
    repos = cfg.get("doc_repos", [])
    if not isinstance(repos, list):
        logger.warning("doc_repos in config is not a list; ignoring")
        return []

    valid: list[dict] = []
    for entry in repos:
        name = entry.get("name", "")
        path = entry.get("path", "")
        if isinstance(name, str) and name.strip() and isinstance(path, str) and path.strip():
            valid.append({"name": name.strip(), "path": path.strip()})
        else:
            logger.debug("Skipping invalid doc_repo entry: %s", entry)

    logger.info("Loaded %d doc repos from config", len(valid))
    return valid


async def _git_pull(repo_path: str) -> dict:
    """Run ``git pull`` in *repo_path* via subprocess (argument list, no shell).

    Executed via :func:`asyncio.to_thread` to avoid blocking the event loop.
    Timeout is 120 seconds.  Never raises — failures are returned as
    ``{ok: False, stderr: ...}``.

    Returns:
        ``{ok: bool, stdout: str, stderr: str}``
    """
    cmd = ["git", "-C", repo_path, "pull"]
    logger.info("git pull: %s", repo_path)

    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    try:
        proc = await asyncio.to_thread(_run)
        ok = proc.returncode == 0
        if not ok:
            logger.warning(
                "git pull failed for %s (rc=%d): %s",
                repo_path, proc.returncode, proc.stderr.strip(),
            )
        return {"ok": ok, "stdout": proc.stdout, "stderr": proc.stderr}
    except subprocess.TimeoutExpired:
        logger.warning("git pull timed out after 120s: %s", repo_path)
        return {"ok": False, "stdout": "", "stderr": "Git pull timed out after 120s"}
    except FileNotFoundError:
        logger.warning("git executable not found on PATH; cannot pull %s", repo_path)
        return {"ok": False, "stdout": "", "stderr": "git executable not found"}
    except Exception as exc:
        logger.warning("git pull error for %s: %s", repo_path, exc)
        return {"ok": False, "stdout": "", "stderr": str(exc)}


def _db_upsert_state(key: str, val) -> None:
    """Store *val* as JSON under *key* in the sync_state table."""
    encoded = json.dumps(val)
    _db_set(key, encoded)


def _db_get_state(key: str):
    """Read *key* from sync_state and return the parsed JSON value.

    Returns ``None`` if the key is missing or the stored value is not valid JSON.
    """
    raw = _db_get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("sync_state key '%s' contains invalid JSON; returning None", key)
        return None


# ── Sync lock (module-level) ─────────────────────────────────

_sync_lock = asyncio.Lock()


# ═══════════════════════════════════════════════════════════
#  Sync pipeline — hash comparison, upsert, cleanup, orchestration
# ═══════════════════════════════════════════════════════════

def _should_reindex(conn: sqlite3.Connection, repo: str, rel_path: str, sha256: str) -> bool:
    """Check whether a file needs re-extraction based on stored hash.

    Returns ``True`` if no matching row exists or the stored ``sha256``
    differs from *sha256*.  Returns ``False`` when hashes match.
    """
    row = conn.execute(
        "SELECT sha256 FROM doc_metadata WHERE repo = ? AND relative_path = ?",
        (repo, rel_path),
    ).fetchone()
    if row is None:
        return True
    return row["sha256"] != sha256


def _upsert_document(conn: sqlite3.Connection, repo: str, rel_path: str, result: dict) -> int:
    """Insert or update a document in doc_metadata and rebuild its FTS5 entry.

    Uses content-less FTS5 pattern: DELETE old inverted entry, INSERT new one.
    The *result* dict is the output of :func:`extract_text` with keys
    ``text``, ``encoding``, ``needs_ocr``, ``sha256``, ``error``.

    Returns the ``rowid`` of the inserted/updated row.
    """
    text = result.get("text", "") or ""
    sha = result.get("sha256", "") or ""
    encoding = result.get("encoding", "utf_8") or "utf_8"
    needs_ocr = 1 if result.get("needs_ocr") else 0

    conn.execute(
        """INSERT INTO doc_metadata (repo, relative_path, full_text, sha256,
           encoding, needs_ocr, last_extracted)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(repo, relative_path) DO UPDATE SET
             full_text=excluded.full_text,
             sha256=excluded.sha256,
             encoding=excluded.encoding,
             needs_ocr=excluded.needs_ocr,
             last_extracted=excluded.last_extracted""",
        (repo, rel_path, text, sha, encoding, needs_ocr),
    )

    # Retrieve the rowid for the (repo, relative_path) pair
    fetched = conn.execute(
        "SELECT id FROM doc_metadata WHERE repo = ? AND relative_path = ?",
        (repo, rel_path),
    ).fetchone()
    if fetched is None:
        raise RuntimeError(f"Failed to retrieve rowid after upsert for {repo}/{rel_path}")
    rowid = fetched["id"]

    # Content-less FTS5 update: delete old entry, insert new
    conn.execute("DELETE FROM doc_search_fts WHERE rowid = ?", (rowid,))
    conn.execute(
        "INSERT INTO doc_search_fts(rowid, full_text) VALUES (?, ?)",
        (rowid, text),
    )

    return rowid


def _clean_deleted(conn: sqlite3.Connection, repo: str, existing_paths: set[str]) -> int:
    """Remove rows from doc_metadata for files no longer on disk.

    Content-less FTS5 virtual table auto-removes linked rows when the
    content table row is deleted (via ``content_rowid``).

    Returns the number of deleted rows.
    """
    # Collect all relative_path values for the repo
    all_rows = conn.execute(
        "SELECT id, relative_path FROM doc_metadata WHERE repo = ?",
        (repo,),
    ).fetchall()

    to_delete: list[int] = []
    for row in all_rows:
        if row["relative_path"] not in existing_paths:
            to_delete.append(row["id"])

    if not to_delete:
        return 0

    # Delete from doc_metadata; FTS5 content-less auto-removes linked rows
    placeholders = ",".join("?" for _ in to_delete)
    conn.execute(
        f"DELETE FROM doc_metadata WHERE id IN ({placeholders})",
        to_delete,
    )

    deleted = len(to_delete)
    logger.info("Cleaned %d deleted files from repo '%s'", deleted, repo)
    return deleted


async def _sync_repo(repo_name: str, repo_path: str) -> dict:
    """Core per-repo sync coroutine.

    1. ``os.walk(repo_path)`` collecting all file paths (skips ``.git``).
    2. Compute SHA-256 hash for each file.
    3. ``_should_reindex`` check → collect files needing change.
    4. ``ThreadPoolExecutor(max_workers=4)`` parallel extraction via
       ``asyncio.to_thread()``.
    5. ``_upsert_document`` for each extraction result.
    6. ``_clean_deleted`` to remove stale entries.

    Returns a summary dict:
        ``{repo, pulled, total, changed, deleted, errors}``

    All blocking work (DB, file I/O) runs inside ``asyncio.to_thread()``.
    """
    errors: list[str] = []

    def _walk_and_filter() -> tuple[list[tuple[str, str, str]], list[str], list[str]]:
        """Blocking: walk disk, compute hashes, determine what needs change."""
        needs_change: list[tuple[str, str, str]] = []  # (rel_path, full_path, sha256)
        all_rel_paths: list[str] = []
        errors_inner: list[str] = []

        conn = _get_db()
        try:
            for root, dirs, files in os.walk(repo_path):
                # Skip .git directory
                if ".git" in dirs:
                    dirs.remove(".git")

                for fname in files:
                    full_path = os.path.join(root, fname)
                    try:
                        rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/")
                    except ValueError:
                        errors_inner.append(f"path resolution failed: {full_path}")
                        continue

                    all_rel_paths.append(rel_path)

                    sha = compute_sha256(full_path)
                    if not sha:
                        errors_inner.append(f"SHA-256 failed: {rel_path}")
                        continue

                    with _db_lock:
                        if _should_reindex(conn, repo_name, rel_path, sha):
                            needs_change.append((rel_path, full_path, sha))
        finally:
            conn.close()

        return needs_change, all_rel_paths, errors_inner

    # 1. Walk + hash (blocking)
    needs_change, all_rel_paths, walk_errors = await asyncio.to_thread(_walk_and_filter)
    errors.extend(walk_errors)

    total_files = len(all_rel_paths)
    changed_count = 0

    # 2. Parallel extraction for changed files
    if needs_change:
        logger.info(
            "Repo '%s': %d/%d files need extraction", repo_name, len(needs_change), total_files
        )

        def _extract_one(full_path: str) -> dict:
            """Single-file extraction (no-op if extract_text raises — it never does)."""
            return extract_text(full_path)

        def _upsert_batch(rel_path: str, extr_result: dict) -> None:
            """Blocking: upsert a single document into the DB."""
            with _db_lock:
                conn = _get_db()
                try:
                    _upsert_document(conn, repo_name, rel_path, extr_result)
                    conn.commit()
                finally:
                    conn.close()

        # Run extractions in thread pool (max_workers=4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            # Submit all extraction tasks
            futures = {
                pool.submit(_extract_one, full_path): (rel_path, full_path)
                for rel_path, full_path, _sha in needs_change
            }

            done_total = 0
            for future in concurrent.futures.as_completed(futures):
                rel_path, full_path = futures[future]
                try:
                    extr_result = await asyncio.to_thread(future.result)
                    err = extr_result.get("error")
                    if err:
                        errors.append(f"{rel_path}: {err}")
                    else:
                        # Upsert into DB (blocking — run in thread)
                        await asyncio.to_thread(_upsert_batch, rel_path, extr_result)
                        changed_count += 1
                except Exception as exc:
                    errors.append(f"{rel_path}: extraction crashed: {exc}")
                    logger.warning("Extraction failed for %s: %s", full_path, exc)

                done_total += 1
                # Update progress in sync_state periodically
                if done_total % 5 == 0 or done_total == len(needs_change):
                    _db_upsert_state("sync_progress", {
                        "phase": "indexing",
                        "repo": repo_name,
                        "done": done_total,
                        "total": len(needs_change),
                    })

    # 3. Cleanup deleted files
    def _do_cleanup() -> int:
        with _db_lock:
            conn = _get_db()
            try:
                existing_set = set(all_rel_paths)
                deleted = _clean_deleted(conn, repo_name, existing_set)
                conn.commit()
                return deleted
            finally:
                conn.close()

    deleted_count = await asyncio.to_thread(_do_cleanup)

    logger.info(
        "Repo '%s' sync complete: %d total, %d changed, %d deleted, %d errors",
        repo_name, total_files, changed_count, deleted_count, len(errors),
    )

    return {
        "repo": repo_name,
        "pulled": True,
        "total": total_files,
        "changed": changed_count,
        "deleted": deleted_count,
        "errors": errors,
    }


async def _sync_job() -> None:
    """Top-level sync orchestrator.

    Pipeline per repo: git pull → walk → hash → extract → upsert → cleanup.

    Guarded by :data:`_sync_lock` — only one sync may run at a time.
    When the lock is already held, the call is silently skipped with a warning.
    """
    if _sync_lock.locked():
        logger.warning("Sync already in progress; skipping duplicate trigger")
        return

    async with _sync_lock:
        try:
            repos = _load_doc_repos()
            if not repos:
                logger.info("No doc repos configured; sync complete")
                return

            _db_upsert_state("sync_progress", {"phase": "starting"})
            logger.info("Sync job started — %d repo(s) configured", len(repos))

            for repo in repos:
                name = repo["name"]
                path = repo["path"]

                # Phase: pulling
                _db_upsert_state("sync_progress", {"phase": "pulling", "repo": name})
                pull_result = await _git_pull(path)
                logger.info(
                    "git pull %s: ok=%s (%s)",
                    name, pull_result["ok"], pull_result["stdout"].strip() or "no output",
                )
                # Continue even on pull failure — files may still be on disk

                # Phase: indexing
                _db_upsert_state("sync_progress", {"phase": "indexing", "repo": name, "done": 0, "total": 0})
                sync_result = await _sync_repo(name, path)
                logger.info(
                    "sync %s: total=%d changed=%d deleted=%d errors=%d",
                    name,
                    sync_result["total"],
                    sync_result["changed"],
                    sync_result["deleted"],
                    len(sync_result.get("errors", [])),
                )

            # Mark complete
            _db_upsert_state("sync_progress", {"phase": "complete"})
            _db_upsert_state("last_sync", datetime.now(timezone.utc).isoformat())
            logger.info("Sync job complete")

        except Exception as exc:
            logger.error("Sync job failed: %s", exc)
            _db_upsert_state("sync_progress", {"phase": "error", "error": str(exc)})
        finally:
            # Lock released by 'async with' exiting
            pass


# ═══════════════════════════════════════════════════════════
#  Plugin class
# ═══════════════════════════════════════════════════════════

class DocSearchPlugin(ToolkitPlugin):
    id = "doc_search"
    name = "Documentation Search"
    icon = "\U0001f50d"   # 🔍 magnifying glass
    order = 46            # after CompetencePlugin (45), before others

    # ── Route registration ──────────────────────────────────

    def register_routes(self, app: FastAPI) -> None:

        @app.get("/api/doc_search/status")
        async def doc_search_status():
            """Return plugin health and schema version."""
            try:
                ver = _db_get("schema_version")
                return {
                    "status": "ok",
                    "schema_version": ver or "unknown",
                }
            except Exception as e:
                logger.warning("Status check failed: %s", e)
                return {
                    "status": "error",
                    "schema_version": "unknown",
                }

    # ── Lifecycle hooks ─────────────────────────────────────

    def startup(self) -> None:
        """Initialize SQLite schema on first run; skip migration if current."""
        try:
            with _db_lock:
                conn = _get_db()
                try:
                    # 1. Ensure sync_state table exists
                    conn.execute(
                        "CREATE TABLE IF NOT EXISTS sync_state "
                        "(key TEXT PRIMARY KEY, value TEXT)"
                    )
                    conn.commit()

                    # 2. Check current schema version
                    current_ver = conn.execute(
                        "SELECT value FROM sync_state WHERE key = 'schema_version'"
                    ).fetchone()
                    if current_ver and current_ver["value"] == SCHEMA_VERSION:
                        conn.close()
                        logger.info(
                            "DocSearch schema v%s already initialized", SCHEMA_VERSION
                        )
                        return

                    # 3. Execute full schema DDL
                    conn.executescript("""
                        CREATE TABLE IF NOT EXISTS doc_metadata (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            repo TEXT NOT NULL,
                            relative_path TEXT NOT NULL,
                            full_text TEXT NOT NULL DEFAULT '',
                            sha256 TEXT NOT NULL DEFAULT '',
                            encoding TEXT NOT NULL DEFAULT 'utf_8',
                            needs_ocr INTEGER NOT NULL DEFAULT 0,
                            last_extracted TEXT NOT NULL DEFAULT '',
                            UNIQUE(repo, relative_path)
                        );

                        CREATE VIRTUAL TABLE IF NOT EXISTS doc_search_fts USING fts5(
                            full_text,
                            tokenize='unicode61'
                        );

                        CREATE INDEX IF NOT EXISTS idx_doc_metadata_sha256
                            ON doc_metadata(sha256);
                        CREATE INDEX IF NOT EXISTS idx_doc_metadata_repo
                            ON doc_metadata(repo);

                        INSERT OR REPLACE INTO sync_state (key, value)
                            VALUES ('schema_version', '1');
                    """)
                    conn.commit()

                finally:
                    conn.close()

            logger.info(
                "DocSearch SQLite v%s initialized at %s", SCHEMA_VERSION, DB_PATH
            )

        except Exception as e:
            logger.warning("DocSearch plugin DB init failed: %s", e)

    def shutdown(self) -> None:
        """Cleanup hook — no async clients to close in Phase 5."""
        logger.debug("DocSearch plugin shutdown complete")


# ── Auto-discovery singleton ────────────────────────────────────
plugin = DocSearchPlugin()
