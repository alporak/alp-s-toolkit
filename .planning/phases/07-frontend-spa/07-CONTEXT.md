# Phase 7: Frontend SPA - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Users interact with a polished search interface featuring debounced search-as-you-type, color-coded repo badges, inline preview with highlighting, file-type filters, keyboard navigation, and sync controls — all following competence.js patterns.

Depends on Phase 6 (all API endpoints must be stable).

Requirements: UI-01..11
</domain>

<decisions>
## Implementation Decisions

### Layout & Interaction
- Search-as-you-type: 250ms debounce with AbortController for request cancellation
- 50 results per query, scrollable list (no pagination UI yet)
- Inline accordion preview: expands below clicked result, pushes results down — clicking another replaces the preview
- Sync button at top of page, next to search bar

### Visual Design & States
- Repo badges: blue (#3B82F6) for fmb-docs, green (#10B981) for teltonika, amber (#F59E0B) for isp_procedures
- File type icons: emoji — 📄 .docx, 📑 .pdf, 📝 .doc, 📋 .rst, 🔷 .drawio, 🕸 .graphml
- Preview panel: inline accordion below result — keeps context visible
- Loading: small spinner next to search bar + "Searching..." text in results area
- Empty states: "No results for '{query}'", "Index building... Click Sync Now", "0 repos configured"

### Claude's Discretion
- Exact CSS class names and styling details
- Spinner implementation (CSS animation vs emoji)
- Toast timing for sync completion
- Keyboard focus ring styling
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/static/js/core.js` — `h(tag, attrs, children)`, `api(url, opts)`, `toast(msg, type)`, `registerPlugin(p)`, `createTabs()`, `createTable()`, `icons` object
- `app/static/js/competence.js` — Reference plugin: ES module, `registerPlugin({id, name, order, svgIcon, init, destroy})`, tabbed layout pattern, async data loading
- `app/static/js/app.js` — Import chain for plugin JS files

### Established Patterns
- Plugin registration: `registerPlugin({ id: "doc_search", name: "Documentation Search", order: 46, svgIcon: icons.search, init(container), destroy() })`
- DOM building: `h()` helper with className, style, onclick, html attributes
- API calls: `api(url)` returns parsed JSON, auto-toasts on error
- Toast: `toast("message", "info"|"error"|"success", ms)`
- Module import: `import { h, api, toast, registerPlugin, icons } from "./core.js"`
- Plugin lifecycle: `init(container)` builds DOM, `destroy()` cleans up
- Single file per plugin, auto-discovered via `app.js` import

### Integration Points
- New file: `app/static/js/doc_search.js` (~300 lines)
- Modify: `app/static/js/app.js` — add `import "./doc_search.js";`
- API endpoints from Phase 6: `/api/doc_search/search`, `/api/doc_search/preview`, `/api/doc_search/repos`, `/api/doc_search/sync`, `/api/doc_search/sync/status`
</code_context>

<specifics>
## Specific Ideas

No specific requirements — follow competence.js patterns exactly. All decisions captured above.
</specifics>

<deferred>
## Deferred Ideas

None — all ideas within phase scope.
</deferred>
