from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    ScoreSemantics,
    SemanticVersion,
    SourceIdentifierPolicy,
    compatibility_error,
)
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalMetadata,
    ApprovalRestrictions,
    ProfileMaturity,
    SupportedProductVersionRange,
)
from ragguard.retrieval import RetrievalAdapterError
from ragguard.validation_report import (
    ValidationCheckResult,
    ValidationOverallStatus,
    ValidationReport,
    ValidationType,
    evaluate_approval_decision,
)


_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


class RegistryKind(str, Enum):
    TEST = "test"
    PRODUCTION = "production"


class RegistryStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class RegistryEventCategory(str, Enum):
    REGISTERED = "registered"
    SUSPENDED = "suspended"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"
    RESOLUTION_SUCCEEDED = "resolution_succeeded"
    RESOLUTION_REJECTED = "resolution_rejected"


_ALLOWED_TRANSITIONS = frozenset(
    {
        (RegistryStatus.ACTIVE, RegistryStatus.SUSPENDED),
        (RegistryStatus.ACTIVE, RegistryStatus.DEPRECATED),
        (RegistryStatus.ACTIVE, RegistryStatus.REVOKED),
        (RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED),
        (RegistryStatus.SUSPENDED, RegistryStatus.REVOKED),
        (RegistryStatus.DEPRECATED, RegistryStatus.REVOKED),
    }
)


@dataclass(frozen=True, repr=False)
class RegistryEntry:
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    maturity: ProfileMaturity
    approval_record_id: str
    validation_record_id: str
    approval_decision: ApprovalDecision
    supported_product_version_range: SupportedProductVersionRange
    approved_capabilities: tuple[str, ...]
    approved_score_semantics: ScoreSemantics
    approved_source_identifier_policy: SourceIdentifierPolicy
    restrictions: ApprovalRestrictions | None
    registered_at: datetime
    expires_at: datetime | None
    registry_status: RegistryStatus
    registry_kind: RegistryKind
    validation_type: ValidationType
    validation_expires_at: datetime | None
    approval_expires_at: datetime | None
    revalidation_required: bool

    def __post_init__(self) -> None:
        if (
            not _safe_identifier(self.profile_id)
            or not _safe_identifier(self.approval_record_id)
            or not _safe_identifier(self.validation_record_id)
            or not isinstance(self.profile_version, SemanticVersion)
            or not isinstance(self.protocol_version, SemanticVersion)
            or not isinstance(self.maturity, ProfileMaturity)
            or not isinstance(self.approval_decision, ApprovalDecision)
            or not isinstance(
                self.supported_product_version_range,
                SupportedProductVersionRange,
            )
            or not _canonical_capabilities(self.approved_capabilities)
            or not isinstance(self.approved_score_semantics, ScoreSemantics)
            or not isinstance(
                self.approved_source_identifier_policy,
                SourceIdentifierPolicy,
            )
            or (
                self.restrictions is not None
                and not isinstance(self.restrictions, ApprovalRestrictions)
            )
            or not isinstance(self.registry_status, RegistryStatus)
            or not isinstance(self.registry_kind, RegistryKind)
            or not isinstance(self.validation_type, ValidationType)
            or type(self.revalidation_required) is not bool
        ):
            _invalid()
        for value in (
            self.registered_at,
            self.expires_at,
            self.validation_expires_at,
            self.approval_expires_at,
        ):
            _validate_datetime(value, optional=value is None)
        expected_expiration = _earliest(
            self.validation_expires_at,
            self.approval_expires_at,
            (
                self.restrictions.expires_at
                if self.restrictions is not None
                else None
            ),
        )
        if self.expires_at != expected_expiration:
            _invalid()
        if self.approval_decision is ApprovalDecision.APPROVED_WITH_RESTRICTIONS:
            if self.restrictions is None or self.restrictions.is_empty:
                _invalid()
        elif self.restrictions is not None:
            _invalid()

    @classmethod
    def from_evidence(
        cls,
        *,
        profile_id: str,
        profile_version: SemanticVersion,
        maturity: ProfileMaturity,
        approval_metadata: ApprovalMetadata,
        validation_report: ValidationReport,
        registry_kind: RegistryKind,
        registered_at: datetime,
    ) -> RegistryEntry:
        if (
            not isinstance(approval_metadata, ApprovalMetadata)
            or not isinstance(validation_report, ValidationReport)
        ):
            _invalid()
        restriction_expiration = (
            approval_metadata.restrictions.expires_at
            if approval_metadata.restrictions is not None
            else None
        )
        expires_at = _earliest(
            validation_report.expires_at,
            approval_metadata.expires_at,
            restriction_expiration,
        )
        return cls(
            profile_id=profile_id,
            profile_version=profile_version,
            protocol_version=validation_report.protocol_version,
            maturity=maturity,
            approval_record_id=approval_metadata.approval_record_id,
            validation_record_id=validation_report.validation_record_id,
            approval_decision=approval_metadata.decision,
            supported_product_version_range=(
                approval_metadata.supported_product_version_range
            ),
            approved_capabilities=approval_metadata.approved_capabilities,
            approved_score_semantics=(
                approval_metadata.approved_score_semantics
            ),
            approved_source_identifier_policy=(
                approval_metadata.approved_source_identifier_policy
            ),
            restrictions=approval_metadata.restrictions,
            registered_at=registered_at,
            expires_at=expires_at,
            registry_status=RegistryStatus.ACTIVE,
            registry_kind=registry_kind,
            validation_type=validation_report.validation_type,
            validation_expires_at=validation_report.expires_at,
            approval_expires_at=approval_metadata.expires_at,
            revalidation_required=validation_report.revalidation_required,
        )

    @classmethod
    def from_mapping(cls, value: object) -> RegistryEntry:
        fields = {
            "profile_id",
            "profile_version",
            "protocol_version",
            "maturity",
            "approval_record_id",
            "validation_record_id",
            "approval_decision",
            "supported_product_version_range",
            "approved_capabilities",
            "approved_score_semantics",
            "approved_source_identifier_policy",
            "restrictions",
            "registered_at",
            "expires_at",
            "registry_status",
            "registry_kind",
            "validation_type",
            "validation_expires_at",
            "approval_expires_at",
            "revalidation_required",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _invalid()
        restrictions = value["restrictions"]
        try:
            return cls(
                profile_id=value["profile_id"],
                profile_version=_version(value["profile_version"]),
                protocol_version=_version(value["protocol_version"]),
                maturity=_enum(ProfileMaturity, value["maturity"]),
                approval_record_id=value["approval_record_id"],
                validation_record_id=value["validation_record_id"],
                approval_decision=_enum(
                    ApprovalDecision, value["approval_decision"]
                ),
                supported_product_version_range=(
                    SupportedProductVersionRange.from_mapping(
                        value["supported_product_version_range"]
                    )
                ),
                approved_capabilities=_tuple(value["approved_capabilities"]),
                approved_score_semantics=_enum(
                    ScoreSemantics, value["approved_score_semantics"]
                ),
                approved_source_identifier_policy=_enum(
                    SourceIdentifierPolicy,
                    value["approved_source_identifier_policy"],
                ),
                restrictions=(
                    None
                    if restrictions is None
                    else ApprovalRestrictions.from_mapping(restrictions)
                ),
                registered_at=_parse_datetime(value["registered_at"]),
                expires_at=_parse_datetime(value["expires_at"], optional=True),
                registry_status=_enum(RegistryStatus, value["registry_status"]),
                registry_kind=_enum(RegistryKind, value["registry_kind"]),
                validation_type=_enum(ValidationType, value["validation_type"]),
                validation_expires_at=_parse_datetime(
                    value["validation_expires_at"], optional=True
                ),
                approval_expires_at=_parse_datetime(
                    value["approval_expires_at"], optional=True
                ),
                revalidation_required=value["revalidation_required"],
            )
        except RetrievalAdapterError:
            _invalid()

    def __repr__(self) -> str:
        return "RegistryEntry(<safe>)"


@dataclass(frozen=True)
class RegistrySafeSummary:
    profile_id: str
    profile_version: str
    protocol_version: str
    registry_status: str
    approval_decision: str
    restriction_status: str
    supported_version_status: str
    expiration_status: str
    revalidation_required: bool

    def as_mapping(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "profile_id": self.profile_id,
                "profile_version": self.profile_version,
                "protocol_version": self.protocol_version,
                "registry_status": self.registry_status,
                "approval_decision": self.approval_decision,
                "restriction_status": self.restriction_status,
                "supported_version_status": self.supported_version_status,
                "expiration_status": self.expiration_status,
                "revalidation_required": self.revalidation_required,
            }
        )


@dataclass(frozen=True, repr=False)
class ResolvedRegistryEntry:
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    approval_decision: ApprovalDecision
    approved_capabilities: tuple[str, ...]
    approved_score_semantics: ScoreSemantics
    approved_source_identifier_policy: SourceIdentifierPolicy
    restrictions: ApprovalRestrictions | None

    def __repr__(self) -> str:
        return "ResolvedRegistryEntry(<safe>)"


@dataclass(frozen=True)
class RegistryEvent:
    category: RegistryEventCategory
    profile_id: str
    profile_version: str
    registry_status: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.category, RegistryEventCategory)
            or not _safe_identifier(self.profile_id)
            or not isinstance(self.profile_version, str)
            or not isinstance(self.registry_status, str)
        ):
            _invalid()


def validate_registration_eligibility(
    entry: RegistryEntry,
    *,
    approval_metadata: ApprovalMetadata,
    validation_report: ValidationReport,
    evaluation_time: datetime,
) -> None:
    if (
        not isinstance(entry, RegistryEntry)
        or not isinstance(approval_metadata, ApprovalMetadata)
        or not isinstance(validation_report, ValidationReport)
    ):
        _invalid()
    _validate_datetime(evaluation_time)
    if (
        entry.registry_status is not RegistryStatus.ACTIVE
        or entry.profile_id != validation_report.profile_id
        or entry.profile_version != validation_report.profile_version
        or entry.protocol_version != validation_report.protocol_version
        or entry.validation_record_id != validation_report.validation_record_id
        or entry.validation_record_id != approval_metadata.validation_record_id
        or entry.approval_record_id != approval_metadata.approval_record_id
        or entry.approval_decision is not approval_metadata.decision
        or entry.supported_product_version_range
        != approval_metadata.supported_product_version_range
        or entry.approved_capabilities != approval_metadata.approved_capabilities
        or entry.approved_score_semantics
        is not approval_metadata.approved_score_semantics
        or entry.approved_source_identifier_policy
        is not approval_metadata.approved_source_identifier_policy
        or entry.restrictions != approval_metadata.restrictions
        or entry.validation_type is not validation_report.validation_type
        or entry.validation_expires_at != validation_report.expires_at
        or entry.approval_expires_at != approval_metadata.expires_at
        or entry.revalidation_required != validation_report.revalidation_required
    ):
        _invalid()
    if entry.maturity is not ProfileMaturity.APPROVED:
        raise compatibility_error(CompatibilityErrorCategory.PROFILE_UNAPPROVED)
    if entry.approval_decision not in {
        ApprovalDecision.APPROVED,
        ApprovalDecision.APPROVED_WITH_RESTRICTIONS,
    }:
        raise compatibility_error(CompatibilityErrorCategory.PROFILE_UNAPPROVED)
    if entry.registry_kind is RegistryKind.PRODUCTION:
        if validation_report.validation_type is not ValidationType.MANUAL:
            raise compatibility_error(
                CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
            )
    if validation_report.revalidation_required:
        raise compatibility_error(CompatibilityErrorCategory.REVALIDATION_REQUIRED)
    if validation_report.overall_status is not ValidationOverallStatus.PASSED:
        raise compatibility_error(CompatibilityErrorCategory.PROFILE_UNAPPROVED)
    if (
        validation_report.expires_at is not None
        and evaluation_time >= validation_report.expires_at
    ):
        raise compatibility_error(
            CompatibilityErrorCategory.PROFILE_VALIDATION_EXPIRED
        )
    if approval_metadata.is_expired(evaluation_time):
        raise compatibility_error(CompatibilityErrorCategory.APPROVAL_EXPIRED)
    required_checks = (
        validation_report.required_capabilities_result,
        validation_report.score_semantics_result,
        validation_report.source_policy_result,
        validation_report.transport_boundary_result,
        validation_report.non_disclosure_result,
    )
    if any(result is not ValidationCheckResult.PASSED for result in required_checks):
        raise compatibility_error(CompatibilityErrorCategory.PROFILE_UNAPPROVED)
    decision = entry.approval_decision
    if entry.registry_kind is RegistryKind.PRODUCTION:
        decision = evaluate_approval_decision(
            profile_id=entry.profile_id,
            profile_version=entry.profile_version,
            maturity=entry.maturity,
            validation_report=validation_report,
            approval_metadata=approval_metadata,
            product_version=str(validation_report.normalized_product_version),
            evaluation_time=evaluation_time,
        )
    if decision is ApprovalDecision.NEEDS_REVALIDATION:
        raise compatibility_error(CompatibilityErrorCategory.REVALIDATION_REQUIRED)
    if decision not in {
        ApprovalDecision.APPROVED,
        ApprovalDecision.APPROVED_WITH_RESTRICTIONS,
    }:
        raise compatibility_error(CompatibilityErrorCategory.PROFILE_UNAPPROVED)
    if decision is not entry.approval_decision:
        _invalid()


class TrustedProductionRegistry:
    def __init__(self, *, kind: RegistryKind):
        if not isinstance(kind, RegistryKind):
            raise compatibility_error(
                CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
            )
        self._kind = kind
        self._entries: dict[tuple[str, SemanticVersion], RegistryEntry] = {}
        self._events: tuple[RegistryEvent, ...] = ()

    @property
    def kind(self) -> RegistryKind:
        return self._kind

    @property
    def events(self) -> tuple[RegistryEvent, ...]:
        return self._events

    @property
    def snapshot(
        self,
    ) -> Mapping[tuple[str, SemanticVersion], RegistryEntry]:
        return MappingProxyType(dict(self._entries))

    def register(
        self,
        entry: RegistryEntry,
        *,
        approval_metadata: ApprovalMetadata,
        validation_report: ValidationReport,
        evaluation_time: datetime,
    ) -> RegistryEvent:
        if not isinstance(entry, RegistryEntry):
            _invalid()
        if entry.registry_kind is not self._kind:
            raise compatibility_error(
                CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
            )
        key = (entry.profile_id, entry.profile_version)
        if key in self._entries:
            _invalid()
        validate_registration_eligibility(
            entry,
            approval_metadata=approval_metadata,
            validation_report=validation_report,
            evaluation_time=evaluation_time,
        )
        self._entries = {**self._entries, key: entry}
        return self._record(RegistryEventCategory.REGISTERED, entry)

    def contains(self, profile_id: str, profile_version: object) -> bool:
        key = self._key(profile_id, profile_version)
        return key in self._entries

    def resolve(
        self,
        *,
        profile_id: str,
        profile_version: object,
        normalized_product_version: object,
        evaluation_time: datetime,
    ) -> ResolvedRegistryEntry:
        _validate_datetime(evaluation_time)
        try:
            key = self._key(profile_id, profile_version)
            entry = self._entries.get(key)
            if entry is None:
                category = (
                    CompatibilityErrorCategory.PROFILE_VERSION_NOT_REGISTERED
                    if any(
                        registered_id == profile_id
                        for registered_id, _ in self._entries
                    )
                    else CompatibilityErrorCategory.PROFILE_NOT_REGISTERED
                )
                raise compatibility_error(category)
            if self._kind is not RegistryKind.PRODUCTION:
                raise compatibility_error(
                    CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
                )
            self._require_resolvable(
                entry,
                normalized_product_version=normalized_product_version,
                evaluation_time=evaluation_time,
            )
        except RetrievalAdapterError:
            self._record_rejection(profile_id, profile_version)
            raise
        resolved = ResolvedRegistryEntry(
            profile_id=entry.profile_id,
            profile_version=entry.profile_version,
            protocol_version=entry.protocol_version,
            approval_decision=entry.approval_decision,
            approved_capabilities=entry.approved_capabilities,
            approved_score_semantics=entry.approved_score_semantics,
            approved_source_identifier_policy=(
                entry.approved_source_identifier_policy
            ),
            restrictions=entry.restrictions,
        )
        self._record(RegistryEventCategory.RESOLUTION_SUCCEEDED, entry)
        return resolved

    def list_safe_summaries(
        self,
        *,
        evaluation_time: datetime,
        normalized_product_version: object | None = None,
    ) -> tuple[RegistrySafeSummary, ...]:
        _validate_datetime(evaluation_time)
        return tuple(
            _summary(
                entry,
                evaluation_time=evaluation_time,
                normalized_product_version=normalized_product_version,
            )
            for _, entry in sorted(
                self._entries.items(),
                key=lambda item: (item[0][0], item[0][1]),
            )
        )

    def suspend(
        self, profile_id: str, profile_version: object
    ) -> RegistryEvent:
        return self._transition(
            profile_id,
            profile_version,
            RegistryStatus.SUSPENDED,
            RegistryEventCategory.SUSPENDED,
        )

    def deprecate(
        self, profile_id: str, profile_version: object
    ) -> RegistryEvent:
        return self._transition(
            profile_id,
            profile_version,
            RegistryStatus.DEPRECATED,
            RegistryEventCategory.DEPRECATED,
        )

    def revoke(self, profile_id: str, profile_version: object) -> RegistryEvent:
        return self._transition(
            profile_id,
            profile_version,
            RegistryStatus.REVOKED,
            RegistryEventCategory.REVOKED,
        )

    def _key(
        self, profile_id: str, profile_version: object
    ) -> tuple[str, SemanticVersion]:
        if not _safe_identifier(profile_id):
            _invalid()
        version = (
            profile_version
            if isinstance(profile_version, SemanticVersion)
            else SemanticVersion.parse(
                profile_version,
                category=CompatibilityErrorCategory.REGISTRY_METADATA_INVALID,
            )
        )
        return profile_id, version

    def _transition(
        self,
        profile_id: str,
        profile_version: object,
        target: RegistryStatus,
        event: RegistryEventCategory,
    ) -> RegistryEvent:
        key = self._key(profile_id, profile_version)
        entry = self._entries.get(key)
        if entry is None:
            raise compatibility_error(
                CompatibilityErrorCategory.PROFILE_NOT_REGISTERED
            )
        if (entry.registry_status, target) not in _ALLOWED_TRANSITIONS:
            _invalid()
        updated = replace(entry, registry_status=target)
        self._entries = {**self._entries, key: updated}
        return self._record(event, updated)

    def _require_resolvable(
        self,
        entry: RegistryEntry,
        *,
        normalized_product_version: object,
        evaluation_time: datetime,
    ) -> None:
        status_errors = {
            RegistryStatus.SUSPENDED: CompatibilityErrorCategory.PROFILE_SUSPENDED,
            RegistryStatus.DEPRECATED: CompatibilityErrorCategory.PROFILE_DEPRECATED,
            RegistryStatus.REVOKED: CompatibilityErrorCategory.PROFILE_REVOKED,
        }
        if entry.registry_status is not RegistryStatus.ACTIVE:
            raise compatibility_error(status_errors[entry.registry_status])
        if entry.maturity is not ProfileMaturity.APPROVED:
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_UNAPPROVED)
        if entry.revalidation_required:
            raise compatibility_error(
                CompatibilityErrorCategory.REVALIDATION_REQUIRED
            )
        if (
            entry.validation_expires_at is not None
            and evaluation_time >= entry.validation_expires_at
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.PROFILE_VALIDATION_EXPIRED
            )
        approval_expiration = _earliest(
            entry.approval_expires_at,
            (
                entry.restrictions.expires_at
                if entry.restrictions is not None
                else None
            ),
        )
        if (
            approval_expiration is not None
            and evaluation_time >= approval_expiration
        ):
            raise compatibility_error(CompatibilityErrorCategory.APPROVAL_EXPIRED)
        try:
            supported = entry.supported_product_version_range.contains(
                normalized_product_version
            )
        except RetrievalAdapterError:
            supported = False
        if not supported:
            raise compatibility_error(
                CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED
            )
        product = SemanticVersion.parse(
            normalized_product_version,
            category=CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED,
        )
        if (
            entry.restrictions is not None
            and entry.restrictions.supported_minor_versions
            and f"{product.major}.{product.minor}"
            not in entry.restrictions.supported_minor_versions
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED
            )

    def _record(
        self, category: RegistryEventCategory, entry: RegistryEntry
    ) -> RegistryEvent:
        event = RegistryEvent(
            category=category,
            profile_id=entry.profile_id,
            profile_version=str(entry.profile_version),
            registry_status=entry.registry_status.value,
        )
        self._events = (*self._events, event)
        return event

    def _record_rejection(
        self, profile_id: object, profile_version: object
    ) -> None:
        safe_profile = profile_id if _safe_identifier(profile_id) else "invalid"
        try:
            safe_version = str(
                profile_version
                if isinstance(profile_version, SemanticVersion)
                else SemanticVersion.parse(
                    profile_version,
                    category=(
                        CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
                    ),
                )
            )
        except RetrievalAdapterError:
            safe_version = "invalid"
        event = RegistryEvent(
            category=RegistryEventCategory.RESOLUTION_REJECTED,
            profile_id=safe_profile,
            profile_version=safe_version,
            registry_status="unavailable",
        )
        self._events = (*self._events, event)

    def __repr__(self) -> str:
        return "TrustedProductionRegistry(<safe>)"


def _summary(
    entry: RegistryEntry,
    *,
    evaluation_time: datetime,
    normalized_product_version: object | None,
) -> RegistrySafeSummary:
    supported = "unknown"
    if normalized_product_version is not None:
        try:
            supported = (
                "supported"
                if entry.supported_product_version_range.contains(
                    normalized_product_version
                )
                else "unsupported"
            )
        except RetrievalAdapterError:
            supported = "unsupported"
    expired = entry.expires_at is not None and evaluation_time >= entry.expires_at
    return RegistrySafeSummary(
        profile_id=entry.profile_id,
        profile_version=str(entry.profile_version),
        protocol_version=str(entry.protocol_version),
        registry_status=entry.registry_status.value,
        approval_decision=entry.approval_decision.value,
        restriction_status=(
            "restricted" if entry.restrictions is not None else "none"
        ),
        supported_version_status=supported,
        expiration_status="expired" if expired else "active",
        revalidation_required=entry.revalidation_required,
    )


def _safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) is not None


def _canonical_capabilities(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and all(_safe_identifier(item) for item in value)
        and tuple(sorted(set(value))) == value
    )


def _earliest(*values: datetime | None) -> datetime | None:
    present = tuple(value for value in values if value is not None)
    return min(present) if present else None


def _validate_datetime(value: object, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        _invalid()


def _parse_datetime(value: object, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        _invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _invalid()
    _validate_datetime(parsed)
    return parsed


def _version(value: object) -> SemanticVersion:
    return SemanticVersion.parse(
        value,
        category=CompatibilityErrorCategory.REGISTRY_METADATA_INVALID,
    )


def _tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        value = tuple(value)
    if not isinstance(value, tuple):
        _invalid()
    return value


def _enum(enum_type: type[Enum], value: object):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        _invalid()


def _invalid() -> None:
    raise compatibility_error(CompatibilityErrorCategory.REGISTRY_METADATA_INVALID)
