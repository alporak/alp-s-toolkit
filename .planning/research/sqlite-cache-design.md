# SQLite Cache Layer Design

## Database: `competence_cache.db`
Location: `app/plugins/competence_cache.db` (co-located with plugin)

## Schema

### `sync_state`
```sql
CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
)
```
Stores `last_sync` timestamp and `is_running` flag as key-value pairs.

### `transitions`
```sql
CREATE TABLE IF NOT EXISTS transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_key TEXT NOT NULL,
    transition_date TEXT NOT NULL,  -- ISO format datetime
    action_type TEXT NOT NULL CHECK(action_type IN ('ATTEMPT', 'RETURN'))
)
```

## Concurrency
Single-writer pattern: only the background sync task writes. The stats endpoint reads only. SQLite's WAL mode handles concurrent read/write safely.

## Connection Pattern
- Open connection per request (short-lived reads)
- Open connection for duration of sync (long-lived write)
- Use `sqlite3.connect()` with `check_same_thread=False` for FastAPI async context, OR use `asyncio.to_thread()` to run sync sqlite3 calls in thread pool.

## Indexing
```sql
CREATE INDEX IF NOT EXISTS idx_transitions_date ON transitions(transition_date);
CREATE INDEX IF NOT EXISTS idx_transitions_key ON transitions(ticket_key);
```

## Cache Invalidation
- Sync always fetches issues updated since `last_sync`
- Deduplication: check if a transition for same ticket_key + transition_date already exists before inserting
- Full re-sync: triggered when `last_sync` is NULL (first run)
