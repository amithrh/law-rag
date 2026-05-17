"""Tests for the judgment chunker.

The judgment chunker is simpler than the act chunker — judgments have either
numbered paragraphs (^\\s*N\\.\\s) or no structure (fallback to semantic windows).
The invariants we care about are the same:

1. Citation correctness: chunk `#para-N` should contain section N's text,
   not section M's.
2. No silent content loss: every non-empty portion of the judgment ends up
   in some chunk.
3. Anchor format URL-safe and stable.
4. Sub-split chunks (`#para-N-a`, `#para-N-b`) preserve paragraph context.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chunking.judgment import (
    PARA_MAX_TOKENS,
    SEMANTIC_TARGET_TOKENS,
    chunk_judgment,
)
from chunking.types import ChunkStrategy


# -------------------- numbered-paragraph path -------------------------------

NUMBERED_JUDGMENT = """[2024] 5 S.C.R. 596 : 2024 INSC 446
TAMIL NADU MEDICAL SERVICES CORPORATION LTD.
v.
TAMIL NADU MEDICAL SERVICES CORPORATION EMPLOYEES WELFARE UNION
(Civil Appeal No. 6511 of 2024)
17 May 2024
[Sanjay Karol and Prasanna Bhalachandra Varale, JJ.]

1. Leave granted.

2. Heard learned counsel for the parties.

3. The present appeal challenges the order of the High Court dated 10.09.2018, whereby the
respondent-Union was granted relief of permanent status to its workmen.

4. The factual matrix may be briefly stated. The appellant-Corporation, originally formed as
"Tamil Nadu Medical Services Corporation Limited", is a State Government Undertaking, fully owned
and operated by the Government of Tamil Nadu. It was established with the objective of
streamlining the supply chain of essential medicines and surgical items to public hospitals.

5. The respondent-Union represents employees of the appellant-Corporation. The dispute centres
around the applicability of the Tamil Nadu Industrial Establishments (Conferment of Permanent
Status to Workmen) Act, 1981 to the parties.

6. Ordered accordingly.
"""


def test_numbered_judgment_produces_para_chunks():
    chunks = list(chunk_judgment("sc/2024/insc-446", NUMBERED_JUDGMENT))
    para_anchors = [c.anchor for c in chunks if "#para-" in c.anchor and "header" not in c.anchor]
    # 6 numbered paragraphs in the fixture
    assert len(para_anchors) >= 5  # allow for sub-splits
    # Each anchor should have form 'sc/2024/insc-446#para-N' optionally suffixed
    for a in para_anchors:
        assert a.startswith("sc/2024/insc-446#para-")


def test_numbered_judgment_header_emitted_when_substantial():
    """The pre-paragraph header (caption + bench) should be its own chunk."""
    chunks = list(chunk_judgment("sc/2024/insc-446", NUMBERED_JUDGMENT))
    headers = [c for c in chunks if c.anchor.endswith("#header")]
    assert len(headers) == 1
    # The header should contain the case citation and parties
    assert "TAMIL NADU MEDICAL SERVICES" in headers[0].text
    assert "2024 INSC 446" in headers[0].text


def test_numbered_judgment_paragraph_chunks_contain_correct_content():
    """Anchor `#para-N` must contain content semantically from paragraph N
    (not paragraph M). Citation-correctness invariant.
    """
    chunks = list(chunk_judgment("sc/2024/insc-446", NUMBERED_JUDGMENT))
    # Known content per paragraph in the fixture
    expected = {
        "1": ["Leave granted"],
        "2": ["Heard learned counsel"],
        "3": ["challenges the order of the High Court", "10.09.2018"],
        "4": ["Tamil Nadu Medical Services Corporation"],
        "5": ["respondent-Union"],
        "6": ["Ordered accordingly"],
    }
    for para_no, expected_phrases in expected.items():
        # Find the chunk(s) anchored for this para
        matches = [c for c in chunks
                   if c.anchor == f"sc/2024/insc-446#para-{para_no}"
                   or c.anchor.startswith(f"sc/2024/insc-446#para-{para_no}-")]
        assert matches, f"no chunk for para-{para_no}"
        combined = " ".join(c.text for c in matches)
        for phrase in expected_phrases:
            assert phrase in combined, (
                f"para-{para_no} chunk(s) missing expected content {phrase!r}: "
                f"got {combined[:200]!r}"
            )


def test_numbered_judgment_short_paragraphs_kept_as_single_chunks():
    """Para like '1. Leave granted.' is short but legitimate; must NOT be merged."""
    chunks = list(chunk_judgment("sc/2024/insc-446", NUMBERED_JUDGMENT))
    para_1 = [c for c in chunks if c.anchor.endswith("#para-1")]
    assert len(para_1) == 1
    assert para_1[0].token_count > 0
    assert "Leave granted" in para_1[0].text


# -------------------- oversize paragraph sub-split --------------------------

def test_oversize_paragraph_subsplits_with_a_b_c_suffixes():
    """A single numbered paragraph >1000 tokens must be sub-split with
    suffixes a, b, c, ... Use a fixture with 5+ paragraphs (so the chunker
    chooses the numbered-paragraph strategy, not semantic-window) and an
    oversize paragraph-1 to force sub-splitting.
    """
    sentences = [
        f"This is sentence number {i} in the appellant's submissions concerning "
        f"the consumer protection act and the relief sought by the petitioner."
        for i in range(60)
    ]
    long_body = " ".join(sentences)  # well over PARA_MAX_TOKENS
    text = (
        f"1. {long_body}\n"
        f"2. The respondent's counter-submissions are summarized below.\n"
        f"3. The court considered both sides at length.\n"
        f"4. The judgment was reserved for further hearing.\n"
        f"5. The judgment was pronounced today.\n"
        f"6. Ordered accordingly.\n"
    )

    chunks = list(chunk_judgment("test-doc", text))
    # Must be in numbered-paragraph mode
    assert any(c.chunk_strategy == ChunkStrategy.NUMBERED_PARAGRAPH for c in chunks), (
        "Expected numbered-paragraph strategy for a doc with 6 numbered paras; "
        f"got strategies: {set(c.chunk_strategy.value for c in chunks)}"
    )
    sub_anchors = [c.anchor for c in chunks if c.anchor.startswith("test-doc#para-1-")]
    assert len(sub_anchors) >= 2, (
        f"expected sub-splits for ~3000-token paragraph, got: {sub_anchors}"
    )
    suffixes = [a.split("#para-1-")[1] for a in sub_anchors]
    assert all(len(s) == 1 and s.isalpha() for s in suffixes), (
        f"sub-suffixes should be single letters: {suffixes}"
    )


# -------------------- semantic-window fallback ------------------------------

UNNUMBERED_JUDGMENT = """The Court delivered its judgment as follows.

The petitioner was aggrieved by the order of the District Forum dated
05.05.2020 dismissing her complaint on technical grounds. The complaint
alleged that the respondent had failed to deliver a refrigerator within
the agreed time period and had subsequently refused to refund the purchase
amount despite repeated demands.

The respondent contended that the petitioner had agreed to extended delivery
timelines via WhatsApp communication, and that the alleged communications
constituted a contractual modification under the Indian Contract Act, 1872.

The Court, after hearing both sides at length, observed that the WhatsApp
communications relied upon by the respondent were ambiguous and could not
be construed as unequivocal acceptance of the modified delivery schedule.
Further, the principles of consumer protection mandate that the consumer's
rights cannot be diluted by post-facto contractual modifications imposed
without clear and informed consent.

Accordingly, the impugned order is set aside, and the complaint is restored
to file before the District Forum with directions to dispose of the same
on merits within three months.
"""


def test_unnumbered_judgment_uses_semantic_windows():
    chunks = list(chunk_judgment("sc/2020/insc-xxx", UNNUMBERED_JUDGMENT))
    # Should fall back to window strategy
    win_anchors = [c.anchor for c in chunks if "#win-" in c.anchor]
    assert win_anchors, f"expected #win- anchors, got: {[c.anchor for c in chunks]}"
    for c in chunks:
        if "#win-" in c.anchor:
            assert c.chunk_strategy == ChunkStrategy.SEMANTIC_WINDOW


def test_unnumbered_judgment_window_anchors_are_sequential():
    chunks = list(chunk_judgment("sc/2020/insc-xxx", UNNUMBERED_JUDGMENT))
    win_anchors = sorted(c.anchor for c in chunks if "#win-" in c.anchor)
    win_nums = [int(a.split("#win-")[1]) for a in win_anchors]
    # 0, 1, 2, ... no gaps
    assert win_nums == list(range(len(win_nums)))


# -------------------- anchor format -----------------------------------------

def test_anchors_are_url_safe():
    chunks = list(chunk_judgment("sc/2024/insc-446", NUMBERED_JUDGMENT))
    for c in chunks:
        assert " " not in c.anchor
        assert "\n" not in c.anchor
        assert c.anchor.isascii()


def test_empty_paragraphs_skipped():
    text = """1. First substantive paragraph here. With some content.

2.

3. Third paragraph, second was empty.
"""
    chunks = list(chunk_judgment("test-doc", text))
    para_anchors = [c.anchor for c in chunks if "#para-" in c.anchor and "header" not in c.anchor]
    # Empty para-2 should not produce a chunk
    assert "test-doc#para-2" not in para_anchors


# -------------------- real-data smoke test ----------------------------------

SC_JSONL = Path(__file__).parent.parent.parent.parent / "data" / "processed" / "sc" / "year=2024.jsonl"


@pytest.mark.skipif(not SC_JSONL.exists(), reason="data/processed/sc/year=2024.jsonl not present")
class TestRealJudgmentSmoke:
    @pytest.fixture(scope="class")
    def sample_judgments(self) -> list[dict]:
        """Take the first 5 SC judgments from 2024 for real-data testing."""
        out = []
        with SC_JSONL.open() as f:
            for line in f:
                row = json.loads(line)
                if row.get("subject_area") is None:
                    continue
                out.append(row)
                if len(out) >= 5:
                    break
        return out

    def test_real_sc_judgments_produce_at_least_some_chunks(
        self, sample_judgments: list[dict],
    ) -> None:
        for row in sample_judgments:
            chunks = list(chunk_judgment(row["case_id"].replace(" ", "-").lower(), row["text"]))
            assert chunks, f"no chunks produced for {row['case_id']}"

    def test_real_sc_judgments_have_consistent_anchor_prefix(
        self, sample_judgments: list[dict],
    ) -> None:
        for row in sample_judgments:
            doc_id = row["case_id"].replace(" ", "-").lower()
            for c in chunk_judgment(doc_id, row["text"]):
                assert c.anchor.startswith(doc_id), (
                    f"chunk anchor {c.anchor} doesn't share doc_id {doc_id}"
                )

    def test_real_sc_judgment_chunk_strategies_set(
        self, sample_judgments: list[dict],
    ) -> None:
        seen_strategies: set[str] = set()
        for row in sample_judgments:
            for c in chunk_judgment(row["case_id"], row["text"]):
                seen_strategies.add(c.chunk_strategy.value)
        # At least one strategy must show up — most modern SC judgments are
        # numbered_paragraph, but the chunker must handle the fallback too.
        assert seen_strategies, "no chunks at all across 5 sample judgments"
