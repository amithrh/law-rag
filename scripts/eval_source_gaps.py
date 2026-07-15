#!/usr/bin/env python3
"""Shared source-gap classification helpers for legal evals.

These helpers do not decide whether an answer should pass. They only label
missing authority so reports can distinguish an honest state/local-law gap from
a retriever miss, a retrieved-but-not-cited answer, or an unclassified hole.
"""
from __future__ import annotations

import re
from typing import Any


def expected_authority_gap_kind(row: dict[str, Any], prompt: dict[str, Any] | None = None) -> str | None:
    """Classify an expected-authority miss for reporting.

    Returns ``None`` when there is no expected-authority miss.
    """
    if row.get("expected_act_hit") is not False and row.get("expected_act_cited_hit") is not False:
        return None
    if row.get("expected_act_hit") is True and row.get("expected_act_cited_hit") is False:
        return "retrieved_not_cited"

    prompt = prompt or {}
    blob = _blob(
        row.get("query"),
        row.get("answer_text"),
        row.get("expected_act_hint"),
        prompt.get("expected_act_hint"),
        row.get("route_category"),
    )
    if _is_state_or_local_source(blob):
        return "state_or_local_authority_gap"
    if _is_constitutional_source(blob):
        return "constitutional_authority_gap"
    if _is_supporting_records_source(blob):
        return "supporting_records_gap"
    if _is_national_statute_source(blob):
        return "national_statute_retrieval_gap"
    return "unclassified_expected_authority_gap"


def route_required_source_gap_classifications(row: dict[str, Any]) -> list[dict[str, str]]:
    """Classify each route-required source missing from a flattened eval row."""
    existing = row.get("route_required_source_gap_classifications")
    if isinstance(existing, list) and existing:
        normalized: list[dict[str, str]] = []
        for item in existing:
            if not isinstance(item, dict):
                continue
            source = str(item.get("required_source") or "").strip()
            kind = str(item.get("kind") or "").strip()
            if source and kind:
                normalized.append({"required_source": source, "kind": kind})
        if normalized:
            return normalized

    classifications: list[dict[str, str]] = []
    for required_source in row.get("route_required_sources_missing") or []:
        source = str(required_source or "").strip()
        if not source:
            continue
        classifications.append({
            "required_source": source,
            "kind": route_required_source_gap_kind(row, source),
        })
    return classifications


def route_required_source_gap_kind(row: dict[str, Any], required_source: str) -> str:
    source_blob = _blob(required_source)
    if "only after" in source_blob or "where relevant" in source_blob or "based on incident date" in source_blob:
        if _is_criminal_source(source_blob):
            return "national_criminal_source_gap"
        if _is_state_or_local_source(source_blob):
            return "state_or_local_authority_gap"
        return "conditional_authority_gap"
    if _is_constitutional_source(source_blob):
        return "constitutional_authority_gap"
    if _is_supporting_records_source(source_blob):
        return "supporting_records_gap"
    if _is_state_or_local_source(source_blob):
        return "state_or_local_authority_gap"
    if _is_tax_source(source_blob):
        return "national_tax_source_gap"
    if _is_labor_source(source_blob):
        return "national_labor_source_gap"
    if _is_property_source(source_blob):
        return "national_property_source_gap"
    if _is_transport_source(source_blob):
        return "national_transport_source_gap"
    if _is_criminal_source(source_blob):
        return "national_criminal_source_gap"
    if _is_national_statute_source(source_blob):
        return "national_statute_retrieval_gap"

    blob = _blob(
        required_source,
        row.get("query"),
        row.get("answer_text"),
        row.get("route_category"),
        row.get("expected_act_hint"),
    )
    if "only after" in blob or "where relevant" in blob or "based on incident date" in blob:
        if _is_criminal_source(blob):
            return "national_criminal_source_gap"
        if _is_state_or_local_source(blob):
            return "state_or_local_authority_gap"
        return "conditional_authority_gap"
    if _is_constitutional_source(blob):
        return "constitutional_authority_gap"
    if _is_supporting_records_source(blob):
        return "supporting_records_gap"
    if _is_state_or_local_source(blob):
        return "state_or_local_authority_gap"
    if _is_tax_source(blob):
        return "national_tax_source_gap"
    if _is_labor_source(blob):
        return "national_labor_source_gap"
    if _is_property_source(blob):
        return "national_property_source_gap"
    if _is_transport_source(blob):
        return "national_transport_source_gap"
    if _is_criminal_source(blob):
        return "national_criminal_source_gap"
    if _is_national_statute_source(blob):
        return "national_statute_retrieval_gap"
    return "unclassified_route_source_gap"


def has_unclassified_route_source_gap(row: dict[str, Any]) -> bool:
    return any(
        str(item.get("kind") or "").startswith("unclassified_")
        for item in route_required_source_gap_classifications(row)
        if isinstance(item, dict)
    )


def _blob(*parts: Any) -> str:
    text_parts: list[str] = []
    for part in parts:
        if isinstance(part, list):
            text_parts.extend(str(item) for item in part)
        elif part is not None:
            text_parts.append(str(part))
    return re.sub(r"\s+", " ", " ".join(text_parts).lower())


def _has_any(blob: str, terms: tuple[str, ...]) -> bool:
    return any(term in blob for term in terms)


def _is_state_or_local_source(blob: str) -> bool:
    return _has_any(blob, (
        "state ", "state-", "state/", "local", "municipal", "municipality",
        "municipal corporation", "panchayat", "gram sabha", "shops and establishments",
        "shop or trade", "trade-licence", "trade license", "rent-control",
        "tenancy law", "school board", "education-record", "education rules",
        "caste-certificate", "land revenue", "mutation", "forest/revenue",
        "scheduled area", "scheduled areas", "tribal-land", "cattle preservation",
        "animal preservation", "cow slaughter", "bhang-rule", "excise/local",
        "witch-hunting", "witch-branding", "tonahi", "tonhi", "daain", "dayan",
        "scheme rules", "state pension", "state welfare", "ration scheme",
        "icds", "anganwadi", "asha", "nhm", "prison rules", "prison manual",
        "state rera", "traffic police e-challan procedure", "motor vehicle rules",
    ))


def _is_constitutional_source(blob: str) -> bool:
    return _has_any(blob, (
        "constitution", "article 14", "article 17", "article 19", "article 21",
        "article 22", "article 32", "article 226", "constitutional",
    ))


def _is_supporting_records_source(blob: str) -> bool:
    return bool(re.search(r"\brti\b", blob)) or _has_any(blob, (
        "right to information", "written status", "status and reasons",
        "records request", "first appeal", "written cancellation/status",
        "deficiency note", "reason in writing", "reasons and first appeal",
    ))


def _is_tax_source(blob: str) -> bool:
    return _has_any(blob, (
        "gst", "customs act", "customs", "income tax", "tds", "icegate",
        "valuation", "classification", "svb",
    ))


def _is_labor_source(blob: str) -> bool:
    return _has_any(blob, (
        "payment of wages", "code on wages", "minimum wage", "minimum wages",
        "industrial disputes", "epf", "employees provident", "employees' provident",
        "employees state insurance", "esi", "bocw", "factories act",
    ))


def _is_property_source(blob: str) -> bool:
    return _has_any(blob, (
        "registration act", "transfer of property", "limitation act",
        "specific relief", "hindu succession", "succession act",
    ))


def _is_transport_source(blob: str) -> bool:
    return _has_any(blob, (
        "motor vehicles act", "motor vehicle", "mv act", "rto",
        "challan", "permit", "driving licence", "driving license",
    ))


def _is_criminal_source(blob: str) -> bool:
    return _has_any(blob, (
        "bns", "bnss", "ipc", "crpc", "offence provisions", "bail provisions",
        "criminal procedure", "bharatiya nyaya sanhita",
        "bharatiya nagarik suraksha sanhita",
    ))


def _is_national_statute_source(blob: str) -> bool:
    return " act" in blob or " code" in blob or _has_any(blob, (
        "ombudsman", "aadhaar", "consumer protection", "pocso", "posh",
        "domestic violence", "pwdva", "forest rights", "rfctlarr",
    ))
