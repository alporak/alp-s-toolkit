# Stack Research: Documentation Search Engine Plugin

**Domain:** Full-text search engine plugin for a FastAPI toolkit
**Researched:** 2026-07-01
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Whoosh (whoosh-reloaded) | 2.7.5 | Full-text search index and query engine | Pure Python, zero native deps. Built for document search: stemming, BM25 scoring, snippet highlighting, fuzzy matching. At ~3000 files, indexing takes seconds and queries return in <100ms. Separate index directory cleanly isolated from SQLite. |
| GitPython | 3.1.50 | Git repo sync (pull from 3 local repos) | Standard Python git library. Wraps `git pull` for existing repos cleanly — no subprocess management needed. Repo context manager ensures cleanup. Despite maintenance-mode label, it's stable and widely deployed. |
| python-docx | 1.2.0 | Text extraction from .docx files | De facto standard for Word 2007+ documents. `Document("file.docx").paragraphs[0].text` API is trivial. Also handles tables via `iter_inner_content()`. |
| pypdf | 6.14.2 | Text extraction from .pdf files | Modern successor to PyPDF2 (PyPDF2 is deprecated — do NOT use). Pure Python, actively maintained (releases every ~2 weeks), supports `extraction_mode="layout"` for layout-preserving extraction. Simpler and lighter than pdfplumber for text-only extraction. |
| docutils | 0.23 | Text extraction from .rst files | Official reStructuredText parser. Extracts plain text from RST documents by walking the doctree. Stdlib-like quality, maintained by Python community. |
| textract | 2.0.0 | Unified fallback for legacy .doc and other formats | Single-API extraction: `textract.process("file.doc")`. Handles .doc (via antiword/catdoc backend), .pptx, .odt, and dozens of other formats. Avoids maintaining per-format extraction code. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pdfplumber | 0.11.10 | Advanced PDF extraction (tables, layout) | Upgrade from pypdf if docs contain complex tables or you need visual debugging. Built on pdfminer.six. More powerful but heavier. |
| mark.js | 9.0.0 | Client-side search term highlighting | Highlights search terms in DOM elements. Supports `accuracy: "partially"`, case-insensitive, diacritics. Works standalone (no jQuery). Use `instance.mark("term")` on the preview container. |
| xml.etree.ElementTree | stdlib | Text extraction from .drawio and .graphml | Both formats are XML. Extract text from `<mxCell value="...">` (drawio) and `<node>`/`<data>` elements (graphml). No external library needed. |

### System Dependencies (for legacy .doc extraction)

| Dependency | OS | How to Install | Why Needed |
|------------|-----|---------------|------------|
| antiword | Linux | `apt install antiword` | textract backend for .doc → text conversion |
| antiword | macOS | `brew install antiword` | textract backend for .doc → text conversion |
| antiword.exe | Windows | Download from antiword website or use LibreOffice fallback | textract backend for .doc → text conversion |
| LibreOffice (optional) | All | `apt install libreoffice` / winget | Fallback if antiword unavailable: `soffice --headless --convert-to txt file.doc` |

### Frontend Dependencies (standalone, no npm/build step)

| Library | Version | Delivery | Purpose |
|---------|---------|----------|---------|
| mark.js | 9.0.0 | CDN: `https://cdn.jsdelivr.net/npm/mark.js@9/dist/mark.min.js` | Search term highlighting in preview pane |

## Per-Format Extraction Chain

```
File Extension → Extraction Method
════════════════════════════════════════════════════════
.docx         → python-docx (Document paragraphs + tables)
.pdf          → pypdf (PdfReader.extract_text)
               → pdfplumber (upgrade if tables needed)
.rst          → docutils (publish_doctree → text visitor)
.drawio       → xml.etree (extract mxCell/@value text)
.graphml      → xml.etree (extract node/data text)
.doc (legacy) → textract.process(file) → antiword backend
               → Fallback: subprocess soffice --headless --convert-to txt
.txt, .md, .py, .json, .yaml, .cfg, .ini, .html, .xml
              → open().read() (plain text, no extraction needed)
* (unknown)   → open().read() as raw text attempt
```

## Search Backend Decision

### Recommendation: Whoosh (whoosh-reloaded 2.7.5)

**Why Whoosh over alternatives:**

| Aspect | Whoosh | SQLite FTS5 | Tantivy |
|--------|--------|-------------|---------|
| Dependencies | Zero (pure Python) | Zero (already in project) | Rust compiled wheel (3.8MB) |
| Index flexibility | Free-form documents with any fields | Requires defined column schema | Structured schema |
| Stemming | Built-in (Snowball, Porter) | Manual porter tokenizer | Built-in language analyzers |
| Highlighting | Built-in `highlights()` method | `snippet()` function (limited) | Not built into Python bindings |
| Query features | Prefix, wildcard, fuzzy, phrase, boolean, range, faceting | Prefix, phrase, NEAR, boolean | Full Lucene-like query language |
| Indexing speed (3000 docs) | ~5-10 sec | ~3-5 sec | ~1-2 sec |
| Query latency | <100ms | <50ms | <10ms |
| API complexity | Simple, well-documented | SQL, verbose | Moderate |
| Separate index directory | Yes (clean isolation) | No (same SQLite DB) | Yes |

**Decision: Whoosh wins for this project because:**

1. **Designed for document search** — its entire API is about indexing documents and searching them. Stemming and highlighting are first-class features you get for free.
2. **Zero new native dependencies** — installs anywhere Python runs. No Rust toolchain, no compiled wheels to match to the server platform.
3. **Clean separation** — Whoosh index lives in its own directory alongside the plugin's SQLite database. If you delete the index, nothing else breaks.
4. **Right-sized at scale** — Whoosh handles 10K-50K documents comfortably. For 3K files, it's well within its sweet spot.

**When SQLite FTS5 would win:**
- You want zero new packages and are comfortable writing SQL for search
- You need search results joined with relational metadata in one query
- The search schema is rigid and column-based (author, title, body)

**When Tantivy would win:**
- You expect to grow to 100K+ documents
- Query latency must be <10ms under load
- You're comfortable managing a native dependency (Rust wheel)

### Whoosh Integration Pattern

```python
# Schema — defines what gets indexed and what's stored
from whoosh.fields import Schema, TEXT, ID, STORED, DATETIME

schema = Schema(
    path=ID(stored=True, unique=True),       # file path (primary key)
    repo=ID(stored=True),                     # which repo (for filtering)
    title=TEXT(stored=True),                  # filename or title
    content=TEXT,                             # full extracted text (indexed, not stored)
    file_type=TEXT(stored=True),              # docx, pdf, rst, etc.
    modified=DATETIME(stored=True),           # file modification time
)

# Index per-plugin in its own directory
from whoosh.index import create_in, open_dir
import os

index_dir = os.path.join(plugin_data_dir, "search_index")
if not os.path.exists(index_dir):
    ix = create_in(index_dir, schema)
else:
    ix = open_dir(index_dir)

# Indexing — extract text, add to index
writer = ix.writer()
for file_path in changed_files:
    text = extract_text(file_path)  # dispatch based on extension
    writer.update_document(
        path=file_path,
        repo=repo_name,
        title=os.path.basename(file_path),
        content=text,
        file_type=file_path.suffix,
        modified=os.path.getmtime(file_path),
    )
writer.commit()

# Searching — with highlighting
from whoosh.qparser import QueryParser, OrGroup

with ix.searcher() as searcher:
    parser = QueryParser("content", ix.schema, group=OrGroup)
    query = parser.parse(user_query)
    results = searcher.search(query, limit=20)
    for hit in results:
        print(hit["title"], hit.score)
        # Built-in snippet highlighting
        print(hit.highlights("content"))
```

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| PyPDF2 | Deprecated. Renamed to pypdf in 2023. PyPDF2 v3.0 was the last release before the rename. | pypdf 6.x |
| PyMuPDF (fitz) | AGPL license. Not suitable for internal company tool unless you purchase a commercial license. | pypdf + pdfplumber |
| Elasticsearch / Meilisearch | External service requiring separate process, Java runtime or daemon. Massive overkill for 3000 files. | Whoosh (embedded, zero process overhead) |
| Tantivy | Adds Rust native dependency (3.8MB wheel). Overkill at 3000-file scale. Better query API exists in Whoosh for Python. | Whoosh (or Tantivy if scaling past 50K docs) |
| Subprocess `git pull` | Raw subprocess calls mean parsing stdout, handling errors manually, no context manager cleanup. | GitPython (proper API, error handling) |
| jQuery (for mark.js) | mark.js works standalone. Adding jQuery is 87KB of unnecessary JS. | mark.js standalone (`new Mark(element).mark("term")`) |
| SQLite for search corpus | SQLite FTS5 requires column schema, no built-in stemming, limited snippet generation. | Whoosh for search, SQLite for metadata |
| textract as primary extractor | textract is a black box — you don't know which backend it picked or why it failed for a given file. | Use textract only as fallback for legacy .doc. Use format-specific libraries for .docx, .pdf, .rst. |
| highlight.js | Code syntax highlighter. Not designed for arbitrary search-term highlighting across DOM text nodes. | mark.js (purpose-built for search term highlighting) |
| doc2txt | Not a real maintained package. The actual tool is `antiword` (binary) wrapped by textract. | textract with antiword backend |
| New database engine | SQLite already used per-plugin. No need to introduce PostgreSQL or MongoDB. | Existing SQLite for metadata + Whoosh index directory for search |

## Installation

```bash
# Core extraction + search
pip install whoosh-reloaded==2.7.5
pip install GitPython==3.1.50
pip install python-docx==1.2.0
pip install pypdf==6.14.2
pip install docutils==0.23
pip install textract==2.0.0

# Optional: advanced PDF extraction
# pip install pdfplumber==0.11.10

# System dependency for legacy .doc (platform-specific):
# Linux:   sudo apt install antiword
# macOS:   brew install antiword
# Windows: download antiword.exe or install LibreOffice
```

## Integration with Existing Plugin Pattern

The new plugin (`app/plugins/docsearch.py`) follows the same `ToolkitPlugin` base class conventions as the Competence plugin:

```python
# app/plugins/docsearch.py
from app.plugin_base import ToolkitPlugin
from whoosh.index import open_dir, create_in

class DocSearchPlugin(ToolkitPlugin):
    def __init__(self):
        self.ix = None           # Whoosh index
        self.repo_paths = []     # Configured git repo paths
        self.db = None           # SQLite for metadata/config

    def register_routes(self):
        # Standard FastAPI route registration
        self.router.add_api_route("/docsearch/search", self.search)
        self.router.add_api_route("/docsearch/sync", self.sync)
        self.router.add_api_route("/docsearch/status", self.status)
        self.router.add_api_route("/docsearch/preview", self.preview)

    async def startup(self):
        # Open/create Whoosh index
        # Connect SQLite
        # Initial git pull on startup

    async def shutdown(self):
        # Close Whoosh index (searcher context managers auto-close)
        # Close git repo objects
        # Close SQLite connection
```

## Version Compatibility Matrix

| Package | Version | Python Requirement | Notes |
|---------|---------|-------------------|-------|
| whoosh-reloaded | 2.7.5 | Python >=3.9 | Latest stable (Feb 2026) |
| GitPython | 3.1.50 | Python >=3.7 | Maintenance mode, stable |
| python-docx | 1.2.0 | Python >=3.9 | Production/Stable |
| pypdf | 6.14.2 | Python >=3.9 | Actively maintained (bi-weekly releases) |
| pdfplumber | 0.11.10 | Python >=3.8 | Optional upgrade from pypdf |
| docutils | 0.23 | Python >=3.9 | Beta (but de facto stable) |
| textract | 2.0.0 | Python >=3.9 | Unified fallback extractor |
| mark.js | 9.0.0 | Browser (ES5+) | CDN delivery, no npm required |

## Sources

- Context7 `/python-openxml/python-docx` — docx reading API verification (CONFIDENCE: HIGH)
- Context7 `/jsvine/pdfplumber` — PDF extraction API verification (CONFIDENCE: HIGH)
- Context7 `/py-pdf/pypdf` — pypdf PdfReader.extract_text API (CONFIDENCE: HIGH)
- Context7 `/gitpython-developers/gitpython` — GitPython Repo clone/pull API (CONFIDENCE: HIGH)
- Context7 `/sygil-dev/whoosh-reloaded` — Whoosh index/search/query API (CONFIDENCE: HIGH)
- Context7 `/quickwit-oss/tantivy-py` — Tantivy Python bindings API (CONFIDENCE: HIGH)
- Context7 `/websites/markjs_io` — mark.js highlighting API (CONFIDENCE: HIGH)
- Context7 `/deanmalmgren/textract` — textract unified extraction API (CONFIDENCE: MEDIUM)
- Context7 `/docutils/docutils` — docutils RST parsing (CONFIDENCE: MEDIUM)
- PyPI `/pypdf` — version 6.14.2 verified (CONFIDENCE: HIGH)
- PyPI `/python-docx` — version 1.2.0 verified (CONFIDENCE: HIGH)
- PyPI `/GitPython` — version 3.1.50, maintenance mode confirmed (CONFIDENCE: HIGH)
- PyPI `/tantivy` — version 0.26.0, win_amd64 wheels confirmed (CONFIDENCE: HIGH)
- PyPI `/pdfplumber` — version 0.11.10 verified (CONFIDENCE: HIGH)
- PyPI `/textract` — version 2.0.0 verified (CONFIDENCE: HIGH)
- PyPI `/docutils` — version 0.23 verified (CONFIDENCE: HIGH)
- GitHub `/sygil-dev/whoosh-reloaded/releases` — version 2.7.5 confirmed (CONFIDENCE: HIGH)
- GitHub `/julmot/mark.js` package.json — version 9.0.0 confirmed (CONFIDENCE: HIGH)

---

*Stack research for: Documentation Search Engine plugin*
*Researched: 2026-07-01*
