from __future__ import annotations

from dataclasses import InitVar, dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum

from ragguard.local_rag_environment import (
    EnvironmentApproval,
    EnvironmentApprovalResult,
    EnvironmentAttestationDecision,
    EnvironmentAttestationState,
    EnvironmentAttestationSuite,
    EnvironmentReview,
    EnvironmentRoleContext,
    LocalRAGEnvironmentManifest,
    validate_environment_approval,
)
from ragguard.local_rag_integration import (
    IntegrationApproval,
    IntegrationResult,
    IntegrationReview,
    IntegrationRoleContext,
    LocalRAGDataFlowPlan,
    LocalRAGIntegrationManifest,
    LocalRAGIntegrationReceipt,
    RAGStage,
    ReviewResult,
    SyntheticConfidentialFixture,
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


_SESSION_MARKER = object()
_EXECUTION_RECEIPT_MARKER = object()


class LocalRAGExecutionError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class SessionAuthorizationState(str, Enum):
    APPROVED_FOR_CONTROLLED_EXECUTION = "approved_for_controlled_execution"


class SessionLifecycle(str, Enum):
    APPROVED = "approved"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class SessionRegistryReason(str, Enum):
    INVALID_CHAIN = "invalid_chain"
    ROLE_CONFLICT = "role_conflict"
    GENERATION_MISMATCH = "generation_mismatch"
    PREDECESSOR_MISMATCH = "predecessor_mismatch"
    REPLAY = "replay"
    TEMPORAL_INVALID = "temporal_invalid"
    COMMIT_FAULT = "commit_fault"
    STATUS_INVALID = "status_invalid"


class SessionRegistryFault(str, Enum):
    NONE = "none"
    CANDIDATE_STATE = "candidate_state"
    BEFORE_SWAP = "before_swap"


class StageExecutionResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class SessionExecutionResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class SessionReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class SessionApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RealDataTrialReadinessState(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_ENVIRONMENT_ATTESTATION = "needs_environment_attestation"
    NEEDS_CONTROLLED_SESSION_EXECUTION = "needs_controlled_session_execution"
    NEEDS_SECURITY_REVIEW = "needs_security_review"
    ELIGIBLE_FOR_EXPLICIT_REAL_DATA_TRIAL_APPROVAL_REVIEW = (
        "eligible_for_explicit_real_data_trial_approval_review"
    )


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


@dataclass(frozen=True, repr=False)
class SessionRoleContext(_Canonical):
    environment_verifier_id: str
    environment_reviewer_id: str
    environment_approver_id: str
    session_requester_id: str
    session_operator_id: str
    session_reviewer_id: str
    session_approver_id: str

    def __post_init__(self) -> None:
        if not all(is_identifier(v) for v in vars(self).values()):
            raise LocalRAGExecutionError("session_role_invalid")
        prohibited_equalities = (
            self.environment_verifier_id == self.environment_reviewer_id,
            self.environment_verifier_id == self.environment_approver_id,
            self.environment_reviewer_id == self.environment_approver_id,
            self.session_requester_id == self.session_operator_id,
            self.session_requester_id == self.session_reviewer_id,
            self.session_requester_id == self.session_approver_id,
            self.session_operator_id == self.session_reviewer_id,
            self.session_operator_id == self.session_approver_id,
            self.session_reviewer_id == self.session_approver_id,
            self.environment_approver_id == self.session_approver_id,
        )
        if any(prohibited_equalities):
            raise LocalRAGExecutionError("session_role_conflict")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {k: v for k, v in vars(self).items() if k != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class LocalRAGExecutionSessionRequest(_Canonical):
    session_request_id: str
    environment_manifest_digest: str
    environment_approval_digest: str
    v0_22_integration_manifest_digest: str
    v0_22_data_flow_plan_digest: str
    fixture_manifest_digest: str
    requester_id: str
    operator_id: str
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (not is_identifier(self.session_request_id) or not is_identifier(self.requester_id)
                or not is_identifier(self.operator_id)
                or not all(is_digest(v) for k, v in vars(self).items() if k.endswith("_digest"))
                or not is_aware(self.requested_at) or not is_aware(self.expires_at)
                or self.expires_at <= self.requested_at):
            raise LocalRAGExecutionError("session_request_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {k: canonical_datetime(v) if isinstance(v, datetime) else v
                for k, v in vars(self).items() if k != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class LocalRAGExecutionSessionReview(_Canonical):
    review_id: str
    session_request_digest: str
    environment_approval_digest: str
    integration_manifest_digest: str
    fixture_manifest_digest: str
    reviewer_id: str
    reviewed_at: datetime
    result: SessionReviewResult
    findings_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.review_id) or not is_identifier(self.reviewer_id)
                or not all(is_digest(value) for value in (
                    self.session_request_digest, self.environment_approval_digest,
                    self.integration_manifest_digest, self.fixture_manifest_digest,
                    self.findings_digest))
                or not is_aware(self.reviewed_at)
                or not isinstance(self.result, SessionReviewResult)):
            raise LocalRAGExecutionError("session_pre_review_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"environment_approval_digest": self.environment_approval_digest,
                "findings_digest": self.findings_digest,
                "fixture_manifest_digest": self.fixture_manifest_digest,
                "integration_manifest_digest": self.integration_manifest_digest,
                "result": self.result.value, "review_id": self.review_id,
                "reviewed_at": canonical_datetime(self.reviewed_at),
                "reviewer_id": self.reviewer_id,
                "session_request_digest": self.session_request_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class LocalRAGExecutionSessionApproval(_Canonical):
    approval_id: str
    session_request_digest: str
    review_digest: str
    approver_id: str
    approved_at: datetime
    result: SessionApprovalResult

    def __post_init__(self) -> None:
        if (not is_identifier(self.approval_id) or not is_identifier(self.approver_id)
                or not is_digest(self.session_request_digest)
                or not is_digest(self.review_digest)
                or not is_aware(self.approved_at)
                or not isinstance(self.result, SessionApprovalResult)):
            raise LocalRAGExecutionError("session_pre_approval_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"approval_id": self.approval_id,
                "approved_at": canonical_datetime(self.approved_at),
                "approver_id": self.approver_id, "result": self.result.value,
                "review_digest": self.review_digest,
                "session_request_digest": self.session_request_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def real_data_approved(self) -> bool:
        return False

    @property
    def real_data_use_authorized(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class ApprovedLocalRAGExecutionSession(_Canonical):
    session_id: str
    session_request_digest: str
    session_review_digest: str
    session_approval_digest: str
    environment_manifest_digest: str
    environment_approval_digest: str
    integration_manifest_digest: str
    fixture_manifest_digest: str
    operator_id: str
    session_generation: int
    predecessor_session_digest: str | None
    approved_at: datetime
    expires_at: datetime
    state: SessionAuthorizationState = SessionAuthorizationState.APPROVED_FOR_CONTROLLED_EXECUTION
    lifecycle: SessionLifecycle = SessionLifecycle.APPROVED
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        if (not is_identifier(self.session_id) or not is_identifier(self.operator_id)
                or not all(is_digest(v) for v in (
                    self.session_request_digest, self.session_review_digest,
                    self.session_approval_digest, self.environment_manifest_digest,
                    self.environment_approval_digest, self.integration_manifest_digest,
                    self.fixture_manifest_digest))
                or (self.predecessor_session_digest is not None
                    and not is_digest(self.predecessor_session_digest))
                or type(self.session_generation) is not int or self.session_generation < 1
                or not is_aware(self.approved_at) or not is_aware(self.expires_at)
                or self.expires_at <= self.approved_at
                or not isinstance(self.state, SessionAuthorizationState)
                or not isinstance(self.lifecycle, SessionLifecycle)
                or _marker is not _SESSION_MARKER):
            raise LocalRAGExecutionError("approved_session_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"approved_at": canonical_datetime(self.approved_at),
                "environment_approval_digest": self.environment_approval_digest,
                "environment_manifest_digest": self.environment_manifest_digest,
                "expires_at": canonical_datetime(self.expires_at),
                "fixture_manifest_digest": self.fixture_manifest_digest,
                "integration_manifest_digest": self.integration_manifest_digest,
                "lifecycle": self.lifecycle.value, "operator_id": self.operator_id,
                "predecessor_session_digest": self.predecessor_session_digest,
                "session_generation": self.session_generation, "session_id": self.session_id,
                "session_approval_digest": self.session_approval_digest,
                "session_request_digest": self.session_request_digest,
                "session_review_digest": self.session_review_digest, "state": self.state.value}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def real_data_approved(self) -> bool:
        return False

    @property
    def production_active(self) -> bool:
        return False

    @property
    def unrestricted_execution(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class StageExecutionEvidence(_Canonical):
    stage: RAGStage
    input_digest: str
    output_digest: str
    transformation_digest: str
    policy_digest: str
    sensitive_class_digest: str
    result: StageExecutionResult

    def __post_init__(self) -> None:
        if (not isinstance(self.stage, RAGStage)
                or not all(is_digest(v) for v in (
                    self.input_digest, self.output_digest, self.transformation_digest,
                    self.policy_digest, self.sensitive_class_digest))
                or not isinstance(self.result, StageExecutionResult)):
            raise LocalRAGExecutionError("stage_execution_evidence_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {"input_digest": self.input_digest, "output_digest": self.output_digest,
                "policy_digest": self.policy_digest, "result": self.result.value,
                "sensitive_class_digest": self.sensitive_class_digest, "stage": self.stage.value,
                "transformation_digest": self.transformation_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class ExecutionSideEffectAccounting(_Canonical):
    external_network_count: int = 0
    http_count: int = 0
    cloud_count: int = 0
    filesystem_real_write_count: int = 0
    database_write_count: int = 0
    persistent_vector_write_count: int = 0
    production_registry_write_count: int = 0
    credential_use_count: int = 0
    token_use_count: int = 0
    runtime_activation_count: int = 0
    runtime_switch_count: int = 0
    real_data_access_count: int = 0

    def __post_init__(self) -> None:
        if not all(type(v) is int and v >= 0 for v in vars(self).values()):
            raise LocalRAGExecutionError("side_effect_accounting_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, int]:
        return {k: v for k, v in vars(self).items() if k != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def all_zero(self) -> bool:
        return all(v == 0 for v in self._payload().values())


@dataclass(frozen=True, repr=False)
class SessionExecutionReceipt(_Canonical):
    execution_receipt_id: str
    session_digest: str
    environment_manifest_digest: str
    environment_approval_digest: str
    integration_manifest_digest: str
    fixture_manifest_digest: str
    operator_id: str
    stage_result_digests: tuple[str, ...]
    started_at: datetime
    finished_at: datetime
    result: SessionExecutionResult
    external_side_effect_digest: str
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        if (not is_identifier(self.execution_receipt_id) or not is_identifier(self.operator_id)
                or not all(is_digest(v) for v in (
                    self.session_digest, self.environment_manifest_digest,
                    self.environment_approval_digest, self.integration_manifest_digest,
                    self.fixture_manifest_digest, *self.stage_result_digests,
                    self.external_side_effect_digest))
                or len(self.stage_result_digests) != len(RAGStage)
                or not is_aware(self.started_at) or not is_aware(self.finished_at)
                or self.finished_at < self.started_at
                or not isinstance(self.result, SessionExecutionResult)
                or self.result is SessionExecutionResult.PASSED
                    and _marker is not _EXECUTION_RECEIPT_MARKER):
            raise LocalRAGExecutionError("execution_receipt_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"environment_approval_digest": self.environment_approval_digest,
                "environment_manifest_digest": self.environment_manifest_digest,
                "execution_receipt_id": self.execution_receipt_id,
                "external_side_effect_digest": self.external_side_effect_digest,
                "finished_at": canonical_datetime(self.finished_at),
                "fixture_manifest_digest": self.fixture_manifest_digest,
                "integration_manifest_digest": self.integration_manifest_digest,
                "operator_id": self.operator_id, "result": self.result.value,
                "session_digest": self.session_digest,
                "stage_result_digests": list(self.stage_result_digests),
                "started_at": canonical_datetime(self.started_at)}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def real_data_approved(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class SessionExecutionReview(_Canonical):
    review_id: str
    session_digest: str
    execution_receipt_digest: str
    reviewer_id: str
    reviewed_at: datetime
    result: SessionReviewResult
    findings_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.review_id) or not is_identifier(self.reviewer_id)
                or not all(is_digest(v) for v in (
                    self.session_digest, self.execution_receipt_digest, self.findings_digest))
                or not is_aware(self.reviewed_at) or not isinstance(self.result, SessionReviewResult)):
            raise LocalRAGExecutionError("session_review_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"execution_receipt_digest": self.execution_receipt_digest,
                "findings_digest": self.findings_digest, "result": self.result.value,
                "review_id": self.review_id, "reviewed_at": canonical_datetime(self.reviewed_at),
                "reviewer_id": self.reviewer_id, "session_digest": self.session_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class SessionExecutionApproval(_Canonical):
    approval_id: str
    session_digest: str
    execution_receipt_digest: str
    review_digest: str
    approver_id: str
    approved_at: datetime
    result: SessionApprovalResult

    def __post_init__(self) -> None:
        if (not is_identifier(self.approval_id) or not is_identifier(self.approver_id)
                or not all(is_digest(v) for v in (
                    self.session_digest, self.execution_receipt_digest, self.review_digest))
                or not is_aware(self.approved_at)
                or not isinstance(self.result, SessionApprovalResult)):
            raise LocalRAGExecutionError("session_approval_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"approval_id": self.approval_id,
                "approved_at": canonical_datetime(self.approved_at),
                "approver_id": self.approver_id,
                "execution_receipt_digest": self.execution_receipt_digest,
                "result": self.result.value, "review_digest": self.review_digest,
                "session_digest": self.session_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def real_data_use_authorized(self) -> bool:
        return False


def validate_v022_integration_chain(
    manifest: LocalRAGIntegrationManifest,
    plan: LocalRAGDataFlowPlan,
    fixture: SyntheticConfidentialFixture,
    receipt: LocalRAGIntegrationReceipt,
    review: IntegrationReview,
    approval: IntegrationApproval,
    roles: IntegrationRoleContext,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not all(canonical_object_valid(v) for v in (
            manifest, plan, fixture, receipt, review, approval, roles)):
        reasons.append("forged_v022_chain")
    if (plan.integration_manifest_digest != manifest.canonical_digest
            or receipt.integration_manifest_digest != manifest.canonical_digest
            or receipt.data_flow_plan_digest != plan.canonical_digest
            or receipt.fixture_manifest_digest != fixture.canonical_digest
            or review.receipt_digest != receipt.canonical_digest
            or approval.receipt_digest != receipt.canonical_digest
            or approval.review_digest != review.canonical_digest):
        reasons.append("v022_digest_binding_mismatch")
    if (receipt.result is not IntegrationResult.PASSED
            or review.result is not ReviewResult.APPROVED
            or approval.result is not ReviewResult.APPROVED):
        reasons.append("v022_not_approved")
    if (receipt.operator_id != roles.operator_id
            or review.reviewer_id != roles.reviewer_id
            or approval.approver_id != roles.approver_id
            or len({receipt.operator_id, review.reviewer_id, approval.approver_id}) != 3):
        reasons.append("v022_role_conflict")
    if not (fixture.created_at <= receipt.executed_at < review.reviewed_at
            < approval.approved_at < fixture.expires_at):
        reasons.append("v022_temporal_invalid")
    return tuple(dict.fromkeys(reasons))


def _validate_session_preapproval(
    request: LocalRAGExecutionSessionRequest,
    review: LocalRAGExecutionSessionReview | None,
    approval: LocalRAGExecutionSessionApproval | None,
    roles: SessionRoleContext,
    environment_approval: EnvironmentApproval,
    integration_manifest: LocalRAGIntegrationManifest,
    fixture: SyntheticConfidentialFixture,
    *,
    registry_approved_at: datetime,
) -> tuple[SessionRegistryReason, ...]:
    reasons: list[SessionRegistryReason] = []
    if (not isinstance(review, LocalRAGExecutionSessionReview)
            or not isinstance(approval, LocalRAGExecutionSessionApproval)):
        return (SessionRegistryReason.INVALID_CHAIN,)
    if not all(canonical_object_valid(value) for value in (request, review, approval, roles)):
        reasons.append(SessionRegistryReason.INVALID_CHAIN)
    if (review.session_request_digest != request.canonical_digest
            or review.environment_approval_digest != environment_approval.canonical_digest
            or review.integration_manifest_digest != integration_manifest.canonical_digest
            or review.fixture_manifest_digest != fixture.canonical_digest
            or approval.session_request_digest != request.canonical_digest
            or approval.review_digest != review.canonical_digest
            or review.result is not SessionReviewResult.APPROVED
            or approval.result is not SessionApprovalResult.APPROVED):
        reasons.append(SessionRegistryReason.INVALID_CHAIN)
    role_ids = (request.requester_id, request.operator_id, review.reviewer_id,
                approval.approver_id)
    if (request.requester_id != roles.session_requester_id
            or request.operator_id != roles.session_operator_id
            or review.reviewer_id != roles.session_reviewer_id
            or approval.approver_id != roles.session_approver_id
            or len(set(role_ids)) != len(role_ids)
            or roles.environment_approver_id == approval.approver_id):
        reasons.append(SessionRegistryReason.ROLE_CONFLICT)
    if (not is_aware(registry_approved_at)
            or not (request.requested_at <= review.reviewed_at
                    < approval.approved_at <= registry_approved_at < request.expires_at)):
        reasons.append(SessionRegistryReason.TEMPORAL_INVALID)
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True)
class SessionRegistryResult:
    applied: bool
    reasons: tuple[SessionRegistryReason, ...]
    session: ApprovedLocalRAGExecutionSession | None
    write_count: int
    mutation_count: int
    event_count: int


@dataclass(frozen=True)
class _SessionRegistryState:
    sessions: tuple[ApprovedLocalRAGExecutionSession, ...] = ()
    used_request_digests: frozenset[str] = frozenset()
    used_review_digests: frozenset[str] = frozenset()
    used_approval_digests: frozenset[str] = frozenset()
    used_session_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class TestOnlySessionRegistry:
    __test__ = False

    def __init__(self) -> None:
        self._state = _SessionRegistryState()

    @property
    def sessions(self) -> tuple[ApprovedLocalRAGExecutionSession, ...]:
        return self._state.sessions

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
    def replay_snapshot(self) -> tuple[
            frozenset[str], frozenset[str], frozenset[str], frozenset[str]]:
        return (self._state.used_request_digests, self._state.used_review_digests,
                self._state.used_approval_digests, self._state.used_session_digests)

    def approve(
        self,
        *,
        session_id: str,
        request: LocalRAGExecutionSessionRequest,
        environment_manifest: LocalRAGEnvironmentManifest,
        environment_suite: EnvironmentAttestationSuite,
        environment_decision: EnvironmentAttestationDecision,
        environment_review: EnvironmentReview,
        environment_approval: EnvironmentApproval,
        environment_roles: EnvironmentRoleContext,
        integration_manifest: LocalRAGIntegrationManifest,
        data_flow_plan: LocalRAGDataFlowPlan,
        fixture: SyntheticConfidentialFixture,
        integration_receipt: LocalRAGIntegrationReceipt,
        integration_review: IntegrationReview,
        integration_approval: IntegrationApproval,
        integration_roles: IntegrationRoleContext,
        session_review: LocalRAGExecutionSessionReview | None,
        session_approval: LocalRAGExecutionSessionApproval | None,
        session_roles: SessionRoleContext,
        session_generation: int,
        predecessor_session_digest: str | None,
        approved_at: datetime,
        fault: SessionRegistryFault = SessionRegistryFault.NONE,
    ) -> SessionRegistryResult:
        reasons: list[SessionRegistryReason] = []
        environment_reasons = validate_environment_approval(
            environment_manifest, environment_suite, environment_decision,
            environment_review, environment_approval, environment_roles,
            evaluation_time=approved_at)
        integration_reasons = validate_v022_integration_chain(
            integration_manifest, data_flow_plan, fixture, integration_receipt,
            integration_review, integration_approval, integration_roles)
        session_preapproval_reasons = _validate_session_preapproval(
            request, session_review, session_approval, session_roles,
            environment_approval, integration_manifest, fixture,
            registry_approved_at=approved_at)
        objects = (request, session_roles, environment_manifest, environment_suite,
            environment_decision, environment_review, environment_approval, environment_roles,
            integration_manifest, data_flow_plan, fixture, integration_receipt,
            integration_review, integration_approval, integration_roles,
            session_review, session_approval)
        exact = (
            all(canonical_object_valid(v) for v in objects),
            not environment_reasons, not integration_reasons, not session_preapproval_reasons,
            request.environment_manifest_digest == environment_manifest.canonical_digest,
            request.environment_approval_digest == environment_approval.canonical_digest,
            request.v0_22_integration_manifest_digest == integration_manifest.canonical_digest,
            request.v0_22_data_flow_plan_digest == data_flow_plan.canonical_digest,
            request.fixture_manifest_digest == fixture.canonical_digest,
            request.requester_id == session_roles.session_requester_id,
            request.operator_id == session_roles.session_operator_id,
            request.operator_id == integration_receipt.operator_id,
            environment_manifest.integration_manifest_digest == integration_manifest.canonical_digest,
            environment_manifest.masking_policy_digest == integration_manifest.masking_policy_digest,
            environment_manifest.chunking_policy_digest == integration_manifest.chunking_policy_digest,
            environment_manifest.embedding_policy_digest == integration_manifest.embedding_policy_digest,
            environment_manifest.retrieval_policy_digest == integration_manifest.retrieval_policy_digest,
            environment_manifest.prompt_policy_digest == integration_manifest.prompt_policy_digest,
            environment_manifest.logging_policy_digest == integration_manifest.logging_policy_digest,
            environment_manifest.cache_policy_digest == integration_manifest.cache_policy_digest,
            session_roles.environment_verifier_id == environment_roles.verifier_id,
            session_roles.environment_reviewer_id == environment_roles.reviewer_id,
            session_roles.environment_approver_id == environment_roles.approver_id,
            session_roles.session_operator_id == integration_roles.operator_id,
        )
        if not all(exact):
            reasons.append(SessionRegistryReason.INVALID_CHAIN)
        reasons.extend(session_preapproval_reasons)
        expected_generation = len(self.sessions) + 1
        expected_predecessor = self.sessions[-1].canonical_digest if self.sessions else None
        if session_generation != expected_generation:
            reasons.append(SessionRegistryReason.GENERATION_MISMATCH)
        if predecessor_session_digest != expected_predecessor:
            reasons.append(SessionRegistryReason.PREDECESSOR_MISMATCH)
        if request.canonical_digest in self._state.used_request_digests:
            reasons.append(SessionRegistryReason.REPLAY)
        review_digest = getattr(session_review, "canonical_digest", None)
        approval_digest = getattr(session_approval, "canonical_digest", None)
        if (review_digest in self._state.used_review_digests
                or approval_digest in self._state.used_approval_digests):
            reasons.append(SessionRegistryReason.REPLAY)
        if (not is_aware(approved_at)
                or not (environment_approval.approved_at < request.requested_at
                        and integration_approval.approved_at < request.requested_at
                        <= approved_at < request.expires_at)
                or fixture.expires_at <= approved_at):
            reasons.append(SessionRegistryReason.TEMPORAL_INVALID)
        if reasons:
            return self._result(False, tuple(dict.fromkeys(reasons)), None)
        try:
            if fault is SessionRegistryFault.CANDIDATE_STATE:
                raise RuntimeError
            session = ApprovedLocalRAGExecutionSession(
                session_id, request.canonical_digest, session_review.canonical_digest,
                session_approval.canonical_digest, environment_manifest.canonical_digest,
                environment_approval.canonical_digest, integration_manifest.canonical_digest,
                fixture.canonical_digest, request.operator_id, session_generation,
                predecessor_session_digest, approved_at, request.expires_at,
                _marker=_SESSION_MARKER)
            candidate = replace(self._state,
                sessions=self.sessions + (session,),
                used_request_digests=self._state.used_request_digests | {request.canonical_digest},
                used_review_digests=self._state.used_review_digests | {
                    session_review.canonical_digest},
                used_approval_digests=self._state.used_approval_digests | {
                    session_approval.canonical_digest},
                used_session_digests=self._state.used_session_digests | {session.canonical_digest},
                write_count=self.write_count + 1,
                mutation_count=self.mutation_count + 1,
                event_count=self.event_count + 1)
            if fault is SessionRegistryFault.BEFORE_SWAP:
                raise RuntimeError
            self._state = candidate
            return self._result(True, (), session)
        except RuntimeError:
            return self._result(False, (SessionRegistryReason.COMMIT_FAULT,), None)

    def transition(
        self,
        *,
        source_session: ApprovedLocalRAGExecutionSession,
        new_session_id: str,
        lifecycle: SessionLifecycle,
        transitioned_at: datetime,
        fault: SessionRegistryFault = SessionRegistryFault.NONE,
    ) -> SessionRegistryResult:
        if (not self.sessions or not canonical_object_valid(source_session)
                or source_session.canonical_digest != self.sessions[-1].canonical_digest
                or source_session.lifecycle is not SessionLifecycle.APPROVED
                or lifecycle not in {
                    SessionLifecycle.EXPIRED, SessionLifecycle.REVOKED, SessionLifecycle.SUPERSEDED}
                or not is_aware(transitioned_at) or transitioned_at <= source_session.approved_at):
            return self._result(False, (SessionRegistryReason.STATUS_INVALID,), None)
        if fault is not SessionRegistryFault.NONE:
            return self._result(False, (SessionRegistryReason.COMMIT_FAULT,), None)
        session = ApprovedLocalRAGExecutionSession(
            new_session_id, source_session.session_request_digest,
            source_session.session_review_digest, source_session.session_approval_digest,
            source_session.environment_manifest_digest, source_session.environment_approval_digest,
            source_session.integration_manifest_digest, source_session.fixture_manifest_digest,
            source_session.operator_id, source_session.session_generation + 1,
            source_session.canonical_digest, transitioned_at,
            max(source_session.expires_at, transitioned_at + timedelta(microseconds=1)),
            source_session.state, lifecycle, _marker=_SESSION_MARKER)
        candidate = replace(self._state, sessions=self.sessions + (session,),
            used_session_digests=self._state.used_session_digests | {session.canonical_digest},
            write_count=self.write_count + 1, mutation_count=self.mutation_count + 1,
            event_count=self.event_count + 1)
        self._state = candidate
        return self._result(True, (), session)

    def _result(self, applied, reasons, session):
        return SessionRegistryResult(applied, reasons, session,
            self.write_count, self.mutation_count, self.event_count)


def _stage_policy_digest(manifest: LocalRAGIntegrationManifest, stage: RAGStage) -> str:
    mapping = {
        RAGStage.INPUT_CANDIDATE: manifest.ragguard_policy_digest,
        RAGStage.POLICY_DECISION: manifest.ragguard_policy_digest,
        RAGStage.MASKING: manifest.masking_policy_digest,
        RAGStage.CHUNKING: manifest.chunking_policy_digest,
        RAGStage.EMBEDDING: manifest.embedding_policy_digest,
        RAGStage.VECTOR_WRITE: manifest.embedding_policy_digest,
        RAGStage.RETRIEVAL: manifest.retrieval_policy_digest,
        RAGStage.PROMPT: manifest.prompt_policy_digest,
        RAGStage.LLM_INPUT: manifest.prompt_policy_digest,
        RAGStage.RESPONSE: manifest.prompt_policy_digest,
        RAGStage.LOGGING_CACHE: manifest.logging_policy_digest,
    }
    return mapping[stage]


class ControlledLocalRAGExecutionAdapter:
    def execute(
        self,
        *,
        execution_receipt_id: str,
        session: ApprovedLocalRAGExecutionSession,
        request: LocalRAGExecutionSessionRequest,
        environment_manifest: LocalRAGEnvironmentManifest,
        environment_approval: EnvironmentApproval,
        integration_manifest: LocalRAGIntegrationManifest,
        data_flow_plan: LocalRAGDataFlowPlan,
        fixture: SyntheticConfidentialFixture,
        operator_id: str,
        started_at: datetime,
        finished_at: datetime,
        injected_failure_stage: RAGStage | None = None,
    ) -> tuple[tuple[StageExecutionEvidence, ...], ExecutionSideEffectAccounting,
               SessionExecutionReceipt]:
        objects = (session, request, environment_manifest, environment_approval,
                   integration_manifest, data_flow_plan, fixture)
        bindings = (
            all(canonical_object_valid(v) for v in objects),
            session.session_request_digest == request.canonical_digest,
            session.environment_manifest_digest == environment_manifest.canonical_digest,
            session.environment_approval_digest == environment_approval.canonical_digest,
            session.integration_manifest_digest == integration_manifest.canonical_digest,
            session.fixture_manifest_digest == fixture.canonical_digest,
            request.v0_22_data_flow_plan_digest == data_flow_plan.canonical_digest,
            data_flow_plan.integration_manifest_digest == integration_manifest.canonical_digest,
            session.operator_id == request.operator_id == operator_id,
            session.lifecycle is SessionLifecycle.APPROVED,
            session.state is SessionAuthorizationState.APPROVED_FOR_CONTROLLED_EXECUTION,
            is_aware(started_at), is_aware(finished_at),
            session.approved_at <= started_at <= finished_at < session.expires_at,
            finished_at < fixture.expires_at,
        )
        accounting = ExecutionSideEffectAccounting()
        if not all(bindings):
            raise LocalRAGExecutionError("execution_binding_invalid")
        evidence: list[StageExecutionEvidence] = []
        previous = session.canonical_digest
        failure_seen = False
        for stage in RAGStage:
            if failure_seen:
                result = StageExecutionResult.INCOMPLETE
            elif stage is injected_failure_stage:
                result = StageExecutionResult.FAILED
                failure_seen = True
            else:
                result = StageExecutionResult.PASSED
            output = digest(canonical_json({"fixture_manifest_digest": fixture.canonical_digest,
                "input_digest": previous, "session_digest": session.canonical_digest,
                "stage": stage.value, "result": result.value}))
            item = StageExecutionEvidence(stage, previous, output,
                digest(canonical_json({"stage": stage.value, "mode": "masked_metadata_only"})),
                _stage_policy_digest(integration_manifest, stage),
                digest(canonical_json(sorted(kind.value for kind, _ in fixture.fields))), result)
            evidence.append(item)
            previous = output
        receipt_result = (SessionExecutionResult.FAILED if failure_seen
                          else SessionExecutionResult.PASSED)
        receipt = SessionExecutionReceipt(execution_receipt_id, session.canonical_digest,
            environment_manifest.canonical_digest, environment_approval.canonical_digest,
            integration_manifest.canonical_digest, fixture.canonical_digest, operator_id,
            tuple(v.canonical_digest for v in evidence), started_at, finished_at,
            receipt_result, accounting.canonical_digest,
            _marker=_EXECUTION_RECEIPT_MARKER
                if receipt_result is SessionExecutionResult.PASSED else None)
        return tuple(evidence), accounting, receipt


@dataclass(frozen=True, repr=False)
class RealDataTrialReadinessDecision(_Canonical):
    state: RealDataTrialReadinessState
    environment_decision_digest: str
    session_digest: str
    execution_receipt_digest: str
    review_digest: str
    approval_digest: str
    reason_codes: tuple[str, ...]
    evaluated_at: datetime
    real_data_approved: bool = field(init=False, default=False)
    real_data_use_authorized: bool = field(init=False, default=False)
    production_active: bool = field(init=False, default=False)
    external_network_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    cloud_count: int = field(init=False, default=0)
    filesystem_real_write_count: int = field(init=False, default=0)
    database_write_count: int = field(init=False, default=0)
    persistent_vector_write_count: int = field(init=False, default=0)
    production_registry_write_count: int = field(init=False, default=0)
    credential_use_count: int = field(init=False, default=0)
    token_use_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    runtime_switch_count: int = field(init=False, default=0)
    real_data_access_count: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if (not isinstance(self.state, RealDataTrialReadinessState)
                or not all(is_digest(v) for v in (
                    self.environment_decision_digest, self.session_digest,
                    self.execution_receipt_digest, self.review_digest, self.approval_digest))
                or not self.reason_codes or not all(is_identifier(v) for v in self.reason_codes)
                or not is_aware(self.evaluated_at)):
            raise LocalRAGExecutionError("readiness_decision_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        counts = {k: v for k, v in vars(self).items() if k.endswith("_count")}
        return {"approval_digest": self.approval_digest,
                "environment_decision_digest": self.environment_decision_digest,
                "evaluated_at": canonical_datetime(self.evaluated_at),
                "execution_receipt_digest": self.execution_receipt_digest,
                "external_side_effect_counts": counts, "reason_codes": list(self.reason_codes),
                "review_digest": self.review_digest, "session_digest": self.session_digest,
                "state": self.state.value}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


def evaluate_real_data_trial_readiness(
    environment_decision: EnvironmentAttestationDecision,
    session: ApprovedLocalRAGExecutionSession | None,
    stage_evidence: tuple[StageExecutionEvidence, ...] | None,
    receipt: SessionExecutionReceipt | None,
    side_effects: ExecutionSideEffectAccounting | None,
    review: SessionExecutionReview | None,
    approval: SessionExecutionApproval | None,
    roles: SessionRoleContext,
    *,
    evaluation_time: datetime,
) -> RealDataTrialReadinessDecision:
    if not is_aware(evaluation_time):
        raise LocalRAGExecutionError("readiness_time_invalid")
    empty = digest("missing")
    if (not canonical_object_valid(environment_decision)
            or environment_decision.state is not EnvironmentAttestationState.ELIGIBLE_FOR_ENVIRONMENT_REVIEW):
        return RealDataTrialReadinessDecision(
            RealDataTrialReadinessState.NEEDS_ENVIRONMENT_ATTESTATION,
            environment_decision.canonical_digest, empty, empty, empty, empty,
            ("environment_attestation_required",), evaluation_time)
    if session is None or not canonical_object_valid(session):
        return RealDataTrialReadinessDecision(
            RealDataTrialReadinessState.NEEDS_CONTROLLED_SESSION_EXECUTION,
            environment_decision.canonical_digest, empty, empty, empty, empty,
            ("approved_session_required",), evaluation_time)
    if receipt is None or stage_evidence is None or side_effects is None:
        return RealDataTrialReadinessDecision(
            RealDataTrialReadinessState.NEEDS_CONTROLLED_SESSION_EXECUTION,
            environment_decision.canonical_digest, session.canonical_digest,
            empty, empty, empty, ("controlled_execution_required",), evaluation_time)
    reasons: list[str] = []
    if not all(canonical_object_valid(v) for v in (
            session, *stage_evidence, receipt, side_effects, roles)):
        reasons.append("forged_execution_chain")
    if (tuple(v.stage for v in stage_evidence) != tuple(RAGStage)
            or tuple(v.canonical_digest for v in stage_evidence) != receipt.stage_result_digests
            or any(v.result is not StageExecutionResult.PASSED for v in stage_evidence)
            or receipt.result is not SessionExecutionResult.PASSED
            or receipt.session_digest != session.canonical_digest
            or receipt.environment_manifest_digest != session.environment_manifest_digest
            or receipt.environment_approval_digest != session.environment_approval_digest
            or receipt.integration_manifest_digest != session.integration_manifest_digest
            or receipt.fixture_manifest_digest != session.fixture_manifest_digest
            or receipt.operator_id != session.operator_id
            or receipt.external_side_effect_digest != side_effects.canonical_digest
            or not side_effects.all_zero):
        reasons.append("execution_chain_invalid")
    if (session.lifecycle is not SessionLifecycle.APPROVED
            or evaluation_time >= session.expires_at
            or not (session.approved_at <= receipt.started_at <= receipt.finished_at
                    < session.expires_at)
            or receipt.finished_at > evaluation_time):
        reasons.append("session_temporal_or_lifecycle_invalid")
    if (receipt.operator_id != roles.session_operator_id
            or len({roles.session_operator_id, roles.session_reviewer_id,
                    roles.session_approver_id}) != 3):
        reasons.append("session_role_conflict")
    if review is not None and (not canonical_object_valid(review)
            or review.session_digest != session.canonical_digest
            or review.execution_receipt_digest != receipt.canonical_digest
            or review.reviewer_id != roles.session_reviewer_id):
        reasons.append("review_approval_invalid")
    if approval is not None and (review is None or not canonical_object_valid(approval)
            or approval.session_digest != session.canonical_digest
            or approval.execution_receipt_digest != receipt.canonical_digest
            or approval.review_digest != review.canonical_digest
            or approval.approver_id != roles.session_approver_id):
        reasons.append("review_approval_invalid")
    if reasons:
        state = RealDataTrialReadinessState.INELIGIBLE
        review_digest = review.canonical_digest if review else empty
        approval_digest = approval.canonical_digest if approval else empty
    elif review is None or approval is None:
        state = RealDataTrialReadinessState.NEEDS_SECURITY_REVIEW
        reasons.append("independent_security_review_required")
        review_digest = review.canonical_digest if review else empty
        approval_digest = approval.canonical_digest if approval else empty
    else:
        review_digest, approval_digest = review.canonical_digest, approval.canonical_digest
        if not all(canonical_object_valid(v) for v in (review, approval)):
            reasons.append("forged_review_chain")
        if (review.session_digest != session.canonical_digest
                or review.execution_receipt_digest != receipt.canonical_digest
                or approval.session_digest != session.canonical_digest
                or approval.execution_receipt_digest != receipt.canonical_digest
                or approval.review_digest != review.canonical_digest
                or review.reviewer_id != roles.session_reviewer_id
                or approval.approver_id != roles.session_approver_id
                or review.result is not SessionReviewResult.APPROVED
                or approval.result is not SessionApprovalResult.APPROVED):
            reasons.append("review_approval_invalid")
        if not (receipt.finished_at < review.reviewed_at < approval.approved_at <= evaluation_time):
            reasons.append("readiness_temporal_invalid")
        state = (RealDataTrialReadinessState.INELIGIBLE if reasons
                 else RealDataTrialReadinessState.ELIGIBLE_FOR_EXPLICIT_REAL_DATA_TRIAL_APPROVAL_REVIEW)
    return RealDataTrialReadinessDecision(state, environment_decision.canonical_digest,
        session.canonical_digest, receipt.canonical_digest, review_digest, approval_digest,
        tuple(dict.fromkeys(reasons or ["controlled_session_evidence_approved"])), evaluation_time)


__all__ = [
    "ApprovedLocalRAGExecutionSession", "ControlledLocalRAGExecutionAdapter",
    "ExecutionSideEffectAccounting", "LocalRAGExecutionError",
    "LocalRAGExecutionSessionApproval", "LocalRAGExecutionSessionRequest",
    "LocalRAGExecutionSessionReview", "RealDataTrialReadinessDecision",
    "RealDataTrialReadinessState", "SessionApprovalResult", "SessionAuthorizationState",
    "SessionExecutionApproval", "SessionExecutionReceipt", "SessionExecutionResult",
    "SessionExecutionReview", "SessionLifecycle", "SessionRegistryFault",
    "SessionRegistryReason", "SessionRegistryResult", "SessionReviewResult",
    "SessionRoleContext", "StageExecutionEvidence", "StageExecutionResult",
    "TestOnlySessionRegistry", "evaluate_real_data_trial_readiness",
    "validate_v022_integration_chain",
]
