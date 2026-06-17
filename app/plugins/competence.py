"""
Competence & Performance Plugin — tracks bug return rate from Jira changelog history.
"""

from __future__ import annotations

import os
import json
import asyncio
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException

from app.plugins.base import ToolkitPlugin
from app import config

# ── Constants ──────────────────────────────────────────────
DOMAIN = "teltonika-telematics.atlassian.net"
SERVER = f"https://{DOMAIN}"
DB_PATH = os.path.join(os.path.dirname(__file__), "competence_cache.db")

# ── State machine status sets (configurable) ───────────────
RETURN_FROM = {"For Testing", "In Testing", "Test Failed", "Testing Failed"}
RETURN_TO = {"In Development", "In Progress", "Gathering Information", "To Do", "New"}
ATTEMPT_TO = {"Developed", "For Testing", "In Testing"}
ATTEMPT_FROM = {"In Development", "New", "Gathering Information"}

# ── Module-level state ─────────────────────────────────────
_db_lock = threading.Lock()
_http_client: httpx.AsyncClient | None = None


# ═══════════════════════════════════════════════════════════
#  SQLite helpers
# ═══════════════════════════════════════════════════════════

def _get_db() -> sqlite3.Connection:
    """Return a thread-safe SQLite connection with WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _db_get(key: str) -> str | None:
    """Synchronous read from sync_state key-value store."""
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
    """Synchronous write (insert-or-replace) to sync_state."""
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


async def _db_get_async(key: str) -> str | None:
    """Async wrapper — runs _db_get in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(_db_get, key)


async def _db_set_async(key: str, value: str) -> None:
    """Async wrapper — runs _db_set in a thread."""
    await asyncio.to_thread(_db_set, key, value)


# ═══════════════════════════════════════════════════════════
#  HTTP helpers (Jira REST API v3 via httpx)
# ═══════════════════════════════════════════════════════════

async def _get_client() -> httpx.AsyncClient:
    """Lazy-init a shared httpx AsyncClient with Jira BasicAuth."""
    global _http_client
    if _http_client is None:
        c = config.load_jira_config()
        email = c.get("email", "")
        token = c.get("token", "")
        if not email or not token:
            raise HTTPException(503, "Jira credentials not configured")
        _http_client = httpx.AsyncClient(
            base_url=f"{SERVER}/rest/api/3/",
            auth=httpx.BasicAuth(email, token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=httpx.Timeout(30.0),
        )
    return _http_client


async def _api_get(path: str, **params) -> dict:
    """Perform a GET against the Jira REST API v3 and return parsed JSON.

    Raises HTTPException on 4xx/5xx responses.
    """
    client = await _get_client()
    resp = await client.get(path, params=params)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()


async def _close_client() -> None:
    """Close the shared httpx client (called on plugin shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


# ═══════════════════════════════════════════════════════════
#  State machine — changelog parsing
# ═══════════════════════════════════════════════════════════

def _parse_changelog(
    changelog: dict,
    ticket_key: str,
    current_account_id: str,
) -> list[dict]:
    """Parse a Jira issue changelog into ATTEMPT / RETURN transitions.

    ATTEMPT: entering a testing status, authored by *current_account_id*.
    RETURN:  leaving a testing status back to development, AFTER a prior
             ATTEMPT was recorded for this ticket (any author).

    State tracking per ticket uses an ``in_testing`` boolean:
      - ATTEMPT sets ``in_testing = True``.
      - RETURN  sets ``in_testing = False`` (allowing another cycle).

    Returns a list of dicts with keys ``ticket_key``, ``transition_date``
    (ISO string), and ``action_type`` (``"ATTEMPT"`` or ``"RETURN"``).
    """
    transitions: list[dict] = []
    in_testing = False

    for entry in changelog.get("values", []):
        author = entry.get("author") or {}
        author_id = author.get("accountId", "")
        created = entry.get("created", "")

        for item in entry.get("items", []):
            if item.get("field") != "status":
                continue

            from_status = item.get("fromString", "")
            to_status = item.get("toString", "")

            if not from_status or not to_status:
                continue

            # ── Rule 1: ATTEMPT — authored by current user, entering testing ──
            if (
                from_status in ATTEMPT_FROM
                and to_status in ATTEMPT_TO
                and author_id == current_account_id
            ):
                transitions.append({
                    "ticket_key": ticket_key,
                    "transition_date": created,
                    "action_type": "ATTEMPT",
                })
                in_testing = True

            # ── Rule 2: RETURN — any author, leaving testing after attempt ──
            elif (
                in_testing
                and from_status in RETURN_FROM
                and to_status in RETURN_TO
            ):
                transitions.append({
                    "ticket_key": ticket_key,
                    "transition_date": created,
                    "action_type": "RETURN",
                })
                in_testing = False

    return transitions


# ═══════════════════════════════════════════════════════════
#  Stats helpers (pandas)
# ═══════════════════════════════════════════════════════════

def _format_2q_label(period: pd.Period) -> str:
    """Convert a 2Q pandas Period to a human-readable label.

    In pandas ``2Q`` frequency, ``period.quarter`` is 1 for the first
    half-year (Q1+Q2) and 3 for the second half-year (Q3+Q4).
    """
    year = period.year
    if period.quarter == 1:
        return f"{year} Q1-Q2"
    else:
        return f"{year} Q3-Q4"


def _load_transitions_df() -> pd.DataFrame:
    """Read all transitions from SQLite into a pandas DataFrame.

    Reads use WAL mode so no lock is required.
    """
    conn = _get_db()
    try:
        df = pd.read_sql_query(
            "SELECT id, ticket_key, transition_date, action_type "
            "FROM transitions ORDER BY transition_date",
            conn,
        )
    finally:
        conn.close()
    return df


# ═══════════════════════════════════════════════════════════
#  Background sync engine
# ═══════════════════════════════════════════════════════════

async def _sync_job() -> None:
    """Core sync pipeline: search Jira → fetch changelogs → parse →
    insert into SQLite.

    Runs as a background task spawned by ``asyncio.create_task()``.
    Uses an ``in_progress`` flag to prevent concurrent runs.
    """
    # ── Guard: prevent concurrent syncs ──────────────────────
    if await _db_get_async("in_progress") == "1":
        print("[competence] Sync already in progress")
        return

    await _db_set_async("in_progress", "1")
    try:
        # ── 1. Identify current user ─────────────────────────
        myself = await _api_get("myself")
        current_account_id: str = myself.get("accountId", "")
        if not current_account_id:
            print("[competence] Could not determine current user accountId")
            return

        # ── 2. Build JQL ──────────────────────────────────────
        last_sync = await _db_get_async("last_sync")
        if last_sync:
            # Incremental — only issues touched since last run
            jql = (
                f"(assignee WAS currentUser() OR reporter = currentUser()) "
                f"AND updated >= '{last_sync}'"
            )
        else:
            # First sync — full history
            jql = "assignee WAS currentUser() OR reporter = currentUser()"

        # ── 3. Search for issues (paginated) ──────────────────
        all_issues: list[dict] = []
        start_at = 0
        max_results = 1000
        while True:
            resp = await _api_get(
                "search",
                jql=jql,
                fields="key",
                maxResults=max_results,
                startAt=start_at,
            )
            batch = resp.get("issues", [])
            all_issues.extend(batch)
            total: int = resp.get("total", 0)
            start_at += len(batch)
            if start_at >= total:
                break

        issue_keys = [iss["key"] for iss in all_issues]
        print(f"[competence] Found {len(issue_keys)} issues to scan")

        # ── 4. Fetch changelogs with concurrency limit ────────
        semaphore = asyncio.Semaphore(5)

        async def _fetch_changelog(key: str) -> tuple[str, list[dict]]:
            async with semaphore:
                try:
                    entries: list[dict] = []
                    start = 0
                    page_size = 100
                    while True:
                        data = await _api_get(
                            f"issue/{key}/changelog",
                            maxResults=page_size,
                            startAt=start,
                        )
                        batch = data.get("values", [])
                        entries.extend(batch)
                        if len(batch) < page_size:
                            break
                        start += len(batch)
                    return key, entries
                except HTTPException:
                    raise
                except Exception as exc:
                    print(
                        f"[competence] Failed to fetch changelog for {key}: {exc}"
                    )
                    return key, []

        tasks = [_fetch_changelog(key) for key in issue_keys]
        results = await asyncio.gather(*tasks)

        # ── 5. Parse changelogs through state machine ─────────
        all_transitions: list[dict] = []
        for key, entries in results:
            if not entries:
                continue
            parsed = _parse_changelog(
                {"values": entries}, key, current_account_id
            )
            all_transitions.extend(parsed)

        # ── 6. Deduplicate & insert into SQLite ──────────────
        inserted = 0
        for t in all_transitions:
            with _db_lock:
                conn = _get_db()
                try:
                    # Check for existing duplicate
                    existing = conn.execute(
                        "SELECT 1 FROM transitions "
                        "WHERE ticket_key = ? AND transition_date = ? "
                        "AND action_type = ?",
                        (t["ticket_key"], t["transition_date"], t["action_type"]),
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            "INSERT INTO transitions "
                            "(ticket_key, transition_date, action_type) "
                            "VALUES (?, ?, ?)",
                            (t["ticket_key"], t["transition_date"], t["action_type"]),
                        )
                        conn.commit()
                        inserted += 1
                finally:
                    conn.close()

        # ── 7. Update last_sync timestamp ────────────────────
        await _db_set_async("last_sync", datetime.now(timezone.utc).isoformat())

        print(
            f"[competence] Sync complete: {len(issue_keys)} issues, "
            f"{len(all_transitions)} transitions ({inserted} new)"
        )

    except HTTPException as e:
        print(f"[competence] Sync error (Jira): {e.status_code} {e.detail}")
    except Exception as e:
        print(f"[competence] Sync failed: {e}")
    finally:
        await _db_set_async("in_progress", "0")


# ═══════════════════════════════════════════════════════════
#  Plugin class
# ═══════════════════════════════════════════════════════════

class CompetencePlugin(ToolkitPlugin):
    id = "competence"
    name = "Competence Matrix"
    icon = "📈"
    order = 45

    # ── Route registration ──────────────────────────────────

    def register_routes(self, app: FastAPI) -> None:

        @app.get("/api/competence/stats")
        async def competence_stats():
            """Return bug return rate aggregated by 2-quarter periods."""
            try:
                df = _load_transitions_df()
                if df.empty:
                    return []

                df["transition_date"] = pd.to_datetime(df["transition_date"])
                grouped = df.groupby(
                    pd.Grouper(key="transition_date", freq="2Q")
                )

                result: list[dict] = []
                for period, group in grouped:
                    attempts = int((group["action_type"] == "ATTEMPT").sum())
                    returns = int((group["action_type"] == "RETURN").sum())
                    rate = (
                        round((returns / attempts * 100), 1)
                        if attempts > 0
                        else 0.0
                    )
                    result.append({
                        "period": _format_2q_label(period),
                        "attempts": attempts,
                        "returns": returns,
                        "return_rate_pct": rate,
                    })

                return result
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.post("/api/competence/sync")
        async def competence_sync():
            """Kick off a background Jira changelog sync."""
            try:
                in_progress = await _db_get_async("in_progress")
                if in_progress == "1":
                    return {
                        "status": "sync_already_running",
                        "message": "A sync job is already in progress.",
                    }

                asyncio.create_task(_sync_job())
                return {
                    "status": "sync_started",
                    "message": "Jira sync running in background.",
                }
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/api/competence/sync/status")
        async def competence_sync_status():
            """Report last sync timestamp and whether a job is in progress."""
            try:
                last_sync = await _db_get_async("last_sync")
                in_progress = await _db_get_async("in_progress")
                return {
                    "last_sync": last_sync,
                    "in_progress": in_progress == "1",
                }
            except Exception as e:
                raise HTTPException(500, str(e))

    # ── Lifecycle hooks ─────────────────────────────────────

    def startup(self) -> None:
        """Create SQLite tables and indexes on first launch."""
        try:
            with _db_lock:
                conn = _get_db()
                try:
                    conn.executescript("""
                        CREATE TABLE IF NOT EXISTS sync_state (
                            key TEXT PRIMARY KEY,
                            value TEXT
                        );

                        CREATE TABLE IF NOT EXISTS transitions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ticket_key  TEXT NOT NULL,
                            transition_date TEXT NOT NULL,
                            action_type TEXT NOT NULL
                                CHECK(action_type IN ('ATTEMPT', 'RETURN'))
                        );

                        CREATE INDEX IF NOT EXISTS idx_transitions_date
                            ON transitions(transition_date);

                        CREATE INDEX IF NOT EXISTS idx_transitions_ticket
                            ON transitions(ticket_key);
                    """)
                    conn.commit()
                finally:
                    conn.close()
            print(f"[competence] SQLite initialized at {DB_PATH}")
        except Exception as e:
            print(f"[warn] Competence plugin DB init failed: {e}")

    def shutdown(self) -> None:
        """Close the shared httpx client if it was created."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_close_client())
        except RuntimeError:
            # No running loop — nothing to clean up
            pass


# ── Auto-discovery singleton ────────────────────────────────────
plugin = CompetencePlugin()
