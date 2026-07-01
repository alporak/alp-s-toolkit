---
gsd_state_version: 1.0
milestone: M3
milestone_name: Documentation Search Engine
status: planning
last_updated: "2026-07-01T00:00:00.000Z"
last_activity: 2026-07-01
progress:
  total_phases: 3
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
| `app/plugins/doc_search.py` | ~400 | Backend: plugin lifecycle, sync orchestration, search API |
| `app/plugins/doc_extraction.py` | ~150 | Text extraction: format dispatch for 6 file types |
| `app/static/js/doc_search.js` | ~300 | Frontend: search SPA with debounce, filters, keyboard nav |
| `app/static/js/app.js` | +1 | `import "./doc_search.js"` |

## Current Position

**Phase:** 5 — Extraction & Index Foundation
**Plan:** TBD
**Status:** Roadmap defined, awaiting plan
**Last activity:** 2026-07-01 — ROADMAP.md created for M3

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
- [ ] Phase 5: Plan extraction pipeline + FTS5 schema
- [ ] Phase 6: Plan sync engine + search API
- [ ] Phase 7: Plan frontend SPA

## Session Continuity

- **Last session:** 2026-07-01 — Roadmap creation
- **Next action:** `/gsd-plan-phase 5`
- **Context needed:** Read ROADMAP.md Phase 5 section, research/SUMMARY.md Phase 5 research flags

---

*Last updated: 2026-07-01 | M3 Roadmap Created*
