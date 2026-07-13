# Pitfalls Research

**Domain:** Adding local SQLite cache + browser notifications + "hours-vs-target" insights to an existing Jira time-tracking FastAPI plugin (Alps Toolkit M4)
**Researched:** 2026-07-13
**Confidence:** HIGH (most pitfalls directly evidenced in `app/plugins/jira_tracker.py` and `PROJECT.md`; platform behaviors — SQLite WAL, Notification API, TZ handling — are stable and well-established. One item flagged for a live-spike verification.)

---

## Scope Note

This research targets mistakes *specific to adding* these three features to the **existing** Jira Tracker plugin. It does **not** re-litigate the plugin's current design (that is accepted context). Every pitfall below is anchored to a line/behavior in the shipped code or a documented toolkit constraint. Where a pitfall depends on behavior we cannot read from source (e.g., exactly what timezone offset Jira's API returns in `started`), it is flagged for a Phase-1 spike.

Assumed M4 phase structure (reconcile with the actual ROADMAP.md when authored):
- **Phase 1 (BE foundation):** SQLite read-through cache + event-loop refactor of the Jira client.
- **Phase 2 (FE redesign):** Persistent sidebar, tab state kept alive, shared in-memory store, no re-fetch on tab switch.
- **Phase 3 (Notifications):** In-app Insights tab + toggleable browser Notification API + tab-bar badge.
- **Phase 4 (Insights engine):** Week math, target calculation, configurable non-working-day marking.
- **Phase 5 (Gap-fill tools):** Quick log / top-up actions.

---

## Critical Pitfalls

### Pitfall 1: Cache treated as source of truth (stale-mirror divergence)

**What goes wrong:**
The SQLite store is meant to be a *read-only mirror* of Jira (PROJECT.md: "SQLite-backed local persistence… read-only mirror of Jira"). The failure mode is code that, after a successful POST/PUT/DELETE to Jira, *writes the optimistic result directly into the cache* (e.g., insert the new worklog row locally) instead of invalidating and letting the next read re-fetch. If the local insert and the remote state ever disagree (clock skew, Jira rounding `timeSpentSeconds`, the worklog landing on a different issue than requested), the cache becomes the authority and the divergence is permanent until TTL.

**Why it happens:**
Optimistic local updates feel faster ("instant" UI) and it's tempting to reuse the request payload as the cache row.

**How to avoid:**
- Enforce a single rule: **the cache is populated *only* by a successful Jira fetch, never by a write payload.** On a successful worklog add/edit/delete, *invalidate* the affected key(s) and return fresh data or signal the client to refetch.
- Make the cache layer a pure read-through function: `get(key) -> miss ? fetch_from_jira() -> store() -> return : return stored`. Never expose a `put_after_write()` path.
- Add an integration test that asserts: after a simulated Jira write, the cache row for that week is *absent* (or stale-flagged), not updated.

**Warning signs:**
- Code contains `INSERT`/`UPDATE` into the worklog cache outside the fetch path.
- After adding a worklog, the returned `cached: true` for the same week.

**Phase to address:** Phase 1 (cache layer contract).

---

### Pitfall 2: Over-broad invalidation → cache stampede / cross-user blowout

**What goes wrong:**
The current code calls `_cache_clear()` (full module dict wipe, lines 533/553/564/571) on *every* write. With a persistent SQLite cache this is worse than wasteful:
- A full `DELETE FROM worklog_cache` means the next read of *any* open week or *any* teammate re-fetches from Jira simultaneously → thundering herd when the user has several weeks/teammates loaded.
- Clearing teammate data when *I* log a worklog is incorrect scoping (teammate weeks didn't change).

**Why it happens:**
The in-memory dict made a full clear cheap; the pattern was carried over blindly to a DB-backed cache.

**How to avoid:**
- Invalidate by **(account_id, week_monday)**, not globally. Key the cache table on `account_id` + `week_start` (and a `date_from`/`date_to` range column for the raw fetch).
- On a write for account `A` affecting week `W`, delete only rows where `account_id = A AND week_start = W`. If a worklog's date is edited across a week boundary, invalidate *both* old and new weeks.
- Keep a `force_refresh` path that invalidates a single key (already exists at line 454). Never expose a global clear to normal writes; reserve global clear for an explicit user action / config change (as today).

**Warning signs:**
- A write handler calls a "clear all" function.
- After one log, the network tab shows Jira refetches for weeks the user isn't even looking at.

**Phase to address:** Phase 1 (cache keying + scoped invalidation).

---

### Pitfall 3: Event-loop blocking from the existing synchronous Jira client

**What goes wrong:**
Every route handler calls `_api()` (line 91, `requests`) or `_jira()` (line 31, the `jira` library) **synchronously inside `async def`** (e.g., lines 298, 353, 430, 457, 530). These block the entire FastAPI event loop. PROJECT.md is explicit: *"All blocking I/O via `asyncio.to_thread()` — never on event loop (Windows SQLite safety)"* and *"All DB writes through `asyncio.to_thread()`."* The Jira plugin currently **violates the toolkit's own hard rule.** Once you add SQLite reads/writes on the same loop, a blocked loop + SQLite on Windows is exactly the corruption scenario the toolkit already documented (Key Decision #53).

**Why it happens:**
The plugin predates the toolkit's `asyncio.to_thread` convention (it's M1-era code); the rule was enforced on later plugins (doc_search) but never retrofitted here.

**How to avoid:**
- Wrap **every** blocking call in `await asyncio.to_thread(...)`: the `_api()` HTTP call, the `_jira().search_issues()` call, and **all** SQLite operations (open/query/commit).
- Do not share a single module-global `_jira_client` across threads without a lock, or better: create the client lazily per-thread (the `jira` client is not documented thread-safe). A simple `functools.lru_cache` keyed by thread ident, or a `threading.Local`, avoids cross-thread reuse.
- Add a lint/CI guard or a smoke test that fails if a route handler does a sync call outside `to_thread` (or at minimum a comment contract + review checklist).

**Warning signs:**
- A `/api/jira/*` request blocks *all other* toolkit requests (e.g., doc search hangs while a Jira fetch is in flight).
- `sqlite3` "database is locked" / corruption after a slow Jira call coincides with a DB write.

**Phase to address:** Phase 1 (this is the foundation; everything else builds on it). HIGH confidence — documented constraint.

---

### Pitfall 4: Concurrent SQLite writes on Windows ("database is locked")

**What goes wrong:**
WAL mode (toolkit standard, PROJECT.md) allows many concurrent *readers* but **only one writer at a time**. With the new cache you now have multiple write sources contending: (a) a Jira fetch writing the cache after a miss, (b) an invalidation `DELETE`, (c) non-working-day metadata writes (Phase 4), (d) possibly a periodic background refresh. Two of these racing produce `sqlite3.OperationalError: database is locked`, surfacing as 500s or, worse, a half-written cache row.

**Why it happens:**
`sqlite3` connections are not thread-safe by default; spawning writers from multiple `asyncio.to_thread` tasks without serialization re-creates the exact Windows corruption risk the toolkit already flagged.

**How to avoid:**
- Open a **dedicated connection per thread** (`check_same_thread=False` only if you fully serialize access; prefer per-thread connections via a small pool or `threading.Local`).
- Set `PRAGMA busy_timeout = 5000` so a contending writer waits instead of erroring.
- Serialize *writes* through a single `asyncio.Lock` (or a write queue / executor) so only one `to_thread` write runs at a time. Reads can run freely (WAL).
- Reuse the toolkit's established `_ensure_schema()`-at-startup + WAL + auto-migration (version-bump `ALTER TABLE`) pattern (Key Decisions #56/#57) — do not reinvent.

**Warning signs:**
- Intermittent 500s with `database is locked` in logs under concurrent use.
- `PRAGMA journal_mode` not `wal` after startup.

**Phase to address:** Phase 1 (DB layer). HIGH confidence — WAL single-writer is a documented SQLite fact and the toolkit already encodes the rule.

---

### Pitfall 5: Timezone off-by-one at week boundaries (Monday local vs UTC)

**What goes wrong:**
Two coupled bugs:
1. **Date extraction ignores the offset.** Lines 229 and 508 do `w.get("started","")[:10]` — they slice the date out of the ISO string and **discard the timezone offset**. Jira's `started` carries an offset (e.g., `2026-07-13T02:00:00.000+0000` for 05:00 Baltic). If Jira returns the timestamp in UTC, a worklog physically logged at 02:00 on *Monday* Baltic is encoded as *Sunday* UTC, so `[:10]` yields Sunday → it lands in the wrong week and the Monday-week insight misses it (or a Sunday-week insight over-counts).
2. **Week boundary uses server-local naive date.** `_week_range` (lines 158-166) uses `date.today()` / `date.fromisoformat()` with no timezone — correct only if the *server* is in the user's Baltic TZ. The user is Baltic, but the rule "Monday in local TZ" must be *the user's* TZ, not wherever the process runs.

The two must use the **same** timezone or you get silent mis-bucketing.

**Why it happens:**
String-slicing a datetime is a classic shortcut that works only when the stored offset equals the desired display TZ.

**How to avoid:**
- Parse `started` as a timezone-aware `datetime` (`datetime.fromisoformat` handles the offset) and **convert to the user's local TZ before taking the date**: `date_local = started.astimezone(LOCAL_TZ).date()`. Store an explicit `date_local` column at insert time so all later math is offset-free.
- Define `LOCAL_TZ` once (e.g., `zoneinfo` from a config or default `Europe/Vilnius`) and use it for *both* `_week_range` (compute Monday/Sunday in `LOCAL_TZ`) and the per-worklog date. Do not mix naive `date.today()` with offset-aware conversion.
- Add a unit test with a known boundary case: a worklog at `2026-07-13T01:00:00+0000` (Baltic 04:00 Mon) must bucket to Monday 2026-07-13, not Sunday.

**Warning signs:**
- Total weekly hours differ between the Jira web UI and the plugin by exactly the hours of a worklog logged late/early in the day.
- Insights show "missing day" for a day the user actually logged (off-by-one at Mon/Sun edge).

**Phase to address:** Phase 1 (store `date_local`) and Phase 4 (week math must use `LOCAL_TZ`). **Flag for spike:** confirm empirically what offset Jira returns in `started` for this account (UTC vs reporter TZ) via one live `GET issue/{key}/worklog` during Phase 1 — the fix is correct regardless, but the spike confirms whether current production data already has mis-bucketed rows to backfill.

---

### Pitfall 6: Weekly target miscalculation when non-working days are marked mid-week

**What goes wrong:**
Default target is "40h/week ≈ 8h × 5 days." Marking a non-working day (holiday / PTO) should drop the target (40h → 32h for a 4-day week). The traps:
- **Wrong scaling model.** Naively computing `target = 40h × (working_days / 5)` yields `40 × 4/5 = 32h` — which *coincidentally* matches `8 × 4`, so it looks right for one day off but breaks for two (`40 × 3/5 = 24h` vs the intended `8 × 3 = 24h` — still matches)… until you realize the *correct* semantic is **per-day base × working_days**, not weekly-total scaled. They only align because base = 8 and full week = 5. The moment the per-day base is configurable (e.g., a 6h/day norm), the scaling model silently produces wrong targets. Pin the model to **`daily_target × working_days`**.
- **Hours already logged on the marked-off day.** If the user logged 8h on a day they later mark non-working, two valid interpretations exist: (a) exclude that day entirely from both target and logged (treat as 0/0), or (b) keep the logged 8h but lower the target. Mixing them ("lower target but still count the 8h") makes the week look *over* target and hides the gap.
- **Retroactive redefinition of history.** Marking a past week's day off changes that week's target. Decide whether marking is metadata applied at *query time* (recalc on read, non-destructive) or a mutation. Query-time is required so you can toggle/undo without rewriting logged hours.
- **Weekends counted as working days.** `working_days` must start from *weekdays minus weekends minus marked-off*, not raw 5.

**Why it happens:**
"40h target" is a verbal shorthand that hides the per-day base; teams implement the scaling formula and only notice the error when the base changes or a logged day is marked off.

**How to avoid:**
- Store target as **`daily_target` (default 8h) + a set of marked non-working dates**; compute `target = daily_target × (5 − weekends_in_week − marked_off_in_week)` at *query time*.
- For a marked-off day that has logged hours: **exclude it from both numerator and denominator** and surface a warning ("Day X has 8h logged but is marked non-working — hours excluded from this week's total"). Let the user decide to move/delete those hours (gap-fill, Phase 5) rather than silently counting them.
- Keep marking as metadata; never mutate stored `time_spent_seconds`. Recalculation is idempotent and reversible.
- Unit-test: mark Thu+Fri off a 40h week with 8h logged Mon–Wed → target 24h, logged 24h, "on target." Mark a day that has 8h logged → warning + that day excluded.

**Warning signs:**
- A 4-day week shows target 40h (forgot to subtract) or 24h when base should be 8×4=32 (wrong scaling).
- "On target" weeks where the user actually took a day off and logged nothing — false negatives.

**Phase to address:** Phase 4 (insights engine — this is its core logic). HIGH confidence on the modeling pitfall; the chosen interpretation (exclude day from both sides) should be confirmed against the product spec.

---

### Pitfall 7: Notification spam (state-transition vs every-render)

**What goes wrong:**
Notifications fire on every insights recompute / every poll / every tab open instead of on *change*. Concretely: opening the Insights tab recomputes gaps and re-notifies "You have a missing day" every time → the user disables notifications entirely within a day. The badge also flickers if recompute runs on a timer.

**Why it happens:**
It's easier to "notify current gaps" than to track what was already notified.

**How to avoid:**
- Notify **only on state transitions**: a gap *appears* (new missing day / week drops below target) or *clears* (user logs the hours). Track a per-gap signature (e.g., `f"{account_id}:{week}:{gap_type}"`) of currently-active gaps; diff against last notification set; emit only the delta.
- **Throttle / dedupe:** one notification per gap signature until it clears. Don't re-notify the same gap on refresh.
- **Only use the OS Notification API when the page/tab is not focused** (the platform best practice — a visible page should use the in-app badge + Insights tab, not a toast). If `document.visibilityState === 'visible'`, suppress the browser notification and rely on the badge.
- Respect the toggle: browser notifications default **off**; the in-app badge + Insights tab are always available.

**Warning signs:**
- Opening the tab 3× produces 3 "missing hours" toasts.
- Notification history fills with duplicates of the same gap.

**Phase to address:** Phase 3 (notification engine). HIGH confidence — standard web-notification UX.

---

### Pitfall 8: Permission-denial handling for the Notification API

**What goes wrong:**
`Notification.requestPermission()` returns `"granted"`, `"denied"`, or `"default"` (user dismissed without choosing). Failure modes:
- Calling `requestPermission()` **on page load** (not from a user gesture) → browsers block/ignore it and it trains the user to ignore prompts. After a `"denied"`, repeated re-prompts are futile and annoying (the browser will not re-show it).
- Treating `"default"` (dismissed) the same as `"denied"` → prematurely hiding the feature.
- Showing the browser-notification toggle as enabled when permission is actually `"denied"` → clicking it does nothing and the user thinks it's broken.

**Why it happens:**
Permission is requested at the wrong moment and the three states aren't distinguished.

**How to avoid:**
- Call `requestPermission()` **only from the toggle's click handler** (a user gesture). Never on load.
- Persist the resolved state. If `"denied"`: hide/disable the browser-notification toggle, show "Enable notifications in your browser settings" hint, and fall back to the in-app badge + Insights tab only.
- Treat `"default"` as "not yet decided" — keep the toggle available but don't assume granted.
- Feature-detect `Notification` existence (older/locked-down browsers) before offering the toggle at all.

**Warning signs:**
- Console shows "Notification permission request ignored because not triggered by user gesture."
- Toggle is on but no toasts ever appear (silent deny).

**Phase to address:** Phase 3. HIGH confidence — documented browser behavior (MDN Notification API).

---

## Secondary Pitfalls (still phase-owned, lower blast radius)

### Pitfall 9: Caching a failed/empty Jira fetch as "no worklogs"

**What goes wrong:**
`_fetch_worklogs_for_user` (lines 211-215) returns `[]` on `JIRAError`. If the new cache stores that `[]`, a *transient* Jira 503 becomes "you logged nothing this week" — persisted until TTL, polluting insights ("missing week" false positive) and gap-fill suggestions.

**Why it happens:**
`[]` is ambiguous: a valid empty week vs. a fetch failure.

**How to avoid:**
- Never cache a failed fetch. Distinguish: on `JIRAError`/non-OK, return an error / fall back to stale cache, but **do not write** the empty result.
- Only write cache on a successful, fully-parsed response. Mark cache rows with a `fetched_at` so staleness is explicit.
- On read miss *and* fetch failure, return HTTP 502/error to the client rather than a misleading empty list.

**Warning signs:** Insights claim "0h logged" during a Jira outage. **Phase:** Phase 1.

---

### Pitfall 10: Write-succeeds / cache-insert-fails race

**What goes wrong:**
Jira write succeeds (200), you invalidate, then the re-fetch-and-store into SQLite fails (locked/disk). The cache now has *no* row for that week, so the next read treats it as a permanent miss and re-fetches — wasting calls and, if the re-fetch also fails, showing empty.

**Why it happens:** Invalidation and repopulation are two separate steps; only one is guarded.

**How to avoid:**
- Make cache insert **non-fatal**: on insert failure, log and leave the key *absent* (forcing a re-fetch on next read) rather than writing a partial/empty row. Never write an empty placeholder that looks like "valid empty."
- Consider returning the fresh Jira payload directly from the write handler (don't depend on the cache for the immediate response), and let the background cache-populate be best-effort.

**Warning signs:** After logging, the week shows empty until a manual force-refresh. **Phase:** Phase 1.

---

### Pitfall 11: TTL used as primary freshness instead of invalidation

**What goes wrong:**
Plan mentions "smart refresh / TTL / force-refresh." If the implementation leans on a 5-min TTL as the primary freshness mechanism, a user who just logged hours (gap-fill, Phase 5) sees stale data for up to 5 minutes, undermining the "instant" promise and making notifications lag.

**Why it happens:** TTL is easy; write-time invalidation is extra plumbing.

**How to avoid:**
- Make **write-time invalidation the primary** freshness path (Pitfall 2). TTL is only a *safety net* for changes made outside this tool (e.g., Jira web UI, another user).
- "Smart refresh" = don't auto-refresh while the user is mid-edit (Phase 2/5); refresh on tab *focus* if the cached row is older than TTL, and always refresh on an explicit user action.
- Keep TTL short (e.g., 2–5 min) given it's a fallback.

**Warning signs:** User logs hours, badge still shows the gap for minutes. **Phase:** Phase 1 (policy) + Phase 2 (refresh trigger).

---

### Pitfall 12: Frontend shared store goes stale after a backend mutation

**What goes wrong:**
Phase 2 keeps tab state alive in a shared in-memory store "no re-fetch on tab switch." But a write (add/edit/delete, Phase 5) or an invalidation must propagate to that store, or the UI shows pre-write data after the user logs hours. The "no re-fetch" optimization collides with "show fresh data after I log."

**Why it happens:** The store was designed to *avoid* fetches; it wasn't given an invalidation channel.

**How to avoid:**
- The write response (or a returned invalidation signal) must update/evict the specific week in the frontend store immediately. "No re-fetch on tab switch" ≠ "never refresh after a mutation."
- Centralize store mutations behind a `invalidateWeek(accountId, week)` that both drops the cached payload and (if that week is visible) triggers one targeted refetch.

**Warning signs:** After logging, switching tabs shows old hours until a full reload. **Phase:** Phase 2 (store design) + Phase 5 (calls invalidate).

---

### Pitfall 13: Per-account cache scoping collision ("me" vs teammates)

**What goes wrong:**
The cache must key by `account_id` so caching "me" doesn't overwrite a teammate's week and invalidating "me" doesn't nuke teammate data (Pitfall 2). The existing `_cache_clear(account_id)` scopes by prefix, but the SQLite schema must preserve `account_id` as a first-class key column, and the `is_me` detection (lines 448-452) must not cause double storage of the same person under two keys.

**Why it happens:** Easy to key only by week and let "me" and teammates collide.

**How to avoid:**
- Primary key `(account_id, week_start)`. Compute `is_me` once and store under the real `account_id` consistently.
- Invalidation and reads always qualify by `account_id`.

**Warning signs:** Teammate's week disappears when I log; or my week shows teammate's data. **Phase:** Phase 1.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Optimistically write the new worklog into the cache on POST | Instant UI, no refetch | Cache becomes authority; divergence from Jira is silent & permanent | **Never** — invalidate + refetch instead |
| Full cache clear on every write (carryover from in-memory dict) | One line of code | Cache stampede; cross-user blowout on SQLite | Never in DB-backed cache; scope by key |
| Keep `requests`/`jira` sync calls on the event loop | No refactor of M1 code | Blocks whole toolkit; SQLite corruption risk on Windows | Never — `asyncio.to_thread` is a documented hard rule |
| Use `started[:10]` string slice for date | Avoids datetime parsing | TZ off-by-one at week edges; mis-bucketed insights | Never once TZ-aware parse is in place |
| Treat `[]` fetch result as cacheable | Simpler cache path | Transient outage → false "0h logged" insights | Never — only cache successful fetches |
| Scale weekly target (`40 × days/5`) instead of `daily × days` | Matches 8×5 by accident | Wrong as soon as daily base ≠ 8 or week ≠ 5 days | Never — use per-day base model |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Jira REST `worklog` API | Storing `started` as the raw ISO string and slicing `[:10]` for the date | Parse with offset, convert to `LOCAL_TZ`, store `date_local` |
| Jira write (`POST/PUT/DELETE worklog`) | Writing `+0000` (UTC) while intending a local day → day shift | Send `started` with the user's local offset (or the existing noon-UTC hack consistently) so Jira records the intended local day |
| Jira as cache upstream | Trusting cache after a write without re-fetch | Invalidate key on successful write; repopulate on next read |
| SQLite (Windows) | Opening one global connection shared across `to_thread` tasks | Per-thread connections + `busy_timeout` + serialized writes (`asyncio.Lock`) |
| Browser Notification API | Requesting permission on page load / re-prompting after deny | Request only on toggle click; persist state; degrade to in-app badge on deny |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-cache-clear stampede | After one log, many simultaneous Jira refetches; API rate-limit hits | Scoped invalidation by `(account_id, week)` | With >1 week or >1 teammate loaded |
| Cache-as-truth divergence | Insights drift from Jira UI; "ghost" worklogs | Read-through only; never write-from-payload | Immediately on first missed invalidation |
| Unbounded cache growth | SQLite file grows; slow queries | TTL + periodic prune of old weeks; index on `(account_id, week_start)` | After months of daily use |
| Blocking Jira call on event loop | All toolkit endpoints freeze during a slow Jira call | `asyncio.to_thread` for every blocking call | Any Jira latency spike (>1s) |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing Jira token in the cache DB | Token leakage if DB file copied | Cache stores only worklog *mirror* data; token stays in `config` (existing). Never echo `api_token` in `/api/jira/config` response (already returns `""` at line 268 — keep it that way) |
| Notification permission requested without gesture | Browser console errors; user distrust | Request only from toggle click |
| `os.startfile` / path handling on ticket folders | (Existing, not new) — unchanged by M4 | No new surface; keep existing `re.match(r"^[\w-]+$")` sanitization (line 621) |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Notify while tab is visible | Annoying duplicate of what's on screen | Suppress OS toast when `visibilityState === 'visible'`; use badge |
| Badge never clears | User thinks gaps remain after fixing | Clear badge on gap-state transition to empty; recompute after mutation |
| "On target" despite a marked-off day with logged hours | False reassurance | Exclude marked-off day from both sides + show warning |
| Stale UI after logging (shared store not invalidated) | User re-logs or thinks it failed | Invalidate the week in the store on write response |
| Browser notification toggle looks enabled but is denied | Dead control, user confusion | Disable/hide toggle + "enable in browser settings" hint when `"denied"` |

---

## "Looks Done But Isn't" Checklist

- [ ] **Cache:** Verify cache is populated *only* by fetches, never by write payloads (Pitfall 1).
- [ ] **Cache:** Verify a write invalidates only the affected `(account_id, week)`, not the whole table (Pitfall 2).
- [ ] **Event loop:** Verify no synchronous `requests`/`jira`/SQLite call runs outside `asyncio.to_thread` (Pitfall 3).
- [ ] **SQLite:** Verify `journal_mode=wal`, `busy_timeout` set, writes serialized (Pitfall 4).
- [ ] **Timezone:** Verify a boundary worklog (e.g., 02:00 local Mon = 23:00 UTC Sun) buckets to the correct local day/week (Pitfall 5).
- [ ] **Target:** Verify marking 1 non-working day drops a 40h target to 32h, and a day with logged hours marked off is excluded + warned (Pitfall 6).
- [ ] **Notifications:** Verify OS toast fires only on gap *transition* and only when tab hidden (Pitfall 7).
- [ ] **Permissions:** Verify `"denied"` hides the toggle and falls back to badge; request only on click (Pitfall 8).
- [ ] **Error caching:** Verify a Jira 5xx does **not** cache an empty `[]` (Pitfall 9).
- [ ] **Frontend store:** Verify logging hours updates the shared store without a full reload (Pitfall 12).

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Cache divergence (Pitfall 1) | LOW | Add scoped invalidation; run one force-refresh per affected week; backfill by re-fetch |
| Stale/mis-bucketed TZ rows (Pitfall 5) | MEDIUM | Recompute `date_local` from raw `started` (offset-aware) via a one-off migration; re-bucket |
| "database is locked" corruption (Pitfall 4) | MEDIUM–HIGH | Restore from WAL/auto-recover (toolkit `_ensure_schema` at startup); add write serialization to prevent recurrence |
| False "0h" from cached error (Pitfall 9) | LOW | Flush cache for affected week; fix to not cache failures |
| Notification permission denied (Pitfall 8) | LOW | UI falls back to badge; instruct user to re-enable in browser settings |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 — Cache-as-truth | Phase 1 | Test: after write, cache row absent, not updated |
| 2 — Over-broad invalidation | Phase 1 | Test: write invalidates only `(account_id, week)`; no refetch of other weeks |
| 3 — Event-loop blocking | Phase 1 | Smoke: concurrent toolkit requests not blocked during Jira call |
| 4 — Concurrent SQLite writes | Phase 1 | Load test: concurrent writes → no `database is locked` |
| 5 — TZ week-boundary | Phase 1 (store `date_local`) + Phase 4 (week math) | Unit test on boundary timestamp |
| 6 — Target miscalc | Phase 4 | Unit test: 4-day week = 32h; marked-off logged day excluded + warned |
| 7 — Notification spam | Phase 3 | Test: only transition deltas notify; no toast when visible |
| 8 — Permission denial | Phase 3 | Test: denied → toggle hidden + badge fallback; request only on click |
| 9 — Caching failures | Phase 1 | Test: Jira 5xx → no empty cache row |
| 10 — Write/insert race | Phase 1 | Test: insert failure leaves key absent, forces refetch |
| 11 — TTL as primary | Phase 1/2 | Test: write invalidates immediately; TTL only fallback |
| 12 — Stale frontend store | Phase 2/5 | Test: log → store updates without reload |
| 13 — Account scoping | Phase 1 | Test: teammate/week isolation |

---

## Sources

- `app/plugins/jira_tracker.py` (lines cited): synchronous `_api`/`_jira` calls in `async def` handlers (91-93, 212, 223, 298, 353, 430, 457, 530); in-memory full-clear cache (44-79, 533/553/564); `started[:10]` date slice (229, 508); `_to_jira_datetime` UTC `+0000` (149-155); naive `_week_range` (158-166); `api_token` never echoed (268).
- `PROJECT.md` (Alps Toolkit): "All blocking I/O via `asyncio.to_thread()` — never on event loop (Windows SQLite safety)" (Key Constraints #5, Key Decisions #53/#56/#57); SQLite WAL + per-plugin DB + `_ensure_schema` recovery; M4 goal statement (local persistence as "read-only mirror of Jira," insights target recalc).
- Platform-stable behavior (no live verification required, but flagged where ambiguous): SQLite WAL single-writer + `busy_timeout` (sqlite.org); MDN Notification API `requestPermission()` states (`granted`/`denied`/`default`) and gesture requirement; IANA `zoneinfo` / `datetime.astimezone` for TZ-correct date bucketing.
- **Flagged for live spike (Phase 1):** exact timezone offset Jira returns in `started` for this account (UTC vs reporter TZ) — confirm via one real `GET issue/{key}/worklog` call; the recommended fix (offset-aware parse → `LOCAL_TZ` → `date_local`) is correct regardless.

---
*Pitfalls research for: Alps Toolkit M4 — Jira Tracker cache + notifications + insights*
*Researched: 2026-07-13*
