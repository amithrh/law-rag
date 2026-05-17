"""Verifier sentence-segmentation + citation-verification tests.

The verifier is the citation-correctness gate. The two correctness invariants:

  1. **Segmentation correctness on legal text.** Legal abbreviations like
     "Sec.", "v.", "Ors.", "Hon'ble Mr." must not split a sentence mid-citation.
     pysbd handles most cases; we add regression tests for known stumbling blocks.

  2. **Verdict correctness.** Per-sentence index check + coverage check must
     produce OK / UNSUPPORTED / UNKNOWN_CITATION / META correctly.

NLI integration tests live separately (require the DeBERTa-v3-mnli model to be
downloaded). These tests skip NLI and exercise the index+coverage stage.
"""
from __future__ import annotations

import pytest

from apps.api.verifier import (
    SentenceStatus,
    parse_citation_tags,
    segment_sentences,
    verify_answer,
    verify_sentence,
)


# -------------------- citation-tag parsing ---------------------------------

class TestParseCitationTags:
    def test_single_tag(self) -> None:
        assert parse_citation_tags("The court held [3].") == [3]

    def test_multiple_consecutive_tags(self) -> None:
        assert parse_citation_tags("As established earlier [1][2].") == [1, 2]
        assert parse_citation_tags("Also see [3][5][7].") == [3, 5, 7]

    def test_no_tags(self) -> None:
        assert parse_citation_tags("Plain factual claim without citation.") == []

    def test_tag_inside_quote(self) -> None:
        assert parse_citation_tags('"The Act [12] provides…" said the petitioner.') == [12]

    def test_double_digit_tags(self) -> None:
        assert parse_citation_tags("The relevant ratio appears at [42] of the judgment.") == [42]


# -------------------- sentence segmentation on legal text ------------------

class TestSegmentSentences:
    def test_normal_sentences(self) -> None:
        text = "First sentence. Second sentence. Third one."
        out = segment_sentences(text)
        assert len(out) == 3
        assert out[0] == "First sentence."
        assert out[1] == "Second sentence."

    def test_section_abbreviation_does_not_split(self) -> None:
        """`Sec. 5` should not be split at "Sec.""."""
        text = "The petitioner relied on Sec. 5 of the Act. The respondent disagreed."
        out = segment_sentences(text)
        assert len(out) == 2, f"split incorrectly on 'Sec.': got {out}"
        assert "Sec. 5" in out[0]

    def test_v_abbreviation_does_not_split(self) -> None:
        """`X v. Y` (party-name abbreviation) should not be split."""
        text = "The court in Kesavananda Bharati v. State of Kerala laid down the basic structure doctrine. This was reaffirmed later."
        out = segment_sentences(text)
        assert len(out) == 2, f"split incorrectly on 'v.': got {out}"
        assert "Kesavananda Bharati v. State of Kerala" in out[0]

    def test_ors_abbreviation_pysbd_known_limitation(self) -> None:
        """KNOWN LIMITATION: pysbd splits on "Ors." when followed by a verb
        starting with lowercase (e.g. "Ors. was allowed"). This degrades
        verifier accuracy because a citation tag at the end of the original
        sentence ends up on what pysbd thinks is the second fragment.

        Mitigations (post-slice work tracked in PLAN §4.3 safety net):
          - re-segmentation pass after stream that merges adjacent fragments
            sharing a citation
          - move to blingfire or a legal-trained segmenter

        For now this test documents the limitation so we don't regress
        OTHER abbreviation handling while fixing this one.
        """
        text = "The appeal in ABC Co. v. XYZ & Ors. was allowed by this Court. The matter was remanded."
        out = segment_sentences(text)
        # Today: pysbd produces 3 segments (split on Ors.)
        # Future: we want exactly 2 after mitigation lands
        assert 2 <= len(out) <= 3, f"unexpected segment count: got {out}"
        # Verify the next fragment still contains the verb (so the safety
        # net can detect "verb fragment" and merge backward)
        if len(out) == 3:
            assert "was allowed" in out[1] or "was allowed" in out[0]

    def test_honble_abbreviation_does_not_split(self) -> None:
        # pysbd handles "Hon'ble Mr.|Hon'ble Justice" in most cases. Verify.
        text = "The judgment was authored by Hon'ble Mr. Justice Karol. He observed the following."
        out = segment_sentences(text)
        assert len(out) == 2, f"split incorrectly on 'Mr.': got {out}"

    def test_citation_at_sentence_end_preserved(self) -> None:
        """Sentences ending with [N]. must not be split at [N]."""
        text = "The respondent's argument was without merit [3]. The Court therefore allowed the appeal [4]."
        out = segment_sentences(text)
        assert len(out) == 2
        assert "[3]" in out[0]
        assert "[4]" in out[1]

    def test_empty_string(self) -> None:
        assert segment_sentences("") == []

    def test_no_terminal_punctuation(self) -> None:
        """A trailing fragment without a terminator should still be returned."""
        out = segment_sentences("A partial sentence")
        assert len(out) >= 1
        assert "partial sentence" in " ".join(out)


# -------------------- single-sentence verification -------------------------

class TestVerifySentence:
    def setup_method(self) -> None:
        self.idx_map = {
            1: "The court held that the petitioner was entitled to relief under Section 12.",
            2: "The respondent failed to deliver the goods within the agreed timeline.",
            3: "Costs of Rs. 50,000 were awarded to the petitioner.",
        }

    def test_well_cited_sentence_passes(self) -> None:
        s = "The petitioner was entitled to relief [1]."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.OK
        assert v.citations == [1]

    def test_uncited_factual_sentence_flagged_unsupported(self) -> None:
        s = "The respondent's actions clearly violated consumer law."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED
        assert v.citations == []
        assert "no citation" in v.reason.lower()

    def test_unknown_citation_flagged(self) -> None:
        """Citation [99] refers to a passage that doesn't exist."""
        s = "The relief was granted as established [99]."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNKNOWN_CITATION
        assert 99 in v.citations
        assert "not in retrieved set" in v.reason or "99" in v.reason

    def test_section_header_is_meta(self) -> None:
        """`**Short answer**` etc. are designated meta-sentences."""
        s = "**Short answer**"
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.META

    def test_refusal_line_is_meta(self) -> None:
        s = "The sources I have don't cover this clearly. I won't guess."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.META

    def test_lawyer_disclaimer_is_meta(self) -> None:
        s = "Talk to a lawyer for your specific situation."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.META

    def test_multiple_citations_resolve(self) -> None:
        s = "The court awarded costs and reaffirmed the timeline [2][3]."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.OK
        assert v.citations == [2, 3]


# -------------------- full-answer verification -----------------------------

class TestVerifyAnswer:
    def setup_method(self) -> None:
        self.idx_map = {
            1: "Section 12 of the Consumer Protection Act provides for District Forums.",
            2: "The forum has jurisdiction up to twenty lakh rupees.",
        }

    def test_clean_answer(self) -> None:
        text = (
            "**Short answer**\n"
            "You can file a complaint with the District Forum [1]. "
            "The forum's jurisdiction is up to twenty lakh rupees [2]."
        )
        v = verify_answer(text, self.idx_map, skip_nli=True)
        assert v.unsupported_count == 0
        # 1 meta + 2 OK
        ok = [s for s in v.sentences if s.status == SentenceStatus.OK]
        meta = [s for s in v.sentences if s.status == SentenceStatus.META]
        assert len(ok) == 2
        assert len(meta) == 1

    def test_answer_with_one_uncited_claim(self) -> None:
        text = (
            "The forum has jurisdiction [2]. "
            "You will probably win your case."  # uncited
        )
        v = verify_answer(text, self.idx_map, skip_nli=True)
        assert v.unsupported_count == 1
        # Skip ratio: 1 unsupported out of 2 emitted (1.0 - excluding meta) = 0.5
        assert v.skip_ratio > 0.0

    def test_answer_all_uncited(self) -> None:
        text = "First claim with no citation. Second claim also without."
        v = verify_answer(text, self.idx_map, skip_nli=True)
        assert v.unsupported_count == 2
        assert v.skip_ratio == 1.0


# -------------------- NLI integration (real model) -------------------------

class TestNLIIntegration:
    """End-to-end NLI tests. Need DeBERTa-v3-base-mnli loaded — skip if not."""

    @pytest.mark.needs_models
    @pytest.mark.slow
    def test_entailing_sentence_passes_with_high_score(self) -> None:
        from apps.api.verifier import nli_score
        s = nli_score(
            premise="Anticipatory bail under Section 438 of the CrPC can be granted even after an FIR is filed.",
            hypothesis="You can apply for anticipatory bail even if an FIR has already been filed.",
        )
        assert s is not None
        assert s > 0.7, f"expected high entailment, got {s}"

    @pytest.mark.needs_models
    @pytest.mark.slow
    def test_contradicting_sentence_scored_low(self) -> None:
        from apps.api.verifier import nli_score
        s = nli_score(
            premise="No confession made to a police officer shall be proved against the accused.",
            hypothesis="Police confessions are admissible as evidence against the accused.",
        )
        assert s is not None
        assert s < 0.2, f"expected very low entailment for contradiction, got {s}"

    @pytest.mark.needs_models
    @pytest.mark.slow
    def test_verify_sentence_with_nli_marks_weak_support(self) -> None:
        """A sentence whose cited passage doesn't entail it should be flagged
        weak_support (entailment below threshold)."""
        idx_map = {
            1: "The court awarded costs of Rs. 50,000 to the petitioner.",
        }
        # Hypothesis claims something not supported by the premise (different amount)
        sentence = "The court awarded Rs. 5,00,000 in compensation [1]."
        v = verify_sentence(sentence, idx_map, skip_nli=False, nli_threshold=0.5)
        # Either weak_support OR ok with low score; both surface the discrepancy
        assert v.entailment_score is not None
        assert v.entailment_score < 0.5, f"expected low entailment, got {v.entailment_score}"
        assert v.status == SentenceStatus.WEAK_SUPPORT

    @pytest.mark.needs_models
    @pytest.mark.slow
    def test_verify_sentence_with_nli_marks_ok_for_supported_claim(self) -> None:
        idx_map = {
            1: "Anticipatory bail under Section 438 of the CrPC may be granted even after an FIR has been filed.",
        }
        sentence = "Anticipatory bail can be granted after an FIR is filed [1]."
        v = verify_sentence(sentence, idx_map, skip_nli=False, nli_threshold=0.5)
        assert v.status == SentenceStatus.OK
        assert v.entailment_score is not None
        assert v.entailment_score > 0.5
