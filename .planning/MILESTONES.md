# Milestones

## M4 Jira Tracker Rework (Shipped: 2026-07-13)

**Phases completed:** 6 phases, 6 plans, 32 requirements, 15 tests

**Key accomplishments:**
- Local SQLite persistence (`jira_store.py`): read-through cache with TTL + stale-serve, survives restarts
- Event-loop offload: all Jira/DB I/O wrapped in `asyncio.to_thread()`, fixing latent Windows SQLite corruption risk
- Frontend redesign: persistent sidebar (display-toggle, no re-fetch on tab switch), shared in-memory store, `localStorage` cross-tab sync
- Insights engine: ghost-day detection, under-target alerts, 40h-configurable target with non-working-day recalculation (40h→32h), historical trend
- Notifications: nav-level tab-bar badge, toggleable browser notifications (secure-context + gesture), in-app toast fallback
- TeltoHeart side-project timesheet: mark tickets, aggregate hours per person per week, multi-teammate support
- Gap-fill tools: one-click "log 8h for missed day" and "top-up short week" quick actions
- `setPluginBadge()` in `core.js` — reusable across all plugins

**Files:**
| File | Lines | Purpose |
|------|-------|---------|
| `app/plugins/jira_store.py` | ~380 | SQLite mirror + insights engine + TeltoHeart |
| `app/plugins/jira_tracker.py` | ~820 | Routes, read-through, scoped invalidation, event-loop offload |
| `app/static/js/jira.js` | ~950 | Persistent sidebar SPA + Insights + TeltoHeart + gap-fill |
| `app/static/js/core.js` | +1 | `setPluginBadge()` |
| `tests/test_jira_store.py` | ~200 | 11 store tests (schema, cache, insights) |
| `tests/test_jira_cache.py` | ~100 | 4 read-through + invalidation tests |

## M3 Documentation Search Engine (Shipped: 2026-07-02)

**Phases completed:** 3 phases, 5 plans, 8 tasks

**Key accomplishments:**
- Full-text search across 3 internal documentation repos (~3,000 files)
- SQLite FTS5 search index with 6-format text extraction
- Git sync engine with incremental updates
- Vanilla JS SPA frontend with search-as-you-type

---
