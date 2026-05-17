"""Tests for the cross-encoder rerank pass.

The reranker is loaded lazily on first call; these tests avoid actually
loading bge-reranker-v2-m3 by patching _RerankerWorker.score_pairs. The
real model is verified in `test_rerank_integration_reorders_results`
(marked `needs_models`, skipped by default).
"""
from __future__ import annotations

from datetime import date

import pytest

from apps.api import rerank as rerank_module
from apps.api.rerank import rerank
from apps.api.retrieval import RetrievedChunk


def _chunk(idx: int, text: str, dense: float = 0.5, bm25: float = 0.0) -> RetrievedChunk:
    """Construct a RetrievedChunk with minimal scaffolding for testing."""
    return RetrievedChunk(
        chunk_id=idx, document_id=idx, anchor=f"test/sec-{idx}",
        text=text, source_type="bare_act", subject_area=None,
        as_at=None, paragraph_no=None, title=f"doc-{idx}",
        citation=None, court=None, statute_short=None,
        dense_score=dense, bm25_score=bm25,
    )


def _patch_score_pairs(monkeypatch, scores: list[float]) -> None:
    """Patch the reranker worker to return preset scores."""

    class _Stub:
        def is_available(self) -> bool:
            return True

        def score_pairs(self, query, passages):
            assert len(passages) == len(scores), (
                f"test wired wrong: {len(passages)} passages vs {len(scores)} scores"
            )
            return scores

    monkeypatch.setattr(rerank_module, "get_reranker", lambda: _Stub())


def test_rerank_reorders_by_rerank_score(monkeypatch):
    """Reranker scores override the input order — even if dense said
    chunk A is most relevant, a high cross-encoder score for chunk C
    should move C to the top.
    """
    chunks = [
        _chunk(1, "A — first by dense", dense=0.95, bm25=0.5),
        _chunk(2, "B — second by dense", dense=0.85, bm25=0.4),
        _chunk(3, "C — third by dense", dense=0.75, bm25=0.3),
    ]
    # Reranker says chunk C is best, B middle, A worst
    _patch_score_pairs(monkeypatch, [0.1, 0.5, 0.9])

    out = rerank("some query", chunks)
    assert [c.chunk_id for c in out] == [3, 2, 1]
    # Each chunk now carries its rerank_score
    assert out[0].rerank_score == 0.9
    assert out[1].rerank_score == 0.5
    assert out[2].rerank_score == 0.1


def test_rerank_respects_keep_top_n(monkeypatch):
    chunks = [_chunk(i, f"chunk {i}") for i in range(10)]
    _patch_score_pairs(monkeypatch, list(reversed(range(10))))  # 9..0 → chunk 0 best
    out = rerank("query", chunks, keep=3)
    assert len(out) == 3
    # Top 3 by rerank score should be the ones the reranker scored 9, 8, 7
    assert [c.chunk_id for c in out] == [0, 1, 2]


def test_rerank_passes_through_when_reranker_unavailable(monkeypatch):
    """If the reranker model can't load, we return the input list unchanged
    rather than blocking retrieval.
    """

    class _UnavailableStub:
        def is_available(self) -> bool:
            return False

        def score_pairs(self, query, passages):
            return None

    monkeypatch.setattr(rerank_module, "get_reranker", lambda: _UnavailableStub())

    chunks = [_chunk(1, "first"), _chunk(2, "second"), _chunk(3, "third")]
    out = rerank("query", chunks)
    # Input order preserved (no reranking happened)
    assert [c.chunk_id for c in out] == [1, 2, 3]
    # None of the chunks got a rerank_score
    assert all(c.rerank_score is None for c in out)


def test_rerank_passes_through_on_predict_failure(monkeypatch):
    """If score_pairs returns None (predict failed mid-flight), pass through."""

    class _FailStub:
        def is_available(self) -> bool:
            return True

        def score_pairs(self, query, passages):
            return None

    monkeypatch.setattr(rerank_module, "get_reranker", lambda: _FailStub())
    chunks = [_chunk(1, "first"), _chunk(2, "second")]
    out = rerank("query", chunks)
    assert [c.chunk_id for c in out] == [1, 2]


def test_rerank_empty_list_returns_empty(monkeypatch):
    """No chunks → no calls to score_pairs, no errors."""
    out = rerank("query", [])
    assert out == []


# --- Integration (uses the actual bge-reranker model) ----------------------

@pytest.mark.needs_models
@pytest.mark.slow
def test_rerank_integration_reorders_results():
    """End-to-end with the real model. Verify the reranker correctly
    promotes a passage that's semantically more relevant than what dense
    scoring picked first.
    """
    chunks = [
        # Dense gave this top score, but it's about an unrelated topic
        _chunk(1, "The court ordered specific performance of the agreement.", dense=0.95),
        # This is the actually-relevant passage for the query below
        _chunk(2, "Section 12 of the Consumer Protection Act 2019 sets up the District Consumer Disputes Redressal Commission with jurisdiction up to twenty lakh rupees.", dense=0.50),
        _chunk(3, "The petitioner filed an appeal against the High Court order.", dense=0.40),
    ]
    out = rerank("What is the jurisdiction of the District Consumer Forum?", chunks, keep=3)
    # The relevant Consumer Protection passage should rank above the
    # unrelated specific-performance one
    rank_of = {c.chunk_id: i for i, c in enumerate(out)}
    assert rank_of[2] < rank_of[1], (
        f"reranker failed to promote relevant passage; got order: "
        f"{[c.chunk_id for c in out]}"
    )
