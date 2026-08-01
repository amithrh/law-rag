#!/usr/bin/env python3
"""Audit MatterPlan authority bindings across a query inventory.

This is an offline producer audit. It does not retrieve documents or call a
model; it verifies that each routed query creates enforceable obligations that
are bound to the source packs the serving path will actually search.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from apps.api.legal_issue_plan import build_matter_plan
from apps.api.matter_router import route_matter
from apps.api.source_gap import (
    _is_deferred_date_regime_entry,
    _is_split_constitutional_descriptor,
    is_active_plan_authority_entry,
    matter_plan_integrity_gap,
)
from scripts.eval_timed_100 import load_eval_rows


def profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories: Counter[str] = Counter()
    owners: Counter[str] = Counter()
    gap_kinds: Counter[str] = Counter()
    binding_failures: Counter[str] = Counter()
    empty_ledger: list[dict[str, str]] = []
    integrity_gap_queries: list[dict[str, Any]] = []
    deferred_regime_rows = 0
    deferred_regime_obligations = 0
    deferred_regime_evidence_required = 0
    plan_count = 0
    integrity_gap_rows = 0

    for row in rows:
        query = str(row.get("query") or "").strip()
        if not query:
            continue
        route = route_matter(query)
        categories[route.category] += 1
        plan = build_matter_plan(query, route)
        if plan is None:
            continue
        plan_count += 1
        owners[plan.answer_policy.required_primary_owner] += 1
        if not plan.authority_ledger:
            empty_ledger.append({"query": query, "category": route.category})

        gap = matter_plan_integrity_gap(plan, query)
        if gap:
            integrity_gap_rows += 1
            for kind in gap.get("gap_kinds", []):
                gap_kinds[str(kind)] += 1
            integrity_gap_queries.append({
                "query": query,
                "category": route.category,
                "gap_kinds": list(gap.get("gap_kinds", [])),
                "missing_required_sources": [
                    str(item.get("required_source") or "")
                    for item in gap.get("missing_required_sources", [])
                ],
            })

        packs = {source.source_pack_id: source for source in plan.retrieval_sources}
        row_has_deferred_regime = False
        for entry in plan.authority_ledger:
            # Keep this audit aligned with the serving source-gap path. The
            # ledger also carries intake pointers and conditional context that
            # are intentionally not citable obligations for this query.
            if not is_active_plan_authority_entry(entry, plan=plan, query=query):
                continue
            # A combined Article 21/22 obligation is intentionally verified by
            # the passage-level constitutional matcher, not by one source-pack
            # binding. It is therefore not an inventory binding failure.
            if _is_split_constitutional_descriptor(
                entry.source,
                source_pack_id=entry.source_pack_id,
            ):
                continue
            if _is_deferred_date_regime_entry(plan, entry):
                if not row_has_deferred_regime:
                    deferred_regime_rows += 1
                    row_has_deferred_regime = True
                deferred_regime_obligations += 1
                deferred_regime_evidence_required += 1
                continue
            if entry.note == "date_dependent_regime_choose_by_incident_date":
                # Keep an unready composite visible as a real binding failure;
                # unlike a ready composite, it cannot safely defer to the
                # incident-date evidence gate.
                if not row_has_deferred_regime:
                    deferred_regime_rows += 1
                    row_has_deferred_regime = True
            pack = packs.get(entry.source_pack_id) if entry.source_pack_id else None
            if pack is None:
                binding_failures["missing_source_pack"] += 1
                continue
            if not pack.doc_ids:
                binding_failures["missing_document_identity"] += 1
            if not pack.source_types:
                binding_failures["missing_source_type_binding"] += 1
            if entry.required_anchor_patterns and not any(
                str(pattern).lower() in str(anchor).lower()
                for pattern in entry.required_anchor_patterns
                for anchor in pack.anchor_patterns
            ):
                binding_failures["missing_required_anchor_binding"] += 1
            if entry.registry_key and entry.authority_id not in pack.authority_ids:
                binding_failures["missing_registry_authority_binding"] += 1

    return {
        "rows": len(rows),
        "plans": plan_count,
        "categories": dict(categories.most_common()),
        "owners": dict(owners.most_common()),
        "integrity_gap_rows": integrity_gap_rows,
        "integrity_gap_kinds": dict(gap_kinds.most_common()),
        "binding_failures": dict(binding_failures.most_common()),
        "integrity_gap_queries": integrity_gap_queries,
        "deferred_regime_rows": deferred_regime_rows,
        "deferred_regime_obligations": deferred_regime_obligations,
        "deferred_regime_evidence_required": deferred_regime_evidence_required,
        "empty_ledger": empty_ledger,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries-dir", type=Path, default=Path("data/eval_500"))
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    rows = load_eval_rows(args.queries_dir, limit=args.limit, seed=args.seed)
    result = profile(rows)
    payload = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
