# Alps Toolkit

## Overview
A FastAPI-based toolkit with plugin auto-discovery (`app/plugins/`). Plugins extend `ToolkitPlugin` base class and provide API routes + frontend SPAs. Ships with Competence & Performance analytics and Documentation Search Engine plugins.

## Use Case
Internal developer tooling — Jira analytics dashboards, documentation search across internal repos, log parsing, GPS simulation, release management.

## Milestone History

### M1: Core Competence Plugin (COMPLETE — Phase 1 + 2)
- Phase 1: Backend — SQLite, Jira sync, state machine, stats API
- Phase 2: Frontend — SPA plugin with bar chart, sync button

### M2: Performance Analytics v2 (COMPLETE — Phase 3 + 4)
- Phase 3: Backend — extended schema, attribution tracking, 8 endpoints
- Phase 4: Frontend — tabbed power-dashboard, per-ticket table, multi-chart views

### M3: Documentation Search Engine (COMPLETE — Phase 5 + 6 + 7)
- Phase 5: Extraction pipeline — 6 formats (docx/pdf/doc/rst/drawio/graphml), FTS5 schema, charset detection, SHA-256 fingerprinting
- Phase 6: Sync engine — git pull from 3 repos, incremental index updates, BM25 search API, preview endpoint, path traversal protection
- Phase 7: Frontend SPA — search-as-you-type, formatted HTML preview, file-type filters, keyboard nav, sync progress bar, repo settings UI, native "Open file" via os.startfile()
- **Artifacts**: `app/plugins/doc_extraction.py` (484 lines), `app/plugins/doc_search.py` (926 lines), `app/static/js/doc_search.js` (1106 lines), `tests/test_doc_extraction.py` (280 lines)

## Current Milestone: M4 — Jira Tracker Rework

**Goal:** Make the Jira Tracker instant and insight-rich — SQLite-backed local persistence, a redesigned tabbed UI with a persistent sidebar and pinned insights (seamless transitions, no re-fetch on tab switch), in-app + browser notifications, and power-user tools for spotting missed hours and under-target weeks.

**Target features:**
- **Local persistence** — Replace the per-process in-memory worklog cache with a SQLite store (per-plugin DB, WAL) that survives restarts, with smart refresh / TTL / force-refresh.
- **UI redesign** — Persistent sidebar, tab state kept alive (no API call on every tab open), instant transitions, a shared in-memory store across tabs.
- **Notifications** — New Insights tab + toggleable browser notifications + tab-bar badge when gaps (missed days / short weeks) are detected.
- **Insights engine** — Detect days with no/missing hours and weeks below target; 40h default weekly target with configurable non-working-day marking that recalculates the target (e.g. 40h → 32h for a 4-day week / holidays).
- **Gap-fill tools** — Quick actions to log hours for missed days and top up short weeks.

## Current State (post-M3, starting M4)

Shipped M3 with ~2,800 lines of new code across 4 files. Working plugin serving ~1,100 indexed documents across 3 repos. Jira Tracker plugin (M1-era) is functional but has known friction: per-process in-memory cache lost on restart, every tab open triggers a full re-render + Jira API calls, and no insight into missed/under-target logging. M4 reworks it.

## Tech Stack
- **Backend**: FastAPI plugin (ToolkitPlugin base class)
- **Database**: SQLite FTS5 — content-less mode, WAL, per-plugin DB files, auto-migration
- **HTTP**: `httpx` async, `subprocess` for git operations
- **Search**: SQLite FTS5 with BM25 ranking, `snippet()` highlighting
- **Text extraction**: python-docx, pdfplumber (primary) + pypdf (fallback), doc2txt, docutils, xml.etree
- **Encoding**: charset-normalizer for Baltic-locale legacy documents
- **Frontend**: Vanilla JS SPA using core.js (h(), api(), registerPlugin()), no frameworks/no npm
- **File serving**: os.startfile() for native app opening, FileResponse with MIME types

## Key Decisions
- Content-less FTS5 over Whoosh (zero deps, already in stack, 3:1 research consensus)
- Batch extraction (100-file chunks, 2 workers) to prevent OOM on large PDF repos
- All DB writes through `asyncio.to_thread()` — event-loop SQLite access corrupts on Windows
- Formatted HTML preview via `docx_to_html()` converter preserving paragraphs/bold/italics/tables
- `os.startfile()` for "Open file" — launches native Windows app instead of browser download
- `_ensure_schema()` called at sync start — handles auto-recovered DB after corruption
- Schema auto-migration: `ALTER TABLE` on version bump, WAL mode, `UNIQUE(repo, path)`

## Key Constraints
1. Plugins auto-discovered from `app/plugins/` — module-level `plugin` attribute
2. Plugin lifecycle: `register_routes()` → `startup()` → `shutdown()`
3. No auth required (internal network tool)
4. Git repos must be accessible from company network
5. All blocking I/O via `asyncio.to_thread()` — never on event loop (Windows SQLite safety)

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-07-02 | Milestone M3 complete*
