# Timed 100-question eval

Rows: 100
Input/output: `data/processed/timed_eval_final100_codex_stage32_seed2026052855.jsonl`

## Outcome

- Refused: 2/100
- Errors: 0/100
- Relevance verdicts: {'ok': 80, 'off_topic': 4, 'refused': 2, 'partial': 12, 'no_relevance': 2}
- Expected Act hit: 76/95 (80.0%)
- Expected Act cited hit: 51/95 (53.7%)
- Expected Act unscored: 1/100
- Expected procedure anchor cited coverage: 0/0 (0.0%)
- Answer quality flags: {'expected_act_not_cited': 44, 'zero_ok_legal_sentences': 8, 'missing_criminal_regime_caveat': 9, 'suppressed_sentences': 11, 'no_concrete_next_step': 8, 'dangling_next_step_header': 4, 'missing_next_step_section': 1}
- Legal-safety gate: FAIL (15/100 hard fails)

## Latency

| stage | p50 | p90 | max |
| --- | ---: | ---: | ---: |
| total_ms | 16.6s | 20.1s | 39.0s |
| matter_route_ms | 0.0s | 0.0s | 0.0s |
| llm_preflight_ms | 0.0s | 0.0s | 0.0s |
| query_expand_ms | 0.0s | 0.0s | 0.0s |
| retrieval_single_query_ms | 1.4s | 1.5s | 1.6s |
| single_expanded_retrieval_ms | 2.0s | 2.4s | 2.6s |
| variant_candidate_retrieval_ms | n/a | n/a | n/a |
| required_source_pack_ms | 0.1s | 0.2s | 0.2s |
| variant_rerank_ms | 3.5s | 3.8s | 4.1s |
| retrieval_ms | 5.5s | 6.1s | 6.5s |
| prompt_build_ms | 0.0s | 0.0s | 0.0s |
| llm_stream_ms | 11.4s | 14.4s | 33.1s |
| verification_ms | 0.3s | 0.3s | 0.7s |
| relevance_ms | 0.1s | 0.1s | 0.2s |

## Route Distribution

| route | count |
| --- | ---: |
| tribal_caste_atrocity | 8 |
| cyber_fraud_or_harassment | 6 |
| police_fir | 6 |
| family_domestic | 5 |
| business_contract_partnership | 5 |
| employment_wages | 5 |
| consumer | 4 |
| general_legal | 4 |
| cheque_bounce | 4 |
| criminal_general | 4 |
| labour_exploitation_discrimination | 4 |
| criminal_defence_bail | 4 |
| social_welfare_identity | 4 |
| bonded_labour_rescue | 3 |
| property_tenancy | 3 |
| child_custody_adoption | 3 |
| court_procedure | 3 |
| tax_gst_compliance | 3 |
| business_license_compliance | 3 |
| trademark_ip | 2 |
| undertrial_review_release | 2 |
| custody_compensation | 2 |
| digital_platform_account | 2 |
| surrogacy_parenthood | 1 |
| prison_parole_furlough | 1 |
| workplace_injury_compensation | 1 |
| reproductive_rights_mtp | 1 |
| education_rights | 1 |
| disability_access | 1 |
| land_revenue_records | 1 |
| arrest_custody_safeguard | 1 |
| election_voter_rights | 1 |
| manual_scavenging_safety | 1 |
| pmla_ed | 1 |

## Action Packs

| action_pack | count |
| --- | ---: |
| tribal_caste_atrocity | 8 |
| cyber | 6 |
| police_fir | 6 |
| family_domestic | 5 |
| business_contract_partnership | 5 |
| employment_wages | 5 |
| consumer | 4 |
| none | 4 |
| cheque_bounce | 4 |
| criminal_general | 4 |
| labour_exploitation_discrimination | 4 |
| criminal_defence_bail | 4 |
| social_welfare_identity | 4 |
| bonded_labour_rescue | 3 |
| property_tenancy | 3 |
| child_custody_adoption | 3 |
| court_procedure | 3 |
| tax_gst_compliance | 3 |
| business_license_compliance | 3 |
| trademark_ip | 2 |
| undertrial_review_release | 2 |
| custody_compensation | 2 |
| digital_platform_account | 2 |
| surrogacy_parenthood | 1 |
| prison_parole_furlough | 1 |
| workplace_injury_compensation | 1 |
| reproductive_rights_mtp | 1 |
| education_rights | 1 |
| disability_access | 1 |
| land_revenue_records | 1 |
| arrest_custody_safeguard | 1 |
| election_voter_rights | 1 |
| manual_scavenging_safety | 1 |
| pmla_ed | 1 |

## Answer Quality Flags

| flag | count |
| --- | ---: |
| expected_act_not_cited | 44 |
| suppressed_sentences | 11 |
| missing_criminal_regime_caveat | 9 |
| zero_ok_legal_sentences | 8 |
| no_concrete_next_step | 8 |
| dangling_next_step_header | 4 |
| missing_next_step_section | 1 |

## Legal Safety Gate

Gate: **FAIL**

| label | count |
| --- | ---: |
| wrong_forum | 6 |
| wrong_deadline | 3 |
| wrong_regime | 8 |
| dangerous_off_topic | 0 |
| unsafe_refusal | 2 |
| dangerous_framing | 0 |

### Legal-Safety Failures

| labels | route | expected | query | reasons |
| --- | --- | --- | --- | --- |
| wrong_forum, unsafe_refusal | general_legal | juvenile_age | 16 yr boy detained adult jail 2 weeks already how to transfer observation home | answerable legal prompt produced refusal, error, or zero cited sentences; expected juvenile_age route, got general_legal |
| wrong_forum, wrong_deadline | cheque_bounce | finance | i issued post dated cheques as security to my landlord, he is now misusing them after i va | expected finance route, got cheque_bounce; deadline-sensitive prompt lacked a deadline-aware route/answer signal |
| wrong_regime | police_fir | fir_refusal | police refusing FIR caste atrocity case sub inspector saying it is small matter jharkhand | unknown-date criminal answer used BNS/BNSS/IPC/CrPC framing without saying incident date decides the regime |
| wrong_regime | undertrial_review_release | legal_aid_eligibility | i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain | unknown-date criminal answer used BNS/BNSS/IPC/CrPC framing without saying incident date decides the regime |
| wrong_forum | land_revenue_records | forest_rights | patta given under FRA but forest guards still cutting our bamboo saying it is reserved bas | expected forest_rights route, got land_revenue_records |
| wrong_regime | cyber_fraud_or_harassment | cyber_privacy | my nudes leaked on whatsapp group after breakup what section against him | unknown-date criminal answer used BNS/BNSS/IPC/CrPC framing without saying incident date decides the regime |
| wrong_regime | cyber_fraud_or_harassment | cyber_harassment | bumble guy is blackmailing me threatening to send screenshots to my dad | unknown-date criminal answer used BNS/BNSS/IPC/CrPC framing without saying incident date decides the regime |
| wrong_regime | criminal_general | false_charge | manager threatening to call police saying we are bangladeshi but we are from murshidabad w | unknown-date criminal answer used BNS/BNSS/IPC/CrPC framing without saying incident date decides the regime |
| wrong_forum | family_domestic | acid_attack_threat | my mother in law is threatening to throw acid on me if I don't get more money from my pare | expected acid_attack_threat route, got family_domestic |
| wrong_forum, wrong_deadline | cheque_bounce | elder_fraud | son gave me cheque for monthly maintenance it bounced twice can i file case | expected elder_fraud route, got cheque_bounce; deadline-sensitive prompt lacked a deadline-aware route/answer signal |
| unsafe_refusal | social_welfare_identity | education_finance | bank not giving education loan to my daughter even though we have scholarship paper | answerable legal prompt produced refusal, error, or zero cited sentences |
| wrong_forum, wrong_deadline | undertrial_review_release | interim_medical_bail | paralegal volunteer 4 women undertrials byculla pregnant where rule postpone trial bail | expected interim_medical_bail route, got undertrial_review_release; deadline-sensitive prompt lacked a deadline-aware route/answer signal |
| wrong_regime | police_fir | honour_threat | my daughter eloped with boy of other religion family threatening her with khap panchayat | unknown-date criminal answer used BNS/BNSS/IPC/CrPC framing without saying incident date decides the regime |
| wrong_regime | criminal_general | procedure | how to file private complaint before magistrate when police inaction | unknown-date criminal answer used BNS/BNSS/IPC/CrPC framing without saying incident date decides the regime |
| wrong_regime | cyber_fraud_or_harassment | cyber_harassment | tinder match wala extortion gang met in bandra hotel took my phone | unknown-date criminal answer used BNS/BNSS/IPC/CrPC framing without saying incident date decides the regime |

## Slowest Rows

| total | retrieval | llm | verify | route | query |
| ---: | ---: | ---: | ---: | --- | --- |
| 39.0s | 5.8s | 33.1s | 0.4s | reproductive_rights_mtp | I am 6 months pregnant after rape doctor says it is too late for abortion but I cannot kee |
| 24.1s | 4.9s | 19.2s | 0.2s | pmla_ed | pmla case ED filed twin condition kya hai how to argue not guilty |
| 23.8s | 6.0s | 17.7s | 0.2s | employment_wages | father epf trust delayed gratuity 18 months no interest paid hsmc bangalore |
| 23.5s | 6.3s | 17.0s | 0.3s | family_domestic | the man I am supposed to marry next month I found out hides he is HIV positive his family  |
| 22.2s | 4.8s | 17.3s | 0.3s | family_domestic | my mother in law is threatening to throw acid on me if I don't get more money from my pare |
| 22.1s | 5.5s | 16.4s | 0.3s | criminal_general | manager threatening to call police saying we are bangladeshi but we are from murshidabad w |
| 21.2s | 5.4s | 15.7s | 0.3s | consumer | telecom company charging deceased husband mobile bill 6 months tried to deactivate no resp |
| 21.0s | 6.0s | 14.8s | 0.2s | tax_gst_compliance | i forgot to file ITR for AY 2022-23 can i still file it now what is the penalty |
| 20.3s | 5.9s | 14.3s | 0.2s | tax_gst_compliance | my employer deducted TDS but did not deposit it, form 26AS not showing the amount, refund  |
| 20.1s | 6.1s | 13.8s | 0.3s | cheque_bounce | i issued post dated cheques as security to my landlord, he is now misusing them after i va |
| 20.1s | 5.8s | 14.1s | 0.2s | labour_exploitation_discrimination | garment unit jharkhand girl 15 working with us factory says she is 18 no proof |
| 20.0s | 5.5s | 14.4s | 0.3s | cyber_fraud_or_harassment | my nudes leaked on whatsapp group after breakup what section against him |
| 19.9s | 6.1s | 13.7s | 0.2s | court_procedure | respondent skipped pre litigation mediation can my commercial suit be rejected at threshol |
| 19.8s | 5.6s | 14.0s | 0.2s | land_revenue_records | patta given under FRA but forest guards still cutting our bamboo saying it is reserved bas |
| 19.8s | 6.1s | 13.6s | 0.3s | criminal_defence_bail | passport seized in mumbai airport for vape cartridge cbd legal in goa |

## Expected-Act Unscored

| persona | hint | route | query | reason |
| --- | --- | --- | --- | --- |
| prisoner_undertrial | Prem Shankar Shukla v Delhi Admin 1980 + Citizen for Democracy v State of Assam 1995 | arrest_custody_safeguard | brother in handcuffs taken to court hearing is this legal high security prisoner | state/procedure source key unavailable or conditional |

## Expected-Act Misses

| persona | expected | route | query | top source |
| --- | --- | --- | --- | --- |
| prisoner_undertrial | Juvenile Justice Act | general_legal | 16 yr boy detained adult jail 2 weeks already how to transfer observation home |  |
| small_business | Commercial Courts Act, Specific Relief Act | trademark_ip | urgent interim injunction needed competitor passing off my product packaging can i skip 12 | O.M.P. (COMM)/110/2022 of VIVID SOLAIRE ENERGY PRIVATE LIMITED	 Vs EVERGREEN RENEWABLES PR |
| procedural | Constitution | court_procedure | what is mandamus writ and when can I file against government officer | Code of Civil Procedure 1908 |
| small_business | Drugs and Cosmetics Act | general_legal | drug inspector picked up samples from my medical store schedule h sale without prescriptio | AMERY PHARMACEUTICALS AND ANR. versus STATE OF RAJASTHAN |
| youth_digital | BNS, Digital Personal Data Protection Act, Information Technology Act | cyber_fraud_or_harassment | got porn video featuring lookalike of me 2 lakh views not me but face same | Information Technology Act 2000 |
| elderly | Senior Citizens Act | family_domestic | mother in delhi son refuses to pay maintenance how much can tribunal order maximum | Protection of Women from Domestic Violence Act 2005 |
| procedural | Legal Services Authorities Act | business_license_compliance | how to approach Lok Adalat for pending traffic challan settlement | TheMotorVehiclesAct,1988 |
| tribal_marginalized | Forest Rights Act | land_revenue_records | patta given under FRA but forest guards still cutting our bamboo saying it is reserved bas | GOVERNMENT OF ANDHRA PRADESH THR. PRINCIPAL SECRETARY AND OTHERS versus PRATAP KARAN AND O |
| rural_dlsa | Births and Deaths Act | social_welfare_identity | panchayat secretary not giving me birth certificate of my child born at home | Right to Information Act 2005 |
| tribal_marginalized | Constitution, SC/ST POA Act | tribal_caste_atrocity | thakur men forced me to drink dirty water from well saying dalit cannot touch dindori mp | Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989 |
| migrant_labour | BNS, Constitution | criminal_general | manager threatening to call police saying we are bangladeshi but we are from murshidabad w | BAIL APPLN./3653/2022 of PRIYANKA Vs STATE OF NCT OF DELHI |
| migrant_labour | MV Act, Motor Vehicle Aggregator Guidelines | digital_platform_account | ola driver suspended id no reason 4000 rupees earning gone how to complaint | Information Technology Act 2000 |
| rural_dlsa | Right to Education Act | social_welfare_identity | bank not giving education loan to my daughter even though we have scholarship paper |  |
| urban_pro | Trade Marks Act | trademark_ip | trademark application opposed by a bigger company saying it is similar to their mark, hear | O.M.P. (COMM)/110/2022 of VIVID SOLAIRE ENERGY PRIVATE LIMITED	 Vs EVERGREEN RENEWABLES PR |
| women_vulnerable | Constitution | child_custody_adoption | my ex husband took our son to UK on tourist visa and is not bringing back he said permanen | Guardians and Wards Act 1890 |
| rural_dlsa | IPC | police_fir | my daughter eloped with boy of other religion family threatening her with khap panchayat | Bharatiya Nyaya Sanhita 2023 |
| youth_digital | Aadhaar Act, Information Technology Act, Telecommunications Act | social_welfare_identity | rapido rider job rejected fake aadhaar issue but my aadhaar is real bro | Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 20 |
| elderly | Senior Citizens Act, Transfer of Property Act | property_tenancy | i gifted house to son in 2015 now he is not feeding me can i take back | Transfer of Property Act 1882 |
| women_vulnerable | HIV Act, Hindu Marriage Act | family_domestic | the man I am supposed to marry next month I found out hides he is HIV positive his family  | Protection of Women from Domestic Violence Act 2005 |

## Expected-Act Cited Misses

| persona | expected | route | query | cited answer excerpt |
| --- | --- | --- | --- | --- |
| prisoner_undertrial | Juvenile Justice Act | general_legal | 16 yr boy detained adult jail 2 weeks already how to transfer observation home |  |
| small_business | Commercial Courts Act, Specific Relief Act | trademark_ip | urgent interim injunction needed competitor passing off my product packaging can i skip 12 | **Short answer** To seek an interim injunction for passing off, you do not need to rely on Section 12A of the Trade Mark |
| prisoner_undertrial | Prison Act | prison_parole_furlough | 65 yrs heart patient husband in jail furlough application uttar pradesh how to file | **Short answer** To apply for furlough for your husband, you must ensure he meets conditions like good conduct, no histo |
| tribal_marginalized | BNSS, SC/ST POA Act | police_fir | police refusing FIR caste atrocity case sub inspector saying it is small matter jharkhand | **Short answer** If the police refuse to register an FIR in a caste atrocity case, you can apply to the Magistrate under |
| youth_digital | Digital Personal Data Protection Act, Information Technology Act, Mental Healthcare Act | cyber_fraud_or_harassment | someone leaked my chat with therapist on twitter mental health privacy | **Short answer** If someone leaks your private chat with a therapist on social media, it may constitute criminal intimid |
| prisoner_undertrial | Legal Services Authorities Act | undertrial_review_release | i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain | **Short answer** If you have been an undertrial for three years and your lawyer is not attending hearings, you can apply |
| procedural | Constitution | court_procedure | what is mandamus writ and when can I file against government officer | **Short answer** However, you may file an appeal against a government officer if the case involves a substantial questio |
| small_business | Drugs and Cosmetics Act | general_legal | drug inspector picked up samples from my medical store schedule h sale without prescriptio | **Short answer** If a drug inspector collects samples from your medical store without a prescription, they must follow S |
| youth_digital | BNS, Digital Personal Data Protection Act, Information Technology Act | cyber_fraud_or_harassment | got porn video featuring lookalike of me 2 lakh views not me but face same | **Short answer** If a video featuring your lookalike is shared online without your consent and violates your privacy, yo |
| elderly | Senior Citizens Act | family_domestic | mother in delhi son refuses to pay maintenance how much can tribunal order maximum | **Short answer** There is no specific maximum limit on the amount of maintenance a tribunal can order under the Protecti |
| procedural | Legal Services Authorities Act | business_license_compliance | how to approach Lok Adalat for pending traffic challan settlement | **Short answer** There is no direct legal provision in the provided passages that explains how to approach Lok Adalat fo |
| tribal_marginalized | Forest Rights Act | land_revenue_records | patta given under FRA but forest guards still cutting our bamboo saying it is reserved bas | **Short answer** If you have been given a patta under the Forest Rights Act but forest guards are cutting your bamboo, c |
| women_vulnerable | BNS | criminal_defence_bail | my wife filed false 498A and DV case to harass me how do I defend my family is also named | **Short answer** If you are in custody, you may apply for bail, and the court may release you on bail if it finds reason |
| prisoner_undertrial | BNSS, NHRC Act | police_fir | father custodial death lockup byculla police saying suicide what is 196 procedure | **Short answer** For your father's police lockup death, the nearest Magistrate empowered to hold inquests must hold an i |
| rural_dlsa | Births and Deaths Act | social_welfare_identity | panchayat secretary not giving me birth certificate of my child born at home | **Short answer** For your child's birth certificate born at home, use RTI to ask the panchayat or registrar for the appl |
| small_business | Code of Civil Procedure, Commercial Courts Act | court_procedure | respondent skipped pre litigation mediation can my commercial suit be rejected at threshol | **Short answer** If the respondent skipped pre-litigation mediation, your commercial suit cannot be rejected at the thre |
| urban_pro | Industrial Disputes Act | employment_wages | i was terminated for poor performance without any warning or PIP, no domestic enquiry done | **Short answer** If you were terminated without a domestic enquiry or warning, the employer must prove the termination w |
| women_vulnerable | Constitution | family_domestic | I am gay and my parents are forcing me to marry a girl next month they are not listening I | **Short answer** You may be able to seek legal protection from your parents’ coercive behavior under the Protection of W |
| youth_digital | BNS, Information Technology Act | cyber_fraud_or_harassment | bumble guy is blackmailing me threatening to send screenshots to my dad | **Short answer** If someone threatens to send screenshots to your family, this may be considered criminal intimidation u |
| elderly | BNS | criminal_defence_bail | my mother got named in false 498a fir by son wife she is 71 what to do | **Short answer** If your mother is falsely named in a 498A FIR, she can seek bail if the court finds reasonable grounds  |

## Expected Procedure Anchor Misses

| persona | procedure | route | query | missing cited anchors |
| --- | --- | --- | --- | --- |
| none | n/a | n/a | n/a | n/a |
