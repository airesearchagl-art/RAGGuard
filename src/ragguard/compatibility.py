from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlsplit

from ragguard.retrieval import RetrievalAdapterError


MAX_PROFILE_IDENTIFIER_LENGTH = 64
MAX_PROFILE_PATH_LENGTH = 128
MAX_VERSION_COMPONENT = 9999

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
_REQUEST_FIELDS = frozenset({"query", "top_k", "query_id", "capability_version"})
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
    }
)
_REQUIRED_RESPONSE_FIELDS = frozenset(
    {"rank", "document_id", "title", "source_id", "matched_keywords"}
)
_FEATURE_FIELDS = frozenset({"keyword_metadata", "title", "query_id_echo"})
_SAFE_PROFILE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SAFE_FIELD_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_SAFE_RELATIVE_HTTP_PATH = re.compile(r"/[A-Za-z0-9_/-]{1,127}\Z")
_SEMANTIC_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


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


class ScoreSemantics(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    UNSCORED = "unscored"


class SourceIdentifierPolicy(str, Enum):
    OPAQUE_SAFE_ID = "opaque_safe_id"


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
