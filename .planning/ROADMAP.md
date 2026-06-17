# Roadmap — Competence & Performance Plugin

## Overview
Two-phase delivery: backend plugin (Phase 1) then frontend UI (Phase 2).

---

## Phase 1: Backend Plugin — Competence Engine
**Goal**: Working `competence.py` plugin with SQLite cache, Jira sync, and stats API.

**Requirements**: [FR1, FR2, FR3, FR4, FR5, FR6, NFR1, NFR2, NFR3, NFR4, NFR5]

**Plans**: 1 plan (8 waves)

Plans:
- [ ] 01-01-PLAN.md — Full plugin: skeleton → SQLite → auth → state machine → sync → stats → endpoints → verification (8 waves)

**Exit criteria**:
- Plugin auto-discovered and listed in `GET /api/plugins`
- All three endpoints respond correctly
- Sync populates SQLite with transitions
- Stats endpoint returns correctly grouped 2Q periods
- Plugin works without crashing when Jira config is unset

---

## Phase 2: Frontend Dashboard
**Goal**: Chart UI showing bug return rate over time.

**Tasks**:
1. Create `app/static/js/competence.js`:
   - Register route handler in core SPA router
   - Fetch stats from `/api/competence/stats`
   - Render chart using Plotly (already available in project)
   - "Sync Now" button calling `POST /api/competence/sync`
   - Show last sync time from `/api/competence/sync/status`
2. Import `competence.js` in `app/static/js/app.js`
3. Add page template section to `app/static/index.html`

**Exit criteria**:
- Dashboard visible in sidebar at correct position
- Chart renders with period labels on x-axis, return rate on y-axis
- Sync button triggers sync and shows status
- Responsive layout matching existing plugin pages

---

## Phase Dependency Graph
```
Phase 1 (Backend) ──► Phase 2 (Frontend)
```
Phase 2 depends on Phase 1 API being functional.

---

## Timeline Estimate
| Phase | Estimate |
|-------|----------|
| Phase 1 | 1 session |
| Phase 2 | 1 session |
