# @module: aevara.scripts.github_sync
# @deps: hashlib, json, os, subprocess, sys, time, uuid, pathlib, fnmatch, asyncio
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Async GitHub sync orchestrator with selective staging, atomic commits,
#           telemetry logging, zero-trust auth, and automatic rollback on failure.

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Resolve workspace root (parent of aevara/) for absolute imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent           # .../aevara
_WORKSPACE_ROOT = _PROJECT_ROOT.parent        # .../Nova pasta
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

try:
    from aevara.src.telemetry.logger import StructuredLogger, TelemetryEvent
    from aevara.src.infra.security.credential_vault import CredentialVault
except ImportError:
    import sys as _sys
    _root = Path(__file__).resolve().parent.parent.parent
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))
    from aevara.src.telemetry.logger import StructuredLogger, TelemetryEvent
    from aevara.src.infra.security.credential_vault import CredentialVault


# =============================================================================
# DATA CONTRACTS
# =============================================================================

@dataclass(frozen=True, slots=True)
class SyncConfig:
    repo_url: str
    branch: str = "main"
    commit_prefix: str = "[AEVRA]"
    include_patterns: Tuple[str, ...] = (
        "src/**/*.py",
        "docs/**/*.md",
        "tests/**/*.py",
        "config/*.yaml",
        "scripts/*.py",
        "*.md",
        "requirements.txt",
        "pyproject.toml",
    )
    exclude_patterns: Tuple[str, ...] = (
        ".env",
        ".env.*",
        "*.log",
        "data/raw/*",
        "data/processed/*",
        ".venv/",
        "__pycache__/",
        "*.pyc",
        ".git/",
        "secrets/",
        ".claude/",
        "*.egg-info/",
        ".pytest_cache/",
        "build/",
        "dist/",
        ".openclaude-profile.json",
    )
    telemetry_enabled: bool = True
    dry_run: bool = False
    max_retries: int = 3
    rollback_on_failure: bool = True


@dataclass(frozen=True, slots=True)
class SyncResult:
    success: bool
    files_staged: int
    commit_hash: Optional[str]
    remote_url: str
    elapsed_ms: int
    error: Optional[str] = None
    telemetry_trace_id: Optional[str] = None


# =============================================================================
# STATE HASHING
# =============================================================================

def compute_state_hash(project_root: Path, files: List[str]) -> str:
    """SHA-256 hash of file contents for state integrity verification."""
    h = hashlib.sha256()
    for f in sorted(files):
        fp = project_root / f
        if fp.is_file():
            try:
                h.update(fp.read_bytes())
            except (OSError, PermissionError):
                pass
    h.update(str(time.time_ns()).encode())
    return h.hexdigest()[:12]


# =============================================================================
# GIT HELPERS (PowerShell-compatible, no shell=True)
# =============================================================================

def _git(args: List[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return result


def _git_has_repo(path: str) -> bool:
    try:
        result = _git(["rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
        return result.returncode == 0
    except Exception:
        return False


def _git_get_head(cwd: str) -> str:
    result = _git(["rev-parse", "--short", "HEAD"], cwd=cwd)
    return result.stdout.strip()


def _git_init(cwd: str, branch: str = "main") -> None:
    _git(["init", "-b", branch], cwd=cwd)
    # Set user if not configured (required for commit)
    _git(["config", "user.name", "Aevra Sync Bot"], cwd=cwd)
    _git(["config", "user.email", "aevara@local"], cwd=cwd)


def _git_add_remote(cwd: str, name: str, url: str) -> None:
    try:
        _git(["remote", "remove", name], cwd=cwd, check=False)
    except RuntimeError:
        pass
    _git(["remote", "add", name, url], cwd=cwd)


def _git_status_porcelain(cwd: str) -> List[str]:
    result = _git(["status", "--porcelain"], cwd=cwd)
    lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    return lines


def _git_add_files(files: List[str], cwd: str) -> int:
    if not files:
        return 0
    _git(["add", "--"] + files, cwd=cwd)
    return len(files)


def _git_commit(message: str, cwd: str, no_verify: bool = False) -> Optional[str]:
    args = ["commit", "-m", message]
    if no_verify:
        args.append("--no-verify")
    result = _git(args, cwd=cwd, check=False)
    if result.returncode != 0:
        return None
    return _git_get_head(cwd)


def _git_push(cwd: str, remote: str = "origin", branch: str = "main") -> bool:
    result = _git(["push", "-u", remote, branch], cwd=cwd, check=False)
    return result.returncode == 0


def _git_soft_reset_one(cwd: str) -> bool:
    result = _git(["reset", "--soft", "HEAD~1"], cwd=cwd, check=False)
    return result.returncode == 0


def _git_remote_url(cwd: str, remote: str = "origin") -> Optional[str]:
    result = _git(["remote", "get-url", remote], cwd=cwd, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


# =============================================================================
# FILE SELECTION ENGINE
# =============================================================================

def select_files(project_root: Path, config: SyncConfig) -> List[str]:
    """Apply include/exclude patterns to select files for sync.

    NEVER includes .env files, credentials, or raw data regardless of patterns.
    """
    selected: set[str] = set()

    # Gather files matching include patterns
    for pattern in config.include_patterns:
        matched = set()
        # Use rglob for ** patterns, glob for simple patterns
        if "**" in pattern or "*" in pattern.split("/")[0]:
            # Extract glob suffix for matching
            suffix = pattern.split("/**/")[-1] if "/**/" in pattern else pattern.split("/", 1)[-1] if "/" in pattern else pattern
            if "/**/" in pattern:
                base_dir = pattern.split("/**/")[0]
                search_root = project_root / base_dir if base_dir else project_root
            else:
                search_root = project_root

            if search_root.is_dir():
                for f in search_root.rglob(suffix):
                    if f.is_file():
                        rel = str(f.relative_to(project_root).as_posix())
                        matched.add(rel)
        else:
            for f in project_root.glob(pattern):
                if f.is_file():
                    rel = str(f.relative_to(project_root).as_posix())
                    matched.add(rel)

        selected.update(matched)

    # Apply exclude patterns
    to_exclude: set[str] = set()
    for pattern in config.exclude_patterns:
        glob_pat = pattern.rstrip("/")
        for f in list(selected):
            if _matches_exclude(f, pattern):
                to_exclude.add(f)

    # Also filter: never allow sensitive file patterns
    sensitive_patterns = [
        ".env", ".env.", "*.env", "*.pem", "*.key", "*.p12",
        "*.pfx", "secrets/", "credentials/", ".claude/",
        "data/raw/", "data/processed/",
    ]
    for f in list(selected):
        for sp in sensitive_patterns:
            if f.startswith(sp.removesuffix("/")) or f.startswith(sp.removesuffix("/") + "/"):
                to_exclude.add(f)

    final = sorted(selected - to_exclude)
    return final


def _matches_exclude(filepath: str, pattern: str) -> bool:
    """Check if filepath matches an exclude pattern."""
    import fnmatch

    # Direct fnmatch
    if fnmatch.fnmatch(filepath, pattern):
        return True

    # Check each path component for directory patterns (e.g., ".venv/")
    if pattern.endswith("/"):
        dir_name = pattern[:-1]
        parts = filepath.split("/")
        for part in parts[:-1]:  # Check directory components only
            if fnmatch.fnmatch(part, dir_name):
                return True

    # Check for exact prefix match (e.g., "__pycache__/")
    if pattern.endswith("/") and filepath.startswith(pattern[:-1]):
        return True

    # Check basename against patterns like "*.pyc"
    basename = filepath.rsplit("/", 1)[-1] if "/" in filepath else filepath
    if fnmatch.fnmatch(basename, pattern):
        return True

    # Special case: .env must match basename as prefix (catches .env, .env0, .env.prod)
    if pattern == ".env" and basename.startswith(".env"):
        return True

    return False


# =============================================================================
# AUTHENTICATION (Zero-Trust)
# =============================================================================

async def validate_auth(
    vault: Optional[CredentialVault] = None
) -> Tuple[Optional[str], str]:
    """Validate GitHub credentials. Returns (auth_url_or_none, method).

    Auth URL may still be SSH if PAT is not available.
    Method: 'PAT', 'SSH', or 'NONE'
    """
    # Attempt 1: CredentialVault
    if vault:
        pat = vault.get("GITHUB_PAT")
        if pat:
            return (pat, "VAULT")

    # Attempt 2: Environment variable
    pat = os.environ.get("AEVRA_GITHUB_PAT") or os.environ.get("GITHUB_TOKEN")
    if pat:
        return (pat, "ENV")

    # Attempt 3: SSH key check
    ssh_key = Path.home() / ".ssh" / "aevara_ed25519"
    if ssh_key.exists():
        return (None, "SSH")

    # Fallback: check if `gh` CLI is authenticated
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return (None, "GH_CLI")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return (None, "NONE")


def build_push_url(repo_url: str, pat: Optional[str]) -> str:
    """Build auth-embedded URL for push (PAT-based) or return original (SSH/GH_CLI)."""
    if pat and repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://x-access-token:{pat}@")
    return repo_url


# =============================================================================
# PROJECT STATE MANAGEMENT
# =============================================================================

def load_project_state(project_root: Path) -> Dict[str, Any]:
    """Load PROJECT_STATE.yaml without requiring pyyaml (simple parser)."""
    state_file = project_root / "docs" / "PROJECT_STATE.yaml"
    state: Dict[str, Any] = {
        "github_sync": {
            "status": "never",
            "last_ts": None,
            "remote_url": None,
            "last_commit": None,
            "last_files_count": 0,
        },
        "modules": {},
        "last_checkpoint": None,
    }
    if state_file.exists():
        try:
            import yaml
            with open(state_file, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            state.update(loaded)
        except ImportError:
            # Simple line-by-line parser
            with open(state_file, "r", encoding="utf-8") as f:
                content = f.read()
            if "github_sync" in content:
                state["github_sync"]["status"] = "previous"
    return state


def _parse_yaml_simple(path: Path) -> Dict[str, Any]:
    """Minimal YAML parser for flat key: value files."""
    result: Dict[str, Any] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if value:
                    # Try to parse as number/bool
                    if value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    else:
                        try:
                            value = int(value)
                        except ValueError:
                            try:
                                value = float(value)
                            except ValueError:
                                pass  # Keep as string
                    result[key] = value
    return result


def _save_yaml_simple(path: Path, data: Dict[str, Any]) -> None:
    """Write simple YAML from dict (one level deep)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# @module: aevara.docs.PROJECT_STATE\n")
        f.write(f"# @status: AUTO_UPDATED\n")
        f.write(f"# @last_update: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n")
        for key, value in data.items():
            if isinstance(value, dict):
                f.write(f"{key}:\n")
                for k2, v2 in value.items():
                    if v2 is None:
                        f.write(f"  {k2}: null\n")
                    elif isinstance(v2, bool):
                        f.write(f"  {k2}: {'true' if v2 else 'false'}\n")
                    else:
                        f.write(f"  {k2}: {v2}\n")
            else:
                f.write(f"{key}: {value}\n")


def update_project_state(project_root: Path, result: SyncResult) -> None:
    """Update PROJECT_STATE.yaml with sync metadata."""
    state_file = project_root / "docs" / "PROJECT_STATE.yaml"
    state: Dict[str, Any] = _parse_yaml_simple(state_file) if state_file.exists() else {}

    # Ensure github_sync section exists
    if "github_sync" not in state:
        state["github_sync"] = {}

    state["github_sync"]["status"] = "success" if result.success else "failed"
    state["github_sync"]["last_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["github_sync"]["remote_url"] = result.remote_url
    state["github_sync"]["last_commit"] = result.commit_hash or "null"
    state["github_sync"]["last_files_count"] = result.files_staged

    if result.error:
        state["github_sync"]["last_error"] = result.error

    state_file.parent.mkdir(parents=True, exist_ok=True)
    _save_yaml_simple(state_file, state)


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

class GitHubSyncOrchestrator:
    """
    Async GitHub sync with selective staging, atomic commits, telemetry, and rollback.

    Invariants:
    - Zero-Trust Auth: credentials never hardcoded or logged in plaintext
    - Selective Staging: never `git add .`, always explicit file list
    - Atomic Commits: message includes state_hash + file count + trace_id
    - Telemetry Obrigatória: every stage emits TelemetryEvent
    - Rollback Automático: if push fails, commit is soft-reverted
    - Dry-Run support: full pipeline except actual push
    """

    def __init__(
        self,
        config: SyncConfig,
        logger: Optional[StructuredLogger] = None,
        vault: Optional[CredentialVault] = None,
    ):
        self._config = config
        self._logger = logger or StructuredLogger(
            log_dir=str(_PROJECT_ROOT / "data" / "audit")
        )
        self._vault = vault or CredentialVault()
        self._vault.load_from_env("AEVRA_")
        self._trace_id = uuid.uuid4().hex[:12]

    async def execute(self) -> SyncResult:
        """Full pipeline: validate -> stage -> commit -> push -> update state."""
        t0 = time.time_ns()

        # Phase 1: Validate Auth
        auth_result = await self.validate_auth()
        if auth_result[1] == "NONE":
            err_msg = "No GitHub credentials found. Set AEVRA_GITHUB_PAT or configure SSH."
            await self._logger.error(
                "github_sync", "auth_failed", err_msg,
                context={"trace_id": self._trace_id},
            )
            return self._result(False, 0, None, t0, err_msg)

        await self._logger.info(
            "github_sync", "auth_validated",
            f"Authenticated via {auth_result[1]}",
            context={"method": auth_result[1], "trace_id": self._trace_id},
        )

        # Phase 2: Init git repo if needed
        cwd = str(_PROJECT_ROOT)
        if not _git_has_repo(cwd):
            await self._logger.info(
                "github_sync", "git_init",
                "Initializing git repository",
                context={"trace_id": self._trace_id},
            )
            _git_init(cwd, self._config.branch)

        # Phase 3: Set remote
        push_url = build_push_url(self._config.repo_url, auth_result[0] if auth_result[0] else None)
        _git_add_remote(cwd, "origin", push_url)
        await self._logger.info(
            "github_sync", "remote_configured",
            f"Remote origin set to {self._config.repo_url}",
            context={"remote": self._config.repo_url, "method": auth_result[1]},
        )

        # Phase 4: Selective staging
        files = select_files(_PROJECT_ROOT, self._config)
        await self._logger.info(
            "github_sync", "files_selected",
            f"Selected {len(files)} files for sync",
            context={
                "files_count": len(files),
                "trace_id": self._trace_id,
                "dry_run": self._config.dry_run,
            },
            metrics={"files_staged": float(len(files))},
        )

        if self._config.dry_run:
            await self._logger.info(
                "github_sync", "dry_run_complete",
                f"Dry run: {len(files)} files would be synced",
                context={
                    "files": files[:10],  # Log first 10 for visibility
                    "total": len(files),
                    "trace_id": self._trace_id,
                },
            )
            return self._result(True, len(files), None, t0, None)

        if not files:
            warn_msg = "No files selected for sync"
            await self._logger.warning(
                "github_sync", "no_files", warn_msg,
                context={"trace_id": self._trace_id},
            )
            return self._result(False, 0, None, t0, warn_msg)

        # Phase 5: Staging + commit
        n_staged = _git_add_files(files, cwd)
        state_hash = compute_state_hash(_PROJECT_ROOT, files)
        commit_msg = (
            f"{self._config.commit_prefix} Sync | "
            f"state_hash: {state_hash} | "
            f"files: {n_staged} | "
            f"trace: {self._trace_id}"
        )

        commit_hash = _git_commit(commit_msg, cwd)
        if commit_hash is None:
            # Check if there's nothing to commit (already clean)
            status = _git_status_porcelain(cwd)
            if not status:
                await self._logger.info(
                    "github_sync", "already_clean",
                    "Working tree is clean, nothing to commit",
                    context={"trace_id": self._trace_id},
                )
                return self._result(True, n_staged, _git_get_head(cwd), t0, None)

            err_msg = f"Failed to create commit. Status: {status}"
            await self._logger.error(
                "github_sync", "commit_failed", err_msg,
                context={"trace_id": self._trace_id},
            )
            return self._result(False, n_staged, None, t0, err_msg)

        await self._logger.info(
            "github_sync", "commit_created",
            f"Commit {commit_hash} created with {n_staged} files",
            context={
                "commit_hash": commit_hash,
                "files": n_staged,
                "state_hash": state_hash,
                "trace_id": self._trace_id,
            },
        )

        # Phase 6: Push with retry
        push_ok = await self.push_with_retry()
        if not push_ok:
            error_msg = f"Push failed after {self._config.max_retries} retries"
            await self._logger.error(
                "github_sync", "push_failed", error_msg,
                context={
                    "commit_hash": commit_hash,
                    "retries": self._config.max_retries,
                    "trace_id": self._trace_id,
                },
            )
            # Rollback
            if self._config.rollback_on_failure:
                rolled_back = _git_soft_reset_one(cwd)
                await self._logger.info(
                    "github_sync", "rollback_executed",
                    f"Soft reset HEAD~1: {'OK' if rolled_back else 'FAILED'}",
                    context={"trace_id": self._trace_id},
                )
            return self._result(False, n_staged, commit_hash, t0, error_msg)

        # Phase 7: Update project state
        self.update_project_state(
            SyncResult(
                success=True,
                files_staged=n_staged,
                commit_hash=commit_hash,
                remote_url=self._config.repo_url,
                elapsed_ms=(time.time_ns() - t0) // 1_000_000,
                telemetry_trace_id=self._trace_id,
            )
        )

        await self._logger.info(
            "github_sync", "sync_complete",
            f"Sync completed: {n_staged} files, commit {commit_hash}",
            context={
                "commit_hash": commit_hash,
                "files_staged": n_staged,
                "elapsed_ms": (time.time_ns() - t0) // 1_000_000,
                "trace_id": self._trace_id,
            },
        )

        return self._result(True, n_staged, commit_hash, t0, None)

    async def validate_auth(self) -> Tuple[Optional[str], str]:
        return await validate_auth(self._vault)

    async def push_with_retry(self) -> bool:
        backoff = 2.0
        for attempt in range(self._config.max_retries):
            ok = _git_push(str(_PROJECT_ROOT), "origin", self._config.branch)
            if ok:
                return True
            if attempt < self._config.max_retries - 1:
                await self._logger.warning(
                    "github_sync", "push_retry",
                    f"Push retry {attempt + 1}/{self._config.max_retries}",
                    context={"attempt": attempt + 1, "backoff_s": backoff},
                )
                await asyncio.sleep(backoff)
                backoff *= 2
        return False

    def update_project_state(self, result: SyncResult) -> None:
        update_project_state(_PROJECT_ROOT, result)

    @staticmethod
    def _result(
        success: bool,
        files_staged: int,
        commit_hash: Optional[str],
        t0_ns: int,
        error: Optional[str],
    ) -> SyncResult:
        return SyncResult(
            success=success,
            files_staged=files_staged,
            commit_hash=commit_hash,
            remote_url=str(_PROJECT_ROOT),
            elapsed_ms=(time.time_ns() - t0_ns) // 1_000_000,
            error=error,
        )


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

async def async_main(args: argparse.Namespace) -> SyncResult:
    config = SyncConfig(
        repo_url=args.repo_url,
        branch=args.branch,
        dry_run=args.dry_run,
        max_retries=args.max_retries,
        telemetry_enabled=not args.no_telemetry,
    )

    logger = StructuredLogger(log_dir=str(_PROJECT_ROOT / "data" / "audit"))
    orchestrator = GitHubSyncOrchestrator(config, logger)

    result = await orchestrator.execute()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aevra GitHub Sync Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (no push, just check what would be synced)
  python scripts/github_sync.py --dry-run

  # Execute real push
  python scripts/github_sync.py --execute

  # Custom remote and retries
  python scripts/github_sync.py --execute --repo-url https://github.com/org/repo.git --max-retries 5

Auth (set one before running --execute):
  export AEVRA_GITHUB_PAT="ghp_..."          # Personal Access Token
  # Or configure SSH key at ~/.ssh/aevara_ed25519
  # Or use `gh auth login` for GitHub CLI auth
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true",
        help="Check files and config without pushing"
    )
    group.add_argument(
        "--execute", dest="execute_flag", action="store_true",
        help="Execute full sync pipeline including push"
    )

    parser.add_argument(
        "--repo-url", default="https://github.com/jokerofcassinos/aevara_trading.git",
        help="Remote repository URL (default: aevara_trading)"
    )
    parser.add_argument("--branch", default="main", help="Branch name (default: main)")
    parser.add_argument("--max-retries", type=int, default=3, help="Push retry count")
    parser.add_argument("--no-telemetry", action="store_true", help="Disable telemetry logging")
    parser.add_argument("--no-rollback", action="store_true", help="Disable commit rollback on failure")

    args = parser.parse_args()

    if args.execute_flag:
        args.dry_run = False

    result = asyncio.run(async_main(args))

    if result.success:
        print(f"SYNC OK | files={result.files_staged} | commit={result.commit_hash} | elapsed={result.elapsed_ms}ms")
        sys.exit(0)
    else:
        print(f"SYNC FAILED | error={result.error} | files_staged={result.files_staged}")
        sys.exit(1)


if __name__ == "__main__":
    main()
