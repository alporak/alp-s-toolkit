# Phase 8: SQLite Persistence Foundation — Context

**Gathered:** 2026-07-13
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous smart-discuss)

<domain>
## Phase Boundary

Establish the local persistence layer for the Jira Tracker. Worklogs and assigned
tickets are mirrored into a local SQLite store that survives process restarts. All
blocking Jira/SQLite I/O is moved off the event loop via `asyncio.to_thread()`. Worklog
dates are stored timezone-correct (local `date_local`) so week-boundary math is correct.

This phase is the foundation; the read-through read path (TTL, stale-serve, scoped
invalidation) is delivered in Phase 9. Here we create the store module, its schema, and
persist data on fetch, while keeping existing route behavior working.
</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices at Claude's discretion, guided by PROJECT.md, research
(STACK/ARCHITECTURE/PITFALLS), and the `doc_search.py` DB convention.

- New module `app/plugins/jira_store.py` mirrors `doc_search.py`: co-located
  `jira_tracker.db`, `PRAGMA journal_mode=WAL`, `row_factory=Row`, `_db_lock`
  (`threading.Lock()`), `_ensure_schema()` at startup, all writes under lock, all DB
  access via `asyncio.to_thread()`.
- Schema: `worklogs` (PK `account_id, id`), `assigned_tickets` (PK `key`),
  `cache_meta` (`account_id, week_start`), `non_working_days` (`date`), plus
  `schema_meta` for `SCHEMA_VERSION`.
- Blocking Jira calls (`_api`, `_jira().search_issues`) wrapped in `asyncio.to_thread()`
  in the routes (Pitfall 3). JIRA client serialized via a creation lock.
- `date_local` computed offset-aware from `started`, converted to `LOCAL_TZ`
  (default `Europe/Vilnius`, fallback machine local), stored explicitly.
- `_fetch_worklogs_for_user` persists fetched rows into the store (PERS-01/02/06) so data
  survives restarts; the read path itself is added in Phase 9.
</decisions>

<code_context>
## Existing Code Insights

- `app/plugins/doc_search.py` — reference SQLite pattern (lines 38–170+).
- `app/plugins/jira_tracker.py` — existing sync `requests`/`jira` calls in `async def`
  routes; `_fetch_worklogs_for_user` returns dicts with `id, ticket_key, ticket_summary,
  date, started, time_spent_seconds, comment`.
- `app/plugins/base.py` — `startup()` lifecycle hook.
- `app/config.py` — `load_jira_config()` / `save_jira_config()`.
</code_context>

<specifics>
## Specific Ideas

- Store is a read-only mirror of Jira; only `non_working_days` is locally authored.
- `jira_tracker.db` + `-wal`/`-shm` must be git-ignored.
</specifics>

<deferred>
## Deferred Ideas

- Read-through read path, TTL, stale-serve, scoped invalidation → Phase 9.
- Insights computation → Phase 11.
</deferred>
