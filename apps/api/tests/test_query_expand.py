import asyncio

from apps.api import config as config_module
from apps.api.query_expand import expand_query


def _clear_settings_cache() -> None:
    config_module.get_settings.cache_clear()


def test_llm_fallback_disabled_for_general_queries():
    query = "station not released my seized phone after case closed"
    out = asyncio.run(
        expand_query(
            query,
            max_variants=1,
        )
    )

    assert out == [query]


def test_low_confidence_route_expansion_uses_deterministic_variant():
    out = asyncio.run(
        expand_query(
            "how to file private complaint before magistrate when police inaction",
            max_variants=1,
        )
    )

    assert len(out) == 2
    assert "BNSS 2023" in out[1]


def test_default_bail_expansion_targets_default_bail_not_anticipatory():
    out = asyncio.run(
        expand_query(
            "brother in jail 60 days completed no chargesheet can he get default bail",
            max_variants=1,
        )
    )

    assert len(out) == 2
    variant = out[1].lower()
    assert "default bail" in variant
    assert "section 187" in variant
    assert "section 167" in variant
    assert "anticipatory" not in variant


def test_legacy_default_bail_expansion_prefers_crpc_167():
    out = asyncio.run(
        expand_query(
            "arrested in 2023 and 90 days passed with no chargesheet default bail",
            max_variants=1,
        )
    )

    assert len(out) == 2
    assert "CrPC 1973 section 167" in out[1]
    assert "BNSS 2023 section 187" not in out[1]


def test_anticipatory_bail_expansion_keeps_anticipatory_sections():
    out = asyncio.run(
        expand_query(
            "anticipatory bail in dowry case husband family how many days valid",
            max_variants=1,
        )
    )

    assert len(out) == 2
    variant = out[1].lower()
    assert "anticipatory bail" in variant
    assert "section 482" in variant
    assert "section 438" in variant


def test_section_91_notice_expansion_maps_current_bnss_94():
    out = asyncio.run(
        expand_query(
            "police sent section 91 notice asking for my phone and whatsapp chats",
            max_variants=2,
        )
    )

    joined = "\n".join(out[1:])
    assert "BNSS 2023 section 94" in joined
    assert "CrPC 1973 section 91" in joined


def test_new_red_flag_route_expansions_are_deterministic():
    cases = {
        "my brother is 13 they got him married to 20 year old how to stop": "Prohibition of Child Marriage Act 2006",
        "brick kiln owner up keeping family hostage advance 25000 cannot go home": "Bonded Labour System Abolition Act 1976",
        "I am disabled cannot walk officer not making my disability certificate 1 year": "Rights of Persons with Disabilities Act 2016",
        "papa arrest 5 din ho gaya magistrate ke samne kab le jana hota hai": "BNSS 2023 section 57",
    }
    for query, expected in cases.items():
        out = asyncio.run(expand_query(query, max_variants=2))
        assert expected in "\n".join(out[1:]), query


def test_high_risk_dynamic_expansions_cover_child_cyber_and_witch_branding():
    cyber = asyncio.run(
        expand_query("my 15 year daughter nude photo leaked on instagram", max_variants=3)
    )
    assert "POCSO Act 2012" in "\n".join(cyber[1:])
    assert "Information Technology Act 2000 section 66E 67" in "\n".join(cyber[1:])

    witch = asyncio.run(
        expand_query("my saas labelled daayan and beaten by village people assam barpeta", max_variants=2)
    )
    assert "Witch Hunting" in "\n".join(witch[1:])


def test_adult_offspring_cyber_expansion_does_not_inject_pocso():
    out = asyncio.run(
        expand_query("my 22 year old child nude photo leaked on instagram", max_variants=3)
    )
    assert "POCSO Act 2012" not in "\n".join(out[1:])


def test_non_gambling_platform_expansion_does_not_inject_gambling_law():
    out = asyncio.run(
        expand_query("binance froze my usdt wallet 4 lakh saying suspicious trade is it legal", max_variants=4)
    )
    joined = "\n".join(out[1:]).lower()
    assert "public gambling act" not in joined
    assert "tamil nadu prohibition of online gambling" not in joined


def test_retrenchment_tax_succession_and_voter_expansions():
    cases = {
        "want to retrench 8 workers factory has 120 employees ludhiana garments need permission": "Industrial Disputes Act 1947 section 25F",
        "i forgot to file ITR for AY 2022-23 can i still file it now what is the penalty": "Income Tax Act 1961 section 234F",
        "gst officer sealed my godown without notice surat textile trader what to do": "Central Goods and Services Tax Act 2017 section 67",
        "parsi mother passed away in mumbai how property divided among us three sisters": "Indian Succession Act 1925 Parsi",
        "voter id name spelt wrong booth officer denied me vote last election": "Representation of the People Act 1950",
    }
    for query, expected in cases.items():
        out = asyncio.run(expand_query(query, max_variants=3))
        assert expected in "\n".join(out[1:]), query


def test_gst_registration_expansion_does_not_default_to_234f_penalty():
    out = asyncio.run(
        expand_query("freelance designer 18 lakh income should i register gst or no", max_variants=3)
    )
    joined = "\n".join(out[1:])
    assert "CGST Act 2017" in joined
    assert "234F" not in joined


def test_legacy_arrest_expansion_does_not_invent_crpc_58():
    out = asyncio.run(
        expand_query(
            "arrested in 2023 not produced before magistrate within 24 hours",
            max_variants=2,
        )
    )
    joined = "\n".join(out[1:])
    assert "CrPC 1973 section 56 section 57" in joined
    assert "CrPC 1973 section 57 section 58" not in joined


def test_special_law_default_bail_expansion_mentions_ndps_extension_only_when_indexed():
    out = asyncio.run(
        expand_query(
            "brother in NDPS case arrested 110 days no chargesheet default bail possible",
            max_variants=2,
        )
    )

    assert any("NDPS Act 1985 section 36A" in item for item in out[1:])

    uapa_out = asyncio.run(
        expand_query(
            "brother arrested in UAPA 100 days no chargesheet default bail possible",
            max_variants=2,
        )
    )
    assert not any("Unlawful Activities Prevention Act" in item for item in uapa_out[1:])


def test_procedural_family_tax_gap_expansions_are_deterministic():
    cases = {
        "i am paralegal volunteer in tihar undertrial 70 yrs ipc 302 how to apply 479 BNSS review": "BNSS 2023 section 479",
        "decree holder how to file execution petition Order 21 CPC": "Code of Civil Procedure 1908 execution of decrees",
        "second appeal high court substantial question of law procedure": "Code of Civil Procedure 1908 section 100",
        "customs ICEGATE bill of entry hold importer what appeal remedy": "Customs Act 1962",
        "ITAT appeal delay after income tax assessment order what is limitation": "Income Tax Act 1961 section 253",
        "my husband took our 5 year old to delhi during fight and is not letting me meet how do I get her back fast": "Guardians and Wards Act 1890",
        "want to file mutual consent divorce, both me and husband agree, what is the process and time in mumbai": "Hindu Marriage Act 1955 section 13B",
    }
    for query, expected in cases.items():
        out = asyncio.run(expand_query(query, max_variants=3))
        assert expected in "\n".join(out[1:]), query


def test_eval_general_spillover_expansions_are_specific():
    cases = {
        "muster roll fake entries BDO putting my name without me working khunti how complain": "section 17 social audit section 19 grievance",
        "factory deducted 800 every month for shoes uniform never given orissa worker tiruppur knitwear": "Code on Wages 2019 section 17",
        "my startup co founder is trying to dilute my equity using ESOP pool without my consent, i have 30 percent": "Companies Act 2013 section 62",
        "agent took my goods worth 7 lakh and absconded gujarat principal agent relationship": "Indian Contract Act 1872 agency",
        "zomato rider here met with accident on bike no insurance from company": "Code on Social Security 2020 section 113",
        "what is an affidavit and how do I get one notarised for court": "court affidavit notarised notary",
    }
    for query, expected in cases.items():
        out = asyncio.run(expand_query(query, max_variants=3))
        joined = "\n".join(out[1:])
        assert expected in joined, query
        if "muster roll" in query:
            assert "section 25" not in joined


def test_subagent_false_positive_expansion_regressions():
    rti = asyncio.run(expand_query("RTI second appeal no reply from PIO for ration records", max_variants=3))
    assert "Code of Civil Procedure 1908 section 100" not in "\n".join(rti[1:])
    assert "Right to Information Act 2005" in "\n".join(rti[1:])

    special = asyncio.run(
        expand_query("special marriage couple mutual consent divorce both agree section 28", max_variants=3)
    )
    joined_special = "\n".join(special[1:])
    assert "Special Marriage Act 1954 section 28" in joined_special
    assert "Hindu Marriage Act 1955 section 13B" not in joined_special

    christian = asyncio.run(
        expand_query("we are christian couple want mutual consent divorce both agree", max_variants=3)
    )
    assert "Hindu Marriage Act 1955 section 13B" not in "\n".join(christian[1:])
    assert "Divorce Act 1869" in "\n".join(christian[1:])


def test_family_civil_expansions_preserve_user_issue_lanes():
    cases = [
        (
            "mutual consent divorce both agree no fight what papers needed",
            ("Hindu Marriage Act 1955 section 13B",),
            ("second marriage", "bigamy", "section 27 restraint", "adultery"),
        ),
        (
            "special marriage couple mutual consent divorce both agree section 28",
            ("Special Marriage Act 1954 section 28",),
            ("Hindu Marriage Act 1955 section 13B", "second marriage", "bigamy"),
        ),
        (
            "we are christian couple want mutual consent divorce both agree",
            ("Divorce Act 1869",),
            ("Hindu Marriage Act 1955 section 13B", "Special Marriage Act 1954 section 28", "second marriage"),
        ),
        (
            "muslim couple want divorce by mutual consent both agree procedure",
            ("Muslim Personal Law",),
            ("Hindu Marriage Act 1955 section 13B", "Special Marriage Act 1954 section 28"),
        ),
        (
            "i caught my husband with another woman having sex",
            ("Hindu Marriage Act 1955 section 13",),
            ("section 13B", "second marriage", "bigamy", "Protection of Women from Domestic Violence Act"),
        ),
        (
            "christian wife caught husband having affair with another woman",
            ("Divorce Act 1869",),
            ("Hindu Marriage Act 1955", "Special Marriage Act 1954 section 27", "second marriage"),
        ),
        (
            "muslim husband having affair with another woman what family court remedy",
            ("Muslim Personal Law",),
            ("Hindu Marriage Act 1955", "Special Marriage Act 1954", "second marriage"),
        ),
        (
            "special marriage husband having affair with another woman what divorce ground",
            ("Special Marriage Act 1954 section 27",),
            ("Hindu Marriage Act 1955", "Divorce Act 1869", "second marriage"),
        ),
        (
            "my wife denies sex since one year what can i do",
            ("Hindu Marriage Act 1955 section 9 section 13",),
            ("BNS 2023", "bigamy", "second marriage"),
        ),
        (
            "my husband forces sex when i say no and threatens me",
            ("Protection of Women from Domestic Violence Act 2005",),
            ("section 13B", "second marriage", "non compete"),
        ),
        (
            "my husband did second marriage without divorcing me",
            ("second marriage",),
            ("section 13B mutual consent", "Special Marriage Act 1954 section 28"),
        ),
        (
            "my husband lied about salary before marriage",
            ("Hindu Marriage Act 1955 section 12",),
            ("second marriage", "adultery", "section 13B"),
        ),
        (
            "my tenant not vacating because I want to sell the flat",
            ("section 106 lease termination",),
            ("section 45 joint transfer", "gift deed", "legal heirs inherited"),
        ),
        (
            "can I sell property if one legal heir is not agreeing",
            ("Hindu Succession Act 1956 section 8",),
            ("tenant not vacating", "section 106 lease termination", "gift deed"),
        ),
        (
            "my brother took hand loan and not returning money",
            ("Indian Contract Act 1872 section 37",),
            ("section 27 non compete", "Negotiable Instruments Act 1881 section 138"),
        ),
    ]
    for query, required, forbidden in cases:
        joined = "\n".join(asyncio.run(expand_query(query, max_variants=3))[1:])
        for expected in required:
            assert expected in joined, (query, expected, joined)
        for unexpected in forbidden:
            assert unexpected not in joined, (query, unexpected, joined)


def test_name_change_expansion_uses_gazette_identity_terms_not_marriage_status_terms():
    out = asyncio.run(
        expand_query(
            "how to legally change my surname after marriage, do i need to publish in gazette",
            max_variants=3,
        )
    )

    joined = "\n".join(out[1:]).lower()
    assert "department of publication" in joined
    assert "egazette" in joined
    assert "identity record" in joined
    assert "second marriage" not in joined
    assert "protection maintenance" not in joined

    refund = asyncio.run(expand_query("income tax refund stuck ITR processed no refund", max_variants=3))
    joined_refund = "\n".join(refund[1:])
    assert "234F" not in joined_refund
    assert "section 237" in joined_refund

    gst = asyncio.run(expand_query("GST penalty notice for late return what to do", max_variants=3))
    joined_gst = "\n".join(gst[1:])
    assert "registration threshold" not in joined_gst
    assert "section 47" in joined_gst

    surrogacy = asyncio.run(
        expand_query(
            "we want a baby through surrogate my wife had hysterectomy 4 years ago we are both 38 is surrogacy allowed for us",
            max_variants=3,
        )
    )
    assert "Surrogacy Regulation Act 2021 section 4" in "\n".join(surrogacy[1:])

    election = asyncio.run(
        expand_query(
            "returning officer rejected my nomination for MLA election what remedy",
            max_variants=3,
        )
    )
    joined_election = "\n".join(election[1:])
    assert "Representation of the People Act 1951 section 33" in joined_election
    assert "section 36" in joined_election

    corrupt_election = asyncio.run(
        expand_query("booth capturing corrupt practice election petition to set aside result", max_variants=3)
    )
    joined_corrupt_election = "\n".join(corrupt_election[1:])
    assert "section 123" in joined_corrupt_election
    assert "section 100 election petition" in joined_corrupt_election

    false_affidavit_corrupt = asyncio.run(
        expand_query("candidate affidavit false assets corrupt practice election petition", max_variants=3)
    )
    joined_false_affidavit_corrupt = "\n".join(false_affidavit_corrupt[1:])
    assert "section 123" in joined_false_affidavit_corrupt
    assert "section 100 election petition" in joined_false_affidavit_corrupt

    false_affidavit_petition = asyncio.run(
        expand_query("candidate affidavit false assets election petition", max_variants=3)
    )
    joined_false_affidavit_petition = "\n".join(false_affidavit_petition[1:])
    assert "section 33A" in joined_false_affidavit_petition
    assert "section 125A" in joined_false_affidavit_petition
    assert "section 100 election petition" in joined_false_affidavit_petition

    hidden_case_petition = asyncio.run(
        expand_query("candidate hid criminal case in affidavit election petition", max_variants=3)
    )
    joined_hidden_case_petition = "\n".join(hidden_case_petition[1:])
    assert "section 33A" in joined_hidden_case_petition
    assert "section 125A" in joined_hidden_case_petition

    surrogacy_abortion = asyncio.run(
        expand_query("surrogacy abortion terminate pregnancy consent surrogate mother clinic forcing", max_variants=3)
    )
    joined_surrogacy_abortion = "\n".join(surrogacy_abortion[1:])
    assert "Surrogacy Regulation Act 2021 section 7 section 8 section 10" in joined_surrogacy_abortion
    assert "Medical Termination of Pregnancy Act 1971" in joined_surrogacy_abortion

    legacy_undertrial = asyncio.run(
        expand_query(
            "my brother undertrial in jail since 2021 trial not started what remedy for release",
            max_variants=3,
        )
    )
    joined_undertrial = "\n".join(legacy_undertrial[1:])
    assert "CrPC 1973 section 436A" in joined_undertrial
    assert "CrPC 1973 section 479" not in joined_undertrial


def test_legal_hyde_off_override_preserves_general_query(monkeypatch):
    query = "station not released my seized phone after case closed"
    monkeypatch.setenv("LEGAL_HYDE_MODE", "off")
    _clear_settings_cache()
    try:
        out = asyncio.run(expand_query(query, max_variants=1))
    finally:
        _clear_settings_cache()

    assert out == [query]


def test_legal_hyde_always_appends_retrieval_only_brief(monkeypatch):
    query = "INSURERER IS REJECTING MY CLAIM"
    monkeypatch.setenv("LEGAL_HYDE_MODE", "always")
    _clear_settings_cache()
    try:
        out = asyncio.run(expand_query(query, max_variants=1))
    finally:
        _clear_settings_cache()

    assert len(out) >= 2
    brief = out[-1].lower()
    assert "matter insurance claim" in brief
    assert "insurance ombudsman" in brief
    assert query.lower() in brief
    assert "you should" not in brief
    assert "file a complaint" not in brief


def test_legal_hyde_fallback_only_when_no_existing_variant(monkeypatch):
    query = "INSURERER IS REJECTING MY CLAIM"
    monkeypatch.setenv("LEGAL_HYDE_MODE", "fallback")
    monkeypatch.setattr("apps.api.query_expand._route_variants", lambda *args, **kwargs: [])
    _clear_settings_cache()
    try:
        out = asyncio.run(expand_query(query, max_variants=1))
    finally:
        _clear_settings_cache()

    assert len(out) == 2
    assert out[0] == query
    assert "matter insurance claim" in out[1].lower()


def test_legal_hyde_fallback_does_not_add_when_deterministic_variant_exists(monkeypatch):
    query = "INSURERER IS REJECTING MY CLAIM"
    monkeypatch.setenv("LEGAL_HYDE_MODE", "fallback")
    _clear_settings_cache()
    try:
        out = asyncio.run(expand_query(query, max_variants=1))
    finally:
        _clear_settings_cache()

    assert len(out) == 2
    assert not any("matter insurance" in variant.lower() for variant in out[1:])
