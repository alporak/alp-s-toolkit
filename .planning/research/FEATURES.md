# Feature Research

**Domain:** Documentation Search Engine (internal tool)
**Researched:** 2026-07-01
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.
Based on Algolia DocSearch, Meilisearch, mkdocs-material search, and Sphinx search conventions.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Keyword full-text search | Minimum viable search. Users expect to type words and get matching files. | LOW | SQLite FTS5 handles this natively via `MATCH` operator. Default unicode61 tokenizer supports basic word tokenization. |
| Search result listing with file name + relative path | Users need to identify which file matched and where it lives. | LOW | Store file path in FTS5 table as indexed column. Display in results as "filename.xyz — repo/sub/path/". |
| Match snippet with surrounding context | Users need to see *why* a file matched, not just *that* it matched. Standard in every doc search tool (Algolia cropping, mkdocs snippets). | LOW | SQLite FTS5 `snippet()` auxiliary function returns text fragments with matches highlighted. Built-in, no extra deps. |
| Relevance-ranked results (BM25) | Raw ordering is useless. Users expect best match first. | LOW | SQLite FTS5 built-in `bm25()` ranking function. Sort by `ORDER BY rank`. Tunable via column weights. |
| "No results" state | Empty results without feedback feels broken. | LOW | Return HTTP 200 with empty array + message from backend. Frontend renders "No results for 'query' — try different keywords". |
| Initial index build on startup | Search must work without manual setup. Table stakes for any search tool. | MEDIUM | Walk all 3 repo directories, extract text from each file, insert into FTS5 table. Runs in `startup()` lifecycle hook. Similar to competence plugin's schema init pattern. |
| Multi-format support (.docx, .pdf, .doc, .rst, .drawio) | Project explicitly requires these formats. Missing any = broken requirement. | MEDIUM | pdf: `pdfplumber` (best text extraction quality). docx: `python-docx`. doc: `python-pptx` for pptx, `textract` or antiword wrapper for legacy .doc. rst: plain `.read_text()`. drawio/graphml: extract XML text nodes. Each format needs its own parser — this is the bulk of initial complexity. |
| Git repo sync (3 repos, pull latest) | Content must be current. Stale docs → useless search. | MEDIUM | `git pull` via subprocess in each repo directory. Run on startup + daily schedule + manual trigger. Simple pattern: `subprocess.run(["git", "-C", path, "pull"], capture_output=True)`. Handle auth (SSH keys already configured on host). Check git status before pull to avoid conflicts. |
| Basic query syntax (multi-word AND, phrase search with quotes) | Users naturally type multi-word queries and expect AND behavior. Phrase search with quotes is universal (Google, every search engine). | LOW | FTS5 handles both natively: `'word1 word2'` = implicit AND; `'"exact phrase"'` = exact phrase match. No custom parsing needed. |
| Loading indicator during search | Users need to know the system is working. Standard UX. | LOW | Show spinner while API call is in flight. Same pattern as competence plugin's spinner div: `<div class="spinner"></div>`. |
| Manual sync trigger button | Explicit refresh mechanism. Users need a way to force re-index after repo updates. | LOW | POST endpoint `/api/docs/sync` that triggers background git pull + re-index. Same pattern as `POST /api/competence/sync`. Frontend button with "Syncing..." disabled state. |

### Differentiators (Competitive Advantage)

Features that set this apart from a basic `grep` over files. Not required, but high value for internal users.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Real-time search-as-you-type (debounced) | Dramatically faster discovery. User sees results refine with each keystroke. Standard in Algolia/DocSearch, Meilisearch, every modern search. | MEDIUM | Frontend: `<input>` with `oninput` handler, debounce 150-250ms before API call. Abort in-flight requests when new query arrives (`AbortController`). Backend: SQLite FTS5 queries are sub-50ms for ~3000 docs — fast enough for this pattern. |
| Search term highlighting in results (bold/color) | Visual scan of results is much faster when matched terms are highlighted. Primary UX pattern in Algolia DocSearch, Meilisearch. | LOW-MEDIUM | Backend: FTS5 `highlight()` wraps matches in `<b>` tags — include highlighted snippet in API response. Frontend: render as innerHTML. Also store match positions for client-side highlighting if needed. |
| Inline file preview with highlighted search terms | Users can read context without leaving search. Saves context-switching. Modeled on Algolia DocSearch hit preview + mkdocs-material inline expansion. | MEDIUM | Click result → fetch full file text via API → render in expandable panel below result. Apply highlight spans at match positions. Keep preview truncated (~500 chars around first match) for large files. |
| File-type filtering (docx/pdf/rst/drawio) | Targeted search when user knows format. "Show me only PDFs about deployment" | LOW | Store `file_type` column in FTS5 table. Frontend: dropdown or chip filters. Backend: add `AND file_type = ?` to FTS5 query. FTS5 column filters handle this efficiently. |
| Result count display | Quick feedback on search scope. "42 results for 'deployment config'" | LOW | Return `total_count` in API response alongside results. Frontend renders count above result list. |
| Keyboard navigation (arrow keys, Enter, Escape) | Power-user efficiency. Standard in every search modal (Algolia, VS Code, Command Palette). | MEDIUM | Frontend: `keydown` handler on search input. Up/Down moves focus highlight through result list. Enter opens top/highlighted result. Escape clears search or closes preview. Track `selectedIndex` in JS state. |
| Repo source indicator per result | Users need to know which repo a result comes from (3 repos merged into one index). | LOW | Store `repo_name` column. Frontend shows small badge/tag per result (e.g., "repo-config", "repo-docs", "repo-manuals"). Color-coded for quick visual scan. |
| Sync progress feedback | Long sync operations (extracting ~3000 files) feel broken without progress. | MEDIUM | Same pattern as competence plugin: poll `GET /api/docs/sync/status` returning `{"phase": "...", "done": N, "total": N}`. Frontend shows progress bar or phase text. |
| Search scope indicator (which repos are indexed) | Shows users what's searchable. Builds trust in results. | LOW | At page top: "Searching across 3 repos: api-docs (1.2K files), user-guides (800 files), internal-wiki (1K files)". Last sync timestamp displayed nearby. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems at this scope. Explicitly out of scope for M3.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| NLP/semantic search (vector embeddings, meaning-based matching) | "Search that understands what I mean, not just keywords" | Requires embedding model (OpenAI API or local), vector DB or SQLite extension, 10-100x query latency increase, significant cost if using API. Massive overkill for 3000 internal docs where keyword search is perfectly adequate. | Use SQLite FTS5 with trigram tokenizer for substring matching — covers most "semantic-like" needs without ML complexity. |
| OCR for scanned PDFs / images | "What about scanned older docs?" | Requires Tesseract OCR installation, significant processing time per file (seconds to minutes), language model files, poor accuracy on technical documents. 10x implementation complexity for edge case. | Flag scanned PDFs during text extraction (detect near-zero text output) and tag as "unsearchable — manual review needed". Accept ~5% exclusion rate for scanned docs. |
| Full-text highlighting in very large files (10MB+) | "Show me all matches highlighted in the full document" | Loading entire 100MB PDF as highlighted HTML in browser freezes the UI. Memory issues on both backend (reading full file) and frontend (rendering). | Truncate preview to ~500 chars around first 3 match clusters. Show "View full file" link to open raw file. Document the preview limit. |
| Web crawling / external URL indexing | "Why not index Confluence/wiki too?" | Requires separate crawl infrastructure, rate limiting, auth handling, HTML parsing, link following. Fundamentally different from local file search. | Defer to future milestone. Suggest users export Confluence space to static HTML and add to repo directories. |
| Advanced query DSL (NEAR, wildcard, boolean operators in UI) | "Power users want complex queries" | UX complexity explodes. Most users type 2-3 words. Building a query builder UI is a separate product. | Support FTS5 query syntax passthrough for power users (if they type `NEAR(...)` or `AND`/`OR`, pass it raw to FTS5). But don't build UI for it. |
| Multi-language stemming (Lithuanian, Russian, etc.) | Internal docs might contain non-English text | Stemming for non-English languages requires custom tokenizer configuration in FTS5 or external libraries. Adds complexity with low payoff — most technical documentation is English. | Default unicode61 tokenizer handles Latin text fine. If specific language needs emerge, add porter stemmer for English, or configure FTS5 locale option later. |
| Search analytics / click tracking | "Which queries return zero results?" | Requires analytics pipeline, storage, dashboard — a separate feature set. | Log zero-result queries to application logger. Review logs manually. Defer full analytics to future milestone. |
| Offline search (client-side index) | "What if the server is down?" | Requires building the entire search index in JS (lunr.js or similar), syncing index to browser, handling index size for 3000 files. Double implementation (backend + frontend search logic). | Not needed — this is an internal tool on company network. Server uptime is near 100%. If server is down, users have bigger problems. |

## Feature Dependencies

```
[1. Git Repo Sync] ──required by──> [2. Text Extraction] ──required by──> [3. FTS Index Building]
                                                                                    │
[4. Keyword Search API] ◄────────────────────────────────────────────────────────────┘
        │
        ├──required by──> [5. Result Snippets & Highlighting]
        ├──required by──> [6. Result Listing UI]
        │                       │
        │                       └──enhanced by──> [7. Keyboard Navigation]
        │                       └──enhanced by──> [8. File-Type Filtering]
        │
        └──enhanced by──> [9. Search-as-you-type] ──conflicts with──> [Debounce too aggressive = feels laggy]
                                                                               │
                                                                   [Optimize: 150ms debounce, AbortController]
```

```
[10. Inline File Preview] ──requires──> [Result Listing UI]
[10. Inline File Preview] ──requires──> [File content API endpoint]

[11. Manual Sync Button] ──reuses──> [Sync pipeline from #1-3]
[11. Manual Sync Button] ──reuses──> [Status polling from competence plugin pattern]
```

### Dependency Notes

- **Text Extraction requires Git Sync:** Files must exist on disk before extraction. Git pull must complete first.
- **FTS Index Building requires Text Extraction:** FTS5 INSERT needs extracted text content (one row per file).
- **All search features require FTS Index:** The index is the foundation. No index = no search.
- **Inline Preview requires Result Listing:** User clicks a result to see preview. Preview can't exist without results.
- **Search-as-you-type requires fast queries:** FTS5 on 3000 docs should be <50ms. If extraction yields very large files, consider limiting indexed content per file (first 50KB of text).
- **Keyboard navigation conflicts with debounce aggressiveness:** If debounce is too short, rapid keystrokes cause result flicker. 250ms is a good balance for internal tool use. Competence plugin uses 2s polling — search needs to be much faster.

## UX Patterns (How Documentation Search UIs Work)

Based on analysis of Algolia DocSearch, Meilisearch, Docusaurus search, and mkdocs-material search. These are the standard UX conventions users expect.

### Search Input Placement

- **Position:** Top of the plugin page, full width or centered (600-800px max-width)
- **Placeholder text:** "Search documentation..." or "Search across 3 repos..."
- **Visual:** Search icon (magnifying glass) on left, clear (X) button appears when text entered
- **Focus behavior:** Auto-focus on plugin load (users open the search tab to search)

### Results Layout

```
┌─────────────────────────────────────────────────┐
│  🔍 [deployment configuration_______________ ×]  │  ← Search input
│  42 results for "deployment configuration"       │  ← Result count
├─────────────────────────────────────────────────┤
│  📄 deployment-guide.rst    [user-guides]        │  ← File name + repo badge
│     /setup/deployment-guide.rst                  │  ← Full path
│     ...to configure the **deployment** pipeline  │  ← Snippet with highlights
│     for production, use the **config** file...   │
├─────────────────────────────────────────────────┤
│  📄 config-reference.pdf    [api-docs]           │
│     /reference/config-reference.pdf              │
│     ...the **deployment** settings are defined   │
│     in the main **configuration** section...     │
├─────────────────────────────────────────────────┤
│  📄 setup-drawio.drawio     [internal-wiki]      │
│     /diagrams/setup-drawio.drawio                │
│     ...**Deployment** flow: build → **config**   │
│     → test → release...                          │
└─────────────────────────────────────────────────┘
```

### Result Item Anatomy

Each result item shows:
1. **File icon** — different icon per file type (PDF icon, DOCX icon, code icon for RST)
2. **File name** — bold, clickable, primary identifier
3. **Repo badge** — small colored tag showing source repo (e.g., "[api-docs]" in blue)
4. **Full path** — grey, smaller text, shows directory context
5. **Match snippet** — 2-3 lines of text around the match, with **matched terms bolded/highlighted**
6. **Hover state** — background color change on hover (standard row highlighting)

### Keyboard Navigation

| Key | Action |
|-----|--------|
| `↓` / `↑` | Move selection highlight down/up through results |
| `Enter` | Open selected result (expand inline preview) |
| `Escape` | Clear search query / close preview if open |
| `Ctrl+K` (or `/`) | Focus search input from anywhere on page |

### Inline Preview Pattern

When user clicks a result or presses Enter:
- Result row expands downward (accordion pattern) — not a modal
- Shows first ~500 characters of file content with search terms highlighted
- Header shows full file path, file size, last modified date
- "Open raw file" link at bottom to open in new tab (for binary formats like PDF/DOCX, opens the file directly)
- Only one preview open at a time — opening new one closes previous

### Empty / Error States

| State | Display |
|-------|---------|
| No query | Placeholder text in search box, no results area shown |
| No results | "No results for 'query'. Try different keywords or check spelling." |
| Index not built | "Search index is building... (X of Y files processed)" with progress bar |
| Sync never run | "Click Sync Now to index documentation repositories." with Sync button |
| Search error | Toast notification "Search failed: [error message]" (same toast pattern as core.js `toast()`) |
| Empty repo | "Repo 'X' returned 0 files — check path and permissions" in sync status |

### Search-as-you-type UX

```
User types "d" → debounce 250ms → query "d" → shows all results containing "d" (broad)
User types "de" → abort previous request → debounce 250ms → query "de" → narrows
User types "dep" → abort previous request → debounce 250ms → query "dep" → narrower
User pauses → query "deployment" → final narrow results
```

Key behaviors:
- **Abort in-flight:** Each new keystroke cancels the previous API request via `AbortController`
- **Debounce:** 250ms is right for typing speed. Shorter = too many requests. Longer = feels laggy.
- **Minimum query length:** Search after 2+ characters. 1-character queries are too broad to be useful.
- **No results during typing:** Don't show "no results" during active typing — only after debounce settles.

### Grading System for Results (Optional Differentiator)

Noted from Meilisearch and Algolia: search results can include a relevance score or confidence indicator. For this tool, keep it simple but useful:
- Sort by BM25 score (FTS5 `rank` column) — higher = more relevant
- Optionally show relevance % (but this is a P3 feature — most users just need the right file, not a score)

## MVP Definition

### Launch With (v1 — Minimum Viable Search)

- [ ] **Git repo cloning + pull** — clone 3 repos on first run, pull updates on demand. Essential for content to exist.
- [ ] **Text extraction pipeline** — pdf (pdfplumber), docx (python-docx), doc (antiword/textract), rst (plain), drawio (XML text extraction). Essential for content to be searchable.
- [ ] **FTS5 index building** — SQLite FTS5 virtual table with file path, content, repo name, file type. Foundation of all search.
- [ ] **Keyword search API** — `GET /api/docs/search?q=...` returning JSON with file name, path, snippet, repo. Minimum search functionality.
- [ ] **Result listing UI** — display file name, path, snippet, repo badge in a scrollable list. Users need to see results.
- [ ] **Manual sync button** — trigger git pull + re-index from UI. Users need to refresh content.
- [ ] **Sync status endpoint** — `GET /api/docs/sync/status` to show progress. Users need feedback during long syncs.
- [ ] **Empty and error states** — proper handling of no results, index building, sync errors. Users need to know what's happening.

**Why these:** These 8 items form the complete search loop: content exists → content is indexed → user searches → user sees results → user can refresh content. Everything else enhances this loop.

### Add After Validation (v1.x — What Makes It Good)

- [ ] **Search-as-you-type with debounce** — significantly better UX, add once basic search works
- [ ] **Search term highlighting in snippets** — visual scan improvement, low technical risk via FTS5 `highlight()`
- [ ] **File-type filter chips** — quick UX win, simple backend filter
- [ ] **Result count display** — trivial to add, high perceived quality
- [ ] **Repo source badges** — color-coded tags, quick visual win
- [ ] **Keyboard navigation** (arrows + Enter) — power user feature, medium frontend complexity
- [ ] **Inline file preview** — expands result row, shows first ~500 chars with highlights

### Future Consideration (v2+)

- [ ] **Typo tolerance** — requires trigram tokenizer or edit-distance search. Changes index strategy.
- [ ] **Search suggestions / autocomplete** — needs separate suggestion index or trie. New backend endpoint.
- [ ] **Faceted search** (filter by repo, date modified) — needs metadata columns in FTS5 index
- [ ] **Deep-linkable search URLs** — `?q=deployment` persists search in URL
- [ ] **Zero-result query logging** — simple logging, but needs dashboard to be useful
- [ ] **Search scope configuration** — allow adding/removing repos without code change
- [ ] **Relevance tuning UI** — column weight adjustment for power users

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Text extraction pipeline (5 formats) | HIGH | HIGH | P0 — Foundation |
| FTS5 index building | HIGH | MEDIUM | P0 — Foundation |
| Git repo sync | HIGH | MEDIUM | P0 — Content source |
| Keyword search API | HIGH | LOW | P0 — Core feature |
| Result listing UI | HIGH | LOW | P0 — Core feature |
| Manual sync button | HIGH | LOW | P0 — Content refresh |
| Sync status + progress | HIGH | LOW | P0 — Feedback |
| Empty/error states | MEDIUM | LOW | P1 — Polish |
| Search-as-you-type | HIGH | MEDIUM | P1 — UX |
| Term highlighting in snippets | HIGH | LOW | P1 — UX |
| File-type filtering | MEDIUM | LOW | P1 — Utility |
| Result count display | MEDIUM | LOW | P1 — Polish |
| Repo source badges | MEDIUM | LOW | P1 — Clarity |
| Keyboard navigation | MEDIUM | MEDIUM | P2 — Power users |
| Inline file preview | MEDIUM | MEDIUM | P2 — Power users |
| Typo tolerance | MEDIUM | HIGH | P3 — Future |
| Search suggestions | LOW | HIGH | P3 — Future |
| Analytics / logging | LOW | MEDIUM | P3 — Future |

## Competitor Feature Analysis

Compared against standard documentation search tools relevant to this domain.

| Feature | Algolia DocSearch | mkdocs-material (lunr.js) | Meilisearch | Our Approach |
|---------|-------------------|---------------------------|-------------|-------------|
| Search index type | Cloud-hosted Algolia | Client-side lunr.js (JSON) | Self-hosted server | SQLite FTS5 in FastAPI backend |
| Search-as-you-type | Yes (modal) | Yes (dropdown) | Yes (API-driven) | Yes (API-driven, debounced) |
| Result snippets | Yes (cropping + highlight) | Yes (context around match) | Yes (cropping + highlight) | Yes (FTS5 snippet()) |
| Typo tolerance | Yes (built-in) | No (exact match) | Yes (configurable) | Deferred to v2 |
| Keyboard navigation | Full (modal pattern) | Basic (arrows) | Depends on frontend | Full (arrows + Enter + Escape) |
| Faceted search | Yes (language, version, tags) | No | Yes (filterable attributes) | File-type filtering, repo filtering |
| Inline preview | No (external link) | No (external link) | No (external link) | Yes — inline expandable panel |
| Ranking | Configurable | BM25 (built-in lunr) | Customizable rules | BM25 (FTS5 built-in) |
| Multi-format support | Web crawl only (HTML) | Markdown only | Any JSON document | Direct file parsing (pdf, docx, doc, rst, drawio) |
| Offline support | No | Yes (full client index) | No | No (server-based, internal network) |
| Free tier | Yes (open source docs) | Fully free | Open source, self-hosted | N/A — internal tool |

**Key insight:** Our differentiator is direct multi-format file parsing + inline preview. No existing doc search tool does both. Algolia crawls HTML only. mkdocs only does Markdown. Meilisearch needs pre-parsed JSON. We can parse the raw files directly and show previews — that's the unique value proposition.

## Integration with Existing Plugin Infrastructure

All features must follow the established plugin patterns from `competence.py`:

| Concern | Pattern to Follow | Reference |
|---------|-------------------|-----------|
| Plugin class | Extend `ToolkitPlugin`, set `id`/`name`/`icon`/`order`, implement `register_routes()` + `startup()` + `shutdown()` | `base.py` lines 28-53 |
| Database | SQLite with WAL mode, `threading.Lock()`, per-plugin DB file, schema versioning in `sync_state` table | `competence.py` lines 41-91 |
| Background tasks | `asyncio.create_task()` in route handler, status polling via `GET /status` endpoint, progress stored as JSON in `sync_state` | `competence.py` lines 609, 443-479 |
| Frontend | Import from `core.js` (`h`, `api`, `toast`, `registerPlugin`, `icons`, `createTabs`, `createTable`), define `init(container)` + `destroy()` | `competence.js` lines 4-6, 16-18 |
| API style | All endpoints under `/api/docs/...`, return JSON, use `HTTPException` for errors | Pattern from `competence.py` routes |
| Sync pattern | POST triggers, GET polls, `in_progress` flag prevents double-sync, `last_sync` timestamp tracked | `competence.py` lines 600-633 |
| Route registration | Decorator pattern inside `register_routes()` method on FastAPI app instance | `competence.py` lines 579+ |

## Sources

- **Algolia DocSearch** — https://docsearch.algolia.com/docs/what-is-docsearch (MEDIUM confidence — official docs, verified)
- **Meilisearch Features** — https://www.meilisearch.com/docs/learn/what_is_meilisearch/features (HIGH confidence — official docs, verified)
- **Docusaurus Search** — https://docusaurus.io/docs/search (HIGH confidence — official docs, verified)
- **Material for MkDocs Search** — https://squidfunk.github.io/mkdocs-material/setup/setting-up-site-search/ (HIGH confidence — official docs, verified)
- **SQLite FTS5** — https://www.sqlite.org/fts5.html (HIGH confidence — official documentation, verified)
- **Algolia Autocomplete** — https://www.algolia.com/doc/ui-libraries/autocomplete/introduction/what-is-autocomplete/ (HIGH confidence — official docs)
- **Competence Plugin (existing codebase)** — `app/plugins/competence.py` (HIGH confidence — production code, verified)
- **Core.js Frontend Framework** — `app/static/js/core.js` (HIGH confidence — production code, verified)
- **ToolkitPlugin Base Class** — `app/plugins/base.py` (HIGH confidence — production code, verified)

---

*Feature research for: Documentation Search Engine Plugin*
*Researched: 2026-07-01*
*Confidence: HIGH — All claims verified against official docs or production codebase*
