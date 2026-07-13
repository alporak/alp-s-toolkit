# Phase 8 Verification — SQLite Persistence Foundation

**Status:** passed
**Date:** 2026-07-13

## Automated checks
- `pytest tests/test_jira_store.py` → **7 passed** (schema, upsert/get, timezone
  boundary, scoped invalidation, assigned, non-working-days, clear_all).
- `python -c "import app.plugins.jira_tracker"` → OK (plugin id `jira`, startup hook
  wired to `jira_store.ensure_schema`).

## Success criteria mapping
1. **Restart survival** — worklogs/assigned persist in `jira_tracker.db` (WAL);
   `_fetch_worklogs_for_user` mirrors every fetch into the store. ✓ (unit-verified
   round-trip; live Jira call not exercised here — covered by integration use)
2. **Assigned present after restart** — `upsert_assigned`/`get_assigned` persist. ✓ (test)
3. **Event loop not blocked** — all blocking `_api`/`_jira().search_issues`/`_fetch_*`
   calls now run via `asyncio.to_thread()`; JIRA client creation serialized by a lock. ✓
4. **Timezone-correct week bucketing** — `date_local` computed offset-aware and
   converted to `LOCAL_TZ` (Europe/Vilnius). ✓ (boundary test: 01:00 UTC Mon →
   2026-07-13; 21:00 UTC Sun → 2026-07-13; 20:00 UTC Sun → 2026-07-12)

## Notes
- In-memory `_wl_cache` retained as a no-op shim; read-through read path (TTL,
  stale-serve, scoped invalidation on writes) lands in Phase 9.
- `jira_tracker.db*` git-ignored.
