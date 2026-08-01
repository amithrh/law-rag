"""Deterministic, privacy-conscious follow-up questions for legal intake.

The first answer should remain useful on its own.  These questions are a
bounded refinement layer: they expose only the facts that can change the
route, forum, regime, or immediate safety advice.  They do not call an LLM
and they never persist the user's answers.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .legal_issue_plan import MatterPlan
    from .matter_router import MatterRoute


IntakeInputType = Literal["text", "date", "choice"]
SOURCE_GAP_INTAKE_KIND = "source_gap_facts"
SOURCE_GAP_INTAKE_QUESTION_IDS = frozenset({
    "jurisdiction",
    "incident_date",
    "document_status",
    "desired_outcome",
})


@dataclass(frozen=True)
class IntakeQuestion:
    id: str
    prompt: str
    reason: str
    input_type: IntakeInputType = "text"
    options: tuple[str, ...] = ()

    def to_event(self) -> dict:
        payload = asdict(self)
        payload["options"] = list(self.options)
        return payload


def build_intake_event(
    query: str,
    route: MatterRoute,
    plan: MatterPlan | None,
    *,
    max_questions: int = 3,
) -> dict | None:
    """Return a small UI-safe intake event, or ``None`` when no question helps.

    The function intentionally uses the already-reviewed MatterPlan rather
    than re-classifying the query.  That keeps intake aligned with the same
    route and avoids a second, potentially contradictory classifier.
    """
    if plan is None or route.category == "off_topic" or max_questions <= 0:
        return None

    q = _normalize(query)
    candidates: list[IntakeQuestion] = []

    def add(question: IntakeQuestion, *, already_answered: bool = False) -> None:
        if already_answered or any(existing.id == question.id for existing in candidates):
            return
        if question.id == "incident_date" and any(
            existing.id == "criminal_transition" for existing in candidates
        ):
            return
        if question.id == "criminal_transition" and any(
            existing.id == "incident_date" for existing in candidates
        ):
            return
        candidates.append(question)

    # Safety is first and is never hidden behind a form.  The answer plan is
    # still emitted immediately; this prompt only helps the next refinement.
    if plan.urgency == "emergency" and _missing_fact(plan, "safety", "shelter", "current danger"):
        add(
            IntakeQuestion(
                id="current_safety",
                prompt="Are you safe right now, and do you need emergency help or a safe place?",
                reason="Immediate safety changes the first step and should not wait for legal classification.",
                input_type="choice",
                options=("Safe for now", "Need urgent help", "Prefer not to say"),
            ),
            already_answered=_mentions(q, "safe", "safety", "danger", "emergency", "shelter"),
        )

    if _is_bank_hold(route, plan):
        add(
            IntakeQuestion(
                id="bank_hold_reason",
                prompt="What reason did the bank give for the freeze or lien: KYC, cyber/police, court/ED, or an internal bank hold, and when did it start?",
                reason="The source, date, and written reason determine whether this is a bank-service complaint or a legal-investigation hold.",
                input_type="choice",
                options=("KYC/bank reason", "Cyber or police", "Court or ED", "No reason given"),
            ),
            already_answered=_mentions(
                q,
                "written reason",
                "reference number",
                "order copy",
                "freeze date",
                "lien date",
                "kyc/bank reason",
                "cyber or police",
                "court or ed",
                "no reason given",
                "internal bank hold",
                "cyber/police",
            ),
        )

    if _needs_transition_question(q, route, plan):
        device_specific = "device" in plan.primary_issue or "device" in plan.primary_label.lower()
        prompt = (
            "Was the investigation, application, inquiry, or trial already pending immediately before 1 July 2024, or did it start on/after that date?"
            if device_specific
            else "What is the incident or FIR date, and was the investigation or proceeding already pending immediately before 1 July 2024?"
        )
        add(
            IntakeQuestion(
                id="criminal_transition",
                prompt=prompt,
                reason="The transition rule can change which criminal procedure source and remedy apply.",
                input_type="choice",
                options=(
                    "Pending immediately before 1 July 2024",
                    "Started on or after 1 July 2024",
                    "Concluded before 1 July 2024",
                    "Unknown",
                ),
            ),
            already_answered=_has_transition_answer(q),
        )

    if plan.jurisdiction.needs_state or _missing_fact(plan, "state", "city", "district"):
        add(
            IntakeQuestion(
                id="jurisdiction",
                prompt="Which state and city or district is this in?",
                reason="Forum, limitation, rent, labour, welfare, and administrative routes can depend on state and district.",
            ),
            already_answered=(
                bool(plan.jurisdiction.city)
                or _mentions_named_city_or_district(q)
                or _mentions(q, "city:", "district:")
            ),
        )

    if _is_cyber_money(route, plan):
        add(
            IntakeQuestion(
                id="money_loss_and_time",
                prompt="Has money already left your account, when did it happen, and have you reported it to the bank or 1930?",
                reason="A live money trail needs a faster preservation and reporting path than a general cyber complaint.",
            ),
            already_answered=_mentions(q, "money transferred", "money got transferred", "lost", "1930", "reported to bank", "bank complaint"),
        )

    if _is_court_or_police_stage(route, plan):
        add(
            IntakeQuestion(
                id="case_stage",
                prompt="Is there an FIR, notice, arrest, charge-sheet, court order, or next hearing date already?",
                reason="The available remedy changes sharply between pre-complaint, investigation, custody, and court stages.",
                input_type="choice",
                options=("No paper yet", "FIR or police stage", "Arrest or custody", "Court stage"),
            ),
            already_answered=_mentions(q, "fir", "notice", "summons", "custody", "charge sheet", "chargesheet", "hearing", "court order", "bail"),
        )

    # Generic high-value fact prompts come after route-specific prompts.  The
    # wording is intentionally plain-language rather than exposing the raw
    # internal ``missing_facts`` labels to users.
    for fact in plan.required_facts:
        question = _question_for_fact(fact, route, plan)
        if question is None:
            continue
        add(question, already_answered=_fact_already_present(q, fact))

    if len(candidates) < max_questions and plan.desired_outcome in {
        "unspecified",
        "relief_or_next_step",
        "pre_complaint_or_unknown",
    }:
        add(
            IntakeQuestion(
                id="desired_outcome",
                prompt="What result do you want first: stop the harm, recover money/property, challenge a notice/order, or understand the next forum?",
                reason="The desired result helps separate an urgent protection step from a later claim or appeal.",
                input_type="choice",
                options=("Safety or stop harm", "Recover money/property", "Challenge notice/order", "Find the right forum"),
            ),
            already_answered=_mentions(q, "what can i do", "what should i do", "next step", "recover", "refund", "release", "stop", "challenge", "appeal"),
        )

    if not candidates:
        return None
    questions = candidates[:max_questions]
    return {
        "schema_version": 1,
        "questions": [question.to_event() for question in questions],
        "privacy_note": "Do not share Aadhaar, full bank or card numbers, passwords, OTPs, or private intimate material here.",
    }


def build_source_gap_intake_event(
    query: str,
    route: MatterRoute,
    source_gap_event: dict | None,
    *,
    max_questions: int = 3,
) -> dict | None:
    """Offer bounded fact collection for a jurisdictional source handoff.

    A source gap still withholds the legal answer.  This narrower event lets a
    user supply the state, district, date, or controlling paper that may make a
    later retry answerable.  It intentionally does not require or serialize a
    MatterPlan, forum, portal, deadline, or legal conclusion.
    """
    if not isinstance(source_gap_event, dict) or max_questions <= 0:
        return None
    gap_kinds = source_gap_event.get("gap_kinds")
    if (
        source_gap_event.get("has_gap") is not True
        or source_gap_event.get("outcome") != "source_gap_handoff"
        or source_gap_event.get("safe_handoff_only") is not True
        or not isinstance(gap_kinds, list)
        or not all(isinstance(kind, str) and kind.strip() for kind in gap_kinds)
        or "state_or_local_authority_gap" not in gap_kinds
    ):
        return None

    query_text = _normalize(query)
    candidates: list[IntakeQuestion] = []

    def add(question: IntakeQuestion) -> None:
        if len(candidates) >= max_questions:
            return
        if any(existing.id == question.id for existing in candidates):
            return
        if question.id not in SOURCE_GAP_INTAKE_QUESTION_IDS:
            return
        candidates.append(question)

    missing_facts = tuple(str(fact or "") for fact in route.missing_facts)
    needs_jurisdiction = any(
        _mentions(_normalize(fact), "state", "city", "district", "jurisdiction")
        for fact in missing_facts
    )
    if needs_jurisdiction and not (
        _mentions_named_city_or_district(query_text)
        or _mentions(query_text, "city:", "district:")
    ):
        add(
            IntakeQuestion(
                id="jurisdiction",
                prompt="Which state and city or district is this in?",
                reason="The missing local authority or procedure can change with the jurisdiction.",
            )
        )

    date_needed = any(
        _mentions(_normalize(fact), "date", "when", "incident", "seizure")
        for fact in missing_facts
    ) or "incident_date_needed" in str(route.legal_regime or "")
    if date_needed and not _fact_already_present(query_text, "incident date"):
        add(
            IntakeQuestion(
                id="incident_date",
                prompt="What date did the key event, notice, seizure, or refusal happen?",
                reason="The date can change the applicable procedure and the safest next step.",
                input_type="date",
            )
        )

    if any(
        _mentions(_normalize(fact), "notice", "order", "fir", "complaint", "application", "proof")
        for fact in missing_facts
    ):
        add(
            IntakeQuestion(
                id="document_status",
                prompt="Do you have the notice, order, complaint receipt, application number, or written refusal?",
                reason="The exact paper and date are safer than guessing from an oral explanation.",
            )
        )

    if not candidates:
        add(
            IntakeQuestion(
                id="desired_outcome",
                prompt="What result do you want first: stop the harm, recover money/property, challenge a notice/order, or find the right forum?",
                reason="The immediate goal helps decide which source-backed route to verify on retry.",
                input_type="choice",
                options=("Safety or stop harm", "Recover money/property", "Challenge notice/order", "Find the right forum"),
            )
        )

    if not candidates:
        return None
    return {
        "schema_version": 1,
        "intake_kind": SOURCE_GAP_INTAKE_KIND,
        "route_category": route.category,
        "questions": [question.to_event() for question in candidates[:max_questions]],
        "privacy_note": "Do not share Aadhaar, full bank or card numbers, passwords, OTPs, or private intimate material here.",
    }


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _mentions(query: str, *terms: str) -> bool:
    return any(term in query for term in terms)


def _mentions_named_jurisdiction(query: str) -> bool:
    """Accept a jurisdiction only when a real place is named.

    The words ``state`` and ``city`` often occur in a user's question about
    which regime applies; treating those labels as an answer suppresses the
    very intake question needed to resolve the route.
    """
    places = (
        "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
        "delhi", "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand",
        "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur",
        "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab",
        "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
        "uttar pradesh", "uttarakhand", "west bengal", "ahmedabad", "bengaluru",
        "bangalore", "bhopal", "chennai", "hyderabad", "jaipur", "kolkata",
        "lucknow", "mumbai", "nagpur", "noida", "patna", "pune", "ranchi",
        "surat", "vadodara", "baroda", "thane", "indore", "rajkot", "kochi",
        "cochin", "ernakulam", "thiruvananthapuram", "coimbatore", "madurai",
        "salem", "mysuru", "mysore", "mangalore", "faridabad", "gurugram",
        "gurgaon", "chandigarh", "jammu", "srinagar", "puducherry", "pondicherry",
    )
    return any(re.search(rf"\b{re.escape(place)}\b", query) for place in places)


def _mentions_named_city_or_district(query: str) -> bool:
    """Return true only when a concrete city/district-level place is named."""
    cities = (
        "ahmedabad", "bengaluru", "bangalore", "bhopal", "chennai",
        "hyderabad", "jaipur", "kolkata", "lucknow", "mumbai", "nagpur",
        "noida", "patna", "pune", "ranchi", "surat", "vadodara", "baroda",
        "thane", "indore", "rajkot", "kochi", "cochin", "ernakulam",
        "thiruvananthapuram", "coimbatore", "madurai", "salem", "mysuru",
        "mysore", "mangalore", "faridabad", "gurugram", "gurgaon",
        "chandigarh", "jammu", "srinagar", "puducherry", "pondicherry",
    )
    return any(re.search(rf"\b{re.escape(city)}\b", query) for city in cities)


def _missing_fact(plan: MatterPlan, *terms: str) -> bool:
    return any(_mentions(_normalize(fact), *terms) for fact in plan.required_facts)


def _is_bank_hold(route: MatterRoute, plan: MatterPlan) -> bool:
    text = f"{route.category} {plan.primary_issue} {plan.primary_label}".lower()
    return "bank" in text and _mentions(text, "freeze", "lien", "hold", "account")


def _is_cyber_money(route: MatterRoute, plan: MatterPlan) -> bool:
    text = f"{route.category} {plan.primary_issue} {plan.primary_label}".lower()
    return "cyber" in text and _mentions(text, "fraud", "money", "financial", "upi", "bank")


def _is_insurance(route: MatterRoute, plan: MatterPlan) -> bool:
    text = f"{route.category} {plan.primary_issue} {plan.primary_label}".lower()
    return _mentions(text, "insurance", "insurer", "policy", "claim")


def _is_court_or_police_stage(route: MatterRoute, plan: MatterPlan) -> bool:
    text = f"{route.category} {plan.primary_issue} {plan.primary_label}".lower()
    return _mentions(text, "police", "fir", "arrest", "bail", "criminal", "court", "notice")


def _needs_transition_question(query: str, route: MatterRoute, plan: MatterPlan) -> bool:
    text = f"{route.category} {plan.primary_issue} {plan.primary_label}".lower()
    criminal = _mentions(text, "criminal", "police", "fir", "arrest", "bail", "device")
    date_fact = _missing_fact(plan, "incident date", "seizure date", "1 july 2024", "pending immediately")
    return criminal and (date_fact or plan.incident_date_status == "needed_for_criminal_regime")


def _has_transition_answer(query: str) -> bool:
    return _mentions(
        query,
        "pending before 1 july 2024",
        "pending immediately before 1 july 2024",
        "pending before july 2024",
        "pending on 30 june 2024",
        "pending as of 30 june 2024",
        "investigation started after 1 july 2024",
        "investigation began after 1 july 2024",
        "investigation started on or after 1 july 2024",
        "investigation began on or after 1 july 2024",
        "proceeding started after 1 july 2024",
        "proceeding began after 1 july 2024",
        "new fir registered after 1 july 2024",
        "new fir filed after 1 july 2024",
        "fir registered on or after 1 july 2024",
        "fir filed on or after 1 july 2024",
        "started on or after 1 july 2024",
        "concluded before 1 july 2024",
        "already concluded before 1 july 2024",
        "already closed before 1 july 2024",
        "already disposed before 1 july 2024",
        "no longer pending before 1 july 2024",
        "ended before 1 july 2024",
        "criminal_transition: unknown",
    )


def _fact_already_present(query: str, fact: str) -> bool:
    fact = _normalize(fact)
    if _mentions(fact, "city", "district"):
        return _mentions_named_city_or_district(query) or _mentions(query, "city:", "district:")
    if _mentions(fact, "state", "city", "district"):
        return _mentions_named_jurisdiction(query)
    if _mentions(fact, "date", "day", "when"):
        return bool(re.search(r"\b(?:19|20)\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", query))
    if _mentions(fact, "amount", "value", "salary", "wage", "rent"):
        return bool(re.search(r"(?:rs\.?|₹|inr|amount|salary|wage|rent)\s*[0-9]", query))
    if _mentions(fact, "notice", "order", "fir", "complaint", "receipt", "proof", "papers", "documents"):
        return _mentions(query, "notice", "order", "fir", "complaint", "receipt", "proof", "papers", "documents")
    if _mentions(fact, "stage", "hearing", "arrest", "custody", "case"):
        return _mentions(query, "stage", "hearing", "arrest", "custody", "case", "court")
    if _mentions(fact, "safety", "injury", "medical", "victim"):
        return _mentions(query, "safe", "safety", "injury", "injured", "medical", "hospital")
    return False


def _question_for_fact(fact: str, route: MatterRoute, plan: MatterPlan) -> IntakeQuestion | None:
    normalized = _normalize(fact)
    if _mentions(normalized, "state", "city", "district"):
        return IntakeQuestion(
            id="jurisdiction",
            prompt="Which state and city or district is this in?",
            reason="The forum and local procedure may depend on the jurisdiction.",
        )
    if _mentions(normalized, "incident date", "seizure date", "application date", "date of"):
        return IntakeQuestion(
            id="incident_date",
            prompt="What date did the key event, notice, seizure, or refusal happen?",
            reason="The date can affect limitation, procedure, and which legal regime applies.",
            input_type="date",
        )
    if _mentions(normalized, "current safety", "current danger", "shelter"):
        return IntakeQuestion(
            id="current_safety",
            prompt="Are you safe right now, and is there any immediate risk of harm?",
            reason="Immediate safety takes priority over a later legal filing.",
            input_type="choice",
            options=("Safe for now", "Immediate risk", "Prefer not to say"),
        )
    if _mentions(normalized, "case stage", "hearing", "arrest status", "custody", "charge-sheet"):
        return IntakeQuestion(
            id="case_stage",
            prompt="What is the current stage: no case paper, police/FIR, arrest or custody, or court hearing?",
            reason="The next remedy depends on the current procedural stage.",
            input_type="choice",
            options=("No paper yet", "Police/FIR", "Arrest or custody", "Court hearing"),
        )
    if _mentions(normalized, "amount", "value", "salary", "wage", "rent"):
        return IntakeQuestion(
            id="amount",
            prompt="What amount or value is involved, and when was it due or last paid?",
            reason="Amount and due dates can change forum, limitation, and the practical next step.",
        )
    if _mentions(normalized, "notice", "order", "fir", "complaint", "application", "refusal"):
        if _is_bank_hold(route, plan):
            prompt = "Do you have the bank's SMS or email, freeze/lien reference, and complaint number?"
        elif route.category == "consumer" and _is_insurance(route, plan):
            prompt = "Do you have the policy, claim number, insurer's written rejection, and complaint or grievance number?"
        elif route.category == "consumer":
            prompt = "Do you have the invoice or order ID, warranty terms, and the seller's written response?"
        elif _is_court_or_police_stage(route, plan):
            prompt = "Do you have the FIR, notice, arrest memo, remand order, or next hearing date?"
        elif route.category in {"education_rights", "school_education"}:
            prompt = "Do you have the admission application, written refusal, and any fee or eligibility papers?"
        elif route.category == "property_tenancy":
            prompt = "Do you have the rent agreement or deed, payment records, and any notice or message?"
        else:
            prompt = "Do you have the notice, order, application receipt, or written refusal, and what date is on it?"
        return IntakeQuestion(
            id="document_status",
            prompt=prompt,
            reason="The exact paper and date are safer than guessing from an oral explanation.",
        )
    if _mentions(normalized, "role", "accused", "witness", "complainant", "employer", "employee"):
        return IntakeQuestion(
            id="user_role",
            prompt="What is your role in this matter: affected person, complainant, accused/respondent, witness, tenant, employee, or business?",
            reason="The same facts can lead to different duties and remedies depending on your role.",
        )
    if _mentions(normalized, "proof", "documents", "papers", "messages", "photos", "records"):
        return IntakeQuestion(
            id="available_proof",
            prompt="What proof do you already have, such as messages, receipts, photos, medical papers, or a complaint number?",
            reason="Evidence already preserved determines the safest immediate action.",
        )
    return None
