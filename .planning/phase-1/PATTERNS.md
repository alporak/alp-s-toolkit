# Phase 1: Competence & Performance Plugin - Pattern Map

**Mapped:** 2026-06-17
**Files to create:** 1 (`app/plugins/competence.py`)
**Analogs found:** 6 / 8 (2 have no analog: SQLite database, BackgroundTasks)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/plugins/competence.py` | plugin | REST (request-response, background-tasks) | `app/plugins/release_creator.py` | role-match (plugin structure + Jira integration) |
| `app/plugins/competence.py` | controller | CRUD | `app/plugins/jira_tracker.py` | role-match (route registration) |
| `app/plugins/competence.py` | service | HTTP client → SQLite | No analog (first: async httpx + SQLite) | — |
| `app/plugins/competence.py` | background-task | event-driven (FastAPI BackgroundTasks) | No analog (first use of BackgroundTasks) | — |

## Pattern Assignments

---

### 1. Plugin Structure & Class Definition

**Analog:** `app/plugins/release_creator.py` (lines 1–19, 234–415) and `app/plugins/jira_tracker.py` (lines 1–19, 250–657)

**Pattern:** Every plugin follows the same structure:
1. Module docstring
2. `from __future__ import annotations`
3. Standard imports (stdlib, third-party, local)
4. Module-level constants and helpers (Jira client, auth, raw-API helpers)
5. Pydantic request models
6. A plugin class extending `ToolkitPlugin` with `id`, `name`, `icon`, `order`
7. `register_routes(self, app: FastAPI)` method containing all `@app.get/post/put/delete` routes
8. Module-level `plugin = YourPluginClass()` singleton

**Imports pattern** (from `release_creator.py` lines 1–22, `jira_tracker.py` lines 1–22):

```python
"""
Competence & Performance Plugin – [DESCRIPTION].
"""

from __future__ import annotations

import os
import json
import asyncio
from typing import Optional, List

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.plugins.base import ToolkitPlugin
from app import config
```

**Plugin class pattern** (from `release_creator.py` lines 234–238, `jira_tracker.py` lines 250–255):

```python
class CompetencePlugin(ToolkitPlugin):
    id = "competence"
    name = "Competence & Performance"
    icon = "📊"
    order = 60

    def register_routes(self, app: FastAPI):
        # All route handlers go here
        ...

    def startup(self):
        """Optional: init DB, validate Jira config."""

    def shutdown(self):
        """Optional: close DB connections."""


plugin = CompetencePlugin()
```

**Adaptation notes:** The new plugin is identical in structure. The main difference is the icon/order/id values and the use of `httpx` (async) instead of `requests` (sync) for HTTP, and `BackgroundTasks` for long-running fetches.

---

### 2. HTTP Client Pattern (Sync → Async Migration)

**Analog:** `app/plugins/release_creator.py` (lines 14–16, 49–78) and `app/plugins/jira_tracker.py` (lines 15–17, 28–93)

**Existing pattern (synchronous `requests`):**

From `release_creator.py` lines 14–16, 49–78:
```python
import requests as _requests
from requests.auth import HTTPBasicAuth
from jira import JIRA, JIRAError

SERVER = f"https://{DOMAIN}"
_jira_client: JIRA | None = None

def _jira() -> JIRA:
    """Lazy-init JIRA client from saved config."""
    global _jira_client
    if _jira_client is None:
        c = config.load_jira_config()
        _jira_client = JIRA(server=SERVER,
                            basic_auth=(c.get("email", ""), c.get("token", "")))
    return _jira_client

def _raw_auth():
    c = config.load_jira_config()
    return HTTPBasicAuth(c.get("email", ""), c.get("token", ""))

_HDR = {"Accept": "application/json", "Content-Type": "application/json"}

def _raw_get(path, **kw):
    return _requests.get(f"{SERVER}/rest/api/2/{path}",
                         headers=_HDR, auth=_raw_auth(), **kw)

def _raw_post(path, body):
    return _requests.post(f"{SERVER}/rest/api/2/{path}",
                          headers=_HDR, auth=_raw_auth(), json=body)
```

From `jira_tracker.py` lines 82–93:
```python
def _auth():
    c = config.load_jira_config()
    return HTTPBasicAuth(c.get("email", ""), c.get("token", ""))

def _headers():
    return {"Accept": "application/json", "Content-Type": "application/json"}

def _api(method, path, **kw):
    url = f"https://{DOMAIN}/rest/api/3/{path}"
    return getattr(_req, method)(url, headers=_headers(), auth=_auth(), **kw)
```

**New pattern (async `httpx`)** — replace the above with:

```python
import httpx

DOMAIN = "teltonika-telematics.atlassian.net"
SERVER = f"https://{DOMAIN}"

_http_client: httpx.AsyncClient | None = None

async def _get_client() -> httpx.AsyncClient:
    """Lazy-init a shared httpx AsyncClient for Jira REST API v3."""
    global _http_client
    if _http_client is None:
        c = config.load_jira_config()
        _http_client = httpx.AsyncClient(
            base_url=f"https://{DOMAIN}/rest/api/3/",
            auth=httpx.BasicAuth(c.get("email", ""), c.get("token", "")),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=httpx.Timeout(30.0),
        )
    return _http_client

async def _close_client():
    """Close the shared httpx client (called on shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None

async def _api_get(path: str, **kwargs) -> dict:
    client = await _get_client()
    resp = await client.get(path, **kwargs)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()

async def _api_post(path: str, body: dict, **kwargs) -> dict:
    client = await _get_client()
    resp = await client.post(path, json=body, **kwargs)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()
```

**Key differences from existing pattern:**
- Use `httpx.AsyncClient` instead of `requests.Session`
- Use `httpx.BasicAuth` instead of `requests.auth.HTTPBasicAuth`
- All HTTP calls must be `await`ed
- Client must be closed on shutdown (`close_client()` called from `shutdown()`)
- Jira API v3 (`/rest/api/3/`) instead of v2 for consistency with `jira_tracker.py`

---

### 3. Config Access Pattern (Jira Credentials)

**Analog:** `app/plugins/release_creator.py` lines 52–59 and `app/plugins/jira_tracker.py` lines 31–37

**Exact pattern — reading Jira credentials:**

```python
from app import config

def _jira() -> JIRA:
    """Lazy-init a JIRA client from saved config."""
    global _jira_client
    if _jira_client is None:
        c = config.load_jira_config()                    # <-- returns dict
        _jira_client = JIRA(server=SERVER,
                            basic_auth=(c.get("email", ""), c.get("token", "")))
    return _jira_client
```

**For the new plugin (async httpx variant):**

```python
from app import config

async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        c = config.load_jira_config()                    # <-- exact same call
        _http_client = httpx.AsyncClient(
            base_url=f"https://{DOMAIN}/rest/api/3/",
            auth=httpx.BasicAuth(c.get("email", ""), c.get("token", "")),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    return _http_client
```

**What `config.load_jira_config()` does** (from `app/config.py` lines 90–97):
```python
JIRA_CFG_PATH = os.path.join(ROOT_DIR, "third_party", "jira-time-tracker", "jira_config.json")

def load_jira_config() -> dict:
    if os.path.exists(JIRA_CFG_PATH):
        try:
            with open(JIRA_CFG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}
```

The returned dict typically has keys: `email`, `token`, `meeting_ticket`, `tickets_folder`, `teammates`, `cache_ttl_minutes`.

**`config.load()` (general settings)** is also available from `app/config.py` lines 42–48:
```python
def load() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return dict(_cache)
    return _read_disk()
```

**Adaptation notes:** The new plugin uses `config.load_jira_config()` in exactly the same way existing plugins do — no change needed for the config access pattern itself. The only change is using those credentials to authenticate `httpx` instead of `requests`/`jira.JIRA`.

---

### 4. Route Registration Pattern

**Analog:** `app/plugins/release_creator.py` lines 240–414 and `app/plugins/jira_tracker.py` lines 256–656

**Pattern:** All routes are nested closures inside `register_routes(self, app: FastAPI)`. Routes use `@app.get/post/put/delete` decorators directly on the `app` instance.

```python
def register_routes(self, app: FastAPI):

    @app.get("/api/competence/status")
    async def comp_status():
        return {"ok": True}

    @app.get("/api/competence/foo/{id}")
    async def comp_get_foo(id: str):
        data = await _api_get(f"issue/{id}")
        return data

    @app.post("/api/competence/analyze")
    async def comp_analyze(req: AnalyzeReq, background_tasks: BackgroundTasks):
        background_tasks.add_task(_run_analysis, req)
        return {"status": "accepted"}
```

**Key conventions (from all existing plugins):**
- Route paths are always `/api/{plugin_id}/...`
- Route handler functions are `async def`
- Pydantic models are injected as route parameters (FastAPI auto-validates)
- Query parameters are declared as function arguments (e.g., `limit: int = 500`)
- Error handling uses `raise HTTPException(status_code, message)`

---

### 5. Error Handling Pattern

**Analog:** `app/plugins/release_creator.py` lines 262–264, 300–301, 393–395 and `app/plugins/jira_tracker.py` lines 316–317, 355–357

**Primary pattern** — wrapping Jira library errors as HTTP exceptions:

From `release_creator.py` lines 262–264:
```python
try:
    issue = _jira().issue(key, fields="summary")
except JIRAError as e:
    raise HTTPException(e.status_code or 400, str(e))
```

From `jira_tracker.py` lines 355–357:
```python
try:
    raw = _jira().search_issues(jql, maxResults=50, fields="summary,status,priority,attachment")
except JIRAError as e:
    raise HTTPException(e.status_code or 500, str(e))
```

**Direct HTTP response checks** (for raw REST calls):

From `release_creator.py` lines 393–395:
```python
r = _raw_post("issue", {"fields": fields})
if not r.ok:
    raise HTTPException(r.status_code, r.text)
```

From `jira_tracker.py` lines 316–317:
```python
r = _api("get", "user/search", params={"query": query, "maxResults": 10})
if not r.ok:
    raise HTTPException(r.status_code, r.text)
```

**New pattern for async httpx (in `competence.py`):**

Since `httpx` raises `httpx.HTTPStatusError` for 4xx/5xx responses (when using `raise_for_status()` or checking manually):

```python
async def _api_get(path: str, **kwargs) -> dict:
    client = await _get_client()
    resp = await client.get(path, **kwargs)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()

# Or, using httpx's built-in raise:
try:
    resp = await client.get(path)
    resp.raise_for_status()
    return resp.json()
except httpx.HTTPStatusError as e:
    raise HTTPException(e.response.status_code, str(e))
```

**Non-fatal error pattern** (from `release_creator.py` lines 400–403):
```python
try:
    j.create_issue_link(LINK_TYPE_NAME, new_key, req.prev_ticket_key)
except JIRAError:
    pass  # non-fatal
```

**Validation errors:**
```python
if not secs or secs <= 0:
    raise HTTPException(400, "Invalid time format")
```

---

### 6. Pydantic Model Pattern

**Analog:** `app/plugins/release_creator.py` lines 210–231 and `app/plugins/jira_tracker.py` lines 98–122

**Pattern:** Request models are flat `BaseModel` subclasses defined at module level (before the plugin class).

From `release_creator.py` lines 210–215:
```python
class VersionReq(BaseModel):
    name: str
    description: str = ""
    start_date: Optional[str] = None
    release_date: Optional[str] = None
```

From `jira_tracker.py` lines 98–109:
```python
class WorklogReq(BaseModel):
    issue_key: str
    time_spent: str           # e.g. "1h 30m", "45m"
    comment: str = ""
    started: Optional[str] = None   # ISO date YYYY-MM-DD or full datetime
```

From `jira_tracker.py` lines 112–120:
```python
class JiraConfigReq(BaseModel):
    url: Optional[str] = ""
    email: str
    api_token: str
    meeting_ticket: Optional[str] = ""
    tickets_folder: Optional[str] = None
    teammates: Optional[list] = None   # list of {accountId, displayName}
    cache_ttl_minutes: Optional[int] = None
```

**New pattern for `competence.py`:**

```python
class AnalyzeReq(BaseModel):
    jql: str = ""
    project_key: str = "FMBP"
    days: int = 90
    assignee: Optional[str] = None

class CompetenceEntry(BaseModel):
    ticket_key: str
    summary: str
    assignee: str
    status: str
    time_spent_seconds: int
    component: str = ""

class PerformanceSummary(BaseModel):
    assignee: str
    ticket_count: int
    total_hours: float
    components: List[str]
```

---

### 7. Database Pattern — SQLite (NO ANALOG)

**Status:** This is the FIRST plugin in the project to use a database. No existing analog exists.

**Specification for the new pattern:**

```python
import sqlite3
import os
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "output", "competence.db")

def _get_db() -> sqlite3.Connection:
    """Get a thread-safe SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def _init_db():
    """Create tables if they don't exist."""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_key TEXT NOT NULL,
            assignee TEXT,
            status TEXT,
            time_spent_seconds INTEGER DEFAULT 0,
            component TEXT DEFAULT '',
            fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(ticket_key, fetched_at)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticket_history_assignee ON ticket_history(assignee)")
    conn.commit()
    conn.close()
```

**Important note:** SQLite connections are NOT async-safe. Since FastAPI runs in an async event loop, database calls should be wrapped in `asyncio.to_thread()`:

```python
import asyncio

async def _db_execute(query: str, params: tuple = ()):
    """Run a DB operation in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(_db_execute_sync, query, params)

def _db_execute_sync(query: str, params: tuple = ()):
    conn = _get_db()
    try:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.fetchall()
    finally:
        conn.close()
```

**Alternative (aiosqlite):** If you prefer an async-native approach, add `aiosqlite` to `requirements.txt`:

```python
# requirements.txt addition:
# aiosqlite

import aiosqlite

async def _get_db() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

---

### 8. Background Task Pattern (NO ANALOG)

**Status:** FastAPI `BackgroundTasks` has not been used in any existing plugin. The current plugins use `threading.Thread(daemon=True)` for background work (e.g., `log_parser.py` line 583, `universal_tester_tool.py` line 1208).

**Specification for the new pattern (BackgroundTasks):**

```python
from fastapi import BackgroundTasks

class CompetencePlugin(ToolkitPlugin):
    ...

    def register_routes(self, app: FastAPI):

        @app.post("/api/competence/sync")
        async def comp_sync(req: SyncReq, background_tasks: BackgroundTasks):
            # Schedule a long-running Jira fetch in the background
            background_tasks.add_task(_fetch_and_cache_data, req)
            return {"status": "accepted", "message": "Sync started"}

async def _fetch_and_cache_data(req: SyncReq):
    """Runs in background after the response is sent."""
    try:
        client = await _get_client()
        # ... do long fetch, process, write to SQLite ...
    except Exception as e:
        # Log error (no request context available in background task)
        print(f"[competence] Background sync failed: {e}")
```

**Or, for status tracking (similar to `log_parser.py` lines 72–73, 564–584):**

```python
import uuid

_sync_jobs: dict[str, dict] = {}

@app.post("/api/competence/sync")
async def comp_sync(req: SyncReq, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    _sync_jobs[job_id] = {"status": "pending", "result": None}
    background_tasks.add_task(_do_sync, job_id, req)
    return {"job_id": job_id, "status": "pending"}

@app.get("/api/competence/sync/{job_id}")
async def comp_sync_status(job_id: str):
    job = _sync_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job

async def _do_sync(job_id: str, req: SyncReq):
    try:
        _sync_jobs[job_id]["status"] = "running"
        # ... fetch + store ...
        _sync_jobs[job_id]["status"] = "done"
    except Exception as e:
        _sync_jobs[job_id]["status"] = "error"
        _sync_jobs[job_id]["result"] = str(e)
```

---

### 9. Plugin Auto-Discovery (No change needed)

**Analog:** `app/main.py` lines 29–47

The `_discover_plugins()` function automatically imports every module in `app/plugins/` and collects any top-level `plugin` attribute that is an instance of `ToolkitPlugin`. Simply creating `app/plugins/competence.py` with a `plugin = CompetencePlugin()` at the bottom is sufficient — no registration needed.

From `app/main.py` lines 29–47:
```python
def _discover_plugins() -> list[ToolkitPlugin]:
    """Import every module in app.plugins and collect `plugin` instances."""
    plugins_pkg = importlib.import_module("app.plugins")
    plugins_dir = os.path.dirname(plugins_pkg.__file__)
    found: list[ToolkitPlugin] = []

    for info in pkgutil.iter_modules([plugins_dir]):
        if info.name in ("__init__", "base"):
            continue
        try:
            mod = importlib.import_module(f"app.plugins.{info.name}")
            obj = getattr(mod, "plugin", None)
            if isinstance(obj, ToolkitPlugin):
                found.append(obj)
        except Exception as exc:
            print(f"[warn] Failed to load plugin '{info.name}': {exc}")

    found.sort(key=lambda p: p.order)
    return found
```

---

## Shared Patterns

### Authentication
**Source:** `app/plugins/release_creator.py` lines 52–59, `app/plugins/jira_tracker.py` lines 31–37
**Apply to:** `competence.py` — HTTP client initialization

```python
c = config.load_jira_config()
# Use c.get("email") and c.get("token") for BasicAuth
```

### Config Access (General)
**Source:** `app/config.py` lines 42–48, 90–97
**Apply to:** `competence.py` — reading Jira credentials and general settings

```python
from app import config
jira_cfg = config.load_jira_config()  # {"email": "...", "token": "..."}
app_cfg = config.load()               # all toolkit_settings.json keys
```

### Route Naming Convention
**Source:** All existing plugins
**Apply to:** `competence.py`

Format: `/api/{plugin.id}/{resource}[/{param}]`

### Response Format
**Source:** All existing plugins
**Apply to:** `competence.py`

Simple JSON dicts: `{"ok": True, "data": ...}`, `{"ok": False, "msg": "reason"}`, or bare data dicts.

### Module-Level Plugin Singleton
**Source:** `release_creator.py` line 415, `jira_tracker.py` line 657, all others
**Apply to:** `competence.py`

```python
plugin = CompetencePlugin()  # MUST be at module level, ONE instance
```

---

## No Analog Found

| Pattern | Reason | Recommendation |
|---------|--------|----------------|
| **Async HTTP client (httpx)** | All existing plugins use synchronous `requests` | Use `httpx.AsyncClient` with lazy-init, close on shutdown. See §2 above. |
| **SQLite database** | No plugin currently persists to a database | Use `sqlite3` with `asyncio.to_thread()` or add `aiosqlite`. See §7 above. |
| **FastAPI BackgroundTasks** | Existing plugins use `threading.Thread` for background work | Use `BackgroundTasks.add_task()` for fire-and-forget. See §8 above. |

---

## Metadata

**Analog search scope:** `app/plugins/*.py` (all 8 plugin files), `app/main.py`, `app/config.py`, `app/plugins/base.py`
**Files scanned:** 11
**Pattern extraction date:** 2026-06-17
