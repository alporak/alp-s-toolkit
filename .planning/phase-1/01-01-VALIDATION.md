# Phase 1: Validation Plan

**Plan:** 01-01-PLAN.md
**Date:** 2026-06-17

## Validation Scope

Phase 1 is the backend plugin only (no frontend). Validation covers:
1. Plugin auto-discovery
2. SQLite database initialization
3. Jira changelog fetching pipeline
4. ATTEMPT/RETURN state machine
5. Three API endpoints (stats, sync, sync/status)
6. Pandas 2Q metric grouping

## Test Suite Map

Tests will be created during execution (Wave 0 per RESEARCH.md recommendations) using pytest at `tests/test_competence.py`:

| Test | Req | Type | What It Validates |
|------|-----|------|-------------------|
| `test_plugin_discovery` | FR1 | unit | Plugin instance auto-discovered by `_discover_plugins()` |
| `test_db_init` | FR2 | unit | SQLite tables created with WAL mode on startup |
| `test_fetch_changelog` | FR3 | integration | httpx client uses correct auth + fetches changelog from Jira |
| `test_state_machine_returns` | FR4 | unit | ATTEMPT/RETURN transition detection from mock changelog items |
| `test_api_stats` | FR5 | integration | GET /api/competence/stats returns valid JSON structure |
| `test_pandas_2q_grouping` | FR6 | unit | Grouper(freq='2Q') produces correct aggregates |

## Manual Verification Checklist

In addition to automated tests, verify:

1. [ ] Plugin appears in `GET /api/plugins` with correct id/name/icon/order
2. [ ] `GET /api/competence/stats` returns `[]` when DB is empty
3. [ ] `POST /api/competence/sync` returns `{"status": "sync_started"}` immediately
4. [ ] `GET /api/competence/sync/status` shows `in_progress: true` during sync
5. [ ] After sync: stats endpoint shows 2Q periods with non-zero data
6. [ ] Plugin does not crash when `jira_config.json` is missing (returns graceful empty stats)
7. [ ] Second sync is incremental (only fetches issues updated since last_sync)
8. [ ] `competence_cache.db` file exists in `app/plugins/` after startup

## Nyquist Gate

These verifications must pass before Phase 1 is considered complete:
- All 6 automated tests pass
- All 8 manual checks pass
- Plugin code follows `release_creator.py` conventions (verified via code review)
