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
- P2C adds a registry-owned hidden-arrest/custody family. Migration `0006`
  declares Constitution Articles 22 and 226, BNSS Sections 1, 36, 37, 47, 48,
  57, 58, and 531, and legacy CrPC Sections 41B, 41C, 50, 50A, 56, and 57.
  Current, legacy, saved-pending, unknown-date, and Nagaland/tribal-area paths
  activate different sets; property custody, voluntary absence, and notice-only
  questions do not inherit the workflow.
- The enacted MHA Gazette is the pinned BNSS source because the available India
  Code PDF extraction duplicated neighboring text for Section 58. All `16/16`
  custody records are bound to exact official PDF hashes and verified corpus
  projections. Public control-room information is kept separate from private
  intimation to a person disclosed or nominated by the arrested person.
- Migration `0007` separates authorities required in retrieval from authorities
  that every answer must cite. The full legal pack remains retrieved while only
  non-duplicative, user-essential safeguards fail closed at answer time.
- P2C evidence: the final shared-route regression slice is `161 passed`; full
  non-stack API gate `1,673 passed, 43 deselected`; full real-stack gate `43 passed, 1,673
  deselected`; wheel build/content/runtime-policy check passed; and migration
  `0007` dry-run/application passed. The broad run also repaired an
  implied-subject arrest expansion miss and added CPU retry when MPS reranking
  fails instead of silently preserving dense order. A second broad run caught
  and closed two cross-route regressions before release: property phrases such
  as `worker ID cards` cannot become human custody, and relative-date handling
  cannot silently change an unrelated trafficking source pack.
- P2C live `/answer` evidence is `8/8`: unknown date, current BNSS, legacy CrPC,
  saved-pending transition, Nagaland scope, and three negative neighbors. Every
  positive returned its exact expected registry set with no source gap,
  refusal, weak-support, unsupported, or suppressed sentence. Independent
  review remains open after three final retries because the reviewer service reports
  `agent thread limit reached`; this is not a production-readiness claim.
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
  Complete for CrPC 1973 Section 436A, the P2B RBI/IT Act/BNS family, and the
  P2C constitutional/BNSS/CrPC hidden-custody family; remaining released
  authorities still need migration into the registry.
- [ ] Add relationships: issue -> conditions -> authority -> remedy -> forum ->
  deadline -> documents -> escalation.
  Complete for `wrong_bank_debit`, `loan_app_harassment`, and
  `arrest_custody_station_case_not_disclosed`; remaining released scenarios
  still need registry-owned workflow relationships.
- [ ] Replace one-off `add_*` scripts with repeatable ingestion migrations tied
  to authority-record IDs.
  The Section 436A one-off script is replaced by migration
  `0001_crpc_436a`; P2B uses migrations `0002`-`0005`; P2C uses authority
  migration `0006` and workflow-policy migration `0007`, all with deterministic
  builders. Other one-off corpus patches remain to be inventoried and migrated.
- [ ] Define supported geography: national law plus a verified set of states.
  Unsupported state-law matters must use a source-gap/handoff policy.
- [ ] Enable provenance verification in production configuration and add a
  freshness/refetch job with review on source drift.
- [ ] Re-run a hand-labelled retrieval benchmark without required-source pack
  injection and publish recall@K by authority family.

### P2D-P2E progress (2026-07-16)

- [x] Add a registry-owned bank account legal-hold family with RBI, BNSS 106,
  and CrPC 102 authority records and regime-aware conditions.
- [x] Keep ED/PMLA bank freezes out of the ordinary bank-hold workflow; the
  PMLA route fails closed until it has its own reviewed authority contract.
- [x] Make generic platform KYC holds require only the IT/Consumer sources
  supported by their facts; add regulated-payment and real-money-gaming gates
  only when those facts are present.
- [x] Remove the duplicate unreachable PMLA/ED route block and lock its route
  precedence with regression tests.
- [x] Refresh and verify BNSS 106 and CrPC 102 against their official source
  bytes; prove current and legacy bank-freeze prompts retrieve positive-ID,
  verified runtime chunks without registry backfill.
- [x] Add a PMLA/ED asset-freeze authority contract with verified Sections 5,
  17, 8, and 26, exact path selection, natural retrieval proof, and fail-closed
  serving. Ambiguous order wording checks both paths; stale undated projections
  are retired and rejected by the answer gate. Final independent review remains
  the stage-close gate.

Exit gate: every released action pack has a reproducible verified source trail;
unsupported state routes cannot silently borrow a neighboring state law.

## P3: Add Guided Intake and Action-Pack UX

- [x] Add a follow-up engine that asks at most three facts when state, incident
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

P3 implementation progress, 2026-07-17: the bounded follow-up event, route
specific question set, emergency-first safety prompt, schema validation,
privacy note, and stale-stream protection are implemented and independently
reviewed PASS. This does not close P3: answers are intentionally not persisted
yet, and usability testing plus the full eight-lane action-pack review remain
open.

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

## Active Execution Checklist

This is the ordered delivery checklist. A stage is not complete because code
exists; it closes only when its evidence gate is met and an independent review
has been recorded.

### Stage 1: Finish Authority-Owned P2 Workflows

- [ ] Measure uninjected retrieval recall@8 for every released authority family.
- [x] Repair natural retrieval of BNSS Section 106 and CrPC Section 102 for
  bank legal-hold cases; regression requires positive-ID, provenance-verified
  chunks and rejects registry backfill.
- [x] Add a PMLA/ED asset-freeze authority contract, source packs, answer
  ownership, verified natural retrieval, and fail-closed tests for Sections 5,
  17, 8, and 26. Closure evidence: immutable alias-retirement repair `0016`,
  full-chain rollback-isolated PostgreSQL coverage, `39` authority tests,
  focused real-stack `4` tests, verified release wheel, and independent PASS.
- [ ] Select the next high-volume routes using actual failure evidence, then
  migrate each to an authority-owned workflow with conditions, remedies,
  forums, documents, and deadlines.
- [ ] Define supported state/jurisdiction coverage and make unsupported local
  law routes visibly hand off rather than infer a neighboring rule.
- [ ] Review each P2 slice independently and run the focused plus broad API
  regression suites.

P2 exit gate: every released action pack has verified authority provenance,
retrieval recall is measured without source-pack injection, and unsupported
state/PMLA routes fail closed.

### Stage 2: Build Guided Intake and Action UX

- [x] Add a follow-up decision engine limited to three material questions.
- [ ] Cover state, incident date, role, amount, authority/court stage,
  documents, and desired outcome where each changes the route.
- [ ] Persist a short-lived redacted matter session for follow-up answers.
- [ ] Render a consistent action plan: urgent safety, legal lane, evidence,
  first authority, deadline risk, and escalation.
- [ ] Make source gaps and unsupported geography understandable and actionable.
- [ ] Conduct usability tests on the first eight supported product lanes.

P3 exit gate: users can identify their next action and the missing fact that
changes it, without guessing how to phrase another prompt.

### Stage 3: Prove Quality on Independent Data

- [ ] Freeze known failures as regression data and exclude them from launch
  evidence.
- [ ] Create a fresh 1,000-prompt holdout with messy English, Hinglish,
  incomplete facts, state/date traps, role ambiguity, and unsupported matters.
- [ ] Label route, authority, citation support, forum, actionability, refusal,
  dangerous framing, and latency for every row.
- [ ] Obtain blinded lawyer or trained-human review for a meaningful sample.
- [ ] Publish per-route results and confidence intervals, not one aggregate.
- [ ] Block merges that regress locked holdout, safety, or latency.

P4 exit gate: at least 200 independently reviewed holdout rows, zero dangerous
framing on critical rows, no concealed source gaps, and no regression against
the locked benchmark.

### Stage 4: Build a Controlled Learning Loop

- [ ] Implement redacted telemetry with plan, source, citation, verifier,
  source-gap, latency, and refusal metadata.
- [ ] Add helpful/not-helpful feedback and a protected human review queue.
- [ ] Complete consent, retention, deletion, access, and PII-redaction rules.
- [ ] Convert reviewed failures into versioned, provenance-tagged datasets.
- [ ] Train routing and reranking only after data review; do not fine-tune the
  answer generator first.
- [ ] Require a locked-holdout improvement before enabling any trained model.

P5 exit gate: learning is reviewed, reproducible, privacy-safe, and cannot
silently change legal-answer policy.

### Stage 5: Production Operations and Release

- [ ] Add authentication, authorization, rate limits, abuse controls, and
  request size/time limits.
- [ ] Enable production provenance verification and source freshness review.
- [ ] Add health/readiness checks, route-level quality dashboards, source-gap
  and refusal alerts, and incident runbooks.
- [ ] Implement encrypted backups, restore drills, deployment rollback, and
  pinned model/container versions.
- [ ] Run load, security, privacy, and disaster-recovery tests.
- [ ] Run final independent 1,000-prompt evaluation after the release
  candidate is frozen.

P6 exit gate: the service is secure, monitored, recoverable, auditable, and
meets the locked quality gates on the exact release candidate.

### 2026-07-17 Holdout RCA and Provenance Stage

- [x] Run a fresh 500-request live holdout through `/answer`; record quality,
  refusal, source-gap, provenance, safety, ownership, and latency metrics.
- [x] Confirm the dominant failure is not latency: `p50 4.7s`, `p90 17.5s`,
  with `122/485` expected Act hits and `219/500` usable answers.
- [x] Trace the quality loss to official Acts present in the corpus but still
  excluded by the fail-closed `provenance_verified` retrieval gate.
- [x] Repair India Code handle-page artifact discovery with tolerant parsing,
  bounded retry, candidate scoring, and focused regression tests.
- [x] Pin the independently checked NDPS official artifact hash and byte size,
  run strict verification, and promote only the compared local document; no
  corpus/evaluation data is committed.
- [x] Make hashless verification diagnostic-only, compare legacy documents
  independently over complete chunks, isolate temporary downloads, retry
  transient fetch failures, and add a strict nonzero release mode.
- [ ] Verify the remaining high-frequency official Act sources and inspect
  every promotion audit before re-running the holdout.
- [ ] Re-run the same 500 holdout after the authority batch and publish the
  before/after delta without changing the gates or hiding failures.

Current status: the verifier stage is partially complete. The fresh holdout
still fails the product gates, so the repository is not production-ready.

Authority-batch evidence, 2026-07-17: strict verification passed for 11
additional high-frequency national sources (TPA, Contract, POSH, NI Act,
Income-tax, POCSO, RTE, Dowry, Gratuity, Aadhaar, and Bonded Labour). A
post-batch live smoke was `28/50` expected Act hit/cited, `10/50` strict
product pass, `8/50` safety hard fails, with `p50 5.1s` and `p90 12.5s`.
Trade Marks was held as a corpus-rebuild blocker because its stored summaries
matched the official Act at only `0.0557`. The authority stage remains open;
the smoke does not replace the required fresh 500 holdout.

### 2026-07-17 Source-Gap Handoff Contract Stage

- [x] Preserve only the reviewed route label, urgency/red flags, missing facts,
  and document checklist when a required source has a gap.
- [x] Fail closed for source-gap route events: do not expose forums, portals,
  escalation instructions, operative action steps, legal regime, or required
  sources as verified legal guidance.
- [x] Validate the intake-only MatterRoute and sentence event schemas before
  browser rendering; reject contradictory or malformed payloads.
- [x] Render a clear preparation handoff instead of a blank answer panel.
- [x] Obtain independent review after implementation: no P0/P1/P2 findings.
- [x] Run focused tests: 119 backend tests, 13 web contract tests, and web
  type-check passed; the fresh live holdout completed with 0 errors.

The fresh 500-query holdout after this stage was stable but did not improve
answer quality: 0 refusals, 0 errors, 339 source-gap handoffs, 141 relevant
answers, 107/485 expected Act hits and citations (22.1%), 59/500 strict
product passes (11.8%), 37/183 critical passes (20.2%), and 268/500 legal
safety hard fails. Latency was p50 5.0s, p90 5.8s, max 27.7s. This is a
safety and UX correctness improvement, not a production-readiness result.

The benchmark used 500 newly generated query texts from the curated evaluation
inventory with a new seed. The inventory contains 501 canonical cases, so the
query wording is new but underlying case coverage may overlap; this is not
real-user telemetry or blinded human review.

Current blocker: expand and strictly verify the highest-frequency missing
authority/source packs, then repair the MatterPlan producer so required
authority obligations are schema-valid, retrieved, and cited without injecting
unsupported guidance. Re-run a fresh 500 only after that batch and publish the
before/after delta. The product gates remain open.

### 2026-07-17 Provenance-Safe Document-to-Chunk Promotion Stage

- [x] Make document and chunk provenance promotion one atomic transaction;
  injected update failure rolls back the document and chunk state.
- [x] Promote only compared, live chunks; registry-owned chunks remain under
  their exact authority audit and quarantined chunks are never promoted.
- [x] Compare every live chunk independently so aggregate document similarity
  cannot hide one corrupted chunk.
- [x] Make the HF mirror path extraction-consistency diagnostic-only; it cannot
  promote production provenance without a canonical artifact hash.
- [x] Restrict generated title/section-prefix normalization to the exact
  stored document title and test a fabricated title negative case.
- [x] Obtain independent review after the final patch: PASS with no P0/P1/P2
  findings.
- [x] Validate with `17` focused tests, `1` real PostgreSQL rollback fixture,
  `104` verifier/retrieval regression tests, and `git diff --check`.
- [x] Strictly re-audit NI Act, POCSO, and POSH official India Code sources;
  NI has `125/126` live chunks verified and one corrupted chunk quarantined;
  no corpus data or benchmark data was committed.
- [x] Run the fresh 500-row live holdout after the stage with `0` errors.

The post-stage report is
`data/processed/timed_eval_holdout_new500_provenance_20260717.md`: `67/500`
refused, `0/500` source-gap handoffs, `359/500` relevance-ok, expected Act
hit `230/485 (47.4%)`, expected Act cited `219/485 (45.2%)`, strict product
pass `66/500 (13.2%)`, critical pass `40/183 (21.9%)`, procedure-anchor
citation `2/3 (66.7%)`, first actionable cited source `417/432 (96.5%)`,
route retrieval gaps `222/500`, route citation gaps `236/500`, MatterPlan
authority retrieval gaps `403/1034`, MatterPlan citation gaps `411/1034`,
visible source gaps `322/500`, and legal-safety hard fails `88/500`.
Latency was `p50 5.4s`, `p90 17.2s`, max `47.1s`.

This is a genuine fresh wording holdout generated from the curated 501-case
inventory with prior exact prompt text excluded. It is human-like synthetic
evaluation data, not real-user telemetry or blinded lawyer review. Its wording
and route mix differ from the earlier source-gap handoff holdout, so the
metrics are not an apples-to-apples causal delta. The evidence does show that
the promotion stage is safe and that quality is still blocked by missing
authority families, MatterPlan obligation coverage, refusals, and safety
framing. The repository is not production-ready.

Next blocker: repair the authority-obligation producer and fill the recurring
source families exposed by this run, starting with senior-citizen/maintenance,
succession, labour injury/EPF, welfare, land/revenue, IBC/NCLT, trademark/IP,
prison procedure, business/MSME, and state/local authorities. Lock this
holdout and rerun a new 500 only after the next implementation and review.

### 2026-07-17 Exact-Section and Source-Pack Identity Stage

- [x] Make split-section matching heading-aware across planner, source-gap,
  constitutional, RTI, HMA, and answer-authority paths; a neighboring `22A`,
  `6A`, or `13` fragment cannot satisfy an exact `22`, `6`, or `13A`
  obligation.
- [x] Keep title-only Acts provisional unless registry identity or a verified
  section is available; remove the generic personal-succession citation
  obligation when religion is unknown.
- [x] Bind Christian widow/children queries to the reviewed child-specific
  Indian Succession Act source pack when the base and child pack scores tie.
- [x] Add focused regressions for the three neighboring-section cases and the
  Christian child-pack tie; obtain an independent review before benchmarking.
- [x] Run the exact fresh 500-row holdout after the review gate with zero
  transport errors and record the full JSONL/Markdown output.

Evidence: focused source-gap/planner validation passed `161` tests, the exact
endpoint regression passed `1` test, direct probes rejected Constitution
Article 22A, RTI Section 6A, and HMA Section 13 fragments, and the independent
review returned GO for measurement. The holdout is
`data/processed/timed_eval_holdout_new500_anchorfix_final_20260717.md`:
`0/500` refusals, `335/500` source-gap handoffs, `0/500` errors, expected Act
hit/cited `120/485 (24.7%)`, strict product pass `63/500 (12.6%)`, critical
pass `39/183 (21.3%)`, first cited source actionable `165/165 (100%)`, route
source retrieval/citation gaps `16/500` each, MatterPlan obligation retrieval
`245/313` and citation `236/313`, visible source gaps `335/500`, and legal
safety hard fails `264/500`. Latency was `p50 5.1s`, `p90 5.9s`, max `31.5s`;
the LLM path was only `9/500` rows and had `p50 21.4s`, `p90 28.6s`, max
`31.5s`.

This is a correctness/non-regression result, not a quality improvement: the
pre-review run on the same 500 synthetic human-like prompts was `120/485`
Act hit/cited, `64/500` strict pass, and `264/500` safety hard fails. The
small strict-pass decrease and relevance movement are normal run variance;
the authority fixes were narrowly scoped and did not solve the dominant
coverage or MatterPlan-contract failures. The prompts are newly generated
wording from the curated evaluation inventory, not real-user telemetry or
blinded lawyer review. Production gates remain open.

Next implementation blocker: repair the MatterPlan producer so the 342 invalid
or missing-plan rows become schema-valid without inventing authority, then
expand and strictly verify the recurring missing source families. Any change
must pass the locked holdout, preserve `0` dangerous framing, and keep latency
within the release budget before it can be called an improvement.

## 2026-07-17 Intake-Ownership Guard and Fresh 500 Gate

- [x] Prevent generic consumer ownership from shadowing seized-device, vehicle,
  and non-consumer routes; preserve explicit online vehicle purchases as
  consumer candidates and use word-boundary matching for vehicle terms.
- [x] Add registered-will ownership and schema-valid non-criminal PMLA/UAPA
  incident-date statuses.
- [x] Treat a safe source-gap handoff as intentionally non-answerable in the
  evaluator, so it is not misreported as a malformed MatterPlan or a dangerous
  answer. Source gaps still fail the product gate because the user did not get
  a supported answer.
- [x] Obtain independent review after the final patch: GO, with no P0/P1/P2
  findings; targeted ownership/schema suite passed `289` tests.
- [x] Run a new 500-row human-messy holdout with seed `2026071717`, prior exact
  prompt packs excluded, and zero transport errors.

Evidence: the live report is
`/tmp/law_rag_20260717_stage1_fresh500/results/timed_eval_500_seed2026071717.md`.
It completed `500/500` rows with `0` refusals and `0` errors. Route match was
`500/500`; expected Act hit and cited hit were `120/485 (24.7%)`; strict
product pass was `63/500 (12.6%)`; critical strict pass was `39/183 (21.3%)`;
relevance was `134 ok`, `26 partial`, and `4 off-topic`; safe source-gap
handoffs were `336/500`; MatterPlan contract validity was `157/164` applicable
answer rows; MatterPlan authority retrieval/citation were `245/310` and
`237/310`; and legal-safety hard fails were `4/500`. Latency was `p50 5.0s`,
`p90 5.7s`, max `25.9s`; the LLM path was `8` rows with `p90 25.3s`.

The independent common-user gate is
`/tmp/law_rag_20260717_stage1_fresh500/results/common_user_gate_500_seed2026071717.md`:
`91/500 (18.2%)` product passes, `120/485 (24.7%)` expected Act citations,
`336` visible source gaps, `16` route-required source gaps, `4` safety hard
fails, and `58.4%` must-term coverage. The failure ledger is
`/tmp/law_rag_2026071717_failure_ledger.md`: `409` strict failed rows, with
`360` source/retrieval gaps, `16` route-source gaps, `62` criminal-procedure
high-risk rows, `44` labour/welfare rows, and `36` family/child-safety rows.

This stage improves evaluator diagnosis and ownership correctness, but it does
not improve user-facing coverage enough for release. The service is healthy,
yet production gates remain open. Next stage: repair the highest-frequency
authority packs and MatterPlan obligation producer, starting with criminal
procedure/bail, welfare/labour, family/caste/tribal, procedure, banking, and
consumer routes. Each source-pack change must pass independent review and a
new holdout before being accepted.

## 2026-07-19 Source-Gap Guided Intake Protocol

- [x] Emit bounded retry intake only for a canonical state/local authority gap.
- [x] Keep the source-gap handoff fail-closed: no MatterPlan, forum, portal,
  deadline, or legal conclusion is serialized with the handoff.
- [x] Clear stale browser content, reject late route/answer events, and bound
  guided retries to the API's 2,000-character query limit.
- [x] Obtain independent re-review: GO, with no P1/P2/P3 findings.
- [x] Run a post-review targeted holdout against the restarted API.

Evidence: backend intake `13 passed`, source-gap suite `189 passed`, frontend
protocol tests `16 passed`, TypeScript check passed, and a live source-gap
smoke emitted `matter_route`, `source_gap`, `intake`, and a citation-free
guidance sentence without a MatterPlan. The fresh 25-row report is
`/tmp/law-rag-stage-slice/timed-v10-reviewed.md`: `0` transport errors, `0`
safety hard fails, `18/25` relevance-ok, `15/24 (62.5%)` expected Act cited,
`7/25 (28.0%)` strict product passes, `6/25` safe source-gap handoffs, p50
`4.9s`, p90 `5.6s`, and max `25.4s`.

This stage improves recovery honesty and stream safety but does not create
missing law. The next blocker is activation and provenance of recurring
route-required authority gaps, especially welfare, transport/drug-control,
disability, senior-maintenance, education, and municipal procedures. The
repository remains not production-ready.

## 2026-07-19 Municipal/Food Authority Boundary Stage

- [x] Make municipal/local-authority sealing own the operative closure route,
  including generic food-inspection wording and qualified city-corporation
  identities.
- [x] Prevent FSSAI over-routing for private-company closures, unnamed health
  or food departments, negated food facts, and ambiguous hotel/restaurant
  closures.
- [x] Keep exact FSSAI passages from satisfying a missing municipal authority
  obligation; preserve source-gap handoff and provenance fields.
- [x] Add regressions for municipal/FSSAI mixed queries, local-health closures,
  private and Ltd city corporations, negated food terms, food-safety synonyms,
  sample actions, and active source-pack anchors.
- [x] Obtain independent review after the final patch: GO from the reviewed
  routing/source-gap stage, with no P0/P1 findings.
- [x] Run deterministic verification: 2062 backend tests passed with model
  and live-stack tests excluded, 18 frontend protocol tests passed, and
  TypeScript/diff/compile checks passed.

Evidence and limits: the complete backend invocation recorded 2066 passed
tests but had 63 live-Postgres failures plus one real-reranker failure because
Postgres.app rejected the ChatGPT client and Hugging Face model resolution was
unavailable. The clean deterministic run was
2062 passed, 1 skipped, 68 deselected; no fresh 500-row holdout was run in
this stage because the API could not connect to the local database. Production
gates remain open. Next blocker: grant Postgres.app permission, verify the
browser-to-API path, then run a genuinely fresh 500-prompt holdout and compare
Act/section coverage, citation correctness, safety, source gaps, latency, and
MatterPlan validity.

## 2026-07-19 Municipal Boundary Review Closure

- [x] Share qualifier-aware local-authority identity logic across routing and
  source-gap materiality, including named/private city-corporation wording.
- [x] Keep generic health officer/inspector/team wording out of FSSAI while
  routing explicit local/municipal health actors to local-authority intake.
- [x] Preserve the public street-vendor permit/removal pattern while rejecting
  private corporations, landlords, security actors, and named private entities.
- [x] Add full source-gap regressions for all accepted hawker/vending variants.
- [x] Obtain independent Hubble and Avicenna reviews: both GO, no P0/P1/P2.
- [x] Run the final affected deterministic suite: `1119 passed`, `57
  deselected` stack/model tests, one warning.

This stage closes a routing/source-gap correctness boundary; it does not claim
product readiness. The next gate is still a live API/database run followed by
a fresh 500-prompt holdout. Existing holdout evidence remains well below the
release thresholds, so no production claim is permitted yet.

## 2026-07-19 Bounded Database Startup Stage

- [x] Make Postgres connection timeout explicit and configurable for host and
  production Compose deployments.
- [x] Reject invalid timeout values (`<=0`, `>60`, `NaN`, and infinity) at
  configuration load; keep a defensive runtime clamp in the pool builder.
- [x] Verify the actual unavailable-Postgres path exits with `TimeoutError`
  instead of hanging indefinitely.
- [x] Obtain independent review: Hubble and Avicenna both GO, no P0/P1/P2.
- [x] Run the full deterministic API gate: `2075 passed`, `1 skipped`, `70
  deselected`, `8 warnings`.

This improves operability and diagnosis only. PostgreSQL.app still does not
accept the current client connection, so the API and fresh 500-row live holdout
remain pending. No production claim is permitted until that external service
condition is fixed and the holdout, provenance, safety, and operational gates
are measured on the running release candidate.

## 2026-07-19 Verified Readiness and Service Probe

- [x] Make `/readyz` count only non-quarantined chunks accepted by the same
  verified-provenance predicate used by production retrieval.
- [x] Count a document as ready only when it owns at least one eligible chunk;
  the unverified CI fixture cannot make the service appear ready.
- [x] Make `/healthz` return a sanitized `503` on database failure rather than
  leaking a startup/connection exception as an unstructured `500`.
- [x] Wire the production Compose healthcheck to `/readyz`, wait for a healthy
  API before starting the web service, and retain bounded startup timing.
- [x] Obtain independent Hubble and Avicenna reviews: both GO, no P0/P1
  findings. Both noted only P2 test-depth/per-probe-cost follow-ups.
- [x] Run focused readiness/provenance tests: `7 passed`; compile and diff
  checks passed.
- [x] Restore and verify the populated local `lawrag` service stack without
  initializing an empty replacement database. The API reports `189907` chunks,
  `5808` documents, and the expected worktree fingerprint; the frontend root
  returns HTTP 200.
- [x] Run a fresh 500-row live human-like holdout pinned to the serving
  fingerprint. It completed `500/500` with zero transport/API errors and zero
  refusals. The prompt inventory is synthetic evaluation data, not production
  user telemetry or blinded human/legal review.

Evidence from the 2026-07-20 run: strict product pass `132/500 (26.4%)`,
common-user gate pass `162/500 (32.4%)`, route match `499/500 (99.8%)`, expected
Act cited `187/485 (38.6%)`, visible source-gap handoffs `253/500`, one legal
safety hard fail, total latency p50/p90 `5.2s/6.1s`, and LLM-path p90 `24.9s`.
The system is operational but not production-ready. Next blockers are source
pack activation/provenance and citation completion for high-harm/high-volume
families, plus a regression for the CIBIL/NOC off-topic safety failure; no
training decision should be made until these evidence gates improve.

## 2026-07-21 Criminal Custody Authority-Identity Repair

- [x] Promote exact, provenance-verified official sections for the criminal
  custody recovery slice: CrPC section 482; Juvenile Justice Act sections 9,
  10, 12, and 94; and Legal Services Authorities Act sections 9 and 12.
- [x] Preserve independently registry-projected exact chunks when a promoted
  source document is refreshed. Document replacement may only de-verify chunks
  that it actually owns.
- [x] Preserve every reviewed source-pack identity when one physical passage is
  shared by several obligations. The primary source-pack label remains stable
  for ranking and UI, while the complete reviewed identity set is retained for
  authority, source-gap, and workflow checks.
- [x] Split the Juvenile Justice age/court obligation from the age-document
  obligation: the court requirement is satisfied only by section 9, while
  section 94 remains evidence for age determination.
- [x] Add regressions for shared source-pack identity and for a juvenile
  section satisfying the reviewed bail/board obligation.

Root cause: retrieval contained the exact JJ Act material, but deduplication
kept only one source-pack label for a shared chunk. A source-gap check could
therefore miss a valid pack while a workflow check could accept a different
anchor, producing a false handoff or an internally inconsistent plan. The
repair keeps the exact source title, document ID, source type, and section
anchor checks unchanged; it only records every reviewed pack that a verified
chunk is allowed to satisfy.

Focused verification passed: the promotion suite (`16` tests), shared-pack and
authority-preservation retrieval suite (`4` tests), and selected juvenile
source-gap/source-pack tests. A live replay of `16 yr boy detained adult jail
2 weeks already how to transfer observation home` returned the emergency
`juvenile_adult_jail_age_determination` workflow, official JJ Act sections 94,
9, and 12, no source-gap handoff, and total latency `4.7s`. This is a
high-harm slice repair, not a release result. Independent review and a new
held-out evaluation remain mandatory before this stage can count toward
production readiness.
