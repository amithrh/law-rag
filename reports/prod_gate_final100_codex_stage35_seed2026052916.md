# Timed 100-question eval

Rows: 100
Input/output: `data/processed/timed_eval_final100_codex_stage35_seed2026052916.jsonl`

## Outcome

- Refused: 0/100
- Errors: 0/100
- Relevance verdicts: {'ok': 74, 'partial': 18, 'off_topic': 6, 'no_relevance': 2}
- Expected Act hit: 79/94 (84.0%)
- Expected Act cited hit: 63/94 (67.0%)
- Expected Act unscored: 2/100
- Expected procedure anchor cited coverage: 0/0 (0.0%)
- Answer quality flags: {'expected_act_not_cited': 31, 'missing_next_step_section': 1, 'suppressed_sentences': 10, 'zero_ok_legal_sentences': 8, 'dangling_next_step_header': 3, 'no_concrete_next_step': 8}
- Legal-safety gate: FAIL (1/100 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 16.1s | 19.8s | 22.8s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.1s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | 1.5s | 1.7s | 1.7s |
| single_expanded_retrieval_ms | 2.1s | 2.5s | 6.5s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.3s |
| variant_rerank_ms | 3.4s | 3.8s | 11.8s |
| retrieval_ms | 5.5s | 6.3s | 18.4s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 10.7s | 14.0s | 18.2s |
| verification_ms | 0.2s | 0.3s | 0.8s |
| relevance_ms | 0.1s | 0.3s | 0.4s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 10 |
| tribal_caste_atrocity | 7 |
| court_procedure | 6 |
| consumer | 6 |
| business_license_compliance | 4 |
| business_contract_partnership | 4 |
| senior_citizen | 4 |
| bonded_labour_rescue | 4 |
| employment_wages | 4 |
| digital_platform_account | 3 |
| prison_parole_furlough | 3 |
| labour_exploitation_discrimination | 3 |
| trademark_ip | 3 |
| police_fir | 3 |
| social_welfare_identity | 3 |
| cyber_fraud_or_harassment | 3 |
| succession_inheritance | 2 |
| workplace_sexual_harassment | 2 |
| tax_gst_compliance | 2 |
| land_revenue_records | 2 |
| property_tenancy | 2 |
| banking_credit_dispute | 2 |
| workplace_injury_compensation | 2 |
| environment_compensation | 2 |
| ibc_nclt | 1 |
| general_legal | 1 |
| legal_aid | 1 |
| street_vendor_municipal | 1 |
| surrogacy_parenthood | 1 |
| criminal_general | 1 |
| undertrial_review_release | 1 |
| cheque_bounce | 1 |
| family_domestic | 1 |
| arrest_custody_safeguard | 1 |
| reproductive_rights_mtp | 1 |
| custody_compensation | 1 |
| disability_access | 1 |
| criminal_procedure_notice | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| criminal_defence_bail | 10 |
| tribal_caste_atrocity | 7 |
| court_procedure | 6 |
| consumer | 6 |
| business_contract_partnership | 4 |
| bonded_labour_rescue | 4 |
| employment_wages | 4 |
| prison_parole_furlough | 3 |
| business_license_compliance | 3 |
| labour_exploitation_discrimination | 3 |
| trademark_ip | 3 |
| senior_citizen | 3 |
| police_fir | 3 |
| cyber | 3 |
| succession_inheritance | 2 |
| digital_platform_account | 2 |
| workplace_sexual_harassment | 2 |
| tax_gst_compliance | 2 |
| land_revenue_records | 2 |
| property_tenancy | 2 |
| banking_credit_dispute | 2 |
| workplace_injury_compensation | 2 |
| social_welfare_identity | 2 |
| ibc_nclt | 1 |
| none | 1 |
| caste_certificate_appeal | 1 |
| legal_aid | 1 |
| drug_license_compliance | 1 |
| senior_maintenance_cheque | 1 |
| street_vendor_municipal | 1 |
| surrogacy_parenthood | 1 |
| criminal_general | 1 |
| online_gambling_dispute | 1 |
| undertrial_review_release | 1 |
| cheque_bounce | 1 |
| family_domestic | 1 |
| arrest_custody_safeguard | 1 |
| tribal_project_displacement_rr | 1 |
| reproductive_rights_mtp | 1 |
| custody_compensation | 1 |
| mining_displacement_rr | 1 |
| disability_access | 1 |
| criminal_procedure_notice | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| expected_act_not_cited | 31 |
| suppressed_sentences | 10 |
| zero_ok_legal_sentences | 8 |
| no_concrete_next_step | 8 |
| dangling_next_step_header | 3 |
| missing_next_step_section | 1 |

## Legal Safety Gate

Gate: **FAIL**

| label | count |
| --- | ---: |
| wrong_forum | 1 |
| wrong_deadline | 0 |
| wrong_regime | 0 |
| dangerous_off_topic | 0 |
| unsafe_refusal | 0 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |
| wrong_forum | business_contract_partnership | msme_payment | buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck | msme_payment route did not expose a category-specific forum |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 22.8s | 4.5s | 18.2s | 0.3s | ibc_nclt | procedure to file insolvency petition against company in NCLT |
| 21.4s | 6.4s | 14.5s | 0.2s | court_procedure | summons not served through registered post what is next step |
| 21.2s | 3.5s | 17.6s | 0.2s | tax_gst_compliance | rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai |
| 20.6s | 5.5s | 14.9s | 0.3s | prison_parole_furlough | father in tihar 7 yrs ipc 302 furlough denied 4 times why what to do |
| 20.6s | 5.0s | 15.4s | 0.3s | court_procedure | what is an affidavit and how do I get one notarised for court |
| 20.4s | 5.7s | 14.4s | 0.6s | arrest_custody_safeguard | police took my brother yesterday no arrest memo given dk basu kya hai |
| 20.4s | 6.5s | 13.6s | 0.2s | environment_compensation | DM gave NOC to bauxite project bastar without gram sabha resolution how to challenge |
| 20.1s | 5.1s | 14.9s | 0.2s | custody_compensation | i was in yerwada 18 months theft case now released want compensation for delay |
| 19.9s | 5.6s | 14.1s | 0.2s | court_procedure | family court summons received what is the next step before lawyer |
| 19.8s | 7.0s | 12.4s | 0.4s | social_welfare_identity | aadhaar number showing someone else photo cannot get pension help |
| 19.7s | 5.6s | 14.0s | 0.3s | family_domestic | want to file mutual consent divorce, both me and husband agree, what is the process and ti |
| 19.2s | 5.5s | 13.3s | 0.8s | business_contract_partnership | former employee joined competitor and is using our customer list, NDA was signed how to en |
| 19.0s | 6.2s | 12.7s | 0.3s | cheque_bounce | drawer ka cheque 3 lakh ka return aaya stop payment likh ke kya kar sakte hai |
| 19.0s | 5.9s | 13.0s | 0.3s | workplace_injury_compensation | my husband lost hand in brick kiln no compensation owner saying he was careless |
| 18.9s | 6.9s | 11.7s | 0.3s | business_license_compliance | food safety officer collected sample from my kirana said adulteration delhi azadpur |

## Expected-Act Unscored

| persona | hint | route | query | reason |
| --- | --- | --- | --- | --- |
| urban_pro | Maharashtra Cooperative Societies Act | consumer | society management has put a fine of 25000 on me for keeping a pet without prior approval, | state/procedure source key unavailable or conditional |
| urban_pro | Cooperative Societies Act | consumer | my neighbor is parking his car blocking my dedicated parking slot in apartment, security g | state/procedure source key unavailable or conditional |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| urban_pro | Trade Marks Act | trademark_ip | trademark application opposed by a bigger company saying it is similar to their mark, hear | O.M.P. (COMM)/110/2022 of VIVID SOLAIRE ENERGY PRIVATE LIMITED	 Vs EVERGREEN RENEWABLES PR |
| rural_dlsa | RFCTLARR Act | property_tenancy | my land taken for highway 4 years back compensation still not received who to ask | Transfer of Property Act 1882 |
| procedural | Legal Services Authorities Act | business_license_compliance | how to approach Lok Adalat for pending traffic challan settlement | TheMotorVehiclesAct,1988 |
| small_business | BOCW Act, Shops and Establishments Act | employment_wages | maharashtra labour department raid kiya overtime register not maintained 11 workers what t | Code on Social Security 2020 |
| tribal_marginalized | Constitution, SC/ST POA Act | tribal_caste_atrocity | thakur men forced me to drink dirty water from well saying dalit cannot touch dindori mp | Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989 |
| elderly | Indian Contract Act, Transfer of Property Act | criminal_general | mother says son took her thumb impression on blank paper now produced as gift deed | BAIL APPLN./2366/2023 of PRAMOD KUMAR Vs THE STATE( NCT OF DELHI) & ANR. & ORS. |
| small_business | MSMED Act, Sale of Goods Act | business_contract_partnership | buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck | Micro, Small and Medium Enterprises Development Act 2006 |
| tribal_marginalized | Scheduled Areas Land Transfer Regulation | land_revenue_records | tehsildar transferred my baba land to bania without my consent agency area andhra | GOVERNMENT OF ANDHRA PRADESH THR. PRINCIPAL SECRETARY AND OTHERS versus PRATAP KARAN AND O |
| urban_pro | Banking Ombudsman | banking_credit_dispute | bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and th | Banking Regulation Act 1949 |
| rural_dlsa | Hindu Succession Act, Transfer of Property Act | property_tenancy | ancestral land in my dada name now uncle selling without telling us what to do | Transfer of Property Act 1882 |
| small_business | Indian Contract Act, Sale of Goods Act | consumer | supplier delivered defective material now refusing refund 18 lakh contract | Consumer Protection Act 2019 |
| rural_dlsa | IPC | police_fir | my daughter eloped with boy of other religion family threatening her with khap panchayat | Bharatiya Nagarik Suraksha Sanhita 2023 |
| tribal_marginalized | Constitution, Protection of Civil Rights Act | tribal_caste_atrocity | village headman saying my caste cannot enter temple in festival dindori what rights | Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989 |
| youth_digital | PMLA | digital_platform_account | blue trunks app froze my account showing kyc pending pe stuck 80k | Information Technology Act 2000 |
| women_vulnerable | Hindu Marriage Act, MTP Act | reproductive_rights_mtp | I had abortion 5 years back husband never knew now he found out and is threatening divorce | Medical Termination of Pregnancy Act 1971 |

## Expected-Act Cited Misses

| persona | expected | route | query | cited answer excerpt |
| --- | --- | --- | --- | --- |
| prisoner_undertrial | Prison Act | prison_parole_furlough | son in tihar can he get books from family during mulaqat prison rules | **Short answer** Prisoners can be released on furlough to maintain family and social ties [2]. However, furlough is not  |
| urban_pro | Trade Marks Act | trademark_ip | trademark application opposed by a bigger company saying it is similar to their mark, hear | **Short answer** If your trademark application is opposed due to similarity with another company’s mark, the court will  |
| elderly | PWDVA, Senior Citizens Act | senior_citizen | daughter in law beats my mother in lucknow what protection available 68 years old | **Short answer** The Senior Citizens Act source gives the parent/senior-citizen maintenance obligation route where child |
| prisoner_undertrial | BNSS, UAPA | criminal_defence_bail | brother UAPA arrested 3 months chargesheet not filed total custody can be extended 180 day | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If the chargesheet is  |
| prisoner_undertrial | Constitution, Legal Services Authorities Act | legal_aid | i am poor brother arrested can court give free lawyer nalsa kya hota hai | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If you are poor and ar |
| procedural | CrPC | court_procedure | magistrate refused to take cognizance complaint how to challenge | **Short answer** If a Magistrate refuses to take cognizance of your complaint, you may apply to a higher authority or co |
| rural_dlsa | RFCTLARR Act | property_tenancy | my land taken for highway 4 years back compensation still not received who to ask | **Short answer** The passages focus on property transfer, gifts, and stamp duties, not on compensation procedures or aut |
| migrant_labour | Prevention of Corruption Act, Street Vendors Act | street_vendor_municipal | vendor zone bhopal allotted me 2018 now hawker inspector saying pay 2000 every month other | **Short answer** If the hawker inspector is demanding payment of 2000 every month for vending in Zone Bhopal 2018, you m |
| procedural | Legal Services Authorities Act | business_license_compliance | how to approach Lok Adalat for pending traffic challan settlement | **Short answer** Lok Adalat is not mentioned in the provided passages, and none of the sections of the Motor Vehicles Ac |
| small_business | BOCW Act, Shops and Establishments Act | employment_wages | maharashtra labour department raid kiya overtime register not maintained 11 workers what t | **Short answer** If the Maharashtra Labour Department raids your workplace and finds that the overtime register is not m |
| tribal_marginalized | Constitution, SC/ST POA Act | tribal_caste_atrocity | thakur men forced me to drink dirty water from well saying dalit cannot touch dindori mp | **Short answer** Forcing a member of a Scheduled Caste to drink dirty water is an offence under Section 3(a) of the Sche |
| youth_digital | BNS, Information Technology Act, PMLA | cyber_fraud_or_harassment | guy from telegram crypto group rugpulled me 3 lakh whom to complain | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If someone from a Tele |
| elderly | Indian Contract Act, Transfer of Property Act | criminal_general | mother says son took her thumb impression on blank paper now produced as gift deed | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If a mother claims her |
| migrant_labour | Bonded Labour Act, Inter-State Migrant Workmen Act | bonded_labour_rescue | thekedar took 18000 advance from me darbhanga not letting leave bangalore site | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If a thekedar or contr |
| small_business | MSMED Act, Sale of Goods Act | business_contract_partnership | buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck | **Short answer** If the buyer withholds payment citing a quality issue without formally rejecting the goods, you may be  |
| tribal_marginalized | Scheduled Areas Land Transfer Regulation | land_revenue_records | tehsildar transferred my baba land to bania without my consent agency area andhra | **Short answer** If your land was transferred without your consent by a Tehsildar, you may have a legal claim to challen |
| urban_pro | Banking Ombudsman | banking_credit_dispute | bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and th | **Short answer** The sources I have don't cover this clearly. I won't guess. You should talk to a lawyer for your specif |
| elderly | BNS | criminal_defence_bail | my mother got named in false 498a fir by son wife she is 71 what to do | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If your mother is fals |
| rural_dlsa | Hindu Succession Act, Transfer of Property Act | property_tenancy | ancestral land in my dada name now uncle selling without telling us what to do | **Short answer** If your ancestral land was gifted to your grandfather and your uncle is selling it without your knowled |
| elderly | BNS, Information Technology Act | senior_citizen | fake call from sbi pension office took 2 lakh from my account 75 yr father | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** The Senior Citizens Ac |

## Expected Procedure Anchor Misses

| persona | procedure | route | query | missing cited anchors |
| --- | --- | --- | --- | --- |
| none | n/a | n/a | n/a | n/a |
