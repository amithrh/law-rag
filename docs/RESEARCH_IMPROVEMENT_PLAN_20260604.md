# Law RAG Product Improvement Plan - 2026-06-04

## Current State

Fresh 500 human-messy eval:

- Product pass: 392/500 (78.4%), target 95%.
- Route match: 499/500 (99.8%).
- Expected Act hit: 456/484 (94.2%).
- Expected Act cited: 446/484 (92.1%), target 93.5%.
- First cited actionable: 500/500.
- Safety hard fails: 3.
- Relevance not ok: 70.
- p50 latency: 7.0s; p90 latency: 21.0s.

The biggest gap is no longer broad routing. It is product-quality grounding: the system often knows the rough matter type, but still fails to cite the required authority, answer the user's exact question, or handle state/date/personal-law constraints consistently.

## External Research Takeaways

- LegalBench-RAG argues legal RAG should retrieve minimal, highly relevant legal snippets, because large imprecise chunks raise cost/latency and make citation support harder: https://arxiv.org/abs/2408.10343
- ARES separates RAG evaluation into context relevance, answer faithfulness, and answer relevance, using a small human-labelled set to calibrate judges: https://arxiv.org/abs/2311.09476
- Self-RAG shows that retrieval should be adaptive, with self-reflection over retrieved passages and generated claims rather than fixed top-k retrieval for every query: https://arxiv.org/abs/2310.11511
- CRAG proposes a retrieval evaluator that detects weak retrieval and triggers corrective actions before generation: https://arxiv.org/abs/2401.15884
- NIST AI RMF and the Generative AI Profile frame production AI as lifecycle risk management: governance, testing, monitoring, incident handling, and risk tolerance must be explicit: https://www.nist.gov/itl/ai-risk-management-framework and https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf

## Claude CLI Review Summary

Claude's CLI review agreed with the main diagnosis: the current repo behaves like a benchmark-fitted expert system. The route cascade, source packs, and answer templates help specific clusters, but they do not scale to the state-law and procedural tail. Claude's highest-priority recommendation was:

1. Fix hard safety regressions first, especially testamentary/will questions falling into criminal routes.
2. Add corrective retrieval instead of endlessly adding source packs.
3. Track corpus coverage explicitly so source gaps are not confused with retrieval failures.
4. Calibrate relevance evaluation before using it as a hard product gate.
5. Move citation enforcement into the answer verification layer.

## Product-Grade Architecture Direction

### 1. Authority Graph

Build a legal authority graph with fields:

- matter route
- jurisdiction/state
- date regime
- personal law
- required Act/rule
- section anchors
- forum
- limitation/deadline
- remedy
- evidence/documents
- escalation path

This should become the source of truth for action packs and required-source gates. The router should fill slots; retrieval should satisfy the graph; generation should not invent remedies outside the graph.

### 2. Corrective Retrieval Loop

Before answering:

1. Retrieve with current route/source-pack logic.
2. Grade whether top sources contain the required Act/section/forum.
3. If weak, retry with statute-name expansion, exact section lookup, FTS fallback, and state/date-specific query expansion.
4. If still weak, return a source-gap response rather than a confident answer.

This targets expected_act_missing and relevance failures generically.

### 3. Citation Enforcement

For each answer sentence that makes a legal claim:

- require one supporting cited passage;
- prefer statutes/rules for procedural remedies;
- use judgments only for interpretation or remedies not directly covered by statute;
- if a required source is retrieved but not cited, run a repair pass before returning.

This targets expected_act_not_cited without chasing answer wording.

### 4. Calibrated Evaluation

Replace single hard `relevance_not_ok` gating with calibrated dimensions:

- route correctness;
- context relevance;
- required authority retrieved;
- required authority cited;
- answer faithfulness;
- answer relevance;
- user-action usefulness;
- legal safety.

Legal safety stays a hard gate. Relevance judge output should become a calibrated signal, not a single opaque blocker, until it has a human-labelled validation set.

### 5. Corpus Coverage Ledger

Add a ledger for missing or partial official sources:

- state Shops and Establishments Acts;
- state witch-branding/tonhi/daayan Acts;
- tribal land transfer/restoration laws by state;
- welfare schemes and service-delivery rules;
- RBI/FIU/cyber/platform workflows;
- municipal sealing/local authority routes;
- state cattle/excise rules.

Every failed expected Act should be marked as either `in_index`, `retrieval_missed`, `citation_missed`, or `corpus_gap`.

### 6. Latency Hardening

Keep p50 below 10s and p90 below 20s by:

- deterministic action-pack answers for high-frequency procedural routes;
- parallel retrieval/verification where possible;
- caching stable source-pack retrieval;
- streaming long answer generation;
- model timeout and retry ceilings.

## Implementation Stage 1

Implemented in this branch:

- Early high-precision testamentary routing before criminal/high-risk catchalls.
- Tighter self-harm context so generic `i will` does not contribute to false crisis routing.
- Expanded testamentary phrases for real user wording: `make will`, `wrote will`, `registered my will`, `latest will`, `valid will`, `will giving`, `sub registrar` with will context.
- Strengthened Indian Succession Act / Registration Act source packs for will questions.
- Added a general Mediation Act route for non-commercial "how to initiate mediation without court" questions.
- Added Mediation Act + Legal Services Authorities source packs for that route.
- Added regression tests for the fresh 500 hard failures and the mediation fallback.

## Next Implementation Stages

1. Police/custody consistency:
   - default bail/no chargesheet;
   - lockup beating/bribe;
   - SC/ST FIR refusal;
   - arrest memo/FIR copy/date-regime handling.

2. State source coverage:
   - Tamil Nadu Shops and Establishments;
   - Chhattisgarh/Jharkhand witch-branding;
   - scheduled-area/tribal land restoration packs;
   - welfare identity/ration/Aadhaar mismatch packs.

3. Corrective retrieval prototype:
   - required-source check after rerank;
   - statute-name retry;
   - exact section/anchor retry;
   - source-gap classification.

4. Citation repair:
   - detect required Act retrieved but uncited;
   - re-prompt with source requirement;
   - reject unsupported legal-claim sentences.

5. Eval calibration:
   - create 150-300 human-labelled rows from failures;
   - score route/context/faithfulness/relevance separately;
   - keep legal safety as a hard gate.

## Production Gate

Do not call this production-grade until:

- Product pass >= 95% on fresh 500 human-messy prompts.
- Safety hard fails = 0 on fresh and old prompts.
- Expected Act cited >= 93.5%.
- p50 latency <= 10s and p90 <= 20s.
- No high-frequency route falls to `general_legal`.
- Source-gap ledger is explicit and visible in reports.
