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

import logging
import os
import sqlite3
import threading

from fastapi import FastAPI

from app.plugins.base import ToolkitPlugin

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
                            content='doc_metadata',
                            content_rowid='id',
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
