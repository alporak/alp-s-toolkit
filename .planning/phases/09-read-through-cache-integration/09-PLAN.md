# Phase 9: Read-Through Cache Integration — Plan

**Goal:** TTL + stale-serve read path; scoped `(account, week)` invalidation on writes.
**Requirements:** PERS-03, PERS-04
**Depends on:** Phase 8

## Approach

### 1. Store — precise lookup
- `get_worklog(account_id, worklog_id)` → single row (for delete invalidation).

### 2. Read-through in `jira_tracker.py`
- `_load_weekly(account_id, d_from, d_to, display_name, force)`:
  - `week_start = jira_store._monday_of(d_from)`
  - if cache fresh (cache_meta within TTL) and not force → return stored rows,
    `(cached=True, stale=False)`.
  - else fetch via `asyncio.to_thread(_fetch_worklogs_for_user, ...)` (persists + sets
    meta) → return `(cached=False, stale=False)`.
  - on fetch error → if stored rows exist, return them with `(cached=True, stale=True)`;
    else re-raise (Pitfall 9).
  - in-flight guard: concurrent callers for same `(account_id, week_start)` await one
    future.
- Weekly route uses `_load_weekly`; response includes `stale` flag.

### 3. Scoped invalidation on writes
- `_invalidate_for_write(date_str=None, worklog_id=None)`: resolve current user id,
  compute week_start (from `date_str[:10]` or the stored worklog's `week_start`), call
  `jira_store.mark_stale_week`.
- Replace `_cache_clear()` in `POST/PUT/DELETE /worklog` and `/meeting` with
  `await _invalidate_for_write(...)`. Keep `_cache_clear()` only for `/cache/clear`.
- Weekly `force_refresh` → `jira_store.mark_stale_week(t_id, week_start)`.

### 4. Tests (`tests/test_jira_store.py` additions)
- `get_worklog` returns the right row.
- stale-serve behavior mocked: with a fake fetcher that raises, `_load_weekly` returns
  stored rows with stale=True when present (unit-level by calling the cache-meta logic).
- scoped invalidation removes only the affected week (covered in Phase 8 tests; add a
  route-level check that `_invalidate_for_write` targets the correct week).

## Success Criteria
1. Jira unreachable → last cached worklogs served with `stale` indicator.
2. After a write, only the affected `(account, week)` refreshes; other weeks/accounts stay cached.
3. On cache miss/TTL expiry, transparent Jira fetch + repopulate SQLite.
