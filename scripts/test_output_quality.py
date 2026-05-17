#!/usr/bin/env python3
"""Run a battery of real public-user queries through /answer and capture
what comes out. Surfaces output-quality issues before we build the UI.

This is NOT a unit test (those are in apps/api/tests/). This is a
qualitative output audit:
  - Real questions a layperson would ask
  - Real LLM stream + real verifier + real reranker
  - Captures: response sentences, statuses (ok/weak/unsupported), citations,
    coverage chip, latency, refusals, stops
  - Writes results to data/processed/output_quality_<timestamp>.json for
    review

Use to:
  - Spot retrieval gaps (what subjects need more data)
  - Spot prompt issues (LLM violating lay-friendly format)
  - Spot verifier issues (false unsupported, missed bad claims)
  - Tune SKIP_RATIO_STOP, NLI threshold, etc.

Run with:
  PYTHONPATH=. .venv/bin/python -u scripts/test_output_quality.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
API_BASE = "http://127.0.0.1:8000"

# Representative public-user queries across slice subjects.
# Phrased the way a layperson would actually type them.
QUERIES: list[dict] = [
    # ===== Consumer =====
    {"subject": "consumer", "q": "My online order arrived broken. Can I get a refund and where do I file a complaint?"},
    {"subject": "consumer", "q": "The builder didn't deliver my flat on time. What are my options?"},
    {"subject": "consumer", "q": "A doctor gave me wrong treatment and now I have permanent damage. Can I sue?"},

    # ===== Family =====
    {"subject": "family", "q": "My husband threatens me and throws me out of the house. What legal protection do I have?"},
    {"subject": "family", "q": "Can I file for divorce on grounds of cruelty? How long does it take?"},
    {"subject": "family", "q": "My wife took away our child. Can I get custody?"},

    # ===== Criminal =====
    {"subject": "criminal", "q": "Police did not file my FIR. What can I do?"},
    {"subject": "criminal", "q": "I fear I will be arrested. Can I apply for anticipatory bail and how?"},
    {"subject": "criminal", "q": "What is the maximum punishment for theft under Indian law?"},
    {"subject": "criminal", "q": "Can a confession I gave to police be used against me in court?"},

    # ===== Wages =====
    {"subject": "wages", "q": "My employer has not paid my salary for two months. How do I recover it?"},
    {"subject": "wages", "q": "I was fired without notice. Am I entitled to any compensation?"},

    # ===== RTI =====
    {"subject": "rti", "q": "I filed an RTI and it was rejected. Can I appeal? What is the time limit?"},

    # ===== Motor =====
    {"subject": "motor", "q": "My family member died in a road accident. How do I claim compensation?"},
    {"subject": "motor", "q": "I had a car accident. The other driver was drunk. What can I do?"},

    # ===== Out-of-slice (should refuse honestly) =====
    {"subject": "tax", "q": "How is capital gains tax calculated on the sale of a house?"},  # out of slice
    {"subject": "constitutional", "q": "Does the right to privacy come from the Constitution?"},  # out of slice

    # ===== Genuinely unsupported (should refuse, NOT hallucinate) =====
    {"subject": "unknown", "q": "What is the airspeed velocity of an unladen swallow under Indian law?"},
]


def stream_answer(q: str, *, top_k: int = 8, skip_nli: bool = False) -> dict:
    """Hit /answer SSE, collect every event into a structured result."""
    result = {
        "query": q,
        "events": [],
        "sentences": [],
        "stopped": False,
        "refused": False,
        "error": None,
        "coverage": None,
        "passages": [],
        "first_event_at_ms": None,
        "total_ms": None,
    }
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=300.0) as c:
            with c.stream("POST", f"{API_BASE}/answer",
                          json={"q": q, "top_k": top_k, "skip_nli": skip_nli}) as r:
                r.raise_for_status()
                current_event = None
                for line in r.iter_lines():
                    if result["first_event_at_ms"] is None and line.strip():
                        result["first_event_at_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                    if not line:
                        current_event = None
                        continue
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and current_event:
                        data_str = line.split(":", 1)[1].strip()
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            data = data_str
                        result["events"].append({"event": current_event, "data": data})
                        if current_event == "sentence":
                            result["sentences"].append(data)
                        elif current_event == "coverage":
                            result["coverage"] = data
                        elif current_event == "passages":
                            result["passages"] = data
                        elif current_event == "stop":
                            result["stopped"] = True
                        elif current_event == "refused":
                            result["refused"] = True
                        elif current_event == "error":
                            result["error"] = data
    except Exception as e:
        result["error"] = str(e)
    result["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result


def summarize(result: dict, subject: str) -> dict:
    n_ok = sum(1 for s in result["sentences"] if s.get("status") == "ok")
    n_weak = sum(1 for s in result["sentences"] if s.get("status") == "weak_support")
    n_bad = sum(1 for s in result["sentences"]
                if s.get("status") in ("unsupported", "unknown_citation"))
    n_meta = sum(1 for s in result["sentences"] if s.get("status") == "meta")
    return {
        "subject": subject,
        "query": result["query"],
        "total_ms": result["total_ms"],
        "first_event_ms": result["first_event_at_ms"],
        "n_sentences_emitted": len(result["sentences"]),
        "n_ok": n_ok,
        "n_weak_support": n_weak,
        "n_unsupported_or_unknown_cite": n_bad,
        "n_meta": n_meta,
        "stopped": result["stopped"],
        "refused": result["refused"],
        "error": result["error"],
        "passages_count": len(result["passages"]),
        "coverage": result["coverage"],
    }


def main():
    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"output_quality_{stamp}.json"

    print(f"=== Output quality test ({len(QUERIES)} queries) ===")
    print(f"API: {API_BASE}")
    print(f"Results → {out_path.name}\n")

    all_results = []
    for i, q_spec in enumerate(QUERIES, 1):
        q = q_spec["q"]
        subject = q_spec["subject"]
        print(f"[{i:>2}/{len(QUERIES)}] [{subject:13s}] {q[:60]}…", flush=True)
        result = stream_answer(q, top_k=8, skip_nli=False)
        summary = summarize(result, subject)
        all_results.append({"summary": summary, "full": result})

        verdict_bits = []
        verdict_bits.append(f"ok={summary['n_ok']}")
        if summary["n_weak_support"]:
            verdict_bits.append(f"weak={summary['n_weak_support']}")
        if summary["n_unsupported_or_unknown_cite"]:
            verdict_bits.append(f"BAD={summary['n_unsupported_or_unknown_cite']}")
        if summary["stopped"]:
            verdict_bits.append("STOPPED")
        if summary["refused"]:
            verdict_bits.append("REFUSED")
        if summary["error"]:
            verdict_bits.append(f"ERR={summary['error']}")
        print(f"        → {' | '.join(verdict_bits)}  ({summary['total_ms']/1000:.1f}s)")

    out_path.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\nFull results: {out_path}")

    # Aggregate
    by_subject: dict = {}
    for r in all_results:
        s = r["summary"]
        by_subject.setdefault(s["subject"], {"queries": 0, "good": 0, "bad": 0, "stopped": 0, "refused": 0})
        by_subject[s["subject"]]["queries"] += 1
        if s["stopped"]:
            by_subject[s["subject"]]["stopped"] += 1
        if s["refused"]:
            by_subject[s["subject"]]["refused"] += 1
        if s["n_ok"] >= 2 and s["n_unsupported_or_unknown_cite"] == 0 and not s["stopped"]:
            by_subject[s["subject"]]["good"] += 1
        else:
            by_subject[s["subject"]]["bad"] += 1

    print("\n=== Per-subject summary ===")
    print(f"{'subject':15s} {'qs':>3} {'good':>5} {'bad':>5} {'stop':>5} {'refused':>7}")
    for subj, stats in sorted(by_subject.items()):
        print(f"  {subj:13s} {stats['queries']:>3d} {stats['good']:>5d} "
              f"{stats['bad']:>5d} {stats['stopped']:>5d} {stats['refused']:>7d}")


if __name__ == "__main__":
    main()
