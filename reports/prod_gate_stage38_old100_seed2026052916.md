# Timed 100-question eval

Rows: 100
Input/output: `data/processed/timed_eval_stage38_old100_seed2026052916.jsonl`

## Outcome

- Refused: 0/100
- Errors: 0/100
- Relevance verdicts: {'ok': 80, 'off_topic': 5, 'partial': 13, 'no_relevance': 2}
- Expected Act hit: 87/94 (92.6%)
- Expected Act cited hit: 70/94 (74.5%)
- Expected Act unscored: 2/100
- Expected procedure anchor cited coverage: 0/0 (0.0%)
- Answer quality flags: {'expected_act_not_cited': 24, 'missing_next_step_section': 2, 'suppressed_sentences': 11, 'zero_ok_legal_sentences': 6, 'dangling_next_step_header': 2, 'no_concrete_next_step': 4}
- Legal-safety gate: PASS (0/100 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 16.1s | 19.9s | 24.9s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | 1.6s | 1.8s | 1.8s |
| single_expanded_retrieval_ms | 2.2s | 2.6s | 2.9s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.3s |
| variant_rerank_ms | 3.6s | 4.0s | 4.5s |
| retrieval_ms | 5.9s | 6.5s | 6.9s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 10.4s | 13.9s | 19.1s |
| verification_ms | 0.3s | 0.4s | 0.8s |
| relevance_ms | 0.1s | 0.3s | 0.4s |

## Route Distribution

| route | count |
| --- | ---: |
| criminal_defence_bail | 10 |
| tribal_caste_atrocity | 7 |
| court_procedure | 6 |
| consumer | 6 |
| business_contract_partnership | 4 |
| senior_citizen | 4 |
| bonded_labour_rescue | 4 |
| digital_platform_account | 3 |
| prison_parole_furlough | 3 |
| business_license_compliance | 3 |
| labour_exploitation_discrimination | 3 |
| trademark_ip | 3 |
| police_fir | 3 |
| social_welfare_identity | 3 |
| employment_wages | 3 |
| cyber_fraud_or_harassment | 3 |
| succession_inheritance | 2 |
| workplace_sexual_harassment | 2 |
| tax_gst_compliance | 2 |
| land_revenue_records | 2 |
| legal_aid | 2 |
| banking_credit_dispute | 2 |
| workplace_injury_compensation | 2 |
| environment_compensation | 2 |
| ibc_nclt | 1 |
| general_legal | 1 |
| land_acquisition_compensation | 1 |
| street_vendor_municipal | 1 |
| labour_compliance | 1 |
| surrogacy_parenthood | 1 |
| criminal_general | 1 |
| undertrial_review_release | 1 |
| property_tenancy | 1 |
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
| prison_parole_furlough | 3 |
| labour_exploitation_discrimination | 3 |
| trademark_ip | 3 |
| senior_citizen | 3 |
| police_fir | 3 |
| employment_wages | 3 |
| cyber | 3 |
| succession_inheritance | 2 |
| digital_platform_account | 2 |
| business_license_compliance | 2 |
| workplace_sexual_harassment | 2 |
| tax_gst_compliance | 2 |
| land_revenue_records | 2 |
| legal_aid | 2 |
| banking_credit_dispute | 2 |
| workplace_injury_compensation | 2 |
| social_welfare_identity | 2 |
| ibc_nclt | 1 |
| none | 1 |
| caste_certificate_appeal | 1 |
| land_acquisition_compensation | 1 |
| drug_license_compliance | 1 |
| senior_maintenance_cheque | 1 |
| street_vendor_municipal | 1 |
| labour_register_compliance | 1 |
| surrogacy_parenthood | 1 |
| criminal_general | 1 |
| online_gambling_dispute | 1 |
| undertrial_review_release | 1 |
| property_tenancy | 1 |
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
| expected_act_not_cited | 24 |
| suppressed_sentences | 11 |
| zero_ok_legal_sentences | 6 |
| no_concrete_next_step | 4 |
| missing_next_step_section | 2 |
| dangling_next_step_header | 2 |

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
| 24.9s | 5.5s | 19.1s | 0.4s | ibc_nclt | procedure to file insolvency petition against company in NCLT |
| 21.3s | 3.7s | 17.5s | 0.2s | tax_gst_compliance | rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai |
| 21.2s | 4.3s | 16.6s | 0.7s | prison_parole_furlough | son in tihar can he get books from family during mulaqat prison rules |
| 21.0s | 6.2s | 14.6s | 0.4s | court_procedure | family court summons received what is the next step before lawyer |
| 20.9s | 5.6s | 15.1s | 0.3s | prison_parole_furlough | father in tihar 7 yrs ipc 302 furlough denied 4 times why what to do |
| 20.8s | 6.0s | 14.5s | 0.2s | court_procedure | summons not served through registered post what is next step |
| 20.7s | 6.8s | 13.5s | 0.2s | environment_compensation | DM gave NOC to bauxite project bastar without gram sabha resolution how to challenge |
| 20.3s | 6.5s | 13.4s | 0.4s | court_procedure | how to file vakalatnama change of advocate during pending suit |
| 20.2s | 5.8s | 14.3s | 0.4s | family_domestic | want to file mutual consent divorce, both me and husband agree, what is the process and ti |
| 20.0s | 6.4s | 13.4s | 0.4s | cheque_bounce | drawer ka cheque 3 lakh ka return aaya stop payment likh ke kya kar sakte hai |
| 19.9s | 5.8s | 13.9s | 0.3s | business_contract_partnership | former employee joined competitor and is using our customer list, NDA was signed how to en |
| 19.5s | 6.1s | 13.1s | 0.4s | cyber_fraud_or_harassment | guy from telegram crypto group rugpulled me 3 lakh whom to complain |
| 19.4s | 3.9s | 15.4s | 0.4s | court_procedure | what is an affidavit and how do I get one notarised for court |
| 19.4s | 5.8s | 13.4s | 0.4s | workplace_sexual_harassment | after I complained to ICC against my reporting manager he is now giving me bad rating and  |
| 19.3s | 6.8s | 12.4s | 0.4s | social_welfare_identity | aadhaar number showing someone else photo cannot get pension help |

## Expected-Act Unscored

| persona | hint | route | query | reason |
| --- | --- | --- | --- | --- |
| urban_pro | Maharashtra Cooperative Societies Act | consumer | society management has put a fine of 25000 on me for keeping a pet without prior approval, | state/procedure source key unavailable or conditional |
| urban_pro | Cooperative Societies Act | consumer | my neighbor is parking his car blocking my dedicated parking slot in apartment, security g | state/procedure source key unavailable or conditional |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| elderly | Indian Contract Act, Transfer of Property Act | criminal_general | mother says son took her thumb impression on blank paper now produced as gift deed | BAIL APPLN./2366/2023 of PRAMOD KUMAR Vs THE STATE( NCT OF DELHI) & ANR. & ORS. |
| tribal_marginalized | Scheduled Areas Land Transfer Regulation | land_revenue_records | tehsildar transferred my baba land to bania without my consent agency area andhra | GOVERNMENT OF ANDHRA PRADESH THR. PRINCIPAL SECRETARY AND OTHERS versus PRATAP KARAN AND O |
| rural_dlsa | Hindu Succession Act, Transfer of Property Act | property_tenancy | ancestral land in my dada name now uncle selling without telling us what to do | Transfer of Property Act 1882 |
| small_business | Indian Contract Act, Sale of Goods Act | consumer | supplier delivered defective material now refusing refund 18 lakh contract | Consumer Protection Act 2019 |
| rural_dlsa | IPC | police_fir | my daughter eloped with boy of other religion family threatening her with khap panchayat | Bharatiya Nagarik Suraksha Sanhita 2023 |
| youth_digital | PMLA | digital_platform_account | blue trunks app froze my account showing kyc pending pe stuck 80k | Information Technology Act 2000 |
| women_vulnerable | Hindu Marriage Act, MTP Act | reproductive_rights_mtp | I had abortion 5 years back husband never knew now he found out and is threatening divorce | Medical Termination of Pregnancy Act 1971 |

## Expected-Act Cited Misses

| persona | expected | route | query | cited answer excerpt |
| --- | --- | --- | --- | --- |
| prisoner_undertrial | Prison Act | prison_parole_furlough | son in tihar can he get books from family during mulaqat prison rules | **Short answer** Prisoners can maintain family relations through parole or furlough, which allows them to have contact w |
| elderly | PWDVA, Senior Citizens Act | senior_citizen | daughter in law beats my mother in lucknow what protection available 68 years old | **Short answer** The Senior Citizens Act source gives the parent/senior-citizen maintenance obligation route where child |
| prisoner_undertrial | BNSS, UAPA | criminal_defence_bail | brother UAPA arrested 3 months chargesheet not filed total custody can be extended 180 day | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If the chargesheet is  |
| youth_digital | Copyright Act | trademark_ip | youtube struck my video for copyright but it was my own original song bro | **Short answer** |
| prisoner_undertrial | Constitution, Legal Services Authorities Act | legal_aid | i am poor brother arrested can court give free lawyer nalsa kya hota hai | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If you are poor and ar |
| procedural | CrPC | court_procedure | magistrate refused to take cognizance complaint how to challenge | **Short answer** If a Magistrate refuses to take cognizance of your complaint, you may request the Magistrate to examine |
| migrant_labour | Prevention of Corruption Act, Street Vendors Act | street_vendor_municipal | vendor zone bhopal allotted me 2018 now hawker inspector saying pay 2000 every month other | **Short answer** If the hawker inspector is demanding payment of 2000 every month, you may be required to pay fees for r |
| youth_digital | BNS, Information Technology Act, PMLA | cyber_fraud_or_harassment | guy from telegram crypto group rugpulled me 3 lakh whom to complain | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If someone from a Tele |
| elderly | Indian Contract Act, Transfer of Property Act | criminal_general | mother says son took her thumb impression on blank paper now produced as gift deed | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If a mother claims her |
| migrant_labour | Bonded Labour Act, Inter-State Migrant Workmen Act | bonded_labour_rescue | thekedar took 18000 advance from me darbhanga not letting leave bangalore site | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If a thekedar or contr |
| tribal_marginalized | Scheduled Areas Land Transfer Regulation | land_revenue_records | tehsildar transferred my baba land to bania without my consent agency area andhra | **Short answer** If your land was transferred without your consent by a Tehsildar, you may have a legal claim to challen |
| elderly | BNS | criminal_defence_bail | my mother got named in false 498a fir by son wife she is 71 what to do | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If your mother is fals |
| rural_dlsa | Hindu Succession Act, Transfer of Property Act | property_tenancy | ancestral land in my dada name now uncle selling without telling us what to do | **Short answer** If your ancestral land was gifted to your grandfather and your uncle is selling it without your knowled |
| youth_digital | BNS, Information Technology Act | cyber_fraud_or_harassment | bumble guy is blackmailing me threatening to send screenshots to my dad | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If the electronic mate |
| elderly | BNS, Information Technology Act | senior_citizen | fake call from sbi pension office took 2 lakh from my account 75 yr father | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** The Senior Citizens Ac |
| prisoner_undertrial | Prison Act | prison_parole_furlough | father in tihar 7 yrs ipc 302 furlough denied 4 times why what to do | **Short answer** Furlough can be denied if the authorities, such as the District Magistrate or Commissioner of Police, d |
| small_business | Indian Contract Act, Sale of Goods Act | consumer | supplier delivered defective material now refusing refund 18 lakh contract | **Short answer** If the supplier delivered defective material and refuses a refund, you can file a complaint with the Di |
| rural_dlsa | IPC | police_fir | my daughter eloped with boy of other religion family threatening her with khap panchayat | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** For this khap or honou |
| women_vulnerable | BNS | criminal_defence_bail | my wife filed false 498A and DV case to harass me how do I defend my family is also named | The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies. **Short answer** If you are in custody, |
| youth_digital | PMLA | digital_platform_account | blue trunks app froze my account showing kyc pending pe stuck 80k | **Short answer** If an app freezes your account and shows "KYC pending," you may have a consumer dispute under the Consu |

## Expected Procedure Anchor Misses

| persona | procedure | route | query | missing cited anchors |
| --- | --- | --- | --- | --- |
| none | n/a | n/a | n/a | n/a |
