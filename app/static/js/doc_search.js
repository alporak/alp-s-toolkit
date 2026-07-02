/* ================================================================
   Documentation Search Plugin — FTS5 full-text search SPA
   ================================================================ */
import { h, api, toast, registerPlugin, icons } from "./core.js";

// ── Constants ──────────────────────────────────────────────
const FILE_ICONS = {
  docx: "\uD83D\uDCC4",   // 📄
  pdf:  "\uD83D\uDCD1",   // 📑
  doc:  "\uD83D\uDCDD",   // 📝
  rst:  "\uD83D\uDCCB",   // 📋
  drawio: "\uD83D\uDD37", // 🔷
  graphml: "\uD83D\uDD78", // 🕸
};
const FILE_ICON_FALLBACK = "\uD83D\uDCCE"; // 📎

const REPO_COLORS = {
  "fmb-docs":       "#3B82F6",
  "teltonika":      "#10B981",
  "isp_procedures": "#F59E0B",
};
const REPO_COLOR_FALLBACK = "#6B7280";

const FILE_TYPES = ["docx", "pdf", "doc", "rst", "drawio", "graphml"];

const DEBOUNCE_MS = 250;

registerPlugin({
  id: "doc_search",
  name: "Documentation Search",
  order: 46,
  svgIcon: icons.search,

  // ── Instance state ──────────────────────────────────────
  _debounceTimer: null,
  _abortController: null,
  _activeFilters: new Set(FILE_TYPES),
  _expandedIndex: null,
  _previewEl: null,
  _focusedIndex: -1,
  _pollInterval: null,
  _searchResults: [],
  _repos: [],
  _currentQuery: "",

  // ── DOM refs (set during init) ──────────────────────────
  _searchInput: null,
  _resultsContainer: null,
  _previewContainer: null,
  _syncBtn: null,
  _syncStatus: null,
  _repoScope: null,
  _filterRow: null,
  _progressPanel: null,

  // ═══════════════════════════════════════════════════════
  //  Lifecycle
  // ═══════════════════════════════════════════════════════

  init(container) {
    container.innerHTML = "";
    this._render(container);
    this._loadRepos();
    this._loadSyncStatus();
  },

  destroy() {
    if (this._debounceTimer) clearTimeout(this._debounceTimer);
    if (this._abortController) this._abortController.abort();
    if (this._pollInterval) clearInterval(this._pollInterval);
    this._debounceTimer = null;
    this._abortController = null;
    this._pollInterval = null;
    this._expandedIndex = null;
    this._previewEl = null;
    this._focusedIndex = -1;
    this._searchResults = [];
    this._searchInput = null;
    this._resultsContainer = null;
    this._previewContainer = null;
    this._syncBtn = null;
    this._syncStatus = null;
    this._repoScope = null;
    this._filterRow = null;
    this._settingsBtn = null;
    this._progressPanel = null;
  },

  // ═══════════════════════════════════════════════════════
  //  DOM scaffold
  // ═══════════════════════════════════════════════════════

  _render(c) {
    const self = this;

    // ── Header row (search input + sync button + status) ──
    const header = h("div", {
      style: { display: "flex", gap: "12px", marginBottom: "16px", flexWrap: "wrap" },
    });

    const searchInput = h("input", {
      type: "text",
      placeholder: "Search documentation...",
      style: {
        flex: "1", minWidth: "200px", padding: "8px 12px",
        borderRadius: "6px", border: "1px solid var(--border)",
        background: "var(--bg-secondary)", color: "var(--text-primary)",
        fontSize: "14px",
      },
      oninput: () => self._onSearchInput(),
      onkeydown: (e) => self._onKeyDown(e),
    });
    this._searchInput = searchInput;

    const syncBtn = h("button", {
      className: "btn btn-primary",
      id: "doc-sync-btn",
      onclick: () => self._onSyncClick(),
    }, "Sync Now");
    this._syncBtn = syncBtn;

    const settingsBtn = h("button", {
      className: "btn btn-secondary",
      id: "doc-settings-btn",
      title: "Configure repos",
      style: { fontSize: "16px", padding: "6px 10px" },
      onclick: () => self._toggleSettings(),
    });
    settingsBtn.textContent = "\u2699"; // ⚙
    this._settingsBtn = settingsBtn;

    const syncStatus = h("span", {
      id: "doc-sync-status",
      className: "text-muted",
    }, "Checking...");
    this._syncStatus = syncStatus;

    header.appendChild(searchInput);
    header.appendChild(syncBtn);
    header.appendChild(settingsBtn);
    header.appendChild(syncStatus);
    c.appendChild(header);

    // ── Sync progress bar panel (hidden by default) ──────
    const progressPanel = h("div", {
      id: "doc-sync-progress",
      style: { display: "none", marginBottom: "16px", padding: "10px 14px", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--bg-secondary)" },
    });
    this._progressPanel = progressPanel;
    c.appendChild(progressPanel);

    // ── Settings panel (hidden by default) ────────────────
    const settingsPanel = h("div", {
      id: "doc-settings-panel",
      style: { display: "none", padding: "16px", border: "1px solid var(--border)", borderRadius: "8px", marginBottom: "16px", background: "var(--bg-secondary)" },
    });
    c.appendChild(settingsPanel);

    // ── Repo scope indicator ──────────────────────────────
    const repoScope = h("div", {
      id: "doc-repo-scope",
      className: "text-muted",
      style: { marginBottom: "12px", fontSize: "12px" },
    }, "Loading repos...");
    this._repoScope = repoScope;
    c.appendChild(repoScope);

    // ── Filter chips row ──────────────────────────────────
    const filterRow = h("div", {
      style: { display: "flex", gap: "6px", marginBottom: "12px", flexWrap: "wrap" },
    });
    for (const ft of FILE_TYPES) {
      const chip = h("button", {
        className: "btn btn-primary btn-sm",
        style: { fontSize: "12px", padding: "2px 10px" },
        "data-file-type": ft,
        onclick: () => self._onFilterToggle(ft),
      }, (FILE_ICONS[ft] || FILE_ICON_FALLBACK) + " " + ft);
      filterRow.appendChild(chip);
    }
    this._filterRow = filterRow;
    c.appendChild(filterRow);

    // ── Results container ─────────────────────────────────
    const resultsContainer = h("div", {
      id: "doc-results",
      style: { maxHeight: "60vh", overflowY: "auto" },
    });
    resultsContainer.appendChild(this._emptyState("Type to search across documentation repos..."));
    this._resultsContainer = resultsContainer;
    c.appendChild(resultsContainer);

    // ── Preview container ─────────────────────────────────
    const previewContainer = h("div", { id: "doc-preview" });
    previewContainer.style.display = "none";
    this._previewContainer = previewContainer;
    c.appendChild(previewContainer);
  },

  // ═══════════════════════════════════════════════════════
  //  Search — debounce + AbortController
  // ═══════════════════════════════════════════════════════

  _onSearchInput() {
    const self = this;
    if (this._debounceTimer) clearTimeout(this._debounceTimer);
    this._debounceTimer = setTimeout(() => {
      const value = self._searchInput ? self._searchInput.value.trim() : "";
      if (!value) {
        self._currentQuery = "";
        self._searchResults = [];
        self._clearResults();
        self._resultsContainer.appendChild(self._emptyState("Type to search across documentation repos..."));
        return;
      }
      self._currentQuery = value;
      self._doSearch(value);
    }, DEBOUNCE_MS);
  },

  async _doSearch(query) {
    // Abort any in-flight request
    if (this._abortController) this._abortController.abort();
    this._abortController = new AbortController();

    // Show loading spinner
    this._clearResults();
    this._closePreview();
    this._resultsContainer.appendChild(this._loadingState());

    try {
      const data = await api(
        "/api/doc_search/search?q=" + encodeURIComponent(query),
        { signal: this._abortController.signal },
      );
      this._searchResults = data.results || [];
      this._clearResults();

      if (!this._searchResults.length) {
        this._resultsContainer.appendChild(
          this._emptyState("No results found for '" + query + "'"),
        );
      } else {
        // Result count header
        this._resultsContainer.appendChild(
          h("div", {
            style: { fontSize: "12px", color: "var(--text-muted)", marginBottom: "8px" },
          }, this._searchResults.length + " result" + (this._searchResults.length !== 1 ? "s" : "") + " for '" + query + "'"),
        );
        // Render each result
        for (let i = 0; i < this._searchResults.length; i++) {
          const item = this._renderResultItem(this._searchResults[i], query, i);
          this._resultsContainer.appendChild(item);
        }
      }
      this._resultsContainer.scrollTop = 0;
      this._focusedIndex = -1;
    } catch (e) {
      // Aborted requests are expected — don't show error
      if (e && e.name === "AbortError") return;
      // api() already toasts the error; show error state in results
      this._clearResults();
      this._resultsContainer.appendChild(
        h("div", {
          style: { padding: "24px", textAlign: "center", color: "var(--text-muted)" },
        }, "Search failed. Please try again."),
      );
    }
  },

  // ═══════════════════════════════════════════════════════
  //  Result rendering (safe DOM — no innerHTML for content)
  // ═══════════════════════════════════════════════════════

  _renderResultItem(result, query, index) {
    const self = this;
    const fileType = result.file_type || "";
    const icon = FILE_ICONS[fileType] || FILE_ICON_FALLBACK;

    // Repo badge color
    const badgeColor = REPO_COLORS[result.repo] || REPO_COLOR_FALLBACK;

    // Build snippet with term highlighting
    const snippetFrag = this._highlightTerms(result.snippet || "", query);

    // needs_ocr warning
    if (result.needs_ocr) {
      const warnSpan = h("span", {
        style: { color: "#F59E0B", fontSize: "11px", marginLeft: "6px" },
        title: "This PDF may contain scanned images",
      });
      warnSpan.textContent = " \u26A0 scanned"; // ⚠ scanned
      snippetFrag.appendChild(warnSpan);
    }

    const row = h("div", {
      "data-file-type": fileType,
      "data-result-index": String(index),
      style: {
        padding: "10px", borderBottom: "1px solid var(--border)",
        cursor: "pointer", transition: "background 0.15s",
      },
      onclick: (e) => self._onResultClick(index, e),
      onmouseenter: function () { if (self._focusedIndex !== index) this.style.background = "var(--bg-secondary)"; },
      onmouseleave: function () { if (self._focusedIndex !== index) this.style.background = ""; },
    });

    // Top row: icon + filename + path
    const topRow = h("div", {
      style: { display: "flex", alignItems: "flex-start", gap: "8px", marginBottom: "4px" },
    });

    // Icon + filename + relative path
    const left = h("div", {
      style: { flex: "1", minWidth: 0 },
    });

    const nameLine = h("div", {
      style: { display: "flex", alignItems: "center", gap: "8px" },
    });

    const iconSpan = h("span", { style: { fontSize: "16px", flexShrink: 0 } });
    iconSpan.textContent = icon;
    nameLine.appendChild(iconSpan);

    const nameSpan = h("span", { style: { fontWeight: "600" } });
    nameSpan.textContent = result.filename || "";
    nameLine.appendChild(nameSpan);

    // Repo badge
    const badge = h("span", {
      style: {
        background: badgeColor, color: "#fff", padding: "1px 8px",
        borderRadius: "10px", fontSize: "11px", fontWeight: "600", flexShrink: 0,
      },
    });
    badge.textContent = result.repo || "";
    nameLine.appendChild(badge);

    left.appendChild(nameLine);

    // Relative path below filename
    if (result.path && result.path !== result.filename) {
      const pathLine = h("div", {
        style: { marginTop: "2px", fontSize: "11px", color: "var(--text-muted)", wordBreak: "break-all" },
      });
      pathLine.textContent = result.path;
      left.appendChild(pathLine);
    }

    // Score (right side)
    const score = h("span", {
      style: { color: "var(--text-muted)", fontSize: "11px", flexShrink: 0, marginLeft: "auto" },
    });
    score.textContent = typeof result.score === "number" ? result.score.toFixed(2) : "";

    topRow.appendChild(left);
    topRow.appendChild(score);
    row.appendChild(topRow);

    // Snippet line
    const snippetLine = h("div", {
      style: { marginTop: "4px", fontSize: "13px", color: "var(--text-muted)" },
    });
    snippetLine.appendChild(snippetFrag);
    row.appendChild(snippetLine);

    return row;
  },

  /**
   * Build a DocumentFragment where occurrences of each word in *query*
   * are wrapped in <mark> elements created via document.createElement.
   * Uses textContent + createTextNode — zero innerHTML for user content.
   */
  _highlightTerms(text, query) {
    const frag = document.createDocumentFragment();
    if (!query || !text) {
      frag.appendChild(document.createTextNode(text));
      return frag;
    }

    // Extract unique words from query (split on whitespace, strip punctuation)
    const words = [...new Set(
      query.toLowerCase().split(/\s+/).map(w => w.replace(/[^a-z0-9]/g, "")).filter(Boolean),
    )];

    if (!words.length) {
      frag.appendChild(document.createTextNode(text));
      return frag;
    }

    // Build a regex that matches any of the words (case-insensitive)
    const escaped = words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const pattern = new RegExp("(" + escaped.join("|") + ")", "gi");

    const parts = text.split(pattern);
    for (const part of parts) {
      if (!part) continue;
      const isMatch = words.some(w => part.toLowerCase() === w);
      if (isMatch) {
        const mark = document.createElement("mark");
        mark.textContent = part;
        frag.appendChild(mark);
      } else {
        frag.appendChild(document.createTextNode(part));
      }
    }

    return frag;
  },

  // ═══════════════════════════════════════════════════════
  //  Preview accordion
  // ═══════════════════════════════════════════════════════

  _onResultClick(index, event) {
    // Don't trigger on keyboard events that already handled it
    if (event && event.detail === 0) return;

    if (this._expandedIndex === index) {
      // Collapse
      this._closePreview();
      return;
    }

    // Collapse any existing preview
    if (this._expandedIndex !== null) {
      this._closePreview();
    }

    const result = this._searchResults[index];
    if (!result) return;

    // Insert loading spinner after the clicked result row
    const resultRow = this._resultsContainer.querySelector('[data-result-index="' + index + '"]');
    if (!resultRow) return;

    this._expandedIndex = index;

    const loadingDiv = h("div", {
      className: "spinner",
      style: { margin: "8px 0 8px 28px" },
    });
    resultRow.insertAdjacentElement("afterend", loadingDiv);

    // Fetch preview
    this._loadPreview(result.repo, result.path, index, resultRow, loadingDiv);
  },

  async _loadPreview(repo, path, index, resultRow, loadingDiv) {
    const self = this;
    try {
      const data = await api(
        "/api/doc_search/preview/" + encodeURIComponent(repo) + "/" + encodeURIComponent(path),
      );

      // Remove loading spinner
      if (loadingDiv && loadingDiv.parentNode) loadingDiv.remove();

      // Check if another preview was opened while fetching
      if (this._expandedIndex !== index) return;

      // Build preview panel
      const MAX_PREVIEW = 5000;
      const text = data.text || "";
      const html = data.html || "";
      const truncated = text.length > MAX_PREVIEW || html.length > MAX_PREVIEW * 2;
      const displayText = truncated ? text.substring(0, MAX_PREVIEW) : text;

      const result = this._searchResults[index];
      const filename = result ? result.filename : "";
      const repoName = result ? result.repo : "";
      const filePath = result ? result.path : "";

      const previewPanel = h("div", {
        style: {
          marginLeft: "28px", padding: "10px 14px",
          background: "var(--bg-secondary)", borderRadius: "6px",
          borderLeft: "3px solid var(--accent)", fontSize: "13px",
          maxHeight: "350px", overflowY: "auto", marginBottom: "8px",
        },
      });

      // Header with filename + "Open file" button
      const headerRow = h("div", {
        style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" },
      });

      const titleText = h("span", {
        style: { fontWeight: "600", fontSize: "12px", color: "var(--text-primary)" },
      });
      titleText.textContent = filename;
      headerRow.appendChild(titleText);

      // "Open file" button — launches native app via os.startfile()
      const openBtn = h("button", {
        className: "btn btn-primary btn-sm",
        style: { fontSize: "11px", padding: "2px 10px", marginLeft: "auto" },
        onclick: async (e) => {
          e.stopPropagation();
          try {
            const url = "/api/doc_search/open/" + encodeURIComponent(repoName) + "/" + encodeURIComponent(filePath);
            const resp = await api(url, { method: "POST" });
            if (resp.status === "opened") {
              toast("Opened in default app", "success", 1500);
            }
          } catch (err) {
            // api() already toasts errors
          }
        },
      }, "Open file");
      headerRow.appendChild(openBtn);

      previewPanel.appendChild(headerRow);

      // Full file path below header
      const pathLine = h("div", {
        style: { fontSize: "11px", color: "var(--text-muted)", marginBottom: "8px", wordBreak: "break-all" },
      });
      pathLine.textContent = filePath;
      previewPanel.appendChild(pathLine);

      // Rendered content — use HTML if available, otherwise plain text with highlights
      if (html) {
        const htmlDiv = h("div", {
          style: { lineHeight: "1.6" },
        });
        // XSS-safe: all HTML was generated server-side from docx (no user input)
        htmlDiv.innerHTML = html;
        previewPanel.appendChild(htmlDiv);
      } else {
        const textFrag = this._highlightTerms(displayText, this._currentQuery);
        const textDiv = h("div", { style: { whiteSpace: "pre-wrap", lineHeight: "1.5" } });
        textDiv.appendChild(textFrag);
        previewPanel.appendChild(textDiv);
      }

      // "Show more" indicator if truncated
      if (truncated) {
        const moreDiv = h("div", {
          style: { fontSize: "11px", color: "var(--text-muted)", marginTop: "8px", fontStyle: "italic" },
        }, "Showing first " + MAX_PREVIEW.toLocaleString() + " chars — use \"Open file\" for full content");
        previewPanel.appendChild(moreDiv);
      }

      // Insert after result row
      resultRow.insertAdjacentElement("afterend", previewPanel);
      this._previewEl = previewPanel;

      // Scroll into view
      previewPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) {
      // Aborted — ignore
      if (e && e.name === "AbortError") return;
      if (loadingDiv && loadingDiv.parentNode) loadingDiv.remove();
      if (this._expandedIndex !== index) return;

      // Show error preview
      const errorPanel = h("div", {
        style: {
          marginLeft: "28px", padding: "10px 14px",
          background: "var(--bg-secondary)", borderRadius: "6px",
          borderLeft: "3px solid #e74c3c", fontSize: "13px",
          marginBottom: "8px", color: "var(--text-muted)",
        },
      }, "Preview unavailable");
      resultRow.insertAdjacentElement("afterend", errorPanel);
      this._previewEl = errorPanel;
    }
  },

  _closePreview() {
    if (this._previewEl && this._previewEl.parentNode) {
      this._previewEl.remove();
    }
    this._previewEl = null;
    this._expandedIndex = null;
    this._removeFocusClass();
  },

  // ═══════════════════════════════════════════════════════
  //  File-type filter chips
  // ═══════════════════════════════════════════════════════

  _onFilterToggle(type) {
    if (this._activeFilters.has(type)) {
      this._activeFilters.delete(type);
    } else {
      this._activeFilters.add(type);
    }
    // Update chip appearance
    const chip = this._filterRow ? this._filterRow.querySelector('[data-file-type="' + type + '"]') : null;
    if (chip) {
      if (this._activeFilters.has(type)) {
        chip.className = "btn btn-primary btn-sm";
      } else {
        chip.className = "btn btn-outline btn-sm";
      }
    }
    // Apply filters to visible results
    this._applyFilters();
  },

  _applyFilters() {
    const rows = this._resultsContainer.querySelectorAll("[data-file-type]");
    const allActive = this._activeFilters.size === 0 || this._activeFilters.size === FILE_TYPES.length;

    for (const row of rows) {
      const ft = row.getAttribute("data-file-type") || "";
      if (allActive || this._activeFilters.has(ft)) {
        row.style.display = "";
      } else {
        row.style.display = "none";
      }
    }
  },

  // ═══════════════════════════════════════════════════════
  //  Keyboard navigation
  // ═══════════════════════════════════════════════════════

  _onKeyDown(e) {
    // Only handle when results are showing
    if (!this._searchResults.length) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        this._focusNext();
        break;
      case "ArrowUp":
        e.preventDefault();
        this._focusPrev();
        break;
      case "Enter":
        if (this._focusedIndex >= 0) {
          e.preventDefault();
          // Trigger click on focused result
          this._onResultClick(this._focusedIndex, { detail: 0 });
        }
        break;
      case "Escape":
        e.preventDefault();
        this._handleEscape();
        break;
    }
  },

  _focusNext() {
    const total = this._searchResults.length;
    if (!total) return;

    this._removeFocusClass();
    this._focusedIndex = (this._focusedIndex + 1) % total;
    this._addFocusClass();
  },

  _focusPrev() {
    const total = this._searchResults.length;
    if (!total) return;

    this._removeFocusClass();
    this._focusedIndex = this._focusedIndex <= 0 ? -1 : this._focusedIndex - 1;

    if (this._focusedIndex >= 0) {
      this._addFocusClass();
    } else if (this._searchInput) {
      this._searchInput.focus();
    }
  },

  _addFocusClass() {
    const row = this._resultsContainer.querySelector(
      '[data-result-index="' + this._focusedIndex + '"]',
    );
    if (row) {
      row.classList.add("doc-result-focused");
      row.style.outline = "2px solid var(--accent)";
      row.style.outlineOffset = "-2px";
      row.style.borderRadius = "4px";
      row.scrollIntoView({ block: "nearest" });
    }
  },

  _removeFocusClass() {
    if (this._focusedIndex < 0) return;
    const row = this._resultsContainer.querySelector(
      '[data-result-index="' + this._focusedIndex + '"]',
    );
    if (row) {
      row.classList.remove("doc-result-focused");
      row.style.outline = "";
      row.style.outlineOffset = "";
      row.style.borderRadius = "";
    }
  },

  _handleEscape() {
    if (this._expandedIndex !== null) {
      // Close preview
      this._closePreview();
    } else if (this._focusedIndex >= 0) {
      // Remove focus from results
      this._removeFocusClass();
      this._focusedIndex = -1;
    } else {
      // Clear search
      if (this._searchInput) {
        this._searchInput.value = "";
        this._searchInput.focus();
      }
      this._currentQuery = "";
      this._searchResults = [];
      this._clearResults();
      this._resultsContainer.appendChild(
        this._emptyState("Type to search across documentation repos..."),
      );
    }
  },

  // ═══════════════════════════════════════════════════════
  //  Sync controls
  // ═══════════════════════════════════════════════════════

  async _onSyncClick() {
    const self = this;
    const btn = this._syncBtn;
    if (!btn) return;

    const origText = btn.textContent || "Sync Now";
    btn.disabled = true;
    btn.textContent = "Syncing...";

    try {
      const data = await api("/api/doc_search/sync", { method: "POST" });

      if (data.status === "sync_already_running") {
        toast("Sync already in progress", "info");
        self._startPolling();
        return;
      }

      // sync_started
      toast("Sync started", "success");
      self._startPolling();
    } catch (e) {
      // api() already toasts
      btn.disabled = false;
      btn.textContent = origText;
    }
  },

  _startPolling() {
    const self = this;
    if (this._pollInterval) clearInterval(this._pollInterval);

    // Poll immediately
    this._pollSyncStatus();

    this._pollInterval = setInterval(() => {
      self._pollSyncStatus();
    }, 2000);
  },

  async _pollSyncStatus() {
    const self = this;
    try {
      const status = await api("/api/doc_search/sync/status");
      self._updateSyncStatus(status);
    } catch (e) {
      // Non-critical — polling will retry
      console.error("[DocSearch] Sync status poll failed:", e.message);
    }
  },

  _updateSyncStatus(status) {
    const el = this._syncStatus;
    if (!el) return;

    if (status.in_progress) {
      const p = status.progress;
      let phase = "Syncing";
      let detail = "";
      let done = 0;
      let total = 0;

      if (p) {
        if (p.phase === "pulling") {
          phase = "Pulling";
          detail = p.repo || "";
        } else if (p.phase === "indexing") {
          phase = "Indexing";
          detail = p.repo || "";
          done = p.done || 0;
          total = p.total || 0;
        } else if (p.phase === "starting") {
          phase = "Preparing";
        }
      }

      // Build fluently: "Indexing fmb-docs · 124/230 files"
      let text = phase;
      if (detail) text += " " + detail;
      if (total > 0) text += " \u00b7 " + done + "/" + total + " files";
      el.textContent = text;
      el.className = "";

      // Show progress bar panel
      this._showProgressPanel(phase, detail, done, total);

      // Keep button in syncing state
      if (this._syncBtn) {
        this._syncBtn.disabled = true;
        this._syncBtn.textContent = "Syncing...";
      }
    } else {
      // Sync complete — hide progress panel
      this._hideProgressPanel();

      if (this._pollInterval) {
        clearInterval(this._pollInterval);
        this._pollInterval = null;
      }

      if (this._syncBtn) {
        this._syncBtn.disabled = false;
        this._syncBtn.textContent = "Sync Now";
      }

      if (status.last_sync) {
        const d = new Date(status.last_sync);
        el.textContent = "Last sync: " + d.toLocaleString();
        el.className = "text-muted";
      } else {
        el.textContent = "Not synced yet";
        el.className = "text-muted";
      }

      // Toast on completion (only if we were previously syncing)
      if (this._wasSyncing) {
        toast("Sync complete", "success");
      }
    }
    this._wasSyncing = status.in_progress;
  },

  _showProgressPanel(phase, repo, done, total) {
    const panel = this._progressPanel;
    if (!panel) return;
    panel.style.display = "block";
    panel.innerHTML = "";

    const pct = total > 0 ? Math.round((done / total) * 100) : 0;

    // Phase line: "Indexing fmb-docs"
    const phaseLine = h("div", {
      style: { fontSize: "13px", fontWeight: "600", marginBottom: "6px", color: "var(--text-primary)" },
    }, phase + (repo ? " " + repo : ""));

    // Progress bar
    const barOuter = h("div", {
      style: { height: "8px", borderRadius: "4px", background: "var(--bg-primary)", overflow: "hidden", marginBottom: "6px" },
    });
    const barInner = h("div", {
      style: {
        height: "100%", width: pct + "%", borderRadius: "4px",
        background: "var(--accent, #3B82F6)",
        transition: "width 0.4s ease",
      },
    });
    barOuter.appendChild(barInner);

    // Count line: "124 / 230 files"
    const countLine = h("div", {
      style: { fontSize: "12px", color: "var(--text-muted)" },
    });
    if (total > 0) {
      countLine.textContent = done + " / " + total + " files" + (pct > 0 ? " \u00b7 " + pct + "%" : "");
    } else {
      countLine.textContent = "\u2026";
    }

    panel.appendChild(phaseLine);
    panel.appendChild(barOuter);
    panel.appendChild(countLine);
  },

  _hideProgressPanel() {
    if (this._progressPanel) {
      this._progressPanel.style.display = "none";
    }
  },

  async _loadSyncStatus() {
    try {
      const status = await api("/api/doc_search/sync/status");
      this._updateSyncStatus(status);
      if (status.in_progress) {
        this._startPolling();
      }
    } catch (e) {
      console.error("[DocSearch] Load sync status failed:", e.message);
    }
  },

  // ═══════════════════════════════════════════════════════
  //  Repo scope indicator
  // ═══════════════════════════════════════════════════════

  async _loadRepos() {
    const el = this._repoScope;
    if (!el) return;

    try {
      const repos = await api("/api/doc_search/repos");
      this._repos = repos || [];
      el.innerHTML = "";

      if (!repos || !repos.length) {
        el.innerHTML = "";
        const self = this;
        el.appendChild(document.createTextNode("0 repos configured \u2014 "));
        const btn = h("button", {
          className: "btn btn-primary btn-sm",
          style: { fontSize: "11px", padding: "2px 10px", marginLeft: "6px", cursor: "pointer" },
          onclick: () => self._toggleSettings(),
        }, "\u2699 Configure");
        el.appendChild(btn);
        return;
      }

      const totalFiles = repos.reduce((sum, r) => sum + (r.file_count || 0), 0);
      const labelSpan = h("span", null, "Searching " + repos.length + " repo" + (repos.length !== 1 ? "s" : "") + ": ");
      el.appendChild(labelSpan);

      for (let i = 0; i < repos.length; i++) {
        const r = repos[i];
        const color = REPO_COLORS[r.name] || REPO_COLOR_FALLBACK;
        const badge = h("span", {
          style: {
            background: color, color: "#fff", padding: "1px 6px",
            borderRadius: "8px", fontSize: "11px", fontWeight: "600",
            marginLeft: i > 0 ? "4px" : "0",
          },
        });
        badge.textContent = r.name + " (" + (r.file_count || 0) + " file" + (r.file_count !== 1 ? "s" : "") + ")";
        el.appendChild(badge);
        if (i < repos.length - 1) {
          el.appendChild(document.createTextNode(", "));
        }
      }

      // If all repos have 0 files, show "Index building" hint
      if (totalFiles === 0) {
        const hintDiv = h("div", {
          style: { marginTop: "6px", fontSize: "12px", color: "var(--text-muted)" },
        }, "Index building... Click Sync Now to index documentation");
        el.appendChild(hintDiv);
      }
    } catch (e) {
      console.error("[DocSearch] Load repos failed:", e.message);
      el.textContent = "Could not load repo list";
    }
  },

  // ═══════════════════════════════════════════════════════
  //  Helpers — empty / loading states
  // ═══════════════════════════════════════════════════════

  _emptyState(msg) {
    return h("div", { className: "empty" },
      h("div", { className: "empty-icon" }, "\u2014"),
      h("p", null, msg),
    );
  },

  _loadingState() {
    return h("div", {
      style: { textAlign: "center", padding: "24px", color: "var(--text-muted)" },
    },
      h("div", { className: "spinner" }),
      h("p", { style: { marginTop: "8px" } }, "Searching..."),
    );
  },

  _clearResults() {
    if (this._resultsContainer) {
      this._resultsContainer.innerHTML = "";
    }
    this._closePreview();
  },

  // ═══════════════════════════════════════════════════════
  //  Settings panel — repo configuration
  // ═══════════════════════════════════════════════════════

  _toggleSettings() {
    const panel = document.getElementById("doc-settings-panel");
    const results = this._resultsContainer;
    const gear = document.getElementById("doc-settings-btn");
    if (!panel || !results) return;

    const open = panel.style.display !== "none";
    if (open) {
      panel.style.display = "none";
      results.style.display = "";
      if (gear) gear.textContent = "\u2699"; // ⚙
      return;
    }
    panel.style.display = "block";
    results.style.display = "none";
    if (gear) gear.textContent = "\u2715"; // ✕
    this._renderSettingsPanel();
  },

  async _renderSettingsPanel() {
    const panel = document.getElementById("doc-settings-panel");
    if (!panel) return;
    panel.innerHTML = "";

    // Load current settings
    let repos = [];
    try {
      const settings = await api("/api/settings");
      repos = settings.doc_repos || [];
    } catch (e) {
      panel.textContent = "Failed to load settings";
      return;
    }

    const self = this;

    const title = h("h3", { style: { marginBottom: "12px" } }, "Repository Configuration");
    panel.appendChild(title);

    // Existing repos list
    if (!repos.length) {
      panel.appendChild(h("p", { className: "text-muted", style: { marginBottom: "16px" } }, "No repos configured yet. Add at least one to enable search."));
    } else {
      const list = h("div", { style: { marginBottom: "16px" } });
      for (let i = 0; i < repos.length; i++) {
        const r = repos[i];
        const color = REPO_COLORS[r.name] || REPO_COLOR_FALLBACK;
        const row = h("div", {
          style: {
            display: "flex", alignItems: "center", gap: "8px",
            padding: "8px", border: "1px solid var(--border)", borderRadius: "6px",
            marginBottom: "6px",
          },
        });
        const badge = h("span", {
          style: { background: color, color: "#fff", padding: "2px 8px", borderRadius: "8px", fontSize: "12px", fontWeight: "600" },
        });
        badge.textContent = r.name;
        row.appendChild(badge);

        const pathSpan = h("span", {
          style: { flex: "1", fontSize: "12px", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
        });
        pathSpan.textContent = r.path || "";
        row.appendChild(pathSpan);

        const delBtn = h("button", {
          className: "btn btn-danger btn-sm",
          style: { fontSize: "11px", padding: "2px 8px" },
          onclick: (function (idx) { return function () { self._removeRepo(idx); }; })(i),
        }, "Remove");
        row.appendChild(delBtn);

        list.appendChild(row);
      }
      panel.appendChild(list);
    }

    // Add repo form
    const formTitle = h("h4", { style: { marginBottom: "8px" } }, repos.length ? "Add another repo" : "Add a repo");
    panel.appendChild(formTitle);

    const form = h("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "8px" } });

    const nameInput = h("input", {
      type: "text", id: "doc-repo-name",
      placeholder: "Repo name (e.g. fmb-docs)",
      style: { flex: "1", minWidth: "140px", padding: "6px 10px", borderRadius: "6px", border: "1px solid var(--border)", background: "var(--bg-secondary)", color: "var(--text-primary)", fontSize: "13px" },
    });
    form.appendChild(nameInput);

    const pathInput = h("input", {
      type: "text", id: "doc-repo-path",
      placeholder: "C:\\Users\\...\\repo-path",
      style: { flex: "2", minWidth: "200px", padding: "6px 10px", borderRadius: "6px", border: "1px solid var(--border)", background: "var(--bg-secondary)", color: "var(--text-primary)", fontSize: "13px" },
    });
    form.appendChild(pathInput);

    const addBtn = h("button", {
      className: "btn btn-primary btn-sm",
      style: { padding: "6px 16px" },
      onclick: () => self._addRepo(),
    }, "Add");
    form.appendChild(addBtn);

    panel.appendChild(form);

    // Help text
    panel.appendChild(h("p", { className: "text-muted", style: { fontSize: "11px", marginTop: "8px" } }, "Repos must be accessible git repositories on your local machine or network. Click Sync Now after saving to index the documentation."));
  },

  async _addRepo() {
    const nameEl = document.getElementById("doc-repo-name");
    const pathEl = document.getElementById("doc-repo-path");
    const name = (nameEl ? nameEl.value.trim() : "");
    const path = (pathEl ? pathEl.value.trim() : "");

    if (!name || !path) {
      toast("Repo name and path are required", "error");
      return;
    }

    let repos = [];
    try {
      const settings = await api("/api/settings");
      repos = settings.doc_repos || [];
    } catch (e) { return; }

    // Check for duplicate name
    if (repos.some(r => r.name === name)) {
      toast("A repo named '" + name + "' already exists", "error");
      return;
    }

    repos.push({ name: name, path: path });
    await this._saveRepos(repos);

    if (nameEl) nameEl.value = "";
    if (pathEl) pathEl.value = "";
    toast("Repo '" + name + "' added. Click Sync Now to index.", "success");
    this._renderSettingsPanel();
    this._loadRepos();
  },

  async _removeRepo(index) {
    let repos = [];
    try {
      const settings = await api("/api/settings");
      repos = settings.doc_repos || [];
    } catch (e) { return; }

    const removed = repos[index] && repos[index].name || "repo";
    repos.splice(index, 1);
    await this._saveRepos(repos);

    toast("Removed '" + removed + "'", "info");
    this._renderSettingsPanel();
    this._loadRepos();
  },

  async _saveRepos(repos) {
    try {
      await api("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_repos: repos }),
      });
    } catch (e) {
      toast("Failed to save settings", "error");
      throw e;
    }
  },
});
