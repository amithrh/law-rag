# Fresh 100-Prompt Codex vs Claude Eval, Round 2

Date: 2026-05-27 IST
Prompt set: `data/eval_500`, persona-balanced selection, seed `20260527`, limit `100`
Outputs: `data/processed/fresh100v2_codex_final_20260527.jsonl` and `data/processed/fresh100v2_claude_final_20260527.jsonl`

## Executive Summary

Codex is the stronger product branch right now: it is 19.2s median versus Claude at 67.6s, emits route/timing/action-pack telemetry on every row, and now passes the median latency gate on this run. The latency hardening landed: query expansion is effectively zero-cost, retrieval p50 is 4.5s, and the remaining tail is mostly LLM streaming.

Claude had better expected-Act citation hit on this harder seed, 35/49 (71.4%) versus Codex 24/49 (49.0%), and it answered more rows as `ok`. But Claude is not a one-step legal solution branch: p50 is 67.6s, p90 is 81.8s, route/action/timing telemetry is 0/100, and it marked multiple real legal/welfare/safety prompts as off-topic or no-relevance.

Neither branch is ready to ship as a legal one-step solution. Codex won the product-readiness lane; Claude won this run's expected-Act hit lane. The next Codex work should attack recall/route coverage without giving back the latency gains.

## Branches Tested

| system | branch | commit | worktree | API port |
| --- | --- | --- | --- | ---: |
| Codex | `codex/latency-hardening` | `61b7d7469a45 + Stage 4 dirty worktree` | `/Users/amitmishra/worksppace-central/law-rag/.claude/worktrees/nervous-hodgkin-c617cc` | 8031 |
| Claude | `claude/nervous-hodgkin-c617cc` | `ecc095174361` | `/private/tmp/law-rag-compare-claude` | 8032 |

Both runs used the same local DB/corpus and the same prompt order. Local corpus count at report time: chunks=743429, documents=26190.
Ollama was served from host `127.0.0.1:11434` with `qwen3:14b` available; Docker Ollama was kept stopped during branch evaluation to avoid routing generation through the CPU-only container listener.

## Commands Run

```bash
POSTGRES_HOST=localhost POSTGRES_HOST_PORT=5433 POSTGRES_DB=lawrag POSTGRES_USER=lawrag POSTGRES_PASSWORD=change-me-locally \
  PYTHONPATH=. .venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8031 --workers 1
PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8031 \
  --queries-dir data/eval_500 --limit 100 --seed 20260527 --timeout-s 300 \
  --out data/processed/fresh100v2_codex_final_20260527.jsonl \
  --report data/processed/fresh100v2_codex_final_20260527.md
```

```bash
git worktree add /private/tmp/law-rag-compare-claude claude/nervous-hodgkin-c617cc
cd /private/tmp/law-rag-compare-claude
POSTGRES_HOST=localhost POSTGRES_HOST_PORT=5433 POSTGRES_DB=lawrag POSTGRES_USER=lawrag POSTGRES_PASSWORD=change-me-locally \
  PYTHONPATH=. /Users/amitmishra/worksppace-central/law-rag/.claude/worktrees/nervous-hodgkin-c617cc/.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8032 --workers 1
cd /Users/amitmishra/worksppace-central/law-rag/.claude/worktrees/nervous-hodgkin-c617cc
PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8032 \
  --queries-dir data/eval_500 --limit 100 --seed 20260527 --timeout-s 300 \
  --out data/processed/fresh100v2_claude_final_20260527.jsonl \
  --report data/processed/fresh100v2_claude_final_20260527.md
```

## Scorecard

| metric | Codex | Claude | readout |
| --- | ---: | ---: | --- |
| Rows completed | 100 | 100 | tie |
| Errors | 0 | 0 | both clean transport |
| Refused | 23 | 2 | Codex is stricter, sometimes too strict |
| Relevance `ok` | 54 | 77 | Claude answers more often |
| Relevance `partial` | 6 | 9 | low/medium difference |
| Relevance `no_relevance` | 12 | 4 | Codex has more hard misses/refusals |
| Relevance `off_topic` | 5 | 8 | both unsafe proxy failures |
| Expected Act hit | 24/49 (49.0%) | 35/49 (71.4%) | Claude +11 hits |
| Wall latency p50 | 19.2s | 67.6s | Codex about 3.5x faster |
| Wall latency p90 | 24.8s | 81.8s | Codex faster tail |
| Wall latency max | 43.8s | 104.2s | Claude max above 100s |
| Route events | 100/100 | 0/100 | Codex debuggable, Claude opaque |
| Timing events | 100/100 | 0/100 | Codex debuggable, Claude opaque |
| Action packs | 76/100 | 0/100 | Codex has workflow layer |

## Gate Check

| gate | target | Codex | Claude | pass? |
| --- | ---: | ---: | ---: | --- |
| Expected Act hit | >=85% | 24/49 (49.0%) | 35/49 (71.4%) | fail both |
| Median wall latency | <20s | 19.2s | 67.6s | Codex pass, Claude fail |
| Dangerous framing | 0 | not proven | not proven | fail both until manually audited |
| Route/action telemetry | required | 100/100 routes, 76/100 packs | 0/100 routes, 0/100 packs | Codex pass, Claude fail |

Dangerous framing is not directly judged by this evaluator. The proxy risks are legal prompts marked `off_topic`, `no_relevance`, refused, or routed into visibly wrong categories. Manual legal-safety labeling is still required before shipping.

## Latency Detail

| stage | Codex p50 | Codex p90 | Codex max | Claude p50 | Claude p90 | Claude max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wall_ms | 19.2s | 24.8s | 43.8s | 67.6s | 81.8s | 104.2s |
| total_ms event | 19.2s | 24.8s | 43.8s | n/a | n/a | n/a |
| query expand | 0.0s | 0.0s | 0.0s | n/a | n/a | n/a |
| retrieval | 4.5s | 5.1s | 5.5s | n/a | n/a | n/a |
| LLM stream | 16.0s | 22.2s | 38.6s | n/a | n/a | n/a |
| verification | 0.7s | 0.9s | 1.3s | n/a | n/a | n/a |

Codex was faster on 100/100 prompts. Claude was faster on 0/100 prompts.

## Expected Act Head-to-Head

| bucket | count | rows |
| --- | ---: | --- |
| Both hit | 19 | 4, 8, 12, 13, 16, 18, 20, 27, 34, 35, 40, 45, 61, 68, 71, 73, 76, 86, 94 |
| Codex hit, Claude missed | 5 | 23, 43, 52, 53, 83 |
| Claude hit, Codex missed | 16 | 1, 7, 10, 19, 30, 31, 41, 48, 57, 58, 64, 78, 90, 91, 99, 100 |
| Both missed | 9 | 2, 3, 11, 33, 42, 50, 72, 81, 92 |

## High-Signal Findings

1. Codex latency improvements landed. Query-expansion fallback is no longer a hidden LLM call, single-query retrieval keeps retrieval p50 near 4-5s, and total median moved under the 20s gate.
2. Codex recall is not good enough on this harder seed: expected Act hit is only 49.0%. Its biggest misses are `general_legal` spillover, welfare/labour, succession/property mutation, cyber/private-photo, and gig/platform matters.
3. Claude retrieved/cited expected Acts more often on scored prompts, but it is too slow for a real product and has no matter router, legal regime, action pack, or timing telemetry.
4. Claude has serious off-topic/no-relevance failures on real legal prompts: wage deductions, NREGA/job card, prison mulaqat, displacement/rehabilitation, stalking, and vulnerable-worker discrimination.
5. Neither branch can claim `0 dangerous framing`; this run is a timed/product eval, not a full legal-safety audit.

## Codex Branch Changes Validated

- Host Ollama routing now defaults API calls to `127.0.0.1` while preserving Docker/prod compatibility through `OLLAMA_API_HOST` and legacy `OLLAMA_HOST` in container mode.
- LLM query-expansion fallback is disabled by default; deterministic route-aware expansion remains on.
- Single-query expanded retrieval skips the slow sparse fallback for one-variant cases, merges required source packs, then reranks the union.
- Router/source-pack coverage expanded for cyber intimate-image harm, POCSO/minor survivor, senior citizen maintenance/gift issues, forest/FRA/PESA, legal aid, Lok Adalat, CrPC/BNSS procedural source packs, and passport/police verification handling.

## Suggested Next Work For Codex

1. Improve recall before training: add deterministic route/source packs for the top miss families in this report.
2. Split `general_legal` into smaller procedural/intake buckets so source packs fire before retrieval.
3. Add a legal-safety eval layer with labels for wrong forum, wrong deadline, wrong regime, dangerous off-topic, and unsafe refusal.
4. Keep the latency budget fixed: any recall change must preserve median <20s and preferably reduce p90 below 25s.
5. Delay document generation until routing, required-source hit rate, and dangerous-framing gates pass.

## Proxy Safety Failures To Inspect

| system | row | verdict | persona | prompt |
| --- | ---: | --- | --- | --- |
| Codex | 2 | REF | migrant_labour | domestic worker bangalore madam not paying 3 months said i broke vase wants 8000 |
| Codex | 6 | REF | small_business | buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck |
| Codex | 7 | REF | tribal_marginalized | thana refused to file complaint against zamindar who burnt our hut latehar |
| Codex | 10 | REF | youth_digital | got porn video featuring lookalike of me 2 lakh views not me but face same |
| Codex | 11 | REF | elderly | my husband died 2024 i am 78 mutation of land in my name jharkhand process |
| Codex | 14 | REF | procedural | family court summons received what is the next step before lawyer |
| Codex | 19 | REF | women_vulnerable | my husband's brother has been making me uncomfortable saying things and now grabbed my hand whom to tell I cant tell husband |
| Codex | 29 | REF | women_vulnerable | I am hearing impaired my employer is not providing interpreter for HR sessions and now they say I missed important update |
| Codex | 30 | REF | youth_digital | someone leaked my chat with therapist on twitter mental health privacy |
| Codex | 32 | off_topic | migrant_labour | contractor said go back home pandemic no return ticket money given 9 of us walked from delhi |
| Codex | 33 | REF | prisoner_undertrial | i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain |
| Codex | 38 | REF | urban_pro | my startup co founder is trying to dilute my equity using ESOP pool without my consent, i have 30 percent |
| Codex | 42 | off_topic | migrant_labour | construction site delhi 14 hour work no overtime contractor laughing when i ask |
| Codex | 48 | REF | urban_pro | ola driver took longer route and charged extra fare, customer support is closing complaint without resolution |
| Codex | 50 | REF | youth_digital | zomato rider here met with accident on bike no insurance from company |
| Codex | 60 | REF | youth_digital | got income tax notice 143(1) for 6 lakh youtube adsense income panic |
| Codex | 62 | REF | migrant_labour | cab driver mumbai uber deactivated rating low because customer racist hindi speaker |
| Codex | 63 | off_topic | prisoner_undertrial | wife mulaqat denied prison superintendent saying no list kya rule hai delhi |
| Codex | 65 | REF | rural_dlsa | I am ASHA worker not paid honorarium 6 months who can help |
| Codex | 72 | REF | migrant_labour | factory deducted 800 every month for shoes uniform never given orissa worker tiruppur knitwear |
| Claude | 11 | off_topic | elderly | my husband died 2024 i am 78 mutation of land in my name jharkhand process |
| Claude | 42 | off_topic | migrant_labour | construction site delhi 14 hour work no overtime contractor laughing when i ask |
| Claude | 47 | off_topic | tribal_marginalized | nrega job card not given by panchayat 9 months pls help nuapada odisha |
| Claude | 63 | off_topic | prisoner_undertrial | wife mulaqat denied prison superintendent saying no list kya rule hai delhi |
| Claude | 65 | REF | rural_dlsa | I am ASHA worker not paid honorarium 6 months who can help |
| Claude | 72 | off_topic | migrant_labour | factory deducted 800 every month for shoes uniform never given orissa worker tiruppur knitwear |
| Claude | 92 | off_topic | migrant_labour | biharee called we are by site engineer pune always after wage complaint is this crime |
| Claude | 96 | REF | small_business | fssai notice mismatch in licence category for snack manufacturing renewal due how to upgrade state to central |
| Claude | 97 | off_topic | tribal_marginalized | iron ore mine displaced our 12 villages no rehabilitation given keonjhar |
| Claude | 99 | off_topic | women_vulnerable | ex boyfriend follows my scooty everyday from office to home he doesn't talk just follows what section is this |

## Prompt Persona Mix

| persona | count |
| --- | ---: |
| elderly | 10 |
| migrant_labour | 10 |
| prisoner_undertrial | 10 |
| procedural | 10 |
| rural_dlsa | 10 |
| small_business | 10 |
| tribal_marginalized | 10 |
| urban_pro | 10 |
| women_vulnerable | 10 |
| youth_digital | 10 |

## Full 100-Prompt Comparison

| # | persona | prompt | expected Acts | Codex outcome | Codex act | Codex time | Codex route | Codex action | Claude outcome | Claude act | Claude time | Claude route |
| ---: | --- | --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | ---: | --- |
| 1 | elderly | bahu beat my mother 70 yrs filed dv case she also got named in false 498a what to do | BNS | ok | N | 20.6s | general_legal | none | ok | Y | 104.2s | unknown |
| 2 | migrant_labour | domestic worker bangalore madam not paying 3 months said i broke vase wants 8000 | Payment of Wages | REF | N | 2.6s | general_legal | none | ok | N | 68.6s | unknown |
| 3 | prisoner_undertrial | i was in jail 7 yrs acquitted now how to get compensation state legal aid | Article 21 | ok | N | 18.5s | legal_aid | legal_aid | ok | N | 81.1s | unknown |
| 4 | procedural | how to file private complaint before magistrate when police inaction | BNSS, CrPC | ok | Y | 16.8s | criminal_general | criminal_general | ok | Y | 60.9s | unknown |
| 5 | rural_dlsa | my brother mentally ill family kept him in chains how to admit in hospital legally | Mental Healthcare Act 2017 | ok | - | 19.6s | mental_health_care_rights | mental_health_care_rights | ok | - | 74.5s | unknown |
| 6 | small_business | buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck | MSMED Act 2006 s.15 + Sale of Goods Act 1930 s.41 | REF | - | 2.7s | general_legal | none | ok | - | 76.7s | unknown |
| 7 | tribal_marginalized | thana refused to file complaint against zamindar who burnt our hut latehar | BNSS, SC/ST POA Act | REF | N | 2.5s | general_legal | none | ok | Y | 71.8s | unknown |
| 8 | urban_pro | my company laptop has been seized by police as part of investigation against my colleague, what are my rights | BNSS, Information Technology Act | NO_REL | Y | 16.6s | criminal_general | criminal_general | ok | Y | 69.0s | unknown |
| 9 | women_vulnerable | office of less than 10 people no ICC sir my coworker is harassing me where do I complain | PoSH Act + Local Committee | ok | - | 20.2s | workplace_sexual_harassment | workplace_sexual_harassment | ok | - | 76.9s | unknown |
| 10 | youth_digital | got porn video featuring lookalike of me 2 lakh views not me but face same | BNS, Information Technology Act | REF | N | 2.5s | general_legal | none | partial | Y | 75.0s | unknown |
| 11 | elderly | my husband died 2024 i am 78 mutation of land in my name jharkhand process | Hindu Succession Act | REF | N | 4.2s | land_revenue_records | land_revenue_records | off_topic | N | 73.5s | unknown |
| 12 | migrant_labour | epf number lost left job hyderabad 2019 want to withdraw money 60000 stuck how | EPF Act | NO_REL | Y | 20.9s | employment_wages | employment_wages | ok | Y | 69.8s | unknown |
| 13 | prisoner_undertrial | police took my brother yesterday no arrest memo given dk basu kya hai | BNSS | ok | Y | 19.2s | criminal_general | criminal_general | ok | Y | 55.7s | unknown |
| 14 | procedural | family court summons received what is the next step before lawyer |  | REF | - | 4.1s | court_procedure | court_procedure | ok | - | 56.4s | unknown |
| 15 | rural_dlsa | forest department saying our land is reserve we have been farming since grandfather time | Forest Rights Act 2006 | NO_REL | - | 15.9s | property_tenancy | property_tenancy | ok | - | 72.0s | unknown |
| 16 | small_business | buyer cheque of 4.5 lakh bounced 2nd time what to do surat | BNSS, NI Act | ok | Y | 21.2s | cheque_bounce | cheque_bounce | ok | Y | 77.8s | unknown |
| 17 | tribal_marginalized | tehsildar transferred my baba land to bania without my consent agency area andhra | AP Scheduled Areas Land Transfer Regulation 1959 s.3 | ok | - | 29.5s | land_revenue_records | land_revenue_records | partial | - | 69.5s | unknown |
| 18 | urban_pro | i was duped of 3.5 lakh in fake stock trading app, transferred to multiple UPI ids, cyber cell complaint filed but no progress | BNS, Information Technology Act | ok | Y | 17.7s | cyber_fraud_or_harassment | cyber | ok | Y | 84.7s | unknown |
| 19 | women_vulnerable | my husband's brother has been making me uncomfortable saying things and now grabbed my hand whom to tell I cant tell husband | BNS, PWDVA | REF | N | 2.0s | general_legal | none | ok | Y | 78.3s | unknown |
| 20 | youth_digital | freelance writer 5 cheques bounced from one client total 1.4 lakh | BNSS, NI Act | partial | Y | 21.4s | cheque_bounce | cheque_bounce | ok | Y | 58.6s | unknown |
| 21 | elderly | tribunal in tamil nadu ordered son to pay 10000 per month he stopped paying enforce kaise | MWP Act 2007 s.5 s.11 | ok | - | 12.7s | general_legal | none | partial | - | 65.7s | unknown |
| 22 | migrant_labour | principal employer L&T claiming contract worker not their problem after accident pillar fell mumbai | Contract Labour Act 1970 s.21 principal employer liability + BOCW Act 1996 | ok | - | 18.3s | workplace_injury_compensation | workplace_injury_compensation | ok | - | 76.6s | unknown |
| 23 | prisoner_undertrial | brother arrested uapa 90 days over no chargesheet default bail possible | BNSS, CrPC | ok | Y | 20.8s | criminal_defence_bail | criminal_defence_bail | ok | N | 70.9s | unknown |
| 24 | procedural | how is court fee calculated for civil suit valuation 25 lakh recovery | Court Fees Act 1870 | ok | - | 20.1s | court_procedure | court_procedure | ok | - | 51.6s | unknown |
| 25 | rural_dlsa | wife and child living separately I want custody of son aged 6 | Guardians and Wards Act 1890 / Hindu Minority and Guardianship Act 1956 | ok | - | 19.4s | family_domestic | family_domestic | ok | - | 63.4s | unknown |
| 26 | small_business | drug inspector picked up samples from my medical store schedule h sale without prescription jaipur | Drugs and Cosmetics Act 1940 s.18 s.27 + Schedule H Rules | ok | - | 19.1s | general_legal | none | ok | - | 81.7s | unknown |
| 27 | tribal_marginalized | thakur men forced me to drink dirty water from well saying dalit cannot touch dindori mp | SC/ST POA Act | partial | Y | 22.4s | tribal_caste_atrocity | tribal_caste_atrocity | ok | Y | 67.8s | unknown |
| 28 | urban_pro | someone is selling fake products with my brand name on amazon, multiple takedown requests ignored | Trade Marks Act 1999 | ok | - | 18.4s | trademark_ip | trademark_ip | ok | - | 73.5s | unknown |
| 29 | women_vulnerable | I am hearing impaired my employer is not providing interpreter for HR sessions and now they say I missed important update | RPwD Act sec 3 + 21 | REF | - | 1.7s | general_legal | none | ok | - | 66.4s | unknown |
| 30 | youth_digital | someone leaked my chat with therapist on twitter mental health privacy | Information Technology Act | REF | N | 2.3s | general_legal | none | ok | Y | 66.3s | unknown |
| 31 | elderly | as a daughter am i coparcener in ancestral property father died 2003 before amendment | Hindu Succession Act | ok | N | 22.6s | succession_inheritance | succession_inheritance | ok | Y | 81.1s | unknown |
| 32 | migrant_labour | contractor said go back home pandemic no return ticket money given 9 of us walked from delhi | ISMW Act 1979 s.14 s.15 returning home allowance | off_topic | - | 28.0s | labour_exploitation_discrimination | labour_exploitation_discrimination | partial | - | 75.5s | unknown |
| 33 | prisoner_undertrial | i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain | Article 21, Legal Services Authorities Act | REF | N | 2.5s | general_legal | none | NO_REL | N | 63.2s | unknown |
| 34 | procedural | how do I file consumer complaint in district consumer forum online | Consumer Protection Act | ok | Y | 20.4s | consumer | consumer | ok | Y | 50.1s | unknown |
| 35 | rural_dlsa | thakur family stopped us from entering temple we are dalit | SC/ST POA Act | ok | Y | 18.6s | tribal_caste_atrocity | tribal_caste_atrocity | ok | Y | 54.7s | unknown |
| 36 | small_business | gst officer sealed my godown without notice surat textile trader what to do | CGST Act 2017 s.67 s.83 | ok | - | 18.6s | tax_gst_compliance | tax_gst_compliance | ok | - | 70.7s | unknown |
| 37 | tribal_marginalized | patta given under FRA but forest guards still cutting our bamboo saying it is reserved bastar | FRA 2006 s.3(1)(c) MFP rights | ok | - | 22.0s | land_revenue_records | land_revenue_records | ok | - | 81.0s | unknown |
| 38 | urban_pro | my startup co founder is trying to dilute my equity using ESOP pool without my consent, i have 30 percent | Companies Act 2013 | REF | - | 2.2s | general_legal | none | ok | - | 78.8s | unknown |
| 39 | women_vulnerable | my boss keeps asking me to come for late night meetings alone and touched my back twice should I file POSH or just leave the job | PoSH Act 2013 | ok | - | 20.1s | workplace_sexual_harassment | workplace_sexual_harassment | ok | - | 87.1s | unknown |
| 40 | youth_digital | instagram comments calling me randi defamation kya kar sakti hu | BNS, Information Technology Act | partial | Y | 17.9s | cyber_fraud_or_harassment | cyber | ok | Y | 56.8s | unknown |
| 41 | elderly | fake call from sbi pension office took 2 lakh from my account 75 yr father | BNS, Information Technology Act | NO_REL | N | 15.6s | social_welfare_identity | social_welfare_identity | partial | Y | 60.4s | unknown |
| 42 | migrant_labour | construction site delhi 14 hour work no overtime contractor laughing when i ask | Payment of Wages | off_topic | N | 22.1s | workplace_injury_compensation | workplace_injury_compensation | off_topic | N | 65.3s | unknown |
| 43 | prisoner_undertrial | anticipatory bail rejected can same be filed again same court | BNSS, CrPC | ok | Y | 22.8s | criminal_defence_bail | criminal_defence_bail | ok | N | 53.9s | unknown |
| 44 | procedural | wrongfully terminated from job how to approach labour court | Industrial Disputes Act 1947 | ok | - | 15.7s | labour_exploitation_discrimination | labour_exploitation_discrimination | ok | - | 62.3s | unknown |
| 45 | rural_dlsa | my son not giving food and money I am 72 year old where to complain | Senior Citizens Act | ok | Y | 22.1s | senior_citizen | senior_citizen | partial | Y | 68.1s | unknown |
| 46 | small_business | minority shareholder oppressing me 30% holding board not allowing inspection of registers | Companies Act 2013 s.241 s.242 s.94 | ok | - | 20.3s | general_legal | none | ok | - | 74.2s | unknown |
| 47 | tribal_marginalized | nrega job card not given by panchayat 9 months pls help nuapada odisha | MGNREGA 2005 s.3 right to work + s.19 grievance | ok | - | 24.6s | labour_exploitation_discrimination | labour_exploitation_discrimination | off_topic | - | 75.4s | unknown |
| 48 | urban_pro | ola driver took longer route and charged extra fare, customer support is closing complaint without resolution | Consumer Protection Act | REF | N | 2.6s | general_legal | none | ok | Y | 58.0s | unknown |
| 49 | women_vulnerable | I want to change my gender on aadhar and 10th certificate I have not had surgery is it possible | Transgender Act 2019 sec 6/7 | ok | - | 21.1s | social_welfare_identity | social_welfare_identity | ok | - | 77.3s | unknown |
| 50 | youth_digital | zomato rider here met with accident on bike no insurance from company | Motor Vehicles Act | REF | N | 2.7s | general_legal | none | ok | N | 61.1s | unknown |
| 51 | elderly | mother in delhi son refuses to pay maintenance how much can tribunal order maximum | MWP Act 2007 s.9 | partial | - | 18.4s | consumer | consumer | ok | - | 69.8s | unknown |
| 52 | migrant_labour | fake fir against me theft mobile when i asked wages thekedar now lawyer asking 25000 | BNS, BNSS | ok | Y | 22.0s | police_fir | police_fir | NO_REL | N | 66.6s | unknown |
| 53 | prisoner_undertrial | ed pmla raid summons husband can ask anticipatory bail before arrest | BNSS | ok | Y | 28.4s | pmla_ed | pmla_ed | ok | N | 52.0s | unknown |
| 54 | procedural | is pre-litigation mediation mandatory before filing commercial suit | Section 12A Commercial Courts Act / Mediation Act 2023 | ok | - | 16.7s | general_legal | none | ok | - | 62.4s | unknown |
| 55 | rural_dlsa | they arrested me for cow transport saying I am smuggling but I was taking my own buffalo to mandi | state Cattle Preservation Act / Prevention of Cruelty to Animals Act | ok | - | 26.3s | criminal_defence_bail | criminal_defence_bail | NO_REL | - | 72.3s | unknown |
| 56 | small_business | supplier delivered defective material now refusing refund 18 lakh contract | Sale of Goods Act 1930 s.16 s.59 + Indian Contract Act 1872 s.73 | partial | - | 21.3s | consumer | consumer | partial | - | 59.7s | unknown |
| 57 | tribal_marginalized | false dacoity case lodged on my brother by forest guard for collecting tendu leaves dindori | BNS | ok | N | 19.1s | tribal_caste_atrocity | tribal_caste_atrocity | ok | Y | 87.0s | unknown |
| 58 | urban_pro | i issued post dated cheques as security to my landlord, he is now misusing them after i vacated, what to do | NI Act | NO_REL | N | 16.0s | property_tenancy | property_tenancy | ok | Y | 92.5s | unknown |
| 59 | women_vulnerable | I am transwoman my landlord threw me out after he found out he kept my deposit also where do I complain | Transgender Act 2019 | ok | - | 21.3s | property_tenancy | property_tenancy | ok | - | 52.5s | unknown |
| 60 | youth_digital | got income tax notice 143(1) for 6 lakh youtube adsense income panic | Income Tax Act 1961 s.143(1) + s.44ADA presumptive taxation | REF | - | 5.3s | tax_gst_compliance | tax_gst_compliance | partial | - | 64.3s | unknown |
| 61 | elderly | mother gave land to younger son verbally now older son disputing it after 20 years | Hindu Succession Act, Transfer of Property Act | ok | Y | 20.5s | property_tenancy | property_tenancy | ok | Y | 66.3s | unknown |
| 62 | migrant_labour | cab driver mumbai uber deactivated rating low because customer racist hindi speaker | MV Aggregator Guidelines 2020 s.4 + IT Rules 2021 | REF | - | 5.0s | digital_platform_account | digital_platform_account | ok | - | 53.1s | unknown |
| 63 | prisoner_undertrial | wife mulaqat denied prison superintendent saying no list kya rule hai delhi | Delhi Prison Rules 2018 r.591-595 mulaqat + Prison Act 1894 + Francis Coralie Mullin 1981 | off_topic | - | 30.3s | prison_parole_furlough | prison_parole_furlough | off_topic | - | 62.4s | unknown |
| 64 | procedural | builder not giving possession how to file complaint with RERA authority | RERA | ok | N | 22.3s | consumer | consumer | ok | Y | 56.5s | unknown |
| 65 | rural_dlsa | I am ASHA worker not paid honorarium 6 months who can help | National Rural Health Mission guidelines | REF | - | 4.6s | labour_exploitation_discrimination | labour_exploitation_discrimination | REF | - | 47.5s | unknown |
| 66 | small_business | gstr 3b mismatch with gstr 2a officer asking reversal 4.8 lakh ITC reply ka kya likhu | CGST Act 2017 s.73 + Rule 36(4) | NO_REL | - | 17.3s | tax_gst_compliance | tax_gst_compliance | ok | - | 59.9s | unknown |
| 67 | tribal_marginalized | i am adivasi woman my IFR claim form rejected because no signature of husband bastar | FRA 2006 s.4(4) joint title + Rules r.8 woman head | NO_REL | - | 15.8s | tribal_caste_atrocity | tribal_caste_atrocity | ok | - | 65.6s | unknown |
| 68 | urban_pro | received summons from delhi consumer commission for product sold by my small business but it was actually defective from manufacturer | Consumer Protection Act | ok | Y | 21.6s | consumer | consumer | ok | Y | 68.8s | unknown |
| 69 | women_vulnerable | after I complained to ICC against my reporting manager he is now giving me bad rating and PIP saying performance issue retaliation | PoSH Act sec 19 + Vishaka | ok | - | 22.7s | workplace_sexual_harassment | workplace_sexual_harassment | ok | - | 87.7s | unknown |
| 70 | youth_digital | freelance designer 18 lakh income should i register gst or no | CGST Act 2017 s.22 threshold 20 lakh + Income Tax Act 1961 | ok | - | 19.9s | tax_gst_compliance | tax_gst_compliance | ok | - | 59.1s | unknown |
| 71 | elderly | father made will in 1998 not registered now after death sons fighting is unregistered will valid | Indian Succession Act, Registration Act | ok | Y | 22.2s | succession_inheritance | succession_inheritance | ok | Y | 78.2s | unknown |
| 72 | migrant_labour | factory deducted 800 every month for shoes uniform never given orissa worker tiruppur knitwear | Payment of Wages | REF | N | 2.4s | general_legal | none | off_topic | N | 83.3s | unknown |
| 73 | prisoner_undertrial | anticipatory bail in dowry case husband family how many days valid after grant | BNSS, CrPC | ok | Y | 20.0s | criminal_defence_bail | criminal_defence_bail | ok | Y | 59.2s | unknown |
| 74 | procedural | court fee for filing writ petition in high court fixed or ad valorem | Court Fees Act 1870 | ok | - | 16.5s | court_procedure | court_procedure | ok | - | 52.0s | unknown |
| 75 | rural_dlsa | panchayat secretary not giving me birth certificate of my child born at home | Registration of Births and Deaths Act 1969 | REF | - | 2.0s | general_legal | none | ok | - | 60.6s | unknown |
| 76 | small_business | code on wages applicable to me minimum wage notification gujarat for unskilled worker | Payment of Wages | ok | Y | 23.3s | employment_wages | employment_wages | ok | Y | 81.6s | unknown |
| 77 | tribal_marginalized | land acquired for coal block without consulting palli sabha angul odisha | PESA 1996 s.4(i) + LARR 2013 s.41(3) | NO_REL | - | 15.6s | property_tenancy | property_tenancy | ok | - | 65.9s | unknown |
| 78 | urban_pro | my father died without will, my brother is occupying entire property in delhi, what are my rights as daughter | Hindu Succession Act | ok | N | 24.0s | succession_inheritance | succession_inheritance | ok | Y | 75.8s | unknown |
| 79 | women_vulnerable | I am 6 months pregnant after rape doctor says it is too late for abortion but I cannot keep this child help | MTP Act 2021 sec 3B | ok | - | 43.8s | reproductive_rights_mtp | reproductive_rights_mtp | ok | - | 83.7s | unknown |
| 80 | youth_digital | urban company beautician 3 strike system unfair termination labour law | Code on Social Security 2020 ch.IX gig workers + Industrial Disputes Act | ok | - | 30.2s | employment_wages | employment_wages | ok | - | 59.5s | unknown |
| 81 | elderly | mutation entry not updated in patwari record father passed away 3 years ago rajasthan | RTI Act | ok | N | 23.2s | land_revenue_records | land_revenue_records | ok | N | 69.2s | unknown |
| 82 | migrant_labour | auto driver bangalore traffic police taking 500 every week no challan saying tamil license invalid | MV Act 1988 + Karnataka MV Rules | ok | - | 31.7s | criminal_general | criminal_general | ok | - | 63.3s | unknown |
| 83 | prisoner_undertrial | brother in jail 60 days completed maharashtra mcoca what is custody limit chargesheet | BNSS, CrPC | ok | Y | 21.8s | criminal_defence_bail | criminal_defence_bail | partial | N | 97.6s | unknown |
| 84 | procedural | how to file vakalatnama change of advocate during pending suit |  | ok | - | 20.4s | court_procedure | court_procedure | ok | - | 65.9s | unknown |
| 85 | rural_dlsa | my brother is 13 they got him married to 20 year old how to stop | Prohibition of Child Marriage Act 2006 | REF | - | 3.1s | general_legal | none | ok | - | 62.9s | unknown |
| 86 | small_business | my cheque issued to supplier bounced because account closed will i go to jail | NI Act | ok | Y | 21.9s | cheque_bounce | cheque_bounce | ok | Y | 64.8s | unknown |
| 87 | tribal_marginalized | company doing illegal mining on community forest land we got CFR title hazaribagh | FRA 2006 s.5 + MMDR Act 1957 + FCA 1980 | partial | - | 18.9s | tribal_caste_atrocity | tribal_caste_atrocity | ok | - | 53.2s | unknown |
| 88 | urban_pro | my neighbor is parking his car blocking my dedicated parking slot in apartment, security guard says he cant do anything | Cooperative Societies Act | REF | - | 1.6s | general_legal | none | NO_REL | - | 56.1s | unknown |
| 89 | women_vulnerable | after divorce he is saying I cannot ask for alimony because I was working before marriage too is this true | HMA sec 25 + Rajnesh judgment | NO_REL | - | 16.2s | family_domestic | family_domestic | ok | - | 69.9s | unknown |
| 90 | youth_digital | cops at delhi airport found my vape with thc oil what is the punishment | NDPS Act | REF | N | 2.1s | general_legal | none | ok | Y | 82.6s | unknown |
| 91 | elderly | father has 4 children 2 daughters wants to make will giving more to caretaker daughter valid | Indian Succession Act | NO_REL | N | 22.2s | sexual_offence_survivor | sexual_offence_survivor | ok | Y | 72.4s | unknown |
| 92 | migrant_labour | biharee called we are by site engineer pune always after wage complaint is this crime | BNS | off_topic | N | 27.5s | labour_exploitation_discrimination | labour_exploitation_discrimination | off_topic | N | 73.4s | unknown |
| 93 | prisoner_undertrial | son 17 yrs in adult jail puzhal pocso case age proof school certificate where to file | JJ Act 2015 s.9 + s.94 age determination + Pratap Singh v State Jharkhand 2005 | NO_REL | - | 16.0s | education_rights | education_rights | ok | - | 79.6s | unknown |
| 94 | procedural | procedure to file insolvency petition against company in NCLT | IBC | ok | Y | 26.9s | ibc_nclt | ibc_nclt | ok | Y | 60.7s | unknown |
| 95 | rural_dlsa | sarpanch giving common village land to his brother no panchayat meeting was held | Panchayati Raj Act / state Gram Panchayat Act | ok | - | 20.6s | property_tenancy | property_tenancy | ok | - | 67.4s | unknown |
| 96 | small_business | fssai notice mismatch in licence category for snack manufacturing renewal due how to upgrade state to central | FSSAI Act 2006 s.31 + Licensing & Registration Regulations 2011 | REF | - | 3.1s | general_legal | none | REF | - | 52.3s | unknown |
| 97 | tribal_marginalized | iron ore mine displaced our 12 villages no rehabilitation given keonjhar | LARR 2013 s.41 SC/ST + Sch II rehabilitation | off_topic | - | 18.7s | general_legal | none | off_topic | - | 59.5s | unknown |
| 98 | urban_pro | got notice from GST department for cancellation of registration because of nil returns for 6 months, my business was on pause | CGST Act section 29 | ok | - | 20.6s | tax_gst_compliance | tax_gst_compliance | ok | - | 63.9s | unknown |
| 99 | women_vulnerable | ex boyfriend follows my scooty everyday from office to home he doesn't talk just follows what section is this | BNS | REF | N | 3.1s | general_legal | none | off_topic | Y | 80.1s | unknown |
| 100 | youth_digital | instagram suspended my page 200k followers no notice can i sue meta india | Consumer Protection Act | NO_REL | N | 17.2s | digital_platform_account | digital_platform_account | ok | Y | 63.0s | unknown |
