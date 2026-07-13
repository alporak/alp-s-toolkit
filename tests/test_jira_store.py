"""
Tests for the Jira Tracker local persistence store (Phase 8).

These run without any Jira credentials — the store is a pure SQLite mirror.
"""

import os
import tempfile
from datetime import timezone, timedelta

import pytest

from app.plugins import jira_store


@pytest.fixture
def store():
    """Point the store at a temp DB and reset it between tests."""
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "jira_tracker_test.db")
    jira_store.DB_PATH = db
    # Deterministic local TZ (UTC+3, like Vilnius summer) for boundary tests.
    jira_store.LOCAL_TZ = timezone(timedelta(hours=3))
    jira_store.ensure_schema()
    yield jira_store
    for ext in ("", "-wal", "-shm"):
        p = db + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def test_ensure_schema_creates_tables_and_version(store):
    import sqlite3

    conn = sqlite3.connect(store.DB_PATH)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"worklogs", "assigned_tickets", "cache_meta",
            "non_working_days", "schema_meta"} <= tables
    meta = store.get_cache_meta  # ensure module loaded
    assert store.SCHEMA_VERSION == "1"


def test_upsert_and_get_worklogs(store):
    rows = [
        {"id": "1", "ticket_key": "FMBP-1", "ticket_summary": "Do thing",
         "date": "2026-07-13", "started": "2026-07-13T08:00:00.000+0000",
         "time_spent_seconds": 3600, "comment": "x"},
        {"id": "2", "ticket_key": "FMBP-2", "ticket_summary": "Other",
         "date": "2026-07-14", "started": "2026-07-14T09:00:00.000+0000",
         "time_spent_seconds": 7200, "comment": "y"},
    ]
    store.upsert_worklogs("acc1", rows)
    got = store.get_worklogs("acc1", "2026-07-13")  # Monday of that week
    assert len(got) == 2
    ids = {r["id"] for r in got}
    assert ids == {"1", "2"}


def test_local_date_boundary(store):
    # UTC+3 local TZ. 01:00 UTC Mon = 04:00 local Mon -> 2026-07-13
    assert store._to_local_date("2026-07-13T01:00:00.000+0000") == "2026-07-13"
    # 21:00 UTC Sun = 00:00 local Mon -> 2026-07-13 (boundary rolls forward)
    assert store._to_local_date("2026-07-12T21:00:00.000+0000") == "2026-07-13"
    # 20:00 UTC Sun = 23:00 local Sun -> 2026-07-12 (boundary stays)
    assert store._to_local_date("2026-07-12T20:00:00.000+0000") == "2026-07-12"


def test_scoped_invalidation(store):
    store.upsert_worklogs("A", [{"id": "1", "ticket_key": "FMBP-1",
                                 "started": "2026-07-13T08:00:00.000+0000",
                                 "time_spent_seconds": 1}])
    store.upsert_worklogs("B", [{"id": "2", "ticket_key": "FMBP-1",
                                 "started": "2026-07-13T08:00:00.000+0000",
                                 "time_spent_seconds": 1}])
    store.upsert_worklogs("A", [{"id": "3", "ticket_key": "FMBP-1",
                                 "started": "2026-07-20T08:00:00.000+0000",
                                 "time_spent_seconds": 1}])
    # Cache meta so the read path would consider them fresh
    store.set_cache_meta("A", "2026-07-13")
    store.set_cache_meta("A", "2026-07-20")
    store.set_cache_meta("B", "2026-07-13")

    store.mark_stale_week("A", "2026-07-13")

    # Only A's week 2026-07-13 removed
    assert store.get_worklogs("A", "2026-07-13") == []
    assert len(store.get_worklogs("A", "2026-07-20")) == 1
    assert len(store.get_worklogs("B", "2026-07-13")) == 1
    assert store.get_cache_meta("A", "2026-07-13") is None
    assert store.get_cache_meta("A", "2026-07-20") is not None
    assert store.get_cache_meta("B", "2026-07-13") is not None


def test_assigned_upsert_get(store):
    rows = [{"key": "FMBP-1", "summary": "s", "status": "In Progress",
             "priority": "High", "attachment_count": 2, "has_folder": True,
             "local_files": 1}]
    store.upsert_assigned(rows)
    got = store.get_assigned()
    assert len(got) == 1
    assert got[0]["key"] == "FMBP-1"
    assert got[0]["attachment_count"] == 2


def test_non_working_days_crud(store):
    store.add_non_working_day("2026-07-15", "PTO")
    assert "2026-07-15" in store.get_non_working_days()
    store.remove_non_working_day("2026-07-15")
    assert "2026-07-15" not in store.get_non_working_days()


def test_clear_all(store):
    store.upsert_worklogs("A", [{"id": "1", "ticket_key": "FMBP-1",
                                 "started": "2026-07-13T08:00:00.000+0000",
                                 "time_spent_seconds": 1}])
    store.upsert_assigned([{"key": "FMBP-1"}])
    store.clear_all()
    assert store.get_worklogs("A", "2026-07-13") == []
    assert store.get_assigned() == []
