#!/usr/bin/env python3
"""End-to-end eval: 100 unique lay-person queries against the live /answer.

Goal: simulate a real walk-in legal-aid user. Per query we capture:
  - was it refused (coverage < gate, or empty corpus)?
  - relevance verdict (ok / partial / off_topic) + cosine score
  - coverage score (top rerank of any retrieved chunk)
  - number of sentences emitted, suppressed (uncited), weak-support
  - source-type breakdown of the passages actually used
  - top-3 source titles + anchors

Per-query single-line summary on stdout; full structured rows
written to data/processed/e2e_eval_<timestamp>.jsonl for later
analysis.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/eval_e2e_100.py [--limit N] [--offset N]

100 queries × ~20s each ≈ 33 min. Use --limit 30 for a 10-min smoke.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
API_URL = "http://localhost:8000/answer"

# Realistic end-user queries grouped by domain. NOT a perfect taxonomy —
# the system has to figure out the operative law from a lay phrase. Each
# query is a real thing a NALSA / district-court / online-portal user
# might type. Mix of formal / informal / broken-English / specific /
# vague to reflect actual traffic.
QUERIES: list[tuple[str, str]] = [
    # --- family / divorce / maintenance ---------------------------------
    ("family", "my husband is beating me what can I do"),
    ("family", "i want divorce my husband stopped working drinks all day"),
    ("family", "hindu marriage how to get divorce mutual consent"),
    ("family", "wife asking for maintenance under section 125 crpc"),
    ("family", "custody of child after divorce who gets it"),
    ("family", "muslim woman wants to divorce her husband"),
    ("family", "married in same gotra is the marriage valid hindu law"),
    ("family", "second marriage without divorce is it legal in india"),
    ("family", "interfaith marriage special marriage act procedure"),
    ("family", "want to adopt a child as a single parent"),
    # --- senior citizens / parents ---
    ("senior", "my son threw me out of the house after I gave him my property"),
    ("senior", "parents not being taken care of by children legal remedy"),
    ("senior", "I am 70 years old can I cancel the gift deed I made to my son"),
    ("senior", "maintenance tribunal for senior citizens how to approach"),
    # --- property / land / tenancy ---
    ("property", "my landlord is not returning my deposit money"),
    ("property", "landlord increased rent suddenly without notice"),
    ("property", "neighbour captured my land what can I do"),
    ("property", "land grabber occupied my agricultural land for 10 years"),
    ("property", "want to sell ancestral property brother not agreeing"),
    ("property", "registration of sale deed stamp duty in maharashtra"),
    ("property", "builder not giving possession of flat after 5 years"),
    ("property", "right to property in joint family how is it shared"),
    ("property", "easement right of way through neighbours land"),
    ("property", "tenant not vacating after lease expired"),
    # --- consumer / e-commerce ---
    ("consumer", "online order broken refund company not responding"),
    ("consumer", "amazon delivery damaged product refund denied"),
    ("consumer", "restaurant served bad food got food poisoning what to do"),
    ("consumer", "doctor negligence wrong treatment compensation"),
    ("consumer", "car dealership sold defective vehicle"),
    ("consumer", "insurance company denying my health claim"),
    ("consumer", "builder gave possession 3 years late RERA"),
    ("consumer", "bank charging hidden fees on my savings account"),
    # --- criminal / safety ---
    ("criminal", "my husband filed false 498A case on me what to do"),
    ("criminal", "anticipatory bail for false dowry case"),
    ("criminal", "FIR not being registered by police what should I do"),
    ("criminal", "stalking online by ex boyfriend"),
    ("criminal", "domestic violence in family am I a victim"),
    ("criminal", "neighbour threatened me with knife"),
    ("criminal", "false case filed against me how to quash FIR"),
    ("criminal", "child molested by neighbour POCSO complaint"),
    ("criminal", "acid attack victim legal remedy compensation"),
    ("criminal", "cyber bullying on instagram what law applies"),
    # --- employment / labor / wages ---
    ("employment", "boss fired me without notice and without paying salary"),
    ("employment", "my company is not paying my gratuity"),
    ("employment", "sexual harassment at work boss touching me"),
    ("employment", "EPF withdrawal company refusing to give my PF"),
    ("employment", "termination of employment without notice period valid"),
    ("employment", "maternity leave denied by employer 26 weeks"),
    ("employment", "overtime not paid for working 12 hours daily"),
    ("employment", "company asking me to resign or face termination"),
    # --- wages / industrial dispute ---
    ("wages", "factory shut down without notice we workers got no payment"),
    ("wages", "minimum wages not being paid by contractor"),
    # --- cyber / data / privacy ---
    ("cyber", "someone hacked my facebook account and posted bad things"),
    ("cyber", "credit card fraud online transaction unauthorized"),
    ("cyber", "deepfake video of me circulating on whatsapp"),
    ("cyber", "company shared my personal data with third party"),
    ("cyber", "phishing email pretending to be my bank lost money"),
    # --- tax / GST / income tax ---
    ("tax", "received income tax notice under section 148"),
    ("tax", "GST registration threshold for small business turnover"),
    ("tax", "TDS deducted by employer but not deposited what to do"),
    ("tax", "capital gains tax on sale of inherited property"),
    ("tax", "income tax refund not received for 2 years"),
    ("tax", "GST input tax credit denied by department"),
    # --- finance / cheque bounce / loans ---
    ("finance", "cheque bounced from my client what is the legal remedy"),
    ("finance", "section 138 NI Act notice 30 days time limit"),
    ("finance", "bank giving recovery notice for personal loan can they seize my property"),
    ("finance", "SARFAESI notice from bank for home loan default"),
    ("finance", "credit card company harassment for unpaid bill"),
    # --- children / education / RTE ---
    ("education", "school is not admitting my children even though has cleared admission test"),
    ("education", "school demanding capitation fee for admission"),
    ("education", "private school refused to give 25 percent EWS reservation"),
    ("education", "child failed in school can school detain him"),
    # --- women / harassment / safety ---
    ("women", "stalked by colleague at office what to do"),
    ("women", "married as child at age 14 want to annul marriage"),
    ("women", "dowry demand by in laws after marriage harassment"),
    ("women", "rape complaint how to file FIR what is procedure"),
    # --- constitutional / civic rights ---
    ("constitutional", "police arrested without warrant my fundamental rights"),
    ("constitutional", "RTI application not getting reply from government"),
    ("constitutional", "right to privacy aadhaar mandatory for bank account"),
    ("constitutional", "Article 21 right to life what does it mean"),
    # --- procedure / courts / legal aid ---
    ("procedure", "free legal aid eligibility how to apply NALSA"),
    ("procedure", "limitation period for filing civil suit recovery of money"),
    ("procedure", "what is the procedure for filing a writ petition high court"),
    ("procedure", "case pending for 10 years in district court what to do"),
    ("procedure", "Lok Adalat settlement is it final binding"),
    ("procedure", "lawyer not appearing for my case can I change"),
    ("procedure", "court fee for filing suit how much"),
    # --- motor / accident ---
    ("motor", "hit and run accident victim compensation claim"),
    ("motor", "third party insurance not paying after accident"),
    ("motor", "MACT claim for road accident death of family member"),
    # --- inheritance / succession ---
    ("succession", "father died without will sons and daughters share"),
    ("succession", "muslim inheritance shares for daughter wife mother"),
    ("succession", "daughter coparcener in hindu joint family 2005 amendment"),
    ("succession", "stepmother claiming share in father's property"),
    # --- specialty / misc ---
    ("misc", "POSH internal complaints committee composition my office"),
    ("misc", "PMLA attachment of property ED proceedings against me"),
    ("misc", "passport application denied criminal case pending"),
    ("misc", "narcotics case bail NDPS Act commercial quantity"),
    ("misc", "company defaulting on payment IBC NCLT proceedings"),
    # --- truly off-corpus (refusal expected) ---
    ("off_corpus", "what is the weather today in delhi"),
    ("off_corpus", "recipe for biryani"),
    ("off_corpus", "how does python list comprehension work"),
]


def stream_answer(query: str, timeout_s: int = 90) -> dict:
    """Stream /answer SSE and aggregate per-query metrics."""
    data = json.dumps({"q": query}).encode()
    req = urllib.request.Request(
        API_URL, data=data, headers={"Content-Type": "application/json"},
    )

    result: dict = {
        "query": query,
        "started_at": datetime.utcnow().isoformat(),
        "events": {},
        "sentences": 0,
        "ok_sentences": 0,
        "weak_sentences": 0,
        "unsupported_sentences": 0,
        "suppressed": 0,
        "refused": False,
        "refused_reason": None,
        "relevance_score": None,
        "relevance_verdict": None,
        "coverage_top_rerank": None,
        "sources_count": 0,
        "bare_act_count": 0,
        "sc_judgment_count": 0,
        "top_titles": [],
        "took_s": None,
        "error": None,
        # Strict verdict (computed post-stream below) — agent #1 wanted
        # an "OK only if grounded in actual bare-act when one was needed"
        # metric to separate cosmetic-OK from honest-OK.
        "verdict_strict": None,
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
                    try:
                        d = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    result["events"].setdefault(event_name or "unknown", 0)
                    result["events"][event_name or "unknown"] += 1
                    if event_name == "sentence":
                        result["sentences"] += 1
                        # 2026-05-20 multi-agent review: this used to read
                        # `d.get("verdict")` and check for "OK"/"WEAK_SUPPORT",
                        # but the API emits `"status"` with lowercase values
                        # (apps/api/main.py::_sentence_event → SentenceStatus.OK
                        # → "ok"). So per-sentence ok/weak counts had been 0
                        # across every eval (v2/v3/v4/v5) — meaning the OK
                        # rate was driven entirely by the relevance-cosine
                        # gate, not by citation grounding. Honest read of the
                        # post-fix numbers requires this to actually count.
                        status = d.get("status", "")
                        if status == "ok":
                            result["ok_sentences"] += 1
                        elif status == "weak_support":
                            result["weak_sentences"] += 1
                        elif status in ("unsupported", "unknown_citation"):
                            # Should already be suppressed pre-emit, but
                            # count for visibility if any slips through.
                            result["unsupported_sentences"] = (
                                result.get("unsupported_sentences", 0) + 1
                            )
                    elif event_name == "suppressed":
                        result["suppressed"] += 1
                    elif event_name == "refused":
                        result["refused"] = True
                        result["refused_reason"] = d.get("reason")
                    elif event_name == "relevance":
                        result["relevance_score"] = d.get("score")
                        result["relevance_verdict"] = d.get("verdict")
                    elif event_name == "coverage":
                        result["coverage_top_rerank"] = d.get("top_rerank") or d.get("top_score")
                    elif event_name == "sources":
                        # Payload is a LIST of {index, title, court, citation, anchor, as_at}.
                        # source_type isn't included — infer from anchor: SC judgments
                        # use `\d{4}-insc-\d+#...`, bare-acts use `<slug>/sec-...`.
                        items = d if isinstance(d, list) else (
                            d.get("items") or d.get("sources") or [])
                        if isinstance(items, list):
                            result["sources_count"] = len(items)
                            import re as _re
                            sc_anchor_re = _re.compile(r"^\d{4}-(insc|\d+-\d+)")
                            for s in items:
                                if not isinstance(s, dict):
                                    continue
                                anchor = s.get("anchor", "") or ""
                                if sc_anchor_re.match(anchor):
                                    result["sc_judgment_count"] += 1
                                elif "/" in anchor or anchor.startswith(("posh-", "rte-", "ipc-")):
                                    result["bare_act_count"] += 1
                                # else: leave uncounted (unknown source_type)
                            result["top_titles"] = [
                                {
                                    "title": (s.get("title") or "")[:60],
                                    "anchor": s.get("anchor", "")[:50],
                                    "court": s.get("court", ""),
                                }
                                for s in items[:3] if isinstance(s, dict)
                            ]
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    result["took_s"] = round(time.time() - t0, 1)

    # Strict verdict — added 2026-05-20 after agent #1's review showed
    # the cosine-relevance gate was passing "topically-similar SC-only"
    # answers as OK for queries that obviously needed a bare Act.
    # Rule: if the cosine gate says "ok" AND the query is in a category
    # that ALWAYS needs operative-Act citation (or names an Act explicitly),
    # demote to "partial" when no bare-act was cited.
    result["verdict_strict"] = _strict_verdict(result)
    return result


# Categories where the answer is incomplete without citing the operative Act.
# "constitutional"/"procedure" CAN sometimes be answered from SC interpretation
# alone; "criminal" sometimes too (judicial principles), so they're excluded.
# But for tax/property/consumer/employment etc. an SC-only answer is suspicious.
_ACT_REQUIRED_CATEGORIES = frozenset({
    "tax", "finance", "property", "consumer", "employment", "family",
    "senior", "women", "motor", "wages", "education", "cyber",
})

# Rough Act-name regex — if the query literally names an Act, the answer
# should cite at least one chunk from that Act.
_ACT_NAME_HINTS = (
    "act ", "section ", "article ", "rule ", "code ", "rti", "ipc",
    "crpc", "bns", "bnss", "bsa", "tpa", "cgst", "igst", "rera", "ndps",
    "pmla", "sarfaesi", "fema", "ibc", "posh", "pocso", "epf", "esi",
    "dpdp", "itpa", "rte", "hsa", "pwdva",
)


def _strict_verdict(r: dict) -> str | None:
    """Demote cosine-relevance OK to partial when retrieval clearly missed
    the operative Act for queries that need one. Leaves refused/error rows
    alone. Never promotes — only demotes."""
    if r.get("refused") or r.get("error"):
        return None
    base = r.get("relevance_verdict")
    if base != "ok":
        return base  # PARTIAL / OFF_TOPIC stay
    cat = r.get("category", "")
    q = (r.get("query") or "").lower()
    needs_act = (
        cat in _ACT_REQUIRED_CATEGORIES
        or any(h in q for h in _ACT_NAME_HINTS)
    )
    if needs_act and r.get("bare_act_count", 0) == 0:
        return "partial_strict"  # was cosmetic-OK; honest read is PARTIAL
    return "ok"


def fmt_line(idx: int, total: int, category: str, q: str, r: dict) -> str:
    """One-line summary for stdout."""
    qshort = q[:55] + ("…" if len(q) > 55 else "")
    if r.get("error"):
        return f"  [{idx:>3}/{total}] {category:<13} ERR {r['error'][:60]}  q={qshort!r}"
    if r.get("refused"):
        return (f"  [{idx:>3}/{total}] {category:<13} REFUSE       "
                f"cov={r.get('coverage_top_rerank') or 0.0:.2f}  q={qshort!r}")
    verdict = r.get("relevance_verdict") or "-"
    rscore = r.get("relevance_score") or 0.0
    sents = r.get("sentences", 0)
    ok = r.get("ok_sentences", 0)
    weak = r.get("weak_sentences", 0)
    sup = r.get("suppressed", 0)
    bare = r.get("bare_act_count", 0)
    sc = r.get("sc_judgment_count", 0)
    cov = r.get("coverage_top_rerank") or 0.0
    took = r.get("took_s", 0)
    badge = {"ok": "OK ", "partial": "PRT", "off_topic": "OFF"}.get(verdict, "?  ")
    return (f"  [{idx:>3}/{total}] {category:<13} {badge} "
            f"rel={rscore:.2f} cov={cov:.2f} "
            f"sents={ok}+{weak}w-{sup}s "
            f"src=act{bare}/sc{sc} "
            f"t={took:>4.1f}s  q={qshort!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="cap to first N queries (smoke-test mode)")
    ap.add_argument("--offset", type=int, default=0,
                    help="start at query N (for resuming)")
    ap.add_argument("--out", type=str, default=None,
                    help="output JSONL path (default: data/processed/e2e_eval_<ts>.jsonl)")
    args = ap.parse_args()

    queries = QUERIES[args.offset:]
    if args.limit:
        queries = queries[:args.limit]

    out_path = Path(args.out) if args.out else (
        ROOT / "data" / "processed" /
        f"e2e_eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = len(queries)
    print(f"=== e2e eval: {total} queries → {out_path} ===\n", flush=True)
    rows: list[dict] = []
    t_overall = time.time()
    with out_path.open("a") as f:
        for i, (cat, q) in enumerate(queries, 1):
            r = stream_answer(q)
            r["category"] = cat
            rows.append(r)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(fmt_line(i, total, cat, q, r), flush=True)

    elapsed = time.time() - t_overall
    # ---- aggregate ----
    by_cat: dict[str, dict] = {}
    for r in rows:
        c = r["category"]
        by_cat.setdefault(c, {
            "n": 0, "refused": 0, "ok": 0, "partial": 0, "off_topic": 0,
            "err": 0, "act_used": 0, "sc_used": 0, "both_used": 0,
        })
        st = by_cat[c]
        st["n"] += 1
        if r.get("error"):
            st["err"] += 1
        elif r.get("refused"):
            st["refused"] += 1
        else:
            # 2026-05-21 multi-agent review: the previous `or "ok"` default
            # silently counted rows with no `relevance` event (LLM emitted 0
            # cited sentences) as OK. That inflated the cosine-OK count by
            # ~9 across v2-v6. Use "no_relevance" so these surface in the
            # report instead of being hidden in OK.
            v = r.get("relevance_verdict") or "no_relevance"
            st[v] = st.get(v, 0) + 1
        if r.get("bare_act_count", 0) > 0:
            st["act_used"] += 1
        if r.get("sc_judgment_count", 0) > 0:
            st["sc_used"] += 1
        if r.get("bare_act_count", 0) > 0 and r.get("sc_judgment_count", 0) > 0:
            st["both_used"] += 1

    print(f"\n=== Aggregate ({elapsed/60:.1f} min for {total} queries) ===")
    print(f"  {'category':<14} {'n':>3} {'ok':>3} {'prt':>3} {'off':>3} "
          f"{'nor':>3} {'ref':>3} {'err':>3}  bare-act-used  sc-used  both")
    print(f"  {'(nor=no_relevance-event — answer with 0 cited sentences)':<60}")
    overall = {"n": 0, "ok": 0, "partial": 0, "off_topic": 0, "refused": 0,
               "no_relevance": 0, "err": 0, "act_used": 0, "sc_used": 0,
               "both_used": 0}
    for cat in sorted(by_cat):
        st = by_cat[cat]
        print(f"  {cat:<14} {st['n']:>3} {st.get('ok',0):>3} "
              f"{st.get('partial',0):>3} {st.get('off_topic',0):>3} "
              f"{st.get('no_relevance',0):>3} "
              f"{st['refused']:>3} {st['err']:>3}  "
              f"{st['act_used']:>4}/{st['n']:<4}  {st['sc_used']:>4}/{st['n']:<4}  "
              f"{st['both_used']:>3}")
        for k in overall:
            overall[k] += st.get(k, 0)
    print(f"  {'TOTAL':<14} {overall['n']:>3} {overall['ok']:>3} "
          f"{overall['partial']:>3} {overall['off_topic']:>3} "
          f"{overall['no_relevance']:>3} "
          f"{overall['refused']:>3} {overall['err']:>3}  "
          f"{overall['act_used']:>4}/{overall['n']:<4}  "
          f"{overall['sc_used']:>4}/{overall['n']:<4}  "
          f"{overall['both_used']:>3}")

    # ---- Strict verdict aggregate ----
    # Distinguishes "honest OK" (cosine OK + actually cited the operative
    # Act when the category needs one) from "cosmetic OK" (cosine OK but
    # answer cites only SC caselaw for a query that obviously needed a
    # statute). The honest number is the one to track session-over-session.
    strict_counts: dict[str, int] = {}
    sent_groundedness: dict[str, list] = {"ok": [], "partial_strict": [],
                                          "partial": [], "off_topic": []}
    for r in rows:
        v = r.get("verdict_strict")
        if v is None:
            continue
        strict_counts[v] = strict_counts.get(v, 0) + 1
        sent_groundedness.setdefault(v, []).append(
            r.get("ok_sentences", 0) + r.get("weak_sentences", 0)
        )
    print(f"\n=== STRICT verdict (honest read — see _strict_verdict docstring) ===")
    n_scored = sum(strict_counts.values())
    if n_scored:
        ok_honest = strict_counts.get("ok", 0)
        ok_cosmetic = strict_counts.get("partial_strict", 0)
        partial = strict_counts.get("partial", 0)
        off = strict_counts.get("off_topic", 0)
        print(f"  OK (honest)        : {ok_honest:>3}  ({100*ok_honest/n_scored:.0f}%)")
        print(f"  OK (was cosmetic, now demoted): {ok_cosmetic:>3}  ({100*ok_cosmetic/n_scored:.0f}%)")
        print(f"  PARTIAL            : {partial:>3}  ({100*partial/n_scored:.0f}%)")
        print(f"  OFF_TOPIC          : {off:>3}  ({100*off/n_scored:.0f}%)")
        # Sentence-grounding median per verdict
        print(f"\n  Sentence groundedness (ok + weak sentences cited) by verdict:")
        for v in ("ok", "partial_strict", "partial", "off_topic"):
            counts = sent_groundedness.get(v) or []
            if counts:
                med = sorted(counts)[len(counts)//2]
                mean = sum(counts) / len(counts)
                print(f"    {v:<18}: n={len(counts):>3}  median={med:>3}  mean={mean:.1f}")

    # Concerning failures: high-confidence off-topic or low-coverage
    # answers that weren't refused
    print("\n=== Worst 10 (off-topic answers that weren't refused) ===")
    not_ref = [r for r in rows if not r.get("refused") and not r.get("error")]
    not_ref.sort(key=lambda r: (
        r.get("relevance_score") or 1.0,
        -(r.get("suppressed") or 0),
    ))
    for r in not_ref[:10]:
        v = r.get("relevance_verdict") or "-"
        s = r.get("relevance_score") or 0.0
        bare = r.get("bare_act_count", 0)
        sc = r.get("sc_judgment_count", 0)
        print(f"  rel={s:.3f} {v:<10s}  bare={bare} sc={sc}  "
              f"q={r['query'][:75]!r}")

    print(f"\n  Full results: {out_path}")


if __name__ == "__main__":
    main()
