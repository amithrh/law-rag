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
    "attacked", "beat", "beaten", "recorded", "murder", "burnt",
    "burned", "arson", "498a", "blank paper", "forged", "forgery",
    "moneylender", "stripped", "disrobed", "public humiliation",
    "didn't sign", "did not sign", "fake signature", "loan against",
    "stalker", "stalked", "follows", "following", "extortion",
    "robbery", "took my phone", "khap",
    "acid", "acid attack", "chemical attack", "threw something on my face",
    "eyes are burning", "eyes burning",
)
_CYBER_WORDS = (
    "cyber", "hacked", "facebook", "instagram", "whatsapp", "otp",
    "phishing", "upi", "credit card", "debit card", "online transaction",
    "deepfake", "fake account", "sextortion", "upload", "uploaded",
    "secretly recorded", "recorded us", "scam", "digital arrest",
    "parcel has drugs", "fake cbi", "fake police call",
    "dick pic", "bumble", "leaked my chat", "leaked chat",
    "mental health privacy", "privacy leak", "insta", "dm daily",
        "after blocking", "stalker", "stalking", "tinder", "extortion",
    "tweet", "twitter", "x.com", "online post", "social media post",
    "rugpull", "rugpulled",
)
_INTIMATE_IMAGE_WORDS = (
    "private photo", "private photos", "private picture", "private pictures",
    "private video", "private videos", "intimate photo", "intimate photos",
    "intimate video", "intimate videos", "nude photo", "nude photos",
    "nudes", "morphed photo", "morphed photos", "leaked photo",
    "leaked photos", "deepfake", "sex video", "porn video",
    "morphed image", "morphed images", "morphed pic", "morphed pics",
    "morphed group photo", "morphed group photos", "ai porn",
    "onlyfans content",
)
_IMAGE_ABUSE_CONTEXT_WORDS = (
    "send to", "send it to", "send my", "send our", "send her", "send his",
    "share my", "share our", "show my", "show our", "forward my",
    "forward our", "upload", "uploaded", "post online", "posted", "posting",
    "leak", "leaked", "blackmail", "threat", "threaten", "threatens",
    "threatened", "threatening", "telegram", "whatsapp", "instagram",
    "facebook", "reddit", "hostel", "college group", "circulate",
    "circulating",
)
_INTIMATE_IMAGE_RISK_WORDS = (
    "ex", "boyfriend", "girlfriend", "bf", "gf", "partner", "stranger",
    "unknown person", "online friend", "has my nudes", "has our nudes",
    "has my nude", "has my private photo", "has my private photos",
    "has my intimate", "saved my nudes", "kept my nudes", "lookalike",
    "look alike", "face same", "not me but face", "featuring me",
)
_INTIMATE_IMAGE_SERVICE_WORDS = (
    "photographer", "wedding", "family photo", "photo shoot", "photoshoot",
    "album", "designer", "studio", "refund", "lost", "defective", "service",
)
_CONSUMER_WORDS = (
    "refund", "defective", "damaged", "broken", "delivery",
    "consumer", "warranty", "insurance claim", "bad food", "doctor negligence",
    "builder", "possession", "rera", "customer support", "extra fare",
    "charged extra fare", "longer route", "deactivate no response",
    "closing complaint", "deactivate", "service complaint",
    "medical negligence", "hospital negligence", "wrong injection",
    "doctor gave", "patient died compensation", "hospital bill",
    "icu", "without consent", "refused to treat",
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
    "untouchable", "caste discrimination", "temple entry", "cannot enter temple",
    "not allowed temple", "prevented temple",
    "forest rights", "forest department", "fra 2006", "fra claim",
    "gram sabha", "pesa", "st certificate", "gond",
    "munda", "agency village",
    "ifr title", "ifr claim", "cfr title", "community forest", "minor forest produce",
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
    "district court", "affidavit", "notarised", "notarized", "notary",
    "litigant in person", "party in person", "wear to court",
    "what should i wear", "appearing first time",
)
_WORK_INJURY_WORDS = (
    "construction site", "worksite", "factory accident", "site accident",
    "fell from", "fell down", "leg broken", "hand broken", "boiler burst",
    "silicosis", "contractor injury",
    "no insurance from company", "lost hand", "lost arm", "amputation",
    "hand cut", "hand crushed",
)
_BAIL_WORDS = (
    "anticipatory bail", "regular bail", "default bail", "interim bail",
    "bail", "arrested", "arrest notice", "notice for arrest",
    "chargesheet", "charge sheet", "custody limit", "custody period",
    "judicial custody", "police custody", "remand",
    "mcoca", "uapa", "narcotic", "narcotics",
)
_NDPS_PERSONAL_USE_WORDS = (
    "ndps", "narcotic", "narcotics", "ganja", "charas", "mdma",
    "heroin", "cannabis", "weed", "hash", "cbd", "thc", "thc oil",
    "vape", "vape pen", "vape cartridge",
)
_SOCIAL_WELFARE_WORDS = (
    "aadhaar", "aadhar", "pension", "scholarship", "ration card",
    "pds", "ration shop", "biometric",
    "benefit stopped", "widow pension", "old age pension",
    "disability pension", "caste certificate", "income certificate",
    "birth certificate", "birth registration", "death certificate",
    "sc scholarship", "st scholarship", "obc scholarship", "rte quota",
    "kanya vivah", "kanyadan", "kanya bibaha", "vivah yojana",
    "marriage scheme", "scheme money", "government after my daughter wedding",
    "change my gender", "gender on aadhaar", "gender on aadhar",
    "transgender certificate", "transgender id",
)
_DISABILITY_ACCESS_WORDS = (
    "disability certificate", "disabled certificate", "udid", "unique disability id",
    "not making my disability", "wheelchair access", "sign language interpreter",
    "reasonable accommodation", "rpwd", "disabled cannot",
    "hearing impaired", "not providing interpreter", "providing interpreter",
    "missed important update", "60 percent disability", "disability terminated",
)
_SEXUAL_OFFENCE_SURVIVOR_WORDS = (
    "was raped", "raped by", "rape by", "molested me", "molested by",
    "sexual assault", "caretaker raped", "caretaker molested",
    "caretaker touched", "caretaker sexually", "visually impaired", "disabled girl",
    "minor girl", "minor daughter", "daughter touched", "teacher touched",
    "pocso complaint", "child raped", "pocso victim", "touching me since",
    "uncle touching", "neighbor uncle", "neighbour uncle",
)
_CHILD_MARRIAGE_WORDS = (
    "child marriage", "minor marriage", "underage marriage", "bal vivah",
    "married as child", "married as a child", "married at 14", "married at 15",
    "married at 16", "marry a minor",
)
_MARRIAGE_CONTEXT_WORDS = (
    "marriage", "married", "shaadi", "shadi", "nikah", "wedding",
    "fixing marriage", "got him married", "got her married",
)
_BONDED_LABOUR_WORDS = (
    "bonded labour", "bonded labor", "release certificate", "rehab money",
    "rehabilitation money", "brick kiln", "bhatta", "kiln owner", "hostage",
    "kept hostage", "keeping family hostage", "cannot go home", "cannot leave",
    "not letting leave", "advance", "loan finish", "debt bondage",
    "cards passport", "keeping our cards", "documents retained", "aadhaar original",
)
_FAMILY_SUPPORT_WORDS = (
    "left me with children", "left me with two small children",
    "left me with small children", "no money for school fees",
    "no money for children", "no money for child", "children no money",
    "maintenance for children", "child maintenance",
)
_ARREST_PRODUCTION_WORDS = (
    "magistrate ke samne", "magistrate ke saamne", "produce before magistrate",
    "produced before magistrate", "not produced", "24 hours", "twenty four hours",
    "5 din", "five days", "5 days", "kab le jana", "court ke samne",
)
_WITCH_BRANDING_WORDS = (
    "daayan", "dayan", "witch-branding", "tonhi",
    "daini", "labelled daayan", "branded witch",
)
_PRISON_RELEASE_WORDS = (
    "parole", "furlough", "remission", "premature release",
    "jail visit", "mulaqat", "prison visit", "open prison",
)
_WORKPLACE_SEXUAL_HARASSMENT_WORDS = (
    "posh", "sexual harassment", "boss touched", "manager touched",
    "colleague touched", "touches me", "late night meetings alone",
    "internal committee", "icc complaint", "local committee", "icc",
)
_REPRODUCTIVE_RIGHTS_WORDS = (
    "abortion", "terminate pregnancy", "termination of pregnancy", "mtp",
    "pregnant after rape", "pregnancy after rape", "too late for abortion",
)
_TAX_GST_WORDS = (
    "gst", "cgst", "gstr", "tds", "26as", "income tax", "itr",
    "register gst", "tax notice", "form 26as", "itat", "cit(a)",
    "cit appeal", "commissioner appeals", "assessment order",
    "customs", "icegate", "bill of entry", "shipping bill",
    "drawback", "import duty", "customs duty", "duty demand",
    "classification dispute", "reclassified", "shipment held at port",
    "capital gains", "54f", "80c", "80ccd", "nps",
    "tcs", "foreign remittance", "remittance", "206c",
    "rule 86b", "86b", "1% cash", "1 percent cash", "one percent cash",
)
_CUSTOMS_TAX_WORDS = (
    "customs", "icegate", "bill of entry", "shipping bill", "drawback",
    "import duty", "customs duty", "customs broker", "port hold",
    "duty demand", "classification dispute", "reclassified",
    "shipment held at port",
)
_INCOME_TAX_APPEAL_WORDS = (
    "itat", "cit(a)", "cit appeal", "commissioner appeals",
    "income tax appeal", "assessment order", "143(3)", "section 143",
    "section 147", "tax demand appeal",
)
_VOTER_RIGHTS_WORDS = (
    "voter id", "voter list", "electoral roll", "booth officer",
    "denied me vote", "denied vote", "name spelt wrong", "name spelled wrong",
    "epic card", "election id",
)
_ELECTION_CANDIDATE_WORDS = (
    "nomination rejected", "nomination paper", "returning officer",
    "contest election", "stand for election", "candidate disqualified",
    "candidate disqualification", "disqualification on conviction",
    "election petition", "corrupt practice", "booth capturing",
    "vote recount", "election recount", "recounting of votes",
    "counting agent", "symbol allotment", "model code of conduct",
    "mcc violation",
    "affidavit assets", "mla election", "mp election", "lok sabha",
    "vidhan sabha", "legislative assembly", "parliament election",
)
_FAMILY_MARRIAGE_STATUS_WORDS = (
    "second wife", "second marriage", "without divorcing me", "first marriage",
    "bigamy", "another wife", "took second wife", "triple talaq",
    "talaq-e-biddat", "instant talaq", "talaq on whatsapp",
)
_IBC_WORDS = (
    "ibc", "insolvency", "nclt", "operational creditor",
    "section 9 ibc", "section 7 ibc", "corporate debtor",
)
_BUSINESS_CONTRACT_WORDS = (
    "partnership", "partner", "mou", "exclusivity", "dealer",
    "non compete", "non-compete", "personal liability", "contract clause",
    "specific performance", "co founder", "co-founder", "dilute my equity",
    "diluting my equity", "esop", "minority shareholder", "shareholder oppressing",
    "inspection of registers", "principal agent", "principal-agent",
    "agent took my goods", "agent absconded",
    "nda", "non disclosure", "non-disclosure", "customer list",
    "trade secret", "trade secrets", "joined competitor",
    "delivery partner agreement", "commission dispute",
    "invoice", "client not paying", "not paying invoice", "saas work",
    "buyer deducting payment", "quality issue", "formal rejection",
    "lakh stuck", "msme payment",
    "payment delay", "45 days payment", "amount outstanding",
    "samadhan", "samadhaan", "msefc", "msme registered",
    "msme registered party", "msme samadhan portal", "public sector buyer",
    "psu not paid", "commercial court", "pre litigation mediation",
    "pre-litigation mediation", "vendor agreed", "recover advance",
    "cancel and recover", "delivery in 30 days", "supplier failed",
    "failed to deliver", "did not deliver", "machinery", "equipment",
    "goods delivery",
    "fanvue payment", "creator payment", "creator payout",
    "platform payout", "usd payment", "foreign platform payment",
    "payment frozen", "release fund",
)
_BUSINESS_LICENSE_WORDS = (
    "shop license", "shop act", "licence renewal", "license renewal", "shops and establishments",
    "trade license", "factory license", "establishment registration",
    "fssai", "food licence", "food license", "snack manufacturing",
    "food safety officer", "adulteration", "misbranding", "designated officer",
    "improvement notice", "food sample", "sample collected", "kirana",
    "auto permit", "transport permit", "permit renewal", "permit expired",
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
    "took our daughter", "took our child", "not letting me meet",
    "not letting us meet", "not bringing back", "tourist visa",
    "child custody", "international child", "custody petition",
    "minor child", "parents in law took", "in laws took", "wife died",
    "supervised visitation", "unsupervised visitation", "visitation for my daughter",
    "visitation for my son", "visitation order",
)
_CIVIL_PROCEDURE_WORDS = (
    "order 21", "order xxi", "execution petition", "decree holder",
    "execute decree", "execution of decree", "substantial question of law",
    "second appeal", "section 100 cpc", "cpc 100", "section 24 cpc",
    "first appeal", "section 96 cpc", "cpc 96",
    "transfer of case", "case transfer", "civil procedure",
    "order 7 rule 11", "order vii rule 11", "condonation of delay",
)
_UNDERTRIAL_REVIEW_WORDS = (
    "bnss 479", "479 bnss", "section 479", "undertrial review",
    "undertrial prisoner review", "undertrial release", "436a",
    "half of maximum", "one half of maximum", "one-third of maximum",
    "half sentence", "half maximum", "completed half", "maximum punishment",
    "trial not started", "long custody", "jail since", "spent half",
    "one third", "one-third",
)
_SURROGACY_WORDS = (
    "surrogacy", "surrogate", "baby through surrogate",
    "surrogate mother", "commercial surrogacy", "altruistic surrogacy",
    "surrogacy agent", "surrogacy clinic", "intending couple",
    "intending woman",
)
_MUTUAL_CONSENT_DIVORCE_WORDS = (
    "mutual consent divorce", "section 13b", "13b divorce",
    "both agree divorce", "both me and husband agree",
    "both me and wife agree", "we both agree divorce",
)
_LABOUR_EXPLOITATION_WORDS = (
    "nrega", "mgnrega", "asha worker", "honorarium", "cards passport",
    "keeping our cards", "bonded labour", "women workers", "half pay",
    "biharee", "racist", "wrongfully terminated", "terminated from job",
    "migrant worker", "inter state migrant", "inter-state migrant",
    "go back home", "return ticket", "walked from", "domestic worker",
    "madam not paying", "muster roll", "fake muster", "bdo putting my name",
    "factory deducted", "deducted 800", "wage deducted", "uniform never given",
    "shoes uniform", "job card", "job cards", "mukhiya", "munshi",
    "no payment", "bocw card", "bocw", "cess", "ismw",
    "inter-state migrant workmen", "inter state migrant workmen",
    "migrant registration", "displacement allowance", "came together",
    "minimum wage", "minimum wages", "state rate", "unskilled",
)
_ENVIRONMENT_WORDS = (
    "thermal plant", "blasting", "cracking our houses", "pollution",
    "environment", "factory pollution", "mining company", "iron ore",
    "iron ore mine", "mine displaced", "mine displacement",
    "mining displacement",
    "borewell water", "water pollution", "throwing chemicals",
    "chemicals", "bad water", "dam", "land acquisition", "project displaced",
    "displaced by", "displacement compensation", "highway project",
    "dam project", "rehabilitation and resettlement",
    "resettlement compensation", "rehabilitation package after acquisition",
    "no rehabilitation", "land acquired", "acquired for", "coal block", "palli sabha",
    "bauxite project", "mining project", "without gram sabha",
    "land taken for highway", "taken for highway", "highway compensation",
)
_PMLA_ED_WORDS = (
    "pmla", "enforcement directorate", "ecir", "twin condition",
    "money laundering",
)
_BANKING_CREDIT_WORDS = (
    "bank wrongly debited", "forex transaction", "bank not giving noc",
    "cibil", "credit score", "loan tenure", "banking ombudsman",
    "bank kyc", "bank account frozen", "bank account froze",
    "savings account frozen", "current account frozen", "nbfc kyc",
    "rbi ombudsman", "bank account kyc",
    "fd", "fixed deposit", "nominee", "loan against my house",
    "didn't sign", "did not sign", "sarfaesi", "13(2) notice",
    "home loan default", "security interest", "possession notice",
    "nbfc", "recovery agent", "recovery agents", "loan recovery",
    "bajaj finserv", "emi bounced", "emi bounce", "bank error",
    "threatening cibil", "threaten cibil",
)
_DIGITAL_PLATFORM_WORDS = (
    "uber deactivated", "account froze", "kyc pending", "online gaming",
    "app froze", "page suspended", "instagram suspended", "meta",
    "account deactivated", "account suspended", "rider deactivated",
    "driver deactivated", "zomato deactivated", "swiggy deactivated",
    "id blocked", "profile blocked", "rider id blocked", "driver id blocked",
    "wallet froze", "wallet frozen", "binance froze", "usdt wallet",
    "dream11", "parimatch", "betting app", "rummy app",
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

    specific_route = _specific_high_risk_surface_route(q)
    if specific_route is not None:
        return specific_route

    priority_route = _priority_route(q)
    if priority_route is not None:
        return priority_route

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

    if _is_digital_device_police_seizure(q):
        return MatterRoute(
            category="police_fir",
            label="Police seizure of digital device",
            confidence=0.80,
            urgency="high",
            required_sources=[
                "BNSS 2023 / CrPC 1973 search, seizure, production, and court-supervision procedure based on incident date",
                "Information Technology Act 2000 where computer resources, electronic records, or social-media material are involved",
                "BSA 2023 / Evidence Act electronic-record rules where device data is used as evidence",
            ],
            forums=["investigating officer/police station", "criminal court or Magistrate", "District Legal Services Authority"],
            missing_facts=["seizure memo or notice", "case/FIR number", "device owner/user", "whether you are accused, witness, employer, or third party", "data needed urgently for work"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_ndps_personal_use_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="NDPS / alleged drug possession defence",
            confidence=0.80,
            urgency="high",
            required_sources=[
                "NDPS Act 1985 for alleged narcotic or psychotropic substance possession",
                "BNSS 2023 / CrPC 1973 search, seizure, arrest, bail, and complaint procedure based on incident date",
                "customs/airport or passport procedure only if an order or travel-document seizure is involved",
            ],
            forums=[
                "criminal court",
                "investigating officer/police station",
                "legal aid/lawyer",
                "Regional Passport Office only for a passport-seizure order",
            ],
            missing_facts=[
                "substance named in seizure memo",
                "quantity",
                "FIR/notice sections",
                "whether arrest or passport seizure order exists",
                "incident date and airport/police station",
            ],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
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

    if _is_lok_adalat_traffic_settlement(q):
        return MatterRoute(
            category="legal_aid",
            label="Lok Adalat traffic challan settlement",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Legal Services Authorities Act 1987 Lok Adalat provisions",
                "traffic challan / e-challan record for the pending matter",
            ],
            forums=["District Legal Services Authority", "traffic Lok Adalat / referring traffic court", "traffic police e-challan portal"],
            missing_facts=["state/city", "challan number", "vehicle number", "pending court/e-challan status", "next Lok Adalat date"],
            red_flags=[],
            action_pack=_legal_aid_pack(),
        )

    if _is_interim_medical_bail_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Custody medical care / interim bail",
            confidence=0.86,
            urgency="high",
            required_sources=[
                "Article 21 constitutional custody-health and dignity safeguards",
                "BNSS 2023 / CrPC 1973 bail and custody provisions based on incident date",
                "court/prison medical-care and pregnancy-in-custody safeguards where available",
            ],
            forums=["criminal court", "jail superintendent", "District Legal Services Authority", "High Court writ jurisdiction"],
            missing_facts=["custody start date", "jail/prison name", "pregnancy or medical condition records", "doctor requests/refusals", "case/offence sections", "prior bail orders"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_undertrial_review_issue(q):
        return MatterRoute(
            category="undertrial_review_release",
            label="Undertrial custody review / release eligibility",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "BNSS 2023 section 479 for current undertrial custody-review limits",
                "CrPC 1973 section 436A for legacy / transitional comparison",
                "Legal Services Authorities Act 1987 and undertrial review committee procedure",
            ],
            forums=["trial court", "jail superintendent", "District Legal Services Authority / Under Trial Review Committee", "High Court writ jurisdiction where delay is unlawful"],
            missing_facts=["offence sections", "maximum punishment alleged", "custody start date", "chargesheet/trial stage", "prior bail orders", "age/illness/vulnerability facts"],
            red_flags=_red_flags(q),
            action_pack=_undertrial_review_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_child_marriage(q):
        return MatterRoute(
            category="child_marriage_protection",
            label="Child marriage prevention / annulment",
            confidence=0.86,
            urgency="emergency" if _has_any(q, ("stop", "tonight", "today", "tomorrow", "forcing", "fixing")) else "high",
            required_sources=[
                "Prohibition of Child Marriage Act 2006",
                "POCSO Act 2012 where sexual activity or child sexual offence risk is involved",
                "BNS/BNSS or IPC/CrPC based on incident date where force, kidnapping, assault, or threats are involved",
            ],
            forums=["Childline 1098 / child helpline", "Child Welfare Committee", "police station", "District Legal Services Authority"],
            missing_facts=["child age/date of birth", "marriage date or planned date", "current location and safety", "who is forcing or arranging it", "district/state"],
            red_flags=_red_flags(q),
            action_pack=_child_marriage_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_arrest_production_delay(q) or _is_custody_restraint_issue(q) or _is_arrest_information_safeguard(q):
        return MatterRoute(
            category="arrest_custody_safeguard",
            label="Arrest / production before Magistrate",
            confidence=0.82,
            urgency="emergency",
            required_sources=[
                "BNSS 2023 arrest and 24-hour production safeguards for current matters",
                "CrPC 1973 arrest and 24-hour production safeguards for pre-1 July 2024 matters",
                "constitutional liberty safeguards under Articles 21 and 22",
            ],
            forums=["nearest Magistrate/criminal court", "District Legal Services Authority", "senior police officer", "High Court writ jurisdiction for unlawful detention"],
            missing_facts=["arrest date and time", "police station", "FIR/offence details", "whether family was informed", "whether any remand order exists"],
            red_flags=_red_flags(q),
            action_pack=_custody_safeguard_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_custody_legal_aid_access_issue(q):
        return MatterRoute(
            category="legal_aid",
            label="Custody legal aid / lawyer access",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "Legal Services Authorities Act 1987 custody-stage legal-aid entitlement",
                "Article 21 and Article 22 lawyer-access safeguards",
                "BNSS/CrPC arrest and remand procedure based on incident date",
            ],
            forums=["District Legal Services Authority", "jail legal-aid clinic", "trial court", "High Court writ jurisdiction where access is blocked"],
            missing_facts=["jail/police station", "arrest/remand date", "case/FIR details", "lawyer appointment status", "who refused the meeting", "next hearing date"],
            red_flags=_red_flags(q),
            action_pack=_legal_aid_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_custodial_violence_issue(q):
        return MatterRoute(
            category="police_fir",
            label="Custodial violence / police extortion",
            confidence=0.84,
            urgency="emergency",
            required_sources=[
                "Article 21 and custodial-violence safeguards",
                "BNS/BNSS or IPC/CrPC based on incident date",
                "human-rights commission / police complaint authority procedure",
            ],
            forums=["senior police officer", "Judicial Magistrate", "Human Rights Commission", "District Legal Services Authority"],
            missing_facts=["detention/arrest date and police station", "injury/medical records", "officer details", "money demanded or paid", "current custody/release status"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_caste_bonded_labour_issue(q):
        return MatterRoute(
            category="tribal_caste_atrocity",
            label="Caste-linked forced labour / atrocity risk",
            confidence=0.76,
            urgency="high",
            required_sources=[
                "Bonded Labour System (Abolition) Act 1976 where work is tied to debt, coercion, or unpaid subsistence",
                "SC/ST (Prevention of Atrocities) Act 1989 only if the victim is Scheduled Caste or Scheduled Tribe and caste targeting is shown",
                "Code on Wages / labour law for unpaid wages",
            ],
            forums=[
                "District Magistrate/Sub-Divisional Magistrate",
                "Labour Commissioner",
                "police station or Special Court where SC/ST facts exist",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "victim caste/community status",
                "worksite and district/state",
                "employer/landlord details",
                "wage/debt facts",
                "threats or confinement",
                "whether any caste words or acts were used",
            ],
            red_flags=_red_flags(q),
            action_pack=_tribal_caste_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, _CRIME_WORDS) else None,
        )

    if _is_bonded_labour_rescue(q):
        return MatterRoute(
            category="bonded_labour_rescue",
            label="Bonded labour / forced labour rescue",
            confidence=0.84,
            urgency="emergency" if _has_any(q, ("hostage", "cannot go home", "cannot leave", "locked", "wife sick")) else "high",
            required_sources=[
                "Bonded Labour System (Abolition) Act 1976",
                "Inter-State Migrant Workmen Act 1979 where recruitment or movement across states is involved",
                "Code on Wages / labour law where unpaid wages or contractor dues are involved",
                "BNS/BNSS or IPC/CrPC based on incident date where confinement, assault, threats, or document retention are involved",
            ],
            forums=["District Magistrate/Sub-Divisional Magistrate", "Labour Commissioner", "police station", "District Legal Services Authority"],
            missing_facts=["worksite and district/state", "contractor/employer name", "advance/debt amount", "documents retained", "people confined or threatened", "wage and movement restrictions"],
            red_flags=_red_flags(q),
            action_pack=_bonded_labour_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_disability_access(q):
        return MatterRoute(
            category="disability_access",
            label="Disability certificate / accessibility rights",
            confidence=0.80,
            urgency="high" if _has_any(q, ("cannot walk", "abuse", "violence", "no medicine")) else "medium",
            required_sources=[
                "Rights of Persons with Disabilities Act 2016",
                "state disability certificate / UDID procedure",
                "Legal Services Authorities Act 1987 where legal aid is needed",
            ],
            forums=["district medical board / certifying medical authority", "UDID or state disability portal", "District Social Welfare Office", "District Legal Services Authority"],
            missing_facts=["state/district", "disability type", "application or UDID number", "medical documents submitted", "written refusal or delay proof"],
            red_flags=_red_flags(q),
            action_pack=_disability_access_pack(),
        )

    if _is_esi_benefit_issue(q):
        return MatterRoute(
            category="employment_wages",
            label="ESI benefit / insured-person treatment dispute",
            confidence=0.78,
            urgency="high" if _has_any(q, ("delivery", "emergency", "refused to treat")) else "medium",
            required_sources=["Employees' State Insurance Act 1948", "ESI medical-benefit and contribution eligibility procedure", "labour/DLSA grievance route"],
            forums=["ESI Corporation branch office", "ESI hospital medical superintendent", "Employees' Insurance Court", "DLSA / District Legal Services Authority"],
            missing_facts=["ESI insurance number", "contribution period", "employer details", "hospital/refusal date", "written refusal or eligibility reason"],
            red_flags=_red_flags(q),
            action_pack=_employment_pack(),
        )

    if _is_witch_branding_violence(q):
        return MatterRoute(
            category="criminal_general",
            label="Criminal law / safety",
            confidence=0.74,
            urgency="emergency" if _has_any(q, ("beaten", "mob", "attack", "attacked", "village people")) else "high",
            required_sources=[
                "BNS/BNSS or IPC/CrPC based on incident date",
                "SC/ST Act where caste or tribal status is part of the targeting",
                "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given",
            ],
            forums=["police station", "senior police officer", "District Legal Services Authority", "state women/social welfare authority where applicable"],
            missing_facts=["state/district", "incident date and place", "injury/medical proof", "who used the witch-branding words", "caste/tribal status if relevant"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_voter_rights_issue(q):
        return MatterRoute(
            category="election_voter_rights",
            label="Voter ID / electoral-roll rights",
            confidence=0.76,
            urgency="medium",
            required_sources=["Representation of the People Act 1950 / election rules where voter-list correction or denial of vote is involved", "Election Commission voter-services procedure"],
            forums=["Electoral Registration Officer / Booth Level Officer", "voters.eci.gov.in", "District Election Officer", "District Legal Services Authority"],
            missing_facts=["state/assembly constituency", "EPIC/voter ID number", "polling booth details", "error in name/roll", "written refusal or election date"],
            red_flags=[],
            action_pack=_voter_rights_pack(),
        )

    if _is_election_candidate_issue(q):
        return MatterRoute(
            category="election_candidate_dispute",
            label="Election candidate / petition procedure",
            confidence=0.76,
            urgency="high" if _has_any(q, ("nomination rejected", "petition deadline", "counting", "recount")) else "medium",
            required_sources=[
                "Representation of the People Act 1951 for candidate qualification, disqualification, nominations, corrupt practices, and election petitions",
                "Election Commission procedure / Conduct of Election Rules where forms, affidavits, symbols, or counting procedure are involved",
            ],
            forums=["Returning Officer / District Election Officer", "Election Commission / Chief Electoral Officer", "High Court election-petition jurisdiction", "District Legal Services Authority"],
            missing_facts=["election type and constituency", "candidate/voter status", "order or notice date", "nomination/petition/counted-votes documents", "deadline or result declaration date"],
            red_flags=[],
            action_pack=_election_candidate_pack(),
        )

    if _is_elder_financial_fraud_issue(q):
        return MatterRoute(
            category="senior_citizen",
            label="Senior citizen financial abuse / mis-selling",
            confidence=0.76,
            urgency="medium",
            required_sources=[
                "Maintenance and Welfare of Parents and Senior Citizens Act 2007 where an elderly parent is exploited",
                "Consumer Protection Act 2019 where financial or telecom service deficiency/mis-selling applies",
                "BNS/BNSS or IPC/CrPC where cheating or criminal breach of trust is alleged",
            ],
            forums=["Maintenance Tribunal / District Magistrate", "National Consumer Helpline or consumer forum", "police/cyber cell where cheating is alleged", "District Legal Services Authority"],
            missing_facts=["age and relationship", "amount/value", "policy/service documents", "who sold or took the money/property", "complaints already filed"],
            red_flags=_red_flags(q),
            action_pack=_senior_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("fraud", "cheating", "took", "stolen", "jewellery")) else None,
        )

    if _is_bank_or_pension_impersonation_fraud(q):
        return MatterRoute(
            category="cyber_fraud_or_harassment",
            label="Bank / pension impersonation fraud",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "Information Technology Act 2000 identity-theft / cheating by personation provisions",
                "BNS 2023 / IPC 1860 cheating and fraud provisions based on incident date",
                "BNSS 2023 / CrPC 1973 complaint/FIR procedure",
            ],
            forums=["bank fraud desk", "National Cyber Crime Portal / cyber police station", "local police station", "District Legal Services Authority"],
            missing_facts=["call number and time", "bank account and transaction IDs", "amount and beneficiary account/UPI", "screenshots/recordings", "bank complaint number", "victim age and relationship"],
            red_flags=_red_flags(q),
            action_pack=_cyber_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_civil_registration_record_issue(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="Civil registration / identity record",
            confidence=0.76,
            urgency="medium",
            required_sources=[
                "Registration of Births and Deaths Act 1969 or state civil-registration rules where locally available",
                "Right to Information Act 2005 for written status, reasons, and first appeal",
                "panchayat/municipal registrar procedure for delayed or home-birth registration",
            ],
            forums=["Registrar of Births and Deaths / panchayat or municipal registrar", "block development or municipal office", "DLSA / District Legal Services Authority"],
            missing_facts=["state/district", "birth/death date and place", "hospital or home-birth proof", "application/receipt number", "written refusal or delay reason"],
            red_flags=_red_flags(q),
            action_pack=_social_welfare_pack(),
        )

    if _is_education_loan_denial(q):
        return MatterRoute(
            category="education_loan_denial",
            label="Education loan / scholarship-linked denial",
            confidence=0.76,
            urgency="medium",
            required_sources=[
                "RBI/banking grievance and ombudsman procedure for education-loan refusal",
                "scholarship or education-department scheme rules where the scholarship paper is relied on",
                "Consumer Protection Act 2019 where bank service deficiency is alleged",
            ],
            forums=["bank branch/grievance officer", "RBI Ombudsman", "district education or scholarship authority", "District Legal Services Authority"],
            missing_facts=["bank name", "course/school and student age", "loan application number", "written refusal reason", "scholarship document", "complaint acknowledgement"],
            red_flags=_red_flags(q),
            action_pack=_education_loan_pack(),
        )

    if _is_trans_identity_certificate_issue(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="Transgender identity certificate / ID correction",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Transgender Persons (Protection of Rights) Act 2019 certificate of identity provisions",
                "Aadhaar Act / UIDAI correction procedure where Aadhaar gender data is involved",
                "school board or education-record correction rules for marksheet/certificate changes",
            ],
            forums=["District Magistrate / transgender certificate portal", "Aadhaar Seva Kendra/UIDAI grievance", "school board/education department", "District Legal Services Authority"],
            missing_facts=["state/district", "whether a transgender certificate was applied for", "Aadhaar enrolment number", "school board/class 10 certificate details", "written refusal reason if any"],
            red_flags=_red_flags(q),
            action_pack=_social_welfare_pack(),
        )

    if _has_any(q, _SOCIAL_WELFARE_WORDS) and not (
        _has_any(q, _EDUCATION_WORDS) and not _has_any(q, ("scholarship",))
    ):
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

    if _is_cab_aggregator_driver_issue(q):
        return MatterRoute(
            category="digital_platform_account",
            label="Cab aggregator driver deactivation / platform account",
            confidence=0.82,
            urgency="medium" if not _has_any(q, ("money stuck", "earning", "lakh")) else "high",
            required_sources=[
                "Motor Vehicle Aggregator Guidelines 2020/2025 for driver contract, grievance, and aggregator licensing duties",
                "Motor Vehicles Act 1988 aggregator licensing provisions",
                "Consumer Protection Act / platform grievance route where service deficiency is alleged",
                "labour or equality remedies where the deactivation is linked to language, region, caste, or race",
            ],
            forums=["platform grievance officer/help centre", "state transport department / RTO aggregator licensing authority", "consumer forum/e-Daakhil where service deficiency applies", "Labour Commissioner or DLSA where discrimination or unpaid dues are involved"],
            missing_facts=["platform/app name", "driver/account ID", "deactivation notice/reason", "ratings and trip history", "support ticket or appeal number", "unpaid earnings if any"],
            red_flags=_red_flags(q),
            action_pack=_digital_platform_pack(),
        )

    if _is_digital_platform_issue(q):
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
                "porn video", "lookalike", "face same", "reddit",
            )) or _is_intimate_image_emergency(q) else "high",
            required_sources=_cyber_required_sources(q),
            forums=["National Cyber Crime Portal", "1930 cyber helpline", "local police station"],
            missing_facts=["incident date", "platform", "amount lost", "whether money is still moving", "screenshots/transaction IDs"],
            red_flags=_red_flags(q),
            action_pack=_cyber_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_surrogacy_issue(q):
        return MatterRoute(
            category="surrogacy_parenthood",
            label="Surrogacy / assisted parenthood eligibility",
            confidence=0.78,
            urgency="medium",
            required_sources=[
                "Surrogacy (Regulation) Act 2021",
                "Assisted Reproductive Technology law/rules where clinic or ART procedure is involved",
                "Medical Termination of Pregnancy Act 1971 where abortion or termination facts are involved",
                "medical board / appropriate authority procedure",
            ],
            forums=["appropriate authority under surrogacy/ART law", "registered clinic/hospital", "District Legal Services Authority"],
            missing_facts=["marital status", "ages of intending parents", "medical indication such as infertility or hysterectomy", "surrogate relationship/eligibility", "clinic registration and certificates obtained", "payments, agent, compensation, or insurance facts if money is involved"],
            red_flags=_red_flags(q),
            action_pack=_surrogacy_pack(),
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

    if _is_pmla_bail_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="PMLA bail / anticipatory or interim bail",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Prevention of Money Laundering Act 2002 bail and arrest provisions",
                "BNSS 2023 / CrPC 1973 bail procedure based on incident date",
                "constitutional liberty and medical/vulnerability bail principles",
            ],
            forums=["Special PMLA Court", "High Court", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
            missing_facts=["summons/arrest status", "scheduled offence/ECIR details", "custody date", "medical/pregnancy/newborn facts if interim bail", "prior bail orders"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _has_pmla_ed_context(q):
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

    if _is_manual_scavenging_issue(q):
        return MatterRoute(
            category="manual_scavenging_safety",
            label="Manual scavenging / sewer or septic-tank safety",
            confidence=0.84,
            urgency="emergency" if _has_any(q, ("died", "death", "dead", "no safety")) else "high",
            required_sources=[
                "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013",
                "BNS/BNSS or IPC/CrPC where coercion, assault, or death is involved",
                "labour/municipal safety and compensation procedure",
            ],
            forums=["District Magistrate", "local authority/municipality", "police station where coercion or death is involved", "District Legal Services Authority"],
            missing_facts=["district/local body", "work type", "who forced or employed workers", "photos/witnesses", "injury/death and compensation facts"],
            red_flags=_red_flags(q),
            action_pack=_manual_scavenging_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, _CRIME_WORDS) else None,
        )

    if _is_accused_scst_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="SC/ST Act accused defence / false-case claim",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "SC/ST (Prevention of Atrocities) Act 1989 including anticipatory-bail restrictions and exceptions",
                "BNSS 2023 / CrPC 1973 bail and quashing procedure based on incident date",
                "relevant Supreme Court precedents on prima facie scrutiny in SC/ST Act cases",
            ],
            forums=["Special Court under SC/ST Act", "High Court where quashing/anticipatory bail is considered", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
            missing_facts=["FIR sections and date", "accusation facts", "caste/status allegations", "arrest/notice status", "evidence showing false implication"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_tribal_project_displacement_issue(q):
        return MatterRoute(
            category="environment_compensation",
            label="Tribal project displacement / Gram Sabha consent",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "PESA Act 1996 Gram Sabha consultation/consent provisions where the villages are in Scheduled Areas",
                "RFCTLARR Act 2013 rehabilitation, resettlement, compensation, and Scheduled Area safeguards",
                "project/acquisition notices only to identify the operator, land, and displacement record",
            ],
            forums=["Collector / R&R authority", "district rehabilitation office", "Gram Sabha / Panchayat channel where Scheduled Area rights apply", "tribal welfare authority", "District Legal Services Authority"],
            missing_facts=["state/district and Scheduled Area status", "project/acquisition notice", "affected village/family list", "Gram Sabha notice/minutes or absence of consent", "rehabilitation/compensation award status"],
            red_flags=_red_flags(q),
            action_pack=_tribal_project_displacement_pack(),
        )

    if _is_tribal_caste_issue(q):
        if _is_tribal_land_transfer_issue(q):
            return MatterRoute(
                category="tribal_caste_atrocity",
                label="Tribal land transfer / restoration",
                confidence=0.80,
                urgency="high",
                required_sources=[
                    "state tenancy / scheduled-area land-transfer law such as CNT/SPT where the land is in Jharkhand",
                    "Constitution Article 244 / Fifth Schedule Scheduled Area framework where applicable",
                    "PESA Act / Forest Rights Act where Gram Sabha or forest-rights facts apply",
                ],
                forums=["Deputy Commissioner / Collector or revenue authority", "tribal welfare authority", "civil court where title is disputed", "District Legal Services Authority"],
                missing_facts=["state and district", "land record/khata details", "tribal status documents", "sale/transfer deed date", "who signed and whether permission was taken"],
                red_flags=_red_flags(q),
                action_pack=_tribal_caste_pack(),
                legal_regime=None,
            )
        if _is_untouchability_civil_rights_issue(q):
            return MatterRoute(
                category="tribal_caste_atrocity",
                label="Untouchability / temple or water access",
                confidence=0.82,
                urgency="high",
                required_sources=[
                    "Constitution Article 17 abolition of untouchability",
                    "Protection of Civil Rights Act 1955 for temple, well/water, and public-access disabilities",
                    "SC/ST (Prevention of Atrocities) Act 1989 where the victim is SC/ST and caste-targeting facts fit",
                ],
                forums=["police station", "District Legal Services Authority", "SC/ST protection cell or Special Court where applicable", "district social welfare / SC-ST welfare office"],
                missing_facts=["community/status proof", "incident date and location", "exact words/acts", "witnesses/video", "whether police complaint exists"],
                red_flags=_red_flags(q),
                action_pack=_tribal_caste_pack(),
                legal_regime=_criminal_regime(q) if _has_any(q, _CRIME_WORDS) else None,
            )
        return MatterRoute(
            category="tribal_caste_atrocity",
            label="Caste / tribal rights / targeted violence",
            confidence=0.76,
            urgency="emergency" if _has_any(q, ("attacked", "beat", "beaten", "mob", "violence", "threat", "burn", "kill")) else "high",
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

    if _is_security_cheque_defence_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Security cheque misuse / NI Act defence",
            confidence=0.80,
            urgency="high",
            required_sources=[
                "Negotiable Instruments Act 1881 sections 138 and 142 for dishonour notice and complaint limits",
                "bank account / stop-payment complaint records",
                "rent, loan, or security-deposit documents showing why the cheque was issued",
            ],
            forums=["bank branch/grievance officer", "Judicial Magistrate court if a notice or complaint is filed", "civil/rent court where the underlying liability is disputed", "District Legal Services Authority"],
            missing_facts=["cheque date and number", "bank return memo date if presented", "demand notice sent date if any", "15-day payment-window status", "security purpose and underlying liability proof"],
            red_flags=[],
            action_pack=_security_cheque_pack(),
        )

    if _is_elder_maintenance_cheque_issue(q):
        return MatterRoute(
            category="senior_citizen",
            label="Parent maintenance cheque / elder support",
            confidence=0.78,
            urgency="high",
            required_sources=[
                "Maintenance and Welfare of Parents and Senior Citizens Act 2007",
                "Negotiable Instruments Act 1881 sections 138 and 142 where a maintenance cheque is dishonoured",
                "BNSS/CrPC complaint procedure only if criminal process is involved",
            ],
            forums=["Maintenance Tribunal", "District Magistrate / senior-citizen cell where available", "Judicial Magistrate court if NI Act notice/complaint is pursued", "District Legal Services Authority"],
            missing_facts=["parent age and dependency", "maintenance arrangement/order if any", "cheque return memo date", "demand notice sent date if any", "15-day payment-window status"],
            red_flags=_red_flags(q),
            action_pack=_senior_maintenance_cheque_pack(),
        )

    if _is_cheque_bounce_issue(q):
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

    if _has_any(q, _TAX_GST_WORDS) or _has_any(q, _CUSTOMS_TAX_WORDS) or _has_any(q, _INCOME_TAX_APPEAL_WORDS):
        return MatterRoute(
            category="tax_gst_compliance",
            label="Tax / GST / TDS compliance",
            confidence=0.76,
            urgency="medium",
            required_sources=["CGST Act 2017 / GST registration rules where GST applies", "Income Tax Act 1961 for TDS, return, assessment, and appeal issues", "Customs Act 1962 where import/export, ICEGATE, duty, or drawback is involved", "RBI/banking records where payment proof matters"],
            forums=["GST portal/help desk", "Income Tax portal / ITAT where appeal is involved", "ICEGATE / customs officer or customs appellate route", "tax professional/legal-aid clinic for notices"],
            missing_facts=["state", "turnover/income amount", "nature of service/business/import/export", "notice/order or form number", "tax period and appeal deadline"],
            red_flags=[],
            action_pack=_tax_pack(),
        )

    if _is_motor_vehicle_traffic_police_issue(q):
        return MatterRoute(
            category="business_license_compliance",
            label="Motor vehicle licence / traffic-police dispute",
            confidence=0.76,
            urgency="medium",
            required_sources=[
                "Motor Vehicles Act 1988 for driving licence, challan, permit, and traffic enforcement",
                "state motor vehicle rules / traffic police e-challan procedure",
                "Prevention of Corruption Act 1988 where a public servant demands money without challan",
            ],
            forums=[
                "Regional Transport Office / state transport department",
                "traffic police grievance cell",
                "anti-corruption/Lokayukta channel where bribe is demanded",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "vehicle type and permit/licence number",
                "state that issued the licence",
                "place/date of demand or challan",
                "whether challan/receipt was issued",
                "officer name or badge if known",
            ],
            red_flags=_red_flags(q),
            action_pack=_business_license_pack(),
        )

    if _is_prohibition_excise_accused_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="State prohibition / excise accused procedure",
            confidence=0.72,
            urgency="high" if _has_any(q, ("arrest", "custody", "jail")) else "medium",
            required_sources=[
                "state Prohibition / Excise Act based on the state named in FIR or seizure memo",
                "BNSS 2023 / CrPC 1973 arrest, notice, bail, and complaint procedure based on incident date",
            ],
            forums=["criminal court", "police station/investigating officer", "District Legal Services Authority"],
            missing_facts=["state", "FIR/seizure memo sections", "quantity and place", "arrest/notice status", "whether bail was granted"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
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

    if _is_child_family_issue(q):
        if _is_supervised_visitation_issue(q):
            return MatterRoute(
                category="child_custody_adoption",
                label="Supervised visitation / custody-order modification",
                confidence=0.82,
                urgency="medium",
                required_sources=["Guardians and Wards Act custody welfare principles", "Family Courts Act jurisdiction/procedure", "existing custody or visitation order"],
                forums=["Family Court", "same court that passed the visitation order", "DLSA"],
                missing_facts=["child age", "existing supervised-visitation order", "next hearing/date", "safety concerns", "messages or request from the other side"],
                red_flags=_red_flags(q),
                action_pack=_supervised_visitation_pack(),
            )
        return MatterRoute(
            category="child_custody_adoption",
            label="Child custody / adoption / child return",
            confidence=0.76,
            urgency="high" if _has_any(q, ("uk", "not bringing back", "tourist visa", "not letting me meet", "blocked calls", "fast")) else "medium",
            required_sources=["Guardians and Wards Act / family law custody principles", "Juvenile Justice Act 2015 and adoption regulations where adoption papers are missing", "habeas corpus / child return precedents where child is removed across borders or urgently withheld"],
            forums=["Family Court", "District Child Protection Unit/CARA route where adoption is involved", "High Court writ jurisdiction for urgent child return", "DLSA"],
            missing_facts=["child age", "current location", "parent/guardian status", "orders/adoption papers", "travel documents"],
            red_flags=_red_flags(q),
            action_pack=_child_family_pack(),
        )

    if _is_business_contract_issue(q):
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

    if _is_business_license_issue(q):
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

    if _is_private_magistrate_complaint_issue(q):
        return MatterRoute(
            category="court_procedure",
            label="Private complaint / Magistrate police-inaction procedure",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "BNSS 2023 / CrPC 1973 private complaint and Magistrate investigation procedure based on incident date",
                "BNS 2023 / IPC 1860 offence provisions only after the alleged offence facts are known",
            ],
            forums=["Judicial Magistrate", "police station", "District Legal Services Authority", "lawyer/legal-aid clinic"],
            missing_facts=["incident date", "offence facts", "prior police complaint and acknowledgement", "police refusal/inaction proof", "witnesses and documents"],
            red_flags=_red_flags(q),
            action_pack=_court_procedure_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_simple_hurt_accused_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Simple hurt / assault accused defence",
            confidence=0.76,
            urgency="high" if _has_any(q, ("arrest", "notice", "police called")) else "medium",
            required_sources=["BNS 2023 / IPC 1860 hurt and assault provisions based on incident date", "BNSS 2023 / CrPC 1973 notice, bail, and complaint procedure"],
            forums=["police station/investigating officer", "criminal court", "District Legal Services Authority"],
            missing_facts=["incident date", "injury/medical facts", "FIR/notice sections if any", "witnesses/CCTV/messages", "whether compromise or mediation is being discussed"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_simple_hurt_complainant_issue(q):
        return MatterRoute(
            category="criminal_general",
            label="Simple hurt / assault complaint",
            confidence=0.70,
            urgency="high" if _has_any(q, ("threat", "injury", "hospital", "bleeding")) else "medium",
            required_sources=[
                "BNS 2023 / IPC 1860 hurt and assault provisions based on incident date",
                "BNSS 2023 / CrPC 1973 FIR, complaint, and medical-record procedure",
            ],
            forums=["police station", "senior police officer", "Judicial Magistrate", "District Legal Services Authority"],
            missing_facts=["incident date and place", "injury/medical facts", "witnesses/CCTV/messages", "whether police complaint or medical report already exists"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
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

    if _is_cheque_bounce_issue(q):
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

    if _is_labour_exploitation_issue(q):
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

    if _is_civil_procedure_issue(q):
        return MatterRoute(
            category="court_procedure",
            label="Civil court procedure / appeal / execution",
            confidence=0.78,
            urgency="medium",
            required_sources=["Code of Civil Procedure 1908", "Limitation Act 1963 where delay or appeal time is involved", "court rules and practice directions for the relevant court"],
            forums=["civil court / High Court filing counter", "District Legal Services Authority", "lawyer/legal-aid clinic"],
            missing_facts=["court and case number", "decree/order date", "appeal or execution stage", "limitation/deadline date", "copies of judgment, decree, or order"],
            red_flags=[],
            action_pack=_court_procedure_pack(),
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

    if _is_child_family_issue(q):
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

    if _is_family_marriage_status_issue(q):
        return MatterRoute(
            category="family_marriage_status",
            label="Marriage status / second marriage / family protection",
            confidence=0.76,
            urgency="high",
            required_sources=["personal law by religion", "BNS/IPC bigamy or cruelty provisions where applicable", "family maintenance and domestic-violence remedies where protection or support is needed"],
            forums=["Family Court", "Magistrate court where protection/maintenance/criminal complaint applies", "District Legal Services Authority"],
            missing_facts=["religion/personal law context", "first marriage proof", "second marriage facts", "children/dependants", "threats or financial neglect"],
            red_flags=_red_flags(q),
            action_pack=_family_marriage_status_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("second wife", "second marriage", "bigamy", "without divorcing", "cruelty", "threat", "beat", "beaten")) else None,
        )

    if _is_acid_chemical_attack_issue(q):
        return MatterRoute(
            category="police_fir",
            label="Acid or chemical attack / urgent FIR",
            confidence=0.88,
            urgency="emergency",
            required_sources=[
                "BNS 2023 / IPC 1860 acid-attack, hurt, and threat provisions based on incident date",
                "BNSS 2023 / CrPC 1973 FIR and victim medical-care procedure",
                "PWDVA 2005 protection-order route where the threat is inside a domestic relationship",
                "victim-compensation and DLSA procedure for urgent treatment/support",
            ],
            forums=["emergency medical care", "police station", "senior police officer", "Magistrate court for protection orders", "District Legal Services Authority"],
            missing_facts=["incident or threat date/time and location", "exact words and witnesses", "current safety and shelter", "hospital/MLC record if any", "police complaint/FIR status"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_family_safety_issue(q) or _is_family_support_issue(q) or _has_any(q, (
        "domestic violence", "husband beat", "husband is beating",
        "husband threatens", "husband threatened", "husband threatening",
        "slaps me", "slapped me", "hit me", "dowry", "in laws", "in-laws",
        "streedhan", "stridhan", "jewellery", "maintenance", "divorce", "custody",
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

    if _is_succession_issue(q):
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

    if _is_contract_labour_wage_issue(q):
        return MatterRoute(
            category="labour_exploitation_discrimination",
            label="Contract labour wage / principal-employer liability",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Contract Labour (Regulation and Abolition) Act 1970 section 21 where principal-employer wage liability is involved",
                "Code on Wages 2019 for wage dues and claims authority",
                "Inter-State Migrant Workmen Act 1979 where workers were recruited from another state",
            ],
            forums=["Labour Commissioner", "wage authority", "District Legal Services Authority", "police where cheating/threats are alleged"],
            missing_facts=["state/city and worksite", "principal employer name", "contractor/thekedar details", "number of workers", "wage amount and work dates", "attendance or wage proof"],
            red_flags=_red_flags(q),
            action_pack=_labour_exploitation_pack(),
        )

    if _has_any(q, (
        "salary", "wages", "gratuity", "pf", "epf", "maternity",
        "termination", "fired", "resign", "overtime",
        "retrench", "retrenched", "retrenchment", "layoff", "lay off",
        "notice period", "offer letter", "full and final", "final settlement",
        "settlement dues", "employment contract", "joining letter",
        "minimum wage", "minimum wages", "unpaid",
        "pip", "performance improvement plan", "bad rating", "hr complaint",
        "complained to hr", "manager harassment", "workplace harassment",
        "retaliation",
    )):
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

    if _has_any(q, _ENVIRONMENT_WORDS) and _is_environment_damage_issue(q):
        if _is_mining_displacement_matter(q):
            return MatterRoute(
                category="environment_compensation",
                label="Mining displacement / rehabilitation compensation",
                confidence=0.82,
                urgency="medium",
                required_sources=[
                    "RFCTLARR Act 2013 rehabilitation and Scheduled Area safeguards",
                    "PESA / Gram Sabha consultation where Scheduled Area facts apply",
                    "mining lease/project source only to identify the operator and project",
                ],
                forums=["Collector / R&R authority", "district rehabilitation office", "Gram Sabha where Scheduled Area rights apply", "DLSA"],
                missing_facts=["village/location", "acquisition or displacement notice", "project/company or lease details", "rehabilitation award/package status", "Gram Sabha record if any"],
                red_flags=_red_flags(q),
                action_pack=_mining_displacement_pack(),
            )
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

    if _is_street_vendor_municipal(q):
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

    if _has_any(q, (
        "landlord", "tenant", "rent", "deposit", "lease", "property",
        "land", "ancestral", "sale deed", "gift deed", "possession",
        "house", "flat", "joint name",
    )):
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


def _specific_high_risk_surface_route(q: str) -> MatterRoute | None:
    if _is_online_gambling_issue(q):
        tn_context = _has_tamil_nadu_context(q)
        required_sources = [
            "Public Gambling Act 1867 for common gaming-house / game-of-skill framing",
            "state online-gambling law where the user played or accessed the service",
            "platform terms and cyber/consumer route only where separate fraud, misrepresentation, or service deficiency is alleged",
        ]
        if tn_context:
            required_sources.insert(0, "Tamil Nadu Prohibition of Online Gambling and Regulation of Online Games Act 2022")
        return MatterRoute(
            category="digital_platform_account",
            label="Online gambling / gaming legality and money dispute",
            confidence=0.82,
            urgency="high" if _has_any(q, ("lakh", "50k", "lost", "recover")) else "medium",
            required_sources=required_sources,
            forums=[
                "Tamil Nadu Online Gaming Authority where Tamil Nadu facts apply",
                "platform grievance officer/help centre",
                "cyber/police channel where fraud or cheating is alleged",
                "consumer forum only for separate service-deficiency facts",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "state where the user was physically present",
                "app/provider name",
                "game type and whether money or other stakes were used",
                "transaction IDs and payment trail",
                "platform terms/screenshots and grievance history",
                "whether fraud or only gambling loss is alleged",
            ],
            red_flags=_red_flags(q),
            action_pack=_online_gambling_pack(),
        )

    if _is_caste_certificate_appeal(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="Caste certificate rejection / appeal",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Constitution Article 341 / 342 for Scheduled Caste or Scheduled Tribe lists",
                "state caste-certificate issuance and appeal rules",
                "Right to Information Act 2005 for written reasons/status where the order is unclear",
            ],
            forums=[
                "Tehsildar / competent certificate authority",
                "SDM/Revenue appellate authority or caste scrutiny committee as state rules provide",
                "District Social Welfare / SC-ST welfare office",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "state/district",
                "caste/community name claimed",
                "rejection order date and reason",
                "documents filed",
                "purpose of certificate",
                "appeal deadline printed on the order if any",
            ],
            red_flags=_red_flags(q),
            action_pack=_caste_certificate_pack(),
        )

    if _is_gig_platform_termination_issue(q):
        return MatterRoute(
            category="employment_wages",
            label="Gig/platform worker termination or deactivation",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Code on Social Security 2020 Chapter IX for gig workers and platform workers",
                "Industrial Disputes Act 1947 only if employee/workman facts fit",
                "platform contract, strike policy, grievance, and payout records",
            ],
            forums=[
                "platform grievance officer/help centre",
                "Labour Commissioner where workman/wage facts fit",
                "social-security facilitation or welfare board route where available",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "platform/app name",
                "role and contract status",
                "strike/deactivation notice",
                "earnings or payout held back",
                "service history and ratings",
                "whether there was an inquiry or appeal",
            ],
            red_flags=_red_flags(q),
            action_pack=_gig_platform_worker_pack(),
        )

    return None


def _priority_route(q: str) -> MatterRoute | None:
    """High-risk and high-conflict routes before the broad keyword chain."""
    if _is_land_acquisition_compensation_issue(q):
        return MatterRoute(
            category="land_acquisition_compensation",
            label="Land acquisition / RFCTLARR compensation",
            confidence=0.84,
            urgency="high" if _has_any(q, ("4 years", "years", "still not received", "not paid")) else "medium",
            required_sources=[
                "RFCTLARR Act 2013 compensation award, payment/deposit, and reference-to-Authority provisions",
                "project/acquisition award papers only to identify the land, award, and payment status",
            ],
            forums=["Collector / Land Acquisition Officer", "RFCTLARR Authority/reference forum", "District Legal Services Authority", "High Court writ route for exceptional administrative inaction"],
            missing_facts=["state/district", "acquisition notification or award number", "land/shop details", "award amount", "payment/deposit status", "objection/reference history"],
            red_flags=[],
            action_pack=_land_acquisition_compensation_pack(),
        )

    if _is_labour_overtime_register_notice(q):
        return MatterRoute(
            category="labour_compliance",
            label="Labour inspection / overtime register compliance",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "state Shops and Establishments law for overtime, registers, and inspection powers",
                "Maharashtra Shops and Establishments Act 2017 only where Maharashtra facts fit",
                "Building and Other Construction Workers Act 1996 where the workplace is a construction/building worksite",
                "Code on Wages 2019 where unpaid overtime wages are also claimed",
            ],
            forums=["Labour Commissioner / Facilitator", "Labour Department hearing officer", "wage authority where wages are claimed", "District Legal Services Authority"],
            missing_facts=["state/city", "establishment type", "number of workers", "inspection notice date", "records demanded", "whether construction/building work is involved"],
            red_flags=[],
            action_pack=_labour_register_compliance_pack(),
        )

    if _is_dpdp_data_breach_issue(q):
        return MatterRoute(
            category="cyber_fraud_or_harassment",
            label="Personal data breach / DPDP grievance",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Digital Personal Data Protection Act 2023 for personal-data breach duties and grievance route",
                "Information Technology Act 2000 where identity misuse, account compromise, or cyber offence is alleged",
                "Aadhaar Act 2016 only where Aadhaar authentication or UIDAI records are directly involved",
            ],
            forums=["platform/app grievance officer", "Data Protection Board grievance route where available", "cyber police station if identity misuse or fraud occurs", "District Legal Services Authority"],
            missing_facts=["platform/company name", "what personal data leaked", "date of breach or notice", "screenshots/emails", "loss or identity misuse", "complaints already filed"],
            red_flags=_red_flags(q),
            action_pack=_cyber_pack(),
        )

    if _is_msme_payment_route_issue(q):
        return MatterRoute(
            category="business_contract_partnership",
            label="MSME delayed-payment / 43B(h) dispute",
            confidence=0.84,
            urgency="medium",
            required_sources=[
                "MSMED Act 2006 sections 15, 16, and 18 for delayed payment and Facilitation Council route",
                "Indian Contract Act 1872 for invoice, delivery, and breach facts",
                "Sale of Goods Act 1930 where quality rejection, acceptance, or price deduction is disputed",
            ],
            forums=["MSME Samadhan / Micro and Small Enterprises Facilitation Council", "civil/commercial court where MSMED route is unavailable", "arbitration forum if the contract requires it", "District Legal Services Authority"],
            missing_facts=["Udyam/MSME registration date", "invoice and delivery dates", "buyer acceptance or rejection", "amount outstanding", "43B(h) communication", "purchase order/contract terms"],
            red_flags=[],
            action_pack=_business_contract_pack(),
        )

    if _is_agri_cooperative_recovery_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Agricultural / cooperative-bank recovery",
            confidence=0.78,
            urgency="high",
            required_sources=[
                "loan agreement and cooperative-bank recovery rules",
                "available cooperative-bank recovery case law and Banking Regulation Act context",
                "RBI/cooperative-bank grievance route and state cooperative-society forum",
            ],
            forums=["bank branch/grievance officer", "Registrar of Cooperative Societies or cooperative recovery forum", "Debt Recovery Tribunal where SARFAESI/DRT route applies", "District Legal Services Authority"],
            missing_facts=["state and bank name", "loan type and amount", "recovery or seizure notice", "asset/livestock seized", "auction/sale date if any", "complaints already filed"],
            red_flags=[],
            action_pack=_banking_credit_pack(),
        )

    if _is_forest_false_charge_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Forest produce / false criminal case defence",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Forest Rights Act 2006 minor forest produce and community forest-right provisions where applicable",
                "BNS 2023 / IPC 1860 dacoity, theft, and false-case provisions based on incident date",
                "BNSS 2023 / CrPC 1973 bail, FIR, and charge procedure based on incident date",
            ],
            forums=["criminal court / bail court", "investigating officer or police station for FIR papers", "Gram Sabha / forest-rights committee where FRA claim exists", "District Legal Services Authority"],
            missing_facts=["FIR sections", "arrest/notice status", "forest produce collected", "community/forest-right claim documents", "seizure memo", "bail or court dates"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_marriage_name_change_issue(q):
        return MatterRoute(
            category="family_marriage_status",
            label="Name / surname change after marriage",
            confidence=0.76,
            urgency="low",
            required_sources=[
                "state gazette/name-change procedure where locally available",
                "available name-change and identity-record correction case law where an authority refuses",
                "marriage certificate and identity-record update rules",
                "court order only if an authority disputes the change",
            ],
            forums=["state gazette or government press office", "Aadhaar/passport/PAN or record-issuing authority", "District Legal Services Authority"],
            missing_facts=["state/city", "old and new name", "marriage certificate", "ID records to update", "whether any authority refused the change"],
            red_flags=[],
            action_pack=_name_change_identity_pack(),
        )

    if _is_spa_raid_subject_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="ITPA raid / person taken to police station",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Immoral Traffic (Prevention) Act 1956 for raid, rescue, accused, and victim distinctions",
                "BNS 2023 / IPC 1860 trafficking or exploitation provisions based on incident date",
                "BNSS 2023 / CrPC 1973 arrest, notice, statement, and bail procedure based on incident date",
            ],
            forums=["police station/investigating officer for notice or station diary details", "criminal court or legal-aid lawyer if accused or summoned", "One Stop Centre/women helpline if coerced or exploited", "District Legal Services Authority"],
            missing_facts=["whether you were arrested, summoned, or only questioned", "sections mentioned", "statement or notice copy", "work role", "coercion or wage facts", "next police/court date"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_worksite_assault_injury_issue(q):
        return MatterRoute(
            category="workplace_injury_compensation",
            label="Worksite assault / injury and wage dispute",
            confidence=0.82,
            urgency="emergency",
            required_sources=[
                "BNS 2023 / IPC 1860 hurt or grievous-hurt provisions based on incident date",
                "Employees Compensation Act 1923 where injury arose out of and in course of work",
                "Code on Wages / labour law for unpaid wage context",
            ],
            forums=["police station for assault/FIR", "Labour Commissioner", "Employees Compensation Commissioner", "District Legal Services Authority"],
            missing_facts=["injury date/place", "medical papers", "employer/contractor or mukadam details", "wage-dues amount", "witnesses/CCTV", "police complaint status"],
            red_flags=_red_flags(q),
            action_pack=_work_injury_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_inlaw_jewellery_breach_issue(q):
        return MatterRoute(
            category="criminal_general",
            label="Family jewellery / breach of trust",
            confidence=0.78,
            urgency="medium",
            required_sources=[
                "BNS 2023 / IPC 1860 criminal breach of trust, cheating, or theft provisions based on incident date",
                "PWDVA 2005 economic-abuse route only if a domestic relationship and protection/return relief are needed",
                "civil property/recovery route where ownership and entrustment are disputed",
            ],
            forums=["police station for criminal breach of trust complaint", "Judicial Magistrate/criminal court", "Protection Officer or Magistrate where PWDVA applies", "District Legal Services Authority"],
            missing_facts=["who owns the jewellery", "entrustment date and words", "proof of purchase/gift", "messages demanding return", "relationship and shared-household facts", "police complaint status"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_panchayat_common_land_issue(q):
        return MatterRoute(
            category="land_revenue_records",
            label="Panchayat / common land transfer dispute",
            confidence=0.78,
            urgency="medium",
            required_sources=[
                "state panchayat and common-land rules where locally available",
                "available Panchayat/common-land case law for public/common land disputes",
                "state land-revenue / record-of-rights law",
                "Right to Information Act 2005 for meeting records, resolution, and allotment file",
            ],
            forums=["Gram Panchayat / Gram Sabha records office", "Block Development Officer or Collector", "revenue appellate authority", "District Legal Services Authority"],
            missing_facts=["state/district", "land record or plot details", "panchayat resolution or meeting date", "allotment/transfer order", "relationship conflict facts", "RTI or objection already filed"],
            red_flags=[],
            action_pack=_land_records_pack(),
        )

    if _is_pressure_property_transfer_issue(q):
        return MatterRoute(
            category="property_tenancy",
            label="Property transfer under pressure / undue influence",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Indian Contract Act 1872 consent, coercion, undue influence, and fraud provisions",
                "Transfer of Property Act 1882 gift/transfer and revocation provisions",
                "Specific Relief Act / civil court procedure for cancellation or declaration where needed",
            ],
            forums=["civil court", "registration/revenue office for document copy and mutation status", "District Legal Services Authority"],
            missing_facts=["registered document type", "signing date and hospital/ICU facts", "medical capacity proof", "pressure/coercion evidence", "property details", "possession/mutation status"],
            red_flags=_red_flags(q),
            action_pack=_property_pack(),
        )

    if _is_juvenile_age_custody_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Juvenile age determination / adult jail",
            confidence=0.86,
            urgency="emergency",
            required_sources=[
                "Juvenile Justice Act 2015 age inquiry and age-determination provisions",
                "POCSO Act 2012 only where the offence alleged is POCSO",
                "BNSS 2023 / CrPC 1973 production, custody, and bail procedure based on incident date",
            ],
            forums=["Juvenile Justice Board", "criminal court handling the case", "jail legal-aid clinic / District Legal Services Authority", "High Court where urgent transfer is needed"],
            missing_facts=["date of birth", "school certificate and Aadhaar/birth records", "FIR/POCSO sections", "current jail/observation-home location", "production order", "next court date"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_housing_society_parking_issue(q):
        return MatterRoute(
            category="consumer",
            label="Housing society / apartment parking dispute",
            confidence=0.72,
            urgency="low",
            required_sources=[
                "cooperative housing society bye-laws or apartment association rules",
                "consumer/civil remedy where common-area or allotted-parking service deficiency is alleged",
                "available cooperative-society case law where local housing rules are not indexed",
            ],
            forums=["society managing committee / association grievance channel", "Registrar of Cooperative Societies or local housing authority", "consumer forum or civil court where maintainable", "District Legal Services Authority"],
            missing_facts=["state/city", "allotment letter or sale deed parking clause", "society bye-law/resolution", "photos or security complaints", "written complaint and reply"],
            red_flags=[],
            action_pack=_consumer_pack(),
        )

    if _is_housing_society_pet_fine_issue(q):
        return MatterRoute(
            category="consumer",
            label="Housing society / pet fine dispute",
            confidence=0.72,
            urgency="low",
            required_sources=[
                "cooperative housing society bye-laws or apartment association rules",
                "available cooperative-society case law where local housing/pet rules are not indexed",
                "Consumer/civil remedy only after checking the society resolution and notice",
            ],
            forums=["society managing committee / association grievance channel", "Registrar of Cooperative Societies or local housing authority", "consumer forum or civil court where maintainable", "District Legal Services Authority"],
            missing_facts=["state/city", "society bye-law or resolution", "fine notice date", "pet approval rule", "prior warnings", "appeal/grievance already filed"],
            red_flags=[],
            action_pack=_consumer_pack(),
        )

    if _is_released_undertrial_police_torture_issue(q):
        return MatterRoute(
            category="police_fir",
            label="Custodial torture / post-release complaint",
            confidence=0.86,
            urgency="high",
            required_sources=[
                "Article 21 and custodial-violence safeguards",
                "Protection of Human Rights Act 1993 NHRC/SHRC complaint powers",
                "BNS 2023 / IPC 1860 hurt, grievous hurt, extortion, or public-servant offences based on incident date",
                "BNSS 2023 / CrPC 1973 FIR and Magistrate complaint procedure based on incident date",
            ],
            forums=["Human Rights Commission", "Judicial Magistrate", "senior police officer / police complaint authority", "District Legal Services Authority"],
            missing_facts=["custody dates and jail/police station", "release date", "injury/medical records", "officer names", "witnesses/co-prisoners", "prior complaints"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_ndps_bail_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="NDPS bail / custody defence",
            confidence=0.86,
            urgency="high",
            required_sources=[
                "NDPS Act 1985 section 37 for bail restrictions and section 36A where custody/default-bail timelines arise",
                "Article 21 prolonged-incarceration and speedy-trial principles where custody is long",
                "BNSS 2023 / CrPC 1973 bail and custody procedure based on incident date",
            ],
            forums=["Special NDPS Court", "High Court where bail is repeatedly refused", "criminal lawyer/legal-aid desk", "District Legal Services Authority"],
            missing_facts=["custody start date", "NDPS sections and quantity", "prior bail rejection orders", "chargesheet/status and trial progress", "medical/vulnerability facts if any"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_marital_sexual_violence_issue(q):
        return MatterRoute(
            category="family_domestic",
            label="Marital sexual violence / domestic safety",
            confidence=0.82,
            urgency="emergency" if _has_any(q, ("tonight", "now", "unsafe", "force", "forces", "forced")) else "high",
            required_sources=[
                "PWDVA 2005 sexual, physical, verbal, emotional, and economic abuse protections",
                "BNS 2023 / IPC 1860 sexual-offence provisions and marital-exception limits based on incident date",
                "BNSS 2023 / CrPC 1973 protection, complaint, and maintenance procedure where needed",
            ],
            forums=["Protection Officer", "Magistrate court", "women helpline / One Stop Centre", "police where immediate safety or assault risk exists", "District Legal Services Authority"],
            missing_facts=["current safety", "incident dates", "injury/medical or message proof if any", "children/dependants", "state/city", "whether you need residence, protection, or monetary relief"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_creator_cross_border_payout_issue(q):
        return MatterRoute(
            category="business_contract_partnership",
            label="Creator / foreign-platform payout dispute",
            confidence=0.74,
            urgency="medium",
            required_sources=[
                "Foreign Exchange Management Act 1999 and RBI foreign-exchange/payment directions where foreign platform payout is involved",
                "Income Tax Act 1961 for Indian taxability of creator/freelance income",
                "Indian Contract Act 1872 / platform terms where payout is withheld without clear reason",
            ],
            forums=["platform grievance/support channel", "bank/RBI grievance route where remittance is blocked", "civil/commercial court or arbitration if a contractual claim remains unresolved", "District Legal Services Authority"],
            missing_facts=["platform account ID", "country/currency and amount", "withholding/freeze reason", "bank/remittance reference", "tax/FEMA documents requested", "contract or creator terms"],
            red_flags=[],
            action_pack=_business_contract_pack(),
        )

    if _is_tweet_defamation_chargesheet_issue(q):
        return MatterRoute(
            category="cyber_fraud_or_harassment",
            label="Tweet / online defamation charge-sheet",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "BNS 2023 section 356 / IPC 1860 defamation provisions based on incident date",
                "BNSS 2023 / CrPC 1973 charge-sheet, summons, bail, discharge, and court procedure based on incident date",
                "Information Technology Act 2000 only where a specific electronic identity, privacy, obscene-content, or cyber-fraud provision is alleged",
            ],
            forums=[
                "criminal court named in the summons/charge-sheet",
                "High Court for quashing where legally advised",
                "cyber police station or local police station for case records and investigation contact",
                "District Legal Services Authority",
                "criminal lawyer/legal-aid desk",
            ],
            missing_facts=[
                "incident/tweet date",
                "charge-sheet date",
                "summons or next court date",
                "exact BNS/IPC/IT Act sections cited",
                "deadline or limitation facts for discharge, quashing, revision, or appeal",
            ],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_habeas_illegal_detention_issue(q):
        return MatterRoute(
            category="arrest_custody_safeguard",
            label="Illegal detention / habeas corpus",
            confidence=0.84,
            urgency="emergency",
            required_sources=[
                "Article 21 and Article 226 constitutional liberty / habeas corpus route",
                "BNSS 2023 / CrPC 1973 arrest, detention, and production safeguards based on incident date",
            ],
            forums=["High Court writ jurisdiction", "nearest Magistrate/criminal court", "District Legal Services Authority", "senior police officer"],
            missing_facts=["detention date/time", "police station or authority", "last known location", "FIR/case details if any", "proof of requests to police/court"],
            red_flags=_red_flags(q),
            action_pack=_custody_safeguard_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_acid_chemical_attack_issue(q):
        return MatterRoute(
            category="police_fir",
            label="Acid or chemical attack / urgent FIR",
            confidence=0.88,
            urgency="emergency",
            required_sources=[
                "BNS 2023 / IPC 1860 acid-attack, hurt, and threat provisions based on incident date",
                "BNSS 2023 / CrPC 1973 FIR and victim medical-care procedure",
                "PWDVA 2005 protection-order route where the threat is inside a domestic relationship",
                "victim-compensation and DLSA procedure for urgent treatment/support",
            ],
            forums=["emergency medical care", "police station", "senior police officer", "Magistrate court for protection orders", "District Legal Services Authority"],
            missing_facts=["incident or threat date/time and location", "exact words and witnesses", "current safety and shelter", "hospital/MLC record if any", "police complaint/FIR status"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_mgnrega_social_audit_issue(q):
        return MatterRoute(
            category="labour_exploitation_discrimination",
            label="MGNREGA wage / social-audit grievance",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "MGNREGA 2005 social-audit and grievance provisions",
                "Right to Information Act 2005 where records or action-taken reports are needed",
                "BNS/Prevention of Corruption Act where bribe, forged muster, or misappropriation facts exist",
            ],
            forums=["programme officer/BDO", "district MGNREGA grievance authority", "Gram Sabha/social audit forum", "District Legal Services Authority"],
            missing_facts=["state/district and gram panchayat", "job card/work ID", "social-audit report", "wage or corruption amount", "complaints already filed"],
            red_flags=_red_flags(q),
            action_pack=_labour_exploitation_pack(),
        )

    if _is_hate_or_identity_insult_crime(q):
        return MatterRoute(
            category="criminal_general",
            label="Identity insult / hate-speech complaint",
            confidence=0.78,
            urgency="high" if _has_any(q, ("threat", "attack", "beat", "beaten")) else "medium",
            required_sources=[
                "BNS 2023 / IPC 1860 insult, intimidation, and public-order provisions based on incident date",
                "SC/ST Act only where caste/tribal status is part of the abuse",
                "BNSS/CrPC complaint procedure",
            ],
            forums=["police station", "senior police officer", "District Legal Services Authority"],
            missing_facts=["exact words used", "place and date", "whether it was public or online", "witnesses/screenshots", "whether caste/tribal status was targeted"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_commercial_mediation_procedure(q):
        return MatterRoute(
            category="court_procedure",
            label="Commercial suit / pre-litigation mediation procedure",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Commercial Courts Act 2015 pre-institution mediation provision where applicable",
                "Mediation Act 2023 / rules where notified procedure applies",
                "Code of Civil Procedure 1908 for plaint rejection and threshold objections",
            ],
            forums=["commercial court", "District Legal Services Authority / mediation centre", "civil court filing counter", "lawyer/legal-aid clinic"],
            missing_facts=["commercial dispute type and value", "urgent interim relief sought or not", "mediation notice/status", "suit filing date", "court/order copy"],
            red_flags=[],
            action_pack=_court_procedure_pack(),
        )

    if _is_environment_damage_issue(q):
        if _is_mining_displacement_matter(q):
            return MatterRoute(
                category="environment_compensation",
                label="Mining displacement / rehabilitation compensation",
                confidence=0.82,
                urgency="medium",
                required_sources=[
                    "RFCTLARR Act 2013 rehabilitation and Scheduled Area safeguards",
                    "PESA / Gram Sabha consultation where Scheduled Area facts apply",
                    "mining lease/project source only to identify the operator and project",
                ],
                forums=["Collector / R&R authority", "district rehabilitation office", "Gram Sabha where Scheduled Area rights apply", "DLSA"],
                missing_facts=["village/location", "acquisition or displacement notice", "project/company or lease details", "rehabilitation award/package status", "Gram Sabha record if any"],
                red_flags=_red_flags(q),
                action_pack=_mining_displacement_pack(),
            )
        return MatterRoute(
            category="environment_compensation",
            label="Environmental damage / compensation",
            confidence=0.78,
            urgency="medium",
            required_sources=[
                "Water Act / pollution-control law where water, effluent, or factory pollution is involved",
                "Environment Protection / NGT procedure where available",
                "LARR/PESA/FRA where displacement or Scheduled Area consent applies",
            ],
            forums=["District Collector / pollution control board", "National Green Tribunal", "DLSA", "Gram Sabha where Scheduled Area rights apply"],
            missing_facts=["location", "project/company", "damage proof", "dates", "complaints or notices already filed"],
            red_flags=_red_flags(q),
            action_pack=_environment_pack(),
        )

    if _is_senior_citizen_issue(q):
        return MatterRoute(
            category="senior_citizen",
            label="Senior citizen maintenance / property transfer",
            confidence=0.82,
            urgency="high" if _has_any(q, ("threw me out", "no food", "homeless", "widow", "no income")) else "medium",
            required_sources=[
                "Maintenance and Welfare of Parents and Senior Citizens Act 2007",
                "Transfer of Property Act 1882 where gift or property-transfer cancellation is involved",
                "state maintenance tribunal rules",
            ],
            forums=["Maintenance Tribunal / District Magistrate", "District Legal Services Authority"],
            missing_facts=["state/city", "age", "property ownership/transfer facts", "whether a gift/settlement deed exists", "current shelter and income"],
            red_flags=_red_flags(q),
            action_pack=_senior_pack(),
        )

    if _is_bocw_registration_issue(q):
        return MatterRoute(
            category="labour_exploitation_discrimination",
            label="BOCW registration / welfare-board record dispute",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Building and Other Construction Workers Act 1996 registration and welfare-board provisions",
                "BOCW Cess Act / state welfare-board cess records where cess collection or fake registers are alleged",
                "BNS/BNSS or IPC/CrPC where cheating, forgery, or false registers are alleged",
            ],
            forums=["BOCW Welfare Board", "Labour Commissioner", "District Legal Services Authority", "police where register fraud or cheating is alleged"],
            missing_facts=["state/city", "contractor/thekedar details", "worksite and principal employer", "register/card details", "names used in records", "cess or benefit claim proof"],
            red_flags=_red_flags(q),
            action_pack=_labour_exploitation_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("cheating", "fraud", "fake", "false register")) else None,
        )

    if _is_it_act_67_accused_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="IT Act 67 / online-content accused defence",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Information Technology Act 2000 section 67 / 66E where electronic image or obscene-content allegation is made",
                "BNS 2023 / IPC 1860 and BNSS/CrPC procedure based on incident date",
            ],
            forums=["criminal court", "investigating officer/police for notice/FIR status", "District Legal Services Authority", "cyber-law/criminal lawyer"],
            missing_facts=["FIR/notice sections", "exact image/content shared", "platform and group details", "date/time", "whether arrest notice or summons exists"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_rape_promise_accused_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Rape / promise-to-marry accused defence",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "BNS 2023 sections 63 and 69 / IPC legacy sexual-offence provisions based on incident date",
                "BNSS 2023 / CrPC 1973 bail, notice, and investigation procedure",
            ],
            forums=["criminal court", "police/investigating officer for notices", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
            missing_facts=["FIR sections and date", "ages", "relationship timeline", "messages/consent facts", "arrest/notice status", "court stage"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_stalking_harassment_issue(q):
        cyber_context = _has_any(q, ("insta", "instagram", "dm daily", "direct message", "dms", "whatsapp", "facebook", "tinder", "online", "profile"))
        return MatterRoute(
            category="cyber_fraud_or_harassment" if cyber_context else "police_fir",
            label="Stalking / harassment complaint",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "BNS 2023 / IPC 1860 stalking and criminal-intimidation provisions based on incident date",
                "Information Technology Act 2000 where platform messages, DMs, or online accounts are involved",
                "BNSS 2023 / CrPC 1973 complaint/FIR procedure",
            ],
            forums=["police station", "National Cyber Crime Portal where online", "District Legal Services Authority"],
            missing_facts=["incident dates", "platform or physical route/location", "screenshots/CCTV/witnesses", "prior warning/blocking", "current safety risk"],
            red_flags=_red_flags(q),
            action_pack=_cyber_pack() if cyber_context else _fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_minor_interfaith_relationship_issue(q):
        return MatterRoute(
            category="police_fir",
            label="Minor interfaith relationship / police protection",
            confidence=0.80,
            urgency="high",
            required_sources=[
                "POCSO Act 2012 where either person is under 18 and sexual activity is alleged",
                "Article 21 partner-choice and liberty principles for adult autonomy",
                "BNSS/CrPC and BNS/IPC complaint procedure based on incident date",
            ],
            forums=["police station", "Child Welfare Committee where child protection is involved", "District Legal Services Authority", "High Court writ jurisdiction for protection"],
            missing_facts=["exact ages/date-of-birth proof", "current location and safety", "whether any FIR/missing complaint exists", "threats/coercion facts", "incident date"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_honour_threat_issue(q):
        return MatterRoute(
            category="police_fir",
            label="Honour-threat / adult partner-choice protection",
            confidence=0.82,
            urgency="emergency" if _has_any(q, ("kill", "attack", "mob", "khap")) else "high",
            required_sources=[
                "Article 21 partner-choice and liberty principles",
                "BNS/BNSS or IPC/CrPC criminal-intimidation and protection procedure based on incident date",
                "Supreme Court honour-crime protection guidelines where applicable",
            ],
            forums=["police station", "senior police officer", "District Legal Services Authority", "High Court writ jurisdiction for protection"],
            missing_facts=["ages", "current location and safety", "who is threatening", "messages/calls/witnesses", "whether a complaint was filed"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_dowry_death_issue(q):
        return MatterRoute(
            category="police_fir",
            label="Dowry death / suspicious marital death",
            confidence=0.86,
            urgency="emergency",
            required_sources=[
                "BNS 2023 section 80 / IPC 304B dowry-death provisions based on incident date",
                "BNSS/CrPC inquest, FIR, post-mortem, and investigation procedure",
                "Dowry Prohibition Act 1961 where dowry demand facts exist",
            ],
            forums=["police station", "senior police officer", "Magistrate", "District Legal Services Authority"],
            missing_facts=["death date and place", "marriage date", "dowry demand history", "post-mortem/inquest status", "injury/body marks", "FIR status"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_family_economic_abuse_issue(q):
        return MatterRoute(
            category="family_domestic",
            label="Domestic violence / economic abuse",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "PWDVA 2005 economic abuse, monetary relief, protection, and application procedure",
                "family maintenance law where support or household expenses are withheld",
            ],
            forums=["Protection Officer", "Magistrate court", "Family Court", "District Legal Services Authority"],
            missing_facts=["marriage/domestic relationship facts", "income and bank/ATM control", "household-expense facts", "children/dependants", "current safety and residence"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
        )

    if _is_deceitful_intercourse_issue(q):
        return MatterRoute(
            category="criminal_general",
            label="Promise-to-marry / deceitful-intercourse complaint",
            confidence=0.76,
            urgency="high",
            required_sources=[
                "BNS 2023 section 69 and sexual-offence provisions where deceitful means are alleged",
                "BNSS/CrPC complaint and investigation procedure",
                "live-in/domestic-relationship protection law where financial or residence abuse is involved",
            ],
            forums=["police station", "District Legal Services Authority", "criminal court where FIR/case proceeds"],
            missing_facts=["ages", "relationship timeline", "promise/messages", "cohabitation facts", "incident dates", "current safety"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_undertrial_legal_aid_issue(q):
        return MatterRoute(
            category="undertrial_review_release",
            label="Undertrial legal aid / custody-delay review",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "Legal Services Authorities Act 1987 section 12 and DLSA legal-aid procedure",
                "Article 21 speedy-trial and effective-legal-aid principles",
                "BNSS 2023 section 479 / CrPC 436A where custody duration may trigger review",
            ],
            forums=["District Legal Services Authority", "jail legal-aid clinic", "trial court", "High Court writ jurisdiction where delay is unlawful"],
            missing_facts=["jail/prison name", "custody start date", "offence sections", "lawyer appointment/history", "hearing dates missed", "bail/review orders"],
            red_flags=_red_flags(q),
            action_pack=_undertrial_review_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_sarfaesi_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="SARFAESI / secured-loan recovery",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "SARFAESI Act 2002 section 13 demand and possession procedure",
                "SARFAESI Act 2002 section 17 DRT application/remedy where possession or measures are taken",
                "loan documents and RBI restructuring/settlement guidance where negotiation is requested",
            ],
            forums=["bank authorised officer / secured creditor", "Debt Recovery Tribunal", "Debt Recovery Appellate Tribunal", "District Legal Services Authority"],
            missing_facts=["notice date", "loan type and outstanding amount", "section 13(2)/13(4) stage", "secured-asset details", "reply/representation sent", "possession date if any"],
            red_flags=_red_flags(q),
            action_pack=_banking_credit_pack(),
        )

    if _is_msme_payment_issue(q):
        return MatterRoute(
            category="business_contract_partnership",
            label="MSME / business delayed-payment dispute",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "MSMED Act 2006 delayed-payment provisions where the supplier is a micro or small enterprise",
                "Indian Contract Act 1872 for breach, performance, and damages",
                "Sale of Goods / contract documents where rejection or quality dispute is raised",
            ],
            forums=["MSME Samadhan / Micro and Small Enterprises Facilitation Council", "civil/commercial court where MSMED route is unavailable", "arbitration forum if the contract requires it", "District Legal Services Authority"],
            missing_facts=["MSME/Udyam registration status", "invoice and delivery dates", "written rejection/quality communications", "purchase order/contract terms", "amount outstanding", "buyer details"],
            red_flags=[],
            action_pack=_business_contract_pack(),
        )

    if _is_transport_permit_issue(q):
        return MatterRoute(
            category="business_license_compliance",
            label="Transport permit / auto-taxi renewal",
            confidence=0.78,
            urgency="medium",
            required_sources=[
                "Motor Vehicles Act 1988 permit and renewal provisions",
                "state motor vehicle rules and transport-department renewal procedure",
                "RTI/grievance route where renewal status or lockdown extension is unclear",
            ],
            forums=["Regional Transport Office", "state transport department portal", "RTI/public grievance channel", "District Legal Services Authority"],
            missing_facts=["state/RTO", "permit type", "expiry date", "renewal application/receipt", "vehicle number", "penalty or rejection notice"],
            red_flags=[],
            action_pack=_business_license_pack(),
        )

    if _is_esi_benefit_issue(q):
        return MatterRoute(
            category="employment_wages",
            label="ESI benefit / insured-person treatment dispute",
            confidence=0.82,
            urgency="high" if _has_any(q, ("delivery", "emergency", "refused to treat", "hospital")) else "medium",
            required_sources=["Employees' State Insurance Act 1948", "ESI medical-benefit and contribution eligibility procedure", "labour/DLSA grievance route"],
            forums=["ESI Corporation branch office", "ESI hospital medical superintendent", "Employees' Insurance Court", "DLSA / District Legal Services Authority"],
            missing_facts=["ESI insurance number", "contribution period", "employer details", "hospital/refusal date", "written refusal or eligibility reason"],
            red_flags=_red_flags(q),
            action_pack=_employment_pack(),
        )

    if _is_labour_compliance_notice(q):
        return MatterRoute(
            category="labour_compliance",
            label="Labour / ESI compliance notice",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Employees' State Insurance Act 1948 where ESI contribution notice applies",
                "Code on Social Security 2020 where contribution/social-security classification applies",
                "labour authority / ESI Court procedure for contesting contribution determinations",
            ],
            forums=["ESI Corporation / assessing officer", "Employees' Insurance Court", "Labour Commissioner", "District Legal Services Authority"],
            missing_facts=["notice date", "coverage period", "worker categories", "contribution calculation", "inspection report", "reply or hearing deadline"],
            red_flags=[],
            action_pack=_labour_compliance_pack(),
        )

    if _is_manual_scavenging_issue(q):
        return MatterRoute(
            category="manual_scavenging_safety",
            label="Manual scavenging / sewer or septic-tank death",
            confidence=0.84,
            urgency="emergency" if _has_any(q, ("dies", "died", "death", "dead", "no safety", "septic tank", "sewer")) else "high",
            required_sources=[
                "Prohibition of Employment as Manual Scavengers and their Rehabilitation Act 2013",
                "Employees' Compensation Act 1923 / labour compensation route where employment link exists",
                "BNS/BNSS or IPC/CrPC based on incident date where death, negligence, or forced hazardous cleaning is involved",
            ],
            forums=["District Magistrate/local authority", "police station", "Labour Commissioner / Employees Compensation Commissioner", "District Legal Services Authority"],
            missing_facts=["incident date and place", "employer/contractor/company", "sewer or septic-tank work facts", "safety equipment provided", "death/medical records", "family/dependant details"],
            red_flags=_red_flags(q),
            action_pack=_manual_scavenging_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_prison_medical_bail_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Custody medical care / interim bail",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Article 21 constitutional custody-health safeguards",
                "BNSS 2023 / CrPC 1973 bail and custody provisions based on incident date",
                "prison manual / jail medical-care rules for the state",
            ],
            forums=["criminal court", "jail superintendent", "District Legal Services Authority", "High Court writ jurisdiction"],
            missing_facts=["custody start date", "jail/prison name", "medical condition and test dates", "doctor requests/refusals", "case/offence sections", "prior bail orders"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_ndps_default_bail_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="NDPS default bail / no chargesheet",
            confidence=0.86,
            urgency="high",
            required_sources=[
                "NDPS Act 1985 section 36A and section 37 where commercial quantity is involved",
                "BNSS 2023 / CrPC 1973 default-bail custody provisions based on incident date",
            ],
            forums=["Special NDPS Court", "criminal court", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
            missing_facts=["custody start date", "chargesheet filing date", "NDPS sections and quantity", "extension application/order if any", "prior bail orders"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_pocso_minor_accused_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="POCSO / minor accused defence",
            confidence=0.86,
            urgency="high",
            required_sources=[
                "POCSO Act 2012 where the complainant is a child",
                "Juvenile Justice Act 2015 where the accused is under 18",
                "BNSS 2023 / CrPC 1973 bail and procedure based on incident date",
            ],
            forums=["Juvenile Justice Board or criminal court as applicable", "Special Court under POCSO", "District Legal Services Authority"],
            missing_facts=["ages and date-of-birth proof for both persons", "incident/date and FIR sections", "custody/arrest status", "whether statement/medical examination happened"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_498a_complainant_protection_issue(q):
        return MatterRoute(
            category="family_domestic",
            label="Domestic violence / matrimonial protection",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "PWDVA 2005 protection, residence, monetary relief and application procedure",
                "BNS 2023 / IPC 1860 cruelty provisions based on incident date where FIR/498A is involved",
                "BNSS 2023 / CrPC 1973 complaint and court procedure based on incident date",
            ],
            forums=["Protection Officer", "Magistrate court", "Family Court", "District Legal Services Authority"],
            missing_facts=["current safety and shelter", "FIR/complaint date and sections", "marriage/residence facts", "children/dependants", "income and documents", "state/city"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_accused_498a_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="498A / matrimonial criminal defence",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "BNS 2023 / IPC 1860 cruelty provisions based on incident date",
                "BNSS 2023 / CrPC 1973 bail, notice, and quashing procedure based on incident date",
            ],
            forums=["criminal court", "police/investigating officer for notices", "District Legal Services Authority", "High Court where quashing is sought"],
            missing_facts=["incident date", "FIR sections", "arrest/notice status", "family members named", "court stage", "mediation or matrimonial case status"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_custodial_violence_issue(q):
        return MatterRoute(
            category="police_fir",
            label="Custodial violence / police extortion",
            confidence=0.84,
            urgency="emergency",
            required_sources=[
                "Article 21 and custodial-violence safeguards",
                "BNS/BNSS or IPC/CrPC based on incident date",
                "human-rights commission / police complaint authority procedure",
            ],
            forums=["senior police officer", "Judicial Magistrate", "Human Rights Commission", "District Legal Services Authority"],
            missing_facts=["detention/arrest date and police station", "injury/medical records", "officer details", "money demanded or paid", "current custody/release status"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_fir_copy_access_issue(q):
        return MatterRoute(
            category="police_fir",
            label="FIR copy / arrest information",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "BNSS 2023 / CrPC 1973 FIR and arrest-information procedure based on incident date",
                "Article 22 arrest safeguards where family is not informed or grounds are withheld",
            ],
            forums=["police station", "Superintendent of Police", "Judicial Magistrate", "District Legal Services Authority"],
            missing_facts=["arrest date and police station", "FIR/crime number if known", "whether accused/complainant/family requested the copy", "written refusal or reason given"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_domestic_residence_issue(q):
        return MatterRoute(
            category="family_domestic",
            label="Domestic violence / right to residence",
            confidence=0.82,
            urgency="emergency" if _has_any(q, ("raat", "night", "now", "today", "unsafe", "locked", "threw me out", "kicked me out", "ghar se nikal", "nikal diya")) else "high",
            required_sources=["PWDVA 2005 residence, protection, monetary relief and application procedure", "family law statute by religion where maintenance/divorce also applies"],
            forums=["Protection Officer", "Magistrate court", "Family Court", "District Legal Services Authority"],
            missing_facts=["current safety and shelter", "marriage/residence facts", "children/dependants", "incident dates", "income and documents", "state/city"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, _CRIME_WORDS) else None,
        )

    if _is_adult_forced_marriage_issue(q):
        return MatterRoute(
            category="family_domestic",
            label="Adult forced marriage / family pressure",
            confidence=0.78,
            urgency="high",
            required_sources=["Article 21 autonomy and partner-choice principles", "family/domestic-violence protection law where confinement, threats, or shelter risk exists", "BNS/BNSS or IPC/CrPC where threats or confinement are involved"],
            forums=["District Legal Services Authority", "Protection Officer/Magistrate where protection is needed", "police for threats or confinement", "High Court writ jurisdiction for liberty protection"],
            missing_facts=["age", "current safety/location", "threats or confinement", "planned marriage date", "state/city", "trusted support person"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("threat", "locked", "force", "forcing", "confinement")) else None,
        )

    if _is_security_cheque_defence_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Security cheque misuse / NI Act defence",
            confidence=0.80,
            urgency="high",
            required_sources=[
                "Negotiable Instruments Act 1881 sections 138 and 142 for dishonour notice and complaint limits",
                "bank account / stop-payment complaint records",
                "rent, loan, or security-deposit documents showing why the cheque was issued",
            ],
            forums=["bank branch/grievance officer", "Judicial Magistrate court if a notice or complaint is filed", "civil/rent court where the underlying liability is disputed", "District Legal Services Authority"],
            missing_facts=["cheque date and number", "bank return memo date if presented", "demand notice sent date if any", "15-day payment-window status", "security purpose and underlying liability proof"],
            red_flags=[],
            action_pack=_security_cheque_pack(),
        )

    if _is_elder_maintenance_cheque_issue(q):
        return MatterRoute(
            category="senior_citizen",
            label="Parent maintenance cheque / elder support",
            confidence=0.78,
            urgency="high",
            required_sources=[
                "Maintenance and Welfare of Parents and Senior Citizens Act 2007",
                "Negotiable Instruments Act 1881 sections 138 and 142 where a maintenance cheque is dishonoured",
                "BNSS/CrPC complaint procedure only if criminal process is involved",
            ],
            forums=["Maintenance Tribunal", "District Magistrate / senior-citizen cell where available", "Judicial Magistrate court if NI Act notice/complaint is pursued", "District Legal Services Authority"],
            missing_facts=["parent age and dependency", "maintenance arrangement/order if any", "cheque return memo date", "demand notice sent date if any", "15-day payment-window status"],
            red_flags=_red_flags(q),
            action_pack=_senior_maintenance_cheque_pack(),
        )

    if _is_cheque_bounce_issue(q):
        return MatterRoute(
            category="cheque_bounce",
            label="Cheque dishonour",
            confidence=0.84,
            urgency="high",
            required_sources=["Negotiable Instruments Act 1881 sections 138 and 142", "BNSS/CrPC complaint procedure"],
            forums=["Judicial Magistrate court", "lawyer/legal aid for notice drafting"],
            missing_facts=["date cheque returned", "bank return memo reason", "demand notice sent date", "15-day payment-window status", "amount and drawer details"],
            red_flags=[],
            action_pack=_cheque_pack(),
        )

    if _is_spa_trafficking_issue(q):
        return MatterRoute(
            category="criminal_general",
            label="Forced sexual exploitation / trafficking risk",
            confidence=0.82,
            urgency="emergency",
            required_sources=["BNS/IPC trafficking, coercion and sexual-offence provisions based on incident date", "Immoral Traffic (Prevention) Act where commercial sexual exploitation is involved", "BNSS/CrPC complaint and protection procedure"],
            forums=["police station", "District Legal Services Authority", "One Stop Centre or women helpline where applicable", "labour department for wage coercion"],
            missing_facts=["current safety and location", "employer/owner details", "threats or confinement", "wage/payment facts", "identity documents retained", "whether police raid/complaint exists"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_child_labour_issue(q):
        return MatterRoute(
            category="labour_exploitation_discrimination",
            label="Child labour / age proof",
            confidence=0.82,
            urgency="high",
            required_sources=["Child and Adolescent Labour law", "Juvenile Justice Act 2015 where care/protection is needed", "Code on Wages / labour law where wages or employer records are involved"],
            forums=["Labour Commissioner", "Child Welfare Committee", "District Legal Services Authority", "police where exploitation or trafficking appears"],
            missing_facts=["child age/date-of-birth proof", "worksite and employer", "work type/hours", "wage/payment facts", "documents shown for age", "district/state"],
            red_flags=_red_flags(q),
            action_pack=_labour_exploitation_pack(),
        )

    if _is_witch_branding_accused_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Witch-branding / false-case accused defence",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "BNS/BNSS or IPC/CrPC accused-rights and bail/quashing procedure based on incident date",
                "state witch-hunting law must be verified for the specific state before giving offence/remedy details",
            ],
            forums=["criminal court", "police/investigating officer for notice/FIR status", "District Legal Services Authority", "High Court where quashing/protection is considered"],
            missing_facts=["state/district", "FIR/notice sections", "who filed the case", "incident date", "arrest/notice status", "evidence showing false implication"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_witch_branding_violence(q):
        return MatterRoute(
            category="police_fir",
            label="Witch-branding violence / police complaint",
            confidence=0.82,
            urgency="emergency" if _has_any(q, ("beaten", "beat", "attack", "mob", "throw me out")) else "high",
            required_sources=["BNS/BNSS or IPC/CrPC based on incident date", "SC/ST Act where caste or tribal status is part of the targeting", "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given"],
            forums=["police station", "senior police officer", "District Legal Services Authority", "state women/social welfare authority where applicable"],
            missing_facts=["state/district", "incident date and place", "injury/medical proof", "who used the witch-branding words", "caste/tribal status if relevant"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_scst_poa_procedure_issue(q):
        return MatterRoute(
            category="tribal_caste_atrocity",
            label="SC/ST atrocity case procedure",
            confidence=0.84,
            urgency="high",
            required_sources=["SC/ST (Prevention of Atrocities) Act 1989 and Rules", "BNSS/CrPC investigation and complaint procedure", "BNS/IPC based on incident date where offences are alleged"],
            forums=["police station/senior police", "Special Court under SC/ST Act", "District Legal Services Authority", "district social welfare/tribal welfare authority"],
            missing_facts=["community/status documents", "FIR/case number", "investigating officer rank/order", "district/state", "complaints to SP or Special Court"],
            red_flags=_red_flags(q),
            action_pack=_tribal_caste_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_custody_compensation_issue(q):
        return MatterRoute(
            category="custody_compensation",
            label="Wrongful custody / acquittal compensation",
            confidence=0.80,
            urgency="medium",
            required_sources=["Article 21 constitutional compensation and speedy-trial principles", "human-rights commission procedure", "BNSS/CrPC custody and appeal records where relevant"],
            forums=["High Court writ jurisdiction", "Human Rights Commission", "District Legal Services Authority"],
            missing_facts=["custody start/end dates", "acquittal/release order", "case/offence sections", "bail history", "delay or unlawful custody facts"],
            red_flags=_red_flags(q),
            action_pack=_custody_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_company_compliance_issue(q):
        is_llp = _has_any(q, ("llp", "limited liability partnership", "form 11"))
        return MatterRoute(
            category="ibc_nclt",
            label="LLP annual filing / strike-off risk" if is_llp else "Company filing / director disqualification",
            confidence=0.78,
            urgency="medium",
            required_sources=(
                ["Limited Liability Partnership Act 2008 annual return and strike-off provisions", "Registrar of Companies / MCA procedure for LLP filings"]
                if is_llp
                else ["Companies Act 2013 annual filing, director disqualification, and restoration provisions", "NCLT/ROC procedure where revival or strike-off is involved"]
            ),
            forums=["Registrar of Companies / MCA portal", "NCLT where restoration/revival is needed", "company-law professional"],
            missing_facts=["company CIN", "forms pending and years", "strike-off/disqualification status", "ROC notice/order", "financial statements and board records"],
            red_flags=[],
            action_pack=_llp_compliance_pack() if is_llp else _ibc_pack(),
        )

    if _is_drug_license_compliance_issue(q):
        return MatterRoute(
            category="business_license_compliance",
            label="Drug licence / medical-store compliance",
            confidence=0.78,
            urgency="medium",
            required_sources=[
                "Drugs and Cosmetics Act 1940 inspection, sampling, and sale-compliance provisions",
                "Drugs Rules / Schedule H prescription-sale rules where locally available",
                "state drug-control authority procedure for notices and replies",
            ],
            forums=["Drug Inspector / licensing authority", "State Drug Controller", "criminal court if prosecution is filed", "District Legal Services Authority"],
            missing_facts=["drug licence number", "sample memo or notice", "drug name and Schedule H status", "prescription/sale register", "test report or prosecution status"],
            red_flags=[],
            action_pack=_drug_license_pack(),
        )

    if _is_food_license_issue(q):
        return MatterRoute(
            category="business_license_compliance",
            label="FSSAI / food licence compliance",
            confidence=0.78,
            urgency="medium",
            required_sources=["Food Safety and Standards Act 2006", "FSSAI Licensing and Registration Regulations", "state/central licence upgrade procedure"],
            forums=["FSSAI FoSCoS portal", "state food safety authority", "licensing authority", "District Legal Services Authority"],
            missing_facts=["state/city", "licence number", "business category and turnover/capacity", "notice or mismatch reason", "renewal deadline"],
            red_flags=[],
            action_pack=_business_license_pack(),
        )

    if _is_payment_refund_service_issue(q):
        return MatterRoute(
            category="consumer",
            label="Consumer payment/refund dispute",
            confidence=0.78,
            urgency="medium",
            required_sources=["Consumer Protection Act 2019", "Consumer Protection Rules / e-Daakhil procedure", "RBI/payment-provider grievance route where payment status is disputed"],
            forums=["National Consumer Helpline", "District Consumer Disputes Redressal Commission", "e-Daakhil", "payment provider/bank grievance officer"],
            missing_facts=["payment date and UPI/reference ID", "merchant/order details", "bank/payment status", "refund request history", "screenshots and communications"],
            red_flags=_red_flags(q),
            action_pack=_consumer_pack(),
        )

    if _is_digital_money_platform_issue(q):
        return MatterRoute(
            category="digital_platform_account",
            label="Digital platform / wallet / online gaming dispute",
            confidence=0.76,
            urgency="high" if _has_any(q, ("lakh", "money stuck", "frozen", "froze", "lost")) else "medium",
            required_sources=["Consumer Protection Act 2019 where paid service or wallet/platform service is involved", "Information Technology Act 2000 / IT Rules where platform grievance applies", "RBI/KYC or online-gaming rules where financial account facts apply"],
            forums=["platform grievance officer/help centre", "consumer forum/e-Daakhil where service deficiency applies", "RBI/cyber/police channel where fraud or money movement is involved"],
            missing_facts=["platform/app name", "account or wallet ID", "amount stuck/lost", "notice/reason given", "transaction IDs", "grievance history"],
            red_flags=_red_flags(q),
            action_pack=_digital_platform_pack(),
        )

    if _is_document_fraud_issue(q):
        return MatterRoute(
            category="criminal_general",
            label="Forgery / document fraud",
            confidence=0.78,
            urgency="high",
            required_sources=["BNS 2023 / IPC 1860 cheating and forgery provisions based on incident date", "BNSS 2023 / CrPC complaint and investigation procedure"],
            forums=["police station", "senior police officer", "Judicial Magistrate", "District Legal Services Authority"],
            missing_facts=["document shown or used", "date/place of thumb impression/signature", "who produced the document", "loan/property amount", "police or court stage"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_child_support_enforcement_issue(q):
        return MatterRoute(
            category="family_domestic",
            label="Child support / maintenance order enforcement",
            confidence=0.80,
            urgency="high",
            required_sources=["BNSS 2023 / CrPC 1973 maintenance enforcement provisions", "Family Court procedure and existing order enforcement route"],
            forums=["Family Court", "Magistrate court", "District Legal Services Authority"],
            missing_facts=["court/order date", "monthly amount", "arrears months", "payment proof", "other parent's income/location", "execution or recovery steps already taken"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
        )

    if _is_property_transfer_document_issue(q):
        return MatterRoute(
            category="property_tenancy",
            label="Property transfer / gift deed dispute",
            confidence=0.78,
            urgency="medium",
            required_sources=["Transfer of Property Act 1882", "Indian Contract Act 1872 where consent, coercion, undue influence, or authority is disputed", "Registration Act / civil court procedure where document validity is disputed"],
            forums=["civil court", "revenue/registration office where records must be checked", "District Legal Services Authority"],
            missing_facts=["state/city", "registered document type", "signing/thumb-impression date", "ownership and consideration facts", "possession status", "fraud/coercion evidence"],
            red_flags=_red_flags(q),
            action_pack=_property_pack(),
        )

    if _is_forced_adult_or_lgbt_marriage(q):
        return MatterRoute(
            category="family_domestic",
            label="Adult autonomy / forced marriage protection",
            confidence=0.78,
            urgency="high",
            required_sources=["Article 21 partner-choice and personal liberty principles", "domestic-violence/family protection route where threats or confinement exist", "BNS/BNSS or IPC/CrPC where criminal intimidation or confinement is involved"],
            forums=["District Legal Services Authority", "police for threats or confinement", "Protection Officer/Magistrate", "High Court writ jurisdiction for liberty protection"],
            missing_facts=["age", "current location and safety", "planned marriage date", "threats/confinement", "state/city", "support person"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("threat", "locked", "force", "forcing", "confinement")) else None,
        )

    return None


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


def _is_acid_chemical_attack_issue(q: str) -> bool:
    injury_context = _has_any(q, (
        "acid", "acid attack", "chemical attack", "chemical thrown",
        "threw acid", "threw chemical", "threw something on my face",
        "eyes are burning", "eyes burning", "face burning",
    ))
    urgent_context = _has_any(q, (
        "what to do", "hospital", "road", "auto driver", "police", "fir",
        "burning", "burn", "injury", "threat", "threaten", "threatens",
        "threatened", "threatening", "throw acid", "throw chemical",
    ))
    return injury_context and urgent_context


def _is_habeas_illegal_detention_issue(q: str) -> bool:
    liberty_context = _has_any(q, (
        "habeas corpus", "illegal detention", "illegally detained",
        "detained illegally", "unlawful detention",
    ))
    authority_context = _has_any(q, ("police", "jail", "custody", "authority", "state", "thana"))
    return liberty_context and authority_context


def _is_private_magistrate_complaint_issue(q: str) -> bool:
    complaint_context = _has_any(q, (
        "private complaint", "complaint before magistrate", "magistrate complaint",
        "file complaint before magistrate", "file private complaint",
        "156(3)", "156 3", "section 156", "section 200",
    ))
    police_inaction_context = _has_any(q, (
        "police inaction", "police not acting", "police refused",
        "police not taking", "police not registering", "no fir",
    ))
    return complaint_context or ("magistrate" in q and police_inaction_context)


def _is_mgnrega_social_audit_issue(q: str) -> bool:
    mgnrega_context = _has_any(q, ("mgnrega", "nrega", "job card", "muster roll", "social audit"))
    local_body_context = _has_any(q, ("gram sabha", "panchayat", "sarpanch", "mukhiya", "bdo", "programme officer"))
    grievance_context = _has_any(q, ("corruption", "fake", "no action", "wage", "payment", "muster", "audit"))
    return mgnrega_context and local_body_context and grievance_context


def _is_hate_or_identity_insult_crime(q: str) -> bool:
    if _has_any(q, (
        "caste", "caste slur", "caste name", "upper caste", "dominant caste",
        "dalit", "adivasi", "sc st", "sc/st", "untouchable", "atrocity",
    )):
        return False
    identity_context = _has_any(q, (
        "biharee", "bihari", "regional slur", "caste slur", "caste name",
        "dalit", "adivasi", "sc st", "sc/st",
    ))
    insult_context = _has_any(q, ("called", "calling", "slur", "insult", "abuse", "abused"))
    legal_context = _has_any(q, ("crime", "fir", "complaint", "police", "case", "what section"))
    return identity_context and insult_context and legal_context


def _is_commercial_mediation_procedure(q: str) -> bool:
    commercial_context = _has_any(q, ("commercial suit", "commercial court", "commercial dispute"))
    mediation_context = _has_any(q, (
        "pre litigation mediation", "pre-litigation mediation",
        "pre institution mediation", "pre-institution mediation",
        "respondent skipped", "mediation notice", "section 12a", "12a",
    ))
    return commercial_context and mediation_context


def _is_environment_damage_issue(q: str) -> bool:
    education_room_context = _has_any(q, (
        "engineering college", "college", "hostel room", "hostel", "dorm room",
        "campus room",
    ))
    project_land_context = _has_any(q, (
        "land acquisition", "land acquired", "village", "villages", "palli sabha",
        "gram sabha", "mining company", "mining project", "iron ore",
        "coal block", "bauxite project", "lease", "rehabilitation colony",
        "land taken for highway", "taken for highway", "highway compensation",
    ))
    if education_room_context and not project_land_context:
        return False
    if _has_any(q, ("ngt", "national green tribunal", "wetland")) and _has_any(q, (
        "complaint", "file", "illegal construction", "encroachment", "construction",
        "pollution", "damage", "protect",
    )):
        return True
    environment_context = _has_any(q, (
        "pollution", "chemical water", "factory", "thermal plant", "blasting",
        "effluent", "borewell water", "water pollution", "mining company",
        "land acquired", "coal block", "palli sabha", "bauxite project",
        "mining project", "iron ore", "iron ore mine", "mine displaced",
        "wetland", "illegal construction near wetland", "chemicals",
        "throwing chemicals", "dam", "dam project", "project displaced",
        "highway project", "road widening", "land taken for highway",
        "taken for highway", "highway compensation",
    ))
    damage_context = _has_any(q, (
        "damaged", "cracking", "crack", "bad", "bad water", "no compensation",
        "compensation", "pollution", "acquired", "displaced",
        "displacement", "rehabilitation", "no rehabilitation",
        "illegal construction", "encroachment", "complaint", "chemicals",
        "throwing chemicals", "borewell water", "not received", "still not received",
        "who to ask",
    ))
    return environment_context and damage_context


def _is_land_acquisition_compensation_issue(q: str) -> bool:
    land_context = _has_any(q, (
        "land acquisition", "land acquired", "land taken", "taken my land",
        "taken for highway", "land taken for highway", "road widening",
        "highway project", "highway compensation", "acquired for",
        "rfctlarr", "larr",
    ))
    affected_asset_context = bool(re.search(r"\b(?:land|plot|shop|house|field|farm)\b", q))
    project_context = _has_any(q, ("highway", "road widening", "project", "acquisition", "acquired", "taken"))
    compensation_context = _has_any(q, (
        "compensation", "award", "payment", "deposit", "not paid",
        "not received", "still not received", "who to ask", "amount",
    ))
    return (land_context or (affected_asset_context and project_context)) and compensation_context


def _is_mining_displacement_matter(q: str) -> bool:
    mining_context = _has_any(q, (
        "iron ore", "iron ore mine", "mining project", "mining company",
        "mine displaced", "mine displacement", "mining displacement",
        "coal block", "bauxite project",
    ))
    displacement_context = _has_any(q, (
        "displaced", "displacement", "rehabilitation", "no rehabilitation",
        "resettlement", "rehabilitation package",
    ))
    community_land_context = _has_any(q, (
        "village", "villages", "land", "families", "houses", "gram sabha",
        "palli sabha", "scheduled area", "keonjhar",
    ))
    return mining_context and displacement_context and community_land_context


def _is_tribal_project_displacement_issue(q: str) -> bool:
    tribal_or_scheduled_context = _has_any(q, (
        "tribal", "adivasi", "scheduled tribe", "scheduled area",
        "gram sabha", "pesa", "palli sabha",
    ))
    project_context = _has_any(q, (
        "dam", "submerge", "submerges", "submerged", "submergence",
        "land acquisition", "land acquired", "acquired for", "project",
        "power plant", "hydro project", "irrigation project",
    ))
    community_context = _has_any(q, (
        "village", "villages", "families", "houses", "land", "forest",
        "gram sabha", "palli sabha",
    ))
    consent_or_rr_context = _has_any(q, (
        "no consent", "without consent", "consent", "gram sabha",
        "rehabilitation", "resettlement", "compensation", "no compensation",
        "submerge", "submerged", "submergence", "displaced", "displacement",
    ))
    return tribal_or_scheduled_context and project_context and community_context and consent_or_rr_context


def _is_section_91_notice(q: str) -> bool:
    return _has_any(q, _SECTION_91_NOTICE_WORDS) and _has_any(q, ("police", "court", "fir", "case", "notice", "summons", "io", "investigating officer"))


def _is_passport_procedure(q: str) -> bool:
    return "passport" in q and _has_any(q, _PASSPORT_PROCEDURE_WORDS + ("criminal case", "case pending", "warrant", "summons"))


def _is_education_loan_denial(q: str) -> bool:
    loan_context = _has_any(q, ("education loan", "student loan", "loan for education", "loan for school", "loan for college"))
    bank_context = _has_any(q, ("bank", "nbfc", "not giving", "refused", "rejected", "denied", "denial"))
    education_context = _has_any(q, ("daughter", "son", "student", "scholarship", "school", "college", "course"))
    return loan_context and bank_context and education_context


def _is_trans_identity_certificate_issue(q: str) -> bool:
    if _has_any(q, ("not gender change", "not a gender change", "not changing gender")):
        return False
    trans_context = _has_any(q, (
        "transgender", "trans woman", "transwoman", "trans man", "transman",
        "trans person", "change my gender", "gender change",
        "gender on aadhaar", "gender on aadhar", "gender in aadhaar",
        "gender in aadhar", "gender on 10th", "gender on tenth",
        "gender on certificate", "gender on marksheet",
    ))
    record_context = _has_any(q, (
        "aadhaar", "aadhar", "certificate", "10th certificate", "marksheet",
        "school record", "identity", "id", "surgery", "not had surgery",
        "without surgery",
    ))
    return trans_context and record_context


def _is_lok_adalat_challenge(q: str) -> bool:
    return _has_any(q, _LOK_ADALAT_CHALLENGE_WORDS) and _has_any(q, ("challenge", "set aside", "cancel", "fraud", "coercion", "without consent", "appeal", "review"))


def _is_lok_adalat_traffic_settlement(q: str) -> bool:
    lok_context = _has_any(q, ("lok adalat", "lokadalat", "national lok adalat"))
    traffic_context = _has_any(q, ("traffic challan", "challan", "e-challan", "vehicle fine", "traffic fine"))
    settlement_context = _has_any(q, ("settlement", "settle", "approach", "pending", "pay", "reduce", "compromise"))
    return lok_context and traffic_context and settlement_context


def _is_undertrial_review_issue(q: str) -> bool:
    if _has_any(q, ("not undertrial", "not an undertrial")):
        return False
    if _is_interim_medical_bail_issue(q):
        return False
    if _has_any(q, ("convicted", "after conviction", "convict")) and _has_any(q, ("parole", "furlough", "remission")):
        return False
    review_context = _has_any(q, _UNDERTRIAL_REVIEW_WORDS)
    custody_context = _has_any(q, (
        "undertrial", "jail", "prison", "custody", "tihar", "puzhal",
        "byculla", "yerwada", "paralegal", "dlsa", "legal aid",
    ))
    if not custody_context:
        return False
    if review_context:
        return True
    undertrial_context = "undertrial" in q
    release_delay_context = _has_any(q, (
        "release", "bail", "trial not started", "trial delay", "long custody",
        "jail since", "custody since", "half sentence", "half maximum",
        "maximum punishment", "completed half",
    ))
    return undertrial_context and release_delay_context


def _is_interim_medical_bail_issue(q: str) -> bool:
    custody_context = _has_any(q, (
        "jail", "prison", "custody", "undertrial", "undertrials",
        "byculla", "arthur road", "tihar", "puzhal", "yerwada",
        "paralegal",
    ))
    medical_context = _has_any(q, (
        "pregnant", "pregnancy", "new born", "newborn", "medical",
        "doctor", "hospital", "treatment", "tb", "medicine",
    ))
    bail_context = _has_any(q, (
        "bail", "interim bail", "medical bail", "postpone trial",
        "postpone", "release", "custody",
    ))
    return custody_context and medical_context and bail_context


def _is_prison_medical_bail_issue(q: str) -> bool:
    custody_context = _has_any(q, ("jail", "prison", "arthur road", "tihar", "custody", "undertrial"))
    medical_context = _has_any(q, ("tb", "test not done", "doctor", "medical", "hospital", "treatment", "medicine"))
    delay_context = _has_any(q, ("waiting", "months", "4 months", "not done", "refused", "delay"))
    return custody_context and medical_context and delay_context


def _is_pocso_minor_accused_issue(q: str) -> bool:
    relationship_context = _has_any(q, ("girlfriend", "boyfriend", "relationship", "love", "came on her own", "consensual"))
    pocso_context = _has_any(q, ("pocso", "minor", "14 year", "15 year", "16 year", "17 year", "under 18"))
    accused_context = _has_any(q, (
        "filed pocso on me", "filed pocso against me", "pocso on me",
        "pocso against me", "case against me", "against me",
        "i am accused", "i'm accused", "accused me", "accused in pocso",
        "need bail", "anticipatory bail", "regular bail", "arrested me",
        "police arrested me", "my bail",
    ))
    accused_context = accused_context or (
        _has_any(q, ("i am 17", "i was 17", "i am 16", "i was 16"))
        and _has_any(q, ("on me", "against me", "arrest", "bail", "accused"))
    )
    return relationship_context and pocso_context and accused_context


def _is_accused_498a_issue(q: str) -> bool:
    if not _has_any(q, ("498a", "dowry case")):
        return False
    complainant_context = _has_any(q, (
        "i filed 498a", "i have filed 498a", "i lodged 498a",
        "i filed dowry case", "my 498a complaint", "against my husband",
        "against my in laws", "against my in-laws",
    )) and not _has_any(q, (
        "against me", "on me", "my wife filed", "wife filed",
        "filed by wife", "false 498a",
    ))
    if complainant_context:
        return False
    return _has_any(q, (
        "498a against me", "498a on me", "case against me",
        "my wife filed", "wife filed", "filed by wife", "false 498a",
        "against my family", "whole family", "old mother", "defend",
        "accused", "anticipatory bail", "regular bail", "quash", "quashing",
        "police notice to me", "summons to me",
    ))


def _is_498a_complainant_protection_issue(q: str) -> bool:
    complainant_context = _has_any(q, (
        "i filed 498a", "i have filed 498a", "i lodged 498a",
        "498a against my husband", "498a against husband",
        "dowry case against my husband", "my 498a complaint",
    ))
    support_context = _has_any(q, (
        "protection", "maintenance", "residence", "shelter", "husband",
        "in laws", "in-laws", "sasural", "dowry",
    ))
    return complainant_context and support_context


def _is_custodial_violence_issue(q: str) -> bool:
    person_custody = _has_any(q, (
        "lockup", "custody", "detained", "detention", "arrest", "arrested",
        "after arrest", "jail", "prison",
        "custodial death", "lockup death",
        "not released me", "not released him", "not released her",
        "did not release me", "did not release him", "did not release her",
        "not released my brother", "not released my husband",
        "still not released", "kept me", "kept my brother",
    ))
    custody_authority_context = _has_any(q, (
        "lockup", "custody", "custodial", "constable", "police station",
        "thana", "jail", "prison", "jail guard", "prison guard",
    ))
    police_context = custody_authority_context or (_has_any(q, ("police",)) and person_custody)
    violence = _has_any(q, (
        "beaten", "beat", "beating", "torture", "assault", "injury", "hurt",
        "death", "died", "suicide", "hanging",
    ))
    extortion = _has_any(q, ("took 20000", "bribe", "money for bail", "paid for bail", "demanded money"))
    release_blocked = person_custody and _has_any(q, (
        "not released", "still not released", "did not release",
        "refused to release", "kept in lockup", "kept in custody",
        "kept my brother in custody", "kept my husband in custody",
    ))
    return police_context and (violence or extortion or release_blocked)


def _is_domestic_residence_issue(q: str) -> bool:
    residence_loss = _has_any(q, ("ghar se nikal", "nikal diya", "threw me out", "kicked me out", "sasural", "shared household"))
    marital_context = _has_any(q, ("husband", "wife", "sasural", "in laws", "married", "marriage"))
    return residence_loss and marital_context


def _is_adult_forced_marriage_issue(q: str) -> bool:
    adult_context = _has_age_at_least(q, 18) or _has_any(q, ("i am 26", "adult", "major"))
    marriage_context = _has_any(q, (
        "forcing me to marry", "force me to marry", "forced marriage",
        "parents are forcing", "marry a", "marry him", "marry her",
        "marriage next", "shaadi", "love marriage", "partner choice",
    ))
    coercion_context = _has_any(q, (
        "forcing", "force", "forced", "not listening", "locked",
        "threat", "confined", "not allowing",
    ))
    return adult_context and marriage_context and coercion_context


def _is_spa_trafficking_issue(q: str) -> bool:
    commercial_sex_context = _has_any(q, ("spa", "customers want extra", "owner makes us", "extra and owner", "if we refuse no salary"))
    coercion_context = _has_any(q, ("makes us", "force", "forced", "refuse no salary", "no salary", "cannot leave"))
    return commercial_sex_context and coercion_context


def _is_child_labour_issue(q: str) -> bool:
    child_context = (
        _has_age_under(q, 18)
        or bool(re.search(r"\b(?:child|girl|boy|minor)\s*(?:aged?\s*)?(?:1[0-7]|[1-9])\b", q))
        or _has_any(q, ("girl 15", "boy 15", "child worker", "minor worker", "girl child", "boy child"))
    )
    work_context = _has_any(q, (
        "factory", "garment", "unit", "working", "worker", "labour", "employ",
        "domestic work", "house work", "household work", "helping mother",
        "helping in", "migrant camp", "camp work",
    ))
    return child_context and work_context


def _is_caste_bonded_labour_issue(q: str) -> bool:
    protected_class_context = _has_any(q, (
        "dalit", "scheduled caste", "scheduled tribe", "sc/st", "sc st",
        "adivasi", "tribal", "caste slur", "caste name", "untouchable",
        "chamar", "munda", "sarna", "pahan",
    )) or re.search(r"\b(?:sc|st)\b", q) is not None
    caste_power_or_targeting_context = _has_any(q, (
        "thakur", "zamindar", "upper caste", "landlord caste", "caste people",
        "caste", "atrocity", "poa",
    ))
    bonded_context = _is_bonded_labour_rescue(q) or (
        _has_any(q, ("no wages", "just food", "only food", "12 years", "years no wages"))
        and _has_any(q, ("working", "work", "labour", "servant", "field"))
    )
    return protected_class_context and bonded_context


def _is_ndps_personal_use_issue(q: str) -> bool:
    if _has_any(q, ("digital arrest", "fake cbi", "fake police call", "otp", "upi", "paid", "transferred", "lost money")):
        return False
    substance_context = _has_any(q, _NDPS_PERSONAL_USE_WORDS) or _has_any(q, (
        "parcel has drugs", "drug packet", "drugs in parcel",
    ))
    enforcement_context = _has_any(q, (
        "caught", "police", "case", "fir", "arrest", "bail", "seized",
        "airport", "customs", "passport seized", "legal in goa", "punishment",
    ))
    return substance_context and enforcement_context


def _is_motor_vehicle_traffic_police_issue(q: str) -> bool:
    vehicle_context = _has_any(q, (
        "auto driver", "taxi driver", "cab driver", "driver license",
        "driving license", "driver licence", "driving licence", "licence invalid",
        "license invalid", "permit", "challan", "traffic police", "rto",
        "transport department",
    ))
    enforcement_context = _has_any(q, (
        "traffic police", "no challan", "challan", "taking 500", "taking money",
        "bribe", "fine", "license invalid", "licence invalid", "seized vehicle",
    ))
    return vehicle_context and enforcement_context


def _is_prohibition_excise_accused_issue(q: str) -> bool:
    alcohol_context = _has_any(q, (
        "prohibition law", "excise act", "liquor case", "alcohol case",
        "drinking village", "caught me drinking", "drinking alcohol",
        "desi daru", "sharab", "liquor",
    ))
    enforcement_context = _has_any(q, ("police", "case", "fir", "caught", "punishment", "arrest", "bail"))
    return alcohol_context and enforcement_context


def _is_scst_poa_procedure_issue(q: str) -> bool:
    poa_context = _has_any(q, ("poa act", "atrocity", "sc/st", "sc st", "caste atrocity", "poa case"))
    procedure_context = _has_any(q, (
        "dsp", "sp not", "transferring", "investigation", "officer rank",
        "special court", "pending", "5 years", "five years", "delay",
    ))
    return poa_context and procedure_context


def _is_custody_compensation_issue(q: str) -> bool:
    custody_history = _has_any(q, ("jail", "custody", "prison")) and _has_any(q, ("acquitted", "released", "7 yrs", "7 years"))
    compensation_context = _has_any(q, ("compensation", "state legal aid", "legal aid"))
    return custody_history and compensation_context


def _is_company_compliance_issue(q: str) -> bool:
    llp_context = _has_any(q, ("llp", "limited liability partnership", "form 11"))
    if llp_context:
        return _has_any(q, (
            "not filed", "annual return", "form 11", "partner refusing",
            "refusing to sign", "strike off", "filing",
        ))

    criminal_report_context = _has_any(q, (
        "police", "fir", "criminal complaint", "cheat", "cheated",
        "cheating", "fraud", "420", "complaint not filed", "not filed fir",
    ))
    corporate_marker = _has_any(q, (
        "private limited", "pvt ltd", "mgt 7", "aoc 4", "roc", "mca",
        "cin", "annual return", "financial statement", "financial statements",
        "director disqualified", "disqualified director", "strike off", "revive",
    ))
    if criminal_report_context and not corporate_marker:
        return False

    explicit_company_context = _has_any(q, (
        "private limited", "pvt ltd", "company director",
        "director disqualified", "disqualified director",
        "mgt 7", "aoc 4", "roc", "mca", "cin",
    ))
    corporate_compliance_context = _has_any(q, (
        "mgt 7", "aoc 4", "not filed", "director disqualified",
        "disqualified", "revive", "strike off", "annual return",
        "financial statement", "financial statements",
    ))
    return explicit_company_context and corporate_compliance_context


def _is_drug_license_compliance_issue(q: str) -> bool:
    pharmacy_context = _has_any(q, (
        "drug inspector", "drugs inspector", "drug controller",
        "medical store", "pharmacy", "chemist shop", "schedule h",
        "drug sample", "sample picked", "picked up samples",
    ))
    prescription_sale_context = _has_any(q, ("without prescription", "schedule h")) and _has_any(q, (
        "medical store", "pharmacy", "chemist", "sale", "sold", "selling",
        "drug inspector", "sample", "samples",
    ))
    compliance_context = _has_any(q, (
        "notice", "sample", "samples", "sale", "without prescription",
        "licence", "license", "inspection", "inspector", "schedule h",
    ))
    return (pharmacy_context or prescription_sale_context) and compliance_context


def _is_food_license_issue(q: str) -> bool:
    food_authority_context = _has_any(q, (
        "fssai", "food licence", "food license", "food safety officer",
        "designated officer", "food authority",
    ))
    food_business_context = _has_any(q, (
        "snack manufacturing", "kirana", "masala", "packet", "food business",
        "restaurant", "dhaba", "canteen",
    ))
    compliance_context = _has_any(q, (
        "licence", "license", "notice", "renewal", "category", "central",
        "state", "sample", "adulteration", "misbranding", "improvement notice",
    ))
    return (food_authority_context or food_business_context) and compliance_context


def _is_digital_money_platform_issue(q: str) -> bool:
    platform_money = _has_any(q, ("binance", "usdt", "wallet", "dream11", "parimatch", "betting app", "rummy", "online gaming"))
    money_or_freeze = _has_any(q, ("froze", "frozen", "suspicious", "lost", "recover", "money", "lakh", "50k"))
    return platform_money and money_or_freeze


def _is_online_gambling_issue(q: str) -> bool:
    gambling_context = _has_any(q, (
        "dream11", "parimatch", "betting app", "betting site",
        "online betting", "online gambling", "online rummy", "rummy app",
        "fantasy app", "gaming app", "real money game", "real-money game",
    ))
    stake_context = _has_any(q, (
        "lost", "recover", "money", "stake", "stakes", "wager", "bet",
        "legal", "illegal", "allowed", "ban", "banned", "50k", "lakh",
    ))
    return gambling_context and stake_context


def _has_tamil_nadu_context(q: str) -> bool:
    return _has_any(q, (
        "tamil nadu", "chennai", "coimbatore", "madurai",
        "tiruchirappalli", "trichy", "salem", "tirunelveli", "cuddalore",
    ))


def _is_payment_refund_service_issue(q: str) -> bool:
    payment_context = _has_any(q, ("upi", "payment", "bank transfer", "transaction"))
    refund_context = _has_any(q, ("bounced back", "failed", "reversed", "refund", "refunding", "merchant"))
    merchant_context = _has_any(q, ("merchant", "seller", "shop", "order", "service"))
    fraud_context = _has_any(q, ("otp", "phishing", "scam", "unauthorized", "fraud", "lost money", "hacked"))
    return payment_context and refund_context and merchant_context and not fraud_context


def _is_document_fraud_issue(q: str) -> bool:
    document_context = _has_any(q, ("thumb impression", "blank paper", "forged", "fake signature", "didn't sign", "did not sign"))
    fraud_context = _has_any(q, ("loan", "gift deed", "moneylender", "bank", "showing", "produced", "fraud"))
    return document_context and fraud_context


def _is_business_contract_issue(q: str) -> bool:
    if _is_work_injury(q):
        return False
    if not _has_any(q, _BUSINESS_CONTRACT_WORDS):
        return False
    consumer_or_personal_context = _has_any(q, (
        "online order", "refund", "seller", "landlord", "tenant", "rent",
        "deposit", "hospital", "doctor", "patient", "medical bill",
        "husband", "wife", "boyfriend", "girlfriend", "live in partner",
        "domestic violence", "violence", "threatens me",
    ))
    commercial_context = _has_any(q, (
        "client", "buyer", "supplier", "vendor", "saas", "purchase order",
        "po ", "invoice", "msme", "msmed", "udyam", "samadhan", "msefc",
        "samadhaan", "msme registered", "msme samadhan portal",
        "public sector buyer", "psu",
        "business", "company", "firm", "partnership", "dealer", "agent",
        "principal agent", "principal-agent", "goods worth", "customer list",
        "trade secret", "co founder", "co-founder", "shareholder", "equity",
        "delivery partner", "commercial court", "commercial suit",
        "machinery", "equipment", "goods",
    ))
    strong_commercial_context = _has_any(q, (
        "client", "buyer", "supplier", "vendor", "saas", "purchase order",
        "msme", "msmed", "udyam", "samadhan", "msefc", "business", "company",
        "samadhaan", "msme registered", "msme samadhan portal",
        "public sector buyer", "psu",
        "firm", "partnership", "dealer", "principal agent", "principal-agent",
        "goods worth", "customer list", "trade secret", "co founder",
        "co-founder", "shareholder", "equity", "delivery partner",
        "commercial court", "commercial suit", "machinery", "equipment",
        "goods",
    ))
    if consumer_or_personal_context and not strong_commercial_context:
        return False
    if _has_any(q, ("partnership", "business partner", "partner in firm", "retire from partnership")):
        return True
    business_dispute = _has_any(q, (
        "not paying", "unpaid", "deducting payment", "formal rejection",
        "quality issue", "lakh stuck", "breach", "contract", "liability",
        "absconded", "invoice", "non compete", "non-compete", "nda",
        "specific performance", "exclusivity", "dilute my equity",
        "diluting my equity", "esop", "minority shareholder",
        "shareholder oppressing", "commission dispute", "agreement",
        "payment delay", "45 days payment", "amount outstanding",
        "not paid", "non payment", "charge interest", "samadhan portal",
        "commercial court", "pre litigation mediation", "pre-litigation mediation",
        "recover advance", "advance", "cancel and recover", "delivery in 30 days",
        "failed to deliver", "did not deliver", "not delivered",
    ))
    return commercial_context and business_dispute


def _is_simple_hurt_accused_issue(q: str) -> bool:
    hurt_context = _has_any(q, ("slap", "slapped", "hit", "pushed", "assault"))
    direct_victim_context = _has_any(q, (
        "slapped me", "hit me", "pushed me", "assaulted me",
        "punched me", "beat me", "beaten me",
    ))
    family_context = _has_any(q, (
        "husband", "wife", "in laws", "in-laws", "mother in law",
        "father in law", "married", "marriage", "live in partner",
        "live-in partner", "domestic relationship",
    ))
    accused_context = _has_any(q, (
        "case on me", "case against me", "filing case on me",
        "filed case on me", "complaint against me", "against me",
        "fir against me", "notice to me", "police called me",
    ))
    self_action_context = bool(re.search(
        r"\bi\s+(?:also\s+)?(?:slapped|hit|pushed|assaulted|punched|beat)\b",
        q,
    )) or _has_any(q, ("i caught them i slapped", "i slapped the", "i hit the"))
    if (direct_victim_context or family_context) and not self_action_context:
        return False
    return hurt_context and (accused_context or self_action_context)


def _is_simple_hurt_complainant_issue(q: str) -> bool:
    if _is_simple_hurt_accused_issue(q):
        return False
    family_context = _has_any(q, (
        "husband", "wife", "in laws", "in-laws", "mother in law",
        "father in law", "married", "marriage", "live in partner",
        "live-in partner", "domestic relationship",
    ))
    if family_context:
        return False
    direct_victim_context = _has_any(q, (
        "slapped me", "hit me", "pushed me", "assaulted me",
        "punched me", "beat me", "beaten me",
    ))
    third_party_victim_context = _has_any(q, (
        "slapped my", "hit my", "pushed my", "assaulted my",
        "punched my", "beat my", "beaten my",
    ))
    return direct_victim_context or third_party_victim_context


def _is_business_license_issue(q: str) -> bool:
    if not _has_any(q, _BUSINESS_LICENSE_WORDS):
        return False
    employee_wage_context = _has_any(q, (
        "wage", "wages", "salary", "overtime", "not paid", "unpaid",
        "employee overtime", "worker overtime", "minimum wage",
    ))
    if employee_wage_context:
        return False
    registration_context = _has_any(q, (
        "register", "registration", "renewal", "licence", "license",
        "permit", "fssai", "notice", "inspector said", "trade license",
    ))
    return registration_context


def _is_labour_exploitation_issue(q: str) -> bool:
    if not _has_any(q, _LABOUR_EXPLOITATION_WORDS):
        return False
    project_displacement = _has_any(q, (
        "dam", "land acquisition", "larr", "project displaced",
        "displaced by", "mining project", "thermal plant",
    ))
    strong_labour_context = _has_any(q, (
        "thekedar", "contractor", "munshi", "employer", "wage", "wages",
        "salary", "came together",
        "brought from", "return ticket", "migrant registration", "ismw",
        "factory", "site", "domestic worker", "job card", "mgnrega",
        "labour card", "bocw", "cess", "deducted", "half pay",
        "site supervisor", "minimum wage", "minimum wages", "state rate",
        "unskilled", "construction",
    ))
    return not project_displacement or strong_labour_context


def _is_bocw_registration_issue(q: str) -> bool:
    bocw_context = _has_any(q, ("bocw", "building worker", "construction worker", "construction welfare board"))
    registration_or_cess = _has_any(q, (
        "registration", "register", "card", "welfare board", "benefit",
        "cess", "same name", "fake name", "real names", "name on register",
    ))
    return bocw_context and registration_or_cess and not _is_work_injury(q)


def _is_it_act_67_accused_issue(q: str) -> bool:
    section_context = _has_any(q, ("67 case", "section 67", "it act 67", "67 notice", "filed 67"))
    if not section_context:
        return False
    self_complainant = bool(re.search(r"\bi\s+(?:filed|registered|gave|made)\b", q))
    other_filed = bool(re.search(r"\b(?:she|he|they|ex|girlfriend|boyfriend|girl|woman|man|police)\s+(?:has\s+)?filed\b", q))
    self_action = _has_any(q, ("i shared", "i posted", "i sent", "i uploaded", "i forwarded"))
    accused_marker = _has_any(q, ("case against me", "against me", "notice to me", "summons to me", "accused", "arrest"))
    support_or_third_party_context = (
        _has_any(q, ("evidence", "with police", "to police", "help her", "help him", "sister", "daughter", "friend"))
        or bool(re.search(r"\bfiled\b.*\bagainst\s+(?:her|his|their)\s+(?:ex|boyfriend|girlfriend|husband|wife)\b", q))
    )
    if support_or_third_party_context and not accused_marker:
        return False
    return (accused_marker or (self_action and other_filed)) and not (self_complainant and not accused_marker)


def _is_rape_promise_accused_issue(q: str) -> bool:
    case_context = _has_any(q, ("rape case", "filed rape", "accused of rape", "case against me"))
    promise_context = _has_any(q, ("promised marriage", "promise marriage", "dating", "relationship", "broke up", "breakup"))
    self_complainant = bool(re.search(r"\bi\s+(?:filed|registered|gave|made)\b", q))
    other_filed = bool(re.search(r"\b(?:she|girl|woman|girlfriend|ex)\s+(?:has\s+)?filed\b", q))
    accused_context = _has_any(q, ("against me", "i was dating", "i promised", "we had relationship", "accused", "arrest")) or other_filed
    if self_complainant and not _has_any(q, ("against me", "accused", "arrest")):
        return False
    return case_context and promise_context and accused_context


def _is_stalking_harassment_issue(q: str) -> bool:
    stalking_context = _has_any(q, ("stalker", "stalking", "stalked", "follows", "following", "followed"))
    repeated_or_route_context = _has_any(q, (
        "everyday", "daily", "office to home", "scooty", "after blocking",
        "dm daily", "direct message", "dms", "messages", "doesn't talk", "does not talk",
    ))
    return stalking_context and (repeated_or_route_context or _has_any(q, ("complaint", "what section", "file complaint")))


def _is_minor_interfaith_relationship_issue(q: str) -> bool:
    minor_context = _has_age_under(q, 18) or _has_any(q, ("minor", "under 18", "under eighteen"))
    relationship_context = _has_any(q, ("ran away", "eloped", "love jihad", "different religion", "other religion", "interfaith", "inter-faith"))
    police_or_family_context = _has_any(q, ("police", "family", "parents", "father", "mother", "threat", "missing"))
    return minor_context and relationship_context and police_or_family_context


def _is_honour_threat_issue(q: str) -> bool:
    relationship_context = _has_any(q, ("eloped", "ran away", "different religion", "other religion", "interfaith", "inter-faith", "love marriage"))
    threat_context = _has_any(q, ("khap", "family threatening", "threatening her", "threatening him", "honour", "honor", "kill", "mob"))
    return relationship_context and threat_context


def _is_dowry_death_issue(q: str) -> bool:
    death_context = _has_any(q, ("died", "death", "suicide", "body", "dead", "burnt", "burned"))
    marital_context = _has_any(q, ("in laws", "in-laws", "husband", "married", "sister", "wife", "daughter"))
    suspicious_context = _has_any(q, ("dowry", "body had marks", "marks", "suicide", "suspicious", "burnt", "burned"))
    return death_context and marital_context and suspicious_context


def _is_family_economic_abuse_issue(q: str) -> bool:
    family_context = _has_any(q, ("husband", "wife", "domestic relationship", "live in partner"))
    control_context = _has_any(q, (
        "took my salary", "salary atm", "atm card", "bank card", "takes my salary",
        "only 2000", "groceries", "breadwinner", "not giving money",
    ))
    return family_context and control_context


def _is_deceitful_intercourse_issue(q: str) -> bool:
    complainant_context = _has_any(q, ("boyfriend", "living with", "live in", "promised marriage", "promise marriage"))
    deception_context = _has_any(q, ("promised marriage", "promise marriage", "now he is marrying", "marrying another", "file case"))
    return complainant_context and deception_context and not _is_rape_promise_accused_issue(q)


def _is_undertrial_legal_aid_issue(q: str) -> bool:
    undertrial_context = _has_any(q, ("undertrial", "under trial", "in jail", "in prison", "puzhal", "tihar", "yerwada"))
    legal_aid_context = _has_any(q, (
        "lawyer not coming", "lawyer not appearing", "legal aid not helping",
        "hearings", "hearing", "complain", "complaint", "dlsa", "nalsa",
    ))
    custody_duration = _has_any(q, ("3 yrs", "3 years", "three years", "long custody", "trial not started"))
    return undertrial_context and (legal_aid_context or custody_duration)


def _is_sarfaesi_issue(q: str) -> bool:
    return _has_any(q, ("sarfaesi", "13(2)", "13(4)", "security interest", "possession notice")) and _has_any(q, ("bank", "loan", "default", "notice", "possession", "negotiate"))


def _is_msme_payment_issue(q: str) -> bool:
    if not _is_business_contract_issue(q):
        return False
    explicit_msme = _has_any(q, (
        "msme", "msmed", "udyam", "samadhan", "samadhaan", "msefc",
        "msme registered", "micro enterprise", "small enterprise",
    ))
    forty_five_day_context = _has_any(q, ("45 days payment", "45 day payment", "it act 43b", "43b(h)"))
    return explicit_msme or forty_five_day_context


def _is_transport_permit_issue(q: str) -> bool:
    permit_context = _has_any(q, ("auto permit", "taxi permit", "cab permit", "transport permit", "permit renewal", "permit expired"))
    vehicle_context = _has_any(q, ("auto", "taxi", "cab", "vehicle", "rto", "transport"))
    renewal_context = _has_any(q, ("expired", "renew", "renewal", "lockdown", "permit"))
    return permit_context or (vehicle_context and renewal_context and "permit" in q)


def _is_labour_compliance_notice(q: str) -> bool:
    if _is_esi_benefit_issue(q):
        return False
    if _is_labour_overtime_register_notice(q):
        return True
    esi_context = _has_any(q, ("esi", "esic", "employees state insurance", "employees' state insurance"))
    compliance_context = _has_any(q, (
        "inspector", "notice", "contribution", "short contribution",
        "casual workers", "contest", "demand", "assessment", "coverage",
    ))
    wage_rule_context = _has_any(q, (
        "code on wages", "minimum wage notification", "minimum wages notification",
        "state rate", "floor wage", "unskilled worker", "wage notification",
    ))
    wage_applicability_context = _has_any(q, ("applicable", "apply", "notification", "gujarat", "unskilled"))
    return (esi_context and compliance_context) or (wage_rule_context and wage_applicability_context)


def _is_labour_overtime_register_notice(q: str) -> bool:
    inspection_context = _has_any(q, (
        "labour department", "labor department", "labour inspector",
        "labor inspector", "inspection", "raid", "raided",
    ))
    register_context = _has_any(q, (
        "overtime register", "ot register", "register not maintained",
        "not maintained", "records not maintained", "registers", "records",
    ))
    worker_count_context = bool(re.search(r"\b(?:1[0-9]|[2-9][0-9])\s+workers?\b", q))
    return inspection_context and register_context and ("overtime" in q or worker_count_context)


def _is_manual_scavenging_issue(q: str) -> bool:
    if _has_any(q, ("overflowing", "not cleaning", "needs cleaning", "cleaning complaint")) and not _has_any(q, ("forcing", "forced", "made me", "worker", "safai", "manual scavenging")):
        return False
    septic_or_sewer = _has_any(q, (
        "septic tank", "sewer", "manhole", "drain cleaning",
        "sewer cleaning", "septic cleaning", "dry latrine", "latrine",
    ))
    hazardous_cleaning = _has_any(q, (
        "cleaning", "cleaner", "safai", "manual scavenging",
        "manual scavenger", "forcing dalit women to clean", "forcing women to clean",
        "forcing me to clean", "forced me to clean", "clean dry latrine",
        "clean latrine", "clean sewer", "clean septic",
    ))
    harm = _has_any(q, (
        "dies", "died", "death", "dead", "no safety", "no equipment",
        "compensation", "refusing compensation",
    ))
    return (septic_or_sewer and (hazardous_cleaning or harm)) or _has_any(q, ("manual scavenging", "manual scavenger"))


def _is_custody_legal_aid_access_issue(q: str) -> bool:
    custody_context = _has_any(q, ("jail", "lockup", "custody", "arrest", "arrested", "detained", "prison"))
    lawyer_context = _has_any(q, (
        "lawyer meeting", "lawyer meet", "not allowing lawyer", "legal aid",
        "free lawyer", "court give free lawyer", "court appoint lawyer",
        "nalsa", "dlsa", "jail superintendent",
    ))
    return custody_context and lawyer_context


def _is_esi_benefit_issue(q: str) -> bool:
    esi_context = _has_any(q, ("esi", "esic", "employees state insurance", "employees' state insurance"))
    benefit_context = _has_any(q, (
        "hospital", "treat", "treatment", "delivery", "medical benefit",
        "refused", "claim rejected", "sickness benefit", "maternity benefit",
        "disablement benefit", "insured person",
    ))
    return esi_context and benefit_context


def _is_elder_financial_fraud_issue(q: str) -> bool:
    elder_context = (
        _has_any(q, ("senior", "elderly", "old", "grandfather", "grandmother"))
        or _has_age_at_least(q, 60)
        or re.search(r"\b(?:6[0-9]|7[0-9]|8[0-9]|9[0-9])\s*(?:year|years|yr|yrs)\s+(?:father|mother|parent)\b", q) is not None
        or (
            _has_any(q, ("father", "mother", "parent"))
            and _has_any(q, ("pension money", "retirement money", "ulip", "agent sold", "mis-selling", "misselling"))
        )
    )
    financial_abuse = _has_any(q, (
        "ulip", "policy", "agent sold", "lost", "jewellery", "safe keeping",
        "not returning", "charging deceased", "deactivate no response",
        "pension money", "mis-selling", "misselling", "fake call",
        "fraud call", "scam call", "pension office", "took 2 lakh",
        "took money", "debited", "transferred",
    ))
    return elder_context and financial_abuse


def _is_bank_or_pension_impersonation_fraud(q: str) -> bool:
    fraud_context = _has_any(q, (
        "fake call", "fraud call", "scam call", "impersonating",
        "pretending", "otp", "phishing", "took", "debited", "transferred",
        "lost money", "2 lakh",
    ))
    institution_context = _has_any(q, (
        "sbi", "bank", "pension office", "pension", "pf office",
        "epfo", "account", "atm", "upi",
    ))
    return fraud_context and institution_context


def _is_pmla_bail_issue(q: str) -> bool:
    return _has_pmla_ed_context(q) and _has_any(q, (
        "bail", "anticipatory", "interim", "new born", "newborn",
        "baby", "before arrest", "arrested",
    ))


def _has_pmla_ed_context(q: str) -> bool:
    if _has_any(q, _PMLA_ED_WORDS):
        return True
    ed_masked = re.sub(r"\bed\s+tech(?:nology)?\b|\bed-tech(?:nology)?\b", "edtech", q)
    return bool(re.search(r"(?<![-\w])ed(?![-\w])", ed_masked)) and _has_any(q, (
        "summons", "notice", "raid", "raided", "arrest", "attachment",
        "provisional attachment", "ecir", "pmla", "money laundering",
        "directorate",
    ))


def _is_accused_scst_issue(q: str) -> bool:
    scst_context = _has_any(q, ("sc st", "sc/st", "atrocity act", "atrocities act", "poa case", "poa act"))
    accused_context = _has_any(q, ("filed on me", "fir filed on me", "false case", "accused", "get bail", "how to get bail", "anticipatory bail"))
    return scst_context and accused_context


def _is_fir_copy_access_issue(q: str) -> bool:
    fir_copy = _has_any(q, (
        "fir copy", "copy of fir", "no fir copy", "fir ki copy",
        "fir ka copy",
    ))
    custody_or_family = _has_any(q, (
        "arrested", "arrest", "family", "brother", "husband", "son",
        "police", "secret", "not telling",
    ))
    return fir_copy and custody_or_family


def _is_ndps_default_bail_issue(q: str) -> bool:
    ndps_context = _has_any(q, (
        "ndps", "ganja", "charas", "mdma", "heroin",
        "commercial quantity", "commercial",
    ))
    no_chargesheet = _has_any(q, (
        "no chargesheet", "no charge sheet", "chargesheet not",
        "charge sheet not", "chargesheet filed nahi", "charge sheet filed nahi",
    ))
    custody_duration = bool(re.search(r"\b\d+\s*(?:days?|months?)\b", q)) or _has_any(q, (
        "custody", "jail", "arthur road", "remand",
    ))
    return ndps_context and no_chargesheet and custody_duration


def _is_ndps_bail_issue(q: str) -> bool:
    ndps_context = _has_any(q, (
        "ndps", "ganja", "charas", "mdma", "heroin", "cannabis",
        "weed", "hash", "narcotic", "narcotics", "commercial quantity",
    ))
    bail_or_custody_context = _has_any(q, (
        "bail", "default bail", "regular bail", "anticipatory bail",
        "session court", "sessions court", "special court", "rejected",
        "jail", "custody", "tihar", "arthur road", "puzhal",
        "long custody", "3 yrs", "3 years", "prolonged incarceration",
    ))
    return ndps_context and bail_or_custody_context


def _is_marital_sexual_violence_issue(q: str) -> bool:
    if _has_negated_sexual_coercion(q):
        return False
    marital_context = _has_any(q, ("husband", "wife", "married", "marriage", "sasural", "in laws", "in-laws"))
    sexual_coercion = _has_any(q, (
        "forces me at night", "force me at night", "forced me at night",
        "forces sex", "force sex", "forced sex", "marital rape",
        "sex when i say no", "when i say no", "even when i say no",
        "without consent", "unwell is there any law", "tired or unwell",
    ))
    return marital_context and sexual_coercion


def _has_negated_sexual_coercion(q: str) -> bool:
    return _has_any(q, (
        "does not force sex", "doesn't force sex", "not force sex",
        "never forces sex", "never forced sex", "no forced sex",
        "not forcing sex", "not forcing me for sex",
    ))


def _is_creator_cross_border_payout_issue(q: str) -> bool:
    creator_platform = _has_any(q, (
        "fanvue", "onlyfans", "patreon", "gumroad", "foreign platform",
        "creator account", "creator payout", "creator payment",
    ))
    payout_context = _has_any(q, (
        "payment frozen", "payout frozen", "payout held", "release fund",
        "release funds", "usd", "dollar", "foreign payment", "remittance",
        "withheld", "blocked payment", "frozen 2400",
    ))
    return creator_platform and payout_context


def _is_tweet_defamation_chargesheet_issue(q: str) -> bool:
    online_speech_context = _has_any(q, (
        "tweet", "twitter", "x.com", "online post", "social media post",
        "facebook post", "instagram post", "youtube comment",
    ))
    defamation_context = _has_any(q, (
        "defamation", "356", "cm corrupt", "corrupt", "calling cm", "called cm",
    ))
    court_stage = _has_any(q, (
        "chargesheet", "charge sheet", "summons", "notice", "court date", "police filed",
    ))
    return online_speech_context and defamation_context and court_stage


def _is_dpdp_data_breach_issue(q: str) -> bool:
    breach_context = _has_any(q, (
        "data breach", "personal data", "dpdp", "pan leaked", "aadhaar leaked",
        "aadhar leaked", "pan and aadhaar", "pan and aadhar", "data leaked",
    ))
    compensation_or_grievance = _has_any(q, (
        "compensation", "claim", "complain", "complaint", "grievance", "leaked",
        "misuse", "fraud",
    ))
    return breach_context and compensation_or_grievance


def _is_msme_payment_route_issue(q: str) -> bool:
    msme_context = _has_any(q, (
        "msme", "msmed", "udyam", "samadhan", "samadhaan", "msefc",
        "micro enterprise", "small enterprise",
    ))
    payment_context = _has_any(q, (
        "payment", "invoice", "not paid", "delay", "delayed", "outstanding",
        "43b", "43b(h)", "section 43b", "disallowance", "buyer",
    ))
    buyer_quality_withheld_context = (
        _has_any(q, ("buyer", "quality issue", "formal rejection", "rejection given", "goods"))
        and _has_any(q, ("payment", "deducting", "deducted", "not paid", "lakh stuck", "outstanding"))
    )
    return (msme_context and payment_context) or buyer_quality_withheld_context


def _is_agri_cooperative_recovery_issue(q: str) -> bool:
    loan_context = _has_any(q, ("crop loan", "agri loan", "agricultural loan", "farm loan", "loan default"))
    cooperative_context = _has_any(q, ("cooperative bank", "co-operative bank", "co op bank", "coop bank"))
    livestock_or_seizure = _has_any(q, (
        "buffalo", "cow", "cattle", "livestock", "tractor", "seized", "take livestock",
        "took livestock", "auction",
    ))
    return loan_context and (cooperative_context or livestock_or_seizure)


def _is_forest_false_charge_issue(q: str) -> bool:
    forest_context = _has_any(q, (
        "forest guard", "forest officer", "tendu", "minor forest produce",
        "mahua", "bamboo", "community forest",
    ))
    accused_context = _has_any(q, (
        "false case", "false dacoity", "dacoity case", "lodged on my brother",
        "case lodged", "accused", "arrested", "fir on",
    ))
    return forest_context and accused_context


def _is_fra_forest_rights_issue(q: str) -> bool:
    fra_context = _has_any(q, ("fra", "forest rights", "fra 2006", "fra claim", "ifr", "cfr", "community forest"))
    forest_official_context = _has_any(q, ("forest guard", "forest guards", "forest officer", "forest department", "reserved forest"))
    protected_produce_or_title = _has_any(q, (
        "patta", "title", "bamboo", "tendu", "mahua", "minor forest produce",
        "community forest rights", "gram sabha", "community forest", "cfr", "ifr",
    ))
    interference_context = _has_any(q, ("cutting", "stopped", "seized", "reserved", "denied", "refused"))
    return (fra_context and (protected_produce_or_title or interference_context)) or (
        forest_official_context and protected_produce_or_title and interference_context
    )


def _is_marriage_name_change_issue(q: str) -> bool:
    name_context = _has_any(q, ("change my surname", "change surname", "name change", "change my name"))
    marriage_context = _has_any(q, ("after marriage", "married", "marriage", "husband surname", "wife surname"))
    gazette_context = _has_any(q, ("gazette", "publish", "official gazette", "newspaper", "affidavit"))
    return name_context and (marriage_context or gazette_context)


def _is_spa_raid_subject_issue(q: str) -> bool:
    spa_context = _has_any(q, ("spa", "massage parlour", "massage parlor"))
    raid_context = _has_any(q, ("raid", "raided", "police took", "took me", "station", "itpa", "pita"))
    subject_context = _has_any(q, ("i just do massage", "i only do massage", "scared", "what will happen", "took me and other girls"))
    return spa_context and raid_context and subject_context


def _is_worksite_assault_injury_issue(q: str) -> bool:
    work_context = _has_any(q, (
        "site", "worksite", "mukadam", "thekedar", "contractor", "factory",
        "construction", "old wages", "wages",
    ))
    assault_context = _has_any(q, ("beat me", "beaten", "beating", "assault", "hit me", "head injury", "stitches"))
    injury_context = _has_any(q, ("injury", "head", "stitches", "medical", "hospital", "fracture", "blood"))
    return work_context and assault_context and injury_context


def _is_inlaw_jewellery_breach_issue(q: str) -> bool:
    inlaw_context = _has_any(q, ("daughter in law", "daughter-in-law", "son's wife", "bahu"))
    jewellery_context = _has_any(q, ("jewellery", "jewelry", "gold", "ornaments", "stridhan", "streedhan"))
    entrustment_context = _has_any(q, (
        "safe keeping", "safekeeping", "not returning", "refusing to return",
        "refuse to return", "kept",
    ))
    return inlaw_context and jewellery_context and entrustment_context


def _is_panchayat_common_land_issue(q: str) -> bool:
    local_body_context = _has_any(q, ("sarpanch", "panchayat", "gram sabha", "mukhiya"))
    common_land_context = _has_any(q, ("common village land", "common land", "village land", "panchayat land", "gairmazarua"))
    improper_process = _has_any(q, ("no panchayat meeting", "no meeting", "no resolution", "to his brother", "without meeting", "allotting"))
    return local_body_context and common_land_context and improper_process


def _is_pressure_property_transfer_issue(q: str) -> bool:
    property_context = _has_any(q, ("property", "house", "flat", "land", "gift deed", "signed property"))
    pressure_context = _has_any(q, ("under pressure", "coercion", "forced", "icu", "hospital", "medical", "not conscious"))
    challenge_context = _has_any(q, ("challenge", "cancel", "set aside", "revoke", "signed", "transfer"))
    return property_context and pressure_context and challenge_context


def _is_juvenile_age_custody_issue(q: str) -> bool:
    child_context = (
        _has_age_under(q, 18)
        or _has_any(q, ("juvenile", "minor", "child in conflict"))
        or re.search(r"\b(?:son|daughter|boy|girl|child)\s+(?:is\s+)?(?:[1-9]|1[0-7])\s*(?:year|years|yr|yrs)\b", q) is not None
    )
    custody_context = _has_any(q, ("adult jail", "adult lockup", "lockup", "jail", "prison", "observation home", "arrested", "detained", "custody"))
    age_proof_context = _has_any(q, ("age proof", "school certificate", "birth certificate", "verify age", "age determination", "pocso"))
    transfer_context = _has_any(q, ("adult jail", "adult lockup", "observation home", "transfer", "shift", "remove from jail", "remove from lockup"))
    return child_context and custody_context and (age_proof_context or transfer_context)


def _is_housing_society_pet_fine_issue(q: str) -> bool:
    housing_context = _has_any(q, (
        "society management", "housing society", "apartment association", "rwa",
        "cooperative society", "co-operative society",
    ))
    pet_context = re.search(r"\b(?:pet|pets|dog|dogs|cat|cats)\b", q) is not None
    fine_context = _has_any(q, ("fine", "penalty", "25000", "approval", "prior approval"))
    return housing_context and pet_context and fine_context


def _is_housing_society_parking_issue(q: str) -> bool:
    housing_context = _has_any(q, (
        "society management", "housing society", "apartment association", "rwa",
        "cooperative society", "co-operative society", "apartment",
        "flat association",
    ))
    parking_context = _has_any(q, (
        "parking", "parking slot", "dedicated parking", "allotted parking",
        "stilt parking", "car park", "blocked my parking", "blocking my parking",
    ))
    grievance_context = _has_any(q, (
        "security guard", "cant do anything", "can't do anything",
        "not helping", "complaint", "blocking", "blocked",
    ))
    return housing_context and parking_context and grievance_context


def _is_released_undertrial_police_torture_issue(q: str) -> bool:
    custody_context = _has_any(q, ("undertrial", "jail", "prison", "custody", "released"))
    torture_context = _has_any(q, ("police torture", "torture case", "custodial torture", "police beating", "beaten by police"))
    complaint_context = _has_any(q, ("file", "complaint", "case", "nhrc", "human rights", "help"))
    return custody_context and torture_context and complaint_context


def _is_child_support_enforcement_issue(q: str) -> bool:
    support_context = _has_any(q, (
        "child support", "child maintenance", "maintenance for child",
        "maintenance order",
    ))
    order_context = _has_any(q, (
        "court order", "as per order", "per month", "pending",
        "arrears", "not paying", "stopped paying",
    ))
    family_context = _has_any(q, (
        "ex husband", "ex wife", "husband", "wife", "children", "child",
    ))
    return family_context and support_context and order_context


def _is_property_transfer_document_issue(q: str) -> bool:
    property_context = _has_any(q, (
        "gift deed", "registered gift", "joint name", "house", "flat",
        "property transfer", "transfer in hospital", "thumb impression",
    ))
    dispute_context = _has_any(q, (
        "blank paper", "under pressure", "not caring", "cancel",
        "cancelled", "claims half", "half share", "didn't sign",
        "did not sign", "produced as", "challenge", "not taking care",
    ))
    return property_context and dispute_context


def _is_forced_adult_or_lgbt_marriage(q: str) -> bool:
    identity_context = _has_any(q, ("i am gay", "lesbian", "lgbt", "same sex", "queer"))
    forced_context = _has_any(q, ("forcing me to marry", "force me to marry", "parents are forcing", "girl next month", "boy next month"))
    adult_context = _has_age_at_least(q, 18) or _has_any(q, ("i am 26", "adult", "major"))
    return forced_context and (identity_context or adult_context)


def _has_age_under(q: str, limit: int) -> bool:
    patterns = (
        r"\b(?:age|aged|is|was)\s+([1-9]|1[0-7])\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s*old\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s+(?:daughter|son|girl|boy|child|minor)\b",
        r"\b([1-9]|1[0-7])\s*(?:yo|saal)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, q):
            try:
                if int(match.group(1)) < limit:
                    return True
            except ValueError:
                continue
    return False


def _has_age_at_least(q: str, floor: int) -> bool:
    patterns = (
        r"\b(?:age|aged|is|was)\s+(1[8-9]|[2-9][0-9])\b",
        r"\b(1[8-9]|[2-9][0-9])\s*(?:year|years|yr|yrs)\s*old\b",
        r"\b(1[8-9]|[2-9][0-9])\s*(?:year|years|yr|yrs)\s+(?:daughter|son|girl|boy|child)\b",
        r"\b(1[8-9]|[2-9][0-9])\s*(?:yo|saal)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, q):
            try:
                if int(match.group(1)) >= floor:
                    return True
            except ValueError:
                continue
    return False


def _is_child_marriage(q: str) -> bool:
    if _has_any(q, _CHILD_MARRIAGE_WORDS):
        return True
    forced_child_context = _has_any(q, ("child", "minor")) and _has_any(q, ("fixing marriage", "force marriage", "forcing marriage", "got him married", "got her married", "marry"))
    minor_context = _has_age_under(q, 18) or _has_any(q, ("minor", "under 18", "under eighteen")) or forced_child_context
    return minor_context and _has_any(q, _MARRIAGE_CONTEXT_WORDS)


def _is_arrest_production_delay(q: str) -> bool:
    if _has_any(q, ("notice", "summons", "appear")) and not _has_any(q, ("arrested", "detained", "custody", "lockup", "police picked", "utha liya")):
        return False
    arrest_context = _has_any(q, ("arrest", "arrested", "police picked", "custody", "lockup", "detained", "utha liya"))
    production_context = _has_any(q, (
        "magistrate ke samne", "magistrate ke saamne", "produce before magistrate",
        "produced before magistrate", "not produced", "24 hours",
        "twenty four hours", "kab le jana", "court ke samne",
    ))
    prolonged_context = _has_any(q, ("5 din", "five days", "5 days")) and _has_any(q, ("magistrate", "custody", "lockup", "detained", "police station"))
    return arrest_context and (production_context or prolonged_context)


def _is_arrest_information_safeguard(q: str) -> bool:
    arrest_context = _has_any(q, (
        "arrest", "arrested", "detained", "custody", "lockup",
        "police took", "police picked", "utha liya",
    ))
    information_context = _has_any(q, (
        "arrest memo", "no arrest memo", "dk basu", "d.k. basu",
        "grounds of arrest", "not informed", "family not informed",
        "no fir copy", "secret", "where taken",
    ))
    return arrest_context and information_context


def _is_custody_restraint_issue(q: str) -> bool:
    restraint_context = _has_any(q, ("handcuff", "handcuffs", "hand cuff", "hand cuffs", "chained", "shackled"))
    custody_or_court_context = _has_any(q, (
        "court", "taken to court", "produced", "magistrate", "police",
        "custody", "prisoner", "jail", "lockup", "undertrial", "high security",
    ))
    return restraint_context and custody_or_court_context


def _is_bonded_labour_rescue(q: str) -> bool:
    if _has_any(q, ("bonded labour", "bonded labor", "release certificate")):
        return True
    work_context = _has_any(q, (
        "contractor", "thekedar", "brick kiln", "bhatta", "kiln owner",
        "owner", "work", "worker", "labour", "labor", "site", "factory",
    ))
    strong_coercion_context = _has_any(q, (
        "hostage", "cannot go home", "cannot leave site", "cannot leave worksite",
        "cannot leave factory", "not letting leave", "not letting us leave",
        "not letting me leave",
        "keeping family", "locked", "cards passport", "keeping our cards",
        "documents retained", "aadhaar original", "passport", "loan finish",
        "debt bondage",
    ))
    debt_control_context = _has_any(q, ("advance", "debt")) and _has_any(q, ("must work", "cannot go home", "not letting", "hostage", "loan finish", "till loan"))
    return work_context and (strong_coercion_context or debt_control_context)


def _is_disability_access(q: str) -> bool:
    if _is_survivor_sexual_offence(q):
        return False
    if _has_any(q, _DISABILITY_ACCESS_WORDS):
        return True
    disability_context = _has_any(q, ("disabled", "disability", "divyang", "handicapped"))
    certificate_context = _has_any(q, ("certificate", "udid", "medical board", "officer", "application", "pending", "refused", "denied"))
    return disability_context and certificate_context


def _is_family_support_issue(q: str) -> bool:
    family_context = _has_any(q, ("husband", "wife", "children", "child", "small children"))
    if not family_context:
        return False
    if _has_any(q, _FAMILY_SUPPORT_WORDS):
        return True
    support_context = _has_any(q, ("left me", "deserted", "no money", "maintenance", "not paying", "school fees"))
    return family_context and support_context


def _is_child_family_issue(q: str) -> bool:
    if _has_any(q, _CHILD_FAMILY_WORDS):
        return True
    child_context = _has_any(q, (
        "child", "son", "daughter", "minor", "5 year old", "five year old",
        "kid", "baby", "girl child", "boy child",
    )) or _has_age_under(q, 18)
    custody_context = _has_any(q, (
        "custody", "custody order", "took our", "taken our", "took my",
        "parents in law took", "in laws took", "took her away", "took him away",
        "not letting me meet", "not letting us meet", "blocked calls",
        "meet her", "meet him", "get her back", "get him back",
        "return child", "bring back", "not bringing back",
        "refuse to return", "refuses to return", "custody petition",
    ))
    family_context = _has_any(q, (
        "husband", "wife", "ex husband", "ex wife", "ex partner",
        "father", "mother", "parents in law", "in laws", "family court",
    ))
    return child_context and custody_context and family_context


def _is_supervised_visitation_issue(q: str) -> bool:
    return _has_any(q, (
        "supervised visitation", "unsupervised visitation", "visitation order",
        "supervised visit", "unsupervised visit",
    ))


def _is_witch_branding_violence(q: str) -> bool:
    if _is_witch_branding_accused_issue(q):
        return False
    if _has_any(q, ("daayan", "dayan", "tonhi", "daini", "labelled daayan", "branded witch", "witch-branding")):
        return True
    social_context = _has_any(q, ("village", "mob", "people", "saas", "mother", "woman", "assam", "jharkhand", "chhattisgarh", "bihar"))
    violence_context = _has_any(q, ("beaten", "beat", "attack", "attacked", "assault", "hair cut", "paraded", "throw me out"))
    branding_context = _has_any(q, ("branded", "labelled", "called", "calling"))
    return "witch" in q and ((branding_context and social_context) or violence_context)


def _is_witch_branding_accused_issue(q: str) -> bool:
    witch_context = _has_any(q, ("daayan", "dayan", "tonhi", "daini", "witch"))
    accused_context = _has_any(q, (
        "false case", "case filed", "filed on me", "against me",
        "accused", "i am accused", "they say i am", "police called me",
        "notice to me", "arrested me",
    ))
    return witch_context and accused_context


def _is_voter_rights_issue(q: str) -> bool:
    voter_context = _has_any(q, ("voter", "electoral roll", "booth officer", "epic", "election id", "polling booth", "denied vote", "denied me vote"))
    correction_or_denial = _has_any(q, ("name spelt wrong", "name spelled wrong", "correction", "denied", "vote", "roll", "booth"))
    return voter_context and correction_or_denial


def _is_election_candidate_issue(q: str) -> bool:
    private_election_context = _has_any(q, (
        "housing society", "apartment association", "rwa", "college election",
        "club election", "cooperative", "co-operative", "company election",
        "company board", "shareholder", "trade union", "student union",
        "private election", "municipal election", "panchayat election",
        "local body election", "club", "society",
    ))
    election_procedure_context = _has_any(q, (
        "election", "nomination", "returning officer", "candidate",
        "recount", "counting", "symbol",
    ))
    if private_election_context and election_procedure_context:
        return False
    if _has_any(q, _ELECTION_CANDIDATE_WORDS):
        return True
    public_election_context = _has_any(q, (
        "candidate", "nomination", "returning officer", "election commission",
        "eci", "mla", "mp", "lok sabha", "rajya sabha", "vidhan sabha",
        "assembly election", "parliament election", "general election",
    ))
    legal_election_issue = _has_any(q, (
        "disqualified", "disqualification", "convicted", "conviction",
        "rejected", "scrutiny", "affidavit", "assets", "expenses",
        "petition", "corrupt practice", "bribe", "vote recount",
        "election recount", "recounting of votes", "counting",
        "symbol", "set aside",
    ))
    return public_election_context and legal_election_issue


def _is_tribal_caste_issue(q: str) -> bool:
    administrative_or_service_context = _has_any(q, (
        "employee transfer order", "training workshop", "workshop cancelled",
        "cancelled want refund", "campus project", "college project",
        "office transfer", "service refund",
    ))
    rights_or_harm_context = _has_any(q, (
        "atrocity", "caste", "caste slur", "untouchable", "discrimination",
        "not allowed", "beat", "beaten", "violence", "threat", "boycott",
        "forest rights", "gram sabha", "pesa", "land sold", "land transfer",
        "land grabbed", "restoration", "st certificate", "tribal certificate",
        "scheduled tribe certificate",
    ))
    if administrative_or_service_context and not rights_or_harm_context:
        return False
    if _is_fra_forest_rights_issue(q):
        return True
    if _has_any(q, _TRIBAL_CASTE_WORDS):
        return True
    if _has_any(q, ("caste", "upper caste", "dominant caste")) and _has_any(q, (
        "temple", "enter", "entry", "water", "well", "shop", "hotel",
        "boycott", "discrimination", "not allowed",
    )):
        return True
    return _has_any(q, ("upper caste", "dominant caste")) and _has_any(q, ("beat", "beaten", "called", "slur", "untouchable", "violence", "threat", "boycott"))


def _is_untouchability_civil_rights_issue(q: str) -> bool:
    caste_context = _has_any(q, (
        "dalit", "scheduled caste", "sc/st", "sc st", "caste",
        "untouchability", "untouchable", "cannot touch", "can't touch",
    ))
    access_context = _has_any(q, (
        "temple", "enter temple", "temple entry", "well", "water",
        "dirty water", "public place", "shop", "hotel", "not allowed",
    ))
    return caste_context and access_context


def _is_tribal_land_transfer_issue(q: str) -> bool:
    tribal_context = _has_any(q, (
        "tribal", "adivasi", "scheduled tribe", "munda", "santhal",
        "oraon", "khuntkatti", "non tribal", "non-tribal",
        "cnt", "chotanagpur", "chota nagpur", "santhal parganas",
    ))
    land_noun_context = bool(re.search(
        r"\b(?:land|plot|raiyat|tenancy|khata|khasra)\b",
        q,
    )) or _has_any(q, ("cnt", "chotanagpur", "chota nagpur", "santhal parganas"))
    transfer_context = _has_any(q, (
        "sold", "sale deed", "land transfer", "land transferred",
        "plot transfer", "registered deed", "without our consent",
        "restore", "restoration", "grabbed", "land grab",
        "land restoration", "mortgage", "mortgaged", "sahukar",
        "moneylender", "refusing return", "refusing to return",
        "not returning land", "took my land",
    )) or bool(re.search(
        r"\btransfer(?:red)?\s+of\s+(?:tribal\s+)?(?:land|plot)\b",
        q,
    ))
    return tribal_context and land_noun_context and transfer_context


def _is_cheque_bounce_issue(q: str) -> bool:
    if _has_any(q, ("notice under 138", "section 138", "ni act 138")):
        return True
    cheque_context = _has_any(q, ("cheque", "cheques", "post dated", "post-dated", "security cheque"))
    misuse_context = _has_any(q, (
        "misusing", "misuse", "deposited", "presented", "bank return",
        "return memo", "legal notice", "notice under 138", "dishonour",
        "dishonored", "insufficient funds", "bounced", "stop payment",
        "payment stopped", "cheque return", "cheque returned",
    ))
    return cheque_context and misuse_context


def _is_security_cheque_defence_issue(q: str) -> bool:
    cheque_context = _has_any(q, ("cheque", "cheques", "post dated", "post-dated", "security cheque"))
    security_context = _has_any(q, ("security", "landlord", "rent", "tenant", "builder", "loan security", "blank cheque"))
    drawer_context = _has_any(q, (
        "i issued", "we issued", "i gave", "we gave", "taken from me",
        "took from me", "my cheque", "our cheque",
    ))
    misuse_context = _has_any(q, ("misusing", "misuse", "presented", "deposited", "threatening 138", "notice under 138"))
    return cheque_context and security_context and (drawer_context or misuse_context)


def _is_elder_maintenance_cheque_issue(q: str) -> bool:
    cheque_context = _has_any(q, ("cheque", "cheques", "bounced", "dishonour", "dishonored"))
    family_context = _has_any(q, ("son", "daughter", "children", "monthly maintenance", "maintenance"))
    parent_context = _has_any(q, ("mother", "father", "parent", "parents", "me"))
    return cheque_context and family_context and parent_context and _has_any(q, ("maintenance", "feeding", "support"))


def _is_family_marriage_status_issue(q: str) -> bool:
    if _is_succession_issue(q):
        return False
    if _has_any(q, ("triple talaq", "talaq-e-biddat", "instant talaq", "talaq on whatsapp")):
        return _has_any(q, ("husband", "wife", "muslim", "marriage", "nikah", "whatsapp", "remedy"))
    if _has_any(q, ("legal age", "age legal", "marriage age", "got married")) and _has_any(q, ("married", "marriage", "family says illegal")):
        return True
    return _has_any(q, _FAMILY_MARRIAGE_STATUS_WORDS) and _has_any(q, ("husband", "wife", "marriage", "divorce", "land", "share", "protection", "muslim", "hindu"))


def _is_succession_issue(q: str) -> bool:
    if _has_any(q, ("inheritance", "succession", "father died", "mother died", "will", "share from", "property share", "muslim inheritance", "coparcener")):
        return True
    if _has_any(q, ("inherit", "heir", "heirs", "sunni law", "hanafi")) and _has_any(q, ("muslim", "widow", "wife", "daughter", "father")):
        return True
    if _has_any(q, ("widow", "husband")) and _has_any(q, ("stepchildren", "step children", "children", "heirs")) and _has_any(q, ("property", "flat", "house", "land", "share")):
        return True
    personal_law_context = _has_any(q, ("parsi", "christian", "muslim", "widow", "sisters", "brothers", "children", "heirs"))
    death_context = _has_any(q, ("passed away", "died", "death", "dead"))
    property_context = _has_any(q, ("property", "flat", "house", "land", "share", "divided", "partition"))
    return death_context and property_context and personal_law_context


def _is_caste_certificate_appeal(q: str) -> bool:
    certificate_context = _has_any(q, (
        "caste certificate", "sc certificate", "st certificate",
        "scheduled caste certificate", "scheduled tribe certificate",
        "community certificate",
    ))
    hard_rejection_context = _has_any(q, (
        "rejected", "reject", "refused", "denied", "appeal",
        "rejection order", "refusal order",
    ))
    issuing_authority_context = _has_any(q, (
        "tehsildar", "tahsildar", "talathi", "revenue officer",
        "sdm", "sub divisional magistrate", "district magistrate",
        "dm office", "collector", "competent authority",
        "certificate authority", "caste scrutiny committee",
    ))
    non_issue_context = _has_any(q, ("not giving", "not issuing", "not making"))
    school_or_scholarship_context = _has_any(q, ("school", "college", "scholarship", "form"))
    if school_or_scholarship_context and non_issue_context and not issuing_authority_context:
        return False
    return certificate_context and (
        hard_rejection_context
        or issuing_authority_context
        or (non_issue_context and issuing_authority_context)
    )


def _is_gig_platform_termination_issue(q: str) -> bool:
    platform_context = _has_any(q, (
        "urban company", "housejoy", "zomato", "swiggy", "ola", "uber",
        "blinkit", "zepto", "rapido", "dunzo", "gig worker",
        "platform worker", "delivery partner", "driver partner",
        "beautician", "service partner",
    ))
    adverse_action = _has_any(q, (
        "termination", "terminated", "fired", "deactivated", "suspended",
        "id blocked", "profile blocked", "3 strike", "three strike",
        "strike system", "unfair", "bad rating", "low rating",
    ))
    labour_frame = _has_any(q, (
        "labour law", "labor law", "employment", "worker", "wages",
        "payout", "earning", "full and final", "dues",
    ))
    explicit_status_challenge = _has_any(q, (
        "labour law", "labor law", "employment law", "wrongful termination",
        "unfair termination", "industrial dispute", "employee status",
        "workman status",
    ))
    service_partner_context = _has_any(q, (
        "urban company", "housejoy", "beautician", "service partner",
        "salon partner", "home service",
    ))
    return platform_context and adverse_action and labour_frame and (
        explicit_status_challenge or service_partner_context
    )


def _is_street_vendor_municipal(q: str) -> bool:
    if _has_any(q, ("software", "saas", "client", "vendor agreement", "license dispute")):
        return False
    if _has_any(q, (
        "municipal seized", "street vendor", "vending license",
        "vending licence", "market vendor", "fish market vendor",
        "thela", "rehri", "vendor zone",
    )):
        return True
    physical_vendor_context = _has_any(q, ("cart", "hawker", "fish market", "vegetable", "market", "stall", "footpath", "roadside", "vendor zone"))
    enforcement_context = _has_any(q, ("municipal", "panchayat", "fine", "license", "licence", "seized", "ward office", "inspector", "remove", "allotted", "pay 2000", "bribe"))
    return _has_any(q, ("vendor", "hawker")) and physical_vendor_context and enforcement_context


def _is_cyber_issue(q: str) -> bool:
    if _is_family_marriage_status_issue(q) or _is_workplace_sexual_harassment(q):
        return False
    if _is_benign_crypto_or_creator_discussion(q):
        return False
    if _has_any(q, ("telegram", "crypto", "investment group")) and _has_any(q, (
        "rugpull", "rugpulled", "scam", "fraud", "lost", "took",
        "3 lakh", "2 lakh",
        "otp", "seed phrase", "connect wallet", "wallet drained",
        "drained account", "admin vanished", "stole my crypto",
    )):
        return True
    if _has_any(q, _CYBER_WORDS):
        return True
    if not _has_any(q, _INTIMATE_IMAGE_WORDS):
        return False
    if _has_any(q, _IMAGE_ABUSE_CONTEXT_WORDS):
        return True
    if _has_any(q, _INTIMATE_IMAGE_SERVICE_WORDS):
        return False
    return _has_any(q, _INTIMATE_IMAGE_RISK_WORDS)


def _is_benign_crypto_or_creator_discussion(q: str) -> bool:
    benign_context = _has_any(q, (
        "not scam", "no scam", "tax discussion", "income tax",
        "crypto tax", "creator promotion", "promotion income tax",
        "tax on payouts",
    ))
    hard_harm_context = _has_any(q, (
        "rugpull", "rugpulled", "fraud", "scammed", "lost money",
        "lost 3 lakh", "took 3 lakh", "took 2 lakh", "leaked",
        "without permission", "blackmail", "threat", "took my money",
        "took money", "then took", "otp",
        "asked for otp", "seed phrase", "connect wallet", "wallet drained",
        "drained account", "drained my account", "admin vanished",
        "vanished with money", "transferred my crypto", "stole my crypto",
    ))
    return benign_context and not hard_harm_context


def _is_digital_platform_issue(q: str) -> bool:
    tax_context = _has_any(q, _TAX_GST_WORDS) or _has_any(q, _CUSTOMS_TAX_WORDS) or _has_any(q, _INCOME_TAX_APPEAL_WORDS) or _has_any(q, ("tax on winnings", "winnings"))
    platform_dispute_context = _has_any(q, (
        "lost", "recover", "refund", "account", "deactivated", "suspended",
        "frozen", "froze", "kyc", "blocked", "support", "grievance",
        "wallet", "money stuck",
    ))
    if tax_context and not platform_dispute_context:
        return False
    platform_context = _has_any(q, (
        "uber", "ola", "zomato", "swiggy", "instagram", "facebook", "meta",
        "online gaming", "gaming app", "game", "platform", "page suspended",
        "rider", "driver",
    ))
    platform_action = _has_any(q, ("deactivated", "suspended", "account froze", "account frozen", "kyc pending"))
    if not (_has_any(q, _DIGITAL_PLATFORM_WORDS) or (platform_context and platform_action)):
        return False
    financial_kyc_context = _has_any(q, (
        "bank", "nbfc", "rbi", "sbi", "hdfc", "icici", "axis",
        "savings account", "current account", "bank account", "loan account",
    )) and _has_any(q, ("kyc", "account froze", "account frozen", "account freeze", "frozen"))
    return not (financial_kyc_context and not platform_context)


def _is_cab_aggregator_driver_issue(q: str) -> bool:
    aggregator_context = _has_any(q, ("uber", "ola", "cab aggregator", "taxi aggregator", "ride hailing", "ride-hailing"))
    passenger_negation = _has_any(q, (
        "not driver", "not a driver", "not an uber driver", "not ola driver",
        "i am customer", "i'm customer", "i am a customer", "i'm a customer",
        "customer account", "my customer account", "as customer", "as a customer",
        "as passenger", "as a passenger", "i was passenger", "i was a passenger",
        "i am passenger", "i am a passenger",
    ))
    if passenger_negation:
        return False
    driver_context = _has_any(q, (
        "cab driver", "taxi driver", "uber driver", "ola driver", "driver id",
        "my driver id", "driver account", "driver profile", "driver partner",
        "platform partner", "partner", "vehicle integrated",
    ))
    platform_action = _has_any(q, (
        "deactivated", "suspended", "id blocked", "driver id blocked",
        "profile blocked", "rating low", "low rating", "off-boarded",
        "offboarded", "off boarded",
    ))
    return aggregator_context and driver_context and platform_action


def _cyber_required_sources(q: str) -> list[str]:
    sources = ["Information Technology Act 2000", "BNS/BNSS or IPC/CrPC based on incident date"]
    if _is_child_intimate_image(q):
        sources.append("POCSO Act 2012 where the intimate image or sexual content involves a child")
    return sources


def _is_child_intimate_image(q: str) -> bool:
    child_age = _has_age_under(q, 18)
    if not child_age and _has_age_at_least(q, 18):
        return False
    child_context = child_age or _has_any(q, ("minor", "child", "under 18", "under eighteen"))
    return child_context and _has_any(q, _INTIMATE_IMAGE_WORDS)


def _is_intimate_image_emergency(q: str) -> bool:
    return _has_any(q, _INTIMATE_IMAGE_WORDS) and (
        _has_any(q, _IMAGE_ABUSE_CONTEXT_WORDS)
        or (
            _has_any(q, _INTIMATE_IMAGE_RISK_WORDS)
            and not _has_any(q, _INTIMATE_IMAGE_SERVICE_WORDS)
        )
    )


def _is_family_safety_issue(q: str) -> bool:
    if _has_negated_sexual_coercion(q) and not _has_any(q, (
        "beat", "beating", "threat", "locked", "unsafe", "dowry",
        "grabbed", "touching", "touched",
    )):
        return False
    has_family_context = _has_any(q, (
        "domestic violence", "husband", "wife", "in laws", "mother in law",
        "father in law", "dowry", "marriage", "married", "live in partner",
        "live-in partner", "domestic relationship", "husband's brother",
        "husbands brother", "brother in law", "brother-in-law", "in-laws",
    ))
    has_immediate_safety = _has_any(q, (
        "husband beat", "husband is beating", "beating me", "beats me",
        "slaps me", "slapped me", "hit me", "hitting me", "locked", "threat", "threatens",
        "threatened", "threatening", "kill", "no food", "not giving food",
        "threw me out", "unsafe", "grabbed my hand", "grabbed me",
        "touching me", "touched me", "making me uncomfortable", "uncomfortable",
        "forces sex", "force sex", "forced sex", "marital rape",
        "even when i say no", "sex when i say no",
    ))
    return has_family_context and has_immediate_safety


def _is_work_injury(q: str) -> bool:
    wage_only_context = _has_any(q, (
        "wage", "wages", "salary", "not paid", "unpaid", "ran away with",
        "overtime", "14 hour", "14 hours", "minimum wage",
    )) and not _has_any(q, (
        "injury", "injured", "accident", "fell", "fall", "broken", "fracture",
        "death", "insurance", "medical", "hospital", "silicosis",
        "lost hand", "lost arm", "amputation", "hand cut", "hand crushed",
    ))
    if wage_only_context:
        return False
    negated_injury = _has_any(q, ("no accident", "without accident", "not an accident", "no injury", "not injured", "without injury"))
    missing_accident_record = _has_any(q, (
        "no accident report", "no accident record", "no accident register",
        "no accident intimation", "no accident form",
    ))
    if negated_injury and not missing_accident_record:
        return False
    if _has_any(q, _WORK_INJURY_WORDS):
        return True
    injury_context = _has_any(q, (
        "injury", "injured", "accident", "fell", "fall", "broken",
        "fracture", "death", "compensation", "insurance", "lost hand",
        "lost arm", "amputation", "hand cut", "hand crushed",
    ))
    gig_context = _has_any(q, (
        "zomato rider", "swiggy rider", "delivery rider", "gig worker",
        "platform worker", "ola driver", "uber driver", "cab driver",
        "delivery partner", "zomato delivery partner", "swiggy delivery partner",
    ))
    if gig_context and injury_context:
        return True
    work_context = _has_any(q, ("construction", "site", "factory", "mine", "contractor", "thekedar", "labour", "worker", "brick kiln", "bhatta", "kiln owner"))
    return work_context and injury_context


def _is_contract_labour_wage_issue(q: str) -> bool:
    wage_context = _has_any(q, (
        "wage", "wages", "salary", "not paid", "unpaid",
        "dues", "wage dues", "salary dues", "4 months wages",
        "months wages", "payment of wages",
    ))
    if not wage_context:
        return False
    if _has_any(q, ("principal employer", "contract labour", "contract labor", "workmen")):
        return True
    worker_context = _has_any(q, (
        "worker", "workers", "workmen", "labour", "labor", "mazdoor",
        "site worker", "construction worker", "factory worker",
        "22 workers", "10 workers", "migrant worker",
    ))
    return _has_any(q, ("contractor", "thekedar")) and worker_context and _has_any(q, (
        "site", "worksite", "factory", "construction", "plant",
        "company", "labour", "labor", "mazdoor",
    ))


def _is_survivor_sexual_offence(q: str) -> bool:
    survivor_bail_context = (
        _has_any(q, ("oppose bail", "oppose anticipatory bail", "cancel bail", "bail of accused", "accused bail"))
        and _has_any(q, ("survivor", "victim", "complainant", "my sister", "my daughter", "my wife", "rape survivor"))
    )
    if survivor_bail_context:
        return True
    accused_context = _has_any(q, ("false rape", "rape case against me", "accused of rape", "bail in rape"))
    accused_context = accused_context or (
        _has_any(q, ("anticipatory bail", "regular bail"))
        and _has_any(q, ("against me", "i am accused", "accused of", "my bail", "defend"))
    )
    if accused_context:
        return False
    if _has_any(q, _SEXUAL_OFFENCE_SURVIVOR_WORDS):
        return True
    if _has_any(q, ("minor", "child", "daughter")) and _has_any(q, ("touch", "touched", "molest", "pocso")):
        return True
    historic_child_context = (
        _has_any(q, ("since i was", "when i was", "as a child", "childhood"))
        and _has_age_under(q, 18)
        and _has_any(q, ("touch", "touched", "touching", "rape", "molest", "sexual"))
    )
    if historic_child_context:
        return True
    survivor_context = _has_any(q, ("my sister", "my daughter", "my wife", "my girlfriend", "girlfriend", "me", "victim", "survivor"))
    sexual_context = _has_any(q, ("rape", "molest", "sexual assault", "pocso"))
    return survivor_context and sexual_context


def _is_workplace_sexual_harassment(q: str) -> bool:
    if _has_any(q, _WORKPLACE_SEXUAL_HARASSMENT_WORDS):
        return True
    retaliation_context = _has_any(q, ("retaliation", "reporting manager", "bad rating", "pip")) and _has_any(q, (
        "posh", "sexual harassment", "icc", "internal committee", "local committee",
        "harassment complaint", "complained to icc", "complained to internal committee",
    ))
    if retaliation_context:
        return True
    workplace_context = _has_any(q, ("boss", "manager", "colleague", "coworker", "office", "workplace", "hr")) or (
        _has_any(q, ("vendor",)) and _has_any(q, ("office", "workplace", "my office", "at office"))
    )
    romantic_date_context = _has_any(q, ("asks for date", "asking for date", "asked for date")) and _has_any(q, (
        "told him no", "told her no", "i told", "keeps", "uncomfortable",
    ))
    emoji_context = _has_any(q, ("whatsapp emojis", "emojis")) and _has_any(q, (
        "asks for date", "asking for date", "keeps messaging", "keeps sending",
        "told him no", "uncomfortable",
    ))
    harassment_context = _has_any(q, (
        "touch", "touched", "harass", "stalking", "sexual", "alone",
        "late night",
    )) or romantic_date_context or emoji_context
    return workplace_context and harassment_context


def _is_civil_registration_record_issue(q: str) -> bool:
    registration_context = _has_any(q, (
        "birth certificate", "birth registration", "death certificate",
        "death registration", "born at home", "home birth",
    ))
    authority_context = _has_any(q, (
        "panchayat", "municipal", "registrar", "secretary", "not giving",
        "refused", "pending", "delayed", "certificate",
    ))
    return registration_context and authority_context


def _is_digital_device_police_seizure(q: str) -> bool:
    if _has_any(q, ("case closed", "after case closed", "not released", "return my phone", "release my phone")):
        return False
    device_context = _has_any(q, (
        "laptop", "phone", "mobile", "computer", "hard disk", "pendrive",
        "pen drive", "device", "server", "company laptop", "electronic record",
    ))
    police_context = _has_any(q, ("police", "investigation", "investigating officer", "io", "fir", "case"))
    seizure_context = _has_any(q, ("seized", "seizure", "taken", "took", "confiscated", "kept"))
    return device_context and police_context and seizure_context


def _is_reproductive_rights(q: str) -> bool:
    if _has_any(q, _REPRODUCTIVE_RIGHTS_WORDS):
        return True
    pregnancy_context = _has_any(q, ("pregnant", "pregnancy"))
    termination_context = _has_any(q, ("abortion", "terminate", "termination", "doctor says too late"))
    return pregnancy_context and termination_context


def _is_surrogacy_issue(q: str) -> bool:
    if _has_any(q, (
        "not surrogacy", "not surrogate", "no surrogacy", "no surrogate",
        "without surrogacy", "without surrogate", "no surrogate arrangement",
    )):
        return False
    return _has_any(q, _SURROGACY_WORDS) and _has_any(q, (
        "baby", "wife", "husband", "couple", "clinic", "allowed",
        "eligible", "certificate", "hysterectomy", "infertility",
        "single woman", "single mother", "can use", "unmarried",
        "live in", "partner", "widow", "divorcee", "commercial",
        "altruistic", "agent", "compensation", "insurance",
        "surrogate mother", "extra money", "delivery", "agreement",
        "took money",
    ))


def _is_senior_citizen_issue(q: str) -> bool:
    senior_welfare_context = _has_any(q, (
        "old age pension", "vridha pension", "pension status",
        "pension not", "pension stopped", "aadhaar", "ration",
        "scheme", "beneficiary", "widow pension",
    ))
    family_or_maintenance_context = _has_any(q, (
        "son", "daughter", "daughter in law", "daughter-in-law",
        "children", "brother", "grandson", "family", "maintenance",
        "not taking care", "stopped giving", "food", "medical",
        "threw", "evict", "homeless", "not allowed", "locked",
        "own house", "own kitchen", "gift", "gifted", "transfer",
        "property", "flat", "house", "land", "gold",
    ))
    if senior_welfare_context and not family_or_maintenance_context:
        return False
    if _has_any(q, ("son threw", "daughter threw", "children not taking care")):
        return True
    if _has_any(q, ("senior citizen", "old age")) and family_or_maintenance_context:
        return True
    parent_transfer = (
        _has_any(q, ("father", "mother", "parent", "parents", "grandfather", "grandmother"))
        and _has_any(q, ("gift", "gifted", "transfer", "transferred", "settlement deed", "gold", "property", "flat", "house", "land"))
        and _has_any(q, (
            "food", "basic amenities", "maintenance", "not taking care",
            "not caring", "does not care", "doesn't care", "refuses to care",
            "stopped giving", "medical bill", "medical bills", "medical",
            "hospital", "cant pay", "can't pay", "cannot pay", "wants back",
            "take back", "cancel", "cancelled", "cancellation",
            "throw me out", "throw him out", "throw her out", "evict",
        ))
    )
    if parent_transfer:
        return True
    first_person_child_transfer = (
        _has_any(q, ("my house", "my flat", "my land", "my property", "i gave", "i gifted"))
        and _has_any(q, ("son", "daughter", "children"))
        and _has_any(q, ("gift", "gifted", "gift deed", "transfer", "transferred", "settlement deed"))
        and _has_any(q, (
            "throw me out", "threw me out", "evict", "eviction",
            "not taking care", "not caring", "maintenance", "cancel",
            "cancelled", "cancellation", "take back",
        ))
    )
    if first_person_child_transfer:
        return True
    parent_maintenance = (
        _has_any(q, ("father", "mother", "parent", "parents"))
        and _has_any(q, ("son", "daughter", "children"))
        and _has_any(q, (
            "refuses to pay maintenance", "refuse to pay maintenance",
            "not paying maintenance", "maintenance tribunal",
            "how much can tribunal order", "maximum maintenance",
        ))
    )
    if parent_maintenance:
        return True
    senior_age = re.search(r"\b(6[0-9]|7[0-9]|8[0-9]|9[0-9])\b", q) is not None
    neglect_or_shelter = _has_any(q, (
        "threw", "evict", "homeless", "not giving food", "not taking care",
        "maintenance tribunal", "senior citizen tribunal", "gift deed",
        "widow threw", "house threw", "not allowed", "locked",
        "own house", "own kitchen", "daughter in law", "daughter-in-law",
    ))
    return senior_age and neglect_or_shelter


def _is_civil_procedure_issue(q: str) -> bool:
    if _has_any(q, ("rti", "right to information", "pio", "public information officer", "information commission")):
        return False
    if _has_any(q, ("consumer", "e-daakhil", "edaakhil", "district consumer", "consumer complaint")):
        return False
    if _has_any(q, _CIVIL_PROCEDURE_WORDS):
        return True
    civil_forum = _has_any(q, ("cpc", "civil court", "district court", "high court"))
    procedural_step = _has_any(q, ("execution", "decree", "appeal", "petition", "revision", "transfer"))
    if civil_forum and procedural_step:
        return True
    return _has_any(q, ("decree holder", "substantial question")) and _has_any(q, ("file", "procedure", "appeal", "execution"))


def _red_flags(q: str) -> list[str]:
    flags: list[str] = []
    if _has_any(q, (
        "rape", "child", "minor", "molest", "pocso", "acid", "knife",
        "kill", "suicide", "mob", "violence", "beat", "beaten", "witch", "daayan",
        "dayan", "hostage",
    )):
        flags.append("Immediate safety risk or serious offence")
    if _has_any(q, ("arrested", "arrest", "detained", "in jail", "custody", "bail", "magistrate")):
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


def _online_gambling_pack() -> ActionPack:
    return ActionPack(
        id="online_gambling_dispute",
        title="Online gaming legality path",
        next_steps=[
            "Preserve the app terms, location/state, screenshots, game history, and transaction IDs.",
            "Separate ordinary gambling loss from fraud, cheating, unauthorized debit, or misleading-platform facts.",
            "Raise a platform grievance and use the state online-gaming authority or cyber/police channel only on the facts that fit.",
        ],
        documents=["app/account ID", "KYC details", "transaction IDs", "screenshots", "terms/promotional messages", "platform tickets"],
        portals=["platform grievance portal", "cybercrime.gov.in where fraud or unauthorized transaction is alleged"],
        escalation=["state online-gaming authority where available", "cyber/police channel for fraud", "District Legal Services Authority"],
        cautions=["Online gambling and real-money game rules are state-sensitive; do not treat gambling losses as an automatic consumer recovery claim."],
    )


def _caste_certificate_pack() -> ActionPack:
    return ActionPack(
        id="caste_certificate_appeal",
        title="Caste certificate appeal path",
        next_steps=[
            "Collect the rejection order, application receipt, caste/community records, school records, and family certificates.",
            "Check the state rule or the rejection order for the appellate authority and deadline.",
            "If the order gives no reasons, ask the office in writing or by RTI for the rule and documents relied on.",
        ],
        documents=["rejection order", "application receipt", "caste/community proof", "school records", "family certificate", "residence proof"],
        portals=["state e-district or revenue portal where available", "rtionline.gov.in for central authorities"],
        escalation=["competent certificate authority", "revenue appellate authority / caste scrutiny committee", "District Legal Services Authority"],
        cautions=["Caste-certificate appeal forums and deadlines are state-specific; the rejection order matters."],
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


def _llp_compliance_pack() -> ActionPack:
    return ActionPack(
        id="llp_annual_filing",
        title="LLP annual filing path",
        next_steps=[
            "Identify the pending annual-return years, Form 11 status, and any Form 8/statement-of-account default.",
            "Collect LLPIN, LLP agreement, partner/DSC access records, MCA master data, and any Registrar notice.",
            "Use the MCA/ROC professional route first; NCLT/Tribunal only matters if strike-off or restoration has already reached that stage.",
        ],
        documents=["LLPIN", "LLP agreement", "MCA master data", "pending Form 11/Form 8 records", "partner communications", "Registrar notice if any"],
        portals=["mca.gov.in"],
        escalation=["Registrar of Companies / MCA helpdesk", "company secretary or company-law professional", "NCLT/Tribunal only for restoration/strike-off stage"],
        cautions=["This is LLP compliance, not an IBC debt-recovery path; default fees, filing status, and Registrar notices matter."],
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


def _labour_compliance_pack() -> ActionPack:
    return ActionPack(
        id="labour_compliance",
        title="Labour compliance notice path",
        next_steps=[
            "Read the notice for the exact period, worker category, alleged short payment, and reply/hearing date.",
            "Collect wage registers, attendance, challans, worker lists, contractor records, and inspection notes.",
            "File a written reply with documents before the deadline; use the ESI Court or labour forum if a determination is passed.",
        ],
        documents=["notice/order", "inspection report", "wage register", "attendance register", "ESI/challan proof", "worker and contractor list"],
        escalation=["ESI Corporation / assessing officer", "Employees' Insurance Court", "Labour Commissioner", "District Legal Services Authority"],
        cautions=["Contribution and inspection matters are deadline-sensitive; do not ignore the hearing date even if the demand looks wrong."],
    )


def _labour_register_compliance_pack() -> ActionPack:
    return ActionPack(
        id="labour_register_compliance",
        title="Overtime/register inspection path",
        next_steps=[
            "Read the inspection notice for the records demanded, alleged register gap, and hearing or reply date.",
            "Collect attendance, overtime, wage, leave, worker-list, and establishment-registration records.",
            "File a written reply with available records and a correction/compliance plan before the Labour Department hearing.",
        ],
        documents=["inspection notice", "attendance register", "overtime register", "wage register", "worker list", "establishment registration", "reply/hearing papers"],
        escalation=["Labour Department / Facilitator", "Labour Commissioner", "wage authority if wages are claimed", "District Legal Services Authority"],
        cautions=["State shops-and-establishments law controls the exact register format; BOCW applies only where the workplace is construction/building work."],
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


def _bonded_labour_pack() -> ActionPack:
    return ActionPack(
        id="bonded_labour_rescue",
        title="Bonded-labour rescue path",
        next_steps=[
            "Prioritize getting the worker or family to a safe place; do not negotiate alone with the contractor if movement is restricted.",
            "Report the worksite, contractor, advance/debt demand, and document retention to the District Magistrate/SDM, labour office, DLSA, or police.",
            "Ask for rescue, release-certificate, wage, and rehabilitation steps to be recorded in writing.",
        ],
        documents=["worker IDs", "worksite location", "contractor/employer details", "advance/debt proof", "wage proof", "photos/messages/witness names"],
        escalation=["District Magistrate/Sub-Divisional Magistrate", "Labour Commissioner", "District Legal Services Authority", "police for confinement or threats"],
        cautions=["Forced work, debt, document retention, and blocked movement are urgent safety facts, not only wage disputes."],
    )


def _child_marriage_pack() -> ActionPack:
    return ActionPack(
        id="child_marriage_protection",
        title="Child-marriage protection path",
        next_steps=[
            "Move fast on safety: contact the child helpline, Child Welfare Committee, police, or DLSA if the marriage is planned or ongoing.",
            "Preserve age proof and any invitation, message, travel, or venue details showing the planned or completed marriage.",
            "Ask for prevention, protection, residence, and annulment/remedy options based on whether the marriage has happened.",
        ],
        documents=["birth certificate/school record", "ID/address proof", "invitation/messages", "venue/date details", "guardian details", "photos/videos if safe"],
        portals=["1098 child helpline where available"],
        escalation=["Child Welfare Committee", "police station", "District Legal Services Authority", "Child Marriage Prohibition Officer where available"],
        cautions=["Do not wait for a detailed legal answer if the child may be moved or married soon."],
    )


def _disability_access_pack() -> ActionPack:
    return ActionPack(
        id="disability_access",
        title="Disability certificate/access path",
        next_steps=[
            "Collect the application number, medical papers, and the exact office or medical board handling the certificate.",
            "Ask for written status or refusal reasons, then escalate to the district social welfare office or disability commissioner channel.",
            "Use DLSA help if delay, denial, or lack of accommodation blocks benefits, education, work, or mobility.",
        ],
        documents=["ID/address proof", "medical records", "UDID/application receipt", "refusal or delay proof", "benefit/school/work notice if linked"],
        portals=["swavlambancard.gov.in where UDID applies"],
        escalation=["district medical board/certifying authority", "District Social Welfare Office", "State Commissioner for Persons with Disabilities", "District Legal Services Authority"],
        cautions=["Certificate and benefit steps are state-procedure heavy; written status/reason is the anchor."],
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


def _supervised_visitation_pack() -> ActionPack:
    return ActionPack(
        id="supervised_visitation",
        title="Supervised-visitation order path",
        next_steps=[
            "Keep the existing supervised-visitation order and the message asking for unsupervised access.",
            "File a written objection or modification/clarification request in the same Family Court.",
            "Use DLSA if you need help filing quickly before the next visit date.",
        ],
        documents=["existing visitation order", "messages/notices asking for unsupervised access", "safety facts", "next hearing or visit date", "child age proof"],
        escalation=["Family Court", "same court registry", "DLSA"],
        cautions=["A lawyer's request does not itself change a court-ordered supervised-visitation condition."],
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


def _education_loan_pack() -> ActionPack:
    return ActionPack(
        id="education_loan_denial",
        title="Education-loan grievance path",
        next_steps=[
            "Ask the bank for written reasons for refusing or delaying the education-loan application.",
            "Collect the loan application, scholarship paper, admission/course proof, and complaint acknowledgement.",
            "Escalate through the bank grievance officer and RBI Ombudsman route if the bank does not give a reasoned response.",
        ],
        documents=["loan application", "written refusal/reason", "scholarship letter", "admission/course proof", "income/category documents", "bank complaint number"],
        portals=["cms.rbi.org.in"],
        escalation=["bank grievance officer", "RBI Ombudsman", "district education/scholarship authority", "DLSA"],
        cautions=["Education-loan disputes turn on bank policy, written refusal reasons, and the scholarship or admission documents."],
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


def _land_acquisition_compensation_pack() -> ActionPack:
    return ActionPack(
        id="land_acquisition_compensation",
        title="Land acquisition compensation path",
        next_steps=[
            "Collect the acquisition notification, award, possession record, payment/deposit proof, and land/shop ownership papers.",
            "Ask the Collector or Land Acquisition Officer in writing for award and compensation payment/deposit status.",
            "If the award/payment is disputed or not accepted, ask DLSA or counsel about the RFCTLARR reference-to-Authority route.",
        ],
        documents=["acquisition notification", "award copy", "possession notice", "payment/deposit record", "land/shop ownership papers", "objection/reference papers"],
        escalation=["Collector / Land Acquisition Officer", "RFCTLARR Authority/reference forum", "District Legal Services Authority", "High Court writ route for exceptional inaction"],
        cautions=["Do not treat highway acquisition compensation as a pollution/NGT claim unless there is a separate environmental damage fact."],
    )


def _mining_displacement_pack() -> ActionPack:
    return ActionPack(
        id="mining_displacement_rr",
        title="Mining displacement rehabilitation path",
        next_steps=[
            "Collect acquisition notices, displacement lists, award papers, and rehabilitation package records.",
            "File first with the Collector/R&R authority or district rehabilitation office.",
            "If the area is Scheduled Area/SC-ST affected, preserve Gram Sabha and Scheduled Area facts for the RFCTLARR/PESA route.",
        ],
        documents=["acquisition notice", "award/R&R papers", "village displacement list", "rehabilitation package record", "project/company or lease details", "Gram Sabha record where relevant"],
        escalation=["Collector / R&R authority", "district rehabilitation office", "Gram Sabha where applicable", "DLSA"],
        cautions=["Do not treat mining-permit details as a substitute for the rehabilitation and resettlement claim."],
    )


def _tribal_project_displacement_pack() -> ActionPack:
    return ActionPack(
        id="tribal_project_displacement_rr",
        title="Project displacement rehabilitation path",
        next_steps=[
            "Collect acquisition/project notices, affected-village lists, Gram Sabha records, and rehabilitation package papers.",
            "File first with the Collector/R&R authority or district rehabilitation office, adding the Gram Sabha/PESA objection where Scheduled Area facts fit.",
            "Use tribal welfare authority or DLSA support if records or notices are being withheld.",
        ],
        documents=["project/acquisition notice", "affected family or village list", "Gram Sabha notice/minutes", "R&R award/package papers", "land/forest-rights records", "ID/status proof"],
        escalation=["Collector / R&R authority", "district rehabilitation office", "Gram Sabha / Panchayat channel", "tribal welfare authority", "DLSA"],
        cautions=["Do not frame a project-displacement problem as only a police atrocity case unless there is separate violence, threat, or caste/tribe-targeted offence conduct."],
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


def _surrogacy_pack() -> ActionPack:
    return ActionPack(
        id="surrogacy_parenthood",
        title="Surrogacy eligibility path",
        next_steps=[
            "Confirm whether the clinic is registered and what eligibility certificates or medical indications are being requested.",
            "Collect age, marriage, medical, infertility/hysterectomy, and clinic documents before relying on verbal advice.",
            "Check the appropriate authority process before paying or signing any surrogacy arrangement.",
        ],
        documents=["IDs and marriage proof", "age proof", "medical records", "infertility/hysterectomy certificate", "clinic registration details", "draft agreement or consent papers"],
        escalation=["appropriate authority under surrogacy/ART law", "registered clinic/hospital", "District Legal Services Authority"],
        cautions=["Surrogacy is eligibility-heavy and tightly regulated; document generation should stay gated until source retrieval is strong."],
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


def _family_marriage_status_pack() -> ActionPack:
    return ActionPack(
        id="family_marriage_status",
        title="Marriage-status protection path",
        next_steps=[
            "Collect first-marriage proof, any second-marriage proof, and messages about property, support, or threats.",
            "Clarify the personal law context before choosing civil, maintenance, domestic-violence, or criminal remedies.",
            "Use DLSA or a family-law lawyer quickly if housing, maintenance, children, or safety are affected.",
        ],
        documents=["marriage proof", "second-marriage proof if any", "ID/address proof", "children documents", "property papers", "messages/notices"],
        escalation=["Family Court", "Magistrate court where protection or maintenance applies", "District Legal Services Authority"],
        cautions=["Second-marriage remedies differ by religion/personal law and by whether protection, maintenance, or property is the immediate issue."],
    )


def _name_change_identity_pack() -> ActionPack:
    return ActionPack(
        id="name_change_identity",
        title="Name and ID-record update path",
        next_steps=[
            "Collect the marriage certificate, old and new name spelling, and identity records that need updating.",
            "Check the state gazette or government-press procedure before assuming publication is mandatory.",
            "If an authority refuses the update, keep the refusal and escalation proof for legal-aid or court review.",
        ],
        documents=["marriage certificate", "old and new ID proof", "newspaper/Gazette papers if used", "application receipt", "refusal letter if any"],
        portals=["eGazette or state gazette portal where applicable", "Aadhaar/passport/PAN or record-issuing portal"],
        escalation=["government press or gazette office", "record-issuing authority grievance channel", "District Legal Services Authority"],
        cautions=["Gazette publication can be a route for name-change proof, but the required path depends on the record and authority being updated."],
    )


def _employment_pack() -> ActionPack:
    return ActionPack(
        id="employment_wages",
        title="Employment dues path",
        next_steps=[
            "Create a wage/employment timeline with joining date, last working date, and unpaid amount.",
            "Send a written demand to employer/contractor and preserve proof.",
            "Check the notice-period, resignation, full-and-final, or termination deadline before replying.",
            "Approach the labour office or statutory portal depending on wages, PF, gratuity, maternity, or retrenchment facts.",
        ],
        documents=["appointment letter", "salary slips", "attendance", "bank statements", "termination/resignation messages"],
        portals=["EPFO grievance portal for PF issues"],
        escalation=["Labour Commissioner", "wage authority", "District Legal Services Authority"],
        cautions=["Notice-period and full-and-final disputes turn on the contract, last working date, and limitation-sensitive forum route."],
    )


def _gig_platform_worker_pack() -> ActionPack:
    return ActionPack(
        id="gig_platform_worker",
        title="Gig/platform work dispute path",
        next_steps=[
            "Preserve the contract, strike/deactivation policy, notice, appeal history, ratings, and payout ledger.",
            "Ask the platform for written reasons, the review/appeal route, and release of undisputed earnings.",
            "Use labour or social-security channels only after checking whether the facts show employee/workman status or gig/platform-worker coverage.",
        ],
        documents=["platform contract", "strike/deactivation notice", "appeal tickets", "rating/service history", "payout ledger", "ID/KYC proof"],
        portals=["platform grievance portal"],
        escalation=["platform grievance officer", "Labour Commissioner where workman/wage facts fit", "District Legal Services Authority"],
        cautions=["Platform-worker remedies depend on the contract, actual control over work, and whether the issue is wages, deactivation, or social security."],
    )


def _voter_rights_pack() -> ActionPack:
    return ActionPack(
        id="election_voter_rights",
        title="Voter-roll correction path",
        next_steps=[
            "Check the EPIC/voter ID entry and electoral-roll spelling on the Election Commission voter-services portal.",
            "File the correction or inclusion request with the Booth Level Officer or Electoral Registration Officer and keep acknowledgement.",
            "If vote denial already happened, preserve booth details, date, officer name if known, and any written refusal or complaint.",
        ],
        documents=["EPIC/voter ID", "address proof", "identity proof", "wrong-roll screenshot", "booth details", "complaint acknowledgement if any"],
        portals=["voters.eci.gov.in"],
        escalation=["Booth Level Officer", "Electoral Registration Officer", "District Election Officer", "District Legal Services Authority"],
        cautions=["Election remedies are time-sensitive around polling and roll-revision dates; exact constituency and date matter."],
    )


def _election_candidate_pack() -> ActionPack:
    return ActionPack(
        id="election_candidate_dispute",
        title="Election procedure path",
        next_steps=[
            "Preserve the nomination/order/result documents and note the exact declaration or rejection date.",
            "Use the Returning Officer or Election Commission channel for immediate procedural objections.",
            "For result challenges, check election-petition limitation before drafting any representation.",
        ],
        documents=["nomination papers", "scrutiny/rejection order", "affidavit and symbol documents", "result/counting records", "complaint acknowledgements"],
        portals=["eci.gov.in", "voters.eci.gov.in"],
        escalation=["Returning Officer", "District Election Officer", "Chief Electoral Officer / Election Commission", "High Court election-petition route"],
        cautions=["Election deadlines can be very short; avoid generic legal notices when a statute-prescribed petition or objection route applies."],
    )


def _undertrial_review_pack() -> ActionPack:
    return ActionPack(
        id="undertrial_review_release",
        title="Undertrial review path",
        next_steps=[
            "Calculate custody time from the first remand date and compare it with the maximum punishment alleged.",
            "Collect remand orders, chargesheet/trial stage, prior bail orders, and age/medical records.",
            "Ask jail legal aid, DLSA, or the trial court to place the case for statutory undertrial review or bail.",
        ],
        documents=["FIR/charge sections", "remand orders", "chargesheet status", "custody warrant", "prior bail orders", "age/medical proof"],
        escalation=["jail legal-aid clinic", "District Legal Services Authority / Under Trial Review Committee", "trial court", "High Court where delay is unlawful"],
        cautions=["Section 479/436A eligibility depends on offence severity, maximum punishment, prior custody period, and statutory exclusions."],
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
            "Calculate custody days and chargesheet/default-bail dates from remand papers; NDPS commercial cases may have a 180-day chargesheet period.",
            "Collect notice, FIR, arrest memo, bail orders, remand orders, extension applications, and court dates.",
            "Speak to legal aid or a criminal lawyer quickly if arrest or custody is possible.",
        ],
        documents=["FIR/complaint", "notice/summons", "arrest memo if any", "remand orders", "chargesheet/extension status", "prior bail/order copies", "ID/address proof"],
        escalation=["criminal court", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
        cautions=["Bail strategy changes with offence sections, arrest status, custody length, chargesheet deadline, and incident date."],
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


def _manual_scavenging_pack() -> ActionPack:
    return ActionPack(
        id="manual_scavenging_safety",
        title="Septic-tank/sewer death path",
        next_steps=[
            "Prioritize safety and medical/emergency reporting; do not send anyone else into the sewer or tank.",
            "Record the employer/contractor, work order, safety equipment facts, witnesses, and death or injury records.",
            "Approach the District Magistrate/local authority, police, labour office, and DLSA for prohibition, compensation, rehabilitation, and criminal-negligence routes.",
        ],
        documents=["death certificate/postmortem or medical papers", "photos/videos of site and safety equipment", "contractor/employer details", "work order or attendance proof", "witness names", "dependant/family documents"],
        escalation=["District Magistrate/local authority", "police station", "Labour Commissioner / Employees Compensation Commissioner", "District Legal Services Authority"],
        cautions=["Sewer and septic-tank death is an urgent safety and compensation matter; avoid informal settlements before official records are made."],
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


def _custody_safeguard_pack() -> ActionPack:
    return ActionPack(
        id="arrest_custody_safeguard",
        title="Arrest safeguard path",
        next_steps=[
            "Write the exact arrest or pickup time, police station, officer details, and whether family was informed.",
            "Ask DLSA or a lawyer to check whether the person has been produced before a Magistrate and whether a remand order exists.",
            "For continued detention without production/order, escalate urgently to the Magistrate, senior police, or High Court route.",
        ],
        documents=["arrest memo if any", "FIR/case details", "station diary/acknowledgement if available", "messages/calls", "ID proof", "medical/injury record if any"],
        escalation=["nearest Magistrate", "District Legal Services Authority", "senior police officer", "High Court writ jurisdiction"],
        cautions=["The old/new criminal-procedure regime can depend on the incident and arrest dates, so dates matter."],
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


def _security_cheque_pack() -> ActionPack:
    return ActionPack(
        id="security_cheque_defence",
        title="Security-cheque defence path",
        next_steps=[
            "Collect the rent, loan, or security agreement showing why the cheque was given.",
            "Preserve any bank return memo, notice, envelope, and messages about misuse.",
            "If a notice arrives, calculate the reply and payment-window dates before choosing a defence or settlement path.",
        ],
        documents=["cheque copy/details", "rent/loan/security agreement", "vacating or repayment proof", "bank return memo", "notice copy", "messages"],
        escalation=["bank branch/grievance officer", "Judicial Magistrate court if complaint is filed", "civil/rent court", "District Legal Services Authority"],
        cautions=["Security-cheque facts are actor-sensitive; drawer and payee routes are different, and NI Act timelines can be strict."],
    )


def _senior_maintenance_cheque_pack() -> ActionPack:
    return ActionPack(
        id="senior_maintenance_cheque",
        title="Parent-maintenance cheque path",
        next_steps=[
            "Collect proof of age, dependency, and the maintenance arrangement or order.",
            "Preserve the cheque, bank return memo, and any demand notice or reply.",
            "Compare the senior-citizen maintenance route with the cheque-dishonour route before filing.",
        ],
        documents=["age proof", "maintenance order/agreement if any", "cheque", "return memo", "notice copy", "messages"],
        escalation=["Maintenance Tribunal", "District Magistrate / senior-citizen cell", "Judicial Magistrate court", "District Legal Services Authority"],
        cautions=["Cheque-dishonour dates and maintenance-tribunal facts both matter; avoid missing the notice/payment-window timeline."],
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


def _drug_license_pack() -> ActionPack:
    return ActionPack(
        id="drug_license_compliance",
        title="Drug-inspector sample path",
        next_steps=[
            "Preserve the sample memo, seizure/intimation papers, test report, batch invoices, and prescription or sale register entries.",
            "Match the notice to the alleged Schedule H/licence condition and reply through the licensing authority or Drug Inspector channel.",
            "If prosecution is filed, use the criminal-court/legal-aid route with the licence record, sample chain, and analyst report.",
        ],
        documents=["drug licence copy", "sample memo", "seizure/intimation papers", "test report", "batch invoices", "prescription/sale register", "notice/prosecution papers"],
        escalation=["Drug Inspector / licensing authority", "State Drug Controller", "criminal court if prosecution is filed", "DLSA"],
        cautions=["Do not answer a sample seizure or Schedule H allegation as a generic shop-licence renewal issue; the sample chain and statutory notice matter."],
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
