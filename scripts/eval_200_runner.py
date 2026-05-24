#!/usr/bin/env python3
"""Run the 200-query realistic eval against /answer.

Streams each query through the SSE endpoint and captures everything
needed for downstream failure analysis:
  - relevance verdict + score
  - per-sentence statuses (ok / weak_support / unsupported / meta)
  - top sources (anchor + title + source_type)
  - LLM-emitted body (all sentence texts concatenated)
  - refusal reason if refused
  - expansion variants (if available via debug)
  - timing

Designed for offline failure-mode analysis — see scripts/analyze_eval_200.py.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/eval_200_runner.py
  PYTHONPATH=. .venv/bin/python scripts/eval_200_runner.py --limit 10  # smoke
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
API_URL = "http://localhost:8000/answer"
SC_ANCHOR_RE = re.compile(r"^\d{4}-(insc|\d+-\d+)")
HC_ANCHOR_RE = re.compile(r"^hc/")


def load_queries(folder: Path) -> list[dict]:
    """Load all *.jsonl files in folder, tag with persona from filename."""
    rows: list[dict] = []
    for fp in sorted(folder.glob("*.jsonl")):
        persona = fp.stem
        with fp.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception as e:
                    print(f"  skipping bad line in {fp.name}: {e}",
                          file=sys.stderr)
                    continue
                d["persona"] = persona
                rows.append(d)
    # Dedupe by query text (case-insensitive)
    seen: dict[str, dict] = {}
    for r in rows:
        key = r["query"].strip().lower()
        if key not in seen:
            seen[key] = r
    return list(seen.values())


def classify_anchor(anchor: str) -> str:
    if not anchor:
        return "unknown"
    if HC_ANCHOR_RE.match(anchor):
        return "hc_judgment"
    if SC_ANCHOR_RE.match(anchor):
        return "sc_judgment"
    if "/" in anchor:
        return "bare_act"
    return "unknown"


def stream_answer(query: str, timeout_s: int = 120) -> dict:
    """Hit /answer and aggregate."""
    payload = json.dumps({"q": query, "top_k": 8}).encode()
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={"Content-Type": "application/json",
                 "Accept": "text/event-stream"},
    )
    result: dict = {
        "query": query,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "events": {},
        "sentences": [],          # list of {text, status, citations, entailment_score, reason}
        "n_sentences": 0,
        "n_ok": 0,
        "n_weak": 0,
        "n_unsupported": 0,
        "n_meta": 0,
        "suppressed": 0,
        "refused": False,
        "refused_reason": None,
        "relevance_score": None,
        "relevance_verdict": None,
        "coverage": None,
        "sources": [],            # list of {index, anchor, title, source_type}
        "source_counts": {"bare_act": 0, "sc_judgment": 0, "hc_judgment": 0},
        "took_s": None,
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
                    payload_str = line.split(":", 1)[1].strip()
                    try:
                        d = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    result["events"].setdefault(event_name or "?", 0)
                    result["events"][event_name or "?"] += 1
                    if event_name == "sentence":
                        result["n_sentences"] += 1
                        status = d.get("status", "")
                        sent_rec = {
                            "text": d.get("text", ""),
                            "status": status,
                            "citations": d.get("citations", []),
                            "entailment_score": d.get("entailment_score"),
                            "reason": d.get("reason", ""),
                        }
                        result["sentences"].append(sent_rec)
                        if status == "ok":
                            result["n_ok"] += 1
                        elif status == "weak_support":
                            result["n_weak"] += 1
                        elif status in ("unsupported", "unknown_citation"):
                            result["n_unsupported"] += 1
                        elif status == "meta":
                            result["n_meta"] += 1
                    elif event_name == "suppressed":
                        result["suppressed"] += 1
                    elif event_name == "refused":
                        result["refused"] = True
                        result["refused_reason"] = d.get("message")
                    elif event_name == "relevance":
                        result["relevance_score"] = d.get("score")
                        result["relevance_verdict"] = d.get("verdict")
                    elif event_name == "coverage":
                        result["coverage"] = d
                    elif event_name == "passages" or event_name == "sources":
                        items = d if isinstance(d, list) else []
                        for s in items:
                            if not isinstance(s, dict):
                                continue
                            anchor = s.get("anchor", "") or ""
                            stype = classify_anchor(anchor)
                            result["sources"].append({
                                "index": s.get("index"),
                                "anchor": anchor,
                                "title": (s.get("title") or "")[:80],
                                "court": s.get("court", ""),
                                "source_type": stype,
                            })
                            if stype in result["source_counts"]:
                                result["source_counts"][stype] += 1
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    result["took_s"] = round(time.time() - t0, 1)
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--queries-dir", default=str(ROOT / "data/eval_200"))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--prefix", default="eval_200",
                   help="output filename prefix (default: eval_200). "
                        "Use 'eval_500_baseline', 'eval_500_postrerank', "
                        "'eval_500_postdistill', 'eval_500_finalhc' for "
                        "the 4-run sweep.")
    p.add_argument("--out", default=None,
                   help="explicit output JSONL path (overrides --prefix)")
    p.add_argument("--resume-from", default=None,
                   help="existing JSONL — queries present here are skipped "
                        "(matched by lowercased query text). New rows are "
                        "APPENDED to --out (or to --resume-from itself if "
                        "--out is omitted).")
    args = p.parse_args()

    queries = load_queries(Path(args.queries_dir))
    if args.limit:
        queries = queries[:args.limit]
    print(f"loaded {len(queries)} queries", flush=True)

    # Resume logic: read --resume-from, build skip set, append new rows.
    done_keys: set[str] = set()
    if args.resume_from:
        rf = Path(args.resume_from)
        if rf.exists():
            with rf.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        done_keys.add(json.loads(line)["query"].strip().lower())
                    except Exception:
                        continue
        print(f"resume: {len(done_keys)} queries already done", flush=True)

    before = len(queries)
    queries = [q for q in queries if q["query"].strip().lower() not in done_keys]
    print(f"after dedup vs resume-from: {len(queries)}/{before} queries remain",
          flush=True)

    # If --out not given but --resume-from is, append to resume-from
    if args.out:
        out_path = Path(args.out)
    elif args.resume_from:
        out_path = Path(args.resume_from)
    else:
        out_path = (ROOT / "data/processed" /
                    f"{args.prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    file_mode = "a" if done_keys else "w"
    print(f"writing to {out_path} (mode={file_mode!r})", flush=True)

    t_overall = time.time()
    n_ok_cosine = 0
    n_refused = 0
    n_error = 0
    n_act_hit = 0
    with out_path.open(file_mode) as f:
        for i, qrow in enumerate(queries, 1):
            q = qrow["query"]
            r = stream_answer(q)
            r["persona"] = qrow.get("persona")
            r["expected_category"] = qrow.get("expected_category")
            r["expected_act_hint"] = qrow.get("expected_act_hint")
            r["is_accused_subject"] = qrow.get("is_accused_subject", False)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()

            if r.get("error"):
                n_error += 1
            elif r.get("refused"):
                n_refused += 1
            elif r.get("relevance_verdict") == "ok":
                n_ok_cosine += 1
            if r["source_counts"].get("bare_act", 0) > 0:
                n_act_hit += 1

            v = (r.get("relevance_verdict") or "?")[:3]
            sc = r["source_counts"].get("sc_judgment", 0)
            hc = r["source_counts"].get("hc_judgment", 0)
            act = r["source_counts"].get("bare_act", 0)
            qshort = q[:60] + ("…" if len(q) > 60 else "")
            mark = "REF" if r.get("refused") else ("ERR" if r.get("error") else v)
            print(f"  [{i:>3}/{len(queries)}] {qrow['persona'][:8]:<8} "
                  f"{mark:<4} t={r['took_s']:>5.1f}s "
                  f"act={act}/sc={sc}/hc={hc} "
                  f"q={qshort!r}",
                  flush=True)

    elapsed = (time.time() - t_overall) / 60
    print(f"\n=== Done in {elapsed:.1f} min ===")
    print(f"  cosine OK: {n_ok_cosine}/{len(queries)} "
          f"({100*n_ok_cosine/len(queries):.0f}%)")
    print(f"  refused:   {n_refused}/{len(queries)} "
          f"({100*n_refused/len(queries):.0f}%)")
    print(f"  errors:    {n_error}/{len(queries)}")
    print(f"  bare-act in sources: {n_act_hit}/{len(queries)} "
          f"({100*n_act_hit/len(queries):.0f}%)")
    print(f"  output: {out_path}")


if __name__ == "__main__":
    main()
