# Pitfalls Research

**Domain:** Documentation Search Engine — text extraction + full-text search + plugin integration
**Researched:** 2026-07-01
**Confidence:** HIGH

Sources: official PyPI pages, library documentation (python-docx, pdfplumber, doc2txt, Whoosh, textract, charset-normalizer, olefile), SQLite FTS5 docs, existing project codebase analysis.

---

## Critical Pitfalls

### Pitfall 1: Assuming python-docx Handles .doc Files

**What goes wrong:**
Developers write `from docx import Document; text = Document("file.doc")` and get cryptic errors. python-docx v1.2.0 only handles OpenXML (.docx) format — it has zero support for legacy OLE2 Compound File Binary Format (.doc, pre-2007). The project has 201 .doc files that will silently fail.

**Why it happens:**
The naming is misleading: `python-docx` implies it handles "doc files." Every new developer on this domain makes this mistake. The library's name refers to the DOCX format, not .doc files.

**How to avoid:**
Use a dispatch table keyed on extension:
- `.docx` → `python-docx` (Document(path).paragraphs)
- `.doc` → `doc2txt.extract_text(path)` (wraps antiword with bundled Windows binary, v1.0.8, July 2025)
- `.pdf` → `pdfplumber` (for text-based PDFs)
- `.pptx` → `python-pptx` (if encountered)

Alternatively, use `textract v2.0.0` (April 2026) as a unified facade — it wraps all these libraries but is a single-point-of-failure if one backend breaks.

**Warning signs:**
- `python-docx` import errors or AttributeError when trying to open .doc files
- Corrupted/garbled text from .doc files (someone tried `open().read()` as a fallback)
- Missing search results for all legacy Word documents

**Phase to address:**
Text extraction phase (Phase 1). Must be part of the extraction pipeline design before any index building.

---

### Pitfall 2: Whoosh Is Abandonware — Using It Creates a Dead End

**What goes wrong:**
Whoosh v2.7.4 was released April 4, 2016 — over 10 years ago. It has:
- Zero Python 3.12/3.13 compatibility testing
- No async support (synchronous file I/O in FastAPI event loop = blocked threads)
- No active maintenance (last commit years ago)
- No type hints (contemporary Python tooling blind spot)
- Index corruption bugs that will never be fixed

**Why it happens:**
Whoosh appears in many "Python full-text search" guides and has great documentation. It was excellent software in its time. Without checking release dates, it seems like a solid pick.

**How to avoid:**
Use **SQLite FTS5** instead. The project already has SQLite infrastructure (WAL mode, per-plugin DB files, `asyncio.to_thread()` patterns for writes — see `competence.py` lines 94-99). FTS5:
- Ships with Python's `sqlite3` module (zero-dependency)
- Supports BM25 ranking (better than TF-IDF for search relevance)
- Built-in `highlight()` and `snippet()` functions for hit highlighting
- Content-less FTS tables for external content storage (store full path + extracted text separately)
- Thread-safe with `check_same_thread=False` + `asyncio.to_thread()`
- Existing plugin schema management pattern already proven (schema versioning via `sync_state` table)

Relevant SQL: `CREATE VIRTUAL TABLE doc_search USING fts5(path, content, title, repo, tokenize='unicode61');`

**Warning signs:**
- Whoosh index file locking errors on Windows
- Random `LockError` or `IndexError` in Whoosh during concurrent reads
- Deprecation warnings on Python >= 3.12

**Phase to address:**
Search index design phase (Phase 2). Must decide FTS5 vs Whoosh before index schema is committed.

---

### Pitfall 3: PDF Text Extraction Silently Returns Empty/Partial Text on Scanned Documents

**What goes wrong:**
pdfplumber (and all pdfminer.six-based libraries) extract text from machine-generated PDFs. Scanned PDFs (image-based) have no embedded text layer — `page.extract_text()` returns `""` or garbage. 393 PDF files in the repos will have a mix. Without detection, scanned PDFs produce zero search hits with no user-facing indication why.

**Why it happens:**
pdfplumber's documentation clearly states "Works best on machine-generated, rather than scanned, PDFs" — but developers skip this line. There's no built-in OCR capability and no warning when text extraction fails silently.

**How to avoid:**
1. After extraction, if `len(extracted_text) < 20` characters and page count > 0 → flag as "likely scanned"
2. Store a `needs_ocr: true` flag in the document metadata table
3. Log a warning: `"PDF appears scanned, no text extracted: {path}"` 
4. In the search UI, indicate which documents are image-only with a `⚠` icon
5. Do NOT add OCR dependencies (tesseract, pytesseract) to the plugin — it's out of scope, adds massive Windows install complexity, and dramatically slows extraction
6. Offer a clear UX message: "X documents could not be searched (scanned PDFs)"

**Warning signs:**
- Search queries that should match known content return 0 results
- `page.extract_text()` returns empty string for multi-page PDFs
- User complaints about "I know this PDF contains the word, but search doesn't find it"

**Phase to address:**
Text extraction phase (Phase 1). Scanned PDF detection must be built into the extraction pipeline.

---

### Pitfall 4: Blocking the FastAPI Event Loop with Synchronous Extraction and Git Operations

**What goes wrong:**
Text extraction from 3000 files + git pull across 3 repos + SQLite FTS5 index building are all synchronous, blocking operations. Running them directly in a FastAPI route handler or `startup()` callback freezes the entire server. The competence plugin already shows the pattern: `asyncio.create_task()` for background work (line 609 of `competence.py`), but git operations and file I/O still need to be offloaded.

**Why it happens:**
- `docx.Document(path)` is synchronous (no async file API exists)
- `pdfplumber.open(path)` is synchronous
- `git pull` via `subprocess.run()` blocks the event loop
- SQLite writes block if not wrapped in `asyncio.to_thread()`
- Developers test with 5 files (seems fast) → deploy with 3000 files (blocks for 30+ seconds)

**How to avoid:**
1. ALL extraction work must run in `asyncio.to_thread(extract_all_docs)` — NEVER in the event loop
2. Use `run_in_executor` with a `concurrent.futures.ThreadPoolExecutor(max_workers=4)` for parallel extraction (too many workers = disk I/O thrashing)
3. Git operations: `asyncio.to_thread(subprocess.run, ["git", "pull"], ...)` — use `subprocess` not `GitPython` (which has its own blocking issues)
4. Index builds: wrap the entire `INSERT INTO fts5 ...` batch in `asyncio.to_thread()`
5. Follow the exact async pattern from `competence.py` lines 93-99:
```python
async def _db_execute_async(query: str, params: tuple) -> None:
    await asyncio.to_thread(_db_execute, query, params)
```

**Warning signs:**
- Server hangs during sync/extraction (all routes time out)
- `RuntimeWarning: coroutine 'X' was never awaited`
- uvicorn logs showing long request durations during index build

**Phase to address:**
Every phase. This is the #1 integration pitfall. The extraction phase, search phase, and sync phase all touch blocking I/O.

---

### Pitfall 5: Character Encoding Decoding Errors on Legacy Documents (Mojibake)

**What goes wrong:**
Old .doc and .pdf files from Eastern European or mixed-locale environments use non-UTF-8 encodings: Windows-1257 (Baltic), ISO-8859-13, CP852, Windows-1252. Reading them as UTF-8 produces `UnicodeDecodeError` or, worse, `errors='replace'` producing silent garbage (mojibake) that goes into the search index unnoticed. Search queries then fail silently.

**Why it happens:**
- .doc files store text in the encoding of the creating Word version (often locale-specific)
- pdfminer.six may extract text bytes that need decoding
- RST files can use `# -*- coding: cp1257 -*-` declarations
- `str(bytes_data)` without explicit encoding detection
- Developers assume "everything is UTF-8 in 2026"

**How to avoid:**
1. Use `charset-normalizer v3.4.7` (actively maintained, April 2026) for ALL text extraction outputs:
```python
from charset_normalizer import from_bytes
result = from_bytes(raw_bytes).best()
if result:
    text = str(result)
```
2. For pdfplumber: the library usually returns Python `str` — but verify with `isinstance(text, str)` and handle edge cases
3. For .doc via doc2txt: output is already decoded, but run through charset-normalizer as a safety net
4. For .docx via python-docx: uses XML internally (UTF-8 by spec), but embedded content from legacy sources may still carry encoding issues
5. Store a `detected_encoding` column in the document metadata table for debugging
6. Log encoding detection confidence: `< 0.5` confidence → flag for manual review

**Warning signs:**
- Search for "specifikacija" returns 0 results but the document clearly contains it
- Random `\ufffd` replacement characters in extracted text
- `UnicodeDecodeError` in logs during extraction
- Lithuanian character ė/ą/ų appearing as garbled text

**Phase to address:**
Text extraction phase (Phase 1). Must be in the extraction pipeline from day one.

---

### Pitfall 6: Search Index Rebuild on Every Startup (Cold Start Performance)

**What goes wrong:**
Building an FTS5 index from 3000 documents every time the plugin starts takes 30-120 seconds. If the index is rebuilt in `startup()`, the plugin is unusable until the build completes. Even worse: indexing triggers a cascade of extraction (git pull → text extraction → FTS indexing), amplifying the delay.

**Why it happens:**
- FTS5 index stored in memory or as a file that's deleted on schema migration
- No cache invalidation strategy — developers check "does index exist?" → "no" → rebuild
- Index file not persisted across restarts (wrong DB path)
- Schema version bump causes DROP+CREATE every startup

**How to avoid:**
1. **Persist the FTS5 index to disk**: Use a SQLite file at `app/plugins/doc_search_index.db` (not `:memory:`)
2. **Incremental updates, not full rebuilds**: On startup, only re-extract files modified since last index update (compare file mtimes against `doc_metadata` table)
3. **File hash fingerprinting** for accuracy: Store `xxhash` or SHA-256 of each file in metadata. If mtime changed but hash didn't → skip re-extraction
4. **Lazy loading**: Serve basic UI immediately; start index verification in background via `asyncio.create_task()` — show a "Indexing... X of 3000 files" progress indicator
5. **Use `startup()` for DB schema init only** (like `competence.py` lines 1037-1092), kick off sync in a background task
6. Rebuild only when: git pull detects new content OR schema version changes OR manual "Rebuild Index" button

**Warning signs:**
- Plugin takes 60+ seconds to show UI after server start
- SQLite file grows 500MB+ (unindexed document text stored inline in FTS)
- Repeated `DROP TABLE` / `CREATE VIRTUAL TABLE` in startup logs

**Phase to address:**
Index design phase (Phase 2) + Sync phase (Phase 3). Persistence strategy must be designed before index schema.

---

### Pitfall 7: FTS5 Content Storage Strategy — Inline vs Content-Less

**What goes wrong:**
The default FTS5 table stores indexed text directly in the virtual table structure. For 3000 documents averaging 100+ KB of extracted text each, this balloons the index file to 500MB+, slows queries, and makes incremental updates expensive (must delete + reinsert entire document instead of updating metadata).

**Why it happens:**
The simplest FTS5 pattern is:
```sql
CREATE VIRTUAL TABLE docs USING fts5(content);
INSERT INTO docs VALUES('long document text here...');
```
This stores the full text twice: once in the FTS index structure (for tokenization) AND once in the content table (for retrieval). For 20 documents this is negligible. For 3000 it's crippling.

**How to avoid:**
Use **content-less FTS5 tables** (external content FTS5):
```sql
-- Metadata table stores the full extracted text
CREATE TABLE doc_metadata (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    title TEXT,
    repo TEXT,
    file_hash TEXT,
    file_mtime REAL,
    extracted_text TEXT,     -- full text here
    detected_encoding TEXT,
    file_type TEXT,
    needs_ocr INTEGER DEFAULT 0
);

-- FTS5 table references metadata, stores only tokens
CREATE VIRTUAL TABLE doc_search USING fts5(
    path, content, title, repo,
    content='doc_metadata',        -- points to external table
    content_rowid='id',            -- uses metadata PK for rowid
    tokenize='unicode61 remove_diacritics 2'
);
```
This way:
- `extracted_text` lives in `doc_metadata` once (not duplicated)
- FTS5 stores only the inverted index (tokens → rowids)
- `highlight(doc_search, 1, '<mark>', '</mark>')` still works on snippets
- Updates only modify the small metadata table + FTS tokens, not entire document content
- Index file stays proportional to unique token count, not raw document size

**Warning signs:**
- `doc_search_index.db` is 10× larger than expected
- Queries on 3000 documents take >500ms
- Index rebuild time grows linearly with each document added

**Phase to address:**
Search index design phase (Phase 2). Content storage strategy is a schema-level decision.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip encoding detection, assume UTF-8 | One less dependency | Silent search misses on legacy docs, impossible to debug | NEVER — charset-normalizer is 150KB wheel, no reason to skip |
| Use Whoosh "because docs are great" | Familiar API, good tutorial | Abandonware, Python 3.13 breaks, no one to fix bugs | NEVER — SQLite FTS5 is already in the stack |
| Extract all text in `register_routes()` | Quick prototype | Blocks all other plugins from loading, server startup delayed | Only in a throwaway spike |
| Inline FTS5 content storage | Simpler SQL, less code | 500MB+ index, slow rebuilds, per-doc updates impossible | Only if <100 total documents |
| Pull all 3 repos with `git pull` in startup() | Simple, always fresh | 30s+ startup delay, blocked UI, git auth failure kills plugin | NEVER — git sync must be background task |
| Skip DrawIO/GraphML extraction as "too complex" | Faster delivery | 2 file formats not searchable, users lose trust in completeness | Acceptable IF clearly communicated and added in next milestone |
| Hardcode repo paths in plugin | Easy to write | Breaks when repos move, no way to change without code edit | NEVER — store in config, same pattern as competence plugin's Jira config |
| Use `subprocess.run()` without `asyncio.to_thread()` | One less wrapper | Blocks entire FastAPI event loop, all requests hang | NEVER — the 5 seconds it takes to add `to_thread` saves hours of debugging |

---

## Integration Gotchas

Common mistakes when connecting components to the existing plugin system.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Plugin DB file location | Placing `.db` at project root or hardcoded absolute path | Use `os.path.join(os.path.dirname(__file__), "doc_search_index.db")` — same pattern as `competence.py` line 31 |
| `startup()` vs `register_routes()` | Heavy work (extraction, indexing, git pull) in `register_routes()` | `register_routes()` = route definitions ONLY. `startup()` = schema init ONLY. Heavy work → `asyncio.create_task()` spawned at end of `startup()` |
| Module-level `plugin` attribute | Forgetting the auto-discovery singleton | Must have `plugin = DocSearchPlugin()` at module top-level (see `competence.py` line 1103) |
| SQLite threading with FastAPI | Using default `sqlite3.connect()` without `check_same_thread=False` | ALWAYS use `check_same_thread=False` + `asyncio.to_thread()` for all DB operations. The competence plugin already does this (line 63) |
| httpx vs requests for git/repo fetching | Using `requests` (sync) for HTTP git clone | Use `httpx` async client (already in the project) OR `subprocess` via `asyncio.to_thread()` for `git clone/pull` |
| Frontend SPA integration | Building a separate React app instead of following the vanilla JS pattern | Use `core.js` framework patterns from `competence.js`: `h()`, `api()`, `registerPlugin()` |
| Error handling in background tasks | Unhandled exceptions in `asyncio.create_task()` silently crash the task | Wrap all background work in try/except with logger: `except Exception as e: logger.error("Sync failed: %s", e, exc_info=True)` |
| Plugin lifecycle for cleanup | Leaving file handles, DB connections, or git locks open on shutdown | Implement `shutdown()` to close: httpx clients (if any), DB connections, cancel background tasks, clean temp extraction files |
| Config management | Inline config values in plugin code | Follow `config.load_jira_config()` pattern — create `config.load_docsearch_config()` that reads repo URLs, sync intervals, etc. |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Synchronous extraction in event loop | Server unresponsive, all requests time out | `asyncio.to_thread()` for ALL extraction | 50+ files |
| FTS5 with no content_rowid optimization | Slow queries on 3000 docs, index file >300MB | Content-less FTS5 tables, BM25 ranking | 500+ documents |
| Extracting all files on every startup | 30-120s cold start | File hash + mtime incremental check | 100+ documents |
| Loading entire PDF/DOCX into memory | OOM killer terminates process | Stream extraction; extract pages individually with context manager | 1 large PDF (>500MB) |
| Single-threaded extraction of 3000 files | Takes 15+ minutes | `ThreadPoolExecutor(max_workers=4)` + `run_in_executor` | 500+ files |
| git pull without timeout | Plugin hangs indefinitely on network error | `subprocess.run(["git", "pull"], timeout=60)` in `asyncio.to_thread()` | Any network blip |
| FTS5 query without LIMIT or snippet bounds | Slow response, huge JSON payload | `LIMIT 50` + use `snippet(doc_search, 2, ...)` for match context, not full extracted text | 100+ results |
| No search result caching | Repeated identical queries hit DB every time | In-memory LRU cache (e.g., `functools.lru_cache(128)` on search function) for identical queries within 5s | 10+ concurrent users |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Path traversal in file preview endpoint | Attackers read arbitrary server files via `../../etc/passwd` | Resolve all file paths against allowed repo roots using `os.path.realpath()` and verify prefix: `if not resolved.startswith(allowed_root): raise HTTPException(403)` |
| Storing raw extracted text in search results without sanitization | XSS via documents containing HTML/JS (e.g., RST raw directives) | HTML-escape all snippets before embedding in JSON; use `html.escape()` on snippet text |
| git credentials in plugin code or config | Credential leak via git history or env inspection | Use existing git credential manager (Git Credential Manager on Windows) — do NOT store passwords in config |
| No size limits on file preview | DoS via requesting preview of 2GB document | Limit preview to first 100KB; for PDF, limit to first 5 pages |
| Subprocess injection via user-controlled repo paths | Command injection: `repo_path = "../../evil; rm -rf /"` | Validate repo paths against whitelist; use `shlex.quote()` for all subprocess arguments |
| SQL injection in search queries | Though FTS5 is parameterized, manual query string concatenation is dangerous | ALWAYS use parameterized queries with `?` placeholders — FTS5 MATCH queries accept bound parameters: `cursor.execute("SELECT * FROM doc_search WHERE doc_search MATCH ?", (query,))` |

---

## UX Pitfalls

Common user experience mistakes in search applications.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent zero-results page | User doesn't know if search worked or if index is empty | Show "No results for 'X'. Try different terms. X documents could not be searched (scanned PDFs, extraction errors). Index last updated: 2h ago." |
| No search-as-you-type | User must press Enter after every query, slow feedback loop | Debounced input (300ms) firing `api()` calls. Vanilla JS: `input.addEventListener('input', debounce(doSearch, 300))` |
| Results show only filename, no context | User must click every result to find the right one | Show: title, path, first 2 lines of snippet with `<mark>` highlighting, repo badge, file type icon |
| No preview loading state | User clicks result, sees blank pane for 3 seconds | Show spinner immediately; stream preview via `<iframe>` or fetch text and render client-side |
| "Rebuild Index" button without progress | User clicks, nothing happens for 60 seconds, thinks it's broken | Progress bar: "Extracting: 234/3000 files" → "Indexing: 45% complete". Poll `/api/doc_search/index/status` every 2 seconds |
| Search returns results for deleted files | Clicking a result shows 404 | On git pull, detect deleted files and remove from index. Store repo path + relative path separately for existence checks |
| No distinction between repos in results | User doesn't know which repo a result came from | Color-coded repo badges or filter chips: `[repo1] [repo2] [repo3]` |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Text extraction:** Works on test docs, but 201 .doc files silently fail because python-docx can't open them — verify with a .doc fixture
- [ ] **Text extraction:** PDF text extracted successfully, but 20% of PDFs are scanned (no text layer) — run extraction on ALL PDFs to get scanned count
- [ ] **Text extraction:** All files extract on dev machine, but encoding errors hit on production Windows with Baltic locale documents — test with CP1257-encoded .doc fixtures
- [ ] **Search index:** Queries work, but index is rebuilt from scratch every startup (no persistence) — restart plugin and verify search works without reindex
- [ ] **Search index:** Snippets show correctly, but double-encoding produces garbled characters in Lithuanian text — search for "įrenginio" and verify snippet is readable
- [ ] **Git sync:** Pull succeeds on first run, but fails on second run (uncommitted changes, merge conflicts) — test with dirty working directory
- [ ] **Git sync:** Sync works when repo is accessible, but hangs forever when VPN is disconnected — test with unreachable repo URL
- [ ] **Plugin integration:** Plugin loads and routes work, but startup() blocks all other plugins during extraction — verify other plugin endpoints respond during extraction
- [ ] **File preview:** Preview works for .docx, but .doc preview returns binary garbage — verify .doc preview pipeline
- [ ] **DrawIO/GraphML:** Files present in repo but silently skipped during extraction — verify these file types produce usable text
- [ ] **Error handling:** Extraction failure on 1 corrupted file doesn't halt entire batch — inject a corrupt PDF and verify others still process

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Used Whoosh, need to migrate to FTS5 | MEDIUM | Write a migration script that reads Whoosh index, emits SQL INSERT statements for FTS5. ~2h work. |
| Index built with inline content (500MB+) | MEDIUM | ALTER approach: create new content-less FTS5 table, INSERT INTO new_fts SELECT from old, DROP old, rename new. Requires downtime for full reindex. |
| All .doc files failed extraction (wrong library) | LOW | Add doc2txt to pipeline, re-run extraction phase on .doc files only (detected by extension). No index rebuild needed if using content-less schema. |
| Encoding mojibake in index | HIGH | Re-extract ALL files with charset-normalizer in pipeline. Full index rebuild required since tokens are corrupted. |
| Git repo moved, hardcoded paths broken | LOW | Update config. If using repo path whitelist, add new path. Re-clone if needed. |
| Subprocess injection vulnerability discovered | LOW | Add `shlex.quote()` + path whitelist validation. No data migration needed. Audit existing index entries. |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| python-docx can't handle .doc (P#1) | Phase 1: Text Extraction | Test extraction on a .doc fixture, verify non-empty text output |
| Whoosh abandonware (P#2) | Phase 2: Search Index Design | Confirm SQLite FTS5 chosen, verify BM25 ranking with sample queries |
| Scanned PDF silent failure (P#3) | Phase 1: Text Extraction | Run extraction on all PDFs, verify `needs_ocr` flag is set correctly |
| Blocking event loop (P#4) | All phases (cross-cutting) | Load-test: trigger extraction while hitting `/api/competence/stats` — verify no timeout |
| Character encoding (P#5) | Phase 1: Text Extraction | Test with CP1257 .doc fixture, verify no `\ufffd` in output |
| Cold start index rebuild (P#6) | Phase 2: Index Design + Phase 3: Sync | Restart plugin twice, verify second startup is sub-5-second |
| FTS5 content storage strategy (P#7) | Phase 2: Index Design | Verify index file size is proportional to tokens, not raw document size |
| Path traversal (Security) | Phase 2: Search API | Attempt `../../etc/hosts` in preview path — verify 403 |
| Subprocess injection (Security) | Phase 3: Git Sync | Attempt `repo_path = "repo; rm -rf /"` — verify validation rejects it |
| Windows file locking | Phase 3: Git Sync | Trigger git pull while extraction is running — verify no PermissionError |
| Hardcoded repo config | Phase 3: Git Sync | Verify repo paths come from config, not inline constants |

---

## Sources

- python-docx v1.2.0 PyPI page & official docs (https://python-docx.readthedocs.io/) — confirms .docx-only, no .doc support — **HIGH confidence**
- pdfplumber v0.11.10 PyPI page — confirms "Works best on machine-generated, rather than scanned, PDFs. Built on pdfminer.six." No OCR — **HIGH confidence**
- Whoosh v2.7.4 PyPI page — release date April 4, 2016, no update in 10+ years. Python 2.5 classifier indicates extreme staleness — **HIGH confidence**
- doc2txt v1.0.8 PyPI page — Python wrapper with bundled antiword binaries for Windows/Linux/macOS, July 2025 release. Supports .doc extraction — **HIGH confidence**
- textract v2.0.0 PyPI page — unified extraction facade, April 2026 release, wraps multiple backends — **MEDIUM confidence** (new major version, ecosystem stability unproven)
- charset-normalizer v3.4.7 PyPI page — "The Real First Universal Charset Detector," actively maintained (April 2026), 97% accuracy, better than chardet — **HIGH confidence**
- olefile v0.47 PyPI page — stable OLE2 parser, December 2023, handles Compound File Binary Format (Office 97-2003) — **HIGH confidence**
- Project codebase analysis: `app/plugins/competence.py` (lines 93-99 async SQLite pattern, lines 607-609 background task pattern, lines 1037-1092 schema management pattern) — **HIGH confidence**
- SQLite FTS5 documentation (sqlite.org/fts5.html) — external content tables, BM25, highlight/snippet functions — **HIGH confidence**

---

*Pitfalls research for: Documentation Search Engine (M3)*
*Researched: 2026-07-01*
