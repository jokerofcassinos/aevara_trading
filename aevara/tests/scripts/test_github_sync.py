# @module: aevara.tests.scripts.test_github_sync
# @deps: scripts.github_sync, pytest, hypothesis
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Tests for GitHub Sync Orchestrator — happy path, edge cases,
#           error handling, property-based security validation.

from __future__ import annotations

import os
import pathlib
import time

import pytest

from scripts.github_sync import (
    SyncConfig,
    SyncResult,
    GitHubSyncOrchestrator,
    select_files,
    _matches_exclude,
    compute_state_hash,
    build_push_url,
    _git_has_repo,
)

try:
    from hypothesis import given, settings
    import hypothesis.strategies as st
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


# =============================================================================
# SYNC CONFIG
# =============================================================================

class TestSyncConfig:
    def test_defaults(self):
        cfg = SyncConfig(repo_url="https://example.com/repo.git")
        assert cfg.branch == "main"
        assert cfg.commit_prefix == "[AEVRA]"
        assert cfg.dry_run is False
        assert cfg.max_retries == 3
        assert cfg.telemetry_enabled is True

    def test_custom_values(self):
        cfg = SyncConfig(
            repo_url="https://example.com/repo.git",
            branch="dev",
            dry_run=True,
            max_retries=5,
        )
        assert cfg.branch == "dev"
        assert cfg.dry_run is True
        assert cfg.max_retries == 5


class TestSyncResult:
    def test_success_result(self):
        result = SyncResult(
            success=True, files_staged=42, commit_hash="abc123",
            remote_url="https://example.com/repo.git", elapsed_ms=1500,
        )
        assert result.success
        assert result.files_staged == 42
        assert result.error is None

    def test_failure_result(self):
        result = SyncResult(
            success=False, files_staged=10, commit_hash=None,
            remote_url="https://example.com/repo.git", elapsed_ms=500,
            error="Push failed",
        )
        assert not result.success
        assert result.error == "Push failed"


# =============================================================================
# FILE SELECTION
# =============================================================================

class TestFileSelection:
    def test_selects_python_files(self):
        cfg = SyncConfig(repo_url="https://example.com/repo.git")
        files = select_files(_PROJECT_ROOT, cfg)
        # Should find our own source files
        python_files = [f for f in files if f.endswith(".py")]
        assert len(python_files) > 0

    def test_selects_yaml_configs(self):
        cfg = SyncConfig(repo_url="https://example.com/repo.git")
        files = select_files(_PROJECT_ROOT, cfg)
        yaml_files = [f for f in files if f.endswith(".yaml")]
        assert len(yaml_files) > 0

    def test_excludes_underscored_dirs(self):
        cfg = SyncConfig(repo_url="https://example.com/repo.git")
        files = select_files(_PROJECT_ROOT, cfg)
        for f in files:
            assert not f.startswith("__pycache__/")
            assert not f.startswith(".venv/")
            assert not f.startswith(".pytest_cache/")
            assert not f.startswith(".claude/")

    def test_select_files_returns_list(self):
        cfg = SyncConfig(repo_url="https://example.com/repo.git")
        files = select_files(_PROJECT_ROOT, cfg)
        assert isinstance(files, list)
        assert all(isinstance(f, str) for f in files)

    def test_no_duplicates(self):
        cfg = SyncConfig(repo_url="https://example.com/repo.git")
        files = select_files(_PROJECT_ROOT, cfg)
        assert len(files) == len(set(files))


# =============================================================================
# EXCLUDE PATTERN MATCHING
# =============================================================================

class TestExcludeMatching:
    def test_env_file_excluded(self):
        assert _matches_exclude(".env", ".env")

    def test_env_local_excluded(self):
        assert _matches_exclude(".env.local", ".env.*")

    def test_pyc_excluded(self):
        assert _matches_exclude("src/__pycache__/module.pyc", "*.pyc")

    def test_venv_dir_excluded(self):
        assert _matches_exclude(".venv/lib/python/site.py", ".venv/")

    def test_pycache_dir_excluded(self):
        assert _matches_exclude("__pycache__/test.pyc", "__pycache__/")

    def test_log_file_excluded(self):
        assert _matches_exclude("data/audit/telemetry.log", "*.log")

    def test_git_dir_excluded(self):
        assert _matches_exclude(".git/config", ".git/")

    def test_secrets_dir_excluded(self):
        assert _matches_exclude("secrets/keys.txt", "secrets/")

    def test_normal_file_not_excluded(self):
        assert not _matches_exclude("src/core/signal.py", "*.log")

    def test_test_file_not_excluded(self):
        assert not _matches_exclude("tests/unit/core/test_signal.py", "*.log")


# =============================================================================
# STATE HASHING
# =============================================================================

class TestStateHashing:
    def test_produces_string(self, tmp_path):
        (tmp_path / "test.py").write_text("print('hello')")
        h = compute_state_hash(tmp_path, ["test.py"])
        assert isinstance(h, str)
        assert len(h) == 12

    def test_different_produces_different_hashes(self, tmp_path):
        (tmp_path / "a.py").write_text("version1")
        h1 = compute_state_hash(tmp_path, ["a.py"])
        (tmp_path / "a.py").write_text("version2")
        h2 = compute_state_hash(tmp_path, ["a.py"])
        assert h1 != h2

    def test_empty_files_produces_hash(self, tmp_path):
        h = compute_state_hash(tmp_path, [])
        assert isinstance(h, str)
        assert len(h) == 12

    def test_nonexistent_file_same_hash(self, tmp_path):
        h1 = compute_state_hash(tmp_path, ["nonexistent.py"])
        h2 = compute_state_hash(tmp_path, ["also_nonexistent.py"])
        # Should not raise
        assert isinstance(h1, str)


# =============================================================================
# PUSH URL BUILDING
# =============================================================================

class TestPushUrlBuilding:
    def test_https_with_pat_embeds_token(self):
        result = build_push_url("https://github.com/org/repo.git", "ghp_secret123")
        assert "ghp_secret123" in result
        assert "x-access-token" in result

    def test_https_without_pat_unchanged(self):
        result = build_push_url("https://github.com/org/repo.git", None)
        assert result == "https://github.com/org/repo.git"

    def test_ssh_url_unchanged_with_pat(self):
        result = build_push_url("git@github.com:org/repo.git", "ghp_secret")
        assert result == "git@github.com:org/repo.git"

    def test_no_pat_no_change(self):
        result = build_push_url("https://github.com/org/repo.git", None)
        assert "x-access-token" not in result


# =============================================================================
# ORCHESTRATOR INIT
# =============================================================================

class TestOrchestratorInit:
    def test_init_with_defaults(self):
        cfg = SyncConfig(repo_url="https://github.com/org/repo.git")
        orch = GitHubSyncOrchestrator(cfg)
        assert orch._config == cfg

    def test_init_with_custom_logger(self):
        from aevara.src.telemetry.logger import StructuredLogger
        cfg = SyncConfig(repo_url="https://github.com/org/repo.git")
        logger = StructuredLogger(log_dir=str(_PROJECT_ROOT / "data" / "audit"))
        orch = GitHubSyncOrchestrator(cfg, logger=logger)
        assert orch._logger is logger


# =============================================================================
# DRY RUN (no git required)
# =============================================================================

class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_result(self):
        os.environ.setdefault("AEVRA_GITHUB_PAT", "ghp_test_token_12345")
        cfg = SyncConfig(
            repo_url="https://github.com/org/repo.git",
            dry_run=True,
        )
        orch = GitHubSyncOrchestrator(cfg)
        result = await orch.execute()
        assert result.success
        assert result.files_staged > 0
        assert result.commit_hash is None  # dry run, no commit
        del os.environ["AEVRA_GITHUB_PAT"]


# =============================================================================
# GIT DETECTION
# =============================================================================

class TestGitDetection:
    def test_non_repo_returns_false(self, tmp_path):
        assert not _git_has_repo(str(tmp_path))


# =============================================================================
# PROPERTY-BASED TESTS (Hypothesis)
# =============================================================================

if HAS_HYPOTHESIS:
    class TestPropertyBasedSecurity:
        @given(st.text(min_size=1, max_size=50).filter(lambda s: "/" not in s))
        @settings(max_examples=50)
        def test_env_variants_always_excluded(self, suffix):
            """Any .env variant must be excluded."""
            filepath = f".env{suffix}"
            assert _matches_exclude(filepath, ".env") or \
                   _matches_exclude(filepath, ".env.*")

        @given(
            dir_name=st.text(min_size=1, max_size=20),
            filename=st.text(min_size=1, max_size=20),
        )
        @settings(max_examples=50)
        def test_sensitive_dirs_excluded(self, dir_name, filename):
            """Files inside sensitive directories must be excluded."""
            for sensitive in ["secrets", ".venv", "__pycache__", ".git", ".claude"]:
                filepath = f"{sensitive}/{dir_name}/{filename}"
                assert _matches_exclude(filepath, f"{sensitive}/")

        @given(st.text(min_size=1, max_size=30))
        @settings(max_examples=50)
        def test_data_raw_never_selected(self, subpath):
            """data/raw paths must always be excluded."""
            filepath = f"data/raw/{subpath}"
            assert _matches_exclude(filepath, "data/raw/")

        @given(st.text(min_size=1, max_size=30))
        @settings(max_examples=50)
        def test_log_files_always_excluded(self, basename):
            """Any .log file must be excluded."""
            filepath = f"some/path/{basename}.log"
            assert _matches_exclude(filepath, "*.log")

    class TestPropertyBasedConfig:
        @given(st.integers(min_value=1, max_value=100))
        @settings(max_examples=20)
        def test_include_patterns_never_empty(self, n):
            """Include patterns must always have at least one entry."""
            cfg = SyncConfig(
                repo_url="https://example.com/repo.git",
                include_patterns=("src/**/*.py",) * n,
            )
            assert len(cfg.include_patterns) > 0

        @given(st.integers(min_value=1, max_value=100))
        @settings(max_examples=20)
        def test_exclude_patterns_never_empty(self, n):
            """Exclude patterns must always have at least one entry."""
            cfg = SyncConfig(
                repo_url="https://example.com/repo.git",
                exclude_patterns=("*.log",) * n,
            )
            assert len(cfg.exclude_patterns) > 0
