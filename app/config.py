"""
Alps Toolkit – Configuration manager.

Single source of truth for toolkit_settings.json.
Thread-safe read/write with in-memory caching.
"""

import json
import os
import threading
from typing import Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT_DIR, "toolkit_settings.json")

_lock = threading.Lock()
_cache: dict | None = None

DEFAULTS: dict[str, Any] = {
    "server_port": 8000,
    "server_protocol": "TCP",
    "server_tls_enabled": False,
    "server_tls_cert_path": "",
    "server_tls_key_path": "",
    "server_tls_ca_path": "",
    "server_tls_verify_client": False,
    "server_https_response_enabled": False,
    "server_https_response_body": '{"status":"ok","server":"alps-toolkit"}',
    "avl_ids_path": "",
    "catcher_path": os.path.join(ROOT_DIR, "third_party", "easy-catcher", "catcher_mod", "Catcher.exe"),
    "clg2txt_path": os.path.join(ROOT_DIR, "third_party", "easy-catcher", "catcher_mod", "Clg2Txt.exe"),
    "db_path": "",
    "tickets_folder": "",
    "jira_base_url": "https://teltonika-telematics.atlassian.net",
    "universal_tester_tool_path": os.path.join(ROOT_DIR, "third_party", "universal-tester-tool"),
    "universal_tester_tool_log_dir": os.path.join(ROOT_DIR, "output", "universal_tester_tool_logs"),
    "doc_repos": [],
}

JIRA_CFG_PATH = os.path.join(ROOT_DIR, "third_party", "jira-time-tracker", "jira_config.json")


def load() -> dict:
    """Return current config (cached). Thread-safe."""
    global _cache
    with _lock:
        if _cache is not None:
            return dict(_cache)
    return _read_disk()


def _read_disk() -> dict:
    global _cache
    cfg = dict(DEFAULTS)
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cfg.update(raw)
    except Exception:
        pass
    with _lock:
        _cache = cfg
    return dict(cfg)


def save(updates: dict) -> dict:
    """Merge *updates* into persisted config and return new config."""
    global _cache
    cfg = load()
    cfg.update(updates)
    with _lock:
        _cache = cfg
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        print(f"Config save error: {e}")
    return dict(cfg)


def invalidate():
    """Force next load() to re-read disk."""
    global _cache
    with _lock:
        _cache = None


# ── Jira credentials helpers ───────────────────────────────────────

def load_jira_config() -> dict:
    if os.path.exists(JIRA_CFG_PATH):
        try:
            with open(JIRA_CFG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_jira_config(cfg: dict):
    os.makedirs(os.path.dirname(JIRA_CFG_PATH), exist_ok=True)
    with open(JIRA_CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

