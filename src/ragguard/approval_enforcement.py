from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    SemanticVersion,
    compatibility_error,
)
from ragguard.production_registry import (
    RegistryKind,
    ResolvedRegistryEntry,
    TrustedProductionRegistry,
)
from ragguard.profile_approval import ApprovalRestrictions
from ragguard.retrieval import MAX_LOCAL_TOP_K, RetrievalAdapterError


REQUIRED_RETRIEVAL_CAPABILITIES = frozenset(
    {
        "retrieval",
        "bounded_top_k",
        "deterministic_result_schema",
        "safe_source_identifier",
        "response_size_compliance",
    }
)
OPTIONAL_RETRIEVAL_CAPABILITIES = frozenset(
    {"score", "title", "matched_keywords", "query_id_echo", "protocol_version_echo"}
)
REQUIRED_EXECUTION_CONSTRAINTS = frozenset(
    {
        "bounded_response",
        "loopback_only",
        "no_credentials",
        "no_proxy",
        "no_redirect",
    }
)
OPTIONAL_RESULT_FIELDS = frozenset(
    {"score", "title", "matched_keywords", "query_id_echo"}
)
_CAPABILITIES = REQUIRED_RETRIEVAL_CAPABILITIES | OPTIONAL_RETRIEVAL_CAPABILITIES
_SAFE_ERRORS = frozenset(category.value for category in CompatibilityErrorCategory)


@dataclass(frozen=True, repr=False)
class ApprovalEnforcementRequest:
    profile_id: str
    profile_version: SemanticVersion
    normalized_product_version: SemanticVersion
    evaluation_time: datetime
    registry: TrustedProductionRegistry
    requested_capabilities: tuple[str, ...]
    requested_execution_constraints: tuple[str, ...]
    requested_top_k: int
    requested_optional_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or not isinstance(self.profile_version, SemanticVersion)
            or not isinstance(self.normalized_product_version, SemanticVersion)
            or not isinstance(self.registry, TrustedProductionRegistry)
            or not _canonical(self.requested_capabilities, _CAPABILITIES)
            or not REQUIRED_RETRIEVAL_CAPABILITIES.issubset(
                self.requested_capabilities
            )
            or not _canonical(
                self.requested_execution_constraints,
                REQUIRED_EXECUTION_CONSTRAINTS,
            )
            or set(self.requested_execution_constraints)
            != REQUIRED_EXECUTION_CONSTRAINTS
            or type(self.requested_top_k) is not int
            or not 1 <= self.requested_top_k <= MAX_LOCAL_TOP_K
            or not _canonical(
                self.requested_optional_fields,
                OPTIONAL_RESULT_FIELDS,
            )
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
            )
        _validate_datetime(self.evaluation_time)
        if not set(self.requested_optional_fields).issubset(
            self.requested_capabilities
        ):
            raise compatibility_error(
                CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
            )

    def __repr__(self) -> str:
        return "ApprovalEnforcementRequest(<safe>)"


@dataclass(frozen=True, repr=False)
class ApprovalEnforcementResult:
    allowed: bool
    safe_error_category: str | None
    resolved_approved_entry: ResolvedRegistryEntry | None
    applied_restrictions: tuple[str, ...]
    approval_status_summary: str
    registry_status_summary: str

    def __post_init__(self) -> None:
        if (
            type(self.allowed) is not bool
            or (
                self.safe_error_category is not None
                and self.safe_error_category not in _SAFE_ERRORS
            )
            or (
                self.resolved_approved_entry is not None
                and not isinstance(
                    self.resolved_approved_entry,
                    ResolvedRegistryEntry,
                )
            )
            or not _canonical(
                self.applied_restrictions,
                frozenset(
                    {
                        "matched_keywords_disabled",
                        "maximum_top_k",
                        "query_id_echo_required",
                        "score_disabled",
                        "supported_minor_versions",
                        "title_disabled",
                    }
                ),
            )
            or self.approval_status_summary
            not in {"approved", "approved_with_restrictions", "denied"}
            or self.registry_status_summary
            not in {
                "active_test",
                "deprecated",
                "revoked",
                "suspended",
                "unavailable",
            }
        ):
            _invalid_result()
        if self.allowed:
            if (
                self.safe_error_category is not None
                or self.resolved_approved_entry is None
                or self.approval_status_summary == "denied"
                or self.registry_status_summary != "active_test"
            ):
                _invalid_result()
        elif (
            self.safe_error_category is None
            or self.resolved_approved_entry is not None
            or self.applied_restrictions
            or self.approval_status_summary != "denied"
            or self.registry_status_summary == "active_test"
        ):
            _invalid_result()

    def as_mapping(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "allowed": self.allowed,
                "safe_error_category": self.safe_error_category,
                "restriction_applied": bool(self.applied_restrictions),
                "approval_status": self.approval_status_summary,
                "registry_status": self.registry_status_summary,
            }
        )

    def __repr__(self) -> str:
        return "ApprovalEnforcementResult(<safe>)"


def evaluate_approval_enforcement(
    request: ApprovalEnforcementRequest,
) -> ApprovalEnforcementResult:
    if not isinstance(request, ApprovalEnforcementRequest):
        raise compatibility_error(
            CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
        )
    try:
        if request.registry.kind is not RegistryKind.TEST:
            raise compatibility_error(
                CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
            )
        resolved = request.registry.resolve(
            profile_id=request.profile_id,
            profile_version=request.profile_version,
            normalized_product_version=request.normalized_product_version,
            evaluation_time=request.evaluation_time,
        )
        if not set(request.requested_capabilities).issubset(
            resolved.approved_capabilities
        ):
            _restriction_violation()
        restrictions = resolved.restrictions
        _enforce_restrictions(request, restrictions)
        applied = _restriction_labels(restrictions)
        return ApprovalEnforcementResult(
            allowed=True,
            safe_error_category=None,
            resolved_approved_entry=resolved,
            applied_restrictions=applied,
            approval_status_summary=resolved.approval_decision.value,
            registry_status_summary="active_test",
        )
    except RetrievalAdapterError as exc:
        category = str(exc)
        if category not in _SAFE_ERRORS:
            category = CompatibilityErrorCategory.REGISTRY_METADATA_INVALID.value
        registry_status = {
            CompatibilityErrorCategory.PROFILE_SUSPENDED.value: "suspended",
            CompatibilityErrorCategory.PROFILE_DEPRECATED.value: "deprecated",
            CompatibilityErrorCategory.PROFILE_REVOKED.value: "revoked",
        }.get(category, "unavailable")
        return ApprovalEnforcementResult(
            allowed=False,
            safe_error_category=category,
            resolved_approved_entry=None,
            applied_restrictions=(),
            approval_status_summary="denied",
            registry_status_summary=registry_status,
        )


def require_approved_retrieval(
    request: ApprovalEnforcementRequest,
) -> ApprovalEnforcementResult:
    result = evaluate_approval_enforcement(request)
    if not result.allowed:
        try:
            category = CompatibilityErrorCategory(result.safe_error_category)
        except (TypeError, ValueError):
            category = CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
        raise compatibility_error(category)
    return result


def _enforce_restrictions(
    request: ApprovalEnforcementRequest,
    restrictions: ApprovalRestrictions | None,
) -> None:
    if restrictions is None:
        return
    fields = set(request.requested_optional_fields)
    capabilities = set(request.requested_capabilities)
    if (
        (
            restrictions.maximum_top_k is not None
            and request.requested_top_k > restrictions.maximum_top_k
        )
        or (restrictions.score_disabled and "score" in fields)
        or (restrictions.title_disabled and "title" in fields)
        or (
            restrictions.matched_keywords_disabled
            and "matched_keywords" in fields
        )
        or (
            restrictions.query_id_echo_required
            and (
                "query_id_echo" not in fields
                or "query_id_echo" not in capabilities
            )
        )
    ):
        _restriction_violation()


def _restriction_labels(
    restrictions: ApprovalRestrictions | None,
) -> tuple[str, ...]:
    if restrictions is None:
        return ()
    labels: list[str] = []
    if restrictions.maximum_top_k is not None:
        labels.append("maximum_top_k")
    if restrictions.score_disabled:
        labels.append("score_disabled")
    if restrictions.title_disabled:
        labels.append("title_disabled")
    if restrictions.matched_keywords_disabled:
        labels.append("matched_keywords_disabled")
    if restrictions.query_id_echo_required:
        labels.append("query_id_echo_required")
    if restrictions.supported_minor_versions:
        labels.append("supported_minor_versions")
    return tuple(sorted(labels))


def _canonical(values: object, allowed: frozenset[str]) -> bool:
    return (
        isinstance(values, tuple)
        and all(isinstance(value, str) and value in allowed for value in values)
        and tuple(sorted(set(values))) == values
    )


def _validate_datetime(value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise compatibility_error(
            CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
        )


def _restriction_violation() -> None:
    raise compatibility_error(
        CompatibilityErrorCategory.RESTRICTION_VIOLATION
    )


def _invalid_result() -> None:
    raise compatibility_error(
        CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
    )
