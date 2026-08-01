from apps.api.local_authority import (
    has_explicit_municipal_authority_context,
    has_qualified_city_corporation,
    has_private_vendor_actor_context,
    has_specific_hawker_corporation_context,
)


def test_qualified_city_corporation_accepts_municipal_identity():
    assert has_qualified_city_corporation("Vadodara Corporation sealed our shop")


def test_qualified_city_corporation_accepts_owner_says_wording():
    assert has_qualified_city_corporation("my owner says Vadodara Corporation sealed my shop")


def test_qualified_city_corporation_rejects_private_company_wording():
    assert not has_qualified_city_corporation("private Vadodara Corporation closed my hotel")
    assert not has_qualified_city_corporation("Vadodara Corporation Ltd. closed my restaurant")
    assert not has_qualified_city_corporation(
        "the company that owns the Vadodara Corporation hotel issued closure notice"
    )


def test_qualified_city_corporation_rejects_unknown_or_bare_corporation():
    assert not has_qualified_city_corporation("the corporation closed my shop")
    assert not has_qualified_city_corporation("a private company closed my shop")


def test_qualified_city_corporation_can_check_a_specific_city():
    query = "Vadodara Corporation sealed our shop"
    assert has_qualified_city_corporation(query, city="vadodara")
    assert not has_qualified_city_corporation(query, city="ahmedabad")


def test_company_owner_wording_does_not_hide_a_real_municipal_actor():
    assert has_qualified_city_corporation(
        "my company owns a shop and Vadodara corporation sealed it"
    )


def test_explicit_municipal_context_rejects_private_corporation_phrasing():
    assert has_explicit_municipal_authority_context("BMC sealed my shop")
    assert has_explicit_municipal_authority_context("local health authority closed my hotel")
    assert has_explicit_municipal_authority_context(
        "my private restaurant was sealed by the local authority"
    )
    assert has_explicit_municipal_authority_context(
        "my private shop was sealed by Vadodara corporation"
    )
    assert not has_explicit_municipal_authority_context("private city corporation sealed my shop")
    assert not has_explicit_municipal_authority_context(
        "a private Vadodara municipal corporation Ltd. closed my shop"
    )
    assert not has_explicit_municipal_authority_context(
        "the entity named Vadodara Corporation sealed my shop"
    )
    assert not has_explicit_municipal_authority_context(
        "Vadodara Corporation is my company and sealed my shop"
    )


def test_health_inspector_variants_are_public_only_when_the_actor_is_municipal():
    assert not has_explicit_municipal_authority_context(
        "health officer sealed my restaurant after hygiene inspection"
    )
    assert not has_explicit_municipal_authority_context(
        "health inspector closed my hotel after food inspection"
    )
    assert has_explicit_municipal_authority_context(
        "local health inspector closed my hotel after hygiene inspection"
    )
    assert has_explicit_municipal_authority_context(
        "municipal health officer sealed my restaurant"
    )


def test_specific_hawker_corporation_context_is_shared_and_private_safe():
    public_query = "hawker license pending but corporation removed my stall before hearing"
    assert has_specific_hawker_corporation_context(public_query)
    assert not has_private_vendor_actor_context(public_query)
    assert not has_specific_hawker_corporation_context(
        "company named Vadodara Corporation removed my stall after hawker license pending"
    )
    assert not has_specific_hawker_corporation_context(
        "private Vadodara Corporation removed my stall after hawker license pending"
    )
