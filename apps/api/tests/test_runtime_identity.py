from apps.api.runtime_identity import runtime_identity


def test_runtime_identity_honours_explicit_build_fingerprint(monkeypatch):
    monkeypatch.setenv("LAW_RAG_BUILD_FINGERPRINT", "a" * 64)
    monkeypatch.setattr(
        "apps.api.runtime_identity._git_worktree_fingerprint",
        lambda: "a" * 64,
    )
    runtime_identity.cache_clear()

    assert runtime_identity() == {
        "fingerprint": "a" * 64,
        "source": "environment_verified",
    }

    runtime_identity.cache_clear()


def test_runtime_identity_rejects_unattested_environment_label(monkeypatch):
    monkeypatch.setenv("LAW_RAG_BUILD_FINGERPRINT", "release-test-123")
    runtime_identity.cache_clear()

    assert runtime_identity() == {"fingerprint": "unknown", "source": "unavailable"}

    runtime_identity.cache_clear()


def test_runtime_identity_rejects_environment_digest_mismatch(monkeypatch):
    monkeypatch.setenv("LAW_RAG_BUILD_FINGERPRINT", "a" * 64)
    monkeypatch.setattr(
        "apps.api.runtime_identity._git_worktree_fingerprint",
        lambda: "b" * 64,
    )
    runtime_identity.cache_clear()

    assert runtime_identity() == {"fingerprint": "unknown", "source": "unavailable"}

    runtime_identity.cache_clear()


def test_runtime_identity_is_opaque_and_nonempty(monkeypatch):
    monkeypatch.delenv("LAW_RAG_BUILD_FINGERPRINT", raising=False)
    runtime_identity.cache_clear()

    identity = runtime_identity()

    assert identity["fingerprint"]
    assert identity["source"] in {"git_worktree", "unavailable"}
    assert "/" not in identity["fingerprint"]

    runtime_identity.cache_clear()
