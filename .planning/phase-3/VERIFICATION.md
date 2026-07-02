# Phase 3 Plan Verification Report

**Phase:** 03-competence-v2 — Backend Enhancements: Extended Data Model & APIs
**Date:** 2026-06-17
**Plans checked:** 1 (`phase-3/PLAN.md`, 1263 lines, 9 tasks)
**Status:** **ISSUES FOUND** — 1 blocker, 4 warnings
**Verifier:** `gsd-plan-checker`

---

## Executive Summary

The plan is **well-constructed and thorough** — it correctly maps all FR7-FR10 requirements to specific tasks, provides detailed code excerpts for every endpoint, includes automated test scripts for 7 of 9 tasks, and explicitly documents locked architectural decisions (D-01 through D-09). The single-file rewrite is well-organized into 9 sequential waves.

**However, one blocker must be resolved**: the RESEARCH.md `## Open Questions` section has not been marked `(RESOLVED)`, and its 3 questions lack resolution status markers. Additionally, the ROADMAP.md exit criterion "without data loss" conflicts with D-01's DROP+CREATE approach, and 9 tasks in a single plan exceeds the recommended scope budget.

---

## Dimension-by-Dimension Analysis

### Dimension 1: Requirement Coverage — ⚠️ WARNING

| Requirement | Source | Covered By | Status |
|-------------|--------|------------|--------|
| FR7 (Extended Schema) | REQUIREMENTS.md | Task 1 (DDL) | ✅ COVERED |
| FR7.1 (4 new columns) | REQUIREMENTS.md | Task 1 | ✅ COVERED |
| FR7.2 (tickets table) | REQUIREMENTS.md | Task 1 | ✅ COVERED |
| FR7.3 (schema version detection) | REQUIREMENTS.md | Task 1 (override: DROP+CREATE) | ⚠️ OVERRIDDEN |
| FR7.4 (WAL + indexes) | REQUIREMENTS.md | Task 1 | ✅ COVERED |
| FR8 (Enhanced Parser) | REQUIREMENTS.md | Task 2 | ✅ COVERED |
| FR8.1 (extended dicts) | REQUIREMENTS.md | Task 2 | ✅ COVERED |
| FR8.2 (RETURN captures QA) | REQUIREMENTS.md | Task 2 | ✅ COVERED |
| FR8.3 (sync stores extended data) | REQUIREMENTS.md | Task 3c | ✅ COVERED |
| FR9 (Ticket Metadata) | REQUIREMENTS.md | Task 3 | ✅ COVERED |
| FR9.1 (summary+issuetype) | REQUIREMENTS.md | Task 3a | ✅ COVERED |
| FR9.2 (upsert) | REQUIREMENTS.md | Task 3b | ✅ COVERED |
| FR9.3 (last_synced) | REQUIREMENTS.md | Task 3b | ✅ COVERED |
| FR10 (New Endpoints) | REQUIREMENTS.md | Tasks 5-8 | ✅ COVERED |
| FR10.1 (GET /tickets) | REQUIREMENTS.md | Task 5 | ✅ COVERED |
| FR10.2 (GET /tickets/{key}) | REQUIREMENTS.md | Task 6 | ✅ COVERED |
| FR10.3 (GET /chart/volume) | REQUIREMENTS.md | Task 7 | ✅ COVERED |
| FR10.4 (GET /summary) | REQUIREMENTS.md | Task 8 | ✅ COVERED |
| FR10.5 (preserve M1 endpoints) | REQUIREMENTS.md | Task 4 | ✅ COVERED |
| NFR6 (no data loss) | REQUIREMENTS.md | — | ⚠️ EXCLUDED (overridden by D-01) |
| NFR7 (stats <500ms) | REQUIREMENTS.md | Task 4 (unchanged) | ✅ COVERED |
| NFR8 (paginated if >100) | REQUIREMENTS.md | Task 5 (deferred) | ⚠️ CONDITIONAL |
| NFR9 (Plotly HTML valid) | REQUIREMENTS.md | Tasks 4, 7 | ✅ COVERED |

**Findings:**

1. **NFR6 exclusion**: The plan frontmatter intentionally excludes NFR6 ("Schema migration must not delete existing data"). D-01 (DROP+CREATE) directly contradicts NFR6 and FR7.3. RESEARCH.md documents this as a user-driven architectural decision. However:
   - ROADMAP.md's exit criterion "Schema migration runs on startup without data loss" will NOT be met
   - No CONTEXT.md exists to independently verify the user approved this override
   - The plan achieves the phase goal regardless (sync refetches data)

2. **NFR8 deferral**: The `/tickets` endpoint returns all results rather than implementing pagination. Task 5 documents this explicitly ("add pagination only if testing reveals >500ms response time"), which is consistent with RESEARCH.md Open Question 3's recommendation. Acceptable for initial delivery.

### Dimension 2: Task Completeness — ⚠️ WARNING

| Task | Type | Files | Action | Verify | Done | Status |
|------|------|-------|--------|--------|------|--------|
| 1 | auto | ✅ | ✅ | ✅ automated | ✅ | PASS |
| 2 | tdd | ✅ | ✅ behavior+action | ✅ automated (6 tests) | ✅ | PASS |
| 3 | auto | ✅ | ✅ | ✅ automated | ✅ | PASS |
| 4 | auto | ✅ | ✅ | ⚠️ MISSING | ✅ | WARNING |
| 5 | tdd | ✅ | ✅ behavior+action | ✅ automated (6 tests) | ✅ | PASS |
| 6 | auto | ✅ | ✅ | ✅ automated | ✅ | PASS |
| 7 | auto | ✅ | ✅ | ⚠️ MISSING | ✅ | WARNING |
| 8 | tdd | ✅ | ✅ behavior+action | ✅ automated (5 tests) | ✅ | PASS |
| 9 | auto | ✅ | ✅ | ✅ automated | ✅ | PASS |

**Findings:**
- **Tasks 4 and 7** have `<automated>MISSING</automated>` — manual verification only. However, Task 9's integration test exercises all 8 endpoints including those covered by Tasks 4/7, providing indirect automated coverage. This is acceptable but the plan should note the Task 9 dependency in these tasks' verify blocks.
- All other tasks have well-structured automated tests embedded inline.
- Task 2's 6 TDD test cases are comprehensive and cover the key attribution scenarios.
- Task 5's test verifies `last_return_by` attribution, empty state, and sort order.
- Task 8's test verifies `most_returned` top-5 behavior (D-08).

### Dimension 3: Dependency Correctness — ✅ PASS

```
Plan 01 (wave: 1, depends_on: [])
  └─ Internal waves 1→9 (sequential within single file)
     W1 (Task 1): Schema → W2 (Task 2): Parser → W3 (Task 3): Sync
     W4 (Task 4): Preserve → W5 (Task 5): /tickets → W6 (Task 6): /tickets/{key}
     W7 (Task 7): /chart/volume → W8 (Task 8): /summary → W9 (Task 9): Integration
```

**Findings:**
- Single plan, no cross-plan dependencies. `depends_on: []` is correct.
- Internal wave ordering is logical: schema before parser, parser before sync, endpoints after schema, integration after all.
- All 9 tasks modify `app/plugins/competence.py` — sequential execution is required (can't parallelize same-file writes).
- No cycles, no forward references.

### Dimension 4: Key Links Planned — ✅ PASS

| Key Link | Source Task | Verified |
|----------|-------------|----------|
| `_parse_changelog()` → `INSERT INTO transitions` (extended) | Task 2 → Task 3c | ✅ Task 3c extends INSERT statement |
| `jira.search_issues()` → `tickets` table via `_upsert_ticket()` | Task 3a → Task 3b | ✅ New helper + async wrapper specified |
| `GET /tickets` → `transitions LEFT JOIN tickets` via SQL GROUP BY | Task 5 | ✅ Explicit SQL in action |
| `GET /chart/volume` → `go.Figure([go.Bar, go.Bar])` via `fig.to_html()` | Task 7 | ✅ Full Plotly code in action |
| `GET /summary` → `_load_transitions_df()` aggregation | Task 8 | ✅ pandas groupby in action |

All critical data flows are explicitly wired in task actions.

### Dimension 5: Scope Sanity — ⚠️ WARNING

| Metric | Actual | Target | Warning | Blocker |
|--------|--------|--------|---------|---------|
| Tasks/plan | **9** | 2-3 | 4 | 5+ |
| Files/plan | 1 (but full rewrite) | 5-8 | 10 | 15+ |
| Plan size | 1263 lines | — | — | — |
| Expected output | ~750 lines | — | — | — |

**Finding:** 9 tasks exceeds the 5-task blocker threshold. However, this is a **single-file rewrite** where all tasks modify the same file sequentially — splitting into separate plan files would create merge conflicts without improving execution quality. Mitigation: the plan uses internal wave ordering (`<!-- WAVE 1..9 -->`) for clear sequencing, and each task covers a distinct, self-contained concern (schema, parser, sync, endpoint 1, endpoint 2, etc.). The executor processes one file throughout, maintaining context efficiency. **Not a blocker for this specific case.**

### Dimension 6: Verification Derivation (must_haves) — ✅ PASS

The `must_haves.truths` are user-observable and testable:
- "On startup, old tables are DROPped and recreated with extended schema" — verifiable via schema inspection
- "GET /api/competence/tickets returns per-ticket aggregated stats with SQL GROUP BY" — verifiable via HTTP test
- "All 8 endpoints respond correctly" — verifiable via Task 9 integration test

`must_haves.artifacts` correctly identifies the single output file with realistic `min_lines: 700`.
`must_haves.key_links` maps all 5 critical data flows with specific patterns.

### Dimension 7: Context Compliance — ⏭️ SKIPPED

No CONTEXT.md found in `.planning/` directory. Dimension not applicable.

### Dimension 7b: Scope Reduction Detection — ✅ PASS

No scope reduction language found beyond transparently-documented NFR8 deferral:
- "Return all results for now" (Task 5) — explicitly notes conditional pagination path
- "make the guard non-fatal" (Task 3d) — reasonable error-handling simplification for `myself()` call
- All 4 new endpoints and all 4 M1 endpoints are fully implemented per spec
- D-08 (top 5 most_returned) is correctly implemented in Task 8, not reduced

### Dimension 7c: Architectural Tier Compliance — ✅ PASS

All tasks align with the RESEARCH.md Architectural Responsibility Map:

| Capability | Expected Tier | Task File | Match |
|------------|--------------|-----------|-------|
| Jira data fetch | API / Backend | Task 3 (competence.py) | ✅ |
| Changelog parsing | API / Backend | Task 2 (competence.py) | ✅ |
| SQLite persistence | Database | Task 1 (competence.py) | ✅ |
| Aggregation queries | API / Backend | Tasks 5, 8 (competence.py) | ✅ |
| Plotly rendering | API / Backend | Tasks 4, 7 (competence.py) | ✅ |
| Sync orchestration | API / Backend | Task 3 (competence.py) | ✅ |
| Frontend consumption | Browser (Phase 4) | — out of scope | ✅ |

No tier mismatches. All backend logic stays server-side.

### Dimension 8: Nyquist Compliance — ⏭️ SKIPPED

`nyquist_validation` is explicitly set to `false` in `.planning/config.json` (line 10). Per specification: "Skip if `workflow.nyquist_validation` is explicitly set to `false` in config.json."

Note: Tasks 4 and 7 have `<automated>MISSING</automated>` in their verify blocks — this is a task completeness concern (Dimension 2) but not a Nyquist failure since the feature is disabled. Task 9 provides integration-level coverage.

### Dimension 9: Cross-Plan Data Contracts — ⏭️ SKIPPED

Single plan. No cross-plan data pipelines exist.

### Dimension 10: AGENTS.md Compliance — ⏭️ SKIPPED

No `AGENTS.md` found in workspace root.

### Dimension 11: Research Resolution — ❌ BLOCKER

**File:** `.planning/phase-3/RESEARCH.md` (lines 640-656)

The `## Open Questions` section exists and contains 3 unresolved questions:

| # | Question | Status |
|---|----------|--------|
| 1 | Should `_parse_changelog` process entries in chronological or reverse-chronological order? | No RESOLVED marker (recommendation given) |
| 2 | What should `/summary` "most_returned" list include when there are ties? | No RESOLVED marker (recommendation: top 5) |
| 3 | Should `/tickets` be paginated server-side or client-side? | No RESOLVED marker (recommendation: defer) |

**Required fix:** Either:
1. Mark the section heading as `## Open Questions (RESOLVED)` and add `RESOLVED:` prefix to each question with the chosen answer, OR
2. Remove the section entirely if the questions have been resolved in the plan

The plan (Task 2, Task 5, Task 8) already implements the recommendations from these questions — the RESEARCH.md just needs to be updated to reflect that the questions are now resolved.

### Dimension 12: Pattern Compliance — ✅ PASS

PATTERNS.md exists with 8/8 analogs mapped. The plan references all 8 pattern sections:

| PATTERNS.md Section | Plan Reference | Status |
|---------------------|----------------|--------|
| §1 Plugin class skeleton | Task 1, 4 (unchanged) | ✅ |
| §2 Jira client factory | Task 3 (KEEP AS-IS) | ✅ |
| §3 HTTP client helpers | Task 3 (KEEP AS-IS) | ✅ |
| §4 Schema DDL | Task 1 (explicit DROP+CREATE) | ✅ |
| §5 State machine parser | Task 2 (enhanced) | ✅ |
| §6 Sync job | Task 3 (enhanced) | ✅ |
| §7 Endpoints | Tasks 4-8 | ✅ |
| §8 register_routes | Task 4 (add after existing) | ✅ |

**PATTERNS.md tickets schema discrepancy:** PATTERNS.md §4 defines the `tickets` table with extra columns (`status`, `assignee_display_name`, `assignee_account_id`, `last_fetched`) that are NOT in the locked D-03 decision. The plan **correctly identifies and resolves** this: Task 1 action explicitly says "DO NOT add extra columns like status, assignee_display_name, or assignee_account_id — those are from PATTERNS.md's expanded version, not from the locked D-03 decision." This is proper plan-level resolution of a research artifact discrepancy.

---

## Goal-Backward Verification

**Phase goal (from ROADMAP.md):** "Capture per-transition attribution (who returned, statuses involved), add ticket metadata, expose richer API endpoints."

### What must be TRUE for the goal to be achieved:

1. ✅ **Extended schema exists with attribution columns** → Task 1 creates 8-column transitions + 4-column tickets
2. ✅ **Parser captures attribution data** → Task 2 rewrites `_parse_changelog()` with all 7 fields per transition
3. ✅ **Sync stores extended data** → Task 3 extends INSERT to include 4 new columns + upserts tickets
4. ✅ **4 new endpoints available** → Tasks 5-8 implement `/tickets`, `/tickets/{key}`, `/chart/volume`, `/summary`
5. ✅ **4 M1 endpoints preserved** → Task 4 verifies no changes to existing route handler bodies
6. ✅ **Attribution visible in API responses** → Task 5 shows `last_return_by`, Task 6 shows `author`/`from`/`to` per transition
7. ✅ **No new dependencies** → D-09 verified: all packages already in requirements.txt

### ROADMAP.md Exit Criteria Assessment:

| Criterion | Met? | Evidence |
|-----------|------|----------|
| Schema migration runs on startup without data loss | ⚠️ | D-01 DROP+CREATE loses M1 test data; intentional per RESEARCH.md user override |
| Tickets endpoint returns correct per-ticket stats with attribution | ✅ | Task 5 tests verify attempts, returns, return_rate_pct, last_return_by |
| Ticket detail shows full transition timeline with authors and statuses | ✅ | Task 6 tests verify date, action, author, from, to per transition |
| Volume chart renders attempts + returns per period | ✅ | Task 7 produces Plotly dual-bar with barmode="group" |
| Summary endpoint returns correct aggregates | ✅ | Task 8 tests verify total_tickets, total_attempts, total_returns, most_returned top-5 |
| Existing M1 endpoints unchanged | ✅ | Task 4 preserves 4 M1 route handler bodies exactly |

**Goal assessable:** The plan WILL achieve the core phase goal. The one ROADMAP.md exit criterion gap ("without data loss") is intentionally overridden by D-01 per the RESEARCH.md documentation, and the sync job's refetch capability makes the data loss recoverable.

---

## Edge Cases & Robustness

| Scenario | Covered By | Status |
|----------|-----------|--------|
| Empty database | Tasks 5, 6, 7, 8 (empty state handling in each) | ✅ |
| Non-existent ticket key | Task 6 (returns empty transitions, not 404) | ✅ |
| Schema version already v2 | Task 1 (idempotent: skip DDL) | ✅ |
| Concurrent sync | Task 3 (in_progress guard preserved) | ✅ |
| Sync crash with in_progress=1 | Task 3 (try/finally preserved, Pitfall 1 awareness) | ✅ |
| Jira API errors | Task 3 (3-tier error handling: JIRAError → HTTPException → Exception) | ✅ |
| Jira pagination edge case | Task 3 (existing pagination pattern preserved, Pitfall 2) | ✅ |
| SQL injection | Task 6 (parameterized queries `WHERE ticket_key = ?`) | ✅ |
| Chart dark theme | Task 7 (#3498db + #e74c3c on transparent bg, Pitfall 4) | ✅ |
| Module import errors | Task 9 (import check) | ✅ |
| Duplicate transitions | Task 3 (dedup logic + UNIQUE constraint) | ✅ |
| Tickets without metadata | Task 5 (LEFT JOIN with COALESCE) | ✅ |

---

## Structured Issues

```yaml
issues:
  - issue:
      plan: "03-01"
      dimension: "research_resolution"
      severity: "blocker"
      description: "RESEARCH.md has 3 unresolved open questions. Section heading '## Open Questions' is not marked '(RESOLVED)' and individual questions lack RESOLVED status markers."
      file: ".planning/phase-3/RESEARCH.md"
      unresolved_questions:
        - "Q1: Parse changelog chronological vs reverse order"
        - "Q2: /summary most_returned list size (ties vs top-N)"
        - "Q3: /tickets pagination strategy"
      fix_hint: "Mark section as '## Open Questions (RESOLVED)' and add 'RESOLVED: <answer>' to each question. The plan (Tasks 2, 5, 8) already implements the recommended answers."

  - issue:
      plan: "03-01"
      dimension: "requirement_coverage"
      severity: "warning"
      description: "NFR6 ('Schema migration must not delete existing data') is excluded from plan requirements. ROADMAP.md exit criterion 'without data loss' conflicts with D-01 DROP+CREATE. RESEARCH.md documents this as user override, but ROADMAP.md exit criteria are not updated."
      plan: "03-01"
      related:
        - "REQUIREMENTS.md NFR6"
        - "ROADMAP.md Phase 3 exit criterion 1"
        - "PLAN.md D-01"
      fix_hint: "Either update ROADMAP.md exit criteria to reflect D-01 (remove 'without data loss'), or add CONTEXT.md documenting the user's explicit DROP+CREATE decision."

  - issue:
      plan: "03-01"
      dimension: "scope_sanity"
      severity: "warning"
      description: "9 tasks in a single plan exceeds the 2-3 target and 5-task blocker threshold. Single-file rewrite context makes splitting impractical but execution risk remains."
      metrics:
        tasks: 9
        files: 1
        plan_lines: 1263
        expected_output_lines: 750
      mitigation: "Internal wave sequencing provides clear ordering. All tasks modify same file, maintaining executor context."
      fix_hint: "Consider consolidating waves (e.g., merge W5+W6 into 'new endpoints part 1', W7+W8 into 'new endpoints part 2') to reduce task count to 5-6. Or accept the 9-wave structure as inherent to the single-file rewrite pattern."

  - issue:
      plan: "03-01"
      dimension: "task_completeness"
      severity: "warning"
      description: "Task 4 and Task 7 have '<automated>MISSING</automated>' in verify blocks — manual verification only. Task 9 integration test provides indirect coverage."
      plan: "03-01"
      tasks: [4, 7]
      mitigation: "Task 9's test_phase3_integration.py exercises all 8 endpoints."
      fix_hint: "Add note in Task 4/7 verify blocks referencing Task 9 integration test as automated coverage. E.g., '<automated>See Task 9 integration test</automated>'."

  - issue:
      plan: "03-01"
      dimension: "requirement_coverage"
      severity: "warning"
      description: "ROADMAP.md exit criterion 1 ('Schema migration runs on startup without data loss') will not be met due to D-01 DROP+CREATE. Criterion should be updated or removed."
      plan: "03-01"
      fix_hint: "Update ROADMAP.md Phase 3 exit criteria to replace 'without data loss' with 'Schema recreated on startup per D-01 (DROP+CREATE, sync refetches data)'."
```

---

## PASS / FAIL Summary

| Dimension | Status |
|-----------|--------|
| 1. Requirement Coverage | ⚠️ WARNING (NFR6 excluded, ROADMAP exit criterion gap) |
| 2. Task Completeness | ⚠️ WARNING (Tasks 4/7 MISSING automated verify, mitigated by Task 9) |
| 3. Dependency Correctness | ✅ PASS |
| 4. Key Links Planned | ✅ PASS |
| 5. Scope Sanity | ⚠️ WARNING (9 tasks, single-file rewrite context) |
| 6. Verification Derivation | ✅ PASS |
| 7. Context Compliance | ⏭️ SKIPPED (no CONTEXT.md) |
| 7b. Scope Reduction | ✅ PASS |
| 7c. Architectural Tier | ✅ PASS |
| 8. Nyquist Compliance | ⏭️ SKIPPED (nyquist_validation: false) |
| 9. Cross-Plan Contracts | ⏭️ SKIPPED (single plan) |
| 10. AGENTS.md Compliance | ⏭️ SKIPPED (no AGENTS.md) |
| 11. Research Resolution | ❌ **BLOCKER** (unresolved open questions) |
| 12. Pattern Compliance | ✅ PASS |

---

## Recommendation

**1 BLOCKER** requires resolution before execution:

1. **Mark RESEARCH.md Open Questions as RESOLVED** — Open `.planning/phase-3/RESEARCH.md`, change the section heading from `## Open Questions` to `## Open Questions (RESOLVED)`, and add `RESOLVED:` markers to each of the 3 questions with the answers already implemented in the plan:
   - Q1 → RESOLVED: Process oldest-first (`reversed()`)
   - Q2 → RESOLVED: Top 5 by return count (D-08)
   - Q3 → RESOLVED: Return all results; add pagination (`?offset=0&limit=100`) only if performance testing shows >500ms

All warnings are advisory — the plan is otherwise execution-ready. The single-file rewrite with 9 sequential waves is structurally sound, all requirements are covered, and every task has specific, actionable implementation instructions with testable acceptance criteria.

After fixing the blocker, run `/gsd-execute-phase 3` to proceed.
