#!/usr/bin/env python3
"""LLM-judge classifier for eval_500_*.jsonl outputs.

Why this exists — the 201-query eval's heuristic analyzer
(scripts/analyze_eval_200.py) produced 23 WRONG_REF false positives
(matching 'Domestic Violence Act' verbatim when PWDVA was correctly
cited as 'Protection of Women from Domestic Violence Act, 2005')
and 15 UNKNOWN rows with no signal at all. Heuristic classification
is fast but noisy.

This script runs qwen3:14b (already loaded for /answer) as a
LLM-judge over each eval row, producing structured judgments:

  - correct_act: did the cited Act(s) cover the expected legal basis?
  - on_topic: is the answer body on the right topic?
  - operationally_actionable: does it give concrete next steps
      (forum, deadline, procedure)?
  - dangerous_framing: accused asked, answer framed as victim?
  - real_issue: enum (see ROOT_CAUSE_ENUM below)
  - rationale: 1-2 sentence explanation

Wall budget: ~17 min for 500 rows at ~2s/row on qwen3:14b.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/llm_judge_eval.py \\
      --eval data/processed/eval_500_baseline_LATEST.jsonl \\
      --out  data/processed/eval_500_baseline_LATEST.judged.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent

ROOT_CAUSE_ENUM = [
    "corpus_gap",                # right Act missing from corpus
    "retrieval_miss",            # corpus has it, didn't surface top-K
    "rerank_misfire",            # surfaced but rerank scored wrong chunks
    "llm_hallucination",         # LLM ignored retrieval, made up cite
    "wrong_act_year",            # cited but old version (CPA 1986 vs 2019)
    "accused_as_victim",         # dangerous frame mismatch
    "refusal_threshold_tight",   # system refused, was answerable
    "answer_too_thin",           # cite correct but no operational guidance
    "off_corpus",                # query genuinely outside scope
    "none",                      # looks fine
]


JUDGE_PROMPT = """You are evaluating the quality of an Indian legal RAG system's answer
to a real-user question. Be strict but fair — these answers are seen by
non-lawyers who need to act on the information.

PERSONA CONTEXT
The user is a {persona} — {persona_blurb}.

THE QUESTION
{query}

WHAT SHOULD HAVE BEEN CITED (gold hint from eval set)
{expected_act_hint}

TOP CITATIONS THE SYSTEM ACTUALLY RETURNED
{sources_summary}

THE ANSWER BODY (concatenated sentences)
{body}

REFUSAL / OFF-TOPIC SIGNALS
- system refused: {refused}
- relevance_verdict (cosine gate): {relevance_verdict}
- n_sentences cited: {n_sentences}

YOUR TASK
Classify this answer along these dimensions, output as a single JSON
object on ONE line (no markdown, no preamble, no <think> tags):

{{
  "correct_act": true/false,
  "on_topic": true/false,
  "operationally_actionable": true/false,
  "dangerous_framing": true/false,
  "real_issue": "<one of: corpus_gap, retrieval_miss, rerank_misfire, llm_hallucination, wrong_act_year, accused_as_victim, refusal_threshold_tight, answer_too_thin, off_corpus, none>",
  "rationale": "<one sentence — why you chose real_issue>"
}}

GUIDANCE
- `correct_act`: a closely-related Act counts (e.g. cited BNS instead of
  expected IPC for post-2023 — that's correct, not wrong).
- `operationally_actionable`: answer must name AT LEAST ONE concrete
  forum/deadline/procedure (e.g. "file with magistrate within 30 days",
  "approach DLSA", "tribunal under section 5"). Pure citation = false.
- `dangerous_framing`: ONLY true if the user clearly stated they are
  the accused/subject-of-state-action but the answer frames them as a
  victim/complainant. Be conservative — most cases will be false.
- `real_issue` priority order (use the FIRST match):
    1. system refused but query has clear legal hook -> refusal_threshold_tight
    2. cited Act exists but wrong year/version -> wrong_act_year
    3. accused asked, victim-framed answer -> accused_as_victim
    4. expected_act_hint Act/section not in any citation, no near-match -> corpus_gap or retrieval_miss (corpus_gap if you suspect the Act isn't in the corpus at all; retrieval_miss if the right Act is famous and should be there)
    5. correct Act cited but the wrong section within it surfaced top -> rerank_misfire
    6. answer text contradicts cited sources -> llm_hallucination
    7. correct Act + section but no procedural steps -> answer_too_thin
    8. query genuinely not about Indian law -> off_corpus
    9. otherwise -> none
"""


PERSONA_BLURBS = {
    "urban_pro": "white-collar professional in metro, English-fluent, knows some legal vocab",
    "rural_dlsa": "rural villager, broken English, often goes through legal-aid clinic",
    "women_vulnerable": "woman facing DV/dowry/harassment, anxious, may be in crisis",
    "procedural": "person trying to navigate a legal procedure, asks how-to questions",
    "youth_digital": "18-30, smartphone-native, deals with cybercrime/gig/freelance issues",
    "elderly": "60+, often paralegal-mediated, property/will/maintenance issues",
    "small_business": "MSME owner, shopkeeper, freelancer, commercial disputes",
    "tribal_marginalized": "SC/ST/Adivasi user, atrocities/land/forest rights/FIR-refusal issues",
    "migrant_labour": "inter-state migrant worker, very broken English, wage theft/accident/ID loss",
    "prisoner_undertrial": "family member of someone in custody OR recently-released undertrial",
}


def format_sources(sources: list[dict]) -> str:
    if not sources:
        return "  (no sources retrieved)"
    lines = []
    for s in sources[:5]:
        lines.append(
            f"  - [{s.get('source_type', '?'):<11}] {s.get('anchor', '?')} "
            f"— {s.get('title', '')[:60]}"
        )
    return "\n".join(lines)


def get_body(row: dict) -> str:
    sents = row.get("sentences", [])
    return " ".join(s.get("text", "") for s in sents)[:2000]


def parse_judge_response(text: str) -> dict | None:
    """Best-effort JSON extraction from qwen3 output (may contain <think> tags)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Find the first {...} block
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not m:
        # Try multi-line
        m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return d


async def judge_one(row: dict, model: str = "qwen3:14b") -> dict:
    """Call qwen3:14b via Ollama and return the parsed judgment."""
    from apps.api.llm import chat_once

    body = get_body(row)
    sources_summary = format_sources(row.get("sources") or [])
    prompt = JUDGE_PROMPT.format(
        persona=row.get("persona", "unknown"),
        persona_blurb=PERSONA_BLURBS.get(row.get("persona", ""),
                                          "Indian legal-aid client"),
        query=row.get("query", ""),
        expected_act_hint=row.get("expected_act_hint", "(none provided)"),
        sources_summary=sources_summary,
        body=body or "(empty)",
        refused=row.get("refused", False),
        relevance_verdict=row.get("relevance_verdict", "?"),
        n_sentences=row.get("n_sentences", 0),
    )
    try:
        raw = await chat_once(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )
    except Exception as e:
        return {"error": f"llm_call_failed: {type(e).__name__}: {e}"}

    d = parse_judge_response(raw)
    if d is None:
        return {"error": "parse_failed", "raw": raw[:300]}
    # Validate enum
    if d.get("real_issue") not in ROOT_CAUSE_ENUM:
        d["_warn"] = f"real_issue not in enum: {d.get('real_issue')}"
        d["real_issue"] = "none"
    return d


async def main_async() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--eval", required=True,
                   help="input eval JSONL (from eval_200_runner / eval_500)")
    p.add_argument("--out", required=True,
                   help="output JSONL with judgment field added")
    p.add_argument("--limit", type=int, default=None,
                   help="cap total rows judged")
    p.add_argument("--concurrency", type=int, default=4,
                   help="parallel judge calls (qwen3 handles ~4 well)")
    p.add_argument("--model", default="qwen3:14b")
    args = p.parse_args()

    inp = Path(args.eval)
    if not inp.exists():
        raise SystemExit(f"input missing: {inp}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    with inp.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    if args.limit:
        rows = rows[:args.limit]
    print(f"loaded {len(rows)} rows from {inp.name}", flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    judged: list[dict] = []
    t0 = time.time()

    async def go(i: int, r: dict):
        async with sem:
            j = await judge_one(r, model=args.model)
            r2 = {**r, "judgment": j}
            judged.append((i, r2))
            elapsed = time.time() - t0
            real = j.get("real_issue", "?") if "error" not in j else "ERR"
            issue_summary = j.get('error') or real
            print(f"  [{i+1:>3}/{len(rows)}] "
                  f"t={elapsed:>6.1f}s real_issue={issue_summary:<26} "
                  f"q={r.get('query','')[:50]!r}",
                  flush=True)

    await asyncio.gather(*(go(i, r) for i, r in enumerate(rows)))

    judged.sort(key=lambda t: t[0])
    with out.open("w") as f:
        for _, r in judged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\ndone in {(time.time() - t0)/60:.1f} min — wrote {out}")

    # Summary
    from collections import Counter
    cnt = Counter(r["judgment"].get("real_issue", "?") for _, r in judged
                  if "error" not in r["judgment"])
    err = sum(1 for _, r in judged if "error" in r["judgment"])
    print(f"\n=== real_issue distribution (n={len(judged) - err}) ===")
    for k, v in cnt.most_common():
        print(f"  {k:<30} {v:>4}  ({100 * v / max(1, len(judged) - err):.1f}%)")
    if err:
        print(f"  judgement errors: {err}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
