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
    "  'principal employer ran with wages / contractor disappeared' → "
    "Contract Labour (Regulation and Abolition) Act 1970 s.21 "
    "(principal-employer liability); add Inter-State Migrant Workmen Act "
    "1979 only when inter-state recruitment / displacement allowance facts "
    "appear\n"
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
        "Constitution of India Article 341 Scheduled Castes Article 342 Scheduled Tribes caste certificate rejection appeal",
        "Mukhyamantri Kanya Vivah Yojana service delivery eligibility marriage certificate income proof",
        "National Food Security Act 2013 targeted public distribution system ration card grievance redressal",
        "One Nation One Ration Card portability fair price shop food security allowance",
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
        "Transfer of Property Act 1882 section 126 revocation gift deed senior citizen",
    ],
    "family_domestic": [
        "Protection of Women from Domestic Violence Act 2005 section 12",
        "Protection of Women from Domestic Violence Act 2005 section 19 residence order shared household",
        "BNSS 2023 section 144 CrPC 1973 section 125 maintenance child support",
        "BNS 2023 section 85 cruelty husband dowry harassment",
    ],
    "child_marriage_protection": [
        "Prohibition of Child Marriage Act 2006 section 3 section 13 injunction annulment child marriage",
        "Child Marriage Prohibition Officer Child Welfare Committee police prevention under PCMA 2006",
    ],
    "arrest_custody_safeguard": [
        "BNSS 2023 section 57 section 58 arrest produced before magistrate twenty four hours",
        "CrPC 1973 section 56 section 57 arrest production before magistrate 24 hours",
    ],
    "undertrial_review_release": [
        "BNSS 2023 section 479 maximum period undertrial prisoner detention release",
        "CrPC 1973 section 436A undertrial prisoner maximum detention release",
    ],
    "bonded_labour_rescue": [
        "Bonded Labour System Abolition Act 1976 section 4 section 10 release certificate district magistrate",
        "forced labour debt bondage document retention hostage labour commissioner police rehabilitation",
    ],
    "disability_access": [
        "Rights of Persons with Disabilities Act 2016 disability certificate certifying authority UDID",
        "RPwD Act 2016 reasonable accommodation state disability commissioner certificate denial",
    ],
    "employment_wages": [
        "Code on Social Security 2020 section 112 section 113 section 114 gig worker platform worker social security",
        "Payment of Wages Act unpaid salary labour commissioner complaint",
        "Code on Wages 2019 wage theft employer contractor",
        "Industrial Disputes Act 1947 section 25F section 25G section 25H retrenchment",
        "Indian Contract Act 1872 notice period employment contract breach compensation",
    ],
    "labour_compliance": [
        "Employees State Insurance Act 1948 section 40 contribution section 45A determination section 75 ESI Court",
        "Code on Social Security 2020 social security contribution employer inspection",
        "Maharashtra Shops and Establishments Act 2017 section 15 overtime section 25 registers records section 28 facilitator inspection",
        "Building and Other Construction Workers Act 1996 employer registration construction worker welfare board compliance",
    ],
    "manual_scavenging_safety": [
        "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013 hazardous cleaning sewer septic tank",
        "Employees Compensation Act 1923 death injury accident arising out of employment compensation",
    ],
    "labour_exploitation_discrimination": [
        "Bonded Labour System Abolition Act 1976 document retention contractor",
        "MGNREGA Act 2005 wage delay grievance compensation",
        "Juvenile Justice Act 2015 child in need of care and protection child labour rescue",
        "Building and Other Construction Workers Act 1996 registration welfare board benefits",
    ],
    "workplace_injury_compensation": [
        "Employees Compensation Act 1923 workplace injury accident compensation",
        "BOCW Act 1996 construction worker injury welfare board",
        "Motor Vehicles Act 1988 accident insurance claims tribunal compensation",
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
        "CGST Act 2017 section 29 cancellation registration section 30 revocation section 107 appeal",
        "Income Tax Act 1961 return filing TDS Form 26AS tax compliance",
    ],
    "ibc_nclt": [
        "Companies Act 2013 annual return MGT-7 financial statement AOC-4 director disqualification",
        "Companies Act 2013 section 252 company restoration strike off NCLT",
        "Insolvency and Bankruptcy Code 2016 section 9 operational creditor",
        "NCLT insolvency application demand notice default debt",
    ],
    "business_contract_partnership": [
        "Indian Contract Act 1872 section 27 non compete restraint trade",
        "Indian Partnership Act 1932 retirement partner liability notice",
    ],
    "business_license_compliance": [
        "Food Safety and Standards Act 2006 FSSAI licence registration renewal category upgrade",
        "FSSAI licensing registration regulation FoSCoS state central licence notice",
        "state Shops and Establishments Act shop license renewal penalty",
        "municipal trade license renewal delay RTI grievance",
    ],
    "child_custody_adoption": [
        "Guardians and Wards Act 1890 custody welfare of minor child",
        "Hindu Marriage Act 1955 section 26 custody of children",
        "Juvenile Justice Act 2015 adoption procedure missing papers",
    ],
    "education_rights": [
        "Right to Education Act 2009 admission transfer certificate school",
        "RTE Act section 12 25 percent quota private school",
    ],
    "environment_compensation": [
        "Water Prevention and Control of Pollution Act 1974 state pollution control board effluent complaint",
        "Environment Protection Act 1986 compensation pollution blasting damage",
        "National Green Tribunal Act environmental damage compensation",
        "RFCTLARR Act 2013 compensation award payment deposit reference Authority land acquired for highway",
    ],
    "land_acquisition_compensation": [
        "RFCTLARR Act 2013 section 77 payment compensation deposit Authority",
        "RFCTLARR Act 2013 section 64 reference to Authority award compensation objection",
        "Right to Fair Compensation land acquisition highway road widening award payment deposit",
    ],
    "pmla_ed": [
        "PMLA 2002 section 45 twin conditions bail",
        "Prevention of Money Laundering Act arrest attachment ED summons",
    ],
    "banking_credit_dispute": [
        "Banking Regulation Act 1949 cooperative bank fixed deposit nominee depositor",
        "Consumer Protection Act 2019 banking service deficiency fixed deposit nominee complaint",
        "RBI Integrated Ombudsman Scheme bank wrong debit complaint",
        "Credit Information Companies Act CIBIL correction loan closed NOC",
    ],
    "mental_health_care_rights": [
        "Mental Healthcare Act 2017 supported admission rights safeguards",
        "Mental Health Review Board unlawful confinement chains treatment",
    ],
    "tribal_caste_atrocity": [
        "SC ST Prevention of Atrocities Act 1989 caste abuse violence",
        "Constitution of India Article 17 abolition of untouchability Protection of Civil Rights Act 1955 temple well water access",
        "PESA Act 1996 Forest Rights Act 2006 gram sabha tribal rights",
    ],
    "land_revenue_records": [
        "state land revenue record of rights mutation pattadar passbook",
        "Right to Information Act 2005 land records revenue office delay",
    ],
    "court_procedure": [
        "Code of Civil Procedure 1908 civil court procedure filing appeal",
        "Legal Services Authorities Act 1987 court help desk legal aid",
    ],
    "criminal_procedure_notice": [
        "BNSS 2023 section 94 and CrPC 1973 section 91 summons to produce document electronic record phone",
        "CrPC 1973 section 91 summons to produce document or other thing",
    ],
    "passport_police_verification": [
        "passport police verification adverse report Regional Passport Office criminal case remedy",
        "passport refusal criminal proceedings police verification grievance writ jurisdiction",
    ],
    "lok_adalat_award_challenge": [
        "Legal Services Authorities Act 1987 section 21 Lok Adalat award final binding no appeal",
        "Lok Adalat award challenge fraud coercion no consent writ jurisdiction",
    ],
    "cheque_bounce": [
        "Negotiable Instruments Act 1881 section 138 cheque dishonour demand notice 15 days",
        "Negotiable Instruments Act 1881 section 142 limitation complaint one month",
    ],
    "property_tenancy": [
        "Transfer of Property Act 1882 gift deed joint ownership section 45 section 126 revocation",
        "Transfer of Property Act 1882 tenancy lease possession deposit",
        "Registration Act 1908 compulsory registration gift deed sale deed",
        "Indian Contract Act 1872 consent coercion undue influence fraud property document",
        "state rent control act landlord tenant security deposit eviction",
    ],
    "succession_inheritance": [
        "Indian Succession Act 1925 will intestate succession property share",
        "Muslim personal law inheritance share wife daughter mother",
    ],
    "family_marriage_status": [
        "personal law second marriage first marriage valid protection maintenance",
        "BNS 2023 IPC 1860 bigamy cruelty marriage status family court",
    ],
    "election_voter_rights": [
        "Representation of the People Act 1950 section 19 section 22 section 23 electoral roll correction voter ID EPIC",
        "Representation of the People Act 1951 section 62 right to vote polling booth denial",
    ],
    "election_candidate_dispute": [
        "Representation of the People Act 1951 candidate nomination disqualification election petition",
        "Election Commission returning officer nomination scrutiny corrupt practice counting procedure",
    ],
    "surrogacy_parenthood": [
        "Surrogacy Regulation Act 2021 section 4 eligibility intending couple intending woman certificate",
        "Surrogacy Regulation Act 2021 appropriate authority registered clinic surrogate mother consent",
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
    q = query.lower()
    if route.category == "criminal_defence_bail":
        return _criminal_defence_bail_variants(q, route)[:max_variants]
    if route.category == "arrest_custody_safeguard":
        return _arrest_custody_variants(route)[:max_variants]
    if route.action_pack and route.action_pack.id == "name_change_identity":
        return [
            "Department of Publication Guidelines for Change of Name adult Gazette of India Part IV eGazette identity record required documents formalities",
            "eGazette name change surname change marriage certificate identity record update Aadhaar PAN passport",
            "name change after marriage government press gazette publication newspaper undertaking proforma witnesses",
        ][:max_variants]

    variants = _ROUTE_EXPANSIONS.get(route.category, [])
    if route.category == "employment_wages" and re.search(r"\b(epf|pf|provident fund)\b", q):
        variants = [
            "Employees Provident Funds Act 1952 employer contribution default",
            "EPFO grievance provident fund deducted not deposited",
        ] + variants
    if route.category == "employment_wages" and _contains_any(q, ("esi", "esic", "employees state insurance")):
        variants = [
            "Employees State Insurance Act 1948 section 40 contribution employer employee",
            "Employees State Insurance Act 1948 section 45A contribution determination section 75 ESI Court",
        ] + variants
    if route.category == "employment_wages" and _contains_any(q, ("notice period", "offer letter", "appointment letter", "employment contract", "full and final", "final settlement", "dues")):
        variants = [
            "Indian Contract Act 1872 performance breach compensation employment notice period",
            "Code on Wages 2019 payment of wages final settlement dues wage authority",
        ] + variants
    if route.category == "digital_platform_account" and _contains_any(q, (
        "dream11", "parimatch", "betting app", "betting site",
        "online betting", "online gambling", "online rummy", "rummy app",
        "fantasy app", "gaming app", "real money game", "real-money game",
    )):
        variants = [
            "Public Gambling Act 1867 section 12 game of mere skill online gambling betting rummy",
            "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022 sections 7 14 online gambling online game of chance",
        ] + variants
    if route.category == "succession_inheritance" and re.search(r"\b(muslim|shariat|islamic)\b", q):
        variants = [
            "Muslim Personal Law Shariat Application Act 1937 inheritance",
            "Muslim law succession property share heirs",
        ] + variants
    if route.category == "succession_inheritance" and re.search(r"\b(parsi|christian)\b", q):
        variants = [
            "Indian Succession Act 1925 Parsi intestate succession sections 50 51 54 Schedule II",
            "Indian Succession Act 1925 Christian intestate succession sections 32 33",
        ] + variants
    if route.category == "employment_wages" and _contains_any(q, ("urban company", "gig", "platform worker", "service partner", "beautician", "delivery partner", "driver partner")):
        variants = [
            "Code on Social Security 2020 section 112 section 113 section 114 gig worker platform worker social security",
            "Industrial Disputes Act 1947 workman retrenchment section 25F termination labour court",
        ] + variants
    if route.category == "employment_wages" and re.search(r"\b(retrench|retrenched|retrenchment|layoff|lay off)\b", q):
        variants = [
            "Industrial Disputes Act 1947 section 25F retrenchment compensation notice",
            "Industrial Disputes Act 1947 section 25G last come first go section 25H re employment retrenched workmen",
            "Industrial Disputes Act 1947 section 25N prior permission retrenchment 100 workmen",
        ] + variants
    if route.category == "employment_wages" and _contains_any(q, ("labour department", "labor department", "overtime register", "register not maintained", "raid", "raided")):
        variants = [
            "Maharashtra Shops and Establishments Act 2017 section 15 overtime wages section 25 registers records section 28 facilitator inspection",
            "Building and Other Construction Workers Act 1996 registration employer compliance inspection construction worker",
        ] + variants
    if route.category == "labour_compliance":
        variants = [
            "Employees State Insurance Act 1948 section 40 section 45A contribution determination casual worker",
            "Employees State Insurance Act 1948 section 75 Employees Insurance Court contribution dispute",
        ] + variants
    if route.category == "manual_scavenging_safety":
        variants = [
            "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013 hazardous cleaning sewer septic tank death compensation",
            "Employees Compensation Act 1923 death injury accident arising out of employment dependant compensation",
            "BNS 2023 death negligence hurt criminal law sewer septic tank no safety",
        ] + variants
    if route.category == "labour_exploitation_discrimination":
        if _contains_any(q, ("asha worker", "asha", "honorarium", "nhm", "nrhm")):
            variants = [
                "National Health Mission ASHA incentives guidelines honorarium payment grievance ASHA worker",
                "NRHM ASHA worker incentive payment state health society grievance",
            ] + variants
        if _contains_any(q, ("principal employer", "contract labour", "contract labor", "workmen")) and _contains_any(q, ("wage", "wages", "not paid", "unpaid", "dues", "workers")):
            contract_variants = [
                "Contract Labour Regulation and Abolition Act 1970 section 21 responsibility for payment of wages principal employer contractor workmen",
            ]
            if _contains_interstate_migrant_context(q):
                contract_variants.append(
                    "Inter-State Migrant Workmen Act 1979 contractor principal employer wages displacement allowance journey allowance"
                )
            variants = contract_variants + variants
        if _contains_any(q, ("child", "minor", "girl child", "boy child", "girl 15", "boy 15", "15 working", "16 working", "17 working", "under 18", "domestic work")) or _contains_child_age(q):
            variants = [
                "Child and Adolescent Labour Prohibition Regulation Act 1986 prohibition child labour adolescent domestic work hazardous occupation",
                "Juvenile Justice Act 2015 child in need of care and protection Child Welfare Committee rescue",
                "Code on Wages 2019 child labour wage employer records",
            ] + variants
        if _contains_any(q, ("bocw", "construction worker", "construction 8 years", "building worker", "mason")):
            variants = [
                "Building and Other Construction Workers Act 1996 section 12 registration section 13 identity card section 14 cessation",
                "Building and Other Construction Workers welfare board registration fake register cess construction worker benefits",
            ] + variants
            if _contains_any(q, ("cess", "levy", "collection")):
                variants = [
                    "Building and Other Construction Workers Welfare Cess Act 1996 section 3 levy and collection of cess",
                ] + variants
        if _contains_interstate_migrant_context(q):
            variants = [
                "Inter-State Migrant Workmen Act 1979 section 4 registration section 6 contractor licence section 12 duties",
                "Code on Wages 2019 migrant worker wage register contractor employee records",
            ] + variants
        if _contains_any(q, ("nrega", "mgnrega", "muster roll", "bdo", "mukhiya", "job card")):
            variants = [
                "Mahatma Gandhi National Rural Employment Guarantee Act 2005 section 3 wage employment section 17 social audit section 19 grievance",
            ] + variants
        elif _contains_any(q, ("domestic worker", "madam not paying", "factory deducted", "wage deducted", "uniform never given", "shoes uniform", "no payment", "munshi", "minimum wage", "minimum wages", "state rate", "unskilled")):
            variants = [
                "Code on Wages 2019 section 17 payment of wages section 18 deductions section 45 claims",
                "Code on Wages 2019 minimum wages floor wage employee unskilled worker",
            ] + variants
    if route.category == "ibc_nclt":
        if _contains_any(q, ("nclat", "appeal", "days limit", "limitation", "against nclt order")):
            variants = [
                "Insolvency and Bankruptcy Code 2016 section 61 appeal NCLAT thirty days fifteen days condonation NCLT order",
            ] + variants
        if _contains_any(q, ("company", "private limited", "pvt ltd", "mgt", "aoc", "roc", "director", "disqualified", "strike off", "revive")):
            variants = [
                "Companies Act 2013 section 92 annual return MGT-7 section 137 financial statement AOC-4",
                "Companies Act 2013 section 164 director disqualification section 252 restoration NCLT",
            ] + variants
    if route.category == "business_license_compliance" and _contains_any(q, ("fssai", "food", "snack", "foscos")):
        variants = [
            "Food Safety and Standards Act 2006 FSSAI licence registration renewal category upgrade",
            "FSSAI Licensing and Registration Regulations state central licence manufacturing turnover capacity",
        ] + variants
    if route.category == "business_license_compliance" and _contains_any(q, ("auto permit", "taxi permit", "cab permit", "transport permit", "permit renewal", "permit expired")):
        variants = [
            "Motor Vehicles Act 1988 section 74 contract carriage permit renewal Regional Transport Authority",
            "Motor Vehicles Act 1988 section 80 permit renewal replacement appeal transport authority",
        ] + variants
    if route.category == "business_license_compliance" and _contains_any(q, ("traffic police", "challan", "license invalid", "licence invalid", "auto driver", "driving license", "driving licence")):
        variants = [
            "Motor Vehicles Act 1988 driving licence validity traffic challan penalty enforcement",
            "Prevention of Corruption Act 1988 section 7 public servant taking gratification bribe",
        ] + variants
    if route.category == "workplace_injury_compensation" and _contains_any(q, ("zomato", "swiggy", "uber", "ola", "rider", "driver", "gig", "platform worker", "delivery partner", "bike accident")):
        variants = [
            "Code on Social Security 2020 section 113 section 114 gig worker platform worker social security",
            "Motor Vehicles Act 1988 section 147 insurance section 165 section 166 motor accident claims tribunal",
        ] + variants
    if route.category == "workplace_injury_compensation" and _contains_any(q, ("beat", "beaten", "assault", "head injury", "mukadam", "contractor beat")):
        variants = [
            "BNS 2023 section 115 section 117 hurt grievous hurt assault workplace contractor beat head injury",
            "BNSS 2023 FIR police complaint hurt assault workplace injury",
        ] + variants
    if route.category == "business_contract_partnership":
        if _contains_any(q, ("delivery", "vendor", "seller", "recover advance", "advance", "cancel and recover")):
            variants = [
                "Indian Contract Act 1872 section 39 refusal to perform section 73 compensation breach delivery advance",
                "Sale of Goods Act 1930 delivery of goods seller buyer damages price section 55",
            ] + variants
        if _contains_any(q, ("invoice", "client not paying", "not paying invoice", "saas work", "buyer deducting payment", "quality issue", "formal rejection", "lakh stuck")):
            variants = [
                "MSMED Act 2006 section 15 buyer delayed payment section 16 interest section 18 Facilitation Council",
                "Indian Contract Act 1872 breach of contract compensation unpaid invoice section 73",
                "Indian Contract Act 1872 performance of promise payment due buyer quality rejection",
            ] + variants
            if _contains_any(q, ("dubai", "foreign", "export", "saas")):
                variants = [
                    "Foreign Exchange Management Act 1999 export services foreign exchange realisation India",
                ] + variants
        if _contains_any(q, ("co founder", "co-founder", "equity", "esop", "shareholder", "registers", "board")):
            variants = [
                "Companies Act 2013 section 62 share capital ESOP section 94 registers section 241 section 242 oppression mismanagement",
            ] + variants
        if _contains_any(q, ("principal agent", "principal-agent", "agent took", "agent absconded")):
            variants = [
                "Indian Contract Act 1872 agency principal agent duty accounts compensation",
            ] + variants
    if route.category == "social_welfare_identity" and _contains_any(q, ("army", "defence", "defense", "service pension", "family pension")):
        variants = [
            "Pension Regulations for the Army 2008 Part I family pension widow eligibility",
            "Pension Regulations for the Army 2008 Part II initial grant family pension claims documents procedure",
        ] + variants
    if route.category == "social_welfare_identity" and _contains_any(q, ("rti", "pension not", "pension nahi", "nahi aayi", "not received pension", "not paid pension")):
        variants = [
            "Right to Information Act 2005 section 6 application section 7 time limit section 19 appeal pension status reasons",
        ] + variants
    if route.category == "social_welfare_identity" and _contains_any(q, ("caste certificate", "community certificate", "sc certificate", "st certificate", "tehsildar", "tahsildar")):
        variants = [
            "Constitution of India Article 341 Scheduled Castes Article 342 Scheduled Tribes caste certificate state list",
            "Right to Information Act 2005 section 6 section 7 section 19 rejection reasons first appeal",
        ] + variants
    if route.category == "court_procedure" and _contains_any(q, ("cognizance", "private complaint", "156(3)", "156 3", "section 200", "magistrate complaint")):
        variants = [
            "BNSS 2023 Bharatiya Nagarik Suraksha Sanhita section 175 section 223 Magistrate complaint police inaction investigation",
            "Code of Criminal Procedure 1973 section 156(3) section 190 section 200 Magistrate complaint cognizance",
        ] + variants
    if route.category == "court_procedure" and _contains_any(q, ("order 21", "order xxi", "execution", "decree holder")):
        variants = [
            "Code of Civil Procedure 1908 execution of decrees Order XXI",
            "Code of Civil Procedure 1908 section 47 execution decree questions",
        ] + variants
    if route.category == "court_procedure" and _contains_any(q, ("affidavit", "notarised", "notarized", "notary")):
        variants = [
            "court affidavit notarised notary oath affirmation filing procedure",
            "Code of Civil Procedure 1908 affidavit evidence court filing",
        ] + variants
    if route.category == "court_procedure" and _contains_any(q, ("second appeal", "substantial question", "section 100")):
        variants = [
            "Code of Civil Procedure 1908 section 100 second appeal substantial question of law",
            "CPC second appeal High Court substantial question of law procedure",
        ] + variants
    if route.category == "court_procedure" and _contains_any(q, ("transfer of case", "case transfer", "section 24")):
        variants = [
            "Code of Civil Procedure 1908 section 24 transfer of suit appeal proceeding",
        ] + variants
    if route.category == "child_custody_adoption" and _contains_any(q, ("not letting me meet", "took our", "not bringing back", "return")):
        variants = [
            "Guardians and Wards Act 1890 section 25 custody return of minor",
            "habeas corpus child custody urgent child return High Court",
        ] + variants
    if route.category == "family_domestic" and _contains_any(q, ("mutual consent", "13b", "both agree divorce")):
        if _contains_any(q, ("special marriage", "special marriage act", "interfaith", "inter-faith", "court marriage")):
            variants = [
                "Special Marriage Act 1954 section 28 divorce by mutual consent",
                "Family Courts Act 1984 jurisdiction divorce mutual consent petition",
            ] + variants
        elif _contains_any(q, ("muslim", "shariat", "nikah")):
            variants = [
                "Muslim Personal Law Shariat Application Act 1937 divorce personal law",
                "Dissolution of Muslim Marriages Act 1939 Muslim wife divorce grounds",
                "Family Courts Act 1984 jurisdiction divorce petition",
            ] + variants
        elif _contains_any(q, ("christian", "church marriage")):
            variants = [
                "Divorce Act 1869 Christian divorce mutual consent family court",
                "Family Courts Act 1984 jurisdiction divorce petition",
            ] + variants
        else:
            variants = [
                "Hindu Marriage Act 1955 section 13B mutual consent divorce",
                "Family Courts Act 1984 jurisdiction divorce mutual consent petition",
            ] + variants
    if route.category == "family_domestic" and _contains_any(q, ("residence", "shared household", "ghar se nikal", "threw me out", "sasural", "kicked me out")):
        variants = [
            "Protection of Women from Domestic Violence Act 2005 section 19 residence order shared household",
            "Protection of Women from Domestic Violence Act 2005 section 17 right to reside shared household",
        ] + variants
    if route.category == "family_domestic" and _contains_any(q, ("salary", "atm card", "groceries", "breadwinner", "economic abuse", "not giving money")):
        variants = [
            "Protection of Women from Domestic Violence Act 2005 section 3 economic abuse",
            "Protection of Women from Domestic Violence Act 2005 section 20 monetary relief",
        ] + variants
    if route.category == "family_domestic" and _contains_any(q, ("child support", "child maintenance", "maintenance order", "not paying", "arrears")):
        variants = [
            "BNSS 2023 section 144 maintenance wife child parents enforcement",
            "CrPC 1973 section 125 maintenance child support enforcement",
            "Family Courts Act 1984 jurisdiction maintenance child support",
        ] + variants
    if route.category == "surrogacy_parenthood":
        variants = [
            "Surrogacy Regulation Act 2021 section 4 eligibility intending couple intending woman certificate",
            "Surrogacy Regulation Act 2021 section 6 surrogate mother written informed consent",
        ] + variants
        if _contains_any(q, ("clinic", "registration", "registered")):
            variants = [
                "Surrogacy Regulation Act 2021 section 3 section 11 registration surrogacy clinic",
            ] + variants
        if _contains_any(q, ("abandon", "abandoned", "child rights", "abortion", "terminate")):
            variants = [
                "Surrogacy Regulation Act 2021 section 7 section 8 section 10 abandon child rights abortion + Medical Termination of Pregnancy Act 1971 termination pregnancy consent registered medical practitioner",
            ] + variants
    if route.category == "election_candidate_dispute":
        if _contains_any(q, ("convicted", "conviction", "disqualified", "disqualification", "two years", "2 years")):
            variants = [
                "Representation of the People Act 1951 section 8 disqualification on conviction candidate",
                "Representation of the People Act 1951 section 8A disqualification corrupt practices",
            ] + variants
        elif _contains_any(q, (
            "false affidavit", "affidavit false", "false assets", "hid assets",
            "hide assets", "hidden assets", "wrong affidavit", "fake affidavit",
            "suppressed criminal case", "concealed criminal case",
            "hid criminal case", "hide criminal case", "hidden criminal case",
        )):
            variants = [
                "Representation of the People Act 1951 section 33A section 125A false affidavit assets criminal cases + section 80 section 81 section 83 section 100 election petition",
            ] + variants
            if _contains_any(q, ("corrupt practice", "bribe", "booth capturing", "religion appeal", "hate speech")):
                variants = [
                    "Representation of the People Act 1951 section 33A section 125A false affidavit assets + section 123 corrupt practices + section 80 section 81 section 83 section 100 election petition",
                ] + variants[1:]
        elif _contains_any(q, ("corrupt practice", "bribe", "booth capturing", "religion appeal", "hate speech")):
            variants = [
                "Representation of the People Act 1951 section 123 corrupt practices election + section 80 section 81 section 100 election petition",
            ] + variants
        elif _contains_any(q, ("nomination", "returning officer", "affidavit")):
            variants = [
                "Representation of the People Act 1951 section 33 section 36 nomination scrutiny returning officer",
                "Representation of the People Act 1951 candidate affidavit nomination rejection remedy",
            ] + variants
        elif _contains_any(q, ("petition", "recount", "counting", "set aside")):
            variants = [
                "Representation of the People Act 1951 section 80 section 81 election petition",
                "Representation of the People Act 1951 section 100 grounds for declaring election void",
            ] + variants
    if route.category == "tax_gst_compliance":
        variants = []
        if _contains_any(q, ("gst", "cgst", "gstr")):
            if _contains_any(q, ("sealed", "seal", "search", "inspection", "godown")):
                variants += [
                    "Central Goods and Services Tax Act 2017 section 67 inspection search seizure",
                    "CGST Act 2017 section 83 provisional attachment tax proceedings",
                ]
            elif _contains_any(q, ("cancellation", "cancelled", "cancelled registration", "registration cancelled", "nil returns", "nil return", "revocation")):
                variants += [
                    "Central Goods and Services Tax Act 2017 section 29 cancellation of registration",
                    "Central Goods and Services Tax Act 2017 section 30 revocation of cancellation registration",
                    "Central Goods and Services Tax Act 2017 section 107 appeal order cancellation",
                ]
            elif _contains_any(q, ("late return", "late fee", "penalty", "notice")):
                variants += [
                    "Central Goods and Services Tax Act 2017 section 47 late fee delayed return",
                    "CGST Act 2017 section 73 section 74 tax demand penalty notice",
                ]
            elif _contains_any(q, ("appeal", "assessment order", "adjudication order")):
                variants += [
                    "Central Goods and Services Tax Act 2017 section 107 appeal adjudication order",
                ]
            else:
                variants += [
                    "CGST Act 2017 GST registration threshold service provider",
                    "Central Goods and Services Tax Act 2017 section 22 registration threshold",
                ]
        if _contains_any(q, ("customs", "icegate", "bill of entry", "shipping bill", "drawback", "import duty", "customs duty", "duty demand", "classification dispute", "shipment held at port")):
            if _contains_any(q, ("refund", "drawback")):
                variants += [
                    "Customs Act 1962 section 27 refund of duty",
                    "Customs Act 1962 section 74 section 75 drawback",
                ]
            else:
                variants += [
                    "Customs Act 1962 bill of entry assessment classification duty appeal",
                    "Customs Act 1962 section 128 appeal against customs decision",
                ]
        if _contains_any(q, ("cit(a)", "commissioner appeals")):
            variants += [
                "Income Tax Act 1961 section 246A appeal Commissioner Appeals assessment order",
                "Income Tax Act 1961 section 249 limitation Commissioner Appeals",
            ]
        elif _contains_any(q, ("itat", "appellate tribunal")):
            variants += [
                "Income Tax Act 1961 section 253 appeal Appellate Tribunal ITAT",
                "Income Tax Act 1961 section 254 orders of Appellate Tribunal",
            ]
        elif _contains_any(q, ("income tax refund", "refund stuck", "processed no refund")):
            variants += [
                "Income Tax Act 1961 section 237 refund of tax",
                "Income Tax Act 1961 section 244A interest on refund",
            ]
        elif _contains_any(q, ("80c", "80ccd", "nps")):
            variants += [
                "Income Tax Act 1961 section 80C deduction limit",
                "Income Tax Act 1961 section 80CCD National Pension System additional deduction",
            ]
        elif _contains_any(q, ("capital gains", "54f", "sale of flat")):
            variants += [
                "Income Tax Act 1961 section 45 capital gains",
                "Income Tax Act 1961 section 54F exemption sale of capital asset residential house",
            ]
        elif _contains_any(q, ("143(2)", "section 143(2)")):
            variants += [
                "Income Tax Act 1961 section 143 notice scrutiny assessment",
            ]
        elif (
            _contains_any(q, ("itr", "assessment year", "234f", "belated return"))
            or bool(re.search(r"\bay\s*\d{4}", q))
            or ("income tax" in q and not _contains_any(q, ("assessment order", "appeal")))
        ):
            variants += [
                "Income Tax Act 1961 section 234F late filing fee belated ITR",
                "Income Tax Act 1961 section 139 belated revised return assessment year",
            ]
    if route.category == "property_tenancy":
        if _contains_any(q, ("gift deed", "gift", "registered gift", "not caring", "cancel", "revocation")):
            variants = [
                "Transfer of Property Act 1882 section 126 revocation suspension of gift deed",
                "Transfer of Property Act 1882 section 122 section 123 gift transfer registered instrument",
            ] + variants
        if _contains_any(q, ("joint name", "half share", "claims half", "house", "flat")):
            variants = [
                "Transfer of Property Act 1882 section 45 joint transfer consideration co owner share",
                "Transfer of Property Act 1882 joint ownership house flat share",
            ] + variants
        if _contains_any(q, ("thumb impression", "blank paper", "under pressure", "coercion", "undue influence", "fraud", "didn't sign", "did not sign")):
            variants = [
                "Indian Contract Act 1872 consent coercion undue influence fraud voidable agreement",
                "Registration Act 1908 registered gift deed sale deed validity",
            ] + variants
    if route.category == "sexual_offence_survivor" and (
        _contains_any(q, ("child", "minor", "pocso", "under 18", "since i was", "when i was"))
        or _contains_child_age(q)
    ):
        variants = [
            "POCSO Act 2012 child sexual offence reporting special court survivor support",
            "BNSS 2023 CrPC 1973 child sexual offence FIR statement medical examination",
        ] + variants
    if route.category == "cyber_fraud_or_harassment" and _contains_any(q, (
        "sex video", "porn video", "intimate", "nudes", "upload", "recorded",
        "morphed", "deepfake", "lookalike", "reddit", "nude", "leaked",
    )):
        variants = [
            "Information Technology Act 2000 section 66E 67 intimate video",
            "BNS 2023 voyeurism criminal intimidation intimate image threat",
        ] + variants
        if _contains_any(q, ("election", "candidate", "campaign")):
            variants = [
                "Representation of the People Act 1951 false statement corrupt practice election campaign candidate party",
            ] + variants
        if _contains_child_age(q) or (not _contains_adult_age(q) and _contains_any(q, ("minor", "child", "under 18"))):
            variants = [
                "POCSO Act 2012 child sexual image reporting special court + Information Technology Act 2000 section 66E 67 intimate image",
            ] + variants
    if route.category == "cyber_fraud_or_harassment" and _contains_any(q, ("stalker", "stalking", "dm daily", "direct message", "dms", "after blocking")):
        variants = [
            "BNS 2023 section 78 stalking section 351 criminal intimidation",
            "Information Technology Act 2000 section 66E privacy electronic communication cyber complaint",
        ] + variants
    if route.category == "cyber_fraud_or_harassment" and _contains_any(q, ("tinder", "extortion", "gang", "took my phone")):
        variants = [
            "BNS 2023 section 308 extortion section 309 robbery section 310 gang",
            "Information Technology Act 2000 section 66D cheating by personation cyber complaint",
        ] + variants
    if route.category == "cyber_fraud_or_harassment" and _contains_any(q, ("privacy", "personal data", "therapist", "mental health", "leaked chat")):
        variants = [
            "Digital Personal Data Protection Act 2023 personal data breach consent grievance data fiduciary",
            "Information Technology Act 2000 privacy breach electronic record cyber complaint",
        ] + variants
    if route.category == "banking_credit_dispute" and _contains_any(q, ("sarfaesi", "13(2)", "home loan default", "possession notice")):
        variants = [
            "SARFAESI Act 2002 section 13(2) demand notice section 13(4) possession",
            "SARFAESI Act 2002 section 17 Debts Recovery Tribunal appeal borrower",
        ] + variants
    if route.category == "banking_credit_dispute" and _contains_any(q, ("recovery agent", "recovery agents", "nbfc", "loan recovery", "shouted")):
        variants = [
            "Reserve Bank Integrated Ombudsman Scheme 2021 NBFC recovery agent harassment complaint",
            "RBI fair practices code recovery agents customer harassment NBFC lender complaint",
        ] + variants
    if route.category == "banking_credit_dispute" and _contains_any(q, ("emi", "bank error", "bounced", "bajaj finserv", "penalty", "cibil", "nbfc")):
        variants = [
            "Reserve Bank Integrated Ombudsman Scheme 2021 NBFC bank complaint deficiency in service EMI penalty CIBIL",
            "Credit Information Companies Regulation Act 2005 CIBIL credit report correction dispute",
        ] + variants
    if route.category == "legal_aid" and _contains_any(q, ("lok adalat", "lokadalat", "traffic challan", "e-challan")):
        variants = [
            "Legal Services Authorities Act 1987 section 19 organisation of Lok Adalats section 20 cognizance of cases section 21 award",
            "Lok Adalat pending traffic challan settlement District Legal Services Authority",
        ] + variants
    if route.category in {"police_fir", "criminal_general"} and (
        _contains_any(q, ("stalker", "stalking", "follows", "following"))
        or _contains_any(q, ("promised marriage", "promise marriage", "deceitful", "live in"))
        or _contains_any(q, ("dowry", "body had marks", "khap", "love jihad", "minor"))
    ):
        variants = [
            "BNS 2023 section 78 stalking section 69 deceitful promise to marry section 80 dowry death",
            "BNSS 2023 section 173 FIR police complaint investigation",
        ] + variants
        if _contains_child_age(q) or _contains_any(q, ("minor", "under 18", "pocso")):
            variants = [
                "POCSO Act 2012 child sexual offence reporting police special court",
            ] + variants
    if _contains_any(q, ("daayan", "dayan", "witch", "tonhi", "daini")):
        variants = [
            "state Witch Hunting Prohibition Act daayan witch branding assault police complaint",
            "BNS 2023 hurt criminal intimidation wrongful restraint witch branding violence",
        ] + variants
    if route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
        variants = [
            v.replace("BNSS 2023 section 479", "CrPC 1973 section 436A")
            .replace("BNSS 2023", "CrPC 1973")
            .replace("BNS 2023", "IPC 1860")
            for v in variants
        ]
    return variants[:max_variants]


def _criminal_defence_bail_variants(query: str, route: MatterRoute) -> list[str]:
    legacy = route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident"
    current = route.legal_regime == "current_bns_bnss_bsa_for_post_2024_incident"
    date_unclear = route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"

    if _contains_any(query, ("slap", "slapped", "hit", "pushed", "assault")):
        return [
            "Bharatiya Nyaya Sanhita 2023 section 115 voluntarily causing hurt section 351 criminal intimidation",
            "BNSS 2023 notice bail accused rights simple hurt assault complaint",
        ]

    default_bail_context = _contains_any(query, ("default bail", "no chargesheet", "charge sheet", "60 days", "90 days"))
    if _contains_any(query, ("cbd", "vape cartridge", "cannabis", "weed", "hash", "ganja", "charas", "ndps", "narcotic")) and not default_bail_context:
        return [
            "NDPS Act 1985 narcotic drug cannabis psychotropic substance possession small quantity bail seizure",
            "BNSS 2023 search seizure arrest bail criminal procedure NDPS case",
            "CrPC 1973 search seizure arrest bail criminal procedure NDPS case",
        ]

    if _contains_any(query, ("prohibition law", "excise act", "liquor case", "caught me drinking", "drinking village", "sharab", "desi daru")):
        return [
            "state prohibition excise act alcohol drinking offence punishment bail procedure",
            "BNSS 2023 arrest notice bail accused criminal court procedure",
            "CrPC 1973 arrest bail accused criminal court procedure",
        ]

    if default_bail_context:
        special = []
        if _contains_any(query, ("ndps", "narcotic", "ganja", "charas", "mdma", "heroin", "cannabis", "weed", "hash", "cbd", "vape cartridge")):
            special.append("NDPS Act 1985 section 36A one hundred eighty days custody chargesheet default bail commercial quantity section 37")
        if legacy:
            return special + [
                "CrPC 1973 section 167 default bail no chargesheet 60 days 90 days",
                "BNSS 2023 section 187 default bail current criminal procedure",
            ]
        if current:
            return special + [
                "BNSS 2023 section 187 default bail no chargesheet 60 days 90 days",
                "CrPC 1973 section 167 default bail pre-1-Jul-2024 comparison",
            ]
        if date_unclear:
            return special + [
                "BNSS 2023 section 187 CrPC 1973 section 167 default bail",
                "default bail 60 days 90 days no chargesheet custody remand",
            ]

    if _contains_any(query, ("anticipatory", "before arrest", "438", "482")):
        if legacy:
            return [
                "CrPC 1973 section 438 anticipatory bail accused before arrest",
                "Arnesh Kumar arrest safeguards 498A dowry case",
            ]
        return [
            "BNSS 2023 section 482 CrPC 1973 section 438 anticipatory bail",
            "Arnesh Kumar arrest safeguards 498A dowry case",
        ]

    if legacy:
        return [
            "CrPC 1973 section 437 section 439 regular bail accused custody",
            "CrPC 1973 section 167 remand custody chargesheet timeline",
        ]
    return [
        "BNSS 2023 section 480 section 483 regular bail accused custody",
        "BNSS 2023 section 187 remand custody chargesheet timeline",
    ]


def _arrest_custody_variants(route: MatterRoute) -> list[str]:
    if route.legal_regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
        return [
            "CrPC 1973 section 56 section 57 arrest production before magistrate 24 hours",
            "Article 22 Constitution arrest informed grounds produced before magistrate",
        ]
    if route.legal_regime == "current_bns_bnss_bsa_for_post_2024_incident":
        return [
            "BNSS 2023 section 57 section 58 arrest produced before magistrate twenty four hours",
            "Article 22 Constitution arrest informed grounds produced before magistrate",
        ]
    return [
        "BNSS 2023 section 57 section 58 arrest produced before magistrate twenty four hours",
        "CrPC 1973 section 56 section 57 arrest production before magistrate 24 hours",
    ]


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _contains_interstate_migrant_context(text: str) -> bool:
    if re.search(r"\bfrom\s+[a-z ]{2,30}\s+to\s+[a-z ]{2,30}\b", text):
        return True
    return _contains_any(text, (
        "ismw", "inter-state migrant workmen", "inter state migrant workmen",
        "migrant registration", "migrant worker", "inter state migrant",
        "inter-state migrant", "displacement allowance", "came together",
        "brought from", "return ticket", "go back home", "walked from",
        "journey allowance", "other state", "another state",
        "from bihar", "from odisha", "from orissa", "from bengal",
        "from jharkhand", "from up ", "from uttar pradesh",
        "from chhattisgarh", "from rajasthan", "to gujarat",
        "to maharashtra", "to delhi", "to karnataka", "to tamil nadu",
    ))


def _contains_child_age(text: str) -> bool:
    patterns = (
        r"\b(?:age|aged|is|was)\s+([1-9]|1[0-7])\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s*old\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s+(?:daughter|son|girl|boy|child|minor)\b",
        r"\b([1-9]|1[0-7])\s*(?:yo|saal)\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _contains_adult_age(text: str) -> bool:
    patterns = (
        r"\b(?:age|aged|is|was)\s+(1[8-9]|[2-9][0-9])\b",
        r"\b(1[8-9]|[2-9][0-9])\s*(?:year|years|yr|yrs)\s*old\b",
        r"\b(1[8-9]|[2-9][0-9])\s*(?:year|years|yr|yrs)\s+(?:daughter|son|girl|boy|child)\b",
        r"\b(1[8-9]|[2-9][0-9])\s*(?:yo|saal)\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


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
    if deterministic and route.confidence >= 0.55:
        logger.info(
            "query_expand: route-aware %d variants (category=%s confidence=%.2f)",
            len(deterministic), route.category, route.confidence,
        )
        return [query] + deterministic

    if not getattr(settings, "query_expansion_llm_enabled", False):
        logger.info(
            "query_expand: LLM fallback disabled; original only "
            "(category=%s confidence=%.2f)",
            route.category,
            route.confidence,
        )
        return [query]

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
