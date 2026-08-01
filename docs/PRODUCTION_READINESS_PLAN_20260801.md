# Production Readiness Plan

**Created:** 2026-08-01
**Current decision:** NO-GO
**Target:** A limited-scope, defensible Indian legal-help production release

## Executive schedule

This schedule is evidence-gated. Dates move when a gate fails; the gate does
not move to preserve a date.

| Milestone | Target date | Exit condition |
| --- | --- | --- |
| Reproducible release baseline | 2026-08-10 | Clean release branch, current regression fixed, CI and deterministic suites green |
| Supported-route legal/data closure | 2026-08-23 | V1 authority packs are naturally retrievable, provenance-verified, and fail closed outside scope |
| Controlled pilot candidate | 2026-08-31 | Action UX, privacy boundary, live stack, and pilot holdout pass |
| Production release candidate | 2026-09-18 | Security, load, Redis admission, backup/restore, rollback, and monitoring gates pass |
| Earliest public limited-scope launch | 2026-09-28 | Frozen candidate passes the final independent holdout and legal go/no-go review |
| Realistic launch window | 2026-09-28 to 2026-10-12 | Allows one full remediation and re-evaluation cycle |

The dates assume two full-time engineers, a part-time Indian-law reviewer, and
access to the intended Linux/GPU production host. With one engineer and no
dedicated legal reviewer, plan for roughly 12-16 weeks rather than 8-10 weeks.

## Recommended V1 boundary

Production readiness is achievable only with an explicit supported scope. The
recommended first release supports reviewed action packs for:

1. FIR, arrest, custody, and immediately related criminal-procedure safeguards.
2. Domestic/family safety and emergency handoff.
3. Cyber/financial harm, bank holds, wrongful debit, and loan-app harassment.
4. Consumer/banking grievance and escalation.

All other matters must identify the missing jurisdiction, date, role, or
authority and provide a safe legal-aid/lawyer handoff. They must not borrow a
nearby law or fall through to an unrestricted LLM answer.

Expanding all eight planned product lanes is a post-V1 program unless the team
accepts a later launch date.

## Current baseline

- The latest documented 500-query holdout is NO-GO: 35.8% product pass, 47.2%
  expected-Act citation, 36.6-second p90 latency, and 0/500 safety hard fails.
- The stale MGNREGA wage-delay assertion has been corrected to enforce the
  current authority contract: ordinary wage delay uses Section 19, while
  Section 17 remains conditional on social-audit/accountability facts.
- Clean integration checkpoint `98197dd` passed the exact full API gate with
  2,532 tests passed, 3 explicit Redis/PostgreSQL opt-in contracts skipped,
  and zero failures. Those opt-in contracts were also exercised separately:
  the live PostgreSQL/Redis marker slice passed 68 tests, including the real
  Redis admission contract and the two rollback-only database contracts.
- The model-backed integration slice passed 7 tests and the local
  evaluation-data contract slice passed 2 tests.
- Frontend type-checking, all 26 protocol tests, and the optimized production
  build pass. The production-built browser contract also passes against the
  live staged API, covering authenticated same-origin proxying, SSE terminal
  ordering, a normal consumer answer, and an acid/chemical fail-closed handoff.
- The merged production Compose contract and authority-registry release wheel
  verification pass.
- A live API startup against the local service stack returned HTTP 200 from
  deep readiness with 189,748 eligible chunks and 5,827 documents.
- The substantive implementation originated on `codex/latency-hardening` and
  is now assembled on `codex/production-readiness-20260801`; `main` remains
  effectively empty and has not yet been reconciled with this release line.
- The initial 114-path dirty inventory has been converted into reviewable
  commits for governance (`c0cf002`), immutable authority/provenance repair
  (`4cc75cb`), API and matter contracts (`4a9f91d`), web/deployment boundaries
  (`283b285`), and legal-safety evidence (`1ce286b`). This is an integration
  checkpoint, followed by the documentation checkpoint (`98197dd`); it is not
  a frozen production candidate.
- Production admission control exists in code but the real Redis-backed
  topology, proxy cancellation, and final deployed-configuration holdout are
  not verified.

## Phase 0: Stabilize the repository (2026-08-01 to 2026-08-10)

### Work

- Fix the MGNREGA Section 17 grounded-template regression without weakening
  source or safety gates.
- Inventory every modified and untracked path; separate serving, authority
  migrations, evaluation, frontend, infrastructure, and documentation changes.
- Split the current work into reviewable commits and remove generated/runtime
  artifacts from the release diff.
- Reconcile the substantive branch with `main` through a reviewed merge or a
  clearly designated release branch.
- Repair/reinstall the local Codex CLI separately from the application repo.
- Run deterministic API tests, full local tests, web tests, type-check, build,
  authority-wheel verification, production Compose validation, and real
  PostgreSQL migration tests.

### Gate

- Clean worktree and reproducible lockfiles.
- Zero deterministic API failures.
- Zero release-critical skipped tests.
- Remote CI green on the exact candidate commit.
- No application implementation stranded only in an untracked worktree.

## Phase 1: Close supported-route authority gaps (2026-08-11 to 2026-08-23)

### Work

- Publish the V1 supported-route and unsupported-route matrix.
- Make every V1 condition, remedy, forum, deadline, document, and escalation
  relationship registry-owned.
- Replace remaining one-off corpus patches for V1 authorities with idempotent,
  versioned migrations.
- Verify canonical publisher URL, effective date, jurisdiction, source bytes,
  section text, and active corpus projection for every controlling authority.
- Measure uninjected retrieval recall@8 by authority family; source-pack
  injection cannot count as natural retrieval evidence.
- Add positive, paraphrase, negative-neighbor, date-regime, state, role, and
  unsupported-scope tests.
- Re-run the locked regression set after each authority batch.

### Gate

- 100% of surfaced controlling V1 authorities are provenance-verified.
- No visible source gap for a declared supported route.
- Unsupported routes fail closed with an actionable handoff.
- No freeform LLM owns a critical V1 route.
- Independent legal review approves each V1 action pack.

## Phase 2: Complete the user and privacy contract (2026-08-18 to 2026-08-31)

### Work

- Persist only a short-lived, redacted matter session for guided follow-ups.
- Render consistent sections for immediate safety, applicable lane, evidence,
  first authority/forum, deadline risk, documents, and escalation.
- Make source gaps, unsupported geography, and missing facts explicit.
- Define consent, retention, deletion, access, and audit rules before storing
  query or answer text.
- Run the hand-labelled PII/redaction release evaluation.
- Conduct observed usability tests across each V1 lane, including Hinglish and
  incomplete-fact journeys.

### Gate

- No raw sensitive matter text is persisted without an approved purpose,
  retention period, access policy, and deletion path.
- PII/redaction gate passes its reviewed corpus with no critical leakage.
- Users can identify their next action and the missing fact that changes it.

## Phase 3: Prove legal quality (2026-08-24 to 2026-09-10)

### Work

- Freeze known failures as regression data and exclude them from launch
  evidence.
- Create a sealed 1,000-prompt holdout with messy English, Hinglish, role
  ambiguity, state/date traps, unsupported matters, and negative neighbors.
- Obtain blinded lawyer/trained-human review for at least 200 representative
  rows.
- Publish per-route results and confidence intervals.
- Audit answer ownership for every scored run.
- Remediate by root cause: intake, routing, authority coverage, retrieval,
  answer ownership, verifier, UI, or latency. Do not tune against holdout text.

### Gate

- Product pass >=95%.
- Expected Act cited >=93.5%.
- Required terms >=95%.
- Timing telemetry >=95%.
- Total and LLM-path p90 <=20 seconds.
- Zero dangerous framing and zero unsafe critical-route refusal.
- No concealed source gap or unsupported controlling-authority claim.

Any failed gate requires a new candidate and a new sealed confirmation set.

## Phase 4: Production operations and security (2026-09-01 to 2026-09-18)

### Work

- Build and publish reproducible API and web images; pin all container and model
  digests and remove floating `latest` tags.
- Verify authentication/authorization boundaries, secret rotation, request-size
  and time limits, trusted-proxy handling, Redis admission, and rate limiting.
- Run browser disconnect/cancellation and Redis failure/recovery tests in the
  real production topology.
- Run load, abuse, security, and privacy tests at the intended concurrency.
- Add route-level latency, source-gap, refusal, verifier, admission, and model
  availability dashboards and alerts.
- Implement encrypted backups, perform a restore drill, perform a rollback
  drill, and write incident/source-drift runbooks.
- Verify TLS and external ingress configuration on the intended host.

### Gate

- Production starts fail closed when secrets, provenance, Redis, models, or the
  reviewed corpus are unavailable.
- Load and disconnect behavior stay within admission and latency budgets.
- Backup restore and release rollback succeed from documented commands.
- Alerts fire in drills and identify the affected route/service.
- Security, privacy, and operations reviews have no open launch blockers.

## Phase 5: Freeze and launch (2026-09-19 onward)

1. Freeze the exact release commit, image digests, model digests, corpus
   manifest, authority-registry version, and configuration fingerprint.
2. Re-run all deterministic, live-stack, model, migration, frontend, security,
   privacy, load, restore, and rollback gates.
3. Run the final independent 1,000-prompt evaluation on the deployed candidate.
4. Obtain written engineering, legal-quality, privacy/security, and product
   go/no-go decisions.
5. Launch to a bounded cohort with monitoring and a documented shutdown/rollback
   trigger before expanding traffic.

## Responsibilities and external dependencies

Codex can implement and verify the repository changes, tests, migrations,
evaluation tooling, deployment configuration, monitoring, and runbooks.

Human decisions/evidence are still required for:

- final V1 scope and unsupported-matter policy;
- independent Indian-law review and holdout labels;
- privacy/retention approval;
- production credentials, host access, and domain/TLS configuration;
- security acceptance and the final launch decision.

## Immediate next actions

1. Push the integration branch and require remote CI on its exact head.
2. Review the stacked commits and reconcile this release line with `main`
   without squashing away the audit boundary.
3. Lock the four-lane V1 scope and publish its supported/unsupported route and
   authority-coverage matrix.
4. Run uninjected recall/provenance closure for every V1 authority family and
   obtain independent Indian-law review for each action pack.
5. Freeze a new candidate only after privacy, security, load, backup/restore,
   rollback, monitoring, and production-host checks pass; then run a fresh
   sealed holdout.

No launch date is considered committed until Phase 0 is green and the V1 scope
has an assigned legal reviewer.
