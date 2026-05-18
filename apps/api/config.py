"""App configuration loaded from .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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

    # LLM (Ollama)
    ollama_host_port: int = 11434
    llm_model: str = "llama3.1:8b-instruct-q4_K_M"
    llm_max_tokens: int = 1024

    # Retrieval
    bm25_top_k: int = 100
    dense_top_k: int = 100
    rerank_input_k: int = 50          # how many candidates the cross-encoder scores
    rerank_top_k: int = 20            # how many we return after rerank
    prompt_top_k: int = 8
    hnsw_ef_search: int = 40
    rerank_enabled: bool = True       # disable for ablation / when model unavailable
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # Verifier (PLAN §4.3)
    # Per Codex adversarial review #1: unsupported sentences are SUPPRESSED
    # from the user stream (main.py:_emit_and_check) rather than shipped
    # with a red strikethrough. So `skip_ratio_stop` here is no longer the
    # "what users see" knob — it's the "how bad does the answer have to be
    # before we show the stop banner instead of a partial answer" knob.
    # 0.4 = stop if 40%+ of emitted sentences are bad. Lower would over-
    # stop on the common single-trailing-fluff pattern; higher would let
    # very weak answers ship as 2-3 visible sentences.
    skip_ratio_stop: float = 0.4
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
    nli_model: str = "MoritzLaurer/DeBERTa-v3-base-mnli"
    answer_fast_enabled: bool = False     # disabled in production
    # Auto-cite: lexical 4-gram recall fallback when the LLM forgets the
    # inline [N]. The chosen passage still has to clear NLI in step 3, so
    # this can never let a hallucinated claim through — it just keeps the
    # strict-stop from killing answers that small Q4 models would otherwise
    # ship un-cited. Threshold 0.5 = the sentence's 4-grams must be at least
    # 50% covered by the passage.
    auto_cite_enabled: bool = True
    auto_cite_min_recall: float = 0.4
    # Coverage gate: refuse the query honestly when the reranker can't find
    # a passage above this score. In-slice queries reliably score 0.6-0.9
    # for the top hit; out-of-slice (e.g., tenancy / tax / IP / nonsense)
    # score < 0.15. Threshold 0.3 is well between the two.
    refuse_below_rerank: float = 0.3

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
