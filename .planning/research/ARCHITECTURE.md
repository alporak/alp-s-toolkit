# Architecture Research: Documentation Search Engine Plugin

**Domain:** Full-text search over internal documentation repos
**Researched:** 2026-07-01
**Confidence:** HIGH (source code verified against existing plugin patterns)

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FastAPI Application                           │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    Plugin Auto-Discovery                        │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │  │
│  │  │competence│ │log_parser│ │jira     │ │ doc_search (NEW) │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────┬──────────┘  │  │
│  └────────────────────────────────────────────────┼───────────────┘  │
│                                                    │                  │
├────────────────────────────────────────────────────┼──────────────────┤
│                    API Routes (/api/doc_search/*)  │                  │
│                                                    ↓                  │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                  DocSearchPlugin Instance                        │ │
│  │  ┌───────────────┐ ┌───────────────┐ ┌──────────────────────┐   │ │
│  │  │ Sync Engine    │ │ Search Engine │ │ Preview / Extraction │   │ │
│  │  │ (asyncio task) │ │ (FTS5 query)  │ │ (format-specific)    │   │ │
│  │  └───────┬───────┘ └───────┬───────┘ └──────────┬───────────┘   │ │
│  │          │                 │                     │               │ │
│  │          └─────────┬───────┴─────────────────────┘               │ │
│  │                    ↓                                              │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │              SQLite FTS5 Index + Metadata                    │ │ │
│  │  │  app/plugins/doc_search_index.db (WAL mode)                  │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                         File System                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐          │
│  │ Repo A (git)   │  │ Repo B (git)   │  │ Repo C (git)   │          │
│  │ .docx .pdf .rst│  │ .doc .drawio   │  │ .graphml .pdf  │          │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘          │
│          │                   │                    │                   │
│          └───────────────────┼────────────────────┘                   │
│                              ↓                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │              Text Extraction Pipeline (module)                    │ │
│  │  python-docx → PyPDF2 → textract → extract text from all formats │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                         Frontend (SPA)                                 │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  app/static/js/doc_search.js (Vanilla JS + core.js)              │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │ │
│  │  │ SearchBar│ │ Results  │ │ Preview  │ │ Sync Button+Status│  │ │
│  │  │ (input)  │ │ (table)  │ │ (iframe) │ │ (button+text)     │  │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  Imported in app.js:  import "./doc_search.js"  (1-line addition)     │
└──────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|---------------|----------------|
| **DocSearchPlugin** | Plugin lifecycle, route registration, state management | `app/plugins/doc_search.py` (~400 lines) |
| **Text Extraction Module** | Format-specific text extraction from 6+ formats | `app/plugins/doc_extraction.py` (~150 lines, separate module imported by plugin) |
| **Sync Engine** | Git pull → traverse files → extract text → upsert FTS5 | `_sync_job()` coroutine in `doc_search.py`, run via `asyncio.create_task()` |
| **Search Engine** | Full-text FTS5 queries with snippet generation | SQLite FTS5 virtual table, `snippet()` function for highlighting |
| **Preview Service** | Extract text from specific file, highlight terms, return HTML | `GET /api/doc_search/preview/{repo_id}/{file_path}` |
| **FTS5 Index** | Indexed content storage, repo metadata, sync state | `app/plugins/doc_search_index.db` (WAL mode) |
| **Frontend SPA** | Search input, result table, preview panel, sync UI | `app/static/js/doc_search.js` (~300 lines, Vanilla JS + core.js) |
| **Config** | Repo paths, sync schedule preferences | `toolkit_settings.json` via `app.config` |

## Plugin Structure

### New Files (all new, zero existing code modified)

```
app/
├── plugins/
│   ├── doc_search.py           # Plugin class + sync engine + search API
│   └── doc_extraction.py       # Text extraction from .docx/.pdf/.doc/.rst/.drawio/.graphml
├── static/
│   └── js/
│       └── doc_search.js       # Frontend SPA (search UI + sync button + preview)
```

### Modified Files (minimal touch — only registration lines)

```
app/
└── static/
    └── js/
        └── app.js              # Add: import "./doc_search.js";
```

**Nothing else modified.** No changes to `main.py`, `config.py`, `base.py`, `__init__.py`, or any existing plugin.

### Why Extraction Is a Separate Module

The text extraction logic is isolated from the plugin class for three reasons:
1. **Testability** — extraction functions can be unit-tested without FastAPI context
2. **Internal API clarity** — the plugin class focuses on orchestration (sync, search, serve), extraction is a pure function call
3. **Size** — 6+ formats each require their own `try/except` extraction logic; keeping them in the plugin file would blow it past 800+ lines

The extraction module exports a simple function signature:
```python
# doc_extraction.py
def extract_text(file_path: str, mime_type: str | None = None) -> str:
    """Extract plain text from a documentation file. Returns empty string on failure."""
    ...
```

## Data Flow

### 1. Sync Flow (Git Pull → Index)

```
POST /api/doc_search/sync
        │
        ▼
asyncio.create_task(_sync_job())
        │
        ├── 1. For each configured repo:
        │       git pull (subprocess)
        │
        ├── 2. Walk repo directory tree
        │       Find files matching: *.docx, *.pdf, *.doc, *.rst, *.drawio, *.graphml
        │       Skip files already indexed (via file_hash)
        │
        ├── 3. For each new/changed file:
        │       extract_text(file_path) → plain text
        │
        ├── 4. Upsert into SQLite FTS5:
        │       INSERT OR REPLACE into fts_index + metadata table
        │       Update sync_state (file_hash, last_synced timestamps)
        │
        └── 5. Update sync_state.sync_progress per step
                POST /api/doc_search/sync/status returns progress JSON
```

### 2. Search Flow

```
GET /api/doc_search/search?q=full+text+search&repo_id=all&limit=50
        │
        ▼
FTS5 MATCH query with snippet() function:
    SELECT repo_id, relative_path, title, snippet(doc_search_fts, 1, '<mark>', '</mark>', '...', 40)
    FROM doc_search_fts
    WHERE doc_search_fts MATCH ?
    ORDER BY rank
    LIMIT ?
        │
        ▼
JSON response:
    [ { repo_id, path, title, snippet: "...<mark>search</mark>...", score } ]
```

### 3. Preview Flow

```
GET /api/doc_search/preview/{repo_id}/{file_path}?q=search+terms
        │
        ├── 1. Read file from disk (repo_id → local path)
        ├── 2. extract_text(file_path) → plain text
        ├── 3. Find query terms in text, extract surrounding context
        ├── 4. Generate HTML with <mark> highlights
        │
        └── HTMLResponse with preview + term highlighting
```

### 4. Frontend Data Flow

```
[User types in search input]
    │
    ▼
debounce 300ms → api("/api/doc_search/search?q=...")
    │
    ▼
Render results table with snippet column
    │
    ▼ (user clicks result row)
api("/api/doc_search/preview/{repo}/{path}?q=...")
    │
    ▼
Render preview in iframe/div with syntax highlighting
```

## API Design

All endpoints follow the existing competence plugin pattern: prefix `/api/{plugin.id}/`.

| Endpoint | Method | Purpose | Example Response |
|----------|--------|---------|-----------------|
| `/api/doc_search/search` | GET | Full-text search with snippets | `[{repo_id, path, title, snippet, score}]` |
| `/api/doc_search/sync` | POST | Trigger git pull + re-index (async) | `{status: "sync_started"}` |
| `/api/doc_search/sync/status` | GET | Current sync progress | `{in_progress, progress: {phase, done, total}}` |
| `/api/doc_search/preview/{repo_id}/{path:path}` | GET | File preview with term highlighting | HTML response (like competence chart) |
| `/api/doc_search/repos` | GET | List configured repos + stats | `[{id, name, path, file_count, last_synced}]` |

### Why These Endpoints

- **search** — core value proposition; required by frontend
- **sync** — manual trigger, follows `POST /api/competence/sync` pattern exactly
- **sync/status** — progress polling, identical pattern to competence
- **preview** — differentiator feature (competitor parity); `HTMLResponse` like competence chart
- **repos** — frontend needs repo names/labels for display and filtering

### Query Parameters for `/search`

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | str | *required* | Search query (FTS5 syntax) |
| `repo_id` | str | `"all"` | Filter to specific repo |
| `limit` | int | `50` | Max results |
| `offset` | int | `0` | Pagination offset |

## Search Index Strategy

### Why SQLite FTS5 (not Whoosh)

1. **Zero additional dependencies** — SQLite is already in the stack; FTS5 is built-in since Python 3.9
2. **In-process** — no separate service to manage; co-located with plugin DB
3. **Proven pattern** — competence plugin already uses SQLite in `app/plugins/`
4. **WAL mode support** — readers don't block writers; search queries run concurrent with sync
5. **`snippet()` function** — built-in match highlighting, no custom logic needed
6. **~3000 files is trivial** — FTS5 handles 100K+ documents effortlessly

### Schema

```sql
-- Sync state (follows competence pattern)
CREATE TABLE IF NOT EXISTS sync_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Repo configuration
CREATE TABLE IF NOT EXISTS repos (
    id       TEXT PRIMARY KEY,        -- short name: "firmware", "hardware", "manuals"
    name     TEXT NOT NULL,           -- display name
    path     TEXT NOT NULL,           -- local filesystem path
    enabled  INTEGER NOT NULL DEFAULT 1
);

-- File metadata (fast lookup for changed files)
CREATE TABLE IF NOT EXISTS file_index (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id       TEXT NOT NULL REFERENCES repos(id),
    relative_path TEXT NOT NULL,
    title         TEXT NOT NULL DEFAULT '',       -- derived from filename
    mime_type     TEXT NOT NULL DEFAULT '',
    file_hash     TEXT NOT NULL DEFAULT '',       -- SHA-256 of file content
    file_size     INTEGER NOT NULL DEFAULT 0,
    last_modified TEXT NOT NULL,                  -- from filesystem
    indexed_at    TEXT NOT NULL,                  -- when this entry was created
    UNIQUE(repo_id, relative_path)
);

-- FTS5 virtual table (content search + snippets)
CREATE VIRTUAL TABLE IF NOT EXISTS doc_search_fts USING fts5(
    repo_id,          -- tokenized for filtering
    relative_path,    -- unindexed (column marked UNINDEXED)
    title,            -- weighted column
    content,          -- main search body
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Index for fast repo+path lookups
CREATE INDEX IF NOT EXISTS idx_file_repo_path ON file_index(repo_id, relative_path);
```

### Why This Schema

- **`repos` table** — stores repo configuration in-DB rather than only in config, allows dynamic repo management later without config file editing
- **`file_index` table** — stores file metadata separately from FTS5 content; enables change detection via `file_hash` without re-extracting text
- **`doc_search_fts` virtual table** — FTS5 handles tokenization, ranking, snippet generation; `content` column carries the full extracted text
- **`UNIQUE(repo_id, relative_path)`** — prevents duplicate entries per file; combined with `INSERT OR REPLACE` for upserts
- **`threading.Lock()` for writes** — follows competence plugin's `_db_lock` pattern

### Incremental vs Full Re-Index

| Trigger | Strategy |
|---------|----------|
| First run (no `last_sync`) | Full walk + extract + index all files |
| Subsequent sync | Walk repo, compare file_hash with stored hash; only re-extract changed/new files |
| File deleted from repo | Entry in `file_index` not found during walk → DELETE from both tables |
| Manual "full reindex" | API param `full=true` → DELETE all rows for that repo → full walk |

**File hash** is SHA-256 of content bytes; computed before extraction to avoid re-extracting unchanged files.

## Sync Strategy

### When Sync Runs

| Trigger | Mechanism | Pattern From |
|---------|-----------|-------------|
| App startup | `startup()` calls `asyncio.get_running_loop().create_task(_sync_job())` | New (competence doesn't auto-sync) |
| Manual button (API) | `POST /api/doc_search/sync` → `asyncio.create_task(_sync_job())` | `competence_sync()` |
| Scheduled (future) | Optional `asyncio` periodic task; not in MVP | New |

### startup() Design

```python
def startup(self) -> None:
    """Initialize DB schema and kick off initial git pull."""
    self._init_db()
    # Auto-sync on startup so search works immediately
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_sync_job(full=False))
    except RuntimeError:
        pass  # No event loop yet — will sync on first manual trigger
```

### Sync Progress Reporting

Follows competence plugin pattern: `sync_progress` key in `sync_state` with JSON:
```json
{"phase": "git_pull", "repo": "firmware", "done": 1, "total": 3}
{"phase": "scanning",   "repo": "firmware", "found": 1500}
{"phase": "extracting", "repo": "firmware", "done": 342, "total": 1500}
{"phase": "indexing",   "repo": "firmware", "done": 342, "total": 1500}
```

### Shutdown

```python
def shutdown(self) -> None:
    """Nothing to clean up — all state is in SQLite."""
    pass
```

Unlike competence plugin (which has to close httpx clients), the doc search plugin has no persistent network connections to clean up.

## Frontend Integration

### How JS Talks to Plugin API

Exactly like competence.js:
1. **Import core.js**: `import { h, api, toast, registerPlugin, icons, createTable } from "./core.js";`
2. **Call `registerPlugin()`**: with `{ id, name, order, svgIcon, init(container), destroy() }`
3. **Use `api()` helper**: for all fetch calls — handles errors, JSON parsing, toast on failure
4. **Use `h()` builder**: for DOM construction
5. **No framework**: pure Vanilla JS, no build step, served as ES module from `/static/js/`

### Registration Pattern

```javascript
// doc_search.js
import { h, api, toast, registerPlugin, icons, createTable } from "./core.js";

registerPlugin({
  id: "doc_search",
  name: "Doc Search",
  order: 50,
  svgIcon: icons.search,

  _query: "",
  _repoId: "all",
  _debounceTimer: null,

  init(container) {
    this._render(container);
  },

  destroy() {
    // Clean up any timers, event listeners
    if (this._debounceTimer) clearTimeout(this._debounceTimer);
  },

  _render(c) { /* search bar + results + preview layout */ },

  async _doSearch(q) { /* debounced search call */ },

  async _showPreview(repo, path) { /* load preview into iframe/div */ },
});
```

### app.js Modification (1 line)

```javascript
// app.js — add import
import "./doc_search.js";
```

## Integration Points

### Internal Boundaries

| Boundary | Pattern | Notes |
|----------|---------|-------|
| Plugin ↔ FastAPI | `register_routes(app)` decorates `app` with `@app.get(...)` | No return value; side-effect only |
| Plugin ↔ Config | `app.config.load()` reads `toolkit_settings.json` | Read-only at sync time; add `doc_repos` key to config |
| Plugin ↔ Filesystem | `git pull` via `subprocess.run()`, file walking via `os.walk()` | Sync-only operation |
| Plugin ↔ SQLite | Same connection pattern as competence: open/close per operation, `check_same_thread=False`, WAL mode | Threading lock for writes |
| extraction module ↔ Plugin | `extract_text(path, mime_type) → str` | Pure function, no side effects, import-only |
| Frontend ↔ API | `fetch("/api/doc_search/*")` via `api()` helper | ES module import; no CORS needed (same origin) |

### Config Integration

Add to `toolkit_settings.json`:
```json
{
    "doc_repos": [
        {
            "id": "firmware",
            "name": "Firmware Docs",
            "path": "C:/docs/firmware-repo",
            "enabled": true
        },
        {
            "id": "hardware", 
            "name": "Hardware Specs",
            "path": "C:/docs/hardware-repo",
            "enabled": true
        },
        {
            "id": "manuals",
            "name": "User Manuals", 
            "path": "C:/docs/manuals-repo",
            "enabled": true
        }
    ]
}
```

Config is read at sync time; repos table is synced from config on startup.

### External Dependencies

| Dependency | Purpose | Install |
|------------|---------|---------|
| `python-docx` | Extract text from .docx files | `pip install python-docx` |
| `PyPDF2` or `pdfplumber` | Extract text from .pdf files | `pip install pdfplumber` |
| `textract` or custom parser | Extract text from .doc (legacy) | `pip install textract` |
| `rst` parsing | .rst files are plain text; `open().read()` works | No dependency |
| `.drawio` / `.graphml` | XML-based; extract text from XML tags | No dependency (stdlib `xml.etree`) |
| `git` | CLI tool for `git pull` | Already on system (existing tool infrastructure) |

## Suggested Build Order

### Phase 1: Backend Core (search + extraction + index) — Blocks Phase 2

**Rationale:** Frontend can't be built until API endpoints exist. Extraction is the most complex and error-prone piece — start early.

**Build order within Phase 1:**
1. `doc_extraction.py` — write and test extraction for all 6 formats
2. `doc_search.py` — plugin class, DB schema, FTS5 index creation in `register_routes()`
3. `POST /api/doc_search/sync` — git pull + walk + extract + index
4. `GET /api/doc_search/search?q=...` — FTS5 query with snippets
5. `GET /api/doc_search/sync/status` — progress reporting
6. `GET /api/doc_search/preview/{repo_id}/{path}` — file preview
7. `GET /api/doc_search/repos` — repo listing
8. Manual smoke test: `curl` sync → search → preview

### Phase 2: Frontend SPA — Depends on Phase 1

**Rationale:** Needs Phase 1 API. Frontend is straightforward vanilla JS following competence.js patterns.

**Build order within Phase 2:**
1. `doc_search.js` — plugin registration + `init()` layout
2. Search bar with debounce → results table with snippets
3. Row click → preview panel (iframe with highlight HTML)
4. Sync button + status polling (identical pattern to competence.js `_doSync()`)
5. Repo filter dropdown
6. `app.js` — add `import "./doc_search.js";`
7. Manual smoke test: search → click → preview → sync button

### Why Not Parallel?

Backend and frontend *could* be built in parallel if:
- API contract is specified upfront
- Frontend developer mocks API responses

But in this codebase pattern, the same implementor does both (single-file plugin + single JS file). Building backend-first means the frontend can be tested against real data immediately.

### Phase 3: Polish (Optional)

- Autocomplete/suggestions from FTS5
- Search term highlighting in results list
- "Open in external viewer" button in preview
- Scheduled background sync (cron-style)
- Fuzzy search fallback for typos

## Patterns to Follow

### Pattern 1: Module-Level State + Locking (from competence.py)
```python
_db_lock = threading.Lock()
_http_client: httpx.AsyncClient | None = None

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
```
**Why:** Competence plugin proves this works for concurrent sync + reads. FTS5 queries are reads (no lock needed in WAL mode), only writes need the lock.

### Pattern 2: Async Background Task (from competence.py)
```python
@router.post("/sync")
async def trigger_sync():
    if await _db_get_async("in_progress") == "1":
        return {"status": "sync_already_running"}
    asyncio.create_task(_sync_job())
    return {"status": "sync_started"}
```
**Why:** Long-running sync (3000 files × extraction) must not block the request. Progress tracked in `sync_state` table, polled by status endpoint.

### Pattern 3: HTMLResponse for Previews (from competence.py chart)
```python
@app.get("/api/doc_search/preview/{repo_id}/{path:path}", response_class=HTMLResponse)
async def preview(repo_id: str, path: str, q: str = ""):
    text = extract_text(full_path)
    html = _highlight_terms(text, q.split())
    return f"<html><body>{html}</body></html>"
```
**Why:** Returns self-contained HTML, consumed by frontend iframe. No separate rendering logic needed in JS. Same pattern as Plotly charts in competence.

### Pattern 4: Simple `extract_text()` Dispatch
```python
# doc_extraction.py
def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    extractor = _EXTRACTORS.get(ext)
    if not extractor:
        logger.warning(f"No extractor for {ext}, trying as plain text")
        return _extract_plain(file_path)
    try:
        return extractor(file_path)
    except Exception as e:
        logger.warning(f"Extraction failed for {file_path}: {e}")
        return ""

_EXTRACTORS = {
    ".docx": _extract_docx,
    ".pdf":  _extract_pdf,
    ".doc":  _extract_doc,
    ".rst":  _extract_plain,  # reStructuredText is plain text
    ".drawio": _extract_xml,
    ".graphml": _extract_xml,
    ".txt":  _extract_plain,
    ".md":   _extract_plain,
}
```
**Why:** Extensible — adding a format is one function + one dict entry. Failures are logged but don't crash the sync.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Blocking Sync in Request Handler
**What people do:** `await _sync_job()` inside the POST handler, making the client wait 10+ minutes
**Why it's wrong:** HTTP timeout, blocked event loop, terrible UX
**Do this instead:** `asyncio.create_task(_sync_job())` — return immediately, poll status

### Anti-Pattern 2: Single Monolithic `doc_search.py`
**What people do:** Put extraction, sync, search, and preview all in one 1500-line file
**Why it's wrong:** Hard to test, hard to read, extraction testing requires FastAPI context
**Do this instead:** Separate `doc_extraction.py` module — pure functions, zero dependencies on plugin framework

### Anti-Pattern 3: Full Re-Index Every Sync
**What people do:** Delete all FTS5 rows, re-extract all 3000 files, re-insert
**Why it's wrong:** Unnecessary I/O, 10+ minute sync for 1 changed file
**Do this instead:** Compare file hashes in `file_index` table; only re-extract changed/new files

### Anti-Pattern 4: Loading All Files Into Memory
**What people do:** Read all 3000 files into a list, extract all, then insert
**Why it's wrong:** Memory spike; sync crash on large repos
**Do this instead:** Stream — walk files, extract one at a time, insert immediately, report progress

### Anti-Pattern 5: Mixing Extraction Errors with Sync Failures
**What people do:** One bad .doc file crashes the entire sync
**Why it's wrong:** 1 corrupt file blocks indexing 2999 good files
**Do this instead:** Extract inside `try/except`; log warning, skip file, continue sync. Report skipped-files count in sync status.

## Sources

- **Existing codebase** (verified by reading source): `app/plugins/competence.py`, `app/plugins/base.py`, `app/main.py`, `app/config.py`, `app/static/js/core.js`, `app/static/js/competence.js`, `app/static/js/app.js`
- **SQLite FTS5 Documentation**: https://www.sqlite.org/fts5.html (built-in since Python 3.9, `snippet()` function for highlighting)
- **PROJECT.md**: Milestone M3 specification — git sync, text extraction, search, preview

---

*Architecture research for: Documentation Search Engine Plugin*
*Researched: 2026-07-01*
*All claims verified against existing codebase patterns*
