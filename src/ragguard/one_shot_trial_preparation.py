from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    RealDataDocumentClass,
)
from ragguard.real_data_access_authorization import (
    RealDataAccessApprovalResult,
    RealDataAccessAuthorizationLifecycle,
    RealDataAccessAuthorizationState,
)
from ragguard.real_data_trial import RealDataClass
from ragguard.real_target_resolver import (
    ControlledTargetReference,
    RealTargetResolverPolicy,
    TrialRootDescriptor,
)
from ragguard.real_trial_approval import (
    ApprovedOneShotRealDataTrial,
    ApprovedOneShotRealDataTrialLifecycle,
    ApprovedOneShotRealDataTrialState,
    RealTrialApprovalRequest,
    RealTrialApprovalRoleContext,
    RealTrialApprovalSourceContext,
    TrialAuthorizationReviewResult,
    TrialDataGovernanceReview,
    TrialExecutionApproval,
    TrialExecutionApprovalResult,
    TrialSecurityReview,
    validate_real_trial_approval_source,
)
from ragguard.real_trial_root import (
    LinkReparseVerificationResult,
    NetworkIsolationVerificationResult,
    PermissionVerificationResult,
    RealTrialClosureRequirement,
    RealTrialPurpose,
    RealTrialPurposeClass,
    RealTrialRootIdentity,
    RealTrialRootProvisioningRequest,
    RealTrialTargetSelection,
    RootConfinementVerificationResult,
    RootProvisioningAttestation,
    RootProvisioningAttestationState,
    RootProvisioningVerificationState,
    WriteProhibitionVerificationResult,
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


class OneShotTrialPreparationError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class ExecutionPreparationState(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_ROOT_PROVISIONING = "needs_root_provisioning"
    NEEDS_TARGET_BINDING = "needs_target_binding"
    NEEDS_OPERATOR_BINDING = "needs_operator_binding"
    NEEDS_TRIAL_APPROVAL = "needs_trial_approval"
    NEEDS_ACCESS_AUTHORIZATION = "needs_access_authorization"
    NEEDS_CLOSURE_REQUIREMENTS = "needs_closure_requirements"
    READY_FOR_EXPLICIT_EXECUTION_APPROVAL = (
        "ready_for_explicit_execution_approval"
    )


class ExecutionPreparationReason(str, Enum):
    INVALID_PACKET = "invalid_packet"
    INVALID_REQUEST = "invalid_request"
    FORGED_OBJECT_CHAIN = "forged_object_chain"
    TRIAL_APPROVAL_INVALID = "trial_approval_invalid"
    ACCESS_AUTHORIZATION_INVALID = "access_authorization_invalid"
    ROOT_PROVISIONING_INVALID = "root_provisioning_invalid"
    TARGET_BINDING_INVALID = "target_binding_invalid"
    OPERATOR_BINDING_INVALID = "operator_binding_invalid"
    PURPOSE_INVALID = "purpose_invalid"
    POLICY_INVALID = "policy_invalid"
    CLOSURE_REQUIREMENTS_INVALID = "closure_requirements_invalid"
    TEMPORAL_INVALID = "temporal_invalid"
    ROLE_CONFLICT = "role_conflict"
    REPLAY = "replay"


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
            else list(item)
            if isinstance(item, tuple)
            else item
        )
        for key, item in vars(value).items()
        if key != "canonical_digest"
    }


@dataclass(frozen=True, repr=False)
class OneShotTrialExecutionPacket(_Canonical):
    packet_id: str
    approved_trial_digest: str
    access_authorization_digest: str
    root_identity_digest: str
    root_attestation_digest: str
    target_selection_digest: str
    operator_assignment_digest: str
    operator_id: str
    purpose_digest: str
    purpose_class: RealTrialPurposeClass
    resolver_policy_digest: str
    reader_policy_digest: str
    closure_requirement_digest: str
    allowed_read_count: int
    stage_ceiling: RAGStage
    raw_retention_allowed: bool
    raw_logging_allowed: bool
    raw_cache_allowed: bool
    persistence_allowed: bool
    export_allowed: bool
    network_allowed: bool
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        digests = tuple(
            item for key, item in vars(self).items() if key.endswith("_digest")
        )
        prohibited = (
            self.raw_retention_allowed,
            self.raw_logging_allowed,
            self.raw_cache_allowed,
            self.persistence_allowed,
            self.export_allowed,
            self.network_allowed,
        )
        if (
            not is_identifier(self.packet_id)
            or not is_identifier(self.operator_id)
            or not all(is_digest(item) for item in digests)
            or self.purpose_class
            is not RealTrialPurposeClass.LOCAL_RAG_CONFIDENTIALITY_TRIAL
            or self.allowed_read_count != 1
            or self.stage_ceiling is not RAGStage.CHUNKING
            or not all(type(item) is bool for item in prohibited)
            or any(prohibited)
            or not _is_utc(self.issued_at)
            or not _is_utc(self.expires_at)
            or self.expires_at <= self.issued_at
        ):
            raise OneShotTrialPreparationError("execution_packet_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class ExecutionPreparationRequest(_Canonical):
    preparation_request_id: str
    packet_digest: str
    requested_by: str
    requested_at: datetime
    evaluation_time: datetime

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.preparation_request_id)
            or not is_digest(self.packet_digest)
            or not is_identifier(self.requested_by)
            or not _is_utc(self.requested_at)
            or not _is_utc(self.evaluation_time)
            or self.evaluation_time < self.requested_at
        ):
            raise OneShotTrialPreparationError("preparation_request_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class ExecutionPreparationSideEffectAccounting(_Canonical):
    actual_file_open_count: int = 0
    actual_file_read_count: int = 0
    actual_real_data_access_count: int = 0
    arbitrary_filesystem_read_count: int = 0
    directory_scan_count: int = 0
    local_rag_material_access_count: int = 0
    restricted_material_access_count: int = 0
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
        if not all(
            type(item) is int and item >= 0 for item in vars(self).values()
        ):
            raise OneShotTrialPreparationError("side_effect_accounting_invalid")
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


@dataclass(frozen=True, repr=False)
class ExecutionPreparationSafeSummary(_Canonical):
    packet_id: str
    packet_digest: str
    approved_trial_digest: str
    access_authorization_digest: str
    root_identity_digest: str
    target_selection_digest: str
    operator_id: str
    purpose_class: RealTrialPurposeClass
    allowed_read_count: int
    stage_ceiling: RAGStage
    raw_retention_allowed: bool
    raw_logging_allowed: bool
    raw_cache_allowed: bool
    persistence_allowed: bool
    export_allowed: bool
    network_allowed: bool
    expires_at: datetime
    closure_requirement_digest: str
    readiness_decision: ExecutionPreparationState
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        digests = (
            self.packet_digest,
            self.approved_trial_digest,
            self.access_authorization_digest,
            self.root_identity_digest,
            self.target_selection_digest,
            self.closure_requirement_digest,
        )
        booleans = (
            self.raw_retention_allowed,
            self.raw_logging_allowed,
            self.raw_cache_allowed,
            self.persistence_allowed,
            self.export_allowed,
            self.network_allowed,
        )
        if (
            not is_identifier(self.packet_id)
            or not is_identifier(self.operator_id)
            or not all(is_digest(item) for item in digests)
            or self.purpose_class
            is not RealTrialPurposeClass.LOCAL_RAG_CONFIDENTIALITY_TRIAL
            or self.allowed_read_count != 1
            or self.stage_ceiling is not RAGStage.CHUNKING
            or any(item is not False for item in booleans)
            or not _is_utc(self.expires_at)
            or not isinstance(self.readiness_decision, ExecutionPreparationState)
            or not isinstance(self.reason_codes, tuple)
            or not all(isinstance(item, str) for item in self.reason_codes)
        ):
            raise OneShotTrialPreparationError("safe_summary_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class ExecutionPreparationDecision(_Canonical):
    state: ExecutionPreparationState
    reasons: tuple[ExecutionPreparationReason, ...]
    packet_digest: str
    request_digest: str
    ready_for_explicit_execution_approval: bool
    execution_authorized: bool
    file_read_executed: bool
    safe_summary: ExecutionPreparationSafeSummary | None
    side_effects: ExecutionPreparationSideEffectAccounting

    def __post_init__(self) -> None:
        ready = self.state is (
            ExecutionPreparationState.READY_FOR_EXPLICIT_EXECUTION_APPROVAL
        )
        if (
            not isinstance(self.state, ExecutionPreparationState)
            or not isinstance(self.reasons, tuple)
            or not all(isinstance(item, ExecutionPreparationReason) for item in self.reasons)
            or not is_digest(self.packet_digest)
            or not is_digest(self.request_digest)
            or self.ready_for_explicit_execution_approval is not ready
            or self.execution_authorized is not False
            or self.file_read_executed is not False
            or (
                self.safe_summary is not None
                and not canonical_object_valid(self.safe_summary)
            )
            or not canonical_object_valid(self.side_effects)
            or not self.side_effects.all_zero
        ):
            raise OneShotTrialPreparationError("preparation_decision_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {
            "execution_authorized": self.execution_authorized,
            "file_read_executed": self.file_read_executed,
            "packet_digest": self.packet_digest,
            "ready_for_explicit_execution_approval": (
                self.ready_for_explicit_execution_approval
            ),
            "reasons": [item.value for item in self.reasons],
            "request_digest": self.request_digest,
            "safe_summary_digest": (
                self.safe_summary.canonical_digest
                if self.safe_summary is not None
                else None
            ),
            "side_effects_digest": self.side_effects.canonical_digest,
            "state": self.state.value,
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True)
class _PreparationRegistryState:
    prepared_packet_digests: frozenset[str] = frozenset()
    used_request_digests: frozenset[str] = frozenset()
    preparation_count: int = 0


def _canonical(value: object, expected_type: type[object]) -> bool:
    return isinstance(value, expected_type) and canonical_object_valid(value)


def _summary(
    packet: OneShotTrialExecutionPacket,
    state: ExecutionPreparationState,
    reasons: tuple[ExecutionPreparationReason, ...],
) -> ExecutionPreparationSafeSummary:
    return ExecutionPreparationSafeSummary(
        packet.packet_id,
        packet.canonical_digest,
        packet.approved_trial_digest,
        packet.access_authorization_digest,
        packet.root_identity_digest,
        packet.target_selection_digest,
        packet.operator_id,
        packet.purpose_class,
        packet.allowed_read_count,
        packet.stage_ceiling,
        packet.raw_retention_allowed,
        packet.raw_logging_allowed,
        packet.raw_cache_allowed,
        packet.persistence_allowed,
        packet.export_allowed,
        packet.network_allowed,
        packet.expires_at,
        packet.closure_requirement_digest,
        state,
        tuple(item.value for item in reasons),
    )


def _decision(
    *,
    state: ExecutionPreparationState,
    reasons: tuple[ExecutionPreparationReason, ...],
    packet: OneShotTrialExecutionPacket,
    request: ExecutionPreparationRequest,
    include_summary: bool = True,
) -> ExecutionPreparationDecision:
    return ExecutionPreparationDecision(
        state,
        tuple(dict.fromkeys(reasons)),
        packet.canonical_digest,
        request.canonical_digest,
        state is ExecutionPreparationState.READY_FOR_EXPLICIT_EXECUTION_APPROVAL,
        False,
        False,
        _summary(packet, state, tuple(dict.fromkeys(reasons)))
        if include_summary
        else None,
        ExecutionPreparationSideEffectAccounting(),
    )


class TestOnlyExecutionPreparationRegistry:
    """In-memory replay boundary; it has no production write capability."""

    __test__ = False

    def __init__(self) -> None:
        self._state = _PreparationRegistryState()

    @property
    def prepared_packet_digests(self) -> frozenset[str]:
        return self._state.prepared_packet_digests

    @property
    def used_request_digests(self) -> frozenset[str]:
        return self._state.used_request_digests

    @property
    def preparation_count(self) -> int:
        return self._state.preparation_count

    @property
    def replay_snapshot(self) -> tuple[frozenset[str], frozenset[str]]:
        return (
            self._state.prepared_packet_digests,
            self._state.used_request_digests,
        )

    def prepare(
        self,
        *,
        packet: OneShotTrialExecutionPacket,
        request: ExecutionPreparationRequest,
        approved_trial: ApprovedOneShotRealDataTrial,
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
        closure_requirement: RealTrialClosureRequirement | None,
        approval_request: RealTrialApprovalRequest,
        security_review: TrialSecurityReview,
        governance_review: TrialDataGovernanceReview,
        execution_approval: TrialExecutionApproval,
        roles: RealTrialApprovalRoleContext,
    ) -> ExecutionPreparationDecision:
        state_before = self._state
        decision = _evaluate_preparation(
            replay_snapshot=self.replay_snapshot,
            packet=packet,
            request=request,
            approved_trial=approved_trial,
            source_context=source_context,
            purpose=purpose,
            provisioning_request=provisioning_request,
            root_identity=root_identity,
            root_confinement=root_confinement,
            link_reparse=link_reparse,
            permission=permission,
            write_prohibition=write_prohibition,
            network_isolation=network_isolation,
            root_attestation=root_attestation,
            target_selection=target_selection,
            closure_requirement=closure_requirement,
            approval_request=approval_request,
            security_review=security_review,
            governance_review=governance_review,
            execution_approval=execution_approval,
            roles=roles,
        )
        if decision.ready_for_explicit_execution_approval:
            candidate = replace(
                state_before,
                prepared_packet_digests=(
                    state_before.prepared_packet_digests | {packet.canonical_digest}
                ),
                used_request_digests=(
                    state_before.used_request_digests | {request.canonical_digest}
                ),
                preparation_count=state_before.preparation_count + 1,
            )
            self._state = candidate
        return decision


def _evaluate_preparation(
    *,
    replay_snapshot: tuple[frozenset[str], frozenset[str]],
    packet: OneShotTrialExecutionPacket,
    request: ExecutionPreparationRequest,
    approved_trial: ApprovedOneShotRealDataTrial,
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
    closure_requirement: RealTrialClosureRequirement | None,
    approval_request: RealTrialApprovalRequest,
    security_review: TrialSecurityReview,
    governance_review: TrialDataGovernanceReview,
    execution_approval: TrialExecutionApproval,
    roles: RealTrialApprovalRoleContext,
) -> ExecutionPreparationDecision:
    if not _canonical(packet, OneShotTrialExecutionPacket):
        return _decision(
            state=ExecutionPreparationState.INELIGIBLE,
            reasons=(ExecutionPreparationReason.INVALID_PACKET,),
            packet=packet,
            request=request,
            include_summary=False,
        )
    if (
        not _canonical(request, ExecutionPreparationRequest)
        or request.packet_digest != packet.canonical_digest
    ):
        return _decision(
            state=ExecutionPreparationState.INELIGIBLE,
            reasons=(ExecutionPreparationReason.INVALID_REQUEST,),
            packet=packet,
            request=request,
        )
    if (
        packet.canonical_digest in replay_snapshot[0]
        or request.canonical_digest in replay_snapshot[1]
    ):
        return _decision(
            state=ExecutionPreparationState.INELIGIBLE,
            reasons=(ExecutionPreparationReason.REPLAY,),
            packet=packet,
            request=request,
        )

    trial_objects = (
        approved_trial,
        approval_request,
        security_review,
        governance_review,
        execution_approval,
    )
    if not (
        _canonical(approved_trial, ApprovedOneShotRealDataTrial)
        and _canonical(approval_request, RealTrialApprovalRequest)
        and _canonical(security_review, TrialSecurityReview)
        and _canonical(governance_review, TrialDataGovernanceReview)
        and _canonical(execution_approval, TrialExecutionApproval)
        and all(canonical_object_valid(item) for item in trial_objects)
    ):
        return _decision(
            state=ExecutionPreparationState.NEEDS_TRIAL_APPROVAL,
            reasons=(
                ExecutionPreparationReason.FORGED_OBJECT_CHAIN,
                ExecutionPreparationReason.TRIAL_APPROVAL_INVALID,
            ),
            packet=packet,
            request=request,
        )

    if not _canonical(source_context, RealTrialApprovalSourceContext):
        return _decision(
            state=ExecutionPreparationState.NEEDS_ACCESS_AUTHORIZATION,
            reasons=(ExecutionPreparationReason.ACCESS_AUTHORIZATION_INVALID,),
            packet=packet,
            request=request,
        )
    try:
        access_reasons = validate_real_trial_approval_source(
            source_context, evaluation_time=request.evaluation_time
        )
    except (AttributeError, TypeError, ValueError):
        access_reasons = ("invalid",)
    if access_reasons:
        return _decision(
            state=ExecutionPreparationState.NEEDS_ACCESS_AUTHORIZATION,
            reasons=(ExecutionPreparationReason.ACCESS_AUTHORIZATION_INVALID,),
            packet=packet,
            request=request,
        )
    access = source_context.read_authorization_context

    if not _canonical(target_selection, RealTrialTargetSelection):
        return _decision(
            state=ExecutionPreparationState.NEEDS_TARGET_BINDING,
            reasons=(ExecutionPreparationReason.TARGET_BINDING_INVALID,),
            packet=packet,
            request=request,
        )
    target_exact = (
        target_selection.max_documents == 1,
        target_selection.data_class is RealDataClass.INTERNAL_LOW,
        target_selection.document_class
        is RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,
        target_selection.controlled_target_reference_digest
        == source_context.controlled_target_reference.canonical_digest,
        target_selection.target_identity_digest
        == source_context.controlled_target_reference.expected_content_identity_digest,
        packet.target_selection_digest == target_selection.canonical_digest,
    )
    if not all(target_exact):
        return _decision(
            state=ExecutionPreparationState.NEEDS_TARGET_BINDING,
            reasons=(ExecutionPreparationReason.TARGET_BINDING_INVALID,),
            packet=packet,
            request=request,
        )

    if not _canonical(roles, RealTrialApprovalRoleContext):
        return _decision(
            state=ExecutionPreparationState.NEEDS_OPERATOR_BINDING,
            reasons=(ExecutionPreparationReason.ROLE_CONFLICT,),
            packet=packet,
            request=request,
        )
    role_values = tuple(
        item for key, item in vars(roles).items() if key != "canonical_digest"
    )
    role_exact = (
        len(set(role_values)) == 8,
        roles.root_provisioner_id == provisioning_request.root_provisioner_id,
        roles.root_verifier_id == root_attestation.generated_by,
        roles.trial_requester_id == approval_request.requester_id,
        roles.security_reviewer_id == security_review.reviewer_id,
        roles.governance_reviewer_id == governance_review.reviewer_id,
        roles.operator_id == access.operator_assignment.operator_id,
        roles.operator_id == approved_trial.operator_id,
        roles.operator_id == execution_approval.operator_id,
        roles.operator_id == target_selection.operator_id,
        roles.operator_id == packet.operator_id,
        roles.execution_approver_id == execution_approval.approver_id,
        roles.access_approver_id == access.access_approval.approver_id,
        packet.operator_assignment_digest
        == access.operator_assignment.canonical_digest,
    )
    if not all(role_exact):
        return _decision(
            state=ExecutionPreparationState.NEEDS_OPERATOR_BINDING,
            reasons=(ExecutionPreparationReason.OPERATOR_BINDING_INVALID,),
            packet=packet,
            request=request,
        )

    if not _canonical(purpose, RealTrialPurpose):
        return _decision(
            state=ExecutionPreparationState.INELIGIBLE,
            reasons=(ExecutionPreparationReason.PURPOSE_INVALID,),
            packet=packet,
            request=request,
        )
    purpose_exact = (
        purpose.purpose_class
        is RealTrialPurposeClass.LOCAL_RAG_CONFIDENTIALITY_TRIAL,
        purpose.allowed_processing_stage is RAGStage.CHUNKING,
        purpose.retention_class is RealDataAccessRetentionClass.NONE,
        purpose.closure_required,
        packet.purpose_digest == purpose.canonical_digest,
        packet.purpose_class is purpose.purpose_class,
        packet.stage_ceiling is purpose.allowed_processing_stage,
    )
    if not all(purpose_exact):
        return _decision(
            state=ExecutionPreparationState.INELIGIBLE,
            reasons=(ExecutionPreparationReason.PURPOSE_INVALID,),
            packet=packet,
            request=request,
        )

    if not _canonical(closure_requirement, RealTrialClosureRequirement):
        return _decision(
            state=ExecutionPreparationState.NEEDS_CLOSURE_REQUIREMENTS,
            reasons=(ExecutionPreparationReason.CLOSURE_REQUIREMENTS_INVALID,),
            packet=packet,
            request=request,
        )
    closure_required = (
        closure_requirement.one_shot_receipt_required,
        closure_requirement.usage_exhaustion_required,
        closure_requirement.classification_evidence_required,
        closure_requirement.masking_evidence_required,
        closure_requirement.post_read_evidence_required,
        closure_requirement.closure_record_required,
        closure_requirement.closure_review_required,
    )
    closure_prohibited = (
        closure_requirement.downstream_processing_authorized,
        closure_requirement.embedding_authorized,
        closure_requirement.persistence_authorized,
        closure_requirement.export_authorized,
    )
    if (
        not all(item is True for item in closure_required)
        or any(item is not False for item in closure_prohibited)
        or closure_requirement.purpose_digest != purpose.canonical_digest
        or closure_requirement.access_authorization_record_digest
        != access.authorization_record.canonical_digest
        or packet.closure_requirement_digest
        != closure_requirement.canonical_digest
    ):
        return _decision(
            state=ExecutionPreparationState.NEEDS_CLOSURE_REQUIREMENTS,
            reasons=(ExecutionPreparationReason.CLOSURE_REQUIREMENTS_INVALID,),
            packet=packet,
            request=request,
        )

    root_objects = (
        (provisioning_request, RealTrialRootProvisioningRequest),
        (root_identity, RealTrialRootIdentity),
        (root_confinement, RootConfinementVerificationResult),
        (link_reparse, LinkReparseVerificationResult),
        (permission, PermissionVerificationResult),
        (write_prohibition, WriteProhibitionVerificationResult),
        (network_isolation, NetworkIsolationVerificationResult),
        (root_attestation, RootProvisioningAttestation),
        (source_context.root_descriptor, TrialRootDescriptor),
        (source_context.resolver_policy, RealTargetResolverPolicy),
        (source_context.controlled_target_reference, ControlledTargetReference),
    )
    if not all(_canonical(item, expected) for item, expected in root_objects):
        return _decision(
            state=ExecutionPreparationState.NEEDS_ROOT_PROVISIONING,
            reasons=(ExecutionPreparationReason.ROOT_PROVISIONING_INVALID,),
            packet=packet,
            request=request,
        )
    try:
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
            evaluation_time=request.evaluation_time,
        )
    except (AttributeError, TypeError, ValueError):
        root_reasons = ("invalid",)
    root_exact = (
        packet.root_identity_digest == root_identity.canonical_digest,
        packet.root_attestation_digest == root_attestation.canonical_digest,
        packet.resolver_policy_digest
        == source_context.resolver_policy.canonical_digest,
        packet.reader_policy_digest
        == source_context.resolver_policy.canonical_digest,
        packet.reader_policy_digest
        == approval_request.v0_27_reader_policy_digest,
        root_attestation.result is RootProvisioningAttestationState.APPROVED,
        all(
            item.result is RootProvisioningVerificationState.PASSED
            for item in (
                root_confinement,
                link_reparse,
                permission,
                write_prohibition,
                network_isolation,
            )
        ),
    )
    if root_reasons or not all(root_exact):
        return _decision(
            state=ExecutionPreparationState.NEEDS_ROOT_PROVISIONING,
            reasons=(ExecutionPreparationReason.ROOT_PROVISIONING_INVALID,),
            packet=packet,
            request=request,
        )

    authorization = access.authorization_record
    usage = access.usage_contract
    policy = access.access_policy
    access_exact = (
        packet.access_authorization_digest == authorization.canonical_digest,
        packet.allowed_read_count == 1,
        authorization.state
        is RealDataAccessAuthorizationState.AUTHORIZED_FOR_LIMITED_READ_EXECUTION_REVIEW,
        authorization.lifecycle is RealDataAccessAuthorizationLifecycle.AUTHORIZED,
        authorization.allowed_read_count == 1,
        authorization.remaining_read_count == 1,
        usage.authorization_record_digest == authorization.canonical_digest,
        usage.allowed_read_count == 1,
        usage.remaining_read_count == 1,
        access.access_approval.result is RealDataAccessApprovalResult.APPROVED,
        policy.retention_class is RealDataAccessRetentionClass.NONE,
        policy.logging_class is RealDataAccessLoggingClass.NONE,
        policy.cache_class is RealDataAccessCacheClass.NONE,
        policy.persistence_class is RealDataAccessPersistenceClass.NONE,
        policy.export_class is RealDataAccessExportClass.PROHIBITED,
        policy.network_class is RealDataAccessNetworkClass.PROHIBITED,
    )
    if not all(access_exact):
        return _decision(
            state=ExecutionPreparationState.NEEDS_ACCESS_AUTHORIZATION,
            reasons=(ExecutionPreparationReason.ACCESS_AUTHORIZATION_INVALID,),
            packet=packet,
            request=request,
        )

    approval_exact = (
        packet.approved_trial_digest == approved_trial.canonical_digest,
        approved_trial.source_context_digest == source_context.canonical_digest,
        approved_trial.purpose_digest == purpose.canonical_digest,
        approved_trial.root_provisioning_request_digest
        == provisioning_request.canonical_digest,
        approved_trial.root_identity_digest == root_identity.canonical_digest,
        approved_trial.root_attestation_digest == root_attestation.canonical_digest,
        approved_trial.target_selection_digest == target_selection.canonical_digest,
        approved_trial.closure_requirement_digest
        == closure_requirement.canonical_digest,
        approved_trial.approval_request_digest == approval_request.canonical_digest,
        approved_trial.security_review_digest == security_review.canonical_digest,
        approved_trial.governance_review_digest == governance_review.canonical_digest,
        approved_trial.execution_approval_digest
        == execution_approval.canonical_digest,
        approved_trial.access_authorization_record_digest
        == authorization.canonical_digest,
        approved_trial.access_operator_assignment_digest
        == access.operator_assignment.canonical_digest,
        approved_trial.access_usage_contract_digest == usage.canonical_digest,
        approved_trial.root_descriptor_digest
        == source_context.root_descriptor.canonical_digest,
        approved_trial.resolver_policy_digest
        == source_context.resolver_policy.canonical_digest,
        approved_trial.controlled_target_reference_digest
        == source_context.controlled_target_reference.canonical_digest,
        approved_trial.state
        is ApprovedOneShotRealDataTrialState.APPROVED_FOR_ONE_SHOT_EXECUTION_REVIEW,
        approved_trial.lifecycle is ApprovedOneShotRealDataTrialLifecycle.APPROVED,
        security_review.result is TrialAuthorizationReviewResult.APPROVED,
        governance_review.result is TrialAuthorizationReviewResult.APPROVED,
        execution_approval.result is TrialExecutionApprovalResult.APPROVED,
        approval_request.purpose_digest == purpose.canonical_digest,
        approval_request.root_identity_digest == root_identity.canonical_digest,
        approval_request.root_provisioning_request_digest
        == provisioning_request.canonical_digest,
        approval_request.root_attestation_digest
        == root_attestation.canonical_digest,
        approval_request.target_selection_digest
        == target_selection.canonical_digest,
        approval_request.v0_25_authorization_record_digest
        == authorization.canonical_digest,
        approval_request.access_approval_digest
        == access.access_approval.canonical_digest,
        approval_request.approved_trial_record_digest
        == access.approved_trial.canonical_digest,
        approval_request.root_descriptor_digest
        == source_context.root_descriptor.canonical_digest,
        approval_request.v0_27_reader_policy_digest
        == source_context.resolver_policy.canonical_digest,
        approval_request.controlled_target_reference_digest
        == source_context.controlled_target_reference.canonical_digest,
        approval_request.closure_requirement_digest
        == closure_requirement.canonical_digest,
        approval_request.operator_id == roles.operator_id,
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
        execution_approval.security_review_digest == security_review.canonical_digest,
        execution_approval.governance_review_digest
        == governance_review.canonical_digest,
    )
    if not all(approval_exact):
        return _decision(
            state=ExecutionPreparationState.NEEDS_TRIAL_APPROVAL,
            reasons=(ExecutionPreparationReason.TRIAL_APPROVAL_INVALID,),
            packet=packet,
            request=request,
        )

    policy_flags = (
        packet.raw_retention_allowed,
        packet.raw_logging_allowed,
        packet.raw_cache_allowed,
        packet.persistence_allowed,
        packet.export_allowed,
        packet.network_allowed,
    )
    if any(item is not False for item in policy_flags):
        return _decision(
            state=ExecutionPreparationState.INELIGIBLE,
            reasons=(ExecutionPreparationReason.POLICY_INVALID,),
            packet=packet,
            request=request,
        )

    expiries = (
        packet.expires_at,
        approved_trial.expires_at,
        authorization.expires_at,
        access.operator_assignment.expires_at,
        access.access_approval.expires_at,
        provisioning_request.expires_at,
        root_identity.expires_at,
        root_attestation.expires_at,
        approval_request.expires_at,
        execution_approval.expires_at,
    )
    if (
        not (
            approved_trial.approved_at
            <= packet.issued_at
            <= request.requested_at
            <= request.evaluation_time
        )
        or request.evaluation_time >= min(expiries)
        or packet.expires_at > min(expiries[1:])
    ):
        return _decision(
            state=ExecutionPreparationState.INELIGIBLE,
            reasons=(ExecutionPreparationReason.TEMPORAL_INVALID,),
            packet=packet,
            request=request,
        )

    return _decision(
        state=ExecutionPreparationState.READY_FOR_EXPLICIT_EXECUTION_APPROVAL,
        reasons=(),
        packet=packet,
        request=request,
    )


def prepare_one_shot_trial(
    *,
    registry: TestOnlyExecutionPreparationRegistry,
    packet: OneShotTrialExecutionPacket,
    request: ExecutionPreparationRequest,
    approved_trial: ApprovedOneShotRealDataTrial,
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
    closure_requirement: RealTrialClosureRequirement | None,
    approval_request: RealTrialApprovalRequest,
    security_review: TrialSecurityReview,
    governance_review: TrialDataGovernanceReview,
    execution_approval: TrialExecutionApproval,
    roles: RealTrialApprovalRoleContext,
) -> ExecutionPreparationDecision:
    """Dry-run the metadata chain and stop before human execution approval."""
    if not isinstance(registry, TestOnlyExecutionPreparationRegistry):
        raise OneShotTrialPreparationError("test_only_registry_required")
    return registry.prepare(
        packet=packet,
        request=request,
        approved_trial=approved_trial,
        source_context=source_context,
        purpose=purpose,
        provisioning_request=provisioning_request,
        root_identity=root_identity,
        root_confinement=root_confinement,
        link_reparse=link_reparse,
        permission=permission,
        write_prohibition=write_prohibition,
        network_isolation=network_isolation,
        root_attestation=root_attestation,
        target_selection=target_selection,
        closure_requirement=closure_requirement,
        approval_request=approval_request,
        security_review=security_review,
        governance_review=governance_review,
        execution_approval=execution_approval,
        roles=roles,
    )


__all__ = [
    "ExecutionPreparationDecision",
    "ExecutionPreparationReason",
    "ExecutionPreparationRequest",
    "ExecutionPreparationSafeSummary",
    "ExecutionPreparationSideEffectAccounting",
    "ExecutionPreparationState",
    "OneShotTrialExecutionPacket",
    "OneShotTrialPreparationError",
    "TestOnlyExecutionPreparationRegistry",
    "prepare_one_shot_trial",
]
