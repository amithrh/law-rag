"""Shared, conservative incident-fact detectors used by routing and answers."""
from __future__ import annotations

import re


_ACID_COMPLETION_PHRASES = (
    "suffered an acid attack",
    "suffered acid burn",
    "suffered chemical burn",
    "acid attack happened",
    "acid attack on me",
)
_ACID_ATTACK_LABEL_PHRASES = (
    "acid attack",
    "chemical attack",
)
_ACID_EXPOSURE_PHRASES = (
    "acid on my face",
    "acid on me",
    "chemical on my face",
    "chemical on me",
    "acid spilled on me",
    "chemical spilled on me",
    "chemical exposure",
    "acid injury",
    "chemical injury",
    "acid burn",
    "acid burns",
    "chemical burn",
    "chemical burns",
    # These are exposure clues, not proof that an intentional attack occurred.
    "eyes burning",
    "eyes are burning",
    "my eyes are burning",
    "face burning",
    "face is burning",
    "my face is burning",
    "burning after acid",
    "hospital said acid",
)
_CLAUSE_BREAKS = (
    ".", "?", "!", ";", ":", ",", " but ", " however ", " although ",
    " and ", " or ",
)
_NEGATION_WORDS = (
    r"(?:no|nobody|no one|nothing|neither|never|not|without|"
    r"didn't|did not|doesn't|does not|isn't|is not|wasn't|was not|"
    r"weren't|were not|can't|cannot|couldn't|could not)"
)
_UNCERTAINTY_WORDS = (
    "didn't see", "did not see", "not sure", "unsure", "unclear",
    "don't know", "do not know", "no idea whether", "cannot tell",
    "might have", "could have", "may have", "perhaps", "maybe",
    "contact is uncertain", "contact uncertain", "cannot confirm",
    "can't confirm", "not confirmed", "cannot be confirmed",
    "could not confirm", "couldn't confirm",
)
_ACID_ATTEMPT_PHRASES = (
    "attempted to throw acid",
    "attempted to throw chemical",
    "tried to throw acid",
    "tried to throw chemical",
    "was trying to throw acid",
    "was trying to throw chemical",
    "attempted an acid attack",
    "attempted a chemical attack",
    "tried an acid attack",
    "tried a chemical attack",
    "failed to throw acid",
    "failed to throw chemical",
)
_ACID_ATTEMPT_RE = re.compile(
    r"\b(?:attempt(?:ed|ing)?|tr(?:ied|y|ying)|failed)\b.{0,48}"
    r"\b(?:throw|pour|splash|use|attack|assault)\w*\b.{0,32}"
    r"\b(?:acid|chemical)\b"
)
_POSSIBLE_ACID_EXPOSURE_ACTION_RE = re.compile(
    r"\b(?:throw|threw|thrown|pour|poured|splash|splashed|"
    r"administer|administered|use|used)\b.{0,28}\b(?:acid|chemical)\b"
    r"|\b(?:acid|chemical)\b.{0,28}\b(?:thrown|poured|splashed|"
    r"administered|used)\b"
)
_DIRECT_ACID_ACTION_RE = re.compile(
    r"\b(?:throw|threw|thrown|pour|poured|splashed|administer|administered|"
    r"use|used)\b.{0,32}\b(?:acid|chemical(?:s)?)\b.{0,32}"
    r"\b(?:on|at|onto|to|over)\s+(?:me|my\s+(?:face|body|eyes|skin)|him|her|"
    r"the\s+victim|a\s+person|someone|anyone)\b"
    r"|\b(?:acid|chemical(?:s)?)\b.{0,32}\b(?:thrown|poured|splashed|"
    r"administered|used)\b.{0,32}\b(?:on|at|onto|to|over)\s+(?:me|my\s+"
    r"(?:face|body|eyes|skin)|him|her|the\s+victim|a\s+person|someone|"
    r"anyone)\b",
)
_DIRECT_ACID_ATTACK_RE = re.compile(
    r"\b(?:was|were|been|being|got)\s+(?:attacked|assaulted)\s+with\s+"
    r"(?:an?\s+|the\s+)?(?:acid|chemical(?:s)?)\b"
    r"|\b(?:attacked|assaulted)\s+(?:me\s+)?with\s+(?:an?\s+|the\s+)?"
    r"(?:acid|chemical(?:s)?)\b"
    r"|\b(?:attacked|assaulted)\b.{0,32}\busing\b.{0,16}"
    r"(?:an?\s+|the\s+)?(?:acid|chemical(?:s)?)(?:\s+liquid)?\b"
    r"|\b(?:acid|chemical)\s+was\s+used\s+to\s+attack\b"
    r"|\b(?:used|use)\s+(?:an?\s+|the\s+)?(?:acid|chemical)\b"
    r".{0,24}\bto\s+attack\b"
)
_UNCERTAIN_ACID_EVENT_RE = re.compile(
    r"\b(?:acid|chemical)\b.{0,48}\b(?:throw|threw|thrown|pour|poured|"
    r"splash|splashed|administer|administered|use|used)\b.{0,48}"
    r"\b(?:on|at|onto|to|over)\s+(?:me|my\s+(?:face|body|eyes|skin)|"
    r"him|her|the\s+victim|a\s+person|someone|anyone)\b"
    r"|\b(?:throw|threw|thrown|pour|poured|splash|splashed|administer|"
    r"administered|use|used)\b.{0,48}\b(?:acid|chemical)\b.{0,48}"
    r"\b(?:on|at|onto|to|over)\s+(?:me|my\s+(?:face|body|eyes|skin)|"
    r"him|her|the\s+victim|a\s+person|someone|anyone)\b"
)
_POST_THREAT_COMPLETION_RE = re.compile(
    r"\b(?:acid|chemical)\b.{0,24}\b(?:later|then)\b.{0,24}"
    r"\b(?:threw|thrown|poured|splashed|administered|used)\b"
)
_LATER_CONFIRMED_CONTACT_RE = re.compile(
    r"\b(?:miss(?:ed)?|fell short|no contact|couldn't confirm contact|"
    r"could not confirm contact|might have|could have|may have)\b"
    r".{0,96}\b(?:then|later|but later)\b.{0,32}"
    r"\b(?:it|acid|chemical|the liquid)\b.{0,24}\b(?:hit|touched|"
    r"contacted|reached|landed|got on|burned)\b.{0,20}\b(?:me|myself|"
    r"my\s+(?:face|body|eyes|skin)|him|her|the\s+victim|someone)\b"
)
_MEDICAL_ACID_CONFIRMATION_RE = re.compile(
    r"\b(?:hospital|doctor|mlc|medical(?:\s+report|\s+test)?)\b"
    r".{0,40}\b(?:said|confirmed|found|diagnosed|showed)\b"
    r".{0,20}\b(?:acid|chemical)\b"
)
_FUTURE_OR_PLANNED_PREFIX_RE = re.compile(
    r"\b(?:would|will|shall|might|could|may|going\s+to|about\s+to|"
    r"plan(?:s|ned|ning)?|intend(?:s|ed)?|meant\s+to)\b.{0,48}$"
)

_TEXT_NORMALIZATION = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_TEXT_NORMALIZATION).lower()).strip()


def _has_negation_before(lower: str, start: int) -> bool:
    clause_start = 0
    for marker in _CLAUSE_BREAKS:
        marker_start = lower.rfind(marker, 0, start)
        if marker_start >= 0:
            clause_start = max(clause_start, marker_start + len(marker))
    before = lower[clause_start:start]
    return (
        re.search(rf"\b{_NEGATION_WORDS}\b", before) is not None
        or any(marker in before for marker in _UNCERTAINTY_WORDS)
    )


def _has_threat_prefix(lower: str, start: int) -> bool:
    clause_start = 0
    for marker in _CLAUSE_BREAKS:
        marker_start = lower.rfind(marker, 0, start)
        if marker_start >= 0:
            clause_start = max(clause_start, marker_start + len(marker))
    prefix = lower[max(clause_start, start - 64):start]
    return re.search(
        r"\b(?:threat(?:en(?:ed|ing)?|s)?|dhamki|"
        r"warn(?:ed|ing|s)?|fear(?:ed|ing)?|afraid|scared)\b.{0,48}$",
        prefix,
    ) is not None


def _has_attempt_prefix(lower: str, start: int) -> bool:
    """Reject an action match that is explicitly described as an attempt."""
    clause_start = 0
    for marker in _CLAUSE_BREAKS:
        marker_start = lower.rfind(marker, 0, start)
        if marker_start >= 0:
            clause_start = max(clause_start, marker_start + len(marker))
    prefix = lower[max(clause_start, start - 72):start]
    return re.search(
        r"\b(?:attempt(?:ed|ing)?|tr(?:ied|y|ying)|failed|missed)\b.{0,60}$",
        prefix,
    ) is not None


def _has_post_exposure_uncertainty(lower: str, end: int) -> bool:
    """Reject a label when the user is unsure whether contact actually occurred."""
    tail = lower[end:end + 128]
    if not any(marker in tail for marker in _UNCERTAINTY_WORDS):
        return False
    return re.search(
        r"\b(?:touch(?:ed|es|ing)?|contact(?:ed|s|ing)?|"
        r"reach(?:ed|es|ing)?|land(?:ed|s|ing)?|hit|hitting|"
        r"got\s+on|came\s+on)\b",
        tail,
    ) is not None


def _has_post_exposure_contradiction(lower: str, end: int) -> bool:
    """Reject a completed label contradicted by a later no-contact statement."""
    tail = lower[end:end + 160]
    return re.search(
        r"\b(?:no|not|never|without|didn't|did not|doesn't|does not|"
        r"isn't|is not|wasn't|was not|weren't|were not)\b.{0,56}"
        r"\b(?:touch(?:ed|es|ing)?|contact(?:ed|s|ing)?|"
        r"reach(?:ed|es|ing)?|land(?:ed|s|ing)?|hit|hitting)\b",
        tail,
    ) is not None or re.search(
        r"\b(?:missed|miss|fell short|didn't hit|did not hit|"
        r"didn't touch|did not touch|failed to hit|failed to touch)\b",
        tail,
    ) is not None or re.search(
        r"\b(?:nothing|no injury|no harm|no effect)\b"
        r"(?:\s+(?:really|actually))?\s+(?:happened|occurred|took place|resulted|"
        r"came\s+to\s+(?:me|myself|the\s+victim))\b",
        tail,
    ) is not None


def _has_past_exposure_after_modifier(lower: str, start: int) -> bool:
    """Distinguish fear/warning about a past throw from a future threat."""
    prefix = lower[max(0, start - 88):start]
    modifier = re.search(
        r"\b(?:warn(?:ed|ing|s)?|fear(?:ed|ing)?|afraid|scared)\b",
        prefix,
    )
    if modifier is None:
        return False
    tail = lower[modifier.end():start + 96]
    return re.search(
        r"\b(?:throw|threw|thrown|pour|poured|splash|splashed|"
        r"administer|administered|use|used|happened|occurred)\b",
        tail,
    ) is not None


def _has_future_or_planned_prefix(lower: str, start: int) -> bool:
    """Catch prospective action wording without treating it as completed."""
    clause_start = 0
    for marker in _CLAUSE_BREAKS:
        marker_start = lower.rfind(marker, 0, start)
        if marker_start >= 0:
            clause_start = max(clause_start, marker_start + len(marker))
    prefix = lower[max(clause_start, start - 72):start]
    return _FUTURE_OR_PLANNED_PREFIX_RE.search(prefix) is not None


def _has_positive_phrase(
    lower: str,
    phrases: tuple[str, ...],
    *,
    reject_threat_prefix: bool = False,
) -> bool:
    for phrase in phrases:
        start = lower.find(phrase)
        while start >= 0:
            end = start + len(phrase)
            if (
                not _has_negation_before(lower, start)
                and not _has_negation_after(lower, end)
                and not _has_post_exposure_uncertainty(lower, end)
                and not (
                    reject_threat_prefix
                    and _has_post_exposure_contradiction(lower, end)
                )
                and not (reject_threat_prefix and _has_threat_prefix(lower, start))
                and not (reject_threat_prefix and _has_attempt_prefix(lower, start))
                and not (
                    reject_threat_prefix
                    and _has_future_or_planned_prefix(lower, start)
                )
            ):
                return True
            start = lower.find(phrase, start + 1)
    return False


def _has_negation_after(lower: str, end: int) -> bool:
    """Catch labels negated after the label, e.g. ``attack did not happen``."""
    clause_end = len(lower)
    for marker in _CLAUSE_BREAKS:
        marker_end = lower.find(marker, end)
        if marker_end >= 0:
            clause_end = min(clause_end, marker_end)
    after = lower[end:clause_end]
    return re.search(
        rf"\b{_NEGATION_WORDS}\b(?:\s+\w+){{0,4}}\s+"
        r"(?:happen|happened|occur|occurred|take place|real|true|exist|"
        r"thrown|poured|splashed|administered|used|touch(?:ed)?|"
        r"contact(?:ed)?|reach(?:ed)?|land(?:ed)?|hit)\b",
        after,
    ) is not None


def _has_positive_regex(
    lower: str,
    pattern: str,
    *,
    reject_threat_prefix: bool = False,
) -> bool:
    # Evaluate each clause independently. A greedy regex must not let a
    # negated first clause swallow a later positive clause, e.g. "no acid was
    # thrown but chemical was thrown on me".
    clause_start = 0
    split_re = re.compile(r"[.?!;:,]|\b(?:but|however|although|and|or)\b")
    for split in split_re.finditer(lower):
        clause = lower[clause_start:split.start()]
        for match in re.finditer(pattern, clause):
            absolute_start = clause_start + match.start()
            absolute_end = clause_start + match.end()
            if (
                not _has_negation_before(lower, absolute_start)
                and not _has_negation_after(lower, absolute_end)
                and not _has_post_exposure_uncertainty(lower, absolute_end)
                and not (
                    reject_threat_prefix
                    and _has_post_exposure_contradiction(lower, absolute_end)
                )
                and not (reject_threat_prefix and _has_threat_prefix(lower, absolute_start))
                and not (reject_threat_prefix and _has_attempt_prefix(lower, absolute_start))
                and not (
                    reject_threat_prefix
                    and _has_future_or_planned_prefix(lower, absolute_start)
                )
            ):
                return True
        clause_start = split.end()
    for match in re.finditer(pattern, lower[clause_start:]):
        absolute_start = clause_start + match.start()
        absolute_end = clause_start + match.end()
        if (
            not _has_negation_before(lower, absolute_start)
            and not _has_negation_after(lower, absolute_end)
            and not _has_post_exposure_uncertainty(lower, absolute_end)
            and not (
                reject_threat_prefix
                and _has_post_exposure_contradiction(lower, absolute_end)
            )
            and not (reject_threat_prefix and _has_threat_prefix(lower, absolute_start))
            and not (reject_threat_prefix and _has_attempt_prefix(lower, absolute_start))
            and not (
                reject_threat_prefix
                and _has_future_or_planned_prefix(lower, absolute_start)
            )
        ):
            return True
    return False


def _has_failed_directed_acid_action(lower: str) -> bool:
    """Recognize a directed throw/attack that explicitly missed or made no contact."""
    for pattern in (_DIRECT_ACID_ACTION_RE, _DIRECT_ACID_ATTACK_RE):
        for match in pattern.finditer(lower):
            start, end = match.span()
            if (
                _has_negation_before(lower, start)
                or _has_negation_after(lower, end)
                or _has_threat_prefix(lower, start)
                or _has_future_or_planned_prefix(lower, start)
                or _has_post_exposure_uncertainty(lower, end)
            ):
                continue
            if _has_post_exposure_contradiction(lower, end):
                return True
    for phrase in _ACID_ATTACK_LABEL_PHRASES:
        start = lower.find(phrase)
        while start >= 0:
            end = start + len(phrase)
            if (
                not _has_negation_before(lower, start)
                and not _has_negation_after(lower, end)
                and _has_post_exposure_contradiction(lower, end)
            ):
                return True
            start = lower.find(phrase, start + 1)
    return False


def _has_uncertain_acid_event(lower: str) -> bool:
    uncertainty_markers = (
        *_UNCERTAINTY_WORDS,
        "fear",
        "feared",
        "afraid",
        "scared",
        "warned",
        "warning",
    )
    return (
        any(marker in lower for marker in uncertainty_markers)
        and _UNCERTAIN_ACID_EVENT_RE.search(lower) is not None
    )


def _has_possible_exposure_action(lower: str) -> bool:
    """Keep an uncertain post-action report in the safety context."""
    for match in _POSSIBLE_ACID_EXPOSURE_ACTION_RE.finditer(lower):
        start = match.start()
        if (
            not _has_negation_before(lower, start)
            and (
                not _has_threat_prefix(lower, start)
                or _has_past_exposure_after_modifier(lower, start)
            )
            and not _has_attempt_prefix(lower, start)
        ):
            return True
    return False


def _has_nonnegated_exposure_action(lower: str) -> bool:
    """Find a past exposure action while allowing uncertainty before it."""
    for match in _POSSIBLE_ACID_EXPOSURE_ACTION_RE.finditer(lower):
        clause_start = 0
        for marker in _CLAUSE_BREAKS:
            marker_start = lower.rfind(marker, 0, match.start())
            if marker_start >= 0:
                clause_start = max(clause_start, marker_start + len(marker))
        before = lower[clause_start:match.start()]
        if re.search(rf"\b{_NEGATION_WORDS}\b", before) is not None:
            continue
        return True
    return False


def _has_possible_attack_label(lower: str) -> bool:
    """Keep a reported attack label in intake safety context when contact is uncertain."""
    for phrase in _ACID_ATTACK_LABEL_PHRASES:
        start = lower.find(phrase)
        while start >= 0:
            end = start + len(phrase)
            if (
                not _has_negation_before(lower, start)
                and not _has_negation_after(lower, end)
                and not _has_attempt_prefix(lower, start)
            ):
                return True
            start = lower.find(phrase, start + 1)
    return False


def is_completed_acid_attack_query(query: str) -> bool:
    """Return true only when a positive completed exposure is present."""
    lower = _norm(query)
    for phrase in _ACID_COMPLETION_PHRASES:
        if _has_positive_phrase(lower, (phrase,), reject_threat_prefix=True):
            return True
    # A failed first action followed by a later confirmed contact is still a
    # completed exposure. The later clause must name the contact event so an
    # attempt-only report is not upgraded on the word "later" alone.
    if (
        _LATER_CONFIRMED_CONTACT_RE.search(lower) is not None
        and _has_nonnegated_exposure_action(lower)
    ):
        return True
    if _has_positive_regex(
        lower, _DIRECT_ACID_ACTION_RE.pattern, reject_threat_prefix=True
    ):
        return True
    if _has_positive_regex(
        lower, _DIRECT_ACID_ATTACK_RE.pattern, reject_threat_prefix=True
    ):
        return True
    # A threat followed by a positive later throwing event is a completed
    # incident even when the user omits the target in the second clause.
    for match in _POST_THREAT_COMPLETION_RE.finditer(lower):
        action_start = match.start()
        action_match = re.search(
            r"\b(?:threw|thrown|poured|splashed|administered|used)\b",
            lower[match.start():match.end()],
        )
        if action_match is not None:
            action_start = match.start() + action_match.start()
        if _has_negation_before(lower, action_start):
            continue
        if _has_attempt_prefix(lower, action_start):
            continue
        if _has_post_exposure_uncertainty(lower, action_start):
            continue
        if _has_post_exposure_contradiction(lower, action_start):
            continue
        if (
            _has_positive_phrase(lower, _ACID_ATTACK_LABEL_PHRASES)
            or _has_positive_regex(
                lower,
                r"\b(?:threat(?:en(?:ed|ing)?|s)?|dhamki)\b"
                r".{0,60}\b(?:acid|chemical)\b",
            )
        ):
            return True
    return False


def is_acid_threat_only_query(query: str) -> bool:
    """Return true for an acid/chemical threat with no completed exposure."""
    lower = _norm(query)
    if "acid" not in lower and "chemical" not in lower:
        return False
    threat_phrases = (
            "threatened to throw",
            "threatening to throw",
            "threatens to throw",
            "will throw acid",
            "throw acid on me",
            "throw chemical on me",
            "threatens an acid attack",
            "threatening an acid attack",
            "threatened an acid attack",
            "threatened me with an acid attack",
            "threatened acid attack",
            "threat of an acid attack",
            "threat of acid attack",
            "acid attack threat",
            "threatens acid attack",
            "would throw acid",
            "would throw chemical",
            "might throw acid",
            "might throw chemical",
            "could throw acid",
            "could throw chemical",
            "may throw acid",
            "may throw chemical",
            "will throw acid",
            "will throw chemical",
            "going to throw acid",
            "going to throw chemical",
            "about to throw acid",
            "about to throw chemical",
            "planning an acid attack",
            "planning a chemical attack",
            "plans an acid attack",
            "plans a chemical attack",
            "plan an acid attack",
            "plan a chemical attack",
            "planned an acid attack",
            "planned a chemical attack",
            "intends an acid attack",
            "intends a chemical attack",
            "intended an acid attack",
            "intended a chemical attack",
            "warned me about an acid attack",
            "warned me about a chemical attack",
            "warning of an acid attack",
            "warning of a chemical attack",
            "fear an acid attack",
            "fear a chemical attack",
            "feared an acid attack",
            "feared a chemical attack",
            "afraid of an acid attack",
            "afraid of a chemical attack",
            "scared of an acid attack",
            "scared of a chemical attack",
            "there may be an acid attack",
            "there may be a chemical attack",
            "may be an acid attack",
            "may be a chemical attack",
        )
    threat = _has_positive_phrase(lower, threat_phrases) or _has_positive_regex(
        lower,
        r"\b(?:threat(?:en(?:ed|ing)?|s)?|dhamki|warn(?:ed|ing|s)?|"
        r"fear(?:ed|ing)?|afraid|scared)\b.{0,60}\b(?:acid|chemical)\b"
        r"|\b(?:acid|chemical)\b.{0,60}\b(?:threat(?:en(?:ed|ing)?|s)?|"
        r"dhamki|warn(?:ed|ing|s)?|fear(?:ed|ing)?|afraid|scared)\b",
    )
    threat = (
        threat
        and not is_completed_acid_attack_query(lower)
        and not is_acid_attempt_query(lower)
    )
    if threat and re.search(
        r"\b(?:warn(?:ed|ing|s)?|fear(?:ed|ing)?|afraid|scared)\b.{0,80}"
        r"\b(?:acid|chemical)\b",
        lower,
    ):
        if any(
            _has_past_exposure_after_modifier(lower, match.start())
            for match in re.finditer(
                r"\b(?:throw|threw|thrown|pour|poured|splash|splashed|"
                r"administer|administered|use|used|happened|occurred)\b",
                lower,
            )
        ):
            threat = False
    return threat


def is_acid_attempt_query(query: str) -> bool:
    """Return true for an intentional attempted throw/attack without exposure."""
    lower = _norm(query)
    if "acid" not in lower and "chemical" not in lower:
        return False
    return (
        _has_positive_phrase(lower, _ACID_ATTEMPT_PHRASES)
        or _has_positive_regex(lower, _ACID_ATTEMPT_RE.pattern)
        or _has_failed_directed_acid_action(lower)
    )


def is_positive_acid_chemical_context(query: str) -> bool:
    """Return true only for a positive attack, threat, or personal exposure.

    Raw substring checks such as ``"acid" in query`` turn clarifications like
    "no one threw acid" into emergency routes. Keep polarity and the shared
    completion detector at the boundary used by routing, workflow selection,
    and source-gap enforcement.
    """
    lower = _norm(query)
    if (
        is_completed_acid_attack_query(lower)
        or is_acid_threat_only_query(lower)
        or is_acid_attempt_query(lower)
    ):
        return True
    return _has_positive_phrase(
        lower, (*_ACID_ATTACK_LABEL_PHRASES, *_ACID_EXPOSURE_PHRASES)
    ) or _has_positive_phrase(
        lower,
        (
            "might have thrown acid",
            "could have thrown acid",
            "may have thrown acid",
            "might have thrown chemical",
            "could have thrown chemical",
            "may have thrown chemical",
        ),
    ) or _has_positive_regex(lower, _MEDICAL_ACID_CONFIRMATION_RE.pattern) or _has_possible_exposure_action(lower) or _has_possible_attack_label(lower) or _has_uncertain_acid_event(lower)


def is_positive_intentional_acid_chemical_context(query: str) -> bool:
    """Return true only when an intentional attack/threat is positively stated."""
    lower = _norm(query)
    if (
        is_completed_acid_attack_query(lower)
        or is_acid_threat_only_query(lower)
        or is_acid_attempt_query(lower)
    ):
        return True
    if _has_positive_regex(lower, _DIRECT_ACID_ATTACK_RE.pattern):
        return True
    if _has_positive_regex(lower, _DIRECT_ACID_ACTION_RE.pattern):
        return True
    return _has_positive_phrase(
        lower,
        (
            "attacked", "attack", "assaulted", "assault",
        ),
    ) or is_acid_attempt_query(lower)


def is_acid_exposure_uncertain_query(query: str) -> bool:
    """Return true for a positive past exposure report without confirmed contact."""
    lower = _norm(query)
    if "acid" not in lower and "chemical" not in lower:
        return False
    if (
        not is_positive_acid_chemical_context(lower)
        or is_completed_acid_attack_query(lower)
        or is_acid_attempt_query(lower)
        or is_acid_threat_only_query(lower)
    ):
        return False
    uncertainty_markers = (*_UNCERTAINTY_WORDS, "fear", "feared", "afraid", "scared", "warned", "warning")
    uncertain_action = (
        _has_possible_exposure_action(lower)
        or _has_possible_attack_label(lower)
        or _has_uncertain_acid_event(lower)
    )
    if not uncertain_action:
        uncertain_action = _has_positive_phrase(
            lower,
            (
                "might have thrown acid",
                "could have thrown acid",
                "may have thrown acid",
                "might have thrown chemical",
                "could have thrown chemical",
                "may have thrown chemical",
            ),
        )
    return any(marker in lower for marker in uncertainty_markers) and uncertain_action


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


__all__ = [
    "is_acid_threat_only_query",
    "is_acid_attempt_query",
    "is_acid_exposure_uncertain_query",
    "is_completed_acid_attack_query",
    "is_positive_acid_chemical_context",
    "is_positive_intentional_acid_chemical_context",
]
