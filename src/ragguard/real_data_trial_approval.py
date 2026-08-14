from __future__ import annotations

from dataclasses import InitVar, dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum

from ragguard.local_rag_environment import (
    EnvironmentApproval,
    EnvironmentApprovalResult,
    LocalRAGEnvironmentManifest,
)
from ragguard.local_rag_execution import (
    ApprovedLocalRAGExecutionSession,
    RealDataTrialReadinessDecision,
    RealDataTrialReadinessState,
    SessionApprovalResult,
    SessionAuthorizationState,
    SessionExecutionApproval,
    SessionExecutionReceipt,
    SessionExecutionResult,
    SessionExecutionReview,
    SessionLifecycle,
    SessionReviewResult,
)
from ragguard.real_data_trial import (
    RealDataClassificationPolicy,
    RealDataTrialScope,
    TrialCachePolicy,
    TrialExportPolicy,
    TrialLoggingPolicy,
    TrialPersistencePolicy,
    TrialRetentionPolicy,
    TrialStagePolicy,
    validate_trial_scope_policies,
)
from ragguard.storage_adapter import (
    canonical_datetime,
    canonical_json,
    canonical_object_valid,
    digest,
    is_aware,
    is_digest,
    is_identifier,
)


MAX_TRIAL_READINESS_AGE = timedelta(hours=1)
_APPROVED_TRIAL_MARKER = object()


class RealDataTrialApprovalError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class TrialReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class TrialApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovedTrialState(str, Enum):
    APPROVED_FOR_REAL_DATA_ACCESS_AUTHORIZATION_REVIEW = (
        "approved_for_real_data_access_authorization_review"
    )


class TrialLifecycle(str, Enum):
    APPROVED = "approved"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class TrialRegistryReason(str, Enum):
    INVALID_CHAIN = "invalid_chain"
    POLICY_INVALID = "policy_invalid"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    GENERATION_MISMATCH = "generation_mismatch"
    PREDECESSOR_MISMATCH = "predecessor_mismatch"
    REPLAY = "replay"
    COMMIT_FAULT = "commit_fault"
    STATUS_INVALID = "status_invalid"


class TrialRegistryFault(str, Enum):
    NONE = "none"
    CANDIDATE_STATE = "candidate_state"
    BEFORE_SWAP = "before_swap"


class RealDataAccessAuthorizationReadinessState(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_TRIAL_SECURITY_REVIEW = "needs_trial_security_review"
    NEEDS_TRIAL_GOVERNANCE_REVIEW = "needs_trial_governance_review"
    NEEDS_TRIAL_APPROVAL = "needs_trial_approval"
    ELIGIBLE_FOR_REAL_DATA_ACCESS_AUTHORIZATION_REVIEW = (
        "eligible_for_real_data_access_authorization_review"
    )


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


def _is_utc(value: object) -> bool:
    return is_aware(value) and value.utcoffset() == timedelta(0)


@dataclass(frozen=True, repr=False)
class TrialRoleContext(_Canonical):
    trial_requester_id: str
    session_operator_id: str
    environment_approver_id: str
    security_reviewer_id: str
    governance_reviewer_id: str
    trial_approver_id: str

    def __post_init__(self) -> None:
        values = tuple(vars(self).values())
        if (not all(is_identifier(value) for value in values)
                or len(set(values)) != len(values)):
            raise RealDataTrialApprovalError("trial_role_conflict")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {key: value for key, value in vars(self).items()
                if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialApprovalRequest(_Canonical):
    trial_request_id: str
    trial_scope_digest: str
    v0_23_readiness_record_digest: str
    approved_session_digest: str
    environment_approval_digest: str
    requested_by: str
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (not is_identifier(self.trial_request_id) or not is_identifier(self.requested_by)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))
                or not _is_utc(self.requested_at) or not _is_utc(self.expires_at)
                or self.expires_at <= self.requested_at):
            raise RealDataTrialApprovalError("trial_request_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {key: canonical_datetime(value) if isinstance(value, datetime) else value
                for key, value in vars(self).items() if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialSecurityReview(_Canonical):
    review_id: str
    trial_request_digest: str
    trial_scope_digest: str
    readiness_record_digest: str
    reviewed_at: datetime
    reviewer_id: str
    result: TrialReviewResult
    findings_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.review_id) or not is_identifier(self.reviewer_id)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))
                or not _is_utc(self.reviewed_at)
                or not isinstance(self.result, TrialReviewResult)):
            raise RealDataTrialApprovalError("trial_security_review_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"findings_digest": self.findings_digest, "result": self.result.value,
                "review_id": self.review_id, "reviewed_at": canonical_datetime(self.reviewed_at),
                "reviewer_id": self.reviewer_id,
                "readiness_record_digest": self.readiness_record_digest,
                "trial_request_digest": self.trial_request_digest,
                "trial_scope_digest": self.trial_scope_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialDataGovernanceReview(_Canonical):
    review_id: str
    trial_request_digest: str
    classification_policy_digest: str
    retention_policy_digest: str
    logging_policy_digest: str
    persistence_policy_digest: str
    reviewed_at: datetime
    reviewer_id: str
    result: TrialReviewResult
    findings_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.review_id) or not is_identifier(self.reviewer_id)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))
                or not _is_utc(self.reviewed_at)
                or not isinstance(self.result, TrialReviewResult)):
            raise RealDataTrialApprovalError("trial_governance_review_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"classification_policy_digest": self.classification_policy_digest,
                "findings_digest": self.findings_digest,
                "logging_policy_digest": self.logging_policy_digest,
                "persistence_policy_digest": self.persistence_policy_digest,
                "result": self.result.value, "retention_policy_digest": self.retention_policy_digest,
                "review_id": self.review_id, "reviewed_at": canonical_datetime(self.reviewed_at),
                "reviewer_id": self.reviewer_id,
                "trial_request_digest": self.trial_request_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialApproval(_Canonical):
    approval_id: str
    trial_request_digest: str
    security_review_digest: str
    governance_review_digest: str
    approver_id: str
    approved_at: datetime
    expires_at: datetime
    result: TrialApprovalResult

    def __post_init__(self) -> None:
        if (not is_identifier(self.approval_id) or not is_identifier(self.approver_id)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))
                or not _is_utc(self.approved_at) or not _is_utc(self.expires_at)
                or self.expires_at <= self.approved_at
                or not isinstance(self.result, TrialApprovalResult)):
            raise RealDataTrialApprovalError("trial_approval_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"approval_id": self.approval_id,
                "approved_at": canonical_datetime(self.approved_at),
                "approver_id": self.approver_id,
                "expires_at": canonical_datetime(self.expires_at),
                "governance_review_digest": self.governance_review_digest,
                "result": self.result.value,
                "security_review_digest": self.security_review_digest,
                "trial_request_digest": self.trial_request_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def real_data_access_authorized(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class ApprovedRealDataTrialRecord(_Canonical):
    approved_trial_record_id: str
    trial_scope_digest: str
    trial_request_digest: str
    security_review_digest: str
    governance_review_digest: str
    approval_digest: str
    approved_session_digest: str
    environment_approval_digest: str
    trial_generation: int
    predecessor_trial_digest: str | None
    approved_at: datetime
    expires_at: datetime
    state: ApprovedTrialState = ApprovedTrialState.APPROVED_FOR_REAL_DATA_ACCESS_AUTHORIZATION_REVIEW
    lifecycle: TrialLifecycle = TrialLifecycle.APPROVED
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        if (not is_identifier(self.approved_trial_record_id)
                or not all(is_digest(value) for value in (
                    self.trial_scope_digest, self.trial_request_digest,
                    self.security_review_digest, self.governance_review_digest,
                    self.approval_digest, self.approved_session_digest,
                    self.environment_approval_digest))
                or (self.predecessor_trial_digest is not None
                    and not is_digest(self.predecessor_trial_digest))
                or type(self.trial_generation) is not int or self.trial_generation < 1
                or not _is_utc(self.approved_at) or not _is_utc(self.expires_at)
                or self.expires_at <= self.approved_at
                or not isinstance(self.state, ApprovedTrialState)
                or not isinstance(self.lifecycle, TrialLifecycle)
                or _marker is not _APPROVED_TRIAL_MARKER):
            raise RealDataTrialApprovalError("approved_trial_record_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"approval_digest": self.approval_digest,
                "approved_at": canonical_datetime(self.approved_at),
                "approved_session_digest": self.approved_session_digest,
                "approved_trial_record_id": self.approved_trial_record_id,
                "environment_approval_digest": self.environment_approval_digest,
                "expires_at": canonical_datetime(self.expires_at),
                "governance_review_digest": self.governance_review_digest,
                "lifecycle": self.lifecycle.value,
                "predecessor_trial_digest": self.predecessor_trial_digest,
                "security_review_digest": self.security_review_digest,
                "state": self.state.value, "trial_generation": self.trial_generation,
                "trial_request_digest": self.trial_request_digest,
                "trial_scope_digest": self.trial_scope_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def actual_real_data_read(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class TrialSideEffectAccounting(_Canonical):
    actual_file_read_count: int = 0
    real_data_access_count: int = 0
    filesystem_write_count: int = 0
    database_write_count: int = 0
    persistent_vector_write_count: int = 0
    external_network_count: int = 0
    http_count: int = 0
    cloud_count: int = 0
    production_registry_write_count: int = 0
    credential_use_count: int = 0
    token_use_count: int = 0
    runtime_activation_count: int = 0
    runtime_switch_count: int = 0

    def __post_init__(self) -> None:
        if not all(type(value) is int and value >= 0 for value in vars(self).values()):
            raise RealDataTrialApprovalError("trial_side_effect_accounting_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, int]:
        return {key: value for key, value in vars(self).items()
                if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def all_zero(self) -> bool:
        return all(value == 0 for value in self._payload().values())


def validate_v023_trial_source_chain(
    environment_manifest: LocalRAGEnvironmentManifest,
    environment_approval: EnvironmentApproval,
    approved_session: ApprovedLocalRAGExecutionSession,
    execution_receipt: SessionExecutionReceipt,
    execution_review: SessionExecutionReview,
    execution_approval: SessionExecutionApproval,
    readiness: RealDataTrialReadinessDecision,
    *,
    evaluation_time: datetime,
) -> tuple[str, ...]:
    reasons: list[str] = []
    objects = (environment_manifest, environment_approval, approved_session,
               execution_receipt, execution_review, execution_approval, readiness)
    if not all(canonical_object_valid(value) for value in objects):
        reasons.append("forged_v023_trial_chain")
    if (environment_approval.result is not EnvironmentApprovalResult.APPROVED
            or approved_session.state is not SessionAuthorizationState.APPROVED_FOR_CONTROLLED_EXECUTION
            or approved_session.lifecycle is not SessionLifecycle.APPROVED
            or execution_receipt.result is not SessionExecutionResult.PASSED
            or execution_review.result is not SessionReviewResult.APPROVED
            or execution_approval.result is not SessionApprovalResult.APPROVED
            or readiness.state is not (
                RealDataTrialReadinessState.ELIGIBLE_FOR_EXPLICIT_REAL_DATA_TRIAL_APPROVAL_REVIEW)):
        reasons.append("v023_trial_source_not_approved")
    if (environment_approval.manifest_digest != environment_manifest.canonical_digest
            or approved_session.environment_manifest_digest != environment_manifest.canonical_digest
            or approved_session.environment_approval_digest != environment_approval.canonical_digest
            or execution_receipt.session_digest != approved_session.canonical_digest
            or execution_receipt.environment_manifest_digest != environment_manifest.canonical_digest
            or execution_receipt.environment_approval_digest != environment_approval.canonical_digest
            or execution_receipt.operator_id != approved_session.operator_id
            or execution_review.session_digest != approved_session.canonical_digest
            or execution_review.execution_receipt_digest != execution_receipt.canonical_digest
            or execution_approval.session_digest != approved_session.canonical_digest
            or execution_approval.execution_receipt_digest != execution_receipt.canonical_digest
            or execution_approval.review_digest != execution_review.canonical_digest
            or readiness.session_digest != approved_session.canonical_digest
            or readiness.execution_receipt_digest != execution_receipt.canonical_digest
            or readiness.review_digest != execution_review.canonical_digest
            or readiness.approval_digest != execution_approval.canonical_digest):
        reasons.append("v023_trial_source_binding_mismatch")
    if (not _is_utc(evaluation_time)
            or not all(_is_utc(value) for value in (
                environment_manifest.created_at, environment_approval.approved_at,
                approved_session.approved_at, approved_session.expires_at,
                execution_receipt.started_at, execution_receipt.finished_at,
                execution_review.reviewed_at, execution_approval.approved_at,
                readiness.evaluated_at))
            or not (environment_approval.approved_at <= approved_session.approved_at
                    <= execution_receipt.started_at <= execution_receipt.finished_at
                    < execution_review.reviewed_at < execution_approval.approved_at
                    <= readiness.evaluated_at <= evaluation_time < approved_session.expires_at)
            or evaluation_time - readiness.evaluated_at > MAX_TRIAL_READINESS_AGE):
        reasons.append("v023_trial_source_temporal_invalid")
    if (readiness.real_data_approved or readiness.real_data_use_authorized
            or readiness.production_active
            or any(value != 0 for key, value in vars(readiness).items()
                   if key.endswith("_count"))):
        reasons.append("v023_trial_source_boundary_invalid")
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True)
class TrialRegistryResult:
    applied: bool
    reasons: tuple[TrialRegistryReason, ...]
    record: ApprovedRealDataTrialRecord | None
    write_count: int
    mutation_count: int
    event_count: int


@dataclass(frozen=True)
class _TrialRegistryState:
    records: tuple[ApprovedRealDataTrialRecord, ...] = ()
    used_request_digests: frozenset[str] = frozenset()
    used_security_review_digests: frozenset[str] = frozenset()
    used_governance_review_digests: frozenset[str] = frozenset()
    used_approval_digests: frozenset[str] = frozenset()
    used_record_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class TestOnlyRealDataTrialRegistry:
    __test__ = False

    def __init__(self) -> None:
        self._state = _TrialRegistryState()

    @property
    def records(self) -> tuple[ApprovedRealDataTrialRecord, ...]:
        return self._state.records

    @property
    def write_count(self) -> int:
        return self._state.write_count

    @property
    def mutation_count(self) -> int:
        return self._state.mutation_count

    @property
    def event_count(self) -> int:
        return self._state.event_count

    @property
    def replay_snapshot(self) -> tuple[frozenset[str], ...]:
        return (self._state.used_request_digests,
                self._state.used_security_review_digests,
                self._state.used_governance_review_digests,
                self._state.used_approval_digests,
                self._state.used_record_digests)

    def approve(
        self,
        *,
        approved_trial_record_id: str,
        scope: RealDataTrialScope,
        classification_policy: RealDataClassificationPolicy,
        stage_policy: TrialStagePolicy,
        retention_policy: TrialRetentionPolicy,
        logging_policy: TrialLoggingPolicy,
        cache_policy: TrialCachePolicy,
        export_policy: TrialExportPolicy,
        persistence_policy: TrialPersistencePolicy,
        request: TrialApprovalRequest,
        security_review: TrialSecurityReview | None,
        governance_review: TrialDataGovernanceReview | None,
        approval: TrialApproval | None,
        roles: TrialRoleContext,
        environment_manifest: LocalRAGEnvironmentManifest,
        environment_approval: EnvironmentApproval,
        approved_session: ApprovedLocalRAGExecutionSession,
        execution_receipt: SessionExecutionReceipt,
        execution_review: SessionExecutionReview,
        execution_approval: SessionExecutionApproval,
        v0_23_readiness: RealDataTrialReadinessDecision,
        trial_generation: int,
        predecessor_trial_digest: str | None,
        approved_at: datetime,
        record_expires_at: datetime,
        fault: TrialRegistryFault = TrialRegistryFault.NONE,
    ) -> TrialRegistryResult:
        reasons: list[TrialRegistryReason] = []
        if not isinstance(security_review, TrialSecurityReview) \
                or not isinstance(governance_review, TrialDataGovernanceReview) \
                or not isinstance(approval, TrialApproval):
            return self._result(False, (TrialRegistryReason.INVALID_CHAIN,), None)
        objects = (scope, classification_policy, stage_policy, retention_policy,
            logging_policy, cache_policy, export_policy, persistence_policy,
            request, security_review, governance_review, approval, roles,
            environment_manifest, environment_approval, approved_session,
            execution_receipt, execution_review, execution_approval, v0_23_readiness)
        if not all(canonical_object_valid(value) for value in objects):
            reasons.append(TrialRegistryReason.INVALID_CHAIN)
        source_reasons = validate_v023_trial_source_chain(
            environment_manifest, environment_approval, approved_session,
            execution_receipt, execution_review, execution_approval, v0_23_readiness,
            evaluation_time=approved_at)
        if source_reasons:
            reasons.append(TrialRegistryReason.INVALID_CHAIN)
        if validate_trial_scope_policies(scope, classification_policy, stage_policy,
                retention_policy, logging_policy, cache_policy, export_policy,
                persistence_policy):
            reasons.append(TrialRegistryReason.POLICY_INVALID)
        exact = (
            scope.approved_session_digest == approved_session.canonical_digest,
            scope.environment_manifest_digest == environment_manifest.canonical_digest,
            scope.environment_approval_digest == environment_approval.canonical_digest,
            scope.integration_manifest_digest == execution_receipt.integration_manifest_digest,
            scope.fixture_validation_receipt_digest == execution_receipt.canonical_digest,
            request.trial_scope_digest == scope.canonical_digest,
            request.v0_23_readiness_record_digest == v0_23_readiness.canonical_digest,
            request.approved_session_digest == approved_session.canonical_digest,
            request.environment_approval_digest == environment_approval.canonical_digest,
            security_review.trial_request_digest == request.canonical_digest,
            security_review.trial_scope_digest == scope.canonical_digest,
            security_review.readiness_record_digest == v0_23_readiness.canonical_digest,
            governance_review.trial_request_digest == request.canonical_digest,
            governance_review.classification_policy_digest == classification_policy.canonical_digest,
            governance_review.retention_policy_digest == retention_policy.canonical_digest,
            governance_review.logging_policy_digest == logging_policy.canonical_digest,
            governance_review.persistence_policy_digest == persistence_policy.canonical_digest,
            approval.trial_request_digest == request.canonical_digest,
            approval.security_review_digest == security_review.canonical_digest,
            approval.governance_review_digest == governance_review.canonical_digest,
            security_review.result is TrialReviewResult.APPROVED,
            governance_review.result is TrialReviewResult.APPROVED,
            approval.result is TrialApprovalResult.APPROVED,
        )
        if not all(exact):
            reasons.append(TrialRegistryReason.INVALID_CHAIN)
        role_values = (
            request.requested_by, approved_session.operator_id,
            environment_approval.approver_id, security_review.reviewer_id,
            governance_review.reviewer_id, approval.approver_id,
        )
        if (request.requested_by != roles.trial_requester_id
                or approved_session.operator_id != roles.session_operator_id
                or environment_approval.approver_id != roles.environment_approver_id
                or security_review.reviewer_id != roles.security_reviewer_id
                or governance_review.reviewer_id != roles.governance_reviewer_id
                or approval.approver_id != roles.trial_approver_id
                or len(set(role_values)) != len(role_values)):
            reasons.append(TrialRegistryReason.ROLE_CONFLICT)
        expected_generation = len(self.records) + 1
        expected_predecessor = self.records[-1].canonical_digest if self.records else None
        if trial_generation != expected_generation:
            reasons.append(TrialRegistryReason.GENERATION_MISMATCH)
        if predecessor_trial_digest != expected_predecessor:
            reasons.append(TrialRegistryReason.PREDECESSOR_MISMATCH)
        if self.records and self.records[-1].lifecycle is not TrialLifecycle.APPROVED:
            reasons.append(TrialRegistryReason.STATUS_INVALID)
        replay_values = (
            (request.canonical_digest, self._state.used_request_digests),
            (security_review.canonical_digest, self._state.used_security_review_digests),
            (governance_review.canonical_digest, self._state.used_governance_review_digests),
            (approval.canonical_digest, self._state.used_approval_digests),
        )
        if any(value in used for value, used in replay_values):
            reasons.append(TrialRegistryReason.REPLAY)
        temporal_values = (
            scope.created_at, scope.expires_at, request.requested_at, request.expires_at,
            security_review.reviewed_at, governance_review.reviewed_at,
            approval.approved_at, approval.expires_at, approved_at, record_expires_at,
        )
        latest_expiry = min(scope.expires_at, request.expires_at, approval.expires_at,
                            approved_session.expires_at)
        if (not all(_is_utc(value) for value in temporal_values)
                or not (v0_23_readiness.evaluated_at < scope.created_at
                        <= request.requested_at < security_review.reviewed_at
                        < governance_review.reviewed_at < approval.approved_at
                        <= approved_at < record_expires_at <= latest_expiry)
                or approved_at - v0_23_readiness.evaluated_at > MAX_TRIAL_READINESS_AGE):
            reasons.append(TrialRegistryReason.TEMPORAL_INVALID)
        if reasons:
            return self._result(False, tuple(dict.fromkeys(reasons)), None)
        try:
            if fault is TrialRegistryFault.CANDIDATE_STATE:
                raise RuntimeError
            record = ApprovedRealDataTrialRecord(
                approved_trial_record_id, scope.canonical_digest, request.canonical_digest,
                security_review.canonical_digest, governance_review.canonical_digest,
                approval.canonical_digest, approved_session.canonical_digest,
                environment_approval.canonical_digest, trial_generation,
                predecessor_trial_digest, approved_at, record_expires_at,
                _marker=_APPROVED_TRIAL_MARKER)
            if record.canonical_digest in self._state.used_record_digests:
                return self._result(False, (TrialRegistryReason.REPLAY,), None)
            candidate = replace(self._state,
                records=self.records + (record,),
                used_request_digests=self._state.used_request_digests | {
                    request.canonical_digest},
                used_security_review_digests=self._state.used_security_review_digests | {
                    security_review.canonical_digest},
                used_governance_review_digests=self._state.used_governance_review_digests | {
                    governance_review.canonical_digest},
                used_approval_digests=self._state.used_approval_digests | {
                    approval.canonical_digest},
                used_record_digests=self._state.used_record_digests | {record.canonical_digest},
                write_count=self.write_count + 1,
                mutation_count=self.mutation_count + 1,
                event_count=self.event_count + 1)
            if fault is TrialRegistryFault.BEFORE_SWAP:
                raise RuntimeError
            self._state = candidate
            return self._result(True, (), record)
        except RuntimeError:
            return self._result(False, (TrialRegistryReason.COMMIT_FAULT,), None)

    def transition(
        self,
        *,
        source_record: ApprovedRealDataTrialRecord,
        new_record_id: str,
        lifecycle: TrialLifecycle,
        transitioned_at: datetime,
        fault: TrialRegistryFault = TrialRegistryFault.NONE,
    ) -> TrialRegistryResult:
        if (not self.records or not canonical_object_valid(source_record)
                or source_record.canonical_digest != self.records[-1].canonical_digest
                or source_record.lifecycle is not TrialLifecycle.APPROVED
                or lifecycle not in {
                    TrialLifecycle.EXPIRED, TrialLifecycle.REVOKED, TrialLifecycle.SUPERSEDED}
                or not _is_utc(transitioned_at)
                or transitioned_at <= source_record.approved_at):
            return self._result(False, (TrialRegistryReason.STATUS_INVALID,), None)
        if fault is not TrialRegistryFault.NONE:
            return self._result(False, (TrialRegistryReason.COMMIT_FAULT,), None)
        transitioned = ApprovedRealDataTrialRecord(
            new_record_id, source_record.trial_scope_digest,
            source_record.trial_request_digest, source_record.security_review_digest,
            source_record.governance_review_digest, source_record.approval_digest,
            source_record.approved_session_digest, source_record.environment_approval_digest,
            source_record.trial_generation + 1, source_record.canonical_digest,
            transitioned_at, max(source_record.expires_at,
                                 transitioned_at + timedelta(microseconds=1)),
            source_record.state, lifecycle, _marker=_APPROVED_TRIAL_MARKER)
        candidate = replace(self._state, records=self.records + (transitioned,),
            used_record_digests=self._state.used_record_digests | {
                transitioned.canonical_digest},
            write_count=self.write_count + 1, mutation_count=self.mutation_count + 1,
            event_count=self.event_count + 1)
        self._state = candidate
        return self._result(True, (), transitioned)

    def _result(self, applied, reasons, record) -> TrialRegistryResult:
        return TrialRegistryResult(applied, reasons, record,
            self.write_count, self.mutation_count, self.event_count)


@dataclass(frozen=True, repr=False)
class RealDataAccessAuthorizationReadinessDecision(_Canonical):
    state: RealDataAccessAuthorizationReadinessState
    trial_scope_digest: str
    trial_request_digest: str
    security_review_digest: str
    governance_review_digest: str
    trial_approval_digest: str
    approved_trial_record_digest: str
    side_effect_accounting_digest: str
    reason_codes: tuple[str, ...]
    evaluated_at: datetime
    actual_real_data_access_authorized: bool = field(init=False, default=False)
    real_data_use_authorized: bool = field(init=False, default=False)
    actual_real_data_read: bool = field(init=False, default=False)
    production_active: bool = field(init=False, default=False)
    actual_file_read_count: int = field(init=False, default=0)
    real_data_access_count: int = field(init=False, default=0)
    filesystem_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    persistent_vector_write_count: int = field(init=False, default=0)
    external_network_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    cloud_count: int = field(init=False, default=0)
    production_registry_write_count: int = field(init=False, default=0)
    credential_use_count: int = field(init=False, default=0)
    token_use_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    runtime_switch_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if (not isinstance(self.state, RealDataAccessAuthorizationReadinessState)
                or not all(is_digest(value) for value in (
                    self.trial_scope_digest, self.trial_request_digest,
                    self.security_review_digest, self.governance_review_digest,
                    self.trial_approval_digest, self.approved_trial_record_digest,
                    self.side_effect_accounting_digest))
                or not self.reason_codes
                or not all(is_identifier(value) for value in self.reason_codes)
                or not _is_utc(self.evaluated_at)):
            raise RealDataTrialApprovalError("access_authorization_readiness_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        counts = {key: value for key, value in vars(self).items() if key.endswith("_count")}
        return {"approved_trial_record_digest": self.approved_trial_record_digest,
                "evaluated_at": canonical_datetime(self.evaluated_at),
                "external_side_effect_counts": counts,
                "governance_review_digest": self.governance_review_digest,
                "reason_codes": list(self.reason_codes),
                "security_review_digest": self.security_review_digest,
                "side_effect_accounting_digest": self.side_effect_accounting_digest,
                "state": self.state.value,
                "trial_approval_digest": self.trial_approval_digest,
                "trial_request_digest": self.trial_request_digest,
                "trial_scope_digest": self.trial_scope_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


def evaluate_real_data_access_authorization_readiness(
    scope: RealDataTrialScope,
    request: TrialApprovalRequest,
    security_review: TrialSecurityReview | None,
    governance_review: TrialDataGovernanceReview | None,
    approval: TrialApproval | None,
    record: ApprovedRealDataTrialRecord | None,
    roles: TrialRoleContext,
    side_effects: TrialSideEffectAccounting,
    *,
    evaluation_time: datetime,
) -> RealDataAccessAuthorizationReadinessDecision:
    if not _is_utc(evaluation_time):
        raise RealDataTrialApprovalError("access_authorization_readiness_time_invalid")
    missing = digest("missing")
    base_objects = (scope, request, roles, side_effects)
    if (not all(canonical_object_valid(value) for value in base_objects)
            or request.trial_scope_digest != scope.canonical_digest
            or request.requested_by != roles.trial_requester_id
            or not side_effects.all_zero):
        return RealDataAccessAuthorizationReadinessDecision(
            RealDataAccessAuthorizationReadinessState.INELIGIBLE,
            scope.canonical_digest, request.canonical_digest, missing, missing, missing, missing,
            side_effects.canonical_digest, ("trial_chain_invalid",), evaluation_time)
    if security_review is None:
        return RealDataAccessAuthorizationReadinessDecision(
            RealDataAccessAuthorizationReadinessState.NEEDS_TRIAL_SECURITY_REVIEW,
            scope.canonical_digest, request.canonical_digest, missing, missing, missing, missing,
            side_effects.canonical_digest, ("trial_security_review_required",), evaluation_time)
    if (not canonical_object_valid(security_review)
            or security_review.trial_request_digest != request.canonical_digest
            or security_review.trial_scope_digest != scope.canonical_digest
            or security_review.reviewer_id != roles.security_reviewer_id
            or security_review.result is not TrialReviewResult.APPROVED):
        return RealDataAccessAuthorizationReadinessDecision(
            RealDataAccessAuthorizationReadinessState.INELIGIBLE,
            scope.canonical_digest, request.canonical_digest,
            security_review.canonical_digest, missing, missing, missing,
            side_effects.canonical_digest, ("trial_security_review_invalid",), evaluation_time)
    if governance_review is None:
        return RealDataAccessAuthorizationReadinessDecision(
            RealDataAccessAuthorizationReadinessState.NEEDS_TRIAL_GOVERNANCE_REVIEW,
            scope.canonical_digest, request.canonical_digest,
            security_review.canonical_digest, missing, missing, missing,
            side_effects.canonical_digest, ("trial_governance_review_required",), evaluation_time)
    if (not canonical_object_valid(governance_review)
            or governance_review.trial_request_digest != request.canonical_digest
            or governance_review.reviewer_id != roles.governance_reviewer_id
            or governance_review.result is not TrialReviewResult.APPROVED):
        return RealDataAccessAuthorizationReadinessDecision(
            RealDataAccessAuthorizationReadinessState.INELIGIBLE,
            scope.canonical_digest, request.canonical_digest,
            security_review.canonical_digest, governance_review.canonical_digest,
            missing, missing, side_effects.canonical_digest,
            ("trial_governance_review_invalid",), evaluation_time)
    if approval is None:
        return RealDataAccessAuthorizationReadinessDecision(
            RealDataAccessAuthorizationReadinessState.NEEDS_TRIAL_APPROVAL,
            scope.canonical_digest, request.canonical_digest,
            security_review.canonical_digest, governance_review.canonical_digest,
            missing, missing, side_effects.canonical_digest,
            ("trial_approval_required",), evaluation_time)
    approval_valid = (canonical_object_valid(approval)
        and approval.trial_request_digest == request.canonical_digest
        and approval.security_review_digest == security_review.canonical_digest
        and approval.governance_review_digest == governance_review.canonical_digest
        and approval.approver_id == roles.trial_approver_id
        and approval.result is TrialApprovalResult.APPROVED)
    if not approval_valid:
        return RealDataAccessAuthorizationReadinessDecision(
            RealDataAccessAuthorizationReadinessState.INELIGIBLE,
            scope.canonical_digest, request.canonical_digest,
            security_review.canonical_digest, governance_review.canonical_digest,
            approval.canonical_digest, missing, side_effects.canonical_digest,
            ("trial_approval_invalid",), evaluation_time)
    if record is None:
        return RealDataAccessAuthorizationReadinessDecision(
            RealDataAccessAuthorizationReadinessState.NEEDS_TRIAL_APPROVAL,
            scope.canonical_digest, request.canonical_digest,
            security_review.canonical_digest, governance_review.canonical_digest,
            approval.canonical_digest, missing, side_effects.canonical_digest,
            ("approved_trial_record_required",), evaluation_time)
    record_valid = (canonical_object_valid(record)
        and record.trial_scope_digest == scope.canonical_digest
        and record.trial_request_digest == request.canonical_digest
        and record.security_review_digest == security_review.canonical_digest
        and record.governance_review_digest == governance_review.canonical_digest
        and record.approval_digest == approval.canonical_digest
        and record.lifecycle is TrialLifecycle.APPROVED
        and record.state is ApprovedTrialState.APPROVED_FOR_REAL_DATA_ACCESS_AUTHORIZATION_REVIEW
        and record.approved_at <= evaluation_time < record.expires_at
        and approval.approved_at <= record.approved_at
        and not record.actual_real_data_read)
    state = (RealDataAccessAuthorizationReadinessState.ELIGIBLE_FOR_REAL_DATA_ACCESS_AUTHORIZATION_REVIEW
             if record_valid else RealDataAccessAuthorizationReadinessState.INELIGIBLE)
    reasons = ("approved_trial_ready_for_separate_access_authorization_review",) \
        if record_valid else ("approved_trial_record_invalid",)
    return RealDataAccessAuthorizationReadinessDecision(
        state, scope.canonical_digest, request.canonical_digest,
        security_review.canonical_digest, governance_review.canonical_digest,
        approval.canonical_digest, record.canonical_digest, side_effects.canonical_digest,
        reasons, evaluation_time)


__all__ = [
    "MAX_TRIAL_READINESS_AGE", "ApprovedRealDataTrialRecord", "ApprovedTrialState",
    "RealDataAccessAuthorizationReadinessDecision",
    "RealDataAccessAuthorizationReadinessState", "RealDataTrialApprovalError",
    "TestOnlyRealDataTrialRegistry", "TrialApproval", "TrialApprovalRequest",
    "TrialApprovalResult", "TrialDataGovernanceReview", "TrialLifecycle",
    "TrialRegistryFault", "TrialRegistryReason", "TrialRegistryResult",
    "TrialReviewResult", "TrialRoleContext", "TrialSecurityReview",
    "TrialSideEffectAccounting", "evaluate_real_data_access_authorization_readiness",
    "validate_v023_trial_source_chain",
]
