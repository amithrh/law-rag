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

    # Postgres
    postgres_host: str = "localhost"
    postgres_host_port: int = 5433
    postgres_db: str = "lawrag"
    postgres_user: str = "lawrag"
    postgres_password: str = ""

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
    skip_ratio_stop: float = 0.0          # public-product default per §4.3
    nli_weak_support_below: float = 0.5
    nli_model: str = "MoritzLaurer/DeBERTa-v3-base-mnli"
    answer_fast_enabled: bool = False     # disabled in production

    # Other
    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
