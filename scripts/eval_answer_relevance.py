#!/usr/bin/env python3
"""Run the answer-relevance eval set against the live API (Task #10 Part B).

For each query in data/eval/answer_relevance.jsonl:
  1. POST /answer with the query.
  2. Stream the SSE response; capture the `relevance` event (if any),
     the refusal status, and the assembled answer body.
  3. Compare the observed verdict against the expected_verdict label.

Reports:
  - True-positive rate: trick queries correctly flagged off_topic / partial.
  - False-positive rate: in-scope queries incorrectly flagged off_topic.
  - Where each trick query lands (cosine score, verdict).

Usage:
    PYTHONPATH=. .venv/bin/python scripts/eval_answer_relevance.py
    PYTHONPATH=. .venv/bin/python scripts/eval_answer_relevance.py --api http://localhost:8000

The API must be running. This script doesn't load any ML models itself —
it consumes the events the server emits.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def stream_answer(api_base: str, q: str, *, top_k: int = 8) -> dict:
    """POST /answer, parse SSE, return a dict of the events we care about
    for relevance evaluation."""
    result: dict = {
        "query": q,
        "refused": False,
        "stopped": False,
        "relevance": None,
        "n_sentences": 0,
        "n_ok": 0,
        "n_weak": 0,
        "error": None,
        "total_ms": None,
    }
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=300.0) as c:
            with c.stream(
                "POST", f"{api_base}/answer",
                json={"q": q, "top_k": top_k, "skip_nli": False},
            ) as r:
                r.raise_for_status()
                current_event = None
                for line in r.iter_lines():
                    if not line:
                        current_event = None
                        continue
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and current_event:
                        try:
                            data = json.loads(line.split(":", 1)[1].strip())
                        except json.JSONDecodeError:
                            data = line.split(":", 1)[1].strip()
                        if current_event == "sentence":
                            result["n_sentences"] += 1
                            if isinstance(data, dict):
                                st = data.get("status")
                                if st == "ok":
                                    result["n_ok"] += 1
                                elif st == "weak_support":
                                    result["n_weak"] += 1
                        elif current_event == "stop":
                            result["stopped"] = True
                        elif current_event == "refused":
                            result["refused"] = True
                        elif current_event == "relevance":
                            result["relevance"] = data
    except Exception as e:
        result["error"] = str(e)
    result["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result


def classify_outcome(eval_item: dict, observed: dict) -> dict:
    """Did the observed result match the expected_verdict label?

    Categories:
      - "tp" (true positive): trick or out-of-scope correctly flagged
        OR an in-scope query correctly returned verdict=ok.
      - "fp" (false positive): in-scope query incorrectly flagged
        off_topic.
      - "fn" (false negative): trick query NOT flagged (verdict=ok).
      - "expected_refusal": out-of-slice query that the system correctly
        refused (no relevance event needed).
      - "other": query landed somewhere unexpected (e.g. trick query
        was refused — that's fine, the relevance check didn't have to
        fire because the refusal already protected the user).
    """
    expected = eval_item["expected_verdict"]
    category = eval_item["category"]

    rel = observed.get("relevance")
    refused = observed.get("refused")
    verdict = rel.get("verdict") if rel else None

    if expected == "refused":
        if refused:
            return {"outcome": "expected_refusal", "ok": True}
        # System tried to answer despite expecting refusal — depends
        # on the relevance verdict
        if verdict == "off_topic":
            return {"outcome": "rescued_by_relevance", "ok": True,
                    "note": "expected refusal but answered; relevance correctly flagged off_topic"}
        if verdict == "partial":
            return {"outcome": "partial_softened", "ok": True,
                    "note": "expected refusal but answered; relevance partial — soft signal to user"}
        return {"outcome": "missed_refusal", "ok": False}

    if expected == "ok":
        if refused:
            # Surprising but not a relevance failure
            return {"outcome": "unexpected_refusal", "ok": False}
        if verdict == "ok":
            return {"outcome": "tp_on_topic", "ok": True}
        if verdict == "partial":
            return {"outcome": "fp_partial", "ok": False,
                    "note": "in-scope query flagged partial"}
        if verdict == "off_topic":
            return {"outcome": "fp_off_topic", "ok": False,
                    "note": "in-scope query flagged off_topic"}
        return {"outcome": "no_relevance_event", "ok": False,
                "note": "expected verdict=ok but no relevance event emitted"}

    if expected == "off_topic_or_refused":
        if refused:
            return {"outcome": "trick_caught_by_refusal", "ok": True}
        if verdict == "off_topic":
            return {"outcome": "tp_off_topic", "ok": True}
        if verdict == "partial":
            return {"outcome": "tp_partial", "ok": True,
                    "note": "trick landed in partial band — graceful"}
        if verdict == "ok":
            return {"outcome": "fn_missed_trick", "ok": False,
                    "note": "trick query not flagged"}
        return {"outcome": "trick_no_relevance_event", "ok": False}

    if expected == "partial_or_off_topic":
        if refused:
            return {"outcome": "ambiguous_refused", "ok": True}
        if verdict in ("partial", "off_topic"):
            return {"outcome": "tp_ambiguous_flagged", "ok": True}
        if verdict == "ok":
            return {"outcome": "ambiguous_passed", "ok": True,
                    "note": "ambiguous query landed ok — acceptable"}
        return {"outcome": "ambiguous_no_event", "ok": True}

    return {"outcome": "unknown_expected", "ok": False}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--api", default=os.getenv("API_BASE", "http://localhost:8000"),
        help="API base URL (default: $API_BASE or http://localhost:8000)",
    )
    p.add_argument(
        "--eval-file", type=Path,
        default=ROOT / "data" / "eval" / "answer_relevance.jsonl",
    )
    p.add_argument(
        "--out", type=Path,
        default=ROOT / "data" / "processed" / "answer_relevance_eval.json",
    )
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument(
        "--limit", type=int, default=None,
        help="run only the first N queries (for quick smoke tests)",
    )
    args = p.parse_args()

    if not args.eval_file.exists():
        raise SystemExit(f"eval file not found: {args.eval_file}")

    items = [json.loads(line) for line in args.eval_file.read_text().split("\n") if line.strip()]
    if args.limit:
        items = items[:args.limit]
    logger.info("running %d queries against %s", len(items), args.api)

    rows: list[dict] = []
    for i, item in enumerate(items, 1):
        logger.info("[%2d/%d] %s — %s",
                    i, len(items), item["id"], item["query"][:80])
        observed = stream_answer(args.api, item["query"], top_k=args.top_k)
        outcome = classify_outcome(item, observed)
        rows.append({
            "id": item["id"],
            "category": item["category"],
            "query": item["query"],
            "expected_verdict": item["expected_verdict"],
            "observed_refused": observed["refused"],
            "observed_stopped": observed["stopped"],
            "observed_relevance": observed["relevance"],
            "observed_n_ok": observed["n_ok"],
            "observed_n_weak": observed["n_weak"],
            "outcome": outcome,
            "total_ms": observed["total_ms"],
            "error": observed["error"],
        })
        cosine = (observed["relevance"] or {}).get("score")
        verdict = (observed["relevance"] or {}).get("verdict")
        logger.info(
            "    refused=%s stopped=%s verdict=%s cosine=%s outcome=%s",
            observed["refused"], observed["stopped"], verdict, cosine,
            outcome["outcome"],
        )

    # Aggregate
    by_category: dict[str, Counter] = {}
    for r in rows:
        by_category.setdefault(r["category"], Counter())[r["outcome"]["outcome"]] += 1

    # Compute TPR / FPR
    tp = sum(1 for r in rows if r["category"] in ("trick_semantic_flip",)
             and r["outcome"]["outcome"] in (
                 "tp_off_topic", "tp_partial", "trick_caught_by_refusal"
             ))
    fn = sum(1 for r in rows if r["category"] in ("trick_semantic_flip",)
             and r["outcome"]["outcome"] in ("fn_missed_trick", "trick_no_relevance_event"))
    fp = sum(1 for r in rows if r["category"] == "in_scope"
             and r["outcome"]["outcome"] in ("fp_off_topic", "fp_partial"))
    tn = sum(1 for r in rows if r["category"] == "in_scope"
             and r["outcome"]["outcome"] == "tp_on_topic")
    tpr = tp / (tp + fn) if (tp + fn) else None
    fpr = fp / (fp + tn) if (fp + tn) else None

    summary = {
        "api": args.api,
        "eval_file": str(args.eval_file),
        "n_queries": len(rows),
        "by_category": {k: dict(v) for k, v in by_category.items()},
        "tpr_off_topic": round(tpr, 4) if tpr is not None else None,
        "fpr_off_topic": round(fpr, 4) if fpr is not None else None,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "rows": rows,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2))

    print()
    print("=" * 70)
    print("Answer-relevance eval summary")
    print("=" * 70)
    print(f"  Total queries:   {len(rows)}")
    print(f"  True positive (trick flagged):     {tp}")
    print(f"  False negative (trick missed):     {fn}")
    print(f"  False positive (in-scope flagged): {fp}")
    print(f"  True negative (in-scope ok):       {tn}")
    print(f"  TPR (off-topic recall):  {tpr:.2%}" if tpr is not None else "  TPR: n/a")
    print(f"  FPR (in-scope flagged):  {fpr:.2%}" if fpr is not None else "  FPR: n/a")
    print()
    print("Where each trick query landed:")
    for r in rows:
        if r["category"] != "trick_semantic_flip":
            continue
        cosine = (r["observed_relevance"] or {}).get("score")
        verdict = (r["observed_relevance"] or {}).get("verdict")
        refused = r["observed_refused"]
        print(
            f"  {r['id']:32s} refused={refused!s:5s} "
            f"verdict={verdict!s:9s} cosine={cosine!s:7s} → {r['outcome']['outcome']}"
        )
    print()
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
