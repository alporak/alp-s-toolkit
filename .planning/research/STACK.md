# Stack Research

**Domain:** Jira Tracker rework — local SQLite persistence (read-through cache), browser notifications, seamless cross-tab frontend state. Existing FastAPI + vanilla-JS plugin; only NEW-capability stack is in scope.
**Researched:** 2026-07-13
**Confidence:** HIGH

## Executive Summary

The single most important finding is that **no new Python dependency is required for any of the three features.** Everything the milestone needs already exists in this repository's stack and conventions:

1. **Local SQLite cache** — the `doc_search` and `competence` plugins already implement the exact pattern this plugin must adopt: a per-plugin `sqlite3` file opened with `check_same_thread=False`, `PRAGMA journal_mode=WAL`, `conn.row_factory = sqlite3.Row`, a `threading.Lock()` to serialize writes, and **all blocking I/O run through `asyncio.to_thread()`**. The Jira plugin should copy this verbatim into `jira_tracker.py` using a new `jira_tracker.db` co-located with the module. `sqlite3` is stdlib — zero added packages.

2. **Eliminating the event-loop-blocking risk** — the current plugin calls `requests` and the `jira` library (v3.10.5, synchronous, no async API) *directly inside async route handlers*. This is the latent bug the milestone must fix. The correct, lowest-risk fix is **not** to migrate to `httpx` async (the `jira` library has no async surface, so it would still need `to_thread` anyway), but to **wrap every existing blocking Jira/`requests` call in `asyncio.to_thread()`** — exactly the rule `doc_search` already follows. This removes the risk with near-zero rewrite.

3. **Browser notifications** — use the native **Notification API** (no library). Critical caveat from MDN: it is a *secure-context-only* feature (HTTPS). This internal toolkit is often served over plain HTTP on the LAN, where `Notification` is `undefined` and the constructor throws. The stack must therefore **feature-detect** (`"Notification" in window && window.isSecureContext`) and **degrade to the existing `toast()`** when unavailable. We do **not** adopt service-worker / persistent notifications — they require HTTPS + a registered SW and buy nothing for a tool that only notifies while a tab is open.

4. **Cross-tab state** — the friction ("re-fetch on tab open") is caused by `createTabs` re-rendering the tab body and `_loadWeekly`/`_renderAssigned` always hitting the API. The fix is two layers, both dependency-free: (a) **module-level JS memory** as the hot cache (already partially present via `this._cfg` / `_assignedCache`) — stop re-fetching on every render, fetch only on TTL expiry or `force_refresh`; (b) **`localStorage` + the `storage` event** for true cross-*tab* sharing. MDN confirms the `storage` event fires in *all other* tabs on the same origin but **not** the tab that made the change — precisely the cross-tab invalidation signal we need. We explicitly **reject IndexedDB** (async, overkill for a week of worklogs, and forbidden by the "no npm" constraint) and **reject any npm state library** (localforage/idb).

A periodic **backend background sync is NOT recommended** for v1. The frontend already runs a `setInterval` auto-refresh, and the read-through cache (populate-on-miss) already delivers "instant on restart." A background task adds write-contention risk, shutdown-cancellation complexity, and overlapping-with-request-update races for marginal benefit. Add it later only if user testing shows cold-start latency is unacceptable.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python `sqlite3` (stdlib) | Python 3.10+ (bundled) | Local read-through cache for worklogs + assigned tickets, survives restarts | Already the established pattern in `doc_search.py`/`competence.py`; zero new deps; WAL gives concurrent readers + safe crash recovery on Windows. Jira remains the source of truth — this is a READ-ONLY mirror. |
| `asyncio.to_thread()` | Python 3.9+ (bundled) | Run all blocking Jira/`requests`/`sqlite3` calls off the event loop | Hard constraint in PROJECT.md ("All blocking I/O via asyncio.to_thread() — never on event loop (Windows SQLite safety)"). This is what converts the current sync `requests`/`jira` calls from a latent bug into a safe pattern. |
| `requests` (existing) | already in requirements.txt (unpinned) | Jira REST calls (`_api()` helper) | Already used; keep it. Wrap in `to_thread`. No reason to migrate. |
| `jira` (pycontribs/jira) | **3.10.5** (Context7-verified) | `JIRA()` client + `search_issues` | Already used; synchronous-only library (no async API). Keep, wrap in `to_thread`. Do not replace. |
| Notification API (browser std) | — (Baseline: limited availability / secure-context only, per MDN 2026-05-25) | Toggleable browser notifications on gap detection | Native, no library, no npm. Non-persistent `Notification()` constructor is sufficient for an always-open internal tab. |
| `localStorage` + `storage` event (browser std) | — (Baseline: widely available, MDN 2025-05-02) | Cross-tab shared state + cache invalidation signal | `storage` event fires in *other* tabs on the same origin — the exact cross-tab sync primitive. Synchronous, simple, survives reload. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `threading.Lock()` (stdlib) | — | Serialize SQLite writes (`check_same_thread=False`) | Mirror `doc_search`'s `_db_lock`. Mandatory whenever >1 thread may write the same connection. |
| `json` (stdlib) | — | Serialize worklog/assigned rows to/from SQLite `TEXT` columns if storing as blobs, or pass row tuples directly | Use native rows (`sqlite3.Row`) for query results; `json.dumps` only for the `cache_meta` value store. |
| `toast()` (core.js, existing) | — | Fallback notification when `Notification` is unavailable (non-secure context) | Call instead of `new Notification()` whenever `"Notification" in window && window.isSecureContext` is false. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Existing `pytest` + `tests/` | Unit-test the read-through cache (miss → Jira fetch via `to_thread` → SQLite upsert → hit) | Mock the `to_thread` Jira call; assert SQLite row after. Reuse `tests/` layout from M1/M3. |
| `sqlite3` CLI (or `DB Browser for SQLite`) | Inspect `jira_tracker.db` during dev | WAL produces `-wal`/`-shm` sidecar files; don't panic — that's expected. |

## Installation

**No new packages to install.** `sqlite3` and `asyncio` are stdlib; `requests`, `httpx`, and `jira` are already in `requirements.txt`. The only "installation" step is creating the DB file at first run via an `_ensure_schema()` call in `startup()` (mirroring `doc_search`):

```python
# In jira_tracker.py — copy the doc_search convention exactly
import sqlite3, asyncio, threading, os

DB_PATH = os.path.join(os.path.dirname(__file__), "jira_tracker.db")
_db_lock = threading.Lock()

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

# All callers from async routes MUST use:  await asyncio.to_thread(_blocking_fn, ...)
```

If (and only if) you want to pin the `jira` package to a known-good version, add to `requirements.txt`:

```text
jira==3.10.5   # currently unpinned; pin to avoid silent upstream breakage
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Wrap existing `requests`/`jira` in `asyncio.to_thread()` | Migrate Jira calls to `httpx.AsyncClient` | Only if you also drop the `jira` library entirely and hand-roll all Jira REST calls. Not worth it — `jira` lib has no async API, so migration is partial at best and adds rewrite risk. |
| stdlib `sqlite3` + `to_thread` (mirror `doc_search`) | `aiosqlite` | Only if you want native async DB calls. Unnecessary here — the convention is `to_thread`, and mixing in a new async DB driver diverges from every other plugin. |
| stdlib `sqlite3` + `to_thread` | `SQLAlchemy` / `peewee` ORM | Only for a schema with dozens of relational tables. This cache is 2–3 flat mirror tables; an ORM is pure overhead and breaks the established raw-`sqlite3` style. |
| `localStorage` + `storage` event | `IndexedDB` (or `idb` npm lib) | Only if cached payloads exceed ~5 MB or need structured queries. A week of worklogs is small JSON; IndexedDB's async API adds complexity for no gain, and the npm lib violates the "no frameworks/no npm" constraint. |
| `localStorage` + `storage` event | `BroadcastChannel` (alone) | Only for live in-session tab messaging without persistence. `storage` event already covers cross-tab; `BroadcastChannel` does NOT survive reload, so it can't replace localStorage as the persistence layer. Could be *added later* as a complement for instant same-session updates. |
| Native `Notification()` + `toast()` fallback | Service-worker persistent notifications | Only if you need notifications while NO tab is open and can serve over HTTPS with a registered SW. Overkill for an internal tool; requires infra the project doesn't have. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Calling `requests`/`jira` **directly inside async route handlers** | Blocks the event loop → stalls all other requests; on Windows this is the documented SQLite-corruption / latency risk | Wrap in `asyncio.to_thread()` (same as `doc_search._git_pull`) |
| `httpx` async client for Jira calls | `jira` lib is sync-only; partial migration adds a second HTTP stack and rewrite risk with no real benefit | Keep `requests` + `to_thread` |
| A new SQL ORM (`SQLAlchemy`/`peewee`) | Diverges from every other plugin's raw-`sqlite3` style; overkill for a flat mirror schema | Raw `sqlite3` + `to_thread` |
| `IndexedDB` / `idb` npm package | Async complexity, violates "no npm" constraint, payload too small to need it | `localStorage` + `storage` event |
| Service-worker / push notifications | Requires HTTPS + SW registration the toolkit lacks; unnecessary when a tab is open | Native `Notification()` with `toast()` fallback |
| A backend **periodic background sync task** (v1) | Write-contention with request-time updates, shutdown-cancellation complexity, overlapping-update races; frontend auto-refresh already covers freshness | Read-through cache (populate on miss) + `force_refresh`; add background warm-up later only if cold-start latency is proven bad |
| `sessionStorage` for cross-tab state | `storage` event for `sessionStorage` fires only in iframes of the same tab, NOT other tabs | `localStorage` |

## Stack Patterns by Variant

**For the SQLite read-through cache (primary new backend component):**
- New `jira_tracker.db` at `os.path.join(os.path.dirname(__file__), "jira_tracker.db")` — co-located with the module, exactly like `doc_search.db` / `competence_cache.db`.
- Schema (mirror, read-only vs Jira): `worklogs_cache(account_id, issue_key, worklog_id, started_date, started_ts, time_spent_seconds, comment, ticket_summary, PRIMARY KEY(account_id, worklog_id))`; `assigned_cache(account_id, issue_key, summary, status, priority, attachment_count, has_folder, local_files, fetched_at)`; `cache_meta(key TEXT PRIMARY KEY, value TEXT)` for TTL/etag.
- `_ensure_schema()` in `startup()` with a `SCHEMA_VERSION` constant; `ALTER TABLE`/recreate on mismatch — copy `doc_search`'s `_ensure_schema` + corruption-recreate logic (it even does `os.remove(DB_PATH)` on `DatabaseError` and recreates).
- Read path (async route): `await asyncio.to_thread(_db_get_cached, key)` → if fresh (TTL vs `cache_meta`) return; else `await asyncio.to_thread(_fetch_from_jira, ...)` → `await asyncio.to_thread(_db_upsert, ...)` → return. This is what makes tab-open instant and survives restart.
- Write path (after add/edit/delete worklog): invalidate the affected cache rows via `to_thread`, exactly replacing today's `_cache_clear()` calls.

**For notifications:**
- Add `notifications_enabled: bool` to the existing Jira config (`config.load_jira_config()`), surfaced in the Config tab + a new Insights-tab toggle.
- On toggle ON: call `Notification.requestPermission()` inside the click handler (user gesture required per MDN). Store the choice.
- On gap detection (Insights engine, later phase): if `Notification.permission === "granted"` AND secure context → `new Notification("Jira: 2 days missing", { body: ... })`; else `toast(...)`.
- Feature-detect up front: `const canNotify = "Notification" in window && window.isSecureContext;` — if false, hide the toggle or label it "needs HTTPS" and rely on in-app `toast`.

**For cross-tab frontend state:**
- Keep `this._cfg`, `this._weekOffset`, and promote `_assignedCache`/`_worklogCache` to **module-level singletons** (they already persist across tab switches within one tab because the plugin object is a module singleton).
- Gate re-fetch on staleness, not on render: `_loadWeekly` should check the cache TTL and skip the API call when fresh — eliminating the "re-fetch on tab open" friction at its root (the bug is in the render function, not the cache).
- For true multi-tab sharing: on every successful fetch, write the payload + timestamp to `localStorage` under a versioned key (e.g. `jira:weekly:<weekOf>:<accountId>`). Add `window.addEventListener("storage", ...)` to re-read and re-render when *another* tab updates — MDN confirms this fires only in other tabs, so no echo loop.
- Do NOT add any npm dependency.

## Version Compatibility

| Package | Compatible With | Notes |
|-----------|-----------------|-------|
| `jira` 3.10.5 | Python 3.8+; FastAPI stack as-is | Synchronous; must be `to_thread`-wrapped. Pin it (currently unpinned in requirements.txt) to avoid upstream breakage. |
| stdlib `sqlite3` (WAL) | Python 3.7+ (WAL since 3.7) | Bundled; no install. WAL sidecar files (`-wal`,`-shm`) are expected and must not be deleted while the process runs. |
| `requests` (existing) | existing `httpx`/FastAPI stack | Unchanged; only call site moves into `to_thread`. |
| Browser Notification API | Chrome/Edge/Firefox desktop (secure context) | **Unavailable over plain HTTP** — mandatory `toast()` fallback. Throws `TypeError` on most mobile browsers (irrelevant: desktop internal tool). |
| `localStorage` / `storage` event | All modern browsers (Baseline widely available) | 5 MB origin quota — ample for a week of worklogs. |

## Sources

- `app/plugins/doc_search.py` (lines 38–164, 481, 586–673, 899–903) — authoritative existing convention: `DB_PATH` co-located, `sqlite3.connect(check_same_thread=False)`, `PRAGMA journal_mode=WAL`, `row_factory=Row`, `_db_lock = threading.Lock()`, `_ensure_schema()` + corruption `os.remove`/recreate, every blocking call via `asyncio.to_thread()`. **HIGH confidence (in-repo).**
- `app/plugins/competence.py` (lines 31, 63, 1090) — second confirming instance of the identical SQLite pattern. **HIGH confidence (in-repo).**
- `requirements.txt` — confirms `requests`, `httpx`, `jira` already present; nothing new to add. **HIGH confidence (in-repo).**
- `jira_tracker.py` (current 657-line plugin) — baseline: sync `requests`/`jira`, per-process `_wl_cache` dict, `_cache_clear()` invalidation points. **HIGH confidence (in-repo).**
- `app/static/js/jira.js` — baseline frontend: module-level `_assignedCache` (2-min TTL), `setInterval` auto-refresh, `createTabs` re-render friction, `toast()` available. **HIGH confidence (in-repo).**
- Context7 `/pycontribs/jira` — `jira` Python library current version **3.10.5**, synchronous design (no async API). **HIGH confidence.**
- Context7 `/websites/python-httpx` & `/encode/httpx` — httpx supports sync **and** async; already in stack but not needed for Jira. **HIGH confidence.**
- MDN Notifications API (last modified 2026-05-25) — `Notification()` constructor = non-persistent, page-lifetime notifications; **secure-context (HTTPS) only**; `requestPermission()` must be in a user gesture. **HIGH confidence (official docs).**
- MDN Window `storage` event (last modified 2025-05-02) — fires in **all other** same-origin browsing contexts on `localStorage` change, **not** the initiating window; Baseline widely available. **HIGH confidence (official docs).**

---
*Stack research for: Jira Tracker rework — SQLite persistence + browser notifications + seamless cross-tab UI*
*Researched: 2026-07-13*
