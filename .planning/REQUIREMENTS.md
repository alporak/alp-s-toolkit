# Requirements — Documentation Search Engine

## Version: 3.0 | Status: Approved | Milestone: M3

---

## EXTR: Text Extraction Pipeline

- [x] **EXTR-01**: Format dispatch table extracts text from 6 file types: .docx (python-docx), .pdf (pdfplumber), .doc (doc2txt), .rst (docutils), .drawio (xml.etree), .graphml (xml.etree)
- [x] **EXTR-02**: Each extracted text is validated — non-empty, non-BOM-only. Failures are logged but never crash the sync pipeline
- [x] **EXTR-03**: charset-normalizer detects encoding on all extracted text output; store detected encoding in metadata
- [x] **EXTR-04**: PDFs with pages > 0 but extracted text < 20 chars are flagged `needs_ocr: true` — no OCR performed, just detected
- [x] **EXTR-05**: Text extraction functions are pure (`file_path -> str`), independently testable without plugin infrastructure

---

## INDEX: Search Index

- [ ] **INDEX-01**: SQLite FTS5 virtual table (`doc_search_fts`) using content-less mode (`content='doc_metadata'`, `content_rowid='id'`) — stores inverted index only, not full text
- [ ] **INDEX-02**: `doc_metadata` table stores: repo name, relative path, full extracted text, SHA-256 file hash, detected encoding, `needs_ocr` flag, last_extracted timestamp
- [ ] **INDEX-03**: File hash fingerprinting enables incremental updates — only re-extract files whose SHA-256 has changed
- [ ] **INDEX-04**: Index persisted to disk (`doc_search.db` in `app/plugins/`), WAL mode — not `:memory:`
- [ ] **INDEX-05**: Schema versioning with auto-migration on plugin startup (pattern from competence plugin)

---

## SYNC: Git Sync Engine

- [ ] **SYNC-01**: `POST /api/doc_search/sync` triggers async background sync task (fires `asyncio.create_task()`, returns immediately)
- [ ] **SYNC-02**: `GET /api/doc_search/sync/status` returns `{phase, done, total, error}` — polling pattern from competence plugin
- [ ] **SYNC-03**: Git pull from 3 configured repos via `subprocess.run(["git", "pull"])` wrapped in `asyncio.to_thread()`
- [ ] **SYNC-04**: Incremental mode: walk repo, compare file hashes, extract+index only new/changed files, delete entries for removed files
- [ ] **SYNC-05**: `startup()` kicks off initial sync as background task (non-blocking — UI loads immediately with "Indexing..." status)
- [ ] **SYNC-06**: Repo paths configured via `toolkit_settings.json` (follows existing config patterns)
- [ ] **SYNC-07**: Sync `in_progress` guard prevents concurrent sync runs (config.json pattern from competence)

---

## SRCH: Search API

- [ ] **SRCH-01**: `GET /api/doc_search/search?q={query}` returns FTS5 BM25-ranked results with `snippet()` highlights, limited to 50
- [ ] **SRCH-02**: Response shape: `{results: [{repo, path, filename, snippet, score, needs_ocr, file_type}], total, query}`
- [ ] **SRCH-03**: `GET /api/doc_search/preview/{repo}/{path:path}` returns full extracted text; path traversal protection via `os.path.realpath()` validation
- [ ] **SRCH-04**: `GET /api/doc_search/repos` returns configured repo list with file counts and last synced timestamps
- [ ] **SRCH-05**: Empty query returns empty results (no error); no results returns `{results: [], total: 0}`
- [ ] **SRCH-06**: Subprocess injection prevention: git commands use argument lists (not shell strings)

---

## UI: Frontend SPA

- [ ] **UI-01**: Search bar with 250ms debounce and AbortController (cancel in-flight request on new keystroke)
- [ ] **UI-02**: Result list items show: file type icon, filename, repo badge (color-coded), highlighted snippet with `<mark>` tags, relevance score
- [ ] **UI-03**: Inline preview panel: clicking a result expands accordion showing first ~500 chars of extracted text with search term highlights
- [ ] **UI-04**: Sync button with progress bar polling `GET /sync/status` every 2s during active sync
- [ ] **UI-05**: File-type filter chips (docx, pdf, doc, rst, drawio, graphml) — click toggles visibility
- [ ] **UI-06**: Repo scope indicator: "Searching N repos: repo1 (X files), repo2 (Y files)"
- [ ] **UI-07**: Keyboard navigation: Arrow Up/Down to move focus, Enter to expand preview, Escape to clear search / close preview
- [ ] **UI-08**: Empty states: "No results found for '{query}'", "Index building... Click Sync Now", "0 repos configured — add repos in settings"
- [ ] **UI-09**: Loading spinner during search requests; error toast on sync or search failure
- [ ] **UI-10**: Plugin registered via `core.js` `registerPlugin({id, name, icon, order, init, destroy})`; single line added to `app.js`: `import "./doc_search.js"`
- [ ] **UI-11**: XSS protection: all user content (filenames, snippets, extracted text) rendered via textContent or sanitized before innerHTML; search term `<mark>` wrapping uses DOM manipulation, not string concatenation

---

## NFR: Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR12 | All extraction, git, and FTS5 write operations must run in `asyncio.to_thread()` — never block the event loop |
| NFR13 | Path traversal protection on all file access — `realpath()` validation before any file read |
| NFR14 | Search API response < 200ms for typical queries (measured at endpoint, excluding network) |
| NFR15 | Zero new infrastructure dependencies — no external services, no database servers, no npm build step |
| NFR16 | Follow existing patterns: background task + polling from competence.py; tabbed layout from competence.js |
| NFR17 | Frontend must pass JS syntax check — zero console errors |
| NFR18 | Extraction failures per-file are logged but never crash or block sync — graceful degradation |

---

## Acceptance Criteria (UAT)

1. Type a search query → results appear within 200ms with file names, snippets, and highlights
2. Click a result → inline preview panel expands showing extracted text with search terms highlighted
3. Press Sync Now → progress bar appears → completes → search results reflect updated content
4. All 6 file formats produce searchable text (verified with real fixture files from each repo)
5. Legacy .doc files (pre-2007) are searchable
6. Scanned PDFs show `needs_ocr` indicator in results (not silently empty)
7. Keyboard navigation works: arrows move between results, Enter expands preview, Escape closes
8. File-type filter chips hide/show results by format
9. Repo scope indicator shows all 3 repos with accurate file counts
10. Zero console errors in browser DevTools
11. Path traversal attack returns 403 (not file content)
12. Startup with cold index shows "Indexing..." status — UI remains responsive

---

## Out of Scope (M3)

- OCR for scanned PDFs (flagged as needs_ocr, not processed)
- NLP/semantic search (vector embeddings)
- Web crawling / external URL indexing
- Advanced query DSL UI (FTS5 syntax passthrough for power users)
- Multi-language stemming (most docs are English)
- Search analytics / click tracking
- Daily scheduled sync (background on startup + manual button only)

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXTR-01 | Phase 5 | Pending |
| EXTR-02 | Phase 5 | Pending |
| EXTR-03 | Phase 5 | Pending |
| EXTR-04 | Phase 5 | Pending |
| EXTR-05 | Phase 5 | Pending |
| INDEX-01 | Phase 5 | Pending |
| INDEX-02 | Phase 5 | Pending |
| INDEX-03 | Phase 5 | Pending |
| INDEX-04 | Phase 5 | Pending |
| INDEX-05 | Phase 5 | Pending |
| SYNC-01 | Phase 6 | Pending |
| SYNC-02 | Phase 6 | Pending |
| SYNC-03 | Phase 6 | Pending |
| SYNC-04 | Phase 6 | Pending |
| SYNC-05 | Phase 6 | Pending |
| SYNC-06 | Phase 6 | Pending |
| SYNC-07 | Phase 6 | Pending |
| SRCH-01 | Phase 6 | Pending |
| SRCH-02 | Phase 6 | Pending |
| SRCH-03 | Phase 6 | Pending |
| SRCH-04 | Phase 6 | Pending |
| SRCH-05 | Phase 6 | Pending |
| SRCH-06 | Phase 6 | Pending |
| UI-01 | Phase 7 | Pending |
| UI-02 | Phase 7 | Pending |
| UI-03 | Phase 7 | Pending |
| UI-04 | Phase 7 | Pending |
| UI-05 | Phase 7 | Pending |
| UI-06 | Phase 7 | Pending |
| UI-07 | Phase 7 | Pending |
| UI-08 | Phase 7 | Pending |
| UI-09 | Phase 7 | Pending |
| UI-10 | Phase 7 | Pending |
| UI-11 | Phase 7 | Pending |

**Cross-Cutting NFRs (referenced in each phase, not assigned to a single phase):**

| NFR | Referenced In | Status |
|-----|---------------|--------|
| NFR-12 | Phase 5, Phase 6 | Pending |
| NFR-13 | Phase 6 | Pending |
| NFR-14 | Phase 6 | Pending |
| NFR-15 | Phase 5, Phase 6 | Pending |
| NFR-16 | Phase 7 | Pending |
| NFR-17 | Phase 7 | Pending |
| NFR-18 | Phase 5 | Pending |

---

*Last updated: 2026-07-01 | M3 Requirements Approved*
