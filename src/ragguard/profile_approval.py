from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    ScoreSemantics,
    SemanticVersion,
    SourceIdentifierPolicy,
    compatibility_error,
)
from ragguard.retrieval import MAX_LOCAL_TOP_K, RetrievalAdapterError


_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_MINOR_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_REQUIRED_CAPABILITIES = frozenset(
    {
        "retrieval",
        "bounded_top_k",
        "deterministic_result_schema",
        "safe_source_identifier",
        "response_size_compliance",
    }
)
_OPTIONAL_CAPABILITIES = frozenset(
    {"score", "title", "matched_keywords", "query_id_echo", "protocol_version_echo"}
)
_CAPABILITIES = _REQUIRED_CAPABILITIES | _OPTIONAL_CAPABILITIES
VALIDATION_CASE_IDS = frozenset(
    {
        "schema_validation",
        "synthetic_compatibility",
        "security_e2e",
        "capability_mapping",
        "request_response_mapping",
        "score_semantics",
        "source_identifier_policy",
        "timeout_boundary",
        "response_size_boundary",
        "error_non_disclosure",
        "manual_compatibility",
    }
)
_SAFE_VALIDATION_ERRORS = frozenset(category.value for category in CompatibilityErrorCategory)


class ProfileMaturity(str, Enum):
    DRAFT = "draft"
    SYNTHETIC_VALIDATED = "synthetic_validated"
    MANUALLY_VALIDATED = "manually_validated"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_RESTRICTIONS = "approved_with_restrictions"
    REJECTED = "rejected"
    NEEDS_REVALIDATION = "needs_revalidation"


class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVALIDATION = "needs_revalidation"


_ALLOWED_TRANSITIONS = frozenset(
    {
        (ProfileMaturity.DRAFT, ProfileMaturity.SYNTHETIC_VALIDATED),
        (ProfileMaturity.SYNTHETIC_VALIDATED, ProfileMaturity.MANUALLY_VALIDATED),
        (ProfileMaturity.MANUALLY_VALIDATED, ProfileMaturity.APPROVED),
        (ProfileMaturity.APPROVED, ProfileMaturity.DEPRECATED),
        (ProfileMaturity.APPROVED, ProfileMaturity.REVOKED),
        (ProfileMaturity.DEPRECATED, ProfileMaturity.REVOKED),
    }
)


def validate_maturity_transition(current: object, target: object) -> None:
    current_maturity = _enum_value(
        ProfileMaturity, current, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
    )
    target_maturity = _enum_value(
        ProfileMaturity, target, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
    )
    if (current_maturity, target_maturity) not in _ALLOWED_TRANSITIONS:
        raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)


@dataclass(frozen=True, repr=False)
class SupportedProductVersionRange:
    minimum_version: SemanticVersion
    maximum_version: SemanticVersion | None
    open_ended: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.minimum_version, SemanticVersion)
            or type(self.open_ended) is not bool
            or (self.open_ended and self.maximum_version is not None)
            or (not self.open_ended and not isinstance(self.maximum_version, SemanticVersion))
            or (
                isinstance(self.maximum_version, SemanticVersion)
                and self.minimum_version > self.maximum_version
            )
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> SupportedProductVersionRange:
        fields = {"minimum_version", "maximum_version", "open_ended"}
        if not isinstance(value, Mapping) or set(value) != fields:
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        maximum = value["maximum_version"]
        return cls(
            minimum_version=SemanticVersion.parse(
                value["minimum_version"],
                category=CompatibilityErrorCategory.APPROVAL_METADATA_INVALID,
            ),
            maximum_version=(
                None
                if maximum is None
                else SemanticVersion.parse(
                    maximum,
                    category=CompatibilityErrorCategory.APPROVAL_METADATA_INVALID,
                )
            ),
            open_ended=value["open_ended"],
        )

    def contains(self, value: object) -> bool:
        version = SemanticVersion.parse(
            value, category=CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED
        )
        return version >= self.minimum_version and (
            self.maximum_version is None or version <= self.maximum_version
        )

    def __repr__(self) -> str:
        return "SupportedProductVersionRange(<bounded>)"


@dataclass(frozen=True, repr=False)
class ApprovalRestrictions:
    maximum_top_k: int | None = None
    score_disabled: bool = False
    title_disabled: bool = False
    matched_keywords_disabled: bool = False
    query_id_echo_required: bool = False
    supported_minor_versions: tuple[str, ...] = ()
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        booleans = (
            self.score_disabled,
            self.title_disabled,
            self.matched_keywords_disabled,
            self.query_id_echo_required,
        )
        if (
            (self.maximum_top_k is not None and (
                type(self.maximum_top_k) is not int
                or self.maximum_top_k < 1
                or self.maximum_top_k > MAX_LOCAL_TOP_K
            ))
            or any(type(value) is not bool for value in booleans)
            or not isinstance(self.supported_minor_versions, tuple)
            or any(
                not isinstance(value, str) or _MINOR_VERSION.fullmatch(value) is None
                for value in self.supported_minor_versions
            )
            or tuple(sorted(set(self.supported_minor_versions)))
            != self.supported_minor_versions
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        _validate_datetime(self.expires_at, optional=True)

    @classmethod
    def from_mapping(cls, value: object) -> ApprovalRestrictions:
        fields = {
            "maximum_top_k",
            "score_disabled",
            "title_disabled",
            "matched_keywords_disabled",
            "query_id_echo_required",
            "supported_minor_versions",
            "expires_at",
        }
        if not isinstance(value, Mapping) or not set(value).issubset(fields):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        minor_versions = value.get("supported_minor_versions", ())
        if isinstance(minor_versions, list):
            minor_versions = tuple(minor_versions)
        return cls(
            maximum_top_k=value.get("maximum_top_k"),
            score_disabled=value.get("score_disabled", False),
            title_disabled=value.get("title_disabled", False),
            matched_keywords_disabled=value.get("matched_keywords_disabled", False),
            query_id_echo_required=value.get("query_id_echo_required", False),
            supported_minor_versions=minor_versions,
            expires_at=_parse_datetime(value.get("expires_at"), optional=True),
        )

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.maximum_top_k is not None,
                self.score_disabled,
                self.title_disabled,
                self.matched_keywords_disabled,
                self.query_id_echo_required,
                bool(self.supported_minor_versions),
                self.expires_at is not None,
            )
        )

    def __repr__(self) -> str:
        return "ApprovalRestrictions(<bounded>)"


@dataclass(frozen=True, repr=False)
class ValidationMetadata:
    validation_record_id: str
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    normalized_product_version: SemanticVersion
    validation_status: ValidationStatus
    validated_at: datetime
    validation_cases: tuple[str, ...]
    required_capabilities_result: bool
    optional_capabilities_result: tuple[str, ...]
    safe_error_categories: tuple[str, ...]
    result_summary: str

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
            or not isinstance(self.validation_status, ValidationStatus)
            or type(self.required_capabilities_result) is not bool
            or not _canonical_allowlist(self.validation_cases, VALIDATION_CASE_IDS)
            or not _canonical_allowlist(
                self.optional_capabilities_result, _OPTIONAL_CAPABILITIES
            )
            or not _canonical_allowlist(
                self.safe_error_categories, _SAFE_VALIDATION_ERRORS
            )
            or self.result_summary
            not in {"validation_passed", "validation_failed", "revalidation_required"}
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        _validate_datetime(self.validated_at)
        expected_summary = {
            ValidationStatus.PASSED: "validation_passed",
            ValidationStatus.FAILED: "validation_failed",
            ValidationStatus.NEEDS_REVALIDATION: "revalidation_required",
        }[self.validation_status]
        if (
            self.result_summary != expected_summary
            or (
                self.validation_status is ValidationStatus.PASSED
                and self.safe_error_categories
            )
            or (
                self.validation_status is not ValidationStatus.PASSED
                and not self.safe_error_categories
            )
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> ValidationMetadata:
        fields = {
            "validation_record_id", "profile_id", "profile_version", "protocol_version",
            "normalized_product_version", "validation_status", "validated_at",
            "validation_cases", "required_capabilities_result",
            "optional_capabilities_result", "safe_error_categories", "result_summary",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        return cls(
            validation_record_id=value["validation_record_id"],
            profile_id=value["profile_id"],
            profile_version=_version(value["profile_version"]),
            protocol_version=_version(value["protocol_version"]),
            normalized_product_version=_version(value["normalized_product_version"]),
            validation_status=_enum_value(
                ValidationStatus, value["validation_status"],
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID,
            ),
            validated_at=_parse_datetime(value["validated_at"]),
            validation_cases=_tuple(value["validation_cases"]),
            required_capabilities_result=value["required_capabilities_result"],
            optional_capabilities_result=_tuple(value["optional_capabilities_result"]),
            safe_error_categories=_tuple(value["safe_error_categories"]),
            result_summary=value["result_summary"],
        )

    def __repr__(self) -> str:
        return "ValidationMetadata(<safe>)"


@dataclass(frozen=True, repr=False)
class ApprovalMetadata:
    approval_record_id: str
    reviewer_id: str
    approver_id: str
    decision: ApprovalDecision
    approved_at: datetime
    validation_record_id: str
    supported_product_version_range: SupportedProductVersionRange
    approved_capabilities: tuple[str, ...]
    approved_score_semantics: ScoreSemantics
    approved_source_identifier_policy: SourceIdentifierPolicy
    restrictions: ApprovalRestrictions | None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            not all(
                _safe_identifier(value)
                for value in (
                    self.approval_record_id,
                    self.reviewer_id,
                    self.approver_id,
                    self.validation_record_id,
                )
            )
            or self.reviewer_id == self.approver_id
            or not isinstance(self.decision, ApprovalDecision)
            or not isinstance(
                self.supported_product_version_range, SupportedProductVersionRange
            )
            or not _canonical_allowlist(self.approved_capabilities, _CAPABILITIES)
            or not _REQUIRED_CAPABILITIES.issubset(self.approved_capabilities)
            or not isinstance(self.approved_score_semantics, ScoreSemantics)
            or not isinstance(
                self.approved_source_identifier_policy, SourceIdentifierPolicy
            )
            or (
                self.restrictions is not None
                and not isinstance(self.restrictions, ApprovalRestrictions)
            )
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        _validate_datetime(self.approved_at)
        _validate_datetime(self.expires_at, optional=True)
        if self.decision is ApprovalDecision.APPROVED_WITH_RESTRICTIONS:
            if self.restrictions is None or self.restrictions.is_empty:
                raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        elif self.restrictions is not None:
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        if self.restrictions is not None and (
            (self.restrictions.score_disabled and "score" in self.approved_capabilities)
            or (self.restrictions.title_disabled and "title" in self.approved_capabilities)
            or (
                self.restrictions.matched_keywords_disabled
                and "matched_keywords" in self.approved_capabilities
            )
            or (
                self.restrictions.query_id_echo_required
                and "query_id_echo" not in self.approved_capabilities
            )
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        if (
            self.approved_score_semantics is not ScoreSemantics.UNSCORED
            and "score" not in self.approved_capabilities
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> ApprovalMetadata:
        fields = {
            "approval_record_id", "reviewer_id", "approver_id", "decision", "approved_at",
            "validation_record_id", "supported_product_version_range",
            "approved_capabilities", "approved_score_semantics",
            "approved_source_identifier_policy", "restrictions", "expires_at",
        }
        required = fields - {"expires_at"}
        if (
            not isinstance(value, Mapping)
            or not required.issubset(value)
            or not set(value).issubset(fields)
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        restrictions = value["restrictions"]
        return cls(
            approval_record_id=value["approval_record_id"],
            reviewer_id=value["reviewer_id"],
            approver_id=value["approver_id"],
            decision=_enum_value(
                ApprovalDecision, value["decision"],
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID,
            ),
            approved_at=_parse_datetime(value["approved_at"]),
            validation_record_id=value["validation_record_id"],
            supported_product_version_range=SupportedProductVersionRange.from_mapping(
                value["supported_product_version_range"]
            ),
            approved_capabilities=_tuple(value["approved_capabilities"]),
            approved_score_semantics=_enum_value(
                ScoreSemantics, value["approved_score_semantics"],
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID,
            ),
            approved_source_identifier_policy=_enum_value(
                SourceIdentifierPolicy, value["approved_source_identifier_policy"],
                CompatibilityErrorCategory.APPROVAL_METADATA_INVALID,
            ),
            restrictions=(
                None if restrictions is None else ApprovalRestrictions.from_mapping(restrictions)
            ),
            expires_at=_parse_datetime(value.get("expires_at"), optional=True),
        )

    def __repr__(self) -> str:
        return "ApprovalMetadata(<safe>)"

    def is_expired(self, evaluation_time: datetime) -> bool:
        _validate_datetime(evaluation_time)
        return bool(
            (
                self.expires_at is not None
                and evaluation_time >= self.expires_at
            )
            or (
                self.restrictions is not None
                and self.restrictions.expires_at is not None
                and evaluation_time >= self.restrictions.expires_at
            )
        )


@dataclass(frozen=True, repr=False)
class ProfileApprovalContract:
    profile_id: str
    profile_version: SemanticVersion
    maturity: ProfileMaturity
    validation_metadata: ValidationMetadata | None = None
    approval_metadata: ApprovalMetadata | None = None
    revalidation_required: bool = False

    def __post_init__(self) -> None:
        if (
            not _safe_identifier(self.profile_id)
            or not isinstance(self.profile_version, SemanticVersion)
            or not isinstance(self.maturity, ProfileMaturity)
            or type(self.revalidation_required) is not bool
            or (
                self.validation_metadata is not None
                and not isinstance(self.validation_metadata, ValidationMetadata)
            )
            or (
                self.approval_metadata is not None
                and not isinstance(self.approval_metadata, ApprovalMetadata)
            )
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        validation = self.validation_metadata
        approval = self.approval_metadata
        if validation is not None and (
            validation.profile_id != self.profile_id
            or validation.profile_version != self.profile_version
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        if approval is not None and validation is not None and (
            approval.validation_record_id != validation.validation_record_id
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
        if approval is not None and validation is not None:
            approved_optional = set(approval.approved_capabilities) - _REQUIRED_CAPABILITIES
            if not approved_optional.issubset(validation.optional_capabilities_result):
                raise compatibility_error(
                    CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
                )
        if self.maturity is ProfileMaturity.APPROVED:
            if validation is None or approval is None:
                raise compatibility_error(CompatibilityErrorCategory.PROFILE_UNAPPROVED)
            if approval.decision not in {
                ApprovalDecision.APPROVED,
                ApprovalDecision.APPROVED_WITH_RESTRICTIONS,
            }:
                raise compatibility_error(CompatibilityErrorCategory.PROFILE_UNAPPROVED)
            if (
                validation.validation_status is not ValidationStatus.PASSED
                or not validation.required_capabilities_result
                or not VALIDATION_CASE_IDS.issubset(validation.validation_cases)
            ):
                raise compatibility_error(
                    CompatibilityErrorCategory.MANUAL_VALIDATION_REQUIRED
                )
        elif (
            self.maturity not in {ProfileMaturity.DEPRECATED, ProfileMaturity.REVOKED}
            and approval is not None
            and approval.decision in {
            ApprovalDecision.APPROVED,
            ApprovalDecision.APPROVED_WITH_RESTRICTIONS,
            }
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)

    def require_active_approval(
        self, product_version: object, *, now: datetime | None = None
    ) -> ApprovalSafeSummary:
        current_time = now or datetime.now(timezone.utc)
        _validate_datetime(current_time)
        if self.maturity is ProfileMaturity.REVOKED:
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_REVOKED)
        if self.maturity is ProfileMaturity.DEPRECATED:
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_UNAPPROVED)
        if self.revalidation_required:
            raise compatibility_error(CompatibilityErrorCategory.REVALIDATION_REQUIRED)
        validation = self.validation_metadata
        approval = self.approval_metadata
        if self.maturity is not ProfileMaturity.APPROVED or approval is None:
            category = (
                CompatibilityErrorCategory.MANUAL_VALIDATION_REQUIRED
                if self.maturity in {
                    ProfileMaturity.DRAFT,
                    ProfileMaturity.SYNTHETIC_VALIDATED,
                    ProfileMaturity.MANUALLY_VALIDATED,
                }
                else CompatibilityErrorCategory.PROFILE_UNAPPROVED
            )
            raise compatibility_error(category)
        if (
            validation is None
            or validation.validation_status is not ValidationStatus.PASSED
            or not validation.required_capabilities_result
            or not VALIDATION_CASE_IDS.issubset(validation.validation_cases)
        ):
            raise compatibility_error(CompatibilityErrorCategory.MANUAL_VALIDATION_REQUIRED)
        if approval.is_expired(current_time):
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_VALIDATION_EXPIRED)
        if not approval.supported_product_version_range.contains(product_version):
            raise compatibility_error(CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED)
        product = SemanticVersion.parse(
            product_version,
            category=CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED,
        )
        if (
            approval.restrictions is not None
            and approval.restrictions.supported_minor_versions
            and f"{product.major}.{product.minor}"
            not in approval.restrictions.supported_minor_versions
        ):
            raise compatibility_error(CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED)
        return self.safe_summary(product_version=product_version, now=current_time)

    def safe_summary(
        self, *, product_version: object | None = None, now: datetime | None = None
    ) -> ApprovalSafeSummary:
        approval = self.approval_metadata
        validation = self.validation_metadata
        supported = "unknown"
        if product_version is not None and approval is not None:
            try:
                supported = (
                    "supported"
                    if approval.supported_product_version_range.contains(product_version)
                    else "unsupported"
                )
            except RetrievalAdapterError:
                supported = "unsupported"
        current_time = now or datetime.now(timezone.utc)
        expired = approval.is_expired(current_time) if approval is not None else False
        return ApprovalSafeSummary(
            profile_id=self.profile_id,
            profile_version=str(self.profile_version),
            maturity=self.maturity.value,
            approval_decision=(approval.decision.value if approval else "unavailable"),
            approval_status=(
                "active"
                if self.maturity is ProfileMaturity.APPROVED
                and not expired
                and not self.revalidation_required
                else "inactive"
            ),
            supported_version_status=supported,
            restriction_summary=(
                "restricted" if approval and approval.restrictions else "none"
            ),
            validation_status=(
                validation.validation_status.value if validation else "unavailable"
            ),
            revalidation_required=self.revalidation_required,
            revoked=self.maturity is ProfileMaturity.REVOKED,
            deprecated=self.maturity is ProfileMaturity.DEPRECATED,
        )

    def __repr__(self) -> str:
        return "ProfileApprovalContract(<safe>)"


@dataclass(frozen=True)
class ApprovalSafeSummary:
    profile_id: str
    profile_version: str
    maturity: str
    approval_decision: str
    approval_status: str
    supported_version_status: str
    restriction_summary: str
    validation_status: str
    revalidation_required: bool
    revoked: bool
    deprecated: bool

    def as_mapping(self) -> dict[str, str | bool]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "maturity": self.maturity,
            "approval_decision": self.approval_decision,
            "approval_status": self.approval_status,
            "supported_version_status": self.supported_version_status,
            "restriction_summary": self.restriction_summary,
            "validation_status": self.validation_status,
            "revalidation_required": self.revalidation_required,
            "revoked": self.revoked,
            "deprecated": self.deprecated,
        }


def _safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) is not None


def _canonical_allowlist(values: object, allowed: frozenset[str]) -> bool:
    return (
        isinstance(values, tuple)
        and all(isinstance(value, str) and value in allowed for value in values)
        and tuple(sorted(set(values))) == values
    )


def _tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        value = tuple(value)
    if not isinstance(value, tuple):
        raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
    return value


def _version(value: object) -> SemanticVersion:
    return SemanticVersion.parse(
        value, category=CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
    )


def _enum_value(enum_type: type[Enum], value: object, category: CompatibilityErrorCategory):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise compatibility_error(category) from None


def _parse_datetime(value: object, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID) from None
    _validate_datetime(parsed)
    return parsed


def _validate_datetime(value: object, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise compatibility_error(CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)
