import json
from datetime import UTC, date, datetime

from apps.api.config import Settings
from scripts.corpus_manifest import MANIFEST_VERSION, build_manifest, init_sql_sha256, json_default


def test_offline_corpus_manifest_records_runtime_and_schema_without_db_access():
    manifest = build_manifest(settings=Settings(database_url="postgresql://example"), database=None)

    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["database"] is None
    assert manifest["schema"]["management"] == "bootstrap_sql_no_migration_table"
    assert manifest["schema"]["init_sql_sha256"] == init_sql_sha256()
    assert manifest["runtime"]["embedding_model"] == "BAAI/bge-m3"
    assert manifest["runtime"]["llm_model"] == "qwen3:14b"


def test_corpus_manifest_serializes_postgres_date_and_timestamp_values():
    payload = {
        "as_at": date(2026, 7, 15),
        "fetched_at": datetime(2026, 7, 15, 3, 30, tzinfo=UTC),
    }

    rendered = json.loads(json.dumps(payload, default=json_default))

    assert rendered == {
        "as_at": "2026-07-15",
        "fetched_at": "2026-07-15T03:30:00+00:00",
    }
