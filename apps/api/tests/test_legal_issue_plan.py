from __future__ import annotations

from apps.api.legal_issue_plan import (
    RetrievalSourcePlan,
    _augment_owner_retrieval_sources,
    _description_source_pack_id,
    build_matter_plan,
    plan_owned_answer_route,
)
from apps.api.matter_router import MatterRoute, route_matter


def _plan(query: str):
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    return route, plan.to_event()


def test_legal_issue_plan_none_for_off_topic():
    query = "who will win the cricket match tomorrow"
    route = route_matter(query)

    assert route.category == "off_topic"
    assert build_matter_plan(query, route) is None


def test_scst_targeted_violence_binds_legacy_authorities_to_legacy_packs():
    _, plan = _plan("upper caste people beat me on 2023-01-02 what action can i take")

    entries = {
        entry["act"]: entry
        for entry in plan["authority_ledger"]
        if entry["act"] in {
            "Code of Criminal Procedure 1973",
            "Indian Penal Code 1860",
        }
    }
    assert entries["Code of Criminal Procedure 1973"]["source_pack_id"] == (
        "crpc_1973_scst_atrocity_fir"
    )
    assert entries["Indian Penal Code 1860"]["source_pack_id"] == (
        "ipc_1860_scst_atrocity_threat_hurt"
    )


def test_article_pack_binding_rejects_compound_slash_and_ampersand_descriptions():
    constitution = RetrievalSourcePlan(
        source_pack_id="constitution_article_21",
        title_patterns=["Constitution of India"],
        search_query="Constitution Article 21",
        doc_ids=["constitution-india"],
        anchor_patterns=["/sec-21"],
        source_types=["bare_act"],
    )

    assert _description_source_pack_id(
        "Constitution Articles 21/22 liberty safeguards",
        [constitution],
    ) is None
    assert _description_source_pack_id(
        "Constitution Article 21 & 22 liberty safeguards",
        [constitution],
    ) is None
    assert _description_source_pack_id(
        "Article 21 personal liberty safeguard",
        [constitution],
    ) == "constitution_article_21"


def test_legal_issue_plan_consumer_customer_role_and_authorities():
    route, plan = _plan("online order arrived broken what to do")

    assert route.category == "consumer"
    assert plan["schema_version"] == 2
    assert plan["plan_id"].startswith("matter_plan_v2_")
    assert plan["primary_issue"] == "consumer"
    assert plan["user_role"] == "consumer_or_customer"
    assert plan["desired_outcome"] in {"complaint_or_grievance", "refund_or_compensation"}
    assert plan["authority_ledger"][0]["act"] == "Consumer Protection Act 2019"
    assert plan["authority_ledger"][0]["authority_id"].startswith("authority_")
    assert plan["authority_ledger"][0]["source_pack_id"]
    assert plan["authority_ledger"][0]["priority"] == "must_cite"
    assert plan["retrieval_sources"]


def test_lok_adalat_challenge_gets_a_distinct_answer_owner():
    query = "Can I challenge a traffic ticket settled in Lok Adalat?"
    route = route_matter(query)

    owner = plan_owned_answer_route(query, route)

    assert route.category == "lok_adalat_award_challenge"
    assert owner is not None
    assert owner.scenario_id == "lok_adalat_award_challenge"
    assert owner.owner_token == "common_workflow_contracts:lok_adalat_award_challenge"


def test_pan_aadhaar_record_correction_binds_its_income_tax_source_pack():
    route, plan = _plan("my PAN and Aadhaar mismatch")

    assert route.label == "PAN/Aadhaar mismatch / identity linking"
    income_tax = next(
        entry
        for entry in plan["authority_ledger"]
        if entry["act"] == "Income-tax Act 1961"
    )
    assert income_tax["source_pack_id"] == "income_tax_pan_1961"
    assert income_tax["must_cite"] is True
    assert income_tax["section"] == "Section 139A"


def test_pan_aadhaar_linking_binds_section_139aa_to_its_income_tax_source_pack():
    _route, plan = _plan("PAN Aadhaar linking failed and bank KYC rejected")

    income_tax = next(
        entry
        for entry in plan["authority_ledger"]
        if entry["act"] == "Income-tax Act 1961"
    )
    assert income_tax["source_pack_id"] == "income_tax_pan_1961"
    assert income_tax["must_cite"] is True
    assert income_tax["section"] == "Section 139AA"
    assert income_tax["required_anchor_patterns"] == ["/sec-139aa"]
    income_tax_pack = next(
        source
        for source in plan["retrieval_sources"]
        if source["source_pack_id"] == "income_tax_pan_1961"
    )
    assert income_tax_pack["doc_ids"] == ["income-tax-1961-official"]


def test_owned_contract_document_ids_constrain_all_duplicate_pack_variants():
    query = "PAN Aadhaar linking failed and bank KYC rejected"
    route = route_matter(query)
    owner = plan_owned_answer_route(query, route)
    assert owner is not None
    sources = [
        RetrievalSourcePlan(
            source_pack_id="income_tax_pan_1961",
            title_patterns=["Income-tax Act 1961"],
            search_query="income tax PAN Aadhaar",
            doc_ids=["income-tax-1961"],
            anchor_patterns=["/sec-139aa"],
        ),
        RetrievalSourcePlan(
            source_pack_id="income_tax_pan_1961",
            title_patterns=["Income-tax Act 1961"],
            search_query="income tax PAN Aadhaar alternate",
            doc_ids=["income-tax-1961-other"],
            anchor_patterns=["/sec-139aa"],
        ),
    ]

    augmented = _augment_owner_retrieval_sources(owner, sources, route)

    assert [source.doc_ids for source in augmented] == [
        ["income-tax-1961-official"],
        ["income-tax-1961-official"],
    ]


def test_matter_plan_v2_identity_and_retrieval_policy_are_deterministic():
    query = "online order arrived broken what to do"
    route = route_matter(query)
    first = build_matter_plan(query, route)
    second = build_matter_plan(query, route)

    assert first is not None
    assert second is not None
    assert first.plan_id == second.plan_id
    assert first.retrieval_sources == second.retrieval_sources
    assert all(entry.authority_id for entry in first.authority_ledger)
    assert all(source.source_pack_id for source in first.retrieval_sources)

    punctuated = build_matter_plan(f"  {query.upper()}!!! ", route_matter(f"{query}!!!"))
    assert punctuated is not None
    assert first.plan_id == punctuated.plan_id


def test_secondary_issue_matching_does_not_treat_parents_as_rent():
    query = "my mother in law is threatening to throw acid if I do not get more money from my parents"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert plan is not None
    assert "rent_arrears" not in plan.secondary_issues
    assert "eviction_or_possession" not in plan.secondary_issues

    tenant_plan = build_matter_plan(
        "my tenant has not paid rent and is not vacating",
        route_matter("my tenant has not paid rent and is not vacating"),
    )
    assert tenant_plan is not None
    assert "rent_arrears" in tenant_plan.secondary_issues
    assert "eviction_or_possession" in tenant_plan.secondary_issues

    plural_tenant_plan = build_matter_plan(
        "my tenants have not paid rent and refuse to leave",
        route_matter("my tenants have not paid rent and refuse to leave"),
    )
    assert plural_tenant_plan is not None
    assert "rent_arrears" in plural_tenant_plan.secondary_issues
    assert "eviction_or_possession" in plural_tenant_plan.secondary_issues


def test_authority_identity_is_canonical_across_routes():
    _, product = _plan("online order arrived broken what to do")
    _, medical = _plan("doctor operated wrong leg in hospital what can we do")

    product_cpa = next(
        entry for entry in product["authority_ledger"]
        if entry["act"] == "Consumer Protection Act 2019"
    )
    medical_cpa = next(
        entry for entry in medical["authority_ledger"]
        if entry["act"] == "Consumer Protection Act 2019"
    )
    assert product_cpa["authority_id"] == medical_cpa["authority_id"]
    assert product_cpa["identity_status"] == "provisional"


def test_authority_pack_binding_never_guesses_neighboring_law():
    _, pesa = _plan("sand mining lease given without gram sabha consent in scheduled area")
    pesa_entry = next(entry for entry in pesa["authority_ledger"] if entry["act"] == "PESA Act 1996")
    assert pesa_entry["source_pack_id"] == "pesa_1996"

    _, caste = _plan("office rejected my ST certificate saying not local resident what appeal")
    constitution = next(
        entry for entry in caste["authority_ledger"]
        if entry["act"] == "Constitution of India"
    )
    rti = next(
        entry for entry in caste["authority_ledger"]
        if entry["act"] == "Right to Information Act 2005"
    )
    state_rules = next(
        entry for entry in caste["authority_ledger"]
        if entry["note"] == "plan_owned_context_authority"
    )
    assert constitution["source_pack_id"] == "constitution_article_341_342"
    assert rti["source_pack_id"] == "rti_2005_certificate_record_request"
    assert state_rules["source_pack_id"] is None

    _, tenancy = _plan("my tenant is not vacating house and not paying rent in Pune")
    provisional_tenancy = [
        entry for entry in tenancy["authority_ledger"]
        if entry["identity_status"] == "provisional"
    ]
    assert provisional_tenancy
    assert any(entry["source_pack_id"] is None for entry in provisional_tenancy)

    _, senior = _plan("my senior citizen father gifted flat to daughter now she is not maintaining him")
    state_tribunal = next(
        entry for entry in senior["authority_ledger"]
        if entry["identity_status"] == "provisional" and entry["act"] is None
    )
    assert state_tribunal["source_pack_id"] is None


def test_authority_pack_binding_rejects_section_only_and_yearless_guesses():
    from apps.api.legal_issue_plan import (
        AuthorityLedgerEntry,
        RetrievalSourcePlan,
        _bind_authority_policy,
    )

    packs = [
        RetrievalSourcePlan(
            source_pack_id="senior_citizens_2007",
            title_patterns=["Maintenance and Welfare of Parents and Senior Citizens Act 2007"],
            search_query="senior citizens section 23",
            anchor_patterns=["/sec-23"],
        ),
        RetrievalSourcePlan(
            source_pack_id="consumer_protection_2019",
            title_patterns=["Consumer Protection Act 2019"],
            search_query="consumer protection",
        ),
        RetrievalSourcePlan(
            source_pack_id="pesa_1996",
            title_patterns=["Panchayats (Extension to the Scheduled Areas) Act 1996"],
            search_query="PESA scheduled areas",
        ),
    ]
    (
        unknown,
        yearless,
        unknown_year,
        state_rules,
        canonical,
        punctuated,
        unknown_pesa,
        state_pesa,
        negated_pesa,
    ) = _bind_authority_policy(
        [
            AuthorityLedgerEntry(
                source="Unknown Act Section 23",
                act="Unknown Act",
                section="Section 23",
            ),
            AuthorityLedgerEntry(
                source="Consumer Protection Act",
                act="Consumer Protection Act",
            ),
            AuthorityLedgerEntry(source="Unknown Act 2020", act="Unknown Act 2020"),
            AuthorityLedgerEntry(source="State Rules 2020", act="State Rules 2020"),
            AuthorityLedgerEntry(
                source="Consumer Protection Act 2019 Section 2",
                act="Consumer Protection Act 2019",
                section="Section 2",
            ),
            AuthorityLedgerEntry(
                source="Consumer Protection Act, 2019 Section 2",
                act="Consumer Protection Act, 2019",
                section="Section 2",
            ),
            AuthorityLedgerEntry(
                source="Unknown Act 2020 read with PESA",
                act="Unknown Act 2020",
            ),
            AuthorityLedgerEntry(
                source="State Rules 2020 made under PESA",
                act="State Rules 2020",
            ),
            AuthorityLedgerEntry(
                source="Unknown Act Section 23, not PESA",
                act="Unknown Act",
                section="Section 23",
            ),
        ],
        packs,
    )

    assert unknown.identity_status == "provisional"
    assert unknown.source_pack_id is None
    assert yearless.identity_status == "provisional"
    assert yearless.source_pack_id is None
    assert unknown_year.identity_status == "provisional"
    assert unknown_year.source_pack_id is None
    assert state_rules.identity_status == "provisional"
    assert state_rules.source_pack_id is None
    assert canonical.identity_status == "canonical"
    assert punctuated.identity_status == "canonical"
    assert canonical.authority_id == punctuated.authority_id
    for mixed in (unknown_pesa, state_pesa, negated_pesa):
        assert mixed.identity_status == "provisional"
        assert mixed.source_pack_id is None


def test_named_year_matched_act_binds_only_a_unique_reviewed_pack():
    cases = (
        (
            "gst department issued show cause notice for mismatch in 2A and 3B",
            "CGST Act 2017",
            "cgst_2017",
        ),
        (
            "fish market vendor cochin license panchayat only kerala municipal saying pay fine",
            "Street Vendors Act 2014",
            "street_vendors_2014",
        ),
        (
            "filed case on msme samadhan portal against private ltd buyer how long it takes",
            "MSMED Act 2006",
            "msmed_2006",
        ),
    )
    for query, act, source_pack_id in cases:
        _, plan = _plan(query)
        entry = next(entry for entry in plan["authority_ledger"] if entry["act"] == act)
        assert entry["source_pack_id"] == source_pack_id


def test_contextual_route_requirements_bind_existing_reviewed_packs():
    cases = (
        (
            "factory owner not paid wages 3 months 25 workers we don't have written contract",
            "Code on Wages 2019 / Payment of Wages law for wage-rights, wage-authority, and claims",
            "code_on_wages_2019",
        ),
        (
            "wife and child living separately I want custody of son aged 6",
            "Guardians and Wards Act / family law custody principles",
            "guardians_wards_1890",
        ),
        (
            "private hospital in noida overcharged 4 lakh for father icu now denying refund",
            "Clinical Establishments Act / state clinical-establishment rules where hospital records, billing, or standards are involved",
            "clinical_establishments_2010",
        ),
    )
    for query, source, pack_id in cases:
        plan = build_matter_plan(query, route_matter(query))
        assert plan is not None
        entry = next(item for item in plan.authority_ledger if item.source == source)
        assert entry.source_pack_id == pack_id


def test_curated_yearless_route_names_bind_only_to_their_reviewed_instrument():
    cases = (
        (
            "what to do father transferred flat to son before death now daughter wants share is gift valid is this legal",
            "Transfer of Property Act",
            "transfer_property_1882",
        ),
        (
            "can u tell demand notice form 3 ibc sent buyer disputing the invoice now what happens to my section 9 filing what can i do",
            "NCLT Rules / IBC application forms",
            "nclt_rules_2016",
        ),
        (
            "need help, got designated officer notice fr misbranding masala packet improvement notice 14 days what next",
            "FSSAI Licensing and Registration Regulations",
            "fssai_licensing_2011",
        ),
    )
    for query, source, pack_id in cases:
        plan = build_matter_plan(query, route_matter(query))
        assert plan is not None
        entry = next(item for item in plan.authority_ledger if item.source == source)
        assert entry.source_pack_id == pack_id


def test_reviewed_sibling_selector_binds_specific_quashing_and_access_packs():
    false_fir = build_matter_plan(
        "need help, thekedar made fake theft fir against me after i asked wages now police calling station what next",
        route_matter("need help, thekedar made fake theft fir against me after i asked wages now police calling station what next"),
    )
    assert false_fir is not None
    bnss = next(
        item for item in false_fir.authority_ledger
        if item.act == "Bharatiya Nagarik Suraksha Sanhita 2023" and item.section == "Section 528"
    )
    assert bnss.source_pack_id == "bnss_2023_quashing_false_fir_retaliation"

    access_query = "pls tell village headman saying my caste cannot enter temple in festival dindori what rights need lawyer or police"
    access = build_matter_plan(access_query, route_matter(access_query))
    assert access is not None
    civil_rights = next(
        item for item in access.authority_ledger
        if item.act == "Protection of Civil Rights Act 1955"
    )
    assert civil_rights.source_pack_id == "protection_civil_rights_1955_religious_access"


def test_contextual_binding_does_not_choose_bocw_cess_for_generic_bocw_requirement():
    query = "thekedar gave 8 of us same name on register only 2 names real cheating bocw he gets cess"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    entry = next(
        item
        for item in plan.authority_ledger
        if item.source == "Building and Other Construction Workers Act 1996 registration and welfare-board provisions"
    )
    assert entry.source_pack_id == "bocw_1996"
    assert entry.source_pack_id != "bocw_cess_1996"

    # Both BOCW packs carry the same Act family but cover different legal
    # instruments. The reviewed selector should choose the welfare/registration
    # pack for worker-registration facts, never the cess pack.
    _, bocw = _plan(
        "thekedar gave 8 of us same name on register only 2 names real cheating bocw he gets cess"
    )
    bocw_entry = next(
        entry
        for entry in bocw["authority_ledger"]
        if entry["act"] == "Building and Other Construction Workers Act 1996"
    )
    assert bocw_entry["source_pack_id"] == "bocw_1996"
    assert bocw_entry["source_pack_id"] != "bocw_cess_1996"


def test_acronym_binding_requires_full_title_and_year_equivalence():
    from apps.api.legal_issue_plan import (
        AuthorityLedgerEntry,
        RetrievalSourcePlan,
        _bind_authority_policy,
    )

    def bind(act: str, pack_id: str, title: str):
        return _bind_authority_policy(
            [AuthorityLedgerEntry(source=act, act=act)],
            [
                RetrievalSourcePlan(
                    source_pack_id=pack_id,
                    title_patterns=[title],
                    search_query="",
                )
            ],
        )[0]

    assert bind(
        "CGST Act",
        "cgst_2017",
        "Central Goods and Services Tax Act 2017",
    ).source_pack_id is None
    assert bind(
        "CGST Act 2017",
        "cgst_rules_2017",
        "Central Goods and Services Tax Rules 2017",
    ).source_pack_id is None
    assert bind(
        "RBI Act",
        "rbi_integrated_ombudsman_2021",
        "Reserve Bank - Integrated Ombudsman Scheme 2021",
    ).source_pack_id is None
    for act, pack_id, title in (
        ("NI Rules 1881", "ni_act_1881", "Negotiable Instruments Act 1881"),
        ("CGST Rules 2017", "cgst_2017", "Central Goods and Services Tax Act 2017"),
        ("BNS Rules 2023", "bns_2023", "Bharatiya Nyaya Sanhita 2023"),
        ("PMLA Rules 2002", "pmla_2002", "Prevention of Money Laundering Act 2002"),
    ):
        assert bind(act, pack_id, title).source_pack_id is None

    for act, pack_id, title in (
        ("PESA Act 1996", "pesa_1996", "Panchayats Development Act 1996"),
        ("PESA Act 1996", "pesa_1996", "Panchayati Extension to the Scheduled Areas Act 1996"),
        ("RERA Act 2016", "rera_2016", "Real Estate Development Act 2016"),
        (
            "MGNREGA Act 2005",
            "mgnrega_2005",
            "National Rural Employment Guarantee Act 2005",
        ),
    ):
        assert bind(act, pack_id, title).source_pack_id is None


def test_duplicate_source_packs_do_not_change_canonical_authority_identity():
    from dataclasses import replace

    from apps.api.legal_issue_plan import (
        AuthorityLedgerEntry,
        RetrievalSourcePlan,
        _bind_authority_policy,
    )

    authority = AuthorityLedgerEntry(
        source="Right to Information Act 2005 Section 6",
        act="Right to Information Act 2005",
        section="Section 6",
    )
    first = RetrievalSourcePlan(
        source_pack_id="rti_2005_application",
        title_patterns=["Right to Information Act 2005"],
        search_query="RTI application section 6",
        anchor_patterns=["/sec-6"],
    )
    duplicate = RetrievalSourcePlan(
        source_pack_id="rti_2005_certificate_record_request",
        title_patterns=["Right to Information Act 2005"],
        search_query="RTI certificate record section 6",
        anchor_patterns=["/sec-6"],
        priority=2.0,
    )

    single = _bind_authority_policy([authority], [first])[0]
    ambiguous = _bind_authority_policy([authority], [first, duplicate])[0]
    empty_binding = _bind_authority_policy(
        [replace(authority, source_pack_id="")], [first, duplicate]
    )[0]

    assert single.source_pack_id == first.source_pack_id
    assert ambiguous.source_pack_id is None
    assert empty_binding.source_pack_id == ""
    assert single.identity_status == ambiguous.identity_status == "canonical"
    assert single.authority_id == ambiguous.authority_id


def test_passage_authority_ids_require_act_and_section_alignment():
    from apps.api.legal_issue_plan import authority_ids_for_passage

    query = "office rejected my ST certificate saying not local resident what appeal"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    article_342 = next(
        entry for entry in plan.authority_ledger
        if entry.act == "Constitution of India" and entry.section == "Article 342"
    )

    matched = authority_ids_for_passage(
        plan,
        title="Constitution of India",
        anchor="constitution-india/sec-342",
        source_pack_id="constitution_article_341_342",
        source_type="bare_act",
    )
    wrong_section = authority_ids_for_passage(
        plan,
        title="Constitution of India",
        anchor="constitution-india/sec-341",
        source_pack_id="constitution_article_341_342",
        source_type="bare_act",
    )
    wrong_act = authority_ids_for_passage(
        plan,
        title="Consumer Protection Act 2019",
        anchor="consumer-protection-2019/sec-342",
        source_type="bare_act",
    )

    assert matched == [article_342.authority_id]
    assert wrong_section == []
    assert wrong_act == []


def test_split_section_anchor_uses_passage_heading_without_matching_neighbor():
    from apps.api.legal_issue_plan import authority_ids_for_passage

    query = "my customer gave me a cheque and it bounced, what is the deadline to send notice"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    section_142 = next(
        entry for entry in plan.authority_ledger
        if entry.act == "Negotiable Instruments Act 1881" and entry.section == "Section 142"
    )

    split_section = authority_ids_for_passage(
        plan,
        title="Negotiable Instruments Act 1881",
        anchor="negotiable-instruments-1881/sec-142-a",
        text="Negotiable Instruments Act 1881, Section 142\n142. Cognizance of offences.",
        source_pack_id="ni_act_1881",
        source_type="bare_act",
    )
    neighboring_section = authority_ids_for_passage(
        plan,
        title="Negotiable Instruments Act 1881",
        anchor="negotiable-instruments-1881/sec-142-a",
        text="Negotiable Instruments Act 1881, Section 142A\n142A. Validation for transfer of pending cases.",
        source_pack_id="ni_act_1881",
        source_type="bare_act",
    )

    assert split_section == [section_142.authority_id]
    assert neighboring_section == []


def test_title_only_act_identity_is_provisional_without_registry_or_section():
    query = "my Christian father died without a will who inherits his house"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    indian_succession = next(
        entry for entry in plan.authority_ledger
        if entry.act == "Indian Succession Act 1925"
    )
    assert indian_succession.section is None
    assert indian_succession.registry_key is None
    assert indian_succession.identity_status == "provisional"
    assert not any(
        entry.source == "personal succession law" and entry.must_cite
        for entry in plan.authority_ledger
    )


def test_succession_plan_selects_personal_law_source_from_known_religion():
    cases = {
        "my Hindu father died without a will and brothers deny my daughter share": "Hindu Succession Act 1956",
        "my Muslim father died without a will and my brothers deny my share": "Muslim Personal Law (Shariat) Application Act 1937",
        "my Christian father died without a will who inherits his house": "Indian Succession Act 1925",
        "my Parsi mother died without a will how is property divided": "Indian Succession Act 1925",
    }
    for query, expected in cases.items():
        route = route_matter(query)
        plan = build_matter_plan(query, route)
        assert plan is not None
        assert route.required_sources == [expected]
        assert any(entry.source == expected for entry in plan.authority_ledger)


def test_christian_child_succession_binds_child_specific_pack():
    query = "my Christian father died without a will who inherits his house among children"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    entry = next(
        item for item in plan.authority_ledger
        if item.act == "Indian Succession Act 1925"
    )
    assert entry.source_pack_id == "indian_succession_1925_christian_children"
    assert entry.required_anchor_patterns == ["/sec-37"]


def test_christian_widow_children_query_prefers_child_specific_pack_on_tie():
    query = "I am a Christian widow and my children want their share in my husband's house"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    entry = next(
        item for item in plan.authority_ledger
        if item.act == "Indian Succession Act 1925"
    )
    assert entry.source_pack_id == "indian_succession_1925_christian_children"
    assert entry.required_anchor_patterns == ["/sec-37"]


def test_succession_without_religion_keeps_personal_law_as_intake_fact():
    route = route_matter("my father died without a will and relatives deny my property share")
    assert route.category == "succession_inheritance"
    assert route.required_sources == [
        "religion/personal-law and family-tree facts before selecting the succession statute"
    ]
    assert "religion/personal law" in route.missing_facts


def test_passage_authority_ids_reject_empty_titles_wrong_types_and_stale_packs():
    from apps.api.legal_issue_plan import authority_ids_for_passage

    query = "online order arrived broken what to do"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    controlling = next(entry for entry in plan.authority_ledger if entry.canonical_name)

    assert authority_ids_for_passage(
        plan,
        title="",
        anchor="consumer-protection-2019/sec-35",
        source_pack_id="consumer_protection_2019",
        source_type="bare_act",
    ) == []
    assert authority_ids_for_passage(
        plan,
        title="Consumer Protection Act 2019",
        anchor="consumer-protection-2019/sec-35",
        source_pack_id="consumer_protection_2019",
        source_type="sc_judgment",
    ) == []
    assert authority_ids_for_passage(
        plan,
        title="Consumer Protection Act 2019",
        anchor="consumer-protection-2019/sec-35",
        source_pack_id="stale_or_forged_pack",
        source_type="bare_act",
    ) == []
    assert authority_ids_for_passage(
        plan,
        title="Consumer Protection Act 2019",
        anchor="consumer-protection-2019/sec-35",
        source_type="bare_act",
    ) == []
    assert authority_ids_for_passage(
        plan,
        title="Consumer Protection Act 2019",
        anchor="consumer-protection-2019/sec-35",
        source_pack_id="consumer_protection_2019",
        source_type="bare_act",
    ) == [controlling.authority_id]
    assert authority_ids_for_passage(
        plan,
        title="Consumer Protection Act 2019",
        anchor="consumer-protection-2019/sec-35",
        source_pack_id="consumer_protection_2019",
        source_type="",
    ) == []


def test_passage_authority_ids_fail_closed_for_ambiguous_title_without_pack():
    from dataclasses import replace

    from apps.api.legal_issue_plan import RetrievalSourcePlan, authority_ids_for_passage

    plan = build_matter_plan("online order arrived broken what to do", route_matter("online order arrived broken what to do"))
    assert plan is not None
    controlling = next(
        entry for entry in plan.authority_ledger
        if entry.act == "Consumer Protection Act 2019"
    )
    authority_ledger = [
        replace(entry, source_pack_id=None) if entry is controlling else entry
        for entry in plan.authority_ledger
    ]
    retrieval_sources = [
        RetrievalSourcePlan(
            source_pack_id="consumer_pack_a",
            title_patterns=["Consumer Protection Act 2019"],
            search_query="consumer refund",
            anchor_patterns=["/sec-35"],
            source_types=["bare_act"],
        ),
        RetrievalSourcePlan(
            source_pack_id="consumer_pack_b",
            title_patterns=["Consumer Protection Act 2019"],
            search_query="consumer bank dispute",
            anchor_patterns=["/sec-35"],
            source_types=["bare_act"],
        ),
    ]
    plan = replace(plan, authority_ledger=authority_ledger, retrieval_sources=retrieval_sources)

    assert authority_ids_for_passage(
        plan,
        title="Consumer Protection Act 2019",
        anchor="consumer-protection-2019/sec-35",
        source_type="bare_act",
    ) == []


def test_unsectioned_authority_uses_query_specific_pack_anchors():
    from apps.api.legal_issue_plan import authority_ids_for_passage

    query = "ICEGATE says imported goods were misdeclared and may be confiscated"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    customs = next(entry for entry in plan.authority_ledger if entry.act == "Customs Act 1962")

    assert customs.source_pack_id == "customs_misdeclaration_1962"
    assert "/sec-75" not in customs.required_anchor_patterns
    assert authority_ids_for_passage(
        plan,
        title="Customs Act 1962",
        anchor="customs-1962/sec-75",
        source_pack_id=customs.source_pack_id,
        source_type="bare_act",
    ) == []
    assert authority_ids_for_passage(
        plan,
        title="Customs Act 1962",
        anchor="customs-1962/sec-111",
        source_pack_id=customs.source_pack_id,
        source_type="bare_act",
    ) == [customs.authority_id]


def test_unstructured_route_requirements_bind_manual_and_constitutional_packs():
    from apps.api.legal_issue_plan import authority_ids_for_passage

    prison_query = (
        "need help tihar jail mulaqat only 30 min once a week is this legal "
        "can we ask more what next"
    )
    prison = build_matter_plan(prison_query, route_matter(prison_query))
    assert prison is not None
    manual = next(
        entry for entry in prison.authority_ledger
        if entry.source_pack_id == "delhi_prison_rules_2018_mulaqat_books"
    )
    assert manual.identity_status == "provisional"
    assert authority_ids_for_passage(
        prison,
        title="Delhi Prison Rules 2018",
        anchor="delhi-prison-rules-2018/rule-2-mulaqat",
        source_pack_id="delhi_prison_rules_2018_mulaqat_books",
        source_type="bare_act",
    ) == [manual.authority_id]

    article_21 = next(
        entry for entry in prison.authority_ledger
        if entry.source_pack_id == "constitution_article_21"
    )
    assert article_21.identity_status == "provisional"


def test_exact_source_pack_does_not_expand_to_same_title_sibling():
    from apps.api.legal_issue_plan import (
        AuthorityLedgerEntry,
        RetrievalSourcePlan,
        _authority_retrieval_sources,
    )

    entry = AuthorityLedgerEntry(
        source="Right to Information Act 2005 Section 6",
        act="Right to Information Act 2005",
        section="Section 6",
        source_pack_id="rti_2005_application",
    )
    first = RetrievalSourcePlan(
        source_pack_id="rti_2005_application",
        title_patterns=["Right to Information Act 2005"],
        search_query="RTI application section 6",
        anchor_patterns=["/sec-6"],
    )
    sibling = RetrievalSourcePlan(
        source_pack_id="rti_2005_certificate_record_request",
        title_patterns=["Right to Information Act 2005"],
        search_query="RTI certificate record section 6",
        anchor_patterns=["/sec-6"],
    )

    matching = _authority_retrieval_sources(
        entry,
        canonical_act="right to information act 2005",
        source_pack_id=entry.source_pack_id,
        retrieval_sources=[first, sibling],
    )
    assert [source.source_pack_id for source in matching] == [first.source_pack_id]


def test_unknown_explicit_source_pack_does_not_fallback_to_title_sibling():
    from apps.api.legal_issue_plan import (
        AuthorityLedgerEntry,
        RetrievalSourcePlan,
        _authority_retrieval_sources,
    )

    entry = AuthorityLedgerEntry(
        source="Right to Information Act 2005 Section 6",
        act="Right to Information Act 2005",
        section="Section 6",
        source_pack_id="stale_rti_pack_id",
    )
    sibling = RetrievalSourcePlan(
        source_pack_id="rti_2005_certificate_record_request",
        title_patterns=["Right to Information Act 2005"],
        search_query="RTI certificate record section 6",
        anchor_patterns=["/sec-6"],
    )

    assert _authority_retrieval_sources(
        entry,
        canonical_act="right to information act 2005",
        source_pack_id=entry.source_pack_id,
        retrieval_sources=[sibling],
    ) == []


def test_search_query_overlap_cannot_select_an_unreviewed_sibling_pack():
    from apps.api.legal_issue_plan import (
        AuthorityLedgerEntry,
        RetrievalSourcePlan,
        _attach_query_selected_source_packs,
    )

    entry = AuthorityLedgerEntry(
        source="Consumer Protection Act 2019",
        act="Consumer Protection Act 2019",
    )
    packs = [
        RetrievalSourcePlan(
            source_pack_id="pack_a",
            title_patterns=["Consumer Protection Act 2019"],
            search_query="consumer refund complaint",
        ),
        RetrievalSourcePlan(
            source_pack_id="pack_b",
            title_patterns=["Consumer Protection Act 2019"],
            search_query="consumer bank dispute",
        ),
    ]

    selected = _attach_query_selected_source_packs(
        [entry], packs, "consumer bank dispute"
    )[0]
    assert selected.source_pack_id is None


def test_section_scoping_does_not_fallback_to_wrong_same_title_pack():
    from apps.api.legal_issue_plan import (
        AuthorityLedgerEntry,
        RetrievalSourcePlan,
        _attach_query_selected_source_packs,
    )

    entry = AuthorityLedgerEntry(
        source="Consumer Protection Act 2019 Section 3",
        act="Consumer Protection Act 2019",
        section="Section 3",
    )
    packs = [
        RetrievalSourcePlan(
            source_pack_id="consumer_section_2",
            title_patterns=["Consumer Protection Act 2019"],
            search_query="consumer definitions",
            anchor_patterns=["/sec-2"],
            selection_terms=["definition"],
        ),
        RetrievalSourcePlan(
            source_pack_id="consumer_section_35",
            title_patterns=["Consumer Protection Act 2019"],
            search_query="consumer complaint",
            anchor_patterns=["/sec-35"],
            selection_terms=["complaint"],
        ),
    ]

    selected = _attach_query_selected_source_packs(
        [entry], packs, "consumer complaint section 3"
    )[0]
    assert selected.source_pack_id is None


def test_concrete_personal_law_act_is_not_downgraded_to_generic_context():
    from apps.api.legal_issue_plan import _authority_entry

    concrete = _authority_entry(
        "Muslim Personal Law (Shariat) Application Act 1937",
        1,
    )
    generic = _authority_entry("personal law by religion", 1)

    assert concrete.conditional is False
    assert concrete.must_cite is True
    assert generic.conditional is True
    assert generic.must_cite is False


def test_stage_source_ownership_binds_exact_reviewed_packs_for_common_routes():
    from apps.api.source_gap import matter_plan_integrity_gap

    cases = (
        (
            "sir MGNREGA wages of 4 months not paid sarpanch saying funds not come where to go",
            "MGNREGA 2005 wage, job-card, grievance and social-audit provisions",
            "mgnrega_2005",
        ),
        (
            "hi, cheque dishonoured in 2025 insufficient funds sent legal notice 30 days over can i file complaint can i file case",
            "BNSS 2023 / CrPC 1973 complaint procedure based on incident date",
            "bnss_cheque_complaint",
        ),
        (
            "please help esic card not issued even after 2 yrs cutting from salary went hospital they refused any remedy",
            "ESI medical-benefit and contribution eligibility procedure",
            "esi_1948",
        ),
        (
            "what to do i am ASHA worker not paid honorarium 6 months who can help is this legal",
            "RTI/public grievance route for payment status and sanction records",
            "rti_2005",
        ),
        (
            "hi, we want a baby through surrogate my wife had hysterectomy 4 years ago we are both 38 is surrogacy allowed for us can i file case",
            "medical board / appropriate authority procedure",
            "surrogacy_2021",
        ),
        (
            "can u tell village ojha branded my mother daayan stripped her in public ranchi area what can i do",
            "state-specific witch-hunting statute must be verified for the user's state before state-law offence details are given",
            "jharkhand_witch_daain_2001",
        ),
    )
    for query, source, pack_id in cases:
        plan = build_matter_plan(query, route_matter(query))
        assert plan is not None
        entry = next(item for item in plan.authority_ledger if item.source == source)
        assert entry.source_pack_id == pack_id, query
        assert matter_plan_integrity_gap(plan, query) is None, query


def test_stage_minimum_wage_query_does_not_inherit_esi_authorities():
    query = "hi, code on wages applicable to me minimum wage notification gujarat for unskilled worker can i file case"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.category == "labour_compliance"
    assert any(source.startswith("Code on Wages 2019") for source in route.required_sources)
    assert not any("State Insurance" in source for source in route.required_sources)
    assert plan is not None
    assert any(
        entry.source.startswith("Code on Wages 2019")
        and entry.source_pack_id == "code_on_wages_2019"
        for entry in plan.authority_ledger
    )


def test_stage_state_specific_caste_certificate_route_remains_fail_closed():
    from apps.api.source_gap import (
        build_source_gap_event,
        matter_plan_integrity_gap,
        missing_required_authorities,
    )

    query = "what to do my caste certificate rejected by tehsildar I am SC how to appeal is this legal"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    assert matter_plan_integrity_gap(plan, query) is None
    assert any(
        item["required_source"] == "state caste-certificate issuance and appeal rules"
        and item["kind"] == "state_or_local_authority_gap"
        for item in missing_required_authorities(
            required_sources=route.required_sources,
            passages=[],
            query=query,
        )
    )
    event = build_source_gap_event(
        query=query,
        route_category=route.category,
        required_sources=route.required_sources,
        passages=[],
        plan=plan,
        legal_regime=route.legal_regime,
    )
    assert event is not None
    assert "state_or_local_authority_gap" in event["gap_kinds"]


def test_reviewed_rti_certificate_pack_is_selected_for_certificate_query():
    query = "ST certificate not issued by tehsildar 8 months daughter exam form rejected jharkhand"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    rti = next(
        entry for entry in plan.authority_ledger
        if entry.act == "Right to Information Act 2005"
    )
    assert rti.source_pack_id == "rti_2005_certificate_record_request"


def test_reviewed_it_intermediary_pack_is_selected_for_platform_leak_query():
    query = "telegram channel leaked my onlyfans content without permission what to do"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    it_act = next(
        entry for entry in plan.authority_ledger
        if entry.act == "Information Technology Act 2000"
    )
    assert it_act.source_pack_id == "it_act_2000_intermediary"


def test_same_title_ni_packs_bind_security_section_and_general_section_separately():
    query = "I gave blank cheque to landlord as security and he sent notice under 138 what defence"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    section_138 = next(
        entry for entry in plan.authority_ledger if entry.section == "Section 138"
    )
    section_142 = next(
        entry for entry in plan.authority_ledger if entry.section == "Section 142"
    )
    assert section_138.source_pack_id == "ni_act_138_security_cheque"
    assert section_142.source_pack_id == "ni_act_1881"
    assert "/sec-138" in section_138.required_anchor_patterns
    assert set(("/sec-138", "/sec-141", "/sec-142")) == set(
        section_142.required_anchor_patterns
    )


def test_subsection_requirement_accepts_reviewed_parent_section_anchor():
    from apps.api.legal_issue_plan import authority_ids_for_passage

    query = "sand mining in scheduled area without gram sabha recommendation"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None
    pesa = next(entry for entry in plan.authority_ledger if entry.act == "PESA Act 1996")
    assert pesa.section == "Section 4(c)"

    assert authority_ids_for_passage(
        plan,
        title="Panchayats (Extension to the Scheduled Areas) Act 1996",
        anchor="pesa-1996/sec-4",
        text="Panchayats (Extension to the Scheduled Areas) Act 1996, Section 4(c)\nConsultation.",
        source_pack_id="pesa_1996",
        source_type="bare_act",
    ) == [pesa.authority_id]

    assert authority_ids_for_passage(
        plan,
        title="Panchayats (Extension to the Scheduled Areas) Act 1996",
        anchor="pesa-1996/sec-4",
        text="Panchayats (Extension to the Scheduled Areas) Act 1996, Section 4(d)\nConsultation.",
        source_pack_id="pesa_1996",
        source_type="bare_act",
    ) == []


def test_criminal_authority_identity_follows_incident_regime():
    legacy_query = "in 2023 police arrested me for bike theft what bail can I get"
    current_query = "in 2025 police arrested me for bike theft what bail can I get"
    legacy = build_matter_plan(legacy_query, route_matter(legacy_query))
    current = build_matter_plan(current_query, route_matter(current_query))
    assert legacy is not None and current is not None

    legacy_acts = {entry.act for entry in legacy.authority_ledger}
    current_acts = {entry.act for entry in current.authority_ledger}
    assert "Code of Criminal Procedure 1973" in legacy_acts
    assert "Indian Penal Code 1860" in legacy_acts
    assert "Bharatiya Nagarik Suraksha Sanhita 2023" not in legacy_acts
    assert "Bharatiya Nyaya Sanhita 2023" not in legacy_acts
    assert "Bharatiya Nagarik Suraksha Sanhita 2023" in current_acts
    assert "Bharatiya Nyaya Sanhita 2023" in current_acts
    assert "Code of Criminal Procedure 1973" not in current_acts
    assert "Indian Penal Code 1860" not in current_acts


def test_separate_criminal_procedure_requirements_follow_incident_regime():
    legacy_query = "in 2023 police arrested my son at night what are his rights"
    current_query = "in 2025 police arrested my son at night what are his rights"
    legacy = build_matter_plan(legacy_query, route_matter(legacy_query))
    current = build_matter_plan(current_query, route_matter(current_query))
    assert legacy is not None and current is not None

    legacy_acts = {entry.act for entry in legacy.authority_ledger}
    current_acts = {entry.act for entry in current.authority_ledger}
    assert "Code of Criminal Procedure 1973" in legacy_acts
    legacy_bnss = [
        entry
        for entry in legacy.authority_ledger
        if entry.act == "Bharatiya Nagarik Suraksha Sanhita 2023"
    ]
    assert {entry.section for entry in legacy_bnss} == {"Section 531"}
    assert "Bharatiya Nagarik Suraksha Sanhita 2023" in current_acts
    assert "Code of Criminal Procedure 1973" not in current_acts


def test_unknown_date_hidden_arrest_keeps_current_and_legacy_route_packs():
    query = "Police picked my son from home and gave no FIR copy"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None
    assert route.legal_regime == "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"

    source_pack_ids = {source.source_pack_id for source in plan.retrieval_sources}
    assert "bnss_2023" in source_pack_ids
    assert "crpc_1973" in source_pack_ids
    assert "bnss_2023_custody_registry" in source_pack_ids


def test_filtered_legacy_route_reindexes_first_retained_authority_as_must_cite():
    query = "in 2023 police called me for questioning as witness what are my rights"
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    crpc_entries = [
        entry for entry in plan.authority_ledger
        if entry.act == "Code of Criminal Procedure 1973"
    ]
    assert crpc_entries[0].section == "Section 160"
    assert crpc_entries[0].must_cite is True
    assert crpc_entries[0].priority == "must_cite"


def test_single_statute_composites_preserve_every_explicit_section():
    route = MatterRoute(
        category="cyber_fraud_or_harassment",
        label="Electronic content allegation",
        confidence=0.8,
        urgency="high",
        required_sources=[
            "Information Technology Act 2000 sections 67 / 66E / 67A",
            "Immoral Traffic Prevention Act 1956 sections 4, 5, 7, or 8",
        ],
        forums=[],
        missing_facts=[],
        red_flags=[],
    )
    plan = build_matter_plan("police case about electronic content", route)
    assert plan is not None

    it_sections = [
        entry.section for entry in plan.authority_ledger
        if entry.act == "Information Technology Act 2000"
    ]
    itpa_sections = [
        entry.section for entry in plan.authority_ledger
        if entry.act == "Immoral Traffic Prevention Act 1956"
    ]
    assert it_sections == ["Section 67", "Section 66E", "Section 67A"]
    assert itpa_sections == ["Section 4", "Section 5", "Section 7", "Section 8"]


def test_composite_criminal_source_preserves_every_explicit_section():
    query = (
        "in 2025 girl I was dating filed rape case after we broke up saying I promised "
        "marriage we had relationship for 2 years"
    )
    plan = build_matter_plan(query, route_matter(query))
    assert plan is not None

    bns_sections = [
        entry.section for entry in plan.authority_ledger
        if entry.act == "Bharatiya Nyaya Sanhita 2023"
    ]
    assert bns_sections == ["Section 63", "Section 69"]


def test_matter_plan_answer_policy_matches_critical_route_guard():
    _, critical = _plan("police did not file my FIR what can I do")
    assert critical["answer_policy"] == {
        "required_primary_owner": "reviewed_workflow",
        "fallback_owner": "source_gap_handoff",
        "allow_freeform_llm": False,
        "requires_reviewed_contract": True,
    }

    _, ordinary = _plan("online order arrived broken what to do")
    assert ordinary["answer_policy"]["required_primary_owner"] == "server_template_or_verified_llm"
    assert ordinary["answer_policy"]["allow_freeform_llm"] is True
    assert ordinary["remedies"] == []
    assert ordinary["deadlines"] == []


def test_workplace_respondent_plan_binds_exact_workflow_and_posh_source():
    query = "I am accused of sexually harassing a colleague and got an ICC notice"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.category == "workplace_sexual_harassment"
    assert plan is not None
    assert plan.user_role == "accused_or_accused_family"
    assert plan.answer_policy.required_primary_owner == (
        "common_workflow_contracts:workplace_sexual_harassment_respondent"
    )
    assert plan.answer_policy.allow_freeform_llm is False
    assert any(source.source_pack_id == "posh_2013" for source in plan.retrieval_sources)
    assert any(
        entry.source_pack_id == "posh_2013" and entry.required_anchor_patterns
        for entry in plan.authority_ledger
    )


def test_workplace_complainant_plan_binds_exact_workflow_and_posh_source():
    query = "I complained to ICC about sexual harassment by my manager"
    route = route_matter(query)
    plan = build_matter_plan(query, route)

    assert route.category == "workplace_sexual_harassment"
    assert plan is not None
    assert plan.user_role == "complainant_or_victim"
    assert plan.answer_policy.required_primary_owner == (
        "common_workflow_contracts:workplace_sexual_harassment_first_action"
    )
    assert plan.answer_policy.allow_freeform_llm is False
    assert any(source.source_pack_id == "posh_2013" for source in plan.retrieval_sources)
    assert any(
        entry.source_pack_id == "posh_2013" and entry.required_anchor_patterns
        for entry in plan.authority_ledger
    )


def test_bare_icc_does_not_create_a_posh_secondary_issue():
    _, plan = _plan("ICC cricket match ticket refund")
    assert plan["primary_issue"] == "consumer"
    assert "workplace_sexual_harassment" not in plan["secondary_issues"]


def test_bare_icc_notice_does_not_get_a_route_independent_posh_owner():
    route, plan = _plan("I got an ICC notice")
    assert route.category == "general_legal"
    assert plan["answer_policy"]["required_primary_owner"] != (
        "common_workflow_contracts:workplace_sexual_harassment_first_action"
    )


def test_legal_issue_plan_tracks_multilabel_medical_negligence():
    _, plan = _plan("doctor operated wrong leg in hospital what can we do")

    assert plan["user_role"] == "patient_or_family"
    assert "medical_negligence" in plan["secondary_issues"]
    assert "consumer_compensation" in plan["secondary_issues"]


def test_legal_issue_plan_accused_framing_guard_for_cyber_notice():
    _, plan = _plan("police sent me notice in cyber fraud case and i am accused what to do")

    assert plan["user_role"] == "accused_or_accused_family"
    assert plan["case_stage"] == "notice_stage"
    assert plan["desired_outcome"] == "defence_or_notice_response"
    assert "incident_date_needed" in plan["safety_flags"]
    assert "accused_framing_guard" in plan["safety_flags"]
    regime_entries = [
        entry for entry in plan["authority_ledger"]
        if entry["act"] == "date-dependent criminal regime"
    ]
    assert regime_entries
    assert regime_entries[0]["priority"] == "must_cite"
    assert regime_entries[0]["must_cite"] is True


def test_legal_issue_plan_jurisdiction_and_date_flags():
    route, plan = _plan("my tenant is not vacating house and not paying rent in Pune")

    assert route.category == "property_tenancy"
    assert plan["user_role"] == "landlord"
    assert plan["jurisdiction"]["city"] == "pune"
    assert plan["jurisdiction"]["state"] == "maharashtra"
    assert plan["desired_outcome"] == "eviction_or_possession"
    assert "state_or_city_needed" not in plan["safety_flags"]


def test_legal_issue_plan_senior_parent_role_not_patient_by_default():
    route, plan = _plan("my senior citizen father gifted flat to daughter now she is not maintaining him")

    assert route.category == "senior_citizen"
    assert plan["user_role"] == "senior_citizen_or_family"


def test_legal_issue_plan_senior_eviction_not_misread_as_generic_parent():
    route, plan = _plan("my son threw me out of my own house i paid for it in 1985 mumbai")

    assert route.category == "senior_citizen"
    assert plan["user_role"] == "senior_citizen_or_family"


def test_legal_issue_plan_hospital_wrong_limb_role_is_patient_family():
    route, plan = _plan("hospital operated wrong leg on my 80 yr old father what can we do")

    assert route.category == "consumer"
    assert plan["user_role"] == "patient_or_family"


def test_legal_issue_plan_generic_hr_pip_does_not_leak_posh_secondary():
    route, plan = _plan("i complained against my manager for harassment to HR and now they are putting me on PIP, is this retaliation")

    assert route.category == "employment_wages"
    assert "employment_retaliation" in plan["secondary_issues"]
    assert "workplace_sexual_harassment" not in plan["secondary_issues"]
    assert plan["user_role"] == "employee_or_worker"


def test_legal_issue_plan_posh_pip_keeps_posh_secondary():
    route, plan = _plan("complained about sexual harassment by my manager to HR and now he gave PIP bad rating")

    assert route.category == "workplace_sexual_harassment"
    assert plan["primary_issue"] == "workplace_sexual_harassment"
    assert "employment_retaliation" in plan["secondary_issues"]


def test_legal_issue_plan_family_property_not_patient_by_default():
    route, plan = _plan("my father sold ancestral land without asking me what can i do")

    assert route.category != "consumer"
    assert plan["user_role"] != "patient_or_family"


def test_legal_issue_plan_common_category_defaults_are_not_unknown():
    cases = {
        "spotify took down my remix song fair use ya legal copyright issue": "creator_or_rights_holder",
        "hi, rule 86B applies to me turnover 55 lakh per month must pay 1% cash mandatory ya choot hai": "taxpayer_or_business",
        "urgent procedure to file insolvency petition against company in NCLT how to complain": "creditor_debtor_or_company_stakeholder",
        "sir ASHA worker not paid honorarium 6 months who can help where to go": "employee_or_worker",
        "can u tell nrega 28 days work done village mukhiya not paid since 6 months gadchiroli maharashtra": "employee_or_worker",
        "data breach at byjus my pan and aadhaar leaked can i claim compensation under DPDP act": "complainant_or_victim",
    }
    for query, expected_role in cases.items():
        _, plan = _plan(query)
        assert plan["user_role"] == expected_role


def test_legal_issue_plan_environment_project_extracts_affected_role_and_district():
    route, plan = _plan("DM gave NOC to bauxite project bastar without gram sabha resolution how to challenge")

    assert route.category == "environment_compensation"
    assert plan["user_role"] == "affected_resident_or_landholder"
    assert plan["jurisdiction"]["city"] == "bastar"
    assert plan["jurisdiction"]["state"] == "chhattisgarh"
    assert plan["desired_outcome"] == "project_approval_or_compensation"


def test_legal_issue_plan_undertrial_and_order_stages_are_explicit():
    _, undertrial = _plan("need help i undertrial 3 yrs in puzhal lawyer not coming hearings when can complain")
    assert undertrial["user_role"] == "accused_or_accused_family"
    assert undertrial["case_stage"] == "custody_or_trial_pending"
    assert undertrial["jurisdiction"]["city"] == "puzhal"
    assert undertrial["jurisdiction"]["state"] == "tamil nadu"

    _, support = _plan("ex husband not paying child support of 25000 per month as per court order 8 months pending")
    assert support["case_stage"] == "order_or_decree_exists"
    assert support["desired_outcome"] == "maintenance_enforcement"


def test_legal_issue_plan_notice_under_is_category_aware_not_accused_by_default():
    cases = [
        (
            "bank sent me notice under sarfaesi section 13(2)",
            "banking_credit_dispute",
            "bank_customer_or_borrower",
            "sarfaesi_or_banking_notice_response",
        ),
        (
            "gst notice under section 73 received",
            "tax_gst_compliance",
            "taxpayer_or_business",
            "tax_notice_response",
        ),
        (
            "landlord sent me notice under rent act to vacate",
            "property_tenancy",
            "tenant",
            "tenancy_notice_response",
        ),
        (
            "notice under consumer complaint from customer received by my shop",
            "consumer",
            "business_or_service_provider_respondent",
            "consumer_notice_response",
        ),
        (
            "police sent me notice under 41a but i am witness",
            "criminal_general",
            "witness_or_notice_recipient",
            "witness_notice_response",
        ),
    ]
    for query, category, role, outcome in cases:
        route, plan = _plan(query)
        assert route.category == category
        assert plan["user_role"] == role
        assert plan["case_stage"] == "notice_stage"
        assert plan["desired_outcome"] == outcome


def test_legal_issue_plan_accused_word_does_not_steal_victim_or_witness_context():
    victim_queries = [
        "the accused got bail and is threatening me what can i do",
        "accused got bail and threatening me what can i do",
        "accused is threatening me after bail what to do",
        "main accused came to my house after bail and threatened me",
    ]
    for query in victim_queries:
        _, victim = _plan(query)
        assert victim["user_role"] == "complainant_or_victim"
        assert victim["desired_outcome"] == "victim_protection_or_bail_cancellation"

    _, witness = _plan("witness saw accused but police not recording statement")
    assert witness["user_role"] == "witness_or_complainant"
    assert witness["desired_outcome"] == "witness_statement_or_police_followup"

    _, witness_threat = _plan("accused in my case is harassing me and witness")
    assert witness_threat["user_role"] == "witness_or_complainant"
    assert witness_threat["desired_outcome"] == "victim_or_witness_protection_followup"

    _, accused = _plan("police sent me notice in cyber fraud case and i am accused what to do")
    assert accused["user_role"] == "accused_or_accused_family"
    assert accused["desired_outcome"] == "defence_or_notice_response"

    _, brother = _plan("my brother is accused and got bail what to do")
    assert brother["user_role"] == "accused_or_accused_family"
    assert brother["desired_outcome"] == "bail_or_release"

    _, son = _plan("my son is accused in FIR what should we do")
    assert son["user_role"] == "accused_or_accused_family"
    assert son["desired_outcome"] == "defence_or_notice_response"

    accused_queries = [
        "my son is accused in FIR what to do",
        "i have been accused in cyber fraud case what to do",
        "my brother was accused falsely in fir what to do",
    ]
    for query in accused_queries:
        _, plan = _plan(query)
        assert plan["user_role"] == "accused_or_accused_family"
        assert plan["desired_outcome"] == "defence_or_notice_response"


def test_legal_issue_plan_active_accused_voice_stays_complainant_side():
    complainant_queries = [
        "i accused him of fraud but police not filing fir what to do",
        "i accused company of cheating consumer what to do next",
        "my son accused neighbour of assault police not filing fir",
        "my daughter accused neighbour of assault police not filing fir",
        "my father accused neighbour of assault police not filing fir",
        "my brother accused shopkeeper of cheating but no fir",
    ]
    for query in complainant_queries:
        _, plan = _plan(query)
        assert plan["user_role"] != "accused_or_accused_family"
        assert plan["desired_outcome"] != "defence_or_notice_response"


def test_legal_issue_plan_victim_bail_opposition_is_not_accused_release():
    cases = [
        ("i accused him of fraud need bail cancellation", "complainant_or_victim"),
        ("my son accused neighbour of assault need bail cancellation", "complainant_or_victim"),
        ("accused in my case applying bail how oppose", "complainant_or_victim"),
        ("the accused filed bail application how to oppose", "complainant_or_victim"),
        (
            "rape survivor wants to oppose anticipatory bail of accused",
            "sexual_offence_survivor_or_complainant",
        ),
    ]
    for query, role in cases:
        _, plan = _plan(query)
        assert plan["user_role"] == role
        assert plan["desired_outcome"] == "victim_protection_or_bail_cancellation"


def test_legal_issue_plan_minor_mineral_pesa_does_not_force_rfctlarr():
    route, plan = _plan("sand mining lease given without gram sabha consent in scheduled area")
    acts = [entry["act"] or "" for entry in plan["authority_ledger"]]

    assert route.label == "Minor mineral / Gram Sabha recommendation"
    assert any("PESA Act 1996" in act for act in acts)
    assert any("Mines and Minerals" in act for act in acts)
    assert not any("RFCTLARR" in act or "Fair Compensation" in act for act in acts)


def test_legal_issue_plan_extracts_pwdva_acronym_as_must_cite_act():
    _, plan = _plan("my husband hit me and took my salary what to do")
    first = plan["authority_ledger"][0]

    assert first["source"].startswith("PWDVA 2005")
    assert first["act"] == "Protection of Women from Domestic Violence Act 2005"
    assert first["must_cite"] is True


def test_legal_issue_plan_selects_st_article_and_does_not_append_sc_source():
    from apps.api.main import _plan_must_cite_passages, _route_required_source_floor_passages

    query = "office rejected my ST certificate saying not local resident what appeal"
    route = route_matter(query)
    plan = build_matter_plan(query, route)
    assert plan is not None

    constitution_entries = [entry for entry in plan.authority_ledger if entry.act == "Constitution of India"]
    assert [entry.section for entry in constitution_entries] == ["Article 342"]
    rti_entries = [entry for entry in plan.authority_ledger if entry.act == "Right to Information Act 2005"]
    assert [entry.section for entry in rti_entries] == ["Section 6"]
    assert [entry.identity_status for entry in rti_entries] == ["canonical"]

    passages = [
        {"index": 1, "title": "Constitution of India", "anchor": "constitution-india/sec-341"},
        {"index": 2, "title": "Right to Information Act 2005", "anchor": "rti-2005/sec-6"},
        {"index": 3, "title": "Constitution of India", "anchor": "constitution-india/sec-342"},
    ]
    additions = _plan_must_cite_passages(route, plan, passages, cited={2, 3}, query=query)

    assert additions == []

    floor = _route_required_source_floor_passages(
        route,
        passages,
        cited={2, 3},
        cited_source_keys=set(),
        query=query,
        plan=plan,
    )
    assert all(passage["index"] != 1 for passage in floor)


def test_legal_issue_plan_keeps_ambiguous_sc_st_category_unselected():
    for query in (
        "my SC/ST certificate was rejected what appeal",
        "my SC-ST certificate was rejected what appeal",
    ):
        route = route_matter(query)
        plan = build_matter_plan(query, route)
        assert plan is not None

        constitution_entries = [
            entry for entry in plan.authority_ledger if entry.act == "Constitution of India"
        ]
        assert len(constitution_entries) == 1
        assert constitution_entries[0].section is None
        assert constitution_entries[0].required_anchor_patterns == ["/sec-341", "/sec-342"]
