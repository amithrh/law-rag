#!/usr/bin/env python3
"""Browser-level checks for the answer-stream safety contract.

This runs against the real Next.js UI. The API stream is deliberately
controlled at the browser boundary so truncated and out-of-order transport
behavior is reproducible without mutating the production corpus.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("LAW_RAG_WEB_URL", "http://127.0.0.1:3000/")


def valid_plan() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "plan_id": "matter_plan_v2_browser_contract_test",
        "primary_issue": "consumer",
        "primary_label": "Consumer complaint",
        "confidence": 0.9,
        "user_role": "consumer_or_customer",
        "jurisdiction": {"state": None, "city": None, "forum_mentioned": None, "needs_state": False},
        "incident_date_status": "not_required_or_not_detected",
        "urgency": "medium",
        "legal_regime": None,
        "case_stage": "pre_complaint_or_unknown",
        "desired_outcome": "refund_or_compensation",
        "action_pack_id": "consumer",
        "action_pack_title": "Consumer complaint path",
        "required_facts": [],
        "secondary_issues": [],
        "forums": [],
        "remedies": [],
        "deadlines": [],
        "documents": [],
        "next_steps": [],
        "portals": [],
        "escalation": [],
        "cautions": [],
        "safety_flags": [],
        "authority_ledger": [{
            "source": "Consumer Protection Act 2019",
            "authority_id": "authority_consumer",
            "identity_status": "canonical",
            "canonical_name": "consumer protection act 2019",
            "act": "Consumer Protection Act 2019",
            "section": None,
            "source_pack_id": "consumer_protection_2019",
            "required_anchor_patterns": ["/sec-35"],
            "claim_type": "legal_basis",
            "priority": "must_cite",
            "must_cite": True,
            "conditional": False,
            "note": None,
        }],
        "retrieval_sources": [{
            "source_pack_id": "consumer_protection_2019",
            "title_patterns": ["Consumer Protection Act 2019"],
            "search_query": "consumer complaint",
            "doc_ids": ["consumer-protection-2019"],
            "anchor_patterns": ["/sec-35"],
            "source_types": ["bare_act"],
            "priority": 1,
        }],
        "answer_policy": {
            "required_primary_owner": "server_template_or_verified_llm",
            "fallback_owner": "source_gap_handoff",
            "allow_freeform_llm": True,
            "requires_reviewed_contract": False,
        },
    }


def source_gap() -> dict[str, Any]:
    return {
        "has_gap": True,
        "route_category": "business_license_compliance",
        "gap_kinds": ["state_or_local_authority_gap"],
        "missing_required_sources": [{
            "required_source": "state licensing rules",
            "kind": "state_or_local_authority_gap",
        }],
        "message": "The controlling state procedure needs verification.",
        "handoff": "DLSA/legal aid or a qualified lawyer",
        "policy": "do_not_substitute_neighboring_authority",
        "outcome": "source_gap_handoff",
        "reason": "required_source_gap",
        "safe_handoff_only": True,
    }


def timing() -> dict[str, Any]:
    return {
        "total_ms": 12.0,
        "llm_model": "contract-test-model",
        "llm_model_available": True,
        "retrieved_count": 1,
        "passages_used": 1,
        "expansion_variant_count": 1,
        "sentence_count": 1,
    }


def sse(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(
        f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"
        for name, data in events
    )


def main() -> int:
    with sync_playwright() as playwright:
        executable = os.environ.get(
            "LAW_RAG_BROWSER_EXECUTABLE",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        launch_options: dict[str, Any] = {"headless": True}
        if os.path.exists(executable):
            launch_options["executable_path"] = executable
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page()
        mode = {"name": "source_gap"}

        def answer_route(route) -> None:
            if mode["name"] == "source_gap":
                body = sse([("source_gap", source_gap())])
            else:
                body = sse([
                    ("matter_plan", valid_plan()),
                    ("sentence", {
                        "text": "EARLY ANSWER",
                        "status": "ok",
                        "citations": [1],
                        "entailment_score": 0.8,
                        "reason": None,
                        "auto_cited": False,
                    }),
                    ("timing", timing()),
                    ("sentence", {
                        "text": "LATE ANSWER MUST NOT SHOW",
                        "status": "ok",
                        "citations": [1],
                        "entailment_score": 0.8,
                        "reason": None,
                        "auto_cited": False,
                    }),
                    ("error", {"message": "late transport error"}),
                ])
            encoded_body = body.encode("utf-8")
            route.fulfill(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-store",
                    "Content-Length": str(len(encoded_body)),
                },
                body=encoded_body,
            )

        page.route("**/api/answer", answer_route)
        page.goto(BASE_URL, wait_until="domcontentloaded")
        question = page.locator('input[type="text"]').first
        ask = page.get_by_role("button", name="Ask")

        question.click()
        question.press_sequentially("state licence procedure is unclear")
        page.wait_for_function(
            "document.querySelector('button[type=submit]')?.disabled === false",
            timeout=5000,
        )
        ask.click()
        page.get_by_text("Safe intake handoff", exact=True).wait_for(timeout=5000)
        body_text = page.locator("body").inner_text()
        assert "The answer could not be completed safely" not in body_text
        assert "controlling authority" in body_text

        mode["name"] = "late_events"
        question.click()
        question.press("ControlOrMeta+A")
        question.press_sequentially("my order arrived damaged")
        page.wait_for_function(
            "document.querySelector('button[type=submit]')?.disabled === false",
            timeout=5000,
        )
        ask.click()
        try:
            page.get_by_text("EARLY ANSWER", exact=True).wait_for(timeout=5000)
        except Exception:
            raise
        page.wait_for_timeout(150)
        body_text = page.locator("body").inner_text()
        assert "EARLY ANSWER" in body_text
        assert "LATE ANSWER MUST NOT SHOW" not in body_text
        assert "late transport error" not in body_text

        # Real service smoke: remove interception and exercise the browser's
        # same-origin proxy, the live API, retrieval, and terminal timing.
        page.close()
        page = browser.new_page()
        page.goto(BASE_URL, wait_until="domcontentloaded")
        question = page.locator('input[type="text"]').first
        ask = page.get_by_role("button", name="Ask")
        question.click()
        question.press_sequentially("My online order arrived broken. Can I get a refund?")
        page.wait_for_function(
            "document.querySelector('button[type=submit]')?.disabled === false",
            timeout=5000,
        )
        ask.click()
        page.get_by_text("answered in", exact=False).wait_for(timeout=120000)
        body_text = page.locator("body").inner_text()
        assert "Answer plan unavailable" not in body_text
        assert "The answer could not be completed safely" not in body_text

        # Real safety smoke: an acid/chemical incident must travel through
        # the live proxy and fail closed when the date/regime-specific source
        # pair cannot be verified. This guards the browser path that mocked
        # source-gap events cannot cover.
        page.close()
        page = browser.new_page()
        page.goto(BASE_URL, wait_until="domcontentloaded")
        question = page.locator('input[type="text"]').first
        ask = page.get_by_role("button", name="Ask")
        question.click()
        question.press_sequentially(
            "Someone threw acid on my face and I went to the hospital; what should I do?"
        )
        page.wait_for_function(
            "document.querySelector('button[type=submit]')?.disabled === false",
            timeout=5000,
        )
        ask.click()
        page.get_by_text("Safe intake handoff", exact=True).wait_for(timeout=120000)
        body_text = page.locator("body").inner_text()
        assert "Acid or chemical attack / urgent FIR" in body_text
        assert "source verification pending" in body_text
        assert "Controlling source not fully available" in body_text
        assert "The answer could not be completed safely" not in body_text
        assert "Answer plan unavailable" not in body_text
        assert "The question reports an acid or chemical attack" not in body_text
        assert "BNS Section 124" not in body_text
        assert "IPC Section 326A" not in body_text
        assert "Go to hospital/emergency care first" not in body_text
        browser.close()
    print("browser contract: PASS (protocol safety plus live proxy/API stream)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"browser contract: FAIL: {exc}", file=sys.stderr)
        raise
