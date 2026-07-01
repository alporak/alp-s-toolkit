---
phase: 05-extraction-index-foundation
plan: "01"
subsystem: extraction
tags:
  - text-extraction
  - encoding-detection
  - sha-256
  - pdf
  - docx
  - pure-functions
dependency-graph:
  requires: []
  provides:
    - app.plugins.doc_extraction
  affects:
    - 05-02 (index schema + plugin class)
tech-stack:
  added:
    - pdfplumber
    - pypdf
    - python-docx
    - doc2txt
    - docutils
    - charset-normalizer
  patterns:
    - Pure-function extractors (no plugin/framework dependencies)
    - Format dispatch table (extension → callable)
    - Lazy imports inside extractors (fail gracefully on missing deps)
key-files:
  created:
    - app/plugins/doc_extraction.py
  modified:
    - requirements.txt
decisions:
  - "Silent extraction failure detection: if text is empty AND sha256 is empty (file missing), set error field — prevents extractors that return '' on failure from hiding errors"
  - "Scanned PDF detection re-opens file with pypdf for page-count check when extension is .pdf and text is empty — small perf cost for accurate needs_ocr flagging"
  - "GraphML namespace-aware search with no-namespace fallback for maximum compatibility with different .graphml generators"
metrics:
  duration: "3m 12s"
  files_created: 1
  files_modified: 1
  total_lines_added: 399
  tasks_completed: 2
  requirements_satisfied:
    - EXTR-01
    - EXTR-02
    - EXTR-03
    - EXTR-04
    - EXTR-05
  completed: "2026-07-01T14:20:00Z"
---

# Phase 5 Plan 1: Doc Extraction Pipeline Summary

**One-liner:** Pure-function text extraction pipeline with format dispatch table for 6 file types, charset-normalizer encoding detection, SHA-256 fingerprinting, and scanned-PDF flagging — zero plugin dependencies.

---

## Task Completion

### Task 1: Create `doc_extraction.py` — 6 extractors + dispatch + charset detection + SHA-256

**Commit:** `0a955f9` — `feat(05-01): create doc_extraction.py`

**What was built:**
- `compute_sha256(file_path)` — streaming SHA-256 in 64KB chunks, returns empty string for missing files
- `detect_encoding(text)` — charset-normalizer wrapper with `utf_8` fallback
- 6 format extractors, each `(file_path: str) -> str`:
  - `extract_docx` — paragraphs + tables (tab-separated cells)
  - `extract_pdf` — pdfplumber primary, pypdf fallback; scanned PDF detection (pages > 0, text < 20 → `""`)
  - `extract_doc` — doc2txt wrapper
  - `extract_rst` — docutils document tree recursive walk
  - `extract_drawio` — XML `mxCell` value attribute extraction
  - `extract_graphml` — namespace-aware `node/data` extraction with no-namespace fallback
- `EXTRACTORS` dispatch table: `{".docx": ..., ".pdf": ..., ".doc": ..., ".rst": ..., ".drawio": ..., ".graphml": ...}`
- `extract_text(file_path) -> dict` — returns `{text, encoding, needs_ocr, sha256, error}`; never raises unhandled exceptions (NFR-18)

**Lines:** 391 (plan minimum: 120)  
**Exports:** All 9 from plan verified callable  
**Verification:** All automated checks passed — module imports cleanly, 6 extractors callable, dict shape correct, failure handling for missing files returns `error` string

### Task 2: Add extraction dependencies to `requirements.txt` and verify imports

**Commit:** `f559088` — `chore(05-01): add 6 document extraction dependencies`

**Added packages (unpinned, latest):**
- `pdfplumber` (0.11.9)
- `pypdf` (6.14.2)
- `python-docx` (1.2.0)
- `doc2txt` (1.0.8)
- `docutils` (0.23)
- `charset-normalizer` (3.3.0)

**requirements.txt:** 34 lines (was 26, +8 under `# ── Document extraction ─────────────────────────` section)

**Verification:** All 6 packages install and import without errors on Windows/Python 3.10.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Silent failure detection for empty extraction results**
- **Found during:** Task 1 verification
- **Issue:** `extract_text('nonexistent.docx')` returned `error: None` even though extraction failed — extractors catch exceptions internally and return `""`, which left no trace that extraction failed vs. genuinely empty content
- **Fix:** Added post-extraction check in `extract_text()`: if `text` is empty AND `sha256` is empty (file not found/readable), set `error = "File not found or unreadable: ..."`. If `text` is empty but `sha256` is present (file exists but produced nothing), set `error = "Extraction produced no text for: ..."` for non-PDF files.
- **Files modified:** `app/plugins/doc_extraction.py`
- **Commit:** `0a955f9`

---

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries beyond what the threat model (`T-05-01`, `T-05-02`, `T-05-03`, `T-05-SC`) already covers.

---

## Known Stubs

None — all functions are fully implemented. No placeholders, TODO markers, or hardcoded empty values that flow to UI rendering.

---

## Success Criteria Verification

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Module imports cleanly with all 6 extractors callable | ✅ PASS |
| 2 | `extract_text(file_path)` returns dict with all 5 keys — never raises | ✅ PASS |
| 3 | Corrupt/missing files return `text=""` + non-None error string, logger.warning issued | ✅ PASS |
| 4 | Valid .docx/.pdf/.doc files produce non-empty text | ⚠️ DEFER — requires real fixture files (Plan 05-02) |
| 5 | Scanned PDF (pages>0, text<20 chars) → `needs_ocr: true` | ⚠️ DEFER — requires scanned PDF fixture (Plan 05-02) |
| 6 | `compute_sha256` returns consistent 64-char hex digests | ✅ PASS |
| 7 | `requirements.txt` updated, all 6 packages import successfully | ✅ PASS |

---

## Self-Check

**File existence:**
- `app/plugins/doc_extraction.py` — FOUND ✅
- `requirements.txt` — FOUND, contains 6 new packages ✅

**Commit existence:**
- `0a955f9` — FOUND ✅ (`feat(05-01): create doc_extraction.py`)
- `f559088` — FOUND ✅ (`chore(05-01): add 6 document extraction dependencies`)

**Import verification:**
- Module imports (all 9 exports) — PASS ✅
- Package imports (all 6 libraries) — PASS ✅
- `extract_text` dict shape (5 keys) — PASS ✅
- SHA-256 deterministic (same file → same hash) — PASS ✅
- Failure handling (missing file → error string) — PASS ✅
- Unsupported format detection — PASS ✅

## Self-Check: PASSED
