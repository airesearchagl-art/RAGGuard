from __future__ import annotations

from copy import deepcopy

import pytest

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    CompatibilityProfile,
    CompatibilityResult,
    HealthStatus,
    ProtocolStatus,
    ScoreSemantics,
    StandardRetrievalRequest,
    map_product_response,
    map_standard_request,
)
from ragguard.retrieval import RetrievalAdapterError


def profile_data() -> dict[str, object]:
    return {
        "profile_id": "synthetic_mapping_v1",
        "profile_version": "1.0.0",
        "protocol_version": "1.0.0",
        "health_path": "/health",
        "capabilities_path": "/capabilities",
        "retrieve_path": "/retrieve",
        "request_field_mapping": {
            "query": "query_text",
            "top_k": "result_limit",
            "query_id": "request_id",
            "protocol_version": "contract_version",
            "requested_capabilities": "features",
        },
        "response_field_mapping": {
            "rank": "position",
            "document_id": "item_id",
            "score": "relevance",
            "title": "display_title",
            "source_id": "safe_source",
            "matched_keywords": "matches",
            "adapter_metadata": "safe_metadata",
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


def compatibility(
    profile: CompatibilityProfile,
    enabled: tuple[str, ...] = ("matched_keywords", "score", "title"),
) -> CompatibilityResult:
    return CompatibilityResult(
        profile_id=profile.profile_id,
        protocol_status=ProtocolStatus.EXACT,
        health_status=HealthStatus.HEALTHY,
        required_capabilities_satisfied=True,
        enabled_optional_capabilities=enabled,
    )


def product_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "position": 1,
        "item_id": "synthetic-document-001",
        "relevance": 0.9,
        "display_title": "Synthetic Document",
        "safe_source": "synthetic-source-001",
        "matches": ["synthetic"],
        "safe_metadata": {"result_type": "synthetic"},
    }
    item.update(overrides)
    return item


def assert_category(
    caught: pytest.ExceptionInfo[RetrievalAdapterError],
    category: CompatibilityErrorCategory,
) -> None:
    assert str(caught.value) == category.value


def test_standard_request_maps_only_explicit_flat_fields() -> None:
    profile = make_profile(
        optional_feature_flags={
            "keyword_metadata": True,
            "title": True,
            "query_id_echo": True,
        }
    )
    request = StandardRetrievalRequest.from_mapping(
        {
            "query": "synthetic question marker",
            "top_k": 3,
            "query_id": "query-001",
            "protocol_version": "1.0.0",
            "requested_capabilities": ["score", "title"],
        }
    )

    mapped = map_standard_request(
        profile,
        request,
        compatibility(
            profile, ("matched_keywords", "query_id_echo", "score", "title")
        ),
    )

    assert dict(mapped.as_mapping()) == {
        "contract_version": "1.0.0",
        "features": ("score", "title"),
        "query_text": "synthetic question marker",
        "request_id": "query-001",
        "result_limit": 3,
    }
    assert mapped.mapped_field_count == 5
    assert "synthetic question marker" not in repr(request) + repr(mapped)


@pytest.mark.parametrize("top_k", [True, False, 0, 101, 1.0, "1"])
def test_standard_request_rejects_invalid_top_k(top_k: object) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        StandardRetrievalRequest.from_mapping({"query": "synthetic", "top_k": top_k})
    assert_category(caught, CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)


def test_standard_request_rejects_unknown_fields_and_unsafe_query_id() -> None:
    for value in (
        {"query": "synthetic", "top_k": 1, "unknown": "private"},
        {"query": "synthetic", "top_k": 1, "query_id": "../private"},
    ):
        with pytest.raises(RetrievalAdapterError) as caught:
            StandardRetrievalRequest.from_mapping(value)
        assert_category(caught, CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)


def test_request_mapping_rejects_unmapped_required_or_requested_field() -> None:
    values = profile_data()
    mapping = deepcopy(values["request_field_mapping"])
    assert isinstance(mapping, dict)
    mapping.pop("query_id")
    values["request_field_mapping"] = mapping
    profile = CompatibilityProfile.from_mapping(values)
    request = StandardRetrievalRequest("synthetic", 1, query_id="query-001")

    with pytest.raises(RetrievalAdapterError) as caught:
        map_standard_request(profile, request)
    assert_category(caught, CompatibilityErrorCategory.REQUEST_MAPPING_ERROR)


def test_mapped_request_enforces_encoded_64_kib_limit() -> None:
    profile = make_profile()
    request = StandardRetrievalRequest("x" * 4096, 1)
    mapped = map_standard_request(profile, request)
    assert mapped.encoded_size < 65_536

    with pytest.raises(RetrievalAdapterError) as caught:
        type(mapped)(mapped.fields, 65_537)
    assert_category(caught, CompatibilityErrorCategory.INVALID_MAPPED_REQUEST)


def test_valid_product_response_normalizes_to_ranked_results() -> None:
    profile = make_profile()
    response = map_product_response(
        profile,
        {"results": [product_item()]},
        top_k=3,
        compatibility=compatibility(profile),
    )

    assert response.result_count == 1
    assert response.results[0].rank == 1
    assert response.results[0].document_id == "synthetic-document-001"
    assert response.results[0].source_path == "synthetic-source-001"
    assert response.results[0].score == 0.9
    assert response.results[0].matched_keywords == ["synthetic"]
    assert response.results[0].adapter_metadata == {"result_type": "synthetic"}


@pytest.mark.parametrize(
    ("semantics", "scores"),
    [
        ("higher_is_better", (0.9, 0.7)),
        ("lower_is_better", (0.1, 0.4)),
    ],
)
def test_score_semantics_preserve_product_values(
    semantics: str, scores: tuple[float, float]
) -> None:
    profile = make_profile(score_semantics=semantics)
    items = [
        product_item(relevance=scores[0]),
        product_item(
            position=2,
            item_id="synthetic-document-002",
            safe_source="synthetic-source-002",
            relevance=scores[1],
        ),
    ]
    response = map_product_response(
        profile,
        {"results": items},
        top_k=2,
        compatibility=compatibility(profile),
    )
    assert tuple(result.score for result in response.results) == scores


def test_unscored_response_does_not_require_or_accept_product_score() -> None:
    profile = make_profile(
        score_semantics="unscored",
        optional_feature_flags={
            "keyword_metadata": False,
            "title": False,
            "query_id_echo": False,
        },
    )
    item = product_item()
    item.pop("relevance")
    response = map_product_response(
        profile,
        {"results": [item]},
        top_k=1,
        compatibility=compatibility(profile, ()),
    )
    assert response.score_semantics is ScoreSemantics.UNSCORED
    assert response.results[0].score == 0.0
    assert response.results[0].title == "not_provided"
    assert response.results[0].matched_keywords == []

    item["relevance"] = 0.5
    with pytest.raises(RetrievalAdapterError) as caught:
        map_product_response(
            profile,
            {"results": [item]},
            top_k=1,
            compatibility=compatibility(profile, ()),
        )
    assert_category(caught, CompatibilityErrorCategory.UNSUPPORTED_SCORE_SEMANTICS)


@pytest.mark.parametrize("score", [True, False, float("nan"), float("inf"), "0.5"])
def test_invalid_scores_fail_closed(score: object) -> None:
    profile = make_profile()
    with pytest.raises(RetrievalAdapterError) as caught:
        map_product_response(
            profile,
            {"results": [product_item(relevance=score)]},
            top_k=1,
            compatibility=compatibility(profile),
        )
    assert_category(caught, CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)


def test_score_rank_contradiction_is_not_silently_corrected() -> None:
    profile = make_profile()
    items = [
        product_item(relevance=0.2),
        product_item(
            position=2,
            item_id="synthetic-document-002",
            safe_source="synthetic-source-002",
            relevance=0.8,
        ),
    ]
    with pytest.raises(RetrievalAdapterError) as caught:
        map_product_response(
            profile,
            {"results": items},
            top_k=2,
            compatibility=compatibility(profile),
        )
    assert_category(caught, CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)


@pytest.mark.parametrize(
    ("mutation", "category"),
    [
        ("missing_required", CompatibilityErrorCategory.RESPONSE_MAPPING_ERROR),
        ("unknown_field", CompatibilityErrorCategory.PRODUCT_RESPONSE_INVALID),
        ("unsafe_source", CompatibilityErrorCategory.UNSAFE_SOURCE_IDENTIFIER),
        ("rank_gap", CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE),
        ("duplicate_document", CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE),
        ("duplicate_source", CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE),
    ],
)
def test_response_mapping_rejects_invalid_product_results(
    mutation: str, category: CompatibilityErrorCategory
) -> None:
    profile = make_profile()
    first = product_item()
    items = [first]
    if mutation == "missing_required":
        first.pop("item_id")
    elif mutation == "unknown_field":
        first["private_product_field"] = "private-value"
    elif mutation == "unsafe_source":
        first["safe_source"] = "C:/private/path"
    else:
        second = product_item(
            position=2,
            item_id="synthetic-document-002",
            safe_source="synthetic-source-002",
            relevance=0.8,
        )
        if mutation == "rank_gap":
            second["position"] = 3
        elif mutation == "duplicate_document":
            second["item_id"] = first["item_id"]
        elif mutation == "duplicate_source":
            second["safe_source"] = first["safe_source"]
        items.append(second)

    with pytest.raises(RetrievalAdapterError) as caught:
        map_product_response(
            profile,
            {"results": items},
            top_k=2,
            compatibility=compatibility(profile),
        )
    assert_category(caught, category)


def test_negotiated_optional_field_is_required_and_unnegotiated_field_is_ignored() -> None:
    profile = make_profile(
        score_semantics="unscored",
        optional_feature_flags={
            "keyword_metadata": False,
            "title": False,
            "query_id_echo": False,
        },
    )
    item = product_item()
    item.pop("relevance")
    response = map_product_response(
        profile,
        {"results": [item]},
        top_k=1,
        compatibility=compatibility(profile, ()),
    )
    assert response.results[0].title == "not_provided"
    assert response.results[0].matched_keywords == []

    requested_profile = make_profile()
    item.pop("display_title")
    with pytest.raises(RetrievalAdapterError) as caught:
        map_product_response(
            requested_profile,
            {"results": [item]},
            top_k=1,
            compatibility=compatibility(requested_profile),
        )
    assert_category(caught, CompatibilityErrorCategory.RESPONSE_MAPPING_ERROR)


def test_negotiated_query_id_echo_must_match_and_is_not_retained() -> None:
    profile = make_profile(
        optional_feature_flags={
            "keyword_metadata": True,
            "title": True,
            "query_id_echo": True,
        }
    )
    negotiated = compatibility(
        profile, ("matched_keywords", "query_id_echo", "score", "title")
    )
    response = map_product_response(
        profile,
        {"results": [product_item()], "echo_request_id": "query-001"},
        top_k=1,
        compatibility=negotiated,
        expected_query_id="query-001",
    )
    assert "query-001" not in repr(response)

    for product_echo in (None, "query-002"):
        payload: dict[str, object] = {"results": [product_item()]}
        if product_echo is not None:
            payload["echo_request_id"] = product_echo
        with pytest.raises(RetrievalAdapterError) as caught:
            map_product_response(
                profile,
                payload,
                top_k=1,
                compatibility=negotiated,
                expected_query_id="query-001",
            )
        assert_category(caught, CompatibilityErrorCategory.CAPABILITY_MISMATCH)


def test_metadata_allowlist_and_safe_mapping_summary() -> None:
    profile = make_profile()
    marker = "private-query-marker"
    response = map_product_response(
        profile,
        {"results": [product_item()]},
        top_k=1,
        compatibility=compatibility(profile),
    )
    rendered = repr(response) + str(response)
    assert marker not in rendered
    assert "synthetic-source-001" not in rendered
    assert "result_count=1" in rendered

    with pytest.raises(RetrievalAdapterError) as caught:
        map_product_response(
            profile,
            {"results": [product_item(safe_metadata={"private_path": "C:/secret"})]},
            top_k=1,
            compatibility=compatibility(profile),
        )
    assert_category(caught, CompatibilityErrorCategory.INVALID_MAPPED_RESPONSE)


def test_profile_mismatch_fails_at_capability_boundary_without_raw_values() -> None:
    profile = make_profile()
    mismatch = CompatibilityResult(
        profile_id="other_profile",
        protocol_status=ProtocolStatus.EXACT,
        health_status=HealthStatus.HEALTHY,
        required_capabilities_satisfied=True,
        enabled_optional_capabilities=(),
    )
    marker = "private-query-marker"
    with pytest.raises(RetrievalAdapterError) as caught:
        map_product_response(
            profile,
            {"results": [product_item(display_title=marker)]},
            top_k=1,
            compatibility=mismatch,
        )
    assert_category(caught, CompatibilityErrorCategory.CAPABILITY_MISMATCH)
    assert marker not in str(caught.value)
