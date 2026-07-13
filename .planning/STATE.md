---
gsd_state_version: 1.0
milestone: M4
milestone_name: Jira Tracker Rework
status: planning
last_updated: "2026-07-13T11:09:28.344Z"
last_activity: 2026-07-13
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Current Milestone

**M3: Documentation Search Engine** (ACTIVE — planning)

A FastAPI plugin for full-text search across 3 internal documentation repos (~3000 files). SQLite FTS5 search index with content-less tables, 6-format text extraction, git sync with incremental updates, and a Vanilla JS SPA frontend.

## Previous Milestones

### M1: Core Plugin (COMPLETE)

- **Phase 1** — Backend: SQLite, Jira sync, state machine, stats/sync/chart API
- **Phase 2** — Frontend: bar chart, sync button, status display

### M2: Performance Analytics v2 (COMPLETE)

- **Phase 3** — Backend: extended schema (8-col transitions + tickets), 8 endpoints, attribution tracking
- **Phase 4** — Frontend: tabbed power-dashboard, summary cards, per-ticket table, multi-chart views

## Key Decisions

### Inherited from M1/M2

- Plugin autodiscovery: `app/plugins/` → module-level `plugin` attribute
- SQLite: WAL mode, per-plugin database files
- Frontend: Vanilla JS + `core.js` helpers (`h()`, `api()`, `registerPlugin()`)
- Async: `asyncio.create_task()` for background work, polling for progress
- HTTP: `httpx` async client

### M3-Specific

- Search backend: SQLite FTS5 (not Whoosh) — already in stack, content-less tables supported
- Git operations: `subprocess.run(["git", "pull"])` via `asyncio.to_thread()` (not GitPython)
- PDF extraction: pdfplumber primary, pypdf fallback
- Legacy .doc: doc2txt primary (bundled antiword for Windows)
- Encoding detection: charset-normalizer on all extracted text
- Config: `toolkit_settings.json` for repo paths (follows existing config patterns)
- Phase ordering: Extraction+Index → Sync+Search → Frontend (strictly sequential)
- Plugin: id="doc_search", name="Doc Search", order=50

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `app/plugins/doc_search.py` | 179 | Plugin lifecycle, FTS5 schema, status endpoint (Phase 6 adds sync/search) |
| `app/plugins/doc_extraction.py` | 391 | Text extraction: format dispatch for 6 file types (complete) |
| `tests/test_doc_extraction.py` | 280 | Unit tests: 26 functions covering all extractors, dispatch, failure modes |
| `app/static/js/doc_search.js` | ~300 | Frontend: search SPA with debounce, filters, keyboard nav |
| `app/static/js/app.js` | +1 | `import "./doc_search.js"` |

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-07-13 — Milestone M4 started

## Accumulated Context

### Open Decisions

- DrawIO/GraphML extraction quality on real fixture files — spike needed during Phase 5
- Scanned PDF percentage in target repos — determine real exclusion rate during Phase 5
- charset-normalizer necessity — may be optional safety net if all docs are UTF-8

### Known Risks

- Blocking the FastAPI event loop (#1 integration pitfall) — mitigated by `asyncio.to_thread()` + ThreadPoolExecutor
- Silent PDF extraction failures on scanned docs — mitigated by `needs_ocr` detection
- Legacy .doc encoding corruption (Windows-1257 Baltic) — mitigated by charset-normalizer

### Blockers

- None

### TODOs

- [x] ~~Phase 5: Plan extraction pipeline + FTS5 schema~~
- [x] Phase 5 Plan 01: Extraction pipeline complete
- [x] Phase 5 Plan 02: FTS5 schema & plugin foundation complete
- [x] Phase 6: Plan sync engine + search API — 2 plans created (06-01, 06-02)
- [x] Phase 7: Plan frontend SPA — 1 plan created (07-01)

## Session Continuity

- **Last session:** 2026-07-01T10:41:17.808Z
- **Next action:** `/gsd-execute-phase --plan 06-*` (Phase 6: Sync Engine + Search API)
- **Context needed:** Read 06-01-PLAN.md, 06-02-PLAN.md, app/plugins/doc_search.py, app/plugins/doc_extraction.py

---

*Last updated: 2026-07-01 | Phase 6 Planned — 2 plans ready for execution*

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 06-sync-engine-search-api P01 | 14m | 2 tasks | 3 files |
| Phase 06-sync-engine-search-api P02 | 12m | 2 tasks | 2 files |

## Decisions

- [Phase ?]: FTS5 content-less pattern: standalone FTS5 table (removed content doc_metadata) for DELETE INSERT upsert
- [Phase ?]: Git subprocess: argument-list form via asyncio.to_thread, timeout=120s
- [Phase ?]: Thread pool sizing: max_workers=4 for parallel extraction
- [Phase ?]: Single-file plugin (~826 lines) covering all 3 tasks — practical consolidation since all tasks modify same file
- [Phase ?]: Frontend-side term highlighting: regex splitting + document.createElement('mark') since backend strips FTS5 snippet markers
- [Phase ?]: Filter chips toggle visibility via CSS display:none for instant re-filtering without re-rendering
- [Phase ?]: Only one preview accordion open at a time — clicking different closes old, clicking same toggles

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
