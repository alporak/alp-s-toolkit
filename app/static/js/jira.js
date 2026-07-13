/* ================================================================
   Jira Tracker v2 — Persistent sidebar, shared store, no re-fetch
   on tab switch. Phase 10: Seamless Tab Redesign (UI-01..06).
   ================================================================ */
import { h, $, $$, api, toast, registerPlugin, icons, makeColumnsResizable, setPluginBadge } from "./core.js";

/* ── Helpers ──────────────────────────────────────────────────── */
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const ICONS = {
  ...icons,
  edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  save: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>`,
  folder: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg>`,
  paperclip: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>`,
  download: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
  insights: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="12" width="3" height="9" rx="1"/><rect x="10" y="7" width="3" height="14" rx="1"/><rect x="17" y="3" width="3" height="18" rx="1"/></svg>`,
};

const fmtSec = s => {
  const hrs = Math.floor(s / 3600), min = Math.floor((s % 3600) / 60);
  return hrs ? `${hrs}h ${min}m` : `${min}m`;
};
const isoDate = d => d.toISOString().split("T")[0];
const mondayOf = d => { const c = new Date(d); c.setDate(c.getDate() - ((c.getDay() + 6) % 7)); return c; };
const addDays = (d, n) => { const c = new Date(d); c.setDate(c.getDate() + n); return c; };

/* ── Cached assigned list (frontend-side, shared across tabs) ── */
let _assignedCache = null;
let _assignedCacheTs = 0;
const ASSIGNED_CACHE_TTL = 120_000;

async function _getAssigned(force = false) {
  if (!force && _assignedCache && (Date.now() - _assignedCacheTs) < ASSIGNED_CACHE_TTL)
    return _assignedCache;
  try {
    _assignedCache = await api("/api/jira/assigned");
    _assignedCacheTs = Date.now();
  } catch (e) {
    console.error("[Jira] Failed to load assigned:", e.message);
    _assignedCache = [];
  }
  return _assignedCache;
}

/* ================================================================ */
registerPlugin({
  id: "jira", name: "Jira Tracker", order: 4, svgIcon: icons.clock,
  _cfg: null,
  _autoRefreshTimer: null,

  /* ── Shared store + state ─────────────────────────────────── */
  _store: { weekly: null, weeklyWeek: "", assigned: [], config: null },
  _dirty: { wk: true, asg: true, cfg: true, ins: true },
  _activePanel: "wk",
  _weekOffset: 0,

  /* ================================================================
     INIT  —  build the layout once, toggle panels on navigation
     ================================================================ */
  init(container) {
    container.classList.add("jira-app");
    container.innerHTML = "";

    const tabs = [
      { id: "wk",  label: "Weekly",   icon: icons.clock },
      { id: "asg", label: "Assigned", icon: icons.link },
      { id: "ins", label: "Insights", icon: ICONS.insights },
      { id: "cfg", label: "Config",   icon: icons.settings },
    ];

    // Sidebar
    const sidebar = h("div", { className: "jira-sidebar" });
    const sidebarTitle = h("div", { className: "jira-sidebar-title" }, "Jira Tracker");
    sidebar.appendChild(sidebarTitle);
    for (const t of tabs) {
      const btn = h("button", {
        className: "jira-sidebar-btn",
        "data-panel": t.id,
        onclick: () => this._showPanel(t.id),
      },
        h("span", { className: "jira-sidebar-icon", html: t.icon }),
        h("span", { className: "jira-sidebar-label" }, t.label),
        h("span", { className: "jira-sidebar-badge", style: { display: "none" } }),
      );
      sidebar.appendChild(btn);
    }
    container.appendChild(sidebar);

    // Content area — panels are mounted once, toggled via CSS
    const content = h("div", { className: "jira-content" });
    content.appendChild(this._buildWeeklyPanel());
    content.appendChild(this._buildAssignedPanel());
    content.appendChild(this._buildInsightsPanel());
    content.appendChild(this._buildConfigPanel());
    container.appendChild(content);

    this._showPanel("wk");
    this._startAutoRefresh();

    // Cross-tab invalidation (UI-05)
    window.addEventListener("storage", this._onStorageEvent = (e) => {
      if (e.key && e.key.startsWith("jira:")) {
        this._markDirty(e.key);
      }
    });
  },

  destroy() {
    if (this._autoRefreshTimer) { clearInterval(this._autoRefreshTimer); this._autoRefreshTimer = null; }
    window.removeEventListener("storage", this._onStorageEvent);
    setPluginBadge("jira", 0);
  },

  _startAutoRefresh() {
    if (this._autoRefreshTimer) clearInterval(this._autoRefreshTimer);
    const ttl = Math.max(60, ((this._cfg?.cache_ttl_minutes || 5) * 60)) * 1000;
    this._autoRefreshTimer = setInterval(() => {
      this._refreshActivePanel();
    }, ttl);
  },

  _markDirty(key) {
    if (!key) { this._dirty.wk = this._dirty.asg = true; return; }
    if (key.includes(":weekly") || key.includes(":insights")) this._dirty.wk = true;
    if (key.includes(":assigned")) this._dirty.asg = true;
    if (key.includes(":config")) this._dirty.cfg = true;
    setPluginBadge("jira", 0);  // TODO Phase 12: wire gap count
  },

  _refreshActivePanel() {
    this._dirty[this._activePanel] = true;
    this._refreshPanel(this._activePanel);
  },

  _showPanel(id) {
    this._activePanel = id;
    // Highlight sidebar button
    $$(".jira-sidebar-btn", document).forEach(b => b.classList.toggle("active", b.dataset.panel === id));
    // Toggle panel visibility
    const container = document.querySelector(".jira-content");
    if (!container) return;
    $$(".jira-panel", container).forEach(p => p.classList.toggle("active", p.dataset.panel === id));
    // Refresh if dirty
    if (this._dirty[id]) this._refreshPanel(id);
  },

  _refreshPanel(id) {
    switch (id) {
      case "wk":  this._refreshWeekly(); break;
      case "asg": this._refreshAssigned(); break;
      case "cfg": this._refreshConfig(); break;
      case "ins": this._refreshInsights(); break;
    }
  },

  /* ================================================================
     WEEKLY PANEL  (UI-01: mounted once, inner content refreshed)
     ================================================================ */
  _buildWeeklyPanel() {
    const panel = h("div", { className: "jira-panel", "data-panel": "wk" });
    const cacheIndicator = h("span", { className: "wk-cache-indicator" });
    const nav = h("div", { className: "wk-toolbar" },
      h("div", { className: "wk-toolbar-left" },
        h("button", { className: "wk-nav-btn", onclick: () => { this._weekOffset--; this._dirty.wk = true; this._showPanel("wk"); } }, "\u2039"),
        h("span", { className: "wk-week-label", id: "wk-week-label" }),
        h("button", { className: "wk-nav-btn", onclick: () => { this._weekOffset++; this._dirty.wk = true; this._showPanel("wk"); } }, "\u203A"),
        h("button", { className: "wk-nav-btn wk-today-btn", onclick: () => { this._weekOffset = 0; this._dirty.wk = true; this._showPanel("wk"); } }, "Today"),
      ),
      h("div", { className: "wk-toolbar-right" },
        cacheIndicator,
        h("button", { className: "wk-nav-btn wk-refresh-btn", title: "Force refresh from Jira",
          onclick: () => { this._dirty.wk = true; this._showPanel("wk"); } },
          h("span", { html: icons.refresh })),
      ),
    );
    panel.appendChild(nav);
    // Table area
    const tableArea = h("div", { className: "wk-table-area" });
    panel.appendChild(tableArea);
    return panel;
  },

  async _ensureCfg() {
    if (!this._cfg) try { this._cfg = await api("/api/jira/config"); } catch (e) { console.error("[Jira] Failed to load config:", e.message); }
    return this._cfg;
  },

  async _refreshWeekly() {
    const panel = document.querySelector(`.jira-panel[data-panel="wk"]`);
    if (!panel) return;
    const tableArea = panel.querySelector(".wk-table-area");
    const cacheInd = panel.querySelector(".wk-cache-indicator");
    const label = panel.querySelector("#wk-week-label");
    const cfg = await this._ensureCfg();
    if (!cfg?.has_token) { tableArea.innerHTML = '<div class="empty"><p>Configure Jira credentials in the Config tab first</p></div>'; return; }

    const monday = mondayOf(addDays(new Date(), this._weekOffset * 7));
    const sunday = addDays(monday, 6);
    const weekOf = isoDate(monday);
    label.textContent = `${weekOf}  \u2192  ${isoDate(sunday)}`;
    tableArea.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Loading worklogs\u2026</p></div>';

    // Cross-tab: write last-week to localStorage for other tabs
    try { localStorage.setItem("jira:weekly:week", weekOf); } catch (_) { }

    try {
      const myData = await api(`/api/jira/worklogs/weekly?week_of=${weekOf}`);
      tableArea.innerHTML = "";
      if (cacheInd) {
        cacheInd.textContent = myData.cached ? (myData.stale ? "stale" : "cached") : "live";
        cacheInd.className = "wk-cache-indicator" + (myData.stale ? " wk-stale" : myData.cached ? " wk-cached" : " wk-live");
      }
      this._store.weekly = myData;
      this._store.weeklyWeek = weekOf;
      this._dirty.wk = false;
      this._buildWeekTable(tableArea, myData.users[0], monday);

      if (cfg.teammates?.length) {
        const tmArea = h("div", { className: "wk-tm-area" });
        tableArea.appendChild(tmArea);
        for (const tm of cfg.teammates) {
          const tmContainer = h("div", { className: "wk-tm-loader" },
            h("span", { className: "spinner-sm" }), ` Loading ${tm.displayName || tm.accountId}\u2026`);
          tmArea.appendChild(tmContainer);
          api(`/api/jira/worklogs/weekly?week_of=${weekOf}&account_id=${tm.accountId}`)
            .then(tmData => {
              tmContainer.remove();
              if (tmData.users?.length) this._buildWeekTable(tmArea, tmData.users[0], monday);
            })
            .catch(err => {
              tmContainer.innerHTML = `<span class="text-error">Failed to load ${tm.displayName}</span>`;
              console.error(err);
            });
        }
      }

      try { localStorage.setItem("jira:weekly:data:" + weekOf, JSON.stringify(myData)); } catch (_) { }
    } catch (e) {
      console.error("[Jira] Weekly load failed:", e.message);
      tableArea.innerHTML = `<div class="empty"><p>Failed to load: ${e.message}</p></div>`;
    }
  },

  _buildWeekTable(container, user, monday) {
    const totalSec = user.worklogs.reduce((s, w) => s + (w.time_spent_seconds || 0), 0);
    let wrapper, contentTarget;
    if (user.is_me) {
      wrapper = h("div", { className: "wk-user-block" });
      wrapper.appendChild(h("div", { className: "wk-user-hdr" },
        h("span", { className: "wk-user-name" }, user.displayName + " (You)"),
        h("span", { className: "wk-user-total" }, fmtSec(totalSec)),
      ));
      contentTarget = wrapper;
    } else {
      wrapper = h("details", { className: "wk-user-details" });
      wrapper.appendChild(h("summary", { className: "wk-user-hdr wk-clickable" },
        h("span", { className: "wk-user-name" },
          h("span", { className: "wk-caret" }, "\u25B6"),
          user.displayName || "Teammate"),
        h("span", { className: "wk-user-total" }, fmtSec(totalSec)),
      ));
      contentTarget = wrapper;
    }
    container.appendChild(wrapper);
    if (!user.worklogs.length) {
      contentTarget.appendChild(h("div", { className: "wk-empty-week" }, "No worklogs this week"));
      return;
    }
    const byDate = {};
    for (const wl of user.worklogs) (byDate[wl.date] ??= []).push(wl);
    const colCount = user.is_me ? 6 : 5;
    const table = h("table", { className: "wk-tbl" });
    const thead = h("thead");
    thead.appendChild(h("tr", null,
      h("th", { className: "wk-th-day" }, "Day"),
      h("th", { className: "wk-th-ticket" }, "Ticket"),
      h("th", { className: "wk-th-summary" }, "Summary"),
      h("th", { className: "wk-th-time" }, "Time"),
      h("th", { className: "wk-th-comment" }, "Comment"),
      user.is_me ? h("th", { className: "wk-th-actions" }, "Actions") : null,
    ));
    table.appendChild(thead);
    const tbody = h("tbody");
    const sortedDates = Object.keys(byDate).sort();
    for (const dt of sortedDates) {
      const wls = byDate[dt];
      const dayIdx = (new Date(dt + "T00:00:00").getDay() + 6) % 7;
      const isToday = dt === isoDate(new Date());
      const daySec = wls.reduce((s, w) => s + (w.time_spent_seconds || 0), 0);
      if (tbody.children.length > 0)
        tbody.appendChild(h("tr", { className: "wk-row-spacer" }, h("td", { colSpan: String(colCount) })));
      for (let j = 0; j < wls.length; j++) {
        const wl = wls[j];
        const tr = h("tr", { className: "wk-row" + (isToday ? " wk-row-today" : ""), "data-id": wl.id });
        if (j === 0) {
          tr.appendChild(h("td", { className: "wk-cell-day" + (isToday ? " wk-cell-today" : ""), rowSpan: String(wls.length) },
            h("div", { className: "wk-day-label" }, DAY_NAMES[dayIdx]),
            h("div", { className: "wk-day-date" }, dt.slice(5)),
            h("div", { className: "wk-day-subtotal" + (daySec >= 28800 ? " wk-ok" : "") }, fmtSec(daySec)),
          ));
        }
        const jiraUrl = this._cfg?.url ? `${this._cfg.url}/browse/${wl.ticket_key}` : "#";
        tr.appendChild(h("td", { className: "wk-cell-ticket" },
          h("a", { href: jiraUrl, target: "_blank", className: "wk-ticket-link" }, wl.ticket_key)));
        tr.appendChild(h("td", { className: "wk-cell-summary" }, wl.ticket_summary));
        tr.appendChild(h("td", { className: "wk-cell-time" }, wl.time_spent));
        tr.appendChild(h("td", { className: "wk-cell-comment" }, wl.comment || ""));
        if (user.is_me) {
          const actionsCell = h("td", { className: "wk-cell-actions" });
          actionsCell.appendChild(h("button", { className: "wk-btn-icon", title: "Edit Worklog",
            onclick: () => this._enableEditMode(tr, wl, actionsCell) }, h("span", { html: ICONS.edit })));
          actionsCell.appendChild(h("button", { className: "wk-btn-icon wk-btn-del", title: "Delete Worklog",
            onclick: async () => {
              if (!confirm("Delete this worklog?")) return;
              try {
                await api(`/api/jira/worklog/${wl.ticket_key}/${wl.id}`, { method: "DELETE" });
                toast("Deleted", "success");
                this._dirty.wk = true;
                this._showPanel("wk");
              } catch (e) { console.error("[Jira] Delete failed:", e.message); }
            } }, h("span", { html: ICONS.x })));
          tr.appendChild(actionsCell);
        }
        tbody.appendChild(tr);
      }
    }
    table.appendChild(tbody);
    contentTarget.appendChild(table);
    makeColumnsResizable(table, "jira_weekly_col_widths");
  },

  _enableEditMode(tr, wl, actionsCell) {
    if (tr.classList.contains("wk-editing")) return;
    tr.classList.add("wk-editing");
    const timeCell = tr.querySelector(".wk-cell-time");
    const commentCell = tr.querySelector(".wk-cell-comment");
    const oldTime = timeCell.textContent;
    const oldComment = commentCell.textContent;
    timeCell.innerHTML = "";
    const timeInput = h("input", { className: "form-control input-sm", value: oldTime, style: { width: "70px", textAlign: "right" } });
    timeCell.appendChild(timeInput);
    commentCell.innerHTML = "";
    const commentInput = h("input", { className: "form-control input-sm", value: oldComment, style: { width: "100%" } });
    commentCell.appendChild(commentInput);
    const rerender = () => { this._dirty.wk = true; this._showPanel("wk"); };
    const save = async () => {
      const newTime = timeInput.value.trim();
      const newComment = commentInput.value.trim();
      if (!newTime) { timeInput.focus(); return; }
      try {
        await api(`/api/jira/worklog/${wl.ticket_key}/${wl.id}`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ issue_key: wl.ticket_key, time_spent: newTime, comment: newComment, started: wl.started.split("T")[0] }),
        });
        toast("Saved", "success");
        rerender();
      } catch (e) { console.error(e); }
    };
    actionsCell.innerHTML = "";
    actionsCell.appendChild(h("button", { className: "wk-btn-icon text-success", title: "Save", onclick: save }, h("span", { html: ICONS.save })));
    actionsCell.appendChild(h("button", { className: "wk-btn-icon text-dim", title: "Cancel", onclick: rerender }, h("span", { html: ICONS.x })));
    timeInput.addEventListener("keydown", e => { if (e.key === "Enter") save(); if (e.key === "Escape") rerender(); });
    commentInput.addEventListener("keydown", e => { if (e.key === "Enter") save(); if (e.key === "Escape") rerender(); });
    timeInput.focus();
  },

  /* ================================================================
     ASSIGNED PANEL
     ================================================================ */
  _buildAssignedPanel() {
    const panel = h("div", { className: "jira-panel", "data-panel": "asg" });
    const content = h("div", { className: "asg-content" });
    panel.appendChild(content);
    return panel;
  },

  async _refreshAssigned() {
    const panel = document.querySelector(`.jira-panel[data-panel="asg"]`);
    if (!panel) return;
    const content = panel.querySelector(".asg-content") || panel.querySelector(":scope > div") || panel;
    content.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Loading assigned tickets\u2026</p></div>';
    const cfg = await this._ensureCfg();
    if (!cfg?.has_token) { content.innerHTML = '<div class="empty"><p>Configure Jira credentials in the Config tab first</p></div>'; return; }
    const assigned = await _getAssigned(true);
    content.innerHTML = "";
    const today = isoDate(new Date());
    const yesterday = isoDate(addDays(new Date(), -1));
    const defaultMtgKey = cfg.meeting_ticket || "FMBP-44552";

    /* ── Log Work Card ────────────────────────────────────── */
    const ticketSelect = h("select", { id: "wl-key", className: "form-control" });
    ticketSelect.appendChild(h("option", { value: "" }, "\u2014 Select ticket \u2014"));
    for (const t of assigned) {
      ticketSelect.appendChild(h("option", { value: t.key }, `${t.key}  \u2013  ${t.summary}`.slice(0, 80)));
    }
    const ticketManual = h("input", { id: "wl-key-manual", className: "form-control", placeholder: "Or type ticket key (e.g. FMBP-12345)", style: { marginTop: "4px", display: "none" } });
    const toggleManual = h("button", { className: "btn btn-sm", onclick: () => {
      const show = ticketManual.style.display === "none";
      ticketManual.style.display = show ? "block" : "none";
      if (show) { ticketSelect.value = ""; ticketManual.focus(); } else ticketManual.value = "";
    } }, "manual entry");

    content.appendChild(h("div", { className: "card" },
      h("h3", null, "Log Work"),
      h("div", { className: "form-row" },
        h("div", { className: "form-group", style: { flex: "1", minWidth: "220px" } },
          h("label", null, "Ticket"), ticketSelect, ticketManual, toggleManual),
        h("div", { className: "form-group", style: { flex: "0 0 100px" } },
          h("label", null, "Time"), h("input", { id: "wl-time", className: "form-control", placeholder: "1h 30m" })),
        h("div", { className: "form-group", style: { flex: "0 0 150px" } },
          h("label", null, "Date"), h("input", { id: "wl-date", className: "form-control", type: "date", value: today })),
      ),
      h("div", { className: "form-row" },
        h("div", { className: "form-group", style: { flex: "1" } },
          h("label", null, "Comment"), h("input", { id: "wl-cmt", className: "form-control", placeholder: "What did you work on?" })),
      ),
      h("div", { className: "btn-group", style: { marginTop: "8px" } },
        h("button", { className: "btn btn-primary", onclick: () => this._submitWorklog() }, "Log Work"),
        h("button", { className: "btn", onclick: () => { $("#wl-date").value = today; } }, "Today"),
        h("button", { className: "btn", onclick: () => { $("#wl-date").value = yesterday; } }, "Yesterday"),
      ),
    ));

    const timeInput = $("#wl-time");
    const quickTimes = ["15m", "30m", "45m", "1h", "1h 30m", "2h", "3h", "4h"];
    const quickRow = h("div", { className: "jira-quick-times" });
    for (const qt of quickTimes) { quickRow.appendChild(h("button", { className: "jira-quick-time-btn", onclick: () => { timeInput.value = qt; } }, qt)); }
    timeInput.closest(".form-group").appendChild(quickRow);

    /* ── Meeting Log Card ─────────────────────────────────── */
    content.appendChild(h("div", { className: "card" },
      h("h3", null, "Log Meeting / Standup"),
      h("div", { className: "form-row" },
        h("div", { className: "form-group", style: { flex: "0 0 160px" } },
          h("label", null, "Meeting Ticket"), h("input", { id: "mt-key", className: "form-control", value: defaultMtgKey })),
        h("div", { className: "form-group", style: { flex: "0 0 100px" } },
          h("label", null, "Duration"), h("input", { id: "mt-time", className: "form-control", placeholder: "30m" })),
        h("div", { className: "form-group", style: { flex: "1", minWidth: "180px" } },
          h("label", null, "Comment"), h("input", { id: "mt-cmt", className: "form-control", placeholder: "Daily standup" })),
        h("div", { className: "form-group", style: { flex: "0 0 150px" } },
          h("label", null, "Date"), h("input", { id: "mt-date", className: "form-control", type: "date", value: today })),
      ),
      h("div", { className: "btn-group", style: { marginTop: "8px" } },
        h("button", { className: "btn btn-primary", onclick: () => this._submitMeeting() }, "Log Meeting"),
        h("button", { className: "btn", onclick: () => { $("#mt-date").value = today; } }, "Today"),
        h("button", { className: "btn", onclick: () => { $("#mt-date").value = yesterday; } }, "Yesterday"),
      ),
    ));

    if (!assigned.length) {
      content.appendChild(h("div", { className: "empty" }, h("p", null, "No assigned tickets")));
      return;
    }
    const toolbar = h("div", { className: "asg-toolbar" },
      h("span", { className: "asg-count" }, `${assigned.length} assigned tickets`),
      h("div", { className: "asg-toolbar-right" },
        cfg.tickets_folder
          ? h("span", { className: "asg-folder-path", title: cfg.tickets_folder },
              h("span", { className: "asg-folder-icon", html: ICONS.folder }), cfg.tickets_folder.split("\\").pop())
          : h("span", { className: "text-dim", style: { fontSize: "12px" } }, "No tickets folder configured"),
        h("button", { className: "btn btn-sm", title: "Refresh", onclick: () => { _assignedCache = null; this._dirty.asg = true; this._showPanel("asg"); } },
          h("span", { html: icons.refresh })),
      ),
    );
    content.appendChild(toolbar);

    const table = h("table", { className: "wk-tbl asg-tbl" });
    const thead = h("thead");
    thead.appendChild(h("tr", null,
      h("th", { style: { width: "120px" } }, "Key"),
      h("th", null, "Summary"),
      h("th", { style: { width: "100px" } }, "Status"),
      h("th", { style: { width: "70px", textAlign: "center" } }, "Attach"),
      h("th", { style: { width: "70px", textAlign: "center" } }, "Folder"),
      h("th", { style: { width: "180px", textAlign: "right" } }, "Actions"),
    ));
    table.appendChild(thead);
    const tbody = h("tbody");
    for (const t of assigned) {
      const url = cfg.url ? `${cfg.url}/browse/${t.key}` : "#";
      const stLower = (t.status || "").toLowerCase();
      let badgeClass = "badge-primary";
      if (stLower.includes("progress") || stLower.includes("review")) badgeClass = "badge-info";
      else if (stLower.includes("done") || stLower.includes("closed")) badgeClass = "badge-success";
      let folderIndicator;
      if (t.has_folder) {
        const synced = t.attachment_count > 0 && t.local_files >= t.attachment_count;
        folderIndicator = h("span", { className: "asg-folder-status" + (synced ? " asg-synced" : " asg-partial"),
          title: `${t.local_files} local files / ${t.attachment_count} remote attachments` },
          synced ? "\u2713" : `${t.local_files}/${t.attachment_count}`);
      } else if (t.attachment_count > 0) {
        folderIndicator = h("span", { className: "asg-folder-status asg-missing", title: "Not synced yet" }, "\u2717");
      } else {
        folderIndicator = h("span", { className: "asg-folder-status asg-none", title: "No attachments" }, "\u2014");
      }
      const tr = h("tr", { className: "wk-row" },
        h("td", { className: "wk-cell-ticket" }, h("a", { href: url, target: "_blank", className: "wk-ticket-link" }, t.key)),
        h("td", { className: "asg-cell-summary" }, t.summary),
        h("td", null, h("span", { className: `badge ${badgeClass}` }, t.status || "")),
        h("td", { style: { textAlign: "center" } },
          t.attachment_count > 0
            ? h("span", { className: "asg-att-count", title: `${t.attachment_count} attachments` },
                h("span", { className: "asg-att-icon", html: ICONS.paperclip }), String(t.attachment_count))
            : h("span", { className: "text-dim" }, "\u2014")),
        h("td", { style: { textAlign: "center" } }, folderIndicator),
      );
      const actTd = h("td", { className: "asg-actions" });
      actTd.appendChild(h("button", { className: "btn btn-sm btn-primary", title: "Log work to this ticket",
        onclick: () => { const sel = $("#wl-key"); if (sel) { sel.value = t.key; sel.scrollIntoView({ behavior: "smooth", block: "center" }); } } },
        h("span", { className: "btn-icon", html: icons.clock })));
      actTd.appendChild(h("button", { className: "btn btn-sm", title: "Sync attachments & open folder",
        onclick: async (ev) => {
          const btn = ev.currentTarget; btn.disabled = true; const orig = btn.innerHTML;
          btn.innerHTML = '<span class="spinner-sm"></span>';
          try {
            const res = await api(`/api/jira/ticket/${t.key}/sync?open_folder=true`, { method: "POST" });
            toast(`${t.key}: synced ${res.downloaded} new files`, "success");
            _assignedCache = null; this._dirty.asg = true; this._showPanel("asg");
          } catch (e) { toast(`Sync failed: ${e.message}`, "error"); btn.disabled = false; btn.innerHTML = orig; }
        } }, h("span", { className: "btn-icon", html: ICONS.download })));
      actTd.appendChild(h("button", { className: "btn btn-sm", title: "Open folder in Explorer",
        onclick: async () => { try { await api(`/api/jira/ticket/${t.key}/open`, { method: "POST" }); } catch (e) { toast(`Open failed: ${e.message}`, "error"); } } },
        h("span", { className: "btn-icon", html: ICONS.folder })));
      tr.appendChild(actTd);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    content.appendChild(h("div", { className: "wk-table-wrap" }, table));
    makeColumnsResizable(table, "jira_assigned_col_widths");
    this._store.assigned = assigned;
    this._dirty.asg = false;
    try { localStorage.setItem("jira:assigned:data", JSON.stringify(assigned)); } catch (_) { }
  },

  /* ================================================================
     CONFIG PANEL
     ================================================================ */
  _buildConfigPanel() {
    const panel = h("div", { className: "jira-panel", "data-panel": "cfg" });
    const content = h("div", { className: "cfg-content" });
    panel.appendChild(content);
    return panel;
  },

  async _refreshConfig() {
    const panel = document.querySelector(`.jira-panel[data-panel="cfg"]`);
    if (!panel) return;
    const content = panel.querySelector(".cfg-content");
    content.innerHTML = '<div class="loading-state"><div class="spinner"></div></div>';
    try {
      const cfg = await api("/api/jira/config");
      this._cfg = cfg; this._store.config = cfg; this._dirty.cfg = false;
      content.innerHTML = "";
      content.appendChild(h("div", { className: "card" },
        h("h3", null, "Jira Credentials"),
        h("div", { className: "form-row" },
          h("div", { className: "form-group", style: { flex: "1" } },
            h("label", null, "Jira URL"), h("input", { id: "j-url", className: "form-control", value: cfg.url || "", placeholder: "https://jira.example.com" })),
          h("div", { className: "form-group", style: { flex: "1" } },
            h("label", null, "Email"), h("input", { id: "j-email", className: "form-control", value: cfg.email || "" })),
        ),
        h("div", { className: "form-row" },
          h("div", { className: "form-group", style: { flex: "1" } },
            h("label", null, "API Token"), h("input", { id: "j-token", className: "form-control", type: "password", placeholder: cfg.has_token ? "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022  (leave blank to keep)" : "Enter API token" })),
        ),
        h("div", { className: "form-row" },
          h("div", { className: "form-group", style: { flex: "0 0 160px" } },
            h("label", null, "Meeting Ticket"), h("input", { id: "j-mtg", className: "form-control", value: cfg.meeting_ticket || "" })),
          h("div", { className: "form-group", style: { flex: "0 0 100px" } },
            h("label", null, "Cache TTL"), h("input", { id: "j-cache-ttl", className: "form-control", type: "number", min: "1", max: "60", value: String(cfg.cache_ttl_minutes || 5) })),
          h("div", { className: "form-group", style: { flex: "0 0 80px" } },
            h("label", null, "Target h/d"), h("input", { id: "j-daily-target", className: "form-control", type: "number", min: "1", max: "24", value: String(cfg.daily_target_hours || 8) })),
          h("div", { className: "form-group", style: { flex: "0 0 80px" } },
            h("label", null, "Min h/d"), h("input", { id: "j-daily-min", className: "form-control", type: "number", min: "1", max: "24", value: String(cfg.daily_min_hours || 4) })),
          h("div", { className: "form-group", style: { flex: "1" } },
            h("label", null, "Tickets Folder"), h("input", { id: "j-tickets-folder", className: "form-control", value: cfg.tickets_folder || "", placeholder: "C:\\path\\to\\_tickets" })),
        ),
        h("div", { className: "btn-group" },
          h("button", { className: "btn btn-primary", onclick: async () => {
            try {
              const upd = { url: ($("#j-url")?.value || "").trim(), email: ($("#j-email")?.value || "").trim(), api_token: ($("#j-token")?.value || "").trim(), meeting_ticket: ($("#j-mtg")?.value || "").trim(), cache_ttl_minutes: parseInt($("#j-cache-ttl")?.value) || 5, daily_target_hours: parseInt($("#j-daily-target")?.value) || 8, daily_min_hours: parseInt($("#j-daily-min")?.value) || 4, tickets_folder: ($("#j-tickets-folder")?.value || "").trim() };
              await api("/api/jira/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(upd) });
              this._cfg = null; this._dirty.wk = this._dirty.asg = true; this._startAutoRefresh();
              toast("Configuration saved", "success");
            } catch (e) { console.error("[Jira] Save config failed:", e.message); }
          } }, "Save"),
          h("button", { className: "btn", onclick: async () => {
            try { const me = await api("/api/jira/myself"); toast(`Connected as ${me.displayName || me.email || "OK"}`, "success"); } catch (e) { toast("Connection failed", "error"); }
          } }, h("span", { className: "btn-icon", html: icons.link }), "Test Connection"),
        ),
      ));
      content.appendChild(this._buildTeammateConfig(cfg.teammates || []));
    } catch (e) {
      console.error("[Jira] Load config failed:", e.message);
      content.innerHTML = `<div class="empty"><p>Failed to load config: ${e.message}</p></div>`;
    }
  },

  _buildTeammateConfig(teammates) {
    const card = h("div", { className: "card" },
      h("h3", null, "Teammates"),
      h("p", { className: "text-dim", style: { marginBottom: "12px", fontSize: "12px" } }, "Add teammates to see their worklogs alongside yours."),
    );
    const listEl = h("div", { id: "tm-list", className: "teammate-list" });
    const renderList = () => {
      listEl.innerHTML = "";
      if (!teammates.length) { listEl.appendChild(h("div", { className: "text-muted", style: { padding: "8px 0", fontSize: "12px" } }, "No teammates added yet")); return; }
      for (const tm of teammates) {
        listEl.appendChild(h("div", { className: "teammate-item" },
          h("span", null, tm.displayName || tm.accountId),
          h("button", { className: "btn btn-danger btn-sm", onclick: async () => {
            teammates = teammates.filter(t => t.accountId !== tm.accountId);
            try { await api("/api/jira/teammates", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ teammates }) }); toast("Removed", "success"); } catch (e) { console.error(e); }
            renderList();
          } }, h("span", { html: icons.x })),
        ));
      }
    };
    renderList(); card.appendChild(listEl);
    const searchResults = h("div", { id: "tm-results", style: { marginTop: "8px" } });
    const searchRow = h("div", { className: "form-row", style: { marginTop: "12px" } },
      h("input", { id: "tm-search", className: "form-control", placeholder: "Search by name or email\u2026", style: { flex: "1" } }),
      h("button", { className: "btn btn-primary", onclick: async () => {
        const q = ($("#tm-search")?.value || "").trim();
        if (q.length < 2) { toast("Enter at least 2 characters", "error"); return; }
        searchResults.innerHTML = '<div class="spinner"></div>';
        try {
          const users = await api(`/api/jira/users/search?query=${encodeURIComponent(q)}`);
          searchResults.innerHTML = "";
          if (!users.length) { searchResults.appendChild(h("div", { className: "text-muted" }, "No users found")); return; }
          for (const u of users) {
            const already = teammates.some(t => t.accountId === u.accountId);
            searchResults.appendChild(h("div", { className: "teammate-search-result" },
              h("span", null, `${u.displayName} (${u.email || ""})`),
              already ? h("span", { className: "badge badge-primary" }, "Added")
                : h("button", { className: "btn btn-sm btn-primary", onclick: async () => {
                    teammates.push({ accountId: u.accountId, displayName: u.displayName });
                    try { await api("/api/jira/teammates", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ teammates }) }); toast(`Added ${u.displayName}`, "success"); } catch (e) { console.error(e); }
                    renderList(); searchResults.innerHTML = "";
                  } }, "Add"),
            ));
          }
        } catch (e) { searchResults.innerHTML = "<p>Search failed</p>"; }
      } }, h("span", { className: "btn-icon", html: icons.search }), "Search"),
    );
    card.appendChild(searchRow); card.appendChild(searchResults);
    return card;
  },

  /* ================================================================
     INSIGHTS PANEL  (Phase 11: ghost-days, under-target, history, nwd)
     ================================================================ */
  _insWeekOffset: 0,

  _buildInsightsPanel() {
    const panel = h("div", { className: "jira-panel", "data-panel": "ins" });
    const nav = h("div", { className: "wk-toolbar" },
      h("div", { className: "wk-toolbar-left" },
        h("button", { className: "wk-nav-btn", onclick: () => { this._insWeekOffset--; this._dirty.ins = true; this._showPanel("ins"); } }, "\u2039"),
        h("span", { className: "wk-week-label", id: "ins-week-label" }),
        h("button", { className: "wk-nav-btn", onclick: () => { this._insWeekOffset++; this._dirty.ins = true; this._showPanel("ins"); } }, "\u203A"),
        h("button", { className: "wk-nav-btn wk-today-btn", onclick: () => { this._insWeekOffset = 0; this._dirty.ins = true; this._showPanel("ins"); } }, "Today"),
      ),
    );
    panel.appendChild(nav);
    panel.appendChild(h("div", { className: "ins-content" }));
    return panel;
  },

  async _refreshInsights() {
    const panel = document.querySelector(`.jira-panel[data-panel="ins"]`);
    if (!panel) return;
    const content = panel.querySelector(".ins-content");
    const label = panel.querySelector("#ins-week-label");
    const cfg = await this._ensureCfg();
    if (!cfg?.has_token) { content.innerHTML = '<div class="empty"><p>Configure Jira credentials in the Config tab first</p></div>'; return; }

    const monday = mondayOf(addDays(new Date(), this._insWeekOffset * 7));
    const sunday = addDays(monday, 6);
    const weekOf = isoDate(monday);
    label.textContent = `${weekOf}  \u2192  ${isoDate(sunday)}`;
    content.innerHTML = '<div class="loading-state"><div class="spinner"></div></div>';

    try {
      const ins = await api(`/api/jira/insights?week_of=${weekOf}`);
      const nwd = await api("/api/jira/non-working-days");
      content.innerHTML = "";

      // Summary bar
      const pct = ins.target_seconds > 0 ? Math.min(100, Math.round(ins.total_seconds / ins.target_seconds * 100)) : 0;
      content.appendChild(h("div", { className: "ins-summary" },
        h("div", { className: "ins-bar" },
          h("div", { className: "ins-bar-fill" + (pct >= 100 ? " ins-ok" : " ins-warn"), style: { width: pct + "%" } }),
          h("span", { className: "ins-bar-label" }, `${fmtSec(ins.total_seconds)} / ${fmtSec(ins.target_seconds)} (${ins.working_days}d)`),
        ),
        ins.below_target
          ? h("p", { className: "ins-gap" }, `\u26A0 ${fmtSec(ins.gap_seconds)} below target`)
          : h("p", { className: "ins-ontarget" }, "\u2713 On target"),
      ));

      // Missing days
      if (ins.missing_days.length) {
        content.appendChild(h("h3", { className: "ins-hdr" }, `Missing (${ins.missing_days.length})`));
        const grid = h("div", { className: "ins-day-grid" });
        for (const d of ins.missing_days) {
          const date = new Date(d + "T00:00:00");
          const label = DAY_NAMES[(date.getDay() + 6) % 7] + " " + d.slice(5);
          grid.appendChild(h("button", { className: "ins-tag ins-tag-miss",
            title: `Click for per-day context`, onclick: () => {
              const div = h("div", { className: "ins-drill" },
                h("p", null, label + " — 0h (missing)"),
                ...Object.entries(ins.per_day || {}).map(([dd, ss]) =>
                  h("div", { className: ss === 0 ? "text-error" : "" },
                    DAY_NAMES[(new Date(dd + "T00:00:00").getDay() + 6) % 7] + " " + dd.slice(5) + ": " + fmtSec(ss)))
              );
              const existing = grid.nextElementSibling;
              if (existing?.classList.contains("ins-drill")) existing.remove();
              div.onclick = () => div.remove();
              grid.after(div);
            } }, label));
        }
        content.appendChild(grid);
      }

      // Low hours
      if (ins.low_days.length) {
        content.appendChild(h("h3", { className: "ins-hdr" }, `Low hours (${ins.low_days.length})`));
        const grid = h("div", { className: "ins-day-grid" });
        for (const d of ins.low_days) {
          const date = new Date(d + "T00:00:00");
          const label = DAY_NAMES[(date.getDay() + 6) % 7] + " " + d.slice(5) + " (" + fmtSec(ins.per_day[d] || 0) + ")";
          grid.appendChild(h("span", { className: "ins-tag ins-tag-low" }, label));
        }
        content.appendChild(grid);
      }

      // Warned days (marked off with hours)
      if (ins.warned_days.length) {
        content.appendChild(h("h3", { className: "ins-hdr" }, "\u26A0 Marked-off days with hours"));
        const grid = h("div", { className: "ins-day-grid" });
        for (const d of ins.warned_days) {
          const label = d.slice(5) + " (" + fmtSec(ins.per_day[d] || 0) + ")";
          grid.appendChild(h("span", { className: "ins-tag ins-tag-warn" }, label));
        }
        content.appendChild(grid);
      }

      // Historical trend (last 4 weeks)
      await this._renderTrend(content, monday, cfg);

      // Non-working day manager
      await this._renderNWD(content, nwd);

      this._dirty.ins = false;
    } catch (e) {
      console.error("[Jira] Insights failed:", e.message);
      content.innerHTML = `<div class="empty"><p>Failed: ${e.message}</p></div>`;
    }
  },

  async _renderTrend(container, currentMonday, cfg) {
    const section = h("div", { className: "ins-trend" });
    section.appendChild(h("h3", { className: "ins-hdr" }, "Trend (4 weeks)"));
    const row = h("div", { className: "ins-trend-row" });
    for (let i = 3; i >= 0; i--) {
      const w = isoDate(addDays(currentMonday, -i * 7));
      try {
        const s = await api(`/api/jira/insights/summary?week_of=${w}`);
        const pct = s.gap_seconds === 0 && !s.below_target ? 100
          : Math.min(100, Math.round((s.gap_seconds || 0) / (cfg.daily_target_hours * 3600 * 5) * 100));
        row.appendChild(h("div", { className: "ins-trend-bar-wrap" },
          h("div", { className: "ins-trend-bar", style: { height: pct + "%" },
            title: `${w.slice(5)}: gap ${fmtSec(s.gap_seconds || 0)}` }),
        ));
      } catch (_) {}
    }
    section.appendChild(row);
    container.appendChild(section);
  },

  async _renderNWD(container, nwd) {
    const section = h("div", { className: "ins-nwd" });
    section.appendChild(h("h3", { className: "ins-hdr" }, "Non-working days"));
    const grid = h("div", { className: "ins-day-grid" });
    for (const d of nwd) {
      grid.appendChild(h("span", { className: "ins-tag ins-tag-off" },
        d, h("button", { className: "ins-nwd-del", title: "Remove",
          onclick: async () => {
            try { await api(`/api/jira/non-working-days/${d}`, { method: "DELETE" }); this._dirty.ins = true; this._showPanel("ins"); }
            catch (e) { toast("Remove failed", "error"); }
          } }, "\u00d7"),
      ));
    }
    section.appendChild(grid);
    const addForm = h("div", { className: "form-row", style: { marginTop: "var(--sp-2)" } },
      h("input", { id: "nwd-date", className: "form-control", type: "date", style: { flex: "1" } }),
      h("button", { className: "btn btn-sm btn-primary", onclick: async () => {
        const d = ($("#nwd-date")?.value || "").trim();
        if (!d) return;
        try { await api("/api/jira/non-working-days", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ date: d }) }); this._dirty.ins = true; this._showPanel("ins"); }
        catch (e) { toast("Add failed", "error"); }
      } }, "Mark"),
    );
    section.appendChild(addForm);
    container.appendChild(section);
  },

  /* ================================================================
     SUBMIT HANDLERS  (unchanged from v1, just mark panels dirty)
     ================================================================ */
  async _submitWorklog() {
    const selKey = ($("#wl-key")?.value || "").trim();
    const manKey = ($("#wl-key-manual")?.value || "").trim();
    const key = manKey || selKey;
    const time = ($("#wl-time")?.value || "").trim();
    if (!key || !time) { toast("Ticket + time required", "error"); return; }
    try {
      await api("/api/jira/worklog", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ issue_key: key, time_spent: time, comment: ($("#wl-cmt")?.value || "").trim(), started: $("#wl-date")?.value }) });
      toast(`Logged ${time} to ${key}`, "success");
      if ($("#wl-time")) $("#wl-time").value = "";
      if ($("#wl-cmt")) $("#wl-cmt").value = "";
      this._dirty.wk = true; this._dirty.asg = true;
    } catch (e) { console.error("[Jira] Add worklog failed:", e.message); }
  },

  async _submitMeeting() {
    const key = ($("#mt-key")?.value || "").trim();
    const time = ($("#mt-time")?.value || "").trim();
    if (!time) { toast("Duration required", "error"); return; }
    try {
      await api("/api/jira/meeting", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ issue_key: key, time_spent: time, summary: ($("#mt-cmt")?.value || "").trim(), started: $("#mt-date")?.value }) });
      toast(`Meeting logged (${time})`, "success");
      if ($("#mt-time")) $("#mt-time").value = "";
      if ($("#mt-cmt")) $("#mt-cmt").value = "";
      this._dirty.wk = true;
    } catch (e) { console.error("[Jira] Log meeting failed:", e.message); }
  },
});
