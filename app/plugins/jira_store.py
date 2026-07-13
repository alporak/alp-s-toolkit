"""
Jira Tracker — local persistence store.

A SQLite read-through mirror of Jira worklog / assigned-ticket data. This is the
foundation layer for the M4 rework: it lets the Jira Tracker render instantly after a
restart and powers the insights engine (Phase 11) and notifications (Phase 12).

Convention mirror: ``doc_search.py`` — co-located DB, WAL mode, ``threading.Lock`` for
writes, ``_ensure_schema()`` at startup, every blocking call via ``asyncio.to_thread()``.

Jira is the authoritative source. The store is a read-only mirror except for
``non_working_days``, which is locally-authored user metadata used by the insights engine.
"""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

from app import config

DB_PATH = os.path.join(os.path.dirname(__file__), "jira_tracker.db")
SCHEMA_VERSION = "1"

_db_lock = threading.Lock()

# Local timezone for week-boundary math. Default to Europe/Vilnius (user's TZ); fall back
# to the machine's local timezone if the IANA database is unavailable.
try:
    from zoneinfo import ZoneInfo

    try:
        LOCAL_TZ = ZoneInfo("Europe/Vilnius")
    except Exception:
        LOCAL_TZ = datetime.now().astimezone().tz
except Exception:  # pragma: no cover - zoneinfo always present on py3.9+
    LOCAL_TZ = datetime.now().astimezone().tz


# ── Low-level DB helpers ────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    """Open (or create) the jira_tracker SQLite database with WAL mode."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _monday_of(date_str: str) -> str:
    """Return the ISO Monday of the week containing *date_str* (YYYY-MM-DD)."""
    if not date_str:
        return ""
    d = date.fromisoformat(date_str)
    return (d - timedelta(days=d.weekday())).isoformat()


def _to_local_date(started: str) -> str:
    """Convert a Jira ``started`` timestamp to the local YYYY-MM-DD date.

    Jira returns e.g. ``2026-07-13T02:00:00.000+0000``. The trailing offset lacks a
    colon, so normalize before ``datetime.fromisoformat`` and then convert to LOCAL_TZ.
    Falls back to the raw ``YYYY-MM-DD`` slice if parsing fails.
    """
    if not started:
        return ""
    s = started
    m = re.search(r"([+-]\d{2})(\d{2})$", s)
    if m:
        s = s[: m.start()] + m.group(1) + ":" + m.group(2)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # last resort: assume the first 10 chars are already a usable date
        return started[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ).date().isoformat()


# ── Schema ──────────────────────────────────────────────────────────────

def ensure_schema() -> None:
    """Create tables if missing. Mirrors doc_search recovery on corruption."""
    try:
        with _db_lock:
            conn = _get_db()
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS schema_meta ("
                    "  key TEXT PRIMARY KEY, value TEXT)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS worklogs ("
                    "  id TEXT NOT NULL,"
                    "  account_id TEXT NOT NULL,"
                    "  issue_key TEXT NOT NULL DEFAULT '',"
                    "  issue_summary TEXT NOT NULL DEFAULT '',"
                    "  date TEXT NOT NULL DEFAULT '',"
                    "  started TEXT NOT NULL DEFAULT '',"
                    "  time_spent_seconds INTEGER NOT NULL DEFAULT 0,"
                    "  comment TEXT NOT NULL DEFAULT '',"
                    "  week_start TEXT NOT NULL DEFAULT '',"
                    "  fetched_at TEXT NOT NULL DEFAULT '',"
                    "  PRIMARY KEY (account_id, id))"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_wl_week "
                    "ON worklogs(account_id, week_start)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_wl_date "
                    "ON worklogs(account_id, date)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS assigned_tickets ("
                    "  key TEXT PRIMARY KEY,"
                    "  summary TEXT NOT NULL DEFAULT '',"
                    "  status TEXT NOT NULL DEFAULT '',"
                    "  priority TEXT NOT NULL DEFAULT '',"
                    "  attachment_count INTEGER NOT NULL DEFAULT 0,"
                    "  has_folder INTEGER NOT NULL DEFAULT 0,"
                    "  local_files INTEGER NOT NULL DEFAULT 0,"
                    "  fetched_at TEXT NOT NULL DEFAULT '')"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS cache_meta ("
                    "  account_id TEXT NOT NULL,"
                    "  week_start TEXT NOT NULL,"
                    "  fetched_at TEXT NOT NULL DEFAULT '',"
                    "  complete INTEGER NOT NULL DEFAULT 1,"
                    "  PRIMARY KEY (account_id, week_start))"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS non_working_days ("
                    "  date TEXT PRIMARY KEY,"
                    "  reason TEXT NOT NULL DEFAULT '')"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS teltoheart_tickets ("
                    "  issue_key TEXT PRIMARY KEY)"
                )
                conn.execute(
                    "INSERT OR REPLACE INTO schema_meta (key, value) "
                    "VALUES ('version', ?)",
                    (SCHEMA_VERSION,),
                )
                conn.commit()
            finally:
                conn.close()
    except sqlite3.DatabaseError:
        # Corrupted DB — remove and recreate (toolkit recovery pattern).
        try:
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            for side in (DB_PATH + "-wal", DB_PATH + "-shm"):
                if os.path.exists(side):
                    os.remove(side)
        except OSError:
            pass
        with _db_lock:
            conn = _get_db()
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS schema_meta ("
                    "  key TEXT PRIMARY KEY, value TEXT)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS worklogs ("
                    "  id TEXT NOT NULL,"
                    "  account_id TEXT NOT NULL,"
                    "  issue_key TEXT NOT NULL DEFAULT '',"
                    "  issue_summary TEXT NOT NULL DEFAULT '',"
                    "  date TEXT NOT NULL DEFAULT '',"
                    "  started TEXT NOT NULL DEFAULT '',"
                    "  time_spent_seconds INTEGER NOT NULL DEFAULT 0,"
                    "  comment TEXT NOT NULL DEFAULT '',"
                    "  week_start TEXT NOT NULL DEFAULT '',"
                    "  fetched_at TEXT NOT NULL DEFAULT '',"
                    "  PRIMARY KEY (account_id, id))"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_wl_week "
                    "ON worklogs(account_id, week_start)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_wl_date "
                    "ON worklogs(account_id, date)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS assigned_tickets ("
                    "  key TEXT PRIMARY KEY,"
                    "  summary TEXT NOT NULL DEFAULT '',"
                    "  status TEXT NOT NULL DEFAULT '',"
                    "  priority TEXT NOT NULL DEFAULT '',"
                    "  attachment_count INTEGER NOT NULL DEFAULT 0,"
                    "  has_folder INTEGER NOT NULL DEFAULT 0,"
                    "  local_files INTEGER NOT NULL DEFAULT 0,"
                    "  fetched_at TEXT NOT NULL DEFAULT '')"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS cache_meta ("
                    "  account_id TEXT NOT NULL,"
                    "  week_start TEXT NOT NULL,"
                    "  fetched_at TEXT NOT NULL DEFAULT '',"
                    "  complete INTEGER NOT NULL DEFAULT 1,"
                    "  PRIMARY KEY (account_id, week_start))"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS non_working_days ("
                    "  date TEXT PRIMARY KEY,"
                    "  reason TEXT NOT NULL DEFAULT '')"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS teltoheart_tickets ("
                    "  issue_key TEXT PRIMARY KEY)"
                )
                conn.execute(
                    "INSERT OR REPLACE INTO schema_meta (key, value) "
                    "VALUES ('version', ?)",
                    (SCHEMA_VERSION,),
                )
                conn.commit()
            finally:
                conn.close()


# ── Worklogs ────────────────────────────────────────────────────────────

def upsert_worklogs(account_id: str, rows: list[dict]) -> None:
    """Persist fetched worklogs for *account_id*. Idempotent (INSERT OR REPLACE)."""
    with _db_lock:
        conn = _get_db()
        try:
            for r in rows:
                started = r.get("started", "")
                date_local = _to_local_date(started) or (r.get("date") or "")[:10]
                week_start = _monday_of(date_local) if date_local else ""
                conn.execute(
                    "INSERT OR REPLACE INTO worklogs "
                    "(id, account_id, issue_key, issue_summary, date, started, "
                    " time_spent_seconds, comment, week_start, fetched_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        r.get("id"),
                        account_id,
                        r.get("ticket_key", ""),
                        r.get("ticket_summary", ""),
                        date_local,
                        started,
                        int(r.get("time_spent_seconds") or 0),
                        r.get("comment", ""),
                        week_start,
                        _now(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def get_worklog(account_id: str, worklog_id: str) -> dict | None:
    """Return a single stored worklog by id (for precise invalidation)."""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT * FROM worklogs WHERE account_id=? AND id=?",
                (account_id, worklog_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_worklogs(account_id: str, week_start: str) -> list[dict]:
    """Return all stored worklogs for *account_id* in the week starting *week_start*."""
    with _db_lock:
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM worklogs WHERE account_id=? AND week_start=? "
                "ORDER BY started DESC",
                (account_id, week_start),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_worklogs_range(account_id: str, d_from: str, d_to: str) -> list[dict]:
    """Return stored worklogs for *account_id* between *d_from* and *d_to* (inclusive)."""
    with _db_lock:
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM worklogs WHERE account_id=? AND date >= ? AND date <= ? "
                "ORDER BY date ASC, started ASC",
                (account_id, d_from, d_to),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Assigned tickets ────────────────────────────────────────────────────

def upsert_assigned(rows: list[dict]) -> None:
    with _db_lock:
        conn = _get_db()
        try:
            for t in rows:
                conn.execute(
                    "INSERT OR REPLACE INTO assigned_tickets "
                    "(key, summary, status, priority, attachment_count, has_folder, "
                    " local_files, fetched_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        t.get("key"),
                        t.get("summary", ""),
                        t.get("status", ""),
                        t.get("priority", ""),
                        int(t.get("attachment_count") or 0),
                        int(bool(t.get("has_folder"))),
                        int(t.get("local_files") or 0),
                        _now(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def get_assigned() -> list[dict]:
    with _db_lock:
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM assigned_tickets ORDER BY key"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Cache metadata ──────────────────────────────────────────────────────

def set_cache_meta(account_id: str, week_start: str, complete: bool = True) -> None:
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO cache_meta "
                "(account_id, week_start, fetched_at, complete) VALUES (?,?,?,?)",
                (account_id, week_start, _now(), 1 if complete else 0),
            )
            conn.commit()
        finally:
            conn.close()


def get_cache_meta(account_id: str, week_start: str) -> dict | None:
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT * FROM cache_meta WHERE account_id=? AND week_start=?",
                (account_id, week_start),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


# ── Invalidation ────────────────────────────────────────────────────────

def mark_stale_week(account_id: str, week_start: str) -> None:
    """Scoped invalidation: drop only this (account, week). Never a global clear."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "DELETE FROM worklogs WHERE account_id=? AND week_start=?",
                (account_id, week_start),
            )
            conn.execute(
                "DELETE FROM cache_meta WHERE account_id=? AND week_start=?",
                (account_id, week_start),
            )
            conn.commit()
        finally:
            conn.close()


def clear_all() -> None:
    """Global clear — only for an explicit user action, never on a normal write."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("DELETE FROM worklogs")
            conn.execute("DELETE FROM assigned_tickets")
            conn.execute("DELETE FROM cache_meta")
            conn.commit()
        finally:
            conn.close()


# ── Non-working days (locally authored metadata) ────────────────────────

def add_non_working_day(d: str, reason: str = "") -> None:
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO non_working_days (date, reason) VALUES (?,?)",
                (d, reason),
            )
            conn.commit()
        finally:
            conn.close()


def remove_non_working_day(d: str) -> None:
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("DELETE FROM non_working_days WHERE date=?", (d,))
            conn.commit()
        finally:
            conn.close()


def get_non_working_days() -> list[str]:
    with _db_lock:
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT date FROM non_working_days ORDER BY date"
            ).fetchall()
            return [r["date"] for r in rows]
        finally:
            conn.close()


def get_non_working_days_in_range(d_from: str, d_to: str) -> list[str]:
    with _db_lock:
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT date FROM non_working_days WHERE date >= ? AND date <= ? "
                "ORDER BY date",
                (d_from, d_to),
            ).fetchall()
            return [r["date"] for r in rows]
        finally:
            conn.close()


# ── TeltoHeart side-project tickets (Phase 13) ───────────────────────

def mark_teltoheart_ticket(issue_key: str) -> None:
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO teltoheart_tickets (issue_key) VALUES (?)",
                (issue_key,),
            )
            conn.commit()
        finally:
            conn.close()


def unmark_teltoheart_ticket(issue_key: str) -> None:
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "DELETE FROM teltoheart_tickets WHERE issue_key=?",
                (issue_key,),
            )
            conn.commit()
        finally:
            conn.close()


def get_teltoheart_tickets() -> list[str]:
    with _db_lock:
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT issue_key FROM teltoheart_tickets ORDER BY issue_key"
            ).fetchall()
            return [r["issue_key"] for r in rows]
        finally:
            conn.close()


def get_teltoheart_hours(d_from: str, d_to: str) -> list[dict]:
    """Return per-account total seconds for worklogs on TeltoHeart tickets
    in the given date range. Requires worklogs to have been cached first."""
    tickets = get_teltoheart_tickets()
    if not tickets:
        return []
    placeholders = ",".join("?" for _ in tickets)
    with _db_lock:
        conn = _get_db()
        try:
            rows = conn.execute(
                f"SELECT account_id, SUM(time_spent_seconds) AS total_seconds "
                f"FROM worklogs WHERE issue_key IN ({placeholders}) "
                f"AND date >= ? AND date <= ? "
                f"GROUP BY account_id",
                tickets + [d_from, d_to],
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Insights engine (Phase 11) ────────────────────────────────────────────

def compute_insights(
    rows: list[dict],
    non_working_days: list[str],
    daily_target_sec: int = 8 * 3600,
    daily_min_sec: int = 4 * 3600,
) -> dict:
    """Pure function: compute missing-days / under-target / low-hours from
    stored worklog rows and a set of non-working dates.

    Returns a dict with: total_seconds, target_seconds, working_days,
    below_target, gap_seconds, missing_days, low_days, per_day, warned_days.
    """
    from datetime import date as _date, timedelta as _td

    if not rows:
        return {
            "total_seconds": 0, "target_seconds": 0, "working_days": 0,
            "below_target": False, "gap_seconds": 0,
            "missing_days": [], "low_days": [], "per_day": {},
            "warned_days": [],
        }

    nwd = set(non_working_days)
    by_date: dict[str, int] = {}
    for w in rows:
        d = (w.get("date") or "")[:10]
        if not d:
            continue
        by_date[d] = by_date.get(d, 0) + int(w.get("time_spent_seconds") or 0)

    week_start = rows[0].get("week_start", "")
    if not week_start:
        return {
            "total_seconds": sum(by_date.values()), "target_seconds": 0,
            "working_days": 0, "below_target": False, "gap_seconds": 0,
            "missing_days": [], "low_days": [], "per_day": by_date,
            "warned_days": [],
        }

    try:
        monday = _date.fromisoformat(week_start)
    except ValueError:
        return {
            "total_seconds": sum(by_date.values()), "target_seconds": 0,
            "working_days": 0, "below_target": False, "gap_seconds": 0,
            "missing_days": [], "low_days": [], "per_day": by_date,
            "warned_days": [],
        }
    week_dates = [monday + _td(days=i) for i in range(7)]
    working = [d for d in week_dates if d.weekday() < 5 and d.isoformat() not in nwd]
    target = daily_target_sec * len(working)
    total = sum(by_date.values())

    missing_days: list[str] = []
    low_days: list[str] = []
    warned_days: list[str] = []
    for d in working:
        ds = d.isoformat()
        secs = by_date.get(ds, 0)
        if secs == 0:
            missing_days.append(ds)
        elif secs < daily_min_sec:
            low_days.append(ds)
    # Days marked non-working that have logged hours → warn
    for nd in nwd:
        if nd in by_date:
            warned_days.append(nd)

    return {
        "total_seconds": total,
        "target_seconds": target,
        "working_days": len(working),
        "below_target": total < target,
        "gap_seconds": max(0, target - total),
        "missing_days": missing_days,
        "low_days": low_days,
        "per_day": {d.isoformat(): by_date.get(d.isoformat(), 0) for d in working},
        "warned_days": warned_days,
    }
