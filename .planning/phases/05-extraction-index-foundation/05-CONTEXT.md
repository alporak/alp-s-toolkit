# Phase 5: Extraction & Index Foundation - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Documents from all 6 formats (.docx, .pdf, .doc, .rst, .drawio, .graphml) are reliably extracted with encoding detection, stored in a content-less FTS5 index, and hash-fingerprinted for incremental updates. This phase delivers the foundational data layer that Phases 6 and 7 depend on.

Requirements: EXTR-01..05, INDEX-01..05
</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and existing plugin conventions (competence.py patterns) to guide decisions.

### Prior Decisions (from Research)
- All blocking work must use `asyncio.to_thread()` (NFR-12)
- Extraction failures are logged but never crash (NFR-18)
- Zero new infrastructure dependencies (NFR-15)
- FTS5 content-less mode (`content='doc_metadata'`) for index storage efficiency
- Format dispatch table keyed on file extension: python-docx (.docx), pdfplumber (.pdf), doc2txt (.doc), docutils (.rst), xml.etree (.drawio, .graphml)
- charset-normalizer for encoding detection on all extracted text
- SHA-256 hashing for incremental update fingerprinting
- Scanned PDF detection: pages > 0 but text < 20 chars → flag `needs_ocr: true`
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/plugins/base.py` — ToolkitPlugin base class (plugin lifecycle)
- `app/plugins/competence.py` — Reference plugin: SQLite WAL mode, threading.Lock(), _get_db() pattern, schema versioning with auto-migration, module-level `plugin = ...` singleton
- `app/main.py` — Plugin auto-discovery from app/plugins/ with module-level `plugin` attribute

### Established Patterns
- SQLite: WAL mode, `check_same_thread=False`, `row_factory = sqlite3.Row`, threading.Lock for writes
- Plugin: `id`, `name`, `icon`, `order` class attributes; `register_routes(app)`, `startup()`, `shutdown()` methods
- DB schema: `sync_state` table with key/value pairs for version tracking
- File co-location: DB files live in `app/plugins/` alongside plugin code

### Integration Points
- New files: `app/plugins/doc_extraction.py` (pure functions), `app/plugins/doc_search.py` (plugin class)
- No modifications to existing files
- Plugin auto-discovered by `main.py` via module-level `plugin` attribute
</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. All decisions driven by research (SUMMARY.md) and ROADMAP success criteria.
</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase covers only the extraction pipeline and index schema.
</deferred>
