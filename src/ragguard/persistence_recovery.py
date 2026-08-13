from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ragguard.real_persistence import DurableStoreSnapshot, PersistenceCommitReceiptV2


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class PersistenceRecoveryState(str, Enum):
    NO_COMMIT_DETECTED = "no_commit_detected"
    COMMITTED_AND_CONSISTENT = "committed_and_consistent"
    INCOMPLETE_OR_AMBIGUOUS = "incomplete_or_ambiguous"
    CORRUPTION_DETECTED = "corruption_detected"


class PersistenceRecoveryReason(str, Enum):
    DIGEST_MISMATCH = "digest_mismatch"
    GENERATION_INVALID = "generation_invalid"
    PREDECESSOR_INVALID = "predecessor_invalid"
    RECEIPT_MISSING = "receipt_missing"
    SNAPSHOT_MISSING = "snapshot_missing"
    AMBIGUOUS_STATE = "ambiguous_state"
    CORRUPTION = "corruption"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    REPLAY_DETECTED = "replay_detected"


@dataclass(frozen=True, repr=False)
class PersistenceRecoveryRequest:
    recovery_request_id: str
    expected_authorization_record_digest: str
    expected_intent_digest: str
    expected_transaction_plan_digest: str
    expected_receipt_digest: str | None
    expected_store_state_digest: str
    expected_generation: int
    expected_predecessor_digest: str | None
    requested_at: datetime
    recovery_operator_id: str
    recovery_reviewer_id: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not all(_is_identifier(v) for v in (self.recovery_request_id,
                self.recovery_operator_id, self.recovery_reviewer_id))
                or not all(_is_digest(v) for v in (self.expected_authorization_record_digest,
                    self.expected_intent_digest, self.expected_transaction_plan_digest,
                    self.expected_store_state_digest))
                or self.expected_receipt_digest is not None and not _is_digest(self.expected_receipt_digest)
                or self.expected_predecessor_digest is not None and not _is_digest(self.expected_predecessor_digest)
                or type(self.expected_generation) is not int or self.expected_generation < 0
                or not _is_aware(self.requested_at)):
            raise ValueError("persistence_recovery_contract_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _json({"expected_authorization_record_digest": self.expected_authorization_record_digest,
            "expected_generation": self.expected_generation,
            "expected_intent_digest": self.expected_intent_digest,
            "expected_predecessor_digest": self.expected_predecessor_digest,
            "expected_receipt_digest": self.expected_receipt_digest,
            "expected_store_state_digest": self.expected_store_state_digest,
            "expected_transaction_plan_digest": self.expected_transaction_plan_digest,
            "recovery_operator_id": self.recovery_operator_id,
            "recovery_request_id": self.recovery_request_id,
            "recovery_reviewer_id": self.recovery_reviewer_id,
            "requested_at": _dt(self.requested_at)})

    def __repr__(self) -> str:
        return "PersistenceRecoveryRequest(<safe>)"


@dataclass(frozen=True)
class PersistenceRecoveryRecord:
    recovery_request_digest: str
    receipt_digest: str | None
    store_snapshot_digest: str | None
    state: PersistenceRecoveryState
    evaluated_at: datetime
    reviewed_by: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_digest", _digest(_json({
            "evaluated_at": _dt(self.evaluated_at),
            "receipt_digest": self.receipt_digest,
            "recovery_request_digest": self.recovery_request_digest,
            "reviewed_by": self.reviewed_by, "state": self.state.value,
            "store_snapshot_digest": self.store_snapshot_digest})))


@dataclass(frozen=True)
class PersistenceRecoveryDecision:
    state: PersistenceRecoveryState
    reasons: tuple[PersistenceRecoveryReason, ...]
    record: PersistenceRecoveryRecord | None
    evaluated_at: datetime
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    external_storage_count: int = field(init=False, default=0)
    registry_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    credential_use_count: int = field(init=False, default=0)
    token_generation_count: int = field(init=False, default=0)


def evaluate_persistence_recovery(request: PersistenceRecoveryRequest,
        receipt: PersistenceCommitReceiptV2 | None,
        snapshot: DurableStoreSnapshot | None, *, evaluation_time: datetime,
        used_recovery_request_digests: frozenset[str] = frozenset(),
        used_recovery_record_digests: frozenset[str] = frozenset()) -> PersistenceRecoveryDecision:
    if not _is_aware(evaluation_time):
        raise ValueError("persistence_recovery_contract_invalid")
    reasons: set[PersistenceRecoveryReason] = set()
    if request.recovery_operator_id == request.recovery_reviewer_id:
        reasons.add(PersistenceRecoveryReason.ROLE_CONFLICT)
    if request.requested_at > evaluation_time:
        reasons.add(PersistenceRecoveryReason.TEMPORAL_INVALID)
    if request.canonical_digest in used_recovery_request_digests:
        reasons.add(PersistenceRecoveryReason.REPLAY_DETECTED)
    if receipt is None and snapshot is None:
        state = PersistenceRecoveryState.NO_COMMIT_DETECTED
    elif receipt is None or snapshot is None:
        reasons.add(PersistenceRecoveryReason.AMBIGUOUS_STATE)
        state = PersistenceRecoveryState.INCOMPLETE_OR_AMBIGUOUS
    else:
        mismatches = (
            request.expected_receipt_digest != receipt.canonical_digest,
            request.expected_authorization_record_digest != receipt.authorization_record_digest,
            request.expected_intent_digest != receipt.intent_digest,
            request.expected_transaction_plan_digest != receipt.transaction_plan_digest,
            request.expected_store_state_digest != snapshot.state_digest,
            receipt.after_state_digest != snapshot.state_digest,
            snapshot.latest_receipt_digest != receipt.canonical_digest,
        )
        if any(mismatches): reasons.add(PersistenceRecoveryReason.CORRUPTION)
        if request.expected_generation != receipt.generation or snapshot.generation != receipt.generation:
            reasons.add(PersistenceRecoveryReason.GENERATION_INVALID)
        if request.expected_predecessor_digest != receipt.predecessor_digest:
            reasons.add(PersistenceRecoveryReason.PREDECESSOR_INVALID)
        state = (PersistenceRecoveryState.CORRUPTION_DETECTED if reasons else
                 PersistenceRecoveryState.COMMITTED_AND_CONSISTENT)
    record = PersistenceRecoveryRecord(request.canonical_digest,
        receipt.canonical_digest if receipt else None,
        snapshot.canonical_digest if snapshot else None, state, evaluation_time,
        request.recovery_reviewer_id)
    if record.canonical_digest in used_recovery_record_digests:
        reasons.add(PersistenceRecoveryReason.REPLAY_DETECTED)
        state = PersistenceRecoveryState.CORRUPTION_DETECTED
        record = None
    if reasons and state in (PersistenceRecoveryState.NO_COMMIT_DETECTED,
                             PersistenceRecoveryState.COMMITTED_AND_CONSISTENT):
        state = PersistenceRecoveryState.CORRUPTION_DETECTED
        record = None
    return PersistenceRecoveryDecision(state,
        tuple(r for r in PersistenceRecoveryReason if r in reasons), record, evaluation_time)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
