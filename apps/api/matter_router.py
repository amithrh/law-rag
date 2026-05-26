"""Lightweight matter router and conservative action packs.

This is deliberately rule-based for now. It gives the UI a practical,
low-latency "what kind of problem is this?" frame before the cited RAG
answer arrives. The cited answer remains the source of legal propositions;
the router output is a triage and workflow aid.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal


Urgency = Literal["low", "medium", "high", "emergency"]


@dataclass(frozen=True)
class ActionPack:
    id: str
    title: str
    next_steps: list[str]
    documents: list[str]
    portals: list[str] = field(default_factory=list)
    escalation: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MatterRoute:
    category: str
    label: str
    confidence: float
    urgency: Urgency
    required_sources: list[str]
    forums: list[str]
    missing_facts: list[str]
    red_flags: list[str]
    action_pack: ActionPack | None = None
    legal_regime: str | None = None

    def to_event(self) -> dict:
        out = asdict(self)
        return out


_CRIME_WORDS = (
    "fir", "police", "arrest", "bail", "theft", "rape", "molest",
    "knife", "threat", "assault", "cheating", "fraud", "dowry",
    "stalking", "pocso", "ndps", "cyber", "hacked", "blackmail",
    "attacked", "recorded", "murder",
)
_CYBER_WORDS = (
    "cyber", "hacked", "facebook", "instagram", "whatsapp", "otp",
    "phishing", "upi", "credit card", "debit card", "online transaction",
    "deepfake", "fake account", "sextortion", "upload", "uploaded",
    "secretly recorded", "recorded us", "scam", "digital arrest",
    "parcel has drugs", "fake cbi", "fake police call",
)
_INTIMATE_IMAGE_WORDS = (
    "private photo", "private photos", "private picture", "private pictures",
    "private video", "private videos", "intimate photo", "intimate photos",
    "intimate video", "intimate videos", "nude photo", "nude photos",
    "nudes", "morphed photo", "morphed photos", "leaked photo",
    "leaked photos", "deepfake", "sex video",
)
_IMAGE_ABUSE_CONTEXT_WORDS = (
    "send to", "send it to", "send my", "send our", "send her", "send his",
    "share my", "share our", "show my", "show our", "forward my",
    "forward our", "upload", "uploaded", "post online", "posted", "posting",
    "leak", "leaked", "blackmail", "threat", "threaten", "threatens",
    "threatened", "threatening", "telegram", "whatsapp", "instagram",
    "facebook", "circulate", "circulating",
)
_INTIMATE_IMAGE_RISK_WORDS = (
    "ex", "boyfriend", "girlfriend", "bf", "gf", "partner", "stranger",
    "unknown person", "online friend", "has my nudes", "has our nudes",
    "has my nude", "has my private photo", "has my private photos",
    "has my intimate", "saved my nudes", "kept my nudes",
)
_INTIMATE_IMAGE_SERVICE_WORDS = (
    "photographer", "wedding", "family photo", "photo shoot", "photoshoot",
    "album", "designer", "studio", "refund", "lost", "defective", "service",
)
_CONSUMER_WORDS = (
    "refund", "defective", "damaged", "broken", "delivery", "order",
    "consumer", "warranty", "insurance claim", "bad food", "doctor negligence",
    "builder", "possession", "rera",
)
_OFF_TOPIC_WORDS = (
    "weather", "recipe", "python", "javascript", "cricket score",
    "cricket match", "movie", "biryani", "weekend party", "gaming laptop",
    "recommend a laptop", "laptop under", "quicksort",
)
_LEGAL_HINT_WORDS = (
    "act", "law", "legal", "court", "case", "fir", "police", "notice",
    "complaint", "appeal", "bail", "arrest", "warrant", "warranty",
    "refund", "defective", "consumer", "copyright", "trademark", "stolen",
    "fraud", "harassment", "harass", "claim", "compensation", "rights",
    "licence", "license", "contract", "rent", "landlord", "tenant",
)
_TRADEMARK_WORDS = (
    "trademark", "trade mark", "brand name", "logo", "passing off",
    "counterfeit", "copyright", "patent", "ip india", "unlicensed copies",
    "software license",
)
_TRIBAL_CASTE_WORDS = (
    "adivasi", "tribal", "sarna", "pahan", "dalit", "scheduled caste",
    "scheduled tribe", "sc st", "caste slur", "caste name", "untouchability",
    "forest rights", "gram sabha", "pesa", "st certificate", "gond",
    "ifr title", "cfr title", "community forest", "minor forest produce",
    "tendu", "scheduled area",
)
_LAND_RECORD_WORDS = (
    "pattadar", "passbook", "patta", "khata", "khatian", "khasra",
    "khatauni", "jamabandi", "record of rights", "ror", "mutation",
    "patwari", "tehsildar", "tahsildar", "talathi", "land record",
)
_COURT_PROCEDURE_WORDS = (
    "your honour", "my lord", "judge", "court etiquette", "court dress",
    "vakalatnama", "court fee", "case status", "filing procedure",
    "district court",
)
_WORK_INJURY_WORDS = (
    "construction site", "worksite", "factory accident", "site accident",
    "fell from", "fell down", "leg broken", "hand broken", "boiler burst",
    "silicosis", "thekedar", "principal employer", "contractor injury",
)
_BAIL_WORDS = (
    "anticipatory bail", "regular bail", "default bail", "interim bail",
    "bail", "arrested", "arrest notice", "notice for arrest",
    "chargesheet", "charge sheet", "custody limit", "custody period",
    "judicial custody", "police custody", "remand", "fir copy",
    "mcoca", "uapa", "narcotic", "narcotics",
)
_SOCIAL_WELFARE_WORDS = (
    "aadhaar", "aadhar", "pension", "scholarship", "ration card",
    "benefit stopped", "widow pension", "old age pension",
    "disability pension", "caste certificate", "income certificate",
    "sc scholarship", "st scholarship", "obc scholarship",
)
_SEXUAL_OFFENCE_SURVIVOR_WORDS = (
    "was raped", "raped by", "rape by", "molested me", "molested by",
    "sexual assault", "caretaker", "visually impaired", "disabled girl",
    "minor girl", "minor daughter", "daughter touched", "teacher touched",
    "pocso complaint", "child raped", "pocso victim",
)
_PRISON_RELEASE_WORDS = (
    "parole", "furlough", "remission", "premature release",
    "jail visit", "mulaqat", "prison visit", "open prison",
)
_WORKPLACE_SEXUAL_HARASSMENT_WORDS = (
    "posh", "sexual harassment", "boss touched", "manager touched",
    "colleague touched", "touches me", "late night meetings alone",
    "internal committee", "icc complaint", "local committee", "icc",
    "retaliation", "reporting manager", "bad rating", "pip",
)
_REPRODUCTIVE_RIGHTS_WORDS = (
    "abortion", "terminate pregnancy", "termination of pregnancy", "mtp",
    "pregnant after rape", "pregnancy after rape", "too late for abortion",
)
_TAX_GST_WORDS = (
    "gst", "cgst", "gstr", "tds", "26as", "income tax", "itr",
    "register gst", "tax notice", "form 26as",
)
_IBC_WORDS = (
    "ibc", "insolvency", "nclt", "operational creditor",
    "section 9 ibc", "section 7 ibc", "corporate debtor",
)
_BUSINESS_CONTRACT_WORDS = (
    "partnership", "partner", "mou", "exclusivity", "dealer",
    "non compete", "non-compete", "personal liability", "contract clause",
    "specific performance",
)
_BUSINESS_LICENSE_WORDS = (
    "shop license", "licence renewal", "license renewal", "shops and establishments",
    "trade license", "factory license", "establishment registration",
)
_GOVT_COURT_PROCEDURE_WORDS = (
    "mandamus", "writ", "article 226", "cognizance", "condonation",
    "limitation", "summons", "labour court",
)
_SECTION_91_NOTICE_WORDS = (
    "section 91", "crpc 91", "91 crpc", "notice under 91",
    "summons to produce", "produce document", "produce documents",
    "produce phone", "produce mobile", "hand over phone", "seize phone",
    "phone and whatsapp", "phone data", "device notice",
)
_PASSPORT_PROCEDURE_WORDS = (
    "passport police verification", "police verification", "adverse police report",
    "passport refused", "passport rejection", "passport denied", "passport pending",
    "rpo", "regional passport officer", "passport impounded", "passport revoked",
    "passport renewal", "passport application",
)
_LOK_ADALAT_CHALLENGE_WORDS = (
    "lok adalat award", "challenge lok adalat", "set aside lok adalat",
    "lok adalat settlement", "national lok adalat award",
)
_EDUCATION_WORDS = (
    "rte", "school", "admission", "tc", "transfer certificate",
    "capitation", "25 percent", "teacher demanding money",
)
_CHILD_FAMILY_WORDS = (
    "adopted child", "adoption", "real parents", "took our son",
    "not bringing back", "tourist visa", "child custody", "international child",
)
_LABOUR_EXPLOITATION_WORDS = (
    "nrega", "mgnrega", "asha worker", "honorarium", "cards passport",
    "keeping our cards", "bonded labour", "women workers", "half pay",
    "biharee", "racist", "wrongfully terminated", "terminated from job",
    "migrant worker", "inter state migrant", "inter-state migrant",
    "go back home", "return ticket", "walked from",
)
_ENVIRONMENT_WORDS = (
    "thermal plant", "blasting", "cracking our houses", "pollution",
    "environment", "no compensation", "factory pollution", "mining company",
)
_PMLA_ED_WORDS = (
    "pmla", "ed filed", "ed raided", "twin condition", "money laundering",
)
_BANKING_CREDIT_WORDS = (
    "bank wrongly debited", "forex transaction", "bank not giving noc",
    "cibil", "credit score", "loan tenure", "banking ombudsman",
)
_DIGITAL_PLATFORM_WORDS = (
    "uber deactivated", "account froze", "kyc pending", "online gaming",
    "app froze", "page suspended", "instagram suspended", "meta",
)
_MENTAL_HEALTH_WORDS = (
    "mentally ill", "kept him in chains", "mental healthcare",
    "admit in hospital", "psychiatric",
)


def route_matter(query: str) -> MatterRoute:
    q = _norm(query)

    if _is_off_topic(q):
        return MatterRoute(
            category="off_topic",
            label="Outside legal-help scope",
            confidence=0.85,
            urgency="low",
            required_sources=[],
            forums=[],
            missing_facts=[],
            red_flags=[],
            action_pack=None,
        )

    if _is_section_91_notice(q):
        return MatterRoute(
            category="criminal_procedure_notice",
            label="Police production notice / device request",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "CrPC 1973 section 91 for pre-1 July 2024 matters",
                "BNSS 2023 section 94 for current production summons",
                "BSA 2023 / Evidence Act rules where electronic records are involved",
            ],
            forums=["investigating officer/police station", "criminal court", "legal aid/lawyer"],
            missing_facts=["notice date", "case/FIR number", "issuing officer or court", "exact items demanded", "whether you are accused, witness, or complainant"],
            red_flags=_red_flags(q),
            action_pack=_criminal_notice_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_passport_procedure(q):
        return MatterRoute(
            category="passport_police_verification",
            label="Passport police verification / refusal",
            confidence=0.78,
            urgency="medium",
            required_sources=["Passports Act 1967", "Passport Rules / MEA police-verification procedure", "BNSS/CrPC only where a criminal case, warrant, or summons is involved"],
            forums=["Passport Seva Kendra / Regional Passport Office", "passport grievance portal", "High Court writ jurisdiction where refusal is arbitrary", "District Legal Services Authority"],
            missing_facts=["application file number", "police verification date", "adverse-report reason", "pending FIR/case/warrant details", "RPO notice or refusal order"],
            red_flags=_red_flags(q),
            action_pack=_passport_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("criminal case", "fir", "warrant", "summons", "case pending")) else None,
        )

    if _is_lok_adalat_challenge(q):
        return MatterRoute(
            category="lok_adalat_award_challenge",
            label="Lok Adalat award / settlement challenge",
            confidence=0.80,
            urgency="medium",
            required_sources=["Legal Services Authorities Act 1987 section 21", "constitutional/writ review principles where fraud, no consent, or jurisdiction is alleged"],
            forums=["District Legal Services Authority", "court that referred the matter", "High Court writ jurisdiction where exceptional grounds exist"],
            missing_facts=["award date", "case number", "whether you signed/consented", "fraud/coercion/no-authority facts", "copy of award and settlement terms"],
            red_flags=[],
            action_pack=_lok_adalat_pack(),
        )

    if _has_any(q, _SOCIAL_WELFARE_WORDS):
        return MatterRoute(
            category="social_welfare_identity",
            label="Welfare benefit / identity record",
            confidence=0.74,
            urgency="medium",
            required_sources=["Aadhaar Act 2016 where identity/authentication is involved", "state pension/scholarship/ration scheme rules", "Right to Information Act 2005 for status and reasons"],
            forums=["scheme portal/help desk", "district social welfare office", "Aadhaar Seva Kendra/CSC where relevant", "District Legal Services Authority"],
            missing_facts=["state/district", "scheme name", "application/beneficiary ID", "rejection or mismatch reason", "documents already submitted"],
            red_flags=_red_flags(q),
            action_pack=_social_welfare_pack(),
        )

    if _is_senior_citizen_issue(q):
        return MatterRoute(
            category="senior_citizen",
            label="Senior citizen maintenance / property transfer",
            confidence=0.78,
            urgency="high" if _has_any(q, ("threw me out", "no food", "homeless")) else "medium",
            required_sources=[
                "Maintenance and Welfare of Parents and Senior Citizens Act 2007",
                "state maintenance tribunal rules",
            ],
            forums=["Maintenance Tribunal / District Magistrate", "District Legal Services Authority"],
            missing_facts=["state/city", "age", "property transfer date", "whether a gift/settlement deed exists"],
            red_flags=_red_flags(q),
            action_pack=_senior_pack(),
        )

    if _has_any(q, _DIGITAL_PLATFORM_WORDS):
        return MatterRoute(
            category="digital_platform_account",
            label="Digital platform / account / KYC dispute",
            confidence=0.72,
            urgency="medium" if not _has_any(q, ("80k", "lakh", "money stuck", "frozen")) else "high",
            required_sources=["Information Technology Act 2000 / IT Rules where intermediary grievance applies", "Consumer Protection Act 2019 where paid service or money is involved", "RBI/KYC or online-gaming rules where financial account facts apply"],
            forums=["platform grievance officer/help centre", "consumer forum/e-Daakhil where service deficiency applies", "RBI or cyber/police channel where money/fraud is involved"],
            missing_facts=["platform/app name", "account ID", "amount stuck if any", "notice/reason given", "appeal/grievance history"],
            red_flags=_red_flags(q),
            action_pack=_digital_platform_pack(),
        )

    if _is_cyber_issue(q):
        return MatterRoute(
            category="cyber_fraud_or_harassment",
            label="Cyber fraud / online harassment",
            confidence=0.82,
            urgency="emergency" if _has_any(q, (
                "lost money", "upi", "credit card", "debit card", "otp",
                "blackmail", "nudes", "nude", "deepfake", "upload",
                "secretly recorded", "intimate video", "sex video",
            )) or _is_intimate_image_emergency(q) else "high",
            required_sources=["Information Technology Act 2000", "BNS/BNSS or IPC/CrPC based on incident date"],
            forums=["National Cyber Crime Portal", "1930 cyber helpline", "local police station"],
            missing_facts=["incident date", "platform", "amount lost", "whether money is still moving", "screenshots/transaction IDs"],
            red_flags=_red_flags(q),
            action_pack=_cyber_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_reproductive_rights(q):
        return MatterRoute(
            category="reproductive_rights_mtp",
            label="Pregnancy termination / reproductive rights",
            confidence=0.82,
            urgency="emergency" if _has_any(q, ("rape", "too late", "minor", "child")) else "high",
            required_sources=["Medical Termination of Pregnancy Act 1971 and Rules", "constitutional reproductive autonomy and privacy precedents", "BNS/IPC and POCSO where sexual offence or child facts apply"],
            forums=["registered medical practitioner / appropriate hospital", "medical board or court route where required", "District Legal Services Authority", "One Stop Centre where sexual offence is involved"],
            missing_facts=["gestational age in weeks", "survivor age", "medical condition", "doctor's written reason", "state/city and hospital"],
            red_flags=_red_flags(q),
            action_pack=_reproductive_rights_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("rape", "pocso", "minor", "child")) else None,
        )

    if _is_survivor_sexual_offence(q):
        return MatterRoute(
            category="sexual_offence_survivor",
            label="Sexual offence survivor / police response",
            confidence=0.86,
            urgency="emergency",
            required_sources=[
                "BNS 2023 / IPC 1860 sexual-offence provisions based on incident date",
                "BNSS 2023 / CrPC 1973 FIR, statement, and medical-examination procedure",
                "POCSO Act 2012 where the survivor is a child",
                "Rights of Persons with Disabilities Act 2016 where disability support is involved",
            ],
            forums=["police station/senior police", "One Stop Centre or women helpline", "Special Court where applicable", "District Legal Services Authority"],
            missing_facts=["survivor age", "incident date and place", "police complaint/FIR status", "medical care status", "disability/support needs"],
            red_flags=_red_flags(q),
            action_pack=_sexual_offence_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_workplace_sexual_harassment(q):
        return MatterRoute(
            category="workplace_sexual_harassment",
            label="Workplace sexual harassment",
            confidence=0.82,
            urgency="high",
            required_sources=["POSH Act 2013", "BNS 2023 / IPC 1860 provisions where physical assault, stalking, or threats are involved", "service/employment rules where applicable"],
            forums=["Internal Committee / Local Committee under POSH", "HR/employer grievance channel", "police where assault or threat is involved", "District Legal Services Authority"],
            missing_facts=["workplace and employer", "incident dates", "who was involved", "messages/witnesses", "whether an Internal Committee exists"],
            red_flags=_red_flags(q),
            action_pack=_posh_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("touch", "touched", "assault", "threat", "stalking")) else None,
        )

    if _has_any(q, _PMLA_ED_WORDS):
        return MatterRoute(
            category="pmla_ed",
            label="PMLA / ED proceedings",
            confidence=0.80,
            urgency="high",
            required_sources=["Prevention of Money Laundering Act 2002", "BNSS/CrPC bail and arrest safeguards where relevant", "Supreme Court PMLA bail/arrest precedents"],
            forums=["Special PMLA Court", "High Court", "legal aid/lawyer"],
            missing_facts=["ECIR/FIR details", "arrest/summons status", "scheduled offence", "attachment order if any", "custody/bail stage"],
            red_flags=_red_flags(q),
            action_pack=_pmla_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _has_any(q, _TRIBAL_CASTE_WORDS):
        return MatterRoute(
            category="tribal_caste_atrocity",
            label="Caste / tribal rights / targeted violence",
            confidence=0.76,
            urgency="emergency" if _has_any(q, ("attacked", "mob", "violence", "threat", "burn", "kill")) else "high",
            required_sources=[
                "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act 1989 where applicable",
                "PESA Act / Forest Rights Act where Scheduled Area or forest-rights facts apply",
                "BNS/BNSS or IPC/CrPC based on incident date",
            ],
            forums=["police station", "Special Court under SC/ST Act where applicable", "District Legal Services Authority", "tribal welfare authority"],
            missing_facts=["community/status documents", "incident date and place", "exact words/acts", "witnesses/video", "whether police complaint exists"],
            red_flags=_red_flags(q),
            action_pack=_tribal_caste_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, _CRIME_WORDS) else None,
        )

    if _has_any(q, _TRADEMARK_WORDS):
        return MatterRoute(
            category="trademark_ip",
            label="Trademark / brand / IP dispute",
            confidence=0.78,
            urgency="medium",
            required_sources=["Trade Marks Act 1999", "Copyright Act 1957 where creative work/logo is involved", "Commercial Courts Act where applicable"],
            forums=["Trade Marks Registry", "commercial court/civil court", "District Legal Services Authority or IP lawyer"],
            missing_facts=["mark/logo name", "first use date", "registration/application number", "evidence of use", "competitor details"],
            red_flags=_red_flags(q),
            action_pack=_trademark_pack(),
        )

    if _has_any(q, _TAX_GST_WORDS):
        return MatterRoute(
            category="tax_gst_compliance",
            label="Tax / GST / TDS compliance",
            confidence=0.76,
            urgency="medium",
            required_sources=["CGST Act 2017 / GST registration rules where GST applies", "Income Tax Act 1961 for TDS and return issues", "RBI/banking records where payment proof matters"],
            forums=["GST portal/help desk", "Income Tax portal", "tax professional/legal-aid clinic for notices"],
            missing_facts=["state", "turnover/income amount", "nature of service/business", "notice or form number", "tax period"],
            red_flags=[],
            action_pack=_tax_pack(),
        )

    if _has_any(q, _IBC_WORDS):
        return MatterRoute(
            category="ibc_nclt",
            label="IBC / NCLT insolvency",
            confidence=0.80,
            urgency="medium",
            required_sources=["Insolvency and Bankruptcy Code 2016", "NCLT Rules / IBC application forms", "Companies Act where company records matter"],
            forums=["NCLT", "insolvency professional/lawyer", "District Legal Services Authority for basic guidance"],
            missing_facts=["debt type", "amount", "default date", "invoices/contract", "demand notice status"],
            red_flags=[],
            action_pack=_ibc_pack(),
        )

    if _has_any(q, _BUSINESS_CONTRACT_WORDS):
        return MatterRoute(
            category="business_contract_partnership",
            label="Business contract / partnership",
            confidence=0.74,
            urgency="medium",
            required_sources=["Indian Contract Act 1872", "Indian Partnership Act 1932 where firm/partner facts apply", "Specific Relief Act 1963 where injunction/performance is sought"],
            forums=["civil/commercial court", "arbitration forum if contract has clause", "lawyer/legal-aid clinic"],
            missing_facts=["contract/MOU terms", "parties and dates", "amount/liability", "arbitration clause", "notices already sent"],
            red_flags=[],
            action_pack=_business_contract_pack(),
        )

    if _has_any(q, _BUSINESS_LICENSE_WORDS):
        return MatterRoute(
            category="business_license_compliance",
            label="Business license / shop registration",
            confidence=0.74,
            urgency="medium",
            required_sources=["state Shops and Establishments Act / rules", "municipal trade-license rules where applicable", "Right to Information Act 2005 where renewal delay/status is unclear"],
            forums=["state labour/shops establishment office", "municipal licensing office", "RTI/public grievance channel", "DLSA"],
            missing_facts=["state/city", "license/registration number", "renewal application date", "fee/penalty notice", "inspection or rejection reason"],
            red_flags=[],
            action_pack=_business_license_pack(),
        )

    if _has_any(q, _BAIL_WORDS):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Bail / criminal defence",
            confidence=0.80,
            urgency="high",
            required_sources=["BNSS 2023 / CrPC 1973 bail provisions based on incident date", "BNS 2023 / IPC 1860 offence provisions where relevant"],
            forums=["criminal court", "legal aid/lawyer", "police station only for notices/complaints"],
            missing_facts=["incident date", "FIR/offence sections", "arrest status", "court stage", "notice/order copies"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _has_any(q, ("fir",)) or (_has_any(q, ("police refused", "police not", "thana", "station")) and _has_any(q, _CRIME_WORDS)):
        return MatterRoute(
            category="police_fir",
            label="FIR / police inaction",
            confidence=0.84,
            urgency="emergency" if _has_any(q, ("rape", "molest", "child", "knife", "acid", "violence", "threat")) else "high",
            required_sources=["BNSS 2023 / CrPC based on incident date", "BNS 2023 / IPC based on incident date"],
            forums=["police station", "Superintendent of Police", "Judicial Magistrate", "District Legal Services Authority"],
            missing_facts=["incident date", "place", "whether complaint was given in writing", "police station name", "acknowledgement/CSR/DD number"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _has_any(q, ("cheque", "138", "dishonour", "insufficient funds", "bounced")):
        return MatterRoute(
            category="cheque_bounce",
            label="Cheque dishonour",
            confidence=0.82,
            urgency="high",
            required_sources=["Negotiable Instruments Act 1881 sections 138 and 142", "BNSS/CrPC complaint procedure"],
            forums=["Judicial Magistrate court", "lawyer/legal aid for notice drafting"],
            missing_facts=["date cheque returned", "bank return memo reason", "demand notice sent date", "15-day payment-window status", "amount and drawer details"],
            red_flags=[],
            action_pack=_cheque_pack(),
        )

    if _is_work_injury(q):
        return MatterRoute(
            category="workplace_injury_compensation",
            label="Workplace injury / compensation",
            confidence=0.76,
            urgency="high",
            required_sources=["Employees Compensation Act 1923", "BOCW Act 1996 / Factories Act 1948 where applicable", "state labour welfare and safety rules"],
            forums=["Labour Commissioner", "Employees Compensation Commissioner", "BOCW welfare board", "District Legal Services Authority"],
            missing_facts=["state/city", "employment/contractor details", "accident date", "medical papers", "wage proof"],
            red_flags=_red_flags(q),
            action_pack=_work_injury_pack(),
        )

    if _has_any(q, _LABOUR_EXPLOITATION_WORDS):
        return MatterRoute(
            category="labour_exploitation_discrimination",
            label="Labour exploitation / discrimination",
            confidence=0.76,
            urgency="high" if _has_any(q, ("passport", "cards passport", "bonded", "chains")) else "medium",
            required_sources=["Code on Wages / Payment of Wages law", "Bonded Labour System (Abolition) Act 1976 where coercion or document retention applies", "Equal Remuneration / anti-discrimination protections where applicable", "MGNREGA/state scheme rules where public work applies"],
            forums=["Labour Commissioner", "DLSA", "MGNREGA grievance authority where applicable", "police where coercion/document retention occurs"],
            missing_facts=["state/district", "employer/contractor", "wage amount", "dates worked", "documents retained or threats if any"],
            red_flags=_red_flags(q),
            action_pack=_labour_exploitation_pack(),
        )

    if _has_any(q, _CONSUMER_WORDS):
        return MatterRoute(
            category="consumer",
            label="Consumer complaint / service deficiency",
            confidence=0.78,
            urgency="medium",
            required_sources=["Consumer Protection Act 2019", "Consumer Protection Rules / e-Daakhil procedure"],
            forums=["National Consumer Helpline", "District Consumer Disputes Redressal Commission", "e-Daakhil"],
            missing_facts=["purchase date", "amount paid", "seller/service provider", "invoice/order ID", "written complaint history"],
            red_flags=_red_flags(q),
            action_pack=_consumer_pack(),
        )

    if _has_any(q, _CHILD_FAMILY_WORDS):
        return MatterRoute(
            category="child_custody_adoption",
            label="Child custody / adoption / child return",
            confidence=0.76,
            urgency="high" if _has_any(q, ("uk", "not bringing back", "tourist visa")) else "medium",
            required_sources=["Guardians and Wards Act / family law custody principles", "Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing", "habeas corpus / child return precedents where child is removed across borders"],
            forums=["Family Court", "District Child Protection Unit/CARA route where adoption is involved", "High Court writ jurisdiction for urgent child return", "DLSA"],
            missing_facts=["child age", "current location", "parent/guardian status", "orders/adoption papers", "travel documents"],
            red_flags=_red_flags(q),
            action_pack=_child_family_pack(),
        )

    if _has_any(q, ("legal aid", "free lawyer", "nalsa", "dlsa", "lok adalat")) and not _is_family_safety_issue(q):
        return MatterRoute(
            category="legal_aid",
            label="Legal aid / court support",
            confidence=0.80,
            urgency="medium",
            required_sources=["Legal Services Authorities Act 1987", "NALSA schemes"],
            forums=["District Legal Services Authority", "Taluk Legal Services Committee", "Lok Adalat where suitable"],
            missing_facts=["district", "income/category eligibility", "case type", "court stage"],
            red_flags=[],
            action_pack=_legal_aid_pack(),
        )

    if _is_family_safety_issue(q) or _has_any(q, (
        "domestic violence", "husband beat", "husband is beating",
        "husband threatens", "husband threatened", "husband threatening",
        "slaps me", "dowry", "in laws", "maintenance", "divorce", "custody",
    )):
        return MatterRoute(
            category="family_domestic",
            label="Family / domestic violence / maintenance",
            confidence=0.74,
            urgency="emergency" if _is_family_safety_issue(q) or _has_any(q, (
                "beating", "violence", "food", "locked", "threat", "threatens",
                "threatened", "threatening",
            )) else "high",
            required_sources=["PWDVA 2005", "family law statute by religion", "BNSS/CrPC maintenance provisions where applicable"],
            forums=["Protection Officer", "Magistrate court", "Family Court", "District Legal Services Authority"],
            missing_facts=["religion/personal law context", "marriage date", "children", "current safety", "income and residence details"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, _CRIME_WORDS) else None,
        )

    if _has_any(q, ("inheritance", "succession", "father died", "mother died", "will", "share from", "property share", "muslim inheritance", "coparcener")):
        return MatterRoute(
            category="succession_inheritance",
            label="Inheritance / succession",
            confidence=0.72,
            urgency="medium",
            required_sources=["personal succession law", "Indian Succession Act 1925 where applicable", "Hindu Succession Act / Muslim personal law where applicable"],
            forums=["civil court", "revenue office for mutation", "District Legal Services Authority"],
            missing_facts=["religion/personal law", "death date", "family tree", "will or no will", "property documents"],
            red_flags=_red_flags(q),
            action_pack=_succession_pack(),
        )

    if _has_any(q, ("salary", "wages", "gratuity", "pf", "epf", "maternity", "termination", "fired", "resign", "overtime", "contractor")):
        return MatterRoute(
            category="employment_wages",
            label="Employment / wages",
            confidence=0.74,
            urgency="medium",
            required_sources=["Payment of Wages Act / Code on Wages", "Industrial Disputes Act", "Maternity Benefit Act / EPF Act where relevant"],
            forums=["Labour Commissioner", "wage authority", "EPFO grievance portal", "District Legal Services Authority"],
            missing_facts=["state", "employee/workman status", "salary amount", "employment dates", "appointment letter or wage slips"],
            red_flags=_red_flags(q),
            action_pack=_employment_pack(),
        )

    if _has_any(q, ("jail", "prison", "custody", "yerwada", "tihar", "released")) and _has_any(q, ("compensation", "delay", "no chargesheet", "acquitted", "18 months")):
        return MatterRoute(
            category="custody_compensation",
            label="Custody delay / compensation",
            confidence=0.72,
            urgency="high" if _has_any(q, ("in jail", "custody", "bail")) else "medium",
            required_sources=["Article 21 constitutional remedies", "BNSS/CrPC default bail and speedy trial law", "human rights compensation precedents"],
            forums=["High Court writ jurisdiction", "Human Rights Commission", "District Legal Services Authority"],
            missing_facts=["case dates", "offence sections", "bail/chargesheet dates", "release/acquittal order", "court orders"],
            red_flags=_red_flags(q),
            action_pack=_custody_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _has_any(q, _PRISON_RELEASE_WORDS) or (_has_any(q, ("jail", "prison")) and _has_any(q, ("eligible", "release", "leave", "visit"))):
        return MatterRoute(
            category="prison_parole_furlough",
            label="Prison parole / furlough / remission",
            confidence=0.74,
            urgency="medium",
            required_sources=["state prison/parole/furlough rules", "prison manual", "Article 21 constitutional safeguards where custody conditions are involved"],
            forums=["prison superintendent", "state parole/furlough authority", "District Legal Services Authority", "High Court writ jurisdiction where needed"],
            missing_facts=["state/prison", "conviction or undertrial status", "sentence/offence details", "time already served", "reason for parole/furlough"],
            red_flags=_red_flags(q),
            action_pack=_prison_release_pack(),
        )

    if _has_any(q, _EDUCATION_WORDS):
        return MatterRoute(
            category="education_rights",
            label="School / education rights",
            confidence=0.74,
            urgency="medium",
            required_sources=["Right of Children to Free and Compulsory Education Act 2009 where school admission/TC facts apply", "state education rules", "anti-corruption/criminal law where illegal demand is made"],
            forums=["school management/education department", "district education officer", "RTE grievance authority", "DLSA"],
            missing_facts=["state/district", "school type", "child age/class", "written refusal/demand", "application or TC record"],
            red_flags=_red_flags(q),
            action_pack=_education_pack(),
        )

    if _has_any(q, _ENVIRONMENT_WORDS):
        return MatterRoute(
            category="environment_compensation",
            label="Environmental damage / compensation",
            confidence=0.72,
            urgency="medium",
            required_sources=["Environment Protection Act 1986", "National Green Tribunal Act 2010", "LARR/PESA/FRA where displacement or Scheduled Area consent applies"],
            forums=["District Collector / pollution control board", "National Green Tribunal", "DLSA", "Gram Sabha where Scheduled Area rights apply"],
            missing_facts=["location", "project/company", "damage proof", "dates", "complaints or notices already filed"],
            red_flags=_red_flags(q),
            action_pack=_environment_pack(),
        )

    if _has_any(q, ("municipal seized", "cart", "hawker", "street vendor", "vending license", "thela", "rehri")):
        return MatterRoute(
            category="street_vendor_municipal",
            label="Street vendor / municipal seizure",
            confidence=0.70,
            urgency="medium",
            required_sources=["Street Vendors Act 2014", "municipal corporation by-laws"],
            forums=["Town Vending Committee", "municipal commissioner/ward office", "District Legal Services Authority"],
            missing_facts=["city", "license/certificate status", "seizure memo", "place and date", "goods value"],
            red_flags=_red_flags(q),
            action_pack=_street_vendor_pack(),
        )

    if _has_any(q, _LAND_RECORD_WORDS):
        return MatterRoute(
            category="land_revenue_records",
            label="Land records / revenue office",
            confidence=0.74,
            urgency="medium",
            required_sources=["state land revenue / record-of-rights law", "state mutation and patta/passbook rules", "Right to Information Act 2005 where delay or missing records are involved"],
            forums=["tehsildar/taluk/revenue office", "revenue appellate authority", "District Legal Services Authority"],
            missing_facts=["state/district", "survey/khata/passbook number", "owner name", "loss/damage date", "applications already filed"],
            red_flags=_red_flags(q),
            action_pack=_land_records_pack(),
        )

    if _has_any(q, ("landlord", "tenant", "rent", "deposit", "lease", "property", "land", "ancestral", "sale deed", "gift deed", "possession")):
        return MatterRoute(
            category="property_tenancy",
            label="Property / tenancy",
            confidence=0.70,
            urgency="medium",
            required_sources=["Transfer of Property Act", "Registration Act", "state rent/control law", "Limitation Act where needed"],
            forums=["civil court or rent authority", "revenue office for land records", "District Legal Services Authority"],
            missing_facts=["state/city", "ownership/lease documents", "dates", "possession status", "notices already sent"],
            red_flags=_red_flags(q),
            action_pack=_property_pack(),
        )

    if _has_any(q, ("rti", "information", "government reply")):
        return MatterRoute(
            category="rti",
            label="RTI / government information",
            confidence=0.77,
            urgency="low",
            required_sources=["Right to Information Act 2005 sections 7 and 19"],
            forums=["Public Information Officer", "First Appellate Authority", "Information Commission"],
            missing_facts=["public authority", "application date", "reply or non-reply date", "RTI registration number", "first appeal filing date if already filed"],
            red_flags=[],
            action_pack=_rti_pack(),
        )

    if _has_any(q, _BANKING_CREDIT_WORDS):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Banking / credit record dispute",
            confidence=0.74,
            urgency="medium",
            required_sources=["RBI Integrated Ombudsman Scheme", "Credit Information Companies law where CIBIL/credit record is involved", "Consumer Protection Act 2019 where service deficiency applies"],
            forums=["bank grievance officer", "RBI Ombudsman", "credit bureau dispute channel", "consumer forum where needed"],
            missing_facts=["bank/NBFC name", "account/loan details", "transaction or NOC dates", "complaint number", "credit report entry"],
            red_flags=_red_flags(q),
            action_pack=_banking_credit_pack(),
        )

    if _has_any(q, _MENTAL_HEALTH_WORDS):
        return MatterRoute(
            category="mental_health_care_rights",
            label="Mental healthcare / protective admission",
            confidence=0.74,
            urgency="high" if _has_any(q, ("chains", "violence", "suicide")) else "medium",
            required_sources=["Mental Healthcare Act 2017", "Rights of Persons with Disabilities Act 2016 where disability support applies", "BNSS/BNS only where immediate violence is involved"],
            forums=["district mental health programme / hospital", "Mental Health Review Board", "DLSA", "police/emergency care if immediate harm"],
            missing_facts=["state/district", "current safety", "diagnosis/treatment history", "consent/capacity facts", "hospital availability"],
            red_flags=_red_flags(q),
            action_pack=_mental_health_pack(),
        )

    if _has_any(q, _COURT_PROCEDURE_WORDS) or _has_any(q, _GOVT_COURT_PROCEDURE_WORDS):
        return MatterRoute(
            category="court_procedure",
            label="Court procedure / court visit",
            confidence=0.72,
            urgency="low",
            required_sources=["court rules and practice directions for the relevant court", "Legal Services Authorities Act 1987 where help is needed"],
            forums=["court filing/help desk", "District Legal Services Authority", "lawyer/legal-aid clinic"],
            missing_facts=["court name", "case type", "case stage", "whether you are party/witness/visitor"],
            red_flags=[],
            action_pack=_court_procedure_pack(),
        )

    if _has_any(q, _CRIME_WORDS):
        return MatterRoute(
            category="criminal_general",
            label="Criminal law / safety",
            confidence=0.62,
            urgency="high" if _has_any(q, ("arrest", "bail", "rape", "threat", "violence")) else "medium",
            required_sources=["BNS/BNSS/BSA or IPC/CrPC/Evidence Act based on incident date"],
            forums=["police station", "criminal court", "District Legal Services Authority"],
            missing_facts=["incident date", "place", "whether FIR/notice/arrest already happened", "case stage"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
            legal_regime=_criminal_regime(q),
        )

    return MatterRoute(
        category="general_legal",
        label="General legal information",
        confidence=0.45,
        urgency="medium",
        required_sources=[],
        forums=["District Legal Services Authority", "relevant court/forum after issue classification"],
        missing_facts=["state/city", "dates", "documents", "what result you want"],
        red_flags=_red_flags(q),
        action_pack=None,
    )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    for needle in needles:
        if " " in needle:
            if needle in text:
                return True
            continue
        if re.search(rf"\b{re.escape(needle)}\b", text):
            return True
    return False


def _is_off_topic(q: str) -> bool:
    return _has_any(q, _OFF_TOPIC_WORDS) and not _has_any(q, _LEGAL_HINT_WORDS)


def _is_section_91_notice(q: str) -> bool:
    return _has_any(q, _SECTION_91_NOTICE_WORDS) and _has_any(q, ("police", "court", "fir", "case", "notice", "summons", "io", "investigating officer"))


def _is_passport_procedure(q: str) -> bool:
    return "passport" in q and _has_any(q, _PASSPORT_PROCEDURE_WORDS + ("criminal case", "case pending", "warrant", "summons"))


def _is_lok_adalat_challenge(q: str) -> bool:
    return _has_any(q, _LOK_ADALAT_CHALLENGE_WORDS) and _has_any(q, ("challenge", "set aside", "cancel", "fraud", "coercion", "without consent", "appeal", "review"))


def _is_cyber_issue(q: str) -> bool:
    if _has_any(q, _CYBER_WORDS):
        return True
    if not _has_any(q, _INTIMATE_IMAGE_WORDS):
        return False
    if _has_any(q, _IMAGE_ABUSE_CONTEXT_WORDS):
        return True
    if _has_any(q, _INTIMATE_IMAGE_SERVICE_WORDS):
        return False
    return _has_any(q, _INTIMATE_IMAGE_RISK_WORDS)


def _is_intimate_image_emergency(q: str) -> bool:
    return _has_any(q, _INTIMATE_IMAGE_WORDS) and (
        _has_any(q, _IMAGE_ABUSE_CONTEXT_WORDS)
        or (
            _has_any(q, _INTIMATE_IMAGE_RISK_WORDS)
            and not _has_any(q, _INTIMATE_IMAGE_SERVICE_WORDS)
        )
    )


def _is_family_safety_issue(q: str) -> bool:
    has_family_context = _has_any(q, (
        "domestic violence", "husband", "wife", "in laws", "mother in law",
        "father in law", "dowry", "marriage", "married",
    ))
    has_immediate_safety = _has_any(q, (
        "husband beat", "husband is beating", "beating me", "beats me",
        "slaps me", "hit me", "hitting me", "locked", "threat", "threatens",
        "threatened", "threatening", "kill", "no food", "not giving food",
        "threw me out", "unsafe",
    ))
    return has_family_context and has_immediate_safety


def _is_work_injury(q: str) -> bool:
    if _has_any(q, _WORK_INJURY_WORDS):
        return True
    work_context = _has_any(q, ("construction", "site", "factory", "mine", "contractor", "thekedar", "labour", "worker"))
    injury_context = _has_any(q, ("injury", "injured", "accident", "fell", "fall", "broken", "fracture", "death", "compensation"))
    return work_context and injury_context


def _is_survivor_sexual_offence(q: str) -> bool:
    accused_context = _has_any(q, ("false rape", "rape case against me", "accused of rape", "anticipatory bail", "regular bail", "bail in rape"))
    if accused_context:
        return False
    if _has_any(q, _SEXUAL_OFFENCE_SURVIVOR_WORDS):
        return True
    if _has_any(q, ("minor", "child", "daughter")) and _has_any(q, ("touch", "touched", "molest", "pocso")):
        return True
    survivor_context = _has_any(q, ("my sister", "my daughter", "my wife", "me", "victim", "survivor"))
    sexual_context = _has_any(q, ("rape", "molest", "sexual assault", "pocso"))
    return survivor_context and sexual_context


def _is_workplace_sexual_harassment(q: str) -> bool:
    if _has_any(q, _WORKPLACE_SEXUAL_HARASSMENT_WORDS):
        return True
    workplace_context = _has_any(q, ("boss", "manager", "colleague", "coworker", "office", "workplace", "hr"))
    harassment_context = _has_any(q, ("touch", "touched", "harass", "stalking", "sexual", "alone", "late night"))
    return workplace_context and harassment_context


def _is_reproductive_rights(q: str) -> bool:
    if _has_any(q, _REPRODUCTIVE_RIGHTS_WORDS):
        return True
    pregnancy_context = _has_any(q, ("pregnant", "pregnancy"))
    termination_context = _has_any(q, ("abortion", "terminate", "termination", "doctor says too late"))
    return pregnancy_context and termination_context


def _is_senior_citizen_issue(q: str) -> bool:
    if _has_any(q, ("son threw", "daughter threw", "children not taking care", "senior citizen", "old age", "gift deed", "daughter in law")):
        return True
    parent_transfer = _has_any(q, ("father", "mother", "parent")) and _has_any(q, ("gift", "gifted", "transfer", "transferred")) and _has_any(q, ("food", "basic amenities", "maintenance", "not taking care", "stopped giving"))
    if parent_transfer:
        return True
    senior_age = re.search(r"\b(6[0-9]|7[0-9]|8[0-9]|9[0-9])\b", q) is not None
    neglect_or_shelter = _has_any(q, (
        "threw", "evict", "homeless", "not giving food", "not taking care",
        "maintenance tribunal", "senior citizen tribunal", "gift deed",
        "widow threw", "house threw",
    ))
    return senior_age and neglect_or_shelter


def _red_flags(q: str) -> list[str]:
    flags: list[str] = []
    if _has_any(q, ("rape", "child", "molest", "pocso", "acid", "knife", "kill", "suicide", "mob", "violence")):
        flags.append("Immediate safety risk or serious offence")
    if _has_any(q, ("arrested", "in jail", "custody", "bail")):
        flags.append("Liberty/custody issue")
    if _has_any(q, ("lost money", "upi", "otp", "credit card", "bank account")):
        flags.append("Time-sensitive money trail")
    if _has_any(q, (
        "threw me out", "homeless", "not giving food", "beating", "locked",
        "hit me", "hitting me", "unsafe", "threatens", "threatened",
        "threatening",
    )):
        flags.append("Shelter or personal safety concern")
    return flags


def _criminal_regime(q: str) -> str:
    years = _extract_years(q)
    if len(years) > 1 and any(y < 2024 for y in years) and any(y > 2024 for y in years):
        return "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    year = _extract_year(q)
    if year is not None and year < 2024:
        return "legacy_ipc_crpc_evidence_for_pre_2024_incident"
    if year == 2024 and _mentions_before_july_2024(q):
        return "legacy_ipc_crpc_evidence_for_pre_2024_incident"
    if year is not None and year > 2024:
        return "current_bns_bnss_bsa_for_post_2024_incident"
    if year == 2024 and _mentions_after_july_2024(q):
        return "current_bns_bnss_bsa_for_post_2024_incident"
    return "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"


def _extract_year(q: str) -> int | None:
    years = _extract_years(q)
    return years[0] if years else None


def _extract_years(q: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r"\b(20\d{2}|19\d{2})\b", q)]


def _mentions_before_july_2024(q: str) -> bool:
    return "before july 2024" in q or "june 2024" in q or "may 2024" in q


def _mentions_after_july_2024(q: str) -> bool:
    return "after july 2024" in q or "august 2024" in q or "september 2024" in q


def _consumer_pack() -> ActionPack:
    return ActionPack(
        id="consumer",
        title="Consumer complaint path",
        next_steps=[
            "Send a short written complaint to the seller or service provider and keep proof.",
            "If unresolved, raise the grievance on National Consumer Helpline or e-Daakhil.",
            "Prepare a simple timeline with order date, defect/service issue, and refund/repair demand.",
        ],
        documents=["invoice/order ID", "photos/video", "emails/chats", "warranty", "payment proof"],
        portals=["consumerhelpline.gov.in", "edaakhil.nic.in"],
        escalation=["District Consumer Disputes Redressal Commission"],
        cautions=["Medical negligence, builder delay, and insurance disputes often need extra documents and expert review."],
    )


def _social_welfare_pack() -> ActionPack:
    return ActionPack(
        id="social_welfare_identity",
        title="Benefit/identity correction path",
        next_steps=[
            "Identify the exact scheme or ID record causing the denial and collect the rejection/mismatch proof.",
            "File a written correction or grievance with the scheme office, portal, CSC, or Aadhaar centre as relevant.",
            "If officials do not give reasons, use RTI or DLSA help to get status and the rule relied on.",
        ],
        documents=["Aadhaar/ID proof", "scheme application ID", "rejection or mismatch screenshot", "certificate/income/caste papers", "bank/passbook proof"],
        portals=["scheme portal where available", "uidai.gov.in for Aadhaar services", "rtionline.gov.in for central authorities"],
        escalation=["district social welfare office", "scheme appellate/grievance authority", "District Legal Services Authority"],
        cautions=["Benefit cases are state- and scheme-specific; exact scheme name and rejection reason matter."],
    )


def _digital_platform_pack() -> ActionPack:
    return ActionPack(
        id="digital_platform_account",
        title="Platform grievance path",
        next_steps=[
            "Preserve the suspension/deactivation/KYC message and account screenshots.",
            "File an in-app/platform grievance and keep the ticket number.",
            "If money is stuck or fraud is suspected, use the consumer, RBI, cyber, or police route as facts require.",
        ],
        documents=["account/profile ID", "screenshots", "transaction IDs", "KYC submission proof", "support ticket history"],
        portals=["platform grievance portal", "consumerhelpline.gov.in where service deficiency applies", "cybercrime.gov.in for fraud"],
        escalation=["platform grievance officer", "consumer forum", "RBI/cyber channel where money or fraud is involved"],
        cautions=["Platform disputes depend heavily on the notice reason and terms of service."],
    )


def _tax_pack() -> ActionPack:
    return ActionPack(
        id="tax_gst_compliance",
        title="Tax/GST facts path",
        next_steps=[
            "Identify the exact tax period, turnover/income amount, and notice or form involved.",
            "Download portal records such as GSTR, Form 26AS, AIS/TIS, challans, or TDS certificates.",
            "For notices or threshold decisions, get a tax professional to check the filing route before responding.",
        ],
        documents=["PAN/GSTIN", "invoices", "bank statements", "Form 26AS/AIS", "notices", "returns/challans"],
        portals=["gst.gov.in", "incometax.gov.in"],
        escalation=["GST help desk", "Income Tax grievance", "tax professional"],
        cautions=["Tax thresholds and deadlines change with facts; do not guess filings from a short chat answer."],
    )


def _ibc_pack() -> ActionPack:
    return ActionPack(
        id="ibc_nclt",
        title="IBC/NCLT filing path",
        next_steps=[
            "Classify the claim as financial debt, operational debt, or another company-law issue.",
            "Collect invoices, contracts, default date proof, and demand notice history.",
            "Check NCLT form, limitation, and pre-filing notice requirements before filing.",
        ],
        documents=["contract/invoices", "ledger", "default proof", "demand notice", "company master data", "email acknowledgements"],
        portals=["nclt.gov.in", "ibbi.gov.in"],
        escalation=["NCLT", "insolvency professional/lawyer"],
        cautions=["IBC is not a normal debt-recovery shortcut; defective notices or limitation issues can sink the filing."],
    )


def _business_contract_pack() -> ActionPack:
    return ActionPack(
        id="business_contract_partnership",
        title="Business-contract path",
        next_steps=[
            "Read the contract/MOU for termination, liability, arbitration, non-compete, and notice clauses.",
            "Create a dated breach/liability timeline with payment and communication proof.",
            "Send or respond to notices only after checking the forum and clause strategy.",
        ],
        documents=["contract/MOU", "partnership deed", "loan/security papers", "invoices", "messages/emails", "notices"],
        escalation=["commercial/civil court", "arbitration forum if agreed", "lawyer/legal-aid clinic"],
        cautions=["Non-competes, partnership retirement, and exclusivity clauses are fact- and drafting-heavy."],
    )


def _business_license_pack() -> ActionPack:
    return ActionPack(
        id="business_license_compliance",
        title="License renewal/status path",
        next_steps=[
            "Collect the license number, renewal application receipt, fee proof, and any penalty/rejection notice.",
            "Ask the licensing office for written status and the rule causing delay or penalty.",
            "Use RTI/public grievance or DLSA help if the office will not give reasons.",
        ],
        documents=["license/registration copy", "renewal receipt", "fee/challan proof", "inspection notice", "penalty/rejection letter"],
        escalation=["shops establishment office", "municipal licensing office", "RTI/public grievance channel", "DLSA"],
        cautions=["Shop and establishment rules are state-specific; city and license type matter."],
    )


def _labour_exploitation_pack() -> ActionPack:
    return ActionPack(
        id="labour_exploitation_discrimination",
        title="Labour exploitation path",
        next_steps=[
            "Write down work dates, wage due, contractor/employer details, and any threats or document retention.",
            "Approach the labour office/DLSA; use police too if documents are held or movement is restricted.",
            "For NREGA or scheme work, file the scheme grievance with job-card/work-demand details.",
        ],
        documents=["ID/job card", "attendance/work proof", "wage slips", "bank statement", "contractor details", "messages/witnesses"],
        escalation=["Labour Commissioner", "DLSA", "MGNREGA grievance authority", "police for coercion"],
        cautions=["Document retention, forced work, and migration under debt can become bonded-labour issues."],
    )


def _child_family_pack() -> ActionPack:
    return ActionPack(
        id="child_custody_adoption",
        title="Child custody/adoption path",
        next_steps=[
            "Confirm the child's current location, age, and who has legal custody or guardianship papers.",
            "Collect birth, school, travel, and adoption/guardianship records.",
            "For urgent removal or foreign travel, speak to DLSA/lawyer about family court or writ options quickly.",
        ],
        documents=["child birth proof", "school records", "travel documents", "custody/adoption papers", "messages", "prior orders"],
        escalation=["Family Court", "District Child Protection Unit", "DLSA", "High Court writ route for urgent child return"],
        cautions=["Informal adoption and cross-border child removal are high-risk; paperwork and jurisdiction matter."],
    )


def _education_pack() -> ActionPack:
    return ActionPack(
        id="education_rights",
        title="School-rights path",
        next_steps=[
            "Ask for written reasons for admission denial, TC refusal, scholarship denial, or money demand.",
            "File a complaint with the school authority and district education office/RTE authority.",
            "Use DLSA or anti-corruption/police channels if an official demand for money is involved.",
        ],
        documents=["application/TC request", "fee receipts", "school messages", "child age/class proof", "category/income proof where relevant"],
        escalation=["district education officer", "RTE grievance authority", "DLSA"],
        cautions=["School remedies are state-rule heavy; written refusal is very useful."],
    )


def _environment_pack() -> ActionPack:
    return ActionPack(
        id="environment_compensation",
        title="Environmental harm path",
        next_steps=[
            "Collect damage photos, dates, project/company name, and any health/property records.",
            "Complain to the district authority and pollution control board with evidence.",
            "For serious continuing harm, check NGT, High Court, or Scheduled Area consent routes with legal aid.",
        ],
        documents=["photos/videos", "damage assessment", "medical/property papers", "complaint copies", "project/company details"],
        escalation=["pollution control board", "District Collector", "National Green Tribunal", "DLSA"],
        cautions=["Environmental compensation needs proof of damage, cause, and responsible project/operator."],
    )


def _pmla_pack() -> ActionPack:
    return ActionPack(
        id="pmla_ed",
        title="PMLA/ED defence path",
        next_steps=[
            "Collect summons, arrest grounds, ECIR/FIR links, attachment orders, and bail/custody papers.",
            "Identify the scheduled offence and current stage before arguing bail or attachment.",
            "Use urgent legal aid/lawyer support if summons, arrest, or custody is live.",
        ],
        documents=["ED summons", "arrest memo/grounds", "FIR/scheduled offence papers", "attachment order", "bank/property records", "court orders"],
        escalation=["Special PMLA Court", "High Court", "legal aid/lawyer"],
        cautions=["PMLA bail and attachment law is high-risk and fact-specific."],
    )


def _banking_credit_pack() -> ActionPack:
    return ActionPack(
        id="banking_credit_dispute",
        title="Banking/credit correction path",
        next_steps=[
            "File a written bank/NBFC complaint and preserve the acknowledgement number.",
            "Collect transaction, NOC, credit-report, and repayment proof.",
            "Escalate to RBI Ombudsman or credit-bureau dispute channel if the bank does not fix it.",
        ],
        documents=["bank statement", "loan closure proof", "NOC request", "credit report", "complaint number", "transaction ID"],
        portals=["cms.rbi.org.in", "credit bureau dispute portal"],
        escalation=["bank grievance officer", "RBI Ombudsman", "credit bureau"],
        cautions=["Credit-record disputes need exact account numbers, closure dates, and bureau entries."],
    )


def _mental_health_pack() -> ActionPack:
    return ActionPack(
        id="mental_health_care_rights",
        title="Mental-health care path",
        next_steps=[
            "Check immediate safety first and contact emergency medical help if there is risk of harm.",
            "Approach a government mental-health facility or district mental-health programme for lawful assessment.",
            "If someone is chained, confined, or abused, contact DLSA and local authorities urgently.",
        ],
        documents=["ID proof", "medical history", "current safety facts", "photos/witnesses of confinement or abuse", "hospital records"],
        escalation=["mental-health facility", "Mental Health Review Board", "DLSA", "police/emergency services"],
        cautions=["Forced admission has legal safeguards; safety and dignity both matter."],
    )


def _fir_pack() -> ActionPack:
    return ActionPack(
        id="police_fir",
        title="Police complaint path",
        next_steps=[
            "Write the incident facts with date, place, people involved, and what police refused to do.",
            "Ask for an acknowledgement number for any written complaint.",
            "If the station still refuses, escalate to senior police or court/legal aid with the complaint proof.",
        ],
        documents=["written complaint", "ID proof", "photos/videos", "medical report if any", "witness names", "prior police acknowledgement"],
        portals=["state police portal where available"],
        escalation=["Superintendent of Police", "Judicial Magistrate", "District Legal Services Authority"],
        cautions=["For immediate danger, call local emergency services first."],
    )


def _cyber_pack() -> ActionPack:
    return ActionPack(
        id="cyber",
        title="Cyber incident path",
        next_steps=[
            "Preserve screenshots, URLs, profile links, transaction IDs, and timestamps.",
            "For money loss, report quickly through 1930 or the cybercrime portal.",
            "Do not delete chats/accounts until evidence is backed up.",
        ],
        documents=["screenshots", "bank/UPI transaction IDs", "phone numbers", "profile URLs", "device/account details"],
        portals=["cybercrime.gov.in", "1930 helpline"],
        escalation=["local cyber cell", "police station", "bank fraud desk for payment reversal attempts"],
        cautions=["If intimate images, blackmail, or threats are involved, treat it as urgent safety matter."],
    )


def _sexual_offence_pack() -> ActionPack:
    return ActionPack(
        id="sexual_offence_survivor",
        title="Immediate survivor-support path",
        next_steps=[
            "Prioritize medical care, safety, and a trusted support person before paperwork.",
            "Ask police for FIR registration and survivor-sensitive procedure; escalate if they refuse.",
            "Contact DLSA, One Stop Centre, women helpline, or child/disability support service where relevant.",
        ],
        documents=["written complaint", "medical papers", "survivor age/ID proof", "disability/support documents if any", "messages/photos/witness details"],
        portals=["state police/women helpline where available"],
        escalation=["senior police officer", "District Legal Services Authority", "One Stop Centre", "Special Court where applicable"],
        cautions=["Do not delay urgent medical care or safety steps while waiting for a perfect legal answer."],
    )


def _posh_pack() -> ActionPack:
    return ActionPack(
        id="workplace_sexual_harassment",
        title="Workplace harassment safety path",
        next_steps=[
            "Preserve messages, call logs, meeting invites, CCTV clues, and a dated incident timeline.",
            "Check whether the employer has an Internal Committee; if not, ask the district Local Committee/DLSA for the POSH route.",
            "If there is assault, stalking, threats, or immediate danger, treat it as a police/safety issue too.",
        ],
        documents=["incident timeline", "messages/emails", "meeting invites", "witness names", "employment proof", "medical record if any"],
        escalation=["Internal Committee / Local Committee", "District Legal Services Authority", "police for assault, stalking, or threats"],
        cautions=["Retaliation and forced settlement are common risks; keep copies outside the work device."],
    )


def _reproductive_rights_pack() -> ActionPack:
    return ActionPack(
        id="reproductive_rights_mtp",
        title="Urgent medical/legal support path",
        next_steps=[
            "Get prompt medical assessment from an appropriate hospital or registered medical practitioner.",
            "Ask for the doctor's written reason if termination is refused or delayed.",
            "For rape, minor, disability, or late-pregnancy facts, contact DLSA/One Stop Centre urgently for the medical-board or court route.",
        ],
        documents=["medical records", "ultrasound/gestational-age proof", "doctor refusal/reason if any", "ID/age proof", "FIR/complaint if sexual offence is involved"],
        escalation=["District Legal Services Authority", "One Stop Centre", "medical board or court route where required"],
        cautions=["This is time-sensitive and medical-risk-sensitive; do not rely only on a chatbot for decisions."],
    )


def _senior_pack() -> ActionPack:
    return ActionPack(
        id="senior_citizen",
        title="Senior citizen support path",
        next_steps=[
            "Collect property transfer papers, proof of age, and proof of neglect or eviction.",
            "Approach the Maintenance Tribunal or District Legal Services Authority for urgent guidance.",
            "If there is violence or immediate eviction, treat safety and shelter first.",
        ],
        documents=["age proof", "gift/sale/settlement deed", "residence proof", "medical records", "messages/witness details"],
        escalation=["Maintenance Tribunal", "District Magistrate", "District Legal Services Authority"],
    )


def _family_safety_pack() -> ActionPack:
    return ActionPack(
        id="family_domestic",
        title="Family safety path",
        next_steps=[
            "If you are unsafe, prioritize shelter, emergency help, and a trusted person.",
            "Keep medical records, photos, messages, and a dated incident diary.",
            "Legal routes may include protection, residence, maintenance, custody, or criminal complaint depending on facts.",
        ],
        documents=["marriage proof", "ID/address proof", "medical records", "messages/photos", "income details", "child documents"],
        escalation=["Protection Officer", "Magistrate court", "Family Court", "District Legal Services Authority"],
        cautions=["Do not wait for a perfect legal answer if there is immediate violence."],
    )


def _employment_pack() -> ActionPack:
    return ActionPack(
        id="employment_wages",
        title="Employment dues path",
        next_steps=[
            "Create a wage/employment timeline with joining date, last working date, and unpaid amount.",
            "Send a written demand to employer/contractor and preserve proof.",
            "Approach the labour office or statutory portal depending on wages, PF, gratuity, or maternity issue.",
        ],
        documents=["appointment letter", "salary slips", "attendance", "bank statements", "termination/resignation messages"],
        portals=["EPFO grievance portal for PF issues"],
        escalation=["Labour Commissioner", "wage authority", "District Legal Services Authority"],
    )


def _succession_pack() -> ActionPack:
    return ActionPack(
        id="succession_inheritance",
        title="Inheritance facts path",
        next_steps=[
            "Prepare a family tree and list the properties or accounts in dispute.",
            "Clarify whether there is a will and which personal law applies.",
            "For land/flat mutation, collect death certificate and title records before approaching the authority or court.",
        ],
        documents=["death certificate", "family tree", "will if any", "title documents", "identity/address proofs"],
        escalation=["civil court", "revenue/mutation authority", "District Legal Services Authority"],
    )


def _street_vendor_pack() -> ActionPack:
    return ActionPack(
        id="street_vendor_municipal",
        title="Municipal seizure path",
        next_steps=[
            "Ask for the seizure memo, challan, or written reason for taking goods.",
            "Collect vending certificate/license papers and photos of the vending spot.",
            "Approach the ward office or Town Vending Committee with a written release request.",
        ],
        documents=["vending certificate/license", "seizure memo", "photos", "stock value proof", "ID/address proof"],
        escalation=["Town Vending Committee", "municipal commissioner/ward office", "District Legal Services Authority"],
    )


def _tribal_caste_pack() -> ActionPack:
    return ActionPack(
        id="tribal_caste_atrocity",
        title="Targeted-violence triage path",
        next_steps=[
            "Write down the exact incident with date, place, words used, people involved, and witnesses.",
            "Preserve photos, videos, medical papers, and community/status documents.",
            "For violence, threats, or police refusal, approach police, DLSA, or the SC/ST/tribal welfare channel urgently.",
        ],
        documents=["community/status certificate", "written complaint", "photos/videos", "medical record", "witness names", "land/forest-rights papers if relevant"],
        escalation=["police station", "Special Court under SC/ST Act where applicable", "District Legal Services Authority", "tribal welfare authority"],
        cautions=["This route depends heavily on whether the affected person is legally covered by SC/ST or tribal-rights protections."],
    )


def _trademark_pack() -> ActionPack:
    return ActionPack(
        id="trademark_ip",
        title="Brand/IP dispute path",
        next_steps=[
            "Check the mark/application status on the Trade Marks Registry and preserve screenshots.",
            "Collect proof of first use, invoices, packaging, website/social pages, and customer proof.",
            "Decide whether the immediate step is opposition, rectification, infringement, passing off, or a legal notice.",
        ],
        documents=["brand/logo files", "first-use proof", "invoices", "advertising/screenshots", "registry application or registration details"],
        portals=["ipindia.gov.in"],
        escalation=["Trade Marks Registry", "commercial court/civil court", "IP lawyer or legal-aid clinic"],
        cautions=["Deadlines for opposition/rectification can matter, and drafting mistakes can hurt later litigation."],
    )


def _bail_pack() -> ActionPack:
    return ActionPack(
        id="criminal_defence_bail",
        title="Bail defence path",
        next_steps=[
            "Identify the FIR/offence sections and the incident date before choosing old or new criminal procedure.",
            "Collect notice, FIR, arrest memo, bail orders, and court dates.",
            "Speak to legal aid or a criminal lawyer quickly if arrest or custody is possible.",
        ],
        documents=["FIR/complaint", "notice/summons", "arrest memo if any", "prior bail/order copies", "ID/address proof"],
        escalation=["criminal court", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
        cautions=["Bail strategy changes with offence sections, arrest status, and incident date."],
    )


def _work_injury_pack() -> ActionPack:
    return ActionPack(
        id="workplace_injury_compensation",
        title="Work-injury compensation path",
        next_steps=[
            "Get medical treatment records and preserve the accident-site details immediately.",
            "Write a dated complaint to the employer/contractor and labour office with wage and accident facts.",
            "Check whether the route is Employees Compensation, BOCW welfare board, ESI, or factory safety enforcement.",
        ],
        documents=["medical records", "accident photos/videos", "wage proof", "contractor/employer details", "witness names", "site ID/attendance proof"],
        escalation=["Labour Commissioner", "Employees Compensation Commissioner", "BOCW welfare board", "District Legal Services Authority"],
        cautions=["Serious injury and death claims need prompt medical, wage, and employer-link evidence."],
    )


def _land_records_pack() -> ActionPack:
    return ActionPack(
        id="land_revenue_records",
        title="Land-records path",
        next_steps=[
            "Collect survey/khata/passbook details and any prior receipts or applications.",
            "File a written request at the revenue office and ask for an acknowledgement.",
            "If delayed, use the revenue appeal/grievance channel or RTI to get status and records.",
        ],
        documents=["ID/address proof", "old passbook/record copy", "survey or khata number", "application receipt", "loss/damage proof if any"],
        escalation=["tehsildar/taluk/revenue office", "revenue appellate authority", "District Legal Services Authority"],
    )


def _court_procedure_pack() -> ActionPack:
    return ActionPack(
        id="court_procedure",
        title="Court-visit support path",
        next_steps=[
            "Confirm the court, case type, and whether you are appearing as party, witness, or visitor.",
            "Carry ID, case number, and any notice/order connected to the visit.",
            "For filing or representation, ask the court help desk or DLSA before the hearing date.",
        ],
        documents=["ID proof", "case number", "notice/summons/order", "filing papers if any"],
        escalation=["court help desk", "District Legal Services Authority", "lawyer/legal-aid clinic"],
    )


def _custody_pack() -> ActionPack:
    return ActionPack(
        id="custody_compensation",
        title="Custody-delay facts path",
        next_steps=[
            "Build an exact timeline from arrest to chargesheet, bail, release, or acquittal.",
            "Collect certified copies of FIR, remand orders, bail orders, and final release/acquittal papers.",
            "Speak to legal aid or a lawyer before filing compensation or writ proceedings.",
        ],
        documents=["FIR", "arrest/remand papers", "chargesheet date proof", "bail/release order", "final judgment/order"],
        escalation=["High Court writ jurisdiction", "Human Rights Commission", "District Legal Services Authority"],
        cautions=["Custody, bail, and compensation claims are fact-heavy and deadline-sensitive."],
    )


def _prison_release_pack() -> ActionPack:
    return ActionPack(
        id="prison_parole_furlough",
        title="Prison leave/remission path",
        next_steps=[
            "Confirm whether the person is an undertrial or convicted prisoner and which prison/state rules apply.",
            "Collect sentence/order details, custody period, conduct record, and reason for parole or furlough.",
            "Apply through prison authorities first, then seek legal aid or court review if refused without proper reasons.",
        ],
        documents=["conviction/order papers", "custody period proof", "prison conduct record", "family/medical/emergency proof", "prior rejection order if any"],
        escalation=["prison superintendent", "state parole/furlough authority", "District Legal Services Authority", "High Court writ jurisdiction"],
        cautions=["Parole, furlough, and remission are state-rule heavy and depend on conviction status and conduct record."],
    )


def _cheque_pack() -> ActionPack:
    return ActionPack(
        id="cheque_bounce",
        title="Cheque dishonour path",
        next_steps=[
            "Preserve the original cheque, bank return memo, and all payment communications.",
            "Check the statutory demand-notice, payment-window, and complaint timelines carefully with a lawyer/legal-aid clinic.",
            "Prepare drawer details, amount due, and the transaction background.",
        ],
        documents=["original cheque", "return memo", "notice copy", "postal/courier proof", "invoice/loan proof"],
        escalation=["Judicial Magistrate court", "legal aid/lawyer for limitation-sensitive drafting"],
        cautions=["This category is deadline-sensitive."],
    )


def _criminal_notice_pack() -> ActionPack:
    return ActionPack(
        id="criminal_procedure_notice",
        title="Police notice response path",
        next_steps=[
            "Read the notice exactly: issuing authority, case number, item demanded, and appearance/production date.",
            "Preserve the device/data and avoid deleting, altering, or forwarding material connected to the case.",
            "Get urgent legal-aid or lawyer help before handing over a phone or passwords, especially if you may be treated as an accused.",
        ],
        documents=["notice copy", "FIR/case number", "ID proof", "device ownership proof", "screenshots/messages", "prior police communications"],
        escalation=["investigating officer", "Magistrate/criminal court", "District Legal Services Authority"],
        cautions=["A CrPC section 91-style notice is now usually mapped to BNSS section 94 for current matters; the incident/case date matters."],
    )


def _passport_pack() -> ActionPack:
    return ActionPack(
        id="passport_police_verification",
        title="Passport verification path",
        next_steps=[
            "Collect the Passport Seva file number, police verification details, and the RPO notice/refusal reason.",
            "Ask for the adverse-report reason in writing and prepare a factual reply with case-status documents.",
            "Escalate through passport grievance/RPO first, then consider legal aid or writ review if the refusal is unsupported.",
        ],
        documents=["passport file number", "RPO notice/refusal order", "police verification report if available", "case/FIR/warrant status papers", "identity/address proof"],
        portals=["passportindia.gov.in grievance/status channels"],
        escalation=["Regional Passport Office", "passport grievance officer", "District Legal Services Authority", "High Court writ jurisdiction"],
    )


def _lok_adalat_pack() -> ActionPack:
    return ActionPack(
        id="lok_adalat_award_challenge",
        title="Lok Adalat award review path",
        next_steps=[
            "Collect the award, settlement memo, referral order, and proof of who consented or signed.",
            "Identify the narrow challenge ground: no consent, fraud, coercion, mistaken party authority, or lack of jurisdiction.",
            "Get DLSA/court help quickly; ordinary appeal routes are usually limited for Lok Adalat awards.",
        ],
        documents=["Lok Adalat award", "settlement memo", "case papers", "signature/authority proof", "fraud/coercion evidence"],
        escalation=["District Legal Services Authority", "referring court", "High Court writ jurisdiction"],
        cautions=["Do not frame this as a normal appeal without checking section 21 and the exact consent facts."],
    )


def _property_pack() -> ActionPack:
    return ActionPack(
        id="property_tenancy",
        title="Property document path",
        next_steps=[
            "Identify whether the issue is ownership, possession, rent/deposit, registration, or land records.",
            "Collect the core property papers and any notice/communication.",
            "State law matters heavily, so state and city are required before giving forum-specific next steps.",
        ],
        documents=["sale/gift/lease deed", "rent agreement", "receipts", "land records", "notices/messages"],
        escalation=["civil court/rent authority", "revenue office", "District Legal Services Authority"],
    )


def _rti_pack() -> ActionPack:
    return ActionPack(
        id="rti",
        title="RTI appeal path",
        next_steps=[
            "Keep the RTI application, fee proof, and reply or non-reply record.",
            "If no proper reply, prepare a first appeal with dates and the information requested.",
            "Escalate to the Information Commission if the first appeal does not resolve it.",
        ],
        documents=["RTI application", "fee proof", "postal/online receipt", "PIO reply", "first appeal papers"],
        portals=["rtionline.gov.in for central public authorities"],
        escalation=["First Appellate Authority", "Information Commission"],
    )


def _legal_aid_pack() -> ActionPack:
    return ActionPack(
        id="legal_aid",
        title="Legal aid path",
        next_steps=[
            "Identify your district and case type.",
            "Collect income/category proof and any court/police papers.",
            "Approach DLSA/TLSC or the court legal-aid desk.",
        ],
        documents=["ID proof", "income/category proof", "case papers", "FIR/notice/order if any"],
        portals=["nalsa.gov.in"],
        escalation=["District Legal Services Authority", "Taluk Legal Services Committee"],
    )


def _criminal_pack() -> ActionPack:
    return ActionPack(
        id="criminal_general",
        title="Criminal-law triage path",
        next_steps=[
            "Clarify incident date first because old and new criminal codes may differ.",
            "Collect FIR/notice/arrest papers and a timeline.",
            "If arrest or custody is involved, contact a lawyer or legal aid urgently.",
        ],
        documents=["FIR/complaint", "notice/summons", "arrest memo if any", "medical report", "messages/photos/videos"],
        escalation=["criminal court", "District Legal Services Authority", "senior police officer where appropriate"],
        cautions=["Bail, custody, sexual offences, and child-safety matters need urgent professional help."],
    )


__all__ = ["ActionPack", "MatterRoute", "route_matter"]
