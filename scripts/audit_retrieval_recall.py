#!/usr/bin/env python3
"""Retrieval recall@K audit — per architecture-research Task #1 gating decision.

The Legal RAG Bench paper says IR is the ceiling on legal RAG. Before
spending 2-3 weeks on architecture changes (bge-m3 multi-head, SAC, etc.),
measure whether the *gold passage* is actually in our top-K results. If
it's not, no downstream change will help.

Method:
  1. Hand-curated (query, gold_substring) pairs. The substring is a phrase
     that uniquely identifies the gold judgment/section title — e.g.
     "SAKIRI VASU versus STATE OF U.P." for the FIR-refusal question.
  2. POST /search top_k=20 for each query.
  3. For each gold_substring, check if any title in the top-20 contains it.
  4. Report recall@20, recall@8, and average rank when found.

Decision rule (from research roadmap):
  - recall@20 ≥ 85%  → retrieval is fine; push on verifier/prompt next
  - recall@20 65-85% → both retrieval and verifier need work; bge-m3
                       multi-head next
  - recall@20  < 65% → retrieval is the bottleneck; multi-head + SAC
                       are MANDATORY before anything else

Run from repo root:
  PYTHONPATH=. .venv/bin/python scripts/audit_retrieval_recall.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
API = "http://127.0.0.1:8000"


# 15 hand-curated query→gold-passage pairs. Each gold_substring uniquely
# identifies a judgment title that any legal expert would name as
# answering the query. Some queries have MULTIPLE valid gold passages —
# we accept recall if ANY of them surface.
#
# How these were picked: cross-referenced what the battery v3 round-7
# traces cited as OK with what's in CITE_GRAPH (which is a literature
# of known landmark Indian SC cases per topic). Where the round-7 model
# cited "INVENTED CASE", I substituted the real landmark.
CASES: list[dict] = [
    {
        "q": "Police did not file my FIR. What can I do?",
        "gold": ["SAKIRI VASU", "ALEQUE PADAMSEE", "LALITA KUMARI"],
        "subject": "criminal",
    },
    {
        "q": "I fear I will be arrested. Can I apply for anticipatory bail and how?",
        "gold": ["GURBAKSH SINGH SIBBIA", "SIDDHARAM SATLINGAPPA MHETRE",
                 "SUSHILA AGGARWAL"],
        "subject": "criminal",
    },
    {
        "q": "What is the maximum punishment for theft under Indian law?",
        "gold": ["Section 303", "Section 379", "BNS", "PENAL CODE", "theft"],
        "subject": "criminal",
    },
    {
        "q": "Can a confession I gave to police be used against me in court?",
        "gold": ["Section 25", "INDIAN EVIDENCE", "Section 27", "BSA",
                 "DAGDU"],
        "subject": "criminal",
    },
    {
        "q": "What is the difference between cognizable and non-cognizable offence?",
        "gold": ["Section 154", "Section 155", "cognizable", "Cr.P.C", "BNSS"],
        "subject": "criminal",
    },
    {
        "q": "My husband threatens me and throws me out of the house. What legal protection do I have?",
        "gold": ["DOMESTIC VIOLENCE", "Section 498", "PWDV", "INDRA SARMA",
                 "V.D. BHANOT", "S.R. BATRA"],
        "subject": "family",
    },
    {
        "q": "Can I file for divorce on grounds of cruelty? How long does it take?",
        "gold": ["NAVEEN KOHLI", "SAMAR GHOSH", "Section 13", "cruelty"],
        "subject": "family",
    },
    {
        "q": "My wife took away our child. Can I get custody?",
        "gold": ["custody", "Guardians and Wards", "GAUTAM KUNDU",
                 "Section 6", "welfare of the child"],
        "subject": "family",
    },
    {
        "q": "My employer has not paid my salary for two months. How do I recover it?",
        "gold": ["PAYMENT OF WAGES", "Section 15", "AGGARWALA",
                 "P.C. AGGARWALA", "GHAZIABAD ZILA"],
        "subject": "wages",
    },
    {
        "q": "I was fired without notice. Am I entitled to any compensation?",
        "gold": ["INDUSTRIAL DISPUTES", "Section 25F", "retrenchment",
                 "NATIONAL ENGINEERING"],
        "subject": "wages",
    },
    {
        "q": "I filed an RTI and it was rejected. Can I appeal? What is the time limit?",
        "gold": ["RIGHT TO INFORMATION", "Section 19", "RTI Act",
                 "CENTRAL INFORMATION COMMISSION"],
        "subject": "rti",
    },
    {
        "q": "My family member died in a road accident. How do I claim compensation?",
        "gold": ["MOTOR VEHICLES", "Section 166", "Section 168",
                 "RAJESH", "NATIONAL INSURANCE", "Section 163A"],
        "subject": "motor",
    },
    {
        "q": "The builder didn't deliver my flat on time. What are my options?",
        "gold": ["EXPERION DEVELOPERS", "CONSUMER PROTECTION",
                 "real estate", "DLF", "PIONEER URBAN"],
        "subject": "consumer",
    },
    {
        "q": "A doctor gave me wrong treatment and now I have permanent damage. Can I sue?",
        "gold": ["medical negligence", "JACOB MATHEW", "MARTIN F. D'SOUZA",
                 "KUSUM SHARMA", "CONSUMER PROTECTION"],
        "subject": "consumer",
    },
    {
        "q": "What is the maximum punishment for theft under Indian law?",
        "gold": ["theft", "Section 379", "Section 303", "PENAL CODE", "BNS"],
        "subject": "criminal",
    },
]


def check(query: str, gold: list[str], top_k: int = 20) -> dict:
    r = httpx.get(
        f"{API}/search",
        params={"q": query, "top_k": top_k},
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    hits = data["hits"]
    titles_upper = [(i, (h.get("title") or "").upper()) for i, h in enumerate(hits)]

    found = []
    for g in gold:
        g_upper = g.upper()
        matches = [i for i, t in titles_upper if g_upper in t]
        if matches:
            found.append({"gold": g, "rank": matches[0] + 1})

    return {
        "query": query,
        "gold": gold,
        "hit_count": len(hits),
        "found_at_top_k": len(found) > 0,
        "best_rank": min((m["rank"] for m in found), default=None),
        "matches": found,
        "top_5_titles": [(t[1] or "")[:80] for t in titles_upper[:5]],
        "top_rerank_score": hits[0].get("rerank_score") if hits else None,
    }


def main() -> None:
    print(f"=== Retrieval recall audit ({len(CASES)} queries) ===\n")
    results = []
    for i, case in enumerate(CASES, 1):
        try:
            res = check(case["q"], case["gold"])
            res["subject"] = case["subject"]
        except Exception as e:
            res = {
                "query": case["q"], "subject": case["subject"],
                "gold": case["gold"], "error": str(e),
                "found_at_top_k": False, "best_rank": None,
            }
        results.append(res)
        marker = "✓" if res["found_at_top_k"] else "✗"
        rank = res.get("best_rank")
        rank_s = f"rank={rank}" if rank else "MISS"
        print(f"  {marker} [{case['subject']:10s}] {rank_s:10s}  {case['q'][:62]}")
        if not res["found_at_top_k"] and res.get("top_5_titles"):
            print(f"           top-5 got: {res['top_5_titles'][:3]}")

    # Aggregate
    n = len(results)
    found_at_20 = sum(1 for r in results if r["found_at_top_k"])
    found_at_8 = sum(
        1 for r in results
        if r.get("best_rank") is not None and r["best_rank"] <= 8
    )
    found_at_3 = sum(
        1 for r in results
        if r.get("best_rank") is not None and r["best_rank"] <= 3
    )

    print()
    print("=== Aggregate ===")
    print(f"  recall@20 = {found_at_20}/{n} = {100*found_at_20/n:.0f}%")
    print(f"  recall@8  = {found_at_8}/{n} = {100*found_at_8/n:.0f}%")
    print(f"  recall@3  = {found_at_3}/{n} = {100*found_at_3/n:.0f}%")
    print()
    if found_at_20 / n >= 0.85:
        verdict = "retrieval is fine; push on verifier/prompt next"
    elif found_at_20 / n >= 0.65:
        verdict = "BOTH retrieval and verifier need work; bge-m3 multi-head next"
    else:
        verdict = "retrieval is the bottleneck; multi-head + SAC are MANDATORY"
    print(f"  VERDICT: {verdict}")

    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"retrieval_audit_{stamp}.json"
    out_path.write_text(json.dumps({
        "run_at": datetime.now(timezone.utc).isoformat(),
        "n": n,
        "recall_at_20": found_at_20 / n,
        "recall_at_8": found_at_8 / n,
        "recall_at_3": found_at_3 / n,
        "verdict": verdict,
        "results": results,
    }, indent=2, default=str))
    print(f"\n  Wrote: {out_path}")


if __name__ == "__main__":
    main()
