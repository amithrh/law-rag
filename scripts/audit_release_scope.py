#!/usr/bin/env python3
"""Audit the limited-V1 release scope against the executable legal plan.

The scope manifest is governance data, not a switch that can make a route safe
by declaration. This audit resolves every candidate through the production
router and MatterPlan, checks its exact answer owner and registry-backed
must-cite obligations, and requires fingerprinted evidence for provenance,
natural retrieval, and independent legal review before a scenario can be
approved.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from apps.api.config import get_settings
from apps.api.legal_issue_plan import (
    PLAN_OWNED_ANSWER_ROUTES,
    build_matter_plan,
    plan_owned_answer_route,
)
from apps.api.matter_router import route_matter
from apps.api.source_gap import is_active_plan_authority_entry

from authority_registry import load_authority_registry

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCOPE = ROOT / "config" / "release_scope_v1_20260801.json"
EVIDENCE_GATES = (
    "active_corpus_provenance",
    "natural_retrieval",
    "independent_legal_review",
)
PASSING_STATUS = "passed"
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class ScopeValidationError(ValueError):
    """The release-scope manifest is malformed or incomplete."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScopeValidationError(message)


def _unique_ids(rows: list[dict[str, Any]], field: str, label: str) -> set[str]:
    values = [str(row.get(field) or "") for row in rows]
    _require(all(values), f"{label} entries require {field}")
    _require(len(values) == len(set(values)), f"duplicate {label} {field}")
    return set(values)


def load_release_scope(path: Path = DEFAULT_SCOPE) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "release scope must be a JSON object")
    _require(payload.get("schema_version") == 1, "unsupported release-scope schema")
    _require(payload.get("release_decision") in {"no_go", "go"}, "invalid release decision")
    candidate_fingerprint = str(payload.get("candidate_fingerprint") or "")
    if payload.get("release_decision") == "go":
        _require(
            bool(FINGERPRINT_RE.fullmatch(candidate_fingerprint)),
            "a go decision requires the exact SHA-256 candidate fingerprint",
        )
    _require(
        payload.get("default_unlisted_policy") == "source_gap_handoff",
        "unlisted scenarios must fail closed to source_gap_handoff",
    )

    lanes = payload.get("lanes")
    candidates = payload.get("candidate_scenarios")
    excluded = payload.get("excluded_plan_owned_scenarios")
    _require(isinstance(lanes, list) and lanes, "release scope requires lanes")
    _require(isinstance(candidates, list) and candidates, "release scope requires candidates")
    _require(isinstance(excluded, list), "release scope requires an exclusion inventory")

    lane_ids = _unique_ids(lanes, "lane_id", "lane")
    candidate_ids = _unique_ids(candidates, "scenario_id", "candidate")
    excluded_ids = _unique_ids(excluded, "scenario_id", "excluded scenario")
    _require(not candidate_ids & excluded_ids, "candidate and excluded scenarios overlap")

    plan_owned_ids = {rule.scenario_id for rule in PLAN_OWNED_ANSWER_ROUTES}
    _require(
        candidate_ids | excluded_ids == plan_owned_ids,
        "candidate plus excluded scenarios must exactly cover PLAN_OWNED_ANSWER_ROUTES",
    )

    for row in candidates:
        scenario_id = row["scenario_id"]
        _require(row.get("lane_id") in lane_ids, f"{scenario_id}: unknown lane")
        _require(
            row.get("support_status") in {"candidate_blocked", "approved"},
            f"{scenario_id}: invalid support status",
        )
        _require(bool(str(row.get("representative_query") or "").strip()), f"{scenario_id}: query required")
        _require(bool(str(row.get("owner_token") or "").strip()), f"{scenario_id}: owner required")
        evidence = row.get("evidence")
        _require(isinstance(evidence, dict), f"{scenario_id}: evidence object required")
        _require(set(evidence) == set(EVIDENCE_GATES), f"{scenario_id}: evidence gates are incomplete")
        for gate_name in EVIDENCE_GATES:
            gate = evidence[gate_name]
            _require(isinstance(gate, dict), f"{scenario_id}: {gate_name} must be an object")
            status = gate.get("status")
            _require(
                status in {"pending", "unmeasured", "failed", PASSING_STATUS},
                f"{scenario_id}: invalid {gate_name} status",
            )
            if status == PASSING_STATUS:
                _require(bool(gate.get("artifact")), f"{scenario_id}: passed {gate_name} needs artifact")
                _require(
                    bool(FINGERPRINT_RE.fullmatch(str(gate.get("candidate_fingerprint") or ""))),
                    f"{scenario_id}: passed {gate_name} needs SHA-256 candidate fingerprint",
                )

    for row in excluded:
        scenario_id = row["scenario_id"]
        _require(bool(row.get("reason_code")), f"{scenario_id}: exclusion reason required")
        _require(
            row.get("fallback_owner") == "source_gap_handoff",
            f"{scenario_id}: excluded scenario must fail closed",
        )
    return payload


def _manifest_fingerprint(scope: dict[str, Any]) -> str:
    canonical = json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _authority_blockers(plan: Any, query: str) -> tuple[list[dict[str, Any]], list[str]]:
    registry = load_authority_registry()
    packs = {source.source_pack_id: source for source in plan.retrieval_sources}
    authority_rows: list[dict[str, Any]] = []
    blockers: list[str] = []

    active = [
        entry
        for entry in plan.authority_ledger
        if entry.must_cite and is_active_plan_authority_entry(entry, plan=plan, query=query)
    ]
    if not active:
        blockers.append("no_active_must_cite_authority")

    for entry in active:
        entry_blockers: list[str] = []
        authority_id = str(entry.authority_id or "")
        registry_key = str(entry.registry_key or "")
        if not authority_id or authority_id.startswith("authority_provisional_"):
            entry_blockers.append("provisional_authority_id")
        if not registry_key:
            entry_blockers.append("missing_registry_key")
            record = None
        else:
            record = registry.by_key(registry_key)
            if record is None:
                entry_blockers.append("registry_record_missing")
            elif record.authority_id_expected != authority_id:
                entry_blockers.append("registry_authority_id_mismatch")

        pack = packs.get(entry.source_pack_id) if entry.source_pack_id else None
        if pack is None:
            entry_blockers.append("missing_retrieval_source_pack")
        else:
            if registry_key and authority_id not in pack.authority_ids:
                entry_blockers.append("missing_pack_authority_binding")
            if not entry.required_anchor_patterns:
                entry_blockers.append("missing_required_anchor")
            elif not any(
                str(required).lower() in str(actual).lower()
                for required in entry.required_anchor_patterns
                for actual in pack.anchor_patterns
            ):
                entry_blockers.append("missing_pack_anchor_binding")

        authority_rows.append(
            {
                "source": entry.source,
                "authority_id": entry.authority_id,
                "registry_key": entry.registry_key,
                "source_pack_id": entry.source_pack_id,
                "required_anchor_patterns": list(entry.required_anchor_patterns),
                "blockers": entry_blockers,
            }
        )
        blockers.extend(f"authority:{registry_key or authority_id or entry.source}:{code}" for code in entry_blockers)
    return authority_rows, blockers


def _evidence_blockers(
    row: dict[str, Any],
    *,
    candidate_fingerprint: str | None,
) -> list[str]:
    blockers = []
    for gate_name in EVIDENCE_GATES:
        gate = row["evidence"][gate_name]
        if gate["status"] != PASSING_STATUS:
            blockers.append(f"evidence:{gate_name}:{gate['status']}")
            continue
        artifact = Path(str(gate["artifact"]))
        artifact_path = artifact if artifact.is_absolute() else ROOT / artifact
        if not artifact_path.is_file():
            blockers.append(f"evidence:{gate_name}:artifact_missing")
        if candidate_fingerprint and gate["candidate_fingerprint"] != candidate_fingerprint:
            blockers.append(f"evidence:{gate_name}:candidate_fingerprint_mismatch")
    return blockers


def _owner_blockers(
    row: dict[str, Any],
    declared_rule: Any,
    owner: Any,
) -> list[str]:
    blockers = []
    expected_owner = row["owner_token"]
    if owner is None or owner.scenario_id != row["scenario_id"]:
        blockers.append("representative_query_owner_mismatch")
    elif owner.owner_token != expected_owner:
        blockers.append("representative_query_owner_token_mismatch")
    if declared_rule.owner_token != expected_owner:
        blockers.append("manifest_owner_token_drift")
    if declared_rule.fallback_owner != "source_gap_handoff":
        blockers.append("owner_fallback_not_fail_closed")
    return blockers


def _plan_contract_audit(
    plan: Any,
    *,
    route_category: str,
    expected_owner: str,
    query: str,
) -> tuple[str | None, str, list[dict[str, Any]], list[str], list[str]]:
    if plan is None:
        return None, route_category, [], [], ["matter_plan_missing"]

    blockers = []
    if plan.answer_policy.required_primary_owner != expected_owner:
        blockers.append("matter_plan_owner_mismatch")
    if plan.answer_policy.fallback_owner != "source_gap_handoff":
        blockers.append("matter_plan_fallback_not_fail_closed")
    if plan.answer_policy.allow_freeform_llm:
        blockers.append("freeform_llm_allowed")
    if not plan.answer_policy.requires_reviewed_contract:
        blockers.append("reviewed_contract_not_required")
    authority_rows, authority_contract_blockers = _authority_blockers(plan, query)
    blockers.extend(authority_contract_blockers)
    return (
        plan.plan_id,
        plan.primary_issue,
        authority_rows,
        authority_contract_blockers,
        blockers,
    )


def _audit_candidate(
    row: dict[str, Any],
    *,
    rules: dict[str, Any],
    candidate_fingerprint: str | None,
) -> dict[str, Any]:
    scenario_id = row["scenario_id"]
    query = row["representative_query"]
    expected_owner = row["owner_token"]
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)
    plan = build_matter_plan(query, route)
    blockers = _owner_blockers(row, rules[scenario_id], owner)
    (
        plan_id,
        route_category,
        authority_rows,
        authority_contract_blockers,
        plan_blockers,
    ) = _plan_contract_audit(
        plan,
        route_category=route.category,
        expected_owner=expected_owner,
        query=query,
    )
    blockers.extend(plan_blockers)
    blockers.extend(
        _evidence_blockers(row, candidate_fingerprint=candidate_fingerprint)
    )
    if row["support_status"] != "approved":
        blockers.append(f"support_status:{row['support_status']}")
    return {
        "scenario_id": scenario_id,
        "lane_id": row["lane_id"],
        "representative_query": query,
        "route_category": route_category,
        "plan_id": plan_id,
        "owner_token": expected_owner,
        "support_status": row["support_status"],
        "registry_contract_ready": bool(authority_rows) and not authority_contract_blockers,
        "launch_ready": not blockers,
        "active_must_cite_authorities": authority_rows,
        "blockers": blockers,
    }


def audit_release_scope(scope: dict[str, Any]) -> dict[str, Any]:
    rules = {rule.scenario_id: rule for rule in PLAN_OWNED_ANSWER_ROUTES}
    scenario_results = [
        _audit_candidate(
            row,
            rules=rules,
            candidate_fingerprint=scope.get("candidate_fingerprint"),
        )
        for row in scope["candidate_scenarios"]
    ]

    global_blockers = []
    if scope["release_decision"] != "go":
        global_blockers.append(f"release_decision:{scope['release_decision']}")
    not_ready = [row["scenario_id"] for row in scenario_results if not row["launch_ready"]]
    if not_ready:
        global_blockers.append(f"candidate_scenarios_not_ready:{len(not_ready)}")

    registry_ready = [
        row["scenario_id"] for row in scenario_results if row["registry_contract_ready"]
    ]
    return {
        "schema_version": 1,
        "scope_id": scope["scope_id"],
        "scope_manifest_sha256": _manifest_fingerprint(scope),
        "release_decision": scope["release_decision"],
        "launch_ready": not global_blockers,
        "summary": {
            "lanes": len(scope["lanes"]),
            "candidate_scenarios": len(scenario_results),
            "excluded_plan_owned_scenarios": len(scope["excluded_plan_owned_scenarios"]),
            "registry_contract_ready_scenarios": len(registry_ready),
            "launch_ready_scenarios": len(scenario_results) - len(not_ready),
        },
        "registry_contract_ready_scenario_ids": registry_ready,
        "not_launch_ready_scenario_ids": not_ready,
        "global_blockers": global_blockers,
        "scenarios": scenario_results,
        "excluded_plan_owned_scenarios": scope["excluded_plan_owned_scenarios"],
    }


def _live_projection_blockers(
    required: dict[str, Any],
    projection: dict[str, Any] | None,
) -> list[str]:
    if projection is None:
        return ["projection_missing"]
    registry_key = str(required["registry_key"])
    record = load_authority_registry().by_key(registry_key)
    if record is None:
        return ["registry_record_missing"]

    blockers = []
    if projection["authority_id"] != required["authority_id"]:
        blockers.append("authority_id_mismatch")
    if projection["record_sha256"] != record.record_sha256:
        blockers.append("record_sha256_mismatch")
    chunk_anchor = str(projection["chunk_anchor"]).split("@", 1)[0].lower()
    canonical_anchor = str(projection["canonical_anchor"]).split("@", 1)[0].lower()
    if not chunk_anchor.endswith(canonical_anchor):
        blockers.append("canonical_anchor_mismatch")
    if projection["quarantined"]:
        blockers.append("projection_quarantined")
    if not projection["provenance_verified"]:
        blockers.append("chunk_provenance_unverified")
    if projection["provenance_tier"] != "canonical":
        blockers.append("source_not_canonical")
    if projection["raw_sha256"] != record.provenance.raw_sha256:
        blockers.append("source_raw_sha256_mismatch")
    if projection["raw_bytes_size"] != record.provenance.raw_bytes_size:
        blockers.append("source_raw_bytes_size_mismatch")
    return blockers


async def audit_live_registry_ready_corpus(
    scope_audit: dict[str, Any],
) -> dict[str, Any]:
    scenarios = [
        row for row in scope_audit["scenarios"] if row["registry_contract_ready"]
    ]
    required_by_key = {
        authority["registry_key"]: authority
        for scenario in scenarios
        for authority in scenario["active_must_cite_authorities"]
    }
    keys = sorted(required_by_key)
    settings = get_settings()
    connection = await asyncpg.connect(
        settings.resolved_database_url_host_side,
        timeout=settings.postgres_connect_timeout_sec,
    )
    try:
        rows = await connection.fetch(
            """
            SELECT da.canonical_key, da.authority_id, da.record_sha256,
                   da.canonical_anchor, c.anchor AS chunk_anchor,
                   c.quarantined, c.provenance_verified,
                   s.provenance_tier, s.raw_sha256, s.raw_bytes_size
            FROM document_authorities AS da
            JOIN sources AS s ON s.id = da.source_id
            JOIN chunks AS c ON c.id = da.chunk_id
            WHERE da.canonical_key = ANY($1::text[])
            ORDER BY da.canonical_key
            """,
            keys,
        )
    finally:
        await connection.close()

    projections = {str(row["canonical_key"]): dict(row) for row in rows}
    authority_results = []
    for key in keys:
        required = required_by_key[key]
        projection = projections.get(key)
        blockers = _live_projection_blockers(required, projection)
        authority_results.append(
            {
                "registry_key": key,
                "authority_id": required["authority_id"],
                "ready": not blockers,
                "chunk_anchor": projection["chunk_anchor"] if projection else None,
                "blockers": blockers,
            }
        )

    by_key = {row["registry_key"]: row for row in authority_results}
    scenario_results = []
    for scenario in scenarios:
        authority_keys = [
            item["registry_key"] for item in scenario["active_must_cite_authorities"]
        ]
        blockers = [
            f"{key}:{blocker}"
            for key in authority_keys
            for blocker in by_key[key]["blockers"]
        ]
        scenario_results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "ready": not blockers,
                "required_authority_keys": authority_keys,
                "blockers": blockers,
            }
        )

    return {
        "ready": all(row["ready"] for row in scenario_results),
        "summary": {
            "registry_contract_ready_scenarios": len(scenario_results),
            "live_corpus_ready_scenarios": sum(row["ready"] for row in scenario_results),
            "required_authorities": len(authority_results),
            "live_corpus_ready_authorities": sum(row["ready"] for row in authority_results),
        },
        "scenarios": scenario_results,
        "authorities": authority_results,
    }


def _normalized_retrieval_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _retrieval_hit_matches_authority(
    hit: dict[str, Any],
    required: dict[str, Any],
) -> bool:
    """Match a natural-search hit to one exact registry authority provision."""
    record = load_authority_registry().by_key(str(required["registry_key"]))
    if record is None:
        return False

    hit_title = _normalized_retrieval_text(hit.get("title"))
    accepted_titles = {
        _normalized_retrieval_text(record.title),
        _normalized_retrieval_text(record.canonical_name),
        *(_normalized_retrieval_text(alias) for alias in record.aliases),
    }
    if not hit_title or not any(
        title and (title in hit_title or hit_title in title)
        for title in accepted_titles
    ):
        return False

    hit_anchor = str(hit.get("anchor") or "").split("@", 1)[0].lower()
    accepted_anchors = {
        str(record.provision.canonical_anchor).lower(),
        *(str(alias).lower() for alias in record.provision.anchor_aliases),
        *(
            str(pattern).lower()
            for pattern in required.get("required_anchor_patterns", [])
        ),
    }
    return any(
        anchor
        and re.search(rf"{re.escape(anchor)}(?:__|$)", hit_anchor) is not None
        for anchor in accepted_anchors
    )


def audit_live_natural_retrieval(
    scope: dict[str, Any],
    scope_audit: dict[str, Any],
    *,
    api_base_url: str,
    search: Callable[[str, int], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Measure raw `/search` recall without MatterPlan/source-pack injection."""
    top_k = 8
    threshold = float(scope["gate_policy"]["minimum_natural_retrieval_recall_at_8"])
    scenarios = [
        row for row in scope_audit["scenarios"] if row["registry_contract_ready"]
    ]

    if search is None:
        client = httpx.Client(base_url=api_base_url, timeout=120.0)

        def search(query: str, limit: int) -> list[dict[str, Any]]:
            response = client.get(
                "/search",
                params={
                    "q": query,
                    "top_k": limit,
                    "natural_expansion": True,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("retrieval_mode") != "natural_expansion_no_source_packs":
                raise ValueError("/search did not confirm no-source-pack retrieval mode")
            hits = payload.get("hits")
            if not isinstance(hits, list):
                raise ValueError("/search response does not contain a hits list")
            return hits
    else:
        client = None

    scenario_results = []
    try:
        for scenario in scenarios:
            hits = search(scenario["representative_query"], top_k)
            authority_results = []
            for required in scenario["active_must_cite_authorities"]:
                ranks = [
                    rank
                    for rank, hit in enumerate(hits[:top_k], start=1)
                    if _retrieval_hit_matches_authority(hit, required)
                ]
                authority_results.append(
                    {
                        "registry_key": required["registry_key"],
                        "authority_id": required["authority_id"],
                        "found": bool(ranks),
                        "best_rank": min(ranks) if ranks else None,
                    }
                )
            found = sum(row["found"] for row in authority_results)
            required_count = len(authority_results)
            recall = found / required_count if required_count else 0.0
            scenario_results.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "representative_query": scenario["representative_query"],
                    "required_authorities": required_count,
                    "found_authorities": found,
                    "recall_at_8": recall,
                    "ready": recall >= threshold,
                    "authorities": authority_results,
                    "top_8": [
                        {
                            "rank": rank,
                            "title": hit.get("title"),
                            "anchor": hit.get("anchor"),
                        }
                        for rank, hit in enumerate(hits[:top_k], start=1)
                    ],
                }
            )
    finally:
        if client is not None:
            client.close()

    total_required = sum(row["required_authorities"] for row in scenario_results)
    total_found = sum(row["found_authorities"] for row in scenario_results)
    micro_recall = total_found / total_required if total_required else 0.0
    return {
        "ready": bool(scenario_results) and all(
            row["ready"] for row in scenario_results
        ),
        "method": "GET /search natural expansion with the representative lay query; no MatterPlan or source-pack injection",
        "top_k": top_k,
        "minimum_recall_at_8": threshold,
        "summary": {
            "registry_contract_ready_scenarios": len(scenario_results),
            "natural_retrieval_ready_scenarios": sum(
                row["ready"] for row in scenario_results
            ),
            "required_authority_obligations": total_required,
            "found_authority_obligations": total_found,
            "micro_recall_at_8": micro_recall,
        },
        "scenarios": scenario_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--live-corpus", action="store_true")
    parser.add_argument("--live-retrieval", action="store_true")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8056")
    parser.add_argument("--require-launch-ready", action="store_true")
    parser.add_argument("--require-registry-ready-corpus", action="store_true")
    parser.add_argument("--require-registry-ready-retrieval", action="store_true")
    args = parser.parse_args()
    if args.require_registry_ready_corpus and not args.live_corpus:
        parser.error("--require-registry-ready-corpus requires --live-corpus")
    if args.require_registry_ready_retrieval and not args.live_retrieval:
        parser.error("--require-registry-ready-retrieval requires --live-retrieval")

    try:
        scope = load_release_scope(args.scope)
        result = audit_release_scope(scope)
        if args.live_corpus:
            result["live_registry_ready_corpus"] = asyncio.run(
                audit_live_registry_ready_corpus(result)
            )
        if args.live_retrieval:
            result["live_natural_retrieval"] = audit_live_natural_retrieval(
                scope,
                result,
                api_base_url=args.api_base_url,
            )
    except (
        OSError,
        httpx.HTTPError,
        json.JSONDecodeError,
        ScopeValidationError,
        ValueError,
    ) as exc:
        print(json.dumps({"launch_ready": False, "error": str(exc)}, indent=2))
        return 2

    rendered = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if args.require_launch_ready and not result["launch_ready"]:
        return 1
    if args.require_registry_ready_corpus and not result[
        "live_registry_ready_corpus"
    ]["ready"]:
        return 1
    if args.require_registry_ready_retrieval and not result[
        "live_natural_retrieval"
    ]["ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
