# Phase 11 Summary — Insights Engine

**Delivered:** 2026-07-13
**Requirements:** INS-01..09

## What shipped
- `jira_store.compute_insights()` — pure function detecting missing days, under-target weeks, low-hours, warned marked-off days, with per-day breakdown and target recalculation (40h→32h).
- `/api/jira/insights` and `/api/jira/insights/summary` endpoints with `_resolve_user` + `_daily_target_sec` helpers.
- `/api/jira/non-working-days` CRUD routes.
- Config extended with `daily_target_hours` (default 8h) and `daily_min_hours` (default 4h).
- Insights tab UI: week-vs-target bar, missing/low/warned day lists, ghost-day drill-down, historical trend (4 weeks), non-working day manager.
- 5 compute_insights unit tests covering: full week, missing/low days, short week recalculation, warned marked-off day with hours.
