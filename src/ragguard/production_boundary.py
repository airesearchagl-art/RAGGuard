from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from ragguard.compatibility import SemanticVersion
from ragguard.production_equivalence import ProductionEquivalentState
from ragguard.production_registry import RegistryStatus


CANONICAL_PRODUCTION_BOUNDARY_DIGEST_ALGORITHM = "sha256"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SAFE_CONTEXT = frozenset(
    {
        "no_credentials",
        "no_network",
        "no_persistence",
        "no_production_registry_write",
        "no_real_documents",
        "no_runtime_activation",
        "no_transport",
        "product_neutral",
        "synthetic_only",
        "test_registry_only",
    }
)


class ManualValidationState(str, Enum):
    NOT_PERFORMED = "not_performed"
    PERFORMED_PENDING_REVIEW = "performed_pending_review"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class CompatibilityEvidenceKind(str, Enum):
    SYNTHETIC_ONLY = "synthetic_only"
    CONTROLLED_MANUAL = "controlled_manual"
    PRODUCTION_EQUIVALENT = "production_equivalent"


class PersistenceState(str, Enum):
    NONE = "none"
    TEST_ONLY = "test_only"
    PRODUCTION_READY = "production_ready"


class RuntimeAuthorizationState(str, Enum):
    DISABLED = "disabled"
    CANDIDATE_ONLY = "candidate_only"
    ACTIVE = "active"


class SecurityReviewState(str, Enum):
    NOT_REVIEWED = "not_reviewed"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class RollbackSemantics(str, Enum):
    EXPLICIT_NO_REACTIVATION = "explicit_no_reactivation"
    UNSPECIFIED = "unspecified"


class ProductionBoundaryErrorCategory(str, Enum):
    INVALID_IDENTIFIER = "production_boundary_identifier_invalid"
    INVALID_DIGEST = "production_boundary_digest_invalid"
    INVALID_TEMPORAL_INPUT = "production_boundary_temporal_input_invalid"
    INVALID_SAFE_CONTEXT = "production_boundary_safe_context_invalid"
    INVALID_PERSISTENCE_METADATA = "persistence_boundary_metadata_invalid"
    INVALID_CONTRACT = "production_boundary_contract_invalid"


class ProductionBoundaryError(ValueError):
    def __init__(self, category: ProductionBoundaryErrorCategory) -> None:
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True)
class PersistenceBoundaryMetadata:
    durability_required: bool
    append_only_audit_required: bool
    tamper_evidence_required: bool
    backup_restore_required: bool
    secret_separation_required: bool
    rollback_semantics: RollbackSemantics
    boundary_approved: bool

    def __post_init__(self) -> None:
        if (
            not all(
                type(value) is bool
                for value in (
                    self.durability_required,
                    self.append_only_audit_required,
                    self.tamper_evidence_required,
                    self.backup_restore_required,
                    self.secret_separation_required,
                    self.boundary_approved,
                )
            )
            or not isinstance(self.rollback_semantics, RollbackSemantics)
        ):
            _raise(ProductionBoundaryErrorCategory.INVALID_PERSISTENCE_METADATA)

    @property
    def is_approved(self) -> bool:
        return (
            self.boundary_approved
            and self.durability_required
            and self.append_only_audit_required
            and self.tamper_evidence_required
            and self.backup_restore_required
            and self.secret_separation_required
            and self.rollback_semantics
            is RollbackSemantics.EXPLICIT_NO_REACTIVATION
        )


@dataclass(frozen=True)
class ProductionBoundarySafeSummary:
    boundary_evidence_id: str
    evaluation_time: str
    source_lifecycle_status: str
    profile_id: str
    profile_version: str
    protocol_version: str
    product_id: str
    product_version: str
    compatibility_evidence_kind: str
    manual_validation_state: str
    persistence_state: str
    runtime_authorization_state: str
    security_review_state: str
    production_equivalent_state: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ProductionBoundaryEvidence:
    boundary_evidence_id: str
    evaluation_time: datetime
    source_admission_entry_digest: str
    source_replacement_entry_digest: str | None
    source_lifecycle_status: RegistryStatus
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    plan_digest: str
    evidence_digest: str
    reviewer_attestation_digest: str
    approval_digest: str
    admission_decision_digest: str
    replacement_decision_digest: str | None
    registry_entry_digest: str
    registry_state_digest: str
    compatibility_evidence_kind: CompatibilityEvidenceKind
    manual_validation_state: ManualValidationState
    persistence_state: PersistenceState
    runtime_authorization_state: RuntimeAuthorizationState
    security_review_state: SecurityReviewState
    validation_operator_id: str
    evidence_reviewer_id: str
    approver_id: str
    registry_administrator_id: str
    boundary_reviewer_id: str
    authorization_approver_id: str
    evidence_completed_at: datetime
    reviewed_at: datetime
    approved_at: datetime
    admission_evaluated_at: datetime
    evidence_expires_at: datetime
    latest_required_action_at: datetime
    persistence_metadata: PersistenceBoundaryMetadata
    safe_context: tuple[str, ...]
    replacement_evaluated_at: datetime | None = None
    lifecycle_evaluated_at: datetime | None = None
    chain_reuse_detected: bool = False
    unresolved_revalidation: bool = False
    pending_lifecycle_transition: bool = False
    manual_validation_execution_digest: str | None = None
    manual_validation_evidence_digest: str | None = None
    manual_validation_review_digest: str | None = None
    manual_validation_approval_digest: str | None = None
    production_equivalent_state: ProductionEquivalentState = (
        ProductionEquivalentState.NOT_ASSESSED
    )
    equivalence_assessment_digest: str | None = None
    equivalence_review_digest: str | None = None
    equivalence_approval_digest: str | None = None
    equivalence_criteria_digest: str | None = None
    equivalence_evidence_descriptor_digest: str | None = None
    safe_summary: ProductionBoundarySafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_PRODUCTION_BOUNDARY_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        identifiers = (
            self.boundary_evidence_id,
            self.profile_id,
            self.product_id,
            self.validation_operator_id,
            self.evidence_reviewer_id,
            self.approver_id,
            self.registry_administrator_id,
            self.boundary_reviewer_id,
            self.authorization_approver_id,
        )
        if not all(_is_identifier(value) for value in identifiers):
            _raise(ProductionBoundaryErrorCategory.INVALID_IDENTIFIER)
        digests = (
            self.source_admission_entry_digest,
            self.plan_digest,
            self.evidence_digest,
            self.reviewer_attestation_digest,
            self.approval_digest,
            self.admission_decision_digest,
            self.registry_entry_digest,
            self.registry_state_digest,
        )
        optional_digests = (
            self.source_replacement_entry_digest,
            self.replacement_decision_digest,
            self.manual_validation_execution_digest,
            self.manual_validation_evidence_digest,
            self.manual_validation_review_digest,
            self.manual_validation_approval_digest,
            self.equivalence_assessment_digest,
            self.equivalence_review_digest,
            self.equivalence_approval_digest,
            self.equivalence_criteria_digest,
            self.equivalence_evidence_descriptor_digest,
        )
        if not all(_is_digest(value) for value in digests) or any(
            value is not None and not _is_digest(value) for value in optional_digests
        ):
            _raise(ProductionBoundaryErrorCategory.INVALID_DIGEST)
        times = (
            self.evaluation_time,
            self.evidence_completed_at,
            self.reviewed_at,
            self.approved_at,
            self.admission_evaluated_at,
            self.evidence_expires_at,
            self.latest_required_action_at,
        )
        optional_times = (self.replacement_evaluated_at, self.lifecycle_evaluated_at)
        if not all(_is_aware(value) for value in times) or any(
            value is not None and not _is_aware(value) for value in optional_times
        ):
            _raise(ProductionBoundaryErrorCategory.INVALID_TEMPORAL_INPUT)
        if (
            not isinstance(self.source_lifecycle_status, RegistryStatus)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (self.profile_version, self.protocol_version, self.product_version)
            )
            or not isinstance(self.persistence_metadata, PersistenceBoundaryMetadata)
            or not isinstance(self.compatibility_evidence_kind, CompatibilityEvidenceKind)
            or not isinstance(self.manual_validation_state, ManualValidationState)
            or not isinstance(self.persistence_state, PersistenceState)
            or not isinstance(self.runtime_authorization_state, RuntimeAuthorizationState)
            or not isinstance(self.security_review_state, SecurityReviewState)
            or not isinstance(self.production_equivalent_state, ProductionEquivalentState)
            or not all(
                type(value) is bool
                for value in (
                    self.chain_reuse_detected,
                    self.unresolved_revalidation,
                    self.pending_lifecycle_transition,
                )
            )
        ):
            _raise(ProductionBoundaryErrorCategory.INVALID_CONTRACT)
        if (self.source_replacement_entry_digest is None) != (
            self.replacement_decision_digest is None
        ):
            _raise(ProductionBoundaryErrorCategory.INVALID_CONTRACT)
        manual_chain = (
            self.manual_validation_execution_digest,
            self.manual_validation_evidence_digest,
            self.manual_validation_review_digest,
            self.manual_validation_approval_digest,
        )
        if any(value is None for value in manual_chain) and any(
            value is not None for value in manual_chain
        ):
            _raise(ProductionBoundaryErrorCategory.INVALID_CONTRACT)
        equivalence_chain = (
            self.equivalence_assessment_digest,
            self.equivalence_review_digest,
            self.equivalence_approval_digest,
            self.equivalence_criteria_digest,
            self.equivalence_evidence_descriptor_digest,
        )
        if any(value is None for value in equivalence_chain) and any(
            value is not None for value in equivalence_chain
        ):
            _raise(ProductionBoundaryErrorCategory.INVALID_CONTRACT)
        if (
            self.production_equivalent_state is ProductionEquivalentState.APPROVED
            and any(value is None for value in equivalence_chain)
        ):
            _raise(ProductionBoundaryErrorCategory.INVALID_CONTRACT)
        if (
            not isinstance(self.safe_context, tuple)
            or tuple(sorted(set(self.safe_context))) != self.safe_context
            or any(
                not isinstance(value, str) or value not in _SAFE_CONTEXT
                for value in self.safe_context
            )
        ):
            _raise(ProductionBoundaryErrorCategory.INVALID_SAFE_CONTEXT)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ProductionBoundarySafeSummary(
                boundary_evidence_id=self.boundary_evidence_id,
                evaluation_time=_canonical_datetime(self.evaluation_time),
                source_lifecycle_status=self.source_lifecycle_status.value,
                profile_id=self.profile_id,
                profile_version=str(self.profile_version),
                protocol_version=str(self.protocol_version),
                product_id=self.product_id,
                product_version=str(self.product_version),
                compatibility_evidence_kind=self.compatibility_evidence_kind.value,
                manual_validation_state=self.manual_validation_state.value,
                persistence_state=self.persistence_state.value,
                runtime_authorization_state=self.runtime_authorization_state.value,
                security_review_state=self.security_review_state.value,
                production_equivalent_state=self.production_equivalent_state.value,
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "actor_identities": {
                    "authorization_approver_id": self.authorization_approver_id,
                    "boundary_reviewer_id": self.boundary_reviewer_id,
                    "evidence_reviewer_id": self.evidence_reviewer_id,
                    "approver_id": self.approver_id,
                    "registry_administrator_id": self.registry_administrator_id,
                    "validation_operator_id": self.validation_operator_id,
                },
                "admission_decision_digest": self.admission_decision_digest,
                "admission_evaluated_at": _canonical_datetime(self.admission_evaluated_at),
                "approval_digest": self.approval_digest,
                "approved_at": _canonical_datetime(self.approved_at),
                "boundary_evidence_id": self.boundary_evidence_id,
                "chain_reuse_detected": self.chain_reuse_detected,
                "compatibility_evidence_kind": self.compatibility_evidence_kind.value,
                "evaluation_time": _canonical_datetime(self.evaluation_time),
                "evidence_completed_at": _canonical_datetime(self.evidence_completed_at),
                "evidence_digest": self.evidence_digest,
                "evidence_expires_at": _canonical_datetime(self.evidence_expires_at),
                "latest_required_action_at": _canonical_datetime(self.latest_required_action_at),
                "lifecycle_evaluated_at": _optional_datetime(self.lifecycle_evaluated_at),
                "manual_validation_state": self.manual_validation_state.value,
                "production_equivalence_chain": {
                    "approval_digest": self.equivalence_approval_digest,
                    "assessment_digest": self.equivalence_assessment_digest,
                    "criteria_digest": self.equivalence_criteria_digest,
                    "evidence_descriptor_digest": (
                        self.equivalence_evidence_descriptor_digest
                    ),
                    "review_digest": self.equivalence_review_digest,
                    "state": self.production_equivalent_state.value,
                },
                "manual_validation_chain": {
                    "approval_digest": self.manual_validation_approval_digest,
                    "evidence_digest": self.manual_validation_evidence_digest,
                    "execution_digest": self.manual_validation_execution_digest,
                    "review_digest": self.manual_validation_review_digest,
                },
                "pending_lifecycle_transition": self.pending_lifecycle_transition,
                "persistence_metadata": {
                    "append_only_audit_required": (
                        self.persistence_metadata.append_only_audit_required
                    ),
                    "backup_restore_required": self.persistence_metadata.backup_restore_required,
                    "boundary_approved": self.persistence_metadata.boundary_approved,
                    "durability_required": self.persistence_metadata.durability_required,
                    "rollback_semantics": self.persistence_metadata.rollback_semantics.value,
                    "secret_separation_required": (
                        self.persistence_metadata.secret_separation_required
                    ),
                    "tamper_evidence_required": self.persistence_metadata.tamper_evidence_required,
                },
                "persistence_state": self.persistence_state.value,
                "plan_digest": self.plan_digest,
                "product_id": self.product_id,
                "product_version": str(self.product_version),
                "profile_id": self.profile_id,
                "profile_version": str(self.profile_version),
                "protocol_version": str(self.protocol_version),
                "registry_entry_digest": self.registry_entry_digest,
                "registry_state_digest": self.registry_state_digest,
                "replacement_decision_digest": self.replacement_decision_digest,
                "replacement_evaluated_at": _optional_datetime(self.replacement_evaluated_at),
                "reviewed_at": _canonical_datetime(self.reviewed_at),
                "reviewer_attestation_digest": self.reviewer_attestation_digest,
                "runtime_authorization_state": self.runtime_authorization_state.value,
                "safe_context": list(self.safe_context),
                "security_review_state": self.security_review_state.value,
                "source_admission_entry_digest": self.source_admission_entry_digest,
                "source_lifecycle_status": self.source_lifecycle_status.value,
                "source_replacement_entry_digest": self.source_replacement_entry_digest,
                "unresolved_revalidation": self.unresolved_revalidation,
            }
        )

    def __repr__(self) -> str:
        return "ProductionBoundaryEvidence(<safe>)"

    @property
    def manual_validation_chain_complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.manual_validation_execution_digest,
                self.manual_validation_evidence_digest,
                self.manual_validation_review_digest,
                self.manual_validation_approval_digest,
            )
        )

    @property
    def production_equivalence_chain_complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.equivalence_assessment_digest,
                self.equivalence_review_digest,
                self.equivalence_approval_digest,
                self.equivalence_criteria_digest,
                self.equivalence_evidence_descriptor_digest,
            )
        )


def canonical_registry_state_digest(entry_digests: tuple[str, ...]) -> str:
    if (
        not isinstance(entry_digests, tuple)
        or not entry_digests
        or tuple(sorted(set(entry_digests))) != entry_digests
        or not all(_is_digest(value) for value in entry_digests)
    ):
        _raise(ProductionBoundaryErrorCategory.INVALID_DIGEST)
    return _digest(_canonical_json({"entry_digests": list(entry_digests)}))


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else _canonical_datetime(value)


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _raise(category: ProductionBoundaryErrorCategory) -> None:
    raise ProductionBoundaryError(category)
