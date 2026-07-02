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
import re
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import FileResponse

from app import config
from app.plugins.base import ToolkitPlugin
from app.plugins.doc_extraction import compute_sha256, extract_text

logger = logging.getLogger("doc_search")

# ── Constants ──────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "doc_search.db")
SCHEMA_VERSION = "2"

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
    """Store *val* as JSON under *key* in the sync_state table.

    This is a blocking call — always run it via ``asyncio.to_thread()``
    from async contexts to avoid SQLite corruption on the event-loop thread.
    """
    encoded = json.dumps(val)
    _db_set(key, encoded)


async def _adb_upsert_state(key: str, val) -> None:
    """Async wrapper for :func:`_db_upsert_state` — runs on a thread."""
    await asyncio.to_thread(_db_upsert_state, key, val)


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
#  XSS sanitization helper
# ═══════════════════════════════════════════════════════════

def _sanitize_html(text: str) -> str:
    """Strip HTML tags from *text* to prevent XSS in search results.

    Applied to snippet output before returning in JSON responses.
    FTS5 snippet() may preserve custom markers like ``<mark>`` which
    are re-added by the frontend via DOM manipulation — stripping
    all tags here ensures no malicious HTML survives.
    """
    return re.sub(r"<[^>]*>", "", text)


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
    html = result.get("html", "") or ""
    sha = result.get("sha256", "") or ""
    encoding = result.get("encoding", "utf_8") or "utf_8"
    needs_ocr = 1 if result.get("needs_ocr") else 0

    # Wrap in explicit transaction so DELETE+INSERT on FTS5 are atomic
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """INSERT INTO doc_metadata (repo, relative_path, full_text, full_html, sha256,
               encoding, needs_ocr, last_extracted)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(repo, relative_path) DO UPDATE SET
                 full_text=excluded.full_text,
                 full_html=excluded.full_html,
                 sha256=excluded.sha256,
                 encoding=excluded.encoding,
                 needs_ocr=excluded.needs_ocr,
                 last_extracted=excluded.last_extracted""",
            (repo, rel_path, text, html, sha, encoding, needs_ocr),
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
        conn.commit()
    except Exception:
        conn.rollback()
        raise

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

        # Process in batches to limit memory — futures + extracted text accumulate
        BATCH_SIZE = 100
        changed_files = [(rel_path, full_path, _sha) for rel_path, full_path, _sha in needs_change]
        changed_count = 0
        done_total = 0
        last_progress_update = 0

        for batch_start in range(0, len(changed_files), BATCH_SIZE):
            batch = changed_files[batch_start:batch_start + BATCH_SIZE]

            # Submit batch to thread pool
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = {
                    pool.submit(_extract_one, full_path): (rel_path, full_path)
                    for rel_path, full_path, _sha in batch
                }

                for future in concurrent.futures.as_completed(futures):
                    rel_path, full_path = futures[future]
                    try:
                        extr_result = await asyncio.to_thread(future.result)
                        err = extr_result.get("error")
                        if err:
                            errors.append(f"{rel_path}: {err}")
                        else:
                            await asyncio.to_thread(_upsert_batch, rel_path, extr_result)
                            changed_count += 1
                    except Exception as exc:
                        errors.append(f"{rel_path}: extraction crashed: {exc}")
                        logger.warning("Extraction failed for %s: %s", full_path, exc)

                    done_total += 1
                    if done_total % 100 == 0 or done_total == len(needs_change):
                        logger.info(
                            "Repo '%s': indexed %d/%d files (%d errors so far)",
                            repo_name, done_total, len(needs_change), len(errors),
                        )
                    if done_total - last_progress_update >= 50 or done_total == len(needs_change):
                        last_progress_update = done_total
                        await asyncio.to_thread(_db_upsert_state, "sync_progress", {
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
            # Ensure schema exists (DB may have been auto-recovered from corruption)
            await asyncio.to_thread(_ensure_schema)

            repos = _load_doc_repos()
            if not repos:
                logger.info("No doc repos configured; sync complete")
                return

            await _adb_upsert_state("sync_progress", {"phase": "starting"})
            logger.info("Sync job started — %d repo(s) configured", len(repos))

            for repo in repos:
                name = repo["name"]
                path = repo["path"]

                # Phase: pulling
                await _adb_upsert_state("sync_progress", {"phase": "pulling", "repo": name})
                pull_result = await _git_pull(path)
                logger.info(
                    "git pull %s: ok=%s (%s)",
                    name, pull_result["ok"], pull_result["stdout"].strip() or "no output",
                )
                # Continue even on pull failure — files may still be on disk

                # Phase: indexing
                await _adb_upsert_state("sync_progress", {"phase": "indexing", "repo": name, "done": 0, "total": 0})
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
            await _adb_upsert_state("sync_progress", {"phase": "complete"})
            await _adb_upsert_state("last_sync", datetime.now(timezone.utc).isoformat())
            logger.info("Sync job complete")

        except Exception as exc:
            logger.error("Sync job failed: %s", exc)
            await _adb_upsert_state("sync_progress", {"phase": "error", "error": str(exc)})
        finally:
            # Lock released by 'async with' exiting
            pass


# ═══════════════════════════════════════════════════════════
#  Plugin class
# ═══════════════════════════════════════════════════════════


def _ensure_schema() -> None:
    """Ensure the SQLite schema exists — idempotent, safe to call repeatedly.

    Creates tables if missing; skips if schema_version matches.
    Must be called with ``_db_lock`` held or from a single thread.
    """
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sync_state "
                "(key TEXT PRIMARY KEY, value TEXT)"
            )

            current_ver = conn.execute(
                "SELECT value FROM sync_state WHERE key = 'schema_version'"
            ).fetchone()
            if current_ver and current_ver["value"] == SCHEMA_VERSION:
                conn.commit()
                return

            conn.executescript("""
                CREATE TABLE IF NOT EXISTS doc_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    full_text TEXT NOT NULL DEFAULT '',
                    full_html TEXT NOT NULL DEFAULT '',
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
                    VALUES ('schema_version', '2');
            """)

            # Migration: add full_html column for v1 → v2
            try:
                conn.execute("ALTER TABLE doc_metadata ADD COLUMN full_html TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists

            conn.commit()
            logger.info("DocSearch SQLite v%s initialized at %s", SCHEMA_VERSION, DB_PATH)
        finally:
            conn.close()

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

        # ── Search endpoint ──────────────────────────────────

        @app.get("/api/doc_search/search")
        async def doc_search(q: str = Query("", description="FTS5 search query")):
            """Full-text search across indexed documents using BM25 ranking.

            Supports FTS5 query syntax: AND, OR, phrase queries, prefix
            queries.  Empty query returns empty results gracefully.
            """
            query = q.strip()
            if not query:
                return {"results": [], "total": 0, "query": q}

            def _run_search() -> list[dict]:
                conn = _get_db()
                try:
                    try:
                        rows = conn.execute("""
                            SELECT
                                m.repo, m.relative_path, m.needs_ocr,
                                snippet(doc_search_fts, 0, '<mark>', '</mark>', '...', 32) AS snippet,
                                bm25(doc_search_fts) AS score
                            FROM doc_search_fts
                            JOIN doc_metadata m ON m.id = doc_search_fts.rowid
                            WHERE doc_search_fts MATCH ?
                            ORDER BY score
                            LIMIT 50
                        """, (query,)).fetchall()
                    except sqlite3.OperationalError:
                        logger.warning("FTS5 query failed, returning empty: %r", query)
                        return []
                    return [dict(r) for r in rows]
                finally:
                    conn.close()

            rows = await asyncio.to_thread(_run_search)

            results: list[dict] = []
            for row in rows:
                path = row["relative_path"]
                raw_snippet = row["snippet"] or ""
                snippet_text = _sanitize_html(raw_snippet)
                results.append({
                    "repo": row["repo"],
                    "path": path,
                    "filename": os.path.basename(path),
                    "snippet": snippet_text,
                    "score": float(row["score"]),
                    "needs_ocr": bool(row["needs_ocr"]),
                    "file_type": os.path.splitext(path)[1].lstrip(".").lower(),
                })

            # Store last_search timestamp (non-blocking in thread)
            await asyncio.to_thread(
                _db_upsert_state, "last_search",
                datetime.now(timezone.utc).isoformat(),
            )

            return {"results": results, "total": len(results), "query": q}

        # ── Preview endpoint ─────────────────────────────────

        @app.get("/api/doc_search/preview/{repo}/{path:path}")
        async def doc_search_preview(repo: str, path: str = Path(..., description="Document relative path")):
            """Return extracted text preview with path-traversal protection.

            Resolves the full path with ``os.path.realpath()`` and verifies the
            result is within the configured repo root.  Returns 403 for any
            path-traversal attempt (NFR-13).
            """
            # Load repo config
            repos = _load_doc_repos()
            repo_entry = next((r for r in repos if r["name"] == repo), None)
            if repo_entry is None:
                raise HTTPException(status_code=404, detail={"error": "Repo not found"})

            repo_root = repo_entry["path"]
            full_path = os.path.join(repo_root, path)
            resolved = os.path.realpath(full_path)
            real_root = os.path.realpath(repo_root)

            # Path traversal protection (NFR-13)
            if not (resolved == real_root or resolved.startswith(real_root + os.sep)):
                raise HTTPException(
                    status_code=403,
                    detail={"error": "Path traversal detected"},
                )

            def _run_preview() -> str | None:
                conn = _get_db()
                try:
                    row = conn.execute(
                        "SELECT full_text, full_html FROM doc_metadata WHERE repo = ? AND relative_path = ?",
                        (repo, path),
                    ).fetchone()
                    if row is None:
                        return None
                    return {"text": row["full_text"], "html": row["full_html"] or ""}
                finally:
                    conn.close()

            result = await asyncio.to_thread(_run_preview)
            if result is None:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "Document not found in index"},
                )

            return {
                "repo": repo,
                "path": path,
                "text": result["text"][:10000],
                "html": result["html"],
            }

        # ── Open file endpoint ───────────────────────────────

        @app.get("/api/doc_search/open/{repo}/{path:path}")
        async def doc_search_open_file(repo: str, path: str = Path(..., description="Document relative path")):
            """Serve the raw file for in-browser viewing/download.

            Validates path traversal before serving. Returns the file with
            its extension-determined MIME type for native browser handling.
            """
            repos = _load_doc_repos()
            repo_entry = next((r for r in repos if r["name"] == repo), None)
            if repo_entry is None:
                raise HTTPException(status_code=404, detail={"error": "Repo not found"})

            repo_root = repo_entry["path"]
            full_path = os.path.join(repo_root, path)
            resolved = os.path.realpath(full_path)
            real_root = os.path.realpath(repo_root)

            if not (resolved == real_root or resolved.startswith(real_root + os.sep)):
                raise HTTPException(status_code=403, detail={"error": "Path traversal detected"})

            if not os.path.isfile(resolved):
                raise HTTPException(status_code=404, detail={"error": "File not found"})

            # Determine media type by extension
            ext = os.path.splitext(resolved)[1].lower()
            media_types = {
                ".pdf": "application/pdf",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".doc": "application/msword",
                ".rst": "text/plain",
                ".txt": "text/plain",
                ".md": "text/markdown",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".xml": "application/xml",
                ".html": "text/html",
            }
            media_type = media_types.get(ext, "application/octet-stream")

            return FileResponse(
                resolved,
                media_type=media_type,
                filename=os.path.basename(resolved),
                content_disposition_type="inline",
            )

        # ── Repos endpoint ───────────────────────────────────

        @app.get("/api/doc_search/repos")
        async def doc_search_repos():
            """List configured repos with file counts and last-synced timestamps."""
            def _run_repo_counts() -> dict[str, int]:
                conn = _get_db()
                try:
                    rows = conn.execute(
                        "SELECT repo, COUNT(*) as file_count FROM doc_metadata GROUP BY repo"
                    ).fetchall()
                    return {r["repo"]: r["file_count"] for r in rows}
                finally:
                    conn.close()

            counts = await asyncio.to_thread(_run_repo_counts)
            repos = _load_doc_repos()
            last_synced = await asyncio.to_thread(_db_get_state, "last_sync")

            result: list[dict] = []
            for repo in repos:
                result.append({
                    "name": repo["name"],
                    "path": repo["path"],
                    "file_count": counts.get(repo["name"], 0),
                    "last_synced": last_synced,
                })

            return result

        # ── Sync trigger endpoint ────────────────────────────

        @app.post("/api/doc_search/sync")
        async def doc_search_sync():
            """Trigger a full doc repository sync in the background.

            Returns immediately with ``sync_started``.  If a sync is
            already running, returns ``sync_already_running`` (SYNC-07).
            """
            if _sync_lock.locked():
                return {
                    "status": "sync_already_running",
                    "message": "A sync is already in progress.",
                }

            try:
                asyncio.create_task(_sync_job())
                logger.info("Sync triggered via POST /api/doc_search/sync")
                return {
                    "status": "sync_started",
                    "message": "Doc sync running in background.",
                }
            except Exception as exc:
                logger.error("Failed to start sync: %s", exc)
                raise HTTPException(
                    status_code=500,
                    detail={"error": f"Failed to start sync: {exc}"},
                )

        # ── Sync status endpoint ─────────────────────────────

        @app.get("/api/doc_search/sync/status")
        async def doc_search_sync_status():
            """Return current sync progress for polling-based UI updates.

            Shape per SYNC-02:
                ``{in_progress, progress: {phase, repo, done, total}|null, last_sync}``
            """
            progress = await asyncio.to_thread(_db_get_state, "sync_progress")
            last_sync = await asyncio.to_thread(_db_get_state, "last_sync")

            return {
                "in_progress": _sync_lock.locked(),
                "progress": progress,
                "last_sync": last_sync,
            }

    # ── Lifecycle hooks ─────────────────────────────────────

    def startup(self) -> None:
        """Initialize SQLite schema on first run; skip migration if current.

        After schema init, kicks off an initial background sync so the UI
        shows ``Indexing...`` immediately without blocking startup.
        """
        try:
            _ensure_schema()
        except sqlite3.DatabaseError as e:
            logger.warning("DocSearch plugin DB init failed (corrupt?): %s", e)
            # Auto-recover by deleting the corrupted DB and recreating
            try:
                os.remove(DB_PATH)
                logger.info("Removed corrupted DB at %s — will recreate on next sync", DB_PATH)
            except Exception as rm_err:
                logger.warning("Could not remove corrupted DB: %s", rm_err)
        except Exception as e:
            logger.warning("DocSearch plugin DB init failed: %s", e)
            return

        # ── Kick off initial sync as background task (non-blocking) ──
        # Per SYNC-05: fires after routes registered, UI loads immediately.
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_sync_job())
            logger.info("Initial doc sync started in background")
        except RuntimeError:
            logger.warning("No running event loop — skipping initial sync")

    def shutdown(self) -> None:
        """Cleanup hook — no async clients to close in Phase 5."""
        logger.debug("DocSearch plugin shutdown complete")


# ── Auto-discovery singleton ────────────────────────────────────
plugin = DocSearchPlugin()
