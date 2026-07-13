# Feature Research

**Domain:** Insight / notification layer for an existing Jira worklog tracker (Alps Toolkit Jira Tracker, M4)
**Researched:** 2026-07-13
**Confidence:** MEDIUM (Clockify + Harvest feature pages fetched and verified; Toggl/Harvest/Tempo behaviors from training data — flagged LOW where unverified)

---

## Scope Note

This file covers ONLY the new Insight/Notification features for M4. The base tracker (Weekly View, Assigned tab, Config tab, worklog CRUD, meeting shortcut) is treated as an existing dependency, not re-researched. All complexity ratings are relative to that existing codebase.

---

## How Real Tools Do This (Grounding)

Pulled from live vendor feature pages + training knowledge. These inform what "table stakes" means.

| Tool | Relevant behavior | Source |
|------|-------------------|--------|
| **Clockify** | Timesheet has **Reminders** ("Reminder for due timesheets"); **Auto-tracker → Gaps** ("Identify gaps in productivity"); **Approval → Reminders** ("Send late timesheet reminders"); **Weekly** report type; **Time off / Holidays** module (define holidays, balances) | clockify.me/features (fetched, HIGH) |
| **Harvest** | **Custom reminders** ("Create automated reminders to help your team track time regularly and accurately"); **Activity log** ("review time entries and changes. Identify irregular or missing entries to ensure accuracy"); **Budget on target** (live budget vs tracked); capacity reporting | getharvest.com/features/time-tracking (fetched, HIGH) |
| **Toggl Track** | Saved reports + **weekly email digests**; **reminders** for unfilled time; project **progress vs estimate** dashboard; billable-rate targets | training (LOW–MED, unverified) |
| **Jira Tempo** | **Timesheet** with **missing-worklog highlighting**, **period target** (e.g. 40h contract), **fill-timesheet** nudges, approval workflow | training (LOW–MED, unverified) |
| **Generic timesheet SaaS** | "Ghost day" = a working day with zero entries; "under-target week" = sum < contract; end-of-week summary email; manager late-timesheet reminders | industry pattern (MED) |

**Cross-tool pattern:** detection (ghost days / missing entries) → summarize (week vs target) → notify (reminder/digest) → act (fill/submit). Tools separate *detecting* from *auto-filling* — none auto-write hours because that corrupts timesheet integrity. Harvest explicitly frames the activity log as "identify irregular or missing entries," not "fix them."

---

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes / Dependency on existing model |
|---------|--------------|------------|--------------------------------------|
| **Missed-day (ghost-day) detection** | Core ask; every timesheet tool flags zero-entry working days. | MED | Needs `date` + `time_spent_seconds` (both already in worklog dict). Group by day; a working day with 0s = missed. |
| **Under-target-week alert** | "am I below 40h?" is the headline question. | LOW–MED | Sum week's `time_spent_seconds`; compare to target. Reuses existing weekly endpoint payload. |
| **Configurable weekly target (default 40h)** | Users have different contracts; 40h is just a default. | LOW | NEW config field. Drives both detectors. |
| **In-app Insights tab** | A place to *see* the gaps, not just be told. | LOW (UI) | New tab; reads a detection endpoint. No new data needed beyond worklogs + target. |
| **Tab-bar badge when gaps exist** | At-a-glance "you have something to fix." | LOW | Pure UI state from detection result. Recomputes on tab open against cached data. |
| **Mark non-working days (holidays/PTO) that recalc target** | 40h→32h for a 4-day week is an explicit user requirement; without it the detector false-positives every short week. | MED–HIGH | NEW data (set of dates or per-week day-off flags). **Critical**: without this, under-target alert is useless on holiday weeks. See formula below. |
| **Working-day definition (default Mon–Fri)** | Week is Mon–Sun (7 days) per `_week_range`, but Sat/Sun must NOT count as "missed." | LOW–MED | Needed so ghost-day detection only fires on Mon–Fri (or user-defined) days. |
| **Toggleable browser notifications** | Users want the alert pushed, but also want it OFF. | MED | Notification API + permission prompt + NEW toggle in Config. Reuses detection output. |
| **Quick "fill missing day" action** | The natural payoff of detecting a gap. | MED | Reuses **existing** `POST /api/jira/worklog` (issue_key, time_spent, comment, started). UI just pre-fills date + suggested amount. |

**Target recalculation formula (core to the missed/under-target logic):**
```
expected_week_total = (target / default_working_days) * (working_days_this_week − non_working_days_this_week)
```
With target=40h, default_working_days=5, 4 working days (one marked off) → 32h. This is the model that makes "40h→32h" work and avoids false alerts on holiday weeks.

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Non-working-day-aware target (user-managed, local)** | Clockify's "Time off/Holidays" is team-admin context; here the user marks their own days off locally — simpler, faster, no approval chain. Directly delivers the user's 4-day-week example. | MED–HIGH | Builds on the table-stakes "mark non-working days" — the *local, personal* framing is the differentiator. |
| **Per-teammate gap view** | Tracker already has a teammates list + per-user weekly fetch. Peer/self gap spotting (not manager shaming) is unusual and cheap here. | MED | Reuses `teammates` config + existing per-account-id weekly fetch. |
| **One-click "top up short week" to meeting ticket** | Extends the existing meeting shortcut to a "fill the remaining hours" action. Very low cost, high delight. | LOW–MED | Reuses meeting endpoint + suggested delta = target − logged. |
| **Local-first instant insights** | Because M4 adds SQLite persistence + shared in-memory store, insights render with zero API call on tab switch — unlike cloud tools that need a refresh. | LOW | Depends on M4 persistence phase; differentiator vs SaaS refresh latency. |
| **Historical under-target trend / streak** | "3 of last 4 weeks under target" is motivating and only possible because we persist worklogs locally across weeks. | MED | Requires SQLite persistence (M4) + storing target config over time. |
| **Ghost-day drill-down** | Click a missed day → see what WAS logged that week / adjacent days, to judge if it's truly missing or just mis-logged. | LOW | UI-only; reads existing weekly payload. |

### Anti-Features (Commonly Requested, Often Problematic)

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| **Auto-logging hours for missed days** | "Just fill it for me." | Falsifies the timesheet; breaks audit/compliance integrity. Every real tool (Harvest activity log, Tempo) *identifies* missing entries but never *writes* them. | Draft + one-click confirm via existing worklog endpoint. |
| **Real-time "you're behind today" pop-ups every X min** | Micro-nudging seems helpful. | Notification fatigue kills adoption; defeats the "toggleable" value. | End-of-day or end-of-week digest only. |
| **Manager-facing enforcement / team shaming board** | "See who's slacking." | Not the use case (internal dev tool, self/peer view); privacy/trust risk. | Opt-in per-teammate view only. |
| **AI-estimated "expected hours" from history** | Smart targets sound impressive. | Misleading; averages ≠ contract; erodes trust in the number. | Explicit configured target + manual non-working-day marks. |
| **Cross-week deficit rollover** | "Carry the 8h I missed into next week." | Contracts are per-week; rollover confuses the alert and double-penalizes. | Independent per-week evaluation. |
| **Idle/away-time & screenshot tracking (Clockify Location/Screenshots)** | "Prove they worked." | Privacy-invasive, irrelevant for an internal Jira tool; banned by culture. | Out of scope entirely. |
| **Mobile push notifications** | Parity with SaaS apps. | The product is a browser SPA on an internal network; no mobile app. | Browser notifications only. |

---

## Feature Dependencies

```
[Insights Engine: detect missed days + under-target week]
    └──requires──> [Configurable weekly target (40h default)]
    └──requires──> [Working-day definition (Mon–Fri)]
    └──requires──> [Mark non-working days (holidays/PTO)]
                         └──enables──> [Target recalculation 40h→32h]

[Browser notifications (toggleable)]
    └──requires──> [Insights Engine output]
    └──requires──> [Notification permission + Config toggle]

[Tab-bar badge]
    └──requires──> [Insights Engine output]

[Gap-fill: fill missed day / top-up week]
    └──requires──> [Insights Engine (which day / how much)]
    └──reuses────> [POST /api/jira/worklog]  (existing endpoint)
    └──reuses────> [Meeting shortcut]        (for top-up action)

[Historical trend / streak]
    └──requires──> [SQLite local persistence]  (M4 separate phase)
    └──requires──> [Target config stored over time]

[Per-teammate gap view]
    └──reuses────> [teammates config]        (existing)
    └──reuses────> [per-account-id weekly fetch] (existing)

[Local-first instant insights]
    └──requires──> [Shared in-memory store across tabs]  (M4 UI redesign phase)
```

### Dependency Notes

- **Mark non-working days requires a NEW data store.** Existing schema has no field for "this date is a day off." Must be added (SQLite table or config blob). This is the single highest-leverage missing piece — without it the under-target detector cannot distinguish a holiday week from a lazy week.
- **Gap-fill is cheap BECAUSE the worklog endpoint already exists.** Do not build new Jira-write logic; wrap the existing `POST /api/jira/worklog` with date + suggested-amount pre-fill.
- **Historical trend depends on the M4 persistence phase, not on this feature set.** Sequence it after SQLite lands.
- **Timezone caveat (verify during build):** worklog `date` is derived as `started[:10]`, which is the **UTC** date from Jira (`+0000`). The milestone defines the week as Mon–Sun in **local** time. Late-evening logs can shift a day. The detection engine must normalize to local date before grouping, or ghost-day detection will mis-attribute entries. Flag for the implementation phase.

---

## MVP Definition

### Launch With (v1 — the insight core)

- [ ] Missed-day (ghost-day) detection — Mon–Fri only
- [ ] Under-target-week alert vs 40h default
- [ ] Configurable weekly target
- [ ] Working-day definition (Mon–Fri default)
- [ ] Mark non-working days + target recalculation
- [ ] In-app Insights tab
- [ ] Tab-bar badge
- [ ] Quick "fill missing day" (reuse existing endpoint)

### Add After Validation (v1.x)

- [ ] Toggleable browser notifications
- [ ] One-click "top up short week" to meeting ticket
- [ ] Per-teammate gap view
- [ ] Ghost-day drill-down

### Future Consideration (v2+, needs persistence)

- [ ] Historical under-target trend / streak
- [ ] Local-first instant insight refresh on tab switch (post UI-redesign)
- [ ] Smart-refresh only when cache invalidated

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Missed-day detection | HIGH | MED | P1 |
| Under-target-week alert | HIGH | LOW–MED | P1 |
| Configurable 40h target | HIGH | LOW | P1 |
| Mark non-working days + recalc | HIGH | MED–HIGH | P1 |
| Working-day definition (Mon–Fri) | HIGH | LOW–MED | P1 |
| Insights tab | HIGH | LOW | P1 |
| Tab-bar badge | MED | LOW | P1 |
| Quick fill-missed-day | HIGH | MED | P1 |
| Toggleable browser notifications | MED | MED | P2 |
| Top-up-short-week (meeting) | MED | LOW–MED | P2 |
| Per-teammate gap view | MED | MED | P2 |
| Ghost-day drill-down | LOW–MED | LOW | P2 |
| Historical trend / streak | MED | MED | P3 |
| Local-first instant insights | MED | LOW | P3 (post-redesign) |

**Priority key:** P1 = must have for launch · P2 = should have · P3 = future

---

## Competitor Feature Analysis

| Feature | Clockify | Harvest | Our Approach (Alps Jira Tracker) |
|---------|----------|---------|-----------------------------------|
| Ghost-day / missing-entry detection | Auto-tracker "Gaps" (productivity) | Activity log "identify missing entries" | Worklog-grouped ghost-day detection on Mon–Fri |
| Under-target alert | Weekly report + budget | Budget-on-target | Weekly sum vs configured 40h (recalc on day-off marks) |
| Reminders | Timesheet + approval reminders | Custom automated reminders | Toggleable browser notification + in-app badge |
| Non-working-day handling | Time off / Holidays (team-admin) | — | User-managed local day-off marks (no admin) |
| Fill-the-gap action | Manual timesheet entry | Manual + approval | One-click fill via existing worklog endpoint |
| Team visibility | Manager/team dashboards | Team capacity | Opt-in per-teammate peer view |

---

## Sources

- Clockify Features — https://www.clockify.me/features (fetched 2026-07-13, HIGH confidence): Timesheet Reminders, Auto-tracker "Gaps," Approval late-timesheet Reminders, Weekly reports, Time off/Holidays.
- Harvest Time Tracking — https://www.getharvest.com/features/time-tracking (fetched 2026-07-13, HIGH confidence): Custom reminders, Activity log ("identify irregular or missing entries"), Budget-on-target.
- Toggl Track / Jira Tempo behaviors — training knowledge only (LOW–MED, **unverified**; treat as hypothesis, validate in implementation phase if precise parity matters).
- Existing data model — `app/plugins/jira_tracker.py` (read): worklog dict has `date` (UTC-derived `started[:10]`), `time_spent_seconds`, `ticket_key`, `comment`; week = Mon–Sun via `_week_range`; `POST /api/jira/worklog` and meeting shortcut exist for gap-fill reuse.
- Project context — `.planning/PROJECT.md` M4 goal (local persistence, UI redesign, notifications, insights engine, gap-fill tools).

---

*Feature research for: Jira Tracker M4 Insight/Notification layer*
*Researched: 2026-07-13*
