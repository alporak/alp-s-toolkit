# Phase 3: Backend Enhancements — Extended Data Model & APIs

**Mapped:** 2026-06-17
**Files analyzed:** 1 (rewrite `app/plugins/competence.py` — single-file plugin rewrite)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/plugins/competence.py` | plugin (class) | request-response + background-task | `app/plugins/release_creator.py` (lines 234–415) | exact (same base class, same register_routes pattern) |
| `app/plugins/competence.py` | Jira client | lazy-init singleton | `app/plugins/release_creator.py` (lines 49–59) | exact (same `_jira()` pattern) |
| `app/plugins/competence.py` | HTTP client | async REST (httpx) | `app/plugins/competence.py` (lines 103–151) — SELF | exact (keep current pattern) |
| `app/plugins/competence.py` | SQLite schema | DDL (startup migration) | `app/plugins/competence.py` (lines 549–580) — SELF | exact (extend existing startup pattern) |
| `app/plugins/competence.py` | parser | state-machine (changelog → transitions) | `app/plugins/competence.py` (lines 158–220) — SELF | exact (enhance current parser) |
| `app/plugins/competence.py` | sync engine | event-driven (asyncio.create_task + Semaphore) | `app/plugins/competence.py` (lines 261–395) — SELF | exact (enhance current sync job) |
| `app/plugins/competence.py` | stats/chart endpoints | CRUD + chart (JSON + HTML) | `app/plugins/competence.py` (lines 410–545) — SELF + `app/plugins/log_parser.py` (lines 713–752) | exact (keep existing + add new endpoints) |
| `app/plugins/competence.py` | route registration | decorator-in-method with inner async defs | `app/plugins/release_creator.py` (lines 240–412) | exact (same closure pattern) |

---

## Pattern Assignments

---

### 1. Plugin Structure & Class Definition (KEEP from M1)

**Analog:** `app/plugins/release_creator.py` (lines 234–238, 414–415)

The outer structure of `competence.py` is exactly the same as every other plugin. The rewrite keeps this identical.

**File layout order (top to bottom):**
1. Module docstring
2. `from __future__ import annotations`
3. Standard library imports (os, json, asyncio, sqlite3, threading, datetime, typing)
4. Third-party imports (httpx, pandas, plotly, jira, fastapi)
5. Local imports (base, config)
6. Constants section (`# ── Constants ──`)
7. State machine status sets (`# ── State machine status sets ──`)
8. Module-level state variables (`# ── Module-level state ──`)
9. Jira client factory function
10. SQLite helpers section (`# ── SQLite helpers ──`)
11. HTTP helpers section (`# ── HTTP helpers ──`)
12. State machine parser function (`# ── State machine — changelog parsing ──`)
13. Stats helpers (pandas) (`# ── Stats helpers ──`)
14. Background sync engine function (`# ── Background sync engine ──`)
15. Plugin class section (`# ── Plugin class ──`)
16. Module-level singleton: `plugin = CompetencePlugin()`

**Plugin class skeleton (unchanged pattern from release_creator.py lines 234–238):**

```python
# From release_creator.py lines 234–238:
class ReleaseCreatorPlugin(ToolkitPlugin):
    id = "release"
    name = "Release Creator"
    icon = "🚀"
    order = 50
```

**Adaptation for competence.py (unchanged from M1, competence.py lines 402–406):**

```python
class CompetencePlugin(ToolkitPlugin):
    id = "competence"
    name = "Competence Matrix"
    icon = "📈"
    order = 45

    def register_routes(self, app: FastAPI) -> None:
        # ── All routes defined inside this method (closures) ──
        ...

    def startup(self) -> None:
        """Create/upgrade SQLite tables on first launch."""
        ...

    def shutdown(self) -> None:
        """Close the shared httpx client."""
        ...

# ── Auto-discovery singleton ──
plugin = CompetencePlugin()
```

**Adaptation notes:** Class-level attributes (`id`, `name`, `icon`, `order`) remain exactly as they are. The `startup()` method signature stays the same — its body will be updated for the new schema. The `shutdown()` method stays the same. The module-level `plugin = CompetencePlugin()` singleton remains at the bottom of the file.

---

### 2. Jira Client Pattern (KEEP, fix error handling)

**Analog:** `app/plugins/release_creator.py` (lines 49–59) and `app/plugins/jira_tracker.py` (lines 28–37)

Both existing plugins use the same lazy-init singleton pattern for the JIRA client. The competence.py version already follows this pattern correctly but should inherit the error-handling robustness pattern used in route handlers.

**Exact pattern from release_creator.py lines 49–59:**

```python
# release_creator.py lines 49–59:
_jira_client: JIRA | None = None

def _jira() -> JIRA:
    """Lazy-init a JIRA client from saved config."""
    global _jira_client
    if _jira_client is None:
        c = config.load_jira_config()
        _jira_client = JIRA(server=SERVER,
                            basic_auth=(c.get("email", ""), c.get("token", "")))
    return _jira_client
```

**Current competence.py version (lines 42–51) — already matches:**

```python
# competence.py lines 42–51:
def _get_jira_client() -> JIRA:
    """Lazy-init a JIRA client from saved config (same pattern as release_creator.py)."""
    global _jira_client
    if _jira_client is None:
        c = config.load_jira_config()
        _jira_client = JIRA(
            server=SERVER,
            basic_auth=(c.get("email", ""), c.get("token", "")),
        )
    return _jira_client
```

**Error handling for Jira calls in route handlers (from jira_tracker.py lines 355–357):**

```python
# jira_tracker.py lines 355–357 — wrapper pattern for JIRAError:
try:
    raw = _jira().search_issues(jql, maxResults=50, fields="summary,status,priority,attachment")
except JIRAError as e:
    raise HTTPException(e.status_code or 500, str(e))
```

**Adaptation notes:** The `_get_jira_client()` function stays exactly as-is. The enhancement is in its *callers*: when the sync job calls `_get_jira_client().myself()` or `_get_jira_client().search_issues()`, wrap in try/except JIRAError (already partially done in the sync job at lines 390–391). For the new ticket detail endpoint that fetches a single issue, follow the jira_tracker.py pattern above.

```python
# For new endpoints that use _get_jira_client():
try:
    issue = await asyncio.to_thread(_get_jira_client().issue, key, fields="summary,issuetype,status,assignee")
except JIRAError as e:
    raise HTTPException(e.status_code or 400, str(e))
```

---

### 3. HTTP Client for Changelogs (KEEP — no change)

**Analog:** `app/plugins/competence.py` (lines 103–151) — SELF

The httpx async HTTP client pattern already works correctly. The three core functions (`_get_client`, `_api_get`, `_close_client`) are stable and need no changes. These remain as-is in the rewrite.

**Exact current code (competence.py lines 103–151) — KEEP AS-IS:**

```python
# competence.py lines 103–151:
# ═══════════════════════════════════════════════════════════
#  HTTP helpers (Jira REST API v2 via httpx)
# ═══════════════════════════════════════════════════════════

async def _get_client() -> httpx.AsyncClient:
    """Lazy-init a shared httpx AsyncClient with Jira BasicAuth."""
    global _http_client
    if _http_client is None:
        c = config.load_jira_config()
        email = c.get("email", "")
        token = c.get("token", "")
        if not email or not token:
            raise HTTPException(503, "Jira credentials not configured")
        _http_client = httpx.AsyncClient(
            base_url=f"{SERVER}/rest/api/2/",
            auth=httpx.BasicAuth(email, token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=httpx.Timeout(30.0),
        )
    return _http_client


async def _api_get(path: str, **params) -> dict:
    """Perform a GET against the Jira REST API v2 and return parsed JSON.
    Raises HTTPException on 4xx/5xx responses.
    """
    client = await _get_client()
    resp = await client.get(path, params=params)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()


async def _api_post(path: str, body: dict) -> dict:
    """Perform a POST against the Jira REST API v2 and return parsed JSON."""
    client = await _get_client()
    resp = await client.post(path, json=body)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()


async def _close_client() -> None:
    """Close the shared httpx client (called on plugin shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
```

**Adaptation notes:** These functions are production-ready. The only consideration: for the enhanced sync job that also fetches ticket summary/issuetype, these same `_api_get()` / `_api_post()` functions will be reused. The `_api_get("issue/{key}")` call pattern already exists in the changelog fetching loop.

**Module-level state (competence.py lines 36–39) — KEEP AS-IS:**

```python
# Module-level state (lines 36–39):
_db_lock = threading.Lock()
_http_client: httpx.AsyncClient | None = None
_jira_client: JIRA | None = None
```

---

### 4. SQLite Schema (REWRITE — fresh DROP + CREATE migration)

**Analog:** `app/plugins/competence.py` (lines 549–580) — SELF (startup pattern)

**Current startup() schema** (competence.py lines 549–580):

```python
# competence.py lines 549–580:
def startup(self) -> None:
    """Create SQLite tables and indexes on first launch."""
    try:
        with _db_lock:
            conn = _get_db()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS sync_state (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    );

                    CREATE TABLE IF NOT EXISTS transitions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_key  TEXT NOT NULL,
                        transition_date TEXT NOT NULL,
                        action_type TEXT NOT NULL
                            CHECK(action_type IN ('ATTEMPT', 'RETURN'))
                    );

                    CREATE INDEX IF NOT EXISTS idx_transitions_date
                        ON transitions(transition_date);

                    CREATE INDEX IF NOT EXISTS idx_transitions_ticket
                        ON transitions(ticket_key);
                """)
                conn.commit()
            finally:
                conn.close()
        print(f"[competence] SQLite initialized at {DB_PATH}")
    except Exception as e:
        print(f"[warn] Competence plugin DB init failed: {e}")
```

**New schema (Phase 3 rewrite) — extended transitions + new tickets table:**

The rewrite uses a **DROP + CREATE** approach (fresh start since M1 data is not production-critical). The `startup()` method must:

1. Check `schema_version` in `sync_state`
2. If version is missing or < 2, DROP old tables
3. CREATE all tables fresh with extended columns
4. Set `schema_version = '2'`

```python
# NEW startup() body for Phase 3 rewrite:

def startup(self) -> None:
    """Create or upgrade SQLite tables on launch."""
    try:
        with _db_lock:
            conn = _get_db()
            try:
                # ── Check schema version ──
                row = conn.execute(
                    "SELECT value FROM sync_state WHERE key = 'schema_version'"
                ).fetchone()
                current_version = row["value"] if row else "0"

                if current_version != "2":
                    self._migrate_v2(conn)
                    conn.execute(
                        "INSERT OR REPLACE INTO sync_state (key, value) "
                        "VALUES ('schema_version', '2')"
                    )
                    conn.commit()
                    print("[competence] Schema migrated to v2 (fresh DROP + CREATE)")
                else:
                    print(f"[competence] SQLite already at v2")
            finally:
                conn.close()
    except Exception as e:
        print(f"[warn] Competence plugin DB init failed: {e}")

# Static or module-level helper (inside or near CompetencePlugin):
@staticmethod
def _migrate_v2(conn: sqlite3.Connection) -> None:
    """V2 schema: extended transitions + tickets table."""
    conn.executescript("""
        DROP TABLE IF EXISTS transitions;
        DROP TABLE IF EXISTS tickets;

        CREATE TABLE sync_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE transitions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_key      TEXT    NOT NULL,
            transition_date TEXT    NOT NULL,
            action_type     TEXT    NOT NULL
                CHECK(action_type IN ('ATTEMPT', 'RETURN')),
            author_account_id   TEXT    NOT NULL DEFAULT '',
            author_display_name TEXT    NOT NULL DEFAULT '',
            from_status         TEXT    NOT NULL DEFAULT '',
            to_status           TEXT    NOT NULL DEFAULT '',
            UNIQUE(ticket_key, transition_date, action_type)
        );

        CREATE TABLE tickets (
            ticket_key  TEXT PRIMARY KEY,
            summary     TEXT    NOT NULL DEFAULT '',
            issue_type  TEXT    NOT NULL DEFAULT '',
            status      TEXT    NOT NULL DEFAULT '',
            assignee_display_name TEXT NOT NULL DEFAULT '',
            assignee_account_id   TEXT NOT NULL DEFAULT '',
            last_fetched TEXT    NOT NULL DEFAULT ''
        );

        CREATE INDEX idx_transitions_date   ON transitions(transition_date);
        CREATE INDEX idx_transitions_ticket ON transitions(ticket_key);
        CREATE INDEX idx_transitions_author ON transitions(author_account_id);
        CREATE INDEX idx_tickets_assignee   ON tickets(assignee_account_id);
    """)
```

**DB helper pattern — keep existing `_get_db()`, `_db_get()`, `_db_set()`, plus add helpers:**

Keep from current competence.py lines 58–90 (unchanged):

```python
# competence.py lines 58–90 — KEEP AS-IS:
def _get_db() -> sqlite3.Connection:
    """Return a thread-safe SQLite connection with WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _db_get(key: str) -> str | None:
    """Synchronous read from sync_state key-value store."""
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT value FROM sync_state WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()

def _db_set(key: str, value: str) -> None:
    """Synchronous write (insert-or-replace) to sync_state."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

async def _db_get_async(key: str) -> str | None:
    return await asyncio.to_thread(_db_get, key)

async def _db_set_async(key: str, value: str) -> None:
    await asyncio.to_thread(_db_set, key, value)
```

**New helper needed — upsert tickets:**

```python
def _upsert_ticket(key: str, summary: str, issue_type: str, status: str,
                   assignee_name: str, assignee_id: str) -> None:
    """Synchronous upsert into tickets table."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO tickets
                    (ticket_key, summary, issue_type, status,
                     assignee_display_name, assignee_account_id, last_fetched)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (key, summary, issue_type, status,
                  assignee_name, assignee_id,
                  datetime.now(timezone.utc).isoformat()))
            conn.commit()
        finally:
            conn.close()
```

**Adaptation notes:** The `startup()` method changes from a `CREATE TABLE IF NOT EXISTS` approach to a **DROP + CREATE** migration triggered by a `schema_version` check. This is acceptable because M1 data is not production-critical (ROADMAP.md implies fresh data). The DB_PATH constant (line 28) stays the same: `os.path.join(os.path.dirname(__file__), "competence_cache.db")`.

---

### 5. State Machine Parser (ENHANCE from M1)

**Analog:** `app/plugins/competence.py` (lines 158–220) — SELF

The current `_parse_changelog()` function correctly implements the ATTEMPT/RETURN state machine. For Phase 3, we need to **augment** it to capture attribution data (who performed the transition, what statuses were involved).

**Current parser** (competence.py lines 158–220):

```python
# competence.py lines 158–220:
def _parse_changelog(
    changelog: dict,
    ticket_key: str,
    current_account_id: str,
) -> list[dict]:
    """Parse a Jira issue changelog into ATTEMPT / RETURN transitions."""
    transitions: list[dict] = []
    in_testing = False

    for entry in changelog.get("values", []):
        author = entry.get("author") or {}
        author_id = author.get("accountId", "")
        created = entry.get("created", "")

        for item in entry.get("items", []):
            if item.get("field") != "status":
                continue

            from_status = item.get("fromString", "")
            to_status = item.get("toString", "")

            if not from_status or not to_status:
                continue

            # ── Rule 1: ATTEMPT — authored by current user, entering testing ──
            if (
                from_status in ATTEMPT_FROM
                and to_status in ATTEMPT_TO
                and author_id == current_account_id
            ):
                transitions.append({
                    "ticket_key": ticket_key,
                    "transition_date": created,
                    "action_type": "ATTEMPT",
                })
                in_testing = True

            # ── Rule 2: RETURN — any author, leaving testing after attempt ──
            elif (
                in_testing
                and from_status in RETURN_FROM
                and to_status in RETURN_TO
            ):
                transitions.append({
                    "ticket_key": ticket_key,
                    "transition_date": created,
                    "action_type": "RETURN",
                })
                in_testing = False

    return transitions
```

**Enhanced parser for Phase 3 — adds author_display_name, from_status, to_status, and removes current_account_id filter on ATTEMPT:**

```python
def _parse_changelog(
    changelog: dict,
    ticket_key: str,
) -> list[dict]:
    """Parse a Jira issue changelog into ATTEMPT / RETURN transitions.

    Phase 3 enhancement: captures full attribution data.
    ATTEMPT: entering a testing status (any author now, for team-wide tracking).
    RETURN:  leaving a testing status back to development, AFTER a prior
             ATTEMPT was recorded for this ticket (any author).

    Returns a list of dicts with keys:
        ticket_key, transition_date, action_type,
        author_account_id, author_display_name,
        from_status, to_status
    """
    transitions: list[dict] = []
    in_testing = False

    for entry in changelog.get("values", []):
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

            # ── Rule 1: ATTEMPT — any author, entering testing ──
            if (
                from_status in ATTEMPT_FROM
                and to_status in ATTEMPT_TO
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

            # ── Rule 2: RETURN — any author, leaving testing after attempt ──
            elif (
                in_testing
                and from_status in RETURN_FROM
                and to_status in RETURN_TO
            ):
                transitions.append({
                    "ticket_key": ticket_key,
                    "transition_date": created,
                    "action_type": "RETURN",
                    "author_account_id": author_id,
                    "author_display_name": author_name,
                    "from_status": from_status,
                    "to_status": to_status,
                })
                in_testing = False

    return transitions
```

**Adaptation notes for `_parse_changelog()`:**
1. **Keep:** The state machine logic (ATTEMPT_FROM/TO, RETURN_FROM/TO, in_testing flag) — identical.
2. **Remove:** `current_account_id` parameter — no longer filter ATTEMPTs to current user (team-wide tracking per ROADMAP.md).
3. **Add:** `author_account_id`, `author_display_name`, `from_status`, `to_status` to each transition dict — these are new columns in the extended transitions table.
4. **Keep:** The `in_testing` boolean per-ticket-per-call (correct behavior — tracks whether a return is valid only after an attempt in the same changelog parse).

**Constant sets (keep these exactly, lines 31–34):**

```python
# competence.py lines 31–34 — KEEP AS-IS:
RETURN_FROM = {"For Testing", "In Testing", "Test Failed", "Testing Failed"}
RETURN_TO = {"In Development", "In Progress", "Gathering Information", "To Do", "New"}
ATTEMPT_TO = {"Developed", "For Testing", "In Testing"}
ATTEMPT_FROM = {"In Development", "New", "Gathering Information"}
```

---

### 6. Sync Job (ENHANCE from M1)

**Analog:** `app/plugins/competence.py` (lines 261–395) — SELF

The core sync pipeline structure works correctly. For Phase 3, we enhance it with:
1. Ticket summary/issuetype fetching (upserts into new `tickets` table)
2. Extended transition data insertion (new columns)
3. Remove the `current_account_id` dependency in `_parse_changelog()` call

**Current sync job structure** (competence.py lines 261–395):

```python
# competence.py lines 261–395 — core structure:
async def _sync_job() -> None:
    # 1. Guard: prevent concurrent syncs
    if await _db_get_async("in_progress") == "1":
        print("[competence] Sync already in progress")
        return
    await _db_set_async("in_progress", "1")

    try:
        # 2. Identify current user
        myself = await asyncio.to_thread(_get_jira_client().myself)
        current_account_id = myself.get("accountId", "")
        # ... (guard returns if no accountId)

        # 3. Build JQL (incremental vs full)
        last_sync = await _db_get_async("last_sync")
        if last_sync:
            jql = f"(assignee WAS currentUser() OR reporter = currentUser()) AND updated >= '{last_sync}'"
        else:
            jql = "assignee WAS currentUser() OR reporter = currentUser()"

        # 4. Search for issues (paginated via jira package)
        all_issues: list[dict] = []
        start_at = 0; max_results = 1000
        while True:
            results = await asyncio.to_thread(
                _get_jira_client().search_issues, jql,
                maxResults=max_results, startAt=start_at, fields="key")
            batch = [{"key": iss.key} for iss in results]
            all_issues.extend(batch)
            start_at += len(results)
            if len(results) < max_results: break

        # 5. Fetch changelogs with Semaphore(5) concurrency
        semaphore = asyncio.Semaphore(5)

        async def _fetch_changelog(key: str) -> tuple[str, list[dict]]:
            async with semaphore:
                try:
                    entries: list[dict] = []
                    start = 0; page_size = 100
                    while True:
                        data = await _api_get(f"issue/{key}/changelog",
                            maxResults=page_size, startAt=start)
                        batch = data.get("values", [])
                        entries.extend(batch)
                        if len(batch) < page_size: break
                        start += len(batch)
                    return key, entries
                except HTTPException: raise
                except Exception as exc:
                    print(f"[competence] Failed to fetch changelog for {key}: {exc}")
                    return key, []

        tasks = [_fetch_changelog(key) for key in issue_keys]
        results = await asyncio.gather(*tasks)

        # 6. Parse changelogs through state machine
        all_transitions: list[dict] = []
        for key, entries in results:
            if not entries: continue
            parsed = _parse_changelog({"values": entries}, key, current_account_id)
            all_transitions.extend(parsed)

        # 7. Deduplicate & insert into SQLite
        inserted = 0
        for t in all_transitions:
            with _db_lock:
                conn = _get_db()
                try:
                    existing = conn.execute(
                        "SELECT 1 FROM transitions "
                        "WHERE ticket_key = ? AND transition_date = ? AND action_type = ?",
                        (t["ticket_key"], t["transition_date"], t["action_type"]),
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            "INSERT INTO transitions "
                            "(ticket_key, transition_date, action_type) "
                            "VALUES (?, ?, ?)",
                            (t["ticket_key"], t["transition_date"], t["action_type"]),
                        )
                        conn.commit()
                        inserted += 1
                finally:
                    conn.close()

        # 8. Update last_sync timestamp
        await _db_set_async("last_sync", datetime.now(timezone.utc).isoformat())

    except HTTPException as e:
        print(f"[competence] Sync error (Jira): {e.status_code} {e.detail}")
    except Exception as e:
        print(f"[competence] Sync failed: {e}")
    finally:
        await _db_set_async("in_progress", "0")
```

**Enhanced sync job for Phase 3 — key changes:**

The enhanced version adds a step between steps 4 and 5 to fetch ticket metadata (summary, issuetype, status, assignee), and updates step 6 to pass data without `current_account_id`, and step 7 to insert extended columns.

**New step: Fetch ticket metadata (insert between steps 4 and 5):**

```python
# ── 4b. Fetch ticket summary + issuetype (NEW) ────────
# Fetch per-issue metadata for the tickets table.
# Run in parallel with the changelog fetch using separate semaphore.
_ticket_semaphore = asyncio.Semaphore(5)

async def _fetch_ticket_meta(key: str) -> tuple[str, dict]:
    async with _ticket_semaphore:
        try:
            data = await _api_get(
                f"issue/{key}",
                fields="summary,issuetype,status,assignee"
            )
            fields = data.get("fields", {})
            issuer = fields.get("assignee") or {}
            return key, {
                "summary": fields.get("summary", ""),
                "issue_type": (fields.get("issuetype") or {}).get("name", ""),
                "status": (fields.get("status") or {}).get("name", ""),
                "assignee_name": issuer.get("displayName", ""),
                "assignee_id": issuer.get("accountId", ""),
            }
        except HTTPException:
            return key, {}
        except Exception as exc:
            print(f"[competence] Failed to fetch ticket meta for {key}: {exc}")
            return key, {}

# Run in parallel with changelog fetch
ticket_meta_tasks = [_fetch_ticket_meta(key) for key in issue_keys]
ticket_meta_results = await asyncio.gather(*ticket_meta_tasks)
ticket_meta = dict(ticket_meta_results)

# Then upsert into tickets table
for key, meta in ticket_meta.items():
    if meta:
        _upsert_ticket(key,
            meta["summary"], meta["issue_type"], meta["status"],
            meta["assignee_name"], meta["assignee_id"])
```

**Updated parse call (step 6 — remove `current_account_id`):**

```python
# OLD (competence.py line 353):
parsed = _parse_changelog({"values": entries}, key, current_account_id)

# NEW:
parsed = _parse_changelog({"values": entries}, key)
```

**Updated insertion (step 7 — add new columns):**

```python
for t in all_transitions:
    with _db_lock:
        conn = _get_db()
        try:
            existing = conn.execute(
                "SELECT 1 FROM transitions "
                "WHERE ticket_key = ? AND transition_date = ? AND action_type = ?",
                (t["ticket_key"], t["transition_date"], t["action_type"]),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO transitions "
                    "(ticket_key, transition_date, action_type, "
                    " author_account_id, author_display_name, "
                    " from_status, to_status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (t["ticket_key"], t["transition_date"], t["action_type"],
                     t.get("author_account_id", ""),
                     t.get("author_display_name", ""),
                     t.get("from_status", ""),
                     t.get("to_status", "")),
                )
                conn.commit()
                inserted += 1
        finally:
            conn.close()
```

**Adaptation notes for `_sync_job()`:**
1. **Keep:** `asyncio.create_task(_sync_job())` spawning pattern (from `competence_sync()` route, line 456).
2. **Keep:** `Semaphore(5)` concurrency limit for changelog fetches.
3. **Keep:** `in_progress` guard flag pattern.
4. **Keep:** `last_sync` timestamp update.
5. **Add:** Parallel ticket metadata fetch (separate semaphore, separate gather).
6. **Add:** `_upsert_ticket()` calls in the sync pipeline.
7. **Change:** Insert statement includes new columns.
8. **Remove:** `current_account_id` dependency — no longer needed since `_parse_changelog()` captures all authors.

---

### 7. Stats & Chart Endpoints (KEEP existing + ADD new)

**Analog:** Current `app/plugins/competence.py` (lines 410–545) — SELF + `app/plugins/log_parser.py` (lines 713–752)

#### 7a. KEEP existing endpoints (lines 410–478, unchanged)

**`/api/competence/stats`** (lines 412–443): Keep as-is — returns ATTEMPT/RETURN grouped by 2Q periods. The underlying `_load_transitions_df()` will naturally include the new columns (pandas reads them as extra columns, harmless).

**`/api/competence/sync`** (lines 445–464): Keep as-is — triggers `asyncio.create_task(_sync_job())`. The sync job internals change; the endpoint signature does not.

**`/api/competence/sync/status`** (lines 466–477): Keep as-is — returns last_sync and in_progress flags.

#### 7b. KEEP existing chart endpoint (lines 479–545, unchanged)

**`/api/competence/chart`** (lines 479–545): Keep as-is — returns Plotly HTML bar chart of return rate.

**Pattern source** — log_parser.py lines 713–721 for the `response_class=HTMLResponse` decorated endpoint:

```python
# log_parser.py lines 713–721 — Plotly HTML endpoint pattern:
@app.get("/api/logs/analysis/{aid}/timeline", response_class=HTMLResponse)
async def get_timeline_chart(aid: str):
    parsed = _get_parsed(aid)
    if not parsed:
        raise HTTPException(404)
    fig = create_timeline(parsed.get("events", []))
    if fig is None:
        return "<p>No events for timeline</p>"
    return fig.to_html(include_plotlyjs="cdn", full_html=False)
```

#### 7c. NEW endpoint: `/api/competence/tickets` (per-ticket aggregated stats)

**Analog:** `competence.py` lines 412–443 (`/stats` endpoint) — same pandas grouping pattern

```python
@app.get("/api/competence/tickets")
async def competence_tickets():
    """Return per-ticket aggregated stats: attempt count, return count,
    last transition date, associated ticket metadata."""
    try:
        df = pd.read_sql_query("""
            SELECT t.ticket_key, t.transition_date, t.action_type,
                   t.author_account_id, t.author_display_name,
                   t.from_status, t.to_status,
                   tk.summary, tk.issue_type, tk.status,
                   tk.assignee_display_name
            FROM transitions t
            LEFT JOIN tickets tk ON t.ticket_key = tk.ticket_key
            ORDER BY t.ticket_key, t.transition_date
        """, _get_db())

        if df.empty:
            return []

        grouped = df.groupby("ticket_key")

        result: list[dict] = []
        for key, group in grouped:
            attempts = int((group["action_type"] == "ATTEMPT").sum())
            returns = int((group["action_type"] == "RETURN").sum())
            return_rate = (
                round((returns / attempts * 100), 1)
                if attempts > 0 else 0.0
            )
            last_row = group.iloc[-1]
            result.append({
                "ticket_key": key,
                "summary": last_row.get("summary", ""),
                "issue_type": last_row.get("issue_type", ""),
                "status": last_row.get("status", ""),
                "assignee": last_row.get("assignee_display_name", ""),
                "attempts": attempts,
                "returns": returns,
                "return_rate_pct": return_rate,
                "last_transition": str(last_row["transition_date"]),
            })

        return result
    except Exception as e:
        raise HTTPException(500, str(e))
```

**Adaptation notes:** Uses the same `pandas.read_sql_query()` pattern as `_load_transitions_df()` (line 247). Uses the same `.groupby()` / `.sum()` pattern as the stats endpoint (lines 421–428). Returns a list of dicts.

#### 7d. NEW endpoint: `/api/competence/tickets/{key}` (single ticket timeline)

```python
@app.get("/api/competence/tickets/{key}")
async def competence_ticket_detail(key: str):
    """Return the full transition timeline for a single ticket,
    including attribution data and ticket metadata."""
    try:
        # Load transitions
        df = pd.read_sql_query("""
            SELECT ticket_key, transition_date, action_type,
                   author_account_id, author_display_name,
                   from_status, to_status
            FROM transitions
            WHERE ticket_key = ?
            ORDER BY transition_date
        """, _get_db(), params=(key,))

        # Load ticket metadata
        conn = _get_db()
        try:
            meta_row = conn.execute(
                "SELECT * FROM tickets WHERE ticket_key = ?", (key,)
            ).fetchone()
            meta = dict(meta_row) if meta_row else {}
        finally:
            conn.close()

        transitions = df.to_dict(orient="records") if not df.empty else []

        return {
            "ticket_key": key,
            "summary": meta.get("summary", ""),
            "issue_type": meta.get("issue_type", ""),
            "status": meta.get("status", ""),
            "assignee": meta.get("assignee_display_name", ""),
            "transitions": transitions,
        }
    except Exception as e:
        raise HTTPException(500, str(e))
```

#### 7e. NEW endpoint: `/api/competence/chart/volume` (attempts vs returns volume)

**Analog:** `competence.py` lines 479–545 (`/chart` endpoint) — same Plotly pattern, adds a second trace

```python
@app.get("/api/competence/chart/volume", response_class=HTMLResponse)
async def competence_chart_volume():
    """Return a Plotly grouped bar chart: attempts vs returns per half-year."""
    try:
        df = _load_transitions_df()
        if df.empty:
            return "<p style='padding:40px;text-align:center;color:var(--text-muted)'>No data yet</p>"

        df["transition_date"] = pd.to_datetime(df["transition_date"])
        grouped = df.groupby(pd.Grouper(key="transition_date", freq="2Q"))

        periods = []
        attempt_counts = []
        return_counts = []
        for period, group in grouped:
            periods.append(_format_2q_label(period))
            attempt_counts.append(int((group["action_type"] == "ATTEMPT").sum()))
            return_counts.append(int((group["action_type"] == "RETURN").sum()))

        fig = go.Figure([
            go.Bar(name="Attempts", x=periods, y=attempt_counts,
                   marker_color="#27ae60"),
            go.Bar(name="Returns",  x=periods, y=return_counts,
                   marker_color="#e74c3c"),
        ])

        fig.update_layout(
            title="Testing Attempts vs Returns by Half-Year",
            yaxis_title="Count",
            barmode="group",
            margin=dict(l=40, r=20, t=40, b=40),
            height=400,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9"),
        )

        return fig.to_html(include_plotlyjs="cdn", full_html=False)
    except Exception as e:
        raise HTTPException(500, str(e))
```

**Adaptation notes:** Identical structure to the existing chart endpoint (lines 479–545): same imports, same `_load_transitions_df()`, same `pd.Grouper(freq="2Q")` grouping, same `fig.to_html()` return. Only differences: two `go.Bar()` traces instead of one, and `barmode="group"`.

#### 7f. NEW endpoint: `/api/competence/summary` (aggregate stats)

```python
@app.get("/api/competence/summary")
async def competence_summary():
    """Return overall aggregate stats: total transitions, unique tickets,
    overall return rate, authors involved, etc."""
    try:
        df = _load_transitions_df()
        if df.empty:
            return {
                "total_transitions": 0,
                "total_attempts": 0,
                "total_returns": 0,
                "return_rate_pct": 0.0,
                "unique_tickets": 0,
                "unique_authors": 0,
                "last_sync": await _db_get_async("last_sync"),
                "data_available": False,
            }

        total_attempts = int((df["action_type"] == "ATTEMPT").sum())
        total_returns = int((df["action_type"] == "RETURN").sum())
        return_rate = (
            round((total_returns / total_attempts * 100), 1)
            if total_attempts > 0 else 0.0
        )

        # Load tickets metadata
        conn = _get_db()
        try:
            ticket_count_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM tickets"
            ).fetchone()
            unique_tickets = ticket_count_row["cnt"] if ticket_count_row else 0
        finally:
            conn.close()

        return {
            "total_transitions": len(df),
            "total_attempts": total_attempts,
            "total_returns": total_returns,
            "return_rate_pct": return_rate,
            "unique_tickets": unique_tickets,
            "unique_authors": df["author_account_id"].nunique() if "author_account_id" in df.columns else 0,
            "last_sync": await _db_get_async("last_sync"),
            "data_available": True,
        }
    except Exception as e:
        raise HTTPException(500, str(e))
```

---

### 8. register_routes Pattern

**Analog:** `app/plugins/release_creator.py` (lines 240–412)

Every plugin uses the **decorator-in-method with inner async defs** pattern. All routes are closures defined inside `register_routes(self, app: FastAPI)`.

**Exact pattern from release_creator.py lines 240–412:**

```python
# release_creator.py lines 240–412:
def register_routes(self, app: FastAPI):

    # Helper functions (local to this method)
    def _ver_dict(v):
        return {"id": v.id, "name": v.name, ...}

    @app.get("/api/release/versions")
    async def rel_versions(base: str = ""):
        try:
            vs = _versions_dicts()
        except JIRAError as e:
            raise HTTPException(e.status_code or 500, str(e))
        ...

    @app.post("/api/release/ticket")
    async def rel_create_ticket(req: TicketReq):
        j = _jira()
        # ... business logic ...
        try:
            src = j.issue(req.clone_from)
        except JIRAError as e:
            raise HTTPException(400, f"Cannot fetch clone source {req.clone_from}: {e}")
        ...
        return {"ok": True, "key": new_key, "summary": summary}
```

**How competence.py applies this (current, unchanged register_routes structure):**

```python
# competence.py lines 410–545:
def register_routes(self, app: FastAPI) -> None:

    @app.get("/api/competence/stats")
    async def competence_stats():
        ...

    @app.post("/api/competence/sync")
    async def competence_sync():
        ...

    @app.get("/api/competence/sync/status")
    async def competence_sync_status():
        ...

    @app.get("/api/competence/chart", response_class=HTMLResponse)
    async def competence_chart():
        ...
```

**Phase 3 expanded register_routes — add these new endpoints after the existing ones:**

```python
def register_routes(self, app: FastAPI) -> None:

    # ── Existing M1 endpoints (KEEP AS-IS) ──
    @app.get("/api/competence/stats")
    async def competence_stats():
        ...  # unchanged

    @app.post("/api/competence/sync")
    async def competence_sync():
        ...  # unchanged

    @app.get("/api/competence/sync/status")
    async def competence_sync_status():
        ...  # unchanged

    @app.get("/api/competence/chart", response_class=HTMLResponse)
    async def competence_chart():
        ...  # unchanged

    # ── NEW Phase 3 endpoints ──
    @app.get("/api/competence/tickets")
    async def competence_tickets():
        """Per-ticket aggregated stats with attribution."""
        ...

    @app.get("/api/competence/tickets/{key}")
    async def competence_ticket_detail(key: str):
        """Single ticket transition timeline."""
        ...

    @app.get("/api/competence/chart/volume", response_class=HTMLResponse)
    async def competence_chart_volume():
        """Attempts vs returns volume chart."""
        ...

    @app.get("/api/competence/summary")
    async def competence_summary():
        """Overall aggregate stats."""
        ...
```

**Key conventions enforced:**
1. Every route path is `/api/competence/...` — no exceptions.
2. Every handler is `async def`.
3. Error handling: `try/except Exception as e: raise HTTPException(500, str(e))` (consistent with all existing endpoints).
4. Chart endpoints use `response_class=HTMLResponse`.
5. Tiered error handling when using Jira calls: catch `JIRAError` specifically before generic `Exception` (as in release_creator.py lines 262–264).

**Specific error handling for ticket detail (Jira-backed if fetching live):**

```python
# Pattern from release_creator.py lines 262–264:
try:
    issue = _jira().issue(key, fields="summary")
except JIRAError as e:
    raise HTTPException(e.status_code or 400, str(e))
```

---

## Shared Patterns

### Authentication (Jira BasicAuth)
**Source:** `app/config.py` lines 90–97 (`load_jira_config()`)
**Apply to:** All HTTP/Jira client initialization

```python
from app import config
c = config.load_jira_config()
# c.get("email", ""), c.get("token", "") — used for both JIRA() and httpx.BasicAuth
```

### Config Access
**Source:** `app/config.py` lines 42–48, 90–97
**Apply to:** Plugin startup (reading DB path), HTTP client init, Jira client init

### Error Handling Stack (three-tier)
**Source:** `app/plugins/release_creator.py` lines 262–264, 393–395; `app/plugins/competence.py` lines 390–391, 442–443

| Tier | Pattern | When |
|------|---------|------|
| 1 | `except JIRAError as e: raise HTTPException(e.status_code or 500, str(e))` | Jira pip package calls |
| 2 | `except HTTPException: raise` (re-raise) | Let httpx errors propagate |
| 3 | `except Exception as e: raise HTTPException(500, str(e))` | Catch-all in routes |

### Route Naming Convention
**Source:** All existing plugins
**Format:** `/api/{plugin.id}/{resource}[/{param}]`
**Apply to:** All 4 new endpoints

### Module-Level Plugin Singleton
**Source:** `release_creator.py` line 415, `jira_tracker.py` line 657, `competence.py` line 593

```python
plugin = CompetencePlugin()  # MUST be at module level, ONE instance
```

### async def / asyncio.to_thread() Bridge
**Source:** `competence.py` lines 93–101
**Apply to:** Any synchronous DB or Jira call inside async context

```python
# Read from sync_state in async handler:
last_sync = await _db_get_async("last_sync")

# Call Jira methods (synchronous library) in async handler:
myself = await asyncio.to_thread(_get_jira_client().myself)
```

### pandas DataFrame Pattern
**Source:** `competence.py` lines 240–254 (`_load_transitions_df()`)
**Apply to:** All stats endpoints

```python
def _load_transitions_df() -> pd.DataFrame:
    conn = _get_db()
    try:
        df = pd.read_sql_query(
            "SELECT ... FROM transitions ORDER BY transition_date", conn)
    finally:
        conn.close()
    return df
```

---

## No Analog Found

| Pattern | Reason | Recommendation |
|---------|--------|----------------|
| **Drop + Create migration** | No existing plugin does schema migration — all use CREATE TABLE IF NOT EXISTS. | Implement `_migrate_v2()` as a static method on CompetencePlugin. Check `schema_version` in `sync_state` on startup. |
| **Tickets metadata table** | No existing plugin has a separate metadata table. | Pattern derived from transitions table — same `_get_db()` / `_db_lock` / `asyncio.to_thread()` conventions. |

---

## Metadata

**Analog search scope:** `app/plugins/*.py` (all 8 plugin files), `app/config.py`, `app/plugins/base.py`
**Files read at depth:** `competence.py` (593 lines), `release_creator.py` (415 lines), `jira_tracker.py` (657 lines), `log_parser.py` (lines 700–760), `base.py` (53 lines), `config.py` (104 lines)
**Files scanned:** 12
**Pattern extraction date:** 2026-06-17
**Rewrite scope:** Single file (`app/plugins/competence.py`). Sections to keep unchanged: HTTP client helpers (§3), Jira client factory (§2), constants (§5). Sections to enhance: parser (§5), sync job (§6), startup/schema (§4). Sections to add: 4 new API endpoints (§7c–§7f).
