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

from apps.api.crisis_resources import india_self_harm_portal_labels


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
    "fir", "police", "arrest", "bail", "theft", "stolen", "stole", "rape", "molest",
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
    "fake trai", "fake video", "fake ai video", "ai video",
    "it cell",
    "fake customer care", "fake customer support", "fake helpline",
    "install app", "installed app", "remote access", "anydesk",
    "screen sharing", "money got transferred", "video call recorded",
    "recorded video call", "recorded me", "demanding money",
    "dick pic", "bumble", "leaked my chat", "leaked chat",
    "mental health privacy", "privacy leak", "insta", "dm daily",
        "after blocking", "tinder", "extortion",
    "tweet", "twitter", "x.com", "online post", "social media post",
    "rugpull", "rugpulled", "csam", "ai csam",
    "child sexual abuse material", "child sexual image",
    "child sexual images", "child porn", "child pornography",
)
_CSAM_WORDS = (
    "csam", "ai csam", "child sexual abuse material",
    "child sexual image", "child sexual images",
    "child porn", "child pornography",
)
_INTIMATE_IMAGE_WORDS = (
    "private photo", "private photos", "private picture", "private pictures",
    "private video", "private videos", "intimate photo", "intimate photos",
    "intimate video", "intimate videos", "nude photo", "nude photos",
    "nude", "nude image", "nude video", "naked photo", "naked photos",
    "naked image", "naked video", "fake nude", "fake nudes",
    "sexual image", "sexual images", "morphed sexual image",
    "morphed sexual images", "nudes", "morphed photo", "morphed photos", "leaked photo",
    "leaked photos", "deepfake", "sex video", "porn video",
    "morphed image", "morphed images", "morphed pic", "morphed pics",
    "morphed nude", "morphed nudes", "morphed naked",
    "morphed group photo", "morphed group photos", "ai porn",
    "onlyfans content", "onlyfans video", "onlyfans videos",
    "onlyfans photo", "onlyfans photos", "paid content",
    "subscription content", "creator content", "recorded video call", *_CSAM_WORDS,
)
_IMAGE_ABUSE_CONTEXT_WORDS = (
    "send to", "send it to", "send my", "send our", "send her", "send his",
    "share my", "share our", "show my", "show our", "forward my",
    "forward our", "upload", "uploaded", "post online", "posted", "posting",
    "leak", "leaked", "blackmail", "threat", "threaten", "threatens",
    "threatened", "threatening", "telegram", "whatsapp", "instagram",
    "facebook", "reddit", "hostel", "college group", "family group",
    "relatives", "circulate", "circulating", "website", "remove",
    "takedown", "take down", "complain",
)
_INTIMATE_IMAGE_RISK_WORDS = (
    "ex", "boyfriend", "girlfriend", "bf", "gf", "partner", "stranger",
    "unknown person", "online friend", "has my nudes", "has our nudes",
    "has my nude", "has my private photo", "has my private photos",
    "has my intimate", "saved my nudes", "kept my nudes", "lookalike",
    "look alike", "face same", "not me but face", "featuring me",
    "with my face", "my face",
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
    "not refunding", "support not refunding", "charged after cancellation",
    "subscription after cancellation", "subscription refund",
    "yearly subscription", "auto renewal", "auto-renewal",
    "amazon", "flipkart", "e-commerce", "online order", "third party seller",
    "third-party seller", "fake iphone", "fake product", "return refused",
    "fake goods", "fake shoes", "duplicate shoes", "online seller",
    "service center", "service centre", "coaching", "coaching centre",
    "coaching center",
    "medical negligence", "hospital negligence", "wrong injection",
    "doctor gave", "patient died compensation", "hospital bill",
    "wrong surgery", "wrong operation", "wrong leg", "wrong limb",
    "operated wrong", "surgical negligence", "icu", "refused to treat",
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
    "salary", "wage", "wages", "pay", "paid", "payment", "unpaid", "dues",
    "employer", "employee", "job", "work", "labour", "labor", "termination",
    "terminated", "fired", "dismissed",
)
_TRADEMARK_WORDS = (
    "trademark", "trade mark", "brand name", "logo", "passing off",
    "counterfeit", "copyright", "patent", "ip india", "unlicensed copies",
)
_TRIBAL_CASTE_WORDS = (
    "adivasi", "tribal", "sarna", "pahan", "dalit", "scheduled caste",
    "scheduled tribe", "sc st", "caste slur", "caste name", "untouchability",
    "untouchable", "caste discrimination", "temple entry", "cannot enter temple",
    "not allowed temple", "prevented temple",
    "forest rights", "forest department", "fra 2006", "fra claim",
    "gram sabha", "pesa", "st certificate", "gond",
    "munda", "agency village", "agency area",
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
    "boiler blast", "boiler explosion", "factory blast", "factory explosion",
    "plant accident", "plant blast", "plant explosion", "factory death",
    "factory killed", "factory killed worker", "worker died", "worker dead",
    "worker killed", "killed worker", "friend dead", "friend died",
    "died at site", "death at site", "silicosis", "contractor injury",
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
    "vape", "vape pen", "vape cartridge", "bhang", "bhang lassi",
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
    "temporary release", "temporary parole", "emergency parole",
    "custody parole", "release for funeral", "funeral parole",
    "last rites", "cremation", "family death", "death in family",
    "death of mother", "death of father", "mother's funeral",
    "father's funeral", "wedding parole", "marriage parole",
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
    "svb", "special valuation branch",
    "capital gains", "54f", "80c", "80ccd", "nps",
    "tax applies", "tax on sale", "tax on property sale", "property sale tax",
    "tcs", "foreign remittance", "remittance", "206c",
    "itc", "input tax credit", "supplier registration cancelled",
    "rule 86b", "86b", "1% cash", "1 percent cash", "one percent cash",
)
_CUSTOMS_TAX_WORDS = (
    "customs", "icegate", "bill of entry", "shipping bill", "drawback",
    "import duty", "customs duty", "customs broker", "port hold",
    "duty demand", "classification dispute", "reclassified",
    "shipment held at port", "svb", "special valuation branch",
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
    "lied before marriage", "lie before marriage", "lies before marriage",
    "false before marriage", "fraud before marriage", "misrepresented before marriage",
    "misrepresentation before marriage", "hid before marriage", "concealed before marriage",
    "job before marriage", "salary before marriage", "job and salary",
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
    "payment delay", "payment pending", "pending payment", "45 days payment", "amount outstanding",
    "samadhan", "samadhaan", "msefc", "msme registered",
    "msme registered party", "msme samadhan portal", "public sector buyer",
    "psu not paid", "commercial court", "pre litigation mediation",
    "pre-litigation mediation", "vendor agreed", "recover advance",
    "kept my advance", "advance can i recover", "advance recover",
    "advance refund", "purchase order", "work order",
    "cancel and recover", "delivery in 30 days", "supplier failed",
    "cancelled contract", "canceled contract",
    "nutrition supplier", "supplier bill", "vendor bill", "government bill",
    "failed to deliver", "did not deliver", "machinery", "equipment",
    "goods delivery", "supplier delivered", "defective material",
    "defective materials", "supplier refusing refund", "refusing refund",
    "defective goods", "damaged goods", "poor quality goods",
    "supplier refund", "supplier replace", "supplier replacement",
    "fanvue payment", "creator payment", "creator payout",
    "platform payout", "usd payment", "foreign platform payment",
    "payment frozen", "release fund",
)
_BUSINESS_LICENSE_WORDS = (
    "shop license", "shop act", "licence renewal", "license renewal", "shops and establishments",
    "trade license", "factory license", "establishment registration",
    "signboard licence", "signboard license", "licence problem",
    "license problem", "municipal fine", "shop fine", "market shop",
    "restaurant sealed", "restaurant was sealed", "sealed by corporation",
    "corporation officers", "can i reopen",
    "bar license", "bar licence", "liquor license", "liquor licence",
    "excise license", "excise licence", "wine shop", "liquor shop",
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
    "bnss 94", "section 94", "94 notice", "notice under 94",
    "summons to produce", "produce document", "produce documents",
    "produce phone", "produce mobile", "hand over phone", "seize phone",
    "phone and whatsapp", "phone data", "device notice", "call recordings",
    "all chats", "bring all chats", "bring chats", "laptop", "produce laptop",
)
_PASSPORT_PROCEDURE_WORDS = (
    "passport police verification", "passport verification", "police verification",
    "adverse police report", "police not clearing passport",
    "not clearing passport verification", "clearing passport verification",
    "passport refused", "passport rejection", "passport denied", "passport pending",
    "passport on hold", "passport hold", "rpo", "regional passport officer",
    "passport impounded", "passport revoked", "passport renewal", "passport application",
    "pasport", "adverse report", "police/thana verification", "thana verification",
)
_LOK_ADALAT_CHALLENGE_WORDS = (
    "lok adalat award", "challenge lok adalat", "set aside lok adalat",
    "lok adalat settlement", "national lok adalat award",
)
_EDUCATION_WORDS = (
    "rte", "school", "admission", "tc", "transfer certificate",
    "capitation", "25 percent", "teacher demanding money",
    "college", "original certificate", "original certificates",
    "holding certificate", "holding certificates",
    "withholding certificate", "withholding certificates",
    "original marksheet", "original marksheets", "original mark sheet",
    "original mark sheets",
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
    "civil case", "civil court", "court summons", "court sent summons",
    "witness evidence", "witness summons", "bring documents",
    "bring sale deed", "bring property papers",
)
_UNDERTRIAL_REVIEW_WORDS = (
    "bnss 479", "479 bnss", "section 479", "undertrial review",
    "undertrial review committee", "under trial review committee",
    "undertrial prisoner review", "undertrial release", "436a",
    "half of maximum", "one half of maximum", "one-third of maximum",
    "half sentence", "half maximum", "completed half", "maximum punishment",
    "trial not started", "long custody", "jail since", "spent half",
    "one third", "one-third", "trial not moving", "trial delay",
    "trial court keeps dates", "no witness", "not produced by video",
    "not produced on video", "not produced for", "missed court dates",
    "missed video production", "missed video productions",
    "video production dates", "video productions",
    "jail internet failed", "video link failed", "video production failed",
    "custody increasing", "remand keeps extending", "remand extending",
    "custody is", "custody-duration",
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
    "mutual divorce", "both of us agree", "both agree for mutual divorce",
    "both want divorce", "joint divorce petition", "joint petition for divorce",
)
_LABOUR_EXPLOITATION_WORDS = (
    "nrega", "mgnrega", "asha worker", "honorarium", "cards passport",
    "keeping our cards", "bonded labour", "women workers", "half pay",
    "biharee", "racist", "wrongfully terminated", "terminated from job",
    "migrant worker", "inter state migrant", "inter-state migrant",
    "go back home", "return ticket", "return fare", "journey allowance",
    "sent us home", "sent them home", "sent workers home", "walked from", "domestic worker",
    "madam not paying", "muster roll", "fake muster", "bdo putting my name",
    "factory deducted", "deducted 800", "wage deducted", "uniform never given",
    "shoes uniform", "safety shoes", "deducting for shoes", "never gives shoes",
    "never gave shoes", "takes money for safety shoes", "job card", "job cards", "mukhiya", "munshi",
    "no payment", "bocw card", "bocw", "cess", "ismw",
    "industrial dispute", "industrial disputes", "section 10", "sec 10",
    "labour court", "labor court", "conciliation", "reference pending",
    "inter-state migrant workmen", "inter state migrant workmen",
    "migrant registration", "displacement allowance", "came together",
    "brought from", "abandoned workers", "abandoned 12 workers",
    "minimum wage", "minimum wages", "state rate", "unskilled",
)
_ENVIRONMENT_WORDS = (
    "thermal plant", "blasting", "cracking our houses", "pollution",
    "environment", "factory pollution", "air pollution", "smoke",
    "factory smoke", "ngt", "national green tribunal",
    "mining company", "iron ore",
    "iron ore mine", "mine displaced", "mine displacement",
    "mining displacement", "mining blast", "mine blasting", "blast cracked",
    "cracked my house", "cracked my house walls",
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
    "bank account is frozen", "bank account freeze",
    "bank account blocked", "bank account lien",
    "lien marked by bank",
    "salary account blocked", "salary account frozen", "upi account frozen",
    "upi account blocked", "bank wrong debit", "bank wrongly deducted",
    "bank not reversing", "bank not reversing amount", "bank dedcted",
    "dedcted money wrongly", "money dedcted wrongly", "loan app",
    "online loan app", "instant loan app", "digital lending app",
    "rbi ombudsman", "bank account kyc",
    "fd", "fixed deposit", "nominee", "loan against my house",
    "didn't sign", "did not sign", "sarfaesi", "13(2) notice",
    "home loan default", "security interest", "possession notice",
    "nbfc", "recovery agent", "recovery agents", "loan recovery",
    "bajaj", "bajaj finance", "bajaj finserv", "finance company", "collection agent",
    "collection agents", "collection people", "emi bounced", "emi bounce",
    "emi default", "bank error",
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
    "fantasy app", "gaming app", "winning amount",
)
_MENTAL_HEALTH_WORDS = (
    "mentally ill", "kept him in chains", "mental healthcare",
    "admit in hospital", "psychiatric",
)


def _criminal_quashing_route(q: str) -> MatterRoute | None:
    if not _is_criminal_quashing_issue(q):
        return None
    if _is_accused_498a_issue(q):
        return None
    regime = _criminal_regime(q)
    if regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
        required_sources = [
            "CrPC 1973 section 482 for pre-1 July 2024 or legacy CrPC framing",
            "FIR, charge-sheet, summons, and lower-court orders only to identify the case stage",
        ]
    elif regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
        required_sources = [
            "BNSS 2023 section 528 for current High Court inherent-powers/quashing framing",
            "CrPC 1973 section 482 for pre-1 July 2024 or legacy CrPC framing",
            "FIR, charge-sheet, summons, and lower-court orders only to identify the case stage",
        ]
    else:
        required_sources = [
            "BNSS 2023 section 528 for current High Court inherent-powers/quashing framing",
            "FIR, charge-sheet, summons, and lower-court orders only to identify the case stage",
        ]
    return MatterRoute(
        category="criminal_defence_bail",
        label="Criminal quashing / High Court procedure",
        confidence=0.84,
        urgency="high",
        required_sources=required_sources,
        forums=["High Court", "criminal court named in the case papers", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
        missing_facts=["incident date", "FIR/charge-sheet sections", "current case stage", "summons or next hearing date", "copy of FIR/charge-sheet/order being challenged"],
        red_flags=_red_flags(q),
        action_pack=_bail_pack(),
        legal_regime=regime,
    )


def _domestic_residence_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="family_domestic",
        label="Domestic violence / right to residence",
        confidence=0.82,
        urgency="emergency" if _has_any(q, (
            "raat", "night", "now", "today", "unsafe", "locked",
            "threw me out", "throws me out", "throwing me out",
            "thrown me out", "kicked me out", "ghar se nikal", "nikal diya",
        )) else "high",
        required_sources=[
            "PWDVA 2005 residence, protection, monetary relief and application procedure",
            "BNS 2023 / IPC 1860 hurt, intimidation, confinement, or threat provisions based on incident date where assault or coercion is alleged",
            "BNSS 2023 / CrPC 1973 FIR, complaint, and Magistrate escalation procedure based on incident date where police help is needed",
            "family law statute by religion where maintenance/divorce also applies",
        ],
        forums=["Protection Officer", "Magistrate court", "Family Court", "District Legal Services Authority"],
        missing_facts=["current safety and shelter", "marriage/residence facts", "children/dependants", "incident dates", "income and documents", "state/city"],
        red_flags=_red_flags(q),
        action_pack=_family_safety_pack(),
        legal_regime=_criminal_regime(q) if _has_any(q, _CRIME_WORDS) else None,
    )


def _family_domestic_notice_response_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="family_domestic",
        label="Domestic violence notice / response",
        confidence=0.80,
        urgency="high",
        required_sources=[
            "PWDVA 2005 application, protection, residence, monetary-relief, and reply procedure",
            "Family Courts Act 1984 where matrimonial, custody, maintenance, or settlement proceedings are linked",
            "BNSS/CrPC and BNS/IPC only where a separate FIR, arrest notice, or criminal complaint exists",
        ],
        forums=["Magistrate court named in the notice", "Family Court if linked proceedings exist", "District Legal Services Authority", "lawyer/legal-aid desk"],
        missing_facts=["notice/application copy", "next hearing date", "reliefs claimed", "residence and marriage facts", "income/payment records", "messages/medical or witness records supporting your reply"],
        red_flags=[],
        action_pack=_family_notice_response_pack(),
    )


def route_matter(query: str) -> MatterRoute:
    q = _norm(query)

    if _is_crisis_signal(q):
        return MatterRoute(
            category="crisis_self_harm",
            label="Mental health crisis — immediate support needed",
            confidence=0.95,
            urgency="emergency",
            required_sources=[],
            forums=[
                "iCall: 9152987821",
                "Vandrevala Foundation: 1860-2662-345",
                "AASRA: 9820466627",
                "iCall WhatsApp: 9152987821",
            ],
            missing_facts=[],
            red_flags=["Suicidal ideation detected — refer to crisis helpline immediately"],
            action_pack=ActionPack(
                id="self_harm_crisis",
                title="Immediate mental health support",
                next_steps=[
                    "Call iCall on 9152987821 or WhatsApp the same number — trained counsellors available.",
                    "Call Vandrevala Foundation on 1860-2662-345 (24x7, free, multilingual).",
                    "If in immediate danger, go to the nearest government hospital emergency or call 112.",
                ],
                documents=[],
                portals=india_self_harm_portal_labels(),
                escalation=["nearest government hospital emergency", "112 for immediate danger"],
                cautions=["This is mental health support, not legal advice. Legal questions can be revisited when you are safe."],
            ),
        )

    if _is_self_harm_crisis(q):
        return MatterRoute(
            category="crisis_self_harm",
            label="Immediate self-harm crisis / safety first",
            confidence=0.9,
            urgency="emergency",
            required_sources=[
                "Immediate emergency/crisis support before legal analysis",
                "District Legal Services Authority or relevant legal route only after immediate safety",
            ],
            forums=[
                "local emergency services",
                "AASRA 24x7 helpline",
                "KIRAN mental-health helpline",
                "Vandrevala Foundation helpline",
                "trusted person or nearby hospital",
                "District Legal Services Authority after immediate safety",
            ],
            missing_facts=[
                "current location/safety",
                "whether you are alone",
                "trusted person nearby",
                "medical emergency or violence risk",
                "state/city for legal follow-up",
            ],
            red_flags=["Self-harm or suicide risk"],
            action_pack=_self_harm_crisis_pack(),
        )

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

    if _is_uapa_bail_or_custody_issue(q):
        return _uapa_bail_route(q)

    if _is_family_domestic_notice_response_issue(q):
        return _family_domestic_notice_response_route(q)

    civil_court_route = _civil_court_procedure_route(q)
    if civil_court_route is not None:
        return civil_court_route

    high_risk_route = _high_risk_precedence_route(q)
    if high_risk_route is not None:
        return high_risk_route

    if _is_adult_partner_choice_police_return_issue(q):
        return _adult_partner_choice_police_return_route(q)

    early_precise_route = _early_precise_common_route(q)
    if early_precise_route is not None:
        return early_precise_route

    prison_release_or_access = _prison_release_or_access_route(q)
    if prison_release_or_access is not None:
        return prison_release_or_access

    if _is_mutation_after_death_issue(q):
        return MatterRoute(
            category="land_revenue_records",
            label="Mutation after death / revenue record correction",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Hindu Succession Act / applicable personal succession law for heirship and shares",
                "state land revenue / mutation rules for record correction based on state and mutation order",
                "Right to Information Act 2005 where mutation status, objections, or file reasons are not supplied",
            ],
            forums=["tehsildar/taluk/revenue office", "revenue appellate authority", "civil court only if title/share is disputed", "District Legal Services Authority"],
            missing_facts=["state/district", "death certificate", "family tree/legal-heir proof", "khata/khasra/survey or patwari record", "mutation application number", "objection or rejection reason if any"],
            red_flags=_red_flags(q),
            action_pack=_land_records_pack(),
        )

    # Succession questions are a high-precision civil route. Run this before
    # legal-aid/criminal catchalls so "police", "DLSA", or "children" in a
    # widow/no-will property question does not create a dangerous wrong frame.
    if _is_succession_issue(q):
        return _succession_route(q)

    if _is_family_domestic_notice_response_issue(q):
        return _family_domestic_notice_response_route(q)

    criminal_defense_route = _criminal_quashing_route(q)
    if criminal_defense_route is not None:
        return criminal_defense_route

    specific_route = _specific_high_risk_surface_route(q)
    if specific_route is not None:
        if specific_route.category != "environment_compensation" or not _is_work_injury(q):
            return specific_route

    if _is_bocw_registration_issue(q):
        return _bocw_registration_route(q)

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

    if _is_work_injury(q):
        return MatterRoute(
            category="workplace_injury_compensation",
            label="Workplace injury / compensation",
            confidence=0.76,
            urgency="high",
            required_sources=["Employees Compensation Act 1923", "BOCW Act 1996 / Factories Act 1948 where applicable"],
            forums=["Labour Commissioner", "Employees Compensation Commissioner", "BOCW welfare board", "District Legal Services Authority"],
            missing_facts=["state/city", "employment/contractor details", "accident date", "medical papers", "wage proof"],
            red_flags=_red_flags(q),
            action_pack=_work_injury_pack(),
        )

    priority_route = _priority_route(q)
    if priority_route is not None:
        return priority_route

    if _is_criminal_quashing_issue(q):
        regime = _criminal_regime(q)
        if regime == "legacy_ipc_crpc_evidence_for_pre_2024_incident":
            required_sources = [
                "CrPC 1973 section 482 for pre-1 July 2024 or legacy CrPC framing",
                "FIR, charge-sheet, summons, and lower-court orders only to identify the case stage",
            ]
        elif regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc":
            required_sources = [
                "BNSS 2023 section 528 for current High Court inherent-powers/quashing framing",
                "CrPC 1973 section 482 for pre-1 July 2024 or legacy CrPC framing",
                "FIR, charge-sheet, summons, and lower-court orders only to identify the case stage",
            ]
        else:
            required_sources = [
                "BNSS 2023 section 528 for current High Court inherent-powers/quashing framing",
                "FIR, charge-sheet, summons, and lower-court orders only to identify the case stage",
            ]
        return MatterRoute(
            category="criminal_defence_bail",
            label="Criminal quashing / High Court procedure",
            confidence=0.84,
            urgency="high",
            required_sources=required_sources,
            forums=["High Court", "criminal court named in the case papers", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
            missing_facts=["incident date", "FIR/charge-sheet sections", "current case stage", "summons or next hearing date", "copy of FIR/charge-sheet/order being challenged"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=regime,
        )

    if _is_criminal_compounding_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Criminal compounding / withdrawal procedure",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "BNSS 2023 compounding/withdrawal procedure for current matters",
                "CrPC 1973 section 320 for legacy or expressly CrPC-framed matters",
                "court permission and offence-compoundability limits must be checked from the exact section",
            ],
            forums=["criminal court / Magistrate", "prosecution or complainant counsel", "District Legal Services Authority"],
            missing_facts=["offence sections", "incident/FIR date", "case stage", "whether complainant and accused consent", "whether court permission is required"],
            red_flags=[],
            action_pack=_court_procedure_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_section_91_notice(q):
        return _production_notice_route(q)

    if _is_police_questioning_notice_issue(q):
        return MatterRoute(
            category="criminal_procedure_notice",
            label="Police questioning / appearance notice",
            confidence=0.78,
            urgency="high",
            required_sources=[
                "BNSS 2023 section 35 police notice/appearance safeguards for current matters",
                "CrPC 1973 section 160 witness-attendance route for pre-1 July 2024 matters where applicable",
                "BNSS 2023 / CrPC 1973 FIR or complaint route if police refuse to give any written paper",
            ],
            forums=["investigating officer/police station", "Magistrate/criminal court if coercion or refusal escalates", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
            missing_facts=["notice/call date", "police station and officer", "case/FIR number if any", "whether you are witness, complainant, or suspect", "whether a written notice was given"],
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

    if _is_drug_treatment_support_issue(q):
        return MatterRoute(
            category="drug_treatment_support",
            label="Drug addiction / de-addiction support",
            confidence=0.73,
            urgency="high" if _has_any(q, ("overdose", "unconscious", "suicide", "violent", "violence", "unsafe")) else "medium",
            required_sources=[
                "NDPS Act 1985 treatment, de-addiction, and rehabilitation provisions",
                "district health / de-addiction centre route and family-support counselling where available",
                "police or criminal-law route only if there is contraband, violence, threat, seizure, FIR, or immediate danger",
            ],
            forums=["government de-addiction or treatment centre", "district hospital / District Mental Health Programme where available", "District Legal Services Authority", "police/emergency care only if immediate danger or illegal possession facts are present"],
            missing_facts=["state/district", "age and current safety", "substance if known", "whether treatment is voluntary or resisted", "overdose/violence/threat facts", "whether police/FIR/seizure is already involved"],
            red_flags=_red_flags(q),
            action_pack=_drug_treatment_support_pack(),
        )

    if _is_household_drug_safety_issue(q):
        return MatterRoute(
            category="criminal_general",
            label="Household drug-possession safety concern",
            confidence=0.74,
            urgency="high",
            required_sources=[
                "NDPS Act 1985 for narcotic or psychotropic substance classification and possession exposure",
                "BNSS 2023 / CrPC 1973 complaint, seizure, and police procedure based on incident date",
                "medical, counselling, or family-safety support where substance use creates immediate danger",
            ],
            forums=["police station or senior police if immediate danger", "District Legal Services Authority", "criminal lawyer/legal-aid desk", "emergency medical or crisis support if unsafe"],
            missing_facts=["substance name if known", "quantity/location", "current safety", "whether police/FIR/seizure already happened", "incident date and place"],
            red_flags=_red_flags(q),
            action_pack=_drug_safety_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_completed_suicide_legal_issue(q):
        return MatterRoute(
            category="criminal_general",
            label="Suicide / abetment or workplace-harassment complaint",
            confidence=0.76,
            urgency="high",
            required_sources=[
                "BNS 2023 / IPC 1860 abetment, cruelty, threat, or harassment provisions based on incident date",
                "BNSS 2023 / CrPC 1973 FIR, investigation, post-mortem/inquest, and complaint-escalation procedure based on incident date",
                "labour/employment forum only where workplace harassment, wage, or employer-retaliation facts are involved",
            ],
            forums=["police station", "senior police officer", "Judicial Magistrate", "District Legal Services Authority", "labour authority where workplace facts exist"],
            missing_facts=["date and place of death", "suicide note/messages/witnesses", "post-mortem/inquest papers", "harassment/threat facts", "workplace or family relationship", "police complaint/FIR status"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_adult_family_violence_issue(q):
        return MatterRoute(
            category="family_domestic",
            label="Adult family violence / elder-safety complaint",
            confidence=0.74,
            urgency="high",
            required_sources=[
                "BNS 2023 / IPC 1860 hurt, assault, intimidation, or confinement provisions based on incident date",
                "PWDVA 2005 domestic-relationship protection route where shared household or family relationship facts fit",
                "Maintenance and Welfare of Parents and Senior Citizens Act 2007 where the victim is a parent/senior citizen",
            ],
            forums=["police station or senior police if immediate danger", "Protection Officer / Magistrate court where PWDVA applies", "Maintenance Tribunal or senior-citizen cell where applicable", "District Legal Services Authority"],
            missing_facts=["victim age", "relationship and shared-household facts", "incident date/place", "injury/medical proof", "messages/witnesses", "current safety"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_child_household_assault_issue(q):
        return MatterRoute(
            category="criminal_general",
            label="Child assault / household safety complaint",
            confidence=0.78,
            urgency="high",
            required_sources=[
                "BNS 2023 / IPC 1860 hurt or assault provisions based on incident date",
                "BNSS 2023 / CrPC 1973 complaint and investigation procedure based on incident date",
                "Juvenile Justice Act / child-welfare route where the child needs care, protection, or safe placement",
            ],
            forums=["police station or senior police if immediate danger", "Child Welfare Committee / child helpline where available", "District Legal Services Authority", "doctor/ hospital for injury record"],
            missing_facts=["child age", "current safety", "injury/medical facts", "incident date and place", "messages/photos/witnesses", "whether police or CWC was contacted"],
            red_flags=_red_flags(q),
            action_pack=_child_safety_pack(),
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
        passport_required_sources = [
            "Passports Act 1967",
            "Passport Rules / MEA police-verification procedure",
            "BNSS/CrPC only where a criminal case, warrant, or summons is involved",
        ]
        if _has_any(q, ("asking money", "asked money", "bribe", "demanding money", "pay money")):
            passport_required_sources.append("Prevention of Corruption Act / anti-corruption complaint route where a public servant demands money")
        return MatterRoute(
            category="passport_police_verification",
            label="Passport police verification / refusal",
            confidence=0.78,
            urgency="high" if _has_any(q, ("asking money", "asked money", "bribe", "demanding money", "pay money", "deadline", "urgent")) else "medium",
            required_sources=passport_required_sources,
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

    if _is_lok_adalat_compounding_issue(q):
        return MatterRoute(
            category="legal_aid",
            label="Lok Adalat / compoundable-dispute route",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Legal Services Authorities Act 1987 Lok Adalat referral and award provisions",
                "BNSS 2023 / CrPC 1973 compounding provisions based on case date and papers",
                "exact offence section and consent/permission status before treating a criminal case as compoundable",
            ],
            forums=["District Legal Services Authority", "Lok Adalat desk / referring court", "criminal court or Magistrate for offence-compounding permission"],
            missing_facts=["case type and offence sections", "incident/FIR date", "case stage", "whether both sides consent", "whether the court has referred it or a Lok Adalat date is fixed"],
            red_flags=[],
            action_pack=_legal_aid_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_uapa_bail_or_custody_issue(q):
        return _uapa_bail_route(q)

    if _is_undertrial_review_issue(q):
        return _undertrial_review_route(q)

    if _is_interim_medical_bail_issue(q):
        return _custody_medical_care_route(q)

    if _is_bail_release_delay_issue(q):
        return _bail_release_delay_route(q)

    if _is_bail_surety_hardship_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Bail surety / bond hardship",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "BNSS 2023 / CrPC 1973 bail bond and surety modification provisions based on case date",
                "Article 21 personal-liberty principles where unaffordable or local-surety conditions block release",
                "bail order, bond amount, and surety condition papers",
            ],
            forums=["criminal court that imposed the condition", "District Legal Services Authority", "jail legal-aid clinic", "High Court where release is blocked despite bail"],
            missing_facts=["case/FIR number and offence sections", "bail order date", "exact surety/bond condition", "why local surety is unavailable", "income/address proof and family details"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_undertrial_review_issue(q):
        return _undertrial_review_route(q)

    if _is_default_bail_issue(q):
        return _default_bail_route(q)

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

    if _is_custody_compensation_issue(q):
        return MatterRoute(
            category="custody_compensation",
            label="Wrongful custody / acquittal compensation",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Article 21 constitutional compensation and speedy-trial principles",
                "human-rights commission procedure",
                "BNSS/CrPC custody and appeal records where relevant",
            ],
            forums=["High Court writ jurisdiction", "Human Rights Commission", "District Legal Services Authority"],
            missing_facts=["custody start/end dates", "acquittal/release order", "case/offence sections", "bail history", "delay or unlawful custody facts"],
            red_flags=_red_flags(q),
            action_pack=_custody_pack(),
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

    if _is_custody_legal_aid_access_issue(q):
        return _custody_legal_aid_access_route(q)

    if _is_arrest_production_delay(q) or _is_custody_restraint_issue(q) or _is_arrest_information_safeguard(q):
        return _arrest_custody_safeguard_route(q)

    if _is_custodial_violence_issue(q):
        return _custodial_violence_route(q)

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
        if _has_scst_protected_status(q):
            return MatterRoute(
                category="tribal_caste_atrocity",
                label="Caste / tribal witch-branding violence",
                confidence=0.84,
                urgency="emergency" if _has_any(q, ("beaten", "beat", "attack", "mob", "burn", "threat", "stripped", "disrobed", "naked in public")) else "high",
                required_sources=[
                    "SC/ST (Prevention of Atrocities) Act 1989 where caste or tribal status is part of the targeting",
                    "BNS/BNSS or IPC/CrPC based on incident date for assault, intimidation, and police-refusal procedure",
                    "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given",
                ],
                forums=["police station", "Superintendent of Police", "Special Court where SC/ST POA facts apply", "District Legal Services Authority"],
                missing_facts=["state/district", "victim SC/ST/community status proof", "incident date/place", "injury/medical proof", "police refusal proof"],
                red_flags=_red_flags(q),
                action_pack=_tribal_caste_pack(),
                legal_regime=_criminal_regime(q),
            )
        return MatterRoute(
            category="police_fir",
            label="Witch-branding violence / police complaint",
            confidence=0.74,
            urgency="emergency" if _has_any(q, ("beaten", "mob", "attack", "attacked", "village people", "stripped", "disrobed", "naked in public")) else "high",
            required_sources=[
                "BNS/BNSS or IPC/CrPC based on incident date",
                "SC/ST Act where caste or tribal status is part of the targeting",
                "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given",
            ],
            forums=["police station", "senior police officer", "District Legal Services Authority", "state women/social welfare authority where applicable"],
            missing_facts=["state/district", "incident date and place", "injury/medical proof", "who used the witch-branding words", "caste/tribal status if relevant"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
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

    if _is_pan_aadhaar_mismatch_issue(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="PAN/Aadhaar mismatch / identity linking",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Income-tax Act / PAN procedure where PAN record or PAN-Aadhaar linking is involved",
                "Aadhaar Act 2016 where Aadhaar authentication or demographic data is involved",
                "Right to Information Act 2005 or public grievance route for written status/reasons",
            ],
            forums=["Income Tax e-filing / PAN service provider", "Aadhaar Seva Kendra / UIDAI grievance", "public grievance or RTI route where official reasons are withheld", "District Legal Services Authority"],
            missing_facts=["exact name/date-of-birth mismatch", "PAN/Aadhaar last four digits", "portal or bank/scheme where rejected", "error screenshot", "which record needs correction", "complaints already filed"],
            red_flags=[],
            action_pack=_pan_aadhaar_identity_pack(),
        )

    if _is_false_loan_credit_record_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="False loan / credit-report correction",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Credit Information Companies Act 2005 for disputed credit-report correction",
                "RBI Integrated Ombudsman Scheme for bank/NBFC/lender grievance escalation",
                "Information Technology Act / BNS and BNSS only where identity theft, electronic KYC misuse, forgery, or police complaint facts exist",
            ],
            forums=[
                "bank/NBFC grievance officer",
                "credit bureau dispute channel",
                "RBI Ombudsman / CMS",
                "cyber police/local police where identity theft or forgery is alleged",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "lender/NBFC name",
                "loan account shown in credit report",
                "PAN/Aadhaar/KYC misuse proof",
                "CIBIL/credit-report screenshot",
                "lender and bureau complaint numbers",
                "police/cyber complaint number if filed",
            ],
            red_flags=_red_flags(q),
            action_pack=_banking_credit_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("forged", "forgery", "fake signature", "cyber", "police", "fir")) else None,
        )

    if _is_fake_authority_payment_fraud(q) and not _is_identity_loan_or_sim_misuse_issue(q):
        return _fake_authority_payment_fraud_route(q)

    if _is_bank_or_pension_impersonation_fraud(q) and not _is_identity_loan_or_sim_misuse_issue(q):
        return _bank_or_pension_impersonation_fraud_route(q)

    if _is_identity_loan_or_sim_misuse_issue(q):
        return MatterRoute(
            category="cyber_fraud_or_harassment",
            label="Aadhaar/PAN identity misuse / fake loan",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "Aadhaar Act 2016 where Aadhaar authentication or identity information is misused",
                "Information Technology Act 2000 identity-theft / cheating-by-personation provisions",
                "Credit Information Companies Act 2005 and RBI grievance route where a false loan or credit-report entry is involved",
                "BNS 2023 / IPC 1860 and BNSS 2023 / CrPC 1973 based on incident date where fraud, SIM misuse, or police complaint facts exist",
            ],
            forums=[
                "bank/NBFC grievance officer",
                "credit bureau dispute channel",
                "National Cyber Crime Portal / cyber police station",
                "local police station",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "Aadhaar/PAN or SIM misuse proof",
                "loan/NBFC/bank name",
                "CIBIL/credit-report entry",
                "KYC or account documents",
                "cyber/police complaint number",
                "incident date",
            ],
            red_flags=_red_flags(q),
            action_pack=_cyber_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_bank_account_freeze_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Bank account freeze / lien / KYC hold",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "RBI Integrated Ombudsman Scheme for bank/NBFC grievance escalation",
                "Banking Regulation Act / regulated-entity records for bank account service issues",
                "police/cyber/ED/court order only if the bank says the freeze is due to a legal hold",
            ],
            forums=["bank branch/grievance officer", "RBI Ombudsman", "cyber police/local police only if a legal hold or fraud is stated", "District Legal Services Authority"],
            missing_facts=["bank name and branch", "account type/number suffix", "freeze/lien date", "written reason or SMS/email", "KYC status", "complaint number", "whether police/cyber/court/ED hold is mentioned"],
            red_flags=_red_flags(q),
            action_pack=_bank_account_freeze_pack(),
        )

    if _is_lender_reminder_or_recovery_service_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Lender reminder / recovery conduct",
            confidence=0.76,
            urgency="medium",
            required_sources=[
                "RBI Integrated Ombudsman Scheme for bank/NBFC/lender grievance escalation",
                "written lender reminder, repayment/default timeline, and complaint record",
                "BNS/BNSS only if threats, public shaming, extortion, violence, or police facts are alleged",
            ],
            forums=["lender grievance officer", "RBI Ombudsman where the lender/regulated entity is covered", "District Legal Services Authority", "police/cyber police only if threats or unlawful harassment are alleged"],
            missing_facts=["lender/NBFC name", "loan account", "due date and amount", "exact SMS/call text", "whether there were threats, public shaming, or repeated abusive calls", "written complaint number"],
            red_flags=_red_flags(q),
            action_pack=_banking_credit_pack(),
        )

    if _is_loan_app_harassment_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Loan-app / recovery harassment",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "RBI Integrated Ombudsman Scheme / RBI recovery-agent and digital-lending grievance route for regulated lenders",
                "Digital Personal Data Protection Act / Information Technology Act where contacts or phone data are misused",
                "BNS/BNSS or IPC/CrPC only where threats, extortion, obscene messages, or police complaint facts are alleged",
            ],
            forums=["lender or loan-app grievance officer", "RBI Ombudsman where the lender/RE is covered", "cyber police/local police for threats or contact-data abuse", "District Legal Services Authority"],
            missing_facts=["loan app/lender name", "amount and repayment status", "messages/call logs sent to contacts", "permissions/screenshots", "complaint number", "whether threats/extortion/private-image abuse occurred"],
            red_flags=_red_flags(q),
            action_pack=_loan_app_harassment_pack(),
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
            urgency="high" if _has_any(q, ("deadline", "last date", "admission deadline", "fee deadline", "scholarship deadline")) else "medium",
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

    if _is_pan_aadhaar_mismatch_issue(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="PAN/Aadhaar mismatch / identity linking",
            confidence=0.78,
            urgency="medium",
            required_sources=[
                "Income-tax Act / PAN procedure where PAN record or PAN-Aadhaar linking is involved",
                "Aadhaar Act 2016 where Aadhaar authentication or demographic data is involved",
                "Right to Information Act 2005 or public grievance route for written status/reasons",
            ],
            forums=["Income Tax e-filing / PAN service provider", "Aadhaar Seva Kendra / UIDAI grievance", "public grievance or RTI route where official reasons are withheld", "District Legal Services Authority"],
            missing_facts=["exact name/date-of-birth mismatch", "PAN/Aadhaar last four digits", "portal or bank/scheme where rejected", "error screenshot", "which record needs correction", "complaints already filed"],
            red_flags=[],
            action_pack=_pan_aadhaar_identity_pack(),
        )

    if _is_legal_aid_eligibility_issue(q):
        return MatterRoute(
            category="legal_aid",
            label="Legal aid eligibility / DLSA support",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Legal Services Authorities Act 1987 section 12 legal-services eligibility",
                "NALSA/SLSA/DLSA legal-aid procedure for application and assignment",
            ],
            forums=["District Legal Services Authority", "State Legal Services Authority", "Taluk Legal Services Committee", "court legal-aid desk"],
            missing_facts=["district/state", "income/category proof such as BPL card if relied on", "case type", "court/police papers if any"],
            red_flags=_red_flags(q),
            action_pack=_legal_aid_pack(),
        )

    if _is_ration_card_pds_issue(q):
        required_sources = [
            "National Food Security Act 2013 for TPDS/ration entitlement and grievance redressal",
            "Right to Information Act 2005 for written cancellation/status reasons and first appeal",
        ]
        if _has_any(q, ("aadhaar", "aadhar", "biometric", "mismatch", "authentication")):
            required_sources.append("Aadhaar Act 2016 only for the identity/authentication part")
        return MatterRoute(
            category="social_welfare_identity",
            label="Ration card / PDS entitlement",
            confidence=0.78,
            urgency="medium",
            required_sources=required_sources,
            forums=[
                "ration office / food and civil supplies department",
                "State NFSA grievance mechanism / District Grievance Redressal Officer",
                "RTI public information officer for order/reason/status records",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "state/district",
                "ration-card or household ID",
                "cancellation/denial date",
                "written order or reason",
                "shop/dealer or panchayat office involved",
                "Aadhaar/biometric error if any",
            ],
            red_flags=_red_flags(q),
            action_pack=_social_welfare_pack(),
        )

    if _is_epfo_pension_identity_issue(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="EPFO pension / Aadhaar mismatch",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Employees Provident Funds and Miscellaneous Provisions Act 1952 or Code on Social Security 2020 for EPFO/EPS pension scheme basis",
                "Aadhaar Act 2016 where identity/authentication mismatch is involved",
                "Right to Information Act 2005 for written EPFO status, deficiency note, and reasons",
            ],
            forums=["EPFO grievance portal", "Regional Provident Fund Office / RPFO", "Aadhaar Seva Kendra/UIDAI for demographic correction", "RTI/Public Information Officer for EPFO records", "District Legal Services Authority"],
            missing_facts=["UAN/member ID or PPO/pension ID", "Aadhaar mismatch message", "last pension credit date", "EPFO office/region", "written rejection or grievance number"],
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
            urgency="high" if _has_any(q, ("deadline", "last date", "scholarship deadline", "admission deadline", "exam form")) else "medium",
            required_sources=["Aadhaar Act 2016 where identity/authentication is involved", "state pension/scholarship/ration scheme rules", "Right to Information Act 2005 for status and reasons"],
            forums=["scheme portal/help desk", "district social welfare office", "Aadhaar Seva Kendra/CSC where relevant", "District Legal Services Authority"],
            missing_facts=["state/district", "scheme name", "application/beneficiary ID", "rejection or mismatch reason", "documents already submitted"],
            red_flags=_red_flags(q),
            action_pack=_social_welfare_pack(),
        )

    if _is_senior_citizen_issue(q):
        return MatterRoute(
            category="senior_citizen",
            label="Parent / senior citizen maintenance",
            confidence=0.78,
            urgency="high" if _has_any(q, (
                "threw me out", "no food", "homeless", "not giving food",
                "not giving medicine", "food or medicine", "food and medicine",
                "medical expenses",
            )) else "medium",
            required_sources=[
                "Maintenance and Welfare of Parents and Senior Citizens Act 2007",
                "state maintenance tribunal rules",
            ],
            forums=["Maintenance Tribunal / District Magistrate", "District Legal Services Authority"],
            missing_facts=["state/city", "age", "property transfer date", "whether a gift/settlement deed exists"],
            red_flags=_red_flags(q),
            action_pack=_senior_pack(),
        )

    if _is_builder_rera_issue(q):
        return MatterRoute(
            category="consumer",
            label="Builder/RERA possession or occupancy-certificate dispute",
            confidence=0.82,
            urgency="high" if _has_any(q, ("full money", "all money", "paid full", "possession due", "missed deadline")) else "medium",
            required_sources=[
                "Real Estate (Regulation and Development) Act 2016 for project registration, possession delay, promoter obligations, and RERA complaint",
                "Consumer Protection Act 2019 where service deficiency/refund/compensation is pursued before consumer forum",
                "Registration/allotment/agreement documents and state RERA rules for forum-specific procedure",
            ],
            forums=["State RERA Authority / adjudicating officer", "District Consumer Disputes Redressal Commission or e-Daakhil where maintainable", "District Legal Services Authority"],
            missing_facts=[
                "state and project name",
                "RERA registration number if any",
                "builder/developer/promoter name",
                "agreement/allotment date and promised possession/OC date",
                "amount paid and receipts",
                "written refusal, delay notice, layout change, or occupancy-certificate status",
            ],
            red_flags=_red_flags(q),
            action_pack=_consumer_pack(),
        )

    if _is_cab_passenger_platform_issue(q):
        return MatterRoute(
            category="consumer",
            label="Cab/platform refund or driver complaint",
            confidence=0.80,
            urgency="medium" if not _has_any(q, ("threat", "assault", "unsafe")) else "high",
            required_sources=[
                "Consumer Protection Act 2019 for paid ride/platform service deficiency",
                "Motor Vehicles Act / aggregator guidelines where cab aggregator licensing or driver grievance duties are involved",
                "police or transport authority route only where assault, threat, or immediate safety facts are present",
            ],
            forums=["platform grievance officer/help centre", "National Consumer Helpline", "District Consumer Disputes Redressal Commission", "state transport/RTO aggregator authority where driver safety facts apply"],
            missing_facts=["platform/app name", "ride/trip ID", "fare/refund amount", "driver or support-ticket details", "screenshots and payment proof", "whether there was threat or assault"],
            red_flags=_red_flags(q),
            action_pack=_consumer_pack(),
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
        return _cyber_fraud_or_harassment_route(q)

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
        pmla_required_sources = [
            "Prevention of Money Laundering Act 2002 bail and arrest provisions",
            "BNSS 2023 / CrPC 1973 bail procedure based on incident date",
        ]
        if _has_any(q, (
            "article 21", "constitutional", "liberty", "interim", "medical",
            "newborn", "new born", "baby", "pregnant", "pregnancy", "sick",
            "infirm", "woman", "wife", "vulnerability", "proviso",
        )):
            pmla_required_sources.append("constitutional liberty and medical/vulnerability bail principles")
        return MatterRoute(
            category="criminal_defence_bail",
            label="PMLA bail / anticipatory or interim bail",
            confidence=0.84,
            urgency="high",
            required_sources=pmla_required_sources,
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

    if _is_minor_mineral_gram_sabha_issue(q):
        return MatterRoute(
            category="environment_compensation",
            label="Minor mineral / Gram Sabha recommendation",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "PESA Act 1996 section 4(c) Gram Sabha recommendation for minor minerals in Scheduled Areas",
                "Mines and Minerals (Development and Regulation) Act 1957 mining lease and mineral-concession approval record",
                "Forest Conservation Act 1980 where forest land or forest clearance is involved",
            ],
            forums=["Collector / District Magistrate", "mining department", "Gram Sabha / Panchayat channel where Scheduled Area rights apply", "tribal welfare authority", "District Legal Services Authority"],
            missing_facts=["state/district and Scheduled Area status", "mineral or quarry type", "lease/NOC number if known", "Gram Sabha/Palli Sabha notice or minutes", "forest or pollution clearance papers if any"],
            red_flags=_red_flags(q),
            action_pack=_minor_mineral_gram_sabha_pack(),
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

    if _is_mining_gram_sabha_noc_issue(q):
        return MatterRoute(
            category="environment_compensation",
            label="Mining / Gram Sabha consent challenge",
            confidence=0.80,
            urgency="high",
            required_sources=[
                "PESA Act 1996 Gram Sabha consultation or recommendation source where Scheduled Area facts apply",
                "Mines and Minerals (Development and Regulation) Act 1957 mining lease and mineral-concession approval record",
                "Forest Conservation Act 1980 where forest land or forest clearance is involved",
                "RFCTLARR Act 2013 only if land acquisition, displacement, rehabilitation, or compensation facts are involved",
            ],
            forums=["Collector / District Magistrate", "mining department", "Gram Sabha / Panchayat channel where Scheduled Area rights apply", "tribal welfare authority", "District Legal Services Authority"],
            missing_facts=["state/district and Scheduled Area status", "mine/mineral or project name", "lease/NOC number if known", "Gram Sabha/Palli Sabha notice or minutes", "forest or pollution clearance papers if any"],
            red_flags=_red_flags(q),
            action_pack=_minor_mineral_gram_sabha_pack(),
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
                action_pack=_tribal_land_transfer_pack(),
                legal_regime=None,
            )
        if _is_fra_forest_rights_issue(q):
            return MatterRoute(
                category="tribal_caste_atrocity",
                label="Forest rights / FRA claim or forest produce",
                confidence=0.82,
                urgency="high",
                required_sources=[
                    "Forest Rights Act 2006 recognition, title, minor forest produce, and Gram Sabha/SDLC/DLC procedure",
                    "PESA Act 1996 Gram Sabha provisions where the village is in a Scheduled Area",
                    "state forest/revenue records only to identify the claim, patta, or official refusal",
                ],
                forums=["Gram Sabha / Forest Rights Committee", "Sub-Divisional Level Committee", "District Level Committee / Collector", "tribal welfare authority", "District Legal Services Authority"],
                missing_facts=["state/district and village", "IFR/CFR/MFP claim type", "Gram Sabha resolution", "SDLC/DLC order or refusal reason", "patta/title papers", "forest-guard action or seizure details"],
                red_flags=_red_flags(q),
                action_pack=_forest_rights_fra_pack(),
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

    if _is_copyright_platform_takedown_issue(q):
        return MatterRoute(
            category="trademark_ip",
            label="Copyright / platform takedown",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Copyright Act 1957 infringement, exceptions/fair dealing, and civil remedies",
                "platform takedown/counter-notice record",
                "Information Technology Act intermediary route only if platform due-diligence or illegal content handling is involved",
            ],
            forums=["platform copyright appeal/counter-notice process", "commercial/civil court where needed", "IP lawyer or legal-aid clinic"],
            missing_facts=["strike notice", "upload date", "original files/proof of authorship", "claimant details", "platform appeal status", "monetary/channel impact"],
            red_flags=_red_flags(q),
            action_pack=_copyright_takedown_pack(),
        )

    if _is_software_copyright_license_issue(q):
        return MatterRoute(
            category="trademark_ip",
            label="Software copyright / licence notice",
            confidence=0.80,
            urgency="high" if _has_any(q, ("notice", "legal notice", "raid", "audit", "court")) else "medium",
            required_sources=[
                "Copyright Act 1957 infringement, exceptions/fair dealing, and civil remedies",
                "software licence, invoice, audit notice, and seat-use records",
                "Trade Marks Act 1999 only if the dispute is about brand/logo/passing-off",
            ],
            forums=["vendor/licensor notice reply channel", "commercial/civil court where needed", "IP lawyer or District Legal Services Authority"],
            missing_facts=["software/product name", "licence count or seat count", "notice date", "audit report/screenshots", "invoice/subscription records", "user/device list", "vendor settlement demand"],
            red_flags=_red_flags(q),
            action_pack=_software_license_pack(),
        )

    if _has_any(q, _TRADEMARK_WORDS) and not _has_negated_trademark_context(q):
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

    if _is_company_strikeoff_restore_issue(q):
        return MatterRoute(
            category="ibc_nclt",
            label="Company strike-off / restoration",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Companies Act 2013 strike-off and restoration provisions",
                "NCLT/Registrar of Companies route for restoration",
                "GST refund/bank operation records only after company status is addressed",
            ],
            forums=["Registrar of Companies", "NCLT", "company secretary / legal-aid clinic", "GST portal only for refund follow-up after restoration"],
            missing_facts=["CIN/company name", "strike-off notice/order date", "reason for restoration", "pending returns/financials", "bank/GST refund record"],
            red_flags=[],
            action_pack=_ibc_pack(),
        )

    if _is_nclat_appeal_issue(q):
        return MatterRoute(
            category="ibc_nclt",
            label="NCLAT appeal / tribunal-order challenge",
            confidence=0.78,
            urgency="high" if _has_any(q, ("limitation", "days", "deadline", "urgent")) else "medium",
            required_sources=[
                "IBC 2016 section 61 where the order is an NCLT insolvency order",
                "Companies Act 2013 / NCLAT procedure where the order is a company-law tribunal order",
                "NCLAT rules, forms, fees, certified-copy and limitation facts",
            ],
            forums=["National Company Law Appellate Tribunal", "NCLT registry for certified copy/record", "company/IBC lawyer or legal-aid clinic"],
            missing_facts=["tribunal name", "order date", "case type", "certified-copy date", "whether it is IBC or Companies Act matter", "appeal deadline/condonation facts"],
            red_flags=[],
            action_pack=_ibc_pack(),
        )

    non_gst_tax_context = _has_non_gst_tax_context(q)
    if (
        (_has_any(q, _TAX_GST_WORDS) and (non_gst_tax_context or not _negates_gst_without_tax_facts(q)))
        or _has_any(q, _CUSTOMS_TAX_WORDS)
        or _has_any(q, _INCOME_TAX_APPEAL_WORDS)
        or non_gst_tax_context
    ):
        return MatterRoute(
            category="tax_gst_compliance",
            label="Tax / GST / TDS compliance",
            confidence=0.76,
            urgency="medium",
            required_sources=_tax_required_sources(q),
            forums=["GST portal/help desk", "Income Tax portal / ITAT where appeal is involved", "ICEGATE / customs officer or customs appellate route", "tax professional/legal-aid clinic for notices"],
            missing_facts=["state", "turnover/income amount", "nature of service/business/import/export", "notice/order or form number", "tax period and appeal deadline"],
            red_flags=[],
            action_pack=_tax_pack(),
        )

    if _is_motor_accident_claim_issue(q):
        return MatterRoute(
            category="motor_accident_claims",
            label="Motor accident / third-party claim",
            confidence=0.76,
            urgency="high" if _has_any(q, ("injury", "hospital", "dead", "death")) else "medium",
            required_sources=[
                "Motor Vehicles Act 1988 insurance and Claims Tribunal provisions",
                "police accident record/FIR and medical records",
                "insurance policy terms for third-party coverage",
            ],
            forums=["Motor Accident Claims Tribunal", "traffic/local police", "insurer claims office", "District Legal Services Authority"],
            missing_facts=["accident date/place", "vehicle and policy details", "injury/medical papers", "police accident record", "claim notice or demand amount"],
            red_flags=_red_flags(q),
            action_pack=_court_procedure_pack(),
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

    if _is_cattle_transport_accused_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="State cattle / animal-transport accused procedure",
            confidence=0.78,
            urgency="high" if _has_any(q, ("arrest", "arrested", "custody", "jail", "bail")) else "medium",
            required_sources=[
                "state Cattle Preservation / Animal Preservation Act based on state and FIR/seizure memo sections",
                "Prevention of Cruelty to Animals Act 1960 or animal-transport rules where animal-cruelty or transport conditions are alleged",
                "BNSS 2023 / CrPC 1973 arrest, remand, seizure, and bail procedure based on incident date",
            ],
            forums=["criminal court / bail court", "police station or investigating officer for FIR and seizure papers", "District Legal Services Authority"],
            missing_facts=[
                "state and police station",
                "FIR or seizure-memo sections",
                "animal species and ownership papers",
                "transport permit/mandi or veterinary documents",
                "arrest/remand/bail status",
                "incident date",
            ],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _has_any(q, _IBC_WORDS):
        ppirp_context = _has_any(q, ("pre pack", "pre-pack", "prepack", "pre packaged", "pre-packaged", "ppirp", "own company"))
        return MatterRoute(
            category="ibc_nclt",
            label="IBC / NCLT insolvency",
            confidence=0.80,
            urgency="medium",
            required_sources=(
                [
                    "Insolvency and Bankruptcy Code 2016",
                    "Insolvency and Bankruptcy (Pre-Packaged Insolvency Resolution Process) Rules 2021 / Form 1 where PPIRP filing process is asked",
                    "Companies Act where company records matter",
                ]
                if ppirp_context
                else ["Insolvency and Bankruptcy Code 2016", "NCLT Rules / IBC application forms", "Companies Act where company records matter"]
            ),
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

    if _is_obvious_consumer_goods_issue(q):
        return MatterRoute(
            category="consumer",
            label="Consumer complaint / defective goods or warranty service",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Consumer Protection Act 2019 for product defect, warranty, repair, return, refund, or service deficiency",
                "invoice/warranty card/order ID/service-centre record and written seller/service-provider response",
                "e-Daakhil / District Consumer Commission route if the seller or service centre does not resolve it",
            ],
            forums=["seller/service-provider grievance desk", "National Consumer Helpline", "District Consumer Disputes Redressal Commission", "e-Daakhil"],
            missing_facts=["purchase date", "invoice/order ID", "warranty terms", "defect/repair facts", "written complaint history"],
            red_flags=_red_flags(q),
            action_pack=_consumer_pack(),
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

    if _is_municipal_shop_sealing_issue(q):
        return MatterRoute(
            category="business_license_compliance",
            label="Municipal sealing / shop closure notice",
            confidence=0.80,
            urgency="high",
            required_sources=[
                "state municipal corporation/municipality law and trade-licence by-laws for sealing or closure power",
                "state Shops and Establishments / trade-licence rules where shop registration is involved",
                "Right to Information Act 2005 for order copy, inspection file, status, and reasons if not supplied",
            ],
            forums=["municipal ward/licensing office", "Municipal Commissioner or appellate authority named in the order", "local court/High Court only after checking the written order", "District Legal Services Authority"],
            missing_facts=["city/municipality", "sealing order or notice date", "reason stated for sealing", "shop/trade licence or registration", "ownership/lease papers", "hearing/appeal date if any"],
            red_flags=_red_flags(q),
            action_pack=_municipal_shop_sealing_pack(),
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

    if _is_private_magistrate_complaint_issue(q):
        return MatterRoute(
            category="court_procedure",
            label="Private complaint / Magistrate police-inaction procedure",
            confidence=0.82,
        urgency="medium",
        required_sources=[
            "BNSS 2023 / CrPC 1973 private complaint and Magistrate investigation procedure based on incident date",
        ],
            forums=["Judicial Magistrate", "police station", "District Legal Services Authority", "lawyer/legal-aid clinic"],
            missing_facts=["incident date", "offence facts", "prior police complaint and acknowledgement", "police refusal/inaction proof", "witnesses and documents"],
            red_flags=_red_flags(q),
            action_pack=_court_procedure_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_police_fir_inaction_issue(q):
        return _police_fir_inaction_route(q)

    if _is_lgbtq_identity_arrest_issue(q):
        return MatterRoute(
            category="arrest_custody_safeguard",
            label="LGBTQ identity arrest / custody safeguard",
            confidence=0.86,
            urgency="emergency",
            required_sources=[
                "Navtej Singh Johar v Union of India on consensual adult same-sex conduct and sexual orientation",
                "constitutional liberty safeguards under Articles 21 and 22",
                "BNSS 2023 / CrPC 1973 arrest, FIR, remand, and bail procedure based on incident date",
            ],
            forums=["nearest Magistrate/criminal court", "District Legal Services Authority", "senior police officer", "High Court writ jurisdiction for unlawful detention"],
            missing_facts=["age of the arrested person", "FIR/offence sections", "arrest date/time and police station", "whether family was informed", "whether produced before Magistrate", "whether any non-consent/minor/public-place allegation is made"],
            red_flags=_red_flags(q),
            action_pack=_custody_safeguard_pack(),
            legal_regime=_criminal_regime(q),
        )

    negated_custody_police_complaint = _has_any(q, (
        "no police custody", "no custody", "no detention", "not detained",
        "not arrested", "nobody was detained", "nobody detained",
    )) and _is_police_fir_inaction_issue(q)
    if _has_any(q, _BAIL_WORDS) and not negated_custody_police_complaint:
        required_sources = ["BNSS 2023 / CrPC 1973 bail provisions based on incident date"]
        if _has_uapa_context(q):
            required_sources.append("Unlawful Activities (Prevention) Act 1967 section 43D / 43D(5) bail restrictions and prolonged-incarceration/default-bail rules")
        required_sources.append("BNS 2023 / IPC 1860 offence provisions where relevant")
        return MatterRoute(
            category="criminal_defence_bail",
            label="Bail / criminal defence",
            confidence=0.80,
            urgency="high",
            required_sources=required_sources,
            forums=["criminal court", "legal aid/lawyer", "police station only for notices/complaints"],
            missing_facts=["incident date", "FIR/offence sections", "arrest status", "court stage", "notice/order copies"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_simple_hurt_accused_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Simple hurt / assault accused defence",
            confidence=0.76,
            urgency="high" if _has_any(q, ("arrest", "notice", "police called")) else "medium",
            required_sources=["BNS 2023 / IPC 1860 hurt and assault provisions based on incident date", "BNSS 2023 / CrPC 1973 arrest and notice procedure based on incident date"],
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

    if _is_witch_branding_violence(q) and _has_scst_protected_status(q):
        return MatterRoute(
            category="tribal_caste_atrocity",
            label="Caste / tribal witch-branding violence",
            confidence=0.84,
            urgency="emergency" if _has_any(q, ("beaten", "beat", "attack", "mob", "burn", "threat")) else "high",
            required_sources=[
                "SC/ST (Prevention of Atrocities) Act 1989 where caste or tribal status is part of the targeting",
                "BNS/BNSS or IPC/CrPC based on incident date for assault, intimidation, and police-refusal procedure",
                "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given",
            ],
            forums=["police station", "Superintendent of Police", "Special Court where SC/ST POA facts apply", "District Legal Services Authority"],
            missing_facts=["state/district", "victim SC/ST/community status proof", "incident date/place", "injury/medical proof", "police refusal proof"],
            red_flags=_red_flags(q),
            action_pack=_tribal_caste_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_police_fir_inaction_issue(q) or _has_any(q, ("fir",)) or (_has_any(q, ("police refused", "police not", "thana", "station")) and _has_any(q, _CRIME_WORDS)):
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

    if _is_silicosis_quarry_issue(q):
        return MatterRoute(
            category="workplace_injury_compensation",
            label="Occupational disease / quarry silicosis compensation",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Employees Compensation Act 1923 occupational-disease and claim provisions",
                "Factories Act 1948 or mine/workplace safety source where the inspected worksite facts support it",
                "state medical-board or silicosis welfare scheme procedure only for diagnosis/certificate and local benefit filing",
            ],
            forums=["Employees Compensation Commissioner", "Labour Commissioner", "medical board / silicosis scheme desk where available", "District Legal Services Authority"],
            missing_facts=["state/city and quarry location", "diagnosis or medical-board papers", "employer/contractor details", "dust-exposure work history", "wage proof", "co-worker/death details"],
            red_flags=_red_flags(q),
            action_pack=_work_injury_pack(),
        )

    if _is_work_injury(q):
        return MatterRoute(
            category="workplace_injury_compensation",
            label="Workplace injury / compensation",
            confidence=0.76,
            urgency="high",
            required_sources=["Employees Compensation Act 1923", "BOCW Act 1996 / Factories Act 1948 where applicable"],
            forums=["Labour Commissioner", "Employees Compensation Commissioner", "BOCW welfare board", "District Legal Services Authority"],
            missing_facts=["state/city", "employment/contractor details", "accident date", "medical papers", "wage proof"],
            red_flags=_red_flags(q),
            action_pack=_work_injury_pack(),
        )

    scheme_worker_payment = _is_scheme_worker_payment_issue(q)
    mgnrega_public_work = _is_mgnrega_job_card_or_wage_issue(q) or _is_mgnrega_social_audit_issue(q)
    industrial_dispute_reference = _has_any(q, ("industrial dispute", "industrial disputes", "section 10", "sec 10", "labour court", "labor court", "conciliation", "reference pending"))
    if scheme_worker_payment or (_is_labour_exploitation_issue(q) and not _is_pf_contribution_default_issue(q)):
        scheme_worker_category = "employment_wages" if scheme_worker_payment else "labour_exploitation_discrimination"
        return MatterRoute(
            category=scheme_worker_category,
            label=(
                "Anganwadi honorarium / ICDS payment"
                if _is_anganwadi_payment_issue(q)
                else "ASHA incentive / NHM payment"
                if _is_asha_payment_issue(q)
                else "Industrial dispute / labour-court reference"
                if industrial_dispute_reference
                else "Labour exploitation / discrimination"
            ),
            confidence=0.76,
            urgency="high" if _has_any(q, ("passport", "cards passport", "bonded", "chains")) else "medium",
            required_sources=(
                [
                    "state ICDS/Women and Child Development Anganwadi honorarium order or circular",
                    "CDPO/District Programme Officer payment ledger and sanction records",
                    "RTI/public grievance route for payment status if no written reason is given",
                ]
                if _is_anganwadi_payment_issue(q)
                else ["NHM/ASHA incentive guidelines for the state/scheme", "RTI/public grievance route for payment status and sanction records", "Legal Services Authorities Act for DLSA assistance"]
                if _is_asha_payment_issue(q)
                else [
                    "MGNREGA 2005 wage, job-card, grievance and social-audit provisions",
                    "Right to Information Act 2005 where payment, muster, or action-taken records are needed",
                    "BNS/Prevention of Corruption Act where forged muster, fake job cards, bribe, or misappropriation facts exist",
                ]
                if mgnrega_public_work
                else [
                    "Industrial Disputes Act 1947 Section 10/reference and conciliation provisions",
                    "Legal Services Authorities Act 1987 for legal-aid/DLSA assistance",
                    "Code on Wages / Payment of Wages law only where wage dues are also claimed",
                ]
                if industrial_dispute_reference
                else ["Code on Wages / Payment of Wages law", "Bonded Labour System (Abolition) Act 1976 where coercion or document retention applies", "Equal Remuneration / anti-discrimination protections where applicable", "MGNREGA/state scheme rules where public work applies"]
            ),
            forums=(
                ["CDPO / Child Development Project Office", "District Programme Officer / Women and Child Development department", "district grievance/public grievance office", "District Legal Services Authority"]
                if _is_anganwadi_payment_issue(q)
                else ["ASHA facilitator / PHC or block medical officer", "district health society / NHM office", "state health grievance channel where available", "District Legal Services Authority"]
                if _is_asha_payment_issue(q)
                else ["Programme Officer/BDO", "district MGNREGA grievance authority or Ombudsman", "Gram Sabha/social-audit forum", "District Legal Services Authority"]
                if mgnrega_public_work
                else ["Conciliation Officer / Labour Commissioner", "Labour Court or Industrial Tribunal after reference", "District Legal Services Authority"]
                if industrial_dispute_reference
                else ["Labour Commissioner", "DLSA", "MGNREGA grievance authority where applicable", "police where coercion/document retention occurs"]
            ),
            missing_facts=(
                ["state/district/block", "worker role", "scheme or duty period", "incentive/honorarium amount", "attendance/work records", "bank statement and prior complaint"]
                if scheme_worker_payment
                else ["state/district and gram panchayat", "job card/work-demand/work ID", "muster/FTO/payment record", "bank/passbook entry", "complaints already filed"]
                if mgnrega_public_work
                else ["state", "employer/establishment", "workman status", "termination/service facts", "conciliation/reference status", "orders/notices already received"]
                if industrial_dispute_reference
                else ["state/district", "employer/contractor", "wage amount", "dates worked", "documents retained or threats if any"]
            ),
            red_flags=_red_flags(q),
            action_pack=_labour_exploitation_pack(),
        )

    if _is_civil_procedure_issue(q):
        return MatterRoute(
            category="court_procedure",
            label="Civil court procedure / appeal / execution",
            confidence=0.78,
            urgency="medium",
            required_sources=["Code of Civil Procedure 1908 (CPC)", "Limitation Act 1963 where delay or appeal time is involved", "court rules and practice directions for the relevant court"],
            forums=["civil court / High Court filing counter", "District Legal Services Authority", "lawyer/legal-aid clinic"],
            missing_facts=["court and case number", "decree/order date", "appeal or execution stage", "limitation/deadline date", "copies of judgment, decree, or order"],
            red_flags=[],
            action_pack=_court_procedure_pack(),
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

    if _is_insurance_claim_dispute(q):
        return MatterRoute(
            category="consumer",
            label="Insurance claim / service deficiency",
            confidence=0.78,
            urgency="medium",
            required_sources=["Consumer Protection Act 2019", "Insurance Ombudsman Rules / insurer grievance procedure"],
            forums=["insurer grievance officer", "Insurance Ombudsman", "District Consumer Disputes Redressal Commission", "e-Daakhil"],
            missing_facts=["policy number", "claim number", "loss/fire date", "surveyor report", "repudiation or delay letter", "written insurer grievance"],
            red_flags=_red_flags(q),
            action_pack=_consumer_pack(),
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

    if _is_mutual_divorce_issue(q):
        return MatterRoute(
            category="family_marriage_status",
            label="Mutual consent divorce / family-court procedure",
            confidence=0.84,
            urgency="medium",
            required_sources=[
                "Hindu Marriage Act 1955 section 13B or applicable personal/Special Marriage Act mutual-consent divorce source",
                "Family Courts Act 1984 for matrimonial jurisdiction",
                "personal law and local filing rules based on religion, marriage form, and Family Court practice",
            ],
            forums=["Family Court", "District Legal Services Authority", "family-law lawyer/legal-aid desk"],
            missing_facts=["religion/personal law or Special Marriage Act registration", "marriage date", "separation/cooling-off facts", "children, maintenance, alimony, and property settlement terms", "current district and address proof"],
            red_flags=[],
            action_pack=_marriage_breakdown_pack(),
            legal_regime=None,
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

    if _is_spouse_civil_property_or_maintenance_issue(q):
        required_sources = [
            "personal marriage law based on religion and form of marriage",
            "Hindu Marriage Act 1955 / Special Marriage Act 1954 maintenance or matrimonial-relief provisions where applicable",
            "Family Courts Act 1984 for family-court jurisdiction",
            "property title and civil-court route where ownership/title is disputed",
        ]
        if _is_spousal_economic_support_issue(q):
            required_sources.append(
                "PWDVA 2005 economic-abuse / monetary-relief route where household expenses, support, residence, or shared-household facts are involved"
            )
        return MatterRoute(
            category="family_marriage_status",
            label="Matrimonial property / maintenance response",
            confidence=0.76,
            urgency="medium",
            required_sources=required_sources,
            forums=["Family Court", "District Legal Services Authority", "family-law lawyer/legal-aid desk", "civil court where title is directly disputed"],
            missing_facts=["religion/personal law or Special Marriage Act registration", "marriage date", "pending divorce/maintenance case status", "whose name the property is in", "income and dependants", "what notice or petition has been received"],
            red_flags=[],
            action_pack=_marriage_breakdown_pack(),
            legal_regime=None,
        )

    if _is_domestic_residence_issue(q):
        return _domestic_residence_route(q)

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

    if _is_family_court_summons_issue(q):
        return MatterRoute(
            category="court_procedure",
            label="Family-court summons / appearance preparation",
            confidence=0.80,
            urgency="high" if _has_any(q, ("urgent", "today", "tomorrow", "next date")) else "medium",
            required_sources=[
                "Family Courts Act 1984 for family-court jurisdiction",
                "Code of Civil Procedure 1908 summons/appearance procedure where applicable",
                "Legal Services Authorities Act 1987 where help is needed",
            ],
            forums=["Family Court help desk/registry", "District Legal Services Authority", "family-law lawyer/legal-aid clinic"],
            missing_facts=["case number", "next hearing date", "petition/relief claimed", "whether reply or personal appearance is directed"],
            red_flags=[],
            action_pack=_court_procedure_pack(),
        )

    if _is_family_domestic_notice_response_issue(q):
        return _family_domestic_notice_response_route(q)

    streedhan_return = _is_streedhan_return_issue(q)
    if _is_family_safety_issue(q) or _is_family_support_issue(q) or streedhan_return or _has_any(q, (
        "domestic violence", "husband beat", "husband is beating",
        "husband threatens", "husband threatened", "husband threatening",
        "slaps me", "slapped me", "hit me", "dowry", "in laws", "in-laws",
        "streedhan", "stridhan", "jewellery", "maintenance", "divorce", "custody",
    )):
        disabled_child_abandonment = _is_disabled_child_abandonment_issue(q)
        return MatterRoute(
            category="family_domestic",
            label=(
                "Disabled child abandonment / family safety"
                if disabled_child_abandonment
                else "Streedhan / family jewellery return"
                if streedhan_return
                else "Family / domestic violence / maintenance"
            ),
            confidence=0.74,
            urgency="emergency" if _is_family_safety_issue(q) or _has_any(q, (
                "beating", "violence", "food", "locked", "threat", "threatens",
                "threatened", "threatening",
            )) else "high",
            required_sources=(
                [
                    "Rights of Persons with Disabilities Act 2016 disability protection where disability is the reason for abandonment pressure",
                    "Juvenile Justice Act 2015 child-in-need-of-care / Child Welfare Committee route where a baby may be abandoned",
                    "BNS 2023 / IPC 1860 threat, cruelty, or abandonment provisions only if the exact facts and incident date fit",
                    "PWDVA 2005 protection route where in-laws or spouse are pressuring or threatening the mother",
                ]
                if disabled_child_abandonment
                else [
                    "PWDVA 2005 economic-abuse / streedhan return route where domestic relationship facts fit",
                    "Dowry Prohibition Act 1961 for dowry or marriage-gift return facts where applicable",
                    "BNS 2023 / IPC 1860 breach of trust, cheating, or theft provisions only after incident date and entrustment facts are verified",
                ]
                if streedhan_return
                else ["PWDVA 2005", "family law statute by religion", "BNSS/CrPC maintenance provisions where applicable"]
            ),
            forums=(
                ["Child Welfare Committee", "hospital social worker / Childline where available", "Protection Officer", "Magistrate court", "District Legal Services Authority", "police for immediate danger"]
                if disabled_child_abandonment
                else ["Protection Officer", "Magistrate court under PWDVA", "police station if breach of trust/threat facts fit", "Family Court/DLSA for linked matrimonial relief"]
                if streedhan_return
                else ["Protection Officer", "Magistrate court", "Family Court", "District Legal Services Authority"]
            ),
            missing_facts=(
                ["child age/medical condition", "hospital papers", "who is pressuring abandonment", "messages/threats", "current safety", "incident date if any threat or force occurred"]
                if disabled_child_abandonment
                else ["marriage/separation facts", "list and ownership proof of gold/jewellery", "who kept it and when", "messages demanding return", "locker/key details", "current safety and police/PWDVA complaint status"]
                if streedhan_return
                else ["religion/personal law context", "marriage date", "children", "current safety", "income and residence details"]
            ),
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
            legal_regime=_criminal_regime(q) if (_has_any(q, _CRIME_WORDS) or disabled_child_abandonment) else None,
        )

    if _is_succession_issue(q):
        return _succession_route(q)

    if _is_contract_labour_wage_issue(q) and not _is_pf_contribution_default_issue(q):
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

    if _is_pf_contribution_default_issue(q):
        pf_sources = [
            "Employees Provident Funds and Miscellaneous Provisions Act 1952 for employer contribution default and EPFO recovery",
            "Code on Social Security 2020 where current social-security coverage framing is relevant",
        ]
        if _has_any(q, ("contractor", "thekedar", "contract labour", "contract labor", "principal employer", "labour", "labor", "workers", "workmen")):
            pf_sources.append(
                "Contract Labour (Regulation and Abolition) Act 1970 where contractor/principal-employer wage records or site responsibility matter"
            )
        return MatterRoute(
            category="employment_wages",
            label="PF / EPFO contribution default",
            confidence=0.82,
            urgency="high" if _has_any(q, ("8 months", "many months", "urgent", "closed", "shut down", "left job")) else "medium",
            required_sources=pf_sources,
            forums=["EPFO grievance portal", "Regional Provident Fund Office / RPFO", "Labour Commissioner for connected wage dues", "District Legal Services Authority"],
            missing_facts=["UAN/member ID", "EPFO passbook entries", "salary slips showing PF deduction", "employer establishment name/code", "employment dates and amount deducted"],
            red_flags=_red_flags(q),
            action_pack=_employment_pack(),
        )

    if _has_any(q, (
        "salary", "wages", "gratuity", "pf", "epf", "maternity",
        "maternity leave", "pregnant", "pregnancy",
        "provident fund", "uan", "epfo", "pf passbook", "uan passbook",
        "passbook empty", "passbook has zero", "passbook shows zero", "salary slip deduction",
        "payslip", "never deposited", "employer contribution",
        "termination", "terminated", "fired", "resign", "resigned",
        "resignation", "asked me to resign", "overtime",
        "retrench", "retrenched", "retrenchment", "layoff", "lay off",
        "notice period", "offer letter", "full and final", "final settlement",
        "settlement dues", "employment contract", "joining letter",
        "company kept my original", "employer kept my original",
        "kept my original degree", "original degree certificate",
        "degree certificate after", "documents after resignation",
        "minimum wage", "minimum wages", "unpaid", "not paid",
        "not paying salary", "salary not paid", "wages not paid",
        "pip", "performance improvement plan", "bad rating", "hr complaint",
        "complained to hr", "manager harassment", "workplace harassment",
        "retaliation",
    )):
        notice_period_only = (
            _has_any(q, ("notice period", "serve 90", "90 day", "90 days", "60 day", "60 days", "offer letter", "appointment letter"))
            and not _has_any(q, (
                "salary not paid", "wages not paid", "not paid salary", "not paying salary",
                "unpaid", "full and final", "final settlement", "settlement dues",
                "termination", "terminated", "fired", "retrench", "retrenched",
                "pf", "epf", "maternity", "gratuity", "overtime",
            ))
        )
        if notice_period_only:
            required_sources = [
                "Indian Contract Act 1872 / appointment letter or service-rule clause for notice-period term",
                "Industrial Disputes Act only if termination, retrenchment, workman status, or industrial dispute is involved",
                "Code on Wages only if salary, full-and-final, leave encashment, or wage dues are withheld",
            ]
        elif _is_gratuity_delay_issue(q) or _is_gratuity_eligibility_issue(q):
            required_sources = [
                "Payment of Gratuity Act 1972",
                "Employees Provident Funds and Miscellaneous Provisions Act 1952 only if PF/EPF account, trust, or contribution facts are also involved",
            ]
        elif _is_wage_waiver_language_issue(q):
            required_sources = [
                "Code on Wages 2019 / Payment of Wages law for wage-rights, wage-authority, and claims",
                "Indian Contract Act 1872 only if consent, coercion, fraud, language, or misrepresentation in the signed paper is disputed",
                "Industrial Disputes Act only if termination, retrenchment, workman status, or industrial dispute is involved",
            ]
        else:
            pf_or_uan_context = _has_any(q, ("pf", "epf", "provident", "uan", "pf passbook", "epfo"))
            maternity_context = _has_any(q, ("maternity", "maternity leave", "pregnant", "pregnancy"))
            termination_context = _has_any(q, (
                "termination", "terminated", "fired", "resign", "resigned",
                "forced resign", "forced resignation", "forced me to resign", "asked me to resign", "retrench", "retrenched",
                "retrenchment", "layoff", "lay off", "pip", "bad rating",
                "retaliation",
            ))
            wage_due_context = _has_any(q, (
                "salary", "wage", "wages", "unpaid", "not paid",
                "not paying", "full and final", "final settlement",
                "overtime", "minimum wage", "deducted", "deduction",
            ))
            if pf_or_uan_context and not (termination_context or wage_due_context or maternity_context):
                required_sources = [
                    "Employees Provident Funds and Miscellaneous Provisions Act 1952 for PF/UAN account, contribution, or withdrawal issues",
                    "Code on Social Security 2020 where current social-security coverage framing is relevant",
                    "Code on Wages only if salary, full-and-final, leave encashment, or wage dues are withheld",
                    "Industrial Disputes Act only if termination, retrenchment, workman status, or industrial dispute is involved",
                ]
            elif maternity_context and not termination_context:
                required_sources = [
                    "Maternity Benefit Act 1961 for maternity leave, benefit, dismissal, or role-change facts",
                    "Code on Wages only if salary, full-and-final, leave encashment, or wage dues are withheld",
                    "Industrial Disputes Act only if termination, retrenchment, workman status, or industrial dispute is involved",
                ]
            elif wage_due_context and not termination_context:
                required_sources = [
                    "Code on Wages 2019 / Payment of Wages law for wage-rights, wage-authority, and claims",
                    "Industrial Disputes Act only if termination, retrenchment, workman status, or industrial dispute is involved",
                    "Maternity Benefit Act / EPF Act only where maternity or PF/EPF facts are involved",
                ]
            elif termination_context and wage_due_context:
                required_sources = [
                    "Code on Wages 2019 / Payment of Wages law for withheld salary, full-and-final, leave encashment, or wage dues",
                    "Industrial Disputes Act for termination, retrenchment, workman status, or industrial dispute",
                    "Maternity Benefit Act / EPF Act only where maternity or PF/EPF facts are involved",
                ]
            elif termination_context:
                required_sources = [
                    "Industrial Disputes Act for termination, retrenchment, workman status, or industrial dispute",
                    "Code on Wages only if salary, full-and-final, leave encashment, or wage dues are withheld",
                    "Maternity Benefit Act / EPF Act only where maternity or PF/EPF facts are involved",
                ]
            else:
                required_sources = [
                    "Payment of Wages Act / Code on Wages",
                    "Industrial Disputes Act",
                    "Maternity Benefit Act / EPF Act where relevant",
                ]
        forums = (
            ["Employer/HR written clarification", "labour office only if wage dues or termination facts are involved", "District Legal Services Authority"]
            if notice_period_only
            else ["Labour Commissioner", "wage authority", "EPFO grievance portal", "District Legal Services Authority"]
        )
        return MatterRoute(
            category="employment_wages",
            label="Employment / wages",
            confidence=0.74,
            urgency="medium",
            required_sources=required_sources,
            forums=forums,
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

    prison_release_or_access = _prison_release_or_access_route(q)
    if prison_release_or_access is not None:
        return prison_release_or_access

    if _has_any(q, _EDUCATION_WORDS) and not _is_juvenile_age_custody_issue(q):
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

    if _has_any(q, _LAND_RECORD_WORDS):
        if _has_any(q, ("pattadar", "passbook", "pass book", "title deed cum passbook", "bhudhaar", "bhu dhaar", "record of rights", "ror")):
            land_required_sources = [
                "Andhra Pradesh Rights in Land and Pattadar Pass Books Act 1971 / Record of Rights Act for pattadar/passbook",
                "Right to Information Act 2005 where delay or missing records are involved",
                "state land revenue / mutation rules based on state and application",
            ]
        elif _has_any(q, ("bribe", "asking 5000", "asking money", "patwari asking", "corruption", "rishwat", "ghoos")):
            land_required_sources = [
                "Prevention of Corruption Act 1988 for public-servant bribe demand",
                "Right to Information Act 2005 where delay or missing records are involved",
                "state land revenue / record-of-rights law based on state and mutation application",
            ]
        else:
            land_required_sources = [
                "state land revenue / record-of-rights law based on state and application",
                "state mutation and patta/passbook rules based on state and application",
                "Right to Information Act 2005 where delay or missing records are involved",
            ]
        return MatterRoute(
            category="land_revenue_records",
            label="Land records / revenue office",
            confidence=0.74,
            urgency="medium",
            required_sources=land_required_sources,
            forums=["tehsildar/taluk/revenue office", "revenue appellate authority", "District Legal Services Authority"],
            missing_facts=["state/district", "survey/khata/passbook number", "owner name", "loss/damage date", "applications already filed"],
            red_flags=_red_flags(q),
            action_pack=_land_records_pack(),
        )

    if _is_forest_notice_non_fra_issue(q):
        return MatterRoute(
            category="environment_compensation",
            label="Forest land notice / forest authority",
            confidence=0.76,
            urgency="high" if _has_any(q, ("evict", "remove", "demolish", "seize")) else "medium",
            required_sources=[
                "Forest Conservation Act 1980 where forest land or non-forest use is alleged",
                "state forest/revenue notice and appeal procedure based on the written notice",
                "Forest Rights Act only if long occupation, Gram Sabha/FRC, IFR/CFR, or forest-rights claim facts exist",
            ],
            forums=["forest department / range officer named in the notice", "District Forest Officer or Collector/appellate authority", "revenue authority where land record is disputed", "DLSA / District Legal Services Authority"],
            missing_facts=["state/district", "notice copy and section invoked", "forest compartment/survey details", "occupation start date", "whether FRA/IFR/CFR claim or patta exists"],
            red_flags=_red_flags(q),
            action_pack=_environment_pack(),
        )

    if _is_property_specific_performance_issue(q):
        return MatterRoute(
            category="property_tenancy",
            label="Land agreement / specific performance",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Specific Relief Act 1963 specific-performance or injunction provisions for enforcing the agreement",
                "Indian Contract Act 1872 for agreement, performance, breach, and compensation framing",
                "Transfer of Property Act 1882 only where transfer/title facts must be checked",
                "Registration Act only if a registered sale deed, document registration, or admissibility issue is disputed",
            ],
            forums=["civil court / commercial court depending on property and value", "mediation centre where settlement is possible", "District Legal Services Authority", "local property lawyer/legal-aid desk"],
            missing_facts=["agreement date", "advance/payment proof", "seller refusal messages/notices", "property description", "readiness and willingness facts", "registration/title status"],
            red_flags=[],
            action_pack=_property_pack(),
        )

    if _has_any(q, (
        "landlord", "tenant", "rent", "deposit", "lease", "property",
        "land", "ancestral", "sale deed", "gift deed", "possession",
        "house", "flat", "joint name", "plot",
    )):
        tenancy_context = _has_any(q, (
            "landlord", "tenant", "rent", "deposit", "lease", "evict",
            "eviction", "vacate", "not vacating", "locked out", "lockout",
            "threw me out",
        ))
        registration_document_context = _has_any(q, (
            "sale deed", "gift deed", "registered", "registration", "stamp",
            "verbally", "verbal", "orally", "oral gift", "gave land",
            "gave property", "transferred flat", "transferred land",
            "father transferred", "mother gave", "younger son", "older son",
        ))
        if tenancy_context and not registration_document_context:
            required_sources = [
                "Transfer of Property Act lease or notice provisions where the lease/notice route applies",
                "state rent/control law where applicable based on city and property type",
                "Registration Act only if lease/document registration or admissibility is disputed",
                "Limitation Act where needed",
            ]
        elif registration_document_context:
            required_sources = [
                "Transfer of Property Act",
                "Registration Act",
                "Hindu Succession Act / applicable personal succession law for heirship and shares",
                "Limitation Act where needed",
            ]
        else:
            required_sources = [
                "Transfer of Property Act",
                "Registration Act only if document registration or admissibility is disputed",
                "state rent/control law where applicable",
                "Limitation Act where needed",
            ]
        return MatterRoute(
            category="property_tenancy",
            label="Property / tenancy",
            confidence=0.70,
            urgency="medium",
            required_sources=required_sources,
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
        return _court_procedure_route(q)

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


def route_matter_trace(query: str, selected_route: MatterRoute | None = None) -> dict:
    """Diagnostics for route collisions without changing the selected route.

    The product path is still the deterministic router above. This trace makes
    high-risk false positives visible in evals and UI/API debugging so that a
    broad legacy branch cannot silently win over a nearby procedural route.
    """
    q = _norm(query)
    selected = selected_route or route_matter(query)
    candidates: list[dict] = []

    def add(name: str, route: MatterRoute | None, *, stage: str) -> None:
        if route is None:
            return
        candidates.append({
            "signal": name,
            "stage": stage,
            "category": route.category,
            "label": route.label,
            "confidence": route.confidence,
            "urgency": route.urgency,
        })

    add("civil_court_procedure", _civil_court_procedure_route(q), stage="early_guard")
    if _is_juvenile_age_custody_issue(q):
        add("juvenile_age_custody", _juvenile_age_custody_route(q), stage="high_risk")
    if _is_missing_person_police_complaint_issue(q):
        add("missing_person_police_complaint", _missing_person_police_complaint_route(q), stage="high_risk")
    if _is_interim_medical_bail_issue(q):
        add("custody_medical_care", _custody_medical_care_route(q), stage="high_risk")
    if _is_undertrial_review_issue(q):
        add("undertrial_review", _undertrial_review_route(q), stage="high_risk")
    if _is_custodial_violence_issue(q):
        add("custodial_violence", _custodial_violence_route(q), stage="high_risk")
    if _is_police_fir_inaction_issue(q):
        add("police_fir_inaction", _police_fir_inaction_route(q), stage="high_risk")
    if _is_bail_release_delay_issue(q):
        add("bail_release_delay", _bail_release_delay_route(q), stage="high_risk")
    if _is_custody_legal_aid_access_issue(q):
        add("custody_legal_aid_access", _custody_legal_aid_access_route(q), stage="high_risk")
    if _is_section_91_notice(q):
        add("production_notice", _production_notice_route(q), stage="high_risk")
    if _is_police_questioning_notice_issue(q):
        add("police_questioning_notice", _police_questioning_notice_route(q), stage="high_risk")
    add("prison_release_or_access", _prison_release_or_access_route(q), stage="pre_broad")

    if _is_legal_aid_eligibility_issue(q):
        add(
            "legal_aid_eligibility",
            MatterRoute(
                category="legal_aid",
                label="Legal aid eligibility / DLSA support",
                confidence=0.80,
                urgency="medium",
                required_sources=[],
                forums=[],
                missing_facts=[],
                red_flags=[],
                action_pack=_legal_aid_pack(),
            ),
            stage="broad",
        )
    if _has_any(q, (
        "landlord", "tenant", "rent", "deposit", "lease", "property",
        "land", "ancestral", "sale deed", "gift deed", "possession",
        "house", "flat", "joint name", "plot", "partition",
    )):
        add(
            "property_tenancy_broad",
            MatterRoute(
                category="property_tenancy",
                label="Property / tenancy",
                confidence=0.70,
                urgency="medium",
                required_sources=[],
                forums=[],
                missing_facts=[],
                red_flags=[],
                action_pack=_property_pack(),
            ),
            stage="broad",
        )
    legacy_fir_condition = _has_any(q, ("fir",)) or (
        _has_any(q, ("police refused", "police not", "thana", "station"))
        and _has_any(q, _CRIME_WORDS)
    )
    if legacy_fir_condition:
        add("legacy_fir_broad", _police_fir_inaction_route(q), stage="legacy_broad")
    if _has_any(q, _COURT_PROCEDURE_WORDS) or _has_any(q, _GOVT_COURT_PROCEDURE_WORDS) or _has_any(q, _CIVIL_PROCEDURE_WORDS):
        add("court_procedure_terms", _court_procedure_route(q), stage="broad")

    selected_key = (selected.category, selected.label)
    unique_keys = {(item["category"], item["label"]) for item in candidates}
    return {
        "selected": {
            "category": selected.category,
            "label": selected.label,
            "confidence": selected.confidence,
            "urgency": selected.urgency,
        },
        "candidate_count": len(candidates),
        "collision": len(unique_keys) > 1,
        "selected_in_candidates": selected_key in unique_keys,
        "candidates": candidates,
        "matched_terms": _route_trace_terms(q),
    }


def _specific_high_risk_surface_route(q: str) -> MatterRoute | None:
    if _is_minor_synthetic_sexual_image_issue(q):
        return MatterRoute(
            category="cyber_fraud_or_harassment",
            label="Minor sexual-image / AI CSAM cyber complaint",
            confidence=0.90,
            urgency="emergency",
            required_sources=[
                "POCSO Act 2012 where a child or minor is shown in sexual content",
                "Information Technology Act 2000 section 67B / 66E / 67A where electronic sexual-image publication or privacy misuse is alleged",
                "BNSS 2023 / CrPC 1973 FIR and complaint procedure based on incident date",
            ],
            forums=["National Cyber Crime Portal", "local cyber police station", "police station for FIR", "Childline/1098 or child-protection authority", "District Legal Services Authority"],
            missing_facts=["age/date of birth proof", "platform/group/app", "URLs/profile IDs", "screenshots and timestamps", "who made/shared it", "whether the child is safe now"],
            red_flags=["minor sexual image / CSAM risk", *_red_flags(q)],
            action_pack=_cyber_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_labour_chowk_police_begging_issue(q):
        return MatterRoute(
            category="police_fir",
            label="Labour chowk police pickup / wage-worker liberty complaint",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "BNSS 2023 / CrPC 1973 arrest and detention procedure based on incident date",
                "Article 21 and Article 22 liberty and arrest safeguards",
                "Code on Wages 2019 where the same facts include unpaid wage, attendance, or contractor payment dispute",
            ],
            forums=["police station/senior police officer", "Judicial Magistrate", "Labour Commissioner or wage authority", "District Legal Services Authority"],
            missing_facts=["date/time and police station", "whether anyone was detained or named in FIR", "contractor/employer details", "wage/attendance proof", "worker IDs", "witnesses and videos"],
            red_flags=_red_flags(q),
            action_pack=_fir_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_arms_act_farming_tool_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Arms Act / farming-tool criminal defence",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Arms Act 1959 definition/licensing/penalty source for alleged weapon or farming tool",
                "BNSS 2023 / CrPC 1973 arrest and notice procedure based on incident date",
            ],
            forums=["criminal court", "police station/investigating officer", "District Legal Services Authority"],
            missing_facts=["FIR sections", "incident date", "seizure memo", "tool description", "place/purpose", "arrest/notice status"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_medical_negligence_consumer_issue(q):
        return MatterRoute(
            category="consumer",
            label="Medical negligence / hospital service deficiency",
            confidence=0.84,
            urgency="high" if _has_any(q, ("death", "died", "wrong leg", "wrong limb", "wrong surgery", "wrong operation")) else "medium",
            required_sources=[
                "Consumer Protection Act 2019 for medical service deficiency and consumer-forum complaint",
                "hospital records, consent form, discharge summary, and independent medical opinion",
                "BNS/BNSS or IPC/CrPC only if criminal negligence, assault, or police FIR facts are actually alleged",
            ],
            forums=["hospital grievance desk", "District Consumer Disputes Redressal Commission", "State Medical Council where professional misconduct is alleged", "police only for clear criminal-negligence facts", "District Legal Services Authority"],
            missing_facts=["patient age and condition", "hospital/doctor name", "date of procedure/treatment", "what went wrong", "medical records and consent form", "bill/payment proof", "complaints already filed"],
            red_flags=_red_flags(q),
            action_pack=_consumer_pack(),
        )

    if _is_spousal_adultery_marriage_breakdown_issue(q):
        return MatterRoute(
            category="family_marriage_status",
            label="Marriage breakdown / adultery facts",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Hindu Marriage Act 1955 section 13 or applicable personal/Special Marriage Act divorce ground",
                "Family Courts Act 1984 for matrimonial jurisdiction",
                "criminal/domestic-violence law only if there is force, threat, assault, or economic abuse",
            ],
            forums=["Family Court", "District Legal Services Authority", "family-law lawyer/legal-aid desk", "safe counselling/mediation only if voluntary"],
            missing_facts=["religion/personal law or Special Marriage Act registration", "marriage date", "proof and how it was obtained", "children/maintenance/residence concerns", "whether there is violence or threat", "what remedy you want"],
            red_flags=_red_flags(q),
            action_pack=_marriage_breakdown_pack(),
        )

    if _is_personal_money_recovery_issue(q):
        return MatterRoute(
            category="business_contract_partnership",
            label="Personal loan / money recovery",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Indian Contract Act 1872 for agreement, performance, breach, and compensation framing",
                "Limitation Act 1963 for money-recovery limitation based on due date, last payment, or written acknowledgement",
                "Code of Civil Procedure 1908 / civil-court procedure for money suit; Negotiable Instruments Act 1881 only if a cheque was dishonoured",
            ],
            forums=["civil court / mediation centre", "District Legal Services Authority", "local lawyer/legal-aid desk", "police only if deception at inception, forgery, threats, or cheating facts are present"],
            missing_facts=["amount and date paid", "bank/UPI/cash proof", "loan agreement or messages acknowledging debt", "repayment due date", "last payment or acknowledgement", "whether cheque/security was issued"],
            red_flags=_red_flags(q),
            action_pack=_personal_money_recovery_pack(),
        )

    if _is_heir_property_sale_consent_issue(q):
        return MatterRoute(
            category="property_tenancy",
            label="Inherited property sale / heir consent",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Hindu Succession Act 1956 or applicable personal succession law to identify heirs and shares",
                "Transfer of Property Act 1882 for co-owner transfer of share/interest",
                "Specific Relief Act 1963 for declaration, injunction, or cancellation if a deed affects another heir's right",
            ],
            forums=["civil court", "sub-registrar/revenue office for deed and mutation records", "District Legal Services Authority", "local property lawyer/legal-aid desk"],
            missing_facts=["state/district", "whose name is on the title/mutation", "death certificate and family tree", "will or no will", "each heir's claimed share", "whether any heir has signed release/consent"],
            red_flags=[],
            action_pack=_property_pack(),
        )

    if _is_bank_debit_service_dispute(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Bank debit / RBI Ombudsman complaint",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "RBI Integrated Ombudsman Scheme for regulated-entity complaint route",
                "Consumer Protection Act 2019 where bank service deficiency is alleged",
                "bank statement, transaction reference, card/forex dispute record, and written bank grievance",
            ],
            forums=["bank grievance officer", "RBI Ombudsman", "consumer forum where needed", "District Legal Services Authority"],
            missing_facts=["bank name", "account/card details", "transaction date and amount", "forex/card network reference", "complaint number and bank reply", "whether OTP/phishing/scam facts exist"],
            red_flags=_red_flags(q),
            action_pack=_banking_credit_pack(),
        )

    if _is_false_loan_credit_record_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="False loan / credit-report correction",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "Credit Information Companies Act 2005 for disputed credit-report correction",
                "RBI Integrated Ombudsman Scheme for bank/NBFC/lender grievance escalation",
                "Information Technology Act / BNS and BNSS only where identity theft, electronic KYC misuse, forgery, or police complaint facts exist",
            ],
            forums=["bank/NBFC grievance officer", "credit bureau dispute channel", "RBI Ombudsman / CMS", "cyber police/local police where identity theft or forgery is alleged", "District Legal Services Authority"],
            missing_facts=["lender/NBFC name", "loan account shown in credit report", "PAN/Aadhaar/KYC misuse proof", "CIBIL/credit-report screenshot", "lender and bureau complaint numbers", "police/cyber complaint number if filed"],
            red_flags=_red_flags(q),
            action_pack=_banking_credit_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("forged", "forgery", "fake signature", "cyber", "police", "fir")) else None,
        )

    if _is_lender_reminder_or_recovery_service_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Lender reminder / recovery conduct",
            confidence=0.76,
            urgency="medium",
            required_sources=[
                "RBI Integrated Ombudsman Scheme for bank/NBFC/lender grievance escalation",
                "written lender reminder, repayment/default timeline, and complaint record",
                "BNS/BNSS only if threats, public shaming, extortion, violence, or police facts are alleged",
            ],
            forums=["lender grievance officer", "RBI Ombudsman where the lender/regulated entity is covered", "District Legal Services Authority", "police/cyber police only if threats or unlawful harassment are alleged"],
            missing_facts=["lender/NBFC name", "loan account", "due date and amount", "exact SMS/call text", "whether there were threats, public shaming, or repeated abusive calls", "written complaint number"],
            red_flags=_red_flags(q),
            action_pack=_banking_credit_pack(),
        )

    if _is_bank_account_freeze_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Bank account freeze / lien / KYC hold",
            confidence=0.80,
            urgency="high",
            required_sources=[
                "RBI Integrated Ombudsman Scheme for bank/NBFC grievance escalation",
                "Banking Regulation Act / regulated-entity records for bank account service issues",
                "police/cyber/ED/court order only if the bank says the freeze is due to a legal hold",
            ],
            forums=["bank branch/grievance officer", "RBI Ombudsman", "cyber police/local police only if a legal hold or fraud is stated", "District Legal Services Authority"],
            missing_facts=["bank name and branch", "account type/number suffix", "freeze/lien date", "written reason or SMS/email", "KYC status", "complaint number", "whether police/cyber/court/ED hold is mentioned"],
            red_flags=_red_flags(q),
            action_pack=_bank_account_freeze_pack(),
        )

    if _is_loan_app_harassment_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Loan-app / recovery harassment",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "RBI Integrated Ombudsman Scheme / RBI recovery-agent and digital-lending grievance route for regulated lenders",
                "Digital Personal Data Protection Act / Information Technology Act where contacts or phone data are misused",
                "BNS/BNSS or IPC/CrPC only where threats, extortion, obscene messages, or police complaint facts are alleged",
            ],
            forums=["lender or loan-app grievance officer", "RBI Ombudsman where the lender/RE is covered", "cyber police/local police for threats or contact-data abuse", "District Legal Services Authority"],
            missing_facts=["loan app/lender name", "amount and repayment status", "messages/call logs sent to contacts", "permissions/screenshots", "complaint number", "whether threats/extortion/private-image abuse occurred"],
            red_flags=_red_flags(q),
            action_pack=_loan_app_harassment_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_itpa_call_handling_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="ITPA call-handling / accused-risk clarification",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "Immoral Traffic (Prevention) Act 1956 sections 4, 5, 7, or 8 as applicable to the alleged facts",
                "BNSS 2023 / CrPC 1973 arrest, notice, statement, and bail procedure based on incident date",
                "phone records, chats, payment trail, and FIR/notice sections to identify witness versus accused status",
            ],
            forums=["police station/investigating officer for notice or FIR sections", "criminal court or legal-aid lawyer if accused or summoned", "District Legal Services Authority"],
            missing_facts=["FIR/notice sections", "whether arrested, summoned, or only questioned", "exact phone/chat/payment role alleged", "incident date", "next police/court date"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

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
                "platform contract/proof, strike policy, grievance record, and payout records",
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


def _early_precise_common_route(q: str) -> MatterRoute | None:
    """Common user workflows that must beat broad keyword buckets."""
    if _is_civil_registration_record_issue(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="Civil registration / identity record",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Registration of Births and Deaths Act 1969 or state civil-registration rules where locally available",
                "Right to Information Act 2005 for written status, reasons, and first appeal",
                "panchayat/municipal registrar procedure for delayed or home-birth/home-death registration",
            ],
            forums=[
                "Registrar of Births and Deaths / panchayat or municipal registrar",
                "block development or municipal office",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "state/district",
                "birth/death date and place",
                "hospital or home-event proof",
                "application/receipt number",
                "written refusal or delay reason",
            ],
            red_flags=_red_flags(q),
            action_pack=_social_welfare_pack(),
        )

    if _is_medical_negligence_consumer_issue(q):
        death_or_serious = _has_any(q, (
            "died", "death", "dead", "passed away", "wrong injection",
            "wrong surgery", "wrong operation", "icu", "serious",
        ))
        return MatterRoute(
            category="consumer",
            label="Medical negligence / hospital service deficiency",
            confidence=0.88,
            urgency="high" if death_or_serious else "medium",
            required_sources=[
                "Consumer Protection Act 2019 service-deficiency complaint provisions",
                "Medical Council / medical ethics record and professional-conduct rules where records or negligence are disputed",
                "Clinical Establishments Act / state clinical-establishment rules where hospital records, billing, or standards are involved",
                "BNS/BNSS or IPC/CrPC only as a separate criminal-negligence track where facts support it",
            ],
            forums=[
                "hospital grievance or medical superintendent first for records",
                "District Consumer Disputes Redressal Commission for compensation/refund",
                "State Medical Council / clinical-establishment authority where applicable",
                "police only for a separate criminal-negligence complaint after preserving medical records",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "hospital/doctor name and city",
                "treatment date and death/injury date",
                "prescription, injection chart, consent form, discharge summary, bills, and case papers",
                "death certificate or injury record",
                "written record request or hospital reply",
            ],
            red_flags=_red_flags(q),
            action_pack=_consumer_pack(),
        )

    if _is_army_service_pension_issue(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="Army service/family pension grievance",
            confidence=0.86,
            urgency="medium",
            required_sources=[
                "Pension Regulations for the Army 2008 family-pension and claims procedure",
                "Right to Information Act 2005 for pension-file status, deficiency notes, and action-taken records",
                "Legal Services Authorities Act 1987 for legal-aid help where the widow/family needs filing assistance",
            ],
            forums=[
                "Record Office / regiment pension channel",
                "Pension Disbursing Authority or PCDA defence pension channel",
                "Zila Sainik Board or district sainik welfare office",
                "District Legal Services Authority",
                "Armed Forces Tribunal or service-law counsel only after checking the written rejection/status",
            ],
            missing_facts=[
                "service number/regiment or PPO number",
                "death certificate",
                "marriage/family proof",
                "bank/passbook and KYC details",
                "last office reply, rejection, or pending-file status",
            ],
            red_flags=_red_flags(q),
            action_pack=_social_welfare_pack(),
        )

    if _is_decree_execution_issue(q):
        return MatterRoute(
            category="court_procedure",
            label="Civil decree execution / attachment",
            confidence=0.86,
            urgency="medium",
            required_sources=[
                "Code of Civil Procedure 1908 (CPC) section 51 and Order XXI execution procedure",
                "Limitation Act 1963 where delay in execution or appeal affects the route",
                "certified judgment, decree, and execution application papers",
            ],
            forums=[
                "executing civil court",
                "same court or transferred executing court depending on decree and property location",
                "District Legal Services Authority",
                "lawyer/legal-aid desk",
            ],
            missing_facts=[
                "court and case number",
                "judgment/decree date",
                "amount due and interest calculation",
                "judgment-debtor property, salary, bank, or asset details",
                "whether any appeal/stay is pending",
            ],
            red_flags=[],
            action_pack=_court_procedure_pack(),
        )

    if _is_trademark_marketplace_brand_issue(q):
        return MatterRoute(
            category="trademark_ip",
            label="Trademark / marketplace fake-products takedown",
            confidence=0.86,
            urgency="medium",
            required_sources=[
                "Trade Marks Act 1999 infringement, passing-off, and forum/remedy provisions",
                "platform IP/takedown ticket, seller listing, and counterfeit proof",
                "Commercial Courts Act / civil injunction route where business court relief is needed",
            ],
            forums=[
                "marketplace IP/takedown grievance channel",
                "commercial court/civil court for injunction, damages, or delivery-up",
                "Trade Marks Registry only for registration/opposition status questions",
                "IP lawyer or legal-aid clinic",
            ],
            missing_facts=[
                "trademark registration/application number and brand/logo proof",
                "seller ID, listing URLs, screenshots, and sample purchase/invoice",
                "takedown ticket numbers and replies",
                "proof of your brand use and customer confusion",
            ],
            red_flags=_red_flags(q),
            action_pack=_trademark_pack(),
        )

    if _is_employment_noncompete_contract_issue(q):
        return MatterRoute(
            category="employment_wages",
            label="Employment non-compete / contract restraint",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Indian Contract Act 1872 section 27 restraint-of-trade source for non-compete enforceability",
                "employment contract / offer letter clause and resignation or joining facts",
                "Specific Relief Act 1963 only if the employer seeks an injunction or negative-covenant relief",
            ],
            forums=[
                "civil/commercial court only if the employer sues or seeks injunction",
                "labour/employment lawyer or legal-aid desk for contract and workman-status review",
                "arbitration forum if the employment contract has an arbitration clause",
            ],
            missing_facts=[
                "exact non-compete/confidentiality clause",
                "employment role and seniority",
                "duration and geography of restriction",
                "whether confidential information or customer poaching is alleged",
                "notice/legal threat or case papers if any",
            ],
            red_flags=[],
            action_pack=_employment_pack(),
        )

    if _is_business_confidentiality_issue(q):
        return MatterRoute(
            category="business_contract_partnership",
            label="Business confidentiality / NDA / customer-list misuse",
            confidence=0.84,
            urgency="medium",
            required_sources=[
                "Indian Contract Act 1872 obligation, restraint-of-trade, and compensation provisions",
                "Specific Relief Act 1963 injunction provisions where misuse is continuing",
                "signed NDA/confidentiality clause, access logs, and client-contact proof",
            ],
            forums=[
                "civil/commercial court for injunction or damages",
                "arbitration forum if the contract has an arbitration clause",
                "lawyer/legal-aid clinic",
            ],
            missing_facts=[
                "signed NDA/confidentiality or employment agreement",
                "what customer data/list/pricing was accessed",
                "proof of copying, download, client contact, or poaching",
                "competitor/rival joining date",
                "arbitration/forum clause and loss calculation",
            ],
            red_flags=[],
            action_pack=_business_contract_pack(),
        )

    if _is_environment_pil_pollution_issue(q):
        return MatterRoute(
            category="environment_compensation",
            label="Pollution PIL / NGT / public environmental complaint",
            confidence=0.84,
            urgency="high" if _has_any(q, ("drinking water", "sick", "ill", "toxic", "chemical")) else "medium",
            required_sources=[
                "Water Act / Air Act and Pollution Control Board complaint route where factory pollution is alleged",
                "National Green Tribunal Act 2010 for environmental relief/compensation route",
                "Constitution Article 226 High Court PIL/writ route where public-law facts fit",
            ],
            forums=[
                "State Pollution Control Board / regional officer",
                "District Magistrate or local pollution authority for immediate inspection",
                "National Green Tribunal",
                "High Court Article 226 PIL/writ route where NGT is not the right forum",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "factory name and location",
                "pollution type: water, air, effluent, chemical, smoke, or waste",
                "photos/videos, test reports, medical symptoms, and affected people",
                "prior complaint number and authority reply",
            ],
            red_flags=_red_flags(q),
            action_pack=_environment_pack(),
        )

    if _is_municipal_garbage_nuisance_issue(q):
        return MatterRoute(
            category="business_license_compliance",
            label="Municipal nuisance / garbage complaint",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "municipal sanitation/solid-waste complaint procedure for the local body",
                "Right to Information Act 2005 for written complaint status, officer name, and action-taken report",
                "District Legal Services Authority where repeated no-action creates health or access risk",
            ],
            forums=[
                "municipal ward office or sanitation/solid-waste department",
                "municipal grievance portal/helpline where available",
                "Municipal Commissioner or zonal health/sanitation officer",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "city/municipality and ward",
                "dumping location and dates",
                "photos/videos and health/access impact",
                "complaint number and officer reply",
                "neighbour or property details if known",
            ],
            red_flags=[],
            action_pack=_business_license_pack(),
        )

    return None


def _priority_route(q: str) -> MatterRoute | None:
    """High-risk and high-conflict routes before the broad keyword chain."""
    if _is_street_vendor_municipal(q):
        return MatterRoute(
            category="street_vendor_municipal",
            label="Street vendor / municipal seizure",
            confidence=0.80,
            urgency="high" if _has_any(q, ("police took", "took my cart", "seized", "removed", "without notice")) else "medium",
            required_sources=["Street Vendors Act 2014", "municipal corporation / Town Vending Committee procedure"],
            forums=["Town Vending Committee", "municipal commissioner/ward office", "District Legal Services Authority"],
            missing_facts=["city", "certificate/survey status", "seizure memo or challan", "place and date", "goods/cart value", "officer or police details"],
            red_flags=_red_flags(q),
            action_pack=_street_vendor_pack(),
        )

    if _is_writ_constitution_procedure_issue(q):
        return MatterRoute(
            category="court_procedure",
            label="Writ / constitutional remedy procedure",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Constitution of India Article 226 for High Court writ jurisdiction",
                "Constitution of India Article 32 for Supreme Court fundamental-right enforcement where applicable",
                "Legal Services Authorities Act 1987 where filing help or legal aid is needed",
            ],
            forums=["High Court writ jurisdiction", "Supreme Court only for Article 32 fundamental-right enforcement", "District Legal Services Authority", "lawyer/legal-aid desk"],
            missing_facts=["which government authority/officer", "written order or refusal", "date of representation/complaint", "public duty or fundamental right involved", "state/city"],
            red_flags=[],
            action_pack=_writ_constitution_pack(),
        )

    if _is_accused_scst_false_poa_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="Accused-side SC/ST POA / false-case defence",
            confidence=0.84,
            urgency="high",
            required_sources=[
                "SC/ST (Prevention of Atrocities) Act 1989 where POA sections are alleged",
                "BNSS/CrPC bail, arrest, and court procedure based on incident date",
                "BNS/IPC underlying offence sections such as theft only if those facts are in the FIR",
            ],
            forums=["Special Court / criminal court", "High Court where quashing/protection is considered", "police/investigating officer for FIR/notice status", "District Legal Services Authority"],
            missing_facts=["FIR/complaint copy", "POA and BNS/IPC sections alleged", "incident date", "arrest/notice status", "caste/status allegations in FIR", "false-implication proof"],
            red_flags=_red_flags(q),
            action_pack=_bail_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_scst_poa_procedure_issue(q) or _is_caste_violence_priority_issue(q):
        poa_rules_source = (
            "SC/ST (Prevention of Atrocities) Rules 1995 Rule 7 DSP-rank investigating-officer requirement"
            if _is_scst_poa_dsp_investigation_issue(q)
            else "SC/ST (Prevention of Atrocities) Act 1989 and Rules where protected caste/tribal targeting fits"
        )
        return MatterRoute(
            category="tribal_caste_atrocity",
            label="SC/ST atrocity case procedure / targeted violence",
            confidence=0.84,
            urgency="emergency" if _has_any(q, ("beat", "beaten", "attack", "attacked", "violence", "threat")) else "high",
            required_sources=[
                poa_rules_source,
                "BNSS/CrPC investigation, FIR, and complaint procedure based on incident date",
                "BNS/IPC based on incident date where assault, intimidation, or other offences are alleged",
            ],
            forums=["police station/senior police", "Special Court under SC/ST Act", "District Legal Services Authority", "district social welfare/tribal welfare authority"],
            missing_facts=["community/status documents", "FIR/case number if any", "district/state", "incident date/place", "exact words/acts", "witnesses or school/medical record"],
            red_flags=_red_flags(q),
            action_pack=_tribal_caste_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_senior_maintenance_order_enforcement(q):
        return MatterRoute(
            category="senior_citizen",
            label="Senior citizen maintenance order enforcement",
            confidence=0.84,
            urgency="medium",
            required_sources=[
                "Maintenance and Welfare of Parents and Senior Citizens Act 2007 enforcement and deposit provisions",
                "state maintenance tribunal rules based on state and district",
                "tribunal order, arrears ledger, and payment proof to identify enforcement route",
            ],
            forums=["Maintenance Tribunal / District Magistrate", "District Legal Services Authority", "local lawyer/legal-aid desk"],
            missing_facts=["state/district", "tribunal order date", "arrears amount", "payments missed", "copy of tribunal order", "son/relative details"],
            red_flags=_red_flags(q),
            action_pack=_senior_pack(),
        )

    if _is_ancestral_land_sale_issue(q):
        return MatterRoute(
            category="property_tenancy",
            label="Ancestral land sale / heir share dispute",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Hindu Succession Act 1956 where Hindu coparcenary/intestate heirship or ancestral share is involved",
                "Transfer of Property Act 1882 for co-owner or heir transfer of share/interest",
                "Specific Relief Act 1963 for cancellation, declaration, or injunction where a sale deed affects your right",
            ],
            forums=["civil court", "revenue/mutation office for certified records", "sub-registrar for sale deed copy", "District Legal Services Authority"],
            missing_facts=["state/district", "whose name the land is recorded in", "death/family tree facts", "sale deed or mutation copy", "possession status", "your claimed share"],
            red_flags=[],
            action_pack=_property_pack(),
        )

    if _is_joint_property_sale_issue(q):
        return MatterRoute(
            category="property_tenancy",
            label="Joint property sale / co-owner dispute",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Transfer of Property Act 1882 for co-owner transfer and joint purchase/share framing",
                "Specific Relief Act 1963 for cancellation, declaration, or injunction where a sale deed affects your right",
                "Registration Act / sale deed and mutation records to identify what was actually transferred",
            ],
            forums=["civil court", "sub-registrar/revenue office for deed and mutation copies", "District Legal Services Authority"],
            missing_facts=["whose name is on the sale deed", "payment contribution proof", "share written in the deed", "whether the whole plot or only his share was sold", "possession and mutation status"],
            red_flags=[],
            action_pack=_property_pack(),
        )

    if _is_tenant_nonpayment_possession_issue(q):
        return MatterRoute(
            category="property_tenancy",
            label="Tenant not vacating / rent arrears",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Transfer of Property Act 1882 lease, notice, and termination provisions where state rent law does not displace them",
                "state rent-control/tenancy law based on state and city",
                "rent agreement, rent receipts, notices, and arrears ledger",
            ],
            forums=["rent authority or civil court depending on state law", "District Legal Services Authority", "local lawyer/legal-aid desk"],
            missing_facts=["state/city", "rent agreement term", "monthly rent and arrears", "notice already sent", "tenant possession status", "property use residential/commercial"],
            red_flags=[],
            action_pack=_tenancy_pack(),
        )

    if _is_pre_marriage_health_disclosure_issue(q):
        return MatterRoute(
            category="family_marriage_status",
            label="Pre-marriage health disclosure / cancelled wedding",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "personal marriage law only if a marriage has already occurred or later validity is in issue",
                "Hindu Marriage Act 1955 / Special Marriage Act 1954 where applicable for voidable-marriage analysis after marriage",
                "Dowry Prohibition Act 1961 or civil recovery route where gifts, dowry, or wedding expenses are disputed",
                "medical privacy and non-discrimination law must be verified from primary sources before disclosing HIV/health status publicly",
            ],
            forums=["District Legal Services Authority", "family-law lawyer/legal-aid desk", "Family Court only if matrimonial proceedings become necessary", "civil/police route only for coercion, threats, or property return facts"],
            missing_facts=["whether the marriage has already happened", "religion/personal law or Special Marriage Act context", "what was disclosed and when", "proof of messages/biodata", "gifts/dowry/wedding-expense records", "threats or pressure if any"],
            red_flags=_red_flags(q),
            action_pack=_pre_marriage_disclosure_pack(),
        )

    if _is_marriage_misrepresentation_issue(q):
        return MatterRoute(
            category="family_marriage_status",
            label="Marriage misrepresentation / family-law options",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "personal marriage law based on religion and form of marriage",
                "Hindu Marriage Act 1955 / Special Marriage Act 1954 where applicable for voidable marriage or matrimonial relief",
                "Family Courts Act 1984 for family-court jurisdiction",
            ],
            forums=["Family Court", "District Legal Services Authority", "family-law lawyer/legal-aid desk"],
            missing_facts=["religion/personal law or Special Marriage Act registration", "marriage date", "what exactly was represented", "proof of the statement", "when the truth was discovered", "whether you want annulment, divorce, maintenance, or counselling"],
            red_flags=[],
            action_pack=_marriage_misrepresentation_pack(),
        )

    if _is_marital_intimacy_breakdown_issue(q):
        return MatterRoute(
            category="family_marriage_status",
            label="Marriage breakdown / family-law options",
            confidence=0.70,
            urgency="medium",
            required_sources=[
                "personal marriage law based on religion and form of marriage",
                "Family Courts Act 1984 for matrimonial jurisdiction",
                "domestic-violence or criminal law only if there is force, threat, or abuse",
            ],
            forums=["Family Court", "District Legal Services Authority", "counselling/mediation service where safe and voluntary"],
            missing_facts=["religion/personal law or Special Marriage Act registration", "marriage date", "whether there is violence, threat, or coercion", "children/maintenance/residence concerns", "what remedy you want"],
            red_flags=_red_flags(q),
            action_pack=_marriage_breakdown_pack(),
        )

    if _is_minor_mineral_gram_sabha_issue(q):
        return MatterRoute(
            category="environment_compensation",
            label="Minor mineral / Gram Sabha recommendation",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "PESA Act 1996 section 4(c) Gram Sabha recommendation for minor minerals in Scheduled Areas",
                "Mines and Minerals (Development and Regulation) Act 1957 mining lease and mineral-concession approval record",
                "Forest Conservation Act 1980 where forest land or forest clearance is involved",
            ],
            forums=["Collector / District Magistrate", "mining department", "Gram Sabha / Panchayat channel where Scheduled Area rights apply", "tribal welfare authority", "District Legal Services Authority"],
            missing_facts=["state/district and Scheduled Area status", "mineral or quarry type", "lease/NOC number if known", "Gram Sabha/Palli Sabha notice or minutes", "forest or pollution clearance papers if any"],
            red_flags=_red_flags(q),
            action_pack=_minor_mineral_gram_sabha_pack(),
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

    if _is_pan_aadhaar_mismatch_issue(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="PAN/Aadhaar mismatch / identity linking",
            confidence=0.80,
            urgency="medium",
            required_sources=[
                "Income-tax Act / PAN procedure where PAN record or PAN-Aadhaar linking is involved",
                "Aadhaar Act 2016 where Aadhaar authentication or demographic data is involved",
                "Right to Information Act 2005 or public grievance route for written status/reasons",
            ],
            forums=["Income Tax e-filing / PAN service provider", "Aadhaar Seva Kendra / UIDAI grievance", "public grievance or RTI route where official reasons are withheld", "District Legal Services Authority"],
            missing_facts=["exact name/date-of-birth mismatch", "PAN/Aadhaar last four digits", "portal or bank/scheme where rejected", "error screenshot", "which record needs correction", "complaints already filed"],
            red_flags=[],
            action_pack=_pan_aadhaar_identity_pack(),
        )

    if _is_dpdp_data_breach_issue(q):
        required_sources = [
            "Digital Personal Data Protection Act 2023 for personal-data breach duties and grievance route",
            "Information Technology Act 2000 where identity misuse, account compromise, or cyber offence is alleged",
            "Aadhaar Act 2016 only where Aadhaar authentication or UIDAI records are directly involved",
        ]
        if _is_mental_health_privacy_breach_issue(q):
            required_sources.insert(
                1,
                "Mental Healthcare Act 2017 for confidentiality/privacy of mental-health records or therapist communications",
            )
        return MatterRoute(
            category="cyber_fraud_or_harassment",
            label="Personal data breach / DPDP grievance",
            confidence=0.84,
            urgency="high",
            required_sources=required_sources,
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
                "loan agreement document and state cooperative-bank recovery rules based on state/bank notice",
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

    if _is_name_change_identity_issue(q) or _is_marriage_name_change_issue(q):
        return MatterRoute(
            category="social_welfare_identity",
            label="Name / gazette / identity-record correction",
            confidence=0.76,
            urgency="low",
            required_sources=[
                "state gazette/name-change procedure where locally available",
                "available name-change and identity-record correction case law where an authority refuses",
                "identity-record update rules for Aadhaar, passport, PAN, school, or other records",
                "court order only if an authority disputes the change",
            ],
            forums=["state gazette or government press office", "Aadhaar/passport/PAN or record-issuing authority", "District Legal Services Authority"],
            missing_facts=["state/city", "old and new name", "reason for change/correction", "records to update", "affidavit/newspaper/gazette status", "whether any authority refused the change"],
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
            category="family_domestic",
            label="Streedhan / family jewellery return",
            confidence=0.78,
            urgency="medium",
            required_sources=[
                "PWDVA 2005 economic-abuse / streedhan return route where domestic relationship facts fit",
                "Dowry Prohibition Act 1961 for dowry or marriage-gift return facts where applicable",
                "BNS 2023 / IPC 1860 criminal breach of trust, cheating, or theft provisions based on incident date",
                "civil property/recovery route where ownership and entrustment are disputed",
            ],
            forums=["Protection Officer or Magistrate under PWDVA", "police station for breach of trust/threat facts", "Judicial Magistrate/criminal court where criminal complaint is filed", "District Legal Services Authority"],
            missing_facts=["who owns the jewellery", "entrustment date and words", "proof of purchase/gift", "messages demanding return", "relationship and shared-household facts", "police complaint status"],
            red_flags=_red_flags(q),
            action_pack=_family_safety_pack(),
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
                "cooperative housing society bye-laws or apartment association rules based on state/city and allotment documents",
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
                "cooperative housing society bye-laws or apartment association rules based on state/city and fine notice documents",
                "available cooperative-society case law where local housing/pet rules are not indexed",
                "consumer/civil remedy based on the society resolution, fine notice, and local maintainability",
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
                "BNS 2023 / IPC 1860 sexual-offence provisions and marital-exception limits only where a separate FIR, arrest notice, or criminal complaint exists",
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

    if _is_missing_person_police_complaint_issue(q):
        return _missing_person_police_complaint_route(q)

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
                "caste/tribal-status fact check before adding SC/ST atrocity route",
                "BNSS/CrPC complaint procedure",
            ],
            forums=["police station", "senior police officer", "District Legal Services Authority"],
            missing_facts=["exact words used", "place and date", "whether it was public or online", "witnesses/screenshots", "whether caste/tribal status was targeted"],
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
            legal_regime=_criminal_regime(q),
        )

    if _is_commercial_mediation_procedure(q) or _is_general_mediation_procedure(q):
        commercial_mediation = _is_commercial_mediation_procedure(q)
        return MatterRoute(
            category="court_procedure",
            label="Commercial suit / pre-litigation mediation procedure" if commercial_mediation else "Mediation procedure / legal-aid route",
            confidence=0.80,
            urgency="medium",
            required_sources=(
                [
                    "Commercial Courts Act 2015 pre-institution mediation provision where applicable",
                    "Mediation Act 2023 / rules where notified procedure applies",
                    "Code of Civil Procedure 1908 for plaint rejection and threshold objections",
                ]
                if commercial_mediation
                else [
                    "Mediation Act 2023 for voluntary/pre-litigation/court-referred mediation procedure where notified",
                    "Legal Services Authorities Act 1987 for legal-aid and mediation-centre access",
                    "Code of Civil Procedure 1908 only where a court case is already pending or a settlement needs court handling",
                ]
            ),
            forums=(
                ["commercial court", "District Legal Services Authority / mediation centre", "civil court filing counter", "lawyer/legal-aid clinic"]
                if commercial_mediation
                else ["District Legal Services Authority", "court-annexed mediation centre", "legal-aid clinic", "civil court help desk where a case is pending"]
            ),
            missing_facts=(
                ["commercial dispute type and value", "urgent interim relief sought or not", "mediation notice/status", "suit filing date", "court/order copy"]
                if commercial_mediation
                else ["state/city", "dispute type", "whether any court case is pending", "opposite party contact/notice status", "whether urgent interim relief is needed"]
            ),
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
            label="Parent / senior citizen maintenance",
            confidence=0.82,
            urgency="high" if _has_any(q, (
                "threw me out", "no food", "homeless", "widow", "no income",
                "not giving food", "not giving medicine", "food or medicine",
                "food and medicine", "medical expenses",
            )) else "medium",
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
        return _bocw_registration_route(q)

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
        if _is_explicit_physical_stalking_context(q):
            cyber_context = False
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

    if _is_domestic_residence_issue(q):
        return _domestic_residence_route(q)

    if _is_spousal_property_return_issue(q):
        return MatterRoute(
            category="family_domestic",
            label="Spousal jewellery / property return",
            confidence=0.76,
            urgency="medium",
            required_sources=[
                "Family Courts Act 1984 for family-court jurisdiction in spousal property-return intake",
                "civil recovery or property-return route where ownership, possession, or entrustment is disputed",
                "BNS 2023 / IPC 1860 breach of trust or theft provisions based on incident date only if entrustment, demand, and refusal facts fit",
                "BNSS 2023 / CrPC 1973 complaint procedure only if a criminal complaint is actually supportable",
            ],
            forums=["District Legal Services Authority", "Family Court where matrimonial proceedings are linked", "civil court for ownership/recovery", "police/Magistrate only where breach-of-trust or theft facts fit"],
            missing_facts=["who owns the item", "purchase/gift proof", "when and how it was taken", "messages demanding return", "whether there was entrustment or consent", "any pending matrimonial case"],
            red_flags=[],
            action_pack=_spousal_property_return_pack(),
            legal_regime=_criminal_regime(q) if _has_any(q, ("stole", "stolen", "theft", "breach of trust", "criminal complaint")) else None,
        )

    if _is_wife_as_aggressor_issue(q):
        sexual_coercion = _is_wife_as_aggressor_sexual_coercion(q)
        return MatterRoute(
            category="criminal_general",
            label="Spousal sexual coercion / safety support" if sexual_coercion else "Spousal assault / financial-control complaint",
            confidence=0.76,
            urgency="high" if sexual_coercion or _has_any(q, ("slap", "slapped", "hit", "beat", "threat", "threw me out", "kicked me out", "locked me out")) else "medium",
            required_sources=([
                "BNSS 2023 / CrPC 1973 complaint and investigation procedure based on incident date",
                "BNS 2023 / IPC 1860 force, hurt, threat, restraint, or other offence provisions only after checking exact gendered/fact-specific fit",
                "medical, counselling, DLSA, and safety-support route without assuming a women-protection domestic-violence frame",
            ] if sexual_coercion else [
                "BNS 2023 / IPC 1860 hurt, threat, theft, or breach-of-trust provisions based on incident date where criminal facts fit",
                "BNSS 2023 / CrPC 1973 complaint and investigation procedure based on incident date",
                "family/civil remedy only after identifying the exact marital, property, or financial facts",
            ]),
            forums=(["emergency medical care or crisis support if unsafe", "police station or senior police where force, threat, injury, or confinement is alleged", "District Legal Services Authority", "lawyer/legal-aid desk for exact offence fit"] if sexual_coercion else ["police station or senior police where assault, threats, or card misuse are alleged", "District Legal Services Authority", "Family Court or civil court where matrimonial/financial relief is sought"]),
            missing_facts=(["incident date and place", "current safety", "force/threat/injury details", "medical or counselling support needed", "messages/witnesses", "whether any police complaint or medical record exists"] if sexual_coercion else ["incident date and place", "injury/medical proof if any", "what exactly was taken or controlled", "bank/ATM transaction proof", "messages/witnesses", "current safety"]),
            red_flags=_red_flags(q),
            action_pack=_criminal_pack(),
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

    if _is_pocso_minor_accused_issue(q) or _is_sexual_offence_accused_issue(q):
        return MatterRoute(
            category="criminal_defence_bail",
            label="POCSO / sexual-offence accused defence",
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
        return _custodial_violence_route(q)

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
        return _domestic_residence_route(q)

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
        if _has_scst_protected_status(q):
            return MatterRoute(
                category="tribal_caste_atrocity",
                label="Caste / tribal witch-branding violence",
                confidence=0.84,
                urgency="emergency" if _has_any(q, ("beaten", "beat", "attack", "mob", "burn", "threat")) else "high",
                required_sources=[
                    "SC/ST (Prevention of Atrocities) Act 1989 where caste or tribal status is part of the targeting",
                    "BNS/BNSS or IPC/CrPC based on incident date for assault, intimidation, and police-refusal procedure",
                    "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given",
                ],
                forums=["police station", "Superintendent of Police", "Special Court where SC/ST POA facts apply", "District Legal Services Authority"],
                missing_facts=["state/district", "victim SC/ST/community status proof", "incident date/place", "injury/medical proof", "police refusal proof"],
                red_flags=_red_flags(q),
                action_pack=_tribal_caste_pack(),
                legal_regime=_criminal_regime(q),
            )
        return MatterRoute(
            category="police_fir",
            label="Witch-branding violence / police complaint",
            confidence=0.82,
            urgency="emergency" if _has_any(q, ("beaten", "beat", "attack", "mob", "throw me out", "stripped", "disrobed", "naked in public")) else "high",
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

    if _is_crypto_wallet_transfer_fraud_issue(q):
        return _cyber_fraud_or_harassment_route(q, label="Crypto / wallet transfer fraud")

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

    if _is_bank_property_document_fraud_issue(q):
        return MatterRoute(
            category="banking_credit_dispute",
            label="Forged loan / bank-property document dispute",
            confidence=0.82,
            urgency="high",
            required_sources=[
                "BNS 2023 / IPC 1860 cheating, forgery, and false-document provisions based on incident date",
                "Banking Regulation Act 1949 and RBI grievance route for the bank-service dispute",
                "property/security documents and registration records to verify consent and charge creation",
            ],
            forums=[
                "bank fraud/grievance desk",
                "RBI Ombudsman where maintainable",
                "police/cyber police for forged documents",
                "civil court or DRT where the security/property record is disputed",
                "District Legal Services Authority",
            ],
            missing_facts=[
                "bank/lender name",
                "loan account or notice number",
                "property/security document copy",
                "signature/thumb-impression dispute proof",
                "complaint number",
                "whether any SARFAESI/DRT/court step has started",
            ],
            red_flags=_red_flags(q),
            action_pack=_banking_credit_pack(),
            legal_regime=_criminal_regime(q),
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
        required_sources = ["Transfer of Property Act 1882", "Indian Contract Act 1872 where consent, coercion, undue influence, or authority is disputed", "Registration Act / civil court procedure where document validity is disputed"]
        if _has_document_forgery_or_false_document_terms(q):
            required_sources.extend([
                "BNS 2023 / IPC 1860 cheating, forgery, or false-document provisions based on incident date",
                "BNSS 2023 / CrPC 1973 complaint and investigation procedure based on incident date",
            ])
        return MatterRoute(
            category="property_tenancy",
            label="Property transfer / gift deed dispute",
            confidence=0.78,
            urgency="medium",
            required_sources=required_sources,
            forums=["civil court", "revenue/registration office where records must be checked", "District Legal Services Authority"],
            missing_facts=["state/city", "registered document type", "signing/thumb-impression date", "ownership and consideration facts", "possession status", "fraud/coercion evidence"],
            red_flags=_red_flags(q),
            action_pack=_property_pack(),
            legal_regime=_criminal_regime(q) if _has_document_forgery_or_false_document_terms(q) else None,
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
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    return _expand_devanagari_legal_hints(normalized)


def _expand_devanagari_legal_hints(text: str) -> str:
    if not re.search(r"[\u0900-\u097f]", text):
        return text
    additions: list[str] = []
    if any(term in text for term in (
        "मरने का मन",
        "खुद को मार",
        "ख़ुद को मार",
        "आत्महत्या",
        "जान देना",
        "जीना नहीं",
        "जिंदा नहीं",
        "ज़िंदा नहीं",
    )):
        additions.append(" kill myself suicidal self harm immediate safety crisis")
    if _has_any(text, ("पति", "ससुराल", "ससुर", "सास", "मारता", "मारती", "पीटता", "पीटती", "निकाल दिया", "घर से निकाल", "दहेज")):
        additions.append(" husband sasural domestic violence husband beat threw me out dowry family_domestic")
    if _has_any(text, ("पुलिस", "एफआईआर", "गिरफ्तार", "चोरी", "धमकी")):
        additions.append(" police fir arrest theft threat criminal")
    if _has_any(text, ("किराया", "मकान मालिक", "किरायेदार", "घर खाली")):
        additions.append(" rent landlord tenant vacate property tenancy")
    if _has_any(text, ("वेतन", "सैलरी", "नौकरी", "मजदूरी", "भुगतान")):
        additions.append(" salary wages employer employee labour")
    if not additions:
        return text
    return f"{text} {' '.join(additions)}"


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    for needle in needles:
        if " " in needle:
            if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text):
                return True
            continue
        if re.search(rf"\b{re.escape(needle)}\b", text):
            return True
    return False


def _negates_gst_without_tax_facts(q: str) -> bool:
    if not _has_any(q, (
        "no gst issue", "not gst issue", "not a gst issue", "not an gst issue",
        "no issue of gst", "not related to gst", "nothing to do with gst",
    )):
        return False
    return not _has_any(q, (
        "itc", "input tax credit", "input credit", "gstr", "gst notice", "cgst notice",
        "gst show cause", "cgst show cause", "gst scn", "cgst scn",
        "gst registration", "gst registration cancellation",
        "supplier gst", "gst cancelled", "gst cancelled retrospectively", "gst department",
        "rule 86b", "86b", "e-way bill", "eway bill", "tax period",
    ))


def _has_non_gst_tax_context(q: str) -> bool:
    return _has_any(q, (
        "tds", "26as", "form 26as", "income tax", "itr", "itat", "cit(a)",
        "cit appeal", "commissioner appeals", "assessment order", "143(3)",
        "section 143", "section 147", "section 148", "148 notice", "148a",
        "capital gains", "54f", "80c", "80ccd", "nps", "tax on sale",
        "tax on property sale", "property sale tax", "tcs", "foreign remittance",
        "remittance", "206c", "customs", "icegate", "bill of entry",
        "shipping bill", "drawback", "import duty", "customs duty", "duty demand",
        "classification dispute", "reclassified", "shipment held at port",
        "svb", "special valuation branch",
    )) or _has_customs_valuation_context(q)


def _has_customs_valuation_context(q: str) -> bool:
    return _has_any(q, ("declared value", "invoice value", "related party", "related-party", "valuation")) and _has_any(q, (
        "import", "imported", "invoice", "duty", "bill of entry", "customs", "shipment",
    ))


def _is_gratuity_delay_issue(text: str) -> bool:
    return _has_any(text, ("gratuity", "gratuity interest", "delayed gratuity")) and _has_any(text, (
        "delay", "delayed", "18 months", "months", "interest", "not paid", "not paying",
        "without paying", "unpaid", "no interest", "closed company", "company closed",
        "employer closed", "closure", "company shut down", "factory closed",
        "both pending", "no epf deposit",
    ))


def _is_gratuity_eligibility_issue(text: str) -> bool:
    return "gratuity" in text and _has_any(text, (
        "section 4", "sec 4", "eligibility", "eligible", "4 years 11",
        "4 year 11", "four years 11", "continuous service",
    ))


def _matched_any(text: str, needles: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for needle in needles:
        if " " in needle:
            if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text):
                matches.append(needle)
            continue
        if re.search(rf"\b{re.escape(needle)}\b", text):
            matches.append(needle)
    return matches


def _route_trace_terms(q: str) -> dict[str, list[str]]:
    groups = {
        "custody": (
            "jail", "lockup", "custody", "arrest", "arrested", "detained",
            "prison", "remand", "first remand", "police picked",
            "police took", "not produced by video", "not produced on video",
        ),
        "legal_aid": (
            "legal aid", "free lawyer", "free advocate", "dlsa", "nalsa",
            "slsa", "private lawyer", "cannot afford advocate",
            "cannot afford lawyer", "no lawyer", "lawyer access",
            "lawyer meeting", "first remand",
        ),
        "property_civil": (
            "property", "partition", "civil suit", "civil case", "civil court",
            "court sent summons", "court summons", "witness evidence",
            "bring documents", "land", "tenant", "rent", "lease",
        ),
        "police_notice": (
            "bnss 35", "35 notice", "section 35", "police notice",
            "police sent", "police called", "cyber police", "asked me to come",
            "bring phone", "bring chats", "phone chats",
        ),
        "fir_police": (
            "fir", "police refused", "police not registering", "not filing fir",
            "not taking fir", "police delaying", "superintendent of police",
            "sp or magistrate",
        ),
        "prison_admin": (
            "parole", "furlough", "remission", "mulaqat", "mulakat",
            "interview", "visit", "family call", "phone call",
        ),
        "medical_custody": (
            "doctor", "medical", "hospital", "pregnant", "bleeding",
            "dental", "dentist", "treatment", "jail doctor",
        ),
        "juvenile": (
            "minor", "16 year", "17 year", "child accused", "observation home",
            "school certificate", "age proof", "jjb", "juvenile",
        ),
    }
    return {name: matches for name, terms in groups.items() if (matches := _matched_any(q, terms))}


def _tax_required_sources(q: str) -> list[str]:
    required: list[str] = []
    gst_context = (
        (
            _has_any(q, (
                "gst", "cgst", "gstr", "itc", "input tax credit", "supplier gst",
                "gst department", "gst registration", "registration cancellation",
                "cancellation of registration", "rule 86b", "86b",
            )) or (
                _has_any(q, ("show cause notice", "scn"))
                and _has_any(q, (
                    "gst", "cgst", "gstr", "itc", "input tax credit", "input credit",
                    "supplier gst", "registration cancellation", "cancellation of registration",
                    "gst section 73", "gst section 74", "cgst section 73", "cgst section 74",
                ))
            )
        )
        and not _negates_gst_without_tax_facts(q)
    )
    income_tax_context = _has_any(q, (
        "tds", "26as", "income tax", "itr", "itat", "cit(a)", "cit appeal",
        "commissioner appeals", "assessment order", "143(3)", "section 143",
        "section 147", "section 148", "148 notice", "148a", "capital gains", "54f", "80c", "80ccd", "nps",
        "tcs", "foreign remittance", "remittance", "206c", "tax on sale",
        "tax on property sale",
    ))
    customs_context = _has_any(q, _CUSTOMS_TAX_WORDS) or _has_customs_valuation_context(q)

    if gst_context:
        if _has_any(q, ("sealed", "seal", "search", "godown", "without notice", "inspection")):
            required.append("CGST Act 2017 section 67 for inspection, search, seizure, and godown sealing/search issues")
        elif _has_any(q, ("rule 86b", "86b", "1% cash", "1 percent cash", "one percent cash")):
            required.append("CGST Rules 2017 Rule 86B and CGST Act 2017 electronic-credit-ledger provisions")
        elif _has_any(q, ("supplier gst cancelled", "supplier cancelled", "cancelled retrospectively", "canceled retrospectively", "retrospective cancellation")):
            required.append("CGST Act 2017 sections 16 and 29 for ITC eligibility and supplier registration cancellation issues")
        elif _has_any(q, ("itc", "input tax credit", "gstr 2a", "gstr-2a", "gstr 3b", "gstr-3b", "reversal", "reverse")):
            required.append("CGST Act 2017 sections 16, 41, and 73 for ITC mismatch, reversal, and notice issues")
        else:
            required.append("CGST Act 2017 / GST registration rules for GST registration, notice, and show-cause issues")
    if income_tax_context:
        if _has_any(q, ("tcs", "foreign remittance", "remittance", "206c", "lrs")):
            required.append("Income Tax Act 1961 section 206C and return/refund provisions for TCS credit on foreign remittance")
        else:
            required.append("Income Tax Act 1961 for TDS, return, assessment, and appeal issues")
    if customs_context:
        required.append("Customs Act 1962 for import/export, ICEGATE, duty, valuation, SVB, drawback, or classification issues")
    if not required:
        required.append("CGST Act 2017 / Income Tax Act 1961 / Customs Act 1962 depending on the notice, return, import/export, or assessment facts")
    if _has_any(q, ("bank", "payment proof", "upi", "utr", "chargeback", "rbi")):
        required.append("RBI/banking records where payment proof or chargeback facts matter")
    return required


def _is_off_topic(q: str) -> bool:
    return _has_any(q, _OFF_TOPIC_WORDS) and not _has_any(q, _LEGAL_HINT_WORDS)


def _is_self_harm_crisis(q: str) -> bool:
    custody_medical_legal_context = (
        _has_any(q, (
            "jail", "prison", "undertrial", "convict", "prisoner",
            "jail doctor", "jail hospital", "custody",
        ))
        and _has_any(q, (
            "psychiatric help", "psychiatrist", "mental health",
            "suicidal undertrial", "suicidal prisoner", "suicidal",
            "self harm", "self-harm",
        ))
        and _has_any(q, (
            "dlsa", "court", "move court", "legal", "urgent", "medical",
            "doctor", "hospital", "not giving", "refused", "refuses",
        ))
    )
    if custody_medical_legal_context:
        return False
    if _has_any(q, (
        "custodial death", "lockup death", "lockup suicide",
        "they say suicide", "saying suicide", "suicide but body",
    )):
        return False
    devanagari_self_harm = any(term in q for term in (
        "मरने का मन",
        "खुद को मार",
        "ख़ुद को मार",
        "आत्महत्या",
        "जान देना",
        "जीना नहीं",
        "जिंदा नहीं",
        "ज़िंदा नहीं",
    ))
    roman_hindi_self_harm = _has_any(q, (
        "suicide karne", "suicide karna", "suicide ka mann",
        "suicide karne ka mann", "marne ka mann", "marne ka man",
        "khud ko marna", "khud ko maarna", "apne aap ko marna",
        "jaan dena", "zinda nahi rehna", "jeena nahi",
    ))
    return _has_any(q, (
        "kill myself", "end my life", "want to die", "i want to die",
        "i will die", "harm myself", "hurt myself", "self harm",
        "self-harm", "hang myself", "jump from", "consume poison",
        "drink poison", "suicidal",
    )) or devanagari_self_harm or roman_hindi_self_harm or (
        _has_any(q, ("suicide",))
        and _has_any(q, (
            "myself", "i want", "i am thinking", "thinking of", "feel like",
            "i will commit", "i will kill", "i will do suicide",
        ))
    )


def _is_crisis_signal(q: str) -> bool:
    if _has_any(q, (
        "want to kill myself", "end my life", "want to die", "will kill myself",
        "khatam kar loon", "marna chahta", "marna chahti", "jaan de doon",
    )):
        return True
    completed_or_legal_suicide_context = _has_any(q, (
        "committed suicide", "died by suicide", "made worker commit suicide",
        "made employee commit suicide", "abetment of suicide", "suicide after",
        "suicide due to", "suicide note",
    ))
    first_person_current_risk = re.search(r"\b(i|i'm|im|main|mein|mujhe)\b", q) is not None or _has_any(q, ("myself", "my life"))
    current_third_party_risk = _has_any(q, (
        "says he will commit suicide", "says she will commit suicide",
        "said he will commit suicide", "said she will commit suicide",
        "threatening suicide", "threatens suicide", "will commit suicide",
        "wants to commit suicide",
    ))
    return not completed_or_legal_suicide_context and _has_any(q, ("thinking of suicide", "commit suicide")) and (
        first_person_current_risk or current_third_party_risk
    )


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
    location_hidden = _has_any(q, (
        "police took", "police picked", "picked my", "took my",
        "taken by police", "took my brother", "took my son",
    )) and _has_any(q, (
        "not showing station", "not telling station", "not telling where",
        "where taken",
    ))
    access_or_production_blocked = _has_any(q, (
        "not allowing lawyer", "lawyer not allowed", "not allowing advocate",
        "no lawyer", "secret", "not produced", "24 hours passed",
        "24 hours", "whole night",
    ))
    hidden_police_custody_context = location_hidden and access_or_production_blocked
    authority_context = _has_any(q, ("police", "jail", "custody", "authority", "state", "thana"))
    return (liberty_context and authority_context) or hidden_police_custody_context


def _is_missing_person_police_complaint_issue(q: str) -> bool:
    if _is_prison_records_admin_issue(q):
        return False
    missing_context = _has_any(q, (
        "missing", "missing since", "not reachable", "phone off",
        "phone switched off", "disappeared", "not found", "cannot find",
    ))
    person_context = _has_any(q, (
        "brother", "sister", "husband", "wife", "son", "daughter",
        "father", "mother", "adult", "child", "family", "friend",
    ))
    police_custody_negated = _has_any(q, (
        "no proof police picked", "no proof police took", "no proof of police",
        "not police custody", "no police custody proof", "no proof of police custody",
        "no idea police", "not sure police",
    ))
    explicit_police_custody = _has_any(q, (
        "police picked", "police took", "detained", "custody", "lockup",
        "arrested", "taken by police",
    ))
    return missing_context and person_context and (police_custody_negated or not explicit_police_custody)


def _high_risk_precedence_route(q: str) -> MatterRoute | None:
    """Safety-critical route ownership before broad topic buckets.

    These are explicit preemption pairs found in real held-out prompts: prison
    admin must not swallow custody medical/legal-aid/arrest, and cyber/phone
    words must not swallow bail-release or police-notice questions.
    """
    if _is_juvenile_age_custody_issue(q):
        return _juvenile_age_custody_route(q)
    if _is_adult_partner_choice_police_return_issue(q):
        return _adult_partner_choice_police_return_route(q)
    if _is_prison_records_admin_issue(q):
        return _prison_records_route(q)
    if _is_missing_person_police_complaint_issue(q):
        return _missing_person_police_complaint_route(q)
    if _is_fake_authority_payment_fraud(q) and not _is_identity_loan_or_sim_misuse_issue(q):
        return _fake_authority_payment_fraud_route(q)
    if _is_dating_app_extortion_or_phone_seizure(q):
        return _cyber_fraud_or_harassment_route(q, label="Dating-app extortion / phone seizure")
    if _is_uapa_bail_or_custody_issue(q):
        return _uapa_bail_route(q)
    if _is_default_bail_issue(q):
        return _default_bail_route(q)
    if _is_undertrial_review_issue(q):
        return _undertrial_review_route(q)
    if _is_interim_medical_bail_issue(q):
        return _custody_medical_care_route(q)
    if _is_undertrial_review_issue(q):
        return _undertrial_review_route(q)
    if _is_custody_compensation_issue(q):
        return MatterRoute(
            category="custody_compensation",
            label="Wrongful custody / acquittal compensation",
            confidence=0.82,
            urgency="medium",
            required_sources=[
                "Article 21 constitutional compensation and speedy-trial principles",
                "human-rights commission procedure",
                "BNSS/CrPC custody and appeal records where relevant",
            ],
            forums=["High Court writ jurisdiction", "Human Rights Commission", "District Legal Services Authority"],
            missing_facts=["custody start/end dates", "acquittal/release order", "case/offence sections", "bail history", "delay or unlawful custody facts"],
            red_flags=_red_flags(q),
            action_pack=_custody_pack(),
            legal_regime=_criminal_regime(q),
        )
    if _is_custodial_violence_issue(q):
        return _custodial_violence_route(q)
    if _is_private_magistrate_complaint_issue(q):
        return _private_magistrate_complaint_route(q)
    if _is_bail_release_delay_issue(q):
        return _bail_release_delay_route(q)
    if _is_custody_legal_aid_access_issue(q):
        return _custody_legal_aid_access_route(q)
    if _is_police_station_coercive_questioning_issue(q) or _is_arrest_production_delay(q) or _is_custody_restraint_issue(q) or _is_arrest_information_safeguard(q):
        return _arrest_custody_safeguard_route(q)
    if _is_section_91_notice(q):
        return _production_notice_route(q)
    if _is_police_questioning_notice_issue(q):
        return _police_questioning_notice_route(q)
    return None


def _missing_person_police_complaint_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="police_fir",
        label="Missing person / police complaint",
        confidence=0.76,
        urgency="high",
        required_sources=[
            "BNSS 2023 / CrPC 1973 police information, complaint, and investigation route",
            "senior police / Magistrate escalation where police refuse or delay recording the complaint",
        ],
        forums=["local police station", "senior police officer", "Magistrate court where police refuse action", "District Legal Services Authority"],
        missing_facts=["last-seen time and place", "photo/ID and phone number", "known companions or vehicle details", "call/message/location records", "whether there is any proof of police custody"],
        red_flags=_red_flags(q),
        action_pack=_fir_pack(),
        legal_regime=_criminal_regime(q),
    )


def _custody_medical_care_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="criminal_defence_bail",
        label="Custody medical care / interim bail",
        confidence=0.86,
        urgency="high",
        required_sources=[
            "Article 21 constitutional custody-health and dignity safeguards",
            "Prisons Act 1894 / prison medical-officer and superintendent route where applicable",
            "BNSS 2023 / CrPC 1973 bail and custody provisions based on incident date",
        ],
        forums=["criminal court", "jail superintendent", "District Legal Services Authority", "High Court writ jurisdiction"],
        missing_facts=["custody start date", "jail/prison name", "pregnancy or medical condition records", "doctor requests/refusals", "case/offence sections", "prior bail orders"],
        red_flags=_red_flags(q),
        action_pack=_bail_pack(),
        legal_regime=_criminal_regime(q),
    )


def _juvenile_age_custody_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="criminal_defence_bail",
        label="Juvenile age / JJB custody route",
        confidence=0.86,
        urgency="emergency" if _has_any(q, ("adult jail", "adult prison", "adult lockup", "with adults", "station with adults", "overnight with adults", "kept him overnight", "kept her overnight")) else "high",
        required_sources=[
            "Juvenile Justice Act 2015 age-determination and JJB production/transfer route",
            "Juvenile Justice Act 2015 child-custody and bail provisions",
            "BNSS 2023 / CrPC 1973 only for the adult criminal-procedure wrapper after age is checked",
        ],
        forums=["Juvenile Justice Board", "current criminal court", "District Legal Services Authority", "observation home / child-welfare authority where applicable"],
        missing_facts=["date of birth and age proof", "current custody place", "FIR/offence sections", "remand/court papers", "parent or guardian contact", "whether JJB was approached"],
        red_flags=_red_flags(q),
        action_pack=_bail_pack(),
        legal_regime=_criminal_regime(q),
    )


def _bail_release_delay_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="criminal_defence_bail",
        label="Bail release / surety verification delay",
        confidence=0.84,
        urgency="high",
        required_sources=[
            "BNSS 2023 / CrPC 1973 bail, bond, and release procedure based on case date",
            "Article 21 personal-liberty principles where release is blocked despite bail",
            "bail order, release warrant, surety verification, and jail non-release papers",
        ],
        forums=["same bail court / trial court", "jail superintendent", "District Legal Services Authority", "High Court where release remains blocked despite bail"],
        missing_facts=["bail order date", "release warrant status", "surety verification status", "jail non-release reason", "case/FIR number", "next hearing date"],
        red_flags=_red_flags(q),
        action_pack=_bail_pack(),
        legal_regime=_criminal_regime(q),
    )


def _custody_legal_aid_access_route(q: str) -> MatterRoute:
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


def _arrest_custody_safeguard_route(q: str) -> MatterRoute:
    habeas_context = _is_habeas_illegal_detention_issue(q)
    coercive_questioning = _is_police_station_coercive_questioning_issue(q)
    return MatterRoute(
        category="arrest_custody_safeguard",
        label=(
            "Illegal detention / habeas corpus"
            if habeas_context
            else "Police station coercion / custody safeguard"
            if coercive_questioning
            else "Arrest / production before Magistrate"
        ),
        confidence=0.84 if coercive_questioning else 0.82,
        urgency="emergency",
        required_sources=[
            "Article 21 and Article 226 constitutional liberty / habeas corpus route" if habeas_context else "constitutional liberty safeguards under Articles 21 and 22",
            "BNSS 2023 arrest, notice, and 24-hour production safeguards for current matters",
            "CrPC 1973 arrest and 24-hour production safeguards for pre-1 July 2024 matters",
        ],
        forums=["nearest Magistrate/criminal court", "District Legal Services Authority", "senior police officer", "High Court writ jurisdiction for unlawful detention"],
        missing_facts=["arrest/date and time", "police station/officer", "FIR/offence or notice details", "whether family was informed", "whether any remand order exists"],
        red_flags=_red_flags(q),
        action_pack=_custody_safeguard_pack(),
        legal_regime=_criminal_regime(q),
    )


def _custodial_violence_route(q: str) -> MatterRoute:
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


def _police_questioning_notice_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="criminal_procedure_notice",
        label="Police questioning / appearance notice",
        confidence=0.80,
        urgency="high",
        required_sources=[
            "BNSS 2023 section 35 police notice/appearance safeguards for current matters",
            "CrPC 1973 section 160 witness-attendance route for pre-1 July 2024 matters where applicable",
            "BNSS 2023 / CrPC 1973 FIR or complaint route if police refuse to give any written paper",
        ],
        forums=["investigating officer/police station", "Magistrate/criminal court if coercion or refusal escalates", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
        missing_facts=["notice/call date", "police station and officer", "case/FIR number if any", "whether you are witness, complainant, or suspect", "whether a written notice was given"],
        red_flags=_red_flags(q),
        action_pack=_criminal_notice_pack(),
        legal_regime=_criminal_regime(q),
    )


def _production_notice_route(q: str) -> MatterRoute:
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


def _is_police_fir_inaction_issue(q: str) -> bool:
    if _has_any(q, (
        "take cognizance", "refused to take cognizance", "without cognizance",
        "cognizance complaint", "dismissed complaint", "dismissed my complaint",
        "magistrate dismissed", "revision against dismissal", "revision against order",
    )):
        return False
    if _is_family_domestic_notice_response_issue(q) and _has_any(q, (
        "no fir", "without fir", "only notice", "just notice",
        "no police case", "no criminal case", "no criminal complaint",
    )):
        return False
    fir_context = _has_any(q, ("fir", "complaint", "cognizable")) or (
        _has_any(q, (
            "assault", "hit me", "beat me", "beaten", "hurt me",
            "broke my", "broken", "damaged my", "damage to", "scooter mirror",
        ))
        and _has_any(q, ("go to sp", "sp or magistrate", "magistrate", "police say settle", "police says settle", "settle privately"))
    )
    police_delay_context = _has_any(q, (
        "police delaying", "police are delaying", "police delayed",
        "police refused", "police not registering", "not filing fir",
        "not taking fir", "no fir", "go to sp", "sp or magistrate",
        "superintendent of police", "magistrate", "police say settle",
        "police says settle", "settle privately", "calling it insurance",
    ))
    return fir_context and police_delay_context


def _police_fir_inaction_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="police_fir",
        label="FIR / police inaction",
        confidence=0.84,
        urgency="high",
        required_sources=[
            "BNSS 2023 / CrPC 1973 FIR and senior-police / Magistrate complaint-escalation procedure based on incident date",
        ],
        forums=["police station", "Superintendent of Police", "Judicial Magistrate", "District Legal Services Authority"],
        missing_facts=["incident date", "place", "offence facts", "whether complaint was given in writing", "police station name", "acknowledgement/CSR/DD number or refusal proof"],
        red_flags=_red_flags(q),
        action_pack=_fir_pack(),
        legal_regime=_criminal_regime(q),
    )


def _is_civil_court_procedure_issue(q: str) -> bool:
    civil_summons_context = _has_any(q, (
        "court sent summons", "court summons", "witness evidence",
        "bring documents", "summons for witness", "summons to witness",
        "witness summons", "civil summons", "bring sale deed", "bring deed",
        "bring property papers", "bring land papers",
    )) and _has_any(q, (
        "civil case", "civil court", "witness", "documents", "summons",
        "sale deed", "property case",
    ))
    court_status_context = (
        _has_any(q, ("already on bail", "bail granted", "got bail", "released on bail"))
        and _has_any(q, (
            "video link failed", "vc failed", "video conference failed",
            "not produced by video", "next date", "date status",
            "case status", "adjourned", "hearing date",
        ))
    )
    police_sender_context = _has_any(q, (
        "cyber police sent", "police sent", "police station sent",
        "investigating officer sent", "io sent", "police called",
        "police asked me", "cyber police asked", "fir number", "crime number",
    ))
    return (civil_summons_context or court_status_context) and not police_sender_context


def _court_procedure_route(q: str) -> MatterRoute:
    civil_specific = _has_any(q, _CIVIL_PROCEDURE_WORDS)
    bail_status = _has_any(q, ("already on bail", "bail granted", "got bail", "released on bail"))
    return MatterRoute(
        category="court_procedure",
        label=(
            "Civil court summons / witness procedure"
            if civil_specific
            else "Criminal court date / case-status procedure"
            if bail_status
            else "Court procedure / court visit"
        ),
        confidence=0.80 if civil_specific or bail_status else 0.72,
        urgency="medium" if _has_any(q, ("next date", "hearing date", "summons", "tomorrow")) else "low",
        required_sources=(
            [
                "Code of Civil Procedure 1908 summons, witness, and document-production procedure for civil cases",
                "court rules/practice directions for the court named in the summons",
                "Legal Services Authorities Act 1987 where court help or legal aid is needed",
            ]
            if civil_specific
            else [
                "court rules and practice directions for the relevant court",
                "BNSS 2023 / CrPC 1973 only if the case-status issue is in a criminal case",
                "Legal Services Authorities Act 1987 where help is needed",
            ]
        ),
        forums=["court filing/help desk", "same court/registry named in the summons or case", "District Legal Services Authority", "lawyer/legal-aid clinic"],
        missing_facts=["court name", "case number", "case type", "next date", "summons/order copy", "whether you are party/witness/visitor"],
        red_flags=[],
        action_pack=_court_procedure_pack(),
        legal_regime=_criminal_regime(q) if bail_status else None,
    )


def _civil_court_procedure_route(q: str) -> MatterRoute | None:
    if not _is_civil_court_procedure_issue(q):
        return None
    return _court_procedure_route(q)


def _default_bail_route(q: str) -> MatterRoute:
    required_sources = [
        "BNSS 2023 section 187 / CrPC 1973 section 167 default-bail custody periods based on incident/procedure date",
        "offence-specific maximum punishment and special-statute extension rules where applicable",
        "charge-sheet filing status, extension application/order, and first remand date",
    ]
    if _has_uapa_context(q):
        required_sources[1] = "Unlawful Activities (Prevention) Act 1967 section 43D / 43D(5) special bail/default-bail extension rules where UAPA is alleged"
    if _has_any(q, (
        "mcoca", "mco case", "maharashtra control of organised crime",
        "organised crime act", "organized crime act",
    )):
        required_sources[1] = "Maharashtra Control of Organised Crime Act 1999 Section 21 extension rules where MCOCA is alleged"
    return MatterRoute(
        category="criminal_defence_bail",
        label="Default bail / no chargesheet",
        confidence=0.87,
        urgency="high",
        required_sources=required_sources,
        forums=["trial court / Magistrate", "Special Court where a special statute applies", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
        missing_facts=["first remand date", "charge-sheet filing date/status", "offence sections and maximum punishment", "extension application/order if any", "whether default-bail application was already filed"],
        red_flags=_red_flags(q),
        action_pack=_bail_pack(),
        legal_regime=_criminal_regime(q),
    )


def _uapa_bail_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="criminal_defence_bail",
        label="UAPA bail / criminal defence",
        confidence=0.88,
        urgency="high",
        required_sources=[
            "Unlawful Activities (Prevention) Act 1967 section 43D / 43D(5) bail restrictions and prolonged-incarceration/default-bail rules",
            "BNSS 2023 / CrPC 1973 bail and custody procedure based on incident date",
            "Article 21 speedy-trial/liberty principles where prolonged custody or trial delay is the issue",
        ],
        forums=["Special Court / Sessions Court", "High Court", "District Legal Services Authority", "criminal lawyer/legal-aid desk"],
        missing_facts=["FIR/NIA case number", "exact UAPA sections", "custody start date", "charge-sheet and sanction status", "prior bail order", "whether 43D(5), default bail, or delay-based bail is being argued"],
        red_flags=_red_flags(q),
        action_pack=_bail_pack(),
        legal_regime=_criminal_regime(q),
    )


def _cyber_fraud_or_harassment_route(q: str, *, label: str = "Cyber fraud / online harassment") -> MatterRoute:
    return MatterRoute(
        category="cyber_fraud_or_harassment",
        label=label,
        confidence=0.82,
        urgency="emergency" if _has_any(q, (
            "lost money", "upi", "credit card", "debit card", "otp",
            "blackmail", "nudes", "nude", "deepfake", "upload",
            "secretly recorded", "intimate video", "sex video",
            "porn video", "lookalike", "face same", "reddit",
            "extortion", "took my phone", "phone taken",
        )) or _is_intimate_image_emergency(q) else "high",
        required_sources=_cyber_required_sources(q),
        forums=["National Cyber Crime Portal", "1930 cyber helpline", "local police station"],
        missing_facts=["incident date", "platform", "amount lost", "whether money is still moving", "screenshots/transaction IDs"],
        red_flags=_red_flags(q),
        action_pack=_cyber_pack(),
        legal_regime=_criminal_regime(q),
    )


def _fake_authority_payment_fraud_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="cyber_fraud_or_harassment",
        label="Fake authority / digital arrest payment fraud",
        confidence=0.84,
        urgency="high",
        required_sources=[
            "Information Technology Act 2000 identity-theft / cheating by personation provisions",
            "BNS 2023 / IPC 1860 cheating and criminal-intimidation provisions based on incident date",
            "BNSS 2023 / CrPC 1973 complaint/FIR procedure",
        ],
        forums=["National Cyber Crime Portal / cyber police station", "1930 cyber helpline if money is still moving", "local police station", "District Legal Services Authority"],
        missing_facts=["caller/handle and time", "video-call or message screenshots/recordings", "amount demanded or transferred", "beneficiary account/UPI", "bank complaint number", "cyber complaint acknowledgement"],
        red_flags=_red_flags(q),
        action_pack=_cyber_pack(),
        legal_regime=_criminal_regime(q),
    )


def _bank_or_pension_impersonation_fraud_route(q: str) -> MatterRoute:
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


def _undertrial_review_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="undertrial_review_release",
        label="Undertrial custody review / release eligibility",
        confidence=0.84,
        urgency="high",
        required_sources=[
            "BNSS 2023 section 479 for current undertrial custody-review limits",
            "CrPC 1973 section 436A for legacy / transitional comparison",
            "Legal Services Authorities Act 1987 and Under Trial Review Committee procedure",
            "Article 21 speedy-trial and liberty principles where trial delay or non-production is alleged",
        ],
        forums=["trial court", "jail superintendent", "District Legal Services Authority / Under Trial Review Committee", "High Court writ jurisdiction where delay is unlawful"],
        missing_facts=["offence sections", "maximum punishment alleged", "custody start date", "chargesheet/trial stage", "production/hearing dates missed", "prior bail/review orders"],
        red_flags=_red_flags(q),
        action_pack=_undertrial_review_pack(),
        legal_regime=_criminal_regime(q),
    )


def _prison_records_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="prison_records",
        label="Prison records / prisoner account request",
        confidence=0.78,
        urgency="medium",
        required_sources=[
            "Prisons Act 1894 prison-administration and rule-making source",
            "state prison rules / prison manual for prisoner accounts, canteen, visitor, and record-copy procedure",
            "Right to Information Act 2005 where public records, file status, or reasons are withheld",
        ],
        forums=["prison superintendent", "jail records/accounts office", "District Legal Services Authority", "RTI Public Information Officer where records are withheld", "court registry for certified court orders"],
        missing_facts=["state/prison", "prisoner number", "relationship/authority to request", "record/account/order requested", "written refusal or no-reply proof"],
        red_flags=_red_flags(q),
        action_pack=_prison_records_pack(),
    )


def _is_private_magistrate_complaint_issue(q: str) -> bool:
    complaint_context = _has_any(q, (
        "private complaint", "complaint before magistrate", "magistrate complaint",
        "file complaint before magistrate", "file private complaint",
        "156(3)", "156 3", "section 156", "section 200",
        "complaint without cognizance", "without cognizance",
        "dismissed my private", "dismissed my complaint",
        "magistrate dismissed", "complaint dismissed by magistrate",
        "dismissed without cognizance", "did not take cognizance",
        "not take cognizance", "revision against dismissal",
        "revision against magistrate", "criminal revision",
    ))
    police_inaction_context = _has_any(q, (
        "police inaction", "police not acting", "police refused",
        "police not taking", "police not registering", "no fir",
    ))
    return complaint_context or ("magistrate" in q and police_inaction_context)


def _private_magistrate_complaint_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="court_procedure",
        label="Private complaint / Magistrate police-inaction procedure",
        confidence=0.84,
        urgency="medium",
        required_sources=[
            "BNSS 2023 / CrPC 1973 private complaint, cognizance, dismissal, revision, and Magistrate investigation procedure based on incident date",
        ],
        forums=["Judicial Magistrate", "Sessions/revisional court where applicable", "District Legal Services Authority", "lawyer/legal-aid clinic"],
        missing_facts=["complaint filing date", "dismissal/order copy", "whether cognizance was refused or complaint dismissed", "prior police complaint proof", "incident date and offence facts"],
        red_flags=_red_flags(q),
        action_pack=_court_procedure_pack(),
        legal_regime=_criminal_regime(q),
    )


def _is_adult_partner_choice_police_return_issue(q: str) -> bool:
    adult_context = _has_age_at_least(q, 18) or _has_any(q, (
        "adult daughter", "adult son", "adult sister", "adult brother",
        "major daughter", "major son", "major girl", "major boy",
        "above 18", "over 18", "adult woman", "adult man",
    ))
    partner_or_choice = _has_any(q, (
        "left with boyfriend", "left with girlfriend", "went with boyfriend",
        "went with girlfriend", "living with boyfriend", "living with girlfriend",
        "staying with boyfriend", "staying with girlfriend", "boyfriend",
        "girlfriend", "love marriage", "partner choice", "choice marriage",
        "left home with", "ran away with", "went with partner",
    ))
    forced_return_or_police = _has_any(q, (
        "bring her home", "bring him home", "bring back", "return home",
        "force her back", "force him back", "parents want police",
        "family wants police", "police to bring", "police bring",
        "police should bring", "missing complaint", "kidnap complaint",
        "habeas", "against her wish", "against his wish",
    ))
    minor_or_coercion = _has_any(q, (
        "minor", "under 18", "under eighteen", "kidnapped", "abducted",
        "trafficked", "forced by boyfriend", "forced by girlfriend",
    ))
    return adult_context and partner_or_choice and forced_return_or_police and not minor_or_coercion


def _adult_partner_choice_police_return_route(q: str) -> MatterRoute:
    return MatterRoute(
        category="police_fir",
        label="Adult partner-choice / no forced return",
        confidence=0.86,
        urgency="high" if _has_any(q, ("threat", "attack", "kill", "violence", "honour", "khap")) else "medium",
        required_sources=[
            "Article 21 adult autonomy and partner-choice liberty principles",
            "BNSS 2023 / CrPC 1973 police complaint route only if missing, threat, coercion, confinement, or offence facts exist",
            "BNS 2023 / IPC 1860 intimidation or confinement provisions only where threats or force are alleged",
        ],
        forums=[
            "police station for safety/missing entry only on facts",
            "senior police officer",
            "District Legal Services Authority",
            "High Court writ/protection route where threats or unlawful restraint exist",
        ],
        missing_facts=["exact age proof", "current location/safety", "whether the adult is acting voluntarily", "any threat/confinement facts", "whether any FIR/missing complaint exists"],
        red_flags=_red_flags(q),
        action_pack=_fir_pack(),
        legal_regime=_criminal_regime(q),
    )


def _is_mgnrega_social_audit_issue(q: str) -> bool:
    mgnrega_context = _has_any(q, ("mgnrega", "nrega", "job card", "muster roll", "muster", "social audit", "work demand"))
    local_body_context = _has_any(q, (
        "gram sabha", "panchayat", "sarpanch", "mukhiya", "bdo",
        "programme officer", "program officer", "mate", "district officer",
    ))
    grievance_context = _has_any(q, (
        "corruption", "fake", "fake attendance", "no action", "no payment",
        "not paid", "not paying", "money taken", "wage", "payment",
        "muster", "audit", "complain", "no reply", "silent", "forged",
        "receipt not given", "come next week", "no card", "atr",
    ))
    return mgnrega_context and (local_body_context or "muster" in q or "job card" in q) and grievance_context


def _is_mgnrega_job_card_or_wage_issue(q: str) -> bool:
    mgnrega_context = _has_any(q, (
        "mgnrega", "nrega", "job card", "job cards", "work demand",
        "muster roll", "muster", "social audit",
    ))
    local_body_or_work_context = _has_any(q, (
        "panchayat", "gram panchayat", "gram sabha", "sarpanch", "mukhiya",
        "mate", "programme officer", "program officer", "bdo", "block office",
        "collector", "district officer", "work done", "worked", "wage", "wages",
        "payment", "paid", "bank passbook", "passbook", "bank account",
        "portal", "website", "muster", "job card", "work demand",
    ))
    grievance_context = _has_any(q, (
        "not issuing", "not issued", "not given", "not giving", "pending",
        "come later", "come next week", "no payment", "not paid", "nil",
        "absent", "fake", "forged", "corruption", "no action", "ignored",
        "no reply", "silent", "no credit", "zero credit", "no fund",
        "ask atr", "atr", "complaint", "complain", "refused", "refusing",
        "what proof", "proof need", "what proof need",
    ))
    return mgnrega_context and local_body_or_work_context and grievance_context


def _is_minor_synthetic_sexual_image_issue(q: str) -> bool:
    image_context = _has_any(q, (
        "fake nude", "fake nudes", "morphed sexual", "sexual image",
        "sexual images", "deepfake nude", "ai nude", "ai porn",
        "csam", "child sexual abuse material", "child porn",
        "child pornography", "morphed nude", "nude",
    ))
    if not image_context:
        return False
    minor_context = (
        _has_age_under(q, 18)
        or _has_any(q, (
            "minor", "child", "under 18", "under eighteen", "school",
            "schoolmate", "classmate", "student", "college girl",
            "college girls", "girl in class", "girls in class",
        ))
    )
    creation_or_spread = _has_any(q, (
        "made", "created", "generated", "shared", "circulating",
        "circulated", "posted", "uploaded", "telegram", "whatsapp",
        "school group", "college group", "delete", "takedown",
    ))
    return minor_context and creation_or_spread


def _is_labour_chowk_police_begging_issue(q: str) -> bool:
    labour_chowk = _has_any(q, ("labour chowk", "labor chowk", "mazdoor chowk", "daily wage corner"))
    police_or_label = _has_any(q, (
        "police", "picked", "picking", "detain", "detained",
        "begging", "beggar", "nautanki", "not work",
    ))
    return labour_chowk and police_or_label


def _is_arms_act_farming_tool_issue(q: str) -> bool:
    if not _has_any(q, ("arms act", "weapon case", "weapon")):
        return False
    return _has_any(q, (
        "axe", "sickle", "farming", "farm", "agriculture",
        "agricultural", "field", "tool",
    ))


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


def _is_general_mediation_procedure(q: str) -> bool:
    mediation_context = _has_any(q, (
        "mediation act", "mediation act 2023", "initiate mediation",
        "start mediation", "file for mediation", "apply for mediation",
        "go for mediation", "mediation centre", "mediation center",
        "court annexed mediation", "court-annexed mediation",
        "legal aid mediation", "legal-aid mediation",
        "mediator",
    ))
    procedure_context = _has_any(q, (
        "how to", "initiate", "start", "file", "apply", "complain",
        "notice", "settlement", "agreement", "without going to court",
        "court case", "pending case", "urgent",
    ))
    return mediation_context and procedure_context


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
        "pollution", "damage", "protect", "factory", "smoke", "air", "water",
        "effluent", "chemicals", "proof", "sick", "health",
    )):
        return True
    if _has_any(q, ("pil", "public interest litigation", "high court", "article 226", "writ")) and _has_any(q, (
        "pollution", "factory", "smoke", "air", "water", "effluent",
        "chemicals", "environment", "wetland", "making us sick", "health",
    )):
        return True
    environment_context = _has_any(q, (
        "pollution", "chemical water", "factory", "thermal plant", "blasting",
        "mining blast", "mine blasting", "blast cracked", "cracked my house",
        "effluent", "borewell water", "water pollution", "air pollution",
        "factory smoke", "smoke from factory", "smoke making",
        "mining company",
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
        "cracked my house", "cracked walls", "house walls", "wall cracks",
        "who to ask", "making us sick",
        "health problem", "health problems", "breathing problem",
        "cough", "asthma",
    ))
    return environment_context and damage_context


def _is_family_court_summons_issue(q: str) -> bool:
    family_forum = _has_any(q, ("family court", "family-court", "matrimonial court"))
    summons_or_notice = _has_any(q, (
        "summons", "summon", "notice", "court notice", "received",
        "appearance", "appear", "paper", "papers", "aya", "aaya",
    ))
    next_step = _has_any(q, (
        "next step", "what next", "what to do", "before lawyer", "how to complain",
        "reply", "respond", "response", "written statement", "hearing", "next date", "urgent",
        "what first step", "first step", "what to carry", "documents",
        "kya leke", "leke jana", "lawyer nahi", "advocate",
    ))
    return family_forum and summons_or_notice and next_step


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
        "power plant", "thermal plant", "hydro project", "irrigation project",
        "coal block", "coal mine", "mining", "mine", "bauxite", "bauxite project",
    ))
    community_context = _has_any(q, (
        "village", "villages", "families", "houses", "land", "forest",
        "gram sabha", "palli sabha",
    ))
    consent_or_rr_context = _has_any(q, (
        "no consent", "without consent", "consent", "gram sabha",
        "rehabilitation", "resettlement", "compensation", "no compensation",
        "submerge", "submerged", "submergence", "displaced", "displacement",
        "without consulting", "consulting palli sabha", "palli sabha", "noc",
    ))
    acquisition_or_rr_context = _has_any(q, (
        "land acquisition", "land acquired", "acquired for", "land taken",
        "displacement", "displaced", "rehabilitation", "resettlement",
        "compensation", "award", "submerge", "submerged", "submergence",
    ))
    return (
        tribal_or_scheduled_context
        and project_context
        and community_context
        and consent_or_rr_context
        and acquisition_or_rr_context
    )


def _is_minor_mineral_gram_sabha_issue(q: str) -> bool:
    minor_mineral = _has_any(q, (
        "minor mineral", "minor minerals", "sand mining", "sand lease",
        "stone quarry", "quarry lease", "quarry",
    ))
    scheduled_area = _has_any(q, (
        "gram sabha", "palli sabha", "pesa", "scheduled area",
        "tribal village", "adivasi village",
    ))
    consent_or_approval = _has_any(q, (
        "without", "no gram sabha", "not taken", "not given",
        "consent", "consultation", "recommendation", "noc", "lease",
        "approval", "challenge",
    ))
    acquisition_or_rr = _has_any(q, (
        "land acquisition", "land acquired", "acquired for", "land taken",
        "displacement", "displaced", "rehabilitation", "resettlement",
        "compensation", "award", "submerge", "submerged", "submergence",
    ))
    return minor_mineral and scheduled_area and consent_or_approval and not acquisition_or_rr


def _is_mining_gram_sabha_noc_issue(q: str) -> bool:
    mining = _has_any(q, (
        "mine", "mining", "mining company", "mining project", "mine blasting",
        "blasting", "iron ore", "coal block", "bauxite", "minerals",
    ))
    gram_sabha_or_scheduled = _has_any(q, (
        "gram sabha", "palli sabha", "pesa", "scheduled area",
        "tribal village", "adivasi village", "bastar", "west singhbhum",
    ))
    consent_or_noc = _has_any(q, (
        "no gram sabha", "without gram sabha", "without consent",
        "no consent", "noc", "resolution", "recommendation", "consultation",
        "challenge", "what can i do",
    ))
    acquisition_or_rr = _has_any(q, (
        "land acquisition", "land acquired", "acquired for", "land taken",
        "displacement", "displaced", "rehabilitation", "resettlement",
        "compensation", "award", "submerge", "submerged", "submergence",
    ))
    return mining and gram_sabha_or_scheduled and consent_or_noc and not acquisition_or_rr


def _is_section_91_notice(q: str) -> bool:
    if _has_any(q, ("35 notice", "bnss 35", "35(3)", "35 (3)", "section 35")) and not _has_any(q, (
        "section 91", "crpc 91", "91 crpc", "bnss 94", "section 94",
        "94 notice", "notice under 91", "notice under 94",
        "summons to produce", "produce document", "produce documents",
    )):
        return False
    production_context = _has_any(q, (
        "section 91", "crpc 91", "91 crpc", "bnss 94",
        "section 94", "94 notice", "notice", "summons",
        "produce", "bring", "hand over", "asked for",
        "asking for", "notice asking",
    ))
    seizure_done_context = _has_any(q, ("seized", "has been seized", "already seized", "took my laptop", "took my phone"))
    return (
        production_context
        and not (seizure_done_context and not _has_any(q, ("notice", "summons", "section 91", "section 94", "bnss 94", "crpc 91")))
        and _has_any(q, _SECTION_91_NOTICE_WORDS)
        and _has_any(q, ("police", "court", "fir", "case", "notice", "summons", "io", "investigating officer"))
    )


def _is_police_questioning_notice_issue(q: str) -> bool:
    if _has_any(q, ("civil case", "civil court", "court sent summons", "witness evidence")) and not _has_any(q, ("cyber police", "police station", "investigating officer")):
        return False
    if _is_section_91_notice(q):
        return False
    if _has_any(q, ("digital arrest",)):
        return False
    if _has_any(q, ("seized", "seizure", "release of seized", "return my phone", "release my phone")):
        return False
    police_context = _has_any(q, ("police", "thana", "station", "io", "investigating officer", "cyber cell", "cyber police"))
    notice_context = _has_any(q, (
        "notice", "called me", "calling me", "phone call", "sent notice",
        "message came", "asked me to come", "told me to come",
        "come station", "come to station", "come police station",
        "appear at station", "appear before police", "35(3)", "35 (3)",
        "35 notice", "section 35", "bnss 35",
    ))
    questioning_context = _has_any(q, (
        "questioning", "inquiry", "enquiry", "statement", "ask questions",
        "puchh taach", "pooch taach", "poochtaach", "for questioning",
        "tomorrow", "kal", "go with lawyer", "with lawyer", "go alone",
        "if i go", "can they arrest", "should i apply bail", "no arrest notice",
        "bring phone", "bring chats", "phone chats", "lawyer should not come",
        "lawyer should not", "lawyer not come", "lawyer should not come",
        "35(3)", "35 (3)", "35 notice", "section 35", "bnss 35",
    ))
    custody_or_arrest = _has_any(q, ("arrested", "detained", "custody", "lockup", "picked up", "police picked", "police took"))
    negated_arrest = _has_any(q, (
        "not arrested", "no arrest", "not in custody", "not detained",
        "does this alone mean i am arrested", "does this mean i am arrested",
        "notice alone mean", "notice mean i am arrested",
    ))
    return police_context and notice_context and questioning_context and (not custody_or_arrest or negated_arrest)


def _is_passport_procedure(q: str) -> bool:
    passport_context = "passport" in q or "pasport" in q
    return passport_context and _has_any(q, _PASSPORT_PROCEDURE_WORDS + ("criminal case", "case pending", "warrant", "summons"))


def _is_education_loan_denial(q: str) -> bool:
    loan_context = _has_any(q, ("education loan", "student loan", "loan for education", "loan for school", "loan for college"))
    bank_context = _has_any(q, ("bank", "nbfc", "not giving", "refused", "rejected", "denied", "denial", "subsidy", "interest subsidy", "moratorium"))
    education_context = _has_any(q, ("daughter", "son", "student", "scholarship", "school", "college", "course", "subsidy", "admission", "fees"))
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
    if _has_any(q, ("convicted", "after conviction", "convict")) and _has_any(q, ("parole", "furlough", "remission")):
        return False
    review_context = _has_any(q, _UNDERTRIAL_REVIEW_WORDS)
    custody_context = _has_any(q, (
        "undertrial", "jail", "prison", "custody", "tihar", "puzhal",
        "byculla", "yerwada", "paralegal", "dlsa", "legal aid",
        "half sentence", "half maximum", "half sentence rule",
    ))
    if not custody_context:
        return False
    if review_context:
        return True
    if _is_interim_medical_bail_issue(q):
        return False
    undertrial_context = "undertrial" in q
    release_delay_context = _has_any(q, (
        "release", "bail", "trial not started", "trial delay", "long custody",
        "jail since", "custody since", "half sentence", "half maximum",
        "maximum punishment", "completed half", "trial not moving",
        "chargesheet filed", "chargesheet filed but trial",
    ))
    return undertrial_context and release_delay_context


def _is_uapa_bail_or_custody_issue(q: str) -> bool:
    if not _has_uapa_context(q):
        return False
    if _is_default_bail_issue(q):
        return True
    return _has_any(q, (
        *_BAIL_WORDS,
        "43d", "43 d", "prima facie", "prima-facie",
        "trial not started", "no trial", "long custody",
        "prolonged custody", "jail", "custody", "undertrial",
    ))


def _prison_release_or_access_route(q: str) -> MatterRoute | None:
    if _has_any(q, (
        "bail application", "bail hearing", "bail pending", "pending bail",
        "next hearing", "bail order", "bail granted", "got bail",
        "granted bail", "personal bond", "cash deposit", "release warrant",
        "release order", "release memo",
    )):
        return None
    prison_records = _is_prison_records_admin_issue(q)
    prison_books = _is_prison_books_access_issue(q)
    carceral_context = _has_any(q, (
        "jail", "prison", "prisoner", "undertrial", "convict", "convicted",
        "tihar", "mandoli", "rohini jail", "rohini prison", "central jail",
        "arthur road", "yerwada", "byculla", "puzhal",
    ))
    explicit_release_context = _has_any(q, (
        "parole", "furlough", "remission", "premature release",
        "temporary release", "temporary parole", "emergency parole",
        "custody parole", "release for funeral", "funeral parole",
        "last rites", "cremation", "family death", "death in family",
        "death of mother", "death of father", "mother's funeral",
        "father's funeral", "wedding parole", "marriage parole",
        "open prison",
    ))
    generic_release_or_visit_context = (
        carceral_context
        and _has_any(q, (
            "eligible", "release", "leave", "visit", "meet", "interview",
            "mulakat", "mulaqat", "books", "book", "library", "newspaper",
            "magazine", "visitor", "visitor list", "video call", "video calls",
            "video slot", "call slot", "server down", "server error",
            "system error", "system issue", "technical issue", "written order",
        ))
    )
    custody_parole_context = _has_any(q, ("custody parole", "emergency parole", "temporary parole"))
    explicit_prison_release_without_jail_word = explicit_release_context and _has_any(q, (
        "delhi", "tihar", "mandoli", "rohini", "up ", "uttar pradesh",
        "maharashtra", "tamil nadu", "rajasthan", "state rule",
        "good conduct", "reasoned order", "competent authority",
    ))
    if not (prison_records or prison_books or custody_parole_context or explicit_prison_release_without_jail_word or (carceral_context and (explicit_release_context or generic_release_or_visit_context))):
        return None

    visit_problem_context = _has_any(q, (
        "mulaqat cancelled", "mulakat cancelled", "visit cancelled",
        "video call slot failed", "video slot failed", "call slot failed",
        "server down", "server error", "system error", "system issue",
        "technical issue", "video call failed", "video call cancelled",
        "visitor list", "deny family mulaqat", "denied family mulaqat",
        "jail deny", "jail denied", "not allowing visit",
        "not allowing mulaqat", "not allowing mulakat",
    ))
    prison_visit = prison_books or (not explicit_release_context and _has_any(q, (
        "mulaqat", "mulakat", "interview", "visit", "visitation",
        "visitor", "visitor list", "meet", "wife", "husband",
        "phone call", "family call", "video call", "video calls",
        "video slot", "call slot",
    ))) or visit_problem_context
    if prison_records:
        return _prison_records_route(q)
    return MatterRoute(
        category="prison_mulaqat" if prison_visit else "prison_parole_furlough",
        label=(
            "Prison books / mulaqat access"
            if prison_books
            else "Prison mulaqat / interview access"
            if prison_visit
            else "Prison parole / furlough / remission"
        ),
        confidence=0.78 if custody_parole_context else 0.74,
        urgency="high" if _has_any(q, ("funeral", "last rites", "cremation", "death", "medical emergency", "emergency")) else "medium",
        required_sources=(
            [
                "state prison rules / prison manual for interviews, visits, and permitted books",
                "Prisons Act 1894 where applicable",
                "Article 21 constitutional safeguards where custody conditions are arbitrary",
            ]
            if prison_visit
            else [
                "Prisons Act 1894",
                "Article 21 constitutional safeguards where custody conditions are involved",
            ]
        ),
        forums=(
            ["prison superintendent", "District Legal Services Authority", "prison visitors board where available", "High Court writ jurisdiction where needed"]
            if prison_visit
            else ["prison superintendent", "state parole/furlough authority", "District Legal Services Authority", "High Court writ jurisdiction where needed"]
        ),
        missing_facts=(
            ["state/prison", "undertrial or convicted status", "relationship to prisoner", "current mulaqat/books rule or order", "refusal or restriction reason"]
            if prison_visit
            else ["state/prison", "conviction or undertrial status", "sentence/offence details", "time already served", "reason for parole/furlough"]
        ),
        red_flags=_red_flags(q),
        action_pack=_prison_mulaqat_pack() if prison_visit else _prison_release_pack(),
    )


def _is_prison_books_access_issue(q: str) -> bool:
    prison_context = _has_any(q, ("jail", "prison", "tihar", "mandoli", "rohini"))
    if not prison_context:
        return False
    return re.search(r"\b(?:book|books|library|newspaper|magazine|reading material)\b", q) is not None


def _is_interim_medical_bail_issue(q: str) -> bool:
    custody_context = _has_any(q, (
        "jail", "prison", "prisoner", "custody", "undertrial", "undertrials",
        "byculla", "arthur road", "tihar", "puzhal", "yerwada",
        "mandoli", "rohini", "district jail", "paralegal",
    ))
    medical_context = _has_any(q, (
        "pregnant", "pregnancy", "new born", "newborn", "medical",
        "doctor", "hospital", "treatment", "tb", "tuberculosis", "medicine",
        "medicines", "chest pain", "heart pain", "heart patient", "depression",
        "psychiatrist", "psychiatric", "mental", "self harm", "suicide",
        "vomiting", "injury", "diabetic", "insulin", "outside hospital",
        "medical report", "heart blockage", "wheelchair", "assault by inmates",
        "medical examination", "medical records", "dental", "dentist",
        "doctor appointment", "jail doctor appointment",
    ))
    bail_context = _has_any(q, (
        "bail", "interim bail", "medical bail", "postpone trial",
        "postpone", "release", "custody", "court", "which court",
        "legal step", "order outside hospital", "family file", "family wants",
        "can court", "move court",
    ))
    care_denial_context = _has_any(q, (
        "not getting hospital", "hospital checkup", "hospital check-up",
        "not getting checkup", "not getting check-up", "not getting treatment",
        "not getting medicines", "not getting medicine",
        "doctor not seeing", "doctor not coming", "medical care denied",
        "medicine not given", "test not done", "checkup", "check-up",
        "medicine stopped", "medicines stopped", "medicine missed",
        "medicines missed", "missed for", "not giving report",
        "doctor not giving report", "no doctor visit", "says wait",
        "hospital says wait", "jail hospital says wait", "not arranged",
        "not giving medicine", "not giving medicines",
        "medical report hidden", "report hidden", "stopped insulin",
        "insulin stopped", "no outside hospital referral", "outside doctor",
        "no report", "cannot walk", "refuses medical aid",
        "doctor appointment", "jail doctor appointment", "ask jail doctor",
        "family ask jail doctor", "not giving psychiatric help",
        "psychiatric help", "suicidal undertrial", "urgent hospital direction",
    ))
    return custody_context and medical_context and (bail_context or care_denial_context)


def _is_bail_release_delay_issue(q: str) -> bool:
    if _is_bail_surety_hardship_issue(q) and _has_any(q, (
        "two local", "2 local", "local surety", "local sureties",
        "cannot arrange", "can't arrange", "cant arrange",
        "unable to arrange", "amount high", "surety amount high",
        "high surety", "too high", "unaffordable", "migrant", "migrants",
    )):
        return False
    bail_order_context = _has_any(q, (
        "bail order", "bail granted", "got bail", "granted bail",
        "court granted bail", "bail allowed", "release order",
        "release warrant", "release memo", "court ordered release",
        "high court granted bail", "sessions court granted bail",
        "trial court granted bail",
    ))
    jail_nonrelease_context = _has_any(q, (
        "jail not releasing", "not releasing", "not released",
        "still in jail", "still inside", "release pending",
        "not sent release", "release warrant not reached",
        "release warrant has not come", "warrant has not come",
        "warrant not received", "e-copy not received", "e copy not received",
        "e-copy not received", "surety acceptance delayed",
        "cash deposit before release", "demands cash deposit",
        "demanding cash deposit", "clerk demands cash", "jail clerk demands",
        "personal bond but", "cash before release", "prison says",
        "jail says",
    ))
    verification_context = _has_any(q, (
        "surety verification", "verification pending", "surety pending",
        "local surety verification", "police verification pending",
        "10 days", "ten days", "many days", "delay", "cash deposit",
        "personal bond", "bond allowed",
    ))
    return bail_order_context and jail_nonrelease_context and (
        verification_context
        or "surety" in q
        or "release warrant" in q
        or "e-copy" in q
        or "e copy" in q
        or "court ordered release" in q
        or "high court granted bail" in q
    )


def _is_bail_surety_hardship_issue(q: str) -> bool:
    surety_context = _has_any(q, (
        "surety", "sureties", "local surety", "local sureties",
        "bail bond", "bond amount", "personal bond",
    ))
    hardship_context = _has_any(q, (
        "migrant", "migrants", "no local", "two local", "2 local",
        "cannot arrange", "can't arrange", "cant arrange", "unable to arrange",
        "unaffordable", "too high", "amount high", "surety amount high",
        "high surety", "poor", "no one local", "release blocked",
    ))
    court_or_bail_context = _has_any(q, (
        "court asked", "court ordered", "bail", "release", "jail",
        "accused", "case", "magistrate",
    ))
    surety_amount_context = _has_any(q, (
        "surety amount", "surety money", "surety condition",
        "surety conditions", "bond amount",
    ))
    return surety_context and hardship_context and (court_or_bail_context or surety_amount_context)


def _is_police_station_coercive_questioning_issue(q: str) -> bool:
    police_station_context = _has_any(q, ("police", "station", "thana", "crime branch", "io", "investigating officer"))
    coercion_context = _has_any(q, (
        "keep me in station", "keep me at station", "whole night",
        "overnight", "sign statement", "don't sign statement",
        "dont sign statement", "if i don't sign", "if i dont sign",
        "force me to sign", "forced to sign", "threatening to keep",
        "confession statement", "only after confession", "inside station",
        "inside lockup", "won't let advocate", "wont let advocate",
        "will not let advocate", "lawyer can meet only after",
        "forced blank paper", "forced to sign blank paper",
    ))
    same_day_detention_context = _has_any(q, (
        "since morning", "10 hours", "ten hours", "phone switched off",
        "phone off", "not reachable",
    ))
    negated_arrest = _has_any(q, ("not arrested", "no arrest", "not in custody", "not detained"))
    return police_station_context and (coercion_context or same_day_detention_context) and (
        negated_arrest or "statement" in q or "lockup" in q or "advocate" in q
        or "lawyer" in q or same_day_detention_context
    )


def _is_prison_records_admin_issue(q: str) -> bool:
    carceral_context = _has_any(q, (
        "jail", "prison", "prisoner", "undertrial", "convict",
        "tihar", "mandoli", "rohini", "arthur road", "yerwada",
        "byculla", "puzhal",
    ))
    records_context = _has_any(q, (
        "money order", "canteen", "account detail", "account details",
        "prison account", "jail account", "nominal roll", "custody certificate",
        "bail rejection order", "order copy", "copy of order", "certified copy",
        "record can ask", "records can ask", "record copy", "records copy",
        "not getting account", "jail records", "prison records",
        "ledger copy", "no ledger copy", "ledger", "canteen balance",
        "balance missing",
    ))
    return carceral_context and records_context


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


def _is_sexual_offence_accused_issue(q: str) -> bool:
    if _has_any(q, (
        "survivor wants", "victim wants", "complainant wants",
        "oppose bail", "oppose anticipatory bail", "cancel bail",
        "bail of accused", "accused bail",
    )):
        return False
    third_party_or_helper_context = _has_any(q, (
        "another teacher", "another man", "another person", "someone else",
        "other teacher", "other man", "other person", "against another",
        "against someone else", "abused her", "abused him", "help her",
        "help him", "what should we do for her", "what should we do for him",
    ))
    if third_party_or_helper_context and not _has_any(q, (
        "against me", "on me", "fir against me", "case against me",
        "complaint against me", "accused me", "i am accused", "i'm accused",
    )):
        return False
    offence_context = _has_any(q, ("pocso", "rape", "sexual assault", "molest", "molestation"))
    accused_context = _has_any(q, (
        "case against me", "filed against me", "filed a case against me",
        "complaint against me", "fir against me", "against me",
        "on me", "i am accused", "accused me", "accused of",
        "need bail", "anticipatory bail", "regular bail", "defend",
    ))
    complainant_relation_context = (
        _has_any(q, (
            "my girlfriend filed", "girlfriend filed", "my ex filed",
            "ex girlfriend filed", "ex-girlfriend filed", "my wife filed",
            "wife filed", "my partner filed", "partner filed",
        ))
        and _has_any(q, ("complaint", "case", "fir", "rape", "pocso", "sexual"))
        and not third_party_or_helper_context
    )
    accused_context = accused_context or complainant_relation_context
    return offence_context and accused_context


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
    if _has_any(q, (
        "no police beating involved", "nobody was detained or beaten",
        "nobody detained or beaten", "no one was detained or beaten",
        "not detained or beaten", "no custody or beating",
    )):
        return False
    if _has_any(q, ("custody parole", "emergency parole", "parole", "furlough", "remission")) and not _has_any(q, (
        "custodial death", "lockup death", "police torture", "torture",
        "beaten", "beating", "assault", "injury", "slap", "slapped",
        "bribe", "money for release", "demanded money", "took cash",
        "took money", "not released", "refused to release",
    )):
        return False
    person_custody = _has_any(q, (
        "lockup", "custody", "detained", "detention", "arrest", "arrested",
        "after arrest", "jail", "prison",
        "custodial death", "lockup death",
        "during questioning", "police questioning",
        "not released me", "not released him", "not released her",
        "did not release me", "did not release him", "did not release her",
        "not released my brother", "not released my husband",
        "still not released", "kept me", "kept my brother",
    ))
    custody_authority_context = _has_any(q, (
        "lockup", "custody", "custodial", "constable", "police station",
        "thana", "jail", "prison", "jail guard", "prison guard",
    ))
    direct_official_abuse = _has_any(q, (
        "police beat", "police beating", "police tortured", "police torture",
        "police assaulted", "police hurt", "police injured",
        "constable beat", "constable hurt", "officer beat", "officer hurt",
    ))
    # A station name plus a private assault/FIR refusal is not custodial
    # violence. Require an actual custody fact, unless the prompt directly
    # alleges abuse by an officer.
    police_context = direct_official_abuse or (custody_authority_context and person_custody)
    violence = _has_any(q, (
        "beaten", "beat", "beating", "torture", "assault", "injury", "hurt",
        "death", "died", "suicide", "hanging", "slap", "slapped",
    ))
    extortion = _has_any(q, (
        "took 20000", "bribe", "money for bail", "money for release",
        "paid for bail", "demanded money", "took cash", "took money",
    ))
    release_blocked = person_custody and _has_any(q, (
        "not released", "still not released", "did not release",
        "refused to release", "kept in lockup", "kept in custody",
        "kept my brother in custody", "kept my husband in custody",
    ))
    return police_context and (violence or extortion or release_blocked)


def _is_domestic_residence_issue(q: str) -> bool:
    if _is_wife_as_aggressor_issue(q):
        return False
    if _is_child_family_issue(q) and _has_any(q, (
        "child", "son", "daughter", "not sharing school", "school location",
        "not allowing father", "not allowing mother", "weekend meeting",
    )):
        return False
    residence_loss = _has_any(q, (
        "ghar se nikal", "nikal diya", "threw me out", "kicked me out",
        "throws me out", "throwing me out", "thrown me out",
        "throws us out", "throwing us out", "thrown out", "throw out",
        "removed from home", "forced out", "not allowing me in",
        "not letting me enter", "shared household", "shared house",
        "kept my documents", "keeping my documents", "documents kept",
        "house in mother in law name", "house is in mother in law name",
        "home in mother in law name", "matrimonial home",
    ))
    marital_context = _has_any(q, (
        "husband", "wife", "spouse", "sasural", "in laws", "in-laws",
        "husband family", "wife family", "married", "marriage",
    ))
    return residence_loss and marital_context


def _is_family_domestic_notice_response_issue(q: str) -> bool:
    if _has_any(q, ("498a", "498 a", "section 85", "sec 85", "bns 85", "anticipatory bail", "regular bail", "get bail")):
        return False
    if _has_any(q, ("fir", "arrest", "arrest notice", "police case", "criminal case")) and not _has_any(q, (
        "no fir", "without fir", "only notice", "just notice", "no police case", "no criminal case",
        "no arrest notice", "without arrest notice", "no police notice",
        "without police notice", "only summons", "only court summons",
    )):
        return False
    respondent_context = _has_any(q, (
        "against me", "filed on me", "filed against me", "case on me",
        "notice to me", "i have notice", "received notice", "summons",
        "sent me notice", "notice sent to me", "served notice",
        "served me notice", "complaint notice", "police sent me notice",
        "notice reply", "reply notice", "reply", "respond",
        "what do i reply", "how to reply", "defend", "false case",
        "false domestic violence", "false dv",
    ))
    spouse_filed_case_context = _has_any(q, (
        "wife filed domestic violence", "wife has filed domestic violence",
        "wife filed dv", "wife has filed dv", "dv case against me",
        "domestic violence case against me",
    )) and _has_any(q, (
        "next date", "hearing", "court date", "date tomorrow",
        "legal aid", "free lawyer", "lawyer", "reply", "respond",
    ))
    domestic_case_context = _has_any(q, (
        "domestic violence", "dv case", "pwdva", "protection order",
        "maintenance case", "residence order",
    ))
    return (respondent_context or spouse_filed_case_context) and domestic_case_context


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


def _is_household_drug_safety_issue(q: str) -> bool:
    if _has_any(q, ("digital arrest", "fake cbi", "fake police call", "otp", "upi", "send money", "paid", "transferred", "lost money")):
        return False
    if _has_any(q, ("police caught", "arrest", "arrested", "fir", "case", "bail", "seized", "seizure memo", "passport seized")):
        return False
    if _is_drug_treatment_support_context(q):
        return False
    household_context = _has_any(q, (
        "my husband", "my wife", "spouse", "at home", "in my house",
        "in our house", "family member", "my son", "my daughter",
        "my brother", "my sister",
    ))
    possession_context = _has_any(q, (
        "with drugs", "has drugs", "keeping drugs", "keeps drugs",
        "drug packet", "narcotics",
        "ganja", "weed", "charas", "mdma", "heroin", "cannabis",
    ))
    use_context = _has_any(q, ("using drugs", "taking drugs"))
    danger_context = _has_any(q, (
        "threat", "threaten", "violence", "violent", "unsafe", "danger",
        "beating", "hit", "assault", "overdose", "unconscious", "child",
        "minor",
    ))
    discovery_context = _has_any(q, ("caught", "found", "saw", "what should i do", "what to do"))
    return household_context and discovery_context and (possession_context or (use_context and danger_context))


def _is_drug_treatment_support_issue(q: str) -> bool:
    if not _is_drug_treatment_support_context(q):
        return False
    drug_context = _has_any(q, (
        "drug", "drugs", "ganja", "weed", "charas", "mdma", "heroin",
        "cannabis", "narcotic", "substance abuse",
    ))
    help_context = _has_any(q, (
        "help", "treatment", "rehab", "rehabilitation", "deaddiction",
        "de-addiction", "counselling", "counseling", "doctor", "quit",
        "stop", "addicted", "addiction",
    ))
    family_or_user_context = _has_any(q, (
        "my husband", "my wife", "my son", "my daughter", "my brother",
        "my sister", "family", "spouse", "i am", "i'm", "myself",
    ))
    return drug_context and help_context and family_or_user_context


def _is_drug_treatment_support_context(q: str) -> bool:
    treatment_context = _has_any(q, (
        "addicted", "addiction", "rehab", "rehabilitation", "treatment",
        "deaddiction", "de-addiction", "counselling", "counseling",
        "doctor", "needs help", "need help", "get help", "quit drugs",
        "stop drugs",
    ))
    hard_safety_or_possession_context = _has_any(q, (
        "with drugs", "has drugs", "keeping drugs", "keeps drugs",
        "drug packet", "contraband", "found ganja", "found weed",
        "found charas", "found mdma", "found heroin", "threat",
        "violence", "violent", "beating", "hit", "assault", "unsafe",
        "danger", "overdose", "unconscious",
    ))
    return treatment_context and not hard_safety_or_possession_context


def _is_completed_suicide_legal_issue(q: str) -> bool:
    suicide_context = _has_any(q, (
        "committed suicide", "died by suicide", "made worker commit suicide",
        "made employee commit suicide", "commit suicide", "suicide note",
        "suicide after", "suicide due to", "abetment of suicide",
    ))
    legal_context = _has_any(q, (
        "case", "fir", "complaint", "police", "harassment", "harass",
        "employer", "company", "manager", "family wants", "post mortem",
        "post-mortem", "inquest", "threat", "threatened",
    ))
    current_crisis_context = _has_any(q, (
        "i want", "i will", "myself", "says he will", "says she will",
        "threatening suicide", "threatens suicide", "wants to commit",
    ))
    return suicide_context and legal_context and not current_crisis_context


def _is_adult_family_violence_issue(q: str) -> bool:
    explicit_adult_child_to_parent_context = (
        _has_any(q, (
            "adult son", "adult daughter", "grown up son", "grown-up son",
            "grown up daughter", "grown-up daughter",
        ))
        or re.search(r"\b(?:my|our)?\s*(?:son|daughter)\s+(?:is\s+)?(?:aged?\s+)?(?:1[89]|[2-9]\d)\b", q) is not None
    )
    parent_child_relation_context = _has_any(q, (
        "my son", "my daughter", "our son", "our daughter", "his son",
        "her son", "his daughter", "her daughter",
    ))
    parent_victim_context = _has_any(q, (
        "mother", "father", "parent", "parents", "old mother", "old father",
        "elderly mother", "elderly father",
    ))
    violence_context = _has_any(q, (
        "beats", "beating", "beat ", "hit", "hitting", "slap", "slapped",
        "assault", "hurt", "injury", "threat", "threatens", "threatened",
        "locked", "not giving food", "throws out", "threw out",
    ))
    explicit_minor_context = _has_age_under(q, 18) or _has_any(q, (
        "minor son", "minor daughter", "school child", "school going",
        "school-going", "teenage son", "teenage daughter",
    ))
    implied_adult_family_context = parent_child_relation_context and parent_victim_context and not explicit_minor_context
    return (explicit_adult_child_to_parent_context or implied_adult_family_context) and parent_victim_context and violence_context


def _is_child_household_assault_issue(q: str) -> bool:
    adult_child_context = _has_any(q, (
        "adult son", "adult daughter", "grown up son", "grown-up son",
        "grown up daughter", "grown-up daughter",
    )) or re.search(
        r"\b(?:my|our)?\s*(?:son|daughter|child)\s+(?:is\s+)?(?:aged?\s+)?(?:1[89]|[2-9]\d)\b",
        q,
    ) is not None
    if adult_child_context:
        return False
    explicit_minor_context = _has_age_under(q, 18) or _has_any(q, (
        "minor child", "minor son", "minor daughter", "kid", "baby",
        "school child", "school going", "school-going", "teenage son",
        "teenage daughter",
    ))
    generic_child_context = _has_any(q, ("my child", "our child", "my son", "my daughter", "our son", "our daughter"))
    parent_victim_context = _has_any(q, (
        "his mother", "her mother", "his father", "her father", "their mother",
        "their father", "my mother", "my father", "parents", "parent",
    ))
    if generic_child_context and parent_victim_context and not explicit_minor_context:
        return False
    child_context = explicit_minor_context or generic_child_context
    assault_context = _has_any(q, (
        "beating", "beats", "beat ", "beat my", "hit", "hitting",
        "slap", "slapped", "assault", "hurt", "injury",
    ))
    household_actor_context = _has_any(q, (
        "my wife", "my husband", "mother", "father", "stepfather",
        "stepmother", "guardian", "family", "at home", "house",
    ))
    return child_context and assault_context and household_actor_context


def _is_caste_bonded_labour_issue(q: str) -> bool:
    protected_class_context = _has_any(q, (
        "dalit", "scheduled caste", "scheduled tribe", "sc/st", "sc st",
        "adivasi", "tribal", "caste slur", "caste name", "untouchable",
        "chamar", "munda", "sarna", "pahan",
    )) or re.search(r"\b(?:sc|st)\b", q) is not None
    _ = _has_any(q, (
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
        "parcel has drugs", "drug parcel", "drug packet", "drugs in parcel",
        "narcotics parcel", "contraband parcel",
    ))
    enforcement_context = _has_any(q, (
        "caught", "police", "case", "fir", "arrest", "bail", "seized",
        "airport", "customs", "passport seized", "legal in goa", "punishment",
        "raid", "section 37", "fsl", "lab report", "state excise", "source applies",
    ))
    return substance_context and enforcement_context


def _is_motor_vehicle_traffic_police_issue(q: str) -> bool:
    if _is_street_vendor_municipal(q):
        return False
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
    licensing_context = _has_any(q, (
        "liquor shop", "wine shop", "bar license", "bar licence",
        "liquor license", "liquor licence", "excise license",
        "excise licence", "license cancelled", "licence cancelled",
        "license canceled", "licence canceled", "license renewal",
        "licence renewal", "renewal delayed", "shop license",
        "shop licence", "trade license", "trade licence",
    ))
    accused_context = _has_any(q, (
        "fir", "arrest", "arrested", "seized", "seizure", "caught",
        "caught me drinking", "case on me", "filed on me", "accused",
        "bail", "punishment", "thana", "police caught",
    ))
    if licensing_context and not accused_context:
        return False

    alcohol_context = _has_any(q, (
        "prohibition law", "excise act", "liquor case", "alcohol case",
        "drinking village", "caught me drinking", "drinking alcohol",
        "with alcohol", "desi daru", "sharab", "liquor", "wine shop",
        "selling alcohol", "sell alcohol", "selling liquor", "sell liquor",
        "alcohol without", "liquor without", "license expired",
        "licence expired",
        "bihar prohibition", "state prohibition", "prohibition case",
    ))
    enforcement_context = _has_any(q, (
        "police", "thana", "case", "fir", "caught", "punishment",
        "arrest", "bail", "section", "notice", "what can i do",
    ))
    return alcohol_context and enforcement_context


def _is_cattle_transport_accused_issue(q: str) -> bool:
    if _is_agri_cooperative_recovery_issue(q):
        return False
    cattle_context = _has_any(q, (
        "cattle", "cow", "buffalo", "ox", "bullock", "calf", "livestock",
        "gau", "gauraksha", "cow slaughter", "animal preservation",
        "cattle preservation",
    ))
    transport_or_slaughter_context = _has_any(q, (
        "transport", "transporting", "taking", "took", "mandi", "market",
        "slaughter", "smuggling", "smuggle", "vehicle seized", "animal seized",
        "seized animal", "seized vehicle",
    ))
    accused_or_enforcement_context = _has_any(q, (
        "arrest", "arrested", "bail", "custody", "jail", "police", "fir",
        "case", "section", "accused", "smuggling", "gauraksha", "seized",
    ))
    return cattle_context and transport_or_slaughter_context and accused_or_enforcement_context


def _has_scst_protected_status(q: str) -> bool:
    return bool(re.search(r"\b(?:sc|st)\b", q)) or _has_any(q, (
        "dalit", "scheduled caste", "scheduled tribe", "sc/st", "sc st",
        "adivasi", "tribal", "munda", "sarna", "pahan", "gond",
        "untouchable",
    ))


def _is_scst_poa_procedure_issue(q: str) -> bool:
    poa_context = _has_any(q, ("poa", "poa act", "atrocity", "sc/st", "sc st", "caste atrocity", "poa case"))
    procedure_context = _has_any(q, (
        "dsp", "sp not", "transferring", "investigation", "officer rank",
        "special court", "pending", "5 years", "five years", "delay",
    ))
    return poa_context and procedure_context


def _is_scst_poa_dsp_investigation_issue(q: str) -> bool:
    poa_context = _has_any(q, ("poa", "poa act", "atrocity", "sc/st", "sc st", "caste atrocity", "poa case"))
    dsp_context = _has_any(q, (
        "dsp", "deputy superintendent", "rule 7", "rule-7",
        "sp not", "transferring", "transfer to dsp",
        "investigating officer", "investigation officer", "officer rank",
    ))
    return poa_context and dsp_context


def _is_accused_scst_false_poa_issue(q: str) -> bool:
    poa_context = _has_any(q, (
        "false poa", "poa case", "false atrocity", "sc/st case",
        "sc st case", "atrocity case", "poa",
    ))
    direct_accused_context = _has_any(q, (
        "accused", "filed against me", "false case", "false complaint",
        "stealing", "theft", "chicken", "chickens",
    ))
    against_me_case_context = _has_any(q, ("against me", "put on them", "put on me")) and _has_any(q, (
        "case", "complaint", "fir", "stealing", "theft", "false",
        "chicken", "chickens",
    ))
    return poa_context and (direct_accused_context or against_me_case_context)


def _is_caste_violence_priority_issue(q: str) -> bool:
    protected_context = _has_scst_protected_status(q) or _has_any(q, (
        "caste name", "caste slur", "upper caste", "dominant caste",
        "chamar", "bastar",
    ))
    harm_context = _has_any(q, (
        "beat", "beaten", "attack", "attacked", "called", "calling",
        "untouchable", "caste name", "slur", "outside school",
        "sarpanch", "mob", "threat",
    ))
    return protected_context and harm_context


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


def _is_company_strikeoff_restore_issue(q: str) -> bool:
    company_context = _has_any(q, (
        "company", "private limited", "pvt ltd", "roc", "mca", "cin",
        "company master", "bank operations", "gst refund",
    ))
    strikeoff_context = _has_any(q, (
        "struck off", "strike off", "striking off", "restore", "restoration",
        "revive", "revival", "section 248", "section 252",
    ))
    return company_context and strikeoff_context


def _is_disabled_child_abandonment_issue(q: str) -> bool:
    disability_child = _has_any(q, (
        "disabled baby", "baby with disability", "disabled child",
        "child with disability", "disability baby", "special child",
    ))
    abandonment_pressure = _has_any(q, (
        "leave", "leave baby", "leave the baby", "abandon", "abandoned",
        "hospital", "give away", "throw out", "not take home", "refuse to take",
        "in laws want", "in-laws want", "pressure",
    ))
    return disability_child and abandonment_pressure


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
        "designated officer", "food authority", "health department",
        "food inspector", "food inspection",
    ))
    food_business_context = _has_any(q, (
        "snack manufacturing", "kirana", "masala", "packet", "food business",
        "restaurant", "dhaba", "canteen", "hotel", "kitchen", "small hotel",
    ))
    compliance_context = _has_any(q, (
        "licence", "license", "notice", "renewal", "category",
        "central licence", "central license", "state licence", "state license",
        "sample", "adulteration", "misbranding", "improvement notice",
        "sealed", "seal", "sealing", "closed", "closure", "inspection",
        "inspection report",
    ))
    return (food_authority_context or food_business_context) and compliance_context


def _is_digital_money_platform_issue(q: str) -> bool:
    if _is_crypto_wallet_transfer_fraud_issue(q):
        return False
    tax_context = _has_any(q, _TAX_GST_WORDS) or _has_any(q, ("tax on winnings", "file itr"))
    dispute_context = _has_any(q, (
        "froze", "frozen", "blocked", "support not replying", "not allowing",
        "withdraw", "withdrawal", "refund", "money stuck", "no payout",
    ))
    if tax_context and not dispute_context:
        return False
    platform_money = _has_any(q, (
        "binance", "crypto exchange", "usdt", "wallet", "dream11",
        "parimatch", "betting app", "rummy", "online gaming",
        "fantasy app", "gaming app", "real money game",
    ))
    money_or_freeze = _has_any(q, (
        "froze", "frozen", "blocked", "blocked my account", "suspicious",
        "lost", "recover", "money", "lakh", "50k", "withdraw",
        "withdrawal", "winning amount", "winnings", "support not replying",
    ))
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


def _is_medical_negligence_consumer_issue(q: str) -> bool:
    if _has_any(q, ("jail", "prison", "custody", "lockup", "arthur road", "undertrial")):
        return False
    if _is_esi_benefit_issue(q):
        return False
    if _is_civil_registration_record_issue(q):
        return False
    medical_context = _has_any(q, (
        "hospital", "doctor", "clinic", "nursing home", "surgeon",
        "operation", "operated", "surgery", "icu",
    ))
    harm_context = _has_any(q, (
        "wrong leg", "wrong limb", "wrong surgery", "wrong operation",
        "operated wrong", "wrong injection", "negligence", "died",
        "death", "passed away", "doctor injection mistake", "injection mistake",
        "compensation", "without consent", "refused to treat",
        "wrong treatment", "medical records", "case papers",
        "hospital records", "not giving records", "not giving medical records",
        "refusing case papers", "detailed bill", "overcharge", "overcharged",
        "extra charge", "no receipt", "not giving bill",
    ))
    return medical_context and harm_context


def _is_army_service_pension_issue(q: str) -> bool:
    pension_context = _has_any(q, (
        "family pension", "service pension", "widow pension", "pension",
        "no pension", "pension denied", "pension pending", "pension not started",
    ))
    service_context = _has_any(q, (
        "army", "military", "defence", "defense", "soldier", "jawan",
        "sepoy", "ex serviceman", "ex-serviceman", "record office",
        "pension disbursing", "pcda", "ppo", "zila sainik", "regiment",
    ))
    beneficiary_context = _has_any(q, (
        "widow", "husband died", "husband death", "husband passed away",
        "my husband", "wife", "family pension", "death certificate",
        "ppo", "documents", "papers",
    ))
    contractor_context = _has_any(q, (
        "civilian contractor", "contractor", "vendor", "outsourced",
        "canteen contractor", "security contractor",
    ))
    return pension_context and service_context and beneficiary_context and not contractor_context


def _is_decree_execution_issue(q: str) -> bool:
    decree_context = _has_any(q, (
        "judgment debtor", "judgement debtor", "money decree", "decree passed",
        "decree amount", "decree holder", "decree money", "decree execution",
        "execution of decree", "order 21", "order xxi",
    ))
    execution_action = _has_any(q, (
        "not paying", "not paid", "no payment", "refusing to pay",
        "stopped paying", "execute", "execution", "attach", "attachment",
        "attach property", "civil court procedure", "property attachment",
    ))
    return decree_context and execution_action


def _is_trademark_marketplace_brand_issue(q: str) -> bool:
    if _has_negated_trademark_context(q):
        return False
    brand_context = _has_any(q, (
        "registered brand", "brand name", "my brand", "our brand",
        "trademark", "trade mark", "logo", "counterfeit", "fake products",
        "fake product", "fake items", "fake item", "fake goods",
    ))
    marketplace_context = _has_any(q, (
        "amazon", "flipkart", "marketplace", "online seller",
        "third party seller", "third-party seller", "seller", "listing",
        "takedown", "take down", "ip complaint",
    ))
    misuse_context = _has_any(q, (
        "fake", "counterfeit", "using my brand", "using our brand",
        "takedown", "not working", "ignored", "not removing", "infringement",
        "passing off",
    ))
    buyer_refund_context = _has_any(q, (
        "refund", "return", "damaged phone", "warranty", "my order",
        "order id", "delivered damaged", "replacement",
    ))
    return brand_context and marketplace_context and misuse_context and not buyer_refund_context


def _is_business_confidentiality_issue(q: str) -> bool:
    no_nda_context = _has_any(q, (
        "no nda", "without nda", "no non disclosure", "no non-disclosure",
        "not signed nda", "nda not signed",
    ))
    protected_data_context = _has_any(q, (
        "customer list", "client list", "customer database", "customer data",
        "client database", "trade secret", "confidential", "confidentiality",
        "pricing data", "copied data", "downloaded data",
    ))
    if no_nda_context and not protected_data_context:
        return False
    business_actor = _has_any(q, (
        "former employee", "ex employee", "ex-employee", "sales manager",
        "employee", "manager", "staff", "competitor", "rival", "business",
        "company", "client", "customer",
    ))
    confidential = _has_any(q, (
        "nda", "non disclosure", "non-disclosure", "confidential",
        "confidentiality", "customer list", "client list", "customer database",
        "customer data", "client database", "trade secret", "pricing",
        "database",
    ))
    misuse = _has_any(q, (
        "using", "misuse", "misusing", "joined competitor", "joined rival",
        "rival", "competitor", "poach", "poaching", "leak", "leaked",
        "downloaded", "copied", "enforce", "injunction",
        "civil court remedy",
    ))
    return business_actor and confidential and misuse


def _is_employment_noncompete_contract_issue(q: str) -> bool:
    employment_context = _has_any(q, (
        "employee", "employer", "company", "job", "employment contract",
        "offer letter", "joined competitor", "joining competitor",
        "joined rival", "joining rival", "resigned", "resignation",
    ))
    restraint_context = _has_any(q, (
        "non compete", "non-compete", "restraint of trade",
        "cannot join competitor", "can't join competitor",
        "not join competitor", "working for competitor",
    ))
    enforceability_context = _has_any(q, (
        "enforceable", "valid", "legal", "clause", "notice", "threat",
        "sue", "injunction", "stop me", "restrict", "restriction",
    ))
    confidential_data_context = _has_any(q, (
        "customer list", "customer database", "client list", "client database",
        "trade secret", "confidential data", "copied", "downloaded",
    ))
    return employment_context and restraint_context and enforceability_context and not confidential_data_context


def _is_environment_pil_pollution_issue(q: str) -> bool:
    if _has_any(q, (
        "no public pil", "not public pil", "not a pil", "not pil",
        "no pil", "only my house", "only my flat", "only our house",
        "private compensation", "just compensation",
    )):
        return False
    pil_context = _has_any(q, (
        "pil", "public interest litigation", "high court", "article 226",
        "writ", "ngt", "national green tribunal",
    ))
    pollution_context = _has_any(q, (
        "pollution", "polluting", "factory", "chemical factory", "water",
        "drinking water", "effluent", "chemical", "chemicals", "air",
        "smoke", "waste", "toxic", "environment",
    ))
    public_context = _has_any(q, (
        "people", "public", "village", "nearby", "residents", "community",
        "many families", "children", "public interest",
    ))
    ordinary_municipal_context = _has_any(q, (
        "shop sealed", "trade license", "licence renewal", "license renewal",
        "property tax", "building notice",
    ))
    return pil_context and pollution_context and public_context and not ordinary_municipal_context


def _is_municipal_garbage_nuisance_issue(q: str) -> bool:
    garbage_context = _has_any(q, (
        "garbage", "dumping", "dumped", "waste", "solid waste",
        "trash", "rubbish", "sewage", "drain", "open drain",
        "dumping garbage", "throwing garbage",
    ))
    local_body_context = _has_any(q, (
        "municipal", "municipality", "corporation", "ward", "sanitation",
        "health officer", "nagar nigam", "nagar palika", "panchayat",
        "local body", "complaint",
    ))
    no_action_context = _has_any(q, (
        "no action", "not acting", "ignored", "not replying", "complaint",
        "complain", "where to complain", "what to do",
    ))
    private_party_context = _has_any(q, ("neighbour", "neighbor", "near house", "near my house", "society"))
    return garbage_context and local_body_context and (no_action_context or private_party_context)


def _has_negated_trademark_context(q: str) -> bool:
    return _has_any(q, (
        "not trademark", "not a trademark", "no trademark", "not trade mark",
        "no trade mark", "not ip", "not an ip", "only refund",
        "just refund", "ordinary refund",
    ))


def _is_software_copyright_license_issue(q: str) -> bool:
    generic_business_portal_context = _has_any(q, (
        "shop registration", "business registration", "registration portal",
        "license renewal", "licence renewal", "renewal pending",
        "portal error", "portal software error", "excise department",
        "bar license", "bar licence", "liquor license", "liquor licence",
        "shop license", "shop licence", "trade license", "trade licence",
    ))
    software_enforcement_context = _has_any(q, (
        "unlicensed", "pirated", "copyright", "infringement", "audit",
        "vendor sent", "vendor notice", "legal notice", "notice saying",
        "settlement", "seats", "seat", "copies", "autocad", "solidworks",
        "photoshop", "cad",
    ))
    if generic_business_portal_context and not software_enforcement_context:
        return False

    software_context = _has_any(q, (
        "software", "cad", "autocad", "solidworks", "photoshop",
        "unlicensed copies", "unlicensed copy", "pirated software",
        "software license", "software licence", "license audit", "licence audit",
    ))
    licence_or_notice_context = _has_any(q, (
        "unlicensed", "pirated", "notice", "legal notice", "vendor sent",
        "vendor notice", "audit", "seats", "seat", "copies", "licence",
        "license", "infringement", "copyright",
    ))
    trademark_only_context = _has_any(q, (
        "brand", "brand name", "logo", "counterfeit", "passing off",
        "trademark", "trade mark",
    ))
    return software_context and licence_or_notice_context and not trademark_only_context


def _is_bank_debit_service_dispute(q: str) -> bool:
    atm_service_context = _has_any(q, (
        "atm cash not dispensed", "cash not dispensed", "atm did not dispense",
        "atm didn't dispense", "atm withdrawal failed", "cash not received",
        "cash did not come", "cash didn't come", "account debited",
        "atm debited", "atm debit", "cash withdrawal failed",
    ))
    if _has_any(q, (
        "otp", "phishing", "scam", "fake call", "fake cbi",
        "digital arrest", "hacked", "mule account", "fraud",
    )) and not atm_service_context:
        return False
    bank_context = _has_any(q, (
        "bank", "hdfc", "icici", "sbi", "axis", "kotak", "yes bank",
        "account", "debit card", "credit card", "forex card",
        "upi", "phonepe", "gpay", "google pay", "paytm",
        "payment app", "atm", "imps", "neft", "rtgs",
    )) or atm_service_context
    debit_context = _has_any(q, (
        "bank wrongly debited", "wrongly debited", "unauthorized debit",
        "unauthorised debit", "forex transaction", "forex debit",
        "card transaction", "debit transaction", "debited twice",
        "transaction failed", "status failed", "failed but debited",
        "failed but money cut", "failed but money deducted",
        "failed but amount cut", "failed but amount deducted",
        "transaction failed but", "status failed but",
        "wrong charge", "chargeback", "chargeback not processed",
        "not processed", "transaction dispute",
        "deducted money wrongly", "money deducted wrongly",
        "dedcted money wrongly", "money dedcted wrongly",
        "wrongly deducted", "wrong deduction", "wrong debit",
        "deducted from account", "money deducted from account",
        "unauthorized transaction", "unauthorised transaction",
        "credit card unauthorized transaction",
        "credit card unauthorised transaction", "not reversing",
        "not reversing amount", "bank not reversing", "reversed my balance",
        "balance reversed", "technical error", "wrong balance",
        "failed but amount debited", "amount debited", "upi failed",
        "upi transaction failed", "failed transaction",
        "failed upi refund", "upi refund", "money cut",
        "amount cut", "money deducted", "deducted cancellation",
        "charge twice", "charged twice", "charged forex",
        "annual fee", "card annual fee", "annual fee charged",
        "annual fee twice", "charged annual fee", "charged annual fee twice",
        "fee charged", "fee charged twice", "card was closed", "card closed",
        "credit card charged annual fee twice",
        "wrongly charged", "forex markup", "charged markup",
        "markup twice", "markup charged", "maintenance charge",
        "deducted maintenance charge", "atm cash not dispensed",
        "cash not dispensed", "atm did not dispense", "atm didn't dispense",
        "atm withdrawal failed", "cash not received", "cash did not come",
        "cash didn't come", "account debited", "atm debited", "atm debit",
        "cash withdrawal failed",
        "imps transfer failed", "imps failed", "failed imps",
        "beneficiary did not get money", "beneficiary didn't get money",
        "beneficiary says not received", "beneficiary says no money",
    )) or atm_service_context
    grievance_context = _has_any(q, (
        "no response", "not resolving", "complaint", "refund", "reversal",
        "ombudsman", "rbi", "customer care", "branch", "not giving reason",
        "bank and app blaming", "app blaming", "blaming each other",
        "closed ticket", "support", "wait", "says wait", "branch says wait",
        "wait 45 days", "ask bank",
        "complaint number", "not helping", "beneficiary did not get money",
        "beneficiary didn't get money", "did not get money", "didn't get money",
        "beneficiary says not received", "beneficiary says no money",
        "not received",
        "card was closed", "card closed",
        "chargeback not processed", "not processed",
    ))
    card_fee_context = _has_any(q, ("credit card", "card")) and _has_any(q, (
        "annual fee", "card fee", "fee charged", "card was closed", "card closed",
    ))
    return bank_context and debit_context and (
        grievance_context or "forex" in q or atm_service_context or card_fee_context
    )


def _is_lender_reminder_or_recovery_service_issue(q: str) -> bool:
    closed_loan_credit_record_context = _has_any(q, (
        "closed loan", "loan closed", "tenure ended", "not giving noc",
        "no dues", "noc", "closure letter", "foreclosure", "loan closure",
    )) and _has_any(q, (
        "cibil", "credit report", "credit score", "credit bureau",
        "still active", "active", "written off", "wrong entry",
    ))
    if closed_loan_credit_record_context:
        return False
    false_credit_identity_context = _has_any(q, (
        "fake loan", "signature not mine", "signature is not mine",
        "not my signature", "loan not mine", "without my consent",
    )) and _has_any(q, ("cibil", "credit report", "nbfc", "finance company", "loan"))
    if false_credit_identity_context:
        return False

    lender_context = _has_any(q, (
        "lender", "nbfc", "finance company", "loan account",
        "emi", "loan", "repayment", "recovery sms", "reminder sms",
        "bajaj", "bajaj finance", "bajaj finserv",
    ))
    reminder_context = _has_any(q, (
        "reminder sms", "sent reminder", "normal emi", "emi is late",
        "emi late", "late emi", "payment reminder", "repayment reminder",
        "is that harassment", "harassment", "harass", "emi bounced",
        "emi bounce", "penalty", "late fee",
        "bank error", "threatening cibil", "threaten cibil",
        "cibil", "credit report", "credit score",
    ))
    aggressive_collection_context = _has_any(q, (
        "threat", "threatening", "abuse", "abusive", "shouting",
        "workplace", "neighbours", "neighbors", "contacts", "photo",
        "public shaming", "shame",
    ))
    if _is_loan_app_harassment_issue(q) or _is_bank_debit_service_dispute(q):
        return False
    return lender_context and reminder_context and not aggressive_collection_context


def _is_spousal_adultery_marriage_breakdown_issue(q: str) -> bool:
    if _has_any(q, ("slap", "slapped", "hit", "beat", "beaten")) and _has_any(q, (
        "case on me", "filing case on me", "filed case on me",
        "complaint against me", "fir against me", "police called me",
    )):
        return False
    spouse_context = _has_any(q, ("husband", "wife", "spouse"))
    explicit_adultery_context = _has_any(q, (
        "adultery", "extra marital", "extra-marital", "affair", "cheating on me",
        "affair with", "relationship with another",
        "living with another man", "living with another woman",
        "living with another women", "staying with another man",
        "staying with another woman", "staying with another women",
        "another women having sex", "another woman having sex",
        "another man having sex", "having sex with another",
        "sex with another woman", "sex with another women", "sex with another man",
    ))
    caught_context = _has_any(q, (
        "caught my husband", "caught my wife", "caught husband", "caught wife",
        "caught him with", "caught her with",
    ))
    sexual_or_romantic_context = _has_any(q, (
        "having sex", "sex with", "in bed", "naked", "lover", "girlfriend",
        "boyfriend", "romantic", "love affair", "relationship with",
    ))
    return spouse_context and (explicit_adultery_context or (caught_context and sexual_or_romantic_context))


def _is_personal_money_recovery_issue(q: str) -> bool:
    if _has_any(q, (
        "bank", "nbfc", "loan app", "education loan", "home loan",
        "business loan", "customer care", "consumer", "refund", "salary",
        "wages", "rent", "tenant", "landlord", "invoice", "client not paying",
    )):
        return False
    amount_context = re.search(r"\b(?:rs\.?|inr)?\s*\d{4,}\b", q) is not None
    money_context = _has_any(q, (
        "money", "loan", "hand loan", "borrowed", "lent", "gave him",
        "gave her", "gave my", "upi", "cash", "amount", "repay", "repayment",
    )) or amount_context
    non_return_context = _has_any(q, (
        "not returning", "not return", "not repaying", "not repay",
        "refusing to return", "refusing to repay", "took loan",
        "took hand loan", "avoiding calls", "blocked my number",
        "blocked number", "blocked me", "now blocked",
        "took money", "borrowed money", "money back", "return my money",
        "recover my money", "recover money", "will repay", "said he will repay",
        "says he will repay", "whatsapp says", "whatsapp message",
        "no written agreement", "without written agreement", "can police recover",
    ))
    personal_context = _has_any(q, (
        "brother", "sister", "friend", "relative", "cousin", "uncle",
        "aunt", "neighbour", "neighbor", "family", "known person",
        "colleague",
    ))
    return money_context and non_return_context and personal_context


def _is_mutation_after_death_issue(q: str) -> bool:
    death_context = _has_any(q, (
        "father died", "mother died", "husband died", "wife died",
        "parent died", "parents died", "died", "death", "passed away",
        "late father", "late mother", "late husband", "late wife",
    ))
    land_record_context = _has_any(q, (
        "mutation", "mutate", "patwari", "tehsildar", "tahsildar",
        "talathi", "khata", "khasra", "khatauni", "jamabandi",
        "land record", "revenue record", "ror", "record of rights",
        "name not updated", "not updated", "enter my name",
    ))
    land_context = _has_any(q, (
        "land", "plot", "field", "agricultural", "khata", "khasra",
        "patwari record", "revenue record", "property", "house", "flat", "home",
    ))
    return death_context and land_record_context and land_context


def _is_heir_property_sale_consent_issue(q: str) -> bool:
    if _has_any(q, ("tribal", "non tribal", "non-tribal", "adivasi", "scheduled tribe", "scheduled area")):
        return False
    heir_context = _has_any(q, ("legal heir", "legal heirs", "heir", "heirs", "co-heir", "co heir"))
    property_context = _has_any(q, ("property", "land", "plot", "house", "flat", "ancestral", "inherited"))
    sale_context = _has_any(q, ("sell", "selling", "sale", "sold", "transfer", "registration", "registered"))
    consent_context = _has_any(q, (
        "not agreeing", "not agree", "refusing", "refuses", "without consent",
        "no consent", "not signing", "won't sign", "will not sign",
        "one legal heir", "one heir",
    ))
    return heir_context and property_context and sale_context and consent_context


def _is_itpa_call_handling_issue(q: str) -> bool:
    itpa_context = _has_any(q, ("itpa", "pita", "immoral traffic"))
    role_context = _has_any(q, (
        "phone", "call", "calls", "whatsapp", "paying clients", "client booking",
        "clients", "booking", "bookings", "take bookings", "took bookings",
        "only talking", "not meet", "not meeting", "did not meet",
    ))
    return itpa_context and role_context


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
    b2b_context = _has_any(q, (
        "vendor", "supplier", "purchase order", "work order", "equipment",
        "business dispute", "msme", "msefc", "commercial court", "invoice",
        "buyer", "machinery", "goods worth",
    ))
    return payment_context and refund_context and merchant_context and not fraud_context and not b2b_context


def _is_obvious_consumer_goods_issue(q: str) -> bool:
    theft_or_police_context = _has_any(q, (
        "stolen", "stole", "theft", "snatched", "robbed",
        "police", "fir", "lost report", "not filing fir",
        "refusing fir", "refused fir",
    ))
    if theft_or_police_context:
        return False
    goods_or_service = _has_any(q, (
        "phone", "mobile", "iphone", "laptop", "computer", "shoes",
        "footwear", "online order", "online seller", "seller",
        "service center", "service centre", "warranty", "amazon",
        "flipkart", "marketplace", "third party seller",
        "third-party seller", "repair", "replacement",
    ))
    defect_or_refusal = _has_any(q, (
        "damaged", "defective", "defect", "fake", "counterfeit",
        "duplicate", "return", "refund", "replacement", "repair",
        "not accepting", "refusing", "refused", "not valid",
        "warranty repair", "warranty refused",
    ))
    business_goods_context = _has_any(q, (
        "purchase order", "po ", "msme", "supplier", "vendor",
        "commercial court", "buyer", "public sector buyer", "psu",
        "goods worth", "machinery", "equipment",
    ))
    return goods_or_service and defect_or_refusal and not business_goods_context


def _is_document_fraud_issue(q: str) -> bool:
    if _is_tribal_land_transfer_issue(q):
        return False
    if _is_bank_property_document_fraud_issue(q) or _is_property_transfer_document_issue(q):
        return False
    document_context = _has_any(q, ("thumb impression", "blank paper", "forged", "fake signature", "didn't sign", "did not sign"))
    fraud_context = _has_any(q, ("loan", "gift deed", "moneylender", "bank", "showing", "produced", "fraud"))
    return document_context and fraud_context


def _is_bank_property_document_fraud_issue(q: str) -> bool:
    bank_context = _has_any(q, (
        "bank", "lender", "nbfc", "loan", "loan against", "mortgage",
        "secured loan", "home loan",
    ))
    property_context = _has_any(q, (
        "house", "home", "flat", "property", "land", "plot",
        "title deed", "sale deed",
    ))
    forged_context = _has_any(q, (
        "didn't sign", "did not sign", "fake signature", "forged", "forgery",
        "blank paper", "thumb impression", "without my consent",
    ))
    return bank_context and property_context and forged_context


def _is_business_contract_issue(q: str) -> bool:
    if _is_work_injury(q):
        return False
    if _is_criminal_quashing_issue(q):
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
        "work order", "po ", "invoice", "msme", "msmed", "udyam", "samadhan", "msefc",
        "samadhaan", "msme registered", "msme samadhan portal",
        "public sector buyer", "psu",
        "business", "company", "firm", "partnership", "dealer", "agent",
        "principal agent", "principal-agent", "goods worth", "customer list",
        "trade secret", "co founder", "co-founder", "shareholder", "equity",
        "delivery partner", "commercial court", "commercial suit", "business dispute",
        "machinery", "equipment", "goods",
    ))
    explicit_consumer_service_context = _has_any(q, (
        "consumer complaint", "consumer forum", "consumer court", "consumer helpline",
        "coaching", "coaching centre", "coaching center", "online course", "edtech",
        "course refund", "student refund", "customer support",
    ))
    clear_b2b_context = _has_any(q, (
        "client", "buyer", "supplier", "vendor", "purchase order", "work order",
        "invoice", "msme", "msmed", "udyam", "samadhan", "msefc", "samadhaan",
        "public sector buyer", "psu", "firm", "partnership", "dealer",
        "principal agent", "principal-agent", "goods worth", "commercial court",
        "commercial suit", "business dispute", "machinery", "equipment", "b2b",
    ))
    strong_commercial_context = _has_any(q, (
        "client", "buyer", "supplier", "vendor", "saas", "purchase order", "work order",
        "msme", "msmed", "udyam", "samadhan", "msefc", "business",
        "samadhaan", "msme registered", "msme samadhan portal",
        "public sector buyer", "psu",
        "firm", "partnership", "dealer", "principal agent", "principal-agent",
        "goods worth", "customer list", "trade secret", "co founder",
        "co-founder", "shareholder", "equity", "delivery partner",
        "commercial court", "commercial suit", "business dispute", "machinery", "equipment",
        "goods",
    ))
    if explicit_consumer_service_context and not clear_b2b_context:
        return False
    if consumer_or_personal_context and not strong_commercial_context:
        return False
    if _has_any(q, ("partnership", "business partner", "partner in firm", "retire from partnership")):
        return True
    business_dispute = _has_any(q, (
        "not paying", "unpaid", "deducting payment", "formal rejection",
        "quality issue", "defective", "damaged", "poor quality",
        "refusing refund", "refund", "replace", "replacement",
        "lakh stuck", "breach", "contract", "liability",
        "absconded", "invoice", "non compete", "non-compete", "nda",
        "specific performance", "exclusivity", "dilute my equity",
        "diluting my equity", "esop", "minority shareholder",
        "shareholder oppressing", "commission dispute", "agreement",
        "payment delay", "45 days payment", "amount outstanding",
        "payment pending", "pending payment", "supplier bill", "vendor bill",
        "not paid", "non payment", "charge interest", "samadhan portal",
        "commercial court", "pre litigation mediation", "pre-litigation mediation",
        "recover advance", "advance", "cancel and recover", "delivery in 30 days",
        "failed to deliver", "delivery failed", "did not deliver", "not delivered",
        "work order", "business dispute",
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
    if _is_family_safety_issue(q):
        return False
    family_context = _has_any(q, (
        "husband", "wife", "spouse", "in laws", "in-laws", "mother in law",
        "father in law", "married", "marriage", "live in partner",
        "live-in partner", "domestic relationship", "matrimonial home",
        "shared house", "shared household", "sasural",
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
        "permit", "fssai", "notice", "fine", "fined", "inspector said",
        "trade license",
    ))
    return registration_context


def _is_municipal_shop_sealing_issue(q: str) -> bool:
    shop_context = _has_any(q, (
        "shop", "dukan", "store", "restaurant", "hotel", "clinic", "godown",
        "warehouse", "commercial premises", "business premises", "showroom",
        "office sealed", "factory sealed",
    ))
    municipal_context = _has_any(q, (
        "municipality", "municipal", "municipal corporation", "corporation",
        "ward office", "nagar palika", "nagarpalika", "mcd", "bmc",
        "bbmp", "noida authority", "development authority", "local body",
        "local authority", "authority",
    ))
    sealing_context = _has_any(q, (
        "sealed", "seal", "sealing", "locked", "closed my shop",
        "shop closed", "closure notice", "demolition notice",
        "licence issue", "license issue", "trade license expired",
        "trade licence expired",
    ))
    return shop_context and municipal_context and sealing_context


def _is_bank_account_freeze_issue(q: str) -> bool:
    non_bank_account_context = _has_any(q, (
        "instagram", "facebook", "meta", "youtube", "google", "gmail",
        "twitter", "x account", "whatsapp", "telegram", "amazon seller",
        "flipkart seller", "seller account", "merchant account",
        "zerodha", "groww", "upstox", "demat", "trading account",
        "binance", "crypto", "usdt", "wallet", "gaming", "dream11",
        "parimatch", "rummy", "creator account", "payout account",
    ))
    explicit_bank_context = _has_any(q, (
        "bank", "bank account", "savings account", "current account",
        "salary account", "loan account", "jan dhan account", "upi account",
        "sbi", "hdfc", "icici", "axis", "kotak", "pnb", "canara",
        "bob", "bank of baroda", "union bank", "idfc", "yes bank",
        "rbi", "nbfc",
    ))
    freeze_context = _has_any(q, (
        "bank account frozen", "bank account is frozen", "bank account froze",
        "savings account frozen", "current account frozen", "account freeze",
        "bank account freeze", "bank account blocked",
        "account blocked by bank", "salary account blocked",
        "salary account frozen", "upi account frozen", "upi account blocked",
        "account is frozen", "account was frozen",
        "my account frozen", "account frozen for kyc",
        "account frozen because kyc", "kyc pending", "kyc is pending",
        "account is on hold", "account on hold", "account hold",
        "bank account on hold", "bank put account on hold",
        "account lien", "bank account lien", "lien marked", "freeze my account",
        "debit freeze", "credit freeze", "kyc hold", "marked lien",
        "bank marked lien", "bank put lien", "put lien on my account",
        "put lien on savings account", "lien on savings account",
        "lien on my account", "lien on salary account",
        "salary account has lien", "account has lien", "has lien",
        "not giving order copy", "no order copy", "no notice came",
        "froze my bank account", "police froze my bank account",
        "freeze marked", "ed freeze", "legal hold", "cyber cell email",
        "fraud complaint against my upi id",
    ))
    if non_bank_account_context and not explicit_bank_context:
        return False
    return explicit_bank_context and freeze_context


def _is_loan_app_harassment_issue(q: str) -> bool:
    ordinary_reminder_only = _has_any(q, (
        "normal due date reminder", "only sends normal due date reminder",
        "only normal reminder", "only sends reminder", "only reminder",
        "normal emi reminder", "normal payment reminder",
        "no threats or contacts", "no threat or contact",
        "no threats", "no threat", "no contacts", "not harassing",
        "not harassment", "no harassment",
    )) and not _has_any(q, (
        "calling my contacts", "calling contacts", "harassing my contacts",
        "sent message to contacts", "messages to contacts", "abusing",
        "abusive", "threatened", "threatening", "blackmail", "morphed",
        "nude", "came to my office", "visiting office", "shouting",
        "publicly shame", "tell my boss", "tell manager", "tell my office",
        "tell my neighbours", "tell my neighbors",
    ))
    if ordinary_reminder_only:
        return False

    credit_record_only_pressure = _has_any(q, (
        "threatening cibil", "threaten cibil", "cibil",
        "credit report", "credit score", "credit bureau",
    )) and not _has_any(q, (
        "contacts", "contact list", "relatives", "family group",
        "calling my relatives", "abusing my relatives", "sending my photo",
        "photo to contacts", "morphed", "nude", "blackmail", "extortion",
        "leak my data", "threatening to leak", "came home", "came to my house",
        "came to my office", "visiting office", "workplace", "shame",
        "society", "publicly shame", "tell manager", "tell my manager",
        "tell my office", "tell my workplace", "tell my neighbours",
        "tell my neighbors", "shouting",
    ))
    if credit_record_only_pressure:
        return False

    app_context = bool(re.search(r"\bloan\s+apps?\b", q)) or _has_any(q, (
        "instant loan app", "online loan app", "digital lending app",
        "cash loan app", "loan recovery app", "finance app",
    ))
    lender_context = app_context or (
        _has_any(q, (
            "nbfc", "finance company", "finance agent", "bajaj",
            "bajaj finance",
            "bajaj finserv", "recovery agent", "recovery agents",
            "loan recovery", "collection agent", "collection agents",
            "collection people",
        ))
        and _has_any(q, (
            "app", "contacts", "harass", "harassing", "harrasing",
            "threat", "threaten", "threatened", "threatening", "abuse", "abusing", "came home",
            "home", "house", "photo", "photos", "took photo", "took photos",
            "came to my office", "visiting office", "office", "workplace", "shame", "society",
            "neighbour", "neighbor", "neighbours", "neighbors",
            "boss", "manager", "employer", "calling my boss", "calling my manager",
            "saying i am fraud", "saying I am fraud",
            "tell manager", "tell my manager", "tell my office", "tell my workplace", "tell my neighbours",
            "tell my neighbors", "shouting", "emi default",
        ))
    )
    harassment_context = _has_any(q, (
        "harass", "harassing", "harrasing", "harassment", "calling my contacts",
        "calling contacts", "contacting contacts", "harassing my contacts",
        "harassing contacts", "sent message to contacts", "messages to contacts",
        "contact list", "abusing contacts", "threatening contacts",
        "recovery calls", "threatened", "threatening cibil", "threaten cibil",
        "morphed photo", "abusive message", "blackmail", "contacts",
        "relatives", "family", "calling my relatives", "abusing me",
        "abusing my relatives", "sending my photo", "photo to contacts",
        "took photo", "took photos", "photos of my house", "photo of my house",
        "house photo", "home photo", "came to my house",
        "leak my data", "threatening to leak",
        "came home", "came to my office", "visiting office", "shame me", "shame me in society",
        "society", "publicly shame", "tell manager", "tell my manager", "tell my office", "tell my workplace",
        "boss", "manager", "employer", "calling my boss", "calling my manager",
        "saying i am fraud", "saying I am fraud",
        "tell my neighbours", "tell my neighbors", "office and neighbours",
        "office and neighbors", "workplace", "shouting", "emi default",
        "came to my workplace", "came workplace",
    ))
    return lender_context and harassment_context


def _is_pan_aadhaar_mismatch_issue(q: str) -> bool:
    pan_context = _has_any(q, ("pan", "pan card", "income tax portal"))
    aadhaar_context = _has_any(q, ("aadhaar", "aadhar", "uidai"))
    mismatch_context = _has_any(q, (
        "mismatch", "not matching", "does not match", "doesn't match",
        "name different", "dob different", "date of birth different",
        "linking failed", "link failed", "cannot link", "not linking",
    ))
    return pan_context and aadhaar_context and mismatch_context


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
        "brought from", "return ticket", "return fare", "journey allowance",
        "sent us home", "migrant registration", "ismw",
        "factory", "site", "domestic worker", "job card", "mgnrega",
        "labour card", "bocw", "cess", "deducted", "deducting", "takes money",
        "safety shoes", "half pay",
        "site supervisor", "minimum wage", "minimum wages", "state rate",
        "unskilled", "construction",
    ))
    return not project_displacement or strong_labour_context


def _is_scheme_worker_payment_issue(q: str) -> bool:
    return _is_asha_payment_issue(q) or _is_anganwadi_payment_issue(q)


def _is_asha_payment_issue(q: str) -> bool:
    non_payment_context = _has_any(q, (
        "login", "software", "app not working", "portal not working",
        "training", "transfer", "posting", "attendance app",
    ))
    worker_context = _has_any(q, (
        "asha", "asha worker", "asha facilitator", "nhm", "nrhm",
        "national health mission",
    ))
    payment_context = _has_any(q, (
        "honorarium", "incentive", "incentives", "not paid", "not paying",
        "pending", "arrears", "payment", "payments", "salary", "covid duty",
        "duty incentive",
    ))
    return worker_context and payment_context and not (non_payment_context and not payment_context)


def _is_pf_contribution_default_issue(q: str) -> bool:
    return _has_any(q, ("pf", "epf", "provident fund", "uan", "epfo", "pf passbook", "uan passbook")) and _has_any(q, (
        "deducted", "deduction", "not deposited", "not depositing", "never deposited",
        "passbook empty", "passbook has zero", "passbook shows zero", "zero contribution",
        "balance missing", "hr not replying", "uan", "employer contribution",
    ))


def _is_epfo_pension_identity_issue(q: str) -> bool:
    epfo_context = _has_any(q, ("epfo", "eps", "employees pension", "employee pension", "provident fund pension", "pf pension"))
    pension_context = _has_any(q, (
        "pension", "pension nahi", "pension not", "pension arrears",
        "pension stopped", "not releasing pension", "pension pending",
        "pension milega", "pension nahi milega",
    ))
    identity_or_status_context = _has_any(q, (
        "aadhaar", "aadhar", "mismatch", "kyc", "uan", "ppo",
        "not releasing", "not paid", "arrears", "pending", "4 saal",
        "4 years", "2 years", "6 month", "6 months",
    ))
    return epfo_context and pension_context and identity_or_status_context


def _is_anganwadi_payment_issue(q: str) -> bool:
    explicit_asha_worker = _has_any(q, ("asha worker", "asha facilitator"))
    explicit_anganwadi_worker = _has_any(q, (
        "anganwadi worker", "anganwadi helper", "icds worker",
        "icds helper", "icds didi",
    ))
    if explicit_asha_worker and not explicit_anganwadi_worker:
        return False
    non_worker_payment = _has_any(q, (
        "supplier", "vendor", "nutrition supplier", "food supplier",
        "building rent", "room rent", "rent pending", "contractor bill",
        "ration supply", "milk supply",
    ))
    if non_worker_payment and not explicit_anganwadi_worker:
        return False
    worker_context = _has_any(q, (
        "anganwadi worker", "anganwadi helper", "icds worker",
        "icds helper", "icds didi",
    )) or (
        _has_any(q, ("anganwadi", "cdpo", "icds"))
        and _has_any(q, (
            "honorarium", "honourarium", "worker", "helper", "sevika", "didi",
            "nutrition duty", "nutrition work", "duty", "app attendance",
            "district office", "no sanction",
        ))
    )
    payment_context = _has_any(q, (
        "honorarium", "honourarium", "incentive", "incentives",
        "not paid", "not paying", "pending", "arrears", "payment",
        "salary", "cdpo", "block office", "no sanction", "not credited",
        "payment stopped", "attendance issue",
    ))
    return worker_context and payment_context


def _bocw_registration_route(q: str) -> MatterRoute:
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


def _is_bocw_registration_issue(q: str) -> bool:
    bocw_context = _has_any(q, ("bocw", "building worker", "construction worker", "construction welfare board"))
    registration_or_cess = _has_any(q, (
        "registration", "register", "card", "welfare board", "benefit",
        "cess", "same name", "fake name", "real names", "name on register",
    ))
    actual_injury_context = _has_any(q, (
        "injury", "injured", "accident", "fell from", "fell down", "leg broken",
        "hand broken", "lost hand", "lost arm", "amputation", "died",
        "death", "dead", "killed", "compensation", "medical",
    ))
    record_fraud_context = _has_any(q, (
        "fake", "false register", "fake register", "duplicate", "same name",
        "real names", "cess record", "welfare benefit", "benefit claim",
    ))
    return bocw_context and registration_or_cess and (not _is_work_injury(q) or (record_fraud_context and not actual_injury_context))


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
    stalking_context = _has_any(q, (
        "stalker", "stalking", "stalked", "stalks",
        "follows", "following", "followed",
    ))
    repeated_or_route_context = _has_any(q, (
        "everyday", "daily", "office to home", "scooty", "after blocking",
        "dm daily", "direct message", "dms", "messages", "doesn't talk", "does not talk",
        "outside my house", "near my house", "near house", "outside office",
        "near office", "road", "street", "bus stop", "college", "market",
    ))
    return stalking_context and (repeated_or_route_context or _has_any(q, ("complaint", "what section", "file complaint")))


def _is_explicit_physical_stalking_context(q: str) -> bool:
    return _has_any(q, (
        "not online", "offline", "physically", "physical stalking",
        "physical stalker", "near my house", "near house", "outside my house",
        "outside office", "near office", "road", "street", "bus stop",
        "college", "market",
    ))


def _is_minor_interfaith_relationship_issue(q: str) -> bool:
    minor_context = _has_age_under(q, 18) or _has_any(q, ("minor", "under 18", "under eighteen"))
    relationship_context = _has_any(q, ("ran away", "eloped", "love jihad", "different religion", "other religion", "interfaith", "inter-faith"))
    police_or_family_context = _has_any(q, ("police", "family", "parents", "father", "mother", "threat", "missing"))
    return minor_context and relationship_context and police_or_family_context


def _is_honour_threat_issue(q: str) -> bool:
    relationship_context = _has_any(q, (
        "eloped", "ran away", "different religion", "other religion",
        "interfaith", "inter-faith", "inter religion", "inter-religion",
        "love marriage", "inter caste", "inter-caste", "different caste",
        "other caste", "outside caste", "marry outside caste",
    ))
    threat_context = _has_any(q, ("khap", "family threatening", "threatening her", "threatening him", "honour", "honor", "kill", "mob"))
    return relationship_context and threat_context


def _is_dowry_death_issue(q: str) -> bool:
    death_context = _has_any(q, ("died", "death", "suicide", "body", "dead", "burnt", "burned"))
    marital_context = _has_any(q, ("in laws", "in-laws", "husband", "married", "sister", "wife", "daughter"))
    suspicious_context = _has_any(q, ("dowry", "body had marks", "marks", "suicide", "suspicious", "burnt", "burned"))
    return death_context and marital_context and suspicious_context


def _is_family_economic_abuse_issue(q: str) -> bool:
    if _is_wife_as_aggressor_issue(q):
        return False
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
    if _has_msme_negation(q):
        return False
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
    if _is_ration_card_pds_issue(q):
        return False
    inspection_context = _has_any(q, (
        "labour department", "labor department", "labour inspector",
        "labor inspector", "labour officer", "labor officer",
        "inspection", "raid", "raided", "notice",
    ))
    register_context = _has_any(q, (
        "overtime register", "ot register", "register not maintained",
        "not maintained", "records not maintained", "registers", "records",
        "employee register", "staff register", "shop register",
        "shops register", "maharashtra shops register",
        "establishment register", "keeping employee register",
    ))
    worker_count_context = bool(re.search(r"\b(?:1[0-9]|[2-9][0-9])\s+workers?\b", q))
    shop_context = _has_any(q, ("shops act", "shop act", "shops and establishments", "shop", "store", "cafe"))
    return inspection_context and register_context and ("overtime" in q or worker_count_context or shop_context)


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
    if _has_any(q, ("parole", "furlough", "remission", "custody parole", "wedding", "marriage", "funeral", "cremation")) and not _has_any(q, (
        "lawyer meeting", "lawyer meet", "not allowing lawyer", "not allowing advocate",
        "legal aid lawyer not coming", "lawyer not coming", "no lawyer until interrogation",
        "lawyer access", "advocate access",
    )):
        return False
    custody_negated = _has_any(q, (
        "no arrest", "not arrested", "not criminal case", "not a criminal case",
        "no criminal case", "not in custody", "not detained", "no detention",
        "no police custody",
    ))
    civil_affordability_context = _has_any(q, (
        "property", "partition", "civil suit", "civil case", "land",
        "consumer complaint", "phone company", "consumer case",
        "labour case", "family case", "divorce", "inheritance",
    ))
    if custody_negated and civil_affordability_context:
        return False
    custody_context = _has_any(q, (
        "jail", "lockup", "custody", "arrest", "arrested",
        "detained", "prison", "remand", "first remand",
    ))
    lawyer_context = _has_any(q, (
        "lawyer meeting", "lawyer meet", "not allowing lawyer", "legal aid",
        "free lawyer", "court give free lawyer", "court appoint lawyer",
        "nalsa", "dlsa", "jail superintendent", "no lawyer",
        "free advocate", "no advocate", "cannot pay lawyer",
        "can't pay lawyer", "cant pay lawyer", "remand court",
        "first remand", "lawyer can meet", "lawyer access",
        "advocate access", "legal aid lawyer", "private lawyer",
        "cannot afford advocate", "can't afford advocate", "cant afford advocate",
        "cannot afford lawyer", "can't afford lawyer", "cant afford lawyer",
    ))
    return custody_context and lawyer_context


def _is_default_bail_issue(q: str) -> bool:
    charge_sheet_context = _has_any(q, (
        "no chargesheet", "no charge sheet", "no charge-sheet",
        "chargesheet not", "charge sheet not", "charge-sheet not",
        "chargesheet filed nahi", "charge sheet filed nahi",
        "chargesheet not ready", "charge sheet not ready",
        "chargesheet still not", "charge-sheet is still not",
        "no challan", "challan not", "challan filed nahi", "challan not filed",
        "no complaint filed", "complaint not filed",
        "no final report", "final report not", "final report after",
        "extension request", "extension application",
        "police may file chargesheet", "police may file charge sheet",
        "supplementary report not full chargesheet",
    ))
    bail_context = _has_any(q, (
        "default bail", "default-bail", "statutory bail", "statutory/default bail",
        "can i file default", "file default", "what court should file",
        "default bail kya", "default bail possible", "statutory bail possible",
    ))
    custody_context = _has_any(q, (
        "jail", "prison", "custody", "arrest", "arrested", "remand",
        "tihar", "arthur road", "inside", "arrest memo",
    ))
    custody_days = re.search(r"\b(?:6[0-9]|[7-9][0-9]|1[0-9]{2})\s*days?\b", q) is not None
    custody_months = re.search(r"\b(?:3|4|5|6|7|8|9|10|11|12)\s*(?:months?|mnths?)\b", q) is not None
    return (
        bail_context
        or (charge_sheet_context and (custody_context or custody_days or custody_months))
        or ((custody_days or custody_months) and _has_any(q, ("bail", "chargesheet", "charge sheet", "charge-sheet", "challan", "final report", "extension")))
    )


def _has_uapa_context(q: str) -> bool:
    return _has_any(q, (
        "uapa", "43d", "43 d", "unlawful activities", "unlawful activity",
        "terror case", "terrorist case", "terrorism case",
    ))


def _is_esi_benefit_issue(q: str) -> bool:
    esi_context = _has_any(q, ("esi", "esic", "employees state insurance", "employees' state insurance"))
    benefit_context = _has_any(q, (
        "hospital", "treat", "treatment", "delivery", "medical benefit",
        "refused", "claim rejected", "sickness benefit", "maternity benefit",
        "disablement benefit", "insured person",
    ))
    return esi_context and benefit_context


def _is_nclat_appeal_issue(q: str) -> bool:
    nclat_context = _has_any(q, ("nclat", "national company law appellate tribunal"))
    appeal_context = _has_any(q, ("appeal", "appeal against", "tribunal order", "order against me", "format", "fees", "limitation", "days"))
    return nclat_context and appeal_context


def _is_elder_financial_fraud_issue(q: str) -> bool:
    if _is_motor_accident_claim_issue(q):
        return False
    if _is_bank_or_pension_impersonation_fraud(q):
        return False
    elder_context = (
        _has_any(q, ("senior", "elderly", "old", "grandfather", "grandmother"))
        or _has_age_at_least(q, 60)
        or re.search(r"\b(?:6[0-9]|7[0-9]|8[0-9]|9[0-9])\s*(?:year|years|yr|yrs)\s+(?:father|mother|parent)\b", q) is not None
        or (
            _has_any(q, ("father", "mother", "parent"))
            and _has_any(q, (
                "pension money", "retirement money", "ulip", "agent sold",
                "mis-selling", "misselling", "policy", "insurance", "lic",
                "guaranteed return", "matured",
            ))
        )
    )
    financial_abuse = _has_any(q, (
        "ulip", "policy", "agent sold", "lost", "jewellery", "safe keeping",
        "not returning", "charging deceased", "deactivate no response",
        "pension money", "mis-selling", "misselling", "fake call",
        "fraud call", "scam call", "pension office", "took 2 lakh",
        "took money", "debited", "transferred", "lic", "insurance",
        "guaranteed return", "matured", "maturity amount",
    ))
    return elder_context and financial_abuse


def _is_insurance_claim_dispute(q: str) -> bool:
    insurance_context = _has_any(q, (
        "insurance", "insurer", "insurerer", "insurerr", "insurance company", "policy", "claim number",
        "surveyor", "repudiation", "repudiated",
    ))
    claim_context = _has_any(q, (
        "claim", "not paying", "not paid", "rejected", "rejecting", "denied", "repudiated",
        "settlement", "settle", "delay", "fire", "accident", "damage", "loss",
    ))
    criminal_context = _has_any(q, ("fir", "police", "arson", "burned by", "burnt by", "set fire"))
    return insurance_context and claim_context and not criminal_context


def _is_lgbtq_identity_arrest_issue(q: str) -> bool:
    identity_context = _has_any(q, (
        "being gay", "for being gay", "because he is gay", "because she is gay",
        "because i am gay", "because im gay", "gay", "lesbian", "same sex",
        "same-sex", "homosexual", "lgbt", "lgbtq", "queer", "sexual orientation",
    ))
    custody_context = _has_any(q, (
        "police arrested", "arrested", "arrest", "detained", "picked up",
        "police picked", "custody", "lockup", "jail", "taken by police",
        "fir", "case filed", "case against",
    ))
    return identity_context and custody_context


def _is_dating_app_extortion_or_phone_seizure(q: str) -> bool:
    dating_context = _has_any(q, (
        "tinder", "bumble", "hinge", "dating app", "dating-app",
        "online dating", "dating match", "match wala",
    ))
    extortion_context = _has_any(q, (
        "extortion", "blackmail", "honey trap", "honeytrap", "gang",
        "threatening", "threat", "recorded", "video", "photo",
        "took my phone", "phone taken", "snatched my phone", "seized my phone",
        "hotel", "met in", "money demand", "demanding money",
    ))
    action_context = _has_any(q, (
        "need lawyer", "need police", "police", "fir", "complaint",
        "cyber", "phone", "money", "pay", "send", "transfer",
    ))
    return dating_context and extortion_context and action_context


def _has_negated_fake_authority_or_payment(q: str) -> bool:
    return _has_any(q, (
        "no fake call", "not a fake call", "no fraud call", "no scam call",
        "no otp", "no phishing", "not phishing", "no video call",
        "no digital arrest", "not digital arrest", "no money demand",
        "no payment demand", "no demand for money", "no demand", "no transfer",
        "did not pay", "didn't pay", "no payment asked", "no money asked",
    ))


def _has_negated_bank_pension_impersonation(q: str) -> bool:
    return _has_any(q, (
        "no fraud call", "no fake call", "no scam call", "no otp",
        "no phishing", "not phishing", "no impersonation", "not impersonating",
        "no digital arrest", "not digital arrest",
    ))


def _is_fake_authority_payment_fraud(q: str) -> bool:
    if _has_negated_fake_authority_or_payment(q):
        return False
    base_fake_authority = _has_any(q, (
        "fake cbi", "fake police", "fake trai", "digital arrest",
        "courier scam",
    ))
    parcel_context = _has_any(q, ("drug parcel", "parcel has drugs"))
    parcel_scam_context = parcel_context and _has_any(q, (
        "fake", "scam", "video call", "digital arrest", "send money",
        "send 5", "pay", "paid", "transfer", "transferred", "demanded",
        "demanding", "asking money", "asking 5", "5 lakh", "cyber",
    ))
    fake_authority_context = _has_any(q, (
        "fake cbi", "fake police", "fake trai", "digital arrest",
        "courier scam",
    )) or parcel_scam_context or base_fake_authority
    authority_threat_or_payment = _has_any(q, (
        "video call", "police video call", "arrest", "threatening arrest",
        "sim will close", "pay", "paid", "transfer", "transferred",
        "made me transfer", "upi transfer", "bank", "cyber", "send",
        "send money", "send 5", "demand", "demanded", "demanding",
        "asking money", "asking 5", "5 lakh",
    ))
    return fake_authority_context and authority_threat_or_payment


def _is_bank_or_pension_impersonation_fraud(q: str) -> bool:
    if _has_negated_bank_pension_impersonation(q):
        return False
    if _has_any(q, ("failed but amount debited", "upi failed", "transaction failed", "blaming each other")) and not _has_any(q, (
        "otp", "phishing", "scam", "fake call", "fraud call", "impersonating",
        "pretending", "digital arrest", "fake cbi",
    )):
        return False
    if _has_any(q, (
        "atm cash not dispensed", "cash not dispensed", "atm did not dispense",
        "atm didn't dispense", "atm withdrawal failed", "cash not received",
        "cash did not come", "cash didn't come", "account debited",
    )) and not _has_any(q, (
        "otp", "phishing", "scam", "fake call", "fraud call", "impersonating",
        "pretending", "digital arrest", "fake cbi",
    )):
        return False
    if _is_fake_authority_payment_fraud(q):
        return True
    direct_impersonation = _has_any(q, (
        "fake call", "fraud call", "scam call", "impersonating",
        "pretending", "otp", "phishing", "digital arrest", "fake cbi",
        "fake police", "fake trai", "courier scam",
    ))
    money_loss_with_impersonation_context = _has_any(q, (
        "took money", "took 2 lakh", "lost money", "transferred",
        "made me transfer", "upi transfer",
    )) and _has_any(q, (
        "fake", "fraud", "scam", "otp", "phishing", "pension office",
        "sbi pension", "bank officer", "bank employee", "cbi", "trai",
        "courier", "digital arrest",
    ))
    fraud_context = direct_impersonation or money_loss_with_impersonation_context
    institution_context = _has_any(q, (
        "sbi", "bank", "pension office", "pension", "pf office",
        "epfo", "account", "atm", "upi",
        "aadhaar", "aadhar", "trai", "sim", "cbi", "courier",
        "parcel",
    ))
    return fraud_context and institution_context


def _is_identity_loan_or_sim_misuse_issue(q: str) -> bool:
    identity_context = _has_any(q, (
        "aadhaar", "aadhar", "uidai", "pan", "pan card",
        "kyc", "identity", "id proof",
    ))
    misuse_context = _has_any(q, (
        "used my", "someone used", "misuse", "misused", "identity misuse",
        "identity theft", "not mine", "without my consent", "fake",
        "opened with", "opened in my name", "in my name",
        "aadhaar used", "aadhar used", "pan used", "used for sim",
        "used to issue", "used to issue sim", "used to issue sims", "issued sim",
        "issued sims", "sim issued", "sims issued", "sim issued using",
        "sims issued using",
        "never took", "never taken", "i never took",
        "fraud case came to me", "someone opened", "opened bank account",
        "photocopy leaked", "copy leaked", "leaked in telegram",
    ))
    loan_or_sim_context = _has_any(q, (
        "loan", "fake loan", "nbfc", "finance company", "cibil",
        "credit report", "credit score", "credit bureau", "sim", "sims",
        "sim card", "sim cards", "mobile number", "fraud case", "fraud", "kyc loan",
        "bank account", "fake bank account", "account opened",
        "opened bank account",
    ))
    return identity_context and misuse_context and loan_or_sim_context


def _is_false_loan_credit_record_issue(q: str) -> bool:
    credit_record_context = _has_any(q, (
        "cibil", "credit report", "credit score", "credit bureau",
        "loan account", "loan shown", "loan showing", "loan opened",
        "loan in my name", "fake loan",
    ))
    false_loan_context = _has_any(q, (
        "fake loan", "which i never took", "i never took",
        "never took", "never taken", "not taken by me",
        "not my loan", "loan not mine", "opened with my pan",
        "opened with my aadhaar", "opened with my aadhar",
        "without my consent", "signature not mine", "fake signature",
        "did not sign", "didn't sign",
    ))
    identity_record_context = _has_any(q, (
        "pan", "pan card", "aadhaar", "aadhar", "kyc",
        "identity", "documents", "signature",
    )) or credit_record_context
    sim_or_non_credit_context = _has_any(q, (
        "sim", "mobile number", "phone number", "telecom",
    )) and not _has_any(q, ("loan", "cibil", "credit report", "credit score"))
    return credit_record_context and false_loan_context and identity_record_context and not sim_or_non_credit_context


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
    if _is_arrest_information_safeguard(q):
        return False
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
        "no complaint filed", "complaint not filed",
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
    if _is_wife_as_aggressor_issue(q):
        return False
    if _has_negated_sexual_coercion(q):
        return False
    marital_context = _has_any(q, ("husband", "wife", "spouse", "married", "marriage", "sasural", "in laws", "in-laws"))
    explicit_sexual_context = _has_any(q, (
        "sex", "sexual", "intimacy", "physical relation", "physical relationship",
        "touch", "touching", "rape", "marital rape", "bedroom",
    ))
    coercion_without_explicit_sex = _has_any(q, (
        "when i say no", "even when i say no", "without consent",
    ))
    if coercion_without_explicit_sex and not explicit_sexual_context:
        return False
    sexual_coercion = _has_any(q, (
        "forces me at night", "force me at night", "forced me at night",
        "forces sex", "forcing sex", "force sex", "forced sex", "marital rape",
        "forcing me for sex", "forces me for sex", "forced me for sex",
        "forcing her for sex", "forcing wife for sex", "forcing husband for sex",
        "sex when i say no", "when i say no", "even when i say no",
        "if i refuse sex", "when i refuse sex", "if i deny physical relation",
        "when i deny physical relation",
        "without consent", "unwell is there any law", "tired or unwell",
    ))
    threat_for_refusal = _has_any(q, ("threat", "threaten", "threatening", "threatens", "violent", "violence")) and _has_any(q, (
        "refuse sex", "refusing sex", "deny physical relation", "denying physical relation",
        "say no", "without consent",
    ))
    return marital_context and (sexual_coercion or threat_for_refusal)


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
        "pan card copy leaked", "pan copy leaked",
        "therapist leaked", "counselling chat", "counseling chat",
        "therapy chat", "mental health privacy", "medical privacy",
        "leaked my counselling", "leaked my counseling", "leaked my therapy",
    ))
    compensation_or_grievance = _has_any(q, (
        "compensation", "claim", "complain", "complaint", "grievance", "leaked",
        "misuse", "fraud", "fake account opened", "opened in my name",
        "fake bank account",
    ))
    return breach_context and compensation_or_grievance


def _is_mental_health_privacy_breach_issue(q: str) -> bool:
    mental_health_context = _has_any(q, (
        "therapist", "psychiatrist", "psychologist", "counsellor", "counselor",
        "counselling chat", "counseling chat", "therapy chat", "mental health",
        "mental-health", "medical privacy",
    ))
    leak_context = _has_any(q, (
        "leaked", "leak", "posted", "shared", "published", "twitter", "x ",
        "online", "privacy", "data breach",
    ))
    return mental_health_context and leak_context


def _has_msme_negation(q: str) -> bool:
    return _has_any(q, (
        "no msme registration", "not msme", "not an msme",
        "not msme registered", "not registered as msme",
        "not registered under msme", "not udyam registered",
        "no udyam", "no udyam registration", "without udyam",
    ))


def _is_msme_payment_route_issue(q: str) -> bool:
    if _has_msme_negation(q):
        return False
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
    fra_context = _has_any(q, (
        "fra", "forest rights", "fra 2006", "fra claim", "ifr", "cfr",
        "community forest", "forest rights committee", "frc", "sdlc", "dlc",
    ))
    forest_official_context = _has_any(q, ("forest guard", "forest guards", "forest officer", "forest department", "reserved forest"))
    protected_produce_or_title = _has_any(q, (
        "patta", "title", "bamboo", "tendu", "mahua", "minor forest produce",
        "community forest rights", "gram sabha", "community forest", "cfr", "ifr",
        "claim", "claim form", "fra claim", "forest rights claim",
        "claim under fra", "husband signature", "joint title", "forest produce",
        "farming since grandfather", "farming since", "land is reserve",
        "reserved land",
    ))
    interference_context = _has_any(q, (
        "cutting", "stopped", "seized", "reserved", "denied", "refused",
        "rejected", "without reason", "not giving", "not issuing", "no signature",
        "where to go", "how to complain", "what can i do",
        "saying our land is reserve",
    ))
    return (fra_context and (protected_produce_or_title or interference_context)) or (
        forest_official_context and protected_produce_or_title and interference_context
    )


def _is_forest_notice_non_fra_issue(q: str) -> bool:
    if _is_fra_forest_rights_issue(q):
        return False
    forest_context = _has_any(q, (
        "forest guard", "forest officer", "forest department", "forest land",
        "reserved forest", "forest notice", "range officer",
    ))
    notice_or_action = _has_any(q, (
        "notice", "encroach", "encroached", "encroachment", "remove",
        "evict", "eviction", "demolish", "seize", "seizure", "case filed",
        "what forum", "where to go",
    ))
    return forest_context and notice_or_action


def _is_name_change_identity_issue(q: str) -> bool:
    name_context = _has_any(q, (
        "change my surname", "change surname", "name change", "change my name",
        "legally change my name", "legally change name", "change legal name",
        "name spelling wrong", "spelling wrong in certificates",
        "surname after marriage", "change surname after marriage",
    ))
    record_context = _has_any(q, (
        "gazette", "official gazette", "newspaper", "affidavit",
        "passport", "aadhaar", "aadhar", "pan", "documents",
        "certificates", "school certificate", "marksheet",
    ))
    return name_context and record_context


def _is_marriage_name_change_issue(q: str) -> bool:
    name_context = _has_any(q, ("change my surname", "change surname", "name change", "change my name"))
    marriage_context = _has_any(q, ("after marriage", "married", "marriage", "husband surname", "wife surname"))
    gazette_context = _has_any(q, ("gazette", "publish", "official gazette", "newspaper", "affidavit"))
    return name_context and (marriage_context or gazette_context)


def _is_spa_raid_subject_issue(q: str) -> bool:
    spa_context = _has_any(q, ("spa", "massage parlour", "massage parlor", "parlour", "parlor"))
    raid_context = _has_any(q, ("raid", "raided", "police came", "police took", "took me", "station", "itpa", "pita", "cctv"))
    subject_context = _has_any(q, (
        "i just do massage", "i only do massage", "scared", "what will happen",
        "am i in trouble", "need lawyer", "ran away", "took me and other girls",
        "receptionist", "reception desk", "only worked", "only working",
    ))
    return spa_context and raid_context and subject_context


def _is_worksite_assault_injury_issue(q: str) -> bool:
    work_context = _has_any(q, (
        "site", "worksite", "mukadam", "thekedar", "contractor", "factory",
        "construction", "old wages", "wages",
    ))
    assault_context = _has_any(q, (
        "beat me", "beat worker", "beat labour", "beat labor",
        "contractor beat", "mukadam beat", "beaten", "beating",
        "assault", "hit me", "head injury", "stitches",
    ))
    injury_context = _has_any(q, ("injury", "head", "stitches", "medical", "hospital", "fracture", "blood"))
    return work_context and assault_context and injury_context


def _is_inlaw_jewellery_breach_issue(q: str) -> bool:
    inlaw_context = _has_any(q, (
        "daughter in law", "daughter-in-law", "son's wife", "bahu",
        "mother in law", "mother-in-law", "father in law", "father-in-law",
        "in laws", "in-laws", "saas", "sasural",
    ))
    jewellery_context = _has_any(q, ("jewellery", "jewelry", "gold", "ornaments", "stridhan", "streedhan"))
    entrustment_context = _has_any(q, (
        "safe keeping", "safekeeping", "not returning", "refusing to return",
        "refuse to return", "kept", "has my", "took my", "withholding",
    ))
    return inlaw_context and jewellery_context and entrustment_context


def _is_streedhan_return_issue(q: str) -> bool:
    relationship_context = _has_any(q, (
        "husband", "wife", "mother in law", "mother-in-law",
        "father in law", "father-in-law", "in laws", "in-laws",
        "saas", "sasural", "after separation", "marriage",
    ))
    jewellery_context = _has_any(q, (
        "streedhan", "stridhan", "marriage gold", "my gold",
        "jewellery", "jewelry", "ornaments", "locker keys",
    ))
    withholding_context = _has_any(q, (
        "not returning", "refusing return", "refusing to return",
        "has my", "kept", "took", "withholding", "not giving back",
        "what case", "case can i file",
    ))
    return relationship_context and jewellery_context and withholding_context


def _is_panchayat_common_land_issue(q: str) -> bool:
    local_body_context = _has_any(q, ("sarpanch", "panchayat", "gram sabha", "mukhiya"))
    common_land_context = _has_any(q, ("common village land", "common land", "village land", "panchayat land", "gairmazarua"))
    improper_process = _has_any(q, ("no panchayat meeting", "no meeting", "no resolution", "to his brother", "without meeting", "allotting"))
    return local_body_context and common_land_context and improper_process


def _is_pressure_property_transfer_issue(q: str) -> bool:
    property_context = _has_any(q, ("property", "prop", "house", "flat", "land", "gift deed", "signed property", "signed prop"))
    pressure_context = _has_any(q, ("under pressure", "coercion", "forced", "icu", "hospital", "medical", "not conscious"))
    challenge_context = _has_any(q, ("challenge", "cancel", "set aside", "revoke", "signed", "transfer"))
    return property_context and pressure_context and challenge_context


def _is_juvenile_age_custody_issue(q: str) -> bool:
    adult_record_correction = (
        _has_age_at_least(q, 18)
        and _has_any(q, (
            "fir says minor", "fir shows minor", "fir says juvenile",
            "fir shows juvenile", "written minor", "written juvenile",
            "charge sheet says 17", "chargesheet says 17", "case paper says 17",
            "old school certificate wrong", "wrong school certificate",
            "wrong school dob", "wrong dob", "wrong date of birth",
            "minor by mistake", "age record", "correct age record",
        ))
    )
    if adult_record_correction:
        return False
    child_person = (
        "son|daughter|boy|girl|child|minor|brother|sister|nephew|niece|cousin|schoolboy|schoolgirl"
    )
    child_context = (
        _has_age_under(q, 18)
        or _has_any(q, ("juvenile", "minor", "child in conflict"))
        or _has_any(q, (
            "child accused", "minor accused", "child sent to observation home",
            "child in observation home", "child at observation home",
            "child is in observation home", "child being called to police station",
            "police call him 16", "police calls him 16", "police called him 16",
            "police call her 16", "police calls her 16", "police called her 16",
        ))
        or re.search(rf"\b(?:{child_person})\s+(?:is\s+)?(?:[1-9]|1[0-7])\s*(?:year|years|yr|yrs)\b", q) is not None
        or re.search(rf"\b(?:[1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s+(?:{child_person})\b", q) is not None
        or re.search(r"\b(?:him|her)\s+(?:is\s+)?(?:[1-9]|1[0-7])\b", q) is not None
    )
    custody_context = _has_any(q, (
        "adult jail", "adult lockup", "lockup", "jail", "prison",
        "observation home", "arrested", "detained", "custody",
        "police station", "picked by police", "kept in station",
        "station with adults", "kept with adults", "police picked",
        "kept him overnight with adults", "kept her overnight with adults",
        "overnight with adults",
    ))
    accused_context = _has_any(q, ("accused", "which court decides", "court decides", "juvenile court", "jjb", "adult case", "court ignoring", "police says"))
    age_proof_context = _has_any(q, (
        "age proof", "school certificate", "birth certificate", "verify age",
        "age determination", "pocso", "aadhaar", "school dob", "dob proof",
        "school tc", "age certificate", "school id", "school record",
        "school records", "id says age", "id says he is", "id says she is",
    ))
    transfer_context = _has_any(q, ("adult jail", "adult prison", "adult lockup", "observation home", "transfer", "shift", "remove from jail", "remove from lockup", "jjb transfer"))
    jjb_process_context = _has_any(q, ("jjb", "juvenile justice board", "parents refuse", "ask jjb", "observation home"))
    return child_context and (custody_context or accused_context or jjb_process_context) and (age_proof_context or transfer_context or accused_context or jjb_process_context)


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
        "property transfer", "transfer in hospital", "sale deed",
    ))
    dispute_context = _has_any(q, (
        "blank paper", "under pressure", "not caring", "cancel",
        "cancelled", "claims half", "half share", "didn't sign",
        "did not sign", "produced as", "challenge", "not taking care",
        "fake signature", "forged", "forgery", "fraudulently",
        "false document",
    ))
    return property_context and dispute_context


def _has_document_forgery_or_false_document_terms(q: str) -> bool:
    return _has_any(q, (
        "thumb impression", "blank paper", "fake signature", "forged",
        "forgery", "didn't sign", "did not sign", "produced as",
        "false document", "fraud deed", "fraudulent deed",
    ))


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
    if _has_any(q, ("notice", "summons", "appear")) and not _has_any(q, ("arrested", "detained", "custody", "lockup", "police picked", "crime branch", "picked by", "utha liya")):
        return False
    arrest_context = _has_any(q, (
        "arrest", "arrested", "police picked", "custody", "lockup",
        "detained", "crime branch", "picked by", "picked up by",
        "took brother", "took my brother", "took my son", "took my husband",
        "utha liya",
    ))
    production_context = _has_any(q, (
        "magistrate ke samne", "magistrate ke saamne", "produce before magistrate",
        "produced before magistrate", "not produced", "24 hours",
        "twenty four hours", "24 hrs", "twenty-four hours",
        "no production", "not produced in court", "not taken to court",
        "court production", "production in court", "kab le jana", "court ke samne",
    ))
    prolonged_context = _has_any(q, ("5 din", "five days", "5 days", "24 hours passed", "one day passed")) and _has_any(q, ("magistrate", "custody", "lockup", "detained", "police station", "crime branch"))
    return arrest_context and (production_context or prolonged_context)


def _is_arrest_information_safeguard(q: str) -> bool:
    arrest_context = _has_any(q, (
        "arrest", "arrested", "detained", "custody", "lockup",
        "police took", "police picked", "police has picked",
        "police have picked", "picked my", "picked up",
        "picked by", "picked up by", "taken by police", "crime branch",
        "took my son", "took my brother", "took my husband", "utha liya",
    ))
    information_context = _has_any(q, (
        "arrest memo", "no arrest memo", "dk basu", "d.k. basu",
        "grounds of arrest", "not informed", "family not informed",
        "no fir copy", "secret", "where taken", "not telling station",
        "not telling the station", "not telling case", "not telling station or case",
        "not telling which station", "not telling where", "from my home",
        "not showing station", "not allowing lawyer", "lawyer not allowed",
        "not allowing advocate", "from home", "in the night", "at night",
        "24 hours", "24 hrs", "no production", "not produced",
        "phone off", "phone switched off", "not reachable",
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
        "cannot leave until", "can't leave until", "cant leave until",
        "cannot leave till", "can't leave till", "cant leave till",
        "not allowed to leave", "not allow me to leave", "not allow us to leave",
        "keeping family", "locked", "cards passport", "keeping our cards",
        "documents retained", "aadhaar original", "passport", "loan finish",
        "debt bondage",
    ))
    debt_control_context = _has_any(q, ("advance", "debt")) and _has_any(q, (
        "must work", "cannot go home", "cannot leave until", "can't leave until",
        "cant leave until", "cannot leave till", "can't leave till", "cant leave till",
        "not letting", "not allowed to leave", "hostage", "loan finish", "till loan",
    ))
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
        "kid", "baby", "girl child", "boy child", "grandson",
        "granddaughter",
    )) or _has_age_under(q, 18)
    custody_context = _has_any(q, (
        "custody", "custody order", "took our", "taken our", "took my",
        "took child", "took the child", "took our child", "taken child",
        "left me and took child", "left with child", "left with the child",
        "left matrimonial home with child", "left home with child",
        "left house with child",
        "parents in law took", "in laws took", "took her away", "took him away",
        "not letting me meet", "not letting us meet", "blocked calls",
        "not allowing video calls", "video calls", "changed number",
        "changed phone number", "hiding our", "hiding my",
        "meet her", "meet him", "get her back", "get him back",
        "return child", "bring back", "not bringing back",
        "refuse to return", "refuses to return", "custody petition",
        "not allowing me to meet", "not letting mother see",
        "not letting father see", "letting mother see", "letting father see",
        "visitation rights", "want visitation", "wants visitation",
        "meet my child", "see my child", "see her", "see him",
        "seeing my son", "seeing my daughter", "seeing child",
        "see child", "meet child", "father to see child",
        "mother to see child", "not allowing father", "not allowing mother",
        "refuses weekend meeting", "refuse weekend meeting",
        "not sharing school location", "blocked all calls",
        "blocked calls with", "blocking calls with",
        "wants to meet", "want to meet", "no court order",
    ))
    family_context = _has_any(q, (
        "husband", "wife", "ex husband", "ex wife", "ex partner",
        "ex", "other parent", "father", "mother", "parents in law", "in laws", "family court",
        "grandparent", "grandparents", "grandfather", "grandmother",
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
    social_context = _has_any(q, (
        "village", "mob", "people", "saas", "mother", "aunt", "woman",
        "nani", "dadi", "mausi",
        "ojha", "neighbour", "neighbor", "neighbours", "neighbors",
        "public", "assam", "jharkhand", "chhattisgarh", "bihar",
    ))
    violence_context = _has_any(q, (
        "beaten", "beat", "attack", "attacked", "assault", "hair cut",
        "paraded", "throw me out", "threat", "threaten", "threatened",
        "threatening", "kill", "burn", "stripped", "disrobed",
        "public humiliation", "humiliated", "naked in public",
        "parade", "parade her", "forced her to leave",
        "forced her to leave home", "leave home",
    ))
    branding_context = _has_any(q, ("branded", "labelled", "called", "calling", "wrote", "written", "painted"))
    witch_or_black_magic = "witch" in q or "black magic" in q
    return witch_or_black_magic and ((branding_context and social_context) or violence_context)


def _is_builder_rera_issue(q: str) -> bool:
    real_estate_context = _has_any(q, (
        "builder", "developer", "promoter", "rera", "flat", "apartment",
        "housing project", "real estate project",
    ))
    possession_context = _has_any(q, (
        "possession", "occupancy certificate", "occupation certificate",
        "completion certificate", "handover", "handover date",
        "missed deadline", "deadline", "delayed", "delay", "not giving",
        "not handed over", "not handing over",
        "wait indefinitely", "waiting indefinitely", "promised oc",
        "defective", "defect", "not repairing", "repairing", "leakage",
    )) or re.search(r"\b(?:oc|cc)\b", q) is not None
    money_or_remedy_context = _has_any(q, (
        "full money", "all money", "paid full", "paid everything",
        "taking full money", "took full money", "booking amount",
        "refund", "not refunding", "compensation", "layout changed",
        "changed layout", "agreement", "allotment", "registered project",
        "rera registered", "full payment", "after full payment",
    ))
    return real_estate_context and (possession_context or money_or_remedy_context)


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
    if _is_tribal_land_transfer_issue(q):
        return True
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
    if _has_any(q, ("burnt", "burned", "burning", "arson", "set fire", "fire")) and _has_any(q, (
        "hut", "house", "home", "jhuggi", "jhopdi", "complaint", "fir", "thana", "police",
    )):
        return False
    tribal_context = _has_any(q, (
        "tribal", "adivasi", "scheduled tribe", "munda", "santhal",
        "oraon", "khuntkatti", "non tribal", "non-tribal",
        "cnt", "chotanagpur", "chota nagpur", "santhal parganas",
        "scheduled area", "agency area", "agency village",
    ))
    tribal_context = tribal_context or re.search(r"\bst\s+(?:land|plot|property)\b", q) is not None
    land_noun_context = bool(re.search(
        r"\b(?:land|plot|raiyat|tenancy|khata|khasra)\b",
        q,
    )) or _has_any(q, ("cnt", "chotanagpur", "chota nagpur", "santhal parganas"))
    transfer_context = _has_any(q, (
        "sold", "sale deed", "land transfer", "land transferred",
        "transferred my", "transferred our", "transferred his",
        "transferred her", "transferred baba", "transferred grandfather",
        "plot transfer", "registered deed", "without our consent",
        "restore", "restoration", "grabbed", "land grab",
        "land restoration", "mortgage", "mortgaged", "sahukar",
        "moneylender", "refusing return", "refusing to return",
        "not returning land", "took my land", "mutation", "mutation record",
        "mutated", "patwari mutated", "record changed", "khata changed",
        "khata transfer", "patwari changed", "bought", "purchased",
        "non tribal bought", "non-tribal bought", "non tribal purchased",
        "non-tribal purchased", "non tribal buyer", "non-tribal buyer", "buyer", "giving my",
        "giving our", "giving his", "giving her",
    )) or bool(re.search(
        r"\b(?:transfer(?:red)?\s+of\s+(?:tribal\s+)?(?:land|plot)|transferred\s+.*\b(?:land|plot)\b|mutation\s+.*\b(?:land|plot)\b|giving\s+.*\b(?:land|plot)\b.*\b(?:non[-\s]?tribal|buyer)\b)\b",
        q,
    ))
    return tribal_context and land_noun_context and transfer_context


def _is_cheque_bounce_issue(q: str) -> bool:
    if _has_any(q, ("notice under 138", "section 138", "ni act 138", "cheque 138", "138 cheque", "138 notice")):
        return True
    cheque_context = _has_any(q, ("cheque", "cheques", "post dated", "post-dated", "security cheque"))
    misuse_context = _has_any(q, (
        "misusing", "misuse", "deposited", "presented", "bank return",
        "return memo", "legal notice", "notice under 138", "dishonour",
        "dishonored", "insufficient funds", "bounced", "stop payment",
        "payment stopped", "cheque return", "cheque returned",
        "bank returned", "bank returned it", "returned by bank",
        "returned unpaid", "was returned", "got returned",
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
    if (
        _is_marriage_misrepresentation_issue(q)
        or _is_marital_intimacy_breakdown_issue(q)
        or _is_spousal_adultery_marriage_breakdown_issue(q)
        or _is_mutual_divorce_issue(q)
    ):
        return True
    if _has_any(q, ("triple talaq", "talaq-e-biddat", "instant talaq", "talaq on whatsapp")):
        return _has_any(q, ("husband", "wife", "muslim", "marriage", "nikah", "whatsapp", "remedy"))
    if _has_any(q, ("legal age", "age legal", "marriage age", "got married")) and _has_any(q, ("married", "marriage", "family says illegal")):
        return True
    return _has_any(q, _FAMILY_MARRIAGE_STATUS_WORDS) and _has_any(q, ("husband", "wife", "marriage", "divorce", "land", "share", "protection", "muslim", "hindu"))


def _is_mutual_divorce_issue(q: str) -> bool:
    if _is_family_safety_issue(q):
        return False
    return _has_any(q, _MUTUAL_CONSENT_DIVORCE_WORDS) and _has_any(q, ("divorce", "13b", "separation"))


def _is_joint_property_sale_issue(q: str) -> bool:
    if _is_wife_as_aggressor_issue(q):
        return False
    if _has_any(q, ("tribal", "non tribal", "non-tribal", "adivasi", "scheduled tribe", "scheduled area")):
        return False
    if _has_any(q, ("own plot", "own land", "own property", "own house")):
        return False
    if _has_any(q, _TAX_GST_WORDS) or _has_any(q, ("tax applies", "capital gains", "file itr")):
        return False
    joint_context = _has_any(q, (
        "joint name", "jointly", "together", "co owner", "co-owner",
        "coowned", "co-owned", "common fund", "both bought", "we bought",
        "we purchased", "both purchased", "brother and i bought",
        "sister and i bought", "brother and i purchased", "sister and i purchased",
        "common land", "common property", "joint flat", "joint share",
        "without consent", "brother sold", "sister sold",
    ))
    property_context = _has_any(q, ("plot", "land", "house", "flat", "property", "sale deed"))
    sale_context = _has_any(q, ("sold", "sale", "transferred", "registered", "mutation"))
    return property_context and sale_context and joint_context


def _is_ancestral_land_sale_issue(q: str) -> bool:
    if _has_any(q, ("tribal", "non tribal", "non-tribal", "adivasi", "scheduled tribe", "scheduled area")):
        return False
    property_context = _has_any(q, (
        "ancestral", "dada", "grandfather", "grandfather's",
        "father land", "father's land", "father property", "father's property",
        "family land", "family property",
    )) and _has_any(q, ("land", "plot", "house", "property"))
    sale_context = _has_any(q, ("selling", "sold", "sale", "sale deed", "transfer", "transferred", "mutation"))
    family_context = _has_any(q, ("brother", "uncle", "cousin", "family", "heir", "legal heir", "father", "mother"))
    exclusion = _has_any(q, ("refund", "defective", "damaged phone", "online order", "delivery", "warranty"))
    return property_context and sale_context and family_context and not exclusion


def _is_tenant_nonpayment_possession_issue(q: str) -> bool:
    tenancy = _has_any(q, ("tenant", "tenent", "landlord", "rent agreement", "lease"))
    possession = _has_any(q, (
        "not vacating", "not leaving", "refusing to vacate", "evict", "eviction",
        "possession", "changed lock", "broke lock", "broke my lock", "locked me out",
        "lockout", "lock out", "threw my things", "thrown my things",
    ))
    arrears = _has_any(q, ("not paying rent", "rent not paid", "rent arrears", "unpaid rent", "no rent", "rent late", "stopped paying rent"))
    return tenancy and (possession or arrears)


def _is_marriage_misrepresentation_issue(q: str) -> bool:
    marriage_context = _has_existing_or_completed_marriage_context(q)
    misrep_context = _has_any(q, (
        "lied", "lie", "lies", "false", "fraud", "misrepresented",
        "misrepresentation", "concealed", "hid", "hide", "hidden", "fake",
    ))
    life_fact_context = _has_any(q, (
        "job", "salary", "income", "work", "employment", "qualification",
        "education", "degree", "health", "disease", "hiv", "hiv positive",
        "aids", "already married", "earlier marriage", "previous marriage",
        "prior marriage", "first marriage", "sexual orientation", "gay",
        "lesbian", "same sex", "same-sex", "lgbt", "lgbtq", "queer",
    ))
    return marriage_context and misrep_context and life_fact_context


def _is_pre_marriage_health_disclosure_issue(q: str) -> bool:
    pre_marriage = _has_any(q, (
        "supposed to marry", "marry next month", "marriage next month",
        "wedding next month", "before marriage", "not married yet",
        "engagement", "engaged", "fiance", "fiancee", "prospective bride",
        "prospective groom",
    ))
    health = _has_any(q, (
        "hiv", "hiv positive", "aids", "std", "sti", "disease",
        "health issue", "medical condition",
    ))
    disclosure = _has_any(q, (
        "hid", "hide", "hides", "concealed", "did not tell",
        "didn't tell", "found out", "lied", "false",
    ))
    return pre_marriage and health and disclosure


def _is_writ_constitution_procedure_issue(q: str) -> bool:
    writ_context = _has_any(q, ("writ", "mandamus", "article 226", "article 32"))
    legal_help_context = _has_any(q, (
        "when can i file", "how to file", "what is", "difference between",
        "against government", "government officer", "public authority",
        "complain", "complaint", "high court", "supreme court",
    ))
    return writ_context and legal_help_context


def _has_existing_or_completed_marriage_context(q: str) -> bool:
    if _has_any(q, (
        "not married", "not married yet", "never married", "marriage not happened",
        "wedding not happened", "wedding cancelled", "engagement", "engaged",
        "fiance", "fiancee", "prospective bride",
        "prospective groom",
    )) and not _has_any(q, ("husband", "wife", "spouse")):
        return False
    return _has_any(q, (
        "husband", "wife", "spouse", "married", "got married", "after marriage",
        "after wedding", "wedding happened", "marriage happened", "marriage took place",
        "wedding took place", "marriage certificate", "our marriage", "my marriage",
    ))


def _is_marital_intimacy_breakdown_issue(q: str) -> bool:
    no_coercion_context = _has_any(q, (
        "do not want to force", "don't want to force", "dont want to force",
        "will not force", "won't force", "wont force",
        "no force", "without forcing",
    ))
    if _has_any(q, ("force", "forcing", "forced", "without consent", "no consent", "threat", "threaten", "threatening", "threatens", "beat", "beating", "violent", "violence", "assault", "rape")) and not no_coercion_context:
        return False
    spouse_context = _has_any(q, ("wife", "husband", "spouse", "marriage", "married"))
    intimacy_context = _has_any(q, (
        "denies sex", "denied sex", "denying sex", "refuses sex", "refusing sex",
        "no sex", "physical relation", "physical relationship",
        "denying physical relation", "denying physical relationship",
        "conjugal", "intimacy",
    ))
    return spouse_context and intimacy_context


def _is_testamentary_issue(q: str) -> bool:
    testamentary_context = _has_any(q, (
        "written will", "registered will", "unregistered will", "probate",
        "letter of administration", "testament", "testamentary",
        "execute will", "execute a will", "made a will", "left a will",
        "will deed", "make a will", "write a will", "draft a will",
        "create a will", "prepare a will", "register a will",
        "make will", "write will", "draft will", "create will",
        "prepare will", "register will", "execute will",
        "make my will", "write my will", "draft my will", "create my will",
        "prepare my will", "register my will", "execute my will",
        "registered my will", "get my will registered", "will registration",
        "wrote will", "wrote a will", "wrote his will", "wrote her will",
        "latest will", "valid will", "will giving", "will in sub registrar",
        "attested will", "will witness",
        "will witnesses", "will revocation", "revocation of will",
        "change my will", "update my will", "probate of will", "contest will",
        "executor of will", "bequeath", "bequest",
    ))
    if testamentary_context:
        return True
    if "will" not in q:
        return False
    if re.search(
        r"\bwill\s+(?:police|court|magistrate|judge|station|sho|io|officer|"
        r"company|employer|landlord|tenant|bank|school|college|government|"
        r"municipality|builder|seller|husband|wife|son|daughter|brother|"
        r"sister|they|he|she|it|someone|people)\b",
        q,
    ):
        return False
    legal_context = _has_any(q, (
        "property", "assets", "house", "flat", "land", "plot", "heir", "heirs",
        "children", "son", "daughter", "father", "mother", "beneficiary",
        "caretaker", "registered", "registration", "valid", "latest",
        "attestation", "witness", "sub registrar", "sub-registrar",
    ))
    will_verb_context = _has_any(q, (
        "make", "making", "made", "write", "written", "wrote", "draft",
        "prepare", "execute", "register", "registered", "change", "update",
        "cancel", "revoke", "revise", "giving more", "give more",
    ))
    return legal_context and will_verb_context


def _is_succession_issue(q: str) -> bool:
    if _is_testamentary_issue(q):
        return True
    if (
        _has_any(q, ("daughter", "daughters", "married daughter", "girl child"))
        and _has_any(q, ("ancestral", "coparcener", "father land", "father's land", "agricultural land", "family land"))
        and _has_any(q, ("no share", "have no share", "denied share", "denying share", "not giving share", "share"))
    ):
        return True
    if _has_any(q, ("inheritance", "succession", "father died", "mother died", "share from", "property share", "muslim inheritance", "coparcener")):
        return True
    if (
        _has_any(q, ("who inherits", "who will inherit", "who inherit", "inherits his", "inherits her", "legal heirs of", "heirs of"))
        and _has_any(q, ("property", "prop", "self acquired", "self-acquired", "house", "flat", "land", "estate", "asset"))
        and _has_any(q, ("hindu", "muslim", "christian", "parsi", "uncle", "aunt", "father", "mother", "widow", "wife", "daughter", "son", "children", "no children", "not married", "unmarried"))
    ):
        return True
    if _has_any(q, ("inherit", "heir", "heirs", "sunni law", "hanafi")) and _has_any(q, ("muslim", "widow", "wife", "daughter", "father")):
        return True
    if _has_any(q, ("widow", "husband")) and _has_any(q, ("stepchildren", "step children", "children", "heirs")) and _has_any(q, ("property", "flat", "house", "land", "share")):
        return True
    personal_law_context = _has_any(q, ("parsi", "christian", "muslim", "widow", "sisters", "brothers", "children", "heirs"))
    death_context = _has_any(q, ("passed away", "died", "death", "dead", "late husband", "late wife", "late father", "late mother"))
    property_context = _has_any(q, (
        "property", "prop", "flat", "house", "land", "estate", "asset", "assets",
        "share", "divided", "divide", "divides", "division", "partition",
        "no will", "without will", "without a will", "no testament", "intestate",
        "inherit", "inheritance", "get nothing",
    ))
    return death_context and property_context and personal_law_context


def _succession_route(q: str) -> MatterRoute:
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


def _is_caste_certificate_appeal(q: str) -> bool:
    certificate_context = _has_any(q, (
        "caste certificate", "caste cert", "sc certificate", "sc cert",
        "st certificate", "st cert",
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
        "cab app", "taxi app",
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
        "thela", "rehri", "vendor zone", "vegetable cart", "fruit cart",
        "hawker zone", "vegetable stall", "vending receipt",
        "municiple seized", "hawker inspector", "vending certificate",
        "certificate of vending", "town vending committee card",
        "municipal people took my goods", "municipal people took goods",
    )):
        return True
    physical_vendor_context = _has_any(q, (
        "cart", "tea cart", "hawker", "fish market", "vegetable",
        "vegetable stall", "stall", "footpath", "roadside",
        "vendor zone", "street vending goods", "vending goods", "thela",
        "labour chowk", "vending certificate", "certificate of vending",
        "vending receipt",
        "goods", "footpath stall",
    ))
    enforcement_context = _has_any(q, (
        "municipal", "municipality", "nagar nigam", "nagar palika",
        "panchayat", "fine", "license", "licence", "seized", "removed",
        "without notice", "ward office", "inspector", "remove", "allotted",
        "removing", "people are removing",
        "pay 2000", "bribe", "municiple", "took goods", "took my goods",
        "took my fruit cart",
        "goods are missing", "without receipt", "asking fine",
    ))
    municipal_context = _has_any(q, (
        "municipal", "municipality", "municipal corporation", "corporation",
        "nagar nigam", "nagar palika", "ward office", "panchayat",
    ))
    return (
        _has_any(q, ("vendor", "hawker")) and physical_vendor_context and enforcement_context
    ) or (municipal_context and physical_vendor_context and enforcement_context)


def _is_cyber_issue(q: str) -> bool:
    if _is_school_tc_or_admission_money_issue(q):
        return False
    if _is_family_marriage_status_issue(q) or _is_workplace_sexual_harassment(q):
        return False
    if _is_benign_crypto_or_creator_discussion(q):
        return False
    if _is_identity_loan_or_sim_misuse_issue(q):
        return True
    if _is_crypto_wallet_transfer_fraud_issue(q):
        return True
    if _has_any(q, ("telegram", "crypto", "investment group")) and _has_any(q, (
        "rugpull", "rugpulled", "scam", "fraud", "lost", "took",
        "3 lakh", "2 lakh",
        "otp", "seed phrase", "connect wallet", "wallet drained",
        "drained account", "admin vanished", "stole my crypto",
    )):
        return True
    if _has_any(q, (
        "dating app", "posted my number", "posting my number",
        "shared my number", "posted my phone number",
        "posting my phone number", "shared my phone number",
        "phone number on dating app", "mobile number on dating app",
    )):
        number_abuse_context = _has_any(q, (
            "unknown person", "stranger", "without consent", "fake profile",
            "fake account", "harass", "harassing", "abuse", "threat",
            "posted my number", "posting my number", "posted my phone number",
            "posting my phone number", "strangers are calling",
            "unknown people are calling", "calls from strangers",
        ))
        platform_context = _has_any(q, (
            "dating app", "tinder", "bumble", "social media", "online",
            "instagram", "facebook", "whatsapp",
        ))
        if number_abuse_context and platform_context:
            return True
    if _has_any(q, ("stalker", "stalking", "stalked", "stalks", "follows", "following", "followed")) and _is_explicit_physical_stalking_context(q):
        return False
    if _has_any(q, ("stalker", "stalking", "stalked", "stalks", "follows", "following", "followed")) and not _has_any(q, (
        "cyber", "online", "instagram", "insta", "facebook", "whatsapp",
        "telegram", "tinder", "bumble", "dating app", "dm", "dms",
        "message", "messages", "profile", "social media",
    )):
        return False
    if _has_any(q, _CYBER_WORDS):
        return True
    if not _has_any(q, _INTIMATE_IMAGE_WORDS):
        return False
    if _has_any(q, _IMAGE_ABUSE_CONTEXT_WORDS):
        return True
    if _has_any(q, _INTIMATE_IMAGE_SERVICE_WORDS):
        return False
    return _has_any(q, _INTIMATE_IMAGE_RISK_WORDS)


def _is_school_tc_or_admission_money_issue(q: str) -> bool:
    school_context = _has_any(q, ("school", "principal", "teacher", "headmaster", "head teacher"))
    child_context = _has_any(q, ("child", "son", "daughter", "student", "pupil", "class"))
    education_record_context = _has_any(q, (
        "tc", "transfer certificate", "school leaving certificate",
        "admission", "failed", "exam", "fees", "fee", "rte",
    ))
    demand_or_refusal_context = _has_any(q, (
        "demanding money", "asking money", "asked money", "money to give",
        "bribe", "donation", "capitation", "not giving", "refusing",
        "refused", "denied", "denying", "where to go",
    ))
    return school_context and education_record_context and (child_context or demand_or_refusal_context)


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


def _is_crypto_wallet_transfer_fraud_issue(q: str) -> bool:
    if _is_benign_crypto_or_creator_discussion(q):
        return False
    crypto_context = _has_any(q, (
        "crypto", "usdt", "coin", "token", "crypto wallet",
        "telegram crypto", "crypto group",
    )) or (
        _has_any(q, ("telegram", "wallet"))
        and _has_any(q, ("group", "transfer", "vanished", "fraud", "scam"))
    )
    fraud_context = _has_any(q, (
        "fraud", "scam", "rugpull", "rug pull", "rugpulled", "rug pulled",
        "vanished", "drained", "stole", "stolen", "took", "wallet transfer fraud",
        "transfer fraud",
    ))
    money_context = _has_any(q, (
        "money", "amount", "lakh", "wallet", "crypto", "usdt", "coin",
        "token", "transfer",
    ))
    ordinary_service_context = _has_any(q, (
        "paytm", "phonepe", "gpay", "google pay", "refund",
        "support not replying", "customer care not replying",
    )) and not _has_any(q, ("crypto", "usdt", "coin", "token", "telegram"))
    return crypto_context and fraud_context and money_context and not ordinary_service_context


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
        "rider", "driver", "fantasy app", "crypto exchange",
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
    aggregator_context = _has_any(q, ("uber", "ola", "cab app", "taxi app", "cab aggregator", "taxi aggregator", "ride hailing", "ride-hailing"))
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
        "platform partner", "partner", "vehicle integrated", "driving",
        "drive for", "driving for",
    ))
    platform_action = _has_any(q, (
        "deactivated", "suspended", "id blocked", "driver id blocked",
        "profile blocked", "rating low", "low rating", "off-boarded",
        "offboarded", "off boarded",
    ))
    return aggregator_context and driver_context and platform_action


def _is_cab_passenger_platform_issue(q: str) -> bool:
    if _is_cab_aggregator_driver_issue(q):
        return False
    aggregator_context = _has_any(q, (
        "uber", "ola", "cab app", "cab aggregator", "taxi aggregator",
        "ride hailing", "ride-hailing",
    ))
    passenger_service_context = _has_any(q, (
        "cancelled ride", "canceled ride", "ride cancelled",
        "ride canceled", "deducted money", "not refunding", "no refund",
        "refund", "extra fare", "charged extra fare", "longer route",
        "driver abused", "driver misbehaved", "platform closed complaint",
        "customer care not helping", "customer support not helping",
        "cancellation fee", "deducted cancellation", "wallet",
        "support bot", "closed ticket",
        "fare", "trip", "ride",
    ))
    return aggregator_context and passenger_service_context


def _cyber_required_sources(q: str) -> list[str]:
    sources = ["Information Technology Act 2000", "BNS/BNSS or IPC/CrPC based on incident date"]
    if _is_child_intimate_image(q):
        sources[0] = "Information Technology Act 2000 section 67B for child sexual-image electronic publication"
        sources.append("POCSO Act 2012 where the intimate image or sexual content involves a child")
    return sources


def _is_child_intimate_image(q: str) -> bool:
    if _has_any(q, _CSAM_WORDS):
        return True
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
    if _is_wife_as_aggressor_issue(q):
        return False
    if _has_negated_sexual_coercion(q) and not _has_any(q, (
        "beat", "beating", "slap", "slapped", "slaps", "hit", "threat", "locked", "unsafe", "dowry",
        "grabbed", "touching", "touched",
    )):
        return False
    has_family_context = _has_any(q, (
        "domestic violence", "husband", "wife", "spouse", "in laws", "mother in law",
        "father in law", "dowry", "marriage", "married", "live in partner",
        "live-in partner", "domestic relationship", "husband's brother",
        "husbands brother", "brother in law", "brother-in-law", "in-laws",
        "sasural", "sasural people", "matrimonial home", "shared house",
        "shared household", "he gets angry", "my parents say all marriages",
    ))
    has_immediate_safety = _has_any(q, (
        "husband beat", "husband is beating", "beating me", "beats me",
        "slap", "slaps me", "slapped me", "hit me", "hits me", "hitting me",
        "punched", "punching", "assaulted me", "assault", "locked", "threat", "threatens",
        "threatened", "threatening", "kill", "no food", "not giving food",
        "threw me out", "throw me out", "get out", "evict", "evict me",
        "remove me from", "no place to stay", "not allowing me to call",
        "unsafe", "grabbed my hand", "grabbed me",
        "touching me", "touched me", "making me uncomfortable", "uncomfortable",
        "forces sex", "forcing sex", "force sex", "forced sex", "marital rape",
        "even when i say no", "sex when i say no", "ghar se nikal",
        "nikal diya", "raat ko", "sorry next day", "should i stay",
    ))
    implied_domestic_residence_risk = (
        _has_any(q, ("slapped me", "hit me", "punched me", "assaulted me", "beat me"))
        and _has_any(q, ("child", "get out", "no place to stay", "home", "house", "today", "tonight"))
    )
    return (has_family_context and has_immediate_safety) or implied_domestic_residence_risk


def _is_wife_as_aggressor_issue(q: str) -> bool:
    if _is_accused_498a_issue(q):
        return False
    wife_context = _has_any(q, (
        "my wife", "wife slapped", "wife hit", "wife beat", "wife beats",
        "wife beating", "wife is beating", "wife took", "wife threw",
        "wife kicked", "wife threatens", "wife threatened",
    ))
    first_person_victim = _has_any(q, (
        "slapped me", "hit me", "beat me", "beats me", "hitting me",
        "threatens me", "threatened me", "threatening me", "abuses me",
        "forces sex", "forcing sex", "force sex", "forced sex", "sex without consent",
        "sexual assault", "sexually assaulted me", "sexually assaulting me",
        "assaulted me sexually",
        "took my salary", "takes my salary", "my salary", "my atm",
        "atm card", "bank card", "not giving me money", "against me",
        "threw me out", "kicked me out", "locked me out", "not allowing me entry",
        "not letting me enter", "not letting me in", "not allowing me in",
        "took my jewellery", "took my jewelry", "took my gold", "my jewellery",
        "my jewelry", "my gold", "my documents", "took my property",
        "stole my property", "sold my property", "transferred my property",
        "took my house papers", "sold my house", "transferred my house",
    ))
    return wife_context and first_person_victim and not _has_any(q, (
        "husband slapped", "husband hit", "husband beat", "husband took",
        "my husband",
    ))


def _is_spousal_property_return_issue(q: str) -> bool:
    if _is_domestic_residence_issue(q):
        return False
    if _is_streedhan_return_issue(q) and _has_any(q, (
        "streedhan", "stridhan", "in laws", "in-laws", "mother in law",
        "father in law", "husband died", "after husband died", "widow",
    )):
        return False
    if _is_wife_as_aggressor_issue(q) and not _has_any(q, (
        "left house", "left home", "left me", "not returning",
        "not giving back", "refusing to return", "withholding",
    )):
        return False
    spouse_context = _has_any(q, (
        "my wife", "my husband", "wife", "husband", "spouse",
        "ex wife", "ex-wife", "ex husband", "ex-husband",
    ))
    property_context = _has_any(q, (
        "my gold", "my jewellery", "my jewelry", "my ornaments",
        "my documents", "my property papers", "my house papers",
        "my locker", "gold", "jewellery", "jewelry", "ornaments",
    ))
    taking_or_withholding = _has_any(q, (
        "took", "taken", "kept", "keeping", "not returning",
        "not giving back", "refusing to return", "withholding",
        "left house", "left home", "left me",
    ))
    violence_context = _has_any(q, (
        "slapped", "hit", "beat", "beating", "threat", "threatened",
        "threatening", "locked", "forced sex", "without consent",
    ))
    return spouse_context and property_context and taking_or_withholding and not violence_context


def _is_wife_as_aggressor_sexual_coercion(q: str) -> bool:
    return _has_any(q, (
        "forces sex", "forcing sex", "force sex", "forced sex", "sex without consent",
        "sexual assault", "sexually assaulted me", "sexually assaulting me",
        "assaulted me sexually",
    ))


def _is_spouse_civil_property_or_maintenance_issue(q: str) -> bool:
    if _is_wife_as_aggressor_issue(q):
        return False
    spouse_context = _has_any(q, (
        "my wife", "my husband", "spouse", "husband", "wife",
        "ex husband", "ex-husband", "ex wife", "ex-wife",
    ))
    civil_context = _has_any(q, (
        "maintenance", "alimony", "share in my property", "share in my house",
        "share in property", "share in house", "property share", "house share",
        "during divorce", "after divorce", "divorce case", "divorce notice",
        "matrimonial property", "family court notice",
    ))
    alimony_context = _has_any(q, ("alimony", "maintenance")) and _has_any(q, (
        "after divorce", "during divorce", "divorce case", "divorce",
        "family court", "working before marriage", "was working",
        "i was working", "i am working", "earning",
    ))
    active_deprivation = _has_any(q, (
        "slapped me", "hit me", "beat me", "threatens me", "threatened me",
        "threw me out", "kicked me out", "locked me out", "not allowing me entry",
        "took my", "stole my", "sold my", "transferred my",
    ))
    return ((spouse_context and civil_context) or alimony_context) and not active_deprivation


def _is_spousal_economic_support_issue(q: str) -> bool:
    spouse_context = _has_any(q, ("husband", "wife", "spouse"))
    support_context = _has_any(q, (
        "household expenses", "stopped paying", "not paying",
        "not giving money", "no money", "maintenance", "monetary relief",
        "economic abuse", "salary", "groceries", "breadwinner",
        "separation", "separated", "left me",
    ))
    property_only = _has_any(q, (
        "share in my property", "share in my house", "property share",
        "house share", "title deed", "joint ownership",
    )) and not _has_any(q, (
        "household expenses", "stopped paying", "not paying",
        "not giving money", "no money", "monetary relief",
        "economic abuse", "groceries",
    ))
    return spouse_context and support_context and not property_only


def _is_work_injury(q: str) -> bool:
    if _is_silicosis_quarry_issue(q):
        return False
    environment_damage_context = _has_any(q, (
        "pollution", "polluting", "smoke", "factory smoke", "effluent",
        "chemical water", "air pollution", "water pollution", "ngt",
        "pollution control", "house wall", "wall damaged", "crop damaged",
    ))
    worker_harm_context = _has_any(q, (
        "worker", "labour", "labor", "employee", "contractor", "mukadam",
        "injury", "injured", "accident", "fell", "fall", "fracture",
        "death", "died", "dead", "killed", "hospital", "medical",
        "lost hand", "lost arm", "amputation", "hand cut", "hand crushed",
        "silicosis",
    ))
    if environment_damage_context and not worker_harm_context:
        return False
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
        "fracture", "death", "died", "dead", "killed", "compensation",
        "insurance", "lost hand", "lost arm", "amputation", "hand cut",
        "hand crushed",
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


def _is_silicosis_quarry_issue(q: str) -> bool:
    disease = _has_any(q, (
        "silicosis", "silica", "lungs gone", "lung disease", "dust disease",
        "stone dust", "quarry dust",
    ))
    quarry = _has_any(q, (
        "quarry", "stone quarry", "mine", "mining", "crusher", "stone cutting",
        "sandstone", "rajasthan",
    ))
    harm = _has_any(q, (
        "cough", "breathing", "breath", "lungs", "died", "death", "dead",
        "medical", "doctor", "compensation", "legal", "is this legal",
    ))
    return disease and quarry and harm


def _is_wage_waiver_language_issue(q: str) -> bool:
    wage_context = _has_any(q, ("wage", "wages", "salary", "dues", "payment"))
    waiver_context = _has_any(q, (
        "give up wages", "waive wages", "waiver", "signed paper",
        "signed document", "signed form", "relinquish",
    ))
    language_or_consent = _has_any(q, (
        "dont read", "don't read", "did not read", "cannot read", "cant read",
        "can't read", "english", "kannada", "language", "understand",
        "pressure", "forced", "misrepresentation",
    ))
    return wage_context and waiver_context and language_or_consent


def _is_property_specific_performance_issue(q: str) -> bool:
    performance_context = _has_any(q, (
        "specific performance", "enforce sale agreement", "enforce agreement",
        "seller backing out", "seller backed out", "backing out",
    ))
    property_context = _has_any(q, (
        "land", "plot", "flat", "house", "property", "sale agreement",
        "purchase deal", "agreement to sell", "advance paid",
    ))
    transfer_done_context = _has_any(q, (
        "registered sale deed already", "sale deed registered", "registration refused",
        "sub registrar refused", "document not registered",
    ))
    return performance_context and property_context and not transfer_done_context


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


def _is_copyright_platform_takedown_issue(q: str) -> bool:
    leak_context = _has_any(q, (
        "leak", "leaked", "repost", "reposted", "re-uploaded", "reuploaded",
        "without permission", "without credit", "used my", "copied my",
        "stolen content", "used my reel", "copied my reel", "reposted my reel",
    ))
    creative_asset_context = _has_any(q, (
        "my own", "original", "my song", "my video", "my videos",
        "own song", "own original", "creator", "upload", "paid video",
        "paid content", "subscription content", "creator content",
        "my content", "review video", "cover video", "lyrics", "music",
        "my reel", "our reel", "reel i made", "reel made by me",
    ))
    explicit_copyright_context = _has_any(q, (
        "copyright", "copyright claim", "copyright complaint", "strike", "struck",
        "takedown", "take down", "counter notice", "counter-notice",
    ))
    copyright_context = explicit_copyright_context or (
        leak_context and creative_asset_context
    )
    platform_context = _has_any(q, (
        "youtube", "instagram", "facebook", "telegram", "platform", "channel",
        "video", "song", "music", "reel", "influencer", "post", "views",
    ))
    creator_context = creative_asset_context or (
        explicit_copyright_context
        and _has_any(q, ("video", "song", "music", "reel", "influencer"))
    )
    return copyright_context and platform_context and creator_context


def _is_survivor_sexual_offence(q: str) -> bool:
    survivor_bail_context = (
        _has_any(q, ("oppose bail", "oppose anticipatory bail", "cancel bail", "bail of accused", "accused bail"))
        and _has_any(q, ("survivor", "victim", "complainant", "my sister", "my daughter", "my wife", "rape survivor"))
    )
    if survivor_bail_context:
        return True
    accused_context = _has_any(q, (
        "false rape", "rape case against me", "accused of rape", "bail in rape",
        "case against me", "case filed against me", "filed against me",
        "pocso case against me", "filed a pocso case against me",
        "pocso on me", "pocso against me", "fir against me",
        "accused of", "i am accused", "complaint against me",
        "charged with rape", "falsely accused",
    ))
    accused_context = accused_context or (
        _has_any(q, ("anticipatory bail", "regular bail", "pocso", "sexual assault", "rape", "molest"))
        and _has_any(q, ("against me", "on me", "i am accused", "accused of", "my bail", "defend", "employee filed", "filed against"))
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
    survivor_context = _has_any(q, ("victim", "survivor", "my sister", "my daughter", "my wife", "my girlfriend"))
    sexual_context = _has_any(q, ("rape", "molest", "sexual assault", "pocso"))
    return survivor_context and sexual_context


def _is_workplace_sexual_harassment(q: str) -> bool:
    if _has_any(q, _WORKPLACE_SEXUAL_HARASSMENT_WORDS):
        return True
    hr_harassment_retaliation = (
        _has_any(q, ("complained", "complaint", "reported", "report"))
        and _has_any(q, ("harassment", "harass", "sexual"))
        and _has_any(q, ("hr", "manager", "boss", "reporting manager", "employer"))
        and _has_any(q, ("pip", "bad rating", "performance improvement", "retaliation", "warning", "rating"))
        and _has_any(q, (
            "posh", "sexual harassment", "sexual", "icc", "internal committee",
            "local committee", "touch", "touched", "late night", "alone",
        ))
    )
    if hr_harassment_retaliation:
        return True
    retaliation_context = _has_any(q, ("retaliation", "reporting manager", "bad rating", "pip", "performance improvement")) and _has_any(q, (
        "posh", "sexual harassment", "icc", "internal committee", "local committee",
        "harassment complaint under posh", "complained about sexual harassment",
        "complained to icc", "complained to internal committee",
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
        "touch", "touched", "stalking", "sexual", "alone",
        "late night", "dirty messages", "dirty message", "sexual message",
        "promotion favour",
    )) or romantic_date_context or emoji_context
    dinner_favour_context = _has_any(q, ("dinner", "date")) and _has_any(q, (
        "promotion", "favour", "favor", "complaint", "uncomfortable",
    ))
    if workplace_context and dinner_favour_context:
        return True
    return workplace_context and harassment_context


def _is_civil_registration_record_issue(q: str) -> bool:
    if _has_any(q, ("school", "admission", "rte", "student", "child")) and _has_any(q, (
        "denied", "not taking", "refusing", "refused", "passed test",
        "admission exam", "selection list",
    )):
        return False
    registration_context = _has_any(q, (
        "birth certificate", "birth registration", "death certificate",
        "death registration", "born at home", "home birth",
    ))
    authority_context = _has_any(q, (
        "panchayat", "municipal", "registrar", "secretary", "hospital",
        "not giving",
        "refused", "pending", "delayed", "apply", "application",
        "register", "registration", "give certificate", "issue certificate",
        "certificate nahi", "certificate not", "wrong name", "name wrong",
        "cannot correct", "can't correct", "correction", "correct it",
    ))
    return registration_context and authority_context


def _is_ration_card_pds_issue(q: str) -> bool:
    ration_office_context = re.search(r"\bration\s+office\b", q) is not None
    ration_context = ration_office_context or _has_any(q, (
        "ration card", "ration shop", "ration dealer",
        "pds", "fair price shop", "fair price", "family card",
        "household card", "bpl ration", "bpl card", "foodgrain",
        "foodgrains", "food grains", "dealer not giving ration",
        "no rice", "subsidised grain", "subsidized grain",
    ))
    deletion_or_record_context = _has_any(q, (
        "deleted", "removed", "cut", "cancelled", "canceled",
        "cancelled in system", "name cancelled", "name canceled",
        "name cut", "name removed", "name deleted", "mother deleted",
        "mother name", "maa name", "restore", "records", "order copy",
        "no order", "without notice", "no notice", "written notice",
        "written reason",
    ))
    grain_denial_context = _has_any(q, (
        "grain", "wheat", "rice", "foodgrain", "food grains", "ration",
    ))
    biometric_food_denial = (
        _has_any(q, ("dealer", "ration dealer", "fair price", "fair price shop"))
        and _has_any(q, (
            "biometric", "fingerprint", "thumb", "authentication failed",
            "authentication fail", "pos machine", "machine", "ekyc", "e-kyc",
            "not matching", "mismatch", "server failed", "machine not working",
        ))
        and grain_denial_context
    )
    dealer_record_denial = (
        (_has_any(q, ("dealer", "ration dealer", "fair price", "fair price shop")) or ration_office_context)
        and (deletion_or_record_context or grain_denial_context)
    )
    return ration_context or biometric_food_denial or dealer_record_denial


def _is_legal_aid_eligibility_issue(q: str) -> bool:
    if _is_family_safety_issue(q):
        return False
    legal_aid_context = _has_any(q, (
        "free legal aid", "legal aid eligibility", "legal aid",
        "legal services", "free lawyer", "slsa", "nalsa",
        "cannot afford advocate", "can't afford advocate", "cant afford advocate",
        "cannot afford lawyer", "can't afford lawyer", "cant afford lawyer",
    )) or (
        "dlsa" in q and _has_any(q, (
            "apply", "eligib", "free", "legal", "aid", "lawyer",
            "how to complain", "how complain",
        ))
    )
    if not legal_aid_context:
        return False
    ration_grievance_context = _has_any(q, (
        "ration card cancelled", "ration card canceled", "ration cancelled",
        "ration card not working", "ration shop", "pds", "no rice",
        "dealer not giving ration", "foodgrain", "foodgrains", "food grains",
    ))
    return not ration_grievance_context


def _is_digital_device_police_seizure(q: str) -> bool:
    if _is_arrest_information_safeguard(q) or _is_arrest_production_delay(q):
        return False
    if _has_any(q, ("case closed", "after case closed", "not released", "return my phone", "release my phone")):
        return False
    phone_is_only_contact_evidence = _has_any(q, (
        "phone number", "phone numbers", "mobile number", "mobile numbers",
        "contact number", "contact numbers",
    )) and not _has_any(q, (
        "phone seized", "phone was seized", "phone taken", "took my phone",
        "mobile seized", "mobile was seized", "mobile taken", "took my mobile",
        "return my phone", "release my phone", "device seized", "device taken",
    ))
    if phone_is_only_contact_evidence:
        return False
    device_context = _has_any(q, (
        "laptop", "computer", "hard disk", "pendrive", "pen drive", "device",
        "server", "company laptop", "electronic record", "phone seized",
        "phone was seized", "phone taken", "took my phone", "mobile seized",
        "mobile was seized", "mobile taken", "took my mobile", "my phone",
        "mobile phone",
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
    if _has_any(q, ("498a", "498-a")) and _has_any(q, (
        "filed", "case", "fir", "defend", "bail", "against",
    )):
        return False
    if _is_mgnrega_job_card_or_wage_issue(q):
        return False
    senior_welfare_context = _has_any(q, (
        "old age pension", "vridha pension", "pension status",
        "pension not", "pension stopped", "aadhaar", "ration",
        "scheme", "beneficiary", "widow pension",
    ))
    family_or_maintenance_context = _has_any(q, (
        "son", "daughter", "daughter in law", "daughter-in-law",
        "bahu",
        "children", "brother", "grandson", "family", "maintenance",
        "not taking care", "stopped giving", "food", "medical",
        "support", "supporting", "medical expenses", "threw",
        "thrown out", "pushed out", "pushed me out", "forced out",
        "evict", "homeless", "not allowed", "not allowing", "locked",
        "own house", "own kitchen", "gift", "gifted", "transfer",
        "property", "flat", "house", "land", "gold", "ornaments",
        "jewellery", "jewelry", "passbook", "atm card", "not giving money",
        "medicine money", "monthly support", "left me alone", "leave house",
        "changed lock", "cannot stay", "sleep outside", "not letting",
        "medicine", "bank passbook", "from my savings",
        "room", "bathroom", "self acquired", "self-acquired", "bought by me",
        "refusing to maintain", "maintain her", "maintain him",
    ))
    if senior_welfare_context and not family_or_maintenance_context:
        return False
    tribunal_enforcement = (
        _has_any(q, ("maintenance tribunal", "senior citizen tribunal", "tribunal ordered", "tribunal order"))
        and _has_any(q, ("son", "daughter", "children", "parent", "father", "mother", "relative", "senior citizen", "ordered"))
        and _has_any(q, (
            "pay", "maintenance", "stopped paying", "not paying", "enforce",
            "enforcement", "default", "missed payment", "order not followed",
        ))
    )
    if tribunal_enforcement:
        return True
    if _has_any(q, ("son threw", "daughter threw", "children not taking care")):
        return True
    if _has_any(q, (
        "senior citizen", "senior mother", "senior father", "old age", "elderly", "old mother", "old father",
        "old parent", "old parents", "father is old", "mother is old",
        "maa", "widow",
    )) and family_or_maintenance_context:
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
            "throw me out", "throw him out", "throw her out", "thrown out",
            "pushed me out", "pushed out", "leave house", "evict",
            "refuses food", "refusing to maintain", "maintain her", "maintain him",
            "sleep outside", "bahu", "medicine",
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
            "pushed me out", "pushed out", "leave house",
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
            "claim maintenance", "file maintenance", "monthly maintenance",
            "not giving food", "not giving medicine", "not giving medical",
            "medical expenses", "not supporting", "refusing to support",
            "not maintaining", "support old mother", "support old father",
            "no food", "refuses food", "monthly support", "left me alone",
            "refusing to maintain", "maintain her", "maintain him",
            "medicine",
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
        "abandoned", "abandon", "left me", "left alone", "not maintaining",
        "refusing to support", "no support", "pushed me out", "pushed out",
        "thrown out", "flat bought", "bought by me", "passbook", "atm card",
        "not giving money", "medicine money", "no food", "monthly support",
        "room", "bathroom", "leave house", "refusing to maintain",
        "changed lock", "cannot stay", "sleep outside", "medicine",
        "bank passbook", "from my savings",
    ))
    return senior_age and neglect_or_shelter


def _is_senior_maintenance_order_enforcement(q: str) -> bool:
    tribunal_context = _has_any(q, (
        "maintenance tribunal",
        "senior citizen tribunal",
        "tribunal ordered",
        "tribunal order",
        "tribunal has ordered",
        "ordered son",
        "ordered daughter",
        "order against son",
        "order against daughter",
    ))
    family_context = _has_any(q, (
        "son", "daughter", "children", "child", "parent", "father",
        "mother", "relative", "senior citizen", "elderly", "old age",
    ))
    enforcement_context = _has_any(q, (
        "pay",
        "maintenance",
        "stopped paying",
        "not paying",
        "refusing to pay",
        "arrears",
        "default",
        "missed payment",
        "order not followed",
        "enforce",
        "enforcement",
        "kaise",
    ))
    return tribunal_context and family_context and enforcement_context


def _is_civil_procedure_issue(q: str) -> bool:
    if _has_any(q, ("rti", "right to information", "pio", "public information officer", "information commission")):
        return False
    if _has_any(q, ("consumer", "e-daakhil", "edaakhil", "district consumer", "consumer complaint")):
        return False
    execution_context = _has_any(q, (
        "judgment debtor", "judgement debtor", "money decree", "decree amount",
        "decree money", "decree execution", "execution of decree",
        "attach property", "attachment of property", "attach his property",
        "attach her property",
    ))
    execution_action = _has_any(q, (
        "not paying", "not paid", "refusing to pay", "stopped paying",
        "execute", "execution", "attach", "attachment", "property",
        "order 21", "order xxi",
    ))
    if execution_context and execution_action:
        return True
    if _has_any(q, _CIVIL_PROCEDURE_WORDS):
        return True
    civil_forum = _has_any(q, ("cpc", "civil court", "district court", "high court"))
    procedural_step = _has_any(q, ("execution", "decree", "appeal", "petition", "revision", "transfer"))
    if civil_forum and procedural_step:
        return True
    return _has_any(q, ("decree holder", "substantial question")) and _has_any(q, ("file", "procedure", "appeal", "execution"))


def _is_criminal_quashing_issue(q: str) -> bool:
    quashing_context = _has_any(q, (
        "quash", "quashing", "482 crpc", "crpc 482", "section 482",
        "sec 482", "482 petition", "bnss 528", "section 528", "sec 528",
    ))
    criminal_case_context = _has_any(q, (
        "fir", "criminal case", "chargesheet", "charge sheet", "summons",
        "accused", "police case", "criminal proceeding", "criminal proceedings",
        "criminal complaint", "police report", "charge-sheet", "quashing petition",
        "420 case", "498a", "498-a", "police calling", "case on me",
        "case against me", "case against my brother", "filed against me",
        "420 fir", "cheating 420 fir", "420 complaint", "420 police complaint", "cheating complaint",
        "fake cheating complaint", "cyber cheating case",
    ))
    false_case_context = _has_any(q, (
        "false fir", "false case", "false 420", "false 498a",
        "false 498-a", "fake case", "false criminal case",
        "false theft fir", "false theft case", "fake theft fir",
        "fake theft case", "wrong theft fir",
        "false complaint", "made false 420 case", "filed false",
        "wife filed false", "neighbour made false", "neighbor made false",
        "fake 420", "fake fir", "fake cheating", "false cheating",
        "fake complaint", "filed fake", "put false cheating",
        "old business debt", "property payment fight",
        "refund fight", "refund dispute",
    ))
    accused_money_complaint = (
        _has_any(q, ("420 complaint", "420 police complaint", "420 case", "cheating complaint", "cheating case"))
        and (
            _has_any(q, ("police calling", "police called", "summons", "against me", "on me"))
            or _has_any(q, ("what to carry to station", "called to station", "go to station"))
        )
        and _has_any(q, ("money dispute", "cheque money", "business debt", "loan money", "personal loan dispute", "repay", "payment fight", "refund fight", "refund dispute", "customer put"))
    )
    return (quashing_context and criminal_case_context) or (false_case_context and criminal_case_context) or accused_money_complaint


def _is_criminal_compounding_issue(q: str) -> bool:
    if _is_lok_adalat_compounding_issue(q):
        return False
    return _has_any(q, (
        "section 320", "sec 320", "320 crpc", "crpc 320",
        "compoundable offence", "compoundable offences", "compound offence",
        "compound criminal", "withdraw criminal complaint",
        "withdraw complaint under section 320",
    ))


def _is_lok_adalat_compounding_issue(q: str) -> bool:
    lok_context = _has_any(q, ("lok adalat", "lokadalat", "national lok adalat"))
    compound_context = _has_any(q, (
        "compoundable offence", "compoundable offences", "compound offence",
        "compounding", "compound criminal", "criminal compromise",
        "settle criminal", "referred to lok adalat", "which disputes",
    ))
    return lok_context and compound_context


def _is_motor_accident_claim_issue(q: str) -> bool:
    if _has_any(q, ("zomato", "swiggy", "delivery partner", "rider", "gig worker")) and _has_any(q, ("no insurance from company", "company", "platform")):
        return False
    accident_context = _has_any(q, (
        "hit a pedestrian", "hit pedestrian", "pedestrian",
        "third party insurance", "third-party insurance", "third party only",
        "mact", "motor accident", "vehicle accident", "road accident",
        "truck accident", "bike accident", "car accident", "bike hit",
        "car hit", "truck hit", "vehicle hit",
    ))
    claim_context = _has_any(q, (
        "claiming", "claim", "compensation", "demanding", "8 lakh", "lakh",
        "insurance company not paying", "insurer denying", "hospital bill",
        "vehicle owner", "not paying claim",
    ))
    driving_context = _has_any(q, ("driving", "vehicle", "car", "bike", "auto"))
    return accident_context and (claim_context or driving_context)


def _red_flags(q: str) -> list[str]:
    flags: list[str] = []
    if _has_any(q, (
        "rape", "child", "minor", "molest", "pocso", "acid", "knife",
        "kill", "suicide", "mob", "violence", "beat", "beaten", "witch", "daayan",
        "dayan", "black magic", "hostage",
    )):
        flags.append("Immediate safety risk or serious offence")
    if _has_any(q, (
        "arrested", "arrest", "detained", "in jail", "custody", "bail",
        "remand", "lockup", "not produced before magistrate",
        "magistrate production", "produced before magistrate",
    )):
        flags.append("Liberty/custody issue")
    if _has_any(q, ("lost money", "upi", "otp", "credit card", "bank account", "account frozen", "account freeze", "account is frozen", "lien marked")):
        flags.append("Time-sensitive money trail")
    if _has_any(q, (
        "threw me out", "homeless", "not giving food", "beating", "locked",
        "hit me", "hitting me", "unsafe", "threatens", "threatened",
        "threatening", "harassing contacts", "harassing my contacts",
        "loan app is harassing",
    )):
        flags.append("Shelter or personal safety concern")
    return flags


def _criminal_regime(q: str) -> str:
    if _mentions_before_july_2024(q):
        return "legacy_ipc_crpc_evidence_for_pre_2024_incident"
    if _mentions_after_july_2024(q):
        return "current_bns_bnss_bsa_for_post_2024_incident"
    years = _extract_incident_years(q)
    if len(years) > 1 and any(y < 2024 for y in years) and any(y > 2024 for y in years):
        return "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
    year = years[0] if years else None
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


def _extract_incident_years(q: str) -> list[int]:
    years: list[int] = []
    for match in re.finditer(r"\b(20\d{2}|19\d{2})\b", q):
        if _looks_like_statute_year(q, match.start(), match.end()):
            continue
        years.append(int(match.group(1)))
    return years


def _looks_like_statute_year(q: str, start: int, end: int) -> bool:
    before = q[max(0, start - 36):start].lower()
    after = q[end:end + 28].lower()
    statute_before = (
        "bnss", "bns", "bsa", "crpc", "ipc", "ndps", "pocso",
        "evidence act", "information technology act", "it act",
        "code on wages", "senior citizens act", "juvenile justice act",
        "act", "code", "sanhita", "adhiniyam",
    )
    if any(term in before for term in statute_before):
        incident_markers = ("incident", "offence", "offense", "crime", "fir", "arrest", "arrested", "case from", "happened", "occurred")
        if not any(term in before for term in incident_markers):
            return True
    if re.match(r"\s*(act|code|section|sec|s\.|sanhita|adhiniyam)\b", after):
        return True
    return False


def _mentions_before_july_2024(q: str) -> bool:
    return (
        "before july 2024" in q
        or "before 1 july 2024" in q
        or "before 01 july 2024" in q
        or "prior to 1 july 2024" in q
        or "prior to 01 july 2024" in q
        or "until 1 july 2024" in q
        or "until 01 july 2024" in q
        or "till 1 july 2024" in q
        or "till 01 july 2024" in q
        or "pre july 2024" in q
        or "pre-july 2024" in q
        or "june 2024" in q
        or "jun 2024" in q
        or "may 2024" in q
        or re.search(r"\b(?:before|pre|prior to|until|till)\s+0?1[-/]0?7[-/]2024\b", q) is not None
        or re.search(r"\b(?:before|pre|prior to|until|till)\s+2024[-/]0?7[-/]0?1\b", q) is not None
        or re.search(r"\b(?:pre[-\s]?|prior to\s+)?july\s+1(?:st)?\s*,?\s*2024\b", q) is not None and _has_any(q, ("before", "pre", "prior to", "until", "till"))
        or re.search(r"\b30(?:st|nd|rd|th)?\s+june\s+2024\b", q) is not None
        or re.search(r"\bjune\s+30(?:st|nd|rd|th)?\s*,?\s*2024\b", q) is not None
        or re.search(r"\b2024[-/]0?6(?:[-/]30)?\b", q) is not None
        or re.search(r"\b30[-/]0?6[-/]2024\b", q) is not None
    )


def _mentions_after_july_2024(q: str) -> bool:
    return (
        "after july 2024" in q
        or "after 1 july 2024" in q
        or "after 01 july 2024" in q
        or "from 1 july 2024" in q
        or "from 01 july 2024" in q
        or "on 1 july 2024" in q
        or "on 01 july 2024" in q
        or "1 july 2024" in q
        or "01 july 2024" in q
        or "2 july 2024" in q
        or "02 july 2024" in q
        or "july 2024" in q
        or "august 2024" in q
        or "september 2024" in q
        or "october 2024" in q
        or "november 2024" in q
        or "december 2024" in q
        or re.search(r"\b(?:[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+july\s+2024\b", q) is not None
        or re.search(r"\bjuly\s+(?:[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s*,?\s*2024\b", q) is not None
        or re.search(r"\b2024[-/]0?7(?:[-/](?:0?[1-9]|[12]\d|3[01]))?\b", q) is not None
        or re.search(r"\b(?:0?[1-9]|[12]\d|3[01])[-/]0?7[-/]2024\b", q) is not None
    )


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
            "Identify the exact scheme or ID record causing the denial, decide which record needs correction, and collect the rejection/mismatch proof.",
            "File a written correction or grievance with the scheme office, portal, CSC, or Aadhaar centre as relevant.",
            "If a scholarship, admission, exam, or benefit deadline is close, preserve proof of the deadline and ask for urgent written status before the last date.",
            "If officials do not give reasons, use RTI or DLSA help to get status and the rule relied on.",
        ],
        documents=["Aadhaar/ID proof", "scheme application ID", "rejection or mismatch screenshot", "certificate/income/caste papers", "bank/passbook proof"],
        portals=["scheme portal where available", "uidai.gov.in for Aadhaar services", "rtionline.gov.in for central authorities"],
        escalation=["district social welfare office", "scheme appellate/grievance authority", "District Legal Services Authority"],
        cautions=["Benefit cases are state- and scheme-specific; exact scheme name and rejection reason matter."],
    )


def _pan_aadhaar_identity_pack() -> ActionPack:
    return ActionPack(
        id="pan_aadhaar_identity",
        title="PAN/Aadhaar correction path",
        next_steps=[
            "Identify whether the mismatch is name, date of birth, gender, or mobile/authentication status.",
            "Correct the wrong record at the PAN/income-tax side or Aadhaar/UIDAI side before retrying linking.",
            "Keep screenshots and ask for a written rejection reason if the portal or office refuses correction.",
        ],
        documents=["PAN card/e-PAN", "Aadhaar copy", "portal error screenshot", "name/DOB proof", "mobile/email used", "complaint acknowledgement"],
        portals=["incometax.gov.in", "uidai.gov.in", "public grievance/RTI route where reasons are withheld"],
        escalation=["Income Tax/PAN grievance", "UIDAI grievance or Aadhaar Seva Kendra", "District Legal Services Authority"],
        cautions=["Do not treat a PAN/Aadhaar mismatch as a caste or welfare-entitlement answer unless a specific scheme denial is also present."],
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


def _personal_money_recovery_pack() -> ActionPack:
    return ActionPack(
        id="personal_money_recovery",
        title="Personal loan recovery path",
        next_steps=[
            "Collect the money-transfer proof, messages, repayment promise, and any written acknowledgement.",
            "Send a written demand or legal notice after checking the due date and limitation position.",
            "Use civil recovery/mediation first; use police only for clear cheating, forgery, threats, or violence facts.",
        ],
        documents=["bank/UPI proof", "cash receipt if any", "messages/emails", "loan note or acknowledgement", "repayment timeline", "cheque and return memo if any"],
        escalation=["civil court / mediation centre", "District Legal Services Authority", "local lawyer/legal-aid desk", "police only for cheating/forgery/threat facts"],
        cautions=["A family or friendly loan is not automatically a police case; cheque-bounce law needs an actual dishonoured cheque and notice facts."],
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


def _municipal_shop_sealing_pack() -> ActionPack:
    return ActionPack(
        id="municipal_shop_sealing",
        title="Municipal sealing response path",
        next_steps=[
            "Get the sealing order, show-cause notice, inspection report, and the officer/ward details in writing.",
            "Collect shop licence, trade registration, lease/ownership papers, tax/fee receipts, photos, and any hearing notice.",
            "Use the municipal appellate/review route named in the order; use RTI or DLSA help if the file or reasons are not given.",
        ],
        documents=["sealing order", "show-cause notice", "shop/trade licence", "lease/ownership proof", "fee/tax receipts", "photos/videos", "inspection report"],
        escalation=["municipal ward/licensing office", "Municipal Commissioner/appellate authority", "local lawyer/DLSA", "court route only after reading the order"],
        cautions=["Municipal sealing powers and appeals are state/city-specific; the written order controls the next forum and deadline."],
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
            "If an admission, fee-payment, or scholarship deadline is close, preserve proof of the deadline and ask for urgent written status before the last date.",
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


def _minor_mineral_gram_sabha_pack() -> ActionPack:
    return ActionPack(
        id="minor_mineral_gram_sabha",
        title="Minor mineral Gram Sabha path",
        next_steps=[
            "Collect the mining or quarry lease/NOC file, Gram Sabha or Palli Sabha notice and minutes, and mineral-department approval record.",
            "Verify Scheduled Area status and whether the PESA Gram Sabha recommendation route applies before treating the lease as complete.",
            "Use the Collector, mining department, tribal welfare authority, DLSA, or court/NGT route depending on which approval is missing.",
        ],
        documents=["lease/NOC file", "Gram Sabha/Palli Sabha notice and minutes", "mineral-department approval", "site map", "forest or pollution clearance papers", "Scheduled Area proof"],
        escalation=["Collector / District Magistrate", "mining department", "Gram Sabha / Panchayat channel", "tribal welfare authority", "DLSA"],
        cautions=["Do not add RFCTLARR rehabilitation or compensation framing unless land acquisition, displacement, compensation, or R&R facts are present."],
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


def _bank_account_freeze_pack() -> ActionPack:
    return ActionPack(
        id="bank_account_freeze",
        title="Bank account freeze path",
        next_steps=[
            "Ask the bank in writing for the exact freeze/lien/KYC reason, authority, and complaint number.",
            "Collect the statement, freeze message, KYC proof, branch reply, and any police/cyber/court reference.",
            "Escalate through bank grievance and RBI Ombudsman if it is a bank-service issue; use legal aid/court/police route if it is a legal hold.",
        ],
        documents=["bank statement", "freeze/lien message", "KYC proof", "complaint number", "branch reply", "legal hold/order reference if any", "transaction IDs if fraud is alleged"],
        portals=["bank grievance portal", "cms.rbi.org.in", "cybercrime.gov.in only for fraud/cyber lien facts"],
        escalation=["bank branch/grievance officer", "RBI Ombudsman", "cyber police/local police where a legal hold is stated", "DLSA"],
        cautions=["Do not try to bypass or route money around a legal hold; first get the written reason and authority."],
    )


def _loan_app_harassment_pack() -> ActionPack:
    return ActionPack(
        id="loan_app_harassment",
        title="Loan-app harassment path",
        next_steps=[
            "Preserve call logs, WhatsApp/SMS screenshots, messages sent to contacts, app permissions, loan agreement, and repayment proof.",
            "File a written grievance with the lender/app and ask for the regulated entity/NBFC details.",
            "Escalate to RBI Ombudsman where covered; use cyber police/local police if threats, extortion, obscene messages, or contact-data abuse continue.",
        ],
        documents=["loan app/lender name", "loan agreement", "repayment proof", "call logs", "contact messages", "screenshots", "app permissions", "complaint number"],
        portals=["lender grievance portal", "cms.rbi.org.in", "cybercrime.gov.in for threats/contact-data misuse"],
        escalation=["lender grievance officer", "RBI Ombudsman", "cyber police/local police", "DLSA"],
        cautions=["Keep repayment/default facts separate from illegal recovery harassment; do not delete the app or messages before preserving evidence."],
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


def _self_harm_crisis_pack() -> ActionPack:
    return ActionPack(
        id="self_harm_crisis",
        title="Immediate safety path",
        next_steps=[
            "If you may hurt yourself, call local emergency services or go to the nearest hospital now.",
            "Contact a trusted person and stay with them while you use a crisis helpline.",
            "Use the legal route only after immediate safety is handled.",
        ],
        documents=["current location", "trusted contact", "medical emergency details", "violence or harassment facts for later legal follow-up"],
        portals=india_self_harm_portal_labels(),
        escalation=["local emergency services", "nearest hospital", "trusted person", "District Legal Services Authority after immediate safety"],
        cautions=["Do not wait for a legal answer if you may harm yourself."],
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
            "If you are unsafe or thrown out, prioritize emergency help, shelter, a trusted person, and a safe phone copy of evidence.",
            "Write a dated incident and residence timeline; keep medical records, photos, messages, expense proof, and witness names.",
            "Use the Protection Officer/Magistrate/DLSA route for protection, residence, monetary relief, custody, or police escalation depending on facts.",
        ],
        documents=["marriage proof", "ID/address proof", "medical records", "messages/photos", "income details", "child documents"],
        escalation=["Protection Officer", "One Stop Centre / women helpline", "Magistrate court", "Family Court", "District Legal Services Authority", "police for immediate danger"],
        cautions=["Do not wait for a perfect legal answer if there is immediate violence."],
    )


def _family_notice_response_pack() -> ActionPack:
    return ActionPack(
        id="family_notice_response",
        title="DV/family notice response path",
        next_steps=[
            "Read the notice/application and write the hearing date, court, reliefs claimed, and response deadline.",
            "Prepare a fact-wise reply with documents instead of ignoring the notice or sending threats.",
            "Use DLSA or a family-law lawyer to decide whether reply, settlement, mediation, appeal, or linked criminal-defence steps fit.",
        ],
        documents=["notice/application copy", "marriage/residence proof", "income and payment records", "messages/photos", "medical records if relevant", "prior complaint or mediation papers"],
        escalation=["Magistrate court named in the notice", "Family Court if linked", "District Legal Services Authority", "lawyer/legal-aid desk"],
        cautions=["Do not assume a case is false just because you disagree; answer each allegation with dates and proof."],
    )


def _spousal_property_return_pack() -> ActionPack:
    return ActionPack(
        id="spousal_property_return",
        title="Spousal property return path",
        next_steps=[
            "Make an item-wise list of what was taken, who owns it, when it was taken, and what proof exists.",
            "Send/record a clear demand for return before choosing civil, family-court, or criminal complaint steps.",
            "Use DLSA or a family-law/civil lawyer to separate ownership/settlement issues from breach-of-trust or theft facts.",
        ],
        documents=["purchase/gift proof", "photos of items", "messages demanding return", "bank/locker records", "marriage/separation timeline", "pending case papers if any"],
        escalation=["District Legal Services Authority", "Family Court where matrimonial proceedings are linked", "civil court", "police/Magistrate only where criminal facts fit"],
        cautions=["Do not start with a criminal label unless entrustment, demand for return, refusal, or theft facts are specific."],
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


def _marriage_misrepresentation_pack() -> ActionPack:
    return ActionPack(
        id="marriage_misrepresentation",
        title="Marriage misrepresentation path",
        next_steps=[
            "Write a timeline of what was stated before marriage, when you discovered the truth, and what proof exists.",
            "Clarify the personal law or Special Marriage Act route before choosing annulment, divorce, maintenance, or counselling.",
            "Use DLSA or a family-law lawyer before sending any notice because limitation, proof, and the remedy choice matter.",
        ],
        documents=["marriage proof", "messages/profile/biodata", "salary/job proof if available", "date you discovered the truth", "children/residence/maintenance details"],
        escalation=["Family Court", "District Legal Services Authority", "family-law lawyer/legal-aid desk"],
        cautions=["A false statement before marriage is fact-sensitive; do not assume every lie automatically cancels the marriage."],
    )


def _pre_marriage_disclosure_pack() -> ActionPack:
    return ActionPack(
        id="pre_marriage_disclosure",
        title="Pre-marriage disclosure path",
        next_steps=[
            "First separate cancellation/safety from legal claims: write down what was disclosed, when you learned it, and whether the marriage has already happened.",
            "Preserve biodata/messages, engagement or wedding-expense records, gift/dowry return records, and any threats or pressure.",
            "Speak to DLSA or a family-law lawyer before sending public accusations or notices, especially where medical privacy is involved.",
        ],
        documents=["messages/biodata", "engagement or wedding records", "gift/dowry/payment records", "date of discovery", "threat or pressure messages if any"],
        escalation=["District Legal Services Authority", "family-law lawyer/legal-aid desk", "Family Court only if matrimonial proceedings become necessary"],
        cautions=["If marriage has not happened, do not frame the issue as divorce or annulment; also do not disclose a person's medical status publicly without legal advice."],
    )


def _writ_constitution_pack() -> ActionPack:
    return ActionPack(
        id="writ_constitution",
        title="Writ remedy path",
        next_steps=[
            "Identify the government authority, written order/refusal, public duty, and date of your representation.",
            "For High Court writs, prepare the order/refusal, representation, proof of delivery, and urgency facts.",
            "Use DLSA or a writ lawyer to check maintainability, alternate remedy, limitation/delay, and the exact relief before filing.",
        ],
        documents=["written order/refusal", "representation/complaint copy", "proof of delivery", "timeline", "ID/address proof", "supporting records"],
        escalation=["High Court writ jurisdiction", "District Legal Services Authority", "lawyer/legal-aid desk"],
        cautions=["A writ is not a generic complaint form; the public duty, authority, right, delay, and alternate remedy matter."],
    )


def _marriage_breakdown_pack() -> ActionPack:
    return ActionPack(
        id="marriage_breakdown",
        title="Marriage breakdown path",
        next_steps=[
            "Do not use pressure or force; first decide whether you want counselling, separation, divorce, maintenance, or another family-court remedy.",
            "Write down the timeline and any linked issues like violence, threats, residence, children, or maintenance.",
            "Speak to DLSA or a family-law lawyer about the personal-law route before filing anything.",
        ],
        documents=["marriage proof", "timeline", "messages", "counselling/medical records if any", "children/residence/maintenance details"],
        escalation=["Family Court", "District Legal Services Authority", "safe counselling/mediation only if voluntary"],
        cautions=["Sex cannot be treated as something to force from a spouse; if there is violence or coercion, treat safety first."],
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


def _tribal_land_transfer_pack() -> ActionPack:
    return ActionPack(
        id="tribal_land_transfer_restoration",
        title="Tribal land-transfer restoration path",
        next_steps=[
            "Collect certified land records, mutation order, sale/transfer deed or mortgage papers, and possession facts.",
            "Verify the state Scheduled Area or tribal-land transfer rule with the Collector/Deputy Commissioner or revenue authority.",
            "Use DLSA or tribal welfare help to prepare a restoration, cancellation, or record-correction request.",
        ],
        documents=["khata/khatian/passbook", "mutation order", "sale/transfer deed", "tribal-status proof", "buyer/transferee details", "possession proof", "complaint/RTI copies"],
        escalation=["Collector / Deputy Commissioner", "revenue restoration authority", "tribal welfare authority", "civil court where title is disputed", "District Legal Services Authority"],
        cautions=["Do not use locks, threats, or self-help eviction; tribal land-transfer remedies are state-specific and document-heavy."],
    )


def _forest_rights_fra_pack() -> ActionPack:
    return ActionPack(
        id="forest_rights_fra",
        title="Forest-rights / FRA claim path",
        next_steps=[
            "Collect the FRA claim, Gram Sabha/FRC resolution, patta/CFR title, and any written refusal or seizure record.",
            "Ask the Gram Sabha/FRC, SDLC, DLC, or Collector for a written decision or reasoned correction.",
            "Use tribal welfare office or DLSA help if officials ignore the FRA papers or forest-produce rights.",
        ],
        documents=["FRA claim form", "Gram Sabha/FRC resolution", "IFR/patta/CFR title", "SDLC/DLC order or refusal", "photos/video", "seizure/cutting notice", "witness names"],
        escalation=["Gram Sabha / Forest Rights Committee", "Sub-Divisional Level Committee", "District Level Committee / Collector", "tribal welfare authority", "District Legal Services Authority"],
        cautions=["Use police channels only for separate violence, threat, illegal detention, or a criminal case; ordinary FRA claim and forest-produce disputes start with FRA institutions."],
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


def _copyright_takedown_pack() -> ActionPack:
    return ActionPack(
        id="copyright_platform_takedown",
        title="Copyright takedown path",
        next_steps=[
            "Preserve the platform copyright strike/takedown notice and claimant details.",
            "Collect original project files, upload date, publication history, and proof of authorship/ownership.",
            "Use the platform counter-notice or appeal first; escalate to a copyright lawyer/DLSA if the channel, income, or rights are affected.",
        ],
        documents=["platform strike notice", "project/source files", "upload/publication proof", "claimant messages", "channel/payment impact proof"],
        portals=["platform copyright appeal/counter-notice page"],
        escalation=["platform copyright desk", "commercial/civil court where needed", "IP lawyer or legal-aid clinic"],
        cautions=["Do not mix copyright with trademark unless the dispute is about a brand/logo or marketplace confusion."],
    )


def _software_license_pack() -> ActionPack:
    return ActionPack(
        id="software_license_notice",
        title="Software licence notice path",
        next_steps=[
            "Preserve the vendor notice, audit report, claimed software name/version, seat count, device/user list, and deadline.",
            "Compare the claimed unlicensed seats with invoices, subscriptions, purchase orders, reseller emails, and install/use records.",
            "Reply through counsel or an authorised company contact; do not admit infringement or offer payment until the licence/audit basis is checked.",
        ],
        documents=["vendor/legal notice", "licence invoices/subscriptions", "seat or device list", "audit screenshots/report", "user assignment records", "settlement demand"],
        escalation=["vendor/licensor notice channel", "IP/commercial lawyer", "commercial/civil court where a suit is filed", "District Legal Services Authority"],
        cautions=["Treat this as copyright/software-licence evidence first; trademark law matters only if brand/logo/passing-off facts are actually raised."],
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


def _prison_mulaqat_pack() -> ActionPack:
    return ActionPack(
        id="prison_mulaqat_access",
        title="Prison mulaqat / interview path",
        next_steps=[
            "Ask the Jail Superintendent in writing for the applicable visit/mulaqat rule and reason for the time or frequency limit.",
            "Keep prisoner details, relationship proof, prior appointment/refusal proof, and any medical or family urgency.",
            "Use DLSA or High Court review if access is arbitrary, discriminatory, or blocks lawyer/family communication without reasons.",
        ],
        documents=["prisoner number", "jail name", "relationship/ID proof", "appointment or refusal proof", "rule/order copy if available"],
        escalation=["prison superintendent", "District Legal Services Authority", "prison visitors board where available", "High Court writ jurisdiction"],
        cautions=["Mulaqat timing and frequency are state-prison-rule heavy; verify the prison/state rule before demanding a specific duration."],
    )


def _prison_records_pack() -> ActionPack:
    return ActionPack(
        id="prison_records_admin",
        title="Prison records / account path",
        next_steps=[
            "Ask the Jail Superintendent or records/accounts office in writing for the specific account, order, nominal-roll, or custody record.",
            "Attach prisoner number, jail name, relationship/authority proof, and any prior application or refusal.",
            "Use DLSA, the court registry, or RTI where records or reasons are withheld.",
        ],
        documents=["prisoner number", "jail name", "relationship/authority proof", "record/order/account requested", "money-order or canteen proof", "prior request/refusal"],
        escalation=["prison superintendent", "jail records/accounts office", "District Legal Services Authority", "RTI Public Information Officer", "court registry for certified orders"],
        cautions=["Prison account and record-copy procedures are state-prison-rule heavy; do not treat them as parole, bail, or generic civil recovery questions."],
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


def _tenancy_pack() -> ActionPack:
    return ActionPack(
        id="tenancy_eviction_nonpayment",
        title="Tenant eviction / rent arrears path",
        next_steps=[
            "Collect the rent agreement, rent ledger, payment receipts, messages, and possession facts.",
            "Send a written legal notice only after checking the agreement term and local rent-control law.",
            "File through the rent authority or civil court route instead of using locks, threats, or self-help eviction.",
        ],
        documents=["rent agreement", "rent receipts", "arrears calculation", "notice/messages", "tenant ID/details", "property ownership papers"],
        escalation=["rent authority or civil court", "District Legal Services Authority", "local lawyer/legal-aid desk"],
        cautions=["Tenant-removal procedure is state-law heavy; state and city change the forum and notice route."],
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


def _drug_safety_pack() -> ActionPack:
    return ActionPack(
        id="drug_safety_complaint",
        title="Drug-possession safety path",
        next_steps=[
            "Prioritize immediate safety and do not handle, destroy, or move suspected contraband yourself.",
            "Write down what you saw, where it is, who is involved, and whether police, threats, or violence are already involved.",
            "Use police, DLSA, or a criminal-lawyer/legal-aid desk to separate a safety report from any family or counselling issue.",
        ],
        documents=["date/place note", "photos/messages if safely available", "substance/location details", "police papers if any", "ID/address proof"],
        escalation=["police station or senior police if unsafe", "District Legal Services Authority", "criminal lawyer/legal-aid desk", "medical or crisis support if substance use creates danger"],
        cautions=["The exact NDPS position depends on the substance, quantity, seizure record, and role of each person; do not guess from the word 'drugs' alone."],
    )


def _drug_treatment_support_pack() -> ActionPack:
    return ActionPack(
        id="drug_treatment_support",
        title="Drug treatment / de-addiction support path",
        next_steps=[
            "Treat this first as a treatment and safety-support issue unless there is contraband, violence, police, seizure, or immediate danger.",
            "Contact a government de-addiction/treatment centre, district hospital, or District Mental Health Programme where available.",
            "If the person is violent, unconscious, overdosing, or unsafe, use emergency medical help or police only for immediate safety.",
        ],
        documents=["age/ID proof", "substance/treatment history if known", "medical records if any", "current safety notes", "state/district"],
        escalation=["government de-addiction/treatment centre", "district hospital", "District Mental Health Programme", "District Legal Services Authority", "emergency services if unsafe"],
        cautions=["Do not frame a treatment-only addiction question as an NDPS possession case unless the facts include possession, seizure, FIR, threat, violence, or immediate danger."],
    )


def _child_safety_pack() -> ActionPack:
    return ActionPack(
        id="child_safety_assault",
        title="Child-safety complaint path",
        next_steps=[
            "Move the child to immediate safety and get medical help if there is injury or ongoing violence.",
            "Preserve injury photos, medical records, messages, and witness names without escalating confrontation at home.",
            "Contact police, Child Welfare Committee/child helpline, DLSA, or a doctor depending on current danger and injury facts.",
        ],
        documents=["child age proof", "injury photos/medical record", "messages/videos if safe", "witness names", "school/doctor details", "prior complaint papers"],
        portals=["1098 child helpline where available"],
        escalation=["police station or senior police", "Child Welfare Committee", "doctor/hospital", "District Legal Services Authority"],
        cautions=["Child safety comes before deciding the family-law forum; urgent harm should not wait for a perfect legal classification."],
    )


__all__ = ["ActionPack", "MatterRoute", "route_matter", "route_matter_trace"]
