#!/usr/bin/env python3
"""Output-quality battery v2 — 100 natural public-user prompts.

Successor to test_output_quality.py (v1, 18 queries). v1 found that v0 of
the stack stopped 100% of answers; the fixes since (model swap to
gemma4:e4b on host Metal, think:false, preamble whitelist, lexical auto-
cite, abbreviation merge, CRLF fix, case-ref META, etc.) need broad
validation before we can claim the product works.

This is qualitative output audit — not a unit test. Each query is the way
a layperson would actually phrase the question (broken English, mixed
register, missing context, hypotheticals). We measure:

  * Per-query    : sentences emitted, OK/weak/unsupported counts,
                   stopped?, refused?, latency, citation density, has the
                   5-section template, top passage subjects, auto-cite
                   usage rate.

  * Per-subject  : pass-rate (≥2 OK sentences AND no stop AND no NLI weak
                   majority), median latency, refuse-rate.

  * Overall      : a 0-100 product score factoring pass-rate, latency,
                   citation correctness, and refusal correctness.

Outputs:
  data/processed/battery_v2_<ts>.json    full per-query traces
  data/processed/battery_v2_<ts>.md      human-readable scorecard
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

# 100 queries across slice subjects + out-of-slice + edge cases.
# Each phrased the way a real Indian public user would type it.
QUERIES: list[dict] = [
    # =========== CRIMINAL (20) ===========
    {"subject": "criminal", "q": "Police did not file my FIR. What can I do?"},
    {"subject": "criminal", "q": "I fear I will be arrested. Can I apply for anticipatory bail and how?"},
    {"subject": "criminal", "q": "My friend was arrested yesterday. How do we apply for bail?"},
    {"subject": "criminal", "q": "What is the maximum punishment for theft under Indian law?"},
    {"subject": "criminal", "q": "Can a confession I gave to police be used against me in court?"},
    {"subject": "criminal", "q": "When can the High Court quash an FIR?"},
    {"subject": "criminal", "q": "What is the difference between a bailable and non-bailable offence?"},
    {"subject": "criminal", "q": "Can police arrest me without a warrant for a small fight?"},
    {"subject": "criminal", "q": "What are my rights when police arrest me?"},
    {"subject": "criminal", "q": "What is the difference between police custody and judicial custody?"},
    {"subject": "criminal", "q": "Which offences can be compounded and how?"},
    {"subject": "criminal", "q": "Someone cheated me of 5 lakh rupees. What sections apply?"},
    {"subject": "criminal", "q": "My husband and his family harass me for dowry. What is Section 498A?"},
    {"subject": "criminal", "q": "What is grievous hurt and what is the punishment?"},
    {"subject": "criminal", "q": "What is sexual harassment of women in public places under Indian law?"},
    {"subject": "criminal", "q": "What is the difference between cognizable and non-cognizable offence?"},
    {"subject": "criminal", "q": "Someone hit my car and ran away. What can I do legally?"},
    {"subject": "criminal", "q": "My phone was stolen. The police are not taking action. What now?"},
    {"subject": "criminal", "q": "Can I file a counter-FIR if the other party already filed one against me?"},
    {"subject": "criminal", "q": "What is the procedure for filing a complaint with the magistrate directly?"},

    # =========== CONSUMER (15) ===========
    {"subject": "consumer", "q": "My online order arrived broken. Can I get a refund and where do I file a complaint?"},
    {"subject": "consumer", "q": "The builder didn't deliver my flat on time. What are my options?"},
    {"subject": "consumer", "q": "A doctor gave me wrong treatment and now I have permanent damage. Can I sue?"},
    {"subject": "consumer", "q": "I bought a defective TV and the seller refuses to take it back. What can I do?"},
    {"subject": "consumer", "q": "The mobile shop sold me a phone that stopped working in a week. What are my rights?"},
    {"subject": "consumer", "q": "Amazon is denying my refund for a damaged product. What can I do?"},
    {"subject": "consumer", "q": "The advertisement promised features the product does not have. Is that illegal?"},
    {"subject": "consumer", "q": "Where do I file a consumer complaint for an amount of 2 lakhs?"},
    {"subject": "consumer", "q": "What is the time limit to file a consumer complaint?"},
    {"subject": "consumer", "q": "What are the pecuniary jurisdiction limits of District, State and National consumer forums?"},
    {"subject": "consumer", "q": "Builder is refusing to give possession even after 4 years. How do I file a real estate complaint?"},
    {"subject": "consumer", "q": "Insurance company is denying my health insurance claim. What can I do?"},
    {"subject": "consumer", "q": "Restaurant charged me service charge after I objected. Is this legal?"},
    {"subject": "consumer", "q": "Bought a new car and it has manufacturing defects. Showroom refuses replacement. Help?"},
    {"subject": "consumer", "q": "Builder promised swimming pool and gym but didn't build them. What can I do?"},

    # =========== FAMILY (15) ===========
    {"subject": "family", "q": "Can I file for divorce on grounds of cruelty? How long does it take?"},
    {"subject": "family", "q": "My wife took away our child. Can I get custody?"},
    {"subject": "family", "q": "My husband threatens me and throws me out of the house. What legal protection do I have?"},
    {"subject": "family", "q": "How much maintenance can I claim from my husband?"},
    {"subject": "family", "q": "Both my wife and I agree to divorce. What is the process for mutual consent?"},
    {"subject": "family", "q": "I have proof my husband had an affair. Can I file for divorce?"},
    {"subject": "family", "q": "I want to marry someone of a different religion. What is the procedure?"},
    {"subject": "family", "q": "My husband has secretly married another woman. What can I do?"},
    {"subject": "family", "q": "My wife refuses to live with me. Can I file restitution of conjugal rights?"},
    {"subject": "family", "q": "What is the difference between judicial separation and divorce?"},
    {"subject": "family", "q": "My marriage was forced and below age 18. Is the marriage valid?"},
    {"subject": "family", "q": "My in-laws demand more dowry. What legal action can I take?"},
    {"subject": "family", "q": "After divorce, what about my stridhan and jewellery?"},
    {"subject": "family", "q": "How is alimony calculated in India?"},
    {"subject": "family", "q": "I am separated from my wife but I want to see my child. Do I have visitation rights?"},

    # =========== WAGES (10) ===========
    {"subject": "wages", "q": "My employer has not paid my salary for two months. How do I recover it?"},
    {"subject": "wages", "q": "I was fired without notice. Am I entitled to any compensation?"},
    {"subject": "wages", "q": "I worked 6 years and quit. Am I entitled to gratuity?"},
    {"subject": "wages", "q": "My employer refuses to release my PF after I left the job. What can I do?"},
    {"subject": "wages", "q": "When am I eligible for a bonus under the Code on Wages?"},
    {"subject": "wages", "q": "My company denied me maternity leave. Is this legal?"},
    {"subject": "wages", "q": "I am paid less than male colleagues doing the same job. Is this illegal?"},
    {"subject": "wages", "q": "What are the maximum working hours allowed under Indian labour law?"},
    {"subject": "wages", "q": "Employer wants me to serve 3 months notice. Is this enforceable?"},
    {"subject": "wages", "q": "My salary is being deducted unfairly. Where do I complain?"},

    # =========== RTI (5) ===========
    {"subject": "rti", "q": "I filed an RTI and it was rejected. Can I appeal? What is the time limit?"},
    {"subject": "rti", "q": "What is the time limit for the public authority to respond to an RTI?"},
    {"subject": "rti", "q": "How much fee do I have to pay to file an RTI?"},
    {"subject": "rti", "q": "The PIO says my information is personal and refused. Can they?"},
    {"subject": "rti", "q": "First appeal got rejected. Can I go for second appeal?"},

    # =========== MOTOR ACCIDENT (10) ===========
    {"subject": "motor", "q": "My family member died in a road accident. How do I claim compensation?"},
    {"subject": "motor", "q": "I had a car accident. The other driver was drunk. What can I do?"},
    {"subject": "motor", "q": "A vehicle hit my father and ran away. How do we claim compensation?"},
    {"subject": "motor", "q": "My driving license was suspended after an accident. Can I challenge it?"},
    {"subject": "motor", "q": "Insurance company is refusing third party claim. What now?"},
    {"subject": "motor", "q": "Which tribunal handles motor accident claims and how to approach?"},
    {"subject": "motor", "q": "What is no-fault liability in motor accident cases?"},
    {"subject": "motor", "q": "I bought a car without third-party insurance. Is that an offence?"},
    {"subject": "motor", "q": "I am permanently disabled after a road accident. How is compensation calculated?"},
    {"subject": "motor", "q": "How is compensation amount decided in motor accident claim?"},

    # =========== OUT-OF-SLICE (15) — should refuse honestly ===========
    {"subject": "tax", "q": "How is capital gains tax calculated on the sale of a house?"},
    {"subject": "property", "q": "My neighbor encroached on my land. What legal action can I take?"},
    {"subject": "ip", "q": "I invented a product. How do I get a patent in India?"},
    {"subject": "constitutional", "q": "Does the right to privacy come from the Constitution?"},
    {"subject": "tax", "q": "Do I need GST registration if my turnover is 30 lakhs?"},
    {"subject": "ip", "q": "How do I register a trademark for my brand?"},
    {"subject": "property", "q": "My tenant is not vacating after the notice period. What can I do?"},
    {"subject": "cyber", "q": "Someone is cyberstalking me on Instagram. What can I do legally?"},
    {"subject": "defamation", "q": "Someone wrote false things about me online. Can I sue for defamation?"},
    {"subject": "contract", "q": "The other party breached our contract. What remedies do I have?"},
    {"subject": "inheritance", "q": "My father died without a will. How is property divided among Hindu legal heirs?"},
    {"subject": "inheritance", "q": "Under Muslim personal law, how is inheritance divided?"},
    {"subject": "wills", "q": "I want to write a will. What is the procedure?"},
    {"subject": "poa", "q": "How do I make a Power of Attorney for my parents?"},
    {"subject": "adoption", "q": "What is the legal procedure to adopt a child in India?"},

    # =========== EDGE CASES (10) ===========
    {"subject": "unknown", "q": "What is the airspeed velocity of an unladen swallow under Indian law?"},
    {"subject": "multi-issue", "q": "Police did not file my FIR and they also asked me for a bribe. What can I do?"},
    {"subject": "vague", "q": "what to do?"},
    {"subject": "long-scenario", "q": "I bought a flat in Pune in 2019. The builder promised possession in December 2021 but still has not given it. Now he is demanding extra money for maintenance and threatening to cancel my allotment if I don't pay. I have already paid 95% of the cost. The RERA registration of the project has lapsed. Two other buyers have already filed cases. What are my legal options?"},
    {"subject": "ungrammatical", "q": "wife dont let see child what i do help"},
    {"subject": "time-sensitive", "q": "Yesterday police arrested my brother and they have not allowed us to meet him. What do I do tonight?"},
    {"subject": "procedural", "q": "How exactly do I file an RTI application, step by step?"},
    {"subject": "comparative", "q": "What is the difference between Section 154(3) and Section 156(3) of CrPC?"},
    {"subject": "criminal", "q": "If a husband hits his wife, which sections of BNS apply?"},
    {"subject": "family", "q": "I am a working woman in Mumbai going through divorce. Tell me about my rights regarding maintenance, custody, and stridhan."},
]

assert len(QUERIES) == 100, f"expected 100 queries, got {len(QUERIES)}"

# Slice subjects we can legitimately answer.
SLICE_SUBJECTS = {"criminal", "consumer", "family", "wages", "rti", "motor", "multi-issue", "long-scenario", "ungrammatical", "time-sensitive", "procedural", "comparative"}


def stream_answer(q: str, *, top_k: int = 8, skip_nli: bool = False) -> dict:
    """POST /answer, collect every SSE event into a structured trace."""
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


_SECTION_RE = re.compile(r"^\s*\*\*([A-Za-z][^*]+)\*\*\s*$")
EXPECTED_SECTIONS = {"short answer", "what this means for you", "why (the law)", "what you can do next", "sources", "disclaimer"}


def score(result: dict, subject: str) -> dict:
    """Per-query scorecard."""
    sents = result["sentences"]
    n_ok = sum(1 for s in sents if s.get("status") == "ok")
    n_weak = sum(1 for s in sents if s.get("status") == "weak_support")
    n_unsup = sum(1 for s in sents if s.get("status") in ("unsupported", "unknown_citation"))
    n_meta = sum(1 for s in sents if s.get("status") == "meta")
    n_auto = sum(1 for s in sents if s.get("auto_cited"))

    # Sections seen — extracted from META lines like "**Short answer**"
    sections_seen = set()
    for s in sents:
        m = _SECTION_RE.match(s.get("text", ""))
        if m:
            sections_seen.add(m.group(1).strip().lower())
    sections_present = sections_seen & EXPECTED_SECTIONS

    # Citation density across OK + weak sentences
    cited = [s for s in sents if s.get("status") in ("ok", "weak_support")]
    cit_density = (
        sum(len(s.get("citations") or []) for s in cited) / max(1, len(cited))
    )

    # Verdict
    in_slice = subject in SLICE_SUBJECTS
    if in_slice:
        # Pass if ≥2 cited sentences, weak/total < 50%, no stop
        emitted = n_ok + n_weak + n_unsup
        weak_ratio = n_weak / max(1, emitted)
        verdict = (
            "pass" if (n_ok >= 2 and not result["stopped"] and weak_ratio < 0.5)
            else "stop" if result["stopped"]
            else "fail"
        )
    else:
        # Out-of-slice: pass if refused OR if it produced ≥2 cited sentences
        # that genuinely cover the topic (we don't have a way to judge the
        # latter automatically, so we treat refuse as the correct behavior).
        if result["refused"]:
            verdict = "pass-refused"
        elif n_ok >= 2 and not result["stopped"]:
            verdict = "pass-answered"   # surprisingly the corpus covered it
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
        "n_unsup": n_unsup,
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
    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"battery_v2_{stamp}.json"
    md_path = out_dir / f"battery_v2_{stamp}.md"

    print(f"=== Battery v2 ({len(QUERIES)} queries) ===")
    print(f"API: {API_BASE}")
    print(f"Trace JSON: {json_path.name}")
    print(f"Scorecard:  {md_path.name}\n", flush=True)

    all_results = []
    overall_t0 = time.perf_counter()
    for i, q_spec in enumerate(QUERIES, 1):
        q = q_spec["q"]
        subject = q_spec["subject"]
        print(f"[{i:>3}/{len(QUERIES)}] [{subject:13s}] {q[:62]}…", flush=True)
        result = stream_answer(q, top_k=8, skip_nli=False)
        sc = score(result, subject)
        all_results.append({"score": sc, "full": result})

        bits = [sc["verdict"]]
        bits.append(f"ok={sc['n_ok']}")
        if sc["n_weak"]:
            bits.append(f"weak={sc['n_weak']}")
        if sc["n_unsup"]:
            bits.append(f"BAD={sc['n_unsup']}")
        if sc["stopped"]:
            bits.append("STOP")
        if sc["refused"]:
            bits.append("REF")
        if sc["error"]:
            bits.append(f"ERR={str(sc['error'])[:40]}")
        bits.append(f"{(sc['total_ms'] or 0)/1000:.0f}s")
        print(f"      → {' | '.join(bits)}", flush=True)

    overall_elapsed = time.perf_counter() - overall_t0

    json_path.write_text(json.dumps(all_results, indent=2, default=str))

    # Aggregate
    by_subject = defaultdict(list)
    for r in all_results:
        by_subject[r["score"]["subject"]].append(r["score"])

    lines = []
    lines.append(f"# Output-quality battery v2 — {len(QUERIES)} queries")
    lines.append("")
    lines.append(f"- Run at: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Total elapsed: {overall_elapsed:.0f}s ({overall_elapsed/60:.1f} min)")
    lines.append(f"- API: {API_BASE}")
    lines.append("")

    # Overall scorecard
    n_total = len(all_results)
    n_pass = sum(1 for r in all_results if r["score"]["verdict"].startswith("pass"))
    n_stop = sum(1 for r in all_results if r["score"]["stopped"])
    n_refused = sum(1 for r in all_results if r["score"]["refused"])
    n_error = sum(1 for r in all_results if r["score"]["error"])
    in_slice_results = [r for r in all_results if r["score"]["in_slice"]]
    n_slice_pass = sum(1 for r in in_slice_results if r["score"]["verdict"] == "pass")

    lines.append("## Overall")
    lines.append("")
    lines.append(f"- **{n_pass}/{n_total} pass** ({100*n_pass/n_total:.0f}%) — any pass-variant")
    lines.append(f"- **{n_slice_pass}/{len(in_slice_results)} in-slice pass** ({100*n_slice_pass/max(1,len(in_slice_results)):.0f}%)")
    lines.append(f"- {n_stop} stopped, {n_refused} refused, {n_error} errored")
    lat = [r["score"]["total_ms"] for r in all_results if r["score"]["total_ms"]]
    if lat:
        lines.append(f"- Latency: median {statistics.median(lat)/1000:.1f}s, p90 {statistics.quantiles(lat, n=10)[-1]/1000:.1f}s")
    lines.append("")

    # Per-subject scorecard
    lines.append("## Per-subject")
    lines.append("")
    lines.append("| subject | n | pass | stop | refused | weak% | bad% | auto-cite% | median t |")
    lines.append("|---------|---|------|------|---------|-------|------|-----------|----------|")
    for subj, scores in sorted(by_subject.items()):
        n = len(scores)
        n_pass_s = sum(1 for s in scores if s["verdict"].startswith("pass"))
        n_stop_s = sum(1 for s in scores if s["stopped"])
        n_ref_s = sum(1 for s in scores if s["refused"])
        n_total_emit = sum(s["n_ok"] + s["n_weak"] + s["n_unsup"] for s in scores)
        n_weak_total = sum(s["n_weak"] for s in scores)
        n_bad_total = sum(s["n_unsup"] for s in scores)
        n_auto = sum(s["n_auto_cited"] for s in scores)
        n_emit_ok = sum(s["n_ok"] for s in scores)
        lat_s = [s["total_ms"] for s in scores if s["total_ms"]]
        median_lat = statistics.median(lat_s) / 1000 if lat_s else 0
        lines.append(
            f"| {subj} | {n} | {n_pass_s} | {n_stop_s} | {n_ref_s} | "
            f"{100*n_weak_total/max(1,n_total_emit):.0f}% | "
            f"{100*n_bad_total/max(1,n_total_emit):.0f}% | "
            f"{100*n_auto/max(1,n_emit_ok):.0f}% | "
            f"{median_lat:.0f}s |"
        )

    # Failure details (only failed / stopped queries)
    lines.append("")
    lines.append("## Failures (stop / fail / error)")
    lines.append("")
    for r in all_results:
        s = r["score"]
        if s["verdict"].startswith("pass"):
            continue
        marker = "STOP" if s["stopped"] else "REFUSE" if s["refused"] else "FAIL"
        lines.append(f"- **{marker}** [{s['subject']}] {s['query']}")
        lines.append(
            f"  - ok={s['n_ok']}  weak={s['n_weak']}  bad={s['n_unsup']}  "
            f"meta={s['n_meta']}  auto={s['n_auto_cited']}  "
            f"t={s['total_ms']/1000:.0f}s  sections={s['sections_present']}"
        )

    md_path.write_text("\n".join(lines))
    print()
    print("\n".join(lines))
    print()
    print(f"Full trace: {json_path}")
    print(f"Scorecard : {md_path}")


if __name__ == "__main__":
    main()
