from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ragguard.storage_adapter import (
    canonical_datetime,
    canonical_json,
    canonical_object_valid,
    digest,
    is_aware,
    is_digest,
    is_identifier,
)


MAX_ENVIRONMENT_EVIDENCE_AGE = timedelta(days=30)
_ENVIRONMENT_DECISION_MARKER = object()


class LocalRAGEnvironmentError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class EnvironmentClass(str, Enum):
    ISOLATED_LOCAL_TEST = "isolated_local_test"
    CONTROLLED_LOCAL_INTEGRATION = "controlled_local_integration"


class EnvironmentDataClass(str, Enum):
    SYNTHETIC_ONLY = "synthetic_only"
    CONTROLLED_FIXTURE_ONLY = "controlled_fixture_only"


class EnvironmentNetworkMode(str, Enum):
    DISABLED = "disabled"


class EnvironmentCredentialMode(str, Enum):
    NONE = "none"


class EnvironmentStorageMode(str, Enum):
    IN_MEMORY_ONLY = "in_memory_only"
    EPHEMERAL_TEST_ONLY = "ephemeral_test_only"


class VerificationResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class EnvironmentAttestationState(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_ENVIRONMENT_VERIFICATION = "needs_environment_verification"
    ELIGIBLE_FOR_ENVIRONMENT_REVIEW = "eligible_for_environment_review"


class EnvironmentReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class EnvironmentApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


@dataclass(frozen=True, repr=False)
class LocalRAGEnvironmentManifest(_Canonical):
    environment_id: str
    environment_class: EnvironmentClass
    local_rag_build_digest: str
    ragguard_build_digest: str
    integration_manifest_digest: str
    masking_policy_digest: str
    chunking_policy_digest: str
    embedding_policy_digest: str
    retrieval_policy_digest: str
    prompt_policy_digest: str
    logging_policy_digest: str
    cache_policy_digest: str
    dependency_set_digest: str
    configuration_digest: str
    execution_protocol_version: str
    data_class: EnvironmentDataClass
    network_mode: EnvironmentNetworkMode
    storage_mode: EnvironmentStorageMode
    credential_mode: EnvironmentCredentialMode
    created_at: datetime

    def __post_init__(self) -> None:
        digests = tuple(v for k, v in vars(self).items() if k.endswith("_digest"))
        if (not is_identifier(self.environment_id)
                or not is_identifier(self.execution_protocol_version)
                or not all(is_digest(v) for v in digests)
                or not isinstance(self.environment_class, EnvironmentClass)
                or not isinstance(self.data_class, EnvironmentDataClass)
                or not isinstance(self.network_mode, EnvironmentNetworkMode)
                or not isinstance(self.storage_mode, EnvironmentStorageMode)
                or not isinstance(self.credential_mode, EnvironmentCredentialMode)
                or not is_aware(self.created_at)):
            raise LocalRAGEnvironmentError("environment_manifest_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {k: (canonical_datetime(v) if isinstance(v, datetime)
                    else v.value if isinstance(v, Enum) else v)
                for k, v in vars(self).items() if k != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class _VerificationResult(_Canonical):
    result_id: str
    environment_manifest_digest: str
    verification_protocol_digest: str
    result: VerificationResult
    observed_state_digest: str
    executed_at: datetime
    executed_by: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.result_id) or not is_identifier(self.executed_by)
                or not is_digest(self.environment_manifest_digest)
                or not is_digest(self.verification_protocol_digest)
                or not is_digest(self.observed_state_digest)
                or not isinstance(self.result, VerificationResult)
                or not is_aware(self.executed_at)):
            raise LocalRAGEnvironmentError("verification_result_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"environment_manifest_digest": self.environment_manifest_digest,
                "executed_at": canonical_datetime(self.executed_at),
                "executed_by": self.executed_by, "observed_state_digest": self.observed_state_digest,
                "result": self.result.value, "result_id": self.result_id,
                "result_type": type(self).__name__,
                "verification_protocol_digest": self.verification_protocol_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class BuildVerificationResult(_VerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class DependencyVerificationResult(_VerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class ConfigurationVerificationResult(_VerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class NetworkIsolationVerificationResult(_VerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class StorageIsolationVerificationResult(_VerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class LoggingSafetyVerificationResult(_VerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class FixtureSafetyVerificationResult(_VerificationResult):
    pass


VerificationObjects = tuple[
    BuildVerificationResult,
    DependencyVerificationResult,
    ConfigurationVerificationResult,
    NetworkIsolationVerificationResult,
    StorageIsolationVerificationResult,
    LoggingSafetyVerificationResult,
    FixtureSafetyVerificationResult,
]


@dataclass(frozen=True, repr=False)
class EnvironmentAttestationSuite(_Canonical):
    environment_manifest_digest: str
    build_result_digest: str
    dependency_result_digest: str
    configuration_result_digest: str
    network_result_digest: str
    storage_result_digest: str
    logging_result_digest: str
    fixture_result_digest: str

    def __post_init__(self) -> None:
        if not all(is_digest(v) for v in vars(self).values()):
            raise LocalRAGEnvironmentError("attestation_suite_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {k: v for k, v in vars(self).items() if k != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class EnvironmentAttestationEvidence(_Canonical):
    environment_manifest_digest: str
    build_verification_digest: str
    dependency_verification_digest: str
    configuration_verification_digest: str
    network_isolation_digest: str
    storage_isolation_digest: str
    logging_safety_digest: str
    fixture_safety_digest: str
    verification_suite_digest: str
    generated_at: datetime
    generated_by: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.generated_by) or not is_aware(self.generated_at)
                or not all(is_digest(v) for k, v in vars(self).items() if k.endswith("_digest"))):
            raise LocalRAGEnvironmentError("attestation_evidence_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {k: canonical_datetime(v) if isinstance(v, datetime) else v
                for k, v in vars(self).items() if k != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class EnvironmentAttestationDecision(_Canonical):
    state: EnvironmentAttestationState
    manifest_digest: str
    suite_digest: str
    evidence_digest: str
    reason_codes: tuple[str, ...]
    evaluated_at: datetime
    production_environment_approved: bool = field(init=False, default=False)
    production_ready: bool = field(init=False, default=False)
    active: bool = field(init=False, default=False)
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        if (not isinstance(self.state, EnvironmentAttestationState)
                or not all(is_digest(v) for v in (
                    self.manifest_digest, self.suite_digest, self.evidence_digest))
                or not self.reason_codes or not all(is_identifier(v) for v in self.reason_codes)
                or not is_aware(self.evaluated_at)
                or (self.state is EnvironmentAttestationState.ELIGIBLE_FOR_ENVIRONMENT_REVIEW
                    and _marker is not _ENVIRONMENT_DECISION_MARKER)):
            raise LocalRAGEnvironmentError("attestation_decision_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"evaluated_at": canonical_datetime(self.evaluated_at),
                "evidence_digest": self.evidence_digest, "manifest_digest": self.manifest_digest,
                "reason_codes": list(self.reason_codes), "state": self.state.value,
                "suite_digest": self.suite_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class EnvironmentRoleContext(_Canonical):
    verifier_id: str
    reviewer_id: str
    approver_id: str

    def __post_init__(self) -> None:
        if (not all(is_identifier(v) for v in vars(self).values())
                or self.verifier_id == self.reviewer_id
                or self.verifier_id == self.approver_id
                or self.reviewer_id == self.approver_id):
            raise LocalRAGEnvironmentError("environment_role_conflict")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {"approver_id": self.approver_id, "reviewer_id": self.reviewer_id,
                "verifier_id": self.verifier_id}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class EnvironmentReview(_Canonical):
    review_id: str
    manifest_digest: str
    attestation_suite_digest: str
    reviewed_at: datetime
    reviewer_id: str
    result: EnvironmentReviewResult
    findings_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.review_id) or not is_identifier(self.reviewer_id)
                or not all(is_digest(v) for v in (
                    self.manifest_digest, self.attestation_suite_digest, self.findings_digest))
                or not is_aware(self.reviewed_at)
                or not isinstance(self.result, EnvironmentReviewResult)):
            raise LocalRAGEnvironmentError("environment_review_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"attestation_suite_digest": self.attestation_suite_digest,
                "findings_digest": self.findings_digest, "manifest_digest": self.manifest_digest,
                "result": self.result.value, "review_id": self.review_id,
                "reviewed_at": canonical_datetime(self.reviewed_at), "reviewer_id": self.reviewer_id}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class EnvironmentApproval(_Canonical):
    approval_id: str
    manifest_digest: str
    suite_digest: str
    review_digest: str
    approved_at: datetime
    approver_id: str
    result: EnvironmentApprovalResult
    real_data_approved: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if (not is_identifier(self.approval_id) or not is_identifier(self.approver_id)
                or not all(is_digest(v) for v in (
                    self.manifest_digest, self.suite_digest, self.review_digest))
                or not is_aware(self.approved_at)
                or not isinstance(self.result, EnvironmentApprovalResult)):
            raise LocalRAGEnvironmentError("environment_approval_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"approval_id": self.approval_id,
                "approved_at": canonical_datetime(self.approved_at),
                "approver_id": self.approver_id, "manifest_digest": self.manifest_digest,
                "result": self.result.value, "review_digest": self.review_digest,
                "suite_digest": self.suite_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


def verification_objects(results: VerificationObjects) -> tuple[_VerificationResult, ...]:
    return tuple(results)


def evaluate_environment_attestation(
    manifest: LocalRAGEnvironmentManifest,
    suite: EnvironmentAttestationSuite,
    results: VerificationObjects,
    evidence: EnvironmentAttestationEvidence,
    roles: EnvironmentRoleContext,
    *,
    evaluation_time: datetime,
) -> EnvironmentAttestationDecision:
    if not is_aware(evaluation_time):
        raise LocalRAGEnvironmentError("evaluation_time_invalid")
    reasons: list[str] = []
    objects = (manifest, suite, *verification_objects(results), evidence, roles)
    if not all(canonical_object_valid(v) for v in objects):
        reasons.append("forged_object")
    expected_types = (
        BuildVerificationResult, DependencyVerificationResult,
        ConfigurationVerificationResult, NetworkIsolationVerificationResult,
        StorageIsolationVerificationResult, LoggingSafetyVerificationResult,
        FixtureSafetyVerificationResult,
    )
    if len(results) != len(expected_types) or not all(
            isinstance(value, expected) for value, expected in zip(results, expected_types)):
        reasons.append("verification_set_invalid")
    result_digests = tuple(getattr(v, "canonical_digest", "") for v in results)
    suite_digests = (suite.build_result_digest, suite.dependency_result_digest,
        suite.configuration_result_digest, suite.network_result_digest,
        suite.storage_result_digest, suite.logging_result_digest, suite.fixture_result_digest)
    evidence_digests = (evidence.build_verification_digest,
        evidence.dependency_verification_digest, evidence.configuration_verification_digest,
        evidence.network_isolation_digest, evidence.storage_isolation_digest,
        evidence.logging_safety_digest, evidence.fixture_safety_digest)
    if (suite.environment_manifest_digest != manifest.canonical_digest
            or evidence.environment_manifest_digest != manifest.canonical_digest
            or evidence.verification_suite_digest != suite.canonical_digest
            or result_digests != suite_digests or result_digests != evidence_digests
            or any(v.environment_manifest_digest != manifest.canonical_digest for v in results)):
        reasons.append("digest_binding_mismatch")
    if any(v.result is not VerificationResult.PASSED for v in results):
        reasons.append("verification_not_passed")
    if (manifest.network_mode is not EnvironmentNetworkMode.DISABLED
            or manifest.credential_mode is not EnvironmentCredentialMode.NONE
            or manifest.data_class not in {
                EnvironmentDataClass.SYNTHETIC_ONLY,
                EnvironmentDataClass.CONTROLLED_FIXTURE_ONLY,
            }
            or manifest.storage_mode not in {
                EnvironmentStorageMode.IN_MEMORY_ONLY,
                EnvironmentStorageMode.EPHEMERAL_TEST_ONLY,
            }):
        reasons.append("unsafe_environment_mode")
    if (evidence.generated_by != roles.verifier_id
            or any(v.executed_by != roles.verifier_id for v in results)):
        reasons.append("verifier_mismatch")
    times = [v.executed_at for v in results]
    if (not times or not all(manifest.created_at <= v <= evidence.generated_at for v in times)
            or evidence.generated_at > evaluation_time
            or evaluation_time - evidence.generated_at > MAX_ENVIRONMENT_EVIDENCE_AGE):
        reasons.append("temporal_invalid")
    if reasons:
        state = (EnvironmentAttestationState.NEEDS_ENVIRONMENT_VERIFICATION
                 if reasons == ["verification_not_passed"] else EnvironmentAttestationState.INELIGIBLE)
    else:
        state = EnvironmentAttestationState.ELIGIBLE_FOR_ENVIRONMENT_REVIEW
    return EnvironmentAttestationDecision(state, manifest.canonical_digest,
        suite.canonical_digest, evidence.canonical_digest,
        tuple(dict.fromkeys(reasons or ["environment_verified"])), evaluation_time,
        _marker=_ENVIRONMENT_DECISION_MARKER
            if state is EnvironmentAttestationState.ELIGIBLE_FOR_ENVIRONMENT_REVIEW else None)


def validate_environment_approval(
    manifest: LocalRAGEnvironmentManifest,
    suite: EnvironmentAttestationSuite,
    decision: EnvironmentAttestationDecision,
    review: EnvironmentReview,
    approval: EnvironmentApproval,
    roles: EnvironmentRoleContext,
    *,
    evaluation_time: datetime,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not all(canonical_object_valid(v) for v in (
            manifest, suite, decision, review, approval, roles)):
        reasons.append("forged_environment_chain")
    if (decision.state is not EnvironmentAttestationState.ELIGIBLE_FOR_ENVIRONMENT_REVIEW
            or review.result is not EnvironmentReviewResult.APPROVED
            or approval.result is not EnvironmentApprovalResult.APPROVED):
        reasons.append("environment_not_approved")
    if (decision.manifest_digest != manifest.canonical_digest
            or decision.suite_digest != suite.canonical_digest
            or review.manifest_digest != manifest.canonical_digest
            or review.attestation_suite_digest != suite.canonical_digest
            or approval.manifest_digest != manifest.canonical_digest
            or approval.suite_digest != suite.canonical_digest
            or approval.review_digest != review.canonical_digest):
        reasons.append("environment_chain_mismatch")
    if (review.reviewer_id != roles.reviewer_id
            or approval.approver_id != roles.approver_id
            or roles.verifier_id == review.reviewer_id
            or review.reviewer_id == approval.approver_id):
        reasons.append("environment_role_conflict")
    if not (manifest.created_at <= decision.evaluated_at < review.reviewed_at
            < approval.approved_at <= evaluation_time
            and evaluation_time - approval.approved_at <= MAX_ENVIRONMENT_EVIDENCE_AGE):
        reasons.append("environment_approval_temporal_invalid")
    return tuple(dict.fromkeys(reasons))


__all__ = [
    "MAX_ENVIRONMENT_EVIDENCE_AGE", "BuildVerificationResult",
    "ConfigurationVerificationResult", "DependencyVerificationResult",
    "EnvironmentApproval", "EnvironmentApprovalResult", "EnvironmentAttestationDecision",
    "EnvironmentAttestationEvidence", "EnvironmentAttestationState",
    "EnvironmentAttestationSuite", "EnvironmentClass", "EnvironmentCredentialMode",
    "EnvironmentDataClass", "EnvironmentNetworkMode", "EnvironmentReview",
    "EnvironmentReviewResult", "EnvironmentRoleContext", "EnvironmentStorageMode",
    "FixtureSafetyVerificationResult", "LocalRAGEnvironmentError",
    "LocalRAGEnvironmentManifest", "LoggingSafetyVerificationResult",
    "NetworkIsolationVerificationResult", "StorageIsolationVerificationResult",
    "VerificationObjects", "VerificationResult", "evaluate_environment_attestation",
    "validate_environment_approval",
]
