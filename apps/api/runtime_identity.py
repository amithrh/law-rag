"""Stable identity for the code and configuration serving a request."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_IGNORED_PREFIXES = (".git/", "data/", "reports/", "logs/", ".venv/")
_CODE_SUFFIXES = {".py", ".json", ".toml", ".yaml", ".yml", ".ts", ".tsx", ".js", ".mjs", ".css"}
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def _run_git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def _git_worktree_fingerprint() -> str | None:
    commit_raw = _run_git("rev-parse", "HEAD")
    diff = _run_git("diff", "--binary", "HEAD", "--", ".")
    untracked_raw = _run_git("ls-files", "--others", "--exclude-standard")
    if commit_raw is None or diff is None or untracked_raw is None:
        return None
    commit = commit_raw.strip()
    if not commit:
        return None
    untracked = untracked_raw.splitlines()
    digest = hashlib.sha256()
    digest.update(commit.encode())
    digest.update(b"\0")
    digest.update(hashlib.sha256(diff.encode()).digest())
    for raw_path in sorted(untracked):
        path = raw_path.strip()
        if not path or any(path.startswith(prefix) for prefix in _IGNORED_PREFIXES):
            continue
        if Path(path).suffix.lower() not in _CODE_SUFFIXES:
            continue
        file_path = ROOT / path
        try:
            if not file_path.is_file():
                continue
            file_bytes = file_path.read_bytes()
        except OSError:
            return None
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(file_bytes).digest())
    return digest.hexdigest()


@lru_cache(maxsize=1)
def runtime_identity() -> dict[str, str]:
    """Return an opaque build fingerprint without exposing local paths."""
    configured = os.getenv("LAW_RAG_BUILD_FINGERPRINT", "").strip()
    computed = _git_worktree_fingerprint()
    if configured:
        if _FINGERPRINT_RE.fullmatch(configured) is None:
            return {"fingerprint": "unknown", "source": "unavailable"}
        if computed is None:
            return {"fingerprint": configured, "source": "environment_unverified"}
        if configured != computed:
            return {"fingerprint": "unknown", "source": "unavailable"}
        return {"fingerprint": configured, "source": "environment_verified"}
    if computed:
        return {"fingerprint": computed, "source": "git_worktree"}
    return {"fingerprint": "unknown", "source": "unavailable"}


__all__ = ["runtime_identity"]
