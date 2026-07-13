# Phase 10: Frontend Seamless Tab Redesign — Context

**Gathered:** 2026-07-13
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous smart-discuss)

<domain>
## Phase Boundary

Replace the `createTabs` re-render-on-switch pattern with a persistent sidebar + DOM
toggle. All four panel views (Weekly, Assigned, Insights placeholder, Config) are
mounted once and kept alive. Tab switching just shows/hides panels. A shared in-memory
store holds worklog/assigned/config data across tabs. One auto-refresh interval drives
the whole plugin. Cross-tab sync via `localStorage` + `storage` event. Store is
invalidated after mutations (log/edit/delete worklog).

Depends on Phase 9 (backend read-through cache delivers fast responses).
</domain>

<decisions>
## Implementation Decisions
- Custom sidebar in `#main` div; not modifying global `#nav`.
- Panels use existing `.tab-panel` CSS class (display:none / .active display:block).
- `_store` holds: `weekly` (last API response), `weeklyWeek`, `assigned` (list),
  `config` (object). Not a full Map — just last-fetched data, sufficient for
  no-re-fetch-on-tab-switch since backend handles read-through.
- `_dirty` flags per panel: true on init, after a data mutation, or on period elapsed.
  Panel only re-fetches when dirty.
- `setPluginBadge("jira", 0)` placeholder wired in `core.js`; real gap count wired
  in Phase 12.
- All existing features preserved: weekly view, assigned tickets, log-work/meeting
  forms, teammate search, config save, folder sync, edit/delete worklogs, time quick
  buttons, toolbar navigation.
</decisions>
</code_context>
