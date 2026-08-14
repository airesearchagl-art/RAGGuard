from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum

from ragguard.activation_commit import RuntimeAuthorizationCommitRecord
from ragguard.real_persistence import (
    PersistenceAuthorizationRequest,
    PersistenceCommitReceiptV2,
    PersistenceIntent,
    PersistenceTransactionPlan,
    TargetStoreClass,
)
from ragguard.storage_adapter import (
    AdapterClass,
    AtomicityModel,
    CredentialMode,
    DurabilityModel,
    FilesystemMode,
    IdempotencyModel,
    NetworkMode,
    RecoveryModel,
    StorageAdapterCapability,
    StorageAdapterError,
    StorageAdapterManifest,
    StorageAdapterPolicy,
    StorageAdapterSafeSummary,
    TransactionModel,
    canonical_datetime,
    canonical_json,
    canonical_object_valid,
    digest,
    is_aware,
    is_digest,
    is_identifier,
)


MAX_ADAPTER_EVIDENCE_AGE = timedelta(days=90)
_RECORD_MARKER = object()

__all__ = [
    "MAX_ADAPTER_EVIDENCE_AGE", "AdapterApprovalResult",
    "AdapterConformanceReason", "AdapterConformanceResult", "AdapterConformanceState",
    "AdapterEvidenceClass", "AdapterLifecycleStatus", "AdapterRecordState",
    "AdapterRegistryFault", "AdapterRegistryReason", "AdapterRegistryResult",
    "AdapterReviewResult", "AdapterRoleContext", "ApprovedStorageAdapterRecord",
    "StorageAdapterApproval", "StorageAdapterAttestationEvidence",
    "StorageAdapterReview", "TestApprovedStorageAdapterRegistry",
    "WriteCompatibilityDecision", "WriteCompatibilityReason",
    "WriteCompatibilityState", "evaluate_adapter_conformance",
    "evaluate_write_compatibility",
]


class AdapterEvidenceClass(str, Enum):
    CONTROLLED_CONFORMANCE = "controlled_conformance"
    SYNTHETIC_CONFORMANCE = "synthetic_conformance"


class AdapterConformanceState(str, Enum):
    FAILED = "failed"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    ELIGIBLE_FOR_ADAPTER_REVIEW = "eligible_for_adapter_review"


class AdapterConformanceReason(str, Enum):
    DIGEST_MISMATCH = "digest_mismatch"
    CAPABILITY_MISSING = "capability_missing"
    POLICY_REJECTED = "policy_rejected"
    MODEL_INCOMPATIBLE = "model_incompatible"
    UNSAFE_MODE = "unsafe_mode"
    TEMPORAL_INVALID = "temporal_invalid"
    STALE_EVIDENCE = "stale_evidence"


class AdapterReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class AdapterApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class AdapterRecordState(str, Enum):
    APPROVED_FOR_WRITE_AUTHORIZATION_REVIEW = "approved_for_write_authorization_review"


class AdapterLifecycleStatus(str, Enum):
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class AdapterRegistryReason(str, Enum):
    INVALID_CHAIN = "invalid_chain"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    REPLAY = "replay"
    GENERATION_MISMATCH = "generation_mismatch"
    PREDECESSOR_MISMATCH = "predecessor_mismatch"
    STATUS_INVALID = "status_invalid"
    COMMIT_FAULT = "commit_fault"


class AdapterRegistryFault(str, Enum):
    NONE = "none"
    CANDIDATE_STATE = "candidate_state"
    COUNTERS = "counters"
    BEFORE_SWAP = "before_swap"


class WriteCompatibilityState(str, Enum):
    INCOMPATIBLE = "incompatible"
    NEEDS_ADAPTER_APPROVAL = "needs_adapter_approval"
    READY_FOR_WRITE_AUTHORIZATION_REVIEW = "ready_for_write_authorization_review"


class WriteCompatibilityReason(str, Enum):
    ADAPTER_NOT_APPROVED = "adapter_not_approved"
    DIGEST_MISMATCH = "digest_mismatch"
    MODEL_INCOMPATIBLE = "model_incompatible"
    GENERATION_MISMATCH = "generation_mismatch"
    PREDECESSOR_MISMATCH = "predecessor_mismatch"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    POLICY_INVALID = "policy_invalid"


@dataclass(frozen=True, repr=False)
class StorageAdapterAttestationEvidence:
    evidence_id: str
    adapter_manifest_digest: str
    capability_digest: str
    conformance_suite_digest: str
    atomicity_test_digest: str
    recovery_test_digest: str
    corruption_test_digest: str
    idempotency_test_digest: str
    failure_injection_digest: str
    evidence_class: AdapterEvidenceClass
    generated_at: datetime
    generated_by: str
    canonical_digest: str = field(init=False)
    safe_summary: StorageAdapterSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        digests = tuple(v for k, v in vars(self).items() if k.endswith("_digest"))
        if (
            not all(is_identifier(v) for v in (self.evidence_id, self.generated_by))
            or not all(is_digest(v) for v in digests)
            or not isinstance(self.evidence_class, AdapterEvidenceClass)
            or not is_aware(self.generated_at)
        ):
            raise StorageAdapterError("storage_adapter_evidence_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))
        object.__setattr__(self, "safe_summary", StorageAdapterSafeSummary(
            self.evidence_id, self.canonical_digest, self.evidence_class.value,
            canonical_datetime(self.generated_at)))

    def canonical_json(self) -> str:
        return canonical_json(
            {
                k: canonical_datetime(v) if isinstance(v, datetime) else v.value if isinstance(v, Enum) else v
                for k, v in vars(self).items()
                if k not in {"canonical_digest", "safe_summary"}
            }
        )

    def __repr__(self) -> str:
        return "StorageAdapterAttestationEvidence(<safe>)"


@dataclass(frozen=True)
class AdapterConformanceResult:
    state: AdapterConformanceState
    reasons: tuple[AdapterConformanceReason, ...]
    manifest_digest: str
    capability_digest: str
    evidence_digest: str
    policy_digest: str
    evaluated_at: datetime
    canonical_digest: str = field(init=False)
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    external_storage_write_count: int = field(init=False, default=0)
    registry_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    credential_use_count: int = field(init=False, default=0)
    token_generation_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    runtime_switch_count: int = field(init=False, default=0)
    real_data_access_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "capability_digest": self.capability_digest,
                "evaluated_at": canonical_datetime(self.evaluated_at),
                "evidence_digest": self.evidence_digest,
                "manifest_digest": self.manifest_digest,
                "policy_digest": self.policy_digest,
                "reasons": [v.value for v in self.reasons],
                "state": self.state.value,
            }
        )


def evaluate_adapter_conformance(
    manifest: StorageAdapterManifest,
    capability: StorageAdapterCapability,
    evidence: StorageAdapterAttestationEvidence,
    policy: StorageAdapterPolicy,
    *,
    evaluation_time: datetime,
) -> AdapterConformanceResult:
    if not is_aware(evaluation_time):
        raise StorageAdapterError("storage_adapter_evaluation_time_invalid")
    reasons: list[AdapterConformanceReason] = []
    if (
        not all(canonical_object_valid(v) for v in (manifest, capability, evidence, policy))
        or manifest.capability_digest != capability.canonical_digest
        or evidence.adapter_manifest_digest != manifest.canonical_digest
        or evidence.capability_digest != capability.canonical_digest
        or policy.required_capability_digest != capability.canonical_digest
    ):
        reasons.append(AdapterConformanceReason.DIGEST_MISMATCH)
    if not capability.all_required:
        reasons.append(AdapterConformanceReason.CAPABILITY_MISSING)
    if (
        not policy.is_approved
        or manifest.adapter_class not in policy.allowed_adapter_classes
        or manifest.transaction_model not in policy.allowed_transaction_models
        or manifest.durability_model not in policy.allowed_durability_models
    ):
        reasons.append(AdapterConformanceReason.POLICY_REJECTED)
    if (
        manifest.transaction_model is not TransactionModel.ATOMIC_COMPARE_AND_SWAP
        or manifest.durability_model is not DurabilityModel.DURABLE_APPEND_ONLY
        or manifest.atomicity_model is not AtomicityModel.CANDIDATE_STATE_SINGLE_SWAP
        or manifest.recovery_model is not RecoveryModel.VERIFIED_RECOVERY_PROBE
        or manifest.idempotency_model is not IdempotencyModel.SUCCESSFUL_ONLY_KEY_CONSUMPTION
    ):
        reasons.append(AdapterConformanceReason.MODEL_INCOMPATIBLE)
    if (
        manifest.credential_mode is not CredentialMode.NONE
        or manifest.network_mode is not NetworkMode.DISABLED
        or manifest.filesystem_mode is not FilesystemMode.SIMULATED_ONLY
        or manifest.network_mode not in policy.allowed_network_modes
        or manifest.filesystem_mode not in policy.allowed_filesystem_modes
        or manifest.credential_mode not in policy.allowed_credential_modes
    ):
        reasons.append(AdapterConformanceReason.UNSAFE_MODE)
    if not (
        policy.effective_at <= manifest.created_at <= evidence.generated_at <= evaluation_time < policy.expires_at
    ):
        reasons.append(AdapterConformanceReason.TEMPORAL_INVALID)
    if evaluation_time - evidence.generated_at > MAX_ADAPTER_EVIDENCE_AGE:
        reasons.append(AdapterConformanceReason.STALE_EVIDENCE)
    if reasons:
        hard = set(reasons) - {AdapterConformanceReason.CAPABILITY_MISSING}
        state = AdapterConformanceState.FAILED if hard else AdapterConformanceState.NEEDS_MORE_EVIDENCE
    else:
        state = AdapterConformanceState.ELIGIBLE_FOR_ADAPTER_REVIEW
    return AdapterConformanceResult(
        state,
        tuple(dict.fromkeys(reasons)),
        manifest.canonical_digest,
        capability.canonical_digest,
        evidence.canonical_digest,
        policy.canonical_digest,
        evaluation_time,
    )


@dataclass(frozen=True, repr=False)
class StorageAdapterReview:
    review_id: str
    manifest_digest: str
    evidence_digest: str
    conformance_result_digest: str
    reviewed_at: datetime
    reviewer_id: str
    review_result: AdapterReviewResult
    findings_digest: str
    canonical_digest: str = field(init=False)
    safe_summary: StorageAdapterSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        if (
            not all(is_identifier(v) for v in (self.review_id, self.reviewer_id))
            or not all(
                is_digest(v)
                for v in (
                    self.manifest_digest,
                    self.evidence_digest,
                    self.conformance_result_digest,
                    self.findings_digest,
                )
            )
            or not is_aware(self.reviewed_at)
            or not isinstance(self.review_result, AdapterReviewResult)
        ):
            raise StorageAdapterError("storage_adapter_review_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))
        object.__setattr__(self, "safe_summary", StorageAdapterSafeSummary(
            self.review_id, self.canonical_digest, self.review_result.value,
            canonical_datetime(self.reviewed_at)))

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "conformance_result_digest": self.conformance_result_digest,
                "evidence_digest": self.evidence_digest,
                "findings_digest": self.findings_digest,
                "manifest_digest": self.manifest_digest,
                "review_id": self.review_id,
                "review_result": self.review_result.value,
                "reviewed_at": canonical_datetime(self.reviewed_at),
                "reviewer_id": self.reviewer_id,
            }
        )

    def __repr__(self) -> str:
        return "StorageAdapterReview(<safe>)"


@dataclass(frozen=True, repr=False)
class StorageAdapterApproval:
    approval_id: str
    manifest_digest: str
    evidence_digest: str
    review_digest: str
    approved_at: datetime
    approver_id: str
    approval_result: AdapterApprovalResult
    policy_digest: str
    canonical_digest: str = field(init=False)
    safe_summary: StorageAdapterSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        if (
            not all(is_identifier(v) for v in (self.approval_id, self.approver_id))
            or not all(
                is_digest(v)
                for v in (
                    self.manifest_digest,
                    self.evidence_digest,
                    self.review_digest,
                    self.policy_digest,
                )
            )
            or not is_aware(self.approved_at)
            or not isinstance(self.approval_result, AdapterApprovalResult)
        ):
            raise StorageAdapterError("storage_adapter_approval_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))
        object.__setattr__(self, "safe_summary", StorageAdapterSafeSummary(
            self.approval_id, self.canonical_digest, self.approval_result.value,
            canonical_datetime(self.approved_at)))

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "approval_id": self.approval_id,
                "approval_result": self.approval_result.value,
                "approved_at": canonical_datetime(self.approved_at),
                "approver_id": self.approver_id,
                "evidence_digest": self.evidence_digest,
                "manifest_digest": self.manifest_digest,
                "policy_digest": self.policy_digest,
                "review_digest": self.review_digest,
            }
        )

    def __repr__(self) -> str:
        return "StorageAdapterApproval(<safe>)"


@dataclass(frozen=True, repr=False)
class AdapterRoleContext:
    evidence_producer_id: str
    adapter_reviewer_id: str
    adapter_approver_id: str
    persistence_requester_id: str
    persistence_reviewer_id: str
    persistence_approver_id: str
    persistence_operator_id: str
    runtime_authorization_approver_id: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        values = tuple(v for k, v in vars(self).items() if k.endswith("_id"))
        if not all(is_identifier(v) for v in values) or len(set(values)) != len(values):
            raise StorageAdapterError("storage_adapter_role_conflict")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return canonical_json({k: v for k, v in vars(self).items() if k.endswith("_id")})


@dataclass(frozen=True, repr=False)
class ApprovedStorageAdapterRecord:
    approved_adapter_record_id: str
    manifest_digest: str
    capability_digest: str
    evidence_digest: str
    review_digest: str
    approval_digest: str
    policy_digest: str
    role_context_digest: str
    adapter_approver_id: str
    adapter_generation: int
    predecessor_record_digest: str | None
    recorded_at: datetime
    state: AdapterRecordState
    lifecycle_status: AdapterLifecycleStatus
    _marker: object = field(default=None, repr=False, compare=False)
    canonical_digest: str = field(init=False)
    safe_summary: StorageAdapterSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        digests = tuple(v for k, v in vars(self).items() if k.endswith("_digest") and v is not None)
        if (
            self._marker is not _RECORD_MARKER
            or not all(is_identifier(v) for v in (self.approved_adapter_record_id, self.adapter_approver_id))
            or not all(is_digest(v) for v in digests)
            or type(self.adapter_generation) is not int
            or self.adapter_generation < 1
            or not is_aware(self.recorded_at)
            or not isinstance(self.state, AdapterRecordState)
            or not isinstance(self.lifecycle_status, AdapterLifecycleStatus)
        ):
            raise StorageAdapterError("approved_storage_adapter_record_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))
        object.__setattr__(self, "safe_summary", StorageAdapterSafeSummary(
            self.approved_adapter_record_id, self.canonical_digest,
            self.lifecycle_status.value, canonical_datetime(self.recorded_at)))

    def canonical_json(self) -> str:
        return canonical_json(
            {
                k: canonical_datetime(v) if isinstance(v, datetime) else v.value if isinstance(v, Enum) else v
                for k, v in vars(self).items()
                if k not in {"canonical_digest", "safe_summary", "_marker"}
            }
        )

    def __repr__(self) -> str:
        return "ApprovedStorageAdapterRecord(<safe>)"


@dataclass(frozen=True)
class AdapterRegistryResult:
    applied: bool
    reasons: tuple[AdapterRegistryReason, ...]
    record: ApprovedStorageAdapterRecord | None
    write_count: int
    mutation_count: int
    event_count: int
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    external_storage_write_count: int = field(init=False, default=0)
    production_registry_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    credential_use_count: int = field(init=False, default=0)
    token_generation_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    runtime_switch_count: int = field(init=False, default=0)
    real_data_access_count: int = field(init=False, default=0)


@dataclass(frozen=True)
class _AdapterRegistryState:
    records: tuple[ApprovedStorageAdapterRecord, ...] = ()
    used_manifest_digests: frozenset[str] = frozenset()
    used_evidence_digests: frozenset[str] = frozenset()
    used_review_digests: frozenset[str] = frozenset()
    used_approval_digests: frozenset[str] = frozenset()
    used_record_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class TestApprovedStorageAdapterRegistry:
    """Test-only atomic metadata registry; it exposes no storage adapter execution API."""

    __test__ = False

    def __init__(self) -> None:
        self._state = _AdapterRegistryState()

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
        return (
            self._state.used_manifest_digests,
            self._state.used_evidence_digests,
            self._state.used_review_digests,
            self._state.used_approval_digests,
            self._state.used_record_digests,
        )

    def commit(
        self,
        *,
        record_id: str,
        manifest: StorageAdapterManifest,
        capability: StorageAdapterCapability,
        evidence: StorageAdapterAttestationEvidence,
        conformance: AdapterConformanceResult,
        review: StorageAdapterReview,
        approval: StorageAdapterApproval,
        policy: StorageAdapterPolicy,
        roles: AdapterRoleContext,
        adapter_generation: int,
        predecessor_record_digest: str | None,
        recorded_at: datetime,
        fault: AdapterRegistryFault = AdapterRegistryFault.NONE,
    ) -> AdapterRegistryResult:
        reasons: list[AdapterRegistryReason] = []
        objects = (manifest, capability, evidence, conformance, review, approval, policy, roles)
        exact = (
            all(canonical_object_valid(v) for v in objects),
            manifest.capability_digest == capability.canonical_digest,
            evidence.adapter_manifest_digest == manifest.canonical_digest,
            evidence.capability_digest == capability.canonical_digest,
            conformance.manifest_digest == manifest.canonical_digest,
            conformance.capability_digest == capability.canonical_digest,
            conformance.evidence_digest == evidence.canonical_digest,
            conformance.policy_digest == policy.canonical_digest,
            review.manifest_digest == manifest.canonical_digest,
            review.evidence_digest == evidence.canonical_digest,
            review.conformance_result_digest == conformance.canonical_digest,
            approval.manifest_digest == manifest.canonical_digest,
            approval.evidence_digest == evidence.canonical_digest,
            approval.review_digest == review.canonical_digest,
            approval.policy_digest == policy.canonical_digest,
            evidence.generated_by == roles.evidence_producer_id,
            review.reviewer_id == roles.adapter_reviewer_id,
            approval.approver_id == roles.adapter_approver_id,
        )
        if (
            not all(exact)
            or conformance.state is not AdapterConformanceState.ELIGIBLE_FOR_ADAPTER_REVIEW
            or review.review_result is not AdapterReviewResult.APPROVED
            or approval.approval_result is not AdapterApprovalResult.APPROVED
            or not policy.is_approved
        ):
            reasons.append(AdapterRegistryReason.INVALID_CHAIN)
        role_ids = tuple(value for name, value in vars(roles).items() if name.endswith("_id"))
        if len(set(role_ids)) != len(role_ids):
            reasons.append(AdapterRegistryReason.ROLE_CONFLICT)
        expected_generation = len(self._state.records) + 1
        expected_predecessor = self._state.records[-1].canonical_digest if self._state.records else None
        if adapter_generation != expected_generation:
            reasons.append(AdapterRegistryReason.GENERATION_MISMATCH)
        if predecessor_record_digest != expected_predecessor:
            reasons.append(AdapterRegistryReason.PREDECESSOR_MISMATCH)
        if not (
            manifest.created_at <= evidence.generated_at <= conformance.evaluated_at
            <= review.reviewed_at < approval.approved_at <= recorded_at < policy.expires_at
        ) or recorded_at - approval.approved_at > MAX_ADAPTER_EVIDENCE_AGE:
            reasons.append(AdapterRegistryReason.TEMPORAL_INVALID)
        if (
            manifest.canonical_digest in self._state.used_manifest_digests
            or evidence.canonical_digest in self._state.used_evidence_digests
            or review.canonical_digest in self._state.used_review_digests
            or approval.canonical_digest in self._state.used_approval_digests
        ):
            reasons.append(AdapterRegistryReason.REPLAY)
        if reasons:
            return self._result(False, tuple(dict.fromkeys(reasons)), None)
        try:
            if fault is AdapterRegistryFault.CANDIDATE_STATE:
                raise RuntimeError
            record = ApprovedStorageAdapterRecord(
                record_id,
                manifest.canonical_digest,
                capability.canonical_digest,
                evidence.canonical_digest,
                review.canonical_digest,
                approval.canonical_digest,
                policy.canonical_digest,
                roles.canonical_digest,
                roles.adapter_approver_id,
                adapter_generation,
                predecessor_record_digest,
                recorded_at,
                AdapterRecordState.APPROVED_FOR_WRITE_AUTHORIZATION_REVIEW,
                AdapterLifecycleStatus.APPROVED,
                _marker=_RECORD_MARKER,
            )
            if fault is AdapterRegistryFault.COUNTERS:
                raise RuntimeError
            candidate = _AdapterRegistryState(
                self._state.records + (record,),
                self._state.used_manifest_digests | {manifest.canonical_digest},
                self._state.used_evidence_digests | {evidence.canonical_digest},
                self._state.used_review_digests | {review.canonical_digest},
                self._state.used_approval_digests | {approval.canonical_digest},
                self._state.used_record_digests | {record.canonical_digest},
                self.write_count + 1,
                self.mutation_count + 1,
                self.event_count + 1,
            )
            if fault is AdapterRegistryFault.BEFORE_SWAP:
                raise RuntimeError
            self._state = candidate
            return self._result(True, (), record)
        except RuntimeError:
            return self._result(False, (AdapterRegistryReason.COMMIT_FAULT,), None)

    def transition_status(
        self,
        *,
        source_record: ApprovedStorageAdapterRecord,
        new_record_id: str,
        new_status: AdapterLifecycleStatus,
        transitioned_at: datetime,
        fault: AdapterRegistryFault = AdapterRegistryFault.NONE,
    ) -> AdapterRegistryResult:
        if (
            not self.records
            or source_record.canonical_digest != self.records[-1].canonical_digest
            or source_record.lifecycle_status in {AdapterLifecycleStatus.REVOKED, AdapterLifecycleStatus.SUPERSEDED}
            or source_record.lifecycle_status is AdapterLifecycleStatus.DEPRECATED
            and new_status is AdapterLifecycleStatus.DEPRECATED
            or new_status not in {
                AdapterLifecycleStatus.DEPRECATED,
                AdapterLifecycleStatus.REVOKED,
                AdapterLifecycleStatus.SUPERSEDED,
            }
            or not is_aware(transitioned_at)
            or transitioned_at <= source_record.recorded_at
        ):
            return self._result(False, (AdapterRegistryReason.STATUS_INVALID,), None)
        if fault is not AdapterRegistryFault.NONE:
            return self._result(False, (AdapterRegistryReason.COMMIT_FAULT,), None)
        record = ApprovedStorageAdapterRecord(
            new_record_id,
            source_record.manifest_digest,
            source_record.capability_digest,
            source_record.evidence_digest,
            source_record.review_digest,
            source_record.approval_digest,
            source_record.policy_digest,
            source_record.role_context_digest,
            source_record.adapter_approver_id,
            source_record.adapter_generation + 1,
            source_record.canonical_digest,
            transitioned_at,
            source_record.state,
            new_status,
            _marker=_RECORD_MARKER,
        )
        candidate = replace(
            self._state,
            records=self.records + (record,),
            used_record_digests=self._state.used_record_digests | {record.canonical_digest},
            write_count=self.write_count + 1,
            mutation_count=self.mutation_count + 1,
            event_count=self.event_count + 1,
        )
        self._state = candidate
        return self._result(True, (), record)

    def _result(self, applied, reasons, record):
        return AdapterRegistryResult(
            applied, reasons, record, self.write_count, self.mutation_count, self.event_count
        )


@dataclass(frozen=True)
class WriteCompatibilityDecision:
    state: WriteCompatibilityState
    reasons: tuple[WriteCompatibilityReason, ...]
    adapter_record_digest: str
    persistence_intent_digest: str
    transaction_plan_digest: str
    evaluated_at: datetime
    canonical_digest: str = field(init=False)
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    external_storage_write_count: int = field(init=False, default=0)
    production_registry_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    credential_use_count: int = field(init=False, default=0)
    token_generation_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    runtime_switch_count: int = field(init=False, default=0)
    real_data_access_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json({
            "adapter_record_digest": self.adapter_record_digest,
            "evaluated_at": canonical_datetime(self.evaluated_at),
            "persistence_intent_digest": self.persistence_intent_digest,
            "reasons": [v.value for v in self.reasons],
            "state": self.state.value,
            "transaction_plan_digest": self.transaction_plan_digest,
        })))


def evaluate_write_compatibility(
    record: ApprovedStorageAdapterRecord,
    manifest: StorageAdapterManifest,
    capability: StorageAdapterCapability,
    policy: StorageAdapterPolicy,
    persistence_request: PersistenceAuthorizationRequest,
    intent: PersistenceIntent,
    plan: PersistenceTransactionPlan,
    receipt: PersistenceCommitReceiptV2,
    runtime_record: RuntimeAuthorizationCommitRecord,
    *,
    evaluation_time: datetime,
) -> WriteCompatibilityDecision:
    if not is_aware(evaluation_time):
        raise StorageAdapterError("write_compatibility_time_invalid")
    reasons: list[WriteCompatibilityReason] = []
    objects = (
        record, manifest, capability, policy, persistence_request,
        intent, plan, receipt, runtime_record,
    )
    exact = (
        all(canonical_object_valid(v) for v in objects),
        record.manifest_digest == manifest.canonical_digest,
        record.capability_digest == capability.canonical_digest,
        record.policy_digest == policy.canonical_digest,
        manifest.capability_digest == capability.canonical_digest,
        persistence_request.runtime_authorization_record_digest == runtime_record.canonical_digest,
        intent.authorization_request_digest == persistence_request.canonical_digest,
        intent.runtime_authorization_record_digest == runtime_record.canonical_digest,
        plan.intent_digest == intent.canonical_digest,
        plan.payload_digest == intent.content_digest,
        receipt.intent_digest == intent.canonical_digest,
        receipt.transaction_plan_digest == plan.canonical_digest,
        receipt.authorization_record_digest == runtime_record.canonical_digest,
        receipt.committed_content_digest == intent.content_digest,
    )
    if not all(exact):
        reasons.append(WriteCompatibilityReason.DIGEST_MISMATCH)
    if (
        record.state is not AdapterRecordState.APPROVED_FOR_WRITE_AUTHORIZATION_REVIEW
        or record.lifecycle_status is not AdapterLifecycleStatus.APPROVED
    ):
        reasons.append(WriteCompatibilityReason.ADAPTER_NOT_APPROVED)
    if not policy.is_approved or not (policy.effective_at <= evaluation_time < policy.expires_at):
        reasons.append(WriteCompatibilityReason.POLICY_INVALID)
    if (
        manifest.transaction_model is not TransactionModel.ATOMIC_COMPARE_AND_SWAP
        or manifest.durability_model is not DurabilityModel.DURABLE_APPEND_ONLY
        or intent.target_store_class is not TargetStoreClass.DURABLE_APPEND_ONLY
        or not capability.all_required
    ):
        reasons.append(WriteCompatibilityReason.MODEL_INCOMPATIBLE)
    if not (
        persistence_request.expected_generation
        == intent.expected_generation
        == plan.generation
        == receipt.generation
    ):
        reasons.append(WriteCompatibilityReason.GENERATION_MISMATCH)
    if not (
        persistence_request.expected_previous_record_digest
        == intent.previous_record_digest
        == plan.predecessor_digest
        == receipt.predecessor_digest
    ):
        reasons.append(WriteCompatibilityReason.PREDECESSOR_MISMATCH)
    if record.adapter_approver_id in {
        persistence_request.persistence_operator_id,
        runtime_record.runtime_authorization_approver_id,
    }:
        reasons.append(WriteCompatibilityReason.ROLE_CONFLICT)
    if not (
        receipt.committed_at <= evaluation_time < policy.expires_at
        and record.recorded_at <= evaluation_time
    ):
        reasons.append(WriteCompatibilityReason.TEMPORAL_INVALID)
    if reasons:
        state = (
            WriteCompatibilityState.NEEDS_ADAPTER_APPROVAL
            if reasons == [WriteCompatibilityReason.ADAPTER_NOT_APPROVED]
            else WriteCompatibilityState.INCOMPATIBLE
        )
    else:
        state = WriteCompatibilityState.READY_FOR_WRITE_AUTHORIZATION_REVIEW
    return WriteCompatibilityDecision(
        state,
        tuple(dict.fromkeys(reasons)),
        record.canonical_digest,
        intent.canonical_digest,
        plan.canonical_digest,
        evaluation_time,
    )
