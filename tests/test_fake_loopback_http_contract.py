from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from ragguard.http_contract import (
    HTTP_JSON_CONTENT_TYPE,
    HTTP_REQUEST_SIZE_LIMIT,
    MAX_HTTP_RESPONSE_SIZE_LIMIT,
    HTTPRetrievalRequest,
    HTTPTransportErrorCategory,
    LocalHTTPEndpoint,
    LoopbackResolutionContract,
    http_transport_error,
    parse_http_retrieval_response,
    response_read_limit,
)
from ragguard.retrieval import (
    RetrievalAdapterError,
    normalize_local_response,
)


@dataclass(frozen=True)
class _ScriptedResponse:
    body: bytes
    status: int = 200
    content_type: str = HTTP_JSON_CONTENT_TYPE
    delay_seconds: float = 0.0
    location: str | None = None


@dataclass(frozen=True)
class _RecordedRequest:
    method: str
    path: str
    content_type: str
    body: bytes


class _FakeLoopbackServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        response: _ScriptedResponse,
    ) -> None:
        self.scripted_response = response
        self.requests: list[_RecordedRequest] = []
        super().__init__(address, _FakeLoopbackHandler)


class _FakeIPv6LoopbackServer(_FakeLoopbackServer):
    address_family = socket.AF_INET6


class _FakeLoopbackHandler(BaseHTTPRequestHandler):
    server: _FakeLoopbackServer

    def do_POST(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            self._send_validation_error()
            return
        if not 0 <= content_length <= HTTP_REQUEST_SIZE_LIMIT:
            self._send_validation_error()
            return

        body = self.rfile.read(content_length)
        content_type = self.headers.get("Content-Type", "")
        self.server.requests.append(
            _RecordedRequest(
                method="POST",
                path=self.path,
                content_type=content_type,
                body=body,
            )
        )
        try:
            if content_type != HTTP_JSON_CONTENT_TYPE:
                raise ValueError
            payload = json.loads(body.decode("utf-8"))
            HTTPRetrievalRequest.from_mapping(payload)
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, RetrievalAdapterError):
            self._send_validation_error()
            return

        response = self.server.scripted_response
        if response.delay_seconds:
            time.sleep(response.delay_seconds)
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        if response.location is not None:
            self.send_header("Location", response.location)
        self.end_headers()
        try:
            self.wfile.write(response.body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_validation_error(self) -> None:
        body = b'{"error":"invalid_request"}'
        self.send_response(400)
        self.send_header("Content-Type", HTTP_JSON_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def _running_server(
    response: _ScriptedResponse,
    *,
    ipv6: bool = False,
) -> Iterator[_FakeLoopbackServer]:
    server_type = _FakeIPv6LoopbackServer if ipv6 else _FakeLoopbackServer
    host = "::1" if ipv6 else "127.0.0.1"
    server = server_type((host, 0), response)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
        if thread.is_alive():
            raise AssertionError("fake loopback server did not stop")


def _response_body(
    *,
    results: list[dict[str, Any]] | None = None,
    extra_top_level: dict[str, Any] | None = None,
) -> bytes:
    if results is None:
        results = [
            {
                "rank": 1,
                "document_id": "synthetic-doc-001",
                "score": 1.0,
                "title": "Synthetic Document",
                "source_id": "synthetic-source-001",
                "matched_keywords": ["synthetic"],
                "adapter_metadata": {"transport": "loopback_http"},
            }
        ]
    payload: dict[str, Any] = {"results": results}
    if extra_top_level:
        payload.update(extra_top_level)
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _endpoint(
    server: _FakeLoopbackServer,
    *,
    host: str = "127.0.0.1",
    response_size_limit: int | None = None,
    timeout: float = 1.0,
) -> LocalHTTPEndpoint:
    values: dict[str, Any] = {
        "scheme": "http",
        "host": host,
        "port": server.server_address[1],
        "path": "/retrieve",
        "connect_timeout": timeout,
        "read_timeout": timeout,
        "total_timeout": timeout,
    }
    if response_size_limit is not None:
        values["response_size_limit"] = response_size_limit
    return LocalHTTPEndpoint(**values)


_ConnectionFactory = Callable[[str, int, float], http.client.HTTPConnection]


def _test_only_round_trip(
    endpoint: LocalHTTPEndpoint,
    request: HTTPRetrievalRequest,
    *,
    resolved_addresses: tuple[str, ...] | None = None,
    peer_override: str | None = None,
    resolved_immediately_before_connect: bool = True,
    connection_factory: _ConnectionFactory | None = None,
):
    """Exercise the Phase A contract over loopback without adding a production client."""
    factory = connection_factory or (
        lambda host, port, timeout: http.client.HTTPConnection(
            host,
            port,
            timeout=timeout,
        )
    )
    connection: http.client.HTTPConnection | None = None
    started = time.monotonic()
    try:
        connection = factory(
            endpoint.host,
            endpoint.port,
            min(endpoint.connect_timeout, endpoint.total_timeout),
        )
        connection.connect()
        if connection.sock is None:
            raise http_transport_error(HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED)
        peer = peer_override or connection.sock.getpeername()[0]
        addresses = resolved_addresses or (endpoint.host,)
        LoopbackResolutionContract(
            resolved_addresses=addresses,
            peer_address=peer,
            resolved_immediately_before_connect=resolved_immediately_before_connect,
        )
        remaining = endpoint.total_timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise http_transport_error(HTTPTransportErrorCategory.TIMEOUT)
        connection.sock.settimeout(min(endpoint.read_timeout, remaining))
        connection.request(
            "POST",
            endpoint.path,
            body=request.to_json_bytes(),
            headers={"Content-Type": HTTP_JSON_CONTENT_TYPE},
        )
        response = connection.getresponse()
        body = response.read(response_read_limit(endpoint.response_size_limit))
        if time.monotonic() - started > endpoint.total_timeout:
            raise http_transport_error(HTTPTransportErrorCategory.TIMEOUT)
        return parse_http_retrieval_response(
            body,
            status_code=response.status,
            content_type=response.getheader("Content-Type", ""),
            top_k=request.top_k,
            response_size_limit=endpoint.response_size_limit,
        )
    except RetrievalAdapterError:
        raise
    except (TimeoutError, socket.timeout):
        raise http_transport_error(HTTPTransportErrorCategory.TIMEOUT) from None
    except ConnectionRefusedError:
        raise http_transport_error(HTTPTransportErrorCategory.CONNECTION_REFUSED) from None
    except OSError:
        raise http_transport_error(HTTPTransportErrorCategory.CONNECTION_REFUSED) from None
    except http.client.HTTPException:
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE) from None
    finally:
        if connection is not None:
            connection.close()


def _raw_post(
    server: _FakeLoopbackServer,
    body: bytes,
    *,
    content_type: str = HTTP_JSON_CONTENT_TYPE,
) -> int:
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        server.server_address[1],
        timeout=1.0,
    )
    try:
        connection.request(
            "POST",
            "/retrieve",
            body=body,
            headers={"Content-Type": content_type},
        )
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def test_fake_loopback_round_trip_validates_request_and_normalizes_results() -> None:
    body = _response_body()
    with _running_server(_ScriptedResponse(body=body)) as server:
        endpoint = _endpoint(server)
        response = _test_only_round_trip(
            endpoint,
            HTTPRetrievalRequest(
                query="synthetic question",
                top_k=1,
                query_id="q-001",
                capability_version="v1",
            ),
        )

    ranked = normalize_local_response(
        response,
        top_k=1,
        response_size_limit=endpoint.response_size_limit,
    )
    assert [(item.rank, item.document_id) for item in ranked] == [
        (1, "synthetic-doc-001")
    ]
    assert len(server.requests) == 1
    recorded = server.requests[0]
    assert recorded.method == "POST"
    assert recorded.path == "/retrieve"
    assert recorded.content_type == HTTP_JSON_CONTENT_TYPE
    assert json.loads(recorded.body)["query_id"] == "q-001"


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"not-json", HTTP_JSON_CONTENT_TYPE),
        (b'{"query":"synthetic","top_k":1,"unknown":true}', HTTP_JSON_CONTENT_TYPE),
        (b'{"query":"synthetic","top_k":1}', "text/plain"),
    ],
)
def test_fake_server_rejects_invalid_request_bodies(
    body: bytes,
    content_type: str,
) -> None:
    with _running_server(_ScriptedResponse(body=_response_body())) as server:
        status = _raw_post(server, body, content_type=content_type)

    assert status == 400


@pytest.mark.parametrize(
    ("script", "category"),
    [
        (_ScriptedResponse(body=b"", status=302, location="http://127.0.0.1/other"), "invalid_status"),
        (_ScriptedResponse(body=b"", status=503), "invalid_status"),
        (_ScriptedResponse(body=_response_body(), content_type="text/plain"), "invalid_content_type"),
        (_ScriptedResponse(body=b"\xff"), "invalid_response"),
        (_ScriptedResponse(body=b"not-json"), "invalid_response"),
        (_ScriptedResponse(body=_response_body(extra_top_level={"unknown": True})), "invalid_response"),
        (_ScriptedResponse(body=b'{"results":[{"rank":1}]}'), "invalid_response"),
    ],
)
def test_fake_loopback_rejects_invalid_http_responses(
    script: _ScriptedResponse,
    category: str,
) -> None:
    with _running_server(script) as server:
        with pytest.raises(RetrievalAdapterError, match=category) as exc_info:
            _test_only_round_trip(
                _endpoint(server),
                HTTPRetrievalRequest(query="private-query-value", top_k=1),
            )

    message = str(exc_info.value)
    assert message == category
    assert "private-query-value" not in message
    assert "127.0.0.1" not in message
    decoded_body = script.body.decode("utf-8", errors="ignore")
    if decoded_body:
        assert decoded_body not in message
    assert len(server.requests) == 1


def test_fake_loopback_does_not_follow_redirects_or_retry() -> None:
    script = _ScriptedResponse(
        body=b"redirect-body-private",
        status=307,
        location="http://127.0.0.1:1/private",
    )
    with _running_server(script) as server:
        with pytest.raises(RetrievalAdapterError, match="invalid_status"):
            _test_only_round_trip(
                _endpoint(server),
                HTTPRetrievalRequest(query="synthetic", top_k=1),
            )

    assert len(server.requests) == 1


@pytest.mark.parametrize(("result_count", "top_k"), [(2, 1), (101, 100)])
def test_fake_loopback_rejects_result_count_above_contract_limit(
    result_count: int,
    top_k: int,
) -> None:
    first = json.loads(_response_body())["results"][0]
    results = [
        dict(
            first,
            rank=index,
            document_id=f"synthetic-doc-{index:03d}",
        )
        for index in range(1, result_count + 1)
    ]
    with _running_server(
        _ScriptedResponse(body=_response_body(results=results))
    ) as server:
        with pytest.raises(RetrievalAdapterError, match="invalid_response"):
            _test_only_round_trip(
                _endpoint(server),
                HTTPRetrievalRequest(query="synthetic", top_k=top_k),
            )


def test_fake_loopback_accepts_response_at_exact_configured_limit() -> None:
    body = _response_body()
    with _running_server(_ScriptedResponse(body=body)) as server:
        response = _test_only_round_trip(
            _endpoint(server, response_size_limit=len(body)),
            HTTPRetrievalRequest(query="synthetic", top_k=1),
        )

    assert response.results[0].document_id == "synthetic-doc-001"


@pytest.mark.parametrize("extra_bytes", [1, MAX_HTTP_RESPONSE_SIZE_LIMIT + 1])
def test_fake_loopback_rejects_oversized_response_before_parse(
    extra_bytes: int,
) -> None:
    if extra_bytes == 1:
        limit = len(_response_body())
        body = _response_body() + b" "
    else:
        limit = MAX_HTTP_RESPONSE_SIZE_LIMIT
        body = b"private-raw-response" + b"x" * (
            MAX_HTTP_RESPONSE_SIZE_LIMIT + 1 - len(b"private-raw-response")
        )
    with _running_server(_ScriptedResponse(body=body)) as server:
        with pytest.raises(RetrievalAdapterError, match="response_too_large") as exc_info:
            _test_only_round_trip(
                _endpoint(server, response_size_limit=limit),
                HTTPRetrievalRequest(query="synthetic", top_k=1),
            )

    assert str(exc_info.value) == "response_too_large"
    assert "private-raw-response" not in str(exc_info.value)


def test_fake_loopback_rejects_unverified_or_changed_peer_before_request() -> None:
    with _running_server(_ScriptedResponse(body=_response_body())) as server:
        endpoint = _endpoint(server)
        with pytest.raises(RetrievalAdapterError, match="external_host_rejected"):
            _test_only_round_trip(
                endpoint,
                HTTPRetrievalRequest(query="synthetic", top_k=1),
                peer_override="192.0.2.10",
            )
        with pytest.raises(RetrievalAdapterError, match="external_host_rejected"):
            _test_only_round_trip(
                endpoint,
                HTTPRetrievalRequest(query="synthetic", top_k=1),
                resolved_addresses=("127.0.0.1", "192.0.2.10"),
            )
        with pytest.raises(RetrievalAdapterError, match="invalid_endpoint"):
            _test_only_round_trip(
                endpoint,
                HTTPRetrievalRequest(query="synthetic", top_k=1),
                resolved_immediately_before_connect=False,
            )

    assert server.requests == []


def test_fake_ipv6_loopback_round_trip_when_available() -> None:
    try:
        context = _running_server(_ScriptedResponse(body=_response_body()), ipv6=True)
        with context as server:
            response = _test_only_round_trip(
                _endpoint(server, host="::1"),
                HTTPRetrievalRequest(query="synthetic", top_k=1),
            )
    except OSError as exc:
        pytest.skip(f"IPv6 loopback is unavailable: {type(exc).__name__}")

    assert response.results[0].document_id == "synthetic-doc-001"


class _ConnectionRefusedConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        raise ConnectionRefusedError("private refusal detail")


def test_loopback_connection_refused_maps_to_safe_category() -> None:
    endpoint = LocalHTTPEndpoint(
        scheme="http",
        host="127.0.0.1",
        port=8765,
        path="/retrieve",
        connect_timeout=0.2,
        read_timeout=0.2,
        total_timeout=0.2,
    )
    attempts = 0

    def factory(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
        nonlocal attempts
        attempts += 1
        return _ConnectionRefusedConnection(host, port, timeout=timeout)

    with pytest.raises(RetrievalAdapterError, match="connection_refused") as exc_info:
        _test_only_round_trip(
            endpoint,
            HTTPRetrievalRequest(query="private-query", top_k=1),
            connection_factory=factory,
        )

    assert attempts == 1
    assert str(exc_info.value) == "connection_refused"


class _ConnectTimeoutConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        raise TimeoutError("private connect detail")


def test_connect_timeout_maps_safely_without_network_retry() -> None:
    endpoint = LocalHTTPEndpoint(
        scheme="http",
        host="127.0.0.1",
        port=8765,
        path="/retrieve",
        connect_timeout=0.1,
        read_timeout=0.1,
        total_timeout=0.1,
    )
    attempts = 0

    def factory(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
        nonlocal attempts
        attempts += 1
        return _ConnectTimeoutConnection(host, port, timeout=timeout)

    with pytest.raises(RetrievalAdapterError, match="timeout") as exc_info:
        _test_only_round_trip(
            endpoint,
            HTTPRetrievalRequest(query="private-query", top_k=1),
            connection_factory=factory,
        )

    assert attempts == 1
    assert str(exc_info.value) == "timeout"


def test_read_and_total_timeout_map_safely_without_retry() -> None:
    with _running_server(
        _ScriptedResponse(body=_response_body(), delay_seconds=0.2)
    ) as server:
        with pytest.raises(RetrievalAdapterError, match="timeout") as exc_info:
            _test_only_round_trip(
                _endpoint(server, timeout=0.05),
                HTTPRetrievalRequest(query="private-timeout-query", top_k=1),
            )

    assert len(server.requests) == 1
    assert str(exc_info.value) == "timeout"
    assert "private-timeout-query" not in str(exc_info.value)
