from scripts.build_failure_ledger import classify, strict_product_failures


def test_strict_product_failures_count_safe_source_gap_as_not_production_ready():
    row = {
        "safe_source_gap": True,
        "expected_act_hit": False,
        "expected_act_cited_hit": False,
        "relevance_verdict": "ok",
        "legal_safety": {"hard_fail": False},
    }

    assert strict_product_failures(row) == ["safe_source_gap_not_production_ready"]


def test_failure_ledger_infers_priority_when_prompt_metadata_missing():
    row = {
        "query": "brother arrested uapa 90 days over no chargesheet default bail possible",
        "route_category": "criminal_defence_bail",
        "expected_category": "default_bail",
        "relevance_verdict": "partial",
        "expected_act_hit": True,
        "expected_act_cited_hit": True,
        "legal_safety": {"hard_fail": False},
        "product_failures": ["relevance_not_ok"],
    }

    item = classify(row, index=1)

    assert item["product_priority"] == "critical"
    assert item["harm_bucket"] == "criminal_procedure_high_risk"
    assert item["root_cause"] == "variant_answer_gap"


def test_failure_ledger_avoids_uapa_substring_collision_for_nuapada():
    row = {
        "query": "patwari changed mutation record giving my dadaji land to non tribal buyer nuapada odisha",
        "route_category": "tribal_caste_atrocity",
        "expected_category": "land_alienation",
        "relevance_verdict": "ok",
        "expected_act_hit": False,
        "expected_act_cited_hit": False,
        "safe_source_gap": True,
        "legal_safety": {"hard_fail": False},
    }

    item = classify(row, index=1)

    assert item["product_priority"] == "high"
    assert item["harm_bucket"] == "caste_tribal_state_harm"
    assert item["root_cause"] == "source_or_retrieval_gap"


def test_failure_ledger_avoids_hold_and_misdeclaration_substring_collisions():
    row = {
        "query": "icegate showing bill of entry on hold misdeclaration alleged chinese led lights",
        "route_category": "tax_gst_compliance",
        "expected_category": "customs",
        "relevance_verdict": "partial",
        "expected_act_hit": True,
        "expected_act_cited_hit": True,
        "legal_safety": {"hard_fail": False},
        "product_failures": ["relevance_not_ok"],
    }

    item = classify(row, index=1)

    assert item["product_priority"] == "medium"
    assert item["harm_bucket"] == "business_tax_procedure"
    assert item["variant_subtype"] == "customs"


def test_failure_ledger_avoids_esi_collision_inside_residence():
    row = {
        "query": "sasural waale mujhe ghar se nikal diya raat ko bina kuch diye kya main wapis ja sakti hoon",
        "route_category": "family_domestic",
        "expected_category": "domestic_violence_residence",
        "relevance_verdict": "partial",
        "expected_act_hit": True,
        "expected_act_cited_hit": True,
        "legal_safety": {"hard_fail": False},
        "product_failures": ["relevance_not_ok"],
    }

    item = classify(row, index=1)

    assert item["product_priority"] == "critical"
    assert item["harm_bucket"] == "family_child_safety"
    assert item["variant_subtype"] == "domestic_violence_residence"
