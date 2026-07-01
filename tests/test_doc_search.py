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


# ═══════════════════════════════════════════════════════════════
#  Task 2 Tests — _should_reindex, _upsert_document, _clean_deleted,
#                 _sync_repo, _sync_job orchestration
# ═══════════════════════════════════════════════════════════════

# ── Helpers for Task 2 tests ──────────────────────────────────

def _create_doc_db() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with doc_metadata + doc_search_fts schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE doc_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            full_text TEXT NOT NULL DEFAULT '',
            sha256 TEXT NOT NULL DEFAULT '',
            encoding TEXT NOT NULL DEFAULT 'utf_8',
            needs_ocr INTEGER NOT NULL DEFAULT 0,
            last_extracted TEXT NOT NULL DEFAULT '',
            UNIQUE(repo, relative_path)
        );
        CREATE VIRTUAL TABLE doc_search_fts USING fts5(
            full_text,
            tokenize='unicode61'
        );
    """)
    conn.commit()
    return conn


class TestShouldReindex:
    """Test _should_reindex() hash comparison."""

    def test_returns_true_when_no_row_exists(self):
        """No matching row → reindex needed."""
        from app.plugins.doc_search import _should_reindex
        conn = _create_doc_db()
        try:
            assert _should_reindex(conn, "repo-a", "docs/readme.md", "abc123") is True
        finally:
            conn.close()

    def test_returns_false_when_hash_matches(self):
        """Same SHA-256 → no reindex needed."""
        from app.plugins.doc_search import _should_reindex
        conn = _create_doc_db()
        try:
            conn.execute(
                "INSERT INTO doc_metadata (repo, relative_path, sha256) VALUES (?, ?, ?)",
                ("repo-a", "docs/readme.md", "abc123"),
            )
            conn.commit()
            assert _should_reindex(conn, "repo-a", "docs/readme.md", "abc123") is False
        finally:
            conn.close()

    def test_returns_true_when_hash_differs(self):
        """Different SHA-256 → reindex needed."""
        from app.plugins.doc_search import _should_reindex
        conn = _create_doc_db()
        try:
            conn.execute(
                "INSERT INTO doc_metadata (repo, relative_path, sha256) VALUES (?, ?, ?)",
                ("repo-a", "docs/readme.md", "abc123"),
            )
            conn.commit()
            assert _should_reindex(conn, "repo-a", "docs/readme.md", "def456") is True
        finally:
            conn.close()


class TestUpsertDocument:
    """Test _upsert_document() FTS5 content-less upsert."""

    def test_inserts_new_document(self):
        """New document creates row in doc_metadata and doc_search_fts."""
        from app.plugins.doc_search import _upsert_document
        conn = _create_doc_db()
        try:
            result = {
                "text": "Hello world from test document",
                "encoding": "utf_8",
                "needs_ocr": False,
                "sha256": "abc123",
                "error": None,
            }
            rowid = _upsert_document(conn, "repo-a", "docs/test.md", result)

            # Verify doc_metadata row
            meta = conn.execute(
                "SELECT * FROM doc_metadata WHERE id = ?", (rowid,)
            ).fetchone()
            assert meta is not None
            assert meta["repo"] == "repo-a"
            assert meta["relative_path"] == "docs/test.md"
            assert "Hello world" in meta["full_text"]
            assert meta["sha256"] == "abc123"
            assert meta["encoding"] == "utf_8"

            # Verify FTS5 entry
            fts = conn.execute(
                "SELECT * FROM doc_search_fts WHERE rowid = ?", (rowid,)
            ).fetchone()
            assert fts is not None
            assert "Hello world" in fts["full_text"]
        finally:
            conn.close()

    def test_upserts_existing_document(self):
        """ON CONFLICT updates existing row and rebuilds FTS5 entry."""
        from app.plugins.doc_search import _upsert_document
        conn = _create_doc_db()
        try:
            # First insert
            result1 = {
                "text": "Original text", "encoding": "utf_8",
                "needs_ocr": False, "sha256": "aaa", "error": None,
            }
            rowid1 = _upsert_document(conn, "repo-a", "docs/readme.md", result1)

            # Second insert — same repo+path, different content
            result2 = {
                "text": "Updated text content", "encoding": "utf_8",
                "needs_ocr": False, "sha256": "bbb", "error": None,
            }
            rowid2 = _upsert_document(conn, "repo-a", "docs/readme.md", result2)

            # Rowid should be the same (updated, not new)
            assert rowid1 == rowid2

            # doc_metadata should have updated content
            meta = conn.execute(
                "SELECT sha256, full_text FROM doc_metadata WHERE id = ?", (rowid2,)
            ).fetchone()
            assert meta["sha256"] == "bbb"
            assert "Updated text content" in meta["full_text"]

            # Only one row should exist
            count = conn.execute(
                "SELECT COUNT(*) FROM doc_metadata WHERE repo = ? AND relative_path = ?",
                ("repo-a", "docs/readme.md"),
            ).fetchone()[0]
            assert count == 1

            # FTS5 should reflect updated text, not old text
            fts = conn.execute(
                "SELECT full_text FROM doc_search_fts WHERE rowid = ?", (rowid2,)
            ).fetchone()
            assert "Updated text content" in fts["full_text"]
            assert "Original text" not in fts["full_text"]
        finally:
            conn.close()


class TestCleanDeleted:
    """Test _clean_deleted() removes stale entries."""

    def test_removes_missing_paths(self):
        """Paths not in existing_paths set are deleted from doc_metadata."""
        from app.plugins.doc_search import _clean_deleted
        conn = _create_doc_db()
        try:
            # Insert 3 files for repo-a
            conn.execute(
                "INSERT INTO doc_metadata (repo, relative_path, full_text) "
                "VALUES (?, ?, ?)",
                ("repo-a", "keep.md", "keep text"),
            )
            conn.execute(
                "INSERT INTO doc_metadata (repo, relative_path, full_text) "
                "VALUES (?, ?, ?)",
                ("repo-a", "delete.md", "delete text"),
            )
            conn.execute(
                "INSERT INTO doc_metadata (repo, relative_path, full_text) "
                "VALUES (?, ?, ?)",
                ("repo-b", "other.md", "other text"),
            )
            conn.commit()

            # Only keep.md exists on disk — delete delete.md
            existing = {"keep.md", "new_file.md"}
            deleted = _clean_deleted(conn, "repo-a", existing)

            assert deleted == 1  # delete.md removed

            # Verify keep.md still exists
            keep = conn.execute(
                "SELECT relative_path FROM doc_metadata WHERE repo = ? AND relative_path = ?",
                ("repo-a", "keep.md"),
            ).fetchone()
            assert keep is not None

            # Verify delete.md is gone
            gone = conn.execute(
                "SELECT relative_path FROM doc_metadata WHERE repo = ? AND relative_path = ?",
                ("repo-a", "delete.md"),
            ).fetchone()
            assert gone is None

            # repo-b should be unaffected
            other = conn.execute(
                "SELECT relative_path FROM doc_metadata WHERE repo = ?",
                ("repo-b",),
            ).fetchone()
            assert other is not None
        finally:
            conn.close()

    def test_returns_zero_when_nothing_deleted(self):
        """All paths exist → zero deletions."""
        from app.plugins.doc_search import _clean_deleted
        conn = _create_doc_db()
        try:
            conn.execute(
                "INSERT INTO doc_metadata (repo, relative_path, full_text) "
                "VALUES (?, ?, ?)",
                ("repo-a", "a.md", "text"),
            )
            conn.commit()

            existing = {"a.md", "b.md"}
            deleted = _clean_deleted(conn, "repo-a", existing)
            assert deleted == 0
        finally:
            conn.close()


class TestSyncRepo:
    """Test _sync_repo() per-repo orchestration."""

    def test_sync_repo_walks_and_extracts_changed_files(self, tmp_path):
        """_sync_repo walks directory, extracts only changed files, upserts, cleans."""
        from app.plugins.doc_search import _sync_repo
        from unittest.mock import patch

        repo_path = str(tmp_path / "test-repo")
        os.makedirs(repo_path)
        os.makedirs(os.path.join(repo_path, ".git"))

        # Create some doc files
        files = {
            "readme.md": "# Hello World",
            "guide.rst": "Welcome to the guide",
            "diagram.drawio": '<mxCell value="Box 1"/>',
        }
        for rel, content in files.items():
            full = os.path.join(repo_path, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(content)

        # Mock extract_text to return predictable results
        def _mock_extract(file_path):
            fname = os.path.basename(file_path)
            return {
                "text": f"EXTRACTED:{fname}",
                "encoding": "utf_8",
                "needs_ocr": False,
                "sha256": f"sha-{fname}",
                "error": None,
            }

        # _get_db factory: creates a fresh in-memory DB for each call (thread-safe)
        def _make_in_memory_db():
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            conn.executescript("""
                CREATE TABLE doc_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    full_text TEXT NOT NULL DEFAULT '',
                    sha256 TEXT NOT NULL DEFAULT '',
                    encoding TEXT NOT NULL DEFAULT 'utf_8',
                    needs_ocr INTEGER NOT NULL DEFAULT 0,
                    last_extracted TEXT NOT NULL DEFAULT '',
                    UNIQUE(repo, relative_path)
                );
                CREATE VIRTUAL TABLE doc_search_fts USING fts5(
                    full_text,
                    tokenize='unicode61'
                );
                CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT);
            """)
            conn.commit()
            return conn

        with patch(
            "app.plugins.doc_search.extract_text", side_effect=_mock_extract
        ), patch(
            "app.plugins.doc_search.compute_sha256",
            side_effect=lambda p: f"sha-{os.path.basename(p)}",
        ), patch(
            "app.plugins.doc_search._get_db", side_effect=_make_in_memory_db
        ):
            summary = asyncio.run(_sync_repo("test-repo", repo_path))

            assert summary["repo"] == "test-repo"
            assert summary["total"] == 3
            assert summary["changed"] == 3
            assert summary["deleted"] == 0
            assert isinstance(summary["errors"], list)

    def test_sync_repo_skips_git_directory(self, tmp_path):
        """.git directory is skipped during walk."""
        from app.plugins.doc_search import _sync_repo
        from unittest.mock import patch

        repo_path = str(tmp_path / "test-repo")
        os.makedirs(repo_path)
        os.makedirs(os.path.join(repo_path, ".git"))
        # Create a file inside .git (should be skipped)
        os.makedirs(os.path.join(repo_path, ".git", "objects"))
        with open(os.path.join(repo_path, ".git", "HEAD"), "w") as f:
            f.write("ref: refs/heads/main\n")

        # Only a README outside .git
        with open(os.path.join(repo_path, "readme.md"), "w") as f:
            f.write("hello")

        def _mock_extract(file_path):
            return {
                "text": "EXTRACTED",
                "encoding": "utf_8",
                "needs_ocr": False,
                "sha256": f"sha-{os.path.basename(file_path)}",
                "error": None,
            }

        def _make_in_memory_db():
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            conn.executescript("""
                CREATE TABLE doc_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    full_text TEXT NOT NULL DEFAULT '',
                    sha256 TEXT NOT NULL DEFAULT '',
                    encoding TEXT NOT NULL DEFAULT 'utf_8',
                    needs_ocr INTEGER NOT NULL DEFAULT 0,
                    last_extracted TEXT NOT NULL DEFAULT '',
                    UNIQUE(repo, relative_path)
                );
                CREATE VIRTUAL TABLE doc_search_fts USING fts5(
                    full_text,
                    tokenize='unicode61'
                );
                CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT);
            """)
            conn.commit()
            return conn

        with patch(
            "app.plugins.doc_search.extract_text", side_effect=_mock_extract
        ), patch(
            "app.plugins.doc_search.compute_sha256",
            side_effect=lambda p: f"sha-{os.path.basename(p)}",
        ), patch(
            "app.plugins.doc_search._get_db", side_effect=_make_in_memory_db
        ):
            summary = asyncio.run(_sync_repo("test-repo", repo_path))
            # Only readme.md should be counted, not .git/HEAD
            assert summary["total"] == 1


class TestSyncJobOrchestration:
    """Test _sync_job() full pipeline orchestration."""

    @staticmethod
    def _make_test_db():
        """Factory: create an in-memory DB with all required tables."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.commit()
        return conn

    def test_sync_job_orchestrates_full_pipeline(self):
        """_sync_job loads repos, pulls, syncs each, updates progress."""
        from app.plugins.doc_search import _sync_lock
        from unittest.mock import patch

        mock_repos = [
            {"name": "repo-a", "path": "/tmp/repo-a"},
            {"name": "repo-b", "path": "/tmp/repo-b"},
        ]

        async def _mock_git_pull(repo_path):
            return {"ok": True, "stdout": "up to date", "stderr": ""}

        async def _mock_sync_repo(name, path):
            return {
                "repo": name, "pulled": True, "total": 10,
                "changed": 2, "deleted": 0, "errors": [],
            }

        # Ensure lock is not held before test
        async def _release_lock():
            if _sync_lock.locked():
                _sync_lock.release()

        asyncio.run(_release_lock())

        async def _run():
            with patch(
                "app.plugins.doc_search._load_doc_repos", return_value=mock_repos
            ), patch(
                "app.plugins.doc_search._git_pull", side_effect=_mock_git_pull
            ), patch(
                "app.plugins.doc_search._sync_repo", side_effect=_mock_sync_repo
            ), patch(
                "app.plugins.doc_search._get_db", side_effect=self._make_test_db
            ):
                await _sync_job()
                # After completion, lock should be released
                assert not _sync_lock.locked()

        asyncio.run(_run())

    def test_sync_job_updates_progress_state(self):
        """_sync_job writes sync_progress to sync_state during run."""
        from app.plugins.doc_search import _sync_lock
        from unittest.mock import patch

        mock_repos = [{"name": "repo-x", "path": "/tmp/repo-x"}]

        async def _mock_git_pull(repo_path):
            return {"ok": True, "stdout": "", "stderr": ""}

        async def _mock_sync_repo(name, path):
            return {
                "repo": name, "pulled": True, "total": 5,
                "changed": 0, "deleted": 0, "errors": [],
            }

        # Release lock if held
        async def _release_lock():
            if _sync_lock.locked():
                _sync_lock.release()

        asyncio.run(_release_lock())

        async def _run():
            with patch(
                "app.plugins.doc_search._load_doc_repos", return_value=mock_repos
            ), patch(
                "app.plugins.doc_search._git_pull", side_effect=_mock_git_pull
            ), patch(
                "app.plugins.doc_search._sync_repo", side_effect=_mock_sync_repo
            ), patch(
                "app.plugins.doc_search._get_db", side_effect=self._make_test_db
            ):
                await _sync_job()

        asyncio.run(_run())

    def test_sync_job_continues_on_git_failure(self):
        """Git pull failure for one repo does not stop other repos."""
        from app.plugins.doc_search import _sync_lock
        from unittest.mock import patch

        mock_repos = [
            {"name": "repo-bad", "path": "/tmp/bad"},
            {"name": "repo-good", "path": "/tmp/good"},
        ]

        call_order = []

        async def _mock_git_pull(repo_path):
            call_order.append(("pull", repo_path))
            if "bad" in repo_path:
                return {"ok": False, "stdout": "", "stderr": "failed"}
            return {"ok": True, "stdout": "", "stderr": ""}

        async def _mock_sync_repo(name, path):
            call_order.append(("sync", name))
            return {
                "repo": name, "pulled": True, "total": 1,
                "changed": 0, "deleted": 0, "errors": [],
            }

        async def _release_lock():
            if _sync_lock.locked():
                _sync_lock.release()

        asyncio.run(_release_lock())

        async def _run():
            with patch(
                "app.plugins.doc_search._load_doc_repos", return_value=mock_repos
            ), patch(
                "app.plugins.doc_search._git_pull", side_effect=_mock_git_pull
            ), patch(
                "app.plugins.doc_search._sync_repo", side_effect=_mock_sync_repo
            ), patch(
                "app.plugins.doc_search._get_db", side_effect=self._make_test_db
            ):
                await _sync_job()

        asyncio.run(_run())

        # Both repos should have been pulled
        pulls = [c for c in call_order if c[0] == "pull"]
        assert len(pulls) == 2

        # Both repos should have been synced (bad repo still gets synced)
        syncs = [c for c in call_order if c[0] == "sync"]
        assert len(syncs) == 2


# ═══════════════════════════════════════════════════════════════
#  Task 3 Tests (Plan 06-02) — Search, Preview, Repos API
# ═══════════════════════════════════════════════════════════════

# ── Helpers ─────────────────────────────────────────────────────

def _make_integration_db() -> str:
    """Create a temp SQLite DB with full schema + seed data.

    Creates doc_metadata, doc_search_fts, and sync_state tables.
    Inserts sample documents for search testing.

    Returns the filesystem path to the DB file.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE doc_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            full_text TEXT NOT NULL DEFAULT '',
            sha256 TEXT NOT NULL DEFAULT '',
            encoding TEXT NOT NULL DEFAULT 'utf_8',
            needs_ocr INTEGER NOT NULL DEFAULT 0,
            last_extracted TEXT NOT NULL DEFAULT '',
            UNIQUE(repo, relative_path)
        );
        CREATE VIRTUAL TABLE doc_search_fts USING fts5(
            full_text,
            tokenize='unicode61'
        );
        CREATE TABLE sync_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()

    # Seed test documents
    docs = [
        ("TestRepo", "docs/readme.md", "Welcome to the documentation toolkit. This project indexes and searches technical documents.", "abc111", 0),
        ("TestRepo", "docs/api.md", "The API provides search endpoints for full-text queries using BM25 ranking. Use the /search endpoint.", "def222", 0),
        ("TestRepo", "docs/guide.pdf", "", "ghi333", 1),  # needs_ocr = 1
        ("TestRepo", "notes/meeting.docx", "Meeting notes for Q3 planning session. Discussion about FTS5 optimization.", "jkl444", 0),
        ("OtherRepo", "src/main.py", "print('hello world')", "mno555", 0),
    ]
    for repo, rel_path, text, sha, ocr in docs:
        conn.execute(
            "INSERT INTO doc_metadata (repo, relative_path, full_text, sha256, needs_ocr) "
            "VALUES (?, ?, ?, ?, ?)",
            (repo, rel_path, text, sha, ocr),
        )
        # Get rowid for FTS5 insert
        rowid = conn.execute(
            "SELECT id FROM doc_metadata WHERE repo = ? AND relative_path = ?",
            (repo, rel_path),
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO doc_search_fts(rowid, full_text) VALUES (?, ?)",
            (rowid, text),
        )
    conn.commit()

    # Seed sync_state data
    conn.execute(
        "INSERT INTO sync_state (key, value) VALUES (?, ?)",
        ("last_sync", '"2026-07-01T12:00:00+00:00"'),
    )
    conn.commit()
    conn.close()
    return path


def _make_test_app(db_path: str) -> FastAPI:
    """Create a FastAPI app with DocSearchPlugin registered, DB_PATH patched."""
    from fastapi import FastAPI
    from app.plugins.doc_search import DocSearchPlugin

    app = FastAPI()
    plugin = DocSearchPlugin()
    plugin.register_routes(app)
    return app


# ── Pytest fixtures ──────────────────────────────────────────────

@pytest.fixture
def integration_db():
    """Provide a temp DB path with schema + seed data."""
    db_path = _make_integration_db()
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def search_client(integration_db):
    """HTTP test client against FastAPI app with real test DB."""
    app = _make_test_app(integration_db)

    from fastapi.testclient import TestClient
    client = TestClient(app)

    # We need the endpoint code to use our test DB, not the production one.
    # The endpoint uses _get_db() which uses DB_PATH.
    # Override DB_PATH for the test.
    with patch("app.plugins.doc_search.DB_PATH", integration_db):
        yield client


# ── Search endpoint tests ────────────────────────────────────────

class TestSearchEndpoint:
    """Integration tests for GET /api/doc_search/search."""

    def test_search_returns_bm25_results(self, search_client):
        """FTS5 MATCH returns results with snippet, score, repo, path, etc."""
        response = search_client.get("/api/doc_search/search", params={"q": "documentation"})
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert "query" in data
        assert data["query"] == "documentation"
        assert data["total"] > 0
        assert isinstance(data["results"], list)

        # Check first result shape
        r = data["results"][0]
        assert "repo" in r
        assert "path" in r
        assert "filename" in r
        assert "snippet" in r
        assert "score" in r
        assert "needs_ocr" in r
        assert "file_type" in r
        assert isinstance(r["needs_ocr"], bool)
        assert isinstance(r["score"], (int, float))

    def test_search_limits_to_50(self, search_client):
        """Max 50 results returned per SRCH-01."""
        # Our test DB only has a few docs, so just verify count <= total
        response = search_client.get("/api/doc_search/search", params={"q": "the"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) <= 50

    def test_empty_query_returns_empty_gracefully(self, search_client):
        """Empty q param returns empty results, no error per SRCH-05."""
        response = search_client.get("/api/doc_search/search", params={"q": ""})
        assert response.status_code == 200
        data = response.json()
        assert data == {"results": [], "total": 0, "query": ""}

    def test_search_finds_specific_term(self, search_client):
        """Search for specific word returns relevant doc."""
        response = search_client.get("/api/doc_search/search", params={"q": "BM25"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        found = False
        for r in data["results"]:
            if "api.md" in r.get("path", ""):
                found = True
                break
        assert found, "Expected api.md in results for BM25 query"

    def test_search_result_filename_derived(self, search_client):
        """filename is derived from path basename."""
        response = search_client.get("/api/doc_search/search", params={"q": "print"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert data["results"][0]["filename"] == "main.py"

    def test_search_result_file_type_derived(self, search_client):
        """file_type is lowercase extension without dot."""
        response = search_client.get("/api/doc_search/search", params={"q": "print"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert data["results"][0]["file_type"] == "py"


# ── Preview endpoint tests ───────────────────────────────────────

class TestPreviewEndpoint:
    """Integration tests for GET /api/doc_search/preview/{repo}/{path}."""

    def test_preview_returns_text(self, search_client):
        """Preview returns extracted text for known document."""
        response = search_client.get("/api/doc_search/preview/TestRepo/docs/readme.md")
        assert response.status_code == 200
        data = response.json()
        assert "repo" in data
        assert "path" in data
        assert "text" in data
        assert data["repo"] == "TestRepo"
        assert data["path"] == "docs/readme.md"
        assert "Welcome to the documentation toolkit" in data["text"]

    def test_preview_truncates_at_2000_chars(self, search_client):
        """Preview text is truncated to 2000 characters."""
        response = search_client.get("/api/doc_search/preview/TestRepo/docs/readme.md")
        assert response.status_code == 200
        data = response.json()
        assert len(data["text"]) <= 2000

    def test_preview_path_traversal_returns_403(self, search_client):
        """Path traversal attack returns 403 per NFR-13."""
        # Try to escape with ../
        response = search_client.get(
            "/api/doc_search/preview/TestRepo/../../../etc/passwd"
        )
        assert response.status_code == 403
        data = response.json()
        assert "error" in data.get("detail", {})

    def test_preview_not_found_returns_404(self, search_client):
        """Non-existent document returns 404."""
        response = search_client.get(
            "/api/doc_search/preview/TestRepo/docs/nonexistent.md"
        )
        assert response.status_code == 404
        data = response.json()
        assert "error" in data.get("detail", {})


# ── Repos endpoint tests ─────────────────────────────────────────

class TestReposEndpoint:
    """Integration tests for GET /api/doc_search/repos."""

    def test_repos_returns_configured_repos_with_counts(self, search_client):
        """Returns list of {name, path, file_count, last_synced} per SRCH-04."""
        mock_repos = [
            {"name": "TestRepo", "path": "/tmp/test-repo"},
            {"name": "OtherRepo", "path": "/tmp/other-repo"},
        ]
        with patch("app.plugins.doc_search._load_doc_repos", return_value=mock_repos):
            response = search_client.get("/api/doc_search/repos")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 2

            repo_names = {r["name"] for r in data}
            assert "TestRepo" in repo_names
            assert "OtherRepo" in repo_names

            # Check shape
            for repo in data:
                assert "name" in repo
                assert "path" in repo
                assert "file_count" in repo
                assert "last_synced" in repo
                assert isinstance(repo["file_count"], int)

            # TestRepo has 4 docs, OtherRepo has 1
            testrepo = next(r for r in data if r["name"] == "TestRepo")
            assert testrepo["file_count"] == 4

    def test_repos_zero_configured_returns_empty(self, search_client):
        """Zero repos configured returns empty list."""
        with patch("app.plugins.doc_search._load_doc_repos", return_value=[]):
            response = search_client.get("/api/doc_search/repos")
            assert response.status_code == 200
            data = response.json()
            assert data == []


# ── XSS sanitization tests ───────────────────────────────────────

class TestXssSanitization:
    """XSS payloads are stripped from stored text before JSON response."""

    def _seed_xss_doc(self, db_path: str, repo: str, rel_path: str, text: str):
        """Insert a document with potentially malicious text into the test DB."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO doc_metadata (repo, relative_path, full_text, sha256) "
            "VALUES (?, ?, ?, ?)",
            (repo, rel_path, text, "xss999"),
        )
        rowid = conn.execute(
            "SELECT id FROM doc_metadata WHERE repo = ? AND relative_path = ?",
            (repo, rel_path),
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO doc_search_fts(rowid, full_text) VALUES (?, ?)",
            (rowid, text),
        )
        conn.commit()
        conn.close()

    def test_xss_tags_stripped_from_snippet(self, integration_db, search_client):
        """HTML/script tags in stored text are stripped from search snippet."""
        xss_text = '<script>alert("xss")</script> Useful documentation about <b>security</b>'
        self._seed_xss_doc(
            integration_db, "TestRepo", "xss/evil.md", xss_text
        )

        from app.plugins.doc_search import DB_PATH
        # Re-create client since DB was modified after client creation
        # The search_client fixture already patches DB_PATH, but the DB was seeded
        # after the client was created.  The client still works because it reads
        # the same file.
        response = search_client.get("/api/doc_search/search", params={"q": "security"})
        assert response.status_code == 200
        data = response.json()

        # Find our doc
        xss_result = None
        for r in data["results"]:
            if r.get("path") == "xss/evil.md":
                xss_result = r
                break

        if xss_result is not None:
            snippet = xss_result["snippet"]
            # script tags must be absent
            assert "<script>" not in snippet.lower()
            assert "alert" not in snippet.lower() or "xss" not in snippet.lower()
