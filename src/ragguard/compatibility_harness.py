from __future__ import annotations

from dataclasses import dataclass, field

from ragguard.compatibility import (
    CapabilitiesResponse,
    CompatibilityErrorCategory,
    CompatibilityProfileRegistry,
    CompatibilityResult,
    HealthResponse,
    HealthStatus,
    ProtocolStatus,
    ScoreSemantics,
    StandardRetrievalRequest,
    SupportedCompatibilityProfile,
    compatibility_error,
    map_product_response,
    map_standard_request,
    negotiate_compatibility,
)
from ragguard.retrieval import RankedResult


@dataclass(frozen=True, repr=False)
class SyntheticCompatibilityResult:
    """Safe immutable outcome without raw synthetic inputs or mapped payloads."""

    profile_id: str
    protocol_status: ProtocolStatus
    health_status: HealthStatus
    enabled_optional_capabilities: tuple[str, ...]
    mapped_request_field_count: int
    result_count: int
    score_semantics: ScoreSemantics
    ranked_results: tuple[RankedResult, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or not isinstance(self.protocol_status, ProtocolStatus)
            or not isinstance(self.health_status, HealthStatus)
            or not isinstance(self.enabled_optional_capabilities, tuple)
            or tuple(sorted(set(self.enabled_optional_capabilities)))
            != self.enabled_optional_capabilities
            or type(self.mapped_request_field_count) is not int
            or self.mapped_request_field_count < 0
            or type(self.result_count) is not int
            or self.result_count < 0
            or not isinstance(self.score_semantics, ScoreSemantics)
            or not isinstance(self.ranked_results, tuple)
            or not all(isinstance(result, RankedResult) for result in self.ranked_results)
            or self.result_count != len(self.ranked_results)
        ):
            raise compatibility_error(CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)

    def __repr__(self) -> str:
        return (
            "SyntheticCompatibilityResult("
            f"profile_id={self.profile_id!r}, "
            f"protocol_status={self.protocol_status.value!r}, "
            f"health_status={self.health_status.value!r}, "
            f"enabled_optional_capabilities={self.enabled_optional_capabilities!r}, "
            f"mapped_request_field_count={self.mapped_request_field_count}, "
            f"result_count={self.result_count}, "
            f"score_semantics={self.score_semantics.value!r})"
        )

    __str__ = __repr__


@dataclass(frozen=True, repr=False)
class SyntheticCompatibilityHarness:
    """Deterministic no-I/O orchestration of the Phase A-C production contracts."""

    registry: CompatibilityProfileRegistry = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.registry, CompatibilityProfileRegistry):
            raise compatibility_error(CompatibilityErrorCategory.PROFILE_NOT_CONFIGURED)

    def run(
        self,
        *,
        profile_id: object,
        profile_version: object,
        protocol_version: object,
        health_response: object,
        capabilities_response: object,
        request: StandardRetrievalRequest,
        product_response: object,
        requested_optional_capabilities: tuple[str, ...] = (),
    ) -> SyntheticCompatibilityResult:
        profile = self.registry.resolve(
            profile_id,
            profile_version,
            protocol_version,
        )
        health = HealthResponse.from_mapping(health_response)
        capabilities = CapabilitiesResponse.from_mapping(capabilities_response)
        compatibility = negotiate_compatibility(
            self._supported_profile(profile.profile_id),
            health,
            capabilities,
            requested_optional_capabilities=requested_optional_capabilities,
        )
        mapped_request = map_standard_request(profile, request, compatibility)
        mapped_response = map_product_response(
            profile,
            product_response,
            top_k=request.top_k,
            compatibility=compatibility,
            expected_query_id=request.query_id,
        )
        return self._safe_result(
            compatibility,
            mapped_request.mapped_field_count,
            mapped_response.results,
            mapped_response.score_semantics,
        )

    def _supported_profile(self, profile_id: str) -> SupportedCompatibilityProfile:
        return next(
            entry
            for entry in self.registry.profiles
            if entry.profile.profile_id == profile_id
        )

    @staticmethod
    def _safe_result(
        compatibility: CompatibilityResult,
        mapped_request_field_count: int,
        ranked_results: tuple[RankedResult, ...],
        score_semantics: ScoreSemantics,
    ) -> SyntheticCompatibilityResult:
        return SyntheticCompatibilityResult(
            profile_id=compatibility.profile_id,
            protocol_status=compatibility.protocol_status,
            health_status=compatibility.health_status,
            enabled_optional_capabilities=compatibility.enabled_optional_capabilities,
            mapped_request_field_count=mapped_request_field_count,
            result_count=len(ranked_results),
            score_semantics=score_semantics,
            ranked_results=ranked_results,
        )
