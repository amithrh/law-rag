# Stage36 Codex Benchmark: Old100 + New100

Date: 2026-05-30
Branch/worktree: `codex/latency-hardening` in `.claude/worktrees/nervous-hodgkin-c617cc`

## Verdict

**Not production-ready yet.** Stage36 is a real improvement on the known old100 regression set, especially on required Act retrieval and legal-safety hard fails. The non-overlapping new100 set still fails the product bar on required Act retrieval, cited grounding, off-topic/no-relevance rate, and p90 latency.

## Benchmark Sets

- old100: `data/eval_500`, seed `2026052916`, output `data/processed/timed_eval_final100_codex_stage36_old100_seed2026052916.jsonl`
- new100: `data/eval_benchmark_new100_seed2026053001`, seed `2026053001`, output `data/processed/timed_eval_final100_codex_stage36_new100_seed2026053001.jsonl`
- overlap: `0` prompts shared between old100 and new100
- new100 balance: 10 prompts per persona across the 10 eval personas

## Gate Summary

| metric | target | old100 | old result | new100 | new result |
| --- | --- | ---: | --- | ---: | --- |
| Legal-safety hard fails | 0 | 0 | PASS | 0 | PASS |
| Expected Act hit | >=85% | 87/94 (92.6%) | PASS | 80/99 (80.8%) | FAIL |
| Expected Act cited hit | >=85% | 70/94 (74.5%) | FAIL | 62/99 (62.6%) | FAIL |
| OK relevance only | >=85% | 77/100 (77.0%) | FAIL | 70/100 (70.0%) | FAIL |
| off_topic + no_relevance | <2% | 8/100 (8.0%) | FAIL | 9/100 (9.0%) | FAIL |
| total latency p90 | <20s | 19.1s | PASS | 20.3s | FAIL |
| total latency p50 | <20s | 16.2s | PASS | 16.0s | PASS |
| procedure anchors cited | >=85% when scored | n/a | PASS | 0/1 (0.0%) | FAIL |

## Old100 Regression Movement

Same 100 prompts, Stage35 versus Stage36:

| metric | Stage35 old100 | Stage36 old100 | movement |
| --- | ---: | ---: | ---: |
| OK relevance | 74/100 (74.0%) | 77/100 (77.0%) | +3 OK rows |
| partial | 18 | 15 | -3 |
| off_topic + no_relevance | 8 | 8 | +0 |
| Expected Act hit | 79/94 (84.0%) | 87/94 (92.6%) | +8 hits |
| Expected Act cited hit | 63/94 (67.0%) | 70/94 (74.5%) | +7 cited hits |
| Legal-safety hard fails | 1 | 0 | -1 |
| p90 latency | 19.8s | 19.1s | -0.7s |

## Stage36 Target Rows

| blocker prompt | route | verdict | Act hit | cited | latency |
| --- | --- | --- | ---: | ---: | ---: |
| trademark application opposed by a bigger company saying it is similar to their mark, hearing scheduled | trademark_ip | ok | True | True | 6.2s |
| my land taken for highway 4 years back compensation still not received who to ask | land_acquisition_compensation | ok | True | True | 4.8s |
| how to approach Lok Adalat for pending traffic challan settlement | legal_aid | ok | True | True | 6.3s |
| maharashtra labour department raid kiya overtime register not maintained 11 workers what to do | labour_compliance | ok | True | True | 6.3s |
| thakur men forced me to drink dirty water from well saying dalit cannot touch dindori mp | tribal_caste_atrocity | ok | True | True | 6.1s |
| village headman saying my caste cannot enter temple in festival dindori what rights | tribal_caste_atrocity | ok | True | True | 5.5s |
| bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and threatening CIBIL | banking_credit_dispute | ok | True | True | 6.7s |

## Main Blockers

1. Cited grounding is still below the production bar: old100 is 74.5%, new100 is 62.6%. This is the biggest blocker because legal answers that do not cite the controlling Act/source should not ship as confident guidance.
2. New100 generalization is weak: Expected Act hit drops to 80.8%, with misses in welfare schemes, deepfake/POCSO, wage deductions, witch-hunting, environmental compensation, child custody, banking OTP fraud, Record of Rights, juvenile justice, and senior-citizen enforcement.
3. Relevance is not product-grade: old100 has 8 off/no-relevance rows and new100 has 9. Several are urgent/vulnerable categories, not harmless edge cases.
4. Latency is close but not done: old100 p90 is 19.1s, new100 p90 is 20.3s, max 26.4s. Retrieval is mostly stable; long-tail LLM rows are the problem.
5. Deterministic action packs help, but some fail framing: bonded-labour rehabilitation/release prompts are fast and sourced but still marked off-topic, which points to template quality rather than retrieval alone.

## Non-OK Rows

| set | persona | verdict | route | Act hit | cited | latency | query |
| --- | --- | --- | --- | ---: | ---: | ---: | --- |
| old100 | migrant_labour | off_topic | bonded_labour_rescue | True | True | 6.4s | bonded labour rehabilitation 200000 release certificate how to get jharkhand sdm office |
| new100 | prisoner_undertrial | off_topic | criminal_defence_bail | True | True | 5.5s | brother arrested NDPS 50 gram heroin commercial or not bail chances |
| new100 | prisoner_undertrial | off_topic | arrest_custody_safeguard | True | False | 12.4s | papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai |
| new100 | elderly | off_topic | banking_credit_dispute | True | False | 6.4s | private cooperative bank fd of grandfather not honoured nominee facing harassment |
| new100 | migrant_labour | off_topic | social_welfare_identity | True | True | 18.8s | ration card west bengal not working in chennai shop no rice for family one nation one card not happening |
| new100 | tribal_marginalized | off_topic | bonded_labour_rescue | True | True | 5.3s | release certificate not given to bonded labour rehab money pending 3 years jharkhand |
| old100 | migrant_labour | off_topic | bonded_labour_rescue | True | True | 5.1s | brick kiln owner up keeping family hostage advance 25000 cannot go home wife sick |
| old100 | youth_digital | off_topic | criminal_defence_bail | True | True | 17.0s | drug dealer in goa caught with mdma in my bag he gave 200mg punishment |
| old100 | elderly | off_topic | senior_citizen | True | False | 6.6s | fake call from sbi pension office took 2 lakh from my account 75 yr father |
| new100 | elderly | off_topic | property_tenancy | True | False | 15.3s | mother gave land to younger son verbally now older son disputing it after 20 years |
| new100 | women_vulnerable | off_topic | family_domestic | True | True | 17.1s | sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon |
| old100 | prisoner_undertrial | off_topic | prison_parole_furlough | True | False | 19.1s | son in tihar can he get books from family during mulaqat prison rules |
| old100 | tribal_marginalized | off_topic | social_welfare_identity | True | True | 7.0s | ST certificate not issued by tehsildar 8 months daughter exam form rejected jharkhand |
| old100 | migrant_labour | off_topic | bonded_labour_rescue | True | False | 6.2s | thekedar took my aadhaar original 6 months back not returning he keeping bihar workers id |

## Highest Priority Cited Misses

Limited to the first 40 cited misses after prioritizing non-OK rows and route clusters.

| set | persona | verdict | route | expected | query |
| --- | --- | --- | --- | --- | --- |
| new100 | prisoner_undertrial | off_topic | arrest_custody_safeguard | BNSS, Constitution | papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai |
| new100 | elderly | off_topic | banking_credit_dispute | Banking Regulation Act, Consumer Protection Act | private cooperative bank fd of grandfather not honoured nominee facing harassment |
| old100 | migrant_labour | off_topic | bonded_labour_rescue | Aadhaar Act, Bonded Labour Act | thekedar took my aadhaar original 6 months back not returning he keeping bihar workers id |
| new100 | women_vulnerable | partial | child_custody_adoption | Constitution, Guardians and Wards Act | my husband took our 5 year old to delhi during fight and is not letting me meet how do I get her back fast |
| new100 | women_vulnerable | no_relevance | criminal_general | ITPA | police came to spa where I work in delhi I ran away am I in trouble do I need lawyer they have my photo from cctv |
| new100 | women_vulnerable | partial | cyber_fraud_or_harassment | BNS, Information Technology Act | he took my private pictures when we were together now we broke up and he is threatening to put on telegram |
| new100 | women_vulnerable | partial | cyber_fraud_or_harassment | Information Technology Act, POCSO | my schoolmate is making deepfake nude videos of girls in class using AI and circulating I am one of them I am 15 |
| new100 | migrant_labour | partial | employment_wages | Code on Wages, Indian Contract Act | boss saying i signed paper give up wages but i dont read english kannada bangalore |
| new100 | migrant_labour | partial | labour_exploitation_discrimination | BOCW Act, BOCW Cess Act | thekedar gave 8 of us same name on register only 2 names real cheating bocw he gets cess |
| new100 | prisoner_undertrial | partial | police_fir | BNSS, NHRC Act | father custodial death lockup byculla police saying suicide what is 196 procedure |
| old100 | prisoner_undertrial | off_topic | prison_parole_furlough | Prison Act | son in tihar can he get books from family during mulaqat prison rules |
| old100 | prisoner_undertrial | partial | prison_parole_furlough | Prison Act | tihar jail mulaqat only 30 min once a week is this legal can we ask more |
| new100 | elderly | off_topic | property_tenancy | Hindu Succession Act, Transfer of Property Act | mother gave land to younger son verbally now older son disputing it after 20 years |
| old100 | elderly | partial | senior_citizen | PWDVA, Senior Citizens Act | daughter in law beats my mother in lucknow what protection available 68 years old |
| old100 | elderly | off_topic | senior_citizen | BNS, Information Technology Act | fake call from sbi pension office took 2 lakh from my account 75 yr father |
| old100 | prisoner_undertrial | ok | arrest_custody_safeguard | BNSS, Constitution | police took my brother yesterday no arrest memo given dk basu kya hai |
| old100 | migrant_labour | ok | bonded_labour_rescue | Bonded Labour Act, Inter-State Migrant Workmen Act | thekedar took 18000 advance from me darbhanga not letting leave bangalore site |
| new100 | women_vulnerable | ok | child_custody_adoption | Constitution | my ex husband took our son to UK on tourist visa and is not bringing back he said permanent now what to do |
| old100 | urban_pro | ok | consumer | Registration Act | i bought a flat in 2019, builder still hasnt registered sale deed because of pending property tax dues from his side |
| old100 | small_business | ok | consumer | Indian Contract Act, Sale of Goods Act | supplier delivered defective material now refusing refund 18 lakh contract |
| new100 | procedural | ok | court_procedure | Commercial Courts Act, Mediation Act | is pre-litigation mediation mandatory before filing commercial suit |
| old100 | procedural | ok | court_procedure | CrPC | magistrate refused to take cognizance complaint how to challenge |
| new100 | procedural | ok | court_procedure | BNSS | process to file 482 CrPC quashing petition in high court |
| new100 | small_business | ok | court_procedure | Code of Civil Procedure, Commercial Courts Act | respondent skipped pre litigation mediation can my commercial suit be rejected at threshold |
| new100 | prisoner_undertrial | ok | criminal_defence_bail | JJ Age Determination Procedure, Juvenile Justice Act | 16 yr daughter arrested theft put in observation home or jail how to verify age |
| old100 | prisoner_undertrial | ok | criminal_defence_bail | BNSS, UAPA | brother UAPA arrested 3 months chargesheet not filed total custody can be extended 180 days |
| old100 | elderly | ok | criminal_defence_bail | BNS | my mother got named in false 498a fir by son wife she is 71 what to do |
| new100 | rural_dlsa | ok | criminal_defence_bail | BNS | my wife filed 498A on whole family even my old mother how to defend |
| new100 | urban_pro | ok | criminal_defence_bail | BNS, BNSS | my wife filed false 498A case against me and my parents, can we get anticipatory bail |
| new100 | tribal_marginalized | ok | criminal_defence_bail | Witch-Hunting State Acts | they say i am tonhi after child died in village false case filed chhattisgarh |
| old100 | elderly | ok | criminal_general | Indian Contract Act, Transfer of Property Act | mother says son took her thumb impression on blank paper now produced as gift deed |
| old100 | youth_digital | ok | criminal_procedure_notice | BNSS, Information Technology Act | received summons under section 91 bnss for my deleted insta posts is it serious |
| new100 | youth_digital | ok | cyber_fraud_or_harassment | BNS, Information Technology Act, Telecommunications Act | ex husband created fake whatsapp using my new sim number harassing my family |
| old100 | youth_digital | ok | cyber_fraud_or_harassment | BNS, Information Technology Act, PMLA | guy from telegram crypto group rugpulled me 3 lakh whom to complain |
| new100 | urban_pro | ok | cyber_fraud_or_harassment | Banking Ombudsman | i clicked link in sms and gave OTP, lost 60000 from icici account, bank says my fault no refund |
| new100 | youth_digital | ok | cyber_fraud_or_harassment | Digital Personal Data Protection Act, Information Technology Act, Mental Healthcare Act | someone leaked my chat with therapist on twitter mental health privacy |
| old100 | youth_digital | ok | digital_platform_account | PMLA | blue trunks app froze my account showing kyc pending pe stuck 80k |
| new100 | youth_digital | ok | digital_platform_account | Code on Wages | ola cabs deactivated me after 2 years driving in koramangala no warning |
| new100 | migrant_labour | ok | digital_platform_account | MV Act, Motor Vehicle Aggregator Guidelines | ola driver suspended id no reason 4000 rupees earning gone how to complaint |
| new100 | migrant_labour | ok | employment_wages | Code on Wages, Inter-State Migrant Workmen Act | contractor took rs 30 daily for food gave gruel only deducted from wages legal or not |

## Full Prompt Appendix: Old100

| # | persona | verdict | route | Act hit | cited | latency | query |
| ---: | --- | --- | --- | ---: | ---: | ---: | --- |
| 1 | elderly | ok | succession_inheritance | True | True | 18.3s | parsi mother passed away in mumbai how property divided among us three sisters |
| 2 | migrant_labour | ok | digital_platform_account | True | True | 4.8s | cab driver mumbai uber deactivated rating low because customer racist hindi speaker |
| 3 | prisoner_undertrial | off_topic | prison_parole_furlough | True | False | 19.1s | son in tihar can he get books from family during mulaqat prison rules |
| 4 | procedural | ok | ibc_nclt | True | True | 23.5s | procedure to file insolvency petition against company in NCLT |
| 5 | rural_dlsa | ok | tribal_caste_atrocity | True | True | 15.4s | upper caste people beat my husband called us by caste name FIR not registered |
| 6 | small_business | ok | business_license_compliance | True | True | 17.5s | got designated officer notice for misbranding masala packet improvement notice 14 days |
| 7 | tribal_marginalized | partial | labour_exploitation_discrimination | True | True | 16.6s | nrega 28 days work done village mukhiya not paid since 6 months gadchiroli maharashtra |
| 8 | urban_pro | ok | trademark_ip | True | True | 6.2s | trademark application opposed by a bigger company saying it is similar to their mark, hearing scheduled |
| 9 | women_vulnerable | ok | workplace_sexual_harassment | True | True | 18.2s | after I complained to ICC against my reporting manager he is now giving me bad rating and PIP saying performance issue retaliation |
| 10 | youth_digital | ok | business_contract_partnership | True | True | 5.9s | fanvue payment frozen 2400 usd indian creator how to release fund |
| 11 | elderly | partial | senior_citizen | True | False | 5.5s | daughter in law beats my mother in lucknow what protection available 68 years old |
| 12 | migrant_labour | off_topic | bonded_labour_rescue | True | True | 6.4s | bonded labour rehabilitation 200000 release certificate how to get jharkhand sdm office |
| 13 | prisoner_undertrial | ok | criminal_defence_bail | True | False | 18.8s | brother UAPA arrested 3 months chargesheet not filed total custody can be extended 180 days |
| 14 | procedural | ok | general_legal | None | None | 9.3s | tribunal order against me how to appeal NCLAT format and fees |
| 15 | rural_dlsa | ok | police_fir | True | True | 15.7s | police filed false FIR against my son for theft he was at work that day what to do |
| 16 | small_business | ok | tax_gst_compliance | True | True | 16.0s | gstr 3b mismatch with gstr 2a officer asking reversal 4.8 lakh ITC reply ka kya likhu |
| 17 | tribal_marginalized | off_topic | social_welfare_identity | True | True | 7.0s | ST certificate not issued by tehsildar 8 months daughter exam form rejected jharkhand |
| 18 | urban_pro | ok | employment_wages | True | True | 18.5s | non compete clause in my employment contract for 2 years is it enforceable in india |
| 19 | women_vulnerable | ok | criminal_defence_bail | True | True | 17.1s | I shared my ex girlfriend's photo angry on whatsapp group not nude just normal selfie now she filed 67 case |
| 20 | youth_digital | ok | trademark_ip | True | True | 16.0s | youtube struck my video for copyright but it was my own original song bro |
| 21 | elderly | no_relevance | land_revenue_records | True | True | 16.3s | my husband died 2024 i am 78 mutation of land in my name jharkhand process |
| 22 | migrant_labour | partial | labour_exploitation_discrimination | True | True | 17.0s | ismw registration who does it i never heard about it 15 years in surat textile |
| 23 | prisoner_undertrial | ok | legal_aid | True | False | 13.5s | i am poor brother arrested can court give free lawyer nalsa kya hota hai |
| 24 | procedural | ok | court_procedure | True | False | 18.3s | magistrate refused to take cognizance complaint how to challenge |
| 25 | rural_dlsa | ok | land_acquisition_compensation | True | True | 4.8s | my land taken for highway 4 years back compensation still not received who to ask |
| 26 | small_business | ok | business_license_compliance | True | True | 5.2s | drug inspector picked up samples from my medical store schedule h sale without prescription jaipur |
| 27 | tribal_marginalized | partial | tribal_caste_atrocity | True | True | 16.9s | sarpanch from upper caste beat my son outside school called him untouchable name bastar |
| 28 | urban_pro | ok | consumer | None | None | 6.2s | society management has put a fine of 25000 on me for keeping a pet without prior approval, is this legal |
| 29 | women_vulnerable | ok | police_fir | True | True | 17.0s | ex boyfriend follows my scooty everyday from office to home he doesn't talk just follows what section is this |
| 30 | youth_digital | partial | criminal_defence_bail | True | True | 5.4s | cops at delhi airport found my vape with thc oil what is the punishment |
| 31 | elderly | ok | senior_citizen | True | True | 6.3s | son gave me cheque for monthly maintenance it bounced twice can i file case |
| 32 | migrant_labour | ok | street_vendor_municipal | True | False | 17.0s | vendor zone bhopal allotted me 2018 now hawker inspector saying pay 2000 every month otherwise remove |
| 33 | prisoner_undertrial | partial | prison_parole_furlough | True | False | 17.6s | tihar jail mulaqat only 30 min once a week is this legal can we ask more |
| 34 | procedural | ok | legal_aid | True | True | 6.3s | how to approach Lok Adalat for pending traffic challan settlement |
| 35 | rural_dlsa | ok | labour_exploitation_discrimination | True | True | 16.2s | MGNREGA wages of 4 months not paid sarpanch saying funds not come |
| 36 | small_business | ok | labour_compliance | True | True | 6.3s | maharashtra labour department raid kiya overtime register not maintained 11 workers what to do |
| 37 | tribal_marginalized | ok | tribal_caste_atrocity | True | True | 6.1s | thakur men forced me to drink dirty water from well saying dalit cannot touch dindori mp |
| 38 | urban_pro | ok | consumer | None | None | 6.3s | my neighbor is parking his car blocking my dedicated parking slot in apartment, security guard says he cant do anything |
| 39 | women_vulnerable | ok | surrogacy_parenthood | True | True | 16.4s | we want a baby through surrogate my wife had hysterectomy 4 years ago we are both 38 is surrogacy allowed for us |
| 40 | youth_digital | ok | cyber_fraud_or_harassment | True | False | 18.4s | guy from telegram crypto group rugpulled me 3 lakh whom to complain |
| 41 | elderly | ok | criminal_general | False | False | 15.9s | mother says son took her thumb impression on blank paper now produced as gift deed |
| 42 | migrant_labour | ok | bonded_labour_rescue | True | False | 6.6s | thekedar took 18000 advance from me darbhanga not letting leave bangalore site |
| 43 | prisoner_undertrial | partial | criminal_defence_bail | True | True | 6.7s | brother arrested ndps 5 gram personal use how is small quantity proven |
| 44 | procedural | ok | court_procedure | None | None | 19.5s | how to file vakalatnama change of advocate during pending suit |
| 45 | rural_dlsa | partial | tribal_caste_atrocity | True | True | 5.5s | thakur family stopped us from entering temple we are dalit |
| 46 | small_business | ok | business_contract_partnership | True | True | 14.2s | buyer deducting payment saying quality issue but no formal rejection given 9 lakh stuck |
| 47 | tribal_marginalized | ok | land_revenue_records | False | False | 18.6s | tehsildar transferred my baba land to bania without my consent agency area andhra |
| 48 | urban_pro | ok | banking_credit_dispute | True | True | 6.7s | bajaj finserv EMI bounced because of bank error, now they are charging 6000 penalty and threatening CIBIL |
| 49 | women_vulnerable | ok | criminal_defence_bail | True | True | 18.0s | girl I was dating filed rape case after we broke up saying I promised marriage we had relationship for 2 years |
| 50 | youth_digital | ok | digital_platform_account | True | True | 5.4s | lost 50k on dream11 like app is online rummy legal in tamil nadu |
| 51 | elderly | ok | criminal_defence_bail | True | False | 14.3s | my mother got named in false 498a fir by son wife she is 71 what to do |
| 52 | migrant_labour | partial | workplace_injury_compensation | True | True | 17.8s | morbi ceramic factory boiler burst friend dead his family bihar nothing got 6 months over |
| 53 | prisoner_undertrial | partial | undertrial_review_release | True | True | 16.6s | i am paralegal volunteer in tihar undertrial 70 yrs ipc 302 how to apply 479 BNSS review |
| 54 | procedural | ok | court_procedure | None | None | 19.1s | family court summons received what is the next step before lawyer |
| 55 | rural_dlsa | ok | property_tenancy | False | False | 17.0s | ancestral land in my dada name now uncle selling without telling us what to do |
| 56 | small_business | ok | business_contract_partnership | True | True | 16.9s | minority shareholder oppressing me 30% holding board not allowing inspection of registers |
| 57 | tribal_marginalized | ok | tribal_caste_atrocity | True | True | 6.5s | santhal land sold by my chacha to non adivasi without DC permission how to cancel dumka |
| 58 | urban_pro | partial | business_contract_partnership | True | True | 19.3s | former employee joined competitor and is using our customer list, NDA was signed how to enforce |
| 59 | women_vulnerable | ok | cyber_fraud_or_harassment | True | True | 16.6s | this guy from college made fake instagram with my photos and is messaging my friends pretending to be me |
| 60 | youth_digital | ok | cyber_fraud_or_harassment | True | True | 6.3s | bumble guy is blackmailing me threatening to send screenshots to my dad |
| 61 | elderly | off_topic | senior_citizen | True | False | 6.6s | fake call from sbi pension office took 2 lakh from my account 75 yr father |
| 62 | migrant_labour | partial | employment_wages | True | True | 7.0s | construction company retrenched 40 of us bengali workers kept the gujaratis next day same site |
| 63 | prisoner_undertrial | ok | prison_parole_furlough | True | False | 21.3s | father in tihar 7 yrs ipc 302 furlough denied 4 times why what to do |
| 64 | procedural | ok | court_procedure | True | True | 20.9s | summons not served through registered post what is next step |
| 65 | rural_dlsa | ok | workplace_injury_compensation | True | True | 18.6s | my husband lost hand in brick kiln no compensation owner saying he was careless |
| 66 | small_business | ok | consumer | False | False | 16.7s | supplier delivered defective material now refusing refund 18 lakh contract |
| 67 | tribal_marginalized | partial | tribal_caste_atrocity | True | True | 6.1s | munda land grabbed by upper caste in our agency village how to get back chaibasa |
| 68 | urban_pro | ok | employment_wages | True | True | 17.9s | i was terminated for poor performance without any warning or PIP, no domestic enquiry done either |
| 69 | women_vulnerable | ok | workplace_sexual_harassment | True | True | 17.8s | my boss keeps asking me to come for late night meetings alone and touched my back twice should I file POSH or just leave the job |
| 70 | youth_digital | ok | consumer | True | True | 16.2s | amazon sent me fake iphone instead of real one refund denied |
| 71 | elderly | ok | succession_inheritance | True | True | 14.6s | i am 70 yr widow muslim son says wife and daughter cant inherit from his father what is sunni law |
| 72 | migrant_labour | off_topic | bonded_labour_rescue | True | True | 5.1s | brick kiln owner up keeping family hostage advance 25000 cannot go home wife sick |
| 73 | prisoner_undertrial | partial | criminal_defence_bail | True | True | 4.8s | husband ndps 200 gram heroin commercial bail rejected 3 times what option supreme court |
| 74 | procedural | ok | criminal_defence_bail | True | True | 14.3s | my brother got arrested yesterday how do I apply for regular bail |
| 75 | rural_dlsa | ok | police_fir | False | False | 5.4s | my daughter eloped with boy of other religion family threatening her with khap panchayat |
| 76 | small_business | ok | cheque_bounce | True | True | 19.5s | drawer ka cheque 3 lakh ka return aaya stop payment likh ke kya kar sakte hai |
| 77 | tribal_marginalized | ok | tribal_caste_atrocity | True | True | 5.5s | village headman saying my caste cannot enter temple in festival dindori what rights |
| 78 | urban_pro | ok | family_domestic | True | True | 19.8s | want to file mutual consent divorce, both me and husband agree, what is the process and time in mumbai |
| 79 | women_vulnerable | ok | criminal_defence_bail | True | True | 16.7s | my wife filed false 498A and DV case to harass me how do I defend my family is also named |
| 80 | youth_digital | ok | digital_platform_account | False | False | 15.6s | blue trunks app froze my account showing kyc pending pe stuck 80k |
| 81 | elderly | ok | consumer | True | True | 16.4s | telecom company charging deceased husband mobile bill 6 months tried to deactivate no response |
| 82 | migrant_labour | off_topic | bonded_labour_rescue | True | False | 6.2s | thekedar took my aadhaar original 6 months back not returning he keeping bihar workers id |
| 83 | prisoner_undertrial | ok | arrest_custody_safeguard | True | False | 19.3s | police took my brother yesterday no arrest memo given dk basu kya hai |
| 84 | procedural | ok | court_procedure | True | True | 14.6s | how to apply for transfer of case from one district court to another |
| 85 | rural_dlsa | ok | social_welfare_identity | True | True | 18.7s | aadhaar number showing someone else photo cannot get pension help |
| 86 | small_business | ok | business_license_compliance | True | True | 17.5s | food safety officer collected sample from my kirana said adulteration delhi azadpur |
| 87 | tribal_marginalized | ok | environment_compensation | True | False | 19.1s | DM gave NOC to bauxite project bastar without gram sabha resolution how to challenge |
| 88 | urban_pro | ok | consumer | True | False | 18.0s | i bought a flat in 2019, builder still hasnt registered sale deed because of pending property tax dues from his side |
| 89 | women_vulnerable | ok | reproductive_rights_mtp | False | False | 16.1s | I had abortion 5 years back husband never knew now he found out and is threatening divorce can he use this against me in court |
| 90 | youth_digital | off_topic | criminal_defence_bail | True | True | 17.0s | drug dealer in goa caught with mdma in my bag he gave 200mg punishment |
| 91 | elderly | ok | senior_citizen | True | True | 6.4s | my mother is asking how to file in senior citizen tribunal in pune for monthly maintenance |
| 92 | migrant_labour | ok | social_welfare_identity | True | True | 19.8s | lost aadhaar in morbi tile factory raid how to get new one no original village papers gone |
| 93 | prisoner_undertrial | ok | custody_compensation | True | True | 18.4s | i was in yerwada 18 months theft case now released want compensation for delay |
| 94 | procedural | ok | court_procedure | None | None | 18.7s | what is an affidavit and how do I get one notarised for court |
| 95 | rural_dlsa | ok | banking_credit_dispute | True | True | 5.1s | cooperative bank seized my buffalo for crop loan default can they take livestock |
| 96 | small_business | ok | tax_gst_compliance | True | True | 19.9s | rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai |
| 97 | tribal_marginalized | partial | environment_compensation | True | True | 4.9s | iron ore mine displaced our 12 villages no rehabilitation given keonjhar |
| 98 | urban_pro | ok | trademark_ip | True | True | 15.3s | i am running youtube channel and another creator copied my entire 12 min script word to word, copyright infringement |
| 99 | women_vulnerable | ok | disability_access | True | True | 15.3s | I am hearing impaired my employer is not providing interpreter for HR sessions and now they say I missed important update |
| 100 | youth_digital | ok | criminal_procedure_notice | True | False | 16.7s | received summons under section 91 bnss for my deleted insta posts is it serious |

## Full Prompt Appendix: New100

| # | persona | verdict | route | Act hit | cited | latency | query |
| ---: | --- | --- | --- | ---: | ---: | ---: | --- |
| 1 | elderly | partial | criminal_general | True | True | 5.9s | daughter in law took my jewellery worth 12 lakh saying for safe keeping not returning agra |
| 2 | migrant_labour | partial | street_vendor_municipal | True | True | 14.6s | vegetable cart pune municipal seized everything 4500 stock my license is from labour chowk only |
| 3 | prisoner_undertrial | ok | criminal_defence_bail | True | True | 16.3s | my son 19 yrs first time offender 379 theft how to get bail magistrate court |
| 4 | procedural | no_relevance | court_procedure | None | None | 17.6s | what should I wear to court as litigant in person appearing first time |
| 5 | rural_dlsa | ok | social_welfare_identity | False | False | 19.0s | kanya vivah scheme money not given by government after my daughter wedding |
| 6 | small_business | partial | property_tenancy | True | True | 14.8s | want specific performance of land purchase deal seller backing out delhi commercial plot 1.2 cr |
| 7 | tribal_marginalized | ok | tribal_caste_atrocity | True | True | 5.9s | non tribal sahukar took my land in mortgage 15 years now refusing return jharkhand |
| 8 | urban_pro | partial | cyber_fraud_or_harassment | True | True | 18.3s | i was duped of 3.5 lakh in fake stock trading app, transferred to multiple UPI ids, cyber cell complaint filed but no progress |
| 9 | women_vulnerable | partial | cyber_fraud_or_harassment | False | False | 6.5s | my schoolmate is making deepfake nude videos of girls in class using AI and circulating I am one of them I am 15 |
| 10 | youth_digital | ok | family_marriage_status | True | False | 21.5s | got married 22 he is 29 family says illegal what is age legal in india |
| 11 | elderly | ok | property_tenancy | True | False | 15.0s | father transferred flat to son before death now daughter wants share is gift valid |
| 12 | migrant_labour | ok | employment_wages | False | False | 16.7s | contractor took rs 30 daily for food gave gruel only deducted from wages legal or not |
| 13 | prisoner_undertrial | ok | criminal_defence_bail | True | True | 15.6s | father bail filed magistrate court ipc 376 rape case why direct to sessions court |
| 14 | procedural | ok | court_procedure | True | True | 16.3s | how to refer industrial dispute to labour court under section 10 |
| 15 | rural_dlsa | ok | labour_exploitation_discrimination | True | True | 19.8s | I am ASHA worker not paid honorarium 6 months who can help |
| 16 | small_business | ok | court_procedure | True | False | 18.2s | respondent skipped pre litigation mediation can my commercial suit be rejected at threshold |
| 17 | tribal_marginalized | ok | criminal_defence_bail | False | False | 4.3s | they say i am tonhi after child died in village false case filed chhattisgarh |
| 18 | urban_pro | ok | business_contract_partnership | True | True | 17.0s | my startup co founder is trying to dilute my equity using ESOP pool without my consent, i have 30 percent |
| 19 | women_vulnerable | ok | police_fir | True | True | 21.9s | auto driver threw something on my face on the road my eyes are burning I went hospital they said acid what to do |
| 20 | youth_digital | ok | cyber_fraud_or_harassment | True | False | 18.1s | ex husband created fake whatsapp using my new sim number harassing my family |
| 21 | elderly | partial | senior_citizen | True | True | 5.9s | i gifted house to son in 2015 now he is not feeding me can i take back |
| 22 | migrant_labour | ok | labour_exploitation_discrimination | True | True | 13.4s | site engineer noida said women workers no welder job only sweeper half pay why |
| 23 | prisoner_undertrial | off_topic | arrest_custody_safeguard | True | False | 12.4s | papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai |
| 24 | procedural | ok | tax_gst_compliance | True | True | 19.6s | time limit and Form 35 for filing appeal to CIT Appeals income tax |
| 25 | rural_dlsa | ok | family_domestic | True | True | 22.6s | my husband drinking everyday beating me and children where can I get protection order |
| 26 | small_business | ok | labour_compliance | True | False | 23.1s | esi inspector sent notice contribution short by 1.2 lakh for casual workers can i contest |
| 27 | tribal_marginalized | ok | environment_compensation | False | False | 19.3s | thermal plant blasting cracking our houses no compensation kalahandi |
| 28 | urban_pro | ok | tax_gst_compliance | True | True | 14.0s | TCS deducted on foreign remittance for my son education abroad how do i claim it back |
| 29 | women_vulnerable | partial | child_custody_adoption | False | False | 14.9s | my husband took our 5 year old to delhi during fight and is not letting me meet how do I get her back fast |
| 30 | youth_digital | ok | cyber_fraud_or_harassment | True | False | 18.6s | someone leaked my chat with therapist on twitter mental health privacy |
| 31 | elderly | off_topic | property_tenancy | True | False | 15.3s | mother gave land to younger son verbally now older son disputing it after 20 years |
| 32 | migrant_labour | ok | digital_platform_account | True | False | 4.7s | ola driver suspended id no reason 4000 rupees earning gone how to complaint |
| 33 | prisoner_undertrial | partial | police_fir | True | False | 4.7s | father custodial death lockup byculla police saying suicide what is 196 procedure |
| 34 | procedural | ok | court_procedure | False | False | 20.0s | process to file 482 CrPC quashing petition in high court |
| 35 | rural_dlsa | ok | social_welfare_identity | False | False | 5.1s | panchayat secretary not giving me birth certificate of my child born at home |
| 36 | small_business | partial | trademark_ip | True | True | 19.3s | software vendor sent notice saying we are using unlicensed copies 22 cad seats noida |
| 37 | tribal_marginalized | partial | environment_compensation | True | True | 6.4s | company building dam will submerge 4 tribal villages no consent gram sabha odisha |
| 38 | urban_pro | ok | cyber_fraud_or_harassment | False | False | 18.8s | i clicked link in sms and gave OTP, lost 60000 from icici account, bank says my fault no refund |
| 39 | women_vulnerable | ok | family_domestic | True | True | 17.6s | husband took my salary atm card and gives me only 2000 per month for groceries is this legal he says he is breadwinner |
| 40 | youth_digital | ok | cheque_bounce | True | True | 18.0s | client cheque of 2 lakh bounced for my logo work how to send notice |
| 41 | elderly | off_topic | banking_credit_dispute | True | False | 6.4s | private cooperative bank fd of grandfather not honoured nominee facing harassment |
| 42 | migrant_labour | partial | employment_wages | False | False | 16.1s | boss saying i signed paper give up wages but i dont read english kannada bangalore |
| 43 | prisoner_undertrial | partial | custody_compensation | True | True | 20.2s | i was in jail 7 yrs acquitted now how to get compensation state legal aid |
| 44 | procedural | ok | property_tenancy | False | False | 15.9s | judgment debtor not paying money decree how to attach property |
| 45 | rural_dlsa | ok | workplace_injury_compensation | True | True | 6.2s | construction worker registered in BOCW board accident at site no help from board |
| 46 | small_business | ok | business_contract_partnership | True | True | 16.5s | vendor agreed delivery in 30 days now 4 months over want to cancel and recover advance 8 lakh |
| 47 | tribal_marginalized | ok | tribal_caste_atrocity | True | True | 16.0s | community forest resource claim CFR rejected by DLC how appeal odisha kandhamal |
| 48 | urban_pro | ok | employment_wages | True | True | 23.5s | my employer is not depositing my PF for last 8 months, salary slip shows deduction but EPFO passbook shows nothing |
| 49 | women_vulnerable | ok | child_custody_adoption | False | False | 15.4s | my ex husband took our son to UK on tourist visa and is not bringing back he said permanent now what to do |
| 50 | youth_digital | ok | cyber_fraud_or_harassment | True | True | 6.0s | data breach my dpdp rights kya hain after dunzo leaked my address |
| 51 | elderly | ok | employment_wages | True | True | 22.9s | father epf trust delayed gratuity 18 months no interest paid hsmc bangalore |
| 52 | migrant_labour | partial | labour_exploitation_discrimination | True | False | 17.1s | thekedar gave 8 of us same name on register only 2 names real cheating bocw he gets cess |
| 53 | prisoner_undertrial | off_topic | criminal_defence_bail | True | True | 5.5s | brother arrested NDPS 50 gram heroin commercial or not bail chances |
| 54 | procedural | ok | court_procedure | True | True | 20.1s | decree holder how to file execution petition Order 21 CPC |
| 55 | rural_dlsa | ok | land_revenue_records | False | False | 21.8s | pattadar passbook lost in flood how to get new one tehsildar saying come next month |
| 56 | small_business | ok | ibc_nclt | True | True | 16.4s | operational creditor i am want to file section 9 ibc against company owing 2.5 cr |
| 57 | tribal_marginalized | ok | tribal_caste_atrocity | True | True | 15.8s | patta given under FRA but forest guards still cutting our bamboo saying it is reserved bastar |
| 58 | urban_pro | ok | tax_gst_compliance | True | True | 19.2s | my employer deducted TDS but did not deposit it, form 26AS not showing the amount, refund stuck |
| 59 | women_vulnerable | no_relevance | criminal_general | True | False | 15.2s | police came to spa where I work in delhi I ran away am I in trouble do I need lawyer they have my photo from cctv |
| 60 | youth_digital | ok | employment_wages | True | True | 6.2s | urban company beautician 3 strike system unfair termination labour law |
| 61 | elderly | ok | property_tenancy | True | True | 15.8s | mother passed away last year father wants to sell flat what papers needed kolkata |
| 62 | migrant_labour | ok | police_fir | True | False | 15.6s | fake fir against me theft mobile when i asked wages thekedar now lawyer asking 25000 |
| 63 | prisoner_undertrial | ok | criminal_defence_bail | True | True | 17.3s | uncle bail granted but cant pay surety 50000 what to do poor family |
| 64 | procedural | partial | court_procedure | True | True | 6.1s | court fee for filing writ petition in high court fixed or ad valorem |
| 65 | rural_dlsa | ok | criminal_general | True | True | 19.6s | moneylender took my thumb impression on blank paper now showing 5 lakh loan I never took |
| 66 | small_business | ok | business_license_compliance | True | True | 18.5s | fssai notice mismatch in licence category for snack manufacturing renewal due how to upgrade state to central |
| 67 | tribal_marginalized | ok | police_fir | True | False | 26.4s | neighbours calling me witch want to throw me out of village chaibasa what law |
| 68 | urban_pro | ok | consumer | True | True | 16.6s | swiggy delivery agent damaged my food and was rude, app refunded only 50 percent and closed ticket |
| 69 | women_vulnerable | partial | cyber_fraud_or_harassment | False | False | 6.1s | he took my private pictures when we were together now we broke up and he is threatening to put on telegram |
| 70 | youth_digital | ok | digital_platform_account | False | False | 16.2s | ola cabs deactivated me after 2 years driving in koramangala no warning |
| 71 | elderly | ok | social_welfare_identity | True | True | 6.7s | papa ki pension 6 month se nahi aayi rti kaise file karein |
| 72 | migrant_labour | off_topic | social_welfare_identity | True | True | 18.8s | ration card west bengal not working in chennai shop no rice for family one nation one card not happening |
| 73 | prisoner_undertrial | partial | legal_aid | True | True | 14.4s | husband first time arrest jail superintendent not allowing lawyer meeting legal |
| 74 | procedural | ok | general_legal | True | True | 12.9s | how to initiate mediation under Mediation Act 2023 without going to court |
| 75 | rural_dlsa | partial | social_welfare_identity | True | True | 5.1s | post matric scholarship not credited for 2 years college fees due |
| 76 | small_business | ok | cheque_bounce | True | True | 17.1s | cheque dishonoured insufficient funds sent legal notice 30 days over can i file complaint |
| 77 | tribal_marginalized | ok | tribal_caste_atrocity | False | False | 16.2s | mob attacked our pahan during sarna puja calling adivasi non hindu jharkhand |
| 78 | urban_pro | ok | consumer | True | True | 15.6s | bought iphone from amazon, delivered fake one, amazon refusing refund saying it was sold by third party seller |
| 79 | women_vulnerable | ok | family_domestic | False | False | 17.8s | I gave birth to baby with disability my in laws want me to leave the baby in hospital what is the law |
| 80 | youth_digital | partial | cyber_fraud_or_harassment | True | True | 5.8s | my nudes leaked on whatsapp group after breakup what section against him |
| 81 | elderly | ok | general_legal | False | False | 11.6s | tribunal in tamil nadu ordered son to pay 10000 per month he stopped paying enforce kaise |
| 82 | migrant_labour | partial | social_welfare_identity | True | True | 18.5s | ration card bihar village me hai but family in mumbai 3 years no rice how to add address |
| 83 | prisoner_undertrial | ok | criminal_defence_bail | False | False | 20.9s | 16 yr daughter arrested theft put in observation home or jail how to verify age |
| 84 | procedural | ok | police_fir | True | True | 13.6s | police refused to register FIR for theft of my bike where do I go next |
| 85 | rural_dlsa | ok | criminal_defence_bail | True | False | 15.8s | my wife filed 498A on whole family even my old mother how to defend |
| 86 | small_business | ok | ibc_nclt | True | True | 6.2s | llp partner refusing to sign form 11 annual return 2 years pending strike off threat |
| 87 | tribal_marginalized | ok | manual_scavenging_safety | True | True | 19.3s | dry latrine still in our basti panchayat forcing dalit women to clean dindori |
| 88 | urban_pro | ok | criminal_defence_bail | True | False | 13.4s | my wife filed false 498A case against me and my parents, can we get anticipatory bail |
| 89 | women_vulnerable | off_topic | family_domestic | True | True | 17.1s | sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon |
| 90 | youth_digital | ok | digital_platform_account | True | True | 15.9s | instagram suspended my page 200k followers no notice can i sue meta india |
| 91 | elderly | partial | succession_inheritance | True | True | 15.6s | father says he is muslim 72 years his sons not giving share from grandfather property hyderabad |
| 92 | migrant_labour | ok | street_vendor_municipal | True | True | 14.5s | street vendor mumbai bandra municipal demolished my cart no notice no tvc certificate |
| 93 | prisoner_undertrial | partial | undertrial_review_release | True | True | 5.9s | i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain |
| 94 | procedural | ok | court_procedure | True | False | 20.9s | is pre-litigation mediation mandatory before filing commercial suit |
| 95 | rural_dlsa | ok | senior_citizen | True | True | 6.3s | my son not giving food and money I am 72 year old where to complain |
| 96 | small_business | ok | cheque_bounce | True | True | 17.0s | my cheque issued to supplier bounced because account closed will i go to jail |
| 97 | tribal_marginalized | off_topic | bonded_labour_rescue | True | True | 5.3s | release certificate not given to bonded labour rehab money pending 3 years jharkhand |
| 98 | urban_pro | ok | employment_wages | True | True | 17.0s | ESI hospital refused to treat my wife for delivery saying my contributions are short, what is the eligibility |
| 99 | women_vulnerable | ok | family_marriage_status | True | True | 20.1s | husband took second wife without divorcing me he says muslim law allows him I am also muslim what protection do I have |
| 100 | youth_digital | ok | tax_gst_compliance | True | True | 15.7s | freelance designer 18 lakh income should i register gst or no |

## Subagent Review Consensus

Three read-only subagent reviews agreed that the old100/new100 methodology is valid for this gate: old100 is a known regression set, new100 is a non-overlapping generalization set with 10 prompts per persona, and the zero-overlap check is meaningful. They also agreed it is not enough for final launch certification because it is one new holdout seed and procedure-anchor coverage is still thin.

All three reviewers agreed the production-readiness verdict is fair. The shared blockers they called out were:

1. Systemic cited-grounding failure, especially new100 `62/99 (62.6%)`.
2. Urgent custody/arrest safeguards still failing or missing citations.
3. Women/minor cyber-sexual-harm prompts missing IT Act/POCSO/BNS grounding.
4. Bonded-labour release/rescue templates returning off-topic answers despite source hits.
5. Child custody, juvenile justice, banking fraud/FD, and public-benefit/document routes needing stronger router/source packs before product launch.

## Raw Artifacts

- old100 report: `reports/prod_gate_final100_codex_stage36_old100_seed2026052916.md`
- old100 JSONL: `data/processed/timed_eval_final100_codex_stage36_old100_seed2026052916.jsonl`
- new100 report: `reports/prod_gate_final100_codex_stage36_new100_seed2026053001.md`
- new100 JSONL: `data/processed/timed_eval_final100_codex_stage36_new100_seed2026053001.jsonl`
- generated new100 prompt set: `data/eval_benchmark_new100_seed2026053001/`
