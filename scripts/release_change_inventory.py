#!/usr/bin/env python3
"""Create a deterministic inventory of release-worktree changes."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Change:
    status: str
    path: str
    concern: str
    original_path: str | None = None


_PREFIX_CONCERNS = (
    (("apps/api/tests/",), "api_tests"),
    (("apps/api/",), "api_runtime"),
    (("apps/web/",), "web"),
    (("packages/authority_registry/",), "authority_registry"),
    (("packages/ingest/", "packages/chunking/", "packages/retrieval/"), "data_and_retrieval"),
    (("packages/eval/", "reports/"), "evaluation_evidence"),
    (("infra/", ".github/"), "infrastructure_and_ci"),
    (("docs/",), "documentation_and_governance"),
)

_EXACT_CONCERNS = {
    ".env.example": "infrastructure_and_ci",
    "Makefile": "infrastructure_and_ci",
    "pyproject.toml": "infrastructure_and_ci",
    "uv.lock": "infrastructure_and_ci",
    "AGENTS.md": "documentation_and_governance",
    "README.md": "documentation_and_governance",
    "PLAN.md": "documentation_and_governance",
    "OPEN_QUESTIONS.md": "documentation_and_governance",
}


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(("git", "-C", str(repo), *args))


def _categorize(path: str) -> str:
    if path.startswith("scripts/"):
        filename = Path(path).name
        if any(token in filename for token in ("eval", "holdout", "audit")):
            return "evaluation_evidence"
        if any(
            token in filename
            for token in ("ingest", "promote", "repair", "quarantine", "source", "chunk")
        ):
            return "data_and_retrieval"
        return "tooling"
    if exact_concern := _EXACT_CONCERNS.get(path):
        return exact_concern
    for prefixes, concern in _PREFIX_CONCERNS:
        if path.startswith(prefixes):
            return concern
    return "other"


def _parse_porcelain_v1_z(raw: bytes) -> list[Change]:
    records = raw.split(b"\0")
    changes: list[Change] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise ValueError(f"unexpected git status record: {record[:80]!r}")
        status = record[:2].decode("ascii")
        path = record[3:].decode("utf-8", errors="surrogateescape")
        original_path: str | None = None
        if "R" in status or "C" in status:
            if index >= len(records) or not records[index]:
                raise ValueError(f"missing original path for {path!r}")
            original_path = records[index].decode("utf-8", errors="surrogateescape")
            index += 1
        changes.append(
            Change(
                status=status,
                path=path,
                concern=_categorize(path),
                original_path=original_path,
            )
        )
    return sorted(changes, key=lambda change: (change.concern, change.path, change.status))


def build_inventory(repo: Path) -> dict[str, object]:
    repo = repo.resolve()
    changes = _parse_porcelain_v1_z(
        _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    )
    status_counts = Counter(change.status for change in changes)
    concern_counts = Counter(change.concern for change in changes)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "repo_root": str(repo),
        "branch": _git(repo, "branch", "--show-current").decode().strip(),
        "head": _git(repo, "rev-parse", "HEAD").decode().strip(),
        "working_tree_clean": not changes,
        "counts": {
            "total": len(changes),
            "tracked_changes": sum(change.status != "??" for change in changes),
            "untracked": sum(change.status == "??" for change in changes),
            "by_status": dict(sorted(status_counts.items())),
            "by_concern": dict(sorted(concern_counts.items())),
        },
        "changes": [asdict(change) for change in changes],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Git worktree to inventory (defaults to the repository containing this script)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write formatted JSON to this path instead of standard output",
    )
    args = parser.parse_args()

    payload = json.dumps(build_inventory(args.repo), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
