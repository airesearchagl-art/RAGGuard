from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from ragguard.compatibility import SemanticVersion
from ragguard.production_authorization import (
    ProductionAuthorizationCandidate,
    ProductionAuthorizationResult,
)
from ragguard.production_boundary import (
    CompatibilityEvidenceKind,
    ManualValidationState,
    ProductionBoundaryEvidence,
    SecurityReviewState,
    canonical_registry_state_digest,
)
from ragguard.production_persistence import PersistedAuthorizationRecord
from ragguard.production_registry import RegistryStatus


CANONICAL_AUTHORIZATION_ACTIVATION_DIGEST_ALGORITHM = "sha256"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ActivationEvaluationResult(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_MANUAL_VALIDATION = "needs_manual_validation"
    NEEDS_PERSISTENCE_VERIFICATION = "needs_persistence_verification"
    NEEDS_ACTIVATION_REVIEW = "needs_activation_review"
    READY_FOR_ACTIVATION_COMMIT = "ready_for_activation_commit"


class ActivationReason(str, Enum):
    IDENTITY_MISMATCH = "identity_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    INTEGRITY_MISMATCH = "integrity_mismatch"
    UNSAFE_RESOLUTION = "unsafe_resolution"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    SOURCE_CANDIDATE_INELIGIBLE = "source_candidate_ineligible"
    LIFECYCLE_INACTIVE = "lifecycle_inactive"
    STALE_SOURCE = "stale_source"
    REPLACED_PREDECESSOR = "replaced_predecessor"
    EVIDENCE_EXPIRED = "evidence_expired"
    REPLAY_DETECTED = "replay_detected"
    MANUAL_VALIDATION_REQUIRED = "manual_validation_required"
    PERSISTENCE_VERIFICATION_REQUIRED = "persistence_verification_required"
    ACTIVATION_REVIEW_REQUIRED = "activation_review_required"


_REASON_ORDER = tuple(ActivationReason)
_STRUCTURAL = frozenset(_REASON_ORDER[:7])
_LIFECYCLE = frozenset(_REASON_ORDER[7:12])


class AuthorizationActivationError(ValueError):
    def __init__(self) -> None:
        super().__init__("authorization_activation_contract_invalid")


@dataclass(frozen=True, repr=False)
class ActivationRequest:
    activation_request_id: str
    persisted_record_digest: str
    expected_persistence_generation: int
    activation_requested_at: datetime
    activation_requester_id: str
    activation_reviewer_id: str
    authorization_approver_id: str
    expected_profile_id: str
    expected_profile_version: SemanticVersion
    expected_product_id: str
    expected_product_version: SemanticVersion
    expected_protocol_version: SemanticVersion
    expected_registry_state_digest: str
    expected_lifecycle_status: RegistryStatus
    request_nonce_digest: str
    persistence_verified: bool
    activation_review_approved: bool
    use_current_alias: bool = False
    use_latest_alias: bool = False
    allow_fallback: bool = False
    infer_source: bool = False
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_AUTHORIZATION_ACTIVATION_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        identifiers = (
            self.activation_request_id,
            self.activation_requester_id,
            self.activation_reviewer_id,
            self.authorization_approver_id,
            self.expected_profile_id,
            self.expected_product_id,
        )
        if (
            not all(_is_identifier(value) for value in identifiers)
            or not _is_digest(self.persisted_record_digest)
            or not _is_digest(self.expected_registry_state_digest)
            or not _is_digest(self.request_nonce_digest)
            or type(self.expected_persistence_generation) is not int
            or self.expected_persistence_generation < 1
            or not _is_aware(self.activation_requested_at)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.expected_profile_version,
                    self.expected_product_version,
                    self.expected_protocol_version,
                )
            )
            or not isinstance(self.expected_lifecycle_status, RegistryStatus)
            or not all(
                type(value) is bool
                for value in (
                    self.persistence_verified,
                    self.activation_review_approved,
                    self.use_current_alias,
                    self.use_latest_alias,
                    self.allow_fallback,
                    self.infer_source,
                )
            )
        ):
            raise AuthorizationActivationError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "activation_request_id": self.activation_request_id,
                "activation_requested_at": _canonical_datetime(
                    self.activation_requested_at
                ),
                "activation_requester_id": self.activation_requester_id,
                "activation_review_approved": self.activation_review_approved,
                "activation_reviewer_id": self.activation_reviewer_id,
                "allow_fallback": self.allow_fallback,
                "authorization_approver_id": self.authorization_approver_id,
                "expected_lifecycle_status": self.expected_lifecycle_status.value,
                "expected_persistence_generation": (
                    self.expected_persistence_generation
                ),
                "expected_product_id": self.expected_product_id,
                "expected_product_version": str(self.expected_product_version),
                "expected_profile_id": self.expected_profile_id,
                "expected_profile_version": str(self.expected_profile_version),
                "expected_protocol_version": str(self.expected_protocol_version),
                "expected_registry_state_digest": (
                    self.expected_registry_state_digest
                ),
                "infer_source": self.infer_source,
                "persisted_record_digest": self.persisted_record_digest,
                "persistence_verified": self.persistence_verified,
                "request_nonce_digest": self.request_nonce_digest,
                "use_current_alias": self.use_current_alias,
                "use_latest_alias": self.use_latest_alias,
            }
        )

    def __repr__(self) -> str:
        return "ActivationRequest(<safe>)"


@dataclass(frozen=True, repr=False)
class ActivationCommitPlan:
    activation_request_digest: str
    persisted_record_digest: str
    source_candidate_digest: str
    expected_registry_state_digest: str
    expected_generation: int
    approved_at: datetime
    approver_id: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not all(
                _is_digest(value)
                for value in (
                    self.activation_request_digest,
                    self.persisted_record_digest,
                    self.source_candidate_digest,
                    self.expected_registry_state_digest,
                )
            )
            or type(self.expected_generation) is not int
            or self.expected_generation < 1
            or not _is_aware(self.approved_at)
            or not _is_identifier(self.approver_id)
        ):
            raise AuthorizationActivationError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "activation_request_digest": self.activation_request_digest,
                "approved_at": _canonical_datetime(self.approved_at),
                "approver_id": self.approver_id,
                "expected_generation": self.expected_generation,
                "expected_registry_state_digest": (
                    self.expected_registry_state_digest
                ),
                "persisted_record_digest": self.persisted_record_digest,
                "source_candidate_digest": self.source_candidate_digest,
            }
        )

    def __repr__(self) -> str:
        return "ActivationCommitPlan(<safe>)"


@dataclass(frozen=True)
class ActivationEvaluationSafeSummary:
    activation_request_id: str
    result: str
    reason_categories: tuple[str, ...]
    persisted_record_digest: str
    persistence_generation: int
    lifecycle_status: str
    evaluated_at: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ActivationEvaluation:
    activation_request_id: str
    result: ActivationEvaluationResult
    reason_categories: tuple[ActivationReason, ...]
    activation_request_digest: str
    persisted_record_digest: str
    source_candidate_digest: str
    persistence_generation: int
    lifecycle_status: RegistryStatus
    evaluated_at: datetime
    commit_plan: ActivationCommitPlan | None
    write_count: int = field(init=False, default=0)
    mutation_count: int = field(init=False, default=0)
    transport_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    persistence_write_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    safe_summary: ActivationEvaluationSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not _is_identifier(self.activation_request_id)
            or not isinstance(self.result, ActivationEvaluationResult)
            or not isinstance(self.reason_categories, tuple)
            or tuple(reason for reason in _REASON_ORDER if reason in self.reason_categories)
            != self.reason_categories
            or not all(isinstance(reason, ActivationReason) for reason in self.reason_categories)
            or not all(
                _is_digest(value)
                for value in (
                    self.activation_request_digest,
                    self.persisted_record_digest,
                    self.source_candidate_digest,
                )
            )
            or type(self.persistence_generation) is not int
            or not isinstance(self.lifecycle_status, RegistryStatus)
            or not _is_aware(self.evaluated_at)
            or (
                self.result is ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT
            )
            != (self.commit_plan is not None)
        ):
            raise AuthorizationActivationError()
        canonical = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", canonical)
        object.__setattr__(
            self,
            "safe_summary",
            ActivationEvaluationSafeSummary(
                activation_request_id=self.activation_request_id,
                result=self.result.value,
                reason_categories=tuple(reason.value for reason in self.reason_categories),
                persisted_record_digest=self.persisted_record_digest,
                persistence_generation=self.persistence_generation,
                lifecycle_status=self.lifecycle_status.value,
                evaluated_at=_canonical_datetime(self.evaluated_at),
                canonical_digest=canonical,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "activation_request_digest": self.activation_request_digest,
                "activation_request_id": self.activation_request_id,
                "commit_plan_digest": (
                    None if self.commit_plan is None else self.commit_plan.canonical_digest
                ),
                "evaluated_at": _canonical_datetime(self.evaluated_at),
                "lifecycle_status": self.lifecycle_status.value,
                "persisted_record_digest": self.persisted_record_digest,
                "persistence_generation": self.persistence_generation,
                "reason_categories": [reason.value for reason in self.reason_categories],
                "result": self.result.value,
                "source_candidate_digest": self.source_candidate_digest,
            }
        )

    def __repr__(self) -> str:
        return "ActivationEvaluation(<safe>)"


@dataclass(frozen=True)
class _ActivationReplayState:
    used_request_ids: frozenset[str] = frozenset()
    used_nonce_digests: frozenset[str] = frozenset()
    used_record_digests: frozenset[str] = frozenset()
    committed_review_count: int = 0


class InMemoryActivationReplayStore:
    """Test-only replay ledger; it cannot activate a runtime."""

    def __init__(self) -> None:
        self._state = _ActivationReplayState()

    @property
    def used_request_ids(self) -> frozenset[str]:
        return self._state.used_request_ids

    @property
    def used_nonce_digests(self) -> frozenset[str]:
        return self._state.used_nonce_digests

    @property
    def used_record_digests(self) -> frozenset[str]:
        return self._state.used_record_digests

    @property
    def committed_review_count(self) -> int:
        return self._state.committed_review_count

    def evaluate(
        self,
        request: ActivationRequest,
        record: PersistedAuthorizationRecord,
        candidate: ProductionAuthorizationCandidate,
        evidence: ProductionBoundaryEvidence,
        registry_snapshot_digests: tuple[str, ...],
        evaluation_time: datetime,
    ) -> ActivationEvaluation:
        result = evaluate_activation_request(
            request,
            record,
            candidate,
            evidence,
            registry_snapshot_digests,
            evaluation_time,
            used_request_ids=self._state.used_request_ids,
            used_nonce_digests=self._state.used_nonce_digests,
            used_record_digests=self._state.used_record_digests,
        )
        if result.result is ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT:
            self._state = _ActivationReplayState(
                used_request_ids=self._state.used_request_ids
                | {request.activation_request_id},
                used_nonce_digests=self._state.used_nonce_digests
                | {request.request_nonce_digest},
                used_record_digests=self._state.used_record_digests
                | {request.persisted_record_digest},
                committed_review_count=self._state.committed_review_count + 1,
            )
        return result


def evaluate_activation_request(
    request: ActivationRequest,
    record: PersistedAuthorizationRecord,
    candidate: ProductionAuthorizationCandidate,
    evidence: ProductionBoundaryEvidence,
    registry_snapshot_digests: tuple[str, ...],
    evaluation_time: datetime,
    *,
    used_request_ids: frozenset[str] = frozenset(),
    used_nonce_digests: frozenset[str] = frozenset(),
    used_record_digests: frozenset[str] = frozenset(),
) -> ActivationEvaluation:
    if (
        not isinstance(request, ActivationRequest)
        or not isinstance(record, PersistedAuthorizationRecord)
        or not isinstance(candidate, ProductionAuthorizationCandidate)
        or not isinstance(evidence, ProductionBoundaryEvidence)
        or not _is_aware(evaluation_time)
        or not all(
            isinstance(value, frozenset)
            for value in (
                used_request_ids,
                used_nonce_digests,
                used_record_digests,
            )
        )
    ):
        raise AuthorizationActivationError()
    reasons: set[ActivationReason] = set()
    if not _identity_matches(request, evidence):
        reasons.add(ActivationReason.IDENTITY_MISMATCH)
    if not _digests_match(
        request, record, candidate, evidence, registry_snapshot_digests
    ):
        reasons.add(ActivationReason.DIGEST_MISMATCH)
    if not _integrity_matches(record, candidate, request):
        reasons.add(ActivationReason.INTEGRITY_MISMATCH)
    if any(
        (
            request.use_current_alias,
            request.use_latest_alias,
            request.allow_fallback,
            request.infer_source,
        )
    ):
        reasons.add(ActivationReason.UNSAFE_RESOLUTION)
    if not _roles_valid(request, record, evidence):
        reasons.add(ActivationReason.ROLE_CONFLICT)
    if not (
        record.persisted_at
        <= request.activation_requested_at
        <= evaluation_time
        < evidence.evidence_expires_at
    ):
        reasons.add(ActivationReason.TEMPORAL_INVALID)
    if evaluation_time >= evidence.evidence_expires_at:
        reasons.add(ActivationReason.EVIDENCE_EXPIRED)
    if (
        record.source_lifecycle_status is not RegistryStatus.ACTIVE
        or evidence.source_lifecycle_status is not RegistryStatus.ACTIVE
        or request.expected_lifecycle_status is not RegistryStatus.ACTIVE
    ):
        reasons.add(ActivationReason.LIFECYCLE_INACTIVE)
    if evidence.unresolved_revalidation or evidence.pending_lifecycle_transition:
        reasons.add(ActivationReason.STALE_SOURCE)
    if record.source_registry_entry_digest not in registry_snapshot_digests:
        reasons.add(ActivationReason.REPLACED_PREDECESSOR)
    if (
        request.activation_request_id in used_request_ids
        or request.request_nonce_digest in used_nonce_digests
        or request.persisted_record_digest in used_record_digests
    ):
        reasons.add(ActivationReason.REPLAY_DETECTED)

    result = _result(request, candidate, evidence, reasons)
    ordered = tuple(reason for reason in _REASON_ORDER if reason in reasons)
    plan = None
    if result is ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT:
        plan = ActivationCommitPlan(
            activation_request_digest=request.canonical_digest,
            persisted_record_digest=record.canonical_digest,
            source_candidate_digest=candidate.canonical_digest,
            expected_registry_state_digest=request.expected_registry_state_digest,
            expected_generation=request.expected_persistence_generation,
            approved_at=evaluation_time,
            approver_id=request.authorization_approver_id,
        )
    return ActivationEvaluation(
        activation_request_id=request.activation_request_id,
        result=result,
        reason_categories=ordered,
        activation_request_digest=request.canonical_digest,
        persisted_record_digest=record.canonical_digest,
        source_candidate_digest=candidate.canonical_digest,
        persistence_generation=record.persistence_generation,
        lifecycle_status=record.source_lifecycle_status,
        evaluated_at=evaluation_time,
        commit_plan=plan,
    )


def _result(
    request: ActivationRequest,
    candidate: ProductionAuthorizationCandidate,
    evidence: ProductionBoundaryEvidence,
    reasons: set[ActivationReason],
) -> ActivationEvaluationResult:
    if reasons & (_STRUCTURAL | _LIFECYCLE):
        return ActivationEvaluationResult.INELIGIBLE
    if (
        candidate.result is ProductionAuthorizationResult.NEEDS_MANUAL_VALIDATION
        or evidence.manual_validation_state is not ManualValidationState.APPROVED
        or evidence.compatibility_evidence_kind is CompatibilityEvidenceKind.SYNTHETIC_ONLY
    ):
        reasons.add(ActivationReason.MANUAL_VALIDATION_REQUIRED)
        return ActivationEvaluationResult.NEEDS_MANUAL_VALIDATION
    if candidate.result is ProductionAuthorizationResult.NEEDS_PERSISTENCE_BOUNDARY:
        reasons.add(ActivationReason.PERSISTENCE_VERIFICATION_REQUIRED)
        return ActivationEvaluationResult.NEEDS_PERSISTENCE_VERIFICATION
    if not request.persistence_verified:
        reasons.add(ActivationReason.PERSISTENCE_VERIFICATION_REQUIRED)
        return ActivationEvaluationResult.NEEDS_PERSISTENCE_VERIFICATION
    if candidate.result not in {
        ProductionAuthorizationResult.ELIGIBLE_FOR_AUTHORIZATION_REVIEW,
        ProductionAuthorizationResult.NEEDS_SECURITY_REVIEW,
    }:
        reasons.add(ActivationReason.SOURCE_CANDIDATE_INELIGIBLE)
        return ActivationEvaluationResult.INELIGIBLE
    if (
        candidate.result is ProductionAuthorizationResult.NEEDS_SECURITY_REVIEW
        or evidence.security_review_state is not SecurityReviewState.APPROVED
        or not request.activation_review_approved
    ):
        reasons.add(ActivationReason.ACTIVATION_REVIEW_REQUIRED)
        return ActivationEvaluationResult.NEEDS_ACTIVATION_REVIEW
    return ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT


def _identity_matches(
    request: ActivationRequest,
    evidence: ProductionBoundaryEvidence,
) -> bool:
    return all(
        (
            request.expected_profile_id == evidence.profile_id,
            request.expected_profile_version == evidence.profile_version,
            request.expected_product_id == evidence.product_id,
            request.expected_product_version == evidence.product_version,
            request.expected_protocol_version == evidence.protocol_version,
            request.authorization_approver_id == evidence.authorization_approver_id,
        )
    )


def _digests_match(
    request: ActivationRequest,
    record: PersistedAuthorizationRecord,
    candidate: ProductionAuthorizationCandidate,
    evidence: ProductionBoundaryEvidence,
    registry_snapshot_digests: tuple[str, ...],
) -> bool:
    try:
        registry_state = canonical_registry_state_digest(registry_snapshot_digests)
    except ValueError:
        return False
    return all(
        (
            request.persisted_record_digest == record.canonical_digest,
            request.expected_persistence_generation == record.persistence_generation,
            request.expected_registry_state_digest == registry_state,
            request.expected_registry_state_digest == evidence.registry_state_digest,
            record.source_candidate_digest == candidate.canonical_digest,
            record.source_boundary_evidence_digest == evidence.canonical_digest,
            candidate.boundary_evidence_digest == evidence.canonical_digest,
            record.source_admission_decision_digest
            == evidence.admission_decision_digest,
            record.source_registry_entry_digest == candidate.source_entry_digest,
            record.source_registry_entry_digest == evidence.registry_entry_digest,
            record.source_registry_state_digest == registry_state,
            record.source_replacement_digest == evidence.replacement_decision_digest,
        )
    )


def _integrity_matches(
    record: PersistedAuthorizationRecord,
    candidate: ProductionAuthorizationCandidate,
    request: ActivationRequest,
) -> bool:
    return all(
        (
            _digest(record.integrity_json()) == record.integrity_digest,
            _digest(record.canonical_json()) == record.canonical_digest,
            _digest(candidate.canonical_json()) == candidate.canonical_digest,
            _digest(request.canonical_json()) == request.canonical_digest,
        )
    )


def _roles_valid(
    request: ActivationRequest,
    record: PersistedAuthorizationRecord,
    evidence: ProductionBoundaryEvidence,
) -> bool:
    request_roles = (
        request.activation_requester_id,
        request.activation_reviewer_id,
        request.authorization_approver_id,
    )
    source_roles = {
        evidence.validation_operator_id,
        evidence.evidence_reviewer_id,
        evidence.approver_id,
        evidence.registry_administrator_id,
        evidence.boundary_reviewer_id,
    }
    return all(
        (
            len(set(request_roles)) == len(request_roles),
            record.persisted_by != request.authorization_approver_id,
            record.persisted_by not in source_roles,
            request.activation_requester_id not in source_roles,
            request.activation_reviewer_id not in source_roles,
            request.authorization_approver_id not in source_roles,
        )
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


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


__all__ = [
    "ActivationCommitPlan",
    "ActivationEvaluation",
    "ActivationEvaluationResult",
    "ActivationEvaluationSafeSummary",
    "ActivationReason",
    "ActivationRequest",
    "AuthorizationActivationError",
    "CANONICAL_AUTHORIZATION_ACTIVATION_DIGEST_ALGORITHM",
    "InMemoryActivationReplayStore",
    "evaluate_activation_request",
]
