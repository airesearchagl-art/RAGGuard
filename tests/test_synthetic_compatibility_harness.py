from __future__ import annotations

from copy import deepcopy

import pytest

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    CompatibilityProfile,
    CompatibilityProfileRegistry,
    StandardRetrievalRequest,
    SupportedCompatibilityProfile,
)
from ragguard.compatibility_harness import SyntheticCompatibilityHarness
from ragguard.retrieval import RetrievalAdapterError


def profile_data() -> dict[str, object]:
    return {
        "profile_id": "synthetic_harness_v1",
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
            "query_id_echo": False,
        },
    }


def make_profile(**overrides: object) -> CompatibilityProfile:
    values = profile_data()
    values.update(overrides)
    return CompatibilityProfile.from_mapping(values)


def make_harness(
    profile: CompatibilityProfile | None = None,
    *,
    allowed_profile_minors: tuple[int, ...] = (),
    allowed_protocol_minors: tuple[int, ...] = (),
) -> SyntheticCompatibilityHarness:
    selected = profile or make_profile()
    supported = SupportedCompatibilityProfile(
        selected,
        allowed_profile_minor_versions=allowed_profile_minors,
        allowed_protocol_minor_versions=allowed_protocol_minors,
    )
    return SyntheticCompatibilityHarness(CompatibilityProfileRegistry((supported,)))


def health(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "status": "healthy",
        "protocol_version": "1.0.0",
        "service_available": True,
    }
    value.update(overrides)
    return value


def capabilities(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "retrieval": True,
        "bounded_top_k": True,
        "deterministic_result_schema": True,
        "safe_source_identifier": True,
        "response_size_compliance": True,
        "score": True,
        "title": True,
        "matched_keywords": True,
        "query_id_echo": True,
        "protocol_version_echo": True,
    }
    value.update(overrides)
    return value


def product_item(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "position": 1,
        "item_id": "synthetic-document-001",
        "relevance": 0.9,
        "display_title": "Synthetic Document",
        "safe_source": "synthetic-source-001",
        "matches": ["synthetic"],
    }
    value.update(overrides)
    return value


def run_valid(
    harness: SyntheticCompatibilityHarness | None = None,
    *,
    request: StandardRetrievalRequest | None = None,
    health_response: object | None = None,
    capabilities_response: object | None = None,
    product_response: object | None = None,
    profile_id: object = "synthetic_harness_v1",
    profile_version: object = "1.0.0",
    protocol_version: object = "1.0.0",
    requested_optional_capabilities: tuple[str, ...] = (),
):
    return (harness or make_harness()).run(
        profile_id=profile_id,
        profile_version=profile_version,
        protocol_version=protocol_version,
        health_response=health() if health_response is None else health_response,
        capabilities_response=(
            capabilities()
            if capabilities_response is None
            else capabilities_response
        ),
        request=request or StandardRetrievalRequest("synthetic query marker", 3),
        product_response=(
            {"results": [product_item()]}
            if product_response is None
            else product_response
        ),
        requested_optional_capabilities=requested_optional_capabilities,
    )


def assert_category(
    caught: pytest.ExceptionInfo[RetrievalAdapterError],
    category: CompatibilityErrorCategory,
) -> None:
    assert str(caught.value) == category.value


@pytest.mark.parametrize(
    ("semantics", "score", "enabled"),
    [
        ("higher_is_better", 0.9, ("matched_keywords", "score", "title")),
        ("lower_is_better", 0.1, ("matched_keywords", "score", "title")),
        ("unscored", None, ()),
    ],
)
def test_harness_runs_complete_phase_a_to_c_path(
    semantics: str,
    score: float | None,
    enabled: tuple[str, ...],
) -> None:
    flags = {
        "keyword_metadata": semantics != "unscored",
        "title": semantics != "unscored",
        "query_id_echo": False,
    }
    profile = make_profile(score_semantics=semantics, optional_feature_flags=flags)
    item = product_item()
    if score is None:
        item.pop("relevance")
    else:
        item["relevance"] = score

    result = run_valid(
        make_harness(profile),
        capabilities_response=(
            capabilities()
            if enabled
            else {key: True for key in (
                "retrieval",
                "bounded_top_k",
                "deterministic_result_schema",
                "safe_source_identifier",
                "response_size_compliance",
            )}
        ),
        product_response={"results": [item]},
    )

    assert result.profile_id == "synthetic_harness_v1"
    assert result.protocol_status.value == "exact"
    assert result.health_status.value == "healthy"
    assert result.enabled_optional_capabilities == enabled
    assert result.mapped_request_field_count == 2
    assert result.result_count == 1
    assert result.score_semantics.value == semantics
    assert result.ranked_results[0].document_id == "synthetic-document-001"
    assert result.ranked_results[0].score == (0.0 if score is None else score)


def test_harness_is_deterministic_for_identical_inputs() -> None:
    harness = make_harness()
    first = run_valid(harness)
    second = run_valid(harness)
    assert first == second
    assert first.ranked_results == second.ranked_results


@pytest.mark.parametrize(
    ("overrides", "expected_status"),
    [
        ({"status": "degraded"}, "health_unavailable"),
        ({"status": "unavailable"}, "health_unavailable"),
        ({"status": "incompatible"}, "health_unavailable"),
        ({"service_available": False}, "health_unavailable"),
    ],
)
def test_health_failures_stop_before_mapping(
    overrides: dict[str, object], expected_status: str
) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(health_response=health(**overrides))
    assert str(caught.value) == expected_status


@pytest.mark.parametrize(
    ("profile_id", "profile_version", "protocol_version", "category"),
    [
        (
            "unknown_profile",
            "1.0.0",
            "1.0.0",
            CompatibilityErrorCategory.UNKNOWN_PROFILE,
        ),
        (
            "synthetic_harness_v1",
            "2.0.0",
            "1.0.0",
            CompatibilityErrorCategory.UNSUPPORTED_PROFILE_VERSION,
        ),
        (
            "synthetic_harness_v1",
            "1.1.0",
            "1.0.0",
            CompatibilityErrorCategory.UNSUPPORTED_PROFILE_VERSION,
        ),
        (
            "synthetic_harness_v1",
            "1.0.0",
            "2.0.0",
            CompatibilityErrorCategory.PROTOCOL_VERSION_MISMATCH,
        ),
    ],
)
def test_profile_and_version_fail_closed(
    profile_id: str,
    profile_version: str,
    protocol_version: str,
    category: CompatibilityErrorCategory,
) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(
            profile_id=profile_id,
            profile_version=profile_version,
            protocol_version=protocol_version,
        )
    assert_category(caught, category)


def test_explicit_minor_compatibility_is_accepted() -> None:
    result = run_valid(
        make_harness(allowed_profile_minors=(1,), allowed_protocol_minors=(1,)),
        profile_version="1.1.3",
        protocol_version="1.1.2",
        health_response=health(protocol_version="1.1.4"),
    )
    assert result.protocol_status.value == "compatible_minor"


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
def test_missing_required_capability_fails_closed(capability: str) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(capabilities_response=capabilities(**{capability: False}))
    assert_category(caught, CompatibilityErrorCategory.CAPABILITY_MISMATCH)


def test_missing_requested_optional_capability_fails_closed() -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(capabilities_response=capabilities(title=False))
    assert_category(caught, CompatibilityErrorCategory.UNSUPPORTED_CAPABILITY)


@pytest.mark.parametrize(
    ("health_response", "capabilities_response", "category"),
    [
        ({"status": "healthy"}, capabilities(), CompatibilityErrorCategory.HEALTH_INVALID),
        (health(), {"retrieval": True}, CompatibilityErrorCategory.INVALID_CAPABILITIES_RESPONSE),
    ],
)
def test_malformed_pre_retrieval_responses_fail_closed(
    health_response: object,
    capabilities_response: object,
    category: CompatibilityErrorCategory,
) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(
            health_response=health_response,
            capabilities_response=capabilities_response,
        )
    assert_category(caught, category)


def test_missing_optional_request_mapping_uses_existing_category() -> None:
    data = profile_data()
    mapping = deepcopy(data["request_field_mapping"])
    assert isinstance(mapping, dict)
    mapping.pop("query_id")
    data["request_field_mapping"] = mapping
    data["optional_feature_flags"] = {
        "keyword_metadata": True,
        "title": True,
        "query_id_echo": True,
    }
    profile = CompatibilityProfile.from_mapping(data)
    request = StandardRetrievalRequest("synthetic", 1, query_id="query-001")

    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(make_harness(profile), request=request)
    assert_category(caught, CompatibilityErrorCategory.REQUEST_MAPPING_ERROR)


def test_invalid_standard_request_uses_existing_category() -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        StandardRetrievalRequest.from_mapping({"query": "synthetic", "top_k": True})
    assert_category(caught, CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)


def test_missing_negotiated_response_mapping_fails_closed() -> None:
    data = profile_data()
    mapping = deepcopy(data["response_field_mapping"])
    assert isinstance(mapping, dict)
    mapping.pop("title")
    data["response_field_mapping"] = mapping
    profile = CompatibilityProfile.from_mapping(data)

    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(make_harness(profile))
    assert_category(caught, CompatibilityErrorCategory.RESPONSE_MAPPING_ERROR)


@pytest.mark.parametrize(
    ("product_response", "category"),
    [
        ({"invalid": []}, CompatibilityErrorCategory.PRODUCT_RESPONSE_INVALID),
        (
            {"results": [product_item(item_id=None)]},
            CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE,
        ),
        (
            {"results": [product_item(safe_source="C:/private/path")]},
            CompatibilityErrorCategory.UNSAFE_SOURCE_IDENTIFIER,
        ),
        (
            {
                "results": [
                    product_item(),
                    product_item(position=2, safe_source="synthetic-source-002"),
                ]
            },
            CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE,
        ),
        (
            {
                "results": [
                    product_item(),
                    product_item(
                        position=3,
                        item_id="synthetic-document-002",
                        safe_source="synthetic-source-002",
                        relevance=0.8,
                    ),
                ]
            },
            CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE,
        ),
    ],
)
def test_product_response_failures_use_existing_categories(
    product_response: object,
    category: CompatibilityErrorCategory,
) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(product_response=product_response)
    assert_category(caught, category)


def test_missing_required_product_field_fails_closed() -> None:
    item = product_item()
    item.pop("item_id")
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(product_response={"results": [item]})
    assert_category(caught, CompatibilityErrorCategory.RESPONSE_MAPPING_ERROR)


def test_product_result_count_cannot_exceed_requested_top_k() -> None:
    results = [
        product_item(),
        product_item(
            position=2,
            item_id="synthetic-document-002",
            safe_source="synthetic-source-002",
            relevance=0.8,
        ),
    ]
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(
            request=StandardRetrievalRequest("synthetic", 1),
            product_response={"results": results},
        )
    assert_category(caught, CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)


def test_top_k_and_absolute_item_limits_fail_closed() -> None:
    results = [
        product_item(
            position=index,
            item_id=f"synthetic-document-{index:03d}",
            safe_source=f"synthetic-source-{index:03d}",
            relevance=1.0 - index / 1000,
        )
        for index in range(1, 102)
    ]
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(
            request=StandardRetrievalRequest("synthetic", 100),
            product_response={"results": results},
        )
    assert_category(caught, CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)


def test_query_id_echo_mismatch_fails_closed() -> None:
    profile = make_profile(
        optional_feature_flags={
            "keyword_metadata": True,
            "title": True,
            "query_id_echo": True,
        }
    )
    request = StandardRetrievalRequest("synthetic", 1, query_id="query-001")
    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(
            make_harness(profile),
            request=request,
            product_response={
                "results": [product_item()],
                "echo_request_id": "query-002",
            },
        )
    assert_category(caught, CompatibilityErrorCategory.CAPABILITY_MISMATCH)


def test_unsupported_score_semantics_fails_before_harness_execution() -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        make_profile(score_semantics="normalized")
    assert_category(caught, CompatibilityErrorCategory.UNSUPPORTED_SCORE_SEMANTICS)


def test_result_and_errors_do_not_retain_or_render_raw_inputs() -> None:
    query_marker = "private-query-marker"
    raw_marker = "private-raw-response-marker"
    result = run_valid(
        request=StandardRetrievalRequest(query_marker, 1),
        product_response={
            "results": [product_item(display_title=raw_marker)]
        },
    )
    rendered = repr(result) + str(result)
    stored = repr(vars(result))
    for marker in (
        query_marker,
        "/health",
        "query_text",
        "credential-marker",
        "127.0.0.1:9999",
        "C:/private/path",
    ):
        assert marker not in rendered
        assert marker not in stored
    assert raw_marker in stored
    assert "query_text" not in vars(result)
    assert "health_response" not in vars(result)
    assert "capabilities_response" not in vars(result)
    assert "product_response" not in vars(result)

    with pytest.raises(RetrievalAdapterError) as caught:
        run_valid(
            request=StandardRetrievalRequest(query_marker, 1),
            product_response={"results": [{"raw": raw_marker}]},
        )
    assert str(caught.value) == CompatibilityErrorCategory.PRODUCT_RESPONSE_INVALID.value
    assert repr(caught.value) == "RetrievalAdapterError('product_response_invalid')"
    assert query_marker not in str(caught.value)
    assert raw_marker not in str(caught.value)


def test_harness_module_has_no_io_random_sleep_or_product_schema() -> None:
    import ragguard.compatibility_harness as module

    source_names = set(module.__dict__)
    assert source_names.isdisjoint(
        {"socket", "requests", "urllib", "Path", "open", "sleep", "random"}
    )
    assert not hasattr(SyntheticCompatibilityHarness, "connect")
    assert not hasattr(SyntheticCompatibilityHarness, "load_config")
