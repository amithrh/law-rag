from __future__ import annotations

from scripts.build_human_messy_eval import expected_routes, must_include_terms, trigger_matches


def test_trigger_matching_does_not_treat_first_as_fir():
    assert trigger_matches("fir refusal police", "fir")
    assert not trigger_matches("competitor registered my brand first", "fir")


def test_trademark_prior_user_metadata_is_not_police_fir():
    query = "competitor registered my brand name as trademark first what i do already using 6 years surat can i file case"

    routes = expected_routes(category="trademark", query=query, route_category="trademark_ip")
    terms = must_include_terms(
        category="trademark",
        query=query,
        act_hint="Trade Marks Act 1999 section 34 prior user and section 57 rectification",
    )

    assert "trademark_ip" in routes
    assert "police_fir" not in routes
    assert "arrest_custody_safeguard" not in routes
    assert {"trademark", "prior user", "rectification", "registry", "passing off"} <= set(terms)


def test_common_hard_prompts_get_scenario_specific_must_terms():
    noncompete_terms = set(must_include_terms(
        category="employment",
        query="non compete clause in my employment contract for 2 years enforceable in india",
        act_hint="Indian Contract Act section 27",
    ))
    assert {"non-compete", "section 27", "contract", "employer legal notice"} <= noncompete_terms

    silicosis_terms = set(must_include_terms(
        category="construction_accident",
        query="rajasthan stone quarry silicosis lungs gone cough 6 months what to do",
        act_hint="Employees Compensation Act occupational disease",
    ))
    assert {"silicosis", "quarry", "occupational disease", "compensation", "medical"} <= silicosis_terms


def test_must_terms_do_not_leak_from_incidental_query_words():
    pds_terms = set(must_include_terms(
        category="pds_portability",
        query="ration card west bengal not working in chennai shop no rice for family one nation one card",
        act_hint="NFSA 2013 s.10 + ONORC scheme",
    ))
    assert {"ration", "nfsa", "dealer", "grievance"} <= pds_terms
    assert {"family court", "protection officer", "divorce"}.isdisjoint(pds_terms)

    land_terms = set(must_include_terms(
        category="land_acquisition",
        query="my land taken for highway 4 years back compensation still not received",
        act_hint="Right to Fair Compensation and Transparency in Land Acquisition Act 2013",
    ))
    assert {"land acquisition", "compensation", "award", "authority"} <= land_terms
    assert {"sale deed", "partition", "title"}.isdisjoint(land_terms)

    mental_health_terms = set(must_include_terms(
        category="mental_health",
        query="my brother mentally ill family kept him in chains how to admit in hospital legally",
        act_hint="Mental Healthcare Act 2017",
    ))
    assert {"mental health", "hospital", "board", "supported admission"} <= mental_health_terms
    assert {"consumer", "district commission", "divorce"}.isdisjoint(mental_health_terms)


def test_common_procedure_prompts_get_precise_must_terms():
    name_change_terms = set(must_include_terms(
        category="family",
        query="how to legally change my surname after marriage do i need to publish in gazette",
        act_hint="Gazette notification process",
    ))
    assert {"gazette", "affidavit", "newspaper", "name change", "documents"} <= name_change_terms
    assert {"family court", "divorce"}.isdisjoint(name_change_terms)

    default_bail_terms = set(must_include_terms(
        category="default_bail",
        query="brother arrested 6 months ago no chargesheet ipc 420 cheating case when bail",
        act_hint="BNSS/CrPC default bail",
    ))
    assert {"default bail", "chargesheet", "remand", "deadline", "court"} <= default_bail_terms
