"""Versioned authority registry shared by planning, retrieval, and ingestion."""

from .loader import (
    AuthorityRegistry,
    LoadedAuthorityMigration,
    get_authority_record,
    load_authority_migrations,
    load_authority_registry,
    reconcile_applied_migrations,
)
from .model import AuthorityMigration, AuthorityRecord, canonical_authority_id

__all__ = [
    "AuthorityMigration",
    "AuthorityRecord",
    "AuthorityRegistry",
    "LoadedAuthorityMigration",
    "canonical_authority_id",
    "get_authority_record",
    "load_authority_migrations",
    "load_authority_registry",
    "reconcile_applied_migrations",
]
