# Fresh 100-Prompt Codex vs Claude Eval

Date: 2026-05-26
Prompt set: `data/eval_compare_20260526/fresh_user_100.jsonl`
Rows: 100 fresh user-like prompts, seed `20260526`
Full comparison row order: actual eval execution order after seeded persona-balanced selection.

## Executive Summary

Codex is the better product branch right now because it is materially faster, exposes routing/timing telemetry, emits action-pack decisions, and retrieves the expected Act more often. It is not ready to call a one-step legal solution yet: expected Act hit is still only 64.1%, median latency is just above the 20s target, and there are still legal prompts that route badly or refuse due low coverage.

Claude answered more prompts as `ok`, but that is not the same as better legal grounding. It missed the expected Act more often, had no route/action-pack/timing instrumentation, and its median wall latency was about 63s. I did not modify Claude; this is an as-is benchmark.

## Branches Tested

| system | branch | commit | worktree | API port |
| --- | --- | --- | --- | ---: |
| Codex | `codex/latency-hardening` | `f4561480f34e` | `/Users/amitmishra/worksppace-central/law-rag/.claude/worktrees/nervous-hodgkin-c617cc` | 8031 |
| Claude | `claude/nervous-hodgkin-c617cc` | `ecc095174361` | `/private/tmp/law-rag-compare-claude` | 8032 |

Both runs used the same local DB/corpus: 740,419 chunks and 26,184 documents. Port 8011 was occupied by an unrelated stock-scanner service, so isolated ports 8031/8032 were used.

## Commands Run

```bash
PYTHONPATH=. .venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8031 --workers 1
PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8031 \
  --queries-dir data/eval_compare_20260526 \
  --limit 100 \
  --seed 20260526 \
  --timeout-s 360 \
  --out data/processed/fresh100_codex_20260526.jsonl \
  --report data/processed/fresh100_codex_20260526.md
```

```bash
cd /private/tmp/law-rag-compare-claude
PYTHONPATH=. .venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8032 --workers 1
cd /Users/amitmishra/worksppace-central/law-rag/.claude/worktrees/nervous-hodgkin-c617cc
PYTHONPATH=. .venv/bin/python scripts/eval_timed_100.py \
  --api http://127.0.0.1:8032 \
  --queries-dir data/eval_compare_20260526 \
  --limit 100 \
  --seed 20260526 \
  --timeout-s 360 \
  --out data/processed/fresh100_claude_20260526.jsonl \
  --report data/processed/fresh100_claude_20260526.md
```

## Scorecard

| metric | Codex | Claude | readout |
| --- | ---: | ---: | --- |
| Rows completed | 100 | 100 | tie |
| Errors | 0 | 0 | both clean transport |
| Refused | 11 | 6 | Codex is stricter |
| Relevance `ok` | 68 | 86 | Claude answers more often |
| Relevance `partial` | 6 | 4 | low difference |
| Relevance `no_relevance`/NO_REL | 14 | 3 | Codex stricter/less complete |
| Relevance `off_topic` | 1 | 1 | both have one |
| Expected Act hit | 50/78 (64.1%) | 39/78 (50.0%) | Codex +11 hits |
| Wall latency p50 | 20.9s | 63.2s | Codex about 3.0x faster |
| Wall latency p90 | 41.0s | 74.5s | Codex faster, still above target |
| Wall latency max | 48.2s | 108.1s | Claude worst row over 108s |
| Route events | 100/100 | 0/100 | Codex debuggable, Claude opaque |
| Timing events | 100/100 | 0/100 | Codex debuggable, Claude opaque |
| Action packs | 77/100 | 0/100 | Codex has product workflow layer |

## Gate Check

| gate | target | Codex | Claude | pass? |
| --- | ---: | ---: | ---: | --- |
| Expected Act hit | >=85% | 50/78 (64.1%) | 39/78 (50.0%) | fail both |
| Median wall latency | <20s | 20.9s | 63.2s | fail both, Codex close |
| Dangerous framing | 0 | not 0 | not 0 | fail both |
| Route/action telemetry | required | 100/100 | 0/100 | Codex pass, Claude fail |

Dangerous framing here is a proxy from the eval, not a full legal safety audit. It flags legal prompts that were refused, marked off-topic/no-relevance, or routed into a visibly wrong category. Manual review is still required before shipping.

## Latency Detail

| stage | Codex p50 | Codex p90 | Codex max | Claude p50 | Claude p90 | Claude max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wall_ms | 20.9s | 41.0s | 48.2s | 63.2s | 74.5s | 108.1s |
| total_ms event | 20.9s | 41.0s | 48.2s | n/a | n/a | n/a |
| retrieval_ms event | 4.5s | 21.0s | 33.8s | n/a | n/a | n/a |
| llm_stream_ms event | 16.5s | 23.7s | 41.2s | n/a | n/a | n/a |

Codex was faster on 98/100 prompts. Claude was faster on 2/100 prompts.

## Expected Act Head-to-Head

| bucket | count | rows |
| --- | ---: | --- |
| Both hit | 32 | 5, 7, 8, 10, 11, 18, 21, 23, 33, 34, 37, 40, 42, 44, 45, 50, 52, 62, 66, 67, 69, 72, 75, 77, 81, 82, 84, 85, 90, 92, 94, 100 |
| Codex hit, Claude missed | 18 | 4, 15, 16, 31, 38, 46, 48, 53, 55, 59, 68, 70, 76, 78, 79, 86, 93, 97 |
| Claude hit, Codex missed | 7 | 9, 13, 27, 32, 43, 56, 98 |
| Both missed | 21 | 2, 12, 19, 24, 26, 28, 29, 35, 39, 41, 49, 57, 58, 60, 63, 64, 65, 74, 80, 87, 88 |

## High-Signal Findings

1. Codex wins the branch comparison for user-product readiness, but it does not pass the one-step legal solution gate yet.
2. Claude is too slow for production chat: p50 63.2s, p90 74.5s, max 108.1s.
3. Claude has zero route/timing/action-pack telemetry, so failures are hard to debug.
4. Codex still has recall gaps in Street Vendors, NREGA/wage claims, forest/community rights, senior-citizen gift cancellation, RTI/legal-aid routing, property/tenancy, and some data/privacy/business matters.
5. Codex has one severe route miss: row 32, private-photo blackmail, went to `succession_inheritance` and produced `off_topic`; Claude handled that prompt better but much slower.
6. Claude has severe high-stakes misses: row 52 atrocity FIR scored `off_topic`; row 94 rape-survivor compromise produced `NO_REL`; several default-bail/deadline matters missed expected Acts.

## Suggested Next Work For Codex Branch

1. Add deterministic source packs/rules for the missed legal categories before any model training.
2. Build hard routers for deadline-heavy procedural questions: default bail, NI Act notice timing, RTI first appeal, UAPA/NDPS extensions, Lok Adalat challenge, passport/police verification.
3. Fix the private-photo/cyber harassment route regression with explicit keyword and harm-pattern tests.
4. Reduce `general_legal` retrieval spikes by routing more categories before expansion and caching expansion/rerank work.
5. Add safety eval labels beyond relevance: dangerous off-topic, wrong forum, wrong limitation/deadline, wrong regime, and unsupported document-generation content.

## Prompt Persona Mix

| persona | count |
| --- | ---: |
| elderly | 9 |
| migrant_labour | 9 |
| off_topic | 5 |
| prisoner_undertrial | 9 |
| procedural | 9 |
| rural_dlsa | 9 |
| small_business | 10 |
| tribal_marginalized | 10 |
| urban_pro | 10 |
| women_vulnerable | 10 |
| youth_digital | 10 |

## Full 100-Prompt Comparison

| # | persona | prompt | expected Acts | Codex outcome | Codex act | Codex time | Codex route | Claude outcome | Claude act | Claude time | Claude route |
| ---: | --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |
| 1 | elderly | pension stopped because aadhaar biometric failed ration shop also refusing grain | Aadhaar Act | ok | - | 41.8s | social_welfare_identity | ok | - | 108.1s | unknown |
| 2 | migrant_labour | migrant worker injured in road accident while going to work can family claim mact | Motor Vehicles Act | ok | N | 16.6s | workplace_injury_compensation | ok | N | 66.6s | unknown |
| 3 | off_topic | best biryani recipe for weekend party |  | REF | - | 0.0s | off_topic | REF | - | 26.8s | unknown |
| 4 | prisoner_undertrial | ndps commercial quantity husband in jail 170 days no chargesheet when statutory bail | NDPS Act default bail CrPC BNSS | partial | Y | 18.7s | criminal_defence_bail | ok | N | 53.3s | unknown |
| 5 | procedural | how to file consumer complaint in district commission for fridge warranty refusal | Consumer Protection Act | ok | Y | 22.0s | consumer | ok | Y | 53.6s | unknown |
| 6 | rural_dlsa | ration card cancelled due aadhaar mismatch children not getting grains | Aadhaar Act | ok | - | 21.0s | social_welfare_identity | ok | - | 61.8s | unknown |
| 7 | small_business | client cheque bounced but drawer is private limited company whom to make accused | NI Act | ok | Y | 46.2s | cheque_bounce | ok | Y | 74.0s | unknown |
| 8 | tribal_marginalized | called by caste name in market and beaten when we complained about land | SC/ST POA Act BNS | ok | Y | 20.3s | tribal_caste_atrocity | partial | Y | 70.6s | unknown |
| 9 | urban_pro | bank recovery agents calling my office and relatives for credit card dues | BNS Consumer Protection Act | NO_REL | N | 15.8s | cyber_fraud_or_harassment | ok | Y | 62.7s | unknown |
| 10 | women_vulnerable | husband and in laws force me to bring 5 lakh after marriage and threaten divorce | PWDVA BNS | ok | Y | 20.0s | family_domestic | ok | Y | 69.5s | unknown |
| 11 | youth_digital | upi fraud 98000 after otp shared cyber helpline says complaint closed | Information Technology Act | ok | Y | 20.9s | cyber_fraud_or_harassment | ok | Y | 60.9s | unknown |
| 12 | elderly | my father gifted flat to my brother in 2022 but now brother stopped giving food can gift be cancelled | Senior Citizens Act 2007 s.23 | ok | N | 38.9s | general_legal | ok | N | 50.9s | unknown |
| 13 | migrant_labour | contractor kept my aadhaar and labour card and says cannot leave site until advance repaid | Payment of Wages Act | NO_REL | N | 18.0s | social_welfare_identity | ok | Y | 67.5s | unknown |
| 14 | off_topic | what is the weather in bangalore tomorrow |  | REF | - | 0.0s | off_topic | REF | - | 33.5s | unknown |
| 15 | prisoner_undertrial | anticipatory bail granted in 498a does it expire after few weeks | BNSS CrPC | ok | Y | 18.7s | criminal_defence_bail | ok | N | 81.7s | unknown |
| 16 | procedural | can lok adalat award be challenged later if party forced me to settle | Legal Services Authorities Act | ok | Y | 22.4s | legal_aid | ok | N | 69.9s | unknown |
| 17 | rural_dlsa | school refusing admission under ews quota saying seats full in private school | RTE Act | ok | - | 18.8s | education_rights | ok | - | 60.9s | unknown |
| 18 | small_business | nclt operational creditor demand notice format and time before section 9 | IBC | ok | Y | 25.3s | ibc_nclt | ok | Y | 68.7s | unknown |
| 19 | tribal_marginalized | forest officer stopped us collecting tendu leaves in community forest | Forest Rights Act SC/ST POA Act | ok | N | 40.9s | general_legal | ok | N | 65.0s | unknown |
| 20 | urban_pro | my employer deducted tds but form 26as does not show it | Income Tax Act | REF | - | 4.5s | tax_gst_compliance | ok | - | 75.0s | unknown |
| 21 | women_vulnerable | minor daughter touched by tuition teacher how to file pocso complaint | POCSO BNS | ok | Y | 48.2s | criminal_general | ok | Y | 66.8s | unknown |
| 22 | youth_digital | youtube channel copied my song beat and lyrics what copyright remedy | Copyright Act | ok | - | 19.4s | trademark_ip | ok | - | 58.0s | unknown |
| 23 | elderly | christian father died in kochi without will wife and two daughters how share calculate | Indian Succession Act | ok | Y | 24.2s | succession_inheritance | ok | Y | 73.2s | unknown |
| 24 | migrant_labour | vegetable cart seized by municipality without receipt can they throw my stock | Street Vendors Act | REF | N | 1.4s | street_vendor_municipal | NO_REL | N | 48.3s | unknown |
| 25 | off_topic | recommend a laptop under 60000 for gaming |  | REF | - | 33.8s | general_legal | REF | - | 30.7s | unknown |
| 26 | prisoner_undertrial | undertrial spent 3 years in jail then acquitted can he get compensation | Article 21 | NO_REL | N | 19.6s | custody_compensation | ok | N | 48.2s | unknown |
| 27 | procedural | limitation for recovery suit on friendly loan given 5 years ago | Limitation Act | ok | N | 20.3s | court_procedure | ok | Y | 49.6s | unknown |
| 28 | rural_dlsa | panchayat gave common land to sarpanch brother without gram sabha | RTI Act | partial | N | 19.6s | tribal_caste_atrocity | ok | N | 74.5s | unknown |
| 29 | small_business | buyer company not paying msme invoice 18 lakh for 90 days | IBC | REF | N | 20.8s | general_legal | ok | N | 73.5s | unknown |
| 30 | tribal_marginalized | tribal woman forest right title only in husband name can she get joint title | Forest Rights Act | partial | - | 19.4s | tribal_caste_atrocity | ok | - | 61.0s | unknown |
| 31 | urban_pro | company fired me on email without notice and salary for last month unpaid | Payment of Wages | ok | Y | 27.1s | employment_wages | ok | N | 61.1s | unknown |
| 32 | women_vulnerable | ex boyfriend has private photos and says he will send to my parents | Information Technology Act BNS | off_topic | N | 22.1s | succession_inheritance | ok | Y | 65.8s | unknown |
| 33 | youth_digital | someone made fake instagram account using my photos and asking money | Information Technology Act BNS | ok | Y | 19.6s | cyber_fraud_or_harassment | ok | Y | 57.6s | unknown |
| 34 | elderly | i am 74 widow son changed house lock and says go to old age home what legal step now | Senior Citizens Act | ok | Y | 24.9s | senior_citizen | ok | Y | 70.3s | unknown |
| 35 | migrant_labour | worked 42 days under nrega but job card mate says payment rejected what complaint | MGNREGA wages RTI Act | REF | N | 4.5s | labour_exploitation_discrimination | ok | N | 54.8s | unknown |
| 36 | off_topic | who won yesterday cricket match india pakistan |  | REF | - | 19.7s | general_legal | REF | - | 17.8s | unknown |
| 37 | prisoner_undertrial | police beat my brother in lockup and did not show arrest memo what can family do | Article 21 BNSS | NO_REL | Y | 24.7s | criminal_general | ok | Y | 55.1s | unknown |
| 38 | procedural | cheque bounce notice sent after 45 days is complaint still maintainable | NI Act | ok | Y | 45.0s | cheque_bounce | ok | N | 80.2s | unknown |
| 39 | rural_dlsa | hospital refused treatment because no aadhaar card emergency case | Aadhaar Act Article 21 | ok | N | 21.1s | social_welfare_identity | ok | N | 56.1s | unknown |
| 40 | small_business | tenant in my commercial shop not vacating after lease expired | Transfer of Property Act | ok | Y | 22.0s | property_tenancy | ok | Y | 66.5s | unknown |
| 41 | tribal_marginalized | hostel denied scheduled tribe scholarship saying certificate old format | RTI Act | NO_REL | N | 15.4s | social_welfare_identity | ok | N | 54.0s | unknown |
| 42 | urban_pro | builder asking extra maintenance before giving possession rera registered project | RERA Consumer Protection Act | ok | Y | 22.5s | consumer | ok | Y | 53.3s | unknown |
| 43 | women_vulnerable | live in partner promised marriage then took money and left can i file case | PWDVA BNS | NO_REL | N | 17.3s | business_contract_partnership | ok | Y | 65.7s | unknown |
| 44 | youth_digital | crypto telegram group promised double money now admin disappeared | Information Technology Act BNS | ok | Y | 37.3s | general_legal | partial | Y | 55.5s | unknown |
| 45 | elderly | grandmother made will but not registered bank says it is invalid is registration compulsory | Indian Succession Act 1925 | ok | Y | 21.6s | succession_inheritance | ok | Y | 68.5s | unknown |
| 46 | migrant_labour | domestic worker salary not paid for 5 months madam took phone also | Payment of Wages | ok | Y | 25.1s | employment_wages | ok | N | 64.2s | unknown |
| 47 | off_topic | write python code for quicksort in javascript style |  | REF | - | 0.0s | off_topic | REF | - | 31.8s | unknown |
| 48 | prisoner_undertrial | ed arrested my sister pmla but grounds of arrest not given in writing | PMLA BNSS Article 21 | ok | Y | 29.9s | pmla_ed | ok | N | 52.9s | unknown |
| 49 | procedural | free legal aid for woman domestic violence case how to apply in dlsa | Legal Services Authorities Act | ok | N | 19.6s | family_domestic | ok | N | 70.9s | unknown |
| 50 | rural_dlsa | husband drinks beats me and in laws demand bike what law protects me | PWDVA BNS | ok | Y | 20.0s | family_domestic | ok | Y | 67.8s | unknown |
| 51 | small_business | someone registered my restaurant brand name after i used it 8 years | Trade Marks Act | ok | - | 19.6s | trademark_ip | ok | - | 64.4s | unknown |
| 52 | tribal_marginalized | police refused atrocity fir saying caste abuse happened in private place | SC/ST POA Act BNSS | partial | Y | 17.5s | police_fir | off_topic | Y | 58.5s | unknown |
| 53 | urban_pro | passport renewal stuck because old criminal case was closed but police verification adverse | BNSS | NO_REL | Y | 39.4s | criminal_general | REF | N | 45.3s | unknown |
| 54 | women_vulnerable | doctor refusing abortion after rape saying 23 weeks too late | MTP Act | ok | - | 40.1s | reproductive_rights_mtp | ok | - | 59.4s | unknown |
| 55 | youth_digital | company leaked my phone number and medical data to marketing vendor | Information Technology Act | ok | Y | 40.7s | general_legal | ok | N | 67.4s | unknown |
| 56 | elderly | daughter wants share in ancestral house father died in 2010 brothers saying only sons get coparcenary | Hindu Succession Act | ok | N | 23.3s | succession_inheritance | ok | Y | 84.4s | unknown |
| 57 | migrant_labour | thekedar ran away without paying 3 months wages principal company says not our workers | Payment of Wages | NO_REL | N | 12.9s | workplace_injury_compensation | ok | N | 72.9s | unknown |
| 58 | prisoner_undertrial | 17 year old boy kept in adult jail in pocso case school certificate shows minor | POCSO BNSS | partial | N | 20.0s | education_rights | ok | N | 68.2s | unknown |
| 59 | procedural | police refused fir for bike theft saying come tomorrow what exact complaint process | BNSS | ok | Y | 17.7s | police_fir | ok | N | 62.0s | unknown |
| 60 | rural_dlsa | patwari asking money to correct land record name after father death | RTI Act | ok | N | 24.7s | land_revenue_records | ok | N | 65.4s | unknown |
| 61 | small_business | gst officer blocked my input tax credit in portal without hearing | CGST Act | ok | - | 19.7s | tax_gst_compliance | ok | - | 58.8s | unknown |
| 62 | tribal_marginalized | village labelled my mother witch and cut her hair what criminal sections | BNS SC/ST POA Act | ok | Y | 41.8s | general_legal | partial | Y | 65.9s | unknown |
| 63 | urban_pro | doctor gave wrong injection and patient in icu medical negligence compensation | Consumer Protection Act | REF | N | 21.3s | general_legal | ok | N | 71.8s | unknown |
| 64 | women_vulnerable | husband took my streedhan jewellery and mother in law hiding it | PWDVA BNS | NO_REL | N | 19.8s | general_legal | ok | N | 64.3s | unknown |
| 65 | youth_digital | police sent section 91 notice asking my phone for investigation do i comply | BNSS | ok | N | 20.4s | court_procedure | ok | N | 60.2s | unknown |
| 66 | elderly | senior citizen tribunal ordered son to pay maintenance but he stopped after 3 months enforcement? | Senior Citizens Act | NO_REL | Y | 18.5s | senior_citizen | ok | Y | 67.2s | unknown |
| 67 | migrant_labour | minimum wage in hotel paid 250 per day in gurgaon 12 hours shift no overtime | Payment of Wages | ok | Y | 22.4s | employment_wages | ok | Y | 73.0s | unknown |
| 68 | prisoner_undertrial | brother in jail 75 days theft case no chargesheet can we ask default bail | BNSS section 187 CrPC section 167 default bail | ok | Y | 19.4s | criminal_defence_bail | ok | N | 77.5s | unknown |
| 69 | procedural | which court to file appeal after district consumer commission order | Consumer Protection Act | ok | Y | 21.5s | consumer | ok | Y | 59.5s | unknown |
| 70 | rural_dlsa | widow pension pending two years officer says file lost what remedy | RTI Act | ok | Y | 19.9s | social_welfare_identity | ok | N | 54.9s | unknown |
| 71 | small_business | former employee using customer list after leaving and joined competitor | Indian Contract Act | ok | - | 43.0s | general_legal | ok | - | 57.3s | unknown |
| 72 | tribal_marginalized | upper caste landlord evicted dalit tenant after inter caste marriage | SC/ST POA Act Transfer of Property Act | ok | Y | 19.9s | tribal_caste_atrocity | ok | Y | 52.6s | unknown |
| 73 | urban_pro | non compete says i cannot join competitor for 2 years after resignation | Indian Contract Act | ok | - | 21.4s | business_contract_partnership | ok | - | 62.0s | unknown |
| 74 | women_vulnerable | married at 16 now 19 and husband violent can i annul child marriage | BNS PWDVA | ok | N | 38.9s | general_legal | ok | N | 55.3s | unknown |
| 75 | youth_digital | digital arrest scam caller said parcel has drugs and made me transfer money | Information Technology Act BNS | partial | Y | 19.3s | cyber_fraud_or_harassment | ok | Y | 66.5s | unknown |
| 76 | elderly | my dad signed property transfer in hospital ICU under pressure can we challenge it | Transfer of Property Act Indian Contract Act | NO_REL | Y | 17.8s | property_tenancy | ok | N | 75.0s | unknown |
| 77 | migrant_labour | factory deducts pf but epfo passbook zero for one year what to do | EPF Act | ok | Y | 44.0s | employment_wages | ok | Y | 74.9s | unknown |
| 78 | prisoner_undertrial | uapa case 92 days over no chargesheet nia asked extension what is default bail rule | CrPC BNSS Article 21 | ok | Y | 23.6s | criminal_defence_bail | ok | N | 75.8s | unknown |
| 79 | procedural | rti reply not received in 30 days what is first appeal time limit | RTI Act | ok | Y | 21.5s | rti | ok | N | 61.1s | unknown |
| 80 | rural_dlsa | neighbour blocked village pathway to my field can i file civil case | Transfer of Property Act | NO_REL | N | 37.1s | general_legal | ok | N | 71.2s | unknown |
| 81 | small_business | bank sent sarfaesi 13(2) notice for shop loan default what can i do | SARFAESI | ok | Y | 40.9s | general_legal | ok | Y | 69.1s | unknown |
| 82 | tribal_marginalized | contractor paid adivasi workers less than others for same road work | Payment of Wages SC/ST POA Act | NO_REL | Y | 13.5s | tribal_caste_atrocity | ok | Y | 55.9s | unknown |
| 83 | urban_pro | manager put me on pip after i complained to icc about sexual comments | POSH Act | ok | - | 19.6s | workplace_sexual_harassment | ok | - | 68.5s | unknown |
| 84 | women_vulnerable | husband installed tracking app on my phone without permission | Information Technology Act BNS | ok | Y | 36.8s | general_legal | ok | Y | 61.3s | unknown |
| 85 | youth_digital | instagram page with 300k followers disabled no appeal response | Information Technology Act Consumer Protection Act | ok | Y | 20.3s | cyber_fraud_or_harassment | NO_REL | Y | 47.7s | unknown |
| 86 | elderly | son gave maintenance cheque to mother but cheque bounced what case can she file | NI Act s.138 | ok | Y | 45.4s | cheque_bounce | ok | N | 73.0s | unknown |
| 87 | migrant_labour | construction site fall broke spine no bocw card contractor says you are daily wage no compensation | Motor Vehicles Act Payment of Wages | ok | N | 18.4s | workplace_injury_compensation | ok | N | 61.7s | unknown |
| 88 | prisoner_undertrial | wife wants mulaqat with husband in prison jail staff refusing without reason | Article 21 | ok | N | 19.7s | prison_parole_furlough | partial | N | 65.4s | unknown |
| 89 | procedural | how to respond to gst show cause notice alleging wrong input tax credit | CGST Act | ok | - | 20.0s | tax_gst_compliance | ok | - | 65.1s | unknown |
| 90 | rural_dlsa | caste people stopped us from drawing water from common well | SC/ST POA Act | ok | Y | 40.1s | general_legal | ok | Y | 52.5s | unknown |
| 91 | small_business | software audit notice says unlicensed copies installed by employee what risk | Copyright Act | NO_REL | - | 14.9s | trademark_ip | ok | - | 67.8s | unknown |
| 92 | tribal_marginalized | caste panchayat fined us for marrying outside tribe and threatened social boycott | BNS SC/ST POA Act | ok | Y | 40.8s | general_legal | ok | Y | 74.7s | unknown |
| 93 | urban_pro | flat landlord refuses deposit return saying normal wear and tear paint cost | Transfer of Property Act | ok | Y | 21.2s | property_tenancy | ok | N | 58.8s | unknown |
| 94 | women_vulnerable | police asking rape survivor to compromise with accused family | BNS BNSS | ok | Y | 23.6s | sexual_offence_survivor | NO_REL | Y | 61.1s | unknown |
| 95 | youth_digital | freelance client in dubai not paying invoice can indian court help | Indian Contract Act | ok | - | 43.3s | general_legal | ok | - | 63.7s | unknown |
| 96 | small_business | supplier delivered wrong grade steel can i claim damages under contract | Indian Contract Act | ok | - | 43.0s | general_legal | ok | - | 62.5s | unknown |
| 97 | tribal_marginalized | mining company started blasting without gram sabha consent in scheduled area | SC/ST POA Act | ok | Y | 18.9s | tribal_caste_atrocity | ok | N | 61.6s | unknown |
| 98 | urban_pro | health insurance rejected surgery claim saying hypertension pre existing | Consumer Protection Act | REF | N | 19.0s | general_legal | ok | Y | 50.6s | unknown |
| 99 | women_vulnerable | workplace icc has only men members is posh committee valid | POSH Act | ok | - | 22.3s | workplace_sexual_harassment | ok | - | 62.5s | unknown |
| 100 | youth_digital | deepfake nude video of school girls circulating on telegram group | POCSO Information Technology Act | ok | Y | 19.4s | cyber_fraud_or_harassment | ok | Y | 70.2s | unknown |

## Artifacts

- Prompt file: `data/eval_compare_20260526/fresh_user_100.jsonl`
- Codex raw JSONL: `data/processed/fresh100_codex_20260526.jsonl`
- Codex runner report: `data/processed/fresh100_codex_20260526.md`
- Claude raw JSONL: `data/processed/fresh100_claude_20260526.jsonl`
- Claude runner report: `data/processed/fresh100_claude_20260526.md`
- Combined report: `data/processed/fresh100_codex_vs_claude_20260526.md`

## Caveats

- Expected Act hit is computed from source/passages metadata, not a human legal review of answer text.
- Claude did not emit stage timing or matter-route SSE events, so only wall-clock timing is available for Claude.
- This is a product eval for retrieval/routing/grounding behavior, not a final legal correctness certification.
