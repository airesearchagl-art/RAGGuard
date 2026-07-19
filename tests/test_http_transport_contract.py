from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragguard.http_contract import (
    DEFAULT_HTTP_RESPONSE_SIZE_LIMIT,
    HTTP_JSON_CONTENT_TYPE,
    HTTP_REQUEST_SIZE_LIMIT,
    MAX_HTTP_RESPONSE_SIZE_LIMIT,
    HTTPRetrievalRequest,
    HTTPTransportErrorCategory,
    LocalHTTPEndpoint,
    LoopbackResolutionContract,
    http_transport_error,
    parse_local_http_endpoint,
    parse_http_retrieval_response,
    response_read_limit,
)
from ragguard.retrieval import RetrievalAdapterError, load_local_retrieval_config


def _endpoint(**overrides: object) -> LocalHTTPEndpoint:
    values: dict[str, object] = {
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 8765,
        "path": "/retrieve",
        "connect_timeout": 1.0,
        "read_timeout": 2.0,
        "total_timeout": 3.0,
    }
    values.update(overrides)
    return LocalHTTPEndpoint(**values)  # type: ignore[arg-type]


def _response_body(**result_overrides: object) -> bytes:
    result: dict[str, object] = {
        "rank": 1,
        "document_id": "synthetic-doc-001",
        "score": 1.0,
        "title": "Synthetic Document",
        "source_id": "synthetic-source-001",
        "matched_keywords": ["synthetic"],
        "adapter_metadata": {"transport": "loopback_http"},
    }
    result.update(result_overrides)
    return json.dumps({"results": [result]}).encode("utf-8")


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_http_endpoint_accepts_literal_loopback(host: str) -> None:
    endpoint = _endpoint(host=host)

    assert endpoint.host == host
    assert endpoint.scheme == "http"
    assert endpoint.response_size_limit == DEFAULT_HTTP_RESPONSE_SIZE_LIMIT


def test_http_endpoint_accepts_only_explicitly_allowlisted_hostname() -> None:
    endpoint = _endpoint(
        host="localhost",
        allowlisted_hostnames=frozenset({"localhost"}),
    )

    assert endpoint.host == "localhost"

    with pytest.raises(RetrievalAdapterError, match="external_host_rejected"):
        _endpoint(host="localhost")


@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0",
        "::",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.10",
        "8.8.8.8",
        "example.invalid",
    ],
)
def test_http_endpoint_rejects_non_loopback_hosts(host: str) -> None:
    with pytest.raises(RetrievalAdapterError, match="external_host_rejected") as exc_info:
        _endpoint(host=host)

    assert host not in str(exc_info.value)


@pytest.mark.parametrize(
    ("overrides", "category"),
    [
        ({"scheme": "https"}, "invalid_endpoint"),
        ({"host": "*"}, "invalid_endpoint"),
        ({"host": "user@127.0.0.1"}, "invalid_endpoint"),
        ({"path": "/retrieve?mode=unsafe"}, "invalid_endpoint"),
        ({"path": "/retrieve#fragment"}, "invalid_endpoint"),
        ({"path": "/../private"}, "invalid_endpoint"),
        ({"port": True}, "invalid_endpoint"),
        ({"port": 0}, "invalid_endpoint"),
    ],
)
def test_http_endpoint_rejects_unsafe_components(
    overrides: dict[str, object],
    category: str,
) -> None:
    with pytest.raises(RetrievalAdapterError, match=category):
        _endpoint(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"connect_timeout": 0},
        {"connect_timeout": True},
        {"read_timeout": float("inf")},
        {"total_timeout": 0},
        {"connect_timeout": 4, "total_timeout": 3},
        {"read_timeout": 4, "total_timeout": 3},
        {"response_size_limit": 0},
        {"response_size_limit": MAX_HTTP_RESPONSE_SIZE_LIMIT + 1},
    ],
)
def test_http_endpoint_rejects_invalid_timeout_and_size_values(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(RetrievalAdapterError):
        _endpoint(**overrides)


def test_loopback_resolution_requires_all_addresses_and_peer_to_be_loopback() -> None:
    resolution = LoopbackResolutionContract(
        resolved_addresses=["127.0.0.1", "::1"],
        peer_address="127.0.0.1",
    )

    assert resolution.resolved_addresses == ("127.0.0.1", "::1")

    with pytest.raises(RetrievalAdapterError, match="external_host_rejected"):
        LoopbackResolutionContract(
            resolved_addresses=["127.0.0.1", "192.168.1.10"],
            peer_address="127.0.0.1",
        )
    with pytest.raises(RetrievalAdapterError, match="external_host_rejected"):
        LoopbackResolutionContract(
            resolved_addresses=["127.0.0.1"],
            peer_address="127.0.0.2",
        )
    with pytest.raises(RetrievalAdapterError, match="invalid_endpoint"):
        LoopbackResolutionContract(
            resolved_addresses=["127.0.0.1"],
            peer_address="127.0.0.1",
            resolved_immediately_before_connect=False,
        )


def test_http_request_is_bounded_deterministic_json() -> None:
    request = HTTPRetrievalRequest(
        query="synthetic question",
        top_k=5,
        query_id="q-001",
        capability_version="v1",
    )

    encoded = request.to_json_bytes()

    assert len(encoded) <= HTTP_REQUEST_SIZE_LIMIT
    assert json.loads(encoded) == {
        "capability_version": "v1",
        "query": "synthetic question",
        "query_id": "q-001",
        "top_k": 5,
    }
    assert HTTP_JSON_CONTENT_TYPE == "application/json"


def test_http_request_rejects_unknown_fields_and_oversized_query_safely() -> None:
    secret_query = "sensitive-query-" + "x" * 4096

    with pytest.raises(RetrievalAdapterError, match="invalid_response") as query_error:
        HTTPRetrievalRequest(query=secret_query, top_k=1)
    with pytest.raises(RetrievalAdapterError, match="invalid_response"):
        HTTPRetrievalRequest.from_mapping(
            {"query": "synthetic", "top_k": 1, "credential": "private"}
        )

    assert secret_query not in str(query_error.value)
    assert secret_query not in repr(HTTPRetrievalRequest(query="safe", top_k=1))


def test_http_response_parses_known_bounded_fields() -> None:
    response = parse_http_retrieval_response(
        _response_body(),
        status_code=200,
        content_type="application/json; charset=utf-8",
        top_k=1,
    )

    assert len(response.results) == 1
    assert response.results[0].document_id == "synthetic-doc-001"
    assert response.results[0].source_id == "synthetic-source-001"
    assert response.results[0].metadata == {"transport": "loopback_http"}


@pytest.mark.parametrize(
    ("kwargs", "category"),
    [
        ({"status_code": 302}, "invalid_status"),
        ({"status_code": 500}, "invalid_status"),
        ({"content_type": "text/plain"}, "invalid_content_type"),
        ({"content_type": "application/json; charset=shift_jis"}, "invalid_content_type"),
    ],
)
def test_http_response_rejects_status_and_content_type(
    kwargs: dict[str, object],
    category: str,
) -> None:
    values: dict[str, object] = {
        "body": _response_body(),
        "status_code": 200,
        "content_type": "application/json",
        "top_k": 1,
    }
    values.update(kwargs)
    with pytest.raises(RetrievalAdapterError, match=category):
        parse_http_retrieval_response(**values)  # type: ignore[arg-type]


def test_http_response_limit_plus_one_rejects_before_parse() -> None:
    limit = 64
    oversized_invalid_json = b"{" + b"x" * limit

    assert response_read_limit(limit) == limit + 1
    with pytest.raises(RetrievalAdapterError, match="response_too_large"):
        parse_http_retrieval_response(
            oversized_invalid_json,
            status_code=200,
            content_type="application/json",
            top_k=1,
            response_size_limit=limit,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"results": [], "unknown": True},
        {"results": [{"rank": 1, "document_id": "synthetic-doc-001"}]},
        {
            "results": [
                {
                    "rank": 1,
                    "document_id": "synthetic-doc-001",
                    "score": 1,
                    "title": "Synthetic",
                    "source_id": "synthetic-source-001",
                    "unknown": "value",
                }
            ]
        },
        {
            "results": [
                {
                    "rank": 1,
                    "document_id": "synthetic-doc-001",
                    "score": 1,
                    "title": "Synthetic",
                    "source_id": "synthetic-source-001",
                    "adapter_metadata": {"credential": "private"},
                }
            ]
        },
    ],
)
def test_http_response_rejects_unknown_or_incomplete_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(RetrievalAdapterError, match="invalid_response"):
        parse_http_retrieval_response(
            json.dumps(payload).encode("utf-8"),
            status_code=200,
            content_type="application/json",
            top_k=1,
        )


def test_http_response_rejects_more_than_top_k() -> None:
    first = json.loads(_response_body())["results"][0]
    second = dict(first, rank=2, document_id="synthetic-doc-002")
    body = json.dumps({"results": [first, second]}).encode("utf-8")

    with pytest.raises(RetrievalAdapterError, match="invalid_response"):
        parse_http_retrieval_response(
            body,
            status_code=200,
            content_type="application/json",
            top_k=1,
        )


def test_http_error_categories_are_bounded_and_do_not_expose_sensitive_values() -> None:
    sensitive_values = (
        "http://user:password@127.0.0.1/private?token=secret",
        "private query body",
        "Authorization: Bearer secret",
        "Cookie: session=secret",
        "C:/private/source.md",
    )

    for category in HTTPTransportErrorCategory:
        error = http_transport_error(category)
        assert str(error) == category.value
        assert all(value not in str(error) for value in sensitive_values)


def test_loopback_http_config_maps_to_validated_endpoint(tmp_path: Path) -> None:
    config_path = tmp_path / "loopback.json"
    config_path.write_text(
        json.dumps(
            {
                "transport_type": "loopback_http",
                "endpoint": "http://127.0.0.1:8765/retrieve",
                "connect_timeout": 1.0,
                "read_timeout": 2.0,
                "total_timeout": 3.0,
                "default_top_k": 7,
                "response_size_limit": 65_536,
                "capabilities": {
                    "ranked_results": True,
                    "matched_keywords": True,
                    "filters": False,
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_local_retrieval_config(config_path)

    assert config.transport_type == "loopback_http"
    assert config.default_top_k == 7
    assert config.http_endpoint is not None
    assert config.http_endpoint.host == "127.0.0.1"
    assert config.http_endpoint.port == 8765
    assert config.http_endpoint.path == "/retrieve"


def test_loopback_http_config_accepts_only_explicitly_allowlisted_hostname(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "loopback.yaml"
    config_path.write_text(
        "\n".join(
            [
                "transport_type: loopback_http",
                "endpoint: http://localhost:8765/retrieve",
                "connect_timeout: 1",
                "read_timeout: 2",
                "total_timeout: 3",
                "allowlisted_hostnames:",
                "  - localhost",
            ]
        ),
        encoding="utf-8",
    )

    config = load_local_retrieval_config(config_path)

    assert config.http_endpoint is not None
    assert config.http_endpoint.host == "localhost"

    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "allowlisted_hostnames:\n  - localhost", "allowlisted_hostnames: []"
        ),
        encoding="utf-8",
    )
    with pytest.raises(RetrievalAdapterError, match="external_host_rejected"):
        load_local_retrieval_config(config_path)


@pytest.mark.parametrize(
    "field",
    ["auth", "token", "cookie", "proxy", "redirect", "retry", "credential"],
)
def test_loopback_http_config_rejects_security_sensitive_and_unknown_fields(
    tmp_path: Path,
    field: str,
) -> None:
    config_path = tmp_path / "private.json"
    config_path.write_text(
        json.dumps(
            {
                "transport_type": "loopback_http",
                "endpoint": "http://127.0.0.1:8765/retrieve",
                "connect_timeout": 1,
                "read_timeout": 1,
                "total_timeout": 1,
                field: "private-value",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RetrievalAdapterError) as exc_info:
        load_local_retrieval_config(config_path)

    assert "private-value" not in str(exc_info.value)
    assert str(config_path) not in str(exc_info.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:8765/retrieve",
        "http://127.0.0.1:8765/retrieve?query=private",
        "http://127.0.0.1:8765/retrieve#private",
        "http://user:secret@127.0.0.1:8765/retrieve",
        "http://127.0.0.1:8765/../private",
        "http://127.0.0.1:8765/%2e%2e/private",
        "http://192.168.1.10:8765/retrieve",
        "http://0.0.0.0:8765/retrieve",
    ],
)
def test_http_config_endpoint_parser_rejects_unsafe_values_without_disclosure(
    endpoint: str,
) -> None:
    with pytest.raises(RetrievalAdapterError) as exc_info:
        parse_local_http_endpoint(
            endpoint,
            connect_timeout=1,
            read_timeout=1,
            total_timeout=1,
        )

    assert endpoint not in str(exc_info.value)
