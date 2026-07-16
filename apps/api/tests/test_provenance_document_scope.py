from scripts.verify_provenance import (
    OFFICIAL_PDF_ORIGINS,
    audit_persistence_rows,
    verification_scope_updates,
)


def _audit(*, matched, targets, scope="document", hash_match=True):
    return {
        "source_id": 1,
        "source_url": "https://example.gov.in/law.pdf",
        "sha_match": hash_match,
        "text_match": matched,
        "verification_pass": bool(matched and hash_match) if matched is not None else None,
        "scope": scope,
        "text_similarity": 1.0 if matched else 0.2,
        "refetch_status": "ok",
        "refetch_size": 100,
        "refetch_pages": 1,
        "refetch_hash": "a" * 64,
        "notes": "test",
        "audit_targets": targets,
    }


def test_audit_rows_are_expanded_to_exact_documents_and_chunks():
    rows = audit_persistence_rows(
        [
            _audit(matched=True, targets=[(10, 100), (11, 110)]),
        ]
    )
    assert [(row[2], row[3]) for row in rows] == [(10, 100), (11, 110)]


def test_verification_updates_only_compared_documents_and_clears_drift():
    passed_docs, failed_docs, passed_chunks, failed_chunks = verification_scope_updates(
        [
            _audit(matched=True, targets=[(10, 100)]),
            _audit(matched=False, targets=[(11, 110)]),
            _audit(matched=None, targets=[(12, 120)]),
            _audit(matched=True, targets=[(13, 130)], scope="chunk"),
            _audit(matched=False, targets=[(14, 140)], scope="chunk"),
        ]
    )
    assert passed_docs == [10]
    assert failed_docs == [11]
    assert passed_chunks == [130]
    assert failed_chunks == [140]


def test_hash_mismatch_cannot_promote_registry_chunk():
    passed_docs, failed_docs, passed_chunks, failed_chunks = verification_scope_updates(
        [
            _audit(
                matched=True,
                hash_match=False,
                targets=[(13, 130)],
                scope="chunk",
            ),
        ]
    )
    assert passed_docs == []
    assert failed_docs == []
    assert passed_chunks == []
    assert failed_chunks == [130]


def test_registry_chunks_keep_independent_verification_verdicts():
    row = _audit(
        matched=False,
        targets=[(13, 130), (13, 131)],
        scope="chunk",
    )
    row["target_verdicts"] = [
        {
            "document_id": 13,
            "chunk_id": 130,
            "text_similarity": 0.99,
            "text_match": True,
            "verification_pass": True,
        },
        {
            "document_id": 13,
            "chunk_id": 131,
            "text_similarity": 0.10,
            "text_match": False,
            "verification_pass": False,
        },
    ]

    persistence = audit_persistence_rows([row])
    assert [(item[3], item[5], item[6]) for item in persistence] == [
        (130, True, 0.99),
        (131, False, 0.10),
    ]
    _, _, passed_chunks, failed_chunks = verification_scope_updates([row])
    assert passed_chunks == [130]
    assert failed_chunks == [131]


def test_official_pdf_verifier_accepts_custody_registry_publishers():
    assert {"mha_gazette", "legislative_department"} <= OFFICIAL_PDF_ORIGINS
