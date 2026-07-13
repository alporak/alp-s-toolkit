---
gsd_state_version: 1.0
milestone: M4
milestone_name: Jira Tracker Rework
status: planning
last_updated: "2026-07-13T12:00:00.000Z"
last_activity: 2026-07-13
progress:
  total_phases: 6
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Current Milestone

**M4: Jira Tracker Rework** (PLANNING — roadmap drafted, 6 phases 8-13)

Goal: Make the Jira Tracker instant and insight-rich — SQLite-backed local persistence, a redesigned tabbed UI with a persistent sidebar and pinned insights (seamless transitions, no re-fetch on tab switch), in-app + browser notifications, and power-user tools for spotting missed hours and under-target weeks, plus a "TeltoHeart" side-project timesheet tracker.

## Previous Milestones

### M1: Core Plugin (COMPLETE)
- **Phase 1** — Backend: SQLite, Jira sync, state machine, stats/sync/chart API
- **Phase 2** — Frontend: bar chart, sync button, status display

### M2: Performance Analytics v2 (COMPLETE)
- **Phase 3** — Backend: extended schema (8-col transitions + tickets), 8 endpoints, attribution tracking
- **Phase 4** — Frontend: tabbed power-dashboard, summary cards, per-ticket table, multi-chart views

### M3: Documentation Search Engine (COMPLETE)
- **Phase 5** — Extraction & Index: 6 formats, FTS5 schema, charset detection
- **Phase 6** — Sync Engine & Search API: git sync, BM25 search, preview, path traversal protection
- **Phase 7** — Frontend SPA: search-as-you-type, HTML preview, filters, keyboard nav, "Open file"

## Key Decisions

### Inherited from prior milestones
- Plugin autodiscovery: `app/plugins/` → module-level `plugin` attribute
- SQLite: WAL mode, per-plugin database files, `_ensure_schema()` at startup
- Frontend: Vanilla JS + `core.js` helpers (`h()`, `api()`, `registerPlugin()`)
- All blocking I/O via `asyncio.to_thread()` behind a lock — never on event loop (Windows SQLite safety)

### M4-Specific (from research)
- New `app/plugins/jira_store.py`: SQLite schema, read-through cache, `compute_insights()`, `non_working_days` CRUD
- `jira_tracker.py` delegates to store; Jira stays authoritative source, DB is read-only mirror except `non_working_days` (local metadata)
- Keep `requests` + `jira` (pin 3.10.5); do NOT migrate to async `httpx` (jira lib has no async API)
- Frontend: persistent sidebar + `this._store` (hot cache) + `localStorage` + `storage` event; tab switching toggles `display` instead of re-fetching
- Notifications: native `Notification` API feature-detected (`"Notification" in window && window.isSecureContext`), degrade to badge + `toast()`
- Weekly target modeled as `daily_target × working_days` so marking non-working days recalculates it

## Files (M4 targets)

| File | Status | Purpose |
|------|--------|---------|
| `app/plugins/jira_store.py` | NEW | SQLite store, read-through cache, insights, non-working-days |
| `app/plugins/jira_tracker.py` | MODIFIED | Delegates to store, scoped invalidation, `/insights` endpoints |
| `app/static/js/jira.js` | MODIFIED | Persistent sidebar + shared store + Insights view + notif toggle |
| `app/static/js/core.js` | MODIFIED (additive) | `setPluginBadge(pluginId, count)` nav hook |

## Current Position

Phase: 8 (next — SQLite Persistence Foundation)
Plan: —
Status: Planning (roadmap drafted, awaiting phase plan)
Last activity: 2026-07-13 — M4 roadmap created (Phases 8-13)

## Accumulated Context

### Open Decisions
- Jira `started` offset (UTC vs reporter TZ): confirm via one live `GET issue/{key}/worklog` in Phase 8; offset-aware `date_local` storage is correct regardless.
- Deployment scheme (HTTPS vs LAN http://): determines if OS notifications fire — Phase 12 feature-detects and degrades to badge+toast regardless.
- Marked-off day with logged hours: adopt "exclude from both sides + warn" interpretation.
- Insights history window: default current week (+ optionally previous week for Monday catch-up).

### Known Risks
- Cache-as-truth divergence: never populate cache from a write payload; invalidate `(account_id, week)` on write and let next read re-fetch.
- Event-loop blocking + SQLite corruption: wrap every `requests`/`jira`/`sqlite3` call in `asyncio.to_thread()` behind a write lock.
- Timezone off-by-one at week edges: store `date_local`, never slice `started[:10]`.
- Notification spam / permission denial: notify only on gap transitions + when tab hidden; request permission only on user gesture.

### Blockers
- None

### TODOs
- [ ] Phase 8: SQLite persistence foundation (PERS-01,02,05,06)
- [ ] Phase 9: Read-through cache integration (PERS-03,04)
- [ ] Phase 10: Frontend seamless tab redesign (UI-01..06)
- [ ] Phase 11: Insights engine (INS-01..09)
- [ ] Phase 12: Notifications + badge (NOTIF-01..05)
- [ ] Phase 13: Gap-fill tools + TeltoHeart timesheet (GAP-01,02 + TELTO-01..04)

## Session Continuity
- **Last session:** 2026-07-13
- **Next action:** `/gsd-plan-phase 8`
- **Context needed:** Read ROADMAP.md (Phase 8 details), REQUIREMENTS.md (PERS), app/plugins/jira_tracker.py, app/static/js/jira.js

---

*Last updated: 2026-07-13 | M4 roadmap drafted — Phases 8-13 planned, next: Phase 8*

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| (M3 history preserved in archived milestone) | | | |

## Operator Next Steps

- Start M4 execution with /gsd-plan-phase 8
