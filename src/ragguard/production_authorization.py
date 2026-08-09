from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from ragguard.production_admission import ProductionAdmissionDecision
from ragguard.production_boundary import (
    CompatibilityEvidenceKind,
    ManualValidationState,
    PersistenceState,
    ProductionBoundaryEvidence,
    RuntimeAuthorizationState,
    SecurityReviewState,
    canonical_registry_state_digest,
)
from ragguard.production_registry import RegistryStatus
from ragguard.registry_admission import RegistryAdmissionEntry
from ragguard.replacement_admission import ReplacementRegistryEntry


CANONICAL_PRODUCTION_AUTHORIZATION_DIGEST_ALGORITHM = "sha256"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ProductionAuthorizationResult(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_MANUAL_VALIDATION = "needs_manual_validation"
    NEEDS_SECURITY_REVIEW = "needs_security_review"
    NEEDS_PERSISTENCE_BOUNDARY = "needs_persistence_boundary"
    NEEDS_RUNTIME_AUTHORIZATION_BOUNDARY = "needs_runtime_authorization_boundary"
    ELIGIBLE_FOR_AUTHORIZATION_REVIEW = "eligible_for_authorization_review"


class ProductionAuthorizationReason(str, Enum):
    IDENTITY_MISMATCH = "identity_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    SECURITY_BOUNDARY_VIOLATION = "security_boundary_violation"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    SOURCE_STATUS_INELIGIBLE = "source_status_ineligible"
    STALE_EVIDENCE = "stale_evidence"
    EVIDENCE_EXPIRED = "evidence_expired"
    REVALIDATION_REQUIRED = "revalidation_required"
    LIFECYCLE_TRANSITION_PENDING = "lifecycle_transition_pending"
    CHAIN_REUSE = "chain_reuse"
    MANUAL_VALIDATION_REQUIRED = "manual_validation_required"
    SECURITY_REVIEW_REQUIRED = "security_review_required"
    PERSISTENCE_BOUNDARY_REQUIRED = "persistence_boundary_required"
    RUNTIME_AUTHORIZATION_BOUNDARY_REQUIRED = "runtime_authorization_boundary_required"
    RUNTIME_ACTIVATION_PROHIBITED = "runtime_activation_prohibited"


_REASON_ORDER = tuple(ProductionAuthorizationReason)
_STRUCTURAL_REASONS = frozenset(_REASON_ORDER[:5])
_STALE_REASONS = frozenset(_REASON_ORDER[6:11])


class ProductionAuthorizationError(ValueError):
    def __init__(self) -> None:
        super().__init__("production_authorization_request_invalid")


@dataclass(frozen=True, repr=False)
class ProductionAuthorizationRequest:
    request_id: str
    evidence: ProductionBoundaryEvidence
    source_entry: RegistryAdmissionEntry | ReplacementRegistryEntry = field(repr=False)
    source_admission_decision: ProductionAdmissionDecision = field(repr=False)
    registry_snapshot_digests: tuple[str, ...]
    use_current_alias: bool = False
    use_latest_alias: bool = False
    allow_fallback: bool = False
    allow_nearest_version: bool = False
    allow_schema_inference: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.request_id, str)
            or _IDENTIFIER.fullmatch(self.request_id) is None
            or not isinstance(self.evidence, ProductionBoundaryEvidence)
            or not isinstance(
                self.source_entry,
                (RegistryAdmissionEntry, ReplacementRegistryEntry),
            )
            or not isinstance(
                self.source_admission_decision,
                ProductionAdmissionDecision,
            )
            or not all(
                type(value) is bool
                for value in (
                    self.use_current_alias,
                    self.use_latest_alias,
                    self.allow_fallback,
                    self.allow_nearest_version,
                    self.allow_schema_inference,
                )
            )
        ):
            raise ProductionAuthorizationError()
        canonical_registry_state_digest(self.registry_snapshot_digests)


@dataclass(frozen=True)
class ProductionAuthorizationSafeSummary:
    request_id: str
    result: str
    reason_categories: tuple[str, ...]
    boundary_evidence_digest: str
    source_entry_digest: str
    evaluated_at: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ProductionAuthorizationCandidate:
    request_id: str
    result: ProductionAuthorizationResult
    reason_categories: tuple[ProductionAuthorizationReason, ...]
    boundary_evidence_digest: str
    source_entry_digest: str
    evaluated_at: datetime
    write_count: int = field(init=False, default=0)
    mutation_count: int = field(init=False, default=0)
    transport_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    persistence_write_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    safe_summary: ProductionAuthorizationSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_PRODUCTION_AUTHORIZATION_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            not isinstance(self.request_id, str)
            or _IDENTIFIER.fullmatch(self.request_id) is None
            or not isinstance(self.result, ProductionAuthorizationResult)
            or not isinstance(self.reason_categories, tuple)
            or any(
                not isinstance(reason, ProductionAuthorizationReason)
                for reason in self.reason_categories
            )
            or tuple(
                reason
                for reason in _REASON_ORDER
                if reason in self.reason_categories
            )
            != self.reason_categories
            or not isinstance(self.boundary_evidence_digest, str)
            or _DIGEST.fullmatch(self.boundary_evidence_digest) is None
            or not isinstance(self.source_entry_digest, str)
            or _DIGEST.fullmatch(self.source_entry_digest) is None
            or not isinstance(self.evaluated_at, datetime)
            or self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() is None
        ):
            raise ProductionAuthorizationError()
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ProductionAuthorizationSafeSummary(
                request_id=self.request_id,
                result=self.result.value,
                reason_categories=tuple(value.value for value in self.reason_categories),
                boundary_evidence_digest=self.boundary_evidence_digest,
                source_entry_digest=self.source_entry_digest,
                evaluated_at=_canonical_datetime(self.evaluated_at),
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "boundary_evidence_digest": self.boundary_evidence_digest,
                "evaluated_at": _canonical_datetime(self.evaluated_at),
                "reason_categories": [value.value for value in self.reason_categories],
                "request_id": self.request_id,
                "result": self.result.value,
                "source_entry_digest": self.source_entry_digest,
            }
        )

    def __repr__(self) -> str:
        return "ProductionAuthorizationCandidate(<safe>)"


def evaluate_production_authorization(
    request: ProductionAuthorizationRequest,
) -> ProductionAuthorizationCandidate:
    if not isinstance(request, ProductionAuthorizationRequest):
        raise ProductionAuthorizationError()
    evidence = request.evidence
    entry = request.source_entry
    decision = request.source_admission_decision
    reasons: set[ProductionAuthorizationReason] = set()

    if not _identity_matches(evidence, entry, decision):
        reasons.add(ProductionAuthorizationReason.IDENTITY_MISMATCH)
    if not _digests_match(
        evidence,
        entry,
        decision,
        request.registry_snapshot_digests,
    ):
        reasons.add(ProductionAuthorizationReason.DIGEST_MISMATCH)
    if any(
        (
            request.use_current_alias,
            request.use_latest_alias,
            request.allow_fallback,
            request.allow_nearest_version,
            request.allow_schema_inference,
        )
    ):
        reasons.add(ProductionAuthorizationReason.SECURITY_BOUNDARY_VIOLATION)
    if len(set(_actors(evidence))) != len(_actors(evidence)):
        reasons.add(ProductionAuthorizationReason.ROLE_CONFLICT)
    if not _temporal_valid(evidence):
        reasons.add(ProductionAuthorizationReason.TEMPORAL_INVALID)
    if evidence.evaluation_time >= evidence.evidence_expires_at:
        reasons.add(ProductionAuthorizationReason.EVIDENCE_EXPIRED)
    if evidence.latest_required_action_at > evidence.evaluation_time:
        reasons.add(ProductionAuthorizationReason.STALE_EVIDENCE)
    if (
        evidence.source_lifecycle_status is not RegistryStatus.ACTIVE
        or entry.registry_status is not RegistryStatus.ACTIVE
    ):
        reasons.add(ProductionAuthorizationReason.SOURCE_STATUS_INELIGIBLE)
    if evidence.unresolved_revalidation:
        reasons.add(ProductionAuthorizationReason.REVALIDATION_REQUIRED)
    if evidence.pending_lifecycle_transition:
        reasons.add(ProductionAuthorizationReason.LIFECYCLE_TRANSITION_PENDING)
    if evidence.chain_reuse_detected:
        reasons.add(ProductionAuthorizationReason.CHAIN_REUSE)

    result = _result(evidence, reasons)
    ordered = tuple(reason for reason in _REASON_ORDER if reason in reasons)
    return ProductionAuthorizationCandidate(
        request_id=request.request_id,
        result=result,
        reason_categories=ordered,
        boundary_evidence_digest=evidence.canonical_digest,
        source_entry_digest=entry.canonical_digest,
        evaluated_at=evidence.evaluation_time,
    )


def _result(
    evidence: ProductionBoundaryEvidence,
    reasons: set[ProductionAuthorizationReason],
) -> ProductionAuthorizationResult:
    if (
        reasons & _STRUCTURAL_REASONS
        or ProductionAuthorizationReason.SOURCE_STATUS_INELIGIBLE in reasons
        or reasons & _STALE_REASONS
    ):
        return ProductionAuthorizationResult.INELIGIBLE
    if (
        evidence.manual_validation_state is not ManualValidationState.APPROVED
        or evidence.compatibility_evidence_kind is CompatibilityEvidenceKind.SYNTHETIC_ONLY
    ):
        reasons.add(ProductionAuthorizationReason.MANUAL_VALIDATION_REQUIRED)
        return ProductionAuthorizationResult.NEEDS_MANUAL_VALIDATION
    if evidence.security_review_state is not SecurityReviewState.APPROVED:
        reasons.add(ProductionAuthorizationReason.SECURITY_REVIEW_REQUIRED)
        return ProductionAuthorizationResult.NEEDS_SECURITY_REVIEW
    if (
        evidence.persistence_state is not PersistenceState.PRODUCTION_READY
        or not evidence.persistence_metadata.is_approved
    ):
        reasons.add(ProductionAuthorizationReason.PERSISTENCE_BOUNDARY_REQUIRED)
        return ProductionAuthorizationResult.NEEDS_PERSISTENCE_BOUNDARY
    if evidence.runtime_authorization_state is RuntimeAuthorizationState.ACTIVE:
        reasons.add(ProductionAuthorizationReason.RUNTIME_ACTIVATION_PROHIBITED)
        return ProductionAuthorizationResult.INELIGIBLE
    if evidence.runtime_authorization_state is not RuntimeAuthorizationState.CANDIDATE_ONLY:
        reasons.add(ProductionAuthorizationReason.RUNTIME_AUTHORIZATION_BOUNDARY_REQUIRED)
        return ProductionAuthorizationResult.NEEDS_RUNTIME_AUTHORIZATION_BOUNDARY
    return ProductionAuthorizationResult.ELIGIBLE_FOR_AUTHORIZATION_REVIEW


def _identity_matches(
    evidence: ProductionBoundaryEvidence,
    entry: object,
    decision: ProductionAdmissionDecision,
) -> bool:
    return all(
        (
            evidence.profile_id == entry.profile_id,
            evidence.profile_version == entry.profile_version,
            evidence.protocol_version == entry.protocol_version,
            evidence.product_id == entry.product_id,
            evidence.product_version == entry.product_version,
            evidence.validation_operator_id == decision.validation_operator_id,
            evidence.evidence_reviewer_id == decision.evidence_reviewer_id,
            evidence.approver_id == decision.approver_id,
            evidence.registry_administrator_id
            == entry.registry_administrator_id,
        )
    )


def _digests_match(
    evidence: ProductionBoundaryEvidence,
    entry: object,
    decision: ProductionAdmissionDecision,
    snapshot: tuple[str, ...],
) -> bool:
    if _digest(entry.canonical_json()) != entry.canonical_digest:
        return False
    if _digest(decision.canonical_json()) != decision.canonical_digest:
        return False
    if evidence.admission_decision_digest != decision.canonical_digest:
        return False
    if entry.admission_decision_digest != decision.canonical_digest:
        return False
    if evidence.approval_digest != decision.approval_digest:
        return False
    if entry.approval_digest != decision.approval_digest:
        return False
    if evidence.registry_entry_digest != entry.canonical_digest:
        return False
    if evidence.registry_state_digest != canonical_registry_state_digest(snapshot):
        return False
    if entry.canonical_digest not in snapshot:
        return False
    if any(
        (
            evidence.plan_digest != entry.plan_digest,
            evidence.evidence_digest != entry.evidence_digest,
            evidence.reviewer_attestation_digest != entry.reviewer_attestation_digest,
            evidence.admission_decision_digest != entry.admission_decision_digest,
        )
    ):
        return False
    if isinstance(entry, RegistryAdmissionEntry):
        return (
            evidence.source_replacement_entry_digest is None
            and evidence.replacement_decision_digest is None
            and evidence.source_admission_entry_digest == entry.canonical_digest
        )
    return (
        evidence.source_replacement_entry_digest == entry.canonical_digest
        and evidence.source_admission_entry_digest == entry.predecessor_entry_digest
        and evidence.replacement_decision_digest == entry.replacement_request_digest
    )


def _actors(evidence: ProductionBoundaryEvidence) -> tuple[str, ...]:
    return (
        evidence.validation_operator_id,
        evidence.evidence_reviewer_id,
        evidence.approver_id,
        evidence.registry_administrator_id,
        evidence.boundary_reviewer_id,
        evidence.authorization_approver_id,
    )


def _temporal_valid(evidence: ProductionBoundaryEvidence) -> bool:
    actions = tuple(
        value
        for value in (evidence.replacement_evaluated_at, evidence.lifecycle_evaluated_at)
        if value is not None
    )
    latest_action = max((evidence.admission_evaluated_at, *actions))
    return (
        evidence.evidence_completed_at <= evidence.reviewed_at
        < evidence.approved_at
        <= evidence.admission_evaluated_at
        and all(
            evidence.admission_evaluated_at <= value <= evidence.evaluation_time
            for value in actions
        )
        and evidence.latest_required_action_at == latest_action
        and evidence.latest_required_action_at <= evidence.evaluation_time
        < evidence.evidence_expires_at
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
