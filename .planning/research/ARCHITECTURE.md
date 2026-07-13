# Architecture Research

**Domain:** Internal Jira analytics plugin rework (FastAPI + vanilla-JS SPA) — local SQLite read-through cache, persistent-tab UI, browser notifications, insights engine
**Researched:** 2026-07-13
**Confidence:** HIGH (integration points derived directly from the existing codebase: `jira_tracker.py`, `jira.js`, `core.js`, `doc_search.py`, `base.py`, `PROJECT.md`)

---

## Standard Architecture

### System Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│  Browser (vanilla-JS SPA, jira.js)                                        │
│                                                                           │
│  ┌──────────────── sidebar / tab-bar ────────────────┐                   │
│  │ Weekly │ Assigned │ Insights │ Config            │  ← tabs keep DOM   │
│  └───────────────────────┬──────────────────────────┘     alive (toggle) │
│                          │  read from shared in-memory store             │
│                  ┌───────▼────────┐                                       │
│                  │ this._store    │  Map<week, payload>, insights, cfg    │
│                  └───────┬────────┘                                       │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │  fetch() (structured JSON + "stale" flag)
                           ▼
┌────────────────────────────────────────────────────────────────────────┐
│  FastAPI — app/plugins/jira_tracker.py  (routes + Jira read path)         │
│                                                                           │
│   /api/jira/worklogs/weekly  ──┐                                           │
│   /api/jira/assigned          │  read-through orchestration              │
│   /api/jira/insights          │                                           │
│   POST/PUT/DELETE /worklog ───┴─► forces invalidation in store           │
│                          │                                                │
│                          ▼  (imports)                                     │
│   app/plugins/jira_store.py  ── NEW persistence module                    │
│     • _get_db()  WAL, row_factory                          │              │
│     • get_worklogs()  read-through (TTL + stale-serve)     │              │
│     • upsert_worklogs() / mark_stale()                     │              │
│     • compute_insights()  (pure, on stored rows)          │              │
│                          │                                                │
│            blocking I/O via asyncio.to_thread()  (Windows-safe)           │
│                          │                                                │
│              ┌───────────▼────────────┐    ┌──────────────────────────┐  │
│              │ jira_tracker.db (WAL)  │    │ Jira Cloud REST API      │  │
│              │ worklogs               │    │ (authoritative source)   │  │
│              │ assigned_tickets       │◄───┤ search_issues + per-issue │  │
│              │ cache_meta             │    │ /worklog                 │  │
│              │ non_working_days       │    └──────────────────────────┘  │
│              └────────────────────────┘                                  │
└────────────────────────────────────────────────────────────────────────┘
```

**Key principle (from `PROJECT.md`):** Jira is authoritative; the local DB is a *read-only mirror*. We never write business data to SQLite that didn't come from Jira. The one exception is `non_working_days` (user annotations) which is local-only metadata used by the insights engine.

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `jira_tracker.py` | Route handlers + Jira read path (`_fetch_worklogs_for_user`, `_api`, `_jira`) | Unchanged fetch logic; now delegates persistence to `jira_store` |
| `jira_store.py` (**NEW**) | SQLite schema, read-through cache, insights computation, non-working-days | Mirror of `doc_search.py`'s DB pattern (`_get_db`, `_db_lock`, `_ensure_schema`) |
| `jira.js` | Persistent sidebar/tab UI + shared in-memory `this._store` | Replace `createTabs` re-render with show/hide + dirty flags |
| `core.js` | Tab helper + NEW `setPluginBadge(id, n)` nav hook | Minor additive change only |
| `jira_tracker.db` | Durable mirror + insights metadata | Per-plugin file in `app/plugins/`, WAL |

---

## Recommended Project Structure

```
app/plugins/
├── jira_tracker.py        # MODIFIED: routes delegate to jira_store; keeps Jira fetch logic
├── jira_store.py          # NEW: schema, read-through, insights, non_working_days
├── doc_search.py          # reference pattern (do not touch)
└── base.py                # unchanged

app/static/js/
├── jira.js                # MODIFIED: persistent layout + this._store
└── core.js                # MODIFIED (small): add setPluginBadge()

.planning/research/
└── ARCHITECTURE.md        # this file
```

### Structure Rationale

- **`jira_store.py` as a separate module** mirrors the existing split in this repo (`doc_search.py` owns schema; `doc_extraction.py` owns parsing). Keeping the Jira *fetch* in `jira_tracker.py` but the *persistence + analytics* in `jira_store.py` preserves the convention and keeps each file focused. It also makes the cache independently testable.
- **DB co-located in `app/plugins/`** exactly like `DB_PATH = os.path.join(os.path.dirname(__file__), "doc_search.db")` — no new config path needed.
- **No framework change on the frontend** — vanilla JS, `h()`/`api()` helpers, additive `core.js` helper only.

---

## Architectural Patterns

### Pattern 1: Read-Through Cache with TTL + Stale-Serve

**What:** `get_worklogs(account_id, d_from, d_to)` checks the SQLite store first. If a fresh (within TTL) complete copy exists, it returns rows with no Jira call. Otherwise it fetches from Jira, persists, and returns. On Jira failure it serves the stale persisted rows and flags `stale: true` instead of erroring.

**When to use:** Any time the upstream (Jira) is slow/rate-limited and we want instant reloads + restart survival. This is the core of the "instant" goal.

**Trade-offs:** Slightly more storage + a refresh/invalidation bookkeeping table (`cache_meta`). Worth it — eliminates the per-process in-memory loss on restart and the re-fetch-on-every-tab-open.

**Example (sketch in `jira_store.py`):**
```python
def get_worklogs(account_id, d_from, d_to, force=False):
    week_start = _monday(d_from)
    meta = _cache_meta_get(account_id, week_start)
    fresh = meta and not force and (now() - meta["fetched_at"] < TTL)
    if fresh and meta["complete"]:
        return _rows_for_week(account_id, week_start), {"cached": True, "stale": False}
    try:
        rows = _fetch_worklogs_for_user(account_id, d_from, d_to)  # from jira_tracker
        _upsert_worklogs(account_id, rows)
        _cache_meta_set(account_id, week_start, complete=True)
        return rows, {"cached": False, "stale": False}
    except JIRAError:
        if meta:                       # graceful degradation
            return _rows_for_week(account_id, week_start), {"cached": True, "stale": True}
        raise
```

### Pattern 2: Persistent Tab Bodies via DOM Toggle (not re-render)

**What:** The current `createTabs` (core.js:168) does `body.innerHTML = ""` on every `activate()` — that destroys the DOM and forces the render callback (which re-fetches). Replace with: build each view's root element **once** in `init()`, keep all of them in the DOM, and switch visibility with `el.style.display`. Re-activation only toggles `display`.

**When to use:** Any SPA where tab content is expensive to rebuild and you want instant switching. Exactly the M4 "seamless transitions" requirement.

**Trade-offs:** Slightly more DOM resident in memory (trivial for 4 tabs). Requires a "dirty" flag so data-affecting actions (log work, refresh) still re-render the relevant view. This is the correct trade for this app.

**Example (sketch in `jira.js`):**
```js
init(container) {
  this._store = { weekly: new Map(), insights: null, cfg: null, dirty: {wk:true, asg:true, ins:true} };
  this._views = {
    wk:   this._mountWeekly(container),
    asg:  this._mountAssigned(container),
    ins:  this._mountInsights(container),
    cfg:  this._mountConfig(container),
  };
  this._sidebar(container, ["wk","asg","ins","cfg"], id => this._show(id));
  this._show("wk");
  this._startAutoRefresh();          // one interval for the whole plugin
}
_show(id){ for (const k in this._views) this._views[k].style.display = (k===id)?"":"none"; }
// re-render only when this._store.dirty[k] is true (e.g. after logging work)
```

> **Alternative considered (and rejected for M4 scope):** Extend `createTabs` in `core.js` with a `{persist:true}` mode so *all* plugins benefit. Cleaner long-term, but it's a shared-core change with blast radius across every plugin and the question only asks for the Jira rework. Recommend the local jira.js approach now; promote to `core.js` later if another plugin needs it. If we do promote, the change is purely additive (`createTabs(container, tabs, {persist})`) and non-breaking.

### Pattern 3: Insights as a Pure Function over the Mirror

**What:** `compute_insights(worklogs, non_working_days, daily_target=8h)` is a pure, dependency-free function that runs entirely on rows already in SQLite — no Jira call. It returns structured gaps. The backend exposes it via `/api/jira/insights`; the nav badge and browser notification are driven by its output.

**When to use:** Any "analytics over cached data" feature. Keeps the expensive network call out of the insight path and makes the badge/notification cheap to recompute on a timer.

**Example:** see `compute_insights` math below.

### Pattern 4: In-Flight Fetch Guard (anti-thundering-herd)

**What:** Because a week fetch hits Jira N times (search + one `/worklog` call per issue), concurrent requests for the same week must not each trigger a full fetch. Guard the read-through with a per-cache-key lock / in-flight future.

**When to use:** Read-through caches where the fill operation is expensive and can be triggered by multiple users/tabs at once.

**Example:**
```python
_inflight: dict[str, asyncio.Future] = {}
async def get_worklogs_async(account_id, d_from, d_to, force=False):
    key = f"{account_id}|{_monday(d_from)}"
    if key in _inflight and not force:
        return await _inflight[key]
    fut = asyncio.get_event_loop().create_future()
    _inflight[key] = fut
    try:
        res = await asyncio.to_thread(get_worklogs, account_id, d_from, d_to, force)
        fut.set_result(res)
    finally:
        _inflight.pop(key, None)
    return res
```

---

## Data Flow

### Request Flow (weekly worklogs — the hot path)

```
User clicks "Weekly" tab (first time)
   ↓  (dirty flag set)
jira.js _show("wk") → reads this._store.weekly.get(weekKey)
   ↓  miss
api("/api/jira/worklogs/weekly?week_of=...")
   ↓
jira_tracker.py route → jira_store.get_worklogs()  [read-through]
   ↓  cache miss
Jira Cloud: search_issues + per-issue /worklog
   ↓
jira_store.upsert_worklogs() + cache_meta   ← persisted to jira_tracker.db (WAL)
   ↓
returns rows + {cached:false}
   ↓
jira.js renders table, stores payload in this._store.weekly (dirty=false)

User switches to Assigned, then back to Weekly
   ↓  (no API call — this._store has it; DOM never destroyed)
jira.js _show("wk") → display toggled, payload already in memory
```

### Invalidation Flow (after logging work)

```
POST /api/jira/worklog  (jira_tracker.py)
   ↓  success
jira_store.mark_stale(account_id, affected_weeks)   # clears cache_meta + deletes rows
jira.js: optimistic update of this._store + set dirty.wk = true
   ↓  next weekly view render (or auto-refresh) re-reads → cache miss → fresh Jira fetch
```

### Notification / Badge Flow

```
Auto-refresh timer (or manual refresh) completes
   ↓
api("/api/jira/insights/summary")  → { gap_count, missed_days, short_weeks }
   ↓  gap_count > 0
core.setPluginBadge("jira", gap_count)   ← red dot/number on the nav button
if Notification.permission === "granted":
    new Notification("Jira: 2 days missing hours", {...})
else: in-app toast (always works) + Insights tab badge
```

### Key Data Flows

1. **Mirror sync:** Jira → SQLite (write path only on cache miss / force).
2. **Read path:** SQLite → API → in-memory store → DOM (no Jira hit when warm).
3. **Insight computation:** SQLite rows → pure function → badge/notification.
4. **Cross-session:** on app restart or plugin re-entry, SQLite serves instantly; only expired TTL triggers a Jira fetch.

---

## SQLite Schema (proposed for `jira_store.py`)

Mirror `doc_search.py`: `DB_PATH = os.path.join(os.path.dirname(__file__), "jira_tracker.db")`, `SCHEMA_VERSION = "1"`, `_get_db()` opens with `PRAGMA journal_mode=WAL`, `_db_lock = threading.Lock()`, all writes via `asyncio.to_thread`.

```sql
CREATE TABLE IF NOT EXISTS worklogs (
    id               TEXT    NOT NULL,        -- Jira worklog id
    account_id       TEXT    NOT NULL,
    issue_key        TEXT    NOT NULL,
    issue_summary    TEXT    NOT NULL DEFAULT '',
    date             TEXT    NOT NULL,        -- YYYY-MM-DD
    started          TEXT    NOT NULL DEFAULT '',
    time_spent_seconds INTEGER NOT NULL DEFAULT 0,
    comment          TEXT    NOT NULL DEFAULT '',
    week_start       TEXT    NOT NULL,        -- derived Monday, for insights queries
    fetched_at       TEXT    NOT NULL,
    PRIMARY KEY (account_id, id)
);
CREATE INDEX IF NOT EXISTS idx_wl_week ON worklogs(account_id, week_start);
CREATE INDEX IF NOT EXISTS idx_wl_date ON worklogs(account_id, date);

CREATE TABLE IF NOT EXISTS assigned_tickets (
    key             TEXT PRIMARY KEY,
    summary         TEXT,
    status          TEXT,
    priority        TEXT,
    attachment_count INTEGER,
    has_folder      INTEGER,
    local_files     INTEGER,
    fetched_at      TEXT
);

CREATE TABLE IF NOT EXISTS cache_meta (
    account_id   TEXT NOT NULL,
    week_start   TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    complete     INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (account_id, week_start)
);

CREATE TABLE IF NOT EXISTS non_working_days (
    date    TEXT PRIMARY KEY,   -- YYYY-MM-DD
    reason  TEXT NOT NULL DEFAULT ''
);
-- Note: weekends are derived at query time, not stored, unless user explicitly marks one.
```

**Why these tables:**
- `worklogs` keyed by `(account_id, id)` → upsert is idempotent, supports teammates, and `week_start` makes insights queries O(indexed) instead of scanning.
- `cache_meta` decouples "is the week fresh?" from the row data so read-through + stale-serve + invalidation are trivial.
- `non_working_days` is the *only* locally-authored table (user annotations). Everything else is a Jira mirror.

---

## Insights Engine — "days missing hours" & "week below target"

### Definitions

- **Working day:** Mon–Fri **minus** any `non_working_days` entry in that range (weekends excluded by default; a user may also mark a Saturday as working, but the default target math only adjusts *weekdays*).
- **Day "missing hours":** day is a working day AND `logged_seconds == 0`. (Optionally a softer "low hours" tier for `0 < secs < MIN_DAILY`, e.g. 4h — surface separately, don't count as a hard gap.)
- **Day "low hours":** working day with `0 < secs < DAILY_MIN` (e.g. 4h). Informational.
- **Weekly target:** `target_seconds = DAILY_TARGET(8h) * working_days_in_week`, where `working_days_in_week = number of Mon–Fri in the week that are NOT in non_working_days`.
  - Default 5-day week → 40h.
  - One weekday holiday (e.g. Friday off) → 4 × 8h = **32h**.
  - Two holidays → 24h. This is the "recalculates the 40h target" requirement.
- **Week below target:** `sum(logged_seconds for the week) < target_seconds`.

### Algorithm (pure function)

```python
def compute_insights(rows, non_working_days, daily_target_sec=8*3600, daily_min_sec=4*3600):
    nwd = set(non_working_days)
    # group by date
    by_date = defaultdict(int)
    for w in rows:
        by_date[w["date"]] += w["time_spent_seconds"]
    # determine week's working weekdays
    monday = date.fromisoformat(rows[0]["week_start"]) if rows else today_monday()
    week_dates = [(monday + timedelta(d)).isoformat() for d in range(7)]
    working = [d for d in week_dates
               if date.fromisoformat(d).weekday() < 5 and d not in nwd]
    target = daily_target_sec * len(working)
    total = sum(by_date.values())
    missing_days = [d for d in working if by_date.get(d, 0) == 0]
    low_days     = [d for d in working if 0 < by_date.get(d, 0) < daily_min_sec]
    return {
        "total_seconds": total,
        "target_seconds": target,
        "working_days": len(working),
        "below_target": total < target,
        "gap_seconds": max(0, target - total),
        "missing_days": missing_days,   # hard gaps → drive badge/notification
        "low_days": low_days,           # soft warnings
        "per_day": {d: by_date.get(d, 0) for d in working},
    }
```

### Why this satisfies the requirement

- The 40h target is **not** a constant — it's `8h × working_days`, so marking a non-working day automatically lowers the bar for that week (40h → 32h for a 4-day week). This is computed per-week from that week's `non_working_days` entries, so holidays only affect the weeks they fall in.
- The function runs on **stored** rows → no Jira hit → cheap enough to call on every auto-refresh and to power the nav badge.

---

## Browser Notifications & Badge

### Permission flow

1. **Secure-context caveat (pitfall — flagged MEDIUM confidence):** The Web `Notification` API requires a *secure context*. `https://` and `http://localhost` qualify; a plain `http://hostname` on the company LAN generally does **not**, so `Notification.requestPermission()` may be rejected/no-op. Mitigation: (a) serve the toolkit behind HTTPS (recommended), or (b) treat the in-app badge + toast as the always-available primary signal and the OS notification as a best-effort enhancement. Do not block the feature on permission.
2. **Request trigger:** a "Enable browser notifications" toggle in the Config (or Insights) tab calls `Notification.requestPermission()`. Store the resulting state (`granted` / `denied` / `default`) in `toolkit_settings.json` so we don't re-prompt every load.
3. **Fire trigger:** the auto-refresh loop (or a dedicated `/insights/summary` poll) calls `compute_insights`; if `missing_days` or `below_target` is true and permission is `granted`, fire `new Notification(...)`.

### Badge

- **Nav-level badge (cross-plugin visibility):** add `setPluginBadge(pluginId, count)` to `core.js`. It finds the nav button for that plugin and renders a small red dot/number. This is the "tab-bar badge" the user sees without opening the plugin. Driven by `/api/jira/insights/summary` → `{gap_count}`.
- **In-plugin Insights tab badge:** the Insights tab button in the jira sidebar shows a dot when `gap_count > 0`.
- Both always work regardless of `Notification` permission.

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single user / small team (current reality) | Current design is more than enough. SQLite WAL + per-plugin file is correct; no server needed. |
| Dozens of teammates viewed at once | Read-through already dedups per-week fetches; add the in-flight guard (Pattern 4) so N teammates don't each trigger N Jira calls. Cache `cache_meta` per account_id. |
| Hundreds of users | SQLite still fine for read-heavy mirror, but consider moving the per-issue `/worklog` fan-out to a background sync job (like `doc_search._sync_job`) instead of synchronous request-time fill, so the UI reads only from SQLite. Out of scope for M4. |

### Scaling Priorities
1. **First bottleneck:** Jira rate-limits the per-issue `/worklog` fan-out. Fix with in-flight guard + longer TTL + background sync later.
2. **Second bottleneck:** WAL checkpoint / `checkpoint` on shutdown. doc_search pattern doesn't checkpoint explicitly; follow the same (acceptable at this scale).

---

## Anti-Patterns

### Anti-Pattern 1: Keep re-fetching Jira on every tab open
**What people do:** current `jira.js` calls the API in every `_renderWeekly`/`_renderAssigned`, and `createTabs` destroys the DOM on switch.
**Why it's wrong:** slow, rate-limit prone, and makes tab switching feel broken.
**Do this instead:** persistent DOM (toggle) + read-through SQLite + shared `this._store`.

### Anti-Pattern 2: Store the cache in process memory
**What people do:** current `_wl_cache` dict.
**Why it's wrong:** lost on every restart / plugin re-entry → re-fetch, defeating "instant".
**Do this instead:** SQLite mirror (`jira_store.py`), survives restarts, survives plugin switches.

### Anti-Pattern 3: Blocking SQLite on the event loop
**What people do:** calling `sqlite3` directly inside `async def` route handlers.
**Why it's wrong:** PROJECT.md explicitly warns — "event-loop SQLite access corrupts on Windows."
**Do this instead:** every DB call via `asyncio.to_thread()` behind `_db_lock`, exactly like `doc_search.py`.

### Anti-Pattern 4: Hard-code the 40h target
**What people do:** `if total < 40*3600`.
**Why it's wrong:** ignores non-working days → false "short week" alarms on holidays.
**Do this instead:** `target = 8h × working_days_in_week` from `non_working_days` (Pattern 3).

### Anti-Pattern 5: Block the feature on Notification permission
**What people do:** only show gaps if `Notification.permission === "granted"`.
**Why it's wrong:** LAN http:// context may deny it; user sees nothing.
**Do this instead:** badge + toast always; OS notification is best-effort enhancement.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Jira Cloud REST API | Read-only mirror; fetched only on cache miss / force | `jira_tracker.py` keeps `_jira()`/`_api()`; store never writes business data back to Jira |
| Browser Notification API | `Notification.requestPermission()` + `new Notification()` | Requires secure context (HTTPS/localhost); degrade to badge+toast otherwise |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `jira_tracker.py` ↔ `jira_store.py` | Direct Python import (same process) | `jira_tracker` imports `get_worklogs`, `upsert_worklogs`, `mark_stale`, `compute_insights`, `ensure_schema` |
| `jira_tracker.py` ↔ `config` | `config.load_jira_config()` | TTL still read from `cache_ttl_minutes`; add `notifications_enabled`, `daily_target_hours` |
| `jira.js` ↔ backend | `api()` JSON | New fields: `stale` flag on weekly; `/insights` + `/insights/summary` endpoints |
| `jira.js` ↔ `core.js` | `setPluginBadge(id, n)` (NEW) | Additive; used to render nav badge |
| `jira.js` internal | `this._store` shared map | Single source of truth across tabs; dirty flags trigger re-render |

---

## New vs Modified Components (explicit)

| Component | Status | Change |
|-----------|--------|--------|
| `app/plugins/jira_store.py` | **NEW** | SQLite schema, `_get_db`/WAL/`_db_lock`/`_ensure_schema`, read-through `get_worklogs`, `upsert_worklogs`, `mark_stale`, `get_assigned`/`upsert_assigned`, `compute_insights`, `non_working_days` CRUD |
| `app/plugins/jira_tracker.py` | MODIFIED | `_wl_cache` in-memory dict replaced by `jira_store` calls; `/worklogs/weekly` & `/assigned` read-through; add `/insights` + `/insights/summary`; writes call `mark_stale`; `startup()` calls `jira_store.ensure_schema()`; `cache_ttl` still from config |
| `app/static/js/jira.js` | MODIFIED | Persistent sidebar + `this._store` + dirty flags (replace `createTabs` re-render); new Insights view; Notification permission toggle; badge consumption |
| `app/static/js/core.js` | MODIFIED (small, additive) | `setPluginBadge(pluginId, count)` helper; non-breaking |
| `app/plugins/jira_tracker.db` | **NEW (generated)** | WAL SQLite mirror; git-ignored |

---

## Suggested Build Order

Dependencies drive the order. The store is the foundation; UI and insights build on top of it.

**Phase A — Storage foundation (`jira_store.py`)**  ⬅ lowest risk, highest leverage
- Schema, `_get_db` (WAL), `_db_lock`, `_ensure_schema`, upsert/get worklogs + assigned, `cache_meta`, `non_working_days` table.
- Wire `JiraTrackerPlugin.startup()` → `jira_store.ensure_schema()`.
- *No UI change yet.* Can be validated with a tiny script hitting `upsert`/`get`.

**Phase B — Read-through cache integration (modify `jira_tracker.py`)**
- Refactor `/worklogs/weekly` and `/assigned` to call `jira_store` read-through.
- Replace in-memory `_wl_cache` with store; keep `cache_ttl_minutes` semantics.
- Invalidations on `POST/PUT/DELETE /worklog` and `/meeting` → `mark_stale`.
- Add **stale-serve** (return persisted rows + `stale:true` on Jira failure).
- Add in-flight guard (Pattern 4).
- *Now restarts are instant; backend is Jira-free on warm cache.*

**Phase C — Insights engine (backend)**  ⬅ can start in parallel with B after A lands
- `compute_insights()` pure function over stored rows + `non_working_days`.
- `/api/jira/insights?week_of=` (full detail) and `/api/jira/insights/summary` (just `gap_count`).
- `non_working_days` CRUD endpoints + config for `daily_target_hours`.

**Phase D — Frontend persistent layout + shared store (modify `jira.js`)**
- Replace `createTabs` re-render with persistent sidebar + `this._store` + dirty flags.
- One shared auto-refresh interval for the plugin; reads through backend (which now hits SQLite, not Jira).
- *Tab switching is now instant and offline-tolerant.*

**Phase E — Insights tab UI**
- Render insights (missing days, low days, week-vs-target bar, gap seconds).
- Gap-fill quick actions: "log hours for missed day" / "top up short week" (reuse existing worklog POST, then `mark_stale` + dirty).
- Non-working-day marker UI (click a day → mark holiday).
- *Depends on C (data) + D (layout).*

**Phase F — Notifications + badge**
- `setPluginBadge` in `core.js`; nav dot driven by `/insights/summary`.
- In-app Insights tab badge.
- Notification permission flow (Config/Insights toggle) + fire on gap detection; graceful fallback when no secure context.
- *Depends on C (knows gaps) + D (layout) + small core.js change.*

> **Vertical-slice note:** A+B is a complete, shippable "instant reload" slice on its own (no new UI features, just speed + durability). C→F are the insight/notification layer and can follow as a second slice. Recommend landing A+B first to de-risk the cache before building UI on top of it.

---

## Open Questions / Gaps

- **Secure context for Notifications:** Confirm whether the toolkit is served over HTTPS or only `http://hostname` on the LAN. If HTTP-only, OS notifications won't fire and the badge+toast is the real UX. (MEDIUM confidence — based on Web platform spec; verify deployment.)
- **Auto-refresh vs. Jira rate limits:** Need to confirm Jira Cloud rate limits for the per-issue `/worklog` fan-out at the team's scale; the in-flight guard + TTL mitigate but a background-sync model (like `doc_search`) may be needed if teammate counts are large.
- **History window for insights:** Should "missing days" scan only the current week, or N past weeks? Recommend current week + optionally the previous week for Monday-morning catch-up; confirm with user.
- **Marking past non-working days:** Should users be able to back-date holiday marks (affects past-week targets)? Recommend yes (cheap, just rows), but confirm.

---

## Sources

- `app/plugins/jira_tracker.py` (existing routes, in-memory cache, Jira fetch logic) — **read, authoritative**
- `app/static/js/jira.js` (current tab re-render behavior, shared `_assignedCache`) — **read, authoritative**
- `app/static/js/core.js` (`createTabs` wipes `body.innerHTML` on activate — root cause) — **read, authoritative**
- `app/plugins/doc_search.py` (reference pattern: `DB_PATH`, WAL, `_db_lock`, `_ensure_schema`, `asyncio.to_thread`, `startup()`) — **read, authoritative**
- `app/plugins/base.py` (`ToolkitPlugin` lifecycle: `register_routes`/`startup`/`shutdown`) — **read, authoritative**
- `.planning/PROJECT.md` (M4 goal, SQLite+WAL+`asyncio.to_thread` convention, "Jira authoritative / local read-only mirror") — **read, authoritative**
- Web Notifications API secure-context requirement — **training knowledge, flagged MEDIUM confidence** (verify deployment's scheme)

---
*Architecture research for: Jira Tracker rework (M4) — local cache, seamless tabs, notifications, insights*
*Researched: 2026-07-13*
