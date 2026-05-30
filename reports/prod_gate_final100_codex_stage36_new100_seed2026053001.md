# Timed 100-question eval

Rows: 100
Input/output: `data/processed/timed_eval_final100_codex_stage36_new100_seed2026053001.jsonl`

## Outcome

- Refused: 0/100
- Errors: 0/100
- Relevance verdicts: {'partial': 21, 'ok': 70, 'no_relevance': 2, 'off_topic': 7}
- Expected Act hit: 80/99 (80.8%)
- Expected Act cited hit: 62/99 (62.6%)
- Expected Act unscored: 0/100
- Expected procedure anchor cited coverage: 0/1 (0.0%)
- Answer quality flags: {'suppressed_sentences': 10, 'zero_ok_legal_sentences': 8, 'no_concrete_next_step': 6, 'expected_act_not_cited': 37, 'dangling_next_step_header': 1, 'missing_next_step_section': 2, 'expected_procedure_anchors_not_cited': 1}
- Legal-safety gate: PASS (0/100 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 16.0s | 20.3s | 26.4s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | 1.5s | 1.7s | 1.7s |
| single_expanded_retrieval_ms | 2.1s | 2.5s | 2.9s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.1s | 0.3s |
| variant_rerank_ms | 3.5s | 3.8s | 4.1s |
| retrieval_ms | 5.6s | 6.2s | 7.0s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 10.7s | 15.7s | 20.6s |
| verification_ms | 0.2s | 0.3s | 0.6s |
| relevance_ms | 0.1s | 0.1s | 0.1s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 8 |
| cyber_fraud_or_harassment | 8 |
| court_procedure | 7 |
| social_welfare_identity | 6 |
| employment_wages | 6 |
| property_tenancy | 5 |
| police_fir | 5 |
| tribal_caste_atrocity | 4 |
| tax_gst_compliance | 4 |
| family_domestic | 4 |
| criminal_general | 3 |
| labour_exploitation_discrimination | 3 |
| digital_platform_account | 3 |
| cheque_bounce | 3 |
| street_vendor_municipal | 2 |
| family_marriage_status | 2 |
| business_contract_partnership | 2 |
| senior_citizen | 2 |
| environment_compensation | 2 |
| child_custody_adoption | 2 |
| ibc_nclt | 2 |
| consumer | 2 |
| general_legal | 2 |
| arrest_custody_safeguard | 1 |
| labour_compliance | 1 |
| trademark_ip | 1 |
| banking_credit_dispute | 1 |
| custody_compensation | 1 |
| workplace_injury_compensation | 1 |
| land_revenue_records | 1 |
| business_license_compliance | 1 |
| legal_aid | 1 |
| manual_scavenging_safety | 1 |
| succession_inheritance | 1 |
| undertrial_review_release | 1 |
| bonded_labour_rescue | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 8 |
| cyber | 8 |
| court_procedure | 7 |
| social_welfare_identity | 6 |
| property_tenancy | 5 |
| employment_wages | 5 |
| police_fir | 5 |
| tribal_caste_atrocity | 4 |
| tax_gst_compliance | 4 |
| family_domestic | 4 |
| criminal_general | 3 |
| labour_exploitation_discrimination | 3 |
| digital_platform_account | 3 |
| cheque_bounce | 3 |
| street_vendor_municipal | 2 |
| family_marriage_status | 2 |
| business_contract_partnership | 2 |
| senior_citizen | 2 |
| child_custody_adoption | 2 |
| consumer | 2 |
| none | 2 |
| arrest_custody_safeguard | 1 |
| labour_compliance | 1 |
| environment_compensation | 1 |
| trademark_ip | 1 |
| tribal_project_displacement_rr | 1 |
| banking_credit_dispute | 1 |
| custody_compensation | 1 |
| workplace_injury_compensation | 1 |
| land_revenue_records | 1 |
| ibc_nclt | 1 |
| gig_platform_worker | 1 |
| business_license_compliance | 1 |
| legal_aid | 1 |
| llp_annual_filing | 1 |
| manual_scavenging_safety | 1 |
| succession_inheritance | 1 |
| undertrial_review_release | 1 |
| bonded_labour_rescue | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| expected_act_not_cited | 37 |
| suppressed_sentences | 10 |
| zero_ok_legal_sentences | 8 |
| no_concrete_next_step | 6 |
| missing_next_step_section | 2 |
| dangling_next_step_header | 1 |
| expected_procedure_anchors_not_cited | 1 |

## Legal Safety Gate

Gate: **PASS**

| label | count |
| --- | ---: |
| wrong_forum | 0 |
| wrong_deadline | 0 |
| wrong_regime | 0 |
| dangerous_off_topic | 0 |
| unsafe_refusal | 0 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 26.4s | 5.7s | 20.6s | 0.2s | police_fir | neighbours calling me witch want to throw me out of village chaibasa what law |
| 23.5s | 6.3s | 17.0s | 0.2s | employment_wages | my employer is not depositing my PF for last 8 months, salary slip shows deduction but EPF |
| 23.1s | 6.1s | 16.9s | 0.3s | labour_compliance | esi inspector sent notice contribution short by 1.2 lakh for casual workers can i contest |
| 22.9s | 5.9s | 16.9s | 0.2s | employment_wages | father epf trust delayed gratuity 18 months no interest paid hsmc bangalore |
| 22.6s | 5.9s | 16.6s | 0.2s | family_domestic | my husband drinking everyday beating me and children where can I get protection order |
| 21.9s | 5.4s | 16.4s | 0.2s | police_fir | auto driver threw something on my face on the road my eyes are burning I went hospital the |
| 21.8s | 4.2s | 17.5s | 0.2s | land_revenue_records | pattadar passbook lost in flood how to get new one tehsildar saying come next month |
| 21.5s | 5.5s | 16.0s | 0.2s | family_marriage_status | got married 22 he is 29 family says illegal what is age legal in india |
| 20.9s | 5.8s | 15.0s | 0.2s | court_procedure | is pre-litigation mediation mandatory before filing commercial suit |
| 20.9s | 5.9s | 14.9s | 0.2s | criminal_defence_bail | 16 yr daughter arrested theft put in observation home or jail how to verify age |
| 20.2s | 5.0s | 15.1s | 0.1s | custody_compensation | i was in jail 7 yrs acquitted now how to get compensation state legal aid |
| 20.1s | 4.1s | 15.9s | 0.2s | family_marriage_status | husband took second wife without divorcing me he says muslim law allows him I am also musl |
| 20.1s | 4.4s | 15.6s | 0.3s | court_procedure | decree holder how to file execution petition Order 21 CPC |
| 20.0s | 4.5s | 15.4s | 0.4s | court_procedure | process to file 482 CrPC quashing petition in high court |
| 19.8s | 3.9s | 15.7s | 0.3s | labour_exploitation_discrimination | I am ASHA worker not paid honorarium 6 months who can help |

## Expected-Act Unscored

| persona | hint | route | query | reason |
| --- | --- | --- | --- | --- |
| none | n/a | n/a | n/a | n/a |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| rural_dlsa | State Welfare Scheme | social_welfare_identity | kanya vivah scheme money not given by government after my daughter wedding | Constitution of India |
| women_vulnerable | Information Technology Act, POCSO | cyber_fraud_or_harassment | my schoolmate is making deepfake nude videos of girls in class using AI and circulating I  | Digital Personal Data Protection Act 2023 |
| migrant_labour | Code on Wages, Inter-State Migrant Workmen Act | employment_wages | contractor took rs 30 daily for food gave gruel only deducted from wages legal or not | Code on Social Security 2020 |
| tribal_marginalized | Witch-Hunting State Acts | criminal_defence_bail | they say i am tonhi after child died in village false case filed chhattisgarh | Bharatiya Nagarik Suraksha Sanhita 2023 |
| tribal_marginalized | Environment Protection Act, RFCTLARR Act | environment_compensation | thermal plant blasting cracking our houses no compensation kalahandi | Water (Prevention and Control of Pollution) Act 1974 |
| women_vulnerable | Constitution, Guardians and Wards Act | child_custody_adoption | my husband took our 5 year old to delhi during fight and is not letting me meet how do I g | Guardians and Wards Act 1890 |
| procedural | BNSS | court_procedure | process to file 482 CrPC quashing petition in high court | Code of Civil Procedure 1908 |
| rural_dlsa | Births and Deaths Act | social_welfare_identity | panchayat secretary not giving me birth certificate of my child born at home | Right to Information Act 2005 |
| urban_pro | Banking Ombudsman | cyber_fraud_or_harassment | i clicked link in sms and gave OTP, lost 60000 from icici account, bank says my fault no r | Information Technology Act 2000 |
| migrant_labour | Code on Wages, Indian Contract Act | employment_wages | boss saying i signed paper give up wages but i dont read english kannada bangalore | Code on Social Security 2020 |
| procedural | Code of Civil Procedure | property_tenancy | judgment debtor not paying money decree how to attach property | Transfer of Property Act 1882 |
| women_vulnerable | Constitution | child_custody_adoption | my ex husband took our son to UK on tourist visa and is not bringing back he said permanen | Guardians and Wards Act 1890 |
| rural_dlsa | Record of Rights Act | land_revenue_records | pattadar passbook lost in flood how to get new one tehsildar saying come next month | Right to Information Act 2005 |
| women_vulnerable | BNS, Information Technology Act | cyber_fraud_or_harassment | he took my private pictures when we were together now we broke up and he is threatening to | Information Technology Act 2000 |
| youth_digital | Code on Wages | digital_platform_account | ola cabs deactivated me after 2 years driving in koramangala no warning | Information Technology Act 2000 |
| tribal_marginalized | BNS, SC/ST POA Act | tribal_caste_atrocity | mob attacked our pahan during sarna puja calling adivasi non hindu jharkhand | Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989 |
| women_vulnerable | IPC, Juvenile Justice Act, RPwD Act | family_domestic | I gave birth to baby with disability my in laws want me to leave the baby in hospital what | Protection of Women from Domestic Violence Act 2005 |
| elderly | Senior Citizens Act | general_legal | tribunal in tamil nadu ordered son to pay 10000 per month he stopped paying enforce kaise | MAT.APP.(F.C.)/266/2023 of SH. VIJAY PINGOLIA Vs SMT. POOJA PINGOLIA |
| prisoner_undertrial | JJ Age Determination Procedure, Juvenile Justice Act | criminal_defence_bail | 16 yr daughter arrested theft put in observation home or jail how to verify age | Juvenile Justice (Care and Protection of Children) Act 2015 |

## Expected-Act Cited Misses

| persona | expected | route | query | cited answer excerpt |
| --- | --- | --- | --- | --- |
| rural_dlsa | State Welfare Scheme | social_welfare_identity | kanya vivah scheme money not given by government after my daughter wedding | **Short answer** If the government has not provided money under the Kanya Vivah Scheme after your daughter's wedding, yo |
| women_vulnerable | Information Technology Act, POCSO | cyber_fraud_or_harassment | my schoolmate is making deepfake nude videos of girls in class using AI and circulating I  | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** For a porn/deepfake lo |
| youth_digital | Prohibition of Child Marriage Act, Special Marriage Act | family_marriage_status | got married 22 he is 29 family says illegal what is age legal in india | **Short answer** In India, the legal age for marriage is 21 for males and 18 for females under the Prohibition of Child  |
| elderly | Hindu Succession Act, Transfer of Property Act | property_tenancy | father transferred flat to son before death now daughter wants share is gift valid | **Short answer** A gift of property must be made voluntarily and without consideration, and it must be accepted during t |
| migrant_labour | Code on Wages, Inter-State Migrant Workmen Act | employment_wages | contractor took rs 30 daily for food gave gruel only deducted from wages legal or not | **Short answer** Deducting wages for providing inadequate food, such as gruel, may not be legal under the Code on Wages  |
| small_business | Code of Civil Procedure, Commercial Courts Act | court_procedure | respondent skipped pre litigation mediation can my commercial suit be rejected at threshol | **Short answer** If the respondent skipped pre-litigation mediation, your commercial suit cannot be rejected at the thre |
| tribal_marginalized | Witch-Hunting State Acts | criminal_defence_bail | they say i am tonhi after child died in village false case filed chhattisgarh | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** For a Chhattisgarh ton |
| youth_digital | BNS, Information Technology Act, Telecommunications Act | cyber_fraud_or_harassment | ex husband created fake whatsapp using my new sim number harassing my family | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If your ex-husband is  |
| prisoner_undertrial | BNSS, Constitution | arrest_custody_safeguard | papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** A person arrested with |
| small_business | ESI Act, Social Security Code | labour_compliance | esi inspector sent notice contribution short by 1.2 lakh for casual workers can i contest | **Short answer** If the ESI inspector issued a notice for unpaid contributions, you can appeal the decision if you belie |
| tribal_marginalized | Environment Protection Act, RFCTLARR Act | environment_compensation | thermal plant blasting cracking our houses no compensation kalahandi | **Short answer** If a thermal plant is causing damage to your house through blasting or cracking, you may need to seek c |
| women_vulnerable | Constitution, Guardians and Wards Act | child_custody_adoption | my husband took our 5 year old to delhi during fight and is not letting me meet how do I g | **Short answer** You can apply to the court for an order to return your child to your custody, as the court may make suc |
| youth_digital | Digital Personal Data Protection Act, Information Technology Act, Mental Healthcare Act | cyber_fraud_or_harassment | someone leaked my chat with therapist on twitter mental health privacy | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If someone leaks your  |
| elderly | Hindu Succession Act, Transfer of Property Act | property_tenancy | mother gave land to younger son verbally now older son disputing it after 20 years | **Short answer** A verbal gift of land is not valid under the Transfer of Property Act 1882, as a gift of immoveable pro |
| migrant_labour | MV Act, Motor Vehicle Aggregator Guidelines | digital_platform_account | ola driver suspended id no reason 4000 rupees earning gone how to complaint | **Short answer** An Uber/Ola driver deactivation after low ratings is a cab-aggregator driver-account grievance, so ask  |
| prisoner_undertrial | BNSS, NHRC Act | police_fir | father custodial death lockup byculla police saying suicide what is 196 procedure | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** For your father's poli |
| procedural | BNSS | court_procedure | process to file 482 CrPC quashing petition in high court | **Short answer** To file a quashing petition under Section 482 of the CrPC in a High Court, you must apply to the High C |
| rural_dlsa | Births and Deaths Act | social_welfare_identity | panchayat secretary not giving me birth certificate of my child born at home | **Short answer** For your child's birth certificate born at home, use RTI to ask the panchayat or registrar for the appl |
| urban_pro | Banking Ombudsman | cyber_fraud_or_harassment | i clicked link in sms and gave OTP, lost 60000 from icici account, bank says my fault no r | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If you clicked on a li |
| elderly | Banking Regulation Act, Consumer Protection Act | banking_credit_dispute | private cooperative bank fd of grandfather not honoured nominee facing harassment | **Short answer** The retrieved cooperative-bank source is about an agricultural cooperative bank and the Registrar of Co |

## Expected Procedure Anchor Misses

| persona | procedure | route | query | missing cited anchors |
| --- | --- | --- | --- | --- |
| prisoner_undertrial | JJ Age Determination Procedure | criminal_defence_bail | 16 yr daughter arrested theft put in observation home or jail how to verify age | jj-2015/sec-9 |
