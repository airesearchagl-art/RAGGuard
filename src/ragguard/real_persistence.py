from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from ragguard.activation_commit import RuntimeAuthorizationCommitRecord
from ragguard.production_persistence import PersistencePolicy


CANONICAL_REAL_PERSISTENCE_DIGEST_ALGORITHM = "sha256"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RECEIPT_MARKER = object()


class TargetStoreClass(str, Enum):
    DURABLE_APPEND_ONLY = "durable_append_only"


class PersistenceAuthorizationResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class DurablePersistenceState(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_PERSISTENCE_AUTHORIZATION = "needs_persistence_authorization"
    NEEDS_TRANSACTION_PLAN = "needs_transaction_plan"
    READY_FOR_DURABLE_COMMIT = "ready_for_durable_commit"


class DurablePersistenceReason(str, Enum):
    SOURCE_INELIGIBLE = "source_ineligible"
    DIGEST_MISMATCH = "digest_mismatch"
    AUTHORIZATION_REQUIRED = "persistence_authorization_required"
    TRANSACTION_PLAN_REQUIRED = "transaction_plan_required"
    GENERATION_MISMATCH = "generation_mismatch"
    PREDECESSOR_MISMATCH = "predecessor_mismatch"
    STORE_STATE_MISMATCH = "store_state_mismatch"
    LIFECYCLE_INVALID = "lifecycle_invalid"
    REVALIDATION_PENDING = "revalidation_pending"
    TRANSITION_PENDING = "lifecycle_transition_pending"
    STALE_AUTHORIZATION = "stale_authorization"
    TEMPORAL_INVALID = "temporal_invalid"
    ROLE_CONFLICT = "role_conflict"
    REPLAY_DETECTED = "replay_detected"
    COMMIT_FAILED = "commit_failed"
    CORRUPTION_DETECTED = "corruption_detected"


class DurableCommitFault(str, Enum):
    NONE = "none"
    CANDIDATE_STATE = "candidate_state"
    RECEIPT = "receipt"
    COUNTERS = "counters"
    BEFORE_SWAP = "before_swap"


class RealPersistenceError(ValueError):
    def __init__(self) -> None:
        super().__init__("real_persistence_contract_invalid")


@dataclass(frozen=True)
class PersistenceAuthorizationSafeSummary:
    request_id: str
    runtime_authorization_record_digest: str
    expected_generation: int
    requested_at: str
    canonical_digest: str


@dataclass(frozen=True)
class PersistenceIntentSafeSummary:
    intent_id: str
    authorization_request_digest: str
    target_store_class: str
    expected_generation: int
    created_at: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class PersistenceAuthorizationRequest:
    persistence_authorization_request_id: str
    runtime_authorization_record_digest: str
    runtime_authorization_request_digest: str
    runtime_review_digest: str
    runtime_approval_digest: str
    source_candidate_digest: str
    equivalence_approval_digest: str
    persistence_policy_digest: str
    expected_store_state_digest: str
    expected_generation: int
    expected_previous_record_digest: str | None
    profile_id: str
    profile_version: str
    product_id: str
    product_version: str
    protocol_version: str
    requested_at: datetime
    requested_by: str
    persistence_reviewer_id: str
    persistence_approver_id: str
    persistence_operator_id: str
    runtime_authorization_approver_id: str
    use_current_alias: bool = False
    use_latest_alias: bool = False
    allow_fallback: bool = False
    infer_generation: bool = False
    canonical_digest: str = field(init=False)
    safe_summary: PersistenceAuthorizationSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        values = (self.persistence_authorization_request_id, self.profile_id,
                  self.profile_version, self.product_id, self.product_version,
                  self.protocol_version, self.requested_by, self.persistence_reviewer_id,
                  self.persistence_approver_id, self.persistence_operator_id,
                  self.runtime_authorization_approver_id)
        digests = (self.runtime_authorization_record_digest,
                   self.runtime_authorization_request_digest, self.runtime_review_digest,
                   self.runtime_approval_digest, self.source_candidate_digest,
                   self.equivalence_approval_digest, self.persistence_policy_digest,
                   self.expected_store_state_digest)
        if (not all(_is_identifier(v) for v in values)
                or not all(_is_digest(v) for v in digests)
                or self.expected_previous_record_digest is not None
                and not _is_digest(self.expected_previous_record_digest)
                or type(self.expected_generation) is not int or self.expected_generation < 1
                or not _is_aware(self.requested_at)
                or not all(type(v) is bool for v in (self.use_current_alias,
                    self.use_latest_alias, self.allow_fallback, self.infer_generation))):
            raise RealPersistenceError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))
        object.__setattr__(self, "safe_summary", PersistenceAuthorizationSafeSummary(
            self.persistence_authorization_request_id,
            self.runtime_authorization_record_digest, self.expected_generation,
            _canonical_datetime(self.requested_at), self.canonical_digest))

    def canonical_json(self) -> str:
        return _canonical_json({
            "allow_fallback": self.allow_fallback,
            "equivalence_approval_digest": self.equivalence_approval_digest,
            "expected_generation": self.expected_generation,
            "expected_previous_record_digest": self.expected_previous_record_digest,
            "expected_store_state_digest": self.expected_store_state_digest,
            "infer_generation": self.infer_generation,
            "persistence_approver_id": self.persistence_approver_id,
            "persistence_authorization_request_id": self.persistence_authorization_request_id,
            "persistence_operator_id": self.persistence_operator_id,
            "persistence_policy_digest": self.persistence_policy_digest,
            "persistence_reviewer_id": self.persistence_reviewer_id,
            "product_id": self.product_id, "product_version": self.product_version,
            "profile_id": self.profile_id, "profile_version": self.profile_version,
            "protocol_version": self.protocol_version,
            "requested_at": _canonical_datetime(self.requested_at),
            "requested_by": self.requested_by,
            "runtime_approval_digest": self.runtime_approval_digest,
            "runtime_authorization_approver_id": self.runtime_authorization_approver_id,
            "runtime_authorization_record_digest": self.runtime_authorization_record_digest,
            "runtime_authorization_request_digest": self.runtime_authorization_request_digest,
            "runtime_review_digest": self.runtime_review_digest,
            "source_candidate_digest": self.source_candidate_digest,
            "use_current_alias": self.use_current_alias,
            "use_latest_alias": self.use_latest_alias,
        })

    def __repr__(self) -> str:
        return "PersistenceAuthorizationRequest(<safe>)"


@dataclass(frozen=True, repr=False)
class PersistenceAuthorizationReview:
    review_id: str
    authorization_request_digest: str
    reviewed_at: datetime
    reviewer_id: str
    approved: bool
    findings_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not all(_is_identifier(v) for v in (self.review_id, self.reviewer_id))
                or not all(_is_digest(v) for v in (self.authorization_request_digest,
                                                    self.findings_digest))
                or not _is_aware(self.reviewed_at) or type(self.approved) is not bool):
            raise RealPersistenceError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"approved": self.approved,
            "authorization_request_digest": self.authorization_request_digest,
            "findings_digest": self.findings_digest, "review_id": self.review_id,
            "reviewed_at": _canonical_datetime(self.reviewed_at),
            "reviewer_id": self.reviewer_id})


@dataclass(frozen=True, repr=False)
class PersistenceAuthorizationApproval:
    approval_id: str
    authorization_request_digest: str
    review_digest: str
    approved_at: datetime
    approver_id: str
    result: PersistenceAuthorizationResult
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not all(_is_identifier(v) for v in (self.approval_id, self.approver_id))
                or not all(_is_digest(v) for v in (self.authorization_request_digest,
                                                    self.review_digest))
                or not _is_aware(self.approved_at)
                or not isinstance(self.result, PersistenceAuthorizationResult)):
            raise RealPersistenceError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"approval_id": self.approval_id,
            "approver_id": self.approver_id,
            "authorization_request_digest": self.authorization_request_digest,
            "approved_at": _canonical_datetime(self.approved_at),
            "result": self.result.value, "review_digest": self.review_digest})


@dataclass(frozen=True, repr=False)
class PersistenceIntent:
    persistence_intent_id: str
    authorization_request_digest: str
    runtime_authorization_record_digest: str
    target_store_class: TargetStoreClass
    expected_store_state_digest: str
    expected_generation: int
    previous_record_digest: str | None
    content_digest: str
    transaction_digest: str
    created_at: datetime
    created_by: str
    canonical_digest: str = field(init=False)
    safe_summary: PersistenceIntentSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        digests = (self.authorization_request_digest,
                   self.runtime_authorization_record_digest,
                   self.expected_store_state_digest, self.content_digest,
                   self.transaction_digest)
        if (not all(_is_identifier(v) for v in (self.persistence_intent_id, self.created_by))
                or not all(_is_digest(v) for v in digests)
                or self.previous_record_digest is not None and not _is_digest(self.previous_record_digest)
                or not isinstance(self.target_store_class, TargetStoreClass)
                or type(self.expected_generation) is not int or self.expected_generation < 1
                or not _is_aware(self.created_at)):
            raise RealPersistenceError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))
        object.__setattr__(self, "safe_summary", PersistenceIntentSafeSummary(
            self.persistence_intent_id, self.authorization_request_digest,
            self.target_store_class.value, self.expected_generation,
            _canonical_datetime(self.created_at), self.canonical_digest))

    def canonical_json(self) -> str:
        return _canonical_json({"authorization_request_digest": self.authorization_request_digest,
            "content_digest": self.content_digest, "created_at": _canonical_datetime(self.created_at),
            "created_by": self.created_by, "expected_generation": self.expected_generation,
            "expected_store_state_digest": self.expected_store_state_digest,
            "persistence_intent_id": self.persistence_intent_id,
            "previous_record_digest": self.previous_record_digest,
            "runtime_authorization_record_digest": self.runtime_authorization_record_digest,
            "target_store_class": self.target_store_class.value,
            "transaction_digest": self.transaction_digest})

    def __repr__(self) -> str:
        return "PersistenceIntent(<safe>)"


@dataclass(frozen=True, repr=False)
class PersistenceTransactionPlan:
    intent_digest: str
    expected_before_state_digest: str
    expected_after_state_digest: str
    generation: int
    predecessor_digest: str | None
    payload_digest: str
    commit_protocol_version: str
    recovery_protocol_version: str
    planned_at: datetime
    planned_by: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not all(_is_digest(v) for v in (self.intent_digest,
                self.expected_before_state_digest, self.expected_after_state_digest,
                self.payload_digest))
                or self.predecessor_digest is not None and not _is_digest(self.predecessor_digest)
                or not all(_is_identifier(v) for v in (self.commit_protocol_version,
                    self.recovery_protocol_version, self.planned_by))
                or type(self.generation) is not int or self.generation < 1
                or not _is_aware(self.planned_at)):
            raise RealPersistenceError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"commit_protocol_version": self.commit_protocol_version,
            "expected_after_state_digest": self.expected_after_state_digest,
            "expected_before_state_digest": self.expected_before_state_digest,
            "generation": self.generation, "intent_digest": self.intent_digest,
            "payload_digest": self.payload_digest, "planned_at": _canonical_datetime(self.planned_at),
            "planned_by": self.planned_by, "predecessor_digest": self.predecessor_digest,
            "recovery_protocol_version": self.recovery_protocol_version})


@dataclass(frozen=True)
class DurablePersistenceDecision:
    state: DurablePersistenceState
    reasons: tuple[DurablePersistenceReason, ...]
    authorization_request_digest: str
    intent_digest: str | None
    transaction_plan_digest: str | None
    runtime_authorization_record_digest: str
    evaluated_at: datetime
    canonical_digest: str = field(init=False)
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    external_storage_count: int = field(init=False, default=0)
    registry_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    credential_use_count: int = field(init=False, default=0)
    token_generation_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_digest", _digest(_canonical_json({
            "authorization_request_digest": self.authorization_request_digest,
            "evaluated_at": _canonical_datetime(self.evaluated_at),
            "intent_digest": self.intent_digest, "reasons": [v.value for v in self.reasons],
            "runtime_authorization_record_digest": self.runtime_authorization_record_digest,
            "state": self.state.value, "transaction_plan_digest": self.transaction_plan_digest})))


@dataclass(frozen=True, repr=False)
class PersistenceCommitReceiptV2:
    receipt_id: str
    intent_digest: str
    transaction_plan_digest: str
    authorization_record_digest: str
    committed_content_digest: str
    before_state_digest: str
    after_state_digest: str
    generation: int
    predecessor_digest: str | None
    committed_at: datetime
    committed_by: str
    commit_result: str
    _marker: object = field(default=None, repr=False, compare=False)
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (self._marker is not _RECEIPT_MARKER or self.commit_result != "committed"
                or not all(_is_identifier(v) for v in (self.receipt_id, self.committed_by))
                or not all(_is_digest(v) for v in (self.intent_digest,
                    self.transaction_plan_digest, self.authorization_record_digest,
                    self.committed_content_digest, self.before_state_digest,
                    self.after_state_digest))
                or self.predecessor_digest is not None and not _is_digest(self.predecessor_digest)
                or type(self.generation) is not int or self.generation < 1
                or not _is_aware(self.committed_at)):
            raise RealPersistenceError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"after_state_digest": self.after_state_digest,
            "authorization_record_digest": self.authorization_record_digest,
            "before_state_digest": self.before_state_digest,
            "commit_result": self.commit_result,
            "committed_at": _canonical_datetime(self.committed_at),
            "committed_by": self.committed_by,
            "committed_content_digest": self.committed_content_digest,
            "generation": self.generation, "intent_digest": self.intent_digest,
            "predecessor_digest": self.predecessor_digest, "receipt_id": self.receipt_id,
            "transaction_plan_digest": self.transaction_plan_digest})

    def __repr__(self) -> str:
        return "PersistenceCommitReceiptV2(<safe>)"


@dataclass(frozen=True)
class DurableStoreSnapshot:
    generation: int
    state_digest: str
    latest_content_digest: str | None
    latest_receipt_digest: str | None
    previous_record_digest: str | None
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_digest", _digest(_canonical_json({
            "generation": self.generation, "latest_content_digest": self.latest_content_digest,
            "latest_receipt_digest": self.latest_receipt_digest,
            "previous_record_digest": self.previous_record_digest,
            "state_digest": self.state_digest})))


@dataclass(frozen=True)
class DurableCommitResult:
    applied: bool
    reasons: tuple[DurablePersistenceReason, ...]
    receipt: PersistenceCommitReceiptV2 | None
    snapshot: DurableStoreSnapshot
    write_count: int
    mutation_count: int
    event_count: int
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    external_storage_count: int = field(init=False, default=0)
    registry_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    credential_use_count: int = field(init=False, default=0)
    token_generation_count: int = field(init=False, default=0)


@dataclass(frozen=True)
class _DurableStoreState:
    generation: int
    state_digest: str
    content_digests: tuple[str, ...] = ()
    receipts: tuple[PersistenceCommitReceiptV2, ...] = ()
    used_authorization_requests: frozenset[str] = frozenset()
    used_intents: frozenset[str] = frozenset()
    used_plans: frozenset[str] = frozenset()
    used_receipts: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


EMPTY_DURABLE_STORE_STATE_DIGEST = "sha256:" + hashlib.sha256(
    json.dumps({"generation": 0, "latest_content_digest": None,
                "latest_receipt_digest": None, "previous_record_digest": None},
               sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
).hexdigest()


class TestAtomicDurableStore:
    """In-memory contract simulator. It performs no filesystem, DB, or network I/O."""

    __test__ = False

    def __init__(self) -> None:
        self._state = _DurableStoreState(0, EMPTY_DURABLE_STORE_STATE_DIGEST)

    @property
    def snapshot(self) -> DurableStoreSnapshot:
        latest_receipt = self._state.receipts[-1] if self._state.receipts else None
        return DurableStoreSnapshot(self._state.generation, self._state.state_digest,
            self._state.content_digests[-1] if self._state.content_digests else None,
            latest_receipt.canonical_digest if latest_receipt else None,
            latest_receipt.predecessor_digest if latest_receipt else None)

    @property
    def receipts(self): return self._state.receipts
    @property
    def write_count(self): return self._state.write_count
    @property
    def mutation_count(self): return self._state.mutation_count
    @property
    def event_count(self): return self._state.event_count
    @property
    def used_intents(self): return self._state.used_intents

    def commit(self, *, receipt_id: str, decision: DurablePersistenceDecision,
               request: PersistenceAuthorizationRequest, intent: PersistenceIntent,
               plan: PersistenceTransactionPlan, runtime_record: RuntimeAuthorizationCommitRecord,
               committed_at: datetime, committed_by: str,
               fault: DurableCommitFault = DurableCommitFault.NONE) -> DurableCommitResult:
        reasons: set[DurablePersistenceReason] = set()
        if decision.state is not DurablePersistenceState.READY_FOR_DURABLE_COMMIT:
            reasons.add(DurablePersistenceReason.SOURCE_INELIGIBLE)
        if not all((decision.authorization_request_digest == request.canonical_digest,
                decision.intent_digest == intent.canonical_digest,
                decision.transaction_plan_digest == plan.canonical_digest,
                request.runtime_authorization_record_digest == runtime_record.canonical_digest,
                plan.intent_digest == intent.canonical_digest,
                plan.payload_digest == intent.content_digest)):
            reasons.add(DurablePersistenceReason.DIGEST_MISMATCH)
        if plan.generation != self._state.generation + 1:
            reasons.add(DurablePersistenceReason.GENERATION_MISMATCH)
        predecessor = self._state.receipts[-1].canonical_digest if self._state.receipts else None
        if plan.predecessor_digest != predecessor or intent.previous_record_digest != predecessor:
            reasons.add(DurablePersistenceReason.PREDECESSOR_MISMATCH)
        if plan.expected_before_state_digest != self._state.state_digest:
            reasons.add(DurablePersistenceReason.STORE_STATE_MISMATCH)
        expected_after = canonical_after_state_digest(self._state.state_digest,
            intent.content_digest, plan.generation, predecessor)
        if plan.expected_after_state_digest != expected_after:
            reasons.add(DurablePersistenceReason.CORRUPTION_DETECTED)
        if (request.canonical_digest in self._state.used_authorization_requests
                or intent.canonical_digest in self._state.used_intents
                or plan.canonical_digest in self._state.used_plans):
            reasons.add(DurablePersistenceReason.REPLAY_DETECTED)
        if not _is_aware(committed_at) or plan.planned_at > committed_at:
            reasons.add(DurablePersistenceReason.TEMPORAL_INVALID)
        if reasons:
            return self._result(reasons)
        try:
            if fault is DurableCommitFault.CANDIDATE_STATE: raise RuntimeError("fault")
            receipt = PersistenceCommitReceiptV2(receipt_id, intent.canonical_digest,
                plan.canonical_digest, runtime_record.canonical_digest, intent.content_digest,
                self._state.state_digest, expected_after, plan.generation, predecessor,
                committed_at, committed_by, "committed", _RECEIPT_MARKER)
            if fault is DurableCommitFault.RECEIPT: raise RuntimeError("fault")
            candidate = _DurableStoreState(plan.generation, expected_after,
                (*self._state.content_digests, intent.content_digest),
                (*self._state.receipts, receipt),
                self._state.used_authorization_requests | {request.canonical_digest},
                self._state.used_intents | {intent.canonical_digest},
                self._state.used_plans | {plan.canonical_digest},
                self._state.used_receipts | {receipt.canonical_digest},
                self._state.write_count + 1, self._state.mutation_count + 1,
                self._state.event_count + 1)
            if fault in (DurableCommitFault.COUNTERS, DurableCommitFault.BEFORE_SWAP):
                raise RuntimeError("fault")
            self._state = candidate
        except Exception:
            return self._result({DurablePersistenceReason.COMMIT_FAILED})
        return DurableCommitResult(True, (), receipt, self.snapshot,
            self._state.write_count, self._state.mutation_count, self._state.event_count)

    def _result(self, reasons: set[DurablePersistenceReason]) -> DurableCommitResult:
        return DurableCommitResult(False, tuple(r for r in DurablePersistenceReason if r in reasons),
            None, self.snapshot, self._state.write_count, self._state.mutation_count,
            self._state.event_count)


def evaluate_durable_persistence(request: PersistenceAuthorizationRequest,
        runtime_record: RuntimeAuthorizationCommitRecord, policy: PersistencePolicy,
        intent: PersistenceIntent | None, plan: PersistenceTransactionPlan | None,
        review: PersistenceAuthorizationReview | None,
        approval: PersistenceAuthorizationApproval | None, *, current_store_state_digest: str,
        current_generation: int, current_predecessor_digest: str | None,
        lifecycle_active: bool, pending_revalidation: bool,
        pending_lifecycle_transition: bool, replacement_predecessor: bool,
        revoked_source: bool, evaluation_time: datetime,
        authorization_max_age: timedelta = timedelta(days=90),
        used_request_digests: frozenset[str] = frozenset(),
        used_intent_digests: frozenset[str] = frozenset(),
        used_plan_digests: frozenset[str] = frozenset()) -> DurablePersistenceDecision:
    if not _is_aware(evaluation_time):
        raise RealPersistenceError()
    reasons: set[DurablePersistenceReason] = set()
    aliases = request.use_current_alias or request.use_latest_alias or request.allow_fallback or request.infer_generation
    if aliases or revoked_source or replacement_predecessor:
        reasons.add(DurablePersistenceReason.SOURCE_INELIGIBLE)
    if not lifecycle_active: reasons.add(DurablePersistenceReason.LIFECYCLE_INVALID)
    if pending_revalidation: reasons.add(DurablePersistenceReason.REVALIDATION_PENDING)
    if pending_lifecycle_transition: reasons.add(DurablePersistenceReason.TRANSITION_PENDING)
    if not policy.is_approved or request.persistence_policy_digest != policy.canonical_digest:
        reasons.add(DurablePersistenceReason.DIGEST_MISMATCH)
    if not all((request.runtime_authorization_record_digest == runtime_record.canonical_digest,
            request.runtime_authorization_request_digest == runtime_record.authorization_request_digest,
            request.runtime_review_digest == runtime_record.runtime_review_digest,
            request.runtime_approval_digest == runtime_record.runtime_approval_digest,
            request.runtime_authorization_approver_id == runtime_record.runtime_authorization_approver_id,
            request.source_candidate_digest == runtime_record.source_candidate_digest,
            request.equivalence_approval_digest == runtime_record.equivalence_approval_digest)):
        reasons.add(DurablePersistenceReason.DIGEST_MISMATCH)
    if request.expected_generation != current_generation + 1:
        reasons.add(DurablePersistenceReason.GENERATION_MISMATCH)
    if request.expected_previous_record_digest != current_predecessor_digest:
        reasons.add(DurablePersistenceReason.PREDECESSOR_MISMATCH)
    if request.expected_store_state_digest != current_store_state_digest:
        reasons.add(DurablePersistenceReason.STORE_STATE_MISMATCH)
    if (request.requested_at < runtime_record.committed_at
            or request.requested_at > evaluation_time):
        reasons.add(DurablePersistenceReason.TEMPORAL_INVALID)
    if evaluation_time - runtime_record.committed_at > authorization_max_age:
        reasons.add(DurablePersistenceReason.STALE_AUTHORIZATION)
    roles = (runtime_record.runtime_authorization_approver_id, request.requested_by,
             request.persistence_reviewer_id, request.persistence_approver_id,
             request.persistence_operator_id)
    if len(set(roles)) != len(roles):
        reasons.add(DurablePersistenceReason.ROLE_CONFLICT)
    if request.canonical_digest in used_request_digests:
        reasons.add(DurablePersistenceReason.REPLAY_DETECTED)
    auth_ok = review is not None and approval is not None and all((
        review.authorization_request_digest == request.canonical_digest,
        approval.authorization_request_digest == request.canonical_digest,
        approval.review_digest == review.canonical_digest,
        review.reviewer_id == request.persistence_reviewer_id,
        approval.approver_id == request.persistence_approver_id,
        review.approved, approval.result is PersistenceAuthorizationResult.APPROVED,
        request.requested_at <= review.reviewed_at < approval.approved_at <= evaluation_time))
    if not auth_ok:
        reasons.add(DurablePersistenceReason.AUTHORIZATION_REQUIRED)
    intent_ok = intent is not None and all((intent.authorization_request_digest == request.canonical_digest,
        intent.runtime_authorization_record_digest == runtime_record.canonical_digest,
        intent.expected_store_state_digest == current_store_state_digest,
        intent.expected_generation == request.expected_generation,
        intent.previous_record_digest == current_predecessor_digest,
        intent.created_by == request.persistence_operator_id,
        approval is not None and approval.approved_at <= intent.created_at <= evaluation_time,
        intent.canonical_digest not in used_intent_digests))
    plan_ok = plan is not None and intent is not None and all((plan.intent_digest == intent.canonical_digest,
        plan.expected_before_state_digest == current_store_state_digest,
        plan.expected_after_state_digest == canonical_after_state_digest(current_store_state_digest,
            intent.content_digest, request.expected_generation, current_predecessor_digest),
        plan.generation == request.expected_generation,
        plan.predecessor_digest == current_predecessor_digest,
        plan.payload_digest == intent.content_digest,
        plan.planned_by == request.persistence_operator_id,
        intent.created_at <= plan.planned_at <= evaluation_time,
        plan.canonical_digest not in used_plan_digests))
    if not intent_ok or not plan_ok:
        reasons.add(DurablePersistenceReason.TRANSACTION_PLAN_REQUIRED)
    if any(r not in (DurablePersistenceReason.AUTHORIZATION_REQUIRED,
                     DurablePersistenceReason.TRANSACTION_PLAN_REQUIRED) for r in reasons):
        state = DurablePersistenceState.INELIGIBLE
    elif DurablePersistenceReason.AUTHORIZATION_REQUIRED in reasons:
        state = DurablePersistenceState.NEEDS_PERSISTENCE_AUTHORIZATION
    elif DurablePersistenceReason.TRANSACTION_PLAN_REQUIRED in reasons:
        state = DurablePersistenceState.NEEDS_TRANSACTION_PLAN
    else:
        state = DurablePersistenceState.READY_FOR_DURABLE_COMMIT
    return DurablePersistenceDecision(state,
        tuple(r for r in DurablePersistenceReason if r in reasons), request.canonical_digest,
        intent.canonical_digest if intent else None, plan.canonical_digest if plan else None,
        runtime_record.canonical_digest, evaluation_time)


def canonical_after_state_digest(before: str, content: str, generation: int,
                                 predecessor: str | None) -> str:
    return _digest(_canonical_json({"before_state_digest": before,
        "content_digest": content, "generation": generation,
        "predecessor_digest": predecessor}))


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
