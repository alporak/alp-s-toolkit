# Phase 9: Read-Through Cache Integration — Context

**Gathered:** 2026-07-13
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous smart-discuss)

<domain>
## Phase Boundary

Wire the Jira Tracker's read path through the local SQLite store: serve cached
worklogs when fresh (TTL), fetch from Jira only on miss/expiry, and on Jira failure
serve the last persisted copy with a `stale` flag instead of erroring or returning
empty. Writes invalidate only the affected `(account_id, week)` — never a global clear.

Depends on Phase 8 (store + event-loop offload exist).
</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
- Read-through lives in `jira_tracker.py` (route layer) using `jira_store` primitives
  (no circular import): `_load_weekly(account_id, d_from, d_to, display_name, force)`.
- TTL from existing `cache_ttl_minutes` config. On miss/expiry: fetch → persist (via
  `_fetch_worklogs_for_user`, already persists) → return. On fetch failure: return
  stored rows with `stale: true`; if nothing stored, propagate the error (Pitfall 9:
  never cache a failed fetch as empty).
- In-flight guard (`_inflight` dict) prevents duplicate concurrent fetches for the same
  `(account_id, week)` (Pattern 4).
- Writes (`POST/PUT/DELETE /worklog`, `/meeting`) call scoped `mark_stale_week` for the
  affected week of the current user (Pitfall 2/13). In-memory `_cache_clear` retained
  only for the explicit `/cache/clear` endpoint.
- Add `jira_store.get_worklog(account_id, worklog_id)` so deletes can find the week to
  invalidate precisely.
</decisions>

<code_context>
## Existing Code Insights

- `jira_store.get_worklogs`, `set_cache_meta`, `get_cache_meta`, `mark_stale_week`
  (Phase 8).
- `jira_tracker._fetch_worklogs_for_user` already persists + sets cache_meta.
- `_week_range`, `_cache_ttl` (seconds), `_api`, `_jira` helpers.
</code_context>

<specifics>
## Specific Ideas

- Weekly response gains a `stale` boolean field; frontend surfaces it.
</specifics>

<deferred>
## Deferred Ideas

- None — this phase completes the cache foundation.
</deferred>
