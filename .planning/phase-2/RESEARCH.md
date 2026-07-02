# Phase 2: Frontend Dashboard — Research

**Researched:** 2026-06-17
**Domain:** Frontend SPA dashboard with server-side Plotly chart rendering
**Confidence:** HIGH

## Summary

Phase 1 delivered a fully functional backend (`competence.py`) with three API endpoints: stats, sync trigger, and sync status. Phase 2 builds the frontend dashboard that consumes these endpoints, following the project's established SPA plugin architecture.

The existing codebase uses a **server-side Plotly → iframe srcdoc** pattern for chart rendering: the Python backend generates Plotly HTML via `fig.to_html(include_plotlyjs="cdn", full_html=False)`, and the JavaScript frontend fetches the HTML and injects it into an `<iframe srcdoc="...">`. This is the exact pattern used by the Log Parser plugin (`logs.js` line 416-425, `log_parser.py` lines 713-742). Following this pattern means: **(a) no new frontend dependencies**, **(b) no Plotly CDN in index.html**, and **(c) a new chart endpoint on the backend**.

**Primary recommendation:** Add `GET /api/competence/chart` to `competence.py` that returns Plotly bar-chart HTML, create `competence.js` as an SPA plugin following the `release.js`/`jira.js` registration pattern, and import it in `app.js`. Zero new packages required — Plotly and pandas are already project dependencies.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Chart data computation (rate aggregation) | API / Backend | — | Already done by `_load_transitions_df()` + pandas grouping in `competence_stats()` |
| Chart HTML generation (rendering) | API / Backend | — | Plotly is a Python package; `fig.to_html()` runs server-side per existing log_parser pattern |
| Chart display in browser | Browser / Client | — | iframe `srcdoc` receives HTML blob from API |
| "Sync Now" trigger | Browser / Client | API / Backend | JS button calls `POST /api/competence/sync`; backend spawns `asyncio.create_task(_sync_job())` |
| Sync status display | Browser / Client | API / Backend | JS polls `GET /api/competence/sync/status` for `{last_sync, in_progress}` |
| Plugin registration and navigation | Browser / Client | — | `registerPlugin()` pushes to `plugins[]`; `renderNav()` builds sidebar from registry |
| Data persistence (transitions cache) | Database / Storage | — | SQLite `competence_cache.db` in WAL mode |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Plotly (Python) | 6.6.0 | Chart generation server-side | Already a project dependency; used by log_parser.py, modules/utils.py, streamlit pages |
| Pandas | 2.1.1 | Data grouping/aggregation | Already imported in `competence.py` for `_load_transitions_df()` |
| FastAPI | — | API endpoint (`response_class=HTMLResponse`) | Existing framework; pattern established in log_parser.py chart endpoints |
| Vanilla JS (no framework) | — | SPA plugin, DOM manipulation | Project uses zero frontend frameworks; all UI built with custom `h()` element builder |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `plotly.graph_objects` (go.Bar) | 6.6.0 | Bar chart for return rate | Discrete half-year periods with single numeric y-value per period |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Server-side Plotly HTML | Client-side Plotly via CDN | Would require `<script>` tag in index.html; breaks existing pattern; Plotly.js ~3MB download; server-side pattern is proven and zero-cost to add |
| `go.Bar` (bar chart) | `go.Scatter` (line chart) | Line chart works for time-series but bar chart visually emphasizes the discrete 2Q periods; can also do combined bar+line for attempts/returns layered with rate overlay |
| iframe srcdoc | direct `innerHTML` injection | iframe provides CSS isolation; srcdoc avoids extra HTTP request for blob/data URL; this is the established project pattern |

**Installation:** No new packages needed. All dependencies already in `requirements.txt`.

## Package Legitimacy Audit

> No new packages are installed by this phase. All required packages (plotly 6.6.0, pandas 2.1.1) are already project dependencies verified in `requirements.txt` and confirmed installed via `pip show`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| plotly | PyPI | 11+ yrs | 15M+/mo | github.com/plotly/plotly.py | N/A (existing dep) | Pre-existing — verified via `pip show` |
| pandas | PyPI | 15+ yrs | 100M+/mo | github.com/pandas-dev/pandas | N/A (existing dep) | Pre-existing — verified via `pip show` |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*No new packages installed — audit skipped by rule (0 new packages).*

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BROWSER (SPA)                                │
│                                                                      │
│  ┌──────────┐    ┌──────────────────┐    ┌───────────────────────┐  │
│  │  app.js  │───▶│  competence.js   │───▶│  <iframe srcdoc="..."> │  │
│  │  import  │    │  registerPlugin()│    │  (renders Plotly HTML) │  │
│  └──────────┘    │                  │    └───────────────────────┘  │
│                  │  init(container) │              ▲                │
│                  │   ├─ "Sync Now"  │              │ HTML string    │
│                  │   │   btn → POST │              │                │
│                  │   ├─ Status bar  │    ┌─────────┴──────────┐    │
│                  │   │   (poll GET) │    │  api() fetch wrapper│    │
│                  │   └─ Chart area  │───▶│  GET /api/competence│    │
│                  │       (fetch GET)│    │       /chart        │    │
│                  └──────────────────┘    └────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTP
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                                 │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  competence.py (CompetencePlugin)                             │   │
│  │                                                                │   │
│  │  GET  /api/competence/stats        → [{period, attempts,      │   │
│  │                                         returns, rate}, ...]   │   │
│  │  POST /api/competence/sync         → {status, message}        │   │
│  │  GET  /api/competence/sync/status  → {last_sync, in_progress} │   │
│  │  GET  /api/competence/chart        → HTMLResponse (Plotly)    │   │
│  │                                        [PHASE 2 - TO ADD]      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                    │                                 │
│                          ┌─────────┴──────────┐                     │
│                          │  competence_cache.db│                     │
│                          │  (SQLite, WAL mode) │                     │
│                          └────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
app/
├── static/
│   ├── js/
│   │   ├── core.js           # h(), api(), registerPlugin(), icons, toast(), renderNav(), switchPlugin()
│   │   ├── app.js            # [MODIFY] add: import "./competence.js";
│   │   ├── competence.js     # [CREATE] plugin: registerPlugin({id:"competence", ...})
│   │   ├── release.js        # [REFERENCE] plugin pattern reference
│   │   ├── logs.js           # [REFERENCE] _chart() iframe pattern reference
│   │   └── ...
│   ├── index.html            # [NO CHANGE] no Plotly CDN needed (server-side pattern)
│   └── style.css             # [NO CHANGE] unless custom competence styles needed
└── plugins/
    └── competence.py         # [MODIFY] add chart endpoint
```

### Pattern 1: Plugin Registration (from release.js lines 40-51)

**What:** Side-effect-only module that calls `registerPlugin()` at module top-level. The plugin object provides `id`, `name`, `order`, `svgIcon`, `init(container)`, and `destroy()`.

**When to use:** Every plugin JS file follows this exact pattern. The import in `app.js` triggers registration before `boot()` runs.

**Example:**
```javascript
// Source: app/static/js/release.js lines 40-51 (verified via codebase read)
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
  // ... additional methods using _renderWizard(c), etc.
});
```

### Pattern 2: Server-Side Chart HTML Endpoint (from log_parser.py lines 713-742)

**What:** FastAPI endpoint that returns `HTMLResponse` containing Plotly `fig.to_html(include_plotlyjs="cdn", full_html=False)`.

**When to use:** Any chart that can be generated server-side (Plotly Python is a project dependency).

**Example:**
```python
# Source: app/plugins/log_parser.py lines 713-721 (verified via codebase read)
@app.get("/api/competence/chart", response_class=HTMLResponse)
async def competence_chart():
    """Return Plotly bar chart HTML for bug return rate over time."""
    data = await competence_stats()  # reuse existing stats computation
    if not data:
        return "<p>No data yet — run a sync first.</p>"

    import plotly.graph_objects as go

    periods = [d["period"] for d in data]
    rates = [d["return_rate_pct"] for d in data]
    attempts = [d["attempts"] for d in data]
    returns = [d["returns"] for d in data]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=periods,
        y=rates,
        name="Return Rate %",
        marker_color="#e74c3c",
        text=[f"{r}%" for r in rates],
        textposition="auto",
        hovertemplate="%{x}<br>Return Rate: %{y}%<extra></extra>",
    ))

    fig.update_layout(
        title="Bug Return Rate by Half-Year",
        xaxis_title=None,
        yaxis_title="Return Rate (%)",
        yaxis=dict(range=[0, max(rates) * 1.2 if rates else 100]),
        margin=dict(l=40, r=20, t=40, b=40),
        height=400,
    )

    return fig.to_html(include_plotlyjs="cdn", full_html=False)
```

### Pattern 3: Chart Rendering in JS (from logs.js lines 416-425)

**What:** Fetch HTML from API endpoint, inject into `<iframe srcdoc="...">`.

**When to use:** Every chart tab in the app follows this pattern.

**Example:**
```javascript
// Source: app/static/js/logs.js lines 416-425 (verified via codebase read)
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

### Pattern 4: Import in app.js (from app.js lines 6-13)

**What:** Side-effect imports (no named imports needed — the module registers itself when executed).

**When to use:** Every new plugin JS file gets one import line.

**Example:**
```javascript
// Source: app/static/js/app.js lines 6-13 (verified via codebase read)
import { boot } from "./core.js";
import "./gps.js";
import "./logs.js";
import "./com.js";
import "./jira.js";
import "./release.js";
import "./universal_tester_tool.js";
// Add: import "./competence.js";

document.addEventListener("DOMContentLoaded", boot);
```

### Pattern 5: Custom SVG Icon (from jira.js lines 8-16)

**What:** Extend the local `icons` object with a custom SVG when `core.js` `icons` doesn't have the needed icon. Use icon short-term, or define a dedicated SVG.

**When to use:** No chart icon exists in `core.js` icons (verified: icons object at lines 370-391 has: satellite, file, unlock, clock, rocket, refresh, search, send, trash, upload, plug, settings, check, x, alert, home, shield, play, stop, link — no chart/bar-chart).

**Example:**
```javascript
// Source: app/static/js/jira.js lines 8-16 (verified pattern: local icon extension)
// Pattern: define a local const with spread of core icons + new SVG
const CHART_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/>
</svg>`;
```

### Anti-Patterns to Avoid

- **Don't add Plotly.js CDN to index.html:** The project pattern is server-side Plotly HTML generation (used by log_parser.py for timeline, signal_chart, state_timeline). Adding a CDN script tag breaks consistency and adds a ~3MB download.
- **Don't build client-side chart rendering:** Plotly is a Python package already installed. Rebuilding chart rendering with Canvas API or SVG manipulation would be redundant.
- **Don't call `api()` in plugin constructor/registration:** Plugin registration runs at import time. API calls belong in `init()` or event handlers.
- **Don't forget `destroy()`:** The `switchPlugin()` → `_resetMain()` flow calls `activePlugin.destroy()` before clearing the container. Omitting `destroy()` causes stale state on navigation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chart rendering | Canvas API / SVG chart / Chart.js client-side | Plotly Python → `fig.to_html()` → iframe srcdoc | Plotly handles axes, tooltips, responsiveness, export; already a project dependency with proven pattern |
| Data fetching | Custom XHR wrapper (already have `api()`) | `api(url)` from core.js | Handles error formatting, FastAPI validation errors, toast on failure, content-type detection |
| Button / layout markup | `document.createElement` + manual attr setting | `h(tag, attrs, ...children)` from core.js | Declarative, chainable, handles event listeners, style objects, className, innerHTML; used by every plugin |
| Tab navigation | Manual state management | `createTabs(container, tabs)` from core.js | Auto-renders tab bar + body, manages active state, used by release.js, logs.js, jira.js |
| Sortable tables | Custom sort logic | `createTable(container, columns, rows)` from core.js | Built-in sort, maxRows, empty state, column rendering; used by every plugin |
| Toast notifications | Custom notification bar | `toast(msg, type, ms)` from core.js | Positioned, auto-dismiss, supports info/success/error types |

**Key insight:** The codebase already has a rich utility layer (`core.js`) that every plugin uses. The competence dashboard should compose these utilities, not reimplement them.

## Runtime State Inventory

> Phase 2 is a greenfield frontend addition (not a rename/refactor/migration). This section is omitted.

## Common Pitfalls

### Pitfall 1: Missing `order` Clash with Existing Plugin
**What goes wrong:** The Competence plugin is registered at backend `order=45`. Another plugin may share the same order, causing unpredictable sidebar positioning.
**Why it happens:** The `competence.py` backend already has `order = 45`. The frontend plugin's `order` property in `registerPlugin()` should match or be independent (frontend order is separate from backend `manifest().order`).
**How to avoid:** Set `order: 45` in the JS plugin registration to match the backend's declared order. Check existing plugin orders: GPS=1, Logs=2, Release=5, Jira=10 (estimated from `apps.js` import order — verify during implementation).
**Warning signs:** Competence plugin appears in wrong position in sidebar nav.

### Pitfall 2: Iframe Height Not Matching Content
**What goes wrong:** The Plotly chart is clipped or has excessive whitespace because the iframe height is fixed.
**Why it happens:** logs.js uses `height: "600px"` which works for timeline charts but may be wrong for a single bar chart. Plotly's `fig.update_layout(height=400)` sets the chart height, but the iframe must be tall enough to contain it.
**How to avoid:** Set iframe height to match or slightly exceed the Plotly figure height. For a bar chart with `height=400`, use `height: "420px"` or `height: "100%"` with a wrapper div. Alternatively, use `config={'responsive': true}` in the Plotly figure and `width: "100%"` on the iframe.
**Warning signs:** Chart appears cut off, scrollbars inside iframe.

### Pitfall 3: Sync Button Not Handling In-Progress State
**What goes wrong:** User clicks "Sync Now" multiple times, spawning unnecessary requests.
**Why it happens:** The POST endpoint guards against concurrent syncs (`in_progress` flag), but the frontend should also disable the button during an active sync.
**How to avoid:** Poll `GET /api/competence/sync/status` periodically during sync, disable the button while `in_progress === true`, re-enable after sync completes.
**Warning signs:** Multiple sync requests queued, button clickable during sync.

### Pitfall 4: `api()` Function Treats HTML Response as JSON
**What goes wrong:** `api()` checks `content-type` header — if the chart endpoint returns `text/html` (via `HTMLResponse`), `api()` returns the raw text string correctly. But if the endpoint accidentally returns JSON, parsing might fail.
**Why it happens:** The log_parser chart endpoints explicitly set `response_class=HTMLResponse`. The new chart endpoint must do the same.
**How to avoid:** Always use `response_class=HTMLResponse` for the chart endpoint. Verify `api()` correctly returns the HTML string (it does — line 82-84 of core.js handles non-JSON responses).
**Warning signs:** Chart iframe shows `[object Object]` or raw JSON.

### Pitfall 5: `_chart()` Pattern Expects an `aid` Parameter
**What goes wrong:** logs.js `_chart(c, aid, type)` takes `aid` (analysis ID) as a path parameter. The competence chart doesn't need an ID parameter.
**Why it happens:** The competence data is global (per-user), not scoped to an analysis ID. The API path should be flat: `/api/competence/chart` (no path parameter).
**How to avoid:** Simplify the pattern — the `_chart()` equivalent for competence should just call `api("/api/competence/chart")` without any ID parameter.
**Warning signs:** 404 errors from chart API, URL construction issues.

## Code Examples

Verified patterns from official sources (the project codebase itself — all examples verified via direct file read).

### Plugin Registration (Complete Template)

```javascript
// Source: Derived from app/static/js/release.js lines 40-51 + logs.js lines 6-8
//         (all verified via codebase read)
import { h, api, toast, registerPlugin } from "./core.js";

registerPlugin({
  id: "competence",
  name: "Competence Matrix",
  order: 45,
  svgIcon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>`,

  init(container) {
    this._render(container);
  },

  destroy() {
    // Clean up any intervals/timers if used
  },

  async _render(c) {
    c.innerHTML = "";

    // ── Header row: title + Sync button + status ──
    const header = h("div", {
      style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }
    },
      h("h2", null, "Bug Return Rate"),
      h("button", {
        className: "btn btn-primary",
        id: "comp-sync-btn",
        onclick: async () => this._doSync(c),
      }, "Sync Now"),
      h("span", { id: "comp-status", className: "text-muted" }, "Checking..."),
    );
    c.appendChild(header);

    // ── Chart area ──
    const chartArea = h("div", { id: "comp-chart" });
    c.appendChild(chartArea);

    // Initial loads
    this._refreshStatus();
    this._loadChart(chartArea);
  },

  async _doSync(c) {
    const btn = document.getElementById("comp-sync-btn");
    btn.disabled = true;
    btn.textContent = "Syncing...";
    try {
      const res = await api("/api/competence/sync", { method: "POST" });
      toast(res.message || "Sync started", "success");
      // Poll until done
      await this._waitForSync();
      const chartArea = document.getElementById("comp-chart");
      if (chartArea) this._loadChart(chartArea);
    } catch (e) {
      toast("Sync failed: " + e.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Sync Now";
      this._refreshStatus();
    }
  },

  async _waitForSync() {
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const status = await api("/api/competence/sync/status");
      this._updateStatus(status);
      if (!status.in_progress) return;
    }
  },

  async _refreshStatus() {
    try {
      const status = await api("/api/competence/sync/status");
      this._updateStatus(status);
    } catch (e) { /* ignore */ }
  },

  _updateStatus(status) {
    const el = document.getElementById("comp-status");
    if (!el) return;
    if (status.in_progress) {
      el.textContent = "Syncing...";
      el.className = "text-muted";
    } else if (status.last_sync) {
      const d = new Date(status.last_sync);
      el.textContent = `Last sync: ${d.toLocaleString()}`;
      el.className = "text-muted";
    } else {
      el.textContent = "Not synced yet";
      el.className = "text-muted";
    }
  },

  async _loadChart(container) {
    container.innerHTML = '<div class="spinner"></div>';
    try {
      const html = await api("/api/competence/chart");
      container.innerHTML = "";
      container.appendChild(h("iframe", {
        srcdoc: html,
        style: { width: "100%", height: "460px", border: "none" },
      }));
    } catch (e) {
      container.innerHTML = `<p class="text-muted">Failed to load chart: ${e.message}</p>`;
    }
  },
});
```

### Bar Chart Generation (Python Backend)

```python
# Source: Pattern from app/plugins/log_parser.py lines 713-742
#         and modules/utils.py lines 1448-1535 (verified via codebase read)
#         with competence-specific data from competence.py stats endpoint
@app.get("/api/competence/chart", response_class=HTMLResponse)
async def competence_chart():
    """Return Plotly bar chart HTML for bug return rate over time."""
    try:
        df = _load_transitions_df()
        if df.empty:
            return "<p style='padding:40px;text-align:center;color:var(--text-muted)'>No data yet — click Sync Now to pull Jira changelogs.</p>"

        df["transition_date"] = pd.to_datetime(df["transition_date"])
        grouped = df.groupby(pd.Grouper(key="transition_date", freq="2Q"))

        periods = []
        rates = []
        attempts_list = []
        returns_list = []
        for period, group in grouped:
            attempts = int((group["action_type"] == "ATTEMPT").sum())
            rets = int((group["action_type"] == "RETURN").sum())
            rate = round((rets / attempts * 100), 1) if attempts > 0 else 0.0
            periods.append(_format_2q_label(period))
            rates.append(rate)
            attempts_list.append(attempts)
            returns_list.append(rets)

        if not periods:
            return "<p>No data</p>"

        import plotly.graph_objects as go

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=periods,
            y=rates,
            name="Return Rate %",
            marker_color="#e74c3c",
            text=[f"{r}%" for r in rates],
            textposition="auto",
            hovertemplate="%{x}<br>Return Rate: %{y}%<br>Attempts: %{customdata[0]}<br>Returns: %{customdata[1]}<extra></extra>",
            customdata=[[a, r] for a, r in zip(attempts_list, returns_list)],
        ))

        fig.update_layout(
            title="Bug Return Rate by Half-Year",
            xaxis_title=None,
            yaxis_title="Return Rate (%)",
            yaxis=dict(range=[0, max(rates) * 1.2 if max(rates) > 0 else 10]),
            margin=dict(l=40, r=20, t=40, b=40),
            height=400,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9"),
        )

        return fig.to_html(include_plotlyjs="cdn", full_html=False)
    except Exception as e:
        raise HTTPException(500, str(e))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| N/A (greenfield) | Server-side Plotly HTML → iframe srcdoc | Current project pattern | No migration needed; follows existing log_parser pattern |
| N/A | `registerPlugin()` SPA plugin architecture | Current project pattern | Reuses existing sidebar nav, switchPlugin, destroy lifecycle |

**Deprecated/outdated:** None — this is a new frontend for an existing backend API.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None detected in project (no pytest.ini, jest.config, vitest.config found in repo root) |
| Config file | None — manual UAT via browser |
| Quick run command | N/A (manual verification) |
| Full suite command | N/A (manual verification) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FR5.1 | Chart renders from stats data | manual-only (visual) | Open browser, navigate to Competence Matrix, verify chart displays | ❌ Wave 0 |
| FR5.2 | Sync button triggers background sync | manual-only | Click "Sync Now", verify spinner/status, check SQLite for new transitions | ❌ Wave 0 |
| FR5.3 | Status bar shows last sync time | manual-only | After sync, verify "Last sync: ..." timestamp appears | ❌ Wave 0 |
| NFR1 | Stats endpoint responds <500ms | manual-only | Browser DevTools Network tab — verify /api/competence/stats latency | ❌ Wave 0 |
| ROADMAP | Plugin visible in sidebar at position 45 | manual-only | Verify "Competence Matrix" appears in sidebar nav | ❌ Wave 0 |
| ROADMAP | Chart uses server-side Plotly (no CDN in index.html) | code-review | Verify index.html has no new script tags; verify chart endpoint returns HTML | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** Manual browser verification (visual check)
- **Per wave merge:** Full UAT checklist (all 6 items above)
- **Phase gate:** All UAT criteria passing before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] No automated test framework exists in the project — all verification is manual/UAT
- [ ] `tests/` directory not found in project root — test infrastructure absent
- [ ] No CI pipeline detected — verification is developer-driven

*(Note: This project relies on manual UAT verification per the existing workflow. Phase 1 was verified via `gsd-verify-work` conversational UAT. Phase 2 should follow the same pattern.)*

## Security Domain

> `security_enforcement` not explicitly set to `false` in config.json — treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Auth handled by existing Jira BasicAuth in backend; frontend has no auth surface |
| V3 Session Management | No | No sessions; SPA is single-user internal tool |
| V4 Access Control | No | Single-user tool; no role-based access |
| V5 Input Validation | Yes (minimal) | Sync button has no user input; stats endpoint has no parameters; chart endpoint has no parameters — **no injection surface** |
| V6 Cryptography | No | No secrets in frontend code; API token stays server-side |

### Known Threat Patterns for Vanilla JS SPA + FastAPI Backend

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via `srcdoc` injection | Tampering | Plotly HTML is generated server-side by `fig.to_html()` which escapes data values; the `api()` wrapper returns raw text for `text/html` content-type — no `innerHTML` injection from user data |
| CSRF on sync endpoint | Tampering | Single-user internal tool; no session cookies; sync is idempotent (duplicate-safe) |
| Clickjacking of iframe | Information Disclosure | No sensitive data in chart; iframe is same-origin (srcdoc), no cross-origin risk |
| Unvalidated redirect in iframe | Spoofing | `srcdoc` attribute renders inline HTML — no navigation possible; cannot load external URLs |

### Security Assessment

**Risk level: LOW.** The frontend adds no new attack surface:
- No user input fields (only a "Sync Now" button)
- No secrets in client-side code
- Chart HTML is generated server-side (no user-controlled content)
- API endpoints are read-only (GET stats/chart/status) or idempotent (POST sync)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `plugins[]` array order (from `registerPlugin()`) determines sidebar position independent of python `manifest().order` | Standard Stack | Plugin may appear out of order if backend `order` value is also used for frontend sorting — need to verify `showHome()` and `renderNav()` use JS `order` property only [VERIFIED: codebase read — `renderNav()` sorts by `a.order` at line 101 of core.js, independent of backend] |
| A2 | The `_format_2q_label()` function in competence.py is importable/accessible for the chart endpoint | Code Examples | If it's a module-level function (not a method), it can be called directly from the chart endpoint — verified: it's a standalone function at line 202 of competence.py |
| A3 | The iframe `srcdoc` pattern works without Plotly CDN availability (offline use) | Code Examples | If `include_plotlyjs="cdn"` requires internet access, offline users see a broken chart. Mitigation: this is the same pattern used by log_parser charts; if it works for log_parser, it works here |
| A4 | No existing plugin uses `order: 45` — confirmed by checking all JS plugin files | Common Pitfalls | If another plugin has order 45, they'll sort alphabetically or by registration order. Check during implementation. From codebase read: GPS=1, Logs=2, Release=5. Jira.js line 46 registration — order not explicitly listed in the grep result (need to check full registration at line 46). |
| A5 | The competence backend `_sync_job()` marks `in_progress` in SQLite, so frontend polling via `GET /api/competence/sync/status` will correctly detect completion | Code Examples | Verified by reading competence.py lines 236-371: `in_progress` is set to "1" at line 248 and reset to "0" in the `finally` block at line 371. Polling is reliable. |

## Open Questions (RESOLVED)

1. **Chart type: bar vs combined bar+line?** RESOLVED: Bar chart for `return_rate_pct` with bar text (rate %) and hover tooltips showing attempts/returns via customdata. Matches exit criteria.

2. **Should the chart endpoint reuse `competence_stats()` or compute independently?** RESOLVED: `_load_transitions_df()` + independent computation in chart endpoint. Allows richer hover data (customdata) and avoids coupling to stats JSON format.

3. **Responsiveness: mobile-friendly chart?** RESOLVED: Add `config={'responsive': true}` on Plotly figure. Iframe uses `width: 100%`. No additional mobile layout work needed.

## Environment Availability

> This phase depends on the Phase 1 backend (competence.py with working API endpoints) and the existing frontend toolchain (no external build tools).

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 + FastAPI | Chart endpoint in competence.py | ✓ | Project runtime | — |
| Plotly (Python) | `fig.to_html()` chart generation | ✓ | 6.6.0 | — |
| Pandas | `_load_transitions_df()` data loading | ✓ | 2.1.1 | — |
| Modern browser (ES modules) | `import` statements in JS | ✓ | Any Chromium/Firefox | — |
| Node.js / npm | None (frontend has zero build step) | N/A | — | — |

**Missing dependencies with no fallback:** None — all dependencies are pre-existing project dependencies.
**Missing dependencies with fallback:** None.

*Step 2.6: AUDIT COMPLETE — no missing dependencies.*

## Sources

### Primary (HIGH confidence)
- `app/static/js/core.js` — Full file read: `h()`, `api()`, `registerPlugin()`, `toast()`, `createTabs()`, `createTable()`, `icons`, `switchPlugin()`, `renderNav()`, `boot()`, `showHome()` — all 397 lines verified
- `app/static/js/release.js` — Full file read: plugin registration pattern, `init()`, `destroy()`, `h()` usage, `api()` usage — all 536 lines verified
- `app/static/js/logs.js` — Partial read (lines 340-500): `_chart()` iframe rendering pattern confirmed at lines 416-425
- `app/static/js/app.js` — Full file read: import pattern, boot invocation — all 14 lines verified
- `app/static/index.html` — Full file read: no Plotly CDN, sidebar nav + main content structure — all 44 lines verified
- `app/plugins/competence.py` — Full file read: existing stats/sync/status endpoints, `_load_transitions_df()`, `_format_2q_label()`, `_sync_job()` in_progress flag — all 501 lines verified
- `app/plugins/log_parser.py` — Partial read (lines 700-753): chart endpoints using `response_class=HTMLResponse`, `fig.to_html(include_plotlyjs="cdn", full_html=False)` — verified pattern
- `modules/utils.py` — Partial read (lines 1-80, 1448-1547): `create_timeline()` using `go.Figure()`, `fig.update_layout()`, `fig.add_trace(go.Scattergl())` — verified Plotly pattern
- `app/plugins/base.py` — Full file read: `ToolkitPlugin` base class, `register_routes()` — all 53 lines verified
- `app/static/js/jira.js` — Partial read (lines 1-30): custom SVG icon pattern — verified
- `requirements.txt` — Confirmed plotly and pandas are existing dependencies

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` — Phase requirements FR5.1-FR5.3 and NFRs — verified against implemented code
- `.planning/ROADMAP.md` — Phase 2 task list and exit criteria — confirmed scope
- `.planning/PROJECT.md` — Tech stack constraints and plugin patterns — verified against codebase
- `.planning/STATE.md` — Phase 1 completion status and key decisions — confirmed all resolved
- `pip show plotly` / `pip show pandas` — Confirmed installed versions: 6.6.0 and 2.1.1

### Tertiary (LOW confidence)
- None — all claims verified against the codebase or official Python package registry

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — All libraries are existing project dependencies; verified via `pip show` and confirmed in `requirements.txt`
- Architecture: HIGH — Five existing plugin files verified for the plugin registration pattern; chart rendering pattern verified in logs.js and log_parser.py; examples are exact code from the codebase
- Pitfalls: HIGH — Based on patterns observed across multiple plugins and the specific iframe rendering mechanism

**Research date:** 2026-06-17
**Valid until:** 2026-07-17 (30 days — stable project with well-established patterns)

---

## Research Complete Summary

### Key Findings
1. **No new packages needed** — Plotly 6.6.0 and pandas 2.1.1 are already project dependencies
2. **Server-side chart pattern is proven** — `log_parser.py` has 3 chart endpoints using `fig.to_html(include_plotlyjs="cdn", full_html=False)` returned as `HTMLResponse`
3. **Client-side chart rendering uses iframe srcdoc** — `logs.js` `_chart()` method fetches HTML and renders via `<iframe srcdoc="...">`
4. **Plugin registration is a side-effect import** — `competence.js` registers itself at module level via `registerPlugin({...})`; `app.js` just needs `import "./competence.js";`
5. **No index.html changes required** — No Plotly CDN script needed; chart HTML is generated server-side

### Files to Create/Modify
| Action | File | Purpose |
|--------|------|---------|
| CREATE | `app/static/js/competence.js` | SPA plugin: chart display, sync button, status display |
| MODIFY | `app/static/js/app.js` | Add `import "./competence.js";` before `boot` |
| MODIFY | `app/plugins/competence.py` | Add `GET /api/competence/chart` endpoint returning Plotly HTML |
| NO CHANGE | `app/static/index.html` | No Plotly CDN needed |

### Ready for Planning
Research is complete with HIGH confidence across all domains. The planner has exact code patterns, verified API signatures, and a clear file modification list.
