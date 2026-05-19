# Verifier backend swap — NLI vs bge vs ensemble

Architecture-research task #2 — investigate whether the existing
`bge-reranker-v2-m3` cross-encoder used at retrieval time can also serve
as the per-sentence verifier, either replacing the DeBERTa-MNLI scorer
("bge backend") or running alongside it ("ensemble backend") for a
tighter fail-closed gate.

## Why

Two payoffs if bge alone is sufficient:

  1. **~1.5 GB RAM freed.** DeBERTa-v3-large-mnli is loaded purely for the
     verifier; the reranker is already resident for retrieval.
  2. **+pass-rate** on legal English. MNLI is not trained on legal
     paraphrase, and round-7 traces showed a stubborn 10–25% weak_support
     rate on otherwise-correct cited sentences.

The risk: bge is a *relevance* scorer (cross-encoder ranking), not a
categorical entailment model. Negation and contradiction may not be
detected. So this swap is honest only if (a) the bge score correlates
with answer-support on real cited sentences, and (b) calibrated
thresholds suppress fabrication.

## Calibration (script: `scripts/calibrate_bge_verifier.py`)

Inputs: the most recent battery v3 trace
(`battery_v3_20260519-010820.json`), 250 cited sentences whose NLI status
is already in the trace.

Method:
  1. Pull each cited passage's text from Postgres by anchor.
  2. Score every (passage, sentence) pair with `bge-reranker-v2-m3`,
     take MAX across cited passages (matches the live verifier's NLI
     aggregation).
  3. Sweep candidate thresholds; pick the largest T where
     `precision(bge >= T against NLI=OK) >= 0.90`.
  4. Hard floor = 5th percentile of bge scores on NLI=WEAK sentences.

`sentence-transformers` applies a sigmoid in `CrossEncoder.predict` by
default, so bge scores fall in **[0, 1]** in practice (the raw-logit
[-10, +10] range from the BAAI paper is what you'd see only if you
disabled the activation).

### Results

| stat                         | value  |
|------------------------------|--------|
| pairs scored                 | 250    |
| NLI = ok                     | 214    |
| NLI = weak_support           | 36     |
| bge median when NLI=ok       | 0.877  |
| bge p10 when NLI=ok          | 0.196  |
| bge median when NLI=weak     | 0.395  |
| bge p90 when NLI=weak        | 0.974  |
| **best threshold (P≥0.90)**  | **0.222** |
| recall at best threshold     | 0.846  |
| hard floor (p05 of NLI=weak) | 0.003  |

### Headline finding

**bge and NLI agree where it matters, but they DISAGREE about which
sentences are weak.** The 90% precision at T=0.222 is real, but the
underlying confusion matrix is revealing:

  - **13/36 NLI-weak sentences score bge > 0.5** — bge would PASS them.
    On inspection these are legitimate-but-paraphrased legal claims
    (e.g. "Section 156(3) gives the Magistrate the authority to direct
    registration") that NLI's general-purpose MNLI model handles poorly.
    **bge is more forgiving of legal paraphrase than NLI.**

  - **22/214 NLI-OK sentences score bge < 0.222** — bge would SUPPRESS
    them. On inspection these are short procedural-step bullets
    ("Keep copies of your employment records", "File a complaint with
    the appropriate consumer forum") where the cited passage doesn't
    specifically discuss the step. **bge is stricter about
    relevance-to-the-specific-claim than NLI's entailment threshold.**

These aren't symmetric errors — they reflect a real design difference.
NLI asks "does the passage logically support this hypothesis?"; bge asks
"is this passage the right place to look for this claim?" Both are
defensible guarantees but they're not the same guarantee.

## Battery v3 results: NLI vs bge vs ensemble

(Pass-rate = "any pass variant" in the v3 scoring: in-slice pass,
pass-refused, or out-of-slice pass-answered.)

| backend  | pass | in-slice pass | stop | fail | refused | median latency | source |
|----------|------|---------------|------|------|---------|----------------|--------|
| NLI      | 42/50 (84%) | 24/41 (59%) | 8 | 0 | 14 | 33.4s | `battery_v3_20260519-010820.md` (baseline) |
| **bge**  | **46/50 (92%)** | **27/41 (66%)** | **0** | 4 | 14 | **16.7s** | `battery_v3_bge.md` |
| ensemble | 41/50 (82%) | 22/41 (54%) | 6 | 3 | 14 | 16.4s | `battery_v3_ensemble.md` |

### bge backend takeaways

- **+4pp overall pass-rate (+7pp in-slice).** Headline number is real
  and consistent with what the calibration suggested (bge is more
  forgiving of legal paraphrase than MNLI).
- **Zero stops** — every query produced enough OK sentences to not hit
  the stop banner. NLI baseline had 8 stops, several driven by
  legitimate but paraphrased holdings scoring below the 0.35 weak
  threshold and tripping the skip-ratio guard.
- **But 4 new "fail" verdicts** (≥2 OK + ≥50% weak ratio) on family
  and wages. bge marks generic procedural-bullet content
  ("File a complaint…", "Keep copies of…") as weak because the cited
  passage doesn't specifically discuss the procedural step. The
  citation guarantee is still upheld — these sentences are flagged
  weak, not OK — but it surfaces as more "this answer is shaky" UI
  noise.
- **Latency halved** (16.7s vs 33.4s median). bge is already in memory
  for retrieval; one additional cross-encoder call per sentence is
  cheaper than spinning up DeBERTa-large and running it on CPU/MPS.

### ensemble backend takeaways

- **-2pp overall pass (-5pp in-slice) vs NLI baseline.** Pessimistic
  AND is too strict on this corpus: every sentence that EITHER
  backend marks weak/unsupported becomes weak/unsupported in the
  ensemble verdict. Because the two backends disagree on which
  sentences are weak (per the calibration headline finding), the
  AND surfaces the UNION of weak verdicts rather than the
  intersection of confident ones.
- **6 stops** (vs NLI's 8, bge's 0) — ensemble preserves NLI's
  tendency to stop on legitimate-but-paraphrased content AND adds
  bge's tendency to stop on generic-bullet content, getting the
  worst of both.
- **Latency same as bge** (16.4s vs 16.7s) because NLI inference
  runs on the same CPU/MPS tier as bge in this configuration. The
  ensemble cost is largely token-budget-dominated.

## Recommendation

**Default to `bge` once the user reviews this report.** Rationale:

  - **bge wins on every operational metric:** +4pp overall pass-rate,
    +7pp in-slice pass-rate, zero stops (vs 8 on NLI), and ~50%
    lower latency. The headline +3-5pp target from the
    architecture-research roadmap is hit.
  - **Ensemble actively HURTS pass-rate** on this corpus (-2pp vs NLI
    baseline). The pessimistic AND surfaces the union of weak verdicts
    from two backends that disagree about which sentences are weak.
    The two safety nets are not complementary here — they're
    independently strict in non-overlapping ways. Combining them
    gives the worst of both.
  - **Ensemble does still preserve the strictest citation guarantee.**
    Every sentence that ships under ensemble has cleared both bge AND
    NLI. The cost is shipping fewer sentences overall.
  - **Retiring NLI saves ~1.5 GB RAM** and a model-download cost on
    cold start, both already-resident-bge being the active backend.

The current default in `config.py` is `ensemble` so a code review can
land first without changing user-facing behaviour. A follow-up PR
should flip the default to `bge` once the calibration is audited.
The thresholds and floor in `config.py` are populated by the
calibration script — recalibrate on corpus or model changes.

## Open caveats / future work

  - **Calibration uses NLI as reference, not ground truth.** A human
    label pass on ~100 cited sentences would let us assert which
    backend is actually more accurate, not just which agrees with the
    other.
  - **bge's blind spot on contradiction was not stress-tested.** The
    calibration set was the cited-sentences-that-already-passed-NLI
    population — contradicting hypotheses had been suppressed
    upstream. Before retiring NLI fully, run a targeted eval with
    deliberate contradictions (e.g., paraphrased holdings flipped to
    negation) to confirm bge's hard floor still catches them. This
    is the strongest argument for keeping NLI available as a fallback.
  - **bge over-suppresses generic procedural bullets.** The 4 fails on
    bge battery v3 trace back to "What you can do next" bullets
    ("File a complaint…", "Keep copies of your employment records").
    Two options: (a) tune `bge_verifier_threshold` lower for higher
    recall at the cost of some precision; (b) write a content-filter
    that exempts procedural-bullet phrasing from the relevance
    requirement (analogous to the META preamble whitelist).
  - **Ensemble UI surface.** `entailment_score` becomes the NLI score
    when both backends scored, but the bge score is hidden. If the
    ensemble backend stays available, the UI should surface both (one
    badge per backend) so operators can debug disagreements without
    re-running.
  - **Threshold sensitivity.** The 0.222 threshold was picked at
    precision ≥ 0.90 on a 250-pair set. With only 36 NLI-weak
    examples, precision is noisy at extreme thresholds — a larger
    battery (200-500 queries) would tighten the bounds.
