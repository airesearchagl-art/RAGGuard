from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ragguard.production_equivalence import (
    EquivalenceAssessment,
    EquivalenceAssessmentResult,
    EquivalenceCriteria,
    EquivalenceEvidenceDescriptor,
    ProductionEquivalenceAssessmentRequest,
    ProductionEquivalenceError,
)


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class EquivalenceReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class EquivalenceApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class EquivalenceCommitReason(str, Enum):
    INVALID_CHAIN = "invalid_chain"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    REPLAY = "replay"
    COMMIT_FAULT = "commit_fault"


@dataclass(frozen=True, repr=False)
class EquivalenceReview:
    review_id: str
    assessment_digest: str
    evidence_descriptor_digest: str
    criteria_digest: str
    reviewed_at: datetime
    reviewer_id: str
    review_result: EquivalenceReviewResult
    findings_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.review_id) or not _is_identifier(self.reviewer_id) or not all(
            _is_digest(value)
            for value in (
                self.assessment_digest,
                self.evidence_descriptor_digest,
                self.criteria_digest,
                self.findings_digest,
            )
        ) or not _is_aware(self.reviewed_at) or not isinstance(
            self.review_result, EquivalenceReviewResult
        ):
            raise ProductionEquivalenceError("equivalence_review_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "assessment_digest": self.assessment_digest,
                "criteria_digest": self.criteria_digest,
                "evidence_descriptor_digest": self.evidence_descriptor_digest,
                "findings_digest": self.findings_digest,
                "review_id": self.review_id,
                "review_result": self.review_result.value,
                "reviewed_at": _canonical_datetime(self.reviewed_at),
                "reviewer_id": self.reviewer_id,
            }
        )

    def __repr__(self) -> str:
        return "EquivalenceReview(<safe>)"


@dataclass(frozen=True, repr=False)
class EquivalenceApproval:
    approval_id: str
    assessment_digest: str
    review_digest: str
    approved_at: datetime
    approver_id: str
    approval_result: EquivalenceApprovalResult
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.approval_id) or not _is_identifier(self.approver_id) or not all(
            _is_digest(value) for value in (self.assessment_digest, self.review_digest)
        ) or not _is_aware(self.approved_at) or not isinstance(
            self.approval_result, EquivalenceApprovalResult
        ):
            raise ProductionEquivalenceError("equivalence_approval_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "approval_id": self.approval_id,
                "approval_result": self.approval_result.value,
                "approved_at": _canonical_datetime(self.approved_at),
                "approver_id": self.approver_id,
                "assessment_digest": self.assessment_digest,
                "review_digest": self.review_digest,
            }
        )

    def __repr__(self) -> str:
        return "EquivalenceApproval(<safe>)"


@dataclass(frozen=True)
class EquivalenceAttestationChain:
    request: ProductionEquivalenceAssessmentRequest
    criteria: EquivalenceCriteria
    descriptor: EquivalenceEvidenceDescriptor
    assessment: EquivalenceAssessment
    review: EquivalenceReview
    approval: EquivalenceApproval

    def validate(
        self,
        *,
        evaluation_time: datetime,
        manual_validation_approver_id: str,
        protected_actor_ids: tuple[str, ...] = (),
    ) -> None:
        if not _is_aware(evaluation_time) or not _is_identifier(
            manual_validation_approver_id
        ) or not isinstance(protected_actor_ids, tuple) or not all(
            _is_identifier(value) for value in protected_actor_ids
        ):
            raise ProductionEquivalenceError("equivalence_attestation_input_invalid")
        if any(
            (
                _digest(self.request.canonical_json()) != self.request.canonical_digest,
                _digest(self.criteria.canonical_json()) != self.criteria.canonical_digest,
                _digest(self.descriptor.canonical_json()) != self.descriptor.canonical_digest,
                _digest(self.assessment.canonical_json()) != self.assessment.canonical_digest,
                _digest(self.review.canonical_json()) != self.review.canonical_digest,
                _digest(self.approval.canonical_json()) != self.approval.canonical_digest,
                self.assessment.request_digest != self.request.canonical_digest,
                self.assessment.criteria_digest != self.criteria.canonical_digest,
                self.assessment.evidence_descriptor_digest != self.descriptor.canonical_digest,
                self.review.assessment_digest != self.assessment.canonical_digest,
                self.review.criteria_digest != self.criteria.canonical_digest,
                self.review.evidence_descriptor_digest != self.descriptor.canonical_digest,
                self.approval.assessment_digest != self.assessment.canonical_digest,
                self.approval.review_digest != self.review.canonical_digest,
                self.assessment.independent_reviewer_id != self.review.reviewer_id,
                self.request.manual_validation_approver_id
                != manual_validation_approver_id,
            )
        ):
            raise ProductionEquivalenceError("equivalence_attestation_digest_mismatch")
        actors = (
            self.request.validation_operator_id,
            self.request.validation_reviewer_id,
            self.request.manual_validation_approver_id,
            self.request.assessor_id,
            self.review.reviewer_id,
            self.approval.approver_id,
            *protected_actor_ids,
        )
        if len(set(actors)) != len(actors):
            raise ProductionEquivalenceError("equivalence_attestation_role_conflict")
        if not (
            self.request.requested_at
            <= self.assessment.evaluated_at
            <= self.review.reviewed_at
            < self.approval.approved_at
            <= evaluation_time
        ):
            raise ProductionEquivalenceError("equivalence_attestation_temporal_invalid")
        if (
            self.assessment.result
            is not EquivalenceAssessmentResult.ELIGIBLE_FOR_EQUIVALENCE_REVIEW
        ):
            raise ProductionEquivalenceError("equivalence_attestation_assessment_ineligible")
        if (
            self.approval.approval_result is EquivalenceApprovalResult.APPROVED
            and self.review.review_result is not EquivalenceReviewResult.APPROVED
        ):
            raise ProductionEquivalenceError("equivalence_attestation_review_not_approved")

    @property
    def approved(self) -> bool:
        return (
            self.assessment.result is EquivalenceAssessmentResult.ELIGIBLE_FOR_EQUIVALENCE_REVIEW
            and self.review.review_result is EquivalenceReviewResult.APPROVED
            and self.approval.approval_result is EquivalenceApprovalResult.APPROVED
        )


@dataclass(frozen=True)
class EquivalenceCommitResult:
    applied: bool
    reason_categories: tuple[EquivalenceCommitReason, ...]
    assessment_digest: str | None
    review_digest: str | None
    approval_digest: str | None
    write_count: int = 0
    mutation_count: int = 0
    persistence_count: int = 0
    filesystem_count: int = 0
    database_count: int = 0
    transport_count: int = 0
    http_count: int = 0
    activation_count: int = 0


@dataclass(frozen=True)
class EquivalenceReplaySnapshot:
    used_request_ids: frozenset[str]
    used_assessment_digests: frozenset[str]
    used_descriptor_digests: frozenset[str]
    used_review_ids: frozenset[str]
    used_review_digests: frozenset[str]
    used_approval_ids: frozenset[str]
    used_approval_digests: frozenset[str]
    used_manual_validation_approval_digests: frozenset[str]
    committed_chain_count: int


@dataclass(frozen=True)
class _AttestationState:
    snapshot: EquivalenceReplaySnapshot


class TestEquivalenceAttestationStore:
    __test__ = False

    def __init__(self) -> None:
        self._state = _AttestationState(snapshot=_empty_snapshot())

    @property
    def snapshot(self) -> EquivalenceReplaySnapshot:
        return self._state.snapshot

    def commit(
        self,
        chain: EquivalenceAttestationChain,
        *,
        evaluation_time: datetime,
        manual_validation_approver_id: str,
        protected_actor_ids: tuple[str, ...] = (),
        fail_commit: bool = False,
    ) -> EquivalenceCommitResult:
        if not isinstance(chain, EquivalenceAttestationChain) or type(fail_commit) is not bool:
            raise ProductionEquivalenceError("equivalence_attestation_input_invalid")
        try:
            chain.validate(
                evaluation_time=evaluation_time,
                manual_validation_approver_id=manual_validation_approver_id,
                protected_actor_ids=protected_actor_ids,
            )
        except ProductionEquivalenceError as exc:
            category = (
                EquivalenceCommitReason.ROLE_CONFLICT
                if "role_conflict" in exc.category
                else EquivalenceCommitReason.TEMPORAL_INVALID
                if "temporal" in exc.category
                else EquivalenceCommitReason.INVALID_CHAIN
            )
            return _result(False, (category,), chain)
        current = self._state.snapshot
        if any(
            (
                chain.request.assessment_request_id in current.used_request_ids,
                chain.assessment.canonical_digest in current.used_assessment_digests,
                chain.descriptor.canonical_digest in current.used_descriptor_digests,
                chain.review.review_id in current.used_review_ids,
                chain.review.canonical_digest in current.used_review_digests,
                chain.approval.approval_id in current.used_approval_ids,
                chain.approval.canonical_digest in current.used_approval_digests,
                chain.request.manual_validation_approval_digest
                in current.used_manual_validation_approval_digests,
            )
        ):
            return _result(False, (EquivalenceCommitReason.REPLAY,), chain)
        if fail_commit:
            return _result(False, (EquivalenceCommitReason.COMMIT_FAULT,), chain)
        candidate = EquivalenceReplaySnapshot(
            used_request_ids=current.used_request_ids | {chain.request.assessment_request_id},
            used_assessment_digests=current.used_assessment_digests
            | {chain.assessment.canonical_digest},
            used_descriptor_digests=current.used_descriptor_digests
            | {chain.descriptor.canonical_digest},
            used_review_ids=current.used_review_ids | {chain.review.review_id},
            used_review_digests=current.used_review_digests | {chain.review.canonical_digest},
            used_approval_ids=current.used_approval_ids | {chain.approval.approval_id},
            used_approval_digests=current.used_approval_digests | {chain.approval.canonical_digest},
            used_manual_validation_approval_digests=(
                current.used_manual_validation_approval_digests
                | {chain.request.manual_validation_approval_digest}
            ),
            committed_chain_count=current.committed_chain_count + 1,
        )
        self._state = _AttestationState(snapshot=candidate)
        return _result(True, (), chain)


def _result(
    applied: bool,
    reasons: tuple[EquivalenceCommitReason, ...],
    chain: EquivalenceAttestationChain,
) -> EquivalenceCommitResult:
    return EquivalenceCommitResult(
        applied=applied,
        reason_categories=reasons,
        assessment_digest=chain.assessment.canonical_digest if applied else None,
        review_digest=chain.review.canonical_digest if applied else None,
        approval_digest=chain.approval.canonical_digest if applied else None,
    )


def _empty_snapshot() -> EquivalenceReplaySnapshot:
    return EquivalenceReplaySnapshot(
        used_request_ids=frozenset(),
        used_assessment_digests=frozenset(),
        used_descriptor_digests=frozenset(),
        used_review_ids=frozenset(),
        used_review_digests=frozenset(),
        used_approval_ids=frozenset(),
        used_approval_digests=frozenset(),
        used_manual_validation_approval_digests=frozenset(),
        committed_chain_count=0,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


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
