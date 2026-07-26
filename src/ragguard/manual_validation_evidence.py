from __future__ import annotations

import hashlib
import json
import re
from dataclasses import InitVar, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar, Mapping

from ragguard.compatibility import CompatibilityErrorCategory, SemanticVersion
from ragguard.manual_validation_plan import (
    ManualValidationCase,
    ManualValidationPlan,
    REQUIRED_MANUAL_VALIDATION_CASES,
)


MAX_EVIDENCE_FRESHNESS = timedelta(days=90)
CANONICAL_EVIDENCE_DIGEST_ALGORITHM = "sha256"

_SAFE_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_EVIDENCE_IDENTIFIER = re.compile(r"manual-evidence-[a-f0-9]{8,48}\Z")
_ENVIRONMENT_IDENTIFIER = re.compile(r"environment-ref-[a-f0-9]{8,48}\Z")
_ADAPTER_IDENTIFIER = re.compile(r"adapter-fixture-[a-z0-9][a-z0-9_-]{0,45}\Z")
_DIGEST = re.compile(r"sha256:[a-f0-9]{64}\Z")
_PROHIBITED_IDENTIFIER_TERMS = (
    "apikey",
    "api_key",
    "bearer",
    "cookie",
    "credential",
    "endpoint",
    "hostname",
    "password",
    "path",
    "secret",
    "token",
    "username",
)


class ManualValidationEvidenceErrorCategory(str, Enum):
    FIELD_SET_INVALID = "manual_evidence_field_set_invalid"
    IDENTITY_INVALID = "manual_evidence_identity_invalid"
    VERSION_INVALID = "manual_evidence_version_invalid"
    PLAN_BINDING_INVALID = "manual_evidence_plan_binding_invalid"
    ROLE_BINDING_INVALID = "manual_evidence_role_binding_invalid"
    EXECUTION_TIME_INVALID = "manual_evidence_execution_time_invalid"
    CASE_RESULTS_INVALID = "manual_evidence_case_results_invalid"
    ENVIRONMENT_FINGERPRINT_INVALID = "manual_evidence_environment_invalid"
    TOOL_VERSION_INVALID = "manual_evidence_tool_version_invalid"
    CLEANUP_EVIDENCE_INVALID = "manual_evidence_cleanup_invalid"
    NON_DISCLOSURE_EVIDENCE_INVALID = "manual_evidence_non_disclosure_invalid"
    FAILURE_SUMMARY_INVALID = "manual_evidence_failure_summary_invalid"


class ManualValidationEvidenceError(ValueError):
    def __init__(self, category: ManualValidationEvidenceErrorCategory) -> None:
        self.category = category
        super().__init__(category.value)


class EvidenceCaseOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ABORTED = "aborted"


class SafeCaseObservation(str, Enum):
    CASE_PASSED = "case_passed"
    CASE_FAILED = "case_failed"
    CASE_ABORTED = "case_aborted"


class EvidenceFailureCategory(str, Enum):
    CASE_ASSERTION_FAILED = "case_assertion_failed"
    EXECUTION_ABORTED = "execution_aborted"
    TIMEOUT = "timeout"
    SCHEMA_MISMATCH = "schema_mismatch"
    CLEANUP_FAILURE = "cleanup_failure"
    SAFETY_BOUNDARY_VIOLATION = "safety_boundary_violation"
    VERSION_MISMATCH = "version_mismatch"


class FailureSummaryCategory(str, Enum):
    FAILED_CASES = "failed_cases"
    ABORTED_CASES = "aborted_cases"
    FAILED_AND_ABORTED_CASES = "failed_and_aborted_cases"


class EnvironmentOSFamily(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"


class EnvironmentArchitecture(str, Enum):
    X86_64 = "x86_64"
    ARM64 = "arm64"


@dataclass(frozen=True, repr=False)
class ManualEvidenceCaseResult:
    case_id: ManualValidationCase
    outcome: EvidenceCaseOutcome
    executed_at: datetime
    safe_observation: SafeCaseObservation
    failure_category: EvidenceFailureCategory | None
    cleanup_confirmed: bool

    def __post_init__(self) -> None:
        expected_observation = {
            EvidenceCaseOutcome.PASSED: SafeCaseObservation.CASE_PASSED,
            EvidenceCaseOutcome.FAILED: SafeCaseObservation.CASE_FAILED,
            EvidenceCaseOutcome.ABORTED: SafeCaseObservation.CASE_ABORTED,
        }
        if (
            not isinstance(self.case_id, ManualValidationCase)
            or not isinstance(self.outcome, EvidenceCaseOutcome)
            or not _is_aware_datetime(self.executed_at)
            or not isinstance(self.safe_observation, SafeCaseObservation)
            or self.safe_observation is not expected_observation[self.outcome]
            or type(self.cleanup_confirmed) is not bool
            or (
                self.outcome is EvidenceCaseOutcome.PASSED
                and self.failure_category is not None
            )
            or (
                self.outcome is not EvidenceCaseOutcome.PASSED
                and not isinstance(self.failure_category, EvidenceFailureCategory)
            )
        ):
            _raise(ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> ManualEvidenceCaseResult:
        fields = {
            "case_id",
            "outcome",
            "executed_at",
            "safe_observation",
            "failure_category",
            "cleanup_confirmed",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID)
        outcome = _enum_value(
            EvidenceCaseOutcome,
            value["outcome"],
            ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID,
        )
        failure = value["failure_category"]
        return cls(
            case_id=_enum_value(
                ManualValidationCase,
                value["case_id"],
                ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID,
            ),
            outcome=outcome,
            executed_at=_parse_datetime(value["executed_at"]),
            safe_observation=_enum_value(
                SafeCaseObservation,
                value["safe_observation"],
                ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID,
            ),
            failure_category=(
                None
                if failure is None
                else _enum_value(
                    EvidenceFailureCategory,
                    failure,
                    ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID,
                )
            ),
            cleanup_confirmed=value["cleanup_confirmed"],
        )

    def __repr__(self) -> str:
        return (
            "ManualEvidenceCaseResult("
            f"case_id={self.case_id.value!r}, outcome={self.outcome.value!r})"
        )


@dataclass(frozen=True, repr=False)
class EvidenceEnvironmentFingerprint:
    environment_id: str = field(repr=False)
    os_family: EnvironmentOSFamily
    architecture: EnvironmentArchitecture
    python_version: SemanticVersion
    ragguard_version: SemanticVersion
    adapter_id: str
    profile_id: str
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_EVIDENCE_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            not isinstance(self.environment_id, str)
            or _ENVIRONMENT_IDENTIFIER.fullmatch(self.environment_id) is None
            or not isinstance(self.os_family, EnvironmentOSFamily)
            or not isinstance(self.architecture, EnvironmentArchitecture)
            or not isinstance(self.python_version, SemanticVersion)
            or not isinstance(self.ragguard_version, SemanticVersion)
            or not isinstance(self.adapter_id, str)
            or _ADAPTER_IDENTIFIER.fullmatch(self.adapter_id) is None
            or not _safe_identifier(self.profile_id)
            or _contains_prohibited_term(self.environment_id)
            or _contains_prohibited_term(self.adapter_id)
            or _contains_prohibited_term(self.profile_id)
        ):
            _raise(
                ManualValidationEvidenceErrorCategory.ENVIRONMENT_FINGERPRINT_INVALID
            )
        payload = {
            "adapter_id": self.adapter_id,
            "architecture": self.architecture.value,
            "environment_id": self.environment_id,
            "os_family": self.os_family.value,
            "profile_id": self.profile_id,
            "python_version": str(self.python_version),
            "ragguard_version": str(self.ragguard_version),
        }
        digest_value = hashlib.sha256(_canonical_json(payload).encode("utf-8"))
        object.__setattr__(
            self,
            "canonical_digest",
            f"{self.digest_algorithm}:{digest_value.hexdigest()}",
        )

    @classmethod
    def from_mapping(cls, value: object) -> EvidenceEnvironmentFingerprint:
        fields = {
            "environment_id",
            "os_family",
            "architecture",
            "python_version",
            "ragguard_version",
            "adapter_id",
            "profile_id",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(
                ManualValidationEvidenceErrorCategory.ENVIRONMENT_FINGERPRINT_INVALID
            )
        return cls(
            environment_id=value["environment_id"],
            os_family=_enum_value(
                EnvironmentOSFamily,
                value["os_family"],
                ManualValidationEvidenceErrorCategory.ENVIRONMENT_FINGERPRINT_INVALID,
            ),
            architecture=_enum_value(
                EnvironmentArchitecture,
                value["architecture"],
                ManualValidationEvidenceErrorCategory.ENVIRONMENT_FINGERPRINT_INVALID,
            ),
            python_version=_parse_version(
                value["python_version"],
                ManualValidationEvidenceErrorCategory.ENVIRONMENT_FINGERPRINT_INVALID,
            ),
            ragguard_version=_parse_version(
                value["ragguard_version"],
                ManualValidationEvidenceErrorCategory.ENVIRONMENT_FINGERPRINT_INVALID,
            ),
            adapter_id=value["adapter_id"],
            profile_id=value["profile_id"],
        )

    def canonical_mapping(self) -> dict[str, str]:
        return {
            "adapter_id": self.adapter_id,
            "architecture": self.architecture.value,
            "canonical_digest": self.canonical_digest,
            "environment_id": self.environment_id,
            "os_family": self.os_family.value,
            "profile_id": self.profile_id,
            "python_version": str(self.python_version),
            "ragguard_version": str(self.ragguard_version),
        }

    def __repr__(self) -> str:
        return (
            "EvidenceEnvironmentFingerprint("
            f"os_family={self.os_family.value!r}, "
            f"architecture={self.architecture.value!r}, "
            f"canonical_digest={self.canonical_digest!r})"
        )


@dataclass(frozen=True)
class CloseCleanupEvidence:
    transport_closed: bool
    close_exactly_once: bool
    temporary_safe_fixture_removed: bool
    no_raw_payload_retained: bool
    no_credential_retained: bool
    no_endpoint_detail_retained: bool
    safe_summary_produced: bool

    def __post_init__(self) -> None:
        values = (
            self.transport_closed,
            self.close_exactly_once,
            self.temporary_safe_fixture_removed,
            self.no_raw_payload_retained,
            self.no_credential_retained,
            self.no_endpoint_detail_retained,
            self.safe_summary_produced,
        )
        if any(type(value) is not bool or not value for value in values):
            _raise(ManualValidationEvidenceErrorCategory.CLEANUP_EVIDENCE_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> CloseCleanupEvidence:
        fields = {
            "transport_closed",
            "close_exactly_once",
            "temporary_safe_fixture_removed",
            "no_raw_payload_retained",
            "no_credential_retained",
            "no_endpoint_detail_retained",
            "safe_summary_produced",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(ManualValidationEvidenceErrorCategory.CLEANUP_EVIDENCE_INVALID)
        return cls(**{name: value[name] for name in fields})


@dataclass(frozen=True)
class NonDisclosureEvidence:
    no_credential_disclosure: bool
    no_endpoint_disclosure: bool
    no_path_disclosure: bool
    no_raw_request_disclosure: bool
    no_raw_response_disclosure: bool
    no_real_document_disclosure: bool
    no_stack_trace_disclosure: bool
    safe_error_only: bool

    def __post_init__(self) -> None:
        values = (
            self.no_credential_disclosure,
            self.no_endpoint_disclosure,
            self.no_path_disclosure,
            self.no_raw_request_disclosure,
            self.no_raw_response_disclosure,
            self.no_real_document_disclosure,
            self.no_stack_trace_disclosure,
            self.safe_error_only,
        )
        if any(type(value) is not bool or not value for value in values):
            _raise(
                ManualValidationEvidenceErrorCategory.NON_DISCLOSURE_EVIDENCE_INVALID
            )

    @classmethod
    def from_mapping(cls, value: object) -> NonDisclosureEvidence:
        fields = {
            "no_credential_disclosure",
            "no_endpoint_disclosure",
            "no_path_disclosure",
            "no_raw_request_disclosure",
            "no_raw_response_disclosure",
            "no_real_document_disclosure",
            "no_stack_trace_disclosure",
            "safe_error_only",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(
                ManualValidationEvidenceErrorCategory.NON_DISCLOSURE_EVIDENCE_INVALID
            )
        return cls(**{name: value[name] for name in fields})


@dataclass(frozen=True)
class ManualEvidenceFailureSummary:
    category: FailureSummaryCategory
    failed_case_count: int
    aborted_case_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.category, FailureSummaryCategory)
            or type(self.failed_case_count) is not int
            or type(self.aborted_case_count) is not int
            or self.failed_case_count < 0
            or self.aborted_case_count < 0
            or self.failed_case_count + self.aborted_case_count < 1
        ):
            _raise(ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> ManualEvidenceFailureSummary:
        fields = {"category", "failed_case_count", "aborted_case_count"}
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID)
        return cls(
            category=_enum_value(
                FailureSummaryCategory,
                value["category"],
                ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID,
            ),
            failed_case_count=value["failed_case_count"],
            aborted_case_count=value["aborted_case_count"],
        )


@dataclass(frozen=True)
class ManualValidationEvidenceSafeSummary:
    evidence_id: str
    plan_id: str
    plan_digest: str
    profile_id: str
    profile_version: str
    protocol_version: str
    product_id: str
    planned_product_version: str
    observed_product_version: str
    execution_started_at: str
    execution_completed_at: str
    expires_at: str
    case_count: int
    passed_count: int
    failed_count: int
    aborted_count: int
    role_separation_valid: bool
    environment_digest: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ManualValidationEvidence:
    evidence_id: str
    plan_id: str
    plan_digest: str
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    product_id: str
    planned_product_version: SemanticVersion
    observed_product_version: SemanticVersion
    execution_started_at: datetime
    execution_completed_at: datetime
    validation_operator_id: str
    evidence_reviewer_id: str
    environment_fingerprint: EvidenceEnvironmentFingerprint
    tool_version: SemanticVersion
    case_results: tuple[ManualEvidenceCaseResult, ...]
    close_cleanup_evidence: CloseCleanupEvidence
    non_disclosure_evidence: NonDisclosureEvidence
    failure_summary: ManualEvidenceFailureSummary | None
    expires_at: datetime
    plan: InitVar[ManualValidationPlan]
    safe_summary: ManualValidationEvidenceSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_EVIDENCE_DIGEST_ALGORITHM

    def __post_init__(self, plan: ManualValidationPlan) -> None:
        self._validate_identity_and_versions()
        self._validate_plan_binding(plan)
        self._validate_execution_time(plan)
        results = self._validate_case_results(plan)
        object.__setattr__(self, "case_results", results)
        self._validate_nested_contracts()
        counts = self._validate_failure_summary()

        digest_value = hashlib.sha256(
            self.canonical_json().encode("utf-8")
        ).hexdigest()
        digest = f"{self.digest_algorithm}:{digest_value}"
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ManualValidationEvidenceSafeSummary(
                evidence_id=self.evidence_id,
                plan_id=self.plan_id,
                plan_digest=self.plan_digest,
                profile_id=self.profile_id,
                profile_version=str(self.profile_version),
                protocol_version=str(self.protocol_version),
                product_id=self.product_id,
                planned_product_version=str(self.planned_product_version),
                observed_product_version=str(self.observed_product_version),
                execution_started_at=_canonical_datetime(
                    self.execution_started_at
                ),
                execution_completed_at=_canonical_datetime(
                    self.execution_completed_at
                ),
                expires_at=_canonical_datetime(self.expires_at),
                case_count=len(self.case_results),
                passed_count=counts[0],
                failed_count=counts[1],
                aborted_count=counts[2],
                role_separation_valid=True,
                environment_digest=self.environment_fingerprint.canonical_digest,
                canonical_digest=digest,
            ),
        )

    @classmethod
    def from_mapping(
        cls, value: object, *, plan: ManualValidationPlan
    ) -> ManualValidationEvidence:
        fields = {
            "evidence_id",
            "plan_id",
            "plan_digest",
            "profile_id",
            "profile_version",
            "protocol_version",
            "product_id",
            "planned_product_version",
            "observed_product_version",
            "execution_started_at",
            "execution_completed_at",
            "validation_operator_id",
            "evidence_reviewer_id",
            "environment_fingerprint",
            "tool_version",
            "case_results",
            "close_cleanup_evidence",
            "non_disclosure_evidence",
            "failure_summary",
            "expires_at",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(ManualValidationEvidenceErrorCategory.FIELD_SET_INVALID)
        raw_results = _tuple_input(
            value["case_results"],
            ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID,
        )
        failure = value["failure_summary"]
        return cls(
            evidence_id=value["evidence_id"],
            plan_id=value["plan_id"],
            plan_digest=value["plan_digest"],
            profile_id=value["profile_id"],
            profile_version=_parse_version(
                value["profile_version"],
                ManualValidationEvidenceErrorCategory.VERSION_INVALID,
            ),
            protocol_version=_parse_version(
                value["protocol_version"],
                ManualValidationEvidenceErrorCategory.VERSION_INVALID,
            ),
            product_id=value["product_id"],
            planned_product_version=_parse_version(
                value["planned_product_version"],
                ManualValidationEvidenceErrorCategory.VERSION_INVALID,
            ),
            observed_product_version=_parse_version(
                value["observed_product_version"],
                ManualValidationEvidenceErrorCategory.VERSION_INVALID,
            ),
            execution_started_at=_parse_datetime(value["execution_started_at"]),
            execution_completed_at=_parse_datetime(
                value["execution_completed_at"]
            ),
            validation_operator_id=value["validation_operator_id"],
            evidence_reviewer_id=value["evidence_reviewer_id"],
            environment_fingerprint=EvidenceEnvironmentFingerprint.from_mapping(
                value["environment_fingerprint"]
            ),
            tool_version=_parse_version(
                value["tool_version"],
                ManualValidationEvidenceErrorCategory.TOOL_VERSION_INVALID,
            ),
            case_results=tuple(
                ManualEvidenceCaseResult.from_mapping(result)
                for result in raw_results
            ),
            close_cleanup_evidence=CloseCleanupEvidence.from_mapping(
                value["close_cleanup_evidence"]
            ),
            non_disclosure_evidence=NonDisclosureEvidence.from_mapping(
                value["non_disclosure_evidence"]
            ),
            failure_summary=(
                None
                if failure is None
                else ManualEvidenceFailureSummary.from_mapping(failure)
            ),
            expires_at=_parse_datetime(value["expires_at"]),
            plan=plan,
        )

    @property
    def is_valid(self) -> bool:
        return all(
            result.outcome is EvidenceCaseOutcome.PASSED
            and result.cleanup_confirmed
            for result in self.case_results
        )

    def is_expired(self, evaluation_time: datetime) -> bool:
        if not _is_aware_datetime(evaluation_time):
            _raise(ManualValidationEvidenceErrorCategory.EXECUTION_TIME_INVALID)
        return evaluation_time >= self.expires_at

    def is_valid_at(self, evaluation_time: datetime) -> bool:
        return self.is_valid and not self.is_expired(evaluation_time)

    def canonical_json(self) -> str:
        payload = {
            "case_results": [
                {
                    "case_id": result.case_id.value,
                    "cleanup_confirmed": result.cleanup_confirmed,
                    "executed_at": _canonical_datetime(result.executed_at),
                    "failure_category": (
                        None
                        if result.failure_category is None
                        else result.failure_category.value
                    ),
                    "outcome": result.outcome.value,
                    "safe_observation": result.safe_observation.value,
                }
                for result in self.case_results
            ],
            "close_cleanup_evidence": {
                "close_exactly_once": (
                    self.close_cleanup_evidence.close_exactly_once
                ),
                "no_credential_retained": (
                    self.close_cleanup_evidence.no_credential_retained
                ),
                "no_endpoint_detail_retained": (
                    self.close_cleanup_evidence.no_endpoint_detail_retained
                ),
                "no_raw_payload_retained": (
                    self.close_cleanup_evidence.no_raw_payload_retained
                ),
                "safe_summary_produced": (
                    self.close_cleanup_evidence.safe_summary_produced
                ),
                "temporary_safe_fixture_removed": (
                    self.close_cleanup_evidence.temporary_safe_fixture_removed
                ),
                "transport_closed": self.close_cleanup_evidence.transport_closed,
            },
            "environment_fingerprint": (
                self.environment_fingerprint.canonical_mapping()
            ),
            "evidence_id": self.evidence_id,
            "evidence_reviewer_id": self.evidence_reviewer_id,
            "execution_completed_at": _canonical_datetime(
                self.execution_completed_at
            ),
            "execution_started_at": _canonical_datetime(
                self.execution_started_at
            ),
            "expires_at": _canonical_datetime(self.expires_at),
            "failure_summary": (
                None
                if self.failure_summary is None
                else {
                    "aborted_case_count": self.failure_summary.aborted_case_count,
                    "category": self.failure_summary.category.value,
                    "failed_case_count": self.failure_summary.failed_case_count,
                }
            ),
            "non_disclosure_evidence": {
                "no_credential_disclosure": (
                    self.non_disclosure_evidence.no_credential_disclosure
                ),
                "no_endpoint_disclosure": (
                    self.non_disclosure_evidence.no_endpoint_disclosure
                ),
                "no_path_disclosure": (
                    self.non_disclosure_evidence.no_path_disclosure
                ),
                "no_raw_request_disclosure": (
                    self.non_disclosure_evidence.no_raw_request_disclosure
                ),
                "no_raw_response_disclosure": (
                    self.non_disclosure_evidence.no_raw_response_disclosure
                ),
                "no_real_document_disclosure": (
                    self.non_disclosure_evidence.no_real_document_disclosure
                ),
                "no_stack_trace_disclosure": (
                    self.non_disclosure_evidence.no_stack_trace_disclosure
                ),
                "safe_error_only": self.non_disclosure_evidence.safe_error_only,
            },
            "observed_product_version": str(self.observed_product_version),
            "plan_digest": self.plan_digest,
            "plan_id": self.plan_id,
            "planned_product_version": str(self.planned_product_version),
            "product_id": self.product_id,
            "profile_id": self.profile_id,
            "profile_version": str(self.profile_version),
            "protocol_version": str(self.protocol_version),
            "tool_version": str(self.tool_version),
            "validation_operator_id": self.validation_operator_id,
        }
        return _canonical_json(payload)

    def _validate_identity_and_versions(self) -> None:
        if (
            not isinstance(self.evidence_id, str)
            or _EVIDENCE_IDENTIFIER.fullmatch(self.evidence_id) is None
            or not _safe_identifier(self.plan_id)
            or not isinstance(self.plan_digest, str)
            or _DIGEST.fullmatch(self.plan_digest) is None
            or not _safe_identifier(self.profile_id)
            or not _safe_identifier(self.product_id)
            or _contains_prohibited_term(self.evidence_id)
        ):
            _raise(ManualValidationEvidenceErrorCategory.IDENTITY_INVALID)
        if not all(
            isinstance(value, SemanticVersion)
            for value in (
                self.profile_version,
                self.protocol_version,
                self.planned_product_version,
                self.observed_product_version,
                self.tool_version,
            )
        ):
            _raise(ManualValidationEvidenceErrorCategory.VERSION_INVALID)

    def _validate_plan_binding(self, plan: ManualValidationPlan) -> None:
        if not isinstance(plan, ManualValidationPlan):
            _raise(ManualValidationEvidenceErrorCategory.PLAN_BINDING_INVALID)
        if (
            self.plan_id != plan.plan_id
            or self.plan_digest != plan.canonical_digest
            or self.profile_id != plan.profile_id
            or self.profile_version != plan.profile_version
            or self.protocol_version != plan.protocol_version
            or self.product_id != plan.product_id
            or self.planned_product_version != plan.product_version
            or self.observed_product_version != self.planned_product_version
        ):
            _raise(ManualValidationEvidenceErrorCategory.PLAN_BINDING_INVALID)
        if (
            self.validation_operator_id != plan.validation_operator_id
            or self.evidence_reviewer_id != plan.evidence_reviewer_id
            or self.validation_operator_id == self.evidence_reviewer_id
        ):
            _raise(ManualValidationEvidenceErrorCategory.ROLE_BINDING_INVALID)

    def _validate_execution_time(self, plan: ManualValidationPlan) -> None:
        timestamps = (
            self.execution_started_at,
            self.execution_completed_at,
            self.expires_at,
        )
        if (
            not all(_is_aware_datetime(value) for value in timestamps)
            or self.execution_started_at >= self.execution_completed_at
            or self.execution_started_at < plan.execution_window_start
            or self.execution_completed_at > plan.execution_window_end
            or self.execution_completed_at >= self.expires_at
            or self.expires_at - self.execution_completed_at
            > MAX_EVIDENCE_FRESHNESS
        ):
            _raise(ManualValidationEvidenceErrorCategory.EXECUTION_TIME_INVALID)

    def _validate_case_results(
        self, plan: ManualValidationPlan
    ) -> tuple[ManualEvidenceCaseResult, ...]:
        if (
            not isinstance(self.case_results, tuple)
            or any(
                not isinstance(result, ManualEvidenceCaseResult)
                for result in self.case_results
            )
        ):
            _raise(ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID)
        case_ids = tuple(result.case_id for result in self.case_results)
        if (
            len(case_ids) != len(set(case_ids))
            or set(case_ids) != set(REQUIRED_MANUAL_VALIDATION_CASES)
            or set(case_ids) != set(plan.required_case_ids)
            or any(
                result.executed_at < self.execution_started_at
                or result.executed_at > self.execution_completed_at
                for result in self.case_results
            )
        ):
            _raise(ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID)
        by_id = {result.case_id: result for result in self.case_results}
        return tuple(by_id[case_id] for case_id in REQUIRED_MANUAL_VALIDATION_CASES)

    def _validate_nested_contracts(self) -> None:
        if (
            not isinstance(
                self.environment_fingerprint, EvidenceEnvironmentFingerprint
            )
            or self.environment_fingerprint.profile_id != self.profile_id
        ):
            _raise(
                ManualValidationEvidenceErrorCategory.ENVIRONMENT_FINGERPRINT_INVALID
            )
        if (
            not isinstance(self.tool_version, SemanticVersion)
            or self.tool_version != self.environment_fingerprint.ragguard_version
        ):
            _raise(ManualValidationEvidenceErrorCategory.TOOL_VERSION_INVALID)
        if not isinstance(self.close_cleanup_evidence, CloseCleanupEvidence):
            _raise(ManualValidationEvidenceErrorCategory.CLEANUP_EVIDENCE_INVALID)
        if not isinstance(self.non_disclosure_evidence, NonDisclosureEvidence):
            _raise(
                ManualValidationEvidenceErrorCategory.NON_DISCLOSURE_EVIDENCE_INVALID
            )

    def _validate_failure_summary(self) -> tuple[int, int, int]:
        passed = sum(
            result.outcome is EvidenceCaseOutcome.PASSED
            for result in self.case_results
        )
        failed = sum(
            result.outcome is EvidenceCaseOutcome.FAILED
            for result in self.case_results
        )
        aborted = sum(
            result.outcome is EvidenceCaseOutcome.ABORTED
            for result in self.case_results
        )
        if failed == 0 and aborted == 0:
            if self.failure_summary is not None:
                _raise(
                    ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID
                )
            return passed, failed, aborted
        if not isinstance(self.failure_summary, ManualEvidenceFailureSummary):
            _raise(ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID)
        expected_category = (
            FailureSummaryCategory.FAILED_AND_ABORTED_CASES
            if failed and aborted
            else (
                FailureSummaryCategory.FAILED_CASES
                if failed
                else FailureSummaryCategory.ABORTED_CASES
            )
        )
        if (
            self.failure_summary.category is not expected_category
            or self.failure_summary.failed_case_count != failed
            or self.failure_summary.aborted_case_count != aborted
        ):
            _raise(ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID)
        return passed, failed, aborted

    def __repr__(self) -> str:
        digest = getattr(self, "canonical_digest", "<unavailable>")
        return (
            "ManualValidationEvidence("
            f"evidence_id={self.evidence_id!r}, plan_id={self.plan_id!r}, "
            f"canonical_digest={digest!r})"
        )


def _raise(category: ManualValidationEvidenceErrorCategory) -> None:
    raise ManualValidationEvidenceError(category) from None


def _contains_prohibited_term(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in _PROHIBITED_IDENTIFIER_TERMS)


def _safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and _SAFE_IDENTIFIER.fullmatch(value) is not None
        and not _contains_prohibited_term(value)
    )


def _parse_version(
    value: object, category: ManualValidationEvidenceErrorCategory
) -> SemanticVersion:
    try:
        return SemanticVersion.parse(
            value, category=CompatibilityErrorCategory.INVALID_PROFILE
        )
    except Exception:
        _raise(category)


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        _raise(ManualValidationEvidenceErrorCategory.EXECUTION_TIME_INVALID)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _raise(ManualValidationEvidenceErrorCategory.EXECUTION_TIME_INVALID)
    if not _is_aware_datetime(parsed):
        _raise(ManualValidationEvidenceErrorCategory.EXECUTION_TIME_INVALID)
    return parsed


def _is_aware_datetime(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _canonical_datetime(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _tuple_input(
    value: object, category: ManualValidationEvidenceErrorCategory
) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        _raise(category)
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError:
        _raise(category)


def _enum_value(
    enum_type: type[Enum],
    value: object,
    category: ManualValidationEvidenceErrorCategory,
):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        _raise(category)


__all__ = [
    "CANONICAL_EVIDENCE_DIGEST_ALGORITHM",
    "CloseCleanupEvidence",
    "EnvironmentArchitecture",
    "EnvironmentOSFamily",
    "EvidenceCaseOutcome",
    "EvidenceEnvironmentFingerprint",
    "EvidenceFailureCategory",
    "FailureSummaryCategory",
    "MAX_EVIDENCE_FRESHNESS",
    "ManualEvidenceCaseResult",
    "ManualEvidenceFailureSummary",
    "ManualValidationEvidence",
    "ManualValidationEvidenceError",
    "ManualValidationEvidenceErrorCategory",
    "ManualValidationEvidenceSafeSummary",
    "NonDisclosureEvidence",
    "SafeCaseObservation",
]
