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
from pathlib import Path
from typing import Any

import pytest
import yaml

from ragguard.cli import main
from ragguard.http_client import (
    BoundedLoopbackHTTPClient,
    resolve_loopback_addresses,
)
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
from ragguard.http_transport import LoopbackHTTPLocalRetrievalTransport
from ragguard.retrieval import (
    LocalRAGRetrievalAdapter,
    LocalRetrievalConfig,
    LocalRetrievalRequest,
    LocalRetrievalTransport,
    RetrievalAdapterError,
    load_local_retrieval_config,
    normalize_local_response,
)


@dataclass(frozen=True)
class _ScriptedResponse:
    body: bytes
    status: int = 200
    content_type: str = HTTP_JSON_CONTENT_TYPE
    delay_seconds: float = 0.0
    body_delay_seconds: float = 0.0
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
        response: _ScriptedResponse | Callable[[_RecordedRequest], _ScriptedResponse],
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
        if callable(response):
            response = response(self.server.requests[-1])
        if response.delay_seconds:
            time.sleep(response.delay_seconds)
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        if response.location is not None:
            self.send_header("Location", response.location)
        self.end_headers()
        if response.body_delay_seconds:
            time.sleep(response.body_delay_seconds)
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
    response: _ScriptedResponse | Callable[[_RecordedRequest], _ScriptedResponse],
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


class _UnsafeAdapterErrorConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        raise RetrievalAdapterError("private raw adapter detail")


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


def test_bounded_client_ipv4_round_trip_returns_ranked_results() -> None:
    with _running_server(_ScriptedResponse(body=_response_body())) as server:
        results = BoundedLoopbackHTTPClient(_endpoint(server)).retrieve(
            HTTPRetrievalRequest(query="synthetic", top_k=1)
        )

    assert [(result.rank, result.document_id) for result in results] == [
        (1, "synthetic-doc-001")
    ]
    assert results[0].source_path == "synthetic-source-001"
    assert len(server.requests) == 1
    assert server.requests[0].method == "POST"
    assert server.requests[0].content_type == HTTP_JSON_CONTENT_TYPE


def test_bounded_client_ipv6_round_trip_when_available() -> None:
    try:
        context = _running_server(_ScriptedResponse(body=_response_body()), ipv6=True)
        with context as server:
            results = BoundedLoopbackHTTPClient(
                _endpoint(server, host="::1")
            ).retrieve(HTTPRetrievalRequest(query="synthetic", top_k=1))
    except OSError as exc:
        pytest.skip(f"IPv6 loopback is unavailable: {type(exc).__name__}")

    assert results[0].document_id == "synthetic-doc-001"


def test_bounded_client_resolves_allowlisted_hostname_for_each_request() -> None:
    calls: list[tuple[str, int]] = []
    with _running_server(_ScriptedResponse(body=_response_body())) as server:
        endpoint = LocalHTTPEndpoint(
            scheme="http",
            host="localhost",
            port=server.server_address[1],
            path="/retrieve",
            connect_timeout=1.0,
            read_timeout=1.0,
            total_timeout=1.0,
            allowlisted_hostnames=frozenset({"localhost"}),
        )

        def resolver(host: str, port: int) -> tuple[str, ...]:
            calls.append((host, port))
            return ("127.0.0.1",)

        client = BoundedLoopbackHTTPClient(endpoint, resolver=resolver)
        first = client.retrieve(HTTPRetrievalRequest(query="first", top_k=1))
        second = client.retrieve(HTTPRetrievalRequest(query="second", top_k=1))

    assert first == second
    assert calls == [
        ("localhost", endpoint.port),
        ("localhost", endpoint.port),
    ]
    assert len(server.requests) == 2


@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1", "192.168.1.10"),
        ("10.0.0.10",),
        ("203.0.113.10",),
        (),
    ],
)
def test_bounded_client_rejects_non_loopback_resolution_before_connect(
    addresses: tuple[str, ...],
) -> None:
    endpoint = LocalHTTPEndpoint(
        scheme="http",
        host="localhost",
        port=8765,
        path="/retrieve",
        connect_timeout=1.0,
        read_timeout=1.0,
        total_timeout=1.0,
        allowlisted_hostnames=frozenset({"localhost"}),
    )
    connection_attempts = 0

    def factory(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
        nonlocal connection_attempts
        connection_attempts += 1
        return http.client.HTTPConnection(host, port, timeout=timeout)

    with pytest.raises(RetrievalAdapterError, match="external_host_rejected"):
        BoundedLoopbackHTTPClient(
            endpoint,
            resolver=lambda host, port: addresses,
            connection_factory=factory,
        ).retrieve(HTTPRetrievalRequest(query="private-query", top_k=1))

    assert connection_attempts == 0


def test_default_resolver_rejects_mixed_addresses_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mixed_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 8765)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.168.1.10", 8765)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mixed_getaddrinfo)

    with pytest.raises(RetrievalAdapterError, match="external_host_rejected"):
        resolve_loopback_addresses("localhost", 8765)


def test_default_resolver_maps_timeout_without_raw_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timed_out_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        raise socket.timeout("private resolver detail")

    monkeypatch.setattr(socket, "getaddrinfo", timed_out_getaddrinfo)

    with pytest.raises(RetrievalAdapterError, match="timeout") as exc_info:
        resolve_loopback_addresses("localhost", 8765)

    assert str(exc_info.value) == "timeout"


class _PeerSocket:
    def __init__(self, peer: str | None) -> None:
        self._peer = peer
        self.closed = False

    def getpeername(self) -> tuple[str, int]:
        if self._peer is None:
            raise OSError("private peer detail")
        return self._peer, 8765

    def close(self) -> None:
        self.closed = True


class _PeerConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, timeout: float, peer: str | None) -> None:
        super().__init__(host, port, timeout=timeout)
        self.peer_socket = _PeerSocket(peer)

    def connect(self) -> None:
        self.sock = self.peer_socket  # type: ignore[assignment]


@pytest.mark.parametrize("peer", ["192.0.2.10", None])
def test_bounded_client_rejects_changed_or_unconfirmed_peer(
    peer: str | None,
) -> None:
    endpoint = LocalHTTPEndpoint(
        scheme="http",
        host="127.0.0.1",
        port=8765,
        path="/retrieve",
        connect_timeout=1.0,
        read_timeout=1.0,
        total_timeout=1.0,
    )
    connections: list[_PeerConnection] = []

    def factory(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
        connection = _PeerConnection(host, port, timeout, peer)
        connections.append(connection)
        return connection

    with pytest.raises(RetrievalAdapterError, match="external_host_rejected"):
        BoundedLoopbackHTTPClient(
            endpoint,
            connection_factory=factory,
        ).retrieve(HTTPRetrievalRequest(query="private-query", top_k=1))

    assert connections[0].peer_socket.closed is True


def test_bounded_client_ignores_environment_proxy_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:9999")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:9999")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:9999")
    with _running_server(_ScriptedResponse(body=_response_body())) as server:
        results = BoundedLoopbackHTTPClient(_endpoint(server)).retrieve(
            HTTPRetrievalRequest(query="synthetic", top_k=1)
        )

    assert results[0].document_id == "synthetic-doc-001"
    assert len(server.requests) == 1


@pytest.mark.parametrize(
    ("script", "category"),
    [
        (_ScriptedResponse(body=b"", status=307, location="http://127.0.0.1:1/private"), "invalid_status"),
        (_ScriptedResponse(body=b"", status=500), "invalid_status"),
        (_ScriptedResponse(body=_response_body(), content_type="text/plain"), "invalid_content_type"),
        (_ScriptedResponse(body=b"not-json"), "invalid_response"),
    ],
)
def test_bounded_client_rejects_invalid_response_without_retry(
    script: _ScriptedResponse,
    category: str,
) -> None:
    connections: list[http.client.HTTPConnection] = []
    with _running_server(script) as server:

        def factory(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
            connection = http.client.HTTPConnection(host, port, timeout=timeout)
            connections.append(connection)
            return connection

        with pytest.raises(RetrievalAdapterError, match=category) as exc_info:
            BoundedLoopbackHTTPClient(
                _endpoint(server),
                connection_factory=factory,
            ).retrieve(
                HTTPRetrievalRequest(query="private-query-value", top_k=1)
            )

    assert str(exc_info.value) == category
    assert "private-query-value" not in str(exc_info.value)
    assert "127.0.0.1" not in str(exc_info.value)
    assert len(server.requests) == 1
    assert len(connections) == 1
    assert connections[0].sock is None


def test_bounded_client_rejects_redirect_before_reading_delayed_body() -> None:
    script = _ScriptedResponse(
        body=b"private-delayed-redirect-body",
        status=302,
        body_delay_seconds=0.2,
        location="http://127.0.0.1:1/private",
    )
    with _running_server(script) as server:
        with pytest.raises(RetrievalAdapterError, match="invalid_status") as exc_info:
            BoundedLoopbackHTTPClient(
                _endpoint(server, timeout=0.05)
            ).retrieve(HTTPRetrievalRequest(query="private-query", top_k=1))

    assert str(exc_info.value) == "invalid_status"
    assert len(server.requests) == 1


def test_bounded_client_accepts_exact_limit_and_rejects_limit_plus_one() -> None:
    body = _response_body()
    with _running_server(_ScriptedResponse(body=body)) as exact_server:
        exact_results = BoundedLoopbackHTTPClient(
            _endpoint(exact_server, response_size_limit=len(body))
        ).retrieve(HTTPRetrievalRequest(query="synthetic", top_k=1))

    with _running_server(_ScriptedResponse(body=body + b" ")) as oversized_server:
        with pytest.raises(
            RetrievalAdapterError,
            match="response_too_large",
        ) as exc_info:
            BoundedLoopbackHTTPClient(
                _endpoint(oversized_server, response_size_limit=len(body))
            ).retrieve(HTTPRetrievalRequest(query="private-query", top_k=1))

    assert exact_results[0].document_id == "synthetic-doc-001"
    assert str(exc_info.value) == "response_too_large"


@pytest.mark.parametrize(
    ("connection_type", "category"),
    [
        (_ConnectionRefusedConnection, "connection_refused"),
        (_ConnectTimeoutConnection, "timeout"),
        (_UnsafeAdapterErrorConnection, "invalid_response"),
    ],
)
def test_bounded_client_maps_connect_errors_without_retry(
    connection_type: type[http.client.HTTPConnection],
    category: str,
) -> None:
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
        return connection_type(host, port, timeout=timeout)

    with pytest.raises(RetrievalAdapterError, match=category) as exc_info:
        BoundedLoopbackHTTPClient(
            endpoint,
            connection_factory=factory,
        ).retrieve(HTTPRetrievalRequest(query="private-query", top_k=1))

    assert attempts == 1
    assert str(exc_info.value) == category


def test_bounded_client_maps_read_timeout_and_closes_connection() -> None:
    connections: list[http.client.HTTPConnection] = []
    with _running_server(
        _ScriptedResponse(body=_response_body(), delay_seconds=0.2)
    ) as server:

        def factory(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
            connection = http.client.HTTPConnection(host, port, timeout=timeout)
            connections.append(connection)
            return connection

        with pytest.raises(RetrievalAdapterError, match="timeout") as exc_info:
            BoundedLoopbackHTTPClient(
                _endpoint(server, timeout=0.05),
                connection_factory=factory,
            ).retrieve(
                HTTPRetrievalRequest(query="private-timeout-query", top_k=1)
            )

    assert str(exc_info.value) == "timeout"
    assert "private-timeout-query" not in str(exc_info.value)
    assert len(server.requests) == 1
    assert connections[0].sock is None


def test_bounded_client_enforces_total_deadline_after_resolution() -> None:
    endpoint = LocalHTTPEndpoint(
        scheme="http",
        host="127.0.0.1",
        port=8765,
        path="/retrieve",
        connect_timeout=1.0,
        read_timeout=1.0,
        total_timeout=1.0,
    )
    clock_values = iter((0.0, 2.0))
    connection_attempts = 0

    def factory(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
        nonlocal connection_attempts
        connection_attempts += 1
        return http.client.HTTPConnection(host, port, timeout=timeout)

    with pytest.raises(RetrievalAdapterError, match="timeout"):
        BoundedLoopbackHTTPClient(
            endpoint,
            resolver=lambda host, port: ("127.0.0.1",),
            connection_factory=factory,
            clock=lambda: next(clock_values),
        ).retrieve(HTTPRetrievalRequest(query="private-query", top_k=1))

    assert connection_attempts == 0


BENCHMARK_FIXTURES = Path(__file__).parent / "fixtures" / "benchmark"


def _write_loopback_config(
    path: Path,
    server: _FakeLoopbackServer,
    **overrides: object,
) -> Path:
    config: dict[str, object] = {
        "transport_type": "loopback_http",
        "endpoint": f"http://127.0.0.1:{server.server_address[1]}/retrieve",
        "connect_timeout": 0.5,
        "read_timeout": 0.5,
        "total_timeout": 1.0,
        "default_top_k": 5,
        "response_size_limit": 262_144,
        "capabilities": {
            "ranked_results": True,
            "matched_keywords": True,
            "filters": False,
        },
    }
    config.update(overrides)
    if path.suffix in {".yaml", ".yml"}:
        path.write_text(yaml.safe_dump(config, sort_keys=True), encoding="utf-8")
    else:
        path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _benchmark_cli_args(output: Path, config: Path) -> list[str]:
    return [
        "benchmark",
        "--corpus",
        str(BENCHMARK_FIXTURES / "corpus"),
        "--queries",
        str(BENCHMARK_FIXTURES / "queries.jsonl"),
        "--output",
        str(output),
        "--adapter",
        "local-rag",
        "--adapter-config",
        str(config),
    ]


def _benchmark_http_response(
    request: _RecordedRequest,
    *,
    first_status: str = "pass",
) -> _ScriptedResponse:
    payload = json.loads(request.body.decode("utf-8"))
    query = payload["query"]
    if query.startswith("Where are sample policy"):
        if first_status == "fail":
            document_id = "sample-faq-001"
            title = "Synthetic FAQ Result"
            source_id = "sample-faq-source"
            keywords = ["fictional support windows"]
        else:
            document_id = "sample-policy-001"
            title = "Synthetic Policy Result"
            source_id = "sample-policy-source"
            keywords = ["sample", "archive"] if first_status == "pass" else ["sample"]
        results = [
            {
                "rank": 1,
                "document_id": document_id,
                "score": 1.0,
                "title": title,
                "source_id": source_id,
                "matched_keywords": keywords,
                "adapter_metadata": {"transport": "loopback_http"},
            }
        ]
    elif query.startswith("What kind of support windows"):
        results = [
            {
                "rank": 1,
                "document_id": "sample-faq-001",
                "score": 1.0,
                "title": "Synthetic FAQ Result",
                "source_id": "sample-faq-source",
                "matched_keywords": ["fictional", "support", "windows"],
                "adapter_metadata": {"transport": "loopback_http"},
            }
        ]
    else:
        results = []
    return _ScriptedResponse(body=_response_body(results=results))


class _RecordingLoopbackHTTPTransport(LoopbackHTTPLocalRetrievalTransport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    def initialize(self, config: LocalRetrievalConfig) -> None:
        self.events.append("initialize")
        super().initialize(config)

    def health_check(self) -> bool:
        self.events.append("health_check")
        return super().health_check()

    def capabilities(self):  # type: ignore[no-untyped-def]
        self.events.append("capabilities")
        return super().capabilities()

    def retrieve(self, request: LocalRetrievalRequest):  # type: ignore[no-untyped-def]
        self.events.append("retrieve")
        return super().retrieve(request)

    def close(self) -> None:
        self.events.append("close")
        super().close()


def test_loopback_http_transport_conforms_and_closes_after_adapter_retrieve(
    tmp_path: Path,
) -> None:
    with _running_server(_benchmark_http_response) as server:
        config = load_local_retrieval_config(
            _write_loopback_config(tmp_path / "loopback.json", server)
        )
        transport = _RecordingLoopbackHTTPTransport()
        query = type(
            "Query",
            (),
            {"question": "Where are sample policy documents stored?", "query_id": "q001"},
        )()
        results = LocalRAGRetrievalAdapter(config, transport).retrieve(query, 5)

    assert isinstance(transport, LocalRetrievalTransport)
    assert transport.events == [
        "initialize",
        "health_check",
        "capabilities",
        "retrieve",
        "close",
    ]
    assert transport.state == "closed"
    assert results[0].document_id == "sample-policy-001"


def test_local_adapter_closes_http_transport_when_config_type_mismatches() -> None:
    transport = _RecordingLoopbackHTTPTransport()
    query = type("Query", (), {"question": "synthetic", "query_id": "q001"})()

    with pytest.raises(RetrievalAdapterError, match="does not match config"):
        LocalRAGRetrievalAdapter(
            LocalRetrievalConfig(configured=True), transport
        ).retrieve(query, 1)

    assert transport.events == ["close"]
    assert transport.state == "closed"


@pytest.mark.parametrize(
    ("first_status", "expected_code", "expected_result"),
    [("pass", 0, "PASS"), ("warning", 1, "WARNING"), ("fail", 2, "FAIL")],
)
def test_loopback_http_cli_e2e_preserves_evaluation_exit_codes_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_status: str,
    expected_code: int,
    expected_result: str,
) -> None:
    transports: list[_RecordingLoopbackHTTPTransport] = []

    def create_transport() -> _RecordingLoopbackHTTPTransport:
        transport = _RecordingLoopbackHTTPTransport()
        transports.append(transport)
        return transport

    monkeypatch.setattr(
        "ragguard.cli.LoopbackHTTPLocalRetrievalTransport", create_transport
    )
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:9999")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:9999")
    with _running_server(
        lambda request: _benchmark_http_response(request, first_status=first_status)
    ) as server:
        config = _write_loopback_config(tmp_path / "private-loopback.json", server)
        output = tmp_path / "report"
        code = main(_benchmark_cli_args(output, config))

    report_text = (output / "benchmark_report.json").read_text(encoding="utf-8")
    markdown = (output / "benchmark_report.md").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert code == expected_code
    assert report["result"] == expected_result
    assert report["metadata"]["retrieval_adapter"] == "local-rag"
    assert set(report) == {
        "result", "status", "corpus_count", "query_count", "summary", "corpus",
        "queries", "per_query_results", "results", "warnings", "errors", "metadata",
    }
    assert all(transport.state == "closed" for transport in transports)
    assert all(transport.events[-1] == "close" for transport in transports)
    combined = report_text + markdown
    assert str(config) not in combined
    assert f"127.0.0.1:{server.server_address[1]}" not in combined
    assert "proxy.invalid" not in combined


def test_loopback_http_cli_accepts_safe_yaml_config(tmp_path: Path) -> None:
    with _running_server(_benchmark_http_response) as server:
        config = _write_loopback_config(tmp_path / "loopback.yaml", server)
        output = tmp_path / "report"
        code = main(_benchmark_cli_args(output, config))

    report = json.loads((output / "benchmark_report.json").read_text(encoding="utf-8"))
    assert code == 0
    assert report["result"] == "PASS"
    assert report["metadata"]["retrieval_adapter"] == "local-rag"


@pytest.mark.parametrize(
    ("script", "category"),
    [
        (_ScriptedResponse(body=b"", status=302, location="http://127.0.0.1:1/private"), "invalid_status"),
        (_ScriptedResponse(body=b"", status=500), "invalid_status"),
        (_ScriptedResponse(body=b"{}", content_type="text/plain"), "invalid_content_type"),
        (_ScriptedResponse(body=b"private-invalid-json"), "invalid_response"),
    ],
)
def test_loopback_http_cli_transport_errors_are_exit_three_and_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    script: _ScriptedResponse,
    category: str,
) -> None:
    transports: list[_RecordingLoopbackHTTPTransport] = []

    def create_transport() -> _RecordingLoopbackHTTPTransport:
        transport = _RecordingLoopbackHTTPTransport()
        transports.append(transport)
        return transport

    monkeypatch.setattr(
        "ragguard.cli.LoopbackHTTPLocalRetrievalTransport", create_transport
    )
    with _running_server(script) as server:
        config = _write_loopback_config(tmp_path / "private-loopback.json", server)
        output = tmp_path / "report"
        code = main(_benchmark_cli_args(output, config))

    error = capsys.readouterr().err
    assert code == 3
    assert category in error
    assert str(config) not in error
    assert f"127.0.0.1:{server.server_address[1]}" not in error
    assert "private-invalid-json" not in error
    assert len(server.requests) == 1
    assert transports[0].events[-1] == "close"
    assert transports[0].state == "closed"
    assert not (output / "benchmark_report.json").exists()


def test_loopback_http_cli_rejects_limit_plus_one_and_timeout_safely(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = _response_body() + b" "
    with _running_server(_ScriptedResponse(body=body)) as oversized_server:
        config = _write_loopback_config(
            tmp_path / "oversized.json",
            oversized_server,
            response_size_limit=len(body) - 1,
        )
        oversized_code = main(
            _benchmark_cli_args(tmp_path / "oversized-report", config)
        )
    oversized_error = capsys.readouterr().err

    with _running_server(
        _ScriptedResponse(body=_response_body(), delay_seconds=0.2)
    ) as timeout_server:
        config = _write_loopback_config(
            tmp_path / "timeout.json",
            timeout_server,
            connect_timeout=0.05,
            read_timeout=0.05,
            total_timeout=0.05,
        )
        timeout_code = main(_benchmark_cli_args(tmp_path / "timeout-report", config))
    timeout_error = capsys.readouterr().err

    assert oversized_code == timeout_code == 3
    assert "response_too_large" in oversized_error
    assert "timeout" in timeout_error
    assert len(oversized_server.requests) == len(timeout_server.requests) == 1


def test_loopback_http_cli_rejects_mixed_resolution_before_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def mixed_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 1)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.168.1.10", 1)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mixed_getaddrinfo)
    with _running_server(_benchmark_http_response) as server:
        config = _write_loopback_config(
            tmp_path / "mixed.json",
            server,
            endpoint=f"http://localhost:{server.server_address[1]}/retrieve",
            allowlisted_hostnames=["localhost"],
        )
        code = main(_benchmark_cli_args(tmp_path / "report", config))

    error = capsys.readouterr().err
    assert code == 3
    assert "external_host_rejected" in error
    assert len(server.requests) == 0


def test_loopback_http_cli_connection_refused_is_exit_three_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    class RefusingClient:
        def __init__(self, endpoint: LocalHTTPEndpoint) -> None:
            assert isinstance(endpoint, LocalHTTPEndpoint)

        def retrieve(self, request: HTTPRetrievalRequest):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            raise http_transport_error(HTTPTransportErrorCategory.CONNECTION_REFUSED)

    monkeypatch.setattr(
        "ragguard.http_transport.BoundedLoopbackHTTPClient", RefusingClient
    )
    config_path = tmp_path / "refused.json"
    config_path.write_text(
        json.dumps(
            {
                "transport_type": "loopback_http",
                "endpoint": "http://127.0.0.1:8765/retrieve",
                "connect_timeout": 0.1,
                "read_timeout": 0.1,
                "total_timeout": 0.1,
            }
        ),
        encoding="utf-8",
    )

    code = main(_benchmark_cli_args(tmp_path / "report", config_path))

    error = capsys.readouterr().err
    assert code == 3
    assert "connection_refused" in error
    assert "127.0.0.1:8765" not in error
    assert str(config_path) not in error
    assert calls == 1


def test_loopback_http_cli_incomplete_config_is_exit_three_without_disclosure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "private-incomplete.json"
    config_path.write_text(
        json.dumps(
            {
                "transport_type": "loopback_http",
                "endpoint": "http://127.0.0.1:8765/private",
            }
        ),
        encoding="utf-8",
    )

    code = main(_benchmark_cli_args(tmp_path / "report", config_path))

    error = capsys.readouterr().err
    assert code == 3
    assert "incomplete" in error
    assert str(config_path) not in error
    assert "127.0.0.1:8765" not in error
