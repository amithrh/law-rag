#!/usr/bin/env python3
"""Citation-correctness audit of v5 outputs.

Hits /answer for 4 queries, captures EVERY sentence/suppressed/passages/
sources/relevance/coverage event in JSONL form for offline analysis.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

API_URL = "http://localhost:8000/answer"

QUERIES = [
    "section 138 NI Act notice 30 days time limit",
    "my landlord is not returning my deposit money",
    "GST input tax credit denied by department",
    "can I deduct home loan interest from my income tax",
]


def capture(query: str, out_path: Path, timeout_s: int = 180) -> dict:
    data = json.dumps({"q": query}).encode()
    req = urllib.request.Request(
        API_URL, data=data, headers={"Content-Type": "application/json"},
    )
    bucket: dict = {
        "query": query,
        "sentences": [],
        "suppressed": 0,
        "refused": None,
        "relevance": None,
        "coverage": None,
        "sources": [],
        "passages": [],
        "stop": None,
        "took_s": 0.0,
        "error": None,
    }
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as f:
            event_name = None
            for raw in f:
                line = raw.decode(errors="replace").rstrip()
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    payload = line.split(":", 1)[1].strip()
                    if not payload:
                        continue
                    try:
                        d = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if event_name == "sentence":
                        bucket["sentences"].append(d)
                    elif event_name == "suppressed":
                        bucket["suppressed"] += 1
                    elif event_name == "refused":
                        bucket["refused"] = d
                    elif event_name == "relevance":
                        bucket["relevance"] = d
                    elif event_name == "coverage":
                        bucket["coverage"] = d
                    elif event_name == "passages":
                        bucket["passages"] = d
                    elif event_name == "sources":
                        bucket["sources"] = d
                    elif event_name == "stop":
                        bucket["stop"] = d
    except Exception as e:
        bucket["error"] = f"{type(e).__name__}: {e}"
    bucket["took_s"] = round(time.time() - t0, 1)
    with out_path.open("a") as f:
        f.write(json.dumps(bucket, ensure_ascii=False) + "\n")
    return bucket


def main() -> None:
    out_path = Path("/tmp/audit_v5.jsonl")
    out_path.unlink(missing_ok=True)
    print(f"writing to {out_path}", flush=True)
    for q in QUERIES:
        print(f"\n=== {q!r} ===", flush=True)
        r = capture(q, out_path)
        if r["error"]:
            print(f"ERROR {r['error']}", flush=True)
            continue
        n_sent = len(r["sentences"])
        n_ok = sum(1 for s in r["sentences"] if s["status"] == "ok")
        n_weak = sum(1 for s in r["sentences"] if s["status"] == "weak_support")
        n_meta = sum(1 for s in r["sentences"] if s["status"] == "meta")
        cov = r.get("coverage") or {}
        rel = r.get("relevance") or {}
        print(
            f"  sent={n_sent} ok={n_ok} weak={n_weak} meta={n_meta} "
            f"suppressed={r['suppressed']} sources={len(r['sources'])} "
            f"passages={len(r['passages'])} cov={cov.get('top_rerank') or cov.get('top_score')} "
            f"rel_score={rel.get('score')} rel_verdict={rel.get('verdict')} "
            f"took={r['took_s']}s",
            flush=True,
        )


if __name__ == "__main__":
    main()
