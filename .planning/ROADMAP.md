# Roadmap — Performance Analytics v2

## Overview
M2 expands the Competence & Performance Plugin into a power-user analytics dashboard. Two phases: backend data model + API enhancements (Phase 3), then frontend power-dashboard (Phase 4).

---

## Phase 1: Backend Plugin (COMPLETE)
SQLite cache, Jira sync, state machine, stats/sync/status/chart API.

## Phase 2: Frontend Dashboard (COMPLETE)
SPA plugin with bar chart, sync button, status display.

---

## Phase 3: Backend Enhancements — Extended Data Model & APIs
**Goal**: Capture per-transition attribution (who returned, statuses involved), add ticket metadata, expose richer API endpoints.

**Files**: `app/plugins/competence.py`

**Plans:** 1 plan (9 task waves)

Plans:
- [ ] `phase-3/PLAN.md` — Full rewrite: extended schema, enhanced parser, ticket metadata sync, 4 new API endpoints + 4 M1 endpoints preserved

**Exit criteria**:
- Schema migration runs on startup without data loss
- Tickets endpoint returns correct per-ticket stats with attribution
- Ticket detail shows full transition timeline with authors and statuses
- Volume chart renders attempts + returns per period
- Summary endpoint returns correct aggregates
- Existing M1 endpoints unchanged

---

## Phase 4: Frontend Power-Dashboard
**Goal**: Tabbed power-user dashboard with overview cards, per-ticket table with expandable detail, multi-chart views.

**Files**: `app/static/js/competence.js`, `app/static/js/core.js` (if new icons needed)

**Tasks**:
1. Replace flat layout with tabbed layout (`createTabs()`: Overview / Per Ticket / Charts)
2. Overview tab: 4 summary cards (from `/summary`) + return rate chart + volume chart
3. Per-Ticket tab: sortable table (from `/tickets`), click row → expand transition timeline panel
4. Charts tab: full-width rate + volume charts with period context
5. Sync button triggers full refresh of all tabs after completion
6. Integration test: all tabs render, data flows end-to-end

**Exit criteria**:
- All three tabs render correctly
- Summary cards show live data from API
- Per-ticket table sortable, expandable with timeline
- Charts tab shows multi-metric views
- Sync updates all tabs automatically
- Zero console errors

---

## Phase Dependency Graph
```
Phase 3 (Backend Extensions) ──► Phase 4 (Frontend Power-Dashboard)
```
Phase 4 depends on Phase 3's new API endpoints.

---

## Timeline Estimate
| Phase | Estimate |
|-------|----------|
| Phase 3 | 1 session |
| Phase 4 | 1 session |
