"""Legal-HyDE-lite retrieval briefs.

Classic HyDE asks an LLM to write a hypothetical answer/document, then embeds
that generated text for retrieval. For legal QA that is too risky as a default:
the fake document can invent a legal frame. This module instead builds a short
source-aware search brief from the router, required-source metadata, and source
packs. The brief is used only as another retrieval query; final answers remain
grounded in retrieved corpus passages.
"""
from __future__ import annotations

import re
from typing import Literal

from apps.api.matter_router import MatterRoute, route_matter
from apps.api.source_packs import source_packs_for_route


Mode = Literal["off", "fallback", "always"]


_GENERIC_CATEGORIES = {"off_topic"}
_GENERIC_SOURCE_PHRASES = {
    "relevant court/forum after issue classification",
    "district legal services authority",
    "state/city",
    "dates",
    "documents",
    "what result you want",
}
_MIN_ROUTE_CONFIDENCE = 0.55
_FALLBACK_EXCLUDED_CATEGORIES = {"court_procedure"}


def maybe_append_legal_hyde_brief(
    query: str,
    variants: list[str],
    *,
    mode: Mode,
    max_chars: int,
    route: MatterRoute | None = None,
) -> list[str]:
    """Append one retrieval-only legal brief according to the configured mode."""
    if mode == "off":
        return variants
    if mode == "fallback" and route is not None and route.category in _FALLBACK_EXCLUDED_CATEGORIES:
        return variants
    if mode == "fallback" and len([v for v in variants[1:] if v.strip()]) > 0:
        return variants

    brief = build_legal_hyde_brief(query, route=route, max_chars=max_chars)
    if not brief:
        return variants

    seen = {_norm(v) for v in variants}
    if _norm(brief) in seen:
        return variants
    return [*variants, brief]


def build_legal_hyde_brief(
    query: str,
    *,
    route: MatterRoute | None = None,
    max_chars: int = 360,
) -> str | None:
    """Build a compact legal-search brief, not a user-facing answer."""
    q = (query or "").strip()
    if not q:
        return None
    route = route or route_matter(q)
    if route.category in _GENERIC_CATEGORIES or route.confidence < _MIN_ROUTE_CONFIDENCE:
        return None

    sources = _clean_terms(route.required_sources, limit=3)
    forums = _clean_terms(route.forums, limit=2)
    missing = _clean_terms(route.missing_facts, limit=3)

    try:
        packs = source_packs_for_route(route, q)[:3]
    except Exception:
        packs = []
    pack_terms = _clean_terms(
        [
            getattr(pack, "search_query", "") or " ".join(getattr(pack, "title_patterns", ()) or ())
            for pack in packs
        ],
        limit=3,
    )

    parts = [
        f"matter {route.label or route.category}",
        _join_part("sources", sources or pack_terms),
        _join_part("forums", forums),
        _join_part("facts", missing),
        f"user words {q}",
    ]
    brief = "; ".join(part for part in parts if part)
    brief = re.sub(r"\s+", " ", brief).strip()
    if len(brief) <= max_chars:
        return brief
    return brief[: max(80, max_chars)].rsplit(" ", 1)[0].strip()


def _join_part(label: str, values: list[str]) -> str:
    if not values:
        return ""
    return f"{label} " + " | ".join(values)


def _clean_terms(values: list[str] | tuple[str, ...], *, limit: int) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = re.sub(r"\s+", " ", str(value)).strip(" .;")
        if not text:
            continue
        lowered = text.lower()
        if lowered in _GENERIC_SOURCE_PHRASES:
            continue
        if lowered not in {item.lower() for item in out}:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


__all__ = ["build_legal_hyde_brief", "maybe_append_legal_hyde_brief"]
