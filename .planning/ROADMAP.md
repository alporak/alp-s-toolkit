# Roadmap — Alps Toolkit

## Overview

This roadmap spans three milestones:
- **M1 (COMPLETE):** Core Competence Plugin — Phases 1-2
- **M2 (COMPLETE):** Performance Analytics v2 — Phases 3-4
- **M3 (ACTIVE):** Documentation Search Engine — Phases 5-7

---

## Completed Milestones

### M1: Core Plugin (COMPLETE)

- **Phase 1** — Backend: SQLite cache, Jira sync, state machine, stats/sync/chart API
- **Phase 2** — Frontend: SPA plugin with bar chart, sync button, status display

### M2: Performance Analytics v2 (COMPLETE)

- **Phase 3** — Backend: extended schema (8-col transitions + tickets), 8 endpoints, attribution tracking
- **Phase 4** — Frontend: tabbed power-dashboard, summary cards, per-ticket table, multi-chart views

---

## Active Milestone: M3 — Documentation Search Engine

**Goal:** A unified, fast full-text search plugin across 3 internal documentation repos (~3000 files) — git pull, text extraction, SQLite FTS5 search index, inline preview.

## Phases

- [ ] **Phase 5: Extraction & Index Foundation** — Text extraction pipeline for 6 formats + FTS5 index schema with content-less tables
- [ ] **Phase 6: Sync Engine & Search API** — Git sync with incremental updates + FTS5 search API with BM25 ranking
- [ ] **Phase 7: Frontend SPA** — Search UI with debounced search-as-you-type, inline preview, file-type filters, keyboard navigation

---

## Phase Dependency Graph

```
Phase 5 (Extraction & Index) ──► Phase 6 (Sync & Search) ──► Phase 7 (Frontend SPA)
```

Strictly sequential. Phase 6 depends on the FTS5 schema and extraction pipeline from Phase 5. Phase 7 depends on all API endpoints from Phase 6.

---

## Phase Details

### Phase 5: Extraction & Index Foundation

**Goal**: Documents from all 6 formats are reliably extracted with encoding detection, stored in a content-less FTS5 index, and hash-fingerprinted for incremental updates.

**Depends on**: Nothing (first M3 phase)

**Requirements**: EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05, INDEX-01, INDEX-02, INDEX-03, INDEX-04, INDEX-05

**Cross-cutting NFRs**: NFR-15 (zero new infrastructure dependencies — all extraction libs are stdlib or already-approved deps), NFR-18 (extraction failures logged but never crash sync pipeline)

**Success Criteria** (what must be TRUE):
  1. Any .docx, .pdf, .doc, .rst, .drawio, or .graphml file can be processed through the extraction pipeline, producing non-empty, encoding-detected text — extraction failures are logged but never crash
  2. PDFs with pages > 0 but extracted text < 20 chars are flagged `needs_ocr: true` in metadata (not silently empty)
  3. Every extracted file's encoding is detected via charset-normalizer and stored alongside the extracted text in metadata
  4. FTS5 index (`doc_search_fts`, content-less) and `doc_metadata` table are created on plugin startup with auto-migration — including SHA-256 hash, encoding, and needs_ocr columns
  5. Extraction functions are independently testable (`file_path → str`); files with unchanged SHA-256 hashes are correctly identified as not needing re-extraction

**Plans**: TBD

---

### Phase 6: Sync Engine & Search API

**Goal**: Users can trigger git sync across 3 repos, monitor progress in real-time, and search indexed documents with BM25-ranked results, highlighted snippets, and inline previews — with path traversal protection.

**Depends on**: Phase 5 (FTS5 schema, extraction pipeline, hash infrastructure)

**Requirements**: SYNC-01, SYNC-02, SYNC-03, SYNC-04, SYNC-05, SYNC-06, SYNC-07, SRCH-01, SRCH-02, SRCH-03, SRCH-04, SRCH-05, SRCH-06

**Cross-cutting NFRs**: NFR-12 (all blocking work runs in `asyncio.to_thread()`), NFR-13 (path traversal protection via `realpath()` validation), NFR-14 (search API response < 200ms), NFR-15 (no new infrastructure)

**Success Criteria** (what must be TRUE):
  1. User clicks "Sync Now" → sync begins asynchronously, progress indicator shows phase/done/total in real-time, and concurrent sync attempts are rejected (guard active)
  2. On plugin startup, initial sync kicks off as a background task — UI loads immediately with "Indexing..." status and no blocking
  3. Incremental sync: only files with changed SHA-256 hashes are re-extracted and re-indexed; files removed from disk are cleaned from the index
  4. User searches via `GET /search?q=term` → receives BM25-ranked results within 200ms showing repo, filename, highlighted snippet, and score; empty query returns empty results gracefully
  5. User requests a preview via `GET /preview/{repo}/{path}` → receives extracted text; path traversal attacks (`../`) return 403, not file content

**Plans**: TBD

---

### Phase 7: Frontend SPA

**Goal**: Users interact with a polished search interface featuring debounced search-as-you-type, color-coded repo badges, inline preview with highlighting, file-type filters, keyboard navigation, and sync controls — all following competence.js patterns.

**Depends on**: Phase 6 (all API endpoints must be stable)

**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, UI-08, UI-09, UI-10, UI-11

**Cross-cutting NFRs**: NFR-16 (follow existing competence plugin patterns — background task + polling, tabbed layout), NFR-17 (zero console errors, JS syntax valid)

**Success Criteria** (what must be TRUE):
  1. User types in the search bar → results appear with 250ms debounce, in-flight requests are cancelled on new keystrokes, and a loading spinner shows during requests
  2. Result list displays file type icon, color-coded repo badge, highlighted snippet with `<mark>` tags, and relevance score — all visually distinguishable at a glance
  3. User clicks a result → inline preview accordion expands showing ~500 chars with search term highlights; clicking another result replaces the preview
  4. File-type filter chips toggle visibility by format; keyboard navigation (Arrow keys/Enter/Escape) works for result focus, preview expansion, and search clearing
  5. Empty/error states display appropriate messages ("No results found for '{query}'", "Index building...", "0 repos configured"), error toasts appear on sync/search failures, and browser console shows zero errors

**Plans**: TBD
**UI hint**: yes

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Backend Plugin | 1/1 | Complete | M1 |
| 2. Frontend Dashboard | 1/1 | Complete | M1 |
| 3. Backend Enhancements | 1/1 | Complete | M2 |
| 4. Frontend Power-Dashboard | 1/1 | Complete | M2 |
| 5. Extraction & Index Foundation | 0/1 | Not started | - |
| 6. Sync Engine & Search API | 0/1 | Not started | - |
| 7. Frontend SPA | 0/1 | Not started | -

---

*Last updated: 2026-07-01 | M3 Roadmap Created*
