/* ================================================================
   Competence Matrix Plugin — Power-user analytics dashboard
   ================================================================ */
import { h, api, toast, registerPlugin, icons, createTabs, createTable } from "./core.js";

registerPlugin({
  id: "competence",
  name: "Competence Matrix",
  order: 45,
  svgIcon: icons.chart,

  _accountId: "",
  _dateFrom: "",
  _dateTo: "",

  init(container) {
    this._render(container);
    this._setupChartClickListener();
  },

  _setupChartClickListener() {
    const self = this;
    window.addEventListener("message", (e) => {
      if (e.data && e.data.type === "competence_period_click") {
        self._showPeriodDetail(e.data.period);
      }
    });
  },

  async _showPeriodDetail(period) {
    try {
      const data = await this._api("/api/competence/quarterly_details");
      const match = data.find(d => d.period === period);
      if (!match) return;

      const detailPanel = document.getElementById("comp-chart-detail");
      if (!detailPanel) return;

      detailPanel.innerHTML = "";
      detailPanel.appendChild(h("h3", { style: { marginBottom: "8px" } }, period + " — " + match.total_attempts + " attempts, " + match.total_returns + " returns (" + match.rate + "%)"));

      if (match.tickets && match.tickets.length) {
        const tableWrap = h("div");
        detailPanel.appendChild(tableWrap);
        const enriched = match.tickets.map(t => ({
          ticket_key: t.ticket_key,
          attempts: t.attempts,
          returns: t.returns,
        }));
        createTable(tableWrap, [
          { key: "ticket_key", label: "Key" },
          { key: "attempts", label: "Attempts" },
          { key: "returns", label: "Returns" },
        ], enriched, { maxRows: 200 });
      }
    } catch (e) {
      console.error("[Competence] Failed to load period detail:", e);
    }
  },

  destroy() {},

  // ── URL builder ────────────────────────────────────────

  _buildParams() {
    const p = [];
    if (this._accountId) p.push("account_id=" + encodeURIComponent(this._accountId));
    if (this._dateFrom) p.push("date_from=" + encodeURIComponent(this._dateFrom));
    if (this._dateTo) p.push("date_to=" + encodeURIComponent(this._dateTo));
    return p.length ? "?" + p.join("&") : "";
  },

  _api(path) {
    return api(path + this._buildParams());
  },

  // ── Layout ──────────────────────────────────────────

  _render(c) {
    const self = this;
    c.innerHTML = "";

    // Persistent header row
    const header = h("div", {
      style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap" }
    },
      h("h2", null, "Bug Return Rate"),

      // Teammate dropdown
      h("select", {
        id: "comp-teammate",
        style: { padding: "4px 8px", borderRadius: "4px", background: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--border)" },
        onchange: () => {
          self._accountId = document.getElementById("comp-teammate").value;
          self._reloadActive();
        },
      }),

      // Quarter filter
      h("select", {
        id: "comp-quarter",
        style: { padding: "4px 8px", borderRadius: "4px", background: "var(--bg-secondary)", color: "var(--text-primary)", border: "1px solid var(--border)" },
        onchange: () => {
          const v = document.getElementById("comp-quarter").value;
          if (v) {
            const [y, q] = v.split("-Q");
            const qs = { "1": "01-01", "2": "04-01", "3": "07-01", "4": "10-01" };
            const qe = { "1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31" };
            self._dateFrom = y + "-" + qs[q];
            self._dateTo = y + "-" + qe[q];
          } else {
            self._dateFrom = "";
            self._dateTo = "";
          }
          self._reloadActive();
        },
      }, h("option", { value: "" }, "All Time")),

      h("button", {
        className: "btn btn-primary",
        id: "comp-sync-btn",
        onclick: async () => self._doSync(),
      }, "Sync Now"),
      h("span", { id: "comp-status", className: "text-muted" }, "Checking..."),
    );
    c.appendChild(header);

    // Tab container
    const tabContainer = h("div");
    c.appendChild(tabContainer);

    createTabs(tabContainer, [
      {
        id: "overview", label: "Overview",
        render(panel) { self._renderOverview(panel); },
      },
      {
        id: "tickets", label: "Per Ticket",
        render(panel) { self._renderTickets(panel); },
      },
      {
        id: "quarters", label: "Quarterly Breakdown",
        render(panel) { self._renderQuarters(panel); },
      },
      {
        id: "charts", label: "Charts",
        render(panel) { self._renderCharts(panel); },
      },
    ]);

    this._refreshStatus();
    this._loadTeammates();
  },

  async _loadTeammates() {
    try {
      const list = await api("/api/competence/teammates");
      const sel = document.getElementById("comp-teammate");
      if (!sel) return;
      sel.innerHTML = "";
      list.forEach(t => {
        sel.appendChild(h("option", { value: t.accountId }, t.displayName));
      });
      // Select "Me" (first item) by default
      if (list.length) {
        sel.value = list[0].accountId;
        this._accountId = list[0].accountId;
      }
    } catch (e) { /* non-critical */ }
  },

  _reloadActive() {
    // Quick reload of visible data without full re-render
    const chartAreas = document.querySelectorAll("[id^='comp-chart-rate'], [id^='comp-charts-rate']");
    chartAreas.forEach(el => this._loadChartUrl(el, "/api/competence/chart" + this._buildParams()));

    const volAreas = document.querySelectorAll("[id^='comp-chart-volume'], [id^='comp-charts-volume']");
    volAreas.forEach(el => this._loadChartUrl(el, "/api/competence/chart/volume" + this._buildParams()));

    if (document.getElementById("comp-chart-rate")) this._loadSummaryCards();
  },

  // ── Overview tab ─────────────────────────────────────

  async _renderOverview(c) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const summary = await this._api("/api/competence/summary");
      c.innerHTML = "";

      // Summary cards
      const cards = h("div", {
        style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px", marginBottom: "20px" }
      });
      [
        ["Total Tickets", summary.total_tickets],
        ["Total Attempts", summary.total_attempts],
        ["Total Returns", summary.total_returns],
        ["Return Rate", summary.overall_rate_pct + "%"],
      ].forEach(([label, value]) => {
        cards.appendChild(h("div", {
          style: { background: "var(--bg-secondary)", borderRadius: "8px", padding: "16px", textAlign: "center" }
        },
          h("div", { style: { fontSize: "24px", fontWeight: "700", color: "var(--accent)" } }, String(value)),
          h("div", { style: { fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" } }, label),
        ));
      });
      c.appendChild(cards);

      if (summary.most_returned && summary.most_returned.length) {
        const top = h("div", { style: { marginBottom: "16px" } },
          h("h3", { style: { marginBottom: "8px" } }, "Most Returned Tickets"),
        );
        summary.most_returned.forEach(t => {
          top.appendChild(h("div", {
            style: { padding: "4px 0", fontSize: "13px", color: "var(--text-muted)" }
          }, t.key + ": " + (t.summary ? t.summary.substring(0, 60) + (t.summary.length > 60 ? "..." : "") : "") + " (" + t.returns + " returns)"));
        });
        c.appendChild(top);
      }

      const cr = h("div", { id: "comp-chart-rate" });
      c.appendChild(cr);
      this._loadChartUrl(cr, "/api/competence/chart" + this._buildParams());

      const cv = h("div", { id: "comp-chart-volume" });
      c.appendChild(cv);
      this._loadChartUrl(cv, "/api/competence/chart/volume" + this._buildParams());

      const detail = h("div", { id: "comp-chart-detail", style: { marginTop: "16px" } });
      c.appendChild(detail);

    } catch (e) {
      c.innerHTML = '<p class="text-muted">Failed to load overview: ' + e.message + '</p>';
    }
  },

  // ── Per-Ticket tab ───────────────────────────────────

  async _renderTickets(c) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const tickets = await this._api("/api/competence/tickets");
      c.innerHTML = "";

      if (!tickets.length) {
        c.appendChild(h("div", { className: "empty" },
          h("div", { className: "empty-icon" }, "\u2014"),
          h("p", null, "No ticket data \u2014 click Sync Now"),
        ));
        return;
      }

      const self = this;
      const detailEl = h("div", { id: "comp-detail", style: { marginTop: "16px" } });
      const tableWrap = h("div");
      c.appendChild(tableWrap);
      c.appendChild(detailEl);

      createTable(tableWrap, [
        {
          key: "ticket_key", label: "Key",
          render: row => h("a", {
            href: "#", style: { color: "var(--accent)", cursor: "pointer" },
            onclick: (e) => { e.preventDefault(); self._showTicketDetail(row.ticket_key, detailEl); },
          }, row.ticket_key),
        },
        { key: "summary", label: "Summary" },
        { key: "issue_type", label: "Type" },
        { key: "attempts", label: "Attempts" },
        { key: "returns", label: "Returns" },
        {
          key: "return_rate_pct", label: "Rate",
          render: row => h("span", {
            style: { color: row.return_rate_pct > 20 ? "#e74c3c" : "var(--text-primary)" }
          }, row.return_rate_pct + "%"),
        },
        { key: "last_return_date", label: "Last Return" },
        { key: "last_return_by", label: "Returned By" },
        {
          key: "excluded", label: "",
          render: row => h("button", {
            className: row.excluded ? "btn btn-sm" : "btn btn-sm btn-outline",
            style: { fontSize: "11px", padding: "2px 8px" },
            onclick: async (e) => { e.stopPropagation(); await self._toggleExclude(row.ticket_key); self._renderTickets(c); },
          }, row.excluded ? "Excluded" : "Exclude"),
        },
      ], tickets, { maxRows: 500 });

    } catch (e) {
      c.innerHTML = '<p class="text-muted">Failed to load tickets: ' + e.message + '</p>';
    }
  },

  async _toggleExclude(key) {
    try {
      const res = await api("/api/competence/tickets/" + key + "/exclude", { method: "POST" });
      toast(res.excluded ? "Ticket excluded" : "Ticket re-included", "info");
    } catch (e) {
      toast("Failed to toggle: " + e.message, "error");
    }
  },

  async _showTicketDetail(key, container) {
    container.innerHTML = '<div class="spinner"></div>';
    try {
      const detail = await api("/api/competence/tickets/" + key);
      const header = h("div", { style: { display: "flex", gap: "8px", marginBottom: "12px" } },
        h("strong", null, detail.ticket_key),
        h("span", { style: { color: "var(--text-muted)" } }, detail.summary),
      );
      let timeline = "";
      detail.transitions.forEach(t => {
        const badge = t.action === "ATTEMPT"
          ? '<span style="color:#3498db;font-weight:600">ATTEMPT</span>'
          : '<span style="color:#e74c3c;font-weight:600">RETURN</span>';
        timeline += '<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:13px">' +
          '<strong>' + t.date.substring(0, 10) + '</strong> ' + badge +
          ' <span style="color:var(--text-muted)">' + t.from + ' \u2192 ' + t.to + '</span>' +
          (t.author ? ' <span style="color:var(--text-muted)">by ' + t.author + '</span>' : "") +
          '</div>';
      });
      container.innerHTML = "";
      container.appendChild(h("div", { style: { padding: "12px", background: "var(--bg-secondary)", borderRadius: "8px" } },
        header,
        h("div", { html: timeline }),
      ));
    } catch (e) {
      container.innerHTML = '<p class="text-muted">Failed to load ticket detail: ' + e.message + '</p>';
    }
  },

  // ── Quarterly Breakdown tab ──────────────────────────

  async _renderQuarters(c) {
    c.innerHTML = '<div class="spinner"></div>';
    try {
      const data = await this._api("/api/competence/quarterly_details");
      c.innerHTML = "";

      if (!data.length) {
        c.appendChild(h("div", { className: "empty" },
          h("div", { className: "empty-icon" }, "\u2014"),
          h("p", null, "No data \u2014 click Sync Now"),
        ));
        return;
      }

      const self = this;
      data.forEach((period, idx) => {
        const header = h("div", {
          style: {
            padding: "10px 12px", cursor: "pointer",
            background: "var(--bg-secondary)", borderRadius: "8px",
            marginBottom: idx < data.length - 1 ? "4px" : "0",
            display: "flex", justifyContent: "space-between", alignItems: "center",
          },
          onclick: () => {
            const body = header.nextSibling;
            if (body) body.style.display = body.style.display === "none" ? "block" : "none";
          },
        },
          h("span", null, period.period),
          h("span", {
            style: { color: period.rate > 20 ? "#e74c3c" : "var(--text-muted)", fontSize: "13px" }
          },
            period.total_attempts + " attempts, " + period.total_returns + " returns (" + period.rate + "%)"
          ),
        );
        c.appendChild(header);

        const body = h("div", { style: { display: "none", marginTop: "4px", marginBottom: "8px" } });
        c.appendChild(body);

        if (period.tickets && period.tickets.length) {
          const enriched = period.tickets.map(t => ({
            ...t,
            summary: "",
            issue_type: "",
          }));
          createTable(body, [
            { key: "ticket_key", label: "Key" },
            { key: "attempts", label: "Attempts" },
            { key: "returns", label: "Returns" },
          ], enriched, { maxRows: 200 });
        }
      });

    } catch (e) {
      c.innerHTML = '<p class="text-muted">Failed to load breakdown: ' + e.message + '</p>';
    }
  },

  // ── Charts tab ───────────────────────────────────────

  _renderCharts(c) {
    c.innerHTML = "";
    const cr = h("div", { id: "comp-charts-rate" });
    c.appendChild(cr);
    this._loadChartUrl(cr, "/api/competence/chart" + this._buildParams());
    const cv = h("div", { id: "comp-charts-volume", style: { marginTop: "16px" } });
    c.appendChild(cv);
    this._loadChartUrl(cv, "/api/competence/chart/volume" + this._buildParams());
    const detail = h("div", { id: "comp-chart-detail", style: { marginTop: "16px" } });
    c.appendChild(detail);
  },

  // ── Chart rendering ──────────────────────────────────

  async _loadChartUrl(container, url) {
    container.innerHTML = '<div class="spinner"></div>';
    try {
      const html = await api(url);
      container.innerHTML = "";
      container.appendChild(h("iframe", {
        srcdoc: html,
        style: { width: "100%", height: "460px", border: "none" },
      }));
    } catch (e) {
      console.error("[Competence] Load chart failed:", e.message);
      container.innerHTML = '<p class="text-muted">Failed to load chart: ' + e.message + '</p>';
    }
  },

  // ── Summary cards refresh ────────────────────────────

  async _loadSummaryCards() {
    try {
      const summary = await this._api("/api/competence/summary");
      const cards = document.querySelectorAll("#main [style*='font-size: 24px']");
      if (cards.length >= 4) {
        cards[0].textContent = String(summary.total_tickets);
        cards[1].textContent = String(summary.total_attempts);
        cards[2].textContent = String(summary.total_returns);
        cards[3].textContent = summary.overall_rate_pct + "%";
      }
    } catch (e) { /* non-critical */ }
  },

  // ── Sync ─────────────────────────────────────────────

  async _doSync() {
    const btn = document.getElementById("comp-sync-btn");
    if (!btn) return;
    const origHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-sm"></span> Syncing...';
    try {
      const url = "/api/competence/sync" + (this._accountId ? "?account_id=" + encodeURIComponent(this._accountId) : "");
      const res = await api(url, { method: "POST" });
      toast(res.message || "Sync started", "success");
      await this._waitForSync();
      this._reloadActive();
    } catch (e) {
      toast("Sync failed: " + e.message, "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = origHTML;
      this._refreshStatus();
    }
  },

  async _waitForSync() {
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const status = await api("/api/competence/sync/status");
        this._updateStatus(status);
        if (!status.in_progress) return;
      } catch (e) { /* continue polling */ }
    }
  },

  // ── Status display ───────────────────────────────────

  async _refreshStatus() {
    try {
      const status = await api("/api/competence/sync/status");
      this._updateStatus(status);
    } catch (e) { /* ignore — non-critical */ }
  },

  _updateStatus(status) {
    const el = document.getElementById("comp-status");
    if (!el) return;
    if (status.in_progress) {
      const p = status.progress;
      if (p && p.phase === "fetching_changelogs" && p.total) {
        el.textContent = "Fetching changelogs: " + p.done + "/" + p.total;
      } else if (p && p.phase) {
        const labels = { starting: "Starting...", searching: "Searching Jira...", fetching_changelogs: "Fetching changelogs...", parsing: "Parsing data..." };
        el.textContent = labels[p.phase] || p.phase;
      } else {
        el.textContent = "Syncing...";
      }
      el.className = "text-muted";
    } else if (status.last_sync) {
      const d = new Date(status.last_sync);
      el.textContent = "Last sync: " + d.toLocaleString();
      el.className = "text-muted";
    } else {
      el.textContent = "Not synced yet";
      el.className = "text-muted";
    }
  },
});
