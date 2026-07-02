# Phase 3: Backend Enhancements — Extended Data Model & APIs - Research

**Researched:** 2026-06-17
**Domain:** Python/FastAPI backend, Jira REST API integration, SQLite analytics, Plotly visualization
**Confidence:** HIGH

## Summary

Phase 3 rewrites `app/plugins/competence.py` (593 lines) with an extended data model that captures per-transition attribution (who returned, from/to statuses), adds a `tickets` table for issue metadata, and exposes four new API endpoints. The M1 codebase provides a working state-machine pattern, SQLite storage, and async Jira sync pipeline — all of which can be retained and extended rather than replaced. The rewrite focuses on three areas: (1) richer `_parse_changelog` output with author and status fields, (2) sync job extension to fetch `summary`+`issuetype` from Jira search and upsert ticket metadata, and (3) new aggregate/summary/timeline endpoints.

The user has made an explicit architectural decision to use DROP+CREATE in `startup()` rather than migration, since M1 data was not production data and the sync job refetches everything from Jira on first run. This simplifies the implementation significantly — REQUIREMENTS.md FR7.3's migration requirement is overridden by this decision.

**Primary recommendation:** Retain the existing module structure and patterns; extend `_parse_changelog` to capture 4 new fields; modify `_sync_job` to fetch ticket metadata via `search_issues(fields="key,summary,issuetype")`; add 4 new FastAPI route handlers; replace `startup()` DDL with DROP+CREATE.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Jira data fetch (search, changelogs) | API / Backend | — | All Jira REST API calls run server-side with stored credentials |
| State machine / changelog parsing | API / Backend | — | Pure data transformation; no UI or persistence logic |
| SQLite persistence (transitions, tickets) | Database / Storage | — | Local WAL-mode SQLite; no external DB |
| Aggregation queries (stats, tickets, summary) | API / Backend | Database / Storage | Queries formulated in Python/pandas, executed against SQLite |
| Plotly chart rendering (rate, volume) | API / Backend | — | Server-side HTML generation returned to browser |
| Sync orchestration (background task) | API / Backend | — | `asyncio.create_task` within FastAPI lifespan |
| Frontend API consumption | Browser / Client | — | Not in Phase 3 scope; Phase 4 consumes these endpoints |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| jira | 3.10.5 | Jira REST API wrapper (search_issues, myself) | Already in use by release_creator.py and jira_tracker.py; handles BasicAuth, pagination, field selection |
| httpx | 0.28.1 | Async HTTP client for changelog REST API | Already in use; async-native; faster than requests for concurrent changelog fetching |
| pandas | 2.1.1 | DataFrame-based aggregation for stats/charts | Already in use; 2Q grouping via `pd.Grouper(freq="2Q")` proven pattern |
| plotly | 6.6.0 | Server-side chart HTML generation | Already in use; `go.Figure` + `fig.to_html(include_plotlyjs="cdn")` pattern; supports dual-bar charts natively |
| fastapi | 0.135.1 | Web framework, route decorators | Already in use; route handlers defined inside `register_routes()` |
| sqlite3 | stdlib | Local WAL-mode database | Already in use; zero-config; sufficient for single-user analytics |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio | stdlib | Background tasks, semaphores, to_thread | Concurrency limiting (Semaphore(5)), async wrappers for sync DB ops |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx for changelog | jira package `issue.changelog` | jira package changelog access requires fetching full Issue object (heavy); httpx gives direct REST control with pagination |
| pandas for aggregation | Raw SQL GROUP BY | pandas is already loaded for charts; using it for stats avoids dual SQL+pandas code paths |
| Migration (ALTER TABLE) | DROP + CREATE fresh | User decision: M1 data is test data, sync refetches; simpler code, no migration bugs |

**Installation:**
No new packages required — all dependencies are already in `requirements.txt`.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| jira | PyPI | ~9 yrs | 2M+/mo | github.com/pycontribs/jira | [OK] | Approved |
| httpx | PyPI | ~5 yrs | 50M+/mo | github.com/encode/httpx | [OK] | Approved |
| pandas | PyPI | ~14 yrs | 200M+/mo | github.com/pandas-dev/pandas | [OK] | Approved |
| plotly | PyPI | ~10 yrs | 8M+/mo | github.com/plotly/plotly.py | [OK] | Approved |
| fastapi | PyPI | ~6 yrs | 30M+/mo | github.com/fastapi/fastapi | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

All packages are existing project dependencies, long-established on PyPI, and slopcheck-verified. No new packages are introduced in this phase.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                      │
│                                                             │
│  ┌──────────────┐    ┌──────────────────────────────────┐  │
│  │ Route Handlers│    │        Background Sync          │  │
│  │              │    │                                  │  │
│  │ GET /stats   │    │  _sync_job() [asyncio.create_task]│  │
│  │ GET /chart   │    │    │                              │  │
│  │ GET /chart/  │    │    ├─► jira.search_issues()      │  │
│  │      volume  │    │    │   (paginated, fields=key,    │  │
│  │ GET /tickets │    │    │    summary, issuetype)       │  │
│  │ GET /tickets/│    │    │                              │  │
│  │      {key}   │    │    ├─► httpx GET /issue/{k}/     │  │
│  │ GET /summary │    │    │   changelog (paginated,      │  │
│  │ POST /sync   │    │    │   semaphore-limited)         │  │
│  │ GET /sync/   │    │    │                              │  │
│  │      status  │    │    ├─► _parse_changelog()        │  │
│  └──────┬───────┘    │    │   (extended: author+status)  │  │
│         │            │    │                              │  │
│         ▼            │    ├─► SQLite INSERT              │  │
│  ┌──────────────┐    │    │   (dedup, upsert tickets)    │  │
│  │  pandas DF   │    │    │                              │  │
│  │  aggregation │    │    └─► update last_sync           │  │
│  └──────┬───────┘    └──────────────┬───────────────────┘  │
│         │                           │                      │
│         ▼                           ▼                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              SQLite (WAL mode)                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │  │
│  │  │ transitions  │  │   tickets    │  │sync_state │  │  │
│  │  │ (extended)   │  │              │  │ (KV store) │  │  │
│  │  └──────────────┘  └──────────────┘  └───────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Plotly Chart Renderer                    │  │
│  │  go.Figure → fig.to_html(include_plotlyjs="cdn")     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
  ┌─────────────┐              ┌──────────────────┐
  │   Browser   │              │  Jira REST API   │
  │  (Phase 4)  │              │  (Atlassian Cloud)│
  └─────────────┘              └──────────────────┘
```

### Recommended Project Structure

Phase 3 touches only one file:
```
app/plugins/
├── competence.py        # FULL REWRITE (~700 lines expected)
├── competence_cache.db  # Auto-created by startup(); DROP+CREATE on restart
└── ...
```

No new files are created. The single-file plugin pattern is consistent with all existing plugins (release_creator.py, gps_server.py, jira_tracker.py, etc.).

### Pattern 1: Module-Level Lazy-Init Singletons

**What:** Global variables initialized on first access, shared across all route handlers. Thread-safe for reads, lock-guarded for writes.

**When to use:** For resources that are expensive to create (DB connections, HTTP clients, JIRA clients) and needed across multiple request handlers.

**Existing code (lines 37-51 of competence.py) — KEEP:**
```python
# Source: app/plugins/competence.py lines 37-51
_db_lock = threading.Lock()
_http_client: httpx.AsyncClient | None = None
_jira_client: JIRA | None = None

def _get_jira_client() -> JIRA:
    global _jira_client
    if _jira_client is None:
        c = config.load_jira_config()
        _jira_client = JIRA(
            server=SERVER,
            basic_auth=(c.get("email", ""), c.get("token", "")),
        )
    return _jira_client
```

**Extend for Phase 3:** No changes needed. This pattern works correctly for the extended sync job.

### Pattern 2: Async DB Wrappers via asyncio.to_thread

**What:** Synchronous SQLite operations (which block) wrapped in `asyncio.to_thread()` to avoid blocking the FastAPI event loop.

**When to use:** For all DB reads/writes from async route handlers. The sync job also uses this pattern for `_get_jira_client().myself()` and `search_issues()`.

**Existing code (lines 93-101) — KEEP:**
```python
# Source: app/plugins/competence.py lines 93-101
async def _db_get_async(key: str) -> str | None:
    return await asyncio.to_thread(_db_get, key)

async def _db_set_async(key: str, value: str) -> None:
    await asyncio.to_thread(_db_set, key, value)
```

**Extend for Phase 3:** Add async wrappers for new DB operations (ticket upsert, extended transition insert, aggregate queries). Example:

```python
async def _db_upsert_ticket(key: str, summary: str, issue_type: str) -> None:
    await asyncio.to_thread(_db_upsert_ticket_sync, key, summary, issue_type)
```

### Pattern 3: FastAPI Route Registration Inside Plugin Class

**What:** All route handlers defined as inner functions of `register_routes(app)`, using `@app.get/post` decorators. This scopes routes to the plugin and allows access to plugin state via closure.

**When to use:** For every plugin endpoint. This is the standard pattern across all Alps Toolkit plugins.

**Existing code (lines 410-546) — KEEP:**
```python
# Source: app/plugins/competence.py lines 410-546
def register_routes(self, app: FastAPI) -> None:
    @app.get("/api/competence/stats")
    async def competence_stats():
        ...
    @app.post("/api/competence/sync")
    async def competence_sync():
        ...
```

**Extend for Phase 3:** Add 4 new route handlers following identical pattern inside the same `register_routes` block. No structural changes.

### Pattern 4: Background Sync with In-Progress Guard

**What:** Sync runs as `asyncio.create_task(_sync_job())`, with a `sync_state['in_progress']` flag preventing concurrent runs. Status reported via `/sync/status`.

**When to use:** For any long-running background data fetch that shouldn't run concurrently.

**Existing code (lines 261-396) — KEEP structure, EXTEND logic:**
```python
# Source: app/plugins/competence.py lines 261-396
async def _sync_job() -> None:
    if await _db_get_async("in_progress") == "1":
        return
    await _db_set_async("in_progress", "1")
    try:
        # ... fetch and process ...
    finally:
        await _db_set_async("in_progress", "0")
```

**Extend for Phase 3:** Add ticket metadata fetch after step 3 (Jira search), before step 4 (changelog fetching). The search already returns issue keys — just extend `fields` param and upsert results.

### Pattern 5: Semaphore-Limited Concurrent Changelog Fetching

**What:** `asyncio.Semaphore(5)` limits concurrent HTTP requests to Jira's changelog API, preventing rate-limit issues.

**When to use:** For any paginated concurrent API fetch against a rate-limited service.

**Existing code (lines 316-345) — KEEP:**
```python
# Source: app/plugins/competence.py lines 316-345
semaphore = asyncio.Semaphore(5)

async def _fetch_changelog(key: str) -> tuple[str, list[dict]]:
    async with semaphore:
        # paginated fetch via _api_get
        ...
```

**Extend for Phase 3:** No changes needed to the concurrency pattern. The changelog response structure is unchanged; only `_parse_changelog` extraction changes.

### Anti-Patterns to Avoid

- **Blocking the event loop:** Never call `sqlite3.connect()` or `_get_db()` directly in async route handlers. Always use `asyncio.to_thread()` or the async wrapper functions.
- **Missing `finally:` for `in_progress` flag:** If sync crashes without resetting the flag, future syncs are permanently blocked. The existing `try/finally` pattern must be preserved.
- **Using `jira` package for changelogs:** The `jira` package requires fetching the full Issue object to access changelog history, which is expensive. Keep using httpx with direct REST API calls for changelog pagination.
- **Schema migration complexity:** The user explicitly chose DROP+CREATE over migration. Do not implement version detection, ALTER TABLE, or data preservation logic.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Jira changelog pagination | Manual offset/limit loop | `_api_get(f"issue/{key}/changelog", maxResults=100, startAt=start)` | Already implemented; Jira REST API handles pagination reliably |
| Concurrent HTTP request limiting | Custom queue/worker pool | `asyncio.Semaphore(5)` | Already implemented; stdlib, zero-config |
| 2Q period grouping | Custom date math | `pd.Grouper(key="transition_date", freq="2Q")` | Already implemented in `_load_transitions_df`; pandas handles edge cases (year boundaries, leap years) |
| Plotly chart rendering | Manual SVG/Canvas drawing | `go.Figure` + `fig.to_html(include_plotlyjs="cdn")` | Already implemented; supports dual-bar, hover templates, responsive layout |
| SQLite thread safety | Custom locking scheme | WAL mode + `threading.Lock()` | Already implemented; WAL allows concurrent reads; lock serializes writes |
| Jira authentication | Custom OAuth/BasicAuth flow | `config.load_jira_config()` + `JIRA(basic_auth=...)` | Already implemented; consistent across all plugins that talk to Jira |

**Key insight:** The M1 codebase already demonstrates production-quality patterns for every infrastructure concern (auth, concurrency, pagination, thread safety). Phase 3 is purely about extending the data model and API surface — no new infrastructure patterns are needed.

## Runtime State Inventory

> This is a rewrite phase affecting the same file and database. Basic inventory needed since the DB schema changes.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `competence_cache.db` — 22 rows in transitions table (M1 test data), 2 rows in sync_state (last_sync, in_progress) | DROP + CREATE fresh on startup; data is non-production test data per user decision |
| Live service config | None — no external service config references competence plugin by name | None |
| OS-registered state | None | None |
| Secrets/env vars | Jira credentials in `third_party/jira-time-tracker/jira_config.json` — read by `config.load_jira_config()` | No changes needed; config access pattern unchanged |
| Build artifacts | None — Python module, no compiled artifacts | None |

**Nothing found in category:** OS-registered state — verified by `grep` across the repo for any systemd/launchd/Task Scheduler references to "competence".

## Common Pitfalls

### Pitfall 1: Sync Blocked by Stale `in_progress` Flag

**What goes wrong:** If `_sync_job()` crashes after setting `in_progress=1` but before the `finally` block resets it to `0`, all future sync attempts return "sync already running" permanently.

**Why it happens:** Python exceptions in the `try` block before the `finally` runs — especially if the exception occurs during `_db_set_async` itself.

**How to avoid:** The `try/finally` pattern at lines 274/394 is correct and should be preserved exactly. Do not add early returns between `_db_set_async("in_progress", "1")` and the `try` block.

**Warning signs:** `/sync/status` reports `in_progress: true` for >5 minutes with no sync activity in logs.

### Pitfall 2: jira Package search_issues Pagination Off-by-One

**What goes wrong:** Infinite loop or missed issues when `len(results) < maxResults` is used as the termination condition but results count equals `maxResults` exactly.

**Why it happens:** The jira package's `ResultList` length can equal `maxResults` on the last page if the total is an exact multiple of `maxResults`.

**How to avoid:** The existing pattern at lines 296-310 is correct — it extends `all_issues`, updates `start_at` with `len(results)`, and breaks when `len(results) < maxResults`. On the exact-multiple edge case, the next iteration returns 0 results and the loop still terminates correctly because `0 < maxResults`. **Keep this exact pattern.**

### Pitfall 3: `_parse_changelog` State Machine Ordering Dependency

**What goes wrong:** If changelog entries arrive out of chronological order, the `in_testing` boolean state machine can produce incorrect ATTEMPT/RETURN pairings.

**Why it happens:** Jira changelog API returns entries in reverse chronological order by default. The existing code iterates `changelog.get("values", [])` without reversing, which means processing from newest to oldest.

**How to avoid:** The current code at line 179 does NOT reverse entries. This is actually correct for the state machine's logic because it processes entries in the order they occurred (newest first means it sees the most recent RETURN first, marks `in_testing=False`, then sees earlier entries). **However**, this is fragile. For the extended parser, **consider reversing** `entries` before iteration to process oldest-first, which is more intuitive and avoids edge cases with the `in_testing` flag. The existing behavior hasn't caused issues because the simple state machine is tolerant of reverse ordering, but with the extended attribution fields, chronological processing is safer.

**Recommendation:** Reverse changelog entries before parsing:
```python
for entry in reversed(changelog.get("values", [])):
```

### Pitfall 4: Dual-Bar Chart Color Clash in Dark Theme

**What goes wrong:** The existing chart uses hardcoded `paper_bgcolor="rgba(0,0,0,0)"` and `font=dict(color="#c9d1d9")` for dark theme. A dual-bar chart needs two distinguishable colors that work on dark backgrounds.

**Why it happens:** Hardcoded colors that look good on light themes may be invisible or low-contrast on dark themes.

**How to avoid:** Use high-contrast colors tested against `#c9d1d9` text. Recommended: `#3498db` (blue) for attempts, `#e74c3c` (red) for returns. Both are already used in the M1 chart and core.js color palette.

### Pitfall 5: `/tickets` SQL Query Performance with GROUP BY

**What goes wrong:** The tickets endpoint query with subquery for `last_return_by` can cause correlated subquery performance issues on large datasets (10,000+ transitions).

**Why it happens:** SQLite executes the correlated subquery once per group row.

**How to avoid:** For the current scale (hundreds of tickets, not thousands), the simple subquery is fine. If performance becomes an issue, use a window function approach or a two-query strategy (main aggregation + separate last-return lookup). Document this as a known optimization point.

## Code Examples

Verified patterns from the existing codebase. All examples below are from `app/plugins/competence.py` (lines specified) or derived from tested patterns in other plugins.

### Extended `_parse_changelog` — Capturing Attribution

**Current code (lines 158-220) returns:**
```python
{"ticket_key": key, "transition_date": created, "action_type": "ATTEMPT"}
```

**Extended version returns:**
```python
# Source: Derived from existing pattern + REQUIREMENTS.md FR8
def _parse_changelog(
    changelog: dict,
    ticket_key: str,
    current_account_id: str,
) -> list[dict]:
    transitions: list[dict] = []
    in_testing = False

    # Process oldest-first for correct state machine ordering
    for entry in reversed(changelog.get("values", [])):
        author = entry.get("author") or {}
        author_id = author.get("accountId", "")
        author_name = author.get("displayName", "")
        created = entry.get("created", "")

        for item in entry.get("items", []):
            if item.get("field") != "status":
                continue
            from_status = item.get("fromString", "")
            to_status = item.get("toString", "")
            if not from_status or not to_status:
                continue

            if (
                from_status in ATTEMPT_FROM
                and to_status in ATTEMPT_TO
                and author_id == current_account_id
            ):
                transitions.append({
                    "ticket_key": ticket_key,
                    "transition_date": created,
                    "action_type": "ATTEMPT",
                    "author_account_id": author_id,
                    "author_display_name": author_name,
                    "from_status": from_status,
                    "to_status": to_status,
                })
                in_testing = True

            elif (
                in_testing
                and from_status in RETURN_FROM
                and to_status in RETURN_TO
            ):
                transitions.append({
                    "ticket_key": ticket_key,
                    "transition_date": created,
                    "action_type": "RETURN",
                    "author_account_id": author_id,       # QA engineer's identity
                    "author_display_name": author_name,   # QA engineer's name
                    "from_status": from_status,
                    "to_status": to_status,
                })
                in_testing = False

    return transitions
```

### Sync Job: Fetching Ticket Metadata via search_issues

**Current search (lines 296-310) fetches only keys:**
```python
# Source: app/plugins/competence.py lines 296-310
results = await asyncio.to_thread(
    _get_jira_client().search_issues,
    jql,
    maxResults=max_results,
    startAt=start_at,
    fields="key",                               # ← Change this
)
batch = [{"key": iss.key} for iss in results]   # ← And this
```

**Extended version — fetch summary+issuetype:**
```python
# Source: jira package signature verified via `inspect.signature(jira.JIRA.search_issues)`
# fields param accepts "key,summary,issuetype" comma-separated string
results = await asyncio.to_thread(
    _get_jira_client().search_issues,
    jql,
    maxResults=max_results,
    startAt=start_at,
    fields="key,summary,issuetype",             # ← Extended
)
# iss.fields.summary → string
# iss.fields.issuetype.name → string (e.g., "Bug", "Task", "Story")
batch = [{
    "key": iss.key,
    "summary": getattr(iss.fields, "summary", "") or "",
    "issue_type": getattr(iss.fields.issuetype, "name", "") if hasattr(iss.fields, "issuetype") and iss.fields.issuetype else "",
} for iss in results]
```

### Upsert Ticket Metadata

**New helper function (insert after line 101):**
```python
# Source: Standard SQLite INSERT OR REPLACE pattern
def _db_upsert_ticket_sync(key: str, summary: str, issue_type: str) -> None:
    """Synchronous upsert of ticket metadata."""
    now = datetime.now(timezone.utc).isoformat()
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO tickets
                   (ticket_key, summary, issue_type, last_synced)
                   VALUES (?, ?, ?, ?)""",
                (key, summary, issue_type, now),
            )
            conn.commit()
        finally:
            conn.close()

async def _db_upsert_ticket(key: str, summary: str, issue_type: str) -> None:
    await asyncio.to_thread(_db_upsert_ticket_sync, key, summary, issue_type)
```

### SQL for `/tickets` Aggregate Query

```sql
-- Source: Derived from REQUIREMENTS.md FR10.1 schema
-- Returns per-ticket aggregated stats with attribution
SELECT
    t.ticket_key,
    COALESCE(tk.summary, '') AS summary,
    COALESCE(tk.issue_type, '') AS issue_type,
    COUNT(CASE WHEN t.action_type = 'ATTEMPT' THEN 1 END) AS attempts,
    COUNT(CASE WHEN t.action_type = 'RETURN' THEN 1 END) AS returns,
    CASE
        WHEN COUNT(CASE WHEN t.action_type = 'ATTEMPT' THEN 1 END) > 0
        THEN ROUND(
            COUNT(CASE WHEN t.action_type = 'RETURN' THEN 1 END) * 100.0
            / COUNT(CASE WHEN t.action_type = 'ATTEMPT' THEN 1 END), 1)
        ELSE 0.0
    END AS return_rate_pct,
    MAX(CASE WHEN t.action_type = 'RETURN' THEN t.transition_date END)
        AS last_return_date,
    (SELECT tr.author_display_name FROM transitions tr
     WHERE tr.ticket_key = t.ticket_key
       AND tr.action_type = 'RETURN'
       AND tr.transition_date = MAX(CASE WHEN t.action_type = 'RETURN' THEN t.transition_date END)
     LIMIT 1) AS last_return_by
FROM transitions t
LEFT JOIN tickets tk ON t.ticket_key = tk.ticket_key
GROUP BY t.ticket_key
ORDER BY returns DESC, attempts DESC
```

### Plotly Dual-Bar Chart for `/chart/volume`

```python
# Source: Derived from existing /chart pattern (lines 479-543)
# Extended to dual-bar: attempts (blue) + returns (red)
fig = go.Figure([
    go.Bar(
        name="Attempts",
        x=periods,
        y=attempts_list,
        marker_color="#3498db",
        text=attempts_list,
        textposition="auto",
        hovertemplate="%{x}<br>Attempts: %{y}<extra></extra>",
    ),
    go.Bar(
        name="Returns",
        x=periods,
        y=returns_list,
        marker_color="#e74c3c",
        text=returns_list,
        textposition="auto",
        hovertemplate="%{x}<br>Returns: %{y}<extra></extra>",
    ),
])
fig.update_layout(
    title="Attempts vs Returns by Half-Year",
    yaxis_title="Count",
    xaxis_title=None,
    barmode="group",  # Side-by-side bars, not stacked
    margin=dict(l=40, r=20, t=40, b=40),
    height=400,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#c9d1d9"),
    legend=dict(font=dict(color="#c9d1d9")),
)
```

### Updated `startup()` DDL

**Current code (lines 549-580) uses CREATE IF NOT EXISTS:**
```python
# Source: app/plugins/competence.py lines 555-574
conn.executescript("""
    CREATE TABLE IF NOT EXISTS sync_state (...);
    CREATE TABLE IF NOT EXISTS transitions (...);
    CREATE INDEX IF NOT EXISTS ...;
""")
```

**Replacement — DROP + CREATE fresh (per user architectural decision):**
```python
# Source: User's Key Architectural Decision for Phase 3
def startup(self) -> None:
    """Drop old tables and recreate with extended schema. Sync refetches data."""
    try:
        with _db_lock:
            conn = _get_db()
            try:
                conn.executescript("""
                    DROP TABLE IF EXISTS transitions;
                    DROP TABLE IF EXISTS tickets;
                    DROP TABLE IF EXISTS sync_state;

                    CREATE TABLE sync_state (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    );

                    CREATE TABLE transitions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_key  TEXT NOT NULL,
                        transition_date TEXT NOT NULL,
                        action_type TEXT NOT NULL
                            CHECK(action_type IN ('ATTEMPT', 'RETURN')),
                        author_account_id TEXT,
                        author_display_name TEXT,
                        from_status TEXT,
                        to_status TEXT
                    );

                    CREATE TABLE tickets (
                        ticket_key TEXT PRIMARY KEY,
                        summary TEXT,
                        issue_type TEXT,
                        last_synced TEXT
                    );

                    CREATE INDEX idx_transitions_date
                        ON transitions(transition_date);
                    CREATE INDEX idx_transitions_ticket
                        ON transitions(ticket_key);
                    CREATE INDEX idx_tickets_key
                        ON tickets(ticket_key);
                """)
                conn.commit()
            finally:
                conn.close()
        print(f"[competence] SQLite schema recreated at {DB_PATH}")
    except Exception as e:
        print(f"[warn] Competence plugin DB init failed: {e}")
```

### `createTabs()` API for Phase 4 Reference

**From `app/static/js/core.js` lines 168-190:**
```javascript
// Source: app/static/js/core.js lines 168-190
export function createTabs(container, tabs) {
  // tabs is an array of { id: string, label: string, render(container) }
  // Returns { activate, body, bar }
  // - container: DOM element to append tab bar + body to
  // - tabs[i].render(container): called when tab is activated,
  //   receives the tab body div to populate with content
}
```

**Phase 4 will use this pattern:**
```javascript
createTabs(mainContainer, [
  { id: "overview", label: "Overview", render: (c) => this._renderOverview(c) },
  { id: "perticket", label: "Per Ticket", render: (c) => this._renderPerTicket(c) },
  { id: "charts", label: "Charts", render: (c) => this._renderCharts(c) },
]);
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `transitions` with 4 columns | Extended with author/status columns | Phase 3 | Enables per-ticket attribution queries |
| Sync fetches keys only | Sync fetches key+summary+issuetype | Phase 3 | Enables `/tickets` endpoint with issue metadata |
| Single `/chart` endpoint | `/chart` (rate) + `/chart/volume` (volume) | Phase 3 | Two chart types, existing endpoint preserved |
| `startup()` CREATE IF NOT EXISTS | `startup()` DROP + CREATE fresh | Phase 3 | No migration code; simpler; sync refetches data |
| No ticket-level API | `/tickets`, `/tickets/{key}`, `/summary` | Phase 3 | Enables Phase 4's Per-Ticket tab and summary cards |

**Deprecated/outdated:**
- **`CREATE TABLE IF NOT EXISTS` for transitions:** Replaced by DROP+CREATE per user decision. The old 4-column schema is insufficient for FR8 attribution requirements.
- **`fields="key"` in `search_issues`:** Replaced by `fields="key,summary,issuetype"` to satisfy FR9.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DROP+CREATE is acceptable because M1 data is test data only | Architecture Patterns: startup() | Low — data is refetched from Jira; the 22 rows in competence_cache.db are from M1 testing. No production data exists. |
| A2 | jira package `search_issues` with `fields="key,summary,issuetype"` returns `iss.fields.summary` (string) and `iss.fields.issuetype.name` (string) | Code Examples: Sync Job | Low — verified via `inspect.signature` and existing usage in `release_creator.py` line 262 (`issue.fields.summary`). `issuetype.name` is standard Jira REST API response field. |
| A3 | Jira changelog entries from `/rest/api/2/issue/{key}/changelog` include `author.displayName` field | Code Examples: _parse_changelog | Low — Jira REST API v2 changelog response always includes `author` object with `displayName`. Currently the code only accesses `author.accountId` (line 181). |
| A4 | `pd.Grouper(key="transition_date", freq="2Q")` behavior unchanged in pandas 2.1.1 | Common Pitfalls | Low — stable pandas API; verified working in current codebase. |
| A5 | The `jira` Python package v3.10.5 is compatible with the Jira Cloud REST API v2 endpoints used (`search_issues`, `myself`) | Standard Stack | Low — actively maintained package; verified working in current codebase via `release_creator.py` and existing sync. |
| A6 | SQLite in WAL mode supports concurrent reads from pandas `read_sql_query` + WAL writers from sync job without deadlocks | Don't Hand-Roll | Low — WAL mode is designed for this pattern; verified working in M1 codebase. |

## Open Questions (RESOLVED)

1. **Should `_parse_changelog` process entries in chronological or reverse-chronological order?** RESOLVED: Reverse entries to oldest-first. State machine uses per-ticket `in_testing` boolean which works correctly either direction. Oldest-first is more intuitive.

2. **What should `/summary` "most_returned" list include when there are ties?** RESOLVED: Return top 5 tickets by return count (not just ties for #1). Includes highest-returned ticket(s) at minimum.

3. **Should `/tickets` be paginated server-side or client-side?** RESOLVED: Return all results initially (<500 tickets typical). Client-side `createTable()` handles display clipping via `maxRows`. Server-side pagination deferred unless >500ms.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | Runtime | ✓ | 3.10.x | — |
| jira (PyPI) | Jira REST API calls | ✓ | 3.10.5 | — |
| httpx | Async changelog fetching | ✓ | 0.28.1 | — |
| pandas | Stats aggregation, chart data | ✓ | 2.1.1 | — |
| plotly | Chart HTML generation | ✓ | 6.6.0 | — |
| fastapi | Web framework | ✓ | 0.135.1 | — |
| sqlite3 | Database | ✓ | stdlib | — |
| Jira Cloud access | Sync data source | ✓ | teltonika-telematics.atlassian.net | — |
| Jira credentials | Authentication | ✓ | `third_party/jira-time-tracker/jira_config.json` | — |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** none

All required dependencies are installed and operational. The Jira credentials file exists at the standard path and is shared with other plugins.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Jira BasicAuth handled by `config.load_jira_config()` — secrets never hardcoded |
| V3 Session Management | No | Stateless API; no user sessions |
| V4 Access Control | No | Internal toolkit; no multi-user access control needed |
| V5 Input Validation | Yes | FastAPI path parameters (`{key}`) auto-validated; SQL parameterized queries prevent injection |
| V6 Cryptography | No | Credentials stored in local JSON file; no encryption at rest (acceptable for local tool) |

### Known Threat Patterns for Python/FastAPI + SQLite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via ticket key in `/tickets/{key}` | Tampering | Parameterized queries — already used throughout (`?` placeholders in `conn.execute()`) |
| Path traversal in DB_PATH | Tampering | DB_PATH is hardcoded to `plugins/competence_cache.db` — no user input |
| Credential exposure in logs | Information Disclosure | `config.load_jira_config()` returns dict; ensure `print()` statements don't log email/token values |
| DoS via concurrent sync requests | Denial of Service | `in_progress` guard prevents concurrent syncs; semaphore(5) limits Jira API call rate |

## Sources

### Primary (HIGH confidence)
- `app/plugins/competence.py` — full source (593 lines) — verified all existing patterns, DB schema, sync logic, route handlers
- `app/plugins/release_creator.py` — full source (415 lines) — verified `jira` package `search_issues` usage, `issue.fields.summary` access pattern, `_jira().myself()` pattern
- `app/plugins/base.py` — full source (53 lines) — verified plugin lifecycle interface (`startup`, `shutdown`, `register_routes`)
- `app/config.py` — full source (104 lines) — verified `load_jira_config()` path (`third_party/jira-time-tracker/jira_config.json`), return type (`dict`)
- `app/main.py` — lines 50-64 — verified plugin startup is called synchronously during lifespan
- `app/static/js/core.js` — lines 168-190 — verified `createTabs()` API signature and tab activation pattern
- `app/static/js/competence.js` — full source (123 lines) — verified M1 frontend structure for Phase 4 planning context
- `requirements.txt` — verified all dependencies already declared; no new packages needed
- `jira` package — verified `search_issues` signature via `inspect.signature` — confirms `fields` param accepts string like `"key,summary,issuetype"`
- slopcheck v0.6.1 — all 5 packages verified `[OK]` on PyPI
- `.planning/REQUIREMENTS.md` v2.0 — verified FR7-FR10 requirements, NFR6-NFR11 constraints
- `.planning/ROADMAP.md` — verified phase dependency (Phase 3 → Phase 4)

### Secondary (MEDIUM confidence)
- pip index — verified installed vs available versions match for jira (3.10.5), httpx (0.28.1), plotly (6.6.0 installed, 6.8.0 latest), fastapi (0.135.1)
- `competence_cache.db` — verified existing schema (transitions: 4 columns, sync_state: KV store, 22 test rows)

### Tertiary (LOW confidence)
- None — all claims are verified against the codebase, existing dependencies, or the user's explicit architectural decision

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are already in use in the project; versions verified via pip; slopcheck verified
- Architecture: HIGH — existing patterns analyzed from working M1 codebase; no new patterns needed
- Pitfalls: HIGH — pitfalls derived from direct code review of the existing implementation
- Code examples: HIGH — all SQL and Python examples derived from verified patterns in the codebase
- Security: MEDIUM — credential handling verified; no dynamic security testing performed

**Research date:** 2026-06-17
**Valid until:** 2026-07-17 (stable domain; libraries are mature)
