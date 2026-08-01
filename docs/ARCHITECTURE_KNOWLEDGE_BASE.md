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

## 2026-07-16 P2D-P2E Bank Holds and Platform-KYC Authority Boundaries

P2D adds a registry-owned bank legal-hold family: RBI Ombudsman clauses form
the banking-service floor, while BNSS Section 106 and CrPC Section 102 are
conditional by incident regime for police/cyber holds. ED/PMLA freezes remain
outside this family and fail closed until their own reviewed PMLA contract is
available. Registry backfill supplies canonical authority passages when
retrieval misses a required provision; this is a safety fallback, not evidence
that retrieval recall is good enough.

P2E fixes a source-gap policy error exposed by a realistic app query: a generic
platform account held for pending KYC was being forced to retrieve RBI or
gaming law without any bank, payment, or gaming fact. The router now requires
IT Act and Consumer Protection Act sources for the generic platform lane, adds
RBI/KYC only for a bank, NBFC, UPI, or identified payment-wallet fact, and adds
state gaming law only for a real-money gaming account dispute. A bare crypto
wallet or casual gaming-app suspension does not borrow the regulated-payment
or gambling gate.

The stage also removes an unreachable duplicate PMLA/ED route block. There is
now one early PMLA owner, so later edits cannot silently change only an
unreachable copy. Targeted router, source-gap, source-pack, workflow, and
answer-ownership checks pass after the cleanup. P2 remains open: natural
retrieval of conditional bank-hold provisions, PMLA/ED authority contracts,
and broader registry coverage are still required before any production claim.

## 2026-07-16 P2F Provenance Refresh and Natural-Retrieval Proof

The bank legal-hold family is now backed by fresh official-source evidence,
not an assertion that registry fallback is adequate. The official BNSS Gazette
PDF and India Code CrPC PDF changed byte hashes while their provision text
continued to match. Immutable migrations `0009` and `0010` pin the observed
official bytes for BNSS Section 106 and CrPC Section 102 respectively; a
targeted hash-and-text audit marks only their mapped chunks verified.

The verifier now distinguishes `verified` from `text only`: matching extracted
text cannot be reported as a provenance pass when the source file hash has
drifted. It continues to fail closed until the versioned authority record is
refreshed and audited.

Natural retrieval is separately tested against the runtime PostgreSQL corpus.
For realistic current and legacy cyber-police account-freeze prompts, the
required source pack returns the exact `bnss-2023/sec-106` or
`crpc-1973/sec-102` chunk with a positive database ID and
`provenance_verified=true`. The test rejects the negative-ID synthetic
registry fallback. A live `/answer` replay for the current prompt exposed
positive document ID `3040` for BNSS Section 106 and produced no source gap.

An independent review found that the original serving path could still add
negative-ID synthetic registry records after retrieval. That path is removed
from both source-gap evaluation and prompt construction: a required authority
miss now remains a real coverage miss and is handed off rather than fabricated
in memory. The review also found that a source hash refresh had to invalidate
all existing projections from that source, not only the updated section. The
migration projector now clears document and chunk verification across that
source before a new audit can promote any provision.

`REQUIRE_PROVENANCE_VERIFIED` now defaults to `true`. Any corpus-wide offline
evaluation that intentionally studies unverified material must explicitly opt
out; a missing production environment variable cannot silently disable the
source gate.

This proves one authority family, not general retrieval quality. Every new
authority-owned workflow still needs the same three-part gate: official source
refresh, mapped-chunk verification, and an uninjected runtime-retrieval test.

## 2026-07-16 P2G PMLA/ED Asset-Restraint Authority Workflow

P2G replaces intake-only refusal for a supported ED/PMLA asset restraint with
two fact-specific statutory paths. A Section 17 freezing order is not described
as a Section 5 provisional attachment order. Both paths converge on Section 8
adjudication and the Section 26 Appellate Tribunal route.

The immutable `0011` migration pins the official India Code PMLA PDF
(`d3699f0228f7b9cdf8311f9e8998032fb15e6570070b99a578eca3cb8fcd6413`,
504,120 bytes) and declares Sections 5, 17, 8, and 26 as separate canonical
authorities. A source audit re-fetched that PDF, persisted four exact
mapped-chunk verdicts, and marked all four mapped chunks provenance verified. Migration
`0012` pins the official PDF artifact snapshot date (`2024-08-30`); `0013` and
the immutable corrective `0014` expand the Section 5/17 statutory checks; and
`0015` quarantines and unverifies the superseded undated projections without
deleting their audit history. The immutable repair migration `0016` replays
that retirement for canonical and split alias anchors on databases where
`0015` was already recorded before alias-aware retirement shipped.

The serving invariants are:

1. A freeze query activates Sections 17, 8, and 26; an attachment query
   activates Sections 5, 8, and 26. The unused path is excluded.
2. Missing Section 8 or Section 26 fails closed. A neighboring judgment or
   generic PMLA chunk cannot substitute for the controlling provision.
3. The answer owner is `authority_graph:pmla_ed_asset_freeze`, freeform LLM
   generation is disabled, and the reviewed contract is a primary answer.
4. `ED` matching is token-aware. Text such as `ordered attachment` cannot be
   captured merely because it contains the letters `ed attachment`.
5. Ordinary ED summons, PMLA bail, cyber-police freezes, KYC holds, civil
   attachments, and arbitral restraints remain outside this owner.
6. Production retrieval uses the MatterPlan source policy and must return
   positive-ID, provenance-verified chunks. Synthetic registry backfill is not
   accepted as retrieval proof.
7. The generic old/new criminal-code caveat is suppressed for this asset path;
   it does not determine the PMLA Sections 5/17/8/26 procedure described here.
8. Explicit Section 5 attachment and explicit Section 17 freeze/seizure wording
   stay on their respective paths. Plain-language holds, liens, locks,
   restraints, and transfer bars retrieve both paths and tell the user to inspect
   the complete order instead of guessing the provision. Document attachments
   and blocked access to account records do not activate asset ownership.
9. Canonical PMLA passages satisfy the answer gate only at the registry snapshot.
   Request-level deduplication removes an older copy, ingestion retires undated
   projections, and source-gap validation rejects a stale fallback.
10. The reviewed deterministic answer remains available if the configured LLM
    is unavailable; the endpoint regression requires dated authority passages,
    the correct workflow, and branch-specific legal content.

Real-stack retrieval returned exactly Sections 17/8/26 and 5/8/26 for the two
paths. Live SSE replays selected the reviewed owner, emitted no unsupported
legal sentence, and cited only the active dated official provisions. Ambiguous
wording returned Sections 5/17/8/26 and a conditional dual-path answer; explicit
seizure wording used the seizure branch. Provenance re-verification reported
four verified chunks and zero failures, the real PostgreSQL migration contract
passed through `0016`, the wheel contained the full migration chain, and the
final broad non-stack regression completed with `1,166 passed` and zero
failures. The reviewer initially held the stage because the automated database
test stopped at `0005` and split Section 8/17 aliases could survive on an
already-migrated database. The repair added the rollback-isolated full-chain
test, immutable migration `0016`, runtime alias assertions, and a fresh
provenance audit. The repaired authority suite passed `39` tests, the focused
real-stack gate passed `4`, the release wheel contained `0016`, and the final

## 2026-07-17 P3 Guided Intake Safety and Privacy Gate

The first guided-intake slice is a bounded refinement layer over the reviewed
MatterPlan. It asks at most three material questions and derives them from the
existing route and plan; it does not run a second classifier, call an LLM, or
persist answers. Route-specific questions cover immediate safety, bank-hold
reason, criminal-regime transition, jurisdiction, cyber money loss, case stage,
documents, role, and desired outcome.

The criminal transition question is deliberately about the Section 531 fact,
not merely an incident or seizure date. Bare years and relative dates such as
"in 2023", "before 1 July 2024", or "after 1 July 2024" keep the question
open. Only explicit pending/started/concluded status or an explicit unknown
choice satisfies it. The four bounded choices are consumed by the same
`criminal_transition_status` classifier used by routing, so a refinement can
select saved CrPC, current BNSS, concluded/unknown, without a second routing
owner.

The SSE event is schema-versioned and bounded before browser rendering. Intake
controls remain editable while the first answer is streaming. A monotonically
increasing request ID plus the active `AbortController` prevents packets,
errors, or completion callbacks from an aborted request from overwriting a
newer refinement. Operational correlation uses a short SHA-256 fingerprint;
raw user questions are not emitted by the query-expansion or answer-coverage
logs covered by this gate. Intake guidance warns users not to share Aadhaar,
full account/card numbers, passwords, OTPs, or private intimate material.

Evidence for this slice: API intake/privacy `12/12`, affected no-stack API
regression `522 passed, 36 deselected`, web contract/stream-guard tests `6/6`,
frontend type-check and production build pass, and live device refinement
selected current BNSS and removed the transition question after the choice was
consumed. Fermat and Averroes independently re-reviewed the final patch and
returned PASS with no P0/P1/P2 findings.

This closes the intake implementation gate, not the product gate. The system
still needs a true independent holdout with human/legal-quality review,
un-injected authority recall measurement, privacy/security operations, and
production deployment controls before it can be called production-ready.

## 2026-07-17 Stage 1 Provenance RCA

The fresh 500-request live holdout exposed a corpus/provenance failure rather
than a latency failure. Wall-clock latency was healthy (`p50 4.7s`, `p90
17.5s`), routing and action-pack telemetry were present for all 500 rows, but
only `122/485` expected Act rows hit and only `219/500` produced a usable
answer. The most important cause was that many high-frequency official Acts
were present in the corpus but their documents/chunks were still
`provenance_verified=false`; production retrieval correctly excluded them.

The first repair is intentionally below retrieval and answer generation.
`scripts/verify_provenance.py` now tolerates India Code handle-page whitespace
and quote variants, retries transient discovery/download failures with bounded
backoff, fetches all candidate PDF artifacts, and prefers an exact pinned
SHA-256 over text similarity. Text similarity is diagnostic-only when a source
hash is missing; `--strict` exits nonzero and no document/chunk is promoted.
Legacy sources are compared per document over their complete
non-quarantined chunk sets. Temporary files are unique and cleaned up, and
promotion remains document/chunk scoped; it does not globally bless a source.

The NDPS source was independently checked against the official India Code
artifact, pinned locally at SHA-256
`ef1b399172971dc8bc6e4da0ae67444f62ee2ea05a983ac26821e96a4e866bd6` and
719,612 bytes, and passed strict verification; one compared document was
promoted locally. This is a verifier/authority-data stage result, not a
quality or production-readiness result. The next step is to verify the
high-frequency national Acts, re-run live smoke, and then repeat the full
holdout. No benchmark result file or local corpus data is part of the release
artifact.

The first authority batch then passed strict verification for TPA 1882,
Indian Contract Act 1872, POSH 2013, NI Act 1881, Income-tax Act 1961, POCSO
2012, RTE 2009, Dowry Prohibition Act 1961, Payment of Gratuity Act 1972,
Aadhaar Act 2016, and Bonded Labour System (Abolition) Act 1976. The batch
also corrected the Income-tax source from an invalid handle response to its
official India Code PDF artifact. A 50-row live smoke showed the expected
directional improvement in several routes, but remained far below launch
quality: Act hit/cited `28/50`, strict product pass `10/50`, critical pass
`5/24`, visible source gaps `30/50`, and safety hard fails `8/50`. Latency
remained healthy (`p50 5.1s`, `p90 12.5s`).

Trade Marks is intentionally not promoted: its six stored passages are
server-authored summaries and have only `0.0557` similarity to the official
PDF. This is a corpus reconstruction task, not a verifier threshold to lower.
The full 500 holdout must be rerun only after the remaining high-volume source
gaps and safety failures are addressed; the 50-row smoke is not a release
claim.

## 2026-07-17 Source-Gap Handoff Contract

Source verification is a hard boundary in the answer architecture. When the
required authority is missing, stale, unverified, or cannot be matched to the
required anchor, the API emits an intake-only `matter_route` event followed by
`source_gap`. The event may carry the route label, urgency/red flags, missing
facts, and a document checklist for preparation. It must carry empty
`required_sources` and `forums`, a null `legal_regime`, and an action pack with
empty next steps, portals, escalation, and cautions. This prevents a route
classifier's plausible forum or action pack from becoming unverified legal
advice.

The browser validates both the intake-only route invariant and every sentence
event before rendering. A malformed route or sentence clears the answer state
and raises the contract error; a source-gap handoff remains safe and visible.
The UI uses the handoff to tell the user what facts and records to gather,
without presenting a forum, portal, deadline, or legal conclusion as verified.

The stage was independently reviewed after implementation with no P0, P1, or
P2 findings. Focused validation passed with 119 backend tests, 13 web contract
tests, and web type-check. A fresh 500-request live holdout completed with no
errors or refusals, p50 latency 5.0s and p90 5.8s. It produced 339 source-gap
handoffs, 107/485 expected Act hits and citations, 59/500 strict product
passes, 37/183 critical passes, and 268/500 safety hard fails. These numbers
show correct fail-closed behavior and fast operation, but not sufficient legal
coverage or production quality.

The next architectural stage is authority coverage and plan completeness:
strictly verify and promote the highest-frequency official source packs, then
make the MatterPlan producer satisfy its schema and authority obligations on
both answered and handoff rows. No answer-generation or training change should
be accepted unless it improves the locked holdout without increasing safety or
source-gap violations.

## 2026-07-17 Provenance-Safe Document-to-Chunk Promotion

The provenance verifier now treats document-to-chunk promotion as a safety
boundary rather than a bookkeeping step. A document-level official artifact
check is persisted in one transaction with its derived chunk updates. On any
SQL failure, the transaction rolls back; a document cannot remain verified while
its retrieval chunks are stale or half-updated. Promotion targets are scoped to
the compared document IDs. Non-quarantined chunks are promoted only when they
are not owned by `document_authorities`; registry-owned chunks are changed only
by their exact chunk-scoped audit. Quarantined chunks are excluded from
promotion, and failed audits clear stale document/chunk verification without
unquarantining data.

Every live chunk is independently compared against the refetched official
artifact. Aggregate document similarity is used only for candidate scoring and
cannot mask a corrupted chunk in the final verdict. The generated chunker
prefix (`<exact document title>, Section N`) is stripped only when the prefix
title matches the stored document title after conservative punctuation
normalization. A different title remains part of the comparison and fails the
threshold. Hashless HF mirror extraction remains diagnostic-only and explicitly
cannot set `verification_pass`.

Evidence for this stage:

- `17` focused provenance tests passed; the real PostgreSQL rollback/scope
  fixture passed; `104` verifier/retrieval regression tests passed.
- Independent final review returned PASS with no P0/P1/P2 findings.
- Strict official India Code audits passed for NI Act, POCSO, and POSH. The NI
  Act has `125/126` live chunks verified; one corrupted/mixed chunk is
  quarantined and remains unavailable to retrieval.
- The fresh live holdout report is
  `data/processed/timed_eval_holdout_new500_provenance_20260717.md`.
  It completed `500/500` rows with zero transport errors: expected Act hit
  `230/485 (47.4%)`, cited hit `219/485 (45.2%)`, strict product pass
  `66/500 (13.2%)`, critical pass `40/183 (21.9%)`, safety hard fails
  `88/500`, route retrieval gaps `222/500`, route citation gaps `236/500`,
  MatterPlan authority retrieval gaps `403/1034`, MatterPlan citation gaps
  `411/1034`, and visible source gaps `322/500`.
- Latency was `p50 5.4s`, `p90 17.2s`, max `47.1s`; latency is not the only
  blocker, although the tail still needs an operational budget.

The 500 prompts are newly generated human-like wording from the curated
501-case inventory with prior exact prompt text excluded. They are not real-user
telemetry or blinded human/legal review, and the changed wording mix means the
metrics must not be presented as a causal before/after comparison against the
earlier source-gap handoff run. The release remains blocked by authority
coverage, plan-obligation retrieval/citation, refusal calibration, and the
safety gate. The next implementation target is the recurring missing authority
families and MatterPlan producer, not answer-model training.

## 2026-07-17 Exact Authority Identity and 500-Row Gate

The serving identity layer now treats a split anchor as an ambiguous storage
representation until the passage heading proves the legal provision. This
applies to both numeric requests and explicit alphanumeric requests. For
example, `sec-22-a` can represent a split chunk of Article 22 or a neighboring
Article 22A; only a matching heading in the passage text can decide. The same
rule protects RTI Section 6 versus 6A and HMA Section 13A versus a Section 13
fragment. Native anchors such as `sec-66e` remain distinct and may pass their
exact identity check.

The generic statute matcher is not allowed to undo that decision. Explicit
Act/Code section requirements take the strict section path before broad
statute-specific branches. HMA's legacy Section 13 divorce-ground matcher has
an additional guard for explicit alphanumeric sections. Constitution and RTI
special branches use the same heading-aware matcher rather than broad anchor
membership. This is a fail-closed provenance invariant, not a retrieval
ranking heuristic.

Source-pack identity is also part of legal provenance. When multiple packs have
the same Act title, the plan cannot bind by title alone. A child-specific
Christian succession pack is selected when a query explicitly contains child
relationship terms, even when `widow` makes the base pack tie on selection
score. The resulting ledger keeps the exact source-pack ID and `/sec-37`
anchor requirement. Title-only authorities without registry identity remain
provisional; an unknown religion does not create a generic personal-law
authority obligation.

Validation for this stage: `161` focused source-gap/planner tests, `1` exact
endpoint regression, direct negative probes for Article 22A, RTI 6A, and HMA
Section 13, direct positive probe for HMA 13A, and independent reviewer GO.
The fresh 500-row holdout completed `500/500` with zero transport errors. Its
report is
`data/processed/timed_eval_holdout_new500_anchorfix_final_20260717.md`.
Expected Act hit and cited hit were both `120/485 (24.7%)`; strict product
pass was `63/500 (12.6%)`; legal-safety hard fails were `264/500`; visible
source gaps were `335/500`; and MatterPlan obligation retrieval/citation were
`245/313` and `236/313`. Latency was `p50 5.1s`, `p90 5.9s`, max `31.5s`.

The stage therefore proves identity hardening and no transport regression, but
not product quality. The same prompt set before this patch had `120/485`
Act hit/cited, `64/500` strict pass, and `264/500` safety hard fails. The
system is not production-ready. The next architecture target is to make the
MatterPlan producer/schema a first-class gate on every row, followed by strict
verification and retrieval coverage for the high-frequency missing authorities
(senior maintenance, succession, labour/EPF, welfare, revenue/land, IBC/NCLT,
trademark/IP, prison procedure, business/MSME, and state/local law). Do not
fine-tune the answer generator until those evidence and safety gates improve.

## 2026-07-17 Intake Ownership and Fresh Holdout Evidence

The serving ownership layer now has explicit guards for generic consumer
ownership. Vehicle terms use word boundaries, and a vehicle is treated as a
consumer product only when the query also supplies online/seller/manufacturer
context. This prevents a bike service-centre dispute or a seized-device query
from being silently converted into a defective-goods answer while preserving
the online-vehicle warranty path. Registered-will queries have a dedicated
owner, and PMLA/UAPA non-criminal plans use schema-valid non-applicable
incident-date statuses rather than pretending to know a criminal cutover.

The evaluator distinguishes an intentional safe source-gap handoff from an
answer row with a malformed MatterPlan. This improves diagnosis only: a safe
handoff remains a product failure because the user still lacks a supported
answer. The safety evaluator applies the same distinction, so it does not call
an intentionally empty source-gap handoff dangerous solely for omitting an
operative forum or legal regime. Real answers with missing authority, dangerous
framing, or nonzero source counts still fail closed.

Validation and evidence:

- Independent review returned GO with no P0/P1/P2 findings; targeted ownership
  and schema tests passed `289` tests.
- The fresh 500-row run used seed `2026071717` and excluded prior exact prompt
  packs. It completed `500/500` with `0` transport errors, `500/500` route
  matches, `120/485 (24.7%)` expected Act hits and citations, `63/500`
  strict product passes, `4/500` legal-safety hard fails, and `336/500` safe
  source-gap handoffs. Latency was `p50 5.0s`, `p90 5.7s`, max `25.9s`.
- MatterPlan authority retrieval/citation were `245/310` and `237/310` on
  applicable answer rows. The common-user gate measured `91/500 (18.2%)`
  product passes, `58.4%` must-term coverage, `16` route-required source gaps,
  `336` visible source gaps, and `25.3s` LLM-path p90.
- The failure ledger grouped `409` strict failed rows: `360` source/retrieval
  gaps, `16` route-source gaps, `62` criminal-procedure high-risk rows, `44`
  labour/welfare rows, and `36` family/child-safety rows.

The evidence confirms that latency and routing are functioning, but the
authority graph/source packs and MatterPlan obligation producer remain the
dominant product bottlenecks. Training the answer model now would amplify
unsupported coverage; source activation, provenance, and action-pack contracts
must improve first. The repository is not production-ready.

## Source-Gap Guided Intake (2026-07-19)

Source gaps are a typed recovery protocol, not a generic empty answer. When
the server has a canonical state or local authority gap, it emits a sanitized
route, the source-gap contract, and a bounded intake event. The intake is
fact-only: jurisdiction, date, and document status may be requested, while
MatterPlan logistics, forums, portals, deadlines, and legal conclusions remain
withheld until a retry verifies the authority.

The browser reducer treats the source-gap event as a latch. It clears the plan,
passages, sources, relevance, and operative sentences; rejects late route or
answer events; and accepts intake only when the latched gap kind is
`state_or_local_authority_gap`. Both API and UI enforce the 2,000-character
query budget, so guided retry construction cannot silently exceed the serving
contract.

This protocol is intentionally orthogonal to retrieval quality. It improves
honesty and recovery for unsupported jurisdictional procedures, but it cannot
create missing law. Authority registry activation, exact provenance, and
source-pack coverage remain the quality bottleneck and must be evaluated on
fresh holdouts before any production claim.

## Municipal and Food-Authority Ownership Boundary (2026-07-19)

The router treats a municipal/local authority sealing as the operative action.
That ownership wins even when the user mentions a generic food inspection or
an FSSAI inspection. An FSSAI route is selected for an explicit food-safety
authority/fact, such as FSSAI, a food-safety officer, a food inspector, food
licensing, food poisoning, contaminated/unsafe/adulterated food, or a
sanitation inspection without an ambiguous department actor. Unnamed health or
food departments remain in the bounded business-license/intake path rather
than being asserted as FSSAI.

Bare corporation is deliberately not a municipal identity because private
companies use the same word. Named city-corporation phrases use a
qualifier-aware matcher: private/Pvt/Ltd/Limited/company/entity qualifiers are
rejected, while a genuine city corporation can own the municipal route. The
source-gap materiality check mirrors the same qualifier rule, so exact Act or
FSSAI regulation passages cannot satisfy the missing municipal-law obligation.

Negated food facts are fail-closed before specialized FSSAI routing. The
boundary covers direct phrases and a bounded negation pattern for forms such
as not/no/does not involve food, hygiene, contamination, unsafe food,
adulterated food, or food poisoning. Active evidence fixtures use the
configured document IDs, source packs, anchors (/sec-26, /reg-2-1), and
source types (bare_act, regulation).

Validation for this stage: selected router/source-gap/workflow tests passed
207, the deterministic backend suite passed 2062 with stack/model tests
excluded, the web protocol suite passed 18, TypeScript passed, and the latest
independent review returned GO for the final routing/source-gap boundary.
This improves authority ownership and handoff correctness; it does not replace
the required fresh 500-prompt quality gate, which remains blocked until the
serving database is available.

## Municipal Boundary Review Closure (2026-07-19)

`apps/api/local_authority.py` is now the shared identity boundary for municipal
routing and source-gap materiality. It rejects private/Pvt/Ltd/company/entity
city-corporation names, distinguishes generic health actors from explicit
local/municipal health actors, and exposes one narrow predicate for a public
hawker/vending permit plus a concrete corporation removal/seizure. The latter
is intentionally paired with source-gap vocabulary for every accepted wording;
otherwise a route could be public while its local procedure requirement was
silently treated as non-material.

The boundary was independently reviewed by Hubble and Avicenna, both GO with no
P0/P1/P2 findings. The final affected deterministic suite passed `1119` tests;
`57` stack/model tests were excluded because the local database/model services
were unavailable. This is a correctness milestone, not a product-quality
milestone: the API must still start against PostgreSQL and pass a fresh real
500-prompt holdout before production readiness can be considered.

## Bounded Database Startup (2026-07-19)

`POSTGRES_CONNECT_TIMEOUT_SEC` is a bounded setting (`0 < value <= 60`) passed
to `asyncpg.create_pool` for both host-side development and the production
Compose overlay. The API still fails closed when the database is unavailable,
but it now exits promptly with a connection timeout rather than hanging during
lifespan startup. Invalid values are rejected by Settings and the pool builder
retains a defensive clamp for non-Settings test/runtime doubles.

Independent review returned GO from both Hubble and Avicenna. The full
deterministic API suite passed `2075` tests, with one explicitly skipped live
database contract and `70` stack/model/evaluation tests deselected. This is an
operations improvement, not evidence of corpus quality or production
readiness; live database startup and a fresh 500-prompt holdout remain required.

## Verified Readiness and Service Probe (2026-07-19)

`/readyz` is now a release-orchestration check, not a row-count check. It counts
only chunks that are live (`NOT quarantined`) and satisfy the exact production
provenance predicate used by retrieval: either the chunk is explicitly
verified, or it has no conflicting authority mapping and its parent document is
verified. A document contributes to readiness only when it owns at least one
such chunk. The CI seed is intentionally unverified and therefore cannot make
the API ready.

`/healthz` keeps the same corpus/build information on success, but returns a
sanitized `503` with `dependency=postgres` and
`reason=database_unavailable` when the database cannot be reached. The lifespan
still closes the pool if model prewarm fails. Production Compose calls
`/readyz` from its API healthcheck and starts the web service only after the API
is healthy.

Independent Hubble and Avicenna reviews both returned GO with no P0/P1
findings. Focused readiness/provenance tests passed `7`; the full live service
probe did not pass because Docker/OrbStack is stopped and the active local
Postgres cluster has no `lawrag` role/database. This stage improves operational
truthfulness but does not establish corpus quality, answer quality, or
production readiness. A populated database, `/readyz` verification, and a
fresh real 500-prompt holdout are still mandatory.

## Live Service and Fresh 500 Holdout (2026-07-20)

The populated local service was restored without initializing a replacement
database. The API and web app served successfully from the same worktree:
`/healthz?deep=true` reported `189907` indexed chunks, `5808` documents, and
build fingerprint
`2be63bea2eb7205c62e3202c4953eb617e3832dad9d79b54fca6e6887f00b2f3`; the web
root returned HTTP 200. The holdout was pinned to that fingerprint, so the
benchmark cannot silently exercise a different checkout.

The first 500 unique prompts from the new 501-question human-like inventory
were streamed through the live `/answer` endpoint and completed `500/500` with
zero transport errors, zero API errors, and zero refusals. This inventory is
synthetic human-like evaluation data, not production user telemetry or blinded
human legal review; it must be described that way in grant, product, and release
materials.

Measured results:

- expected Act hit `189/485 (39.0%)`; expected Act cited `187/485 (38.6%)`;
- strict timed product pass `132/500 (26.4%)`; common-user gate pass
  `162/500 (32.4%)`;
- route match `499/500 (99.8%)`; MatterPlan contract valid on `247/247`
  applicable answer rows;
- source-gap handoffs `253/500`, route required-source retrieval gaps `13`,
  route citation gaps `19`, and MatterPlan authority citation gaps `45`;
- legal-safety hard fails `1/500`, labelled `dangerous_off_topic` for a CIBIL
  loan-closure/NOC query that was routed without a supported answer;
- total latency p50 `5.2s`, p90 `6.1s`, max `38.6s`; the LLM-path p90 was
  `24.9s` across `19` rows.

The result confirms that the service is operational and routing is strong, but
the product is not production-ready. The dominant blocker remains activated,
provenance-verified authority coverage and citation completion, especially for
criminal/custody procedure, labour/welfare, property/succession, banking,
consumer, local/state, and long-tail routes. The single safety hard fail must
also become a regression before release. Training the answer generator is still
premature: it would increase confidence without repairing the `293` source or
retrieval-gap rows in the failure ledger.

## Multi-Pack Evidence Identity and Juvenile Custody Repair (2026-07-21)

One verified `RetrievedChunk` may legitimately discharge more than one reviewed
`SourcePack` obligation. This is common when a single statutory section is
needed both by a generic Act pack and a narrower procedure pack. The retrieval
boundary therefore preserves two metadata fields:

- `_required_source_pack` is the deterministic primary pack used for existing
  ranking and UI behaviour.
- `_required_source_packs` is the complete set of reviewed pack identities that
  the same verified chunk may satisfy.

Deduplication and source-pack merging must union the complete set rather than
discarding a lower-priority label. Source-gap validation, required-authority
preservation, authority-graph matching, and final MatterPlan preflight consume
the complete set. They still require the original exact document, source type,
title, and section-anchor constraints. Aliases do not turn a broadly similar
passage into authority for an unrelated route.

The distinction matters in the Juvenile Justice custody workflow. Section 12
may satisfy both the general JJ Act pack and the reviewed bail/board pack, while
section 94 is evidence for age determination. The court/JJB requirement is
separate and must be anchored to section 9. The `jj_2015_age_claim_court`
pack consequently accepts only `/sec-9`; section 94 belongs to
`jj_2015_age_documents`. This prevents source-gap and workflow logic from
accepting different sections for the same asserted court route.

The acceptance test is end-to-end, not retrieval-only. For a minor reported in
adult custody, the final bounded answer set must contain official JJ Act
sections 94, 9, and 12; select the
`juvenile_adult_jail_age_determination` workflow; and emit no source-gap
handoff. A generic adult bail query must not select this juvenile workflow.
Focused unit tests protect shared-pack preservation and juvenile source-gap
matching, while live `/answer` replays protect the final top-k and workflow
boundary where earlier defects occurred.

## Canonical Public Provenance and Safe-Handoff Validation (2026-07-22)

The API now treats provenance identity as a public contract across every answer
path. A retrieved chunk's stored `anchor` is immutable; focused retrieval can
provide a friendly `display_anchor`, but the `passages` and both template and
model-backed `sources` SSE events must include the canonical anchor, stable
document key, and database chunk ID. This makes a citation traceable to the
precise verified corpus record that supported it.

Source-gap canonicalization is intentionally strict without breaking complete
legacy diagnostics. It accepts only a boolean `has_gap` plus either a non-empty
gap-kind list or a complete missing-required-source record. Nested
`required_anchor_patterns` are validated item-by-item. Malformed supplied
payloads are visible as `invalid_source_gap_payload`; they cannot be silently
cleaned into an apparently ordinary coverage gap.

The plain-language adoption boundary recognizes a planned family adoption such
as "want to adopt my sister's child" while rejecting policy and pet examples
that contain the same vocabulary. The final API regression passed `2354` tests
with one explicitly opt-in PostgreSQL provenance test skipped. This validates
the contract boundary only; a fresh 500-row synthetic human-like evaluation and
independent human/legal review remain required before production readiness.

## LSA Owner Boundary and Projection Repair (2026-07-31)

Lok Adalat traffic intake is split into two distinct answer owners. A pending
or referred traffic challan uses `lok_adalat_traffic_settlement` and Sections
19/20/21 of the Legal Services Authorities Act; a question about an award's
finality, consent, fraud, coercion, or challenge uses
`lok_adalat_award_challenge` and is owned by the Section 21 contract. Both
routes are selected before generic legacy rendering and are independently
validated in MatterPlan ownership tests.

The LSA owner boundary now requires all of the following on every activating
passage: verified chunk provenance, the dated `1994-10-29` projection, the
canonical document key, `bare_act` source type, the exact LSA source-pack ID,
the expected authority ID on the passage, and that same authority ID under
that exact pack's authority map. An ID supplied by a neighbouring pack cannot
discharge this owner.

Authority projection retirement is first-marker preserving. A dated correction
retires the matching undated projection, but a later replay or repair
migration must not rewrite its original
`authority_projection_retired_by_migration` metadata. Stale `-official`
projections are retired by the dedicated 0029 repair. Deployments that already
applied an older 0029 implementation must run
`scripts/repair_lok_adalat_retirement_metadata.py --apply`; the command is
idempotent and changes only the three quarantined, undated LSA anchors.

The retrieval-to-answer contract exposes `provenance_verified` publicly so
owner contracts can fail closed rather than trusting title and anchor strings
alone. This is an integrity gate, not a quality claim: the next release gate
still requires a fresh 500-prompt holdout, zero safety hard fails, and material
improvement in required-source coverage and cited-Act accuracy.

## Official Section Supplements and Release Reproducibility (2026-07-31)

High-risk routes must be wired through the same four contracts: route-required
authority, source pack, source-gap validator, and verified corpus passage. The
PWDVA safety route now uses the independently hash-pinned
`domestic-violence-2005-official` section supplement for Sections 2, 3, 12,
17, 18, 19, 20, 27, and 29. The legacy document remains an identity bridge,
but its unverified chunks cannot satisfy the runtime source-gap gate. The
validator therefore accepts the official supplement document key explicitly;
title similarity alone is never enough.

Source-pack exclusions are applied after category-specific branches as well as
inside branches that can add the same Act. This is important for role-sensitive
queries such as a man reporting violence or property taken by his wife: a
PWDVA pack must not be injected merely because the words `wife` and `jewellery`
appear. Common user wording such as `punched me`, `assaulted me`, and
`threatened to kill me` is covered by the same exclusion contract. Explicitly
negated mentions such as `not asking about gratuity` are likewise excluded
from gratuity source-pack scope while salary authorities remain available.

Before a production release, run the idempotent promotion command through the
tracked Make target:

```text
make promote-source-packs
```

The command downloads or uses each locally provisioned artifact, verifies the
expected byte count and SHA-256, extracts the pinned sections, and promotes
only exact section chunks in a transaction. A missing artifact, changed hash,
changed predecessor identity, or section-text mismatch fails the release
closed. This command is a data-plane release prerequisite, not an API startup
side effect.
