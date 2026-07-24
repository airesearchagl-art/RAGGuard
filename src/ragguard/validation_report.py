from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    SemanticVersion,
    compatibility_error,
)
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalMetadata,
    ProfileMaturity,
)
from ragguard.retrieval import RetrievalAdapterError


MAX_VALIDATION_DURATION_MS = 600_000
MAX_VALIDATION_RESULT_COUNT = 10_000
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SAFE_ERROR_CATEGORIES = frozenset(
    category.value for category in CompatibilityErrorCategory
)

VALIDATION_REPORT_CASE_IDS = frozenset(
    {
        "health_valid",
        "capabilities_valid",
        "required_capabilities_present",
        "request_mapping_valid",
        "response_mapping_valid",
        "pass_query",
        "warning_query",
        "fail_query",
        "malformed_response_rejected",
        "timeout_rejected",
        "oversized_response_rejected",
        "unsafe_source_rejected",
        "duplicate_id_rejected",
        "rank_gap_rejected",
        "query_id_echo_valid",
        "close_cleanup_valid",
        "report_non_disclosure_valid",
    }
)
_MANUAL_REQUIRED_CASE_IDS = frozenset(
    {
        "health_valid",
        "capabilities_valid",
        "required_capabilities_present",
        "request_mapping_valid",
        "response_mapping_valid",
        "pass_query",
        "warning_query",
        "fail_query",
        "malformed_response_rejected",
        "timeout_rejected",
        "oversized_response_rejected",
        "unsafe_source_rejected",
        "close_cleanup_valid",
        "report_non_disclosure_valid",
    }
)
_NOTES_CODES = frozenset(
    {
        "none",
        "expected_rejection",
        "optional_capability",
        "not_executed",
        "manual_observation",
    }
)


class ValidationCaseOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


class ValidationType(str, Enum):
    SYNTHETIC = "synthetic"
    MANUAL = "manual"


class ValidationEnvironmentClass(str, Enum):
    ISOLATED_LOCAL = "isolated_local"
    SYNTHETIC_HARNESS = "synthetic_harness"
    LOOPBACK_MANUAL = "loopback_manual"


class ValidationOverallStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    EXPIRED = "expired"


class ValidationCheckResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


def required_validation_case_ids(
    validation_type: ValidationType | str,
) -> frozenset[str]:
    kind = _enum_value(ValidationType, validation_type)
    if kind is ValidationType.SYNTHETIC:
        return VALIDATION_REPORT_CASE_IDS
    return _MANUAL_REQUIRED_CASE_IDS


@dataclass(frozen=True, repr=False)
class ValidationCaseResult:
    case_id: str
    outcome: ValidationCaseOutcome
    safe_error_category: str | None
    bounded_duration_ms: int
    result_count: int
    required: bool
    notes_code: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.case_id, str)
            or self.case_id not in VALIDATION_REPORT_CASE_IDS
            or not isinstance(self.outcome, ValidationCaseOutcome)
            or (
                self.safe_error_category is not None
                and self.safe_error_category not in _SAFE_ERROR_CATEGORIES
            )
            or type(self.bounded_duration_ms) is not int
            or self.bounded_duration_ms < 0
            or self.bounded_duration_ms > MAX_VALIDATION_DURATION_MS
            or type(self.result_count) is not int
            or self.result_count < 0
            or self.result_count > MAX_VALIDATION_RESULT_COUNT
            or type(self.required) is not bool
            or self.notes_code not in _NOTES_CODES
            or (
                self.outcome is ValidationCaseOutcome.FAILED
                and self.safe_error_category is None
            )
            or (
                self.outcome is not ValidationCaseOutcome.FAILED
                and self.safe_error_category is not None
            )
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )

    @classmethod
    def from_mapping(cls, value: object) -> ValidationCaseResult:
        fields = {
            "case_id",
            "outcome",
            "safe_error_category",
            "bounded_duration_ms",
            "result_count",
            "required",
            "notes_code",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        return cls(
            case_id=value["case_id"],
            outcome=_enum_value(ValidationCaseOutcome, value["outcome"]),
            safe_error_category=value["safe_error_category"],
            bounded_duration_ms=value["bounded_duration_ms"],
            result_count=value["result_count"],
            required=value["required"],
            notes_code=value["notes_code"],
        )

    def __repr__(self) -> str:
        return "ValidationCaseResult(<safe>)"


@dataclass(frozen=True, repr=False)
class ValidationReport:
    validation_record_id: str
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    normalized_product_version: SemanticVersion
    validation_type: ValidationType
    started_at: datetime
    completed_at: datetime
    environment_class: ValidationEnvironmentClass
    case_results: tuple[ValidationCaseResult, ...]
    required_capabilities_result: ValidationCheckResult
    optional_capabilities_result: ValidationCheckResult
    score_semantics_result: ValidationCheckResult
    source_policy_result: ValidationCheckResult
    transport_boundary_result: ValidationCheckResult
    non_disclosure_result: ValidationCheckResult
    overall_status: ValidationOverallStatus
    revalidation_required: bool
    safe_error_categories: tuple[str, ...]
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            not _safe_identifier(self.validation_record_id)
            or not _safe_identifier(self.profile_id)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.profile_version,
                    self.protocol_version,
                    self.normalized_product_version,
                )
            )
            or not isinstance(self.validation_type, ValidationType)
            or not isinstance(self.environment_class, ValidationEnvironmentClass)
            or not isinstance(self.case_results, tuple)
            or any(
                not isinstance(result, ValidationCaseResult)
                for result in self.case_results
            )
            or not all(
                isinstance(value, ValidationCheckResult)
                for value in (
                    self.required_capabilities_result,
                    self.optional_capabilities_result,
                    self.score_semantics_result,
                    self.source_policy_result,
                    self.transport_boundary_result,
                    self.non_disclosure_result,
                )
            )
            or not isinstance(self.overall_status, ValidationOverallStatus)
            or type(self.revalidation_required) is not bool
            or not _canonical_safe_categories(self.safe_error_categories)
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        _validate_datetime(self.started_at)
        _validate_datetime(self.completed_at)
        _validate_optional_datetime(self.expires_at)
        if self.completed_at < self.started_at:
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        allowed_environments = {
            ValidationType.SYNTHETIC: {
                ValidationEnvironmentClass.SYNTHETIC_HARNESS
            },
            ValidationType.MANUAL: {
                ValidationEnvironmentClass.ISOLATED_LOCAL,
                ValidationEnvironmentClass.LOOPBACK_MANUAL,
            },
        }[self.validation_type]
        if self.environment_class not in allowed_environments:
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        if self.expires_at is not None and self.expires_at < self.completed_at:
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        case_ids = tuple(result.case_id for result in self.case_results)
        if tuple(sorted(set(case_ids))) != case_ids:
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        required_ids = required_validation_case_ids(self.validation_type)
        if not required_ids.issubset(case_ids):
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        for result in self.case_results:
            if result.required is not (result.case_id in required_ids):
                raise compatibility_error(
                    CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
                )
        required_results = tuple(
            result for result in self.case_results if result.required
        )
        required_failure = any(
            result.outcome is not ValidationCaseOutcome.PASSED
            for result in required_results
        )
        if self.overall_status is ValidationOverallStatus.PASSED and (
            required_failure
            or self.required_capabilities_result is not ValidationCheckResult.PASSED
            or self.score_semantics_result is not ValidationCheckResult.PASSED
            or self.source_policy_result is not ValidationCheckResult.PASSED
            or self.transport_boundary_result is not ValidationCheckResult.PASSED
            or self.non_disclosure_result is not ValidationCheckResult.PASSED
            or self.safe_error_categories
            or self.revalidation_required
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        if (
            self.overall_status is ValidationOverallStatus.EXPIRED
            and not self.revalidation_required
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        case_error_categories = {
            result.safe_error_category
            for result in self.case_results
            if result.safe_error_category is not None
        }
        if not case_error_categories.issubset(self.safe_error_categories):
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )

    @classmethod
    def from_mapping(cls, value: object) -> ValidationReport:
        fields = {
            "validation_record_id",
            "profile_id",
            "profile_version",
            "protocol_version",
            "normalized_product_version",
            "validation_type",
            "started_at",
            "completed_at",
            "environment_class",
            "case_results",
            "required_capabilities_result",
            "optional_capabilities_result",
            "score_semantics_result",
            "source_policy_result",
            "transport_boundary_result",
            "non_disclosure_result",
            "overall_status",
            "revalidation_required",
            "safe_error_categories",
            "expires_at",
        }
        required_fields = fields - {"expires_at"}
        if (
            not isinstance(value, Mapping)
            or not required_fields.issubset(value)
            or not set(value).issubset(fields)
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        raw_cases = value["case_results"]
        if not isinstance(raw_cases, (list, tuple)):
            raise compatibility_error(
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
            )
        return cls(
            validation_record_id=value["validation_record_id"],
            profile_id=value["profile_id"],
            profile_version=_version(value["profile_version"]),
            protocol_version=_version(value["protocol_version"]),
            normalized_product_version=_version(value["normalized_product_version"]),
            validation_type=_enum_value(ValidationType, value["validation_type"]),
            started_at=_parse_datetime(value["started_at"]),
            completed_at=_parse_datetime(value["completed_at"]),
            environment_class=_enum_value(
                ValidationEnvironmentClass, value["environment_class"]
            ),
            case_results=tuple(
                ValidationCaseResult.from_mapping(case) for case in raw_cases
            ),
            required_capabilities_result=_enum_value(
                ValidationCheckResult, value["required_capabilities_result"]
            ),
            optional_capabilities_result=_enum_value(
                ValidationCheckResult, value["optional_capabilities_result"]
            ),
            score_semantics_result=_enum_value(
                ValidationCheckResult, value["score_semantics_result"]
            ),
            source_policy_result=_enum_value(
                ValidationCheckResult, value["source_policy_result"]
            ),
            transport_boundary_result=_enum_value(
                ValidationCheckResult, value["transport_boundary_result"]
            ),
            non_disclosure_result=_enum_value(
                ValidationCheckResult, value["non_disclosure_result"]
            ),
            overall_status=_enum_value(
                ValidationOverallStatus, value["overall_status"]
            ),
            revalidation_required=value["revalidation_required"],
            safe_error_categories=_tuple(value["safe_error_categories"]),
            expires_at=_parse_optional_datetime(value.get("expires_at")),
        )

    def __repr__(self) -> str:
        return "ValidationReport(<safe>)"


def evaluate_approval_decision(
    *,
    profile_id: str,
    profile_version: SemanticVersion,
    maturity: ProfileMaturity,
    validation_report: ValidationReport,
    approval_metadata: ApprovalMetadata | None,
    product_version: object,
    evaluation_time: datetime,
) -> ApprovalDecision:
    if (
        not _safe_identifier(profile_id)
        or not isinstance(profile_version, SemanticVersion)
        or not isinstance(maturity, ProfileMaturity)
        or not isinstance(validation_report, ValidationReport)
        or (
            approval_metadata is not None
            and not isinstance(approval_metadata, ApprovalMetadata)
        )
    ):
        raise compatibility_error(
            CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
        )
    _validate_datetime(evaluation_time)
    if (
        validation_report.profile_id != profile_id
        or validation_report.profile_version != profile_version
    ):
        raise compatibility_error(
            CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
        )
    if approval_metadata is None:
        return ApprovalDecision.REJECTED
    if (
        approval_metadata.validation_record_id
        != validation_report.validation_record_id
    ):
        raise compatibility_error(
            CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
        )
    if maturity in {ProfileMaturity.REVOKED, ProfileMaturity.DEPRECATED}:
        return ApprovalDecision.REJECTED
    if maturity not in {
        ProfileMaturity.MANUALLY_VALIDATED,
        ProfileMaturity.APPROVED,
    }:
        return ApprovalDecision.REJECTED
    if validation_report.validation_type is not ValidationType.MANUAL:
        return ApprovalDecision.REJECTED
    if (
        validation_report.overall_status is ValidationOverallStatus.EXPIRED
        or validation_report.revalidation_required
        or (
            validation_report.expires_at is not None
            and evaluation_time >= validation_report.expires_at
        )
        or approval_metadata.is_expired(evaluation_time)
        or approval_metadata.decision is ApprovalDecision.NEEDS_REVALIDATION
    ):
        return ApprovalDecision.NEEDS_REVALIDATION
    if validation_report.overall_status in {
        ValidationOverallStatus.FAILED,
        ValidationOverallStatus.INCOMPLETE,
    }:
        return ApprovalDecision.REJECTED
    if (
        validation_report.required_capabilities_result
        is not ValidationCheckResult.PASSED
        or validation_report.score_semantics_result
        is not ValidationCheckResult.PASSED
        or validation_report.source_policy_result
        is not ValidationCheckResult.PASSED
        or validation_report.transport_boundary_result
        is not ValidationCheckResult.PASSED
        or validation_report.non_disclosure_result
        is not ValidationCheckResult.PASSED
        or approval_metadata.decision is ApprovalDecision.REJECTED
    ):
        return ApprovalDecision.REJECTED
    try:
        supported = approval_metadata.supported_product_version_range.contains(
            product_version
        )
    except RetrievalAdapterError:
        supported = False
    if not supported:
        return ApprovalDecision.REJECTED
    product = SemanticVersion.parse(
        product_version,
        category=CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED,
    )
    restrictions = approval_metadata.restrictions
    if (
        restrictions is not None
        and restrictions.supported_minor_versions
        and f"{product.major}.{product.minor}"
        not in restrictions.supported_minor_versions
    ):
        return ApprovalDecision.REJECTED
    if validation_report.optional_capabilities_result is ValidationCheckResult.FAILED:
        if restrictions is None:
            return ApprovalDecision.REJECTED
        return ApprovalDecision.APPROVED_WITH_RESTRICTIONS
    if restrictions is not None:
        return ApprovalDecision.APPROVED_WITH_RESTRICTIONS
    return ApprovalDecision.APPROVED


@dataclass(frozen=True)
class ValidationReportSafeSummary:
    validation_record_id: str
    profile_id: str
    profile_version: str
    validation_type: str
    overall_status: str
    case_counts: tuple[tuple[str, int], ...]
    required_failures_count: int
    safe_error_categories: tuple[str, ...]
    revalidation_required: bool
    approval_decision: str

    def as_mapping(self) -> dict[str, object]:
        return {
            "validation_record_id": self.validation_record_id,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "validation_type": self.validation_type,
            "overall_status": self.overall_status,
            "case_counts": dict(self.case_counts),
            "required_failures_count": self.required_failures_count,
            "safe_error_categories": list(self.safe_error_categories),
            "revalidation_required": self.revalidation_required,
            "approval_decision": self.approval_decision,
        }


def summarize_validation_report(
    report: ValidationReport,
    *,
    approval_decision: ApprovalDecision,
) -> ValidationReportSafeSummary:
    if not isinstance(report, ValidationReport) or not isinstance(
        approval_decision, ApprovalDecision
    ):
        raise compatibility_error(
            CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
        )
    counts = tuple(
        (
            outcome.value,
            sum(result.outcome is outcome for result in report.case_results),
        )
        for outcome in ValidationCaseOutcome
    )
    required_failures = sum(
        result.required and result.outcome is not ValidationCaseOutcome.PASSED
        for result in report.case_results
    )
    return ValidationReportSafeSummary(
        validation_record_id=_short_identifier(report.validation_record_id),
        profile_id=report.profile_id,
        profile_version=str(report.profile_version),
        validation_type=report.validation_type.value,
        overall_status=report.overall_status.value,
        case_counts=counts,
        required_failures_count=required_failures,
        safe_error_categories=report.safe_error_categories,
        revalidation_required=report.revalidation_required,
        approval_decision=approval_decision.value,
    )


def _safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) is not None


def _short_identifier(value: str) -> str:
    return value if len(value) <= 12 else f"{value[:8]}-short"


def _canonical_safe_categories(values: object) -> bool:
    return (
        isinstance(values, tuple)
        and all(
            isinstance(value, str) and value in _SAFE_ERROR_CATEGORIES
            for value in values
        )
        and tuple(sorted(set(values))) == values
    )


def _tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        value = tuple(value)
    if not isinstance(value, tuple):
        raise compatibility_error(
            CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
        )
    return value


def _version(value: object) -> SemanticVersion:
    return SemanticVersion.parse(
        value, category=CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
    )


def _enum_value(enum_type: type[Enum], value: object):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise compatibility_error(
            CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
        ) from None


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise compatibility_error(
            CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise compatibility_error(
            CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
        ) from None
    _validate_datetime(parsed)
    return parsed


def _parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value)


def _validate_datetime(value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise compatibility_error(
            CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
        )


def _validate_optional_datetime(value: object) -> None:
    if value is not None:
        _validate_datetime(value)
