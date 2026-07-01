# Alps Toolkit

## Overview
A FastAPI-based toolkit with plugin auto-discovery (`app/plugins/`). Plugins extend `ToolkitPlugin` base class and provide API routes + frontend SPAs. Currently hosts the Competence & Performance plugin.

## Use Case
Internal developer tooling — Jira analytics dashboards, log parsing, GPS simulation, release management, and now documentation search.

## Milestone History

### M1: Core Plugin (COMPLETE — Phase 1 + 2)
- **Phase 1**: Backend — SQLite cache, Jira changelog sync via `jira` package + httpx, ATTEMPT/RETURN state machine, stats/chart/sync/status API endpoints
- **Phase 2**: Frontend — SPA plugin with bar chart (server-side Plotly HTML → iframe), sync button, status polling
- **Artifacts**: `app/plugins/competence.py` (593 lines), `app/static/js/competence.js` (107 lines)

### M2: Performance Analytics v2 (COMPLETE — Phase 3 + 4)
- **Phase 3**: Backend — extended schema (8-col transitions + tickets), enhanced parsing with attribution, ticket metadata, 4 new API endpoints
- **Phase 4**: Frontend — tabbed power-dashboard (Overview / Per Ticket / Charts), summary cards, sortable per-ticket table with expandable timeline, multi-chart views
- **Artifacts**: `app/plugins/competence.py` (478 lines), `app/static/js/competence.js` (240 lines)

## Current Milestone: M3 — Documentation Search Engine

**Goal:** A unified, fast full-text search plugin across 3 internal documentation repos (~3000 files) — git pull, text extraction, search index, inline preview.

**Target features:**
- Git sync of 3 documentation repos (daily + on startup + manual button)
- Text extraction from .docx, .pdf, .doc, .rst, .drawio, .graphml, and other formats
- Fast full-text search index (unified across all repos)
- Search UI: real-time results with match snippets
- Inline file preview with search term highlighting
- Follows competence plugin conventions

## Tech Stack
- **Backend**: FastAPI plugin (ToolkitPlugin base class)
- **Database**: SQLite — WAL mode, per-plugin database files
- **HTTP**: `httpx` async
- **Frontend**: Vanilla JS SPA using core.js framework (h(), api(), registerPlugin())
- **Search**: Whoosh or SQLite FTS5 (to be decided in research)
- **Text extraction**: python-docx, PyPDF2/pdfplumber, python-pptx, doc2txt

## Key Constraints
1. Plugins auto-discovered from `app/plugins/` — module-level `plugin` attribute
2. Plugin lifecycle: `register_routes()` → `startup()` → `shutdown()`
3. No auth required (internal network tool)
4. Git repos must be accessible from company network
5. Search must handle legacy .doc (pre-2007) formats

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-07-01 | Milestone M3 started*
