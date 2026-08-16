from __future__ import annotations

from dataclasses import InitVar, dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum

from ragguard.local_rag_integration import RAGStage
from ragguard.real_data_access import (
    RealDataAccessCacheClass,
    RealDataAccessExportClass,
    RealDataAccessLoggingClass,
    RealDataAccessNetworkClass,
    RealDataAccessPersistenceClass,
    RealDataAccessRetentionClass,
    RealDataByteClass,
    RealDataDocumentClass,
    validate_real_data_access_selector_policy,
)
from ragguard.real_data_access_authorization import (
    RealDataAccessApprovalResult,
    RealDataAccessAuthorizationLifecycle,
    RealDataAccessAuthorizationState,
    RealDataAccessReviewResult,
    validate_v024_access_source_chain,
)
from ragguard.real_data_read_execution import RealDataReadAuthorizationContext
from ragguard.real_data_trial import RealDataClass
from ragguard.real_target_resolver import (
    ControlledTargetReference,
    RealTargetResolverPolicy,
    TrialRootDescriptor,
)
from ragguard.real_trial_root import (
    LinkReparseVerificationResult,
    NetworkIsolationVerificationResult,
    PermissionVerificationResult,
    RealTrialClosureRequirement,
    RealTrialPurpose,
    RealTrialRootIdentity,
    RealTrialRootProvisioningRequest,
    RealTrialTargetSelection,
    RootConfinementVerificationResult,
    RootProvisioningAttestation,
    WriteProhibitionVerificationResult,
    fixed_real_trial_closure_policy_digest,
    validate_real_trial_root_chain,
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


_APPROVED_TRIAL_MARKER = object()
MAX_ONE_SHOT_TRIAL_APPROVAL_AGE = timedelta(hours=1)


class RealTrialApprovalError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class TrialAuthorizationReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class TrialExecutionApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovedOneShotRealDataTrialState(str, Enum):
    APPROVED_FOR_ONE_SHOT_EXECUTION_REVIEW = (
        "approved_for_one_shot_execution_review"
    )


class ApprovedOneShotRealDataTrialLifecycle(str, Enum):
    APPROVED = "approved"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    EXECUTION_PENDING = "execution_pending"
    CLOSED = "closed"


class RealTrialApprovalRegistryFault(str, Enum):
    NONE = "none"
    CANDIDATE_STATE = "candidate_state"
    BEFORE_SWAP = "before_swap"


class RealTrialApprovalRegistryReason(str, Enum):
    INVALID_CHAIN = "invalid_chain"
    ROOT_PROVISIONING_INVALID = "root_provisioning_invalid"
    POLICY_INVALID = "policy_invalid"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    LIFECYCLE_INVALID = "lifecycle_invalid"
    GENERATION_MISMATCH = "generation_mismatch"
    PREDECESSOR_MISMATCH = "predecessor_mismatch"
    REPLAY = "replay"
    COMMIT_FAULT = "commit_fault"


class OneShotTrialApprovalReadinessState(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_ROOT_ATTESTATION = "needs_root_attestation"
    NEEDS_SECURITY_REVIEW = "needs_security_review"
    NEEDS_GOVERNANCE_REVIEW = "needs_governance_review"
    NEEDS_EXECUTION_APPROVAL = "needs_execution_approval"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    EXECUTION_PENDING = "execution_pending"
    CLOSED = "closed"
    ELIGIBLE_FOR_EXPLICIT_ONE_SHOT_REAL_DATA_EXECUTION = (
        "eligible_for_explicit_one_shot_real_data_execution"
    )
    NOT_APPROVED = "ineligible"
    ELIGIBLE_FOR_EXPLICIT_ONE_SHOT_EXECUTION_REVIEW = (
        "eligible_for_explicit_one_shot_real_data_execution"
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
class RealTrialApprovalRoleContext(_Canonical):
    root_provisioner_id: str
    root_verifier_id: str
    trial_requester_id: str
    security_reviewer_id: str
    governance_reviewer_id: str
    operator_id: str
    execution_approver_id: str
    access_approver_id: str

    def __post_init__(self) -> None:
        values = tuple(
            item for key, item in vars(self).items() if key != "canonical_digest"
        )
        if (
            not all(is_identifier(item) for item in values)
            or len(set(values)) != len(values)
        ):
            raise RealTrialApprovalError("real_trial_role_conflict")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class RealTrialApprovalSourceContext(_Canonical):
    read_authorization_context: RealDataReadAuthorizationContext
    root_descriptor: TrialRootDescriptor
    resolver_policy: RealTargetResolverPolicy
    controlled_target_reference: ControlledTargetReference

    def __post_init__(self) -> None:
        objects = (
            self.read_authorization_context,
            self.root_descriptor,
            self.resolver_policy,
            self.controlled_target_reference,
        )
        if not all(canonical_object_valid(item) for item in objects):
            raise RealTrialApprovalError("real_trial_source_context_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {
            "controlled_target_reference": (
                self.controlled_target_reference.canonical_digest
            ),
            "read_authorization_context": (
                self.read_authorization_context.canonical_digest
            ),
            "resolver_policy": self.resolver_policy.canonical_digest,
            "root_descriptor": self.root_descriptor.canonical_digest,
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealTrialApprovalRequest(_Canonical):
    approval_request_id: str
    purpose_digest: str
    root_identity_digest: str
    root_provisioning_request_digest: str
    root_attestation_digest: str
    target_selection_digest: str
    v0_25_authorization_record_digest: str
    access_approval_digest: str
    approved_trial_record_digest: str
    root_descriptor_digest: str
    v0_27_reader_policy_digest: str
    controlled_target_reference_digest: str
    closure_requirement_digest: str
    requester_id: str
    operator_id: str
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        digest_values = tuple(
            item
            for key, item in vars(self).items()
            if key.endswith("_digest") and item is not None
        )
        if (
            not is_identifier(self.approval_request_id)
            or not all(is_digest(item) for item in digest_values)
            or not is_identifier(self.requester_id)
            or not is_identifier(self.operator_id)
            or self.requester_id == self.operator_id
            or not _is_utc(self.requested_at)
            or not _is_utc(self.expires_at)
            or self.expires_at <= self.requested_at
        ):
            raise RealTrialApprovalError("real_trial_approval_request_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))

    @property
    def access_authorization_record_digest(self) -> str:
        return self.v0_25_authorization_record_digest

    @property
    def resolver_policy_digest(self) -> str:
        return self.v0_27_reader_policy_digest


@dataclass(frozen=True, repr=False)
class TrialSecurityReview(_Canonical):
    review_id: str
    approval_request_digest: str
    root_attestation_digest: str
    target_selection_digest: str
    resolver_policy_digest: str
    reviewer_id: str
    reviewed_at: datetime
    result: TrialAuthorizationReviewResult
    findings_digest: str

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.review_id)
            or not is_digest(self.approval_request_digest)
            or not is_digest(self.root_attestation_digest)
            or not is_digest(self.target_selection_digest)
            or not is_digest(self.resolver_policy_digest)
            or not is_identifier(self.reviewer_id)
            or not _is_utc(self.reviewed_at)
            or not isinstance(self.result, TrialAuthorizationReviewResult)
            or not is_digest(self.findings_digest)
        ):
            raise RealTrialApprovalError("trial_security_review_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class TrialDataGovernanceReview(_Canonical):
    review_id: str
    approval_request_digest: str
    purpose_digest: str
    target_selection_digest: str
    closure_requirement_digest: str
    classification_digest: str
    retention_policy_digest: str
    logging_policy_digest: str
    persistence_policy_digest: str
    reviewer_id: str
    reviewed_at: datetime
    result: TrialAuthorizationReviewResult
    findings_digest: str

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.review_id)
            or not is_digest(self.approval_request_digest)
            or not is_digest(self.purpose_digest)
            or not is_digest(self.target_selection_digest)
            or not is_digest(self.closure_requirement_digest)
            or not is_digest(self.classification_digest)
            or not is_digest(self.retention_policy_digest)
            or not is_digest(self.logging_policy_digest)
            or not is_digest(self.persistence_policy_digest)
            or not is_identifier(self.reviewer_id)
            or not _is_utc(self.reviewed_at)
            or not isinstance(self.result, TrialAuthorizationReviewResult)
            or not is_digest(self.findings_digest)
        ):
            raise RealTrialApprovalError("trial_governance_review_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class TrialExecutionApproval(_Canonical):
    approval_id: str
    approval_request_digest: str
    security_review_digest: str
    governance_review_digest: str
    operator_id: str
    approver_id: str
    approved_at: datetime
    expires_at: datetime
    result: TrialExecutionApprovalResult

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.approval_id)
            or not is_digest(self.approval_request_digest)
            or not is_digest(self.security_review_digest)
            or not is_digest(self.governance_review_digest)
            or not is_identifier(self.operator_id)
            or not is_identifier(self.approver_id)
            or self.operator_id == self.approver_id
            or not _is_utc(self.approved_at)
            or not _is_utc(self.expires_at)
            or self.expires_at <= self.approved_at
            or not isinstance(self.result, TrialExecutionApprovalResult)
        ):
            raise RealTrialApprovalError("trial_execution_approval_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class ApprovedOneShotRealDataTrial(_Canonical):
    approved_trial_id: str
    source_context_digest: str
    purpose_digest: str
    root_provisioning_request_digest: str
    root_identity_digest: str
    root_attestation_digest: str
    target_selection_digest: str
    closure_requirement_digest: str
    approval_request_digest: str
    security_review_digest: str
    governance_review_digest: str
    execution_approval_digest: str
    access_authorization_record_digest: str
    access_operator_assignment_digest: str
    access_usage_contract_digest: str
    root_descriptor_digest: str
    resolver_policy_digest: str
    controlled_target_reference_digest: str
    operator_id: str
    generation: int
    predecessor_trial_digest: str | None
    approved_at: datetime
    expires_at: datetime
    lifecycle_changed_at: datetime
    state: ApprovedOneShotRealDataTrialState = (
        ApprovedOneShotRealDataTrialState.APPROVED_FOR_ONE_SHOT_EXECUTION_REVIEW
    )
    lifecycle: ApprovedOneShotRealDataTrialLifecycle = (
        ApprovedOneShotRealDataTrialLifecycle.APPROVED
    )
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        digest_values = tuple(
            item
            for key, item in vars(self).items()
            if key.endswith("_digest") and item is not None
        )
        if (
            _marker is not _APPROVED_TRIAL_MARKER
            or not is_identifier(self.approved_trial_id)
            or not all(is_digest(item) for item in digest_values)
            or (
                self.predecessor_trial_digest is not None
                and not is_digest(self.predecessor_trial_digest)
            )
            or not is_identifier(self.operator_id)
            or type(self.generation) is not int
            or self.generation < 1
            or not _is_utc(self.approved_at)
            or not _is_utc(self.expires_at)
            or not _is_utc(self.lifecycle_changed_at)
            or not (
                self.approved_at
                <= self.lifecycle_changed_at
                <= self.expires_at
            )
            or self.expires_at <= self.approved_at
            or not isinstance(self.state, ApprovedOneShotRealDataTrialState)
            or not isinstance(
                self.lifecycle, ApprovedOneShotRealDataTrialLifecycle
            )
        ):
            raise RealTrialApprovalError("approved_one_shot_trial_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))

    @property
    def approval_generation(self) -> int:
        return self.generation

    @property
    def predecessor_approval_digest(self) -> str | None:
        return self.predecessor_trial_digest

    @property
    def actual_read_executed(self) -> bool:
        return False

    @property
    def real_data_use_authorized(self) -> bool:
        return False

    @property
    def embedding_authorized(self) -> bool:
        return False

    @property
    def persistence_authorized(self) -> bool:
        return False

    @property
    def export_authorized(self) -> bool:
        return False

    @property
    def runtime_activation_authorized(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class RealTrialApprovalSideEffectAccounting(_Canonical):
    actual_file_open_count: int = 0
    actual_file_read_count: int = 0
    arbitrary_filesystem_read_count: int = 0
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
        if not all(
            type(item) is int and item >= 0 for item in vars(self).values()
        ):
            raise RealTrialApprovalError("trial_side_effect_accounting_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, int]:
        return {
            key: item for key, item in vars(self).items() if key != "canonical_digest"
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def all_zero(self) -> bool:
        return all(item == 0 for item in self._payload().values())


def validate_real_trial_approval_source(
    context: RealTrialApprovalSourceContext,
    *,
    evaluation_time: datetime,
) -> tuple[str, ...]:
    reasons: list[str] = []
    access = context.read_authorization_context
    access_objects = tuple(
        item for key, item in vars(access).items() if key != "canonical_digest"
    )
    if not canonical_object_valid(context) or not all(
        canonical_object_valid(item) for item in access_objects
    ):
        reasons.append("forged_access_source_context")
    if validate_v024_access_source_chain(
        access.approved_trial,
        access.trial_scope,
        access.classification_policy,
        access.stage_policy,
        access.retention_policy,
        access.logging_policy,
        access.cache_policy,
        access.export_policy,
        access.persistence_policy,
        access.trial_request,
        access.trial_security_review,
        access.trial_governance_review,
        access.trial_approval,
        access.environment_approval,
        access.approved_session,
        evaluation_time=evaluation_time,
    ):
        reasons.append("v024_source_chain_invalid")
    if validate_real_data_access_selector_policy(
        access.selector,
        access.access_policy,
        access.approved_trial,
        access.trial_scope,
        access.classification_policy,
        access.stage_policy,
        access.retention_policy,
        access.logging_policy,
        access.cache_policy,
        access.export_policy,
        access.persistence_policy,
    ):
        reasons.append("access_policy_invalid")
    exact = (
        access.authorization_record.access_request_digest
        == access.access_request.canonical_digest,
        access.authorization_record.selector_digest == access.selector.canonical_digest,
        access.authorization_record.policy_digest
        == access.access_policy.canonical_digest,
        access.authorization_record.approved_trial_record_digest
        == access.approved_trial.canonical_digest,
        access.authorization_record.security_review_digest
        == access.access_security_review.canonical_digest,
        access.authorization_record.governance_review_digest
        == access.access_governance_review.canonical_digest,
        access.authorization_record.operator_assignment_digest
        == access.operator_assignment.canonical_digest,
        access.authorization_record.approval_digest
        == access.access_approval.canonical_digest,
        access.authorization_record.operator_id == access.operator_assignment.operator_id,
        access.usage_contract.authorization_record_digest
        == access.authorization_record.canonical_digest,
        access.access_approval.operator_assignment_digest
        == access.operator_assignment.canonical_digest,
        access.access_approval.approver_id == access.access_roles.access_approver_id,
        context.root_descriptor.resolver_policy_digest
        == context.resolver_policy.canonical_digest,
        context.resolver_policy.allowed_root_digest
        == context.root_descriptor.root_identity_digest,
        context.controlled_target_reference.root_digest
        == context.root_descriptor.canonical_digest,
    )
    if not all(exact):
        reasons.append("access_source_binding_mismatch")
    policy = access.access_policy
    hard_gates = (
        access.authorization_record.state
        is RealDataAccessAuthorizationState.AUTHORIZED_FOR_LIMITED_READ_EXECUTION_REVIEW,
        access.authorization_record.lifecycle
        is RealDataAccessAuthorizationLifecycle.AUTHORIZED,
        access.authorization_record.allowed_read_count == 1,
        access.authorization_record.remaining_read_count == 1,
        access.usage_contract.allowed_read_count == 1,
        access.usage_contract.remaining_read_count == 1,
        access.access_security_review.result is RealDataAccessReviewResult.APPROVED,
        access.access_governance_review.result is RealDataAccessReviewResult.APPROVED,
        access.access_approval.result is RealDataAccessApprovalResult.APPROVED,
        access.selector.data_class is RealDataClass.INTERNAL_LOW,
        access.selector.document_class
        is RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,
        policy.allowed_data_classes == (RealDataClass.INTERNAL_LOW,),
        policy.allowed_document_classes
        == (RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,),
        policy.max_stage is RAGStage.CHUNKING,
        policy.masking_required_before_stage is RAGStage.CHUNKING,
        policy.max_documents == 1,
        policy.max_bytes_class is RealDataByteClass.SMALL_DOCUMENT,
        policy.allowed_read_count == 1,
        policy.retention_class is RealDataAccessRetentionClass.NONE,
        policy.logging_class is RealDataAccessLoggingClass.NONE,
        policy.cache_class is RealDataAccessCacheClass.NONE,
        policy.persistence_class is RealDataAccessPersistenceClass.NONE,
        policy.export_class is RealDataAccessExportClass.PROHIBITED,
        policy.network_class is RealDataAccessNetworkClass.PROHIBITED,
        not context.resolver_policy.allow_symlink,
        not context.resolver_policy.allow_junction,
        not context.resolver_policy.allow_reparse_point,
        not context.resolver_policy.allow_parent_traversal,
        not context.resolver_policy.allow_absolute_user_input,
        context.resolver_policy.require_regular_file,
        context.resolver_policy.require_identity_stability,
    )
    if not all(hard_gates):
        reasons.append("access_hard_gate_failed")
    if (
        not _is_utc(evaluation_time)
        or not (
            access.authorization_record.issued_at
            <= evaluation_time
            < access.authorization_record.expires_at
        )
        or evaluation_time >= access.operator_assignment.expires_at
        or evaluation_time >= access.access_approval.expires_at
        or evaluation_time >= access.approved_trial.expires_at
    ):
        reasons.append("access_source_temporal_invalid")
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True)
class RealTrialApprovalRegistryResult:
    applied: bool
    reasons: tuple[RealTrialApprovalRegistryReason, ...]
    record: ApprovedOneShotRealDataTrial | None
    side_effects: RealTrialApprovalSideEffectAccounting
    write_count: int
    mutation_count: int
    event_count: int


@dataclass(frozen=True)
class _RegistryState:
    records: tuple[ApprovedOneShotRealDataTrial, ...] = ()
    used_root_request_digests: frozenset[str] = frozenset()
    used_root_identity_digests: frozenset[str] = frozenset()
    used_root_attestation_digests: frozenset[str] = frozenset()
    used_target_selection_digests: frozenset[str] = frozenset()
    used_approval_request_digests: frozenset[str] = frozenset()
    used_security_review_digests: frozenset[str] = frozenset()
    used_governance_review_digests: frozenset[str] = frozenset()
    used_execution_approval_digests: frozenset[str] = frozenset()
    used_record_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class TestOnlyRealTrialApprovalRegistry:
    __test__ = False

    def __init__(self) -> None:
        self._state = _RegistryState()

    @property
    def records(self) -> tuple[ApprovedOneShotRealDataTrial, ...]:
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
            self._state.used_root_request_digests,
            self._state.used_root_identity_digests,
            self._state.used_root_attestation_digests,
            self._state.used_target_selection_digests,
            self._state.used_approval_request_digests,
            self._state.used_security_review_digests,
            self._state.used_governance_review_digests,
            self._state.used_execution_approval_digests,
            self._state.used_record_digests,
        )

    def approve(
        self,
        *,
        approved_trial_id: str,
        source_context: RealTrialApprovalSourceContext,
        purpose: RealTrialPurpose,
        provisioning_request: RealTrialRootProvisioningRequest,
        root_identity: RealTrialRootIdentity,
        root_confinement: RootConfinementVerificationResult,
        link_reparse: LinkReparseVerificationResult,
        permission: PermissionVerificationResult,
        write_prohibition: WriteProhibitionVerificationResult,
        network_isolation: NetworkIsolationVerificationResult,
        root_attestation: RootProvisioningAttestation,
        target_selection: RealTrialTargetSelection,
        closure_requirement: RealTrialClosureRequirement,
        approval_request: RealTrialApprovalRequest,
        security_review: TrialSecurityReview | None,
        governance_review: TrialDataGovernanceReview | None,
        execution_approval: TrialExecutionApproval | None,
        roles: RealTrialApprovalRoleContext,
        approval_generation: int,
        predecessor_approval_digest: str | None,
        approved_at: datetime,
        expires_at: datetime,
        fault: RealTrialApprovalRegistryFault = RealTrialApprovalRegistryFault.NONE,
    ) -> RealTrialApprovalRegistryResult:
        side_effects = RealTrialApprovalSideEffectAccounting()
        reasons: list[RealTrialApprovalRegistryReason] = []
        if (
            not isinstance(security_review, TrialSecurityReview)
            or not isinstance(governance_review, TrialDataGovernanceReview)
            or not isinstance(execution_approval, TrialExecutionApproval)
            or not isinstance(fault, RealTrialApprovalRegistryFault)
        ):
            return self._result(
                False,
                (RealTrialApprovalRegistryReason.INVALID_CHAIN,),
                None,
                side_effects,
            )
        objects = (
            source_context,
            purpose,
            provisioning_request,
            root_identity,
            root_confinement,
            link_reparse,
            permission,
            write_prohibition,
            network_isolation,
            root_attestation,
            target_selection,
            closure_requirement,
            approval_request,
            security_review,
            governance_review,
            execution_approval,
            roles,
        )
        if not all(canonical_object_valid(item) for item in objects):
            reasons.append(RealTrialApprovalRegistryReason.INVALID_CHAIN)
        if validate_real_trial_approval_source(
            source_context, evaluation_time=approved_at
        ):
            reasons.append(RealTrialApprovalRegistryReason.INVALID_CHAIN)
        root_reasons = validate_real_trial_root_chain(
            purpose=purpose,
            provisioning_request=provisioning_request,
            root_identity=root_identity,
            root_descriptor=source_context.root_descriptor,
            resolver_policy=source_context.resolver_policy,
            target_reference=source_context.controlled_target_reference,
            root_confinement=root_confinement,
            link_reparse=link_reparse,
            permission=permission,
            write_prohibition=write_prohibition,
            network_isolation=network_isolation,
            attestation=root_attestation,
            target_selection=target_selection,
            root_provisioner_id=roles.root_provisioner_id,
            root_verifier_id=roles.root_verifier_id,
            operator_id=roles.operator_id,
            evaluation_time=approved_at,
        )
        if root_reasons:
            reasons.append(RealTrialApprovalRegistryReason.ROOT_PROVISIONING_INVALID)
        access = source_context.read_authorization_context
        exact = (
            provisioning_request.approved_trial_record_digest
            == access.approved_trial.canonical_digest,
            provisioning_request.access_authorization_record_digest
            == access.authorization_record.canonical_digest,
            target_selection.selector_digest == access.selector.canonical_digest,
            target_selection.expected_classification_digest
            == access.classification_policy.canonical_digest,
            purpose.retention_policy_digest
            == access.access_policy.retention_policy_digest,
            purpose.closure_policy_digest
            == fixed_real_trial_closure_policy_digest(),
            closure_requirement.purpose_digest == purpose.canonical_digest,
            closure_requirement.access_authorization_record_digest
            == access.authorization_record.canonical_digest,
            approval_request.purpose_digest == purpose.canonical_digest,
            approval_request.root_identity_digest == root_identity.canonical_digest,
            approval_request.root_provisioning_request_digest
            == provisioning_request.canonical_digest,
            approval_request.root_attestation_digest
            == root_attestation.canonical_digest,
            approval_request.target_selection_digest
            == target_selection.canonical_digest,
            approval_request.access_authorization_record_digest
            == access.authorization_record.canonical_digest,
            approval_request.access_approval_digest
            == access.access_approval.canonical_digest,
            approval_request.approved_trial_record_digest
            == access.approved_trial.canonical_digest,
            approval_request.root_descriptor_digest
            == source_context.root_descriptor.canonical_digest,
            approval_request.resolver_policy_digest
            == source_context.resolver_policy.canonical_digest,
            approval_request.controlled_target_reference_digest
            == source_context.controlled_target_reference.canonical_digest,
            approval_request.closure_requirement_digest
            == closure_requirement.canonical_digest,
            security_review.approval_request_digest
            == approval_request.canonical_digest,
            security_review.root_attestation_digest
            == root_attestation.canonical_digest,
            security_review.target_selection_digest
            == target_selection.canonical_digest,
            security_review.resolver_policy_digest
            == source_context.resolver_policy.canonical_digest,
            governance_review.approval_request_digest
            == approval_request.canonical_digest,
            governance_review.purpose_digest == purpose.canonical_digest,
            governance_review.target_selection_digest
            == target_selection.canonical_digest,
            governance_review.closure_requirement_digest
            == closure_requirement.canonical_digest,
            governance_review.classification_digest
            == access.classification_policy.canonical_digest,
            governance_review.retention_policy_digest
            == access.access_policy.retention_policy_digest,
            governance_review.logging_policy_digest
            == access.access_policy.logging_policy_digest,
            governance_review.persistence_policy_digest
            == access.access_policy.persistence_policy_digest,
            execution_approval.approval_request_digest
            == approval_request.canonical_digest,
            execution_approval.security_review_digest
            == security_review.canonical_digest,
            execution_approval.governance_review_digest
            == governance_review.canonical_digest,
            execution_approval.operator_id == roles.operator_id,
        )
        if not all(exact):
            reasons.append(RealTrialApprovalRegistryReason.INVALID_CHAIN)
        if (
            security_review.result is not TrialAuthorizationReviewResult.APPROVED
            or governance_review.result
            is not TrialAuthorizationReviewResult.APPROVED
            or execution_approval.result is not TrialExecutionApprovalResult.APPROVED
        ):
            reasons.append(RealTrialApprovalRegistryReason.POLICY_INVALID)
        role_bindings = (
            provisioning_request.root_provisioner_id == roles.root_provisioner_id,
            root_attestation.generated_by == roles.root_verifier_id,
            approval_request.requester_id == roles.trial_requester_id,
            security_review.reviewer_id == roles.security_reviewer_id,
            governance_review.reviewer_id == roles.governance_reviewer_id,
            provisioning_request.operator_id == roles.operator_id,
            target_selection.operator_id == roles.operator_id,
            approval_request.operator_id == roles.operator_id,
            execution_approval.operator_id == roles.operator_id,
            execution_approval.approver_id == roles.execution_approver_id,
            access.access_approval.approver_id == roles.access_approver_id,
            access.operator_assignment.operator_id == roles.operator_id,
            access.authorization_record.operator_id == roles.operator_id,
        )
        if not all(role_bindings):
            reasons.append(RealTrialApprovalRegistryReason.ROLE_CONFLICT)
        expected_generation = len(self.records) + 1
        expected_predecessor = self.records[-1].canonical_digest if self.records else None
        if approval_generation != expected_generation:
            reasons.append(RealTrialApprovalRegistryReason.GENERATION_MISMATCH)
        if predecessor_approval_digest != expected_predecessor:
            reasons.append(RealTrialApprovalRegistryReason.PREDECESSOR_MISMATCH)
        if self.records and self.records[-1].lifecycle not in {
            ApprovedOneShotRealDataTrialLifecycle.REVOKED,
            ApprovedOneShotRealDataTrialLifecycle.SUPERSEDED,
            ApprovedOneShotRealDataTrialLifecycle.EXPIRED,
            ApprovedOneShotRealDataTrialLifecycle.CLOSED,
        }:
            reasons.append(RealTrialApprovalRegistryReason.LIFECYCLE_INVALID)
        replay = (
            (provisioning_request.canonical_digest, self._state.used_root_request_digests),
            (root_identity.canonical_digest, self._state.used_root_identity_digests),
            (root_attestation.canonical_digest, self._state.used_root_attestation_digests),
            (target_selection.canonical_digest, self._state.used_target_selection_digests),
            (approval_request.canonical_digest, self._state.used_approval_request_digests),
            (security_review.canonical_digest, self._state.used_security_review_digests),
            (governance_review.canonical_digest, self._state.used_governance_review_digests),
            (execution_approval.canonical_digest, self._state.used_execution_approval_digests),
        )
        if any(value in used for value, used in replay):
            reasons.append(RealTrialApprovalRegistryReason.REPLAY)
        times = (
            approval_request.requested_at,
            approval_request.expires_at,
            security_review.reviewed_at,
            governance_review.reviewed_at,
            execution_approval.approved_at,
            execution_approval.expires_at,
            approved_at,
            expires_at,
        )
        latest_expiry = min(
            approval_request.expires_at,
            execution_approval.expires_at,
            root_attestation.expires_at,
            provisioning_request.expires_at,
            access.authorization_record.expires_at,
            access.operator_assignment.expires_at,
            access.access_approval.expires_at,
        )
        if (
            not all(_is_utc(item) for item in times)
            or not (
                target_selection.selected_at
                <= closure_requirement.created_at
                < approval_request.requested_at
                < security_review.reviewed_at
                < governance_review.reviewed_at
                < execution_approval.approved_at
                <= approved_at
                < expires_at
                <= latest_expiry
            )
            or approved_at - approval_request.requested_at
            > MAX_ONE_SHOT_TRIAL_APPROVAL_AGE
        ):
            reasons.append(RealTrialApprovalRegistryReason.TEMPORAL_INVALID)
        if not is_identifier(approved_trial_id):
            reasons.append(RealTrialApprovalRegistryReason.INVALID_CHAIN)
        if reasons:
            return self._result(
                False, tuple(dict.fromkeys(reasons)), None, side_effects
            )
        try:
            if fault is RealTrialApprovalRegistryFault.CANDIDATE_STATE:
                raise RuntimeError
            record = ApprovedOneShotRealDataTrial(
                approved_trial_id,
                source_context.canonical_digest,
                purpose.canonical_digest,
                provisioning_request.canonical_digest,
                root_identity.canonical_digest,
                root_attestation.canonical_digest,
                target_selection.canonical_digest,
                closure_requirement.canonical_digest,
                approval_request.canonical_digest,
                security_review.canonical_digest,
                governance_review.canonical_digest,
                execution_approval.canonical_digest,
                access.authorization_record.canonical_digest,
                access.operator_assignment.canonical_digest,
                access.usage_contract.canonical_digest,
                source_context.root_descriptor.canonical_digest,
                source_context.resolver_policy.canonical_digest,
                source_context.controlled_target_reference.canonical_digest,
                roles.operator_id,
                approval_generation,
                predecessor_approval_digest,
                approved_at,
                expires_at,
                approved_at,
                _marker=_APPROVED_TRIAL_MARKER,
            )
            if record.canonical_digest in self._state.used_record_digests:
                return self._result(
                    False,
                    (RealTrialApprovalRegistryReason.REPLAY,),
                    None,
                    side_effects,
                )
            candidate = replace(
                self._state,
                records=self.records + (record,),
                used_root_request_digests=self._state.used_root_request_digests
                | {provisioning_request.canonical_digest},
                used_root_identity_digests=self._state.used_root_identity_digests
                | {root_identity.canonical_digest},
                used_root_attestation_digests=self._state.used_root_attestation_digests
                | {root_attestation.canonical_digest},
                used_target_selection_digests=self._state.used_target_selection_digests
                | {target_selection.canonical_digest},
                used_approval_request_digests=self._state.used_approval_request_digests
                | {approval_request.canonical_digest},
                used_security_review_digests=self._state.used_security_review_digests
                | {security_review.canonical_digest},
                used_governance_review_digests=self._state.used_governance_review_digests
                | {governance_review.canonical_digest},
                used_execution_approval_digests=self._state.used_execution_approval_digests
                | {execution_approval.canonical_digest},
                used_record_digests=self._state.used_record_digests
                | {record.canonical_digest},
                write_count=self.write_count + 1,
                mutation_count=self.mutation_count + 1,
                event_count=self.event_count + 1,
            )
            if fault is RealTrialApprovalRegistryFault.BEFORE_SWAP:
                raise RuntimeError
            self._state = candidate
            return self._result(True, (), record, side_effects)
        except (RuntimeError, RealTrialApprovalError):
            return self._result(
                False,
                (RealTrialApprovalRegistryReason.COMMIT_FAULT,),
                None,
                side_effects,
            )

    def transition(
        self,
        *,
        source_record: ApprovedOneShotRealDataTrial,
        new_record_id: str,
        lifecycle: ApprovedOneShotRealDataTrialLifecycle,
        transitioned_at: datetime,
    ) -> RealTrialApprovalRegistryResult:
        side_effects = RealTrialApprovalSideEffectAccounting()
        if (
            not self.records
            or self.records[-1].canonical_digest != source_record.canonical_digest
            or not canonical_object_valid(source_record)
            or not is_identifier(new_record_id)
            or not isinstance(lifecycle, ApprovedOneShotRealDataTrialLifecycle)
            or not _is_utc(transitioned_at)
        ):
            return self._result(
                False,
                (RealTrialApprovalRegistryReason.LIFECYCLE_INVALID,),
                None,
                side_effects,
            )
        allowed = {
            ApprovedOneShotRealDataTrialLifecycle.APPROVED: {
                ApprovedOneShotRealDataTrialLifecycle.EXPIRED,
                ApprovedOneShotRealDataTrialLifecycle.REVOKED,
                ApprovedOneShotRealDataTrialLifecycle.SUPERSEDED,
                ApprovedOneShotRealDataTrialLifecycle.EXECUTION_PENDING,
            },
            ApprovedOneShotRealDataTrialLifecycle.EXECUTION_PENDING: {
                ApprovedOneShotRealDataTrialLifecycle.EXPIRED,
                ApprovedOneShotRealDataTrialLifecycle.REVOKED,
                ApprovedOneShotRealDataTrialLifecycle.CLOSED,
            },
        }
        if (
            lifecycle not in allowed.get(source_record.lifecycle, set())
            or transitioned_at < source_record.lifecycle_changed_at
            or transitioned_at > source_record.expires_at
            or (
                lifecycle is ApprovedOneShotRealDataTrialLifecycle.EXPIRED
                and transitioned_at != source_record.expires_at
            )
        ):
            return self._result(
                False,
                (RealTrialApprovalRegistryReason.LIFECYCLE_INVALID,),
                None,
                side_effects,
            )
        try:
            transitioned = ApprovedOneShotRealDataTrial(
                new_record_id,
                source_record.source_context_digest,
                source_record.purpose_digest,
                source_record.root_provisioning_request_digest,
                source_record.root_identity_digest,
                source_record.root_attestation_digest,
                source_record.target_selection_digest,
                source_record.closure_requirement_digest,
                source_record.approval_request_digest,
                source_record.security_review_digest,
                source_record.governance_review_digest,
                source_record.execution_approval_digest,
                source_record.access_authorization_record_digest,
                source_record.access_operator_assignment_digest,
                source_record.access_usage_contract_digest,
                source_record.root_descriptor_digest,
                source_record.resolver_policy_digest,
                source_record.controlled_target_reference_digest,
                source_record.operator_id,
                source_record.approval_generation + 1,
                source_record.canonical_digest,
                source_record.approved_at,
                source_record.expires_at,
                transitioned_at,
                source_record.state,
                lifecycle,
                _marker=_APPROVED_TRIAL_MARKER,
            )
        except RealTrialApprovalError:
            return self._result(
                False,
                (RealTrialApprovalRegistryReason.LIFECYCLE_INVALID,),
                None,
                side_effects,
            )
        self._state = replace(
            self._state,
            records=self.records + (transitioned,),
            used_record_digests=self._state.used_record_digests
            | {transitioned.canonical_digest},
            write_count=self.write_count + 1,
            mutation_count=self.mutation_count + 1,
            event_count=self.event_count + 1,
        )
        return self._result(True, (), transitioned, side_effects)

    def _result(
        self,
        applied: bool,
        reasons: tuple[RealTrialApprovalRegistryReason, ...],
        record: ApprovedOneShotRealDataTrial | None,
        side_effects: RealTrialApprovalSideEffectAccounting,
    ) -> RealTrialApprovalRegistryResult:
        return RealTrialApprovalRegistryResult(
            applied,
            reasons,
            record,
            side_effects,
            self.write_count,
            self.mutation_count,
            self.event_count,
        )


@dataclass(frozen=True)
class OneShotTrialApprovalReadinessDecision:
    state: OneShotTrialApprovalReadinessState
    eligible_for_explicit_one_shot_real_data_execution: bool
    actual_read_executed: bool
    real_data_use_authorized: bool
    embedding_authorized: bool
    persistence_authorized: bool
    external_side_effect_count: int

    @property
    def eligible_for_explicit_one_shot_execution_review(self) -> bool:
        return self.eligible_for_explicit_one_shot_real_data_execution


def evaluate_one_shot_trial_approval_readiness(
    record: ApprovedOneShotRealDataTrial,
    *,
    evaluation_time: datetime,
) -> OneShotTrialApprovalReadinessDecision:
    state = OneShotTrialApprovalReadinessState.NOT_APPROVED
    eligible = False
    if canonical_object_valid(record) and _is_utc(evaluation_time):
        if evaluation_time >= record.expires_at:
            state = OneShotTrialApprovalReadinessState.EXPIRED
        elif record.lifecycle is ApprovedOneShotRealDataTrialLifecycle.REVOKED:
            state = OneShotTrialApprovalReadinessState.REVOKED
        elif record.lifecycle is ApprovedOneShotRealDataTrialLifecycle.SUPERSEDED:
            state = OneShotTrialApprovalReadinessState.SUPERSEDED
        elif record.lifecycle is ApprovedOneShotRealDataTrialLifecycle.EXECUTION_PENDING:
            state = OneShotTrialApprovalReadinessState.EXECUTION_PENDING
        elif record.lifecycle is ApprovedOneShotRealDataTrialLifecycle.CLOSED:
            state = OneShotTrialApprovalReadinessState.CLOSED
        elif record.lifecycle is ApprovedOneShotRealDataTrialLifecycle.APPROVED:
            state = (
                OneShotTrialApprovalReadinessState.
                ELIGIBLE_FOR_EXPLICIT_ONE_SHOT_EXECUTION_REVIEW
            )
            eligible = True
    return OneShotTrialApprovalReadinessDecision(
        state,
        eligible,
        False,
        False,
        False,
        False,
        0,
    )


__all__ = [
    "MAX_ONE_SHOT_TRIAL_APPROVAL_AGE",
    "ApprovedOneShotRealDataTrial",
    "ApprovedOneShotRealDataTrialLifecycle",
    "ApprovedOneShotRealDataTrialState",
    "OneShotTrialApprovalReadinessDecision",
    "OneShotTrialApprovalReadinessState",
    "RealTrialApprovalError",
    "RealTrialApprovalRegistryFault",
    "RealTrialApprovalRegistryReason",
    "RealTrialApprovalRegistryResult",
    "RealTrialApprovalRequest",
    "RealTrialApprovalRoleContext",
    "RealTrialApprovalSideEffectAccounting",
    "RealTrialApprovalSourceContext",
    "TestOnlyRealTrialApprovalRegistry",
    "TrialAuthorizationReviewResult",
    "TrialDataGovernanceReview",
    "TrialExecutionApproval",
    "TrialExecutionApprovalResult",
    "TrialSecurityReview",
    "evaluate_one_shot_trial_approval_readiness",
    "validate_real_trial_approval_source",
]
