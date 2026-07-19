from __future__ import annotations

from copy import deepcopy

import pytest

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    CompatibilityProfile,
    CompatibilityProfileRegistry,
    ScoreSemantics,
    SemanticVersion,
    SourceIdentifierPolicy,
    SupportedCompatibilityProfile,
    OptionalFeatureFlags,
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
