from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from ragguard.activation_commit import RuntimeAuthorizationCommitRecord
from ragguard.real_persistence import PersistenceCommitReceiptV2


CANONICAL_REAL_WORLD_VALIDATION_DIGEST_ALGORITHM = "sha256"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RECEIPT_MARKER = object()


class RealWorldValidationError(ValueError):
    pass


class EnvironmentClass(str, Enum):
    ISOLATED_LOCAL = "isolated_local"
    CONTROLLED_STAGING = "controlled_staging"
    SYNTHETIC_PRODUCTION_EQUIVALENT = "synthetic_production_equivalent"


class DataClass(str, Enum):
    SYNTHETIC_ONLY = "synthetic_only"
    CONTROLLED_FIXTURE_ONLY = "controlled_fixture_only"


class CredentialClass(str, Enum):
    NONE = "none"
    SYNTHETIC_NONSECRET = "synthetic_nonsecret"


class StorageMode(str, Enum):
    IN_MEMORY_ONLY = "in_memory_only"
    EPHEMERAL_CONTROLLED = "ephemeral_controlled"


class AuthorizationReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ValidationDecisionState(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_ENVIRONMENT_VERIFICATION = "needs_environment_verification"
    NEEDS_EXECUTION_AUTHORIZATION = "needs_execution_authorization"
    READY_FOR_CONTROLLED_EXECUTION = "ready_for_controlled_execution"


class ValidationReason(str, Enum):
    DIGEST_MISMATCH = "digest_mismatch"
    SOURCE_INELIGIBLE = "source_ineligible"
    ENVIRONMENT_UNVERIFIED = "environment_unverified"
    AUTHORIZATION_MISSING = "authorization_missing"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    STALE_REQUEST = "stale_request"
    REPLAY_DETECTED = "replay_detected"


class ExecutionResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class ControlledExecutionOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCOMPLETE = "incomplete"
    COMMIT_FAULT = "commit_fault"


@dataclass(frozen=True, repr=False)
class RealWorldValidationAuthorizationRequest:
    authorization_request_id: str
    manual_validation_approval_digest: str
    equivalence_approval_digest: str
    runtime_authorization_record_digest: str
    persistence_receipt_digest: str
    validation_plan_digest: str
    environment_manifest_digest: str
    product_manifest_digest: str
    protocol_version: str
    profile_id: str
    profile_version: str
    product_id: str
    product_version: str
    requested_at: datetime
    requested_by: str
    reviewer_id: str
    approver_id: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        ids = (self.authorization_request_id, self.profile_id, self.product_id,
               self.requested_by, self.reviewer_id, self.approver_id)
        versions = (self.protocol_version, self.profile_version, self.product_version)
        digests = (self.manual_validation_approval_digest,
                   self.equivalence_approval_digest,
                   self.runtime_authorization_record_digest,
                   self.persistence_receipt_digest, self.validation_plan_digest,
                   self.environment_manifest_digest, self.product_manifest_digest)
        if (not all(_is_identifier(v) for v in ids)
                or not all(_is_version(v) for v in versions)
                or any(v.lower() in {"current", "latest"} for v in versions)
                or not all(_is_digest(v) for v in digests)
                or not _is_aware(self.requested_at)):
            raise RealWorldValidationError("authorization_request_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({
            "approver_id": self.approver_id,
            "authorization_request_id": self.authorization_request_id,
            "environment_manifest_digest": self.environment_manifest_digest,
            "equivalence_approval_digest": self.equivalence_approval_digest,
            "manual_validation_approval_digest": self.manual_validation_approval_digest,
            "persistence_receipt_digest": self.persistence_receipt_digest,
            "product_id": self.product_id, "product_manifest_digest": self.product_manifest_digest,
            "product_version": self.product_version, "profile_id": self.profile_id,
            "profile_version": self.profile_version, "protocol_version": self.protocol_version,
            "requested_at": _canonical_datetime(self.requested_at),
            "requested_by": self.requested_by, "reviewer_id": self.reviewer_id,
            "runtime_authorization_record_digest": self.runtime_authorization_record_digest,
            "validation_plan_digest": self.validation_plan_digest,
        })

    def __repr__(self) -> str:
        return "RealWorldValidationAuthorizationRequest(<safe>)"


@dataclass(frozen=True, repr=False)
class ControlledEnvironmentManifest:
    environment_id: str
    environment_class: EnvironmentClass
    network_mode: str
    data_class: DataClass
    credential_class: CredentialClass
    storage_mode: StorageMode
    transport_mode: str
    product_build_digest: str
    configuration_digest: str
    dependency_digest: str
    protocol_digest: str
    generated_at: datetime
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not _is_identifier(self.environment_id)
                or self.network_mode != "disabled"
                or self.transport_mode != "in_process"
                or not isinstance(self.environment_class, EnvironmentClass)
                or not isinstance(self.data_class, DataClass)
                or not isinstance(self.credential_class, CredentialClass)
                or not isinstance(self.storage_mode, StorageMode)
                or not all(_is_digest(v) for v in (self.product_build_digest,
                    self.configuration_digest, self.dependency_digest, self.protocol_digest))
                or not _is_aware(self.generated_at)):
            raise RealWorldValidationError("environment_manifest_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"configuration_digest": self.configuration_digest,
            "credential_class": self.credential_class.value, "data_class": self.data_class.value,
            "dependency_digest": self.dependency_digest, "environment_class": self.environment_class.value,
            "environment_id": self.environment_id, "generated_at": _canonical_datetime(self.generated_at),
            "network_mode": self.network_mode, "product_build_digest": self.product_build_digest,
            "protocol_digest": self.protocol_digest, "storage_mode": self.storage_mode.value,
            "transport_mode": self.transport_mode})

    def __repr__(self) -> str:
        return "ControlledEnvironmentManifest(<safe>)"


@dataclass(frozen=True, repr=False)
class SafeScenarioManifest:
    scenario_set_id: str
    scenario_count: int
    scenario_class: str
    fixture_digest: str
    expected_behavior_digest: str
    failure_policy_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not _is_identifier(self.scenario_set_id) or self.scenario_class not in
                {"synthetic_contract", "controlled_fixture"}
                or type(self.scenario_count) is not int or self.scenario_count < 1
                or not all(_is_digest(v) for v in (self.fixture_digest,
                    self.expected_behavior_digest, self.failure_policy_digest))):
            raise RealWorldValidationError("scenario_manifest_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"expected_behavior_digest": self.expected_behavior_digest,
            "failure_policy_digest": self.failure_policy_digest, "fixture_digest": self.fixture_digest,
            "scenario_class": self.scenario_class, "scenario_count": self.scenario_count,
            "scenario_set_id": self.scenario_set_id})

    def __repr__(self) -> str:
        return "SafeScenarioManifest(<safe>)"


@dataclass(frozen=True, repr=False)
class RealWorldValidationPlan:
    plan_id: str
    authorization_request_digest: str
    environment_manifest_digest: str
    manual_validation_plan_digest: str
    equivalence_criteria_digest: str
    expected_product_digest: str
    expected_configuration_digest: str
    expected_protocol_digest: str
    scenario_set_digest: str
    pass_criteria_digest: str
    timeout_policy_digest: str
    created_at: datetime
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        values = tuple(v for k, v in vars(self).items() if k.endswith("_digest"))
        if not _is_identifier(self.plan_id) or not all(_is_digest(v) for v in values) or not _is_aware(self.created_at):
            raise RealWorldValidationError("validation_plan_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({k: _canonical_datetime(v) if isinstance(v, datetime) else v
            for k, v in vars(self).items() if k != "canonical_digest"})

    def __repr__(self) -> str:
        return "RealWorldValidationPlan(<safe>)"


@dataclass(frozen=True, repr=False)
class RealWorldValidationAuthorizationReview:
    review_id: str
    authorization_request_digest: str
    reviewed_at: datetime
    reviewer_id: str
    result: AuthorizationReviewResult
    findings_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not all(_is_identifier(v) for v in (self.review_id, self.reviewer_id))
                or not all(_is_digest(v) for v in (self.authorization_request_digest, self.findings_digest))
                or not _is_aware(self.reviewed_at) or not isinstance(self.result, AuthorizationReviewResult)):
            raise RealWorldValidationError("authorization_review_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"authorization_request_digest": self.authorization_request_digest,
            "findings_digest": self.findings_digest, "result": self.result.value,
            "review_id": self.review_id, "reviewed_at": _canonical_datetime(self.reviewed_at),
            "reviewer_id": self.reviewer_id})


@dataclass(frozen=True, repr=False)
class RealWorldValidationAuthorizationApproval:
    approval_id: str
    authorization_request_digest: str
    review_digest: str
    approved_at: datetime
    approver_id: str
    approved: bool
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not all(_is_identifier(v) for v in (self.approval_id, self.approver_id))
                or not all(_is_digest(v) for v in (self.authorization_request_digest, self.review_digest))
                or not _is_aware(self.approved_at) or type(self.approved) is not bool):
            raise RealWorldValidationError("authorization_approval_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({"approval_id": self.approval_id, "approved": self.approved,
            "approved_at": _canonical_datetime(self.approved_at), "approver_id": self.approver_id,
            "authorization_request_digest": self.authorization_request_digest,
            "review_digest": self.review_digest})


@dataclass(frozen=True)
class RealWorldValidationDecision:
    state: ValidationDecisionState
    reasons: tuple[ValidationReason, ...]
    authorization_request_digest: str
    plan_digest: str
    environment_manifest_digest: str
    evaluated_at: datetime
    filesystem_count: int = field(init=False, default=0)
    database_count: int = field(init=False, default=0)
    external_storage_count: int = field(init=False, default=0)
    registry_write_count: int = field(init=False, default=0)
    network_count: int = field(init=False, default=0)
    transport_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    runtime_activation_count: int = field(init=False, default=0)
    credential_count: int = field(init=False, default=0)
    token_count: int = field(init=False, default=0)
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_digest", _digest(_canonical_json({
            "authorization_request_digest": self.authorization_request_digest,
            "environment_manifest_digest": self.environment_manifest_digest,
            "evaluated_at": _canonical_datetime(self.evaluated_at), "plan_digest": self.plan_digest,
            "reasons": [v.value for v in self.reasons], "state": self.state.value})))


def evaluate_real_world_validation(
    request: RealWorldValidationAuthorizationRequest,
    environment: ControlledEnvironmentManifest,
    plan: RealWorldValidationPlan,
    scenario: SafeScenarioManifest,
    runtime_record: RuntimeAuthorizationCommitRecord,
    persistence_receipt: PersistenceCommitReceiptV2,
    review: RealWorldValidationAuthorizationReview | None,
    approval: RealWorldValidationAuthorizationApproval | None,
    *,
    manual_validation_approval_digest: str,
    equivalence_approval_digest: str,
    product_manifest_digest: str,
    lifecycle_active: bool,
    pending_revalidation: bool,
    pending_transition: bool,
    revoked_source: bool,
    replaced_predecessor: bool,
    evaluation_time: datetime,
    valid_until: datetime,
    used_request_digests: frozenset[str] = frozenset(),
) -> RealWorldValidationDecision:
    if not _is_aware(evaluation_time) or not _is_aware(valid_until):
        raise RealWorldValidationError("evaluation_time_invalid")
    reasons: list[ValidationReason] = []
    exact = (
        request.manual_validation_approval_digest == manual_validation_approval_digest,
        request.equivalence_approval_digest == equivalence_approval_digest == runtime_record.equivalence_approval_digest,
        request.runtime_authorization_record_digest == runtime_record.canonical_digest,
        request.persistence_receipt_digest == persistence_receipt.canonical_digest,
        persistence_receipt.authorization_record_digest == runtime_record.canonical_digest,
        request.environment_manifest_digest == environment.canonical_digest == plan.environment_manifest_digest,
        request.product_manifest_digest == product_manifest_digest == plan.expected_product_digest,
        plan.authorization_request_digest == request.canonical_digest,
        plan.scenario_set_digest == scenario.canonical_digest,
        plan.expected_configuration_digest == environment.configuration_digest,
        plan.expected_protocol_digest == environment.protocol_digest,
    )
    if not all(exact): reasons.append(ValidationReason.DIGEST_MISMATCH)
    if not lifecycle_active or pending_revalidation or pending_transition or revoked_source or replaced_predecessor:
        reasons.append(ValidationReason.SOURCE_INELIGIBLE)
    if request.canonical_digest in used_request_digests: reasons.append(ValidationReason.REPLAY_DETECTED)
    if not (environment.generated_at <= plan.created_at <= request.requested_at <= evaluation_time < valid_until):
        reasons.append(ValidationReason.TEMPORAL_INVALID)
    if evaluation_time - request.requested_at > timedelta(days=90): reasons.append(ValidationReason.STALE_REQUEST)
    upstream_actors = {runtime_record.runtime_authorization_approver_id, runtime_record.committed_by,
                       persistence_receipt.committed_by}
    if len({request.requested_by, request.reviewer_id, request.approver_id, *upstream_actors}) != 3 + len(upstream_actors):
        reasons.append(ValidationReason.ROLE_CONFLICT)
    if reasons:
        state = ValidationDecisionState.INELIGIBLE
    elif environment.network_mode != "disabled" or environment.transport_mode != "in_process":
        state = ValidationDecisionState.NEEDS_ENVIRONMENT_VERIFICATION
        reasons.append(ValidationReason.ENVIRONMENT_UNVERIFIED)
    elif review is None or approval is None:
        state = ValidationDecisionState.NEEDS_EXECUTION_AUTHORIZATION
        reasons.append(ValidationReason.AUTHORIZATION_MISSING)
    elif (review.authorization_request_digest != request.canonical_digest
          or approval.authorization_request_digest != request.canonical_digest
          or approval.review_digest != review.canonical_digest
          or review.reviewer_id != request.reviewer_id or approval.approver_id != request.approver_id
          or review.result is not AuthorizationReviewResult.APPROVED or not approval.approved
          or not (request.requested_at <= review.reviewed_at < approval.approved_at <= evaluation_time)):
        state = ValidationDecisionState.INELIGIBLE
        reasons.append(ValidationReason.DIGEST_MISMATCH)
    else:
        state = ValidationDecisionState.READY_FOR_CONTROLLED_EXECUTION
    return RealWorldValidationDecision(state, tuple(dict.fromkeys(reasons)), request.canonical_digest,
                                       plan.canonical_digest, environment.canonical_digest, evaluation_time)


@dataclass(frozen=True, repr=False)
class RealWorldExecutionRequest:
    execution_request_id: str
    authorization_request_digest: str
    authorization_approval_digest: str
    plan_digest: str
    environment_manifest_digest: str
    scenario_digest: str
    requested_at: datetime
    operator_id: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (not all(_is_identifier(v) for v in (self.execution_request_id, self.operator_id))
                or not all(_is_digest(v) for v in (self.authorization_request_digest,
                    self.authorization_approval_digest, self.plan_digest,
                    self.environment_manifest_digest, self.scenario_digest))
                or not _is_aware(self.requested_at)):
            raise RealWorldValidationError("execution_request_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({k: _canonical_datetime(v) if isinstance(v, datetime) else v
            for k, v in vars(self).items() if k != "canonical_digest"})

    def __repr__(self) -> str:
        return "RealWorldExecutionRequest(<safe>)"


@dataclass(frozen=True, repr=False)
class RealWorldExecutionReceipt:
    receipt_id: str
    execution_request_digest: str
    authorization_request_digest: str
    authorization_approval_digest: str
    plan_digest: str
    environment_manifest_digest: str
    scenario_digest: str
    behavior_digest: str
    coverage_digest: str
    failure_digest: str
    started_at: datetime
    completed_at: datetime
    operator_id: str
    result: ExecutionResult
    _marker: object = field(default=None, repr=False, compare=False)
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        digests = tuple(v for k, v in vars(self).items() if k.endswith("_digest"))
        if (self._marker is not _RECEIPT_MARKER
                or not all(_is_identifier(v) for v in (self.receipt_id, self.operator_id))
                or not all(_is_digest(v) for v in digests)
                or not _is_aware(self.started_at) or not _is_aware(self.completed_at)
                or self.completed_at < self.started_at or not isinstance(self.result, ExecutionResult)):
            raise RealWorldValidationError("execution_receipt_invalid")
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json({k: (_canonical_datetime(v) if isinstance(v, datetime)
            else v.value if isinstance(v, Enum) else v) for k, v in vars(self).items()
            if k not in {"canonical_digest", "_marker"}})

    def __repr__(self) -> str:
        return "RealWorldExecutionReceipt(<safe>)"


@dataclass(frozen=True)
class ControlledExecutionResult:
    applied: bool
    receipt: RealWorldExecutionReceipt | None
    filesystem_count: int = 0
    database_count: int = 0
    external_storage_count: int = 0
    registry_write_count: int = 0
    network_count: int = 0
    transport_count: int = 0
    http_count: int = 0
    runtime_activation_count: int = 0
    credential_count: int = 0
    token_count: int = 0


class TestControlledRealWorldExecutionAdapter:
    """Deterministic test-only adapter. It accepts no commands, paths, or endpoints."""

    __test__ = False

    def execute(self, *, decision: RealWorldValidationDecision,
                request: RealWorldExecutionRequest,
                authorization_request: RealWorldValidationAuthorizationRequest,
                authorization_approval: RealWorldValidationAuthorizationApproval,
                plan: RealWorldValidationPlan, environment: ControlledEnvironmentManifest,
                scenario: SafeScenarioManifest, started_at: datetime, completed_at: datetime,
                outcome: ControlledExecutionOutcome) -> ControlledExecutionResult:
        if not _is_aware(started_at) or not _is_aware(completed_at):
            raise RealWorldValidationError("execution_time_invalid")
        valid = (decision.state is ValidationDecisionState.READY_FOR_CONTROLLED_EXECUTION
            and request.authorization_request_digest == authorization_request.canonical_digest
            and request.authorization_approval_digest == authorization_approval.canonical_digest
            and request.plan_digest == plan.canonical_digest
            and request.environment_manifest_digest == environment.canonical_digest
            and request.scenario_digest == scenario.canonical_digest
            and request.requested_at <= started_at <= completed_at
            and request.operator_id not in {authorization_request.requested_by,
                authorization_request.reviewer_id, authorization_request.approver_id})
        if not valid or outcome is ControlledExecutionOutcome.COMMIT_FAULT:
            return ControlledExecutionResult(False, None)
        result = {ControlledExecutionOutcome.PASS: ExecutionResult.PASSED,
                  ControlledExecutionOutcome.FAIL: ExecutionResult.FAILED,
                  ControlledExecutionOutcome.INCOMPLETE: ExecutionResult.INCOMPLETE}[outcome]
        receipt = RealWorldExecutionReceipt("execution-receipt-v020", request.canonical_digest,
            authorization_request.canonical_digest, authorization_approval.canonical_digest,
            plan.canonical_digest, environment.canonical_digest, scenario.canonical_digest,
            scenario.expected_behavior_digest, _digest(_canonical_json({"count": scenario.scenario_count})),
            scenario.failure_policy_digest, started_at, completed_at, request.operator_id, result,
            _marker=_RECEIPT_MARKER)
        return ControlledExecutionResult(True, receipt)


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER.fullmatch(value))


def _is_version(value: object) -> bool:
    return isinstance(value, str) and bool(_VERSION.fullmatch(value))


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and bool(_DIGEST.fullmatch(value))


def _is_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
