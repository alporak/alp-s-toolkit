# Project Research Summary

**Project:** Documentation Search Engine Plugin (M3)
**Domain:** Full-text search over internal documentation repositories
**Researched:** 2026-07-01
**Confidence:** HIGH

## Executive Summary

This project builds a full-text search engine plugin for an existing FastAPI toolkit, indexing documentation across 3 local git repositories containing ~3000 files in 6+ formats (.docx, .pdf, .doc, .rst, .drawio, .graphml). The plugin follows established conventions from the existing competence plugin — same `ToolkitPlugin` base class, same SQLite + WAL mode pattern, same Vanilla JS + `core.js` frontend framework, same background-task + status-polling sync pattern.

**The recommended approach is SQLite FTS5 for search, not Whoosh.** Three of four researchers independently converged on FTS5, and the dissenting researcher (STACK.md) was overridden because: FTS5 already ships with Python's `sqlite3`, it requires zero new dependencies, it supports content-less tables (critical for index size control at 3000 docs), and it uses patterns already proven in the competence plugin. The extraction pipeline must handle 6 formats with per-format dispatch (python-docx for .docx, pdfplumber for .pdf, doc2txt for legacy .doc, stdlib xml.etree for .drawio/.graphml), with charset-normalizer detecting encoding on all outputs to prevent silent mojibake from Baltic-locale documents.

**The primary risk is blocking the FastAPI event loop** with synchronous extraction and git operations across 3000 files. This is mitigated by running ALL heavy work inside `asyncio.to_thread()` with a `ThreadPoolExecutor(max_workers=4)`, following the exact pattern from `competence.py`. Secondary risks include scanned PDFs silently returning empty text (requires detection + flagging, not OCR), and the temptation to rebuild the index on every startup (requires file-hash-based incremental updates and persisted disk index).

## Cross-File Contradictions Resolved

Four parallel researchers independently analyzed the project. The following conflicts were detected and resolved during synthesis:

| Conflict | STACK.md | Other Files | Resolution | Rationale |
|----------|----------|-------------|------------|-----------|
| **Search backend** | Whoosh (whoosh-reloaded 2.7.5) | ARCHITECTURE, FEATURES, PITFALLS all recommend SQLite FTS5 | **SQLite FTS5** | FTS5 ships with Python, zero new deps, content-less tables for storage efficiency, uses proven competence plugin patterns. Whoosh (even maintained fork) adds an unnecessary dependency when the existing DB already does the job. |
| **Git operations** | GitPython 3.1.50 | PITFALLS warns GitPython has its own blocking issues, recommends subprocess | **subprocess via asyncio.to_thread()** | For 3 repos doing `git pull`, subprocess is lighter, more predictable, and avoids an extra dependency. GitPython's context manager doesn't solve the fundamental blocking problem. |
| **PDF extraction** | pypdf primary, pdfplumber optional | FEATURES + PITFALLS both use pdfplumber throughout | **pdfplumber 0.11.10 primary** | pdfplumber has better extraction quality, handles tables natively, and is actively maintained. pypdf stays as lightweight fallback if pdfplumber fails on a specific file. |
| **Legacy .doc extraction** | textract v2.0.0 (April 2026) | PITFALLS recommends doc2txt v1.0.8 (July 2025) with bundled antiword binaries | **doc2txt primary, textract as fallback** | doc2txt ships bundled antiword binaries for Windows — critical since this is a Windows-hosted internal tool. textract v2.0.0 is too new to trust (major version bump, unproven stability). |
| **Phase grouping** | Not addressed | ARCHITECTURE: Backend→Frontend→Polish; PITFALLS: Extraction→Index→Sync phases | **3 phases: Extraction+Index Foundation → Sync+Search API → Frontend SPA** | Merges both perspectives. Extraction and index schema are tightly coupled (must design together). Sync and search API share the same DB + async infrastructure. Frontend depends on stable API contract. |

## Key Findings

### Recommended Stack

The search engine is built entirely within the existing FastAPI/SQLite/Vanilla JS stack. No new infrastructure services, no external search daemons, no npm build step.

**Core technologies:**
- **SQLite FTS5** (stdlib): Full-text search index with BM25 ranking, `snippet()` highlighting, content-less tables. Ships with Python 3.9+. Already proven in competence plugin's WAL-mode DB pattern.
- **pdfplumber 0.11.10**: PDF text extraction with table support. Powers the scanned-PDF detection strategy. Built on pdfminer.six.
- **python-docx 1.2.0**: `.docx` text extraction. Handles paragraphs and tables. Does NOT handle `.doc` — that requires a separate extractor.
- **doc2txt 1.0.8**: Legacy `.doc` extraction wrapping antiword with bundled Windows binaries. Avoids system dependency installation.
- **charset-normalizer 3.4.7**: Encoding detection for all extracted text. Prevents mojibake from Baltic-locale legacy documents. 97% accuracy, actively maintained.
- **subprocess (stdlib)**: Git pull operations, wrapped in `asyncio.to_thread()`. Simpler and more predictable than GitPython.
- **docutils 0.23**: `.rst` plain text extraction via doctree walking (optional; `.rst` files are mostly readable as plain text).
- **xml.etree.ElementTree (stdlib)**: Text extraction from `.drawio` (`mxCell/@value`) and `.graphml` (`node/data` elements). No external dependency.
- **mark.js 9.0.0**: Client-side search term highlighting. Delivered via CDN. Works standalone — no jQuery, no npm.

**What NOT to use (and why):**
- **Whoosh**: Even the maintained fork (whoosh-reloaded) adds an unnecessary dependency. FTS5 is already in the stack and superior for this workload.
- **Elasticsearch / Meilisearch**: External service overkill for 3000 files. Adds operational complexity with zero benefit at this scale.
- **Tantivy**: Rust native dependency (3.8MB wheel). Overkill at 3000-file scale.
- **PyMuPDF (fitz)**: AGPL license — not suitable for internal company tools without commercial license.
- **jQuery**: mark.js works standalone. Adding jQuery for one library is 87KB of dead weight.
- **textract as primary extractor**: Black-box extraction — you can't tell which backend failed. Use format-specific libraries with textract only as last-resort fallback.

### Expected Features

**Must have (table stakes — P0):**
- Multi-format text extraction (6 formats) — without this, nothing is searchable
- FTS5 index building with incremental updates — foundation of all search
- Git repo sync (pull from 3 local repos) — content must be current
- Keyword full-text search API with BM25 ranking — core value proposition
- Result listing with file name + path + snippet + repo badge — users need to identify matches
- Match snippet with `<mark>` highlighting — users need to see why there's a match
- Manual sync trigger button — explicit content refresh
- Sync progress feedback — long syncs feel broken without progress indication
- Empty/error states ("no results", "index building", "sync error") — users need feedback

**Should have (differentiators — P1):**
- Search-as-you-type with 250ms debounce + AbortController — dramatically better UX
- File-type filtering chips — quick visual scan improvement
- Result count display — trivially adds polish
- Repo source badges (color-coded) — users need to know which repo a result comes from
- Search scope indicator (which repos are indexed, file counts) — builds trust

**Nice to have (power users — P2):**
- Keyboard navigation (arrows + Enter + Escape) — power user efficiency
- Inline file preview with highlighted terms — saves context-switching
- Relevance score display — optional transparency

**Explicitly deferred (v2+):**
- NLP/semantic search (vector embeddings) — massive overkill for 3000 internal docs
- OCR for scanned PDFs — requires Tesseract, 10x complexity, accept ~5% exclusion rate instead
- Web crawling / external URL indexing — fundamentally different from local file search
- Advanced query DSL UI — most users type 2-3 words; passthrough FTS5 syntax for power users
- Multi-language stemming — most technical docs are English; add later if needed
- Search analytics / click tracking — log zero-result queries to app logger; full analytics is a separate product

**Key differentiator against competitors (Algolia, mkdocs, Meilisearch):** Direct multi-format file parsing + inline preview. No existing doc search tool does both. Algolia crawls HTML only. mkdocs only does Markdown. Meilisearch needs pre-parsed JSON. This plugin parses raw files directly and shows previews — that's the unique value proposition.

### Architecture Approach

The plugin follows the exact same architecture as the existing competence plugin: a `ToolkitPlugin` subclass with module-level `plugin = DocSearchPlugin()` singleton, route registration via `register_routes(app)`, DB management via SQLite with WAL mode and `threading.Lock()`, background tasks via `asyncio.create_task()` with status polling, and a Vanilla JS frontend using `core.js` helpers (`h()`, `api()`, `registerPlugin()`).

**Major components:**
1. **DocSearchPlugin** (`app/plugins/doc_search.py`, ~400 lines): Plugin lifecycle, route registration, sync orchestration, search API. Extends `ToolkitPlugin`. Owns the FTS5 index lifecycle.
2. **Text Extraction Module** (`app/plugins/doc_extraction.py`, ~150 lines): Format-specific extraction via dispatch table keyed on file extension. Pure functions only — no plugin dependencies. Each function: `file_path → str`. Failures are logged but never crash the sync.
3. **doc_metadata table** (SQLite): Stores full extracted text, file hashes, encoding info, OCR flags. One row per file. Primary content store — FTS5 references it via `content_rowid`.
4. **doc_search_fts virtual table** (FTS5, content-less): Inverted index only. References `doc_metadata` for content. Keeps index file proportional to unique token count, not raw document size.
5. **Sync Engine** (`_sync_job()` coroutine): Git pull → walk files → compare hashes → extract changed files → upsert FTS5. Runs in background via `asyncio.create_task()`. Reports progress via `sync_state` table.
6. **Frontend SPA** (`app/static/js/doc_search.js`, ~300 lines): Vanilla JS ES module. Search bar with debounce, result table with snippets, inline preview panel, sync button. Registered via `registerPlugin()`.
7. **app.js**: One-line addition: `import "./doc_search.js";` — no other files modified.

**Data flow:** Git repos → file system → `extract_text()` → `doc_metadata` table → FTS5 `doc_search_fts` → `GET /search` API → `api()` helper → result rendering. Sync and search are fully decoupled — WAL mode allows concurrent reads during writes.

**API endpoints** (all under `/api/doc_search/`): `GET /search`, `POST /sync`, `GET /sync/status`, `GET /preview/{repo}/{path}`, `GET /repos`. Follows competence plugin URL prefix pattern.

### Critical Pitfalls

1. **python-docx cannot handle .doc files** — Legacy .doc (OLE2 format) requires a completely different library. Use `doc2txt.extract_text()` for `.doc` files, `python-docx` for `.docx`. Test with a .doc fixture before considering extraction "done". (PITFALL #1)

2. **PDF text extraction silently fails on scanned documents** — pdfplumber returns empty text for image-based PDFs with no warning. After extraction, check `len(text) < 20 && page_count > 0` → flag as `needs_ocr: true`. Display a `⚠` icon in search results. Do NOT add OCR — it's out of scope. Accept ~5% exclusion rate for scanned docs. (PITFALL #3)

3. **Blocking the FastAPI event loop** — All extraction, git operations, and FTS5 writes are synchronous. Running them directly in route handlers freezes the entire server. Wrap ALL heavy work in `asyncio.to_thread()` with `ThreadPoolExecutor(max_workers=4)`. Follow the exact pattern from `competence.py` lines 93-99. This is the #1 integration pitfall affecting every phase. (PITFALL #4)

4. **Character encoding silent corruption (mojibake)** — Legacy .doc/.pdf files from Baltic-locale environments use Windows-1257, ISO-8859-13, or CP852. Reading as UTF-8 with `errors='replace'` produces garbage that enters the index unnoticed. Pipe all extracted text through `charset-normalizer.from_bytes().best()`. Store detected encoding in metadata for debugging. (PITFALL #5)

5. **Index rebuild on every startup (cold start)** — Rebuilding the FTS5 index from 3000 docs on every startup takes 30-120 seconds and blocks the UI. Persist the index to disk (`doc_search_index.db`, not `:memory:`). Use file hash (SHA-256) fingerprinting for incremental updates. Kick off index verification as a background task — serve UI immediately with "Indexing..." progress. (PITFALL #6)

6. **FTS5 default inline content storage balloons index** — Without content-less tables, extracted text is stored twice: in the metadata table AND in the FTS virtual table structure. For 3000 docs averaging 100KB, this creates a 500MB+ index. Use `content='doc_metadata'` and `content_rowid='id'` to store only the inverted index. Updates then only modify tokens, not full document content. (PITFALL #7)

7. **Path traversal in preview endpoint** — Attackers can read arbitrary server files via `../../etc/passwd` in the `{path}` parameter. Resolve all file paths with `os.path.realpath()` and verify they start with the allowed repo root. Return HTTP 403 if validation fails. (Security)

## Implications for Roadmap

Based on combined research, the recommended phase structure:

### Phase 1: Extraction & Index Foundation

**Rationale:** Text extraction is the most complex and error-prone work. It has the highest risk of silent failures (encoding, scanned PDFs, wrong library for .doc). The FTS5 schema must be designed alongside extraction because the content strategy (content-less tables) dictates what gets stored and how. These two concerns are tightly coupled and must be built together.

**Delivers:**
- `doc_extraction.py` with format dispatch for 6 formats
- charset-normalizer encoding detection on all extracted text
- Scanned PDF detection + `needs_ocr` flag
- `doc_metadata` table (full text, hashes, encoding info)
- `doc_search_fts` virtual table (content-less FTS5)
- File hash (SHA-256) fingerprinting infrastructure
- Plugin class skeleton with `register_routes()`, `startup()` (schema init only), `shutdown()`
- Module-level `plugin = DocSearchPlugin()` singleton
- Manual test fixtures for each format

**Addresses features:** Text extraction pipeline (P0), FTS5 index building (P0)
**Avoids pitfalls:** PITFALL #1 (.doc handling), #3 (scanned PDFs), #5 (encoding), #7 (content storage strategy)

**Research flag:** Well-documented patterns. Skip research-phase — all extraction APIs and FTS5 schema design are verified against official docs.

---

### Phase 2: Sync Engine & Search API

**Rationale:** Builds on Phase 1's index foundation. Sync and search share the same DB infrastructure, async patterns, and threading model. They must be implemented together because the sync engine populates the index that the search API queries. The background task pattern and status polling are proven in the competence plugin — follow the exact same template.

**Delivers:**
- Git sync engine: `subprocess.run(["git", "pull"])` wrapped in `asyncio.to_thread()`
- Incremental index updates via file hash comparison (re-extract only changed files)
- `GET /api/doc_search/search?q=...` with FTS5 MATCH, BM25 ranking, `snippet()` highlighting, `LIMIT 50`
- `POST /api/doc_search/sync` (async trigger, immediate response)
- `GET /api/doc_search/sync/status` (progress polling: phase, done/total)
- `GET /api/doc_search/preview/{repo}/{path}` with path traversal protection + XSS sanitization
- `GET /api/doc_search/repos` (configured repos + file counts + last synced)
- `startup()` kicks off initial sync as background task
- `toolkit_settings.json` config addition for `doc_repos`
- ThreadPoolExecutor(max_workers=4) for parallel extraction

**Addresses features:** Git repo sync (P0), Keyword search API (P0), Manual sync (P0), Sync progress (P0), Preview endpoint (P2)
**Avoids pitfalls:** PITFALL #2 (FTS5 over Whoosh), #4 (blocking event loop), #6 (cold start rebuild), Security (path traversal, subprocess injection, XSS)

**Research flag:** Standard patterns from competence plugin. Skip research-phase — async background task pattern is a direct copy from `competence.py` lines 600-633.

---

### Phase 3: Frontend SPA

**Rationale:** Depends on Phase 2 for all API endpoints. Frontend is straightforward Vanilla JS following `competence.js` patterns — search bar, result table, preview panel, sync button. The only novel component is the debounced search-as-you-type with AbortController.

**Delivers:**
- `doc_search.js` with `registerPlugin({id, name, order, icon, init, destroy})`
- Search bar with 250ms debounce + AbortController for in-flight request cancellation
- Result listing: file type icons, repo badges (color-coded), highlighted snippets, relevance score
- Inline preview panel: expandable accordion, first ~500 chars with `<mark>` highlights, "Open raw file" link
- Sync button with progress bar polling `GET /sync/status`
- File-type filter chips (docx/pdf/doc/rst/drawio)
- Repo scope indicator ("Searching across 3 repos: ...")
- Keyboard navigation: arrow keys (focus), Enter (expand preview), Escape (clear/close)
- Empty states: "No results", "Index building...", "Click Sync Now to index"
- Loading spinners and error toasts via `core.js` helpers
- `app.js`: add `import "./doc_search.js";`

**Addresses features:** Result listing UI (P0), Search-as-you-type (P1), Highlighting (P1), File-type filtering (P1), Result count (P1), Repo badges (P1), Keyboard nav (P2), Inline preview (P2), Empty/error states (P0)
**Avoids pitfalls:** UX pitfalls (silent zero-results, no loading states, no repo distinction), XSS via innerHTML (sanitize snippets)

**Research flag:** Standard patterns from competence.js. Skip research-phase — all frontend patterns are direct copies from existing plugin.

---

### Phase Ordering Rationale

- **Extraction + Index first** (Phase 1) because: it's the riskiest work (silent failures are common), it establishes the data schema that everything else depends on, and it can be tested independently with fixture files before sync or search exist.
- **Sync + Search second** (Phase 2) because: it depends on the index schema from Phase 1, it produces a testable API contract, and it proves the async infrastructure works before the frontend touches it.
- **Frontend last** (Phase 3) because: it consumes the API from Phase 2, requires no new backend work, and follows established patterns that won't block earlier phases.
- **Not parallel** because: the same implementor typically does both (single-file plugin + single JS file pattern from existing plugins), and building backend-first means the frontend can be tested against real data immediately.

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 1:** `.drawio` and `.graphml` extraction quality — these formats have no standard text extraction library. The XML text extraction approach needs a spike on real fixture files to verify usable text output. If extraction quality is too poor, decide whether to skip these formats or invest in custom parsing.

**Phases with well-documented patterns (skip research-phase):**
- **Phase 2:** Git sync and search API follow competence plugin patterns exactly. No unknowns.
- **Phase 3:** Frontend SPA follows competence.js patterns exactly. No unknowns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommended libraries verified against official PyPI pages and Context7 docs. Stack decisions resolved against contradictory research: FTS5 over Whoosh (3:1 consensus), subprocess over GitPython (PITFALLS warning), pdfplumber over pypdf (feature consensus), doc2txt over textract (Windows compatibility). Only question: whether charset-normalizer is strictly necessary or over-engineering. |
| Features | HIGH | Feature landscape verified against Algolia DocSearch, Meilisearch, mkdocs-material search, and SQLite FTS5 docs. P0/P1/P2/defer classifications reflect standard search UX conventions. Competitor analysis confirms the unique differentiator (direct multi-format parsing + inline preview). |
| Architecture | HIGH | All patterns verified against existing competence plugin codebase (competence.py, competence.js, core.js, base.py). Plugin architecture, async patterns, DB management, and frontend integration are direct copies of proven patterns. Zero new infrastructure. |
| Pitfalls | HIGH | All 7 critical pitfalls verified against library documentation, PyPI release dates, and existing codebase analysis. Each pitfall has a concrete prevention strategy and verification test. Recovery strategies documented for worst-case scenarios. |

**Overall confidence: HIGH**

### Gaps to Address

- **DrawIO/GraphML extraction quality:** The XML text extraction approach needs validation on real fixture files. These formats may produce sparse or unusable text. Spike during Phase 1 planning to decide whether to include or defer these formats.
- **scanned PDF percentage:** Unknown what fraction of the 393 PDFs are scanned vs machine-generated. Run extraction on all PDFs during Phase 1 to determine the real exclusion rate before designing the UI messaging.
- **Legacy .doc encoding accuracy:** doc2txt's bundled antiword binaries may not handle Windows-1257 (Baltic) perfectly. Test with CP1257 .doc fixtures during Phase 1. If accuracy is poor, explore LibreOffice fallback via `soffice --headless --convert-to txt`.
- **Config management pattern:** The competence plugin reads Jira config separately. The doc search plugin needs a similar `config.load_docsearch_config()` pattern. Confirm whether to extend the existing config infrastructure or create a dedicated config module.
- **charset-normalizer necessity:** While encoding issues are real for Baltic-locale documents, the actual occurrence rate in the target repos is unknown. Consider making charset-normalizer an optional safety net, not a hard dependency — if all docs are UTF-8, it adds overhead for no benefit.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `app/plugins/competence.py`, `app/plugins/base.py`, `app/static/js/core.js`, `app/static/js/competence.js`, `app/config.py`, `app/main.py` — all architectural patterns verified
- SQLite FTS5 official docs (sqlite.org/fts5.html) — content-less tables, BM25, snippet(), highlight()
- Context7: `/python-openxml/python-docx`, `/py-pdf/pypdf`, `/jsvine/pdfplumber`, `/gitpython-developers/gitpython`, `/sygil-dev/whoosh-reloaded`, `/quickwit-oss/tantivy-py`, `/websites/markjs_io`, `/deanmalmgren/textract`, `/docutils/docutils`
- PyPI: pypdf, python-docx, GitPython, tantivy, pdfplumber, textract, docutils, doc2txt, charset-normalizer, olefile
- PROJECT.md: Milestone M3 specification

### Secondary (MEDIUM confidence)
- Algolia DocSearch official docs (docsearch.algolia.com) — UX patterns verified
- Meilisearch official docs (meilisearch.com) — feature comparison verified
- Docusaurus Search docs — UX conventions verified
- mkdocs-material search docs — UX conventions verified

### Research files synthesized
- STACK.md (254 lines) — stack recommendations with per-library rationale
- FEATURES.md (297 lines) — feature landscape with competitor analysis
- ARCHITECTURE.md (596 lines) — component breakdown with build order
- PITFALLS.md (405 lines) — 7 critical pitfalls with prevention + recovery

---
*Research completed: 2026-07-01*
*Ready for roadmap: yes*
