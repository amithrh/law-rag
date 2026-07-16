# Law RAG Architecture Knowledge Base

**Purpose:** capture the product architecture and quality invariants for building an Indian-law, plain-language, one-stop legal guidance system.

This repo is not just a generic RAG API. The product goal is to convert messy user questions into safe, grounded, action-oriented legal guidance:

`user facts -> safety/role/date intake -> matter route -> source packs -> retrieval -> Act-first answer -> verifier -> relevance/product gate`

## Product Contract

Every useful answer should do five things:

1. Identify the user's matter route.
2. Respect user role: survivor, accused, complainant, helper, tenant, landlord, employee, employer, borrower, bank customer, etc.
3. Prefer actionable statutory/procedural sources before judgments.
4. Give a safe next step, forum, documents to keep ready, and escalation path.
5. Clearly refuse or ask for clarification when the route/source support is too weak.

## Pipeline Layers

### 1. Pre-route safety intercept

Safety-critical routes must run before off-topic and before coverage refusal.

Examples:

- self-harm / suicide intent,
- immediate domestic violence,
- child/minor sexual harm,
- arrest/custody danger,
- violent threats.

Invariant: a self-harm query must never become `off_topic`, even when mixed with non-legal words.

### 2. Normalization and language hints

`matter_router._norm()` normalizes text and expands Devanagari hints for routing. Mixed-language support is part of routing, not a UI nicety.

Required coverage:

- English,
- Hinglish / roman Hindi,
- Devanagari Hindi for common crisis, domestic, police, tenancy, and wage facts.

Invariant: adding a route for English must include tests for at least one lay phrasing and, where safety-critical, Hindi/Hinglish phrasing.

### 3. Role disambiguation

The same legal term can imply opposite routes:

- `POCSO against me` -> accused defence.
- `POCSO complaint for my student/daughter` -> survivor/helper path.
- `bail of accused` from survivor -> oppose/cancel bail, not accused advice.

Invariant: accused-side routes require first-person accused signals or tightly scoped relationship-filing signals. Third-party/helper language must not route to accused defence.

### 4. Matter router

The router maps a messy query to:

- `category`,
- `label`,
- `urgency`,
- `required_sources`,
- `forums`,
- `missing_facts`,
- `red_flags`,
- `action_pack`,
- criminal date regime when relevant.

The router is product architecture, not only classification. It decides the user's first mental model.

Invariant: route tests must include false-positive probes, not only happy paths.

### 5. Source packs

`source_packs.py` adds exact statutory/procedural sources required by the route. Retrieval can still find judgments, but source packs force the core Acts into candidate space.

Examples:

- wage query -> Code on Wages.
- MACT -> Motor Vehicles Act.
- prospective will -> Indian Succession Act + Registration Act.
- crisis -> Legal Services Authorities Act / Mental Healthcare Act support sources.

Invariant: if a route has a known core Act, expected source packs must be tested.

### 6. Retrieval and preservation

Retrieval combines route-expanded query variants, BM25/dense/rerank, and required source preservation. The answer layer receives bounded passages with source metadata.

Invariant: required source packs should not be silently evicted by top-k ranking when they are the route's primary legal source.

### 7. Prompt and source typing

`llm.py` exposes source type in passage headers:

- Bare Act,
- Supreme Court judgment,
- High Court judgment,
- other source types.

The answer prompt must prefer Bare Act citations when an Act and a judgment support the same claim.

Invariant: judgments can explain, but Acts/procedure usually drive user action.

### 8. Deterministic templates

High-volume, high-risk procedural routes use deterministic templates when exact sources are present.

Templates are appropriate when:

- the route is high confidence,
- the statute/procedure is exact,
- hallucination would be harmful,
- latency matters.

Templates are not a replacement for intake. They should be narrow and tested.

2026-06-04 lesson: first-match template ordering is becoming a product risk.
Stage 5 turned that into a concrete invariant:

- specific labour record/fraud routes must run before generic wage templates;
- minimum-wage questions need a minimum-wage ledger, not only a payment/claim
  ledger;
- MGNREGA fake muster/social-audit questions need Section 17/19 style
  social-audit and grievance sources before generic work-demand sources;
- street-vendor licence/fine/bribe questions must not reuse physical
  removal/seizure wording unless the user actually says goods were removed or
  seized;
- if a state-specific bare Act is not indexed, the answer may say that the
  state law must be verified, but it must not pretend to cite that missing Act.
Moving a specific template above a generic one can fix one route while silently
shadowing another. The next architecture should score eligible templates by
specificity, source support, and route confidence before selecting one.

2026-06-05 update: criminal-procedure Pass 1 introduced the first
answer-generation authority ledger in `apps/api/authority_ledger.py`.
This is the desired direction: narrow contracts keyed by route variant, source
support, forum, remedy, documents, and caution. It should replace generic
criminal floors over time, not become a second pile of unrelated one-off
templates.

Current invariant for authority ledgers:

- emit only when a plausible controlling source is retrieved;
- include at least one source-close statutory sentence, so the verifier can
  produce an `ok` sentence instead of only weak support;
- keep practical next steps cited but do not pretend the source proves every
  operational document checklist;
- when a source is missing, do not invent it or cite a neighboring source;
- before adding another contract, classify the failure as `variant_answer_gap`,
  `retrieved_not_cited`, `retrieval_missed`, `corpus_gap`, or `wrong_anchor`.

### 8.1 Reviewed workflow contract promotion

2026-06-06 update: reviewed common-workflow contracts may preempt legacy
templates only under a narrow, auditable rule. This is a product-safety
mechanism, not a shortcut for improving citation metrics.

A workflow ID may be added to `_WORKFLOW_IDS_THAT_PREEMPT_LEGACY_TEMPLATES`
only when all of these are true:

- the workflow is deterministic server-authored output, not LLM/freeform text;
- the route is high-value, high-risk, or high-volume for real users;
- the workflow has manually reviewed source requirements and answer lines;
- the selected rendered template lines exactly equal the workflow contract
  lines;
- every emitted line has a valid known citation before verifier promotion;
- positive and negative regression tests prove the workflow does not shadow a
  safer or more specific route;
- the change is reviewed after live product-gate output, not only unit tests.

Verifier promotion must stay exact-line and server-template-only. Do not use
fuzzy matching, do not promote LLM sentences through this path, and do not use
this rule to hide missing controlling authority. If the controlling source is
not present after retry, the answer should expose an honest source gap.

2026-06-06 update: the broad 500 failure ledger showed the dominant blocker is
not raw retrieval. It is variant answer quality: source/Act citation can pass
while the answer misses the concrete workflow variant the user asked about.
`variant_answer_gap` must now be decomposed before patching into:

- `variant_subtype`, such as `senior_eviction_residence_property_pressure`,
  `mgnrega_job_card_refusal`, `uapa_default_bail_extension_180`,
  `ndps_quantity_bail_small_intermediate_commercial`, or
  `juvenile_adult_jail_age_proof`;
- completeness gaps, such as `forum_authority_missing`,
  `threshold_amount_missing`, `deadline_calculation_missing`,
  `special_statute_threshold_missing`, `age_custody_transfer_missing`, and
  `relevance_judge_or_language_alignment`.

Do not add a workflow preempt merely because a row fails relevance. A preempt is
allowed only when the new renderer is at least as specific as the legacy path it
shadows. The NDPS quantity contract is the current cautionary example: it must
preserve repeat-bail, default-bail, small/commercial quantity, conscious
possession, Section 37, Section 36A, and Article 21 delay variants separately.

The desired end state is:

`route -> authority slots -> retrieved controlling source -> cited slot answer`

where each slot is either grounded or explicitly marked unknown:

`Act/section -> remedy -> forum -> deadline/time sensitivity -> documents -> escalation`

2026-06-07 update: the burned UI-real 50 stage-1 repair reached the
answer-quality target diagnostically (`49/50` product, `18/18` critical,
`0` errors/refusals/safety hard fails, p90 under 20s), but still failed the
production gate on source gaps. This is the important product boundary:
generic RTI, FSSAI, judgments, or neighboring national statutes must not be used
to pretend a state/local controlling source exists. Tamil Nadu shop-license
renewal stayed red because the state Shops and Establishments / trade-license
source was not retrieved. The next architecture stage is source-slot coverage:
when a route slot requires a state/local rule, labour rule, constitutional
anchor, tax rule, prison manual, or scheme authority, the system must either
retrieve that source or return an explicit source-gap answer. Do not weaken the
source-gap gate to claim production readiness.

2026-07-11 ownership audit, superseding the earlier incomplete note: a blanket
`primary` workflow preemption made broad common first-action workflows win
before narrower source-gated templates could inspect the same facts. At the
then-current checkpoint, the source suite was `49 failed, 198 passed`.

Two controlled experiments established the correct interim boundary:

- safety-only preemption improved endpoints to `25 failed, 222 passed`, but
  broke `32/130` reviewed common-workflow contracts;
- a governed profile keeps every `safety_primary` and every authority-graph
  contract as an owner, and allows only reviewed common workflow IDs to preempt
  a legacy specialist;
- the governed profile passed `131/131` common-workflow tests and initially
  improved the endpoint suite to `19 failed, 228 passed` after
  source-specificity and ownership arbitration repairs.

2026-07-11 deterministic completion: the subsequent source-gated repairs
closed the remaining endpoint regressions. The verified local gates are now
`1,319 passed` full API tests, including `131` common-workflow contracts and
`247` endpoint tests. This proves internal contract consistency only; it does
not prove legal answer quality, corpus coverage, or production readiness
without a fresh holdout.

2026-07-11 live-smoke ownership lesson: selecting an authority-graph contract
is insufficient unless the contract is explicitly declared `primary` or
`safety_primary`. A missing answer mode left a Hindu-intestacy contract in
`merge`, allowing a generic succession template to replace the user's uncle
with an unrelated mother. For every source-gated contract, test the final
`_grounded_template_lines` owner and factual subject, not only selection.

The same smoke found a civil summons/service answer reaching the slow LLM path
despite a source-close CPC Order V service record already being in the corpus.
The fix was a narrow source pack plus a source-gated workflow that preserves
the plaintiff-versus-defendant ambiguity. Retrieval presence is not enough:
the exact source must be requested, returned by live `/answer`, and used by an
answer that does not infer a procedural filing from missing role facts.

The current policy is explicit arbitration:

- an authority-graph or safety workflow owns the answer only after its source
  requirements are satisfied;
- a common workflow owns the answer only when it is in the reviewed ownership
  profile; otherwise it is a fallback after a narrower specialist has had a
  chance to render;
- the decision and the shadowed workflow must be observable in diagnostics;
- each ownership rule needs positive and negative-neighbor tests.

The current temporary arbiter covers verified collisions such as defective-goods
versus generic contract breach, adult age-record correction versus generic bail,
custodial abuse versus private-assault FIR delay, forged property-loan versus
credit-identity correction, and MTP privacy/divorce versus current clinical MTP
access. It is a stabilization device, not the target design. The P1 MatterPlan
must replace it with one declarative owner, authority requirements, and fallback
for each released matter family.

The 2026-07-11 trace recorded `80 failed endpoint tests` containing `127`
answer calls. The largest ownership clusters were tribal/forest access, generic
criminal defence, false-FIR defence, bonded-labour rescue, cyber harassment,
and generic legacy fallbacks. Treat these as migration families, never as a
prompt-by-prompt tuning list.

2026-07-11 P0 follow-up: source-gated arbitration resolved the first labour
family without changing the broad workflow's policy. ISMW registration, Code
on Wages wage/minimum-wage, Contract Labour wage-responsibility, BOCW
register/cess fraud, and ISMW return-fare templates may now outrank generic
labour intake only when both their fact detector and controlling section are
retrieved. The endpoint checkpoint moved from `73 failed, 174 passed` to
`71 failed, 176 passed`. This is deliberately an interim boundary: P1 must put
these conditions and source slots into a declarative MatterPlan, then delete
the arbitration helper rather than growing it indefinitely.

2026-07-11 P0 date-regime follow-up: a query that explicitly provides the
incident date now resolves the criminal authority pair from that date, even if
the matter was reported later. Pre-cutover incidents use the `IPC + CrPC`
pair; current incidents use `BNS + BNSS`. The source selector also prefers the
matched offence anchor (for example, extortion rather than a generic hurt
section) within the chosen regime. Unknown-date cases retain the existing
source-gap/follow-up boundary rather than silently assuming a regime. The
endpoint checkpoint was `68 failed, 179 passed`; this is still a regression
migration measure, not production evidence.

2026-07-11 P0 bonded-labour migration: the high-harm coercion lane is now a
source-gated authority-graph owner rather than a broad rescue workflow that
could win on a title match alone. It requires Bonded Labour Act section 12
before rendering the District Magistrate/SDM inquiry-and-action route, keeps
section 4, Article 23, identity-document, migrant-worker, wage, and police
tracks conditional on their own retrieved sources, and explicitly does not own
an ordinary wage dispute. Focused source-present, source-missing, and
negative-neighbor tests pass. The full endpoint checkpoint moved to `65 failed,
182 passed`; it remains a migration measure, not production evidence.

2026-07-11 P0 marketplace-trademark migration: the phrase "counter notice"
was wrongly captured by a generic cease-and-desist workflow. A marketplace
delisting/IP-complaint detector may now preempt it only with a retrieved Trade
Marks Act section 29 or 134 source. The rendered route then preserves platform
appeal/counter-record evidence and the Trade Marks forum track; a generic notice
or section-34-only result stays on the generic route. The full endpoint
checkpoint moved to `64 failed, 183 passed`; the workflow-contract suite is
`129 passed`. Neither number is launch evidence.

2026-07-11 P0 reproducibility follow-up: the repository now has a GitHub
Actions workflow that runs the full API regression suite, Python syntax checks,
lockfile verification, and the frontend type-check. The local endpoint suite
is now green; CI still requires a clean committed baseline and Docker smoke
evidence before it is release evidence. `scripts/corpus_manifest.py`
creates an aggregate-only JSON snapshot of runtime model configuration, corpus
counts, source freshness, embedding versions, and provenance state. The
database has no Alembic migration table, so the manifest records a hash of the
actual bootstrap SQL and the explicit `bootstrap_sql_no_migration_table` state.
Production compose now sets `REQUIRE_PROVENANCE_VERIFIED=true`; source
verification and a scheduled freshness job are still required before release.

### 9. Sentence verifier and weak support

The verifier checks every emitted sentence against retrieved passages.

Important rule: weak model prose must not be broadly promoted just because it cites a bare Act. Weak support is allowed only for vetted route-authored template/bridge sentences that connect the source to the user scenario without inventing deadlines, outcomes, or legal certainty.

Invariant: citation metrics must not be improved by weakening answer quality.

### 10. Relevance and product gate

Answer relevance is an additive signal, not a legal truth oracle. It catches many wrong-topic answers but can miss nuanced legal confusions.

The product gate combines:

- route match,
- expected Act hit,
- expected Act cited hit,
- first actionable source,
- must-mention scenario terms,
- answer quality flags,
- safety hard fails,
- latency telemetry.

Invariant: a route/citation pass is not enough. Product pass must be checked.

## Production-readiness Gates

Do not call the system production-ready until these gates pass on fresh prompts:

- `>= 95%` product pass on common-user gate,
- `>= 95%` route match,
- `>= 93.5%` expected Act cited on scored rows,
- `0` safety hard fails,
- `0` dangerous framing,
- `0` unintended refusals on common in-scope prompts,
- p50 below `10s` for high-volume templateable routes,
- p90 below `20s` for mixed route sets,
- manual review of a sample of answers for legal best-action quality.

The gate configuration must be frozen before launch review. Do not neutralize
critical/high-priority thresholds because a prompt set lacks metadata. If a set
does not contain priority, expected-authority, route, must-cover, and forbidden
framing fields, use it only as a diagnostic discovery run and fix the set before
using it as production evidence.

Production evidence must include both:

- current regression slices that protect known harms; and
- a true holdout set not generated from `data/eval_500` or from rows already
  used for fixes.

Current focused evidence from 2026-06-06 is encouraging but not sufficient by
itself:

- 77 safety slice: `77/77` product pass, `0` safety hard fails, p90 `6.8s`;
- Stage 5 money/cyber/identity critical slice: `50/50` product pass, critical
  rows `38/38`, `0` safety hard fails, p90 `6.9s`.

These slices remain required regression gates. They do not replace a broad
fresh holdout because they are authored around known risk clusters.

## Required Eval Mix

A fresh 500-prompt run should include:

- 100 known regression prompts,
- 200 fresh layperson common prompts,
- 50 Hindi/Hinglish prompts,
- 50 adversarial role/negation prompts,
- 50 safety/crisis/date-regime prompts,
- 50 long-tail/state/forum prompts.

The eval must include actual user-style wording:

- typos,
- mixed English/Hindi,
- relationship ambiguity,
- "not online" / "not police" negation,
- vague but common phrases,
- urgent emotional language.

Every production-gate row should have stable metadata:

- stable row ID and source/eval split;
- expected route and workflow/subtype when applicable;
- priority (`critical`, `high`, `medium`, `low`);
- expected controlling authority or explicit source-gap expectation;
- must-cover semantic requirements;
- forbidden framing terms for dangerous answers;
- notes for conditional expectations, such as missing state/date/facts.

The old `data/eval_500` inventory is still useful for broad discovery, but it
is not a final holdout: it has expected categories, but lacks priority tags,
must-cover metadata, and explicit expected authorities on most rows.

## Known Production Gaps

- Stage 2 2026-06-04 500-prompt benchmark still failed the production gate:
  - product pass `402/500` (`80.4%`),
  - expected Act cited `446/484` (`92.1%`),
  - relevance verdicts: `447 ok`, `51 partial`, `2 off_topic`,
  - safety hard fails `0`,
  - errors/refusals `0`,
  - p50 `6.7s`, p90 `18.6s`, max `44.8s`.
- Stage 2 fixed specific ASHA/UAPA/undertrial failures, but only moved the
  product gate by `+1` passing row versus the prior 500. The durable blocker is
  answer faithfulness and route-specific action quality after correct routing,
  not broad route classification.
- Stage 2 also showed benchmark metadata gaps: generated 500-prompt packs need
  stable base-row IDs, expected route labels, common issue tags, priority tags,
  and scenario-specific must terms. Without those fields, `route_match`,
  `high_priority`, `critical_rows`, and `must_terms` can look perfect while
  product quality is still weak.
- The next production architecture needs:
  - specificity-scored deterministic template selection,
  - route authority ledgers for Act -> section -> remedy -> forum -> documents,
  - citation faithfulness checks at the sentence level,
  - per-template precision/recall on fresh prompts,
  - stricter gates for custody, UAPA/default bail, sexual harm, domestic
    violence, and child-related routes.
- 2026-06-04 500-prompt benchmark failed the production gate:
  - product pass `338/500` (`67.6%`),
  - expected Act cited `447/484` (`92.4%`),
  - bad route fallbacks `4`,
  - safety hard fails `4`,
  - p50 `6.3s`, p90 `18.8s`.
- The 2026-06-04 failure clusters were:
  - testamentary/will wording variants fell to `general_legal` (`wrote will`, `make will`, `registered my will`);
  - Mediation Act standalone procedure fell to `general_legal`;
  - scheduled-area/tribal land transfer, witch-hunting, cattle/excise, shops-and-establishments, state welfare schemes, and ration/Aadhaar benefit variants need stronger state/scheme source packs;
  - police custody/NHRC, SC/ST FIR, platform/gig deactivation, and principal-employer liability sometimes retrieved the source but did not cite it;
  - the relevance verifier produced `off_topic` on some routed/cited answers, so relevance is useful but not a final legal-quality oracle.
- `general_legal` still needs a better intake/clarifying path so it does not look issue-specific when the issue is unclassified.
- Crisis/help resources now live in `apps/api/crisis_resources.py` with source URLs and `last_verified`; they still need deployment review before public launch.
- State-specific forums and deadlines are not complete.
- Legal knowledge graph is still partial: Act -> section -> remedy -> forum -> deadline -> documents.
- Some routes still fall to LLM and create p90 latency tails.
- Evaluation is still mostly synthetic/human-style, not real user logs.
- 2026-06-06 focused variant slice after first contract fixes still failed
  product quality: `4/15` product pass with `15/15` expected Act cited,
  `0` safety hard fails, and p90 `6.6s`. This is the canonical signal that
  Act citation alone is not product quality. The next gate is a 30-40 row
  high-risk unseen/adversarial slice before rerunning the broad 500.

## Change Checklist

For every route/source/answer change:

- Add positive and negative router tests.
- Add source-pack tests for expected Acts.
- Add at least one common-user product-gate prompt if the route is user-facing.
- Add Hindi/Hinglish coverage for safety-critical routes.
- Check role ambiguity.
- Check negation.
- Run focused tests, broad route/source tests, live product gate, and subagent review.
- Classify every live failure as one of: `safety_hard_fail`, `wrong_route`,
  `wrong_workflow_subtype`, `source_pack_or_corpus_missing`,
  `source_retrieved_not_cited`, `verifier_suppressed_workflow_line`,
  `legacy_template_shadowed_contract`, `generic_or_judgment_first_answer`,
  `eval_oracle_issue`, or `latency_outlier`.
- For `variant_answer_gap`, also record the `variant_subtype` and
  `completeness_gaps`; if the answer is genuinely useful but the embedding
  relevance judge is low, mark it as `relevance_judge_or_language_alignment`
  and adjudicate with fresh unseen prompts rather than lowering the global gate.
- Fix systemic clusters before isolated rows.

## 2026-06-07 Source-Pack Source-Type Lesson

The Tamil Nadu/Coimbatore shop-license repair exposed a retrieval failure mode:
adding a `SourcePack` is not enough if its `source_types` do not match the
inserted chunks.

Example:

- `coimbatore_trade_license_2026` existed as a source pack.
- The backfilled Coimbatore Corporation D&O licensing page was initially
  inserted as `official_guidance`.
- `SourcePack.source_types` defaults to `("bare_act",)`, so required-source
  retrieval silently skipped the local source.
- The answer then cited the Tamil Nadu Shops Act and RTI but missed the
  city-specific licensing page, even though the pack and DB row both existed.

Rule:

- When adding non-Act official material, classify it as a recognized official
  type where possible: `guideline`, `rule`, `notification`, `circular`,
  `scheme`, or `regulation`.
- Explicitly set `SourcePack.source_types` for every non-Act pack.
- Add a source-pack test that asserts both pack ID and compatible
  `source_types`.
- In product validation, inspect the actual cited source list, not only
  `act_hit=True`.

Patch5 proof:

- exact Coimbatore one-row eval cited Coimbatore Corporation first, Tamil Nadu
  Shops Act second, and RTI third;
- burned UI-real 50 diagnostic improved to `50/50` product pass and `48/48`
  expected Act cited, but still failed broad production gates due to remaining
  source-gap rows and LLM-path p90.

## 2026-06-07 State-Source Spelling And Leakage Lesson

The Chhattisgarh Tonahi repair exposed a second source-slot failure mode:
official source coverage can still fail if the route/source/answer layers use
different spellings or context triggers.

Example:

- the official Act title is `Chhattisgarh Tonahi Pratadna Nivaran Act 2005`;
- user prompts often say `tonhi`, not `Tonahi`;
- users may spell the State as `chattisgarh`;
- source-pack selection was initially gated only for Assam witch-law context;
- victim/accused templates looked for `tonhi`/`witch hunting` titles and could
  miss an exact `Tonahi` title even after retrieval succeeded.

Rule:

- State/local source repairs must include common user spellings and district
  aliases in source-pack triggers and state-specific filters.
- Do not use a state Act for another State or for a state-unknown query just
  because the colloquial word is similar.
- Positive tests must prove exact-source citation when the State matches.
- Negative-neighbor tests must prove no source leakage into other States.
- Live validation should inspect the visible answer text as well as
  `act_hit=True`; the answer should name the state source when it is the
  controlling route source.

Tonahi proof:

- idempotent backfill:
  `PYTHONPATH=. .venv/bin/python scripts/add_chhattisgarh_tonahi_sources.py`
  inserted/updated `6` chunks on repeated runs;
- focused tests:
  `PYTHONPATH=. .venv/bin/python -m pytest apps/api/tests/test_source_packs.py::test_witch_false_case_does_not_trigger_generic_child_pocso_packs apps/api/tests/test_source_packs.py::test_witch_branding_ranchi_uses_national_criminal_sources_not_assam_pack apps/api/tests/test_source_packs.py::test_tribal_witch_branding_gets_poa_and_criminal_sources apps/api/tests/test_endpoints.py::test_state_specific_filter_drops_wrong_state_witch_act apps/api/tests/test_endpoints.py::test_witch_branding_victim_template_does_not_use_wrong_state_act apps/api/tests/test_endpoints.py::test_witch_branding_victim_template_cites_chhattisgarh_tonahi_source apps/api/tests/test_endpoints.py::test_grounded_template_for_witch_accused_false_case_keeps_tonhi_context apps/api/tests/test_endpoints.py::test_stage24_templates_do_not_inject_smoke_specific_facts_for_near_misses -q`
  -> `8 passed`;
- exact accused one-row eval:
  `/tmp/law_rag_single_chhattisgarh_tonahi_check/tonahi_eval.jsonl`
  -> `route=criminal_defence_bail`, `act_hit=True`, `cited=True`, `16.7s`,
  first cited source `Chhattisgarh Tonahi Pratadna Nivaran Act 2005`;
- 12-row positive/negative neighbor probe:
  `/tmp/law_rag_tonahi_neighbor_out/tonahi_neighbors_eval.jsonl`
  -> `0/10` non-Chhattisgarh rows cited the Chhattisgarh Act, and `2/2`
  Chhattisgarh positives cited and named the Act.

## 2026-06-17 Stage E9 Source-Gap Repair Lesson

The E9 repair showed why broad benchmark numbers can look acceptable while
real user prompts still fail: several failures were not raw retrieval misses.
They were contract mismatches between route-required sources, source-pack
anchors, and runtime source-gap matchers.

Examples:

- child deepfake prompts retrieved POCSO `sec-13-a` and IT Act `sec-66E`, but
  the runtime matcher did not accept the full POCSO title or IT Act `66E` as
  satisfying the route;
- ITPA raid prompts retrieved BNS `sec-144`/`sec-146`, but the trafficking
  matcher only accepted `sec-143`;
- SC/ST DSP-transfer prompts retrieved PoA Rules `rule-7`, but runtime source
  gap did not have a rule-anchor matcher;
- FRA claim refusal prompts were routed as generic caste/tribal criminal
  matters and incorrectly required BNS/BNSS even without assault, threat, or
  police-criminal facts;
- WhatsApp account-hacked prompts retrieved only IT Act until the source packs
  added the BNS cheating/personation plus BNSS FIR lane.

Rule:

- For every route-required source, keep three layers aligned:
  route contract, source-pack exact anchors, and runtime/eval source-gap
  canonical matcher.
- If the live source list already contains the right authority but `source_gap`
  still fires, fix the matcher rather than adding more retrieval hacks.
- If a non-criminal administrative query gets BNS/BNSS requirements, fix the
  route classification rather than satisfying the wrong requirement.
- Do not declare production readiness from pack-level tests. Run live `/answer`
  regressions on exact messy prompts and save the raw JSONL.

E9 proof:

- focused tests: `66 passed`;
- live targeted old-gap cluster:
  `reports/stage_e9_targeted_29_live_results.jsonl`;
- final live result: `29/29` clean, `0` source gaps, `0` refusals, `0` errors,
  p50 `6.5s`, p90 `7.0s`.

## 2026-06-17 Stage E9b False Source-Gap Repair Lesson

The E9b repair focused on a narrower but product-critical failure: the UI could
show a visible `source_gap` even when the live source list already contained
adequate authority. This made the product feel broken on common messy prompts.

Fixed classes:

- BOCW accident prompts: accept BOCW safety sections and Factories Act safety
  sections for construction/factory injury routes.
- BOCW card/no-benefit prompts: do not force BOCW Cess or BNS/BNSS fraud
  sources unless the user alleges cess collection, fake registers, false
  entries, or benefit fraud.
- Charge-sheet/tweet prompts: accept BNSS/CrPC charge-sheet, summons,
  discharge, and court-procedure anchors even when the event date is missing;
  the answer must still state that the incident date decides old/new procedure.
- Assam witch-branding violence: accept the Assam Witch Hunting source plus
  BNS hurt/intimidation and BNSS FIR/Magistrate procedure anchors.
- Forest-produce dacoity/tendu prompts: inject FRA, BNS dacoity/robbery, and
  BNSS FIR source packs, accept BNS `sec-309` as a robbery/force companion for
  dacoity wording, and allow FRA-only satisfaction when the prompt has
  forest-rights facts but no PESA/scheduled-area trigger.
- SC/ST/tribal routes: keep generic `bnss_2023`, `bns_2023`, and `crpc_1973`
  packs alongside specialized SC/ST FIR/hurt packs so route contracts and older
  eval gates remain aligned.

Rule:

- Do not suppress source gaps globally. Repair the exact authority contract:
  route-required source, source-pack anchors, runtime source-gap matcher, and
  eval matcher must describe the same legal authority.
- Conditional source requirements must be triggered by facts, not by broad route
  labels. Example: BOCW card does not automatically imply cess-record fraud.
- Composite sources should be query-sensitive. Example: PESA + FRA requires
  PESA only when the prompt has PESA/scheduled-area/Gram Sabha facts; forest
  produce alone can be satisfied by FRA authority.
- When restoring source packs for test compatibility, prefer additive generic
  companions rather than removing specialized packs that carry better anchors.

E9b proof:

- focused gate:
  `PYTHONPATH=. .venv/bin/python -m pytest apps/api/tests/test_source_gap.py apps/api/tests/test_source_packs.py apps/api/tests/test_eval_timed_100.py -q`
  -> `363 passed`;
- compile:
  `.venv/bin/python -m py_compile apps/api/source_gap.py apps/api/source_packs.py scripts/eval_timed_100.py`;
- live `/answer` retest on five messy prompts:
  forest-produce dacoity, tweet charge-sheet, BOCW accident, BOCW card/no
  benefit, and Assam daayan/witch-branding violence -> `0` source gaps,
  `0` refusals.

## 2026-07-15 P1B MatterPlan Authority Contract

MatterPlan v2 now owns the user-visible answer gate, runtime authority-gap
policy, and benchmark authority accounting. It is no longer sufficient for an
event to have the right field names: a valid legal plan must contain a nonempty
retrieval policy and a stable must-cite authority ID. The browser hides streamed
sentences until this contract validates and hides them again on malformed or
interrupted streams.

Authority identity and satisfaction rules:

- canonical IDs are stable Act-plus-section identities and do not depend on
  query-specific retrieval anchors;
- every explicitly listed section becomes a separate obligation, including
  mixed BNS/IPC sources and single-statute lists such as IT Act sections;
- known incident dates select the applicable current or legacy criminal law;
  unknown dates require a source-backed mixed-regime obligation and caveat;
- passage authority IDs are recomputed from exact reviewed title, anchor,
  source type, and source-pack metadata; incoming IDs and fuzzy provisional
  title matches are not trusted;
- conditional authorities are enforced only when their query facts activate,
  while records, documents, and intake facts never become missing-law gaps.

Evaluation must mirror the UI, not internal retrieval state. Retrieval recall
may inspect early passages, but citation credit, unknown-index checks, source
ordering, procedural cited anchors, and MatterPlan cited coverage use only the
final `sources` event shown to the user. Expected legal-query metadata controls
the MatterPlan denominator so a legal prompt misrouted as off-topic remains a
failure. Reports label the combined canonical and activated-provisional set as
authority obligations.

P1B proof: two final independent reviewer PASS verdicts, `195` focused tests,
`4` rendered frontend contract tests, frontend type-check and production build,
an integrated SSE contract, and `1,369` full API tests in `384.12s`. This closes
plan consumption and authority-ID enforcement, not P1 as a whole. The next
boundary is P1C: migrate the first ten high-volume/safety answer owners out of
legacy `main.py` branches and prove exactly one primary owner plus fallback per
supported scenario.

## 2026-07-15 P1C Plan-Owned Answer Slice

The first ten released scenario families now have one answer owner declared in
MatterPlan before retrieval. The owner is a provider plus reviewed contract ID,
not a label or whichever template happens to match first. Every released plan
also declares `source_gap_handoff`, requires a reviewed contract, and disables
freeform LLM ownership.

Released scenario families:

- immediate domestic-violence safety;
- arrest/custody where station, case, grounds, or FIR information is withheld;
- identity-only LGBTQ arrest safeguards;
- stolen-vehicle FIR refusal;
- loan-app contact harassment;
- criminal/investigating-authority bank-account hold;
- wrongful bank debit;
- insurance claim rejection or mis-selling;
- a joint co-owner selling the whole property; and
- marital-intimacy or marriage-breakdown remedy.

Ownership resolution is route-independent but fact-bound. It runs every
released contract predicate against the same query and route, returns one
owner, records explicitly compatible secondary owners, or produces an
`answer_owner_ambiguity` handoff. It never resolves two incompatible owners by
priority or first-match order.

Shared semantic predicates are mandatory where three layers need the same
fact. Routing, source-pack selection, and answer ownership now share rules for:

- human custody versus property held by police, including relational nouns,
  names, Roman-Hindi wording, and harmless descriptors such as `adult` or
  `gay` between a possessive and the person;
- initial FIR refusal versus an existing FIR at investigation stage;
- direct domestic harm versus a threat by a tenant, landlord, shop owner, or
  other third party;
- police/cyber/investigating-authority bank holds versus civil decree,
  pre-judgment, arbitral, PMLA/ED, or ordinary platform KYC restraints; and
- current BNS/BNSS, legacy IPC/CrPC, or unknown incident-date obligations.

Source support is an authority ledger, not title presence. Mandatory owner
entries bind to exact source-pack IDs and anchors. Unknown criminal dates bind
both current and legacy procedural sources. An Act title with the wrong section
does not activate an owner. If a required owner cannot activate, the endpoint
returns the structured handoff with no legacy or freeform substitute.

Two live failures established an additional no-substitution invariant. An
arbitral interim restraint cannot be answered from incidental CPC passages, and
a pre-judgment attachment cannot borrow decree-execution or criminal-seizure
law. When the controlling Arbitration Act or Order XXXVIII source is missing,
the server emits route, plan, passages, workflow diagnostics, source gap, and a
refusal, but zero legal answer sentences.

Language and actor binding must be tested in the final stream, not only as
isolated keywords. `Mera husband mujhe abhi maar raha hai` now selects the same
reviewed safety owner as its English equivalent. `My tenant said he will poison
me` stays a criminal threat and cannot retrieve PWDVA or tenancy law merely
because a domestic or property word is nearby.

P1C evidence: both final independent reviews PASS; architecture closed replay
`69 prompts / 226 assertions / 0 failures`; frontend contract tests `4 passed`,
type-check and production build pass; released live routes `10/10`, adversarial
neighbours `9/9`, and the exact user-shaped live corpus `11/11`, including the
reported-spousal-threat pronoun-binding regression. The final broad
ownership/API gate is `1,236 passed, 41 deselected` in `397.78s`. Some rows
correctly use source-gap handoff because the indexed title lacks the mandatory
section. P2 must repair those authority records and corpus anchors rather than
weakening this gate.

## 2026-07-15 P2A Immutable Authority Registry Pilot

CrPC 1973 Section 436A is the first authority moved from an imperative
one-off corpus patch into a packaged, immutable migration chain. The manifest
is the legal declaration; PostgreSQL is only its runtime projection and
idempotence ledger.

The authority record pins stable canonical identity, provision anchors,
jurisdiction, effective period and BNSS Section 531 savings, official publisher
and India Code URL, official PDF SHA-256 and byte size, exact statutory-text
SHA-256, and its retrieval contract.

Registry invariants established by this pilot:

1. Manifests are data-only, strictly validated, hash-addressed, ordered,
   predecessor-aware, included in the built wheel, and applied as an exact
   prefix. Reusing a migration ID with another hash fails closed.
2. Migration 005 upgrades a legacy database; it cannot rely on current
   `init.sql`. It owns all provenance fields, audit tables/indexes, and registry
   ledgers required before projection.
3. Ingestion never self-verifies legal text. It preserves an existing
   whole-document verdict, resets the changed provision chunk, and requires a
   later official-source hash-and-text audit for promotion.
4. Verification is per mapped chunk. A shared PDF hash may be reused, but text
   similarity and pass/fail cannot be aggregated across provisions in one Act.
5. Provision identity belongs in `document_authorities` and chunk metadata.
   Shared source/document metadata cannot use last-writer provision fields.
6. An authority ID has exactly one active corpus projection. A correction
   atomically moves the mapping and quarantines/de-verifies the retired chunk.
7. Required-source and ordinary retrieval use the same mapped-chunk provenance
   predicate. No fallback may reintroduce an unverified registry section.
8. Old-law applicability is explicit. Section 436A ends at the criminal-code
   cutover and carries a savings reference; it is not silently treated as
   current BNSS law.

P2A proof: both independent reviews PASS; wheel import and dry-run pass; a real
PostgreSQL test upgrades an isolated legacy schema and proves first apply,
no-op, rollback, source-origin repair, document-verdict preservation,
per-chunk gating, and corrected-anchor retirement. The broad stage gate is
`1,291 passed, 41 deselected`. A live India Code audit matched the pinned PDF
hash and Section 436A text (`0.984375` similarity), marked only the mapped
chunk verified, and a live `/answer` replay exposed the same canonical
authority with no source gap or refusal.

This is a vertical pilot, not registry completeness. P2 remains open for the
rest of the released authority catalog, authority relationships, geography,
freshness operations, and an uninjected retrieval benchmark.

## 2026-07-15 P2B Registry-Owned RBI and Loan-App Workflows

P2B turns the registry pilot into a multi-authority workflow. Immutable
migrations now declare the RBI Ombudsman application, definition, forum,
complaint-ground, and maintainability clauses; Digital Lending grievance and
data-access paragraphs; recovery-agent conduct; IT Act Section 66E; and BNS
Section 308. The runtime workflow is assembled from registry relationships,
not duplicated title and anchor guesses.

Additional invariants established by this stage:

1. A workflow relationship names ordered authority keys and condition IDs.
   Runtime code resolves those keys to canonical authority IDs and fails closed
   when a key is missing or unverified.
2. Exact registry requirements replace generic source-pack obligations for the
   same workflow. They do not coexist as competing answer owners.
3. Retrieval capacity is at least the number of mandatory authorities. A
   caller's small `top_k` cannot silently drop part of a compound legal route.
4. Registry retrieval joins `document_authorities`; shared document metadata
   is never treated as proof that the requested provision was retrieved.
5. The candidate answer must cite every activated must-cite registry authority.
   If retrieval is complete but the answer omits one, the server refuses before
   emitting legal sentences.
6. Conditional authorities remain fact and regime dependent. IT Act Section
   66E is a narrow private-area image rule, not a catch-all morphed-image law.
   BNS Section 308 is activated for a current payment-linked threat; an unknown
   or legacy incident cannot be forced into the current code by the word
   `now` appearing in unrelated prose.
7. RBI escalation is conditional on a covered Regulated Entity and Clause 10
   maintainability. An unregistered app does not become RBI-regulated merely
   because the user calls it a loan app.
8. A near-miss must prove non-capture, not merely a different final label. The
   bank-freeze replay contains no P2B registry keys, while its separate weak
   bridge sentences remain visible as a later blocker.

The stage gate combines exact migration and wheel checks, real PostgreSQL
upgrade/idempotence tests, official-source provenance verification, broad
router/retrieval/answer tests, and live SSE replays. The three owned prompts
returned the complete expected registry sets with no source gap, refusal, or
weak/unsupported legal sentence. P2B is still awaiting an independent
post-implementation review because the reviewer service reached its child
thread limit; tests do not convert that missing review into a PASS.

## 2026-07-15 P2C Registry-Owned Hidden Arrest and Custody

P2C migrates the hidden-person custody route from title/anchor inference to a
versioned authority workflow. It covers Constitution Articles 22 and 226,
current BNSS arrest/location/intimation/production provisions, BNSS Section 531
transition, legacy CrPC counterparts, and BNSS Section 1 scope for Nagaland and
specified tribal areas.

The legal and product invariants are:

1. Incident date selects one procedural regime. An unknown date activates the
   constitutional floor and transition question; it does not cite both full
   old and new codes as though both govern.
2. A proceeding pending immediately before 1 July 2024 can remain under CrPC
   through BNSS Section 531. The arrest date alone does not erase the savings
   inquiry.
3. BNSS is not asserted nationally for Nagaland or specified tribal areas
   without checking a State notification. Articles 22 and 226 remain available
   while local procedure is verified.
4. Public arrest-location information and private nominated-person intimation
   are separate claims. The public control-room/designated-officer route does
   not promise that any caller is entitled to private custody information.
5. Hidden custody keeps an urgent Article 226 habeas-assistance path even when
   an FIR copy, exact station, or offence section is unavailable.
6. Retrieval completeness and answer completeness are different policies.
   `WorkflowAuthorityRequirement.answer_must_cite` leaves all active provisions
   in retrieval while allowing duplicative safeguards to remain supporting
   law. A workflow-only migration changes that policy without rewriting an
   applied authority migration.
7. Statutory claims should be provision-specific. Combining two duties in one
   sentence caused claim-level support to drop valid citations; the legacy
   template now states Sections 41B, 41C, 50, 50A, 56, and 57 separately and
   preserves the `without warrant` qualification where required.
8. Official-source choice is content-sensitive. The available India Code BNSS
   extraction repeated neighboring text for Section 58, so the enacted MHA
   Gazette PDF is pinned and hash/text verified instead.
9. The router owns the incident-date regime decision. Registry conditions
   consume `MatterRoute.legal_regime` instead of reparsing every four-digit
   number; a birth year or statute year must not switch BNSS and CrPC.
10. Human-custody matching permits bounded personal descriptors such as a birth
    year between the person and pickup location, but remains closed against
    property continuations such as `worker ID cards`, equipment, or documents.

P2C proof: the final shared-route regression slice passes `161/161`, the full
non-stack API gate passes `1,673`, and all `43` real-stack API tests pass. The wheel contains migrations `0001` through
`0007` and reloads the custody answer policy. Live `/answer` replays pass `8/8`
across unknown, current, legacy, saved-pending, Nagaland, and three negative
neighbors with exact authority sets and no source gap, refusal, or
weak/unsupported sentence. The same broad gate repaired an implied-subject
arrest expansion miss and an MPS-to-CPU reranker fallback.

Independent post-implementation review remains open after three final retries
because the reviewer service reports `agent thread limit reached`. The stage is technically green,
not independently closed and not product launch evidence.
