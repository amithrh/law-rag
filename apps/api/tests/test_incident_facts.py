from apps.api.incident_facts import (
    is_acid_attempt_query,
    is_acid_exposure_uncertain_query,
    is_acid_threat_only_query,
    is_completed_acid_attack_query,
    is_positive_acid_chemical_context,
    is_positive_intentional_acid_chemical_context,
)


def test_completed_chemical_exposure_variants_are_shared_across_layers():
    for query in (
        "he poured a chemical on my face",
        "chemical was used to attack me",
        "she splashed acid on my face",
        "my mother in law threatened acid attack but acid was later thrown",
        "no acid was thrown but chemical was thrown on me",
    ):
        assert is_completed_acid_attack_query(query), query
        assert not is_acid_threat_only_query(query), query


def test_negated_and_threat_only_facts_do_not_become_completed_attacks():
    for query in (
        "I was not attacked with acid",
        "no one threw acid on me",
        "nobody threw acid at me",
        "without being attacked with acid",
        "my mother in law threatened an acid attack but no acid was thrown",
    ):
        assert not is_completed_acid_attack_query(query), query

    assert is_acid_threat_only_query("my mother in law threatened me with an acid attack")


def test_positive_context_respects_negation_and_later_positive_clause():
    assert not is_positive_acid_chemical_context("no one threw acid on me")
    assert not is_positive_acid_chemical_context("the acid attack did not happen")
    assert is_positive_acid_chemical_context("no acid was thrown but chemical was thrown on me")
    assert is_positive_acid_chemical_context("chemical injury to my face")


def test_adversarial_negation_and_attack_variants_are_polarity_safe():
    assert is_completed_acid_attack_query("no acid was thrown and chemical was thrown on me")
    assert is_completed_acid_attack_query(
        "my husband did not throw acid and my mother in law later threw acid on me"
    )
    assert not is_completed_acid_attack_query("I didn't see whether acid was thrown at me")
    assert not is_acid_threat_only_query("no one threatened me with acid")
    for query in (
        "assaulted me with acid",
        "I was assaulted with a chemical",
        "attacked with chemical",
    ):
        assert is_completed_acid_attack_query(query), query


def test_future_or_planned_acid_language_is_a_threat_not_a_completed_attack():
    for query in (
        "he told me he would throw acid on me",
        "they are planning an acid attack on me",
        "he will throw chemical on my face",
        "they are going to throw acid at me",
    ):
        assert not is_completed_acid_attack_query(query), query
        assert is_acid_threat_only_query(query), query


def test_uncertain_past_acid_exposure_still_enters_the_safety_context():
    for query in (
        "he might have thrown acid on me",
        "he could have thrown chemical on my face",
    ):
        assert not is_completed_acid_attack_query(query), query
        assert is_positive_acid_chemical_context(query), query


def test_mixed_threat_then_later_throw_stays_a_completed_attack():
    for query in (
        "threatened an acid attack and later threw acid",
        "threatened me with chemical and then poured chemical",
    ):
        assert is_completed_acid_attack_query(query), query
        assert not is_acid_threat_only_query(query), query


def test_attempted_or_uncertain_exposure_is_safe_context_but_not_completed_attack():
    for query in (
        "he attempted to throw acid on me",
        "he tried to throw acid at me but missed",
        "he threw acid at me but it missed",
        "he threw acid at me but acid did not touch me",
        "acid was thrown at me but no contact occurred",
        "he threw acid at me but it didn’t touch me",
    ):
        assert is_acid_attempt_query(query), query
        assert not is_completed_acid_attack_query(query), query
        assert not is_acid_threat_only_query(query), query
        assert is_positive_acid_chemical_context(query), query
        assert is_positive_intentional_acid_chemical_context(query), query

    for query in (
        "he threw acid but I am not sure if it touched me",
        "acid attack on me but I am not sure if it touched me",
        "he threw acid at me but acid did not touch me",
        "acid was thrown at me but no contact occurred",
        "he threw acid at me but perhaps it did not touch me",
    ):
        assert not is_completed_acid_attack_query(query), query
        assert is_positive_acid_chemical_context(query), query

    for query in (
        "I didn’t see whether acid was thrown at me",
        "he threw acid at me but I couldn’t confirm contact",
        "he might have thrown acid on me",
        "I fear he threw acid on me",
    ):
        assert not is_completed_acid_attack_query(query), query
        assert is_acid_exposure_uncertain_query(query), query

    for query in (
        "I fear he threw acid on me",
        "I am afraid acid was thrown at me",
        "she warned me that acid was thrown on me",
    ):
        assert not is_completed_acid_attack_query(query), query
        assert not is_acid_threat_only_query(query), query
        assert is_positive_acid_chemical_context(query), query


def test_warning_fear_and_planning_language_is_threat_only():
    for query in (
        "he planned an acid attack",
        "he intends an acid attack",
        "they warned me about an acid attack on me",
        "I fear an acid attack on me",
        "there may be an acid attack on me",
    ):
        assert not is_completed_acid_attack_query(query), query
        assert is_acid_threat_only_query(query), query
        assert is_positive_acid_chemical_context(query), query


def test_natural_completed_acid_exposure_variants_are_completed():
    for query in (
        "acid was poured over me",
        "acid was splashed over my face",
        "she used acid to attack me",
        "I suffered acid burns",
    ):
        assert is_completed_acid_attack_query(query), query
        assert not is_acid_threat_only_query(query), query


def test_attempt_then_completed_exposure_prefers_completed_fact():
    query = "he tried to throw acid but then poured acid on me"
    assert is_acid_attempt_query(query)
    assert is_completed_acid_attack_query(query)
    assert not is_acid_threat_only_query(query)


def test_missed_throw_is_not_completed_exposure():
    query = "he threw acid at me but it missed"
    assert not is_completed_acid_attack_query(query)
    assert is_positive_acid_chemical_context(query)


def test_later_confirmed_contact_promotes_mixed_event_to_completion():
    for query in (
        "he threw acid at me but it missed, then it hit me",
        "he might have thrown acid but later it hit me",
    ):
        assert is_completed_acid_attack_query(query), query


def test_nothing_happened_does_not_count_as_completed_acid_attack():
    for query in (
        "he threw acid at me but nothing happened",
        "he threw acid at me but nothing actually happened",
        "he threw acid at me but no harm came to me",
    ):
        assert not is_completed_acid_attack_query(query), query


def test_later_contact_must_name_a_person_not_a_wall_or_ground():
    for query in (
        "he threw acid at me but it missed, then it hit the wall",
        "he might have thrown acid but later it hit the ground",
    ):
        assert not is_completed_acid_attack_query(query), query
