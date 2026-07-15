#!/usr/bin/env python3
"""Audit answer ownership in a scored timed-eval JSONL result.

The product currently has reviewed workflow contracts and legacy deterministic
templates in parallel. This command makes ownership drift observable: it
reports unexpected owners, legacy shadows, and critical prompts that fall
through to an LLM. It does not decide legal correctness and it never changes
routing or answer policy automatically.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


UNKNOWN_OWNERS = {"", "unknown", "none"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval_jsonl", type=Path, help="Scored JSONL emitted by scripts/eval_timed_100.py")
    parser.add_argument("--report", type=Path, help="Optional Markdown report path")
    parser.add_argument("--max-unexpected-owners", type=int, default=0)
    parser.add_argument("--max-critical-llm-owners", type=int, default=0)
    parser.add_argument("--allow-fail", action="store_true", help="Write the audit without a non-zero exit code")
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: expected a JSON object")
        rows.append(value)
    if not rows:
        raise ValueError(f"no eval rows found in {path}")
    return rows


def expected_owners(value: object) -> set[str]:
    if value is None:
        return set()
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return {str(item).strip().lower() for item in values if str(item).strip()}


def row_owner(row: dict[str, Any]) -> str:
    return str(row.get("workflow_answer_owner") or "").strip().lower()


def audit_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    owner_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    shadows: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    critical_llm: list[dict[str, Any]] = []
    ownerless: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        owner = row_owner(row)
        route = str(row.get("route_category") or "unknown")
        owner_counts[owner or "unknown"] += 1
        route_counts[route] += 1
        summary = {
            "eval_index": index,
            "query": str(row.get("query") or ""),
            "route_category": route,
            "answer_owner": owner or "unknown",
            "workflow_id": row.get("workflow_id"),
            "shadowed_workflow_id": row.get("shadowed_workflow_id"),
            "product_failures": row.get("product_failures") or [],
        }
        expected = expected_owners(row.get("expected_answer_owner"))
        if expected and owner not in expected:
            unexpected.append({**summary, "expected_answer_owners": sorted(expected)})
        if row.get("workflow_shadowed_by_legacy") is True:
            shadows.append(summary)
        if str(row.get("product_priority") or "").lower() == "critical" and owner == "llm":
            critical_llm.append(summary)
        if owner in UNKNOWN_OWNERS:
            ownerless.append(summary)

    return {
        "rows": len(rows),
        "answer_owner_counts": dict(owner_counts),
        "route_counts": dict(route_counts),
        "legacy_shadows": shadows,
        "unexpected_owners": unexpected,
        "critical_llm_owners": critical_llm,
        "ownerless_rows": ownerless,
    }


def audit_failures(summary: dict[str, Any], args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    unexpected = len(summary["unexpected_owners"])
    critical_llm = len(summary["critical_llm_owners"])
    if unexpected > args.max_unexpected_owners:
        failures.append(f"unexpected answer owners: {unexpected} > {args.max_unexpected_owners}")
    if critical_llm > args.max_critical_llm_owners:
        failures.append(f"critical LLM owners: {critical_llm} > {args.max_critical_llm_owners}")
    return failures


def clip(value: object, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def markdown_report(summary: dict[str, Any], failures: list[str], source: Path | str) -> str:
    lines = [
        "# Answer Ownership Audit",
        "",
        f"Input: `{source}`",
        f"Result: {'PASS' if not failures else 'FAIL'}",
        "",
        "## Summary",
        "",
        f"- Rows: {summary['rows']}",
        f"- Legacy workflow shadows: {len(summary['legacy_shadows'])}",
        f"- Unexpected answer owners: {len(summary['unexpected_owners'])}",
        f"- Critical rows owned by LLM: {len(summary['critical_llm_owners'])}",
        f"- Rows without an owner: {len(summary['ownerless_rows'])}",
        "",
        "## Owner Distribution",
        "",
        "| owner | rows |",
        "| --- | ---: |",
    ]
    for owner, count in sorted(summary["answer_owner_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {owner} | {count} |")
    lines.extend(["", "## Gate Failures", ""])
    lines.extend([f"- {failure}" for failure in failures] or ["- none"])
    for title, rows in (
        ("Unexpected Owners", summary["unexpected_owners"]),
        ("Legacy Shadows", summary["legacy_shadows"]),
        ("Critical LLM Owners", summary["critical_llm_owners"]),
        ("Ownerless Rows", summary["ownerless_rows"]),
    ):
        lines.extend(["", f"## {title}", "", "| route | owner | workflow | query |", "| --- | --- | --- | --- |"])
        if rows:
            for row in rows[:50]:
                workflow = row.get("workflow_id") or row.get("shadowed_workflow_id") or ""
                query = clip(row["query"]).replace("|", "\\|")
                lines.append(f"| {row['route_category']} | {row['answer_owner']} | {workflow} | {query} |")
        else:
            lines.append("| none |  |  |  |")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    summary = audit_rows(load_rows(args.eval_jsonl))
    failures = audit_failures(summary, args)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown_report(summary, failures, args.eval_jsonl), encoding="utf-8")
    print(f"Answer ownership audit: {'PASS' if not failures else 'FAIL'}")
    print(f"Rows: {summary['rows']}")
    print(f"Legacy shadows: {len(summary['legacy_shadows'])}")
    print(f"Unexpected owners: {len(summary['unexpected_owners'])}")
    print(f"Critical LLM owners: {len(summary['critical_llm_owners'])}")
    for failure in failures:
        print(f"- {failure}")
    return 0 if args.allow_fail or not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
