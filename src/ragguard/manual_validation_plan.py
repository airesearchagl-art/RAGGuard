from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar, Mapping

from ragguard.compatibility import CompatibilityErrorCategory, SemanticVersion


MAX_EXECUTION_WINDOW = timedelta(days=30)
CANONICAL_DIGEST_ALGORITHM = "sha256"

_SAFE_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_PRODUCT_IDENTIFIER = re.compile(r"product-fixture-[a-z0-9][a-z0-9_-]{0,47}\Z")
_BOUNDARY_MARKER = re.compile(r"boundary-[a-z0-9][a-z0-9_-]{0,54}\Z")
_ENDPOINT_REFERENCE = re.compile(r"endpoint-ref-[a-f0-9]{8,48}\Z")
_SYNTHETIC_REFERENCE = re.compile(r"synthetic-evidence-[a-f0-9]{8,48}\Z")
_PROHIBITED_IDENTIFIER_TERMS = (
    "apikey",
    "api_key",
    "bearer",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)


class ManualValidationPlanErrorCategory(str, Enum):
    FIELD_SET_INVALID = "manual_plan_field_set_invalid"
    IDENTITY_INVALID = "manual_plan_identity_invalid"
    VERSION_INVALID = "manual_plan_version_invalid"
    ROLE_SEPARATION_INVALID = "manual_plan_role_separation_invalid"
    EXECUTION_WINDOW_INVALID = "manual_plan_execution_window_invalid"
    REQUIRED_CASES_INVALID = "manual_plan_required_cases_invalid"
    ENDPOINT_BOUNDARY_INVALID = "manual_plan_endpoint_boundary_invalid"
    DATA_BOUNDARY_INVALID = "manual_plan_data_boundary_invalid"
    CREDENTIAL_BOUNDARY_INVALID = "manual_plan_credential_boundary_invalid"
    ABORT_CONDITIONS_INVALID = "manual_plan_abort_conditions_invalid"
    CLEANUP_CONDITIONS_INVALID = "manual_plan_cleanup_conditions_invalid"
    SYNTHETIC_EVIDENCE_INVALID = "manual_plan_synthetic_evidence_invalid"


class ManualValidationPlanError(ValueError):
    def __init__(self, category: ManualValidationPlanErrorCategory) -> None:
        self.category = category
        super().__init__(category.value)


class ManualValidationCase(str, Enum):
    HEALTH_VALID = "health_valid"
    CAPABILITIES_VALID = "capabilities_valid"
    REQUIRED_CAPABILITIES_PRESENT = "required_capabilities_present"
    REQUEST_MAPPING_VALID = "request_mapping_valid"
    RESPONSE_MAPPING_VALID = "response_mapping_valid"
    PASS_QUERY = "pass_query"
    WARNING_QUERY = "warning_query"
    FAIL_QUERY = "fail_query"
    MALFORMED_RESPONSE_REJECTED = "malformed_response_rejected"
    TIMEOUT_REJECTED = "timeout_rejected"
    OVERSIZED_RESPONSE_REJECTED = "oversized_response_rejected"
    UNSAFE_SOURCE_REJECTED = "unsafe_source_rejected"
    DUPLICATE_ID_REJECTED = "duplicate_id_rejected"
    RANK_GAP_REJECTED = "rank_gap_rejected"
    QUERY_ID_ECHO_VALID = "query_id_echo_valid"
    CLOSE_CLEANUP_VALID = "close_cleanup_valid"
    REPORT_NON_DISCLOSURE_VALID = "report_non_disclosure_valid"
    PRODUCT_VERSION_VALID = "product_version_valid"
    UNSUPPORTED_PRODUCT_VERSION_REJECTED = "unsupported_product_version_rejected"
    APPROVAL_DENIAL_BEFORE_TRANSPORT = "approval_denial_before_transport"
    CREDENTIAL_NON_DISCLOSURE_VALID = "credential_non_disclosure_valid"
    ENDPOINT_NON_DISCLOSURE_VALID = "endpoint_non_disclosure_valid"


REQUIRED_MANUAL_VALIDATION_CASES = tuple(ManualValidationCase)


class EndpointBoundaryCategory(str, Enum):
    LOOPBACK = "loopback"


class AbortCondition(str, Enum):
    UNEXPECTED_NETWORK_DESTINATION = "unexpected_network_destination"
    CREDENTIAL_REQUEST = "credential_request"
    UNSAFE_SOURCE_DISCLOSURE = "unsafe_source_disclosure"
    RAW_PAYLOAD_RETENTION_ATTEMPT = "raw_payload_retention_attempt"
    SCHEMA_MISMATCH = "schema_mismatch"
    UNSUPPORTED_PRODUCT_VERSION = "unsupported_product_version"
    RESPONSE_SIZE_VIOLATION = "response_size_violation"
    TIMEOUT = "timeout"
    CLEANUP_FAILURE = "cleanup_failure"


REQUIRED_ABORT_CONDITIONS = tuple(AbortCondition)


class CleanupCondition(str, Enum):
    TRANSPORT_CLOSED = "transport_closed"
    TEMPORARY_SAFE_FIXTURE_REMOVED = "temporary_safe_fixture_removed"
    NO_RAW_PAYLOAD_RETAINED = "no_raw_payload_retained"
    NO_CREDENTIAL_RETAINED = "no_credential_retained"
    NO_ENDPOINT_DETAIL_RETAINED = "no_endpoint_detail_retained"
    SAFE_SUMMARY_PRODUCED = "safe_summary_produced"


REQUIRED_CLEANUP_CONDITIONS = tuple(CleanupCondition)


@dataclass(frozen=True, repr=False)
class EndpointBoundary:
    category: EndpointBoundaryCategory
    approved_boundary_marker: str = field(repr=False)
    opaque_endpoint_reference: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.category, EndpointBoundaryCategory)
            or not _safe_endpoint_component(
                self.approved_boundary_marker, _BOUNDARY_MARKER
            )
            or not _safe_endpoint_component(
                self.opaque_endpoint_reference, _ENDPOINT_REFERENCE
            )
        ):
            _raise(ManualValidationPlanErrorCategory.ENDPOINT_BOUNDARY_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> EndpointBoundary:
        fields = {
            "category",
            "approved_boundary_marker",
            "opaque_endpoint_reference",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(ManualValidationPlanErrorCategory.ENDPOINT_BOUNDARY_INVALID)
        try:
            category = EndpointBoundaryCategory(value["category"])
        except (TypeError, ValueError):
            _raise(ManualValidationPlanErrorCategory.ENDPOINT_BOUNDARY_INVALID)
        return cls(
            category=category,
            approved_boundary_marker=value["approved_boundary_marker"],
            opaque_endpoint_reference=value["opaque_endpoint_reference"],
        )

    def __repr__(self) -> str:
        return f"EndpointBoundary(category={self.category.value!r})"


@dataclass(frozen=True)
class DataBoundary:
    synthetic_only: bool
    no_customer_data: bool
    no_production_data: bool
    no_real_documents: bool
    no_raw_payload_retention: bool
    safe_summary_only: bool

    def __post_init__(self) -> None:
        values = (
            self.synthetic_only,
            self.no_customer_data,
            self.no_production_data,
            self.no_real_documents,
            self.no_raw_payload_retention,
            self.safe_summary_only,
        )
        if any(type(value) is not bool or not value for value in values):
            _raise(ManualValidationPlanErrorCategory.DATA_BOUNDARY_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> DataBoundary:
        fields = {
            "synthetic_only",
            "no_customer_data",
            "no_production_data",
            "no_real_documents",
            "no_raw_payload_retention",
            "safe_summary_only",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(ManualValidationPlanErrorCategory.DATA_BOUNDARY_INVALID)
        return cls(**{name: value[name] for name in fields})


@dataclass(frozen=True)
class CredentialBoundary:
    credentials_prohibited: bool

    def __post_init__(self) -> None:
        if type(self.credentials_prohibited) is not bool or not self.credentials_prohibited:
            _raise(ManualValidationPlanErrorCategory.CREDENTIAL_BOUNDARY_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> CredentialBoundary:
        if (
            not isinstance(value, Mapping)
            or set(value) != {"credentials_prohibited"}
        ):
            _raise(ManualValidationPlanErrorCategory.CREDENTIAL_BOUNDARY_INVALID)
        return cls(credentials_prohibited=value["credentials_prohibited"])


@dataclass(frozen=True, repr=False)
class SyntheticEvidenceReference:
    reference_id: str = field(repr=False)
    profile_id: str
    profile_version: SemanticVersion

    def __post_init__(self) -> None:
        if (
            not isinstance(self.reference_id, str)
            or _SYNTHETIC_REFERENCE.fullmatch(self.reference_id) is None
            or _contains_prohibited_term(self.reference_id)
            or not _safe_identifier(self.profile_id)
            or not isinstance(self.profile_version, SemanticVersion)
        ):
            _raise(ManualValidationPlanErrorCategory.SYNTHETIC_EVIDENCE_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> SyntheticEvidenceReference:
        fields = {"reference_id", "profile_id", "profile_version"}
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(ManualValidationPlanErrorCategory.SYNTHETIC_EVIDENCE_INVALID)
        return cls(
            reference_id=value["reference_id"],
            profile_id=value["profile_id"],
            profile_version=_parse_version(
                value["profile_version"],
                ManualValidationPlanErrorCategory.SYNTHETIC_EVIDENCE_INVALID,
            ),
        )

    def __repr__(self) -> str:
        return "SyntheticEvidenceReference(<opaque>)"


@dataclass(frozen=True)
class ManualValidationPlanSafeSummary:
    plan_id: str
    profile_id: str
    profile_version: str
    protocol_version: str
    product_id: str
    product_version: str
    execution_window_start: str
    execution_window_end: str
    case_count: int
    role_separation_valid: bool
    boundary_category: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ManualValidationPlan:
    plan_id: str
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    created_at: datetime
    execution_window_start: datetime
    execution_window_end: datetime
    profile_implementer_id: str
    validation_operator_id: str
    evidence_reviewer_id: str
    approver_id: str
    registry_administrator_id: str
    required_case_ids: tuple[ManualValidationCase, ...]
    endpoint_boundary: EndpointBoundary
    data_boundary: DataBoundary
    credential_boundary: CredentialBoundary
    abort_conditions: tuple[AbortCondition, ...]
    cleanup_conditions: tuple[CleanupCondition, ...]
    synthetic_evidence_reference: SyntheticEvidenceReference = field(repr=False)
    safe_summary: ManualValidationPlanSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        self._validate_identity()
        self._validate_roles()
        self._validate_execution_window()
        required_cases = _canonical_enum_set(
            self.required_case_ids,
            REQUIRED_MANUAL_VALIDATION_CASES,
            ManualValidationCase,
            ManualValidationPlanErrorCategory.REQUIRED_CASES_INVALID,
        )
        abort_conditions = _canonical_enum_set(
            self.abort_conditions,
            REQUIRED_ABORT_CONDITIONS,
            AbortCondition,
            ManualValidationPlanErrorCategory.ABORT_CONDITIONS_INVALID,
        )
        cleanup_conditions = _canonical_enum_set(
            self.cleanup_conditions,
            REQUIRED_CLEANUP_CONDITIONS,
            CleanupCondition,
            ManualValidationPlanErrorCategory.CLEANUP_CONDITIONS_INVALID,
        )
        object.__setattr__(self, "required_case_ids", required_cases)
        object.__setattr__(self, "abort_conditions", abort_conditions)
        object.__setattr__(self, "cleanup_conditions", cleanup_conditions)

        if not isinstance(self.endpoint_boundary, EndpointBoundary):
            _raise(ManualValidationPlanErrorCategory.ENDPOINT_BOUNDARY_INVALID)
        if not isinstance(self.data_boundary, DataBoundary):
            _raise(ManualValidationPlanErrorCategory.DATA_BOUNDARY_INVALID)
        if not isinstance(self.credential_boundary, CredentialBoundary):
            _raise(ManualValidationPlanErrorCategory.CREDENTIAL_BOUNDARY_INVALID)
        if (
            not isinstance(
                self.synthetic_evidence_reference, SyntheticEvidenceReference
            )
            or self.synthetic_evidence_reference.profile_id != self.profile_id
            or self.synthetic_evidence_reference.profile_version
            != self.profile_version
        ):
            _raise(ManualValidationPlanErrorCategory.SYNTHETIC_EVIDENCE_INVALID)

        digest_value = hashlib.sha256(
            self.canonical_json().encode("utf-8")
        ).hexdigest()
        digest = f"{self.digest_algorithm}:{digest_value}"
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ManualValidationPlanSafeSummary(
                plan_id=self.plan_id,
                profile_id=self.profile_id,
                profile_version=str(self.profile_version),
                protocol_version=str(self.protocol_version),
                product_id=self.product_id,
                product_version=str(self.product_version),
                execution_window_start=_canonical_datetime(
                    self.execution_window_start
                ),
                execution_window_end=_canonical_datetime(self.execution_window_end),
                case_count=len(self.required_case_ids),
                role_separation_valid=True,
                boundary_category=self.endpoint_boundary.category.value,
                canonical_digest=digest,
            ),
        )

    @classmethod
    def from_mapping(cls, value: object) -> ManualValidationPlan:
        fields = {
            "plan_id",
            "profile_id",
            "profile_version",
            "protocol_version",
            "product_id",
            "product_version",
            "created_at",
            "execution_window_start",
            "execution_window_end",
            "profile_implementer_id",
            "validation_operator_id",
            "evidence_reviewer_id",
            "approver_id",
            "registry_administrator_id",
            "required_case_ids",
            "endpoint_boundary",
            "data_boundary",
            "credential_boundary",
            "abort_conditions",
            "cleanup_conditions",
            "synthetic_evidence_reference",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _raise(ManualValidationPlanErrorCategory.FIELD_SET_INVALID)
        return cls(
            plan_id=value["plan_id"],
            profile_id=value["profile_id"],
            profile_version=_parse_version(
                value["profile_version"],
                ManualValidationPlanErrorCategory.VERSION_INVALID,
            ),
            protocol_version=_parse_version(
                value["protocol_version"],
                ManualValidationPlanErrorCategory.VERSION_INVALID,
            ),
            product_id=value["product_id"],
            product_version=_parse_version(
                value["product_version"],
                ManualValidationPlanErrorCategory.VERSION_INVALID,
            ),
            created_at=_parse_datetime(value["created_at"]),
            execution_window_start=_parse_datetime(
                value["execution_window_start"]
            ),
            execution_window_end=_parse_datetime(value["execution_window_end"]),
            profile_implementer_id=value["profile_implementer_id"],
            validation_operator_id=value["validation_operator_id"],
            evidence_reviewer_id=value["evidence_reviewer_id"],
            approver_id=value["approver_id"],
            registry_administrator_id=value["registry_administrator_id"],
            required_case_ids=_tuple_input(value["required_case_ids"]),
            endpoint_boundary=EndpointBoundary.from_mapping(
                value["endpoint_boundary"]
            ),
            data_boundary=DataBoundary.from_mapping(value["data_boundary"]),
            credential_boundary=CredentialBoundary.from_mapping(
                value["credential_boundary"]
            ),
            abort_conditions=_tuple_input(value["abort_conditions"]),
            cleanup_conditions=_tuple_input(value["cleanup_conditions"]),
            synthetic_evidence_reference=SyntheticEvidenceReference.from_mapping(
                value["synthetic_evidence_reference"]
            ),
        )

    def canonical_json(self) -> str:
        payload = {
            "abort_conditions": [value.value for value in self.abort_conditions],
            "cleanup_conditions": [value.value for value in self.cleanup_conditions],
            "created_at": _canonical_datetime(self.created_at),
            "credential_boundary": {
                "credentials_prohibited": self.credential_boundary.credentials_prohibited
            },
            "data_boundary": {
                "no_customer_data": self.data_boundary.no_customer_data,
                "no_production_data": self.data_boundary.no_production_data,
                "no_raw_payload_retention": self.data_boundary.no_raw_payload_retention,
                "no_real_documents": self.data_boundary.no_real_documents,
                "safe_summary_only": self.data_boundary.safe_summary_only,
                "synthetic_only": self.data_boundary.synthetic_only,
            },
            "endpoint_boundary": {
                "approved_boundary_marker": self.endpoint_boundary.approved_boundary_marker,
                "category": self.endpoint_boundary.category.value,
                "opaque_endpoint_reference": self.endpoint_boundary.opaque_endpoint_reference,
            },
            "evidence_reviewer_id": self.evidence_reviewer_id,
            "execution_window_end": _canonical_datetime(self.execution_window_end),
            "execution_window_start": _canonical_datetime(
                self.execution_window_start
            ),
            "plan_id": self.plan_id,
            "profile_id": self.profile_id,
            "profile_implementer_id": self.profile_implementer_id,
            "profile_version": str(self.profile_version),
            "product_id": self.product_id,
            "product_version": str(self.product_version),
            "protocol_version": str(self.protocol_version),
            "registry_administrator_id": self.registry_administrator_id,
            "required_case_ids": [value.value for value in self.required_case_ids],
            "synthetic_evidence_reference": {
                "profile_id": self.synthetic_evidence_reference.profile_id,
                "profile_version": str(
                    self.synthetic_evidence_reference.profile_version
                ),
                "reference_id": self.synthetic_evidence_reference.reference_id,
            },
            "validation_operator_id": self.validation_operator_id,
            "approver_id": self.approver_id,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _validate_identity(self) -> None:
        if (
            not _safe_identifier(self.plan_id)
            or not _safe_identifier(self.profile_id)
            or not isinstance(self.product_id, str)
            or _PRODUCT_IDENTIFIER.fullmatch(self.product_id) is None
            or _contains_prohibited_term(self.product_id)
        ):
            _raise(ManualValidationPlanErrorCategory.IDENTITY_INVALID)
        if not all(
            isinstance(value, SemanticVersion)
            for value in (
                self.profile_version,
                self.protocol_version,
                self.product_version,
            )
        ):
            _raise(ManualValidationPlanErrorCategory.VERSION_INVALID)

    def _validate_roles(self) -> None:
        roles = (
            self.profile_implementer_id,
            self.validation_operator_id,
            self.evidence_reviewer_id,
            self.approver_id,
            self.registry_administrator_id,
        )
        if (
            not all(_safe_role_identifier(value) for value in roles)
            or self.evidence_reviewer_id == self.approver_id
            or self.validation_operator_id == self.evidence_reviewer_id
            or self.profile_implementer_id == self.approver_id
        ):
            _raise(ManualValidationPlanErrorCategory.ROLE_SEPARATION_INVALID)

    def _validate_execution_window(self) -> None:
        timestamps = (
            self.created_at,
            self.execution_window_start,
            self.execution_window_end,
        )
        if (
            not all(_is_aware_datetime(value) for value in timestamps)
            or self.created_at > self.execution_window_start
            or self.execution_window_start >= self.execution_window_end
            or self.execution_window_end - self.execution_window_start
            > MAX_EXECUTION_WINDOW
        ):
            _raise(ManualValidationPlanErrorCategory.EXECUTION_WINDOW_INVALID)

    def __repr__(self) -> str:
        digest = getattr(self, "canonical_digest", "<unavailable>")
        return (
            "ManualValidationPlan("
            f"plan_id={self.plan_id!r}, profile_id={self.profile_id!r}, "
            f"canonical_digest={digest!r})"
        )


def _raise(category: ManualValidationPlanErrorCategory) -> None:
    raise ManualValidationPlanError(category) from None


def _contains_prohibited_term(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in _PROHIBITED_IDENTIFIER_TERMS)


def _safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and _SAFE_IDENTIFIER.fullmatch(value) is not None
        and not _contains_prohibited_term(value)
    )


def _safe_role_identifier(value: object) -> bool:
    return _safe_identifier(value) and "@" not in value


def _safe_endpoint_component(value: object, pattern: re.Pattern[str]) -> bool:
    return (
        isinstance(value, str)
        and pattern.fullmatch(value) is not None
        and not _contains_prohibited_term(value)
    )


def _parse_version(
    value: object, category: ManualValidationPlanErrorCategory
) -> SemanticVersion:
    try:
        return SemanticVersion.parse(
            value, category=CompatibilityErrorCategory.INVALID_PROFILE
        )
    except Exception:
        _raise(category)


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        _raise(ManualValidationPlanErrorCategory.EXECUTION_WINDOW_INVALID)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _raise(ManualValidationPlanErrorCategory.EXECUTION_WINDOW_INVALID)
    if not _is_aware_datetime(parsed):
        _raise(ManualValidationPlanErrorCategory.EXECUTION_WINDOW_INVALID)
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


def _tuple_input(value: object) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        _raise(ManualValidationPlanErrorCategory.FIELD_SET_INVALID)
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError:
        _raise(ManualValidationPlanErrorCategory.FIELD_SET_INVALID)


def _canonical_enum_set(
    values: object,
    required: tuple[Enum, ...],
    enum_type: type[Enum],
    category: ManualValidationPlanErrorCategory,
) -> tuple:
    if not isinstance(values, tuple):
        _raise(category)
    parsed: list[Enum] = []
    for value in values:
        try:
            parsed.append(value if isinstance(value, enum_type) else enum_type(value))
        except (TypeError, ValueError):
            _raise(category)
    if len(parsed) != len(set(parsed)) or set(parsed) != set(required):
        _raise(category)
    return required


__all__ = [
    "AbortCondition",
    "CANONICAL_DIGEST_ALGORITHM",
    "CleanupCondition",
    "CredentialBoundary",
    "DataBoundary",
    "EndpointBoundary",
    "EndpointBoundaryCategory",
    "MAX_EXECUTION_WINDOW",
    "ManualValidationCase",
    "ManualValidationPlan",
    "ManualValidationPlanError",
    "ManualValidationPlanErrorCategory",
    "ManualValidationPlanSafeSummary",
    "REQUIRED_ABORT_CONDITIONS",
    "REQUIRED_CLEANUP_CONDITIONS",
    "REQUIRED_MANUAL_VALIDATION_CASES",
    "SyntheticEvidenceReference",
]
