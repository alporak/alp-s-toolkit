"""
Alps Toolkit – FastAPI application factory with plugin auto-discovery.

Plugins are Python modules in app/plugins/ that expose a top-level `plugin`
attribute (an instance of ToolkitPlugin).  They are loaded alphabetically
and sorted by their `order` field.
"""

import importlib
import logging
import os
import pkgutil
import sys
from logging.handlers import RotatingFileHandler

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Ensure project root is importable
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ── File logging — captures crashes and warnings to disk ──────
LOG_DIR = os.path.join(ROOT_DIR, "output")
os.makedirs(LOG_DIR, exist_ok=True)
_file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "toolkit.log"),
    maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
))
logging.getLogger().addHandler(_file_handler)
logging.getLogger().setLevel(logging.INFO)

from app.plugins.base import ToolkitPlugin

_plugins: list[ToolkitPlugin] = []


def _discover_plugins() -> list[ToolkitPlugin]:
    """Import every module in app.plugins and collect `plugin` instances."""
    plugins_pkg = importlib.import_module("app.plugins")
    plugins_dir = os.path.dirname(plugins_pkg.__file__)
    found: list[ToolkitPlugin] = []

    for info in pkgutil.iter_modules([plugins_dir]):
        if info.name in ("__init__", "base"):
            continue
        try:
            mod = importlib.import_module(f"app.plugins.{info.name}")
            obj = getattr(mod, "plugin", None)
            if isinstance(obj, ToolkitPlugin):
                found.append(obj)
        except Exception as exc:
            print(f"[warn] Failed to load plugin '{info.name}': {exc}")

    found.sort(key=lambda p: p.order)
    return found


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Startup
    for p in _plugins:
        try:
            p.startup()
        except Exception as exc:
            print(f"[warn] Plugin {p.id} startup error: {exc}")
    yield
    # Shutdown
    for p in _plugins:
        try:
            p.shutdown()
        except Exception as exc:
            print(f"[warn] Plugin {p.id} shutdown error: {exc}")


def create_app() -> FastAPI:
    global _plugins

    app = FastAPI(title="Alps Toolkit", lifespan=_lifespan)

    # ── Discover & register plugins ──────────────────────────────────
    _plugins = _discover_plugins()
    for p in _plugins:
        p.register_routes(app)
        try:
            print(f"  {p.icon} {p.name} (/{p.id})")
        except UnicodeEncodeError:
            print(f"  ? {p.name} (/{p.id})")

    # ── API: plugin manifest for frontend navigation ─────────────────
    @app.get("/api/plugins")
    async def list_plugins():
        return [p.manifest() for p in _plugins]

    # ── API: toolkit settings ────────────────────────────────────────
    from app import config

    @app.get("/api/settings")
    async def get_settings():
        return config.load()

    @app.put("/api/settings")
    async def put_settings(body: dict):
        return config.save(body)

    # ── Serve static frontend ────────────────────────────────────────
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(static_dir, "index.html"))

    return app
