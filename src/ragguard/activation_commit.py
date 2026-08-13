from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ragguard.runtime_authorization import (
    RuntimeApprovalResult,
    RuntimeAuthorizationApproval,
    RuntimeAuthorizationDecision,
    RuntimeAuthorizationRequest,
    RuntimeAuthorizationResult,
    RuntimeAuthorizationReview,
)


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RECORD_MARKER = object()


class ActivationAuthorizationState(str, Enum):
    NOT_REQUESTED = "not_requested"
    REVIEW_PENDING = "review_pending"
    AUTHORIZATION_COMMIT_READY = "authorization_commit_ready"
    AUTHORIZATION_COMMITTED = "authorization_committed"


class AuthorizationCommitReason(str, Enum):
    DECISION_INELIGIBLE = "decision_ineligible"
    DIGEST_MISMATCH = "digest_mismatch"
    TEMPORAL_INVALID = "temporal_invalid"
    REPLAY_DETECTED = "replay_detected"
    STALE_GENERATION = "stale_generation"
    PREDECESSOR_MISMATCH = "predecessor_mismatch"
    COMMIT_FAILED = "commit_failed"


class AuthorizationCommitFault(str, Enum):
    NONE = "none"
    CANDIDATE_STATE = "candidate_state"
    COUNTERS = "counters"
    BEFORE_SWAP = "before_swap"


@dataclass(frozen=True, repr=False)
class RuntimeAuthorizationCommitRecord:
    runtime_authorization_record_id: str
    authorization_request_digest: str
    runtime_review_digest: str
    runtime_approval_digest: str
    runtime_authorization_approver_id: str
    source_candidate_digest: str
    equivalence_approval_digest: str
    persistence_receipt_digest: str
    activation_commit_plan_digest: str
    registry_state_digest: str
    committed_at: datetime
    committed_by: str
    authorization_generation: int
    previous_authorization_record_digest: str | None
    _marker: object = field(default=None, repr=False, compare=False)
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        digests = (self.authorization_request_digest, self.runtime_review_digest,
                   self.runtime_approval_digest, self.source_candidate_digest,
                   self.equivalence_approval_digest, self.persistence_receipt_digest,
                   self.activation_commit_plan_digest, self.registry_state_digest)
        if (self._marker is not _RECORD_MARKER or not _is_identifier(self.runtime_authorization_record_id)
                or not _is_identifier(self.runtime_authorization_approver_id)
                or not _is_identifier(self.committed_by) or not all(_is_digest(v) for v in digests)
                or self.previous_authorization_record_digest is not None and not _is_digest(self.previous_authorization_record_digest)
                or type(self.authorization_generation) is not int or self.authorization_generation < 1
                or not _is_aware(self.committed_at)):
            raise ValueError("runtime_authorization_commit_record_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({
            "activation_commit_plan_digest": self.activation_commit_plan_digest,
            "authorization_generation": self.authorization_generation,
            "authorization_request_digest": self.authorization_request_digest,
            "committed_at": _canonical_datetime(self.committed_at),
            "committed_by": self.committed_by,
            "equivalence_approval_digest": self.equivalence_approval_digest,
            "persistence_receipt_digest": self.persistence_receipt_digest,
            "previous_authorization_record_digest": self.previous_authorization_record_digest,
            "registry_state_digest": self.registry_state_digest,
            "runtime_approval_digest": self.runtime_approval_digest,
            "runtime_authorization_approver_id": self.runtime_authorization_approver_id,
            "runtime_authorization_record_id": self.runtime_authorization_record_id,
            "runtime_review_digest": self.runtime_review_digest,
            "source_candidate_digest": self.source_candidate_digest,
        })

    def __repr__(self) -> str:
        return "RuntimeAuthorizationCommitRecord(<safe>)"


@dataclass(frozen=True)
class AuthorizationCommitResult:
    applied: bool
    reasons: tuple[AuthorizationCommitReason, ...]
    record: RuntimeAuthorizationCommitRecord | None
    authorization_state: ActivationAuthorizationState
    write_count: int
    mutation_count: int
    event_count: int
    persistence_write_count: int = field(init=False, default=0)
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    transport_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    token_count: int = field(init=False, default=0)
    credential_count: int = field(init=False, default=0)


@dataclass(frozen=True)
class _AuthorizationLedgerState:
    records: tuple[RuntimeAuthorizationCommitRecord, ...] = ()
    used_record_ids: frozenset[str] = frozenset()
    used_request_ids: frozenset[str] = frozenset()
    used_review_digests: frozenset[str] = frozenset()
    used_approval_digests: frozenset[str] = frozenset()
    used_candidate_digests: frozenset[str] = frozenset()
    used_equivalence_approval_digests: frozenset[str] = frozenset()
    used_persistence_receipt_digests: frozenset[str] = frozenset()
    used_activation_plan_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class TestRuntimeAuthorizationLedger:
    """Test-only atomic authorization ledger; it cannot activate a runtime."""

    __test__ = False

    def __init__(self) -> None:
        self._state = _AuthorizationLedgerState()

    @property
    def records(self): return self._state.records
    @property
    def write_count(self): return self._state.write_count
    @property
    def mutation_count(self): return self._state.mutation_count
    @property
    def event_count(self): return self._state.event_count
    @property
    def authorization_generation(self): return len(self._state.records)
    @property
    def used_request_ids(self): return self._state.used_request_ids

    def commit(self, *, record_id: str, request: RuntimeAuthorizationRequest,
               decision: RuntimeAuthorizationDecision,
               review: RuntimeAuthorizationReview,
               approval: RuntimeAuthorizationApproval,
               committed_at: datetime, committed_by: str,
               fault: AuthorizationCommitFault = AuthorizationCommitFault.NONE) -> AuthorizationCommitResult:
        reasons: set[AuthorizationCommitReason] = set()
        if decision.result is not RuntimeAuthorizationResult.READY_FOR_RUNTIME_AUTHORIZATION_COMMIT or approval.approval_result is not RuntimeApprovalResult.APPROVED:
            reasons.add(AuthorizationCommitReason.DECISION_INELIGIBLE)
        if not all((decision.authorization_request_digest == request.canonical_digest,
                    review.authorization_request_digest == request.canonical_digest,
                    approval.authorization_request_digest == request.canonical_digest,
                    approval.review_digest == review.canonical_digest,
                    decision.source_candidate_digest == request.production_authorization_candidate_digest,
                    decision.equivalence_approval_digest == request.equivalence_approval_digest,
                    decision.persistence_receipt_digest == request.persistence_receipt_digest,
                    decision.activation_commit_plan_digest == request.activation_commit_plan_digest)):
            reasons.add(AuthorizationCommitReason.DIGEST_MISMATCH)
        if not (_is_aware(committed_at) and approval.approved_at <= committed_at):
            reasons.add(AuthorizationCommitReason.TEMPORAL_INVALID)
        if decision.authorization_generation != len(self._state.records) + 1:
            reasons.add(AuthorizationCommitReason.STALE_GENERATION)
        previous = None if not self._state.records else self._state.records[-1].canonical_digest
        replay = any((request.authorization_request_id in self._state.used_request_ids,
                      record_id in self._state.used_record_ids,
                      review.canonical_digest in self._state.used_review_digests,
                      approval.canonical_digest in self._state.used_approval_digests,
                      decision.source_candidate_digest in self._state.used_candidate_digests,
                      decision.equivalence_approval_digest in self._state.used_equivalence_approval_digests,
                      decision.persistence_receipt_digest in self._state.used_persistence_receipt_digests,
                      decision.activation_commit_plan_digest in self._state.used_activation_plan_digests))
        if replay:
            reasons.add(AuthorizationCommitReason.REPLAY_DETECTED)
        if reasons:
            return self._result(reasons)
        try:
            if fault is AuthorizationCommitFault.CANDIDATE_STATE: raise RuntimeError("fault")
            record = RuntimeAuthorizationCommitRecord(
                runtime_authorization_record_id=record_id,
                authorization_request_digest=request.canonical_digest,
                runtime_review_digest=review.canonical_digest,
                runtime_approval_digest=approval.canonical_digest,
                runtime_authorization_approver_id=approval.approver_id,
                source_candidate_digest=decision.source_candidate_digest,
                equivalence_approval_digest=decision.equivalence_approval_digest,
                persistence_receipt_digest=decision.persistence_receipt_digest,
                activation_commit_plan_digest=decision.activation_commit_plan_digest,
                registry_state_digest=request.expected_registry_state_digest,
                committed_at=committed_at, committed_by=committed_by,
                authorization_generation=decision.authorization_generation,
                previous_authorization_record_digest=previous, _marker=_RECORD_MARKER,
            )
            if fault is AuthorizationCommitFault.COUNTERS: raise RuntimeError("fault")
            candidate = _AuthorizationLedgerState(
                records=(*self._state.records, record),
                used_record_ids=self._state.used_record_ids | {record_id},
                used_request_ids=self._state.used_request_ids | {request.authorization_request_id},
                used_review_digests=self._state.used_review_digests | {review.canonical_digest},
                used_approval_digests=self._state.used_approval_digests | {approval.canonical_digest},
                used_candidate_digests=self._state.used_candidate_digests | {decision.source_candidate_digest},
                used_equivalence_approval_digests=self._state.used_equivalence_approval_digests | {decision.equivalence_approval_digest},
                used_persistence_receipt_digests=self._state.used_persistence_receipt_digests | {decision.persistence_receipt_digest},
                used_activation_plan_digests=self._state.used_activation_plan_digests | {decision.activation_commit_plan_digest},
                write_count=self._state.write_count + 1,
                mutation_count=self._state.mutation_count + 1,
                event_count=self._state.event_count + 1,
            )
            if fault is AuthorizationCommitFault.BEFORE_SWAP: raise RuntimeError("fault")
            self._state = candidate
        except Exception:
            return self._result({AuthorizationCommitReason.COMMIT_FAILED})
        return AuthorizationCommitResult(True, (), record,
            ActivationAuthorizationState.AUTHORIZATION_COMMITTED,
            self._state.write_count, self._state.mutation_count, self._state.event_count)

    def _result(self, reasons):
        order = tuple(r for r in AuthorizationCommitReason if r in reasons)
        return AuthorizationCommitResult(False, order, None,
            ActivationAuthorizationState.AUTHORIZATION_COMMIT_READY,
            self._state.write_count, self._state.mutation_count, self._state.event_count)


def _canonical_json(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
def _digest(value): return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
def _canonical_datetime(value): return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
def _is_identifier(value): return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None
def _is_digest(value): return isinstance(value, str) and _DIGEST.fullmatch(value) is not None
def _is_aware(value): return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
