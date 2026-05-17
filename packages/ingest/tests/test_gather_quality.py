"""Tests for the gather pipeline's quality gate.

This test exists because of a real product defect: the gather script's
quality check passed three WRONG documents into the corpus on first run —
a Gazette notification of IPC (instead of IPC itself), a Delhi-Amendment
Bill (instead of the actual CrPC), and the Commercial Documents Evidence
Act 1939 (instead of the Indian Evidence Act 1872). All three matched
the "has section markers + Indian Act front-matter" check but were the
wrong document.

The tightened check now requires:
  1. ≥2000 chars
  2. ≥95% ASCII letter ratio (no Hindi/Bengali/garbled OCR)
  3. Title token overlap with the expected query (catches near-name siblings)
"""
from __future__ import annotations

import sys
from pathlib import Path

# scripts/ isn't a package; load gather_more_data manually.
import importlib.util
SPEC = importlib.util.spec_from_file_location(
    "gather_more_data",
    Path(__file__).parent.parent.parent.parent / "scripts" / "gather_more_data.py",
)
_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(_module)
is_meaningful_act_text = _module.is_meaningful_act_text


# Synthetic minimal "looks like an Indian act" text shared by passing tests.
HEAD = (
    "\nTHE EXAMPLE ACT, 2024\n(ACT NO. 99 OF 2024)\nARRANGEMENT OF SECTIONS\n"
    "1. Short title and extent.\n2. Definitions.\n"
    "This Act extends to the whole of India.\n"
)
PADDING = " The following sentences provide enough body text to clear the length gate." * 30
SAMPLE_BODY = HEAD + PADDING  # ~2300 chars


class TestLengthGate:
    def test_short_text_rejected(self) -> None:
        assert is_meaningful_act_text("Too short.") is False

    def test_long_enough_passes_length(self) -> None:
        # No expected title → only length + markers + ASCII checks
        assert is_meaningful_act_text(SAMPLE_BODY) is True


class TestStructureGate:
    def test_random_long_text_with_no_markers_rejected(self) -> None:
        text = "Plain prose without any act markers. " * 200
        assert is_meaningful_act_text(text) is False

    def test_text_with_act_no_marker_passes(self) -> None:
        text = ("ACT NO. 12 OF 2024\n" + PADDING + "Short title in this Act.")
        # Either passes (ACT NO. + Short title found) or fails on ASCII —
        # the synthetic padding is all ASCII so it should pass.
        assert is_meaningful_act_text(text) is True


class TestAsciiRatioGate:
    """The IPC handle we tried first returned a Gazette of India with
    garbled Hindi+English OCR. The ASCII-ratio gate should reject it."""

    def test_hindi_english_mix_rejected(self) -> None:
        garbled = (
            "REGISTERED NO. DIc=(N)04/0007l2003\n"
            "13\nCfi1\n'lh~ <Ga!ette tIC~iG\n~\nEXIRAORDINARY\n"
            "'WI' U-wq 1\nPART U -\nSection I\n"
            "~ -« VCfiIftm\nPUBLISHED BY AUTHORITY\n"
            "\"«0 17J\nNo.17J\n"
            "~~, ~, arm 2, 2013rQ 12, 1935 (~)\n"
            "NEW DELHI, TUESDAY, APRIL 2, 2013/CHAITRA 12, 1935 (SAKA)\n"
            "45 of 1860.\n"
            "~ 'ff1T 11 f'F;r 1fl!O~ ~ \\5ffiitt ~ fcti ~ Sffi1T~ ri' ~ 11 \\8T ~fi I\n"
            + PADDING
        )
        # Even though this text has "Short title", "ACT NO.", "NEW DELHI" etc.,
        # the OCR garbage in the first 3000 chars drops ASCII letter ratio
        # below 0.95.
        assert is_meaningful_act_text(garbled) is False


class TestTitleMatchGate:
    """The real catch — IndiaCode searches for similar-named acts and
    sometimes returns a different one with overlapping words. Title
    matching prevents this."""

    def test_indian_evidence_query_rejects_commercial_documents_evidence(self) -> None:
        """Real case: searching for 'Indian Evidence Act 1872' returned
        handle 2408 = Commercial Documents Evidence Act 1939."""
        text = (
            "1\nTHE COMMERCIAL DOCUMENTS EVIDENCE ACT, 1939\n"
            "ARRANGEMENT OF SECTIONS\n"
            "1. Short title and extent.\n2. Statements of relevant facts...\n"
            + PADDING
        )
        assert is_meaningful_act_text(text, expected_title="Indian Evidence Act 1872") is False

    def test_indian_evidence_query_accepts_indian_evidence_act(self) -> None:
        text = (
            "THE INDIAN EVIDENCE ACT, 1872\n"
            "(ACT NO. 1 OF 1872)\nARRANGEMENT OF SECTIONS\n"
            "1. Short title, extent and commencement.\n"
            + PADDING
        )
        assert is_meaningful_act_text(text, expected_title="Indian Evidence Act 1872") is True

    def test_crpc_query_rejects_delhi_amendment_bill(self) -> None:
        """Real case: searching for 'Code of Criminal Procedure 1973'
        returned handle 13635 = Delhi Amendment Bill 2011."""
        text = (
            "THE CODE OF CRIMINAL PROCEDURE (DELHI AMENDMENT) BILL, 2011\n"
            "Bill No. 6 of 2011\nPREAMBLE\nA Bill further to amend the Code of "
            "Criminal Procedure, 1973, in its application to the National "
            "Capital Territory of Delhi.\nShort title and extent.\n"
            + PADDING
        )
        # The actual title contains "DELHI AMENDMENT BILL", expected says
        # "Code of Criminal Procedure 1973". Most expected tokens missing
        # from actual title → rejected.
        # Note: this is a BILL, not an ACT — the actual_title regex won't
        # match (we require "ACT" in the captured title), so it should
        # also fall through there.
        result = is_meaningful_act_text(
            text, expected_title="Code of Criminal Procedure 1973"
        )
        # Either way, rejected
        assert result is False

    def test_consumer_protection_query_accepts_consumer_protection_act(self) -> None:
        text = (
            "THE CONSUMER PROTECTION ACT, 2019\n"
            "(ACT NO. 35 OF 2019)\nARRANGEMENT OF SECTIONS\n"
            "1. Short title.\n"
            + PADDING
        )
        assert is_meaningful_act_text(text, expected_title="Consumer Protection Act 2019") is True


def test_no_title_check_when_expected_title_none() -> None:
    """expected_title=None makes the function fall back to length + markers +
    ascii only (used for ad-hoc verification)."""
    # No title check at all
    text = "THE FAKE ACT\nACT NO. 1 OF 2099\nShort title\n" + PADDING
    assert is_meaningful_act_text(text, expected_title=None) is True
