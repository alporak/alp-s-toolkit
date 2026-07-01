# Phase 6: Sync Engine & Search API - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can trigger git sync across 3 repos, monitor progress in real-time, and search indexed documents with BM25-ranked results, highlighted snippets, and inline previews — with path traversal protection.

Depends on Phase 5 (FTS5 schema, extraction pipeline, hash infrastructure from `doc_extraction.py` and `doc_search.py`).

Requirements: SYNC-01..07, SRCH-01..06
</domain>

<decisions>
## Implementation Decisions

### Sync Engine Strategy
- Repo paths configured via `toolkit_settings.json` under `"doc_repos"` key — follows existing config patterns
- Git pull failure: log error, set sync state to "error" with message, don't crash — retries on next sync trigger
- Deleted files cleaned from index during sync walk — keeps index consistent with disk state
- Exactly 3 repos supported (configured in settings)

### Search API Design
- Query passed directly to FTS5 MATCH — power users get AND/OR/phrase/prefix operators for free
- 50 results per query, no pagination UI yet — single scrollable list
- Preview endpoint returns full extracted text (first 2000 chars) — frontend decides display amount
- `needs_ocr` files included in results with flag — snippet shows "Scanned PDF — text not searchable"

### Security & Performance
- Path traversal: `os.path.realpath()` check + verify path starts with allowed repo root → 403 on violation
- XSS: Strip HTML tags before storing in DB, use textContent for rendering, add `<mark>` tags via DOM API
- No CORS needed (same-origin plugin, existing FastAPI app)
- No search caching at 3000-doc scale — FTS5 queries return <50ms naturally

### Claude's Discretion
- Exact progress granularity for sync status (per-file vs per-repo vs phases)
- Subprocess timeout for git operations
- Error message wording
- Thread pool sizing for parallel extraction (research recommends max_workers=4)
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/plugins/doc_extraction.py` — `extract_text()`, `compute_sha256()`, `EXTRACTORS` dispatch table (from Phase 5)
- `app/plugins/doc_search.py` — DocSearchPlugin skeleton with FTS5 schema, `doc_metadata` table, `doc_search_fts` virtual table (from Phase 5)
- `app/plugins/competence.py` — Reference for async sync pattern: `asyncio.create_task()`, `in_progress` guard, status polling (`/sync/status`), `_sync_job()` coroutine, `asyncio.to_thread()` for blocking work
- `app/plugins/base.py` — ToolkitPlugin base class

### Established Patterns
- Async background tasks: `asyncio.create_task()` with `in_progress` bool guard
- Status polling: `GET /sync/status` returns `{phase, done, total, error}`
- Thread safety: `threading.Lock()` for DB writes, `asyncio.to_thread()` for blocking I/O
- Config: `toolkit_settings.json` for persistent settings
- URL convention: `GET /api/{plugin.id}/...` , `POST /api/{plugin.id}/...`

### Integration Points
- Modify `app/plugins/doc_search.py` — add sync engine, search API, preview endpoint to existing plugin skeleton
- Add `toolkit_settings.json` entries for repo paths
- No new files needed (extend existing plugin)
</code_context>

<specifics>
## Specific Ideas

No specific requirements — decisions captured above. Follow competence plugin async patterns exactly.
</specifics>

<deferred>
## Deferred Ideas

None — all ideas within phase scope and addressed in decisions above.
</deferred>
