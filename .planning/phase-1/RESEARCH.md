# Phase 1: Competence & Performance Plugin (Backend) - Research

**Researched:** 2026-06-17
**Domain:** Jira changelog analysis + SQLite caching + FastAPI plugin architecture
**Confidence:** HIGH

## Summary

Phase 1 delivers a new Alps Toolkit plugin (`app/plugins/competence.py`) that tracks developer bug return rates by analyzing Jira issue changelog histories. The plugin uses the existing `ToolkitPlugin` base class, follows the exact auth/routing patterns from `release_creator.py` and `jira_tracker.py`, and introduces a new `httpx`-based async HTTP client for Jira REST API calls. A SQLite database provides persistent cache storage with WAL mode, and pandas handles quarterly metric aggregation.

**Primary recommendation:** Follow the `release_creator.py` / `jira_tracker.py` patterns exactly — same auth (`config.load_jira_config()` + `HTTPBasicAuth`), same route registration (inner `async def` functions with `@app.get`/`@app.post` decorators), same error handling (`HTTPException`), and same module-level `plugin = CompetencePlugin()` auto-discovery. The only new dependency is `httpx`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Plugin auto-discovery | Backend (FastAPI app factory) | — | `main.py::_discover_plugins()` scans `app/plugins/` for `plugin` instances |
| SQLite cache | Backend (plugin module) | — | Plugin owns its own SQLite DB file; no external DB service needed |
| Jira changelog fetching | Backend (plugin via httpx) | Jira Cloud API | Plugin is the HTTP client; Jira Cloud is the data source |
| State machine parsing | Backend (plugin module) | — | Pure in-process logic processing changelog items |
| API endpoints | Backend (FastAPI routes) | — | Routes registered via `register_routes()` on the FastAPI app |
| Metric calculation (pandas) | Backend (plugin module) | — | In-process pandas DataFrame operations |

## User Constraints

No CONTEXT.md found — all decisions are at planner's discretion. No locked decisions constrain research.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FR1 | Plugin auto-discovery via ToolkitPlugin base class | Class extends `ToolkitPlugin`, `plugin = CompetencePlugin()` at module level; auto-discovered by `main.py::_discover_plugins()` |
| FR2 | SQLite cache (sync_state + transitions tables, WAL mode, indexes) | Python stdlib `sqlite3`; WAL via `PRAGMA journal_mode=WAL`; CREATE TABLE patterns from analysis below |
| FR3 | Jira changelog fetching via httpx async client with BasicAuth | `httpx.AsyncClient` + `httpx.BasicAuth` using `config.load_jira_config()` credentials; REST API v3 endpoint |
| FR4 | Attempt/Return state machine parsing changelog histories | Pure Python state machine over changelog `items[].fromString -> toString` transitions; pattern detailed below |
| FR5 | Three API endpoints: GET /api/competence/stats, POST /api/competence/sync, GET /api/competence/sync/status | FastAPI route decorators inside `register_routes()`; Pydantic models for request bodies |
| FR6 | Pandas grouping by 2Q frequency for metric calculation | `pandas` already in `requirements.txt`; `df.groupby(pd.Grouper(key='date', freq='2Q'))` pattern |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | (existing) | Route registration, HTTP server | Already used by all plugins; `register_routes(app: FastAPI)` pattern |
| `app.plugins.base.ToolkitPlugin` | (existing) | Plugin base class | Required for auto-discovery; all plugins extend this |
| `app.config` | (existing) | Jira config loading | `load_jira_config()` reads `third_party/jira-time-tracker/jira_config.json` with email/token |
| httpx | ~0.28.x (latest stable) | Async HTTP client for Jira REST API v3 | NOT in `requirements.txt` yet — must be added. Replaces sync `requests` for async changelog fetching |
| sqlite3 | (stdlib) | Persistent cache storage | Built-in, no install needed. WAL mode for concurrent reads |
| pandas | (existing) | Metric aggregation by 2Q frequency | Already in `requirements.txt`; used by project |
| pydantic | (existing via FastAPI) | Request body validation | `from pydantic import BaseModel` — already used by `release_creator.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `asyncio` | (stdlib) | Async coordination for sync operations | Background sync tasks, async route handlers |
| `threading` | (stdlib) | Thread-safe cache operations | SQLite connection management across async boundaries |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx | `aiohttp` | httpx matches existing `requests` API shape (same `HTTPBasicAuth`, same `auth=` kwarg), cleaner migration path from sync `requests` |
| SQLite | file-based JSON cache | SQLite provides proper indexing, WAL concurrency, and queryability; JSON cache would require hand-rolling all query logic |
| Pandas 2Q grouping | pure Python aggregation | Pandas already in project; `Grouper` with `freq='2Q'` handles edge cases (quarter boundaries, partial quarters) |

**Installation:**
```bash
pip install httpx
```

**Version verification:**
```bash
pip index versions httpx  # verify latest before adding to requirements.txt
```

## Package Legitimacy Audit

> Only one new package is introduced: `httpx`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| httpx | PyPI | 6+ yrs | ~100M+/mo | github.com/encode/httpx | N/A (slopcheck unavailable) | Approved — [VERIFIED: PyPI, official project] |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*Note: slopcheck was not available in this environment. `httpx` is a well-established project by the encode organization (same maintainers as Starlette/Uvicorn which are already in `requirements.txt`). Package is verified via PyPI existence and community standing.*

## Architecture Patterns

### System Architecture Diagram

```
                         ┌──────────────────────────┐
                         │    FastAPI Application    │
                         │      (app/main.py)        │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │   _discover_plugins()     │
                         │   scans app/plugins/*.py  │
                         └────────────┬─────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                  │
           ┌───────▼──────┐  ┌──────▼──────┐   ┌───────▼──────┐
           │ release_creator│  │  jira_tracker│   │  competence  │ ◄── NEW
           │   plugin       │  │    plugin    │   │   plugin     │
           └───────────────┘  └──────────────┘   └───────┬──────┘
                                                          │
              ┌───────────────────────────────────────────┼──────────────────────────────┐
              │                                           │                              │
    ┌─────────▼──────────┐                  ┌─────────────▼──────────┐        ┌─────────▼─────────┐
    │  GET /api/         │                  │  POST /api/            │        │  GET /api/         │
    │  competence/stats  │                  │  competence/sync       │        │  competence/sync/   │
    │                    │                  │                        │        │  status             │
    └─────────┬──────────┘                  └─────────────┬──────────┘        └─────────┬─────────┘
              │                                           │                              │
              │                                    ┌──────▼──────┐                       │
              │                                    │  Sync Engine │                       │
              │                                    │ (background) │                       │
              │                                    └──────┬──────┘                       │
              │                                           │                              │
              │                              ┌────────────▼────────────┐                 │
              │                              │   httpx.AsyncClient      │                 │
              │                              │   GET /rest/api/3/       │                 │
              │                              │   issue/{key}/changelog  │                 │
              │                              └────────────┬────────────┘                 │
              │                                           │                              │
              │                              ┌────────────▼────────────┐                 │
              │                              │   State Machine Parser   │                 │
              │                              │   (changelog items ->    │                 │
              │                              │    attempt/return pairs) │                 │
              │                              └────────────┬────────────┘                 │
              │                                           │                              │
              └───────────────────────────────────────────┼──────────────────────────────┘
                                                          │
                                              ┌───────────▼───────────┐
                                              │     SQLite Cache       │
                                              │  ┌─────────────────┐   │
                                              │  │ sync_state       │   │
                                              │  │ transitions      │   │
                                              │  └─────────────────┘   │
                                              │  WAL mode, indexed     │
                                              └───────────┬───────────┘
                                                          │
                                              ┌───────────▼───────────┐
                                              │    Pandas Aggregation  │
                                              │    (2Q frequency)      │
                                              └───────────────────────┘
```

### Recommended Project Structure
```
alps-toolkit/
├── app/
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── base.py              # ToolkitPlugin (unchanged)
│   │   ├── competence.py        # NEW — CompetencePlugin class
│   │   └── ... (existing plugins)
│   ├── config.py                # (unchanged — used by competence.py)
│   └── main.py                  # (unchanged — auto-discovers competence.py)
├── data/                        # NEW (or use configurable db_path)
│   └── competence_cache.db      # SQLite database
├── requirements.txt             # MODIFIED — add httpx
└── third_party/
    └── jira-time-tracker/
        └── jira_config.json     # (unchanged — read by competence.py)
```

### Pattern 1: Plugin Registration (ToolkitPlugin Subclass)

**What:** Every plugin is a class extending `ToolkitPlugin` with class-level id/name/icon/order, a `register_routes(app)` method, and a module-level `plugin = MyClass()` instance.

**When to use:** Creating any new Alps Toolkit plugin.

**Example (from `app/plugins/base.py` lines 28-53):**
```python
# Source: app/plugins/base.py
from app.plugins.base import ToolkitPlugin
from fastapi import FastAPI

class CompetencePlugin(ToolkitPlugin):
    id = "competence"
    name = "Competence & Performance"
    icon = "📊"                   # or appropriate emoji
    order = 60                    # after release_creator(50), jira_tracker(40)

    def register_routes(self, app: FastAPI):
        # Inner async functions with @app decorators...
        pass

    def startup(self):
        """Called once after all plugins are registered. Initialize DB here."""
        pass

# Module-level auto-discovery instance
plugin = CompetencePlugin()
```

### Pattern 2: Jira Auth + REST API Calling

**What:** Read credentials from `config.load_jira_config()`, construct HTTPBasicAuth, call Jira REST API v3 endpoints.

**When to use:** Any Jira API interaction.

**Example (adapted from `release_creator.py` lines 62-78 and `jira_tracker.py` lines 82-93):**
```python
# Source: app/plugins/release_creator.py (auth pattern) +
#         app/plugins/jira_tracker.py (API v3 endpoint pattern)
from app import config
from requests.auth import HTTPBasicAuth  # for sync requests
# For ASYNC:
import httpx

DOMAIN = "teltonika-telematics.atlassian.net"
SERVER = f"https://{DOMAIN}"

def _auth():
    """Return (email, token) tuple for httpx.BasicAuth."""
    c = config.load_jira_config()
    return (c.get("email", ""), c.get("token", ""))

async def _fetch_changelog(issue_key: str):
    """Fetch changelog for a single issue via async httpx."""
    email, token = _auth()
    async with httpx.AsyncClient(
        base_url=f"{SERVER}/rest/api/3/",
        auth=httpx.BasicAuth(email, token),
        headers={"Accept": "application/json"},
    ) as client:
        r = await client.get(f"issue/{issue_key}/changelog")
        r.raise_for_status()
        return r.json()
```

### Pattern 3: register_routes() Inner-Function Structure

**What:** Inside `register_routes(self, app: FastAPI)`, define inner `async def` functions and decorate them with route decorators. Use Pydantic `BaseModel` subclasses for POST request bodies.

**When to use:** Defining all plugin API endpoints.

**Example (from `release_creator.py` lines 240-413):**
```python
# Source: app/plugins/release_creator.py (register_routes pattern)
from pydantic import BaseModel
from fastapi import HTTPException

class SyncRequest(BaseModel):
    assignee: str = ""           # currentUser() if empty
    max_results: int = 100

def register_routes(self, app: FastAPI):

    @app.get(f"/api/{self.id}/stats")
    async def competence_stats():
        try:
            # ... read from SQLite, compute with pandas
            return {"ok": True, "data": []}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post(f"/api/{self.id}/sync")
    async def competence_sync(req: SyncRequest):
        try:
            # ... trigger sync
            return {"ok": True}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get(f"/api/{self.id}/sync/status")
    async def competence_sync_status():
        # ... read sync_state from SQLite
        return {"ok": True, "last_sync": None, "in_progress": False}
```

### Pattern 4: SQLite with WAL Mode + Thread Safety

**What:** Use Python's built-in `sqlite3` with `check_same_thread=False` (for FastAPI multi-worker compatibility), WAL journal mode, and proper indexing.

**When to use:** Any persistent data storage within a plugin.

**Example:**
```python
# Source: Python sqlite3 docs + WAL best practices
import sqlite3
import threading
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "competence_cache.db")

_lock = threading.Lock()

def _get_db() -> sqlite3.Connection:
    """Get a thread-safe SQLite connection in WAL mode."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def _init_db():
    """Create tables if they don't exist."""
    with _lock:
        conn = _get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sync_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_sync_ts TEXT,
                in_progress INTEGER DEFAULT 0,
                issues_synced INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_key TEXT NOT NULL,
                assignee_account_id TEXT,
                assignee_name TEXT,
                from_status TEXT,
                to_status TEXT,
                transition_date TEXT NOT NULL,
                is_return INTEGER DEFAULT 0,
                quarter_label TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_transitions_assignee
                ON transitions(assignee_account_id);
            CREATE INDEX IF NOT EXISTS idx_transitions_quarter
                ON transitions(quarter_label);
            CREATE INDEX IF NOT EXISTS idx_transitions_issue
                ON transitions(issue_key);
        """)
        conn.commit()
```

### Pattern 5: State Machine for Attempt/Return Detection

**What:** Parse changelog `items` arrays to detect when an issue transitions from a testing/verification status back to a development status ("return"). The Jira changelog endpoint returns items with `field` = "status", each containing `fromString` and `toString` (the human-readable status names).

**When to use:** Analyzing developer bug introduction rates from changelog data.

**Example (changelog item structure):**
```json
// Source: Jira REST API v3 changelog response
{
  "values": [
    {
      "id": "12345",
      "author": {"accountId": "712020:abc123", "displayName": "Dev Name"},
      "created": "2025-01-15T10:30:00.000+0000",
      "items": [
        {
          "field": "status",
          "fieldtype": "jira",
          "fromString": "In Development",
          "toString": "For Testing"
        }
      ]
    }
  ]
}
```

**Status categories for state machine (from Jira workflow analysis):**

| Status Name | Category | Role in State Machine |
|-------------|----------|----------------------|
| "New" | Backlog | Starting point; ignore until dev starts |
| "In Development" / "In Progress" | Development | Return target — issue came BACK here from testing |
| "Developed" / "Ready for Testing" | Development | Exit from dev work; next stop is testing |
| "For Testing" / "In Testing" | Testing | An "attempt" starts when issue enters this state |
| "Test Failed" / "Testing Failed" | Testing | Implicit return — failed test means back to dev |
| "Gathering Information" / "To Do" | Backlog | Backlog states — transitions here from testing = return |
| "Done" / "Closed" / "Resolved" | Complete | Terminal — ignore after this |

**State machine algorithm:**
```python
# Source: derived from Jira changelog API structure
RETURN_FROM = {"For Testing", "In Testing", "Test Failed", "Testing Failed"}
RETURN_TO = {"In Development", "In Progress", "Gathering Information", "To Do", "New"}

def parse_transitions(changelog: dict) -> list[dict]:
    """
    Parse a Jira issue changelog into attempt/return transitions.
    
    An "attempt" = entering a testing status (For Testing, In Testing)
    A "return"  = leaving a testing status back to development
    """
    transitions = []
    for entry in changelog.get("values", []):
        author = entry.get("author", {})
        items = entry.get("items", [])
        created = entry.get("created", "")
        
        for item in items:
            if item.get("field") != "status":
                continue
            
            from_status = item.get("fromString", "")
            to_status = item.get("toString", "")
            
            # Detect return: leaving testing → going to dev/backlog
            is_return = (from_status in RETURN_FROM and 
                        to_status in RETURN_TO)
            
            transitions.append({
                "issue_key": None,  # filled by caller
                "assignee_account_id": author.get("accountId", ""),
                "assignee_name": author.get("displayName", ""),
                "from_status": from_status,
                "to_status": to_status,
                "transition_date": created,
                "is_return": int(is_return),
            })
    return transitions
```

### Pattern 6: Pandas 2Q Grouping

**What:** Use `pd.Grouper` with quarterly frequency to aggregate return counts.

**When to use:** Computing metrics for GET /api/competence/stats.

**Example:**
```python
# Source: pandas documentation — Grouper with quarterly frequency
import pandas as pd

def compute_stats(transitions: list[dict]) -> dict:
    """
    Compute bug return rate per developer, grouped by 2-quarter windows.
    """
    df = pd.DataFrame(transitions)
    if df.empty:
        return {"developers": [], "periods": []}
    
    df["transition_date"] = pd.to_datetime(df["transition_date"])
    
    # 2Q grouping: label each row with its 2-quarter period
    df["quarter_bucket"] = df["transition_date"].dt.to_period("2Q")
    
    # Attempts: count transitions INTO testing
    attempts = df[df["to_status"].isin({"For Testing", "In Testing"})]
    
    # Returns: count flagged returns
    returns = df[df["is_return"] == 1]
    
    # Per developer, per 2Q period
    attempt_counts = attempts.groupby(
        ["assignee_account_id", "assignee_name", "quarter_bucket"]
    ).size().reset_index(name="attempts")
    
    return_counts = returns.groupby(
        ["assignee_account_id", "assignee_name", "quarter_bucket"]
    ).size().reset_index(name="returns")
    
    # Merge and compute rate
    stats = pd.merge(
        attempt_counts, return_counts,
        on=["assignee_account_id", "assignee_name", "quarter_bucket"],
        how="left"
    )
    stats["returns"] = stats["returns"].fillna(0).astype(int)
    stats["return_rate"] = stats["returns"] / stats["attempts"]
    
    return stats.to_dict(orient="records")
```

### Anti-Patterns to Avoid
- **Global mutable state without locking:** SQLite connections shared across async tasks MUST use `threading.Lock` or connection-per-request. Without locking, WAL mode can still produce "database is locked" errors on writes.
- **Using sync `requests` in async routes:** Existing plugins use sync `requests` (which blocks the event loop). The competence plugin SHOULD use `httpx.AsyncClient` for non-blocking HTTP. This is the key architectural improvement over existing `release_creator.py` / `jira_tracker.py`.
- **Storing config inline:** Never hardcode Jira credentials or server URLs. Always use `config.load_jira_config()` and `DOMAIN`/`SERVER` constants following existing patterns.
- **Skipping `__init__.py` discovery:** Don't forget the `plugin = CompetencePlugin()` assignment at module level — without it, `_discover_plugins()` won't find the plugin.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async HTTP client | Custom asyncio HTTP with urllib | `httpx.AsyncClient` | Connection pooling, retry logic, timeout handling, auth middleware — all battle-tested |
| SQLite connection management | Custom connection pool | `sqlite3` with `check_same_thread=False` + `threading.Lock` | Sufficient for single-process FastAPI; connection pooling only needed for multi-process |
| Date range / quarter math | Custom datetime arithmetic | `pandas.Grouper(freq='2Q')` + `pd.to_datetime()` | Handles quarter boundaries, partial periods, leap years correctly |
| Jira BasicAuth | Custom auth header construction | `httpx.BasicAuth(email, token)` | Same API shape as existing `HTTPBasicAuth` from `requests`; handles encoding correctly |
| HTTP error handling | Custom status code checking | `r.raise_for_status()` or `HTTPException(status_code, detail)` | Consistent with existing plugin patterns |

**Key insight:** The competence plugin bridges two patterns in the codebase — the older sync `requests` pattern from `release_creator.py`/`jira_tracker.py`, and a new async `httpx` pattern that's architecturally superior for non-blocking I/O. The sync pattern should NOT be emulated; use `httpx` for all Jira API calls.

## Common Pitfalls

### Pitfall 1: Blocking the Event Loop with Sync HTTP
**What goes wrong:** Using `requests.get()` inside an `async def` route handler blocks the FastAPI event loop, killing concurrency.
**Why it happens:** Existing plugins (`release_creator.py`, `jira_tracker.py`) use sync `requests` — tempting to copy-paste.
**How to avoid:** Use `httpx.AsyncClient` exclusively. All Jira API calls go through async HTTP.
**Warning signs:** Slow response times under concurrent requests; only one request processed at a time.

### Pitfall 2: SQLite "database is locked" Errors
**What goes wrong:** Multiple async tasks writing to SQLite simultaneously.
**Why it happens:** WAL mode allows concurrent reads but only one writer at a time. Without a lock, multiple tasks attempt simultaneous writes.
**How to avoid:** Wrap all write operations in a `threading.Lock`. Read operations don't need the lock in WAL mode.
**Warning signs:** `sqlite3.OperationalError: database is locked` errors in logs during sync.

### Pitfall 3: Missing module-level `plugin` Variable
**What goes wrong:** Plugin class is defined but never discovered.
**Why it happens:** Forgetting the `plugin = CompetencePlugin()` line at module bottom.
**How to avoid:** Always end plugin files with `plugin = YourPlugin()`. Verify with: check that `/api/plugins` returns the plugin's manifest.
**Warning signs:** Plugin doesn't appear in `main.py` startup output; routes return 404.

### Pitfall 4: Incorrect Jira API Version
**What goes wrong:** Using `/rest/api/2/` (older API) for changelog when v3 has better pagination support.
**Why it happens:** `release_creator.py` uses `/rest/api/2/`; `jira_tracker.py` uses `/rest/api/3/`. The changelog endpoint exists in both but v3 is preferred.
**How to avoid:** Use `/rest/api/3/issue/{key}/changelog` with `startAt` and `maxResults` query params for pagination.
**Warning signs:** Changelog responses missing newer fields; pagination format differences.

### Pitfall 5: Python Path Issues for `app.` Imports
**What goes wrong:** `ModuleNotFoundError: No module named 'app'` when testing the plugin standalone.
**Why it happens:** The project root must be in `sys.path`. `main.py` handles this at startup (lines 20-22), but standalone testing won't.
**How to avoid:** Run the plugin only through the FastAPI app (`python -m uvicorn app.main:create_app`). For testing, add project root to `sys.path`.
**Warning signs:** Import errors when running `python app/plugins/competence.py` directly.

## Code Examples

Verified patterns from the existing codebase:

### Jira Config Loading + Auth (sync pattern, for reference)
```python
# Source: app/plugins/release_creator.py lines 62-65
def _raw_auth():
    """HTTPBasicAuth for raw requests calls."""
    c = config.load_jira_config()
    return HTTPBasicAuth(c.get("email", ""), c.get("token", ""))
```

### Jira Config File Format
```json
// Source: third_party/jira-time-tracker/jira_config.json
{
  "email": "user@domain.com",
  "token": "ATATT3xFfGF0cA...",
  "refresh_interval": 900,
  "meeting_ticket": "FMBP-44552",
  "cache_ttl_minutes": 15,
  "teammates": [...]
}
```

### Route Registration Pattern
```python
# Source: app/plugins/release_creator.py lines 240-269
class ReleaseCreatorPlugin(ToolkitPlugin):
    id = "release"
    name = "Release Creator"
    icon = "🚀"
    order = 50

    def register_routes(self, app: FastAPI):

        @app.get("/api/release/issue/{key}")
        async def rel_issue(key: str):
            try:
                issue = _jira().issue(key, fields="summary")
            except JIRAError as e:
                raise HTTPException(e.status_code or 400, str(e))
            return {"key": issue.key, "summary": issue.fields.summary}
```

### Plugin Auto-Discovery Mechanism
```python
# Source: app/main.py lines 29-47
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

### Lifespan + startup() Call
```python
# Source: app/main.py lines 50-64
@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Startup
    for p in _plugins:
        try:
            p.startup()
        except Exception as exc:
            print(f"[warn] Plugin {p.id} startup error: {exc}")
    yield
    # Shutdown
    for p in _plugins:
        try:
            p.shutdown()
        except Exception as exc:
            print(f"[warn] Plugin {p.id} shutdown error: {exc}")
```

### startup() Used for Initialization
```python
# Source: app/plugins/gps_server.py lines 261-298
def startup(self):
    global _main_loop
    try:
        _main_loop = asyncio.get_running_loop()
    except RuntimeError:
        _main_loop = asyncio.get_event_loop()
    # ... initialize server, start background threads
```

### Jira REST API v3 Pattern (from jira_tracker.py)
```python
# Source: app/plugins/jira_tracker.py lines 91-93
def _api(method, path, **kw):
    url = f"https://{DOMAIN}/rest/api/3/{path}"
    return getattr(_req, method)(url, headers=_headers(), auth=_auth(), **kw)
```

### Pydantic Request Body Model
```python
# Source: app/plugins/release_creator.py lines 210-215
from pydantic import BaseModel

class VersionReq(BaseModel):
    name: str
    description: str = ""
    start_date: Optional[str] = None
    release_date: Optional[str] = None
```

### Error Handling Pattern
```python
# Source: app/plugins/release_creator.py lines 311-319
@app.post("/api/release/version")
async def rel_create_version(req: VersionReq):
    try:
        v = _jira().create_version(...)
    except JIRAError as e:
        raise HTTPException(e.status_code or 400, str(e))
    return {"ok": True, "version": _ver_dict(v)}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sync `requests` for Jira API (`release_creator.py`) | Async `httpx` for new plugins | Now (Phase 1) | Non-blocking I/O; better for sync operations that fetch many issues |
| In-memory dict cache with TTL (`jira_tracker.py`) | SQLite persistent cache | Now (Phase 1) | Survives restarts; queryable; appropriate for changelog data volume |
| Jira REST API v2 (`/rest/api/2/`) | Jira REST API v3 (`/rest/api/3/`) | v3 preferred for new endpoints | Better pagination, newer response format |

**Deprecated/outdated:**
- **`requests` for new plugins:** New plugins should use `httpx` for async compatibility. Existing sync plugins (`release_creator.py`, `jira_tracker.py`) are not required to migrate.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Jira Cloud changelog endpoint (`/rest/api/3/issue/{key}/changelog`) returns `values[]` with `items[].fromString`/`toString` for status transitions | Architecture Patterns (Pattern 5) | The state machine parsing would need adjustment if the field structure differs for the target Jira instance |
| A2 | Status names in the target Jira project match the standard workflow names ("In Development", "For Testing", "Test Failed", etc.) | Architecture Patterns (Pattern 5) | The `RETURN_FROM` and `RETURN_TO` sets would need updating. The plan should include a configurable status mapping or runtime discovery step |
| A3 | `httpx.__version__` ~0.28.x is the current stable version | Standard Stack | Earlier versions lack `AsyncClient` timeout defaults; later versions may change API surface. Exact version should be pinned after verifying |
| A4 | SQLite database file at `data/competence_cache.db` is an acceptable location | Architecture Patterns (Pattern 4) | May need to be configurable via `config.load()` if the project prefers a different data directory |
| A5 | `check_same_thread=False` for SQLite is safe with `threading.Lock` wrapping writes | Architecture Patterns (Pattern 4) | In a multi-worker deployment (multiple gunicorn workers), this won't be sufficient; would need WAL + file locking or a connection-per-worker approach |
| A6 | The competence plugin only needs to fetch changelogs for issues assigned to specific developers (not all project issues) | Phase Requirements | If the scope is project-wide instead, the sync strategy changes significantly (pagination, rate limiting) |

## Open Questions (RESOLVED)

1. **What is the exact set of Jira projects/issue filters to sync?** RESOLVED: JQL is `assignee WAS currentUser() OR reporter = currentUser()`, incremental via `updated >= '{last_sync}'`. No additional request body filters in Phase 1.

2. **What status names does the FMBP project actually use?** RESOLVED: Configurable `RETURN_FROM` and `RETURN_TO` sets in the state machine, with defaults covering standard Jira workflow statuses. Runtime discovery deferred to future iteration.

3. **What is the expected data volume?** RESOLVED: Paginate changelog with `maxResults=100` + `startAt`. Semaphore(5) for concurrency control. Full re-sync on first run (last_sync=NULL), incremental thereafter.

4. **Should the sync run synchronously or as a background task?** RESOLVED: `asyncio.create_task()` spawns `_sync_job()` in background with `in_progress` flag. POST returns immediately with `{"status": "sync_started"}`.

5. **What is the `db_path` for the SQLite cache?** RESOLVED: Co-located with plugin at `app/plugins/competence_cache.db` (user decision). Uses `os.path.dirname(os.path.abspath(__file__))` for path resolution.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | Runtime | ✓ | 3.10.11 | — |
| pandas | FR6 (metric calculation) | ✓ | (installed) | — |
| httpx | FR3 (async HTTP client) | ✗ | — | Must install: `pip install httpx` |
| sqlite3 | FR2 (cache storage) | ✓ | (stdlib) | — |
| FastAPI | FR5 (API endpoints) | ✓ | (installed) | — |
| pydantic | FR5 (request models) | ✓ | (installed via FastAPI) | — |
| Jira Cloud API | FR3 (changelog data) | ✓ | teltonika-telematics.atlassian.net | Requires valid email/token in jira_config.json |
| pytest | Validation | ✗ | — | Must install if tests needed |

**Missing dependencies with no fallback:**
- `httpx` — required for async Jira API calls. Must be added to `requirements.txt` and installed before execution.

**Missing dependencies with fallback:**
- `pytest` — can be installed when tests are written (Wave 0 or later).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (to be installed) |
| Config file | none — see Wave 0 |
| Quick run command | `python -m pytest tests/test_competence.py -x -v` |
| Full suite command | `python -m pytest tests/ -x -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FR1 | Plugin auto-discovered by `_discover_plugins()` | unit | `pytest tests/test_competence.py::test_plugin_discovery -x` | ❌ Wave 0 |
| FR2 | SQLite tables created on startup with WAL mode | unit | `pytest tests/test_competence.py::test_db_init -x` | ❌ Wave 0 |
| FR3 | Changelog fetched from Jira with correct auth headers | integration | `pytest tests/test_competence.py::test_fetch_changelog -x` | ❌ Wave 0 |
| FR4 | State machine correctly detects return transitions | unit | `pytest tests/test_competence.py::test_state_machine_returns -x` | ❌ Wave 0 |
| FR5 | API endpoints return valid JSON with expected keys | integration | `pytest tests/test_competence.py::test_api_stats -x` | ❌ Wave 0 |
| FR6 | Pandas 2Q grouping produces correct aggregates | unit | `pytest tests/test_competence.py::test_pandas_2q_grouping -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_competence.py -x -v` (unit tests)
- **Per wave merge:** `python -m pytest tests/ -x -v` (all plugin tests)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_competence.py` — covers all 6 FRs (unit + integration)
- [ ] `tests/conftest.py` — shared fixtures (mock Jira responses, temp SQLite DB, FastAPI TestClient)
- [ ] `tests/test_competence_changelog_samples/` — sample JSON files representing Jira changelog responses
- [ ] Framework install: `pip install pytest httpx` — neither pytest nor httpx detected in environment

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `httpx.BasicAuth(email, token)` — uses existing Jira API token from `config.load_jira_config()`. Token is a Jira API token, not a password. |
| V3 Session Management | no | Stateless REST API; no sessions |
| V4 Access Control | no | Phase 1 is backend-only; no multi-user access control needed at plugin level |
| V5 Input Validation | yes | Pydantic `BaseModel` for request bodies; validate `issue_key` format (`^[\w-]+$`), sanitize query params |
| V6 Cryptography | no | No cryptographic operations in this phase |

### Known Threat Patterns for FastAPI + SQLite + Jira API

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API token exposure in logs/errors | Information Disclosure | Never log raw auth headers; catch `HTTPException` without echoing full response body |
| SQL injection via dynamic query building | Tampering | Use parameterized queries exclusively (`cursor.execute("SELECT ... WHERE key = ?", [key])`). Never string-format SQL |
| Path traversal via `issue_key` parameter | Tampering | Validate `issue_key` against `^[\w-]+$` regex; reject keys with `.`, `/`, `\` |
| Denial of Service via unbounded sync | Denial of Service | Enforce `max_results` cap on sync requests; add timeout to httpx client; rate-limit Jira API calls |
| Sensitive data in SQLite DB | Information Disclosure | The `transitions` table stores issue keys and assignee info but no credentials. DB file should be in a protected `data/` directory |

## Sources

### Primary (HIGH confidence)
- `app/plugins/base.py` — ToolkitPlugin base class definition, manifest() method, startup()/shutdown() hooks
- `app/plugins/release_creator.py` — Reference plugin: Jira auth pattern (`_raw_auth()`), route registration, Pydantic models, error handling, module-level `plugin = ...` assignment, SERVER/DOMAIN constants
- `app/plugins/jira_tracker.py` — Jira REST API v3 pattern (`_api()`), in-memory cache pattern, config read/write, team member management
- `app/plugins/gps_server.py` — startup() usage pattern, background thread pattern, WebSocket pattern
- `app/main.py` — Plugin auto-discovery (`_discover_plugins()`), lifespan hooks calling `startup()`/`shutdown()`, app factory pattern
- `app/config.py` — `load_jira_config()`, `save_jira_config()`, `load()`, `save()`, `DEFAULTS` dict
- `third_party/jira-time-tracker/jira_config.json` — Live config file format: `email`, `token`, `refresh_interval`, `meeting_ticket`, `cache_ttl_minutes`, `teammates`
- `requirements.txt` — Confirmed: `httpx` NOT present; `pandas` IS present

### Secondary (MEDIUM confidence)
- Jira REST API v3 documentation (assumed structure) — Changelog endpoint: `GET /rest/api/3/issue/{key}/changelog` with `startAt` + `maxResults` pagination
- Python `sqlite3` documentation (stdlib) — WAL mode: `PRAGMA journal_mode=WAL`, `check_same_thread=False`
- `pandas` documentation — `Grouper(freq='2Q')`, `dt.to_period('2Q')` for quarterly bucketing
- `httpx` documentation — `AsyncClient(auth=BasicAuth(...))`, async context manager pattern

### Tertiary (LOW confidence)
- Jira workflow status names for FMBP project — assumed standard names; actual names might differ. Flagged for runtime discovery.
- httpx exact version — not verified via `pip index versions`; recommended to check latest stable before pinning

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all core libraries verified in existing codebase or requirements.txt; only `httpx` is new and is a well-established package
- Architecture: HIGH — all patterns directly observed in existing plugins and `main.py`; auto-discovery, route registration, auth, and config loading are fully documented
- Pitfalls: HIGH — event loop blocking, SQLite locking, module-level variable omission are all patterns that can be verified against the codebase
- State machine logic: MEDIUM — the parsing algorithm is sound based on Jira changelog structure, but specific status names for FMBP project are unverified

**Research date:** 2026-06-17
**Valid until:** 2026-07-17 (30 days — stable domain, no fast-moving dependencies)
