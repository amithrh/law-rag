# Product Recovery TODO

## Current Baseline

Status: not production ready.

The recovery baseline is committed locally. The deterministic API gates are
green, but the product is still not launch-ready: remote CI, a fresh independent
holdout run, manual legal-quality review, and the operational/privacy gates
below remain open. Its architecture still contains interim workflow ownership
and source-pack arbitration that must move into declarative MatterPlans.

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
  API startup smoke. A remote green workflow run is still required before P0
  exit.
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

- [ ] Define `MatterPlan v2` as the canonical schema for issue, role, state,
  incident date, case stage, desired outcome, required facts, authority ledger,
  forum, remedies, deadlines, documents, safety flags, and confidence.
- [ ] Make routing emit `MatterPlan v2`, not only `MatterRoute` plus free-text
  action-pack fields.
- [ ] Make retrieval consume the authority ledger rather than independently
  inferring source packs from overlapping keyword logic.
- [ ] Make answer rendering consume the same plan. Migrate high-volume routes
  first and retire their legacy template branches.
- [ ] Make source-gap checks and eval scoring consume plan authority IDs instead
  of duplicated title/anchor alias heuristics.
- [ ] Add an ownership test: each supported scenario has exactly one primary
  answer owner and an explicit fallback policy.

Exit gate: the first ten high-volume/safety routes have one plan, one authority
policy, one answer owner, and no `main.py` special-case fallback.

## P2: Build the Authority Registry and Coverage Matrix

- [ ] Create declarative authority records for Act, section, jurisdiction,
  effective date, canonical URL, publisher, provenance status, and verbatim
  status.
- [ ] Add relationships: issue -> conditions -> authority -> remedy -> forum ->
  deadline -> documents -> escalation.
- [ ] Replace one-off `add_*` scripts with repeatable ingestion migrations tied
  to authority-record IDs.
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
