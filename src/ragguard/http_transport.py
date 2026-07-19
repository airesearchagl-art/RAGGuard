from __future__ import annotations

from collections.abc import Callable

from ragguard.http_client import BoundedLoopbackHTTPClient
from ragguard.http_contract import (
    HTTPRetrievalRequest,
    HTTPTransportErrorCategory,
    LocalHTTPEndpoint,
    http_transport_error,
)
from ragguard.retrieval import (
    LocalRetrievalCapabilities,
    LocalRetrievalConfig,
    LocalRetrievalRequest,
    LocalRetrievalResponse,
    LocalRetrievalResult,
    RetrievalAdapterError,
)

HTTPClientFactory = Callable[[LocalHTTPEndpoint], BoundedLoopbackHTTPClient]


class LoopbackHTTPLocalRetrievalTransport:
    """One-shot local transport backed only by the bounded loopback client."""

    transport_type = "loopback_http"

    def __init__(
        self,
        *,
        client_factory: HTTPClientFactory | None = None,
    ) -> None:
        if client_factory is not None and not callable(client_factory):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        self._client_factory = client_factory or BoundedLoopbackHTTPClient
        self._client: BoundedLoopbackHTTPClient | None = None
        self._state = "created"
        self._capabilities = LocalRetrievalCapabilities(matched_keywords=True)

    @property
    def state(self) -> str:
        return self._state

    def initialize(self, config: LocalRetrievalConfig) -> None:
        if self._state == "initialized":
            raise RetrievalAdapterError("loopback HTTP transport is already initialized")
        if self._state == "closed":
            raise RetrievalAdapterError("loopback HTTP transport is closed")
        if (
            not isinstance(config, LocalRetrievalConfig)
            or config.transport_type != self.transport_type
            or not config.configured
            or not isinstance(config.http_endpoint, LocalHTTPEndpoint)
        ):
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT)
        if config.capabilities.filters:
            raise http_transport_error(
                HTTPTransportErrorCategory.UNSUPPORTED_CAPABILITY
            )
        try:
            self._client = self._client_factory(config.http_endpoint)
        except RetrievalAdapterError:
            raise
        except Exception:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_ENDPOINT) from None
        self._state = "initialized"

    def health_check(self) -> bool:
        self._require_initialized()
        return True

    def capabilities(self) -> LocalRetrievalCapabilities:
        self._require_initialized()
        return self._capabilities

    def retrieve(self, request: LocalRetrievalRequest) -> LocalRetrievalResponse:
        self._require_initialized()
        if not isinstance(request, LocalRetrievalRequest) or self._client is None:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE)
        try:
            ranked_results = self._client.retrieve(
                HTTPRetrievalRequest(
                    query=request.query,
                    top_k=request.top_k,
                    query_id=request.query_id,
                    capability_version="1",
                )
            )
            return LocalRetrievalResponse(
                results=[
                    LocalRetrievalResult(
                        rank=result.rank,
                        document_id=result.document_id,
                        score=result.score,
                        title=result.title,
                        source_id=result.source_path,
                        matched_keywords=result.matched_keywords,
                        metadata=result.adapter_metadata,
                    )
                    for result in ranked_results
                ]
            )
        except RetrievalAdapterError:
            raise
        except Exception:
            raise http_transport_error(HTTPTransportErrorCategory.INVALID_RESPONSE) from None

    def close(self) -> None:
        self._client = None
        self._state = "closed"

    def _require_initialized(self) -> None:
        if self._state == "created":
            raise RetrievalAdapterError("loopback HTTP transport is not initialized")
        if self._state == "closed":
            raise RetrievalAdapterError("loopback HTTP transport is closed")
