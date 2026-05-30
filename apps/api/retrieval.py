"""Multi-head hybrid retrieval: BGE-M3 dense + BGE-M3 sparse + Postgres BM25.

Per docs/RETRIEVAL_AUDIT.md (recall@20 = 53%), the production setup —
dense ANN + Postgres `english` tsvector BM25, blended 70/30 — fails on
exact-citation / statute-section queries where the gold passage's text
doesn't share lexical overlap with the user's phrasing (e.g. "punishment
for theft" not finding "Section 379 — Theft"). The architecture-research
roadmap pinpoints learned-sparse retrieval (BGE-M3 lexical-weights head)
as the #1 ROI fix because (a) it's exactly the gap dense embeddings
have and (b) BGE-M3 already emits it from the same forward pass we pay
for today.

Pipeline (`hybrid_mode='dense_sparse_bm25'`):

  Stage 1 — three retrievers in parallel against `chunks`:
    1a. Dense    (HNSW on `embedding`,         top `dense_top_k`)
    1b. Sparse   (JSONB dot product on
                  `embedding_sparse`,           top `sparse_top_k`)
    1c. BM25     (tsvector match on `text_tsv`, top `bm25_top_k`)
    1d. Fielded BM25 over bare Acts only (title/statute/doc-id/anchor/body),
        top `fielded_bm25_top_k`

  Stage 2 — RRF fusion (Cormack et al., k=60):
    For each chunk, its fused score is
        Σ over heads h:  1 / (rrf_k + rank_h)
    where rank_h is the 1-based rank from head h (or absent if the
    chunk wasn't surfaced by that head).

  Stage 3 — optional cross-encoder rerank (bge-reranker-v2-m3) over
    the top `rerank_input_k` fused candidates, keep top `top_k`.

  Stage 4 — LLM consumes the final top K (K=8 by default).

The legacy mode `hybrid_mode='dense_bm25'` keeps the 70/30 weighted-sum
behavior for A/B comparison and for environments where the sparse
column hasn't been backfilled.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date

import asyncpg

from apps.api.config import get_settings
from apps.api.embeddings import embedding_to_halfvec_literal, get_embedder
from apps.api.matter_router import route_matter
from apps.api.source_packs import SourcePack, source_packs_for_route

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    anchor: str
    text: str
    source_type: str
    subject_area: str | None
    as_at: date | None
    paragraph_no: int | None
    title: str
    citation: str | None
    court: str | None
    statute_short: str | None
    dense_score: float = 0.0
    bm25_score: float = 0.0
    sparse_score: float = 0.0
    rerank_score: float | None = None
    # RRF fused score across whichever heads contributed. None if not
    # produced by the RRF path (e.g. legacy `dense_bm25` mode).
    rrf_score: float | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def combined_score(self) -> float:
        """Legacy pre-rerank ordering for `hybrid_mode='dense_bm25'`.

        For `dense_sparse_bm25` use `rrf_score` instead — RRF is the
        correct fusion because dense / sparse / BM25 scores live on
        non-commensurate scales (cosine ≤ 1, BM25 ts_rank unbounded,
        sparse dot-product depends on token frequency).
        """
        return 0.7 * self.dense_score + 0.3 * self.bm25_score


# ---------------------------------------------------------------------------
# RRF helper — exported for tests.
# ---------------------------------------------------------------------------


def rrf_fuse(
    rankings: list[list[int]],
    *,
    k: int = 60,
) -> dict[int, float]:
    """Reciprocal-Rank-Fusion over multiple ranked id lists.

    Each input list is an ordered ranking (rank 1 first). Returns a dict
    mapping id → fused RRF score. Per Cormack et al. (2009) the score is

        score(d) = Σ_h  1 / (k + rank_h(d))

    where the sum is over heads that surfaced `d`. Ranks are 1-based;
    a doc not in a head's ranking contributes 0 for that head.

    `k=60` is the canonical default — it dampens rank-1 dominance enough
    that two heads agreeing weakly (e.g. rank 3 and rank 5) beats one
    head ranking the doc 1st alone. Lower k privileges the top of each
    list; higher k flattens contributions.
    """
    out: dict[int, float] = {}
    for ranking in rankings:
        for rank_idx, chunk_id in enumerate(ranking, start=1):
            out[chunk_id] = out.get(chunk_id, 0.0) + 1.0 / (k + rank_idx)
    return out


# ---------------------------------------------------------------------------
# Sparse retrieval — JSONB dot product
# ---------------------------------------------------------------------------


async def sparse_retrieve(
    pool_or_conn,
    query_sparse: dict[str, float],
    *,
    top_k: int,
    where_clause: str,
    where_params: list,
) -> list:
    """Run sparse retrieval against the `embedding_sparse` JSONB column.

    Scoring: for each chunk whose sparse vector shares ≥1 token with the
    query, compute `Σ_token  query[token] * chunk[token]` (the standard
    SPLADE-style dot product over overlapping tokens). Top-K by score.

    JSONB shape (per `embedding_sparse` column): `{token_id_str: weight}`.

    SQL strategy:
      1. Materialize the query's sparse vector as a small JSONB literal.
      2. For each candidate chunk in the filtered set, unpack the query
         JSONB with `jsonb_each_text`, look up the matching key in the
         chunk's JSONB with `embedding_sparse->>key`, multiply, sum.
      3. The GIN index `idx_chunks_sparse_gin` (jsonb_path_ops) gives us
         a cheap "JSONB ?| array[query keys]" prefilter so we don't scan
         every row.

    The function takes an open connection rather than a pool because the
    caller already holds the pool acquisition (we want all three head
    queries in one acquire) and the dense path needs `SET LOCAL` state.
    """
    if not query_sparse:
        # No tokens in the query (very short / OOV input). Return nothing
        # rather than scanning all chunks for a zero-product sum.
        return []

    query_jsonb = json.dumps(query_sparse, separators=(",", ":"))
    query_keys = list(query_sparse.keys())

    # Param layout:
    #   $1..len(where_params) → existing filter params (subject_area, etc.)
    #   $N+1                  → query_jsonb (JSONB literal)
    #   $N+2                  → query_keys  (text[] for the GIN prefilter)
    #   $N+3                  → top_k
    base = len(where_params)
    params = where_params + [query_jsonb, query_keys, top_k]

    # The CTE `q` materializes the query JSONB once. The main SELECT
    # joins each chunk's sparse vector against q via `jsonb_each_text`
    # and sums the multiplied weights. The GIN-backed `?|` operator
    # restricts the candidate set to chunks that share at least one
    # token with the query.
    sql = f"""
        WITH q AS (SELECT ${base+1}::jsonb AS qs)
        SELECT c.id, c.document_id, c.anchor, c.text, c.source_type,
               c.subject_area, c.as_at, c.paragraph_no, c.metadata,
               d.title, d.citation, d.court, d.statute_short,
               (
                   SELECT COALESCE(SUM(
                       (kv.value)::float8
                       * (c.embedding_sparse->>kv.key)::float8
                   ), 0.0)
                   FROM jsonb_each_text((SELECT qs FROM q)) AS kv
                   WHERE c.embedding_sparse ? kv.key
               ) AS sparse_score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {where_clause}
          AND c.embedding_sparse IS NOT NULL
          AND c.embedding_sparse ?| ${base+2}::text[]
        ORDER BY sparse_score DESC
        LIMIT ${base+3}
    """
    return await pool_or_conn.fetch(sql, *params)


def _bm25_retrieve_sql(
    *,
    where_clause: str,
    where_param_count: int,
    fielded: bool,
) -> str:
    query_param = where_param_count + 1
    limit_param = where_param_count + 2
    common_select = """
               c.id, c.document_id, c.anchor, c.text, c.source_type,
               c.subject_area, c.as_at, c.paragraph_no, c.metadata,
               d.title, d.citation, d.court, d.statute_short,
    """

    if not fielded:
        return f"""SELECT {common_select}
                       ts_rank(c.text_tsv, plainto_tsquery('english', ${query_param})) AS bm25_score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE {where_clause}
                  AND c.text_tsv @@ plainto_tsquery('english', ${query_param})
                ORDER BY bm25_score DESC
                LIMIT ${limit_param}"""

    weighted_vector = """
                   setweight(to_tsvector('english', coalesce(d.title, '')), 'A') ||
                   setweight(to_tsvector('english', coalesce(d.statute_short, '')), 'A') ||
                   setweight(to_tsvector('english', coalesce(d.doc_id, '')), 'B') ||
                   setweight(to_tsvector('english', c.anchor), 'A') ||
                   setweight(coalesce(c.text_tsv, ''::tsvector), 'D')
    """
    section_regex = r"(?:section|sec\.?|s\.?)\s*(\d{1,4}[a-z]?)"
    return f"""WITH q AS (
                    SELECT
                        plainto_tsquery('english', ${query_param}) AS full_tsq,
                        websearch_to_tsquery(
                            'english',
                            regexp_replace(trim(${query_param}), '\\s+', ' OR ', 'g')
                        ) AS any_tsq,
                        ARRAY(
                            SELECT lower(m[1])
                            FROM regexp_matches(${query_param}, '{section_regex}', 'gi') AS m
                        ) AS target_secs
                )
                SELECT {common_select}
                       (
                           ts_rank_cd(({weighted_vector}), q.full_tsq)
                           + 0.20 * ts_rank_cd(({weighted_vector}), q.any_tsq)
                           + CASE WHEN EXISTS (
                               SELECT 1
                               FROM unnest(q.target_secs) AS sec(sec_no)
                               WHERE lower(c.anchor) LIKE '%/sec-' || sec.sec_no || '%'
                           ) THEN 4.0 ELSE 0.0 END
                       ) AS bm25_score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                CROSS JOIN q
                WHERE {where_clause}
                  AND c.anchor NOT ILIKE '%#header%'
                  AND (
                    ({weighted_vector}) @@ q.full_tsq
                    OR c.text_tsv @@ q.any_tsq
                    OR to_tsvector('english', c.anchor) @@ q.any_tsq
                    OR to_tsvector('english', coalesce(d.title, '')) @@ q.any_tsq
                    OR to_tsvector('english', coalesce(d.statute_short, '')) @@ q.any_tsq
                    OR to_tsvector('english', coalesce(d.doc_id, '')) @@ q.any_tsq
                  )
                ORDER BY bm25_score DESC
                LIMIT ${limit_param}"""


def _hydrate_row(r) -> RetrievedChunk:
    metadata = r["metadata"] if isinstance(r["metadata"], dict) else {}
    return RetrievedChunk(
        chunk_id=r["id"],
        document_id=r["document_id"],
        anchor=r["anchor"],
        text=r["text"],
        source_type=r["source_type"],
        subject_area=r["subject_area"],
        as_at=r["as_at"],
        paragraph_no=r["paragraph_no"],
        title=r["title"],
        citation=r["citation"],
        court=r["court"],
        statute_short=r["statute_short"],
        metadata=dict(metadata),
    )


def _focus_required_source_pack_text(chunk: RetrievedChunk, pack: SourcePack) -> None:
    """Trim packed multi-section source chunks to the section the pack needs."""
    if pack.id == "jj_2015_age_claim_court":
        match = re.search(
            r"\(2\)\s+In case a person alleged to have committed an offence claims.*?(?=\n\s*Provided that the person shall|while the person’s claim|while the person's claim|$)",
            chunk.text or "",
            flags=re.DOTALL | re.IGNORECASE,
        )
        if match:
            chunk.text = (
                "Juvenile Justice (Care and Protection of Children) Act 2015, Section 9\n\n"
                + match.group(0).strip()
            )
            chunk.anchor = "jj-2015/sec-9"
            chunk.metadata["section_no"] = "9"
        return
    if pack.id == "jj_2015_age_documents":
        text = chunk.text or ""
        match = re.search(
            r"(?:94\.\s+\(1\).*?reasonable grounds for doubt regarding\s+)?whether the person brought before it is a child.*?(?=\n\s*95\.\s+\(1\)|$)",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r"94\.\s+\(1\).*?(?=\n\s*95\.\s+\(1\)|$)",
                text,
                flags=re.DOTALL | re.IGNORECASE,
            )
        if match:
            chunk.text = (
                "Juvenile Justice (Care and Protection of Children) Act 2015, Section 94\n\n"
                + match.group(0).strip()
            )
            chunk.anchor = "jj-2015/sec-94"
            chunk.metadata["section_no"] = "94"
        return
    if pack.id == "constitution_article_46":
        match = re.search(
            r"46\.\s+Promotion of educational and economic interests.*?(?=\n\s*\d{1,3}\.\s+|$)",
            chunk.text or "",
            flags=re.DOTALL,
        )
        if match:
            chunk.text = "Constitution of India, Article 46\n\n" + match.group(0).strip()
            chunk.anchor = "constitution-india/sec-46"
            chunk.metadata["section_no"] = "46"
        return
    if pack.id == "constitution_article_47":
        match = re.search(
            r"47\.\s+Duty of the State.*?(?=\n\s*\d{1,3}\.\s+|$)",
            chunk.text or "",
            flags=re.DOTALL,
        )
        if match:
            chunk.text = "Constitution of India, Article 47\n\n" + match.group(0).strip()
        return
    if pack.id != "ndps_1985" or "section 36a" not in pack.search_query.lower():
        if pack.id == "jj_2015" and "adoption" in pack.search_query.lower():
            text = chunk.text or ""
            match = re.search(r"\b(56|57|58|59|62|63)\.\s+.*", text, flags=re.DOTALL)
            if match:
                sec_no = match.group(1)
                chunk.text = (
                    "Juvenile Justice (Care and Protection of Children) Act 2015, "
                    f"Section {sec_no}\n\n"
                    + match.group(0).strip()
                )
                chunk.anchor = f"jj-2015/sec-{sec_no}"
                chunk.metadata["section_no"] = sec_no
        return
    text = chunk.text or ""
    match = re.search(r"36A\.\s+Offences triable by Special Courts.*", text, flags=re.DOTALL)
    if not match and "one hundred and eighty days" in text.lower():
        match = re.search(r"\(4\)\s+In respect of persons accused.*?(?=\n\s*\(5\)|$)", text, flags=re.DOTALL)
    if match:
        chunk.text = (
            "Narcotic Drugs and Psychotropic Substances Act 1985, Section 36A\n\n"
            + match.group(0).strip()
        )
        chunk.anchor = "ndps-1985/sec-36A"
        chunk.metadata["section_no"] = "36A"


_BIHAR_TERMS = (
    "bihar", "patna", "gaya", "muzaffarpur", "bhagalpur",
    "darbhanga", "purnea", "samastipur", "siwan", "chhapra",
    "motihari", "nalanda", "begusarai", "madhubani",
)


def _query_allows_state_specific_source(query: str, chunk: RetrievedChunk) -> bool:
    title = (chunk.title or "").lower()
    q = query.lower()
    if "bihar mukhyamantri kanya vivah" in title:
        return any(term in q for term in _BIHAR_TERMS)
    if (
        any(term in q for term in ("prohibition law", "excise act", "liquor", "caught me drinking", "drinking village", "sharab"))
        and ("state of bihar" in title or "bihar prohibition" in title)
    ):
        return _query_has_bihar_excise_jurisdiction(q)
    return True


def _query_has_bihar_excise_jurisdiction(q: str) -> bool:
    if any(term in q for term in (
        "bihar colony", "bihar border", "near bihar border", "bihar bhawan",
        "from bihar",
    )):
        return False
    if any(term in q for term in ("delhi", "uttar pradesh", " up ", " u.p.", "noida", "lucknow")):
        return False
    return any(term in q for term in (
        "bihar prohibition", "bihar excise", "in bihar", "at bihar",
        "under bihar", "bihar police", "bihar thana", "patna", "gaya",
        "muzaffarpur", "bhagalpur", "darbhanga", "purnea", "samastipur",
        "siwan", "chhapra", "motihari", "nalanda", "begusarai",
        "madhubani",
    ))


def _filter_query_ineligible_sources(
    query: str,
    chunks: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    return [c for c in chunks if _query_allows_state_specific_source(query, c)]


def _preserve_required_source_packs(
    candidates: list[RetrievedChunk],
    pack_ids: list[str],
    *,
    limit: int,
    preferred_top_n: int | None = None,
) -> list[RetrievedChunk]:
    """Keep at least one exact required-source chunk per fired pack.

    Rerankers often prefer fact-heavy judgments over the bare Act section,
    even when the router knows that Act is mandatory authority. This helper
    preserves the highest-scoring exact-source chunk for each fired pack
    inside the bounded top-K. When configured, it also moves those exact
    sources into the first few contexts so the answer sees the operative law
    before factually similar judgments.
    """
    if limit <= 0 or not candidates or not pack_ids:
        return candidates[:limit]

    selected = candidates[:limit]
    selected_chunk_ids = {c.chunk_id for c in selected}
    present_pack_ids = {
        str(pack_id)
        for c in selected
        if (pack_id := c.metadata.get("_required_source_pack"))
    }

    for pack_id in pack_ids:
        if pack_id in present_pack_ids:
            continue
        best = next(
            (
                c
                for c in candidates[limit:]
                if c.metadata.get("_required_source_pack") == pack_id
                and c.chunk_id not in selected_chunk_ids
            ),
            None,
        )
        if best is None:
            continue
        if len(selected) < limit:
            selected.append(best)
        else:
            replace_idx = next(
                (
                    idx
                    for idx in range(len(selected) - 1, -1, -1)
                    if not selected[idx].metadata.get("_required_source_pack")
                ),
                len(selected) - 1,
            )
            selected_chunk_ids.discard(selected[replace_idx].chunk_id)
            selected[replace_idx] = best
        selected_chunk_ids.add(best.chunk_id)
        present_pack_ids.add(pack_id)

    selected.sort(
        key=lambda c: c.rerank_score if c.rerank_score is not None else -1e9,
        reverse=True,
    )
    if preferred_top_n is not None and preferred_top_n > 0:
        _promote_required_source_packs(
            selected,
            pack_ids,
            preferred_top_n=min(preferred_top_n, limit),
        )
    return selected[:limit]


def _promote_required_source_packs(
    selected: list[RetrievedChunk],
    pack_ids: list[str],
    *,
    preferred_top_n: int,
) -> None:
    """Move required source packs into the visible context window.

    This deliberately changes ordering, not score. The score remains useful
    telemetry from the reranker, while answer generation sees the operative
    Act before a long run of factually similar case paragraphs.
    """
    if preferred_top_n <= 0:
        return

    present_pack_ids = [
        pack_id
        for pack_id in pack_ids
        if any(c.metadata.get("_required_source_pack") == pack_id for c in selected)
    ]
    if not present_pack_ids:
        return

    window_end = min(preferred_top_n, len(selected))
    insert_at = max(0, window_end - len(present_pack_ids))
    for pack_id in present_pack_ids:
        idx = next(
            (
                i
                for i, c in enumerate(selected)
                if c.metadata.get("_required_source_pack") == pack_id
            ),
            None,
        )
        if idx is None:
            continue
        if idx < window_end:
            continue
        chunk = selected.pop(idx)
        selected.insert(min(insert_at, len(selected)), chunk)
        insert_at += 1


_STATUTE_FIRST_CATEGORIES = {
    "cheque_bounce",
    "consumer",
    "criminal_defence_bail",
    "criminal_general",
    "cyber_fraud_or_harassment",
    "employment_wages",
    "family_domestic",
    "ibc_nclt",
    "labour_exploitation_discrimination",
    "police_fir",
    "reproductive_rights_mtp",
    "rti",
    "senior_citizen",
    "sexual_offence_survivor",
    "tribal_caste_atrocity",
    "workplace_injury_compensation",
    "workplace_sexual_harassment",
}

_CASE_WEIGHTED_CATEGORIES = {
    "custody_compensation",
    "court_procedure",
    "land_revenue_records",
    "property_tenancy",
    "succession_inheritance",
}


def _apply_authority_rerank_boosts(
    candidates: list[RetrievedChunk],
    *,
    route_category: str,
    source_quality_boost: float,
    source_cluster_boost: float,
) -> None:
    """Apply TurboVec-style source quality and source-level corroboration.

    The cross-encoder scores chunk/query fit. This layer answers a different
    product question: "given similarly plausible chunks, which legal source
    should be trusted more?" It is intentionally bounded by headroom toward
    1.0 so it nudges ranking without manufacturing high confidence.
    """
    if not candidates:
        return

    cluster_scores = _source_cluster_scores(candidates, route_category=route_category)
    for chunk in candidates:
        if chunk.rerank_score is None:
            continue
        score = chunk.rerank_score
        quality = _source_quality_score(chunk, route_category=route_category)
        cluster = cluster_scores.get(chunk.document_id, 0.0)
        total_boost = max(0.0, source_quality_boost) * quality
        total_boost += max(0.0, source_cluster_boost) * cluster
        if total_boost <= 0.0:
            continue
        chunk.metadata["_source_quality_score"] = round(quality, 4)
        chunk.metadata["_source_cluster_score"] = round(cluster, 4)
        chunk.rerank_score = min(1.0, score + total_boost * (1.0 - score))


def _source_quality_score(chunk: RetrievedChunk, *, route_category: str) -> float:
    if chunk.metadata.get("_required_source_pack"):
        return 1.0

    source_type = (chunk.source_type or "").lower()
    base = {
        "bare_act": 0.92,
        "sc_judgment": 0.72,
        "hc_judgment": 0.58,
        "tribunal_order": 0.50,
    }.get(source_type, 0.42)

    if route_category in _STATUTE_FIRST_CATEGORIES:
        if source_type == "bare_act":
            base += 0.08
        elif source_type.endswith("judgment"):
            base -= 0.04
    elif route_category in _CASE_WEIGHTED_CATEGORIES:
        if source_type == "sc_judgment":
            base += 0.06
        elif source_type == "hc_judgment":
            base += 0.03

    title_blob = f"{chunk.title} {chunk.statute_short or ''}".lower()
    if source_type == "bare_act" and any(marker in title_blob for marker in (" act", " code", "sanhita", "adhiniyam")):
        base += 0.03

    return max(0.0, min(1.0, base))


def _source_cluster_scores(
    candidates: list[RetrievedChunk],
    *,
    route_category: str,
) -> dict[int, float]:
    by_document: dict[int, list[RetrievedChunk]] = {}
    for chunk in candidates:
        if chunk.rerank_score is None:
            continue
        by_document.setdefault(chunk.document_id, []).append(chunk)

    out: dict[int, float] = {}
    for document_id, chunks in by_document.items():
        ranked_scores = sorted(
            (max(0.0, c.rerank_score or 0.0) for c in chunks),
            reverse=True,
        )
        if not ranked_scores:
            continue
        top = ranked_scores[0]
        second = ranked_scores[1] if len(ranked_scores) > 1 else 0.0
        third = ranked_scores[2] if len(ranked_scores) > 2 else 0.0
        corroboration = min(1.0, max(0, len(chunks) - 1) / 3.0)
        quality = max(_source_quality_score(c, route_category=route_category) for c in chunks)
        out[document_id] = min(
            1.0,
            0.58 * top + 0.17 * second + 0.08 * third + 0.09 * corroboration + 0.08 * quality,
        )
    return out


_SEC_ANCHOR_RE = re.compile(r"(?:^|/)sec-(\d{1,4})([A-Z]{0,2})(?:-([A-Z]))?", re.IGNORECASE)


def _section_numbers_from_anchor_patterns(anchor_patterns: tuple[str, ...]) -> list[str]:
    """Extract exact legal section numbers from source-pack anchor hints.

    Required-source packs are meant to fetch section 3, not section 30 just
    because both contain the string `/sec-3`. Prefer chunk metadata for exact
    matching and keep a boundary-regex fallback for older chunks.
    """
    out: list[str] = []
    seen: set[str] = set()
    for pattern in anchor_patterns:
        match = _SEC_ANCHOR_RE.search(pattern)
        if not match:
            continue
        num = match.group(1)
        inline_suffix = (match.group(2) or "").upper()
        hyphen_suffix = (match.group(3) or "").upper()
        candidates = [f"{num}{inline_suffix}"]
        # Some legacy hints used normalized anchors such as `/sec-13-b`
        # for legal section 13B. Treat that as 13B plus a literal anchor
        # regex, not as section 13; otherwise `/sec-71-a` also matches
        # unrelated `/sec-71__2` split chunks.
        if hyphen_suffix:
            candidates = [f"{num}{hyphen_suffix}"]
        for sec_no in candidates:
            if sec_no and sec_no not in seen:
                seen.add(sec_no)
                out.append(sec_no)
    return out


def _anchor_boundary_regexes(section_nos: list[str]) -> list[str]:
    return [rf"(^|/)sec-{re.escape(sec_no)}(@|-|__|$)" for sec_no in section_nos]


def _anchor_regexes_from_patterns(anchor_patterns: tuple[str, ...]) -> list[str]:
    section_regexes = _anchor_boundary_regexes(_section_numbers_from_anchor_patterns(anchor_patterns))
    literal_regexes = [
        rf"(^|[#/]){re.escape(pattern.removeprefix('/').removesuffix('@'))}($|@|__)"
        for pattern in anchor_patterns
        if pattern and pattern.removeprefix("/").removesuffix("@")
    ]
    return [*section_regexes, *literal_regexes]


def _source_pack_anchor_order(
    chunk: RetrievedChunk,
    *,
    section_nos: list[str],
    anchor_regexes: list[str],
) -> int:
    section_no = str(chunk.metadata.get("section_no") or "").upper()
    section_order = {sec_no.upper(): idx for idx, sec_no in enumerate(section_nos)}
    if section_no in section_order:
        return section_order[section_no]
    anchor = chunk.anchor or ""
    for idx, anchor_regex in enumerate(anchor_regexes):
        if re.search(anchor_regex, anchor, flags=re.IGNORECASE):
            return idx
    return 9999


def _diversify_source_pack_chunks(
    chunks: list[RetrievedChunk],
    *,
    section_nos: list[str],
    anchor_regexes: list[str],
    limit: int,
) -> list[RetrievedChunk]:
    """Keep one strong chunk per requested anchor before duplicates.

    Some official PDFs split a single legal section into many chunks. A
    straight LIMIT can therefore return four Section 18 chunks and miss the
    requested inspector/sampling sections entirely. Round-robin by anchor
    order keeps source packs representative while preserving BM25 ordering
    inside each section.
    """
    if limit <= 0 or len(chunks) <= limit:
        return chunks

    ranked = sorted(
        chunks,
        key=lambda c: (
            -float(c.bm25_score or 0.0),
            c.paragraph_no is None,
            c.paragraph_no if c.paragraph_no is not None else 999999,
            c.chunk_id,
        ),
    )
    groups: dict[int, list[RetrievedChunk]] = {}
    for chunk in ranked:
        order = _source_pack_anchor_order(
            chunk,
            section_nos=section_nos,
            anchor_regexes=anchor_regexes,
        )
        groups.setdefault(order, []).append(chunk)

    diversified: list[RetrievedChunk] = []
    orders = sorted(groups)
    max_group_len = max(len(group) for group in groups.values())
    for round_idx in range(max_group_len):
        for order in orders:
            group = groups[order]
            if round_idx >= len(group):
                continue
            diversified.append(group[round_idx])
            if len(diversified) >= limit:
                return diversified
    return diversified


async def _fetch_source_pack_candidates(
    pool: asyncpg.Pool,
    query: str,
    *,
    packs: list[SourcePack],
    limit_per_pack: int,
) -> list[RetrievedChunk]:
    """Fetch exact-title candidates for route-required authoritative sources."""
    if not packs or limit_per_pack <= 0:
        return []

    out: list[RetrievedChunk] = []
    async with pool.acquire() as conn:
        for pack in packs:
            if pack.id == "jj_2015_age_documents":
                rows = await conn.fetch(
                    """
                    SELECT c.id, c.document_id, c.anchor, c.text, c.source_type,
                           c.subject_area, c.as_at, c.paragraph_no, c.metadata,
                           d.title, d.citation, d.court, d.statute_short,
                           ts_rank(c.text_tsv, plainto_tsquery('english', $1)) AS bm25_score,
                           1 AS anchor_priority,
                           1 AS anchor_order
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    -- These JJ chunks are quarantined only because the
                    -- chunker mis-anchored s.94 under s.30. The exact-text
                    -- branch below trims and re-anchors them before use.
                    WHERE c.source_type = 'bare_act'
                      AND d.doc_id = 'jj-2015'
                      AND (
                        c.text ILIKE '%Where, it is obvious to the Committee or the Board%'
                        OR c.text ILIKE '%date of birth certificate from the school%'
                      )
                    ORDER BY
                      CASE
                        WHEN c.text ILIKE '%date of birth certificate from the school%' THEN 0
                        ELSE 1
                      END,
                      c.id
                    LIMIT $2
                    """,
                    pack.search_query,
                    limit_per_pack,
                )
                for row in rows:
                    chunk = _hydrate_row(row)
                    _focus_required_source_pack_text(chunk, pack)
                    chunk.bm25_score = float(row["bm25_score"] or 0.0)
                    chunk.metadata["_required_source_pack"] = pack.id
                    chunk.metadata["_required_source_priority"] = pack.priority
                    chunk.metadata["_required_source_query"] = pack.search_query
                    out.append(chunk)
                continue
            title_patterns = [f"%{pattern}%" for pattern in pack.title_patterns]
            doc_ids = list(pack.doc_ids)
            section_nos = _section_numbers_from_anchor_patterns(pack.anchor_patterns)
            anchor_regexes = _anchor_regexes_from_patterns(pack.anchor_patterns)
            fetch_limit = max(limit_per_pack, limit_per_pack * max(1, len(pack.anchor_patterns)) * 4)
            rows = await conn.fetch(
                """
                SELECT c.id, c.document_id, c.anchor, c.text, c.source_type,
                       c.subject_area, c.as_at, c.paragraph_no, c.metadata,
                       d.title, d.citation, d.court, d.statute_short,
                       ts_rank(c.text_tsv, plainto_tsquery('english', $6)) AS bm25_score,
                       CASE
                         WHEN cardinality($4::text[]) > 0
                           AND c.metadata->>'section_no' = ANY($4::text[]) THEN 1
                         WHEN cardinality($5::text[]) > 0
                           AND c.anchor ~* ANY($5::text[]) THEN 1
                         ELSE 0
                       END AS anchor_priority,
                       COALESCE(array_position($4::text[], c.metadata->>'section_no'), 9999) AS anchor_order
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE NOT c.quarantined
                  AND c.source_type = ANY($2::text[])
                  AND (
                    d.doc_id = ANY($3::text[])
                    OR d.title ILIKE ANY($1::text[])
                    OR COALESCE(d.statute_short, '') ILIKE ANY($1::text[])
                  )
                  AND (
                    (cardinality($4::text[]) = 0 AND cardinality($5::text[]) = 0)
                    OR c.metadata->>'section_no' = ANY($4::text[])
                    OR c.anchor ~* ANY($5::text[])
                  )
                ORDER BY anchor_priority DESC, anchor_order ASC, bm25_score DESC,
                         c.paragraph_no NULLS LAST, c.id
                LIMIT $7
                """,
                title_patterns,
                list(pack.source_types),
                doc_ids,
                section_nos,
                anchor_regexes,
                pack.search_query,
                fetch_limit,
            )
            pack_chunks: list[RetrievedChunk] = []
            for row in rows:
                chunk = _hydrate_row(row)
                _focus_required_source_pack_text(chunk, pack)
                if (
                    pack.id == "ndps_1985"
                    and "section 36a" in pack.search_query.lower()
                    and chunk.metadata.get("section_no") != "36A"
                ):
                    continue
                if (
                    pack.id == "constitution_article_46"
                    and chunk.metadata.get("section_no") != "46"
                ):
                    continue
                if (
                    pack.id == "jj_2015"
                    and "adoption" in pack.search_query.lower()
                    and chunk.metadata.get("section_no") not in {"56", "57", "58", "59", "62", "63"}
                ):
                    continue
                chunk.bm25_score = float(row["bm25_score"] or 0.0)
                chunk.metadata["_required_source_pack"] = pack.id
                chunk.metadata["_required_source_priority"] = pack.priority
                chunk.metadata["_required_source_query"] = pack.search_query
                pack_chunks.append(chunk)
            out.extend(_diversify_source_pack_chunks(
                pack_chunks,
                section_nos=section_nos,
                anchor_regexes=anchor_regexes,
                limit=limit_per_pack,
            ))
    return out


async def _merge_required_source_packs(
    pool: asyncpg.Pool,
    query: str,
    *,
    union: dict[int, RetrievedChunk],
    packs: list[SourcePack],
    timings: dict[str, float] | None,
) -> None:
    """Merge exact required-source candidates into an existing candidate map."""
    s = get_settings()
    if not getattr(s, "required_source_pack_enabled", True) or not packs:
        return

    t_source_pack = time.perf_counter()
    try:
        source_candidates = await _fetch_source_pack_candidates(
            pool,
            query,
            packs=packs,
            limit_per_pack=getattr(s, "required_source_pack_limit_per_pack", 4),
        )
    except Exception as e:
        logger.warning("required-source pack retrieval failed: %s", e)
        source_candidates = []
    if timings is not None:
        timings["required_source_pack"] = time.perf_counter() - t_source_pack

    for c in _filter_query_ineligible_sources(query, source_candidates):
        existing = union.get(c.chunk_id)
        if existing is None:
            union[c.chunk_id] = c
            continue
        existing_pack = existing.metadata.get("_required_source_pack")
        existing_priority = float(existing.metadata.get("_required_source_priority") or 0.0)
        existing_query = existing.metadata.get("_required_source_query")
        incoming_pack = c.metadata.get("_required_source_pack")
        incoming_priority = float(c.metadata.get("_required_source_priority") or 0.0)
        incoming_wins = bool(incoming_pack) and (
            not existing_pack or incoming_priority >= existing_priority
        )
        if incoming_wins and c.anchor != existing.anchor:
            existing.anchor = c.anchor
            existing.text = c.text
            existing.title = c.title
            existing.source_type = c.source_type
            existing.subject_area = c.subject_area
            existing.as_at = c.as_at
            existing.paragraph_no = c.paragraph_no
            existing.citation = c.citation
            existing.court = c.court
            existing.statute_short = c.statute_short
        existing.metadata.update(c.metadata)
        if existing_pack and incoming_pack and existing_priority > incoming_priority:
            existing.metadata["_required_source_pack"] = existing_pack
            existing.metadata["_required_source_priority"] = existing_priority
            if existing_query:
                existing.metadata["_required_source_query"] = existing_query
        existing.bm25_score = max(existing.bm25_score, c.bm25_score)


def _rerank_candidate_union(
    query: str,
    candidate_list: list[RetrievedChunk],
    *,
    variants: list[str],
    route_category: str,
    packs: list[SourcePack],
    top_k: int | None,
    timings: dict[str, float] | None,
) -> list[RetrievedChunk]:
    """Rerank a merged candidate set while preserving exact source packs."""
    s = get_settings()
    limit = top_k or s.rerank_top_k
    if not candidate_list:
        return []

    do_rerank = s.rerank_enabled
    if not do_rerank:
        return candidate_list[:limit]

    from apps.api.rerank import rerank as _rerank
    # Cap candidates at rerank_input_k to bound cost.
    candidate_list.sort(
        key=lambda c: (
            1 if c.metadata.get("_required_source_pack") else 0,
            c.combined_score,
        ),
        reverse=True,
    )
    candidate_list = candidate_list[: s.rerank_input_k]

    # rerank() mutates each chunk's rerank_score in place. To take
    # the max across variants we call it once per query and copy
    # the scores into a side dict, then write the max back.
    max_scores: dict[int, float] = {c.chunk_id: -1.0 for c in candidate_list}
    rerank_queries = variants[: max(1, getattr(s, "rerank_variant_query_limit", 2))]
    t_variant_rerank = time.perf_counter()
    for q in rerank_queries:
        # `keep=None` returns the full list, sorted by THIS query's score
        reranked = _rerank(q, list(candidate_list), keep=None)
        for c in reranked:
            if c.rerank_score is not None and c.rerank_score > max_scores[c.chunk_id]:
                max_scores[c.chunk_id] = c.rerank_score
    if timings is not None:
        timings["variant_rerank"] = time.perf_counter() - t_variant_rerank

    # Write the per-chunk max back and re-sort. -1.0 default means
    # rerank returned None (degraded state) → keep negative so the
    # downstream `top_rerank = max(...)` check fails closed.
    #
    # 2026-05-21 additions (Codex/agent findings):
    # A) section-N boost: when the ORIGINAL query contains an
    #    explicit "section N" / "Article N" reference, multiply
    #    the rerank score by 1.5× for any chunk whose anchor
    #    matches `<slug>/sec-N`. Targets the canonical
    #    "section 138 NI Act" failure where the bare-Act chunk
    #    was retrieved but the rerank still preferred SC caselaw
    #    that discusses s.138 more verbosely.
    # B) bare-act source boost: +0.05 to rerank score for chunks
    #    whose anchor doesn't match SC's "<year>-insc-..." pattern.
    #    Mild preference for operative law over caselaw when both
    #    score similarly. Inspired by TurboVec's source_quality
    #    weight feature.
    import re as _re
    _sec_ref = _re.compile(r"section\s+(\d{1,4}[A-Z]?)|article\s+(\d{1,4}[A-Z]?)", _re.IGNORECASE)
    _sc_anchor = _re.compile(r"^\d{4}-(insc|\d+-\d+)")
    sec_matches = _sec_ref.findall(query)
    target_secs: set[str] = set()
    for m in sec_matches:
        target_secs.add(m[0] or m[1])

    for c in candidate_list:
        score = max_scores[c.chunk_id]
        if score < 0.0:
            c.rerank_score = None
            continue
        # A) section-N boost
        if target_secs and c.anchor:
            anchor_lower = c.anchor.lower()
            for tsec in target_secs:
                if f"/sec-{tsec.lower()}" in anchor_lower:
                    # Boost: 50% of headroom toward 1.0
                    score = min(1.0, score + 0.5 * (1.0 - score))
                    break
        # B) bare-act source boost (mild preference for operative law)
        if c.anchor and not _sc_anchor.match(c.anchor):
            # 5% headroom-bonus toward 1.0
            score = min(1.0, score + 0.05 * (1.0 - score))
        # C) required-source pack boost. The route picked the matter
        # and the pack fetched an exact indexed Act title. Keep that
        # authority above the coverage gate even when the cross-encoder
        # prefers a factually similar judgment.
        if c.metadata.get("_required_source_pack"):
            score = max(score, getattr(s, "required_source_pack_min_score", 0.42))
            boost = getattr(s, "required_source_pack_boost", 0.10)
            score = min(1.0, score + boost * (1.0 - score))
        c.rerank_score = score
    _apply_authority_rerank_boosts(
        candidate_list,
        route_category=route_category,
        source_quality_boost=getattr(s, "source_quality_boost", 0.06),
        source_cluster_boost=getattr(s, "source_cluster_boost", 0.04),
    )
    candidate_list.sort(
        key=lambda c: c.rerank_score if c.rerank_score is not None else -1e9,
        reverse=True,
    )
    return _preserve_required_source_packs(
        candidate_list,
        [pack.id for pack in packs],
        limit=limit,
        preferred_top_n=getattr(s, "required_source_pack_preferred_top_n", 4),
    )


# ---------------------------------------------------------------------------
# Hybrid retrieval — orchestrator
# ---------------------------------------------------------------------------


async def hybrid_retrieve(
    pool: asyncpg.Pool,
    query: str,
    *,
    source_types: list[str] | None = None,
    subject_areas: list[str] | None = None,
    as_of: date | None = None,
    top_k: int | None = None,
    use_reranker: bool | None = None,
    use_sparse: bool | None = None,
) -> list[RetrievedChunk]:
    """Three-source hybrid retrieval with RRF fusion (or legacy 70/30).

    The mode is set by `settings.hybrid_mode`. `dense_sparse_bm25` (default)
    runs dense + sparse + BM25, plus the optional bare-Act fielded BM25
    head, and fuses via RRF. `dense_bm25` runs dense + BM25 plus optional
    fielded BM25 and uses the legacy weighted-sum order.

    `use_reranker=False` disables the cross-encoder rerank stage; useful
    for ablation studies. Falls back to the pre-rerank order if the
    reranker is unavailable.

    `use_sparse=False` explicitly skips the sparse JSONB head even when
    `hybrid_mode == "dense_sparse_bm25"`. Used by `multi_query_hybrid_
    retrieve` to skip sparse on LLM-generated variants — the agent #4
    latency profile showed sparse owns 99% of every hybrid_retrieve call
    (~10s/call), and the synonym-bridging it provides is only useful for
    lay-phrase original queries, not for the explicit-legal-vocabulary
    variants. Skipping it on variants saves ~25% of total latency.
    """
    s = get_settings()
    if top_k is None:
        top_k = s.rerank_top_k

    embedder = get_embedder()
    if use_sparse is None:
        use_sparse = s.hybrid_mode == "dense_sparse_bm25"
    else:
        # Explicit override; ensure mode supports it
        use_sparse = use_sparse and s.hybrid_mode == "dense_sparse_bm25"

    # Query embedding(s). On the flag-embedding runtime we can get dense
    # AND sparse from one forward pass; on the sentence-transformers
    # runtime we can only get dense, in which case we silently fall back
    # to dense+bm25 (logged so operators notice).
    q_sparse: dict[str, float] | None = None
    if use_sparse and hasattr(embedder, "encode_with_sparse"):
        try:
            d_arr, s_list = embedder.encode_with_sparse([query])
            q_vec = d_arr[0]
            q_sparse = s_list[0]
        except NotImplementedError:
            logger.warning(
                "hybrid_retrieve: embedder doesn't support sparse; "
                "falling back to dense+bm25 for this query",
            )
            q_vec = embedder.encode_one(query)
            use_sparse = False
    else:
        if use_sparse:
            logger.warning(
                "hybrid_retrieve: embedding_runtime doesn't expose sparse; "
                "running dense+bm25 instead. Set embedding_runtime='flag'.",
            )
            use_sparse = False
        q_vec = embedder.encode_one(query)

    q_vec_lit = embedding_to_halfvec_literal(q_vec)

    # Filters as SQL fragments
    where: list[str] = ["NOT c.quarantined"]
    params: list = []
    if source_types:
        params.append(source_types)
        where.append(f"c.source_type = ANY(${len(params)})")
    if subject_areas:
        params.append(subject_areas)
        where.append(f"c.subject_area = ANY(${len(params)})")
    if as_of:
        # For statute chunks, prefer versions whose as_at <= as_of.
        # Judgment chunks have no as_at (NULL) and pass through.
        params.append(as_of)
        where.append(f"(c.as_at IS NULL OR c.as_at <= ${len(params)})")

    # Provenance gate: in production mode, only return chunks from documents
    # whose source has been verified against the canonical Govt source.
    if s.require_provenance_verified:
        where.append(
            "EXISTS (SELECT 1 FROM documents d2 "
            "WHERE d2.id = c.document_id AND d2.provenance_verified = true)"
        )

    where_clause = " AND ".join(where)

    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL hnsw.ef_search = {s.hnsw_ef_search};")

        # --- Dense ANN top N ---
        dense_n = s.dense_top_k
        params_dense = params + [q_vec_lit, dense_n]
        dense_rows = await conn.fetch(
            f"""SELECT c.id, c.document_id, c.anchor, c.text, c.source_type,
                       c.subject_area, c.as_at, c.paragraph_no, c.metadata,
                       d.title, d.citation, d.court, d.statute_short,
                       1 - (c.embedding <=> ${len(params)+1}::halfvec) AS dense_score
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE {where_clause}
                ORDER BY c.embedding <=> ${len(params)+1}::halfvec
                LIMIT ${len(params)+2}""",
            *params_dense,
        )

        # --- BM25 top N ---
        bm25_n = s.bm25_top_k
        params_bm25 = params + [query, bm25_n]
        bm25_rows = await conn.fetch(
            _bm25_retrieve_sql(
                where_clause=where_clause,
                where_param_count=len(params),
                fielded=False,
            ),
            *params_bm25,
        )

        # --- Fielded BM25 top N (bare Acts only) ---
        #
        # Running fielded title/statute/anchor search across every SC/HC
        # judgment is both noisy and slow: judgment headers contain many Act
        # names and section references. Keep the all-corpus BM25 body-text
        # head above, and add this narrow legal-structure head for the place
        # it matters most: getting operative bare Acts into the candidate set.
        fielded_bm25_rows: list = []
        fielded_enabled = getattr(s, "fielded_bm25_enabled", True)
        fielded_allowed = not source_types or "bare_act" in source_types
        if fielded_enabled and fielded_allowed:
            fielded_where_clause = f"{where_clause} AND c.source_type = 'bare_act'"
            fielded_bm25_n = getattr(s, "fielded_bm25_top_k", 50)
            params_fielded_bm25 = params + [query, fielded_bm25_n]
            fielded_bm25_rows = await conn.fetch(
                _bm25_retrieve_sql(
                    where_clause=fielded_where_clause,
                    where_param_count=len(params),
                    fielded=True,
                ),
                *params_fielded_bm25,
            )

        # --- Sparse top N (when enabled) ---
        sparse_rows: list = []
        if use_sparse and q_sparse:
            sparse_rows = await sparse_retrieve(
                conn,
                q_sparse,
                top_k=s.sparse_top_k,
                where_clause=where_clause,
                where_params=params,
            )

    # ---- Union + dedupe by chunk.id ----
    merged: dict[int, RetrievedChunk] = {}

    for r in dense_rows:
        if r["id"] not in merged:
            merged[r["id"]] = _hydrate_row(r)
        merged[r["id"]].dense_score = float(r["dense_score"])
    for r in bm25_rows:
        if r["id"] not in merged:
            merged[r["id"]] = _hydrate_row(r)
        merged[r["id"]].bm25_score = float(r["bm25_score"])
    for r in fielded_bm25_rows:
        if r["id"] not in merged:
            merged[r["id"]] = _hydrate_row(r)
        merged[r["id"]].bm25_score = max(
            merged[r["id"]].bm25_score,
            float(r["bm25_score"]),
        )
    for r in sparse_rows:
        if r["id"] not in merged:
            merged[r["id"]] = _hydrate_row(r)
        merged[r["id"]].sparse_score = float(r["sparse_score"])

    if merged:
        merged = {
            cid: chunk
            for cid, chunk in merged.items()
            if _query_allows_state_specific_source(query, chunk)
        }

    # ---- Stage 1.5 — fuse (RRF when multi-head, weighted-sum otherwise) ----
    if use_sparse:
        # Build per-head rankings (ids in score-descending order).
        dense_ids = [r["id"] for r in dense_rows]
        bm25_ids = [r["id"] for r in bm25_rows]
        sparse_ids = [r["id"] for r in sparse_rows]
        fielded_bm25_ids = [r["id"] for r in fielded_bm25_rows]
        fused = rrf_fuse([dense_ids, sparse_ids, bm25_ids, fielded_bm25_ids], k=s.rrf_k)
        for cid, score in fused.items():
            if cid in merged:
                merged[cid].rrf_score = score
        # Order by RRF first, then by combined_score as tie-breaker
        # (rare — only when two chunks were never co-ranked).
        out = sorted(
            merged.values(),
            key=lambda c: (
                c.rrf_score if c.rrf_score is not None else 0.0,
                c.combined_score,
            ),
            reverse=True,
        )
    else:
        out = sorted(merged.values(), key=lambda c: c.combined_score, reverse=True)

    # Stage 2: cross-encoder rerank top N candidates
    do_rerank = use_reranker if use_reranker is not None else s.rerank_enabled
    if do_rerank and out:
        from apps.api.rerank import rerank as _rerank
        candidates = out[: s.rerank_input_k]
        reranked = _rerank(query, candidates, keep=top_k)
        logger.info(
            "hybrid_retrieve[%s]: %d dense + %d bm25 + %d sparse + %d fielded "
            "→ %d merged → rerank(%d) → top %d",
            s.hybrid_mode,
            len(dense_rows), len(bm25_rows), len(sparse_rows), len(fielded_bm25_rows),
            len(merged), len(candidates), len(reranked),
        )
        return reranked

    logger.info(
        "hybrid_retrieve[%s]: %d dense + %d bm25 + %d sparse + %d fielded → %d merged → "
        "top %d (no rerank)",
        s.hybrid_mode,
        len(dense_rows), len(bm25_rows), len(sparse_rows), len(fielded_bm25_rows),
        len(merged), min(top_k, len(out)),
    )
    return out[:top_k]


async def multi_query_hybrid_retrieve(
    pool: asyncpg.Pool,
    query: str,
    *,
    source_types: list[str] | None = None,
    subject_areas: list[str] | None = None,
    top_k: int | None = None,
    timings: dict[str, float] | None = None,
) -> tuple[list[RetrievedChunk], list[str]]:
    """Retrieve using the original query + LLM-expanded legal-vocabulary variants.

    Returns (chunks, variants_used). `variants_used` is empty when expansion
    was skipped (disabled in config, LLM unavailable, or NOT_LEGAL signal).

    Two-stage flow:
      1. Ask the local LLM to translate the lay-phrase query into 2-3
         legal-vocabulary variants (apps.api.query_expand.expand_query).
         qwen3:14b at ~1.4s avg latency.
      2. Run hybrid_retrieve(...) concurrently for the original + each
         variant, with `use_reranker=False` so each call only contributes
         candidates (not variant-specific rerank scores). Collect the
         union, dedupe by chunk_id, then run a SINGLE rerank pass
         against the ORIGINAL query so the scores stay calibrated to
         what the user actually asked.

    Validated on 15 worst-failing queries from the 102-query e2e eval
    (scripts/eval_query_expand.py, 2026-05-19):
      - bare-act surface rate in top-5: 13% → 53% (+4×)
      - 14/15 queries now have a top-rerank > 0.4 (the coverage gate),
        i.e. would no longer be refused outright
      - 0/15 WORSE (expansion never hurt)

    Falls back to plain hybrid_retrieve when:
      - settings.query_expansion_enabled is False
      - expand_query returns only [original] (LLM failure or NOT_LEGAL)
    """
    import asyncio

    s = get_settings()
    if not getattr(s, "query_expansion_enabled", True):
        t_plain = time.perf_counter()
        chunks = await hybrid_retrieve(
            pool, query,
            source_types=source_types, subject_areas=subject_areas,
            top_k=top_k,
        )
        if timings is not None:
            timings["retrieval_plain"] = time.perf_counter() - t_plain
        return chunks, []

    # Stage 1: LLM-expand
    t_expand = time.perf_counter()
    try:
        from apps.api.query_expand import expand_query
        variants = await expand_query(
            query,
            max_variants=getattr(s, "query_expansion_max_variants", 2),
        )
    except Exception as e:
        logger.warning("multi_query_retrieve: expand_query failed: %s", e)
        variants = [query]
    if timings is not None:
        timings["query_expand"] = time.perf_counter() - t_expand

    if len(variants) == 1:
        # Either disabled, LLM down, or NOT_LEGAL — just original.
        if getattr(s, "query_expansion_strategy", "single") == "single":
            t_single = time.perf_counter()
            chunks = await hybrid_retrieve(
                pool,
                query,
                source_types=source_types,
                subject_areas=subject_areas,
                top_k=s.rerank_input_k,
                use_reranker=False,
                use_sparse=False,
            )
            if timings is not None:
                timings["retrieval_single_query"] = time.perf_counter() - t_single
            if not chunks:
                return [], []

            union = {c.chunk_id: c for c in chunks}
            route = route_matter(query)
            packs = source_packs_for_route(route, query)
            await _merge_required_source_packs(
                pool,
                query,
                union=union,
                packs=packs,
                timings=timings,
            )
            candidate_list = _rerank_candidate_union(
                query,
                list(union.values()),
                variants=variants,
                route_category=route.category,
                packs=packs,
                top_k=top_k,
                timings=timings,
            )
            logger.info(
                "single_query_retrieve: original only → %d candidates → top %d "
                "(top_rerank=%.3f)",
                len(union),
                len(candidate_list),
                (candidate_list[0].rerank_score if candidate_list and
                 candidate_list[0].rerank_score is not None else 0.0),
            )
            return candidate_list, []

        t_single = time.perf_counter()
        chunks = await hybrid_retrieve(
            pool, query,
            source_types=source_types, subject_areas=subject_areas,
            top_k=top_k,
        )
        if timings is not None:
            timings["retrieval_single_query"] = time.perf_counter() - t_single
        return chunks, []

    if getattr(s, "query_expansion_strategy", "single") == "single":
        t_single_expanded = time.perf_counter()
        expanded_query = " ".join(variants)
        chunks = await hybrid_retrieve(
            pool,
            expanded_query,
            source_types=source_types,
            subject_areas=subject_areas,
            top_k=s.rerank_input_k,
            use_reranker=False,
            use_sparse=False,
        )
        if timings is not None:
            timings["single_expanded_retrieval"] = time.perf_counter() - t_single_expanded
        if not chunks:
            return [], variants[1:]

        union = {c.chunk_id: c for c in chunks}
        route = route_matter(query)
        packs = source_packs_for_route(route, query)
        await _merge_required_source_packs(
            pool,
            query,
            union=union,
            packs=packs,
            timings=timings,
        )
        candidate_list = _rerank_candidate_union(
            query,
            list(union.values()),
            variants=variants,
            route_category=route.category,
            packs=packs,
            top_k=top_k,
            timings=timings,
        )
        logger.info(
            "single_query_retrieve: %d variants → %d candidates → top %d "
            "(top_rerank=%.3f)",
            len(variants),
            len(union),
            len(candidate_list),
            (candidate_list[0].rerank_score if candidate_list and
             candidate_list[0].rerank_score is not None else 0.0),
        )
        return candidate_list, variants[1:]

    # Stage 2a: gather candidates per variant in parallel.
    #
    # NO rerank yet — each variant contributes its hybrid-fused (dense +
    # BM25, no sparse on variants) top-`rerank_input_k` candidates. We
    # don't rerank inside because the rerank scores would be calibrated
    # to the VARIANT, not the original.
    #
    # Sparse is enabled ONLY for the ORIGINAL query (index 0). The agent
    # #4 latency profile (2026-05-19) found sparse JSONB owned ~99% of
    # every hybrid_retrieve call (~10s); running it 4× per /answer
    # doubled total latency. Sparse is most valuable for lay-phrase
    # synonym bridging — the variants are already explicit legal
    # vocabulary that BM25 + dense match well. Predicted recall impact
    # is negligible; latency win ~25% per /answer.
    t_candidates = time.perf_counter()
    candidates_per_variant = await asyncio.gather(
        *[
            hybrid_retrieve(
                pool, v,
                source_types=source_types,
                subject_areas=subject_areas,
                top_k=s.rerank_input_k,
                use_reranker=False,
                use_sparse=(i == 0 and getattr(s, "query_expansion_sparse_original", False)),
            )
            for i, v in enumerate(variants)
        ],
        return_exceptions=True,
    )
    if timings is not None:
        timings["variant_candidate_retrieval"] = time.perf_counter() - t_candidates

    # Stage 2b: dedupe across variants (chunk_id is the canonical key).
    union: dict[int, RetrievedChunk] = {}
    for variant_result in candidates_per_variant:
        if isinstance(variant_result, BaseException):
            logger.warning("multi_query: a variant retrieval errored: %s", variant_result)
            continue
        for c in variant_result:
            # Keep the highest combined_score seen for any duplicate
            existing = union.get(c.chunk_id)
            if existing is None or (c.combined_score > existing.combined_score):
                union[c.chunk_id] = c

    if not union:
        return [], variants[1:]

    route = route_matter(query)
    packs = source_packs_for_route(route, query)
    await _merge_required_source_packs(
        pool,
        query,
        union=union,
        packs=packs,
        timings=timings,
    )
    candidate_list = _rerank_candidate_union(
        query,
        list(union.values()),
        variants=variants,
        route_category=route.category,
        packs=packs,
        top_k=top_k,
        timings=timings,
    )

    logger.info(
        "multi_query_retrieve: %d variants → %d union candidates → "
        "rerank-max top %d (top_rerank=%.3f)",
        len(variants), len(union), len(candidate_list),
        (candidate_list[0].rerank_score if candidate_list and
         candidate_list[0].rerank_score is not None else 0.0),
    )

    return candidate_list, variants[1:]


__all__ = [
    "RetrievedChunk", "hybrid_retrieve", "multi_query_hybrid_retrieve",
    "rrf_fuse", "sparse_retrieve",
]
