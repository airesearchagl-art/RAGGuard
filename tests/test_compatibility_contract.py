from __future__ import annotations

from copy import deepcopy

import pytest

from ragguard.compatibility import (
    CapabilitiesResponse,
    CompatibilityErrorCategory,
    CompatibilityProfile,
    CompatibilityProfileRegistry,
    CompatibilityResult,
    HealthResponse,
    HealthStatus,
    OptionalFeatureFlags,
    ProtocolStatus,
    ScoreSemantics,
    SemanticVersion,
    SourceIdentifierPolicy,
    SupportedCompatibilityProfile,
    negotiate_compatibility,
)
from ragguard.retrieval import RetrievalAdapterError


def profile_data() -> dict[str, object]:
    return {
        "profile_id": "synthetic_contract_v1",
        "profile_version": "1.0.0",
        "protocol_version": "1.0.0",
        "health_path": "/health",
        "capabilities_path": "/capabilities",
        "retrieve_path": "/retrieve",
        "request_field_mapping": {
            "query": "query_text",
            "top_k": "result_limit",
            "query_id": "request_id",
        },
        "response_field_mapping": {
            "rank": "position",
            "document_id": "item_id",
            "score": "relevance_score",
            "title": "display_title",
            "source_id": "safe_source_id",
            "matched_keywords": "keyword_matches",
        },
        "score_semantics": "higher_is_better",
        "source_identifier_policy": "opaque_safe_id",
        "optional_feature_flags": {
            "keyword_metadata": True,
            "title": True,
            "query_id_echo": False,
        },
    }


def make_profile(**overrides: object) -> CompatibilityProfile:
    values = profile_data()
    values.update(overrides)
    return CompatibilityProfile.from_mapping(values)


def assert_safe_error(exc: RetrievalAdapterError, category: CompatibilityErrorCategory) -> None:
    assert str(exc) == category.value
    assert repr(exc) == f"RetrievalAdapterError('{category.value}')"


def test_valid_profile_uses_explicit_typed_contract() -> None:
    profile = make_profile()

    assert profile.profile_id == "synthetic_contract_v1"
    assert profile.profile_version == SemanticVersion(1, 0, 0)
    assert profile.protocol_version == SemanticVersion(1, 0, 0)
    assert profile.score_semantics is ScoreSemantics.HIGHER_IS_BETTER
    assert profile.source_identifier_policy is SourceIdentifierPolicy.OPAQUE_SAFE_ID
    assert profile.request_field_mapping.product_field_for("query") == "query_text"
    assert profile.optional_feature_flags.keyword_metadata is True


@pytest.mark.parametrize("value", [None, [], "profile"])
def test_profile_requires_mapping(value: object) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        CompatibilityProfile.from_mapping(value)
    assert_safe_error(caught.value, CompatibilityErrorCategory.PROFILE_NOT_CONFIGURED)


@pytest.mark.parametrize(("mutation", "expected"), [
    (("remove", "retrieve_path"), CompatibilityErrorCategory.INVALID_PROFILE),
    (("add", "unknown_field"), CompatibilityErrorCategory.INVALID_PROFILE),
])
def test_missing_and_unknown_profile_fields_fail_closed(
    mutation: tuple[str, str], expected: CompatibilityErrorCategory
) -> None:
    values = profile_data()
    operation, key = mutation
    if operation == "remove":
        values.pop(key)
    else:
        values[key] = "private-value"
    with pytest.raises(RetrievalAdapterError) as caught:
        CompatibilityProfile.from_mapping(values)
    assert_safe_error(caught.value, expected)


@pytest.mark.parametrize(
    "profile_id",
    [
        "with whitespace",
        "../traversal",
        "folder\\name",
        "https://example.invalid",
        "value?query",
        "value#fragment",
        "C:drive",
        "_" * 65,
        "nonascii-例",
    ],
)
def test_unsafe_profile_identifier_is_rejected_without_echo(profile_id: str) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        make_profile(profile_id=profile_id)
    assert_safe_error(caught.value, CompatibilityErrorCategory.INVALID_PROFILE)
    assert profile_id not in str(caught.value)


@pytest.mark.parametrize(
    "value",
    [True, -1, "1", "1.0", "1.0.0.0", "01.0.0", "1.-1.0", "1.0.0-rc1", "1.0.0+build", "10000.0.0"],
)
def test_invalid_versions_and_prerelease_are_rejected(value: object) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        make_profile(profile_version=value)
    assert_safe_error(caught.value, CompatibilityErrorCategory.INVALID_PROFILE)


def test_registry_rejects_unknown_profile_without_fallback() -> None:
    profile = make_profile()
    registry = CompatibilityProfileRegistry((SupportedCompatibilityProfile(profile),))
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.resolve("synthetic_contract_v2", "1.0.0", "1.0.0")
    assert_safe_error(caught.value, CompatibilityErrorCategory.UNKNOWN_PROFILE)


def test_registry_rejects_unknown_major_and_unallowlisted_minor() -> None:
    profile = make_profile()
    registry = CompatibilityProfileRegistry((SupportedCompatibilityProfile(profile),))
    for version in ("2.0.0", "1.1.0"):
        with pytest.raises(RetrievalAdapterError) as caught:
            registry.resolve(profile.profile_id, version, "1.0.0")
        assert_safe_error(caught.value, CompatibilityErrorCategory.UNSUPPORTED_PROFILE_VERSION)


def test_registry_accepts_only_explicit_minor_allowlist_and_patch_updates() -> None:
    profile = make_profile()
    registry = CompatibilityProfileRegistry(
        (SupportedCompatibilityProfile(profile, allowed_profile_minor_versions=(1,)),)
    )
    assert registry.resolve(profile.profile_id, "1.1.3", "1.0.9") is profile


def test_registry_rejects_protocol_mismatch_safely() -> None:
    profile = make_profile()
    registry = CompatibilityProfileRegistry((SupportedCompatibilityProfile(profile),))
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.resolve(profile.profile_id, "1.0.0", "2.0.0")
    assert_safe_error(caught.value, CompatibilityErrorCategory.PROTOCOL_VERSION_MISMATCH)


@pytest.mark.parametrize(
    "path",
    ["health", "/../health", "/a/../health", "//host/path", "http://host/path", "/path?x=1", "/path#x", "/user@host", "/folder\\name"],
)
def test_invalid_profile_paths_are_rejected_without_echo(path: str) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        make_profile(health_path=path)
    assert_safe_error(caught.value, CompatibilityErrorCategory.INVALID_PROFILE_PATH)
    assert path not in str(caught.value)


@pytest.mark.parametrize(
    "mapping",
    [
        {"query": "same", "top_k": "same"},
        {"query": "query_text", "top_k": "limit", "unknown": "value"},
        {"query": "query.text", "top_k": "limit"},
        {"query": "items[0]", "top_k": "limit"},
        {"query": "${query}", "top_k": "limit"},
        {"query": "", "top_k": "limit"},
    ],
)
def test_invalid_field_mapping_is_rejected(mapping: dict[str, str]) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        make_profile(request_field_mapping=mapping)
    assert_safe_error(caught.value, CompatibilityErrorCategory.INVALID_FIELD_MAPPING)


@pytest.mark.parametrize("semantics", ["normalized", "distance", True])
def test_unsupported_score_semantics_is_rejected(semantics: object) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        make_profile(score_semantics=semantics)
    assert_safe_error(caught.value, CompatibilityErrorCategory.UNSUPPORTED_SCORE_SEMANTICS)


@pytest.mark.parametrize("policy", ["filesystem_path", "full_url", "basename", True])
def test_unsafe_source_identifier_policy_is_rejected(policy: object) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        make_profile(source_identifier_policy=policy)
    assert_safe_error(caught.value, CompatibilityErrorCategory.UNSAFE_SOURCE_IDENTIFIER_POLICY)


@pytest.mark.parametrize(
    "flags",
    [
        {"unknown": True},
        {"keyword_metadata": 1},
        {"title": "yes"},
        [],
    ],
)
def test_optional_feature_flags_are_known_boolean_values_only(flags: object) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        make_profile(optional_feature_flags=flags)
    assert_safe_error(caught.value, CompatibilityErrorCategory.INVALID_PROFILE)


def test_profile_repr_and_str_do_not_expose_paths_or_mappings() -> None:
    values = profile_data()
    values["health_path"] = "/private_health_marker"
    request_mapping = deepcopy(values["request_field_mapping"])
    assert isinstance(request_mapping, dict)
    request_mapping["query"] = "private_query_marker"
    values["request_field_mapping"] = request_mapping
    profile = CompatibilityProfile.from_mapping(values)

    rendered = repr(profile) + str(profile)
    assert "private_health_marker" not in rendered
    assert "private_query_marker" not in rendered
    assert "synthetic_contract_v1" in rendered


def test_contract_models_do_not_execute_mapping_or_perform_io() -> None:
    profile = make_profile()
    assert profile.request_field_mapping.product_field_for("query") == "query_text"
    assert not hasattr(profile, "retrieve")
    assert not hasattr(profile, "health_check")


def test_direct_constructor_does_not_bypass_feature_validation() -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        OptionalFeatureFlags(keyword_metadata=1)  # type: ignore[arg-type]
    assert_safe_error(caught.value, CompatibilityErrorCategory.INVALID_PROFILE)


def health_data(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "status": "healthy",
        "protocol_version": "1.0.0",
        "service_available": True,
    }
    values.update(overrides)
    return values


def capabilities_data(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "retrieval": True,
        "bounded_top_k": True,
        "deterministic_result_schema": True,
        "safe_source_identifier": True,
        "response_size_compliance": True,
        "score": True,
        "title": True,
        "matched_keywords": True,
        "query_id_echo": False,
        "protocol_version_echo": False,
    }
    values.update(overrides)
    return values


def supported_profile(**profile_overrides: object) -> SupportedCompatibilityProfile:
    return SupportedCompatibilityProfile(make_profile(**profile_overrides))


def test_healthy_response_and_valid_capabilities_negotiate_safe_result() -> None:
    result = negotiate_compatibility(
        supported_profile(),
        HealthResponse.from_mapping(health_data()),
        CapabilitiesResponse.from_mapping(capabilities_data()),
    )

    assert result == CompatibilityResult(
        profile_id="synthetic_contract_v1",
        protocol_status=ProtocolStatus.EXACT,
        health_status=HealthStatus.HEALTHY,
        required_capabilities_satisfied=True,
        enabled_optional_capabilities=("matched_keywords", "score", "title"),
    )


@pytest.mark.parametrize("status", ["degraded", "unavailable", "incompatible"])
def test_non_healthy_statuses_remain_distinct_and_stop_negotiation(status: str) -> None:
    health = HealthResponse.from_mapping(health_data(status=status))
    assert health.status.value == status
    with pytest.raises(RetrievalAdapterError) as caught:
        negotiate_compatibility(
            supported_profile(), health, CapabilitiesResponse.from_mapping(capabilities_data())
        )
    assert_safe_error(caught.value, CompatibilityErrorCategory.HEALTH_UNAVAILABLE)


def test_healthy_status_requires_service_available_boolean_true() -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        negotiate_compatibility(
            supported_profile(),
            HealthResponse.from_mapping(health_data(service_available=False)),
            CapabilitiesResponse.from_mapping(capabilities_data()),
        )
    assert_safe_error(caught.value, CompatibilityErrorCategory.HEALTH_UNAVAILABLE)


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"status": "healthy", "protocol_version": "1.0.0"},
        {**health_data(), "unknown": "private"},
        health_data(service_available=1),
        health_data(status="unknown"),
    ],
)
def test_invalid_health_schema_is_rejected_without_raw_values(value: object) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        HealthResponse.from_mapping(value)
    assert_safe_error(caught.value, CompatibilityErrorCategory.HEALTH_INVALID)


@pytest.mark.parametrize("version", ["2.0.0", "1.1.0"])
def test_health_protocol_major_and_unallowlisted_minor_fail_closed(version: str) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        negotiate_compatibility(
            supported_profile(),
            HealthResponse.from_mapping(health_data(protocol_version=version)),
            CapabilitiesResponse.from_mapping(capabilities_data()),
        )
    assert_safe_error(caught.value, CompatibilityErrorCategory.PROTOCOL_VERSION_MISMATCH)
    assert version not in str(caught.value)


def test_health_protocol_minor_requires_explicit_allowlist_without_fallback() -> None:
    support = SupportedCompatibilityProfile(
        make_profile(), allowed_protocol_minor_versions=(1,)
    )
    result = negotiate_compatibility(
        support,
        HealthResponse.from_mapping(health_data(protocol_version="1.1.4")),
        CapabilitiesResponse.from_mapping(capabilities_data()),
    )
    assert result.protocol_status is ProtocolStatus.COMPATIBLE_MINOR


def test_valid_required_capabilities_may_omit_unrequested_optional_fields() -> None:
    profile = make_profile(
        score_semantics="unscored",
        optional_feature_flags={
            "keyword_metadata": False,
            "title": False,
            "query_id_echo": False,
        },
    )
    required_only = {
        key: True
        for key in (
            "retrieval",
            "bounded_top_k",
            "deterministic_result_schema",
            "safe_source_identifier",
            "response_size_compliance",
        )
    }
    result = negotiate_compatibility(
        SupportedCompatibilityProfile(profile),
        HealthResponse.from_mapping(health_data()),
        CapabilitiesResponse.from_mapping(required_only),
    )
    assert result.enabled_optional_capabilities == ()


@pytest.mark.parametrize(
    "capability",
    [
        "retrieval",
        "bounded_top_k",
        "deterministic_result_schema",
        "safe_source_identifier",
        "response_size_compliance",
    ],
)
def test_required_capability_false_stops_before_retrieval(capability: str) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        negotiate_compatibility(
            supported_profile(),
            HealthResponse.from_mapping(health_data()),
            CapabilitiesResponse.from_mapping(capabilities_data(**{capability: False})),
        )
    assert_safe_error(caught.value, CompatibilityErrorCategory.CAPABILITY_MISMATCH)


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"retrieval": True},
        {**capabilities_data(), "unknown": True},
        capabilities_data(score=1),
        capabilities_data(title="yes"),
    ],
)
def test_invalid_capabilities_response_is_rejected(value: object) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        CapabilitiesResponse.from_mapping(value)
    assert_safe_error(
        caught.value, CompatibilityErrorCategory.INVALID_CAPABILITIES_RESPONSE
    )


@pytest.mark.parametrize("capability", ["score", "title", "matched_keywords"])
def test_profile_requested_optional_capability_mismatch_fails_closed(
    capability: str,
) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        negotiate_compatibility(
            supported_profile(),
            HealthResponse.from_mapping(health_data()),
            CapabilitiesResponse.from_mapping(capabilities_data(**{capability: False})),
        )
    assert_safe_error(caught.value, CompatibilityErrorCategory.UNSUPPORTED_CAPABILITY)


def test_explicit_optional_capability_is_never_silently_disabled() -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        negotiate_compatibility(
            supported_profile(),
            HealthResponse.from_mapping(health_data()),
            CapabilitiesResponse.from_mapping(capabilities_data()),
            requested_optional_capabilities=("protocol_version_echo",),
        )
    assert_safe_error(caught.value, CompatibilityErrorCategory.UNSUPPORTED_CAPABILITY)


def test_unknown_or_duplicate_requested_capability_is_rejected() -> None:
    for requested in (("unknown",), ("title", "title"), ([],)):
        with pytest.raises(RetrievalAdapterError) as caught:
            negotiate_compatibility(
                supported_profile(),
                HealthResponse.from_mapping(health_data()),
                CapabilitiesResponse.from_mapping(capabilities_data()),
                requested_optional_capabilities=requested,  # type: ignore[arg-type]
            )
        assert_safe_error(caught.value, CompatibilityErrorCategory.UNSUPPORTED_CAPABILITY)


def test_result_and_errors_do_not_retain_raw_response_or_sensitive_values() -> None:
    result = negotiate_compatibility(
        supported_profile(),
        HealthResponse.from_mapping(health_data()),
        CapabilitiesResponse.from_mapping(capabilities_data()),
    )
    rendered = repr(result) + str(result)
    for marker in ("/health", "query_text", "private-endpoint", "credential-value"):
        assert marker not in rendered

    raw_marker = "private-version-marker"
    with pytest.raises(RetrievalAdapterError) as caught:
        HealthResponse.from_mapping(health_data(protocol_version=raw_marker))
    assert raw_marker not in str(caught.value)
    assert_safe_error(caught.value, CompatibilityErrorCategory.HEALTH_INVALID)
    assert caught.value.__cause__ is None

    raw_status = "private-status-marker"
    with pytest.raises(RetrievalAdapterError) as status_error:
        HealthResponse.from_mapping(health_data(status=raw_status))
    assert raw_status not in str(status_error.value)
    assert status_error.value.__cause__ is None


def test_health_and_capability_models_store_only_typed_fields() -> None:
    health = HealthResponse.from_mapping(health_data())
    capabilities = CapabilitiesResponse.from_mapping(capabilities_data())
    assert not hasattr(health, "raw_response")
    assert not hasattr(capabilities, "metadata")
    assert not hasattr(capabilities, "raw_response")
    assert "1.0.0" not in repr(health)
