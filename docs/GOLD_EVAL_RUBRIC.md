# Gold eval set — annotation rubric

**Status:** stage 1 of training plan. Drafted 2026-05-21.
**Goal:** 200 labeled queries to calibrate everything downstream.
**Output:** `data/labeled/gold_v1.jsonl` — one row per query.

## Why this exists

Every eval we've run so far (v2 → v6) has been calibrated by
intuition. Cosine threshold 0.62 vs 0.55 — we have no labeled positives
in that range. We've been arguing about parameters with no ground
truth. **All training stages depend on this set.**

## The structure of a labeled row

```jsonl
{
  "query": "my son threw me out of the house after I gave him my property",
  "category": "senior",
  "complexity": "lay",
  "source": "user_screenshot_2026_05_18",

  "operative_acts": ["senior-citizens-2007"],
  "operative_sections": ["senior-citizens-2007/sec-23"],
  "acceptable_bare_act_anchors": [
    "senior-citizens-2007/sec-23",
    "senior-citizens-2007/sec-4",
    "transfer-of-property-1882/sec-126"
  ],
  "acceptable_sc_anchors": [
    "2020-insc-701",
    "2022-insc-1257"
  ],
  "correct_refusal": false,

  "ideal_answer_signals": [
    "section 23 of Senior Citizens Act 2007",
    "revocation of gift / transfer",
    "Tribunal under section 7",
    "S. Vanitha v. Deputy Commissioner (landmark)"
  ],
  "wrong_answers_to_flag": [
    "general criminal trespass under BNS",
    "Specific Relief Act civil remedy"
  ],

  "labeler": "claude_draft / amit / lawyer_X",
  "labeled_at": "2026-05-21",
  "confidence": "high / medium / low",
  "notes": ""
}
```

## Field semantics (the rubric)

### `query`
Verbatim string. **Don't sanitize lay grammar.** If the user said
"my landlord is not retyurning my deposit", keep the typo.

### `category`
One of: `family`, `senior`, `property`, `consumer`, `criminal`,
`employment`, `wages`, `cyber`, `tax`, `finance`, `education`, `women`,
`constitutional`, `procedure`, `motor`, `succession`, `misc`,
`off_corpus`. Match the existing eval categories.

### `complexity`
- `lay` — uses everyday words, no legal terms
- `mixed` — partly lay, partly legal ("section 138 cheque bounce")
- `legal` — uses correct statutory phrasing

This lets us measure improvement separately on each tier.

### `source`
Where did the query come from?
- `eval_v6_row_N` — re-use from our 102 eval (slot N)
- `user_screenshot_<date>` — the user's UI tests
- `nalsa_faq` — adapted from NALSA citizen guides
- `textbook_<book>_<chapter>` — from law school texts
- `intake_example` — adapted from public legal-aid intake records

### `operative_acts` (REQUIRED)
List of `doc_id` values for acts that DIRECTLY answer the query.
Usually 1, sometimes 2 (e.g. PWDVA + IPC s.498A for domestic violence).
**Identifiers must match `documents.doc_id` in our DB.**

### `operative_sections` (REQUIRED if not refusal)
Specific anchors. Format: `<doc_id>/sec-<N>` matching our chunk
schema. Example: `senior-citizens-2007/sec-23`. If the answer requires
a whole chapter, list the lead section.

### `acceptable_bare_act_anchors`
**Superset of `operative_sections`.** Includes alternates that would
also be a correct retrieval — adjacent sections, fallback Acts,
procedural sections. Used to compute "did retrieval return SOMETHING
useful" recall.

### `acceptable_sc_anchors`
Landmark SC cases on this question. Format: `<insc-anchor>` (no `#para`
needed; we'll match prefix). The system answer is allowed to cite ONLY
these SC cases (without bare-act) and still be considered correct for
queries where SC interpretation IS the operative law (e.g. Article 21
queries).

### `correct_refusal`
`true` if the query is genuinely off-corpus or unanswerable. The
system SHOULD refuse. Used to test calibration of the refuse-gate
without false positives.

### `ideal_answer_signals`
List of phrases that a correct answer SHOULD contain. Used post-hoc to
spot-check whether the LLM body matched the expected content. NOT
auto-graded — just shown to a human reviewer.

### `wrong_answers_to_flag`
Common-wrong-direction patterns. The deposit-money-in-court mistake
from the screenshot would be:
```
"wrong_answers_to_flag": [
  "depositing rent IN court (opposite money flow)",
  "Specific Relief Act civil suit (longer route)"
]
```

### `confidence`
- `high` — operative section is unambiguous, no edge cases
- `medium` — operative section is correct but other answers exist
- `low` — multiple operative routes possible, label is best-effort

Low-confidence rows get manually reviewed before being used in
recall metrics.

## Annotation process

1. Start from 30 queries pulled from `data/processed/e2e_eval_*.jsonl`
   (the existing 102-query eval). Claude drafts proposed labels.
2. Amit reviews + corrects. Disagreements are notes.
3. After 30 done, pull next 30. Iterate.
4. At row 60, compute Cohen's Kappa on the overlap subset. Adjust the
   rubric if Kappa < 0.7.
5. At row 200, freeze v1. Subsequent additions go in v2 file.

## Quality bar

A row is "ready" when:
- [ ] All required fields populated
- [ ] `operative_sections` ids exist in our `documents` table
- [ ] `acceptable_sc_anchors` exist in our `documents` table (or were
      mined from a public source we can later ingest)
- [ ] `wrong_answers_to_flag` has at least one entry for non-trivial
      queries (the existence of a misdirection class is the point)
- [ ] confidence is set

## What we measure with this set

| Metric | Definition |
|---|---|
| `recall@K_strict` | did `operative_sections` appear in top-K retrieval |
| `recall@K_acceptable` | did any `acceptable_bare_act_anchors` ∪ `acceptable_sc_anchors` appear in top-K |
| `topical_grounding` | does the answer cite at least one acceptable anchor |
| `refusal_precision` | of refused queries, how many were `correct_refusal` |
| `refusal_recall` | of `correct_refusal` queries, how many did the system actually refuse |
| `misdirection_rate` | fraction of answers that contained a `wrong_answers_to_flag` pattern |

## Out of scope for v1

- Multi-turn conversations (handled later)
- Vernacular language queries (Hindi/Tamil — track for v2)
- Cross-jurisdictional comparisons
- Time-bounded queries ("as on 1 April 2026" — covered separately via `as_at`)

## Files

- `data/labeled/gold_v1.jsonl` — the labels themselves (gitignored;
  contains real intake-style queries that could be PII-adjacent)
- `data/labeled/gold_v1_schema.json` — JSON schema for validation
- `scripts/eval_gold.py` — runs the metrics against any eval JSONL
  (to be created when first ~50 rows are labeled)
