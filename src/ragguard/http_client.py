from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import time
from collections.abc import Callable, Mapping, Sequence

from ragguard.http_contract import (
    HTTP_JSON_CONTENT_TYPE,
    HTTPRetrievalRequest,
    HTTPTransportErrorCategory,
    LocalHTTPEndpoint,
    LoopbackResolutionContract,
    http_transport_error,
    parse_http_retrieval_response,
    response_read_limit,
    validate_http_response_head,
)
from ragguard.retrieval import (
    RankedResult,
    RetrievalAdapterError,
    normalize_local_response,
)

AddressResolver = Callable[[str, int], Sequence[str]]
ConnectionFactory = Callable[[str, int, float], http.client.HTTPConnection]
Clock = Callable[[], float]
_SAFE_HTTP_ERROR_VALUES = frozenset(
    category.value for category in HTTPTransportErrorCategory
)


class BoundedLoopbackHTTPClient:
    """One-request loopback HTTP client with bounded I/O and safe errors."""

    def __init__(
        self,
        endpoint: LocalHTTPEndpoint,
        *,
        resolver: AddressResolver | None = None,
        connection_factory: ConnectionFactory | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        if not isinstance(endpoint, LocalHTTPEndpoint):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        if resolver is not None and not callable(resolver):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        if connection_factory is not None and not callable(connection_factory):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        if not callable(clock):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        self._endpoint = endpoint
        self._resolver = resolver or resolve_loopback_addresses
        self._connection_factory = connection_factory or _create_connection
        self._clock = clock

    def retrieve(self, request: HTTPRetrievalRequest) -> list[RankedResult]:
        if not isinstance(request, HTTPRetrievalRequest):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)

        deadline = self._clock() + self._endpoint.total_timeout
        addresses = self._resolve_immediately_before_connect(deadline)
        selected_address = _select_address(addresses)
        connection: http.client.HTTPConnection | None = None
        result: list[RankedResult] | None = None
        error: RetrievalAdapterError | None = None

        try:
            connection = self._connection_factory(
                selected_address,
                self._endpoint.port,
                min(self._endpoint.connect_timeout, self._remaining(deadline)),
            )
            connection.connect()
            socket_object = connection.sock
            if socket_object is None:
                raise http_transport_error(
                    HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
                )
            try:
                peer_address = socket_object.getpeername()[0]
            except Exception:
                raise http_transport_error(
                    HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
                ) from None
            LoopbackResolutionContract(
                resolved_addresses=addresses,
                peer_address=peer_address,
                resolved_immediately_before_connect=True,
            )

            socket_object.settimeout(
                min(self._endpoint.read_timeout, self._remaining(deadline))
            )
            connection.request(
                "POST",
                self._endpoint.path,
                body=request.to_json_bytes(),
                headers={
                    "Accept": HTTP_JSON_CONTENT_TYPE,
                    "Content-Type": HTTP_JSON_CONTENT_TYPE,
                },
            )
            response = connection.getresponse()
            validate_http_response_head(
                response.status,
                response.getheader("Content-Type", ""),
            )
            body = response.read(
                response_read_limit(self._endpoint.response_size_limit)
            )
            self._remaining(deadline)
            local_response = parse_http_retrieval_response(
                body,
                status_code=response.status,
                content_type=response.getheader("Content-Type", ""),
                top_k=request.top_k,
                response_size_limit=self._endpoint.response_size_limit,
            )
            result = normalize_local_response(
                local_response,
                top_k=request.top_k,
                response_size_limit=self._endpoint.response_size_limit,
            )
            self._remaining(deadline)
        except Exception as exc:
            error = _safe_client_error(exc)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    if error is None:
                        error = http_transport_error(
                            HTTPTransportErrorCategory.INVALID_RESPONSE
                        )

        if error is not None:
            raise error from None
        if result is None:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        return result

    def request_json(
        self,
        method: str,
        payload: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        """Perform one bounded product-neutral JSON request without retaining raw data."""
        if method not in {"GET", "POST"} or (method == "GET" and payload is not None):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        try:
            body = (
                None
                if payload is None
                else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
        except (TypeError, ValueError):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE) from None
        if body is not None and len(body) > 65_536:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)

        deadline = self._clock() + self._endpoint.total_timeout
        addresses = self._resolve_immediately_before_connect(deadline)
        selected_address = _select_address(addresses)
        connection: http.client.HTTPConnection | None = None
        parsed: Mapping[str, object] | None = None
        error: RetrievalAdapterError | None = None
        try:
            connection = self._connection_factory(
                selected_address,
                self._endpoint.port,
                min(self._endpoint.connect_timeout, self._remaining(deadline)),
            )
            connection.connect()
            socket_object = connection.sock
            if socket_object is None:
                raise http_transport_error(HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED)
            try:
                peer_address = socket_object.getpeername()[0]
            except Exception:
                raise http_transport_error(
                    HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
                ) from None
            LoopbackResolutionContract(
                resolved_addresses=addresses,
                peer_address=peer_address,
                resolved_immediately_before_connect=True,
            )
            socket_object.settimeout(
                min(self._endpoint.read_timeout, self._remaining(deadline))
            )
            headers = {"Accept": HTTP_JSON_CONTENT_TYPE}
            if body is not None:
                headers["Content-Type"] = HTTP_JSON_CONTENT_TYPE
            connection.request(method, self._endpoint.path, body=body, headers=headers)
            response = connection.getresponse()
            validate_http_response_head(
                response.status, response.getheader("Content-Type", "")
            )
            raw = response.read(response_read_limit(self._endpoint.response_size_limit))
            if len(raw) > self._endpoint.response_size_limit:
                raise http_transport_error(HTTPTransportErrorCategory.RESPONSE_TOO_LARGE)
            self._remaining(deadline)
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE) from None
            if not isinstance(value, Mapping):
                raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
            parsed = dict(value)
        except Exception as exc:
            error = _safe_client_error(exc)
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    if error is None:
                        error = http_transport_error(
                            HTTPTransportErrorCategory.INVALID_RESPONSE
                        )
        if error is not None:
            raise error from None
        if parsed is None:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        return parsed

    def _resolve_immediately_before_connect(
        self,
        deadline: float,
    ) -> tuple[str, ...]:
        try:
            raw_addresses = self._resolver(
                self._endpoint.host,
                self._endpoint.port,
            )
            self._remaining(deadline)
            if isinstance(raw_addresses, (str, bytes)):
                raise http_transport_error(
                    HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
                )
            addresses = tuple(raw_addresses)
            if not addresses:
                raise http_transport_error(
                    HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
                )
            proof = LoopbackResolutionContract(
                resolved_addresses=addresses,
                peer_address=addresses[0],
                resolved_immediately_before_connect=True,
            )
            return tuple(proof.resolved_addresses)
        except Exception as exc:
            raise _safe_resolution_error(exc) from None

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise http_transport_error(HTTPTransportErrorCategory.TIMEOUT)
        return remaining


def resolve_loopback_addresses(host: str, port: int) -> tuple[str, ...]:
    """Resolve one endpoint and return a deterministic complete address set."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            address_info = socket.getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except (TimeoutError, socket.timeout):
            raise http_transport_error(HTTPTransportErrorCategory.TIMEOUT) from None
        except (OSError, UnicodeError):
            raise http_transport_error(
                HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
            ) from None
        raw_addresses = tuple(item[4][0] for item in address_info)
    else:
        raw_addresses = (str(literal),)

    try:
        normalized = {
            str(ipaddress.ip_address(address)) for address in raw_addresses
        }
    except (TypeError, ValueError):
        raise http_transport_error(
            HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
        ) from None
    if not normalized or not all(
        ipaddress.ip_address(address).is_loopback for address in normalized
    ):
        raise http_transport_error(
            HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
        )
    return tuple(sorted(normalized, key=_address_sort_key))


def _select_address(addresses: Sequence[str]) -> str:
    try:
        return min(addresses, key=_address_sort_key)
    except (TypeError, ValueError):
        raise http_transport_error(
            HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
        ) from None


def _address_sort_key(value: str) -> tuple[int, int]:
    address = ipaddress.ip_address(value)
    return address.version, int(address)


def _create_connection(
    host: str,
    port: int,
    timeout: float,
) -> http.client.HTTPConnection:
    # HTTPConnection does not use environment or system proxy configuration.
    return http.client.HTTPConnection(host, port, timeout=timeout)


def _safe_resolution_error(exc: Exception) -> RetrievalAdapterError:
    if isinstance(exc, RetrievalAdapterError):
        if str(exc) in _SAFE_HTTP_ERROR_VALUES:
            return exc
        return http_transport_error(HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED)
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return http_transport_error(HTTPTransportErrorCategory.TIMEOUT)
    return http_transport_error(HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED)


def _safe_client_error(exc: Exception) -> RetrievalAdapterError:
    if isinstance(exc, RetrievalAdapterError):
        if str(exc) in _SAFE_HTTP_ERROR_VALUES:
            return exc
        return http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return http_transport_error(HTTPTransportErrorCategory.TIMEOUT)
    if isinstance(exc, ConnectionRefusedError):
        return http_transport_error(HTTPTransportErrorCategory.CONNECTION_REFUSED)
    if isinstance(exc, OSError):
        return http_transport_error(HTTPTransportErrorCategory.CONNECTION_REFUSED)
    if isinstance(exc, http.client.HTTPException):
        return http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
    return http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
