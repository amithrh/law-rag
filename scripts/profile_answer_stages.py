#!/usr/bin/env python3
"""Per-stage SSE timing profile for /answer.

Stages measured (wall-clock, monotonic):
  S1 retrieval+expansion:    t0 → first 'passages' event
  S2 rerank+LLM cold-start:  'passages' → first 'sentence' event
  S3 LLM stream + verifier:  first 'sentence' → last 'sentence'
  S4 relevance+disclaimer:   last 'sentence' → final event (disclaimer)
"""
from __future__ import annotations

import json
import time
import urllib.request

API_URL = "http://localhost:8000/answer"

QUERIES = [
    "my landlord is not returning my deposit money",
    "section 138 NI Act notice 30 days time limit",
    "my husband is beating me what can I do",
]


def profile(query: str, timeout_s: int = 180) -> dict:
    data = json.dumps({"q": query}).encode()
    req = urllib.request.Request(
        API_URL, data=data, headers={"Content-Type": "application/json"},
    )

    t0 = time.monotonic()
    t_first_passages = None
    t_first_sentence = None
    t_last_sentence = None
    t_final = None
    n_sentences = 0
    refused = False

    with urllib.request.urlopen(req, timeout=timeout_s) as f:
        event_name = None
        for raw in f:
            now = time.monotonic()
            line = raw.decode(errors="replace").rstrip()
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                if event_name == "passages" and t_first_passages is None:
                    t_first_passages = now
                elif event_name == "sentence":
                    if t_first_sentence is None:
                        t_first_sentence = now
                    t_last_sentence = now
                    n_sentences += 1
                elif event_name == "refused":
                    refused = True
                elif event_name == "disclaimer":
                    t_final = now
                # Always update t_final on any event so we capture the
                # last seen event timestamp even if disclaimer is missing.
                t_final = now

    # Fall-back: if no sentences fired (refused), set last==first==passages
    if t_first_sentence is None:
        t_first_sentence = t_first_passages or t_final
        t_last_sentence = t_first_sentence

    return {
        "query": query,
        "refused": refused,
        "n_sentences": n_sentences,
        "S1_retrieval_expand": (t_first_passages - t0) if t_first_passages else None,
        "S2_rerank_llm_cold": (
            (t_first_sentence - t_first_passages)
            if (t_first_sentence and t_first_passages) else None
        ),
        "S3_llm_stream_verify": (
            (t_last_sentence - t_first_sentence)
            if (t_last_sentence and t_first_sentence) else None
        ),
        "S4_relevance_disclaim": (
            (t_final - t_last_sentence)
            if (t_final and t_last_sentence) else None
        ),
        "total": (t_final - t0) if t_final else None,
    }


def fmt(x):
    return f"{x:>6.2f}s" if x is not None else "  n/a "


def main():
    rows = []
    for q in QUERIES:
        r = profile(q)
        rows.append(r)
        print(json.dumps(r), flush=True)

    print()
    print(f"{'query':<55} {'S1':>8} {'S2':>8} {'S3':>8} {'S4':>8} {'TOT':>8}  sents")
    for r in rows:
        q = r["query"][:54]
        print(
            f"{q:<55} "
            f"{fmt(r['S1_retrieval_expand'])} "
            f"{fmt(r['S2_rerank_llm_cold'])} "
            f"{fmt(r['S3_llm_stream_verify'])} "
            f"{fmt(r['S4_relevance_disclaim'])} "
            f"{fmt(r['total'])}  "
            f"{r['n_sentences']:>3}"
        )


if __name__ == "__main__":
    main()
