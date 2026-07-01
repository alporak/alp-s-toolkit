---
phase: 06-sync-engine-search-api
plan: 02
subsystem: doc_search
tags: [search-api, sync-api, fts5, tdd, integration-tests]
requires:
  - "06-01"
provides:
  - "GET /api/doc_search/search"
  - "GET /api/doc_search/preview/{repo}/{path:path}"
  - "GET /api/doc_search/repos"
  - "POST /api/doc_search/sync"
  - "GET /api/doc_search/sync/status"
  - "startup background sync"
affects:
  - "Phase 7 frontend SPA (consumes all 5 endpoints)"
tech-stack:
  added: []
  patterns: [TDD, FTS5 bm25+snippet, asyncio.create_task, asyncio.to_thread, os.path.realpath]
key-files:
  created: []
  modified:
    - app/plugins/doc_search.py (5 endpoints + _sanitize_html + startup background sync)
    - tests/test_doc_search.py (integration tests: 13 new, 49 total)
decisions:
  - "snippet() column index: 0-based for single-column FTS5 table (plan had 1)"
  - "path traversal test: use percent-encoded %2e%2e/ to bypass FastAPI URL normalization"
  - "sync lock testing: mock asyncio.Lock.locked() instead of real acquisition (event-loop mismatch)"
  - "XSS: strip HTML tags but preserve inner text — frontend renders via textContent"
  - "last_sync timestamp returned per-repo from sync_state; isoformat UTC"
metrics:
  duration: ""
  completed_date: "2026-07-01"
---

# Phase 06 Plan 02: Search API & Routes — Summary

**One-liner:** Added 5 API endpoints (search, preview, repos, sync trigger, sync status) plus startup background sync with XSS sanitization and path-traversal protection — all TDD with 49 integration tests passing.

## Plan Execution Summary

Executed both tasks using strict TDD (RED → GREEN) with no REFACTOR needed.

### Task 1: Search, Preview, and Repos API Endpoints

Added three new read endpoints to `DocSearchPlugin.register_routes()`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/doc_search/search?q=` | GET | FTS5 BM25-ranked search with `<mark>` snippets, max 50 results |
| `/api/doc_search/preview/{repo}/{path}` | GET | Returns first 2000 chars of extracted text with path-traversal protection |
| `/api/doc_search/repos` | GET | Lists configured repos with file counts and last-synced timestamps |

Also added `_sanitize_html()` helper using `re.sub(r"<[^>]*>", "", text)` to strip HTML tags from snippets before JSON serialization (XSS mitigation per NFR-13).

**Path traversal protection:** Uses `os.path.realpath()` to resolve the full path, then verifies `resolved.startswith(real_root + os.sep)`. Returns 403 on violation. FastAPI normalizes literal `../` before routing, but encoded `%2e%2e/` bypasses this — caught by realpath check.

**Tests added (13):** TestSearchEndpoint (6), TestPreviewEndpoint (4), TestReposEndpoint (2), TestXssSanitization (1)

### Task 2: Sync API Endpoints + Startup Background Sync

Added two write endpoints and enhanced `startup()`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/doc_search/sync` | POST | Triggers `asyncio.create_task(_sync_job())`, returns `sync_started` or `sync_already_running` |
| `/api/doc_search/sync/status` | GET | Returns `{in_progress, progress: {phase, repo, done, total}, last_sync}` for polling |

**startup() enhancement:** After schema init, fires `loop.create_task(_sync_job())` so the UI loads immediately with "Indexing..." status. Wrapped in try/except RuntimeError for defensive event-loop handling.

**Tests added (7):** TestSyncTriggerEndpoint (2), TestSyncStatusEndpoint (3), TestStartupBackgroundSync (2)

### Test Results

```
49 passed in 2.52s — zero failures, zero regressions
```

### Commit History

```
3a07ca3 feat(06-sync-engine-search-api): add sync trigger, status endpoints + startup background sync
656ea66 test(06-sync-engine-search-api): RED - failing integration tests for sync trigger, status, startup
3b46fd5 feat(06-sync-engine-search-api): add search, preview, repos API + XSS sanitization
4df260e test(06-sync-engine-search-api): RED - failing integration tests for search, preview, repos API endpoints
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed FTS5 snippet() column index from 1 to 0**
- **Found during:** Task 1 GREEN
- **Issue:** Plan specified `snippet(doc_search_fts, 1, ...)` but FTS5 uses 0-based column indexing. Single-column table only has column 0.
- **Fix:** Changed to `snippet(doc_search_fts, 0, ...)`
- **Files modified:** `app/plugins/doc_search.py` line 540
- **Commit:** 3b46fd5

**2. [Rule 3 - Blocking] FastAPI normalizes literal `..` in URL paths before routing**
- **Found during:** Task 1 GREEN (path traversal test)
- **Issue:** Literal `../` in URL path `/preview/TestRepo/../../../etc/passwd` was normalized by FastAPI before reaching the handler, making it unreachable
- **Fix:** Updated test to use percent-encoded `%2e%2e/` which bypasses URL normalization and correctly triggers `os.path.realpath()` check
- **Files modified:** `tests/test_doc_search.py`
- **Commit:** 3b46fd5

**3. [Rule 3 - Blocking] asyncio.Lock tied to event loop — test lock acquisition in separate event loop didn't work**
- **Found during:** Task 2 GREEN (status test)
- **Issue:** `asyncio.Lock` acquired via `asyncio.run()` in a test is tied to that event loop, not the TestClient's portal loop
- **Fix:** Mocked `_sync_lock.locked()` with `patch.object(_sync_lock, "locked", return_value=True)` for tests that verify in-progress state
- **Files modified:** `tests/test_doc_search.py`
- **Commit:** 3a07ca3

**4. [Rule 3 - Blocking] Variable shadowing in test — fixture function name vs value**
- **Found during:** Task 2 GREEN
- **Issue:** Test referenced `integration_db` (fixture function) instead of accepting it as a parameter
- **Fix:** Added `integration_db` to test method signature
- **Files modified:** `tests/test_doc_search.py`
- **Commit:** 3a07ca3

### Auth Gates

None — internal toolkit with no authentication layer.

## Requirements Satisfied

| Requirement | Status | Verified By |
|-------------|--------|-------------|
| SYNC-01 | Done | `test_sync_trigger_starts_background_job` — POST /sync returns sync_started |
| SYNC-02 | Done | `test_status_returns_correct_shape` — GET /status returns correct polling shape |
| SYNC-05 | Done | `test_startup_fires_background_sync` + `test_startup_does_not_block` |
| SRCH-01 | Done | `test_search_returns_bm25_results` + `test_search_limits_to_50` |
| SRCH-02 | Done | `test_search_returns_bm25_results` verifies full result shape |
| SRCH-03 | Done | `test_preview_path_traversal_returns_403` + `test_preview_returns_text` |
| SRCH-04 | Done | `test_repos_returns_configured_repos_with_counts` |
| SRCH-05 | Done | `test_empty_query_returns_empty_gracefully` |
| NFR-13 | Done | Path traversal protection via `os.path.realpath()` — verified in test |
| NFR-14 | Done | XSS HTML stripping via `_sanitize_html()` — verified in test |

## Threat Flags

None — all threats in the plan's threat model are addressed:
- T-06-05 (query injection): accept — FTS5 MATCH is safe
- T-06-06 (path traversal): mitigated — os.path.realpath() check
- T-06-07 (XSS): mitigated — _sanitize_html() strips tags
- T-06-08 (DoS wildcard): accept — limited to 50 results
- T-06-09 (no auth): accept — internal toolkit

## Known Stubs

None — all endpoints are fully functional with DB-backed data flow.

## Self-Check

Will be verified after file creation.
