#!/usr/bin/env python3
"""Output-quality battery v3 — 50 natural prompts, comparison run.

This is a fixed 50-query subset of battery_v2 (every other query) so we
can compare apples-to-apples across runs of the same prompts at different
stack revisions:

  v1:     skip_ratio=0.0, llama3.1:8b on docker CPU                  → 0% pass
  v2-pre: gemma4+host-Metal, strict, no auto-cite tuning             → 17% pass
  v2-tol: ratio=0.20 + min=2 (the weakened gate Codex rejected)      → killed
  v3:     suppress-unsupported, NLI-forced auto-cite, fixed prompt   → tbd

Verdict criteria (in-slice):
  * pass: ≥ 2 OK sentences AND no stop AND weak-rate < 50%
  * stop: stop banner fired
  * fail: too few cited sentences

Verdict criteria (out-of-slice):
  * pass-refused: refused honestly
  * pass-answered: answered with ≥ 2 OK sentences (surprising but ok)
  * stop:        stop banner fired
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
API_BASE = "http://127.0.0.1:8000"

# Import the 100 queries from battery_v2 so we can't drift; take every 2nd
# query for a stratified 50-query slice.
sys.path.insert(0, str(ROOT / "scripts"))
from test_battery_v2 import QUERIES as V2_QUERIES, SLICE_SUBJECTS, _SECTION_RE, EXPECTED_SECTIONS  # type: ignore

QUERIES = V2_QUERIES[::2]
assert len(QUERIES) == 50, len(QUERIES)


def stream_answer(q: str, *, top_k: int = 8, skip_nli: bool = False) -> dict:
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


def score(result: dict, subject: str) -> dict:
    sents = result["sentences"]
    n_ok = sum(1 for s in sents if s.get("status") == "ok")
    n_weak = sum(1 for s in sents if s.get("status") == "weak_support")
    # Unsupported sentences are now suppressed from the stream — won't
    # appear in sents. We track them via the stop event payload instead.
    n_meta = sum(1 for s in sents if s.get("status") == "meta")
    n_auto = sum(1 for s in sents if s.get("auto_cited"))

    sections_seen = set()
    for s in sents:
        m = _SECTION_RE.match(s.get("text", ""))
        if m:
            sections_seen.add(m.group(1).strip().lower())
    sections_present = sections_seen & EXPECTED_SECTIONS

    cited = [s for s in sents if s.get("status") in ("ok", "weak_support")]
    cit_density = (
        sum(len(s.get("citations") or []) for s in cited) / max(1, len(cited))
    )

    in_slice = subject in SLICE_SUBJECTS
    if in_slice:
        # Pass when we got ≥2 visible cited sentences AND no stop AND
        # weak ratio not majority. An in-slice query that the
        # coverage gate honestly refuses (e.g., we don't have specific
        # online-refund e-commerce passages even though Consumer
        # Protection is in slice) counts as pass-refused — that's
        # correct behavior, not a defect.
        emitted_visible = n_ok + n_weak
        weak_ratio = n_weak / max(1, emitted_visible)
        if n_ok >= 2 and not result["stopped"] and weak_ratio < 0.5:
            verdict = "pass"
        elif result["refused"]:
            verdict = "pass-refused"
        elif result["stopped"]:
            verdict = "stop"
        else:
            verdict = "fail"
    else:
        if result["refused"]:
            verdict = "pass-refused"
        elif n_ok >= 2 and not result["stopped"]:
            verdict = "pass-answered"
        else:
            verdict = "stop"

    return {
        "subject": subject,
        "in_slice": in_slice,
        "query": result["query"],
        "verdict": verdict,
        "total_ms": result["total_ms"],
        "first_event_ms": result["first_event_at_ms"],
        "n_sentences": len(sents),
        "n_ok": n_ok,
        "n_weak": n_weak,
        "n_meta": n_meta,
        "n_auto_cited": n_auto,
        "stopped": result["stopped"],
        "refused": result["refused"],
        "error": result["error"],
        "passages_count": len(result["passages"]),
        "sections_present": sorted(sections_present),
        "citation_density": round(cit_density, 2),
    }


def main():
    # Optional label suffix lets multiple backends share the script:
    #   python scripts/test_battery_v3.py bge      → battery_v3_bge.{json,md}
    #   python scripts/test_battery_v3.py ensemble → battery_v3_ensemble.{json,md}
    # No suffix → timestamped filename as before.
    label = sys.argv[1] if len(sys.argv) > 1 else None

    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    if label:
        json_path = out_dir / f"battery_v3_{label}.json"
        md_path = out_dir / f"battery_v3_{label}.md"
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        json_path = out_dir / f"battery_v3_{stamp}.json"
        md_path = out_dir / f"battery_v3_{stamp}.md"

    print(f"=== Battery v3 ({len(QUERIES)} queries) ===")
    print(f"API: {API_BASE}\n", flush=True)

    all_results = []
    overall_t0 = time.perf_counter()
    for i, q_spec in enumerate(QUERIES, 1):
        q = q_spec["q"]
        subject = q_spec["subject"]
        print(f"[{i:>2}/{len(QUERIES)}] [{subject:13s}] {q[:62]}…", flush=True)
        result = stream_answer(q, top_k=8, skip_nli=False)
        sc = score(result, subject)
        all_results.append({"score": sc, "full": result})

        bits = [sc["verdict"]]
        bits.append(f"ok={sc['n_ok']}")
        if sc["n_weak"]:
            bits.append(f"weak={sc['n_weak']}")
        if sc["stopped"]:
            bits.append("STOP")
        if sc["refused"]:
            bits.append("REF")
        bits.append(f"{(sc['total_ms'] or 0)/1000:.0f}s")
        print(f"      → {' | '.join(bits)}", flush=True)

    overall_elapsed = time.perf_counter() - overall_t0

    json_path.write_text(json.dumps(all_results, indent=2, default=str))

    by_subject = defaultdict(list)
    for r in all_results:
        by_subject[r["score"]["subject"]].append(r["score"])

    lines = []
    lines.append(f"# Output-quality battery v3 — {len(QUERIES)} queries")
    lines.append("")
    lines.append(f"- Run at: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Total elapsed: {overall_elapsed:.0f}s ({overall_elapsed/60:.1f} min)")
    lines.append("")

    n_total = len(all_results)
    n_pass = sum(1 for r in all_results if r["score"]["verdict"].startswith("pass"))
    n_stop = sum(1 for r in all_results if r["score"]["stopped"])
    n_refused = sum(1 for r in all_results if r["score"]["refused"])
    in_slice_results = [r for r in all_results if r["score"]["in_slice"]]
    n_slice_pass = sum(1 for r in in_slice_results if r["score"]["verdict"] == "pass")

    lines.append("## Overall")
    lines.append("")
    lines.append(f"- **{n_pass}/{n_total} pass** ({100*n_pass/n_total:.0f}%) — any pass-variant")
    lines.append(f"- **{n_slice_pass}/{len(in_slice_results)} in-slice pass** ({100*n_slice_pass/max(1,len(in_slice_results)):.0f}%)")
    lines.append(f"- {n_stop} stopped, {n_refused} refused")
    lat = [r["score"]["total_ms"] for r in all_results if r["score"]["total_ms"]]
    if lat:
        lines.append(f"- Latency: median {statistics.median(lat)/1000:.1f}s")
    lines.append("")

    lines.append("## Per-subject")
    lines.append("")
    lines.append("| subject | n | pass | stop | refused | weak% | median t |")
    lines.append("|---------|---|------|------|---------|-------|----------|")
    for subj, scores in sorted(by_subject.items()):
        n = len(scores)
        n_pass_s = sum(1 for s in scores if s["verdict"].startswith("pass"))
        n_stop_s = sum(1 for s in scores if s["stopped"])
        n_ref_s = sum(1 for s in scores if s["refused"])
        n_visible = sum(s["n_ok"] + s["n_weak"] for s in scores)
        n_weak_total = sum(s["n_weak"] for s in scores)
        lat_s = [s["total_ms"] for s in scores if s["total_ms"]]
        median_lat = statistics.median(lat_s) / 1000 if lat_s else 0
        lines.append(
            f"| {subj} | {n} | {n_pass_s} | {n_stop_s} | {n_ref_s} | "
            f"{100*n_weak_total/max(1,n_visible):.0f}% | "
            f"{median_lat:.0f}s |"
        )

    lines.append("")
    lines.append("## Failures (stop / fail)")
    lines.append("")
    for r in all_results:
        s = r["score"]
        if s["verdict"].startswith("pass"):
            continue
        marker = "STOP" if s["stopped"] else "FAIL"
        lines.append(f"- **{marker}** [{s['subject']}] {s['query'][:90]}")
        lines.append(
            f"  - ok={s['n_ok']}  weak={s['n_weak']}  meta={s['n_meta']}  "
            f"auto={s['n_auto_cited']}  t={s['total_ms']/1000:.0f}s"
        )

    md_path.write_text("\n".join(lines))
    print()
    print("\n".join(lines))
    print()
    print(f"Full trace: {json_path}")
    print(f"Scorecard : {md_path}")


if __name__ == "__main__":
    main()
