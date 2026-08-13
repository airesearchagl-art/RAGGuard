from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ragguard.real_world_validation import (
    ExecutionResult,
    RealWorldExecutionReceipt,
    RealWorldValidationAuthorizationRequest,
)


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RECORD_MARKER = object()


class RealWorldEvidenceError(ValueError):
    pass


class EvidenceClass(str, Enum):
    CONTROLLED_SYNTHETIC = "controlled_synthetic"
    CONTROLLED_FIXTURE = "controlled_fixture"


class EvidenceReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class EvidenceApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ValidationRecordState(str, Enum):
    EVIDENCE_APPROVED = "evidence_approved"
    VALIDATION_COMPLETED = "validation_completed"


class ValidationCommitReason(str, Enum):
    INVALID_CHAIN = "invalid_chain"
    EXECUTION_NOT_PASSED = "execution_not_passed"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    REPLAY_DETECTED = "replay_detected"
    GENERATION_MISMATCH = "generation_mismatch"
    PREDECESSOR_MISMATCH = "predecessor_mismatch"
    COMMIT_FAULT = "commit_fault"


class ValidationCommitFault(str, Enum):
    NONE = "none"
    CANDIDATE_STATE = "candidate_state"
    COUNTERS = "counters"
    BEFORE_SWAP = "before_swap"


@dataclass(frozen=True, repr=False)
class ExecutionEvidenceDescriptor:
    descriptor_id: str
    execution_receipt_digest: str
    behavior_digest: str
    coverage_digest: str
    failure_digest: str
    environment_manifest_digest: str
    product_digest: str
    configuration_digest: str
    protocol_digest: str
    evidence_class: EvidenceClass
    created_at: datetime
    created_by: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        digests = tuple(v for k, v in vars(self).items() if k.endswith("_digest"))
        if (not all(_is_identifier(v) for v in (self.descriptor_id, self.created_by))
                or not all(_is_digest(v) for v in digests)
                or not isinstance(self.evidence_class, EvidenceClass) or not _is_aware(self.created_at)):
            raise RealWorldEvidenceError("evidence_descriptor_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({k: (_canonical_datetime(v) if isinstance(v, datetime)
            else v.value if isinstance(v, Enum) else v) for k, v in vars(self).items()
            if k != "canonical_digest"})

    def __repr__(self) -> str:
        return "ExecutionEvidenceDescriptor(<safe>)"


@dataclass(frozen=True, repr=False)
class RealWorldEvidenceReview:
    review_id: str
    evidence_descriptor_digest: str
    reviewed_at: datetime
    reviewer_id: str
    result: EvidenceReviewResult
    findings_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not all(_is_identifier(v) for v in (self.review_id, self.reviewer_id))
                or not all(_is_digest(v) for v in (self.evidence_descriptor_digest, self.findings_digest))
                or not _is_aware(self.reviewed_at) or not isinstance(self.result, EvidenceReviewResult)):
            raise RealWorldEvidenceError("evidence_review_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"evidence_descriptor_digest": self.evidence_descriptor_digest,
            "findings_digest": self.findings_digest, "result": self.result.value,
            "review_id": self.review_id, "reviewed_at": _canonical_datetime(self.reviewed_at),
            "reviewer_id": self.reviewer_id})

    def __repr__(self) -> str:
        return "RealWorldEvidenceReview(<safe>)"


@dataclass(frozen=True, repr=False)
class RealWorldEvidenceApproval:
    approval_id: str
    evidence_descriptor_digest: str
    review_digest: str
    approved_at: datetime
    approver_id: str
    result: EvidenceApprovalResult
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not all(_is_identifier(v) for v in (self.approval_id, self.approver_id))
                or not all(_is_digest(v) for v in (self.evidence_descriptor_digest, self.review_digest))
                or not _is_aware(self.approved_at) or not isinstance(self.result, EvidenceApprovalResult)):
            raise RealWorldEvidenceError("evidence_approval_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"approval_id": self.approval_id, "approved_at": _canonical_datetime(self.approved_at),
            "approver_id": self.approver_id, "evidence_descriptor_digest": self.evidence_descriptor_digest,
            "result": self.result.value, "review_digest": self.review_digest})

    def __repr__(self) -> str:
        return "RealWorldEvidenceApproval(<safe>)"


@dataclass(frozen=True, repr=False)
class RealWorldValidationRecord:
    record_id: str
    authorization_request_digest: str
    execution_receipt_digest: str
    evidence_descriptor_digest: str
    review_digest: str
    approval_digest: str
    manual_validation_approval_digest: str
    equivalence_approval_digest: str
    runtime_authorization_record_digest: str
    persistence_receipt_digest: str
    environment_manifest_digest: str
    product_digest: str
    configuration_digest: str
    protocol_digest: str
    behavior_digest: str
    coverage_digest: str
    validated_at: datetime
    generation: int
    predecessor_digest: str | None
    state: ValidationRecordState
    _marker: object = field(default=None, repr=False, compare=False)
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        digests = tuple(v for k, v in vars(self).items() if k.endswith("_digest") and v is not None)
        if (self._marker is not _RECORD_MARKER or not _is_identifier(self.record_id)
                or not all(_is_digest(v) for v in digests)
                or type(self.generation) is not int or self.generation < 1
                or not _is_aware(self.validated_at) or not isinstance(self.state, ValidationRecordState)):
            raise RealWorldEvidenceError("validation_record_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({k: (_canonical_datetime(v) if isinstance(v, datetime)
            else v.value if isinstance(v, Enum) else v) for k, v in vars(self).items()
            if k not in {"canonical_digest", "_marker"}})

    def __repr__(self) -> str:
        return "RealWorldValidationRecord(<safe>)"


@dataclass(frozen=True)
class ValidationLedgerResult:
    applied: bool
    reasons: tuple[ValidationCommitReason, ...]
    record: RealWorldValidationRecord | None
    write_count: int
    mutation_count: int
    event_count: int
    filesystem_count: int = field(init=False, default=0)
    database_count: int = field(init=False, default=0)
    external_storage_count: int = field(init=False, default=0)
    registry_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    transport_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    credential_count: int = field(init=False, default=0)
    token_count: int = field(init=False, default=0)


@dataclass(frozen=True)
class _LedgerState:
    records: tuple[RealWorldValidationRecord, ...] = ()
    used_authorization_requests: frozenset[str] = frozenset()
    used_execution_receipts: frozenset[str] = frozenset()
    used_evidence: frozenset[str] = frozenset()
    used_reviews: frozenset[str] = frozenset()
    used_approvals: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class TestRealWorldValidationLedger:
    """Atomic in-memory ledger. A committed record is not runtime authorization."""

    __test__ = False

    def __init__(self) -> None:
        self._state = _LedgerState()

    @property
    def records(self): return self._state.records
    @property
    def write_count(self): return self._state.write_count
    @property
    def mutation_count(self): return self._state.mutation_count
    @property
    def event_count(self): return self._state.event_count
    @property
    def used_digests(self):
        return (self._state.used_authorization_requests, self._state.used_execution_receipts,
                self._state.used_evidence, self._state.used_reviews, self._state.used_approvals)

    def commit(self, *, record_id: str, authorization_request: RealWorldValidationAuthorizationRequest,
               receipt: RealWorldExecutionReceipt, descriptor: ExecutionEvidenceDescriptor,
               review: RealWorldEvidenceReview, approval: RealWorldEvidenceApproval,
               validated_at: datetime, generation: int, predecessor_digest: str | None,
               fault: ValidationCommitFault = ValidationCommitFault.NONE) -> ValidationLedgerResult:
        reasons: list[ValidationCommitReason] = []
        if (receipt.result is not ExecutionResult.PASSED):
            reasons.append(ValidationCommitReason.EXECUTION_NOT_PASSED)
        exact = (descriptor.execution_receipt_digest == receipt.canonical_digest,
                 descriptor.behavior_digest == receipt.behavior_digest,
                 descriptor.coverage_digest == receipt.coverage_digest,
                 descriptor.failure_digest == receipt.failure_digest,
                 descriptor.environment_manifest_digest == receipt.environment_manifest_digest,
                 review.evidence_descriptor_digest == descriptor.canonical_digest,
                 approval.evidence_descriptor_digest == descriptor.canonical_digest,
                 approval.review_digest == review.canonical_digest,
                 receipt.authorization_request_digest == authorization_request.canonical_digest)
        if not all(exact) or review.result is not EvidenceReviewResult.APPROVED or approval.result is not EvidenceApprovalResult.APPROVED:
            reasons.append(ValidationCommitReason.INVALID_CHAIN)
        actors = (authorization_request.requested_by, authorization_request.reviewer_id,
                  authorization_request.approver_id, receipt.operator_id, descriptor.created_by,
                  review.reviewer_id, approval.approver_id)
        if len(set(actors)) != len(actors): reasons.append(ValidationCommitReason.ROLE_CONFLICT)
        if (not _is_aware(validated_at) or not (receipt.completed_at <= descriptor.created_at
                <= review.reviewed_at < approval.approved_at <= validated_at)):
            reasons.append(ValidationCommitReason.TEMPORAL_INVALID)
        expected_generation = len(self._state.records) + 1
        expected_predecessor = self._state.records[-1].canonical_digest if self._state.records else None
        if generation != expected_generation: reasons.append(ValidationCommitReason.GENERATION_MISMATCH)
        if predecessor_digest != expected_predecessor: reasons.append(ValidationCommitReason.PREDECESSOR_MISMATCH)
        used = self.used_digests
        if (authorization_request.canonical_digest in used[0] or receipt.canonical_digest in used[1]
                or descriptor.canonical_digest in used[2] or review.canonical_digest in used[3]
                or approval.canonical_digest in used[4]):
            reasons.append(ValidationCommitReason.REPLAY_DETECTED)
        if reasons:
            return self._result(False, tuple(dict.fromkeys(reasons)), None)
        try:
            if fault is ValidationCommitFault.CANDIDATE_STATE: raise RuntimeError
            record = RealWorldValidationRecord(record_id, authorization_request.canonical_digest,
                receipt.canonical_digest, descriptor.canonical_digest, review.canonical_digest,
                approval.canonical_digest, authorization_request.manual_validation_approval_digest,
                authorization_request.equivalence_approval_digest,
                authorization_request.runtime_authorization_record_digest,
                authorization_request.persistence_receipt_digest,
                descriptor.environment_manifest_digest, descriptor.product_digest,
                descriptor.configuration_digest, descriptor.protocol_digest,
                descriptor.behavior_digest, descriptor.coverage_digest, validated_at, generation,
                predecessor_digest, ValidationRecordState.VALIDATION_COMPLETED, _marker=_RECORD_MARKER)
            if fault is ValidationCommitFault.COUNTERS: raise RuntimeError
            candidate = _LedgerState(self._state.records + (record,),
                self._state.used_authorization_requests | {authorization_request.canonical_digest},
                self._state.used_execution_receipts | {receipt.canonical_digest},
                self._state.used_evidence | {descriptor.canonical_digest},
                self._state.used_reviews | {review.canonical_digest},
                self._state.used_approvals | {approval.canonical_digest},
                self._state.write_count + 1, self._state.mutation_count + 1,
                self._state.event_count + 1)
            if fault is ValidationCommitFault.BEFORE_SWAP: raise RuntimeError
            self._state = candidate
            return self._result(True, (), record)
        except RuntimeError:
            return self._result(False, (ValidationCommitReason.COMMIT_FAULT,), None)

    def _result(self, applied: bool, reasons: tuple[ValidationCommitReason, ...],
                record: RealWorldValidationRecord | None) -> ValidationLedgerResult:
        return ValidationLedgerResult(applied, reasons, record, self.write_count,
                                      self.mutation_count, self.event_count)


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER.fullmatch(value))


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and bool(_DIGEST.fullmatch(value))


def _is_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
