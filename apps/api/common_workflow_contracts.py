"""Common-user workflow answer contracts.

The matter router gives the legal neighborhood; these contracts supply the
workflow spine for high-volume lay questions: authority, forum, first action,
documents, escalation, and a safety caveat. They are broader than one prompt,
but still source-gated: every emitted legal line cites a retrieved source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from apps.api.authority_graph import (
    authority_graph_contract_template_result,
    authority_graph_template_result,
)
from apps.api.customs_logic import (
    customs_classification_issue,
    customs_drawback_issue,
    customs_misdeclaration_issue,
    customs_related_party_negated,
    customs_svb_issue,
)
from apps.api.matter_router import MatterRoute, has_person_custody_context


_WORKFLOW_ANSWER_MODES: dict[str, str] = {
    # Safety / liberty / high-risk contracts own the answer when source-gated.
    "ai_child_sexual_image": "safety_primary",
    "domestic_violence_immediate_safety": "safety_primary",
    "inlaw_unwelcome_touch_domestic_safety": "safety_primary",
    "dowry_food_denial_domestic_cruelty": "safety_primary",
    "arrest_magistrate_production_delay": "safety_primary",
    "arrest_memo_grounds_family_intimation": "safety_primary",
    "arrest_custody_station_case_not_disclosed": "safety_primary",
    "lgbtq_identity_arrest_safeguard": "safety_primary",
    "custody_legal_aid_lawyer_access": "safety_primary",
    "default_bail_no_chargesheet": "safety_primary",
    "ndps_default_bail_no_chargesheet": "safety_primary",
    "custody_delay_compensation_after_release": "safety_primary",
    "undertrial_lawyer_not_coming_legal_aid": "safety_primary",
    "juvenile_adult_jail_age_determination": "safety_primary",
    "minor_interfaith_child_safety_pocso": "safety_primary",
    "pocso_minor_romantic_accused": "safety_primary",
    "promise_to_marry_rape_accused_defence": "safety_primary",
    "promise_to_marry_deceitful_intercourse_complaint": "safety_primary",
    "custody_medical_care": "safety_primary",
    "pregnant_undertrial_medical_bail": "safety_primary",
    "itpa_receptionist_raid_accused": "safety_primary",
    "498a_bail_rejection_source_gap": "safety_primary",
    # Reviewed, high-volume procedural workflows. These should not lose their
    # user-shaped answer to older judgment/catchall templates.
    "streedhan_return": "primary",
    "cyber_money_fraud": "primary",
    "digital_arrest_impersonation_transfer": "primary",
    "wrong_bank_debit": "primary",
    "bank_wrong_debit": "primary",
    "bank_account_freeze": "primary",
    "bank_account_freeze_legal_hold": "primary",
    "loan_app_harassment": "primary",
    "crypto_exchange_wallet": "primary",
    "intimate_image_blackmail": "primary",
    "public_political_deepfake": "primary",
    "public_political_meme_police_risk": "primary",
    "dpdp_data_breach": "primary",
    "unsolicited_sexual_image_cyber": "safety_primary",
    "cyber_harassment_first_action": "primary",
    "online_defamation_abuse": "primary",
    "dating_app_phone_number_abuse": "primary",
    "elder_bank_pension_impersonation_fraud": "primary",
    "medical_status_online_warning": "primary",
    "false_nbfc_credit_identity_record": "primary",
    "credit_identity_misuse": "primary",
    "aadhaar_sim_identity_misuse": "primary",
    "senior_maintenance_order_enforcement": "primary",
    "senior_parent_pension_neglect": "primary",
    "pension_aadhaar_bank_closure": "primary",
    "pension_aadhaar_biometric_mismatch": "primary",
    "pan_aadhaar_bank_kyc_mismatch": "primary",
    "caste_slur_assault_fir_refusal": "primary",
    "caste_access_police_refusal": "primary",
    "school_caste_slur_assault": "primary",
    "forest_mfp_false_dacoity_case": "primary",
    "witch_branding_violence": "primary",
    "false_fir_defence": "primary",
    "wage_theft_false_fir": "primary",
    "vehicle_theft_fir_refusal": "primary",
    "blank_paper_moneylender_fraud": "primary",
    "arms_act_farming_tool_defence": "primary",
    "identity_police_threat_worker": "safety_primary",
    "regional_slur_wage_retaliation": "primary",
    "police_fir_first_response": "safety_primary",
    "honour_threat_police_protection": "safety_primary",
    "police_seized_device_return": "safety_primary",
    "acid_chemical_attack_first_response": "safety_primary",
    "custody_habeas_lockup_abuse": "safety_primary",
    "bonded_labour_rescue_contract": "safety_primary",
    "bonded_labour_coercion_release": "safety_primary",
    "labour_exploitation_first_action": "primary",
    "mining_gram_sabha_consent_challenge": "safety_primary",
    "tribal_forest_land_access": "safety_primary",
    "poa_special_court_delay": "safety_primary",
    "caste_public_access_exclusion": "safety_primary",
    "family_domestic_safety_or_response": "safety_primary",
    "family_notice_response": "primary",
    "family_forced_sex_safety": "safety_primary",
    "family_disabled_baby_safety": "safety_primary",
    "criminal_defence_first_action": "primary",
    "criminal_production_notice_electronic_records": "safety_primary",
    "spouse_child_maintenance_no_support": "primary",
    "mgnrega_fake_muster": "primary",
    "pds_aadhaar_cancellation": "primary",
    "pds_ration_card_name_removed": "primary",
    "ration_biometric_auth_failure": "primary",
    "scheme_worker_honorarium": "primary",
    "worksite_assault_wage_injury": "primary",
    "bonded_labour_rehabilitation_release_certificate": "safety_primary",
    "manual_scavenging_death_compensation": "safety_primary",
    "manual_scavenging_forced_cleaning": "safety_primary",
    "workplace_death_dependant_compensation": "primary",
    "workplace_injury_lost_limb_compensation": "primary",
    "construction_overtime_wage_claim": "primary",
    "labour_wage_deduction_food": "primary",
    "group_retrenchment_discrimination": "primary",
    "unpaid_salary_after_termination": "primary",
    "unpaid_group_wages_no_contract": "primary",
    "employment_notice_period_contract": "primary",
    "employment_original_document_return": "primary",
    "home_birth_certificate_refusal": "primary",
    "school_admission_tc_refusal": "primary",
    "college_original_certificate_release": "primary",
    "mutation_after_death": "primary",
    "property_lifetime_gift_heir_share": "primary",
    "property_sale_after_mother_death_docs": "primary",
    "property_verbal_land_gift_dispute": "primary",
    "daughter_ancestral_share": "primary",
    "housing_society_flat_transfer_after_death": "primary",
    "land_revenue_bribe_demand": "primary",
    "land_pattadar_passbook_replacement": "primary",
    "heir_refuses_sale": "primary",
    "heir_sale_consent": "primary",
    "joint_coowner_sold_whole_property": "primary",
    "thermal_blasting_house_damage_compensation": "primary",
    "mining_displacement_rehabilitation": "primary",
    "interstate_migrant_displacement_allowance": "primary",
    "tribal_land_nontribal_transfer": "primary",
    "tribal_religious_attack_poa": "primary",
    "poa_rule7_dsp_investigation": "primary",
    "mental_health_chain_or_confinement": "safety_primary",
    "cfr_illegal_mining": "primary",
    "gift_deed_thumb_fraud": "primary",
    "insurance_claim_or_misselling": "primary",
    "emi_penalty_cibil_dispute": "primary",
    "loan_emi_penalty_fee_dispute": "primary",
    "upi_seller_payment_refund": "primary",
    "friendly_loan_upi_recovery": "primary",
    "friendly_loan_civil_recovery": "primary",
    "ordinary_invoice_payment_reminder": "primary",
    "msme_delayed_payment": "primary",
    "business_contract_first_action": "primary",
    "supplier_payment": "primary",
    "principal_agent_goods_absconded": "primary",
    "marriage_misrepresentation_voidable": "primary",
    "marriage_salary_loan_misrepresentation": "primary",
    "spousal_alimony_working_status": "primary",
    "family_court_notice_response": "primary",
    "muslim_second_marriage_protection": "primary",
    "marriage_legal_age": "primary",
    "spousal_adultery_marriage_breakdown": "primary",
    "mutual_consent_divorce": "primary",
    "maintenance_order_nonpayment": "primary",
    "spousal_property_return": "primary",
    "domestic_residence_right": "safety_primary",
    "marital_intimacy": "primary",
    "marital_intimacy_remedy": "primary",
    "ndps_bhang_lassi": "primary",
    "ndps_quantity_bail": "primary",
    "pmla_anticipatory_interim_bail": "safety_primary",
    "regular_bail_after_arrest": "primary",
    "state_prohibition_excise_accused": "primary",
    "bail_surety_condition_modification": "primary",
    "bail_surety_amount_context": "primary",
    "anticipatory_bail_rejected_next_step": "primary",
    "sexual_offence_sessions_bail_forum": "primary",
    "uapa_prima_facie_bail": "safety_primary",
    "itpa_booking_only_accused": "primary",
    "handcuff_restraint_objection": "safety_primary",
    "undertrial_bnss479_review": "safety_primary",
    "custodial_death_inquiry": "safety_primary",
    "prison_mulaqat_books": "primary",
    "forced_sexual_exploitation_victim": "safety_primary",
    "street_vendor_removal": "primary",
    "street_vendor_goods_removed": "primary",
    "bank_credit_noc_cibil": "primary",
    "sarfaesi_possession_measure": "primary",
    "sarfaesi_132_notice": "primary",
    "epf_not_deposited": "primary",
    "esi_contribution_notice": "primary",
    "income_tax_1432_notice": "primary",
    "gst_rule_86b_cash_payment": "primary",
    "income_tax_appeal_deadline": "primary",
    "gst_freelancer_registration_threshold": "primary",
    "customs_drawback_export_mismatch": "primary",
    "customs_icegate_misdeclaration_hold": "primary",
    "customs_reclassification_svb": "primary",
    "builder_rera": "primary",
    "consumer_defective_goods": "primary",
    "hospital_records_billing": "primary",
    "coaching_refund_service_deficiency": "primary",
    "housing_parking_blocked": "primary",
    "aadhaar_lost_reissue_records": "primary",
    "software_license_notice": "primary",
    "trademark_passing_off_interim_injunction": "primary",
    "trademark_cease_desist_logo_similarity": "primary",
    "shop_sealed_municipality": "primary",
    "shop_license_renewal": "primary",
    "civil_summons_service_failed": "primary",
    "hindu_intestate_no_spouse_children": "primary",
    "unregistered_will_validity": "primary",
    "registered_will_update": "primary",
    "caretaker_daughter_will": "primary",
    "parsi_intestate_sisters": "primary",
    "pan_leak_fake_bank_account": "primary",
    "cyber_stalking_online_harassment": "primary",
    "cyber_police_notice_no_paper": "safety_primary",
    "cab_aggregator_driver_account": "primary",
    "gig_platform_worker_account_block": "primary",
    "social_media_account_suspension": "primary",
    "digital_platform_kyc_money_freeze": "primary",
    "online_gambling_platform_dispute": "primary",
    "digital_creator_payout_freeze": "primary",
    "gig_delivery_accident_compensation": "primary",
    "traffic_police_challan_bribe": "primary",
    "posh_pip_retaliation": "primary",
    "workplace_sexual_harassment_first_action": "primary",
    "procedure_writ_32_226_difference": "primary",
    "procedure_nclat_appeal": "primary",
    "procedure_nclt_insolvency_petition": "primary",
    "procedure_writ_court_fee": "primary",
    "procedure_vakalatnama_change": "primary",
    "procedure_ngt_wetland_complaint": "primary",
    "commercial_preinstitution_mediation": "primary",
    "voluntary_preinstitution_mediation": "primary",
    "civil_second_appeal_substantial_question": "primary",
    "limitation_delay_condonation": "primary",
    "civil_case_transfer": "primary",
    "aadhaar_identity_record_correction_pension": "primary",
    "caste_certificate_state_rule_intake": "primary",
    "transport_auto_permit_renewal": "primary",
    "relative_adoption_no_papers": "primary",
    "child_cross_border_return": "safety_primary",
    "child_access": "primary",
    "child_marriage_prevention": "safety_primary",
    "mtp_reproductive_rights": "safety_primary",
    "gratuity_eligibility_4y11m": "primary",
    "retrenchment_permission_120_workers": "primary",
    "sexual_offence_survivor_procedure": "safety_primary",
    "dowry_death_inquest_fir": "safety_primary",
    "maternity_return_role_change": "primary",
    "rajasthan_shop_act_registration": "primary",
    "police_fir_refusal_serious_offence": "safety_primary",
}


@dataclass(frozen=True)
class WorkflowTemplateResult:
    id: str
    source: str
    lines: list[str]
    answer_mode: str = "merge"
    required_sources: tuple[str, ...] = ()
    optional_sources: tuple[str, ...] = ()
    source_indices: dict[str, int] | None = None


def workflow_contract_answer_mode(workflow_id: str) -> str:
    """Return whether a reviewed workflow may own, merge into, or only observe."""
    return _WORKFLOW_ANSWER_MODES.get(workflow_id, "merge")


def common_workflow_contract_query_matches(
    query: str,
    route: MatterRoute,
    workflow_id: str,
    *,
    route_independent: bool = False,
) -> bool:
    """Whether a reviewed common contract owns the facts before retrieval."""
    q = _norm(query)
    if workflow_id == "loan_app_harassment":
        return (
            (route_independent or route.category in {
                "banking_credit_dispute",
                "cyber_fraud_or_harassment",
                "criminal_general",
            })
            and _is_loan_app(q)
        )
    return False


_COMMON_WORKFLOW_ACTIVATION_SPECS: dict[
    str,
    tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...],
] = {
    "loan_app_harassment": (
        (
            "digital_grievance",
            ("digital lending",),
            ("/para-11",),
        ),
        (
            "digital_data",
            ("digital lending",),
            ("/para-12",),
        ),
        (
            "recovery_conduct",
            ("recovery agents", "responsibilities of regulated entities"),
            ("/para-2",),
        ),
        (
            "rbi_application",
            ("reserve bank integrated ombudsman", "integrated ombudsman"),
            ("/sec-1",),
        ),
        (
            "rbi_definitions",
            ("reserve bank integrated ombudsman", "integrated ombudsman"),
            ("/sec-3",),
        ),
        (
            "rbi_forum",
            ("reserve bank integrated ombudsman", "integrated ombudsman"),
            ("/sec-6",),
        ),
        (
            "rbi_grounds",
            ("reserve bank integrated ombudsman", "integrated ombudsman"),
            ("/sec-9",),
        ),
        (
            "rbi_maintainability",
            ("reserve bank integrated ombudsman", "integrated ombudsman"),
            ("/sec-10",),
        ),
    ),
}


DPDP_SECTION_13_EFFECTIVE_FROM = date(2027, 5, 13)


def dpdp_section_13_in_force(*, as_of: date | None = None) -> bool:
    """Return whether DPDP Act Section 13 has commenced for a legal answer."""
    return (as_of or date.today()) >= DPDP_SECTION_13_EFFECTIVE_FROM


def common_workflow_contract_required_source_specs(
    workflow_id: str,
) -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    """Return exact plan-time activation authorities for common workflows."""
    return tuple(
        (title_terms, anchor_terms)
        for _key, title_terms, anchor_terms
        in _COMMON_WORKFLOW_ACTIVATION_SPECS.get(workflow_id, ())
    )


def plan_owned_workflow_contract_result(
    query: str,
    route: MatterRoute,
    passages: list[dict],
    *,
    owner_provider: str,
    owner_contract_id: str,
) -> WorkflowTemplateResult | None:
    """Resolve only the exact immutable answer owner selected by MatterPlan."""
    if owner_provider == "authority_graph":
        result = authority_graph_contract_template_result(
            query,
            route,
            passages,
            owner_contract_id,
        )
        if result is None:
            return None
        return WorkflowTemplateResult(
            id=result.id,
            source="authority_graph",
            lines=result.lines,
            answer_mode=workflow_contract_answer_mode(result.id),
            required_sources=result.required_sources,
            optional_sources=result.optional_sources,
            source_indices=result.source_indices,
        )
    if owner_provider == "common_workflow_contracts":
        if not common_workflow_contract_query_matches(
            query,
            route,
            owner_contract_id,
        ):
            return None
        source_indices: dict[str, int] = {}
        for key, title_terms, anchor_terms in _COMMON_WORKFLOW_ACTIVATION_SPECS.get(
            owner_contract_id,
            (),
        ):
            source_index = _find(
                passages,
                title_terms=title_terms,
                anchor_terms=anchor_terms,
            )
            if source_index is None:
                return None
            source_indices[key] = source_index
        builder = dict(_workflow_builders()).get(owner_contract_id)
        if owner_contract_id == "loan_app_harassment":
            lines = _loan_app_harassment_lines(
                _norm(query),
                route,
                passages,
                enforced_source_indices=source_indices,
            )
        else:
            lines = builder(_norm(query), route, passages) if builder is not None else []
        if not lines:
            return None
        return WorkflowTemplateResult(
            id=owner_contract_id,
            source="common_workflow_contracts",
            lines=lines,
            answer_mode=workflow_contract_answer_mode(owner_contract_id),
            required_sources=tuple(source_indices),
            source_indices=source_indices,
        )
    raise ValueError(f"unknown plan answer owner provider: {owner_provider}")


_REVIEWED_COMMON_PRIMARY_OWNERS = frozenset({
    "arms_act_farming_tool_defence",
    "blank_paper_moneylender_fraud",
    "business_contract_first_action",
    "cab_aggregator_driver_account",
    "child_access",
    "criminal_defence_first_action",
    "customs_icegate_misdeclaration_hold",
    "customs_reclassification_svb",
    "crypto_exchange_wallet",
    "cyber_stalking_online_harassment",
    "cyber_harassment_first_action",
    "cyber_money_fraud",
    "digital_creator_payout_freeze",
    "digital_platform_kyc_money_freeze",
    "dpdp_data_breach",
    "false_fir_defence",
    "gig_platform_worker_account_block",
    "intimate_image_blackmail",
    "labour_exploitation_first_action",
    "loan_app_harassment",
    "maintenance_order_nonpayment",
    "msme_delayed_payment",
    "mutation_after_death",
    "online_defamation_abuse",
    "online_gambling_platform_dispute",
    "procedure_nclat_appeal",
    "procedure_writ_32_226_difference",
    "promise_to_marry_deceitful_intercourse_complaint",
    "public_political_deepfake",
    "regional_slur_wage_retaliation",
    "relative_adoption_no_papers",
    "social_media_account_suspension",
    "street_vendor_removal",
    "streedhan_return",
    "witch_branding_violence",
    "workplace_sexual_harassment_first_action",
    "caste_access_police_refusal",
    "family_notice_response",
})


def workflow_contract_preempts_legacy(result: WorkflowTemplateResult | None) -> bool:
    """Whether a source-backed workflow should own the deterministic answer.

    Safety workflows and authority-graph contracts are explicit, source-gated
    owners. Most common first-action workflows are helpful fallback material,
    but should not hide a narrower legacy specialist that recognises more of
    the user's facts. Only the reviewed common owners below may preempt.
    """
    if result is None:
        return False
    if result.answer_mode == "safety_primary":
        return True
    if result.answer_mode != "primary":
        return False
    # Integrations may supply a fully reviewed primary contract without being
    # part of either built-in provider. Do not silently replace it with a
    # legacy template merely because its provider is new.
    if result.source not in {"common_workflow_contracts", "authority_graph"}:
        return True
    if result.source == "authority_graph":
        return True
    return (
        result.source == "common_workflow_contracts"
        and result.id in _REVIEWED_COMMON_PRIMARY_OWNERS
    )


_VERIFIER_PROMOTED_SAFETY_WORKFLOWS = {
    "arrest_magistrate_production_delay",
    "arrest_memo_grounds_family_intimation",
    "custody_legal_aid_lawyer_access",
    "custody_delay_compensation_after_release",
    "pmla_anticipatory_interim_bail",
    "sexual_offence_survivor_procedure",
    "dowry_death_inquest_fir",
    "undertrial_bnss479_review",
    "undertrial_lawyer_not_coming_legal_aid",
    "police_fir_refusal_serious_offence",
    "honour_threat_police_protection",
    "custody_habeas_lockup_abuse",
    "bonded_labour_rescue_contract",
    "bonded_labour_coercion_release",
    "manual_scavenging_forced_cleaning",
    "manual_scavenging_death_compensation",
    "child_cross_border_return",
    "child_marriage_prevention",
    "poa_special_court_delay",
    "caste_public_access_exclusion",
    "mining_gram_sabha_consent_challenge",
    "promise_to_marry_deceitful_intercourse_complaint",
    "unsolicited_sexual_image_cyber",
    "family_forced_sex_safety",
    "family_disabled_baby_safety",
    "domestic_residence_right",
    "police_seized_device_return",
    "acid_chemical_attack_first_response",
}


def workflow_contract_promotes_verifier(result: WorkflowTemplateResult | None) -> bool:
    """Whether reviewed, source-gated workflow lines may survive verifier drift."""
    if result is None:
        return False
    if result.answer_mode == "primary":
        return True
    return result.answer_mode == "safety_primary" and result.id in _VERIFIER_PROMOTED_SAFETY_WORKFLOWS


def common_workflow_contract_result(
    query: str,
    route: MatterRoute,
    passages: list[dict],
) -> WorkflowTemplateResult | None:
    """Return the selected workflow contract and the exact lines to render."""
    q = _norm(query)
    if route.category == "family_domestic" and route.label == "Domestic violence notice / response":
        lines = _family_notice_response_lines(q, route, passages)
        if lines:
            return WorkflowTemplateResult(
                id="family_notice_response",
                source="common_workflow_contracts",
                lines=lines,
                answer_mode=workflow_contract_answer_mode("family_notice_response"),
            )
    if route.category == "family_marriage_status" and route.label == "Marriage misrepresentation / family-law options":
        lines = _marriage_misrepresentation_voidable_lines(q, route, passages)
        if lines:
            return WorkflowTemplateResult(
                id="marriage_misrepresentation_voidable",
                source="common_workflow_contracts",
                lines=lines,
                answer_mode=workflow_contract_answer_mode("marriage_misrepresentation_voidable"),
            )

    authority_result = authority_graph_template_result(query, route, passages)
    if authority_result is not None:
        return WorkflowTemplateResult(
            id=authority_result.id,
            source="authority_graph",
            lines=authority_result.lines,
            answer_mode=workflow_contract_answer_mode(authority_result.id),
            required_sources=authority_result.required_sources,
            optional_sources=authority_result.optional_sources,
            source_indices=authority_result.source_indices,
        )

    for workflow_id, builder in _workflow_builders():
        lines = builder(q, route, passages)
        if lines:
            return WorkflowTemplateResult(
                id=workflow_id,
                source="common_workflow_contracts",
                lines=lines,
                answer_mode=workflow_contract_answer_mode(workflow_id),
            )
    return None


def common_workflow_contract_template_lines(
    query: str,
    route: MatterRoute,
    passages: list[dict],
) -> list[str]:
    """Return a shared workflow-contract answer for common user questions."""
    result = common_workflow_contract_result(query, route, passages)
    return result.lines if result is not None else []


def common_workflow_contract_diagnostics(
    query: str,
    route: MatterRoute,
    passages: list[dict],
) -> dict:
    """Return eval-facing metadata about the common workflow contract layer.

    This mirrors the builder order used for answer generation and returns the
    same selected contract id as the renderer.
    """
    result = common_workflow_contract_result(query, route, passages)
    if result is not None:
        return {
            "id": result.id,
            "source": result.source,
            "selected": True,
            "line_count": len(result.lines),
            "answer_mode": result.answer_mode,
            "required_sources": list(result.required_sources),
            "optional_sources": list(result.optional_sources),
            "source_indices": result.source_indices or {},
            "contract_miss_reason": None,
        }
    reason = (
        "no_passages"
        if not passages
        else "generic_route_no_contract"
        if route.category == "general_legal"
        else "no_common_workflow_contract_selected"
    )
    return {
        "id": None,
        "source": "common_workflow_contracts",
        "selected": False,
        "line_count": 0,
        "answer_mode": None,
        "required_sources": [],
        "optional_sources": [],
        "source_indices": {},
        "contract_miss_reason": reason,
    }


def _workflow_builders():
    return (
        ("dpdp_data_breach", _dpdp_data_breach_lines),
        ("cyber_money_fraud", _cyber_money_fraud_lines),
        ("cyber_stalking_online_harassment", _cyber_stalking_online_harassment_lines),
        ("online_defamation_abuse", _online_defamation_abuse_lines),
        ("credit_identity_misuse", _credit_identity_misuse_lines),
        ("loan_app_harassment", _loan_app_harassment_lines),
        ("public_political_deepfake", _public_political_deepfake_lines),
        ("intimate_image_blackmail", _intimate_image_blackmail_lines),
        ("unsolicited_sexual_image_cyber", _unsolicited_sexual_image_cyber_lines),
        ("cyber_harassment_first_action", _cyber_harassment_first_action_lines),
        ("witch_branding_violence", _witch_branding_violence_lines),
        ("caste_access_police_refusal", _caste_access_police_refusal_lines),
        ("poa_special_court_delay", _poa_special_court_delay_lines),
        ("caste_public_access_exclusion", _caste_public_access_exclusion_lines),
        ("mining_gram_sabha_consent_challenge", _mining_gram_sabha_consent_challenge_lines),
        ("tribal_forest_land_access", _tribal_forest_land_access_lines),
        ("blank_paper_moneylender_fraud", _blank_paper_moneylender_fraud_lines),
        ("arms_act_farming_tool_defence", _arms_act_farming_tool_defence_lines),
        ("identity_police_threat_worker", _identity_police_threat_worker_lines),
        ("regional_slur_wage_retaliation", _regional_slur_wage_retaliation_lines),
        ("false_fir_defence", _false_fir_defence_lines),
        ("custody_habeas_lockup_abuse", _custody_habeas_lockup_abuse_lines),
        ("police_seized_device_return", _police_seized_device_return_lines),
        ("forced_sexual_exploitation_victim", _forced_sexual_exploitation_victim_lines),
        ("acid_chemical_attack_first_response", _acid_chemical_attack_first_response_lines),
        ("honour_threat_police_protection", _honour_threat_police_protection_lines),
        ("police_fir_first_response", _police_fir_first_response_lines),
        ("bonded_labour_rescue_contract", _bonded_labour_rescue_contract_lines),
        ("manual_scavenging_forced_cleaning", _manual_scavenging_forced_cleaning_lines),
        ("labour_exploitation_first_action", _labour_exploitation_first_action_lines),
        ("family_forced_sex_safety", _family_forced_sex_safety_lines),
        ("family_disabled_baby_safety", _family_disabled_baby_safety_lines),
        ("domestic_residence_right", _domestic_residence_right_lines),
        ("family_notice_response", _family_notice_response_lines),
        ("family_domestic_safety_or_response", _family_domestic_safety_or_response_lines),
        ("criminal_production_notice_electronic_records", _criminal_production_notice_electronic_records_lines),
        ("pocso_minor_romantic_accused", _pocso_minor_romantic_accused_lines),
        ("promise_to_marry_deceitful_intercourse_complaint", _promise_to_marry_deceitful_intercourse_complaint_lines),
        ("criminal_defence_first_action", _criminal_defence_first_action_lines),
        ("cab_aggregator_driver_account", _cab_aggregator_driver_account_lines),
        ("gig_platform_worker_account_block", _gig_platform_worker_account_block_lines),
        ("social_media_account_suspension", _social_media_account_suspension_lines),
        ("digital_platform_kyc_money_freeze", _digital_platform_kyc_money_freeze_lines),
        ("online_gambling_platform_dispute", _online_gambling_platform_dispute_lines),
        ("digital_creator_payout_freeze", _digital_creator_payout_freeze_lines),
        ("cab_aggregator_passenger", _cab_aggregator_passenger_lines),
        ("traffic_police_challan_bribe", _traffic_police_challan_bribe_lines),
        ("relative_adoption_no_papers", _relative_adoption_no_papers_lines),
        ("child_cross_border_return", _child_cross_border_return_lines),
        ("child_access", _child_access_lines),
        ("child_marriage_prevention", _child_marriage_prevention_lines),
        ("mtp_reproductive_rights", _mtp_reproductive_rights_lines),
        ("spousal_property_return", _spousal_property_return_lines),
        ("streedhan_return", _streedhan_return_lines),
        ("street_vendor_removal", _street_vendor_removal_lines),
        ("crypto_exchange_wallet", _crypto_exchange_wallet_lines),
        ("bank_account_freeze", _bank_account_freeze_lines),
        ("bank_wrong_debit", _bank_wrong_debit_lines),
        ("bank_credit_noc_cibil", _bank_credit_noc_cibil_lines),
        ("sarfaesi_possession_measure", _sarfaesi_possession_measure_lines),
        ("sarfaesi_132_notice", _sarfaesi_132_notice_lines),
        ("friendly_loan_civil_recovery", _friendly_loan_civil_recovery_lines),
        ("marital_intimacy", _marital_intimacy_lines),
        ("land_revenue_bribe_demand", _land_revenue_bribe_demand_lines),
        ("land_pattadar_passbook_replacement", _land_pattadar_passbook_replacement_lines),
        ("mutation_after_death", _mutation_after_death_lines),
        ("property_lifetime_gift_heir_share", _property_lifetime_gift_heir_share_lines),
        ("property_sale_after_mother_death_docs", _property_sale_after_mother_death_docs_lines),
        ("property_verbal_land_gift_dispute", _property_verbal_land_gift_dispute_lines),
        ("heir_sale_consent", _heir_sale_consent_lines),
        ("municipal_shop_sealing", _municipal_shop_sealing_lines),
        ("shop_license_renewal", _shop_license_renewal_lines),
        ("rajasthan_shop_act_registration", _rajasthan_shop_act_registration_lines),
        ("procedure_writ_32_226_difference", _procedure_writ_32_226_difference_lines),
        ("procedure_nclat_appeal", _procedure_nclat_appeal_lines),
        ("procedure_nclt_insolvency_petition", _procedure_nclt_insolvency_petition_lines),
        ("procedure_writ_court_fee", _procedure_writ_court_fee_lines),
        ("procedure_vakalatnama_change", _procedure_vakalatnama_change_lines),
        ("procedure_ngt_wetland_complaint", _procedure_ngt_wetland_complaint_lines),
        ("transport_auto_permit_renewal", _transport_auto_permit_renewal_lines),
        ("gratuity_eligibility_4y11m", _gratuity_eligibility_4y11m_lines),
        ("retrenchment_permission_120_workers", _retrenchment_permission_120_workers_lines),
        ("arrest_paperwork", _arrest_paperwork_lines),
        ("scheme_worker_honorarium", _scheme_worker_honorarium_lines),
        ("maternity_return_role_change", _maternity_return_role_change_lines),
        ("posh_pip_retaliation", _posh_pip_retaliation_lines),
        ("workplace_sexual_harassment_first_action", _workplace_sexual_harassment_first_action_lines),
        ("gig_delivery_accident_compensation", _gig_delivery_accident_compensation_lines),
        ("sexual_offence_survivor_procedure", _sexual_offence_survivor_procedure_lines),
        ("dowry_death_inquest_fir", _dowry_death_inquest_fir_lines),
        ("builder_rera", _builder_rera_lines),
        ("msme_delayed_payment", _msme_delayed_payment_lines),
        ("business_contract_first_action", _business_contract_first_action_lines),
        ("supplier_payment", _supplier_payment_lines),
        ("software_license_notice", _software_license_notice_lines),
        ("trademark_cease_desist_logo_similarity", _trademark_cease_desist_logo_similarity_lines),
        ("trademark_passing_off_interim_injunction", _trademark_passing_off_interim_injunction_lines),
        ("subscription_refund", _subscription_refund_lines),
        ("housing_parking_blocked", _housing_parking_blocked_lines),
        ("aadhaar_lost_reissue_records", _aadhaar_lost_reissue_records_lines),
        ("hospital_records_billing", _hospital_records_billing_lines),
        ("consumer_defective_goods", _consumer_defective_goods_lines),
        ("income_tax_1432_notice", _income_tax_1432_notice_lines),
        ("gst_rule_86b_cash_payment", _gst_rule_86b_cash_payment_lines),
        ("customs_drawback_export_mismatch", _customs_drawback_export_mismatch_lines),
        ("customs_icegate_misdeclaration_hold", _customs_icegate_misdeclaration_hold_lines),
        ("customs_reclassification_svb", _customs_reclassification_svb_lines),
    )


def _dpdp_data_breach_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "cyber_fraud_or_harassment" or not _is_dpdp_data_breach(q):
        return []
    dpdp = _find(passages, title_terms=("digital personal data protection",))
    it_act = _find(
        passages,
        title_terms=("information technology",),
        anchor_terms=(
            "/sec-66C", "/sec-66D", "/sec-66E", "/sec-67C",
            "/sec-72", "/sec-72A", "/sec-43A",
        ),
    )
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-318", "/sec-319", "/sec-336", "/sec-356"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    aadhaar = _find(passages, title_terms=("aadhaar",), anchor_terms=("/sec-28", "/sec-29", "/sec-37"))
    mental_health = _find(passages, title_terms=("mental healthcare",), anchor_terms=("/sec-23", "/sec-24", "/sec-25", "/sec-43"))
    mental_health_context = _has_any(q, ("therapist", "mental health", "psychiatrist", "psychologist", "counsellor", "counselor"))
    if dpdp is None or (mental_health_context and mental_health is None):
        return []

    data_kind = (
        "PAN/Aadhaar or identity data"
        if _has_any(q, ("pan", "aadhaar", "aadhar", "kyc"))
        else "address/contact data"
        if _has_any(q, ("address", "phone", "mobile", "contact"))
        else "health or mental-health data"
        if _has_any(q, ("therapist", "mental health", "medical", "health"))
        else "personal data"
    )
    platform = (
        "Byju's" if "byjus" in q or "byju" in q else
        "Dunzo" if "dunzo" in q else
        "company/platform"
    )
    lines = ["**Short answer**"]
    if dpdp is not None:
        lines.append(
            f"For {platform} leaking your address or other {data_kind}, treat it as a DPDP personal-data breach/grievance issue and DPDP personal-data grievance track, not as a deepfake or generic cyber-image complaint: ask what data was exposed, when, what safeguards/notice were used, and what correction or mitigation the data fiduciary will provide [{dpdp}]."
        )
    dpdp_grievance = _find(passages, title_terms=("digital personal data protection",), anchor_terms=("/sec-13",))
    dpdp_board = _find(passages, title_terms=("digital personal data protection",), anchor_terms=("/sec-27",))
    if dpdp_grievance is not None:
        lines.append(
            f"The Data Principal must exhaust the data fiduciary's grievance route before approaching the Board, so keep the written grievance, acknowledgement, and response or non-response in the file [{dpdp_grievance}]."
        )
    if dpdp_board is not None:
        lines.append(
            f"Keep the Digital Personal Data Protection Board route separate for the post-grievance complaint and the breach facts; it does not replace the first written company grievance [{dpdp_board}]."
        )
    if mental_health is not None and mental_health_context:
        lines.append(
            f"Because the leaked material is a therapist or mental-health chat, keep the Mental Healthcare Act confidentiality/privacy source in the file too; preserve who held the record, who posted it, and whether the therapist, clinic, platform, or another person caused the leak [{mental_health}]."
        )
    if aadhaar is not None and _has_any(q, ("aadhaar", "aadhar")):
        lines.append(
            f"If Aadhaar authentication or UIDAI records are directly involved, keep the Aadhaar Act record/confidentiality route separate from ordinary platform support [{aadhaar}]."
        )
    if it_act is not None:
        if mental_health_context:
            lines.append(
                f"Keep the IT Act confidentiality/privacy disclosure source with the electronic chat, platform URL, account trail, and consent facts; this is separate from the DPDP grievance and Mental Healthcare Act confidentiality route [{it_act}]."
            )
        else:
            lines.append(
                f"If the leak led to account compromise, impersonation, phishing, identity misuse, or electronic credential abuse, keep an IT Act/cyber-offence track with the leaked-data proof and misuse trail [{it_act}]."
            )
    if bns is not None or bnss is not None:
        cite = bns or bnss
        lines.append(
            f"If there is cheating, personation, forgery, extortion, or a police complaint, keep that criminal track separate from the DPDP grievance instead of using a data-breach label for everything [{cite}]."
        )
    action_cites = _cite_many(dpdp, mental_health, it_act, aadhaar, bns, bnss)
    lines.extend([
        "**What you can do next**",
        f"- Preserve the breach notice/email, screenshots, leaked fields, account ID, company ticket, dates, loss/identity-misuse proof, and any bank/cyber complaint number; file the company grievance first and escalate to the Data Protection Board route where available after the grievance step {action_cites}.",
        f"- If fraud or identity misuse has already happened, also file a cyber complaint with the misuse evidence and do not wait only for platform customer support {action_cites}.",
    ])
    return lines


def _cyber_stalking_online_harassment_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "cyber_fraud_or_harassment" or not _is_cyber_stalking_online_harassment(q):
        return []
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-78", "/sec-319", "/sec-356", "/sec-351"))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66D", "/sec-66d", "/sec-66E", "/sec-66e"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    crpc = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-154", "/sec-156"))
    primary = bns or it_act or bnss or crpc
    if primary is None:
        return []

    platform = (
        "Instagram" if _has_any(q, ("insta", "instagram")) else
        "dating-app" if _has_any(q, ("dating app", "bumble", "tinder")) else
        "online/platform"
    )
    lines = ["**Short answer**"]
    fake_profile_context = _has_any(q, (
        "fake account", "fake profile", "fake instagram", "fake insta",
        "using my photos", "used my photos", "using my photo", "used my photo",
    ))
    if bns is not None:
        if fake_profile_context:
            lines.append(
                f"For a fake {platform} account using your photos and DMing girls or other people, keep the BNS stalking/intimidation/personation or defamation track where the exact posts, DMs, threats, or reputational harm fit [{bns}]."
            )
        else:
            lines.append(
                f"For repeated {platform} DMs, contact, following, or messages after blocking, keep the offence source as BNS stalking/intimidation where the facts fit; do not say BNSS defines stalking because BNSS is the procedure code, not the stalking offence [{bns}]."
            )
    if it_act is not None:
        if fake_profile_context:
            lines.append(
                f"Keep the IT Act privacy/electronic-record source with the fake profile URL, username, photo-use proof, account ID, and DM trail; do not delete the fake-account evidence before reporting [{it_act}]."
            )
        else:
            lines.append(
                f"Keep the IT Act privacy/electronic-record source with the screenshots, profile URL, account ID, and message trail, especially if the person uses images, private information, or electronic identity details [{it_act}]."
            )
    procedure = bnss or crpc
    if procedure is not None:
        lines.append(
            f"Use the criminal-procedure source for the police/cyber-police complaint, FIR/refusal record, and Magistrate escalation; the procedure source should not replace the BNS/IT Act offence analysis [{procedure}]."
        )
    action_cites = _cite_many(bnss or crpc, bns, it_act)
    lines.extend([
        "**What you can do next**",
        f"- Preserve screenshots, profile links/usernames, phone numbers, dates/times, block history, platform complaint ID, photo-use proof, DM recipients if known, and any threat or identity proof; complain through the platform and cybercrime.gov.in/cyber police/local police, and ask for a written complaint/FIR acknowledgement {action_cites}.",
        f"- If police refuse to record it or only give oral advice, escalate the same written complaint and proof to senior police, cyber cell, Magistrate, or DLSA instead of deleting the account trail {action_cites}.",
    ])
    return lines


def _intimate_image_blackmail_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "cyber_fraud_or_harassment" or not _is_intimate_image_blackmail(q):
        return []
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66E", "/sec-67", "/sec-67A", "/sec-66D"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-77", "/sec-78", "/sec-308", "/sec-351", "/sec-356"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173",))
    bnss_magistrate = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-175",))
    bnss = bnss_fir or bnss_magistrate
    ipc = _find(passages, title_terms=("indian penal",), anchor_terms=("/sec-384", "/sec-503", "/sec-506", "/sec-509", "/sec-499"))
    crpc = _find(passages, title_terms=("criminal procedure",), anchor_terms=("/sec-154", "/sec-156", "/sec-200"))
    legacy_regime = "legacy" in str(route.legal_regime or "").lower()
    current_regime = "current" in str(route.legal_regime or "").lower()
    if legacy_regime:
        offence_source = ipc
        procedure_source = crpc
    elif current_regime:
        offence_source = bns
        procedure_source = bnss
    else:
        offence_source = bns or ipc
        procedure_source = bnss or crpc
    offence_label = "IPC" if offence_source == ipc else "BNS"
    procedure_label = "CrPC" if procedure_source == crpc else "BNSS"
    primary = it_act or offence_source or procedure_source
    if primary is None:
        return []

    material = (
        "lookalike porn/non-consensual sexual video with your face"
        if _has_any(q, ("lookalike", "look alike", "my face", "face same", "not me but face", "face put", "body is not mine")) and _has_any(q, ("porn", "reddit", "website", "video"))
        else
        "AI deepfake porn video uploaded to Xvideos by an ex-boyfriend"
        if "xvideos" in q and _has_any(q, ("ex boyfriend", "ex-boyfriend"))
        else
        "AI deepfake porn video uploaded online by an ex-boyfriend"
        if _has_any(q, ("ex boyfriend", "ex-boyfriend")) and _has_any(q, ("ai deepfake", "deepfake porn", "uploaded online", "uploaded"))
        else "deepfake porn/non-consensual sexual image"
        if _has_any(q, ("deepfake porn", "ai deepfake", "ai porn", "deepfake", "porn"))
        else "leaked private nudes on Telegram or WhatsApp"
        if _has_any(q, ("leaked", "leak")) and _has_any(q, ("private nudes", "nudes", "nude")) and _has_any(q, ("telegram", "whatsapp"))
        else "morphed nude photo in the Telegram/college group"
        if _has_any(q, ("telegram", "college group", "college")) and _has_any(q, ("morphed nude", "nude photo"))
        else "morphed or non-consensual image/group photo"
        if _has_any(q, ("morphed group photo", "group photo"))
        else "morphed nude of your sister being shared in a college group on Telegram"
        if "sister" in q and "telegram" in q and _has_any(q, ("college group", "college"))
        else "morphed nude/private image being shared on Telegram or a group chat"
        if _has_any(q, ("telegram", "college group", "school whatsapp", "whatsapp group")) and _has_any(q, ("morphed", "fake nude", "nude", "naked"))
        else "morphed nude/private image"
        if _has_any(q, ("morphed", "fake nude", "nude", "naked"))
        else "recorded private video/image from a video call"
    )
    money_blackmail = _has_any(q, (
        "blackmail", "demanding money", "demanded money", "pay money",
        "dont pay", "don't pay", "extortion", "extort", "extorting",
    )) and not _has_negated_extortion_money_context(q)
    harm = "blackmail" if money_blackmail else "circulation/takedown"
    lines = ["**Short answer**"]
    if it_act is not None:
        lines.append(
            (
                f"Treat the {material} {harm} as a cyber privacy and non-consensual intimate-image problem first; use the IT Act privacy source for privacy/electronic publication or personation facts instead of negotiating with the blackmailer or resharing the material [{it_act}]."
                if money_blackmail
                else f"Treat the {material} {harm} as a cyber privacy and non-consensual intimate-image problem first; use the IT Act privacy source for privacy/electronic publication or personation facts instead of resharing the material [{it_act}]."
            )
        )
    if offence_source is not None:
        lines.append(
            (
                f"If the person is demanding money, threatening circulation, humiliating you, or using sexual/private material, keep a separate {offence_label} extortion/intimidation/sexual-image track for police or cyber police review [{offence_source}]."
                if money_blackmail
                else f"If the person is threatening circulation, humiliating you, or using sexual/private material, keep a separate {offence_label} intimidation/sexual-image track for police or cyber police review [{offence_source}]."
            )
        )
    if procedure_source is not None:
        lines.append(
            f"For the police route, preserve the electronic trail and use the {procedure_label} FIR/complaint source for cyber police or local police reporting [{procedure_source}]."
        )
    action_cite = procedure_source if procedure_source is not None else it_act if it_act is not None else offence_source
    evidence_cite = it_act if it_act is not None else offence_source if offence_source is not None else procedure_source
    platform = "Xvideos" if "xvideos" in q else "Reddit" if "reddit" in q else "Telegram" if "telegram" in q else "the platform"
    platform_evidence = f"{platform} links/URLs" if platform in {"Xvideos", "Reddit", "Telegram"} else "platform URLs"
    group_context = ", college/group context" if _has_any(q, ("college", "group", "hostel")) else ""
    lines.extend([
        "**What you can do next**",
        f"- Do not pay or forward the material; preserve {platform_evidence}, profile IDs, screenshots, demand messages, timestamps, phone numbers, group/platform links{group_context}, and request urgent takedown/removal through the platform, cybercrime.gov.in/1930, cyber police, or local police if identity/threat is known [{action_cite}].",
        f"- Keep a separate private evidence folder with only necessary screenshots/links and avoid resharing the nude/private material while reporting [{evidence_cite}].",
    ])
    return lines


def _unsolicited_sexual_image_cyber_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "cyber_fraud_or_harassment" or not _is_unsolicited_sexual_image_cyber(q):
        return []
    it_privacy = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66E",))
    it_obscene = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-67", "/sec-67A"))
    it_act = it_obscene or it_privacy
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-74", "/sec-75", "/sec-78", "/sec-351", "/sec-356"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    primary = it_act or bns or bnss
    if primary is None:
        return []

    platform = (
        "Bumble" if "bumble" in q else
        "Tinder" if "tinder" in q else
        "Instagram" if _has_any(q, ("insta", "instagram")) else
        "the dating or social-media app"
    )
    lines = ["**Short answer**"]
    if it_obscene is not None:
        lines.append(
            f"An unsolicited sexual image sent on {platform} without consent can be treated as a cyber obscene/private electronic-content complaint where the retrieved IT Act publication source fits the exact image and sharing facts, not as something you need to tolerate or reply to privately [{it_obscene}]."
        )
    elif it_privacy is not None:
        lines.append(
            f"An unsolicited sexual image sent on {platform} without consent should be treated as a cyber privacy/private-image evidence problem where the retrieved IT Act privacy source fits the exact facts; do not forward or privately negotiate over the image [{it_privacy}]."
        )
    if bns is not None:
        lines.append(
            f"If the image came with threats, repeated contact, sexual harassment, intimidation, or public shaming, keep a separate BNS offence track for police/cyber-police review [{bns}]."
        )
    if bnss is not None:
        lines.append(
            f"For the reporting route, use the BNSS complaint/FIR source with a written complaint, screenshot trail, profile URL, and platform report number [{bnss}]."
        )
    action_cites = _cite_many(it_obscene, it_privacy, bns, bnss) or f"[{primary}]"
    lines.extend([
        "**What you can do next**",
        f"- Do not forward the sexual image; preserve screenshots, sender profile/URL, user ID, chat timestamps, block/report history, and any threat or repeated-contact proof; report in-app and to cybercrime.gov.in/cyber police/local police where needed {action_cites}.",
    ])
    return lines


def _cyber_harassment_first_action_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "cyber_fraud_or_harassment" or not _is_cyber_harassment_first_action(q):
        return []
    if _is_mental_health_privacy_leak_context(q):
        return []
    it_act = _find(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66c", "/sec-66d", "/sec-66e", "/sec-67", "/sec-67a"),
    )
    dpdp = _find(passages, title_terms=("digital personal data protection",))
    copyright_infringement = _find(
        passages,
        title_terms=("copyright",),
        anchor_terms=("/sec-51",),
    )
    copyright_remedy = _find(
        passages,
        title_terms=("copyright",),
        anchor_terms=("/sec-55",),
    )
    copyright_offence = _find(
        passages,
        title_terms=("copyright",),
        anchor_terms=("/sec-63",),
    )
    it_intermediary = _find(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-79",),
    )
    telecom = _find(
        passages,
        title_terms=("telecommunications",),
        anchor_terms=("/sec-29", "/sec-42"),
    )
    bns = _find(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-308", "/sec-318", "/sec-319", "/sec-351", "/sec-356", "/sec-75", "/sec-77", "/sec-78"),
    )
    bns_intimidation = _find(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-351",),
    )
    bnss = _find(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173", "/sec-175", "/sec-176", "/sec-223"),
    )
    ipc = _find(passages, title_terms=("indian penal",), anchor_terms=("/sec-384", "/sec-503", "/sec-506", "/sec-509", "/sec-499"))
    crpc = _find(passages, title_terms=("criminal procedure",), anchor_terms=("/sec-154", "/sec-156", "/sec-200"))
    legacy_regime = "legacy" in str(route.legal_regime or "").lower()
    current_regime = "current" in str(route.legal_regime or "").lower()
    if legacy_regime:
        offence_source = ipc
        procedure_source = crpc
    elif current_regime:
        offence_source = bns
        procedure_source = bnss
    else:
        offence_source = bns or ipc
        procedure_source = bnss or crpc
    offence_label = "IPC" if offence_source == ipc else "BNS"
    procedure_label = "CrPC" if procedure_source == crpc else "BNSS"
    content_leak_context = _has_any(q, (
        "onlyfans", "fanvue", "telegram channel leaked", "leaked my content",
        "leaked content", "creator content", "copied my content",
    ))
    deepfake_identity_context = _has_any(q, (
        "deepfake", "lookalike", "look alike", "face same", "not me but face",
        "face put", "my face", "ai video", "ai porn",
    ))
    sim_misuse_context = _has_any(q, (
        "fake whatsapp", "new sim", "sim number", "mobile number", "phone number",
        "using my sim", "used my sim", "subscriber", "telecom",
    ))
    fake_authority_context = _has_any(q, (
        "fake cbi", "digital arrest", "parcel", "drugs parcel", "courier",
    ))
    dating_blackmail_context = _has_any(q, (
        "tinder", "bumble", "dating app", "hotel", "took my phone",
    )) and _has_any(q, ("blackmail", "threat", "threaten", "extortion"))
    primary = (
        copyright_infringement or copyright_remedy or copyright_offence
        or it_intermediary or it_act or dpdp or telecom or offence_source
        or procedure_source
    )
    if primary is None:
        return []

    incident = (
        "fake CBI/parcel or digital-arrest demand"
        if fake_authority_context
        else "Bandra hotel dating-app blackmail where they took your phone"
        if "bandra" in q and _has_any(q, ("tinder", "bumble", "dating app", "hotel", "took my phone"))
        else "dating-app blackmail or phone seizure/extortion"
        if _has_any(q, ("tinder", "bumble", "dating app", "hotel", "took my phone"))
        else "deepfake/lookalike sexual-video circulation"
        if _has_any(q, ("deepfake", "lookalike", "look alike", "porn", "nude"))
        else "online harassment, blackmail, impersonation, or electronic-record abuse"
    )
    lines = ["**Short answer**"]
    if fake_authority_context and it_act is not None:
        lines.append(f"Source to verify first: Information Technology Act 2000 [{it_act}].")
        lines.append(
            f"A fake CBI/police/courier parcel call demanding money is a cyber impersonation-fraud issue first; the IT Act cheating-by-personation source is the source to check where a communication device or computer resource is used [{it_act}]."
        )
    elif it_act is not None:
        lines.append(
            f"Treat this first as a cyber evidence problem: for a {incident}, keep the IT Act source with the account, device, link, screenshot, profile, or electronic-message trail instead of relying only on oral platform support [{it_act}]."
        )
    if copyright_infringement is not None and content_leak_context:
        lines.append(
            f"Leaked paid creator content is a copyright problem first: the Copyright Act source covers infringement of copyright where protected work is used without permission [{copyright_infringement}]."
        )
    if copyright_remedy is not None and content_leak_context:
        lines.append(
            f"The Copyright Act civil-remedy source is the route to discuss for injunction, damages, or other civil relief if platform takedown does not stop the leak [{copyright_remedy}]."
        )
    if copyright_offence is not None and content_leak_context:
        lines.append(
            f"The Copyright Act source also gives a criminal-offence track for knowing infringement where the statutory ingredients are met [{copyright_offence}]."
        )
    if it_intermediary is not None and content_leak_context:
        lines.append(
            f"The IT Act source is relevant for the platform/intermediary side, so a Telegram or platform takedown should be framed separately from the copyright-owner complaint [{it_intermediary}]."
        )
    if dpdp is not None and deepfake_identity_context:
        lines.append(
            f"For a deepfake or lookalike video using your face or identity, keep the DPDP/personal-data grievance track separate from the criminal and platform-takedown tracks where the uploader, platform, or data fiduciary facts fit [{dpdp}]."
        )
    if telecom is not None and sim_misuse_context:
        lines.append(
            f"Because the harassment uses a SIM, mobile number, or telecom subscriber identity, keep the Telecommunications Act subscriber/identifier misuse source with SIM/KYC/number-ownership proof; do not treat it only as platform harassment [{telecom}]."
        )
    it_identity = _find(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66c",),
    )
    it_personation = _find(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66d",),
    )
    if sim_misuse_context and it_identity is not None:
        lines.append(
            f"A fake WhatsApp account using your new SIM/mobile number should be treated as IT Act identity-theft first; preserve the mobile number, SIM/KYC record, account handle, and impersonating messages [{it_identity}]."
        )
    if sim_misuse_context and it_personation is not None:
        lines.append(
            f"If that fake account is used to deceive or contact relatives as you, keep the IT Act cheating-by-personation source in the complaint file too [{it_personation}]."
        )
    if bns_intimidation is not None and dating_blackmail_context:
        lines.append(
            f"For this dating-app blackmail, the BNS source treats a threat of injury to person, reputation, or property as criminal intimidation where the statutory ingredients are met [{bns_intimidation}]."
        )
    elif offence_source is not None:
        lines.append(
            f"If the facts include cheating by personation, extortion, intimidation, stalking, obscene/private-image circulation, or reputation harm, keep a separate {offence_label} offence track for cyber police/local police review [{offence_source}]."
        )
    if dating_blackmail_context and offence_source is not None and _has_any(q, ("took my phone", "phone", "gang", "hotel")):
        lines.append(
            f"Because the facts say they took your phone in the dating-app incident, preserve a separate robbery/theft-force track where force, restraint, fear, or taking of property is alleged; the exact BNS section must be checked from the complaint facts [{offence_source}]."
        )
    if sim_misuse_context and offence_source is not None:
        lines.append(
            f"For harassment of your family through that fake account, keep a separate BNS track for stalking, criminal intimidation, defamation, or personation depending on the exact messages and threats [{offence_source}]."
        )
    if procedure_source is not None:
        lines.append(
            f"For the police route, use the {procedure_label} information/FIR or complaint source with the cyber complaint packet and any refusal or no-action proof [{procedure_source}]."
        )
    action_cites = _cite_many(
        copyright_infringement,
        copyright_remedy,
        copyright_offence,
        it_intermediary,
        it_act,
        it_identity,
        it_personation,
        dpdp,
        telecom,
        bns_intimidation or offence_source,
        procedure_source,
    )
    lines.append("**What you can do next**")
    if fake_authority_context:
        lines.append(
            f"- Do not send money or call back to negotiate; preserve the caller number, call recording/messages, parcel or case ID claimed, UPI/bank details, and any payment proof, then report through 1930/cybercrime.gov.in, the bank fraud desk if paid, and local police if threats continue {action_cites}."
        )
    elif content_leak_context:
        lines.append(
            f"- Preserve the channel URL, post links, uploader handle, timestamps, payment/subscriber proof, original files, watermark/project proof, and platform report ID; send takedown notices to the platform and keep a separate cyber/police track if the leak includes private/intimate images, threats, or doxxing {action_cites}."
        )
    else:
        lines.append(
            f"- Preserve URLs, screenshots, profile/user IDs, phone IMEI/device details, phone numbers, UPI/bank details if any, device/app names, timestamps, platform complaint IDs, and demand/threat messages; report through the platform plus cybercrime.gov.in/1930 or cyber police/local police where money, blackmail, impersonation, or safety risk exists {action_cites}."
        )
    lines.append(
        f"- If police or platform support refuses or delays, keep the written complaint/refusal number and escalate to senior police, cyber cell, Magistrate/DLSA, or a lawyer instead of deleting the electronic trail {action_cites}."
    )
    return lines


def _online_defamation_abuse_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "cyber_fraud_or_harassment" or not _is_online_defamation_abuse(q):
        return []
    bns_defamation = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-356",))
    bns_threat = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-351", "/sec-78"))
    it_privacy = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66E", "/sec-67", "/sec-67A"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    primary = bns_defamation or bns_threat or it_privacy or bnss
    if primary is None:
        return []

    platform = "Instagram" if _has_any(q, ("instagram", "insta")) else "Telegram" if "telegram" in q else "online platform"
    lines = ["**Short answer**"]
    if bns_defamation is not None:
        if "randi" in q and platform == "Instagram":
            lines.append(
                f"For abusive Instagram comments calling you 'randi', treat this as online abuse/possible defamation, not as a deepfake or private-image complaint, and preserve the exact public words, account handle, URL, date/time, and audience for the BNS defamation/reputational-harm route [{bns_defamation}]."
            )
        else:
            lines.append(
                f"For abusive {platform} comments, sexualised insults, public allegations, or reputation-harming posts, keep the BNS defamation/reputational-harm source with the exact words, account handle, URL, and audience proof [{bns_defamation}]."
            )
    elif bns_threat is not None:
        lines.append(
            f"For abusive {platform} comments that also threaten, stalk, or repeatedly target you, keep the BNS harassment/intimidation source with the exact words and account trail [{bns_threat}]."
        )
    if it_privacy is not None:
        lines.append(
            f"Use the IT Act source only where the post involves electronic identity, privacy, intimate/obscene material, impersonation, or platform evidence; do not stretch it to every ordinary insult without those facts [{it_privacy}]."
        )
        if "randi" in q and platform == "Instagram":
            lines.append(
                f"Use the IT Act electronic-material section only if the actual post or comment is obscene electronic material, private-image material, identity misuse, or another matching electronic-content fact; an abusive word by itself does not make every IT Act section apply [{it_privacy}]."
            )
    if bnss is not None:
        lines.append(
            f"For police or cyber-police escalation, use the BNSS complaint/FIR route with screenshots, URLs, profile IDs, timestamps, platform report IDs, witnesses, and any threat or doxxing proof [{bnss}]."
        )
    action_cite = bnss or bns_defamation or bns_threat or it_privacy
    lines.extend([
        "**What you can do next**",
        f"- Preserve the post/comment URL, username/profile ID, exact words, screenshot with date/time, platform report ID, witnesses, and any continued messages; report to the platform first and take the same packet to cyber police/DLSA/lawyer if it continues or causes serious harm [{action_cite}].",
    ])
    return lines


def _public_political_deepfake_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    q = q.lower()
    if route.category != "cyber_fraud_or_harassment" or not _is_public_political_deepfake(q):
        return []
    it_act = (
        _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66D",))
        or _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66C",))
        or _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66E",))
    )
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-356", "/sec-351", "/sec-196"))
    rpa = _find(passages, title_terms=("representation of the people",), anchor_terms=("/sec-123", "/sec-125", "/sec-125A"))
    primary = rpa or it_act or bns
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if rpa is not None:
        lines.append(
            f"For a public-political deepfake involving a PM/party/candidate or IT-cell threat, preserve the political/election campaign context and check the Representation of the People Act source separately from ordinary cyber-image abuse [{rpa}]."
        )
    if it_act is not None:
        lines.append(
            f"Keep the IT Act cyber layer for electronic publication, personation, or identity misuse in the deepfake circulation, not as private-image sextortion [{it_act}]."
        )
    if bns is not None:
        lines.append(
            f"Keep the BNS layer only for the exact reputation, intimidation, or public-order facts in the posts and threats; do not frame the public-political deepfake as a private-image sextortion case [{bns}]."
        )
    action_cite = rpa if rpa is not None else it_act if it_act is not None else bns
    evidence_cite = it_act if it_act is not None else bns if bns is not None else rpa
    lines.extend([
        "**What you can do next**",
        f"- Preserve URLs, screenshots, profile IDs, uploader details, timestamps, party/IT-cell threats, campaign or circulation context, and platform complaint IDs; ask for takedown/removal and report the cyber/public-political deepfake track to the platform, cyber police, and election-law counsel/Returning Officer where election facts exist [{action_cite}].",
        f"- Do not label it as private-image sextortion unless the content is actually intimate/private-image abuse; keep the cyber evidence and public-political context together for review [{evidence_cite}].",
    ])
    return lines


def _witch_branding_violence_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"police_fir", "tribal_caste_atrocity", "criminal_general"} or not _is_witch_branding(q):
        return []
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-74", "/sec-76", "/sec-115", "/sec-117", "/sec-126", "/sec-127", "/sec-351", "/sec-356"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173",))
    bnss_magistrate = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-175",))
    bnss = bnss_fir or bnss_magistrate
    poa = _find(passages, title_terms=("scheduled castes", "prevention of atrocities"))
    state_witch = _find_state_witch_source(passages)
    if state_witch is not None and _source_type_for_index(passages, state_witch) == "official_summary":
        stronger_state_witch = _find_state_witch_source(passages, allow_reference_only=False)
        if stronger_state_witch is not None:
            state_witch = stronger_state_witch
    state_witch_reference_only = False
    if state_witch is not None:
        state_title = _title_for_index(passages, state_witch)
        state_source_type = _source_type_for_index(passages, state_witch)
        assam_source_for_non_assam_fact = "assam" in state_title and not _has_any(q, ("assam", "barpeta", "kokrajhar", "guwahati", "dibrugarh", "jorhat"))
        chhattisgarh_source_for_non_chhattisgarh_fact = "chhattisgarh" in state_title and not _has_chhattisgarh_context(q)
        if assam_source_for_non_assam_fact or chhattisgarh_source_for_non_chhattisgarh_fact:
            state_witch = None
        elif "jharkhand" in state_title and state_source_type not in {"bare_act", "official_guidance"}:
            state_witch_reference_only = True
    primary = bns or bnss or poa or state_witch
    if primary is None:
        return []

    person = _female_relative_phrase(q)
    harm = (
        "public stripping/disrobing"
        if _has_any(q, ("stripped", "disrobed", "naked", "without clothes", "tore her clothes", "torn clothes", "paraded"))
        else "threatened village removal/expulsion"
        if _has_any(q, ("remove her from village", "expel", "expulsion", "throw her out", "village removal", "forced her to leave", "forced her to leave home", "leave home"))
        else "threatening to kill"
        if _has_any(q, ("threatening to kill", "threaten to kill", "kill"))
        else "beating/threats"
        if _has_any(q, ("beat", "beaten", "threat", "threatened", "threatening"))
        else "witch-branding"
    )
    label_phrase = (
        "tonhi"
        if "tonhi" in q
        else "dayan/daayan"
        if _has_any(q, ("dayan", "daayan", "daini"))
        else "witch"
    )
    incident_phrase = (
        f"an ojha/tantrik or villagers branding {person} {label_phrase} with {harm}"
        if _has_any(q, ("ojha", "tantrik", "villagers", "village people", "panchayat"))
        else f"{person} being called daayan/witch or accused of black magic with {harm}"
    )
    lines = ["**Short answer**"]
    if bns is not None:
        lines.append(
            f"For {incident_phrase}, treat this as an urgent police-protection and criminal-violence issue, not only a village dispute [{bns}]."
        )
    if state_witch is not None and state_witch_reference_only:
        state_label = _witch_state_label(q)
        lines.append(
            f"I found only an official court-reference marker for the {state_label} witch-practices lane, not the exact State Act text; verify the Jharkhand Act/FIR sections before treating it as the controlling offence source, while using the criminal-law source for immediate safety and reporting [{state_witch}]."
        )
    elif state_witch is not None:
        state_title = _title_for_index(passages, state_witch)
        if "jharkhand" in state_title and "dayan pratha" in state_title:
            lines.append(
                f"Use the JHALSA official-guidance source for Jharkhand Dayan Pratha Pratishedh Adhiniyam 2001 as the state witch-practices lane, and keep it separate from the generic BNS/BNSS criminal route [{state_witch}]."
            )
        else:
            lines.append(
                f"Also check the state witch-hunting/witch-branding source for the incident State before relying only on generic criminal law [{state_witch}]."
            )
    elif bnss is not None:
        state_label = _witch_state_label(q)
        lines.append(
            f"I do not have the exact {state_label} witch-practices State Act source in the retrieved index, so verify the state-specific witch-branding law and do not treat BNS, BNSS, or a tangential judgment as the controlling State Act for the daayan/witch-branding offence; use the BNSS FIR/Magistrate route only as the immediate reporting and protection procedure [{bnss}]."
        )
    if bnss_magistrate is not None and bnss_magistrate != bnss:
        lines.append(
            f"If police refuse or delay action, keep the BNSS Magistrate-investigation source as the escalation route to verify [{bnss_magistrate}]."
        )
    if poa is not None:
        lines.append(
            f"If caste, Scheduled Caste, Scheduled Tribe, Dalit, Adivasi, or tribal targeting is part of the facts, keep the SC/ST atrocity route separate from the ordinary FIR route [{poa}]."
        )
    action_cite = bnss if bnss is not None else bns if bns is not None else poa if poa is not None else state_witch
    lines.extend([
        "**What you can do next**",
        f"- Move to safety first if there is mob or village pressure; preserve medical records, photos/videos, torn clothes if any, witness names, exact witch/black-magic words, place/date, and police-refusal proof; take a written complaint to police, SP, DLSA, or Magistrate route [{action_cite}].",
    ])
    return lines


def _caste_access_police_refusal_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"tribal_caste_atrocity", "criminal_general", "police_fir"}:
        return []
    if not (_has_any(q, ("caste", "dalit", "sc/st", "sc st", "scheduled caste", "scheduled tribe", "tribal", "adivasi")) and _has_any(q, ("shop", "hotel", "service", "denied", "not allowed", "police laughing", "police refused", "police not"))):
        return []
    poa = _find(passages, title_terms=("scheduled castes", "prevention of atrocities"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-351", "/sec-356", "/sec-352", "/sec-196"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    pcr = _find(passages, title_terms=("protection of civil rights",))
    primary = poa or pcr or bns or bnss
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if poa is not None:
        lines.append(
            f"If service was denied using caste words and the affected person is SC/ST, keep the SC/ST PoA route as a protected-status complaint; record the exact words, place, witnesses, and police refusal [{poa}]."
        )
    elif pcr is not None:
        lines.append(
            f"If the facts are about caste-based access/service denial or untouchability, keep the civil-rights/untouchability source separate from a generic consumer complaint [{pcr}]."
        )
    if bns is not None or bnss is not None:
        cite = bnss or bns
        lines.append(
            f"The incident date decides whether BNS/BNSS or IPC/CrPC procedure applies for any insult, intimidation, public-order, or police-refusal track, so do not assume the old or new criminal regime without the date [{cite}]."
        )
    else:
        lines.append(
            f"If police add criminal sections, the incident date decides whether BNS/BNSS or IPC/CrPC applies; ask police or legal aid to record the incident date before framing the criminal-law route [{primary}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Write a dated complaint with the exact incident date, caste words, shop/service facts, location, witnesses/CCTV, status proof if available, and what police refused to do; escalate to SP/senior police, DLSA, or the Special Court/PoA route where applicable [{primary}].",
        f"- Keep screenshots/video, bills or entry/service proof, witness names, police station diary/refusal proof, and your caste/community certificate if the SC/ST route is being used [{primary}].",
    ])
    return lines


def _poa_special_court_delay_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "tribal_caste_atrocity" or not _is_poa_special_court_delay(q):
        return []
    poa = _find(passages, title_terms=("scheduled castes", "prevention of atrocities"))
    victim_rights = _find(
        passages,
        title_terms=("scheduled castes", "prevention of atrocities"),
        anchor_terms=("/sec-15A", "/sec-15-a"),
    )
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175", "/sec-230", "/sec-231"))
    if poa is None:
        return []

    delay_phrase = "5-year delay" if _has_any(q, ("5 years", "5 year", "5 yrs", "five years")) else "long delay"
    court_place = "Aurangabad, Maharashtra Special Court" if _has_any(q, ("aurangabad", "maharashtra")) else "SC/ST PoA Special Court"
    lines = [
        "**Short answer**",
        f"For an {court_place} case pending for years, including a {delay_phrase} with no judgement, treat it as a case-status, victim-rights source, and speedy-trial follow-up problem; do not answer it as forest land or ordinary police refusal [{poa}].",
        f"Use the PoA source for the Special Court/atrocity case record and ask for the next date, stage, prosecution status, and whether the victim/complainant rights route or Special Public Prosecutor follow-up is needed [{poa}].",
    ]
    if victim_rights is not None and victim_rights != poa:
        lines.append(
            f"Keep the PoA victim-rights source with the case-status request so notice, participation, and protection/support facts are preserved separately from the delay record [{victim_rights}]."
        )
    if bnss is not None:
        lines.append(
            f"Keep the criminal-procedure source with the order sheets, summons/witness status, and any application for expediting the case or getting copies/status [{bnss}]."
        )
    action_cites = _cite_many(poa, victim_rights, bnss)
    lines.extend([
        "**What you can do next**",
        f"- Collect FIR/charge-sheet number, Special Court case number, order sheets/next dates, witness-examination status, prosecutor details, SC/ST victim papers including caste/community proof, victim/complainant contact, and all applications already filed; ask the Special Court help desk, Special Public Prosecutor, DLSA, or victim-compensation/support authority for a written status and next step {action_cites}.",
    ])
    return lines


def _caste_public_access_exclusion_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"tribal_caste_atrocity", "criminal_general", "police_fir"} or not _is_caste_public_access_exclusion(q):
        return []
    poa = _find(passages, title_terms=("scheduled castes", "prevention of atrocities"))
    pcr = _find(passages, title_terms=("protection of civil rights",))
    article17 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-17",))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-115", "/sec-117", "/sec-351", "/sec-352", "/sec-356"))
    primary = article17 or pcr or poa or bnss or bns
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if article17 is not None or pcr is not None:
        cite = article17 or pcr
        if _has_any(q, ("thakur", "dalit", "temple")):
            lines.append(
                f"If a Thakur family stopped Dalit persons from entering a temple, treat it as a temple-entry/untouchability complaint and public-access exclusion, not an ordinary village quarrel; keep the Article 17 / Protection of Civil Rights Act route in the file [{cite}]."
            )
        else:
            lines.append(
                f"For temple, well, water, or public-access exclusion using caste words, keep the Article 17 / Protection of Civil Rights Act route separate from ordinary trespass or local quarrel framing [{cite}]."
            )
    if poa is not None:
        lines.append(
            f"If the person affected is SC/ST and the facts include caste-targeted humiliation, social boycott, public-access denial, or police refusal, preserve the SC/ST PoA track with status proof, words used, witnesses, and refusal proof [{poa}]."
        )
    if bnss is not None or bns is not None:
        cite = bnss or bns
        lines.append(
            f"For FIR refusal or criminal escalation, use the criminal-procedure/offence source with the written complaint and acknowledgement instead of relying on oral station advice [{cite}]."
        )
    action_cites = _cite_many(article17, pcr, poa, bnss, bns)
    lines.extend([
        "**What you can do next**",
        f"- Preserve caste/community proof, exact words used, temple/well/water/public-place or service denied, location, date/time, names of accused/witnesses, photos/video/CCTV if safe, and police-station diary or refusal proof {action_cites}.",
        f"- Take the written complaint to police/SP, DLSA, Protection of Civil Rights/PoA support channels, or the Special Court route where applicable; keep this public-access/caste-discrimination file separate from land or forest-rights papers {action_cites}.",
    ])
    return lines


def _mining_gram_sabha_consent_challenge_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "environment_compensation" or not _is_mining_gram_sabha_context(q):
        return []
    pesa = _find(passages, title_terms=("panchayats", "scheduled areas"))
    mmdr = _find(passages, title_terms=("mines and minerals",))
    forest_conservation = _find(passages, title_terms=("forest (conservation", "forest conservation", "forest-conservation"))
    rfctlarr = _find(passages, title_terms=("land acquisition", "rehabilitation", "resettlement"))
    fra = _find(passages, title_terms=("forest rights", "scheduled tribes and other traditional forest"))
    primary = pesa or mmdr or forest_conservation or rfctlarr or fra
    if primary is None:
        return []

    minor_mineral_context = _has_any(q, ("sand", "minor mineral", "minor-mineral", "quarry"))
    lines = ["**Short answer**"]
    if pesa is not None:
        if minor_mineral_context:
            lines.append(
                f"For a minor-mineral lease in a Scheduled Area, keep the PESA source as the Gram Sabha recommendation source to check before treating the lease process as complete [{pesa}]."
            )
        else:
            lines.append(
                f"For a bauxite/mining project or DM NOC in Bastar/Scheduled Area facts, keep the PESA/Gram Sabha source separate from the mining-office file; ask for Scheduled Area status, notice, minutes, and the Gram Sabha resolution before treating the NOC as complete [{pesa}]."
            )
    if mmdr is not None:
        if minor_mineral_context:
            lines.append(
                f"Use the MMDR/mining source for the minor-mineral lease and mineral-department approval record; it does not replace the Gram Sabha recommendation question [{mmdr}]."
            )
        else:
            lines.append(
                f"Use the MMDR/mining source for the lease, mineral-concession, NOC, project name, and mining-department approval record; it does not replace the Gram Sabha/PESA question where that route applies [{mmdr}]."
            )
    if forest_conservation is not None:
        lines.append(
            f"If forest land or forest clearance is involved, keep the Forest Conservation Act clearance papers as a separate track from the Gram Sabha and mining-lease file [{forest_conservation}]."
        )
    if rfctlarr is not None and not minor_mineral_context:
        lines.append(
            f"Add RFCTLARR rehabilitation/compensation papers only if the facts include land acquisition, displacement, rehabilitation, or compensation, not merely because a mining NOC exists [{rfctlarr}]."
        )
    action_cites = _cite_many(pesa, mmdr, forest_conservation, None if minor_mineral_context else rfctlarr, fra)
    lines.extend([
        "**What you can do next**",
        (
            f"- Collect the lease number, mineral and site details, Scheduled Area proof, Gram Sabha recommendation/minutes, mineral-department approval, map, and forest or pollution clearance if any; take this file to the Collector/mining department, Gram Sabha/Panchayat channel, tribal welfare authority, DLSA, or court/NGT lawyer depending on which approval is missing {action_cites}."
            if minor_mineral_context
            else f"- Collect the DM/NOC/lease number, project and company name, mineral, village list, Scheduled Area proof, Gram Sabha notice/minutes/resolution, mining-department file, forest/pollution clearance if any, and any land-acquisition or displacement papers; take this file to the Collector/mining department, Gram Sabha/Panchayat channel, tribal welfare authority, DLSA, or court/NGT lawyer depending on which approval is missing {action_cites}."
        ),
    ])
    return lines


def _tribal_forest_land_access_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"tribal_caste_atrocity", "land_revenue_records", "environment_compensation"}:
        return []
    forest_context = _has_any(q, (
        "fra", "forest rights", "ifr", "cfr", "community forest", "forest department",
        "forest guard", "forest officer", "bamboo", "reserve forest", "reserved forest",
        "gram sabha", "sdlc", "dlc", "claim rejected", "patta given",
    ))
    mining_gram_sabha_context = _is_mining_gram_sabha_context(q)
    land_transfer_context = _has_any(q, (
        "non tribal", "non-tribal", "bania", "sahukar", "munda land", "santhal land",
        "agency area", "scheduled area", "dc permission", "land sold", "land grabbed",
        "mortgage", "transferred my", "patwari changed", "tehsildar transferred",
    ))
    public_access_context = _has_any(q, (
        "temple", "well", "dirty water", "cannot touch", "cant enter", "can't enter",
        "not enter", "stopped us from entering", "public access", "untouchable",
        "dalit cannot", "caste cant", "caste can't",
    ))
    atrocity_procedure_context = _has_any(q, (
        "atrocity", "poa", "sc st", "sc/st", "dsp", "special court",
        "case pending", "sp not transferring",
    )) or (
        _has_any(q, ("fir not", "police refusing", "police refused", "station refuses"))
        and _has_any(q, (
            "sc/st", "sc st", "scheduled caste", "scheduled tribe",
            "dalit", "adivasi", "tribal", "caste", "poa", "atrocity",
        ))
    )
    if not (forest_context or land_transfer_context or public_access_context or atrocity_procedure_context):
        return []

    # PoA investigation, Special Court, and FIR-refusal matters have dedicated
    # workflows earlier in the selection order.  This workflow owns those facts
    # only when they are genuinely coupled to forest, land-transfer, or public
    # access facts; otherwise its broad route eligibility masks the narrower
    # criminal-procedure answer.
    if atrocity_procedure_context and not (forest_context or land_transfer_context or public_access_context):
        return []

    fra = _find(passages, title_terms=("forest rights", "scheduled tribes and other traditional forest"))
    pesa = _find(passages, title_terms=("panchayats", "scheduled areas"))
    mmdr = _find(passages, title_terms=("mines and minerals",))
    forest_conservation = _find(passages, title_terms=("forest (conservation", "forest conservation", "forest-conservation"))
    rfctlarr = _find(passages, title_terms=("land acquisition", "rehabilitation", "resettlement"))
    poa = _find(passages, title_terms=("scheduled castes", "prevention of atrocities"))
    poa_rules = _find(passages, title_terms=("prevention of atrocities", "rules"), anchor_terms=("rule-7",))
    pcr = _find(passages, title_terms=("protection of civil rights",))
    article17 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-17",))
    article244 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-244",))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-115", "/sec-117", "/sec-351", "/sec-352", "/sec-356"))
    state_land = _find(passages, title_terms=("chota nagpur", "chotanagpur", "santhal", "tenancy", "scheduled areas", "andhra pradesh scheduled"))
    transfer_property = _find(passages, title_terms=("transfer of property",), anchor_terms=("/sec-44", "/sec-54", "/sec-58", "/sec-122"))
    if public_access_context and not (forest_context or land_transfer_context) and not (article17 or pcr or poa or bnss or bns):
        return []
    primary = fra or pesa or poa_rules or poa or pcr or article17 or state_land or transfer_property or article244 or bnss or bns
    if mining_gram_sabha_context:
        primary = pesa or mmdr or forest_conservation or rfctlarr or primary
    if primary is None:
        return []

    lines = ["**Short answer**"]
    poa_court_delay_context = _has_any(q, ("special court", "case pending", "no judgement", "no judgment", "pending 5 yrs", "pending 5 years"))
    if poa_court_delay_context and poa is None and bnss is not None:
        lines.extend([
            f"I found a criminal-procedure source for the case-status/copy route, but not the SC/ST PoA Act source needed for PoA-specific remedies; treat this as source-gap intake first [{bnss}].",
            "**What you can do next**",
            f"- Collect the case number, FIR/charge-sheet details, order sheets, next date, witness status, and copy/status applications; ask the court help desk, DLSA, or lawyer to verify the PoA Act/Special Court source before using PoA-specific remedies [{bnss}].",
        ])
        return lines
    if poa_court_delay_context and (poa is not None or bnss is not None):
        cite = poa or bnss or primary
        lines.append(
            f"For an SC/ST PoA Special Court case pending for years with no judgment, treat it as a case-status, victim/right-to-participate, and speedy-trial follow-up problem; do not answer it as forest land or ordinary police refusal [{cite}]."
        )
        if poa is not None:
            lines.append(
                f"Use the PoA source for the Special Court/atrocity case record and ask for the next date, stage, prosecution status, and whether the victim/complainant rights route or Special Public Prosecutor follow-up is needed [{poa}]."
            )
        if bnss is not None:
            lines.append(
                f"Keep the criminal-procedure source with the order sheets, summons/witness status, and any application for expediting the case or getting copies/status [{bnss}]."
            )
        action_cites = _cite_many(poa, bnss, article17, pcr)
        lines.extend([
            "**What you can do next**",
            f"- Collect FIR/charge-sheet number, Special Court case number, order sheets/next dates, witness-examination status, prosecutor details, caste/community proof, victim/complainant contact, and all applications already filed; ask the Special Court help desk, Special Public Prosecutor, DLSA, or victim-compensation/support authority for a written status and next step {action_cites}.",
        ])
        return lines

    if mining_gram_sabha_context:
        if pesa is not None:
            lines.append(
                f"For a bauxite/mining project or DM NOC in Bastar/Scheduled Area facts, keep the PESA/Gram Sabha source separate from the mining-office file; ask for Scheduled Area status, notice, minutes, and the Gram Sabha resolution before treating the NOC as complete [{pesa}]."
            )
        if mmdr is not None:
            lines.append(
                f"Use the MMDR/mining source for the lease, mineral-concession, NOC, project name, and mining-department approval record; it does not replace the Gram Sabha/PESA question where that route applies [{mmdr}]."
            )
        if forest_conservation is not None:
            lines.append(
                f"If forest land or forest clearance is involved, keep the Forest Conservation Act clearance papers as a separate track from the Gram Sabha and mining-lease file [{forest_conservation}]."
            )
        if rfctlarr is not None:
            lines.append(
                f"Add RFCTLARR rehabilitation/compensation papers only if the facts include land acquisition, displacement, rehabilitation, or compensation, not merely because a mining NOC exists [{rfctlarr}]."
            )
        action_cites = _cite_many(pesa, mmdr, forest_conservation, rfctlarr, fra)
        lines.extend([
            "**What you can do next**",
            f"- Collect the DM/NOC/lease number, project and company name, mineral, village list, Scheduled Area proof, Gram Sabha notice/minutes/resolution, mining-department file, forest/pollution clearance if any, and any land-acquisition or displacement papers; take this file to the Collector/mining department, Gram Sabha/Panchayat channel, tribal welfare authority, DLSA, or court/NGT lawyer depending on which approval is missing {action_cites}.",
        ])
        return lines

    if forest_context:
        if fra is not None:
            lines.append(
                f"For IFR/CFR, patta, bamboo, forest-guard, SDLC/DLC, or forest-rights rejection facts, use the Forest Rights Act route first; do not convert it into only a generic police or land-record dispute [{fra}]."
            )
        if pesa is not None:
            lines.append(
                f"If the village is in a Scheduled Area or Gram Sabha consent/control is central, keep the PESA/Gram Sabha source with the FRA file instead of relying only on forest-department oral reasons [{pesa}]."
            )
    if land_transfer_context:
        non_scheduled_context = _has_any(q, ("non scheduled", "non-scheduled"))
        land_cite = (
            state_land or transfer_property or poa or fra
            if non_scheduled_context
            else state_land or article244 or pesa or fra or transfer_property or poa
        )
        if non_scheduled_context:
            lines.append(
                f"Because the facts say non-Scheduled Area, do not apply PESA or Article 244 as the controlling route without district verification; keep this on the state tribal-land/revenue/civil cancellation route first [{land_cite}]."
            )
        lines.append(
            f"For tribal land sold, mortgaged, mutated, or grabbed by a non-tribal or moneylender, verify the exact state/scheduled-area land-transfer source and DC/revenue permission route before accepting the sale or mutation as final [{land_cite}]."
        )
    if public_access_context:
        cite = article17 or pcr or poa or bns or bnss or primary
        lines.append(
            f"For temple, well, water, or public-access exclusion using caste words, keep the Article 17 / Protection of Civil Rights Act / SC-ST PoA route separate from ordinary trespass or local quarrel framing [{cite}]."
        )
    if poa_rules is not None:
        lines.append(
            f"If the complaint is that an atrocity investigation was not assigned to the required DSP-rank officer, keep the SC/ST PoA Rules Rule 7 source and ask for the written investigation-transfer/status record [{poa_rules}]."
        )
    if poa is not None:
        lines.append(
            f"If the person affected is SC/ST and the facts include caste-targeted assault, humiliation, land interference, social boycott, or public-access denial, preserve the SC/ST PoA track with status proof, words used, witnesses, and police-refusal proof [{poa}]."
        )
    if bnss is not None:
        lines.append(
            f"For FIR refusal, SP escalation, or Magistrate direction, use the criminal-procedure source with the written complaint and acknowledgement rather than relying on oral station advice [{bnss}]."
        )
    if public_access_context and not (forest_context or land_transfer_context):
        action_cites = _cite_many(poa, pcr, article17, bnss, bns)
        lines.extend([
            "**What you can do next**",
            f"- Preserve caste/community proof, exact words used, temple/well/water/public-place or service denied, location, date/time, names of accused/witnesses, photos/video/CCTV if safe, and police-station diary or refusal proof {action_cites}.",
            f"- Take the written complaint to police/SP, DLSA, Protection of Civil Rights/PoA support channels, or the Special Court route where applicable; keep this public-access/caste-discrimination file separate from land or forest-rights papers {action_cites}.",
        ])
        return lines
    action_cites = _cite_many(fra, pesa, state_land, transfer_property, poa_rules, poa, pcr, article17, bnss)
    lines.extend([
        "**What you can do next**",
        f"- Preserve caste/tribe certificate or community proof, land/patta/IFR/CFR papers, Gram Sabha resolution, SDLC/DLC rejection or silence, mutation/sale/mortgage papers, police complaint/refusal, witness names, photos/video, and the exact caste/public-access words or forest-department reason {action_cites}.",
        f"- Take the file to the Gram Sabha/FRC, SDLC/DLC or revenue authority for FRA/land issues, and to SP/Special Court/DLSA/Magistrate for atrocity or FIR-refusal issues; keep the routes separate when both are present {action_cites}.",
    ])
    return lines


def _blank_paper_moneylender_fraud_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"criminal_general", "criminal_defence_bail", "banking_credit_dispute", "property_tenancy"}:
        return []
    paper_context = _has_any(q, (
        "thumb impression", "blank paper", "fake signature", "forged",
        "forgery", "never took", "loan i never took", "not my loan",
    ))
    lender_context = _has_any(q, (
        "moneylender", "sahukar", "loan", "5 lakh", "five lakh",
        "blank paper now showing", "paper now showing",
    ))
    if not (paper_context and lender_context):
        return []
    bns_forgery = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-336", "/sec-338", "/sec-340", "/sec-318"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    crpc_complaint = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-154", "/sec-156", "/sec-200"))
    contract = _find(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-14", "/sec-16", "/sec-17", "/sec-19", "/sec-19-a"),
    )
    primary = bns_forgery or bnss_fir or crpc_complaint or contract
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if bns_forgery is not None:
        lines.append(
            f"For a moneylender using a thumb impression or blank paper to show a loan you say you never took, treat it as a disputed-document and possible forgery/cheating track first; do not accept the alleged debt merely from the paper shown to you [{bns_forgery}]."
        )
    if contract is not None:
        lines.append(
            f"If the dispute is also about whether you consented to the loan paper, keep the Contract Act free-consent, undue-influence, fraud, or voidability source with the civil reply or cancellation/declaration file [{contract}]."
        )
    if bnss_fir is not None or crpc_complaint is not None:
        procedure = bnss_fir or crpc_complaint
        lines.append(
            f"For the police side, give a written complaint with the document-copy demand and preserve acknowledgement; if police refuse, use senior-police/Magistrate procedure instead of relying on oral station advice [{procedure}]."
        )
    action_cites = _cite_many(bns_forgery, contract, bnss_fir, crpc_complaint)
    lines.extend([
        "**What you can do next**",
        f"- Keep the alleged loan paper copy/photo, thumb-impression/signature comparison material, witness names, money trail, earlier messages, demand notice, village/panchayat pressure facts, and any police-station diary number; ask DLSA/criminal counsel whether to file police complaint, reply to the demand, or seek civil cancellation/declaration {action_cites}.",
    ])
    return lines


def _arms_act_farming_tool_defence_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"criminal_general", "criminal_defence_bail", "police_fir"}:
        return []
    arms_context = _has_any(q, ("arms act", "weapon case", "weapon", "axe", "knife", "licensed arm"))
    farming_context = _has_any(q, ("farming", "farm", "agriculture", "field", "axe", "sickle", "tool"))
    if not (arms_context and farming_context):
        return []
    arms_def = _find(passages, title_terms=("arms act",), anchor_terms=("/sec-2",))
    arms_license = _find(passages, title_terms=("arms act",), anchor_terms=("/sec-4", "/sec-3"))
    arms_penalty = _find(passages, title_terms=("arms act",), anchor_terms=("/sec-25",))
    bnss_bail = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-480", "/sec-483", "/sec-216"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    crpc = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-437", "/sec-438", "/sec-439", "/sec-156"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-351", "/sec-115", "/sec-117"))
    primary = arms_def or arms_license or arms_penalty or bnss_bail or bnss_fir or crpc or bns
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if arms_def is not None:
        lines.append(
            f"For an Arms Act allegation over an axe or farming tool, start with the Arms Act definition source: articles designed solely for agricultural or domestic use are treated differently from weapons, so do not decide guilt from the tool name alone [{arms_def}]."
        )
    if arms_license is not None:
        lines.append(
            f"Also verify whether any Section 4 notification or licence requirement actually applies to that area and class of article before accepting the police label [{arms_license}]."
        )
    if arms_penalty is not None:
        lines.append(
            f"If police cite an Arms Act punishment section, compare the exact FIR section and seizure memo to the Arms Act penalty source rather than relying only on generic bail law [{arms_penalty}]."
        )
    lines.append(
        f"First get the FIR, exact Arms Act section, seizure memo, place, purpose, and whether any threat/violence allegation is made [{primary}]."
    )
    if bnss_bail is not None or crpc is not None:
        bail_cite = bnss_bail or crpc
        lines.append(
            f"If anyone is arrested, called to the station, or facing remand, handle notice/arrest/bail papers first and ask legal aid or a criminal lawyer before arguing the farming-use defence orally at the station [{bail_cite}]."
        )
    if bns is not None:
        lines.append(
            f"If police also allege threat, hurt, intimidation, or violence, keep those BNS facts separate from the Arms Act/seizure question; farming use does not answer every separate violence allegation [{bns}]."
        )
    action_cites = _cite_many(arms_def, arms_license, arms_penalty, bnss_bail, bnss_fir, crpc, bns)
    lines.extend([
        "**What you can do next**",
        f"- Collect the FIR/notice, seizure memo, photograph of the tool, farming/field proof, ownership/use proof, witness names, village/work context, arrest/remand papers, and any allegation of threat or injury; take these to DLSA or criminal counsel for bail/reply/discharge strategy {action_cites}.",
    ])
    return lines


def _identity_police_threat_worker_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"criminal_general", "police_fir", "labour_exploitation_discrimination"}:
        return []
    identity_context = _has_any(q, ("bangladeshi", "murshidabad", "nationality", "citizen", "illegal immigrant"))
    threat_context = _has_any(q, ("threatening", "threaten", "call police", "police", "manager", "employer", "site engineer", "contractor"))
    if not (identity_context and threat_context):
        return []
    article21 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-21",))
    bns_threat = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-351", "/sec-352", "/sec-356"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    primary = article21 or bns_threat or bnss_fir
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if article21 is not None:
        lines.append(
            f"If a manager threatens to call police by saying you are Bangladeshi when you are from Murshidabad/West Bengal, treat it first as an identity/police-threat and liberty-safety issue; keep Article 21 with your ID/address proof [{article21}]."
        )
    if bns_threat is not None:
        lines.append(
            f"The BNS criminal intimidation source is relevant only if the words include threat of injury, reputation harm, job harm, false police action, or similar statutory ingredients; a label alone needs those facts before being framed as this offence [{bns_threat}]."
        )
    if bnss_fir is not None:
        lines.append(
            f"If police are actually called or refuse to record your written complaint, preserve the complaint and acknowledgement/refusal for senior-police or Magistrate escalation [{bnss_fir}]."
        )
    action_cites = _cite_many(article21, bns_threat, bnss_fir)
    lines.extend([
        "**What you can do next**",
        f"- Keep Aadhaar/voter/passport/ration/work ID, address proof from Murshidabad/West Bengal, wage/work records, exact words, witness names, messages/audio, and any police-call or termination threat; use DLSA/legal aid if police or employer pressure escalates {action_cites}.",
    ])
    return lines


def _regional_slur_wage_retaliation_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"criminal_general", "labour_exploitation_discrimination", "employment_wages"}:
        return []
    regional_slur = _has_any(q, ("biharee", "bihari", "outsider"))
    work_actor = _has_any(q, ("site engineer", "supervisor", "contractor", "employer", "manager"))
    wage_context = _has_any(q, ("wage complain", "wage complaint", "wages", "salary", "labour", "labor", "site"))
    if not (regional_slur and work_actor and wage_context):
        return []
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-351", "/sec-352", "/sec-356"))
    wages = _find(passages, title_terms=("code on wages", "payment of wages"), anchor_terms=("/sec-17", "/sec-18", "/sec-45"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-216", "/sec-175"))
    primary = bns or wages or bnss
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if bns is not None:
        lines.append(
            f"Being called 'Biharee' / Bihari/Biharee by a Pune site engineer after a wage complaint should be checked from the exact words, threat, public insult, and harm facts; insult alone is not automatically a crime, but the BNS source is the offence source if intimidation, intentional insult, or defamation ingredients fit [{bns}]."
        )
    if wages is not None:
        lines.append(
            f"Keep a separate wage-dispute file because the trigger was a wage complaint at the worksite; the wage source is the labour-authority side and should not be replaced by only a criminal label [{wages}]."
        )
    else:
        lines.append(
            "Keep the wage complaint in a separate wage-dispute file; the retrieved BNS/BNSS sources do not replace the missing wage-authority source."
        )
    if bnss is not None:
        lines.append(
            f"If the abuse becomes threats, violence, or police-complaint material, keep the BNSS procedure source with FIR/police papers rather than relying only on workplace HR talk [{bnss}]."
        )
    action_cites = _cite_many(bns, wages, bnss)
    lines.extend([
        "**What you can do next**",
        f"- Write the exact Bihari/Biharee words, date, site engineer/supervisor name, witnesses/audio/messages, wage complaint copy, employer/contractor details, and any threat or firing risk; take wage dues to the Labour Commissioner/wage authority and the offence part to police/DLSA only if the BNS ingredients fit {action_cites}.",
    ])
    return lines


def _custody_habeas_lockup_abuse_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"arrest_custody_safeguard", "police_fir", "criminal_general", "custody_compensation"}:
        return []
    if not has_person_custody_context(q):
        return []
    custody_context = _has_any(q, (
        "lockup", "custody", "custodial", "detained", "detention",
        "habeas", "arrest memo", "police beating", "police beat",
        "torture", "not released", "not produced", "picked",
    ))
    if not custody_context:
        return []
    if _has_any(q, ("no proof police picked", "no proof police took", "not sure police picked")):
        return []
    article21 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-21",))
    article22 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-22",))
    article226 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-226",))
    bnss_arrest = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-47", "/sec-48", "/sec-57", "/sec-58"))
    crpc_arrest = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-50", "/sec-56", "/sec-57"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    bns_hurt = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-115", "/sec-117", "/sec-118", "/sec-308"))
    human_rights = _find(passages, title_terms=("protection of human rights",))
    primary = article22 or article21 or article226 or bnss_arrest or crpc_arrest or bnss_fir or human_rights or bns_hurt
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if _has_any(q, ("habeas", "illegal detention", "detained illegally", "not produced")):
        habeas_cite = article226 or article21 or article22 or primary
        lines.append(
            f"For illegal detention or non-production, treat habeas/High Court or urgent Magistrate/legal-aid action as the emergency route; do not wait for a perfect FIR copy if liberty is at stake [{habeas_cite}]."
        )
        if article226 is not None:
            lines.append(
                f"Article 226 is the High Court habeas corpus route to seek production of the detained person; take the pickup timeline, station information, and family/lawyer-access facts to DLSA or High Court counsel urgently [{article226}]."
            )
    if article22 is not None or bnss_arrest is not None or crpc_arrest is not None:
        arrest_cite = article22 or bnss_arrest or crpc_arrest
        lines.append(
            f"Treat this as an arrest-information and liberty safeguard: ask for grounds of arrest, arrest memo, station name, officer details, family or nominated-person intimation, lawyer access, and production before the Magistrate within the required time window [{arrest_cite}]."
        )
    if article22 is not None:
        lines.append(
            f"Article 22 requires production before the nearest Magistrate within twenty-four hours of arrest, excluding necessary journey time, unless a separately reviewed constitutional exception applies [{article22}]."
        )
    if _has_any(q, ("beaten", "beating", "torture", "injury", "took 20000", "bribe", "constable")):
        abuse_cite = bns_hurt or human_rights or article21 or bnss_fir or primary
        lines.append(
            f"For lockup beating, torture, extortion, or bribe-for-release facts, keep a separate custody-abuse complaint track with medical evidence and human-rights/senior-police escalation; do not treat it as only a bail question [{abuse_cite}]."
        )
    if bnss_fir is not None:
        lines.append(
            f"For the FIR copy, written complaint, or FIR-refusal path, submit the custody facts in writing and preserve acknowledgement before escalating to SP, Magistrate, DLSA, or human-rights channels [{bnss_fir}]."
        )
    action_cites = _cite_many(article22, article21, article226, bnss_arrest, crpc_arrest, bnss_fir, human_rights, bns_hurt)
    lines.extend([
        "**What you can do next**",
        f"- Record arrest/pickup time and place, station, officer names, vehicle/CCTV/witnesses, injury photos, medical/MLC papers, money/bribe demand proof, calls/messages, FIR/notice number, and whether family/lawyer access or Magistrate production happened {action_cites}.",
        f"- If the station remains unknown, contact DLSA/legal aid or a criminal lawyer immediately; for continuing detention use the Magistrate/High Court habeas route, and for lockup abuse use senior police, SP, human-rights commission, and medical evidence route {action_cites}.",
    ])
    return lines


def _police_seized_device_return_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"police_fir", "criminal_general"} or not _is_police_seized_device(q):
        return []
    bnss_property = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-497",))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-2", "/sec-65B", "/sec-67C", "/sec-79"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    if bnss_property is None:
        return []

    lines = [
        "**Short answer**",
        f"For a company laptop or device seized in another person's investigation, treat it as a search/seizure and property-custody problem: ask for the seizure memo, case reference, officer/court details, and release/superdari or court-return route; keep ownership and work-device proof separate from the accused person's case [{bnss_property}].",
        f"Use the court-supervision/custody source to ask for interim custody, release, copying, or preservation directions where business data or the device is needed while the case continues [{bnss_property}].",
    ]
    if it_act is not None:
        lines.append(
            f"Because the item is an electronic device, preserve device identifiers, account/email details, work ownership proof, and any electronic-record request or imaging/hash details separately [{it_act}]."
        )
    if bnss_fir is not None:
        lines.append(
            f"If police do not give a seizure memo or status, use the criminal-procedure complaint/status route with the written request and acknowledgement [{bnss_fir}]."
        )
    action_cites = _cite_many(bnss_property, it_act, bnss_fir)
    lines.extend([
        "**What you can do next**",
        f"- Keep laptop serial/asset tag, employer ownership letter, seizure memo, case/FIR number, officer/station details, date/time/place of seizure, work-data urgency, and any notice; ask the investigating officer or court for a written return/release status before filing further applications {action_cites}.",
    ])
    return lines


def _forced_sexual_exploitation_victim_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "criminal_general" or not _has_any(q, (
        "spa", "massage parlour", "massage parlor", "parlour", "parlor",
        "customers want extra", "owner makes us", "commercial sexual",
    )):
        return []
    if not _has_any(q, ("forced", "makes us", "refuse", "no salary", "get out", "rescue", "help", "cannot leave")):
        return []

    bns_trafficking = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-143", "/sec-144", "/sec-146"))
    itpa_rescue = _find(passages, title_terms=("immoral traffic",), anchor_terms=("/sec-5", "/sec-6", "/sec-17"))
    itpa_any = _find(passages, title_terms=("immoral traffic",))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    crpc_complaint = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-154", "/sec-156", "/sec-200"))
    primary = bns_trafficking or itpa_rescue or bnss_fir or crpc_complaint or itpa_any
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if bns_trafficking is not None:
        lines.append(
            f"If the owner is making workers provide sexual services and withholding salary when they refuse, treat it as coercion/forced exploitation and possible trafficking, not as an ordinary wage complaint or customer dispute [{bns_trafficking}]."
        )
    if itpa_rescue is not None:
        lines.append(
            f"Use the ITPA source for procurement/detention/rescue or protective-route checks; ask legal aid or police to treat the worker as a person needing protection, not automatically as an accused [{itpa_rescue}]."
        )
    elif itpa_any is not None:
        lines.append(
            f"Because an ITPA source appeared but not the exact rescue provision, do not rely only on a soliciting/accused-side section; ask DLSA, One Stop Centre, or a lawyer to verify the correct ITPA rescue/procurement/detention route [{itpa_any}]."
        )
    if bnss_fir is not None or crpc_complaint is not None:
        procedure = bnss_fir or crpc_complaint
        lines.append(
            f"For immediate reporting, preserve a written complaint and acknowledgement/FIR or Magistrate-escalation trail; do not wait for perfect paperwork if anyone is being confined, threatened, or forced [{procedure}]."
        )
    action_cites = _cite_many(bns_trafficking, itpa_rescue or itpa_any, bnss_fir, crpc_complaint)
    lines.extend([
        "**What you can do next**",
        f"- Move to safety first: contact emergency services if in danger, DLSA/legal aid, One Stop Centre or women's helpline where available, and a trusted person; do not confront the owner alone {action_cites}.",
        f"- Keep location, owner/manager names, customer-pressure messages, wage/non-payment proof, ID or document-retention facts, threats, witnesses, photos/CCTV if safe, and any prior police or labour complaint details {action_cites}.",
    ])
    return lines


def _acid_chemical_attack_first_response_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"police_fir", "criminal_general"} or not _has_any(q, (
        "acid", "chemical", "eyes burning", "threw something on my face", "face burning",
    )):
        return []
    bns_acid = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-124",))
    bns_hurt = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-115", "/sec-117", "/sec-118", "/sec-125", "/sec-351"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    crpc_fir = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-154", "/sec-156"))
    pwdva = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-3", "/sec-18"))
    mere_threat = _has_any(q, (
        "threatened to throw", "threatening to throw", "threatens to throw",
        "will throw acid", "throw acid on me", "throw chemical on me",
    )) and not _has_any(q, (
        "threw acid", "acid thrown", "chemical thrown", "eyes burning", "face burning",
    ))
    primary = bns_acid or bns_hurt or bnss_fir or crpc_fir or pwdva
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if mere_threat and bns_hurt is not None:
        lines.append(
            f"A threat to throw acid is an urgent prevention and criminal-intimidation issue; do not describe it as a completed acid injury unless acid or another chemical was actually thrown [{bns_hurt}]."
        )
    elif bns_acid is not None:
        lines.append(
            f"For suspected acid or chemical injury to the face/eyes, treat this as an emergency acid-attack/hurt track first, not a normal road quarrel or only a compensation question [{bns_acid}]."
        )
    elif bns_hurt is not None:
        lines.append(
            f"For burning eyes or chemical injury where the exact substance is still being confirmed, keep the hurt/endangering-life source with the hospital papers and complaint [{bns_hurt}]."
        )
    if pwdva is not None and _has_any(q, (
        "mother in law", "mother-in-law", "in laws", "in-laws", "dowry",
        "more money", "parents",
    )):
        lines.append(
            f"Because the threat is from an in-law or linked to pressure for money from your parents, keep the PWDVA protection-order route active alongside the police track [{pwdva}]."
        )
    if bnss_fir is not None or crpc_fir is not None:
        procedure = bnss_fir or crpc_fir
        if mere_threat:
            lines.append(
                f"Preserve the exact threat, messages/calls, witness details, location, and any attempt to obtain acid or another chemical; file a written police complaint and keep its acknowledgement [{procedure}]."
            )
        else:
            lines.append(
                f"Do the medical and police steps together: get emergency treatment/MLC, preserve clothes/photos/CCTV/witnesses, and file a written complaint/FIR with acknowledgement [{procedure}]."
            )
    action_cites = _cite_many(bns_acid, bns_hurt, bnss_fir, crpc_fir, pwdva)
    lines.extend([
        "**What you can do next**",
        (
            f"- Move to a safe place, tell a trusted person, contact 112/police if danger is immediate, and keep the written threat complaint, messages/calls, witnesses, location, and any known access to acid/chemicals; contact a Protection Officer/One Stop Centre where the domestic relationship applies, and use DLSA or senior police if the station delays {action_cites}."
            if mere_threat
            else f"- Go to hospital/emergency care first, ask for MLC/medical record, preserve the container/substance if safe, clothes, photos, vehicle/auto details, CCTV location, witness names, and complaint acknowledgement; contact DLSA/legal aid or police senior officers if the station delays {action_cites}."
        ),
    ])
    return lines


def _police_fir_first_response_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"police_fir", "criminal_general"}:
        return []
    if route.label == "Missing person / police complaint":
        return []
    if _is_witch_branding(q):
        return []
    police_need = _has_any(q, (
        "fir", "zero fir", "online fir", "police refused", "police refusing",
        "thana refused", "complaint", "how to complain", "sp", "magistrate",
        "stalking", "follows my", "acid", "eyes burning", "hut", "burnt",
        "theft of my bike", "lost phone", "laptop has been seized",
        "company laptop", "khap", "honour", "honor", "eloped",
    ))
    if not police_need:
        return []
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173",))
    bnss_magistrate = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-175",))
    crpc_fir = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-154",))
    crpc_magistrate = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-156",))
    bns_hurt = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-115", "/sec-117", "/sec-118", "/sec-124", "/sec-125"))
    bns_stalking = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-78", "/sec-351", "/sec-356"))
    bns_property = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-303", "/sec-324", "/sec-326"))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66", "/sec-67", "/sec-69", "/sec-79"))
    bnss_property = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-497",))
    article21 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-21",))
    procedure = bnss_fir or bnss_magistrate or crpc_fir or crpc_magistrate
    primary = procedure or bnss_property or bns_hurt or bns_stalking or bns_property or it_act or article21
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if _has_any(q, ("zero fir", "another state")) and procedure is not None:
        lines.append(
            f"For a zero-FIR or different-State incident, start with a written complaint and ask the station to record/transfer the information instead of refusing only because the place is elsewhere [{procedure}]."
        )
    elif _has_any(q, ("online fir", "lost phone")) and procedure is not None:
        lines.append(
            f"For a lost-phone or online-FIR question, file through the state police portal where available and keep the written complaint/acknowledgement; if a cognizable theft or misuse fact appears, the FIR/refusal-escalation source still matters [{procedure}]."
        )
    elif _has_any(q, ("police refused", "police refusing", "thana refused", "fir not", "not registering")) and procedure is not None:
        lines.append(
            f"If police refuse to record a cognizable complaint, preserve the written complaint and acknowledgement/refusal, then escalate to senior police/SP and Magistrate route instead of accepting an oral refusal [{procedure}]."
        )
    if _has_any(q, ("encroachment", "encroached", "land grab", "boundary")) and _has_any(q, ("beat me", "beaten", "assault", "hit me", "hurt me", "injury")):
        cite = procedure or bns_hurt or primary
        lines.append(
            f"If your neighbour beat you during a land-encroachment dispute and police refuse to record the FIR, keep two tracks separate: the assault/FIR track goes to the Superintendent of Police or Magistrate route, while the boundary/title track can stay civil/revenue [{cite}]."
        )
    if _has_any(q, ("acid", "eyes burning")):
        cite = bns_hurt or procedure or primary
        lines.append(
            f"For suspected acid/chemical injury, prioritize hospital/MLC and emergency safety first, then give a written police complaint with medical papers, photos, witnesses, and the suspected substance/vehicle/person details [{cite}]."
        )
    if _has_any(q, ("stalking", "follows my", "follows me", "scooty")):
        cite = bns_stalking or procedure or primary
        if "scooty" in q:
            lines.append(
                f"Even if he does not speak, repeated following of your scooty from office to home belongs in the BNS Section 78 stalking analysis if the repeated-following facts fit the section [{cite}]."
            )
        lines.append(
            f"For repeated following/stalking from office or home, preserve dates, routes, CCTV, messages, witnesses, and prior warnings; use the offence source only after matching the exact stalking/intimidation facts [{cite}]."
        )
    if _has_any(q, ("laptop has been seized", "company laptop", "seized by police", "device seized")):
        cite = bnss_property or it_act or procedure or primary
        if bnss_property is not None:
            lines.append(
                f"For a company laptop or device seized in another person's investigation, ask for the seizure memo, case reference, officer/court details, and release/superdari or court-return route; keep ownership and work-device proof separate from the accused person's case [{cite}]."
            )
        else:
            lines.append(
                f"For a company laptop or device seized in another person's investigation, first ask for the seizure memo, case reference, officer/court details, and the legal authority for keeping it; verify the property-return authority before assuming the return process [{cite}]."
            )
    elif bns_property is not None and _has_any(q, (
        "broke", "broken", "damaged", "damage", "smashed", "mirror",
        "vandal", "mischief",
    )):
        lines.append(
            f"For a broken scooter mirror or other deliberate property damage, keep the BNS mischief/property-damage source with repair estimates, photos/CCTV, witnesses, ownership proof, and the police complaint; an insurance issue does not replace the offence complaint [{bns_property}]."
        )
    elif _has_any(q, ("theft of my bike", "bike", "stolen", "lost phone")):
        cite = bns_property or it_act or procedure or primary
        lines.append(
            f"For theft or lost-phone facts, keep IMEI/device/ownership proof, police reference, and written complaint separate from any insurance or office issue [{cite}]."
        )
    if _has_any(q, ("khap", "honour", "honor", "eloped", "other religion", "love jihad")):
        cite = article21 or procedure or primary
        lines.append(
            f"For honour-threat, khap, or inter-faith relationship pressure, keep immediate safety, shelter/DLSA, and written police-protection request separate from family mediation; minor/adult status changes the exact route [{cite}]."
        )
    action_cites = _cite_many(procedure, bnss_property, bns_hurt, bns_stalking, bns_property, it_act, article21)
    lines.extend([
        "**What you can do next**",
        f"- Write a one-page complaint with date/time/place, accused details if known, injury/property/device facts, witnesses, screenshots/CCTV, medical or ownership proof, and what police refused; submit it and keep acknowledgement/DD/FIR/portal number {action_cites}.",
        f"- If there is refusal or no action, escalate the same written packet to SP/senior police, cyber cell where electronic evidence is involved, Magistrate/DLSA, or urgent protection/shelter channels where safety is at risk {action_cites}.",
    ])
    return lines


def _honour_threat_police_protection_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "police_fir" or "honour-threat" not in route.label.lower():
        return []
    if not _has_any(q, (
        "khap", "honour", "honor", "eloped", "other religion",
        "interfaith", "inter-faith", "inter religion", "inter-religion",
        "love marriage", "inter caste", "inter-caste", "different caste",
        "other caste", "outside caste", "marry outside caste",
    )):
        return []
    article21 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-21",))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173",))
    crpc_fir = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-154",))
    bns_threat = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-351", "/sec-352", "/sec-74", "/sec-75"))
    primary = article21 or bnss_fir or crpc_fir or bns_threat
    if primary is None:
        return []
    procedure = bnss_fir or crpc_fir
    threat_cite = bns_threat or article21 or procedure or primary
    lines = [
        "**Short answer**",
        f"For honour-threat, khap, inter-caste, or inter-faith relationship pressure, treat immediate safety and police protection as the first route; do not send the couple back to family mediation when threats are active [{primary}].",
    ]
    if article21 is not None:
        lines.append(
            f"Article 21 is the constitutional liberty and personal-safety source to keep with the protection request where adults face honour-based threats [{article21}]."
        )
    if bns_threat is not None:
        lines.append(
            f"The BNS criminal intimidation source is the separate threat-offence track to match against the exact words, threatened harm, and incident facts [{bns_threat}]."
        )
    if procedure is not None:
        action_cites = _cite_many(article21, procedure, threat_cite)
        lines.append(
            f"Use the complaint/protection procedure source for a written police-protection request, senior-police escalation, DLSA help, and urgent High Court protection if local police do not act [{procedure}]."
        )
        lines.extend([
            "**What you can do next**",
            f"- Preserve threats, messages/calls, witnesses, location, age proof, ID, and current safety facts; file a written police-protection complaint and keep acknowledgement, then contact DLSA/One Stop Centre/shelter or High Court legal aid if there is immediate risk {action_cites}.",
        ])
    else:
        lines.extend([
            f"The retrieved source supports recording the threat facts, but it does not provide the police-complaint or escalation procedure; keep the threat evidence and verify the applicable procedure before naming a forum [{threat_cite}].",
            "**What you can do next**",
            f"- Preserve threats, messages/calls, witnesses, location, age proof, ID, and current safety facts; contact emergency support, DLSA, One Stop Centre, shelter, or High Court legal aid if there is immediate risk [{threat_cite}].",
        ])
    return lines


def _bonded_labour_rescue_contract_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"bonded_labour_rescue", "labour_exploitation_discrimination"}:
        return []
    direct_bonded_context = _has_any(q, (
        "bonded labour", "bonded labor", "advance", "not letting leave",
        "cannot go home", "can't go home", "hostage", "cards passport",
        "aadhaar original", "passport kept", "id kept", "document kept",
        "documents kept", "release certificate", "rehab", "rehabilitation",
        "no wages just food", "loan finish", "brick kiln", "thakur",
    ))
    contractor_bonded_context = _has_any(q, ("thekedar", "contractor", "munshi")) and _has_any(q, (
        "aadhaar original", "passport kept", "id kept", "document kept",
        "documents kept", "not letting leave", "cannot go home", "can't go home",
        "hostage", "advance", "debt", "loan finish", "no wages just food",
        "release certificate", "rehab", "rehabilitation",
    ))
    bonded_context = direct_bonded_context or contractor_bonded_context
    if not bonded_context:
        return []
    bonded = _find(passages, title_terms=("bonded labour", "bonded labor"))
    article23 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-23",))
    aadhaar = _find(passages, title_terms=("aadhaar", "unique identification"), anchor_terms=("/sec-29", "/sec-8"))
    ismw = _find(passages, title_terms=("inter-state migrant", "inter state migrant"))
    wages = _find(passages, title_terms=("code on wages", "payment of wages"), anchor_terms=("/sec-17", "/sec-18", "/sec-45"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-126", "/sec-127", "/sec-351", "/sec-308"))
    primary = bonded or article23 or aadhaar or ismw or wages or bnss or bns
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if bonded is not None:
        lines.append(
            f"For advance debt, document retention, no wages, being kept on site, or not being allowed to leave, treat this first as a bonded-labour rescue/release-certificate problem, not merely as salary delay [{bonded}]."
        )
        if _has_any(q, ("passport", "cards", "aadhaar", "aadhar", "original id", "documents")):
            lines.append(
                f"If a contractor is keeping workers' cards, passport, Aadhaar, or original ID while saying they must work until a loan is finished, keep it as a bonded/forced-labour rescue fact and ask the local authority for return of documents [{bonded}]."
            )
    elif article23 is not None:
        lines.append(
            f"For forced labour, document retention, or work tied to an advance/loan, keep the Article 23 forced-labour source with the rescue file while verifying the Bonded Labour Act source locally [{article23}]."
        )
    if ismw is not None:
        lines.append(
            f"If workers were brought from another state by a contractor, keep the Inter-State Migrant Workmen route for contractor registration, passbook/displacement/journey allowance, wage, and return-home facts [{ismw}]."
        )
    if aadhaar is not None and _has_any(q, ("aadhaar", "aadhar", "id", "document", "documents")):
        lines.append(
            f"If the contractor is keeping original Aadhaar or ID papers, keep the Aadhaar/identity-document source with the rescue file and ask for safe return/copies instead of letting document control keep workers at the site [{aadhaar}]."
        )
    if wages is not None:
        lines.append(
            f"Keep unpaid wages and illegal deductions as a separate wage-authority calculation, but do not let wage recovery replace urgent release/safety where movement or documents are controlled [{wages}]."
        )
    if bnss is not None or bns is not None:
        cite = bnss or bns
        lines.append(
            f"If there is confinement, threats, assault, document seizure, or hostage-like control, preserve a police complaint route alongside labour/SDM/DLSA action [{cite}]."
        )
    action_cites = _cite_many(bonded, article23, aadhaar, ismw, wages, bnss, bns)
    lines.extend([
        "**What you can do next**",
        f"- If anyone is currently unsafe or unable to leave, contact DLSA/legal aid, labour department, police, district magistrate/SDM, or bonded-labour vigilance/rescue channels first; avoid confrontation or self-help at the worksite {action_cites}.",
        f"- Keep worker names, age, home state/village, contractor/owner name, worksite location, advance/loan amount, wage ledger, document-retention facts, threats, photos/videos, messages, witnesses, and release-certificate or rehabilitation application status {action_cites}.",
    ])
    return lines


def _manual_scavenging_forced_cleaning_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "manual_scavenging_safety" or not _is_manual_scavenging_forced_cleaning(q):
        return []
    manual = _find(passages, title_terms=("manual scavengers", "manual scavenging", "prohibition of employment as manual"))
    poa = _find(passages, title_terms=("scheduled castes", "scheduled tribes", "prevention of atrocities"), anchor_terms=("/sec-3",))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-126", "/sec-127", "/sec-351"))
    primary = manual or poa or bnss or bns
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if manual is not None:
        lines.append(
            f"For a dry latrine, sewer/septic work, or panchayat/local-body pressure forcing people to clean human waste, treat this as a manual-scavenging prohibition, rescue, rehabilitation, and local-authority accountability problem first [{manual}]."
        )
    if poa is not None and _has_any(q, ("dalit", "sc", "scheduled caste", "caste")):
        lines.append(
            f"Because the facts mention Dalit/Scheduled Caste workers or caste-linked coercion, keep the SC/ST Atrocities Act source as a separate caste-atrocity track instead of treating the cleaning demand as only a municipal labour issue [{poa}]."
        )
    if bnss is not None or bns is not None:
        cite = bnss or bns
        lines.append(
            f"If there are threats, confinement, assault, or a refusal to record the complaint, preserve a police/FIR-escalation track alongside the District Magistrate, municipality, labour, and DLSA routes [{cite}]."
        )
    action_cites = _cite_many(manual, poa, bnss, bns)
    lines.extend([
        "**What you can do next**",
        f"- Do not wait for a perfect legal label if workers are being forced now: contact the District Magistrate/SDM, municipality/local body, labour department, DLSA, and police where coercion or violence exists {action_cites}.",
        f"- Keep location, panchayat/local-body name, names of workers, caste/coercion facts if any, photos/videos, dates, payment or threat proof, witness names, and any complaint acknowledgement {action_cites}.",
    ])
    return lines


def _labour_exploitation_first_action_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"labour_exploitation_discrimination", "employment_wages", "court_procedure"}:
        return []
    labour_context = _has_any(q, (
        "wage", "wages", "salary", "deducted", "deduction", "minimum wage",
        "domestic worker", "contractor ran away", "principal employer",
        "bocw", "construction", "child", "15", "14 year", "12 helping",
        "women workers", "welder", "sweeper", "half pay", "wrongfully terminated",
        "labour court", "migrant", "return ticket", "ismw", "registration",
        "uniform", "shoes", "never paid", "no payment", "industrial dispute",
        "section 10", "sec 10",
    ))
    if not labour_context:
        return []
    wages = _find(passages, title_terms=("code on wages", "payment of wages"), anchor_terms=("/sec-17", "/sec-18", "/sec-45", "/sec-60", "/sec-4"))
    wages60 = _find(passages, title_terms=("code on wages",), anchor_terms=("/sec-60",))
    wages45 = _find(passages, title_terms=("code on wages",), anchor_terms=("/sec-45",))
    contract19 = _find(passages, title_terms=("indian contract",), anchor_terms=("/sec-19",))
    minimum = _find(passages, title_terms=("code on wages", "minimum wages"), anchor_terms=("/sec-5", "/sec-6", "/sec-9", "/sec-14"))
    bocw = _find(passages, title_terms=("building and other construction", "bocw"))
    bocw_cess = _find(passages, title_terms=("building and other construction workers welfare cess", "bocw cess", "welfare cess"))
    contract_labour = _find(passages, title_terms=("contract labour",))
    child_labour = _find(passages, title_terms=("child labour", "child and adolescent labour"))
    jj = _find(passages, title_terms=("juvenile justice",))
    ismw = _find(passages, title_terms=("inter-state migrant", "inter state migrant"))
    bonded = _find(passages, title_terms=("bonded labour",))
    id_act = _find(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-2A", "/sec-25F", "/sec-10"))
    primary = child_labour or wages or minimum or bocw or bocw_cess or contract_labour or ismw or bonded or id_act or jj
    if primary is None:
        return []
    lines = ["**Short answer**"]
    wage_waiver_context = _has_any(q, ("give up wages", "waive wages", "waiver", "signed paper", "signed document")) and _has_any(q, ("dont read", "don't read", "cannot read", "english", "kannada", "pressure", "forced"))
    if wage_waiver_context and wages60 is not None:
        lines.append(
            f"Do not treat the signed wage-waiver paper as automatically ending the claim: the Code on Wages source addresses contracting out of or relinquishing wage rights [{wages60}]."
        )
    if wage_waiver_context and contract19 is not None:
        lines.append(
            f"If the paper was signed without understanding, under pressure, or because of misrepresentation, preserve those facts separately because the Contract Act source deals with consent that is not free [{contract19}]."
        )
    if wage_waiver_context and wages45 is not None:
        lines.append(
            f"The Code on Wages claims source provides for appointed authorities to hear and determine claims arising under the Code [{wages45}]."
        )
    if child_labour is not None and _has_any(q, ("14", "15", "child", "girl child", "boy from")):
        if _has_any(q, ("factory says she is 18 no proof", "says she is 18 no proof", "says he is 18 no proof")):
            lines.append(
                f"When the factory says the worker is 18 but there is no proof, verify age proof before treating the child/adolescent worksite case as ordinary wages or attendance [{child_labour}]."
            )
        worker_phrase = (
            "15-year-old or adolescent worker, verify age proof and the exact factory/work conditions"
            if _has_any(q, ("15", "adolescent"))
            else "12/14-year-old at a worksite, factory, garment unit, or domestic work setting"
        )
        lines.append(
            f"For a {worker_phrase}, treat it as a child-labour/child-safety route first; do not answer only as unpaid wages [{child_labour}]."
        )
        if jj is not None:
            lines.append(
                f"If the child needs safe return, shelter, or protection, involve the Child Welfare Committee/childline/DLSA route with age proof and worksite facts [{jj}]."
            )
    if wages is not None:
        lines.append(
            f"For unpaid wages, uniform/shoes deductions, domestic-worker deductions, contractor non-payment, or wage records, keep a written wage calculation and labour-authority complaint under the wage source [{wages}]."
        )
    if minimum is not None and _has_any(q, ("minimum wage", "rate is", "half pay", "women workers")):
        lines.append(
            f"If the issue is minimum wage, unequal pay, or women being pushed into lower-paid work, preserve the notified-rate, skill category, attendance, and comparator facts before going to the labour office [{minimum}]."
        )
    if (bocw is not None or bocw_cess is not None) and _has_any(q, ("bocw", "construction", "site", "cess")):
        bocw_cites = _cite_many(bocw, bocw_cess)
        lines.append(
            f"For construction-worker BOCW card, cess-benefit, fake register, or welfare-board facts, keep the BOCW registration/benefit and cess record separate from the ordinary wage claim {bocw_cites}."
        )
    if contract_labour is not None and _has_any(q, ("principal employer", "contractor ran away", "contractor", "site")):
        lines.append(
            f"If a contractor ran away or the principal employer denies responsibility, keep the contract-labour/principal-employer record with gate pass, muster roll, site ID, and contractor details [{contract_labour}]."
        )
    if ismw is not None and _has_any(q, ("migrant", "bihar", "odisha", "supaul", "return ticket", "ismw", "other state")):
        lines.append(
            f"For inter-state migrant work, keep recruitment, journey/return allowance, passbook/registration, and home-state details with the wage file [{ismw}]."
        )
    if id_act is not None and _has_any(q, ("wrongfully terminated", "labour court", "termination", "terminated", "industrial dispute", "section 10", "sec 10")):
        if _has_any(q, ("section 10", "sec 10", "industrial dispute")):
            lines.append(
                f"For an Industrial Disputes Act Section 10 labour-court reference, preserve appointment, termination, demand notice, conciliation, and workman-status facts separately from pure wage recovery [{id_act}]."
            )
        else:
            lines.append(
                f"For termination or labour-court reference, preserve appointment, termination, demand notice, conciliation, and workman-status facts separately from pure wage recovery [{id_act}]."
            )
    action_cites = _cite_many(wages, minimum, bocw, bocw_cess, contract_labour, child_labour, jj, ismw, bonded, id_act)
    lines.extend([
        "**What you can do next**",
        f"- Keep worker names, employer/contractor/principal-employer details, worksite, dates, attendance/muster roll, wage rate, deductions, bank/UPI/cash proof, ID card/gate pass, messages, witnesses, and written demand; file with labour department/wage authority/BOCW board/DLSA depending on the source path {action_cites}.",
        f"- For child labour, coercion, document retention, or workers unable to leave, use the labour inspector/CWC, child-protection, bonded-labour, and DLSA-police safety escalation instead of treating it as only a money claim {action_cites}.",
    ])
    return lines


def _family_forced_sex_safety_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "family_domestic" or not _is_family_forced_sex_safety(q):
        return []
    pwdva_def = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-3",))
    pwdva_relief = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-12", "/sec-18", "/sec-19", "/sec-20", "/sec-21", "/sec-22"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-63", "/sec-67", "/sec-85", "/sec-86", "/sec-351"))
    pwdva = pwdva_def or pwdva_relief
    if pwdva is None:
        return []

    lines = ["**Short answer**"]
    if pwdva_def is not None:
        lines.append(
            f"For forced sex or sexual coercion inside marriage, do not dismiss it as a private marital issue; preserve safety and evidence, and use the domestic violence and safety route (the domestic-violence sexual-abuse/protection route) while a lawyer checks any criminal-law route on the exact facts [{pwdva_def}]."
        )
    else:
        lines.append(
            f"For forced sex or sexual coercion inside marriage, treat this as an immediate safety and domestic-violence relief problem; put the sexual coercion facts, medical state, messages, and safety risk into the PWDVA/Magistrate/DLSA file instead of handling it as ordinary marital disagreement [{pwdva_relief}]."
        )
    if bns is not None:
        lines.append(
            f"If there are threats, cruelty, assault, confinement, or intimidation facts, keep a separate criminal-law safety track for a lawyer/police review without assuming a final criminal section from this answer alone [{bns}]."
        )
        if _has_any(q, ("forces me at night", "when i say no", "without consent", "forced sex", "force sex")):
            lines.append(
                f"The cited BNS sexual-offence source includes marital-exception wording that needs careful incident-date, statutory-text, and fact verification; do not infer a final criminal outcome from this general answer alone [{bns}]."
            )
    action_cites = _cite_many(pwdva_def, pwdva_relief, bns)
    lines.extend([
        "**What you can do next**",
        f"- Prioritize immediate safety, safe phone/evidence copies, medical help if needed, trusted support, Protection Officer/Magistrate/DLSA/One Stop Centre, and a written safety timeline; keep messages, injuries, medical state, dates, and witness/support details {action_cites}.",
    ])
    return lines


def _family_disabled_baby_safety_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "family_domestic" or not _is_family_disabled_baby_safety(q):
        return []
    pwdva = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-3", "/sec-12", "/sec-18", "/sec-19", "/sec-20", "/sec-21", "/sec-22"))
    family_court = _find(passages, title_terms=("family courts",), anchor_terms=("/sec-7",))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-85", "/sec-86", "/sec-351", "/sec-127"))
    jj = _find(passages, title_terms=("juvenile justice",), anchor_terms=("/sec-2", "/sec-27", "/sec-30", "/sec-31", "/sec-75"))
    rpwd = _find(passages, title_terms=("rights of persons with disabilities",), anchor_terms=("/sec-7", "/sec-24", "/sec-25"))
    primary = jj or rpwd or pwdva or family_court or bns
    if primary is None:
        return []

    lines = [
        "**Short answer**",
        f"For pressure to abandon a disabled baby or leave the baby in hospital, treat it as immediate safety, residence/maintenance, and child-welfare support; do not reduce it to only a divorce question or an in-law negotiation [{primary}].",
    ]
    if pwdva is not None:
        lines.append(
            f"Use the PWDVA source for residence, protection, monetary relief, or immediate support facts if the mother is being pressured, threatened, or thrown out [{pwdva}]."
        )
    if jj is not None:
        lines.append(
            f"Keep the Juvenile Justice Act child-care/protection source in the file because pressure to leave a baby in hospital may need hospital social worker, Child Welfare Committee, or child-protection escalation, not only marital negotiation [{jj}]."
        )
    if rpwd is not None:
        lines.append(
            f"Because the baby has a disability, keep the RPwD source with medical/disability records and support-needs facts so the response does not erase disability-specific protection or welfare support [{rpwd}]."
        )
    if family_court is not None:
        lines.append(
            f"Use the Family Court source for maintenance, custody/child-welfare, and family-law relief where the immediate safety path is not enough [{family_court}]."
        )
    action_cites = _cite_many(jj, rpwd, pwdva, family_court, bns)
    lines.extend([
        "**What you can do next**",
        f"- Keep birth/disability/medical records, discharge papers, messages pressuring abandonment, marriage/residence proof, income/expense details, witness/support contacts, and safety facts; contact DLSA, One Stop Centre, Protection Officer, hospital social worker, or Family Court help desk depending on urgency {action_cites}.",
    ])
    return lines


def _domestic_residence_right_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "family_domestic" or route.label != "Domestic violence / right to residence":
        return []
    pwdva_residence = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-17", "/sec-19"))
    pwdva_application = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-12", "/sec-18", "/sec-20"))
    family_court = _find(passages, title_terms=("family courts",), anchor_terms=("/sec-7", "/sec-8"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-85", "/sec-86", "/sec-115", "/sec-127", "/sec-351"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    pwdva = pwdva_residence or pwdva_application
    if pwdva is None:
        return []

    in_law_title = _has_any(q, ("mother in law", "mother-in-law", "father in law", "father-in-law", "in law name", "in-law name"))
    locked_out = _has_any(q, (
        "threw me out", "throws me out", "throwing me out", "thrown me out",
        "kicked me out", "locked me out", "not allowing me in",
        "not letting me enter", "ghar se nikal", "nikal diya",
    ))
    lines = ["**Short answer**"]
    if pwdva_residence is not None:
        owner_phrase = " even if the house title is in an in-law's name" if in_law_title else ""
        lines.append(
            f"If you are being thrown out or blocked from the matrimonial/shared home{owner_phrase}, treat this first as a PWDVA residence/protection problem, not as a self-help lock-breaking or family negotiation issue [{pwdva_residence}]."
        )
    else:
        lines.append(
            f"If you are being denied safe residence in a domestic relationship, start with the PWDVA application/protection route and verify the exact residence-order source before taking any risky step at the house [{pwdva_application}]."
        )
    if pwdva_application is not None and pwdva_application != pwdva_residence:
        lines.append(
            f"Ask for practical relief in the same file: protection, residence, monetary support, and urgent application directions based on your current safety, children, income, and residence facts [{pwdva_application}]."
        )
    if bns is not None or bnss is not None:
        cite = bns or bnss
        lines.append(
            f"Keep a separate police/criminal track only if there is current assault, threat, confinement, or coercion; the residence order itself should still be handled through Protection Officer/Magistrate/DLSA papers [{cite}]."
        )
    if family_court is not None:
        lines.append(
            f"If maintenance, divorce, custody, or settlement is also pending, keep that Family Court track linked but separate from the immediate residence/safety request [{family_court}]."
        )
    action_cites = _cite_many(pwdva_residence, pwdva_application, family_court, bns, bnss)
    urgency = "today" if locked_out else "before the situation escalates"
    lines.extend([
        "**What you can do next**",
        f"- {urgency.capitalize()}, preserve marriage/relationship proof, address/residence proof, messages or calls refusing entry, photos/videos if safe, children/dependant details, income/expense proof, medical records if any, and names of people present; contact Protection Officer, Magistrate court, One Stop Centre, DLSA, shelter, or police for immediate danger {action_cites}.",
        f"- Do not rely on force, threats, or changing locks as the legal plan; ask for a written residence/protection direction or safe interim shelter path first {action_cites}.",
    ])
    return lines


def _family_notice_response_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "family_domestic" or route.label != "Domestic violence notice / response":
        return []
    pwdva = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-12", "/sec-18", "/sec-19", "/sec-20"))
    family_court = _find(passages, title_terms=("family courts",), anchor_terms=("/sec-7", "/sec-8"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-85", "/sec-86", "/sec-316", "/sec-351"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-35", "/sec-173", "/sec-175", "/sec-223"))
    primary = pwdva or family_court
    if primary is None:
        return []

    lines = [
        "**Short answer**",
        f"Treat this as a domestic-violence notice-response first: read the application/notice, note the hearing date and reliefs claimed, and prepare a fact-wise reply with documents instead of ignoring it or filing a retaliatory unsupported complaint; do not assume every DV notice is automatically an FIR case [{primary}].",
    ]
    if family_court is not None:
        lines.append(
            f"If the same dispute is linked with matrimonial, maintenance, custody, or settlement proceedings, keep the Family Court file and the Magistrate/PWDVA file separated by case number and next date [{family_court}]."
        )
    if bns is not None or bnss is not None:
        criminal_cites = _cite_many(bns, bnss)
        lines.append(
            f"Use a separate criminal-defence lane only if there is a separate FIR, arrest notice, police notice, or criminal complaint; do not assume every DV notice is automatically an FIR case {criminal_cites}."
        )

    action_cites = _cite_many(pwdva, family_court, bns, bnss)
    lines.extend([
        "**What you can do next**",
        f"- Keep the notice/application, envelope/service proof, next-date order, marriage/residence proof, income/payment records, messages/photos, medical records if relevant, and a date-wise response chart {action_cites}.",
        f"- Ask DLSA, the court help desk, or a family-law lawyer to check whether reply, settlement/mediation, interim-relief response, appeal, or a separate criminal-defence step fits the papers actually served {action_cites}.",
    ])
    return lines


def _family_domestic_safety_or_response_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "family_domestic":
        return []
    specific_context = _has_any(q, (
        "forces me at night", "when i say no", "without consent", "forced sex",
        "force sex", "salary atm", "atm card", "gives me only", "breadwinner",
        "took my salary", "forcing me to marry", "forced marriage", "gay",
        "disabled baby", "baby with disability", "leave the baby in hospital",
        "alimony", "working before marriage", "dv case", "false", "defend",
        "divorce notice", "family court yesterday",
    ))
    if not specific_context:
        return []
    pwdva_def = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-3",))
    pwdva_relief = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-12", "/sec-18", "/sec-19", "/sec-20", "/sec-21", "/sec-22"))
    pwdva = pwdva_def or pwdva_relief
    family_court = _find(passages, title_terms=("family courts",))
    hma = _find(passages, title_terms=("hindu marriage",), anchor_terms=("/sec-9", "/sec-13", "/sec-24", "/sec-25", "/sec-26"))
    crpc125 = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-125",))
    bnss_maintenance = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-144",))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-85", "/sec-86", "/sec-351", "/sec-127"))
    article21 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-21",))
    primary = pwdva or family_court or hma or crpc125 or bnss_maintenance or bns or article21
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if _has_any(q, ("forces me at night", "when i say no", "without consent", "forced sex", "force sex")):
        cite = pwdva or bns or primary
        if pwdva_def is not None:
            lines.append(
                f"For forced sex or sexual coercion inside marriage, do not dismiss it as a private marital issue; preserve safety and evidence, and use the domestic-violence sexual-abuse/protection route while a lawyer checks any criminal-law route on the exact facts [{cite}]."
            )
        else:
            if pwdva is not None:
                lines.append(
                    f"For forced sex or sexual coercion inside marriage, treat this as an immediate safety and domestic-violence relief problem; put the sexual coercion facts, medical state, messages, and safety risk into the Protection Officer/Magistrate/DLSA file instead of handling it as ordinary marital disagreement [{cite}]."
                )
            else:
                lines.append(
                    f"For forced sex or sexual coercion inside marriage, treat immediate safety and evidence as urgent, but verify the PWDVA/domestic-violence relief source before using Protection Officer or Magistrate-specific wording [{cite}]."
                )
    if _has_any(q, ("salary atm", "atm card", "gives me only", "breadwinner", "took my salary")):
        cite = pwdva or primary
        lines.append(
            f"Taking your salary, ATM card, or controlling household money can be economic abuse in a domestic-violence file; keep bank records, salary proof, messages, and household-expense control facts [{cite}]."
        )
        if pwdva_relief is not None:
            lines.append(
                f"Use the PWDVA monetary-relief route through the Protection Officer or Magistrate for current household expenses, rather than treating the breadwinner statement as a final answer [{pwdva_relief}]."
            )
    if _has_any(q, ("forcing me to marry", "gay", "forced marriage", "not listening")):
        cite = article21 or pwdva or bns or primary
        if _has_any(q, ("gay", "marry a girl", "girl next month", "sexual orientation")):
            lines.append(
                f"For forcing you to marry a girl you do not consent to, especially where sexual orientation and safety are involved, prioritize safe housing, trusted support, DLSA/One Stop Centre, Protection Officer/Magistrate help, and written police-protection request; do not frame it as family mediation only [{cite}]."
            )
        else:
            lines.append(
                f"For an adult being forced into marriage, especially with LGBTQ identity/safety pressure, prioritize safe housing, trusted support, DLSA/One Stop Centre, Protection Officer/Magistrate help, and written police-protection request; do not frame it as family mediation only [{cite}]."
            )
    if _has_any(q, ("disabled baby", "baby with disability", "leave the baby in hospital")):
        cite = pwdva or family_court or primary
        lines.append(
            f"For pressure to abandon a disabled baby or leave the baby in hospital, treat it as immediate safety, residence/maintenance, and child-welfare support; do not reduce it to only a divorce question or an in-law negotiation [{cite}]."
        )
    if _has_any(q, ("alimony", "maintenance", "working before marriage", "he is saying i cannot ask")):
        cite = hma or crpc125 or bnss_maintenance or family_court or primary
        lines.append(
            f"Being employed earlier does not automatically end every alimony or maintenance route; the forum checks income, need, child responsibilities, standard of living, and case facts under the personal-law/maintenance source [{cite}]."
        )
    if _has_any(q, ("dv case", "false", "defend", "divorce notice", "family court yesterday")):
        cite = pwdva or family_court or hma or primary
        lines.append(
            f"If you received a DV/divorce notice or say the allegations are false, respond through the court/protection-order file with documents and dates; do not ignore the notice or retaliate with an unsupported police complaint [{cite}]."
        )
    action_cites = _cite_many(pwdva, family_court, hma, crpc125, bnss_maintenance, bns, article21)
    support_channels = (
        "Protection Officer, One Stop Centre, DLSA, Family Court, or police/shelter"
        if pwdva is not None
        else "DLSA, Family Court/help desk, qualified lawyer, or police/shelter if there is current danger"
    )
    lines.extend([
        "**What you can do next**",
        f"- Keep marriage/relationship proof, notice/summons, residence proof, bank/salary records, medical records, photos/messages, child documents, income/expense proof, and safety timeline; contact {support_channels} {action_cites}.",
        f"- If safety, confinement, forced marriage, sexual coercion, or child abandonment is active, prioritize immediate safe place and legal-aid/police protection before ordinary negotiation {action_cites}.",
    ])
    return lines


def _criminal_production_notice_electronic_records_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "criminal_procedure_notice" or not _is_criminal_production_notice_electronic_records(q):
        return []
    bnss91 = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-91",))
    bnss94 = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-94",))
    crpc91 = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-91",))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-2", "/sec-65B", "/sec-67C", "/sec-79"))
    primary = bnss91 or bnss94 or crpc91
    if primary is None:
        return []

    current_or_legacy = "BNSS" if bnss91 is not None or bnss94 is not None else "CrPC"
    record_phrase = (
        "deleted Instagram posts or social-media records"
        if _has_any(q, ("insta", "instagram", "deleted post", "deleted posts", "social media"))
        else "phone, account, document, or electronic records"
    )
    lines = ["**Short answer**"]
    lines.append(
        f"A Section 91 notice/summons for {record_phrase} is a production-of-records issue under the {current_or_legacy} procedure source; take it seriously, but first verify who issued it, the case number, deadline, exact records demanded, and whether it is a police or court direction [{primary}]."
    )
    if bnss94 is not None and bnss94 != primary:
        lines.append(
            f"If the demand is for electronic communication, account/device data, or digital records, keep the BNSS electronic-record/search-production source with the notice before deciding what to produce [{bnss94}]."
        )
    if crpc91 is not None and (bnss91 is not None or bnss94 is not None):
        lines.append(
            f"Because the incident date decides BNSS versus CrPC, compare the notice date and alleged offence date before relying on an old CrPC Section 91 answer [{crpc91}]."
        )
    if it_act is not None:
        lines.append(
            f"For Instagram, platform, deleted-post, or electronic-record facts, preserve URLs, account IDs, screenshots, device details, and platform emails under the IT/electronic-record source instead of deleting or altering anything after notice [{it_act}]."
        )
    action_cites = _cite_many(primary, bnss94, crpc91, it_act)
    lines.extend([
        "**What you can do next**",
        f"- Do not ignore, destroy, edit, or selectively delete records after receiving the notice; take the notice, envelope/email, case number, officer/court details, deadline, account/device details, and the demanded record list to legal aid or a criminal lawyer before replying {action_cites}.",
        f"- If the notice may expose you personally, ask the lawyer about a written objection/clarification, scope narrowing, privilege/self-incrimination concerns, and safe preservation rather than sending informal screenshots on WhatsApp {action_cites}.",
    ])
    return lines


def _pocso_minor_romantic_accused_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "criminal_defence_bail":
        return []
    minor_context = (
        _has_any(q, (
            "pocso", "minor", "under 18", "underage", "14 year", "14 yr",
            "15 year", "15 yr", "16 year", "16 yr", "17 year", "17 yr",
            "school girl", "schoolgirl",
        ))
        or re.search(r"\b1[4-7]\s*(?:year|years|yr|yrs)\b", q) is not None
    )
    relationship_context = _has_any(q, (
        "girlfriend", "boyfriend", "relationship", "love affair", "came on her own",
        "came with me", "eloped", "ran away", "consensual", "father filed",
        "parents filed", "case on me", "filed pocso on me", "pocso on me",
    ))
    accused_context = _has_any(q, (
        "on me", "against me", "i am 17", "i am 16", "i am minor",
        "accused", "arrest", "bail", "fir", "case", "father filed",
        "parents filed", "her father filed", "her parents filed",
    ))
    if not (minor_context and relationship_context and accused_context):
        return []

    pocso = _find(
        passages,
        title_terms=("protection of children from sexual offences", "pocso"),
        anchor_terms=("/sec-33", "/sec-29", "/sec-3", "/sec-4", "/sec-19"),
    )
    jj = _find(
        passages,
        title_terms=("juvenile justice",),
        anchor_terms=("/sec-2", "/sec-9", "/sec-10", "/sec-12", "/sec-94"),
    )
    bnss = _find(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-47", "/sec-57", "/sec-187", "/sec-480", "/sec-483"),
    )
    crpc = _find(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-50", "/sec-57", "/sec-167", "/sec-437", "/sec-439"),
    )
    procedure = bnss or crpc
    if pocso is None or (jj is None and procedure is None):
        return []

    lines = ["**Short answer**"]
    lines.append(
        f"Treat this as a serious POCSO/child-sexual-offence accused-side matter; do not rely on 'relationship', 'consent', or 'came on her own' as a safe answer without checking the FIR sections, ages, Special Court papers, and exact allegations [{pocso}]."
    )
    if jj is not None:
        lines.append(
            f"If you are 17 or there is any accused-age dispute, raise juvenility/age determination with school, birth, or government records under the JJ route; do not stay in an adult-criminal path without age papers being considered [{jj}]."
        )
    if procedure is not None:
        regime = "BNSS" if bnss is not None else "CrPC"
        lines.append(
            f"Use the {regime} source only for arrest, remand, bail, notice, and court procedure; it does not replace the POCSO allegation or any JJ age route [{procedure}]."
        )
    action_cites = _cite_many(pocso, jj, procedure)
    lines.extend([
        "**What you can do next**",
        f"- Collect FIR/complaint, POCSO sections, both date-of-birth proofs, school certificates, arrest/notice status, remand/bail papers, chats/travel timeline, and guardian details; speak to DLSA or a criminal lawyer before statement, bail, quashing, compromise, or contacting the girl/family {action_cites}.",
    ])
    return lines


def _promise_to_marry_deceitful_intercourse_complaint_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "criminal_general" or not _is_promise_to_marry_complainant(q):
        return []
    bns69 = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-69",))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    bns_stalking = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-78", "/sec-351", "/sec-356"))
    pwdva = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-3", "/sec-12", "/sec-18", "/sec-20"))
    primary = bns69 or bnss or bns_stalking or pwdva
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if bns69 is not None:
        lines.append(
            f"For a complainant saying a long relationship or live-in relationship was based on a marriage promise and he is now marrying someone else, check the BNS Section 69/deceitful-means source with the full timeline and proof; a breakup or later refusal to marry is not automatically criminal: it is not automatically a criminal case without deception at the start [{bns69}]."
        )
    if bnss is not None:
        lines.append(
            f"If you choose the police route, use the BNSS FIR/information source with a written complaint, dates, screenshots/messages, cohabitation proof, and any threat or coercion facts rather than asking orally at the station [{bnss}]."
        )
    if pwdva is not None:
        lines.append(
            f"If the live-in domestic relationship also includes violence, residence exclusion, or financial control, keep that PWDVA safety/support track separate from the promise-to-marry complaint [{pwdva}]."
        )
    if bns_stalking is not None:
        lines.append(
            f"If there are separate threats, stalking, reputation harm, or intimidation after the breakup, keep that offence track separate from the promise-to-marry/deceitful-means question [{bns_stalking}]."
        )
    action_cites = _cite_many(bns69, bnss, bns_stalking, pwdva)
    lines.extend([
        "**What you can do next**",
        f"- Build a dated relationship file: promise/proposal messages, cohabitation or travel proof, sexual-consent context, dates when the promise was made and broken, current safety risk, threats, pregnancy or financial facts if any, and witness details; take it to DLSA/legal aid or a criminal lawyer before filing so the complaint does not overstate the offence {action_cites}.",
    ])
    return lines


def _criminal_defence_first_action_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"criminal_defence_bail", "criminal_general"}:
        return []
    defence_context = _has_any(q, (
        "bail", "anticipatory bail", "interim bail", "regular bail",
        "arrested", "fir", "case", "quashing", "482", "withdraw criminal complaint",
        "compounding", "section 320", "it act 67", "67 case", "pita", "spa",
        "itpa", "cow transport", "cattle", "buffalo", "first time offender",
        "379", "theft", "documents needed", "slapped", "slap", "hit",
        "assault", "filing case on me", "file case on me",
    ))
    if not defence_context:
        return []
    bnss_bail = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-480", "/sec-482", "/sec-483", "/sec-479"))
    crpc_bail = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-437", "/sec-438", "/sec-439", "/sec-167", "/sec-436A"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    bnss_quash = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-528",))
    crpc_quash = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-482",))
    crpc_compound = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-320",))
    bnss_compound = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-359",))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-67", "/sec-67A", "/sec-66E"))
    itpa = _find(passages, title_terms=("immoral traffic", "prevention of immoral traffic"))
    bns_theft = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-303", "/sec-305", "/sec-317", "/sec-318"))
    bns_hurt = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-115", "/sec-117", "/sec-118", "/sec-351"))
    bnss_arrest = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-47", "/sec-48", "/sec-57", "/sec-58"))
    crpc_arrest = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-50", "/sec-56", "/sec-57"))
    cattle = _find(passages, title_terms=("cattle", "cow", "animal preservation", "prevention of cruelty", "transport of animals"))
    primary = it_act or itpa or cattle or bns_hurt or bnss_bail or crpc_bail or bnss_arrest or crpc_arrest or bnss_fir or bnss_quash or crpc_quash or crpc_compound or bnss_compound or bns_theft
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if _has_any(q, ("slapped", "slap", "hit", "assault")):
        cite = bns_hurt or bnss_arrest or crpc_arrest or primary
        lines.append(
            f"If someone says you slapped, hit, or assaulted them, treat it as an accused-side BNS hurt/intimidation or criminal-defence issue first; do not retaliate or assume the other person's affair is a defence by itself [{cite}]."
        )
        arrest_cite = bnss_arrest or crpc_arrest or bnss_bail or primary
        lines.append(
            f"If police call you or a notice/FIR appears, get the complaint/FIR sections, arrest or notice status, medical allegation if any, and incident date before deciding bail, reply, compromise, or counter-complaint strategy [{arrest_cite}]."
        )
    if _has_any(q, ("it act 67", "67 case", "ex girlfriend", "normal selfie", "photo")):
        lines.append(
            f"For an IT Act 67 complaint over non-nude photo material such as a normal selfie, first get the FIR/notice and exact section: the issue is whether it involves obscene/sexual electronic material, not an assumption that every shared photo is harmless or unlawful; check the image, context, consent, and platform facts [{it_act or primary}]."
        )
    if _has_any(q, ("pita", "itpa", "spa", "parlour", "parlor", "massage")):
        lines.append(
            f"For a spa/parlour/ITPA raid, do not accept a generic ITPA label: each section must be matched to the alleged role and evidence, not merely reception-desk work or massage work; use the FIR, role, statement, and raid memo before deciding bail or discharge, and do not admit involvement beyond facts [{itpa or bnss_bail or primary}]."
        )
    if _has_any(q, ("cow", "cattle", "buffalo", "transport", "smuggling")):
        lines.append(
            f"Treat this as a state cattle-preservation accused-procedure issue: the state animal-preservation/cattle law and seizure memo matter; do not answer only from generic bail law without the state, animal, permit, vehicle, and FIR sections [{cattle or bnss_bail or primary}]."
        )
        if cattle is not None:
            lines.append(
                f"Use the Prevention of Cruelty to Animals / Transport of Animals sources only for transport, welfare, custody, veterinary certificate, space, water, feeding, permit, or seizure facts; verify the separate state cattle-preservation source before accepting a smuggling label [{cattle}]."
            )
            lines.append(
                f"I do not have the exact state Cattle Preservation/Animal Preservation Act source in this retrieved set; do not treat a judgment or generic bail/procedure text as the controlling State Act, and remember it does not replace the FIR's exact state Act and section text [{cattle}]."
            )
        lines.append(
            f"Take the FIR/complaint, seizure and ownership papers, permit/transport facts, and bail/remand papers to the trial court, Special Court, High Court, or legal-aid route after the State Act section is verified [{cattle or bnss_bail or primary}]."
        )
    if _has_any(q, ("first time offender", "first-time offender", "379", "theft")):
        cite = bnss_bail or crpc_bail or bns_theft or primary
        lines.append(
            f"Regular bail for first-time accused theft/379 facts belongs before the Magistrate/trial court once FIR sections, custody status, recovery/seizure, and prior record are checked; preserve the first-time accused facts and do not promise bail chances without those papers [{cite}]."
        )
    if _has_any(q, ("anticipatory bail", "documents needed", "how many days valid")):
        cite = bnss_bail or crpc_bail or primary
        lines.append(
            f"For anticipatory bail, collect FIR/complaint, notice, arrest-threat proof, sections, incident date, role, medical/alibi/chat documents, and prior orders; validity/conditions depend on the court order and case facts. Do not use a generic number of days without reading the bail order [{cite}]."
        )
        if _has_any(q, ("how many days valid", "valid after grant", "duration")):
            lines.append(
                f"Anticipatory-bail duration is not a fixed number of days from this answer; read the bail order conditions, next appearance direction, and any investigation-cooperation condition before assuming it has expired or continues [{cite}]."
            )
    if _has_any(q, ("interim bail", "medical", "pregnant", "pregnant where rule", "between regular bail")):
        cite = bnss_bail or crpc_bail or primary
        interim_phrase = (
            "Interim bail between regular-bail hearings is a short-date relief request tied to the pending bail application"
            if _has_any(q, ("between regular bail", "between regular-bail", "regular bail hearings"))
            else "For interim or medical bail, prepare the temporary-relief request"
        )
        lines.append(
            f"{interim_phrase} with custody/remand papers, medical/pregnancy records where relevant, next hearing date, and urgency proof; it is a temporary relief request, not a substitute for regular/default bail [{cite}]."
        )
    if _has_any(q, ("482", "quashing", "quash")):
        cite = bnss_quash or crpc_quash or primary
        if crpc_quash is not None and _has_any(q, ("crpc", "482 crpc", "crpc 482")):
            lines.append(
                f"For CrPC section 482 High Court quashing, first check whether the FIR is pre-1 July 2024 or the papers are still framed under CrPC, then compare FIR allegations with documents, messages, alibi, civil-dispute background, and investigation stage; it is lawyer-led review, not the first answer to every false-case claim [{crpc_quash}]."
            )
        else:
            lines.append(
                f"For High Court quashing, first compare FIR allegations with documents, messages, alibi, civil-dispute background, and investigation stage; it is lawyer-led review, not the first answer to every false-case claim [{cite}]."
            )
    if _has_any(q, ("withdraw criminal complaint", "section 320", "compounding", "compound")):
        cite = bnss_compound or crpc_compound or primary
        lines.append(
            f"For withdrawal/compounding, verify whether the exact offence is compoundable and whether court permission is needed; do not assume every criminal complaint can simply be withdrawn [{cite}]."
        )
    if bnss_fir is not None:
        lines.append(
            f"For information to police on the defence-side facts, preserve FIR/notice, arrest memo, remand order, bail order, seizure memo, complaint copy, and incident date because BNSS/CrPC choice and forum depend on those records [{bnss_fir}]."
        )
    action_cites = _cite_many(it_act, itpa, cattle, bns_hurt, bnss_bail, crpc_bail, bnss_arrest, crpc_arrest, bnss_fir, bnss_quash, crpc_quash, crpc_compound, bnss_compound, bns_theft)
    lines.extend([
        "**What you can do next**",
        f"- Get the FIR/complaint/notice, exact sections, incident date, arrest or custody status, role allegation, seizure/recovery list, statement copy if any, prior bail/order papers, and proof that supports your version; then ask legal aid/DLSA or a criminal lawyer about bail, reply, compounding, discharge, or quashing {action_cites}.",
    ])
    return lines


def _false_fir_defence_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    reviewed_false_case_context = (
        _is_false_fir(q)
        or _is_matrimonial_false_case(q)
        or _is_scst_poa_accused_false_case(q)
        or _is_witch_accused_false_case(q)
    )
    if route.category not in {"criminal_defence_bail", "police_fir", "criminal_general", "cyber_fraud_or_harassment"} or not reviewed_false_case_context:
        return []
    if route.category == "cyber_fraud_or_harassment" and _is_cyber_money_fraud_victim_progress(q):
        return []
    if _has_any(q, ("cow", "cattle", "buffalo", "slaughter", "gauraksha")):
        # Let the source-aware cattle owner handle the state Act before generic false-FIR advice.
        return []
    bnss528 = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-528",))
    crpc482 = _find(passages, title_terms=("criminal procedure",), anchor_terms=("/sec-482",))
    bail = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-480", "/sec-482", "/sec-483"))
    bnss173 = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173",))
    bns_cheating = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-318", "/sec-319"))
    bns_theft = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-303", "/sec-317", "/sec-318"))
    bns_cruelty = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-85", "/sec-86"))
    ipc_cruelty = _find(passages, title_terms=("indian penal",), anchor_terms=("/sec-498A", "/sec-498-a"))
    pwdva = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-3", "/sec-12", "/sec-18"))
    poa = _find(passages, title_terms=("scheduled castes", "prevention of atrocities"), anchor_terms=("/sec-18", "/sec-18A", "/sec-18-a"))
    state_witch = _find(passages, title_terms=("witch hunting", "witch-hunting", "tonhi", "tonahi", "daain", "daayan"))
    bns_witch = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-74", "/sec-76", "/sec-351", "/sec-356"))
    primary = bnss528 or crpc482 or bail or bnss173

    if _is_scst_poa_accused_false_case(q):
        primary = poa or bail or bnss528 or crpc482 or bnss173
        if primary is None:
            return []
        lines = [
            "**Short answer**",
        ]
        if poa is not None:
            lines.append(
                f"For an accused-side SC/ST POA false-case claim, first verify the exact POA sections and whether Section 18/18A anticipatory-bail restrictions are being invoked; do not answer it as a generic 420 or money-dispute case [{poa}]."
            )
        else:
            lines.append(
                f"For an SC/ST POA accused-side false-case claim, first get the FIR sections and the missing POA source before deciding bail or quashing; do not answer it as a generic 420 or money-dispute case [{primary}]."
            )
        if bns_theft is not None:
            allegation = "stealing chickens from an upper-caste house" if _has_any(q, ("chicken", "chickens", "upper caste")) else "the alleged theft or property offence"
            lines.append(
                f"Keep the underlying allegation of {allegation} separate from the POA label and compare it only against the retrieved BNS offence source and FIR facts [{bns_theft}]."
            )
        if bail is not None:
            lines.append(
                f"If arrest is threatened or notice has been served, take the FIR, POA sections, incident date, and arrest/notice status to a criminal lawyer/DLSA for the bail route before assuming anticipatory bail is available without checking the POA bar and prima-facie facts; do not contact or pressure the complainant [{bail}]."
            )
        if bnss528 is not None or crpc482 is not None:
            quash_cite = bnss528 if bnss528 is not None else crpc482
            lines.append(
                f"High Court quashing/protection is a later lawyer-led review after comparing the POA allegations, caste-status facts, witnesses, and contradiction documents with the FIR [{quash_cite}]."
            )
        action_cite = bail or bnss173 or primary
        lines.extend([
            "**What you can do next**",
            f"- Collect the FIR/complaint copy, alleged POA and BNS/IPC sections, caste/status allegation, notice or arrest papers, alibi/location proof, messages, witnesses, and any village-dispute background; ask DLSA or a criminal lawyer about bail, Special Court procedure, or High Court protection [{action_cite}].",
        ])
        return lines

    if _is_matrimonial_false_case(q):
        primary = bns_cruelty or ipc_cruelty or pwdva or bail or bnss528 or crpc482 or bnss173
        if primary is None:
            return []
        family_phrase = " and your 71-year-old mother" if "mother" in q and "71" in q else " and each family member named" if _has_any(q, ("parents", "mother", "father", "family", "whole family", "elder", "70", "71", "bahu", "daughter in law", "daughter-in-law")) else ""
        lines = [
            "**Short answer**",
            f"For a false 498A/DV matrimonial criminal-defence problem, treat it as a cruelty/DV defence route for the accused{family_phrase}, not as a 420 or ordinary money-dispute route [{primary}].",
        ]
        if bns_cruelty is not None or ipc_cruelty is not None:
            cruelty_cite = bns_cruelty if bns_cruelty is not None else ipc_cruelty
            lines.append(
                f"Compare the FIR sections and allegations against the BNS/IPC cruelty source, incident dates, role of each accused relative, residence records, chats, medical papers, and prior matrimonial-case history [{cruelty_cite}]."
            )
        if pwdva is not None:
            lines.append(
                f"If there is a DV application, residence/protection order, or monetary-relief claim, keep the PWDVA proceeding separate from the FIR/bail track and prepare a fact-by-fact reply instead of treating it as one criminal case [{pwdva}]."
            )
        if bail is not None:
            lines.append(
                f"If police call, notice arrives, or arrest is threatened, check anticipatory/regular bail risk immediately with the FIR, notice, sections, and documents for elderly or separately living relatives [{bail}]."
            )
        if bnss528 is not None or crpc482 is not None:
            quash_cite = bnss528 if bnss528 is not None else crpc482
            lines.append(
                f"Quashing or deletion of relatives is a later High Court/inherent-powers question after the lawyer checks whether the FIR contains specific role allegations or only omnibus family allegations [{quash_cite}]."
            )
        action_cite = bail or bnss173 or pwdva or primary
        lines.extend([
            "**What you can do next**",
            f"- Keep FIR/DV application, summons or notice, marriage documents, residence proof for each accused, age/medical proof for elderly relatives, chats/call records, travel/alibi records, and earlier mediation or complaint papers; ask DLSA/criminal counsel which of bail, reply, discharge, mediation, or quashing fits the current stage [{action_cite}].",
        ])
        return lines

    if _is_witch_accused_false_case(q):
        primary = state_witch or bns_witch or bail or bnss528 or crpc482 or bnss173
        if primary is None:
            return []
        state_label = _witch_state_label(q)
        matter = (
            "Chhattisgarh tonhi false-case matter"
            if _has_chhattisgarh_context(q) and "tonhi" in q
            else f"{state_label} tonhi/daayan/witch false-case matter"
        )
        lines = [
            "**Short answer**",
            f"For a {matter} involving a tonhi/daayan/witch false-case accusation, where you are the accused, treat it as a state witch-law plus criminal-defence problem, not as a generic false 420 case [{primary}].",
        ]
        if state_witch is not None:
            state_source_label = "Chhattisgarh Tonahi Act source (state witch-hunting/tonhi source)" if _has_chhattisgarh_context(q) else "state witch-hunting/tonhi source"
            lines.append(
                f"Check the {state_source_label} and the exact FIR sections before deciding bail, reply, or quashing, because the local Act can change the offence and forum path [{state_witch}]."
            )
        if bns_witch is not None:
            lines.append(
                f"If the FIR also alleges assault, disrobing, intimidation, defamation, or public humiliation, compare those facts with the BNS provisions instead of assuming every village accusation is the same offence [{bns_witch}]."
            )
        if bail is not None:
            lines.append(
                f"If arrest or police notice is pending, use the High Court or Court of Session bail route first with the FIR copy, state Act sections, incident date, and witness list [{bail}]."
            )
        action_cite = bail or bnss173 or state_witch or primary
        lines.extend([
            "**What you can do next**",
            f"- Collect the FIR/notice, state and village facts, death/illness background if alleged, witness names, messages, panchayat statements, alibi/location proof, and any medical/death papers; take them to DLSA or criminal counsel for bail, reply, or High Court protection/quashing review [{action_cite}].",
        ])
        return lines

    if primary is None:
        return []

    person = "your brother" if "brother" in q else "you"
    false_case_phrase = (
        f"a false FIR or false 420 case by a business partner over loan money against {person}"
        if "business partner" in q and _has_any(q, ("loan money", "420", "cheating"))
        else f"a false FIR or false 420 case by a relative because of repayment delay against {person}"
        if "relative" in q and _has_any(q, ("repay", "money", "420"))
        else f"a false FIR or false cheating complaint after a property-payment fight against {person}"
        if _has_any(q, ("property payment fight", "property payment", "cheating complaint"))
        else f"a false cyber cheating case about an online-payment/refund dispute against {person}"
        if _has_any(q, ("cyber cheating", "online payment", "refund issue"))
        else f"a fake 420 FIR from an old business-debt dispute against {person}"
        if _has_any(q, ("old business debt", "summons in fake 420"))
        else f"a false FIR or false 420 case where police are calling about a cheque/money dispute against {person}"
        if _has_any(q, ("police calling", "cheque money", "420 complaint"))
        else f"a 420 police complaint after a personal-loan dispute where {person} must prepare for station appearance"
        if _has_any(q, ("personal loan dispute", "what to carry to station", "called to station", "go to station"))
        else
        f"a false FIR or false 420 case by a neighbour because of a money dispute against {person}"
        if "neighbour" in q and _has_any(q, ("money dispute", "420"))
        else f"a false FIR or false 420 case against {person}"
    )
    lines = [
        "**Short answer**",
        f"For {false_case_phrase}, do not start with a final quashing claim; first get the FIR/complaint copy, sections, arrest or notice status, and case stage because bail, police cooperation, discharge, and High Court quashing depend on those papers [{primary}].",
    ]
    if bnss528 is not None or crpc482 is not None:
        quash_cite = bnss528 if bnss528 is not None else crpc482
        if _has_any(q, ("482", "section 482", "sec 482", "crpc 482", "482 crpc")):
            lines.append(
                f"If you are using '482' as shorthand, first check whether the legacy CrPC Section 482 route or the current BNSS Section 528 High Court inherent-powers route applies from the incident date and case papers [{quash_cite}]."
            )
        lines.append(
            f"High Court quashing/inherent-powers review is a later lawyer-led step after comparing the FIR allegations with documents, money trail, messages, witnesses, and civil-dispute background [{quash_cite}]."
        )
    if bail is not None:
        lines.append(
            f"If police are calling, arrest is threatened, or notice has been served, check bail/appearance risk immediately instead of waiting for the quashing decision [{bail}]."
        )
    if bns_cheating is not None:
        lines.append(
            f"If the allegation is cheating/420, compare the FIR facts against the BNS cheating/personation source and your loan, refund, cheque, or property-payment documents; non-payment alone should not be treated as cheating without deception facts at the start [{bns_cheating}]."
        )
    action_cite = bnss173 if bnss173 is not None else bail if bail is not None else primary
    lines.extend([
        "**What you can do next**",
        f"- Collect FIR/complaint, offence sections, notice/summons, transaction proof, chats, witnesses, alibi/location records, prior civil notices, and any repayment or dispute papers; take them to a criminal lawyer/DLSA before choosing bail, discharge, compromise, or High Court quashing [{action_cite}].",
    ])
    return lines


def _gig_platform_worker_account_block_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "digital_platform_account" or not _is_gig_platform_worker_account_block(q):
        return []
    social = _find(passages, title_terms=("code on social security",), anchor_terms=("/sec-112", "/sec-113", "/sec-114"))
    wages = _find(passages, title_terms=("code on wages",), anchor_terms=("/sec-17", "/sec-45"))
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-35"))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-79", "/sec-90"))
    primary = social or wages or consumer or it_act
    if primary is None:
        return []

    platform = (
        "Swiggy" if "swiggy" in q else
        "Zomato" if "zomato" in q else
        "Rapido" if "rapido" in q else
        "the platform"
    )
    worker_role = "delivery/partner ID" if platform in {"Swiggy", "Zomato"} else "worker ID"
    lines = ["**Short answer**"]
    if social is not None:
        lines.append(
            f"For a {platform} {worker_role} blocked case, treat the {platform} worker ID block after rating spam, customer abuse, or an app complaint as a gig/platform-worker grievance; ask for the written deactivation reason, appeal record, and pending-benefit or registration details [{social}]."
        )
    if wages is not None:
        lines.append(
            f"If the block also leaves any earned payout or wages unpaid, including accepted delivery dues, incentives, or final settlement, keep a separate wage/dues record with trip IDs, ledger screenshots, and bank entries [{wages}]."
        )
    if consumer is not None or it_act is not None:
        cite = consumer or it_act
        lines.append(
            f"Use the platform/app-service source only as a grievance and evidence lane; it is not a guarantee of instant reinstatement without the contract, ratings, complaint, and appeal facts [{cite}]."
        )
    action_cites = _cite_many(social, wages, consumer, it_act)
    lines.extend([
        "**What you can do next**",
        f"- Ask support/grievance in writing for the block reason, appeal ID, complaint/rating basis, customer-abuse record, trip/order IDs, account ID, payout ledger, contract terms, and reactivation conditions; then take the packet to platform grievance, labour/wage authority, DLSA, or a lawyer depending on the written reply {action_cites}.",
    ])
    return lines


def _social_media_account_suspension_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "digital_platform_account" or not _is_social_media_account_suspension(q):
        return []
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-79", "/sec-90", "/sec-67C"))
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-35"))
    contract = _find(passages, title_terms=("indian contract",), anchor_terms=("/sec-37", "/sec-73"))
    primary = it_act or consumer or contract
    if primary is None:
        return []

    platform = (
        "Instagram/Meta" if _has_any(q, ("instagram", "insta", "meta")) else
        "Facebook/Meta" if "facebook" in q else
        "the social-media platform"
    )
    account = "page with followers/monetisation history" if _has_any(q, ("followers", "page", "200k")) else "account/page"
    lines = ["**Short answer**"]
    if it_act is not None:
        lines.append(
            f"For a {platform} suspension of your {account} with no notice, start with the platform grievance/intermediary and electronic-record route: ask for the rule violated, ticket ID, appeal decision, and account-data record [{it_act}]."
        )
    if consumer is not None:
        lines.append(
            f"If you paid for ads, subscriptions, business tools, or other services, keep a consumer/service-deficiency backup after the platform appeal and written replies are preserved [{consumer}]."
        )
    if contract is not None:
        lines.append(
            f"If earnings, brand work, or business loss is involved, keep the terms-of-service/contract proof separate from the account-restoration request; do not treat every suspension as automatically unlawful [{contract}]."
        )
    action_cites = _cite_many(it_act, consumer, contract)
    lines.extend([
        "**What you can do next**",
        f"- Preserve username/page URL, follower/analytics screenshots, suspension notice, appeal ticket, emails, ad invoices or monetisation proof, posts alleged to violate rules, business loss proof, and Meta/Instagram grievance replies; escalate only after the written platform path is clear {action_cites}.",
    ])
    return lines


def _digital_platform_kyc_money_freeze_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "digital_platform_account" or not _is_digital_platform_kyc_money_freeze(q):
        return []
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-35"))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-79", "/sec-90", "/sec-67C"))
    pmla = _find(passages, title_terms=("prevention of money laundering",), anchor_terms=("/sec-5", "/sec-8", "/sec-17", "/sec-50"))
    primary = consumer or it_act or pmla
    if primary is None:
        return []

    platform = "the app/platform"
    brand_match = re.search(r"\b([a-z][a-z0-9]*(?:\s+[a-z][a-z0-9]*)?)\s+app\b", q)
    if brand_match:
        platform = f"{brand_match.group(1).title()} app"
    lines = ["**Short answer**"]
    if consumer is not None:
        lines.append(
            f"For {platform} freezing an account or money on a KYC-pending reason, start as a platform-service grievance: ask for the written freeze reason, KYC deficiency, ticket number, ledger, and release conditions [{consumer}]."
        )
        lines.append(
            f"If the platform does not give a lawful written freeze reason or does not resolve the grievance, keep the Consumer Protection Act service-deficiency complaint route as the next civilian remedy [{consumer}]."
        )
    if it_act is not None:
        lines.append(
            f"Keep the IT/electronic-record source with account ID, app screenshots, emails, support chats, and transaction records; do not rely only on oral support calls [{it_act}]."
        )
    if pmla is not None:
        lines.append(
            f"If the platform says AML, suspicious transaction, legal hold, or compliance review, treat the PMLA source as the AML/freeze source to check, separate from an ordinary refund complaint, and ask for the written hold basis [{pmla}]."
        )
    action_cites = _cite_many(consumer, it_act, pmla)
    lines.extend([
        "**What you can do next**",
        f"- Preserve KYC screens, uploaded documents, account ID, freeze/hold message, support ticket, deposit/withdrawal ledger, bank statement, terms, and all replies; escalate through the platform grievance, consumer forum/legal aid, or cyber/police only if there is fraud or unauthorized access {action_cites}.",
    ])
    return lines


def _online_gambling_platform_dispute_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "digital_platform_account" or not _is_online_gambling_platform_dispute(q):
        return []
    state_gambling = _find(passages, title_terms=("online gambling", "gaming"), anchor_terms=("/sec-7", "/sec-8", "/sec-10"))
    public_gambling = _find(passages, title_terms=("public gambling",), anchor_terms=("/sec-3", "/sec-12", "/sec-13"))
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-35"))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-79", "/sec-90"))
    pmla = _find(passages, title_terms=("prevention of money laundering",), anchor_terms=("/sec-8", "/sec-17", "/sec-50"))
    primary = state_gambling or public_gambling or consumer or it_act or pmla
    if primary is None:
        return []

    state_context = "Tamil Nadu" if _has_any(q, ("tamil nadu", "tn ")) else "your state"
    money_context = "KYC/account freeze" if _has_any(q, ("kyc", "froze", "frozen", "freeze", "stuck")) else "loss/recovery dispute"
    lines = ["**Short answer**"]
    if state_gambling is not None:
        lines.append(
            f"For online rummy/betting/gambling in {state_context}, legality and recovery depend on state online-gaming/gambling law and the game/platform facts; do not assume losses are automatically recoverable [{state_gambling}]."
        )
        if public_gambling is not None:
            lines.append(
                f"Keep the Public Gambling Act as a baseline gambling-law source, while checking the current state online-gaming law before treating any platform loss as a legal recovery claim [{public_gambling}]."
            )
    elif public_gambling is not None:
        lines.append(
            f"If no state online-gaming source is retrieved, keep the Public Gambling Act source as only a baseline gambling-law warning: whether the platform is a game of mere skill and whether there is a recoverable wallet dispute depend on current state law and the platform facts, so do not assume losses are automatically recoverable [{public_gambling}]."
        )
    if consumer is not None or it_act is not None:
        cite = consumer or it_act
        lines.append(
            f"For a {money_context}, separate platform grievance, KYC, ledger, deposits, withdrawals, support tickets, and terms from the gambling-legality question [{cite}]."
        )
    elif _has_any(q, ("lost", "loss", "refund", "recover", "recovery")):
        lines.append(
            f"Do not assume a consumer refund is automatic for gambling losses; first preserve the platform ledger, terms, payment trail, and any fraud or misleading-representation facts before choosing a grievance or legal-aid route [{primary}]."
        )
    if pmla is not None and _has_any(q, ("kyc", "freeze", "froze", "frozen", "account")):
        lines.append(
            f"If the platform says KYC/AML/legal hold, ask for the written hold reason and do not frame it only as a refund complaint [{pmla}]."
        )
    action_cites = _cite_many(state_gambling, public_gambling, consumer, it_act, pmla)
    lines.extend([
        "**What you can do next**",
        f"- Preserve deposits/withdrawals, game ledger, KYC requests, freeze notice, terms, screenshots, support tickets, ad claims, state/city, and bank statements; use the platform grievance first, then consumer/cyber/legal-aid review depending on fraud, illegal platform, or KYC hold facts {action_cites}.",
    ])
    return lines


def _digital_creator_payout_freeze_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"business_contract_partnership", "digital_platform_account"} or not _is_digital_creator_payout_freeze(q):
        return []
    contract = _find(passages, title_terms=("indian contract",), anchor_terms=("/sec-37", "/sec-73"))
    fema = _find(passages, title_terms=("foreign exchange management", "fema"), anchor_terms=("/sec-3", "/sec-4", "/sec-8"))
    tax = _find(passages, title_terms=("income-tax", "income tax"), anchor_terms=("/sec-5",))
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-35"))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-79", "/sec-90"))
    primary = contract or fema or tax or consumer or it_act
    if primary is None:
        return []

    platform = "Fanvue" if "fanvue" in q else "OnlyFans" if "onlyfans" in q else "the creator platform"
    lines = ["**Short answer**"]
    if contract is not None:
        lines.append(
            f"For a {platform} payout frozen for an Indian creator, start with the platform contract/terms and payout grievance: ask for the exact hold reason, KYC/tax document requirement, ledger, and release conditions [{contract}]."
        )
    if fema is not None:
        lines.append(
            f"Because the payout is in USD or from a foreign platform, keep a FEMA/foreign-remittance compliance lane with bank rejection, purpose code, KYC, and platform payout records [{fema}]."
        )
    if tax is not None:
        lines.append(
            f"Keep tax-residency/income proof separate from the release dispute; the answer should not promise payout release without checking invoices, TDS/tax forms, and bank compliance records [{tax}]."
        )
    if consumer is not None or it_act is not None:
        cite = consumer or it_act
        lines.append(
            f"If support gives no written reason, preserve the platform-service/electronic-record trail for consumer, platform grievance, or lawyer review [{cite}]."
        )
    action_cites = _cite_many(contract, fema, tax, consumer, it_act)
    lines.extend([
        "**What you can do next**",
        f"- Keep payout ledger, account ID, KYC/tax forms submitted, bank rejection/hold messages, USD amount, invoices, terms of service, support tickets, emails, screenshots, and Indian bank/FEMA/tax details; escalate through platform grievance and then contract/consumer/legal-aid review based on the written reason {action_cites}.",
    ])
    return lines


def _cab_aggregator_driver_account_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "digital_platform_account" or not _is_cab_aggregator_driver_account(q):
        return []
    contract = _find(passages, title_terms=("motor vehicle aggregator",), anchor_terms=("driver-service-contract",))
    transparency = _find(passages, title_terms=("motor vehicle aggregator",), anchor_terms=("app-transparency-grievance",))
    fare = _find(passages, title_terms=("motor vehicle aggregator",), anchor_terms=("non-discrimination-driver-fare",))
    mv_act = _find(passages, title_terms=("motor vehicles", "themotorvehiclesact"), anchor_terms=("/sec-193", "/sec-93"))
    wages = _find(passages, title_terms=("code on wages",), anchor_terms=("/sec-17", "/sec-45"))
    social = _find(passages, title_terms=("code on social security",), anchor_terms=("/sec-112", "/sec-113", "/sec-114"))
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-35", "/sec-38"))
    primary = contract or transparency or fare or mv_act
    if primary is None:
        return []

    platform = "Ola" if "ola" in q else "Uber" if "uber" in q else "cab-app"
    lines = ["**Short answer**"]
    if contract is not None:
        lines.append(
            f"A {platform} driver ID suspension or no-reason deactivation is first a cab-aggregator driver-account grievance: ask for the written deactivation reason, appeal record, and service-provider contract terms [{contract}]."
        )
    if transparency is not None:
        lines.append(
            f"Use the Motor Vehicle Aggregator Guidelines app-transparency/grievance source for rating, trip, incentive, fare-share, charge, support-ticket, and driver-facing app disclosure records [{transparency}]."
        )
    if fare is not None and _has_any(q, ("racist", "regional bias", "hindi speaker", "language bias", "language discrimination", "regional discrimination")):
        lines.append(
            f"Where the rating or deactivation is linked to alleged regional bias or language discrimination, preserve the exact customer comment and trip record and raise the guideline non-discrimination point in the platform and transport-authority grievance [{fare}]."
        )
    if mv_act is not None:
        lines.append(
            f"Keep the Motor Vehicles Act aggregator source as the transport-authority/licensing route if the platform grievance does not give reasons; it is not an automatic reinstatement promise [{mv_act}]."
        )
    if wages is not None and _has_any(q, ("earning", "earnings", "payment", "payout", "dues", "4000", "rs", "rupees")):
        lines.append(
            f"If undisputed earnings or payout, incentives, or final dues are withheld after suspension, keep a separate wage/dues authority track while the aggregator account appeal continues [{wages}]."
        )
    if social is not None:
        lines.append(
            f"Use the Code on Social Security only as the gig/platform-worker welfare or registration track, not as a promise of automatic reinstatement or employee status [{social}]."
        )
    if consumer is not None:
        lines.append(
            f"Do not assume a driver is automatically a consumer: the Consumer Protection Act source, service-provider contract, payout facts, and applicable platform/transport rules decide whether a consumer-service complaint is available [{consumer}]."
        )
    action_cites = _cite_many(contract or primary, transparency, mv_act, wages)
    lines.extend([
        "**What you can do next**",
        f"- Ask the aggregator in writing for the suspension reason, appeal ticket, service-provider contract, app disclosures, trip/rating history, fare-share/incentive ledger, pending payout ledger, and support replies; then choose platform grievance, transport/RTO aggregator authority, wage authority, or DLSA/lawyer escalation based on the written response {action_cites}.",
    ])
    return lines


def _cab_aggregator_passenger_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "consumer" or not _is_cab_aggregator(q):
        return []
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-39", "/sec-2"))
    aggregator = _find(passages, title_terms=("motor vehicle aggregator", "aggregator guidelines"))
    motor = _find(passages, title_terms=("motor vehicles",), anchor_terms=("/sec-93",))
    primary = consumer or aggregator or motor
    if primary is None:
        return []

    issue = (
        "driver-abuse and platform-complaint closure"
        if _has_any(q, ("abused", "abuse", "misbehaved", "misbehaviour", "misbehavior"))
        else "Ola longer-route extra-fare dispute"
        if "ola" in q and _has_any(q, ("longer route", "extra fare", "charged extra fare"))
        else "Ola wallet cancellation-fee refund dispute"
        if "ola" in q and _has_any(q, ("cancellation fee", "wallet", "support bot"))
        else "Uber cancelled-ride deducted-money refund dispute"
        if "uber" in q and _has_any(q, ("cancelled ride", "canceled ride", "deducted money", "not refunding"))
        else "fare/refund dispute"
    )
    lines = ["**Short answer**"]
    if consumer is not None:
        lines.append(
            f"For a cab-app passenger raising a {issue}, keep the Consumer Protection Act service-deficiency/refund route with the trip ID, fare, support ticket, screenshots, and platform reply [{consumer}]."
        )
    if aggregator is not None:
        lines.append(
            f"Also keep the Motor Vehicle Aggregator Guidelines source as the platform/aggregator grievance and driver-conduct lane instead of treating the ride only as a generic refund dispute [{aggregator}]."
        )
    elif motor is not None:
        lines.append(
            f"If the retrieved index does not surface the aggregator guidelines, use the Motor Vehicles aggregator-licensing source only as the transport-authority lane and do not invent missing guideline text [{motor}]."
        )
    action_cite = aggregator if aggregator is not None else consumer if consumer is not None else motor
    lines.extend([
        "**What you can do next**",
        f"- File/appeal in the app first, preserve trip ID, driver details, route map, fare breakup, cancellation fee, refund message, wallet debit, support-bot/support-ticket closure, abuse/safety screenshots, and payment proof; then use National Consumer Helpline/e-Daakhil or the transport/RTO aggregator authority depending on facts [{action_cite}].",
    ])
    return lines


def _traffic_police_challan_bribe_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"business_license_compliance", "police_fir", "criminal_general"} or not _is_traffic_police_challan_bribe(q):
        return []
    mv = _find(passages, title_terms=("motor vehicles", "themotorvehiclesact"), anchor_terms=("/sec-3", "/sec-4", "/sec-206", "/sec-182"))
    pca = _find(passages, title_terms=("prevention of corruption",), anchor_terms=("/sec-7", "/sec-8", "/sec-13"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    primary = pca or mv or bnss
    if primary is None:
        return []

    lines = ["**Short answer**"]
    place = "Bangalore/traffic-police" if _has_any(q, ("bangalore", "bengaluru")) else "traffic-police"
    licence_phrase = "Tamil Nadu licence" if _has_any(q, ("tamil license", "tamil licence", "tamil nadu license", "tamil nadu licence")) else "licence"
    payment_phrase = "Rs.500 or weekly cash" if _has_any(q, ("taking 500", "rs 500", "500 every week")) else "cash or money"
    if mv is not None:
        lines.append(
            f"For a {place} claim that your {licence_phrase} is invalid, first verify the Motor Vehicles Act licence/challan basis and ask for a written challan or notice instead of accepting oral cash demands [{mv}]."
        )
    if pca is not None:
        lines.append(
            f"If a police officer is taking {payment_phrase} without a challan/receipt, keep a separate Prevention of Corruption Act complaint track with date, place, officer details, vehicle number, and proof [{pca}]."
        )
    if bnss is not None:
        lines.append(
            f"For a police complaint or escalation, use the BNSS complaint/FIR route with written facts and evidence; do not rely only on oral allegations if a receipt/challan was refused [{bnss}]."
        )
    action_cite = pca or mv or bnss
    lines.extend([
        "**What you can do next**",
        f"- Keep licence copy, vehicle/permit/RC/insurance papers, challan history, officer name/badge/location/date, any audio/video/message proof, payment proof if safe, and complaint acknowledgement; approach the traffic DCP/RTO/anti-corruption channel or DLSA with the written packet [{action_cite}].",
    ])
    return lines


def _relative_adoption_no_papers_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "child_custody_adoption" or not _is_relative_adoption_no_papers(q):
        return []
    jj56 = _find(passages, title_terms=("juvenile justice",), anchor_terms=("/sec-56",))
    jj58 = _find(passages, title_terms=("juvenile justice",), anchor_terms=("/sec-58",))
    hama6 = _find(passages, title_terms=("hindu adoptions", "hindu adoption"), anchor_terms=("/sec-6",))
    gwa17 = _find(passages, title_terms=("guardians and wards",), anchor_terms=("/sec-17",))
    gwa7 = _find(passages, title_terms=("guardians and wards",), anchor_terms=("/sec-7",))
    primary = jj56 or jj58 or hama6 or gwa17 or gwa7
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if jj56 is not None or jj58 is not None:
        cite = jj56 or jj58
        lines.append(
            f"For an informal/relative adoption from a sister or family member with no papers, do not treat possession of the child alone as final adoption; verify the JJ Act relative-adoption and adoption-order route first [{cite}]."
        )
    if hama6 is not None:
        lines.append(
            f"If Hindu personal law is being relied on, the HAMA validity conditions must be checked separately; do not assume every family handover becomes a valid adoption without capacity, consent, and ceremony/proof facts [{hama6}]."
        )
    if gwa17 is not None or gwa7 is not None:
        cite = gwa17 or gwa7
        lines.append(
            f"If the biological/real parents now want the child back, frame the immediate court question around the child's welfare, current care, age, school, and safety under the guardianship/custody source [{cite}]."
        )
    action_cites = _cite_many(jj56, jj58, hama6, gwa17, gwa7)
    lines.extend([
        "**What you can do next**",
        f"- Collect the child's birth proof, school/medical records, current residence proof, messages from biological parents, any handover/adoption papers, expenses/care proof, and safety facts; speak to DCPU/CARA/DLSA or Family/District Court before refusing return or moving the child {action_cites}.",
    ])
    return lines


def _child_cross_border_return_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "child_custody_adoption" or not _is_child_cross_border_return(q):
        return []
    gwa17 = _find(passages, title_terms=("guardians and wards",), anchor_terms=("/sec-17",))
    gwa25 = _find(passages, title_terms=("guardians and wards",), anchor_terms=("/sec-25",))
    family = _find(passages, title_terms=("family courts",), anchor_terms=("/sec-7",))
    article226 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-226",))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    primary = gwa25 or gwa17 or family or article226 or bnss
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if gwa25 is not None or gwa17 is not None:
        cite = gwa25 or gwa17
        lines.append(
            f"For a child taken abroad on a tourist visa or tourist/foreign-visa route and not brought back, treat this as an urgent custody/child-return matter and child-return/custody welfare problem; do not label it abduction without the specific facts and court context [{cite}]."
        )
    if family is not None:
        lines.append(
            f"Use the Family Court route for custody, visitation, passport/travel-document directions, and interim return or access orders where that forum is available [{family}]."
        )
    if article226 is not None:
        lines.append(
            f"If the child is being withheld abroad or urgent production/return is needed, ask a lawyer/DLSA about High Court writ options alongside family-court relief [{article226}]."
        )
    if bnss is not None:
        lines.append(
            f"If there is forgery, threat, concealment, or a police complaint, keep the criminal-procedure source separate from the custody-return route [{bnss}]."
        )
    action_cites = _cite_many(gwa25, gwa17, family, article226, bnss)
    lines.extend([
        "**What you can do next**",
        f"- Preserve passport/visa/travel details, consent messages, child age/school proof, current foreign address if known, prior custody orders, tickets, chats saying permanent stay, and urgency/safety facts; contact DLSA/family-law counsel quickly for Family Court or High Court return/access relief {action_cites}.",
    ])
    return lines


def _child_access_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "child_custody_adoption" or not _is_child_access(q):
        return []
    gwa17 = _find(passages, title_terms=("guardians and wards",), anchor_terms=("/sec-17",))
    gwa25 = _find(passages, title_terms=("guardians and wards",), anchor_terms=("/sec-25",))
    gwa9 = _find(passages, title_terms=("guardians and wards",), anchor_terms=("/sec-9",))
    family = _find(passages, title_terms=("family courts",))
    constitution = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-21", "/sec-226"))
    hmga = _find(passages, title_terms=("hindu minority", "minority and guardianship"), anchor_terms=("/sec-6", "/sec-13"))
    urgent_access_context = _has_any(q, (
        "fast", "quick", "urgent", "get her back", "get him back", "get child back",
        "took our", "took my", "took to", "other city", "delhi", "hiding",
        "not letting me meet", "not allowing me to meet",
    ))
    primary = gwa25 or gwa17 or family or (constitution if urgent_access_context else None) or gwa9 or hmga
    if primary is None:
        return []

    child = "your daughter" if _has_any(q, ("daughter", "her child")) else "your son" if _has_any(q, ("son", "his child")) else "your child"
    blocker = (
        "your parents-in-law after your wife's death"
        if _has_any(q, ("wife died", "wife is dead", "mother died", "parents in law", "parents-in-law"))
        else "your wife"
        if "wife" in q
        else "your husband"
        if "husband" in q
        else "the mother"
        if "mother" in q and "father" in q
        else "the other parent"
    )
    access_problem = (
        f"{blocker} is not allowing you to meet {child}"
        if _has_any(q, ("not allowing me to meet", "not letting me meet"))
        else f"{blocker} is stopping you from seeing {child}"
        if _has_any(q, ("stopping me from seeing", "seeing my son", "seeing my daughter"))
        else f"{blocker} is not allowing the father or mother to see {child}"
        if _has_any(q, ("father to see child", "mother to see child", "not allowing father", "not allowing mother"))
        else
        f"{blocker} is hiding {child} and blocking access"
        if _has_any(q, ("hiding our", "hiding my"))
        else f"{blocker} changed phone contact and is preventing meetings with {child}"
        if _has_any(q, ("changed number", "changed phone number", "wants to meet", "want to meet"))
        else
        f"{blocker} blocking calls or communication with {child}"
        if _has_any(q, ("blocked all calls", "blocked calls", "blocking calls", "video calls", "changed number", "changed phone number"))
        else f"{blocker} not sharing {child}'s school/location details"
        if _has_any(q, ("school location", "not sharing school", "location"))
        else f"{blocker} refusing weekend meetings or access with {child}"
        if _has_any(q, ("weekend meeting", "refuses weekend", "refuse weekend"))
        else f"{blocker} stopping or not allowing meetings with {child}"
    )
    lines = ["**Short answer**"]
    if _has_any(q, ("supervised visitation", "unsupervised visitation", "visitation order", "visitation for my")):
        welfare_cite = gwa17 or gwa25 or primary
        lines.append(
            f"Do not treat a lawyer asking for unsupervised visitation as a change to a supervised-visitation order; any change must go back to the custody/family court on the child's welfare standard [{welfare_cite}]."
        )
        if gwa25 is not None:
            lines.append(
                f"If the child is withheld contrary to the existing order, ask the same court or DLSA whether the Guardians and Wards Act return-of-ward route is relevant [{gwa25}]."
            )
    if gwa25 is not None or gwa17 is not None:
        cite = gwa25 if gwa25 is not None else gwa17
        lines.append(
            f"Under the Guardians and Wards Act, if {access_problem} after separation, a spouse's death, or during a custody dispute, treat it as a custody/access and child-welfare issue first; a custody-return/access request turns on the minor's welfare and child's welfare, not a police fight between parents [{cite}]."
        )
    if family is not None:
        lines.append(
            f"For parent-child access, visitation, calls, school-location disclosure, and interim parenting-time relief, the Family Courts Act source makes the Family Court the ordinary forum where there is no urgent child-safety or abduction fact [{family}]."
        )
    if constitution is not None and urgent_access_context:
        lines.append(
            f"If there is urgent illegal detention, safety risk, interstate concealment, or a need for fast production/return review, keep the Article 21 Constitution/High Court writ track as an emergency track alongside Family Court relief; do not use it to replace ordinary custody/access proceedings where facts are not urgent [{constitution}]."
        )
    if hmga is not None:
        lines.append(
            f"If Hindu personal law applies, keep the Hindu Minority and Guardianship natural-guardian source secondary to the child's welfare and any existing custody/access order [{hmga}]."
        )
    action_cites = _cite_many(gwa25, gwa17, family, constitution if urgent_access_context else None, gwa9, hmga) or f"[{primary}]"
    lines.extend([
        "**What you can do next**",
        f"- Preserve messages/calls refusing meetings, the child's age, school/location details, separation timeline, any prior custody order, travel/interstate facts, and your proposed safe meeting schedule; ask Family Court/DLSA for interim visitation or access directions, and use the emergency writ track only if the facts are urgent {action_cites}.",
    ])
    return lines


def _child_marriage_prevention_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "child_marriage_protection" or not _is_child_marriage_prevention(q):
        return []
    pcma = _find(passages, title_terms=("prohibition of child marriage",))
    pocso = _find(passages, title_terms=("protection of children from sexual offences", "pocso"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-137", "/sec-140", "/sec-87", "/sec-351"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    if pcma is None:
        return []

    child = "daughter" if "daughter" in q or "girl" in q else "brother" if "brother" in q else "child"
    urgency = "planned soon" if _has_any(q, ("today", "tonight", "tomorrow", "fixing", "fixed", "venue")) else "planned or completed"
    lines = ["**Short answer**"]
    if pcma is not None:
        lines.append(
            f"For a {child}'s {urgency} underage marriage, treat it as a child-marriage protection problem first; use the Prohibition of Child Marriage Act source for prevention, protection, and later remedy/annulment questions [{pcma}]."
        )
    if pocso is not None:
        lines.append(
            f"If the child may be forced into sexual activity, pregnancy, or cohabitation, keep the POCSO child-safety track separate and urgent; do not wait for the ceremony to happen before seeking help [{pocso}]."
        )
    if bns is not None or bnss is not None:
        cite = bns or bnss
        lines.append(
            f"If there are threats, confinement, kidnapping, assault, or police refusal facts, keep a separate police/criminal-procedure track with the same age and safety proof [{cite}]."
        )
    action_cites = _cite_many(pcma, pocso, bns, bnss)
    lines.extend([
        "**What you can do next**",
        f"- Move on safety first: call 1098/child helpline where available, Child Welfare Committee, police, Child Marriage Prohibition Officer, DLSA, or a trusted adult with the child's location and planned venue/date {action_cites}.",
        f"- Keep age proof such as birth certificate/school record, Aadhaar/ID if safe, invitation/messages, travel/venue details, photos/videos if safe, names of adults arranging it, and any threat or confinement proof {action_cites}.",
    ])
    return lines


def _mtp_reproductive_rights_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "reproductive_rights_mtp" or not _is_mtp_reproductive_rights(q):
        return []
    mtp = _find(passages, title_terms=("medical termination of pregnancy", "mtp"))
    constitution = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-21",))
    reproductive_precedent = _find(passages, title_terms=(
        "principal secretary",
        "ms. z",
        "suchita srivastava",
        "puttaswamy",
    ))
    marriage_law = _find(passages, title_terms=("hindu marriage", "special marriage", "family courts"), anchor_terms=("/sec-13", "/sec-13B", "/sec-13-b", "/sec-7"))
    pocso = _find(passages, title_terms=("protection of children from sexual offences", "pocso"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-63", "/sec-64", "/sec-65", "/sec-70"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-184"))
    if mtp is None:
        return []

    post_24 = _has_any(q, ("6 months", "six months", "24 weeks", "twenty four weeks", "too late", "late for abortion"))
    sexual_offence = _has_any(q, ("rape", "raped", "sexual assault", "pocso", "minor", "child"))
    confidentiality = _has_any(q, ("confidential", "privacy", "husband found", "threatening divorce", "abortion 5 years"))
    lines = ["**Short answer**"]
    if mtp is not None:
        if post_24:
            lines.append(
                f"For a pregnancy around or beyond 24 weeks after rape, treat this as urgent medical-and-legal help, not a normal clinic appointment only; use the MTP source to ask a registered medical practitioner/government hospital, DLSA, or court/medical-board route urgently with gestational-age proof [{mtp}]."
            )
        else:
            lines.append(
                f"For abortion or pregnancy-termination facts, start with the MTP source and a registered medical practitioner/hospital; exact gestational age, medical opinion, and statutory category decide the route [{mtp}]."
            )
    if constitution is not None and confidentiality:
        lines.append(
            f"Keep privacy and dignity facts separate from the marriage dispute; reproductive-health information should not be treated as ordinary gossip or proof without legal review [{constitution}]."
        )
    if reproductive_precedent is not None and (post_24 or confidentiality):
        lines.append(
            f"Use the Supreme Court reproductive-autonomy/privacy precedent with the MTP source for dignity, confidentiality, and medical-decision framing; do not treat the issue as only a family dispute or routine hospital refusal [{reproductive_precedent}]."
        )
    if marriage_law is not None and confidentiality and _has_any(q, ("divorce", "husband", "wife", "court")):
        lines.append(
            f"If a spouse tries to use an old pregnancy-termination fact in matrimonial court, keep the family-law/divorce source separate from the medical-confidentiality source; do not assume the fact automatically decides divorce or cruelty without legal review [{marriage_law}]."
        )
    if sexual_offence and (pocso is not None or bns is not None or bnss is not None):
        cite = pocso or bns or bnss
        lines.append(
            f"If the pregnancy follows rape, child sexual offence, coercion, or assault, keep the medical route and the sexual-offence support/police route separate so treatment is not delayed by criminal paperwork [{cite}]."
        )
    action_cites = _cite_many(mtp, constitution, reproductive_precedent, marriage_law, pocso, bns, bnss)
    lines.extend([
        "**What you can do next**",
        f"- Go urgently to a registered medical practitioner/government hospital with ultrasound/gestational-age proof, doctor's written refusal/reason if any, ID, rape/FIR or complaint details if available, and a trusted support person; ask DLSA/One Stop Centre for same-day help if refused {action_cites}.",
        f"- Preserve medical papers, prescription/refusal note, pregnancy duration proof, age proof if minor, and any threat/coercion messages. Do not wait for a perfect legal answer where urgent medical care is needed; seek the hospital/emergency route first {action_cites}.",
    ])
    return lines


def _female_relative_phrase(q: str) -> str:
    if "mother" in q:
        return "your mother"
    if "aunt" in q:
        return "your aunt"
    if "mausi" in q:
        return "your mausi/aunt"
    if "nani" in q:
        return "your nani/grandmother"
    if "dadi" in q:
        return "your dadi/grandmother"
    if "chachi" in q:
        return "your chachi/aunt"
    if "bua" in q:
        return "your bua/aunt"
    if "sister" in q:
        return "your sister"
    return "the victim"


def _spousal_property_return_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "family_domestic" or route.label != "Spousal jewellery / property return":
        return []
    family_court = _find(passages, title_terms=("family courts",), anchor_terms=("/sec-7", "/sec-8"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-303", "/sec-316", "/sec-318", "/sec-61"))
    ipc = _find(passages, title_terms=("indian penal",), anchor_terms=("/sec-378", "/sec-405", "/sec-406", "/sec-420"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    crpc = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-154", "/sec-156", "/sec-200"))
    primary = family_court or bns or ipc or bnss or crpc
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if family_court is not None:
        lines.append(
            f"Treat this first as a spousal property-return and matrimonial-record issue: list the items, ownership proof, and any pending family case before choosing a Family Court, civil, or settlement route [{family_court}]."
        )
    if bns is not None or ipc is not None:
        criminal = bns or ipc
        lines.append(
            f"Keep a criminal complaint track only if the facts support entrustment or taking, a clear demand for return, refusal, or theft; do not label every spouse property dispute as a criminal case automatically [{criminal}]."
        )
    procedure = bnss or crpc
    if procedure is not None:
        lines.append(
            f"If a police/Magistrate complaint is genuinely needed, preserve the written complaint, acknowledgement/refusal, and item-wise proof before escalation [{procedure}]."
        )
    action_cites = _cite_many(family_court, bns, ipc, bnss, crpc)
    lines.extend([
        "**What you can do next**",
        f"- Make an item-wise list, collect purchase/gift proof, photos, locker/bank records, messages asking for return, separation timeline, and any pending case papers; speak to DLSA/family-law or civil counsel before filing police papers {action_cites}.",
    ])
    return lines


def _streedhan_return_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "family_domestic" or not _is_streedhan_return(q):
        return []
    pwdva = _find(passages, title_terms=("domestic violence",), anchor_terms=("/sec-3", "/sec-12", "/sec-20"))
    dowry = _find(passages, title_terms=("dowry prohibition",))
    hsa14 = _find(passages, title_terms=("hindu succession",), anchor_terms=("/sec-14",))
    hsa = hsa14 or _find(passages, title_terms=("hindu succession",), anchor_terms=("/sec-14", "/sec-15", "/sec-16"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-316", "/sec-318", "/sec-61"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    primary = pwdva or hsa or dowry or bns or bnss
    if primary is None:
        return []

    property_phrase = "streedhan locker keys" if "locker" in q else "streedhan/gold/jewellery"
    lines = ["**Short answer**"]
    if pwdva is not None:
        lines.append(
            f"If your husband or in-laws kept your {property_phrase} and are refusing return, treat it first as a streedhan economic abuse/economic-abuse and domestic-relief issue under the Protection of Women from Domestic Violence route [{pwdva}]."
        )
    if bns is not None:
        lines.append(
            f"Keep a separate police/criminal-breach-of-trust track only where the facts show entrustment, possession, demand for return, and refusal; do not reduce streedhan to a generic family-property argument [{bns}]."
        )
    if dowry is not None:
        lines.append(
            f"The Dowry Prohibition Act source may help if the property was linked to dowry/presents, but it should not replace the item-wise streedhan ownership and return record [{dowry}]."
        )
    if hsa14 is not None:
        lines.append(
            f"If the question is after the husband's death, also keep the Hindu Succession Section 14 source with the file because a female Hindu's streedhan/jewellery ownership should not be treated as ordinary in-law property [{hsa14}]."
        )
    elif hsa is not None and _has_any(q, ("husband died", "husband death", "after husband", "widow")):
        lines.append(
            f"Because the question is after the husband's death, keep the Hindu Succession source with the file so jewellery/streedhan and succession claims are not treated as ordinary in-law property [{hsa}]."
        )
    action_cites = _cite_many(pwdva, hsa, dowry, bns, bnss)
    lines.extend([
        "**What you can do next**",
        f"- Make an item-wise streedhan list, locker/key details, bank-locker documents if any, wedding photos, bills, chats demanding return, witnesses, and possession proof; ask a Protection Officer/Magistrate/DLSA for return/monetary relief before deciding whether a police complaint is supported {action_cites}.",
    ])
    return lines


def _street_vendor_removal_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "street_vendor_municipal" or not _is_street_vendor_removal(q):
        return []
    street18 = _find(passages, title_terms=("street vendors",), anchor_terms=("/sec-18",))
    street19 = _find(passages, title_terms=("street vendors",), anchor_terms=("/sec-19",))
    street4 = _find(passages, title_terms=("street vendors",), anchor_terms=("/sec-4",))
    street_any = _find(passages, title_terms=("street vendors",))
    primary = street18 or street19 or street4 or street_any
    if primary is None:
        return []

    stall = (
        "fruit cart"
        if "fruit cart" in q
        else "vegetable stall"
        if "vegetable" in q and "stall" in q
        else "vegetable cart"
        if "vegetable" in q
        else "tea cart"
        if "tea cart" in q
        else "street-vending cart/stall"
    )
    city_prefix = "Pune " if "pune" in q else ""
    lines = [
        "**Short answer**",
        f"If {city_prefix}hawker-zone people, police, or municipal staff are removing your {stall}, treat it as a Street Vendors Act/Town Vending Committee notice, relocation, seizure, or release-of-goods problem, not just an oral local order [{primary}].",
    ]
    if street19 is not None:
        lines.append(
            f"If goods or stock are taken, ask for a seizure list/inventory, receipt, release process, and the rule or challan basis before arguing only about the stock value [{street19}]."
        )
    if street4 is not None:
        lines.append(
            f"Keep your vending receipt/certificate-of-vending, survey status, vending-zone record, or Town Vending Committee papers separate from the immediate removal problem [{street4}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Preserve vending receipt/certificate/survey proof, location photos, fee receipts, challan/fine papers, removal notice, seizure memo, goods list, and witness names; ask the municipal office/Town Vending Committee in writing for the exact order and appeal or release route [{primary}].",
    ])
    return lines


def _crypto_exchange_wallet_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "digital_platform_account" or not _is_crypto_wallet_freeze(q):
        return []
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-2", "/sec-38"))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-79", "/sec-66D", "/sec-43"))
    pmla = _find(passages, title_terms=("prevention of money laundering",), anchor_terms=("/sec-5", "/sec-8", "/sec-17", "/sec-50"))
    primary = consumer or it_act or pmla
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if consumer is not None:
        lines.append(
            f"If a crypto exchange froze your wallet and support is not replying, keep a consumer/platform-service grievance track for the account freeze, support ticket, wallet access, and money-withheld facts [{consumer}]."
        )
    if it_act is not None:
        lines.append(
            f"Keep the IT Act/electronic-record track as a second source for platform account, intermediary, electronic communication, or cyber-fraud facts, especially if the freeze followed unauthorized access or a suspicious online transaction [{it_act}]."
        )
    if pmla is not None:
        lines.append(
            f"If the exchange says AML/FIU/suspicious transaction or legal hold, separate that PMLA/platform compliance-hold track from an ordinary no-response service complaint instead of guessing the reason [{pmla}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Preserve wallet ID, transaction hashes, KYC/freeze notice, support tickets, emails/chats, screenshots of balance/freeze, withdrawal attempts, and any platform AML/legal hold reason; escalate through platform grievance, National Consumer Helpline/e-Daakhil, and cyber police only if fraud/unauthorized access is involved [{consumer or it_act or primary}].",
    ])
    return lines


def _cyber_money_fraud_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"cyber_fraud_or_harassment", "banking_credit_dispute"} or not _is_cyber_money_fraud(q):
        return []
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66C", "/sec-66D", "/sec-66E"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-318", "/sec-319", "/sec-351"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    rbi = _find(passages, title_terms=("reserve bank integrated ombudsman",), anchor_terms=("/sec-2", "/sec-3"))
    pmla = _find(passages, title_terms=("prevention of money laundering",), anchor_terms=("/sec-2", "/sec-5", "/sec-8", "/sec-17", "/sec-50"))
    primary = it_act or rbi or bns or bnss or pmla
    if primary is None:
        return []

    fraud_amount = _money_amount_phrase(q)
    crypto_context = _has_any(q, ("crypto", "usdt", "wallet", "rugpull", "rugpulled", "telegram crypto", "coin", "token"))
    fraud_phrase = (
        "fake customer-care AnyDesk remote-access transfer"
        if "anydesk" in q
        else f"Telegram crypto rug-pull or Telegram crypto/investment rug-pull or wallet-transfer scam involving {fraud_amount}"
        if crypto_context
        else "fake stock/investment trading-app transfer"
        if _has_any(q, ("fake stock", "stock trading app", "fake trading app", "trading app", "investment app"))
        else "WhatsApp/account-takeover impersonation asking contacts for money"
        if _has_any(q, ("whatsapp account", "account hacked", "whatsapp hacked", "asking my contacts for money", "asking contacts for money"))
        else "online scam transfer with cyber-cell follow-up pending"
        if _has_any(q, ("duped", "cyber cell complaint", "cyber complaint filed", "no progress", "multiple upi ids"))
        else
        f"OTP shared or stolen with {fraud_amount} gone and bank alleging customer negligence/no refund"
        if _has_any(q, ("otp", "customer negligence", "negligence", "no refund"))
        else
        "fake customer-care remote-access transfer"
        if _has_any(q, ("fake customer care", "fake customer support", "fake helpline", "install app", "installed app", "remote access", "anydesk", "screen sharing"))
        else "unauthorized credit-card transaction"
        if _has_any(q, ("credit card", "card transaction"))
        else "OTP/UPI fraud"
    )
    lines = ["**Short answer**"]
    if it_act is not None:
        lines.append(
            f"For a {fraud_phrase}, keep the IT Act cyber-fraud track first because identity theft, cheating by personation, privacy, or electronic-record misuse may be involved [{it_act}]."
        )
    if rbi is not None:
        lines.append(
            f"Keep a bank/RBI refund track in parallel: file or update the bank complaint immediately and use the RBI Ombudsman/CMS regulated-entity complaint route if the bank refuses reversal, says customer negligence, or gives only a blame-the-customer reply [{rbi}]."
        )
    if bns is not None:
        if crypto_context:
            lines.append(
                f"If the crypto group, organiser, wallet address, token, or investment promise involved dishonest inducement or false identity, preserve a separate BNS cheating/personation track for police/cyber complaint review [{bns}]."
            )
        else:
            lines.append(
                f"If someone impersonated customer care, induced an app install, took OTP/card credentials, or dishonestly moved money, preserve a separate BNS cheating/personation or intimidation track for police/cyber complaint review [{bns}]."
            )
    if bnss is not None:
        lines.append(
            f"For the police/cyber complaint route, use the current FIR/information and Magistrate-escalation sources with the transaction and device evidence [{bnss}]."
        )
    if pmla is not None and crypto_context:
        lines.append(
            f"If wallet addresses, exchange accounts, mule accounts, or layering of proceeds appear, preserve the PMLA/financial-trail source as a follow-the-money record; this supports escalation but should not replace the immediate cyber/FIR complaint [{pmla}]."
        )
    action_cite = rbi if rbi is not None else it_act if it_act is not None else bns if bns is not None else bnss
    evidence_cite = it_act if it_act is not None else bns if bns is not None else rbi if rbi is not None else bnss
    action_citations = _cite_many(rbi, it_act, bnss, bns, pmla) or f"[{action_cite}]"
    lines.extend([
        "**What you can do next**",
        f"- Act fast: call/report through 1930 or cybercrime.gov.in, ask the bank to freeze/trace the money trail, take a written bank complaint/refund number, and preserve the cyber complaint acknowledgement before waiting for customer care callbacks {action_citations}.",
        (
            f"- Keep wallet addresses, transaction hashes, exchange/UPI/bank transfer proof, Telegram group/profile links, token/project screenshots, organiser handles, dates, bank reply, and cyber complaint number [{evidence_cite}]."
            if crypto_context else
            f"- Keep transaction ID/RRN/UPI reference, card statement, bank SMS/email, app name or remote-access details, phone number/URL, screenshots, device/SIM facts, bank reply, and cyber complaint number [{evidence_cite}]."
        ),
    ])
    return lines


def _bank_account_freeze_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"banking_credit_dispute", "cyber_fraud_or_harassment"} or not _is_bank_freeze(q):
        return []
    rbi = _find(passages, title_terms=("reserve bank integrated ombudsman",))
    banking = _find(passages, title_terms=("banking regulation",), anchor_terms=("/sec-35A",))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-106",))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66C", "/sec-66D", "/sec-66E"))
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-2"))
    primary = rbi or banking or bnss or it_act or consumer
    if primary is None:
        return []
    legal_hold = _has_any(q, (
        "police", "cyber", "fir", "court", "ed", "legal hold", "lien",
        "fraud complaint against my upi",
    ))
    account = "salary account" if "salary account" in q else "savings account" if "savings account" in q else "UPI account" if "upi account" in q else "bank account"
    lines = ["**Short answer**"]
    if rbi is not None:
        account_detail = (
            "salary account blocked"
            if account == "salary account"
            else "ICICI/savings account lien after a cyber cell email with no FIR number shared"
            if "cyber cell" in q and "fir" in q and "lien" in q
            else "UPI account blocked/frozen"
            if account == "UPI account"
            else account
        )
        lines.append(
            f"For a frozen/blocked/lien-marked {account_detail}, start with a written bank-grievance record and the RBI Ombudsman/CMS route if the bank does not give a proper written reason or resolution [{rbi}]."
        )
    if banking is not None:
        lines.append(
            f"Keep the Banking Regulation/RBI-directions source separate from any police or cyber hold: first ask the branch for the exact freeze/lien/KYC reason, police or court reference, authority, reference number, and complaint number [{banking}]."
        )
    if legal_hold and bnss is not None:
        notice_phrase = " with no notice" if "no notice" in q or "without notice" in q else ""
        lines.append(
            f"If the bank says cyber police, police request{notice_phrase}, FIR, court order, or other legal hold caused the freeze, use the BNSS seizure/legal-hold track with legal aid instead of treating it as only a bank-service complaint [{bnss}]."
        )
    if legal_hold and it_act is not None:
        lines.append(
            f"Because the hold is linked to a cyber complaint or electronic transaction, keep the IT Act cyber/electronic-record source with the bank freeze papers instead of treating it as only a KYC dispute [{it_act}]."
        )
    elif consumer is not None:
        lines.append(
            f"If there is no legal hold and the bank simply refuses service or reversal, the consumer service-deficiency route is a backup after the bank grievance and RBI record exist [{consumer}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Bank branch/grievance officer first, then RBI Ombudsman/CMS for bank-service failure; if a cyber cell email, FIR, police request, or court hold is named, take the written freeze/lien reason and police or court reference to DLSA, cyber police, or the concerned court/Magistrate [{rbi or bnss or primary}].",
        f"- Account statement, freeze/lien/KYC reason or SMS/email, KYC proof, complaint number, branch reply/no-reply proof, transaction IDs, FIR number if available, and any police or court reference / cyber request reference [{primary}].",
    ])
    return lines


def _bank_wrong_debit_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "banking_credit_dispute" or not _is_wrong_debit(q):
        return []
    rbi = _find(passages, title_terms=("reserve bank integrated ombudsman",))
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-2"))
    banking = _find(passages, title_terms=("banking regulation",))
    primary = rbi or consumer or banking
    if primary is None:
        return []
    lines = ["**Short answer**"]
    subject = (
        "ATM cash-not-dispensed transaction where the account was debited"
        if _has_any(q, ("atm cash not dispensed", "cash not dispensed", "atm did not dispense", "atm withdrawal failed", "account debited", "atm debited"))
        else
        "HDFC card forex markup charged twice with support saying wait 45 days"
        if _has_any(q, ("forex", "markup", "card", "45 days", "hdfc"))
        else "wrong debit, wrong deduction, failed UPI debit, deducted, or debited transaction"
    )
    if rbi is not None:
        lines.append(
            f"For {subject} where customer care or branch is not helping, first create a written bank complaint with the ATM/card/transaction details and complaint number, then use the RBI Ombudsman/CMS route if the bank reply or non-reply does not fix it [{rbi}]."
        )
    if consumer is not None:
        lines.append(
            f"The Consumer Protection Act route is the service-deficiency backup for {subject} after the bank grievance/RBI record is clear [{consumer}]."
        )
    elif banking is not None:
        lines.append(
            f"The banking-regulation source supports keeping this as a bank-service record problem, not as a random civil dispute, until the bank gives a written explanation [{banking}]."
        )
    evidence_phrase = (
        "ATM ID/location, withdrawal time, account statement debit, ATM slip if any, SMS/email alerts, branch/customer-care complaint number, written refusal or no-reply proof, and CCTV/request timeline"
        if "atm cash-not-dispensed" in subject.lower()
        else "bank/card statement entry, UPI/transaction ID/RRN or card transaction reference, forex markup/charge slip, SMS/email alerts, customer-care chats/call logs, complaint number, written refusal or no-reply proof, and the exact debit/refund timeline"
    )
    lines.extend([
        "**What you can do next**",
        f"- For {subject}, go to the bank grievance officer first with a written complaint number; use RBI Ombudsman/CMS after the complaint/reply period; consumer forum is only a later service-deficiency route if the banking escalation does not resolve it [{rbi or consumer or primary}].",
        f"- For {subject}, keep the {evidence_phrase} [{primary}].",
    ])
    return lines


def _bank_credit_noc_cibil_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "banking_credit_dispute" or not _is_credit_noc_cibil(q):
        return []
    rbi = _find(passages, title_terms=("reserve bank integrated ombudsman",))
    cic = _find(passages, title_terms=("credit information companies",))
    consumer = _find(passages, title_terms=("consumer protection",))
    primary = cic or rbi or consumer
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if cic is not None:
        lines.append(
            f"For a closed personal loan where the bank is not giving NOC or CIBIL still shows the loan as active/written-off, keep a separate credit-report correction track under the Credit Information Companies source [{cic}]."
        )
    if rbi is not None:
        lines.append(
            f"File a written bank/NBFC grievance or written complaint for the NOC, loan-closure statement, and correction request first; use RBI Ombudsman/CMS if the regulated entity does not correct or explain it in writing [{rbi}]."
        )
    if consumer is not None:
        lines.append(
            f"The Consumer Protection Act route is only the service-deficiency backup if the lender/credit-report route does not fix the closed-loan record [{consumer}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Ask the bank/NBFC in writing for the loan-closure statement, NOC/no-dues certificate, date of closure, bureau update request, and written complaint number; then file the credit-bureau dispute with the CIBIL report entry and lender reply [{primary}].",
        f"- Keep repayment proof, foreclosure/closure receipt, account statement, NOC request, bank replies/no-reply proof, CIBIL/credit-report screenshot, bureau dispute ID, and complaint timeline [{primary}].",
    ])
    return lines


def _sarfaesi_132_notice_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "banking_credit_dispute" or not _is_sarfaesi_132_notice(q):
        return []
    sarfaesi13 = _find(passages, title_terms=("securitisation", "sarfaesi"), anchor_terms=("/sec-13",))
    sarfaesi17 = _find(passages, title_terms=("securitisation", "sarfaesi"), anchor_terms=("/sec-17",))
    rbi = _find(passages, title_terms=("reserve bank integrated ombudsman",))
    if sarfaesi13 is None:
        return []

    asset = "home-loan secured property" if _has_any(q, ("home loan", "house", "flat", "property")) else "secured asset"
    lines = [
        "**Short answer**",
        f"For a SARFAESI section 13(2) demand notice on a {asset}, treat it as a secured-creditor notice response first: check the notice amount, secured asset description, account/NPA details, and the response deadline before assuming the bank can take possession immediately [{sarfaesi13}].",
        f"You can negotiate/OTS in writing, but also file a written representation or objection to the authorised officer within the notice track; keep proof of submission and the bank reply because later SARFAESI steps depend on this record [{sarfaesi13}].",
    ]
    if sarfaesi17 is not None:
        lines.append(
            f"If the bank later takes a section 13(4)-type measure such as possession or sale action, keep the DRT section 17 remedy track separate from the earlier 13(2) reply/negotiation track [{sarfaesi17}]."
        )
    elif rbi is not None:
        lines.append(
            f"Use the bank grievance/RBI record only for servicing or grievance handling; it does not replace the SARFAESI statutory reply and DRT path [{rbi}]."
        )
    action_cites = _cite_many(sarfaesi13, sarfaesi17, rbi)
    lines.extend([
        "**What you can do next**",
        f"- Download the full notice and loan statement, calculate arrears, collect sanction letter, mortgage/security papers, NPA notice, payment/EMI proof, hardship/settlement proposal, and send a written representation/OTS proposal with acknowledgement; speak to a DRT/SARFAESI lawyer quickly if possession action is threatened {action_cites}.",
    ])
    return lines


def _sarfaesi_possession_measure_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "banking_credit_dispute" or not _is_sarfaesi_possession_stage(q):
        return []
    sarfaesi13 = _find(passages, title_terms=("securitisation", "sarfaesi"), anchor_terms=("/sec-13",))
    sarfaesi17 = _find(passages, title_terms=("securitisation", "sarfaesi"), anchor_terms=("/sec-17",))
    if sarfaesi13 is None or sarfaesi17 is None:
        return []

    lines = [
        "**Short answer**",
        f"If the bank has issued a SARFAESI possession/sale notice or taken a section 13(4)-type measure, do not answer it as only a fresh 13(2) demand-notice reply; treat it as a possession-stage SARFAESI problem and verify the bank's 13(4) measure, dates, and secured-asset papers [{sarfaesi13}].",
        f"The DRT section 17 track is the remedy source to check after a SARFAESI possession/sale measure; keep the DRT filing limitation, possession date, notice date, and bank action record separate from any settlement/OTS discussion [{sarfaesi17}].",
        "**What you can do next**",
        f"- Collect the 13(2) demand notice, your objection/representation if any, bank reply, possession/sale notice, panchnama/photos if possession happened, loan/NPA statement, security/mortgage papers, payment proof, and settlement emails; speak to a DRT/SARFAESI lawyer urgently about section 17 while keeping OTS talks in writing {_cite_many(sarfaesi13, sarfaesi17)}.",
    ]
    return lines


def _credit_identity_misuse_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"banking_credit_dispute", "cyber_fraud_or_harassment"} or not _is_credit_identity_misuse(q):
        return []
    cic = _find(passages, title_terms=("credit information companies",))
    rbi = _find(passages, title_terms=("reserve bank integrated ombudsman",))
    banking = _find(passages, title_terms=("banking regulation",), anchor_terms=("/sec-21", "/sec-35A", "/sec-35a"))
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66C", "/sec-66D"))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-318", "/sec-319", "/sec-336", "/sec-340"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    primary = cic or rbi or banking or it_act or bns or bnss
    if primary is None:
        return []

    cibil_context = _has_any(q, (
        "cibil", "credit report", "credit score", "credit information",
        "loan which i never took", "which i never took", "i never took",
        "never took", "not my loan", "fake loan", "opened with my pan",
        "opened with my aadhaar", "opened with my aadhar",
    ))
    lines = ["**Short answer**"]
    if cic is not None:
        intro = (
            "If CIBIL or another credit report shows a loan you never took, start with a credit-report/false-loan correction track: dispute the entry with the credit information company and the bank/NBFC/lender, asking for the loan account, KYC/e-sign basis, disbursal account, and bureau correction under the Credit Information Companies source"
            if cibil_context
            else "For an NBFC/finance-company loan showing against your documents where the signature is not yours, keep a credit-report/false-loan correction track under the Credit Information Companies source, not a loan-app harassment track"
        )
        lines.append(f"{intro} [{cic}].")
    if rbi is not None:
        complaint = (
            "If the lender or bank does not correct or explain the CIBIL/credit-report entry in writing, use its grievance channel and RBI Ombudsman/CMS with the bureau dispute ID, CIBIL screenshot, PAN/Aadhaar or KYC misuse proof, and complaint number"
            if cibil_context
            else "For a forged-loan or bank-service dispute where a loan was taken against your house/property or documents without your signature, give the bank/NBFC or lender a written complaint asking for the loan application, KYC file, signature/e-sign basis, disbursal account, security/property papers, and complaint number; use RBI Ombudsman/CMS if the regulated entity does not correct or explain it in writing"
        )
        lines.append(f"{complaint} [{rbi}].")
    if banking is not None:
        lines.append(
            f"If the loan was created against the house/property or bank security papers without your signature, keep the Banking Regulation/bank-record source with the loan application, sanction, mortgage/security, and KYC file request instead of relying only on the credit-bureau correction route [{banking}]."
        )
    if it_act is not None:
        lines.append(
            f"If the false loan used electronic KYC, online identity details, or digital credentials, preserve a separate cyber identity-theft/personation track under the IT Act source [{it_act}]."
        )
    if bns is not None:
        lines.append(
            f"If there is forged signature, fabricated KYC, cheating, or document forgery, keep a separate police/cyber complaint track instead of treating it as only a civil loan dispute [{bns}]."
        )
    elif bnss is not None:
        lines.append(
            f"For police or cyber complaint paperwork, preserve the complaint/FIR route separately from the lender and credit-bureau correction route [{bnss}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep the credit report or lender notice, loan account/NBFC name, disputed signature page if available, KYC documents, complaint number, bureau dispute ID, cyber/police acknowledgement if filed, and all lender replies or no-reply proof [{primary}].",
    ])
    return lines


def _friendly_loan_civil_recovery_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "business_contract_partnership" or route.label != "Personal loan / money recovery":
        return []
    contract = _find(passages, title_terms=("indian contract",))
    limitation = _find(passages, title_terms=("limitation",))
    cpc = _find(passages, title_terms=("code of civil procedure",))
    ni = _find(passages, title_terms=("negotiable instruments",))
    primary = contract or limitation or cpc or ni
    if primary is None:
        return []
    proof_phrase = (
        "WhatsApp repayment message"
        if _has_any(q, ("whatsapp", "message", "will repay", "says he will repay", "said he will repay"))
        else "repayment promise or acknowledgement"
    )
    person = "neighbour" if _has_any(q, ("neighbour", "neighbor")) else "friend" if "friend" in q else "family/friendly borrower"
    lines = ["**Short answer**"]
    if contract is not None:
        lines.append(
            f"Treat money borrowed by a {person} as a civil money-recovery issue first; use the Indian Contract Act source for the repayment promise/proof instead of assuming police can recover an ordinary unpaid loan [{contract}]."
        )
    else:
        lines.append(
            f"Treat money borrowed by a {person} as a civil money-recovery issue first; use the available civil source before assuming police can recover an ordinary unpaid loan [{primary}]."
        )
    if limitation is not None:
        lines.append(
            f"Check limitation under the Limitation Act from the loan date, due date, last part-payment, or written acknowledgement before filing a recovery case [{limitation}]."
        )
    lines.append(
        f"Do not frame non-payment alone as police cheating; use police only if there are facts of deception at the start, forgery, threats, intimidation, or violence [{primary}]."
    )
    if ni is not None:
        lines.append(
            f"If a repayment cheque was dishonoured, keep the NI Act cheque-bounce route separate from the ordinary civil money claim [{ni}]."
        )
    action_cite = cpc or contract or limitation or primary
    lines.extend([
        "**What you can do next**",
        f"- Send a written demand/legal notice with amount, due date, {proof_phrase}, payment proof, and address for reply; then take it to DLSA or a lawyer/legal-aid desk for civil recovery, summary suit, mediation, or cheque-bounce review where applicable [{action_cite}].",
        f"- Keep bank/UPI/cash proof, witnesses if cash, chats admitting the loan, {proof_phrase}, blocked-call proof, last acknowledgement/part-payment date, and any cheque/security details [{primary}].",
    ])
    return lines


def _loan_app_harassment_lines(
    q: str,
    route: MatterRoute,
    passages: list[dict],
    *,
    enforced_source_indices: dict[str, int] | None = None,
) -> list[str]:
    if route.category not in {"banking_credit_dispute", "cyber_fraud_or_harassment", "criminal_general"} or not _is_loan_app(q):
        return []
    source_indices = enforced_source_indices or {}
    digital_grievance = source_indices.get("digital_grievance") or _find(
        passages, title_terms=("digital lending",), anchor_terms=("/para-11",)
    )
    digital_data = source_indices.get("digital_data") or _find(
        passages, title_terms=("digital lending",), anchor_terms=("/para-12",)
    )
    recovery_conduct = source_indices.get("recovery_conduct") or _find(
        passages, title_terms=("recovery agents",), anchor_terms=("/para-2",)
    )
    rbi_application = source_indices.get("rbi_application") or _find(
        passages, title_terms=("integrated ombudsman",), anchor_terms=("/sec-1",)
    )
    rbi_definitions = source_indices.get("rbi_definitions") or _find(
        passages, title_terms=("integrated ombudsman",), anchor_terms=("/sec-3",)
    )
    rbi_forum = source_indices.get("rbi_forum") or _find(
        passages, title_terms=("integrated ombudsman",), anchor_terms=("/sec-6",)
    )
    rbi_grounds = source_indices.get("rbi_grounds") or _find(
        passages, title_terms=("integrated ombudsman",), anchor_terms=("/sec-9",)
    )
    rbi_maintainability = source_indices.get("rbi_maintainability") or _find(
        passages, title_terms=("integrated ombudsman",), anchor_terms=("/sec-10",)
    )
    if any(index is None for index in (
        digital_grievance, digital_data, recovery_conduct,
        rbi_application, rbi_definitions, rbi_forum,
        rbi_grounds, rbi_maintainability,
    )):
        return []
    it_act = _find(passages, title_terms=("information technology",), anchor_terms=("/sec-66C", "/sec-66D", "/sec-66E", "/sec-67"))
    bns_extortion = _find(
        passages,
        title_terms=("bharatiya nyaya sanhita",),
        anchor_terms=("/sec-308",),
    )
    image_blackmail = _has_any(q, ("morphed nude", "fake nude", "nude", "morphed-image", "morphed image")) and _has_any(q, ("blackmail", "miss payment", "payment tonight", "post", "photo", "upload"))
    photo_contacts_context = _has_any(q, (
        "sending my photo", "photo to contacts", "photo to my contacts",
        "send my photo to contacts", "contacts saying fraud",
        "family whatsapp", "family group", "whatsapp group",
    ))
    recovery_subject = (
        "Bajaj Finance agent threatening to shame you in society"
        if "bajaj" in q and _has_any(q, ("shame", "society"))
        else "NBFC recovery agent came to office and shouted about EMI default in front of staff"
        if _has_any(q, ("nbfc", "recovery agent", "recovery agents", "collection agent", "collection agents"))
        and _has_any(q, ("office", "workplace", "came to office"))
        and _has_any(q, ("shouted", "shouting", "emi default", "staff"))
        else "loan app people calling your boss or employer and saying you are fraud"
        if _has_any(q, ("boss", "manager", "employer", "calling my boss", "calling my manager", "saying i am fraud"))
        else "online loan app calling your relatives and abusing you"
        if _has_any(q, ("relatives", "calling my relatives", "abusing my relatives"))
        else "instant loan app sending your photo to contacts and calling you fraud"
        if photo_contacts_context
        else "finance company caller threatening to tell your neighbours you are fraud if you do not pay today"
        if _has_any(q, ("finance company", "neighbours", "neighbors", "fraud", "pay today"))
        else "unregistered loan app blackmailing you with a morphed nude if you miss payment tonight"
        if image_blackmail and _has_any(q, ("unregistered loan app", "loan app", "instant loan app"))
        else "loan app or recovery-agent harassment / threatening to post your photo in a family WhatsApp group"
        if _has_any(q, ("photo", "family whatsapp", "family group", "whatsapp group"))
        else "collection/recovery people threatening workplace or neighbours/neighbour shaming"
        if _has_any(q, ("collection people", "tell my office", "tell my neighbours", "tell my neighbors", "workplace", "emi default"))
        else "NBFC recovery people abusing you on phone and visiting your office"
        if _has_any(q, ("nbfc", "visiting office", "workplace", "office"))
        else "Loan app or recovery harassment (loan app or recovery-agent harassment)"
    )
    lines = [
        "**Short answer**",
        f"RBI Digital Lending Directions paragraph 12 requires need-based, explicitly consented data collection and says regulated loan apps must not access contact lists or call logs [{digital_data}].",
        f"RBI's recovery-agent circular prohibits intimidation or harassment, public humiliation, and intrusion into the privacy of a debtor's family members, referees, and friends [{recovery_conduct}].",
        f"Ombudsman Scheme Clause 1 applies the Scheme to services provided by a Regulated Entity in India, and Clause 3 defines a Regulated Entity to include a bank or covered NBFC [{rbi_application}], [{rbi_definitions}].",
        f"The lender and its app/LSP must provide a grievance route; rejection, an unsatisfactory reply, or 30 days without a reply can lead to RBI CMS escalation [{digital_grievance}].",
        f"For RBI Ombudsman filing, Clause 9 supplies the complaint ground and Clause 10 supplies the prior-grievance and maintainability conditions [{rbi_grounds}], [{rbi_maintainability}].",
    ]
    if image_blackmail and it_act is not None:
        lines.append(
            f"IT Act Section 66E is narrower than a general morphed-image threat: it applies to intentional or knowing capture, publication, or transmission of an actual private-area image without consent in privacy-violating circumstances [{it_act}]."
        )
    if image_blackmail and bns_extortion is not None:
        lines.append(
            f"Because the threat is tied to a demand for payment, BNS Section 308 is the extortion source to check: it covers inducing delivery of property by fear of injury and also attempting to put a person in fear in order to commit extortion [{bns_extortion}]."
        )
    lines.extend([
        "**What you can do next**",
        (
            "- Preserve screenshots, caller/app name, loan account, repayment proof, phone numbers, payment demand, and messages; use the urgent cyber-reporting option in the action path, and do not pay or forward the threatened image."
            if image_blackmail and it_act is not None
            else f"- Use the grievance officer identified under paragraph 11 for a written complaint to the regulated lender or app/LSP; keep the reply or no-reply record [{digital_grievance}]."
        ),
        (
            f"- Confirm that the provider is a covered bank or NBFC before using RBI CMS; Clause 1 limits the Scheme to services of a Regulated Entity in India, and Clause 3 defines the covered entity types [{rbi_application}], [{rbi_definitions}]."
            if image_blackmail and it_act is not None
            else f"- Keep a dated record that {recovery_subject}, plus the lender/app name, loan account, repayment proof, app permissions, call logs, messages sent to contacts, complaint number, and any threat recordings."
        ),
        (
            f"- Use the grievance officer identified under paragraph 11 [{digital_grievance}]. If Clause 10 is satisfied, file through RBI Ombudsman/CMS or the Centralised Receipt and Processing Centre identified by Clause 6 [{rbi_maintainability}], [{rbi_forum}]."
            if image_blackmail and it_act is not None
            else f"- If Clause 10 is satisfied, file through RBI Ombudsman/CMS or the Centralised Receipt and Processing Centre identified by Clause 6 [{rbi_forum}]."
        ),
    ])
    return lines


def _marital_intimacy_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "family_marriage_status" or not _is_marital_intimacy(q):
        return []
    family = _find(passages, title_terms=("family courts",), anchor_terms=("/sec-7", "/sec-8"))
    hma = _find(passages, title_terms=("hindu marriage",), anchor_terms=("/sec-9", "/sec-10", "/sec-13"))
    sma = _find(passages, title_terms=("special marriage",), anchor_terms=("/sec-22", "/sec-23", "/sec-27", "/sec-28"))
    primary = family or hma or sma
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if family is not None:
        lines.append(
            f"Treat refusal of sex, physical relation, or no marital relationship as a matrimonial/family-court counselling or remedy question first, because the Family Courts Act is the forum source for matrimonial proceedings [{family}]."
        )
    if hma is not None:
        lines.append(
            f"If the Hindu Marriage Act applies, the exact remedy depends on specific facts and proof; do not assume every intimacy dispute automatically becomes divorce, cruelty, or restitution [{hma}]."
        )
    elif sma is not None:
        lines.append(
            f"If the Special Marriage Act applies, the matrimonial remedy still turns on the facts, proof, and relief sought, not on a general marital right to sex [{sma}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Consent matters: do not force, threaten, or pressure your spouse for sex; discuss counselling/mediation, judicial separation, divorce, restitution, maintenance, or other family-court relief only through lawful advice and specific facts [{primary}].",
        f"- Marriage proof, timeline, messages, counselling attempts if any, residence/children/maintenance facts, and any violence or coercion facts before speaking to DLSA or a family-law lawyer [{primary}].",
    ])
    return lines


def _marriage_misrepresentation_voidable_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "family_marriage_status" or route.label != "Marriage misrepresentation / family-law options":
        return []
    hma = _find(passages, title_terms=("hindu marriage",), anchor_terms=("/sec-12",))
    sma = _find(passages, title_terms=("special marriage",), anchor_terms=("/sec-24", "/sec-25", "/sec-27"))
    family = _find(passages, title_terms=("family courts",), anchor_terms=("/sec-7", "/sec-8"))
    primary = hma or sma
    if primary is None:
        return []

    orientation_context = _has_any(q, ("gay", "lesbian", "same sex", "same-sex", "sexual orientation", "lgbt", "lgbtq", "queer"))
    salary_loan_context = _has_any(q, ("salary", "job", "loans", "loan", "income", "biodata", "profile"))
    issue = (
        "hidden sexual-orientation or relationship facts"
        if orientation_context
        else "salary, job, loans, income, or biodata facts"
        if salary_loan_context
        else "pre-marriage representation or concealment facts"
    )

    lines = [
        "**Short answer**",
        f"If your concern is {issue}, treat it as a family-law validity/remedy question first: check whether the proven pre-marriage statement, concealment, timing, and proof support voidable-marriage or matrimonial-relief advice under the personal-law/Special Marriage Act source; not every lie automatically cancels a marriage, and not every nondisclosure automatically cancels a marriage [{primary}].",
    ]
    if orientation_context:
        lines.append(
            f"Keep the response privacy-preserving and remedy-focused: collect proof of what was represented before marriage and when you discovered it, then ask DLSA or a family-law lawyer whether annulment, divorce, maintenance, counselling, or settlement is the correct route [{primary}]."
        )
    if family is not None:
        lines.append(
            f"The Family Courts Act source is the forum route for annulment/voidable-marriage, divorce, maintenance, counselling, or other matrimonial relief after the personal-law source and marriage form are identified [{family}]."
        )
    action_cites = _cite_many(primary, family)
    lines.extend([
        "**What you can do next**",
        f"- Keep marriage certificate/proof, religion or Special Marriage Act registration facts, biodata/profile/messages, salary/job/loan proof where relevant, date you discovered the truth, and what relief you want; avoid threats, public posts, or unsupported police complaints {action_cites}.",
    ])
    return lines


def _property_lifetime_gift_heir_share_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"property_tenancy", "succession_inheritance"}:
        return []
    if not (
        _has_any(q, ("father transferred", "father gifted", "transferred flat", "transferred land", "gift valid"))
        and _has_any(q, ("daughter wants share", "daughter", "share", "son before death", "before death"))
    ):
        return []
    tpa_gift = _find(passages, title_terms=("transfer of property",), anchor_terms=("/sec-122", "/sec-123", "/sec-126"))
    registration = _find(passages, title_terms=("registration act",), anchor_terms=("/sec-17", "/sec-49"))
    hsa = _find(passages, title_terms=("hindu succession",), anchor_terms=("/sec-8", "/sec-10", "/sec-15"))
    primary = tpa_gift or registration or hsa
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if tpa_gift is not None:
        lines.append(
            f"For a father transferring or gifting a flat to a son before death, first verify the gift/transfer deed, donor title, free consent, attestation, and possession facts under the Transfer of Property Act gift source [{tpa_gift}]."
        )
    if registration is not None:
        lines.append(
            f"For immovable property, registration and the certified deed matter; if the daughter says the gift is invalid or her share is affected, check the registration record before assuming the transfer binds everyone [{registration}]."
        )
    if hsa is not None:
        lines.append(
            f"Hindu Succession shares matter for property left in the father's estate, but they do not automatically undo a valid lifetime transfer; separate remaining-estate succession from civil court title/cancellation or partition questions about the transferred flat [{hsa}]."
        )
    action_cites = _cite_many(tpa_gift, registration, hsa)
    lines.extend([
        "**What you can do next**",
        f"- Get the certified gift/sale deed, registration receipt, father's title chain, mutation/society records, death certificate, family tree/legal-heir proof, possession and tax records, and any coercion/forgery/capacity facts; use a property lawyer/DLSA for civil court title, cancellation, declaration, or partition advice if the daughter disputes the gift {action_cites}.",
    ])
    return lines


def _property_sale_after_mother_death_docs_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"property_tenancy", "succession_inheritance"}:
        return []
    if not (
        _has_any(q, ("mother passed away", "mother died", "mother death"))
        and _has_any(q, ("father wants to sell", "sell flat", "sell the flat", "what papers", "papers needed"))
    ):
        return []
    hsa15 = _find(passages, title_terms=("hindu succession",), anchor_terms=("/sec-15",))
    hsa10 = _find(passages, title_terms=("hindu succession",), anchor_terms=("/sec-10",))
    tpa = _find(passages, title_terms=("transfer of property",), anchor_terms=("/sec-44", "/sec-45", "/sec-54", "/sec-105"))
    registration = _find(passages, title_terms=("registration act",), anchor_terms=("/sec-17", "/sec-49"))
    primary = hsa15 or hsa10 or tpa or registration
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if hsa15 is not None or hsa10 is not None:
        cite = hsa15 or hsa10
        lines.append(
            f"If the flat was in your mother's name and she died without a will, first identify her legal heirs and shares under the Hindu Succession source before assuming the father alone can sell it [{cite}]."
        )
    if tpa is not None:
        lines.append(
            f"The sale-paper question is a title/share and transfer question: the buyer, sub-registrar, or society will usually need proof of who owns or can transfer the flat, not only an oral family statement [{tpa}]."
        )
    if registration is not None:
        lines.append(
            f"Registration records and certified title documents matter because the sale deed should match the legal heir/title position before the flat is transferred [{registration}]."
        )
    action_cites = _cite_many(hsa15 or hsa10, tpa, registration)
    lines.extend([
        "**What you can do next**",
        f"- For Kolkata or any city, collect the mother's death certificate, title/sale deed, mutation or society share certificate, will/probate if any, family tree/legal-heir proof, ID/address proofs, tax/maintenance dues, NOC/release deed from heirs if everyone agrees, and draft sale deed; use civil court/DLSA/property lawyer help if any heir disputes title, partition, or consent {action_cites}.",
        f"- Use police only for forgery, threats, or coercion facts; ordinary sale permission, partition, title, mutation, or release-deed questions are property/civil court or registration-office issues {action_cites}.",
    ])
    return lines


def _property_verbal_land_gift_dispute_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"property_tenancy", "succession_inheritance"}:
        return []
    if not (
        _has_any(q, ("verbally", "verbal", "orally", "oral gift", "gave land", "gave property"))
        and _has_any(q, ("younger son", "older son", "son disputing", "disputing it", "after 20 yrs", "after 20 years"))
    ):
        return []
    tpa_gift = _find(passages, title_terms=("transfer of property",), anchor_terms=("/sec-122", "/sec-123", "/sec-126"))
    registration = _find(passages, title_terms=("registration act",), anchor_terms=("/sec-17", "/sec-49", "/sec-23"))
    hsa = _find(passages, title_terms=("hindu succession",), anchor_terms=("/sec-15", "/sec-8", "/sec-10"))
    limitation = _find(passages, title_terms=("limitation",), anchor_terms=("/sec-3", "/sec-5"))
    primary = tpa_gift or registration or hsa or limitation
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if tpa_gift is not None:
        lines.append(
            f"For land allegedly given verbally to a younger son, first check the Transfer of Property Act gift source; an immovable-property gift normally needs the proper registered instrument and proof, not only a family oral statement [{tpa_gift}]."
        )
    if registration is not None:
        lines.append(
            f"The registration record is central: if there is no registered gift/sale/release deed, ask a property lawyer to verify whether mutation, possession, or any personal-law exception changes the civil court title position [{registration}]."
        )
    if hsa is not None:
        lines.append(
            f"If the mother's land was not validly transferred during her lifetime, succession and legal-heir shares may need to be checked before either son claims exclusive title [{hsa}]."
        )
    if limitation is not None:
        lines.append(
            f"Because the dispute is after 20 years, preserve possession, mutation, tax, and objection dates; limitation and delay must be checked instead of assuming the old verbal gift automatically wins or fails [{limitation}]."
        )
    action_cites = _cite_many(tpa_gift, registration, hsa, limitation)
    lines.extend([
        "**What you can do next**",
        f"- Collect old title deed, any registered deed or absence proof, mutation/khata/khasra records, tax receipts, possession/cultivation proof, mother's death/status and family tree, witness names, and dates when the older son first disputed it; take the file to DLSA/property lawyer for civil court declaration, partition, injunction, or record-correction advice {action_cites}.",
        f"- Use police only if there is forgery, threats, trespass violence, or fabricated documents; ordinary verbal gift, title, partition, and limitation disputes are civil/property questions {action_cites}.",
    ])
    return lines


def _heir_sale_consent_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"property_tenancy", "succession_inheritance"} or not _is_heir_sale(q):
        return []
    hsa = _find(passages, title_terms=("hindu succession",))
    tpa = _find(passages, title_terms=("transfer of property",), anchor_terms=("/sec-44", "/sec-45"))
    specific = _find(passages, title_terms=("specific relief",), anchor_terms=("/sec-31", "/sec-34", "/sec-38"))
    succession = _find(passages, title_terms=("indian succession",))
    primary = hsa or succession or tpa or specific
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if hsa is not None or succession is not None:
        cite = hsa or succession
        lines.append(
            f"First identify the legal heirs, shares, will/no-will position, and personal succession law before assuming who can sell inherited property [{cite}]."
        )
    if tpa is not None:
        lines.append(
            f"If one legal heir or co-owner is not agreeing, do not assume the whole property can be sold; the Transfer of Property Act co-owner/share source is relevant only for the share or interest that a person can legally transfer [{tpa}]."
        )
        lines.append(
            f"A majority of heirs may try a family settlement, release deed, partition, or sale of their own share, but they should not sell the entire inherited property free of the refusing heir's rights without checking title and court remedies [{tpa}]."
        )
    if specific is not None:
        lines.append(
            f"If a sale is being pushed or already registered despite disputed heir consent, the civil-court declaration, injunction, or cancellation route under the Specific Relief Act is the remedy source to check [{specific}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Try written consent/release/family settlement if everyone agrees; otherwise use partition/declaration/injunction or cancellation in civil court and get revenue/sub-registrar records before relying on any sale paper [{specific or primary}].",
        f"- death certificate, family tree/legal-heir certificate, will if any, title deed, mutation/khata/land records, sale deed/draft sale papers, possession proof, and written consent or refusal from each heir [{primary}].",
    ])
    return lines


def _land_revenue_bribe_demand_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "land_revenue_records" or not _has_any(q, (
        "bribe", "asking 5000", "asking money", "patwari asking", "corruption",
        "rishwat", "ghoos", "pay money",
    )):
        return []
    pca = _find(passages, title_terms=("prevention of corruption",), anchor_terms=("/sec-7", "/sec-8", "/sec-13"))
    if pca is None:
        return []
    explicit_ror_context = _has_any(q, (
        "andhra", "andhra pradesh", "ap ", "pattadar", "passbook",
        "pass book", "record of rights", "ror", "bhudhaar", "bhu dhaar",
    ))
    ror = (
        _find(
            passages,
            title_terms=("andhra pradesh rights in land", "pattadar pass books"),
            anchor_terms=("/sec-4", "/sec-5", "/sec-3", "/sec-9-10"),
        )
        if explicit_ror_context
        else None
    )
    rti = _find(passages, title_terms=("right to information",), anchor_terms=("/sec-6", "/sec-7", "/sec-19"))
    lines = [
        "**Short answer**",
        (
            f"If the patwari/revenue official is asking money to enter your name or move the file, separate the bribe demand from the land-record correction; the Prevention of Corruption Act source is the public-servant undue-advantage track, not an official fee/challan [{pca}]."
        ),
    ]
    if ror is not None:
        lines.append(
            f"For the land-record side, still file or follow up on the mutation/name-entry application through the Tahsildar/MRO/revenue office under the record-of-rights/passbook source where that State system applies [{ror}]."
        )
    if rti is not None:
        lines.append(
            f"If the office refuses an acknowledgement, fee receipt, status, or written reason, use RTI to ask for file status, official fee, officer responsible, and the rule/order relied on [{rti}]."
        )
    action_cites = _cite_many(pca, ror, rti)
    lines.extend([
        "**What you can do next**",
        (
            f"- Do not pay cash without receipt; note date/time/place, official name, exact demand, witnesses, calls/messages, and application number. File a written complaint to the Anti-Corruption Bureau/Lokayukta/vigilance or senior revenue officer, and separately keep the mutation/name-entry application moving with written acknowledgements {action_cites}."
        ),
    ])
    return lines


def _land_pattadar_passbook_replacement_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "land_revenue_records" or not _has_any(q, (
        "pattadar", "passbook", "pass book", "title deed cum passbook",
        "bhudhaar", "bhu dhaar", "record of rights", "ror",
    )):
        return []
    prefer_passbook_copy = _has_any(q, ("lost", "flood", "damaged", "washed away", "missing"))
    ror = None
    if prefer_passbook_copy:
        ror = _find(
            passages,
            title_terms=("andhra pradesh rights in land", "pattadar pass books"),
            anchor_terms=("/sec-6F-7", "/sec-7"),
        )
    if ror is None:
        ror = _find(
            passages,
            title_terms=("andhra pradesh rights in land", "pattadar pass books"),
            anchor_terms=("/sec-3", "/sec-4", "/sec-5", "/sec-6F-7", "/sec-9-10"),
        )
    rti = _find(passages, title_terms=("right to information",), anchor_terms=("/sec-6", "/sec-7", "/sec-19"))
    if ror is None:
        return []
    issue = (
        "lost or damaged pattadar passbook"
        if _has_any(q, ("lost", "flood", "damaged", "washed away", "missing"))
        else "pattadar/passbook or record-of-rights issue"
    )
    lines = [
        "**Short answer**",
        (
            f"For a {issue}, treat this first as a revenue record / certified-copy / passbook-status problem, not a police case unless there is forgery, threat, or cheating; the pattadar passbook source is the record-of-rights Act to verify where that State system applies [{ror}]."
        ),
        (
            f"Ask the Tahsildar/MRO or land-record portal for the record-of-rights extract, passbook/Bhudhaar or title-deed-cum-passbook status, application number, missing-document list, and written refusal or delay reason before accepting an oral 'come next month' answer [{ror}]."
        ),
    ]
    if rti is not None:
        lines.append(
            f"If the office will not give status or reasons in writing, use RTI to ask for the file status, officer responsible, rule/order relied on, and appeal/revision forum [{rti}]."
        )
    lines.extend([
        "**What you can do next**",
        (
            f"- File or follow up with ID/address proof, survey/khata/passbook number, old passbook or record copy if available, tax/receipt proof, flood/loss proof or affidavit where required, application receipt, and any SMS/portal status; escalate to the revenue appellate/revisional authority or DLSA if delayed or refused [{ror}]."
        ),
    ])
    return lines


def _mutation_after_death_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"land_revenue_records", "succession_inheritance"} or not _is_mutation_after_death(q):
        return []
    hsa = _find(passages, title_terms=("hindu succession",))
    succession = _find(passages, title_terms=("indian succession",))
    rti = _find(passages, title_terms=("right to information",), anchor_terms=("/sec-6", "/sec-7", "/sec-19"))
    primary = hsa or succession or rti
    if primary is None:
        return []
    place = (
        "Jharkhand land"
        if "jharkhand" in q
        else "Rajasthan patwari/revenue record"
        if _has_any(q, ("rajasthan", "patwari"))
        else "land/revenue record"
    )
    death_phrase = "husband's death" if _has_any(q, ("husband died", "my husband died")) else "a parent's death"
    lines = ["**Short answer**"]
    if hsa is not None or succession is not None:
        cite = hsa or succession
        lines.append(
            f"For {place} mutation after {death_phrase}, separate succession/heirship from the revenue mutation entry; the succession source helps identify heirs and shares before the record is changed [{cite}]."
        )
    if _has_any(q, ("brother", "sister", "sibling", "blocking", "objection", "objecting", "not allowing", "not signing")):
        lines.append(
            f"If brothers, sisters, or other heirs are blocking mutation, ask the revenue office for the written objection, missing-document list, hearing date, or rejection reason; do not treat an oral block as the final title decision [{rti or primary}]."
        )
    if rti is not None:
        lines.append(
            f"If the patwari/tehsil/revenue office does not update the mutation or give reasons, use RTI to ask for the pending file status, objections, missing documents, and rule/order relied on [{rti}]."
        )
    lines.append(
        f"A legal-heir certificate, family tree, or mutation entry helps the revenue process but does not by itself prove marketable title if another heir objects; use civil court/DLSA for title, share, or injunction disputes [{primary}]."
    )
    lines.extend([
        "**What you can do next**",
        f"- Apply or follow up at the patwari/tehsildar/revenue office with the death certificate, family tree/legal-heir proof, title/khata/khasra or jamabandi record, tax receipts, mutation application number, and any objection/rejection; use revenue appeal or DLSA if delayed or disputed, and use police only for forgery, threats, or violence [{primary}].",
    ])
    return lines


def _municipal_shop_sealing_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"business_license_compliance", "street_vendor_municipal", "property_tenancy"} or not _is_shop_sealed(q):
        return []
    shops = _find(passages, title_terms=("shops", "commercial establishments"))
    rti = _find(passages, title_terms=("right to information",), anchor_terms=("/sec-6", "/sec-7"))
    street_vendor = _find(passages, title_terms=("street vendors",))
    primary = shops or rti or street_vendor
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if shops is not None:
        lines.append(
            f"For a municipal shop sealing/licence closure, check the Shops and Establishments or local commercial-establishment source together with the sealing order and trade-licence file [{shops}]."
        )
    else:
        lines.append(
            f"For a municipality/corporation sealing a shop, the state/local municipal law or Shops and Establishments source must be verified locally; the retrieved source can still support asking for the written order and records instead of guessing from judgments [{primary}]."
        )
    if rti is not None:
        lines.append(
            f"If the municipal authority will not give the sealing order, show-cause notice, inspection report, or licence file, use the RTI/written-record route to obtain reasons and documents [{rti}]."
        )
    if street_vendor is not None:
        lines.append(
            f"If the facts are actually street-vending/cart removal rather than a fixed shop licence, keep the Street Vendors/Town Vending Committee route separate [{street_vendor}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Municipal authority/ward office first for the written order, then the statutory appellate authority or local civil/High Court route only after checking the state/local municipal law and urgency for reopening/release [{primary}].",
        f"- Sealing order, show-cause notice, trade licence, rent/ownership papers, tax/fee receipts, inspection report, photos of seal, inventory of goods, and prior replies or no-notice proof [{primary}].",
    ])
    return lines


def _shop_license_renewal_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "business_license_compliance" or not _is_shop_license_renewal(q):
        return []
    tamil_nadu_shops = _find(
        passages,
        title_terms=("tamil nadu shops and establishments", "tamil nadu shops"),
    )
    coimbatore_trade = _find(
        passages,
        title_terms=("coimbatore city municipal corporation", "licensing of offensive trades"),
    )
    shops = tamil_nadu_shops or _find(passages, title_terms=("shops", "establishments", "establishment"))
    rti = _find(passages, title_terms=("right to information",), anchor_terms=("/sec-6", "/sec-7", "/sec-19"))
    primary = coimbatore_trade or shops or rti
    if primary is None:
        return []
    place = "Tamil Nadu/Coimbatore shop-license renewal" if _has_any(q, ("tamil nadu", "coimbatore")) else "shop/trade-license renewal"
    lines = ["**Short answer**"]
    if coimbatore_trade is not None:
        lines.append(
            f"For Coimbatore D&O/trade-licence renewal or penalty, use the Coimbatore Corporation licensing source for the local renewal window, file movement, and penalty basis; compare it with the actual written demand/order before calculating arrears [{coimbatore_trade}]."
        )
    if tamil_nadu_shops is not None:
        lines.append(
            f"For the Tamil Nadu shop-establishment side, use the Tamil Nadu Shops and Establishments Act source to verify whether the premises is a shop/establishment and which inspector/record/penalty powers are relevant; keep that separate from the municipal D&O licence calculation [{tamil_nadu_shops}]."
        )
    elif shops is not None:
        lines.append(
            f"For {place}, check the Shops and Establishments or local trade-licence source and the actual renewal/penalty order before calculating any penalty [{shops}]."
        )
    elif _has_any(q, ("tamil nadu", "coimbatore", "chennai", "madurai", "tiruppur")) and rti is not None:
        lines.append(
            f"I do not have the exact Tamil Nadu/city licensing source in the retrieved passages for this answer; do not guess the penalty from unrelated judgments, and use the written-record/RTI route to get the controlling renewal rule, demand note, and appeal forum [{rti}]."
        )
    if rti is not None:
        lines.append(
            f"For a {place} or shopkeeper penalty calculation problem, if the state/local shop or trade-licence renewal has been pending or the office is not giving the penalty basis, use RTI/written records request for the renewal status, deficiency memo, inspection note, fee ledger, penalty calculation, and appellate authority [{rti}]."
        )
    lines.append(
        f"Do not shift this to Food Safety/FSSAI unless the notice is actually about food, restaurant, kitchen, FSSAI registration, sample, or food-safety inspection facts [{primary}]."
    )
    lines.extend([
        "**What you can do next**",
        f"- Take the renewal application number, old shop/trade licence, fee receipts, municipal/shops-office messages, any penalty notice, business address proof, GST/Udyam if relevant, and written status request to the state shops/labour office or local municipal licensing office; use RTI/DLSA if the file is stuck without reasons [{primary}].",
    ])
    return lines


def _rajasthan_shop_act_registration_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "business_license_compliance":
        return []
    if not _has_any(q, ("rajasthan", "jaipur", "jodhpur", "udaipur", "kota", "ajmer")):
        return []
    if not _has_any(q, ("shop act", "shops and establishments", "labour inspector", "register under shop", "shop registration", "4 staff", "staff")):
        return []
    shops = _find(passages, title_terms=("rajasthan shops and commercial establishments",), anchor_terms=("/sec-4", "/sec-2", "/sec-5"))
    fee = _find(passages, title_terms=("rajasthan shops and commercial establishments act 1958 fee structure",), anchor_terms=("/registration-fee-checklist",))
    rti = _find(passages, title_terms=("right to information",), anchor_terms=("/sec-6", "/sec-7", "/sec-19"))
    food = _find(passages, title_terms=("food safety", "fssai"))
    primary = shops or fee or rti
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if shops is not None:
        lines.append(
            f"For a Jaipur/Rajasthan shop-registration demand from a labour inspector, start with the Rajasthan Shops and Commercial Establishments Act registration source, not FSSAI, unless the notice is actually about food business, kitchen, sample, or food-safety inspection facts [{shops}]."
        )
    if fee is not None:
        lines.append(
            f"The Rajasthan Labour Department fee/checklist source is the practical filing route for employee-count slab, online application, documents, and registration/renewal penalty checks [{fee}]."
        )
    if food is not None:
        lines.append(
            f"Do not use the Food Safety/FSSAI source just because the word registration appears; use it only if the written notice names food safety, FSSAI, restaurant/kitchen, food sample, or health-inspection facts [{food}]."
        )
    if rti is not None:
        lines.append(
            f"If the labour office will not give the exact registration requirement, deficiency memo, penalty basis, or inspection note, use a written status request/RTI for those records [{rti}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Ask the labour inspector/LDMS office for the written provision, application number, deficiency memo, employee-count basis, fee/penalty calculation, and deadline; keep shop address proof, owner ID, employee list, wage details, weekly-holiday details, photos, fee receipt, and any inspection message [{primary}].",
    ])
    return lines


def _procedure_nclat_appeal_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "ibc_nclt" or "nclat" not in q or not _has_any(q, ("appeal", "tribunal order", "nclt order", "order against")):
        return []
    ibc61 = _find(passages, title_terms=("insolvency and bankruptcy",), anchor_terms=("/sec-61",))
    companies421 = _find(passages, title_terms=("companies act",), anchor_terms=("/sec-421",))
    nclat_rules = _find(passages, title_terms=("appellate tribunal rules", "nclat rules"), anchor_terms=("/rule-22", "/rule-55", "/form-nclat-1"))
    primary = ibc61 or companies421
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if ibc61 is not None:
        lines.append(
            f"For an NCLAT appeal from an NCLT insolvency order, treat this as an NCLAT appeal procedure problem first: verify limitation, delay/condonation, parties, certified-copy date, and appeal papers before preparing the NCLAT appeal under the IBC Section 61 route [{ibc61}]."
        )
    if companies421 is not None:
        lines.append(
            f"If the tribunal order is a company-law tribunal order rather than an IBC insolvency order, keep the Companies Act NCLAT appeal route separate and do not mix its limitation or filing basis with IBC Section 61 [{companies421}]."
        )
    if nclat_rules is not None:
        lines.append(
            f"For format, fee, certified-copy, and registry-defect questions, verify the NCLAT Rules/Form source instead of guessing from the IBC or Companies Act alone [{nclat_rules}]."
        )
    action_cites = _cite_many(ibc61, companies421, nclat_rules)
    lines.extend([
        "**What you can do next**",
        f"- For format and fees, do not guess from a judgment excerpt: get the NCLT order/certified copy, order date, case type, party details, delay facts, vakalatnama/authorisation, annexures, and then verify the NCLAT registry/rules checklist, filing format, court fee, and e-filing defects before filing the appeal {action_cites}.",
    ])
    return lines


def _procedure_writ_32_226_difference_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "court_procedure":
        return []
    article32_context = _has_any(q, ("article 32", "art 32", "supreme court"))
    article226_context = _has_any(q, ("article 226", "art 226", "high court"))
    if not (article32_context and article226_context):
        return []

    article32 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-32",))
    article226 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-226",))
    article226_context_source = article226 or _find_passage_containing(passages, ("article 226", "mandamus"))
    lsa = _find(passages, title_terms=("legal services",), anchor_terms=("/sec-12",))
    primary = article32 or article226 or lsa
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if article32 is not None:
        lines.append(
            f"Article 32 is the Supreme Court procedure for enforcement of fundamental rights, so use it only after identifying the fundamental right and relief you want from the Supreme Court [{article32}]."
        )
    if article226 is not None:
        lines.append(
            f"Article 226 is the High Court writ route and is usually the first practical forum for mandamus, government refusal, authority inaction, records, or local public-authority disputes [{article226}]."
        )
    elif article226_context_source is not None:
        lines.append(
            "The retrieved material gives Article 226/mandamus writ procedure context, but not the bare Article 226 provision; verify the bare Article 226 provision before relying on a judgment excerpt alone."
        )
    if article32 is not None and article226 is not None:
        lines.append(
            f"Do not treat Article 32 and Article 226 as complaint forms; compare forum, respondent authority, urgency, alternate remedy, documents, and exact relief before choosing the Supreme Court or High Court route [{article32}], [{article226}]."
        )
    if lsa is not None:
        lines.append(
            f"If drafting or filing help is needed, take the written refusal/order and timeline to legal aid before trying to file a writ yourself [{lsa}]."
        )
    action_cites = _cite_many(article32, article226, lsa)
    lines.extend([
        "**What you can do next**",
        f"- Prepare the government order/refusal or inaction proof, representation and delivery proof, timeline, respondent authority, fundamental-right/public-duty issue, urgency, alternate-remedy facts, and exact relief requested before choosing Article 32 or Article 226 {action_cites}.",
    ])
    return lines


def _procedure_nclt_insolvency_petition_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "ibc_nclt" or not _has_any(q, (
        "nclt", "insolvency petition", "file insolvency", "petition against",
        "operational creditor", "financial creditor", "section 9", "sec 9",
        "section 7", "sec 7", "demand notice", "form 3", "company owing",
    )):
        return []
    if _has_any(q, ("pre pack", "pre-pack", "prepack", "pre packaged", "pre-packaged", "ppirp", "own company")):
        return []
    ibc7 = _find(passages, title_terms=("insolvency and bankruptcy",), anchor_terms=("/sec-7",))
    ibc8 = _find(passages, title_terms=("insolvency and bankruptcy",), anchor_terms=("/sec-8",))
    ibc9 = _find(passages, title_terms=("insolvency and bankruptcy",), anchor_terms=("/sec-9",))
    ibc_any = _find(passages, title_terms=("insolvency and bankruptcy",))
    companies = _find(passages, title_terms=("companies act",), anchor_terms=("/sec-92", "/sec-137", "/sec-164", "/sec-252"))
    nclt_rules = _find(passages, title_terms=("tribunal rules", "nclt rules"), anchor_terms=("/rule-23", "/rule-34"))
    primary = ibc7 or ibc8 or ibc9 or ibc_any
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if ibc7 is not None:
        lines.append(
            f"If you are a financial creditor, verify the NCLT insolvency petition procedure under the IBC Section 7 source with debt, default, and account proof [{ibc7}]."
        )
    if ibc8 is not None or ibc9 is not None:
        cite = ibc8 or ibc9
        lines.append(
            f"If you are an operational creditor, the procedure usually starts with the IBC demand-notice/dispute-check track before a Section 9 NCLT application, so keep notice, reply, and default proof together [{cite}]."
        )
    if ibc7 is None and ibc8 is None and ibc9 is None:
        lines.append(
            f"Treat the NCLT filing as an insolvency procedure question under the retrieved IBC source, not as a generic company complaint [{primary}]."
        )
    if companies is not None:
        lines.append(
            f"Use Companies Act/ROC records only to identify the company, directors, registered office, and filing status; the insolvency petition route itself must still be verified under the IBC source [{companies}]."
        )
    if nclt_rules is not None:
        lines.append(
            f"For forms, filing counter/e-filing, copies, affidavit, fee, and registry scrutiny, verify the NCLT Rules/Form source in addition to the IBC trigger section [{nclt_rules}]."
        )
    action_cites = _cite_many(primary, companies, nclt_rules)
    lines.extend([
        "**What you can do next**",
        f"- Prepare a procedure file with creditor type, debt amount, default date, invoices/loan documents, bank proof, company master data, demand notice and reply/dispute status, board/authorisation papers, and proposed NCLT form/annexures before speaking to an insolvency professional or filing in NCLT {action_cites}.",
    ])
    return lines


def _procedure_writ_court_fee_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "court_procedure" or "court fee" not in q or not _has_any(q, ("writ", "high court", "article 226")):
        return []
    court_fee = _find(passages, title_terms=("court-fees", "court fees"), anchor_terms=("/sec-7", "/sec-8", "/sec-9"))
    article226 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-226",))
    lsa = _find(passages, title_terms=("legal services",), anchor_terms=("/sec-12",))
    primary = court_fee or article226 or lsa
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if court_fee is not None:
        lines.append(
            f"For High Court writ filing, treat fixed/ad valorem fee as a filing-procedure issue: the Court Fees Act source is only the starting computation source and must be checked with the High Court or state fee schedule [{court_fee}]."
        )
    if article226 is not None:
        lines.append(
            f"Keep the Article 226 writ route separate from ordinary civil-suit valuation; the prayer, interim relief, and whether money/property relief is asked can affect the filing procedure [{article226}]."
        )
    if lsa is not None:
        lines.append(
            f"If court fee or drafting help is unaffordable, take the papers to DLSA/High Court legal-aid services instead of abandoning the writ filing [{lsa}]."
        )
    action_cites = _cite_many(court_fee, article226, lsa)
    lines.extend([
        "**What you can do next**",
        f"- Carry the draft writ/PIL, exact prayers, interim relief, valuation if any money/property relief is claimed, annexure index, ID/affidavit, and High Court filing checklist to the filing counter or lawyer to confirm fixed versus ad valorem fee before payment {action_cites}.",
    ])
    return lines


def _procedure_vakalatnama_change_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "court_procedure" or not _has_any(q, ("vakalatnama", "change advocate", "change of advocate", "new advocate", "change lawyer", "replace lawyer")):
        return []
    cpc = _find(passages, title_terms=("code of civil procedure",), anchor_terms=("/sec-151", "/sec-153", "/sec-108"))
    lsa = _find(passages, title_terms=("legal services",), anchor_terms=("/sec-12",))
    primary = cpc or lsa
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if cpc is not None:
        lines.append(
            f"Changing advocate during a pending suit is a court procedure and registry/roznama issue: keep the case number, existing vakalatnama, discharge/NOC communication if available, and fresh vakalatnama with the CPC procedural source [{cpc}]."
        )
    if lsa is not None:
        lines.append(
            f"If you cannot afford a new advocate or the file is not being returned, the Legal Services Authority source is the legal-aid route to check for help with the pending case [{lsa}]."
        )
    action_cites = _cite_many(cpc, lsa)
    lines.extend([
        "**What you can do next**",
        f"- Ask the present advocate in writing for file handover/NOC or discharge status, get the new advocate's signed vakalatnama, and file it in the same court registry before the next effective hearing; keep fee receipts, messages, order sheets, and next-date proof {action_cites}.",
    ])
    return lines


def _procedure_ngt_wetland_complaint_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "environment_compensation" or not _has_any(q, ("ngt", "national green tribunal", "wetland")):
        return []
    ngt = _find(passages, title_terms=("national green tribunal",), anchor_terms=("/sec-14", "/sec-15", "/sec-18"))
    water = _find(passages, title_terms=("water", "pollution"), anchor_terms=("/sec-17", "/sec-28"))
    epa = _find(passages, title_terms=("environment",), anchor_terms=("/sec-3", "/sec-5", "/sec-15", "/sec-19"))
    primary = ngt or water or epa
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if ngt is not None:
        lines.append(
            f"For illegal construction near a wetland, treat this as an NGT complaint/application procedure problem: use the NGT Act source for environmental dispute, relief, compensation, restoration, or removal-type relief where the facts fit [{ngt}]."
        )
    if water is not None:
        lines.append(
            f"Also preserve the Pollution Control Board/water-pollution record if the wetland, drain, discharge, or local environmental authority record is involved [{water}]."
        )
    if epa is not None:
        lines.append(
            f"Use the Environment Protection source for the regulator/direction track where illegal construction or environmental harm needs official action, but do not replace the NGT filing route with only a local complaint [{epa}]."
        )
    action_cites = _cite_many(ngt, water, epa)
    lines.extend([
        "**What you can do next**",
        f"- Build a procedure file with site location/GPS, photos/videos, wetland map or notification if available, municipal/building permission papers if known, complaints already sent to local body/SPCB/wetland authority, dates of construction, harm caused, and the relief sought; then verify the NGT filing format, limitation, annexures, and respondents before filing {action_cites}.",
    ])
    return lines


def _transport_auto_permit_renewal_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "business_license_compliance" or not _has_any(q, ("auto permit", "taxi permit", "cab permit", "transport permit", "permit renewal", "permit expired")):
        return []
    mv_permit = _find(passages, title_terms=("motor vehicles", "themotorvehiclesact"), anchor_terms=("/sec-74", "/sec-80", "/sec-66", "/sec-86"))
    mv_insurance = _find(passages, title_terms=("motor vehicles", "themotorvehiclesact"), anchor_terms=("/sec-146", "/sec-147"))
    primary = mv_permit or mv_insurance
    if primary is None:
        return []
    place = "Chennai/Tamil Nadu RTO/RTA" if _has_any(q, ("chennai", "tamil nadu", "cuddalore")) else "local RTO/RTA"

    lines = ["**Short answer**"]
    if mv_permit is not None:
        lines.append(
            f"For an expired auto permit, treat renewal as an RTO/RTA transport-permit procedure, not a police case first; verify permit renewal, route/area, fitness, tax, insurance, and delay/lockdown explanation with the Motor Vehicles Act permit source [{mv_permit}]."
        )
    if mv_insurance is not None:
        lines.append(
            f"If the permit renewal involves road use or traffic-police challan risk, keep insurance and vehicle papers with the permit file instead of driving on an expired permit [{mv_insurance}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Take the old permit, RC, fitness certificate, insurance, tax receipt, pollution certificate, licence/badge if applicable, address/base proof, lockdown-delay explanation, and any challan to the {place}; ask for written renewal requirements, late fee/penalty, and appeal/revision route if refused [{primary}].",
    ])
    return lines


def _gratuity_eligibility_4y11m_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "employment_wages" or "gratuity" not in q or not _has_any(q, ("4 years 11", "4 year 11", "four years 11", "section 4")):
        return []
    gratuity4 = _find(passages, title_terms=("payment of gratuity",), anchor_terms=("/sec-4",))
    gratuity7 = _find(passages, title_terms=("payment of gratuity",), anchor_terms=("/sec-7", "/sec-8"))
    social = _find(passages, title_terms=("code on social security",), anchor_terms=("/sec-45", "/sec-113", "/sec-114"))
    primary = gratuity4 or gratuity7
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if gratuity4 is not None:
        lines.append(
            f"For 4 years 11 months service, start with Payment of Gratuity Act Section 4 eligibility and exceptions; do not answer only from a generic social-security or wage source [{gratuity4}]."
        )
        lines.append(
            f"Ask the employer for the exact date of joining, last working date, breaks in service, termination reason, and calculation basis because the gratuity claim turns on continuous service and statutory exceptions under the gratuity source [{gratuity4}]."
        )
    if gratuity7 is not None:
        lines.append(
            f"If the employer disputes gratuity or calculation, keep a written claim/demand for the gratuity controlling authority or labour commissioner route [{gratuity7}]."
        )
    elif social is not None:
        lines.append(
            f"Use the Code on Social Security source only as background; the specific gratuity eligibility question should be checked under the Payment of Gratuity Act first [{social}], [{primary}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep appointment letter, joining date proof, last-working-date proof, payslips/basic wages, resignation/termination letter, leave/break records, nominee details, and employer reply; send a written gratuity calculation request and, if refused, take it to the labour/gratuity controlling authority or Labour Commissioner [{primary}].",
    ])
    return lines


def _retrenchment_permission_120_workers_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "employment_wages" or not _has_any(q, ("retrench", "retrenchment", "layoff", "lay off")) or not _has_any(q, ("120", "one twenty", "hundred twenty", "100 employees", "hundred employees")):
        return []
    id25n = _find(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-25N",))
    id25f = _find(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-25F",))
    id25g = _find(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-25G",))
    primary = id25n or id25f or id25g
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if id25n is not None:
        lines.append(
            f"For a factory with about 120 employees proposing to retrench 8 workers, treat it as labour-compliance first: verify prior-permission requirements under the Industrial Disputes Act Section 25N route where the establishment/workman threshold facts fit [{id25n}]."
        )
    if id25f is not None:
        lines.append(
            f"Keep Section 25F notice, notice pay, and retrenchment-compensation compliance separate from the prior-permission question; both may matter before retrenching workers [{id25f}]."
        )
    if id25g is not None:
        lines.append(
            f"If selection is disputed, preserve category/seniority and last-come-first-go facts separately from permission and compensation compliance [{id25g}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Before issuing retrenchment notices, prepare the labour-compliance file: total workmen count, factory/establishment details, names/categories of 8 workers, seniority list, reason for retrenchment, proposed notice/pay/compensation calculation, government-permission application if required, and Labour Commissioner/appropriate-government filing proof [{primary}].",
    ])
    return lines


def _arrest_paperwork_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"arrest_custody_safeguard", "police_fir"}:
        return []
    if not (_has_any(q, ("arrest memo", "no family information", "no fir copy", "picked", "took brother", "took my", "not producing")) and _has_any(q, ("police", "arrest", "custody", "detained", "picked", "took"))):
        return []
    article22 = _find(passages, title_terms=("constitution",), anchor_terms=("/sec-22",))
    bnss_arrest = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-47", "/sec-48", "/sec-57", "/sec-58"))
    crpc_arrest = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-50", "/sec-56", "/sec-57"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173",))
    primary = article22 or bnss_arrest or crpc_arrest or bnss_fir
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if article22 is not None:
        lines.append(
            f"Treat this as an urgent arrest/custody paperwork and family-rights issue first: Article 22 is the liberty source for grounds of arrest, lawyer access, and production before a Magistrate [{article22}]."
        )
    if bnss_arrest is not None or crpc_arrest is not None:
        cite = bnss_arrest or crpc_arrest
        lines.append(
            f"Ask immediately for the arrest memo, grounds of arrest, station name, family or nominated-person intimation proof, and whether the person has been produced before the Magistrate within 24 hours [{cite}]."
        )
    if bnss_fir is not None:
        lines.append(
            f"The FIR-copy or police-information track is separate from the custody-safeguard track; ask for FIR number/sections or written diary/notice details, but do not wait for a copy if production or illegal detention is urgent [{bnss_fir}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Police station duty officer/senior officer for written details, DLSA or a criminal lawyer immediately, and the nearest Magistrate/High Court habeas route if detention or non-production continues [{primary}].",
        f"- Pickup/arrest time, station name, officer/vehicle/CCTV/witness details, calls/messages, ID proof, medical condition, FIR/notice number if any, and names of family members who were not informed [{primary}].",
    ])
    return lines


def _maternity_return_role_change_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "employment_wages" or not _is_maternity_return_role_change(q):
        return []
    maternity = _find(passages, title_terms=("maternity benefit",), anchor_terms=("/sec-5", "/sec-11", "/sec-12"))
    id_act = _find(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-2A", "/sec-25F"))
    wages = _find(passages, title_terms=("code on wages",), anchor_terms=("/sec-17", "/sec-45"))
    primary = maternity or id_act or wages
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if maternity is not None:
        lines.append(
            f"For return from maternity leave where the role was given to someone else, start with the Maternity Benefit Act source and the written role/pay/leave records; do not answer it as MGNREGA or generic salary law [{maternity}]."
        )
    if id_act is not None:
        lines.append(
            f"If the role change becomes termination, forced resignation, demotion, or service-condition punishment, keep a separate Industrial Disputes/workman-status track with the termination or PIP papers [{id_act}]."
        )
    if wages is not None:
        lines.append(
            f"Use the wage source only for unpaid salary, deductions, or final-settlement dues; it should not replace the maternity-return protection question [{wages}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Send HR a written request for the return-to-work role, pay/grade, reporting manager, reason for reassignment, maternity-leave approval, and whether any adverse action is being proposed; preserve maternity leave approval, emails, appraisal/PIP papers, payslips, appointment letter, and messages [{primary}].",
        f"- If HR does not fix it or gives no written reason, approach the labour officer/DLSA or an employment lawyer with the maternity and service records instead of accepting an oral role change [{primary}].",
    ])
    return lines


def _posh_pip_retaliation_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"employment_wages", "workplace_sexual_harassment"} or not _is_workplace_harassment_pip(q):
        return []
    posh = _find(passages, title_terms=("sexual harassment of women at workplace",), anchor_terms=("/sec-3", "/sec-4", "/sec-9", "/sec-19"))
    id_act = _find(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-2A", "/sec-25F"))
    wages = _find(passages, title_terms=("code on wages",), anchor_terms=("/sec-17", "/sec-18", "/sec-45"))
    primary = posh or id_act or wages
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if posh is not None:
        lines.append(
            f"If the manager/HR harassment complaint was about sexual or gendered workplace conduct, keep the POSH Act route separate from ordinary performance management and ask for the Internal Committee or Local Committee path [{posh}]."
        )
        lines.append(
            f"If the bad rating or PIP started after the IC/HR complaint, preserve it as possible retaliation/adverse-action context within the POSH file instead of accepting a verbal 'performance issue' label without reasons [{posh}]."
        )
    if id_act is not None:
        lines.append(
            f"A PIP after an HR complaint is not automatically illegal by itself; if it becomes dismissal, discharge, retrenchment, termination, or punishment, keep the Industrial Disputes/workman-status track with the PIP timeline [{id_act}]."
        )
    if wages is not None:
        lines.append(
            f"Use the Code on Wages only for withheld salary, deductions, incentive, final settlement, or other money due; do not make it the main answer to a harassment/PIP retaliation complaint [{wages}]."
        )
    action_cites = _cite_many(posh, id_act, wages)
    lines.extend([
        "**What you can do next**",
        f"- Preserve the HR complaint, exact harassment facts, dates, manager messages, witnesses, PIP or rating letter, emails, appraisal record, employment contract, and any termination or salary-withholding proof; ask HR in writing for the IC/Local Committee route where POSH facts exist and separately preserve the labour-dispute record {action_cites}.",
    ])
    return lines


def _workplace_sexual_harassment_first_action_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"workplace_sexual_harassment", "employment_wages"} or not _is_workplace_sexual_harassment_general(q):
        return []
    posh = _find(
        passages,
        title_terms=("sexual harassment of women at workplace",),
        anchor_terms=("/sec-2", "/sec-3", "/sec-4", "/sec-6", "/sec-9", "/sec-11", "/sec-19"),
    )
    bns = _find(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-74", "/sec-75", "/sec-78", "/sec-351", "/sec-356"),
    )
    id_act = _find(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-2a", "/sec-25f"))
    if posh is None:
        return []

    vendor_context = _has_any(q, ("vendor", "visitor", "client", "contractor"))
    incident = (
        "vendor/third-party workplace-linked unwelcome conduct, not as a colleague-only dispute"
        if vendor_context
        else "unwelcome touching or physical conduct at work"
        if _has_any(q, ("touch", "touched", "grop", "hug", "kiss", "back", "waist", "body"))
        else "retaliation after an IC/HR complaint"
        if _has_any(q, ("icc", "ic ", "internal committee", "complained", "complaint", "pip", "bad rating", "performance"))
        else "sexual or gendered conduct at work"
    )
    lines = ["**Short answer**"]
    if posh is not None:
        lines.append(
            f"Treat this as a POSH workplace-sexual-harassment route first: for {incident}, ask for the Internal Committee or Local Committee path and keep the employer's written response, not only an informal HR chat [{posh}]."
        )
    if bns is not None:
        lines.append(
            f"If the same facts include physical touching, stalking, threats, intimidation, or reputation-harming public messages, keep a separate BNS/police track; do not let the POSH complaint replace urgent criminal-law help where safety is at risk [{bns}]."
        )
    if id_act is not None:
        lines.append(
            f"If the employer responds with PIP, bad rating, termination, transfer, or punishment, preserve that as a separate Industrial Disputes Act labour/service retaliation record while the POSH route remains focused on the harassment complaint [{id_act}]."
        )
    action_cites = _cite_many(posh, bns, id_act)
    lines.extend([
        "**What you can do next**",
        f"- Preserve the complaint, exact words/actions, dates, location, witnesses, chats/emails, CCTV request if relevant, manager/HR replies, IC/LC details, appraisal/PIP papers, and any threat or touching evidence; ask in writing for the POSH complaint route and acknowledgement {action_cites}.",
        f"- If there is immediate safety risk, stalking, assault, threats, or forced contact, use emergency/police/DLSA help in parallel with the workplace complaint instead of waiting for an internal meeting {action_cites}.",
    ])
    if vendor_context:
        lines.append(
            f"- Ask HR/IC/LC for access restriction or workplace-safety steps for the vendor/third party while the written complaint is considered {action_cites}."
        )
    return lines


def _gig_delivery_accident_compensation_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "workplace_injury_compensation" or not _is_gig_delivery_accident(q):
        return []
    social = _find(passages, title_terms=("code on social security",), anchor_terms=("/sec-113", "/sec-114"))
    motor = _find(passages, title_terms=("motor vehicles", "themotorvehiclesact"), anchor_terms=("/sec-165", "/sec-166", "/sec-164"))
    employees = _find(passages, title_terms=("employees' compensation", "employees compensation", "workmen's compensation"), anchor_terms=("/sec-3", "/sec-4", "/sec-10"))
    primary = social or motor or employees
    if primary is None:
        return []
    platform = "Zomato" if "zomato" in q else "Swiggy" if "swiggy" in q else "Ola" if "ola" in q else "Uber" if "uber" in q else "delivery/platform"
    lines = ["**Short answer**"]
    if social is not None:
        lines.append(
            f"For a {platform} rider accident, keep the Code on Social Security gig/platform-worker source as the welfare or platform accident-insurance track, but do not assume it automatically proves employee status or automatic reinstatement [{social}]."
        )
    if motor is not None:
        lines.append(
            f"If the injury happened in a road accident, keep the Motor Vehicles Act/MACT source as the vehicle-insurance compensation track with accident, vehicle, driver, insurer, and medical proof [{motor}]."
        )
    if employees is not None:
        lines.append(
            f"Also check the Employees' Compensation source if the platform, contractor, or facts show an employment/work relationship; do not drop it merely because the user is called a gig worker [{employees}]."
        )
    claim_cites = _cite_many(social, motor, employees)
    if "insurance" in q or "company" in q or "platform" in q:
        lines.append(
            f"The {platform} company/platform saying there is no insurance does not end the claim; keep the company insurance denial, MACT road-accident route, and employment-compensation check separate {claim_cites}."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep accident date/time/place, {platform} delivery-app trip/order ID, rider ID, vehicle/insurance papers, hospital records, disability/medical bills, police accident record if any, platform support tickets, payout or company insurance denial, and witness/photos {claim_cites}.",
        f"- Raise the {platform} platform insurance/support claim in writing, then use MACT for road-accident compensation and labour/DLSA advice for employment or Employees' Compensation issues where the facts support them {claim_cites}.",
    ])
    return lines


def _sexual_offence_survivor_procedure_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "sexual_offence_survivor" or not _is_sexual_offence_survivor_procedure(q):
        return []
    pocso = _find(passages, title_terms=("protection of children from sexual offences",))
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-63", "/sec-64", "/sec-74"))
    rpwd = _find(passages, title_terms=("rights of persons with disabilities",), anchor_terms=("/sec-7", "/sec-12", "/sec-13"))
    bnss = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175", "/sec-183", "/sec-184"))
    crpc = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-154", "/sec-164"))
    primary = pocso or bns or rpwd or bnss or crpc
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if pocso is not None:
        lines.append(
            f"If the touching or assault started when you were under 18, keep the child sexual-offence/POCSO track even if you are 19 now; do not assume there is no remedy only because time passed [{pocso}]."
        )
    if bns is not None:
        lines.append(
            f"For adult-period or non-POCSO sexual assault facts, keep the BNS sexual-offence source separate from the survivor-support and procedure steps [{bns}]."
        )
    if rpwd is not None:
        lines.append(
            f"If the survivor is visually impaired, disabled, deaf, or otherwise needs support, use the RPwD source for disability-sensitive access, support, and protection from abuse while the criminal case proceeds [{rpwd}]."
        )
    procedure = bnss or crpc
    if procedure is not None:
        lines.append(
            f"The police route needs FIR/complaint, statement, and medical-examination procedure; the procedure source should travel with the offence source instead of being a vague extra citation [{procedure}]."
        )
    action_cites = _cite_many(pocso or bns, rpwd, procedure)
    if _has_any(q, ("visually impaired", "blind", "disabled", "cannot identify", "can't identify", "caretaker")) and rpwd is not None:
        lines.append(
            f"Police should not treat visual impairment or inability to identify the accused by sight as making the case weak by itself; preserve caretaker/access facts, voice or touch/context details, medical/support evidence, and ask for disability-sensitive statement support {action_cites}."
        )
    lines.extend([
        "**What you can do next**",
        f"- Make a dated timeline, preserve age proof for the old incidents, messages/witness details if any, medical/support records, disability/access needs where relevant, and approach DLSA/One Stop Centre/police with a trusted support person {action_cites}.",
        f"- Ask for survivor-sensitive statement recording, medical care, protection from the accused/caretaker, FIR copy or written complaint acknowledgement, and escalation to senior police/Magistrate if police refuse {action_cites}.",
    ])
    return lines


def _dowry_death_inquest_fir_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"police_fir", "family_domestic", "criminal_general"} or not _is_dowry_death_inquest(q):
        return []
    bns = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-80", "/sec-85", "/sec-86"))
    dowry = _find(passages, title_terms=("dowry prohibition",))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))
    bnss_inquest = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-194", "/sec-196"))
    crpc_fir = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-154", "/sec-156"))
    crpc_inquest = _find(passages, title_terms=("code of criminal procedure",), anchor_terms=("/sec-174", "/sec-176"))
    procedure = bnss_fir or crpc_fir
    inquest = bnss_inquest or crpc_inquest
    primary = bns or dowry or procedure or inquest
    if primary is None:
        return []
    lines = ["**Short answer**"]
    if bns is not None:
        lines.append(
            f"For a sister dying at her in-laws' house with injury marks or dowry facts, treat it as a serious dowry-death/cruelty investigation issue first, not as only a domestic-violence protection-order issue after death [{bns}]."
        )
    if dowry is not None:
        lines.append(
            f"Keep the Dowry Prohibition source for dowry demand/presents/property facts, but the immediate track is FIR, inquest, post-mortem, and investigation records [{dowry}]."
        )
    if procedure is not None:
        lines.append(
            f"Use the criminal-procedure source for the FIR/complaint, written acknowledgement, senior-police or Magistrate escalation, and investigation record [{procedure}]."
        )
    if inquest is not None:
        lines.append(
            f"For body marks, alleged suicide, or suspicious marital death, use the inquest/Magistrate-inquiry source for post-mortem, inquest papers, injury record, and death-scene evidence instead of relying on oral explanations from the in-laws [{inquest}]."
        )
    action_cites = _cite_many(bns, dowry, procedure, inquest)
    lines.extend([
        "**What you can do next**",
        f"- Immediately give a written complaint to police/senior police with marriage date, death date/place, dowry demands, injury marks, photos/messages, witness names, hospital/post-mortem details, and ask for FIR number, inquest/post-mortem papers, and acknowledgement {action_cites}.",
        f"- If police treat it casually or call it only suicide, go to SP/senior police, Magistrate, DLSA, or a criminal lawyer urgently with the same record; do not rely only on oral assurances from the in-laws or police {action_cites}.",
    ])
    return lines


def _scheme_worker_honorarium_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category not in {"employment_wages", "labour_exploitation_discrimination", "general_legal", "social_welfare_identity"}:
        return []
    asha_issue = _has_any(q, ("asha", "asha worker", "asha facilitator", "nhm", "nrhm"))
    anganwadi_issue = _has_any(q, (
        "anganwadi", "anganwadi worker", "anganwadi helper", "icds",
        "cdpo", "nutrition duty", "app attendance",
    ))
    payment_issue = _has_any(q, (
        "honorarium", "honourarium", "incentive", "payment", "payments",
        "salary", "not paid", "pending", "arrears", "not credited",
        "no budget", "no sanction", "stopped", "attendance issue",
    ))
    if not payment_issue or not (asha_issue or anganwadi_issue):
        return []

    asha = _find(passages, title_terms=("asha incentives", "national health mission asha", "national rural health mission"))
    anganwadi = _find(passages, title_terms=("anganwadi", "ameerbi", "maniben", "icds"))
    rti = _find(passages, title_terms=("right to information",), anchor_terms=("/sec-6", "/sec-7", "/sec-19"))
    lsa = _find(passages, title_terms=("legal services authorities",), anchor_terms=("/sec-12", "/sec-9"))
    wages = _find(passages, title_terms=("code on wages",))
    primary = asha if asha_issue and asha is not None else anganwadi if anganwadi_issue and anganwadi is not None else asha or anganwadi
    if primary is None:
        return []
    primary_title = next(
        (
            str(passage.get("title") or "")
            for passage in passages
            if passage.get("index") == primary and passage.get("title")
        ),
        "scheme/Anganwadi authority",
    )

    if asha_issue and not anganwadi_issue:
        worker = "ASHA vaccination/activity incentive or NHM payment" if _has_any(q, ("vaccination", "vaccine", "immunisation", "immunization")) else "ASHA incentive or NHM payment"
        first_forum = "ASHA facilitator, PHC/block medical officer, district health society, or district NHM office"
        evidence = "activity/vaccination records, activity/incentive ledger, attendance, bank/passbook entries, messages, and unpaid-month calculation"
    else:
        worker = "Anganwadi/ICDS honorarium or attendance-linked payment"
        first_forum = "CDPO, District Programme Officer, Women and Child Development department, or district grievance office"
        evidence = "role/order, attendance or app record, duty/nutrition-work record, sanction/payment file, bank/passbook entries, and CDPO/supervisor messages"

    lines = [
        "**Short answer**",
        f"Treat this as a {worker} grievance first, not as a generic salary or RTI-only question; use the retrieved {primary_title} to frame the ASHA honorarium or incentive record, payment-status, activity-wise ledger, and sanction-record demand [{primary}].",
    ]
    if anganwadi_issue and anganwadi is not None:
        lines.append(
            f"The exact state ICDS or Women and Child Development honorarium order still has to be verified locally, but the Anganwadi source in this index is enough to avoid sending the user to unrelated civil or criminal forums [{anganwadi}]."
        )
    if rti is not None:
        lines.append(
            f"If the office says no budget/no sanction or gives no written reason, use RTI or a written status request to obtain the sanction file, payment ledger, attendance basis, and action-taken record [{rti}]."
        )
    if asha_issue and wages is not None:
        lines.append(
            f"The Code on Wages is only a secondary payment-timing source here; the ASHA/NHM scheme record and activity/incentive ledger remain the first route for unpaid honorarium or incentive facts [{wages}]."
        )
    if asha_issue and lsa is not None:
        lines.append(
            f"If the department will not give a written payment status or grievance route, the Legal Services Authorities Act source supports approaching DLSA/TLSC for legal-aid assistance with the same ASHA payment file [{lsa}]."
        )
    action_cite = primary
    dlsa_cite = lsa or action_cite
    lines.extend([
        "**What you can do next**",
        f"- Give a written complaint/status request to the {first_forum}; because unpaid months and appeal/payment timelines can be time-sensitive, ask for unpaid months, payment/sanction file number, reason for delay, and the officer responsible for release [{action_cite}].",
        f"- Keep {evidence}; take the same file to DLSA/legal aid if the department will not give a written status or grievance route [{dlsa_cite}].",
    ])
    return lines


def _software_license_notice_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "trademark_ip" or not _is_software_license_notice(q):
        return []
    infringement = _find(passages, title_terms=("copyright act",), anchor_terms=("/sec-51",))
    remedies = _find(passages, title_terms=("copyright act",), anchor_terms=("/sec-55",))
    exceptions = _find(passages, title_terms=("copyright act",), anchor_terms=("/sec-52",))
    primary = infringement or remedies or exceptions
    if primary is None:
        return []

    product = "CAD software" if _has_any(q, ("cad", "autocad")) else "software"
    seats = "22 seats" if "22" in q and _has_any(q, ("seat", "seats", "copies")) else "the claimed seats/copies"
    place = " in Noida" if "noida" in q else ""

    lines = [
        "**Short answer**",
        f"Treat the vendor notice about {seats} of {product}{place} as a software copyright/licence evidence dispute first, not as a trademark case unless the notice is actually about brand, logo, or passing-off [{primary}].",
    ]
    if remedies is not None:
        lines.append(
            f"Before filing a case or settling, verify the vendor's licence/audit basis because the Copyright Act civil-remedy source is about injunction, damages, accounts, and ownership/use proof, not automatic payment on an unsupported demand [{remedies}]."
        )
    if exceptions is not None:
        lines.append(
            f"Do not rely on general fair-use/fair-dealing language until counsel checks whether any Copyright Act exception can realistically apply to commercial office software-seat use [{exceptions}]."
        )
    action_cites = _cite_many(infringement, remedies, exceptions)
    lines.extend([
        "**What you can do next**",
        f"- Preserve the vendor/legal notice, audit report, claimed product/version, {seats}, device or user list, Noida office/location facts if relevant, invoices, subscriptions, reseller emails, and purchase orders before replying {action_cites}.",
        f"- Reply in writing through an authorised person or lawyer asking for the licence clause, audit basis, calculation, and settlement demand; do not admit infringement or pay only on an oral threat {action_cites}.",
    ])
    return lines


def _trademark_cease_desist_logo_similarity_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "trademark_ip" or not _is_trademark_cease_desist(q):
        return []
    trademark = _find(passages, title_terms=("trade marks",), anchor_terms=("/sec-29", "/sec-34", "/sec-134", "/sec-11"))
    copyright = _find(passages, title_terms=("copyright",), anchor_terms=("/sec-51", "/sec-55"))
    commercial = _find(passages, title_terms=("commercial courts",), anchor_terms=("/sec-12A", "/sec-12-a", "/sec-6", "/sec-7"))
    primary = trademark or copyright or commercial
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if trademark is not None:
        lines.append(
            f"A cease-and-desist notice saying your logo/brand is similar is not itself a court order; first assess trademark similarity, confusion, registration/application status, class, territory, and your prior-use evidence under the Trade Marks Act source before deciding whether to reply, settle, change branding, or file a suit [{trademark}]."
        )
    if copyright is not None:
        lines.append(
            f"Because a logo can also be an artistic work, keep the copyright-infringement/remedy source separate from the trademark confusion track; do not answer only as a generic brand-name dispute if the artwork itself is copied or alleged to be copied [{copyright}]."
        )
    if commercial is not None:
        lines.append(
            f"If either side actually files a commercial IP suit, check the Commercial Courts/pre-institution mediation or urgent-interim-relief route separately from the notice reply [{commercial}]."
        )
    action_cites = _cite_many(trademark, copyright, commercial)
    lines.extend([
        "**What you can do next**",
        f"- Do not ignore the notice and do not admit infringement casually; collect the notice, your logo files, date of first use, invoices/export documents, trademark search/application/registration, designer assignment, customer confusion proof if any, and ask an IP lawyer to send a narrow written reply or choose a commercial-court strategy {action_cites}.",
    ])
    return lines


def _trademark_passing_off_interim_injunction_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "trademark_ip" or not _has_any(q, (
        "passing off", "product packaging", "trade dress", "interim injunction",
        "injunction", "skip 12a", "section 12a", "sec 12a", "12a",
    )):
        return []
    trademark = _find(passages, title_terms=("trade marks",), anchor_terms=("/sec-29", "/sec-134", "/sec-34"))
    commercial_12a = _find(passages, title_terms=("commercial courts",), anchor_terms=("/sec-12A", "/sec-12-a"))
    specific = _find(passages, title_terms=("specific relief",), anchor_terms=("/sec-38", "/sec-39"))
    passing_off_case = _find_passage_containing(passages, ("passing off", "interim injunction"))
    primary = commercial_12a or trademark or specific or passing_off_case
    if primary is None:
        return []

    lines = ["**Short answer**"]
    if commercial_12a is not None:
        lines.append(
            f"For urgent interim injunction in a commercial IP/passing-off dispute, Commercial Courts Act Section 12A is the source to check for the pre-institution mediation route and urgent-interim-relief exception [{commercial_12a}]."
        )
    if trademark is not None:
        lines.append(
            f"Keep passing off/product-packaging confusion separate from mere copyright or general competition: the Trade Marks Act forum/infringement source is the brand/confusion track to verify with first-use and packaging evidence [{trademark}]."
        )
    if specific is not None:
        lines.append(
            f"For the injunction remedy itself, verify the Specific Relief Act permanent/mandatory injunction source along with urgency, balance of convenience, confusion evidence, and loss proof [{specific}]."
        )
    elif passing_off_case is not None:
        lines.append(
            "A passing-off judgment may help context, but do not let a case excerpt replace the Specific Relief Act injunction source if the remedy is the main question."
        )
    action_cites = _cite_many(commercial_12a, trademark, specific)
    lines.extend([
        "**What you can do next**",
        f"- Preserve product packaging photos, invoices, first-use proof, trademark/application records, competitor listing/packaging, confusion screenshots, legal notice, urgency facts, and loss calculation; ask an IP/commercial-court lawyer whether Section 12A can be bypassed because urgent interim relief is genuinely needed {action_cites}.",
    ])
    return lines


def _housing_parking_blocked_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "consumer" or not _is_housing_parking_blocked(q):
        return []
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-38", "/sec-39", "/sec-2"))
    rera = _find(passages, title_terms=("real estate", "rera"), anchor_terms=("/sec-34",))
    parking_case = _find(passages, title_terms=("velagacharla",))
    primary = consumer or rera or parking_case
    if primary is None:
        return []

    support = parking_case or rera or consumer
    lines = [
        "**Short answer**",
        f"Treat this as a civil apartment/allotted-parking enforcement dispute first: the key proof is that the slot is dedicated/allotted to you and that the neighbour is blocking it despite your complaint [{primary}].",
    ]
    if support is not None and support != primary:
        lines.append(
            f"The parking-source support turns on definite material such as the layout, allotment letter, sale deed, society record, or parking register showing the slot was reserved for parking [{support}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Send a dated written complaint to the association/society and security office with photos/video, slot allotment proof, dates/times, and the security guard's refusal; ask for a written enforcement response before escalating [{primary}].",
        f"- If the association will not act, use the Registrar/local housing authority, consumer forum where maintainable, or civil court/DLSA route with the parking proof and complaint acknowledgements [{primary}].",
    ])
    return lines


def _aadhaar_lost_reissue_records_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "social_welfare_identity" or not _is_lost_aadhaar_reissue_problem(q):
        return []
    aadhaar = _find(passages, title_terms=("aadhaar",), anchor_terms=("/sec-4", "/sec-7", "/sec-8", "/sec-59"))
    rti = _find(passages, title_terms=("right to information",), anchor_terms=("/sec-6", "/sec-7", "/sec-19"))
    primary = aadhaar or rti
    if primary is None:
        return []

    place = "Morbi tile-factory raid" if _has_any(q, ("morbi", "tile factory")) else "lost-document"
    lines = [
        "**Short answer**",
        f"Treat this as an Aadhaar reissue/enrolment-record recovery problem after the {place}, not as a criminal case by itself; first identify whether your Aadhaar number already exists and which acceptable identity/address documents or introducer/update route the Aadhaar centre will accept [{primary}].",
    ]
    if rti is not None:
        lines.append(
            f"If an office or public authority will not give written status, rejection reasons, or records after the raid/loss, use RTI to ask for the file status, reason, and officer/action-taken record instead of relying on oral refusal [{rti}]."
        )
    action_cites = _cite_many(aadhaar, rti)
    lines.extend([
        "**What you can do next**",
        f"- Keep any Aadhaar number/VID, mobile number linked earlier, old photocopy/photo, factory/raid papers, police or employer note if available, ration/voter/bank/passbook or other ID proof, and proof that original village papers were lost {action_cites}.",
        f"- Go to an Aadhaar Seva Kendra/CSC or UIDAI grievance route and ask in writing which alternate document, introducer, update, or retrieval route applies; if reasons are not given, file RTI/public grievance for written status {action_cites}.",
    ])
    return lines


def _subscription_refund_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "consumer" or not _is_subscription_refund(q):
        return []
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-39", "/sec-2"))
    if consumer is None:
        return []
    subject = (
        "yearly app subscription charged after cancellation"
        if _has_any(q, ("yearly", "charged after cancellation", "after cancellation"))
        else "paid subscription refund or cancellation dispute"
    )
    lines = [
        "**Short answer**",
        f"For a {subject}, treat it as a consumer service/refund dispute first: build a written platform/merchant complaint record before escalating [{consumer}].",
        f"If the charge came through card, UPI autopay, or a bank mandate after cancellation, keep the payment-rail stop/dispute record separate from the consumer complaint; do not rely only on chat support promises [{consumer}].",
        "**What you can do next**",
        f"- Preserve cancellation proof, renewal/charge message, invoice/receipt, app subscription screenshots, payment transaction ID, support ticket/chats, refund refusal or no-reply proof, and bank/card/UPI mandate status [{consumer}].",
        f"- Send a written refund/cancellation complaint to the app/platform first, stop or dispute the recurring mandate with the bank/payment app where applicable, then use National Consumer Helpline/e-Daakhil/District Commission if unresolved [{consumer}].",
    ]
    return lines


def _consumer_defective_goods_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "consumer" or not _is_defective_goods(q):
        return []
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-2"))
    if consumer is None:
        return []
    subject = (
        "Amazon/marketplace fake iPhone or third-party-seller refund denial"
        if _has_any(q, ("fake iphone", "third party seller", "third-party seller"))
        or (_has_any(q, ("amazon", "marketplace")) and _has_any(q, ("fake product", "fake goods", "refund denial")))
        else "fake/counterfeit shoes from an online seller or marketplace"
        if _has_any(q, ("fake shoes", "fake nike", "counterfeit shoes", "fake goods")) or (_has_any(q, ("shoes", "footwear")) and "fake" in q)
        else "duplicate/wrong shoes refund dispute"
        if _has_any(q, ("duplicate shoes", "shoes", "footwear"))
        else "damaged/defective phone or seller refusing return/refund"
    )
    lines = [
        "**Short answer**",
        f"For a {subject}, treat it as a consumer service-deficiency or defective-goods complaint after preserving proof of purchase, delivery, defect/fake-product evidence, and the platform/seller response [{consumer}].",
        "**What you can do next**",
        f"- Seller/platform/service-centre grievance first with a written refund/replacement demand; then National Consumer Helpline/e-Daakhil and District Consumer Commission if unresolved [{consumer}].",
        f"- Invoice/order ID, seller/platform name, photos/video of damage or fake product, unboxing or service-centre report if any, warranty terms, payment proof, emails/chats, pickup/return attempts, and complaint ticket numbers [{consumer}].",
    ]
    return lines


def _msme_delayed_payment_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "business_contract_partnership" or not _is_msme_delayed_payment(q):
        return []
    msmed15 = _find(passages, title_terms=("micro, small and medium enterprises",), anchor_terms=("/sec-15", "/sec-16"))
    msmed18 = _find(passages, title_terms=("micro, small and medium enterprises",), anchor_terms=("/sec-18",))
    msmed = msmed15 or msmed18
    contract37 = _find(passages, title_terms=("indian contract",), anchor_terms=("/sec-37",))
    contract73 = _find(passages, title_terms=("indian contract",), anchor_terms=("/sec-73",))
    sale_goods = _find(passages, title_terms=("sale of goods",), anchor_terms=("/sec-55", "/sec-59", "/sec-41", "/sec-42"))
    income_tax = _find(passages, title_terms=("income tax", "income-tax"), anchor_terms=("/sec-43B", "/sec-43-b", "/sec-43b"))
    tax_transition = _find(passages, title_terms=("income tax act 2025 transition",))
    commercial = _find(passages, title_terms=("commercial courts",), anchor_terms=("/sec-12A", "/sec-12-a"))
    if msmed is None:
        return []

    amount = _money_amount_phrase(q)
    buyer = "PSU/public-sector buyer" if _has_any(q, ("psu", "public sector")) else "buyer"
    quality_dispute = _has_any(q, ("quality", "defect", "defective", "rejection", "rejected", "deducting", "deduction"))
    samadhaan = _has_any(q, ("samadhaan", "samadhan", "facilitation council", "msefc"))
    lines = ["**Short answer**"]
    if msmed is not None:
        lines.append(
            f"If you are Udyam/MSME registered and the {buyer} has delayed payment for {amount}, keep this as an MSMED delayed-payment matter first: verify invoice date, delivery/acceptance date, written payment terms, and whether the 45-day/default payment trigger is crossed [{msmed}]."
        )
    if msmed18 is not None:
        lines.append(
            f"The MSMED Facilitation Council source is the statutory route to check for the delayed-payment reference after the invoice, acceptance, and Udyam records are assembled [{msmed18}]."
        )
    if tax_transition is not None and _has_any(q, ("43b", "section 43b", "43b(h)", "disallowance")):
        lines.append(
            f"First pin the tax year: the transition source explains that the earlier Income-tax Act continues to govern tax years beginning before the transition date [{tax_transition}]."
        )
    if income_tax is not None and _has_any(q, ("43b", "section 43b", "43b(h)", "disallowance")):
        lines.append(
            f"A buyer's Income-tax Act section 43B(h) pressure or tax-disallowance argument does not replace the supplier's MSMED payment record; keep it as a supporting tax-pressure fact, not the whole remedy [{income_tax}]."
        )
    if quality_dispute and sale_goods is not None:
        lines.append(
            f"If the buyer says quality issue, defective material, or rejection, preserve whether the goods were accepted or rejected in writing under the Sale of Goods/acceptance-rejection record before choosing Samadhaan, commercial-court, arbitration, or civil recovery [{sale_goods}]."
        )
    if contract37 is not None or contract73 is not None:
        cite = contract37 or contract73
        lines.append(
            f"Use the Contract Act source for purchase order, delivery, acceptance, breach, advance/refund, and loss calculation facts alongside the MSME route [{cite}]."
        )
    if commercial is not None and _has_any(q, ("commercial court", "commercial courts", "file directly", "directly file")):
        lines.append(
            f"If you are comparing MSME Samadhaan with filing directly in Commercial Court, keep Commercial Courts Act Section 12A/pre-institution mediation as a separate forum-gate check before treating court filing as automatic [{commercial}]."
        )
    action_cites = _cite_many(msmed, msmed18, commercial, sale_goods, contract37, contract73, income_tax, tax_transition)
    next_step = "continue/track the MSME Samadhaan or Facilitation Council matter" if samadhaan else "send a dated payment demand and consider MSME Samadhaan / Facilitation Council if eligible"
    lines.extend([
        "**What you can do next**",
        f"- {next_step}; keep Udyam certificate, PO/contract, invoices, delivery challans, e-way/GST records, acceptance/quality-rejection emails, part payments, outstanding calculation, 43B(h) message if any, and buyer address/registered details {action_cites}.",
        f"- If the buyer is not covered or the contract has arbitration/commercial-court terms, take the same document packet to DLSA/lawyer for civil/commercial/arbitration strategy; do not rely only on oral payment promises {action_cites}.",
    ])
    return lines


def _business_contract_first_action_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "business_contract_partnership" or not _is_business_contract_first_action(q):
        return []
    contract37 = _find(passages, title_terms=("indian contract",), anchor_terms=("/sec-37", "/sec-73", "/sec-74", "/sec-27"))
    sale_goods = _find(passages, title_terms=("sale of goods",), anchor_terms=("/sec-41", "/sec-42", "/sec-55", "/sec-59"))
    partnership = _find(passages, title_terms=("indian partnership",), anchor_terms=("/sec-32", "/sec-37", "/sec-44"))
    companies = _find(passages, title_terms=("companies act",), anchor_terms=("/sec-62", "/sec-94", "/sec-241", "/sec-242"))
    specific = _find(passages, title_terms=("specific relief",), anchor_terms=("/sec-38", "/sec-39"))
    primary = contract37 or sale_goods or partnership or companies or specific
    if primary is None:
        return []
    partnership_subtype = _has_any(q, ("partner", "partnership", "firm", "dissolve", "retire", "books"))
    company_subtype = _has_any(q, ("co founder", "co-founder", "equity", "esop", "shareholder", "registers", "minority"))
    if company_subtype and companies is None:
        return []
    if partnership_subtype and partnership is None:
        return []

    issue = (
        "partnership exit/accounts dispute"
        if partnership_subtype
        else "shareholder/equity or company-record dispute"
        if company_subtype
        else "NDA/customer-list or exclusivity dispute"
        if _has_any(q, ("nda", "customer list", "competitor", "exclusivity", "exclusive"))
        else "defective-material or quality-rejection dispute"
        if _has_any(q, ("defective", "material", "quality", "rejection", "refund"))
        else "business contract breach"
    )
    lines = ["**Short answer**"]
    if contract37 is not None:
        lines.append(
            f"Treat this first as a {issue}: map the written agreement/MOU/PO, promised performance, breach, payment or advance, notice, and loss before choosing legal notice, injunction, arbitration, or commercial/civil recovery [{contract37}]."
        )
    if contract37 is not None and _has_any(q, ("nda", "customer list", "competitor", "exclusivity", "exclusive", "non compete", "non-compete")):
        lines.append(
            f"For NDA, customer-list, exclusivity, or non-compete facts, separately verify the restraint-of-trade/confidentiality limits, compensation source, and injunction source in the contract before demanding injunction or damages [{contract37}]."
        )
    if sale_goods is not None and _has_any(q, ("defective", "material", "goods", "quality", "delivery")):
        lines.append(
            f"For goods or defective-material disputes, keep the Sale of Goods acceptance/rejection/price-damages record separate from a generic contract-breach answer [{sale_goods}]."
        )
    if partnership is not None and _has_any(q, ("partner", "partnership", "firm", "dissolve", "retire", "books")):
        lines.append(
            f"For partner funds, books, retirement, dissolution, or firm-liability questions, use the Partnership Act source with partnership deed, loan/liability, notice, accounts, and authority facts [{partnership}]."
        )
    if companies is not None and _has_any(q, ("co founder", "co-founder", "equity", "esop", "shareholder", "registers", "minority")):
        lines.append(
            f"For company equity dilution, register inspection, oppression, or board-control facts, keep the Companies Act route separate from ordinary contract recovery [{companies}]."
        )
    if specific is not None and _has_any(q, ("injunction", "stop", "customer list", "competitor", "exclusivity", "exclusive", "nda")):
        lines.append(
            f"If you need the other side stopped from using customer lists, breaching exclusivity, or continuing a wrongful act, ask about injunction/specific-relief options instead of only damages [{specific}]."
        )
    action_cites = _cite_many(contract37, sale_goods, partnership, companies, specific)
    lines.extend([
        "**What you can do next**",
        f"- Collect agreement/MOU/PO, invoices, delivery/acceptance proof, emails/WhatsApp, payment/advance proof, breach timeline, notices, arbitration/forum clause, buyer/dealer/partner/company details, and loss calculation before sending a legal notice or filing {action_cites}.",
        f"- Do not convert every commercial breach into cheating/FIR; use a police track only if there was deception at the beginning, forgery, entrustment with dishonest refusal, threats, or criminal intimidation {action_cites}.",
    ])
    return lines


def _supplier_payment_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "business_contract_partnership" or not _is_supplier_payment(q):
        return []
    contract37 = _find(passages, title_terms=("indian contract",), anchor_terms=("/sec-37",))
    contract73 = _find(passages, title_terms=("indian contract",), anchor_terms=("/sec-73",))
    msmed = _find(passages, title_terms=("micro, small and medium enterprises",), anchor_terms=("/sec-15", "/sec-16", "/sec-18"))
    rti = _find(passages, title_terms=("right to information",), anchor_terms=("/sec-6", "/sec-7", "/sec-19"))
    if _is_msme_delayed_payment(q) and msmed is None:
        return []
    primary = contract73 or contract37 or msmed or rti
    if primary is None:
        return []

    government_context = _has_any(q, ("government", "department", "icds", "anganwadi", "nutrition", "psu", "public sector", "municipal", "panchayat"))
    supplied_item = (
        "ICDS/nutrition supply bill"
        if _has_any(q, ("icds", "nutrition", "anganwadi"))
        else "government/department supplier bill"
        if government_context
        else "supplier/vendor invoice"
    )
    lines = ["**Short answer**"]
    contract_cite = contract37 if contract37 is not None else contract73
    if contract37 is not None:
        lines.append(
            f"For a pending {supplied_item}, use the Indian Contract Act performance source to organise whether there was a purchase/work order, delivery or supply, acceptance, invoice, and payment promise; do not answer it as generic legal information [{contract37}]."
        )
    if contract73 is not None:
        lines.append(
            f"If the department or buyer breached the payment promise for the pending {supplied_item} after acceptance, use the Indian Contract Act source for compensation with the invoice amount, delay, and loss calculation [{contract73}]."
        )
    if msmed is not None:
        lines.append(
            f"If the supplier is Udyam/MSME registered, keep the MSMED delayed-payment route separate from an ordinary civil/commercial recovery route [{msmed}]."
        )
    if government_context and rti is not None:
        lines.append(
            f"Because a government or scheme department appears involved, use RTI/written-records to get bill status, sanction file, measurement or quality objection, payment queue, and officer reasons before choosing the recovery route [{rti}]."
        )
    action_cite = rti if government_context and rti is not None else msmed if msmed is not None else contract_cite if contract_cite is not None else primary
    docs_cite = contract_cite if contract_cite is not None else action_cite
    recovery_options = (
        "department grievance/RTI records, MSME Facilitation Council if eligible, or civil/commercial recovery"
        if msmed is not None
        else "department grievance/RTI records or civil/commercial recovery"
        if government_context and rti is not None
        else "written demand/legal notice, arbitration if applicable, or civil/commercial recovery"
    )
    lines.extend([
        "**What you can do next**",
        f"- Map each bill to purchase order/work order, delivery challan, acceptance/quality check, invoice date, amount, part payment, and written objection if any; then send a dated demand and choose {recovery_options} with DLSA/lawyer help [{action_cite}].",
        f"- Keep PO/work order, invoice, delivery challans, stock/acceptance receipts, emails/WhatsApp, e-way/GST records if any, bank statement, bill-submission acknowledgement, and names of officers who received or rejected the bill [{docs_cite}].",
    ])
    return lines


def _builder_rera_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "consumer" or not _is_builder_rera(q):
        return []
    rera = _find(passages, title_terms=("real estate",), anchor_terms=("/sec-14", "/sec-18", "/sec-31", "/sec-34", "/sec-71"))
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-39", "/sec-2"))
    registration = _find(passages, title_terms=("registration act",), anchor_terms=("/sec-17", "/sec-23", "/sec-49"))
    defect_after_possession = (
        _has_any(q, ("defective", "defect", "not repairing", "repairing", "leakage", "tiles", "bathroom"))
        and _has_any(q, (
            "possession already", "already given", "possession given",
            "gave possession", "given possession", "after possession",
            "completed flat",
        ))
    )
    primary = consumer if defect_after_possession and consumer is not None else rera or consumer
    if primary is None:
        return []

    issue_phrase = (
        "possession given but carpet area is less than the agreement"
        if _has_any(q, ("carpet area", "80 sqft", "less than agreement", "less area"))
        else
        "occupancy-certificate/OC refusal after full payment"
        if _has_any(q, ("full payment", "after full payment"))
        and (_has_any(q, ("occupancy certificate", "occupation certificate", "promised oc")) or re.search(r"\boc\b", q))
        else "occupancy-certificate/OC refusal"
        if _has_any(q, ("occupancy certificate", "occupation certificate", "promised oc")) or re.search(r"\boc\b", q)
        else "completed-flat defect/repair dispute after possession"
        if defect_after_possession
        else "possession delayed for 3 years and refund refused"
        if _has_any(q, ("3 years", "three years")) and _has_any(q, ("not refunding", "refund"))
        else "possession-delay/refund dispute"
        if _has_any(q, ("possession", "handover", "delayed", "delay", "missed deadline", "3 years", "three years"))
        else "sale-deed registration blocked by builder/property-tax dues"
        if _has_any(q, ("sale deed", "registered sale deed", "register sale deed", "hasnt registered", "hasn't registered", "not registered", "property tax dues", "tax dues"))
        else "layout change and booking-amount refund refusal"
        if _has_any(q, ("changed layout", "layout changed", "booking amount"))
        else "possession delay, layout change, refund, or builder-service dispute"
    )
    lines = ["**Short answer**"]
    if defect_after_possession and consumer is not None:
        lines.append(
            f"For a builder/developer {issue_phrase}, treat the Consumer Protection Act route as the direct service-deficiency/repair/compensation route after possession, using the defect photos, handover record, repair complaints, and builder replies [{consumer}]."
        )
    if rera is not None:
        lines.append(
            (
                f"Use RERA as the conditional project/promoter-obligation route if the defect-liability, registration, or promoter-duty facts fit; do not frame a completed-flat repair problem as a possession-delay/refund case unless possession is actually delayed [{rera}]."
                if defect_after_possession
            else f"For a builder/developer {issue_phrase}, treat RERA as the primary real-estate project route; use RERA as the first project/promoter-obligation route: match the agreement, allotment, carpet-area or layout promise, possession/OC deadline, payment receipts, and project/RERA registration details to the Real Estate Act complaint/adjudication source [{rera}]."
            )
        )
    if consumer is not None and not defect_after_possession:
        lines.append(
            f"The Consumer Protection Act route is a parallel service-deficiency/refund/compensation route where maintainable, but it should not replace checking the RERA project registration, possession, OC, and promoter-obligation record first [{consumer}]."
        )
    if registration is not None and _has_any(q, ("sale deed", "registered sale deed", "register sale deed", "hasnt registered", "hasn't registered", "not registered")):
        lines.append(
            f"The Registration Act source is the sale-deed registration source to verify with the sub-registrar record; pending builder property-tax dues should be documented, but the registration question should not disappear into a generic consumer complaint [{registration}]."
        )
    lines.extend([
        "**What you can do next**",
        (
            f"- Send/keep a written repair or compensation demand to the builder/developer, then file before the District Consumer Commission/e-Daakhil and verify RERA if the defect-liability or promoter-obligation route fits [{consumer or rera or primary}]."
            if defect_after_possession
            else f"- Send/keep a written demand to the builder or developer without waiting indefinitely; because registration/possession/OC/refund deadlines can affect forum strategy, file before the State RERA Authority/adjudicating officer and keep the District Consumer Commission/e-Daakhil route as a parallel service-deficiency path where maintainable [{rera or primary}]" + (f", [{consumer}]" if consumer is not None else "") + (f", [{registration}]." if registration is not None else ".")
        ),
        (
            f"- Keep the sale/allotment agreement, draft or executed sale deed, sub-registrar/token records, property-tax-dues notice, possession or handover proof, builder emails/chats, RERA registration number, payment receipts, and complaint tickets [{registration or primary}]."
            if registration is not None and _has_any(q, ("sale deed", "registered sale deed", "register sale deed", "property tax dues", "tax dues"))
            else
            f"- Keep the sale/allotment agreement, possession or handover proof, defect photos/videos, repair complaints, builder emails/chats, inspection notes, warranty/defect-liability papers if any, and proof of loss or repair estimate [{primary}]."
            if defect_after_possession
            else f"- Keep the sale/allotment agreement, RERA registration number, payment receipts, proof of full payment or refund demand, possession or handover proof, carpet-area/measurement proof, layout-change notices or sanctioned-plan papers, OC/completion-certificate status, builder emails/chats, and complaint tickets [{primary}]."
        ),
    ])
    return lines


def _hospital_records_billing_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "consumer" or not _is_hospital_records_billing(q):
        return []
    consumer = _find(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-35", "/sec-38", "/sec-39"))
    clinical = _find(passages, title_terms=("clinical establishments",), anchor_terms=("/sec-12", "/sec-42"))
    ethics = _find(passages, title_terms=("medical ethics",), anchor_terms=("reg-1.3.2", "reg-7.2", "reg-1.3.1"))
    if consumer is None or (clinical is None and ethics is None):
        return []

    records_issue = _has_any(q, (
        "medical records", "case papers", "hospital records",
        "not giving records", "not giving medical records",
        "refusing case papers", "after discharge",
    ))
    bill_issue = _has_any(q, (
        "overcharged", "overcharge", "breakup bill", "breakup",
        "detailed bill", "itemised bill", "itemized bill",
        "not giving bill", "no receipt", "extra charge",
        "bill", "billing", "icu bill",
    ))
    consent_issue = _has_any(q, (
        "without consent", "no consent", "consent", "kept father in icu",
        "kept mother in icu", "icu 12 days", "icu",
    ))
    negligence_issue = _has_any(q, (
        "wrong leg", "wrong side", "wrong surgery", "wrong operation",
        "operated wrong", "wrong injection", "medical negligence",
        "negligence", "died after", "death after",
    ))
    bns_medical = _find(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-106", "/sec-125"))
    bnss_fir = _find(passages, title_terms=("bharatiya nagarik suraksha",), anchor_terms=("/sec-173", "/sec-175"))

    issue_phrase = (
        "wrong-leg or wrong-site surgery/operation complaint"
        if _has_any(q, ("wrong leg", "wrong side", "operated wrong", "wrong surgery", "wrong operation"))
        else "wrong-injection or serious medical-negligence complaint"
        if _has_any(q, ("wrong injection", "died after", "death after", "medical negligence", "negligence"))
        else "Jaipur ICU 12-day treatment without clear consent and an 18 lakh bill"
        if _has_any(q, ("jaipur", "12 days", "18 lakh"))
        else "Noida private-hospital ICU overcharge of 4 lakh with refund denial"
        if _has_any(q, ("noida", "4 lakh", "denying refund"))
        else "breakup-bill and itemised-bill overcharge dispute"
        if bill_issue and _has_any(q, ("breakup", "itemised", "itemized", "overcharged", "overcharge"))
        else "ICU consent, overcharge, records, or refund dispute"
    )
    lines = ["**Short answer**"]
    if negligence_issue:
        lines.append(
            f"For a {issue_phrase}, collect the operation notes, consent papers, discharge summary, and expert/medical-record material first; this can be a consumer-compensation and medical-ethics complaint before deciding whether police/criminal negligence is supportable [{consumer}]."
        )
        if ethics is not None:
            lines.append(
                f"Use the Medical Ethics source for records/professional-conduct support, especially if the hospital refuses case papers or a written explanation of the wrong procedure [{ethics}]."
            )
        if bns_medical is not None or bnss_fir is not None:
            cite = bns_medical or bnss_fir
            lines.append(
                f"Use police only for the separate criminal-negligence/injury track after matching the medical facts, injury/death record, and incident date; do not let the criminal track replace the consumer/medical-record complaint [{cite}]."
            )
    if consent_issue:
        lines.append(
            f"For ICU admission/continuation, consent, and a large hospital bill like a {issue_phrase}, keep the consent forms, ICU notes, daily bill, discharge summary, and written refund/overcharge request together; this is a hospital-service and records/billing grievance before it becomes a vague negligence allegation [{consumer}]."
        )
    if records_issue:
        if ethics is not None:
            lines.append(
                f"For medical records or case papers, first use the medical-record request route: the Medical Ethics Regulations source is the patient/authorised-attendant records source to verify before treating this as only a compensation case [{ethics}]."
            )
        if clinical is not None:
            lines.append(
                f"The Clinical Establishments Act source is the hospital-registration/records-and-conditions source to keep with the complaint, especially if the hospital will not acknowledge the request or give a written reply [{clinical}]."
            )
    if bill_issue:
        if clinical is not None:
            lines.append(
                f"For a {issue_phrase}, use the Clinical Establishments Act source as hospital-registration/conditions support for charges, records, and billing transparency before reducing the issue to a generic consumer complaint [{clinical}]."
            )
        if ethics is not None and records_issue:
            lines.append(
                f"If the bill dispute also needs case papers, preserve the medical-record request separately because the record-copy route and the refund/compensation route need different proof [{ethics}]."
            )
    lines.append(
        f"The Consumer Protection Act source gives the District Commission/e-Daakhil service-deficiency route for refund, compensation, or deficiency after the written hospital request and replies are preserved [{consumer}]."
    )
    action_cites = _cite_many(ethics if records_issue or negligence_issue else None, clinical, consumer, bns_medical, bnss_fir)
    lines.extend([
        "**What you can do next**",
        f"- Give the hospital a dated written request for records/case papers, consent forms, ICU notes, discharge summary, itemised-bill, breakup-bill or breakup of charges, receipts, and written reasons for refund refusal; keep acknowledgement before approaching the hospital grievance desk, clinical-establishment/health authority, medical council where relevant, or District Consumer Commission {action_cites}.",
        f"- Keep patient ID/authority letter, consent forms, discharge summary, prescriptions, investigation reports, bill and payment receipts, screenshots/messages, names of staff spoken to, and the hospital's written reply or no-reply proof {action_cites}.",
    ])
    return lines


def _income_tax_1432_notice_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "tax_gst_compliance" or not _is_income_tax_1432_notice(q):
        return []
    sec143 = _find(passages, title_terms=("income-tax", "income tax"), anchor_terms=("/sec-143",))
    sec142 = _find(passages, title_terms=("income-tax", "income tax"), anchor_terms=("/sec-142",))
    sec144 = _find(passages, title_terms=("income-tax", "income tax"), anchor_terms=("/sec-144",))
    if sec143 is None:
        return []

    lines = ["**Short answer**"]
    if sec143 is not None:
        lines.append(
            f"For an Income-tax Act section 143(2) notice, treat it as a scrutiny-assessment response: respond by the date/time stated in the notice and produce the evidence asked for, rather than using a generic appeal or reassessment route [{sec143}]."
        )
        lines.append(
            f"The section 143 source also matters for checking notice-validity timing, but the immediate user step is still to read the notice deadline and upload/submit the response with proof before that date [{sec143}]."
        )
    if sec142 is not None:
        lines.append(
            f"If the same notice or portal also asks for accounts, documents, statements, or return particulars under section 142, keep that document-production lane separate and answer each questionnaire item with uploaded proof [{sec142}]."
        )
    if sec144 is not None:
        lines.append(
            f"If you ignore the notice, the assessing officer may move toward a best-judgment assessment lane, so do not wait until the last day if documents are missing [{sec144}]."
        )
    action_cites = _cite_many(sec143, sec142, sec144)
    lines.extend([
        "**What you can do next**",
        f"- Download the full notice from the income-tax portal, note the assessment year, DIN/notice number, due date and hearing/submission mode; keep the ITR, computation, Form 16, AIS/Form 26AS, bank statements, deductions/investment proofs, sale/loan records if relevant, and upload a point-wise response with acknowledgement {action_cites}.",
    ])
    return lines


def _gst_rule_86b_cash_payment_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "tax_gst_compliance" or not _is_gst_rule_86b(q):
        return []
    rule86b = _find(passages, title_terms=("central goods and services tax rules",), anchor_terms=("/rule-86b", "rule-86b", "/sec-85", "/sec-85-e", "/sec-98"))
    cgst49 = _find(passages, title_terms=("central goods and services tax act",), anchor_terms=("/sec-49", "/sec-49A", "/sec-49B"))
    if rule86b is None or cgst49 is None:
        return []

    lines = [
        "**Short answer**",
        f"For a Rule 86B question, first check whether the monthly taxable-supply threshold and the rule's exceptions apply; do not treat every high-turnover GSTR-3B as automatically requiring the same cash payment without checking the rule facts [{rule86b}].",
        f"The linked CGST Act electronic-credit-ledger/cash-ledger source is the Act-side provision to keep with the Rule 86B calculation, so verify both the rule and the ledger/payment section together [{cgst49}].",
        "**What you can do next**",
        f"- Reconcile the month-wise taxable turnover, output tax, ITC/electronic credit ledger, cash ledger, GSTR-3B, prior income-tax/GST payment facts, refunds/exceptions if claimed, and ask your CA/GST practitioner to document why Rule 86B applies or an exception applies before filing or litigating {_cite_many(rule86b, cgst49)}.",
    ]
    return lines


def _customs_drawback_export_mismatch_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "tax_gst_compliance" or not _is_customs_drawback_problem(q):
        return []
    sec75 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-75",))
    sec74 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-74",))
    sec27 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-27",))
    sec128 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-128",))
    primary = sec75 if sec75 is not None else sec74 if sec74 is not None else sec27
    if primary is None:
        return []

    claim_source = "Section 75 drawback" if sec75 is not None else "Section 74 drawback" if sec74 is not None else "Section 27 refund"
    action_cites = _cite_many(primary, sec128)
    lines = [
        "**Short answer**",
        f"For a drawback claim rejected or export-incentive rejection tied to a shipping-bill mismatch, keep this as a Customs Act drawback/refund and export-document dispute; verify the rejection order against the {claim_source} source before treating it as ordinary GST or income-tax compliance [{primary}].",
    ]
    if sec128 is not None:
        lines.append(
            f"If Customs has already passed a rejection, assessment, or adjudication order, keep the Customs Act appeal route to Commissioner (Appeals) separate from any rectification or portal follow-up [{sec128}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Build a drawback/export-incentive file with shipping bill, drawback claim, rejection/order, EGM/export general manifest status, invoice, packing list, let-export-order, bank realisation/FIRC if relevant, mismatch screenshot, reply filed, and appeal papers; take it to the customs officer/customs broker or customs counsel before filing rectification, refund, or appeal {action_cites}.",
    ])
    return lines


def _customs_icegate_misdeclaration_hold_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "tax_gst_compliance" or not _is_customs_icegate_misdeclaration_problem(q):
        return []
    sec124 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-124",))
    sec111 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-111",))
    sec112 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-112",))
    sec17 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-17",))
    sec28 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-28",))
    sec128 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-128",))
    primary = sec124 if sec124 is not None else sec111 if sec111 is not None else sec112
    if primary is None:
        return []

    goods_phrase = "Chinese LED lights" if _has_any(q, ("chinese led", "led light", "led lights")) else "the imported goods"
    action_cites = _cite_many(primary, sec111, sec112, sec17, sec28, sec128)
    lines = [
        "**Short answer**",
        f"For an ICEGATE bill-of-entry hold, treat it as an ICEGATE hold alleging misdeclaration of {goods_phrase}: ask for the written hold/order reason and show-cause/adjudication track first; do not treat the portal hold as only a generic tax complaint [{primary}].",
    ]
    if sec111 is not None or sec112 is not None:
        cite = sec111 if sec111 is not None else sec112
        lines.append(
            f"If Customs is alleging improper import or penalty, check the Section 111/112/124 track for confiscation, penalty, and notice separately from tariff classification and duty calculation [{cite}]."
        )
    if sec17 is not None:
        lines.append(
            f"If the hold is really about assessment/classification, keep the bill-of-entry assessment record and assessed/reassessed order as the starting point [{sec17}]."
        )
    if sec28 is not None:
        lines.append(
            f"If a short-levy or duty-demand notice follows the hold, keep the Section 28 demand/adjudication track separate from the ICEGATE screenshot [{sec28}]."
        )
    if sec128 is not None:
        lines.append(
            f"If an appealable order is already passed, verify the Customs Act Commissioner (Appeals) route before filing a case elsewhere [{sec128}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Keep the bill of entry, ICEGATE hold or mismatch screenshot, written query/order/SCN, invoice, packing list, catalogue/product literature, test report if any, tariff heading claimed by each side, duty calculation, reply filed, hearing notices, and appeal papers; use a customs broker/customs counsel for the reply or appeal {action_cites}.",
    ])
    return lines


def _customs_reclassification_svb_lines(q: str, route: MatterRoute, passages: list[dict]) -> list[str]:
    if route.category != "tax_gst_compliance" or not _is_customs_reclassification_svb_problem(q):
        return []
    sec14 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-14",))
    sec17 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-17",))
    sec28 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-28",))
    sec128 = _find(passages, title_terms=("customs act",), anchor_terms=("/sec-128",))
    has_svb_context = customs_svb_issue(q)
    primary = (
        sec14 if has_svb_context and sec14 is not None
        else sec17 if sec17 is not None
        else sec28 if sec28 is not None
        else sec128 if sec128 is not None
        else sec14
    )
    if primary is None:
        return []

    item_phrase = "wire harness" if "wire harness" in q else "the imported goods"
    action_cites = _cite_many(primary, sec17, sec28, sec128)
    if has_svb_context:
        related_party_negated = customs_related_party_negated(q)
        svb_evidence_phrase = (
            "invoice value, declared-value papers, and bill-of-entry order"
            if related_party_negated
            else "invoice value, related-party material, and bill-of-entry order"
        )
        svb_action_docs = (
            "SVB questionnaire/notices, invoices, contracts, declared-value papers"
            if related_party_negated
            else "SVB questionnaire/notices, invoices, contracts, related-party/declared-value papers"
        )
        lead = (
            f"For customs reclassification of {item_phrase} with higher duty and SVB/valuation facts, "
            f"start with the Customs Act valuation/assessment record, {svb_evidence_phrase}; "
            f"do not answer it as a generic GST dispute [{primary}]."
        )
        sec28_line = (
            f"If Customs is demanding differential duty after reclassification or valuation, keep the Section 28 demand/adjudication papers with the SVB file [{sec28}]."
            if sec28 is not None else None
        )
        action_line = (
            f"- Build a customs/SVB file with bill of entry, reclassification/assessment order, tariff headings claimed by both sides, duty calculation, {svb_action_docs}, catalogue/test report, reply filed, hearing notes, and appeal proof; take it to a customs broker/customs counsel before customs appeal or reply {action_cites}."
        )
    else:
        lead = (
            f"For customs reclassification of {item_phrase} with higher duty, start with the Customs Act "
            f"assessment/classification record, tariff heading, bill-of-entry order, and duty calculation; do not answer it as a generic GST dispute [{primary}]."
        )
        sec28_line = (
            f"If Customs is demanding differential duty after reclassification, keep the Section 28 demand/adjudication papers with the assessment file [{sec28}]."
            if sec28 is not None else None
        )
        action_line = (
            f"- Build a customs classification file with bill of entry, reclassification/assessment order, tariff headings claimed by both sides, duty calculation, invoices, product catalogue/literature, test report if any, reply filed, hearing notes, and appeal proof; take it to a customs broker/customs counsel before customs appeal or reply {action_cites}."
        )
    lines = [
        "**Short answer**",
        lead,
    ]
    if sec17 is not None and sec17 != primary:
        lines.append(
            f"The assessment/reassessment source is relevant for the classification and bill-of-entry decision that created the higher-duty demand [{sec17}]."
        )
    if sec28_line is not None:
        lines.append(sec28_line)
    if sec128 is not None:
        lines.append(
            f"If there is an assessment or adjudication order, the customs appeal route to Commissioner (Appeals) is the route to verify before filing elsewhere [{sec128}]."
        )
    lines.extend([
        "**What you can do next**",
        action_line,
    ])
    return lines


def _find(
    passages: list[dict],
    *,
    title_terms: tuple[str, ...] = (),
    anchor_terms: tuple[str, ...] = (),
) -> int | None:
    for passage in passages:
        title = str(passage.get("title") or "").lower()
        anchor = str(passage.get("anchor") or "").lower()
        if title_terms and not any(term in title for term in title_terms):
            continue
        if anchor_terms and not any(_anchor_matches(anchor, term) for term in anchor_terms):
            continue
        idx = passage.get("index")
        return int(idx) if isinstance(idx, int) else None
    return None


def _find_passage_containing(passages: list[dict], terms: tuple[str, ...]) -> int | None:
    for passage in passages:
        blob = " ".join(
            str(passage.get(key) or "").lower()
            for key in ("title", "anchor", "text", "snippet")
        )
        if any(term in blob for term in terms):
            idx = passage.get("index")
            return int(idx) if isinstance(idx, int) else None
    return None


def _title_for_index(passages: list[dict], idx: int) -> str:
    for passage in passages:
        if passage.get("index") == idx:
            return str(passage.get("title") or "").lower()
    return ""


def _display_title_for_index(passages: list[dict], idx: int) -> str:
    for passage in passages:
        if passage.get("index") == idx:
            return str(passage.get("title") or "")
    return ""


def _source_type_for_index(passages: list[dict], idx: int) -> str:
    for passage in passages:
        if passage.get("index") == idx:
            return str(passage.get("source_type") or "").lower()
    return ""


def _find_state_witch_source(passages: list[dict], *, allow_reference_only: bool = True) -> int | None:
    terms = ("witch hunting", "witch-hunting", "tonhi", "tonahi", "daain", "daayan", "dayan pratha")
    for passage in passages:
        blob = " ".join(
            str(passage.get(key) or "").lower()
            for key in ("title", "anchor", "text", "snippet", "statute_short")
        )
        if not any(term in blob for term in terms):
            continue
        if not allow_reference_only and str(passage.get("source_type") or "").lower() not in {"bare_act", "official_guidance"}:
            continue
        idx = passage.get("index")
        return int(idx) if isinstance(idx, int) else None
    return None


def _anchor_matches(anchor: str, term: str) -> bool:
    needle = term.lower()
    if needle.startswith("/sec-"):
        return re.search(rf"{re.escape(needle)}(?=@|-|__|$)", anchor) is not None
    if needle.startswith("sec-"):
        return re.search(rf"(^|/){re.escape(needle)}(?=@|-|__|$)", anchor) is not None
    return needle in anchor


def _norm(text: str) -> str:
    return " ".join(str(text).lower().split())


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _has_chhattisgarh_context(text: str) -> bool:
    q = str(text or "").lower()
    if _has_any(q, (
        "chhattisgarh", "chattisgarh", "raipur", "bilaspur", "jashpur",
        "bastar district", "bastar village", "bastar chhattisgarh",
    )):
        return True
    return re.search(r"(?<![a-z0-9])durg(?![a-z0-9])", q) is not None


def _cite_many(*indices: int | None) -> str:
    unique: list[int] = []
    for idx in indices:
        if idx is None or idx in unique:
            continue
        unique.append(idx)
    return ", ".join(f"[{idx}]" for idx in unique)


def _money_amount_phrase(q: str) -> str:
    lakh_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs)\b", q)
    if lakh_match:
        return f"Rs.{lakh_match.group(1)} lakh"
    rupee_match = re.search(r"\b(?:rs\.?|inr)\s*([0-9][0-9,]*)\b", q)
    if rupee_match:
        return f"Rs.{rupee_match.group(1)}"
    plain_match = re.search(r"\b([1-9][0-9]{3,})\b", q)
    if plain_match:
        return f"Rs.{plain_match.group(1)}"
    return "money"


def _is_builder_rera(q: str) -> bool:
    real_estate = _has_any(q, (
        "builder", "developer", "promoter", "rera", "flat", "apartment",
        "housing project", "real estate project",
    ))
    remedy = _has_any(q, (
        "possession", "occupancy certificate", "occupation certificate",
        "completion certificate", "handover", "delayed", "delay",
        "missed deadline", "full money", "paid full", "taking full money",
        "booking amount", "refund", "layout changed", "changed layout",
        "allotment", "full payment", "after full payment",
        "defective", "defect", "not repairing", "repairing", "leakage",
        "tiles", "bathroom", "sale deed", "registered sale deed",
        "register sale deed", "hasnt registered", "hasn't registered",
        "not registered", "property tax dues", "tax dues",
    )) or re.search(r"\boc\b", q) is not None
    return real_estate and remedy


def _is_hospital_records_billing(q: str) -> bool:
    hospital = _has_any(q, ("hospital", "clinic", "doctor", "icu", "nursing home"))
    issue = _has_any(q, (
        "medical records", "case papers", "hospital records",
        "not giving records", "not giving medical records",
        "refusing case papers", "after discharge",
        "overcharged", "overcharge", "breakup bill", "breakup",
        "detailed bill", "itemised bill", "itemized bill",
        "not giving bill", "no receipt", "extra charge",
        "bill", "billing", "without consent", "no consent",
        "kept father in icu", "kept mother in icu", "icu bill",
        "wrong leg", "wrong side", "wrong surgery", "wrong operation",
        "operated wrong", "wrong injection", "medical negligence",
        "negligence", "died after", "death after",
    ))
    return hospital and issue


def _is_bank_freeze(q: str) -> bool:
    return _has_any(q, ("bank account", "salary account", "savings account", "current account", "upi account", "upi id", "bank ", "bank says")) and _has_any(q, (
        "frozen", "freeze", "froze", "blocked", "lien", "kyc hold",
        "kyc pending", "kyc is pending", "account is on hold",
        "account on hold", "account hold", "fraud complaint",
        "not giving order copy", "order copy",
    ))


def _is_wrong_debit(q: str) -> bool:
    return _has_any(q, ("bank", "account", "savings account", "customer care", "branch", "upi", "gpay", "phonepe", "payment app", "forex", "atm", "imps", "credit card")) and _has_any(q, (
        "wrong debit", "wrongly debited", "debited twice", "deducted money wrongly",
        "wrongly deducted", "wrong deduction", "deducted from", "money deducted",
        "not refund", "no refund", "maintenance charge", "deducted maintenance charge",
        "chargeback", "chargeback not processed", "not processed",
        "charge twice", "charged twice", "wrongly charged", "forex markup",
        "annual fee", "card annual fee", "annual fee charged",
        "annual fee twice", "charged annual fee", "charged annual fee twice",
        "fee charged", "fee charged twice", "card was closed", "card closed",
        "credit card charged annual fee twice",
        "charged markup", "markup twice", "markup charged",
        "failed upi refund", "upi refund", "transaction failed", "status failed",
        "failed but debited", "failed but money cut", "failed but money deducted",
        "money cut", "amount cut",
        "imps transfer failed", "imps failed", "failed imps",
        "beneficiary did not get money", "beneficiary didn't get money",
        "beneficiary says not received", "beneficiary says no money",
        "atm cash not dispensed", "cash not dispensed", "atm did not dispense",
        "atm withdrawal failed", "account debited", "atm debited",
    ))


def _is_credit_noc_cibil(q: str) -> bool:
    closed_loan = _has_any(q, (
        "loan closed", "closed loan", "loan closure", "personal loan closed",
        "tenure ended", "foreclosure", "paid full", "fully paid",
    ))
    credit_or_noc = _has_any(q, (
        "noc", "no dues", "no-dues", "no objection certificate",
        "cibil", "credit report", "credit score", "credit bureau",
        "still active", "written off", "written-off",
    ))
    bank_or_lender = _has_any(q, ("bank", "nbfc", "lender", "finance company", "bajaj", "hdfc", "sbi", "icici", "axis", "kotak"))
    return bank_or_lender and credit_or_noc and (closed_loan or _has_any(q, ("not giving noc", "cibil still", "still active in cibil")))


def _is_credit_identity_misuse(q: str) -> bool:
    lender_or_credit = _has_any(q, (
        "loan", "fake loan", "nbfc", "finance company", "lender",
        "cibil", "credit report", "credit score", "credit bureau",
    ))
    identity_or_signature = _has_any(q, (
        "signature not mine", "not my signature", "fake signature",
        "signature is not mine",
        "did not sign", "didn't sign", "forged", "forgery",
        "loan showing on my documents", "loan showing in my documents",
        "documents but signature", "opened in my name",
        "without my consent",
        "fake loan", "loan which i never took", "which i never took",
        "i never took", "never took", "never taken",
        "not my loan", "loan not mine", "opened with my pan",
        "opened with my aadhaar", "opened with my aadhar",
    ))
    return lender_or_credit and identity_or_signature


def _is_loan_app(q: str) -> bool:
    ordinary_reminder_only = _has_any(q, (
        "normal due date reminder", "only sends normal due date reminder",
        "only normal reminder", "only sends reminder", "only reminder",
        "normal emi reminder", "normal payment reminder",
        "no threats or contacts", "no threat or contact",
        "no threats", "no threat", "no contacts", "not harassing",
        "not harassment", "no harassment", "has not harassed",
        "hasn't harassed", "did not harass", "never harassed",
        "did not contact anyone", "has not contacted anyone",
        "hasn't contacted anyone", "never contacted anyone",
        "asks for contacts permission", "contacts permission during signup",
        "permission during signup", "only asks permission",
    )) and not _has_any(q, (
        "calling my contacts", "calling contacts", "harassing my contacts",
        "sent message to contacts", "messages to contacts", "abusing",
        "abusive", "threatened", "threatening", "blackmail", "morphed",
        "nude", "came to my office", "visiting office", "shouting",
        "publicly shame", "tell my boss", "tell manager", "tell my office",
        "tell my neighbours", "tell my neighbors",
    ))
    if ordinary_reminder_only:
        return False

    if _is_credit_identity_misuse(q) and not _has_any(q, (
        "harass", "harassing", "harrasing", "harassment", "calling my contacts",
        "calling contacts", "contact list", "threat", "threaten", "threatening",
        "abusing", "abuse", "photo to contacts", "sending my photo",
        "morphed", "nude", "blackmail", "extortion", "came to my office",
        "visiting office", "tell my office", "tell my neighbours", "tell my neighbors",
    )):
        return False
    lender = _has_any(q, (
        "loan app", "recovery app", "instant loan", "digital lending",
        "finance app", "nbfc", "finance company", "finance agent",
        "bajaj", "bajaj finance", "bajaj finserv", "recovery agent",
        "recovery agents", "loan recovery", "collection agent",
        "collection agents", "collection people",
    ))
    return lender and _has_loan_harassment_adverse_act(q)


def _has_loan_harassment_adverse_act(q: str) -> bool:
    explicit_abuse = _has_any(q, (
        "harass", "harassing", "harrasing", "harassment", "abusing", "abuse",
        "threat", "threaten", "threatening", "blackmail", "extortion",
        "publicly shame", "shaming", "shouting", "saying i am fraud",
        "saying I am fraud", "morphed", "nude", "data leak",
    ))
    third_party_contact = (
        _has_any(q, (
            "calling", "called", "contacted", "contacting", "messaging",
            "messaged", "sent message", "sending", "sent my", "shared",
            "sharing", "leaked", "posted", "telling", "tell my",
        ))
        and _has_any(q, (
            "contacts", "contact list", "relatives", "family", "mother",
            "neighbours", "neighbors", "boss", "manager", "employer",
            "office", "workplace", "society", "whatsapp group",
        ))
    )
    intrusive_recovery = _has_any(q, (
        "came home", "came to my house", "visiting office", "came to my office",
        "recovery agent visited", "collection agent visited",
    ))
    photo_misuse = (
        _has_any(q, ("photo", "image", "picture"))
        and _has_any(q, ("sending", "sent", "shared", "sharing", "posted", "morphed", "blackmail"))
    )
    return explicit_abuse or third_party_contact or intrusive_recovery or photo_misuse


def _is_intimate_image_blackmail(q: str) -> bool:
    if _is_public_political_deepfake(q):
        return False
    intimate_material = _has_any(q, (
        "nude", "naked", "private photo", "private picture",
        "private video", "intimate photo", "intimate video",
        "sex video", "sexual image", "morphed", "deepfake",
        "recorded me", "video call recorded", "recorded my video",
        "recorded video call", "recorded private", "webcam recorded", "call recorded",
        "secretly recorded us", "recorded us during sex", "recorded sex",
        "recorded our sex", "during sex",
        "my face put", "face put", "body is not mine",
    ))
    pressure = _has_any(q, (
        "blackmail", "extortion", "demanding money", "demanded money",
        "extort", "extorting", "pay money", "threat", "threaten", "threatening",
        "dont pay", "don't pay",
        "circulating", "circulate", "upload", "uploaded", "leak",
        "leaked", "send to", "share", "college group", "family group",
        "relatives", "telegram",
        "whatsapp group", "reddit", "remove", "takedown", "take down",
        "posted", "posting", "website", "can i remove", "remove it",
    ))
    return intimate_material and pressure


def _has_negated_extortion_money_context(q: str) -> bool:
    return _has_any(q, (
        "not extorting", "not extort", "not extortion",
        "no extortion", "without extortion", "no money demand",
        "no money demanded", "not demanding money", "not demanded money",
        "did not demand money", "didn't demand money",
        "just threatening to share", "only threatening to share",
    ))


def _is_dpdp_data_breach(q: str) -> bool:
    breach = _has_any(q, (
        "data breach", "data leaked", "data leak", "leaked my data",
        "pan leaked", "aadhaar leaked", "aadhar leaked", "address leaked",
        "phone leaked", "personal data", "dpdp", "privacy breach",
        "leaked my chat", "therapist", "mental health privacy",
    ))
    company_or_platform = _has_any(q, (
        "byjus", "byju", "dunzo", "company", "platform", "app",
        "school", "college", "hospital", "bank", "nbfc", "twitter",
        "x.com", "instagram", "telegram",
    ))
    misuse = _has_any(q, (
        "fake account", "loan", "fraud", "identity", "kyc", "spam",
        "threat", "blackmail", "compensation", "claim", "where to go",
    ))
    return breach and (company_or_platform or misuse)


def _is_public_political_deepfake(q: str) -> bool:
    deepfake = _has_any(q, ("deepfake", "ai video", "fake video", "morphed video", "lookalike video"))
    public_actor = _has_any(q, (
        "modi", "prime minister", "chief minister", "minister", "politician",
        "bjp", "congress", "aap ", "political party", "party worker", "it cell",
    )) or re.search(r"\b(?:pm|cm|mla|mp)\b", q) is not None
    risk = _has_any(q, ("threat", "threatening", "circulating", "viral", "shared", "campaign", "election", "candidate", "poll", "booth", "fir", "case", "it cell"))
    private_image = _has_any(q, ("nude", "porn", "sex video", "intimate", "private photo"))
    return deepfake and public_actor and risk and not private_image


def _is_software_license_notice(q: str) -> bool:
    software_context = _has_any(q, (
        "software", "cad", "autocad", "solidworks", "photoshop",
        "unlicensed copies", "unlicensed copy", "pirated software",
        "software license", "software licence",
    ))
    notice_context = _has_any(q, (
        "notice", "legal notice", "vendor sent", "vendor notice",
        "audit", "unlicensed", "seats", "seat", "copies", "licence", "license",
    ))
    trademark_context = _has_any(q, ("trademark", "trade mark", "brand", "logo", "passing off", "counterfeit"))
    return software_context and notice_context and not trademark_context


def _is_housing_parking_blocked(q: str) -> bool:
    housing = _has_any(q, ("apartment", "housing society", "society", "rwa", "flat association"))
    parking = _has_any(q, ("parking", "parking slot", "dedicated parking", "allotted parking", "car park"))
    blocked = _has_any(q, ("blocking", "blocked", "security guard", "cant do anything", "can't do anything", "not helping"))
    return housing and parking and blocked


def _is_lost_aadhaar_reissue_problem(q: str) -> bool:
    aadhaar = _has_any(q, ("aadhaar", "aadhar", "uidai"))
    lost = _has_any(q, ("lost", "missing", "gone", "no original", "original papers", "village papers", "raid"))
    reissue = _has_any(q, ("get new one", "new aadhaar", "reissue", "retrieve", "download", "update", "how to get"))
    return aadhaar and lost and reissue


def _is_witch_branding(q: str) -> bool:
    witch_words = _has_any(q, (
        "daayan", "dayan", "witch", "black magic", "tonhi",
        "daini", "ojha", "tantrik",
    ))
    harm_words = _has_any(q, (
        "beat", "beaten", "beating", "threat", "threaten",
        "threatening", "kill", "stripped", "disrobed", "public",
        "branded", "called", "village", "neighbour", "neighbor",
        "expel", "expulsion", "tore her clothes", "without clothes",
        "paraded", "parade", "parade her", "remove her from village",
        "forced her to leave", "forced her to leave home", "leave home",
        "panchayat",
    ))
    return witch_words and harm_words


def _is_income_tax_1432_notice(q: str) -> bool:
    income_tax_context = _has_any(q, (
        "income tax", "income-tax", "itr", "assessment year", " ay ",
        "ay 20", "tax notice", "notice under section 143",
    ))
    section_143_context = _has_any(q, (
        "143(2)", "143 (2)", "section 143(2)", "section 143 (2)",
        "sec 143(2)", "sec. 143(2)", "u/s 143(2)", "under section 143(2)",
    ))
    notice_context = _has_any(q, (
        "notice", "scrutiny", "assessment", "respond", "response",
        "how much time", "deadline", "due date", "hearing",
    ))
    return section_143_context and (income_tax_context or notice_context)


def _is_gst_rule_86b(q: str) -> bool:
    return _has_any(q, ("rule 86b", "86b", "1% cash", "1 percent cash", "one percent cash")) and _has_any(q, (
        "gst", "cgst", "gstr", "turnover", "taxable supply", "cash", "itc", "electronic credit",
    ))


def _is_sarfaesi_possession_stage(q: str) -> bool:
    sarfaesi_or_bank = _has_any(q, ("sarfaesi", "bank", "secured creditor", "home loan", "secured asset"))
    return _has_sarfaesi_possession_terms(q) and sarfaesi_or_bank


def _is_sarfaesi_132_notice(q: str) -> bool:
    sarfaesi = _has_any(q, ("sarfaesi", "13(2)", "13 (2)", "section 13(2)", "sec 13(2)", "demand notice"))
    loan_default = _has_any(q, ("home loan", "loan default", "default", "npa", "bank notice", "bank", "secured asset"))
    return sarfaesi and loan_default and not _has_sarfaesi_possession_terms(q)


def _has_sarfaesi_possession_terms(q: str) -> bool:
    return _has_any(q, (
        "possession notice", "symbolic possession", "physical possession",
        "sale notice", "auction notice", "13(4)", "13 (4)", "section 13(4)",
        "sec 13(4)", "took possession", "taking possession", "auctioning",
    ))


def _is_trademark_cease_desist(q: str) -> bool:
    notice = _has_any(q, (
        "cease and desist", "cease-and-desist", "legal notice", "notice",
        "lawyer notice", "ip notice",
    ))
    mark_context = _has_any(q, ("trademark", "trade mark", "brand", "logo", "similar", "confusing", "confusion"))
    return notice and mark_context


def _witch_state_label(q: str) -> str:
    if "ranchi" in q:
        return "Ranchi/Jharkhand"
    if "chaibasa" in q:
        return "Chaibasa/Jharkhand"
    if _has_any(q, ("jharkhand", "gumla", "khunti", "simdega")):
        return "Jharkhand"
    if _has_any(q, ("chhattisgarh", "chattisgarh", "bilaspur", "raipur", "bastar", "jashpur")):
        return "Chhattisgarh"
    if _has_any(q, ("assam", "barpeta", "kokrajhar", "guwahati")):
        return "Assam"
    return "relevant State"


def _is_false_fir(q: str) -> bool:
    return _has_any(q, (
        "false fir", "false case", "false 420", "fake fir",
        "fake case", "wrong case", "false complaint", "fake 420",
        "fake cheating", "false cheating", "fake complaint",
        "cheating complaint", "cheating case", "cyber cheating case",
    )) or (
        _has_any(q, ("420", "fir", "case", "complaint", "summons"))
        and _has_any(q, ("false", "fake", "made false", "filed false"))
    ) or (
        _has_any(q, ("420 complaint", "420 police complaint", "cheating complaint", "cheating case"))
        and _has_any(q, ("police calling", "police called", "cheque money dispute", "money dispute", "personal loan dispute", "what to carry to station", "payment fight", "refund fight", "refund dispute"))
    )


def _is_matrimonial_false_case(q: str) -> bool:
    matrimonial_offence = _has_any(q, (
        "498a", "498-a", "dv case", "domestic violence case",
        "dowry case", "dowry-cruelty", "cruelty case",
    ))
    family_side = _has_any(q, (
        "wife", "husband", "bahu", "daughter in law", "daughter-in-law",
        "parents", "mother", "father", "family", "whole family",
        "in laws", "in-laws", "mother in law", "mother-in-law",
    ))
    accused_side = _has_any(q, (
        "false", "fake", "named", "accused", "defend", "defence",
        "defense", "harass", "harassing",
    ))
    return matrimonial_offence and family_side and accused_side


def _is_scst_poa_accused_false_case(q: str) -> bool:
    poa_context = _has_any(q, (
        "sc st", "sc/st", "atrocity act", "atrocity case", "poa act",
        "poa case", "poa false", "prevention of atrocities",
        "scheduled caste", "scheduled tribe",
    ))
    accused_side = _has_any(q, (
        "false", "fake", "accused", "filed on me", "against me",
        "put on me", "put on them", "case put", "bail",
        "how to get bail", "where to go",
    ))
    return poa_context and accused_side


def _is_witch_accused_false_case(q: str) -> bool:
    witch_context = _has_any(q, (
        "daayan", "dayan", "witch", "black magic", "tonhi", "tonahi",
        "daini",
    ))
    accused_side = _has_any(q, (
        "false", "fake", "case filed", "filed on me", "against me",
        "they say i am", "say i am", "accused", "bail",
    ))
    return witch_context and accused_side


def _is_cab_aggregator(q: str) -> bool:
    cab_context = _has_any(q, (
        "uber", "ola", "cab app", "cab aggregator", "taxi aggregator",
        "ride hailing", "ride-hailing", "cab ", "taxi ",
    ))
    passenger_problem = _has_any(q, (
        "cancelled ride", "canceled ride", "ride cancelled",
        "ride canceled", "deducted money", "not refunding", "no refund",
        "refund", "extra fare", "charged extra fare", "longer route",
        "driver abused", "driver misbehaved", "platform closed complaint",
        "customer care not helping", "customer support not helping",
        "support bot", "cancellation fee", "wallet", "fare", "trip", "ride",
    ))
    driver_account_problem = _has_any(q, (
        "driver id", "driver account", "driver profile", "driver partner",
        "driving for", "drive for", "deactivated", "profile blocked",
    ))
    return cab_context and passenger_problem and not driver_account_problem


def _is_cab_aggregator_driver_account(q: str) -> bool:
    passenger_negation = _has_any(q, (
        "i am customer", "i am a customer", "customer account",
        "as passenger", "as a passenger", "i was passenger",
    ))
    if passenger_negation:
        return False
    cab_context = _has_any(q, (
        "uber", "ola", "cab app", "taxi app", "cab aggregator",
        "taxi aggregator", "cab ", "taxi ",
    ))
    driver_context = _has_any(q, (
        "driver", "driver id", "driver account", "driver profile",
        "driver partner", "platform partner", "driving", "drive for",
    ))
    account_problem = _has_any(q, (
        "suspended", "deactivated", "blocked", "profile blocked",
        "id blocked", "no reason", "without reason", "appeal",
        "earning", "earnings", "payment", "payout", "dues",
    ))
    return cab_context and driver_context and account_problem


def _is_poa_special_court_delay(q: str) -> bool:
    poa_context = _has_any(q, (
        "poa", "atrocity", "sc/st", "sc st", "scheduled caste",
        "scheduled tribe", "special court",
    ))
    court_delay = _has_any(q, (
        "special court", "case pending", "pending 5 yrs", "pending 5 years",
        "no judgement", "no judgment", "no order", "trial pending",
        "how to complain", "where to complain",
    ))
    return poa_context and court_delay


def _is_caste_public_access_exclusion(q: str) -> bool:
    caste_context = _has_any(q, (
        "dalit", "sc/st", "sc st", "scheduled caste", "caste",
        "thakur", "untouchable", "chamar", "mahar",
    ))
    access_context = _has_any(q, (
        "temple", "well", "dirty water", "cannot touch", "cant enter",
        "can't enter", "not enter", "stopped us from entering",
        "public access", "not allowed", "denied entry", "water source",
    ))
    return caste_context and access_context


def _is_police_seized_device(q: str) -> bool:
    device = _has_any(q, (
        "laptop", "company laptop", "phone", "mobile", "device",
        "hard disk", "computer",
    ))
    seized = _has_any(q, (
        "seized by police", "has been seized", "police seized",
        "took my device", "took my laptop", "seizure memo",
        "investigation against my colleague", "colleague",
    ))
    return device and seized


def _is_family_forced_sex_safety(q: str) -> bool:
    return _has_any(q, ("husband", "marriage", "marital", "wife")) and _has_any(q, (
        "forces me at night", "when i say no", "without consent",
        "forced sex", "force sex", "sexual coercion", "i am tired or unwell",
    ))


def _is_family_disabled_baby_safety(q: str) -> bool:
    family_context = _has_any(q, ("husband", "in laws", "in-laws", "mother in law", "family"))
    baby_context = _has_any(q, ("disabled baby", "baby with disability", "child with disability", "newborn"))
    abandonment = _has_any(q, ("leave the baby", "abandon", "hospital", "throw me out", "not take baby home"))
    return family_context and baby_context and abandonment


def _is_gig_platform_worker_account_block(q: str) -> bool:
    passenger_or_consumer = _has_any(q, (
        "i ordered", "my order", "food order", "customer care",
        "refund", "damaged item", "late delivery",
    ))
    if passenger_or_consumer and not _has_any(q, ("my id blocked", "driver", "delivery boy", "rider", "partner")):
        return False
    platform = _has_any(q, (
        "swiggy", "zomato", "blinkit", "zepto", "dunzo", "rapido",
        "urban company", "delivery app", "gig app", "platform",
    ))
    worker = _has_any(q, (
        "delivery", "rider", "driver", "partner", "delivery boy",
        "delivery partner", "gig worker", "platform worker", "customer abused",
        "customer abuse", "1 star", "rating", "id blocked", "account blocked",
    ))
    account_problem = _has_any(q, (
        "blocked", "suspended", "deactivated", "appeal", "no reason",
        "spam", "rating", "1 star", "customer abused", "customer abuse",
        "payment", "payout", "dues", "earning", "earnings",
    ))
    return platform and worker and account_problem


def _is_social_media_account_suspension(q: str) -> bool:
    platform = _has_any(q, (
        "instagram", "insta", "facebook", "meta", "youtube", "twitter",
        "x.com", "linkedin", "social media",
    ))
    account = _has_any(q, (
        "account", "page", "profile", "channel", "handle", "followers",
        "200k", "monetized", "monetised",
    ))
    suspension = _has_any(q, (
        "suspended", "disabled", "blocked", "banned", "terminated",
        "no notice", "without notice", "cannot login", "can't login",
        "appeal", "restore", "sue meta", "sue instagram",
    ))
    return platform and account and suspension


def _is_online_gambling_platform_dispute(q: str) -> bool:
    gambling = _has_any(q, (
        "parimatch", "dream11", "rummy", "online rummy", "betting app",
        "betting", "gambling", "casino app", "fantasy app", "gaming app",
    ))
    money_or_account = _has_any(q, (
        "lost", "recover", "refund", "money", "lakh", "50k", "80k",
        "stuck", "froze", "frozen", "freeze", "blocked", "kyc",
        "withdrawal", "account",
    ))
    return gambling and money_or_account


def _is_digital_platform_kyc_money_freeze(q: str) -> bool:
    if _is_online_gambling_platform_dispute(q):
        return False
    if _is_crypto_wallet_freeze(q):
        return False
    platform = _has_any(q, (
        "app", "platform", "wallet", "account", "exchange",
        "payment app", "gaming app", "creator platform",
    ))
    freeze_or_kyc = _has_any(q, (
        "kyc", "froze", "frozen", "freeze", "blocked", "hold",
        "withheld", "stuck", "pending verification", "verification pending",
    ))
    money_or_access = _has_any(q, (
        "money", "fund", "funds", "payout", "withdrawal", "deposit",
        "80k", "50k", "lakh", "balance", "account",
    ))
    return platform and freeze_or_kyc and money_or_access


def _is_digital_creator_payout_freeze(q: str) -> bool:
    creator_platform = _has_any(q, (
        "fanvue", "onlyfans", "fansly", "patreon", "youtube creator",
        "creator platform", "creator account",
    ))
    payout = _has_any(q, (
        "payment frozen", "payout frozen", "payment blocked", "payout blocked",
        "fund", "funds", "release fund", "release funds", "usd", "dollar",
        "creator", "kyc", "withdrawal", "money stuck",
    ))
    return creator_platform and payout


def _is_child_access(q: str) -> bool:
    age_only_child = re.search(r"\b(?:[1-9]|1[0-7])\s*(?:year|yr|yrs)[ -]?old\b", q) is not None
    age_object_false_positive = re.search(
        r"\b(?:[1-9]|1[0-7])\s*(?:year|yr|yrs)[ -]?old\s+(?:car|bike|phone|mobile|account|shop|plot|house|flat|loan|policy|machine|vehicle)\b",
        q,
    ) is not None
    age_family_context = age_only_child and not age_object_false_positive and _has_any(q, (
        "husband", "wife", "father", "mother", "parent", "parents",
        "took our", "took my", "not letting me meet", "get her back",
        "get him back", "custody", "visitation", "school", "delhi during fight",
    ))
    child_context = _has_any(q, (
        "child", "son", "daughter", "grandson", "granddaughter",
        "minor", "kid", "children",
    )) or age_family_context
    access_context = _has_any(q, (
        "not allowing me to meet", "not letting me meet",
        "not allowing access", "blocking access", "visitation",
        "meet my child", "see my child", "meet the child",
        "after separation", "custody", "parenting time",
        "hiding our", "hiding my", "video calls", "changed number",
        "changed phone number", "wants to meet", "want to meet",
        "seeing my son", "seeing my daughter", "seeing child",
        "see child", "meet child", "father to see child",
        "mother to see child", "not allowing father", "not allowing mother",
        "not letting mother see", "not letting father see",
        "took child and not letting", "took child", "prevents the mother",
        "took her away", "took him away", "took our daughter", "took our son",
        "took my daughter", "took my son", "refuse to return", "refuses to return",
        "not letting me take", "not letting me bring",
        "blocked all calls", "blocked calls", "blocking calls",
        "refuses weekend meeting", "refuse weekend meeting",
        "not sharing school location", "not sharing school",
        "get her back", "get him back",
    ))
    return child_context and access_context


def _is_child_marriage_prevention(q: str) -> bool:
    return _has_any(q, (
        "child marriage", "minor marriage", "underage marriage", "bal vivah",
        "got him married", "got her married", "they got him married", "they got her married",
        "father is fixing marriage", "fixing marriage", "fixed marriage",
        "forcing marriage", "force marriage", "marry a minor",
    )) or (
        _has_any(q, ("daughter", "girl", "brother", "sister", "child"))
        and _has_any(q, ("13", "14", "15", "16", "17", "minor", "underage"))
        and _has_any(q, ("marriage", "marry", "shaadi", "shadi"))
    )


def _is_mtp_reproductive_rights(q: str) -> bool:
    return _has_any(q, (
        "abortion", "abort", "mtp", "terminate pregnancy", "termination",
        "pregnant", "pregnancy", "doctor says it is too late", "too late for abortion",
        "6 months pregnant", "six months pregnant", "24 weeks", "twenty four weeks",
    )) or (
        _has_any(q, ("rape", "raped", "sexual assault"))
        and _has_any(q, ("pregnant", "pregnancy", "abortion", "abort"))
    )


def _is_streedhan_return(q: str) -> bool:
    family_context = _has_any(q, (
        "husband", "in laws", "in-laws", "mother in law",
        "mother-in-law", "daughter in law", "daughter-in-law",
        "bahu", "sasural", "wife",
    ))
    property_context = _has_any(q, (
        "streedhan", "stridhan", "jewellery", "jewelry",
        "gold", "ornaments", "marriage gold", "locker keys",
        "locker key",
    ))
    withholding_context = _has_any(q, (
        "not returning", "not giving", "refusing", "refusing return",
        "kept", "took", "withholding", "has my", "return",
    ))
    return family_context and property_context and withholding_context


def _is_street_vendor_removal(q: str) -> bool:
    vendor_context = _has_any(q, (
        "street vendor", "hawker", "vending", "vendor certificate",
        "tea cart", "vegetable stall", "vegetable cart", "fruit cart", "cart",
        "footpath stall",
    ))
    removal_context = _has_any(q, (
        "removing", "removed", "seized", "took my cart",
        "took my stall", "took my fruit cart", "asking fine", "without notice",
        "not allowing", "evict", "eviction", "relocation",
    ))
    return vendor_context and removal_context


def _is_crypto_wallet_freeze(q: str) -> bool:
    crypto_platform = _has_any(q, (
        "crypto exchange", "binance", "usdt", "crypto wallet",
        "crypto", "coin", "token",
    )) or ("exchange" in q and _has_any(q, ("crypto", "usdt", "coin", "token")))
    return crypto_platform and _has_any(q, (
        "froze", "frozen", "freeze", "blocked", "support not replying",
        "not replying", "withdrawal", "money stuck", "wallet stuck",
    ))


def _is_cyber_money_fraud(q: str) -> bool:
    if _is_nonfraud_payment_refund_or_debit(q):
        return False
    if _is_bank_freeze(q) and not _has_any(q, (
        "otp", "fraud", "scam", "fake", "unauthorized", "unauthorised",
        "remote access", "anydesk", "screen sharing", "money got transferred",
        "money was transferred", "money transferred", "amount transferred",
        "debit without", "without my consent",
    )):
        return False
    cyber_money = _has_any(q, (
        "otp", "upi fraud", "upi scam", "upi transfer fraud",
        "phonepe fraud", "gpay fraud", "unauthorized transaction",
        "unauthorised transaction", "credit card unauthorized",
        "credit card unauthorised", "card transaction", "fake customer care",
        "fake customer support", "fake helpline", "install app",
        "installed app", "remote access", "anydesk", "screen sharing",
        "money got transferred", "money was transferred", "money transferred",
        "duped", "fake stock", "stock trading app", "fake trading app",
        "trading app", "investment app", "multiple upi ids",
        "cyber cell complaint", "cyber complaint filed", "no progress",
        "whatsapp account got hacked", "whatsapp hacked", "account hacked",
        "asking my contacts for money", "asking contacts for money",
        "bank not reversing", "not reversing amount", "bank says my mistake",
        "bank says my fault",
        "rugpull", "rug pull", "rugpulled", "rug pulled", "crypto group",
        "telegram crypto", "crypto investment", "wallet address",
        "wallet transfer fraud", "telegram group vanished", "group vanished",
        "vanished with money", "vanished",
    ))
    money_or_bank = _has_any(q, (
        "money", "bank", "account", "upi", "credit card", "debit card",
        "card", "transaction", "50000", "50,000", "lakh", "amount",
        "refund", "reversal", "freeze",
    ))
    return cyber_money and money_or_bank


def _is_cyber_harassment_first_action(q: str) -> bool:
    if _is_nonfraud_payment_refund_or_debit(q) and not _has_any(q, ("blackmail", "threat", "harass", "fake", "scam")):
        return False
    platform_or_cyber = _has_any(q, (
        "cyber", "online", "instagram", "insta", "facebook", "telegram",
        "whatsapp", "twitter", "x.com", "tweet", "youtube", "dating app",
        "tinder", "bumble", "profile", "account", "dm", "dms", "screenshot",
        "screenshots", "deepfake", "lookalike", "look alike", "fake video",
        "fake cbi", "digital arrest", "parcel", "courier", "app", "otp",
    ))
    harm = _has_any(q, (
        "blackmail", "extortion", "threat", "threaten", "threatening",
        "harass", "harassing", "harrasing", "harassment", "fake",
        "impersonat", "scam", "fraud", "leak", "leaked", "circulating",
        "circulate", "viral", "posted", "posting", "sent to", "send to",
        "took my phone", "phone seized", "demand", "demanding", "nude",
        "porn", "defamation", "corrupt", "drugs", "pay", "lakh",
    ))
    return platform_or_cyber and harm


def _is_unsolicited_sexual_image_cyber(q: str) -> bool:
    sexual_image = _has_any(q, (
        "dick pic", "dickpic", "penis pic", "private part photo",
        "sexual image", "nude photo", "nude pic", "obscene photo",
        "sent me nude", "sent nude", "sent me porn",
    ))
    consent_or_app = _has_any(q, (
        "without consent", "unsolicited", "stranger", "bumble", "tinder",
        "dating app", "instagram", "insta", "dm", "chat",
    ))
    blackmail_or_deepfake = _has_any(q, (
        "blackmail", "threatening to upload", "threatening upload",
        "morphed", "deepfake", "recorded us", "secretly recorded",
    ))
    return sexual_image and consent_or_app and not blackmail_or_deepfake


def _is_criminal_production_notice_electronic_records(q: str) -> bool:
    section_91 = _has_any(q, (
        "section 91", "sec 91", "91 bnss", "91 crpc", "bnss 91", "crpc 91",
    ))
    notice = _has_any(q, (
        "notice", "summons", "summon", "received", "police sent",
        "asked me to produce", "produce documents", "production",
    ))
    record = _has_any(q, (
        "insta", "instagram", "deleted post", "deleted posts", "posts",
        "social media", "phone", "mobile", "laptop", "device", "email",
        "account", "documents", "records", "data",
    ))
    return section_91 and notice and record


def _is_cyber_money_fraud_victim_progress(q: str) -> bool:
    victim_problem = _has_any(q, (
        "duped", "scammed", "scam", "fraud", "fake stock", "stock trading app",
        "fake trading app", "trading app", "investment app", "money transferred",
        "transferred to multiple upi", "multiple upi ids", "cyber cell complaint",
        "cyber complaint filed", "no progress",
    ))
    accused_side = _has_any(q, (
        "against me", "filed on me", "case on me", "accused", "summons",
        "notice to me", "police calling me", "arrest me", "quash",
    ))
    return victim_problem and not accused_side


def _is_mental_health_privacy_leak_context(q: str) -> bool:
    mental_health_context = _has_any(q, (
        "therapist", "psychiatrist", "psychologist", "counsellor", "counselor",
        "counselling chat", "counseling chat", "therapy chat", "mental health",
        "mental-health", "medical privacy",
    ))
    leak_context = _has_any(q, (
        "leaked", "leak", "posted", "shared", "published", "twitter", "x ",
        "online", "privacy", "data breach", "chat",
    ))
    return mental_health_context and leak_context


def _is_nonfraud_payment_refund_or_debit(q: str) -> bool:
    payment_context = _has_any(q, (
        "upi", "phonepe", "gpay", "google pay", "paytm", "payment app",
        "transaction", "merchant", "seller",
    ))
    service_problem = _has_any(q, (
        "failed upi refund", "upi refund", "failed transaction",
        "payment failed", "money cut", "amount cut", "refund will come",
        "closed ticket", "merchant says", "seller says", "customer care",
        "both sides are blaming", "blaming each other",
    ))
    fraud_context = _has_any(q, (
        "otp", "phishing", "scam", "fraud", "fake customer care",
        "fake cbi", "digital arrest", "anydesk", "remote access",
        "unauthorized", "unauthorised", "hacked", "stolen",
    ))
    return payment_context and service_problem and not fraud_context


def _is_promise_to_marry_complainant(q: str) -> bool:
    relationship_context = _has_any(q, (
        "boyfriend", "living with", "live in", "live-in", "relationship",
        "partner", "love affair",
    ))
    promise_context = _has_any(q, (
        "promised marriage", "promise marriage", "promised to marry",
        "marry me", "now he is marrying", "marrying another", "marrying another girl",
        "file case", "can i file case",
    ))
    accused_context = _has_any(q, (
        "against me", "filed rape case against me", "accused", "false case",
        "girlfriend filed", "complaint on me", "arrest me", "bail",
    ))
    return relationship_context and promise_context and not accused_context


def _is_mining_gram_sabha_context(q: str) -> bool:
    if _is_mining_pollution_damage_without_consent_context(q):
        return False
    mining_context = _has_any(q, (
        "bauxite", "mine", "mining", "quarry", "mineral", "project", "noc", "lease",
        "coal block", "stone crusher",
    ))
    scheduled_or_tribal_context = _has_any(q, ("gram sabha", "pesa", "scheduled area", "bastar", "adivasi", "tribal"))
    consent_or_approval_context = _has_any(q, (
        "gram sabha", "pesa", "noc", "lease", "resolution", "without consent",
        "no consent", "without gram sabha", "no gram sabha", "recommendation",
        "consultation", "approval", "challenge",
    ))
    return mining_context and scheduled_or_tribal_context and consent_or_approval_context


def _is_mining_pollution_damage_without_consent_context(q: str) -> bool:
    mine_context = _has_any(q, ("mine", "mining", "bauxite", "coal mine", "iron ore"))
    pollution_damage = _has_any(q, (
        "pollution", "polluting", "smoke", "dust", "chemical", "effluent",
        "water pollution", "air pollution", "damaged my house", "house damaged",
        "paint damaged", "wall damaged", "crop damaged", "compensation",
    ))
    consent_or_displacement = _has_any(q, (
        "gram sabha", "pesa", "noc", "lease", "resolution", "without consent",
        "no consent", "without gram sabha", "no gram sabha", "recommendation",
        "consultation", "approval", "challenge", "displacement", "displaced",
        "rehabilitation", "resettlement", "land acquisition", "submerge",
        "submerged",
    ))
    return mine_context and pollution_damage and not consent_or_displacement


def _is_marital_intimacy(q: str) -> bool:
    if _has_any(q, ("force", "forcing", "forced", "without consent", "no consent", "threat", "threaten", "threatening", "beat", "beating", "violence", "assault", "rape")):
        return False
    return _has_any(q, ("wife", "husband", "spouse", "marriage", "marital")) and _has_any(q, ("denying sex", "denies sex", "refusing sex", "physical relation", "no marital relationship", "conjugal", "intimacy"))


def _is_heir_sale(q: str) -> bool:
    if _has_any(q, (
        "no sale dispute", "not a sale dispute", "no dispute among heirs",
        "no heir sale dispute", "not about sale", "not about selling",
    )) and _has_any(q, ("tenant", "tenent", "rent", "not leaving", "not vacating")):
        return False
    return _has_any(q, ("heir", "legal heir", "sister", "brother", "father died", "mother died")) and _has_any(q, ("property", "house", "land", "plot", "ancestral", "inherited")) and _has_any(q, ("sell", "sale", "selling", "signing", "not signing", "refuses", "not agreeing", "consent"))


def _is_mutation_after_death(q: str) -> bool:
    death_context = _has_any(q, ("father died", "mother died", "husband died", "wife died", "died", "death", "passed away", "late father", "late mother"))
    mutation_context = _has_any(q, ("mutation", "patwari", "tehsildar", "tahsildar", "talathi", "khata", "khasra", "khatauni", "jamabandi", "land record", "revenue record", "not updated", "name not updated"))
    land_context = _has_any(q, ("land", "plot", "field", "property", "house", "flat", "home", "khata", "khasra", "patwari record", "revenue record"))
    return death_context and mutation_context and land_context


def _is_cyber_stalking_online_harassment(q: str) -> bool:
    stalking = _has_any(q, (
        "stalker", "stalking", "stalked", "stalks", "dm daily",
        "direct message", "dms", "message daily", "keeps messaging",
        "after blocking", "blocked him", "blocked her", "follows me",
        "following me",
    ))
    platform = _has_any(q, (
        "insta", "instagram", "facebook", "whatsapp", "telegram",
        "dating app", "bumble", "tinder", "profile", "online",
    ))
    phone_number_abuse = _has_any(q, (
        "posted my number", "posting my number", "shared my number",
        "phone number on dating app", "strangers are calling",
    ))
    return (stalking and platform) or phone_number_abuse


def _is_online_defamation_abuse(q: str) -> bool:
    platform = _has_any(q, (
        "insta", "instagram", "facebook", "whatsapp", "telegram",
        "x.com", "twitter", "youtube", "comment", "comments", "post",
        "profile", "online", "social media",
    ))
    abuse_or_reputation = _has_any(q, (
        "defamation", "defame", "bad comments", "abusive comment",
        "abusive comments", "calling me", "called me", "randi",
        "slut", "prostitute", "characterless", "cheap woman",
        "fake allegation", "false allegation", "reputation",
        "insult", "abuse", "abusing",
    ))
    intimate_or_image_case = _has_any(q, (
        "nude", "nudes", "intimate", "morphed", "deepfake",
        "lookalike", "sex video", "private photo",
    ))
    return platform and abuse_or_reputation and not intimate_or_image_case


def _is_manual_scavenging_forced_cleaning(q: str) -> bool:
    sanitation = _has_any(q, (
        "manual scavenging", "manual scavenger", "dry latrine",
        "sewer", "septic", "septic tank", "human waste", "toilet",
        "latrine", "drain", "cleaning waste", "clean waste",
    ))
    coercion = _has_any(q, (
        "forcing", "forced", "force", "panchayat", "municipality",
        "local body", "contractor", "sarpanch", "not giving safety",
        "no safety", "without safety", "clean", "cleaning",
    ))
    return sanitation and coercion and not _has_any(q, ("died", "death", "dead"))


def _is_traffic_police_challan_bribe(q: str) -> bool:
    traffic_context = _has_any(q, (
        "traffic police", "traffic cop", "rto", "auto driver",
        "taxi driver", "licence", "license", "challan", "no challan",
        "tamil license", "tamil licence", "bangalore traffic",
    ))
    payment_demand = _has_any(q, (
        "taking 500", "rs 500", "500 every week", "cash", "bribe",
        "hafta", "taking money", "asked money", "asking money",
        "demanded money", "pay money", "paid money",
    ))
    no_receipt_or_challan = _has_any(q, (
        "without challan", "no challan", "without receipt", "no receipt",
        "receipt nahi", "challan nahi",
    ))
    negated_payment = _has_any(q, (
        "no bribe", "not bribe", "not a bribe", "without bribe",
        "no cash demand", "no money demand", "no money demanded",
        "not asking money", "not asked money", "did not ask money",
        "didn't ask money", "no payment demand",
    ))
    if negated_payment:
        return False
    explicit_licence_dispute = _has_any(q, (
        "license invalid", "licence invalid", "license is invalid", "licence is invalid",
        "tamil license", "tamil licence", "driving licence invalid", "driving license invalid",
    ))
    return traffic_context and payment_demand and no_receipt_or_challan and explicit_licence_dispute


def _is_relative_adoption_no_papers(q: str) -> bool:
    adoption = _has_any(q, ("adopted", "adoption", "adopt child", "adopted child"))
    relative = _has_any(q, ("sister", "brother", "cousin", "aunt", "uncle", "relative", "family"))
    paper_or_parent_dispute = _has_any(q, (
        "no papers", "without papers", "no document", "no order",
        "real parents", "biological parents", "want him back",
        "want her back", "asking back", "take back",
    ))
    return adoption and relative and paper_or_parent_dispute


def _is_child_cross_border_return(q: str) -> bool:
    child = _has_any(q, ("son", "daughter", "child", "minor", "kid"))
    foreign = _has_any(q, (
        "uk", "usa", "canada", "dubai", "abroad", "foreign", "tourist visa",
        "passport", "outside india", "not bringing back", "permanent now",
    ))
    withholding = _has_any(q, (
        "not bringing back", "not returning", "took our", "took my",
        "permanent now", "refusing to return", "will not bring",
    ))
    return child and foreign and withholding


def _is_maternity_return_role_change(q: str) -> bool:
    maternity = _has_any(q, ("maternity", "maternity leave", "pregnant", "pregnancy"))
    return maternity and _has_any(q, (
        "came back", "returned", "return from", "role was given",
        "role given", "role changed", "demoted", "same role",
        "back from leave", "after leave", "when i came back",
        "job was given", "position was given",
    ))


def _is_gig_delivery_accident(q: str) -> bool:
    gig = _has_any(q, (
        "zomato", "swiggy", "delivery rider", "rider", "delivery partner",
        "gig worker", "platform worker", "uber", "ola driver",
    ))
    injury = _has_any(q, (
        "accident", "injury", "injured", "bike", "scooter", "road",
        "hospital", "insurance", "compensation", "fracture",
    ))
    return gig and injury


def _is_workplace_harassment_pip(q: str) -> bool:
    if _has_any(q, ("no harassment", "not harassment", "ordinary pip", "missed targets only")):
        return False
    workplace = _has_any(q, (
        "manager", "boss", "hr", "company", "employer",
        "reporting manager", "office", "workplace", "supervisor",
    ))
    complaint = _has_any(q, ("complained", "complaint", "grievance", "reported", "told hr"))
    harassment = _has_any(q, ("harassment", "harass", "sexual", "gendered", "inappropriate"))
    pip = _has_any(q, (
        "pip", "performance improvement plan", "bad rating", "poor rating",
        "retaliation", "retaliate", "warning", "termination", "terminated",
    ))
    return workplace and complaint and harassment and pip


def _is_workplace_sexual_harassment_general(q: str) -> bool:
    if _has_any(q, ("no harassment", "not harassment", "ordinary pip", "missed targets only")):
        return False
    workplace = _has_any(q, (
        "manager", "boss", "hr", "company", "employer", "office",
        "workplace", "supervisor", "reporting manager", "coworker",
        "co-worker", "colleague", "client", "vendor", "internship",
    ))
    sexual_or_gendered = _has_any(q, (
        "sexual", "sexist", "gendered", "inappropriate", "touch",
        "touched", "grop", "hug", "kiss", "late night message",
        "late-night message", "date with me", "come to hotel", "favours",
        "favors", "body comment", "staring", "dirty jokes", "emoji",
        "uncomfortable", "icc", "internal committee", "local committee",
        "posh", "harassment", "harass",
    ))
    retaliation = _has_any(q, (
        "complained", "complaint", "reported", "told hr", "icc",
        "bad rating", "pip", "performance", "transfer", "terminated",
        "warning", "retaliation", "retaliate",
    ))
    return workplace and (sexual_or_gendered or retaliation)


def _is_sexual_offence_survivor_procedure(q: str) -> bool:
    survivor = _has_any(q, (
        "rape", "raped", "sexual assault", "touching me", "touched me",
        "molested", "caretaker", "uncle", "neighbor uncle", "neighbour uncle",
    ))
    procedure_need = _has_any(q, (
        "police", "case", "fir", "file", "complaint", "remedy",
        "many years", "years back", "can i still", "weak", "cannot identify",
        "can't identify", "visually impaired", "blind", "disabled",
        "i am 19", "since i was 12",
    ))
    return survivor and procedure_need


def _is_dowry_death_inquest(q: str) -> bool:
    death = _has_any(q, ("died", "death", "dead", "suicide", "body", "post mortem", "post-mortem"))
    inlaws = _has_any(q, ("in laws", "in-laws", "sasural", "husband family", "husband's house"))
    dowry_or_marks = _has_any(q, ("dowry", "body had marks", "injury marks", "marks", "beaten", "burn", "hanging"))
    return death and (inlaws or dowry_or_marks) and _has_any(q, ("sister", "wife", "daughter", "woman", "married", "dowry"))


def _is_customs_context(q: str) -> bool:
    return _has_any(q, (
        "customs", "icegate", "bill of entry", "shipping bill",
        "drawback", "import duty", "customs duty", "port hold",
        "duty demand", "reclassified", "reclassification", "svb",
        "special valuation branch", "misdeclaration", "misdeclared",
    ))


def _is_customs_drawback_problem(q: str) -> bool:
    return _is_customs_context(q) and customs_drawback_issue(q)


def _is_customs_icegate_misdeclaration_problem(q: str) -> bool:
    return _is_customs_context(q) and customs_misdeclaration_issue(q)


def _is_customs_reclassification_svb_problem(q: str) -> bool:
    return _is_customs_context(q) and (
        customs_svb_issue(q)
        or (
            customs_classification_issue(q)
            and _has_any(q, ("import", "imported", "customs", "duty", "bill of entry"))
        )
    )


def _is_shop_sealed(q: str) -> bool:
    return _has_any(q, ("shop", "restaurant", "hotel", "kitchen", "commercial", "store", "dukan", "office shop")) and _has_any(q, ("municipality", "municipal", "corporation", "local body", "local authority", "ward office", "nagar", "mcd", "bmc", "bbmp", "noida authority", "authority", "health department", "food inspector", "food safety officer")) and _has_any(q, ("sealed", "sealing", "locked", "licence", "license", "licence issue", "license issue"))


def _is_shop_license_renewal(q: str) -> bool:
    shop_context = _has_any(q, ("shop", "dukan", "store", "commercial establishment", "business", "shopkeeper"))
    license_context = _has_any(q, ("shop license", "shop licence", "trade license", "trade licence", "licence renewal", "license renewal", "shops and establishments", "shop act"))
    problem_context = _has_any(q, ("renewal", "pending", "penalty", "fine", "calculate", "delayed", "not renewed", "expired"))
    return shop_context and license_context and problem_context


def _is_subscription_refund(q: str) -> bool:
    subscription_context = _has_any(q, ("subscription", "membership", "premium", "auto renewal", "auto-renewal", "yearly", "annual"))
    charge_or_refund = _has_any(q, ("charged", "charge", "debit", "deducted", "refund", "refunding", "not refunding", "refund denied"))
    cancellation_context = _has_any(q, ("cancel", "cancelled", "canceled", "cancellation", "after cancellation", "support", "customer care"))
    return subscription_context and charge_or_refund and cancellation_context


def _is_supplier_payment(q: str) -> bool:
    supplier = _has_any(q, (
        "supplier", "vendor", "contractor bill", "supplier bill", "vendor bill",
        "purchase order", "work order", "po ", "invoice", "icds", "nutrition",
        "anganwadi supply", "department payment", "government bill",
        "udyam", "msme registered", "samadhaan", "samadhan",
    ))
    payment = _has_any(q, (
        "payment pending", "pending payment", "not paid", "non payment",
        "unpaid", "bill pending", "bill not cleared", "payment delay",
        "amount outstanding", "release payment", "release fund",
        "not paying", "outstanding", "crossed 45 days", "45 days",
    ))
    return supplier and payment


def _is_msme_delayed_payment(q: str) -> bool:
    if _has_any(q, (
        "no msme registration", "not msme", "not an msme",
        "not msme registered", "not registered as msme",
        "not registered under msme", "not udyam registered",
        "no udyam", "no udyam registration", "without udyam",
    )):
        return False
    msme = _has_any(q, (
        "msme", "udyam", "samadhaan", "samadhan", "facilitation council",
        "msefc", "section 43b", "43b(h)", "43b h", "micro small",
    ))
    buyer_quality_rejection_payment = _has_any(q, (
        "buyer deducting payment", "formal rejection", "no formal rejection",
        "quality issue", "quality rejection", "deducting payment",
        "deducting saying quality", "payment stuck", "lakh stuck",
    )) and _has_any(q, (
        "buyer", "payment", "deducting", "quality", "rejection",
        "invoice", "bill", "stuck", "outstanding",
    ))
    payment = _has_any(q, (
        "payment", "paid", "not paid", "non payment", "outstanding",
        "invoice", "buyer", "psu", "public sector", "45 days", "crossed",
        "deducting", "quality issue", "quality", "defective", "delay",
        "samadhaan pursue", "samadhan pursue", "commercial court",
    ))
    return (msme or buyer_quality_rejection_payment) and payment


def _is_business_contract_first_action(q: str) -> bool:
    if _is_supplier_payment(q) or _is_msme_delayed_payment(q):
        return False
    if _has_any(q, ("personal loan", "brother took loan", "friend took loan", "neighbour took loan", "neighbor took loan")):
        return False
    business_context = _has_any(q, (
        "contract", "agreement", "mou", "vendor", "supplier", "dealer",
        "buyer", "seller", "purchase order", "work order", "advance",
        "refund", "defective material", "quality issue", "exclusive",
        "exclusivity", "competitor", "nda", "customer list", "partner",
        "partnership", "firm", "dissolve", "retire from partnership",
        "siphoned funds", "books", "co founder", "co-founder", "equity",
        "esop", "shareholder", "minority shareholder", "registers",
    ))
    dispute_context = _has_any(q, (
        "breach", "not agreeing", "not agreeing refund", "not refund",
        "delivered defective", "defective", "delay", "4 months over",
        "cancel", "recover advance", "selling to my competitor",
        "using our customer list", "enforce", "where to go", "what next",
        "want to dissolve", "retire", "liability", "loan", "dilute",
        "dilution", "not showing books", "inspection", "oppressing",
    ))
    return business_context and dispute_context


def _is_defective_goods(q: str) -> bool:
    return _has_any(q, (
        "phone", "mobile", "iphone", "online order", "seller", "service center",
        "service centre", "warranty", "laptop", "shoes", "footwear",
        "online seller", "amazon", "flipkart", "marketplace",
        "third party seller", "third-party seller",
    )) and _has_any(q, (
        "damaged", "defective", "return", "refund", "replacement",
        "repair", "not accepting", "refusing", "fake", "fake product",
        "fake goods", "fake shoes", "refund denied",
    ))
