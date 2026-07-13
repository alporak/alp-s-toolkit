# Requirements: Alps Toolkit — Jira Tracker Rework (M4)

**Defined:** 2026-07-13
**Core Value:** The Jira Tracker is instant and insight-rich — you open it and your week is already there, with clear signals when hours are missing or short.

## v1 Requirements

Requirements for milestone M4. Each maps to roadmap phases (traceability filled during roadmap creation). 6 categories: Persistence, Frontend Redesign, Insights Engine, Notifications, Gap-Fill Tools, TeltoHeart.

### Persistence (PERS)

- [ ] **PERS-01**: User's worklogs are cached in a local SQLite store (per-plugin DB) that survives process restarts — reopening the app is instant, no Jira call.
- [ ] **PERS-02**: Assigned tickets are cached in the local SQLite store (survives restarts).
- [ ] **PERS-03**: Cache uses read-through with TTL; on a Jira fetch failure it serves the last persisted copy with a `stale` flag instead of erroring or returning empty.
- [ ] **PERS-04**: A successful worklog add/edit/delete invalidates only the affected `(account_id, week)` cache keys — never a global clear.
- [ ] **PERS-05**: All blocking Jira (`requests`/`jira`) and SQLite calls run via `asyncio.to_thread()` behind a write lock — no event-loop blocking (fixes existing latent bug).
- [ ] **PERS-06**: Each worklog stores a timezone-correct local `date_local` (parsed offset-aware, converted to the user's TZ) so week-boundary math is correct.

### Frontend Redesign (UI)

- [ ] **UI-01**: The Jira Tracker uses a persistent sidebar; all tab views (Weekly, Assigned, Insights, Config) are mounted once and kept alive.
- [ ] **UI-02**: Switching tabs toggles visibility — it never re-renders or re-fetches from Jira.
- [ ] **UI-03**: A single shared in-memory store holds worklogs/insights/config across tabs (no per-tab re-fetch).
- [ ] **UI-04**: One shared auto-refresh interval drives the whole plugin (not one per tab).
- [ ] **UI-05**: Cross-tab state is shared via `localStorage` + the `storage` event so other open tabs update without a reload.
- [ ] **UI-06**: After a mutation (log/edit/delete), the shared store is invalidated so the UI shows fresh data without a full reload.

### Insights Engine (INS)

- [ ] **INS-01**: Detect missed (ghost) working days — a Mon–Fri day with 0 logged hours.
- [ ] **INS-02**: Detect under-target weeks — week total < `daily_target × working_days_in_week`.
- [ ] **INS-03**: Weekly target is configurable (default 40h) with a configurable per-day base (default 8h).
- [ ] **INS-04**: User can mark non-working days (holidays/PTO); the week target recalculates (e.g. 40h → 32h for a 4-day week).
- [ ] **INS-05**: A marked-off day that already has logged hours is excluded from both target and total, with a warning shown.
- [ ] **INS-06**: Detect "low-hours" working days (0 < hours < a soft threshold) as a soft warning distinct from hard gaps.
- [ ] **INS-07**: An Insights tab renders the week-vs-target bar, missing/low days, and gap seconds.
- [ ] **INS-08**: Clicking a missed day drills down to adjacent-day context to judge if it is truly missing vs mis-logged.
- [ ] **INS-09**: A historical under-target trend/streak view across multiple past weeks.

### Notifications (NOTIF)

- [ ] **NOTIF-01**: A nav-level tab-bar badge shows when gaps (missed days / short weeks) exist.
- [ ] **NOTIF-02**: The in-plugin Insights tab shows a badge when gaps exist.
- [ ] **NOTIF-03**: Browser notifications are toggleable; permission is requested only on a user gesture and persisted.
- [ ] **NOTIF-04**: Notifications fire only on gap *transitions* (appear/cleared) and are suppressed when the tab is visible.
- [ ] **NOTIF-05**: When permission is denied or the context is not secure, the system degrades to badge + in-app toast (never breaks).

### Gap-Fill Tools (GAP)

- [ ] **GAP-01**: A quick "log hours for this missed day" action pre-fills date + suggested amount and posts via the existing worklog endpoint.
- [ ] **GAP-02**: A one-click "top up short week" action logs the remaining gap to the meeting ticket.

### TeltoHeart Time Tracking (TELTO)

- [ ] **TELTO-01**: User can mark a ticket as a TeltoHeart side-project (local metadata flag, persists across weeks).
- [ ] **TELTO-02**: The plugin aggregates TeltoHeart side-project hours per person for any chosen week from cached worklogs.
- [ ] **TELTO-03**: A "Generate timesheet" action produces a per-week summary (hours per person) for delivery.
- [ ] **TELTO-04**: Timesheet aggregation supports multiple teammates (the user's + a colleague's TeltoHeart hours).

## v2 Requirements

Deferred to a future milestone. Tracked but not in the M4 roadmap.

### Insights

- **INS-V2-01**: General per-teammate gap view (missed days / short weeks shown for each teammate, not just the user).
- **INS-V2-02**: Auto-logging or AI-estimated targets — explicitly out of scope (falsifies timesheets).

## Out of Scope

| Feature | Reason |
|---------|--------|
| Auto-logging hours for missed days | Falsifies the timesheet; breaks audit integrity (every real tool only *identifies* gaps) |
| AI-estimated "expected hours" from history | Misleading; averages ≠ contract; erodes trust in the number |
| Mobile push notifications | Product is a browser SPA on an internal network; no mobile app |
| Service-worker / persistent push notifications | Requires HTTPS + SW registration the toolkit lacks; overkill for an open-tab tool |
| v1 backend background sync task | Write-contention + shutdown-cancellation complexity; frontend auto-refresh + read-through already cover freshness |
| Manager-facing enforcement / team shaming board | Not the use case (self/peer view); privacy/trust risk |
| Idle/away-time & screenshot tracking | Privacy-invasive, irrelevant for an internal Jira tool |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PERS-01 | Phase 8 | Pending |
| PERS-02 | Phase 8 | Pending |
| PERS-03 | Phase 9 | Pending |
| PERS-04 | Phase 9 | Pending |
| PERS-05 | Phase 8 | Pending |
| PERS-06 | Phase 8 | Pending |
| UI-01 | Phase 10 | Pending |
| UI-02 | Phase 10 | Pending |
| UI-03 | Phase 10 | Pending |
| UI-04 | Phase 10 | Pending |
| UI-05 | Phase 10 | Pending |
| UI-06 | Phase 10 | Pending |
| INS-01 | Phase 11 | Pending |
| INS-02 | Phase 11 | Pending |
| INS-03 | Phase 11 | Pending |
| INS-04 | Phase 11 | Pending |
| INS-05 | Phase 11 | Pending |
| INS-06 | Phase 11 | Pending |
| INS-07 | Phase 11 | Pending |
| INS-08 | Phase 11 | Pending |
| INS-09 | Phase 11 | Pending |
| NOTIF-01 | Phase 12 | Pending |
| NOTIF-02 | Phase 12 | Pending |
| NOTIF-03 | Phase 12 | Pending |
| NOTIF-04 | Phase 12 | Pending |
| NOTIF-05 | Phase 12 | Pending |
| GAP-01 | Phase 13 | Pending |
| GAP-02 | Phase 13 | Pending |
| TELTO-01 | Phase 13 | Pending |
| TELTO-02 | Phase 13 | Pending |
| TELTO-03 | Phase 13 | Pending |
| TELTO-04 | Phase 13 | Pending |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 32
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-13*
*Last updated: 2026-07-13 — traceability filled during M4 roadmap creation (Phases 8-13)*
