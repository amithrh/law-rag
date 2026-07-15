"""Authority-ledger backed answer contracts.

The route tells us the neighborhood. These contracts add the legal doorstep:
variant, controlling source, forum, documents, and the next procedural move.
They are intentionally narrow and only emit cited lines when the retrieved
passages contain a plausible controlling source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from apps.api.matter_router import MatterRoute


@dataclass(frozen=True)
class PassageSpec:
    key: str
    title_terms: tuple[str, ...]
    anchor_terms: tuple[str, ...] = ()
    optional: bool = False


@dataclass(frozen=True)
class CriminalVariantContract:
    id: str
    label: str
    triggers_any: tuple[str, ...]
    required_any: tuple[str, ...]
    required_source_keys_any: tuple[str, ...]
    source_specs: tuple[PassageSpec, ...]
    forum: str
    documents: tuple[str, ...]
    remedy: str
    caution: str


CRIMINAL_VARIANT_CONTRACTS: tuple[CriminalVariantContract, ...] = (
    CriminalVariantContract(
        id="pmla_pre_arrest_bail",
        label="PMLA/ED pre-arrest bail",
        triggers_any=("pmla", "ed raid", "ed summons", "ed notice", "ed case", "enforcement directorate", "ecir"),
        required_any=("anticipatory", "before arrest", "pre arrest", "pre-arrest", "summons", "raid"),
        required_source_keys_any=("pmla",),
        source_specs=(
            PassageSpec("pmla", ("prevention of money laundering", "pmla"), ("/sec-45",), optional=True),
            PassageSpec("anticipatory", ("bharatiya nagarik suraksha",), ("/sec-482",), optional=True),
            PassageSpec("anticipatory_legacy", ("code of criminal procedure",), ("/sec-438",), optional=True),
        ),
        forum="Special PMLA Court, Sessions/High Court bail route as advised from the papers",
        documents=("ED summons/raid panchnama", "ECIR/FIR or predicate-offence papers if available", "arrest notice or grounds if served", "bank/property attachment papers"),
        remedy="prepare a PMLA-specific pre-arrest or bail strategy instead of treating the summons as ordinary anticipatory bail",
        caution="PMLA has a special bail filter, so do not assume ordinary anticipatory-bail rules answer the whole question.",
    ),
    CriminalVariantContract(
        id="anticipatory_bail_successive",
        label="Successive anticipatory-bail application",
        triggers_any=("anticipatory bail rejected", "ab rejected", "bail rejected", "sessions rejected", "same court"),
        required_any=("anticipatory", "before arrest", "pre arrest", "pre-arrest"),
        required_source_keys_any=("anticipatory", "anticipatory_legacy"),
        source_specs=(
            PassageSpec("anticipatory", ("bharatiya nagarik suraksha",), ("/sec-482",), optional=True),
            PassageSpec("anticipatory_legacy", ("code of criminal procedure",), ("/sec-438",), optional=True),
            PassageSpec("liberty", ("constitution",), ("/sec-21",), optional=True),
        ),
        forum="same court only on changed circumstances, otherwise Sessions/High Court as the papers permit",
        documents=("rejection order", "FIR and offence sections", "new facts or changed circumstances", "arrest notice or police-call record"),
        remedy="decide whether a fresh anticipatory-bail application has changed circumstances or should move to the higher court",
        caution="Repeating the same grounds before the same court is risky; the rejection order and changed facts matter.",
    ),
    CriminalVariantContract(
        id="anticipatory_bail_duration",
        label="Anticipatory-bail duration / police threat after grant",
        triggers_any=("how many days valid", "30 day", "30 days", "valid after grant", "police still threatening", "threatening to arrest"),
        required_any=("anticipatory", "bail granted", "after grant"),
        required_source_keys_any=("anticipatory", "anticipatory_legacy"),
        source_specs=(
            PassageSpec("anticipatory", ("bharatiya nagarik suraksha",), ("/sec-482",), optional=True),
            PassageSpec("anticipatory_legacy", ("code of criminal procedure",), ("/sec-438",), optional=True),
            PassageSpec("bail_forum", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483"), optional=True),
        ),
        forum="the court that granted anticipatory bail, or the High Court if clarification/protection is needed",
        documents=("anticipatory-bail order", "FIR", "police threat/call record", "conditions in the order", "compliance proof"),
        remedy="read the bail order for any time limit or condition, then seek clarification/protection or regular bail if the order requires it",
        caution="Do not rely on a generic number of days; the order terms control the next step.",
    ),
    CriminalVariantContract(
        id="default_bail_no_chargesheet",
        label="Default-bail / no-charge-sheet custody calculation",
        triggers_any=(
            "default bail", "default-bail", "statutory bail", "statutory/default bail",
            "no chargesheet", "no charge sheet", "chargesheet not filed", "charge sheet not filed",
            "chargesheet not ready", "charge sheet not ready", "chargesheet still not",
            "charge-sheet is still not", "60 days", "65 days", "88 days", "90 days",
            "92 days", "95 days", "100 days", "110 days", "180 days", "181 days",
            "6 months", "six months",
        ),
        required_any=("jail", "custody", "arrested", "remand", "chargesheet", "charge sheet", "mcoca", "uapa", "ndps"),
        required_source_keys_any=("default_bail", "default_bail_legacy"),
        source_specs=(
            PassageSpec("default_bail", ("bharatiya nagarik suraksha",), ("/sec-187",), optional=True),
            PassageSpec("default_bail_legacy", ("code of criminal procedure",), ("/sec-167",), optional=True),
            PassageSpec("ipc_cheating", ("indian penal",), ("/sec-420", "/sec-415"), optional=True),
            PassageSpec("bns_cheating", ("bharatiya nyaya",), ("/sec-318",), optional=True),
            PassageSpec("ndps_extension", ("narcotic drugs and psychotropic substances",), ("/sec-36a",), optional=True),
            PassageSpec("uapa_extension", ("unlawful activities", "uapa"), ("/sec-43d",), optional=True),
            PassageSpec("mcoca", ("maharashtra control of organised crime", "mcoca"), (), optional=True),
        ),
        forum="trial court/Special Court first, then High Court if the calculation or extension order is disputed",
        documents=("first remand date", "all remand orders", "charge-sheet filing status", "extension application/order", "special-statute sections"),
        remedy="decide whether a statutory/default-bail application should be filed immediately from custody dates, charge-sheet status, and any special-statute extension order",
        caution="MCOCA, UAPA, NDPS, and other special statutes can change the ordinary custody-period calculation.",
    ),
    CriminalVariantContract(
        id="regular_bail_first_time",
        label="Regular bail for first-time accused",
        triggers_any=("first time", "first-time", "first offender", "19 yrs", "19 year", "379", "theft"),
        required_any=("bail", "arrested", "custody", "jail"),
        required_source_keys_any=("regular_bail", "regular_bail_legacy"),
        source_specs=(
            PassageSpec("regular_bail", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483"), optional=True),
            PassageSpec("regular_bail_legacy", ("code of criminal procedure",), ("/sec-437", "/sec-439"), optional=True),
            PassageSpec("offence", ("bharatiya nyaya", "indian penal"), ("/sec-303", "/sec-317", "/sec-379"), optional=True),
        ),
        forum="Magistrate/trial court for regular bail, with Sessions/High Court only if refused or conditions are excessive",
        documents=("FIR", "arrest memo", "remand order", "age/address proof", "school/work/family roots", "surety or personal-bond papers"),
        remedy="move a regular-bail application tied to the theft section, custody status, and first-time accused facts",
        caution="Do not mix this with default bail unless the charge-sheet custody period has actually expired.",
    ),
    CriminalVariantContract(
        id="surety_too_high",
        label="Bail granted but surety unaffordable",
        triggers_any=("cant pay surety", "can't pay surety", "cannot pay surety", "surety 50000", "surety 50,000", "poor family", "surety too high", "high surety", "too strict", "conditions too strict", "reduce surety"),
        required_any=("bail granted", "surety", "bond"),
        required_source_keys_any=("regular_bail", "regular_bail_legacy", "moti_ram", "hussainara"),
        source_specs=(
            PassageSpec("regular_bail", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483"), optional=True),
            PassageSpec("regular_bail_legacy", ("code of criminal procedure",), ("/sec-437", "/sec-439"), optional=True),
            PassageSpec("moti_ram", ("moti ram",), (), optional=True),
            PassageSpec("hussainara", ("hussainara",), (), optional=True),
        ),
        forum="same bail court first; Sessions/High Court only if modification is refused",
        documents=("bail order", "surety amount and conditions", "income/poverty proof", "local address proof", "family member ID papers"),
        remedy="seek modification/reduction of surety conditions, personal bond, or alternate surety instead of remaining in jail after bail",
        caution="A bail grant is incomplete in practice if the accused cannot satisfy an unaffordable surety condition.",
    ),
    CriminalVariantContract(
        id="interim_bail_between_hearings",
        label="Interim bail between regular-bail hearings",
        triggers_any=("interim bail", "between regular bail hearings", "between bail hearings", "temporary bail"),
        required_any=("apply", "when", "hearing", "hearings", "regular bail"),
        required_source_keys_any=("regular_bail", "regular_bail_legacy"),
        source_specs=(
            PassageSpec("regular_bail", ("bharatiya nagarik suraksha",), ("/sec-480", "/sec-483"), optional=True),
            PassageSpec("regular_bail_legacy", ("code of criminal procedure",), ("/sec-437", "/sec-439"), optional=True),
        ),
        forum="the court hearing the regular-bail matter",
        documents=("pending bail application", "next hearing date", "urgent reason proof", "custody/remand papers", "medical/family/employment proof where relevant"),
        remedy="ask for interim bail or short-date relief in the pending bail matter when there is a concrete temporary urgency",
        caution="Interim bail is fact-specific; the urgency and custody papers matter more than a generic date formula.",
    ),
    CriminalVariantContract(
        id="it67_normal_selfie_accused",
        label="IT Act 67 complaint over non-nude photo",
        triggers_any=("67 case", "section 67", "it act 67", "photo", "selfie", "not nude", "whatsapp group"),
        required_any=("filed", "case", "complaint", "fir", "remedy"),
        required_source_keys_any=("it67",),
        source_specs=(
            PassageSpec("it67", ("information technology",), ("/sec-67",), optional=True),
            PassageSpec("procedure", ("bharatiya nagarik suraksha",), ("/sec-216", "/sec-173", "/sec-480", "/sec-483"), optional=True),
            PassageSpec("procedure_legacy", ("code of criminal procedure",), ("/sec-437", "/sec-438", "/sec-439"), optional=True),
        ),
        forum="cyber police/criminal court route depending on whether FIR, notice, or arrest has started",
        documents=("copy of the exact photo/post", "chat context", "group details", "complaint/FIR sections", "notice or summons"),
        remedy="check whether the allegation is really obscene/sexual electronic material or another privacy/harassment offence",
        caution="Do not delete evidence or contact/threaten the complainant; preserve the original post and get legal help before responding.",
    ),
    CriminalVariantContract(
        id="accused_simple_assault_after_affair",
        label="Simple assault accusation after domestic conflict",
        triggers_any=("slapped", "slap", "assault", "woman now she is filing case", "filing case on me"),
        required_any=("what to do", "remedy", "case", "police"),
        required_source_keys_any=("hurt",),
        source_specs=(
            PassageSpec("hurt", ("bharatiya nyaya", "indian penal"), ("/sec-115", "/sec-117", "/sec-323", "/sec-352"), optional=True),
            PassageSpec("procedure", ("bharatiya nagarik suraksha",), ("/sec-216", "/sec-480", "/sec-483"), optional=True),
            PassageSpec("procedure_legacy", ("code of criminal procedure",), ("/sec-437", "/sec-438", "/sec-439"), optional=True),
        ),
        forum="police station/criminal court route, with legal aid if notice or arrest risk starts",
        documents=("FIR/complaint if filed", "injury/medical record if any", "messages/CCTV/witnesses", "your own identity and address proof"),
        remedy="respond as an accused-side hurt/assault matter, not as a marriage remedy",
        caution="Do not contact or threaten the woman; preserve evidence and respond through counsel or legal aid if police call you.",
    ),
)


def criminal_authority_ledger_template_lines(
    query: str,
    route: MatterRoute,
    passages: list[dict],
) -> list[str]:
    """Return variant-specific criminal lines from the authority ledger."""
    if route.category not in {"criminal_defence_bail", "pmla_ed"}:
        return []
    q = _norm(query)
    contract = _select_contract(q, passages)
    if contract is None:
        return []
    sources = _resolve_sources(contract, passages)
    if not sources:
        return []
    primary = _primary_source(sources)
    secondary = _secondary_source(sources, primary)
    lines = ["**Short answer**"]
    topic = _topic_phrase(q, contract)
    statutory_line = _statutory_source_sentence(passages, primary)
    if statutory_line:
        lines.append(statutory_line)
    article = "an" if contract.label[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
    if contract.id == "anticipatory_bail_duration":
        lines.append(
            f"Treat this as {article} {contract.label} issue: do not use a generic number of days; {contract.remedy} [{primary}]."
        )
    else:
        lines.append(
            f"Treat this as {article} {contract.label} issue: {contract.remedy} [{primary}]."
        )
    if secondary is not None:
        lines.append(
            f"Keep the second source separate because it changes the legal test, forum, or offence facts for {topic} [{secondary}]."
        )
    if contract.id == "default_bail_no_chargesheet":
        day_count = _mentioned_day_count(q)
        source_refs = f"[{primary}]" + (f"[{secondary}]" if secondary is not None else "")
        if _has_any(q, ("incident 2023", "fir says incident 2023", "old ipc", "crpc or bnss", "ipc case")):
            lines.append(
                f"Because the papers may span the IPC/CrPC and BNS/BNSS transition, verify the incident date, arrest/remand date, and current court procedure before choosing BNSS Section 187 or CrPC Section 167 for the default-bail calculation {source_refs}."
            )
        if day_count is not None and day_count < 60:
            lines.append(
                f"At about {day_count} days in custody, default/statutory bail usually has not accrued only because the charge-sheet is absent; use the remand papers to calculate when the 60-day or 90-day period would expire [{primary}]."
            )
        elif day_count is not None:
            lines.append(
                f"At about {day_count} days with no charge-sheet, ask the trial court or Magistrate handling remand to calculate whether the 60-day or 90-day statutory/default-bail period applies from the offence section and maximum punishment [{primary}]."
            )
        if _has_any(q, ("what court should file", "move magistrate", "magistrate for default bail", "statutory bail")):
            lines.append(
                f"The first filing forum is the trial court or Magistrate/Special Court that controls remand, not a higher court first, unless that court refuses or the calculation is disputed [{primary}]."
            )
        if _has_any(q, ("chargesheet filed", "charge sheet filed", "filed yesterday", "already filed")):
            lines.append(
                f"If the charge-sheet was filed before any default-bail application was moved, do not assume automatic statutory bail; first verify the exact filing time, application time, and whether the right had already been exercised [{primary}]."
            )
        if _has_any(q, ("bail rejected", "regular bail rejected", "rejected twice", "rejected 3", "rejected three")):
            lines.append(
                f"Prior regular-bail rejection does not by itself decide statutory/default bail; if the charge-sheet deadline expired without a valid filing or extension, file a separate default-bail application on that custody calculation [{primary}]."
            )
        if _has_any(q, ("not ready", "tomorrow", "may file chargesheet", "may file charge sheet")):
            lines.append(
                f"If the statutory period has expired and the charge-sheet is still not filed, the family should ask jail legal aid, DLSA, or a criminal lawyer to move the trial court urgently instead of waiting for police to file it later [{primary}]."
            )
        if _has_any(q, ("65 days", "88 days", "90 days", "92 days", "95 days", "100 days", "110 days", "6 months", "six months", "no chargesheet", "no charge sheet", "chargesheet not", "charge sheet not", "statutory bail")):
            lines.append(
                f"The practical question is not ordinary bail versus earlier rejection; it is whether the accused was ready to furnish bail after the statutory period expired while no valid charge-sheet or extension order was on record [{primary}]."
            )
    if contract.id == "default_bail_no_chargesheet" and _has_any(q, ("ipc 420", "420", "cheating")) and _has_any(q, ("6 months", "six months", "tihar")):
        source_refs = f"[{primary}]" + (f"[{secondary}]" if secondary is not None else "")
        day_count = _mentioned_day_count(q)
        custody_phrase = (
            "about six months"
            if _has_any(q, ("6 months", "six months"))
            else f"about {day_count} days"
            if day_count is not None
            else "long enough that the statutory period may have expired"
        )
        ipc_source = sources.get("ipc_cheating")
        bns_source = sources.get("bns_cheating")
        offence_refs = "".join(
            f"[{idx}]"
            for idx in (bns_source, ipc_source)
            if idx is not None
        )
        offence_source = ipc_source or bns_source
        lines.append(
            f"If there is truly no charge-sheet after {custody_phrase} in a non-special cheating/420 case, ask the trial court for statutory/default bail immediately; verify from the remand papers whether BNSS Section 187 or CrPC Section 167 applies by date and regime {source_refs}."
        )
        if bns_source is not None and ipc_source is not None:
            lines.append(
                f"For the cheating/420 label, compare the current BNS cheating source with legacy IPC 420, and use the FIR section and maximum punishment for the 60-day or 90-day default-bail calculation {offence_refs}."
            )
        elif offence_source is not None:
            lines.append(
                f"For the IPC 420/cheating label, verify the exact cheating section and maximum punishment from the FIR before choosing the 60-day or 90-day default-bail period [{offence_source}]."
            )
        lines.append(
            f"If the statutory period has expired, the accused is prepared to furnish bail, and the charge-sheet is still not filed, the immediate next step is to file the default-bail application before the charge-sheet is filed [{primary}]."
        )
        place_note = "Tihar, " if "tihar" in q else ""
        offence_note = "IPC 420/cheating" if "ipc" in q else "cheating/420"
        lines.append(
            f"Because you mention {place_note}{offence_note}, {custody_phrase} in custody, and no charge-sheet, first build a custody-days chart from the first remand order and take it to jail legal aid, DLSA, or a criminal lawyer [{primary}]."
        )
        lines.append(
            f"Use the cited remand/default-bail source to test whether statutory bail has accrued from custody dates, charge-sheet status, maximum punishment, and any valid extension order [{primary}]."
        )
    if contract.id == "default_bail_no_chargesheet" and _has_any(q, ("mcoca", "uapa", "ndps", "special")):
        if "mcoca" in q and "mcoca" not in sources:
            lines.append(
                f"Because you mention MCOCA, do not assume the ordinary 60/90-day default-bail period; ask for the MCOCA extension application/order and verify the special-statute custody limit before filing [{primary}]."
            )
        else:
            lines.append(
                f"Special-statute custody or extension papers must be checked before deciding whether default bail has accrued [{secondary if secondary is not None else primary}]."
            )
    if contract.id == "anticipatory_bail_duration":
        lines.append(
            f"Do not use a generic number of days; read the anticipatory-bail order for any time limit, cooperation condition, or direction to seek regular bail [{primary}]."
        )
    if contract.id == "surety_too_high":
        amount = _money_phrase(q)
        amount_phrase = f" such as {amount}" if amount else ""
        lines.append(
            f"If bail is already granted but the surety{amount_phrase} is unaffordable, the practical next step is a modification application for lower surety, personal bond, or alternate surety papers [{primary}]."
        )
    if contract.id == "it67_normal_selfie_accused":
        lines.append(
            f"If the shared item was a normal selfie and not nude or sexually explicit, preserve the exact image and complaint because the IT Act 67 issue turns on what electronic material is actually alleged [{primary}]."
        )
    if contract.caution:
        lines.append(f"{contract.caution} [{primary}].")
    lines.append("**What you can do next**")
    docs = ", ".join(contract.documents)
    if contract.id == "default_bail_no_chargesheet":
        lines.append(
            f"- Go to {contract.forum}; keep {docs}; prepare a custody-days chart from the first remand date, verify the exact offence section and maximum punishment, and ask jail legal aid, DLSA, or a criminal lawyer to file default/statutory bail in the trial court if the 60-day or 90-day period has expired without a charge-sheet or valid extension order [{primary}]."
        )
    elif contract.id == "anticipatory_bail_duration":
        lines.append(
            f"- Go to {contract.forum}; keep {docs}; do not use a generic number of days, and ask the court or lawyer to read the bail order for any time limit, cooperation condition, or direction to seek regular bail [{primary}]."
        )
    else:
        lines.append(
            f"- Go to {contract.forum}; keep {docs}; and ask for {contract.remedy} [{primary}]."
        )
    return lines


def _select_contract(q: str, passages: list[dict]) -> CriminalVariantContract | None:
    scored: list[tuple[int, CriminalVariantContract]] = []
    for contract in CRIMINAL_VARIANT_CONTRACTS:
        if not _has_any(q, contract.triggers_any):
            continue
        if contract.required_any and not _has_any(q, contract.required_any):
            continue
        sources = _resolve_sources(contract, passages)
        if not sources:
            continue
        if not _has_required_source(contract, sources):
            continue
        trigger_hits = sum(1 for term in contract.triggers_any if term in q)
        source_hits = len(sources)
        harm_bonus = 5 if contract.id in {"pmla_pre_arrest_bail", "default_bail_no_chargesheet"} else 0
        scored.append((trigger_hits * 10 + source_hits + harm_bonus, contract))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _has_required_source(contract: CriminalVariantContract, sources: dict[str, int]) -> bool:
    return any(key in sources for key in contract.required_source_keys_any)


def _resolve_sources(contract: CriminalVariantContract, passages: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for spec in contract.source_specs:
        idx = _find_passage_index(
            passages,
            title_terms=spec.title_terms,
            anchor_terms=spec.anchor_terms,
        )
        if idx is not None:
            out[spec.key] = idx
    return out


def _primary_source(sources: dict[str, int]) -> int:
    for key in (
        "pmla",
        "default_bail",
        "default_bail_legacy",
        "regular_bail",
        "regular_bail_legacy",
        "anticipatory",
        "anticipatory_legacy",
        "it67",
        "hurt",
        "procedure",
    ):
        if key in sources:
            return sources[key]
    return next(iter(sources.values()))


def _secondary_source(sources: dict[str, int], primary: int) -> int | None:
    for key, idx in sources.items():
        if idx != primary and key not in {"moti_ram", "hussainara"}:
            return idx
    for idx in sources.values():
        if idx != primary:
            return idx
    return None


def _find_passage_index(
    passages: list[dict],
    *,
    title_terms: tuple[str, ...] = (),
    anchor_terms: tuple[str, ...] = (),
) -> int | None:
    for passage in passages:
        title = str(passage.get("title") or "").lower()
        anchor = str(passage.get("anchor") or "").lower()
        title_ok = not title_terms or any(term in title for term in title_terms)
        anchor_ok = not anchor_terms or any(_anchor_matches_term(anchor, term) for term in anchor_terms)
        if title_ok and anchor_ok:
            idx = passage.get("index")
            return int(idx) if isinstance(idx, int) else None
    return None


def _statutory_source_sentence(passages: list[dict], idx: int) -> str | None:
    passage = next((item for item in passages if item.get("index") == idx), None)
    if not passage:
        return None
    title = str(passage.get("title") or "").lower()
    anchor = str(passage.get("anchor") or "").lower()
    if "bharatiya nagarik suraksha" in title or "bnss" in anchor:
        if "/sec-483" in anchor:
            return f"The BNSS bail source says a High Court or Court of Session may direct that an accused person in custody be released on bail [{idx}]."
        if "/sec-480" in anchor:
            return f"The BNSS bail source is the court bail provision to check for release of an accused person on bail [{idx}]."
        if "/sec-482" in anchor:
            return f"The BNSS anticipatory-bail source is the current pre-arrest bail provision to check when arrest is feared [{idx}]."
        if "/sec-187" in anchor:
            return f"The BNSS remand source is the custody-period source to check when charge-sheet/default-bail timing is the issue [{idx}]."
    if "code of criminal procedure" in title or "crpc" in anchor:
        if "/sec-439" in anchor:
            return f"The CrPC bail source says a High Court or Court of Session may direct that an accused person in custody be released on bail [{idx}]."
        if "/sec-437" in anchor:
            return f"The CrPC bail source is the court bail provision to check for release in a non-bailable offence [{idx}]."
        if "/sec-438" in anchor:
            return f"The CrPC anticipatory-bail source is the pre-arrest bail provision to check when arrest is feared [{idx}]."
        if "/sec-167" in anchor:
            return f"The CrPC remand source is the custody-period source to check when charge-sheet/default-bail timing is the issue [{idx}]."
    if "prevention of money laundering" in title or "pmla" in anchor:
        return f"The PMLA source is the special money-laundering bail provision to check before ordinary bail procedure [{idx}]."
    if "information technology" in title or "it-act" in anchor:
        return f"The Information Technology Act source is the electronic-content offence source to check against the exact photo, post, and complaint [{idx}]."
    return None


def _anchor_matches_term(anchor: str, term: str) -> bool:
    needle = term.lower()
    if needle.startswith("/sec-"):
        return re.search(rf"{re.escape(needle)}(?=@|-|__|$)", anchor) is not None
    if needle.startswith("sec-"):
        return re.search(rf"(^|/){re.escape(needle)}(?=@|-|__|$)", anchor) is not None
    return needle in anchor


def _topic_phrase(q: str, contract: CriminalVariantContract) -> str:
    if "379" in q or "theft" in q:
        return "the theft or BNS/IPC section in the FIR"
    if "pmla" in q or re.search(r"(?<![a-z0-9])ed(?![a-z0-9])", q):
        return "the PMLA/ED papers"
    if "mcoca" in q:
        return "the MCOCA custody calculation"
    if "surety" in q:
        return "the bail order conditions"
    return contract.label.lower()


def _money_phrase(q: str) -> str | None:
    match = re.search(r"(?:rs\.?\s*)?\b\d{4,7}\b", q)
    return match.group(0) if match else None


def _mentioned_day_count(q: str) -> int | None:
    match = re.search(r"\b(\d{1,3})\s*days?\b", q)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
