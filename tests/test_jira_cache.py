"""
Phase 9 tests — read-through cache, stale-serve, scoped invalidation.

Network calls are monkeypatched; the store is the real SQLite mirror.
"""

import asyncio
import os
import tempfile
from datetime import timezone, timedelta

import pytest

from app.plugins import jira_store
from app.plugins import jira_tracker


@pytest.fixture
def cache_setup():
    tmp = tempfile.mkdtemp()
    jira_store.DB_PATH = os.path.join(tmp, "jira_tracker_test.db")
    jira_store.LOCAL_TZ = timezone(timedelta(hours=3))
    jira_store.ensure_schema()
    jira_tracker._inflight.clear()
    yield
    for ext in ("", "-wal", "-shm"):
        p = jira_store.DB_PATH + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def _fake_fetch(account_id, d_from, d_to, display_name=""):
    week = jira_store._monday_of(d_from)
    rows = [{
        "id": f"{account_id}-{week}", "ticket_key": "FMBP-1",
        "ticket_summary": "s", "date": d_from,
        "started": f"{d_from}T08:00:00.000+0000",
        "time_spent_seconds": 3600, "comment": "x",
    }]
    jira_store.upsert_worklogs(account_id, rows)
    jira_store.set_cache_meta(account_id, week, complete=True)
    return rows, False


def test_get_worklog(cache_setup):
    jira_store.upsert_worklogs("A", [{
        "id": "w1", "ticket_key": "F",
        "started": "2026-07-13T08:00:00.000+0000", "time_spent_seconds": 1}])
    row = jira_store.get_worklog("A", "w1")
    assert row and row["id"] == "w1"
    assert jira_store.get_worklog("A", "nope") is None


def test_read_through_fresh_then_cached(cache_setup, monkeypatch):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return _fake_fetch(*a, **k)

    monkeypatch.setattr(jira_tracker, "_fetch_worklogs_for_user", fake)
    acc, d_from, d_to = "acc1", "2026-07-13", "2026-07-19"

    rows, cached, stale = asyncio.run(
        jira_tracker._load_weekly(acc, d_from, d_to, "Me"))
    assert cached is False and stale is False and calls["n"] == 1

    # Within TTL → served from SQLite, no new fetch
    rows2, cached2, stale2 = asyncio.run(
        jira_tracker._load_weekly(acc, d_from, d_to, "Me"))
    assert cached2 is True and stale2 is False and calls["n"] == 1
    assert len(rows2) == 1

    # Force refresh → re-fetch
    asyncio.run(jira_tracker._load_weekly(acc, d_from, d_to, "Me", force=True))
    assert calls["n"] == 2


def test_stale_serve_on_failure(cache_setup, monkeypatch):
    # Force TTL to 0 so the cache is never "fresh" → every read re-fetches,
    # exercising stale-serve when the fetch fails.
    monkeypatch.setattr(jira_tracker, "_cache_ttl", lambda: 0)
    monkeypatch.setattr(jira_tracker, "_fetch_worklogs_for_user", _fake_fetch)
    acc, d_from = "acc2", "2026-07-13"
    asyncio.run(jira_tracker._load_weekly(acc, d_from, "2026-07-19", "Me"))

    def boom(*a, **k):
        raise RuntimeError("jira down")

    monkeypatch.setattr(jira_tracker, "_fetch_worklogs_for_user", boom)
    rows, cached, stale = asyncio.run(
        jira_tracker._load_weekly(acc, d_from, "2026-07-19", "Me"))
    assert stale is True and cached is True and len(rows) == 1


def test_scoped_invalidation(cache_setup, monkeypatch):
    class FakeResp:
        ok = True

        def json(self):
            return {"accountId": "me1"}

    monkeypatch.setattr(jira_tracker, "_api", lambda *a, **k: FakeResp())

    for wd in ("2026-07-13", "2026-07-20"):
        jira_store.upsert_worklogs("me1", [{
            "id": f"x-{wd}", "ticket_key": "F",
            "started": f"{wd}T08:00:00.000+0000", "time_spent_seconds": 1}])
        jira_store.set_cache_meta("me1", jira_store._monday_of(wd))

    asyncio.run(jira_tracker._invalidate_for_write(date_str="2026-07-13"))

    assert jira_store.get_worklogs("me1", "2026-07-13") == []
    assert len(jira_store.get_worklogs("me1", "2026-07-20")) == 1
