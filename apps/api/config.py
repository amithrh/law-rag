"""App configuration loaded from .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Postgres — DATABASE_URL takes precedence; else assembled from components.
    # On Mac dev (host-side), connect to the docker-mapped port at localhost.
    # In production (api container in same docker network), connect via
    # service name `postgres` over the internal port 5432.
    database_url: str = ""
    postgres_host: str = "localhost"
    postgres_host_port: int = 5433
    postgres_internal_port: int = 5432
    postgres_db: str = "lawrag"
    postgres_user: str = "lawrag"
    postgres_password: str = ""

    @property
    def resolved_database_url(self) -> str:
        """Return a usable postgres URL. Priority:
          1. Explicit DATABASE_URL env var (preferred for production).
          2. Assembled from POSTGRES_* components, choosing the right
             port based on whether we appear to be running inside the
             docker network or on the host.

        Heuristic for component-assembled URLs:
          - If POSTGRES_HOST resolves to a hostname that's only reachable
            from inside docker (any non-localhost / non-127.* name),
            assume we're inside the network → use internal port 5432.
          - Else assume host-side dev → use the mapped host port (5433).
        """
        if self.database_url:
            return self.database_url
        host = self.postgres_host
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            port = self.postgres_host_port
        else:
            port = self.postgres_internal_port
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{host}:{port}/{self.postgres_db}"
        )

    @property
    def resolved_database_url_host_side(self) -> str:
        """Force the host-side variant (localhost:host_port) even when
        POSTGRES_HOST is set to a docker service name. Used by the API
        process when we know it's running on the host (Mac dev).
        """
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@localhost:{self.postgres_host_port}/{self.postgres_db}"
        )

    # Embeddings (host-side sentence-transformers on Mac per Q3 decision)
    embedding_backend: str = "ollama"     # 'mps' (host sentence-transformers) | 'ollama' | 'tei'
    embedding_model: str = "BAAI/bge-m3"
    embedding_max_seq_len: int = 512
    embedding_dim: int = 1024
    # Embedding runtime — which Python wrapper around BGE-M3 we load.
    #   * 'flag': FlagEmbedding's BGEM3FlagModel, which emits dense AND
    #     learned-sparse from a single forward pass. Required for
    #     multi-head retrieval (architecture-research Task #3).
    #   * 'st'  : sentence-transformers, dense head only. Faster cold start,
    #     but no sparse output. Use for ablation or environments where
    #     FlagEmbedding's transitive deps aren't installable.
    # Both load the same BAAI/bge-m3 weights; the swap is purely about
    # which output heads we get back.
    embedding_runtime: Literal["flag", "st"] = "flag"

    # LLM (Ollama)
    ollama_host_port: int = 11434
    # qwen3:14b (Apache-2.0) — dense 14B, hybrid thinking (we disable via
    # `think:false` in llm.py). Round-8 confirmed qwen3:32b is NOT a clean
    # win on this corpus: same battery scored 88% on 14b vs 84% on 32b
    # because 32b was more verbose → more sentences suppressed for not
    # citing. 14b is the better trade-off until we see a query class
    # where 32b clearly wins.
    llm_model: str = "qwen3:14b"
    llm_max_tokens: int = 1024

    # Retrieval
    bm25_top_k: int = 100
    dense_top_k: int = 100
    # Sparse top-K — number of candidates from the BGE-M3 learned-sparse
    # head before fusion. Sized to match the other heads so RRF treats the
    # three sources symmetrically.
    sparse_top_k: int = 100
    rerank_input_k: int = 50          # how many candidates the cross-encoder scores
    rerank_top_k: int = 20            # how many we return after rerank
    prompt_top_k: int = 8
    hnsw_ef_search: int = 40
    rerank_enabled: bool = True       # disable for ablation / when model unavailable
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    # Hybrid retrieval fusion config (architecture-research Task #3).
    #   * 'dense_bm25'        — legacy 70% dense / 30% bm25 weighted-sum.
    #     Kept for A/B comparison and as a fallback when the sparse column
    #     hasn't been backfilled.
    #   * 'dense_sparse_bm25' — RRF fusion of all three sources. This is
    #     the design from the audit recommendation (recall@20 = 53% →
    #     target ≥80%).
    # Override via env var: HYBRID_MODE=dense_bm25.
    hybrid_mode: Literal["dense_bm25", "dense_sparse_bm25"] = "dense_sparse_bm25"
    # RRF constant from the original Cormack et al. paper (k=60).
    # Standard across the IR community; well-behaved for top-K fusion
    # because the contribution of rank R is 1/(k+R) — rank 1 ≈ 0.0164,
    # rank 100 ≈ 0.00625, so deep matches still contribute non-trivially.
    rrf_k: int = 60

    # Verifier (PLAN §4.3)
    # Per Codex adversarial review #1: unsupported sentences are SUPPRESSED
    # from the user stream (main.py:_emit_and_check) rather than shipped
    # with a red strikethrough. So `skip_ratio_stop` here is no longer the
    # "what users see" knob — it's the "how bad does the answer have to be
    # before we show the stop banner instead of a partial answer" knob.
    # Battery v3 round-5 with qwen3:14b: 0.4 was triggering stop banners
    # on answers with 5-7 OK sentences (the model produced many uncited
    # claims that got silently dropped — the user-visible content was
    # fine, but the banner appeared because the model's *raw* output had
    # 5+ unsupported). Raised to 0.6 so the banner only appears when a
    # majority of intended sentences were bad.
    skip_ratio_stop: float = 0.6
    # Below this absolute unsupported count, drop silently (don't show a
    # stop banner). Critical: a single uncited sentence STILL gets dropped
    # — it just doesn't trigger the banner. The citation guarantee is
    # preserved by suppression, not by the banner.
    min_unsupported_before_stop: int = 2
    # NLI entailment score below which a cited sentence is flagged
    # weak_support. 0.5 was too harsh — paraphrased legal text consistently
    # scores 0.3-0.5 even when the cited passage clearly supports it
    # (battery v2 weak-support rates of 30-60% per subject confirmed this).
    nli_weak_support_below: float = 0.35
    # Per round-3 review (security #2): any cited sentence whose NLI score
    # falls below this hard floor is treated as UNSUPPORTED regardless of
    # `auto_cited` and SUPPRESSED from the user stream. The previous
    # WEAK_SUPPORT-with-badge behavior let fabricated content
    # (invented section numbers, made-up sub-section dates) ship as long
    # as the [N] index was real. Floor 0.10 is well below the typical
    # paraphrase scoring band (0.20-0.50) so genuine paraphrase still
    # surfaces as WEAK with a badge.
    nli_hard_floor: float = 0.10
    # Per deep-research report (May 2026): upgraded from base-mnli (184M,
    # general MNLI only) to the large variant trained on 5 datasets
    # (MNLI + FEVER + ANLI + LingNLI + WANLI ≈ 885K pairs). FEVER is
    # claim-verification (exactly our use case) and ANLI is adversarial
    # — both meaningfully more robust on paraphrased legal English. The
    # base variant was scoring 30-60% of legitimate cited sentences as
    # weak_support; the large variant should bring that down to 10-25%.
    # ~435M params, ~1.5GB on disk, ~150-300ms per pair on CPU.
    nli_model: str = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"

    # Verifier backend (architecture-research task #2).
    # Options:
    #   - "nli":      legacy behaviour. Only the DeBERTa entailment scorer
    #                 runs. ~1.5 GB RAM, 150-300ms per pair on CPU.
    #   - "bge":      replace NLI with the existing bge-reranker-v2-m3 cross
    #                 encoder used for retrieval. Higher-rank score == more
    #                 supportive. The reranker is already in memory for
    #                 retrieval so this swap frees ~1.5 GB if NLI retires.
    #                 Calibrated against battery v3 traces — see
    #                 docs/VERIFIER_SWAP.md. NOT a categorical entailment
    #                 model so behaviour on negation / contradiction is
    #                 weaker than NLI; the floor exists to catch the
    #                 fabrication case (low rerank == passage doesn't
    #                 actually cover the sentence) which is what matters
    #                 for the citation guarantee.
    #   - "ensemble": run BOTH and take the WORSE verdict. Pessimistic AND
    #                 across the two safety nets — a sentence passes only
    #                 when both backends agree it's OK / WEAK. This is the
    #                 safe default while we collect evidence that bge alone
    #                 is sufficient.
    # Default = bge after head-to-head battery v3 on the same 50 queries:
    #   NLI-only:  84% pass, 8 stops, 33.4s median latency
    #   bge:       92% pass, 0 stops, 16.7s median  ← winner
    #   ensemble:  82% pass, 6 stops, 16.4s median  (pessimistic AND
    #              over-suppresses; bge and NLI disagree on WHICH
    #              sentences are weak, so the AND surfaces the UNION
    #              of weak verdicts — worse than either alone)
    # See docs/VERIFIER_SWAP.md for the full comparison + caveats.
    # NLI stays available as a fallback if bge needs stress-testing on
    # contradictions / negations; switch via VERIFIER_BACKEND=nli env.
    verifier_backend: Literal["nli", "bge", "ensemble"] = "bge"
    # bge score above which a cited sentence is treated as OK (analogous
    # to nli_weak_support_below). sentence-transformers' CrossEncoder
    # applies a sigmoid by default so bge-reranker-v2-m3 scores fall in
    # [0, 1] in practice (legacy literature reports raw logits in
    # [-10, +10] — we measure the post-sigmoid value because that's what
    # the runtime returns).
    # Calibrated from data/processed/bge_verifier_calibration.json on
    # battery_v3_20260519-010820 (250 cited sentences, NLI status as
    # reference): 0.222 yields precision=0.905 / recall=0.846 against
    # NLI=OK. Recalibrate when the corpus, model, or NLI version changes.
    bge_verifier_threshold: float = 0.222
    # Hard floor: bge below this means the cited passage so weakly supports
    # the sentence that it's treated as UNSUPPORTED and suppressed.
    # Mirrors nli_hard_floor (0.10) but on the bge score scale. The 5th
    # percentile of bge scores on NLI=WEAK pairs is 0.003 — anything below
    # that is well outside the legitimate paraphrase band. Calibrated
    # alongside the threshold; populated from
    # bge_verifier_calibration.json.
    bge_verifier_hard_floor: float = 0.003

    answer_fast_enabled: bool = False     # disabled in production
    # Auto-cite: lexical 4-gram recall fallback when the LLM forgets the
    # inline [N]. The chosen passage still has to clear NLI in step 3, so
    # this can never let a hallucinated claim through — it just keeps the
    # strict-stop from killing answers that small Q4 models would otherwise
    # ship un-cited. Threshold 0.5 = the sentence's 4-grams must be at least
    # 50% covered by the passage.
    auto_cite_enabled: bool = True
    # Round-7: 0.4 → 0.3 minimum lexical recall before auto-cite attaches.
    # The NLI floor (0.10) and the auto-cite NLI requirement (round-3 #3)
    # still suppress anything that doesn't actually entail — so lowering
    # the lexical threshold just lets more candidate sentences reach
    # NLI rather than dropping at the lexical gate.
    auto_cite_min_recall: float = 0.3
    # Coverage gate: refuse the query honestly when the reranker can't find
    # a passage above this score. In-slice queries reliably score 0.6-0.9
    # for the top hit; out-of-slice (e.g., tenancy / tax / IP / nonsense)
    # score < 0.15. Round-7: 0.3 → 0.4 — borderline queries (rerank 0.3-0.4)
    # were producing ≤2 OK sentences then hitting stop; refusing them
    # honestly counts as pass-refused.
    refuse_below_rerank: float = 0.4
    # Per round-3 review (security #5): when rerank is disabled in config
    # (ablation / model-unavailable), the rerank-based gate can't fire and
    # out-of-slice queries used to leak through. Fall back to a calibrated
    # combined-score threshold (BM25 + dense fusion). Threshold tuned
    # conservatively: in-slice top combined_score is typically > 0.5; the
    # original online-refund tangent ran at ~0.15-0.25 combined.
    refuse_below_combined: float = 0.35

    # Answer-relevance check (Task #10).
    #
    # After the answer stream closes, embed (query, assembled_answer_body)
    # with bge-m3 and compute cosine. The verdict (ok / partial /
    # off_topic) is emitted as an SSE event so the UI can warn when the
    # answer cites real law correctly but doesn't address the user's
    # actual question. ADDITIVE — never refuses; only signals.
    #
    # Calibrated against data/processed/answer_relevance_calibration.json
    # on battery_v3_20260519-010820 + 4 synthetic off-topic anchors
    # (the deposit-return failure case, anticipatory-vs-regular bail,
    # and two consumer-protection misalignments). Balanced accuracy
    # 1.0 on the labelled set of 18 (14 on-topic / 4 off-topic).
    # On-topic cosines: 0.713 - 0.817. Off-topic cosines: 0.507 - 0.670.
    # Threshold sits in the gap.
    # Recalibrate when the embedder, prompt, or answer style changes
    # materially — the gap is small (~0.04) so a shift of either
    # distribution will close it.
    # Recalibrated 2026-05-19 from 0.6916 → 0.62 after eval v3/v4 showed
    # the original threshold was tuned pre-query-expansion. Agent #3's
    # analysis of the e2e_eval_20260519_134948.jsonl run found 8/10 of
    # the worst OFF_TOPIC verdicts were actually on-topic — flagged
    # because lay-phrase queries vs legal-vocab answers have inherently
    # lower cosine. At T=0.62 the eval reclassifies to 77 OK / 18 partial
    # / 2 off_topic. Caveat: no labeled positives in 0.60-0.71 range yet;
    # this is eyeball-validated against ~10 worst cases. Re-calibrate on a
    # held-out set once we have one.
    # 2026-05-21 second recalibration: 0.62 still flagged 5 queries as
    # OFF_TOPIC where bare-acts had surfaced (3-6 in top-5) — the lay-
    # phrase vs legal-vocab cosine gap was the cause. Dropping to 0.55
    # is supported by spot-check of those 5: all answer the right
    # operative law just in legal vocabulary the dense cosine doesn't
    # match. Caveat: still no labeled positives in 0.55-0.62, this is
    # eyeball-validated, gold-set will properly recalibrate.
    answer_relevance_threshold: float = 0.55
    # +/- band/2 around the threshold defines the PARTIAL band. Outside
    # the band → verdict is OK or OFF_TOPIC.
    #
    # The task brief suggested band ≈ 0.1 but the data argues for tighter:
    # on the 18-item calibration set the gap between off-topic-max (0.670)
    # and on-topic-min (0.713) is only ~0.04. A 0.1 band would mark
    # ~36% of on-topic answers as "partial" (their cosines cluster
    # at 0.71-0.74). With band=0.05 the partial range is roughly
    # [0.667, 0.716] — captures the noisy borderline without over-
    # flagging legitimate answers.
    # If a future calibration with more on-topic samples shows the
    # distribution shifting, recalibrate. See docs/ANSWER_RELEVANCE.md.
    answer_relevance_band: float = 0.05
    # When True, the server emits a relevance SSE event on every answer
    # that produced any user-visible cited prose. When False, NO
    # relevance event is emitted (useful for ablation / A/B testing).
    answer_relevance_enabled: bool = True

    # Task #13: lay-phrase → legal-vocabulary query expansion.
    # Calls the local LLM once before retrieval to translate the lay
    # query into 2-3 legal-keyword-rich variants, retrieves candidates
    # from each, and reranks the union against the ORIGINAL query.
    # Adds ~1.4s latency to /answer (qwen3:14b expansion) but lifted
    # bare-act top-5 surface rate from 13% → 53% on the worst-failing
    # queries in the 102-query e2e eval (scripts/eval_query_expand.py).
    # Kill switch — flip to False to bypass and use plain hybrid_retrieve.
    query_expansion_enabled: bool = True

    # Provenance gate (PLAN §10.1 + provenance system).
    # In production, retrieval must only return chunks from documents whose
    # source has been verified against the canonical Govt of India source.
    # Set to False during development / evaluation to access the full corpus.
    require_provenance_verified: bool = False

    # Other
    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
