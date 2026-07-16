"""Strict immutable contracts for canonical legal-authority declarations."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def legal_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def canonical_authority_id(canonical_name: str, provision_kind: str, number: str) -> str:
    scope = legal_name(f"{provision_kind} {number}")
    identity = f"{legal_name(canonical_name)}|{scope}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"authority_{digest}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JurisdictionRecord(StrictModel):
    country: Literal["IN"]
    level: Literal["national", "state"]
    state_code: str | None = None

    @model_validator(mode="after")
    def validate_level(self) -> JurisdictionRecord:
        if self.level == "national" and self.state_code is not None:
            raise ValueError("national authority cannot declare a state_code")
        if self.level == "state" and not self.state_code:
            raise ValueError("state authority requires state_code")
        return self


class ProvisionRecord(StrictModel):
    kind: Literal["section", "article", "rule", "clause", "order", "paragraph"]
    number: str = Field(min_length=1)
    heading: str = Field(min_length=1)
    canonical_anchor: str = Field(pattern=r"^/")
    anchor_aliases: tuple[str, ...] = ()

    @property
    def all_anchors(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.canonical_anchor, *self.anchor_aliases)))


class PublisherRecord(StrictModel):
    name: str = Field(min_length=1)
    kind: Literal["official_government", "official_court", "official_regulator"]


class ProvenanceDeclaration(StrictModel):
    tier: Literal["canonical", "mirror", "unverified"]
    verification_method: Literal["refetch_hash_and_text", "manual_official_comparison"]
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_bytes_size: int = Field(gt=0)


class SavingsRecord(StrictModel):
    authority: str = Field(min_length=1)
    provision: str = Field(min_length=1)
    canonical_url: str = Field(pattern=r"^https://")
    effect: str = Field(min_length=1)


class RetrievalDeclaration(StrictModel):
    source_pack_id: str = Field(min_length=1)
    title_patterns: tuple[str, ...] = Field(min_length=1)
    doc_ids: tuple[str, ...] = Field(min_length=1)
    source_types: tuple[str, ...] = Field(min_length=1)
    search_query: str = Field(min_length=1)


class AuthorityRecord(StrictModel):
    schema_version: Literal[1]
    canonical_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    authority_id_expected: str = Field(pattern=r"^authority_[0-9a-f]{20}$")
    canonical_name: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    authority_type: Literal["statute", "rule", "scheme", "judgment", "circular"]
    jurisdiction: JurisdictionRecord
    provision: ProvisionRecord
    effective_from: date
    effective_to: date | None = None
    savings: SavingsRecord | None = None
    consolidation_as_at: date | None = None
    publisher: PublisherRecord
    canonical_url: str = Field(pattern=r"^https://")
    source_origin: Literal["indiacode", "rbi"]
    provenance: ProvenanceDeclaration
    doc_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    statute: str = Field(min_length=1)
    year: int = Field(ge=1800, le=2200)
    subject_area: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    retrieval: RetrievalDeclaration
    verbatim_status: Literal["declared"]
    text: str = Field(min_length=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity_and_text(self) -> AuthorityRecord:
        expected_id = canonical_authority_id(
            self.canonical_name,
            self.provision.kind,
            self.provision.number,
        )
        if self.authority_id_expected != expected_id:
            raise ValueError(
                f"authority_id_expected must be {expected_id} for the canonical identity"
            )
        actual_hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if self.text_sha256 != actual_hash:
            raise ValueError("text_sha256 does not match text")
        if self.provenance.tier == "canonical" and self.publisher.kind not in {
            "official_government",
            "official_court",
            "official_regulator",
        }:
            raise ValueError("canonical provenance requires an official publisher")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot precede effective_from")
        if self.consolidation_as_at is not None and self.consolidation_as_at < self.effective_from:
            raise ValueError("consolidation_as_at cannot precede effective_from")
        if self.effective_to is not None and self.savings is None:
            raise ValueError("ended authority requires an explicit savings record")
        if legal_name(self.canonical_name) not in {
            legal_name(title) for title in self.retrieval.title_patterns
        }:
            raise ValueError("retrieval title_patterns must contain canonical_name")
        if self.doc_id not in self.retrieval.doc_ids:
            raise ValueError("retrieval doc_ids must contain doc_id")
        if self.source_type not in self.retrieval.source_types:
            raise ValueError("retrieval source_types must contain source_type")
        return self

    @property
    def record_sha256(self) -> str:
        # Keep pre-versioning record hashes stable when the optional version
        # field is absent; already-applied immutable migrations depend on it.
        exclude = {"consolidation_as_at"} if self.consolidation_as_at is None else None
        payload = self.model_dump_json(exclude=exclude, exclude_none=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuthorityMigrationOperation(StrictModel):
    op: Literal["upsert"]
    record: AuthorityRecord
    expected_previous_record_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class WorkflowAuthorityRequirement(StrictModel):
    registry_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    role: Literal["scope", "forum", "legal_basis", "maintainability", "remedy"]
    required: bool = True
    condition_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_conditions(self) -> WorkflowAuthorityRequirement:
        if not self.required and not self.condition_ids:
            raise ValueError("conditional authority requires at least one condition_id")
        if len(self.condition_ids) != len(set(self.condition_ids)):
            raise ValueError("authority condition IDs must be unique")
        return self


class AuthorityWorkflowRecord(StrictModel):
    schema_version: Literal[1]
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    owner_token: str = Field(min_length=1)
    condition_ids: tuple[str, ...] = Field(min_length=1)
    authorities: tuple[WorkflowAuthorityRequirement, ...] = Field(min_length=1)
    forums: tuple[str, ...] = Field(min_length=1)
    remedies: tuple[str, ...] = Field(min_length=1)
    deadline_rules: tuple[str, ...] = ()
    documents: tuple[str, ...] = Field(min_length=1)
    escalation: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_workflow(self) -> AuthorityWorkflowRecord:
        keys = [item.registry_key for item in self.authorities]
        if len(keys) != len(set(keys)):
            raise ValueError("workflow authority keys must be unique")
        if len(self.condition_ids) != len(set(self.condition_ids)):
            raise ValueError("workflow condition IDs must be unique")
        return self

    @property
    def record_sha256(self) -> str:
        payload = self.model_dump_json(exclude_none=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WorkflowMigrationOperation(StrictModel):
    op: Literal["upsert"]
    record: AuthorityWorkflowRecord
    expected_previous_record_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class AuthorityMigration(StrictModel):
    migration_id: str = Field(pattern=r"^[0-9]{4}_[a-z0-9][a-z0-9_]*$")
    schema_version: Literal[1]
    operations: tuple[AuthorityMigrationOperation, ...] = Field(min_length=1)
    workflow_operations: tuple[WorkflowMigrationOperation, ...] = ()
