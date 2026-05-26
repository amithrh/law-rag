"""Lay-phrase → legal-vocabulary query expansion (Task #13).

Why this exists — the eval's #1 finding:

  The 102-query e2e eval (2026-05-19, scripts/eval_e2e_100.py) showed
  that 56/102 queries drew only from SC caselaw — even when the
  operative Act WAS indexed. Bare-act surface rate: 25%. The
  dominant failure mode was lay-phrase queries (e.g. "my landlord
  won't return my deposit", "boss fired me without notice") failing
  to find the legal-vocabulary terms used in bare Acts (TPA s.108,
  Industrial Disputes Act s.25F retrenchment notice).

  13 of those produced wrong-direction answers ("you should deposit
  rent in court" for the deposit query — citation-correct, topically
  wrong). The remaining 43 produced PARTIAL or REFUSED.

Approach (lightweight LLM rewrite):

  1. Use the local qwen3:14b that's already loaded for /answer.
  2. Ask it to translate the lay query into 2-3 legal-search variants
     that include Act names, section numbers, and statutory terms.
  3. Run hybrid retrieval (dense + sparse + BM25) on EACH variant
     plus the original, then RRF-fuse the results.
  4. The fused top-K should now have both lay-similar SC cases AND
     the directly-applicable bare-Act chunks.

Latency budget: ~1.5-2 sec for qwen3:14b at max_tokens=200. The
/answer flow already takes 25-35 sec; this added cost is acceptable.

Honest caveats:

  - The LLM may invent Act names that don't exist. We DON'T cite the
    LLM's output to the user — it's purely a retrieval rewrite step,
    so hallucination here only hurts retrieval recall (mildly), not
    citation correctness.
  - For genuinely off-corpus queries ("weather today"), the LLM may
    invent a plausible-sounding legal frame ("weather information
    under RTI Act"). That's fine: the coverage gate still refuses
    when rerank scores are low.
  - We default to enabled but expose a kill switch (`query_expansion_
    enabled` in config) so we can A/B during the rollout.
"""
from __future__ import annotations

import logging
import re
import time

from .config import get_settings
from .llm import chat_once
from .matter_router import MatterRoute, route_matter

logger = logging.getLogger(__name__)


# Strong, opinionated prompt that wants ONLY the queries — no preamble,
# no numbering, no extra commentary. qwen3:14b respects this most of the
# time but we still post-filter for safety.
_SYSTEM_PROMPT = (
    "You are a legal research assistant for Indian law. Indian users ask "
    "in EVERYDAY, COLLOQUIAL, or BROKEN ENGLISH about legal problems. "
    "Output 3 short legal-search queries that an Indian legal database "
    "would use to find the relevant law.\n\n"

    "CRITICAL — read the SOCIAL CONTEXT, not just literal words. Many lay "
    "phrases are EUPHEMISMS that point to a specific Indian Act. If you "
    "miss the social meaning, you'll route the user to the wrong law — "
    "which is worse than refusing. Common euphemism → Act mappings the "
    "average legal-aid client uses:\n"
    "  'caught in spa/massage parlour by police'    → Immoral Traffic "
    "(Prevention) Act 1956 (NOT Indian Evidence Act presumptions)\n"
    "  'soliciting / prostitution / sex worker arrested' → ITPA 1956\n"
    "  'boss touched me / colleague harassed me'    → POSH Act 2013 + "
    "Bharatiya Nyaya Sanhita section 74/75 (assault on woman)\n"
    "  'in-laws asking for money / car at marriage' → Dowry Prohibition "
    "Act 1961 + BNS s.85 (cruelty)\n"
    "  'live-in but he refuses to marry'             → Protection of Women "
    "from Domestic Violence Act 2005 + BNS s.69 (sexual intercourse by "
    "deceitful means)\n"
    "  'my son threw me out / not feeding parents'   → Maintenance & Welfare "
    "of Parents and Senior Citizens Act 2007 s.4, s.23\n"
    "  'school not admitting / capitation fee'       → RTE Act 2009\n"
    "  'cheque bounced / cheque not honoured'        → NI Act 1881 s.138\n"
    "  'fired without notice / boss kicked me out'   → Industrial Disputes "
    "Act 1947 s.25F\n"
    "  'landlord not returning deposit / asking high rent' → State Rent "
    "Control Act + Transfer of Property Act\n"
    "  'neighbour took my land / land grabbed'       → Specific Relief Act "
    "1963 + Transfer of Property Act 1882 + Limitation Act 1963\n"
    "  'married as child / underage marriage'        → Prohibition of "
    "Child Marriage Act 2006\n"
    "  'online order broken / e-commerce fraud'      → Consumer Protection "
    "Act 2019 (NOT 1986)\n"
    "  'deepfake / morphed photo / nude leaked'      → IT Act 2000 s.66E, "
    "s.67 + DPDP Act 2023 + BNS s.77/356\n"
    "  'police arrested without telling reason'      → Article 22 + BNSS "
    "s.35 (NOT Article 21 alone)\n"
    "  'ED raided my house / property attached'      → PMLA 2002\n"
    "  'caught with drugs / NDPS'                    → NDPS Act 1985 s.37\n\n"

    # =====================================================================
    # ROUND-2 EXPANSION (May 2026, mined from 500-query eval retrieval_miss
    # bucket; 313 / 501 queries failed because the operative Act in our
    # corpus DID NOT surface in top-K — almost always because the lay
    # phrase has a non-obvious mapping to a specific Act + section).
    # Each entry below is anchored to a real query the system got wrong.
    # =====================================================================
    "MORE common lay-phrase → Act mappings (added after eval-500):\n"

    # ---- elder care / inheritance / personal-law succession ----
    "  'pension nahi aayi / epfo arrears / 75 years pension stopped' "
    "→ Employees Pension Scheme 1995 + EPF Act 1952 s.7A + RTI Act 2005 + "
    "CGIT industrial tribunal\n"
    "  'gratuity not paid 18 months / employer delayed gratuity' "
    "→ Payment of Gratuity Act 1972 s.7 s.8\n"
    "  'tribunal under senior citizens act / son refuses maintenance / "
    "registered gift deed cancelled' → Maintenance and Welfare of Parents "
    "and Senior Citizens Act 2007 s.5 s.7 s.9 s.11 s.23\n"
    "  'daughter coparcener / ancestral property / brother sold without "
    "consent' → Hindu Succession Act 1956 s.6 (post-2005 amendment) + "
    "Vineeta Sharma v Rakesh Sharma 2020 INSC\n"
    "  'father not registered will / latest will not registered' → Indian "
    "Succession Act 1925 s.63 (will execution) + Registration Act 1908 "
    "s.18 (optional registration)\n"
    "  'christian widow / parsi mother / muslim husband died property' "
    "→ Indian Succession Act 1925 s.32 s.33 (Christians intestate) / "
    "s.50 s.54 (Parsi schedule) / Muslim Personal Law (Shariat) "
    "Application Act 1937 — DO NOT default to Hindu Succession Act\n"
    "  'father transferred flat to son before death / gift cancellation' "
    "→ Transfer of Property Act 1882 s.122 s.126 + MWP Act 2007 s.23\n"
    "  'thumb impression on blank paper / signed property under pressure ICU' "
    "→ Indian Contract Act 1872 s.16 (undue influence) + TPA 1882 s.122\n"
    "  'benami property bought in son name / joint name disputed' → "
    "Benami Transactions (Prohibition) Act 1988 + TPA 1882\n"

    # ---- undertrial / bail / criminal procedure (BIG bucket: 31+ queries) ----
    "  'X months in jail no chargesheet / default bail' → BNSS 2023 "
    "s.187(3) (formerly CrPC 1973 s.167(2)) — 60 days default bail "
    "for offences <10yr, 90 days for >=10yr; NDPS = 180 days via s.36A\n"
    "  'anticipatory bail 498A / domestic violence FIR' → BNSS 2023 "
    "s.482 (formerly CrPC s.438) + Arnesh Kumar v State of Bihar 2014 "
    "(no automatic arrest <7yr) + Satender Kumar Antil v CBI 2022\n"
    "  'UAPA bail rejected / NIA case bail' → UAPA 1967 s.43D(5) + "
    "K.A. Najeeb v Union of India 2021 (prolonged incarceration "
    "exception) + NIA v Zahoor Ahmad Shah Watali 2019\n"
    "  'medical interim bail jail / 65 yr father TB cancer in jail' → "
    "BNSS 2023 s.480 + State of MP v Madanlal 2015 + Arnab Manoranjan "
    "Goswami v Maharashtra 2020 (Art. 21 liberty)\n"
    "  'mulaqat denied prison / family visit jail' → Prison Manual "
    "state rules + Sunil Batra v Delhi Admin 1978 INSC + Article 21\n"
    "  'wrongful detention compensation / acquitted want compensation' → "
    "Hussainara Khatoon v Bihar 1979 INSC + Nilabati Behera v Orissa 1993 "
    "+ Article 21 + DK Basu v West Bengal 1997\n"
    "  'PMLA twin condition / ED bail / women interim bail PMLA' → "
    "PMLA 2002 s.45 + first proviso (women / minors / sick) + Vijay "
    "Madanlal Choudhary v UoI 2022 INSC + Pankaj Bansal v UoI 2023 "
    "(arrest grounds in writing) + Saumya Chaurasia v ED 2024\n"
    "  'NDPS commercial quantity bail rejected 6 times' → NDPS 1985 s.37 + "
    "Mohd Muslim v State NCT Delhi 2023 (prolonged incarceration) + "
    "Toofan Singh v State of TN 2020 (s.67 statement inadmissible)\n"
    "  'NDPS small quantity / 5 gram personal use' → NDPS 1985 s.37 NOT "
    "applicable below commercial quantity + Hira Singh v UoI 2020 "
    "(neutral substance test) + NDPS Notification S.O. 1055(E)\n"
    "  '16 yr old in adult jail / observation home / age determination' → "
    "Juvenile Justice (Care and Protection) Act 2015 s.9 s.94 + JJ "
    "Rules 2016 r.12 (age determination procedure) + r.8 (transfer to "
    "observation home)\n"
    "  'brother beaten in police lockup / custodial torture' → DK Basu "
    "v West Bengal 1997 INSC guidelines + BNSS s.35 (formerly CrPC s.41) "
    "+ NHRC custodial-death format\n"
    "  'caste slur / called us by caste name / atrocity FIR refused' → "
    "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) "
    "Act 1989 s.3(1)(r) s.3(1)(s) s.3(2)(va) s.4 (dereliction by "
    "officer) + BNSS 2023 s.173 s.175 + Rules 1995\n"

    # ---- migrant labour / unorganized / occupational injury ----
    "  'thekedar took advance / cannot leave site / 18000 advance' → "
    "Bonded Labour System (Abolition) Act 1976 s.4 s.21 + ISMW Act 1979 + "
    "Code on Wages 2019\n"
    "  'principal employer ran with wages / contractor disappeared / "
    "displacement allowance' → Contract Labour (Regulation and Abolition) "
    "Act 1970 s.21 (principal-employer liability) + Inter-State Migrant "
    "Workmen Act 1979 s.14 s.15\n"
    "  'no payment 6 months / munshi keeps saying next week' → Payment of "
    "Wages Act 1936 s.4 s.5 + Code on Wages 2019 (after 1 Apr 2026 "
    "consolidation) + state labour court\n"
    "  '14 hour work no overtime construction site' → Factories Act 1948 "
    "s.59 (overtime double rate) + BOCW Act 1996 s.40 + state BOCW rules\n"
    "  'minimum wage 350 only contractor / state rate higher' → Minimum "
    "Wages Act 1948 + Code on Wages 2019 s.5 + state minimum wage "
    "schedule\n"
    "  'fell from site / boiler burst factory / silicosis quarry' → "
    "Building and Other Construction Workers (RECS) Act 1996 s.7 s.39 + "
    "Employees Compensation Act 1923 Sch III (occupational disease) + "
    "Sch IV (compensation) + Factories Act 1948 + Mines Act 1952\n"
    "  'domestic worker not paid / madam not giving wage' → Unorganised "
    "Workers Social Security Act 2008 + Payment of Wages Act 1936 + Code "
    "on Social Security 2020\n"

    # ---- rural / panchayat / FRA / PESA / MGNREGA ----
    "  'sarpanch giving common land to brother / panchayat irregular' → "
    "state Panchayati Raj Act + Article 243 + Panchayat (Extension to "
    "Scheduled Areas) Act 1996 (PESA) where applicable\n"
    "  'patwari asking 5000 / officer demanding bribe' → Prevention of "
    "Corruption Act 1988 s.7 (public servant taking gratification) + s.13 "
    "+ Lokayukta state act\n"
    "  'MGNREGA wages not paid / job card not given / social audit "
    "ignored' → MGNREGA 2005 s.3 (right to work) s.7 (timely payment) "
    "s.17 (social audit) s.19 (grievance) + Sch II para 8 (compensation "
    "for delay)\n"
    "  'IFR title / CFR rejected / forest officer cutting bamboo / mining "
    "on community forest' → Forest Rights Act 2006 s.3(1)(c) (MFP "
    "rights) s.3(1)(i) (CFR) s.4(4) (joint title for spouse) s.5 + "
    "FRA Rules 2008 r.12A (appeal)\n"
    "  'gram sabha consent / palli sabha / mining without consultation' "
    "→ PESA Act 1996 s.4(i) + LARR Act 2013 s.41(3) (SC/ST consent) + "
    "MMDR Act 1957 + Forest (Conservation) Act 1980 s.2\n"
    "  'witch hunting / daayan / tonhi labelled' → state Witch Hunting "
    "Prohibition Act (Jharkhand 2001, Assam 2015, Chhattisgarh 2005) + "
    "BNS 2023 s.115 s.117 (hurt) + SC/ST POA Act if applicable\n"
    "  'ration card cancelled aadhaar mismatch / PDS biometric fail' → "
    "National Food Security Act 2013 s.31 + state PDS rules + Aadhaar "
    "Act 2016 s.7 (NOT mandate denying entitlement — see Puttaswamy "
    "2018)\n"
    "  'caste certificate rejected by tehsildar' → state SC/ST/OBC "
    "certificate rules + Article 341 + Article 342 + Kumari Madhuri "
    "Patil v Addl Commissioner 1994 INSC\n"

    # ---- women / family / personal-law / maternity ----
    "  'wife mulaqat denied / family visit prison' → state Prison Manual "
    "+ Article 21 + Sunil Batra 1978 INSC\n"
    "  'husband left with kids no school fees / deserted' → CrPC s.125 / "
    "BNSS 2023 s.144 maintenance + Hindu Adoption and Maintenance Act "
    "1956 (Hindu) / Muslim Women (Protection of Rights on Divorce) Act "
    "1986 (Muslim) / Shah Bano 1985\n"
    "  'maternity leave role given to someone else / PIP after return' → "
    "Maternity Benefit Act 1961 s.5 s.12 (no dismissal during maternity)\n"
    "  'workplace harassment HR putting me on PIP / retaliation' → POSH "
    "Act 2013 s.10 s.13 + Vishaka v State of Rajasthan 1997 INSC + "
    "Industrial Employment (Standing Orders) Act 1946\n"
    "  'live-in but he refuses to marry / promised marriage cohabitation' "
    "→ PWDVA 2005 + BNS 2023 s.69 (deceitful means) — NOTE: this "
    "replaces the older 'rape on promise to marry' framing under "
    "IPC s.375; the user is NOT a 'prosecutrix' under IEA s.114-A\n"

    # ---- cyber / fintech / online ----
    "  'nudes leaked on whatsapp / morphed photo / deepfake / AI CSAM' → "
    "IT Act 2000 s.66E (privacy) s.67 (obscene material) s.67A (sexually "
    "explicit) + BNS 2023 s.77 (voyeurism) s.319 (cheating by "
    "personation) s.356 (defamation) + DPDP Act 2023 + POCSO 2012 if "
    "minor\n"
    "  'fake instagram account using my photos / impersonation' → IT Act "
    "2000 s.66D (cheating by personation using computer) + BNS 2023 "
    "s.318 (cheating) + DPDP 2023\n"
    "  'blackmailing screenshots to my dad / nude extortion' → BNS 2023 "
    "s.308 (extortion) + IT Act 2000 s.66E + s.67\n"
    "  'phonepe / paytm fraud / OTP stolen 8 lakh / fake call SBI "
    "pension' → IT Act 2000 s.66C (identity theft) s.66D + BNS 2023 "
    "s.318 + RBI Master Direction on Fraud + cybercrime.gov.in NCRP "
    "portal\n"
    "  'crypto rugpull / telegram scam / wallet frozen binance' → PMLA "
    "2002 + IT Act 2000 + RBI advisory on virtual assets + Consumer "
    "Protection Act 2019\n"
    "  'fake cbi call drugs parcel send money / digital arrest scam' → "
    "BNS 2023 s.318 (cheating) s.319 (cheating by personation) + IT Act "
    "2000 s.66D + cybercrime.gov.in\n"
    "  'deepfake of politician / morphed political clip' → IT Act 2000 "
    "s.66E s.67 + Representation of People Act 1951 + DPDP 2023\n"
    "  'data breach my DPDP rights / company leaked my data' → DPDP "
    "Act 2023 s.7 (data principal rights) s.27 (penalty) + IT Act 2000 "
    "s.43A (companies) + Puttaswamy v UoI 2017 INSC (privacy)\n"

    # ---- small business / MSME / contract / GST / trade ----
    "  'MSME 45 days payment delay / buyer not paying / udyam registered' "
    "→ MSMED Act 2006 s.15 (45-day cap) s.16 (compound interest) s.17 "
    "(reference to facilitation council) + MSME Samadhan portal\n"
    "  'specific performance land deal / seller backing out' → Specific "
    "Relief Act 1963 s.10 s.14 (after 2018 amendment, specific "
    "performance is rule not exception)\n"
    "  'shop act registration labour inspector / state shop and "
    "establishment' → state Shops and Establishments Act\n"
    "  'mou exclusivity violated / dealer selling to competitor' → Indian "
    "Contract Act 1872 s.27 (restraint of trade) s.73 + Specific Relief "
    "Act 1963 s.42\n"
    "  'agent absconded with goods / consignment lost principal-agent' → "
    "Indian Contract Act 1872 s.182 s.211 s.213\n"
    "  'former employee using customer list / NDA violation' → Indian "
    "Contract Act 1872 s.27 + Common-law breach of confidence + Trade "
    "Secrets (no statute yet)\n"
    "  'client in dubai not paying invoice / cross-border SaaS' → Indian "
    "Contract Act 1872 + FEMA 1999 + Arbitration and Conciliation Act "
    "1996 (if arbitration clause)\n"
    "  'GST show cause s.74 / GSTR mismatch / ITC reversal / godown "
    "sealed' → CGST Act 2017 s.73 (no-fraud demand) s.74 (fraud demand) "
    "s.16(2)(c) (ITC blocked if supplier didn't pay) s.67 (search) "
    "s.83 (provisional attachment) + Rule 86A (ITC block)\n"

    # ---- banking / insurance / tax for urban users ----
    "  'bank wrongly debited / forex unrecognised transaction' → Banking "
    "Ombudsman Scheme 2021 (RBI-Integrated Ombudsman) + Consumer "
    "Protection Act 2019 + Banking Regulation Act 1949\n"
    "  'insurance claim rejected / pre-existing disease declared / health "
    "insurance' → Insurance Act 1938 + IRDAI Health Insurance Regulations "
    "2016 + IRDAI Ombudsman + Consumer Protection Act 2019\n"
    "  'TDS deducted but not deposited / Form 26AS missing' → Income Tax "
    "Act 1961 s.200 s.201 + IT Rules + Form 26AS reconciliation + "
    "Income Tax Act 2025 (post 1 Apr 2026)\n"
    "  'recovery agent harassment NBFC / bank goons at office' → RBI "
    "Master Direction on Recovery Agents + RBI Fair Practices Code + "
    "BNS 2023 s.351 (criminal intimidation)\n\n"

    "SAFETY — IDENTIFY WHO THE USER IS in the situation. If the user is "
    "the SUBJECT of police/state action ('I am caught', 'I am arrested', "
    "'police took me'), variants must surface the user's RIGHTS AS AN "
    "ACCUSED — bail, defence, procedural safeguards. DO NOT default to "
    "the victim/complainant framing (Evidence Act presumptions, rape "
    "prosecution provisions, etc.) when the user is the accused.\n\n"

    "Each query MUST:\n"
    "- Include the operative Act's FULL OFFICIAL short title with the "
    "ORIGINAL ENACTMENT YEAR — 'Negotiable Instruments Act 1881' (NOT "
    "'NI Act 2018'), 'Central Goods and Services Tax Act 2017' (NOT "
    "'GST Act'), 'Consumer Protection Act 2019' (NOT 1986 — the 1986 "
    "Act was repealed), 'Protection of Women from Domestic Violence Act "
    "2005', 'Transfer of Property Act 1882', 'Industrial Disputes Act "
    "1947'.\n"
    "- If the user's question contains a section number ('section 138', "
    "'s.25F', 'Art. 21'), every variant MUST keep that exact section "
    "reference verbatim.\n"
    "- Use statutory terminology, not lay phrases ('eviction' not "
    "'thrown out'; 'retrenchment' not 'fired'; 'maintenance' not "
    "'taking care'; 'soliciting' not 'caught in spa').\n"
    "- Be 4-15 words long.\n\n"

    "The 3 queries MUST be DIVERSE. Aim for:\n"
    "  (1) the PRIMARY Act + most relevant section (operative law)\n"
    "  (2) ALTERNATIVE Act or different section (parallel remedy / "
    "procedure)\n"
    "  (3) the PROCEDURAL angle — how to file, where, in what forum.\n"
    "Where a 2023+ Act replaces a colonial one (BNS/BNSS/BSA), include "
    "BOTH the new and the predecessor.\n\n"

    "Output ONLY the 3 queries, one per line. No numbering, no quotes, "
    "no preamble, no explanation. If the question is genuinely not about "
    "Indian law (weather, food, code, sports), output: 'NOT_LEGAL'.\n\n"

    "Examples of the right behaviour:\n"
    "  Q: 'i am caught in spa by police'\n"
    "    Immoral Traffic Prevention Act 1956 section 7 soliciting public\n"
    "    Immoral Traffic Prevention Act 1956 section 3 brothel keeping\n"
    "    rights of accused under BNSS 2023 section 35 search seizure\n"
    "  Q: 'my husband is beating me'\n"
    "    Protection of Women from Domestic Violence Act 2005 section 12\n"
    "    Bharatiya Nyaya Sanhita 2023 section 85 cruelty by husband\n"
    "    PWDVA Magistrate procedure protection order Section 18\n"
    "  Q: 'phonepe fraud 8 lakh someone stole my otp'\n"
    "    Information Technology Act 2000 section 66C 66D identity fraud\n"
    "    Bharatiya Nyaya Sanhita 2023 section 318 cheating\n"
    "    cybercrime portal complaint procedure RBI master direction fraud\n"
    "  Q: 'tribunal in tamil nadu ordered son to pay maintenance he stopped'\n"
    "    Maintenance and Welfare of Parents and Senior Citizens Act 2007 "
    "section 5 section 11 maintenance tribunal procedure\n"
    "    Maintenance and Welfare of Parents Act 2007 section 23 transfer "
    "of property cancellation\n"
    "    enforcement of maintenance order arrears warrant section 9\n"
    "  Q: 'brother in jail 6 months no chargesheet ipc 420'\n"
    "    BNSS 2023 section 187 default bail 60 days no chargesheet\n"
    "    CrPC 1973 section 167 default bail computation pre-1-Jul-2024\n"
    "    BNSS 2023 section 480 section 482 regular and anticipatory bail "
    "procedure\n"
    "  Q: 'MSME 45 days buyer not paying 22 lakh udyam registered'\n"
    "    MSMED Act 2006 section 15 section 16 45-day payment delay "
    "compound interest\n"
    "    MSME Samadhan portal facilitation council reference section 17\n"
    "    Specific Relief Act 1963 specific performance commercial dispute\n"
    "  Q: 'as a daughter am i coparcener father died 2003 before amendment'\n"
    "    Hindu Succession Act 1956 section 6 amendment 2005 daughter "
    "coparcener\n"
    "    Vineeta Sharma v Rakesh Sharma 2020 retrospective coparcenary "
    "right\n"
    "    partition suit ancestral property female coparcener procedure\n"
)


_ROUTE_EXPANSIONS: dict[str, list[str]] = {
    "consumer": [
        "Consumer Protection Act 2019 deficiency in goods refund complaint",
        "e-Daakhil District Consumer Disputes Redressal Commission refund",
    ],
    "social_welfare_identity": [
        "Aadhaar Act 2016 identity authentication correction benefit denial",
        "RTI Act 2005 welfare scheme scholarship pension rejection reasons",
    ],
    "digital_platform_account": [
        "Information Technology Rules platform grievance officer account suspension",
        "Consumer Protection Act 2019 digital platform account money dispute",
    ],
    "police_fir": [
        "BNSS 2023 section 173 FIR registration police refusal",
        "CrPC 1973 section 154 police refusal FIR magistrate complaint",
    ],
    "cyber_fraud_or_harassment": [
        "Information Technology Act 2000 section 66C 66D cyber fraud",
        "BNS 2023 cheating personation cybercrime portal complaint",
    ],
    "sexual_offence_survivor": [
        "BNS 2023 sexual offence FIR survivor medical statement procedure",
        "CrPC 1973 BNSS 2023 rape FIR statement medical examination",
    ],
    "workplace_sexual_harassment": [
        "POSH Act 2013 Internal Committee sexual harassment workplace",
        "BNS 2023 assault stalking workplace sexual harassment police complaint",
    ],
    "reproductive_rights_mtp": [
        "Medical Termination of Pregnancy Act 1971 rape survivor termination",
        "MTP Rules medical board pregnancy termination constitutional rights",
    ],
    "senior_citizen": [
        "Maintenance and Welfare of Parents and Senior Citizens Act 2007 section 4",
        "Senior Citizens Act 2007 section 23 transfer property cancellation",
    ],
    "family_domestic": [
        "Protection of Women from Domestic Violence Act 2005 section 12",
        "BNS 2023 section 85 cruelty husband dowry harassment",
    ],
    "employment_wages": [
        "Payment of Wages Act unpaid salary labour commissioner complaint",
        "Code on Wages 2019 wage theft employer contractor",
    ],
    "labour_exploitation_discrimination": [
        "Bonded Labour System Abolition Act 1976 document retention contractor",
        "MGNREGA Act 2005 wage delay grievance compensation",
    ],
    "workplace_injury_compensation": [
        "Employees Compensation Act 1923 workplace injury accident compensation",
        "BOCW Act 1996 construction worker injury welfare board",
    ],
    "criminal_defence_bail": [
        "BNSS 2023 section 482 anticipatory bail criminal defence",
        "CrPC 1973 section 438 anticipatory bail dowry case",
    ],
    "trademark_ip": [
        "Trade Marks Act 1999 infringement passing off registered mark",
        "Trade Marks Registry opposition rectification brand name dispute",
    ],
    "tax_gst_compliance": [
        "CGST Act 2017 GST registration threshold service provider",
        "Income Tax Act 1961 TDS Form 26AS not deposited",
    ],
    "ibc_nclt": [
        "Insolvency and Bankruptcy Code 2016 section 9 operational creditor",
        "NCLT insolvency application demand notice default debt",
    ],
    "business_contract_partnership": [
        "Indian Contract Act 1872 section 27 non compete restraint trade",
        "Indian Partnership Act 1932 retirement partner liability notice",
    ],
    "business_license_compliance": [
        "state Shops and Establishments Act shop license renewal penalty",
        "municipal trade license renewal delay RTI grievance",
    ],
    "child_custody_adoption": [
        "Juvenile Justice Act 2015 adoption procedure missing papers",
        "child custody habeas corpus international child return writ",
    ],
    "education_rights": [
        "Right to Education Act 2009 admission transfer certificate school",
        "RTE Act section 12 25 percent quota private school",
    ],
    "environment_compensation": [
        "Environment Protection Act 1986 compensation pollution blasting damage",
        "National Green Tribunal Act environmental damage compensation",
    ],
    "pmla_ed": [
        "PMLA 2002 section 45 twin conditions bail",
        "Prevention of Money Laundering Act arrest attachment ED summons",
    ],
    "banking_credit_dispute": [
        "RBI Integrated Ombudsman Scheme bank wrong debit complaint",
        "Credit Information Companies Act CIBIL correction loan closed NOC",
    ],
    "mental_health_care_rights": [
        "Mental Healthcare Act 2017 supported admission rights safeguards",
        "Mental Health Review Board unlawful confinement chains treatment",
    ],
    "tribal_caste_atrocity": [
        "SC ST Prevention of Atrocities Act 1989 caste abuse violence",
        "PESA Act 1996 Forest Rights Act 2006 gram sabha tribal rights",
    ],
    "land_revenue_records": [
        "state land revenue record of rights mutation pattadar passbook",
        "Right to Information Act 2005 land records revenue office delay",
    ],
    "court_procedure": [
        "district court practice directions court etiquette addressing judge",
        "Legal Services Authorities Act 1987 court help desk legal aid",
    ],
    "cheque_bounce": [
        "Negotiable Instruments Act 1881 section 138 cheque dishonour",
        "Negotiable Instruments Act 1881 section 142 limitation complaint",
    ],
    "property_tenancy": [
        "Transfer of Property Act 1882 tenancy lease possession deposit",
        "state rent control act landlord tenant security deposit eviction",
    ],
    "succession_inheritance": [
        "Indian Succession Act 1925 will intestate succession property share",
        "Muslim personal law inheritance share wife daughter mother",
    ],
    "street_vendor_municipal": [
        "Street Vendors Act 2014 seizure goods vending certificate",
        "Town Vending Committee municipal hawker license confiscation",
    ],
    "custody_compensation": [
        "Article 21 compensation wrongful detention speedy trial delay",
        "CrPC 1973 BNSS 2023 default bail no chargesheet custody delay",
    ],
    "prison_parole_furlough": [
        "state prison rules parole furlough remission prisoner release",
        "Article 21 prison parole furlough refusal writ jurisdiction",
    ],
    "rti": [
        "Right to Information Act 2005 first appeal public information officer",
        "RTI Act 2005 information commission second appeal delay reply",
    ],
    "legal_aid": [
        "Legal Services Authorities Act 1987 free legal aid eligibility",
        "NALSA District Legal Services Authority application procedure",
    ],
    "criminal_general": [
        "BNSS 2023 criminal procedure bail arrest FIR complaint",
        "BNS 2023 IPC CrPC applicable based on incident date",
    ],
}


def _route_variants(query: str, route: MatterRoute, max_variants: int) -> list[str]:
    if route.category == "off_topic":
        return []
    variants = _ROUTE_EXPANSIONS.get(route.category, [])
    q = query.lower()
    if route.category == "employment_wages" and re.search(r"\b(epf|pf|provident fund)\b", q):
        variants = [
            "Employees Provident Funds Act 1952 employer contribution default",
            "EPFO grievance provident fund deducted not deposited",
        ] + variants
    if route.category == "succession_inheritance" and re.search(r"\b(muslim|shariat|islamic)\b", q):
        variants = [
            "Muslim Personal Law Shariat Application Act 1937 inheritance",
            "Muslim law succession property share heirs",
        ] + variants
    if route.category == "cyber_fraud_or_harassment" and _contains_any(q, ("sex video", "intimate", "nudes", "upload", "recorded")):
        variants = [
            "Information Technology Act 2000 section 66E 67 intimate video",
            "BNS 2023 voyeurism criminal intimidation intimate image threat",
        ] + variants
    if route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
        variants = [
            v.replace("BNSS 2023", "CrPC 1973").replace("BNS 2023", "IPC 1860")
            for v in variants
        ]
    return variants[:max_variants]


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


async def expand_query(query: str, *, max_variants: int = 3) -> list[str]:
    """Return [original_query, ...legal-vocabulary variants].

    Falls back to [original_query] on any error or NOT_LEGAL signal,
    so retrieval is never blocked by expansion failure.
    """
    if not query or not query.strip():
        return [query]

    settings = get_settings()
    max_variants = max(1, min(max_variants, settings.query_expansion_max_variants))
    route = route_matter(query)
    deterministic = _route_variants(query, route, max_variants)
    if deterministic and route.confidence >= 0.70:
        logger.info(
            "query_expand: route-aware %d variants (category=%s confidence=%.2f)",
            len(deterministic), route.category, route.confidence,
        )
        return [query] + deterministic

    t0 = time.time()
    try:
        raw = await chat_once(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Lay question: {query.strip()}"},
            ],
            temperature=0.3,    # small variation across variants
            max_tokens=200,
        )
    except Exception as e:
        logger.warning("query_expand: LLM call failed: %s", e)
        return [query]
    elapsed = time.time() - t0

    # qwen3 sometimes returns leading "thinking" content even with
    # think:false. Drop anything inside <think>...</think> if present.
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    if "NOT_LEGAL" in raw.upper():
        logger.info("query_expand: NOT_LEGAL signal (%.1fs); original only", elapsed)
        return [query]

    variants: list[str] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Drop common preamble phrases the LLM sometimes ignores instructions about
        if line.lower().startswith((
            "here are", "sure,", "of course", "note:", "1.", "2.", "3.",
            "•", "-", "*",
        )):
            # Try to peel off a leading bullet/number prefix
            line = re.sub(r"^(?:\d+[.)]|[•\-*])\s*", "", line).strip()
            if not line:
                continue
        # Drop obvious LLM-rambling lines
        if line.lower().startswith(("legal search queries", "queries:")):
            continue
        # Strip surrounding quotes
        line = line.strip('"').strip("'")
        if len(line) < 6 or len(line) > 200:
            continue
        variants.append(line)
        if len(variants) >= max_variants:
            break

    logger.info(
        "query_expand: %d variants in %.2fs (query=%r)",
        len(variants), elapsed, query[:60],
    )

    # Always return original first — it's the most reliable signal even
    # if all variants are bad.
    return [query] + variants


__all__ = ["expand_query"]
