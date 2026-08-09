from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from ragguard.production_authorization import (
    ProductionAuthorizationCandidate,
    ProductionAuthorizationResult,
)
from ragguard.production_boundary import (
    ProductionBoundaryEvidence,
    canonical_registry_state_digest,
)
from ragguard.production_registry import RegistryStatus


CANONICAL_PRODUCTION_PERSISTENCE_DIGEST_ALGORITHM = "sha256"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class DurabilityMode(str, Enum):
    APPEND_ONLY = "append_only"


class PersistenceRollbackPolicy(str, Enum):
    NO_AUTOMATIC_ROLLBACK = "no_automatic_rollback"


class PersistenceRetentionPolicy(str, Enum):
    AUDIT_RETAINED = "audit_retained"


class PersistenceReason(str, Enum):
    INVALID_REQUEST = "invalid_request"
    DIGEST_MISMATCH = "digest_mismatch"
    POLICY_MISMATCH = "persistence_policy_mismatch"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    SOURCE_INELIGIBLE = "source_candidate_ineligible"
    STALE_SOURCE = "stale_source"
    LIFECYCLE_INVALID = "invalid_lifecycle"
    EVIDENCE_EXPIRED = "evidence_expired"
    GENERATION_MISMATCH = "generation_mismatch"
    PREDECESSOR_MISMATCH = "predecessor_record_mismatch"
    DUPLICATE_RECORD_ID = "duplicate_record_id"
    CANDIDATE_REPLAY = "source_candidate_replay"
    COMMIT_FAILED = "persistence_commit_failed"


_REASON_ORDER = tuple(PersistenceReason)


class PersistenceCommitFault(str, Enum):
    NONE = "none"
    CANDIDATE_STATE = "candidate_state"
    RECORD_APPEND = "record_append"
    COUNTERS = "counters"
    BEFORE_SWAP = "before_swap"


class ProductionPersistenceError(ValueError):
    def __init__(self) -> None:
        super().__init__("production_persistence_contract_invalid")


@dataclass(frozen=True, repr=False)
class PersistencePolicy:
    policy_id: str
    policy_version: str
    durability_mode: DurabilityMode
    append_only_required: bool
    tamper_evidence_required: bool
    backup_required: bool
    restore_verification_required: bool
    rollback_policy: PersistenceRollbackPolicy
    retention_policy: PersistenceRetentionPolicy
    secret_separation_required: bool
    operator_separation_required: bool
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_PRODUCTION_PERSISTENCE_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            not _is_identifier(self.policy_id)
            or not _is_identifier(self.policy_version)
            or not isinstance(self.durability_mode, DurabilityMode)
            or not isinstance(self.rollback_policy, PersistenceRollbackPolicy)
            or not isinstance(self.retention_policy, PersistenceRetentionPolicy)
            or not all(
                type(value) is bool
                for value in (
                    self.append_only_required,
                    self.tamper_evidence_required,
                    self.backup_required,
                    self.restore_verification_required,
                    self.secret_separation_required,
                    self.operator_separation_required,
                )
            )
        ):
            raise ProductionPersistenceError()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    @property
    def is_approved(self) -> bool:
        return all(
            (
                self.durability_mode is DurabilityMode.APPEND_ONLY,
                self.append_only_required,
                self.tamper_evidence_required,
                self.backup_required,
                self.restore_verification_required,
                self.rollback_policy
                is PersistenceRollbackPolicy.NO_AUTOMATIC_ROLLBACK,
                self.retention_policy is PersistenceRetentionPolicy.AUDIT_RETAINED,
                self.secret_separation_required,
                self.operator_separation_required,
            )
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "append_only_required": self.append_only_required,
                "backup_required": self.backup_required,
                "durability_mode": self.durability_mode.value,
                "operator_separation_required": self.operator_separation_required,
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "restore_verification_required": self.restore_verification_required,
                "retention_policy": self.retention_policy.value,
                "rollback_policy": self.rollback_policy.value,
                "secret_separation_required": self.secret_separation_required,
                "tamper_evidence_required": self.tamper_evidence_required,
            }
        )

    def __repr__(self) -> str:
        return "PersistencePolicy(<safe>)"


@dataclass(frozen=True)
class PersistedAuthorizationSafeSummary:
    persisted_record_id: str
    source_candidate_digest: str
    source_lifecycle_status: str
    persistence_generation: int
    persisted_at: str
    persisted_by: str
    integrity_digest: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class PersistedAuthorizationRecord:
    persisted_record_id: str
    source_candidate_digest: str
    source_boundary_evidence_digest: str
    source_admission_decision_digest: str
    source_registry_entry_digest: str
    source_registry_state_digest: str
    source_lifecycle_status: RegistryStatus
    source_replacement_digest: str | None
    persistence_policy_digest: str
    persisted_at: datetime
    persisted_by: str
    persistence_generation: int
    previous_record_digest: str | None
    integrity_digest: str = field(init=False)
    safe_summary: PersistedAuthorizationSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_PRODUCTION_PERSISTENCE_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        required_digests = (
            self.source_candidate_digest,
            self.source_boundary_evidence_digest,
            self.source_admission_decision_digest,
            self.source_registry_entry_digest,
            self.source_registry_state_digest,
            self.persistence_policy_digest,
        )
        optional_digests = (self.source_replacement_digest, self.previous_record_digest)
        if (
            not _is_identifier(self.persisted_record_id)
            or not _is_identifier(self.persisted_by)
            or not all(_is_digest(value) for value in required_digests)
            or any(value is not None and not _is_digest(value) for value in optional_digests)
            or not isinstance(self.source_lifecycle_status, RegistryStatus)
            or not _is_aware(self.persisted_at)
            or type(self.persistence_generation) is not int
            or self.persistence_generation < 1
            or (self.persistence_generation == 1) != (self.previous_record_digest is None)
        ):
            raise ProductionPersistenceError()
        integrity = _digest(self.integrity_json())
        object.__setattr__(self, "integrity_digest", integrity)
        canonical = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", canonical)
        object.__setattr__(
            self,
            "safe_summary",
            PersistedAuthorizationSafeSummary(
                persisted_record_id=self.persisted_record_id,
                source_candidate_digest=self.source_candidate_digest,
                source_lifecycle_status=self.source_lifecycle_status.value,
                persistence_generation=self.persistence_generation,
                persisted_at=_canonical_datetime(self.persisted_at),
                persisted_by=self.persisted_by,
                integrity_digest=integrity,
                canonical_digest=canonical,
            ),
        )

    def integrity_json(self) -> str:
        return _canonical_json(
            {
                "persistence_generation": self.persistence_generation,
                "persistence_policy_digest": self.persistence_policy_digest,
                "previous_record_digest": self.previous_record_digest,
                "source_candidate_digest": self.source_candidate_digest,
            }
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "integrity_digest": self.integrity_digest,
                "persisted_at": _canonical_datetime(self.persisted_at),
                "persisted_by": self.persisted_by,
                "persisted_record_id": self.persisted_record_id,
                "persistence_generation": self.persistence_generation,
                "persistence_policy_digest": self.persistence_policy_digest,
                "previous_record_digest": self.previous_record_digest,
                "source_admission_decision_digest": (
                    self.source_admission_decision_digest
                ),
                "source_boundary_evidence_digest": (
                    self.source_boundary_evidence_digest
                ),
                "source_candidate_digest": self.source_candidate_digest,
                "source_lifecycle_status": self.source_lifecycle_status.value,
                "source_registry_entry_digest": self.source_registry_entry_digest,
                "source_registry_state_digest": self.source_registry_state_digest,
                "source_replacement_digest": self.source_replacement_digest,
            }
        )

    def __repr__(self) -> str:
        return "PersistedAuthorizationRecord(<safe>)"


@dataclass(frozen=True, repr=False)
class PersistenceCommitRequest:
    record: PersistedAuthorizationRecord
    source_candidate: ProductionAuthorizationCandidate = field(repr=False)
    source_evidence: ProductionBoundaryEvidence = field(repr=False)
    policy: PersistencePolicy = field(repr=False)
    registry_snapshot_digests: tuple[str, ...]
    evaluation_time: datetime
    use_current_alias: bool = False
    use_latest_alias: bool = False
    allow_fallback: bool = False
    infer_predecessor: bool = False
    infer_successor: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.record, PersistedAuthorizationRecord)
            or not isinstance(self.source_candidate, ProductionAuthorizationCandidate)
            or not isinstance(self.source_evidence, ProductionBoundaryEvidence)
            or not isinstance(self.policy, PersistencePolicy)
            or not _is_aware(self.evaluation_time)
            or not all(
                type(value) is bool
                for value in (
                    self.use_current_alias,
                    self.use_latest_alias,
                    self.allow_fallback,
                    self.infer_predecessor,
                    self.infer_successor,
                )
            )
        ):
            raise ProductionPersistenceError()
        canonical_registry_state_digest(self.registry_snapshot_digests)

    def __repr__(self) -> str:
        return "PersistenceCommitRequest(<safe>)"


@dataclass(frozen=True)
class PersistenceCommitResult:
    persisted_record_id: str
    applied: bool
    reason_categories: tuple[PersistenceReason, ...]
    record_digest: str
    persistence_generation: int
    evaluated_at: datetime
    write_count: int
    mutation_count: int
    transport_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)


@dataclass(frozen=True)
class _PersistenceStoreState:
    records: tuple[PersistedAuthorizationRecord, ...] = ()
    committed_record_ids: frozenset[str] = frozenset()
    used_candidate_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0


class InMemoryPersistenceStore:
    """Test-only atomic persistence semantics; never writes filesystem or DB state."""

    def __init__(self) -> None:
        self._state = _PersistenceStoreState()

    @property
    def records(self) -> tuple[PersistedAuthorizationRecord, ...]:
        return self._state.records

    @property
    def write_count(self) -> int:
        return self._state.write_count

    @property
    def mutation_count(self) -> int:
        return self._state.mutation_count

    @property
    def committed_record_ids(self) -> frozenset[str]:
        return self._state.committed_record_ids

    @property
    def used_candidate_digests(self) -> frozenset[str]:
        return self._state.used_candidate_digests

    def commit(
        self,
        request: PersistenceCommitRequest,
        *,
        fault: PersistenceCommitFault = PersistenceCommitFault.NONE,
    ) -> PersistenceCommitResult:
        if not isinstance(request, PersistenceCommitRequest) or not isinstance(
            fault, PersistenceCommitFault
        ):
            raise ProductionPersistenceError()
        reasons = _validation_reasons(request, self._state)
        if reasons:
            return _commit_result(request, reasons)
        try:
            candidate = self._candidate_state(request, fault)
            if fault is PersistenceCommitFault.BEFORE_SWAP:
                raise RuntimeError("fault")
            self._state = candidate
        except Exception:
            return _commit_result(request, {PersistenceReason.COMMIT_FAILED})
        return _commit_result(request, set(), applied=True)

    def _candidate_state(
        self,
        request: PersistenceCommitRequest,
        fault: PersistenceCommitFault,
    ) -> _PersistenceStoreState:
        if fault is PersistenceCommitFault.CANDIDATE_STATE:
            raise RuntimeError("fault")
        records = (*self._state.records, request.record)
        if fault is PersistenceCommitFault.RECORD_APPEND:
            raise RuntimeError("fault")
        record_ids = self._state.committed_record_ids | {
            request.record.persisted_record_id
        }
        candidate_digests = self._state.used_candidate_digests | {
            request.record.source_candidate_digest
        }
        if fault is PersistenceCommitFault.COUNTERS:
            raise RuntimeError("fault")
        return _PersistenceStoreState(
            records=records,
            committed_record_ids=frozenset(record_ids),
            used_candidate_digests=frozenset(candidate_digests),
            write_count=self._state.write_count + 1,
            mutation_count=self._state.mutation_count + 1,
        )


def create_persisted_authorization_record(
    *,
    persisted_record_id: str,
    source_candidate: ProductionAuthorizationCandidate,
    source_evidence: ProductionBoundaryEvidence,
    policy: PersistencePolicy,
    persisted_at: datetime,
    persisted_by: str,
    persistence_generation: int,
    previous_record_digest: str | None,
) -> PersistedAuthorizationRecord:
    return PersistedAuthorizationRecord(
        persisted_record_id=persisted_record_id,
        source_candidate_digest=source_candidate.canonical_digest,
        source_boundary_evidence_digest=source_evidence.canonical_digest,
        source_admission_decision_digest=source_evidence.admission_decision_digest,
        source_registry_entry_digest=source_candidate.source_entry_digest,
        source_registry_state_digest=source_evidence.registry_state_digest,
        source_lifecycle_status=source_evidence.source_lifecycle_status,
        source_replacement_digest=source_evidence.replacement_decision_digest,
        persistence_policy_digest=policy.canonical_digest,
        persisted_at=persisted_at,
        persisted_by=persisted_by,
        persistence_generation=persistence_generation,
        previous_record_digest=previous_record_digest,
    )


def _validation_reasons(
    request: PersistenceCommitRequest,
    state: _PersistenceStoreState,
) -> set[PersistenceReason]:
    record = request.record
    candidate = request.source_candidate
    evidence = request.source_evidence
    reasons: set[PersistenceReason] = set()
    if not _record_integrity_matches(record) or not _candidate_digest_matches(candidate):
        reasons.add(PersistenceReason.DIGEST_MISMATCH)
    if not _source_binding_matches(request):
        reasons.add(PersistenceReason.DIGEST_MISMATCH)
    if record.persistence_policy_digest != request.policy.canonical_digest:
        reasons.add(PersistenceReason.POLICY_MISMATCH)
    if not request.policy.is_approved:
        reasons.add(PersistenceReason.POLICY_MISMATCH)
    if candidate.result is not ProductionAuthorizationResult.ELIGIBLE_FOR_AUTHORIZATION_REVIEW:
        reasons.add(PersistenceReason.SOURCE_INELIGIBLE)
    if evidence.source_lifecycle_status is not RegistryStatus.ACTIVE:
        reasons.add(PersistenceReason.LIFECYCLE_INVALID)
    if evidence.unresolved_revalidation or evidence.pending_lifecycle_transition:
        reasons.add(PersistenceReason.STALE_SOURCE)
    if request.evaluation_time >= evidence.evidence_expires_at:
        reasons.add(PersistenceReason.EVIDENCE_EXPIRED)
    if not (
        evidence.evaluation_time <= record.persisted_at <= request.evaluation_time
    ):
        reasons.add(PersistenceReason.TEMPORAL_INVALID)
    if request.policy.operator_separation_required and record.persisted_by in _actors(evidence):
        reasons.add(PersistenceReason.ROLE_CONFLICT)
    if any(
        (
            request.use_current_alias,
            request.use_latest_alias,
            request.allow_fallback,
            request.infer_predecessor,
            request.infer_successor,
        )
    ):
        reasons.add(PersistenceReason.INVALID_REQUEST)
    expected_generation = len(state.records) + 1
    if record.persistence_generation != expected_generation:
        reasons.add(PersistenceReason.GENERATION_MISMATCH)
    expected_previous = None if not state.records else state.records[-1].canonical_digest
    if record.previous_record_digest != expected_previous:
        reasons.add(PersistenceReason.PREDECESSOR_MISMATCH)
    if record.persisted_record_id in state.committed_record_ids:
        reasons.add(PersistenceReason.DUPLICATE_RECORD_ID)
    if record.source_candidate_digest in state.used_candidate_digests:
        reasons.add(PersistenceReason.CANDIDATE_REPLAY)
    return reasons


def _source_binding_matches(request: PersistenceCommitRequest) -> bool:
    record = request.record
    candidate = request.source_candidate
    evidence = request.source_evidence
    try:
        registry_state = canonical_registry_state_digest(
            request.registry_snapshot_digests
        )
    except ValueError:
        return False
    return all(
        (
            record.source_candidate_digest == candidate.canonical_digest,
            record.source_boundary_evidence_digest == evidence.canonical_digest,
            candidate.boundary_evidence_digest == evidence.canonical_digest,
            record.source_admission_decision_digest
            == evidence.admission_decision_digest,
            record.source_registry_entry_digest == candidate.source_entry_digest,
            record.source_registry_entry_digest == evidence.registry_entry_digest,
            record.source_registry_entry_digest in request.registry_snapshot_digests,
            record.source_registry_state_digest == evidence.registry_state_digest,
            record.source_registry_state_digest == registry_state,
            record.source_lifecycle_status is evidence.source_lifecycle_status,
            record.source_replacement_digest == evidence.replacement_decision_digest,
        )
    )


def _record_integrity_matches(record: PersistedAuthorizationRecord) -> bool:
    return (
        _digest(record.integrity_json()) == record.integrity_digest
        and _digest(record.canonical_json()) == record.canonical_digest
    )


def _candidate_digest_matches(candidate: ProductionAuthorizationCandidate) -> bool:
    return _digest(candidate.canonical_json()) == candidate.canonical_digest


def _actors(evidence: ProductionBoundaryEvidence) -> tuple[str, ...]:
    return (
        evidence.validation_operator_id,
        evidence.evidence_reviewer_id,
        evidence.approver_id,
        evidence.registry_administrator_id,
        evidence.boundary_reviewer_id,
        evidence.authorization_approver_id,
    )


def _commit_result(
    request: PersistenceCommitRequest,
    reasons: set[PersistenceReason],
    *,
    applied: bool = False,
) -> PersistenceCommitResult:
    return PersistenceCommitResult(
        persisted_record_id=request.record.persisted_record_id,
        applied=applied,
        reason_categories=tuple(reason for reason in _REASON_ORDER if reason in reasons),
        record_digest=request.record.canonical_digest,
        persistence_generation=request.record.persistence_generation,
        evaluated_at=request.evaluation_time,
        write_count=1 if applied else 0,
        mutation_count=1 if applied else 0,
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
    "CANONICAL_PRODUCTION_PERSISTENCE_DIGEST_ALGORITHM",
    "DurabilityMode",
    "InMemoryPersistenceStore",
    "PersistedAuthorizationRecord",
    "PersistedAuthorizationSafeSummary",
    "PersistenceCommitFault",
    "PersistenceCommitRequest",
    "PersistenceCommitResult",
    "PersistencePolicy",
    "PersistenceReason",
    "PersistenceRetentionPolicy",
    "PersistenceRollbackPolicy",
    "ProductionPersistenceError",
    "create_persisted_authorization_record",
]
