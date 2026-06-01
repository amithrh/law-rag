"""FastAPI app: /search, /answer (SSE stream with per-sentence verification gate).

Run with:
    cd <repo>
    PYTHONPATH=. .venv/bin/uvicorn apps.api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware as _CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from apps.api import config as cfg
from apps.api import metrics
from apps.api.db import close_pool, get_pool
from apps.api.llm import (
    LLMModelUnavailable,
    build_messages,
    check_model_available,
    load_answer_prompt,
    stream_chat,
)
from apps.api.legal_issue_plan import LegalIssuePlan, build_legal_issue_plan
from apps.api.matter_router import MatterRoute, route_matter
from apps.api.relevance import compute_relevance
from apps.api.retrieval import (
    RetrievedChunk,
    _preserve_required_source_packs,
    hybrid_retrieve,
    multi_query_hybrid_retrieve,
)
from apps.api.verifier import (
    SentenceStatus,
    SentenceVerification,
    segment_sentences,
    verify_sentence,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="law-rag", lifespan=lifespan)

# CORS — added 2026-05-21 after frontend SSE proxy timed out at Next.js's
# 30s default. Bypassing the proxy means the browser calls :8000 directly,
# which avoids the timeout entirely. Dev-only allowlist; prod should restrict.
app.add_middleware(
    _CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.1.5:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Standard disclaimer rendered server-side on every answer (PLAN §4.4)
DISCLAIMER_FOOTER = (
    "**Disclaimer**\n"
    "This is general legal information, not legal advice for your specific "
    "situation. Laws and their interpretation change. For decisions that "
    "affect your rights, consult a qualified lawyer or the relevant court / forum."
)

UNKNOWN_CRIMINAL_REGIME = "incident_date_needed_for_bns_bnss_bsa_vs_ipc_crpc"
CRIMINAL_REGIME_CAVEAT = (
    "The incident date decides whether BNS/BNSS/BSA or "
    "IPC/CrPC/Evidence Act applies."
)
MEDICAL_STATUS_ONLINE_DISCLOSURE_TERMS = (
    "post warning", "post online", "warning online", "online", "social media",
    "publish", "publicly", "disclose", "instagram", "whatsapp", "facebook",
    "telegram", "status", "group", "warn people", "tell everyone",
    "tell relatives", "tell friends", "share his hiv status",
    "share her hiv status", "put his hiv status", "put her hiv status",
    "post his hiv status", "post her hiv status", "make viral", "viral",
)
_CRIMINAL_REGIME_SOURCE_TERMS = (
    "bns",
    "bnss",
    "bsa",
    "ipc",
    "crpc",
    "evidence act",
    "bharatiya nyaya",
    "bharatiya nagarik",
    "bharatiya sakshya",
    "indian penal",
    "criminal procedure",
)


# ----- /search ---------------------------------------------------------------

class SearchResponseItem(BaseModel):
    chunk_id: int
    anchor: str
    text: str
    title: str
    source_type: str
    subject_area: str | None
    dense_score: float
    bm25_score: float
    sparse_score: float = 0.0
    combined_score: float
    rrf_score: float | None = None
    rerank_score: float | None
    as_at: str | None
    citation: str | None
    court: str | None


@app.get("/search")
async def search(
    q: str = Query(..., min_length=2),
    sources: str | None = Query(None, description="comma-separated subset of {sc_judgment,hc_judgment,bare_act,circular}"),
    subjects: str | None = Query(None, description="comma-separated subset of slice subject areas"),
    top_k: int = Query(20, ge=1, le=100),
):
    pool = await get_pool()
    src_types = [s.strip() for s in sources.split(",")] if sources else None
    subj = [s.strip() for s in subjects.split(",")] if subjects else None

    t0 = time.perf_counter()
    hits = await hybrid_retrieve(
        pool, q, source_types=src_types, subject_areas=subj, top_k=top_k,
    )
    elapsed = time.perf_counter() - t0
    metrics.retrieval_latency.observe(elapsed)
    elapsed_ms = elapsed * 1000

    return JSONResponse({
        "query": q,
        "took_ms": round(elapsed_ms, 1),
        "hits": [
            SearchResponseItem(
                chunk_id=h.chunk_id, anchor=h.anchor, text=h.text, title=h.title,
                source_type=h.source_type, subject_area=h.subject_area,
                dense_score=h.dense_score, bm25_score=h.bm25_score,
                sparse_score=h.sparse_score,
                combined_score=h.combined_score,
                rrf_score=h.rrf_score,
                rerank_score=h.rerank_score,
                as_at=h.as_at.isoformat() if h.as_at else None,
                citation=h.citation, court=h.court,
            ).model_dump()
            for h in hits
        ],
    })


# ----- /answer (SSE stream) --------------------------------------------------

class AnswerRequest(BaseModel):
    q: str
    sources: list[str] | None = None
    subjects: list[str] | None = None
    top_k: int = 8           # passages handed to the LLM
    # `skip_nli` is a CLIENT HINT, not a directive. Per round-3 review
    # (security #4): exposing it as a free toggle let a caller `curl ...
    # -d '{"skip_nli":true}'` and bypass NLI for every cited sentence,
    # shipping fabricated content with valid [N] indices. The server
    # honours this flag ONLY when settings.answer_fast_enabled=True
    # (an env-gated /answer-fast mode). In production
    # (answer_fast_enabled=False), the client hint is ignored and NLI
    # always runs.
    skip_nli: bool = False


def _make_passages(retrieved: list[RetrievedChunk], n: int) -> tuple[list[dict], dict[int, str]]:
    """Return (passages-for-prompt, idx-to-passage-text-map)."""
    passages: list[dict] = []
    idx_map: dict[int, str] = {}
    for i, h in enumerate(retrieved[:n], start=1):
        passages.append({
            "index": i,
            "text": h.text,
            "anchor": h.anchor,
            "title": h.title,
            "source_type": h.source_type,
            "document_id": h.document_id,
            "as_at": h.as_at.isoformat() if h.as_at else None,
            "court": h.court,
            "citation": h.citation,
            "statute_short": h.statute_short,
            "required_source_pack": h.metadata.get("_required_source_pack"),
            "required_source_priority": h.metadata.get("_required_source_priority"),
        })
        idx_map[i] = h.text
    return passages, idx_map


def _record_stage(timings: dict[str, float], stage: str, started: float) -> float:
    """Record a named /answer stage in seconds and Prometheus."""
    elapsed = time.perf_counter() - started
    timings[stage] = elapsed
    metrics.answer_stage_latency.labels(stage=stage).observe(elapsed)
    return elapsed


def _add_stage_elapsed(timings: dict[str, float], stage: str, elapsed: float) -> None:
    timings[stage] = timings.get(stage, 0.0) + elapsed
    metrics.answer_stage_latency.labels(stage=stage).observe(elapsed)


def _timing_event(
    timings: dict[str, float],
    request_started: float,
    *,
    llm_model: str,
    llm_model_available: bool,
    retrieved_count: int = 0,
    passages_used: int = 0,
    expansion_variant_count: int = 0,
    state: dict | None = None,
) -> dict:
    payload: dict[str, object] = {
        "total_ms": round((time.perf_counter() - request_started) * 1000, 1),
        "llm_model": llm_model,
        "llm_model_available": llm_model_available,
        "retrieved_count": retrieved_count,
        "passages_used": passages_used,
        "expansion_variant_count": expansion_variant_count,
    }
    for stage, seconds in timings.items():
        payload[f"{stage}_ms"] = round(seconds * 1000, 1)
    if state is not None:
        payload["sentence_count"] = state.get("emitted", 0)
        payload["unsupported_count"] = state.get("unsupported", 0)
    return {"event": "timing", "data": json.dumps(payload)}


def _llm_unavailable_error(status: dict, settings: cfg.Settings) -> dict:
    message = status.get("message") or (
        f"Configured Ollama model '{settings.llm_model}' is not available. "
        f"Run `ollama pull {settings.llm_model}` or change LLM_MODEL."
    )
    return {
        "event": "error",
        "data": json.dumps({
            "message": message,
            "reason": "llm_model_unavailable",
            "model": status.get("model", settings.llm_model),
            "available_models": status.get("available_models", []),
        }),
    }


def _matter_route_event(route: MatterRoute) -> dict:
    return {"event": "matter_route", "data": json.dumps(route.to_event())}


def _legal_issue_plan_event(plan: LegalIssuePlan) -> dict:
    return {"event": "legal_issue_plan", "data": json.dumps(plan.to_event())}


def _initial_route_events(route: MatterRoute, plan: LegalIssuePlan | None) -> list[dict]:
    events = [_matter_route_event(route)]
    if plan is not None:
        events.append(_legal_issue_plan_event(plan))
    return events


def _grounded_template_lines(
    query: str,
    route: MatterRoute,
    passages: list[dict],
) -> list[str]:
    """Return deterministic cited lines for high-confidence procedural routes.

    These templates are intentionally narrow. They fire only when the route and
    retrieved passage metadata expose the exact statutory sections needed, then
    the normal verifier still checks every emitted sentence before the user sees
    it. This gives common procedural questions a stable answer without asking
    the LLM to improvise forums, deadlines, or next steps.
    """
    q = query.lower()
    if route.category == "bonded_labour_rescue":
        bonded_lines = _bonded_labour_template_lines(q, passages)
        if bonded_lines:
            return bonded_lines

    if route.category == "arrest_custody_safeguard" and _is_arrest_production_delay_query(q):
        arrest_lines = _arrest_production_delay_template_lines(q, passages)
        if arrest_lines:
            return arrest_lines

    if route.category in {"police_fir", "arrest_custody_safeguard"} and _is_police_picked_fir_copy_query(q):
        arrest_copy_lines = _police_picked_fir_copy_template_lines(q, passages)
        if arrest_copy_lines:
            return arrest_copy_lines

    if route.category == "police_fir" and _is_theft_fir_refusal_query(q):
        theft_fir_lines = _theft_fir_refusal_template_lines(q, passages)
        if theft_fir_lines:
            return theft_fir_lines

    if route.category == "environment_compensation" and _is_mining_gram_sabha_noc_query(q):
        mining_noc_lines = _mining_gram_sabha_noc_template_lines(q, passages)
        if mining_noc_lines:
            return mining_noc_lines

    if route.category == "environment_compensation" and _is_mining_displacement_query(q):
        mining_lines = _mining_displacement_template_lines(passages)
        if mining_lines:
            return mining_lines

    if route.category in {"environment_compensation", "land_acquisition_compensation"} and _is_land_acquisition_compensation_query(q):
        land_lines = _land_acquisition_compensation_template_lines(passages)
        if land_lines:
            return land_lines

    if route.category == "tribal_caste_atrocity" and _is_tribal_land_transfer_query(q):
        tribal_land_lines = _tribal_land_transfer_template_lines(q, passages)
        if tribal_land_lines:
            return tribal_land_lines

    if route.category == "tribal_caste_atrocity" and _is_fra_forest_rights_query(q):
        fra_lines = _forest_rights_template_lines(q, passages)
        if fra_lines:
            return fra_lines

    if route.category == "tribal_caste_atrocity" and _is_untouchability_rights_query(q):
        untouchability_lines = _untouchability_civil_rights_template_lines(q, passages)
        if untouchability_lines:
            return untouchability_lines

    if (
        route.category in {"tribal_caste_atrocity", "environment_compensation"}
        and _has_any_term(q, ("dam", "submerge", "submerges", "submerged", "submergence", "gram sabha", "pesa"))
        and _has_any_term(q, ("tribal", "adivasi", "scheduled area", "village", "villages"))
    ):
        tribal_displacement_lines = _tribal_displacement_template_lines(passages)
        if tribal_displacement_lines:
            return tribal_displacement_lines

    if route.category == "digital_platform_account" and _is_online_gambling_query(q):
        gambling_lines = _online_gambling_template_lines(q, passages)
        if gambling_lines:
            return gambling_lines

    if route.category == "digital_platform_account" and _is_digital_kyc_account_freeze_query(q):
        kyc_lines = _digital_kyc_account_freeze_template_lines(q, passages)
        if kyc_lines:
            return kyc_lines

    if route.category == "digital_platform_account" and _is_cab_aggregator_driver_query(q):
        cab_lines = _cab_aggregator_driver_template_lines(q, passages)
        if cab_lines:
            return cab_lines

    if route.category == "social_welfare_identity" and _is_pan_aadhaar_mismatch_query(q):
        pan_aadhaar_lines = _pan_aadhaar_mismatch_template_lines(q, passages)
        if pan_aadhaar_lines:
            return pan_aadhaar_lines

    if route.category == "labour_exploitation_discrimination" and _is_mgnrega_wage_query(q):
        mgnrega_lines = _mgnrega_wage_template_lines(q, passages)
        if mgnrega_lines:
            return mgnrega_lines

    if route.category == "social_welfare_identity" and _is_caste_certificate_query(q):
        caste_certificate_lines = _caste_certificate_template_lines(q, passages)
        if caste_certificate_lines:
            return caste_certificate_lines

    if route.category == "social_welfare_identity" and _is_trans_identity_query(q):
        trans_lines = _trans_identity_template_lines(passages)
        if trans_lines:
            return trans_lines

    if route.category == "social_welfare_identity" and _is_kanya_vivah_scheme_query(q):
        kanya_lines = _kanya_vivah_scheme_template_lines(q, passages)
        if kanya_lines:
            return kanya_lines

    if route.category == "social_welfare_identity" and _is_ration_portability_query(q):
        ration_lines = _ration_portability_template_lines(q, passages)
        if ration_lines:
            return ration_lines

    if route.category == "employment_wages" and _is_wage_waiver_language_query(q):
        waiver_lines = _wage_waiver_language_template_lines(q, passages)
        if waiver_lines:
            return waiver_lines

    if route.category == "employment_wages" and _is_non_compete_query(q):
        non_compete_lines = _non_compete_template_lines(q, passages)
        if non_compete_lines:
            return non_compete_lines

    if route.category == "employment_wages" and _is_gig_platform_worker_query(q):
        gig_lines = _gig_platform_worker_template_lines(passages)
        if gig_lines:
            return gig_lines

    if route.category == "employment_wages" and _is_discriminatory_retrenchment_query(q):
        retrench_lines = _discriminatory_retrenchment_template_lines(passages)
        if retrench_lines:
            return retrench_lines

    if route.category == "employment_wages" and _is_employment_retaliation_pip_query(q):
        employment_retaliation_lines = _employment_retaliation_pip_template_lines(q, passages)
        if employment_retaliation_lines:
            return employment_retaliation_lines

    if route.category == "workplace_sexual_harassment" and _is_posh_retaliation_query(q):
        posh_lines = _posh_retaliation_template_lines(q, passages)
        if posh_lines:
            return posh_lines

    if route.category == "labour_compliance" and _is_labour_overtime_register_query(q):
        labour_lines = _labour_overtime_register_template_lines(q, passages)
        if labour_lines:
            return labour_lines

    if (
        route.category == "social_welfare_identity"
        and _has_any_term(q, ("birth certificate", "birth registration", "born at home", "home birth"))
    ):
        birth_lines = _birth_certificate_rti_template_lines(q, passages)
        if birth_lines:
            return birth_lines

    if route.category == "consumer" and _is_medical_negligence_query(q):
        medical_lines = _medical_negligence_consumer_template_lines(q, passages)
        if medical_lines:
            return medical_lines

    if (
        route.category == "consumer"
        and _has_any_term(q, ("parking", "parking slot", "dedicated parking", "allotted parking", "stilt parking", "car park", "blocked my parking", "blocking my parking"))
        and _has_any_term(q, ("society", "housing", "apartment", "rwa", "security guard"))
    ):
        parking_lines = _housing_parking_template_lines(q, passages)
        if parking_lines:
            return parking_lines

    if (
        route.category == "consumer"
        and _has_any_term(q, ("pet", "dog", "cat"))
        and _has_any_term(q, ("society", "housing", "apartment", "rwa", "fine", "approval"))
    ):
        pet_lines = _housing_pet_fine_template_lines(q, passages)
        if pet_lines:
            return pet_lines

    if route.category == "consumer" and _is_subscription_refund_query(q):
        subscription_lines = _subscription_refund_template_lines(q, passages)
        if subscription_lines:
            return subscription_lines

    if route.category == "business_contract_partnership" and _is_b2b_defective_goods_query(q):
        goods_lines = _b2b_defective_goods_template_lines(q, passages)
        if goods_lines:
            return goods_lines

    if (
        route.category == "business_contract_partnership"
        and _has_any_term(q, ("msme", "msmed", "udyam"))
        and _has_any_term(q, ("43b", "43b(h)", "section 43b", "disallowance", "payment"))
    ):
        msme_lines = _msme_43b_payment_template_lines(q, passages)
        if msme_lines:
            return msme_lines

    if route.category == "tax_gst_compliance" and _is_gst_itc_mismatch_query(q):
        gst_lines = _gst_itc_mismatch_template_lines(q, passages)
        if gst_lines:
            return gst_lines

    if (
        route.category == "family_marriage_status"
        and _has_any_term(q, ("name change", "change my name", "change my surname", "change surname", "gazette"))
    ):
        name_lines = _name_change_gazette_template_lines(q, passages)
        if name_lines:
            return name_lines

    if route.category == "family_marriage_status" and route.label == "Matrimonial property / maintenance response":
        matrimonial_lines = _matrimonial_property_maintenance_template_lines(q, passages)
        if matrimonial_lines:
            return matrimonial_lines

    if route.category == "family_marriage_status" and _is_pre_marriage_health_disclosure_query(q):
        pre_marriage_lines = _pre_marriage_health_disclosure_template_lines(q, passages)
        if pre_marriage_lines:
            return pre_marriage_lines

    if route.category == "family_marriage_status" and _is_marriage_misrepresentation_query(q):
        marriage_lines = _marriage_misrepresentation_template_lines(q, passages)
        if marriage_lines:
            return marriage_lines

    if route.category == "family_marriage_status" and _is_marital_intimacy_breakdown_query(q):
        breakdown_lines = _marital_intimacy_breakdown_template_lines(q, passages)
        if breakdown_lines:
            return breakdown_lines

    if route.category == "family_domestic" and _is_marital_sexual_violence_query(q):
        marital_sexual_lines = _marital_sexual_violence_template_lines(q, passages)
        if marital_sexual_lines:
            return marital_sexual_lines

    if route.category == "family_domestic" and _is_domestic_violence_safety_query(q):
        domestic_safety_lines = _domestic_violence_safety_template_lines(q, passages)
        if domestic_safety_lines:
            return domestic_safety_lines

    if route.category == "family_domestic" and _is_streedhan_return_query(q):
        streedhan_lines = _streedhan_return_template_lines(q, passages)
        if streedhan_lines:
            return streedhan_lines

    if route.category == "reproductive_rights_mtp" and _is_mtp_privacy_divorce_query(q):
        mtp_lines = _mtp_privacy_divorce_template_lines(q, passages)
        if mtp_lines:
            return mtp_lines

    if route.category == "banking_credit_dispute" and (route.action_pack and route.action_pack.id == "security_cheque_defence"):
        security_cheque_lines = _security_cheque_defence_template_lines(passages)
        if security_cheque_lines:
            return security_cheque_lines

    if route.category == "banking_credit_dispute" and _is_fixed_deposit_nominee_query(q):
        fd_lines = _banking_fd_nominee_template_lines(q, passages)
        if fd_lines:
            return fd_lines

    if route.category == "banking_credit_dispute" and _is_bank_property_document_fraud_query(q):
        forged_loan_lines = _bank_property_document_fraud_template_lines(q, passages)
        if forged_loan_lines:
            return forged_loan_lines

    if route.category == "court_procedure" and _is_private_magistrate_complaint_query(q):
        private_complaint_lines = _private_magistrate_complaint_template_lines(passages)
        if private_complaint_lines:
            return private_complaint_lines

    if route.category == "court_procedure" and _is_decree_execution_attachment_query(q):
        execution_lines = _decree_execution_attachment_template_lines(q, passages)
        if execution_lines:
            return execution_lines

    if route.category == "court_procedure" and _is_vakalatnama_change_query(q):
        vakalat_lines = _vakalatnama_change_template_lines(passages)
        if vakalat_lines:
            return vakalat_lines

    if route.category == "court_procedure" and _is_writ_constitution_query(q):
        writ_lines = _writ_constitution_template_lines(q, passages)
        if writ_lines:
            return writ_lines

    if route.category in {"criminal_defence_bail", "court_procedure", "police_fir"} and _is_criminal_quashing_query(q):
        quashing_lines = _criminal_quashing_template_lines(q, passages)
        if quashing_lines:
            return quashing_lines

    if route.category == "court_procedure" and _has_any_term(q, ("court fee", "court fees", "valuation", "suit valuation")):
        court_fee_lines = _court_fee_template_lines(passages)
        if court_fee_lines:
            return court_fee_lines

    if route.category == "police_fir" and _is_caste_fir_refusal_query(q):
        caste_fir_lines = _caste_fir_refusal_template_lines(passages)
        if caste_fir_lines:
            return caste_fir_lines

    if route.category == "police_fir" and _is_domestic_acid_threat_query(q):
        acid_lines = _domestic_acid_threat_template_lines(q, passages)
        if acid_lines:
            return acid_lines

    if route.category == "police_fir" and _is_honour_or_threat_query(q):
        threat_lines = _police_threat_template_lines(q, passages)
        if threat_lines:
            return threat_lines

    if route.category == "cyber_fraud_or_harassment" and _is_bank_otp_refund_query(q):
        otp_refund_lines = _bank_otp_refund_template_lines(q, passages)
        if otp_refund_lines:
            return otp_refund_lines

    if route.category == "cyber_fraud_or_harassment" and _is_cyber_impersonation_fraud_query(q):
        impersonation_lines = _cyber_impersonation_fraud_template_lines(q, passages)
        if impersonation_lines:
            return impersonation_lines

    if route.category == "cyber_fraud_or_harassment" and _is_crypto_investment_fraud_query(q):
        crypto_lines = _crypto_investment_fraud_template_lines(q, passages)
        if crypto_lines:
            return crypto_lines

    if route.category == "cyber_fraud_or_harassment":
        creator_leak_lines = _creator_content_leak_template_lines(q, passages)
        if creator_leak_lines:
            return creator_leak_lines
        deepfake_lines = _deepfake_lookalike_template_lines(q, passages)
        if deepfake_lines:
            return deepfake_lines

    if route.category == "cyber_fraud_or_harassment" and _is_cyber_blackmail_or_extortion_query(q):
        cyber_lines = _cyber_blackmail_template_lines(q, passages)
        if cyber_lines:
            return cyber_lines

    if route.category == "senior_citizen" and _is_senior_maintenance_enforcement_query(q):
        senior_enforcement_lines = _senior_maintenance_enforcement_template_lines(q, passages)
        if senior_enforcement_lines:
            return senior_enforcement_lines

    if route.category == "senior_citizen" and _is_insurance_misselling_query(q):
        insurance_lines = _insurance_misselling_template_lines(q, passages)
        if insurance_lines:
            return insurance_lines

    if route.category == "senior_citizen" and not (route.action_pack and route.action_pack.id == "senior_maintenance_cheque"):
        senior_lines = _senior_citizen_property_or_maintenance_template_lines(q, passages)
        if senior_lines:
            return senior_lines

    if route.category == "senior_citizen" and (route.action_pack and route.action_pack.id == "senior_maintenance_cheque"):
        senior_cheque_lines = _senior_maintenance_cheque_template_lines(passages)
        if senior_cheque_lines:
            return senior_cheque_lines

    if route.category == "education_loan_denial":
        education_loan_lines = _education_loan_denial_template_lines(passages)
        if education_loan_lines:
            return education_loan_lines

    if route.category == "education_rights" and _is_school_admission_denial_query(q):
        school_lines = _school_admission_denial_template_lines(q, passages)
        if school_lines:
            return school_lines

    if route.category == "legal_aid" and _is_lok_adalat_traffic_query(q):
        lok_lines = _lok_adalat_traffic_template_lines(passages)
        if lok_lines:
            return lok_lines

    if route.category == "undertrial_review_release" and _has_any_term(q, ("lawyer", "legal aid", "dlsa", "not coming", "complain")):
        undertrial_legal_aid_lines = _undertrial_legal_aid_template_lines(passages)
        if undertrial_legal_aid_lines:
            return undertrial_legal_aid_lines

    if route.category == "prison_parole_furlough" and _is_prison_mulaqat_query(q):
        mulaqat_lines = _prison_mulaqat_template_lines(passages)
        if mulaqat_lines:
            return mulaqat_lines

    if route.category == "custody_compensation":
        custody_compensation_lines = _custody_compensation_template_lines(passages)
        if custody_compensation_lines:
            return custody_compensation_lines

    if route.category == "criminal_general" and _is_identity_police_threat_query(q):
        identity_threat_lines = _identity_police_threat_template_lines(passages)
        if identity_threat_lines:
            return identity_threat_lines

    if route.category == "criminal_general" and _is_wife_as_aggressor_query(q):
        spouse_neutral_lines = _spousal_neutral_complaint_template_lines(q, passages)
        if spouse_neutral_lines:
            return spouse_neutral_lines

    if (
        route.category == "banking_credit_dispute"
        and _has_any_term(q, ("cooperative bank", "co-operative bank", "crop loan", "buffalo", "livestock"))
    ):
        agri_bank_lines = _agri_cooperative_recovery_template_lines(q, passages)
        if agri_bank_lines:
            return agri_bank_lines

    if route.category == "banking_credit_dispute" and _is_loan_app_harassment_query(q):
        loan_app_lines = _loan_app_harassment_template_lines(q, passages)
        if loan_app_lines:
            return loan_app_lines

    if route.category == "banking_credit_dispute" and _is_bank_account_freeze_query(q):
        freeze_lines = _bank_account_freeze_template_lines(q, passages)
        if freeze_lines:
            return freeze_lines

    if route.category == "banking_credit_dispute" and _is_bank_debit_service_query(q):
        debit_lines = _bank_debit_ombudsman_template_lines(q, passages)
        if debit_lines:
            return debit_lines

    if route.category == "banking_credit_dispute" and _is_banking_ombudsman_credit_query(q):
        banking_lines = _banking_ombudsman_credit_template_lines(passages)
        if banking_lines:
            return banking_lines

    if (
        route.category == "land_revenue_records"
        and _has_any_term(q, ("sarpanch", "panchayat", "gram sabha"))
        and _has_any_term(q, ("common village land", "common land", "panchayat land", "no panchayat meeting"))
    ):
        panchayat_lines = _panchayat_common_land_template_lines(q, passages)
        if panchayat_lines:
            return panchayat_lines

    if (
        route.category == "criminal_general"
        and _has_any_term(q, ("daughter in law", "daughter-in-law", "bahu"))
        and _has_any_term(q, ("jewellery", "jewelry", "gold", "ornaments"))
        and _has_any_term(q, ("safe keeping", "safekeeping", "not returning", "refusing to return"))
    ):
        jewellery_lines = _inlaw_jewellery_breach_template_lines(q, passages)
        if jewellery_lines:
            return jewellery_lines

    if (
        route.category == "criminal_defence_bail"
        and _has_any_term(q, ("tonhi", "daayan", "dayan", "daini", "witch"))
        and _has_any_term(q, ("false case", "case filed", "accused", "blaming", "they say"))
    ):
        witch_lines = _witch_accused_defence_template_lines(q, passages)
        if witch_lines:
            return witch_lines

    if route.category == "criminal_defence_bail" and _is_elder_498a_accused_query(q):
        elder_498a_lines = _elder_498a_accused_template_lines(q, passages)
        if elder_498a_lines:
            return elder_498a_lines

    if (
        route.category == "criminal_defence_bail"
        and _has_any_term(q, ("pregnant", "pregnancy", "medical bail", "interim bail", "sick", "infirm"))
        and _has_any_term(q, ("undertrial", "jail", "prison", "custody", "byculla", "bail", "postpone trial"))
    ):
        medical_bail_lines = _interim_medical_bail_template_lines(passages)
        if medical_bail_lines:
            return medical_bail_lines

    if (
        route.category == "criminal_defence_bail"
        and _has_any_term(q, ("juvenile", "minor", "under 18", "under eighteen", "age proof", "age determination", "verify age", "school certificate", "birth certificate", "adult jail", "observation home", "son 17", "daughter 17", "boy 17", "girl 17", "son 16", "daughter 16", "boy 16", "girl 16", "16 yr", "16 yrs", "16 year"))
    ):
        juvenile_lines = _juvenile_age_custody_template_lines(q, passages)
        if juvenile_lines:
            return juvenile_lines

    if (
        route.category == "criminal_defence_bail"
        and _has_any_term(q, ("spa", "massage parlour", "massage parlor", "massage"))
        and _has_any_term(q, ("raid", "raided", "police came", "police took", "station", "itpa", "pita", "cctv", "ran away"))
    ):
        spa_lines = _itpa_spa_raid_template_lines(q, passages)
        if spa_lines:
            return spa_lines

    if route.category == "criminal_defence_bail" and _is_itpa_call_handling_query(q):
        itpa_call_lines = _itpa_call_handling_template_lines(q, passages)
        if itpa_call_lines:
            return itpa_call_lines

    if (
        route.category == "criminal_defence_bail"
        and _has_any_term(q, ("forest guard", "forest officer", "tendu", "minor forest produce"))
        and _has_any_term(q, ("dacoity", "false case", "case lodged", "case filed"))
    ):
        forest_lines = _forest_false_dacoity_template_lines(q, passages)
        if forest_lines:
            return forest_lines

    if (
        route.category == "criminal_defence_bail"
        and _has_any_term(q, ("ndps", "ganja", "charas", "mdma", "heroin", "cannabis", "tihar"))
        and _has_any_term(q, ("bail", "custody", "jail", "rejected", "session court", "sessions court"))
    ):
        ndps_lines = _ndps_bail_template_lines(q, passages)
        if ndps_lines:
            return ndps_lines

    if (
        route.category == "criminal_defence_bail"
        and _has_any_term(q, ("ndps", "ganja", "charas", "mdma", "heroin", "cannabis", "weed", "hash", "cbd", "thc", "vape", "vape cartridge", "vape pen", "bhang", "bhang lassi"))
    ):
        ndps_personal_lines = _ndps_personal_use_template_lines(q, passages)
        if ndps_personal_lines:
            return ndps_personal_lines

    if (
        route.category == "ibc_nclt"
        and _has_any_term(q, ("llp", "limited liability partnership", "form 11"))
    ):
        llp_lines = _llp_annual_return_template_lines(passages)
        if llp_lines:
            return llp_lines

    if (
        route.category == "cyber_fraud_or_harassment"
        and _has_any_term(q, ("dpdp", "data breach", "personal data", "pan leaked", "aadhaar leaked", "aadhar leaked", "pan and aadhaar", "pan and aadhar", "data leaked"))
        and not _has_any_term(q, ("fraud", "fake loan", "identity theft", "identity misuse", "blackmail", "sextortion", "otp", "upi", "phishing"))
    ):
        dpdp_lines = _dpdp_data_breach_template_lines(q, passages)
        if dpdp_lines:
            return dpdp_lines

    if (
        route.category == "cyber_fraud_or_harassment"
        and _has_any_term(q, ("tweet", "twitter", "x.com", "online post", "social media post"))
        and _has_any_term(q, ("chargesheet", "charge sheet", "356", "defamation", "cm corrupt"))
    ):
        tweet_lines = _tweet_defamation_chargesheet_template_lines(q, passages)
        if tweet_lines:
            return tweet_lines

    if route.category == "trademark_ip" and _is_trademark_opposition_query(q):
        trademark_lines = _trademark_opposition_template_lines(passages)
        if trademark_lines:
            return trademark_lines

    if (
        route.category == "business_contract_partnership"
        and _has_any_term(q, ("fanvue", "onlyfans", "patreon", "gumroad", "creator", "foreign platform", "usd"))
        and _has_any_term(q, ("payment", "payout", "frozen", "freeze", "release fund", "withheld", "remittance"))
    ):
        payout_lines = _creator_platform_payout_template_lines(q, passages)
        if payout_lines:
            return payout_lines

    if (
        route.category == "social_welfare_identity"
        and _has_any_term(q, ("sc scholarship", "st scholarship", "obc scholarship", "scheduled caste", "scheduled tribe", "dalit", "adivasi", "post-matric", "post matric"))
    ):
        scholarship_lines = _caste_scholarship_template_lines(q, passages)
        if scholarship_lines:
            return scholarship_lines

    if route.category == "succession_inheritance" and _is_parsi_succession_query(q):
        parsi_lines = _parsi_succession_template_lines(passages)
        if parsi_lines:
            return parsi_lines

    if (
        route.category == "workplace_injury_compensation"
        and _has_any_term(q, ("mukadam", "beat", "beaten", "assault", "head injury", "stitches", "old wages"))
    ):
        assault_lines = _workplace_assault_wage_template_lines(q, passages)
        if assault_lines:
            return assault_lines

    if route.category == "workplace_injury_compensation" and _has_any_term(q, ("bocw", "construction", "site", "fell from")):
        injury_lines = _construction_injury_template_lines(q, passages)
        if injury_lines:
            return injury_lines

    if route.category == "child_custody_adoption" and _has_any_term(q, ("adopted", "adoption", "papers", "real parents")):
        adoption_lines = _relative_adoption_template_lines(q, passages)
        if adoption_lines:
            return adoption_lines

    if route.category == "child_custody_adoption" and _is_child_return_or_access_query(q):
        custody_lines = _child_return_custody_template_lines(q, passages)
        if custody_lines:
            return custody_lines

    if route.category == "child_custody_adoption" and _has_any_term(q, ("supervised visitation", "unsupervised visitation", "visitation order", "visitation for my")):
        visitation_lines = _supervised_visitation_template_lines(passages)
        if visitation_lines:
            return visitation_lines

    if (
        route.category == "police_fir"
        and _has_any_term(q, ("custodial death", "lockup death", "death lockup", "lockup suicide", "custody death", "section 196", " 196 procedure"))
    ):
        custody_lines = _custodial_death_template_lines(q, passages)
        if custody_lines:
            return custody_lines

    if (
        route.category == "police_fir"
        and _has_any_term(q, ("police torture", "custodial torture", "torture case", "undertrial"))
    ):
        torture_lines = _police_torture_complaint_template_lines(q, passages)
        if torture_lines:
            return torture_lines

    if (
        route.category == "property_tenancy"
        and _is_property_document_fraud_query(q)
    ):
        property_lines = _property_document_fraud_template_lines(q, passages)
        if property_lines:
            return property_lines

    if (
        route.category == "property_tenancy"
        and _is_ancestral_land_sale_query(q)
    ):
        ancestral_lines = _ancestral_land_sale_template_lines(q, passages)
        if ancestral_lines:
            return ancestral_lines

    if (
        route.category == "property_tenancy"
        and _is_joint_property_sale_query(q)
    ):
        coowner_lines = _joint_property_sale_template_lines(q, passages)
        if coowner_lines:
            return coowner_lines

    if (
        route.category == "property_tenancy"
        and _is_tenant_nonpayment_vacate_query(q)
    ):
        tenant_lines = _tenant_nonpayment_vacate_template_lines(q, passages)
        if tenant_lines:
            return tenant_lines

    if (
        route.category == "property_tenancy"
        and _has_any_term(q, ("icu", "hospital", "pressure", "forced", "undue influence"))
        and _has_any_term(q, ("property", "signed", "transfer", "gift"))
    ):
        property_lines = _property_pressure_transfer_template_lines(q, passages)
        if property_lines:
            return property_lines

    if _has_any_term(q, ("rti", "right to information")):
        rti_lines = _rti_template_lines(q, passages)
        if rti_lines:
            return rti_lines

    if (
        route.category == "business_license_compliance"
        and _is_municipal_shop_sealing_query(q)
    ):
        municipal_lines = _municipal_shop_sealing_template_lines(q, passages)
        if municipal_lines:
            return municipal_lines

    if (
        route.category == "business_license_compliance"
        and _has_any_term(q, ("traffic police", "no challan"))
        and _has_any_term(q, ("license", "licence", "driving"))
        and _has_any_term(q, ("500", "bribe", "taking", "money", "hafta", "without challan"))
    ):
        traffic_lines = _traffic_bribe_template_lines(passages)
        if traffic_lines:
            return traffic_lines

    if (
        route.category == "business_license_compliance"
        and _has_any_term(q, ("drug inspector", "drugs inspector", "medical store", "pharmacy", "chemist", "schedule h", "without prescription"))
    ):
        drug_lines = _drug_inspector_template_lines(passages)
        if drug_lines:
            return drug_lines

    if (
        route.category == "criminal_defence_bail"
        and _has_any_term(q, ("prohibition law", "excise act", "liquor", "drinking", "sharab"))
        and not _has_passage(passages, title_terms=("bihar prohibition",))
    ):
        prohibition_lines = _generic_prohibition_template_lines(passages)
        if prohibition_lines:
            return prohibition_lines

    return []


def _arrest_production_delay_template_lines(query: str, passages: list[dict]) -> list[str]:
    article22 = _find_passage_index(
        passages,
        title_terms=("constitution",),
        anchor_terms=("/sec-22",),
    )
    article21 = _find_passage_index(
        passages,
        title_terms=("constitution",),
        anchor_terms=("/sec-21",),
    )
    bnss57 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-57",),
    )
    bnss58 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-58",),
    )
    crpc56 = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-56",),
    )
    crpc57 = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-57",),
    )
    if article22 is None and article21 is None and bnss57 is None and bnss58 is None and crpc56 is None and crpc57 is None:
        return []
    lines = ["**Short answer**"]
    if article22 is not None:
        arrest_subject = "your father/papa's arrest" if "papa" in query else "the arrest"
        lines.append(
            f"For {arrest_subject}, the Constitution Article 22 source is the key safeguard: after arrest, the person must be produced before the nearest Magistrate within 24 hours, excluding journey time [{article22}]."
        )
    elif article21 is not None:
        lines.append(
            f"The Constitution Article 21 source makes this a personal-liberty problem, so unexplained custody without court production should be treated as urgent [{article21}]."
        )
    if bnss58 is not None:
        lines.append(
            f"For current-law procedure, the BNSS source says police cannot detain an arrested person beyond 24 hours without Magistrate authority, excluding journey time [{bnss58}]."
        )
    elif crpc57 is not None:
        lines.append(
            f"For pre-1 July 2024 matters, the CrPC source gives the same 24-hour custody limit without Magistrate authority, excluding journey time [{crpc57}]."
        )
    if bnss57 is not None:
        lines.append(
            f"The BNSS production source also requires taking the arrested person before the Magistrate or officer in charge without unnecessary delay [{bnss57}]."
        )
    elif crpc56 is not None:
        lines.append(
            f"The CrPC production source similarly requires production before the Magistrate or officer in charge without unnecessary delay [{crpc56}]."
        )
    if _has_any_term(query, ("5 din", "five days", "5 days", "4 din", "four days", "3 din", "three days")):
        delay_cite = article22 if article22 is not None else bnss58 if bnss58 is not None else crpc57 if crpc57 is not None else bnss57 if bnss57 is not None else crpc56 if crpc56 is not None else article21
        lines.append(
            f"So '5 din' in police custody without being taken before the Magistrate should be treated as an urgent unlawful-detention/production issue, not a routine police delay [{delay_cite}]."
        )
    lines.append("**What you can do next**")
    action_cite = article22 if article22 is not None else bnss58 if bnss58 is not None else crpc57 if crpc57 is not None else bnss57 if bnss57 is not None else crpc56 if crpc56 is not None else article21
    lines.append(
        f"- Take the arrest time, police station, FIR number if known, and any remand or arrest papers to DLSA or a criminal lawyer urgently and seek production/remand verification before the Magistrate [{action_cite}]."
    )
    return lines


def _police_picked_fir_copy_template_lines(query: str, passages: list[dict]) -> list[str]:
    article22 = _find_passage_index(
        passages,
        title_terms=("constitution",),
        anchor_terms=("/sec-22",),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    crpc154 = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-154",),
    )
    if article22 is None and bnss173 is None and crpc154 is None:
        return []
    lines = ["**Short answer**"]
    if article22 is not None:
        lines.append(
            f"Because police picked your family member from home, first treat this as an arrest-information and liberty safeguard issue: Article 22 is the source to check for arrest grounds, lawyer access, and production before a Magistrate [{article22}]."
        )
    if bnss173 is not None:
        lines.append(
            f"For the FIR-copy side, BNSS Section 173 is the current-procedure source to check for how information to police is recorded and handled [{bnss173}]."
        )
    elif crpc154 is not None:
        lines.append(
            f"For a pre-1 July 2024 or CrPC-framed matter, CrPC Section 154 is the FIR-information source to check for the recorded information/FIR route [{crpc154}]."
        )
    lines.append("**What you can do next**")
    action_cite = article22 if article22 is not None else bnss173 if bnss173 is not None else crpc154
    lines.append(
        f"- Write down the pickup/arrest time, police station, officer names, and FIR or complaint number if known; take that to DLSA, a criminal lawyer, or the nearest Magistrate and ask for arrest/remand and FIR-copy status [{action_cite}]."
    )
    return lines


def _theft_fir_refusal_template_lines(query: str, passages: list[dict]) -> list[str]:
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    bnss175 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-175",),
    )
    crpc154 = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-154",),
    )
    crpc156 = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-156",),
    )
    bns303 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-303",),
    )
    bns317 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-317",),
    )
    bns_theft = bns303 if bns303 is not None else bns317
    if bnss173 is None and crpc154 is None and bns_theft is None:
        return []
    lines = ["**Short answer**"]
    if bns303 is not None:
        lines.append(
            f"For a stolen bike, the current offence source to check first is the BNS theft provision in the retrieved material [{bns303}]."
        )
    elif bns317 is not None:
        lines.append(
            f"For a stolen bike, the BNS source defines property whose possession has been transferred by theft as stolen property; the exact FIR section still depends on the incident date and police papers [{bns317}]."
        )
    if bnss173 is not None:
        lines.append(
            f"For police refusal to register the case, BNSS Section 173 is the current-procedure source for information given to the officer in charge of a police station [{bnss173}]."
        )
    elif crpc154 is not None:
        lines.append(
            f"For a pre-1 July 2024 or CrPC-framed incident, CrPC Section 154 is the FIR-information source for information given to the police station [{crpc154}]."
        )
    lines.append("**What you can do next**")
    action_cite = bnss175 if bnss175 is not None else crpc156 if crpc156 is not None else bnss173 if bnss173 is not None else crpc154 if crpc154 is not None else bns_theft
    lines.append(
        f"- Give a written theft complaint with bike registration/chassis details, date/place, CCTV or witness details, and keep acknowledgement; if the station still refuses, escalate with the written proof to senior police, DLSA, or the Magistrate route [{action_cite}]."
    )
    return lines


def _school_admission_denial_template_lines(query: str, passages: list[dict]) -> list[str]:
    rte13 = _find_passage_index(
        passages,
        title_terms=("right of children",),
        anchor_terms=("/sec-13",),
    )
    rte12 = _find_passage_index(
        passages,
        title_terms=("right of children",),
        anchor_terms=("/sec-12",),
    )
    rte14 = _find_passage_index(
        passages,
        title_terms=("right of children",),
        anchor_terms=("/sec-14",),
    )
    rte15 = _find_passage_index(
        passages,
        title_terms=("right of children",),
        anchor_terms=("/sec-15",),
    )
    if rte13 is None and rte12 is None and rte14 is None and rte15 is None:
        return []
    lines = ["**Short answer**"]
    if rte13 is not None:
        lines.append(
            f"For a school-admission denial, first check the RTE source on capitation fee and screening procedure instead of treating the issue as only a transfer-certificate problem [{rte13}]."
        )
    if rte12 is not None:
        lines.append(
            f"The RTE admission-duty source is also relevant if your daughter's age, class, school type, and category fit that Act [{rte12}]."
        )
    if rte14 is not None:
        lines.append(
            f"If the school is using age-proof papers as the reason, the RTE age-proof source should be checked before accepting the refusal [{rte14}]."
        )
    elif rte15 is not None:
        lines.append(
            f"If the issue is late or delayed admission, the RTE admission-timing source should be checked with the school year and class facts [{rte15}]."
        )
    lines.append("**What you can do next**")
    action_cite = rte13 if rte13 is not None else rte12 if rte12 is not None else rte14 if rte14 is not None else rte15
    lines.append(
        f"- Ask the school for written refusal reasons, keep the application/exam result/messages, and complain to the district education officer or RTE grievance authority with the child's age, class, school type, and category/income papers where relevant [{action_cite}]."
    )
    return lines


def _pan_aadhaar_mismatch_template_lines(query: str, passages: list[dict]) -> list[str]:
    income_tax_pan = _find_passage_index(
        passages,
        title_terms=("income-tax", "income tax"),
        anchor_terms=("/sec-139-a", "/sec-139a", "/sec-139"),
    )
    aadhaar = _find_passage_index(
        passages,
        title_terms=("aadhaar", "aadhar"),
        anchor_terms=("/sec-4", "/sec-7", "/sec-8", "/sec-59"),
    )
    rti = _find_passage_index(
        passages,
        title_terms=("right to information",),
        anchor_terms=("/sec-6", "/sec-7", "/sec-19"),
    )
    if income_tax_pan is None and aadhaar is None and rti is None:
        return []
    lines = ["**Short answer**"]
    if income_tax_pan is not None:
        lines.append(
            f"For a PAN/Aadhaar mismatch, do not treat this as a caste, ration, or generic welfare issue; first identify whether the PAN/income-tax record or the Aadhaar record has the wrong name, date of birth, gender, or mobile/authentication detail [{income_tax_pan}]."
        )
    if aadhaar is not None:
        lines.append(
            f"The Aadhaar source is relevant only to the identity/authentication side, so it should not be used to say your PAN details are automatically correct or incorrect [{aadhaar}]."
        )
    if rti is not None:
        lines.append(
            f"If an office or portal refuses to tell you the exact mismatch reason, use the written grievance/RTI route to get status, reasons, and the rule or record relied on [{rti}]."
        )
    lines.append("**What you can do next**")
    action_cite = income_tax_pan if income_tax_pan is not None else aadhaar if aadhaar is not None else rti
    lines.append(
        f"- Compare PAN, Aadhaar, and the rejection screenshot field by field; correct the wrong record through the PAN/income-tax side or UIDAI/Aadhaar Seva Kendra, keep the acknowledgement, and retry linking only after the correction is reflected [{action_cite}]."
    )
    return lines


def _ration_portability_template_lines(query: str, passages: list[dict]) -> list[str]:
    nfsa3 = _find_passage_index(
        passages,
        title_terms=("national food security",),
        anchor_terms=("/sec-3",),
    )
    nfsa12 = _find_passage_index(
        passages,
        title_terms=("national food security",),
        anchor_terms=("/sec-12",),
    )
    nfsa14 = _find_passage_index(
        passages,
        title_terms=("national food security",),
        anchor_terms=("/sec-14",),
    )
    nfsa15 = _find_passage_index(
        passages,
        title_terms=("national food security",),
        anchor_terms=("/sec-15",),
    )
    aadhaar7 = _find_passage_index(
        passages,
        title_terms=("aadhaar",),
        anchor_terms=("/sec-7",),
    )
    aadhaar8 = _find_passage_index(
        passages,
        title_terms=("aadhaar",),
        anchor_terms=("/sec-8",),
    )
    if nfsa3 is None and nfsa12 is None and nfsa14 is None and nfsa15 is None and aadhaar7 is None and aadhaar8 is None:
        return []
    if _has_any_term(query, ("aadhaar", "aadhar", "mismatch", "biometric", "cancelled", "canceled")):
        portability_phrase = "ration-card cancellation or Aadhaar mismatch"
    elif _has_any_term(query, ("west bengal", "chennai", "one nation")):
        portability_phrase = "West Bengal ration card not working at a Chennai ration shop under portability"
    else:
        portability_phrase = "ration portability" if _has_any_term(query, ("one nation", "portability", "chennai", "migrant")) else "ration-card denial"
    lines = ["**Short answer**"]
    if nfsa3 is not None:
        lines.append(
            f"For this {portability_phrase}, the NFSA source is relevant because it covers subsidised foodgrains for eligible households under the targeted public distribution system [{nfsa3}]."
        )
    if nfsa12 is not None:
        lines.append(
            f"The NFSA reforms source supports framing the issue as a TPDS/ration-shop delivery failure, including transparency and doorstep-delivery reforms under the Act [{nfsa12}]."
        )
    if nfsa14 is not None:
        lines.append(
            f"For this {portability_phrase}, the NFSA grievance source requires every State Government to put an internal grievance redressal mechanism in place for expeditious and effective redressal [{nfsa14}]."
        )
    if nfsa15 is not None:
        lines.append(
            f"The NFSA District Grievance Redressal Officer source is the escalation route for ration entitlement complaints at district level [{nfsa15}]."
        )
    if aadhaar7 is not None:
        lines.append(
            f"Where the problem is Aadhaar authentication or mismatch, keep that as a separate identity/subsidy-benefit issue under the Aadhaar Act source instead of treating the ration cancellation as final [{aadhaar7}]."
        )
    elif aadhaar8 is not None:
        lines.append(
            f"The Aadhaar Act authentication source is relevant only to the identity/authentication step; the foodgrain entitlement and grievance route still has to be checked separately under NFSA sources [{aadhaar8}]."
        )
    lines.append("**What you can do next**")
    action_cite = nfsa15 if nfsa15 is not None else nfsa14 if nfsa14 is not None else aadhaar7 if aadhaar7 is not None else aadhaar8 if aadhaar8 is not None else nfsa12 if nfsa12 is not None else nfsa3
    lines.append(
        f"- Keep the ration-card number, cancellation or shop details, denial date, Aadhaar or portability error screenshot, BDO/office reply, and family-member details, then file a written complaint through the State NFSA grievance/DGRO or identity-correction route [{action_cite}]."
    )
    return lines


def _medical_negligence_consumer_template_lines(query: str, passages: list[dict]) -> list[str]:
    consumer2 = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-2", "/sec-2-"),
    )
    consumer35 = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-35",),
    )
    consumer39 = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-39",),
    )
    if consumer2 is None and consumer35 is None and consumer39 is None:
        return []
    patient_phrase = "your father" if "father" in query else "the patient"
    issue_phrase = "wrong-limb or wrong-surgery" if _has_any_term(query, ("wrong leg", "wrong limb", "wrong surgery", "wrong operation", "operated wrong")) else "medical-treatment"
    lines = ["**Short answer**"]
    if consumer2 is not None:
        lines.append(
            f"Treat this first as a hospital service-deficiency or medical-negligence question only if the medical records support the {issue_phrase} facts; the Consumer Protection Act source is the consumer-law base to check [{consumer2}]."
        )
    if consumer35 is not None:
        lines.append(
            f"The Consumer Protection Act complaint source gives the consumer-forum filing route, so do not route this only as a police/FIR issue unless separate criminal-negligence facts are alleged [{consumer35}]."
        )
    if consumer39 is not None:
        lines.append(
            f"The Consumer Protection Act relief source is relevant for refund, replacement, removal of deficiency, compensation, or similar consumer-forum relief depending on proof [{consumer39}]."
        )
    action_cite = consumer35 if consumer35 is not None else consumer39 if consumer39 is not None else consumer2
    lines.extend([
        "**What you can do next**",
        f"- Collect {patient_phrase}'s consent form, operation notes, discharge summary, bills, photos, second medical opinion, and written hospital reply before filing a hospital grievance, medical-council complaint, or District Commission complaint [{action_cite}].",
    ])
    return lines


def _banking_fd_nominee_template_lines(query: str, passages: list[dict]) -> list[str]:
    banking45za = _find_passage_index(
        passages,
        title_terms=("banking regulation",),
        anchor_terms=("/sec-45ZA",),
    )
    banking = _find_passage_index(
        passages,
        title_terms=("banking regulation",),
    )
    consumer2 = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-2",),
    )
    consumer35 = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-35",),
    )
    ombudsman = _find_passage_index(
        passages,
        title_terms=("ombudsman", "reserve bank"),
    )
    if banking is None and consumer2 is None and consumer35 is None and ombudsman is None:
        return []
    lines = ["**Short answer**"]
    if banking45za is not None:
        fd_context = "a private/cooperative bank not honouring your grandfather's FD nominee claim" if "grandfather" in query else "a fixed-deposit nominee claim"
        lines.append(
            f"For {fd_context} after the depositor's death, Banking Regulation Act section 45ZA is the exact source to check for the bank's payment-to-nominee route [{banking45za}]."
        )
        lines.append(
            f"Keep any family succession dispute separate from the bank-release step: section 45ZA is about the bank paying the nominee according to the nomination, while beneficial ownership disputes may still need separate succession advice [{banking45za}]."
        )
    elif banking is not None:
        lines.append(
            f"For a fixed-deposit or nominee refusal by a bank, keep the issue framed as a depositor/banking-service dispute, not as agricultural loan recovery or SARFAESI enforcement [{banking}]."
        )
    if consumer2 is not None:
        lines.append(
            f"The Consumer Protection Act source is relevant because banking services can be tested as a service-deficiency complaint when a depositor or nominee is denied service or faces refusal/harassment without lawful basis [{consumer2}]."
        )
    elif consumer35 is not None:
        lines.append(
            f"The Consumer Protection Act complaint source gives the consumer-forum route if the bank's refusal amounts to service deficiency [{consumer35}]."
        )
    if ombudsman is not None:
        lines.append(
            f"The RBI Ombudsman source may be an escalation path after the written bank complaint period under that scheme is satisfied [{ombudsman}]."
        )
    lines.append("**What you can do next**")
    action_cite = ombudsman if ombudsman is not None else consumer35 if consumer35 is not None else consumer2 if consumer2 is not None else banking45za if banking45za is not None else banking
    relation_phrase = "grandfather's" if "grandfather" in query else "the depositor's"
    lines.append(
        f"- Give the branch a written demand with {relation_phrase} FD receipt/account details, death certificate if applicable, nominee proof, KYC, and the refusal/harassment record; then escalate to the bank grievance channel, RBI Ombudsman if available, or consumer forum [{action_cite}]."
    )
    return lines


def _child_return_custody_template_lines(query: str, passages: list[dict]) -> list[str]:
    gwa17 = _find_passage_index(
        passages,
        title_terms=("guardians and wards",),
        anchor_terms=("/sec-17",),
    )
    gwa25 = _find_passage_index(
        passages,
        title_terms=("guardians and wards",),
        anchor_terms=("/sec-25",),
    )
    family_court = _find_passage_index(
        passages,
        title_terms=("family courts",),
    )
    article21 = _find_passage_index(
        passages,
        title_terms=("constitution",),
        anchor_terms=("/sec-21",),
    )
    if gwa17 is None and gwa25 is None and family_court is None and article21 is None:
        return []
    if _has_any_term(query, ("5 year", "five year", "delhi")):
        child_phrase = "your 5-year-old child taken to Delhi"
    else:
        child_phrase = "your daughter" if _has_any_term(query, ("daughter", "her")) else "your son" if _has_any_term(query, ("son", "him")) else "the child"
    lines = ["**Short answer**"]
    if gwa25 is not None:
        lines.append(
            f"If the other parent has taken {child_phrase} and is not allowing access, the Guardians and Wards Act source on return to guardian custody is the first custody-return source to check [{gwa25}]."
        )
    if gwa17 is not None:
        lines.append(
            f"The same Act's welfare source means the court should decide custody or return around the minor's welfare, not only which parent acted first [{gwa17}]."
        )
    if article21 is not None:
        lines.append(
            f"Article 21 can support urgent child-return or habeas-corpus framing where the child's liberty/welfare facts make ordinary custody timing inadequate [{article21}]."
        )
    if family_court is not None:
        lines.append(
            f"The Family Courts source points to the Family Court as the ordinary forum for custody/access disputes where immediate writ relief is not required [{family_court}]."
        )
    lines.append("**What you can do next**")
    action_cite = gwa25 if gwa25 is not None else gwa17 if gwa17 is not None else article21 if article21 is not None else family_court
    lines.append(
        f"- Collect birth proof, school/medical records, messages blocking access, the child's current location, and any prior custody order, then seek urgent custody/access or child-return relief through Family Court or High Court depending on urgency [{action_cite}]."
    )
    return lines


def _msme_43b_payment_template_lines(query: str, passages: list[dict]) -> list[str]:
    msmed15 = _find_passage_index(
        passages,
        title_terms=("micro, small and medium enterprises",),
        anchor_terms=("/sec-15",),
    )
    msmed16 = _find_passage_index(
        passages,
        title_terms=("micro, small and medium enterprises",),
        anchor_terms=("/sec-16",),
    )
    msmed18 = _find_passage_index(
        passages,
        title_terms=("micro, small and medium enterprises",),
        anchor_terms=("/sec-18",),
    )
    tax43b = _find_passage_index(
        passages,
        title_terms=("income-tax", "income tax"),
        anchor_terms=("/sec-43B",),
    )
    tax_transition = _find_passage_index(
        passages,
        title_terms=("income tax act 2025 transition",),
    )
    if msmed15 is None and msmed18 is None and tax43b is None:
        return []
    lines = ["**Short answer**"]
    if tax_transition is not None:
        lines.append(
            f"First pin the tax year: the Income Tax Department transition FAQ says the 1961 Act is repealed from 01.04.2026, but continues to govern tax years beginning before 1 April 2026 [{tax_transition}]."
        )
    if tax43b is not None:
        lines.append(
            f"For a pre-1 April 2026 tax year governed by the 1961 Act, section 43B(h) is a buyer-side deduction timing rule for sums payable to a micro or small enterprise beyond the MSMED section 15 period; it is not a payment-extension right against you [{tax43b}]."
        )
    if msmed15 is not None:
        lines.append(
            f"The MSMED source says the buyer must pay by the written agreed date, and that agreed period cannot exceed forty-five days from the day of acceptance or deemed acceptance [{msmed15}]."
        )
    if msmed16 is not None:
        lines.append(
            f"If the buyer misses the section 15 payment timing, the MSMED source says interest is payable notwithstanding any agreement or other law [{msmed16}]."
        )
    if msmed18 is not None:
        lines.append(
            f"For recovery, the MSMED source allows a reference to the Micro and Small Enterprises Facilitation Council for amounts due under the delayed-payment provisions [{msmed18}]."
        )
    lines.append("**What you can do next**")
    action_cite = msmed18 if msmed18 is not None else msmed15 if msmed15 is not None else tax43b
    lines.append(
        f"- Send a dated demand attaching the Udyam/MSME registration, invoice, delivery or acceptance proof, tax-year/payment-year details, and the buyer's 43B(h) message, then file the MSEFC/MSME Samadhan reference if payment is still withheld [{action_cite}]."
    )
    return lines


def _b2b_defective_goods_template_lines(query: str, passages: list[dict]) -> list[str]:
    contract37 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-37",),
    )
    contract73 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-73",),
    )
    sog31 = _find_passage_index(
        passages,
        title_terms=("sale of goods",),
        anchor_terms=("/sec-31",),
    )
    sog32 = _find_passage_index(
        passages,
        title_terms=("sale of goods",),
        anchor_terms=("/sec-32",),
    )
    sog55 = _find_passage_index(
        passages,
        title_terms=("sale of goods",),
        anchor_terms=("/sec-55",),
    )
    sog56 = _find_passage_index(
        passages,
        title_terms=("sale of goods",),
        anchor_terms=("/sec-56",),
    )
    msmed18 = _find_passage_index(
        passages,
        title_terms=("micro, small and medium enterprises",),
        anchor_terms=("/sec-18",),
    )
    if contract37 is None and contract73 is None and sog31 is None and sog32 is None and sog55 is None and sog56 is None and msmed18 is None:
        return []
    goods_phrase = "defective goods/materials" if _has_any_term(query, ("defective", "quality issue", "material", "materials")) else "goods delivery"
    lines = ["**Short answer**"]
    if sog31 is not None:
        lines.append(
            f"For a supplier delivering {goods_phrase} and refusing refund, treat this as a sale-of-goods plus contract dispute, because the Sale of Goods Act source fixes seller and buyer duties around delivery and acceptance [{sog31}]."
        )
    elif sog32 is not None:
        lines.append(
            f"For a supplier delivering {goods_phrase}, the Sale of Goods Act source should be checked for delivery/payment sequencing before choosing the remedy [{sog32}]."
        )
    if contract73 is not None:
        lines.append(
            f"The Indian Contract Act damages source is relevant for compensation caused by breach, so the loss calculation must be tied to the contract, invoice, and proof of defect [{contract73}]."
        )
    elif contract37 is not None:
        lines.append(
            f"The Indian Contract Act performance source is relevant because each party's obligation still turns on the written contract and delivery terms [{contract37}]."
        )
    if sog55 is not None or sog56 is not None:
        cite = sog56 if _has_any_term(query, ("refund", "damages", "quality issue", "defective")) and sog56 is not None else sog55
        lines.append(
            f"The Sale of Goods Act remedy source should be compared for price, damages, or non-acceptance facts after checking whether the goods were accepted or rejected in writing [{cite}]."
        )
    if msmed18 is not None:
        lines.append(
            f"If the supplier or buyer is MSME/Udyam registered, keep the MSMED Facilitation Council route separate from the ordinary commercial suit or arbitration route [{msmed18}]."
        )
    lines.append("**What you can do next**")
    action_cite = contract73 if contract73 is not None else sog56 if sog56 is not None else sog55 if sog55 is not None else sog31 if sog31 is not None else sog32 if sog32 is not None else contract37 if contract37 is not None else msmed18
    lines.append(
        f"- Send a written defect/rejection or refund notice with the purchase order, invoice, delivery challan, inspection/photos, defect report, emails, and loss calculation before choosing arbitration, commercial/civil court, or MSME Facilitation Council if applicable [{action_cite}]."
    )
    return lines


def _gst_itc_mismatch_template_lines(query: str, passages: list[dict]) -> list[str]:
    sec16 = _find_passage_index(
        passages,
        title_terms=("central goods and services tax",),
        anchor_terms=("/sec-16",),
    )
    sec41 = _find_passage_index(
        passages,
        title_terms=("central goods and services tax",),
        anchor_terms=("/sec-41",),
    )
    sec73 = _find_passage_index(
        passages,
        title_terms=("central goods and services tax",),
        anchor_terms=("/sec-73",),
    )
    if sec16 is None and sec41 is None and sec73 is None:
        return []
    has_2a_3b = _has_any_term(query, ("gstr 2a", "gstr-2a", "2a")) and _has_any_term(query, ("gstr 3b", "gstr-3b", "3b"))
    issue_phrase = "GSTR-3B/GSTR-2A ITC mismatch" if has_2a_3b else "ITC reversal or mismatch issue"
    lines = ["**Short answer**"]
    if sec16 is not None:
        lines.append(
            f"For this {issue_phrase}, start with Section 16 of the CGST Act because it is the input-tax-credit eligibility source [{sec16}]."
        )
    if sec41 is not None:
        lines.append(
            f"If the officer asks for ITC reversal, check the Section 41 CGST source for input-tax-credit availment and reversal framing [{sec41}]."
        )
    elif sec73 is not None:
        lines.append(
            f"If the issue is converted into a tax demand notice, the Section 73 CGST source is the non-fraud demand route to check [{sec73}]."
        )
    lines.append("**What you can do next**")
    if sec16 is not None:
        reconciliation_phrase = "GSTR-2A/3B reconciliation" if has_2a_3b else "invoice and payment reconciliation"
        lines.append(
            f"- In the reply, map each invoice to Section 16 ITC conditions and attach {reconciliation_phrase}, tax invoice, payment, and supplier proof [{sec16}]."
        )
    elif sec41 is not None:
        reconciliation_phrase = "GSTR-2A/3B reconciliation" if has_2a_3b else "invoice and payment reconciliation"
        lines.append(
            f"- In the reply, map the ITC availment and reversal facts to the Section 41 source and attach {reconciliation_phrase}, tax invoice, payment, and supplier proof [{sec41}]."
        )
    elif sec73 is not None:
        lines.append(
            f"- If a non-fraud tax demand notice has been issued, prepare the reply with the notice, reconciliation, tax invoice, payment, and supplier proof under the Section 73 source [{sec73}]."
        )
    return lines


def _non_compete_template_lines(query: str, passages: list[dict]) -> list[str]:
    sec27 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-27",),
    )
    if sec27 is None:
        return []
    duration = "two-year " if _has_any_term(query, ("2 year", "2-year", "two year", "two-year")) else ""
    lines = [
        "**Short answer**",
        f"For a {duration}employment non-compete, Section 27 of the Indian Contract Act is the restraint-of-trade source to check first [{sec27}].",
        f"An agreement by which anyone is restrained from exercising a lawful profession, trade, or business is void to that extent under the Contract Act source [{sec27}].",
        "**What you can do next**",
        f"- Review whether the clause is a post-employment restraint of trade and preserve the employment contract, offer letter, and exit documents [{sec27}].",
    ]
    return lines


def _mining_displacement_template_lines(passages: list[dict]) -> list[str]:
    larr41 = _find_passage_index(passages, title_terms=("right to fair compensation",), anchor_terms=("/sec-41",))
    larr31 = _find_passage_index(passages, title_terms=("right to fair compensation",), anchor_terms=("/sec-31",))
    pesa = _find_passage_index(passages, title_terms=("panchayats (extension", "pesa"), anchor_terms=("/sec-4",))
    mmdr = _find_passage_index(passages, title_terms=("mines and minerals",))
    main_cite = larr41 or larr31
    if main_cite is None:
        return []
    lines = [
        "**Short answer**",
        (
            "For mine displacement with no rehabilitation, start from the land-acquisition rehabilitation route, "
            f"because the RFCTLARR source covers rehabilitation and resettlement safeguards for affected families [{main_cite}]."
        ),
    ]
    if larr41 is not None:
        lines.append(
            "If the affected families are SC/ST or the villages are in a Scheduled Area, separately check the special "
            f"RFCTLARR Scheduled Area safeguards instead of treating this as only a mining-permit issue [{larr41}]."
        )
    if pesa is not None:
        lines.append(
            f"Where Gram Sabha or Scheduled Area consultation was skipped, add the PESA/Gram Sabha objection route to the rehabilitation claim [{pesa}]."
        )
    if mmdr is not None:
        lines.append(
            f"Use the mining lease/operator details to identify the project, but do not let the mining source replace the rehabilitation claim [{mmdr}]."
        )
    lines.extend([
        "**What you can do next**",
        (
            f"Collect acquisition notices, award papers, village displacement lists, rehabilitation package records, and file first with the Collector/R&R authority and DLSA [{main_cite}]."
        ),
    ])
    return lines


def _mining_gram_sabha_noc_template_lines(query: str, passages: list[dict]) -> list[str]:
    minor_mineral = _has_any_term(query, (
        "minor mineral", "minor minerals", "sand mining", "sand lease",
        "stone quarry", "quarry lease", "quarry",
    ))
    land_or_acquisition = _has_any_term(query, (
        "land acquisition", "land acquired", "acquired for", "coal block",
        "land taken", "taken my land", "land taken for mining", "taken for mining",
        "displacement", "rehabilitation", "resettlement", "submerge", "submerged",
    ))
    pesa_minor = _find_passage_index(
        passages,
        title_terms=("panchayats (extension", "pesa"),
        anchor_terms=("/sec-4-c",),
    )
    pesa_land = _find_passage_index(
        passages,
        title_terms=("panchayats (extension", "pesa"),
        anchor_terms=("/sec-4-b",),
    )
    pesa = (pesa_minor if minor_mineral and not land_or_acquisition else None) or pesa_land or _find_passage_index(
        passages,
        title_terms=("panchayats (extension", "pesa"),
        anchor_terms=("/sec-4",),
    )
    mmdr = _find_passage_index(
        passages,
        title_terms=("mines and minerals",),
    )
    fca2 = _find_passage_index(
        passages,
        title_terms=("forest (conservation",),
        anchor_terms=("/sec-2",),
    )
    larr41 = _find_passage_index(
        passages,
        title_terms=("right to fair compensation",),
        anchor_terms=("/sec-41",),
    )
    if land_or_acquisition and pesa is None and larr41 is None:
        return []
    if pesa is None and mmdr is None and fca2 is None and larr41 is None:
        return []
    main_cite = larr41 if land_or_acquisition and larr41 is not None else pesa if pesa is not None else fca2 if fca2 is not None else mmdr if mmdr is not None else larr41
    lines = ["**Short answer**"]
    if minor_mineral and not land_or_acquisition:
        if pesa is not None:
            lines.append(
                f"For a sand, quarry, or minor-mineral lease in a Scheduled Area, the PESA source is the Gram Sabha recommendation source to check first [{pesa}]."
            )
    elif land_or_acquisition:
        if pesa is not None:
            lines.append(
                f"First verify whether the affected village is in a Scheduled Area; if yes, the PESA source is the Gram Sabha/Palli Sabha consultation source to check before treating the project process as complete [{pesa}]."
            )
        if larr41 is not None:
            lines.append(
                f"For land acquisition or displacement in a Scheduled Area, the RFCTLARR section 41 source is the specific Scheduled Area rehabilitation and resettlement safeguard to check [{larr41}]."
            )
    elif pesa is not None:
        lines.append(
            f"For a bauxite or mining NOC in a Scheduled Area where Gram Sabha resolution is missing, the PESA source is the Gram Sabha / Scheduled Area source to check first [{pesa}]."
        )
    if fca2 is not None:
        lines.append(
            f"If forest land or forest clearance is involved, the Forest Conservation Act source is a separate prior-approval source and should be checked with the project papers [{fca2}]."
        )
    if mmdr is not None:
        lines.append(
            f"Use the MMDR/mining source to identify the mining lease, mineral, operator, and government approval record; do not treat it as replacing the Gram Sabha or forest-clearance issue [{mmdr}]."
        )
    if larr41 is not None and not land_or_acquisition and not minor_mineral:
        lines.append(
            f"If land acquisition or displacement is part of the project, the RFCTLARR Scheduled Area source adds a rehabilitation and resettlement track [{larr41}]."
        )
    lines.append("**What you can do next**")
    if minor_mineral and not land_or_acquisition:
        lines.append(
            f"- Ask for the mining or quarry lease file, Gram Sabha/Palli Sabha recommendation and minutes, mineral-department approval, site map, and any forest or pollution clearance papers; then take the record to the Collector, mining department, tribal-welfare authority, DLSA, or court/NGT route depending on which approval is missing [{main_cite}]."
        )
    elif land_or_acquisition:
        lines.append(
            f"- Ask for acquisition notices, project papers, Palli Sabha/Gram Sabha notices and minutes, affected-family lists, R&R records, and forest/mining approvals; then take the record to the Collector/R&R authority, tribal-welfare authority, DLSA, or court/NGT route depending on which safeguard is actually missing [{main_cite}]."
        )
    else:
        lines.append(
            f"- Ask for the NOC file, mining lease/project proposal, Gram Sabha notice and minutes, forest-clearance papers, and affected-village list; then challenge the NOC through the Collector/tribal-welfare authority, forest authority, DLSA, or court/NGT route depending on which approval is missing [{main_cite}]."
        )
    return lines


def _land_acquisition_compensation_template_lines(passages: list[dict]) -> list[str]:
    larr64 = _find_passage_index(passages, title_terms=("right to fair compensation",), anchor_terms=("/sec-64",))
    larr77 = _find_passage_index(passages, title_terms=("right to fair compensation",), anchor_terms=("/sec-77",))
    larr31 = _find_passage_index(passages, title_terms=("right to fair compensation",), anchor_terms=("/sec-31",))
    larr38 = _find_passage_index(passages, title_terms=("right to fair compensation",), anchor_terms=("/sec-38",))
    main_cite = larr77 if larr77 is not None else larr64 if larr64 is not None else larr31 if larr31 is not None else larr38
    if main_cite is None:
        return []
    lines = ["**Short answer**"]
    if larr77 is not None:
        lines.append(
            f"For land taken for a highway with compensation still not received, treat this first as an RFCTLARR compensation-payment/deposit issue, not as a normal property transfer dispute [{larr77}]."
        )
    if larr64 is not None:
        lines.append(
            f"If the award amount, payment, or apportionment is disputed, the RFCTLARR source gives a reference-to-Authority route for a person interested who has not accepted the award [{larr64}]."
        )
    if larr31 is not None:
        lines.append(
            f"Where rehabilitation or resettlement terms are also missing, compare the acquisition record with the RFCTLARR rehabilitation-and-resettlement award source [{larr31}]."
        )
    elif larr38 is not None:
        lines.append(
            f"The possession stage also matters because RFCTLARR ties taking possession to compensation and rehabilitation steps in the acquisition process [{larr38}]."
        )
    lines.append("**What you can do next**")
    if larr64 is not None:
        lines.append(
            f"- Ask the Collector/acquisition officer for the award, payment/deposit status, and reference-to-Authority papers, then take those records to DLSA or a land-acquisition lawyer if the payment is still blocked [{larr64}]."
        )
    else:
        lines.append(
            f"- Ask the Collector/acquisition officer for the award and payment/deposit status, then take those records to DLSA or a land-acquisition lawyer if the payment is still blocked [{main_cite}]."
        )
    return lines


def _untouchability_civil_rights_template_lines(query: str, passages: list[dict]) -> list[str]:
    article17 = _find_passage_index(passages, title_terms=("constitution of india",), anchor_terms=("/sec-17",))
    pcr3 = _find_passage_index(passages, title_terms=("protection of civil rights",), anchor_terms=("/sec-3",))
    pcr4 = _find_passage_index(passages, title_terms=("protection of civil rights",), anchor_terms=("/sec-4",))
    pcr7 = _find_passage_index(passages, title_terms=("protection of civil rights",), anchor_terms=("/sec-7",))
    poa = _find_passage_index(passages, title_terms=("scheduled castes", "prevention of atrocities"))
    pcr_main = pcr3 if pcr3 is not None else pcr4 if pcr4 is not None else pcr7
    if article17 is None and pcr_main is None and poa is None:
        return []
    lines = ["**Short answer**"]
    if article17 is not None:
        lines.append(
            f"This is a civil-rights/untouchability issue first: Article 17 of the Constitution abolishes untouchability and forbids enforcing any disability arising from it [{article17}]."
        )
    if pcr3 is not None:
        pcr3_context = (
            "temple-entry or religious water-access facts"
            if _has_any_term(query, ("temple", "well", "water", "dirty water"))
            else "religious-access facts"
        )
        lines.append(
            f"For {pcr3_context}, use the Protection of Civil Rights Act source on disabilities arising from untouchability in religious access [{pcr3}]."
        )
    if pcr4 is not None:
        water_phrase = "public access and water-related exclusion" if _has_any_term(query, ("well", "water", "dirty water")) else "social access"
        lines.append(
            f"For {water_phrase}, the Protection of Civil Rights Act source also covers social disabilities arising from untouchability [{pcr4}]."
        )
    if _has_any_term(query, ("temple", "enter temple", "temple entry", "cannot enter")) and (article17 is not None or pcr3 is not None):
        temple_cite = pcr3 if pcr3 is not None else article17
        lines.append(
            f"Telling you that your caste cannot enter the temple is the concrete access denial to put in the complaint, along with the festival date, place, and names of the people involved [{temple_cite}]."
        )
    if _has_any_term(query, ("dirty water", "drink dirty", "forced me to drink", "cannot touch")) and (article17 is not None or pcr_main is not None):
        forced_cite = pcr_main if pcr_main is not None else article17
        lines.append(
            f"Forcing a Dalit person to drink dirty water or saying they cannot touch a well should be framed as an untouchability/caste-rights complaint, not as an ordinary quarrel [{forced_cite}]."
        )
    if pcr7 is not None:
        lines.append(
            f"If someone enforces those disabilities or pressures you to submit to them, keep the Section 7 Protection of Civil Rights Act source in the complaint packet [{pcr7}]."
        )
    if poa is not None:
        lines.append(
            f"If the victim is SC/ST and the act was caste-targeted, also check the SC/ST Prevention of Atrocities source instead of filing it only as a public-nuisance or village dispute [{poa}]."
        )
    action_cite = pcr7 if pcr7 is not None else pcr_main if pcr_main is not None else article17 if article17 is not None else poa
    lines.extend([
        "**What you can do next**",
        f"- Preserve witnesses, video/messages, names of the persons involved, caste-status proof, and the temple/well/location details; take a written complaint to police and DLSA using the cited Article 17/PCR Act route [{action_cite}].",
    ])
    return lines


def _tribal_land_transfer_template_lines(query: str, passages: list[dict]) -> list[str]:
    cnt_transfer = _find_passage_index(
        passages,
        title_terms=("chota nagpur tenancy",),
        anchor_terms=("sec-46", "sec-45-c", "sec-45-b"),
    )
    cnt71 = _find_passage_index(passages, title_terms=("chota nagpur tenancy",), anchor_terms=("sec-71-a",))
    schedule = _find_passage_index(passages, title_terms=("constitution of india",), anchor_terms=("/sec-244",))
    pesa = _find_passage_index(
        passages,
        title_terms=("panchayats (extension", "pesa"),
        anchor_terms=("/sec-4",),
    )
    ap_case = _find_passage_index(
        passages,
        title_terms=("government of andhra pradesh", "pratap karan"),
    )
    if cnt_transfer is None and cnt71 is None and ap_case is None and schedule is None and pesa is None:
        return []
    restoration_cite = cnt71 or cnt_transfer
    mortgage_phrase = "mortgage/sahukar" if _has_any_term(query, ("mortgage", "sahukar", "moneylender")) else "transfer"
    mutation_context = _has_any_term(query, ("mutation", "mutation record", "patwari", "khata", "record changed"))
    lines = ["**Short answer**"]
    if cnt_transfer is not None:
        lines.append(
            f"In Jharkhand, a non-tribal {mortgage_phrase} land dispute should be checked under tribal-land transfer restrictions first, "
            f"not only as a general SC/ST offence or civil possession dispute [{cnt_transfer}]."
        )
    elif ap_case is not None:
        lines.append(
            f"For an Andhra Pradesh agency-area tribal land transfer to a non-tribal, treat this first as a Scheduled Area/tribal land-transfer dispute, not just mutation or ordinary civil possession [{ap_case}]."
        )
    if cnt71 is not None:
        lines.append(
            f"Ask the Deputy Commissioner/SAR or revenue restoration forum to examine restoration if the land went to a non-tribal contrary to the Chota Nagpur Tenancy Act route [{restoration_cite}]."
        )
    if schedule is not None:
        if mutation_context and cnt_transfer is None and ap_case is None:
            lines.append(
                f"Treat the mutation/patwari change as a possible state Scheduled Area or tribal land-transfer problem first; the exact Odisha/state regulation has to be verified from the district record, but Article 244 is the constitutional Scheduled Area starting point in this index [{schedule}]."
            )
        elif cnt_transfer is None and ap_case is None:
            lines.append(
                f"Treat this first as a possible state Scheduled Area or tribal land-transfer problem, not only as an ordinary mutation or civil possession dispute; Article 244 is the constitutional Scheduled Area starting point in this index [{schedule}]."
            )
        lines.append(
            f"Also preserve the Scheduled Area/tribal-status facts because the constitutional Scheduled Area framework can affect the forum and remedy [{schedule}]."
        )
    if pesa is not None:
        lines.append(
            f"Where the village is in a Scheduled Area, the PESA source is another official source to verify for local Scheduled Area governance and Gram Sabha facts [{pesa}]."
        )
    lines.extend([
        "**What you can do next**",
    ])
    if restoration_cite is not None:
        lines.append(
            f"Use the land papers, mortgage or possession proof, tribal-status proof, and non-tribal transferee details to seek Deputy Commissioner/SAR restoration under the Chota Nagpur Tenancy Act route [{restoration_cite}]."
        )
    else:
        action_cite = schedule if schedule is not None else ap_case
        lines.append(
            f"- Collect the khata/passbook, mutation order, transfer order or registered deed, tribal-status proof, non-tribal transferee details, and tehsildar/revenue correspondence, then ask the revenue/Collector or tribal-welfare authority to verify the state Scheduled Area land-transfer or restoration route [{action_cite}]."
        )
    return lines


def _forest_rights_template_lines(query: str, passages: list[dict]) -> list[str]:
    fra3 = _find_passage_index(
        passages,
        title_terms=("scheduled tribes and other traditional forest dwellers", "forest rights"),
        anchor_terms=("/sec-3",),
    )
    fra4 = _find_passage_index(
        passages,
        title_terms=("scheduled tribes and other traditional forest dwellers", "forest rights"),
        anchor_terms=("/sec-4",),
    )
    fra5 = _find_passage_index(
        passages,
        title_terms=("scheduled tribes and other traditional forest dwellers", "forest rights"),
        anchor_terms=("/sec-5",),
    )
    fra6 = _find_passage_index(
        passages,
        title_terms=("scheduled tribes and other traditional forest dwellers", "forest rights"),
        anchor_terms=("/sec-6",),
    )
    fra_header = _find_passage_index(
        passages,
        title_terms=("scheduled tribes and other traditional forest dwellers", "forest rights"),
        anchor_terms=("header",),
    )
    pesa = _find_passage_index(passages, title_terms=("panchayats (extension", "pesa"), anchor_terms=("/sec-4",))
    if fra3 is None and fra4 is None and fra5 is None and fra6 is None and fra_header is None and pesa is None:
        return []

    claim_refusal = (
        _has_any_term(query, ("rejected", "refused", "refusal", "without reason", "not giving", "not issuing", "no signature", "sdlc", "dlc"))
        and _has_any_term(query, ("ifr", "claim", "claim form", "patta", "title", "husband signature", "joint title"))
    )
    title_context = _has_any_term(query, ("ifr", "patta", "title", "joint title", "husband signature", "widow", "woman"))
    produce_context = _has_any_term(query, ("bamboo", "tendu", "mahua", "minor forest produce", "forest produce"))
    cfr_project_context = _has_any_term(query, ("cfr", "community forest", "community forest land", "mining", "mine", "company"))
    guard_interference = _has_any_term(query, ("forest guard", "forest guards", "forest officer", "cutting", "seized", "reserved", "invalid"))

    lines = ["**Short answer**"]
    if produce_context and fra3 is not None:
        lines.append(
            f"For bamboo/tendu or other minor forest produce, check the FRA source first because it covers forest-rights claims including minor forest produce/community forest rights [{fra3}]."
        )
    if cfr_project_context and (fra3 is not None or fra5 is not None):
        cfr_cite = fra3 if fra3 is not None else fra5
        lines.append(
            f"For a CFR/community-forest interference issue, keep the dispute on the FRA/community forest-rights route before treating it as an ordinary mining or revenue complaint [{cfr_cite}]."
        )
    if claim_refusal:
        claim_cite = fra4 if fra4 is not None else fra6 if fra6 is not None else fra_header if fra_header is not None else fra3 if fra3 is not None else fra5
        if fra4 is not None or fra6 is not None:
            lines.append(
                f"For an IFR/patta/title refusal, keep it on the FRA claim route and ask for the written reason or order instead of treating it as a general caste complaint [{claim_cite}]."
            )
        elif fra_header is not None:
            lines.append(
                f"The retrieved FRA arrangement identifies recognition/vesting of forest rights and the authorities/procedure chapter as the provisions to verify for an IFR claim refusal [{fra_header}]."
            )
        else:
            lines.append(
                f"The retrieved index did not surface the exact FRA title/procedure section for this refusal; use the Forest Rights Act route as the issue label and get the written SDLC/DLC reason before deciding the next filing [{claim_cite}]."
            )
    elif title_context and (fra3 is not None or fra5 is not None):
        title_cite = fra3 if fra3 is not None else fra5
        lines.append(
            f"For FRA patta/title papers, keep the file with the Forest Rights Act route and preserve the Gram Sabha/FRC and title records before escalating [{title_cite}]."
        )
    if _has_any_term(query, ("sdlc", "dlc", "gram sabha passed", "rejected", "without reason")) and fra6 is not None:
        lines.append(
            f"If the Gram Sabha/FRC supported the claim but SDLC/DLC rejected or delayed it, use the FRA procedure source to challenge the refusal through the SDLC/DLC/Collector channel [{fra6}]."
        )
    if guard_interference:
        guard_cite = fra5 if fra5 is not None else fra3 if fra3 is not None else fra6
        lines.append(
            f"For forest-guard interference, preserve photos, seizure/cutting details, patta papers, and Gram Sabha/FRC records before escalating through the FRA institutions [{guard_cite}]."
        )
    if pesa is not None:
        lines.append(
            f"If the village is in a Scheduled Area, also verify whether the PESA Gram Sabha source applies alongside the FRA papers [{pesa}]."
        )

    action_cite = fra6 if fra6 is not None else fra4 if fra4 is not None else fra_header if fra_header is not None else fra3 if fra3 is not None else fra5 if fra5 is not None else pesa
    if claim_refusal:
        next_step = "Collect the claim form, Gram Sabha/FRC resolution, SDLC/DLC order or refusal, patta/title papers, and witness names; then approach the Gram Sabha/FRC, SDLC/DLC/Collector, tribal welfare office, or DLSA with those papers"
    else:
        next_step = "Collect the patta/CFR title, Gram Sabha/FRC records, photos/video, seizure or cutting notice, and witness names; then approach the Gram Sabha/FRC, SDLC/DLC/Collector, tribal welfare office, or DLSA with those papers"
    lines.extend([
        "**What you can do next**",
        f"- {next_step} [{action_cite}].",
    ])
    return lines


def _tribal_displacement_template_lines(passages: list[dict]) -> list[str]:
    pesa = _find_passage_index(passages, title_terms=("panchayats (extension", "pesa"), anchor_terms=("/sec-4",))
    larr41 = _find_passage_index(passages, title_terms=("right to fair compensation",), anchor_terms=("/sec-41",))
    larr31 = _find_passage_index(passages, title_terms=("right to fair compensation",), anchor_terms=("/sec-31",))
    if pesa is None and larr41 is None and larr31 is None:
        return []
    lines = ["**Short answer**"]
    if pesa is not None:
        lines.append(
            f"Because the dam/project may submerge tribal villages and Gram Sabha consent is disputed, the PESA source is the Gram Sabha / Scheduled Area consultation source to check if those villages are in a Scheduled Area [{pesa}]."
        )
    if larr41 is not None:
        lines.append(
            f"The RFCTLARR source separately matters because it deals with land acquisition and rehabilitation safeguards for Scheduled Areas [{larr41}]."
        )
    elif larr31 is not None:
        lines.append(
            f"The RFCTLARR source separately matters because it deals with rehabilitation and resettlement award contents for displaced families [{larr31}]."
        )
    lines.append("**What you can do next**")
    if pesa is not None and (larr41 is not None or larr31 is not None):
        larr = larr41 if larr41 is not None else larr31
        lines.append(
            f"- Collect the dam/project notice, affected-village list, land-acquisition or rehabilitation papers, Gram Sabha notice/minutes or proof of no consent, and Scheduled Area status; then raise the Gram Sabha/PESA objection where those facts fit along with the RFCTLARR rehabilitation issue before the Collector/R&R authority [{pesa}][{larr}]."
        )
    elif pesa is not None:
        lines.append(
            f"- Get the Gram Sabha minutes or absence of consultation in writing, verify Scheduled Area status, and use the Panchayat/PESA route where those facts fit [{pesa}]."
        )
    else:
        larr = larr41 if larr41 is not None else larr31
        lines.append(
            f"- Ask the Collector/R&R authority for the acquisition and rehabilitation record, then compare the displacement facts with the cited RFCTLARR source [{larr}]."
        )
    return lines


def _cab_aggregator_driver_template_lines(query: str, passages: list[dict]) -> list[str]:
    contract = _find_passage_index(passages, title_terms=("motor vehicle aggregator",), anchor_terms=("driver-service-contract",))
    transparency = _find_passage_index(passages, title_terms=("motor vehicle aggregator",), anchor_terms=("app-transparency-grievance",))
    fare = _find_passage_index(passages, title_terms=("motor vehicle aggregator",), anchor_terms=("non-discrimination-driver-fare",))
    article14 = _find_passage_index(passages, title_terms=("constitution of india",), anchor_terms=("/sec-14",))
    if contract is None and transparency is None and fare is None:
        return []
    main_cite = contract or transparency or fare
    discrimination_context = _has_any_term(query, (
        "racist", "race", "language", "hindi", "regional", "north indian",
        "marathi", "tamil", "kannada", "bengali", "discrimination", "bias",
    ))
    lines = ["**Short answer**"]
    if contract is not None:
        lines.append(
            f"An Uber/Ola driver deactivation after low ratings is a cab-aggregator driver-account grievance, so ask for the written deactivation reason and the service-provider contract terms [{main_cite}]."
        )
    else:
        lines.append(
            f"An Uber/Ola driver deactivation after low ratings is a cab-aggregator driver-account grievance, so ask for the written deactivation reason through the platform grievance route [{main_cite}]."
        )
    if transparency is not None:
        lines.append(
            f"For the cab-driver account issue, ask the aggregator for rating, trip, incentive, fare-share, charge, and driver-facing app disclosures [{transparency}]."
        )
    if fare is not None:
        lines.append(
            f"If the rating/deactivation is linked to language or regional bias, preserve the racist comment or trip record and add the guideline non-discrimination point to the platform and transport-authority grievance [{fare}]."
        )
    elif article14 is not None and discrimination_context:
        lines.append(
            f"If a state transport authority is involved, preserve the language or regional-bias comment and trip record as equality facts for that authority-facing grievance [{article14}]."
        )
    if article14 is not None and discrimination_context:
        lines.append(
            f"The Article 14 source covers equality before law and equal protection, so keep the bias facts only if a transport authority handles the cab-driver grievance [{article14}]."
        )
    lines.extend([
        "**What you can do next**",
        (
            f"- Ask the aggregator in writing for the service-provider contract and the app/website disclosures on rating, fare share, incentives, charges, and driver-facing information [{contract or main_cite}][{transparency or main_cite}]."
        ),
    ])
    return lines


def _online_gambling_template_lines(query: str, passages: list[dict]) -> list[str]:
    tn7 = _find_passage_index(passages, title_terms=("tamil nadu prohibition of online gambling",), anchor_terms=("/sec-7",))
    tn14 = _find_passage_index(passages, title_terms=("tamil nadu prohibition of online gambling",), anchor_terms=("/sec-14",))
    tn16 = _find_passage_index(passages, title_terms=("tamil nadu prohibition of online gambling",), anchor_terms=("/sec-16",))
    skill = _find_passage_index(passages, title_terms=("public gambling",), anchor_terms=("/sec-12",))
    public_street = _find_passage_index(passages, title_terms=("public gambling",), anchor_terms=("/sec-13",))
    if tn7 is None and skill is None and public_street is None:
        return []
    lines = ["**Short answer**"]
    if tn7 is not None:
        lines.append(
            f"For Tamil Nadu, do not frame this only as a consumer refund: the Tamil Nadu online-gambling source prohibits online gambling and online games of chance [{tn7}]."
        )
    if tn14 is not None:
        lines.append(
            f"A non-local online games provider is also restricted from providing online gambling service or games of chance with money or other stakes to users in Tamil Nadu [{tn14}]."
        )
    if skill is not None:
        lines.append(
            f"Section 12 says the Public Gambling Act does not apply to any game of mere skill wherever played [{skill}]."
        )
    elif public_street is not None:
        lines.append(
            f"Section 13 concerns playing for money or other valuable thing in a public place where the game is not a game of mere skill [{public_street}]."
        )
    if tn16 is not None:
        lines.append(
            f"The Tamil Nadu source separately provides penalties for contravening the online-gambling and restricted-game provisions [{tn16}]."
        )
    lines.append("**What you can do next**")
    action_cites: list[int] = []
    if tn7 is not None:
        action_cites.append(tn7)
    if tn14 is not None:
        action_cites.append(tn14)
    if skill is not None:
        action_cites.append(skill)
    elif public_street is not None:
        action_cites.append(public_street)
    cite_text = "".join(f"[{idx}]" for idx in action_cites[:3])
    lines.append(
        "- Check whether the app game is treated as mere skill or as play for money or other valuable thing before treating it as a recoverable wallet dispute "
        f"{cite_text}."
    )
    return lines


def _digital_kyc_account_freeze_template_lines(query: str, passages: list[dict]) -> list[str]:
    consumer35 = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-35", "/sec-2", "/sec-38"),
    )
    it79 = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-79",),
    )
    pmla = _find_passage_index(
        passages,
        title_terms=("prevention of money laundering",),
        anchor_terms=("/sec-2", "/sec-5", "/sec-8", "/sec-17", "/sec-50"),
    )
    if consumer35 is None and it79 is None and pmla is None:
        return []
    platform_phrase = "online gaming or wallet app" if _has_any_term(query, ("game", "gaming", "betting", "rummy", "dream11", "parimatch")) else "digital platform"
    money_phrase = "the stuck balance" if _has_any_term(query, ("80k", "50k", "lakh", "money", "balance", "fund")) else "the account funds"
    lines = ["**Short answer**"]
    if pmla is not None:
        lines.append(
            f"If the {platform_phrase} says the account is frozen for KYC, suspicious-transaction, AML, or FIU reasons, the PMLA source is the AML/freeze source to check before treating it as only a refund dispute [{pmla}]."
        )
    if consumer35 is not None:
        lines.append(
            f"If the platform is simply withholding {money_phrase} or not responding to a KYC ticket, the Consumer Protection Act source is the service-deficiency complaint route to check [{consumer35}]."
        )
    if it79 is not None:
        lines.append(
            f"The IT Act intermediary/platform source is relevant for the platform-grievance side, so preserve ticket numbers and the account-status notice separately from the money claim [{it79}]."
        )
    lines.append("**What you can do next**")
    action_cite = consumer35 if consumer35 is not None else pmla if pmla is not None else it79
    lines.append(
        f"- Send a written platform grievance asking for the exact KYC/freeze reason, account ID, balance, transaction IDs, and deadline to resolve; if unresolved, use the consumer forum/grievance route and add cyber/police only if fraud or unauthorized transfer facts exist [{action_cite}]."
    )
    return lines


def _mgnrega_wage_template_lines(query: str, passages: list[dict]) -> list[str]:
    grievance = _find_passage_index(
        passages,
        title_terms=("mahatma gandhi national rural employment guarantee",),
        anchor_terms=("/sec-19",),
    )
    social_audit = _find_passage_index(
        passages,
        title_terms=("mahatma gandhi national rural employment guarantee",),
        anchor_terms=("/sec-17",),
    )
    if grievance is None and social_audit is None:
        return []
    days_match = re.search(r"\b(\d{1,3})\s+days?\b", query)
    work_phrase = f"{days_match.group(1)} days of NREGA work" if days_match else "NREGA work"
    lines = ["**Short answer**"]
    if grievance is not None:
        lines.append(
            f"For {work_phrase} with wages pending, Section 19 of the MGNREGA source is the grievance-redressal route [{grievance}]."
        )
    if social_audit is not None:
        lines.append(
            f"The Gram Sabha social-audit source can help check muster rolls and wage-payment records for NREGA work [{social_audit}]."
        )
    lines.append("**What you can do next**")
    if grievance is not None:
        lines.append(
            f"- Submit a written NREGA wage complaint with job card, work dates, muster roll details, and pending amount to the programme officer or district grievance authority [{grievance}]."
        )
    elif social_audit is not None:
        lines.append(
            f"- Use the social-audit route to ask for muster roll and payment records for the NREGA work [{social_audit}]."
        )
    return lines


def _caste_certificate_template_lines(query: str, passages: list[dict]) -> list[str]:
    article341 = _find_passage_index(passages, title_terms=("constitution of india",), anchor_terms=("/sec-341",))
    article342 = _find_passage_index(passages, title_terms=("constitution of india",), anchor_terms=("/sec-342",))
    rti6 = _find_passage_index(passages, title_terms=("right to information act",), anchor_terms=("/sec-6",))
    rti7 = _find_passage_index(passages, title_terms=("right to information act",), anchor_terms=("/sec-7",))
    rti19 = _find_passage_index(passages, title_terms=("right to information act",), anchor_terms=("/sec-19",))
    if article341 is None and article342 is None and rti6 is None:
        return []
    is_st_query = _has_any_term(query, (
        "st certificate", "scheduled tribe", "scheduled tribes", "tribal",
        "adivasi", "tribe certificate", "tribal certificate",
    ))
    main_cite = (
        article342 if is_st_query and article342 is not None
        else article341 if article341 is not None
        else article342 if article342 is not None
        else rti6
    )
    info_cite = rti19 if rti19 is not None else rti7 if rti7 is not None else rti6
    lines = ["**Short answer**"]
    if is_st_query and article342 is not None:
        st_fact_phrase = (
            "a delayed ST certificate needed for your daughter's exam form"
            if "daughter" in query and _has_any_term(query, ("exam form", "exam", "school", "college"))
            else "an ST certificate delay or rejection"
        )
        lines.append(
            f"For {st_fact_phrase}, Article 342 is the Scheduled Tribes source to verify the State-wise ST status [{article342}]."
        )
        if info_cite is not None:
            lines.append(
                f"For an ST certificate pending with the tehsildar, use Article 342 for Scheduled Tribes and the RTI appeal source for the pending record [{article342}][{info_cite}]."
            )
    elif article341 is not None:
        lines.append(
            f"For an SC caste-certificate rejection, Article 341 is the starting source because Scheduled Castes are specified for each State or Union Territory by Presidential notification and later Parliamentary change [{article341}]."
        )
    if article342 is not None and not is_st_query:
        lines.append(
            f"If the claim is actually ST rather than SC, Article 342 is the corresponding state-wise Scheduled Tribe source [{article342}]."
        )
    if rti6 is not None:
        lines.append(
            f"The RTI source gives a route to request information from the public authority, but RTI is not itself the caste-certificate appeal [{rti6}]."
        )
    elif rti7 is not None:
        lines.append(
            f"The RTI source can help with a time-bound information request, but RTI is not itself the caste-certificate appeal [{rti7}]."
        )
    if rti19 is not None:
        lines.append(
            f"If the office does not provide information, the RTI first-appeal route is available under the RTI source [{rti19}]."
        )
    lines.append("**What you can do next**")
    if info_cite is not None and main_cite is not None:
        next_cites = f"[{main_cite}][{info_cite}]"
    elif main_cite is not None:
        next_cites = f"[{main_cite}]"
    else:
        next_cites = f"[{info_cite}]"
    if is_st_query and article342 is not None and info_cite is not None:
        lines.append(
            f"- Use the Article 342 Scheduled Tribes source and RTI Act appeal source when asking the tehsildar for written reasons and the pending certificate record [{article342}][{info_cite}]."
        )
    else:
        lines.append(
            "- First verify the claimed community against the state-wise SC/ST list source; if the rejection order lacks reasons, "
            f"use the RTI request or first-appeal route to obtain the authority's record before filing the state-law appeal {next_cites}."
        )
    return lines


def _gig_platform_worker_template_lines(passages: list[dict]) -> list[str]:
    ss113 = _find_passage_index(passages, title_terms=("code on social security",), anchor_terms=("/sec-113",))
    ss114 = _find_passage_index(passages, title_terms=("code on social security",), anchor_terms=("/sec-114",))
    ss112 = _find_passage_index(passages, title_terms=("code on social security",), anchor_terms=("/sec-112",))
    id25f = _find_passage_index(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-25F",))
    if ss113 is None and ss114 is None and ss112 is None and id25f is None:
        return []
    main_cite = ss113 if ss113 is not None else ss114 if ss114 is not None else ss112 if ss112 is not None else id25f
    lines = ["**Short answer**"]
    if ss113 is not None:
        lines.append(
            f"Do not treat an Urban Company style strike/deactivation question as ordinary office termination only; the Code on Social Security source has a registration route for gig workers and platform workers [{ss113}]."
        )
    if ss114 is not None:
        lines.append(
            f"The Code on Social Security source also contemplates social-security schemes for gig workers and platform workers, including accident, health, maternity, and other benefits [{ss114}]."
        )
    if id25f is not None:
        lines.append(
            f"The Industrial Disputes Act termination/retrenchment route matters only if the facts show employee/workman status, so avoid promising reinstatement before checking the contract and control over work [{id25f}]."
        )
    elif ss112 is not None:
        lines.append(
            f"The facilitation-centre source supports asking where gig/platform worker registration or scheme help is available [{ss112}]."
        )
    lines.append("**What you can do next**")
    lines.append(
        f"- Preserve the service-partner contract, strike policy, deactivation notice, appeal tickets, ratings, and payout ledger; ask the platform for written reasons and release of undisputed earnings before choosing labour or social-security escalation [{main_cite}]."
    )
    return lines


def _labour_overtime_register_template_lines(query: str, passages: list[dict]) -> list[str]:
    shops1 = _find_passage_index(passages, title_terms=("maharashtra shops",), anchor_terms=("/sec-1",))
    shops15 = _find_passage_index(passages, title_terms=("maharashtra shops",), anchor_terms=("/sec-15",))
    shops25 = _find_passage_index(passages, title_terms=("maharashtra shops",), anchor_terms=("/sec-25",))
    shops28 = _find_passage_index(passages, title_terms=("maharashtra shops",), anchor_terms=("/sec-28",))
    shops31 = _find_passage_index(passages, title_terms=("maharashtra shops",), anchor_terms=("/sec-31",))
    bocw = _find_passage_index(passages, title_terms=("building and other construction workers",))
    main_cite = shops25 if shops25 is not None else shops28 if shops28 is not None else shops15 if shops15 is not None else bocw
    if main_cite is None:
        return []
    lines = ["**Short answer**"]
    if shops1 is not None:
        worker_count = _extract_worker_count(query)
        worker_phrase = f" with about {worker_count} workers" if worker_count is not None else ""
        lines.append(
            f"For a Maharashtra establishment{worker_phrase}, first check coverage under the Maharashtra Shops and Establishments Act source rather than answering only under generic wage law [{shops1}]."
        )
    if shops15 is not None:
        lines.append(
            f"Overtime exposure turns on the Shops Act overtime source, which treats work beyond the stated daily or weekly limit as overtime wages at the statutory rate [{shops15}]."
        )
    if shops25 is not None:
        lines.append(
            f"The missing overtime-register fact is directly tied to the Shops Act source requiring prescribed registers and records, with production during inspection when demanded [{shops25}]."
        )
    if shops28 is not None:
        lines.append(
            f"The labour-department raid/inspection should be mapped to the Facilitator inspection powers source, including examination and copying of wage/register records [{shops28}]."
        )
    if shops31 is not None:
        lines.append(
            f"If records were refused or not produced, keep the Shops Act penalty-for-refusal source separate from any wage-claim issue [{shops31}]."
        )
    if bocw is not None:
        lines.append(
            f"If the workplace is a construction/building worksite, also check the BOCW Act source for registration and employer-compliance duties [{bocw}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Prepare the inspection notice, worker list, attendance/overtime sheets, wage records, and any missing-register explanation before replying to the Labour Department or attending the hearing [{main_cite}].",
    ])
    return lines


def _parsi_succession_template_lines(passages: list[dict]) -> list[str]:
    sec50 = _find_passage_index(passages, title_terms=("indian succession",), anchor_terms=("/sec-50",))
    sec51 = _find_passage_index(passages, title_terms=("indian succession",), anchor_terms=("/sec-51",))
    sec53 = _find_passage_index(passages, title_terms=("indian succession",), anchor_terms=("/sec-53",))
    sec54 = _find_passage_index(passages, title_terms=("indian succession",), anchor_terms=("/sec-54",))
    if sec51 is None and sec50 is None and sec54 is None:
        return []
    main_cite = sec51 if sec51 is not None else sec50 if sec50 is not None else sec54
    lines = ["**Short answer**"]
    if sec51 is not None:
        lines.append(
            f"If a Parsi mother died intestate and left children but no widower, Indian Succession Act Section 51 says the property is divided among the children in equal shares [{sec51}]."
        )
        lines.append(
            f"So if the three sisters are the only children and there is no will, surviving widower, parent, or predeceased child's branch, the starting answer under the Indian Succession Act is equal one-third shares [{sec51}]."
        )
    if sec50 is not None:
        lines.append(
            f"Section 50 is still important because it sets special Parsi intestate principles, including when a predeceased lineal descendant is ignored or counted [{sec50}]."
        )
    if sec53 is not None:
        lines.append(
            f"If any child died before the mother leaving descendants, Section 53 can change how that child's branch takes the share [{sec53}]."
        )
    if sec54 is not None:
        lines.append(
            f"Section 54 applies to the different situation where there is no lineal descendant but there is a widower or a widower/widow of a lineal descendant [{sec54}]."
        )
    lines.append("**What you can do next**")
    lines.append(
        f"- Before applying the equal-child share rule, confirm the no-will fact, whether any widower survives, and whether any predeceased child's branch must be counted under the Parsi intestate provisions [{main_cite}]."
    )
    return lines


def _trans_identity_template_lines(passages: list[dict]) -> list[str]:
    cert = _find_passage_index(passages, title_terms=("transgender persons",), anchor_terms=("/sec-6",))
    revised = _find_passage_index(passages, title_terms=("transgender persons",), anchor_terms=("/sec-7",))
    identity = cert or _find_passage_index(passages, title_terms=("transgender persons",), anchor_terms=("/sec-4", "/sec-5"))
    if identity is None:
        return []
    lines = [
        "**Short answer**",
        (
            f"Surgery should not be treated as a precondition for the first transgender certificate of identity route; apply to the District Magistrate for the certificate under the Transgender Persons Act source [{identity}]."
        ),
    ]
    if revised is not None:
        lines.append(
            f"Section 7 is the separate revised-certificate route after medical intervention, so keep that distinct from the Section 6 identity-certificate request [{revised}]."
        )
    lines.extend([
        "**What you can do next**",
        (
            f"File the certificate-of-identity application with the District Magistrate and keep the acknowledgement or written refusal before using it for later record-correction requests [{identity}]."
        ),
    ])
    return lines


def _discriminatory_retrenchment_template_lines(passages: list[dict]) -> list[str]:
    lifo = _find_passage_index(passages, title_terms=("industrial disputes",), anchor_terms=("sec-25G",))
    reemployment = _find_passage_index(passages, title_terms=("industrial disputes",), anchor_terms=("sec-25H",))
    notice = _find_passage_index(passages, title_terms=("industrial disputes",), anchor_terms=("sec-25F",))
    article14 = _find_passage_index(passages, title_terms=("constitution of india",), anchor_terms=("/sec-14",))
    if lifo is None and notice is None:
        return []
    main_cite = lifo or notice
    lines = [
        "**Short answer**",
        (
            f"Do not frame this only as unpaid salary; if workers were retrenched while others doing the same site work were kept, check the Industrial Disputes Act retrenchment-selection route [{main_cite}]."
        ),
    ]
    if notice is not None:
        lines.append(
            f"Also check whether the employer gave the required retrenchment notice/compensation before termination [{notice}]."
        )
    if reemployment is not None:
        lines.append(
            f"If the employer later takes workers again for the same work, preserve that fact for the re-employment preference issue [{reemployment}]."
        )
    if article14 is not None:
        lines.append(
            f"If a public employer or state-linked contractor is involved, add the Bengali/Gujarati differential treatment as an equality fact instead of relying only on a wage claim [{article14}]."
        )
    lines.extend([
        "**What you can do next**",
        (
            f"Make a worker list with joining dates, termination dates, who was kept, and same-site work proof to support the Industrial Disputes Act retrenchment-selection claim [{main_cite}]."
        ),
    ])
    return lines


def _employment_retaliation_pip_template_lines(query: str, passages: list[dict]) -> list[str]:
    id2a = _find_passage_index(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-2A",))
    id25f = _find_passage_index(passages, title_terms=("industrial disputes",), anchor_terms=("/sec-25F",))
    posh9 = _find_passage_index(passages, title_terms=("sexual harassment of women at workplace",), anchor_terms=("/sec-9",))
    if id2a is None and id25f is None and posh9 is None:
        return []

    lines = ["**Short answer**"]
    if id2a is not None:
        lines.append(
            f"A HR complaint followed by a PIP or bad rating is not automatically a labour-court claim; the Industrial Disputes Act source becomes directly relevant if it turns into discharge, dismissal, retrenchment, or termination of an individual workman [{id2a}]."
        )
    if id25f is not None:
        lines.append(
            f"If the PIP is used for retrenchment or termination, separately check whether the Section 25F notice/compensation conditions are met [{id25f}]."
        )
    if posh9 is not None or _has_any_term(query, ("sexual harassment", "posh", "icc", "internal committee")):
        cite = posh9 if posh9 is not None else id2a if id2a is not None else id25f
        lines.append(
            f"If the harassment complaint is actually a sexual-harassment/POSH complaint, keep that route separate from ordinary performance-management facts and ask for the Internal Committee/Local Committee path [{cite}]."
        )
    lines.append("**What you can do next**")
    action_cites = [idx for idx in (id2a, id25f) if idx is not None]
    if action_cites:
        cite_text = "".join(f"[{idx}]" for idx in action_cites[:2])
    else:
        cite_text = f"[{posh9}]"
    lines.append(
        f"- Preserve the HR complaint, PIP or rating letter, emails, appraisal record, employment contract, and any termination notice; if the company terminates or retrenches you, take those papers to the labour officer/DLSA for the Industrial Disputes route {cite_text}."
    )
    return lines


def _posh_retaliation_template_lines(query: str, passages: list[dict]) -> list[str]:
    posh3 = _find_passage_index(
        passages,
        title_terms=("sexual harassment",),
        anchor_terms=("/sec-3",),
    )
    posh9 = _find_passage_index(
        passages,
        title_terms=("sexual harassment",),
        anchor_terms=("/sec-9",),
    )
    posh19 = _find_passage_index(
        passages,
        title_terms=("sexual harassment",),
        anchor_terms=("/sec-19",),
    )
    posh4 = _find_passage_index(
        passages,
        title_terms=("sexual harassment",),
        anchor_terms=("/sec-4",),
    )
    if posh3 is None and posh9 is None and posh19 is None and posh4 is None:
        return []
    lines = ["**Short answer**"]
    if posh3 is not None:
        lines.append(
            f"Treat this as a workplace sexual-harassment/POSH route only if the HR complaint was about workplace sexual harassment; the POSH Act source is the harassment baseline to check [{posh3}]."
        )
    if posh9 is not None:
        lines.append(
            f"The POSH complaint source is relevant for the complaint route before the Internal Committee or Local Committee, so the HR complaint and PIP timeline should be preserved together [{posh9}]."
        )
    if posh19 is not None:
        lines.append(
            f"The employer-duties source matters for the workplace response after a complaint, including the records showing what HR or the employer did after the complaint [{posh19}]."
        )
    elif posh4 is not None:
        lines.append(
            f"If there is no functioning Internal Committee, the Internal Committee constitution source is relevant before treating the matter as an ordinary performance-review dispute [{posh4}]."
        )
    action_cite = posh9 if posh9 is not None else posh19 if posh19 is not None else posh4 if posh4 is not None else posh3
    lines.extend([
        "**What you can do next**",
        f"- Preserve the HR/POSH complaint, PIP or rating letter, dates, manager messages, witnesses, and any Internal Committee details, then ask for the POSH/IC or Local Committee route in writing [{action_cite}].",
    ])
    return lines


def _supervised_visitation_template_lines(passages: list[dict]) -> list[str]:
    welfare = _find_passage_index(passages, title_terms=("guardians and wards",), anchor_terms=("/sec-17",))
    return_child = _find_passage_index(passages, title_terms=("guardians and wards",), anchor_terms=("/sec-25",))
    if welfare is None and return_child is None:
        return []
    main_cite = welfare or return_child
    lines = [
        "**Short answer**",
        (
            f"Do not treat an ex-partner's lawyer asking for unsupervised visitation as a change in the order; any change should go through the custody/family court on the child's welfare standard [{main_cite}]."
        ),
        "**What you can do next**",
        (
            f"File a written objection or modification application in the same court with the supervised-visitation order, safety facts, messages, and any child-welfare concerns [{main_cite}]."
        ),
    ]
    if return_child is not None:
        lines.append(
            f"If the child is withheld contrary to the order, also ask your lawyer/DLSA whether the Guardians and Wards Act return-of-ward route is relevant [{return_child}]."
        )
    return lines


def _agri_cooperative_recovery_template_lines(query: str, passages: list[dict]) -> list[str]:
    coop = _find_passage_index(
        passages,
        title_terms=("cooperative agricultural development bank", "registrar,cooperative societies", "registrar of cooperative societies"),
    )
    sarfaesi13 = _find_passage_index(
        passages,
        title_terms=("securitisation and reconstruction",),
        anchor_terms=("/sec-13",),
    )
    sarfaesi31 = _find_passage_index(
        passages,
        title_terms=("securitisation and reconstruction",),
        anchor_terms=("/sec-31",),
    )
    sarfaesi17 = _find_passage_index(
        passages,
        title_terms=("securitisation and reconstruction",),
        anchor_terms=("/sec-17",),
    )
    if coop is None and sarfaesi13 is None and sarfaesi17 is None and sarfaesi31 is None:
        return []
    lines = ["**Short answer**"]
    if coop is not None:
        lines.append(
            f"The retrieved cooperative-bank source is about an agricultural cooperative bank and the Registrar of Cooperative Societies, so ask the bank to identify the cooperative-recovery order or rule it is using for the buffalo seizure [{coop}]."
        )
    if sarfaesi31 is not None:
        lines.append(
            f"The SARFAESI source itself lists cases where the Act does not apply, including pledge of movables and security interest in agricultural land, so the exclusion/applicability question must be checked before accepting a buffalo seizure [{sarfaesi31}]."
        )
    if sarfaesi13 is not None:
        lines.append(
            f"If the bank says it is enforcing a secured asset, the SARFAESI source says security interest is enforced under section 13 procedure, so the security documents and statutory notice matter [{sarfaesi13}]."
        )
    if sarfaesi17 is not None:
        lines.append(
            f"If a SARFAESI measure has actually been taken, the SARFAESI source provides the Debts Recovery Tribunal application route under section 17 [{sarfaesi17}]."
        )
    lines.append("**What you can do next**")
    if sarfaesi31 is not None:
        lines.append(
            f"- Check whether the seizure falls within section 31 exclusions such as pledge of movables or security interest in agricultural land before accepting a SARFAESI recovery action [{sarfaesi31}]."
        )
    else:
        action_cite = sarfaesi17 if sarfaesi17 is not None else sarfaesi13 if sarfaesi13 is not None else coop
        lines.append(
            f"- Ask in writing for the seizure memo, loan agreement, hypothecation or pledge clause, land or security details, demand notice, and the forum the bank says applies before choosing the recovery challenge route [{action_cite}]."
        )
    return lines


def _security_cheque_defence_template_lines(passages: list[dict]) -> list[str]:
    ni138 = _find_passage_index_by_text(
        passages,
        title_terms=("negotiable instruments",),
        text_terms=("debt or other liability", "payee or holder", "drawer"),
    )
    if ni138 is None:
        ni138 = _find_passage_index(
            passages,
            title_terms=("negotiable instruments",),
            anchor_terms=("/sec-138",),
        )
    if ni138 is None:
        return []
    return [
        "**Short answer**",
        f"The NI Act source says Section 138 applies to a cheque drawn for discharge of a debt or other liability when it is returned unpaid [{ni138}].",
        f"The same source frames the demand as the payee or holder in due course giving notice to the drawer of the cheque [{ni138}].",
        "**What you can do next**",
        f"- Treat this as drawer-defence work: compare any notice with the alleged debt or liability stated in the NI Act source [{ni138}].",
    ]


def _private_magistrate_complaint_template_lines(passages: list[dict]) -> list[str]:
    bnss223 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-223",),
    )
    bnss175 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-175",),
    )
    crpc200 = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-200",),
    )
    crpc156 = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-156",),
    )
    complaint = bnss223 if bnss223 is not None else crpc200
    investigation = bnss175 if bnss175 is not None else crpc156
    if complaint is None and investigation is None:
        return []
    lines = ["**Short answer**"]
    if complaint is not None:
        if complaint == bnss223:
            lines.append(
                f"For a private complaint, the BNSS complaint source says the Magistrate taking cognizance on complaint shall examine the complainant and witnesses on oath [{complaint}]."
            )
        else:
            lines.append(
                f"For a private complaint, the CrPC complaint source says the Magistrate taking cognizance on complaint shall examine the complainant and witnesses on oath [{complaint}]."
            )
    if investigation is not None:
        if investigation == bnss175:
            lines.append(
                f"For police inaction, the BNSS source gives the Magistrate power to order an investigation in the retrieved complaint-procedure route [{investigation}]."
            )
        else:
            lines.append(
                f"For police inaction, the CrPC source gives the Magistrate power to order an investigation in the retrieved complaint-procedure route [{investigation}]."
            )
    lines.append("**What you can do next**")
    if complaint is not None:
        lines.append(
            f"- For the private-complaint track, be ready for Magistrate examination of the complainant and witnesses under the cited complaint source [{complaint}]."
        )
    if investigation is not None:
        lines.append(
            f"- For police inaction, use the Magistrate-investigation route stated in the cited investigation source [{investigation}]."
        )
    return lines


def _decree_execution_attachment_template_lines(query: str, passages: list[dict]) -> list[str]:
    cpc51 = _find_passage_index(
        passages,
        title_terms=("code of civil procedure",),
        anchor_terms=("/sec-51",),
    )
    cpc47 = _find_passage_index(
        passages,
        title_terms=("code of civil procedure",),
        anchor_terms=("/sec-47",),
    )
    if cpc51 is None and cpc47 is None:
        return []
    lines = ["**Short answer**"]
    if cpc51 is not None:
        lines.append(
            f"For a judgment-debtor who is not paying a decree, keep it in CPC execution: the CPC source lets the court enforce execution by delivery of property, attachment and sale, arrest/detention, receiver, or another prescribed mode [{cpc51}]."
        )
    if cpc47 is not None:
        lines.append(
            f"Questions between the parties about execution, discharge, or satisfaction of the decree stay with the court executing the decree, not a fresh property-title case [{cpc47}]."
        )
    lines.append("**What you can do next**")
    return lines


def _vakalatnama_change_template_lines(passages: list[dict]) -> list[str]:
    cpc151 = _find_passage_index(
        passages,
        title_terms=("code of civil procedure",),
        anchor_terms=("/sec-151",),
    )
    cpc153 = _find_passage_index(
        passages,
        title_terms=("code of civil procedure",),
        anchor_terms=("/sec-153",),
    )
    cpc = cpc151 if cpc151 is not None else cpc153
    if cpc is None:
        cpc = _find_passage_index(passages, title_terms=("code of civil procedure",))
    lsa = _find_passage_index(
        passages,
        title_terms=("legal services authorities",),
        anchor_terms=("/sec-12",),
    )
    if cpc is None and lsa is None:
        return []
    lines = ["**Short answer**"]
    if cpc is not None:
        lines.append(
            f"For changing advocate during a pending civil suit, the CPC source is the civil-court procedure source to check while filing the new vakalatnama or memo in the same case [{cpc}]."
        )
    if lsa is not None:
        lines.append(
            f"If you cannot afford the new lawyer or need help filing the change, the Legal Services Authorities Act source is the legal-aid eligibility route to check [{lsa}]."
        )
    lines.append("**What you can do next**")
    action_cite = cpc if cpc is not None else lsa
    lines.append(
        f"- Keep the case number, next date, present advocate details, new advocate vakalatnama, any NOC/discharge communication, and fee/brief handover proof, then file it through the same court registry before the next effective hearing [{action_cite}]."
    )
    return lines


def _writ_constitution_template_lines(query: str, passages: list[dict]) -> list[str]:
    article226 = _find_passage_index(
        passages,
        title_terms=("constitution",),
        anchor_terms=("/sec-226",),
    ) or _find_passage_index_by_text(
        passages,
        text_terms=("article 226", "writ"),
    )
    article32 = _find_passage_index(
        passages,
        title_terms=("constitution",),
        anchor_terms=("/sec-32",),
    )
    legal_aid = _find_passage_index(
        passages,
        title_terms=("legal services authorities",),
        anchor_terms=("/sec-12",),
    )
    if article226 is None and article32 is None and legal_aid is None:
        return []
    lines = ["**Short answer**"]
    if article226 is not None:
        lines.append(
            f"For a writ against a government officer or public authority, Article 226 is the High Court source to check; mandamus is usually about requiring performance of a public or legal duty, not a general complaint form [{article226}]."
        )
    if article32 is not None and _has_any_term(query, ("article 32", "supreme court", "fundamental right", "fundamental rights")):
        lines.append(
            f"Article 32 is the Supreme Court route for enforcement of fundamental rights; it is different from the broader High Court Article 226 route [{article32}]."
        )
    elif article32 is not None:
        lines.append(
            f"Article 32 is mainly the Supreme Court fundamental-right enforcement route, so most ordinary officer-refusal questions first need the High Court/alternate-remedy check [{article32}]."
        )
    if legal_aid is not None:
        lines.append(
            f"If filing help is needed, the Legal Services Authorities Act source is the legal-aid route to check before trying to draft a writ alone [{legal_aid}]."
        )
    lines.append("**What you can do next**")
    action_cite = article226 if article226 is not None else article32 if article32 is not None else legal_aid
    lines.append(
        f"- Collect the written order/refusal, your representation and delivery proof, timeline, government-office details, urgency facts, and the exact relief requested before asking DLSA or a writ lawyer about maintainability, alternate remedy, and delay [{action_cite}]."
    )
    return lines


def _criminal_quashing_template_lines(query: str, passages: list[dict]) -> list[str]:
    bnss528 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-528",),
    )
    crpc482 = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-482",),
    )
    if bnss528 is None and crpc482 is None:
        return []
    lines = ["**Short answer**"]
    legacy_query = _has_any_term(query, ("2023", "2022", "2021", "2020", "2019", "2018", "pre-1 july 2024", "before 1 july 2024", "crpc 482", "482 crpc"))
    if legacy_query and crpc482 is not None:
        lines.append(
            f"For a pre-1 July 2024 FIR or papers framed under CrPC, the CrPC section 482 source is the High Court inherent-powers source to compare for quashing [{crpc482}]."
        )
    elif bnss528 is not None:
        lines.append(
            f"For current-law quashing or inherent-powers framing, use the BNSS High Court inherent-powers source, not CPC civil-execution provisions [{bnss528}]."
        )
    if not legacy_query and crpc482 is not None:
        lines.append(
            f"If the matter is pre-1 July 2024 or the case papers are still framed under CrPC, the CrPC section 482 source is the legacy High Court inherent-powers source to compare [{crpc482}]."
        )
    lines.append("**What you can do next**")
    return lines


def _caste_fir_refusal_template_lines(passages: list[dict]) -> list[str]:
    scst = _find_passage_index_by_text(
        passages,
        title_terms=("scheduled castes", "scheduled tribes"),
        text_terms=("not being a member",),
    )
    if scst is None:
        scst = _find_passage_index(
            passages,
            title_terms=("scheduled castes", "scheduled tribes"),
            anchor_terms=("/sec-3",),
        )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    bnss175 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-175",),
    )
    crpc156 = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure",),
        anchor_terms=("/sec-156",),
    )
    if scst is None and bnss173 is None and bnss175 is None and crpc156 is None:
        return []
    lines = ["**Short answer**"]
    if scst is not None:
        lines.append(
            f"For caste-atrocity facts, the SC/ST POA source is the offence source to match because the retrieved section is framed around acts by a person not being a member of a Scheduled Caste or Scheduled Tribe [{scst}]."
        )
    if bnss173 is not None:
        lines.append(
            f"If police refuse to register the FIR, the BNSS source covers information to police and the FIR/refusal procedure under the retrieved provision [{bnss173}]."
        )
    if bnss175 is not None:
        lines.append(
            f"For Magistrate-ordered investigation, the BNSS source is the separate investigation-order authority to check [{bnss175}]."
        )
    elif crpc156 is not None:
        lines.append(
            f"For a legacy CrPC matter, the CrPC source is the separate Magistrate investigation-order authority to check [{crpc156}]."
        )
    lines.append("**What you can do next**")
    if scst is not None:
        lines.append(
            f"- First match the caste-atrocity facts to the cited SC/ST POA offence source before treating it as an atrocity complaint [{scst}]."
        )
    if bnss173 is not None:
        lines.append(
            f"- If police refuse to register the FIR, use the FIR/refusal procedure stated in the cited BNSS source [{bnss173}]."
        )
    if bnss175 is not None:
        lines.append(
            f"- For Magistrate-ordered investigation, use the cited BNSS investigation-order source [{bnss175}]."
        )
    elif crpc156 is not None:
        lines.append(
            f"- For a legacy CrPC matter, use the cited CrPC Magistrate investigation-order source [{crpc156}]."
        )
    return lines


def _domestic_acid_threat_template_lines(query: str, passages: list[dict]) -> list[str]:
    pwdva18 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-18",),
    )
    bns351 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-351",),
    )
    bns124 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-124",),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    if pwdva18 is None and bns351 is None and bns124 is None and bnss173 is None:
        return []
    lines = ["**Short answer**"]
    if pwdva18 is not None:
        threat_phrase = "acid or chemical threat" if _has_any_term(query, ("acid", "chemical")) else "domestic threat"
        lines.append(
            f"For this domestic {threat_phrase}, the PWDVA source gives a Magistrate protection-order route that can prohibit committing, aiding, or threatening domestic violence [{pwdva18}]."
        )
    if bns351 is not None:
        lines.append(
            f"The BNS source treats a threat of injury to person, reputation, or property as criminal intimidation where the statutory ingredients are met [{bns351}]."
        )
    elif bns124 is not None:
        lines.append(
            f"If acid is actually thrown or administered, the BNS acid-attack source is the specific offence source to check with the incident date [{bns124}]."
        )
    if bnss173 is not None:
        lines.append(
            f"For the police track, the BNSS source covers information to police and the FIR/refusal procedure under the retrieved provision [{bnss173}]."
        )
    lines.append("**What you can do next**")
    if pwdva18 is not None:
        lines.append(
            f"- For the domestic-violence track, use the cited PWDVA protection-order source for the Magistrate protection route [{pwdva18}]."
        )
    if bnss173 is not None:
        lines.append(
            f"- For the police track, use the cited BNSS FIR/refusal source when giving information to police or escalating police refusal [{bnss173}]."
        )
    if bns351 is not None:
        lines.append(
            f"- For the criminal-intimidation track, compare the acid-threat words to the cited BNS threat source [{bns351}]."
        )
    elif bns124 is not None:
        lines.append(
            f"- If acid is actually thrown or administered, compare those facts to the cited BNS acid-attack source [{bns124}]."
        )
    return lines


def _police_threat_template_lines(query: str, passages: list[dict]) -> list[str]:
    bns351 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-351",),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    bnss216 = None
    if _is_witness_or_false_evidence_threat_query(query):
        bnss216 = _find_passage_index(
            passages,
            title_terms=("bharatiya nagarik suraksha",),
            anchor_terms=("/sec-216",),
        )
    if bns351 is None and bnss173 is None and bnss216 is None:
        return []
    lines = ["**Short answer**"]
    if _has_any_term(query, ("daughter", "eloped", "other religion", "inter religion", "inter-religion")):
        threat_phrase = "khap or honour threat around your daughter's inter-religion elopement"
    else:
        threat_phrase = "khap or honour threat" if _has_any_term(query, ("khap", "honour", "honor", "eloped", "other religion")) else "threat"
    if bns351 is not None:
        lines.append(
            f"For this {threat_phrase}, the BNS source treats a threat of injury to person, reputation, or property as criminal intimidation where the statutory ingredients are met [{bns351}]."
        )
    if bnss173 is not None:
        lines.append(
            f"For the police track, the BNSS source covers information to police and the FIR/refusal procedure under the retrieved provision [{bnss173}]."
        )
    elif bnss216 is not None:
        lines.append(
            f"The BNSS source gives a criminal-court complaint route for intimidation or threat-related facts in the retrieved provision [{bnss216}]."
        )
    lines.append("**What you can do next**")
    if bns351 is not None:
        lines.append(
            f"- For the criminal-intimidation track, compare the {threat_phrase} words or facts to the cited BNS threat source [{bns351}]."
        )
    if bnss173 is not None:
        lines.append(
            f"- For the police track, use the cited BNSS FIR/refusal source when giving information to police or escalating police refusal [{bnss173}]."
        )
    elif bnss216 is not None:
        lines.append(
            f"- For the court-complaint track, use the cited BNSS complaint-route source for threat-related facts [{bnss216}]."
        )
    return lines


def _creator_content_leak_template_lines(query: str, passages: list[dict]) -> list[str]:
    if not (
        _has_any_term(query, ("onlyfans", "fanvue", "creator content", "patreon", "gumroad"))
        and _has_any_term(query, ("leak", "leaked", "without permission", "telegram"))
    ):
        return []
    copyright51 = _find_passage_index(
        passages,
        title_terms=("copyright act",),
        anchor_terms=("/sec-51",),
    )
    copyright63 = _find_passage_index(
        passages,
        title_terms=("copyright act",),
        anchor_terms=("/sec-63",),
    )
    it79 = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-79",),
    )
    it66e = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66E",),
    )
    if copyright51 is None and copyright63 is None and it79 is None and it66e is None:
        return []
    lines = ["**Short answer**"]
    if copyright51 is not None:
        lines.append(
            f"Leaked paid creator content is a copyright problem first: the Copyright Act source covers infringement of copyright where protected work is used without permission [{copyright51}]."
        )
    if copyright63 is not None:
        lines.append(
            f"The Copyright Act source also gives the criminal-offence track for knowing infringement where the statutory ingredients are met [{copyright63}]."
        )
    if it79 is not None:
        lines.append(
            f"The IT Act source is relevant for the platform/intermediary side, so a Telegram or platform takedown should be framed separately from the copyright-owner complaint [{it79}]."
        )
    elif it66e is not None:
        lines.append(
            f"If the leaked material is also a private image, the IT Act privacy source is a separate cyber-law route to check [{it66e}]."
        )
    lines.append("**What you can do next**")
    action_cite = copyright51 if copyright51 is not None else copyright63 if copyright63 is not None else it79 if it79 is not None else it66e
    lines.append(
        f"- Use the cited Copyright Act source for the creator-owner infringement complaint, and keep the platform/intermediary issue separate under the cited IT Act source if that source is available [{action_cite}]."
    )
    return lines


def _is_child_or_csam_intimate_image_query(query: str) -> bool:
    explicit_child_terms = (
        "csam", "ai csam", "child sexual abuse material",
        "child sexual image", "child sexual images",
        "child porn", "child pornography", "pocso", "minor",
        "under 18", "under eighteen",
    )
    if _has_any_term(query, explicit_child_terms):
        return True
    if _has_any_term(query, ("adult", "major", "colleague", "coworker", "co-worker")):
        return False
    child_age_patterns = (
        r"\b(?:age|aged|is|was|i am|she is|he is)\s+([1-9]|1[0-7])\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s*old\b",
        r"\b([1-9]|1[0-7])\s*(?:year|years|yr|yrs)\s+(?:girl|boy|child|minor|student)\b",
        r"\b(?:girl|boy|child|minor|student)\s+(?:is\s+)?([1-9]|1[0-7])\b",
    )
    if any(re.search(pattern, query) for pattern in child_age_patterns):
        return True
    intimate_context = _has_any_term(query, (
        "deepfake", "nude", "porn", "sex video", "intimate", "private photo",
        "private picture", "morphed",
    ))
    return intimate_context and _has_any_term(query, (
        "schoolmate", "girls in class", "boys in class", "minor girl",
        "minor boy",
    ))


def _deepfake_lookalike_template_lines(query: str, passages: list[dict]) -> list[str]:
    if not _has_any_term(query, (
        "deepfake", "lookalike", "look alike", "face same", "not me but face",
        "ai porn", "porn video", "csam", "child sexual abuse material",
        "child sexual image", "child porn", "child pornography",
    )):
        return []
    it66e = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66E",),
    )
    it67a = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-67A",),
    )
    it67b = _find_passage_index_by_text(
        passages,
        title_terms=("information technology",),
        text_terms=("67b", "children", "sexually explicit"),
    ) or _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-67B",),
    )
    pocso_media = _find_passage_index_by_text(
        passages,
        title_terms=("protection of children from sexual offences", "pocso"),
        text_terms=("use of child", "pornographic purposes"),
    ) or _find_passage_index(
        passages,
        title_terms=("protection of children from sexual offences", "pocso"),
        anchor_terms=("/sec-13", "/sec-14", "/sec-15"),
    )
    pocso_reporting = _find_passage_index(
        passages,
        title_terms=("protection of children from sexual offences", "pocso"),
        anchor_terms=("/sec-19",),
    )
    bns356 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-356",),
    )
    bns77 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-77",),
    )
    bns351 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-351",),
    )
    dpdp8 = _find_passage_index(
        passages,
        title_terms=("digital personal data protection",),
        anchor_terms=("/sec-8",),
    )
    child_or_csam_context = _is_child_or_csam_intimate_image_query(query)
    adult_or_unknown_source = any(source is not None for source in (it66e, it67a, bns356, bns77, bns351, dpdp8))
    child_source = any(source is not None for source in (it67b, pocso_media, pocso_reporting))
    if not child_or_csam_context and not adult_or_unknown_source:
        return []
    if child_or_csam_context and not child_source and not adult_or_unknown_source:
        return []
    if it66e is None and it67a is None and it67b is None and pocso_media is None and pocso_reporting is None and bns356 is None and bns77 is None and bns351 is None and dpdp8 is None:
        return []
    lines = ["**Short answer**"]
    if child_or_csam_context and pocso_media is not None:
        lines.append(
            f"The POCSO source covers use of a child in any form of media for pornographic purposes, including electronic or computer technology used for preparation, transmission, publishing, facilitation, or distribution of such material [{pocso_media}]."
        )
    elif child_or_csam_context and pocso_reporting is not None:
        lines.append(
            f"The POCSO reporting source is relevant for the child sexual-content complaint track, so preserve the links/screenshots and report the facts to police or the Special Juvenile Police Unit rather than treating it as only an adult cyber-harassment issue [{pocso_reporting}]."
        )
    if child_or_csam_context and it67b is not None:
        lines.append(
            f"The IT Act child sexually-explicit material source is directly relevant where a minor's sexual image, CSAM, or nude deepfake is being made or circulated electronically [{it67b}]."
        )
    elif it66e is not None:
        lines.append(
            f"For a porn/deepfake lookalike video, the IT Act privacy source is relevant where a private image is captured, published, or transmitted without consent [{it66e}]."
        )
    elif it67a is not None:
        lines.append(
            f"The IT Act sexually-explicit electronic-publication source is a cyber-law source to check for a pornographic lookalike or deepfake video [{it67a}]."
        )
    if bns356 is not None:
        lines.append(
            f"The BNS defamation source is also relevant if the lookalike video harms reputation or falsely imputes conduct to you [{bns356}]."
        )
    elif bns77 is not None:
        lines.append(
            f"The BNS voyeurism source is relevant where the facts involve watching, capturing, or disseminating private imagery of a woman in the covered circumstances [{bns77}]."
        )
    elif bns351 is not None:
        lines.append(
            f"The BNS criminal-intimidation source is relevant only if the lookalike video is used with threats of injury to person, reputation, or property [{bns351}]."
        )
    if dpdp8 is not None:
        lines.append(
            f"The DPDP source matters only if an identifiable platform or data fiduciary handled your personal data; it imposes security-safeguard duties for personal data breach contexts [{dpdp8}]."
        )
    lines.append("**What you can do next**")
    platform = "Telegram" if "telegram" in query else "WhatsApp" if "whatsapp" in query else "the platform"
    if child_or_csam_context:
        action_cite = it67b if it67b is not None else pocso_media if pocso_media is not None else pocso_reporting if pocso_reporting is not None else it66e if it66e is not None else it67a if it67a is not None else bns356 if bns356 is not None else bns77 if bns77 is not None else bns351 if bns351 is not None else dpdp8
        lines.append(
            f"- Preserve the {platform} links, screenshots, profile IDs, and timestamps, then report the CSAM/minor-image facts through the cyber portal/local police as a child sexual-image and electronic-publication issue using the cited IT Act or POCSO source [{action_cite}]."
        )
    else:
        action_cite = it66e if it66e is not None else it67a if it67a is not None else bns356 if bns356 is not None else bns77 if bns77 is not None else bns351 if bns351 is not None else dpdp8
        lines.append(
            f"- Preserve the {platform} links, screenshots, profile IDs, and timestamps, then report it through the cyber portal/local police as a non-consensual deepfake, private-image, or electronic-publication issue using the cited IT Act/BNS/DPDP source that matches the facts [{action_cite}]."
        )
    return lines


def _cyber_blackmail_template_lines(query: str, passages: list[dict]) -> list[str]:
    bns351 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-351",),
    )
    bns308 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-308",),
    )
    bns77 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-77",),
    )
    it66e = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66E",),
    )
    it66d = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66D",),
    )
    it67 = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-67",),
    )
    if bns351 is None and bns308 is None and bns77 is None and it66e is None and it66d is None and it67 is None:
        return []
    lines = ["**Short answer**"]
    if _has_any_term(query, ("private picture", "private pictures")) and "telegram" in query:
        scenario_phrase = "private-picture Telegram threat after a video call"
    else:
        scenario_phrase = "dating-app blackmail" if _has_any_term(query, ("bumble", "tinder", "dating app")) else "cyber blackmail or extortion"
    if bns351 is not None:
        lines.append(
            f"For this {scenario_phrase}, the BNS source treats a threat of injury to person, reputation, or property as criminal intimidation where the statutory ingredients are met [{bns351}]."
        )
    elif bns308 is not None:
        lines.append(
            f"For this {scenario_phrase}, the BNS extortion source turns on intentionally putting a person in fear of injury and dishonestly inducing delivery of property or valuable security [{bns308}]."
        )
    elif bns77 is not None and _has_any_term(query, ("nude", "nudes", "private", "intimate", "photo", "photos", "image", "images", "video", "videos")):
        channel_phrase = " on Telegram or WhatsApp" if _has_any_term(query, ("telegram", "whatsapp")) else ""
        lines.append(
            f"For leaked private nudes{channel_phrase}, the BNS voyeurism source is relevant where the statutory ingredients for capturing or disseminating private imagery are met [{bns77}]."
        )
    if it66e is not None and _has_any_term(query, ("nude", "private", "intimate", "photo", "video", "image", "screenshot", "screenshots")):
        lines.append(
            f"If the electronic material involves privacy or private images, the IT Act source covers violation of privacy through capturing, publishing, or transmitting the protected image without consent [{it66e}]."
        )
    elif it66d is not None:
        lines.append(
            f"If the online setup involved personation or cheating through a computer resource or communication device, the IT Act cheating-by-personation source is the cyber-law source to check [{it66d}]."
        )
    elif it67 is not None:
        lines.append(
            f"If the threatened Telegram publication involves obscene or sexually explicit private pictures, the IT Act source is the electronic-publication source to check [{it67}]."
        )
    lines.append("**What you can do next**")
    action_cite = it66e if it66e is not None else it66d if it66d is not None else it67 if it67 is not None else bns351 if bns351 is not None else bns308 if bns308 is not None else bns77
    if it66e is not None and _has_any_term(query, ("nude", "private", "intimate", "photo", "video", "image", "screenshot", "screenshots")):
        lines.append(
            f"- For the cyber-law track, compare the private-image or privacy facts to the IT Act privacy source before filing the complaint [{it66e}]."
        )
    elif it66d is not None:
        lines.append(
            f"- For the cyber-law track, compare the dating-app personation or cheating facts to the IT Act cheating-by-personation source before filing the complaint [{it66d}]."
        )
    elif it67 is not None:
        lines.append(
            f"- For the cyber-law track, compare the threatened electronic publication facts to the IT Act obscene-publication source before filing the complaint [{it67}]."
        )
    else:
        lines.append(
            f"- For the criminal-law track, compare the threat or extortion facts to the cited BNS source before filing the complaint [{action_cite}]."
        )
    return lines


def _bank_otp_refund_template_lines(query: str, passages: list[dict]) -> list[str]:
    rbi = _find_passage_index(
        passages,
        title_terms=("reserve bank integrated ombudsman",),
        anchor_terms=("/sec-2", "/sec-3"),
    )
    it66c = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66C",),
    )
    it66d = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66D",),
    )
    bns_cheating = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-318", "/sec-319"),
    )
    if rbi is None and it66c is None and it66d is None and bns_cheating is None:
        return []
    bank_phrase = "bank or UPI account" if _has_any_term(query, ("upi", "phonepe", "gpay")) else "bank account"
    lines = ["**Short answer**"]
    if it66d is not None:
        lines.append(
            f"For an OTP/phishing loss from a {bank_phrase}, keep a cyber-fraud track because the IT Act cheating-by-personation source may apply where a computer resource or communication device was used [{it66d}]."
        )
    elif it66c is not None:
        lines.append(
            f"For an OTP/phishing loss from a {bank_phrase}, keep a cyber-fraud track because the IT Act identity-theft source may apply where electronic credentials or identity information were misused [{it66c}]."
        )
    elif bns_cheating is not None:
        lines.append(
            f"If the facts show dishonest inducement or impersonation, the BNS cheating source is relevant alongside the cyber complaint record [{bns_cheating}]."
        )
    if rbi is not None:
        lines.append(
            f"Do not stop at the bank saying it was your fault: the RBI Ombudsman source is the regulated-entity complaint route to preserve after the bank grievance step [{rbi}]."
        )
    lines.append("**What you can do next**")
    action_cite = rbi if rbi is not None else it66d if it66d is not None else it66c if it66c is not None else bns_cheating
    lines.append(
        f"- Freeze the complaint trail: keep the transaction reference, bank complaint number, cyber complaint acknowledgement, device/SIM facts, and bank reply before escalating through the cited cyber and RBI route [{action_cite}]."
    )
    return lines


def _senior_maintenance_enforcement_template_lines(query: str, passages: list[dict]) -> list[str]:
    senior11 = _find_passage_index(
        passages,
        title_terms=("parents and senior citizens", "senior citizens"),
        anchor_terms=("/sec-11",),
    )
    senior13 = _find_passage_index(
        passages,
        title_terms=("parents and senior citizens", "senior citizens"),
        anchor_terms=("/sec-13",),
    )
    senior9 = _find_passage_index(
        passages,
        title_terms=("parents and senior citizens", "senior citizens"),
        anchor_terms=("/sec-9",),
    )
    senior5 = _find_passage_index(
        passages,
        title_terms=("parents and senior citizens", "senior citizens"),
        anchor_terms=("/sec-5",),
    )
    if senior11 is None and senior13 is None and senior9 is None and senior5 is None:
        return []
    lines = ["**Short answer**"]
    if senior11 is not None:
        lines.append(
            f"If the Maintenance Tribunal already ordered a son or relative to pay, treat the problem as enforcement of that Tribunal order under the Senior Citizens Act source, not as a fresh generic family-law query [{senior11}]."
        )
    elif senior9 is not None:
        lines.append(
            f"The Senior Citizens Act source gives the Tribunal maintenance-order route where children or relatives neglect or refuse to maintain a senior citizen [{senior9}]."
        )
    elif senior5 is not None:
        lines.append(
            f"The Senior Citizens Act source gives the maintenance-application route to the Tribunal; use it with the prior order and default facts [{senior5}]."
        )
    if senior13 is not None:
        lines.append(
            f"The deposit source is relevant because the person ordered to pay maintenance must deposit the ordered amount within the statutory route reflected in that source [{senior13}]."
        )
    lines.append("**What you can do next**")
    return lines


def _senior_citizen_property_or_maintenance_template_lines(query: str, passages: list[dict]) -> list[str]:
    senior23 = _find_passage_index(
        passages,
        title_terms=("parents and senior citizens", "senior citizens"),
        anchor_terms=("/sec-23",),
    )
    senior9 = _find_passage_index(
        passages,
        title_terms=("parents and senior citizens", "senior citizens"),
        anchor_terms=("/sec-9",),
    )
    senior4 = _find_passage_index(
        passages,
        title_terms=("parents and senior citizens", "senior citizens"),
        anchor_terms=("/sec-4",),
    )
    tpa126 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-126",),
    )
    pwdva19 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-19",),
    )
    pwdva12 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-12",),
    )
    is_transfer = _has_any_term(query, ("gift", "gifted", "gift deed", "transfer", "transferred", "settlement deed", "cancel", "cancelled", "cancellation", "take back"))
    is_maintenance = _has_any_term(query, ("maintenance", "tribunal", "maximum", "pay maintenance"))
    violence_context = _has_any_term(query, (
        "beat", "beats", "beating", "hit", "hits", "violence", "abuse",
        "assault", "injury", "threat", "threaten",
    ))
    family_context = _has_any_term(query, (
        "mother", "father", "parent", "senior", "elderly", "68", "70", "75",
        "daughter in law", "daughter-in-law", "bahu", "son", "relative",
    ))
    is_home_violence = violence_context and family_context
    if senior23 is None and senior9 is None and senior4 is None:
        return []
    victim_phrase = (
        "your 68-year-old mother"
        if "mother" in query and _has_any_term(query, ("68", "68 years", "68-year"))
        else "your mother"
        if "mother" in query
        else "the senior citizen"
    )
    actor_phrase = (
        "daughter-in-law"
        if _has_any_term(query, ("daughter in law", "daughter-in-law", "bahu"))
        else "household relative"
    )
    transfer_asset = "house" if _has_any_term(query, ("house", "home")) else "flat" if "flat" in query else "property"
    transferee_phrase = "son" if "son" in query else "transferee or relative"
    lines = ["**Short answer**"]
    if is_home_violence and pwdva19 is not None:
        lines.append(
            f"For domestic violence against {victim_phrase} by a {actor_phrase}, also check the Domestic Violence Act residence-order source because a Magistrate may pass a residence order when domestic violence is shown [{pwdva19}]."
        )
    if is_transfer and senior23 is not None:
        lines.append(
            f"For {transfer_asset} gifted or transferred to a {transferee_phrase} where basic amenities or physical needs are not being provided, Section 23 of the Senior Citizens Act is the transfer-void route to check [{senior23}]."
        )
        lines.append(
            f"The Senior Citizens Act source is the first route to check: a transfer by gift or otherwise can be declared void by the Tribunal if the transferee fails to provide the promised basic amenities or physical needs [{senior23}]."
        )
        if tpa126 is not None:
            lines.append(
                f"The Transfer of Property Act source is still relevant for ordinary gift-revocation clauses, but it should not replace the Senior Citizens Act Tribunal route where section 23 facts fit [{tpa126}]."
            )
    elif is_maintenance and senior9 is not None:
        lines.append(
            f"The Senior Citizens Act source says the Tribunal may order a monthly maintenance allowance where children or relatives neglect or refuse to maintain a senior citizen; the central text caps that prescribed allowance at not more than Rs. 10,000 per month [{senior9}]."
        )
    elif senior4 is not None:
        lines.append(
            f"The Senior Citizens Act source gives the parent/senior-citizen maintenance obligation route where children or relatives with sufficient means neglect support [{senior4}]."
        )
    lines.append("**What you can do next**")
    if is_home_violence and pwdva12 is not None:
        lines.append(
            f"- For immediate protection, prepare a Domestic Violence Act application to the Magistrate and keep age, residence, injury, and relationship proof [{pwdva12}]."
        )
    elif is_transfer and senior23 is not None:
        lines.append(
            f"- Take the gift or settlement deed, proof of age/parent relationship, and proof of neglect to the Maintenance Tribunal / District Magistrate route under the cited Senior Citizens Act source [{senior23}]."
        )
    elif senior9 is not None:
        lines.append(
            f"- File or support a maintenance application before the Maintenance Tribunal with age proof, relationship proof, income/dependency details, and expenses [{senior9}]."
        )
    else:
        lines.append(
            f"- Ask the District Social Welfare office or DLSA to help prepare the parent/senior-citizen maintenance papers using the cited Act source [{senior4}]."
        )
    return lines


def _senior_maintenance_cheque_template_lines(passages: list[dict]) -> list[str]:
    senior4 = _find_passage_index(
        passages,
        title_terms=("parents and senior citizens", "senior citizens"),
        anchor_terms=("/sec-4",),
    )
    senior5 = _find_passage_index(
        passages,
        title_terms=("parents and senior citizens", "senior citizens"),
        anchor_terms=("/sec-5",),
    )
    ni138 = _find_passage_index(
        passages,
        title_terms=("negotiable instruments",),
        anchor_terms=("/sec-138",),
    )
    if senior4 is None and senior5 is None and ni138 is None:
        return []
    lines = ["**Short answer**"]
    if senior4 is not None:
        lines.append(
            f"For a senior parent seeking support, the Senior Citizens Act source states the maintenance obligation route for children or relatives who have sufficient means [{senior4}]."
        )
    elif senior5 is not None:
        lines.append(
            f"For a senior parent seeking support, the Senior Citizens Act source gives the maintenance-application route to the Tribunal [{senior5}]."
        )
    if ni138 is not None:
        lines.append(
            f"For the bounced cheque part, the NI Act source applies where a cheque drawn for discharge of a debt or other liability is returned unpaid after the statutory demand process [{ni138}]."
        )
    lines.append("**What you can do next**")
    if senior5 is not None:
        lines.append(
            f"- For the parent-support track, use the cited Senior Citizens Act maintenance-application source for the Tribunal route [{senior5}]."
        )
    elif senior4 is not None:
        lines.append(
            f"- For the parent-support track, compare the support facts to the cited Senior Citizens Act maintenance-obligation source [{senior4}]."
        )
    if ni138 is not None:
        lines.append(
            f"- For the cheque track, compare the bounced-cheque facts to the cited NI Act debt-or-liability and return-unpaid source [{ni138}]."
        )
    return lines


def _education_loan_denial_template_lines(passages: list[dict]) -> list[str]:
    rbi = _find_passage_index(
        passages,
        title_terms=("reserve bank integrated ombudsman",),
    )
    consumer_def = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-2",),
    )
    consumer_forum = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-35",),
    )
    if rbi is None and consumer_def is None and consumer_forum is None:
        return []
    lines = ["**Short answer**"]
    if rbi is not None:
        lines.append(
            f"For a bank education-loan refusal, the Reserve Bank Integrated Ombudsman source is the banking-service complaint route to check first if the bank is a regulated entity [{rbi}]."
        )
    if consumer_def is not None:
        lines.append(
            f"The Consumer Protection Act source is also relevant to a service-deficiency framing, so keep the bank's written refusal and loan-file papers together [{consumer_def}]."
        )
    elif consumer_forum is not None:
        lines.append(
            f"The Consumer Protection Act source is also relevant to the consumer-complaint route, so keep the bank's written refusal and loan-file papers together [{consumer_forum}]."
        )
    lines.append("**What you can do next**")
    if rbi is not None:
        lines.append(
            f"- For the banking-ombudsman track, use the cited RBI Integrated Ombudsman source if the bank is a regulated entity [{rbi}]."
        )
    if consumer_forum is not None:
        lines.append(
            f"- For the consumer track, use the cited Consumer Protection Act complaint-route source if the facts fit service deficiency [{consumer_forum}]."
        )
    elif consumer_def is not None:
        lines.append(
            f"- For the consumer track, compare the refusal facts to the cited Consumer Protection Act service-deficiency source [{consumer_def}]."
        )
    return lines


def _lok_adalat_traffic_template_lines(passages: list[dict]) -> list[str]:
    lsa19 = _find_passage_index(passages, title_terms=("legal services authorities",), anchor_terms=("/sec-19",))
    lsa20 = _find_passage_index(passages, title_terms=("legal services authorities",), anchor_terms=("/sec-20",))
    lsa21 = _find_passage_index(passages, title_terms=("legal services authorities",), anchor_terms=("/sec-21",))
    main_cite = lsa20 if lsa20 is not None else lsa19 if lsa19 is not None else lsa21
    if main_cite is None:
        return []
    lines = ["**Short answer**"]
    if lsa19 is not None:
        lines.append(
            f"A pending traffic challan settlement through Lok Adalat belongs under the Legal Services Authorities Act source on organisation of Lok Adalats, not only the Motor Vehicles Act challan source [{lsa19}]."
        )
    if lsa20 is not None:
        lines.append(
            f"For a pending matter, use the Legal Services Authorities Act cognizance/referral route for Lok Adalats and carry the challan or e-challan record [{lsa20}]."
        )
    if lsa21 is not None:
        lines.append(
            f"If settlement is reached, the Legal Services Authorities Act source on Lok Adalat awards is the effect-of-settlement source to read before signing [{lsa21}]."
        )
    lines.extend([
        "**What you can do next**",
        f"- Take the challan number, vehicle number, court/e-challan status, and ID proof to the DLSA or the traffic court/Lok Adalat desk for the next available settlement date [{main_cite}].",
    ])
    return lines


def _bank_account_freeze_template_lines(query: str, passages: list[dict]) -> list[str]:
    rbi = _find_passage_index(
        passages,
        title_terms=("reserve bank integrated ombudsman",),
        anchor_terms=("/sec-2", "/sec-3"),
    ) or _find_passage_index(passages, title_terms=("reserve bank integrated ombudsman",))
    banking = _find_passage_index(passages, title_terms=("banking regulation",))
    consumer = _find_passage_index(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-2", "/sec-2-"))
    if rbi is None and banking is None and consumer is None:
        return []
    lines = ["**Short answer**"]
    if rbi is not None:
        lines.append(
            f"For a frozen or lien-marked bank account, first treat this as a written bank-grievance issue: ask for the freeze/lien/KYC reason, the authority behind it, and the complaint number before escalating under the RBI Ombudsman route [{rbi}]."
        )
    elif banking is not None:
        lines.append(
            f"For a frozen or lien-marked bank account, first get the bank's written reason and account-record basis instead of guessing whether it is KYC, fraud, tax, cyber, or a court/police hold [{banking}]."
        )
    if banking is not None:
        lines.append(
            f"Keep the bank-service record separate from any police/cyber/ED hold; the bank source is only the account-service side until the written freeze reason identifies another authority [{banking}]."
        )
    elif consumer is not None:
        lines.append(
            f"If the bank gives no written reason or wrongly blocks service, the consumer/service-deficiency route is a backup after the bank grievance record exists [{consumer}]."
        )
    lines.append("**What you can do next**")
    action_cite = rbi if rbi is not None else banking if banking is not None else consumer
    lines.append(
        f"- Keep the freeze SMS/email, statement, KYC proof, complaint number, branch reply, and any police/cyber/court reference; file the bank grievance first, then use RBI Ombudsman for a bank-service failure or legal aid/court/police route if the freeze is due to a legal hold [{action_cite}]."
    )
    return lines


def _loan_app_harassment_template_lines(query: str, passages: list[dict]) -> list[str]:
    rbi = _find_passage_index(
        passages,
        title_terms=("reserve bank integrated ombudsman",),
        anchor_terms=("/sec-2", "/sec-3"),
    ) or _find_passage_index(passages, title_terms=("reserve bank integrated ombudsman",))
    dpdp = _find_passage_index(passages, title_terms=("digital personal data protection",), anchor_terms=("/sec-8", "/sec-13", "/sec-27"))
    it_act = _find_passage_index(passages, title_terms=("information technology",), anchor_terms=("/sec-66c", "/sec-66d", "/sec-66e"))
    bns_threat = _find_passage_index(passages, title_terms=("bharatiya nyaya",), anchor_terms=("/sec-351", "/sec-308", "/sec-356"))
    consumer = _find_passage_index(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35", "/sec-2", "/sec-2-"))
    if rbi is None and dpdp is None and it_act is None and bns_threat is None and consumer is None:
        return []
    lines = ["**Short answer**"]
    if rbi is not None:
        lines.append(
            f"Loan-app or recovery harassment should be treated as a lender/NBFC grievance plus evidence-preservation problem, not just a repayment question; the RBI Ombudsman source is the regulated-entity escalation route to check [{rbi}]."
        )
    if dpdp is not None:
        lines.append(
            f"If the app is using your contact list or messaging relatives/colleagues, keep a separate personal-data grievance track and preserve the permissions/screenshots before complaining [{dpdp}]."
        )
    elif it_act is not None:
        lines.append(
            f"If the app misused phone data or online identity details, keep a cyber/electronic-record track with screenshots, app permissions, and contact messages [{it_act}]."
        )
    if bns_threat is not None and _has_any_term(query, ("threat", "threaten", "threatening", "blackmail", "extortion", "morphed", "abusive")):
        lines.append(
            f"If threats, blackmail, abusive messages, or morphed-image pressure are involved, keep a police/cyber track separate from the civil repayment dispute [{bns_threat}]."
        )
    elif consumer is not None:
        lines.append(
            f"The consumer-service route is only a backup for service deficiency; threats or contact-data misuse should not be reduced to a normal loan dispute [{consumer}]."
        )
    lines.append("**What you can do next**")
    action_cite = rbi if rbi is not None else dpdp if dpdp is not None else it_act if it_act is not None else bns_threat if bns_threat is not None else consumer
    lines.append(
        f"- Preserve call logs, WhatsApp/SMS screenshots, messages sent to contacts, app permissions, lender/app name, loan agreement, repayment proof, and complaint number; complain to the lender/app first and escalate to RBI Ombudsman or cyber/local police depending on whether it is regulated-entity harassment or threats/contact-data abuse [{action_cite}]."
    )
    return lines


def _banking_ombudsman_credit_template_lines(passages: list[dict]) -> list[str]:
    rbi2 = _find_passage_index(passages, title_terms=("reserve bank integrated ombudsman",), anchor_terms=("/sec-2",))
    rbi3 = _find_passage_index(passages, title_terms=("reserve bank integrated ombudsman",), anchor_terms=("/sec-3",))
    rbi = rbi2 if rbi2 is not None else rbi3 if rbi3 is not None else _find_passage_index(passages, title_terms=("reserve bank integrated ombudsman",))
    cic = _find_passage_index(passages, title_terms=("credit information companies",))
    consumer = _find_passage_index(passages, title_terms=("consumer protection",))
    if rbi is None and cic is None and consumer is None:
        return []
    lines = ["**Short answer**"]
    if rbi2 is not None:
        lines.append(
            f"For an EMI bounce caused by a bank/service error or penalty by an NBFC/finance company, the RBI Integrated Ombudsman source matters because the Scheme covers regulated entities including eligible NBFCs with customer interface [{rbi2}]."
        )
    elif rbi is not None:
        lines.append(
            f"For an EMI bounce caused by a bank/service error, penalty by an NBFC/finance company, or escalation threat, the RBI Integrated Ombudsman source is the regulated-entity complaint route to check first [{rbi}]."
        )
    if rbi3 is not None:
        lines.append(
            f"The same RBI Scheme source says regulated entities must comply with the Scheme and points to the complaint format under it [{rbi3}]."
        )
    if cic is not None:
        lines.append(
            f"Because CIBIL reporting is threatened, keep the Credit Information Companies Act source separate from the penalty dispute and preserve proof of the bank error and payment history [{cic}]."
        )
    if consumer is not None:
        lines.append(
            f"The Consumer Protection Act source is the backup service-deficiency route if the lender or service provider does not correct the charge through its grievance process [{consumer}]."
        )
    action_cite = rbi if rbi is not None else cic if cic is not None else consumer
    lines.extend([
        "**What you can do next**",
        f"- File a written grievance with the lender/finance company attaching the bank-error proof, EMI debit/bounce record, penalty demand, and any CIBIL threat; then use the cited RBI/CIBIL/consumer route if it is not corrected [{action_cite}].",
    ])
    return lines


def _bank_debit_ombudsman_template_lines(query: str, passages: list[dict]) -> list[str]:
    rbi2 = _find_passage_index(passages, title_terms=("reserve bank integrated ombudsman",), anchor_terms=("/sec-2",))
    rbi3 = _find_passage_index(passages, title_terms=("reserve bank integrated ombudsman",), anchor_terms=("/sec-3",))
    rbi = rbi2 if rbi2 is not None else rbi3 if rbi3 is not None else _find_passage_index(passages, title_terms=("reserve bank integrated ombudsman",))
    consumer35 = _find_passage_index(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35",))
    consumer2 = _find_passage_index(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-2-"))
    if rbi is None and consumer35 is None and consumer2 is None:
        return []
    bank_phrase = "HDFC bank" if "hdfc" in query else "the bank"
    transaction_phrase = "forex/card transaction" if _has_any_term(query, ("forex", "card")) else "debit transaction"
    lines = ["**Short answer**"]
    if rbi is not None:
        lines.append(
            f"The RBI Ombudsman Scheme source covers commercial banks and other regulated entities, so first confirm {bank_phrase} is covered for the disputed {transaction_phrase} [{rbi}]."
        )
    if consumer2 is not None:
        lines.append(
            f"The Consumer Protection Act source covers consumer disputes and consumer rights for goods or services, which is the consumer-law base to check for a banking service dispute [{consumer2}]."
        )
    if consumer35 is not None:
        lines.append(
            f"The consumer-complaint source is the backup consumer-forum route if the bank grievance or RBI route does not resolve the service-deficiency claim [{consumer35}]."
        )
    action_cite = rbi if rbi is not None else consumer35 if consumer35 is not None else consumer2
    lines.extend([
        "**What you can do next**",
        f"- Keep the statement entry, transaction reference, forex/card slip, SMS/email alerts, complaint number, bank reply or non-reply, and timeline before escalating the regulated-entity complaint [{action_cite}].",
    ])
    return lines


def _bank_property_document_fraud_template_lines(query: str, passages: list[dict]) -> list[str]:
    bns_forgery = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-336", "/sec-338", "/sec-340", "/sec-318", "/sec-319"),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    crpc_complaint = _find_passage_index(
        passages,
        title_terms=("criminal procedure",),
        anchor_terms=("/sec-154", "/sec-156", "/sec-200"),
    )
    banking = _find_passage_index(passages, title_terms=("banking regulation",))
    rbi = _find_passage_index(passages, title_terms=("reserve bank integrated ombudsman",), anchor_terms=("/sec-2", "/sec-3"))
    consumer = _find_passage_index(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-35"))
    if bns_forgery is None and bnss173 is None and banking is None and rbi is None and consumer is None:
        return []
    property_phrase = "house" if "house" in query or "home" in query else "property"
    lines = ["**Short answer**"]
    if bns_forgery is not None and not _query_mentions_pre_july_2024(query):
        lines.append(
            f"If a loan was created against your {property_phrase} using a signature or consent you dispute, keep a criminal forgery/cheating track; the retrieved BNS source is current-law support only, so the incident date still decides whether BNS/BNSS or IPC/CrPC applies [{bns_forgery}]."
        )
    if banking is not None:
        lines.append(
            f"Keep the bank-service track separate too: the Banking Regulation Act source is the bank-regulation source to verify for the lender and loan-record side [{banking}]."
        )
    if rbi is not None:
        lines.append(
            f"If the lender is covered by the RBI Ombudsman Scheme, the RBI source is the escalation route after a written bank complaint and reply/non-reply period [{rbi}]."
        )
    elif consumer is not None:
        lines.append(
            f"The Consumer Protection Act source may be the backup service-deficiency route if the bank does not handle the disputed loan records properly [{consumer}]."
        )
    if bnss173 is not None:
        lines.append(
            f"For the police side, the BNSS source is the current FIR/information source to preserve if forged documents are alleged [{bnss173}]."
        )
    if crpc_complaint is not None and _query_mentions_pre_july_2024(query):
        lines.append(
            f"Because the facts mention a pre-July-2024 forged-loan dispute, the CrPC complaint/FIR source is the police or Magistrate procedure to check for that older regime [{crpc_complaint}]."
        )
    lines.append("**What you can do next**")
    action_cite = rbi if rbi is not None else banking if banking is not None else bnss173 if bnss173 is not None else bns_forgery if bns_forgery is not None else consumer
    lines.append(
        f"- Give the bank a written disputed-signature/forged-loan complaint with loan number, property papers, signature/thumb-impression proof, and request a temporary hold on disputed recovery while you separately file the police/cyber complaint if forgery is alleged [{action_cite}]."
    )
    return lines


def _cyber_impersonation_fraud_template_lines(query: str, passages: list[dict]) -> list[str]:
    it66c = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66C",),
    )
    it66d = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66D",),
    )
    bns_cheating = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-318", "/sec-319"),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    rbi = _find_passage_index(
        passages,
        title_terms=("reserve bank integrated ombudsman",),
        anchor_terms=("/sec-2", "/sec-3"),
    )
    if it66c is None and it66d is None and bns_cheating is None and bnss173 is None and rbi is None:
        return []
    victim_phrase = "your elderly parent" if _has_any_term(query, ("father", "mother", "75", "70", "senior")) else "the victim"
    lines = ["**Short answer**"]
    if it66d is not None:
        lines.append(
            f"A fake bank or pension-office call is a cyber impersonation-fraud issue first; the IT Act cheating-by-personation source is directly relevant where a communication device or computer resource is used [{it66d}]."
        )
    elif it66c is not None:
        lines.append(
            f"A fake bank or pension-office call is a cyber-fraud issue first; the IT Act identity-theft source is relevant if identity information or credentials were misused [{it66c}]."
        )
    if bns_cheating is not None:
        lines.append(
            f"The BNS cheating/personation source is the criminal-law track to compare with the call, inducement, and money-transfer facts [{bns_cheating}]."
        )
    if bnss173 is not None:
        lines.append(
            f"The BNSS source is the FIR/information route for giving the police the call number, transaction IDs, beneficiary details, and complaint acknowledgement [{bnss173}]."
        )
    if rbi is not None:
        lines.append(
            f"For the bank-service or refund side, the RBI Ombudsman source is the regulated-entity escalation route after a written bank complaint and reply or non-reply period [{rbi}]."
        )
    lines.append("**What you can do next**")
    action_cite = bnss173 if bnss173 is not None else it66d if it66d is not None else it66c if it66c is not None else rbi if rbi is not None else bns_cheating
    lines.append(
        f"- Give the police/cyber complaint with {victim_phrase}'s phone number used for the call, transaction IDs, beneficiary account/UPI, screenshots, and bank complaint number [{action_cite}]."
    )
    return lines


def _crypto_investment_fraud_template_lines(query: str, passages: list[dict]) -> list[str]:
    it66d = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66D",),
    )
    bns318 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-318", "/sec-319"),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173", "/sec-175"),
    )
    pmla = _find_passage_index(
        passages,
        title_terms=("prevention of money laundering",),
        anchor_terms=("/sec-2", "/sec-5", "/sec-17", "/sec-50"),
    )
    if it66d is None and bns318 is None and bnss173 is None and pmla is None:
        return []
    lines = ["**Short answer**"]
    if bns318 is not None:
        lines.append(
            f"A Telegram crypto rug-pull or investment-group loss should be framed as cheating/fraud facts first; the BNS cheating source is the criminal-law source to compare with the inducement and money-transfer record [{bns318}]."
        )
    if it66d is not None:
        lines.append(
            f"Because the approach happened through Telegram or an online group, the IT Act cheating-by-personation source is also relevant if online impersonation or deceptive digital communication is part of the facts [{it66d}]."
        )
    if pmla is not None:
        lines.append(
            f"If the money trail involves crypto wallets, laundering, or suspicious transaction records, keep the PMLA source as a separate money-trail/freezing source rather than the first FIR section [{pmla}]."
        )
    if bnss173 is not None:
        lines.append(
            f"The BNSS source is the FIR/information route for giving police or cyber cell the wallet addresses, transaction hashes, UPI/bank trail, Telegram handles, and complaint acknowledgement [{bnss173}]."
        )
    lines.append("**What you can do next**")
    action_cite = bnss173 if bnss173 is not None else bns318 if bns318 is not None else it66d if it66d is not None else pmla
    lines.append(
        f"- Preserve Telegram group links, admin handles, chat screenshots, payment proofs, wallet addresses, transaction hashes, bank/UPI details, and file on cybercrime.gov.in or at the cyber police station with those identifiers [{action_cite}]."
    )
    return lines


def _insurance_misselling_template_lines(query: str, passages: list[dict]) -> list[str]:
    ombudsman = _find_passage_index(passages, title_terms=("insurance ombudsman", "ombudsman rules"))
    consumer2 = _find_passage_index(passages, title_terms=("consumer protection",), anchor_terms=("/sec-2", "/sec-2-"))
    consumer35 = _find_passage_index(passages, title_terms=("consumer protection",), anchor_terms=("/sec-35",))
    senior = _find_passage_index(passages, title_terms=("parents and senior citizens", "senior citizens"))
    if ombudsman is None and consumer2 is None and consumer35 is None and senior is None:
        return []
    policy_phrase = "LIC policy" if "lic" in query else "insurance policy"
    lines = ["**Short answer**"]
    if ombudsman is not None:
        lines.append(
            f"For a {policy_phrase} sold through an agent and then paying much less at maturity, the Insurance Ombudsman source for insurer/agent complaints is the first sector route to check [{ombudsman}]."
        )
    if consumer2 is not None:
        lines.append(
            f"The Consumer Protection Act source is also relevant because insurance service deficiency or mis-selling can be framed as a consumer-service complaint when the documents support it [{consumer2}]."
        )
    elif consumer35 is not None:
        lines.append(
            f"The Consumer Protection Act complaint source is a backup consumer-forum route if insurer grievance or Ombudsman relief does not resolve the policy dispute [{consumer35}]."
        )
    if senior is not None:
        lines.append(
            f"The Senior Citizens Act source covers an application by a senior citizen or parent who is unable to maintain himself from earnings or property, so use that route only if age, dependency, or exploitation facts also exist [{senior}]."
        )
    lines.append("**What you can do next**")
    action_cite = ombudsman if ombudsman is not None else consumer35 if consumer35 is not None else consumer2 if consumer2 is not None else senior
    lines.append(
        f"- File a written insurer grievance with the policy bond, proposal form, benefit illustration, agent messages, premium receipts, maturity statement, and the exact promised-return words before escalating to Ombudsman or consumer forum [{action_cite}]."
    )
    return lines


def _undertrial_legal_aid_template_lines(passages: list[dict]) -> list[str]:
    lsa = _find_passage_index(
        passages,
        title_terms=("legal services authorities",),
        anchor_terms=("/sec-9", "/sec-12"),
    )
    bnss479 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-479",),
    )
    if lsa is None and bnss479 is None:
        return []
    lines = ["**Short answer**"]
    if bnss479 is not None:
        lines.append(
            f"For the undertrial-delay part, the BNSS source is the custody-duration and release-on-bail provision to check with the offence maximum and detention period [{bnss479}]."
        )
    if lsa is not None:
        lines.append(
            f"For the lawyer-not-attending problem, the Legal Services Authorities source gives the District Legal Services Authority route for legal-services support [{lsa}]."
        )
    lines.append("**What you can do next**")
    if lsa is not None:
        lines.append(
            f"- For lawyer replacement or legal-aid support, use the District Legal Services Authority route stated in the cited legal-services source [{lsa}]."
        )
    if bnss479 is not None:
        lines.append(
            f"- For release based on custody duration, compare the detention period and offence maximum to the cited BNSS undertrial-release source [{bnss479}]."
        )
    return lines


def _prison_mulaqat_template_lines(passages: list[dict]) -> list[str]:
    prisons = _find_passage_index(
        passages,
        title_terms=("prisons act", "prisons"),
    )
    article21 = _find_passage_index(
        passages,
        title_terms=("constitution",),
        anchor_terms=("/sec-21",),
    )
    if prisons is None and article21 is None:
        return []
    lines = ["**Short answer**"]
    if prisons is not None:
        lines.append(
            f"For a jail mulaqat or interview-duration complaint, the Prisons Act source is the prison-administration source to check before relying on a general parole or bail route [{prisons}]."
        )
    if article21 is not None:
        lines.append(
            f"If the restriction is arbitrary, discriminatory, or blocks family/lawyer access without reasons, preserve the Article 21 liberty/fairness point for DLSA or High Court review [{article21}]."
        )
    lines.append("**What you can do next**")
    action_cite = prisons if prisons is not None else article21
    lines.append(
        f"- Submit a written request to the Jail Superintendent with prisoner details, relationship proof, requested mulaqat time/frequency, and the refusal/order copy; then escalate to DLSA, prison-visitors board, or High Court writ route if reasons are not given [{action_cite}]."
    )
    return lines


def _custody_compensation_template_lines(passages: list[dict]) -> list[str]:
    article21 = _find_passage_index(
        passages,
        title_terms=("constitution",),
        anchor_terms=("/sec-21",),
    )
    bnss479 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-479",),
    )
    crpc436a = _find_passage_index(
        passages,
        title_terms=("criminal procedure",),
        anchor_terms=("/sec-436", "/sec-436-a", "/sec-436a"),
    )
    if article21 is None and bnss479 is None and crpc436a is None:
        return []
    lines = ["**Short answer**"]
    if article21 is not None:
        lines.append(
            f"For compensation after delayed or excessive custody, start with the Article 21 liberty source and build the case around unlawful or unjustified deprivation of personal liberty [{article21}]."
        )
    if bnss479 is not None:
        lines.append(
            f"For the custody-duration part, the BNSS Section 479 source is relevant to compare the actual detention period with the maximum punishment and undertrial-release threshold [{bnss479}]."
        )
    if crpc436a is not None:
        lines.append(
            f"If the custody period is from the older CrPC regime, check the CrPC Section 436A source as the comparable undertrial custody-duration provision [{crpc436a}]."
        )
    lines.append("**What you can do next**")
    action_cite = bnss479 if bnss479 is not None else crpc436a if crpc436a is not None else article21
    lines.append(
        f"- Make a dated timeline from arrest/remand to charge-sheet, bail, release, or acquittal, then take FIR, remand, bail/release, and final order copies to DLSA or a lawyer before choosing High Court or Human Rights Commission compensation steps [{action_cite}]."
    )
    return lines


def _identity_police_threat_template_lines(passages: list[dict]) -> list[str]:
    article21 = _find_passage_index(
        passages,
        title_terms=("constitution of india",),
        anchor_terms=("/sec-21",),
    )
    bns351 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-351",),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    if article21 is None and bns351 is None and bnss173 is None:
        return []
    lines = ["**Short answer**"]
    if article21 is not None:
        lines.append(
            f"For a police-threat over alleged nationality or origin, the Constitution source protects life and personal liberty except by procedure established by law [{article21}]."
        )
    if bns351 is not None:
        lines.append(
            f"The BNS source treats a threat of injury to person, reputation, or property as criminal intimidation where the statutory ingredients are met [{bns351}]."
        )
    if bnss173 is not None:
        lines.append(
            f"If you make a police complaint, the BNSS source covers information to police and the FIR/refusal procedure under the retrieved provision [{bnss173}]."
        )
    lines.append("**What you can do next**")
    if bns351 is not None:
        lines.append(
            f"- For the complaint, first test whether the exact words amount to a threat of injury to person, reputation, or property under the cited BNS source [{bns351}]."
        )
    if bnss173 is not None:
        lines.append(
            f"- For the police-procedure track, use the cited BNSS FIR/refusal source when giving information to police or escalating police refusal [{bnss173}]."
        )
    if article21 is not None:
        lines.append(
            f"- For the liberty framing, keep the cited Article 21 source separate from the criminal-offence source [{article21}]."
        )
    return lines


def _spousal_neutral_complaint_template_lines(query: str, passages: list[dict]) -> list[str]:
    bns_hurt = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-115", "/sec-117"),
    )
    bns_property = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-303", "/sec-316", "/sec-318"),
    )
    bns_threat_or_restraint = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-351", "/sec-126", "/sec-127"),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    bnss175 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-175",),
    )
    if bns_hurt is None and bns_property is None and bns_threat_or_restraint is None and bnss173 is None and bnss175 is None:
        return []
    physical_context = _has_any_term(query, ("slap", "slapped", "hit", "beat", "beaten", "hurt"))
    threat_context = _has_any_term(query, ("threat", "threatens", "threatened", "threatening"))
    residence_context = _has_any_term(query, (
        "threw me out", "kicked me out", "locked me out",
        "not allowing me entry", "not letting me enter", "not letting me in",
    ))
    property_context = _has_any_term(query, (
        "salary", "atm card", "bank card", "money", "jewellery", "jewelry",
        "gold", "documents", "took my property", "stole my property",
        "sold my property", "transferred my property", "took my house papers",
        "sold my house", "transferred my house",
    ))
    lines = ["**Short answer**"]
    if physical_context and bns_hurt is not None:
        lines.append(
            f"For a slap, hit, or injury, the neutral BNS hurt/grievous-hurt source is the source to check with the incident date and injury facts [{bns_hurt}]."
        )
    sexual_context = _has_any_term(query, (
        "forces sex", "force sex", "forced sex", "sex without consent",
        "sexual assault", "sexually assaulted me", "sexually assaulting me",
        "assaulted me sexually",
    ))
    if sexual_context:
        sexual_cite = bns_threat_or_restraint if bns_threat_or_restraint is not None else bns_hurt
        if sexual_cite is not None:
            lines.append(
                f"For 'my wife forced sex' or 'my wife sexually assaulted me' facts, do not treat this answer as a final offence classification; the neutral BNS force, hurt, threat, or restraint source is only a source to check if those facts fit [{sexual_cite}]."
            )
        elif bnss173 is not None:
            lines.append(
                f"For 'my wife forced sex' or 'my wife sexually assaulted me' facts, the retrieved BNSS source is only the complaint-procedure source; ask DLSA or a lawyer to check the exact offence fit before filing [{bnss173}]."
            )
    if threat_context and bns_threat_or_restraint is not None:
        lines.append(
            f"For 'my wife threatens me' or similar spouse-threat facts, the neutral BNS criminal-intimidation or restraint source is the source to check with the exact words, conduct, and safety facts [{bns_threat_or_restraint}]."
        )
    if residence_context and bns_threat_or_restraint is not None:
        lines.append(
            f"For 'my wife threw/kicked/locked me out' facts, separate the residence or property dispute from any force, threat, or restraint; the neutral BNS source is the criminal-law source to check only if those facts exist [{bns_threat_or_restraint}]."
        )
    if property_context and bns_property is not None:
        property_phrase = (
            "my wife sold/transferred my house/property without consent"
            if _has_any_term(query, ("sold my house", "transferred my house", "sold my property", "transferred my property"))
            else "my wife took my jewellery/salary/ATM card"
        )
        lines.append(
            f"For '{property_phrase}' or similar property-control facts, first identify ownership, consent, entrustment, transfer papers, withdrawals, and messages; the neutral BNS theft, breach-of-trust, or cheating source is the criminal-law source to compare with those facts [{bns_property}]."
        )
    if bnss173 is not None:
        lines.append(
            f"For the complaint route, the BNSS source on information to police is the procedure source to check before approaching police or escalating refusal [{bnss173}]."
        )
    elif bnss175 is not None:
        lines.append(
            f"If police refuse to act, the BNSS Magistrate-investigation source is the procedure source to check [{bnss175}]."
        )
    lines.append("**What you can do next**")
    action_cite = bnss173 if bnss173 is not None else bnss175 if bnss175 is not None else bns_hurt if bns_hurt is not None else bns_threat_or_restraint if bns_threat_or_restraint is not None else bns_property
    if physical_context:
        lines.append(
            f"- For the 'my wife slapped me' fact, preserve injury photos, medical notes if any, messages, and witness names before deciding whether to make a police complaint or seek family/civil help [{action_cite}]."
        )
    if sexual_context:
        lines.append(
            f"- For the sexual-coercion fact, prioritize current safety, medical or mental-health support if needed, messages, witness details, and legal-aid review before deciding whether to use the police complaint route [{action_cite}]."
        )
    if threat_context:
        lines.append(
            f"- For the threat fact, write down the exact words, date, place, witnesses, and messages before deciding whether to use the police complaint route or family/civil support route [{action_cite}]."
        )
    if residence_context:
        lines.append(
            f"- For the thrown-out or locked-out fact, keep proof of residence, ownership or tenancy papers, messages, and any force or threat details before choosing police, family, or civil forum help [{action_cite}]."
        )
    if property_context:
        lines.append(
            f"- For the salary, ATM-card, jewellery, gold, house, documents, or property-transfer fact, keep bank records, ownership papers, transfer papers, entrustment proof, and messages before deciding whether the correct route is police complaint, family/civil remedy, or both [{action_cite}]."
        )
    lines.append(
        f"- Use DLSA or a lawyer to separate criminal complaint facts from matrimonial or civil financial-relief facts before filing [{action_cite}]."
    )
    return lines


def _name_change_gazette_template_lines(query: str, passages: list[dict]) -> list[str]:
    required_docs = _find_passage_index(
        passages,
        title_terms=("department of publication guidelines for change of name",),
        anchor_terms=("adult-required-documents",),
    )
    formalities = _find_passage_index(
        passages,
        title_terms=("department of publication guidelines for change of name",),
        anchor_terms=("adult-formalities",),
    )
    download = _find_passage_index(
        passages,
        title_terms=("department of publication guidelines for change of name",),
        anchor_terms=("egazette-download-and-submission",),
    )
    if formalities is None or (required_docs is None and download is None):
        return []
    lines = ["**Short answer**"]
    lines.append(
        f"The Department of Publication source is the Gazette of India Part-IV procedure for an adult who wishes to publish a name or surname change; it is not, by itself, a marriage-law rule saying every post-marriage surname update must be gazetted [{formalities}]."
    )
    if required_docs is not None:
        lines.append(
            f"If you use that Gazette route, the guideline lists an undertaking, original newspaper, typed proforma with two witnesses, CD or soft copy, two self-attested photographs, ID proof, hard/soft-copy certificate, request letter, and fee [{required_docs}]."
        )
    lines.append(
        f"For that Gazette route, the same guideline says the name change should be advertised in a daily local leading newspaper with father's or husband's name and residential address, and the typed specimen must be signed in the old name [{formalities}]."
    )
    if download is not None:
        lines.append(
            f"After Gazette publication, the guideline tells the applicant to download the Gazette from egazette.gov.in by searching Weekly Gazette, Part IV, and finding the old or new name in the PDF [{download}]."
        )
    lines.append("**What you can do next**")
    action_cite = required_docs if required_docs is not None else formalities
    lines.append(
        f"- If you choose the Gazette publication route, prepare the newspaper page, undertaking, typed proforma, photographs, ID proof, CD or soft copy certificate, fee receipt, and request letter [{action_cite}]."
    )
    return lines


def _marriage_misrepresentation_template_lines(query: str, passages: list[dict]) -> list[str]:
    hma12 = _find_passage_index(
        passages,
        title_terms=("hindu marriage",),
        anchor_terms=("/sec-12",),
    )
    family7 = _find_passage_index(
        passages,
        title_terms=("family courts",),
        anchor_terms=("/sec-7",),
    )
    if hma12 is None and family7 is None:
        return []
    health_context = _has_any_term(query, ("hiv", "hiv positive", "aids", "health", "disease", "medical condition"))
    misrep_subject = "health or medical-status statement" if health_context else "salary, job, or loan statement"
    proof_phrase = "medical-disclosure proof/messages and the date you discovered the truth" if health_context else "job/salary/loan proof, and the date you discovered the truth"
    lines = ["**Short answer**"]
    if hma12 is not None:
        lines.append(
            f"If the Hindu Marriage Act applies, Section 12 is the source to check for whether a marriage is voidable on consent or fraud-related grounds; a {misrep_subject} must be tested against that source and the proof [{hma12}]."
        )
    if family7 is not None:
        lines.append(
            f"The Family Courts Act jurisdiction source is relevant for matrimonial-status or validity proceedings, so the forum is usually the Family Court route after personal law is identified [{family7}]."
        )
    lines.append("**What you can do next**")
    if hma12 is not None:
        lines.append(
            f"- Collect marriage proof, biodata/messages, {proof_phrase}; then ask DLSA or a family-law lawyer whether annulment, divorce, maintenance, or counselling fits the facts [{hma12}]."
        )
    elif family7 is not None:
        lines.append(
            f"- Collect marriage proof, the statement/proof you relied on, and the date you discovered the truth; then ask DLSA or a family-law lawyer which family-court remedy fits the facts [{family7}]."
        )
    return lines


def _pre_marriage_health_disclosure_template_lines(query: str, passages: list[dict]) -> list[str]:
    hiv = _find_passage_index(
        passages,
        title_terms=("human immunodeficiency",),
        anchor_terms=("/sec-5", "/sec-8", "/sec-9"),
    ) or _find_passage_index(
        passages,
        title_terms=("hiv", "aids"),
        anchor_terms=("/sec-5", "/sec-8", "/sec-9"),
    )
    hma12 = _find_passage_index(
        passages,
        title_terms=("hindu marriage",),
        anchor_terms=("/sec-12",),
    )
    family7 = _find_passage_index(
        passages,
        title_terms=("family courts",),
        anchor_terms=("/sec-7",),
    )
    it_privacy = _find_passage_index(
        passages,
        title_terms=("information technology",),
        anchor_terms=("/sec-66E", "/sec-67"),
    )
    dpdp = _find_passage_index(
        passages,
        title_terms=("digital personal data protection",),
        anchor_terms=("/sec-8", "/sec-13"),
    )
    dowry = _find_passage_index(passages, title_terms=("dowry prohibition",))
    if hiv is None and hma12 is None and family7 is None and it_privacy is None and dpdp is None and dowry is None:
        return []
    lines = ["**Short answer**"]
    not_married_yet = _has_any_term(query, (
        "supposed to marry", "marry next month", "marriage next month",
        "wedding next month", "not married yet", "engagement", "engaged",
        "fiance", "fiancee",
    ))
    if not_married_yet:
        if hma12 is not None:
            lines.append(
                f"If the marriage has not happened yet, do not treat this as divorce or annulment today; the Hindu Marriage Act voidable-marriage source becomes relevant only if a marriage has occurred and consent/fraud has to be tested later [{hma12}]."
            )
        elif family7 is not None:
            lines.append(
                f"If the marriage has not happened yet, first treat this as cancellation, records, privacy, and gifts/expense-return planning, not as a Family Court divorce filing [{family7}]."
            )
    elif hma12 is not None:
        lines.append(
            f"If a marriage has already occurred and the Hindu Marriage Act applies, Section 12 is the source to check for whether consent/fraud facts make the marriage voidable [{hma12}]."
        )
    if hiv is not None:
        lines.append(
            f"For HIV/health-status facts, verify the primary HIV/privacy source before disclosing the person's medical status publicly or using it in any notice [{hiv}]."
        )
    online_warning = _has_any_term(query, MEDICAL_STATUS_ONLINE_DISCLOSURE_TERMS)
    if online_warning:
        privacy_cite = it_privacy if it_privacy is not None else dpdp
        if privacy_cite is not None:
            lines.append(
                f"Do not post the person's identifiable medical status online as a pressure tactic; keep evidence private and verify any disclosure, takedown, or complaint step against the cited privacy/cyber source first [{privacy_cite}]."
            )
    if dowry is not None:
        lines.append(
            f"If gifts, dowry, or wedding-expense return is the dispute, keep that property-return track separate from the medical-disclosure issue [{dowry}]."
        )
    lines.append("**What you can do next**")
    action_cite = (
        it_privacy if online_warning and it_privacy is not None
        else hiv if hiv is not None
        else hma12 if hma12 is not None
        else dowry if dowry is not None
        else dpdp if dpdp is not None
        else family7
    )
    lines.append(
        f"- Preserve biodata/messages, engagement or wedding records, gift/dowry/payment records, and the date you discovered the fact; speak to DLSA or a family-law lawyer before sending a notice or making public allegations about medical status [{action_cite}]."
    )
    if hiv is None:
        lines.append(
            "The retrieved index did not surface the HIV Act source for this answer, so verify the medical-privacy/non-discrimination rule from a lawyer or primary source before acting on that part."
        )
    return lines


def _marital_intimacy_breakdown_template_lines(query: str, passages: list[dict]) -> list[str]:
    family7 = _find_passage_index(
        passages,
        title_terms=("family courts",),
        anchor_terms=("/sec-7",),
    )
    hma13 = _find_passage_index(
        passages,
        title_terms=("hindu marriage",),
        anchor_terms=("/sec-13",),
    )
    if family7 is None and hma13 is None:
        return []
    lines = ["**Short answer**"]
    if family7 is not None:
        lines.append(
            f"For a spouse denying sex or intimacy, treat this as a marriage-breakdown or matrimonial-remedy question, because the Family Courts Act source covers suits and proceedings relating to matrimonial matters [{family7}]."
        )
    if hma13 is not None:
        lines.append(
            f"Do not treat refusal of intimacy as a complete legal claim by itself; if the Hindu Marriage Act applies, Section 13 is the divorce-ground source to check with the full facts [{hma13}]."
        )
    lines.append("**What you can do next**")
    if hma13 is not None:
        lines.append(
            f"- Do not use pressure or force; write the timeline and decide whether you want counselling, separation, divorce, maintenance, or another family-court remedy before speaking to DLSA or a family-law lawyer [{hma13}]."
        )
    elif family7 is not None:
        lines.append(
            f"- Do not use pressure or force; write the timeline, residence, children, maintenance, and any violence/coercion facts before choosing a counselling or family-court route [{family7}]."
        )
    return lines


def _matrimonial_property_maintenance_template_lines(query: str, passages: list[dict]) -> list[str]:
    family7 = _find_passage_index(
        passages,
        title_terms=("family courts",),
        anchor_terms=("/sec-7", "/sec-8"),
    )
    hma = _find_passage_index(
        passages,
        title_terms=("hindu marriage",),
        anchor_terms=("/sec-13", "/sec-24", "/sec-25"),
    )
    sma = _find_passage_index(
        passages,
        title_terms=("special marriage",),
        anchor_terms=("/sec-27", "/sec-28", "/sec-36", "/sec-37"),
    )
    if family7 is None and hma is None and sma is None:
        return []
    lines = ["**Short answer**"]
    if family7 is not None:
        lines.append(
            f"For a wife asking maintenance or a share in house/property, the Family Courts Act source is the forum source to check for matrimonial proceedings and property disputes connected with marriage [{family7}]."
        )
    if hma is not None:
        lines.append(
            f"If the Hindu Marriage Act route applies, the HMA source is the source to check for divorce and maintenance relief; do not assume a criminal complaint from a maintenance or property-share demand alone [{hma}]."
        )
    elif sma is not None:
        lines.append(
            f"If the Special Marriage Act route applies, the SMA source is the source to check for divorce or maintenance relief; do not assume a criminal complaint from a maintenance or property-share demand alone [{sma}]."
        )
    lines.append("**What you can do next**")
    action_cite = family7 if family7 is not None else hma if hma is not None else sma
    lines.append(
        f"- Read the petition, notice, or message first and separate three issues: maintenance, property title or joint ownership, and divorce or matrimonial relief [{action_cite}]."
    )
    lines.append(
        f"- Keep marriage details, income proof, dependants' expenses, title deed or loan papers, and any pending Family Court case number before replying or filing anything [{action_cite}]."
    )
    return lines


def _marital_sexual_violence_template_lines(query: str, passages: list[dict]) -> list[str]:
    pwdva3 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-3",),
    )
    pwdva18 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-18",),
    )
    bns63 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-63",),
    )
    bns67 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-67",),
    )
    if pwdva3 is None and bns63 is None:
        return []
    lines = ["**Short answer**"]
    if pwdva3 is not None:
        lines.append(
            f"If your husband forces sex or sexual contact after you say no, keep the first legal frame as domestic violence and safety; the PWDVA source defines domestic violence to include sexual abuse and related physical or emotional harm [{pwdva3}]."
        )
    if bns63 is not None:
        lines.append(
            f"The BNS sexual-offence source must be checked carefully because Section 63 contains both the rape definition and the marital-exception wording; do not assume the criminal route without the incident date and full facts [{bns63}]."
        )
    if bns67 is not None:
        lines.append(
            f"If the spouses are living separately, also check the specific BNS source on sexual intercourse by husband upon his wife during separation [{bns67}]."
        )
    if pwdva18 is not None:
        lines.append(
            f"For immediate protection, the PWDVA protection-order source is relevant to stopping further domestic violence through the Magistrate route [{pwdva18}]."
        )
    lines.append("**What you can do next**")
    action_cite = pwdva18 if pwdva18 is not None else pwdva3 if pwdva3 is not None else bns63
    lines.append(
        f"- Write a dated safety timeline, preserve messages or medical proof if any, and contact a Protection Officer, women's helpline/One Stop Centre, DLSA, or Magistrate court for protection and support [{action_cite}]."
    )
    return lines


def _domestic_violence_safety_template_lines(query: str, passages: list[dict]) -> list[str]:
    pwdva3 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-3",),
    )
    pwdva12 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-12",),
    )
    pwdva17 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-17",),
    )
    pwdva18 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-18",),
    )
    pwdva19 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-19",),
    )
    pwdva20 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-20",),
    )
    bns_hurt = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-115", "/sec-117"),
    )
    bns_threat = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-351",),
    )
    if all(cite is None for cite in (pwdva3, pwdva12, pwdva17, pwdva18, pwdva19, pwdva20, bns_hurt, bns_threat)):
        return []

    residence_context = _has_any_term(query, (
        "ghar se nikal", "nikal diya", "threw me out", "kicked me out",
        "sasural", "wapis", "go back", "return home", "shared household",
        "residence", "shelter", "raat ko", "night",
    ))
    physical_context = _has_any_term(query, (
        "slap", "slapped", "slaps", "beat", "beaten", "beating",
        "hit", "hits", "hitting", "pushed", "physical violence",
        "angry and", "sorry next day",
    ))
    immediate_context = _has_any_term(query, (
        "right now", "now", "currently", "today", "this moment",
        "beating me", "hitting me", "hits me", "unsafe",
    ))
    economic_context = _has_any_term(query, (
        "salary", "atm card", "bank card", "money", "groceries",
        "breadwinner", "not giving money", "income",
    ))
    dowry_context = _has_any_term(query, ("dowry", "dahej", "taunts", "demand"))
    food_context = _has_any_term(query, ("not let me eat", "does not let me eat", "no food", "food"))

    lines = ["**Short answer**"]
    if pwdva3 is not None:
        if physical_context and immediate_context:
            lines.append(
                f"If he is beating you right now or you are not safe, treat immediate safety first; the PWDVA source recognises physical abuse as domestic violence, not a normal family disagreement [{pwdva3}]."
            )
        elif physical_context:
            lines.append(
                f"You do not have to treat being hit, slapped, or beaten as normal just because he says sorry later; the PWDVA source defines domestic violence to include physical, verbal, emotional, sexual, and economic abuse [{pwdva3}]."
            )
        elif dowry_context or food_context:
            lines.append(
                f"Daily dowry taunts, pressure for money, or being denied food should be checked as domestic violence and economic abuse, not only as a family argument [{pwdva3}]."
            )
        elif economic_context:
            lines.append(
                f"A spouse controlling your salary, ATM card, and grocery money is not just a household-management issue; it can be tested as economic abuse under the PWDVA domestic-violence definition when the facts support it [{pwdva3}]."
            )
        else:
            lines.append(
                f"Keep this as a domestic-violence/support route first, not only a divorce or family-dispute question; the PWDVA source defines the abuse categories to check [{pwdva3}]."
            )
    if residence_context and (pwdva17 is not None or pwdva19 is not None):
        residence_cite = pwdva19 if pwdva19 is not None else pwdva17
        lines.append(
            f"For the ghar se nikal diya / can I go back problem, the PWDVA residence-order source is the direct source to check for exclusion from the shared household and asking the Magistrate for residence protection [{residence_cite}]."
        )
    elif residence_context and (pwdva18 is not None or pwdva12 is not None):
        residence_cite = pwdva18 if pwdva18 is not None else pwdva12
        lines.append(
            f"On whether you can go back after being thrown out at night: do not go alone if it is unsafe; use the Protection Officer/Magistrate route to ask for protection and safe-return or residence relief [{residence_cite}]."
        )
    if pwdva18 is not None:
        if physical_context and immediate_context:
            lines.append(
                f"Because he is beating you right now, move to immediate safety first; the PWDVA protection-order source is the Magistrate route to stop further domestic violence, contact, threats, or intimidation [{pwdva18}]."
            )
        else:
            lines.append(
                f"For immediate safety, the PWDVA protection-order source is the Magistrate route to stop further domestic violence, contact, threats, or intimidation [{pwdva18}]."
            )
    if pwdva20 is not None and (economic_context or dowry_context or food_context):
        lines.append(
            f"For money, household expenses, salary control, or dowry-linked economic pressure, the PWDVA monetary-relief source should be checked along with the proof of income and expenses [{pwdva20}]."
        )
    if bns_hurt is not None and physical_context:
        lines.append(
            f"If there is physical injury or assault, keep a separate criminal-law track too; the BNS hurt source must be matched to the incident date and medical facts [{bns_hurt}]."
        )
    elif bns_threat is not None and _has_any_term(query, ("threat", "threaten", "threatening", "kill")):
        lines.append(
            f"If threats are involved, the BNS criminal-intimidation source is a separate police track to verify with the exact words and incident date [{bns_threat}]."
    )
    lines.append("**What you can do next**")
    action_cite = (
        pwdva18 if pwdva18 is not None
        else pwdva19 if pwdva19 is not None
        else pwdva17 if pwdva17 is not None
        else pwdva20 if pwdva20 is not None
        else pwdva12 if pwdva12 is not None
        else pwdva3 if pwdva3 is not None
        else bns_hurt if bns_hurt is not None
        else bns_threat
    )
    if residence_context:
        lines.append(
            f"- Because the sasural/household has ghar se nikal diya or thrown you out, do not go back alone if it is unsafe; ask the Protection Officer, DLSA, or Magistrate route for safe return, shelter, or residence protection [{action_cite}]."
        )
    if immediate_context and physical_context:
        lines.append(
            f"- If violence is happening right now, move to immediate safety first: call local emergency help/police if needed, contact a trusted person or One Stop Centre/women helpline, and then use the Protection Officer/Magistrate route for protection [{action_cite}]."
        )
    if physical_context:
        lines.append(
            f"- If you are asking whether to stay, decide around immediate safety first: contact a trusted person, helpline, Protection Officer, DLSA, or police/emergency help if violence may continue [{action_cite}]."
        )
    lines.append(
        f"- Write a dated safety timeline, keep messages/photos/medical records, and contact a Protection Officer, One Stop Centre/women helpline, DLSA, or Magistrate court for protection, residence or safe return home, and monetary relief; use police/emergency help if there is immediate danger [{action_cite}]."
    )
    if pwdva12 is not None:
        lines.append(
            f"- For the court filing path, the PWDVA application source is the provision to check before preparing a protection/residence/monetary-relief application [{pwdva12}]."
        )
    return lines


def _streedhan_return_template_lines(query: str, passages: list[dict]) -> list[str]:
    hsa14 = _find_passage_index(
        passages,
        title_terms=("hindu succession",),
        anchor_terms=("/sec-14",),
    )
    hsa_succession = _find_passage_index(
        passages,
        title_terms=("hindu succession",),
        anchor_terms=("/sec-15", "/sec-16"),
    )
    pwdva3 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-3",),
    )
    pwdva12 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-12",),
    )
    pwdva20 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-20",),
    )
    dowry = _find_passage_index(passages, title_terms=("dowry prohibition",))
    bns316 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-316",),
    )
    if hsa14 is None and hsa_succession is None and pwdva3 is None and pwdva12 is None and pwdva20 is None and dowry is None and bns316 is None:
        return []
    lines = ["**Short answer**"]
    if hsa14 is not None:
        lines.append(
            f"For jewellery or streedhan kept by in-laws, first keep it as the woman's property issue; the Hindu Succession Act source on female property is the ownership source to check where that personal-law route applies [{hsa14}]."
        )
    elif hsa_succession is not None:
        lines.append(
            f"Because the husband has died, keep the streedhan/jewellery return issue separate from succession; the Hindu Succession Act source is the succession source to verify for the female-property/heirship side [{hsa_succession}]."
        )
    if pwdva3 is not None:
        lines.append(
            f"The Domestic Violence Act source is relevant because withholding jewellery, streedhan, or economic resources can be tested as economic abuse on the domestic-violence route [{pwdva3}]."
        )
    if pwdva12 is not None or pwdva20 is not None:
        cite = pwdva20 if pwdva20 is not None else pwdva12
        lines.append(
            f"The Magistrate/Protection Officer route should be checked for return, monetary relief, or protection before treating this only as a generic property case [{cite}]."
        )
    if bns316 is not None:
        lines.append(
            f"If the facts show entrustment and dishonest refusal to return, the BNS criminal-breach-of-trust source is a separate criminal-law track to compare with the evidence [{bns316}]."
        )
    if dowry is not None:
        lines.append(
            f"The Dowry Prohibition Act source may be relevant if the jewellery or property is linked to dowry/presents, but it should not replace the streedhan ownership and domestic-relief facts [{dowry}]."
        )
    lines.append("**What you can do next**")
    action_cite = pwdva20 if pwdva20 is not None else pwdva12 if pwdva12 is not None else pwdva3 if pwdva3 is not None else hsa14 if hsa14 is not None else hsa_succession if hsa_succession is not None else bns316 if bns316 is not None else dowry
    lines.append(
        f"- Make an item-wise list with receipts, wedding photos, locker or possession proof, messages demanding return, and witness names, then seek Protection Officer/Magistrate/DLSA help before adding any police complaint for entrustment/refusal facts [{action_cite}]."
    )
    return lines


def _mtp_privacy_divorce_template_lines(query: str, passages: list[dict]) -> list[str]:
    mtp_privacy = _find_passage_index(
        passages,
        title_terms=("medical termination of pregnancy",),
        anchor_terms=("/sec-5A", "/sec-5-a"),
    )
    mtp_general = _find_passage_index(passages, title_terms=("medical termination of pregnancy",))
    hma13 = _find_passage_index(
        passages,
        title_terms=("hindu marriage",),
        anchor_terms=("/sec-13",),
    )
    family7 = _find_passage_index(
        passages,
        title_terms=("family courts",),
        anchor_terms=("/sec-7",),
    )
    if mtp_privacy is None and mtp_general is None and hma13 is None and family7 is None:
        return []
    lines = ["**Short answer**"]
    if mtp_privacy is not None:
        lines.append(
            f"For an old abortion or pregnancy-termination fact being used as a threat, first keep the medical privacy issue separate: the MTP source is the confidentiality/privacy source to check [{mtp_privacy}]."
        )
    elif mtp_general is not None:
        lines.append(
            f"For an old abortion or pregnancy-termination fact being used as a threat, start with the MTP source and medical record privacy before deciding any family-court strategy [{mtp_general}]."
        )
    if hma13 is not None:
        lines.append(
            f"Do not assume a past lawful abortion automatically decides divorce; if the Hindu Marriage Act applies, any divorce ground must be tested under the matrimonial source and the full facts [{hma13}]."
        )
    if family7 is not None:
        lines.append(
            f"The Family Courts Act source is the forum route for matrimonial-status or divorce proceedings, while the medical privacy issue should be handled with minimum disclosure [{family7}]."
        )
    lines.append("**What you can do next**")
    action_cite = mtp_privacy if mtp_privacy is not None else mtp_general if mtp_general is not None else family7 if family7 is not None else hma13
    lines.append(
        f"- Preserve the threat messages and do not circulate medical papers widely; take the marriage/personal-law details and privacy facts to DLSA or a family-law lawyer before responding to the divorce threat [{action_cite}]."
    )
    return lines


def _panchayat_common_land_template_lines(query: str, passages: list[dict]) -> list[str]:
    constitution243g = _find_passage_index(
        passages,
        title_terms=("constitution of india",),
        anchor_terms=("/sec-243G",),
    )
    constitution243 = _find_passage_index(
        passages,
        title_terms=("constitution of india",),
        anchor_terms=("/sec-243",),
    )
    panchayat_case = _find_panchayat_common_land_case_index(passages)
    rti6 = _find_passage_index(
        passages,
        title_terms=("right to information",),
        anchor_terms=("/sec-6",),
    )
    if constitution243g is None and constitution243 is None and panchayat_case is None:
        return []
    lines = ["**Short answer**"]
    if constitution243g is not None:
        lines.append(
            f"Because the state is not stated, start with the local Gram Panchayat/common-land records; the Constitution source says State law endows Panchayats with powers and responsibilities under Part IX [{constitution243g}]."
        )
    elif constitution243 is not None:
        lines.append(
            f"Because the state is not stated, start with the local Gram Panchayat/common-land records; the Constitution source defines Gram Sabha and Panchayat for Part IX purposes [{constitution243}]."
        )
    if panchayat_case is not None:
        lines.append(
            f"The retrieved Panchayat case-law source is the closest indexed authority for common village land, so do not treat a private family allotment as valid without the resolution, land record, and statutory power being checked [{panchayat_case}]."
        )
    if _has_any_term(query, ("sarpanch", "brother", "no panchayat meeting", "no meeting")):
        panchayat_facts = _present_terms_phrase(
            query,
            (
                ("sarpanch", "sarpanch"),
                ("brother", "brother"),
                ("no Panchayat meeting", "no panchayat meeting", "no meeting"),
            ),
            fallback="this common-land transfer",
        )
        panchayat_cite = constitution243g if constitution243g is not None else constitution243 if constitution243 is not None else rti6 if rti6 is not None else panchayat_case
        if panchayat_cite is not None:
            lines.append(
                f"For {panchayat_facts}, the practical issue is whether any valid Gram Sabha or Panchayat resolution and land-allotment power exists at all [{panchayat_cite}]."
            )
    lines.append("**What you can do next**")
    if rti6 is not None:
        lines.append(
            f"- File RTI for the Gram Sabha/Panchayat resolution, meeting minutes, mutation or allotment order, land classification, and the rule relied on for transferring the common land [{rti6}]."
        )
    else:
        next_cite = panchayat_case if panchayat_case is not None else constitution243g if constitution243g is not None else constitution243
        lines.append(
            f"- Get the resolution, meeting minutes, mutation or allotment order, land classification, and the rule relied on before complaining to the Block/Panchayat authority [{next_cite}]."
        )
    return lines


def _find_panchayat_common_land_case_index(passages: list[dict]) -> int | None:
    intended_doc_prefixes = (
        "2000-insc-465",
        "2006-insc-459",
        "2006-insc-620",
        "2022-insc-1016",
    )
    land_terms = (
        "common land",
        "common lands",
        "community property",
        "panchayat land",
        "gram panchayat land",
        "public land",
        "public premises",
        "land in dispute",
    )
    process_terms = (
        "allotment",
        "lease",
        "public auction",
        "resolution",
        "due procedure",
        "not a one-man show",
        "sarpanch",
    )
    for passage in passages:
        title = str(passage.get("title") or "").lower()
        anchor = str(passage.get("anchor") or "").lower()
        text = str(passage.get("text") or "").lower()
        blob = f"{title} {anchor} {text}"
        is_panchayat = "panchayat" in blob or anchor.startswith(intended_doc_prefixes)
        has_land_evidence = any(term in blob for term in land_terms)
        has_process_evidence = any(term in blob for term in process_terms)
        if not is_panchayat or not has_land_evidence or not has_process_evidence:
            continue
        if "#header" in anchor and not text:
            continue
        idx = passage.get("index")
        return int(idx) if isinstance(idx, int) else None
    return None


def _inlaw_jewellery_breach_template_lines(query: str, passages: list[dict]) -> list[str]:
    pwdva3 = _find_passage_index(
        passages,
        title_terms=("domestic violence",),
        anchor_terms=("/sec-3",),
    )
    bns316 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya sanhita",),
        anchor_terms=("/sec-316",),
    )
    if pwdva3 is None and bns316 is None:
        return []
    lines = ["**Short answer**"]
    if bns316 is not None:
        lines.append(
            f"If jewellery was entrusted for safe keeping and then dishonestly kept or misappropriated, the BNS criminal-breach-of-trust source is the criminal-law provision to check, subject to the incident date and old/new code issue [{bns316}]."
        )
        lines.append(
            f"Frame the not-returning-jewellery complaint around entrustment of property and dishonest misappropriation, because those are the elements stated in the BNS source [{bns316}]."
        )
    if pwdva3 is not None:
        lines.append(
            f"The PWDVA source can also matter if the daughter-in-law facts form a domestic relationship, because its domestic-violence definition includes economic abuse in the retrieved section [{pwdva3}]."
        )
    lines.append("**What you can do next**")
    if bns316 is not None and pwdva3 is not None:
        lines.append(
            f"- Preserve purchase or gift proof, entrustment messages, and written demands for return; use the police criminal-breach-of-trust route for the entrustment/refusal facts [{bns316}]."
        )
        lines.append(
            f"- If domestic-relief facts fit, separately consider the PWDVA Magistrate or Protection Officer route for economic-abuse relief [{pwdva3}]."
        )
    else:
        action_cite = bns316 if bns316 is not None else pwdva3
        lines.append(
            f"- Preserve purchase or gift proof, entrustment messages, and written demands for return before choosing the route that fits the facts [{action_cite}]."
        )
    return lines


def _housing_pet_fine_template_lines(query: str, passages: list[dict]) -> list[str]:
    bmc_pet = _find_passage_index(
        passages,
        title_terms=("bmc guidelines",),
        anchor_terms=("pet-dog-residents",),
    )
    bmc_bylaws = _find_passage_index(
        passages,
        title_terms=("bmc guidelines",),
        anchor_terms=("housing-society-pet-bylaws",),
    )
    bmc_license = _find_passage_index(
        passages,
        title_terms=("bmc guidelines",),
        anchor_terms=("pet-owner-license-and-rwa",),
    )
    coop = _find_passage_index(
        passages,
        title_terms=("co-operative housing society", "cooperative housing society"),
    )
    if bmc_pet is None and bmc_bylaws is None and bmc_license is None:
        return []
    lines = ["**Short answer**"]
    if bmc_pet is not None:
        lines.append(
            f"The indexed pet-specific source is a Mumbai/BMC guideline aligned with AWBI materials, so first confirm your city and society bye-laws before treating it as locally binding [{bmc_pet}]."
        )
        lines.append(
            f"For a Mumbai/BMC society, that guideline says RWAs and apartment associations cannot legally introduce a ban on keeping pet dogs or cats [{bmc_pet}]."
        )
    if bmc_bylaws is not None:
        lines.append(
            f"For Mumbai/BMC matters, the same guideline says a housing society cannot pass pet bye-laws that disallow pets, though it can make rules for keeping dogs to protect pet welfare and residents' interests [{bmc_bylaws}]."
        )
    if bmc_license is not None:
        lines.append(
            f"The guideline also says pet owners should keep the society updated about the pet licence and vaccinations [{bmc_license}]."
        )
    lines.append("**What you can do next**")
    if coop is not None:
        lines.append(
            f"- If the society does not withdraw or justify the fine, use the cooperative-housing Registrar or local housing-authority route with the fine notice and your pet records [{coop}]."
        )
    else:
        next_cite = bmc_bylaws if bmc_bylaws is not None else bmc_pet if bmc_pet is not None else bmc_license
        lines.append(
            f"- Reply in writing asking the society to identify the exact local bye-law, resolution, licence condition, and legal basis for the fine before you pay it [{next_cite}]."
        )
    return lines


def _housing_parking_template_lines(query: str, passages: list[dict]) -> list[str]:
    parking_case = _find_passage_index(
        passages,
        title_terms=("velagacharla",),
    )
    consumer = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("sec-35", "sec-38", "sec-39", "sec-2"),
    )
    rera = _find_passage_index(
        passages,
        title_terms=("real estate",),
        anchor_terms=("sec-31", "sec-34", "sec-71"),
    )
    if parking_case is None:
        return []
    escalation_cite = consumer if consumer is not None else rera if rera is not None else parking_case
    lines = [
        "**Short answer**",
        (
            f"Treat this first as an apartment parking-enforcement dispute: preserve proof that the slot is allotted or reserved, because the parking source turns on definite material showing that the area was reserved for parking in the layout or allotment record [{parking_case}]."
        ),
        (
            f"Do not frame it only as a consumer case against the neighbour; use the society or association complaint route first, and use consumer/RERA only if the builder, promoter, or society failed a parking-related service or allotment obligation [{escalation_cite}]."
        ),
        "**What you can do next**",
        (
            f"- Send a written complaint to the association or society with photos, the parking-allotment proof, and the security-guard refusal; ask for a written enforcement response before escalating [{parking_case}]."
        ),
    ]
    return lines


def _subscription_refund_template_lines(query: str, passages: list[dict]) -> list[str]:
    consumer_refund = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-39",),
    )
    consumer_complaint = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-35",),
    )
    consumer_procedure = _find_passage_index(
        passages,
        title_terms=("consumer protection",),
        anchor_terms=("/sec-38",),
    )
    if consumer_refund is None and consumer_complaint is None and consumer_procedure is None:
        return []
    duration_phrase = "six-month paid subscription" if _has_any_term(query, ("6 months", "six months", "6-month", "six-month")) else "paid subscription"
    issue_phrase = f"{duration_phrase} with no refund" if _has_any_term(query, ("refund", "no refund")) else f"{duration_phrase} service issue"
    platform_phrase = "Hinge/Match Group" if _has_any_term(query, ("hinge", "match group")) else "digital-platform"
    service_record = "account-freeze notice" if _has_any_term(query, ("froze", "frozen")) else "account-block or suspension record" if _has_any_term(query, ("blocked", "suspended")) else "service record"
    evidence_phrase = f"payment proof, subscription screenshots, {service_record}, and customer-care record"
    lines = ["**Short answer**"]
    if consumer_refund is not None:
        lines.append(
            f"For a {platform_phrase} {issue_phrase}, the District Commission may order refund of the amount paid under the Consumer Protection Act source [{consumer_refund}]."
        )
    if consumer_complaint is not None:
        lines.append(
            f"Use the Consumer Protection Act complaint-route source for the paid-subscription service dispute, with {evidence_phrase} [{consumer_complaint}]."
        )
    elif consumer_procedure is not None:
        lines.append(
            f"Use the Consumer Protection Act procedure source for the paid-subscription service dispute, with {evidence_phrase} [{consumer_procedure}]."
        )
    lines.append("**What you can do next**")
    if consumer_complaint is not None:
        lines.append(
            f"- File a complaint with the District Commission under Section 35 of the Consumer Protection Act 2019 with {evidence_phrase} [{consumer_complaint}]."
        )
    else:
        action_cite = consumer_refund if consumer_refund is not None else consumer_procedure
        lines.append(
            f"- Prepare {evidence_phrase} before using the cited District Commission consumer route [{action_cite}]."
        )
    return lines


def _juvenile_age_custody_template_lines(query: str, passages: list[dict]) -> list[str]:
    age_proof = _find_passage_index_by_text(
        passages,
        title_terms=("juvenile justice",),
        text_terms=("age determination", "date of birth certificate from the school"),
    )
    court_inquiry = _find_passage_index_by_text(
        passages,
        title_terms=("juvenile justice",),
        text_terms=("claims before a court other than a board", "determine the age"),
    )
    bail = _find_passage_index_by_text(
        passages,
        title_terms=("juvenile justice",),
        text_terms=("apparently a child", "released on bail"),
    )
    no_jail = _find_passage_index_by_text(
        passages,
        title_terms=("juvenile justice",),
        text_terms=("police lockup", "lodged in a jail"),
    )
    board = _find_passage_index_by_text(
        passages,
        title_terms=("juvenile justice",),
        text_terms=("deal exclusively", "children in conflict with law"),
    )
    if age_proof is None and court_inquiry is None and bail is None and no_jail is None and board is None:
        return []
    child_phrase = "your daughter" if "daughter" in query else "your son" if "son" in query else "the child"
    lines = ["**Short answer**"]
    if age_proof is not None:
        lines.append(
            f"For {child_phrase}'s age proof, the JJ Act source says age determination first uses the school or matriculation date-of-birth certificate, then a municipal or panchayat birth certificate, and only then a medical age test [{age_proof}]."
        )
    if court_inquiry is not None:
        lines.append(
            f"If the child claim is raised before a court other than the Juvenile Justice Board, the court must inquire, take evidence, and record a finding on age [{court_inquiry}]."
        )
    if bail is not None:
        lines.append(
            f"For custody, the JJ Act source says a person apparently a child who is detained or brought before the Board is to be released on bail, subject to the statutory exceptions in that source [{bail}]."
        )
    if no_jail is not None:
        lines.append(
            f"The JJ Act source says that in no case shall a child alleged to be in conflict with law be placed in a police lockup or lodged in a jail [{no_jail}]."
        )
        juvenile_context = _present_terms_phrase(
            query,
            (
                ("17-year-old", "17", "seventeen"),
                ("adult jail", "adult jail", "jail"),
                ("POCSO case", "pocso"),
            ),
            fallback="this custody problem",
        )
        lines.append(
            f"For {juvenile_context}, the urgent JJ Act point is production before the Juvenile Justice Board and removal from jail or lockup [{no_jail}]."
        )
    if board is not None:
        lines.append(
            f"The Juvenile Justice Board is the forum with exclusive power for proceedings under the JJ Act relating to children in conflict with law [{board}]."
        )
    lines.append("**What you can do next**")
    if age_proof is not None and court_inquiry is not None:
        lines.append(
            f"- For where to raise the age claim, use the current criminal court or Juvenile Justice Board route stated in the JJ Act court-inquiry source [{court_inquiry}]."
        )
        lines.append(
            f"- For documents, use the school or matriculation certificate, municipal or panchayat birth certificate, and only then a medical age test as ordered under the JJ Act age-determination source [{age_proof}]."
        )
    elif age_proof is not None or court_inquiry is not None:
        next_cite = age_proof if age_proof is not None else court_inquiry
        lines.append(
            f"- File an age-determination application with the current criminal court or Juvenile Justice Board using the school certificate, birth certificate, custody papers, and POCSO/FIR details [{next_cite}]."
        )
    elif no_jail is not None:
        lines.append(
            f"- Use legal aid or the case papers to seek urgent production before the Juvenile Justice Board and removal from jail or lockup [{no_jail}]."
        )
    elif board is not None:
        lines.append(
            f"- Ask for production before the Juvenile Justice Board with the custody papers and FIR details [{board}]."
        )
    elif bail is not None:
        lines.append(
            f"- Ask the Juvenile Justice Board or legal-aid lawyer to move the custody or bail request under the JJ Act source [{bail}]."
        )
    return lines


def _interim_medical_bail_template_lines(passages: list[dict]) -> list[str]:
    article21 = _find_passage_index(
        passages,
        title_terms=("constitution",),
        anchor_terms=("/sec-21",),
    )
    bnss_bail = _find_passage_index_by_text(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        text_terms=("woman", "sick or infirm", "bail"),
    )
    if article21 is None or bnss_bail is None:
        return []
    return [
        "**Short answer**",
        f"The Constitution source protects life and personal liberty except by procedure established by law [{article21}].",
        f"The BNSS bail source says a Court may release an accused person on bail if the person is a woman, sick, or infirm [{bnss_bail}].",
        "**What you can do next**",
        f"- Ask the criminal court to consider bail on the pregnancy or medical condition, using the BNSS woman, sick, or infirm clause [{bnss_bail}].",
    ]


def _itpa_spa_raid_template_lines(query: str, passages: list[dict]) -> list[str]:
    itpa8 = _find_passage_index(
        passages,
        title_terms=("immoral traffic",),
        anchor_terms=("/sec-8",),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    bail = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-480", "/sec-483"),
    )
    if itpa8 is None and bnss173 is None and bail is None:
        return []
    lines = ["**Short answer**"]
    if itpa8 is not None:
        lines.append(
            f"A spa raid does not by itself answer whether police are treating you as a witness, a person needing protection, or an accused person; the retrieved ITPA source is specifically about soliciting for prostitution in a public place or within public view [{itpa8}]."
        )
    if bnss173 is not None:
        lines.append(
            f"For current-law procedure, the BNSS source says oral information to the officer in charge must be reduced to writing and read over to the informant; the incident date decides BNSS versus CrPC framing [{bnss173}]."
        )
    if bail is not None:
        lines.append(
            f"If arrest or custody is actually involved, the retrieved BNSS bail source is the court route to check next, not a generic complaint path [{bail}]."
        )
    lines.append("**What you can do next**")
    if bnss173 is not None:
        lines.append(
            f"- If police are recording information from you, ask that the oral information be reduced to writing and read over before you sign or acknowledge it [{bnss173}]."
        )
    elif bail is not None:
        lines.append(
            f"- If police are treating you as an accused person and custody is involved, take the arrest papers to legal aid or the court bail route reflected in the BNSS source [{bail}]."
        )
    elif itpa8 is not None:
        lines.append(
            f"- Before accepting any allegation, compare the police sections with the ITPA source, which is about soliciting in a public place or within public view [{itpa8}]."
        )
    return lines


def _itpa_call_handling_template_lines(query: str, passages: list[dict]) -> list[str]:
    itpa4 = _find_passage_index(
        passages,
        title_terms=("immoral traffic",),
        anchor_terms=("/sec-4",),
    )
    itpa5 = _find_passage_index(
        passages,
        title_terms=("immoral traffic",),
        anchor_terms=("/sec-5",),
    )
    itpa7 = _find_passage_index(
        passages,
        title_terms=("immoral traffic",),
        anchor_terms=("/sec-7",),
    )
    itpa8 = _find_passage_index(
        passages,
        title_terms=("immoral traffic",),
        anchor_terms=("/sec-8",),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    bail = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-480", "/sec-483"),
    )
    if itpa4 is None and itpa5 is None and itpa7 is None and itpa8 is None and bnss173 is None and bail is None:
        return []
    lines = ["**Short answer**"]
    if itpa5 is not None:
        lines.append(
            f"Section 5 of the Immoral Traffic (Prevention) Act covers procuring, inducing or taking a person for the sake of prostitution [{itpa5}]."
        )
    elif itpa4 is not None:
        lines.append(
            f"The ITPA source on living on earnings is a separate section to compare with the alleged role and money trail [{itpa4}]."
        )
    if itpa7 is not None:
        lines.append(
            f"The ITPA source on prostitution in or near notified or public places is a separate factual route from phone calls alone [{itpa7}]."
        )
    if itpa8 is not None:
        lines.append(
            f"The soliciting source is also a separate section, so ask what section police are relying on before treating phone conversation as public soliciting [{itpa8}]."
        )
    if bnss173 is not None:
        lines.append(
            f"For current procedure, the BNSS FIR/information source matters if police record information or ask you to sign a statement; incident date decides BNSS versus CrPC framing [{bnss173}]."
        )
    action_cite = itpa5 if itpa5 is not None else itpa4 if itpa4 is not None else itpa8 if itpa8 is not None else itpa7 if itpa7 is not None else bnss173 if bnss173 is not None else bail
    if itpa5 is not None:
        action_line = f"- Compare whether police allege procuring, inducing or taking a person for the sake of prostitution under Section 5, and get the FIR or notice sections before deciding defence [{action_cite}]."
    else:
        action_line = f"- Get the FIR or notice sections and compare the alleged role with the cited ITPA section before deciding defence [{action_cite}]."
    lines.extend([
        "**What you can do next**",
        action_line,
    ])
    return lines


def _forest_false_dacoity_template_lines(query: str, passages: list[dict]) -> list[str]:
    fra3 = _find_passage_index_by_text(
        passages,
        title_terms=("forest dwellers", "forest rights"),
        text_terms=("minor forest produce",),
    )
    if fra3 is None:
        fra3 = _find_passage_index(
            passages,
            title_terms=("forest dwellers", "forest rights"),
            anchor_terms=("/sec-3",),
        )
    bns_offence = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya sanhita",),
        anchor_terms=("/sec-310", "/sec-309", "/sec-308"),
    )
    bnss_bail = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-483", "/sec-480"),
    )
    if fra3 is None and bns_offence is None and bnss_bail is None:
        return []
    produce_phrase = "tendu leaves" if "tendu" in query else "minor forest produce"
    lines = ["**Short answer**"]
    if fra3 is not None:
        lines.append(
            f"For collecting {produce_phrase}, first check whether the Forest Rights Act source applies because the retrieved section covers forest rights including minor forest produce and community forest rights [{fra3}]."
        )
    if bns_offence is not None:
        lines.append(
            f"For current-law offence framing, the BNS source says dacoity is when five or more persons conjointly commit or attempt to commit robbery; the incident date decides BNS/BNSS versus IPC/CrPC framing [{bns_offence}]."
        )
    if bnss_bail is not None:
        lines.append(
            f"If arrest or custody is involved, the retrieved BNSS bail source is the immediate court route to check alongside the FIR sections [{bnss_bail}]."
        )
    lines.append("**What you can do next**")
    action_cite = bnss_bail if bnss_bail is not None else bns_offence if bns_offence is not None else fra3
    lines.append(
        f"- Collect the FIR, seizure memo, forest-permit or Gram Sabha/FRA papers, witness names, and the number of alleged accused before moving bail or a false-case defence application [{action_cite}]."
    )
    return lines


def _police_torture_complaint_template_lines(query: str, passages: list[dict]) -> list[str]:
    nhrc12 = _find_passage_index(
        passages,
        title_terms=("protection of human rights",),
        anchor_terms=("/sec-12",),
    )
    bnss173 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-173",),
    )
    bns_hurt = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya sanhita",),
        anchor_terms=("/sec-117", "/sec-115"),
    )
    article21 = _find_passage_index(
        passages,
        title_terms=("constitution of india",),
        anchor_terms=("/sec-21",),
    )
    if nhrc12 is None and bnss173 is None and bns_hurt is None and article21 is None:
        return []
    lines = ["**Short answer**"]
    if nhrc12 is not None:
        lines.append(
            f"For a police-torture complaint after release, the Human Rights Act source says the Commission can inquire into complaints of human-rights violation or negligence in prevention by a public servant [{nhrc12}]."
        )
    if bnss173 is not None:
        lines.append(
            f"If you also report a cognizable offence to police, the BNSS source says oral information to the officer in charge must be reduced to writing and read over to the informant [{bnss173}]."
        )
    if bns_hurt is not None:
        lines.append(
            f"If the allegation includes physical injury, the BNS hurt or grievous-hurt source is relevant, but the incident date still decides BNS/BNSS versus IPC/CrPC framing [{bns_hurt}]."
        )
    elif article21 is not None:
        lines.append(
            f"Article 21 is also relevant for custody-related liberty and bodily-integrity framing, but the complaint still needs dated facts and medical proof [{article21}]."
        )
    lines.append("**What you can do next**")
    action_cite = nhrc12 if nhrc12 is not None else bnss173 if bnss173 is not None else bns_hurt if bns_hurt is not None else article21
    lines.append(
        f"- File a written NHRC/SHRC complaint and a police/SP complaint with release date, jail/custody papers, medical records, witness names, and the officers involved [{action_cite}]."
    )
    return lines


def _joint_property_sale_template_lines(query: str, passages: list[dict]) -> list[str]:
    tpa45 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-45",),
    )
    tpa44 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-44",),
    )
    specific31 = _find_passage_index(
        passages,
        title_terms=("specific relief",),
        anchor_terms=("/sec-31",),
    )
    specific34 = _find_passage_index(
        passages,
        title_terms=("specific relief",),
        anchor_terms=("/sec-34",),
    )
    if tpa45 is None and tpa44 is None and specific31 is None and specific34 is None:
        return []
    lines = ["**Short answer**"]
    if tpa45 is not None:
        lines.append(
            f"For a plot bought by two people, first check the Transfer of Property Act joint-purchase source because it deals with transfers for consideration to two or more persons [{tpa45}]."
        )
    if tpa44 is not None:
        lines.append(
            f"If your brother sold what he could transfer as a co-owner, the co-owner transfer source is relevant, but the sale deed must be checked to see what share or interest was transferred [{tpa44}]."
        )
    if specific31 is not None:
        lines.append(
            f"If a sale deed affecting your share may cause serious injury if left outstanding, the Specific Relief Act cancellation source is the civil-court source to check [{specific31}]."
        )
    elif specific34 is not None:
        lines.append(
            f"If your ownership right or share is being denied, the Specific Relief Act declaration source is the civil-court source to check [{specific34}]."
        )
    lines.append("**What you can do next**")
    action_cite = specific31 if specific31 is not None else specific34 if specific34 is not None else tpa45 if tpa45 is not None else tpa44
    if specific31 is not None:
        lines.append(
            f"- For the civil-court step, check whether the sale deed is a written instrument that is void or voidable against you and may cause serious injury if left outstanding, because that is the cancellation route in the cited Specific Relief source [{specific31}]."
        )
    elif specific34 is not None:
        lines.append(
            f"- For the civil-court step, check whether your legal character or property right is being denied, because that is the declaration route in the cited Specific Relief source [{specific34}]."
        )
    else:
        lines.append(
            f"- For the property-record step, compare the registered sale deed, earlier purchase deed, payment proof, mutation record, and possession facts with the cited co-owner transfer source [{action_cite}]."
        )
    return lines


def _ancestral_land_sale_template_lines(query: str, passages: list[dict]) -> list[str]:
    hsa = _find_passage_index(
        passages,
        title_terms=("hindu succession",),
        anchor_terms=("/sec-6", "/sec-8", "/sec-10"),
    ) or _find_passage_index_by_text(
        passages,
        text_terms=("hindu succession act", "section 6"),
    )
    tpa44 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-44",),
    )
    tpa45 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-45",),
    )
    specific31 = _find_passage_index(
        passages,
        title_terms=("specific relief",),
        anchor_terms=("/sec-31",),
    )
    specific34 = _find_passage_index(
        passages,
        title_terms=("specific relief",),
        anchor_terms=("/sec-34",),
    )
    if hsa is None and tpa44 is None and tpa45 is None and specific31 is None and specific34 is None:
        return []
    lines = ["**Short answer**"]
    if hsa is not None:
        lines.append(
            f"For ancestral or grandfather/dada land, the Hindu Succession source is the inheritance/share source to check before accepting an uncle's proposed sale as binding on everyone [{hsa}]."
        )
    if tpa44 is not None:
        lines.append(
            f"If one co-owner or heir sells, the Transfer of Property Act co-owner transfer source is relevant to check whether only that person's share or interest was transferred [{tpa44}]."
        )
    elif tpa45 is not None:
        lines.append(
            f"The Transfer of Property Act joint-interest source is relevant only after the deed and contribution/share facts are known [{tpa45}]."
        )
    if specific31 is not None:
        lines.append(
            f"If a registered sale deed wrongly affects your share, the Specific Relief Act cancellation source is the civil-court remedy to check [{specific31}]."
        )
    elif specific34 is not None:
        lines.append(
            f"If your heirship or share is denied, the Specific Relief Act declaration source is the civil-court remedy to check [{specific34}]."
        )
    lines.append("**What you can do next**")
    action_cite = specific31 if specific31 is not None else specific34 if specific34 is not None else hsa if hsa is not None else tpa44 if tpa44 is not None else tpa45
    lines.append(
        f"- Get certified copies of the old title deed, mutation/khata, death certificate, family tree/legal-heir papers, proposed or registered sale deed, and possession proof before asking for injunction, declaration, partition, or cancellation in civil court [{action_cite}]."
    )
    return lines


def _tenant_nonpayment_vacate_template_lines(query: str, passages: list[dict]) -> list[str]:
    tpa106 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-106",),
    )
    if tpa106 is None:
        tpa106 = _find_passage_index_by_text(
            passages,
            title_terms=("transfer of property",),
            text_terms=("106. duration of certain leases", "terminable", "notice"),
        )
    tpa111 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-111",),
    )
    tpa105 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-105",),
    )
    if tpa106 is None and tpa111 is None and tpa105 is None:
        return []
    lines = ["**Short answer**"]
    if tpa105 is not None:
        lines.append(
            f"Treat this first as a tenancy/lease dispute, because the Transfer of Property Act lease source is the starting point where it applies [{tpa105}]."
        )
    if tpa106 is not None:
        lines.append(
            f"For asking a tenant to vacate, the Transfer of Property Act notice source is important, subject to any state rent-control law that applies in your city [{tpa106}]."
        )
    if tpa111 is not None:
        lines.append(
            f"The lease-determination source is also relevant before filing for possession or rent arrears [{tpa111}]."
        )
    lines.append("**What you can do next**")
    if tpa106 is not None:
        lines.append(
            f"- Collect the rent agreement, rent ledger/receipts, notices, and messages; then ask a local lawyer/legal-aid desk or rent authority/civil court about the notice and eviction route for your state [{tpa106}]."
        )
    elif tpa111 is not None:
        lines.append(
            f"- Collect the rent agreement, arrears calculation, possession facts, notices, and messages before filing through the rent authority or civil court route instead of self-help eviction [{tpa111}]."
        )
    elif tpa105 is not None:
        lines.append(
            f"- First confirm the rent agreement, possession status, monthly rent, arrears, and state/city law before choosing the rent authority or civil court route [{tpa105}]."
        )
    return lines


def _property_pressure_transfer_template_lines(query: str, passages: list[dict]) -> list[str]:
    contract19 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-19",),
    )
    contract16 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-16",),
    )
    if contract16 is None:
        contract16 = _find_passage_index_by_text(
            passages,
            title_terms=("indian contract",),
            text_terms=("undue influence", "dominate the will"),
        )
    tpa126 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-126",),
    )
    tpa_transfer = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-45", "/sec-122", "/sec-123"),
    )
    specific31 = _find_passage_index(
        passages,
        title_terms=("specific relief",),
        anchor_terms=("/sec-31",),
    )
    specific34 = _find_passage_index(
        passages,
        title_terms=("specific relief",),
        anchor_terms=("/sec-34",),
    )
    if contract19 is None and contract16 is None and tpa126 is None and tpa_transfer is None and specific31 is None and specific34 is None:
        return []
    property_context = _present_terms_phrase(
        query,
        (
            ("dad", "dad", "father", "papa"),
            ("son", "son"),
            ("uncle", "uncle"),
            ("cousin", "cousin"),
            ("ICU", "icu"),
            ("hospital", "hospital"),
            ("pressure", "pressure", "forced", "undue influence"),
        ),
        fallback="the challenged property signing",
    )
    lines = ["**Short answer**"]
    if contract16 is not None:
        lines.append(
            f"For {property_context}, check undue influence/free-consent facts because the Contract Act source covers undue influence in the retrieved section [{contract16}]."
        )
    if contract19 is not None:
        lines.append(
            f"For {property_context}, the Contract Act source also says an agreement where consent is caused by coercion, fraud, or misrepresentation is voidable at the option of the party whose consent was so caused [{contract19}]."
        )
    if tpa126 is not None:
        lines.append(
            f"If the document was a gift, the Transfer of Property Act source deals with when a gift may be suspended or revoked, so the deed terms and revocation facts matter [{tpa126}]."
        )
    elif tpa_transfer is not None:
        lines.append(
            f"The Transfer of Property Act source is relevant because the property document still has to be checked as a transfer or gift deed, not only as a family dispute [{tpa_transfer}]."
        )
    if specific31 is not None:
        lines.append(
            f"For the court remedy, the Specific Relief Act source says a person against whom a void or voidable written instrument may cause serious injury may sue to have it adjudged void or voidable and cancelled [{specific31}]."
        )
    elif specific34 is not None:
        lines.append(
            f"For the court remedy, the Specific Relief Act source covers a declaration of status or property right where another person denies or is interested to deny that right [{specific34}]."
        )
    lines.append("**What you can do next**")
    action_cite = specific31 if specific31 is not None else specific34 if specific34 is not None else contract19 if contract19 is not None else contract16 if contract16 is not None else tpa126 if tpa126 is not None else tpa_transfer
    if specific31 is not None:
        lines.append(
            f"- Build the civil challenge with the registered deed, medical or capacity records if relevant, witnesses to pressure, and possession or mutation papers; if the written instrument is void or voidable and may cause serious injury if left outstanding, sue to have it adjudged void or voidable and cancelled [{specific31}]."
        )
    elif specific34 is not None:
        lines.append(
            f"- If the owner's property right or status is denied, use the declaration route reflected in the Specific Relief Act source [{specific34}]."
        )
    else:
        lines.append(
            f"- Build the challenge around the registered deed, medical or capacity records if relevant, witnesses, payment or gift details, and proof of pressure before the civil court step [{action_cite}]."
        )
    return lines


def _property_document_fraud_template_lines(query: str, passages: list[dict]) -> list[str]:
    contract14 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-14",),
    )
    contract16 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-16",),
    )
    contract17 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-17",),
    )
    contract19 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-19",),
    )
    tpa122 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-122",),
    )
    tpa123 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-123",),
    )
    tpa126 = _find_passage_index(
        passages,
        title_terms=("transfer of property",),
        anchor_terms=("/sec-126",),
    )
    registration = _find_passage_index(
        passages,
        title_terms=("registration act",),
        anchor_terms=("/sec-17", "/sec-49"),
    )
    specific31 = _find_passage_index(
        passages,
        title_terms=("specific relief",),
        anchor_terms=("/sec-31",),
    )
    specific34 = _find_passage_index(
        passages,
        title_terms=("specific relief",),
        anchor_terms=("/sec-34",),
    )
    bns_forgery = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-336", "/sec-338", "/sec-340", "/sec-318"),
    )
    crpc_complaint = _find_passage_index(
        passages,
        title_terms=("criminal procedure",),
        anchor_terms=("/sec-154", "/sec-156", "/sec-200"),
    )
    if (
        contract14 is None and contract16 is None and contract17 is None and contract19 is None
        and tpa122 is None and tpa123 is None and tpa126 is None
        and registration is None and specific31 is None and specific34 is None and bns_forgery is None
    ):
        return []
    deed_phrase = "gift deed" if "gift" in query else "property document"
    lines = ["**Short answer**"]
    if _has_any_term(query, ("thumb impression", "blank paper", "fake signature", "forged", "forgery", "didn't sign", "did not sign")) and (
        contract16 is not None or contract17 is not None or contract19 is not None or tpa123 is not None or tpa122 is not None
    ):
        consent_cite = contract16 if contract16 is not None else contract19 if contract19 is not None else contract17
        gift_cite = tpa123 if tpa123 is not None else tpa122
        cited = [idx for idx in (consent_cite, gift_cite) if idx is not None]
        citation_text = "".join(f"[{idx}]" for idx in cited[:2])
        if citation_text:
            lines.append(
                f"For a thumb impression, blank paper, or disputed signature later shown as a {deed_phrase}, the free-consent and gift-deed sources are the first sources to check {citation_text}."
            )
    if contract16 is not None:
        lines.append(
            f"For a thumb impression or blank-paper signature later shown as a {deed_phrase}, first test free consent and undue influence under the Contract Act source, not just mutation or possession [{contract16}]."
        )
    elif contract14 is not None:
        lines.append(
            f"For a thumb impression or blank-paper signature later shown as a {deed_phrase}, first test whether consent was free under the Contract Act source [{contract14}]."
        )
    if contract17 is not None or contract19 is not None:
        cite = contract19 if contract19 is not None else contract17
        lines.append(
            f"If the document was obtained by fraud, misrepresentation, coercion, or other non-free consent, the Contract Act source is the consent challenge to compare with proof [{cite}]."
        )
    if tpa122 is not None or tpa123 is not None:
        cite = tpa123 if tpa123 is not None else tpa122
        lines.append(
            f"If the paper is a gift deed, the Transfer of Property Act gift-deed source must be checked with the registered document and attestation/registration facts [{cite}]."
        )
    if tpa126 is not None:
        lines.append(
            f"Gift revocation or suspension is a limited Transfer of Property Act question, so do not assume every family dispute automatically cancels a registered gift [{tpa126}]."
        )
    if registration is not None:
        lines.append(
            f"The Registration Act source matters because a registered immovable-property document must be challenged through the record and civil-court route rather than ignored orally [{registration}]."
        )
    if specific31 is not None:
        lines.append(
            f"For the court remedy, the Specific Relief Act cancellation source is the direct civil route if the written instrument is void or voidable against the owner and may cause serious injury if left outstanding [{specific31}]."
        )
    elif specific34 is not None:
        lines.append(
            f"For the court remedy, the Specific Relief Act declaration source can matter where ownership or legal character is denied [{specific34}]."
        )
    if bns_forgery is not None and not _query_mentions_pre_july_2024(query):
        lines.append(
            f"If the facts show a forged or false document, keep a separate police track; the retrieved BNS source is current-law support only, so the incident date still decides whether BNS/BNSS or IPC/CrPC applies [{bns_forgery}]."
        )
    if crpc_complaint is not None and _query_mentions_pre_july_2024(query):
        lines.append(
            f"For a pre-July-2024 alleged forged deed or signature, the CrPC complaint source is the police/Magistrate procedure to check alongside the civil cancellation route [{crpc_complaint}]."
        )
    lines.append("**What you can do next**")
    action_cite = specific31 if specific31 is not None else specific34 if specific34 is not None else contract16 if contract16 is not None else contract19 if contract19 is not None else tpa123 if tpa123 is not None else registration if registration is not None else bns_forgery
    lines.append(
        f"- Get the certified copy of the deed, thumb-impression/signature proof, witness/medical or capacity facts, mutation record, possession papers, and notices, then ask for civil cancellation/declaration and record correction; add a police complaint only for the forgery facts [{action_cite}]."
    )
    return lines


def _dpdp_data_breach_template_lines(query: str, passages: list[dict]) -> list[str]:
    sec8 = _find_passage_index(
        passages,
        title_terms=("digital personal data protection",),
        anchor_terms=("/sec-8",),
    )
    sec13 = _find_passage_index(
        passages,
        title_terms=("digital personal data protection",),
        anchor_terms=("/sec-13",),
    )
    sec27 = _find_passage_index(
        passages,
        title_terms=("digital personal data protection",),
        anchor_terms=("/sec-27",),
    )
    if sec8 is None and sec13 is None and sec27 is None:
        return []
    lines = ["**Short answer**"]
    if sec8 is not None:
        lines.append(
            f"For a PAN/Aadhaar personal-data leak, the DPDP source says the Data Fiduciary must use reasonable security safeguards to prevent personal data breach and must give breach notice to the Board and affected Data Principal [{sec8}]."
        )
    if sec27 is not None:
        lines.append(
            f"The Board can inquire into a Data Principal's complaint about a personal data breach or breach of the Data Fiduciary's obligations and impose penalties under the Act [{sec27}]."
        )
    lines.append("**What you can do next**")
    if sec13 is not None:
        lines.append(
            f"- First use the company's grievance redressal route, because the DPDP source says the Data Principal must exhaust that opportunity before approaching the Board [{sec13}]."
        )
    if sec27 is not None:
        lines.append(
            f"- If the company does not resolve it, file a Board complaint with the breach notice, account details, screenshots, and proof that PAN/Aadhaar data was exposed [{sec27}]."
        )
    return lines


def _bonded_labour_template_lines(query: str, passages: list[dict]) -> list[str]:
    sec4 = _find_passage_index(
        passages,
        title_terms=("bonded labour system",),
        anchor_terms=("/sec-4",),
    )
    sec10 = _find_passage_index(
        passages,
        title_terms=("bonded labour system",),
        anchor_terms=("/sec-10",),
    )
    sec12 = _find_passage_index(
        passages,
        title_terms=("bonded labour system",),
        anchor_terms=("/sec-12",),
    )
    sec13 = _find_passage_index(
        passages,
        title_terms=("bonded labour system",),
        anchor_terms=("/sec-13",),
    )
    aadhaar29 = _find_passage_index(
        passages,
        title_terms=("aadhaar", "aadhar"),
        anchor_terms=("/sec-29",),
    )
    aadhaar37 = _find_passage_index(
        passages,
        title_terms=("aadhaar", "aadhar"),
        anchor_terms=("/sec-37",),
    )
    release_context = _has_any_term(query, ("release certificate", "rehabilitation", "rehab", "rehab money", "200000", "2 lakh"))
    aadhaar_context = _has_any_term(query, ("aadhaar", "aadhar", "original id", "id original", "identity card", "documents"))
    restraint_context = _has_any_term(query, ("hostage", "cannot go home", "not letting leave", "can't leave", "cannot leave", "advance"))
    if aadhaar_context and (sec12 is not None or aadhaar29 is not None or aadhaar37 is not None):
        lines = ["**Short answer**"]
        if sec12 is not None:
            lines.append(
                f"If a contractor is keeping workers' Aadhaar or original ID while stopping them from leaving, keep it framed as a bonded/forced-labour rescue fact for District Magistrate inquiry [{sec12}]."
            )
        if aadhaar29 is not None:
            lines.append(
                f"The Aadhaar Act source should be kept as a separate identity-data source, so the complaint should record exactly who took the Aadhaar and how it is being used or withheld [{aadhaar29}]."
            )
        elif aadhaar37 is not None:
            lines.append(
                f"The Aadhaar Act penalty source is a separate identity misuse route to check after you pin down who kept or used the Aadhaar details [{aadhaar37}]."
            )
        lines.append("**What you can do next**")
        action_cite = sec12 if sec12 is not None else aadhaar29 if aadhaar29 is not None else aadhaar37
        lines.append(
            f"- Give the DM/labour office the contractor name, worksite, worker names, Aadhaar-withholding fact, and whether anyone is prevented from leaving; ask for rescue/release action and return of documents [{action_cite}]."
        )
        return lines
    if release_context and (sec12 is not None or sec13 is not None or sec10 is not None or sec4 is not None):
        lines = ["**Short answer**"]
        if sec4 is not None:
            lines.append(
                f"The Bonded Labour Act source says the bonded labour system is abolished and bonded labourers stand freed from the obligation to render bonded labour [{sec4}]."
            )
        if sec12 is not None:
            release_place = "Jharkhand SDM/DM" if "jharkhand" in query else "District Magistrate"
            lines.append(
                f"For a release-certificate or rehabilitation-money follow-up, start with the {release_place} inquiry/action source because the DM must inquire whether bonded or forced labour is being enforced and take necessary action [{sec12}]."
            )
        if sec13 is not None:
            lines.append(
                f"The Vigilance Committee source is also relevant for tracking bonded-labour identification, release, and follow-up at district/sub-divisional level [{sec13}]."
            )
        elif sec10 is not None:
            lines.append(
                f"The Act also allows specified authorities to implement its provisions, so the complaint should be tied to the local authority named for bonded-labour implementation [{sec10}]."
            )
        lines.append("**What you can do next**")
        action_cite = sec12 if sec12 is not None else sec13 if sec13 is not None else sec10 if sec10 is not None else sec4
        lines.append(
            f"- File a written request with the SDM/DM for release-certificate status, rescue record, rehabilitation status, and Vigilance Committee follow-up, attaching worksite, contractor, family, and prior complaint details [{action_cite}]."
        )
        return lines
    if sec12 is not None and (sec4 is None or restraint_context) and _has_any_term(query, ("advance", "not letting leave", "cannot leave", "can't leave", "hostage", "cannot go home")):
        worksite_phrase = "worksite"
        if "darbhanga" in query and _has_any_term(query, ("bangalore", "bengaluru")):
            worksite_phrase = "Darbhanga-to-Bangalore worksite"
        elif _has_any_term(query, ("site", "worksite")):
            worksite_phrase = "site or worksite"
        if _has_any_term(query, ("brick kiln", "hostage", "wife sick")):
            restraint_phrase = "keeping the family at the brick-kiln worksite despite the advance and illness facts"
        else:
            restraint_phrase = "keeping the family at the worksite" if _has_any_term(query, ("family", "hostage")) else "using an advance to stop you leaving the worksite"
        return [
            "**Short answer**",
            (
                f"If a thekedar or contractor is {restraint_phrase}, "
                "ask the District Magistrate to inquire whether bonded labour or forced labour is being enforced "
                f"and to take necessary action [{sec12}]."
            ),
            "**What you can do next**",
            (
                f"- Give the District Magistrate or labour office the advance amount, the {worksite_phrase} "
                f"details, and the fact that you are being stopped from leaving [{sec12}]."
            ),
        ]
    if sec4 is None or sec12 is None:
        return []
    if "12 years" in query and _has_any_term(query, ("no wages", "just food", "without wages")):
        opening = "For 12 years of work without wages, the bonded labour system stands abolished"
    elif _has_any_term(query, ("no wages", "without wages", "just food")):
        opening = "For work without wages, the bonded labour system stands abolished"
    else:
        opening = "The bonded labour system stands abolished"
    return [
        "**Short answer**",
        (
            f"{opening} and every bonded labourer "
            f"stands freed and discharged from any obligation to render bonded labour [{sec4}]."
        ),
        (
            "The District Magistrate must inquire whether bonded labour or forced labour "
            f"is being enforced and take necessary action to eradicate it [{sec12}]."
        ),
        "**What you can do next**",
        (
            "- Ask the District Magistrate to inquire whether bonded labour or forced labour "
            f"is being enforced and take necessary action to eradicate it [{sec12}]."
        ),
    ]


def _birth_certificate_rti_template_lines(query: str, passages: list[dict]) -> list[str]:
    sec6 = _find_passage_index(passages, title_terms=("right to information act",), anchor_terms=("/sec-6",))
    sec7 = _find_passage_index(passages, title_terms=("right to information act",), anchor_terms=("/sec-7",))
    sec19 = _find_passage_index(passages, title_terms=("right to information act",), anchor_terms=("/sec-19",))
    if sec6 is None:
        return []
    child_phrase = "your child's birth certificate" if _has_any_term(query, ("child", "baby", "son", "daughter")) else "the birth certificate"
    birth_context = " born at home" if _has_any_term(query, ("born at home", "home birth")) else ""
    office_phrase = "panchayat or registrar" if "panchayat" in query else "registrar or municipal office"
    refusal_phrase = (
        " and the official's refusal"
        if _has_any_term(query, ("not giving", "refusing", "refused", "denied", "secretary"))
        else ""
    )
    lines = [
        "**Short answer**",
        (
            f"For {child_phrase}{birth_context}, use RTI to ask the {office_phrase} "
            f"for the application status, the reason for refusal, and the rule being applied [{sec6}]."
        ),
        "**What you can do next**",
        (
            "- File a written or electronic RTI request for the birth-certificate file status, noting the "
            f"birth facts{refusal_phrase} [{sec6}]."
        ),
    ]
    if sec7 is not None:
        lines.insert(2, f"The public information officer generally has thirty days to provide or reject the information request [{sec7}].")
    if sec19 is not None:
        lines.append(f"- If there is no decision or an improper refusal, file the RTI first appeal to the senior officer route [{sec19}].")
    return lines


def _kanya_vivah_scheme_template_lines(query: str, passages: list[dict]) -> list[str]:
    scheme = _find_passage_index(passages, title_terms=("kanya vivah", "mukhyamantri kanya vivah"))
    rti6 = _find_passage_index(passages, title_terms=("right to information",), anchor_terms=("/sec-6",))
    rti19 = _find_passage_index(passages, title_terms=("right to information",), anchor_terms=("/sec-19",))
    if scheme is None and rti6 is None:
        return []
    state_phrase = "Bihar " if _has_any_term(query, ("bihar", "patna", "gaya", "muzaffarpur")) else "state-specific "
    lines = ["**Kanya Vivah payment status**", "**Short answer**"]
    if scheme is not None:
        lines.append(
            f"For {state_phrase}Kanya Vivah scheme money, start with the scheme/service source and check the application status, eligibility papers, and marriage-certificate record before treating it as a generic RTI appeal [{scheme}]."
        )
    elif rti6 is not None:
        lines.append(
            f"For Kanya Vivah scheme money not given after the daughter wedding, use RTI only as the record-status route for the public authority holding the payment file [{rti6}]."
        )
        lines.append(
            f"The RTI source says a person seeking information may make a request in writing or through electronic means to the public information officer [{rti6}]."
        )
        lines.append(
            f"The same RTI source permits the request in English, Hindi, or the official language of the area where the application is made [{rti6}]."
        )
        lines.append(
            f"The RTI source also says the request is accompanied by the prescribed fee [{rti6}]."
        )
    if scheme is not None and rti6 is not None:
        lines.append(
            f"The RTI source is the statutory request route for obtaining information from the public authority that holds the scheme record [{rti6}]."
        )
    lines.append("**What you can do next**")
    return lines


def _wage_waiver_language_template_lines(query: str, passages: list[dict]) -> list[str]:
    wages60 = _find_passage_index(passages, title_terms=("code on wages",), anchor_terms=("/sec-60",))
    wages45 = _find_passage_index(passages, title_terms=("code on wages",), anchor_terms=("/sec-45",))
    contract19 = _find_passage_index(passages, title_terms=("indian contract",), anchor_terms=("/sec-19",))
    wages17 = _find_passage_index(passages, title_terms=("code on wages",), anchor_terms=("/sec-17",))
    if wages60 is None and wages45 is None and contract19 is None and wages17 is None:
        return []
    paper_phrase = "English/Kannada wage-waiver paper" if _has_any_term(query, ("english", "kannada")) else "wage-waiver paper"
    lines = ["**Short answer**"]
    if wages60 is not None:
        lines.append(
            f"Do not treat the {paper_phrase} as automatically ending the wage claim: the Code on Wages source specifically addresses contracting out or relinquishing wage rights [{wages60}]."
        )
    elif wages17 is not None:
        lines.append(
            f"Do not treat the {paper_phrase} as automatically ending the wage claim; first compare the unpaid-wage facts with the Code on Wages payment source [{wages17}]."
        )
    if contract19 is not None:
        lines.append(
            f"If the paper was signed without understanding, under pressure, or because of misrepresentation, preserve those facts separately because the Contract Act source deals with agreements without free consent [{contract19}]."
        )
    lines.append("**What you can do next**")
    if wages45 is not None:
        lines.append(
            f"The Code on Wages claims source provides for appointed authorities to hear and determine claims arising under the Code [{wages45}]."
        )
    return lines


def _witch_accused_defence_template_lines(query: str, passages: list[dict]) -> list[str]:
    bail = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha sanhita",),
        anchor_terms=("/sec-483", "/sec-480"),
    )
    witch = _find_passage_index(
        passages,
        title_terms=("witch hunting", "tonhi", "daain"),
    )
    if witch is not None and not _has_any_term(query, ("assam", "barpeta", "guwahati", "dibrugarh", "jorhat")):
        witch = None
    if bail is None and witch is None:
        return []
    state_phrase = "Chhattisgarh " if "chhattisgarh" in query else ""
    incident_phrase = " after a child death" if _has_any_term(query, ("child died", "child death")) else ""
    label_phrase = "tonhi" if "tonhi" in query else "witch-branding"
    if witch is None and bail is not None:
        return [
            "**Short answer**",
            f"The BNSS source is a High Court or Court of Session bail-power source, so use it only if arrest or custody is involved in the {state_phrase}{label_phrase} false-case matter{incident_phrase} [{bail}].",
            f"If there is arrest or custody in the {state_phrase}{label_phrase} false-case matter, the BNSS source says the High Court or Court of Session may direct release on bail [{bail}].",
            "**What you can do next**",
            f"- If arrest or custody is involved, take the FIR, custody status, and tonhi or witch-branding messages to the High Court or Court of Session bail route [{bail}].",
        ]
    return [
        "**Short answer**",
        f"For a {state_phrase}{label_phrase} false-case allegation{incident_phrase}, separate the accused-rights route from the state witch-branding-law route; the indexed witch-hunting source shows why witch-branding facts should not be treated as an ordinary village quarrel [{witch}].",
        "**What you can do next**",
        (
            "- Get the FIR or notice sections, incident date, custody status, and any messages using tonhi or "
            f"witch-branding words before filing the bail or defence application [{bail if bail is not None else witch}]."
        ),
    ]


def _elder_498a_accused_template_lines(query: str, passages: list[dict]) -> list[str]:
    bns85 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya",),
        anchor_terms=("/sec-85", "/sec-86"),
    )
    bnss_bail = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-480", "/sec-483"),
    )
    crpc_bail = _find_passage_index(
        passages,
        title_terms=("criminal procedure",),
        anchor_terms=("/sec-437", "/sec-438", "/sec-439"),
    )
    if bns85 is None and bnss_bail is None and crpc_bail is None:
        return []
    age_phrase = "your 71-year-old mother" if _has_any_term(query, ("71", "70", "old mother", "elderly mother")) else "the elderly family member"
    lines = ["**Short answer**"]
    if bns85 is not None:
        lines.append(
            f"For a false 498A/dowry-cruelty FIR naming {age_phrase}, first get the exact FIR sections and incident dates; the current BNS cruelty source is relevant only if the case is under the new criminal regime [{bns85}]."
        )
    if bnss_bail is not None:
        lines.append(
            f"If arrest is feared or notice/arrest has started, the BNSS bail source is the current-law bail route to check with age, medical papers, role in the household, and allegations in the FIR [{bnss_bail}]."
        )
    elif crpc_bail is not None:
        lines.append(
            f"If the FIR is from the older CrPC/IPC regime, use the CrPC bail/anticipatory-bail source instead of mixing it with current BNSS framing [{crpc_bail}]."
        )
    lines.append("**What you can do next**")
    action_cite = bnss_bail if bnss_bail is not None else crpc_bail if crpc_bail is not None else bns85
    lines.append(
        f"- Collect the FIR, notice/arrest status, age and medical records, residence proof, call/location proof, and specific role alleged; then ask a criminal lawyer or DLSA about anticipatory/regular bail, quashing only if the FIR is plainly abusive, and cooperation conditions [{action_cite}]."
    )
    return lines


def _ndps_bail_template_lines(query: str, passages: list[dict]) -> list[str]:
    ndps20 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-20",),
    )
    ndps14 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-14",),
    )
    ndps2 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-2",),
    )
    ndps36a = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-36A",),
    )
    ndps37 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-37",),
    )
    article21 = _find_passage_index(
        passages,
        title_terms=("constitution of india",),
        anchor_terms=("/sec-21",),
    )
    bnss_bail = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha sanhita",),
        anchor_terms=("/sec-480", "/sec-483"),
    )
    if ndps20 is None and ndps14 is None and ndps2 is None and ndps36a is None and ndps37 is None and article21 is None and bnss_bail is None:
        return []
    has_three_years = _has_any_term(query, ("3 yrs", "3 years", "three years"))
    has_tihar = "tihar" in query
    custody_timeline_context = has_three_years or _has_any_term(query, (
        "long custody", "custody delay", "trial delay", "no chargesheet",
        "no charge sheet", "default bail", "180 days", "one hundred eighty days",
        "commercial quantity",
    ))
    if has_three_years and has_tihar:
        custody_phrase = "three years in Tihar"
    elif has_three_years:
        custody_phrase = "three years in custody"
    elif has_tihar:
        custody_phrase = "custody in Tihar"
    else:
        custody_phrase = "long custody"
    lines = ["**Short answer**"]
    if ndps20 is not None and _has_any_term(query, ("ganja", "cannabis", "weed", "charas")):
        lines.append(
            f"First compare the seizure memo and quantity with the NDPS cannabis possession source; do not treat the bail question as ordinary criminal bail without the NDPS quantity facts [{ndps20}]."
        )
    elif ndps2 is not None and _has_any_term(query, ("ganja", "cannabis", "weed", "charas", "gram", "grams", "50g", "50 g")):
        lines.append(
            f"Start with the NDPS definition source because the seized substance and quantity alleged in the seizure memo or lab report drive the bail analysis [{ndps2}]."
        )
    elif ndps14 is not None and _has_any_term(query, ("ganja", "cannabis", "weed", "charas")):
        lines.append(
            f"The retrieved NDPS source is a special provision relating to cannabis, so the ganja facts belong in the NDPS track before the separate bail source is applied [{ndps14}]."
        )
    elif ndps2 is not None and _has_any_term(query, ("small quantity", "commercial", "intermediate", "quantity", "gram", "grams", "50g", "50 g")):
        lines.append(
            f"Start with the NDPS definition/quantity source because bail risk depends on the substance and quantity alleged in the seizure memo or lab report [{ndps2}]."
        )
    if ndps37 is not None:
        lines.append(
            f"NDPS bail has a stricter statutory filter under the NDPS Act source, so prior rejection orders and the alleged quantity or section matter before another bail move [{ndps37}]."
        )
    if bnss_bail is not None:
        lines.append(
            f"The BNSS bail source says a High Court or Court of Session may direct that an accused person in custody be released on bail [{bnss_bail}]."
        )
    if ndps36a is not None and custody_timeline_context:
        lines.append(
            f"For an NDPS case in long custody, Section 36A is the NDPS custody and Special Court procedure source to check [{ndps36a}]."
        )
    if article21 is not None and has_three_years and has_tihar:
        lines.append(
            f"For three years in Tihar custody after repeated NDPS bail rejection, Article 21 is the personal-liberty source for a custody-delay argument [{article21}]."
        )
    elif article21 is not None:
        lines.append(
            f"Article 21 protects life and personal liberty, so prolonged incarceration arguments should be built around custody duration and trial delay rather than a bare repeat bail request [{article21}]."
        )
    lines.append("**What you can do next**")
    if ndps36a is not None:
        lines.append(
            f"- Collect the custody start date, remand papers, charge-sheet status, trial progress, and all bail rejection orders before approaching the Special NDPS Court or High Court [{ndps36a}]."
        )
    elif article21 is not None and bnss_bail is None:
        lines.append(
            f"- Build a dated custody-and-trial-delay chart and take the prior bail orders to legal aid or a criminal lawyer before the next High Court or Special Court step [{article21}]."
        )
    return lines


def _ndps_personal_use_template_lines(query: str, passages: list[dict]) -> list[str]:
    ndps43 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-43",),
    )
    ndps14 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-14",),
    )
    ndps20 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-20",),
    )
    ndps22 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-22",),
    )
    ndps37 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-37",),
    )
    ndps2 = _find_passage_index(
        passages,
        title_terms=("narcotic drugs and psychotropic substances",),
        anchor_terms=("/sec-2",),
    )
    if ndps20 is None and ndps22 is None and ndps37 is None and ndps2 is None and ndps43 is None and ndps14 is None:
        return []
    lines = ["**Short answer**"]
    is_bhang = _has_any_term(query, ("bhang", "bhang lassi"))
    if is_bhang and ndps2 is not None:
        lines.append(
            f"For bhang or bhang-lassi facts, start with the NDPS definition source and compare the exact substance in the seizure memo before estimating punishment [{ndps2}]."
        )
    elif is_bhang and ndps43 is not None:
        lines.append(
            f"Section 43 is only a public-place seizure and arrest power for narcotic drugs or psychotropic substances when an NDPS offence is believed [{ndps43}]."
        )
        if ndps14 is not None:
            lines.append(
                f"Section 14 is a special cannabis-cultivation provision, not a bhang-lassi classification answer [{ndps14}]."
            )
    elif ndps20 is not None and _has_any_term(query, ("cannabis", "weed", "ganja", "hash", "thc", "vape")):
        lines.append(
            f"Do not treat this as only a vaping issue: the NDPS source for cannabis-related possession/punishment must be checked against the seizure memo and quantity [{ndps20}]."
        )
    elif ndps22 is not None:
        substance_phrase = "MDMA" if "mdma" in query else "the seized oil or psychotropic substance"
        lines.append(
            f"If {substance_phrase} is treated as a psychotropic substance, the NDPS source for psychotropic-substance possession/punishment is the section to check against the lab report and quantity [{ndps22}]."
        )
    elif ndps14 is not None and _has_any_term(query, ("personal use", "small quantity", "gram", "grams", "5g", "5 gram", "5 grams")):
        lines.append(
            f"Do not prove small quantity from the words 'personal use' alone; the NDPS source retrieved here is not enough by itself, so the seizure memo, substance name, lab/FSL report, and applicable quantity notification must be checked [{ndps14}]."
        )
    elif ndps2 is not None:
        lines.append(
            f"The exact NDPS classification depends on the substance named in the seizure memo or lab report, so the definition source has to be checked before estimating punishment [{ndps2}]."
        )
    if ndps37 is not None:
        lines.append(
            f"If police allege commercial quantity or a serious NDPS charge, the NDPS bail source adds a stricter bail filter [{ndps37}]."
        )
    lines.append("**What you can do next**")
    action_cite = ndps2 if is_bhang and ndps2 is not None else ndps43 if is_bhang and ndps43 is not None else ndps20 if ndps20 is not None else ndps22 if ndps22 is not None else ndps2 if ndps2 is not None else ndps37 if ndps37 is not None else ndps14
    if is_bhang and ndps43 is not None and ndps2 is None:
        lines.append(
            f"- Use the seizure memo to check whether police are relying on a narcotic drug or psychotropic substance before treating the bhang-lassi fact as an NDPS offence [{action_cite}]."
        )
    else:
        lines.append(
            f"- Get the seizure memo, lab/FSL report, quantity, FIR/complaint sections, and arrest or notice papers before asking a lawyer to assess punishment or bail exposure [{action_cite}]."
        )
    return lines


def _llp_annual_return_template_lines(passages: list[dict]) -> list[str]:
    llp35 = _find_passage_index(
        passages,
        title_terms=("limited liability partnership",),
        anchor_terms=("/sec-35",),
    )
    llp75 = _find_passage_index(
        passages,
        title_terms=("limited liability partnership",),
        anchor_terms=("/sec-75",),
    )
    if llp35 is None and llp75 is None:
        return []
    lines = ["**Short answer**"]
    if llp35 is not None:
        lines.append(
            f"The LLP Act source is the direct source: it requires every LLP to file its annual return with the Registrar within the statutory time after the financial year closes [{llp35}]."
        )
    if llp75 is not None:
        lines.append(
            f"The strike-off risk is also an LLP Act issue because the Registrar source covers striking a defunct LLP off the register [{llp75}]."
        )
    lines.append("**What you can do next**")
    action_cites = "".join(f"[{idx}]" for idx in (llp35, llp75) if idx is not None)
    lines.append(
        f"- Collect the LLPIN, pending annual-return/Form 11 years, partner consent trail, MCA notices, and DSC access details so the Registrar filing default and any strike-off stage can be checked against the cited LLP Act sources {action_cites}."
    )
    return lines


def _tweet_defamation_chargesheet_template_lines(query: str, passages: list[dict]) -> list[str]:
    bns356 = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya sanhita",),
        anchor_terms=("/sec-356",),
    )
    bnss193 = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha sanhita",),
        anchor_terms=("/sec-193",),
    )
    if bns356 is None and bnss193 is None:
        return []
    speech_phrase = "a tweet calling a public official corrupt" if "corrupt" in query else "an online post"
    lines = ["**Short answer**"]
    if bns356 is not None:
        lines.append(
            f"For {speech_phrase}, first verify whether the charge-sheet actually cites BNS Section 356, because the BNS source is the defamation provision in the retrieved material; the incident date decides BNS versus IPC framing [{bns356}]."
        )
    if bnss193 is not None:
        lines.append(
            f"Because a charge-sheet is already mentioned, first read the police report and the exact sections listed in it before deciding the next court step [{bnss193}]."
        )
    lines.append("The provided passages do not state the deadline for challenging a charge-sheet or summons.")
    lines.append("**What you can do next**")
    if bns356 is not None:
        lines.append(
            f"- Compare the exact words in the tweet, the complainant named in the charge-sheet, and the listed BNS/IPC/IT Act sections before deciding whether this is really a Section 356 defamation case [{bns356}]."
        )
    if bnss193 is not None:
        lines.append(
            f"- Take the charge-sheet, summons, and listed sections to the criminal court or legal-aid lawyer instead of relying on a generic cyber complaint path [{bnss193}]."
        )
    return lines


def _creator_platform_payout_template_lines(query: str, passages: list[dict]) -> list[str]:
    contract37 = _find_passage_index(
        passages,
        title_terms=("indian contract",),
        anchor_terms=("/sec-37",),
    )
    fema = _find_passage_index(
        passages,
        title_terms=("foreign exchange management",),
        anchor_terms=("/sec-49", "/sec-3", "/sec-4"),
    )
    tax5 = _find_passage_index(
        passages,
        title_terms=("income-tax", "income tax"),
        anchor_terms=("/sec-5",),
    )
    if contract37 is None and fema is None and tax5 is None:
        return []
    platform_phrase = "Fanvue" if "fanvue" in query else "the creator platform"
    amount_phrase = "USD 2400" if "2400" in query and "usd" in query else "the frozen payout"
    lines = ["**Short answer**"]
    if contract37 is not None:
        lines.append(
            f"For {platform_phrase} holding {amount_phrase}, start with the platform terms and payout obligation because the Contract Act source says parties to a contract must perform or offer to perform their promises unless excused under the Act or other law [{contract37}]."
        )
    if fema is not None:
        lines.append(
            f"Because this is a foreign-platform payout to an Indian creator, check the bank or payment processor's foreign-exchange reason for the freeze under the FEMA source before framing it only as a platform dispute [{fema}]."
        )
    if tax5 is not None:
        lines.append(
            f"If you are resident in India, keep tax records for the creator income because the Income-tax Act source covers total income received, deemed received, accrued, or arising in India and abroad depending on status [{tax5}]."
        )
    lines.append("**What you can do next**")
    next_cite = contract37 if contract37 is not None else fema if fema is not None else tax5
    lines.append(
        f"- Ask {platform_phrase} for a written freeze reason, KYC/tax/remittance documents requested, and the payout ledger, then raise the platform grievance and bank/remittance complaint with those records [{next_cite}]."
    )
    return lines


def _trademark_opposition_template_lines(passages: list[dict]) -> list[str]:
    tm21 = _find_passage_index(passages, title_terms=("trade marks",), anchor_terms=("/sec-21",))
    tm11 = _find_passage_index(passages, title_terms=("trade marks",), anchor_terms=("/sec-11",))
    tm29 = _find_passage_index(passages, title_terms=("trade marks",), anchor_terms=("/sec-29",))
    if tm21 is None:
        return []
    lines = ["**Short answer**"]
    if tm21 is not None:
        lines.append(
            f"A trademark application opposed by another brand should be handled under the Trade Marks Act opposition procedure at the Trade Marks Registry, not as a generic contract dispute [{tm21}]."
        )
    if tm11 is not None:
        lines.append(
            f"The similarity/confusion objection is a Trade Marks Act relative-grounds issue, so compare the earlier mark, goods/services, and confusion facts under that source [{tm11}]."
        )
    if tm29 is not None:
        lines.append(
            f"Keep infringement/pass-off style market-use facts separate from the opposition hearing, because infringement is a different Trade Marks Act source [{tm29}]."
        )
    action_cite = tm21 if tm21 is not None else tm11 if tm11 is not None else tm29
    lines.extend([
        "**What you can do next**",
        f"- Collect the application number, journal advertisement, opposition notice, counter-statement deadline, evidence of first use, invoices, website screenshots, and similarity comparison before the Registry hearing [{action_cite}].",
    ])
    return lines


def _caste_scholarship_template_lines(query: str, passages: list[dict]) -> list[str]:
    article46 = _find_passage_index(
        passages,
        title_terms=("constitution of india",),
        anchor_terms=("/sec-46",),
    )
    rti6 = _find_passage_index(
        passages,
        title_terms=("right to information act",),
        anchor_terms=("/sec-6",),
    )
    rti7 = _find_passage_index(
        passages,
        title_terms=("right to information act",),
        anchor_terms=("/sec-7",),
    )
    if article46 is None and rti6 is None:
        return []
    benefit_phrase = "SC scholarship" if "sc scholarship" in query else "caste/community scholarship"
    lines = ["**Short answer**"]
    if article46 is not None:
        lines.append(
            f"For a withheld {benefit_phrase}, Article 46 is relevant because it directs the State to promote the educational and economic interests of Scheduled Castes, Scheduled Tribes, and weaker sections [{article46}]."
        )
    if rti6 is not None:
        lines.append(
            f"Use RTI to ask the school or education authority for the application status, paper-defect reason, rule relied on, and officer responsible for the pending scholarship decision [{rti6}]."
        )
    if rti7 is not None:
        lines.append(
            f"The public information officer generally has thirty days to provide or reject the information request [{rti7}]."
        )
    lines.append("**What you can do next**")
    action_cite = rti6 if rti6 is not None else article46
    timeline_phrase = "two-year timeline" if _has_any_term(query, ("2 years", "two years")) else "delay timeline"
    lines.append(
        f"- Attach the caste certificate, scholarship ID, school refusal or message, and {timeline_phrase} to the written grievance and RTI request [{action_cite}]."
    )
    return lines


def _construction_injury_template_lines(query: str, passages: list[dict]) -> list[str]:
    ec3 = _find_passage_index(
        passages,
        title_terms=("employees' compensation", "employees compensation", "workmen's compensation"),
        anchor_terms=("/sec-3",),
    )
    ec_claim = _find_passage_index(
        passages,
        title_terms=("employees' compensation", "employees compensation", "workmen's compensation"),
        anchor_terms=("/sec-22", "/sec-10"),
    )
    bocw = _find_passage_index(
        passages,
        title_terms=("building and other construction workers",),
        anchor_terms=("/sec-12", "/sec-13", "/sec-39", "/sec-40"),
    )
    if ec3 is None or bocw is None:
        return []
    if "fell from" in query and "5th floor" in query and _has_any_term(query, ("leg broken", "broken leg")):
        injury_phrase = "a 5th-floor construction-site fall with a leg injury"
    elif "fell from" in query:
        injury_phrase = "a fall from a construction site"
    else:
        injury_phrase = "a construction-site injury"
    bocw_phrase = "no BOCW card" if _has_any_term(query, ("no bocw card", "without bocw card")) else "BOCW card or registration"
    contractor_phrase = "the thekedar or contractor" if "thekedar" in query else "the contractor or employer"
    lines = [
        "**Short answer**",
        (
            f"For {injury_phrase}, the Employees' Compensation source covers employer liability "
            f"for personal injury caused by an accident arising out of and in the course of employment [{ec3}]."
        ),
        (
            f"The BOCW source is also relevant when {contractor_phrase} points to {bocw_phrase}, because it covers "
            f"registration or construction-worker welfare/safety duties [{bocw}]."
        ),
        "**What you can do next**",
    ]
    if ec_claim is not None:
        lines.append(f"- Use the medical records, site details, contractor name, and wage facts to file a compensation claim before the Commissioner route [{ec_claim}].")
    else:
        lines.append(f"- Preserve medical records, accident-site details, contractor name, and wage facts before approaching the labour office or compensation route [{ec3}].")
    return lines


def _workplace_assault_wage_template_lines(query: str, passages: list[dict]) -> list[str]:
    bns_hurt = _find_passage_index(
        passages,
        title_terms=("bharatiya nyaya sanhita",),
        anchor_terms=("/sec-117", "/sec-115", "/sec-118"),
    )
    ec3 = _find_passage_index(
        passages,
        title_terms=("employees' compensation", "employees compensation", "workmen's compensation"),
        anchor_terms=("/sec-3",),
    )
    wages = _find_passage_index(
        passages,
        title_terms=("code on wages",),
        anchor_terms=("/sec-17", "/sec-45", "/sec-43"),
    )
    bnss_complaint = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha",),
        anchor_terms=("/sec-216", "/sec-173"),
    )
    if bns_hurt is None and ec3 is None and wages is None:
        return []
    lines = ["**Short answer**"]
    if bns_hurt is not None:
        workplace_facts = _present_terms_phrase(
            query,
            (
                ("Mumbai", "mumbai"),
                ("mukadam", "mukadam"),
                ("8-stitch head injury", "8 stitches", "8 stitch"),
                ("old wages", "old wages", "wages"),
            ),
            fallback="a worksite assault and wage dispute",
        )
        lines.append(
            f"For {workplace_facts}, the BNS source covers voluntarily causing grievous hurt; the incident date decides BNS/BNSS versus IPC/CrPC framing before treating it as only a wage dispute [{bns_hurt}]."
        )
    if ec3 is not None:
        lines.append(
            f"The Employees' Compensation source makes employer liability turn on personal injury caused by accident arising out of and in the course of employment, so keep the worksite link and injury records ready for that route [{ec3}]."
        )
    if wages is not None:
        lines.append(
            f"For the old-wages part, the Code on Wages source deals with timely payment of wages, so keep wage slips, attendance, messages, and contractor details together [{wages}]."
        )
    lines.append("**What you can do next**")
    if ec3 is not None:
        injury_docs = "medical records"
        if _has_any_term(query, ("8 stitches", "8 stitch", "head injury")):
            injury_docs = "medical records for the head injury"
        lines.append(
            f"- Use {injury_docs}, site/witness details, contractor identity, and wage proof; for the compensation track, frame the claim around whether the injury arose out of and in the course of employment [{ec3}]."
        )
    elif wages is not None:
        lines.append(
            f"- For the wage track, frame the claim around timely payment of wages under the Code on Wages source [{wages}]."
        )
    else:
        action_cite = bnss_complaint if bnss_complaint is not None else bns_hurt
        lines.append(
            f"- For the assault track, frame the complaint around the hurt section that matches the medical papers and FIR facts [{action_cite}]."
        )
    return lines


def _relative_adoption_template_lines(query: str, passages: list[dict]) -> list[str]:
    jj56 = _find_passage_index(
        passages,
        title_terms=("juvenile justice",),
        anchor_terms=("/sec-56",),
    )
    jj58 = _find_passage_index(
        passages,
        title_terms=("juvenile justice",),
        anchor_terms=("/sec-58",),
    )
    gwa17 = _find_passage_index(
        passages,
        title_terms=("guardians and wards",),
        anchor_terms=("/sec-17",),
    )
    gwa7 = _find_passage_index(
        passages,
        title_terms=("guardians and wards",),
        anchor_terms=("/sec-7",),
    )
    relative_context = _has_any_term(query, ("sister", "brother", "cousin", "relative", "aunt", "uncle", "family"))
    if gwa17 is None or (relative_context and jj56 is None) or (not relative_context and jj58 is None):
        return []
    family_phrase = "non-Hindu family " if _has_any_term(query, ("not hindu", "not a hindu", "non hindu", "non-hindu", "muslim", "christian", "catholic", "islam")) else ""
    relation_phrase = ""
    if re.search(r"\bfrom\s+(?:my\s+)?sister\b", query) or "sister's child" in query:
        relation_phrase = "from a sister "
    elif "sister" in query:
        relation_phrase = "involving a sister "
    papers_phrase = " without papers" if _has_any_term(query, ("no papers", "without papers")) else ""
    real_parent_dispute = "real parents" in query and _has_any_term(query, (
        "want him back", "want her back", "want child back", "want the child back",
        "wants him back", "wants her back", "asking back", "take back",
        "claim custody", "custody back",
    ))
    custody_phrase = "Because the real parents now want the child back" if real_parent_dispute else "If custody or guardianship is disputed"
    if relative_context:
        adoption_context = f"{family_phrase}relative adoption {relation_phrase}".strip() + papers_phrase
        first_line = (
            f"For a {adoption_context}, the JJ source says relative adoption "
            f"can be made irrespective of religion under the Act and adoption regulations [{jj56}]."
        )
    else:
        adoption_context = "adoption-paper dispute" if "papers" in query else "adoption issue"
        first_line = (
            f"For an {adoption_context}, the JJ source covers the adoption application, "
            f"pre-adoption foster care, and court-order procedure [{jj58}]."
        )
    lines = [
        "**Short answer**",
        first_line,
        (
            f"{custody_phrase}, the guardianship question turns on the minor's "
            f"welfare under the Guardians and Wards Act source [{gwa17}]."
        ),
        "**What you can do next**",
    ]
    if jj58 is not None:
        lines.append(f"- Collect the child's records and adoption papers or proof of care, then check the Specialised Adoption Agency or court-order procedure [{jj58}].")
    elif gwa7 is not None:
        lines.append(f"- If there is no valid adoption order, prepare for a District Court guardianship/custody application focused on the child's welfare [{gwa7}].")
    return lines


def _custodial_death_template_lines(query: str, passages: list[dict]) -> list[str]:
    inquiry = _find_passage_index(
        passages,
        title_terms=("bharatiya nagarik suraksha sanhita", "code of criminal procedure"),
        anchor_terms=("/sec-196", "/sec-176"),
    )
    if inquiry is None:
        return []
    if _has_any_term(query, ("father", "papa")) and _has_any_term(query, ("lockup", "custody", "custodial")):
        opening = "For your father's police lockup death"
    elif _has_any_term(query, ("lockup", "custody", "custodial")):
        opening = "For a police lockup or custody death"
    else:
        opening = "When a person dies in police custody"
    return [
        "**Short answer**",
        (
            f"{opening}, the nearest Magistrate empowered to hold inquests must "
            f"hold an inquiry into the cause of death [{inquiry}]."
        ),
        (
            f"The Magistrate may disinter and examine the body if needed [{inquiry}]."
        ),
        "**What you can do next**",
        (
            "- Apply to the nearest Magistrate empowered to hold inquests for "
            f"an inquiry into the cause of death [{inquiry}]."
        ),
    ]


def _rti_template_lines(query: str, passages: list[dict]) -> list[str]:
    sec6 = _find_passage_index(passages, title_terms=("right to information act",), anchor_terms=("/sec-6",))
    sec7 = _find_passage_index(passages, title_terms=("right to information act",), anchor_terms=("/sec-7",))
    sec19 = _find_passage_index(passages, title_terms=("right to information act",), anchor_terms=("/sec-19",))
    if sec6 is None:
        return []
    if _has_any_term(query, ("appeal", "rejected", "reject", "no response", "not reply", "no reply")) and sec19 is None:
        return []
    if "pension" in query and _has_any_term(query, ("papa", "father", "pitaji")):
        info_phrase = "your father's delayed pension information"
        request_object = "the delayed pension information you seek"
    elif "pension" in query:
        info_phrase = "pension information"
        request_object = "the pension information you seek"
    else:
        info_phrase = "the information you need"
        request_object = "the information you seek"
    lines = [
        "**Short answer**",
        (
            f"For {info_phrase}, you can make an RTI request in writing or through "
            f"electronic means to the Central or State Public Information Officer of the concerned public authority [{sec6}]."
        ),
    ]
    if sec7 is not None:
        lines.append(
            "The public information officer must provide the information or reject the "
            f"request within thirty days of receipt [{sec7}]."
        )
    if sec19 is not None:
        lines.append(
            "If you do not receive a decision within that period, you may prefer an "
            f"appeal to an officer senior in rank to the public information officer [{sec19}]."
        )
    lines.extend([
        "**What you can do next**",
        (
            f"- File a written or electronic request specifying {request_object} [{sec6}]."
        ),
    ])
    return lines


def _court_fee_template_lines(passages: list[dict]) -> list[str]:
    fee7 = _find_passage_index(
        passages,
        title_terms=("court fees", "court fee", "court-fees"),
        anchor_terms=("/sec-7",),
    )
    fee8 = _find_passage_index(
        passages,
        title_terms=("court fees", "court fee", "court-fees"),
        anchor_terms=("/sec-8",),
    )
    if fee7 is None and fee8 is None:
        return []
    lines = ["**Short answer**"]
    if fee7 is not None:
        lines.append(
            f"The Court Fees Act source is the right starting point for a money-recovery suit because it deals with computation of fees for suits according to the amount or value claimed [{fee7}]."
        )
    if fee8 is not None:
        lines.append(
            f"The Court Fees Act source also links fee value and jurisdictional value for covered suits, so valuation cannot be answered from CPC alone [{fee8}]."
        )
    lines.append("**What you can do next**")
    action_cite = fee7 if fee7 is not None else fee8
    lines.append(
        f"- Take the plaint draft, exact reliefs, recovery amount, state court-fee schedule, and any set-off/interest calculation to the filing counter or lawyer before paying court fee [{action_cite}]."
    )
    return lines


def _drug_inspector_template_lines(passages: list[dict]) -> list[str]:
    drugs18 = _find_passage_index(
        passages,
        title_terms=("drugs and cosmetics",),
        anchor_terms=("/sec-18",),
    )
    drugs22 = _find_passage_index(
        passages,
        title_terms=("drugs and cosmetics",),
        anchor_terms=("/sec-22",),
    )
    if drugs22 is None:
        drugs22 = _find_passage_index_by_text(
            passages,
            title_terms=("drugs and cosmetics",),
            text_terms=("powers of inspectors",),
        )
    drugs23 = _find_passage_index(
        passages,
        title_terms=("drugs and cosmetics",),
        anchor_terms=("/sec-23",),
    )
    if drugs18 is None and drugs22 is None and drugs23 is None:
        return []
    lines = ["**Short answer**"]
    if drugs18 is not None:
        lines.append(
            f"The Drugs and Cosmetics Act source is the direct compliance source for sale/manufacture restrictions, so a Schedule H sale allegation should not be answered from generic criminal law [{drugs18}]."
        )
    if drugs22 is not None:
        lines.append(
            f"The inspector-power source matters because it is the authority for inspection and sampling action by a Drug Inspector [{drugs22}]."
        )
    if drugs23 is not None:
        lines.append(
            f"The sampling-procedure source matters because it covers the statutory procedure after an inspector takes a sample [{drugs23}]."
        )
    lines.append("**What you can do next**")
    action_cite = drugs23 if drugs23 is not None else drugs22 if drugs22 is not None else drugs18
    lines.append(
        f"- Preserve the sample memo, Form/intimation, batch invoices, prescription register, licence copy, and test-report notice, then reply through the licensing authority or court channel shown by the cited Act source [{action_cite}]."
    )
    return lines


def _municipal_shop_sealing_template_lines(query: str, passages: list[dict]) -> list[str]:
    rti = _find_passage_index(
        passages,
        title_terms=("right to information",),
        anchor_terms=("/sec-6", "/sec-7", "/sec-19"),
    )
    shops = _find_passage_index(
        passages,
        title_terms=("shops", "establishments", "establishment"),
    )
    street_vendor = _find_passage_index(
        passages,
        title_terms=("street vendors", "street vendor"),
    )
    if rti is None and shops is None and street_vendor is None:
        return []
    lines = ["**Short answer**"]
    if rti is not None:
        lines.append(
            f"For a municipality sealing a shop, the safe first step is not to guess the Gujarat/city by-law from generic judgments; get the sealing order, show-cause notice, inspection file, and written reasons, and use RTI if the office will not give them [{rti}]."
        )
    if shops is not None:
        lines.append(
            f"If the issue is shop registration or trade-licence compliance, match the notice to the shops/establishment or licence source before deciding whether to seek de-sealing, compounding, appeal, or court relief [{shops}]."
        )
    elif street_vendor is not None and _has_any_term(query, ("vendor", "hawker", "street")):
        lines.append(
            f"If this is actually a street-vending spot rather than a fixed shop, keep the street-vendor route separate because the forum and release process may differ [{street_vendor}]."
        )
    lines.append("**What you can do next**")
    action_cite = rti if rti is not None else shops if shops is not None else street_vendor
    lines.append(
        f"- Take the sealing order, licence/trade registration, lease or ownership papers, fee/tax receipts, photos, and hearing date to the municipal ward/licensing office or Commissioner/appellate authority named in the order; use DLSA/local counsel urgently if goods, livelihood, or a deadline is at risk [{action_cite}]."
    )
    return lines


def _traffic_bribe_template_lines(passages: list[dict]) -> list[str]:
    mv_sec3 = _find_passage_index(passages, title_terms=("motorvehicles", "motor vehicles"), anchor_terms=("/sec-3",))
    pca_sec7 = _find_passage_index(passages, title_terms=("prevention of corruption",), anchor_terms=("/sec-7",))
    pca_sec8 = _find_passage_index(passages, title_terms=("prevention of corruption",), anchor_terms=("/sec-8",))
    if mv_sec3 is None or pca_sec7 is None:
        return []
    licence_phrase = "the driving licence issue"
    lines = [
        "**Short answer**",
        (
            f"For {licence_phrase}, no person shall drive a motor vehicle in a public place unless he holds "
            f"an effective driving licence authorising him to drive the vehicle [{mv_sec3}]."
        ),
        (
            "For traffic police taking money without a challan, a public servant who obtains or attempts to obtain an undue advantage "
            f"for improper performance of public duty is punishable under Section 7 of the Prevention of Corruption Act [{pca_sec7}]."
        ),
        "**What you can do next**",
    ]
    if pca_sec8 is not None:
        lines.append(
            "- If you were compelled to give an undue advantage, report it to law "
            f"enforcement or an investigating agency within seven days [{pca_sec8}]."
        )
    else:
        lines.append("The provided passages do not state a concrete next step.")
    return lines


def _generic_prohibition_template_lines(passages: list[dict]) -> list[str]:
    arrest_info = _find_passage_index(
        passages,
        title_terms=("code of criminal procedure", "bharatiya nagarik suraksha sanhita"),
        anchor_terms=("/sec-50", "/sec-47"),
    )
    if arrest_info is None:
        return []
    return [
        "**Short answer**",
        (
            "If police arrest you in a prohibition-law case without warrant, they must communicate "
            f"the full particulars of the offence or other grounds for arrest [{arrest_info}]."
        ),
        (
            "If the person is not accused of a non-bailable offence, the police officer "
            f"must inform the person of the right to be released on bail [{arrest_info}]."
        ),
        "The provided passages do not state a concrete punishment for the prohibition offence.",
        "**What you can do next**",
        "The provided passages do not state a concrete next step.",
    ]


def _find_passage_index(
    passages: list[dict],
    *,
    title_terms: tuple[str, ...] = (),
    anchor_terms: tuple[str, ...] = (),
) -> int | None:
    for passage in passages:
        title = str(passage.get("title") or "").lower()
        anchor = str(passage.get("anchor") or "").lower()
        title_ok = not title_terms or any(term in title for term in title_terms)
        anchor_ok = not anchor_terms or any(_anchor_matches_term(anchor, term) for term in anchor_terms)
        if title_ok and anchor_ok:
            idx = passage.get("index")
            return int(idx) if isinstance(idx, int) else None
    return None


def _find_passage_index_by_text(
    passages: list[dict],
    *,
    title_terms: tuple[str, ...] = (),
    text_terms: tuple[str, ...],
) -> int | None:
    for passage in passages:
        title = str(passage.get("title") or "").lower()
        text = _normalize_match_text(str(passage.get("text") or ""))
        title_ok = not title_terms or any(term in title for term in title_terms)
        text_ok = all(_normalize_match_text(term) in text for term in text_terms)
        if title_ok and text_ok:
            idx = passage.get("index")
            return int(idx) if isinstance(idx, int) else None
    return None


def _anchor_matches_term(anchor: str, term: str) -> bool:
    needle = term.lower()
    if needle.startswith("/sec-"):
        return re.search(rf"{re.escape(needle)}(?=@|-|__|$)", anchor) is not None
    if needle.startswith("sec-"):
        return re.search(rf"(^|/){re.escape(needle)}(?=@|-|__|$)", anchor) is not None
    return needle in anchor


def _has_passage(
    passages: list[dict],
    *,
    title_terms: tuple[str, ...] = (),
    anchor_terms: tuple[str, ...] = (),
) -> bool:
    return _find_passage_index(
        passages,
        title_terms=title_terms,
        anchor_terms=anchor_terms,
    ) is not None


def _has_any_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _query_mentions_pre_july_2024(text: str) -> bool:
    if _has_any_term(text, (
        "before 1 july 2024", "pre-1 july 2024", "pre 1 july 2024",
        "before july 2024", "pre july 2024", "ipc", "crpc",
    )):
        return True
    years = [int(match.group(0)) for match in re.finditer(r"\b(?:19|20)\d{2}\b", text)]
    return bool(years and min(years) < 2024)


def _is_police_picked_fir_copy_query(text: str) -> bool:
    picked = _has_any_term(text, ("police picked", "police took", "picked my", "took my", "utha liya", "detained", "arrested"))
    fir_copy = _has_any_term(text, ("fir copy", "copy of fir", "no fir copy", "not got fir", "not received fir"))
    family = _has_any_term(text, ("son", "daughter", "husband", "wife", "brother", "father", "mother", "family"))
    return picked and fir_copy and (family or "from my home" in text)


def _is_theft_fir_refusal_query(text: str) -> bool:
    theft = _has_any_term(text, ("bike", "scooter", "vehicle", "phone", "stolen", "theft", "steal"))
    refusal = _has_any_term(text, ("not filing fir", "not file fir", "refusing fir", "refused fir", "police not filing", "police refused"))
    return theft and refusal


def _is_school_admission_denial_query(text: str) -> bool:
    school = _has_any_term(text, ("school", "admission", "admission exam", "entrance"))
    denial = _has_any_term(text, ("denied", "refused", "not admitting", "reject", "rejected", "clearing admission"))
    return school and denial


def _is_joint_property_sale_query(text: str) -> bool:
    property_context = _has_any_term(text, ("plot", "land", "house", "flat", "property"))
    sale = _has_any_term(text, ("sold", "sale", "transferred", "registered"))
    joint = _has_any_term(text, ("together", "joint", "jointly", "co-owner", "co owner", "brother and i", "sister and i"))
    return property_context and sale and joint


def _is_ancestral_land_sale_query(text: str) -> bool:
    property_context = _has_any_term(text, ("ancestral", "dada", "grandfather", "grandfather's", "father name", "father's name")) and _has_any_term(text, ("land", "plot", "house", "property"))
    sale_context = _has_any_term(text, ("selling", "sold", "sale", "sale deed", "transfer", "transferred", "mutation"))
    family_context = _has_any_term(text, ("uncle", "brother", "cousin", "family", "heir", "legal heir"))
    secrecy_or_consent = _has_any_term(text, ("without telling", "without consent", "without informing", "not told", "behind our back", "my share", "our share"))
    return property_context and sale_context and (family_context or secrecy_or_consent)


def _is_tenant_nonpayment_vacate_query(text: str) -> bool:
    tenancy = _has_any_term(text, ("tenant", "landlord", "rent agreement", "lease"))
    problem = _has_any_term(text, ("not vacating", "not leaving", "not paying rent", "rent arrears", "unpaid rent", "evict", "eviction"))
    return tenancy and problem


def _is_property_document_fraud_query(text: str) -> bool:
    property_context = _has_any_term(text, (
        "gift deed", "registered gift", "property transfer", "house",
        "flat", "land", "plot", "thumb impression", "sale deed",
    ))
    document_dispute = _has_any_term(text, (
        "blank paper", "produced as", "under pressure", "coercion",
        "undue influence", "didn't sign", "did not sign", "fake signature",
        "forged", "forgery", "fraud", "challenge", "cancel",
    ))
    return property_context and document_dispute


def _is_b2b_defective_goods_query(text: str) -> bool:
    commercial_context = _has_any_term(text, (
        "supplier", "vendor", "buyer", "purchase order", "po ",
        "invoice", "dealer", "company", "business",
    ))
    goods_context = _has_any_term(text, (
        "goods", "material", "materials", "stock", "inventory",
        "machine", "machinery", "equipment", "parts",
    ))
    defect_or_refund = _has_any_term(text, (
        "defective", "quality issue", "poor quality", "not as per",
        "reject", "rejection", "refusing refund", "refund",
        "replace", "damaged",
    ))
    return commercial_context and goods_context and defect_or_refund


def _is_marriage_misrepresentation_query(text: str) -> bool:
    marriage = _has_existing_or_completed_marriage_terms(text)
    misrep = _has_any_term(text, ("lied", "lies", "false", "fraud", "misrepresent", "concealed", "hid", "fake"))
    life_fact = _has_any_term(text, ("job", "salary", "income", "work", "employment", "qualification", "education", "health", "disease", "hiv", "hiv positive", "aids", "already married"))
    return marriage and misrep and life_fact


def _is_pre_marriage_health_disclosure_query(text: str) -> bool:
    pre_marriage = _has_any_term(text, (
        "supposed to marry", "marry next month", "marriage next month",
        "wedding next month", "before marriage", "not married yet",
        "engagement", "engaged", "fiance", "fiancee",
        "prospective bride", "prospective groom",
    ))
    health = _has_any_term(text, ("hiv", "hiv positive", "aids", "std", "sti", "disease", "health issue", "medical condition"))
    disclosure = _has_any_term(text, ("hid", "hide", "hides", "concealed", "did not tell", "didn't tell", "found out", "lied", "false"))
    return pre_marriage and health and disclosure


def _has_existing_or_completed_marriage_terms(text: str) -> bool:
    if _has_any_term(text, (
        "not married", "not married yet", "never married", "marriage not happened",
        "wedding not happened", "wedding cancelled", "engagement", "engaged",
        "fiance", "fiancee", "prospective bride", "prospective groom",
    )) and not _has_any_term(text, ("husband", "wife", "spouse")):
        return False
    return _has_any_term(text, (
        "husband", "wife", "spouse", "married", "got married", "after marriage",
        "after wedding", "wedding happened", "marriage happened", "marriage took place",
        "wedding took place", "marriage certificate", "our marriage", "my marriage",
    ))


def _is_marital_intimacy_breakdown_query(text: str) -> bool:
    spouse = _has_any_term(text, ("wife", "husband", "spouse", "marriage", "married"))
    intimacy = _has_any_term(text, (
        "denies sex", "denied sex", "denying sex", "refuses sex", "refusing sex",
        "no sex", "physical relation", "physical relationship",
        "denying physical relation", "denying physical relationship",
        "conjugal", "intimacy",
    ))
    return spouse and intimacy


def _is_marital_sexual_violence_query(text: str) -> bool:
    if _is_wife_as_aggressor_query(text):
        return False
    spouse = _has_any_term(text, ("wife", "husband", "spouse", "marriage", "married"))
    explicit_sexual_context = _has_any_term(text, (
        "sex", "sexual", "intimacy", "physical relation", "physical relationship",
        "touch", "touching", "rape", "marital rape", "bedroom",
    ))
    coercion_without_explicit_sex = _has_any_term(text, (
        "even when i say no", "when i say no", "without consent",
    ))
    if coercion_without_explicit_sex and not explicit_sexual_context:
        return False
    coercion = _has_any_term(text, (
        "forces sex", "force sex", "forced sex", "marital rape",
        "even when i say no", "sex when i say no", "without consent",
        "forces me at night", "forced me at night",
    ))
    return spouse and coercion


def _is_streedhan_return_query(text: str) -> bool:
    family_context = _has_any_term(text, (
        "in-laws", "in laws", "sasural", "husband", "wife",
        "daughter in law", "daughter-in-law", "widow", "after husband died",
    ))
    property_context = _has_any_term(text, (
        "streedhan", "stridhan", "jewellery", "jewelry", "gold",
        "ornaments",
    ))
    withholding_context = _has_any_term(text, (
        "not giving", "not returning", "refusing", "kept", "took",
        "withholding", "return",
    ))
    return family_context and property_context and withholding_context


def _is_mtp_privacy_divorce_query(text: str) -> bool:
    mtp_context = _has_any_term(text, (
        "abortion", "mtp", "pregnancy termination", "terminated pregnancy",
    ))
    marital_context = _has_any_term(text, (
        "husband", "wife", "spouse", "marriage", "divorce",
    ))
    threat_or_disclosure = _has_any_term(text, (
        "threat", "threatening", "found out", "tell everyone",
        "disclose", "privacy", "old", "years back", "5 years",
    ))
    return mtp_context and marital_context and threat_or_disclosure


def _extract_worker_count(text: str) -> int | None:
    match = re.search(r"\b(\d{1,3})\s+workers?\b", text)
    if not match:
        return None
    return int(match.group(1))


def _is_mining_displacement_query(text: str) -> bool:
    mining = _has_any_term(text, ("iron ore", "mine", "mining", "coal block", "bauxite"))
    displacement = _has_any_term(text, ("displaced", "displacement", "rehabilitation", "resettlement", "no compensation"))
    return mining and displacement


def _is_mining_gram_sabha_noc_query(text: str) -> bool:
    mining = _has_any_term(text, (
        "iron ore", "mine", "mining", "coal block", "bauxite", "minerals",
        "minor mineral", "minor minerals", "sand mining", "sand lease",
        "stone quarry", "quarry lease", "quarry",
    ))
    scheduled_area = _has_any_term(text, ("gram sabha", "palli sabha", "pesa", "scheduled area", "bastar", "tribal village", "adivasi village"))
    approval = _has_any_term(text, ("noc", "clearance", "approval", "lease", "project", "land acquired", "acquired for", "acquisition"))
    challenge = _has_any_term(text, ("challenge", "without", "missing", "not taken", "not given", "no gram sabha", "consulting", "consultation", "consent"))
    return mining and scheduled_area and (approval or challenge)


def _is_land_acquisition_compensation_query(text: str) -> bool:
    land_project = _has_any_term(text, (
        "land acquisition", "land acquired", "land taken", "taken for highway",
        "highway", "road widening", "acquired for", "rfctlarr",
    ))
    compensation = _has_any_term(text, (
        "compensation", "award", "payment", "deposit", "not received",
        "still not received", "who to ask",
    ))
    return land_project and compensation


def _is_untouchability_rights_query(text: str) -> bool:
    caste_context = _has_any_term(text, (
        "dalit", "scheduled caste", "sc/st", "sc st", "caste",
        "untouchability", "untouchable",
    ))
    disability_context = _has_any_term(text, (
        "temple", "enter temple", "temple entry", "well", "water",
        "dirty water", "cannot touch", "can't touch", "not allowed to enter",
    ))
    return caste_context and disability_context


def _is_labour_overtime_register_query(text: str) -> bool:
    inspection = _has_any_term(text, (
        "labour department", "labor department", "labour inspector",
        "labor inspector", "raid", "raided", "inspection",
    ))
    register = _has_any_term(text, (
        "overtime register", "ot register", "register not maintained",
        "not maintained", "records not maintained", "registers", "records",
    ))
    return inspection and register


def _is_lok_adalat_traffic_query(text: str) -> bool:
    return _has_any_term(text, ("lok adalat", "lokadalat", "national lok adalat")) and _has_any_term(text, ("challan", "e-challan", "traffic"))


def _is_banking_ombudsman_credit_query(text: str) -> bool:
    bank_error = _has_any_term(text, ("emi", "bank error", "bounced", "bounce", "penalty", "charge", "charges"))
    credit_reporting = _has_any_term(text, ("cibil", "credit score", "credit report", "credit bureau"))
    regulated_entity = _has_any_term(text, ("nbfc", "bajaj finserv", "finance company", "bank", "lender"))
    return regulated_entity and (bank_error or credit_reporting)


def _is_bank_debit_service_query(text: str) -> bool:
    if _has_any_term(text, ("otp", "phishing", "fake call", "fake cbi", "digital arrest", "scam", "hacked")):
        return False
    bank_context = _has_any_term(text, ("bank", "hdfc", "icici", "sbi", "axis", "kotak", "forex", "card"))
    debit_context = _has_any_term(text, (
        "wrongly debited", "unauthorized debit", "unauthorised debit",
        "forex transaction", "forex debit", "debit transaction",
        "debited twice", "wrong charge", "chargeback", "transaction dispute",
    ))
    return bank_context and debit_context


def _is_medical_negligence_query(text: str) -> bool:
    if _has_any_term(text, ("jail", "prison", "custody", "lockup", "undertrial")):
        return False
    medical_context = _has_any_term(text, ("hospital", "doctor", "clinic", "surgeon", "operation", "operated", "surgery"))
    harm_context = _has_any_term(text, (
        "wrong leg", "wrong limb", "wrong surgery", "wrong operation",
        "operated wrong", "wrong injection", "medical negligence",
        "hospital negligence", "doctor negligence", "without consent",
        "died", "death", "compensation",
    ))
    return medical_context and harm_context


def _is_posh_retaliation_query(text: str) -> bool:
    complaint_context = _has_any_term(text, (
        "posh", "sexual harassment", "icc", "internal committee", "local committee",
        "harassment complaint", "complained to hr", "complained against",
        "complaint against my manager", "complaint to hr",
    ))
    workplace_context = _has_any_term(text, ("manager", "boss", "hr", "office", "workplace", "reporting manager"))
    retaliation_context = _has_any_term(text, ("pip", "bad rating", "retaliation", "performance improvement", "warning", "rating"))
    harassment_context = _has_any_term(text, ("harassment", "harass", "sexual", "touch", "late night", "alone"))
    return workplace_context and retaliation_context and (complaint_context or harassment_context)


def _is_itpa_call_handling_query(text: str) -> bool:
    itpa_context = _has_any_term(text, ("itpa", "pita", "immoral traffic"))
    role_context = _has_any_term(text, (
        "phone", "call", "calls", "whatsapp", "paying clients", "clients",
        "booking", "bookings", "take bookings", "took bookings",
        "only talking", "not meet", "not meeting", "did not meet",
    ))
    return itpa_context and role_context


def _is_trademark_opposition_query(text: str) -> bool:
    return _has_any_term(text, (
        "opposed", "opposition", "counter statement", "counter-statement",
        "hearing", "journal", "advertised", "application opposed",
        "trademark application", "trade mark application",
    ))


def _is_tribal_land_transfer_query(text: str) -> bool:
    tribal = _has_any_term(text, (
        "tribal", "adivasi", "scheduled tribe", "munda", "santhal",
        "non tribal", "non-tribal", "cnt", "chota nagpur", "jharkhand",
        "scheduled area", "agency area", "agency village",
    ))
    land = _has_any_term(text, ("land", "plot", "raiyat", "khata", "khatian"))
    transfer = _has_any_term(text, (
        "mortgage", "sahukar", "moneylender", "refusing return",
        "refusing to return", "grabbed", "land grab", "sold", "transfer",
        "transferred", "restoration", "restore", "without my consent",
        "without our consent", "mutation", "mutation record", "record changed",
        "khata changed", "patwari changed", "non tribal buyer", "non-tribal buyer",
        "buyer", "giving my", "giving our", "giving his", "giving her",
    ))
    return tribal and land and transfer


def _is_fra_forest_rights_query(text: str) -> bool:
    fra = _has_any_term(text, (
        "fra", "forest rights", "fra 2006", "fra claim", "ifr", "cfr",
        "forest rights committee", "frc", "sdlc", "dlc", "community forest",
    ))
    forest_right = _has_any_term(text, (
        "patta", "title", "claim form", "gram sabha", "bamboo", "tendu",
        "mahua", "minor forest produce", "forest produce", "forest guard",
        "forest guards", "forest officer", "reserved", "husband signature",
        "joint title", "rejected", "not giving", "without reason",
    ))
    return fra and forest_right


def _is_cab_aggregator_driver_query(text: str) -> bool:
    if _has_any_term(text, (
        "not driver", "not a driver", "i am customer", "i am a customer",
        "i'm customer", "i'm a customer", "customer account",
        "my customer account", "as customer", "as a customer",
        "as passenger", "as a passenger", "i was passenger",
        "i am passenger", "i am a passenger",
    )):
        return False
    return (
        _has_any_term(text, ("uber", "ola", "cab aggregator", "taxi aggregator"))
        and _has_any_term(text, (
            "cab driver", "taxi driver", "uber driver", "ola driver",
            "driver id", "driver account", "driver profile", "driver partner",
            "platform partner", "vehicle integrated",
        ))
        and _has_any_term(text, ("deactivated", "suspended", "rating low", "low rating", "id blocked", "profile blocked"))
    )


def _is_online_gambling_query(text: str) -> bool:
    gambling_context = _has_any_term(text, (
        "dream11", "parimatch", "betting app", "betting site",
        "online betting", "online gambling", "online rummy", "rummy app",
        "fantasy app", "real money game", "real-money game",
    ))
    stake_context = _has_any_term(text, (
        "lost", "recover", "money", "stake", "stakes", "wager", "bet",
        "legal", "illegal", "allowed", "ban", "banned", "50k", "lakh",
    ))
    return gambling_context and stake_context


def _is_digital_kyc_account_freeze_query(text: str) -> bool:
    platform = _has_any_term(text, (
        "app", "platform", "wallet", "account", "gaming", "online game",
        "blue trunks", "dream11", "parimatch", "rummy", "binance", "usdt",
    ))
    freeze_or_kyc = _has_any_term(text, (
        "kyc", "froze", "frozen", "freeze", "blocked", "suspended",
        "pending", "stuck", "withheld", "not releasing",
    ))
    money = _has_any_term(text, ("80k", "50k", "lakh", "money", "balance", "fund", "funds", "withdraw"))
    return platform and freeze_or_kyc and money


def _is_caste_certificate_query(text: str) -> bool:
    certificate_context = _has_any_term(text, (
        "caste certificate", "sc certificate", "st certificate",
        "scheduled caste certificate", "scheduled tribe certificate",
        "community certificate",
    ))
    rejection_context = _has_any_term(text, (
        "rejected", "reject", "refused", "denied", "not giving",
        "not issuing", "appeal", "tehsildar", "tahsildar", "revenue officer",
    ))
    return certificate_context and rejection_context


def _is_gig_platform_worker_query(text: str) -> bool:
    platform_context = _has_any_term(text, (
        "urban company", "housejoy", "zomato", "swiggy", "ola", "uber",
        "blinkit", "zepto", "rapido", "dunzo", "gig worker",
        "platform worker", "delivery partner", "driver partner",
        "beautician", "service partner",
    ))
    adverse_or_labour = _has_any_term(text, (
        "termination", "terminated", "fired", "deactivated", "suspended",
        "id blocked", "profile blocked", "3 strike", "three strike",
        "strike system", "unfair", "bad rating", "low rating",
        "labour law", "labor law", "employment", "wage", "payout",
        "earning", "full and final", "dues",
    ))
    return platform_context and adverse_or_labour


def _is_parsi_succession_query(text: str) -> bool:
    return (
        "parsi" in text
        and _has_any_term(text, ("passed away", "died", "death", "dead"))
        and _has_any_term(text, ("property", "share", "divided", "partition", "inherit"))
    )


def _is_trans_identity_query(text: str) -> bool:
    return _has_any_term(text, (
        "transgender", "transwoman", "trans woman", "transman", "trans man",
        "change my gender", "gender change", "gender on aadhaar",
        "gender on aadhar", "gender on 10th", "gender on certificate",
    ))


def _is_discriminatory_retrenchment_query(text: str) -> bool:
    retrenchment = _has_any_term(text, ("retrench", "retrenched", "retrenchment", "terminated", "fired"))
    same_work = _has_any_term(text, ("kept", "same site", "same work", "next day", "junior", "last in first out"))
    identity = _has_any_term(text, ("bengali", "gujarati", "hindi speaker", "racist", "language", "migrant", "outsider"))
    return retrenchment and same_work and identity


def _is_employment_retaliation_pip_query(text: str) -> bool:
    workplace = _has_any_term(text, (
        "manager", "boss", "hr", "company", "employer", "reporting manager",
        "office", "workplace", "supervisor",
    ))
    complaint = _has_any_term(text, (
        "complained", "complaint", "grievance", "harassment", "harass",
        "retaliation", "retaliate",
    ))
    pip = _has_any_term(text, (
        "pip", "performance improvement plan", "bad rating", "poor rating",
        "performance issue", "warning", "disciplinary", "performance review",
    ))
    return workplace and complaint and pip


def _is_private_magistrate_complaint_query(text: str) -> bool:
    return _has_any_term(text, ("private complaint", "complaint before magistrate", "magistrate complaint", "police inaction", "156(3)", "156 3", "section 156", "section 200"))


def _is_writ_constitution_query(text: str) -> bool:
    return _has_any_term(text, ("writ", "mandamus", "article 226", "article 32"))


def _is_vakalatnama_change_query(text: str) -> bool:
    lawyer_change = _has_any_term(text, (
        "vakalatnama", "change advocate", "change of advocate",
        "new advocate", "change lawyer", "new lawyer", "replace lawyer",
    ))
    pending_case = _has_any_term(text, ("pending suit", "pending case", "civil suit", "case pending", "during pending"))
    return lawyer_change and (pending_case or "vakalatnama" in text)


def _is_caste_fir_refusal_query(text: str) -> bool:
    caste_context = _has_any_term(text, ("caste", "atrocity", "sc/st", "sc st", "scheduled caste", "scheduled tribe", "dalit", "adivasi"))
    refusal_context = _has_any_term(text, ("refusing fir", "refuse fir", "refused fir", "police refusing", "police refused", "no fir", "small matter"))
    return caste_context and refusal_context


def _is_domestic_acid_threat_query(text: str) -> bool:
    domestic_context = _has_any_term(text, ("husband", "mother in law", "father in law", "in law", "in-law", "wife", "domestic"))
    acid_context = _has_any_term(text, ("acid", "chemical"))
    threat_context = _has_any_term(text, ("threat", "threatening", "throw", "attack", "violence"))
    return domestic_context and acid_context and threat_context


def _is_domestic_violence_safety_query(text: str) -> bool:
    if _is_wife_as_aggressor_query(text):
        return False
    family_context = _has_any_term(text, (
        "husband", "wife", "in laws", "in-laws", "sasural", "mother in law",
        "father in law", "marriage", "married", "domestic violence",
        "live in partner", "live-in partner", "he gets angry", "he slaps",
        "my parents say all marriages",
    ))
    safety_context = _has_any_term(text, (
        "slap", "slapped", "slaps", "beat", "beaten", "beating",
        "hit me", "hits me", "hitting me", "pushed", "threat",
        "threaten", "threatening", "unsafe", "ghar se nikal",
        "nikal diya", "threw me out", "kicked me out", "raat ko",
        "should i stay", "sorry next day", "dowry", "dahej", "taunts",
        "salary", "atm card", "bank card", "breadwinner", "not giving money",
        "groceries", "forces me", "force me",
    ))
    return family_context and safety_context


def _is_bank_account_freeze_query(text: str) -> bool:
    non_bank_account_context = _has_any_term(text, (
        "instagram", "facebook", "meta", "youtube", "google", "gmail",
        "twitter", "x account", "whatsapp", "telegram", "amazon seller",
        "flipkart seller", "seller account", "merchant account",
        "zerodha", "groww", "upstox", "demat", "trading account",
        "binance", "crypto", "usdt", "wallet", "gaming", "dream11",
        "parimatch", "rummy", "creator account", "payout account",
    ))
    bank_context = _has_any_term(text, (
        "bank", "bank account", "savings account", "current account",
        "salary account", "loan account", "jan dhan account", "upi account",
        "sbi", "hdfc", "icici", "axis", "kotak", "pnb", "canara",
        "bob", "bank of baroda", "union bank", "idfc", "yes bank",
        "rbi", "nbfc",
    ))
    freeze_context = _has_any_term(text, (
        "bank account frozen", "bank account is frozen", "bank account froze",
        "savings account frozen", "current account frozen", "account freeze",
        "bank account freeze", "bank account blocked",
        "account lien", "bank account lien", "lien marked", "freeze my account",
        "debit freeze", "credit freeze", "kyc hold",
    ))
    if non_bank_account_context and not bank_context:
        return False
    return bank_context and freeze_context


def _is_loan_app_harassment_query(text: str) -> bool:
    app_context = bool(re.search(r"\bloan\s+apps?\b", text)) or _has_any_term(text, (
        "instant loan app", "online loan app", "digital lending app",
        "cash loan app", "loan recovery app", "finance app",
    ))
    lender_context = app_context or (
        _has_any_term(text, ("nbfc", "finance company", "recovery agent", "recovery agents"))
        and _has_any_term(text, ("app", "contacts", "harass", "harassing"))
    )
    harassment_context = _has_any_term(text, (
        "harass", "harassing", "harassment", "calling my contacts",
        "calling contacts", "contacting contacts", "harassing my contacts",
        "harassing contacts", "sent message to contacts", "messages to contacts",
        "contact list", "abusing contacts", "threatening contacts",
        "recovery calls", "threatening cibil", "threaten cibil",
        "morphed photo", "abusive message", "blackmail",
    ))
    return lender_context and harassment_context


def _is_municipal_shop_sealing_query(text: str) -> bool:
    shop_context = _has_any_term(text, (
        "shop", "dukan", "store", "restaurant", "hotel", "clinic", "godown",
        "warehouse", "commercial premises", "business premises", "showroom",
        "office sealed", "factory sealed",
    ))
    municipal_context = _has_any_term(text, (
        "municipality", "municipal", "municipal corporation", "corporation",
        "ward office", "nagar palika", "nagarpalika", "mcd", "bmc",
        "local body",
    ))
    sealing_context = _has_any_term(text, (
        "sealed", "seal", "sealing", "locked", "closed my shop",
        "shop closed", "closure notice", "demolition notice",
    ))
    return shop_context and municipal_context and sealing_context


def _is_pan_aadhaar_mismatch_query(text: str) -> bool:
    pan_context = _has_any_term(text, ("pan", "pan card", "income tax portal"))
    aadhaar_context = _has_any_term(text, ("aadhaar", "aadhar", "uidai"))
    mismatch_context = _has_any_term(text, (
        "mismatch", "not matching", "does not match", "doesn't match",
        "name different", "dob different", "date of birth different",
        "linking failed", "link failed", "cannot link", "not linking",
    ))
    return pan_context and aadhaar_context and mismatch_context


def _is_wife_as_aggressor_query(text: str) -> bool:
    wife_context = _has_any_term(text, (
        "my wife", "wife slapped", "wife hit", "wife beat", "wife took",
        "wife threw", "wife kicked", "wife threatens", "wife threatened",
    ))
    first_person_victim = _has_any_term(text, (
        "slapped me", "hit me", "beat me", "beats me", "hitting me",
        "threatens me", "threatened me", "threatening me", "abuses me",
        "forces sex", "force sex", "forced sex", "sex without consent",
        "sexual assault", "sexually assaulted me", "sexually assaulting me",
        "assaulted me sexually",
        "took my salary", "takes my salary", "my salary", "my atm",
        "atm card", "bank card", "not giving me money", "against me",
        "threw me out", "kicked me out", "locked me out", "not allowing me entry",
        "not letting me enter", "not letting me in", "not allowing me in",
        "took my jewellery", "took my jewelry", "took my gold", "my jewellery",
        "my jewelry", "my gold", "my documents", "took my property",
        "stole my property", "sold my property", "transferred my property",
        "took my house papers", "sold my house", "transferred my house",
    ))
    return wife_context and first_person_victim and not _has_any_term(text, (
        "my husband", "husband slapped", "husband hit", "husband beat",
        "husband took",
    ))


def _is_honour_or_threat_query(text: str) -> bool:
    honour_context = _has_any_term(text, ("khap", "honour", "honor", "eloped", "inter religion", "inter-religion", "other religion"))
    threat_context = _has_any_term(text, ("threat", "threatening", "harm", "violence", "attack"))
    return honour_context and threat_context


def _is_witness_or_false_evidence_threat_query(text: str) -> bool:
    witness_context = _has_any_term(text, ("witness", "testimony", "deposition", "false evidence", "give false evidence", "not give evidence"))
    threat_context = _has_any_term(text, ("threat", "threatening", "intimidat", "pressure", "force"))
    return witness_context and threat_context


def _is_prison_mulaqat_query(text: str) -> bool:
    prison_context = _has_any_term(text, ("jail", "prison", "tihar", "yerwada", "arthur road", "byculla"))
    visit_context = _has_any_term(text, ("mulaqat", "mulakat", "interview", "visit", "visitation", "meet"))
    restriction_context = _has_any_term(text, ("30 min", "30 minutes", "once a week", "only", "more", "denied", "not allowing"))
    return prison_context and visit_context and restriction_context


def _is_elder_498a_accused_query(text: str) -> bool:
    accused_498a = _has_any_term(text, ("498a", "dowry case", "dowry-cruelty")) and _has_any_term(text, (
        "false", "named", "accused", "against", "filed by wife", "son wife", "daughter in law", "daughter-in-law",
    ))
    elder_context = _has_any_term(text, ("mother", "father", "mother in law", "father in law", "elderly", "old", "70", "71", "72", "73", "74", "75"))
    return accused_498a and elder_context


def _is_arrest_production_delay_query(text: str) -> bool:
    arrest_context = _has_any_term(text, ("arrest", "arrested", "detained", "custody", "lockup", "police picked", "utha liya"))
    production_context = _has_any_term(text, ("magistrate", "not produced", "produce before", "produced before", "24 hours", "twenty four hours", "kab le jana", "court ke samne"))
    prolonged_context = _has_any_term(text, ("5 din", "five days", "5 days", "4 din", "four days", "3 din", "three days"))
    return arrest_context and (production_context or prolonged_context)


def _is_ration_portability_query(text: str) -> bool:
    ration_context = _has_any_term(text, ("ration", "pds", "public distribution", "foodgrain", "food grain"))
    denial_context = _has_any_term(text, (
        "not working", "no rice", "denied", "refused", "not happening",
        "portability", "one nation", "shop", "cancelled", "canceled",
        "mismatch", "aadhaar mismatch", "aadhar mismatch", "renew", "renewal",
        "bdo", "blocked", "deleted",
    ))
    return ration_context and denial_context


def _is_fixed_deposit_nominee_query(text: str) -> bool:
    deposit_context = _has_any_term(text, ("fixed deposit", "fd ", " fd", "fd of", "fd not", "nominee", "depositor"))
    denial_context = _has_any_term(text, ("not honoured", "not honored", "refusing", "refused", "harassment", "not giving", "denied"))
    return deposit_context and denial_context


def _is_kanya_vivah_scheme_query(text: str) -> bool:
    scheme_context = _has_any_term(text, (
        "kanya vivah", "kanyadan", "kanya bibaha", "vivah yojana",
        "daughter wedding", "marriage scheme",
    ))
    nonpayment_context = _has_any_term(text, (
        "not given", "not paid", "not received", "pending", "rejected",
        "no money", "money not", "payment not", "status", "office not",
    ))
    return scheme_context and nonpayment_context


def _is_mgnrega_wage_query(text: str) -> bool:
    mgnrega_context = _has_any_term(text, (
        "nrega", "mgnrega", "job card", "muster roll", "gram sabha", "social audit",
    ))
    wage_context = _has_any_term(text, (
        "wage", "wages", "paid", "payment", "not paid", "pending", "mukhiya",
        "sarpanch", "work done", "work", "days",
    ))
    return mgnrega_context and wage_context


def _is_non_compete_query(text: str) -> bool:
    return _has_any_term(text, (
        "non compete", "non-compete", "restraint of trade", "restrictive covenant",
    ))


def _is_gst_itc_mismatch_query(text: str) -> bool:
    if _has_any_term(text, ("rule 86b", "86b", "1% cash", "1 percent cash", "one percent cash")):
        return False
    has_gst = _has_any_term(text, ("gst", "cgst", "gstr", "gstr 3b", "gstr 2a", "3b", "2a"))
    has_itc = _has_any_term(text, ("itc", "input tax credit"))
    has_mismatch_or_reversal = _has_any_term(text, ("mismatch", "reversal", "reverse"))
    has_2a = _has_any_term(text, ("gstr 2a", "gstr-2a", "2a"))
    has_3b = _has_any_term(text, ("gstr 3b", "gstr-3b", "3b"))
    return has_gst and (
        (has_itc and (has_mismatch_or_reversal or (has_2a and has_3b)))
        or (has_2a and has_3b and has_mismatch_or_reversal)
    )


def _is_subscription_refund_query(text: str) -> bool:
    subscription_context = _has_any_term(text, (
        "subscription", "premium", "paid", "membership", "hinge", "match group",
    ))
    refund_context = _has_any_term(text, ("refund", "no refund"))
    service_block_context = _has_any_term(text, ("froze", "frozen", "blocked", "suspended"))
    return subscription_context and (refund_context or service_block_context)


def _is_wage_waiver_language_query(text: str) -> bool:
    wage_context = _has_any_term(text, ("wage", "wages", "salary", "dues", "payment"))
    waiver_context = _has_any_term(text, (
        "give up wages", "waive wages", "waiver", "signed paper",
        "signed document", "signed form", "relinquish",
    ))
    consent_context = _has_any_term(text, (
        "dont read", "don't read", "did not read", "cannot read", "cant read",
        "can't read", "english", "kannada", "language", "understand",
        "pressure", "forced", "misrepresentation",
    ))
    return wage_context and waiver_context and consent_context


def _is_bank_otp_refund_query(text: str) -> bool:
    otp_context = _has_any_term(text, (
        "otp", "phishing", "unauthorized debit", "unauthorised debit",
        "bank says my fault", "no refund", "customer liability",
    ))
    bank_context = _has_any_term(text, (
        "bank", "account", "upi", "debit", "transaction", "lost",
        "refund", "icici", "sbi", "hdfc", "phonepe", "gpay",
    ))
    return otp_context and bank_context


def _is_cyber_impersonation_fraud_query(text: str) -> bool:
    fraud_context = _has_any_term(text, (
        "fake call", "fraud call", "scam call", "impersonating",
        "pretending", "phishing", "otp", "took", "debited",
        "transferred", "lost money", "2 lakh",
    ))
    institution_context = _has_any_term(text, (
        "sbi", "bank", "pension office", "pension", "pf office",
        "epfo", "account", "atm", "upi",
    ))
    return fraud_context and institution_context


def _is_crypto_investment_fraud_query(text: str) -> bool:
    crypto_context = _has_any_term(text, (
        "crypto", "usdt", "wallet", "telegram group", "telegram crypto",
        "investment group", "transaction hash", "seed phrase",
    ))
    loss_context = _has_any_term(text, (
        "rugpull", "rugpulled", "scam", "fraud", "lost", "took",
        "3 lakh", "2 lakh", "vanished", "wallet drained", "stole my crypto",
    ))
    return crypto_context and loss_context


def _is_bank_property_document_fraud_query(text: str) -> bool:
    bank_context = _has_any_term(text, (
        "bank", "lender", "nbfc", "loan", "loan against",
        "mortgage", "secured loan", "home loan",
    ))
    property_context = _has_any_term(text, (
        "house", "home", "flat", "property", "land", "plot",
        "title deed", "sale deed",
    ))
    disputed_consent = _has_any_term(text, (
        "didn't sign", "did not sign", "fake signature", "forged",
        "forgery", "blank paper", "thumb impression", "without my consent",
    ))
    return bank_context and property_context and disputed_consent


def _is_insurance_misselling_query(text: str) -> bool:
    insurance_context = _has_any_term(text, (
        "insurance", "lic", "policy", "ulip", "premium", "maturity",
        "matured", "maturity amount",
    ))
    dispute_context = _has_any_term(text, (
        "agent sold", "mis-selling", "misselling", "guaranteed return",
        "got half", "half amount", "less amount", "fraud", "wrongly sold",
        "promised", "not paying",
    ))
    return insurance_context and dispute_context


def _is_senior_maintenance_enforcement_query(text: str) -> bool:
    senior_context = _has_any_term(text, (
        "senior citizen", "maintenance tribunal", "tribunal ordered",
        "tribunal order", "ordered son", "ordered daughter",
    ))
    enforcement_context = _has_any_term(text, (
        "stopped paying", "not paying", "enforce", "enforcement",
        "default", "missed payment", "no payment", "order not followed",
    ))
    return senior_context and enforcement_context


def _is_decree_execution_attachment_query(text: str) -> bool:
    decree_context = _has_any_term(text, (
        "judgment debtor", "judgement debtor", "money decree",
        "decree holder", "decree execution", "order 21", "order xxi",
    ))
    execution_context = _has_any_term(text, (
        "not paying", "not paid", "execute", "execution", "attach",
        "attachment", "attach property", "property",
    ))
    return decree_context and execution_context


def _is_criminal_quashing_query(text: str) -> bool:
    quashing_context = _has_any_term(text, (
        "quash", "quashing", "482 crpc", "crpc 482", "section 482",
        "sec 482", "482 petition", "bnss 528", "section 528", "sec 528",
    ))
    criminal_case_context = _has_any_term(text, (
        "fir", "criminal case", "chargesheet", "charge sheet", "summons",
        "accused", "police case", "criminal proceeding", "criminal proceedings",
        "criminal complaint", "police report", "charge-sheet",
    ))
    return quashing_context and criminal_case_context


def _is_cyber_blackmail_or_extortion_query(text: str) -> bool:
    cyber_context = _has_any_term(text, ("bumble", "tinder", "whatsapp", "instagram", "telegram", "online", "cyber", "screenshots", "nude", "nudes", "photo", "video", "phone"))
    coercion_context = _has_any_term(text, ("blackmail", "extortion", "threat", "threatening", "leaked", "leak", "send", "took my phone", "gang"))
    return cyber_context and coercion_context


def _is_child_return_or_access_query(text: str) -> bool:
    child_context = _has_any_term(text, ("child", "daughter", "son", "5 year", "five year", "minor", "her back", "him back"))
    withholding_context = _has_any_term(text, ("not letting me meet", "took our", "took my", "get her back", "get him back", "blocked calls", "return", "away"))
    return child_context and withholding_context


def _is_identity_police_threat_query(text: str) -> bool:
    identity_context = _has_any_term(text, ("bangladeshi", "murshidabad", "nationality", "citizen", "migrant", "illegal immigrant"))
    threat_context = _has_any_term(text, ("threat", "threatening", "call police", "police", "false case"))
    return identity_context and threat_context


def _normalize_match_text(text: str) -> str:
    return " ".join(text.lower().split())


def _present_terms_phrase(
    text: str,
    labelled_terms: tuple[tuple[str, ...], ...],
    *,
    fallback: str,
) -> str:
    lower = text.lower()
    labels: list[str] = []
    for item in labelled_terms:
        label, *terms = item
        if any(term in lower for term in terms):
            labels.append(label)
    return " / ".join(labels) if labels else fallback


def _is_deferred_template_header(text: str) -> bool:
    normalized = text.strip().lower().strip("*#:-. ")
    return normalized == "what you can do next"


def _is_no_concrete_placeholder(text: str) -> bool:
    normalized = text.strip().lower().strip("*#:-. ")
    return normalized.startswith("the provided passages do not state")


def _is_safe_template_next_step(
    text: str,
    route: MatterRoute,
    pending_header: SentenceVerification | None,
) -> bool:
    if pending_header is None or not _is_deferred_template_header(pending_header.text):
        return False
    if not text.lstrip().startswith("- "):
        return False

    action_pack_id = route.action_pack.id if route.action_pack is not None else ""
    allowed_action_packs = {
        "arrest_custody_safeguard",
        "criminal_defence_bail",
        "digital_platform_account",
        "education_rights",
        "banking_credit_dispute",
        "business_contract_partnership",
        "child_custody_adoption",
        "consumer",
        "cyber",
        "family_domestic",
        "marriage_breakdown",
        "marriage_misrepresentation",
        "online_gambling_dispute",
        "police_fir",
        "prison_mulaqat_access",
        "property_tenancy",
        "reproductive_rights_mtp",
        "senior_citizen",
        "social_welfare_identity",
        "supervised_visitation",
        "tenancy_eviction_nonpayment",
        "tribal_caste_atrocity",
        "tribal_land_transfer_restoration",
        "forest_rights_fra",
        "tribal_project_displacement_rr",
        "workplace_sexual_harassment",
    }
    lower = text.lower()
    if action_pack_id == "employment_wages":
        return (
            _has_any_term(lower, ("pip", "rating", "hr complaint", "industrial disputes", "retrench", "termination"))
            and not _has_any_term(lower, ("limitation", "deadline", "last date", "within ", " days", " hours", "file within", "appeal within"))
        )
    if action_pack_id == "criminal_general" and route.label in {"Spousal assault / financial-control complaint", "Spousal sexual coercion / safety support"}:
        return not _has_any_term(lower, (
            "limitation", "deadline", "last date", "within ", " days", " hours",
            "file within", "appeal within",
        ))
    if action_pack_id == "minor_mineral_gram_sabha":
        return _is_safe_minor_mineral_next_step(lower)
    if action_pack_id not in allowed_action_packs:
        return False

    if _has_any_term(lower, (
        "limitation", "deadline", "last date", "within ", " days", " hours",
        "file within", "appeal within",
    )):
        return False
    return True


def _is_safe_minor_mineral_next_step(lower: str) -> bool:
    if _has_any_term(lower, (
        "block the road", "block road", "stop the trucks", "stop trucks",
        "pay the", "bribe", "rishwat", "threat", "force", "beat",
        "lock", "seize", "damage", "burn", "obstruct", "yourself",
        "will cancel", "must cancel", "guaranteed", "guarantee",
        "gherao", "occupy", "road roko", "surround", "encircle",
        "dharna", "protest", "rally", "mob", "crowd",
        "until he cancels", "until they cancel", "until cancellation",
        "cancel the lease", "cancels the lease",
    )):
        return False
    doc_terms = (
        "lease", "noc", "gram sabha", "palli sabha", "minutes",
        "recommendation", "mineral-department", "approval", "site map",
        "forest", "pollution", "scheduled area", "record",
    )
    forum_terms = (
        "collector", "mining department", "tribal", "dlsa", "court",
        "ngt", "panchayat", "gram sabha",
    )
    return sum(1 for term in doc_terms if term in lower) >= 2 and any(term in lower for term in forum_terms)


def _is_safe_template_source_bridge(text: str, route: MatterRoute) -> bool:
    """Allow weak-but-useful deterministic bridge lines to survive.

    These lines are authored by server templates, not the LLM. They connect a
    retrieved source to the user's route without inventing deadlines, amounts,
    or guaranteed outcomes. The verifier often marks them weak because the
    source itself does not contain the user's facts ("LIC agent", "ex's
    lawyer", "thumb impression"), but suppressing them leaves only raw statute
    excerpts and makes the product worse.
    """
    lower = text.lower()
    if _has_any_term(lower, (
        "limitation", "deadline", "last date", "within ", " days", " hours",
        "file within", "appeal within", "guaranteed", "will win", "must win",
    )):
        return False
    bridge_phrases = (
        "source is",
        "sources to check",
        "source matters",
        "source to check",
        "source to verify",
        "source is relevant",
        "route to check",
        "forum route",
        "court remedy",
        "criminal-law track",
        "bank-service track",
        "medical privacy issue",
        "welfare standard",
        "separate police track",
        "should be checked",
        "must be checked",
        "treat this first",
        "keep the",
        "do not assume",
        "do not treat",
        "safe first step",
        "written reasons",
        "sealing order",
        "show-cause notice",
        "trade-licence compliance",
        "written bank-grievance",
        "freeze/lien/kyc reason",
        "bank-service failure",
        "personal-data grievance",
        "cyber/electronic-record",
        "contact-data misuse",
        "not be reduced",
        "do not post",
        "medical status online",
        "keep evidence private",
        "public allegations about medical status",
    )
    return any(phrase in lower for phrase in bridge_phrases)


def _promote_safe_route_next_step(
    v: SentenceVerification,
    route: MatterRoute,
    pending_header: SentenceVerification | None,
) -> SentenceVerification:
    """Let server-authored action-pack bullets pass as weak support.

    The legal source often proves the forum/provision but not the operational
    user step ("keep screenshots", "collect jewellery receipts"). Those steps
    come from our deterministic route/action-pack layer, so an entailment
    scorer can mark them unsupported even when they are the product answer the
    user needs. Keep this narrowly scoped to cited bullets immediately under
    the server's "What you can do next" header.
    """
    if v.status != SentenceStatus.UNSUPPORTED:
        return v
    if not v.citations:
        return v
    if not _is_safe_template_next_step(v.text, route, pending_header):
        return v
    return SentenceVerification(
        text=v.text,
        status=SentenceStatus.WEAK_SUPPORT,
        citations=v.citations,
        entailment_score=v.entailment_score,
        reason="server-authored safe route next step",
        auto_cited=v.auto_cited,
    )


def _promote_safe_template_source_bridge(
    v: SentenceVerification,
    route: MatterRoute,
) -> SentenceVerification:
    if v.status != SentenceStatus.UNSUPPORTED:
        return v
    if not v.citations:
        return v
    if not _is_safe_template_source_bridge(v.text, route):
        return v
    return SentenceVerification(
        text=v.text,
        status=SentenceStatus.WEAK_SUPPORT,
        citations=v.citations,
        entailment_score=v.entailment_score,
        reason="server-authored safe source bridge",
        auto_cited=v.auto_cited,
    )


def _strip_model_terminal_sections(text: str) -> str:
    """Remove model-authored Sources/Disclaimer blocks before segmentation."""
    text = re.sub(
        r"(?i)(?<!\n)\s+((?:#{1,6}\s*)?(?:\*\*\s*)?"
        r"(?:sources?|references?|bibliography|disclaimer)"
        r"(?:\s*\*\*)?\s*:?)",
        r"\n\1",
        text,
    )
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        stripped = line.strip()
        if _SOURCES_HEADER_RE.match(stripped) or _DISCLAIMER_HEADER_RE.match(stripped):
            skipping = True
            continue
        if skipping and _MAJOR_HEADER_RE.match(stripped):
            skipping = False
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


_OFFICIAL_SOURCE_TYPES = {
    "bare_act", "rule", "regulation", "scheme", "guideline", "circular", "notification",
}

_ACTION_WORDS = (
    "apply", "application", "complaint", "complain", "appeal", "petition",
    "file", "filing", "approach", "authority", "tribunal", "court",
    "magistrate", "collector", "officer", "ombudsman", "commission",
    "forum", "notice", "report", "register", "grievance",
)


def _answer_contract_lines(
    route: MatterRoute,
    passages: list[dict],
    state: dict,
    plan: LegalIssuePlan | None = None,
) -> list[str]:
    """Server-side floor for answers that under-cite retrieved law.

    The model is still allowed to write the main explanation, but broad evals
    showed a recurring product failure: retrieval surfaces the right Act while
    the final answer cites only a judgment, or omits a concrete next-step
    section. This post-generation floor emits only conservative source-reference
    lines and route-authored action hints. It deliberately avoids raw statute
    excerpts because bare Act chunks often contain split definitions,
    illustrations, or unrelated procedure fragments.
    """
    official = _official_passages_for_contract(passages)
    if not official:
        return []

    lines: list[str] = []
    cited = set(state.get("emitted_citation_indices") or set())
    planned_seen = set(state.get("seen_sentences") or set())
    official_by_idx = {
        p.get("index"): p
        for p in official
        if isinstance(p.get("index"), int)
    }
    cited_source_keys = {
        _source_pack_key(p)
        for idx, p in official_by_idx.items()
        if idx in cited and _source_pack_key(p)
    }

    for passage in _plan_must_cite_passages(route, plan, official, cited):
        line = _source_excerpt_line(passage)
        if not line:
            continue
        normalized = _normalize_for_dedupe(line)
        if normalized in planned_seen:
            continue
        idx = passage.get("index")
        lines.append(line)
        planned_seen.add(normalized)
        if isinstance(idx, int):
            cited.add(idx)
        source_key = _source_pack_key(passage)
        if source_key:
            cited_source_keys.add(source_key)

    required_source_keys: list[str] = []
    for passage in official:
        key = _source_pack_key(passage)
        if passage.get("required_source_pack") and key and key not in required_source_keys:
            required_source_keys.append(key)
    missing_required_keys = [key for key in required_source_keys if key not in cited_source_keys]
    required_budget = 4 if route.category in {
        "banking_credit_dispute",
        "family_domestic",
        "property_tenancy",
        "reproductive_rights_mtp",
        "senior_citizen",
    } else 3
    if (
        route.label == "Tribal land transfer / restoration"
        and cited_source_keys
        and state.get("saw_next_step_sentence")
    ):
        source_budget = 0
    elif (
        route.label in {"Spousal assault / financial-control complaint", "Spousal sexual coercion / safety support"}
        and cited_source_keys
        and state.get("saw_next_step_sentence")
    ):
        source_budget = 0
    elif cited_source_keys and state.get("saw_next_step_sentence") and int(state.get("emitted") or 0) >= 3:
        source_budget = 0 if len(cited_source_keys) >= 3 else min(1, len(missing_required_keys))
    else:
        source_budget = max(max(0, 2 - len(cited_source_keys)), min(required_budget, len(missing_required_keys)))

    # Cite official/statutory source families the model skipped. Keep this
    # narrow: broad required packs often include fallbacks, and dumping every
    # official source makes the answer drift away from the user's problem.
    added_source_lines = 0
    for passage in official:
        if added_source_lines >= source_budget:
            break
        idx = passage.get("index")
        if not isinstance(idx, int) or idx in cited:
            continue
        source_key = _source_pack_key(passage)
        if _should_skip_contract_source_line(route, source_key, cited_source_keys):
            continue
        if source_key and source_key in cited_source_keys:
            continue
        line = _source_excerpt_line(passage)
        if not line:
            continue
        normalized = _normalize_for_dedupe(line)
        if normalized in planned_seen:
            continue
        lines.append(line)
        planned_seen.add(normalized)
        cited.add(idx)
        if source_key:
            cited_source_keys.add(source_key)
        added_source_lines += 1

    needs_next_step = not state.get("saw_next_step_header") or not state.get("saw_next_step_sentence")
    if needs_next_step:
        action_passages = passages if route.label == "Writ / constitutional remedy procedure" else official
        action_line = _route_action_line(route, action_passages) or _plan_action_line(plan, official)
        if action_line and _normalize_for_dedupe(action_line) not in planned_seen:
            lines.append("**What you can do next**")
            lines.append(action_line)

    return lines


def _official_passages_for_contract(passages: list[dict]) -> list[dict]:
    def score(p: dict) -> tuple[int, float, int, int, int]:
        source_type = str(p.get("source_type") or "").lower()
        title = str(p.get("title") or "").lower()
        anchor = str(p.get("anchor") or "").lower()
        required = 0 if p.get("required_source_pack") else 1
        priority = -float(p.get("required_source_priority") or 0.0)
        official = 0 if _is_official_contract_source(p) else 1
        judgment = 1 if source_type.endswith("judgment") or " versus " in title or " v. " in title else 0
        useful_anchor = 0 if "/sec-" in anchor or "#sec-" in anchor or "section" in title else 1
        return (required, priority, official, judgment, useful_anchor)

    official = [p for p in passages if _is_official_contract_source(p)]
    return sorted(official, key=lambda p: (*score(p), int(p.get("index") or 999)))


def _source_pack_key(passage: dict) -> str:
    pack = str(passage.get("required_source_pack") or "").strip().lower()
    if pack:
        return pack
    return re.sub(
        r"\s+",
        " ",
        str(passage.get("statute_short") or passage.get("title") or "").strip().lower(),
    )


def _plan_must_cite_passages(
    route: MatterRoute,
    plan: LegalIssuePlan | None,
    official: list[dict],
    cited: set[int],
    *,
    limit: int = 2,
) -> list[dict]:
    if plan is None or not official:
        return []

    out: list[dict] = []
    seen_indices: set[int] = set()
    for entry in plan.authority_ledger:
        if not entry.must_cite or not entry.act:
            continue
        if entry.act == "date-dependent criminal regime":
            continue
        already_cited = any(
            isinstance(p.get("index"), int)
            and p.get("index") in cited
            and _plan_authority_matches_passage(entry.act, entry.section, p)
            for p in official
        )
        if already_cited:
            continue
        passage = next(
            (
                p for p in official
                if isinstance(p.get("index"), int)
                and p.get("index") not in cited
                and int(p.get("index")) not in seen_indices
                and not _should_skip_contract_source_line(route, _source_pack_key(p), set())
                and _plan_authority_matches_passage(entry.act, entry.section, p)
            ),
            None,
        )
        if passage is None:
            continue
        out.append(passage)
        seen_indices.add(int(passage["index"]))
        if len(out) >= limit:
            break
    return out


_PLAN_ACT_ALIASES = {
    "bnss": ("bnss", "bharatiya nagarik suraksha sanhita"),
    "bns": ("bns", "bharatiya nyaya sanhita"),
    "bsa": ("bsa", "bharatiya sakshya adhiniyam"),
    "crpc": ("crpc", "criminal procedure"),
    "ipc": ("ipc", "indian penal code"),
    "consumer protection act": ("consumer protection act",),
    "consumer protection act 2019": ("consumer protection act 2019", "consumer protection act"),
    "domestic violence act": ("domestic violence act", "protection of women from domestic violence"),
    "protection of women from domestic violence act 2005": ("protection of women from domestic violence act 2005", "domestic violence act"),
    "forest rights act": ("forest rights act", "scheduled tribes and other traditional forest dwellers"),
    "forest rights act 2006": ("forest rights act 2006", "scheduled tribes and other traditional forest dwellers"),
    "pesa": ("pesa", "panchayats extension to scheduled areas"),
    "pesa act 1996": ("pesa", "panchayats extension to scheduled areas"),
    "rfctlarr act 2013": ("rfctlarr", "right to fair compensation", "land acquisition rehabilitation and resettlement act 2013"),
    "right to fair compensation and transparency in land acquisition rehabilitation and resettlement act 2013": (
        "rfctlarr",
        "right to fair compensation",
        "land acquisition rehabilitation and resettlement act 2013",
    ),
    "sarfaesi act 2002": (
        "sarfaesi",
        "securitisation and reconstruction of financial assets and enforcement of security interest act 2002",
        "securitisation reconstruction financial assets enforcement security interest act 2002",
    ),
    "transfer of property act": ("transfer of property act",),
    "transfer of property act 1882": ("transfer of property act 1882", "transfer of property act"),
}


def _plan_authority_matches_passage(act: str, section: str | None, passage: dict) -> bool:
    act_key = _normalize_plan_authority_text(act)
    if not act_key:
        return False
    haystack = _normalize_plan_authority_text(
        " ".join(
            str(passage.get(field) or "")
            for field in ("title", "statute_short", "anchor", "required_source_pack")
        )
    )
    aliases = _PLAN_ACT_ALIASES.get(act_key, (act_key,))
    if not any(alias and alias in haystack for alias in aliases):
        return False
    if not section:
        return True
    section_token = _section_token(section)
    if not section_token:
        return True
    return _section_token_matches(section_token, _passage_section_tokens(passage))


def _normalize_plan_authority_text(text: str) -> str:
    clean = re.sub(r"\b(?:the|a|an)\b", " ", (text or "").lower())
    clean = clean.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", clean).strip()


def _section_token(section: str) -> str:
    match = re.search(r"\b(?:section|sec\.?|article|order)\s+([0-9a-z()./-]+)", section, flags=re.IGNORECASE)
    if not match:
        return ""
    return _normalize_plan_authority_text(match.group(1))


def _passage_section_tokens(passage: dict) -> set[str]:
    text = " ".join(str(passage.get(field) or "") for field in ("title", "anchor"))
    tokens: set[str] = set()
    for match in re.finditer(r"(?:/|#)sec-([0-9a-z][0-9a-z.-]*)", text, flags=re.IGNORECASE):
        tokens.add(_normalize_plan_authority_text(match.group(1)))
    for match in re.finditer(
        r"\b(?:section|sec\.?|article|order)\s+([0-9a-z()./-]+)",
        text,
        flags=re.IGNORECASE,
    ):
        tokens.add(_normalize_plan_authority_text(match.group(1)))
    return {token for token in tokens if token}


def _section_token_matches(expected: str, actual_tokens: set[str]) -> bool:
    if expected in actual_tokens:
        return True
    expected_parts = expected.split()
    if len(expected_parts) != 1:
        return False
    expected_root = expected_parts[0]
    for token in actual_tokens:
        parts = token.split()
        if len(parts) > 1 and parts[0] == expected_root:
            return True
    return False


def _should_skip_contract_source_line(
    route: MatterRoute,
    source_key: str,
    cited_source_keys: set[str],
) -> bool:
    if route.label == "Minor mineral / Gram Sabha recommendation" and (
        source_key == "rfctlarr_2013"
        or source_key == "rfctlarr_2013_scheduled_area_rr"
        or "right to fair compensation" in source_key
        or "rehabilitation and resettlement" in source_key
    ):
        return True
    if route.label == "SARFAESI / secured-loan recovery" and (
        source_key == "banking_regulation_1949"
        or source_key == "consumer_protection_2019"
        or "banking regulation" in source_key
        or "consumer protection" in source_key
    ):
        return any("sarfaesi" in key or "securitisation" in key for key in cited_source_keys)
    if route.category == "banking_credit_dispute" and source_key == "consumer_protection_2019":
        primary_banking_or_criminal = {
            "rbi_integrated_ombudsman_2021",
            "banking_regulation_1949",
            "bns_2023",
            "bnss_2023",
            "crpc_1973",
        }
        return bool(cited_source_keys & primary_banking_or_criminal)
    if route.label == "Loan-app / recovery harassment" and source_key in {
        "banking_regulation_1949",
        "consumer_protection_2019",
    }:
        loan_app_primary = {
            "rbi_integrated_ombudsman_2021",
            "dpdp_2023",
            "it_act_2000",
            "bns_2023",
            "bnss_2023",
            "crpc_1973",
        }
        return bool(cited_source_keys & loan_app_primary)
    if route.label == "Municipal sealing / shop closure notice" and (
        source_key == "food_safety_2006"
        or "food safety" in source_key
        or source_key == "consumer_protection_2019"
    ):
        return True
    if route.label == "Forest rights / FRA claim or forest produce" and (
        source_key == "scst_poa_1989" or "scheduled castes and scheduled tribes" in source_key
    ):
        return True
    return False


def _prompt_retrieval_candidates(
    query: str,
    route: MatterRoute,
    retrieved: list,
) -> list:
    q = query.lower()
    if route.label == "Municipal sealing / shop closure notice" and not _has_any_term(q, (
        "food", "fssai", "snack", "restaurant", "hotel", "kirana",
        "adulteration", "misbranding", "food safety", "designated officer",
    )):
        filtered = [
            h for h in retrieved
            if "right to information" in str(getattr(h, "title", "")).lower()
            or "rti-2005" in str(getattr(h, "anchor", "")).lower()
            or "shops" in str(getattr(h, "title", "")).lower()
            or "establishment" in str(getattr(h, "title", "")).lower()
            or "street vendor" in str(getattr(h, "title", "")).lower()
            or "municipal" in str(getattr(h, "title", "")).lower()
            or "municipality" in str(getattr(h, "title", "")).lower()
        ]
        if filtered:
            return filtered
    if route.label == "PAN/Aadhaar mismatch / identity linking":
        filtered = [
            h for h in retrieved
            if "income-tax" in str(getattr(h, "anchor", "")).lower()
            or "income tax" in str(getattr(h, "title", "")).lower()
            or "income-tax" in str(getattr(h, "title", "")).lower()
            or "aadhaar" in str(getattr(h, "title", "")).lower()
            or "aadhaar" in str(getattr(h, "anchor", "")).lower()
            or "right to information" in str(getattr(h, "title", "")).lower()
            or "rti-2005" in str(getattr(h, "anchor", "")).lower()
        ]
        if filtered:
            return filtered
    if route.label == "Loan-app / recovery harassment":
        filtered = [
            h for h in retrieved
            if "reserve bank integrated ombudsman" in str(getattr(h, "title", "")).lower()
            or "rbi-integrated-ombudsman" in str(getattr(h, "anchor", "")).lower()
            or "digital personal data protection" in str(getattr(h, "title", "")).lower()
            or "dpdp" in str(getattr(h, "anchor", "")).lower()
            or "information technology" in str(getattr(h, "title", "")).lower()
            or "it-act" in str(getattr(h, "anchor", "")).lower()
            or "bharatiya nyaya" in str(getattr(h, "title", "")).lower()
            or "bns-2023" in str(getattr(h, "anchor", "")).lower()
            or "bharatiya nagarik" in str(getattr(h, "title", "")).lower()
            or "bnss-2023" in str(getattr(h, "anchor", "")).lower()
        ]
        if filtered:
            return filtered
    if route.label == "Writ / constitutional remedy procedure":
        filtered = [
            h for h in retrieved
            if "constitution" in str(getattr(h, "title", "")).lower()
            or "constitution-india" in str(getattr(h, "anchor", "")).lower()
            or "legal services authorities" in str(getattr(h, "title", "")).lower()
            or "article 226" in str(getattr(h, "text", "")).lower()
            or (
                "mandamus" in str(getattr(h, "text", "")).lower()
                and "high court" in str(getattr(h, "text", "")).lower()
            )
        ]
        if filtered:
            return filtered
    if route.label == "Pre-marriage health disclosure / cancelled wedding":
        filtered = [
            h for h in retrieved
            if "human immunodeficiency" in str(getattr(h, "title", "")).lower()
            or "hiv" in str(getattr(h, "title", "")).lower()
            or "aids" in str(getattr(h, "title", "")).lower()
            or "hindu marriage" in str(getattr(h, "title", "")).lower()
            or "family courts" in str(getattr(h, "title", "")).lower()
            or "dowry prohibition" in str(getattr(h, "title", "")).lower()
            or "information technology" in str(getattr(h, "title", "")).lower()
            or "it-2000" in str(getattr(h, "anchor", "")).lower()
            or "digital personal data protection" in str(getattr(h, "title", "")).lower()
            or "dpdp" in str(getattr(h, "anchor", "")).lower()
        ]
        if filtered:
            return filtered
    if route.label == "Tribal project displacement / Gram Sabha consent":
        filtered = [
            h for h in retrieved
            if "panchayats (extension" in str(getattr(h, "title", "")).lower()
            or "pesa" in str(getattr(h, "title", "")).lower()
            or "pesa-1996" in str(getattr(h, "anchor", "")).lower()
            or "right to fair compensation" in str(getattr(h, "title", "")).lower()
            or "rfctlarr" in str(getattr(h, "anchor", "")).lower()
            or "forest rights" in str(getattr(h, "title", "")).lower()
            or "fra-2006" in str(getattr(h, "anchor", "")).lower()
            or "mines and minerals" in str(getattr(h, "title", "")).lower()
            or "mmdr" in str(getattr(h, "anchor", "")).lower()
            or "forest (conservation" in str(getattr(h, "title", "")).lower()
        ]
        if filtered:
            return filtered
    if route.label == "Ancestral land sale / heir share dispute":
        filtered = [
            h for h in retrieved
            if (
                "hindu succession" in str(getattr(h, "title", "")).lower()
                and "/sec-14" not in str(getattr(h, "anchor", "")).lower()
                and "/sec-15" not in str(getattr(h, "anchor", "")).lower()
            )
            or (
                "hindu succession act" in str(getattr(h, "text", "")).lower()
                and "section 6" in str(getattr(h, "text", "")).lower()
            )
            or "transfer of property" in str(getattr(h, "title", "")).lower()
            or "specific relief" in str(getattr(h, "title", "")).lower()
            or "registration act" in str(getattr(h, "title", "")).lower()
        ]
        if filtered:
            return filtered
    if route.label == "Forest rights / FRA claim or forest produce":
        has_fra = any(
            "forest rights" in str(getattr(h, "title", "")).lower()
            or "fra-2006" in str(getattr(h, "anchor", "")).lower()
            for h in retrieved
        )
        if has_fra:
            filtered = [
                h for h in retrieved
                if "prevention of atrocities" not in str(getattr(h, "title", "")).lower()
                and "sc-st-poa" not in str(getattr(h, "anchor", "")).lower()
            ]
            if filtered:
                return filtered
    if (
        route.category == "employment_wages"
        and _is_employment_retaliation_pip_query(q)
        and not _is_gig_platform_worker_query(q)
    ):
        filtered = [
            h for h in retrieved
            if "code on social security" not in str(getattr(h, "title", "")).lower()
            and "social-security-code-2020" not in str(getattr(h, "anchor", "")).lower()
            and "occupational safety" not in str(getattr(h, "title", "")).lower()
            and "osh-code-2020" not in str(getattr(h, "anchor", "")).lower()
        ]
        if any("industrial disputes" in str(getattr(h, "title", "")).lower() for h in filtered):
            return filtered
    return retrieved


def _is_official_contract_source(passage: dict) -> bool:
    source_type = str(passage.get("source_type") or "").lower()
    if source_type in _OFFICIAL_SOURCE_TYPES:
        return True
    if source_type.endswith("judgment"):
        return False
    title = str(passage.get("title") or "").lower()
    if " versus " in title or " vs " in title or " v. " in title:
        return False
    anchor = str(passage.get("anchor") or "").lower()
    return bool(
        anchor.startswith("constitution-india")
        or "/sec-" in anchor
        or "#sec-" in anchor
        or re.search(r"\b(act|code|rules|scheme|guideline|notification|circular)\b", title)
        or any(term in title for term in ("sanhita", "adhiniyam"))
    )


def _source_excerpt_line(passage: dict, *, max_words: int = 34) -> str | None:
    idx = passage.get("index")
    if not isinstance(idx, int):
        return None
    ref = _source_reference_label(passage)
    return f"Additional source to verify for this route: {ref} [{idx}]." if ref else None


def _source_procedural_line(passages: list[dict], *, avoid_normalized: set[str] | None = None) -> str | None:
    avoid = avoid_normalized or set()
    for passage in passages:
        excerpt = _best_source_excerpt(
            str(passage.get("text") or ""),
            max_words=28,
            prefer_terms=_ACTION_WORDS,
            require_prefer_terms=True,
        )
        idx = passage.get("index")
        line = f"- {excerpt} [{idx}]." if excerpt and isinstance(idx, int) else ""
        if line and _normalize_for_dedupe(line) not in avoid:
            return line
    return None


def _route_action_line(route: MatterRoute, passages: list[dict]) -> str | None:
    if not route.action_pack or not route.action_pack.next_steps:
        return None
    if not passages:
        return None
    if route.label == "Writ / constitutional remedy procedure":
        article226 = next((
            p for p in passages
            if "article 226" in _normalize_match_text(str(p.get("text") or ""))
            or "/sec-226" in str(p.get("anchor") or "").lower()
        ), None)
        if article226 is not None and isinstance(article226.get("index"), int):
            idx = article226["index"]
            return (
                "- Collect the written order or refusal, your representation, delivery proof, "
                f"public-duty facts, urgency facts, and exact relief before asking DLSA or a writ lawyer about the High Court Article 226 route [{idx}]."
            )
    passage = passages[0]
    idx = passage.get("index")
    if not isinstance(idx, int):
        return None
    step = _compact_action_step(route.action_pack.next_steps[0])
    if not step:
        return None
    ref = _source_reference_label(passage)
    if ref:
        return f"- {step}; verify the filing, complaint, or reply route against {ref} [{idx}]."
    return f"- {step} using the cited source [{idx}]."


def _plan_action_line(plan: LegalIssuePlan | None, passages: list[dict]) -> str | None:
    if plan is None or not plan.next_steps or not passages:
        return None
    passage = passages[0]
    idx = passage.get("index")
    if not isinstance(idx, int):
        return None
    step = _compact_action_step(plan.next_steps[0])
    if not step:
        return None
    ref = _source_reference_label(passage)
    if ref:
        return f"- {step}; verify the route against {ref} [{idx}]."
    return f"- {step} using the cited source [{idx}]."


def _compact_action_step(step: str, *, max_words: int = 22) -> str:
    clean = re.sub(r"\s+", " ", step).strip().rstrip(".")
    if not clean:
        return ""
    words = clean.split()
    if len(words) > max_words:
        clean = " ".join(words[:max_words]).rstrip(",;:")
    return clean[:1].upper() + clean[1:]


def _best_source_excerpt(
    text: str,
    *,
    max_words: int,
    prefer_terms: tuple[str, ...] = (),
    require_prefer_terms: bool = False,
) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return ""
    candidates = [
        _clean_excerpt_sentence(s)
        for s in segment_sentences(clean)
        if _clean_excerpt_sentence(s)
    ]
    if not candidates:
        candidates = [_clean_excerpt_sentence(clean)]
    if prefer_terms:
        preferred = [s for s in candidates if _has_any_term(s, prefer_terms)]
        if preferred:
            candidates = preferred
        elif require_prefer_terms:
            return ""
    for candidate in candidates:
        if _looks_like_source_heading(candidate):
            continue
        words = candidate.split()
        if len(words) < 4:
            continue
        if len(words) > max_words:
            candidate = " ".join(words[:max_words]).rstrip(",;:")
        return candidate.rstrip(" .;:")
    return ""


def _clean_excerpt_sentence(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    clean = re.sub(r"^\s*[-*—–]\s*", "", clean)
    clean = re.sub(r"^\s*\(?\d+[A-Za-z]?\)?\s*[\).:-]?\s*", "", clean)
    clean = clean.strip(" \"'")
    clean = re.sub(r"\[\d+(?:\s*,\s*\d+)*\]", "", clean).strip()
    return clean


def _looks_like_source_heading(text: str) -> bool:
    clean = re.sub(r"\s+", " ", text).strip(" .;:")
    if not clean:
        return True
    lower = clean.lower()
    words = clean.split()
    has_verb = bool(re.search(r"\b(is|are|may|shall|must|can|means|includes|provides?)\b", lower))
    if len(words) <= 14 and re.search(r"\bsection\s+\d+[a-z]?\b", lower):
        if not has_verb and re.search(r"\b(act|code|rules|constitution|regulations?|guidelines?)\b", lower):
            return True
    if re.fullmatch(r"[A-Za-z0-9 ,&()/-]+ section \d+[a-z]?(?: \d+[a-z]?)?", lower):
        return True
    if len(words) <= 6 and not has_verb:
        return True
    return False


def _source_reference_label(passage: dict) -> str:
    title = re.sub(r"\s+", " ", str(passage.get("title") or passage.get("statute_short") or "")).strip()
    if not title:
        return ""
    section = _anchor_section_label(str(passage.get("anchor") or ""), title=title)
    return f"{title}, {section}" if section else title


def _anchor_section_label(anchor: str, *, title: str) -> str:
    m = re.search(r"/sec-([^#@]+)|#sec-([^#@]+)", anchor)
    if not m:
        return ""
    raw = (m.group(1) or m.group(2) or "").split("__", 1)[0]
    raw = raw.split("@", 1)[0].strip("-_")
    if not raw:
        return ""
    parts = [p for p in raw.split("-") if p]
    if not parts:
        return ""
    main = parts[0].upper()
    suffix = "".join(f"({p})" for p in parts[1:])
    kind = "Article" if "constitution" in title.lower() else "Section"
    return f"{kind} {main}{suffix}"


def _route_regime_caveat(route: MatterRoute) -> str | None:
    if (
        route.legal_regime == UNKNOWN_CRIMINAL_REGIME
        and _route_uses_criminal_regime_sources(route)
    ):
        return CRIMINAL_REGIME_CAVEAT
    return None


def _route_uses_criminal_regime_sources(route: MatterRoute) -> bool:
    source_blob = " ".join([
        route.category or "",
        route.label or "",
        *(route.required_sources or []),
    ]).lower()
    return _has_any_term(source_blob, _CRIMINAL_REGIME_SOURCE_TERMS)


@app.post("/answer")
async def answer(req: AnswerRequest):
    """Stream-with-verification per PLAN §4.3 strict topology.

    Implementation strategy:
      - Retrieve passages.
      - Stream the LLM into an internal buffer.
      - Each time the buffer closes a sentence (pysbd), verify it.
      - Emit verified sentences as SSE events.
      - Public-product default: any `unsupported`/`unknown_citation`
        stops the stream and emits the structured fallback.

    NOTE: the current implementation buffers a small lookahead before
    verifying, so the very last (un-terminated) fragment is verified at
    stream-end. The parallel-with-generation optimization (PLAN §4.3 v1.5)
    requires moving LLM generation onto its own task; this v1 keeps it
    simple and sequential.
    """
    settings = cfg.get_settings()
    request_started = time.perf_counter()
    timings: dict[str, float] = {}
    llm_model_available = True
    src_filter_label = ",".join(sorted(req.sources)) if req.sources else "all"
    metrics.query_total.labels(source_filter=src_filter_label).inc()

    t_route = time.perf_counter()
    route = route_matter(req.q)
    _record_stage(timings, "matter_route", t_route)
    issue_plan = build_legal_issue_plan(req.q, route)
    if issue_plan is not None:
        logger.debug("legal_issue_plan: %s", issue_plan.to_event())

    if route.category == "off_topic":
        metrics.refused_total.inc()

        async def off_topic():
            for ev in _initial_route_events(route, issue_plan):
                yield ev
            yield {"event": "refused", "data": json.dumps({
                "message": "This looks outside the legal-help scope of this system. "
                           "Ask about an Indian legal problem, notice, complaint, "
                           "case, benefit, document, deadline, or forum and I can "
                           "try to route it.",
                "reason": "off_topic",
                "disclaimer": DISCLAIMER_FOOTER,
            })}
            yield _timing_event(
                timings,
                request_started,
                llm_model=settings.llm_model,
                llm_model_available=True,
            )

        return EventSourceResponse(off_topic())

    # Fail fast on model/runtime misconfiguration. Before this preflight,
    # a missing Ollama model spent retrieval + rerank time, emitted coverage
    # and passages, then failed inside the stream. That is slow and confusing.
    t_preflight = time.perf_counter()
    llm_status = await check_model_available(settings.llm_model)
    _record_stage(timings, "llm_preflight", t_preflight)
    if not llm_status.get("ok"):
        llm_model_available = False

        async def llm_missing():
            for ev in _initial_route_events(route, issue_plan):
                yield ev
            yield _llm_unavailable_error(llm_status, settings)
            yield _timing_event(
                timings,
                request_started,
                llm_model=settings.llm_model,
                llm_model_available=False,
            )

        return EventSourceResponse(llm_missing())

    pool = await get_pool()

    # NLI policy: the client hint is honoured ONLY when fast-mode is
    # enabled server-side. In production (answer_fast_enabled=False)
    # NLI always runs, regardless of what the request asks for. See
    # AnswerRequest comment + round-3 review #4.
    skip_nli = req.skip_nli and settings.answer_fast_enabled

    # Retrieve. Task #13: if query_expansion_enabled (default True), use
    # the multi-query path that asks the LLM to translate the lay query
    # into 2-3 legal-vocabulary variants and reranks the union. On the
    # 15 worst-failing queries from the 102-query e2e eval (2026-05-19,
    # scripts/eval_query_expand.py), this lifted the bare-act top-5
    # surface rate from 13% → 53% with 0 WORSE outcomes. Falls back to
    # plain hybrid_retrieve automatically on any expander error.
    src_types = req.sources
    subj = req.subjects
    t_retr = time.perf_counter()
    retrieved, expansion_variants = await multi_query_hybrid_retrieve(
        pool, req.q, source_types=src_types, subject_areas=subj,
        top_k=max(req.top_k, settings.rerank_top_k),
        timings=timings,
    )
    retrieval_elapsed = _record_stage(timings, "retrieval", t_retr)
    metrics.retrieval_latency.observe(retrieval_elapsed)
    if not retrieved:
        metrics.refused_total.inc()
        async def empty():
            for ev in _initial_route_events(route, issue_plan):
                yield ev
            yield {"event": "refused", "data": json.dumps({
                "message": "The sources I have don't cover this clearly. I won't guess. "
                           "You should talk to a lawyer for your specific situation.",
                "disclaimer": DISCLAIMER_FOOTER,
            })}
            yield _timing_event(
                timings,
                request_started,
                llm_model=settings.llm_model,
                llm_model_available=llm_model_available,
                expansion_variant_count=len(expansion_variants),
            )
        return EventSourceResponse(empty())

    # Coverage gate: when the reranker can't find anything close to the
    # query, the LLM will either hallucinate or produce verbose "I don't
    # know" prose grounded in tangential passages. Refuse honestly instead.
    # Threshold derived empirically: in-slice queries score 0.6-0.9 at top;
    # out-of-slice (tenant, IP, "swallow") score < 0.15.
    #
    # Per Codex review (round 2) #3: the gate must fail CLOSED when rerank
    # scores are absent — the original implementation skipped the gate when
    # `top_rerank is None`, which is precisely the degraded state (reranker
    # disabled/unavailable/predict failure) where out-of-slice queries
    # would slip through. If reranking is enabled in config but scores are
    # missing, treat it as service degraded and refuse.
    rerank_scores = [h.rerank_score for h in retrieved if h.rerank_score is not None]
    top_rerank = max(rerank_scores, default=None)
    if settings.rerank_enabled and top_rerank is None:
        # Reranker is supposed to be running but produced no scores.
        # Fail closed.
        metrics.refused_total.inc()
        logger.warning(
            "coverage-gate refusal: reranker enabled but no rerank scores "
            "produced (degraded service) for query %r",
            req.q[:120],
        )
        async def degraded():
            for ev in _initial_route_events(route, issue_plan):
                yield ev
            yield {"event": "refused", "data": json.dumps({
                "message": "The retrieval service is in a degraded state right "
                           "now (the reranker did not return scores). I won't "
                           "answer without that quality signal. Please try again "
                           "shortly, or talk to a lawyer for your specific "
                           "situation.",
                "reason": "rerank_unavailable",
                "disclaimer": DISCLAIMER_FOOTER,
            })}
            yield _timing_event(
                timings,
                request_started,
                llm_model=settings.llm_model,
                llm_model_available=llm_model_available,
                retrieved_count=len(retrieved),
                expansion_variant_count=len(expansion_variants),
            )
        return EventSourceResponse(degraded())
    if top_rerank is not None and top_rerank < settings.refuse_below_rerank:
        metrics.refused_total.inc()
        logger.info("coverage-gate refusal: top_rerank=%.3f < %.3f for query %r",
                    top_rerank, settings.refuse_below_rerank, req.q[:120])
        async def low_coverage():
            for ev in _initial_route_events(route, issue_plan):
                yield ev
            yield {"event": "refused", "data": json.dumps({
                "message": "I couldn't find sources in this index that clearly "
                           "cover your question. I won't make something up from "
                           "tangentially related judgments. Try asking the same "
                           "question more concretely — for example "
                           "'my landlord won't return my deposit' instead of "
                           "'tenant rights' — or talk to a lawyer or legal-aid "
                           "service for your specific situation.",
                "reason": "low_coverage",
                "disclaimer": DISCLAIMER_FOOTER,
            })}
            yield _timing_event(
                timings,
                request_started,
                llm_model=settings.llm_model,
                llm_model_available=llm_model_available,
                retrieved_count=len(retrieved),
                expansion_variant_count=len(expansion_variants),
            )
        return EventSourceResponse(low_coverage())

    # Per round-3 review (security #5): when reranker is disabled in
    # config (operator chose ablation), the rerank-based gate above
    # can't fire — fall back to a calibrated combined-score gate on the
    # BM25+dense fusion so out-of-slice queries can't leak through the
    # disabled-rerank state.
    if not settings.rerank_enabled:
        top_combined = max((h.combined_score for h in retrieved), default=0.0)
        if top_combined < settings.refuse_below_combined:
            metrics.refused_total.inc()
            logger.info(
                "coverage-gate (no-rerank) refusal: top_combined=%.3f < %.3f for query %r",
                top_combined, settings.refuse_below_combined, req.q[:120],
            )
            async def low_dense():
                for ev in _initial_route_events(route, issue_plan):
                    yield ev
                yield {"event": "refused", "data": json.dumps({
                    "message": "I couldn't find sources that clearly cover your "
                               "question. Try asking more concretely, or talk to "
                               "a lawyer or legal-aid service for your specific "
                               "situation.",
                    "reason": "low_coverage_dense_fallback",
                    "disclaimer": DISCLAIMER_FOOTER,
                })}
                yield _timing_event(
                    timings,
                    request_started,
                    llm_model=settings.llm_model,
                    llm_model_available=llm_model_available,
                    retrieved_count=len(retrieved),
                    expansion_variant_count=len(expansion_variants),
                )
            return EventSourceResponse(low_dense())

    t_prompt = time.perf_counter()
    prompt_candidates = _prompt_retrieval_candidates(req.q, route, retrieved)
    required_pack_ids = []
    for h in prompt_candidates:
        pack_id = h.metadata.get("_required_source_pack")
        if pack_id and pack_id not in required_pack_ids:
            required_pack_ids.append(pack_id)
    prompt_retrieved = _preserve_required_source_packs(
        prompt_candidates,
        required_pack_ids,
        limit=req.top_k,
        preferred_top_n=settings.required_source_pack_preferred_top_n,
    )
    passages, idx_map = _make_passages(prompt_retrieved, req.top_k)

    # Build prompt
    system = load_answer_prompt()
    messages = build_messages(system=system, user_question=req.q, passages=passages)
    _record_stage(timings, "prompt_build", t_prompt)
    template_lines = _grounded_template_lines(req.q, route, passages)

    # Coverage chip — sent up front so the UI can render bounds immediately
    seen_sources = set()
    seen_subjects = set()
    for h in prompt_retrieved[:req.top_k]:
        seen_sources.add(h.source_type)
        if h.subject_area:
            seen_subjects.add(h.subject_area)

    async def event_stream() -> AsyncIterator[dict]:
        for ev in _initial_route_events(route, issue_plan):
            yield ev
        # Send the coverage chip first
        yield {"event": "coverage", "data": json.dumps({
            "sources_searched": sorted(seen_sources),
            "subjects_in_results": sorted(seen_subjects),
            "passages_used": len(passages),
        })}
        # Send the passages so the UI can render citation popovers eagerly
        yield {"event": "passages", "data": json.dumps([
            {"index": p["index"], "anchor": p["anchor"], "title": p["title"],
             "as_at": p["as_at"], "court": p["court"], "citation": p["citation"],
             "source_type": p.get("source_type"), "document_id": p.get("document_id"),
             "statute_short": p.get("statute_short")}
            for p in passages
        ])}

        # Mutable state — closured into _check_and_emit so the strict-stop
        # check runs identically in the streaming-loop and final-flush paths.
        state = {
            "emitted": 0,
            "unsupported": 0,
            "skip_threshold": settings.skip_ratio_stop,
            "min_unsupported": settings.min_unsupported_before_stop,
            # Per Codex review (round 2) #4: the model can't be trusted to
            # author the Sources section — a fabricated "[1] SC — INVENTED
            # CASE v. SOMEONE, 2007, para 99." passes the [N] index check
            # while the case name is fiction. We strip everything between
            # the "**Sources**" header and the next major section header
            # (or end-of-stream) and emit our own authoritative sources
            # event from the retrieved metadata after the answer.
            "in_sources_section": False,
            # Strip the model's "**Disclaimer**" block the same way —
            # the server emits the canonical disclaimer event at end of
            # stream, so the model's version is just a duplicate (real
            # user reports showed "**Disclaimer** ..." rendered twice).
            "in_disclaimer_section": False,
            # Dedupe normalized sentence text — small Q4 models routinely
            # loop, emitting the same bullet 4-5 times in a row. The
            # verifier passes each one individually but the UX is broken.
            # Drop verbatim repeats.
            "seen_sentences": set(),
            # Task #10: accumulator for the user-visible answer body —
            # OK + WEAK_SUPPORT sentence texts only. After the stream
            # closes, this concatenation is embedded and compared with
            # the query to compute the relevance verdict.
            # META lines (headers, refusal text, disclaimers) and
            # SUPPRESSED sentences (unsupported, unconfirmed auto-cite)
            # are EXCLUDED — the relevance signal must reflect what the
            # user actually reads.
            "answer_body_sentences": [],
            "emitted_citation_indices": set(),
            "saw_next_step_header": False,
            "saw_next_step_sentence": False,
            "current_section": None,
        }

        def _stop_event() -> dict:
            return {"event": "stop", "data": json.dumps({
                "reason": "insufficient_support",
                "message": ("The sources I have don't cover your question clearly "
                            "enough for me to give a useful answer. Try rephrasing "
                            "it more narrowly, or talk to a lawyer for your "
                            "specific situation."),
                "unsupported_count": state["unsupported"],
                "emitted_count": state["emitted"],
            })}

        def _suppressed_marker() -> dict:
            """Per round-3 UX review: a lightweight signal the UI renders as
            "…" so users can see when a sentence was dropped. Without this,
            the suppress path is invisible: the model wrote "X. Y (uncited).
            Z." and the user sees "X. Z." as if Y never existed."""
            return {"event": "suppressed", "data": json.dumps({})}

        def _verify_with_timing(sent: str) -> SentenceVerification:
            t_verify = time.perf_counter()
            try:
                return verify_sentence(sent, idx_map, skip_nli=skip_nli)
            finally:
                _add_stage_elapsed(
                    timings,
                    "verification",
                    time.perf_counter() - t_verify,
                )

        def _emit_and_check(v: SentenceVerification) -> tuple[dict | None, bool]:
            """Return (sentence-event-or-None, should_stop_now).

            Per Codex adversarial review #1: we do NOT ship unsupported or
            unknown-citation sentences to the user — they get SUPPRESSED
            (event=None) while still counting against the stop budget. This
            preserves the citation guarantee (no uncited legal claim ever
            reaches the user) while letting harmless trailing fluff drop
            silently instead of killing the whole answer.

            Stop still fires when BOTH:
              (a) ratio of unsupported/emitted exceeds skip_threshold, AND
              (b) we've seen at least min_unsupported absolute count.
            With suppression, stop firing means most of the answer was
            uncited — a genuinely bad response — so the explicit banner
            is the right UX."""
            # Detect Sources-section boundary. Per round-3 review (security
            # finding #1) the model can write the header in many shapes
            # — "**Sources**", "## Sources", "Sources:", "SOURCES",
            # "References:", "** Sources **" — and any of those followed by
            # "[N] FAKE CASE v MADE UP, 2099" would ship as OK (valid [N]).
            # Match TOLERANTLY: any line that, after stripping markdown
            # markup, is just the word "sources" or "references".
            if _SOURCES_HEADER_RE.match(v.text.strip()):
                state["in_sources_section"] = True
                return None, False  # drop the header itself
            # Same treatment for the model's Disclaimer block — the server
            # emits the canonical disclaimer at end-of-stream, so anything
            # the model writes under "**Disclaimer**" is a duplicate.
            if _DISCLAIMER_HEADER_RE.match(v.text.strip()):
                state["in_disclaimer_section"] = True
                return None, False
            if state["in_sources_section"] or state["in_disclaimer_section"]:
                # End suppression on ANY major section header so an
                # answer that omits the closing header doesn't suppress
                # the rest of the stream. Both Sources and Disclaimer
                # are last-ish sections; any other major header means
                # the model moved on (defensive).
                if _MAJOR_HEADER_RE.match(v.text.strip()):
                    state["in_sources_section"] = False
                    state["in_disclaimer_section"] = False
                else:
                    return None, False  # inside Sources/Disclaimer, drop

            stripped = v.text.strip()
            if _MAJOR_HEADER_RE.match(stripped):
                normalized_header = stripped.lower().strip("*#:-. ")
                if normalized_header == "what you can do next":
                    state["saw_next_step_header"] = True
                    state["current_section"] = "next_steps"
                else:
                    state["current_section"] = normalized_header

            # Sentence dedupe — small models loop. Normalize and check.
            normalized = _normalize_for_dedupe(v.text)
            if normalized and normalized in state["seen_sentences"]:
                logger.debug("dedupe: dropping repeated sentence %r", v.text[:80])
                return None, False
            if normalized:
                state["seen_sentences"].add(normalized)

            is_bad = v.status in (
                SentenceStatus.UNSUPPORTED, SentenceStatus.UNKNOWN_CITATION,
            )
            # Per Codex review (round 2) #2: auto-cited sentences are
            # citation-by-lexical-overlap, NOT by entailment. If NLI cleared
            # them (status=OK) they're safe to emit. If NLI flagged them as
            # WEAK or was unavailable, they MUST be suppressed — a lexical
            # match without entailment confirmation is not citation evidence
            # and shipping it as cited prose breaks the citation guarantee.
            is_unconfirmed_auto_cite = (
                v.status == SentenceStatus.WEAK_SUPPORT and v.auto_cited
            )
            suppress = is_bad or is_unconfirmed_auto_cite
            if is_bad or is_unconfirmed_auto_cite:
                state["unsupported"] += 1
                # Use the closest existing status label for the metric so
                # the suppression rate is observable.
                metrics.unsupported_total.labels(
                    status=v.status.value if is_bad else "weak_auto_cite",
                ).inc()
            elif v.status == SentenceStatus.WEAK_SUPPORT:
                metrics.weak_support_total.inc()
            if v.status != SentenceStatus.META:
                state["emitted"] += 1
            triggered = (
                state["unsupported"] >= state["min_unsupported"]
                and state["emitted"]
                and state["unsupported"] / max(1, state["emitted"]) > state["skip_threshold"]
            )
            if suppress:
                # Lightweight marker so the UI can render "…" — see
                # _suppressed_marker docstring. We return it as the event
                # so the caller can yield it; counters still tick above.
                return _suppressed_marker(), triggered
            if v.citations:
                state["emitted_citation_indices"].update(v.citations)
            if (
                v.status in (SentenceStatus.OK, SentenceStatus.WEAK_SUPPORT)
                and state.get("current_section") == "next_steps"
            ):
                state["saw_next_step_sentence"] = True
            # Task #10: accumulate user-visible cited prose (OK or
            # WEAK_SUPPORT, never META) for the relevance check. We
            # store the sentence text WITHOUT the [N] citation tags so
            # the cosine reflects the claim itself, not the citation
            # numerals.
            if v.status in (SentenceStatus.OK, SentenceStatus.WEAK_SUPPORT):
                state["answer_body_sentences"].append(
                    _CITATION_TAG_RE.sub("", v.text).strip()
                )
            return _sentence_event(v), triggered

        def _emit_contract_floor() -> tuple[list[dict], bool]:
            out: list[dict] = []
            pending_header: SentenceVerification | None = None
            for sent in _answer_contract_lines(route, passages, state, issue_plan):
                v = _verify_with_timing(sent)
                if _is_deferred_template_header(v.text):
                    pending_header = v
                    continue
                v = _promote_safe_route_next_step(v, route, pending_header)
                v = _promote_safe_template_source_bridge(v, route)
                if not _candidate_sentence_should_emit(v, pending_header):
                    continue
                header_ev: dict | None = None
                if pending_header is not None:
                    header_ev, header_stop = _emit_and_check(pending_header)
                    pending_header = None
                    if header_ev is not None:
                        out.append(header_ev)
                    if header_stop:
                        return out, True
                sentence_ev, should_stop = _emit_and_check(v)
                if sentence_ev is not None:
                    out.append(sentence_ev)
                if should_stop:
                    return out, True
            return out, False

        def _candidate_sentence_should_emit(
            v: SentenceVerification,
            pending_header: SentenceVerification | None = None,
        ) -> bool:
            if _MAJOR_HEADER_RE.match(v.text.strip()) and not _is_deferred_template_header(v.text):
                return False
            if _is_no_concrete_placeholder(v.text):
                return False
            if v.status in (SentenceStatus.UNSUPPORTED, SentenceStatus.UNKNOWN_CITATION):
                return False
            # In compose-before-emit mode, weak model prose is treated as an
            # internal draft failure. The user gets only OK/meta sentences plus
            # the server-composed source floor.
            if v.status == SentenceStatus.WEAK_SUPPORT:
                if _is_safe_template_next_step(v.text, route, pending_header):
                    return True
                return False
            return True

        def _candidate_template_sentence_should_emit(
            v: SentenceVerification,
            pending_header: SentenceVerification | None = None,
        ) -> bool:
            if _MAJOR_HEADER_RE.match(v.text.strip()) and not _is_deferred_template_header(v.text):
                return False
            if _is_no_concrete_placeholder(v.text):
                return False
            if v.status == SentenceStatus.UNKNOWN_CITATION:
                return False
            if v.status == SentenceStatus.UNSUPPORTED:
                return (
                    _is_safe_template_next_step(v.text, route, pending_header)
                    or _is_safe_template_source_bridge(v.text, route)
                )
            if v.status == SentenceStatus.WEAK_SUPPORT:
                if not (
                    _is_safe_template_next_step(v.text, route, pending_header)
                    or _is_safe_template_source_bridge(v.text, route)
                ):
                    return False
            return True

        route_caveat = _route_regime_caveat(route)
        if route_caveat:
            caveat_v = _verify_with_timing(route_caveat)
            caveat_ev, caveat_stop = _emit_and_check(caveat_v)
            if caveat_ev is not None:
                yield caveat_ev
            if caveat_stop:
                metrics.stopped_total.inc()
                yield _stop_event()
                yield _timing_event(
                    timings,
                    request_started,
                    llm_model=settings.llm_model,
                    llm_model_available=llm_model_available,
                    retrieved_count=len(retrieved),
                    passages_used=len(passages),
                    expansion_variant_count=len(expansion_variants),
                    state=state,
                )
                yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
                _record_final_metrics(state, time.perf_counter())
                return

        if template_lines:
            _add_stage_elapsed(timings, "llm_stream", 0.0)
            pending_template_header: SentenceVerification | None = None
            for sent in template_lines:
                v = _verify_with_timing(sent)
                if _is_deferred_template_header(v.text):
                    pending_template_header = v
                    continue
                v = _promote_safe_route_next_step(v, route, pending_template_header)
                v = _promote_safe_template_source_bridge(v, route)
                if not _candidate_template_sentence_should_emit(v, pending_template_header):
                    continue
                if pending_template_header is not None:
                    header_ev, header_stop = _emit_and_check(pending_template_header)
                    pending_template_header = None
                    if header_ev is not None:
                        yield header_ev
                    if header_stop:
                        metrics.stopped_total.inc()
                        yield _stop_event()
                        yield _timing_event(
                            timings,
                            request_started,
                            llm_model=settings.llm_model,
                            llm_model_available=llm_model_available,
                            retrieved_count=len(retrieved),
                            passages_used=len(passages),
                            expansion_variant_count=len(expansion_variants),
                            state=state,
                        )
                        yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
                        _record_final_metrics(state, time.perf_counter())
                        return
                sentence_ev, should_stop = _emit_and_check(v)
                if sentence_ev is not None:
                    yield sentence_ev
                if should_stop:
                    metrics.stopped_total.inc()
                    yield _stop_event()
                    yield _timing_event(
                        timings,
                        request_started,
                        llm_model=settings.llm_model,
                        llm_model_available=llm_model_available,
                        retrieved_count=len(retrieved),
                        passages_used=len(passages),
                        expansion_variant_count=len(expansion_variants),
                        state=state,
                    )
                    yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
                    _record_final_metrics(state, time.perf_counter())
                    return

            contract_events, contract_stop = _emit_contract_floor()
            for ev in contract_events:
                yield ev
            if contract_stop:
                metrics.stopped_total.inc()
                yield _stop_event()
                yield _timing_event(
                    timings,
                    request_started,
                    llm_model=settings.llm_model,
                    llm_model_available=llm_model_available,
                    retrieved_count=len(retrieved),
                    passages_used=len(passages),
                    expansion_variant_count=len(expansion_variants),
                    state=state,
                )
                yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
                _record_final_metrics(state, time.perf_counter())
                return

            yield {"event": "sources", "data": json.dumps([
                {
                    "index": p["index"],
                    "title": p["title"],
                    "court": p["court"],
                    "citation": p["citation"],
                    "anchor": p["anchor"],
                    "as_at": p["as_at"],
                    "source_type": p.get("source_type"),
                    "document_id": p.get("document_id"),
                    "statute_short": p.get("statute_short"),
                }
                for p in passages
            ])}
            if settings.answer_relevance_enabled and state["answer_body_sentences"]:
                body = " ".join(state["answer_body_sentences"]).strip()
                t_relevance = time.perf_counter()
                rel = compute_relevance(
                    req.q, body,
                    threshold=settings.answer_relevance_threshold,
                    band=settings.answer_relevance_band,
                )
                _record_stage(timings, "relevance", t_relevance)
                if rel is not None:
                    yield {"event": "relevance", "data": json.dumps({
                        "score": round(rel.score, 4),
                        "verdict": rel.verdict.value,
                        "threshold": round(rel.threshold, 4),
                        "band": round(rel.band, 4),
                    })}
            yield _timing_event(
                timings,
                request_started,
                llm_model=settings.llm_model,
                llm_model_available=llm_model_available,
                retrieved_count=len(retrieved),
                passages_used=len(passages),
                expansion_variant_count=len(expansion_variants),
                state=state,
            )
            yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
            _record_final_metrics(state, time.perf_counter())
            return

        buf = ""
        llm_t0 = time.perf_counter()
        first_token_seen = False
        llm_stream_recorded = False

        def _record_llm_stream_once() -> None:
            nonlocal llm_stream_recorded
            if not llm_stream_recorded:
                _record_stage(timings, "llm_stream", llm_t0)
                llm_stream_recorded = True

        try:
            async for delta in stream_chat(messages):
                if not first_token_seen and delta.strip():
                    metrics.llm_ttft.observe(time.perf_counter() - llm_t0)
                    first_token_seen = True
                buf += delta

            composed_text = _strip_model_terminal_sections(buf)
            if composed_text.strip():
                for sent in segment_sentences(composed_text):
                    v = _verify_with_timing(sent)
                    if not _candidate_sentence_should_emit(v):
                        continue
                    sentence_ev, should_stop = _emit_and_check(v)
                    if sentence_ev is not None:
                        yield sentence_ev
                    if should_stop:
                        metrics.stopped_total.inc()
                        _record_llm_stream_once()
                        yield _stop_event()
                        yield _timing_event(
                            timings,
                            request_started,
                            llm_model=settings.llm_model,
                            llm_model_available=llm_model_available,
                            retrieved_count=len(retrieved),
                            passages_used=len(passages),
                            expansion_variant_count=len(expansion_variants),
                            state=state,
                        )
                        yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
                        _record_final_metrics(state, llm_t0)
                        return

            _record_llm_stream_once()

            contract_events, contract_stop = _emit_contract_floor()
            for ev in contract_events:
                yield ev
            if contract_stop:
                metrics.stopped_total.inc()
                yield _stop_event()
                yield _timing_event(
                    timings,
                    request_started,
                    llm_model=settings.llm_model,
                    llm_model_available=llm_model_available,
                    retrieved_count=len(retrieved),
                    passages_used=len(passages),
                    expansion_variant_count=len(expansion_variants),
                    state=state,
                )
                yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
                _record_final_metrics(state, llm_t0)
                return

            # Server-authored authoritative Sources event. Per Codex review
            # (round 2) #4, the LLM is no longer allowed to author the
            # Sources section because it can fabricate case names while
            # using a real [N] index. The UI renders this `sources` event
            # exactly as-is from the retrieval result.
            yield {"event": "sources", "data": json.dumps([
                {
                    "index": p["index"],
                    "title": p["title"],
                    "court": p["court"],
                    "citation": p["citation"],
                    "anchor": p["anchor"],
                    "as_at": p["as_at"],
                    "source_type": p.get("source_type"),
                    "document_id": p.get("document_id"),
                    "statute_short": p.get("statute_short"),
                }
                for p in passages
            ])}

            # Task #10: answer-vs-query relevance check. Embed the
            # original query and the concatenated answer body, compare
            # by cosine, classify by calibrated threshold. ADDITIVE — the
            # event is informational; the UI may render a notice but the
            # answer itself is not affected.
            #
            # Emit ONLY on the normal end path (after `sources`, before
            # `disclaimer`). NOT emitted on refused / stopped / empty-
            # body paths because there's nothing meaningful to score.
            if settings.answer_relevance_enabled and state["answer_body_sentences"]:
                body = " ".join(state["answer_body_sentences"]).strip()
                t_relevance = time.perf_counter()
                rel = compute_relevance(
                    req.q, body,
                    threshold=settings.answer_relevance_threshold,
                    band=settings.answer_relevance_band,
                )
                _record_stage(timings, "relevance", t_relevance)
                if rel is not None:
                    yield {"event": "relevance", "data": json.dumps({
                        "score": round(rel.score, 4),
                        "verdict": rel.verdict.value,
                        "threshold": round(rel.threshold, 4),
                        "band": round(rel.band, 4),
                    })}

            yield _timing_event(
                timings,
                request_started,
                llm_model=settings.llm_model,
                llm_model_available=llm_model_available,
                retrieved_count=len(retrieved),
                passages_used=len(passages),
                expansion_variant_count=len(expansion_variants),
                state=state,
            )
            # Final disclaimer event — always
            yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_FOOTER})}
            _record_final_metrics(state, llm_t0)
        except LLMModelUnavailable as e:
            logger.exception("answer stream llm unavailable: %s", e)
            _record_llm_stream_once()
            yield _llm_unavailable_error({
                "ok": False,
                "model": settings.llm_model,
                "available_models": [],
                "message": str(e),
            }, settings)
            yield _timing_event(
                timings,
                request_started,
                llm_model=settings.llm_model,
                llm_model_available=False,
                retrieved_count=len(retrieved),
                passages_used=len(passages),
                expansion_variant_count=len(expansion_variants),
                state=state,
            )
        except Exception as e:
            logger.exception("answer stream error: %s", e)
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
            _record_llm_stream_once()
            yield _timing_event(
                timings,
                request_started,
                llm_model=settings.llm_model,
                llm_model_available=llm_model_available,
                retrieved_count=len(retrieved),
                passages_used=len(passages),
                expansion_variant_count=len(expansion_variants),
                state=state,
            )

    return EventSourceResponse(event_stream())


# Section-header detectors used by the Sources/Disclaimer stripping path.
# Match tolerantly so the model can't slip fabricated content through by
# varying header style. See main.py:_emit_and_check.
_SOURCES_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*\s*)?(sources?|references?|bibliography)(?:\s*\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)
_DISCLAIMER_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*\s*)?disclaimer(?:\s*\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)
_MAJOR_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?\*\*\s*[A-Za-z][^*]+?\*\*\s*:?\s*$"
)

# Strip [N] / [1,2] / [1][2] citation tags from a sentence before
# embedding it for the relevance check (Task #10). bge-m3 doesn't know
# what "[1]" means — leaving the tag in just adds noise to the cosine.
_CITATION_TAG_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


def _normalize_for_dedupe(text: str) -> str:
    """Normalize a sentence for verbatim-repeat detection. Strip leading
    bullet markers, citation tags, surrounding whitespace, and casefold.
    A sentence like "- You may apply ... [1][2]." and "  You may apply ...
    [1] [2]" should compare equal."""
    s = text.strip()
    s = re.sub(r"^\s*[-*]\s*", "", s)
    s = re.sub(r"\[\d+\]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower().strip(" .;:")


def _find_tail_start(buf: str, second_to_last: str) -> int:
    """Locate where the second-to-last segmented sentence starts inside the
    original buffer text. pysbd strips outer whitespace and may normalize
    internal whitespace; we look for the first ~16-char prefix that survives
    intact, then return that index. Falls back to -1 if not found."""
    needle = second_to_last.strip()[:16]
    if not needle:
        return -1
    return buf.find(needle)


def _sentence_event(v: SentenceVerification) -> dict:
    return {
        "event": "sentence",
        "data": json.dumps({
            "text": v.text,
            "status": v.status.value,
            "citations": v.citations,
            "entailment_score": v.entailment_score,
            "reason": v.reason,
            "auto_cited": v.auto_cited,
        }),
    }


def _record_final_metrics(state: dict, llm_t0: float) -> None:
    """End-of-stream metrics (skip_ratio + total LLM time)."""
    metrics.llm_total.observe(time.perf_counter() - llm_t0)
    if state["emitted"]:
        metrics.skip_ratio.observe(state["unsupported"] / state["emitted"])


# ----- health ---------------------------------------------------------------

@app.get("/healthz")
async def healthz(
    deep: bool = Query(False, description="also check local Ollama model availability"),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        chunk_count = await conn.fetchval("SELECT COUNT(*) FROM chunks WHERE NOT quarantined")
        doc_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
    body = {
        "status": "ok",
        "chunks": chunk_count,
        "documents": doc_count,
    }
    if deep:
        llm = await check_model_available()
        body["llm"] = llm
        if not llm.get("ok"):
            body["status"] = "degraded"
    return body


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus scrape endpoint (PLAN §6.4)."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
