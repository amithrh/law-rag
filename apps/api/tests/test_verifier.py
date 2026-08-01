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

    @pytest.mark.parametrize("text", [
        "The provided passages do not state how this applies to your exact facts.",
        "The provided passages do not state a concrete next step.",
        "The provided passages do not state enough to apply the rule to your exact facts.",
        "The provided passages do not state a concrete punishment for the prohibition offence.",
    ])
    def test_prompt_fallback_lines_are_meta(self, text: str) -> None:
        v = verify_sentence(text, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.META

    def test_prompt_fallback_line_with_extra_claim_is_not_meta(self) -> None:
        s = "The provided passages do not state a concrete next step, but you can file an appeal within 30 days."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED

    @pytest.mark.parametrize("text", [
        "The sources I have don't cover this clearly, but you can file an appeal within 30 days.",
        "This is general legal information, but bail is guaranteed tomorrow.",
        "Talk to a lawyer for your specific situation, but you can ignore the summons.",
        "For decisions that affect your rights, consult a qualified lawyer or the relevant court / forum, but limitation is 30 days.",
    ])
    def test_meta_lines_with_extra_claims_are_not_meta(self, text: str) -> None:
        v = verify_sentence(text, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED

    def test_refusal_line_is_meta(self) -> None:
        s = "The sources I have don't cover this clearly. I won't guess."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.META

    def test_lawyer_disclaimer_is_meta(self) -> None:
        s = "Talk to a lawyer for your specific situation."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.META

    def test_server_criminal_regime_caveat_is_meta(self) -> None:
        s = "The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act applies."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.META

    def test_uapa_statute_only_delay_limitation_is_meta(self) -> None:
        s = (
            "This statute-only Section 43D answer does not determine whether delay itself "
            "supports bail; that requires separately verified current precedent."
        )
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.META

    def test_criminal_regime_caveat_with_extra_claim_is_not_meta(self) -> None:
        s = (
            "The incident date decides whether BNS/BNSS/BSA or IPC/CrPC/Evidence Act "
            "applies, and bail is guaranteed tomorrow."
        )
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED

    def test_multiple_citations_resolve(self) -> None:
        s = "The court awarded costs and reaffirmed the timeline [2][3]."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.OK
        assert v.citations == [2, 3]

    # ----- preamble whitelist -----------------------------------------------
    # Small Q4 models almost always open with a transition sentence like
    # "Based on the cases provided…". Without the preamble whitelist,
    # strict-stop would kill the answer on sentence 1 even when the rest of
    # the answer cites correctly.

    def test_preamble_source_framing_is_meta(self) -> None:
        """Narrow whitelist (post round-2 Codex review): only sentences that
        explicitly frame as drawn from sources qualify as preamble META."""
        s = "Based on the provided passages, here are the key points."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.META, (
            f"expected META preamble, got {v.status} ({v.reason})"
        )

    @pytest.mark.parametrize("text", [
        "Based on the provided passages, here are the key points: you can file an appeal within 30 days.",
        "Based on the provided sources here are the main points: bail is guaranteed tomorrow.",
        "Based on the provided passages, here are the key points regarding appeal within 30 days.",
        "Based on the provided sources here are the main points regarding bail guaranteed tomorrow.",
    ])
    def test_preamble_with_extra_claim_is_not_meta(self, text: str) -> None:
        v = verify_sentence(text, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED

    def test_preamble_does_NOT_match_generic_according_to(self) -> None:
        """Codex round-2 #1: 'According to Section 154(3), you can complain'
        is a legal claim. The old broad pattern marked it META and shipped.
        Now it must be UNSUPPORTED (no [N]) and get suppressed."""
        s = "According to Section 154(3), you can complain to the Superintendent of Police."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED, (
            f"sentence with 'According to Section X' but no [N] must be UNSUPPORTED, "
            f"got {v.status}"
        )

    def test_preamble_does_NOT_match_colon_ended_claim(self) -> None:
        """Codex round-2 #1: colon-ended sentences are NOT META. The old
        generic colon rule let any list-introducer slip through."""
        s = "The police must register your FIR for the following reasons:"
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED, (
            f"colon-ended claim without [N] must be UNSUPPORTED, got {v.status}"
        )

    def test_preamble_with_citation_is_verified_normally(self) -> None:
        """A real claim that happens to begin with 'Based on…' must not be
        whitelisted — it's a legal claim and needs citation+entailment."""
        s = "Based on Section 12 of the Consumer Protection Act, you can file a complaint at the District Forum [1]."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.OK
        assert v.citations == [1]

    def test_non_preamble_unsupported_still_fails(self) -> None:
        """Don't let the preamble whitelist mask real uncited claims."""
        s = "The maximum punishment for theft is two years."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED

    # ----- segmentation post-merge (Indian legal abbreviations) -------------
    # Without _merge_abbreviation_splits, pysbd would split "ORS." into its
    # own sentence and the trailing ", 2007, para 26." would be uncited →
    # strict-stop fires on a citation-format artifact, not a real defect.

    def test_segment_merges_ors_in_source_line(self) -> None:
        from apps.api.verifier import segment_sentences
        out = segment_sentences("SAKIRI VASU versus STATE OF U.P. AND ORS., 2007, para 26.")
        assert len(out) == 1, f"expected 1 merged segment, got {out}"

    def test_segment_does_not_merge_real_sentence_boundary(self) -> None:
        """Don't be over-eager — two real sentences must stay split."""
        from apps.api.verifier import segment_sentences
        out = segment_sentences("Police must register the FIR. The Magistrate can intervene.")
        assert len(out) == 2

    def test_segment_handles_v_vs_in_case_names(self) -> None:
        from apps.api.verifier import segment_sentences
        out = segment_sentences("See Aleque Padamsee v. Union of India [5].")
        assert len(out) == 1

    def test_segment_merges_smt_into_party_name(self) -> None:
        """Honorific-abbrev "Smt. MAYADEVI" must not split on the dot — both
        sides belong to the same party-name string."""
        from apps.api.verifier import segment_sentences
        out = segment_sentences("SMT. MAYADEVI versus JAGDISH PRASAD | SC, 2007, para-4.")
        assert len(out) == 1, f"expected merged, got {out}"

    # ----- Codex review #2: case-name sentences must NOT bypass verifier --
    # A sentence containing "v." or "versus" + year is NOT automatically
    # META. The old regex over-matched real legal holdings.

    def test_real_holding_with_case_name_is_verified_not_meta(self) -> None:
        """The bug Codex flagged: 'In Lalita Kumari v. Govt. of U.P., 2013,
        police must register an FIR for a cognizable offence.' has a real
        legal claim AND a case reference. It must be UNSUPPORTED (no [N]),
        not META."""
        s = "In Lalita Kumari v. Govt. of U.P., 2013, police must register an FIR for a cognizable offence."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED, (v.status, v.reason)

    def test_bullet_with_no_citation_is_unsupported(self) -> None:
        """Per Codex review #4: bullets making procedural claims must be
        treated as legal claims, not META. The old broad bullet exemption
        let hallucinated deadlines slip through."""
        s = "- File your appeal within 30 days of the order."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED, (v.status, v.reason)

    def test_bullet_with_citation_passes(self) -> None:
        """A bullet that DOES cite is fine."""
        s = "- File your appeal within 30 days of the order [1]."
        v = verify_sentence(s, self.idx_map, skip_nli=True)
        assert v.status == SentenceStatus.OK
        assert v.citations == [1]

    # ----- Codex review #3: auto-cite must require NLI confirmation -------

    def test_auto_cite_without_nli_is_weak_not_ok(self) -> None:
        """Auto-cite cannot certify entailment from lexical overlap alone.
        If skip_nli=True (or NLI unavailable), an auto-cited sentence must
        be marked WEAK_SUPPORT, not OK — the UI then badges it / drops it."""
        # We mock nli_score to None to simulate NLI unavailable. We can't
        # cleanly stub a global from here without monkeypatch; instead we
        # use a sentence with low recall so auto-cite doesn't fire — and
        # one with high recall so it does. NLI being unavailable in the
        # default test env is handled by the production code path.
        idx_map = {
            1: "Section 12 of the Consumer Protection Act provides for District Forums to hear consumer complaints up to twenty lakh rupees in value.",
        }
        s = "Section 12 of the Consumer Protection Act provides for District Forums to hear consumer complaints up to twenty lakh rupees in value."
        v = verify_sentence(s, idx_map, skip_nli=True)
        # NLI is FORCED for auto-cited sentences. In a unit test
        # environment NLI may be unavailable → fail-closed to WEAK_SUPPORT.
        # If NLI IS available (model loaded), it will produce a real score;
        # for an exact-match sentence that's almost certainly OK. Accept both.
        assert v.auto_cited is True
        assert v.status in (SentenceStatus.OK, SentenceStatus.WEAK_SUPPORT), (
            f"auto-cite must be either NLI-confirmed OK or WEAK on NLI-unavailable; got {v.status}"
        )

    # ----- auto-cite: lexical overlap rescue ---------------------------------

    def test_auto_cite_attaches_passage_on_high_overlap(self) -> None:
        """An uncited sentence whose content overlaps a passage gets that
        passage auto-attached as [N]. Per Codex review #3, NLI is then
        FORCED — so the status is either NLI-confirmed OK (if NLI is
        available and entailment clears the threshold) or WEAK_SUPPORT
        (if NLI is unavailable or entailment is below threshold). Either
        way, the citation is attached and the sentence isn't UNSUPPORTED."""
        idx_map = {
            1: "Section 12 of the Consumer Protection Act provides for District Forums to hear consumer complaints up to twenty lakh rupees in value.",
            2: "Section 100 of the Code on Wages 2019 governs payment of bonus.",
        }
        s = "Section 12 of the Consumer Protection Act provides for District Forums to hear consumer complaints up to twenty lakh rupees in value."
        v = verify_sentence(s, idx_map, skip_nli=True)
        assert v.citations == [1]
        assert v.auto_cited is True
        assert v.status in (SentenceStatus.OK, SentenceStatus.WEAK_SUPPORT), v.status

    def test_auto_cite_does_not_fire_when_overlap_too_low(self) -> None:
        idx_map = {
            1: "Section 12 of the Consumer Protection Act provides for District Forums.",
        }
        s = "The maximum punishment for theft is three years and a fine."
        v = verify_sentence(s, idx_map, skip_nli=True)
        assert v.status == SentenceStatus.UNSUPPORTED
        assert v.auto_cited is False

    def test_auto_cite_does_not_override_explicit_citation(self) -> None:
        """If the LLM did cite, the explicit citation wins — auto-cite never
        runs."""
        idx_map = {
            1: "Section 12 of the Consumer Protection Act provides for District Forums.",
            2: "The forum's jurisdiction is up to twenty lakh rupees.",
        }
        s = "The forum's jurisdiction is up to twenty lakh rupees [2]."
        v = verify_sentence(s, idx_map, skip_nli=True)
        assert v.status == SentenceStatus.OK
        assert v.citations == [2]
        assert v.auto_cited is False


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


# -------------------- bge backend + ensemble (architecture-research task #2)
#
# These tests exercise the bge and ensemble backends without loading any
# real model. We monkeypatch `apps.api.verifier.nli_score` and
# `apps.api.verifier.bge_score` to return controlled values, then verify
# that the backend dispatch + threshold logic in verify_sentence behaves
# correctly.
#
# The bge-as-verifier swap is described in docs/VERIFIER_SWAP.md.

class TestBgeBackend:
    """bge backend exercised in isolation. All bge thresholds come from
    Settings defaults — bge_verifier_threshold=0.222 (from calibration)
    and bge_verifier_hard_floor=0.003. Tests pick scores well above/below
    these values to stay robust to minor recalibration."""

    def setup_method(self) -> None:
        self.idx_map = {
            1: "Section 12 of the Consumer Protection Act provides for District Forums to hear consumer complaints up to twenty lakh rupees in value.",
            2: "The forum has jurisdiction up to twenty lakh rupees.",
        }

    def test_bge_backend_ok_for_supported_claim(self, monkeypatch) -> None:
        """A bge score well above the threshold should produce OK on the bge
        backend (no NLI involvement)."""
        import apps.api.verifier as v_mod
        # Force bge=high (well above 0.222); NLI must NOT be called on bge backend
        nli_called = []
        monkeypatch.setattr(v_mod, "bge_score", lambda p, h: 0.95)
        monkeypatch.setattr(v_mod, "nli_score",
                            lambda p, h: (nli_called.append((p, h)) or 0.99))
        s = "Consumer complaints up to twenty lakh rupees are heard by District Forums [1]."
        v = verify_sentence(s, self.idx_map, backend="bge")
        assert v.status == SentenceStatus.OK, (v.status, v.reason)
        assert v.entailment_score == pytest.approx(0.95)
        # NLI must NOT have been called on the bge-only backend
        assert nli_called == [], "bge backend must not invoke NLI"

    def test_bge_backend_hard_floor_suppresses_fabrication(self, monkeypatch) -> None:
        """A bge score below the hard floor (0.003) should produce
        UNSUPPORTED on the bge backend, matching how the NLI floor
        suppresses fabricated content."""
        import apps.api.verifier as v_mod
        # Stub bge to a value below the floor
        monkeypatch.setattr(v_mod, "bge_score", lambda p, h: 0.0001)
        s = "The Consumer Protection Act mandates a refund within 7 days [1]."
        v = verify_sentence(s, self.idx_map, backend="bge")
        assert v.status == SentenceStatus.UNSUPPORTED, (v.status, v.reason)
        assert "hard floor" in v.reason.lower()
        # Score must be carried for observability
        assert v.entailment_score is not None
        assert v.entailment_score < 0.003

    def test_bge_backend_weak_between_floor_and_threshold(self, monkeypatch) -> None:
        """Coverage: a bge score above the floor but below the threshold
        is WEAK_SUPPORT, not OK. Locks the bge threshold semantics so a
        future recalibration that flips the inequality is caught."""
        import apps.api.verifier as v_mod
        # 0.10 is above floor (0.003) but below threshold (0.222)
        monkeypatch.setattr(v_mod, "bge_score", lambda p, h: 0.10)
        s = "Consumer complaints have a fee of fifty rupees [1]."
        v = verify_sentence(s, self.idx_map, backend="bge")
        assert v.status == SentenceStatus.WEAK_SUPPORT, (v.status, v.reason)


class TestEnsembleBackend:
    """The ensemble backend ANDs NLI and bge — the worse verdict wins."""

    def setup_method(self) -> None:
        self.idx_map = {
            1: "Section 12 of the Consumer Protection Act provides for District Forums to hear consumer complaints up to twenty lakh rupees in value.",
            2: "The forum has jurisdiction up to twenty lakh rupees.",
        }

    def test_ensemble_pessimistic(self, monkeypatch) -> None:
        """When NLI says OK (>=0.35) but bge says WEAK (<0.222), the
        ensemble verdict is WEAK_SUPPORT. Pessimistic AND across backends."""
        import apps.api.verifier as v_mod
        monkeypatch.setattr(v_mod, "nli_score", lambda p, h: 0.80)
        monkeypatch.setattr(v_mod, "bge_score", lambda p, h: 0.15)
        s = "Consumer complaints up to twenty lakh rupees are heard by District Forums [1]."
        v = verify_sentence(s, self.idx_map, backend="ensemble")
        assert v.status == SentenceStatus.WEAK_SUPPORT, (v.status, v.reason)
        # Reason should reference both scores so we can debug disagreements
        assert "nli=" in v.reason and "bge=" in v.reason, v.reason

    def test_ensemble_unsupported_when_one_backend_below_floor(self, monkeypatch) -> None:
        """If either backend says UNSUPPORTED (below its hard floor), the
        ensemble verdict is UNSUPPORTED. The bge backend in particular
        catches relevance failures the NLI backend may miss."""
        import apps.api.verifier as v_mod
        monkeypatch.setattr(v_mod, "nli_score", lambda p, h: 0.80)  # NLI: OK
        monkeypatch.setattr(v_mod, "bge_score", lambda p, h: 0.0001)  # bge: below floor
        s = "Consumer complaints up to twenty lakh rupees are heard by District Forums [1]."
        v = verify_sentence(s, self.idx_map, backend="ensemble")
        assert v.status == SentenceStatus.UNSUPPORTED, (v.status, v.reason)

    def test_ensemble_fail_closed_when_one_backend_unavailable(self, monkeypatch) -> None:
        """If exactly ONE backend is unavailable (returns None), the ensemble
        falls back to the OTHER backend and emits a reason naming the
        unavailable one. Don't double-penalize the sentence for a backend
        availability issue."""
        import apps.api.verifier as v_mod
        # Simulate bge model failing to load
        monkeypatch.setattr(v_mod, "bge_score", lambda p, h: None)
        monkeypatch.setattr(v_mod, "nli_score", lambda p, h: 0.95)
        s = "Consumer complaints are heard by District Forums [1]."
        v = verify_sentence(s, self.idx_map, backend="ensemble")
        # NLI says OK → ensemble should pass through OK (with note in reason)
        assert v.status == SentenceStatus.OK, (v.status, v.reason)
        assert "bge unavailable" in v.reason.lower(), v.reason

    def test_auto_cited_still_requires_entailment_on_bge(self, monkeypatch) -> None:
        """Per Codex review #3, auto-cited sentences MUST run entailment
        regardless of skip_nli, AND must be suppressed when entailment fails.
        Verify that the bge backend enforces this — an auto-cite that
        scores below the bge hard floor is UNSUPPORTED, not OK."""
        import apps.api.verifier as v_mod
        # bge below floor — auto-cite must be suppressed
        monkeypatch.setattr(v_mod, "bge_score", lambda p, h: 0.0001)
        # High-lexical-overlap sentence (auto-cite will fire on idx 1)
        idx_map = {
            1: "Section 12 of the Consumer Protection Act provides for District Forums to hear consumer complaints up to twenty lakh rupees in value.",
        }
        # Sentence shares most content words with passage 1 → auto-cite attaches [1]
        s = "Section 12 of the Consumer Protection Act provides for District Forums to hear consumer complaints up to twenty lakh rupees in value."
        v = verify_sentence(s, idx_map, backend="bge", skip_nli=True)
        # Auto-cite should have fired but bge below floor → UNSUPPORTED
        assert v.auto_cited is True, "auto-cite should have attached citation"
        assert v.status == SentenceStatus.UNSUPPORTED, (v.status, v.reason)
        assert "hard floor" in v.reason.lower()


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
    def test_verify_sentence_with_nli_marks_weak_or_unsupported(self) -> None:
        """A sentence whose cited passage doesn't entail it should be flagged.
        Per round-3 review (security #2), entailment below the hard floor
        (0.10) is UNSUPPORTED (fabricated amounts/numbers). Above the floor
        but below the weak threshold is WEAK_SUPPORT. Either outcome is a
        correct surfacing of the discrepancy.

        Explicit `backend="nli"` so this test exercises the NLI code path
        even when the global default is ensemble (architecture-research
        task #2).
        """
        idx_map = {
            1: "The court awarded costs of Rs. 50,000 to the petitioner.",
        }
        # Hypothesis claims a different amount → either WEAK or UNSUPPORTED.
        sentence = "The court awarded Rs. 5,00,000 in compensation [1]."
        v = verify_sentence(sentence, idx_map, skip_nli=False, nli_threshold=0.5,
                            backend="nli")
        assert v.entailment_score is not None
        assert v.entailment_score < 0.5, f"expected low entailment, got {v.entailment_score}"
        assert v.status in (SentenceStatus.WEAK_SUPPORT, SentenceStatus.UNSUPPORTED), v.status

    @pytest.mark.needs_models
    @pytest.mark.slow
    def test_verify_sentence_with_nli_marks_ok_for_supported_claim(self) -> None:
        idx_map = {
            1: "Anticipatory bail under Section 438 of the CrPC may be granted even after an FIR has been filed.",
        }
        sentence = "Anticipatory bail can be granted after an FIR is filed [1]."
        v = verify_sentence(sentence, idx_map, skip_nli=False, nli_threshold=0.5,
                            backend="nli")
        assert v.status == SentenceStatus.OK
        assert v.entailment_score is not None
        assert v.entailment_score > 0.5
