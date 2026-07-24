from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from ragguard.retrieval import (
    LOCAL_RESPONSE_METADATA_KEYS,
    MAX_LOCAL_IDENTIFIER_LENGTH,
    MAX_LOCAL_KEYWORD_LENGTH,
    MAX_LOCAL_KEYWORDS,
    MAX_LOCAL_METADATA_VALUE_LENGTH,
    MAX_LOCAL_QUERY_LENGTH,
    MAX_LOCAL_TITLE_LENGTH,
    MAX_LOCAL_TOP_K,
    RankedResult,
    RetrievalAdapterError,
    validate_ranked_results,
)


MAX_PROFILE_IDENTIFIER_LENGTH = 64
MAX_PROFILE_PATH_LENGTH = 128
MAX_VERSION_COMPONENT = 9999
MAX_MAPPED_REQUEST_SIZE = 65_536

_PROFILE_FIELDS = frozenset(
    {
        "profile_id",
        "profile_version",
        "protocol_version",
        "health_path",
        "capabilities_path",
        "retrieve_path",
        "request_field_mapping",
        "response_field_mapping",
        "score_semantics",
        "source_identifier_policy",
        "optional_feature_flags",
    }
)
_REQUEST_FIELDS = frozenset(
    {"query", "top_k", "query_id", "protocol_version", "requested_capabilities"}
)
_REQUIRED_REQUEST_FIELDS = frozenset({"query", "top_k"})
_RESPONSE_FIELDS = frozenset(
    {
        "rank",
        "document_id",
        "score",
        "title",
        "source_id",
        "matched_keywords",
        "adapter_metadata",
        "query_id",
    }
)
_REQUIRED_RESPONSE_FIELDS = frozenset({"rank", "document_id", "source_id"})
_FEATURE_FIELDS = frozenset({"keyword_metadata", "title", "query_id_echo"})
_HEALTH_FIELDS = frozenset({"status", "protocol_version", "service_available"})
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
_CAPABILITY_FIELDS = _REQUIRED_CAPABILITIES | _OPTIONAL_CAPABILITIES
_SAFE_PROFILE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SAFE_FIELD_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_SAFE_RELATIVE_HTTP_PATH = re.compile(r"/[A-Za-z0-9_/-]{1,127}\Z")
_SEMANTIC_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_SAFE_SOURCE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_SELECTION_FIELDS = frozenset(
    {"profile_id", "profile_version", "protocol_version", "requested_optional_capabilities"}
)


class CompatibilityErrorCategory(str, Enum):
    PROFILE_NOT_CONFIGURED = "profile_not_configured"
    UNKNOWN_PROFILE = "unknown_profile"
    UNSUPPORTED_PROFILE_VERSION = "unsupported_profile_version"
    PROTOCOL_VERSION_MISMATCH = "protocol_version_mismatch"
    INVALID_PROFILE = "invalid_profile"
    INVALID_PROFILE_PATH = "invalid_profile_path"
    INVALID_FIELD_MAPPING = "invalid_field_mapping"
    UNSUPPORTED_SCORE_SEMANTICS = "unsupported_score_semantics"
    UNSAFE_SOURCE_IDENTIFIER_POLICY = "unsafe_source_identifier_policy"
    HEALTH_UNAVAILABLE = "health_unavailable"
    HEALTH_INVALID = "health_invalid"
    CAPABILITY_MISMATCH = "capability_mismatch"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    INVALID_CAPABILITIES_RESPONSE = "invalid_capabilities_response"
    REQUEST_MAPPING_ERROR = "request_mapping_error"
    RESPONSE_MAPPING_ERROR = "response_mapping_error"
    PRODUCT_RESPONSE_INVALID = "product_response_invalid"
    UNSAFE_SOURCE_IDENTIFIER = "unsafe_source_identifier"
    INVALID_MAPPED_REQUEST = "invalid_mapped_request"
    INVALID_MAPPED_RESPONSE = "invalid_mapped_response"
    PROFILE_UNAPPROVED = "profile_unapproved"
    PROFILE_REVOKED = "profile_revoked"
    PROFILE_VALIDATION_EXPIRED = "profile_validation_expired"
    PRODUCT_VERSION_UNSUPPORTED = "product_version_unsupported"
    MANUAL_VALIDATION_REQUIRED = "manual_validation_required"
    APPROVAL_METADATA_INVALID = "approval_metadata_invalid"
    REVALIDATION_REQUIRED = "revalidation_required"


class ScoreSemantics(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    UNSCORED = "unscored"


class SourceIdentifierPolicy(str, Enum):
    OPAQUE_SAFE_ID = "opaque_safe_id"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"


class ProtocolStatus(str, Enum):
    EXACT = "exact"
    COMPATIBLE_PATCH = "compatible_patch"
    COMPATIBLE_MINOR = "compatible_minor"


def compatibility_error(category: CompatibilityErrorCategory) -> RetrievalAdapterError:
    """Create a bounded error that contains only its allowlisted category."""
    return RetrievalAdapterError(category.value)


@dataclass(frozen=True, order=True)
class SemanticVersion:
    """Strict three-component version; prerelease and build forms are unsupported."""

    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        for value in (self.major, self.minor, self.patch):
            if type(value) is not int or value < 0 or value > MAX_VERSION_COMPONENT:
                raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)

    @classmethod
    def parse(
        cls,
        value: object,
        *,
        category: CompatibilityErrorCategory = CompatibilityErrorCategory.INVALID_PROFILE,
    ) -> SemanticVersion:
        if not isinstance(value, str):
            raise compatibility_error(category)
        match = _SEMANTIC_VERSION.fullmatch(value)
        if match is None:
            raise compatibility_error(category)
        components = tuple(int(component) for component in match.groups())
        if any(component > MAX_VERSION_COMPONENT for component in components):
            raise compatibility_error(category)
        return cls(*components)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, repr=False)
class CompatibilityProfileSelection:
    """Bounded config selection; profile schemas remain in the trusted registry."""

    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    requested_optional_capabilities: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: object) -> CompatibilityProfileSelection:
        required = {"profile_id", "profile_version", "protocol_version"}
        if (
            not isinstance(value, Mapping)
            or not required.issubset(value)
            or not set(value).issubset(_SELECTION_FIELDS)
        ):
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_NOT_CONFIGURED)
        requested = value.get("requested_optional_capabilities", ())
        if isinstance(requested, list):
            requested = tuple(requested)
        if (
            not isinstance(value["profile_id"], str)
            or _SAFE_PROFILE_IDENTIFIER.fullmatch(value["profile_id"]) is None
            or not isinstance(requested, tuple)
            or any(name not in _OPTIONAL_CAPABILITIES for name in requested)
            or tuple(sorted(set(requested))) != requested
        ):
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_NOT_CONFIGURED)
        return cls(
            profile_id=value["profile_id"],
            profile_version=SemanticVersion.parse(
                value["profile_version"],
                category=CompatibilityErrorCategory.UNSUPPORTED_PROFILE_VERSION,
            ),
            protocol_version=SemanticVersion.parse(
                value["protocol_version"],
                category=CompatibilityErrorCategory.PROTOCOL_VERSION_MISMATCH,
            ),
            requested_optional_capabilities=requested,
        )

    def __repr__(self) -> str:
        return (
            "CompatibilityProfileSelection("
            f"profile_id={self.profile_id!r}, "
            f"requested_capability_count={len(self.requested_optional_capabilities)})"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class FieldMappingEntry:
    standard_field: str
    product_field: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.standard_field, str)
            or not isinstance(self.product_field, str)
            or _SAFE_FIELD_IDENTIFIER.fullmatch(self.standard_field) is None
            or _SAFE_FIELD_IDENTIFIER.fullmatch(self.product_field) is None
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_FIELD_MAPPING)


@dataclass(frozen=True)
class FieldMapping:
    """Typed, immutable mapping entries; expressions and nested paths are forbidden."""

    entries: tuple[FieldMappingEntry, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or not all(
            isinstance(entry, FieldMappingEntry) for entry in self.entries
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_FIELD_MAPPING)
        standard_fields = [entry.standard_field for entry in self.entries]
        product_fields = [entry.product_field for entry in self.entries]
        if (
            len(set(standard_fields)) != len(standard_fields)
            or len(set(product_fields)) != len(product_fields)
            or standard_fields != sorted(standard_fields)
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_FIELD_MAPPING)

    @classmethod
    def parse(
        cls,
        value: object,
        *,
        allowed_fields: frozenset[str],
        required_fields: frozenset[str],
    ) -> FieldMapping:
        if not isinstance(value, Mapping):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_FIELD_MAPPING)
        raw_entries = list(value.items())
        standard_fields = {key for key, _ in raw_entries if isinstance(key, str)}
        if (
            len(standard_fields) != len(raw_entries)
            or not required_fields.issubset(standard_fields)
            or not standard_fields.issubset(allowed_fields)
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_FIELD_MAPPING)

        entries: list[FieldMappingEntry] = []
        targets: set[str] = set()
        for standard_field, product_field in raw_entries:
            if (
                not isinstance(product_field, str)
                or _SAFE_FIELD_IDENTIFIER.fullmatch(product_field) is None
                or product_field in targets
            ):
                raise compatibility_error(CompatibilityErrorCategory.INVALID_FIELD_MAPPING)
            targets.add(product_field)
            entries.append(FieldMappingEntry(standard_field, product_field))
        entries.sort(key=lambda entry: entry.standard_field)
        return cls(tuple(entries))

    def product_field_for(self, standard_field: str) -> str:
        for entry in self.entries:
            if entry.standard_field == standard_field:
                return entry.product_field
        raise compatibility_error(CompatibilityErrorCategory.INVALID_FIELD_MAPPING)


@dataclass(frozen=True)
class OptionalFeatureFlags:
    keyword_metadata: bool = False
    title: bool = False
    query_id_echo: bool = False

    def __post_init__(self) -> None:
        if not all(
            type(flag) is bool
            for flag in (self.keyword_metadata, self.title, self.query_id_echo)
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)

    @classmethod
    def parse(cls, value: object) -> OptionalFeatureFlags:
        if not isinstance(value, Mapping) or not set(value).issubset(_FEATURE_FIELDS):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)
        if not all(type(flag) is bool for flag in value.values()):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)
        return cls(**dict(value))


@dataclass(frozen=True, repr=False)
class CompatibilityProfile:
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    health_path: str = field(repr=False)
    capabilities_path: str = field(repr=False)
    retrieve_path: str = field(repr=False)
    request_field_mapping: FieldMapping = field(repr=False)
    response_field_mapping: FieldMapping = field(repr=False)
    score_semantics: ScoreSemantics
    source_identifier_policy: SourceIdentifierPolicy
    optional_feature_flags: OptionalFeatureFlags = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or len(self.profile_id) > MAX_PROFILE_IDENTIFIER_LENGTH
            or _SAFE_PROFILE_IDENTIFIER.fullmatch(self.profile_id) is None
            or not isinstance(self.profile_version, SemanticVersion)
            or not isinstance(self.protocol_version, SemanticVersion)
            or not isinstance(self.request_field_mapping, FieldMapping)
            or not isinstance(self.response_field_mapping, FieldMapping)
            or not isinstance(self.score_semantics, ScoreSemantics)
            or not isinstance(self.source_identifier_policy, SourceIdentifierPolicy)
            or not isinstance(self.optional_feature_flags, OptionalFeatureFlags)
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)
        _validate_profile_path(self.health_path)
        _validate_profile_path(self.capabilities_path)
        _validate_profile_path(self.retrieve_path)

    @classmethod
    def from_mapping(cls, value: object) -> CompatibilityProfile:
        if not isinstance(value, Mapping):
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_NOT_CONFIGURED)
        if set(value) != _PROFILE_FIELDS:
            raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)

        profile_id = value["profile_id"]
        if (
            not isinstance(profile_id, str)
            or len(profile_id) > MAX_PROFILE_IDENTIFIER_LENGTH
            or _SAFE_PROFILE_IDENTIFIER.fullmatch(profile_id) is None
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)

        try:
            score_semantics = ScoreSemantics(value["score_semantics"])
        except (TypeError, ValueError) as exc:
            raise compatibility_error(
                CompatibilityErrorCategory.UNSUPPORTED_SCORE_SEMANTICS
            ) from exc
        try:
            source_policy = SourceIdentifierPolicy(value["source_identifier_policy"])
        except (TypeError, ValueError) as exc:
            raise compatibility_error(
                CompatibilityErrorCategory.UNSAFE_SOURCE_IDENTIFIER_POLICY
            ) from exc

        return cls(
            profile_id=profile_id,
            profile_version=SemanticVersion.parse(value["profile_version"]),
            protocol_version=SemanticVersion.parse(value["protocol_version"]),
            health_path=_validate_profile_path(value["health_path"]),
            capabilities_path=_validate_profile_path(value["capabilities_path"]),
            retrieve_path=_validate_profile_path(value["retrieve_path"]),
            request_field_mapping=FieldMapping.parse(
                value["request_field_mapping"],
                allowed_fields=_REQUEST_FIELDS,
                required_fields=_REQUIRED_REQUEST_FIELDS,
            ),
            response_field_mapping=FieldMapping.parse(
                value["response_field_mapping"],
                allowed_fields=_RESPONSE_FIELDS,
                required_fields=_REQUIRED_RESPONSE_FIELDS,
            ),
            score_semantics=score_semantics,
            source_identifier_policy=source_policy,
            optional_feature_flags=OptionalFeatureFlags.parse(
                value["optional_feature_flags"]
            ),
        )

    def __repr__(self) -> str:
        return (
            "CompatibilityProfile("
            f"profile_id={self.profile_id!r}, "
            f"profile_version={str(self.profile_version)!r}, "
            f"protocol_version={str(self.protocol_version)!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class SupportedCompatibilityProfile:
    profile: CompatibilityProfile
    allowed_profile_minor_versions: tuple[int, ...] = ()
    allowed_protocol_minor_versions: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.profile, CompatibilityProfile):
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_NOT_CONFIGURED)
        _validate_minor_allowlist(self.allowed_profile_minor_versions)
        _validate_minor_allowlist(self.allowed_protocol_minor_versions)


@dataclass(frozen=True)
class CompatibilityProfileRegistry:
    """Exact profile selection with explicit minor-version compatibility only."""

    profiles: tuple[SupportedCompatibilityProfile, ...]

    def __post_init__(self) -> None:
        if not self.profiles:
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_NOT_CONFIGURED)
        identifiers = [entry.profile.profile_id for entry in self.profiles]
        if len(set(identifiers)) != len(identifiers):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)

    def resolve(
        self,
        profile_id: object,
        profile_version: object,
        protocol_version: object,
    ) -> CompatibilityProfile:
        if not isinstance(profile_id, str):
            raise compatibility_error(CompatibilityErrorCategory.UNKNOWN_PROFILE)
        selected = next(
            (entry for entry in self.profiles if entry.profile.profile_id == profile_id),
            None,
        )
        if selected is None:
            raise compatibility_error(CompatibilityErrorCategory.UNKNOWN_PROFILE)

        requested_profile = SemanticVersion.parse(
            profile_version,
            category=CompatibilityErrorCategory.UNSUPPORTED_PROFILE_VERSION,
        )
        requested_protocol = SemanticVersion.parse(
            protocol_version,
            category=CompatibilityErrorCategory.PROTOCOL_VERSION_MISMATCH,
        )
        _validate_requested_version(
            requested_profile,
            selected.profile.profile_version,
            selected.allowed_profile_minor_versions,
            CompatibilityErrorCategory.UNSUPPORTED_PROFILE_VERSION,
        )
        _validate_requested_version(
            requested_protocol,
            selected.profile.protocol_version,
            selected.allowed_protocol_minor_versions,
            CompatibilityErrorCategory.PROTOCOL_VERSION_MISMATCH,
        )
        return selected.profile

    def supported(self, profile_id: str) -> SupportedCompatibilityProfile:
        selected = next(
            (entry for entry in self.profiles if entry.profile.profile_id == profile_id),
            None,
        )
        if selected is None:
            raise compatibility_error(CompatibilityErrorCategory.UNKNOWN_PROFILE)
        return selected


def synthetic_compatibility_registry() -> CompatibilityProfileRegistry:
    """Return the product-neutral registry used only by synthetic compatibility E2E."""
    profile = CompatibilityProfile.from_mapping(
        {
            "profile_id": "synthetic_loopback_v1",
            "profile_version": "1.0.0",
            "protocol_version": "1.0.0",
            "health_path": "/health",
            "capabilities_path": "/capabilities",
            "retrieve_path": "/retrieve",
            "request_field_mapping": {
                "query": "query_text",
                "top_k": "result_limit",
                "query_id": "request_id",
                "protocol_version": "protocol_version",
                "requested_capabilities": "requested_capabilities",
            },
            "response_field_mapping": {
                "rank": "position",
                "document_id": "item_id",
                "score": "relevance",
                "title": "display_title",
                "source_id": "safe_source",
                "matched_keywords": "matches",
                "query_id": "echo_request_id",
            },
            "score_semantics": "higher_is_better",
            "source_identifier_policy": "opaque_safe_id",
            "optional_feature_flags": {
                "keyword_metadata": True,
                "title": True,
                "query_id_echo": True,
            },
        }
    )
    return CompatibilityProfileRegistry((SupportedCompatibilityProfile(profile),))


@dataclass(frozen=True, repr=False)
class HealthResponse:
    """Validated product-neutral health data without retaining its raw response."""

    status: HealthStatus
    protocol_version: SemanticVersion
    service_available: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, HealthStatus)
            or not isinstance(self.protocol_version, SemanticVersion)
            or type(self.service_available) is not bool
        ):
            raise compatibility_error(CompatibilityErrorCategory.HEALTH_INVALID)

    @classmethod
    def from_mapping(cls, value: object) -> HealthResponse:
        if not isinstance(value, Mapping) or set(value) != _HEALTH_FIELDS:
            raise compatibility_error(CompatibilityErrorCategory.HEALTH_INVALID)
        try:
            status = HealthStatus(value["status"])
            protocol_version = SemanticVersion.parse(
                value["protocol_version"],
                category=CompatibilityErrorCategory.HEALTH_INVALID,
            )
        except (TypeError, ValueError):
            raise compatibility_error(
                CompatibilityErrorCategory.HEALTH_INVALID
            ) from None
        if type(value["service_available"]) is not bool:
            raise compatibility_error(CompatibilityErrorCategory.HEALTH_INVALID)
        return cls(status, protocol_version, value["service_available"])

    def __repr__(self) -> str:
        return (
            "HealthResponse("
            f"status={self.status.value!r}, "
            f"service_available={self.service_available!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class CapabilitiesResponse:
    """Typed capability flags; unknown and raw metadata are never retained."""

    retrieval: bool
    bounded_top_k: bool
    deterministic_result_schema: bool
    safe_source_identifier: bool
    response_size_compliance: bool
    score: bool = False
    title: bool = False
    matched_keywords: bool = False
    query_id_echo: bool = False
    protocol_version_echo: bool = False

    def __post_init__(self) -> None:
        if not all(type(value) is bool for value in self._values()):
            raise compatibility_error(
                CompatibilityErrorCategory.INVALID_CAPABILITIES_RESPONSE
            )

    @classmethod
    def from_mapping(cls, value: object) -> CapabilitiesResponse:
        if not isinstance(value, Mapping):
            raise compatibility_error(
                CompatibilityErrorCategory.INVALID_CAPABILITIES_RESPONSE
            )
        fields = set(value)
        if (
            not _REQUIRED_CAPABILITIES.issubset(fields)
            or not fields.issubset(_CAPABILITY_FIELDS)
            or not all(type(flag) is bool for flag in value.values())
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.INVALID_CAPABILITIES_RESPONSE
            )
        return cls(**dict(value))

    def enabled(self, capability: str) -> bool:
        if capability not in _CAPABILITY_FIELDS:
            raise compatibility_error(CompatibilityErrorCategory.UNSUPPORTED_CAPABILITY)
        return bool(getattr(self, capability))

    def _values(self) -> tuple[bool, ...]:
        return (
            self.retrieval,
            self.bounded_top_k,
            self.deterministic_result_schema,
            self.safe_source_identifier,
            self.response_size_compliance,
            self.score,
            self.title,
            self.matched_keywords,
            self.query_id_echo,
            self.protocol_version_echo,
        )


@dataclass(frozen=True, repr=False)
class CompatibilityResult:
    """Safe negotiation summary containing no endpoint, path, or raw response."""

    profile_id: str
    protocol_status: ProtocolStatus
    health_status: HealthStatus
    required_capabilities_satisfied: bool
    enabled_optional_capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or _SAFE_PROFILE_IDENTIFIER.fullmatch(self.profile_id) is None
            or not isinstance(self.protocol_status, ProtocolStatus)
            or not isinstance(self.health_status, HealthStatus)
            or type(self.required_capabilities_satisfied) is not bool
            or not isinstance(self.enabled_optional_capabilities, tuple)
            or any(
                capability not in _OPTIONAL_CAPABILITIES
                for capability in self.enabled_optional_capabilities
            )
            or tuple(sorted(set(self.enabled_optional_capabilities)))
            != self.enabled_optional_capabilities
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)

    def __repr__(self) -> str:
        return (
            "CompatibilityResult("
            f"profile_id={self.profile_id!r}, "
            f"protocol_status={self.protocol_status.value!r}, "
            f"health_status={self.health_status.value!r}, "
            f"required_capabilities_satisfied={self.required_capabilities_satisfied!r}, "
            f"enabled_optional_capabilities={self.enabled_optional_capabilities!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True, repr=False)
class StandardRetrievalRequest:
    """Product-neutral request data; raw mappings and query text are not retained."""

    query: str = field(repr=False)
    top_k: int
    query_id: str | None = field(default=None, repr=False)
    protocol_version: SemanticVersion | None = None
    requested_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)
        if len(self.query) > MAX_LOCAL_QUERY_LENGTH:
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)
        if type(self.top_k) is not int or not 1 <= self.top_k <= MAX_LOCAL_TOP_K:
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)
        if self.query_id is not None:
            _validate_safe_mapping_identifier(
                self.query_id, CompatibilityErrorCategory.INVALID_MAPPED_REQUEST
            )
        if self.protocol_version is not None and not isinstance(
            self.protocol_version, SemanticVersion
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)
        if (
            not isinstance(self.requested_capabilities, tuple)
            or any(name not in _OPTIONAL_CAPABILITIES for name in self.requested_capabilities)
            or tuple(sorted(set(self.requested_capabilities)))
            != self.requested_capabilities
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)

    @classmethod
    def from_mapping(cls, value: object) -> StandardRetrievalRequest:
        if not isinstance(value, Mapping) or set(value) - _REQUEST_FIELDS:
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)
        if not _REQUIRED_REQUEST_FIELDS.issubset(value):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)
        protocol_version = value.get("protocol_version")
        if protocol_version is not None:
            protocol_version = SemanticVersion.parse(
                protocol_version,
                category=CompatibilityErrorCategory.INVALID_MAPPED_REQUEST,
            )
        requested = value.get("requested_capabilities", ())
        if isinstance(requested, list):
            requested = tuple(requested)
        return cls(
            query=value["query"],  # type: ignore[arg-type]
            top_k=value["top_k"],  # type: ignore[arg-type]
            query_id=value.get("query_id"),  # type: ignore[arg-type]
            protocol_version=protocol_version,
            requested_capabilities=requested,  # type: ignore[arg-type]
        )

    def __repr__(self) -> str:
        return (
            "StandardRetrievalRequest("
            f"query_length={len(self.query)}, top_k={self.top_k}, "
            f"has_query_id={self.query_id is not None}, "
            f"has_protocol_version={self.protocol_version is not None}, "
            f"requested_capability_count={len(self.requested_capabilities)})"
        )

    __str__ = __repr__


@dataclass(frozen=True, repr=False)
class MappedRequest:
    """Immutable mapped fields with a bounded, non-sensitive representation."""

    fields: tuple[tuple[str, object], ...] = field(repr=False)
    encoded_size: int = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.fields, tuple)
            or not all(
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and _SAFE_FIELD_IDENTIFIER.fullmatch(item[0]) is not None
                for item in self.fields
            )
            or len({name for name, _ in self.fields}) != len(self.fields)
            or type(self.encoded_size) is not int
            or not 0 <= self.encoded_size <= MAX_MAPPED_REQUEST_SIZE
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)

    @property
    def mapped_field_count(self) -> int:
        return len(self.fields)

    def as_mapping(self) -> Mapping[str, object]:
        return MappingProxyType(dict(self.fields))

    def __repr__(self) -> str:
        return f"MappedRequest(mapped_field_count={self.mapped_field_count})"

    __str__ = __repr__


@dataclass(frozen=True, repr=False)
class MappedResponse:
    """Validated RankedResult values plus a bounded mapping summary."""

    results: tuple[RankedResult, ...] = field(repr=False)
    score_semantics: ScoreSemantics
    enabled_optional_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.results, tuple)
            or not all(isinstance(result, RankedResult) for result in self.results)
            or not isinstance(self.score_semantics, ScoreSemantics)
            or not isinstance(self.enabled_optional_fields, tuple)
            or tuple(sorted(set(self.enabled_optional_fields)))
            != self.enabled_optional_fields
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)

    @property
    def result_count(self) -> int:
        return len(self.results)

    def __repr__(self) -> str:
        return (
            "MappedResponse("
            f"result_count={self.result_count}, "
            f"score_semantics={self.score_semantics.value!r}, "
            f"enabled_optional_fields={self.enabled_optional_fields!r})"
        )

    __str__ = __repr__


def map_standard_request(
    profile: CompatibilityProfile,
    request: StandardRetrievalRequest,
    compatibility: CompatibilityResult | None = None,
) -> MappedRequest:
    """Apply only the profile's explicit flat request mapping."""
    if not isinstance(profile, CompatibilityProfile) or not isinstance(
        request, StandardRetrievalRequest
    ):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)
    enabled = _validate_mapping_compatibility(profile, compatibility)
    if request.requested_capabilities and not set(request.requested_capabilities).issubset(
        enabled
    ):
        raise compatibility_error(CompatibilityErrorCategory.CAPABILITY_MISMATCH)
    if request.query_id is not None and compatibility is not None and "query_id_echo" not in enabled:
        raise compatibility_error(CompatibilityErrorCategory.CAPABILITY_MISMATCH)

    standard_values: dict[str, object] = {
        "query": request.query,
        "top_k": request.top_k,
    }
    if request.query_id is not None:
        standard_values["query_id"] = request.query_id
    if request.protocol_version is not None:
        standard_values["protocol_version"] = str(request.protocol_version)
    if request.requested_capabilities:
        standard_values["requested_capabilities"] = request.requested_capabilities

    mapped: list[tuple[str, object]] = []
    for standard_field, value in standard_values.items():
        product_field = _mapped_product_field(
            profile.request_field_mapping,
            standard_field,
            CompatibilityErrorCategory.REQUEST_MAPPING_ERROR,
        )
        mapped.append((product_field, value))
    mapped.sort(key=lambda item: item[0])
    payload = dict(mapped)
    try:
        encoded_size = len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise compatibility_error(
            CompatibilityErrorCategory.INVALID_MAPPED_REQUEST
        ) from exc
    if encoded_size > MAX_MAPPED_REQUEST_SIZE:
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)
    return MappedRequest(tuple(mapped), encoded_size)


def map_product_response(
    profile: CompatibilityProfile,
    value: object,
    *,
    top_k: int,
    compatibility: CompatibilityResult,
    expected_query_id: str | None = None,
) -> MappedResponse:
    """Map a bounded product response into evaluator-ready RankedResult values."""
    if not isinstance(profile, CompatibilityProfile):
        raise compatibility_error(CompatibilityErrorCategory.RESPONSE_MAPPING_ERROR)
    if type(top_k) is not int or not 1 <= top_k <= MAX_LOCAL_TOP_K:
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)
    enabled = _validate_mapping_compatibility(profile, compatibility)
    if compatibility is None:
        raise compatibility_error(CompatibilityErrorCategory.CAPABILITY_MISMATCH)
    mapped_by_standard = {
        entry.standard_field: entry.product_field
        for entry in profile.response_field_mapping.entries
    }
    query_id_field = mapped_by_standard.get("query_id")
    allowed_root_fields = {"results"}
    if query_id_field is not None:
        allowed_root_fields.add(query_id_field)
    if not isinstance(value, Mapping) or not set(value).issubset(allowed_root_fields):
        raise compatibility_error(CompatibilityErrorCategory.PRODUCT_RESPONSE_INVALID)
    if "results" not in value:
        raise compatibility_error(CompatibilityErrorCategory.PRODUCT_RESPONSE_INVALID)
    if "query_id_echo" in enabled:
        if expected_query_id is None or query_id_field is None or query_id_field not in value:
            raise compatibility_error(CompatibilityErrorCategory.CAPABILITY_MISMATCH)
        _validate_safe_mapping_identifier(
            expected_query_id, CompatibilityErrorCategory.CAPABILITY_MISMATCH
        )
        if value[query_id_field] != expected_query_id:
            raise compatibility_error(CompatibilityErrorCategory.CAPABILITY_MISMATCH)

    raw_results = value["results"]
    if isinstance(raw_results, (str, bytes)) or not isinstance(raw_results, Sequence):
        raise compatibility_error(CompatibilityErrorCategory.PRODUCT_RESPONSE_INVALID)
    if len(raw_results) > top_k or len(raw_results) > MAX_LOCAL_TOP_K:
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)

    allowed_product_fields = {
        product_field
        for standard_field, product_field in mapped_by_standard.items()
        if standard_field != "query_id"
    }
    required = set(_REQUIRED_RESPONSE_FIELDS)
    if profile.score_semantics is not ScoreSemantics.UNSCORED:
        if "score" not in enabled:
            raise compatibility_error(CompatibilityErrorCategory.CAPABILITY_MISMATCH)
        required.add("score")
    for capability, field_name in (
        ("title", "title"),
        ("matched_keywords", "matched_keywords"),
    ):
        if capability in enabled:
            required.add(field_name)
    if not required.issubset(mapped_by_standard):
        raise compatibility_error(CompatibilityErrorCategory.RESPONSE_MAPPING_ERROR)

    ranked: list[RankedResult] = []
    seen_sources: set[str] = set()
    for raw_item in raw_results:
        if not isinstance(raw_item, Mapping) or not set(raw_item).issubset(
            allowed_product_fields
        ):
            raise compatibility_error(CompatibilityErrorCategory.PRODUCT_RESPONSE_INVALID)
        if any(mapped_by_standard[name] not in raw_item for name in required):
            raise compatibility_error(CompatibilityErrorCategory.RESPONSE_MAPPING_ERROR)
        if (
            profile.score_semantics is ScoreSemantics.UNSCORED
            and "score" in mapped_by_standard
            and mapped_by_standard["score"] in raw_item
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.UNSUPPORTED_SCORE_SEMANTICS
            )

        rank = raw_item[mapped_by_standard["rank"]]
        document_id = raw_item[mapped_by_standard["document_id"]]
        source_id = raw_item[mapped_by_standard["source_id"]]
        _validate_mapped_rank(rank)
        _validate_safe_mapping_identifier(
            document_id, CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE
        )
        _validate_safe_mapping_identifier(
            source_id, CompatibilityErrorCategory.UNSAFE_SOURCE_IDENTIFIER
        )
        if source_id in seen_sources:
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)
        seen_sources.add(source_id)

        score = 0.0
        if profile.score_semantics is not ScoreSemantics.UNSCORED:
            score = _validate_mapped_score(raw_item[mapped_by_standard["score"]])
        title = "not_provided"
        if "title" in enabled:
            title = _validate_mapped_title(raw_item[mapped_by_standard["title"]])
        matched_keywords: list[str] = []
        if "matched_keywords" in enabled:
            matched_keywords = _validate_mapped_keywords(
                raw_item[mapped_by_standard["matched_keywords"]]
            )
        metadata = None
        metadata_field = mapped_by_standard.get("adapter_metadata")
        if metadata_field is not None and metadata_field in raw_item:
            metadata = _validate_mapped_metadata(raw_item[metadata_field])

        ranked.append(
            RankedResult(
                rank=rank,
                document_id=document_id,
                score=score,
                matched_keywords=matched_keywords,
                title=title,
                source_path=source_id,
                adapter_metadata=metadata,
            )
        )

    _validate_score_order(ranked, profile.score_semantics)
    try:
        validated = validate_ranked_results(ranked, top_k)
    except RetrievalAdapterError as exc:
        raise compatibility_error(
            CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE
        ) from exc
    optional_fields = tuple(
        sorted(
            field_name
            for field_name in ("score", "title", "matched_keywords")
            if field_name in enabled
        )
    )
    return MappedResponse(tuple(validated), profile.score_semantics, optional_fields)


def negotiate_compatibility(
    supported_profile: SupportedCompatibilityProfile,
    health: HealthResponse,
    capabilities: CapabilitiesResponse,
    *,
    requested_optional_capabilities: tuple[str, ...] = (),
) -> CompatibilityResult:
    """Validate health and capabilities before any retrieval or mapping execution."""
    if not isinstance(supported_profile, SupportedCompatibilityProfile):
        raise compatibility_error(CompatibilityErrorCategory.PROFILE_NOT_CONFIGURED)
    if not isinstance(health, HealthResponse):
        raise compatibility_error(CompatibilityErrorCategory.HEALTH_INVALID)
    if not isinstance(capabilities, CapabilitiesResponse):
        raise compatibility_error(
            CompatibilityErrorCategory.INVALID_CAPABILITIES_RESPONSE
        )

    profile = supported_profile.profile
    protocol_status = _protocol_status(
        health.protocol_version,
        profile.protocol_version,
        supported_profile.allowed_protocol_minor_versions,
    )
    if health.status is not HealthStatus.HEALTHY or not health.service_available:
        raise compatibility_error(CompatibilityErrorCategory.HEALTH_UNAVAILABLE)

    if any(not capabilities.enabled(name) for name in _REQUIRED_CAPABILITIES):
        raise compatibility_error(CompatibilityErrorCategory.CAPABILITY_MISMATCH)

    requested = _profile_requested_optional_capabilities(profile)
    if not isinstance(requested_optional_capabilities, tuple) or not all(
        isinstance(name, str) for name in requested_optional_capabilities
    ):
        raise compatibility_error(CompatibilityErrorCategory.UNSUPPORTED_CAPABILITY)
    if (
        len(set(requested_optional_capabilities)) != len(requested_optional_capabilities)
        or any(name not in _OPTIONAL_CAPABILITIES for name in requested_optional_capabilities)
    ):
        raise compatibility_error(CompatibilityErrorCategory.UNSUPPORTED_CAPABILITY)
    requested.update(requested_optional_capabilities)
    if any(not capabilities.enabled(name) for name in requested):
        raise compatibility_error(CompatibilityErrorCategory.UNSUPPORTED_CAPABILITY)

    enabled = tuple(
        sorted(
            name
            for name in _OPTIONAL_CAPABILITIES
            if capabilities.enabled(name) and name in requested
        )
    )
    return CompatibilityResult(
        profile_id=profile.profile_id,
        protocol_status=protocol_status,
        health_status=health.status,
        required_capabilities_satisfied=True,
        enabled_optional_capabilities=enabled,
    )


def _profile_requested_optional_capabilities(
    profile: CompatibilityProfile,
) -> set[str]:
    requested: set[str] = set()
    if profile.score_semantics is not ScoreSemantics.UNSCORED:
        requested.add("score")
    if profile.optional_feature_flags.keyword_metadata:
        requested.add("matched_keywords")
    if profile.optional_feature_flags.title:
        requested.add("title")
    if profile.optional_feature_flags.query_id_echo:
        requested.add("query_id_echo")
    return requested


def _protocol_status(
    requested: SemanticVersion,
    supported: SemanticVersion,
    allowed_minors: tuple[int, ...],
) -> ProtocolStatus:
    _validate_requested_version(
        requested,
        supported,
        allowed_minors,
        CompatibilityErrorCategory.PROTOCOL_VERSION_MISMATCH,
    )
    if requested == supported:
        return ProtocolStatus.EXACT
    if requested.minor == supported.minor:
        return ProtocolStatus.COMPATIBLE_PATCH
    return ProtocolStatus.COMPATIBLE_MINOR


def _validate_profile_path(value: object) -> str:
    if not isinstance(value, str) or len(value) > MAX_PROFILE_PATH_LENGTH:
        raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE_PATH)
    parsed = urlsplit(value)
    segments = value.split("/")
    if (
        _SAFE_RELATIVE_HTTP_PATH.fullmatch(value) is None
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "@" in value
        or "\\" in value
        or any(segment in {"", ".", ".."} for segment in segments[1:])
    ):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE_PATH)
    return value


def _validate_minor_allowlist(values: Sequence[int]) -> None:
    if not isinstance(values, tuple):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)
    if any(
        type(value) is not int or value < 0 or value > MAX_VERSION_COMPONENT
        for value in values
    ) or len(set(values)) != len(values):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_PROFILE)


def _validate_requested_version(
    requested: SemanticVersion,
    supported: SemanticVersion,
    allowed_minors: tuple[int, ...],
    category: CompatibilityErrorCategory,
) -> None:
    if requested.major != supported.major:
        raise compatibility_error(category)
    if requested.minor != supported.minor and requested.minor not in allowed_minors:
        raise compatibility_error(category)


def _validate_mapping_compatibility(
    profile: CompatibilityProfile,
    compatibility: CompatibilityResult | None,
) -> set[str]:
    if compatibility is None:
        return set()
    if (
        not isinstance(compatibility, CompatibilityResult)
        or compatibility.profile_id != profile.profile_id
        or not compatibility.required_capabilities_satisfied
    ):
        raise compatibility_error(CompatibilityErrorCategory.CAPABILITY_MISMATCH)
    return set(compatibility.enabled_optional_capabilities)


def _mapped_product_field(
    mapping: FieldMapping,
    standard_field: str,
    category: CompatibilityErrorCategory,
) -> str:
    for entry in mapping.entries:
        if entry.standard_field == standard_field:
            return entry.product_field
    raise compatibility_error(category)


def _validate_safe_mapping_identifier(
    value: object,
    category: CompatibilityErrorCategory,
) -> None:
    if (
        not isinstance(value, str)
        or len(value) > MAX_LOCAL_IDENTIFIER_LENGTH
        or _SAFE_SOURCE_IDENTIFIER.fullmatch(value) is None
    ):
        raise compatibility_error(category)


def _validate_mapped_rank(value: object) -> None:
    if type(value) is not int or value < 1:
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)


def _validate_mapped_score(value: object) -> int | float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)
    return value


def _validate_mapped_title(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_LOCAL_TITLE_LENGTH
    ):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)
    return value


def _validate_mapped_keywords(value: object) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)
    keywords = list(value)
    if len(keywords) > MAX_LOCAL_KEYWORDS or not all(
        isinstance(keyword, str)
        and bool(keyword.strip())
        and len(keyword) <= MAX_LOCAL_KEYWORD_LENGTH
        for keyword in keywords
    ):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)
    return keywords


def _validate_mapped_metadata(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not set(value).issubset(
        LOCAL_RESPONSE_METADATA_KEYS
    ):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)
    metadata = dict(value)
    if not all(_safe_mapping_metadata_value(item) for item in metadata.values()):
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)
    return MappingProxyType(metadata)


def _safe_mapping_metadata_value(value: object) -> bool:
    if isinstance(value, bool):
        return True
    if type(value) in (int, float):
        return math.isfinite(float(value))
    return isinstance(value, str) and len(value) <= MAX_LOCAL_METADATA_VALUE_LENGTH


def _validate_score_order(
    results: Sequence[RankedResult], semantics: ScoreSemantics
) -> None:
    if semantics is ScoreSemantics.UNSCORED:
        return
    scores = [float(result.score) for result in results]
    if semantics is ScoreSemantics.HIGHER_IS_BETTER:
        valid = all(left >= right for left, right in zip(scores, scores[1:]))
    elif semantics is ScoreSemantics.LOWER_IS_BETTER:
        valid = all(left <= right for left, right in zip(scores, scores[1:]))
    else:
        raise compatibility_error(
            CompatibilityErrorCategory.UNSUPPORTED_SCORE_SEMANTICS
        )
    if not valid:
        raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)
