"""
Competence & Performance Plugin v2 — bug return rate analytics with per-ticket attribution.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

import httpx
import pandas as pd
import plotly.graph_objects as go
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from jira import JIRA, JIRAError

from app.plugins.base import ToolkitPlugin
from app import config

logger = logging.getLogger("competence")

# ── Constants ──────────────────────────────────────────────
DOMAIN = "teltonika-telematics.atlassian.net"
SERVER = f"https://{DOMAIN}"
DB_PATH = os.path.join(os.path.dirname(__file__), "competence_cache.db")
SCHEMA_VERSION = "3"

# ── State machine status sets ───────────────────────────────
DEV_STATES = {"In Development", "In Progress", "Gathering Information", "To Do", "New", "Open"}
HANDOFF_STATES = {"Developed"}
TEST_STATES = {"For Testing", "In Testing", "Release Verification", "Ready for Testing"}
FAIL_STATES = {"Test Failed", "Testing Failed", "Returned", "Reopened"}

# ── Module-level state ─────────────────────────────────────
_db_lock = threading.Lock()
_http_client: httpx.AsyncClient | None = None
_jira_client: JIRA | None = None


def _get_jira_client() -> JIRA:
    """Lazy-init a JIRA client from saved config."""
    global _jira_client
    if _jira_client is None:
        c = config.load_jira_config()
        _jira_client = JIRA(
            server=SERVER,
            basic_auth=(c.get("email", ""), c.get("token", "")),
        )
    return _jira_client


# ═══════════════════════════════════════════════════════════
#  SQLite helpers
# ═══════════════════════════════════════════════════════════

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _db_get(key: str) -> str | None:
    with _db_lock:
        conn = _get_db()
        try:
            row = conn.execute(
                "SELECT value FROM sync_state WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None
        finally:
            conn.close()


def _db_set(key: str, value: str) -> None:
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()


async def _db_get_async(key: str) -> str | None:
    return await asyncio.to_thread(_db_get, key)


async def _db_set_async(key: str, value: str) -> None:
    await asyncio.to_thread(_db_set, key, value)


# ═══════════════════════════════════════════════════════════
#  HTTP helpers (Jira REST API v2 via httpx)
# ═══════════════════════════════════════════════════════════

async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        c = config.load_jira_config()
        email = c.get("email", "")
        token = c.get("token", "")
        if not email or not token:
            raise HTTPException(503, "Jira credentials not configured")
        _http_client = httpx.AsyncClient(
            base_url=f"{SERVER}/rest/api/3/",
            auth=httpx.BasicAuth(email, token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=httpx.Timeout(30.0),
        )
    return _http_client


async def _api_get(path: str, **params) -> dict:
    client = await _get_client()
    resp = await client.get(path, params=params)
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()


async def _close_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


# ═══════════════════════════════════════════════════════════
#  State machine — changelog parsing (v2 with attribution)
# ═══════════════════════════════════════════════════════════

def _parse_changelog(
    changelog: dict,
    ticket_key: str,
    current_account_id: str,
) -> list[dict]:
    """Parse a Jira issue changelog into ATTEMPT / RETURN transitions.

    ATTEMPT: current user marks work as *Developed* (completes development).
             A single ticket can have multiple cycles of ATTEMPT→RETURN→ATTEMPT.
    RETURN:  ticket was attempted, then:
             - lands in a FAIL state (Test Failed, etc.), OR
             - QA bumps it from a TEST state back to a DEV state.

    Developer self-reverting (e.g. Developed → Gathering Information) is NOT a
    return — only external QA actions are.
    """
    transitions: list[dict] = []
    in_testing = False

    entries = list(changelog.get("values", []))
    entries.reverse()

    for entry in entries:
        author = entry.get("author") or {}
        author_id = author.get("accountId", "")
        author_name = author.get("displayName", "")
        created = entry.get("created", "")

        for item in entry.get("items", []):
            if item.get("field") != "status":
                continue

            from_status = item.get("fromString", "")
            to_status = item.get("toString", "")

            if not from_status or not to_status:
                continue

            # ── ATTEMPT: user hands off work (marks Developed) ──
            if (
                to_status in HANDOFF_STATES
                and author_id == current_account_id
            ):
                transitions.append({
                    "ticket_key": ticket_key,
                    "transition_date": created,
                    "action_type": "ATTEMPT",
                    "author_account_id": author_id,
                    "author_display_name": author_name,
                    "from_status": from_status,
                    "to_status": to_status,
                })
                in_testing = True

            # ── RETURN: external action after ATTEMPT ───────────
            elif in_testing:
                is_fail = to_status in FAIL_STATES
                is_qa_bounce = (
                    from_status in TEST_STATES
                    and to_status in DEV_STATES
                    and author_id != current_account_id
                )

                if is_fail or is_qa_bounce:
                    transitions.append({
                        "ticket_key": ticket_key,
                        "transition_date": created,
                        "action_type": "RETURN",
                        "author_account_id": author_id,
                        "author_display_name": author_name,
                        "from_status": from_status,
                        "to_status": to_status,
                    })
                    in_testing = False

    return transitions


# ═══════════════════════════════════════════════════════════
#  Stats helpers (pandas)
# ═══════════════════════════════════════════════════════════

def _format_quarter_label(period: pd.Period) -> str:
    return f"{period.year} Q{period.quarter}"


def _load_transitions_df() -> pd.DataFrame:
    """Read all transitions from SQLite into a pandas DataFrame."""
    conn = _get_db()
    try:
        df = pd.read_sql_query(
            "SELECT id, ticket_key, transition_date, action_type, "
            "author_account_id, author_display_name, from_status, to_status "
            "FROM transitions ORDER BY transition_date",
            conn,
            parse_dates=["transition_date"],
        )
    finally:
        conn.close()
    return df


def _load_filtered_df(account_id: str = "", date_from: str = "", date_to: str = "") -> pd.DataFrame:
    """Load transitions filtered by developer and/or date range."""
    conn = _get_db()
    try:
        clauses = ["1=1"]
        params = []
        if account_id:
            clauses.append("t.author_account_id = ?")
            params.append(account_id)
        if date_from:
            clauses.append("t.transition_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("t.transition_date <= ?")
            params.append(date_to + "T23:59:59")
        where = " AND ".join(clauses)
        df = pd.read_sql_query(
            f"SELECT t.id, t.ticket_key, t.transition_date, t.action_type, "
            f"t.author_account_id, t.author_display_name, t.from_status, t.to_status "
            f"FROM transitions t "
            f"INNER JOIN tickets tk ON tk.ticket_key = t.ticket_key AND tk.excluded = 0 "
            f"WHERE {where} ORDER BY t.transition_date",
            conn,
            params=params,
            parse_dates=["transition_date"],
        )
    finally:
        conn.close()
    return df


# ═══════════════════════════════════════════════════════════
#  Background sync engine (v2 with ticket metadata)
# ═══════════════════════════════════════════════════════════

def _upsert_ticket(key: str, summary: str, issue_type: str) -> None:
    """Insert or replace ticket metadata, preserving excluded flag."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO tickets (ticket_key, summary, issue_type, last_synced) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(ticket_key) DO UPDATE SET "
                "summary=excluded.summary, issue_type=excluded.issue_type, last_synced=excluded.last_synced",
                (key, summary, issue_type, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()


async def _sync_job(target_account_id: str = "") -> None:
    """Core sync pipeline. If *target_account_id* is given, syncs for that
    user; otherwise syncs for the current user."""
    if await _db_get_async("in_progress") == "1":
        logger.warning("Sync already in progress")
        return

    await _db_set_async("in_progress", "1")
    await _db_set_async("sync_progress", json.dumps({"phase": "starting"}))
    try:
        # ── 1. Identify target user ─────────────────────────
        if target_account_id:
            current_account_id = target_account_id
        else:
            try:
                myself = await asyncio.to_thread(_get_jira_client().myself)
                current_account_id = myself.get("accountId", "")
            except Exception as e:
                logger.error("Failed to get current user: %s (%s)", e, type(e).__name__)
                return
        if not current_account_id:
            logger.error("Could not determine accountId")
            return

        # ── 2. Build JQL ──────────────────────────────────────
        last_sync = await _db_get_async("last_sync")
        if target_account_id:
            base_jql = (
                f"assignee = {target_account_id} OR reporter = {target_account_id} "
                f"OR worklogAuthor = {target_account_id}"
            )
        else:
            base_jql = (
                "assignee = currentUser() OR reporter = currentUser() "
                "OR worklogAuthor = currentUser() OR assignee WAS currentUser() "
                "OR creator = currentUser()"
            )
        if last_sync:
            jql = f"({base_jql}) AND updated >= '{last_sync}'"
        else:
            jql = base_jql
        original_jql = jql

        # ── 3. Search + upsert ticket metadata (paginated) ────
        logger.info("Search JQL: %s", jql)
        await _db_set_async("sync_progress", json.dumps({"phase": "searching"}))
        all_issues: list[dict] = []

        next_page_token = None
        max_results = 100

        while True:
            try:
                client = await _get_client()
                payload = {
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": ["key", "summary", "issuetype"],
                }
                if next_page_token:
                    payload["nextPageToken"] = next_page_token

                resp = await client.post("search/jql", json=payload)
                if resp.status_code >= 400:
                    raise HTTPException(resp.status_code, resp.text)

                data = resp.json()
                batch = data.get("issues", [])

            except HTTPException:
                raise
            except Exception as e:
                logger.error("Search POST failed: %s (%s)", e, type(e).__name__)
                break

            if not batch:
                break

            for iss in batch:
                key = iss.get("key", "")
                if key:
                    all_issues.append({"key": key})
                fields_data = iss.get("fields", {}) or {}
                summary = fields_data.get("summary", "") or ""
                issuetype_data = fields_data.get("issuetype", {}) or {}
                itype = issuetype_data.get("name", "") or ""
                _upsert_ticket(key, summary, itype)

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

        issue_keys = [iss["key"] for iss in all_issues]

        # Fallback: if date filter returned 0 issues, retry full sync
        if not issue_keys and last_sync and original_jql != base_jql:
            logger.info("Incremental sync found 0 issues, retrying full sync...")
            jql = base_jql
            all_issues = []
            next_page_token = None

            while True:
                try:
                    client = await _get_client()
                    payload = {
                        "jql": jql,
                        "maxResults": max_results,
                        "fields": ["key", "summary", "issuetype"],
                    }
                    if next_page_token:
                        payload["nextPageToken"] = next_page_token

                    resp = await client.post("search/jql", json=payload)
                    if resp.status_code >= 400:
                        raise HTTPException(resp.status_code, resp.text)

                    data = resp.json()
                    batch = data.get("issues", [])

                except HTTPException:
                    raise
                except Exception as e:
                    logger.error("Full sync POST failed: %s (%s)", e, type(e).__name__)
                    break

                if not batch:
                    break

                for iss in batch:
                    key = iss.get("key", "")
                    if key:
                        all_issues.append({"key": key})
                    fields_data = iss.get("fields", {}) or {}
                    summary = fields_data.get("summary", "") or ""
                    issuetype_data = fields_data.get("issuetype", {}) or {}
                    itype = issuetype_data.get("name", "") or ""
                    _upsert_ticket(key, summary, itype)

                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break

            issue_keys = [iss["key"] for iss in all_issues]

        logger.info("Found %d issues to scan", len(issue_keys))

        # ── 4. Fetch changelogs with concurrency limit ────────
        semaphore = asyncio.Semaphore(5)
        total_issues = len(issue_keys)
        completed = [0]
        progress_lock = asyncio.Lock()

        async def _fetch_changelog(key: str) -> tuple[str, list[dict]]:
            async with semaphore:
                try:
                    entries: list[dict] = []
                    start = 0
                    page_size = 100
                    while True:
                        data = await _api_get(
                            f"issue/{key}/changelog",
                            maxResults=page_size,
                            startAt=start,
                        )
                        batch = data.get("values", [])
                        entries.extend(batch)
                        if len(batch) < page_size:
                            break
                        start += len(batch)
                    return key, entries
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.warning("Failed to fetch changelog for %s: %s", key, exc)
                    return key, []
                finally:
                    async with progress_lock:
                        completed[0] += 1
                        if completed[0] % 5 == 0 or completed[0] == total_issues:
                            await _db_set_async("sync_progress", json.dumps({
                                "phase": "fetching_changelogs",
                                "done": completed[0],
                                "total": total_issues,
                            }))

        tasks = [_fetch_changelog(key) for key in issue_keys]
        results = await asyncio.gather(*tasks)

        # ── 5. Parse changelogs ────────────────────────────────
        await _db_set_async("sync_progress", json.dumps({"phase": "parsing"}))
        all_transitions: list[dict] = []
        for key, entries in results:
            if not entries:
                continue
            parsed = _parse_changelog({"values": entries}, key, current_account_id)
            all_transitions.extend(parsed)

        # ── 6. Deduplicate & insert into SQLite ────────────────
        inserted = 0
        for t in all_transitions:
            with _db_lock:
                conn = _get_db()
                try:
                    existing = conn.execute(
                        "SELECT 1 FROM transitions "
                        "WHERE ticket_key = ? AND transition_date = ? "
                        "AND action_type = ?",
                        (t["ticket_key"], t["transition_date"], t["action_type"]),
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            "INSERT INTO transitions "
                            "(ticket_key, transition_date, action_type, "
                            "author_account_id, author_display_name, "
                            "from_status, to_status) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                t["ticket_key"],
                                t["transition_date"],
                                t["action_type"],
                                t.get("author_account_id", ""),
                                t.get("author_display_name", ""),
                                t.get("from_status", ""),
                                t.get("to_status", ""),
                            ),
                        )
                        conn.commit()
                        inserted += 1
                finally:
                    conn.close()

        # ── 7. Update last_sync only if we actually processed issues ──
        if inserted > 0:
            await _db_set_async("last_sync", datetime.now(timezone.utc).isoformat())

        logger.info(
            "Sync complete: %d issues, %d transitions (%d new)",
            len(issue_keys), len(all_transitions), inserted,
        )

    except HTTPException as e:
        logger.error("Sync error (HTTP): %s %s", e.status_code, e.detail)
    except JIRAError as e:
        logger.error("Sync error (Jira): %s %s", e.status_code, e.text if hasattr(e, 'text') else str(e))
    except Exception as e:
        logger.error("Sync failed (%s): %s", type(e).__name__, e)
    finally:
        await _db_set_async("in_progress", "0")


# ═══════════════════════════════════════════════════════════
#  Helper: 2Q aggregation iterator
# ═══════════════════════════════════════════════════════════

def _iter_2q_groups(df: pd.DataFrame):
    """Yield (period_label, attempts, returns, rate) for each 2Q group."""
    if df.empty:
        return
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["transition_date"]):
        df["transition_date"] = pd.to_datetime(df["transition_date"], utc=True)
    df = df.set_index("transition_date")
    df.index = pd.to_datetime(df.index, utc=True)
    grouped = df.groupby(pd.Grouper(freq="Q"))
    for period, group in grouped:
        attempts = int((group["action_type"] == "ATTEMPT").sum())
        returns = int((group["action_type"] == "RETURN").sum())
        rate = round((returns / attempts * 100), 1) if attempts > 0 else 0.0
        yield _format_quarter_label(period), attempts, returns, rate


# ═══════════════════════════════════════════════════════════
#  Plugin class
# ═══════════════════════════════════════════════════════════

class CompetencePlugin(ToolkitPlugin):
    id = "competence"
    name = "Competence Matrix"
    icon = "\U0001f4c8"
    order = 45

    # ── Route registration ──────────────────────────────────

    def register_routes(self, app: FastAPI) -> None:

        # ── M1 preserved endpoints ───────────────────────────

        @app.get("/api/competence/stats")
        async def competence_stats(
            account_id: str = "",
            date_from: str = "",
            date_to: str = "",
        ):
            try:
                df = _load_filtered_df(account_id, date_from, date_to)
                if df.empty:
                    return []
                return [
                    {"period": p, "attempts": a, "returns": r, "return_rate_pct": rt}
                    for p, a, r, rt in _iter_2q_groups(df)
                ]
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.post("/api/competence/sync")
        async def competence_sync(account_id: str = ""):
            try:
                in_progress = await _db_get_async("in_progress")
                if in_progress == "1":
                    return {
                        "status": "sync_already_running",
                        "message": "A sync job is already in progress.",
                    }
                asyncio.create_task(_sync_job(account_id))
                return {
                    "status": "sync_started",
                    "message": "Jira sync running in background.",
                }
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/api/competence/sync/status")
        async def competence_sync_status():
            try:
                last_sync = await _db_get_async("last_sync")
                in_progress = await _db_get_async("in_progress")
                progress_raw = await _db_get_async("sync_progress")
                progress = json.loads(progress_raw) if progress_raw else None
                return {
                    "last_sync": last_sync,
                    "in_progress": in_progress == "1",
                    "progress": progress,
                }
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/api/competence/teammates")
        async def competence_teammates():
            """Return list of known developers (self + teammates from jira_config)."""
            try:
                cfg = config.load_jira_config()
                teammates = cfg.get("teammates", []) or []
                myself = await asyncio.to_thread(_get_jira_client().myself)
                me = {
                    "accountId": myself.get("accountId", ""),
                    "displayName": myself.get("displayName", "Me"),
                }
                return [me] + [
                    {"accountId": t.get("accountId", ""), "displayName": t.get("displayName", "")}
                    for t in teammates
                ]
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/api/competence/chart", response_class=HTMLResponse)
        async def competence_chart(
            account_id: str = "",
            date_from: str = "",
            date_to: str = "",
        ):
            try:
                df = _load_filtered_df(account_id, date_from, date_to)
                if df.empty:
                    return (
                        "<p style='padding:40px;text-align:center;"
                        "color:var(--text-muted)'>"
                        "No data yet &mdash; click Sync Now to pull Jira changelogs."
                        "</p>"
                    )
                periods, rates = [], []
                for p, a, r, rt in _iter_2q_groups(df):
                    periods.append(p)
                    rates.append(rt)
                if not periods:
                    return "<p style='padding:40px;text-align:center;color:var(--text-muted)'>No data yet</p>"
                fig = go.Figure([
                    go.Bar(
                        x=periods, y=rates, marker_color="#e74c3c",
                        text=[f"{r}%" for r in rates], textposition="auto",
                        hovertemplate="%{x}<br>Return Rate: %{y}%<extra></extra>",
                    )
                ])
                max_rate = max(rates) if rates else 10
                fig.update_layout(
                    title="Bug Return Rate by Half-Year",
                    yaxis_title="Return Rate (%)", xaxis_title=None,
                    yaxis=dict(range=[0, max_rate * 1.2 if max_rate > 0 else 10]),
                    margin=dict(l=40, r=20, t=40, b=40), height=400,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#c9d1d9"),
                )
                html = fig.to_html(include_plotlyjs="cdn", full_html=False, config={"responsive": True})
                html += """<script>
                (function wait() {
                    var el = document.querySelector('.js-plotly-plot');
                    if (!el || !el._fullLayout) { setTimeout(wait, 100); return; }
                    el.on('plotly_click', function(data) {
                        if (data.points && data.points.length) {
                            parent.postMessage({
                                type: 'competence_period_click',
                                period: data.points[0].x
                            }, '*');
                        }
                    });
                    el.style.cursor = 'pointer';
                })();
                </script>"""
                return html
            except Exception as e:
                raise HTTPException(500, str(e))

        # ── V2 new endpoints ─────────────────────────────────

        @app.get("/api/competence/tickets")
        async def competence_tickets(
            account_id: str = "",
            date_from: str = "",
            date_to: str = "",
        ):
            """Per-ticket aggregated stats with attribution."""
            try:
                clauses = ["1=1"]
                params: list = []
                if account_id:
                    clauses.append("t.author_account_id = ?")
                    params.append(account_id)
                if date_from:
                    clauses.append("t.transition_date >= ?")
                    params.append(date_from)
                if date_to:
                    clauses.append("t.transition_date <= ?")
                    params.append(date_to + "T23:59:59")

                with _db_lock:
                    conn = _get_db()
                    try:
                        rows = conn.execute(f"""
                            SELECT
                                t.ticket_key,
                                tk.summary,
                                tk.issue_type,
                                tk.excluded,
                                SUM(CASE WHEN t.action_type = 'ATTEMPT' THEN 1 ELSE 0 END) AS attempts,
                                SUM(CASE WHEN t.action_type = 'RETURN' THEN 1 ELSE 0 END) AS returns,
                                MAX(CASE WHEN t.action_type = 'RETURN' THEN t.transition_date END) AS last_return_date,
                                (SELECT t2.author_display_name
                                 FROM transitions t2
                                 WHERE t2.ticket_key = t.ticket_key
                                   AND t2.action_type = 'RETURN'
                                 ORDER BY t2.transition_date DESC
                                 LIMIT 1) AS last_return_by
                            FROM transitions t
                            LEFT JOIN tickets tk ON tk.ticket_key = t.ticket_key
                            WHERE {' AND '.join(clauses)}
                            GROUP BY t.ticket_key
                            ORDER BY returns DESC, attempts DESC
                        """, params).fetchall()
                    finally:
                        conn.close()

                result = []
                for row in rows:
                    attempts = row["attempts"] or 0
                    returns = row["returns"] or 0
                    rate = round((returns / attempts * 100), 1) if attempts > 0 else 0.0
                    result.append({
                        "ticket_key": row["ticket_key"],
                        "summary": row["summary"] or "",
                        "issue_type": row["issue_type"] or "",
                        "attempts": attempts,
                        "returns": returns,
                        "return_rate_pct": rate,
                        "last_return_date": row["last_return_date"],
                        "last_return_by": row["last_return_by"] or "",
                        "excluded": bool(row["excluded"]) if "excluded" in row.keys() else False,
                    })
                return result
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/api/competence/tickets/{key}")
        async def competence_ticket_detail(key: str):
            """Single-ticket transition timeline with full attribution."""
            try:
                with _db_lock:
                    conn = _get_db()
                    try:
                        ticket_row = conn.execute(
                            "SELECT summary, issue_type FROM tickets WHERE ticket_key = ?",
                            (key,),
                        ).fetchone()
                        transition_rows = conn.execute(
                            "SELECT transition_date, action_type, "
                            "author_display_name, from_status, to_status "
                            "FROM transitions WHERE ticket_key = ? "
                            "ORDER BY transition_date ASC",
                            (key,),
                        ).fetchall()
                    finally:
                        conn.close()

                if not ticket_row and not transition_rows:
                    raise HTTPException(404, f"Ticket {key} not found")

                return {
                    "ticket_key": key,
                    "summary": ticket_row["summary"] if ticket_row else "",
                    "issue_type": ticket_row["issue_type"] if ticket_row else "",
                    "transitions": [
                        {
                            "date": tr["transition_date"],
                            "action": tr["action_type"],
                            "author": tr["author_display_name"] or "",
                            "from": tr["from_status"] or "",
                            "to": tr["to_status"] or "",
                        }
                        for tr in transition_rows
                    ],
                }
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.post("/api/competence/tickets/{key}/exclude")
        async def competence_ticket_toggle_exclude(key: str):
            """Toggle exclusion flag for a ticket."""
            try:
                with _db_lock:
                    conn = _get_db()
                    try:
                        conn.execute(
                            "INSERT INTO tickets (ticket_key, excluded) VALUES (?, 1) "
                            "ON CONFLICT(ticket_key) DO UPDATE SET "
                            "excluded = CASE WHEN tickets.excluded = 1 THEN 0 ELSE 1 END",
                            (key,),
                        )
                        conn.commit()
                        row = conn.execute(
                            "SELECT excluded FROM tickets WHERE ticket_key = ?", (key,)
                        ).fetchone()
                    finally:
                        conn.close()
                return {"ticket_key": key, "excluded": bool(row["excluded"]) if row else False}
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/api/competence/quarterly_details")
        async def competence_quarterly_details(
            account_id: str = "",
            date_from: str = "",
            date_to: str = "",
        ):
            """Per-period breakdown with per-ticket counts."""
            try:
                df = _load_filtered_df(account_id, date_from, date_to)
                if df.empty:
                    return []

                if not pd.api.types.is_datetime64_any_dtype(df["transition_date"]):
                    df["transition_date"] = pd.to_datetime(df["transition_date"], utc=True)
                df = df.set_index("transition_date")
                df.index = pd.to_datetime(df.index, utc=True)
                grouped = df.groupby(pd.Grouper(freq="Q"))

                result: list[dict] = []
                for period, group in grouped:
                    period_attempts = int((group["action_type"] == "ATTEMPT").sum())
                    period_returns = int((group["action_type"] == "RETURN").sum())
                    rate = (
                        round((period_returns / period_attempts * 100), 1)
                        if period_attempts > 0
                        else 0.0
                    )

                    ticket_groups = group.groupby("ticket_key")
                    tickets: list[dict] = []
                    for key, tg in ticket_groups:
                        ta = int((tg["action_type"] == "ATTEMPT").sum())
                        tr = int((tg["action_type"] == "RETURN").sum())
                        tickets.append({
                            "ticket_key": key,
                            "attempts": ta,
                            "returns": tr,
                        })
                    tickets.sort(key=lambda x: (-x["returns"], -x["attempts"]))

                    result.append({
                        "period": _format_quarter_label(period),
                        "total_attempts": period_attempts,
                        "total_returns": period_returns,
                        "rate": rate,
                        "tickets": tickets,
                    })

                return result
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/api/competence/chart/volume", response_class=HTMLResponse)
        async def competence_chart_volume(
            account_id: str = "",
            date_from: str = "",
            date_to: str = "",
        ):
            """Dual-bar Plotly chart: attempts vs returns per 2Q period."""
            try:
                df = _load_filtered_df(account_id, date_from, date_to)
                if df.empty:
                    return (
                        "<p style='padding:40px;text-align:center;"
                        "color:var(--text-muted)'>"
                        "No data yet &mdash; click Sync Now to pull Jira changelogs."
                        "</p>"
                    )
                periods, attempt_counts, return_counts = [], [], []
                for p, a, r, _rt in _iter_2q_groups(df):
                    periods.append(p)
                    attempt_counts.append(a)
                    return_counts.append(r)
                if not periods:
                    return "<p style='padding:40px;text-align:center;color:var(--text-muted)'>No data yet</p>"

                fig = go.Figure([
                    go.Bar(
                        name="Attempts", x=periods, y=attempt_counts,
                        marker_color="#3498db",
                        text=attempt_counts, textposition="auto",
                        hovertemplate="%{x}<br>Attempts: %{y}<extra></extra>",
                    ),
                    go.Bar(
                        name="Returns", x=periods, y=return_counts,
                        marker_color="#e74c3c",
                        text=return_counts, textposition="auto",
                        hovertemplate="%{x}<br>Returns: %{y}<extra></extra>",
                    ),
                ])
                fig.update_layout(
                    title="Attempts vs Returns Volume by Half-Year",
                    barmode="group",
                    yaxis_title="Count", xaxis_title=None,
                    margin=dict(l=40, r=20, t=40, b=40), height=400,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#c9d1d9"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                html = fig.to_html(include_plotlyjs="cdn", full_html=False, config={"responsive": True})
                html += """<script>
                (function wait() {
                    var el = document.querySelector('.js-plotly-plot');
                    if (!el || !el._fullLayout) { setTimeout(wait, 100); return; }
                    el.on('plotly_click', function(data) {
                        if (data.points && data.points.length) {
                            parent.postMessage({
                                type: 'competence_period_click',
                                period: data.points[0].x
                            }, '*');
                        }
                    });
                    el.style.cursor = 'pointer';
                })();
                </script>"""
                return html
            except Exception as e:
                raise HTTPException(500, str(e))

        @app.get("/api/competence/summary")
        async def competence_summary(
            account_id: str = "",
            date_from: str = "",
            date_to: str = "",
        ):
            """Overall aggregate stats + top 5 most-returned tickets."""
            try:
                clauses = ["(tk.ticket_key IS NULL OR tk.excluded = 0)"]
                params: list = []
                if account_id:
                    clauses.append("t.author_account_id = ?")
                    params.append(account_id)
                if date_from:
                    clauses.append("t.transition_date >= ?")
                    params.append(date_from)
                if date_to:
                    clauses.append("t.transition_date <= ?")
                    params.append(date_to + "T23:59:59")
                where = " AND ".join(clauses)

                with _db_lock:
                    conn = _get_db()
                    try:
                        totals = conn.execute(f"""
                            SELECT
                                COUNT(DISTINCT t.ticket_key) AS total_tickets,
                                SUM(CASE WHEN t.action_type = 'ATTEMPT' THEN 1 ELSE 0 END) AS total_attempts,
                                SUM(CASE WHEN t.action_type = 'RETURN' THEN 1 ELSE 0 END) AS total_returns
                            FROM transitions t
                            LEFT JOIN tickets tk ON tk.ticket_key = t.ticket_key
                            WHERE {where}
                        """, params).fetchone()

                        most = conn.execute(f"""
                            SELECT
                                t.ticket_key,
                                tk.summary,
                                COUNT(*) AS returns
                            FROM transitions t
                            LEFT JOIN tickets tk ON tk.ticket_key = t.ticket_key
                            WHERE t.action_type = 'RETURN' AND {where}
                            GROUP BY t.ticket_key
                            ORDER BY returns DESC
                            LIMIT 5
                        """, params).fetchall()
                    finally:
                        conn.close()

                total_tickets = totals["total_tickets"] or 0
                total_attempts = totals["total_attempts"] or 0
                total_returns = totals["total_returns"] or 0
                overall_rate = (
                    round((total_returns / total_attempts * 100), 1)
                    if total_attempts > 0
                    else 0.0
                )

                return {
                    "total_tickets": total_tickets,
                    "total_attempts": total_attempts,
                    "total_returns": total_returns,
                    "overall_rate_pct": overall_rate,
                    "most_returned": [
                        {"key": m["ticket_key"], "summary": m["summary"] or "", "returns": m["returns"]}
                        for m in most
                    ],
                }
            except Exception as e:
                raise HTTPException(500, str(e))

    # ── Lifecycle hooks ─────────────────────────────────────

    def startup(self) -> None:
        """DROP old schema and CREATE fresh v2 tables."""
        try:
            with _db_lock:
                conn = _get_db()
                try:
                    conn.execute("CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT)")
                    conn.commit()

                    current_ver = conn.execute(
                        "SELECT value FROM sync_state WHERE key = 'schema_version'"
                    ).fetchone()
                    if current_ver and current_ver["value"] == SCHEMA_VERSION:
                        conn.close()
                        logger.info("Schema v%s already initialized", SCHEMA_VERSION)
                        return

                    conn.executescript("""
                        DROP TABLE IF EXISTS transitions;
                        DROP TABLE IF EXISTS tickets;

                        CREATE TABLE transitions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ticket_key       TEXT NOT NULL,
                            transition_date  TEXT NOT NULL,
                            action_type      TEXT NOT NULL
                                CHECK(action_type IN ('ATTEMPT', 'RETURN')),
                            author_account_id   TEXT NOT NULL DEFAULT '',
                            author_display_name TEXT NOT NULL DEFAULT '',
                            from_status         TEXT NOT NULL DEFAULT '',
                            to_status           TEXT NOT NULL DEFAULT ''
                        );

                        CREATE TABLE tickets (
                            ticket_key  TEXT PRIMARY KEY,
                            summary     TEXT NOT NULL DEFAULT '',
                            issue_type  TEXT NOT NULL DEFAULT '',
                            last_synced TEXT NOT NULL DEFAULT '',
                            excluded    INTEGER NOT NULL DEFAULT 0
                        );

                        CREATE INDEX IF NOT EXISTS idx_transitions_date
                            ON transitions(transition_date);
                        CREATE INDEX IF NOT EXISTS idx_transitions_ticket
                            ON transitions(ticket_key);

                        INSERT OR REPLACE INTO sync_state (key, value)
                            VALUES ('schema_version', '3');
                        DELETE FROM sync_state WHERE key IN ('last_sync', 'in_progress', 'sync_progress');
                    """)
                    conn.commit()
                finally:
                    conn.close()
            logger.info("SQLite v%s initialized at %s", SCHEMA_VERSION, DB_PATH)
        except Exception as e:
            logger.warning("Competence plugin DB init failed: %s", e)

    def shutdown(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_close_client())
        except RuntimeError:
            pass


# ── Auto-discovery singleton ────────────────────────────────────
plugin = CompetencePlugin()
