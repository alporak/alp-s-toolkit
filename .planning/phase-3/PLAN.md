---
phase: 03-competence-v2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - app/plugins/competence.py
autonomous: true
requirements:
  - FR7
  - FR8
  - FR9
  - FR10
  - NFR7
  - NFR8
  - NFR9
user_setup: []

must_haves:
  truths:
    - "On startup, old transitions/tickets tables are DROPped and recreated with extended schema (D-01, D-02, D-03)"
    - "_parse_changelog() returns transitions with author_account_id, author_display_name, from_status, to_status (D-04)"
    - "Sync job fetches key+summary+issuetype from Jira, upserts into tickets table, stores extended transition columns (D-05)"
    - "GET /api/competence/stats returns 2Q grouped data from extended schema — existing endpoint preserved (D-07)"
    - "GET /api/competence/chart returns Plotly HTML bar chart — existing endpoint preserved (D-07)"
    - "POST /api/competence/sync triggers background sync — existing endpoint preserved (D-07)"
    - "GET /api/competence/sync/status returns last_sync + in_progress — existing endpoint preserved (D-07)"
    - "GET /api/competence/tickets returns per-ticket aggregated stats with SQL GROUP BY (D-06, FR10.1)"
    - "GET /api/competence/tickets/{key} returns single-ticket transition timeline with attribution (D-06, FR10.2)"
    - "GET /api/competence/chart/volume returns Plotly dual-bar attempts vs returns chart (D-06, FR10.3)"
    - "GET /api/competence/summary returns overall aggregates + top-5 most_returned tickets (D-06, D-08, FR10.4)"
    - "All 8 endpoints respond correctly, sync populates extended columns, attribution visible in API responses"
  artifacts:
    - path: "app/plugins/competence.py"
      provides: "Full rewrite: CompetencePlugin with extended schema, enhanced parser, 8 API endpoints"
      min_lines: 700
    - path: "app/plugins/competence_cache.db"
      provides: "Auto-created at startup with extended transitions + tickets tables"
  key_links:
    - from: "_parse_changelog() return dicts"
      to: "INSERT INTO transitions (extended columns)"
      via: "sync job insertion loop"
      pattern: "author_account_id|author_display_name|from_status|to_status"
    - from: "jira.search_issues()"
      to: "tickets table"
      via: "_upsert_ticket() INSERT OR REPLACE"
      pattern: "INSERT OR REPLACE INTO tickets"
    - from: "GET /api/competence/tickets"
      to: "transitions LEFT JOIN tickets"
      via: "SQL GROUP BY with subquery for last_return_by"
      pattern: "GROUP BY ticket_key"
    - from: "GET /api/competence/chart/volume"
      to: "go.Figure([go.Bar(...), go.Bar(...)])"
      via: "fig.to_html(include_plotlyjs=\"cdn\")"
      pattern: "barmode.*group"
    - from: "GET /api/competence/summary"
      to: "_load_transitions_df() + tickets COUNT"
      via: "aggregate computation"
      pattern: "most_returned"
---

<objective>
Rewrite `app/plugins/competence.py` (593 lines, M1) as production-quality code with an extended data model (8-column transitions + new tickets table) and 4 new API endpoints, while preserving all 4 M1 endpoints unchanged. The rewrite uses DROP+CREATE on startup (no migration — M1 data is test data that sync refetches) per D-01, and requires zero new package dependencies per D-09.

Purpose: Phase 4 (Frontend Power-Dashboard) depends on these new endpoints. The extended schema captures per-transition attribution (who returned, from/to statuses) enabling the Phase 4 Per-Ticket tab and summary cards. All infrastructure patterns (Jira client, HTTP client, semaphore concurrency, SQLite WAL, pandas aggregation, Plotly rendering) are retained from the proven M1 codebase per RESEARCH.md.

Output: One rewritten file (`app/plugins/competence.py`, ~750 lines) with 8 API endpoints, extended schema bootstrapped at startup, and end-to-end data flow from Jira → changelog parse → SQLite → API response.
</objective>

<execution_context>
@C:\Users\orak.al\OneDrive - teltonika.lt\alp_work_files\various_repos\alps-toolkit\.planning\phase-3\RESEARCH.md
@C:\Users\orak.al\OneDrive - teltonika.lt\alp_work_files\various_repos\alps-toolkit\.planning\phase-3\PATTERNS.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/research/v2-architecture.md
@app/plugins/competence.py
</context>

<read_first>
## Source files to study before implementation

1. `app/plugins/competence.py` (593 lines) — full M1 source. All existing patterns to be preserved: module-level state (§3), Jira client factory (§2), HTTP helpers (§3), pandas helpers, register_routes closure pattern.
2. `.planning/phase-3/RESEARCH.md` (730 lines) — full code examples for every component: startup() DDL, extended _parse_changelog(), sync job with ticket metadata fetch, all 4 new endpoint implementations, SQL queries, Plotly config.
3. `.planning/phase-3/PATTERNS.md` (1218 lines) — 8/8 pattern analogs mapped from existing codebase. Section references below map to PATTERNS.md section numbers.

## Key architecture decisions (locked — do not revisit)

- **D-01**: Clean rewrite with DROP+CREATE in startup(). No ALTER TABLE, no migration code, no data preservation. M1's 22 test rows are discarded; sync refetches everything from Jira. Sets `schema_version=2` in sync_state for future migration detection.
- **D-02**: Extended `transitions` table adds 4 new columns: `author_account_id TEXT`, `author_display_name TEXT`, `from_status TEXT`, `to_status TEXT` — all NOT NULL DEFAULT ''.
- **D-03**: New `tickets` table: `ticket_key TEXT PRIMARY KEY`, `summary TEXT`, `issue_type TEXT`, `last_synced TEXT`.
- **D-04**: `_parse_changelog()` signature changes: removes `current_account_id` parameter (team-wide tracking — any author), returns dicts with `author_account_id`, `author_display_name`, `from_status`, `to_status` per transition.
- **D-05**: Sync job `search_issues()` extends `fields` param from `"key"` to `"key,summary,issuetype"`. Upserts ticket metadata into `tickets` table via INSERT OR REPLACE.
- **D-06**: Four new endpoints added inside `register_routes()`: `GET /tickets`, `GET /tickets/{key}`, `GET /chart/volume`, `GET /summary`.
- **D-07**: All M1 endpoints preserved unchanged at their existing paths: `/stats`, `/chart`, `/sync`, `/sync/status`.
- **D-08**: `/summary` endpoint returns top 5 most_returned tickets (not just ties for #1).
- **D-09**: No new packages needed. All dependencies (jira, httpx, pandas, plotly, fastapi) already in requirements.txt.

## PATTERNS.md quick-reference (section numbers)

All code excerpts below are abbreviated pointers — fetch full implementations from PATTERNS.md sections:
- §1: Plugin class skeleton (unchanged: id/name/icon/order, register_routes, startup, shutdown)
- §2: Jira client factory `_get_jira_client()` — KEEP AS-IS. Add JIRAError wrappers in new endpoints.
- §3: HTTP client helpers (`_get_client`, `_api_get`, `_api_post`, `_close_client`) — KEEP AS-IS.
- §4: Schema — full DROP+CREATE DDL with extended columns + tickets table. See RESEARCH.md lines 527-590 for exact code.
- §5: State machine parser — enhanced `_parse_changelog()` with attribution fields. See RESEARCH.md lines 329-395 for exact code.
- §6: Sync job — enhanced with parallel ticket metadata fetch + extended column insert. See RESEARCH.md lines 396-455 for exact code.
- §7: Endpoints — existing 4 kept as-is (§7a-b), 4 new added (§7c-f). See RESEARCH.md lines 456-1011 for exact code.
- §8: register_routes closure pattern — add 4 new route handlers after existing 4.

## Codebase conventions (from competence.py + release_creator.py)

- Route naming: `/api/{plugin.id}/{resource}[/{param}]` — all under `competence` prefix.
- All route handlers are `async def` closures inside `register_routes()`.
- Error handling: 3-tier — `JIRAError` (from jira package) → `HTTPException` from httpx (re-raise) → `Exception` catch-all → `HTTPException(500, str(e))`.
- Chart endpoints: `response_class=HTMLResponse`, return `fig.to_html(include_plotlyjs="cdn", full_html=False)`.
- DB access: synchronous helpers wrapped in `asyncio.to_thread()` for async context. `_db_lock` guards all writes.
- WAL mode: `PRAGMA journal_mode=WAL` in `_get_db()`. Reads need no lock; writes use `_db_lock`.
- Module-level singleton: `plugin = CompetencePlugin()` at file bottom.
</read_first>

<tasks>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- WAVE 1: Fresh schema (DROP+CREATE)                            -->
<!-- ═══════════════════════════════════════════════════════════════ -->

<task type="auto">
  <name>Task 1: Rewrite startup() — fresh DROP+CREATE schema (D-01, D-02, D-03)</name>
  <files>app/plugins/competence.py</files>
  <action>
Replace the existing `startup()` method (lines 549-580) with a schema-version-checked DROP+CREATE based on PATTERNS.md §4 and RESEARCH.md lines 527-590.

Implementation:
1. Keep the outer `try/except` and `_db_lock` pattern from the existing startup().
2. Inside the lock, query `SELECT value FROM sync_state WHERE key = 'schema_version'`. If missing or != "2", execute the full DDL script.
3. The DDL script must DROP (IF EXISTS) transitions and tickets, then CREATE all three tables fresh:
   - `sync_state(key TEXT PRIMARY KEY, value TEXT)` — unchanged from M1.
   - `transitions` — extended with `author_account_id TEXT NOT NULL DEFAULT ''`, `author_display_name TEXT NOT NULL DEFAULT ''`, `from_status TEXT NOT NULL DEFAULT ''`, `to_status TEXT NOT NULL DEFAULT ''`. Keep existing columns: `id INTEGER PK AUTOINCREMENT`, `ticket_key TEXT NOT NULL`, `transition_date TEXT NOT NULL`, `action_type TEXT NOT NULL CHECK(action_type IN ('ATTEMPT','RETURN'))`. Add `UNIQUE(ticket_key, transition_date, action_type)` constraint per RESEARCH.md.
   - `tickets(ticket_key TEXT PRIMARY KEY, summary TEXT NOT NULL DEFAULT '', issue_type TEXT NOT NULL DEFAULT '', last_synced TEXT NOT NULL DEFAULT '')`.
4. Create indexes: `idx_transitions_date ON transitions(transition_date)`, `idx_transitions_ticket ON transitions(ticket_key)`. Do NOT add idx_transitions_author or idx_tickets_assignee (not in D-02/D-03 spec).
5. After DDL, `INSERT OR REPLACE INTO sync_state (key, value) VALUES ('schema_version', '2')`.
6. Commit, close connection, print "[competence] Schema recreated at v2".
7. If schema_version already == "2", skip DDL, print "[competence] SQLite already at v2".

DO NOT: implement ALTER TABLE, data migration, or data preservation logic. D-01 explicitly chooses DROP+CREATE.
DO NOT: change the existing `_get_db()`, `_db_get()`, `_db_set()`, or `_db_get_async()`, `_db_set_async()` functions — they remain exactly as lines 58-101.
DO NOT: change the module-level imports, constants, or state variables (lines 1-39).

Per D-02 and D-03: the exact column set and types must match the specifications above. Do not add extra columns like `status`, `assignee_display_name`, or `assignee_account_id` to the tickets table (those are from PATTERNS.md's expanded version, not from the locked D-03 decision).
  </action>
  <verify>
    <automated>python -c "
import sqlite3; import os
DB_PATH = os.path.join('app', 'plugins', 'competence_cache.db')
if os.path.exists(DB_PATH): os.remove(DB_PATH)
# Simulate startup DDL
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA journal_mode=WAL')
conn.executescript('''
    CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT);
    INSERT INTO sync_state VALUES ('schema_version', '2');
    CREATE TABLE transitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_key TEXT NOT NULL,
        transition_date TEXT NOT NULL,
        action_type TEXT NOT NULL CHECK(action_type IN (''ATTEMPT'',''RETURN'')),
        author_account_id TEXT NOT NULL DEFAULT '''',
        author_display_name TEXT NOT NULL DEFAULT '''',
        from_status TEXT NOT NULL DEFAULT '''',
        to_status TEXT NOT NULL DEFAULT '''',
        UNIQUE(ticket_key, transition_date, action_type)
    );
    CREATE TABLE tickets (
        ticket_key TEXT PRIMARY KEY,
        summary TEXT NOT NULL DEFAULT '''',
        issue_type TEXT NOT NULL DEFAULT '''',
        last_synced TEXT NOT NULL DEFAULT ''''
    );
    CREATE INDEX idx_transitions_date ON transitions(transition_date);
    CREATE INDEX idx_transitions_ticket ON transitions(ticket_key);
''')
conn.commit()
# Verify: 8 columns in transitions, 4 in tickets, 2 in sync_state
cols_t = [r[1] for r in conn.execute('PRAGMA table_info(transitions)')]
assert len(cols_t) == 8, f'transitions: expected 8 cols, got {len(cols_t)}: {cols_t}'
cols_tk = [r[1] for r in conn.execute('PRAGMA table_info(tickets)')]
assert len(cols_tk) == 4, f'tickets: expected 4 cols, got {len(cols_tk)}: {cols_tk}'
assert 'author_account_id' in cols_t
assert 'author_display_name' in cols_t
assert 'from_status' in cols_t
assert 'to_status' in cols_t
assert 'ticket_key' in cols_tk
assert 'summary' in cols_tk
assert 'issue_type' in cols_tk
assert 'last_synced' in cols_tk
# Verify check constraint
conn.execute('INSERT INTO transitions(ticket_key,transition_date,action_type) VALUES(?,?,?)', ('T-1','2025-01-01','ATTEMPT'))
conn.commit()
try:
    conn.execute('INSERT INTO transitions(ticket_key,transition_date,action_type) VALUES(?,?,?)', ('T-2','2025-01-02','INVALID'))
    assert False, 'Should have raised IntegrityError for INVALID action_type'
except sqlite3.IntegrityError:
    pass
conn.close()
os.remove(DB_PATH)
print('OK: Schema validation passed')
"
</automated>
  </verify>
  <done>startup() creates schema_version=2 tables on first launch. transitions has 8 columns with CHECK constraint. tickets has 4 columns with ticket_key PK. Idempotent: re-running startup() on v2 DB is a no-op. Print statements confirm path taken.</done>
</task>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- WAVE 2: Enhanced _parse_changelog()                            -->
<!-- ═══════════════════════════════════════════════════════════════ -->

<task type="auto" tdd="true">
  <name>Task 2: Rewrite _parse_changelog() — capture attribution data (D-04)</name>
  <files>app/plugins/competence.py</files>
  <behavior>
    - Test 1: An ATTEMPT transition (In Development → For Testing by any author) returns a dict with all 8 keys: ticket_key, transition_date, action_type="ATTEMPT", author_account_id, author_display_name, from_status, to_status.
    - Test 2: After an ATTEMPT sets in_testing=True, a subsequent RETURN transition (For Testing → In Development by a DIFFERENT author) returns a dict with author_account_id/author_display_name of the QA engineer (not the original developer).
    - Test 3: A status change that does NOT match ATTEMPT_FROM/TO or RETURN_FROM/TO is skipped (not in output).
    - Test 4: A RETURN before any ATTEMPT is skipped (in_testing guard prevents false returns).
    - Test 5: Multiple ATTEMPT→RETURN cycles on the same ticket produce correct pairings.
    - Test 6: An ATTEMPT that transitions to a non-testing status (not in ATTEMPT_TO) is NOT counted as an ATTEMPT.
  </behavior>
  <action>
Rewrite `_parse_changelog()` (lines 158-220) per PATTERNS.md §5 and RESEARCH.md lines 329-395.

Changes from M1:
1. **Remove** the `current_account_id` parameter from the function signature (D-04: team-wide tracking).
2. **Remove** the `and author_id == current_account_id` condition from the ATTEMPT rule — any author entering testing counts.
3. **Add** four new fields to every transition dict: `author_account_id`, `author_display_name`, `from_status`, `to_status`.
4. Extract `author_name = author.get("displayName", "")` alongside existing `author_id`.
5. **Keep** the `in_testing` state machine logic unchanged (ATTEMPT sets True, RETURN sets False and requires in_testing==True).
6. **Keep** the status set constants (`ATTEMPT_FROM`, `ATTEMPT_TO`, `RETURN_FROM`, `RETURN_TO`) unchanged.
7. **Reverse** changelog entries before iteration: `for entry in reversed(changelog.get("values", []))` — oldest-first processing is safer for the extended attribution fields (RESEARCH.md Pitfall 3 recommendation confirmed by user).

Return type stays `list[dict]`. Each dict has exactly keys: `ticket_key`, `transition_date`, `action_type`, `author_account_id`, `author_display_name`, `from_status`, `to_status`.

DO NOT change the status set constants (lines 31-34). DO NOT change the function's location in the file (after HTTP helpers, before stats helpers).
  </action>
  <verify>
    <automated>python -c "
import sys; sys.path.insert(0, 'app')
from plugins.competence import _parse_changelog, ATTEMPT_FROM, ATTEMPT_TO, RETURN_FROM, RETURN_TO

# Test 1: Single ATTEMPT with full attribution
changelog1 = {'values': [{
    'author': {'accountId': 'dev123', 'displayName': 'Dev User'},
    'created': '2025-01-10',
    'items': [{'field': 'status', 'fromString': 'In Development', 'toString': 'For Testing'}]
}]}
r1 = _parse_changelog(changelog1, 'T-1')
assert len(r1) == 1, f'Expected 1, got {len(r1)}'
t = r1[0]
assert t['ticket_key'] == 'T-1'
assert t['action_type'] == 'ATTEMPT'
assert t['author_account_id'] == 'dev123'
assert t['author_display_name'] == 'Dev User'
assert t['from_status'] == 'In Development'
assert t['to_status'] == 'For Testing'

# Test 2: ATTEMPT + RETURN with different author
changelog2 = {'values': [
    {'author': {'accountId': 'qa456', 'displayName': 'QA User'}, 'created': '2025-01-15',
     'items': [{'field': 'status', 'fromString': 'For Testing', 'toString': 'In Development'}]},
    {'author': {'accountId': 'dev123', 'displayName': 'Dev User'}, 'created': '2025-01-10',
     'items': [{'field': 'status', 'fromString': 'In Development', 'toString': 'For Testing'}]},
]}
r2 = _parse_changelog(changelog2, 'T-2')
assert len(r2) == 2, f'Expected 2, got {len(r2)}'
attempt = [x for x in r2 if x['action_type'] == 'ATTEMPT'][0]
ret = [x for x in r2 if x['action_type'] == 'RETURN'][0]
assert attempt['author_account_id'] == 'dev123'
assert ret['author_account_id'] == 'qa456', f'RETURN author should be QA, got {ret[\"author_account_id\"]}'
assert ret['author_display_name'] == 'QA User'
assert ret['from_status'] == 'For Testing'
assert ret['to_status'] == 'In Development'

# Test 3: Non-status field change is skipped
changelog3 = {'values': [{
    'author': {'accountId': 'x'}, 'created': '2025-01-01',
    'items': [{'field': 'priority', 'fromString': 'High', 'toString': 'Low'}]
}]}
r3 = _parse_changelog(changelog3, 'T-3')
assert len(r3) == 0

# Test 4: RETURN without prior ATTEMPT
changelog4 = {'values': [{
    'author': {'accountId': 'qa'}, 'created': '2025-01-01',
    'items': [{'field': 'status', 'fromString': 'For Testing', 'toString': 'In Development'}]
}]}
r4 = _parse_changelog(changelog4, 'T-4')
assert len(r4) == 0, 'RETURN without ATTEMPT should be skipped'

# Test 5: ATTEMPT to non-testing status should NOT count
changelog5 = {'values': [{
    'author': {'accountId': 'dev'}, 'created': '2025-01-01',
    'items': [{'field': 'status', 'fromString': 'In Development', 'toString': 'Done'}]
}]}
r5 = _parse_changelog(changelog5, 'T-5')
assert len(r5) == 0, 'ATTEMPT to non-testing status should not count'

print('OK: All _parse_changelog tests passed')
"
</automated>
  </verify>
  <done>_parse_changelog() returns dicts with all 7 keys per transition. Any author can trigger ATTEMPT (no current_account_id filter). RETURN captures QA identity. Reversed entry processing (oldest-first). All 6 test cases pass.</done>
</task>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- WAVE 3: Enhanced sync job                                      -->
<!-- ═══════════════════════════════════════════════════════════════ -->

<task type="auto">
  <name>Task 3: Enhance _sync_job() — fetch ticket metadata + store extended columns (D-05, FR9)</name>
  <files>app/plugins/competence.py</files>
  <action>
Modify `_sync_job()` (lines 261-395) per PATTERNS.md §6 and RESEARCH.md lines 396-455. Three areas of change:

### 3a. Extend search_issues fields param (FR9.1, D-05)
In step 3 (line 304), change `fields="key"` to `fields="key,summary,issuetype"`.
Update the batch extraction (lines 306-307) to capture summary and issue_type:
```python
batch = [{
    "key": iss.key,
    "summary": getattr(iss.fields, "summary", "") or "",
    "issue_type": getattr(iss.fields.issuetype, "name", "") if hasattr(iss.fields, "issuetype") and iss.fields.issuetype else "",
} for iss in results]
```

### 3b. Add ticket metadata upsert step (FR9.2, FR9.3, D-05)
After step 3 (search complete) and before step 4 (changelog fetch), add a new step 3b:
1. Iterate over `all_issues` list.
2. For each issue dict with a truthy `summary` or `issue_type`, call a synchronous `_upsert_ticket_sync(key, summary, issue_type)`.
3. Create `_upsert_ticket_sync()` as a new module-level helper function following the `_db_get`/`_db_set` pattern:
   - Uses `_db_lock` + `_get_db()`.
   - `INSERT OR REPLACE INTO tickets (ticket_key, summary, issue_type, last_synced) VALUES (?, ?, ?, ?)`.
   - `last_synced` set to `datetime.now(timezone.utc).isoformat()`.
   - commit, close connection in finally.
4. Create an async wrapper: `async def _db_upsert_ticket(key, summary, issue_type): await asyncio.to_thread(_upsert_ticket_sync, key, summary, issue_type)`.
5. Upsert all tickets: `for iss in all_issues: await _db_upsert_ticket(iss["key"], iss["summary"], iss["issue_type"])`.
   Optionally use `asyncio.gather()` for parallel upserts, but sequential is acceptable for typical <500 tickets.

### 3c. Update parse call + insert statement (FR8.3, D-04)
1. In step 5 (line 352-353), remove the `current_account_id` argument: `parsed = _parse_changelog({"values": entries}, key)` instead of `_parse_changelog({"values": entries}, key, current_account_id)`.
2. In step 6 (lines 371-376), extend the INSERT statement to include 4 new columns:
```sql
INSERT INTO transitions
  (ticket_key, transition_date, action_type,
   author_account_id, author_display_name,
   from_status, to_status)
VALUES (?, ?, ?, ?, ?, ?, ?)
```
With values: `t["ticket_key"], t["transition_date"], t["action_type"], t.get("author_account_id", ""), t.get("author_display_name", ""), t.get("from_status", ""), t.get("to_status", "")`.

### 3d. Remove current_account_id dependency
Since `_parse_changelog()` no longer takes `current_account_id` (D-04), the `myself` call in step 1 (line 276-280) is no longer needed for the parser. However, **keep** the `myself()` call and `current_account_id` variable — it is used by the JQL query construction (`currentUser()` in step 2). The Jira package resolves `currentUser()` server-side, but keeping the `myself()` call provides a fast credential validation check early in the sync pipeline. Simply remove the guard `if not current_account_id: return` since it's no longer required for parsing, OR keep it as a credential check. Recommend: keep the call, make the guard non-fatal (print warning, continue with sync using server-side currentUser() resolution).

DO NOT change: semaphore pattern, changelog fetch loop, dedup logic, in_progress guard, last_sync update, try/finally structure, error handling.
DO NOT remove: the `myself()` call entirely — it validates credentials. Make the accountId absence non-fatal.
  </action>
  <verify>
    <automated>python -c "
# Verify _upsert_ticket_sync function exists and works
import sys; sys.path.insert(0, 'app')
from plugins.competence import _upsert_ticket_sync, _get_db, _db_lock, DB_PATH
import sqlite3, os

# Ensure clean test DB
if os.path.exists(DB_PATH): os.remove(DB_PATH)
conn = sqlite3.connect(DB_PATH)
conn.executescript('''
    CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT);
    INSERT INTO sync_state VALUES ('schema_version', '2');
    CREATE TABLE transitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_key TEXT NOT NULL, transition_date TEXT NOT NULL,
        action_type TEXT NOT NULL CHECK(action_type IN (''ATTEMPT'',''RETURN'')),
        author_account_id TEXT NOT NULL DEFAULT '''',
        author_display_name TEXT NOT NULL DEFAULT '''',
        from_status TEXT NOT NULL DEFAULT '''',
        to_status TEXT NOT NULL DEFAULT '''',
        UNIQUE(ticket_key, transition_date, action_type)
    );
    CREATE TABLE tickets (
        ticket_key TEXT PRIMARY KEY,
        summary TEXT NOT NULL DEFAULT '''',
        issue_type TEXT NOT NULL DEFAULT '''',
        last_synced TEXT NOT NULL DEFAULT ''''
    );
''')
conn.commit(); conn.close()

# Test upsert
_upsert_ticket_sync('TEST-1', 'Fix login bug', 'Bug')
_upsert_ticket_sync('TEST-1', 'Fix login bug - updated', 'Bug')  # idempotent

# Verify
conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
row = conn.execute('SELECT * FROM tickets WHERE ticket_key = ?', ('TEST-1',)).fetchone()
assert row is not None, 'Ticket not inserted'
assert row['summary'] == 'Fix login bug - updated', f'Summary mismatch: {row[\"summary\"]}'
assert row['issue_type'] == 'Bug'
assert row['last_synced'] is not None and len(row['last_synced']) > 0, 'last_synced not set'
conn.close()
os.remove(DB_PATH)
print('OK: _upsert_ticket_sync works correctly')
"
</automated>
  </verify>
  <done>
_upsert_ticket_sync() helper exists and correctly INSERT OR REPLACEs into tickets table with last_synced timestamp.
search_issues() fetches fields="key,summary,issuetype".
Sync job upserts all ticket metadata before changelog fetch.
_transition INSERT includes all 4 new columns (author_account_id, author_display_name, from_status, to_status).
_parse_changelog called without current_account_id argument.
All existing sync guards and error handling preserved.
  </done>
</task>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- WAVE 4: Preserve existing endpoints                            -->
<!-- ═══════════════════════════════════════════════════════════════ -->

<task type="auto">
  <name>Task 4: Update existing endpoints and _load_transitions_df() for new schema (D-07, FR10.5)</name>
  <files>app/plugins/competence.py</files>
  <action>
Three small changes required to make existing M1 endpoints work with the new extended schema:

### 4a. Update _load_transitions_df() SELECT query (line 247-249)
The current query selects only 4 columns: `id, ticket_key, transition_date, action_type`. Update to select all columns so existing endpoints can access new fields if needed:
```python
df = pd.read_sql_query(
    "SELECT id, ticket_key, transition_date, action_type, "
    "author_account_id, author_display_name, from_status, to_status "
    "FROM transitions ORDER BY transition_date",
    conn,
)
```
pandas will add 4 new columns to the DataFrame — existing code that only accesses `action_type` and `transition_date` continues working unchanged. The extra columns are harmless.

### 4b. Verify existing endpoints need NO logic changes
The four M1 endpoints (`/stats`, `/sync`, `/sync/status`, `/chart`) must remain at their exact paths with their exact response signatures per D-07:
- `GET /api/competence/stats` — returns `[{period, attempts, returns, return_rate_pct}]`. The code (lines 412-443) accesses only `action_type` and `transition_date` from the DataFrame — works unchanged with 8-column DataFrame.
- `POST /api/competence/sync` — triggers `asyncio.create_task(_sync_job())`. Signature unchanged. Internal sync job changes are transparent.
- `GET /api/competence/sync/status` — returns `{last_sync, in_progress}`. No schema dependency — works unchanged.
- `GET /api/competence/chart` — returns Plotly HTML. Accesses `action_type` and `transition_date` — works unchanged with 8-column DataFrame.

### 4c. Code preservation checklist
The following blocks must NOT be modified:
- Lines 412-443: `competence_stats()` route handler
- Lines 445-464: `competence_sync()` route handler
- Lines 466-477: `competence_sync_status()` route handler
- Lines 479-545: `competence_chart()` route handler
- Lines 227-254: `_format_2q_label()` and `_load_transitions_df()` — SELECT query expanded but function signature and logic unchanged

Verify that the `db_path` is correct for the lock or the code writes remain unchanged.
  </action>
  <verify>
    <automated>MISSING — verify by manual inspection: all four M1 route handler bodies match lines 412-545 of the original competence.py (unchanged except _load_transitions_df SELECT query which adds 4 harmless columns). The new 4 endpoints must appear AFTER these 4 in register_routes().
</automated>
  </verify>
  <done>_load_transitions_df() returns 8-column DataFrame. All 4 M1 endpoint handler bodies are unchanged. Endpoints remain at their original paths with original response signatures. Chart endpoint returns valid Plotly HTML (NFR9). Stats endpoint based on df["action_type"] aggregation continues working (NFR7).</done>
</task>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- WAVE 5: New /tickets endpoint                                  -->
<!-- ═══════════════════════════════════════════════════════════════ -->

<task type="auto" tdd="true">
  <name>Task 5: Add GET /api/competence/tickets — per-ticket aggregated stats (D-06, FR10.1)</name>
  <files>app/plugins/competence.py</files>
  <behavior>
    - Test 1: Empty DB returns empty array `[]` with status 200.
    - Test 2: With transitions+tickets data, returns one entry per unique ticket_key with fields: ticket_key, summary, issue_type, attempts, returns, return_rate_pct, last_return_date, last_return_by.
    - Test 3: return_rate_pct is 0.0 when attempts=0, correctly computed (returns/attempts*100 rounded to 1 decimal) when attempts>0.
    - Test 4: last_return_by is the author_display_name of the most recent RETURN transition for that ticket.
    - Test 5: Results sorted by returns DESC, then attempts DESC.
    - Test 6: Ticket with no matching row in tickets table still appears (LEFT JOIN), with summary/issue_type as empty strings.
  </behavior>
  <action>
Add a new route handler inside `register_routes()`, after the existing 4 M1 endpoints. Follow PATTERNS.md §7c and RESEARCH.md lines 456-486.

```python
@app.get("/api/competence/tickets")
async def competence_tickets():
    """Return per-ticket aggregated stats with attribution."""
    try:
        conn = _get_db()
        try:
            df = pd.read_sql_query("""
                SELECT
                    t.ticket_key,
                    t.transition_date,
                    t.action_type,
                    t.author_display_name,
                    COALESCE(tk.summary, '') AS summary,
                    COALESCE(tk.issue_type, '') AS issue_type
                FROM transitions t
                LEFT JOIN tickets tk ON t.ticket_key = tk.ticket_key
                ORDER BY t.ticket_key, t.transition_date
            """, conn)
        finally:
            conn.close()

        if df.empty:
            return []

        grouped = df.groupby("ticket_key")
        result: list[dict] = []
        for key, group in grouped:
            attempts = int((group["action_type"] == "ATTEMPT").sum())
            returns = int((group["action_type"] == "RETURN").sum())
            return_rate = (
                round((returns / attempts * 100), 1)
                if attempts > 0 else 0.0
            )
            # Last return info
            returns_mask = group["action_type"] == "RETURN"
            if returns_mask.any():
                last_return = group[returns_mask].iloc[-1]
                last_return_date = str(last_return["transition_date"])
                last_return_by = str(last_return.get("author_display_name", ""))
            else:
                last_return_date = ""
                last_return_by = ""

            first_row = group.iloc[0]
            result.append({
                "ticket_key": key,
                "summary": str(first_row.get("summary", "")),
                "issue_type": str(first_row.get("issue_type", "")),
                "attempts": attempts,
                "returns": returns,
                "return_rate_pct": return_rate,
                "last_return_date": last_return_date,
                "last_return_by": last_return_by,
            })

        # Sort: returns DESC, attempts DESC
        result.sort(key=lambda x: (-x["returns"], -x["attempts"]))
        return result
    except Exception as e:
        raise HTTPException(500, str(e))
```

Key implementation notes:
- Uses pandas `read_sql_query` with LEFT JOIN (consistent with _load_transitions_df pattern).
- Compute last_return_by via pandas groupby filtering (avoids correlated subquery performance issues from RESEARCH.md Pitfall 5).
- Response shape matches FR10.1 exactly: `ticket_key`, `summary`, `issue_type`, `attempts`, `returns`, `return_rate_pct`, `last_return_date`, `last_return_by`.
- NFR8: Return all results for now. Pagination (`?offset=0&limit=100`) should be added only if testing reveals >500ms response time. RESEARCH.md Open Question 3 confirms this approach is acceptable for typical <500 ticket datasets.
- Error handling: three-tier — HTTPException re-raised, generic Exception → HTTPException(500).
  </action>
  <verify>
    <automated>python -c "
import sys; sys.path.insert(0, 'app')
from plugins.competence import _get_db, _db_lock, DB_PATH
import sqlite3, os, json
from fastapi.testclient import TestClient
from app.main import app

# Setup test DB with sample data
if os.path.exists(DB_PATH): os.remove(DB_PATH)
conn = sqlite3.connect(DB_PATH)
conn.executescript('''
    CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT);
    INSERT INTO sync_state VALUES ('schema_version', '2');
    CREATE TABLE transitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_key TEXT NOT NULL, transition_date TEXT NOT NULL,
        action_type TEXT NOT NULL CHECK(action_type IN (''ATTEMPT'',''RETURN'')),
        author_account_id TEXT NOT NULL DEFAULT '''',
        author_display_name TEXT NOT NULL DEFAULT '''',
        from_status TEXT NOT NULL DEFAULT '''',
        to_status TEXT NOT NULL DEFAULT '''',
        UNIQUE(ticket_key, transition_date, action_type)
    );
    CREATE TABLE tickets (
        ticket_key TEXT PRIMARY KEY,
        summary TEXT NOT NULL DEFAULT '''',
        issue_type TEXT NOT NULL DEFAULT '''',
        last_synced TEXT NOT NULL DEFAULT ''''
    );
    INSERT INTO transitions VALUES (1,'T-1','2025-01-01','ATTEMPT','dev1','Dev One','In Dev','For Testing');
    INSERT INTO transitions VALUES (2,'T-1','2025-01-05','RETURN','qa1','QA One','For Testing','In Dev');
    INSERT INTO transitions VALUES (3,'T-1','2025-01-10','ATTEMPT','dev1','Dev One','In Dev','For Testing');
    INSERT INTO transitions VALUES (4,'T-2','2025-01-02','ATTEMPT','dev2','Dev Two','New','For Testing');
    INSERT INTO tickets VALUES ('T-1','Fix login bug','Bug','2025-01-10');
    INSERT INTO tickets VALUES ('T-2','Add feature X','Story','2025-01-10');
''')
conn.commit(); conn.close()

client = TestClient(app)
resp = client.get('/api/competence/tickets')
assert resp.status_code == 200, f'Expected 200, got {resp.status_code}: {resp.text}'
data = resp.json()
assert isinstance(data, list), f'Expected list, got {type(data)}'
assert len(data) == 2, f'Expected 2 tickets, got {len(data)}'

t1 = [t for t in data if t['ticket_key'] == 'T-1'][0]
assert t1['attempts'] == 2, f'T-1: expected 2 attempts, got {t1[\"attempts\"]}'
assert t1['returns'] == 1, f'T-1: expected 1 return, got {t1[\"returns\"]}'
assert t1['return_rate_pct'] == 50.0, f'T-1: expected 50.0%, got {t1[\"return_rate_pct\"]}'
assert t1['summary'] == 'Fix login bug'
assert t1['issue_type'] == 'Bug'
assert t1['last_return_by'] == 'QA One', f'T-1 last_return_by: expected QA One, got {t1[\"last_return_by\"]}'
assert t1['last_return_date'] == '2025-01-05'

t2 = [t for t in data if t['ticket_key'] == 'T-2'][0]
assert t2['attempts'] == 1
assert t2['returns'] == 0
assert t2['return_rate_pct'] == 0.0
assert t2['last_return_date'] == ''
assert t2['last_return_by'] == ''

# Sort verification: T-1 (1 return) before T-2 (0 returns)
assert data[0]['ticket_key'] == 'T-1', f'Sorted: expected T-1 first, got {data[0][\"ticket_key\"]}'

os.remove(DB_PATH)
print('OK: /tickets endpoint tests passed')
"
</automated>
  </verify>
  <done>GET /api/competence/tickets returns per-ticket aggregated stats. Response shape matches FR10.1. Attribution visible (last_return_by shows QA name). Sorted by returns DESC. LEFT JOIN includes tickets with no metadata. Empty DB returns empty array.</done>
</task>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- WAVE 6: New /tickets/{key} endpoint                            -->
<!-- ═══════════════════════════════════════════════════════════════ -->

<task type="auto">
  <name>Task 6: Add GET /api/competence/tickets/{key} — single ticket timeline (D-06, FR10.2)</name>
  <files>app/plugins/competence.py</files>
  <action>
Add a new route handler inside `register_routes()`, after the `/tickets` endpoint. Follow PATTERNS.md §7d and RESEARCH.md lines 488-510.

```python
@app.get("/api/competence/tickets/{key}")
async def competence_ticket_detail(key: str):
    """Return the full transition timeline for a single ticket,
    including attribution data and ticket metadata."""
    try:
        conn = _get_db()
        try:
            # Load transitions for this ticket
            df = pd.read_sql_query("""
                SELECT ticket_key, transition_date, action_type,
                       author_account_id, author_display_name,
                       from_status, to_status
                FROM transitions
                WHERE ticket_key = ?
                ORDER BY transition_date
            """, conn, params=(key,))

            # Load ticket metadata
            meta_row = conn.execute(
                "SELECT * FROM tickets WHERE ticket_key = ?", (key,)
            ).fetchone()
            meta = dict(meta_row) if meta_row else {}
        finally:
            conn.close()

        transitions = df.to_dict(orient="records") if not df.empty else []

        return {
            "ticket_key": key,
            "summary": meta.get("summary", ""),
            "issue_type": meta.get("issue_type", ""),
            "transitions": [
                {
                    "date": t["transition_date"],
                    "action": t["action_type"],
                    "author": t.get("author_display_name", ""),
                    "from": t.get("from_status", ""),
                    "to": t.get("to_status", ""),
                }
                for t in transitions
            ],
        }
    except Exception as e:
        raise HTTPException(500, str(e))
```

Key implementation notes:
- Route parameter `{key}` is auto-validated by FastAPI as a string path parameter.
- SQL uses parameterized query (`?`) to prevent SQL injection (ASVS V5).
- Response shape matches FR10.2: `ticket_key`, `summary`, `transitions[]` with `date`, `action`, `author`, `from`, `to`.
- `issue_type` is NOT in FR10.2 spec but is included as it was in PATTERNS.md — harmless extra field.
- If ticket_key has no data, returns empty transitions array (not 404 — consistent with existing endpoint behavior).
- Error handling: generic Exception → HTTPException(500).
  </action>
  <verify>
    <automated>python -c "
import sys; sys.path.insert(0, 'app')
from fastapi.testclient import TestClient
from app.main import app
import sqlite3, os
from plugins.competence import DB_PATH

# Reuse test DB setup from Task 5 if still exists, else create minimal
if not os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO sync_state VALUES ('schema_version', '2');
        CREATE TABLE transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_key TEXT NOT NULL, transition_date TEXT NOT NULL,
            action_type TEXT NOT NULL CHECK(action_type IN (''ATTEMPT'',''RETURN'')),
            author_account_id TEXT NOT NULL DEFAULT '''',
            author_display_name TEXT NOT NULL DEFAULT '''',
            from_status TEXT NOT NULL DEFAULT '''',
            to_status TEXT NOT NULL DEFAULT '''',
            UNIQUE(ticket_key, transition_date, action_type)
        );
        CREATE TABLE tickets (
            ticket_key TEXT PRIMARY KEY,
            summary TEXT NOT NULL DEFAULT '''',
            issue_type TEXT NOT NULL DEFAULT '''',
            last_synced TEXT NOT NULL DEFAULT ''''
        );
        INSERT INTO transitions VALUES (1,'T-1','2025-01-01','ATTEMPT','dev1','Dev One','In Dev','For Testing');
        INSERT INTO transitions VALUES (2,'T-1','2025-01-05','RETURN','qa1','QA One','For Testing','In Dev');
        INSERT INTO tickets VALUES ('T-1','Fix login','Bug','2025-01-10');
    ''')
    conn.commit(); conn.close()

client = TestClient(app)

# Test existing ticket
resp = client.get('/api/competence/tickets/T-1')
assert resp.status_code == 200, f'Expected 200, got {resp.status_code}'
data = resp.json()
assert data['ticket_key'] == 'T-1'
assert data['summary'] == 'Fix login'
assert data['issue_type'] == 'Bug'
assert len(data['transitions']) == 2
t0 = data['transitions'][0]
assert t0['date'] == '2025-01-01'
assert t0['action'] == 'ATTEMPT'
assert t0['author'] == 'Dev One'
assert t0['from'] == 'In Dev'
assert t0['to'] == 'For Testing'
t1 = data['transitions'][1]
assert t1['action'] == 'RETURN'
assert t1['author'] == 'QA One'

# Test non-existent ticket
resp2 = client.get('/api/competence/tickets/NONEXIST')
assert resp2.status_code == 200
data2 = resp2.json()
assert data2['transitions'] == []
assert data2['ticket_key'] == 'NONEXIST'

os.remove(DB_PATH)
print('OK: /tickets/{key} endpoint tests passed')
"
</automated>
  </verify>
  <done>GET /api/competence/tickets/{key} returns full transition timeline with attribution. Response shape matches FR10.2. Transitions ordered chronologically. Non-existent tickets return empty transitions array. SQL parameterized to prevent injection.</done>
</task>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- WAVE 7: New /chart/volume endpoint                             -->
<!-- ═══════════════════════════════════════════════════════════════ -->

<task type="auto">
  <name>Task 7: Add GET /api/competence/chart/volume — dual-bar attempts vs returns Plotly chart (D-06, FR10.3, NFR9)</name>
  <files>app/plugins/competence.py</files>
  <action>
Add a new route handler inside `register_routes()`, after the `/tickets/{key}` endpoint. Follow PATTERNS.md §7e and RESEARCH.md lines 512-575.

```python
@app.get("/api/competence/chart/volume", response_class=HTMLResponse)
async def competence_chart_volume():
    """Return a Plotly grouped bar chart: attempts vs returns per half-year."""
    try:
        df = _load_transitions_df()
        if df.empty:
            return (
                "<p style='padding:40px;text-align:center;"
                "color:var(--text-muted)'>"
                "No data yet &mdash; click Sync Now to pull Jira changelogs."
                "</p>"
            )

        df["transition_date"] = pd.to_datetime(df["transition_date"])
        grouped = df.groupby(pd.Grouper(key="transition_date", freq="2Q"))

        periods = []
        attempts_list = []
        returns_list = []
        for period, group in grouped:
            periods.append(_format_2q_label(period))
            attempts_list.append(int((group["action_type"] == "ATTEMPT").sum()))
            returns_list.append(int((group["action_type"] == "RETURN").sum()))

        if not periods:
            return "<p style='padding:40px;text-align:center;color:var(--text-muted)'>No data yet</p>"

        fig = go.Figure([
            go.Bar(
                name="Attempts",
                x=periods,
                y=attempts_list,
                marker_color="#3498db",
                text=attempts_list,
                textposition="auto",
                hovertemplate="%{x}<br>Attempts: %{y}<extra></extra>",
            ),
            go.Bar(
                name="Returns",
                x=periods,
                y=returns_list,
                marker_color="#e74c3c",
                text=returns_list,
                textposition="auto",
                hovertemplate="%{x}<br>Returns: %{y}<extra></extra>",
            ),
        ])

        fig.update_layout(
            title="Testing Attempts vs Returns by Half-Year",
            yaxis_title="Count",
            xaxis_title=None,
            barmode="group",
            margin=dict(l=40, r=20, t=40, b=40),
            height=400,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9"),
            legend=dict(font=dict(color="#c9d1d9")),
        )

        return fig.to_html(include_plotlyjs="cdn", full_html=False)
    except Exception as e:
        raise HTTPException(500, str(e))
```

Key implementation notes:
- Uses `response_class=HTMLResponse` (consistent with existing `/chart` endpoint — PATTERNS.md §7b convention).
- Two `go.Bar()` traces with `barmode="group"` for side-by-side bars (per RESEARCH.md Pitfall 4 recommendation).
- Colors: `#3498db` (blue) for attempts, `#e74c3c` (red) for returns — tested against dark theme background.
- Empty state: returns plain HTML message (identical pattern to existing `/chart` endpoint).
- reuses `_load_transitions_df()` and `_format_2q_label()` from the existing helpers.
- `fig.to_html(include_plotlyjs="cdn", full_html=False)` — consistent with existing chart endpoint.

DO NOT change: the `barmode` to "stack" or "overlay". DO NOT import new Plotly modules — `go.Figure`, `go.Bar` already imported.
  </action>
  <verify>
    <automated>MISSING — Plotly output is HTML. Verify manually that:
1. `curl http://localhost:port/api/competence/chart/volume` returns HTML containing `"plotly"` and `"Attempts"` and `"Returns"` text.
2. When DB is empty, returns the "No data yet" placeholder HTML (status 200).
3. The returned HTML renders correctly in a browser (two bar groups per period, blue + red, dark theme).
</automated>
  </verify>
  <done>GET /api/competence/chart/volume returns valid Plotly HTML with two bar traces (attempts + returns) grouped per half-year. Empty DB returns placeholder HTML. Dark theme compatible (#3498db + #e74c3c on transparent background). NFR9 satisfied.</done>
</task>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- WAVE 8: New /summary endpoint                                  -->
<!-- ═══════════════════════════════════════════════════════════════ -->

<task type="auto" tdd="true">
  <name>Task 8: Add GET /api/competence/summary — overall aggregates + top 5 most_returned (D-06, D-08, FR10.4)</name>
  <files>app/plugins/competence.py</files>
  <behavior>
    - Test 1: Empty DB returns `data_available: false`, all counts zero, last_sync from sync_state.
    - Test 2: With data, returns total_tickets, total_attempts, total_returns, overall_rate_pct, most_returned array.
    - Test 3: overall_rate_pct is (total_returns / total_attempts * 100) rounded to 1 decimal.
    - Test 4: most_returned is top 5 by return count DESC. When fewer than 5 tickets have returns, return all that do.
    - Test 5: total_tickets counts unique ticket_key values in the transitions table (not tickets table).
    - Test 6: Response shape matches FR10.4: `{total_tickets, total_attempts, total_returns, overall_rate_pct, most_returned: [{key, returns}]}`.
  </behavior>
  <action>
Add a new route handler inside `register_routes()`, after the `/chart/volume` endpoint. Follow PATTERNS.md §7f and RESEARCH.md lines 577-1011, with modifications per D-08.

```python
@app.get("/api/competence/summary")
async def competence_summary():
    """Return overall aggregate stats + top 5 most-returned tickets."""
    try:
        df = _load_transitions_df()

        last_sync = await _db_get_async("last_sync")

        if df.empty:
            return {
                "total_tickets": 0,
                "total_attempts": 0,
                "total_returns": 0,
                "overall_rate_pct": 0.0,
                "most_returned": [],
                "last_sync": last_sync,
                "data_available": False,
            }

        total_attempts = int((df["action_type"] == "ATTEMPT").sum())
        total_returns = int((df["action_type"] == "RETURN").sum())
        overall_rate = (
            round((total_returns / total_attempts * 100), 1)
            if total_attempts > 0 else 0.0
        )
        total_tickets = df["ticket_key"].nunique()

        # Top 5 most returned (D-08)
        returns_by_ticket = (
            df[df["action_type"] == "RETURN"]
            .groupby("ticket_key")
            .size()
            .reset_index(name="returns")
        )
        top5 = (
            returns_by_ticket
            .sort_values("returns", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )
        most_returned = [
            {"key": str(row["ticket_key"]), "returns": int(row["returns"])}
            for row in top5
        ]

        return {
            "total_tickets": total_tickets,
            "total_attempts": total_attempts,
            "total_returns": total_returns,
            "overall_rate_pct": overall_rate,
            "most_returned": most_returned,
            "last_sync": last_sync,
            "data_available": True,
        }
    except Exception as e:
        raise HTTPException(500, str(e))
```

Key implementation notes:
- `total_tickets` computed from unique `ticket_key` in transitions (not tickets table) — captures all tickets that have transition data, not just those with metadata.
- D-08: `most_returned` returns **top 5** by return count (not just ties for #1). Uses pandas `groupby().size().nlargest(5)`.
- `last_sync` fetched from sync_state via async wrapper — must use `await _db_get_async("last_sync")` since we're in an async handler.
- Response shape matches FR10.4 with added `last_sync` and `data_available` fields (useful for Phase 4 frontend).
- Error handling: generic Exception → HTTPException(500).
  </action>
  <verify>
    <automated>python -c "
import sys; sys.path.insert(0, 'app')
from fastapi.testclient import TestClient
from app.main import app
import sqlite3, os
from plugins.competence import DB_PATH

# Setup test DB
if os.path.exists(DB_PATH): os.remove(DB_PATH)
conn = sqlite3.connect(DB_PATH)
conn.executescript('''
    CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT);
    INSERT INTO sync_state VALUES ('schema_version', '2');
    INSERT INTO sync_state VALUES ('last_sync', '2025-06-01T00:00:00+00:00');
    CREATE TABLE transitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_key TEXT NOT NULL, transition_date TEXT NOT NULL,
        action_type TEXT NOT NULL CHECK(action_type IN (''ATTEMPT'',''RETURN'')),
        author_account_id TEXT NOT NULL DEFAULT '''',
        author_display_name TEXT NOT NULL DEFAULT '''',
        from_status TEXT NOT NULL DEFAULT '''',
        to_status TEXT NOT NULL DEFAULT '''',
        UNIQUE(ticket_key, transition_date, action_type)
    );
    CREATE TABLE tickets (
        ticket_key TEXT PRIMARY KEY,
        summary TEXT NOT NULL DEFAULT '''',
        issue_type TEXT NOT NULL DEFAULT '''',
        last_synced TEXT NOT NULL DEFAULT ''''
    );
    -- T-1: 3 attempts, 2 returns
    INSERT INTO transitions VALUES (1,'T-1','2025-01-01','ATTEMPT','d1','Dev1','In Dev','For Testing');
    INSERT INTO transitions VALUES (2,'T-1','2025-01-05','RETURN','q1','QA1','For Testing','In Dev');
    INSERT INTO transitions VALUES (3,'T-1','2025-01-10','ATTEMPT','d1','Dev1','In Dev','For Testing');
    INSERT INTO transitions VALUES (4,'T-1','2025-01-15','RETURN','q1','QA1','For Testing','In Dev');
    INSERT INTO transitions VALUES (5,'T-1','2025-01-20','ATTEMPT','d1','Dev1','In Dev','For Testing');
    -- T-2: 1 attempt, 1 return
    INSERT INTO transitions VALUES (6,'T-2','2025-02-01','ATTEMPT','d2','Dev2','New','For Testing');
    INSERT INTO transitions VALUES (7,'T-2','2025-02-05','RETURN','q2','QA2','For Testing','In Dev');
    -- T-3: 1 attempt, 0 returns
    INSERT INTO transitions VALUES (8,'T-3','2025-03-01','ATTEMPT','d3','Dev3','In Dev','For Testing');
''')
conn.commit(); conn.close()

client = TestClient(app)
resp = client.get('/api/competence/summary')
assert resp.status_code == 200, f'Expected 200, got {resp.status_code}'
data = resp.json()
assert data['data_available'] == True
assert data['total_tickets'] == 3, f'Expected 3 tickets, got {data[\"total_tickets\"]}'
assert data['total_attempts'] == 5, f'Expected 5 attempts, got {data[\"total_attempts\"]}'
assert data['total_returns'] == 3, f'Expected 3 returns, got {data[\"total_returns\"]}'
assert data['overall_rate_pct'] == 60.0, f'Expected 60.0%, got {data[\"overall_rate_pct\"]}'
assert data['last_sync'] == '2025-06-01T00:00:00+00:00'

# Top 5: T-1 (2 returns) should be first
mr = data['most_returned']
assert len(mr) == 2, f'Expected 2 most_returned, got {len(mr)}'
assert mr[0]['key'] == 'T-1'
assert mr[0]['returns'] == 2
assert mr[1]['key'] == 'T-2'
assert mr[1]['returns'] == 1

os.remove(DB_PATH)
print('OK: /summary endpoint tests passed')
"
</automated>
  </verify>
  <done>GET /api/competence/summary returns total_tickets, total_attempts, total_returns, overall_rate_pct, most_returned (top 5 by returns), last_sync, data_available. Empty DB returns data_available:false with zero counts. Response shape matches FR10.4 with D-08 top-5 constraint.</done>
</task>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!-- WAVE 9: Integration test                                       -->
<!-- ═══════════════════════════════════════════════════════════════ -->

<task type="auto">
  <name>Task 9: End-to-end integration — all 8 endpoints respond, data flows correctly</name>
  <files>app/plugins/competence.py</files>
  <action>
Run a comprehensive integration test that verifies:
1. All 8 endpoints return 200 (or appropriate response) with correct content types.
2. Existing endpoints still respond identically to M1 (signatures preserved per D-07).
3. New endpoints return data in the expected shapes (FR10.1-FR10.4).
4. Attribution data flows end-to-end: sync → parse → insert → API response.
5. No import errors, no runtime crashes on module load.

Create a test script `test_phase3_integration.py` and execute it:

```python
"""Phase 3 integration test — all 8 endpoints + data flow."""
import sys; sys.path.insert(0, '.')
import sqlite3, os, json
from fastapi.testclient import TestClient
from app.main import app
from app.plugins.competence import DB_PATH

def setup_test_db():
    if os.path.exists(DB_PATH): os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO sync_state VALUES ('schema_version', '2');
        INSERT INTO sync_state VALUES ('last_sync', '2025-06-01T00:00:00Z');
        CREATE TABLE transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_key TEXT NOT NULL, transition_date TEXT NOT NULL,
            action_type TEXT NOT NULL CHECK(action_type IN ('ATTEMPT','RETURN')),
            author_account_id TEXT NOT NULL DEFAULT '',
            author_display_name TEXT NOT NULL DEFAULT '',
            from_status TEXT NOT NULL DEFAULT '',
            to_status TEXT NOT NULL DEFAULT '',
            UNIQUE(ticket_key, transition_date, action_type)
        );
        CREATE TABLE tickets (
            ticket_key TEXT PRIMARY KEY,
            summary TEXT NOT NULL DEFAULT '',
            issue_type TEXT NOT NULL DEFAULT '',
            last_synced TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO transitions VALUES
            (1,'T-1','2025-01-10','ATTEMPT','dev1','Dev One','In Dev','For Testing'),
            (2,'T-1','2025-01-15','RETURN','qa1','QA One','For Testing','In Dev'),
            (3,'T-2','2025-02-01','ATTEMPT','dev2','Dev Two','New','For Testing');
        INSERT INTO tickets VALUES
            ('T-1','Fix bug','Bug','2025-06-01'),
            ('T-2','Add feature','Story','2025-06-01');
    ''')
    conn.commit(); conn.close()

def test_all_endpoints():
    client = TestClient(app)
    results = {}

    # M1 endpoints (D-07)
    r = client.get('/api/competence/stats')
    assert r.status_code == 200, f'stats: {r.status_code}'
    assert isinstance(r.json(), list), 'stats: expected list'
    results['stats'] = 'OK'

    r = client.get('/api/competence/sync/status')
    assert r.status_code == 200
    data = r.json()
    assert 'last_sync' in data and 'in_progress' in data
    results['sync_status'] = 'OK'

    r = client.get('/api/competence/chart')
    assert r.status_code == 200
    assert 'plotly' in r.text.lower() or 'No data' in r.text, f'chart: unexpected response'
    assert r.headers.get('content-type', '').startswith('text/html')
    results['chart'] = 'OK'

    r = client.post('/api/competence/sync')
    assert r.status_code == 200
    assert r.json()['status'] in ('sync_started', 'sync_already_running')
    results['sync'] = 'OK'

    # New endpoints (D-06)
    r = client.get('/api/competence/tickets')
    assert r.status_code == 200
    tickets = r.json()
    assert isinstance(tickets, list) and len(tickets) >= 2
    assert tickets[0]['attempts'] == 1
    results['tickets'] = 'OK'

    r = client.get('/api/competence/tickets/T-1')
    assert r.status_code == 200
    detail = r.json()
    assert detail['ticket_key'] == 'T-1'
    assert len(detail['transitions']) == 2
    assert detail['transitions'][1]['action'] == 'RETURN'
    assert detail['transitions'][1]['author'] == 'QA One'
    results['tickets_detail'] = 'OK'

    r = client.get('/api/competence/chart/volume')
    assert r.status_code == 200
    assert r.headers.get('content-type', '').startswith('text/html')
    assert 'plotly' in r.text.lower() or 'No data' in r.text
    results['chart_volume'] = 'OK'

    r = client.get('/api/competence/summary')
    assert r.status_code == 200
    summary = r.json()
    assert summary['total_tickets'] == 2
    assert summary['total_attempts'] == 2
    assert summary['total_returns'] == 1
    assert summary['data_available'] == True
    results['summary'] = 'OK'

    # Verify all 8 passed
    for name, status in results.items():
        assert status == 'OK', f'{name}: {status}'
    print(f'All {len(results)} endpoints OK')

if __name__ == '__main__':
    setup_test_db()
    test_all_endpoints()
    os.remove(DB_PATH)
    print('PASS: Phase 3 integration test complete')
```

Execute: `python test_phase3_integration.py`

DO NOT commit the test file — it's a one-time verification script. Delete it after execution.
  </action>
  <verify>
    <automated>python test_phase3_integration.py</automated>
  </verify>
  <done>All 8 endpoints return correct status codes and content types. M1 endpoints signatures preserved (D-07). New endpoints return data in FR10.1-FR10.4 shapes. Attribution data visible in /tickets and /tickets/{key} responses. No import errors. Test script passes and is deleted.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Client→API | HTTP requests to FastAPI routes — untrusted input (path params, query strings) |
| API→Jira | Outbound authenticated requests to Atlassian Cloud REST API — trusted target |
| API→SQLite | Local file-based database reads/writes — no network boundary |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-01 | Tampering | `GET /api/competence/tickets/{key}` path parameter | mitigate | FastAPI validates `{key}` as string type. SQL uses parameterized query (`WHERE ticket_key = ?`) — no string concatenation. SQL injection prevented by design. |
| T-03-02 | Information Disclosure | Credential logging in sync job error messages | mitigate | Existing `print()` statements in `_sync_job()` only log status codes and generic error messages. Ensure no `config.load_jira_config()` values (email/token) are echoed in error output. Verify during code review. |
| T-03-03 | Denial of Service | Concurrent sync requests overwhelming Jira API or event loop | mitigate | `in_progress` flag in `sync_state` prevents concurrent syncs (D-01 preserves this guard). `asyncio.Semaphore(5)` limits concurrent changelog HTTP requests to 5. Sufficient for single-user analytics tool. |
| T-03-04 | Tampering | Malformed `last_sync` value in sync_state causing invalid JQL | mitigate | `last_sync` is written by `_db_set_async` with `datetime.now(timezone.utc).isoformat()`. If corrupted, Jira API returns error (status 400) which is caught by `except HTTPException` handler. No SQL injection risk (parameterized). |
| T-03-SC | Tampering | npm/pip/cargo installs | accept | D-09: no new packages introduced. All dependencies (jira 3.10.5, httpx 0.28.1, pandas 2.1.1, plotly 6.6.0, fastapi 0.135.1) are existing, slopcheck-verified `[OK]` per RESEARCH.md Package Legitimacy Audit. No new install commands in this phase. |
</threat_model>

<verification>
## Automated verification commands

```bash
# 1. Verify module imports without errors
python -c "from app.plugins.competence import CompetencePlugin, _parse_changelog, _upsert_ticket_sync; print('Import OK')"

# 2. Unit test _parse_changelog (6 test cases)
python -c "
# ... embedded test from Task 2 ...
print('_parse_changelog OK')
"

# 3. Unit test _upsert_ticket_sync
python -c "
# ... embedded test from Task 3 ...
print('_upsert_ticket_sync OK')
"

# 4. Integration test — all 8 endpoints
python test_phase3_integration.py

# 5. Verify no syntax errors in the full file
python -m py_compile app/plugins/competence.py
```

## Manual verification steps (if server is running)

1. `curl http://localhost:8000/api/competence/summary` → returns JSON with total_* fields
2. `curl http://localhost:8000/api/competence/tickets` → returns JSON array with per-ticket stats
3. `curl http://localhost:8000/api/competence/tickets/T-1` → returns JSON with transitions array
4. `curl http://localhost:8000/api/competence/chart/volume` → returns HTML with Plotly chart
5. `curl http://localhost:8000/api/competence/stats` → returns JSON (unchanged from M1)
6. `curl http://localhost:8000/api/competence/chart` → returns HTML (unchanged from M1)
7. `curl -X POST http://localhost:8000/api/competence/sync` → returns `{status: "sync_started"}`
8. `curl http://localhost:8000/api/competence/sync/status` → returns `{last_sync, in_progress}`
</verification>

<success_criteria>
## Phase 3 Exit Criteria

1. **All 8 API endpoints respond correctly** — 4 M1 endpoints preserved (D-07), 4 new endpoints added (D-06). All return appropriate status codes and content types.
2. **Extended schema created on startup** — DROP+CREATE on first launch (D-01). transitions table has 8 columns with author/status attribution (D-02). tickets table exists with 4 columns (D-03). Idempotent on restart.
3. **Sync populates tickets table + extended transitions** — search_issues() fetches key+summary+issuetype (D-05, FR9). Tickets upserted via INSERT OR REPLACE. Transitions inserted with author_account_id, author_display_name, from_status, to_status (FR8).
4. **Attribution data visible in API responses** — /tickets shows last_return_by per ticket. /tickets/{key} shows author/from/to per transition. /summary shows most_returned tickets (D-08).
5. **Chart endpoints return valid Plotly HTML** — /chart (rate) preserved. /chart/volume returns dual-bar attempts vs returns chart with dark theme colors (NFR9, FR10.3).
6. **Summary endpoint returns correct aggregates** — total_tickets from transitions, total_attempts, total_returns, overall_rate_pct, top-5 most_returned (FR10.4, D-08).
7. **No new dependencies** — all packages already in requirements.txt (D-09).
8. **Code passes syntax check** — `python -m py_compile app/plugins/competence.py` succeeds.
9. **_load_transitions_df() updated for 8-column SELECT** — all existing endpoints continue working with the extended DataFrame (D-07, FR10.5).
</success_criteria>

<output>
## Deliverable

Single rewritten file: `app/plugins/competence.py` (~750 lines)

Structure (top to bottom):
1. Module docstring (updated for v2)
2. Imports (unchanged — all pre-existing packages per D-09)
3. Constants (unchanged)
4. Status sets (unchanged)
5. Module-level state (unchanged + `_upsert_ticket_sync` helper added)
6. `_get_jira_client()` (unchanged)
7. SQLite helpers: `_get_db`, `_db_get`, `_db_set`, `_db_get_async`, `_db_set_async` (unchanged) + `_upsert_ticket_sync`, `_db_upsert_ticket` (new)
8. HTTP helpers: `_get_client`, `_api_get`, `_api_post`, `_close_client` (unchanged)
9. `_parse_changelog()` — enhanced, signature changed (D-04)
10. `_format_2q_label()`, `_load_transitions_df()` — updated SELECT query
11. `_sync_job()` — enhanced with ticket metadata fetch + extended column insert (D-05, FR9)
12. `CompetencePlugin` class:
    - `register_routes()` — 4 M1 endpoints preserved + 4 new endpoints added (D-06, D-07)
    - `startup()` — rewritten with schema version check + DROP+CREATE (D-01, D-02, D-03)
    - `shutdown()` (unchanged)
13. `plugin = CompetencePlugin()` (unchanged)

When done, create `.planning/phase-3/SUMMARY.md` summarizing what was built, decisions made, and known limitations.
</output>
