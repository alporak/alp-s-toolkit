/* ================================================================
   Log Parser Plugin
   ================================================================ */
import { h, $, $$, api, toast, registerPlugin, createTabs, createTable, icons, makeColumnsResizable } from "./core.js";

registerPlugin({
  id: "logs", name: "Log Parser", order: 2,
  svgIcon: icons.file,
  _curId: null,
  _sidebarCollapsed: false,
  _headerCollapsed: false,
  _recCols: null,   // { ios: { "239": true, ... } }
  _recData: null,    // cached records for current analysis
  _recAid: null,     // id for cached records
  _recContainer: null,
  _recTableArea: null,
  _recIoPills: null,

  /* ── Record column prefs (localStorage) ─────────────── */
  _loadRecCols() {
    if (this._recCols) return this._recCols;
    try {
      const raw = localStorage.getItem("logs_rec_cols");
      if (raw) { this._recCols = JSON.parse(raw); return this._recCols; }
    } catch {}
    this._recCols = { ios: {} };
    return this._recCols;
  },
  _saveRecCols() {
    try { localStorage.setItem("logs_rec_cols", JSON.stringify(this._recCols)); } catch {}
  },

  init(container) {
    container.style.display = "flex";
    container.style.gap = "0";
    container.style.height = "100%";

    const sidebar = h("div", { className: "log-sidebar", id: "log-sidebar" });
    const viewer = h("div", { className: "log-main", id: "log-viewer" });

    // Sidebar toggle (lives outside sidebar so it's visible when collapsed)
    const sidebarToggle = h("button", {
      className: "btn btn-sm log-sidebar-toggle", id: "log-sidebar-toggle",
      title: "Toggle sidebar",
      style: "position:absolute;top:4px;left:4px;z-index:10;font-size:14px;padding:2px 6px;line-height:1;display:none",
      onclick: () => this._toggleSidebar(),
    }, "\u2630");

    sidebar.appendChild(h("div", { className: "log-sidebar-header", style: "display:flex;justify-content:space-between;align-items:center" },
      h("h3", { style: "margin:0;flex:1" }, "Analyses"),
      h("div", { style: "display:flex;gap:2px" },
        h("button", {
          className: "btn btn-sm", title: "Settings",
          style: "font-size:14px;padding:2px 6px;line-height:1",
          onclick: () => {
            const p = document.getElementById("log-settings-panel");
            if (p) {
              const vis = p.style.display !== "none";
              p.style.display = vis ? "none" : "block";
              if (!vis) this._renderSettings(p);
            }
          },
        }, "\u2699"),
        h("button", {
          className: "btn btn-sm", title: "Collapse sidebar",
          style: "font-size:14px;padding:2px 6px;line-height:1",
          onclick: () => this._toggleSidebar(),
        }, "\u276E"),
      ),
    ));

    sidebar.appendChild(h("div", { id: "log-settings-panel", style: "display:none;padding:0.5em;border-bottom:1px solid var(--color-border,#333)" }));

    const uploadZone = h("div", { className: "upload-zone", id: "log-upload" },
      h("span", { className: "upload-icon", html: icons.upload }),
      h("p", null, "Drop .dmp / .zip / .txt / .clg files here"),
      h("input", { type: "file", multiple: true, accept: ".dmp,.clg,.txt,.log,.zip", onchange: e => this._upload(e.target.files) }),
    );
    uploadZone.onclick = () => $("input", uploadZone).click();
    uploadZone.ondragover = e => { e.preventDefault(); uploadZone.classList.add("dragover"); };
    uploadZone.ondragleave = () => uploadZone.classList.remove("dragover");
    uploadZone.ondrop = e => { e.preventDefault(); uploadZone.classList.remove("dragover"); this._upload(e.dataTransfer.files); };
    sidebar.appendChild(uploadZone);

    sidebar.appendChild(h("div", { id: "log-list", className: "log-list" }));

    container.append(sidebarToggle, sidebar, viewer);
    viewer.appendChild(h("div", { className: "empty" },
      h("div", { className: "empty-icon", html: icons.file }),
      h("p", null, "Upload or select an analysis")));
    this._renderSidebar(sidebar);
  },

  destroy() { },

  /* ── Sidebar collapse ────────────────────────────────── */
  _toggleSidebar() {
    this._sidebarCollapsed = !this._sidebarCollapsed;
    const sb = document.getElementById("log-sidebar");
    const btn = document.getElementById("log-sidebar-toggle");
    if (sb) sb.style.display = this._sidebarCollapsed ? "none" : "";
    if (btn) btn.style.display = this._sidebarCollapsed ? "block" : "none";
  },

  /* ── Sidebar ──────────────────────────────────────────── */
  async _renderSidebar(c) {
    const list = $("#log-list", c) || c;
    list.innerHTML = '<div class="spinner"></div>';
    try {
      const analyses = await api("/api/logs/analyses");
      list.innerHTML = "";
      for (const a of analyses) {
        const nameEl = h("div", { className: "log-item-name" }, a.name || a.id);
        const item = h("div", {
          className: "log-item" + (a.id === this._curId ? " active" : ""),
          onclick: () => this._load(a.id),
        },
          nameEl,
          h("div", { className: "log-item-meta text-muted" },
            `${a.source_files?.length || a.file_count || 0} files`),
          h("div", { className: "log-item-actions", style: "display:flex;gap:2px" },
            h("button", { className: "log-item-btn", title: "Rename", onclick: (e) => {
              e.stopPropagation();
              this._renameAnalysis(a.id, a.name || a.id);
            }}, "\u270E"),
            h("button", { className: "log-item-del", onclick: async (e) => {
              e.stopPropagation();
              if (!confirm("Delete?")) return;
              await api(`/api/logs/analysis/${a.id}`, { method: "DELETE" });
              toast("Deleted", "success");
              this._renderSidebar(c);
            }}, h("span", { html: icons.x })),
          ),
        );
        list.appendChild(item);
      }
    } catch (e) { console.error("[Logs] Load sidebar failed:", e.message); }
  },

  /* ── Rename ───────────────────────────────────────────── */
  async _renameAnalysis(aid, currentName) {
    const newName = prompt("Rename analysis:", currentName);
    if (!newName || newName === currentName) return;
    try {
      const fd = new FormData();
      fd.append("new_name", newName);
      await api(`/api/logs/analysis/${aid}/rename`, { method: "PUT", body: fd });
      toast("Renamed", "success");
      this._renderSidebar(document.getElementById("log-sidebar"));
      if (aid === this._curId) this._load(aid);
    } catch (e) { toast("Rename failed: " + e.message, "error"); }
  },

  /* ── Settings ─────────────────────────────────────────── */
  async _renderSettings(c) {
    c.innerHTML = '<div class="spinner" style="margin:8px auto"></div>';
    try {
      const s = await api("/api/logs/settings");
      c.innerHTML = "";
      const fields = [
        { key: "db_path", label: "Release Vault (DB path)" },
        { key: "tickets_folder", label: "Tickets folder" },
        { key: "catcher_path", label: "Catcher.exe path" },
        { key: "clg2txt_path", label: "Clg2Txt.exe path" },
      ];
      const inputs = {};
      for (const f of fields) {
        const input = h("input", {
          className: "form-control",
          value: s[f.key] || "",
          style: "font-size:11px;padding:3px 6px",
        });
        inputs[f.key] = input;
        c.appendChild(h("div", { style: "margin-bottom:6px" },
          h("label", { style: "font-size:10px;display:block;margin-bottom:1px;text-transform:uppercase;opacity:0.6" }, f.label),
          input,
        ));
      }

      const statusColor = s.easy_catcher_ok ? "var(--color-success,#4caf50)" : "var(--color-danger,#f44336)";
      const statusText = s.easy_catcher_ok ? "\u2713 Easy Catcher available" : "\u2717 Easy Catcher: " + (s.easy_catcher_error || "unavailable");
      c.appendChild(h("div", {
        style: `font-size:11px;margin-bottom:8px;color:${statusColor}`,
      }, statusText));

      c.appendChild(h("button", {
        className: "btn btn-sm btn-primary",
        style: "width:100%",
        onclick: async () => {
          const fd = new FormData();
          for (const [k, inp] of Object.entries(inputs)) fd.append(k, inp.value);
          try {
            await api("/api/logs/settings", { method: "PUT", body: fd });
            toast("Settings saved", "success");
          } catch (e) { toast("Save failed: " + e.message, "error"); }
        },
      }, "Save Settings"));
    } catch (e) {
      c.innerHTML = '<p style="font-size:11px;color:var(--color-danger)">Failed to load settings</p>';
    }
  },

  /* ── Upload ───────────────────────────────────────────── */
  async _upload(files) {
    if (!files?.length) return;
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    const viewer = document.getElementById("log-viewer");
    viewer.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Uploading\u2026</p></div>';
    try {
      const r = await api("/api/logs/parse", { method: "POST", body: fd });
      if (r.job_id && r.status === "processing") {
        this._pollJob(r.job_id, viewer);
        return;
      }
      this._onParseComplete(r, viewer);
    } catch (e) {
      console.error("[Logs] Parse failed:", e.message);
      viewer.innerHTML = '<div class="empty"><p>Parse failed: ' + e.message + '</p></div>';
    }
  },

  /* ── Job polling ─────────────────────────────────────── */
  async _pollJob(jobId, viewer) {
    const logBox = h("div", { className: "loading-state" },
      h("div", { className: "spinner" }),
      h("p", null, "Processing DMP files via Easy Catcher\u2026"),
      h("pre", { id: "job-log", style: {
        textAlign: "left", maxHeight: "300px", overflow: "auto",
        fontSize: "0.8em", whiteSpace: "pre-wrap", width: "100%", padding: "1em",
        background: "var(--color-bg-secondary, #1e1e1e)", borderRadius: "8px",
      }}, "Starting\u2026"),
    );
    viewer.innerHTML = "";
    viewer.appendChild(logBox);

    const logEl = $("#job-log", viewer);
    const poll = async () => {
      try {
        const s = await api(`/api/logs/parse/status/${jobId}`);
        if (logEl) logEl.textContent = (s.logs || []).join("\n") || "Working\u2026";

        if (s.status === "done" && s.result) {
          this._onParseComplete(s.result, viewer);
          return;
        }
        if (s.status === "error") {
          viewer.innerHTML = '<div class="empty"><p>Processing failed</p><pre>' +
            (s.logs || []).join("\n") + '</pre></div>';
          return;
        }
        setTimeout(poll, 1500);
      } catch (e) {
        console.error("[Logs] Poll failed:", e.message);
        setTimeout(poll, 3000);
      }
    };
    poll();
  },

  /* ── Handle parse complete ──────────────────────────────── */
  _onParseComplete(r, viewer) {
    const parts = [`Parsed ${r.file_count || 0} files`];
    if (r.record_count) parts.push(`${r.record_count} data points`);
    if (r.events_count) parts.push(`${r.events_count} events`);
    if (r.log_lines) parts.push(`${r.log_lines} log lines`);
    if (r.auto_saved?.length) parts.push("auto-saved to ticket folder");
    toast(parts.join(" \u2022 "), "success");
    this._curId = r.id;
    this._renderSidebar(document.getElementById("log-sidebar"));
    this._show(r, viewer);
  },

  async _load(id) {
    this._curId = id;
    this._renderSidebar(document.getElementById("log-sidebar"));
    const viewer = document.getElementById("log-viewer");
    viewer.innerHTML = '<div class="loading-state"><div class="spinner"></div></div>';
    try { this._show(await api(`/api/logs/analysis/${id}`), viewer); }
    catch (e) { console.error("[Logs] Load analysis failed:", e.message); viewer.innerHTML = '<div class="empty"><p>Failed to load</p></div>'; }
  },

  /* ── Analysis view ────────────────────────────────────── */
  _show(data, c) {
    c.innerHTML = "";
    const aid = data.id;

    // Collapsible header
    const headerContent = h("div", { id: "log-header-content" });
    const headerToggle = h("button", {
      className: "btn btn-sm",
      style: "font-size:11px;padding:1px 6px;line-height:1;margin-right:6px",
      title: "Toggle header",
      onclick: () => {
        this._headerCollapsed = !this._headerCollapsed;
        headerContent.style.display = this._headerCollapsed ? "none" : "";
        headerToggle.textContent = this._headerCollapsed ? "\u25B6" : "\u25BC";
      },
    }, "\u25BC");

    // Title + stats line (always visible even when collapsed)
    const titleRow = h("div", {
      style: "display:flex;align-items:center;gap:6px;flex:1;min-width:0",
    },
      headerToggle,
      h("h2", {
        style: "cursor:pointer;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis",
        title: "Click to rename",
        onclick: () => this._renameAnalysis(aid, data.name || aid),
      }, data.name || aid),
    );

    const stats = [];
    if (data.file_count) stats.push(`${data.file_count} files`);
    if (data.record_count) stats.push(`${data.record_count} data pts`);
    if (data.events_count) stats.push(`${data.events_count} events`);
    if (data.records) stats.push(`${data.records} records`);
    if (data.log_lines) stats.push(`${data.log_lines} logs`);
    if (data.at_commands) stats.push(`${data.at_commands} AT cmds`);
    if (data.signal_readings) stats.push(`${data.signal_readings} signal`);

    // Buttons row (always visible)
    const btnRow = h("div", { style: "display:flex;gap:4px;flex-shrink:0" });

    if (data.artifacts?.length && data.artifacts.some(a => a.endsWith(".clg"))) {
      btnRow.appendChild(h("button", {
        className: "btn btn-sm btn-primary",
        onclick: async () => {
          try {
            const r = await api(`/api/logs/launch_catcher/${aid}`, { method: "POST" });
            toast(`Launched Catcher: ${r.clg}`, "success");
          } catch (e) { toast("Launch failed: " + e.message, "error"); }
        },
      }, "\u25B6 Catcher"));
    }

    btnRow.appendChild(h("button", {
      className: "btn btn-sm",
      onclick: () => { window.open(`/api/logs/analysis/${aid}/download`, '_blank'); },
    }, "\u2B07 TXT"));

    btnRow.appendChild(h("button", {
      className: "btn btn-sm",
      title: "Open analysis folder",
      onclick: async () => {
        try {
          await api(`/api/logs/analysis/${aid}/open_folder`, { method: "POST" });
          toast("Opened folder", "success");
        } catch (e) { toast("Open failed: " + e.message, "error"); }
      },
    }, "\uD83D\uDCC2"));

    const topRow = h("div", {
      className: "analysis-header",
      style: "display:flex;align-items:center;gap:6px;padding:4px 8px",
    }, titleRow, btnRow);
    c.appendChild(topRow);

    // Collapsible content: stats, identity, auto-saved
    if (stats.length) headerContent.appendChild(h("div", {
      className: "text-muted", style: "font-size:12px;padding:0 8px",
    }, stats.join(" \u2022 ")));

    const ident = data.device_identity;
    if (ident && Object.keys(ident).length) {
      const parts = [];
      if (ident.IMEI) parts.push(`IMEI: ${ident.IMEI}`);
      if (ident.Model) parts.push(ident.Model);
      if (ident.FW) parts.push(`FW: ${ident.FW}`);
      if (parts.length) {
        headerContent.appendChild(h("div", { className: "text-muted", style: "font-size:12px;padding:0 8px" },
          parts.join(" \u2022 ")));
      }
    }

    if (data.auto_saved?.length) {
      headerContent.appendChild(h("div", {
        className: "text-muted",
        style: "font-size:11px;padding:0 8px;color:var(--color-success, #4caf50)",
      }, `\u2713 Auto-saved to ticket folder (${data.auto_saved.length} files)`));
    }

    headerContent.style.display = this._headerCollapsed ? "none" : "";
    c.appendChild(headerContent);

    createTabs(c, [
      { id: "ev",  label: "Events",      render: v => this._tbl(v, aid, "events",
        [{ key: "Timestamp", label: "Time" }, { key: "Type", label: "Type" },
         { key: "Value", label: "Value" }, { key: "Details", label: "Details" }]) },
      { id: "at",  label: "AT Commands",  render: v => this._tbl(v, aid, "at_commands",
        [{ key: "Timestamp", label: "Time" }, { key: "Command", label: "Command" },
         { key: "Response", label: "Response" }, { key: "Category", label: "Category" }]) },
      { id: "rec", label: "Records",      render: v => this._renderRecords(v, aid) },
      { id: "tl",  label: "Timeline",     render: v => this._chart(v, aid, "timeline") },
      { id: "sig", label: "Signal",       render: v => this._chart(v, aid, "signal_chart") },
      { id: "st",  label: "State",        render: v => this._chart(v, aid, "state_timeline") },
      { id: "map", label: "Map",          render: v => this._chart(v, aid, "map") },
      { id: "lg",  label: "Logs",         render: v => this._logview(v, aid) },
      { id: "dp",  label: "Data Points",  render: v => this._dataPoints(v, aid) },
      { id: "af",  label: "Artifacts",    render: v => this._artifacts(v, aid) },
    ]);
  },

  async _tbl(c, aid, endpoint, cols) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const data = await api(`/api/logs/analysis/${aid}/${endpoint}`);
      c.innerHTML = "";
      if (!data?.length) { c.appendChild(h("div", { className: "empty" }, h("p", null, "No data"))); return; }
      createTable(c, cols, data, { maxRows: 2000 });
      const tbl = c.querySelector("table");
      if (tbl) makeColumnsResizable(tbl, `logs_${endpoint}_col_widths`);
    } catch (e) { console.error(`[Logs] Load ${endpoint} failed:`, e.message); c.innerHTML = "<p>Failed to load</p>"; }
  },

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

  /* ── Records view (like GPS Server with IO pinning) ───── */
  async _renderRecords(c, aid) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const recs = await api(`/api/logs/analysis/${aid}/records`);
      this._recData = recs;
      this._recAid = aid;
      this._recContainer = c;
      c.innerHTML = "";

      if (!recs?.length) {
        c.appendChild(h("div", { className: "empty" },
          h("div", { className: "empty-icon" }, "\u2014"),
          h("p", null, "No record generation blocks found in these logs.")));
        return;
      }

      // Toolbar
      const toolbar = h("div", { className: "btn-group", style: "margin-bottom:6px;flex-wrap:wrap" },
        h("button", { className: "btn", onclick: () => this._showLogIoPicker() },
          "Pin IOs"),
      );
      c.appendChild(toolbar);

      // IO pills bar
      this._recIoPills = h("div", { style: "display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px" });
      c.appendChild(this._recIoPills);
      this._renderLogIoPills();

      // Table area
      this._recTableArea = h("div");
      c.appendChild(this._recTableArea);
      this._rebuildLogRecordsTable();
    } catch (e) {
      console.error("[Logs] Load records failed:", e.message);
      c.innerHTML = "<p>Failed to load records</p>";
    }
  },

  /** Rebuild records table from cached _recData using current IO pins */
  _rebuildLogRecordsTable() {
    const area = this._recTableArea;
    const recs = this._recData;
    if (!area || !recs) return;
    area.innerHTML = "";

    const cols = this._loadRecCols();
    const pinnedIos = Object.entries(cols.ios)
      .filter(([, v]) => v)
      .map(([id]) => id)
      .sort((a, b) => parseInt(a) - parseInt(b));

    // Header
    const baseCols = ["Time", "Type", "Prio", "Lat", "Lng", "Speed", "Sats", "Fix", "AVL ID", "IOs", "Size"];
    const headerCells = baseCols.map(c => h("th", null, c));
    for (const ioId of pinnedIos) {
      headerCells.push(h("th", {
        style: "color:var(--tk-blue);font-size:10px;max-width:100px;overflow:hidden;text-overflow:ellipsis",
        title: `IO ${ioId}`,
      }, `[${ioId}]`));
    }
    headerCells.push(h("th", { style: "width:40px" }, ""));

    const tblWrap = h("div", { className: "table-wrap", style: "max-height:calc(100vh - 290px)" });
    const tbl = h("table");
    tbl.appendChild(h("thead", null, h("tr", null, ...headerCells)));

    const tbody = h("tbody");
    for (const r of recs) {
      const ios = r.IOs || {};
      const ioCount = Object.keys(ios).length;
      const fixStr = r.GPSFix === 1 ? "\u2713" : r.GPSFix === 0 ? "\u2717" : "\u2014";
      const fixColor = r.GPSFix === 1 ? "var(--color-success, #4caf50)" : r.GPSFix === 0 ? "var(--color-danger, #f44336)" : "";

      const cells = [
        h("td", null, r.Timestamp || "\u2014"),
        h("td", null, r.RecType || "\u2014"),
        h("td", null, r.RecPriority != null ? String(r.RecPriority) : "\u2014"),
        h("td", { style: "font-family:var(--font-mono);font-size:11px" },
          r.Latitude != null ? Number(r.Latitude).toFixed(6) : "\u2014"),
        h("td", { style: "font-family:var(--font-mono);font-size:11px" },
          r.Longitude != null ? Number(r.Longitude).toFixed(6) : "\u2014"),
        h("td", null, r.Speed != null ? String(r.Speed) : "\u2014"),
        h("td", null, r.SatInUse != null ? String(r.SatInUse) : "\u2014"),
        h("td", { style: fixColor ? `color:${fixColor};font-weight:bold` : "" }, fixStr),
        h("td", { style: "font-family:var(--font-mono);font-size:11px" },
          r.EventAVLID != null ? String(r.EventAVLID) : "\u2014"),
        h("td", null, h("span", { className: "badge badge-primary" }, String(ioCount))),
        h("td", { style: "font-family:var(--font-mono);font-size:11px" },
          r.RecordSize != null ? `${r.RecordSize}B` : "\u2014"),
      ];

      // Pinned IO values
      for (const ioId of pinnedIos) {
        const v = ios[ioId] ?? ios[parseInt(ioId)] ?? ios[String(ioId)] ?? "\u2014";
        const dv = typeof v === "string" && v.length > 16 ? v.substring(0, 16) + "\u2026" : String(v);
        cells.push(h("td", {
          style: "font-family:var(--font-mono);font-size:11px;color:var(--tk-blue)",
          title: `IO ${ioId} = ${v}`,
        }, dv));
      }

      cells.push(h("td", null, h("button", {
        className: "btn btn-sm",
        onclick: (e) => { e.stopPropagation(); this._showRecordDetail(r); },
      }, "\u2026")));

      tbody.appendChild(h("tr", {
        style: "cursor:pointer",
        onclick: () => this._showRecordDetail(r),
      }, ...cells));
    }

    tbl.appendChild(tbody);
    tblWrap.appendChild(tbl);

    area.appendChild(h("div", { className: "text-muted", style: "margin-bottom:6px;font-size:12px" },
      `${recs.length} records \u2022 ${pinnedIos.length} pinned IOs`));
    area.appendChild(tblWrap);
    makeColumnsResizable(tbl, "logs_rec_col_widths");
  },

  /** IO pills above records table */
  _renderLogIoPills() {
    const el = this._recIoPills;
    if (!el) return;
    el.innerHTML = "";
    const cols = this._loadRecCols();
    const pinned = Object.entries(cols.ios).filter(([, v]) => v);
    if (!pinned.length) {
      el.appendChild(h("span", { className: "text-muted", style: "font-size:11px" },
        'No pinned IOs \u2014 click "Pin IOs" to add IO columns'));
      return;
    }
    for (const [id] of pinned.sort((a, b) => parseInt(a[0]) - parseInt(b[0]))) {
      el.appendChild(h("span", {
        className: "badge badge-blue",
        style: "cursor:pointer;padding:3px 8px;display:inline-flex;align-items:center;gap:4px",
        title: `Unpin IO ${id}`,
        onclick: () => {
          cols.ios[id] = false;
          this._saveRecCols();
          this._renderLogIoPills();
          this._rebuildLogRecordsTable();
        },
      },
        `[${id}]`,
        h("span", { style: "font-size:9px;opacity:0.7" }, "\u2715"),
      ));
    }
  },

  /** IO picker modal for records */
  _showLogIoPicker() {
    const cols = this._loadRecCols();
    const modal = h("div", { className: "modal-overlay", onclick: e => { if (e.target === modal) modal.remove(); } });
    const content = h("div", { className: "modal-content", style: "max-width:600px" });
    content.appendChild(h("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px" },
      h("h3", { style: "margin:0" }, "Pin IO Columns"),
      h("button", { className: "btn btn-sm", onclick: () => modal.remove() }, "\u2715"),
    ));

    // Quick add by ID
    const quickRow = h("div", { style: "display:flex;gap:6px;margin-bottom:12px" });
    const quickInput = h("input", {
      className: "form-control", type: "text",
      placeholder: "Add IO by ID (e.g. 239, 240, 21)...", style: "flex:1",
    });
    quickRow.appendChild(quickInput);
    quickRow.appendChild(h("button", { className: "btn btn-primary", onclick: () => {
      const ids = quickInput.value.split(/[,\s]+/).map(s => s.trim()).filter(Boolean);
      for (const id of ids) { if (/^\d+$/.test(id)) cols.ios[id] = true; }
      this._saveRecCols();
      quickInput.value = "";
      renderList();
    }}, "Add"));
    content.appendChild(quickRow);

    const searchInput = h("input", {
      className: "form-control", placeholder: "Filter IOs by ID...",
      style: "width:100%;margin-bottom:8px",
      oninput: () => renderList(searchInput.value),
    });
    content.appendChild(searchInput);

    const listEl = h("div", { style: "max-height:400px;overflow-y:auto" });
    content.appendChild(listEl);

    // Count IOs from data
    const ioFreq = {};
    for (const r of (this._recData || [])) {
      for (const k of Object.keys(r.IOs || {})) {
        ioFreq[k] = (ioFreq[k] || 0) + 1;
      }
    }
    const allIoIds = new Set([...Object.keys(ioFreq), ...Object.keys(cols.ios).filter(k => cols.ios[k])]);
    const sorted = [...allIoIds].sort((a, b) => parseInt(a) - parseInt(b));

    const renderList = (filter = "") => {
      listEl.innerHTML = "";
      const f = filter.toLowerCase();
      let items = sorted.filter(id => !f || id.includes(f));
      items.sort((a, b) => {
        const pa = cols.ios[a] ? 1 : 0, pb = cols.ios[b] ? 1 : 0;
        if (pa !== pb) return pb - pa;
        const fa = ioFreq[a] || 0, fb = ioFreq[b] || 0;
        if (fa !== fb) return fb - fa;
        return parseInt(a) - parseInt(b);
      });
      for (const id of items) {
        const pinned = !!cols.ios[id];
        const freq = ioFreq[id] || 0;
        const row = h("label", {
          style: "display:flex;align-items:center;gap:8px;padding:5px 8px;cursor:pointer;border-radius:4px;font-size:12px;" +
            (pinned ? "background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.3)" :
                      "background:rgba(0,0,0,0.12);border:1px solid transparent") +
            ";margin-bottom:3px",
        },
          h("input", { type: "checkbox", checked: pinned ? "checked" : undefined, onchange: (e) => {
            cols.ios[id] = e.target.checked;
            this._saveRecCols();
            renderList(searchInput.value);
          }}),
          h("span", { style: "font-family:var(--font-mono);min-width:40px;color:var(--tk-fg-dim)" }, `[${id}]`),
          freq > 0
            ? h("span", { className: "badge badge-green", style: "font-size:10px" }, `${freq}x`)
            : h("span", { className: "text-muted", style: "font-size:10px" }, "no data"),
        );
        listEl.appendChild(row);
      }
      if (!items.length) listEl.appendChild(h("span", { className: "text-muted" }, "No matching IOs"));
    };
    renderList();

    // Common IOs quick buttons
    const commonIos = [
      ["Ign", "239"], ["Mvt", "240"], ["GSM", "21"], ["GNSS", "69"],
      ["ExtV", "66"], ["BatV", "67"], ["Odo", "16"], ["Spd", "24"],
    ];
    content.appendChild(h("div", { style: "display:flex;flex-wrap:wrap;gap:4px;margin-top:10px" },
      h("span", { className: "text-muted", style: "font-size:11px;line-height:24px" }, "Quick:"),
      ...commonIos.map(([label, id]) =>
        h("button", {
          className: "btn btn-sm", style: "font-size:11px;padding:2px 8px",
          onclick: () => { cols.ios[id] = !cols.ios[id]; this._saveRecCols(); renderList(searchInput.value); },
        }, `${label} [${id}]`)),
    ));

    // Apply button
    content.appendChild(h("div", { style: "margin-top:12px;text-align:right" },
      h("button", {
        className: "btn btn-primary",
        onclick: () => {
          modal.remove();
          this._renderLogIoPills();
          this._rebuildLogRecordsTable();
        },
      }, "Apply"),
    ));

    modal.appendChild(content);
    document.body.appendChild(modal);
  },

  /* ── Record detail modal ──────────────────────────────── */
  _showRecordDetail(r) {
    const modal = h("div", { className: "modal-overlay", onclick: (e) => {
      if (e.target === modal) modal.remove();
    }});
    const content = h("div", { className: "modal-content", style: "max-width:800px" });

    content.appendChild(h("div", {
      style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:14px",
    },
      h("h3", { style: "margin:0" }, `Record: ${r.Timestamp || "Unknown"}`),
      h("button", { className: "btn btn-sm", onclick: () => modal.remove() }, "\u2715"),
    ));

    // GPS section
    const gpsFields = [
      ["Type", r.RecType], ["Priority", r.RecPriority],
      ["Latitude", r.Latitude], ["Longitude", r.Longitude],
      ["Altitude", r.Altitude], ["Angle", r.Angle],
      ["Speed", r.Speed], ["GSpeed", r.GSpeed],
      ["GSpeed Src", r.GSpeedSrc], ["HDOP", r.HDOP],
      ["Satellites", r.SatInUse], ["GPS Fix", r.GPSFix === 1 ? "Yes" : r.GPSFix === 0 ? "No" : "\u2014"],
      ["Event AVL ID", r.EventAVLID], ["Record Size", r.RecordSize ? `${r.RecordSize} bytes` : null],
      ["Rec Timestamp", r.RecTimestamp ? new Date(r.RecTimestamp * 1000).toISOString() : null],
    ].filter(([, v]) => v != null);

    const gpsGrid = h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px;margin-bottom:16px" });
    for (const [label, val] of gpsFields) {
      gpsGrid.appendChild(h("div", {
        style: "background:rgba(0,0,0,0.15);padding:6px 10px;border-radius:4px",
      },
        h("div", { className: "text-muted", style: "font-size:10px;text-transform:uppercase" }, label),
        h("div", { style: "font-family:var(--font-mono);font-size:13px" }, String(val)),
      ));
    }
    content.appendChild(h("h4", { style: "margin:0 0 8px" }, "GPS & Record Info"));
    content.appendChild(gpsGrid);

    // IOs section
    const ios = r.IOs || {};
    const ioKeys = Object.keys(ios).sort((a, b) => parseInt(a) - parseInt(b));
    if (ioKeys.length) {
      content.appendChild(h("h4", { style: "margin:16px 0 8px" }, `IO Elements (${ioKeys.length})`));
      const ioGrid = h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:4px" });
      for (const id of ioKeys) {
        const val = ios[id];
        const displayVal = typeof val === "string" && val.length > 30 ? val.substring(0, 30) + "\u2026" : String(val);
        ioGrid.appendChild(h("div", {
          style: "display:flex;gap:8px;align-items:center;padding:4px 8px;background:rgba(59,130,246,0.08);border-radius:4px;font-size:12px",
          title: `IO ${id} = ${val}`,
        },
          h("span", { style: "font-family:var(--font-mono);color:var(--tk-blue,#3b82f6);min-width:40px" }, `[${id}]`),
          h("span", { style: "font-family:var(--font-mono)" }, displayVal),
        ));
      }
      content.appendChild(ioGrid);

      // Pin all button
      content.appendChild(h("div", { style: "margin-top:8px" },
        h("button", {
          className: "btn btn-sm",
          onclick: () => {
            const cols = this._loadRecCols();
            for (const id of ioKeys) cols.ios[id] = true;
            this._saveRecCols();
            toast(`Pinned ${ioKeys.length} IOs`, "success");
          },
        }, `Pin all ${ioKeys.length} IOs from this record`),
      ));
    }

    modal.appendChild(content);
    document.body.appendChild(modal);
  },

  /* ── Logs view ────────────────────────────────────────── */
  async _logview(c, aid) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const logs = await api(`/api/logs/analysis/${aid}/logs`);
      c.innerHTML = "";

      if (!logs?.length) {
        c.appendChild(h("div", { className: "empty" }, h("p", null, "No structured logs found")));
        return;
      }

      // Search bar
      const searchRow = h("div", { style: "display:flex;gap:8px;margin-bottom:8px;align-items:center" });
      const searchInput = h("input", {
        className: "form-control", placeholder: "Filter logs...",
        style: "flex:1;max-width:400px",
      });
      const countEl = h("span", { className: "text-muted", style: "font-size:12px" },
        `${logs.length} lines`);
      searchRow.append(searchInput, countEl);
      c.appendChild(searchRow);

      const ld = h("div", { className: "log-container", style: "max-height:calc(100vh - 300px);overflow:auto" });
      let allEntries = [];

      const cleanStr = (s) => {
        if (!s) return "";
        return s.replace(/[^\x20-\x7E\t\n\r\u00A0-\uFFFF]/g, "");
      };

      const renderLogs = (entries) => {
        ld.innerHTML = "";
        for (const e of entries) {
          const lvl = (e.Level || "").toLowerCase();
          const badge = lvl.includes("err") ? "danger" : lvl.includes("warn") ? "warning" : "primary";
          const timeStr = cleanStr(e.Time || "");
          const modStr = cleanStr(e.Module || "");
          const typeStr = cleanStr(e.Type || "");
          const msgStr = cleanStr(e.Message || "");

          const lineEl = h("div", { className: "log-line", style: "display:flex;gap:0.4em;align-items:flex-start;font-size:12px;padding:1px 0;font-family:var(--font-mono, monospace)" });

          if (e.Line) lineEl.appendChild(h("span", {
            className: "text-muted", style: "min-width:3em;text-align:right;opacity:0.4;user-select:none",
          }, String(e.Line)));

          if (timeStr) lineEl.appendChild(h("span", {
            className: "text-muted", style: "min-width:9em",
          }, timeStr));

          if (e.Level || typeStr) {
            const labelText = e.Level || typeStr;
            lineEl.appendChild(h("span", {
              className: `badge badge-${badge}`, style: "font-size:10px;min-width:2em;text-align:center",
            }, cleanStr(labelText)));
          }

          if (modStr) lineEl.appendChild(h("span", {
            style: "color:var(--tk-blue,#3b82f6);min-width:8em;font-size:11px",
          }, modStr));

          lineEl.appendChild(h("span", { style: "flex:1;word-break:break-all" }, msgStr));
          ld.appendChild(lineEl);
        }
      };

      renderLogs(logs);
      allEntries = logs;

      searchInput.oninput = () => {
        const q = searchInput.value.toLowerCase().trim();
        if (!q) {
          renderLogs(allEntries);
          countEl.textContent = `${allEntries.length} lines`;
          return;
        }
        const filtered = allEntries.filter(e =>
          (e.Message || "").toLowerCase().includes(q) ||
          (e.Module || "").toLowerCase().includes(q) ||
          (e.Type || "").toLowerCase().includes(q)
        );
        renderLogs(filtered);
        countEl.textContent = `${filtered.length} / ${allEntries.length} lines`;
      };

      c.appendChild(ld);
    } catch (e) { console.error("[Logs] Load logs failed:", e.message); c.innerHTML = "<p>Failed to load logs</p>"; }
  },

  async _dataPoints(c, aid) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const data = await api(`/api/logs/analysis/${aid}/data_points`);
      c.innerHTML = "";
      if (!data?.length) { c.appendChild(h("div", { className: "empty" }, h("p", null, "No data points"))); return; }
      const keys = Object.keys(data[0]);
      createTable(c, keys.map(k => ({ key: k, label: k })), data, { maxRows: 2000 });
    } catch (e) { console.error("[Logs] Load data points failed:", e.message); c.innerHTML = "<p>Failed to load data</p>"; }
  },

  async _artifacts(c, aid) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const data = await api(`/api/logs/analysis/${aid}/artifacts`);
      c.innerHTML = "";
      if (!data?.length) {
        c.appendChild(h("div", { className: "empty" }, h("p", null, "No artifacts")));
        return;
      }
      const list = h("div", { style: { padding: "1em" } });
      for (const a of data) {
        const sizeKB = (a.size / 1024).toFixed(1);
        const row = h("div", { style: {
          display: "flex", alignItems: "center", gap: "0.5em",
          padding: "0.4em 0", borderBottom: "1px solid var(--color-border, #333)",
        }},
          h("span", { style: { fontFamily: "monospace" } }, a.name),
          h("span", { className: "text-muted" }, `${sizeKB} KB`),
          h("a", {
            href: `/api/logs/analysis/${aid}/artifact/${a.name}`,
            download: a.name,
            className: "btn btn-sm",
            style: { marginLeft: "auto" },
          }, "Download"),
        );
        list.appendChild(row);
      }
      c.appendChild(list);
    } catch (e) {
      console.error("[Logs] Load artifacts failed:", e.message);
      c.innerHTML = "<p>Failed to load artifacts</p>";
    }
  },
});
