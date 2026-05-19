"""Lay-phrase → legal-vocabulary query expansion (Task #13).

Why this exists — the eval's #1 finding:

  The 102-query e2e eval (2026-05-19, scripts/eval_e2e_100.py) showed
  that 56/102 queries drew only from SC caselaw — even when the
  operative Act WAS indexed. Bare-act surface rate: 25%. The
  dominant failure mode was lay-phrase queries (e.g. "my landlord
  won't return my deposit", "boss fired me without notice") failing
  to find the legal-vocabulary terms used in bare Acts (TPA s.108,
  Industrial Disputes Act s.25F retrenchment notice).

  13 of those produced wrong-direction answers ("you should deposit
  rent in court" for the deposit query — citation-correct, topically
  wrong). The remaining 43 produced PARTIAL or REFUSED.

Approach (lightweight LLM rewrite):

  1. Use the local qwen3:14b that's already loaded for /answer.
  2. Ask it to translate the lay query into 2-3 legal-search variants
     that include Act names, section numbers, and statutory terms.
  3. Run hybrid retrieval (dense + sparse + BM25) on EACH variant
     plus the original, then RRF-fuse the results.
  4. The fused top-K should now have both lay-similar SC cases AND
     the directly-applicable bare-Act chunks.

Latency budget: ~1.5-2 sec for qwen3:14b at max_tokens=200. The
/answer flow already takes 25-35 sec; this added cost is acceptable.

Honest caveats:

  - The LLM may invent Act names that don't exist. We DON'T cite the
    LLM's output to the user — it's purely a retrieval rewrite step,
    so hallucination here only hurts retrieval recall (mildly), not
    citation correctness.
  - For genuinely off-corpus queries ("weather today"), the LLM may
    invent a plausible-sounding legal frame ("weather information
    under RTI Act"). That's fine: the coverage gate still refuses
    when rerank scores are low.
  - We default to enabled but expose a kill switch (`query_expansion_
    enabled` in config) so we can A/B during the rollout.
"""
from __future__ import annotations

import logging
import re
import time

from .llm import chat_once

logger = logging.getLogger(__name__)


# Strong, opinionated prompt that wants ONLY the queries — no preamble,
# no numbering, no extra commentary. qwen3:14b respects this most of the
# time but we still post-filter for safety.
_SYSTEM_PROMPT = (
    "You are a legal research assistant for Indian law. "
    "Given a lay-person question (which may be informal, in broken English, "
    "or use everyday words), output 3 short legal-search queries that an "
    "Indian legal database would use to find the relevant law.\n\n"
    "Each query MUST:\n"
    "- Include the name of the operative Act (e.g. 'Transfer of Property "
    "Act 1882', 'Industrial Disputes Act 1947', 'Senior Citizens Act "
    "2007', 'Negotiable Instruments Act section 138').\n"
    "- Use statutory terminology, not lay phrases ('eviction' not 'thrown "
    "out'; 'retrenchment' not 'fired'; 'maintenance' not 'taking care').\n"
    "- Be 4-12 words long.\n\n"
    "Output ONLY the 3 queries, one per line. No numbering, no quotes, "
    "no explanation, no preamble. If the question is not about Indian "
    "law (e.g. weather, food, code), output a single line: 'NOT_LEGAL'."
)


async def expand_query(query: str, *, max_variants: int = 3) -> list[str]:
    """Return [original_query, ...legal-vocabulary variants].

    Falls back to [original_query] on any error or NOT_LEGAL signal,
    so retrieval is never blocked by expansion failure.
    """
    if not query or not query.strip():
        return [query]

    t0 = time.time()
    try:
        raw = await chat_once(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Lay question: {query.strip()}"},
            ],
            temperature=0.3,    # small variation across variants
            max_tokens=200,
        )
    except Exception as e:
        logger.warning("query_expand: LLM call failed: %s", e)
        return [query]
    elapsed = time.time() - t0

    # qwen3 sometimes returns leading "thinking" content even with
    # think:false. Drop anything inside <think>...</think> if present.
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    if "NOT_LEGAL" in raw.upper():
        logger.info("query_expand: NOT_LEGAL signal (%.1fs); original only", elapsed)
        return [query]

    variants: list[str] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Drop common preamble phrases the LLM sometimes ignores instructions about
        if line.lower().startswith((
            "here are", "sure,", "of course", "note:", "1.", "2.", "3.",
            "•", "-", "*",
        )):
            # Try to peel off a leading bullet/number prefix
            line = re.sub(r"^(?:\d+[.)]|[•\-*])\s*", "", line).strip()
            if not line:
                continue
        # Drop obvious LLM-rambling lines
        if line.lower().startswith(("legal search queries", "queries:")):
            continue
        # Strip surrounding quotes
        line = line.strip('"').strip("'")
        if len(line) < 6 or len(line) > 200:
            continue
        variants.append(line)
        if len(variants) >= max_variants:
            break

    logger.info(
        "query_expand: %d variants in %.2fs (query=%r)",
        len(variants), elapsed, query[:60],
    )

    # Always return original first — it's the most reliable signal even
    # if all variants are bad.
    return [query] + variants


__all__ = ["expand_query"]
