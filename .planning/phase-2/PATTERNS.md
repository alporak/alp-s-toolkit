# Phase 2: Competence & Performance Plugin — Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 3 (1 new JS module, 1 modified Python plugin, 1 modified entry point)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/static/js/competence.js` | plugin module | request-response + chart-in-iframe | `app/static/js/release.js` + `app/static/js/logs.js` | exact (release.js for plugin reg; logs.js for chart iframe) |
| `app/plugins/competence.py` | controller/route | request-response (JSON) + HTML (chart) | `app/plugins/log_parser.py` lines 713-742 | exact (same Plotly HTML endpoint pattern) |
| `app/static/js/app.js` | entry point | import wiring | `app/static/js/app.js` lines 1-13 | self-modification |

---

## Pattern Assignments

### 1. Plugin Registration Pattern (`competence.js`)

**Analog:** `app/static/js/release.js` lines 40-51 + `app/static/js/logs.js` lines 6-28

**Imports pattern** (release.js line 4):
```js
import { h, $, api, toast, registerPlugin, createTabs, createTable, icons, makeColumnsResizable } from "./core.js";
```

**Plugin registration block** (release.js lines 40-51):
```js
registerPlugin({
  id: "release", name: "Release Creator", order: 5,
  svgIcon: icons.rocket,
  _st: {},

  init(container) {
    this._st = {};
    createTabs(container, [
      { id: "cr",  label: "Create Release", render: c => this._renderWizard(c) },
      { id: "ver", label: "Versions",       render: c => this._renderVersions(c) },
    ]);
  },
  destroy() { this._st = {}; },
```

**How `competence.js` adapts this:**
```js
registerPlugin({
  id: "competence", name: "Competence Matrix", order: 7,
  svgIcon: icons.chart,  // <-- MUST add to core.js icons
  _st: {},

  init(container) {
    this._st = {};
    createTabs(container, [
      { id: "stats",  label: "Bug Return Rate", render: c => this._renderStats(c) },
      { id: "sync",   label: "Sync",            render: c => this._renderSync(c) },
    ]);
  },
  destroy() { this._st = {}; },
```

**Key rules:**
- `init(container)` receives the `#main` DOM element — render directly into it
- Internal state stored on `this._st` (or `this._curId`, `this._recData` etc as in logs.js)
- `destroy()` should clear internal state (no DOM cleanup needed, core.js handles it)
- `id` must match the Python plugin class `id` value

---

### 2. Import Pattern in app.js

**Analog:** `app/static/js/app.js` lines 1-13

**Current state:**
```js
/* ================================================================
   Alps Toolkit – Entry Point
   Imports all plugin modules and boots the application.
   ================================================================ */
import { boot } from "./core.js";
import "./gps.js";
import "./logs.js";
import "./com.js";
import "./jira.js";
import "./release.js";
import "./universal_tester_tool.js";

document.addEventListener("DOMContentLoaded", boot);
```

**Modification:** Insert after `import "./universal_tester_tool.js";` (line 11):
```js
import "./competence.js";
```

**New file should be (line 12):**
```js
import "./universal_tester_tool.js";
import "./competence.js";

document.addEventListener("DOMContentLoaded", boot);
```

**Convention:** One import per line, `.js` extension, alphabetical-ish order (competence after universal_tester_tool). No semicolons at line end preferred (following existing style).

---

### 3. Chart Rendering Pattern — iframe from Server-rendered HTML

**Analog:** `app/static/js/logs.js` lines 416-425 (`_chart` method)

**Existing pattern:**
```js
async _chart(c, aid, type) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const html = await api(`/api/logs/analysis/${aid}/${type}`);
      c.innerHTML = "";
      c.appendChild(h("iframe", {
        srcdoc: html, style: { width: "100%", height: "600px", border: "none" },
      }));
    } catch (e) { console.error("[Logs] Load chart failed:", e.message); c.innerHTML = "<p>Failed to load chart</p>"; }
  },
```

**How `competence.js` adapts this for the `_renderStats` tab:**
```js
async _renderStats(c) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const html = await api("/api/competence/chart");
      c.innerHTML = "";
      c.appendChild(h("iframe", {
        srcdoc: html, style: { width: "100%", height: "600px", border: "none" },
      }));
    } catch (e) {
      console.error("[Competence] Load chart failed:", e.message);
      c.innerHTML = "<p>Failed to load chart</p>";
    }
  },
```

**Key details:**
- `api()` in `core.js` lines 43-90 auto-detects response content-type: JSON returns parsed object, text returns raw string. For `response_class=HTMLResponse` on the server, `api()` returns the HTML string directly — perfect for `srcdoc`.
- The `api()` helper already includes toast error notifications for HTTP errors (core.js line 87).
- Always show `<div class="spinner"></div>` before fetch, clear it on success.
- The `c` parameter is the tab body element from `createTabs()`.

---

### 4. API Call Pattern

**Analog:** `app/static/js/core.js` lines 43-90 (the `api` helper), called throughout release.js

**GET pattern** (release.js line 86, 135):
```js
const d = await api(`/api/release/issue/${encodeURIComponent(key)}`);
const d = await api(`/api/release/free_slots?base=${encodeURIComponent(base)}`);
```

**POST pattern** (release.js lines 477-480):
```js
const tRes = await api("/api/release/ticket", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(ticketBody),
});
```

**Error handling** — the `api()` function in core.js handles:
- Non-2xx responses: parses FastAPI error detail, throws `Error(msg || 'HTTP ${status}')` (lines 52-74)
- Network errors: logs + toasts + rethrows (lines 85-89)
- Content-type detection: JSON → parsed object; text/HTML → raw string (lines 76-84)

**Caller-side error handling** (release.js lines 89, 492):
```js
try {
  const d = await api(`/api/...`);
  // ... handle success ...
} catch (e) { toast(`Fetch failed: ${e.message}`, "error"); }
```
**Note:** The `api()` core function already calls `toast()` internally (line 87). Callers can safely add their own toast for context-sensitive messages, but avoid double-toasting simple errors.

---

### 5. Button + Status/Loading Pattern

**Analog:** `app/static/js/release.js` lines 82-89 (quick fetch button) and lines 458-493 (long-running POST with spinner)

**Simple fetch button** (release.js lines 82-89):
```js
row.appendChild(h("button", { className: "btn btn-primary", onclick: async () => {
  const key = ($("#rel-src").value || "").trim().toUpperCase();
  if (!key) { toast("Enter a ticket key", "error"); return; }
  try {
    const d = await api(`/api/release/issue/${encodeURIComponent(key)}`);
    st.source_key = d.key; st.source_summary = d.summary || "";
    this._refresh(c);
  } catch (e) { toast(`Fetch failed: ${e.message}`, "error"); }
}}, h("span", { className: "btn-icon", html: icons.search }), "Fetch"));
```

**Long-running button with spinner** (release.js lines 458-493):
```js
btnRow.appendChild(h("button", { className: "btn btn-primary", onclick: async (ev) => {
  const btn = ev.currentTarget; btn.disabled = true;
  const orig = btn.innerHTML;
  btn.innerHTML = '<span class="spinner-sm"></span> Creating…';
  // ... read form values ...
  try {
    const tRes = await api("/api/release/ticket", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ticketBody),
    });
    toast(`Ticket ${tRes.key} created!`, "success");
    // ... render result ...
  } catch (e) { toast(`Ticket creation failed: ${e.message}`, "error"); }
  finally { btn.disabled = false; btn.innerHTML = orig; }
}}, "Create Ticket"));
```

**How `competence.js` adapts for the Sync tab button:**
```js
h("button", { className: "btn btn-primary", onclick: async (ev) => {
  const btn = ev.currentTarget; btn.disabled = true;
  const orig = btn.innerHTML;
  btn.innerHTML = '<span class="spinner-sm"></span> Syncing…';
  try {
    const res = await api("/api/competence/sync", { method: "POST" });
    toast(res.message || "Sync started", "success");
    this._checkSyncStatus(); // poll status after kicking off
  } catch (e) { toast(`Sync failed: ${e.message}`, "error"); }
  finally { btn.disabled = false; btn.innerHTML = orig; }
}}, h("span", { className: "btn-icon", html: icons.refresh }), "Sync from Jira")
```

**Key details:**
- Use `ev.currentTarget` to get the button reference (not `this` from arrow functions)
- `spinner-sm` CSS class for inline button spinners (sibling to `spinner` for full-area)
- Always `finally` block to restore button state
- `btn-icon` span wraps SVG icon inline with button text

---

### 6. SVG Icon Pattern

**Analog:** `app/static/js/core.js` lines 370-391 (`icons` object)

**No "chart" icon exists.** Must add one. The existing `icons.rocket` (line 375-376) is a good structural template:

```js
rocket: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">...</svg>`,
```

**New chart icon to add to `core.js` line ~391 (before the closing `};`)**:
```js
chart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
```

**Existing reusable icons for sync button:**
- `icons.refresh` (line 377) — refresh/sync symbol (two arrows in circle)
- `icons.search` (line 378) — magnifying glass

**Usage in nav icon registration:**
```js
svgIcon: icons.chart,
```

**Usage as inline button icon:**
```js
h("span", { className: "btn-icon", html: icons.refresh })
```

**Key rules:**
- All icons: `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="2"`
- Nav icon assigned via `svgIcon` property — core.js `renderNav()` wraps it in `.nav-icon` span
- Button icons: manually wrap in `h("span", { className: "btn-icon", html: ... })`

---

### 7. Server-side Plotly → HTML Endpoint Pattern

**Analog:** `app/plugins/log_parser.py` lines 713-742 + `modules/utils.py` lines 1480-1535

**Full endpoint pattern** (log_parser.py lines 713-721):
```python
@app.get("/api/logs/analysis/{aid}/timeline", response_class=HTMLResponse)
async def get_timeline_chart(aid: str):
    parsed = _get_parsed(aid)
    if not parsed:
        raise HTTPException(404)
    fig = create_timeline(parsed.get("events", []))
    if fig is None:
        return "<p>No events for timeline</p>"
    return fig.to_html(include_plotlyjs="cdn", full_html=False)
```

**How `competence.py` adds a chart endpoint:**

```python
from fastapi.responses import HTMLResponse
import pandas as pd
import plotly.graph_objects as go

# Inside CompetencePlugin.register_routes():

@app.get("/api/competence/chart", response_class=HTMLResponse)
async def competence_chart():
    """Return a Plotly bar chart of bug return rate by period."""
    try:
        df = _load_transitions_df()
        if df.empty:
            return "<p>No data yet. Run a Jira sync first.</p>"

        df["transition_date"] = pd.to_datetime(df["transition_date"])
        grouped = df.groupby(
            pd.Grouper(key="transition_date", freq="2Q")
        )

        periods = []
        rates = []
        for period, group in grouped:
            attempts = int((group["action_type"] == "ATTEMPT").sum())
            returns = int((group["action_type"] == "RETURN").sum())
            rate = round((returns / attempts * 100), 1) if attempts > 0 else 0.0
            periods.append(_format_2q_label(period))
            rates.append(rate)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=periods, y=rates,
            marker_color="#00b86b",
            text=[f"{r}%" for r in rates],
            textposition="outside",
        ))
        fig.update_layout(
            title="Bug Return Rate by Half-Year",
            xaxis_title=None,
            yaxis_title="Return Rate (%)",
            margin=dict(l=40, r=20, t=40, b=20),
            height=400,
        )

        return fig.to_html(include_plotlyjs="cdn", full_html=False)
    except Exception as e:
        raise HTTPException(500, str(e))
```

**Key details:**
- `response_class=HTMLResponse` is required — without it FastAPI JSON-serializes the HTML string
- `fig.to_html(include_plotlyjs="cdn", full_html=False)` — uses CDN for Plotly.js (no local install needed), returns `<div>` fragment only (no `<html><body>` wrapper, perfect for `iframe srcdoc`)
- `if fig is None` guard pattern for empty data (log_parser.py line 719)
- Already imports available: `pandas`, `datetime` are in competence.py; need to add `plotly.graph_objects as go`
- `_format_2q_label(period)` already exists in competence.py line 202
- `_load_transitions_df()` already exists line 215

---

### 8. HTML Structure / CDN Pattern

**Analog:** `app/static/index.html` (full file, 44 lines)

**No changes needed if using server-side Plotly.** The iframe pattern in logs.js renders the Plotly output as `srcdoc` — Plotly.js is loaded from CDN within the iframe's HTML context (controlled by `include_plotlyjs="cdn"` in `fig.to_html()`).

**If client-side Plotly is needed later** (not required for Phase 2), add to `index.html` head (after line 11):
```html
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
```

---

## Shared Patterns

### Authentication
**Source:** `app/plugins/base.py` + Jira credentials in `config`
**Apply to:** competence.py endpoints (already present)
```python
# No explicit auth middleware — credentials are loaded per-request via config.load_jira_config()
# The sync endpoint uses BasicAuth with Jira (competence.py lines 91-118)
```

### Error Handling (Server-side)
**Source:** `app/plugins/competence.py` lines 419, 439, 453 — already consistent
```python
except Exception as e:
    raise HTTPException(500, str(e))
```
**Apply to:** New chart endpoint

### Error Handling (Client-side)
**Source:** `app/static/js/core.js` lines 52-89 (`api()` function)
**Apply to:** All fetch calls in competence.js
- `api()` auto-toasts HTTP errors and re-throws
- Callers should wrap in try/catch for context-specific messages only

### Responsive Layout
**Source:** `app/static/js/logs.js` lines 33-36
```js
container.style.display = "flex";
container.style.gap = "0";
container.style.height = "100%";
```
**Apply to:** competence.js `init()` if using sidebar layout (optional — tabs layout is simpler)

### Tabs Helper
**Source:** `app/static/js/core.js` lines 168-190 (`createTabs()`)
**Apply to:** competence.js `init()` — call `createTabs(container, [...])` returning `{ activate, body, bar }`

### Toast Notifications
**Source:** `app/static/js/core.js` lines 31-40
```js
toast(msg, type = "info", ms = 3500)
```
Types: `"info"`, `"success"`, `"error"`, `"warning"`

---

## No Analog Found

All patterns have analogs in the codebase. No new patterns are required for Phase 2.

---

## Metadata

**Analog search scope:** `app/static/js/`, `app/plugins/`, `modules/`, `app/static/index.html`
**Files scanned:** 12 (release.js, logs.js, core.js, app.js, competence.py, log_parser.py, base.py, utils.py, index.html, gps.js, com.js, jira.js — the first 8 were read at depth)
**Pattern extraction date:** 2026-06-17
**Icons that need adding:** 1 (`chart` in core.js)
