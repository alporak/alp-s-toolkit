# Performance Analytics v2 — Research

## Current State (M1 Baseline)

### SQLite Schema
```sql
sync_state(key TEXT PK, value TEXT)          -- last_sync, in_progress
transitions(id INTEGER PK, ticket_key TEXT, transition_date TEXT, action_type TEXT CHECK('ATTEMPT','RETURN'))
```

### API Endpoints
| Endpoint | Method | Returns |
|----------|--------|---------|
| `/api/competence/stats` | GET | `[{period, attempts, returns, return_rate_pct}]` 2Q grouped |
| `/api/competence/chart` | GET | HTML (Plotly bar chart) |
| `/api/competence/sync` | POST | `{status, message}` |
| `/api/competence/sync/status` | GET | `{last_sync, in_progress}` |

### Frontend
- Single bar chart (return_rate_pct by 2Q period)
- Sync Now button with polling
- Status display (last sync time)

### Data Captured Per Transition
- `ticket_key`, `transition_date`, `action_type` (ATTEMPT/RETURN)
- Missing: author of return, status names involved, ticket summary

## What Needs to Change for v2

### 1. Extended SQLite Schema
The transitions table needs expansion to capture attribution data:

```sql
-- Extended transitions table
transitions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_key TEXT NOT NULL,
    transition_date TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK(action_type IN ('ATTEMPT','RETURN')),
    author_account_id TEXT,        -- who made this transition
    author_display_name TEXT,      -- display name
    from_status TEXT,              -- status before transition
    to_status TEXT                 -- status after transition
)

-- NEW: tickets table (per-ticket metadata, refreshed on sync)
tickets(
    ticket_key TEXT PRIMARY KEY,
    summary TEXT,                  -- issue summary from Jira
    issue_type TEXT,               -- Bug, Task, Story, etc.
    last_synced TEXT               -- when this ticket's data was last refreshed
)
```

### 2. Enhanced State Machine
`_parse_changelog()` must capture per-transition:
- `author_account_id` and `author_display_name` for the RETURN author
- `from_status` and `to_status` for display context

### 3. Sync Job Enhancements
- Fetch issue `summary` and `issuetype` fields during search (add to `fields` param)
- Upsert into new `tickets` table
- Insert extended fields into `transitions`

### 4. New API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/competence/tickets` | Per-ticket breakdown: key, summary, attempts, returns, last return date, return author |
| `GET /api/competence/tickets/{key}` | Single ticket detail: all transitions with dates, authors, statuses |
| `GET /api/competence/chart/rate` | Return rate trend chart (existing, renamed) |
| `GET /api/competence/chart/volume` | Attempts vs returns volume bar/line chart |
| `GET /api/competence/chart/returns` | Returns per period stacked or breakdown chart |
| `GET /api/competence/summary` | Overall stats: total tickets, attempts, returns, rate, most returned tickets |

### 5. Frontend Architecture
Replace single-view layout with tabbed power-dashboard:

- **Tab 1: Overview** — summary cards (total tickets, attempts, returns, overall rate), return rate trend chart, attempt/return volume chart
- **Tab 2: Per-Ticket** — sortable table: ticket key, summary, attempts, returns, last return date, returned by. Click row → expand detail panel with transition timeline
- **Tab 3: Charts** — full-width charts with date range filter

### 6. Database Migration Strategy
Since M1 has existing data in `transactions` with the old schema:
- `startup()` checks schema version in `sync_state`
- If old schema detected: ALTER TABLE to add new columns (with NULL defaults for existing rows)
- If no `tickets` table: CREATE it
- Incremental — existing data preserved, new columns get NULL

### 7. Jira API Changes for v2
- Search must fetch `fields="key,summary,issuetype"` (was just "key")
- Parse changelog additions happen in `_parse_changelog()` return values
- No new Jira endpoints needed beyond what's already used
