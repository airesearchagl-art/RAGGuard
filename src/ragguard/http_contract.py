from __future__ import annotations

import ipaddress
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ragguard.retrieval import (
    LOCAL_RESPONSE_METADATA_KEYS,
    MAX_LOCAL_QUERY_LENGTH,
    MAX_LOCAL_RESPONSE_SIZE,
    MAX_LOCAL_TIMEOUT_SECONDS,
    MAX_LOCAL_TOP_K,
    LocalRetrievalResponse,
    LocalRetrievalResult,
    RetrievalAdapterError,
)

HTTP_JSON_CONTENT_TYPE = "application/json"
HTTP_REQUEST_SIZE_LIMIT = 65_536
DEFAULT_HTTP_RESPONSE_SIZE_LIMIT = 262_144
MAX_HTTP_RESPONSE_SIZE_LIMIT = MAX_LOCAL_RESPONSE_SIZE
MAX_HTTP_RESULTS = MAX_LOCAL_TOP_K

_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_SAFE_HOSTNAME = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\Z"
)
_REQUEST_FIELDS = frozenset({"query", "top_k", "query_id", "capability_version"})
_RESPONSE_FIELDS = frozenset({"results"})
_RESULT_FIELDS = frozenset(
    {
        "rank",
        "document_id",
        "score",
        "title",
        "source_id",
        "matched_keywords",
        "adapter_metadata",
    }
)
_REQUIRED_RESULT_FIELDS = frozenset(
    {"rank", "document_id", "score", "title", "source_id"}
)


class HTTPTransportErrorCategory(str, Enum):
    INVALID_ENDPOINT = "invalid_endpoint"
    EXTERNAL_HOST_REJECTED = "external_host_rejected"
    CONNECTION_REFUSED = "connection_refused"
    TIMEOUT = "timeout"
    INVALID_STATUS = "invalid_status"
    INVALID_CONTENT_TYPE = "invalid_content_type"
    RESPONSE_TOO_LARGE = "response_too_large"
    INVALID_RESPONSE = "invalid_response"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"


def http_transport_error(
    category: HTTPTransportErrorCategory,
) -> RetrievalAdapterError:
    """Create a bounded error containing only an allowlisted category."""
    if not isinstance(category, HTTPTransportErrorCategory):
        return RetrievalAdapterError(HTTPTransportErrorCategory.INVALID_RESPONSE.value)
    return RetrievalAdapterError(category.value)


@dataclass(frozen=True)
class LocalHTTPEndpoint:
    """Validated loopback HTTP endpoint contract without resolution or I/O."""

    scheme: str
    host: str = field(repr=False)
    port: int
    path: str = field(repr=False)
    connect_timeout: int | float
    read_timeout: int | float
    total_timeout: int | float
    response_size_limit: int = DEFAULT_HTTP_RESPONSE_SIZE_LIMIT
    allowlisted_hostnames: frozenset[str] = field(
        default_factory=frozenset,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.scheme != "http":
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        if type(self.port) is not int or not 1 <= self.port <= 65_535:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        _validate_http_path(self.path)
        _validate_timeout(self.connect_timeout)
        _validate_timeout(self.read_timeout)
        _validate_timeout(self.total_timeout)
        if self.total_timeout < max(self.connect_timeout, self.read_timeout):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        _validate_response_limit(
            self.response_size_limit,
            HTTPTransportErrorCategory.INVALID_ENDPOINT,
        )

        if not isinstance(self.allowlisted_hostnames, frozenset) or not all(
            isinstance(value, str) for value in self.allowlisted_hostnames
        ):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        normalized_allowlist = frozenset(
            value.strip().lower() for value in self.allowlisted_hostnames
        )
        if not all(_SAFE_HOSTNAME.fullmatch(value) for value in normalized_allowlist):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        object.__setattr__(self, "allowlisted_hostnames", normalized_allowlist)

        normalized_host = _validate_loopback_host(self.host, normalized_allowlist)
        object.__setattr__(self, "host", normalized_host)


@dataclass(frozen=True)
class LoopbackResolutionContract:
    """Caller-supplied DNS and peer proof; this model performs no lookup."""

    resolved_addresses: Sequence[str] = field(repr=False)
    peer_address: str = field(repr=False)
    resolved_immediately_before_connect: bool = True

    def __post_init__(self) -> None:
        if self.resolved_immediately_before_connect is not True:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        if isinstance(self.resolved_addresses, (str, bytes)) or not isinstance(
            self.resolved_addresses, Sequence
        ):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        try:
            resolved = tuple(
                str(ipaddress.ip_address(value)) for value in self.resolved_addresses
            )
            peer = str(ipaddress.ip_address(self.peer_address))
        except (TypeError, ValueError):
            raise http_transport_error(
                HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
            ) from None
        if not resolved or not all(ipaddress.ip_address(value).is_loopback for value in resolved):
            raise http_transport_error(
                HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
            )
        if not ipaddress.ip_address(peer).is_loopback or peer not in resolved:
            raise http_transport_error(
                HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
            )
        object.__setattr__(self, "resolved_addresses", resolved)
        object.__setattr__(self, "peer_address", peer)


@dataclass(frozen=True)
class HTTPRetrievalRequest:
    """Bounded JSON request model for a future loopback HTTP transport."""

    query: str = field(repr=False)
    top_k: int
    query_id: str | None = None
    capability_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        if len(self.query) > MAX_LOCAL_QUERY_LENGTH:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        if type(self.top_k) is not int or not 1 <= self.top_k <= MAX_LOCAL_TOP_K:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        for value in (self.query_id, self.capability_version):
            if value is not None and (
                not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value)
            ):
                raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        self.to_json_bytes()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> HTTPRetrievalRequest:
        if not isinstance(raw, Mapping) or not set(raw).issubset(_REQUEST_FIELDS):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        if not {"query", "top_k"}.issubset(raw):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        try:
            return cls(**dict(raw))
        except TypeError:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE) from None

    def to_json_bytes(self) -> bytes:
        payload: dict[str, Any] = {"query": self.query, "top_k": self.top_k}
        if self.query_id is not None:
            payload["query_id"] = self.query_id
        if self.capability_version is not None:
            payload["capability_version"] = self.capability_version
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > HTTP_REQUEST_SIZE_LIMIT:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        return encoded


def response_read_limit(response_size_limit: int) -> int:
    """Return limit + 1 so callers can reject oversized bodies before parsing."""
    _validate_response_limit(response_size_limit)
    return response_size_limit + 1


def parse_http_retrieval_response(
    body: bytes,
    *,
    status_code: int,
    content_type: str,
    top_k: int,
    response_size_limit: int = DEFAULT_HTTP_RESPONSE_SIZE_LIMIT,
) -> LocalRetrievalResponse:
    """Validate a caller-supplied HTTP response without performing communication."""
    _validate_response_limit(response_size_limit)
    if not isinstance(body, bytes):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
    if len(body) > response_size_limit:
        raise http_transport_error(HTTPTransportErrorCategory.RESPONSE_TOO_LARGE)
    if type(status_code) is not int or status_code != 200:
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_STATUS)
    if not _is_json_content_type(content_type):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_CONTENT_TYPE)
    if type(top_k) is not int or not 1 <= top_k <= MAX_HTTP_RESULTS:
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)

    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE) from None
    if not isinstance(raw, Mapping) or set(raw) != _RESPONSE_FIELDS:
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
    raw_results = raw["results"]
    if isinstance(raw_results, (str, bytes)) or not isinstance(raw_results, Sequence):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
    if len(raw_results) > min(top_k, MAX_HTTP_RESULTS):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)

    try:
        results = tuple(_parse_http_result(value) for value in raw_results)
        return LocalRetrievalResponse(results=results)
    except RetrievalAdapterError:
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE) from None


def _parse_http_result(raw: Any) -> LocalRetrievalResult:
    if not isinstance(raw, Mapping):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
    fields = set(raw)
    if not fields.issubset(_RESULT_FIELDS) or not _REQUIRED_RESULT_FIELDS.issubset(fields):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
    metadata = raw.get("adapter_metadata")
    if metadata is not None and (
        not isinstance(metadata, Mapping)
        or not set(metadata).issubset(LOCAL_RESPONSE_METADATA_KEYS)
    ):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
    return LocalRetrievalResult(
        rank=raw["rank"],
        document_id=raw["document_id"],
        score=raw["score"],
        title=raw["title"],
        source_id=raw["source_id"],
        matched_keywords=raw.get("matched_keywords", ()),
        metadata=metadata,
    )


def _validate_loopback_host(host: str, allowlist: frozenset[str]) -> str:
    if not isinstance(host, str) or not host.strip():
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
    normalized = host.strip().lower()
    if any(value in normalized for value in ("@", "*", "/", "?", "#", "[", "]")):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        if not _SAFE_HOSTNAME.fullmatch(normalized) or normalized not in allowlist:
            raise http_transport_error(
                HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED
            ) from None
        return normalized
    if not address.is_loopback:
        raise http_transport_error(HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED)
    return str(address)


def _validate_http_path(path: str) -> None:
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or any(value in path for value in ("?", "#", "\\", "\r", "\n"))
        or ".." in path.split("/")
    ):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)


def _validate_timeout(value: int | float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        or value > MAX_LOCAL_TIMEOUT_SECONDS
    ):
        raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)


def _validate_response_limit(
    value: int,
    category: HTTPTransportErrorCategory = HTTPTransportErrorCategory.INVALID_RESPONSE,
) -> None:
    if type(value) is not int or not 1 <= value <= MAX_HTTP_RESPONSE_SIZE_LIMIT:
        raise http_transport_error(category)


def _is_json_content_type(value: str) -> bool:
    if not isinstance(value, str):
        return False
    parts = [part.strip().lower() for part in value.split(";")]
    if parts[0] != HTTP_JSON_CONTENT_TYPE:
        return False
    return len(parts) == 1 or parts[1:] == ["charset=utf-8"]
