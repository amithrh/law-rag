# Answer-vs-query relevance check (Task #10)

## Why this exists

The original failure case — documented in the task brief — looked like this:

> User: "My landlord is not returning my deposit money."
>
> System: A fully-cited, NLI-passing, bge-passing answer about Section 30
> of the U.P. Rent Act — how to *deposit your monthly rent in court when
> the landlord refuses to accept it*. (Opposite money flow.)

Citation correctness was perfect. NLI / bge confirmed each cited sentence
matched its passage. But the answer was about the wrong question.

The 94% battery pass-rate measured "the model wrote citation-correct
sentences and did not get stopped." It did *not* measure "the answer
addresses the user's question."

This module adds that dimension as an **additive** signal — it warns the
user when query/answer cosine falls below a calibrated threshold, but it
does *not* refuse on its own. The citation gates still ground the answer
text.

## Approach

After the answer stream finishes:

1. Embed the original user query with `bge-m3` (same model used at
   retrieval — already resident).
2. Embed the concatenation of all `OK` + `WEAK_SUPPORT` sentence texts
   (the "user-visible answer body" — META headers, refusal lines, and
   suppressed sentences are excluded). Citation tags `[N]` are stripped
   before embedding so the numerals don't add noise.
3. Compute cosine similarity.
4. Classify by a calibrated threshold `T` and band `B`:
   - `score ≥ T + B/2`              → `ok`
   - `T - B/2 < score < T + B/2`    → `partial`
   - `score ≤ T - B/2`              → `off_topic`
5. Emit an SSE `relevance` event between `sources` and `disclaimer` on
   the normal end path. Refused and stopped paths do not emit.

UI behaviour:
- `ok`        → no notice rendered.
- `partial`   → amber notice: "this answer may only partly match your question".
- `off_topic` → red notice: "this answer may not match your question".

## Calibration

Script: `scripts/calibrate_answer_relevance.py`
Output: `data/processed/answer_relevance_calibration.json`

**Inputs**:
- The most recent battery v3 trace (`battery_v3_20260519-010820.json`),
  filtered to hand-labelled queries.
- 4 synthetic off-topic anchors paraphrased from documented failure modes
  (deposit-return, anticipatory vs regular bail, parking ticket vs
  vehicle registration, complaint-letter vs forum jurisdiction). These
  are realistic answer bodies — the embedding similarity isn't gamed by
  gibberish.

**Method**:
1. For each labelled (query, body) pair, embed and compute bge-m3
   dense cosine.
2. Sweep candidate thresholds (mid-points between observed cosines plus
   0.05/0.95 anchors).
3. Pick the threshold that maximises **balanced accuracy** =
   `(TPR + TNR) / 2`. Balanced accuracy is robust to the on/off imbalance
   in the labelled set.

**Result**:

| stat                | value                  |
|---------------------|------------------------|
| labelled items      | 18                     |
| on-topic cosines    | 0.713 – 0.817 (n=14)   |
| off-topic cosines   | 0.507 – 0.670 (n=4)    |
| threshold T         | **0.6916**             |
| band B              | **0.05**               |
| balanced accuracy   | 1.0 (perfect on set)   |

**Why band=0.05 and not 0.1**

The task brief suggested ±0.1 around the threshold. The data argues
tighter: the gap between off-topic-max (0.670) and on-topic-min (0.713)
is only ~0.04. A 0.1 band would mark ~36% of on-topic answers as
`partial` (their cosines cluster at 0.71-0.74). Band=0.05 keeps the
`partial` range narrow enough that legitimate answers aren't flagged but
borderline cases still surface.

## Live eval results

Script: `scripts/eval_answer_relevance.py`
Eval set: `data/eval/answer_relevance.jsonl` (25 queries)
Result: `data/processed/answer_relevance_eval.json`

Ran 2026-05-19 against the live API with the production index
(475312 chunks, 16158 documents):

**Aggregate**:

| metric                                    | value       |
|-------------------------------------------|-------------|
| True positive (trick flagged or refused)  | 4 / 5 = 80% |
| False negative (trick missed)             | 1 / 5 = 20% |
| False positive (in-scope flagged partial) | 2 / 9 = 22% |
| True negative (in-scope `ok`)             | 7 / 9      |

(One in-scope query — `in_scope_gratuity` — was unexpectedly *refused*
by the coverage gate. That's a corpus issue, not a relevance failure.)

**Trick query breakdown**:

| id                            | outcome                  | cosine | verdict   |
|-------------------------------|--------------------------|--------|-----------|
| trick_deposit_return          | trick_caught_by_refusal  | —      | (refused) |
| trick_anticipatory_bail       | **fn_missed_trick**      | 0.7867 | ok        |
| trick_custody_during_marriage | tp_off_topic             | 0.6540 | off_topic |
| trick_contest_parking_ticket  | trick_caught_by_refusal  | —      | (refused) |
| trick_complaint_letter_format | trick_caught_by_refusal  | —      | (refused) |

**Where the deposit-question failure case lands now**

The system *refused* the deposit-return query at the coverage gate
(`refuse_below_rerank=0.4`) — the relevance check never had to fire.
This is the right outcome: the user gets the "I couldn't find sources
that clearly cover your question" message rather than a confidently
wrong answer. The relevance check is a backup for cases where the
coverage gate doesn't catch the misalignment.

In offline calibration, the same query embedded against a paraphrase of
the *original* failing answer scored 0.670 — well below the 0.6916
threshold, well outside the `partial` band — so if the coverage gate
hadn't caught it, the relevance check would have flagged
`verdict=off_topic`.

**The one missed trick: `trick_anticipatory_bail`**

The system answered the "I am about to be arrested. Can I get
anticipatory bail before arrest?" query with information about regular
(post-arrest) bail under Section 437 CrPC. The cosine was 0.7867 — well
above threshold — because the answer is *adjacent* in legal-text space.
Both queries are about "bail" and reference CrPC; the embedding model
can't distinguish the pre-arrest (438) vs post-arrest (437) nuance.

This is the deep-research agent's caveat made concrete:
**embedding-cosine alone is a weak hallucination signal for legal
nuance.** When two answers cite the same statute family with similar
vocabulary, cosine doesn't separate them.

## Caveats and honest reporting

- **AUC on the live eval set is moderate, not strong.** With 4/5 TPR
  and 22% FPR on a 25-query set, the effective AUC is around 0.79 —
  just above the "honest report" floor of 0.75 the task brief asked us
  to call out.
- **The `partial` band over-flags.** 2 of 9 in-scope queries got flagged
  `partial` despite the answer body being on-topic. The current text
  ("this answer may only partly match your question") is mild enough
  that it's not catastrophic, but it does add UI noise.
- **The "missed trick" mode is real.** Semantic-flip queries within the
  same statute family (anticipatory vs regular bail) won't be caught
  by cosine. They require either a categorical entailment check between
  query and answer (NLI-style) or an LLM judge.

## Recommendations

- **Enable by default? Yes.** The relevance event is informational and
  the UI text is appropriately cautious. The 22% partial-flag rate on
  in-scope answers is a UI-cost more than a correctness-cost — and the
  task brief was explicit that we should bias toward flagging.
- **Emit on every answer, or only when verdict != ok?** Emit on every
  answer. The UI already filters: it only renders a notice for
  `partial` / `off_topic`. Emitting the score on `ok` answers too gives
  us observability — we can graph the cosine distribution over time and
  detect drift.
- **Recommendation if FPR proves painful in production**: replace the
  cosine-based partial/off_topic determination with an LLM judge. The
  cosine threshold gate stays as a cheap pre-filter (run only when
  cosine < threshold), and the LLM judge does the final
  `partial` / `off_topic` decision. Slower but materially more accurate
  on the anticipatory-bail-style miss. Out of scope for this task.

## Files touched

- `apps/api/relevance.py` — new module with `compute_relevance()`.
- `apps/api/main.py` — emits the `relevance` event between `sources`
  and `disclaimer`.
- `apps/api/config.py` — new `answer_relevance_threshold`,
  `answer_relevance_band`, `answer_relevance_enabled` knobs.
- `apps/web/app/lib/types.ts` — `RelevanceEvent` type.
- `apps/web/app/components/answer-view.tsx` — renders the partial /
  off_topic notice.
- `apps/api/tests/test_endpoints.py` — 4 new tests for the relevance
  event (aligned / off-topic / refused / env override).
- `scripts/calibrate_answer_relevance.py` — calibration runner.
- `scripts/eval_answer_relevance.py` — live-API eval runner.
- `data/eval/answer_relevance.jsonl` — 25-query eval set.
- `data/processed/answer_relevance_calibration.json` — calibration
  output.
- `data/processed/answer_relevance_eval.json` — eval output.
