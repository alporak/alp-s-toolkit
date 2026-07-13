# Project Research Summary

**Project:** Alps Toolkit — Jira Tracker Rework (M4)
**Domain:** FastAPI + vanilla-JS internal Jira worklog tracker — local SQLite persistence, seamless cross-tab UI, browser + in-app notifications, and a "hours-vs-target" insights engine
**Researched:** 2026-07-13
**Confidence:** HIGH

## Executive Summary

The Jira Tracker plugin works but has two structural problems: (1) its worklog cache is an in-memory Python dict that is wiped on every process restart and on every tab switch the frontend re-fetches from Jira, and (2) it has no insight into missed/under-target logging. The fix is to add a **SQLite read-through cache** (mirroring the pattern already used by the `doc_search`/`competence` plugins) and a **persistent frontend layout** with a shared in-memory store, so reopening the app or switching tabs is instant and offline-tolerant. No new Python dependency is required — `sqlite3`, `asyncio.to_thread`, `requests`, `jira` (pin to 3.10.5), and the browser `Notification`/`localStorage` APIs are all already in the stack.

The highest-leverage insight from research: the existing plugin **already violates the toolkit's own hard rule** — it calls synchronous `requests`/`jira` inside `async def` route handlers, which blocks the event loop (a documented Windows SQLite-corruption risk). Phase 1 must wrap those calls in `asyncio.to_thread()` *before* adding SQLite. The insights layer should follow the real-tool pattern (Toggl/Harvest/Clockify/Tempo): detect → summarize → notify → let the user act (never auto-write hours). The 40h target must be modeled as `daily_target(8h) × working_days`, so marking non-working days recalculates it (40h → 32h for a 4-day week). Notifications must feature-detect the secure context and degrade to the in-app badge + toast, and must fire only on gap *transitions* (not every render) to avoid spam.

## Key Findings

### Recommended Stack

No new dependencies. Adopt the existing SQLite pattern verbatim: co-located `jira_tracker.db`, `PRAGMA journal_mode=WAL`, `row_factory=Row`, a `threading.Lock()` to serialize writes, `_ensure_schema()` at `startup()`, and **all** blocking I/O (Jira `requests`/`jira` calls and SQLite) via `asyncio.to_thread()`. Keep `requests` + `jira` (do **not** migrate to `httpx` async — the `jira` lib has no async API, so migration is partial and risky). Browser notifications use the native `Notification` API (no library), feature-detected (`"Notification" in window && window.isSecureContext`) with `toast()` fallback. Cross-tab frontend state uses module-level JS memory (hot cache) + `localStorage` + the `storage` event (fires only in *other* tabs). Explicitly reject IndexedDB, service-worker/push notifications, SQL ORMs, and a v1 backend background-sync task.

**Core technologies:**
- `sqlite3` (stdlib) + `asyncio.to_thread()` + `threading.Lock()` — local read-through cache that survives restarts, Windows-safe
- `requests` / `jira` (pin 3.10.5) — Jira access, wrapped in `to_thread` (keep, don't migrate)
- Browser `Notification` API + `toast()` fallback — toggleable notifications with secure-context degradation
- `localStorage` + `storage` event — cross-tab shared state + invalidation signal (no npm)

### Expected Features

**Must have (table stakes):**
- Missed-day (ghost-day) detection — working day (Mon–Fri) with 0 logged hours
- Under-target-week alert — week total vs `daily_target × working_days`
- Configurable weekly target (default 40h) + Mon–Fri working-day definition
- Mark non-working days (holidays/PTO) that recalculate the target (40h → 32h)
- In-app Insights tab + tab-bar badge when gaps exist
- Quick "fill missing day" action (reuses existing `POST /api/jira/worklog`)

**Should have (competitive):**
- Toggleable browser notifications (best-effort, secure-context)
- One-click "top up short week" to the meeting ticket
- Per-teammate gap view (reuses existing teammates config + per-account fetch)
- Ghost-day drill-down

**Defer (v2+):**
- Historical under-target trend / streak (needs persisted multi-week history + time)
- Auto-logging / AI-estimated targets (anti-features — falsify the timesheet)

### Architecture Approach

Split persistence/analytics into a new `app/plugins/jira_store.py` (schema, read-through cache, insights computation, `non_working_days` CRUD) that `jira_tracker.py` imports; Jira stays the authoritative source, the DB is a read-only mirror (the one exception is `non_working_days`, local-only user metadata). Read path: SQLite → API → in-memory store → DOM, with Jira hit only on cache miss. Frontend: replace `createTabs` re-render with a persistent sidebar + `this._store` and dirty flags so tab switching toggles `display` instead of re-fetching. Insights is a pure function over stored rows, cheap enough to drive the nav badge on every refresh. Invalidation is scoped by `(account_id, week)` — never a global clear.

**Major components:**
1. `app/plugins/jira_store.py` (NEW) — SQLite schema, read-through cache, insights, non-working-days
2. `app/plugins/jira_tracker.py` (MODIFIED) — delegates to store, keeps Jira fetch, adds `/insights` endpoints, scopes invalidation
3. `app/static/js/jira.js` (MODIFIED) — persistent sidebar + shared store + Insights view + notification toggle
4. `app/static/js/core.js` (MODIFIED, additive) — `setPluginBadge(pluginId, count)` nav hook

### Critical Pitfalls

1. **Cache-as-truth divergence** — never populate the cache from a write payload; on a successful worklog add/edit/delete, *invalidate* the affected `(account_id, week)` and let the next read re-fetch. (Pitfall 1)
2. **Event-loop blocking + SQLite corruption** — wrap every `requests`/`jira`/`sqlite3` call in `asyncio.to_thread()` behind a write lock; the plugin currently violates this rule. (Pitfall 3/4)
3. **Timezone off-by-one at week edges** — parse `started` offset-aware, convert to `LOCAL_TZ` (e.g. `Europe/Vilnius`), store `date_local`; never slice `started[:10]`. (Pitfall 5)
4. **Target miscalculation on marked-off days** — model target as `daily_target × working_days`; when a marked-off day has logged hours, exclude it from *both* target and total and warn; keep markings as query-time metadata. (Pitfall 6)
5. **Notification spam / permission denial** — notify only on gap *transitions* and only when the tab is hidden; request `Notification` permission only on a user gesture; fall back to badge + toast on `denied`. (Pitfall 7/8)

## Implications for Roadmap

### Phase 1: SQLite persistence foundation (`jira_store.py` + event-loop refactor)
**Rationale:** The foundation everything else builds on; also fixes the latent event-loop-blocking bug.
**Delivers:** `jira_store.py` with WAL schema, `_ensure_schema()` at `startup()`, upsert/get for worklogs + assigned, `cache_meta`, `non_working_days` table; all blocking calls moved to `asyncio.to_thread()`.
**Addresses:** STACK (SQLite pattern), FEATURES (data store for day-off marks)
**Avoids:** Pitfalls 1, 2, 3, 4, 5 (store `date_local`), 9, 10, 11, 13

### Phase 2: Read-through cache integration (modify `jira_tracker.py`)
**Rationale:** Makes restarts instant and removes Jira hits on warm cache before any UI work.
**Delivers:** `/worklogs/weekly` and `/assigned` read-through with stale-serve on Jira failure; scoped `(account_id, week)` invalidation on writes; in-flight guard; `stale` flag in responses.
**Uses:** STACK (read-through + stale-serve)
**Implements:** ARCHITECTURE Pattern 1 + Pattern 4

### Phase 3: Frontend persistent layout + shared store (`jira.js`)
**Rationale:** Delivers the "seamless transitions, no re-fetch on tab switch" goal; depends only on Phase 2's warm cache.
**Delivers:** Persistent sidebar, `this._store` with dirty flags, one shared auto-refresh interval, `display`-toggle tab switching; `localStorage` + `storage` event for cross-tab; store invalidation after mutations.
**Implements:** ARCHITECTURE Pattern 2 + Pitfall 12 mitigation

### Phase 4: Insights engine (backend)
**Rationale:** The data layer for notifications + gap-fill; pure function over stored rows.
**Delivers:** `compute_insights()` (missing days, low days, week-vs-target, gap seconds), `/api/jira/insights` + `/insights/summary`, `non_working_days` CRUD, `daily_target_hours` config.
**Implements:** ARCHITECTURE Pattern 3; avoids Pitfalls 5/6

### Phase 5: Insights tab UI + gap-fill tools (`jira.js`)
**Rationale:** The user-facing payoff; depends on Phase 3 (layout) + Phase 4 (data).
**Delivers:** Insights tab rendering (week-vs-target bar, missing/low days, gap seconds), "log hours for missed day" + "top up short week" quick actions (reuse existing worklog POST then `mark_stale` + dirty), non-working-day marker UI.

### Phase 6: Notifications + badge
**Rationale:** Last layer; depends on Phase 4 (knows gaps) + Phase 3 (layout).
**Delivers:** `setPluginBadge` in `core.js`, in-app Insights-tab badge, Notification permission flow (toggle click) + fire on gap transition with `toast()` fallback.
**Avoids:** Pitfalls 7, 8

### Phase Ordering Rationale

- Store first (Phase 1–2) is a shippable "instant reload" vertical slice that de-risks the cache before UI is built on top of it.
- Frontend persistence (Phase 3) only needs the warm cache, not the insights data.
- Insights data (Phase 4) is a pure function over stored rows, so it can run in parallel with Phase 3 after Phase 2.
- UI for insights (Phase 5) and notifications (Phase 6) are strictly downstream of the data + layout layers.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** confirm Jira's actual `started` offset (UTC vs reporter TZ) via one live `GET issue/{key}/worklog`; the offset-aware fix is correct regardless, but it determines whether existing rows need backfill.
- **Phase 6:** confirm the toolkit's deployment scheme (HTTPS vs LAN http://) — determines whether OS notifications can fire at all; badge + toast are always available.

Phases with standard patterns (skip research-phase):
- **Phase 3:** DOM-toggle persistence is a well-established SPA pattern; no extra research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified against in-repo `doc_search.py`/`competence.py`; Context7-verified `jira` 3.10.5; MDN Notification/`storage` docs |
| Features | HIGH | Clockify + Harvest feature pages fetched; anti-features grounded in industry consensus |
| Architecture | HIGH | Integration points read directly from `jira_tracker.py`, `jira.js`, `core.js`, `doc_search.py` |
| Pitfalls | HIGH | Most anchored to specific lines in shipped code + documented toolkit constraints; one TZ item flagged for live spike |

**Overall confidence:** HIGH

### Gaps to Address

- **Deployment scheme (HTTPS vs http://):** determines if OS notifications fire. Handle in Phase 6 by feature-detecting and degrading to badge+toast regardless.
- **Jira `started` offset:** confirm via live spike in Phase 1; offset-aware `date_local` storage is correct either way.
- **Marked-off day with logged hours:** adopt "exclude from both sides + warn" interpretation (confirm with user if product spec differs).
- **Insights history window:** default to current week (+ optionally previous week for Monday catch-up); confirm with user.

## Sources

### Primary (HIGH confidence)
- `app/plugins/doc_search.py` / `competence.py` — SQLite WAL + `to_thread` + `_ensure_schema` convention
- `app/plugins/jira_tracker.py`, `app/static/js/jira.js`, `app/static/js/core.js` — current behavior (root causes)
- `.planning/PROJECT.md` — M4 goal + SQLite/event-loop constraints
- Context7 `/pycontribs/jira` — `jira` 3.10.5, sync-only
- MDN Notifications API + Window `storage` event — secure-context + cross-tab behavior

### Secondary (MEDIUM confidence)
- Clockify / Harvest feature pages — ghost-day detection, reminders, time-off modules
- Web Notifications secure-context requirement (deployment not yet confirmed)

### Tertiary (LOW confidence)
- Toggl Track / Jira Tempo precise behaviors — training knowledge only; not load-bearing for the design

---
*Research completed: 2026-07-13*
*Ready for roadmap: yes*
