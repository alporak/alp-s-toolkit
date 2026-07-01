"""
Unit tests for doc_search sync engine (Plan 06-01).

Covers: config loading, git subprocess safety, sync state helpers,
in-progress guard, incremental hash comparison, FTS5 upsert,
deleted-file cleanup, and full sync orchestration.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ── These imports will be available after GREEN implementation ──
# (Task 1 functions)
from app.plugins.doc_search import (
    _load_doc_repos,
    _git_pull,
    _db_upsert_state,
    _db_get_state,
    _sync_job,
)

# (Task 2 functions — import tentatively; used in Task 2 tests)
try:
    from app.plugins.doc_search import (
        _should_reindex,
        _upsert_document,
        _clean_deleted,
        _sync_repo,
    )
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def _temp_db() -> str:
    """Create a temporary SQLite file with sync_state table. Returns path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE sync_state (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.commit()
    conn.close()
    return path


# ═══════════════════════════════════════════════════════════════
#  Task 1 Tests — Config, Git, State, Guard
# ═══════════════════════════════════════════════════════════════

class TestLoadDocRepos:
    """Test _load_doc_repos() config parsing."""

    def test_parses_valid_doc_repos(self):
        """Valid doc_repos key returns list of {name, path} dicts."""
        mock_cfg = {
            "doc_repos": [
                {"name": "repo-a", "path": "/path/a"},
                {"name": "repo-b", "path": "/path/b"},
            ]
        }
        with patch("app.plugins.doc_search.config.load", return_value=mock_cfg):
            result = _load_doc_repos()
            assert len(result) == 2
            assert result[0] == {"name": "repo-a", "path": "/path/a"}
            assert result[1] == {"name": "repo-b", "path": "/path/b"}

    def test_missing_key_returns_empty(self):
        """Missing doc_repos key returns empty list."""
        with patch("app.plugins.doc_search.config.load", return_value={}):
            result = _load_doc_repos()
            assert result == []

    def test_empty_list_returns_empty(self):
        """Empty doc_repos list returns empty list."""
        mock_cfg = {"doc_repos": []}
        with patch("app.plugins.doc_search.config.load", return_value=mock_cfg):
            result = _load_doc_repos()
            assert result == []

    def test_skips_missing_name(self):
        """Entry without 'name' key is silently skipped."""
        mock_cfg = {"doc_repos": [{"path": "/p"}, {"name": "good", "path": "/g"}]}
        with patch("app.plugins.doc_search.config.load", return_value=mock_cfg):
            result = _load_doc_repos()
            assert len(result) == 1
            assert result[0] == {"name": "good", "path": "/g"}

    def test_skips_missing_path(self):
        """Entry without 'path' key is silently skipped."""
        mock_cfg = {"doc_repos": [{"name": "bad"}, {"name": "good", "path": "/g"}]}
        with patch("app.plugins.doc_search.config.load", return_value=mock_cfg):
            result = _load_doc_repos()
            assert len(result) == 1
            assert result[0] == {"name": "good", "path": "/g"}

    def test_skips_empty_name(self):
        """Entry with empty string name is skipped."""
        mock_cfg = {"doc_repos": [{"name": "", "path": "/p"}, {"name": "good", "path": "/g"}]}
        with patch("app.plugins.doc_search.config.load", return_value=mock_cfg):
            result = _load_doc_repos()
            assert len(result) == 1
            assert result[0] == {"name": "good", "path": "/g"}


class TestGitPull:
    """Test _git_pull() subprocess safety."""

    def test_passes_argument_list_to_subprocess(self):
        """Git pull uses argument list, never shell=True."""
        mock_run = MagicMock(return_value=MagicMock(
            stdout="Already up to date.\n", stderr="", returncode=0
        ))

        with patch("app.plugins.doc_search.subprocess.run", mock_run):
            result = asyncio.run(_git_pull("/some/repo/path"))

            # Verify argument list (never a string → implies shell=False)
            call_args = mock_run.call_args
            assert call_args is not None
            cmd = call_args[0][0]  # first positional arg
            assert isinstance(cmd, list)
            assert cmd[0] == "git"
            assert "-C" in cmd
            assert "/some/repo/path" in cmd
            assert "pull" in cmd

            # shell=True must never be set
            shell_arg = call_args[1].get("shell")
            assert shell_arg is None or shell_arg is False

            # timeout should be present
            timeout_arg = call_args[1].get("timeout")
            assert timeout_arg == 120

        assert result["ok"] is True
        assert "Already up to date" in result["stdout"]

    def test_handles_git_failure(self):
        """Git failure returns ok=False with stderr."""
        mock_run = MagicMock(return_value=MagicMock(
            stdout="", stderr="fatal: not a git repository\n", returncode=128
        ))

        with patch("app.plugins.doc_search.subprocess.run", mock_run):
            result = asyncio.run(_git_pull("/bad/repo"))
            assert result["ok"] is False
            assert "not a git repository" in result["stderr"]

    def test_handles_timeout(self):
        """subprocess.TimeoutExpired returns ok=False with message."""
        import subprocess

        def _raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0] if args else [], timeout=120)

        with patch("app.plugins.doc_search.subprocess.run", _raise_timeout):
            result = asyncio.run(_git_pull("/slow/repo"))
            assert result["ok"] is False
            assert "timed out" in result["stderr"].lower() or "120s" in result["stderr"]


class TestSyncStateHelpers:
    """Test _db_upsert_state / _db_get_state JSON round-trip."""

    def test_roundtrip_dict(self):
        """Dict value survives json.dumps → json.loads round-trip."""
        db_path = _temp_db()
        try:
            with patch("app.plugins.doc_search.DB_PATH", db_path):
                _db_upsert_state("test_key", {"phase": "pulling", "done": 5})
                val = _db_get_state("test_key")
                assert val == {"phase": "pulling", "done": 5}
        finally:
            os.unlink(db_path)

    def test_roundtrip_string(self):
        """String value round-trips correctly."""
        db_path = _temp_db()
        try:
            with patch("app.plugins.doc_search.DB_PATH", db_path):
                _db_upsert_state("key2", "hello_world")
                val = _db_get_state("key2")
                assert val == "hello_world"
        finally:
            os.unlink(db_path)

    def test_roundtrip_int(self):
        """Integer value round-trips correctly."""
        db_path = _temp_db()
        try:
            with patch("app.plugins.doc_search.DB_PATH", db_path):
                _db_upsert_state("count", 42)
                val = _db_get_state("count")
                assert val == 42
        finally:
            os.unlink(db_path)

    def test_missing_key_returns_none(self):
        """Missing key returns None."""
        db_path = _temp_db()
        try:
            with patch("app.plugins.doc_search.DB_PATH", db_path):
                val = _db_get_state("nonexistent")
                assert val is None
        finally:
            os.unlink(db_path)

    def test_overwrite_previous_value(self):
        """Upsert overwrites existing key."""
        db_path = _temp_db()
        try:
            with patch("app.plugins.doc_search.DB_PATH", db_path):
                _db_upsert_state("key", "first")
                _db_upsert_state("key", "second")
                val = _db_get_state("key")
                assert val == "second"
        finally:
            os.unlink(db_path)

    def test_invalid_json_returns_none(self):
        """Malformed JSON in value column returns None."""
        db_path = _temp_db()
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO sync_state (key, value) VALUES (?, ?)",
                ("bad_key", "not valid json {{{"),
            )
            conn.commit()
            conn.close()
            with patch("app.plugins.doc_search.DB_PATH", db_path):
                val = _db_get_state("bad_key")
                assert val is None
        finally:
            os.unlink(db_path)


class TestSyncJobGuard:
    """Test _sync_job() in-progress guard."""

    def test_guard_prevents_concurrent_runs(self):
        """Second call returns immediately when lock is held."""
        from app.plugins.doc_search import _sync_lock

        mock_repos: list = []

        async def _run_guard_test():
            with patch("app.plugins.doc_search._load_doc_repos", return_value=mock_repos):
                # Acquire the lock first (simulating another sync in progress)
                await _sync_lock.acquire()
                try:
                    # _sync_job should detect locked state and return immediately
                    await _sync_job()
                    # If we get here without error, the guard worked
                finally:
                    _sync_lock.release()

        asyncio.run(_run_guard_test())

    def test_guard_releases_lock_after_completion(self):
        """Lock is released after sync completes normally."""
        from app.plugins.doc_search import _sync_lock

        mock_repos: list = []

        async def _run_release_test():
            with patch("app.plugins.doc_search._load_doc_repos", return_value=mock_repos):
                await _sync_job()
                # Lock should be released
                assert not _sync_lock.locked()

        asyncio.run(_run_release_test())
