# Phase 8: SQLite Persistence Foundation — Plan

**Goal:** Local store survives restarts, event-loop offload, timezone-correct dates.
**Requirements:** PERS-01, PERS-02, PERS-05, PERS-06
**Depends on:** nothing (M4 start)

## Approach

Create `app/plugins/jira_store.py`, a persistence module that mirrors the established
`doc_search.py` SQLite pattern (WAL, per-plugin DB, `_db_lock`, `_ensure_schema()` at
`startup()`, every blocking call via `asyncio.to_thread()`).

### 1. Schema (`jira_store.py`)
- `worklogs(id, account_id, issue_key, issue_summary, date, started, time_spent_seconds,
  comment, week_start, fetched_at)` — PK `(account_id, id)`.
- `assigned_tickets(key, summary, status, priority, attachment_count, has_folder,
  local_files, fetched_at)` — PK `key`.
- `cache_meta(account_id, week_start, fetched_at, complete)` — PK `(account_id, week_start)`.
- `non_working_days(date, reason)` — PK `date`.
- `schema_meta(key, value)` for `SCHEMA_VERSION`.
- `_ensure_schema()` called from `JiraTrackerPlugin.startup()`; on `DatabaseError` remove
  the DB file and recreate (mirrors doc_search recovery).

### 2. Store API (all synchronous; callers wrap in `asyncio.to_thread`)
- `ensure_schema()`
- `upsert_worklogs(account_id, rows)`, `get_worklogs(account_id, week_start)`,
  `get_worklogs_range(account_id, d_from, d_to)`
- `upsert_assigned(rows)`, `get_assigned()`
- `set_cache_meta(account_id, week_start, complete)`, `get_cache_meta(account_id, week_start)`
- `mark_stale_week(account_id, week_start)` (scoped delete — full invalidation later),
  `clear_all()` (explicit global clear only)
- `add_non_working_day(date, reason)`, `remove_non_working_day(date)`,
  `get_non_working_days()`
- Helpers: `_to_local_date(started)`, `_monday_of(date_str)`, `_now()`.

### 3. Event-loop fix (`jira_tracker.py`)
- JIRA client lazily created behind a lock; blocking helpers (`_api`, `_jira().search_issues`,
  `_fetch_worklogs_for_user`) invoked via `await asyncio.to_thread(...)` in routes.
- `_fetch_worklogs_for_user` persists fetched rows into the store (PERS-01/02) with a
  correct `date_local` (PERS-06).

### 4. Tests (`tests/test_jira_store.py`)
- schema creation + version; upsert then get round-trips.
- `date_local` correctness across a UTC-offset boundary (Pitfall 5).
- scoped `mark_stale_week` does not touch other weeks/accounts (Pitfall 2/13).
- assigned tickets upsert/get; non_working_days CRUD.
- `clear_all` empties tables.

### 5. Gitignore
- Add `jira_tracker.db`, `jira_tracker.db-wal`, `jira_tracker.db-shm`.

## Success Criteria
1. After restart the tracker renders previously loaded worklogs with no Jira call (data in SQLite).
2. Assigned tickets present immediately after restart.
3. Server stays responsive during Jira/SQLite ops (event loop not blocked).
4. A worklog near a local week boundary buckets into the correct local week.
