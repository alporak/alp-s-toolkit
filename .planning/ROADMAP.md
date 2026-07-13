# Roadmap — Alps Toolkit

## Milestones

- ✅ **M1: Core Competence Plugin** — Phases 1-2 (shipped)
- ✅ **M2: Performance Analytics v2** — Phases 3-4 (shipped)
- ✅ **M3: Documentation Search Engine** — Phases 5-7 (shipped 2026-07-02)
- ⬜ **M4: Jira Tracker Rework** — Phases 8-13 (planning)

---

## Phases

<details>
<summary>✅ M1: Core Competence Plugin (Phases 1-2) — SHIPPED</summary>

- [x] Phase 1: Backend Plugin — SQLite, Jira sync, state machine, stats API
- [x] Phase 2: Frontend Dashboard — SPA with bar chart, sync button, status display

</details>

<details>
<summary>✅ M2: Performance Analytics v2 (Phases 3-4) — SHIPPED</summary>

- [x] Phase 3: Backend Enhancements — extended schema, 8 endpoints, attribution
- [x] Phase 4: Frontend Power-Dashboard — tabs, summary cards, per-ticket table, multi-chart

</details>

<details>
<summary>✅ M3: Documentation Search Engine (Phases 5-7) — SHIPPED 2026-07-02</summary>

- [x] Phase 5: Extraction & Index Foundation — 6 formats, FTS5 schema, charset detection
- [x] Phase 6: Sync Engine & Search API — git sync, BM25 search, preview, path traversal protection
- [x] Phase 7: Frontend SPA — search-as-you-type, HTML preview, filters, keyboard nav, "Open file"

</details>

<details open>
<summary>🔄 M4: Jira Tracker Rework (Phases 8-13) — IN PROGRESS</summary>

- [x] Phase 8: SQLite Persistence Foundation — local store survives restarts, event-loop refactor, timezone-correct dates
- [x] Phase 9: Read-Through Cache Integration — TTL + stale-serve, scoped invalidation
- [x] Phase 10: Frontend Seamless Tab Redesign — persistent sidebar, shared store, no re-fetch on switch
- [ ] Phase 11: Insights Engine — ghost-day / under-target / non-working-day logic + Insights tab UI
- [ ] Phase 12: Notifications + Badge — nav/tab badges, toggleable transition-only browser notifs
- [ ] Phase 13: Gap-Fill Tools + TeltoHeart Timesheet — quick-fill actions + side-project tracker

</details>

---

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Backend Plugin | M1 | 1/1 | Complete | M1 |
| 2. Frontend Dashboard | M1 | 1/1 | Complete | M1 |
| 3. Backend Enhancements | M2 | 1/1 | Complete | M2 |
| 4. Frontend Power-Dashboard | M2 | 1/1 | Complete | M2 |
| 5. Extraction & Index | M3 | 2/2 | Complete | 2026-07-02 |
| 6. Sync Engine & Search API | M3 | 2/2 | Complete | 2026-07-02 |
| 7. Frontend SPA | M3 | 1/1 | Complete | 2026-07-02 |
| 8. SQLite Persistence Foundation | M4 | 1/1 | Complete | 2026-07-13 |
| 9. Read-Through Cache Integration | M4 | 1/1 | Complete | 2026-07-13 |
| 10. Frontend Seamless Tab Redesign | M4 | 1/1 | Complete | 2026-07-13 |
| 11. Insights Engine | M4 | 0/0 | Not started | — |
| 12. Notifications + Badge | M4 | 0/0 | Not started | — |
| 13. Gap-Fill Tools + TeltoHeart Timesheet | M4 | 0/0 | Not started | — |

---

## Phase Details

### Phase 8: SQLite Persistence Foundation
**Goal**: Jira worklog + assigned data persists locally across restarts, all blocking I/O is off the event loop, and dates are timezone-correct.
**Depends on**: Nothing (M4 start)
**Requirements**: PERS-01, PERS-02, PERS-05, PERS-06
**Success Criteria** (what must be TRUE):
  1. After restarting the app/server, the Jira Tracker renders previously loaded worklogs with no Jira API call (instant load from SQLite).
  2. Assigned tickets are present immediately after a restart without a Jira fetch.
  3. The server stays responsive (event loop not blocked) during Jira/SQLite operations — concurrent requests do not stall.
  4. A worklog dated near a local week boundary (e.g. midnight) is bucketed into the correct local week, not an off-by-one UTC week.
**Plans**: TBD

### Phase 9: Read-Through Cache Integration
**Goal**: Jira Tracker reads through the SQLite store with TTL and stale-serve, invalidating only the affected scope on writes.
**Depends on**: Phase 8
**Requirements**: PERS-03, PERS-04
**Success Criteria** (what must be TRUE):
  1. When Jira is unreachable, the tracker still serves the last cached worklogs with a visible "stale" indicator instead of erroring or returning empty.
  2. After a successful worklog add/edit/delete, only the affected `(account_id, week)` is refreshed — other accounts/weeks stay cached (never a global clear).
  3. On a cache miss or TTL expiry, the tracker transparently fetches from Jira and repopulates SQLite.
**Plans**: TBD

### Phase 10: Frontend Seamless Tab Redesign
**Goal**: Persistent sidebar layout with a shared in-memory store; tab switching toggles visibility and never re-fetches from Jira.
**Depends on**: Phase 9 (warm cache)
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06
**Success Criteria** (what must be TRUE):
  1. The Jira Tracker shows a persistent sidebar; switching between Weekly/Assigned/Insights/Config does not trigger a Jira fetch (instant toggle).
  2. All tabs share one in-memory store — data mutated in one tab is visible in another without reloading.
  3. A single shared auto-refresh interval drives the whole plugin (not one per tab).
  4. Editing the tracker in one browser tab updates another open tab via localStorage without a manual reload.
  5. After logging/editing/deleting a worklog, the shared store invalidates so the UI shows fresh data without a full page reload.
**Plans**: TBD
**UI hint**: yes

### Phase 11: Insights Engine
**Goal**: Compute and surface gaps — ghost days, under-target weeks, non-working-day recalculation, low-hours, and history — in a dedicated Insights tab.
**Depends on**: Phase 9 (data), Phase 10 (layout)
**Requirements**: INS-01, INS-02, INS-03, INS-04, INS-05, INS-06, INS-07, INS-08, INS-09
**Success Criteria** (what must be TRUE):
  1. The Insights tab flags any Mon–Fri day with zero logged hours as a "missed day" warning.
  2. A week whose total is below the configured target (default 40h, recalculated per working-day count) is flagged under-target with the gap in seconds shown.
  3. Marking a day non-working (holiday/PTO) drops the week target (e.g. 40h→32h); if that day has hours logged, it is excluded from both target and total with a warning.
  4. Clicking a missed day reveals adjacent-day context to judge mis-log vs truly missing.
  5. A historical under-target trend/streak across multiple past weeks is visible in the Insights tab.
**Plans**: TBD
**UI hint**: yes

### Phase 12: Notifications + Badge
**Goal**: Surface gaps via nav/tab badges and toggleable, transition-only browser notifications with graceful degradation.
**Depends on**: Phase 10 (layout), Phase 11 (gap knowledge)
**Requirements**: NOTIF-01, NOTIF-02, NOTIF-03, NOTIF-04, NOTIF-05
**Success Criteria** (what must be TRUE):
  1. A nav-level tab-bar badge appears on the Jira Tracker whenever gaps (missed days / short weeks) exist.
  2. The Insights tab shows its own badge when gaps exist.
  3. A user-gesture toggle requests Notification permission; the choice persists across reloads and is never requested without interaction.
  4. Browser notifications fire only when a gap appears or clears (not every render) and not while the tab is visible.
  5. If permission is denied or the context is insecure, the system degrades to badge + in-app toast without breaking.
**Plans**: TBD
**UI hint**: yes

### Phase 13: Gap-Fill Tools + TeltoHeart Timesheet
**Goal**: Power-user quick actions to fill missed hours / top-up short weeks, plus a TeltoHeart side-project timesheet tracker.
**Depends on**: Phase 9 (cache/invalidation), Phase 10 (UI), Phase 11 (gap data)
**Requirements**: GAP-01, GAP-02, TELTO-01, TELTO-02, TELTO-03, TELTO-04
**Success Criteria** (what must be TRUE):
  1. A "log hours for this missed day" action prefills the date + suggested amount and posts via the existing worklog endpoint.
  2. A "top up short week" action logs the remaining gap to the meeting ticket in one click.
  3. A ticket can be flagged as a TeltoHeart side-project; the flag persists across weeks.
  4. The plugin aggregates TeltoHeart side-project hours per person for any chosen week from cached worklogs.
  5. A "Generate timesheet" action produces a per-week summary (hours per person) including multiple teammates' TeltoHeart hours.
**Plans**: TBD
**UI hint**: yes

---

*Last updated: 2026-07-13 | M4: Jira Tracker Rework planned (Phases 8-13)*
