# Stage 5 Failure Ledger

Eval: `/tmp/law_rag_20260604_stage5_eval500/out/timed_eval_stage5_human_messy_seed2026060405.jsonl`
Prompts: `/tmp/law_rag_20260604_stage5_eval500/prompts`
Failed rows: `179`

## Root-Cause Counts

| root cause | rows | critical |
| --- | ---: | ---: |
| scenario_specificity_gap | `68` | `7` |
| variant_answer_gap | `64` | `34` |
| source_or_retrieval_gap | `27` | `15` |
| answer_support_floor | `10` | `3` |
| citation_discipline_gap | `9` | `3` |
| suppressed_sentences | `1` | `0` |

## Harm Buckets

| harm bucket | rows | critical |
| --- | ---: | ---: |
| criminal_procedure_high_risk | `34` | `31` |
| labour_welfare_survival | `27` | `0` |
| other_user_quality | `27` | `5` |
| business_tax_procedure | `22` | `0` |
| family_child_safety | `16` | `4` |
| property_civil_practical | `16` | `0` |
| caste_tribal_state_harm | `15` | `13` |
| cyber_sexual_privacy_high_risk | `10` | `8` |
| banking_platform_money | `7` | `1` |
| street_vendor_local_livelihood | `5` | `0` |

## Recommended Stages

| stage | rows | critical |
| --- | ---: | ---: |
| colloquial_variant_resolver | `68` | `7` |
| variant_answer_contract | `64` | `34` |
| source_pack_or_corpus_patch | `27` | `15` |
| claim_support_and_template_rewrite | `10` | `3` |
| citation_discipline | `9` | `3` |
| manual_review | `1` | `0` |

## Top Issue x Root Cause

| issue | root cause | rows | critical |
| --- | --- | ---: | ---: |
| procedure | scenario_specificity_gap | `11` | `0` |
| business | scenario_specificity_gap | `5` | `0` |
| wage_theft | answer_support_floor | `4` | `0` |
| street_vendor_eviction | variant_answer_gap | `4` | `0` |
| inheritance | scenario_specificity_gap | `4` | `0` |
| cyber_privacy | variant_answer_gap | `4` | `4` |
| tax | scenario_specificity_gap | `3` | `0` |
| will_dispute | scenario_specificity_gap | `3` | `0` |
| employment | scenario_specificity_gap | `3` | `0` |
| epf_esi_default | scenario_specificity_gap | `3` | `0` |
| gift_deed_revoke | scenario_specificity_gap | `3` | `0` |
| anticipatory_bail | variant_answer_gap | `3` | `3` |
| shop_license | source_or_retrieval_gap | `2` | `0` |
| false_charge | variant_answer_gap | `2` | `1` |
| undertrial_overstay | variant_answer_gap | `2` | `1` |
| cyber | variant_answer_gap | `2` | `0` |
| hospital_negligence | variant_answer_gap | `2` | `0` |
| cab_aggregator | scenario_specificity_gap | `2` | `1` |
| ibc_recovery | scenario_specificity_gap | `2` | `0` |
| family | scenario_specificity_gap | `2` | `0` |
| civil | scenario_specificity_gap | `2` | `0` |
| reserved_education | scenario_specificity_gap | `2` | `0` |
| caste_atrocity | source_or_retrieval_gap | `2` | `2` |
| land_alienation | source_or_retrieval_gap | `2` | `2` |
| witch_hunting | source_or_retrieval_gap | `2` | `2` |
| false_charge | source_or_retrieval_gap | `2` | `2` |
| false_charge | answer_support_floor | `2` | `2` |
| forest_rights | variant_answer_gap | `2` | `2` |
| default_bail | variant_answer_gap | `2` | `2` |
| interim_medical_bail | variant_answer_gap | `2` | `2` |
| ndps_bail | variant_answer_gap | `2` | `2` |
| procedure | variant_answer_gap | `2` | `2` |
| regular_bail | variant_answer_gap | `2` | `2` |
| cyber_harassment | variant_answer_gap | `2` | `2` |
| caste_atrocity | scenario_specificity_gap | `2` | `2` |

## Critical Failure Samples

| root cause | bucket | issue | route | query | fix hint |
| --- | --- | --- | --- | --- | --- |
| source_or_retrieval_gap | caste_tribal_state_harm | caste_atrocity | tribal_caste_atrocity | can u tell mob attacked our pahan during sarna puja calling adivasi non hindu jharkhand what can i do | Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed. |
| source_or_retrieval_gap | caste_tribal_state_harm | caste_atrocity | tribal_caste_atrocity | can u tell girl beaten in school by teacher calling caste name principal not acting maharashtra what can i do | Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed. |
| source_or_retrieval_gap | caste_tribal_state_harm | land_alienation | tribal_caste_atrocity | can u tell tehsildar transferred my baba land to bania without my consent agency area andhra what can i do | Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed. |
| source_or_retrieval_gap | caste_tribal_state_harm | tribal_land | tribal_caste_atrocity | sir tribal land sold to non tribal by uncle without our consent is it legal where to go | Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed. |
| source_or_retrieval_gap | caste_tribal_state_harm | witch_hunting | police_fir | can u tell village ojha branded my mother daayan stripped her in public ranchi area what can i do | Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed. |
| source_or_retrieval_gap | caste_tribal_state_harm | witch_hunting | police_fir | can u tell neighbours calling me witch want to throw me out of village chaibasa what law what can i do | Confirm whether the source is absent from corpus or present-but-unreachable; patch source pack before answer prose. |
| source_or_retrieval_gap | criminal_procedure_high_risk | accused_cattle | criminal_defence_bail | sir they arrested me for cow transport saying I am smuggling but I was taking my own buffalo to mandi where to go | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| source_or_retrieval_gap | criminal_procedure_high_risk | drugs_personal_use | criminal_defence_bail | vit student caught with bhang lassi in mahabaleshwar holi is it ndps | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| source_or_retrieval_gap | criminal_procedure_high_risk | false_charge | criminal_defence_bail | can u tell they say i am tonhi after child died in village false case filed chhattisgarh what can i do | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| source_or_retrieval_gap | criminal_procedure_high_risk | false_charge | criminal_general | what to do delhi labour chowk police picking us morning saying nautanki begging not work how to stop is this legal | Confirm whether the source is absent from corpus or present-but-unreachable; patch source pack before answer prose. |
| source_or_retrieval_gap | criminal_procedure_high_risk | false_fir_elder | criminal_defence_bail | pls tell bahu beat my mother 70 yrs filed dv case she also got named in false 498a what to do need lawyer or police | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| source_or_retrieval_gap | criminal_procedure_high_risk | land_alienation | tribal_caste_atrocity | can u tell patwari changed mutation record giving my dadaji land to non tribal buyer nuapada odisha what can i do | Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed. |
| source_or_retrieval_gap | cyber_sexual_privacy_high_risk | cyber_harassment | cyber_fraud_or_harassment | deepfake of modi pm circulating my friend made it bjp it cell threatening | Add cyber-harm victim-first contract: takedown, cyber cell/FIR, evidence preservation, IT/BNS/POCSO/DPDP authority slots. |
| source_or_retrieval_gap | other_user_quality | honour_threat | police_fir | sir my daughter eloped with boy of other religion family threatening her with khap panchayat where to go | Confirm whether the source is absent from corpus or present-but-unreachable; patch source pack before answer prose. |
| source_or_retrieval_gap | other_user_quality | procedure | court_procedure | urgent how to file private complain before magistrate when police inaction how to complain | Confirm whether the source is absent from corpus or present-but-unreachable; patch source pack before answer prose. |
| answer_support_floor | criminal_procedure_high_risk | false_charge | police_fir | what to do thekedar made fake theft fir against me after i asked wages now police calling station is this legal | Add labour/welfare procedural ledger: authority, forum, documents, state/scheme caveat, escalation. |
| answer_support_floor | criminal_procedure_high_risk | false_charge | police_fir | what to do fake fir against me theft mobile when i asked wages thekedar now lawyer asking 25000 is this legal | Add labour/welfare procedural ledger: authority, forum, documents, state/scheme caveat, escalation. |
| answer_support_floor | criminal_procedure_high_risk | interim_medical_bail | criminal_defence_bail | need help, husband in arthur road tb test not done jail doctor 4 months waiting what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | caste_tribal_state_harm | caste_atrocity | police_fir | can u tell upper caste people beat my husband called us chamar FIR not registering thana khunti jharkhand what can i do | Manual review: decide whether this is a real answer gap or evaluator must-term calibration issue. |
| variant_answer_gap | caste_tribal_state_harm | forest_rights | tribal_caste_atrocity | can u tell i am adivasi woman my IFR claim form rejected because no signature of husband bastar what can i do | Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed. |
| variant_answer_gap | caste_tribal_state_harm | forest_rights | tribal_caste_atrocity | can u tell i am gond woman my husband died forest officer not giving me IFR title dindori what can i do | Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed. |
| variant_answer_gap | caste_tribal_state_harm | land_alienation | tribal_caste_atrocity | can u tell munda land grabbed by upper caste in our agency village how to get back chaibasa what can i do | Add colloquial caste/tribal/state-law resolver and source pack; state law must be verified when not indexed. |
| variant_answer_gap | criminal_procedure_high_risk | anticipatory_bail | criminal_defence_bail | need help, anticipatory bail rejected can same be filed again same court what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | anticipatory_bail | criminal_defence_bail | need help, anticipatory bail in dowry case husband family how many days valid after grant what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | anticipatory_bail | criminal_defence_bail | need help, ed pmla raid summons husband can ask anticipatory bail before arrest what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | assault_by_wife_accused | criminal_defence_bail | please help my husband had affair I caught them I slapped the woman now she is filing case on me what to do any remedy | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | default_bail | criminal_defence_bail | need help, brother in jail 60 days completed maharashtra mcoca what is custody limit chargesheet what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | default_bail | criminal_defence_bail | need help, my brother arrested 6 months ago tihar no chargesheet ipc 420 cheating case when bail what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | drugs_personal_use | criminal_defence_bail | drug dealer in goa caught with mdma in my bag he gave 200mg punishment | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | false_charge | criminal_defence_bail | can u tell they accused me of stealing chickens from upper caste house false POA case put on them godda what can i do | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | interim_medical_bail | criminal_defence_bail | need help, paralegal volunteer 4 women undertrials byculla pregnant where rule postpone trial bail what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | interim_medical_bail | criminal_defence_bail | need help, father 65 yrs tb positive in byculla women jail wife when interim bail medical grounds what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | it_act_67_accused | criminal_defence_bail | please help I shared my ex girlfriend's photo angry on whatsapp group not nude just normal selfie now she filed 67 case any remedy | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | juvenile_age | criminal_defence_bail | need help, 16 yr boy detained adult jail 2 weeks already how to transfer observation home what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | ndps_bail | criminal_defence_bail | need help, brother arrested NDPS 50 gram heroin commercial or not bail chances what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | ndps_bail | criminal_defence_bail | need help, husband ndps 200 gram heroin commercial bail rejected 3 times what option supreme court what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | procedure | criminal_defence_bail | urgent how much surety amount typically required for bail in cheque bounce case how to complain | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | procedure | criminal_defence_bail | urgent interim bail when can I apply between regular bail hearings how to complain | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | regular_bail | criminal_defence_bail | need help, my son 19 yrs first time offender 379 theft how to get bail magistrate court what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | regular_bail | criminal_defence_bail | need help, uncle bail granted but cant pay surety 50000 what to do poor family what next | Add criminal-procedure variant contract: subtype, forum, document checklist, date-regime, and cited authority for the exact bail/custody problem. |
| variant_answer_gap | criminal_procedure_high_risk | undertrial_overstay | custody_compensation | need help, son acquitted by sessions court after 4 yrs jail can sue state for compensation what next | Manual review: decide whether this is a real answer gap or evaluator must-term calibration issue. |
| variant_answer_gap | cyber_sexual_privacy_high_risk | cyber_harassment | cyber_fraud_or_harassment | tinder match wala extortion gang met in bandra hotel took my phone | Manual review: decide whether this is a real answer gap or evaluator must-term calibration issue. |
| variant_answer_gap | cyber_sexual_privacy_high_risk | cyber_privacy | cyber_fraud_or_harassment | ai csam of my classmate someone made and shared in college telegram | Add cyber-harm victim-first contract: takedown, cyber cell/FIR, evidence preservation, IT/BNS/POCSO/DPDP authority slots. |
| variant_answer_gap | cyber_sexual_privacy_high_risk | cyber_privacy | cyber_fraud_or_harassment | ex boyfriend made ai deepfake porn of me uploaded to xvideos | Add cyber-harm victim-first contract: takedown, cyber cell/FIR, evidence preservation, IT/BNS/POCSO/DPDP authority slots. |
| variant_answer_gap | cyber_sexual_privacy_high_risk | cyber_privacy | cyber_fraud_or_harassment | got porn video featuring lookalike of me 2 lakh views not me but face same | Add cyber-harm victim-first contract: takedown, cyber cell/FIR, evidence preservation, IT/BNS/POCSO/DPDP authority slots. |

## Next Use

Use this ledger as the Stage 0 source of truth before patching. A row should move from this ledger only when a focused test or eval slice proves the root cause is fixed without worsening safety, citation discipline, or latency.
