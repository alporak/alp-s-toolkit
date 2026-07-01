---
phase: 05-extraction-index-foundation
plan: "02"
subsystem: doc-search
tags: [plugin, fts5, sqlite, search-index, schema, tests]
requires:
  - 05-01 (doc_extraction.py)
provides:
  - app/plugins/doc_search.py
  - tests/test_doc_extraction.py
  - doc_search.db schema foundation
affects:
  - main.py (plugin auto-discovery — no code changes needed)
tech-stack:
  added: [pytest]
  patterns: [ToolkitPlugin subclass, sync_state schema versioning, WAL journal mode,
    FTS5 content-less virtual tables, module-level plugin singleton]
key-files:
  created:
    - app/plugins/doc_search.py
    - tests/__init__.py
    - tests/test_doc_extraction.py
  modified:
    - .gitignore (added app/plugins/*.db rule)
key-decisions:
  - FTS5 content-less mode (content='doc_metadata', content_rowid='id') — inverted index only,
    full text read from doc_metadata; avoids duplicate storage
  - Schema versioning via sync_state table following competence.py pattern exactly —
    re-running startup() detects existing version and skips migration
  - Plugin order 46 (after CompetencePlugin at 45) — places Doc Search in nav correctly
  - DB path co-located with plugin code (app/plugins/doc_search.db) — same pattern as competence_cache.db
  - Status endpoint synchronous (no asyncio.to_thread) — single key lookup is lightweight
metrics:
  duration_secs: 373
  tasks_completed: 2
  files_created: 3
  test_count: 26
  tests_passed: 25
  tests_skipped: 1
  completed_date: "2026-07-01T09:14:26Z"
---

# Phase 5 Plan 2: FTS5 Schema & Unit Tests Summary

**One-liner:** DocSearchPlugin with FTS5 content-less schema, auto-migration, and /api/doc_search/status endpoint — plus 25 passing unit tests for the extraction pipeline.

## What was built

### Task 1: DocSearchPlugin (`app/plugins/doc_search.py`, 179 lines)

Created `DocSearchPlugin` following the exact `competence.py` pattern:
- **Class:** Extends `ToolkitPlugin` with `id="doc_search"`, `name="Documentation Search"`, `icon="🔍"`, `order=46`
- **DB helpers:** `_get_db()`, `_db_get(key)`, `_db_set(key, value)` — identical signatures to competence.py
- **Schema:** `doc_metadata` table with 8 columns (id, repo, relative_path, full_text, sha256, encoding, needs_ocr, last_extracted) and `UNIQUE(repo, relative_path)`
- **FTS5:** `doc_search_fts` virtual table using content-less mode (`content='doc_metadata'`, `content_rowid='id'`, `tokenize='unicode61'`)
- **Indexes:** `idx_doc_metadata_sha256` and `idx_doc_metadata_repo`
- **Migration:** `startup()` checks `sync_state.schema_version` — skips DDL if version matches `"1"`, executes full schema if first run
- **Status endpoint:** `GET /api/doc_search/status` returns `{"status":"ok","schema_version":"1"}`
- **DB file:** Created at `app/plugins/doc_search.db` with WAL journal mode
- **Singleton:** Module-level `plugin = DocSearchPlugin()` for auto-discovery by `main.py`

### Task 2: Unit Test Suite (`tests/__init__.py`, `tests/test_doc_extraction.py`, 411 lines)

Comprehensive test coverage of the extraction module (Plan 05-01):
- **26 test functions** across 15 categories
- **6 extractors tested:** docx (programmatic fixture), pdf (blank + skipped text), doc (skip), rst (fixture), drawio (fixture), graphml (fixture)
- **Dispatch table:** Verified 6 entries with correct lowercase dot-prefixed keys and callable values
- **SHA-256:** Known file, nonexistent file, same-file consistency, different-file differentiation, 64-char lowercase hex format
- **Encoding detection:** ASCII → utf_8/ascii, UTF-8 non-ASCII → utf_8, empty → utf_8 fallback
- **extract_text:** Dict shape (5 keys), dispatch routing, unsupported format error, nonexistent file handling
- **Failure handling:** Corrupt .docx (garbage bytes), non-PDF .pdf, corrupt .docx via extract_text — all return gracefully
- **Scanned PDF:** Blank PDF (pages>0, no text) flags `needs_ocr=True`
- **Results:** 25 passed, 1 skipped (text PDF needs reportlab — documented)

## Verification Results

### Plugin import and manifest
```
✅ Plugin class imports without errors
✅ plugin.id == 'doc_search'
✅ plugin.name == 'Documentation Search'
✅ plugin.order == 46
✅ plugin.icon == '🔍'
✅ SCHEMA_VERSION == '1'
✅ DB_PATH resolves to app/plugins/doc_search.db
✅ isinstance(plugin, ToolkitPlugin) → True
```

### Database schema
```
✅ doc_metadata table: 8 columns (id, repo, relative_path, full_text, sha256, encoding, needs_ocr, last_extracted)
✅ doc_search_fts virtual table: content='doc_metadata', content_rowid='id', tokenize='unicode61'
✅ sync_state table with schema_version='1'
✅ WAL journal mode confirmed
✅ UNIQUE(repo, relative_path) constraint active
```

### Status endpoint
```
✅ startup() creates DB and tables without errors
✅ _db_get('schema_version') returns '1'
✅ Re-running startup() skips migration (version already current)
```

### Test suite
```
✅ 25 passed, 1 skipped, 0 failed
✅ All extractors produce expected output
✅ Dispatch table routes correctly
✅ SHA-256 consistency verified
✅ Scanned PDF detection works
✅ Failure modes handled gracefully (no crashes)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical infrastructure] Added `app/plugins/*.db` to `.gitignore`**
- **Found during:** Task 1 verification (DB file created during testing)
- **Issue:** Generated runtime SQLite databases (`doc_search.db`, `competence_cache.db`) were not gitignored — risk of accidentally committing binary DB files
- **Fix:** Added `app/plugins/*.db` pattern to `.gitignore`
- **Files modified:** `.gitignore`
- **Commit:** `069dfe0`

**2. [Rule 3 - Missing dependency] Installed `pytest`**
- **Found during:** Task 2 setup
- **Issue:** `pytest` was not installed in the environment — required to run unit tests
- **Fix:** `pip install pytest`
- **Files modified:** None (dependency only)

## TDD Gate Compliance

This plan is type `execute`, not `tdd` — TDD gate does not apply. Tests were written after the extraction module (05-01) was already implemented.

## Threat Flags

None — all threat model mitigations from the plan were implemented:
- T-05-04 (DoS): DDL execution wrapped in try/except — startup failure doesn't crash plugin
- T-05-05 (Info Disclosure): Status endpoint returns only status + schema_version
- T-05-07 (Tampering): FTS5 content-less mode prevents direct content injection

## Known Stubs

None — all planned functionality was implemented. The plugin is a skeleton by design (extraction and search logic deferred to Phase 6 per the plan's scope).

## Completed Requirements

- [x] **INDEX-01**: FTS5 content-less virtual table with `content='doc_metadata'`, `content_rowid='id'`
- [x] **INDEX-02**: `doc_metadata` table with all required columns + UNIQUE(repo, relative_path)
- [x] **INDEX-03**: `sha256` column present for incremental update fingerprinting (Phase 6 uses this)
- [x] **INDEX-04**: `doc_search.db` persisted to disk with WAL journal mode
- [x] **INDEX-05**: Schema versioning via sync_state table with auto-migration on startup

## Commits

| Hash | Message |
|------|---------|
| `069dfe0` | feat(05-02): create DocSearchPlugin with FTS5 schema, auto-migration, and /api/doc_search/status endpoint |
| `f37e3ca` | test(05-02): add unit test suite for doc_extraction — 6 extractors, dispatch, encoding, SHA-256, scanned PDF |
