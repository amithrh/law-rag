#!/usr/bin/env python3
"""Calibrate the bge-reranker-as-verifier threshold against a real battery run.

Architecture-research task #2, step 1.

Approach:
  1. Load the most recent battery v3 trace.
  2. For each cited sentence in the trace, fetch the cited passage text(s)
     from Postgres (the trace only carries passage metadata, not text).
  3. Compute bge-reranker-v2-m3 score for (passage, sentence) pairs and
     take the MAX across cited passages — same aggregation as the live
     verifier's NLI path.
  4. Treat the NLI status already in the trace as ground truth (OK vs
     WEAK_SUPPORT). Find the bge threshold T such that
     "bge_max >= T" matches "NLI status == OK" with precision > 0.9.
  5. Pick the hard floor at the bottom percentile of WEAK_SUPPORT
     sentences (analogous to the 0.10 floor on NLI which is below the
     paraphrase band).
  6. Write calibration to data/processed/bge_verifier_calibration.json.

Caveats called out in the report:
  - NLI is not "ground truth" — it's the legacy scorer. This calibration
    is "where does bge agree with NLI", NOT "where does bge correctly
    detect entailment". For real entailment ground truth we'd need
    human labels.
  - The trace only contains sentences that already passed coverage and
    the NLI hard floor (UNSUPPORTED sentences are SUPPRESSED upstream).
    So this calibration tells us how bge ranks the OK/WEAK survivors,
    not how it handles the obviously-bad cases. The hard floor is
    calibrated separately by reading WEAK_SUPPORT scores and picking a
    conservative low-end percentile.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from apps.api.config import get_settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def load_anchor_text(pool: asyncpg.Pool, anchors: list[str]) -> dict[str, str]:
    """Fetch chunk text for each anchor. Anchors are document-scoped
    identifiers — same anchor across documents is impossible by schema
    contract, so a single lookup table is enough."""
    if not anchors:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT anchor, text FROM chunks WHERE anchor = ANY($1::text[])",
            anchors,
        )
    return {r["anchor"]: r["text"] for r in rows}


def find_latest_trace(processed_dir: Path) -> Path:
    candidates = sorted(processed_dir.glob("battery_v3_*.json"))
    if not candidates:
        raise SystemExit("no battery_v3_*.json traces found")
    return candidates[-1]


def collect_pairs(trace: list[dict]) -> list[dict]:
    """Each item: {sentence, anchors (list), nli_status, nli_score}.

    Skips META sentences (they're not cited claims) and sentences without
    citations. Auto-cited and explicit-cited are both included — the
    point of the calibration is "does bge agree with NLI" regardless of
    citation source.
    """
    pairs = []
    for item in trace:
        passages_by_idx = {p["index"]: p["anchor"] for p in item["full"]["passages"]}
        for s in item["full"]["sentences"]:
            cits = s.get("citations") or []
            if not cits:
                continue
            status = s.get("status")
            if status not in ("ok", "weak_support"):
                # unsupported/unknown_citation are SUPPRESSED upstream so
                # they don't appear in the trace. META has no citations.
                continue
            anchors = [passages_by_idx.get(n) for n in cits if n in passages_by_idx]
            anchors = [a for a in anchors if a]
            if not anchors:
                continue
            pairs.append({
                "sentence": s["text"],
                "anchors": anchors,
                "nli_status": status,
                "nli_score": s.get("entailment_score"),
                "auto_cited": s.get("auto_cited", False),
                "query": item["full"]["query"],
            })
    return pairs


def calibrate_threshold(scored: list[dict], target_precision: float) -> dict:
    """Sweep candidate thresholds and pick the largest threshold T at which
    precision >= target_precision. "Precision" here = of sentences predicted
    OK by bge (bge >= T), what fraction were also OK by NLI.

    Why precision and not recall: the citation guarantee is "we never
    surface unsupported claims" → a false-positive (bge says OK, NLI
    says WEAK) is worse than a false-negative. Tune precision tight; let
    recall fall where it falls.
    """
    scores = sorted({p["bge_score"] for p in scored if p["bge_score"] is not None})
    rows = []
    best_T: float | None = None
    best_T_recall = 0.0
    for T in scores:
        tp = sum(1 for p in scored if p["bge_score"] >= T and p["nli_status"] == "ok")
        fp = sum(1 for p in scored if p["bge_score"] >= T and p["nli_status"] == "weak_support")
        fn = sum(1 for p in scored if p["bge_score"] < T and p["nli_status"] == "ok")
        if (tp + fp) == 0:
            continue
        precision = tp / (tp + fp)
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        rows.append({
            "threshold": round(T, 4),
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        })
        if precision >= target_precision and recall > best_T_recall:
            best_T = T
            best_T_recall = recall
    return {"sweep": rows, "best_threshold": best_T, "best_threshold_recall": best_T_recall}


def calibrate_hard_floor(scored: list[dict]) -> float:
    """Hard floor = the value below which we're confident the passage
    doesn't support the sentence at all (fabrication territory). We
    don't have UNSUPPORTED ground truth in the trace (those got
    suppressed upstream). Use the 5th percentile of WEAK_SUPPORT bge
    scores — anything below that is well outside the legitimate
    paraphrase band.
    """
    weak_scores = sorted(
        p["bge_score"] for p in scored
        if p["nli_status"] == "weak_support" and p["bge_score"] is not None
    )
    if not weak_scores:
        return -10.0  # ultra-permissive; no calibration data
    # 5th percentile
    n = len(weak_scores)
    idx = max(0, int(0.05 * n) - 1)
    return weak_scores[idx]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trace", type=str, default=None,
        help="Specific battery v3 JSON; defaults to latest."
    )
    parser.add_argument("--target-precision", type=float, default=0.90)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    settings = get_settings()
    processed = ROOT / "data" / "processed"
    trace_path = Path(args.trace) if args.trace else find_latest_trace(processed)
    out_path = Path(args.out) if args.out else processed / "bge_verifier_calibration.json"

    logger.info("trace: %s", trace_path)
    trace = json.loads(trace_path.read_text())
    pairs = collect_pairs(trace)
    logger.info("collected %d cited sentence/passage pairs", len(pairs))

    # Pull passage text from Postgres
    all_anchors = sorted({a for p in pairs for a in p["anchors"]})
    logger.info("fetching %d unique passages from postgres", len(all_anchors))
    dsn = settings.database_url or settings.resolved_database_url_host_side
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
    try:
        anchor_to_text = await load_anchor_text(pool, all_anchors)
    finally:
        await pool.close()
    missing = [a for a in all_anchors if a not in anchor_to_text]
    if missing:
        logger.warning("could not fetch %d anchors (corpus drift?); skipping those pairs",
                       len(missing))
    # Drop pairs whose first anchor we can't resolve. Keep pairs that have
    # AT LEAST one resolvable anchor.
    resolvable = []
    for p in pairs:
        texts = [anchor_to_text[a] for a in p["anchors"] if a in anchor_to_text]
        if texts:
            resolvable.append({**p, "passage_texts": texts})
    logger.info("scoring %d resolvable pairs with bge-reranker-v2-m3", len(resolvable))

    # Score with bge. Use the shared singleton — same model that runs at
    # retrieval-rerank time. Lazy load.
    from apps.api.verifier import bge_score
    # Warm up the reranker once
    _ = bge_score("warmup passage", "warmup sentence")
    scored = []
    for i, p in enumerate(resolvable):
        sentence = p["sentence"]
        # Max across cited passages — same aggregation as the live verifier
        scs = []
        for txt in p["passage_texts"]:
            sc = bge_score(txt, sentence)
            if sc is not None:
                scs.append(sc)
        if not scs:
            continue
        scored.append({**p, "bge_score": max(scs)})
        if (i + 1) % 25 == 0:
            logger.info("  scored %d/%d", i + 1, len(resolvable))

    # Stats
    n_ok = sum(1 for p in scored if p["nli_status"] == "ok")
    n_weak = sum(1 for p in scored if p["nli_status"] == "weak_support")
    logger.info("scored %d pairs (NLI: ok=%d, weak=%d)", len(scored), n_ok, n_weak)

    sweep = calibrate_threshold(scored, target_precision=args.target_precision)
    hard_floor = calibrate_hard_floor(scored)

    bge_ok = [p["bge_score"] for p in scored if p["nli_status"] == "ok"]
    bge_weak = [p["bge_score"] for p in scored if p["nli_status"] == "weak_support"]

    def summary(name, xs):
        if not xs:
            return {"name": name, "n": 0}
        xs = sorted(xs)
        return {
            "name": name,
            "n": len(xs),
            "min": round(xs[0], 4),
            "p10": round(xs[len(xs) // 10], 4),
            "p25": round(xs[len(xs) // 4], 4),
            "median": round(xs[len(xs) // 2], 4),
            "p75": round(xs[3 * len(xs) // 4], 4),
            "p90": round(xs[9 * len(xs) // 10], 4),
            "max": round(xs[-1], 4),
        }

    result = {
        "trace": str(trace_path),
        "target_precision": args.target_precision,
        "n_pairs_scored": len(scored),
        "n_nli_ok": n_ok,
        "n_nli_weak": n_weak,
        "bge_distribution_when_nli_ok": summary("nli_ok", bge_ok),
        "bge_distribution_when_nli_weak": summary("nli_weak", bge_weak),
        "threshold_sweep": sweep["sweep"],
        "best_threshold": sweep["best_threshold"],
        "best_threshold_recall": sweep["best_threshold_recall"],
        "hard_floor_p05_of_weak": round(hard_floor, 4),
        # Per-pair detail — useful for spot-checking calibration on
        # specific failure modes (case-name boilerplate, etc.).
        "per_pair": [
            {
                "sentence": p["sentence"][:200],
                "query": p["query"][:120],
                "nli_status": p["nli_status"],
                "nli_score": round(p["nli_score"], 4) if p["nli_score"] is not None else None,
                "bge_score": round(p["bge_score"], 4),
                "auto_cited": p["auto_cited"],
            }
            for p in scored
        ],
    }
    out_path.write_text(json.dumps(result, indent=2))
    logger.info("wrote %s", out_path)

    print()
    print("=== Calibration summary ===")
    print(f"  trace                : {trace_path.name}")
    print(f"  pairs scored          : {len(scored)} (NLI ok={n_ok}, weak={n_weak})")
    print(f"  bge when NLI ok       : median={result['bge_distribution_when_nli_ok'].get('median')}, "
          f"p10={result['bge_distribution_when_nli_ok'].get('p10')}")
    print(f"  bge when NLI weak     : median={result['bge_distribution_when_nli_weak'].get('median')}, "
          f"p90={result['bge_distribution_when_nli_weak'].get('p90')}")
    print(f"  best threshold (P>={args.target_precision:.2f}): {sweep['best_threshold']}")
    print(f"  recall at that T      : {sweep['best_threshold_recall']:.3f}")
    print(f"  hard floor (p05 weak) : {hard_floor:.3f}")
    print()
    if sweep["best_threshold"] is None:
        print("  WARNING: no threshold achieves the target precision; bge is")
        print("  NOT a clean substitute for NLI on this trace. Don't swap.")
    else:
        print(f"  Recommended settings:")
        print(f"    bge_verifier_threshold   = {sweep['best_threshold']:.3f}")
        print(f"    bge_verifier_hard_floor  = {hard_floor:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
