from __future__ import annotations

from dataclasses import InitVar, dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum

from ragguard.local_rag_environment import EnvironmentApproval, EnvironmentApprovalResult
from ragguard.local_rag_execution import (
    ApprovedLocalRAGExecutionSession,
    SessionAuthorizationState,
    SessionLifecycle,
)
from ragguard.real_data_access import (
    RealDataAccessPolicy,
    RealDataAccessSelector,
    validate_real_data_access_selector_policy,
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
from ragguard.real_data_trial_approval import (
    ApprovedRealDataTrialRecord,
    ApprovedTrialState,
    TrialApproval,
    TrialApprovalRequest,
    TrialApprovalResult,
    TrialDataGovernanceReview,
    TrialLifecycle,
    TrialReviewResult,
    TrialSecurityReview,
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


MAX_ACCESS_REQUEST_AGE = timedelta(hours=1)
_AUTHORIZATION_RECORD_MARKER = object()
_ELIGIBLE_READINESS_MARKER = object()
_LIMITED_READ_EXECUTOR_MARKER = object()


class RealDataAccessAuthorizationError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class RealDataAccessReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class RealDataAccessApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RealDataAccessAuthorizationState(str, Enum):
    AUTHORIZED_FOR_LIMITED_READ_EXECUTION_REVIEW = (
        "authorized_for_limited_read_execution_review"
    )


class RealDataAccessAuthorizationLifecycle(str, Enum):
    AUTHORIZED = "authorized"
    EXPIRED = "expired"
    REVOKED = "revoked"
    EXHAUSTED = "exhausted"
    SUPERSEDED = "superseded"


class RealDataAccessRegistryReason(str, Enum):
    INVALID_CHAIN = "invalid_chain"
    POLICY_INVALID = "policy_invalid"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    GENERATION_MISMATCH = "generation_mismatch"
    PREDECESSOR_MISMATCH = "predecessor_mismatch"
    REPLAY = "replay"
    COMMIT_FAULT = "commit_fault"
    STATUS_INVALID = "status_invalid"
    USAGE_INVALID = "usage_invalid"


class RealDataAccessRegistryFault(str, Enum):
    NONE = "none"
    CANDIDATE_STATE = "candidate_state"
    BEFORE_SWAP = "before_swap"


class RealDataReadExecutionReadinessState(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_SECURITY_REVIEW = "needs_security_review"
    NEEDS_GOVERNANCE_REVIEW = "needs_governance_review"
    NEEDS_OPERATOR_ASSIGNMENT = "needs_operator_assignment"
    NEEDS_ACCESS_APPROVAL = "needs_access_approval"
    ELIGIBLE_FOR_LIMITED_REAL_DATA_READ_EXECUTION = (
        "eligible_for_limited_real_data_read_execution"
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
class RealDataAccessRoleContext(_Canonical):
    trial_requester_id: str
    trial_approver_id: str
    session_operator_id: str
    access_requester_id: str
    security_reviewer_id: str
    governance_reviewer_id: str
    real_data_operator_id: str
    access_approver_id: str

    def __post_init__(self) -> None:
        values = tuple(vars(self).values())
        if (not all(is_identifier(value) for value in values)
                or len(set(values)) != len(values)):
            raise RealDataAccessAuthorizationError("access_role_conflict")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {key: value for key, value in vars(self).items()
                if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataAccessRequest(_Canonical):
    access_request_id: str
    approved_trial_record_digest: str
    selector_digest: str
    access_policy_digest: str
    approved_session_digest: str
    environment_approval_digest: str
    requested_by: str
    requested_at: datetime
    expires_at: datetime
    purpose_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.access_request_id)
                or not is_identifier(self.requested_by)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))
                or not _is_utc(self.requested_at) or not _is_utc(self.expires_at)
                or self.expires_at <= self.requested_at):
            raise RealDataAccessAuthorizationError("access_request_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {key: canonical_datetime(value) if isinstance(value, datetime) else value
                for key, value in vars(self).items() if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataAccessSecurityReview(_Canonical):
    review_id: str
    access_request_digest: str
    selector_digest: str
    policy_digest: str
    approved_trial_digest: str
    reviewed_at: datetime
    reviewer_id: str
    result: RealDataAccessReviewResult
    findings_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.review_id) or not is_identifier(self.reviewer_id)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))
                or not _is_utc(self.reviewed_at)
                or not isinstance(self.result, RealDataAccessReviewResult)):
            raise RealDataAccessAuthorizationError("access_security_review_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {key: (canonical_datetime(value) if isinstance(value, datetime)
                      else value.value if isinstance(value, Enum) else value)
                for key, value in vars(self).items() if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataAccessGovernanceReview(_Canonical):
    review_id: str
    access_request_digest: str
    approved_trial_digest: str
    classification_digest: str
    retention_policy_digest: str
    logging_policy_digest: str
    persistence_policy_digest: str
    reviewed_at: datetime
    reviewer_id: str
    result: RealDataAccessReviewResult
    findings_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.review_id) or not is_identifier(self.reviewer_id)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))
                or not _is_utc(self.reviewed_at)
                or not isinstance(self.result, RealDataAccessReviewResult)):
            raise RealDataAccessAuthorizationError("access_governance_review_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {key: (canonical_datetime(value) if isinstance(value, datetime)
                      else value.value if isinstance(value, Enum) else value)
                for key, value in vars(self).items() if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataOperatorAssignment(_Canonical):
    assignment_id: str
    access_request_digest: str
    operator_id: str
    assigned_at: datetime
    expires_at: datetime
    operator_scope_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.assignment_id) or not is_identifier(self.operator_id)
                or not is_digest(self.access_request_digest)
                or not is_digest(self.operator_scope_digest)
                or not _is_utc(self.assigned_at) or not _is_utc(self.expires_at)
                or self.expires_at <= self.assigned_at):
            raise RealDataAccessAuthorizationError("operator_assignment_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {key: canonical_datetime(value) if isinstance(value, datetime) else value
                for key, value in vars(self).items() if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def access_authorized(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class RealDataAccessApproval(_Canonical):
    approval_id: str
    access_request_digest: str
    security_review_digest: str
    governance_review_digest: str
    operator_assignment_digest: str
    approver_id: str
    approved_at: datetime
    expires_at: datetime
    result: RealDataAccessApprovalResult

    def __post_init__(self) -> None:
        if (not is_identifier(self.approval_id) or not is_identifier(self.approver_id)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))
                or not _is_utc(self.approved_at) or not _is_utc(self.expires_at)
                or self.expires_at <= self.approved_at
                or not isinstance(self.result, RealDataAccessApprovalResult)):
            raise RealDataAccessAuthorizationError("access_approval_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {key: (canonical_datetime(value) if isinstance(value, datetime)
                      else value.value if isinstance(value, Enum) else value)
                for key, value in vars(self).items() if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataAccessAuthorizationRecord(_Canonical):
    authorization_record_id: str
    access_request_digest: str
    selector_digest: str
    policy_digest: str
    approved_trial_record_digest: str
    security_review_digest: str
    governance_review_digest: str
    operator_assignment_digest: str
    approval_digest: str
    operator_id: str
    authorization_generation: int
    predecessor_authorization_digest: str | None
    allowed_read_count: int
    remaining_read_count: int
    issued_at: datetime
    expires_at: datetime
    state: RealDataAccessAuthorizationState = (
        RealDataAccessAuthorizationState.AUTHORIZED_FOR_LIMITED_READ_EXECUTION_REVIEW)
    lifecycle: RealDataAccessAuthorizationLifecycle = (
        RealDataAccessAuthorizationLifecycle.AUTHORIZED)
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        digest_values = (
            self.access_request_digest, self.selector_digest, self.policy_digest,
            self.approved_trial_record_digest, self.security_review_digest,
            self.governance_review_digest, self.operator_assignment_digest,
            self.approval_digest,
        )
        if (not is_identifier(self.authorization_record_id)
                or not is_identifier(self.operator_id)
                or not all(is_digest(value) for value in digest_values)
                or (self.predecessor_authorization_digest is not None
                    and not is_digest(self.predecessor_authorization_digest))
                or type(self.authorization_generation) is not int
                or self.authorization_generation < 1
                or type(self.allowed_read_count) is not int
                or self.allowed_read_count < 1
                or type(self.remaining_read_count) is not int
                or not 0 <= self.remaining_read_count <= self.allowed_read_count
                or not _is_utc(self.issued_at) or not _is_utc(self.expires_at)
                or self.expires_at <= self.issued_at
                or not isinstance(self.state, RealDataAccessAuthorizationState)
                or not isinstance(self.lifecycle, RealDataAccessAuthorizationLifecycle)
                or (self.lifecycle is RealDataAccessAuthorizationLifecycle.AUTHORIZED
                    and self.remaining_read_count < 1)
                or (self.lifecycle is RealDataAccessAuthorizationLifecycle.EXHAUSTED
                    and self.remaining_read_count != 0)
                or _marker is not _AUTHORIZATION_RECORD_MARKER):
            raise RealDataAccessAuthorizationError("authorization_record_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {key: (canonical_datetime(value) if isinstance(value, datetime)
                      else value.value if isinstance(value, Enum) else value)
                for key, value in vars(self).items() if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def actual_real_data_read_executed(self) -> bool:
        return False

    @property
    def persistence_authorized(self) -> bool:
        return False

    @property
    def runtime_activation_authorized(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class AuthorizationUsageCounterContract(_Canonical):
    authorization_record_digest: str
    allowed_read_count: int
    remaining_read_count: int
    opaque_usage_digest: str
    executor_contract_digest: str

    def __post_init__(self) -> None:
        if (not is_digest(self.authorization_record_digest)
                or not is_digest(self.opaque_usage_digest)
                or not is_digest(self.executor_contract_digest)
                or type(self.allowed_read_count) is not int
                or self.allowed_read_count < 1
                or type(self.remaining_read_count) is not int
                or not 0 <= self.remaining_read_count <= self.allowed_read_count):
            raise RealDataAccessAuthorizationError("usage_counter_contract_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {key: value for key, value in vars(self).items()
                if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataAccessSideEffectAccounting(_Canonical):
    actual_file_open_count: int = 0
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
            raise RealDataAccessAuthorizationError("access_side_effect_accounting_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, int]:
        return {key: value for key, value in vars(self).items()
                if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def all_zero(self) -> bool:
        return all(value == 0 for value in self._payload().values())


def validate_v024_access_source_chain(
    approved_trial: ApprovedRealDataTrialRecord,
    trial_scope: RealDataTrialScope,
    classification_policy: RealDataClassificationPolicy,
    stage_policy: TrialStagePolicy,
    retention_policy: TrialRetentionPolicy,
    logging_policy: TrialLoggingPolicy,
    cache_policy: TrialCachePolicy,
    export_policy: TrialExportPolicy,
    persistence_policy: TrialPersistencePolicy,
    trial_request: TrialApprovalRequest,
    trial_security_review: TrialSecurityReview,
    trial_governance_review: TrialDataGovernanceReview,
    trial_approval: TrialApproval,
    environment_approval: EnvironmentApproval,
    approved_session: ApprovedLocalRAGExecutionSession,
    *,
    evaluation_time: datetime,
) -> tuple[str, ...]:
    reasons: list[str] = []
    objects = (
        approved_trial, trial_scope, classification_policy, stage_policy,
        retention_policy, logging_policy, cache_policy, export_policy,
        persistence_policy, trial_request, trial_security_review,
        trial_governance_review, trial_approval, environment_approval,
        approved_session,
    )
    if not all(canonical_object_valid(value) for value in objects):
        reasons.append("forged_v024_access_source_chain")
    if validate_trial_scope_policies(
            trial_scope, classification_policy, stage_policy, retention_policy,
            logging_policy, cache_policy, export_policy, persistence_policy):
        reasons.append("v024_access_source_policy_invalid")
    exact = (
        approved_trial.trial_scope_digest == trial_scope.canonical_digest,
        approved_trial.trial_request_digest == trial_request.canonical_digest,
        approved_trial.security_review_digest == trial_security_review.canonical_digest,
        approved_trial.governance_review_digest == trial_governance_review.canonical_digest,
        approved_trial.approval_digest == trial_approval.canonical_digest,
        approved_trial.approved_session_digest == approved_session.canonical_digest,
        approved_trial.environment_approval_digest == environment_approval.canonical_digest,
        trial_scope.approved_session_digest == approved_session.canonical_digest,
        trial_scope.environment_approval_digest == environment_approval.canonical_digest,
        trial_request.trial_scope_digest == trial_scope.canonical_digest,
        trial_request.approved_session_digest == approved_session.canonical_digest,
        trial_request.environment_approval_digest == environment_approval.canonical_digest,
        trial_security_review.trial_request_digest == trial_request.canonical_digest,
        trial_security_review.trial_scope_digest == trial_scope.canonical_digest,
        trial_governance_review.trial_request_digest == trial_request.canonical_digest,
        trial_governance_review.classification_policy_digest
            == classification_policy.canonical_digest,
        trial_governance_review.retention_policy_digest == retention_policy.canonical_digest,
        trial_governance_review.logging_policy_digest == logging_policy.canonical_digest,
        trial_governance_review.persistence_policy_digest == persistence_policy.canonical_digest,
        trial_approval.trial_request_digest == trial_request.canonical_digest,
        trial_approval.security_review_digest == trial_security_review.canonical_digest,
        trial_approval.governance_review_digest == trial_governance_review.canonical_digest,
    )
    if not all(exact):
        reasons.append("v024_access_source_binding_mismatch")
    if (environment_approval.result is not EnvironmentApprovalResult.APPROVED
            or approved_session.state is not (
                SessionAuthorizationState.APPROVED_FOR_CONTROLLED_EXECUTION)
            or approved_session.lifecycle is not SessionLifecycle.APPROVED
            or trial_security_review.result is not TrialReviewResult.APPROVED
            or trial_governance_review.result is not TrialReviewResult.APPROVED
            or trial_approval.result is not TrialApprovalResult.APPROVED
            or approved_trial.state is not (
                ApprovedTrialState.APPROVED_FOR_REAL_DATA_ACCESS_AUTHORIZATION_REVIEW)
            or approved_trial.lifecycle is not TrialLifecycle.APPROVED):
        reasons.append("v024_access_source_not_approved")
    temporal = (
        trial_request.requested_at, trial_security_review.reviewed_at,
        trial_governance_review.reviewed_at, trial_approval.approved_at,
        approved_trial.approved_at, approved_trial.expires_at, evaluation_time,
    )
    if (not all(_is_utc(value) for value in temporal)
            or not (trial_scope.created_at <= trial_request.requested_at
                    < trial_security_review.reviewed_at
                    < trial_governance_review.reviewed_at < trial_approval.approved_at
                    <= approved_trial.approved_at <= evaluation_time
                    < approved_trial.expires_at <= trial_scope.expires_at)
            or evaluation_time >= trial_request.expires_at
            or evaluation_time >= trial_approval.expires_at
            or evaluation_time >= approved_session.expires_at
            or approved_trial.actual_real_data_read):
        reasons.append("v024_access_source_temporal_invalid")
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True)
class RealDataAccessRegistryResult:
    applied: bool
    reasons: tuple[RealDataAccessRegistryReason, ...]
    record: RealDataAccessAuthorizationRecord | None
    usage_contract: AuthorizationUsageCounterContract | None
    write_count: int
    mutation_count: int
    event_count: int


@dataclass(frozen=True)
class _AccessRegistryState:
    records: tuple[RealDataAccessAuthorizationRecord, ...] = ()
    used_request_digests: frozenset[str] = frozenset()
    used_security_review_digests: frozenset[str] = frozenset()
    used_governance_review_digests: frozenset[str] = frozenset()
    used_operator_assignment_digests: frozenset[str] = frozenset()
    used_approval_digests: frozenset[str] = frozenset()
    used_record_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class TestOnlyRealDataAccessAuthorizationRegistry:
    __test__ = False

    def __init__(self) -> None:
        self._state = _AccessRegistryState()

    @property
    def records(self) -> tuple[RealDataAccessAuthorizationRecord, ...]:
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
        return (
            self._state.used_request_digests,
            self._state.used_security_review_digests,
            self._state.used_governance_review_digests,
            self._state.used_operator_assignment_digests,
            self._state.used_approval_digests,
            self._state.used_record_digests,
        )

    def authorize(
        self,
        *,
        authorization_record_id: str,
        selector: RealDataAccessSelector,
        access_policy: RealDataAccessPolicy,
        request: RealDataAccessRequest,
        security_review: RealDataAccessSecurityReview | None,
        governance_review: RealDataAccessGovernanceReview | None,
        operator_assignment: RealDataOperatorAssignment | None,
        approval: RealDataAccessApproval | None,
        roles: RealDataAccessRoleContext,
        approved_trial: ApprovedRealDataTrialRecord,
        trial_scope: RealDataTrialScope,
        classification_policy: RealDataClassificationPolicy,
        stage_policy: TrialStagePolicy,
        retention_policy: TrialRetentionPolicy,
        logging_policy: TrialLoggingPolicy,
        cache_policy: TrialCachePolicy,
        export_policy: TrialExportPolicy,
        persistence_policy: TrialPersistencePolicy,
        trial_request: TrialApprovalRequest,
        trial_security_review: TrialSecurityReview,
        trial_governance_review: TrialDataGovernanceReview,
        trial_approval: TrialApproval,
        environment_approval: EnvironmentApproval,
        approved_session: ApprovedLocalRAGExecutionSession,
        authorization_generation: int,
        predecessor_authorization_digest: str | None,
        issued_at: datetime,
        record_expires_at: datetime,
        fault: RealDataAccessRegistryFault = RealDataAccessRegistryFault.NONE,
    ) -> RealDataAccessRegistryResult:
        reasons: list[RealDataAccessRegistryReason] = []
        if (not isinstance(security_review, RealDataAccessSecurityReview)
                or not isinstance(governance_review, RealDataAccessGovernanceReview)
                or not isinstance(operator_assignment, RealDataOperatorAssignment)
                or not isinstance(approval, RealDataAccessApproval)
                or not isinstance(fault, RealDataAccessRegistryFault)):
            return self._result(False, (RealDataAccessRegistryReason.INVALID_CHAIN,), None, None)
        objects = (
            selector, access_policy, request, security_review, governance_review,
            operator_assignment, approval, roles, approved_trial, trial_scope,
            classification_policy, stage_policy, retention_policy, logging_policy,
            cache_policy, export_policy, persistence_policy, trial_request,
            trial_security_review, trial_governance_review, trial_approval,
            environment_approval, approved_session,
        )
        if not all(canonical_object_valid(value) for value in objects):
            reasons.append(RealDataAccessRegistryReason.INVALID_CHAIN)
        if validate_v024_access_source_chain(
                approved_trial, trial_scope, classification_policy, stage_policy,
                retention_policy, logging_policy, cache_policy, export_policy,
                persistence_policy, trial_request, trial_security_review,
                trial_governance_review, trial_approval, environment_approval,
                approved_session, evaluation_time=issued_at):
            reasons.append(RealDataAccessRegistryReason.INVALID_CHAIN)
        if validate_real_data_access_selector_policy(
                selector, access_policy, approved_trial, trial_scope,
                classification_policy, stage_policy, retention_policy, logging_policy,
                cache_policy, export_policy, persistence_policy):
            reasons.append(RealDataAccessRegistryReason.POLICY_INVALID)
        exact = (
            selector.purpose_digest == request.purpose_digest,
            request.approved_trial_record_digest == approved_trial.canonical_digest,
            request.selector_digest == selector.canonical_digest,
            request.access_policy_digest == access_policy.canonical_digest,
            request.approved_session_digest == approved_session.canonical_digest,
            request.environment_approval_digest == environment_approval.canonical_digest,
            security_review.access_request_digest == request.canonical_digest,
            security_review.selector_digest == selector.canonical_digest,
            security_review.policy_digest == access_policy.canonical_digest,
            security_review.approved_trial_digest == approved_trial.canonical_digest,
            governance_review.access_request_digest == request.canonical_digest,
            governance_review.approved_trial_digest == approved_trial.canonical_digest,
            governance_review.classification_digest == classification_policy.canonical_digest,
            governance_review.retention_policy_digest
                == access_policy.retention_policy_digest,
            governance_review.logging_policy_digest == access_policy.logging_policy_digest,
            governance_review.persistence_policy_digest
                == access_policy.persistence_policy_digest,
            operator_assignment.access_request_digest == request.canonical_digest,
            operator_assignment.operator_scope_digest == selector.canonical_digest,
            approval.access_request_digest == request.canonical_digest,
            approval.security_review_digest == security_review.canonical_digest,
            approval.governance_review_digest == governance_review.canonical_digest,
            approval.operator_assignment_digest == operator_assignment.canonical_digest,
            security_review.result is RealDataAccessReviewResult.APPROVED,
            governance_review.result is RealDataAccessReviewResult.APPROVED,
            approval.result is RealDataAccessApprovalResult.APPROVED,
        )
        if not all(exact):
            reasons.append(RealDataAccessRegistryReason.INVALID_CHAIN)
        role_values = (
            trial_request.requested_by, trial_approval.approver_id,
            approved_session.operator_id, request.requested_by,
            security_review.reviewer_id, governance_review.reviewer_id,
            operator_assignment.operator_id, approval.approver_id,
        )
        if (trial_request.requested_by != roles.trial_requester_id
                or trial_approval.approver_id != roles.trial_approver_id
                or approved_session.operator_id != roles.session_operator_id
                or request.requested_by != roles.access_requester_id
                or security_review.reviewer_id != roles.security_reviewer_id
                or governance_review.reviewer_id != roles.governance_reviewer_id
                or operator_assignment.operator_id != roles.real_data_operator_id
                or approval.approver_id != roles.access_approver_id
                or len(set(role_values)) != len(role_values)):
            reasons.append(RealDataAccessRegistryReason.ROLE_CONFLICT)
        expected_generation = len(self.records) + 1
        expected_predecessor = self.records[-1].canonical_digest if self.records else None
        if authorization_generation != expected_generation:
            reasons.append(RealDataAccessRegistryReason.GENERATION_MISMATCH)
        if predecessor_authorization_digest != expected_predecessor:
            reasons.append(RealDataAccessRegistryReason.PREDECESSOR_MISMATCH)
        if self.records and self.records[-1].lifecycle is not (
                RealDataAccessAuthorizationLifecycle.AUTHORIZED):
            reasons.append(RealDataAccessRegistryReason.STATUS_INVALID)
        replay = (
            (request.canonical_digest, self._state.used_request_digests),
            (security_review.canonical_digest, self._state.used_security_review_digests),
            (governance_review.canonical_digest,
             self._state.used_governance_review_digests),
            (operator_assignment.canonical_digest,
             self._state.used_operator_assignment_digests),
            (approval.canonical_digest, self._state.used_approval_digests),
        )
        if any(value in used for value, used in replay):
            reasons.append(RealDataAccessRegistryReason.REPLAY)
        temporal = (
            request.requested_at, request.expires_at, security_review.reviewed_at,
            governance_review.reviewed_at, operator_assignment.assigned_at,
            operator_assignment.expires_at, approval.approved_at,
            approval.expires_at, issued_at, record_expires_at,
        )
        latest_expiry = min(
            request.expires_at, operator_assignment.expires_at, approval.expires_at,
            approved_trial.expires_at, approved_session.expires_at,
        )
        if (not all(_is_utc(value) for value in temporal)
                or not (approved_trial.approved_at < request.requested_at
                        < security_review.reviewed_at < governance_review.reviewed_at
                        < operator_assignment.assigned_at < approval.approved_at
                        <= issued_at < record_expires_at <= latest_expiry)
                or issued_at - request.requested_at > MAX_ACCESS_REQUEST_AGE):
            reasons.append(RealDataAccessRegistryReason.TEMPORAL_INVALID)
        if (access_policy.allowed_read_count < 1
                or access_policy.allowed_read_count != 1):
            reasons.append(RealDataAccessRegistryReason.USAGE_INVALID)
        if not is_identifier(authorization_record_id):
            reasons.append(RealDataAccessRegistryReason.INVALID_CHAIN)
        if reasons:
            return self._result(False, tuple(dict.fromkeys(reasons)), None, None)
        try:
            if fault is RealDataAccessRegistryFault.CANDIDATE_STATE:
                raise RuntimeError
            record = RealDataAccessAuthorizationRecord(
                authorization_record_id, request.canonical_digest,
                selector.canonical_digest, access_policy.canonical_digest,
                approved_trial.canonical_digest, security_review.canonical_digest,
                governance_review.canonical_digest, operator_assignment.canonical_digest,
                approval.canonical_digest, operator_assignment.operator_id,
                authorization_generation, predecessor_authorization_digest,
                access_policy.allowed_read_count, access_policy.allowed_read_count,
                issued_at, record_expires_at, _marker=_AUTHORIZATION_RECORD_MARKER)
            if record.canonical_digest in self._state.used_record_digests:
                return self._result(
                    False, (RealDataAccessRegistryReason.REPLAY,), None, None)
            usage = AuthorizationUsageCounterContract(
                record.canonical_digest, record.allowed_read_count,
                record.remaining_read_count,
                digest(canonical_json({"authorization": record.canonical_digest,
                                       "usage": "opaque"})),
                digest("future-v0.26-real-data-read-executor-only"))
            candidate = replace(
                self._state,
                records=self.records + (record,),
                used_request_digests=self._state.used_request_digests
                    | {request.canonical_digest},
                used_security_review_digests=self._state.used_security_review_digests
                    | {security_review.canonical_digest},
                used_governance_review_digests=self._state.used_governance_review_digests
                    | {governance_review.canonical_digest},
                used_operator_assignment_digests=
                    self._state.used_operator_assignment_digests
                    | {operator_assignment.canonical_digest},
                used_approval_digests=self._state.used_approval_digests
                    | {approval.canonical_digest},
                used_record_digests=self._state.used_record_digests
                    | {record.canonical_digest},
                write_count=self.write_count + 1,
                mutation_count=self.mutation_count + 1,
                event_count=self.event_count + 1,
            )
            if fault is RealDataAccessRegistryFault.BEFORE_SWAP:
                raise RuntimeError
            self._state = candidate
            return self._result(True, (), record, usage)
        except RuntimeError:
            return self._result(
                False, (RealDataAccessRegistryReason.COMMIT_FAULT,), None, None)

    def transition(
        self,
        *,
        source_record: RealDataAccessAuthorizationRecord,
        new_record_id: str,
        lifecycle: RealDataAccessAuthorizationLifecycle,
        transitioned_at: datetime,
        fault: RealDataAccessRegistryFault = RealDataAccessRegistryFault.NONE,
    ) -> RealDataAccessRegistryResult:
        allowed = {
            RealDataAccessAuthorizationLifecycle.EXPIRED,
            RealDataAccessAuthorizationLifecycle.REVOKED,
            RealDataAccessAuthorizationLifecycle.SUPERSEDED,
        }
        temporal_valid = (
            lifecycle is RealDataAccessAuthorizationLifecycle.EXPIRED
            and transitioned_at >= source_record.expires_at
        ) or (
            lifecycle in {
                RealDataAccessAuthorizationLifecycle.REVOKED,
                RealDataAccessAuthorizationLifecycle.SUPERSEDED,
            }
            and source_record.issued_at < transitioned_at < source_record.expires_at
        )
        if (not self.records or not canonical_object_valid(source_record)
                or source_record.canonical_digest != self.records[-1].canonical_digest
                or source_record.lifecycle is not (
                    RealDataAccessAuthorizationLifecycle.AUTHORIZED)
                or lifecycle not in allowed or not _is_utc(transitioned_at)
                or not temporal_valid or not is_identifier(new_record_id)):
            return self._result(
                False, (RealDataAccessRegistryReason.STATUS_INVALID,), None, None)
        if fault is not RealDataAccessRegistryFault.NONE:
            return self._result(
                False, (RealDataAccessRegistryReason.COMMIT_FAULT,), None, None)
        transitioned = RealDataAccessAuthorizationRecord(
            new_record_id, source_record.access_request_digest,
            source_record.selector_digest, source_record.policy_digest,
            source_record.approved_trial_record_digest,
            source_record.security_review_digest,
            source_record.governance_review_digest,
            source_record.operator_assignment_digest, source_record.approval_digest,
            source_record.operator_id, source_record.authorization_generation + 1,
            source_record.canonical_digest, source_record.allowed_read_count,
            source_record.remaining_read_count, source_record.issued_at,
            source_record.expires_at, source_record.state, lifecycle,
            _marker=_AUTHORIZATION_RECORD_MARKER)
        candidate = replace(
            self._state,
            records=self.records + (transitioned,),
            used_record_digests=self._state.used_record_digests
                | {transitioned.canonical_digest},
            write_count=self.write_count + 1,
            mutation_count=self.mutation_count + 1,
            event_count=self.event_count + 1,
        )
        self._state = candidate
        return self._result(True, (), transitioned, None)

    def _result(self, applied, reasons, record, usage) -> RealDataAccessRegistryResult:
        return RealDataAccessRegistryResult(
            applied, reasons, record, usage,
            self.write_count, self.mutation_count, self.event_count)


@dataclass(frozen=True, repr=False)
class RealDataReadExecutionReadinessDecision(_Canonical):
    state: RealDataReadExecutionReadinessState
    access_request_digest: str
    selector_digest: str
    policy_digest: str
    security_review_digest: str
    governance_review_digest: str
    operator_assignment_digest: str
    access_approval_digest: str
    authorization_record_digest: str
    usage_contract_digest: str
    side_effect_accounting_digest: str
    reason_codes: tuple[str, ...]
    evaluated_at: datetime
    actual_real_data_read_executed: bool = field(init=False, default=False)
    real_data_use_authorized: bool = field(init=False, default=False)
    persistence_authorized: bool = field(init=False, default=False)
    runtime_activation_authorized: bool = field(init=False, default=False)
    production_active: bool = field(init=False, default=False)
    actual_file_open_count: int = field(init=False, default=0)
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
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        digest_values = (
            self.access_request_digest, self.selector_digest, self.policy_digest,
            self.security_review_digest, self.governance_review_digest,
            self.operator_assignment_digest, self.access_approval_digest,
            self.authorization_record_digest, self.usage_contract_digest,
            self.side_effect_accounting_digest,
        )
        if (not isinstance(self.state, RealDataReadExecutionReadinessState)
                or not all(is_digest(value) for value in digest_values)
                or not self.reason_codes
                or not all(is_identifier(value) for value in self.reason_codes)
                or not _is_utc(self.evaluated_at)
                or (self.state is (
                    RealDataReadExecutionReadinessState.
                    ELIGIBLE_FOR_LIMITED_REAL_DATA_READ_EXECUTION)
                    and _marker is not _ELIGIBLE_READINESS_MARKER)):
            raise RealDataAccessAuthorizationError("read_execution_readiness_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        counts = {key: value for key, value in vars(self).items()
                  if key.endswith("_count")}
        return {
            "access_approval_digest": self.access_approval_digest,
            "access_request_digest": self.access_request_digest,
            "actual_real_data_read_executed": self.actual_real_data_read_executed,
            "authorization_record_digest": self.authorization_record_digest,
            "evaluated_at": canonical_datetime(self.evaluated_at),
            "external_side_effect_counts": counts,
            "governance_review_digest": self.governance_review_digest,
            "operator_assignment_digest": self.operator_assignment_digest,
            "policy_digest": self.policy_digest,
            "persistence_authorized": self.persistence_authorized,
            "production_active": self.production_active,
            "reason_codes": list(self.reason_codes),
            "real_data_use_authorized": self.real_data_use_authorized,
            "runtime_activation_authorized": self.runtime_activation_authorized,
            "security_review_digest": self.security_review_digest,
            "selector_digest": self.selector_digest,
            "side_effect_accounting_digest": self.side_effect_accounting_digest,
            "state": self.state.value,
            "usage_contract_digest": self.usage_contract_digest,
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


def evaluate_real_data_read_execution_readiness(
    selector: RealDataAccessSelector,
    policy: RealDataAccessPolicy,
    request: RealDataAccessRequest,
    security_review: RealDataAccessSecurityReview | None,
    governance_review: RealDataAccessGovernanceReview | None,
    operator_assignment: RealDataOperatorAssignment | None,
    approval: RealDataAccessApproval | None,
    record: RealDataAccessAuthorizationRecord | None,
    usage_contract: AuthorizationUsageCounterContract | None,
    roles: RealDataAccessRoleContext,
    side_effects: RealDataAccessSideEffectAccounting,
    *,
    evaluation_time: datetime,
) -> RealDataReadExecutionReadinessDecision:
    if not _is_utc(evaluation_time):
        raise RealDataAccessAuthorizationError("read_execution_readiness_time_invalid")
    missing = digest("missing")

    def decision(state, reasons, security=missing, governance=missing,
                 assignment=missing, access_approval=missing, authorization=missing,
                 usage=missing, *, eligible=False):
        return RealDataReadExecutionReadinessDecision(
            state, request.canonical_digest, selector.canonical_digest,
            policy.canonical_digest, security, governance, assignment,
            access_approval, authorization, usage, side_effects.canonical_digest,
            reasons, evaluation_time,
            _marker=_ELIGIBLE_READINESS_MARKER if eligible else None)

    base = (selector, policy, request, roles, side_effects)
    if (not all(canonical_object_valid(value) for value in base)
            or request.selector_digest != selector.canonical_digest
            or request.access_policy_digest != policy.canonical_digest
            or request.purpose_digest != selector.purpose_digest
            or request.requested_by != roles.access_requester_id
            or not side_effects.all_zero
            or not request.requested_at <= evaluation_time < request.expires_at):
        return decision(RealDataReadExecutionReadinessState.INELIGIBLE,
                        ("access_request_chain_invalid",))
    if security_review is None:
        return decision(RealDataReadExecutionReadinessState.NEEDS_SECURITY_REVIEW,
                        ("access_security_review_required",))
    if (not canonical_object_valid(security_review)
            or security_review.access_request_digest != request.canonical_digest
            or security_review.selector_digest != selector.canonical_digest
            or security_review.policy_digest != policy.canonical_digest
            or security_review.reviewer_id != roles.security_reviewer_id
            or security_review.result is not RealDataAccessReviewResult.APPROVED):
        return decision(RealDataReadExecutionReadinessState.INELIGIBLE,
                        ("access_security_review_invalid",),
                        security_review.canonical_digest)
    if governance_review is None:
        return decision(RealDataReadExecutionReadinessState.NEEDS_GOVERNANCE_REVIEW,
                        ("access_governance_review_required",),
                        security_review.canonical_digest)
    if (not canonical_object_valid(governance_review)
            or governance_review.access_request_digest != request.canonical_digest
            or governance_review.reviewer_id != roles.governance_reviewer_id
            or governance_review.result is not RealDataAccessReviewResult.APPROVED):
        return decision(RealDataReadExecutionReadinessState.INELIGIBLE,
                        ("access_governance_review_invalid",),
                        security_review.canonical_digest,
                        governance_review.canonical_digest)
    if operator_assignment is None:
        return decision(RealDataReadExecutionReadinessState.NEEDS_OPERATOR_ASSIGNMENT,
                        ("operator_assignment_required",),
                        security_review.canonical_digest,
                        governance_review.canonical_digest)
    if (not canonical_object_valid(operator_assignment)
            or operator_assignment.access_request_digest != request.canonical_digest
            or operator_assignment.operator_scope_digest != selector.canonical_digest
            or operator_assignment.operator_id != roles.real_data_operator_id
            or not operator_assignment.assigned_at <= evaluation_time
                < operator_assignment.expires_at):
        return decision(RealDataReadExecutionReadinessState.INELIGIBLE,
                        ("operator_assignment_invalid",),
                        security_review.canonical_digest,
                        governance_review.canonical_digest,
                        operator_assignment.canonical_digest)
    if approval is None:
        return decision(RealDataReadExecutionReadinessState.NEEDS_ACCESS_APPROVAL,
                        ("access_approval_required",),
                        security_review.canonical_digest,
                        governance_review.canonical_digest,
                        operator_assignment.canonical_digest)
    approval_valid = (
        canonical_object_valid(approval)
        and approval.access_request_digest == request.canonical_digest
        and approval.security_review_digest == security_review.canonical_digest
        and approval.governance_review_digest == governance_review.canonical_digest
        and approval.operator_assignment_digest == operator_assignment.canonical_digest
        and approval.approver_id == roles.access_approver_id
        and approval.result is RealDataAccessApprovalResult.APPROVED
        and approval.approved_at <= evaluation_time < approval.expires_at
    )
    if not approval_valid:
        return decision(RealDataReadExecutionReadinessState.INELIGIBLE,
                        ("access_approval_invalid",),
                        security_review.canonical_digest,
                        governance_review.canonical_digest,
                        operator_assignment.canonical_digest,
                        approval.canonical_digest)
    if record is None:
        return decision(RealDataReadExecutionReadinessState.NEEDS_ACCESS_APPROVAL,
                        ("authorization_record_required",),
                        security_review.canonical_digest,
                        governance_review.canonical_digest,
                        operator_assignment.canonical_digest,
                        approval.canonical_digest)
    if usage_contract is None:
        return decision(RealDataReadExecutionReadinessState.INELIGIBLE,
                        ("authorization_usage_contract_required",),
                        security_review.canonical_digest,
                        governance_review.canonical_digest,
                        operator_assignment.canonical_digest,
                        approval.canonical_digest, record.canonical_digest)
    record_valid = (
        canonical_object_valid(record)
        and canonical_object_valid(usage_contract)
        and record.access_request_digest == request.canonical_digest
        and record.selector_digest == selector.canonical_digest
        and record.policy_digest == policy.canonical_digest
        and record.security_review_digest == security_review.canonical_digest
        and record.governance_review_digest == governance_review.canonical_digest
        and record.operator_assignment_digest == operator_assignment.canonical_digest
        and record.approval_digest == approval.canonical_digest
        and record.operator_id == operator_assignment.operator_id
        and record.state is (
            RealDataAccessAuthorizationState.AUTHORIZED_FOR_LIMITED_READ_EXECUTION_REVIEW)
        and record.lifecycle is RealDataAccessAuthorizationLifecycle.AUTHORIZED
        and record.allowed_read_count == policy.allowed_read_count
        and record.remaining_read_count > 0
        and record.issued_at <= evaluation_time < record.expires_at
        and usage_contract.authorization_record_digest == record.canonical_digest
        and usage_contract.allowed_read_count == record.allowed_read_count
        and usage_contract.remaining_read_count == record.remaining_read_count
        and not record.actual_real_data_read_executed
        and not record.persistence_authorized
        and not record.runtime_activation_authorized
    )
    if not record_valid:
        return decision(RealDataReadExecutionReadinessState.INELIGIBLE,
                        ("authorization_record_invalid",),
                        security_review.canonical_digest,
                        governance_review.canonical_digest,
                        operator_assignment.canonical_digest,
                        approval.canonical_digest, record.canonical_digest,
                        usage_contract.canonical_digest)
    return decision(
        RealDataReadExecutionReadinessState.
        ELIGIBLE_FOR_LIMITED_REAL_DATA_READ_EXECUTION,
        ("limited_read_ready_for_separate_execution_boundary",),
        security_review.canonical_digest, governance_review.canonical_digest,
        operator_assignment.canonical_digest, approval.canonical_digest,
        record.canonical_digest, usage_contract.canonical_digest, eligible=True)


def _consume_authorization_usage_for_verified_read(
    record: RealDataAccessAuthorizationRecord,
    usage_contract: AuthorizationUsageCounterContract,
    *,
    executor_marker: object,
) -> tuple[RealDataAccessAuthorizationRecord, AuthorizationUsageCounterContract]:
    """Private v0.26 capability; no public decrement, reset, or refill surface."""
    if (
        executor_marker is not _LIMITED_READ_EXECUTOR_MARKER
        or not canonical_object_valid(record)
        or not canonical_object_valid(usage_contract)
        or record.lifecycle is not RealDataAccessAuthorizationLifecycle.AUTHORIZED
        or record.remaining_read_count != 1
        or record.allowed_read_count != 1
        or usage_contract.authorization_record_digest != record.canonical_digest
        or usage_contract.allowed_read_count != record.allowed_read_count
        or usage_contract.remaining_read_count != record.remaining_read_count
    ):
        raise RealDataAccessAuthorizationError("verified_read_usage_consume_invalid")
    exhausted_record = RealDataAccessAuthorizationRecord(
        record.authorization_record_id,
        record.access_request_digest,
        record.selector_digest,
        record.policy_digest,
        record.approved_trial_record_digest,
        record.security_review_digest,
        record.governance_review_digest,
        record.operator_assignment_digest,
        record.approval_digest,
        record.operator_id,
        record.authorization_generation + 1,
        record.canonical_digest,
        record.allowed_read_count,
        0,
        record.issued_at,
        record.expires_at,
        record.state,
        RealDataAccessAuthorizationLifecycle.EXHAUSTED,
        _marker=_AUTHORIZATION_RECORD_MARKER,
    )
    consumed_usage = AuthorizationUsageCounterContract(
        exhausted_record.canonical_digest,
        record.allowed_read_count,
        0,
        digest(
            canonical_json(
                {
                    "authorization": exhausted_record.canonical_digest,
                    "previous_authorization": record.canonical_digest,
                    "previous_usage": usage_contract.canonical_digest,
                    "remaining_read_count": 0,
                }
            )
        ),
        digest("v0.26-limited-real-data-read-executor-only"),
    )
    return exhausted_record, consumed_usage


__all__ = [
    "MAX_ACCESS_REQUEST_AGE", "AuthorizationUsageCounterContract",
    "RealDataAccessApproval", "RealDataAccessApprovalResult",
    "RealDataAccessAuthorizationError", "RealDataAccessAuthorizationLifecycle",
    "RealDataAccessAuthorizationRecord", "RealDataAccessAuthorizationState",
    "RealDataAccessGovernanceReview", "RealDataAccessRegistryFault",
    "RealDataAccessRegistryReason", "RealDataAccessRegistryResult",
    "RealDataAccessRequest", "RealDataAccessReviewResult",
    "RealDataAccessRoleContext", "RealDataAccessSecurityReview",
    "RealDataAccessSideEffectAccounting", "RealDataOperatorAssignment",
    "RealDataReadExecutionReadinessDecision", "RealDataReadExecutionReadinessState",
    "TestOnlyRealDataAccessAuthorizationRegistry",
    "evaluate_real_data_read_execution_readiness", "validate_v024_access_source_chain",
]
