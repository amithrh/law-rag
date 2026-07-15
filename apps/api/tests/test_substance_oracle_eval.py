from __future__ import annotations

from scripts.eval_substance_oracle import (
    adjusted_expected_routes,
    authority_key_status,
    forbidden_term_in_text,
    primary_authority_status,
    score_rows,
    source_diagnosis,
    source_diagnoses,
    term_in_text,
)
from scripts.eval_timed_100 import expected_act_keys
from scripts.build_substance_oracle_set import primary_act_candidates


def test_term_in_text_handles_spacing_and_punctuation() -> None:
    assert term_in_text("default bail", "Ask for default-bail / statutory bail immediately.")
    assert term_in_text("account statement", "Keep the account\nstatement and SMS.")
    assert not term_in_text("consumer court", "Use the RBI Ombudsman first.")


def test_forbidden_terms_ignore_direct_safety_negation() -> None:
    safe = "You cannot force your wife. Use counselling or Family Court based on facts."
    unsafe = "You can force your wife because marriage gives a right to sex."

    assert not forbidden_term_in_text("force your wife", safe)
    assert forbidden_term_in_text("force your wife", unsafe)


def test_oracle_fails_structurally_polished_but_wrong_substance() -> None:
    prompt_rows = {
        "my bank account is frozen": {
            "query": "my bank account is frozen",
            "expected_route_any": ["banking_credit_dispute"],
            "expected_act_hint": "Banking Ombudsman + BNSS 2023",
            "oracle_priority": "critical",
            "oracle_id": "account_freeze_unknown_police",
            "oracle_harm_bucket": "banking_platform_money",
            "oracle": {
                "required_groups": [
                    {"name": "freeze_variant", "any": ["freeze", "frozen", "lien"]},
                    {"name": "banking_forum", "any": ["rbi", "ombudsman", "cms"]},
                    {"name": "police_cyber_step", "any": ["cyber", "police"]},
                ],
                "forbidden_any": ["only consumer court"],
            },
        }
    }
    eval_rows = [
        {
            "query": "my bank account is frozen",
            "route_category": "banking_credit_dispute",
            "relevance_verdict": "ok",
            "expected_act_hit": True,
            "expected_act_cited_hit": True,
            "first_cited_is_actionable": True,
            "answer_quality_flags": [],
            "answer_text": "File a complaint in consumer court for deficiency of service [1]. **What you can do next** File a consumer complaint.",
            "wall_ms": 1000,
        }
    ]

    scored = score_rows(eval_rows, prompt_rows)

    assert scored[0]["oracle_pass"] is False
    assert "missing_freeze_variant" in scored[0]["oracle_failures"]
    assert "missing_banking_forum" in scored[0]["oracle_failures"]
    assert "missing_police_cyber_step" in scored[0]["oracle_failures"]
    assert "answer_contract_gap" == scored[0]["source_diagnosis"]


def test_source_diagnosis_separates_retrieval_and_citation_gaps() -> None:
    assert source_diagnosis({"expected_act_hit": False}, []) == "retrieval_or_corpus_gap"
    assert source_diagnosis({"expected_act_hit": True, "expected_act_cited_hit": False}, []) == "retrieved_not_cited"
    assert (
        source_diagnosis(
            {"expected_act_hit": True, "expected_act_cited_hit": True},
            ["missing_forum"],
        )
        == "answer_contract_gap"
    )


def test_source_diagnoses_emit_multiple_applicable_causes() -> None:
    row = {
        "expected_act_hit": True,
        "expected_act_cited_hit": False,
        "top_sources": [
            {
                "title": "Reserve Bank - Integrated Ombudsman Scheme",
                "source_type": "guideline",
                "statute_short": "RBI Integrated Ombudsman Scheme",
            }
        ],
    }
    prompt = {"expected_primary_act_any": ["Banking Ombudsman"]}

    diagnoses = source_diagnoses(row, prompt, ["missing_forum"])

    assert "retrieved_not_cited" in diagnoses
    assert "answer_contract_gap" in diagnoses


def test_primary_authority_status_scores_any_primary_candidate_not_all_secondary_laws() -> None:
    row = {
        "query": "loan app is harassing my contacts",
        "retrieved_sources": [
            {
                "title": "Reserve Bank - Integrated Ombudsman Scheme",
                "source_type": "guideline",
                "statute_short": "RBI Integrated Ombudsman Scheme",
            }
        ],
        "cited_sources": [
            {
                "title": "Reserve Bank - Integrated Ombudsman Scheme",
                "source_type": "guideline",
                "statute_short": "RBI Integrated Ombudsman Scheme",
            }
        ],
        "expected_act_hit": False,
        "expected_act_cited_hit": False,
    }
    prompt = {"expected_primary_act_any": ["Banking Ombudsman"]}

    status = primary_authority_status(row, prompt)

    assert status["retrieved_hit"] is True
    assert status["cited_hit"] is True


def test_authority_key_status_finds_partial_visible_authorities() -> None:
    row = {
        "expected_act_keys": ["Banking Ombudsman", "BNSS"],
        "top_sources": [
            {
                "title": "Reserve Bank - Integrated Ombudsman Scheme",
                "anchor": "rbi-integrated-ombudsman-scheme/clause-8",
                "source_type": "guideline",
                "statute_short": "RBI Integrated Ombudsman Scheme",
            }
        ],
        "expected_act_hit": False,
    }

    status = authority_key_status(row)

    assert status["Banking Ombudsman"]["present_in_top_sources"] is True
    assert status["BNSS"]["present_in_top_sources"] is False
    assert source_diagnosis(row, []) == "partial_retrieval_or_corpus_gap"


def test_scst_primary_authority_handles_caste_name_without_splitting_slash() -> None:
    assert primary_act_candidates("SC/ST POA Act 1989 + BNS 2023") == ["SC/ST POA Act 1989"]
    assert expected_act_keys(
        "SC/ST POA Act 1989",
        "teacher beat girl in school using caste name principal not acting",
    ) == ["SC/ST POA Act"]


def test_witch_false_case_allows_accused_defence_route() -> None:
    row = {"query": "they say i am tonhi after child died false case chhattisgarh"}
    prompt = {
        "oracle_id": "witch_branding_tonhi",
        "expected_route_any": ["tribal_caste_atrocity", "police_fir"],
    }

    assert "criminal_defence_bail" in adjusted_expected_routes(row, prompt)
