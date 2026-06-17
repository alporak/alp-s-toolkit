---
phase: 02-competence-frontend
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - app/static/js/competence.js
  - app/plugins/competence.py
  - app/static/js/core.js
  - app/static/js/app.js
autonomous: true
requirements:
  - FR5
user_setup: []

must_haves:
  truths:
    - "Competence Matrix plugin visible in sidebar at position matching order=45"
    - "Chart renders with period labels on x-axis, return rate on y-axis via server-side Plotly HTML in iframe"
    - "Sync Now button triggers POST /api/competence/sync, disables during sync, shows visual feedback"
    - "Status display shows last sync time after sync completes"
    - "Layout matches existing plugin design conventions (header, content area, proper spacing)"
  artifacts:
    - path: "app/static/js/competence.js"
      provides: "SPA plugin: chart display, sync button, status bar"
      min_lines: 80
    - path: "app/plugins/competence.py"
      provides: "GET /api/competence/chart endpoint returning Plotly HTML"
    - path: "app/static/js/core.js"
      provides: "chart SVG icon added to icons object"
    - path: "app/static/js/app.js"
      provides: "side-effect import of competence.js"
  key_links:
    - from: "app/static/js/competence.js"
      to: "GET /api/competence/chart"
      via: "api() fetch in _loadChart()"
      pattern: "api\(\"/api/competence/chart\"\)"
    - from: "app/static/js/competence.js"
      to: "POST /api/competence/sync"
      via: "api() fetch with method:POST"
      pattern: "api\(\"/api/competence/sync\".*POST"
    - from: "app/static/js/competence.js"
      to: "app/plugins/competence.py"
      via: "iframe srcdoc with Plotly HTML from server"
      pattern: "srcdoc.*html"
    - from: "app/static/js/app.js"
      to: "app/static/js/competence.js"
      via: "side-effect ES module import"
      pattern: "import.*competence\\.js"
---

<objective>
Deliver the Competence & Performance frontend dashboard: a new SPA plugin (`competence.js`) that displays bug return rate over time via a server-side Plotly bar chart rendered in an iframe, a "Sync Now" button that triggers background Jira sync, and a status display showing the last sync time.

Purpose: Phase 1 delivered a fully functional backend with stats, sync, and sync/status API endpoints. Phase 2 adds the user-facing dashboard following the project's established SPA plugin architecture — no new packages, no index.html changes, reusing the `registerPlugin()` → `api()` → `iframe srcdoc` pattern chain proven by the existing Log Parser and Release Creator plugins.

Output: One new JS file (`competence.js`), one new chart endpoint in `competence.py`, one new SVG icon entry in `core.js`, and one import line in `app.js`. All four artifacts are wired together to produce a working dashboard accessible from the sidebar navigation.
</objective>

<execution_context>
@.planning/phase-2/RESEARCH.md
@.planning/phase-2/PATTERNS.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md

# Source files being modified (read for exact insertion points)
@app/plugins/competence.py (lines 386-501: register_routes and lifecycle)
@app/static/js/core.js (lines 369-391: icons object)
@app/static/js/app.js (lines 1-14: imports + boot)
@app/static/js/logs.js (lines 416-425: _chart iframe pattern)
@app/static/js/release.js (lines 40-51: plugin registration pattern)
</context>

<tasks>

<!-- ═══════════════════════════════════════════════════════════════
     WAVE 1: Backend chart endpoint + frontend icon
     These two changes have zero dependencies on each other
     or on any new file — both modify existing files.
     ═══════════════════════════════════════════════════════════════ -->

<task type="auto" wave="1">
  <name>Task 1: Add chart SVG icon to core.js + Plotly chart endpoint to competence.py</name>
  <files>
    <file>app/static/js/core.js</file>
    <file>app/plugins/competence.py</file>
  </files>

  <action>
    <step order="1" file="app/static/js/core.js">
      Add a `chart` SVG icon to the `icons` object at line ~390 (before the closing `};` on line 391).

      Use this exact SVG — a 3-bar chart following the existing icon conventions
      (viewBox="0 0 24 24", fill="none", stroke="currentColor", stroke-width="2",
      stroke-linecap="round", stroke-linejoin="round"):

      ```
      chart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>`,
      ```

      Insert after the `link` icon on line 390 and before `};` on line 391. Follow the
      existing comma-separated format — the `link` entry ends with a comma, so add the
      `chart` entry and ensure the closing `};` is on its own line after it.
    </step>

    <step order="2" file="app/plugins/competence.py">
      Add a `GET /api/competence/chart` endpoint inside `register_routes()` (after the
      existing `competence_sync_status` endpoint, before the `# ── Lifecycle hooks`
      comment block at line 455).

      The endpoint reuses the existing `_load_transitions_df()` and `_format_2q_label()`
      functions already in the file. It computes the same 2Q grouping as `competence_stats()`
      but independently (no coupling to the JSON serialization format of the stats endpoint),
      then builds a Plotly `go.Figure()` with a single `go.Bar` trace and returns
      `fig.to_html(include_plotlyjs="cdn", full_html=False)` as an `HTMLResponse`.

      Implementation details:

      - Add `from fastapi.responses import HTMLResponse` to the imports at the top of the file
        (line 17 currently imports `FastAPI, HTTPException` — add `HTMLResponse` alongside).
      - Import `plotly.graph_objects as go` — add `import plotly.graph_objects as go` near the
        other imports (around line 16-17, near the `import pandas as pd` line).
      - The endpoint signature: `@app.get("/api/competence/chart", response_class=HTMLResponse)`
        `async def competence_chart():`
      - Load via `df = _load_transitions_df()` — if empty, return a plain HTML `<p>` message:
        `"<p style='padding:40px;text-align:center;color:var(--text-muted)'>No data yet — click Sync Now to pull Jira changelogs.</p>"`
      - Convert dates: `df["transition_date"] = pd.to_datetime(df["transition_date"])`
      - Group by 2Q: `grouped = df.groupby(pd.Grouper(key="transition_date", freq="2Q"))`
      - Iterate groups, compute per-period: `attempts` (ATTEMPT count), `returns` (RETURN count),
        `rate = round((returns / attempts * 100), 1) if attempts > 0 else 0.0`
      - Build `go.Figure()` with `go.Bar(x=periods, y=rates, ...)`:
        - `marker_color="#e74c3c"` (red bar to match the project's alert/error color)
        - `text=[f"{r}%" for r in rates]` with `textposition="auto"` for value labels on bars
        - `hovertemplate="%{x}<br>Return Rate: %{y}%<extra></extra>"` for clean tooltips
      - `fig.update_layout()`:
        - `title="Bug Return Rate by Half-Year"`
        - `yaxis_title="Return Rate (%)"`, `xaxis_title=None`
        - `yaxis=dict(range=[0, max(rates) * 1.2 if max(rates) > 0 else 10])`
        - `margin=dict(l=40, r=20, t=40, b=40)`, `height=400`
        - `paper_bgcolor="rgba(0,0,0,0)"`, `plot_bgcolor="rgba(0,0,0,0)"` for dark-theme compatibility
        - `font=dict(color="#c9d1d9")` to match existing chart text color
      - Return: `return fig.to_html(include_plotlyjs="cdn", full_html=False)`
      - Wrap in try/except: `raise HTTPException(500, str(e))` on failure
      - Handle edge case: if `periods` list is empty after grouping (no transitions matched
        any group), return a plain `<p>` message.

      Exact placement: after line 453 (`raise HTTPException(500, str(e))` of
      `competence_sync_status`) and before line 455 (`# ── Lifecycle hooks`).
    </step>
  </action>

  <verify>
    <automated>
      # 1. Verify icon was added (grep for "chart:" in core.js, filtering out comments)
      grep -n "chart:" app/static/js/core.js | grep -v "^[[:space:]]*//"

      # 2. Verify Python imports were added
      grep -n "HTMLResponse" app/plugins/competence.py
      grep -n "plotly.graph_objects" app/plugins/competence.py

      # 3. Verify endpoint is registered
      grep -n "competence/chart" app/plugins/competence.py

      # 4. Start server and hit the chart endpoint
      curl -s http://localhost:8000/api/competence/chart | head -c 200
      # Should return HTML (not JSON) — look for "&lt;div" or "&lt;script"
    </automated>
  </verify>

  <done>
    1. `icons.chart` is defined in core.js with a valid bar-chart SVG
    2. `GET /api/competence/chart` returns HTML content (verified via curl)
    3. Endpoint returns "No data yet" HTML message when cache is empty
    4. All existing tests/endpoints still pass (stats, sync, sync/status unaffected)
  </done>
</task>

<!-- ═══════════════════════════════════════════════════════════════
     WAVE 2: Plugin JS skeleton — registration + layout structure
     Depends on: Wave 1 (icons.chart must exist in core.js)
     ═══════════════════════════════════════════════════════════════ -->

<task type="auto" wave="2">
  <name>Task 2: Create competence.js — plugin registration and layout skeleton</name>
  <files>
    <file>app/static/js/competence.js</file>
  </files>

  <action>
    Create `app/static/js/competence.js` as a new SPA plugin module. This file will be
    extended by Tasks 3–4; this task establishes the registration, imports, `init()`,
    `destroy()`, and static layout markup only.

    <step order="1">
      File header: Add a comment block matching the existing plugin convention:
      ```
      /* ================================================================
         Competence Matrix Plugin — Bug return rate dashboard
         ================================================================ */
      ```
    </step>

    <step order="2">
      Import from core.js. Only import what is needed:
      ```js
      import { h, api, toast, registerPlugin, icons } from "./core.js";
      ```
      (No `createTabs`, `createTable`, `$`, or `makeColumnsResizable` are needed for this
      plugin — the dashboard is a single view, not tabbed. The `h()` builder, `api()` fetcher,
      `toast()` notifier, `registerPlugin()` registrar, and `icons` object are sufficient.)
    </step>

    <step order="3">
      Register the plugin at module top-level (side-effect pattern — runs on import):
      ```js
      registerPlugin({
        id: "competence",
        name: "Competence Matrix",
        order: 45,
        svgIcon: icons.chart,

        init(container) {
          this._render(container);
        },

        destroy() {
          // No timers or intervals to clear; just nullify state
        },

        // ── Layout ──────────────────────────────────────────
        _render(c) {
          c.innerHTML = "";

          // Header row
          const header = h("div", {
            style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }
          },
            h("h2", null, "Bug Return Rate"),
            h("button", {
              className: "btn btn-primary",
              id: "comp-sync-btn",
              onclick: async () => this._doSync(),
            }, "Sync Now"),
            h("span", { id: "comp-status", className: "text-muted" }, "Checking..."),
          );
          c.appendChild(header);

          // Chart area
          const chartArea = h("div", { id: "comp-chart" });
          c.appendChild(chartArea);
        },
      });
      ```
      Key design decisions:
      - `id: "competence"` matches the Python plugin class `id` and the module filename.
      - `order: 45` matches the backend `order = 45` (sidebar position).
      - `svgIcon: icons.chart` uses the icon added in Task 1.
      - No tab system — single-purpose dashboard doesn't need `createTabs()`.
      - Element IDs (`comp-sync-btn`, `comp-status`, `comp-chart`) are used by later methods
        to update specific DOM nodes — consistent with the `release.js` pattern of referencing
        elements by ID within the plugin container.
      - The `_doSync()` method is referenced but not yet implemented — it will be filled in
        by Task 4. For now, the button exists in the DOM but its click handler target won't
        resolve until the method is added.
      - **However**: the `onclick` handler above references `this._doSync()` which doesn't
        exist yet at this wave. Change the onclick to a no-op stub that Task 4 will replace:
        ```js
        onclick: () => toast("Sync not yet wired", "info"),
        ```
        Task 4 will rewrite this line with the real `_doSync` call.
    </step>
  </action>

  <verify>
    <automated>
      # 1. Verify file was created with required structure
      grep -c "registerPlugin" app/static/js/competence.js
      grep -c "id.*competence" app/static/js/competence.js
      grep -c "order.*45" app/static/js/competence.js
      grep -c "svgIcon.*icons.chart" app/static/js/competence.js
      grep -c "_render" app/static/js/competence.js | grep -v "^#"

      # 2. Verify imports
      grep -c "import.*from.*core.js" app/static/js/competence.js

      # 3. Syntax check (browser DevTools or Node --check)
      # Since no Node.js in project, manual browser load test:
      # Open browser DevTools → verify no "competence.js" errors in console
    </automated>
    <human-check>
      Open browser DevTools Console. Verify no red errors referencing
      `competence.js` or `registerPlugin`. The plugin should not appear
      in the sidebar yet (app.js import not wired until Wave 5).
    </human-check>
  </verify>

  <done>
    1. `app/static/js/competence.js` exists with `registerPlugin({...})` call
    2. Plugin object has: id="competence", name="Competence Matrix", order=45, svgIcon=icons.chart
    3. `init(container)` and `destroy()` methods defined
    4. Layout renders a header with "Bug Return Rate" title, a "Sync Now" button (stub),
       and a "Checking..." status placeholder
    5. No console errors from the module (syntax is valid ES module)
  </done>
</task>

<!-- ═══════════════════════════════════════════════════════════════
     WAVE 3: Chart rendering — iframe srcdoc from server HTML
     Depends on: Wave 1 (chart endpoint exists), Wave 2 (competence.js layout exists)
     ═══════════════════════════════════════════════════════════════ -->

<task type="auto" wave="3">
  <name>Task 3: Add chart iframe rendering to competence.js</name>
  <files>
    <file>app/static/js/competence.js</file>
  </files>

  <action>
    Add the `_loadChart(container)` method and wire it into the `_render()` lifecycle.
    This task implements the proven `logs.js` `_chart()` pattern (lines 416-425) adapted
    for the competence plugin.

    <step order="1">
      Add `_loadChart(container)` method to the plugin object (after `_render`, before
      `destroy` or at the end of the plugin object — place it between `_render` and the
      closing `});`):

      ```js
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
          console.error("[Competence] Load chart failed:", e.message);
          container.innerHTML = `<p class="text-muted">Failed to load chart: ${e.message}</p>`;
        }
      },
      ```

      Key details:
      - `api()` from core.js auto-detects `text/html` content-type and returns the raw
        HTML string (verified: core.js line 76-84). No JSON parsing needed.
      - `api()` already toasts HTTP errors internally (core.js line 87), so the catch block
        only adds a visible error message in the DOM — no duplicate toast.
      - `height: "460px"` accommodates the Plotly figure height of 400px plus title/margins.
      - Iframe `srcdoc` provides CSS isolation — Plotly's CDN-loaded JS runs inside the
        iframe scope, not the main page.
      - `<div class="spinner">` uses the existing CSS spinner class (defined in style.css,
        used by logs.js and other plugins for loading states).
      - Error state renders inline text (not toast) — consistent with logs.js pattern.
    </step>

    <step order="2">
      Wire `_loadChart` into the layout. In the `_render(c)` method, after appending
      `chartArea` to `c`, add:

      ```js
      // Initial loads
      this._refreshStatus();
      this._loadChart(chartArea);
      ```

      But note: `_refreshStatus()` doesn't exist yet (it's added in Task 4). To keep
      this task self-contained and avoid calling undefined methods:
      - Add `this._loadChart(chartArea);` call at the end of `_render()`.
      - Add `this._refreshStatus();` as a stub that does nothing for now (Task 4 fills it):
        ```js
        _refreshStatus() {},  // placeholder — wired in Task 4
        ```
      - Place `_refreshStatus` as a no-op method near `_loadChart` in the plugin object.

      The final `_render()` method after this task should end with:
      ```js
      c.appendChild(chartArea);

      // Initial loads
      this._refreshStatus();  // placeholder — wired in Task 4
      this._loadChart(chartArea);
      ```
    </step>

    <step order="3">
      Remove the now-unnecessary `onclick` handler text on the Sync button (or wait for
      Task 4 to replace it). The button currently has the Task 2 stub:
      ```js
      onclick: () => toast("Sync not yet wired", "info"),
      ```
      This is fine — Task 4 will rewrite this line. No change needed in this task.
    </step>
  </action>

  <verify>
    <automated>
      # 1. Verify _loadChart method exists
      grep -c "_loadChart" app/static/js/competence.js

      # 2. Verify iframe srcdoc pattern
      grep -c "srcdoc" app/static/js/competence.js

      # 3. Verify chart API endpoint is called
      grep -c "competence/chart" app/static/js/competence.js

      # 4. Verify _loadChart is called from _render
      grep -A5 "_render" app/static/js/competence.js | grep "_loadChart"

      # 5. Start server, verify chart endpoint returns valid HTML
      curl -s http://localhost:8000/api/competence/chart | grep -c "plotly"
      # Should return >0 if data exists, or contain the "No data yet" message
    </automated>
  </verify>

  <done>
    1. `_loadChart(container)` method defined and wired into `_render()`
    2. On chart load: spinner appears → iframe replaces spinner with Plotly chart HTML
    3. On chart load error: DOM shows "Failed to load chart: ..." message
    4. Chart iframe has width="100%", height="460px", border="none"
    5. No duplicate toast on failure (api() already handles toast internally)
    6. The `_loadChart` method follows the exact `logs.js` `_chart()` pattern
  </done>
</task>

<!-- ═══════════════════════════════════════════════════════════════
     WAVE 4: Sync button + status display logic
     Depends on: Wave 2 (layout exists), Wave 3 (chart rendering works)
     ═══════════════════════════════════════════════════════════════ -->

<task type="auto" wave="4">
  <name>Task 4: Implement sync button handler and status display logic</name>
  <files>
    <file>app/static/js/competence.js</file>
  </files>

  <action>
    Add three methods to the plugin object and update the Sync button's onclick handler.
    This task follows the `release.js` long-running button pattern (lines 458-493).

    <step order="1">
      Replace the `_refreshStatus` stub with the real implementation:

      ```js
      async _refreshStatus() {
        try {
          const status = await api("/api/competence/sync/status");
          this._updateStatus(status);
        } catch (e) { /* ignore — status display is non-critical */ }
      },
      ```

      Errors are silently ignored — the status display is informational, and failing to
      fetch it should not disrupt the user experience.
    </step>

    <step order="2">
      Add the `_updateStatus(status)` helper:

      ```js
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
      ```

      Note: `new Date(status.last_sync)` handles ISO 8601 strings from the backend
      (`datetime.now(timezone.utc).isoformat()`). The `toLocaleString()` renders in
      the browser's local timezone — no timezone conversion needed.
    </step>

    <step order="3">
      Add the `_doSync()` method — the main sync button handler:

      ```js
      async _doSync() {
        const btn = document.getElementById("comp-sync-btn");
        if (!btn) return;
        const origHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Syncing...';
        try {
          const res = await api("/api/competence/sync", { method: "POST" });
          toast(res.message || "Sync started", "success");
          // Poll until sync completes
          await this._waitForSync();
          // Reload chart with fresh data
          const chartArea = document.getElementById("comp-chart");
          if (chartArea) this._loadChart(chartArea);
        } catch (e) {
          toast("Sync failed: " + e.message, "error");
        } finally {
          btn.disabled = false;
          btn.innerHTML = origHTML;
          this._refreshStatus();
        }
      },
      ```

      Key details:
      - `ev.currentTarget` is NOT used here because the button is referenced by ID
        (`comp-sync-btn`). The `_doSync` method is called from an onclick handler that
        passes no event — using `getElementById` is safer and avoids `this` binding issues.
      - `spinner-sm` is the inline button spinner CSS class (sibling to the full-area
        `spinner` class). Both are defined in `style.css`.
      - Button is disabled + text replaced during sync, restored in `finally`.
      - After sync completes: chart is reloaded via `_loadChart()` to show updated data.
      - After sync: status is refreshed via `_refreshStatus()`.
    </step>

    <step order="4">
      Add the `_waitForSync()` polling helper:

      ```js
      async _waitForSync() {
        for (let i = 0; i < 60; i++) {
          await new Promise(r => setTimeout(r, 2000));
          try {
            const status = await api("/api/competence/sync/status");
            this._updateStatus(status);
            if (!status.in_progress) return;
          } catch (e) { /* continue polling despite transient errors */ }
        }
      },
      ```

      Polls every 2 seconds for up to 120 seconds (60 iterations). The sync job's
      `in_progress` flag is set to "1" at start (competence.py line 248) and reset
      to "0" in the `finally` block (line 371). When `in_progress` becomes `false`,
      polling stops.
    </step>

    <step order="5">
      Update the Sync button's onclick handler. In `_render()`, find the button line:
      ```js
      onclick: () => toast("Sync not yet wired", "info"),
      ```
      Replace with:
      ```js
      onclick: async () => this._doSync(),
      ```
      This binds the real sync handler. The arrow function preserves `this` context
      (refers to the plugin object because `_render` is called with `this` bound to
      the plugin by `init` → `this._render(container)`).
    </step>
  </action>

  <verify>
    <automated>
      # 1. Verify all four methods exist
      grep -c "_doSync" app/static/js/competence.js
      grep -c "_waitForSync" app/static/js/competence.js
      grep -c "_refreshStatus" app/static/js/competence.js
      grep -c "_updateStatus" app/static/js/competence.js

      # 2. Verify sync POST endpoint is called
      grep -c "competence/sync.*POST" app/static/js/competence.js

      # 3. Verify status endpoint is called
      grep -c "competence/sync/status" app/static/js/competence.js

      # 4. Verify button onclick is wired to _doSync
      grep -c "_doSync" app/static/js/competence.js

      # 5. Check for polling loop pattern
      grep -c "setTimeout" app/static/js/competence.js
    </automated>
    <human-check>
      After app.js import is wired (Task 5), manually test:
      1. Navigate to Competence Matrix in sidebar
      2. Click "Sync Now" button — should show spinner and "Syncing..." text
      3. After sync completes: chart reloads, status shows "Last sync: ..."
      4. Verify button is disabled during sync (can't click twice)
    </human-check>
  </verify>

  <done>
    1. Sync button triggers `POST /api/competence/sync` with visual feedback (spinner + disabled)
    2. Status display polls `GET /api/competence/sync/status` every 2s during sync
    3. After sync completes: chart reloads automatically with new data
    4. Status shows "Syncing..." during sync, "Last sync: ..." after completion, "Not synced yet" initially
    5. Button is disabled during sync, re-enabled in `finally` (prevents double-clicks)
    6. On sync error: user sees toast with error message, button restores
  </done>
</task>

<!-- ═══════════════════════════════════════════════════════════════
     WAVE 5: Wire app.js import + end-to-end integration verification
     Depends on: Waves 1–4 (all artifacts exist)
     ═══════════════════════════════════════════════════════════════ -->

<task type="auto" wave="5">
  <name>Task 5: Wire competence.js import in app.js + integration verification</name>
  <files>
    <file>app/static/js/app.js</file>
  </files>

  <action>
    <step order="1">
      Add the side-effect import line in `app/static/js/app.js`.

      Current state (line 11):
      ```js
      import "./universal_tester_tool.js";
      ```

      Insert after line 11 (before the blank line and `document.addEventListener`):
      ```js
      import "./competence.js";
      ```

      The import MUST be added *before* `document.addEventListener("DOMContentLoaded", boot);`
      on line 13. The `boot()` function calls `renderNav()` which iterates the `plugins[]`
      array populated by `registerPlugin()`. All side-effect imports must execute before
      `DOMContentLoaded` fires.

      Final app.js should read:
      ```js
      import { boot } from "./core.js";
      import "./gps.js";
      import "./logs.js";
      import "./com.js";
      import "./jira.js";
      import "./release.js";
      import "./universal_tester_tool.js";
      import "./competence.js";

      document.addEventListener("DOMContentLoaded", boot);
      ```

      Conventions to follow:
      - One import per line (no multi-import)
      - `.js` extension included
      - Alphabetical-ish order (competence follows universal_tester_tool)
      - No trailing semicolons (match existing style)
    </step>

    <step order="2">
      Integration verification checklist. After the import is added, verify the complete
      integration by loading the application and checking:

      a. **Plugin appears in sidebar:** The sidebar nav should show "Competence Matrix"
         with the bar-chart icon, positioned at order=45 (likely between "Release Creator"
         at order=5 and later plugins, or second-to-last before Universal Tester Tool).

      b. **Chart loads on first visit:** Click "Competence Matrix" in sidebar →
         should show "Bug Return Rate" header, "Sync Now" button, "Checking..." status,
         and either "No data yet — click Sync Now..." message (if cache empty) OR a
         Plotly bar chart (if data exists from Phase 1 testing).

      c. **Sync button works:** Click "Sync Now" → button shows spinner, status changes
         to "Syncing...", then after sync completes chart reloads and status shows
         "Last sync: {timestamp}".

      d. **No console errors:** DevTools Console should be clean (no red errors from
         competence.js).

      e. **Other plugins unaffected:** Navigate to GPS, Logs, Release Creator, etc. —
         all should continue working normally (competence.js import is side-effect-only
         and does not modify shared state beyond `plugins[]` registration).
    </step>
  </action>

  <verify>
    <automated>
      # 1. Verify import line exists in app.js
      grep -n "competence.js" app/static/js/app.js

      # 2. Verify import is before DOMContentLoaded
      # Line number of competence import should be < line number of addEventListener
      grep -n "competence.js\|DOMContentLoaded" app/static/js/app.js

      # 3. Start server and verify plugin is registered (via API)
      curl -s http://localhost:8000/api/plugins | grep -c "competence"
      # Should return 1 (plugin auto-discovered by backend)
    </automated>
    <human-check>
      Full UAT checklist (perform in browser):
      1. Open application → sidebar shows "Competence Matrix" with chart icon
      2. Click "Competence Matrix" → dashboard loads with header, button, status
      3. Click "Sync Now" → spinner, status updates, chart loads
      4. Navigate away → navigate back → plugin re-initializes cleanly
      5. Other plugins (GPS, Logs, Release) still work normally
    </human-check>
  </verify>

  <done>
    1. `app.js` includes `import "./competence.js";` before `DOMContentLoaded`
    2. Competence Matrix appears in sidebar navigation at order=45
    3. Full dashboard renders: header + Sync button + status + chart area
    4. Sync button, status display, and chart rendering all function end-to-end
    5. Zero console errors from competence module
    6. All existing plugins continue to work (no regression)
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Jira API → Backend | Auth credentials cross this boundary (handled by Phase 1) |
| Backend → Browser (chart) | Plotly HTML crosses this boundary via API response |
| Browser → iframe (srcdoc) | Chart HTML rendered in isolated iframe context |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-01 | Tampering | `GET /api/competence/chart` → iframe srcdoc | mitigate | Plotly HTML generated server-side by `fig.to_html()` which escapes data values. No user-controlled input in chart data. Iframe `srcdoc` is same-origin and cannot navigate to external URLs. |
| T-02-02 | Tampering | `POST /api/competence/sync` | mitigate | Sync is idempotent (duplicate transitions deduplicated in SQLite). `in_progress` flag prevents concurrent syncs at both backend (competence.py line 244) and frontend (button disabled during sync). |
| T-02-03 | Information Disclosure | Status display (`last_sync` timestamp) | accept | Timestamp is non-sensitive operational metadata. Single-user internal tool — no multi-tenant information leakage risk. |
| T-02-04 | Denial of Service | Polling loop (`_waitForSync`) | mitigate | Polling caps at 60 iterations (2 min), uses 2-second intervals. Backend `in_progress` flag prevents sync overlap. No unbounded loops. |
| T-02-05 | Spoofing | `api()` fetches to chart/sync endpoints | accept | All endpoints are read-only (GET) or idempotent (POST sync with guard). No sensitive operations without server-side validation. Single-user internal tool — no cross-user spoofing surface. |
| T-02-SC | Tampering | npm/pip/cargo installs | accept | Phase 2 installs zero new packages. All dependencies (plotly 6.6.0, pandas 2.1.1) are pre-existing, verified via `pip show` in Phase 1. No slopcheck audit required (0 new packages). |

## Security Assessment

**Risk level: LOW.** Phase 2 adds no new attack surface:
- No user input fields — only a "Sync Now" button
- No secrets in client-side code (Jira credentials stay server-side in `jira_config.json`)
- Chart HTML is server-generated (no user-controlled content in iframe)
- All API endpoints are read-only or idempotent
- Single-user internal tool — no multi-user threat model
</threat_model>

<verification>
## Automated Verification

```bash
# 1. Verify all files exist
Test-Path app/static/js/competence.js
grep -c "registerPlugin" app/static/js/competence.js
grep -c "competence/chart" app/plugins/competence.py
grep -c 'chart:' app/static/js/core.js
grep -c "competence.js" app/static/js/app.js

# 2. Verify server endpoint responds
curl -s http://localhost:8000/api/competence/chart | Select-Object -First 1
# Should return HTML (look for <div> or <script> tags, not JSON)

# 3. Verify plugin is auto-discovered
curl -s http://localhost:8000/api/plugins | grep -c "competence"
# Should return 1
```

## Manual UAT Checklist

1. **Sidebar presence:** Competence Matrix visible with chart icon, positioned around order=45
2. **First load:** Dashboard shows header, Sync button, "Checking..." status, chart area
3. **Empty state:** If no cached data, chart area shows "No data yet — click Sync Now..." message
4. **Sync flow:** Click "Sync Now" → button disables → status "Syncing..." → chart reloads → status "Last sync: ..."
5. **Chart rendering:** Bar chart displays with period labels on x-axis, return rate % on y-axis
6. **Navigation resilience:** Navigate to other plugin → return to Competence Matrix → re-initializes cleanly
7. **No regression:** All existing plugins (GPS, Logs, Release, etc.) function normally
</verification>

<success_criteria>
- [ ] `app/static/js/core.js` — `icons.chart` defined with bar-chart SVG
- [ ] `app/plugins/competence.py` — `GET /api/competence/chart` endpoint returns Plotly HTML
- [ ] `app/static/js/competence.js` — plugin registered with `registerPlugin({id:"competence", ...})`
- [ ] `app/static/js/app.js` — `import "./competence.js";` added before `DOMContentLoaded`
- [ ] Competence Matrix visible in sidebar nav with chart icon
- [ ] Chart renders with period labels on x-axis, return rate on y-axis
- [ ] Sync button triggers background sync with visual feedback (spinner, disabled state)
- [ ] Status displays last sync time after sync completes
- [ ] Layout matches existing plugin design conventions (header, spacing, consistent styling)
- [ ] Zero console errors from competence module
- [ ] All existing plugins continue to work (no regression)
</success_criteria>

<output>
Create `.planning/phase-2/02-01-SUMMARY.md` when all tasks complete.
</output>
