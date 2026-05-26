#!/usr/bin/env python3
"""Timed 100-question /answer eval using the SSE `timing` event.

This runner is for product gating, not model benchmarking:
  - stage latency: preflight, route, retrieval, prompt, LLM, verifier, relevance
  - user outcome: refused/error/relevance verdict/suppressed sentences
  - matter route: category, urgency, legal regime, action pack
  - expected Act hit: did cited source metadata contain the expected Act family?

Usage:
  PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py --api http://localhost:8001
  PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py --limit 10 --api http://localhost:8001
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent


ACT_ALIASES: dict[str, tuple[str, ...]] = {
    "BNSS": ("bnss", "bharatiya nagarik suraksha", "nagarik suraksha"),
    "BNS": ("bns", "bharatiya nyaya", "nyaya sanhita"),
    "BSA": ("bsa", "bharatiya sakshya", "sakshya adhiniyam"),
    "CrPC": ("crpc", "criminal procedure", "code of criminal procedure"),
    "IPC": ("ipc", "indian penal", "penal code"),
    "Evidence Act": ("evidence act", "indian evidence", "sakshya"),
    "Consumer Protection Act": ("consumer protection", "cpa-2019"),
    "Information Technology Act": ("information technology", "it-act", "it act"),
    "Shariat Act": ("shariat", "muslim personal law"),
    "Street Vendors Act": ("street vendors", "street vendor"),
    "Article 21": ("article 21", "hussainara"),
    "Senior Citizens Act": ("senior citizens", "parents and senior citizens", "mwp-2007"),
    "PWDVA": ("domestic violence", "pwdva", "protection of women"),
    "POCSO": ("pocso", "children from sexual offences"),
    "SC/ST POA Act": ("scheduled castes", "scheduled tribes", "poa", "atrocities"),
    "NI Act": ("negotiable instruments", "ni act"),
    "Payment of Wages": ("payment of wages", "code on wages", "wages"),
    "Maternity Benefit Act": ("maternity benefit",),
    "EPF Act": ("epf", "provident fund"),
    "RERA": ("rera", "real estate"),
    "RTI Act": ("right to information", "rti"),
    "Legal Services Authorities Act": ("legal services authorities", "nalsa"),
    "Motor Vehicles Act": ("motor vehicles", "mact"),
    "Hindu Succession Act": ("hindu succession",),
    "Indian Succession Act": ("indian succession",),
    "Registration Act": ("registration act",),
    "Transfer of Property Act": ("transfer of property", "tpa"),
    "Limitation Act": ("limitation act",),
    "NDPS Act": ("ndps", "narcotic"),
    "SARFAESI": ("sarfaesi",),
    "IBC": ("insolvency", "bankruptcy", "ibc"),
}


def load_eval_rows(queries_dir: Path, *, limit: int, seed: int) -> list[dict[str, Any]]:
    by_persona: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(queries_dir.glob("*.jsonl")):
        persona = path.stem
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row.setdefault("persona", persona)
            by_persona[row["persona"]].append(row)

    rng = random.Random(seed)
    for rows in by_persona.values():
        rng.shuffle(rows)

    selected: list[dict[str, Any]] = []
    personas = sorted(by_persona)
    cursor = {p: 0 for p in personas}
    while len(selected) < limit:
        progressed = False
        for persona in personas:
            idx = cursor[persona]
            rows = by_persona[persona]
            if idx >= len(rows):
                continue
            selected.append(rows[idx])
            cursor[persona] += 1
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def stream_answer(api: str, query: str, *, timeout_s: int) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/answer",
        data=json.dumps({"q": query, "top_k": 8}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    out: dict[str, Any] = {
        "events": Counter(),
        "sentences": [],
        "suppressed_count": 0,
        "refused": None,
        "error": None,
        "relevance": None,
        "coverage": None,
        "passages": [],
        "sources": [],
        "matter_route": None,
        "timing": None,
        "wall_ms": None,
    }
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            event_name = "message"
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                if not line:
                    continue
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    data = payload
                out["events"][event_name] += 1
                if event_name == "matter_route":
                    out["matter_route"] = data
                elif event_name == "coverage":
                    out["coverage"] = data
                elif event_name == "passages":
                    out["passages"] = data if isinstance(data, list) else []
                elif event_name == "sentence":
                    out["sentences"].append(data)
                elif event_name == "suppressed":
                    out["suppressed_count"] += 1
                elif event_name == "refused":
                    out["refused"] = data
                elif event_name == "sources":
                    out["sources"] = data if isinstance(data, list) else []
                elif event_name == "relevance":
                    out["relevance"] = data
                elif event_name == "timing":
                    out["timing"] = data
                elif event_name == "error":
                    out["error"] = data
    except urllib.error.HTTPError as e:
        out["error"] = {"message": f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}"}
    except Exception as e:
        out["error"] = {"message": f"{type(e).__name__}: {e}"}
    out["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["events"] = dict(out["events"])
    return out


def expected_act_keys(hint: str | None) -> list[str]:
    if not hint:
        return []
    h = hint.lower()
    keys = [
        canonical
        for canonical, aliases in ACT_ALIASES.items()
        if _alias_in_text(canonical.lower(), h) or any(_alias_in_text(alias, h) for alias in aliases)
    ]
    return sorted(set(keys))


def _alias_in_text(alias: str, text: str) -> bool:
    if not alias:
        return False
    if " " in alias or "-" in alias:
        return alias in text
    return re_search_word(alias, text)


def re_search_word(term: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def expected_act_hit(keys: list[str], sources: list[dict[str, Any]], passages: list[dict[str, Any]]) -> bool | None:
    if not keys:
        return None
    blob = " ".join(
        str(item.get("title", "")) + " " + str(item.get("anchor", "")) + " " + str(item.get("citation", ""))
        for item in [*sources, *passages]
        if isinstance(item, dict)
    ).lower()
    if not blob:
        return False
    for key in keys:
        aliases = ACT_ALIASES.get(key, (key.lower(),))
        if any(_alias_in_text(alias, blob) for alias in aliases):
            return True
    return False


def flatten_row(eval_row: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    route = observed.get("matter_route") or {}
    timing = observed.get("timing") or {}
    relevance = observed.get("relevance") or {}
    refused = observed.get("refused")
    error = observed.get("error")
    expected_keys = expected_act_keys(eval_row.get("expected_act_hint"))
    hit = expected_act_hit(expected_keys, observed.get("sources") or [], observed.get("passages") or [])
    sentences = observed.get("sentences") or []
    return {
        "query": eval_row.get("query"),
        "persona": eval_row.get("persona"),
        "expected_category": eval_row.get("expected_category"),
        "expected_act_hint": eval_row.get("expected_act_hint"),
        "expected_act_keys": expected_keys,
        "expected_act_hit": hit,
        "route_category": route.get("category"),
        "route_label": route.get("label"),
        "route_urgency": route.get("urgency"),
        "route_confidence": route.get("confidence"),
        "legal_regime": route.get("legal_regime"),
        "action_pack_id": (route.get("action_pack") or {}).get("id") if route.get("action_pack") else None,
        "red_flags": route.get("red_flags") or [],
        "refused": bool(refused),
        "refused_reason": refused.get("reason") if isinstance(refused, dict) else None,
        "error": error.get("message") if isinstance(error, dict) else error,
        "relevance_verdict": relevance.get("verdict"),
        "relevance_score": relevance.get("score"),
        "sentence_count": len(sentences),
        "ok_sentences": sum(1 for s in sentences if s.get("status") == "ok"),
        "weak_sentences": sum(1 for s in sentences if s.get("status") == "weak_support"),
        "suppressed_count": observed.get("suppressed_count", 0),
        "source_count": len(observed.get("sources") or []),
        "top_sources": [
            {
                "title": s.get("title"),
                "anchor": s.get("anchor"),
                "court": s.get("court"),
                "citation": s.get("citation"),
            }
            for s in (observed.get("sources") or observed.get("passages") or [])[:5]
            if isinstance(s, dict)
        ],
        "timing": timing,
        "wall_ms": observed.get("wall_ms"),
        "events": observed.get("events"),
    }


def percentile(values: list[float], pct: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    idx = (len(vals) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value / 1000:.1f}s"


def write_report(rows: list[dict[str, Any]], out: Path, report: Path) -> None:
    scored_act = [r for r in rows if r["expected_act_hit"] is not None]
    act_hits = sum(1 for r in scored_act if r["expected_act_hit"])
    refused = sum(1 for r in rows if r["refused"])
    errors = sum(1 for r in rows if r["error"])
    verdicts = Counter(r["relevance_verdict"] or ("refused" if r["refused"] else "no_relevance") for r in rows)
    routes = Counter(r["route_category"] or "unknown" for r in rows)
    action_packs = Counter(r["action_pack_id"] or "none" for r in rows)

    stage_names = [
        "total_ms",
        "matter_route_ms",
        "llm_preflight_ms",
        "query_expand_ms",
        "retrieval_single_query_ms",
        "single_expanded_retrieval_ms",
        "variant_candidate_retrieval_ms",
        "variant_rerank_ms",
        "retrieval_ms",
        "prompt_build_ms",
        "llm_stream_ms",
        "verification_ms",
        "relevance_ms",
    ]
    lines = [
        "# Timed 100-question eval",
        "",
        f"Rows: {len(rows)}",
        f"Input/output: `{out}`",
        "",
        "## Outcome",
        "",
        f"- Refused: {refused}/{len(rows)}",
        f"- Errors: {errors}/{len(rows)}",
        f"- Relevance verdicts: {dict(verdicts)}",
        f"- Expected Act hit: {act_hits}/{len(scored_act)} ({(act_hits / len(scored_act) * 100) if scored_act else 0:.1f}%)",
        "",
        "## Latency",
        "",
        "| stage | p50 | p90 | max |",
        "| --- | ---: | ---: | ---: |",
    ]
    for stage in stage_names:
        vals = [
            (r.get("timing") or {}).get(stage)
            for r in rows
            if isinstance(r.get("timing"), dict)
        ]
        vals = [float(v) for v in vals if isinstance(v, int | float)]
        lines.append(
            f"| {stage} | {fmt_ms(percentile(vals, 0.50))} | "
            f"{fmt_ms(percentile(vals, 0.90))} | {fmt_ms(max(vals) if vals else None)} |"
        )

    lines.extend([
        "",
        "## Route Distribution",
        "",
        "| route | count |",
        "| --- | ---: |",
    ])
    for route, count in routes.most_common():
        lines.append(f"| {route} | {count} |")

    lines.extend([
        "",
        "## Action Packs",
        "",
        "| action_pack | count |",
        "| --- | ---: |",
    ])
    for pack, count in action_packs.most_common():
        lines.append(f"| {pack} | {count} |")

    worst_total = sorted(
        rows,
        key=lambda r: (r.get("timing") or {}).get("total_ms") or r.get("wall_ms") or 0,
        reverse=True,
    )[:15]
    lines.extend([
        "",
        "## Slowest Rows",
        "",
        "| total | retrieval | llm | verify | route | query |",
        "| ---: | ---: | ---: | ---: | --- | --- |",
    ])
    for r in worst_total:
        t = r.get("timing") or {}
        q = (r["query"] or "").replace("|", " ")[:90]
        lines.append(
            f"| {fmt_ms(t.get('total_ms') or r.get('wall_ms'))} | "
            f"{fmt_ms(t.get('retrieval_ms'))} | {fmt_ms(t.get('llm_stream_ms'))} | "
            f"{fmt_ms(t.get('verification_ms'))} | {r.get('route_category')} | {q} |"
        )

    misses = [r for r in scored_act if r["expected_act_hit"] is False][:20]
    lines.extend([
        "",
        "## Expected-Act Misses",
        "",
        "| persona | expected | route | query | top source |",
        "| --- | --- | --- | --- | --- |",
    ])
    for r in misses:
        source = r["top_sources"][0]["title"] if r["top_sources"] else ""
        q = (r["query"] or "").replace("|", " ")[:90]
        expected = ", ".join(r["expected_act_keys"])
        lines.append(
            f"| {r.get('persona')} | {expected} | {r.get('route_category')} | {q} | {source} |"
        )

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--queries-dir", type=Path, default=ROOT / "data" / "eval_500")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260525)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = args.out or ROOT / "data" / "processed" / f"timed_eval_100_{stamp}.jsonl"
    report = args.report or ROOT / "data" / "processed" / f"timed_eval_100_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows_in = load_eval_rows(args.queries_dir, limit=args.limit, seed=args.seed)
    if not rows_in:
        raise SystemExit(f"no eval rows found under {args.queries_dir}")

    print(f"=== timed eval: {len(rows_in)} queries -> {out} ===", flush=True)
    rows: list[dict[str, Any]] = []
    with out.open("w", encoding="utf-8") as f:
        for idx, eval_row in enumerate(rows_in, 1):
            observed = stream_answer(args.api, eval_row["query"], timeout_s=args.timeout_s)
            row = flatten_row(eval_row, observed)
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            timing = row.get("timing") or {}
            outcome = "ERR" if row["error"] else "REF" if row["refused"] else row["relevance_verdict"] or "NO_REL"
            route_name = row.get("route_category") or "unknown"
            print(
                f"[{idx:03}/{len(rows_in)}] {outcome:<7} "
                f"{fmt_ms(timing.get('total_ms') or row.get('wall_ms')):>6} "
                f"retr={fmt_ms(timing.get('retrieval_ms')):>6} "
                f"llm={fmt_ms(timing.get('llm_stream_ms')):>6} "
                f"route={route_name:<26} "
                f"act_hit={row.get('expected_act_hit')} "
                f"q={row['query'][:70]!r}",
                flush=True,
            )

    write_report(rows, out, report)
    print(f"\nreport: {report}", flush=True)


if __name__ == "__main__":
    main()
