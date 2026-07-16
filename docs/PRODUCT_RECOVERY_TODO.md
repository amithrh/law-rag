# Product Recovery TODO

## Current Baseline

Status: not production ready.

The reproducible recovery baseline is committed and green locally and in remote
CI. The product is still not launch-ready: a fresh independent holdout run,
manual legal-quality review, and the operational/privacy gates below remain
open. The first ten released scenario families now use canonical MatterPlan v2
answer ownership; authority-registry coverage, guided intake, independent
holdout evaluation, learning governance, and production operations remain open.

P0 ownership baseline, 2026-07-11:

- API endpoint suite: `80 failed, 167 passed` after the first arbitration
  repair; the earlier baseline was `88 failed, 159 passed`.
- Current deterministic stabilization checkpoint: `1,319 passed` in the full
  API suite on 2026-07-11, including `131` common-workflow contracts and `247`
  endpoint tests. The last repairs covered source-gated safety,
  wage-deduction, MSME, criminal-procedure, answer-fact-retention, Hindu
  intestacy, civil summons service, and custodial-violence workflows.
- P0 revalidation on 2026-07-15 found and repaired an SC/ST authority-owner
  collision, an incorrect plan-derived Article 341 floor on an ST query, and a
  corpus-manifest `datetime.date` serialization failure. The authoritative
  post-repair API run completed with `1,333 passed, 0 failed` and `15` warnings
  in `378.99s` on 2026-07-15.
- Fresh local reproducibility evidence on 2026-07-15: `uv lock --check`, clean
  `npm ci`, frontend type-check, Python compileall, merged production Compose
  configuration, `/healthz` against the local Docker-backed Postgres corpus,
  and an aggregate corpus manifest all pass. The manifest records `747,574`
  active chunks and `26,270` documents; only `5,779` documents are currently
  provenance-verified, so P2 provenance remains open.
- The P0 independent review found the clean-clone corpus/CI smoke and startup
  documentation were incomplete. The follow-up adds an idempotent synthetic
  one-document seed and verifies a disposable pgvector schema plus FastAPI
  `/healthz` returns exactly `1` document and `1` chunk. The fixture is marked
  non-authoritative and is not legal corpus data.
- Remote CI run `29389877668` then exposed six hidden clean-clone dependencies:
  three endpoint tests needed the populated stack, two tests needed ignored
  eval datasets, and one reranker integration needed local model/runtime
  support. These are now explicit pytest markers; standard CI runs the
  deterministic clean-clone selection (`1,283 passed`, `50 deselected` with a
  deliberately unreachable database), while the full `1,333`-test local gate
  continues to cover all three environment-backed slices.
- Replacement remote CI run `29390974062` passed the deterministic API suite,
  Docker-backed pgvector seed/API health smoke, frontend type-check, and merged
  production Compose contract. This closes P0's remote reproducibility gate.
- P1A now emits canonical `matter_plan` schema v2 with deterministic plan IDs,
  canonical/provisional authority identity, exact retrieval-source descriptors,
  and runtime-aligned critical-route answer policy. Multi-query retrieval
  consumes the supplied plan and no longer reroutes or reselects source packs.
  The benchmark parser records the same event. Adversarial tests fail closed on
  section-only matches, neighboring laws, route-prose acronyms, generic/yearless
  authorities, duplicate source packs, and punctuation-equivalent Act names.
- P1A acceptance evidence: final independent review PASS, `1,341 passed` in the
  full API suite (`381.44s`), `110 passed` in the focused plan/retrieval/evaluator
  gate, two live-stack SSE checks, and frontend type-check green. This does not
  close P1: answer rendering, source-gap/eval authority-ID consumption, UI, and
  first-ten-route owner retirement remain open.
- P1B now makes the authority ledger a fail-closed serving and evaluation
  contract. Answer rendering and the browser require a valid MatterPlan before
  showing streamed legal sentences; runtime source-gap checks recompute strict
  authority IDs from title, anchor, source type, and retrieval pack; and the
  evaluator gives citation credit only to the final `sources` event visible to
  the user. Canonical and activated provisional obligations are measured by ID.
- P1B adversarial review caught and closed authority-free placeholder plans,
  old/new criminal-regime filtering errors, missing sections in composite
  requirements, fuzzy provisional-source matches, factual records reported as
  missing law, route-controlled benchmark denominators, and early-passage-only
  citations. Final evidence: both backend and evaluator/UI reviewers PASS,
  focused plan/source-gap/evaluator gate `195 passed`, frontend contract tests
  `4 passed`, frontend type-check and production build pass, integrated SSE
  contract passes, and the full API suite is `1,369 passed, 0 failed` with `15`
  warnings in `384.12s` on 2026-07-15.
- P1C retires legacy/freeform ownership for ten released high-volume or
  safety-sensitive scenario families: immediate domestic violence, hidden
  arrest/custody, identity-only LGBTQ arrest, vehicle-theft FIR refusal,
  loan-app harassment, criminal bank-account hold, wrongful bank debit,
  insurance claim/mis-selling, joint co-owner sale, and marital-intimacy
  remedy. Each plan names one exact source-gated owner, an explicit
  `source_gap_handoff`, and `allow_freeform_llm=false`.
- P1C also centralizes actor, case-stage, legal-regime, and negation predicates
  used by routing, source packs, and answer selection. It separates initial FIR
  refusal from an existing-FIR investigation complaint; criminal bank holds
  from civil/arbitral attachments; direct domestic harm from a threat by a
  tenant or other third party; and current, legacy, or unknown criminal-law
  regimes. Arbitration and pre-judgment attachment now fail closed before any
  legal sentence when their controlling source is missing.
- P1C live proof on the local `747,574`-chunk / `26,270`-document corpus:
  released-route gate `10/10`, adversarial-neighbour gate `9/9`, and exact
  reviewer/user-shaped gate `11/11`, including reported-spousal-threat pronoun
  binding. The final closed reviews are PASS, including architecture replay
  `69 prompts / 226 assertions / 0 failures`. The final broad ownership/API
  gate is `1,236 passed, 41 deselected` in `397.78s`; frontend contract tests,
  type-check, and production build also pass. This proves ownership and
  fail-closed behavior for this release slice, not overall legal coverage or
  production readiness.
- P2A establishes the first immutable authority-registry migration for CrPC
  1973 Section 436A. The packaged JSON manifest pins canonical identity,
  provision anchors, jurisdiction, temporal applicability and BNSS savings,
  official India Code URL, PDF byte hash, verbatim text hash, and retrieval
  declaration. The old one-off Section 436A backfill script is retired.
- P2A is upgrade-safe and chunk-scoped: migration 005 upgrades legacy source,
  document, chunk, audit, and registry schema; existing whole-document
  verification is preserved; changed provisions reset only their exact chunk;
  superseded projections are quarantined; and one authority ID can have only
  one active corpus projection. Required-source retrieval consumes the same
  provenance gate as normal retrieval.
- P2A acceptance evidence: legal and architecture reviews PASS; wheel import
  and migration dry-run pass; an isolated legacy-schema PostgreSQL test proves
  upgrade, idempotence, rollback, source-origin correction, per-chunk
  verification, and corrected-anchor retirement; and the broad
  route/retrieval/API gate is `1,291 passed, 41 deselected` in `400.62s`. A
  live official-source audit matched the pinned PDF SHA-256 and Section 436A
  text (`0.984375` similarity), promoted only the mapped chunk, and the live
  `/answer` replay returned the canonical authority/source without refusal.
  This completes the registry pilot, not P2 coverage.
- P2B extends the immutable registry to the released RBI grievance family and
  its conditional criminal/privacy overlays. Migrations `0002`-`0005` now own
  RBI Integrated Ombudsman Scheme Clauses 1, 3, 6, 9, and 10; Digital Lending
  Directions paragraphs 11 and 12; the recovery-agent harassment paragraph;
  IT Act Section 66E; and BNS Section 308. The `wrong_bank_debit` and
  `loan_app_harassment` workflows consume registry keys directly instead of
  rebuilding authority identity from titles or source-pack prose.
- P2B retrieval expands the result window when a plan has more mandatory
  authorities than `top_k`, joins through `document_authorities`, and refuses
  before emission if a fully retrieved registry authority set is not actually
  cited in the candidate answer. Current private-image payment threats add BNS
  Section 308 only for an unambiguous current regime; IT Act Section 66E is
  described narrowly and is not presented as a general morphed-image offence.
- P2B deterministic evidence is green: authority/ownership `288 passed`,
  retrieval/source-gap `134 passed`, workflow/source-pack `413 passed`,
  router/endpoint `469 passed`, migration stack `2 passed`, wheel build and
  wheel-content checks pass, and the official BNS Section 308 projection
  passed exact provenance verification. Live `/answer` checks passed for
  wrongful debit, contact harassment, and current payment-linked morphed-image
  blackmail with every expected registry key present, no source gap/refusal,
  and no weak/unsupported legal sentence. A bank-freeze near miss did not
  inherit the new registry workflows, but exposed two existing weak-support
  bridge sentences; that remains a production blocker outside this slice.
- P2B is not closed until a post-implementation independent review is recorded.
  The review service reached its child-thread limit during the final gate; this
  is an explicit open gate, not an inferred PASS from tests.
- This is a regression result, not launch evidence. A fresh 500-prompt
  human-style evaluation, independent legal-quality review, and the operational
  release gates remain required before any production claim.
- The latest labour batch permits a detailed template only when its controlling
  source is present: ISMW registration, Code on Wages wage/minimum-wage,
  Contract Labour wage responsibility, BOCW register/cess fraud, or ISMW
  return-fare sources. A broad labour workflow remains the fallback otherwise.
- Criminal composite requirements now select the applicable statutory pair from
  the incident date, not a later reporting date: `IPC + CrPC` for explicit
  pre-cutover incidents and `BNS + BNSS` for current incidents. This does not
  weaken the source-gap policy for incidents whose date is still unknown.
- Bonded-labour coercion now has one source-gated safety owner only when the
  Bonded Labour Act section 12 inquiry/action source is retrieved. It renders
  a District Magistrate/SDM rescue record, preserves separate wage/document/
  police tracks when sourced, and cannot take an ordinary wage claim.
- A marketplace delisting/IP-counter-notice question now outranks generic
  trademark cease-and-desist advice only when Trade Marks Act section 29 or
  134 is retrieved. Ordinary trademark notices and weak-source neighbors keep
  their normal workflow.
- The 80 failures contain 127 answer calls. They cluster around a small group
  of broad owners, led by tribal/forest access, generic criminal defence,
  false-FIR defence, bonded-labour rescue, and cyber-harassment workflows.
- This is not launch evidence or a quality score. It is a migration inventory:
  each cluster must be resolved through one explicit owner and source policy,
  not test-by-test text matching.

This checklist is ordered by dependency. Do not begin a later phase merely
because a focused prompt slice passes.

## P0: Establish a Reproducible Baseline

- [x] Identify which current dirty changes are intentional and split them into
  scoped commits for serving/runtime, evaluation, authority backfills, and
  governance/operations. Local corpus, model, environment, and result data are
  excluded from the checkpoint.
- [x] Restore the full API suite to green: `1,333 passed, 0 failed` on
  2026-07-15. Current command: `PYTHONPATH=. .venv/bin/pytest apps/api/tests -q`.
- [x] Fix pytest configuration so the default command covers `apps/api/tests`.
- [x] Add ownership auditing for scored evals. Unexpected answer owners and
  critical LLM-owned rows now fail `scripts/audit_answer_ownership.py` unless
  an explicit review run uses `--allow-fail`.
- [x] Add non-interactive CI for API tests, frontend type-check, and syntax
  checks, plus a Docker-backed pgvector schema, synthetic seed, and `/healthz`
  API startup smoke. Remote run `29390974062` is green.
- [x] Update README and Makefile to match the real implementation; remove stale
  "pre-implementation" claims and placeholder eval commands.
- [x] Create `scripts/corpus_manifest.py`, an aggregate-only corpus/runtime
  snapshot with document/chunk counts, source timestamps, embedding versions,
  provenance breakdown where the schema supports it, and an explicit bootstrap
  SQL schema fingerprint. It records that no migration table exists rather than
  inventing a migration version.

Exit gate: clean worktree, committed baseline, zero API test failures, CI green,
and a documented local startup path.

## P1: Replace Competing Answer Owners

- [x] Define `MatterPlan v2` as the canonical schema for issue, role, state,
  incident date, case stage, desired outcome, required facts, authority ledger,
  forum, remedies, deadlines, documents, safety flags, and confidence.
- [x] Make routing emit `MatterPlan v2`, not only `MatterRoute` plus free-text
  action-pack fields.
- [x] Make retrieval consume MatterPlan's exact authority/retrieval policy rather
  than independently rerouting and inferring source packs from overlapping
  keyword logic.
- [x] Make answer rendering and UI visibility consume the same plan; invalid,
  missing, interrupted, or authority-free plans cannot reveal legal sentences.
- [x] Migrate the first ten high-volume/safety routes to the plan owner and
  retire their legacy template branches.
- [x] Make source-gap checks and eval scoring consume plan authority IDs instead
  of duplicated title/anchor alias heuristics.
- [x] Add an ownership test: each supported scenario has exactly one primary
  answer owner and an explicit fallback policy.

Exit gate: the first ten high-volume/safety routes have one plan, one authority
policy, one answer owner, and no `main.py` special-case fallback.

## P2: Build the Authority Registry and Coverage Matrix

- [ ] Create declarative authority records for Act, section, jurisdiction,
  effective date, canonical URL, publisher, provenance status, and verbatim
  status.
  Complete for CrPC 1973 Section 436A and the P2B RBI/IT Act/BNS authority
  family listed in the current baseline; remaining released authorities still
  need migration into the registry.
- [ ] Add relationships: issue -> conditions -> authority -> remedy -> forum ->
  deadline -> documents -> escalation.
  Complete for `wrong_bank_debit` and `loan_app_harassment`; remaining released
  scenarios still need registry-owned workflow relationships.
- [ ] Replace one-off `add_*` scripts with repeatable ingestion migrations tied
  to authority-record IDs.
  The Section 436A one-off script is replaced by migration
  `0001_crpc_436a`; P2B uses migrations `0002`-`0005` and deterministic
  manifest builders. Other one-off corpus patches remain to be inventoried and
  migrated.
- [ ] Define supported geography: national law plus a verified set of states.
  Unsupported state-law matters must use a source-gap/handoff policy.
- [ ] Enable provenance verification in production configuration and add a
  freshness/refetch job with review on source drift.
- [ ] Re-run a hand-labelled retrieval benchmark without required-source pack
  injection and publish recall@K by authority family.

Exit gate: every released action pack has a reproducible verified source trail;
unsupported state routes cannot silently borrow a neighboring state law.

## P3: Add Guided Intake and Action-Pack UX

- [ ] Add a follow-up engine that asks at most three facts when state, incident
  date, role, amount, case stage, or desired outcome changes the plan.
- [ ] Persist a short-lived redacted matter session so follow-ups update the
  existing plan rather than restarting from the original text box.
- [ ] Render plan sections: immediate safety, what applies, what to collect,
  first authority/forum, deadline risk, and escalation.
- [ ] Add explicit source-gap and jurisdiction-coverage cards with legal-aid or
  lawyer handoff.
- [ ] Build reviewed action packs for the first supported product lanes:
  FIR/arrest, cyber, domestic safety, consumer/banking, labour/wages,
  property/tenancy, welfare/identity, and court procedure.
- [ ] Defer legal-document generation until action-pack quality passes review.

Exit gate: usability testing shows users can complete the intake and identify a
next action without guessing which state/date/document details matter.

## P4: Create Credible Evaluation and Review

- [ ] Freeze the known-failure regression set and prohibit it from serving as
  launch evidence.
- [ ] Commission an independently labelled holdout with lawyer/manual review;
  include messy language, Hinglish, role ambiguity, state/date traps, and
  legal-but-unsupported questions.
- [ ] Add a rubric for route correctness, authority correctness, forum,
  deadline, actionability, source fidelity, and harmful framing.
- [ ] Add blinded human review for a statistically meaningful sample of answers.
- [ ] Record confidence intervals and per-route results, not only one aggregate
  product-pass score.
- [ ] Require all changes to compare regression, locked holdout, and latency
  before merge.

Exit gate: at least 200 true holdout rows, zero dangerous framing on critical
rows, no source-gap concealment, and no regression against the frozen set.

## P5: Add a Controlled Learning Loop

- [ ] Write redacted answer telemetry to `query_log`: matter plan, sources,
  citations, source gap, verifier status, latency, and refusal reason.
- [ ] Add explicit helpful/not-helpful feedback and a secure review queue.
- [ ] Define retention, deletion, consent, access controls, and PII redaction
  before storing query text or answer text.
- [ ] Turn reviewed failures into versioned datasets with provenance and split
  metadata.
- [ ] Train a route/fact classifier first, then a reranker on reviewed
  query-authority pairs.
- [ ] Require locked-holdout gains before enabling a trained model in serving.

Exit gate: no automatic policy changes from user data; every learning artifact
is reviewed, versioned, reproducible, and independently evaluated.

## P6: Production Operations

- [ ] Add authentication, authorization, rate limiting, abuse controls, and
  request-size/time limits.
- [ ] Complete the PII release gate and test it on a hand-labelled corpus.
- [ ] Implement encrypted backups, restore drills, deployment rollback, and
  incident runbooks.
- [ ] Pin container images and model versions; remove floating `latest` tags.
- [ ] Add production health/readiness checks, alerting for source gaps/refusals,
  and route-level quality dashboards.
- [ ] Run load, security, privacy, and disaster-recovery tests before launch.

Exit gate: the application can be safely operated, monitored, recovered, and
audited beyond a local developer machine.

## Explicit No-Go Rules

- [ ] No production claim while a true holdout set is absent.
- [ ] No production claim while critical routes can be answered by a freeform
  LLM without a reviewed action pack.
- [ ] No production claim while provenance verification is disabled for surfaced
  controlling sources.
- [ ] No production claim while the full API suite is failing.
- [ ] No generator fine-tuning until P1-P5 are complete.
