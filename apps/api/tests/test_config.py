"""Tests for the Settings layer.

Critical invariant: `resolved_database_url` always returns a usable DSN
no matter where the API runs (host-side dev, dockerized prod, managed
postgres). DATABASE_URL takes precedence; otherwise components are
assembled. This is what makes the api dockerizable.
"""
from __future__ import annotations

import os

import pytest  # noqa: F401  — used by tests below

from apps.api.config import Settings


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    # Strip any DATABASE_URL / POSTGRES_* from the environment so each test
    # constructs Settings deterministically.
    for k in list(os.environ):
        if (
            k.startswith("POSTGRES_")
            or k.startswith("OLLAMA_")
            or k in {"DATABASE_URL", "API_IN_DOCKER"}
        ):
            monkeypatch.delenv(k, raising=False)
    yield


class TestDatabaseUrlResolution:
    def test_explicit_database_url_wins(self):
        s = Settings(
            database_url="postgresql://app:pw@db.example.com:5432/legaldb",
            postgres_user="ignored",
            postgres_password="ignored",
            postgres_host="ignored",
            postgres_host_port=9999,
            postgres_db="ignored",
        )
        assert s.resolved_database_url == "postgresql://app:pw@db.example.com:5432/legaldb"

    def test_assembled_from_components_when_no_explicit_url(self):
        s = Settings(
            database_url="",
            postgres_user="lawrag",
            postgres_password="secret",
            postgres_host="localhost",
            postgres_host_port=5433,
            postgres_db="lawrag",
        )
        assert s.resolved_database_url == (
            "postgresql://lawrag:secret@localhost:5433/lawrag"
        )

    def test_assembled_url_uses_localhost_when_host_is_localhost(self):
        """For Mac dev where the API runs on the host and Postgres is
        exposed at localhost via docker port mapping."""
        s = Settings(
            database_url="",
            postgres_host="localhost",
            postgres_host_port=5433,
        )
        assert "localhost:5433" in s.resolved_database_url

    def test_assembled_url_uses_postgres_service_name_for_docker(self):
        """When the API runs in the same docker network as postgres, the
        service name `postgres` is the right host (port 5432 internal)."""
        s = Settings(
            database_url="postgresql://lawrag:secret@postgres:5432/lawrag",
        )
        assert "postgres:5432" in s.resolved_database_url

    def test_assembled_url_uses_internal_port_for_docker_service_name(self):
        """When .env has POSTGRES_HOST=postgres (docker service name), the
        assembly should pick the internal port (5432), not the host-mapped one."""
        s = Settings(
            database_url="",
            postgres_host="postgres",
            postgres_host_port=5433,
            postgres_internal_port=5432,
        )
        assert "postgres:5432" in s.resolved_database_url

    def test_host_side_url_always_localhost_host_port(self):
        """resolved_database_url_host_side ignores POSTGRES_HOST and uses
        localhost:host_port — for processes running outside docker.
        """
        s = Settings(
            database_url="",
            postgres_host="postgres",
            postgres_host_port=5433,
            postgres_user="lawrag",
            postgres_password="secret",
            postgres_db="lawrag",
        )
        assert s.resolved_database_url_host_side == (
            "postgresql://lawrag:secret@localhost:5433/lawrag"
        )


class TestSettingsDefaults:
    def test_rerank_enabled_by_default(self):
        assert Settings(database_url="postgresql://x").rerank_enabled is True

    def test_ollama_api_host_uses_ipv4_loopback_by_default(self):
        # Avoid Mac/OrbStack localhost ambiguity where ::1 can hit the
        # Docker-published CPU-only Ollama listener before host Ollama.
        assert Settings(database_url="postgresql://x").ollama_api_host == "127.0.0.1"
        assert (
            Settings(database_url="postgresql://x").resolved_ollama_api_host
            == "127.0.0.1"
        )

    def test_legacy_ollama_host_is_ignored_for_host_side_runs(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "ollama")
        s = Settings(database_url="postgresql://x")
        assert s.ollama_host == "ollama"
        assert s.resolved_ollama_api_host == "127.0.0.1"

    def test_legacy_ollama_host_is_honored_in_docker(self, monkeypatch):
        monkeypatch.setenv("API_IN_DOCKER", "1")
        monkeypatch.setenv("OLLAMA_HOST", "ollama")
        monkeypatch.setenv("OLLAMA_PORT", "11435")
        s = Settings(database_url="postgresql://x")
        assert s.resolved_ollama_api_host == "ollama"
        assert s.resolved_ollama_api_port == 11435

    def test_strict_stop_thresholds_with_suppression(self):
        # Per Codex review #1, uncited sentences are suppressed (dropped
        # from the user stream) instead of being shipped with a badge.
        # skip_ratio_stop=0.4 controls when the *stop banner* appears; the
        # citation guarantee comes from suppression itself, not the banner.
        s = Settings(database_url="postgresql://x")
        assert s.skip_ratio_stop == 0.6
        assert s.min_unsupported_before_stop == 2

    def test_embedding_max_seq_len_512(self):
        # bge-m3 supports 8k but we cap at 512 per Q3 bench (MPS memory)
        assert Settings(database_url="postgresql://x").embedding_max_seq_len == 512

    def test_rerank_top_k_smaller_than_input_k(self):
        s = Settings(database_url="postgresql://x")
        assert s.rerank_input_k > s.rerank_top_k, (
            "input must be larger than output for rerank to be meaningful"
        )

    def test_require_provenance_verified_off_by_default(self):
        """In development (where the corpus is being loaded), we don't want
        to block queries against unverified content. Production overrides
        via env var REQUIRE_PROVENANCE_VERIFIED=true."""
        assert Settings(database_url="postgresql://x").require_provenance_verified is False

    def test_verifier_backend_defaults_to_bge(self):
        """Default is `bge` after head-to-head battery v3 comparison: bge
        scored 92% (vs NLI 84% / ensemble 82%) with zero stops and half
        the latency. NLI stays available as VERIFIER_BACKEND=nli for
        ablation or if bge needs stress-testing on contradictions."""
        s = Settings(database_url="postgresql://x")
        assert s.verifier_backend == "bge"
        # Calibrated values (from data/processed/bge_verifier_calibration.json
        # on battery_v3_20260519-010820). If these defaults move, the
        # calibration script's `Recommended settings` output is the source
        # of truth — recalibrate before changing.
        assert s.bge_verifier_threshold == pytest.approx(0.222)
        assert s.bge_verifier_hard_floor == pytest.approx(0.003)

    def test_verifier_backend_env_var_override(self, monkeypatch):
        """VERIFIER_BACKEND=bge must reach the Settings object so an
        operator can flip the backend without code edits."""
        monkeypatch.setenv("VERIFIER_BACKEND", "bge")
        s = Settings(database_url="postgresql://x")
        assert s.verifier_backend == "bge"
