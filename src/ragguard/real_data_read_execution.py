from __future__ import annotations

from dataclasses import InitVar, dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from ragguard.local_rag_environment import EnvironmentApproval
from ragguard.local_rag_execution import ApprovedLocalRAGExecutionSession
from ragguard.local_rag_integration import RAGStage
from ragguard.real_data_access import (
    RealDataAccessCacheClass,
    RealDataAccessExportClass,
    RealDataAccessLoggingClass,
    RealDataAccessNetworkClass,
    RealDataAccessPersistenceClass,
    RealDataAccessPolicy,
    RealDataAccessRetentionClass,
    RealDataAccessSelector,
    RealDataByteClass,
    RealDataDocumentClass,
    validate_real_data_access_selector_policy,
)
from ragguard.real_data_access_authorization import (
    AuthorizationUsageCounterContract,
    RealDataAccessApproval,
    RealDataAccessApprovalResult,
    RealDataAccessAuthorizationLifecycle,
    RealDataAccessAuthorizationRecord,
    RealDataAccessAuthorizationState,
    RealDataAccessGovernanceReview,
    RealDataAccessRequest,
    RealDataAccessReviewResult,
    RealDataAccessRoleContext,
    RealDataAccessSecurityReview,
    RealDataOperatorAssignment,
    _LIMITED_READ_EXECUTOR_MARKER,
    _consume_authorization_usage_for_verified_read,
    validate_v024_access_source_chain,
)
from ragguard.real_data_read_receipt import (
    PostReadClassificationResult,
    PostReadMaskingVerification,
    PostReadVerificationState,
    ReadDownstreamState,
    ReadExecutionResult,
    ReadExecutionResultState,
    RealDataReadReceipt,
    RealDataReadReceiptResult,
    VerifiedMaskedContentCandidate,
    _MASKED_CANDIDATE_MARKER,
    _READ_RECEIPT_MARKER,
)
from ragguard.real_data_trial import (
    RealDataClass,
    RealDataClassificationPolicy,
    RealDataTrialScope,
    TrialCachePolicy,
    TrialExportPolicy,
    TrialLoggingPolicy,
    TrialPersistencePolicy,
    TrialRetentionPolicy,
    TrialStagePolicy,
)
from ragguard.real_data_trial_approval import (
    ApprovedRealDataTrialRecord,
    TrialApproval,
    TrialApprovalRequest,
    TrialDataGovernanceReview,
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


_PRE_READ_MARKER = object()


class RealDataReadExecutionError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class PreReadVerificationState(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ControlledReadFailure(str, Enum):
    NONE = "none"
    OPEN_FAILED = "open_failed"
    READ_FAILED = "read_failed"
    INCOMPLETE = "incomplete"
    CLASSIFICATION_FAILED = "classification_failed"
    MASKING_FAILED = "masking_failed"


class ReadExecutionLedgerFault(str, Enum):
    NONE = "none"
    FORGED_EXECUTION_RESULT = "forged_execution_result"
    FORGED_RECEIPT = "forged_receipt"
    CANDIDATE_STATE = "candidate_state"
    BEFORE_SWAP = "before_swap"


class ReadExecutionLedgerReason(str, Enum):
    INVALID_CHAIN = "invalid_chain"
    TARGET_INVALID = "target_invalid"
    POLICY_INVALID = "policy_invalid"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    LIFECYCLE_INVALID = "lifecycle_invalid"
    PRE_READ_FAILED = "pre_read_failed"
    OPEN_FAILED = "open_failed"
    READ_FAILED = "read_failed"
    INCOMPLETE = "incomplete"
    CLASSIFICATION_FAILED = "classification_failed"
    MASKING_FAILED = "masking_failed"
    USAGE_INVALID = "usage_invalid"
    REPLAY = "replay"
    COMMIT_FAULT = "commit_fault"


class ReadExecutionLifecycle(str, Enum):
    REQUESTED = "requested"
    VERIFIED = "verified"
    READ_COMPLETED = "read_completed"
    VERIFICATION_FAILED = "verification_failed"
    RECEIPT_COMMITTED = "receipt_committed"


class ExplicitRealDataTrialExecutionState(str, Enum):
    NEEDS_EXPLICIT_REAL_DATA_EXECUTION_APPROVAL = (
        "needs_explicit_real_data_execution_approval"
    )
    ELIGIBLE_FOR_EXPLICIT_ONE_SHOT_TRIAL_EXECUTION = (
        "eligible_for_explicit_one_shot_trial_execution"
    )


class ExplicitRealDataTrialExecutionHook(Protocol):
    """Interface only. Implementations must be separately approved and are absent in v0.26."""

    def evaluate(
        self,
        *,
        execution_request_digest: str,
        explicit_approval_digest: str,
        evaluation_time: datetime,
    ) -> ExplicitRealDataTrialExecutionState: ...


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


def _is_utc(value: object) -> bool:
    return is_aware(value) and value.utcoffset() == timedelta(0)


def _payload(value: object) -> dict[str, object]:
    return {
        key: (
            canonical_datetime(item)
            if isinstance(item, datetime)
            else item.value
            if isinstance(item, Enum)
            else item
        )
        for key, item in vars(value).items()
        if key != "canonical_digest"
    }


@dataclass(frozen=True, repr=False)
class RealDataReadExecutionRequest(_Canonical):
    execution_request_id: str
    authorization_record_digest: str
    selector_digest: str
    access_policy_digest: str
    approved_trial_record_digest: str
    operator_assignment_digest: str
    operator_id: str
    usage_state_digest: str
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        digest_values = tuple(
            item for key, item in vars(self).items() if key.endswith("_digest")
        )
        if (
            not is_identifier(self.execution_request_id)
            or not is_identifier(self.operator_id)
            or not all(is_digest(item) for item in digest_values)
            or not _is_utc(self.requested_at)
            or not _is_utc(self.expires_at)
            or self.expires_at <= self.requested_at
        ):
            raise RealDataReadExecutionError("execution_request_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class ReadTargetDescriptor(_Canonical):
    target_id: str
    selector_digest: str
    data_class: RealDataClass
    document_class: RealDataDocumentClass
    content_identity_digest: str
    expected_classification_digest: str
    expected_size_class: RealDataByteClass

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.target_id)
            or not is_digest(self.selector_digest)
            or not is_digest(self.content_identity_digest)
            or not is_digest(self.expected_classification_digest)
            or not isinstance(self.data_class, RealDataClass)
            or not isinstance(self.document_class, RealDataDocumentClass)
            or not isinstance(self.expected_size_class, RealDataByteClass)
        ):
            raise RealDataReadExecutionError("target_descriptor_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class PreReadVerificationResult(_Canonical):
    execution_request_digest: str
    authorization_record_digest: str
    target_descriptor_digest: str
    operator_id: str
    authorization_state: RealDataAccessAuthorizationLifecycle
    remaining_read_count: int
    selector_match: bool
    classification_match: bool
    stage_ceiling_match: bool
    retention_policy_match: bool
    logging_policy_match: bool
    persistence_policy_match: bool
    export_policy_match: bool
    network_policy_match: bool
    result: PreReadVerificationState
    evaluated_at: datetime
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        matches = tuple(
            item for key, item in vars(self).items() if key.endswith("_match")
        )
        if (
            _marker is not _PRE_READ_MARKER
            or not is_digest(self.execution_request_digest)
            or not is_digest(self.authorization_record_digest)
            or not is_digest(self.target_descriptor_digest)
            or not is_identifier(self.operator_id)
            or not isinstance(
                self.authorization_state, RealDataAccessAuthorizationLifecycle
            )
            or type(self.remaining_read_count) is not int
            or self.remaining_read_count < 0
            or not all(type(item) is bool for item in matches)
            or not isinstance(self.result, PreReadVerificationState)
            or not _is_utc(self.evaluated_at)
            or (
                self.result is PreReadVerificationState.PASSED
                and (
                    not all(matches)
                    or self.authorization_state
                    is not RealDataAccessAuthorizationLifecycle.AUTHORIZED
                    or self.remaining_read_count != 1
                )
            )
        ):
            raise RealDataReadExecutionError("pre_read_verification_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataReadSideEffectAccounting(_Canonical):
    controlled_adapter_read_count: int = 0
    actual_arbitrary_file_open_count: int = 0
    actual_arbitrary_file_read_count: int = 0
    local_rag_material_access_count: int = 0
    restricted_material_access_count: int = 0
    real_data_access_count: int = 0
    external_network_count: int = 0
    http_count: int = 0
    cloud_count: int = 0
    filesystem_write_count: int = 0
    database_write_count: int = 0
    persistent_vector_write_count: int = 0
    production_registry_write_count: int = 0
    credential_use_count: int = 0
    token_use_count: int = 0
    runtime_activation_count: int = 0
    runtime_switch_count: int = 0

    def __post_init__(self) -> None:
        if not all(type(item) is int and item >= 0 for item in vars(self).values()):
            raise RealDataReadExecutionError("read_side_effect_accounting_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, int]:
        return {
            key: item
            for key, item in vars(self).items()
            if key != "canonical_digest"
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def external_all_zero(self) -> bool:
        return all(
            item == 0
            for key, item in self._payload().items()
            if key != "controlled_adapter_read_count"
        )


@dataclass(frozen=True, repr=False)
class RealDataReadAuthorizationContext(_Canonical):
    selector: RealDataAccessSelector
    access_policy: RealDataAccessPolicy
    access_request: RealDataAccessRequest
    access_security_review: RealDataAccessSecurityReview
    access_governance_review: RealDataAccessGovernanceReview
    operator_assignment: RealDataOperatorAssignment
    access_approval: RealDataAccessApproval
    authorization_record: RealDataAccessAuthorizationRecord
    usage_contract: AuthorizationUsageCounterContract
    access_roles: RealDataAccessRoleContext
    approved_trial: ApprovedRealDataTrialRecord
    trial_scope: RealDataTrialScope
    classification_policy: RealDataClassificationPolicy
    stage_policy: TrialStagePolicy
    retention_policy: TrialRetentionPolicy
    logging_policy: TrialLoggingPolicy
    cache_policy: TrialCachePolicy
    export_policy: TrialExportPolicy
    persistence_policy: TrialPersistencePolicy
    trial_request: TrialApprovalRequest
    trial_security_review: TrialSecurityReview
    trial_governance_review: TrialDataGovernanceReview
    trial_approval: TrialApproval
    environment_approval: EnvironmentApproval
    approved_session: ApprovedLocalRAGExecutionSession

    def __post_init__(self) -> None:
        if not all(hasattr(item, "canonical_digest") for item in vars(self).values()):
            raise RealDataReadExecutionError("read_authorization_context_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {
            key: item.canonical_digest
            for key, item in vars(self).items()
            if key != "canonical_digest"
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True)
class _ControlledAdapterOutcome:
    execution_result: ReadExecutionResult
    raw_payload: str | None
    transformed_payload: str | None
    observed_classification_digest: str
    sensitive_class_digest: str
    masked_class_digest: str
    blocked_class_digest: str
    accounting: RealDataReadSideEffectAccounting


class ControlledReadAdapter:
    """Fixture-backed only. It has no path, directory, or filesystem surface."""

    __slots__ = (
        "adapter_id",
        "target_descriptor_digest",
        "fixture_content_digest",
        "transformed_content_digest",
        "observed_classification_digest",
        "sensitive_class_digest",
        "masked_class_digest",
        "blocked_class_digest",
        "canonical_digest",
        "_fixture_payload",
        "_transformed_payload",
        "_sealed",
    )

    def __setattr__(self, name: str, value: object) -> None:
        if hasattr(self, "_sealed"):
            raise AttributeError("controlled_read_adapter_immutable")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        *,
        adapter_id: str,
        target_descriptor_digest: str,
        fixture_payload: str,
        transformed_payload: str,
        observed_classification_digest: str,
        sensitive_class_digest: str,
        masked_class_digest: str,
        blocked_class_digest: str,
    ) -> None:
        digest_values = (
            target_descriptor_digest,
            observed_classification_digest,
            sensitive_class_digest,
            masked_class_digest,
            blocked_class_digest,
        )
        if (
            not is_identifier(adapter_id)
            or not all(is_digest(item) for item in digest_values)
            or not isinstance(fixture_payload, str)
            or not fixture_payload
            or not isinstance(transformed_payload, str)
            or not transformed_payload
            or fixture_payload == transformed_payload
        ):
            raise RealDataReadExecutionError("controlled_read_adapter_invalid")
        self.adapter_id = adapter_id
        self.target_descriptor_digest = target_descriptor_digest
        self._fixture_payload = fixture_payload
        self._transformed_payload = transformed_payload
        self.fixture_content_digest = digest(fixture_payload)
        self.transformed_content_digest = digest(transformed_payload)
        self.observed_classification_digest = observed_classification_digest
        self.sensitive_class_digest = sensitive_class_digest
        self.masked_class_digest = masked_class_digest
        self.blocked_class_digest = blocked_class_digest
        self.canonical_digest = digest(self.canonical_json())
        object.__setattr__(self, "_sealed", True)

    def __repr__(self) -> str:
        return "ControlledReadAdapter(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "adapter_id": self.adapter_id,
                "blocked_class_digest": self.blocked_class_digest,
                "fixture_content_digest": self.fixture_content_digest,
                "masked_class_digest": self.masked_class_digest,
                "observed_classification_digest": self.observed_classification_digest,
                "sensitive_class_digest": self.sensitive_class_digest,
                "target_descriptor_digest": self.target_descriptor_digest,
                "transformed_content_digest": self.transformed_content_digest,
            }
        )

    def _execute_fixture(
        self,
        *,
        execution_id: str,
        execution_request: RealDataReadExecutionRequest,
        target: ReadTargetDescriptor,
        started_at: datetime,
        finished_at: datetime,
        failure: ControlledReadFailure,
    ) -> _ControlledAdapterOutcome:
        if (
            not is_identifier(execution_id)
            or not canonical_object_valid(execution_request)
            or not canonical_object_valid(target)
            or self.target_descriptor_digest != target.canonical_digest
            or not _is_utc(started_at)
            or not _is_utc(finished_at)
            or finished_at < started_at
            or not isinstance(failure, ControlledReadFailure)
        ):
            raise RealDataReadExecutionError("controlled_read_execution_invalid")
        state = ReadExecutionResultState.READ_SUCCEEDED
        raw_payload: str | None = self._fixture_payload
        transformed_payload: str | None = self._transformed_payload
        controlled_count = 1
        raw_digest = self.fixture_content_digest
        if failure is ControlledReadFailure.OPEN_FAILED:
            state = ReadExecutionResultState.OPEN_FAILED
            raw_payload = None
            transformed_payload = None
            controlled_count = 0
            raw_digest = digest("controlled-fixture-not-opened")
        elif failure is ControlledReadFailure.READ_FAILED:
            state = ReadExecutionResultState.READ_FAILED
            raw_payload = None
            transformed_payload = None
            raw_digest = digest("controlled-fixture-read-failed")
        elif failure is ControlledReadFailure.INCOMPLETE:
            state = ReadExecutionResultState.INCOMPLETE
            raw_payload = None
            transformed_payload = None
            raw_digest = digest("controlled-fixture-incomplete")
        execution_result = ReadExecutionResult(
            execution_id,
            execution_request.canonical_digest,
            target.canonical_digest,
            execution_request.operator_id,
            started_at,
            finished_at,
            state,
            target.expected_size_class,
            raw_digest,
        )
        return _ControlledAdapterOutcome(
            execution_result,
            raw_payload,
            transformed_payload,
            self.observed_classification_digest,
            self.sensitive_class_digest,
            self.masked_class_digest,
            self.blocked_class_digest,
            RealDataReadSideEffectAccounting(
                controlled_adapter_read_count=controlled_count
            ),
        )


def _masking_policy_digest(policy: RealDataAccessPolicy) -> str:
    return digest(
        canonical_json(
            {
                "masking_required_before_stage": (
                    policy.masking_required_before_stage.value
                )
            }
        )
    )


def _pre_read_checks(
    context: RealDataReadAuthorizationContext,
    request: RealDataReadExecutionRequest,
    target: ReadTargetDescriptor,
    adapter: ControlledReadAdapter,
    *,
    evaluated_at: datetime,
) -> tuple[tuple[ReadExecutionLedgerReason, ...], dict[str, bool]]:
    objects = tuple(
        value
        for name, value in vars(context).items()
        if name != "canonical_digest"
    ) + (context, request, target, adapter)
    canonical_valid = all(canonical_object_valid(item) for item in objects)
    source_valid = not validate_v024_access_source_chain(
        context.approved_trial,
        context.trial_scope,
        context.classification_policy,
        context.stage_policy,
        context.retention_policy,
        context.logging_policy,
        context.cache_policy,
        context.export_policy,
        context.persistence_policy,
        context.trial_request,
        context.trial_security_review,
        context.trial_governance_review,
        context.trial_approval,
        context.environment_approval,
        context.approved_session,
        evaluation_time=evaluated_at,
    )
    policy_valid = not validate_real_data_access_selector_policy(
        context.selector,
        context.access_policy,
        context.approved_trial,
        context.trial_scope,
        context.classification_policy,
        context.stage_policy,
        context.retention_policy,
        context.logging_policy,
        context.cache_policy,
        context.export_policy,
        context.persistence_policy,
    )
    exact = (
        context.authorization_record.access_request_digest
        == context.access_request.canonical_digest,
        context.authorization_record.selector_digest
        == context.selector.canonical_digest,
        context.authorization_record.policy_digest
        == context.access_policy.canonical_digest,
        context.authorization_record.approved_trial_record_digest
        == context.approved_trial.canonical_digest,
        context.authorization_record.security_review_digest
        == context.access_security_review.canonical_digest,
        context.authorization_record.governance_review_digest
        == context.access_governance_review.canonical_digest,
        context.authorization_record.operator_assignment_digest
        == context.operator_assignment.canonical_digest,
        context.authorization_record.approval_digest
        == context.access_approval.canonical_digest,
        context.access_security_review.access_request_digest
        == context.access_request.canonical_digest,
        context.access_governance_review.access_request_digest
        == context.access_request.canonical_digest,
        context.operator_assignment.access_request_digest
        == context.access_request.canonical_digest,
        context.access_approval.access_request_digest
        == context.access_request.canonical_digest,
        context.access_approval.security_review_digest
        == context.access_security_review.canonical_digest,
        context.access_approval.governance_review_digest
        == context.access_governance_review.canonical_digest,
        context.access_approval.operator_assignment_digest
        == context.operator_assignment.canonical_digest,
        context.usage_contract.authorization_record_digest
        == context.authorization_record.canonical_digest,
        request.authorization_record_digest
        == context.authorization_record.canonical_digest,
        request.selector_digest == context.selector.canonical_digest,
        request.access_policy_digest == context.access_policy.canonical_digest,
        request.approved_trial_record_digest
        == context.approved_trial.canonical_digest,
        request.operator_assignment_digest
        == context.operator_assignment.canonical_digest,
        request.usage_state_digest == context.usage_contract.canonical_digest,
    )
    selector_match = (
        target.selector_digest == context.selector.canonical_digest
        and adapter.target_descriptor_digest == target.canonical_digest
        and adapter.fixture_content_digest == target.content_identity_digest
    )
    classification_match = (
        target.data_class is RealDataClass.INTERNAL_LOW
        and target.data_class is context.selector.data_class
        and target.document_class
        is RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE
        and target.document_class is context.selector.document_class
        and target.expected_classification_digest
        == context.classification_policy.canonical_digest
        and target.expected_size_class is RealDataByteClass.SMALL_DOCUMENT
    )
    stage_ceiling_match = (
        context.access_policy.max_stage is RAGStage.CHUNKING
        and context.access_policy.masking_required_before_stage is RAGStage.CHUNKING
        and context.selector.allowed_stage_ceiling is RAGStage.CHUNKING
    )
    retention_policy_match = (
        context.access_policy.retention_class is RealDataAccessRetentionClass.NONE
    )
    logging_policy_match = (
        context.access_policy.logging_class is RealDataAccessLoggingClass.NONE
        and context.access_policy.cache_class is RealDataAccessCacheClass.NONE
    )
    persistence_policy_match = (
        context.access_policy.persistence_class
        is RealDataAccessPersistenceClass.NONE
    )
    export_policy_match = (
        context.access_policy.export_class is RealDataAccessExportClass.PROHIBITED
    )
    network_policy_match = (
        context.access_policy.network_class is RealDataAccessNetworkClass.PROHIBITED
    )
    roles = (
        request.operator_id == context.operator_assignment.operator_id,
        request.operator_id == context.authorization_record.operator_id,
        request.operator_id == context.access_roles.real_data_operator_id,
        context.access_security_review.reviewer_id
        == context.access_roles.security_reviewer_id,
        context.access_governance_review.reviewer_id
        == context.access_roles.governance_reviewer_id,
        context.access_approval.approver_id
        == context.access_roles.access_approver_id,
        request.operator_id != context.access_approval.approver_id,
        request.operator_id != context.trial_approval.approver_id,
    )
    lifecycle_valid = (
        context.authorization_record.state
        is RealDataAccessAuthorizationState.AUTHORIZED_FOR_LIMITED_READ_EXECUTION_REVIEW
        and context.authorization_record.lifecycle
        is RealDataAccessAuthorizationLifecycle.AUTHORIZED
        and context.authorization_record.remaining_read_count == 1
        and context.authorization_record.allowed_read_count == 1
        and context.usage_contract.remaining_read_count == 1
        and context.usage_contract.allowed_read_count == 1
        and context.access_security_review.result
        is RealDataAccessReviewResult.APPROVED
        and context.access_governance_review.result
        is RealDataAccessReviewResult.APPROVED
        and context.access_approval.result is RealDataAccessApprovalResult.APPROVED
    )
    temporal_valid = (
        _is_utc(evaluated_at)
        and context.authorization_record.issued_at < request.requested_at
        <= evaluated_at
        < request.expires_at
        <= context.authorization_record.expires_at
        and evaluated_at < context.operator_assignment.expires_at
        and evaluated_at < context.access_approval.expires_at
        and evaluated_at < context.approved_trial.expires_at
    )
    matches = {
        "selector_match": selector_match,
        "classification_match": classification_match,
        "stage_ceiling_match": stage_ceiling_match,
        "retention_policy_match": retention_policy_match,
        "logging_policy_match": logging_policy_match,
        "persistence_policy_match": persistence_policy_match,
        "export_policy_match": export_policy_match,
        "network_policy_match": network_policy_match,
    }
    reasons: list[ReadExecutionLedgerReason] = []
    if not canonical_valid or not source_valid or not all(exact):
        reasons.append(ReadExecutionLedgerReason.INVALID_CHAIN)
    if not selector_match or not classification_match:
        reasons.append(ReadExecutionLedgerReason.TARGET_INVALID)
    if not policy_valid or not all(matches.values()):
        reasons.append(ReadExecutionLedgerReason.POLICY_INVALID)
    if not all(roles):
        reasons.append(ReadExecutionLedgerReason.ROLE_CONFLICT)
    if not lifecycle_valid:
        reasons.append(ReadExecutionLedgerReason.LIFECYCLE_INVALID)
    if not temporal_valid:
        reasons.append(ReadExecutionLedgerReason.TEMPORAL_INVALID)
    return tuple(dict.fromkeys(reasons)), matches


@dataclass(frozen=True)
class RealDataReadLedgerResult:
    applied: bool
    reasons: tuple[ReadExecutionLedgerReason, ...]
    lifecycle: ReadExecutionLifecycle
    pre_read: PreReadVerificationResult
    execution_result: ReadExecutionResult | None
    classification_result: PostReadClassificationResult | None
    masking_verification: PostReadMaskingVerification | None
    receipt: RealDataReadReceipt | None
    masked_candidate: VerifiedMaskedContentCandidate | None
    usage_before: AuthorizationUsageCounterContract
    usage_after: AuthorizationUsageCounterContract | None
    exhausted_authorization: RealDataAccessAuthorizationRecord | None
    side_effects: RealDataReadSideEffectAccounting
    write_count: int
    mutation_count: int
    event_count: int


@dataclass(frozen=True)
class _ReadExecutionLedgerState:
    receipts: tuple[RealDataReadReceipt, ...] = ()
    masked_candidates: tuple[VerifiedMaskedContentCandidate, ...] = ()
    exhausted_authorizations: tuple[RealDataAccessAuthorizationRecord, ...] = ()
    usage_states: tuple[AuthorizationUsageCounterContract, ...] = ()
    used_execution_request_digests: frozenset[str] = frozenset()
    used_target_descriptor_digests: frozenset[str] = frozenset()
    used_execution_result_digests: frozenset[str] = frozenset()
    used_classification_result_digests: frozenset[str] = frozenset()
    used_masking_result_digests: frozenset[str] = frozenset()
    used_receipt_digests: frozenset[str] = frozenset()
    used_authorization_usage_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class TestOnlyRealDataReadExecutionLedger:
    __test__ = False

    def __init__(self) -> None:
        self._state = _ReadExecutionLedgerState()

    @property
    def receipts(self) -> tuple[RealDataReadReceipt, ...]:
        return self._state.receipts

    @property
    def masked_candidates(self) -> tuple[VerifiedMaskedContentCandidate, ...]:
        return self._state.masked_candidates

    @property
    def exhausted_authorizations(self) -> tuple[RealDataAccessAuthorizationRecord, ...]:
        return self._state.exhausted_authorizations

    @property
    def usage_states(self) -> tuple[AuthorizationUsageCounterContract, ...]:
        return self._state.usage_states

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
            self._state.used_execution_request_digests,
            self._state.used_target_descriptor_digests,
            self._state.used_execution_result_digests,
            self._state.used_classification_result_digests,
            self._state.used_masking_result_digests,
            self._state.used_receipt_digests,
            self._state.used_authorization_usage_digests,
        )

    def execute(
        self,
        *,
        receipt_id: str,
        execution_id: str,
        candidate_id: str,
        context: RealDataReadAuthorizationContext,
        execution_request: RealDataReadExecutionRequest,
        target: ReadTargetDescriptor,
        adapter: ControlledReadAdapter,
        pre_read_evaluated_at: datetime,
        started_at: datetime,
        finished_at: datetime,
        classification_evaluated_at: datetime,
        masking_evaluated_at: datetime,
        receipt_issued_at: datetime,
        evaluation_time: datetime,
        controlled_failure: ControlledReadFailure = ControlledReadFailure.NONE,
        fault: ReadExecutionLedgerFault = ReadExecutionLedgerFault.NONE,
    ) -> RealDataReadLedgerResult:
        if not isinstance(controlled_failure, ControlledReadFailure) or not isinstance(
            fault, ReadExecutionLedgerFault
        ):
            raise RealDataReadExecutionError("read_execution_control_invalid")
        pre_reasons, matches = _pre_read_checks(
            context,
            execution_request,
            target,
            adapter,
            evaluated_at=pre_read_evaluated_at,
        )
        pre_read = PreReadVerificationResult(
            execution_request.canonical_digest,
            context.authorization_record.canonical_digest,
            target.canonical_digest,
            execution_request.operator_id,
            context.authorization_record.lifecycle,
            context.usage_contract.remaining_read_count,
            matches["selector_match"],
            matches["classification_match"],
            matches["stage_ceiling_match"],
            matches["retention_policy_match"],
            matches["logging_policy_match"],
            matches["persistence_policy_match"],
            matches["export_policy_match"],
            matches["network_policy_match"],
            PreReadVerificationState.FAILED
            if pre_reasons
            else PreReadVerificationState.PASSED,
            pre_read_evaluated_at,
            _marker=_PRE_READ_MARKER,
        )
        zero_effects = RealDataReadSideEffectAccounting()
        if pre_reasons:
            return self._result(
                False,
                pre_reasons + (ReadExecutionLedgerReason.PRE_READ_FAILED,),
                ReadExecutionLifecycle.REQUESTED,
                pre_read,
                context.usage_contract,
                zero_effects,
            )
        temporal = (
            context.authorization_record.issued_at
            < execution_request.requested_at
            < pre_read_evaluated_at
            < started_at
            < finished_at
            < classification_evaluated_at
            < masking_evaluated_at
            < receipt_issued_at
            <= evaluation_time
            < execution_request.expires_at
            <= context.authorization_record.expires_at
        )
        if not temporal or not all(
            _is_utc(item)
            for item in (
                started_at,
                finished_at,
                classification_evaluated_at,
                masking_evaluated_at,
                receipt_issued_at,
                evaluation_time,
            )
        ):
            return self._result(
                False,
                (ReadExecutionLedgerReason.TEMPORAL_INVALID,),
                ReadExecutionLifecycle.VERIFIED,
                pre_read,
                context.usage_contract,
                zero_effects,
            )
        outcome = adapter._execute_fixture(
            execution_id=execution_id,
            execution_request=execution_request,
            target=target,
            started_at=started_at,
            finished_at=finished_at,
            failure=controlled_failure,
        )
        execution_result = outcome.execution_result
        if fault is ReadExecutionLedgerFault.FORGED_EXECUTION_RESULT:
            object.__setattr__(execution_result, "operator_id", "forged-operator")
        if not canonical_object_valid(execution_result):
            return self._result(
                False,
                (ReadExecutionLedgerReason.INVALID_CHAIN,),
                ReadExecutionLifecycle.VERIFICATION_FAILED,
                pre_read,
                context.usage_contract,
                outcome.accounting,
                execution_result=execution_result,
            )
        failure_reason = {
            ReadExecutionResultState.OPEN_FAILED: ReadExecutionLedgerReason.OPEN_FAILED,
            ReadExecutionResultState.READ_FAILED: ReadExecutionLedgerReason.READ_FAILED,
            ReadExecutionResultState.INCOMPLETE: ReadExecutionLedgerReason.INCOMPLETE,
        }.get(execution_result.result)
        if failure_reason is not None:
            return self._result(
                False,
                (failure_reason,),
                ReadExecutionLifecycle.VERIFICATION_FAILED,
                pre_read,
                context.usage_contract,
                outcome.accounting,
                execution_result=execution_result,
            )
        classification_passed = (
            controlled_failure is not ControlledReadFailure.CLASSIFICATION_FAILED
            and outcome.observed_classification_digest
            == target.expected_classification_digest
        )
        classification = PostReadClassificationResult(
            execution_result.canonical_digest,
            target.expected_classification_digest,
            outcome.observed_classification_digest,
            outcome.sensitive_class_digest,
            PostReadVerificationState.PASSED
            if classification_passed
            else PostReadVerificationState.FAILED,
            classification_evaluated_at,
        )
        if not classification_passed:
            return self._result(
                False,
                (ReadExecutionLedgerReason.CLASSIFICATION_FAILED,),
                ReadExecutionLifecycle.VERIFICATION_FAILED,
                pre_read,
                context.usage_contract,
                outcome.accounting,
                execution_result=execution_result,
                classification_result=classification,
            )
        if outcome.raw_payload is None or outcome.transformed_payload is None:
            raise RealDataReadExecutionError("controlled_fixture_payload_missing")
        transformed_digest = digest(outcome.transformed_payload)
        masking_passed = (
            controlled_failure is not ControlledReadFailure.MASKING_FAILED
            and execution_result.raw_content_digest == digest(outcome.raw_payload)
            and execution_result.raw_content_digest == target.content_identity_digest
            and transformed_digest == adapter.transformed_content_digest
            and transformed_digest != execution_result.raw_content_digest
        )
        masking = PostReadMaskingVerification(
            execution_result.canonical_digest,
            classification.canonical_digest,
            _masking_policy_digest(context.access_policy),
            execution_result.raw_content_digest,
            transformed_digest,
            outcome.masked_class_digest,
            outcome.blocked_class_digest,
            PostReadVerificationState.PASSED
            if masking_passed
            else PostReadVerificationState.FAILED,
            masking_evaluated_at,
        )
        if not masking_passed:
            return self._result(
                False,
                (ReadExecutionLedgerReason.MASKING_FAILED,),
                ReadExecutionLifecycle.VERIFICATION_FAILED,
                pre_read,
                context.usage_contract,
                outcome.accounting,
                execution_result=execution_result,
                classification_result=classification,
                masking_verification=masking,
            )
        try:
            exhausted_record, usage_after = (
                _consume_authorization_usage_for_verified_read(
                    context.authorization_record,
                    context.usage_contract,
                    executor_marker=_LIMITED_READ_EXECUTOR_MARKER,
                )
            )
        except ValueError:
            return self._result(
                False,
                (ReadExecutionLedgerReason.USAGE_INVALID,),
                ReadExecutionLifecycle.VERIFICATION_FAILED,
                pre_read,
                context.usage_contract,
                outcome.accounting,
                execution_result=execution_result,
                classification_result=classification,
                masking_verification=masking,
            )
        receipt = RealDataReadReceipt(
            receipt_id,
            execution_request.canonical_digest,
            context.authorization_record.canonical_digest,
            target.canonical_digest,
            execution_request.operator_id,
            execution_result.canonical_digest,
            classification.canonical_digest,
            masking.canonical_digest,
            transformed_digest,
            context.usage_contract.canonical_digest,
            usage_after.canonical_digest,
            receipt_issued_at,
            RealDataReadReceiptResult.VERIFIED_READ_COMPLETED,
            _marker=_READ_RECEIPT_MARKER,
        )
        candidate = VerifiedMaskedContentCandidate(
            candidate_id,
            receipt.canonical_digest,
            transformed_digest,
            ReadDownstreamState.VERIFIED_MASKED_CONTENT_CANDIDATE,
            receipt_issued_at,
            _marker=_MASKED_CANDIDATE_MARKER,
        )
        if fault is ReadExecutionLedgerFault.FORGED_RECEIPT:
            object.__setattr__(receipt, "operator_id", "forged-operator")
        evidence_valid = (
            canonical_object_valid(classification)
            and canonical_object_valid(masking)
            and canonical_object_valid(receipt)
            and canonical_object_valid(candidate)
            and canonical_object_valid(usage_after)
            and canonical_object_valid(exhausted_record)
            and execution_result.execution_request_digest
            == execution_request.canonical_digest
            and execution_result.target_descriptor_digest == target.canonical_digest
            and execution_result.operator_id == execution_request.operator_id
            and receipt.execution_request_digest == execution_request.canonical_digest
            and receipt.authorization_record_digest
            == context.authorization_record.canonical_digest
            and receipt.target_descriptor_digest == target.canonical_digest
            and receipt.operator_id == execution_result.operator_id
            and receipt.execution_result_digest == execution_result.canonical_digest
            and receipt.classification_result_digest == classification.canonical_digest
            and receipt.masking_verification_digest == masking.canonical_digest
            and receipt.usage_before_digest == context.usage_contract.canonical_digest
            and receipt.usage_after_digest == usage_after.canonical_digest
            and usage_after.remaining_read_count == 0
            and usage_after.authorization_record_digest
            == exhausted_record.canonical_digest
            and exhausted_record.lifecycle
            is RealDataAccessAuthorizationLifecycle.EXHAUSTED
            and exhausted_record.remaining_read_count == 0
            and candidate.receipt_digest == receipt.canonical_digest
        )
        if not evidence_valid:
            return self._result(
                False,
                (ReadExecutionLedgerReason.INVALID_CHAIN,),
                ReadExecutionLifecycle.VERIFICATION_FAILED,
                pre_read,
                context.usage_contract,
                outcome.accounting,
                execution_result=execution_result,
                classification_result=classification,
                masking_verification=masking,
            )
        replay = (
            (
                execution_request.canonical_digest,
                self._state.used_execution_request_digests,
            ),
            (target.canonical_digest, self._state.used_target_descriptor_digests),
            (
                execution_result.canonical_digest,
                self._state.used_execution_result_digests,
            ),
            (
                classification.canonical_digest,
                self._state.used_classification_result_digests,
            ),
            (masking.canonical_digest, self._state.used_masking_result_digests),
            (receipt.canonical_digest, self._state.used_receipt_digests),
            (
                context.usage_contract.canonical_digest,
                self._state.used_authorization_usage_digests,
            ),
        )
        if any(item in used for item, used in replay) or any(
            item.predecessor_authorization_digest
            == context.authorization_record.canonical_digest
            for item in self.exhausted_authorizations
        ):
            return self._result(
                False,
                (ReadExecutionLedgerReason.REPLAY,),
                ReadExecutionLifecycle.VERIFICATION_FAILED,
                pre_read,
                context.usage_contract,
                outcome.accounting,
                execution_result=execution_result,
                classification_result=classification,
                masking_verification=masking,
            )
        try:
            if fault is ReadExecutionLedgerFault.CANDIDATE_STATE:
                raise RuntimeError
            state = self._state
            ledger_candidate = replace(
                state,
                receipts=state.receipts + (receipt,),
                masked_candidates=state.masked_candidates + (candidate,),
                exhausted_authorizations=state.exhausted_authorizations
                + (exhausted_record,),
                usage_states=state.usage_states + (usage_after,),
                used_execution_request_digests=state.used_execution_request_digests
                | {execution_request.canonical_digest},
                used_target_descriptor_digests=state.used_target_descriptor_digests
                | {target.canonical_digest},
                used_execution_result_digests=state.used_execution_result_digests
                | {execution_result.canonical_digest},
                used_classification_result_digests=(
                    state.used_classification_result_digests
                    | {classification.canonical_digest}
                ),
                used_masking_result_digests=state.used_masking_result_digests
                | {masking.canonical_digest},
                used_receipt_digests=state.used_receipt_digests
                | {receipt.canonical_digest},
                used_authorization_usage_digests=(
                    state.used_authorization_usage_digests
                    | {context.usage_contract.canonical_digest}
                ),
                write_count=state.write_count + 1,
                mutation_count=state.mutation_count + 1,
                event_count=state.event_count + 1,
            )
            if fault is ReadExecutionLedgerFault.BEFORE_SWAP:
                raise RuntimeError
            self._state = ledger_candidate
        except RuntimeError:
            return self._result(
                False,
                (ReadExecutionLedgerReason.COMMIT_FAULT,),
                ReadExecutionLifecycle.READ_COMPLETED,
                pre_read,
                context.usage_contract,
                outcome.accounting,
                execution_result=execution_result,
                classification_result=classification,
                masking_verification=masking,
            )
        return RealDataReadLedgerResult(
            True,
            (),
            ReadExecutionLifecycle.RECEIPT_COMMITTED,
            pre_read,
            execution_result,
            classification,
            masking,
            receipt,
            candidate,
            context.usage_contract,
            usage_after,
            exhausted_record,
            outcome.accounting,
            self.write_count,
            self.mutation_count,
            self.event_count,
        )

    def _result(
        self,
        applied: bool,
        reasons: tuple[ReadExecutionLedgerReason, ...],
        lifecycle: ReadExecutionLifecycle,
        pre_read: PreReadVerificationResult,
        usage_before: AuthorizationUsageCounterContract,
        side_effects: RealDataReadSideEffectAccounting,
        *,
        execution_result: ReadExecutionResult | None = None,
        classification_result: PostReadClassificationResult | None = None,
        masking_verification: PostReadMaskingVerification | None = None,
    ) -> RealDataReadLedgerResult:
        return RealDataReadLedgerResult(
            applied,
            reasons,
            lifecycle,
            pre_read,
            execution_result,
            classification_result,
            masking_verification,
            None,
            None,
            usage_before,
            None,
            None,
            side_effects,
            self.write_count,
            self.mutation_count,
            self.event_count,
        )


__all__ = [
    "ControlledReadAdapter",
    "ControlledReadFailure",
    "ExplicitRealDataTrialExecutionHook",
    "ExplicitRealDataTrialExecutionState",
    "PreReadVerificationResult",
    "PreReadVerificationState",
    "ReadExecutionLedgerFault",
    "ReadExecutionLedgerReason",
    "ReadExecutionLifecycle",
    "ReadTargetDescriptor",
    "RealDataReadAuthorizationContext",
    "RealDataReadExecutionError",
    "RealDataReadExecutionRequest",
    "RealDataReadLedgerResult",
    "RealDataReadSideEffectAccounting",
    "TestOnlyRealDataReadExecutionLedger",
]
