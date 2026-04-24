"""
Log Parser plugin – Upload, parse, and analyse firmware log files.

Reuses modules/utils.py for the heavy parsing and chart generation.
Supports:
  • Plain .log, .txt files
  • .dmp files (processed via Easy Catcher adapter)
  • .zip archives containing .dmp files (auto-extracted & processed)
  • .clg files (passed through as-is for Catcher viewing)
  • Auto-saves parsed TXT & CLG to the source ticket folder
"""

from __future__ import annotations

import gzip
import io
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, Response, FileResponse
from pydantic import BaseModel

from app.plugins.base import ToolkitPlugin
from app import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules.utils import (
    parse_log,
    create_map,
    create_timeline,
    create_signal_chart,
    create_state_timeline,
)

ANALYSES_DIR = os.path.join(ROOT, "output", "analyses")
ANALYSES_INDEX = os.path.join(ANALYSES_DIR, "index.json")
MAX_RECENT = 30

_RX_TICKET = re.compile(r'[A-Z]{2,10}-\d+')

# ── Easy Catcher integration ───────────────────────────────────────

_easy_catcher_ok = False
_process_dumps = None
_ec_error = ""

try:
    from modules.easy_catcher_adapter import process_dumps as _ec_process_dumps
    _process_dumps = _ec_process_dumps
    _easy_catcher_ok = True
except Exception as e:
    _ec_error = str(e)


# ── Processing status (for async catcher jobs) ─────────────────────

_processing_jobs: dict[str, dict] = {}   # job_id -> {status, logs, result}
_processing_lock = threading.Lock()


# ── Ticket folder helpers ──────────────────────────────────────────

def _detect_ticket_from_filename(filename: str) -> str:
    """Try to find a JIRA ticket id from the filename or parent ticket folder."""
    cfg = config.load()
    tickets_root = cfg.get("tickets_folder", "")
    ticket_id = None

    if tickets_root and os.path.isdir(tickets_root):
        try:
            for entry in os.scandir(tickets_root):
                if entry.is_dir():
                    candidate = os.path.join(entry.path, filename)
                    if os.path.exists(candidate):
                        ticket_id = entry.name
                        break
        except Exception:
            pass

    if not ticket_id:
        m = _RX_TICKET.search(filename)
        if m:
            ticket_id = m.group(0)

    if '_' in filename:
        suffix = filename.rsplit('_', 1)[-1]
    else:
        suffix = filename

    return f"{ticket_id}: {suffix}" if ticket_id else suffix


def _find_ticket_folder_for_file(filename: str) -> str | None:
    """Find containing folder if *filename* exists inside a subdir of tickets_folder."""
    cfg = config.load()
    tickets_root = cfg.get("tickets_folder", "")
    if tickets_root and os.path.isdir(tickets_root):
        try:
            for entry in os.scandir(tickets_root):
                if entry.is_dir():
                    candidate = os.path.join(entry.path, filename)
                    if os.path.exists(candidate):
                        return entry.path
        except Exception:
            pass
    return None


def _find_clg_in_folder(folder_path: str) -> str | None:
    """Return path to the first .clg file in the folder."""
    if not folder_path or not os.path.isdir(folder_path):
        return None
    for f in os.listdir(folder_path):
        if f.lower().endswith('.clg'):
            return os.path.join(folder_path, f)
    return None


def _resolve_path(p: str) -> str:
    """Resolve a path relative to ROOT if it isn't absolute."""
    if not p:
        return p
    if os.path.isabs(p):
        return p
    return os.path.join(ROOT, p)


def _get_tool_paths() -> dict:
    """Return resolved tool paths for the Easy Catcher adapter."""
    cfg = config.load()
    return {
        'CATCHER_EXE': _resolve_path(cfg.get('catcher_path', '')),
        'CLG2TXT_EXE': _resolve_path(cfg.get('clg2txt_path', '')),
        'DB_PATH': cfg.get('db_path', ''),
    }


# ── Persistence helpers ─────────────────────────────────────────────

def _ensure_dir():
    os.makedirs(ANALYSES_DIR, exist_ok=True)


def _load_index() -> list[dict]:
    _ensure_dir()
    if not os.path.exists(ANALYSES_INDEX):
        return []
    try:
        with open(ANALYSES_INDEX, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_index(entries: list[dict]):
    _ensure_dir()
    with open(ANALYSES_INDEX, "w", encoding="utf-8") as f:
        json.dump(entries[:MAX_RECENT], f, indent=2)


def _save_analysis(raw: str, name: str, files: list[str],
                   catcher_work_dir: str | None = None,
                   parsed: dict | None = None) -> str:
    """Persist a parsed analysis (log content + pickle cache + catcher artifacts)."""
    _ensure_dir()
    aid = datetime.now().strftime("%Y%m%d_%H%M%S")
    adir = os.path.join(ANALYSES_DIR, aid)
    os.makedirs(adir, exist_ok=True)

    # 1. Compressed log content
    with gzip.open(os.path.join(adir, "log_content.gz"), "wt",
                   encoding="utf-8", compresslevel=6) as gz:
        gz.write(raw)

    # 2. Pickle cache
    if parsed:
        try:
            with gzip.open(os.path.join(adir, "parsed_data.pkl.gz"), "wb",
                           compresslevel=3) as gz:
                pickle.dump(parsed, gz, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            print(f"  [logs] Failed to save parsed cache: {e}")

    # 3. Copy catcher artifacts (CLG, LOG, DMP, TXT) into analysis dir
    artifacts_copied = []
    if catcher_work_dir and os.path.isdir(catcher_work_dir):
        parent = os.path.dirname(catcher_work_dir)
        for root, _, fnames in os.walk(parent):
            for fn in fnames:
                ext = os.path.splitext(fn)[1].lower()
                if ext in ('.clg', '.log', '.dmp', '.txt'):
                    src = os.path.join(root, fn)
                    dst = os.path.join(adir, fn)
                    if os.path.exists(dst):
                        base, e = os.path.splitext(fn)
                        dst = os.path.join(adir, f"{base}_{len(artifacts_copied)}{e}")
                    try:
                        shutil.copy2(src, dst)
                        artifacts_copied.append(fn)
                    except Exception:
                        pass

    # 4. Save metadata
    meta = {
        "id": aid, "name": name, "created": datetime.now().isoformat(),
        "source_files": files, "artifacts": artifacts_copied,
    }
    with open(os.path.join(adir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    idx = _load_index()
    idx.insert(0, meta)
    _save_index(idx)
    return aid


def _load_analysis(aid: str):
    adir = os.path.join(ANALYSES_DIR, aid)
    if not os.path.isdir(adir):
        return None, None, None

    meta = {}
    mp = os.path.join(adir, "meta.json")
    if os.path.exists(mp):
        with open(mp, "r") as f:
            meta = json.load(f)

    # Prefer pickle cache
    pkl = os.path.join(adir, "parsed_data.pkl.gz")
    if os.path.exists(pkl):
        try:
            with gzip.open(pkl, "rb") as gz:
                cached = pickle.load(gz)
            return None, meta, cached
        except Exception:
            pass

    gz = os.path.join(adir, "log_content.gz")
    content = None
    if os.path.exists(gz):
        with gzip.open(gz, "rt", encoding="utf-8") as g:
            content = g.read()
    return content, meta, None


# ── In-memory analysis store (current session) ──────────────────────

_analyses: dict[str, dict] = {}


def _get_parsed(aid: str) -> dict | None:
    if aid in _analyses:
        return _analyses[aid]

    content, meta, cached = _load_analysis(aid)
    if cached:
        _analyses[aid] = cached
        return cached

    if content:
        dp, ev, sl, mi = parse_log(content)
        data = {"data_points": dp, "events": ev, "structured_logs": sl, "modem_info": mi}
        _analyses[aid] = data
        return data

    return None


# ── Core upload processing (sync, runs in thread for heavy files) ──

def _process_upload(file_contents: list[tuple[str, bytes]], name: str,
                    job_id: str | None = None) -> dict:
    """Process uploaded file contents and return result dict.

    file_contents: list of (filename, raw_bytes) tuples.
    """
    def _log(msg):
        if job_id:
            with _processing_lock:
                job = _processing_jobs.get(job_id)
                if job:
                    job["logs"].append(str(msg))

    all_content = ""
    parsed_name_parts = []
    last_catcher_work_dir = None

    for fname, raw_bytes in file_contents:
        ext = os.path.splitext(fname)[1].lower()

        if ext == '.zip':
            # --- ZIP: extract and look for DMPs or plain logs ---
            if not _easy_catcher_ok:
                _log(f"Easy Catcher unavailable: {_ec_error}")
                # Fall through: extract plain log/txt files from zip
                try:
                    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                        for zi in sorted(zf.namelist()):
                            if zi.lower().endswith((".log", ".txt")):
                                all_content += zf.read(zi).decode(
                                    "utf-8", errors="replace") + "\n"
                                parsed_name_parts.append(zi)
                except Exception as e:
                    _log(f"Failed to extract zip: {e}")
                continue

            temp_root = tempfile.mkdtemp(prefix='modem_dbg_')
            extract_root = os.path.join(temp_root, 'extracted')
            process_root = os.path.join(temp_root, 'input')
            os.makedirs(extract_root, exist_ok=True)
            os.makedirs(process_root, exist_ok=True)

            zip_path = os.path.join(temp_root, fname)
            with open(zip_path, 'wb') as zf:
                zf.write(raw_bytes)

            try:
                with zipfile.ZipFile(zip_path, 'r') as archive:
                    for member in archive.infolist():
                        mp = Path(member.filename)
                        if member.is_dir() or mp.is_absolute() or '..' in mp.parts:
                            continue
                        archive.extract(member, extract_root)
            except Exception as e:
                _log(f"Failed to extract {fname}: {e}")
                shutil.rmtree(temp_root, ignore_errors=True)
                continue

            # Find .dmp files
            dmp_files = []
            for root, _, files in os.walk(extract_root):
                for fn in files:
                    if fn.lower().endswith('.dmp'):
                        dmp_files.append(os.path.join(root, fn))

            if not dmp_files:
                # No DMPs – extract plain text logs instead
                _log(f"No .dmp files in {fname}, trying plain text extraction")
                for root, _, files in os.walk(extract_root):
                    for fn in files:
                        if fn.lower().endswith(('.log', '.txt')):
                            try:
                                with open(os.path.join(root, fn), 'r',
                                          encoding='utf-8', errors='replace') as f:
                                    all_content += f.read() + "\n"
                                parsed_name_parts.append(fn)
                            except Exception:
                                pass
                shutil.rmtree(temp_root, ignore_errors=True)
                continue

            # Copy DMPs to process_root with sequential names
            for idx, dmp_file in enumerate(sorted(dmp_files), 1):
                dest = f"{idx:04d}_{os.path.basename(dmp_file)}"
                shutil.copy2(dmp_file, os.path.join(process_root, dest))

            # Run Easy Catcher
            tool_paths = _get_tool_paths()

            _log(f"Processing {len(dmp_files)} DMP files from {fname}...")
            output_log = _process_dumps(process_root, tool_paths, log_cb=_log)

            if not output_log or not os.path.exists(output_log):
                _log(f"Easy Catcher produced no output for {fname}")
                for dmp in dmp_files:
                    try:
                        with open(dmp, 'r', encoding='utf-8', errors='replace') as f:
                            all_content += f.read() + "\n"
                    except Exception:
                        pass
                parsed_name_parts.append(fname)
                shutil.rmtree(temp_root, ignore_errors=True)
                continue

            with open(output_log, 'r', encoding='utf-8', errors='replace') as lf:
                all_content += lf.read() + "\n"
            parsed_name_parts.append(f"{fname} -> {os.path.basename(output_log)}")
            last_catcher_work_dir = process_root

        elif ext == '.dmp':
            # --- Single .dmp → Easy Catcher processing ---
            if not _easy_catcher_ok:
                _log(f"Easy Catcher unavailable, reading DMP as text: {fname}")
                all_content += raw_bytes.decode("utf-8", errors="replace") + "\n"
                parsed_name_parts.append(fname)
                continue

            temp_root = tempfile.mkdtemp(prefix='modem_dbg_')
            process_root = os.path.join(temp_root, 'input')
            os.makedirs(process_root, exist_ok=True)

            dest = os.path.join(process_root, f"0001_{fname}")
            with open(dest, 'wb') as f:
                f.write(raw_bytes)

            tool_paths = _get_tool_paths()

            _log(f"Processing DMP: {fname}...")
            output_log = _process_dumps(process_root, tool_paths, log_cb=_log)

            if not output_log or not os.path.exists(output_log):
                _log(f"Easy Catcher failed for {fname}, reading as text")
                all_content += raw_bytes.decode("utf-8", errors="replace") + "\n"
                parsed_name_parts.append(fname)
                shutil.rmtree(temp_root, ignore_errors=True)
                continue

            with open(output_log, 'r', encoding='utf-8', errors='replace') as lf:
                all_content += lf.read() + "\n"
            parsed_name_parts.append(f"{fname} -> {os.path.basename(output_log)}")
            last_catcher_work_dir = process_root

        else:
            # --- Plain .log / .txt / .clg ---
            all_content += raw_bytes.decode("utf-8", errors="replace") + "\n"
            parsed_name_parts.append(fname)

    if not all_content.strip():
        raise ValueError("No parseable content found in uploaded files")

    # Parse
    _log("Parsing log content...")
    dp, ev, sl, mi = parse_log(all_content)
    parsed = {"data_points": dp, "events": ev, "structured_logs": sl, "modem_info": mi}

    # Determine display name
    display = name.strip() if name.strip() else " + ".join(parsed_name_parts)

    # Save analysis (with catcher artifacts)
    _log("Saving analysis...")
    aid = _save_analysis(all_content, display, parsed_name_parts,
                         catcher_work_dir=last_catcher_work_dir, parsed=parsed)
    _analyses[aid] = parsed

    # --- Auto-save TXT + CLG to ticket folder ---
    auto_saved = []
    if file_contents:
        first_fname = file_contents[0][0]
        src_folder = _find_ticket_folder_for_file(first_fname)
        if src_folder:
            try:
                base = os.path.splitext(first_fname)[0]
                # Save parsed TXT
                out_txt = os.path.join(src_folder, f"{base}_parsed.txt")
                with open(out_txt, 'w', encoding='utf-8') as f:
                    f.write(all_content)
                auto_saved.append(out_txt)
                _log(f"Auto-saved parsed log to: {out_txt}")

                # Save CLG if available from analysis dir
                adir = os.path.join(ANALYSES_DIR, aid)
                clg = _find_clg_in_folder(adir)
                if clg:
                    dest_clg = os.path.join(src_folder, f"{base}.clg")
                    shutil.copy2(clg, dest_clg)
                    auto_saved.append(dest_clg)
                    _log(f"Auto-saved CLG to: {dest_clg}")

                # Also check catcher work dir for CLG
                if not clg and last_catcher_work_dir:
                    parent = os.path.dirname(last_catcher_work_dir)
                    for root, _, fnames_in in os.walk(parent):
                        for fn in fnames_in:
                            if fn.lower().endswith('.clg'):
                                src_clg = os.path.join(root, fn)
                                dest_clg = os.path.join(src_folder, f"{base}.clg")
                                shutil.copy2(src_clg, dest_clg)
                                auto_saved.append(dest_clg)
                                _log(f"Auto-saved CLG to: {dest_clg}")
                                break
                        if auto_saved and auto_saved[-1].endswith('.clg'):
                            break
            except Exception as e:
                _log(f"Auto-save failed: {e}")

    # Cleanup temp dirs
    if last_catcher_work_dir:
        temp_root = os.path.dirname(last_catcher_work_dir)
        try:
            shutil.rmtree(temp_root, ignore_errors=True)
        except Exception:
            pass

    result = {
        "id": aid, "name": display,
        "file_count": len(parsed_name_parts),
        "record_count": len(dp),
        "events_count": len(ev),
        "at_commands_count": len(mi.get("at_commands", [])),
        "signal_count": len(mi.get("signal_readings", [])),
        "log_lines": len(sl),
        "auto_saved": auto_saved,
        "device_identity": mi.get("device_identity", {}),
    }

    if job_id:
        with _processing_lock:
            job = _processing_jobs.get(job_id)
            if job:
                job["status"] = "done"
                job["result"] = result

    return result


# ── Plugin ──────────────────────────────────────────────────────────

class LogParserPlugin(ToolkitPlugin):
    id = "logs"
    name = "Log Parser"
    icon = "🔍"
    order = 20

    def register_routes(self, app: FastAPI):

        @app.get("/api/logs/analyses")
        async def list_analyses():
            return _load_index()

        @app.post("/api/logs/parse")
        async def parse_upload(files: list[UploadFile] = File(...),
                               name: str = Form("")):
            """Upload files, parse them (with Easy Catcher if needed).

            Accepts .log, .txt, .dmp, .clg, .zip files.
            ZIP files containing .dmp files are processed via Easy Catcher.
            Returns immediately with a job_id for heavy processing, or
            the full result for plain files.
            """
            file_contents = []
            for file in files:
                raw_bytes = await file.read()
                fname = file.filename or "upload"
                file_contents.append((fname, raw_bytes))

            if not file_contents:
                raise HTTPException(400, "No files uploaded")

            # Auto-detect name from ticket folder if not provided
            if not name.strip():
                name = _detect_ticket_from_filename(file_contents[0][0])

            # Check if any file needs Easy Catcher (async processing)
            has_heavy = any(
                os.path.splitext(f)[1].lower() in ('.zip', '.dmp')
                for f, _ in file_contents
            )

            if has_heavy and _easy_catcher_ok:
                job_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                with _processing_lock:
                    _processing_jobs[job_id] = {
                        "status": "processing",
                        "logs": [],
                        "result": None,
                    }

                def _bg():
                    try:
                        _process_upload(file_contents, name, job_id=job_id)
                    except Exception as e:
                        with _processing_lock:
                            job = _processing_jobs.get(job_id)
                            if job:
                                job["status"] = "error"
                                job["logs"].append(f"ERROR: {e}")

                threading.Thread(target=_bg, daemon=True).start()
                return {"job_id": job_id, "status": "processing"}
            else:
                try:
                    result = _process_upload(file_contents, name)
                    return result
                except ValueError as e:
                    raise HTTPException(400, str(e))

        @app.get("/api/logs/parse/status/{job_id}")
        async def parse_status(job_id: str):
            """Check status of an async parse job (for DMP / ZIP processing)."""
            with _processing_lock:
                job = _processing_jobs.get(job_id)
            if not job:
                raise HTTPException(404, "Job not found")
            return {
                "status": job["status"],
                "logs": job["logs"][-30:],
                "result": job.get("result"),
            }

        @app.get("/api/logs/analysis/{aid}")
        async def get_analysis(aid: str):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404, "Analysis not found")
            meta = {}
            mp = os.path.join(ANALYSES_DIR, aid, "meta.json")
            if os.path.exists(mp):
                with open(mp, "r") as f:
                    meta = json.load(f)
            dp = parsed.get("data_points", [])
            ev = parsed.get("events", [])
            mi = parsed.get("modem_info", {})
            sl = parsed.get("structured_logs", [])
            return {
                "id": aid,
                "name": meta.get("name", aid),
                "file_count": len(meta.get("source_files", [])),
                "record_count": len(dp),
                "events_count": len(ev),
                "log_lines": len(sl),
                "signal_readings": len(mi.get("signal_readings", [])),
                "at_commands": len(mi.get("at_commands", [])),
                "records": len(mi.get("records", [])),
                "device_identity": mi.get("device_identity", {}),
                "artifacts": meta.get("artifacts", []),
                "auto_saved": meta.get("auto_saved", []),
            }

        @app.get("/api/logs/analysis/{aid}/events")
        async def get_events(aid: str, limit: int = 2000):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            return parsed.get("events", [])[:limit]

        @app.get("/api/logs/analysis/{aid}/data_points")
        async def get_data_points(aid: str, limit: int = 5000):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            return parsed.get("data_points", [])[:limit]

        @app.get("/api/logs/analysis/{aid}/at_commands")
        async def get_at_cmds(aid: str, limit: int = 5000):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            raw = parsed.get("modem_info", {}).get("at_commands", [])
            # Group by Group number into Command/Response pairs
            groups: dict[int, dict] = {}
            for entry in raw:
                g = entry.get("Group", 0)
                if g not in groups:
                    groups[g] = {
                        "Timestamp": entry.get("Timestamp", ""),
                        "Command": "", "Response": "",
                        "Category": entry.get("Category", ""),
                        "Description": entry.get("Description", ""),
                    }
                rec = groups[g]
                content = entry.get("Content", "")
                direction = entry.get("Direction", "")
                if direction == "CMD":
                    if rec["Command"]:
                        rec["Command"] += " | " + content
                    else:
                        rec["Command"] = content
                    rec["Category"] = entry.get("Category", rec["Category"])
                    rec["Description"] = entry.get("Description", rec["Description"])
                    if not rec["Timestamp"]:
                        rec["Timestamp"] = entry.get("Timestamp", "")
                else:
                    if rec["Response"]:
                        rec["Response"] += " | " + content
                    else:
                        rec["Response"] = content
                    if not rec["Timestamp"]:
                        rec["Timestamp"] = entry.get("Timestamp", "")
            result = list(groups.values())
            return result[:limit]

        @app.get("/api/logs/analysis/{aid}/records")
        async def get_records(aid: str):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            return parsed.get("modem_info", {}).get("records", [])

        @app.get("/api/logs/analysis/{aid}/signal")
        async def get_signal(aid: str):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            return parsed.get("modem_info", {}).get("signal_readings", [])

        @app.get("/api/logs/analysis/{aid}/logs")
        async def get_raw_logs(aid: str, limit: int = 5000, search: str = ""):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            logs = parsed.get("structured_logs", [])
            if search:
                q = search.lower()
                logs = [l for l in logs if q in l.get("Message", "").lower()
                        or q in l.get("Module", "").lower()]
            return logs[:limit]

        @app.get("/api/logs/analysis/{aid}/timeline", response_class=HTMLResponse)
        async def get_timeline_chart(aid: str):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            fig = create_timeline(parsed.get("events", []))
            if fig is None:
                return "<p>No events for timeline</p>"
            return fig.to_html(include_plotlyjs="cdn", full_html=False)

        @app.get("/api/logs/analysis/{aid}/signal_chart", response_class=HTMLResponse)
        async def get_signal_chart(aid: str):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            readings = parsed.get("modem_info", {}).get("signal_readings", [])
            fig = create_signal_chart(readings)
            if fig is None:
                return "<p>No signal data</p>"
            return fig.to_html(include_plotlyjs="cdn", full_html=False)

        @app.get("/api/logs/analysis/{aid}/state_timeline", response_class=HTMLResponse)
        async def get_state_timeline(aid: str):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            fig = create_state_timeline(parsed.get("events", []))
            if fig is None:
                return "<p>No state data</p>"
            return fig.to_html(include_plotlyjs="cdn", full_html=False)

        @app.get("/api/logs/analysis/{aid}/map", response_class=HTMLResponse)
        async def get_map(aid: str):
            parsed = _get_parsed(aid)
            if not parsed:
                raise HTTPException(404)
            dp = parsed.get("data_points", [])
            m = create_map(dp)
            if m is None:
                return "<p>No GPS data for map</p>"
            return m._repr_html_()

        @app.get("/api/logs/analysis/{aid}/download")
        async def download_parsed_txt(aid: str):
            """Download the parsed log content as a .txt file."""
            adir = os.path.join(ANALYSES_DIR, aid)
            gz_path = os.path.join(adir, "log_content.gz")
            if not os.path.exists(gz_path):
                raise HTTPException(404, "Log content not found")
            with gzip.open(gz_path, "rt", encoding="utf-8") as gz:
                content = gz.read()

            meta = {}
            mp = os.path.join(adir, "meta.json")
            if os.path.exists(mp):
                with open(mp, "r") as f:
                    meta = json.load(f)
            fname = (meta.get("name", aid) + "_parsed.txt").replace(" ", "_")

            return Response(
                content=content,
                media_type="text/plain",
                headers={"Content-Disposition": f'attachment; filename="{fname}"'},
            )

        @app.get("/api/logs/analysis/{aid}/artifacts")
        async def list_artifacts(aid: str):
            """List artifact files in the analysis directory."""
            adir = os.path.join(ANALYSES_DIR, aid)
            if not os.path.isdir(adir):
                raise HTTPException(404)
            artifacts = []
            skip = {'meta.json', 'log_content.gz', 'parsed_data.pkl.gz'}
            for fn in sorted(os.listdir(adir)):
                if fn in skip:
                    continue
                fp = os.path.join(adir, fn)
                artifacts.append({
                    "name": fn,
                    "size": os.path.getsize(fp),
                    "ext": os.path.splitext(fn)[1].lower(),
                })
            return artifacts

        @app.get("/api/logs/analysis/{aid}/artifact/{filename}")
        async def download_artifact(aid: str, filename: str):
            """Download a specific artifact file (CLG, DMP, etc.)."""
            fp = os.path.join(ANALYSES_DIR, aid, filename)
            if not os.path.exists(fp):
                raise HTTPException(404)
            return FileResponse(fp, filename=filename)

        @app.delete("/api/logs/analysis/{aid}")
        async def delete_analysis(aid: str):
            adir = os.path.join(ANALYSES_DIR, aid)
            if os.path.isdir(adir):
                shutil.rmtree(adir, ignore_errors=True)
            idx = _load_index()
            idx = [e for e in idx if e.get("id") != aid]
            _save_index(idx)
            _analyses.pop(aid, None)
            return {"ok": True}

        @app.put("/api/logs/analysis/{aid}/rename")
        async def rename_analysis(aid: str, new_name: str = Form(...)):
            mp = os.path.join(ANALYSES_DIR, aid, "meta.json")
            if os.path.exists(mp):
                with open(mp, "r") as f:
                    meta = json.load(f)
                meta["name"] = new_name
                with open(mp, "w") as f:
                    json.dump(meta, f, indent=2)
            idx = _load_index()
            for e in idx:
                if e.get("id") == aid:
                    e["name"] = new_name
            _save_index(idx)
            return {"ok": True}

        @app.post("/api/logs/launch_catcher/{aid}")
        async def launch_catcher(aid: str):
            """Launch Catcher.exe GUI with the CLG file from this analysis."""
            adir = os.path.join(ANALYSES_DIR, aid)
            if not os.path.isdir(adir):
                raise HTTPException(404, "Analysis not found")

            # Find a CLG file in the analysis dir
            clg_path = _find_clg_in_folder(adir)
            if not clg_path:
                raise HTTPException(404, "No CLG file found in this analysis")

            cfg = config.load()
            catcher_exe = _resolve_path(cfg.get("catcher_path", ""))
            if not catcher_exe or not os.path.exists(catcher_exe):
                raise HTTPException(400, f"Catcher.exe not found: {catcher_exe}")

            try:
                if os.name == 'nt':
                    subprocess.Popen(
                        [catcher_exe, clg_path],
                        cwd=os.path.dirname(catcher_exe),
                        creationflags=0x00000008,  # DETACHED_PROCESS
                        close_fds=True,
                    )
                else:
                    subprocess.Popen(
                        [catcher_exe, clg_path],
                        cwd=os.path.dirname(catcher_exe),
                        close_fds=True,
                    )
                return {"ok": True, "clg": os.path.basename(clg_path)}
            except Exception as e:
                raise HTTPException(500, f"Failed to launch Catcher: {e}")

        @app.post("/api/logs/analysis/{aid}/open_folder")
        async def open_folder(aid: str):
            """Open the analysis folder in the system file explorer."""
            adir = os.path.join(ANALYSES_DIR, aid)
            if not os.path.isdir(adir):
                raise HTTPException(404, "Analysis folder not found")
            try:
                if os.name == 'nt':
                    os.startfile(adir)
                else:
                    subprocess.Popen(['xdg-open', adir])
                return {"ok": True, "path": adir}
            except Exception as e:
                raise HTTPException(500, f"Failed to open folder: {e}")

        @app.get("/api/logs/catcher/status")
        async def catcher_status():
            """Check if Easy Catcher adapter is available."""
            return {
                "available": _easy_catcher_ok,
                "error": _ec_error if not _easy_catcher_ok else None,
            }

        @app.get("/api/logs/settings")
        async def logs_settings():
            """Return log-parser-related settings for the frontend."""
            cfg = config.load()
            return {
                "catcher_path": _resolve_path(cfg.get("catcher_path", "")),
                "clg2txt_path": _resolve_path(cfg.get("clg2txt_path", "")),
                "db_path": cfg.get("db_path", ""),
                "tickets_folder": cfg.get("tickets_folder", ""),
                "easy_catcher_ok": _easy_catcher_ok,
                "easy_catcher_error": _ec_error if not _easy_catcher_ok else None,
            }

        @app.put("/api/logs/settings")
        async def save_logs_settings(
            db_path: str = Form(None),
            tickets_folder: str = Form(None),
            catcher_path: str = Form(None),
            clg2txt_path: str = Form(None),
        ):
            """Save log-parser-related settings."""
            updates = {}
            if db_path is not None:
                updates["db_path"] = db_path
            if tickets_folder is not None:
                updates["tickets_folder"] = tickets_folder
            if catcher_path is not None:
                updates["catcher_path"] = catcher_path
            if clg2txt_path is not None:
                updates["clg2txt_path"] = clg2txt_path
            if updates:
                config.save(updates)
            return {"ok": True}


plugin = LogParserPlugin()
