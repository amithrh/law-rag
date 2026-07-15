"""Fold immutable authority migrations into the runtime registry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from .model import AuthorityMigration, AuthorityRecord, legal_name

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class LoadedAuthorityMigration:
    path: str
    manifest: AuthorityMigration
    manifest_sha256: str


@dataclass(frozen=True)
class AuthorityRegistry:
    schema_version: int
    records: tuple[AuthorityRecord, ...]
    migrations: tuple[LoadedAuthorityMigration, ...]

    def by_key(self, canonical_key: str) -> AuthorityRecord | None:
        return next(
            (record for record in self.records if record.canonical_key == canonical_key), None
        )

    def resolve(
        self,
        *,
        canonical_name: str,
        provision_kind: str,
        provision_number: str,
    ) -> AuthorityRecord | None:
        wanted_name = legal_name(canonical_name)
        wanted_kind = legal_name(provision_kind)
        wanted_number = legal_name(provision_number)
        for record in self.records:
            names = {legal_name(record.canonical_name), *(legal_name(a) for a in record.aliases)}
            if wanted_name not in names:
                continue
            if legal_name(record.provision.kind) != wanted_kind:
                continue
            if legal_name(record.provision.number) == wanted_number:
                return record
        return None


def load_authority_migrations(
    migrations_dir: Path | None = None,
) -> tuple[LoadedAuthorityMigration, ...]:
    loaded: list[LoadedAuthorityMigration] = []
    seen_ids: set[str] = set()
    if migrations_dir is None:
        migration_root = resources.files("authority_registry").joinpath("migrations")
        files: list[Any] = sorted(
            (item for item in migration_root.iterdir() if item.name.endswith(".json")),
            key=lambda item: item.name,
        )
    else:
        files = sorted(migrations_dir.glob("*.json"))
    for path in files:
        raw = path.read_bytes()
        manifest = AuthorityMigration.model_validate(json.loads(raw))
        if manifest.migration_id in seen_ids:
            raise ValueError(f"duplicate authority migration id: {manifest.migration_id}")
        seen_ids.add(manifest.migration_id)
        loaded.append(
            LoadedAuthorityMigration(
                path=str(path),
                manifest=manifest,
                manifest_sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    return tuple(loaded)


def build_authority_registry(
    migrations: tuple[LoadedAuthorityMigration, ...],
) -> AuthorityRegistry:
    records: dict[str, AuthorityRecord] = {}
    authority_ids: dict[str, str] = {}
    document_anchors: dict[tuple[str, str], str] = {}
    previous_migration_id = ""
    for loaded in migrations:
        migration = loaded.manifest
        if migration.migration_id <= previous_migration_id:
            raise ValueError("authority migration ids must be strictly increasing")
        previous_migration_id = migration.migration_id
        for operation in migration.operations:
            record = operation.record
            previous = records.get(record.canonical_key)
            previous_hash = previous.record_sha256 if previous else None
            if operation.expected_previous_record_sha256 != previous_hash:
                raise ValueError(
                    f"unexpected previous hash for {record.canonical_key}: "
                    f"expected {operation.expected_previous_record_sha256}, found {previous_hash}"
                )
            owner = authority_ids.get(record.authority_id_expected)
            if owner is not None and owner != record.canonical_key:
                raise ValueError(
                    f"authority id collision: {record.authority_id_expected} belongs to {owner}"
                )
            anchor_key = (record.doc_id, record.provision.canonical_anchor.lower())
            anchor_owner = document_anchors.get(anchor_key)
            if anchor_owner is not None and anchor_owner != record.canonical_key:
                raise ValueError(f"document anchor collision: {anchor_key}")
            records[record.canonical_key] = record
            authority_ids[record.authority_id_expected] = record.canonical_key
            document_anchors[anchor_key] = record.canonical_key
    return AuthorityRegistry(
        schema_version=1,
        records=tuple(records[key] for key in sorted(records)),
        migrations=migrations,
    )


def reconcile_applied_migrations(
    migrations: tuple[LoadedAuthorityMigration, ...],
    applied: list[tuple[str, str]],
    *,
    through_migration_id: str | None = None,
) -> tuple[LoadedAuthorityMigration, ...]:
    # Run every record/predecessor/collision invariant before deciding what to
    # apply. Selecting one migration must never bypass validation of the chain.
    build_authority_registry(migrations)
    expected_prefix = [
        (loaded.manifest.migration_id, loaded.manifest_sha256)
        for loaded in migrations[: len(applied)]
    ]
    if applied != expected_prefix:
        raise ValueError(
            "applied authority migrations are not an exact hash-matched prefix "
            "of the canonical manifest chain"
        )
    end = len(migrations)
    if through_migration_id is not None:
        try:
            end = next(
                index + 1
                for index, loaded in enumerate(migrations)
                if loaded.manifest.migration_id == through_migration_id
            )
        except StopIteration as exc:
            raise ValueError(f"unknown migration: {through_migration_id}") from exc
    return migrations[len(applied) : end]


@lru_cache(maxsize=1)
def load_authority_registry() -> AuthorityRegistry:
    return build_authority_registry(load_authority_migrations())


def get_authority_record(canonical_key: str) -> AuthorityRecord:
    record = load_authority_registry().by_key(canonical_key)
    if record is None:
        raise KeyError(f"unknown authority record: {canonical_key}")
    return record
