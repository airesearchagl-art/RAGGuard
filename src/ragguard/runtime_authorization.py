from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from ragguard.authorization_activation import ActivationCommitPlan, ActivationRequest
from ragguard.compatibility import SemanticVersion
from ragguard.equivalence_attestation import (
    EquivalenceApprovalResult,
    EquivalenceAttestationChain,
    EquivalenceReviewResult,
)
from ragguard.production_authorization import (
    ProductionAuthorizationCandidate,
    ProductionAuthorizationResult,
)
from ragguard.production_boundary import ProductionBoundaryEvidence, canonical_registry_state_digest
from ragguard.production_persistence import (
    PersistedAuthorizationRecord,
    PersistenceCommitReceipt,
    PersistencePolicy,
    PersistenceStoreSnapshot,
)
from ragguard.production_registry import RegistryStatus


CANONICAL_RUNTIME_AUTHORIZATION_DIGEST_ALGORITHM = "sha256"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class RuntimeAuthorizationResult(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_EQUIVALENCE_APPROVAL = "needs_equivalence_approval"
    NEEDS_PERSISTENCE_VERIFICATION = "needs_persistence_verification"
    NEEDS_ACTIVATION_COMMIT_PLAN = "needs_activation_commit_plan"
    NEEDS_RUNTIME_AUTHORIZATION_REVIEW = "needs_runtime_authorization_review"
    READY_FOR_RUNTIME_AUTHORIZATION_COMMIT = "ready_for_runtime_authorization_commit"


class RuntimeAuthorizationReason(str, Enum):
    IDENTITY_MISMATCH = "identity_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    UNSAFE_RESOLUTION = "unsafe_resolution"
    LIFECYCLE_INACTIVE = "lifecycle_inactive"
    STALE_SOURCE = "stale_source"
    REPLACED_PREDECESSOR = "replaced_predecessor"
    TEMPORAL_INVALID = "temporal_invalid"
    ROLE_CONFLICT = "role_conflict"
    REPLAY_DETECTED = "replay_detected"
    EQUIVALENCE_APPROVAL_REQUIRED = "equivalence_approval_required"
    PERSISTENCE_VERIFICATION_REQUIRED = "persistence_verification_required"
    ACTIVATION_COMMIT_PLAN_REQUIRED = "activation_commit_plan_required"
    RUNTIME_AUTHORIZATION_REVIEW_REQUIRED = "runtime_authorization_review_required"


_REASON_ORDER = tuple(RuntimeAuthorizationReason)
_HARD_FAILURES = frozenset(_REASON_ORDER[:9])


class RuntimeReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class RuntimeApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RuntimeAuthorizationError(ValueError):
    def __init__(self) -> None:
        super().__init__("runtime_authorization_contract_invalid")


@dataclass(frozen=True, repr=False)
class RuntimeAuthorizationRequest:
    authorization_request_id: str
    production_authorization_candidate_digest: str
    production_boundary_evidence_digest: str
    equivalence_assessment_digest: str
    equivalence_review_digest: str
    equivalence_approval_digest: str
    equivalence_criteria_digest: str
    equivalence_evidence_descriptor_digest: str
    persistence_record_digest: str
    persistence_receipt_digest: str
    persistence_snapshot_digest: str
    activation_request_digest: str
    activation_commit_plan_digest: str
    expected_registry_state_digest: str
    expected_lifecycle_status: RegistryStatus
    profile_id: str
    profile_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    protocol_version: SemanticVersion
    requested_at: datetime
    requested_by: str
    runtime_authorization_reviewer_id: str
    runtime_authorization_approver_id: str
    use_current_alias: bool = False
    use_latest_alias: bool = False
    allow_fallback: bool = False
    infer_source: bool = False
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_RUNTIME_AUTHORIZATION_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        identifiers = (
            self.authorization_request_id, self.profile_id, self.product_id,
            self.requested_by, self.runtime_authorization_reviewer_id,
            self.runtime_authorization_approver_id,
        )
        digests = (
            self.production_authorization_candidate_digest,
            self.production_boundary_evidence_digest,
            self.equivalence_assessment_digest, self.equivalence_review_digest,
            self.equivalence_approval_digest, self.equivalence_criteria_digest,
            self.equivalence_evidence_descriptor_digest, self.persistence_record_digest,
            self.persistence_receipt_digest, self.persistence_snapshot_digest,
            self.activation_request_digest, self.activation_commit_plan_digest,
            self.expected_registry_state_digest,
        )
        if (
            not all(_is_identifier(v) for v in identifiers)
            or not all(_is_digest(v) for v in digests)
            or not all(isinstance(v, SemanticVersion) for v in (
                self.profile_version, self.product_version, self.protocol_version
            ))
            or not isinstance(self.expected_lifecycle_status, RegistryStatus)
            or not _is_aware(self.requested_at)
            or not all(type(v) is bool for v in (
                self.use_current_alias, self.use_latest_alias,
                self.allow_fallback, self.infer_source,
            ))
        ):
            raise RuntimeAuthorizationError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({
            "activation_commit_plan_digest": self.activation_commit_plan_digest,
            "activation_request_digest": self.activation_request_digest,
            "allow_fallback": self.allow_fallback,
            "authorization_request_id": self.authorization_request_id,
            "equivalence_approval_digest": self.equivalence_approval_digest,
            "equivalence_assessment_digest": self.equivalence_assessment_digest,
            "equivalence_criteria_digest": self.equivalence_criteria_digest,
            "equivalence_evidence_descriptor_digest": self.equivalence_evidence_descriptor_digest,
            "equivalence_review_digest": self.equivalence_review_digest,
            "expected_lifecycle_status": self.expected_lifecycle_status.value,
            "expected_registry_state_digest": self.expected_registry_state_digest,
            "infer_source": self.infer_source,
            "persistence_receipt_digest": self.persistence_receipt_digest,
            "persistence_record_digest": self.persistence_record_digest,
            "persistence_snapshot_digest": self.persistence_snapshot_digest,
            "product_id": self.product_id,
            "product_version": str(self.product_version),
            "production_authorization_candidate_digest": self.production_authorization_candidate_digest,
            "production_boundary_evidence_digest": self.production_boundary_evidence_digest,
            "profile_id": self.profile_id,
            "profile_version": str(self.profile_version),
            "protocol_version": str(self.protocol_version),
            "requested_at": _canonical_datetime(self.requested_at),
            "requested_by": self.requested_by,
            "runtime_authorization_approver_id": self.runtime_authorization_approver_id,
            "runtime_authorization_reviewer_id": self.runtime_authorization_reviewer_id,
            "use_current_alias": self.use_current_alias,
            "use_latest_alias": self.use_latest_alias,
        })

    def __repr__(self) -> str:
        return "RuntimeAuthorizationRequest(<safe>)"


@dataclass(frozen=True, repr=False)
class RuntimeAuthorizationReview:
    review_id: str
    authorization_request_digest: str
    reviewed_at: datetime
    reviewer_id: str
    review_result: RuntimeReviewResult
    findings_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not _is_identifier(self.review_id) or not _is_identifier(self.reviewer_id)
                or not _is_digest(self.authorization_request_digest)
                or not _is_digest(self.findings_digest) or not _is_aware(self.reviewed_at)
                or not isinstance(self.review_result, RuntimeReviewResult)):
            raise RuntimeAuthorizationError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({
            "authorization_request_digest": self.authorization_request_digest,
            "findings_digest": self.findings_digest,
            "review_id": self.review_id,
            "review_result": self.review_result.value,
            "reviewed_at": _canonical_datetime(self.reviewed_at),
            "reviewer_id": self.reviewer_id,
        })

    def __repr__(self) -> str:
        return "RuntimeAuthorizationReview(<safe>)"


@dataclass(frozen=True, repr=False)
class RuntimeAuthorizationApproval:
    approval_id: str
    authorization_request_digest: str
    review_digest: str
    approved_at: datetime
    approver_id: str
    approval_result: RuntimeApprovalResult
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not _is_identifier(self.approval_id) or not _is_identifier(self.approver_id)
                or not _is_digest(self.authorization_request_digest)
                or not _is_digest(self.review_digest) or not _is_aware(self.approved_at)
                or not isinstance(self.approval_result, RuntimeApprovalResult)):
            raise RuntimeAuthorizationError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({
            "approval_id": self.approval_id,
            "approval_result": self.approval_result.value,
            "approved_at": _canonical_datetime(self.approved_at),
            "approver_id": self.approver_id,
            "authorization_request_digest": self.authorization_request_digest,
            "review_digest": self.review_digest,
        })

    def __repr__(self) -> str:
        return "RuntimeAuthorizationApproval(<safe>)"


@dataclass(frozen=True)
class RuntimeAuthorizationSafeSummary:
    authorization_request_id: str
    result: str
    reason_categories: tuple[str, ...]
    source_candidate_digest: str
    generation: int
    evaluated_at: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class RuntimeAuthorizationDecision:
    authorization_request_id: str
    result: RuntimeAuthorizationResult
    reason_categories: tuple[RuntimeAuthorizationReason, ...]
    authorization_request_digest: str
    source_candidate_digest: str
    equivalence_approval_digest: str
    persistence_receipt_digest: str
    activation_commit_plan_digest: str
    authorization_generation: int
    evaluated_at: datetime
    write_count: int = field(init=False, default=0)
    mutation_count: int = field(init=False, default=0)
    persistence_write_count: int = field(init=False, default=0)
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    transport_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    token_count: int = field(init=False, default=0)
    credential_count: int = field(init=False, default=0)
    canonical_digest: str = field(init=False)
    safe_summary: RuntimeAuthorizationSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        if (not _is_identifier(self.authorization_request_id)
                or not isinstance(self.result, RuntimeAuthorizationResult)
                or tuple(r for r in _REASON_ORDER if r in self.reason_categories) != self.reason_categories
                or not all(isinstance(r, RuntimeAuthorizationReason) for r in self.reason_categories)
                or not all(_is_digest(v) for v in (
                    self.authorization_request_digest, self.source_candidate_digest,
                    self.equivalence_approval_digest, self.persistence_receipt_digest,
                    self.activation_commit_plan_digest,
                )) or self.authorization_generation < 1 or not _is_aware(self.evaluated_at)):
            raise RuntimeAuthorizationError()
        canonical = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", canonical)
        object.__setattr__(self, "safe_summary", RuntimeAuthorizationSafeSummary(
            authorization_request_id=self.authorization_request_id,
            result=self.result.value,
            reason_categories=tuple(r.value for r in self.reason_categories),
            source_candidate_digest=self.source_candidate_digest,
            generation=self.authorization_generation,
            evaluated_at=_canonical_datetime(self.evaluated_at),
            canonical_digest=canonical,
        ))

    def canonical_json(self) -> str:
        return _canonical_json({
            "activation_commit_plan_digest": self.activation_commit_plan_digest,
            "authorization_generation": self.authorization_generation,
            "authorization_request_digest": self.authorization_request_digest,
            "authorization_request_id": self.authorization_request_id,
            "equivalence_approval_digest": self.equivalence_approval_digest,
            "evaluated_at": _canonical_datetime(self.evaluated_at),
            "persistence_receipt_digest": self.persistence_receipt_digest,
            "reason_categories": [r.value for r in self.reason_categories],
            "result": self.result.value,
            "source_candidate_digest": self.source_candidate_digest,
        })

    def __repr__(self) -> str:
        return "RuntimeAuthorizationDecision(<safe>)"


def evaluate_runtime_authorization(
    request: RuntimeAuthorizationRequest,
    candidate: ProductionAuthorizationCandidate,
    evidence: ProductionBoundaryEvidence,
    equivalence_chain: EquivalenceAttestationChain | None,
    record: PersistedAuthorizationRecord | None,
    receipt: PersistenceCommitReceipt | None,
    snapshot: PersistenceStoreSnapshot | None,
    policy: PersistencePolicy | None,
    activation_request: ActivationRequest | None,
    activation_plan: ActivationCommitPlan | None,
    review: RuntimeAuthorizationReview | None,
    approval: RuntimeAuthorizationApproval | None,
    registry_snapshot_digests: tuple[str, ...],
    evaluation_time: datetime,
    *,
    authorization_generation: int = 1,
    used_request_ids: frozenset[str] = frozenset(),
    used_candidate_digests: frozenset[str] = frozenset(),
    used_equivalence_approval_digests: frozenset[str] = frozenset(),
    used_activation_plan_digests: frozenset[str] = frozenset(),
    used_runtime_approval_digests: frozenset[str] = frozenset(),
) -> RuntimeAuthorizationDecision:
    if (not isinstance(request, RuntimeAuthorizationRequest)
            or not isinstance(candidate, ProductionAuthorizationCandidate)
            or not isinstance(evidence, ProductionBoundaryEvidence)
            or not _is_aware(evaluation_time) or authorization_generation < 1):
        raise RuntimeAuthorizationError()
    reasons: set[RuntimeAuthorizationReason] = set()
    if any((request.use_current_alias, request.use_latest_alias, request.allow_fallback, request.infer_source)):
        reasons.add(RuntimeAuthorizationReason.UNSAFE_RESOLUTION)
    if not _identity_matches(request, evidence):
        reasons.add(RuntimeAuthorizationReason.IDENTITY_MISMATCH)
    if candidate.result is not ProductionAuthorizationResult.ELIGIBLE_FOR_AUTHORIZATION_REVIEW:
        reasons.add(RuntimeAuthorizationReason.DIGEST_MISMATCH)
    if (request.production_authorization_candidate_digest != candidate.canonical_digest
            or request.production_boundary_evidence_digest != evidence.canonical_digest
            or candidate.boundary_evidence_digest != evidence.canonical_digest):
        reasons.add(RuntimeAuthorizationReason.DIGEST_MISMATCH)
    if request.expected_lifecycle_status is not RegistryStatus.ACTIVE or evidence.source_lifecycle_status is not RegistryStatus.ACTIVE:
        reasons.add(RuntimeAuthorizationReason.LIFECYCLE_INACTIVE)
    if evidence.unresolved_revalidation or evidence.pending_lifecycle_transition:
        reasons.add(RuntimeAuthorizationReason.STALE_SOURCE)
    try:
        registry_state = canonical_registry_state_digest(registry_snapshot_digests)
    except ValueError:
        registry_state = ""
    if (request.expected_registry_state_digest != registry_state
            or request.expected_registry_state_digest != evidence.registry_state_digest
            or evidence.registry_entry_digest not in registry_snapshot_digests):
        reasons.add(RuntimeAuthorizationReason.REPLACED_PREDECESSOR)
    if request.requested_at > evaluation_time or evaluation_time >= evidence.evidence_expires_at:
        reasons.add(RuntimeAuthorizationReason.TEMPORAL_INVALID)
    if all(v is not None for v in (record, receipt, activation_request, activation_plan)) and not (
        record.persisted_at
        <= receipt.committed_at
        <= activation_request.activation_requested_at
        <= activation_plan.approved_at
        <= request.requested_at
        <= evaluation_time
    ):
        reasons.add(RuntimeAuthorizationReason.TEMPORAL_INVALID)
    source_actors = {
        evidence.validation_operator_id, evidence.evidence_reviewer_id, evidence.approver_id,
        evidence.registry_administrator_id, evidence.boundary_reviewer_id,
        evidence.authorization_approver_id,
    }
    if equivalence_chain is not None:
        source_actors.update((
            equivalence_chain.request.assessor_id,
            equivalence_chain.review.reviewer_id,
            equivalence_chain.approval.approver_id,
        ))
    if record is not None:
        source_actors.add(record.persisted_by)
    if activation_request is not None:
        source_actors.update((activation_request.activation_requester_id,
                              activation_request.activation_reviewer_id,
                              activation_request.authorization_approver_id))
    runtime_actors = (request.requested_by, request.runtime_authorization_reviewer_id,
                      request.runtime_authorization_approver_id)
    if len(set(runtime_actors)) != 3 or any(v in source_actors for v in runtime_actors):
        reasons.add(RuntimeAuthorizationReason.ROLE_CONFLICT)
    if (request.authorization_request_id in used_request_ids
            or candidate.canonical_digest in used_candidate_digests
            or request.equivalence_approval_digest in used_equivalence_approval_digests
            or request.activation_commit_plan_digest in used_activation_plan_digests
            or approval is not None and approval.canonical_digest in used_runtime_approval_digests):
        reasons.add(RuntimeAuthorizationReason.REPLAY_DETECTED)

    equivalence_ok = _equivalence_matches(request, candidate, evidence, equivalence_chain, evaluation_time)
    persistence_ok = _persistence_matches(request, candidate, record, receipt, snapshot, policy)
    activation_ok = _activation_matches(request, candidate, record, receipt, activation_request, activation_plan)
    review_ok = _review_matches(request, review, approval, activation_plan, evaluation_time)
    if reasons & _HARD_FAILURES:
        result = RuntimeAuthorizationResult.INELIGIBLE
    elif not equivalence_ok:
        reasons.add(RuntimeAuthorizationReason.EQUIVALENCE_APPROVAL_REQUIRED)
        result = RuntimeAuthorizationResult.NEEDS_EQUIVALENCE_APPROVAL
    elif not persistence_ok:
        reasons.add(RuntimeAuthorizationReason.PERSISTENCE_VERIFICATION_REQUIRED)
        result = RuntimeAuthorizationResult.NEEDS_PERSISTENCE_VERIFICATION
    elif not activation_ok:
        reasons.add(RuntimeAuthorizationReason.ACTIVATION_COMMIT_PLAN_REQUIRED)
        result = RuntimeAuthorizationResult.NEEDS_ACTIVATION_COMMIT_PLAN
    elif not review_ok:
        reasons.add(RuntimeAuthorizationReason.RUNTIME_AUTHORIZATION_REVIEW_REQUIRED)
        result = RuntimeAuthorizationResult.NEEDS_RUNTIME_AUTHORIZATION_REVIEW
    else:
        result = RuntimeAuthorizationResult.READY_FOR_RUNTIME_AUTHORIZATION_COMMIT
    ordered = tuple(r for r in _REASON_ORDER if r in reasons)
    return RuntimeAuthorizationDecision(
        authorization_request_id=request.authorization_request_id,
        result=result, reason_categories=ordered,
        authorization_request_digest=request.canonical_digest,
        source_candidate_digest=candidate.canonical_digest,
        equivalence_approval_digest=request.equivalence_approval_digest,
        persistence_receipt_digest=request.persistence_receipt_digest,
        activation_commit_plan_digest=request.activation_commit_plan_digest,
        authorization_generation=authorization_generation,
        evaluated_at=evaluation_time,
    )


def _identity_matches(request: RuntimeAuthorizationRequest, evidence: ProductionBoundaryEvidence) -> bool:
    return all((request.profile_id == evidence.profile_id,
                request.profile_version == evidence.profile_version,
                request.product_id == evidence.product_id,
                request.product_version == evidence.product_version,
                request.protocol_version == evidence.protocol_version))


def _equivalence_matches(request, candidate, evidence, chain, evaluation_time) -> bool:
    if chain is None:
        return False
    try:
        chain.validate(evaluation_time=evaluation_time,
                       manual_validation_approver_id=evidence.approver_id)
    except ValueError:
        return False
    return all((chain.approved,
                chain.review.review_result is EquivalenceReviewResult.APPROVED,
                chain.approval.approval_result is EquivalenceApprovalResult.APPROVED,
                request.equivalence_assessment_digest == chain.assessment.canonical_digest == candidate.equivalence_assessment_digest == evidence.equivalence_assessment_digest,
                request.equivalence_review_digest == chain.review.canonical_digest == candidate.equivalence_review_digest == evidence.equivalence_review_digest,
                request.equivalence_approval_digest == chain.approval.canonical_digest == candidate.equivalence_approval_digest == evidence.equivalence_approval_digest,
                request.equivalence_criteria_digest == chain.criteria.canonical_digest == candidate.equivalence_criteria_digest == evidence.equivalence_criteria_digest,
                request.equivalence_evidence_descriptor_digest == chain.descriptor.canonical_digest == candidate.equivalence_evidence_descriptor_digest == evidence.equivalence_evidence_descriptor_digest))


def _persistence_matches(request, candidate, record, receipt, snapshot, policy) -> bool:
    if any(v is None for v in (record, receipt, snapshot, policy)):
        return False
    return all((policy.is_approved,
                request.persistence_record_digest == record.canonical_digest,
                request.persistence_receipt_digest == receipt.canonical_digest,
                request.persistence_snapshot_digest == snapshot.canonical_digest,
                record.source_candidate_digest == candidate.canonical_digest,
                receipt.persisted_record_digest == record.canonical_digest,
                receipt.source_candidate_digest == candidate.canonical_digest,
                receipt.persistence_policy_digest == policy.canonical_digest,
                receipt.persistence_generation == record.persistence_generation == snapshot.persistence_generation,
                receipt.resulting_store_state_digest == snapshot.state_digest,
                snapshot.latest_record_digest == record.canonical_digest,
                snapshot.latest_receipt_digest == receipt.canonical_digest))


def _activation_matches(request, candidate, record, receipt, activation_request, plan) -> bool:
    if any(v is None for v in (record, receipt, activation_request, plan)):
        return False
    return all((request.activation_request_digest == activation_request.canonical_digest,
                request.activation_commit_plan_digest == plan.canonical_digest,
                plan.activation_request_digest == activation_request.canonical_digest,
                plan.persisted_record_digest == record.canonical_digest,
                plan.persistence_receipt_digest == receipt.canonical_digest,
                plan.source_candidate_digest == candidate.canonical_digest,
                plan.expected_registry_state_digest == request.expected_registry_state_digest,
                plan.expected_generation == record.persistence_generation,
                plan.approver_id == activation_request.authorization_approver_id))


def _review_matches(request, review, approval, plan, evaluation_time) -> bool:
    if any(v is None for v in (review, approval, plan)):
        return False
    return all((review.authorization_request_digest == request.canonical_digest,
                approval.authorization_request_digest == request.canonical_digest,
                approval.review_digest == review.canonical_digest,
                review.reviewer_id == request.runtime_authorization_reviewer_id,
                approval.approver_id == request.runtime_authorization_approver_id,
                review.review_result is RuntimeReviewResult.APPROVED,
                approval.approval_result is RuntimeApprovalResult.APPROVED,
                plan.approved_at <= request.requested_at <= review.reviewed_at < approval.approved_at <= evaluation_time))


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
