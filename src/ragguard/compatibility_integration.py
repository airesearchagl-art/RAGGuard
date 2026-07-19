from __future__ import annotations

from ragguard.compatibility import (
    CapabilitiesResponse,
    CompatibilityProfileRegistry,
    CompatibilityProfileSelection,
    HealthResponse,
    StandardRetrievalRequest,
    map_product_response,
    map_standard_request,
    negotiate_compatibility,
)
from ragguard.http_transport import CompatibilityLoopbackHTTPTransport
from ragguard.retrieval import (
    LocalRetrievalConfig,
    RankedResult,
    RetrievalAdapterError,
    RetrievalQuery,
)


class CompatibilityProfileRetrievalAdapter:
    """One-shot profile integration over bounded loopback JSON requests."""

    name = "local-rag"

    def __init__(
        self,
        configuration: LocalRetrievalConfig,
        registry: CompatibilityProfileRegistry,
        *,
        transport: CompatibilityLoopbackHTTPTransport | None = None,
    ) -> None:
        if (
            not isinstance(configuration, LocalRetrievalConfig)
            or configuration.transport_type != "loopback_http"
            or configuration.http_endpoint is None
            or not isinstance(
                configuration.compatibility_profile, CompatibilityProfileSelection
            )
            or not isinstance(registry, CompatibilityProfileRegistry)
            or (transport is not None and not isinstance(
                transport, CompatibilityLoopbackHTTPTransport
            ))
        ):
            raise RetrievalAdapterError("profile_not_configured")
        self._configuration: LocalRetrievalConfig | None = configuration
        self._registry: CompatibilityProfileRegistry | None = registry
        self._transport: CompatibilityLoopbackHTTPTransport | None = (
            transport or CompatibilityLoopbackHTTPTransport()
        )
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def retrieve(self, query: RetrievalQuery, top_k: int) -> list[RankedResult]:
        if self._closed or self._configuration is None or self._registry is None:
            raise RetrievalAdapterError("profile_not_configured")
        configuration = self._configuration
        selection = configuration.compatibility_profile
        assert isinstance(selection, CompatibilityProfileSelection)
        try:
            profile = self._registry.resolve(
                selection.profile_id,
                str(selection.profile_version),
                str(selection.protocol_version),
            )
            supported = self._registry.supported(profile.profile_id)
            if self._transport is None:
                raise RetrievalAdapterError("profile_not_configured")
            self._transport.initialize(configuration)
            health_raw = self._request(profile.health_path, "GET")
            health = HealthResponse.from_mapping(health_raw)
            capabilities_raw = self._request(profile.capabilities_path, "GET")
            capabilities = CapabilitiesResponse.from_mapping(capabilities_raw)
            compatibility = negotiate_compatibility(
                supported,
                health,
                capabilities,
                requested_optional_capabilities=(
                    selection.requested_optional_capabilities
                ),
            )
            standard_request = StandardRetrievalRequest(
                query=query.question,
                top_k=top_k,
                query_id=query.query_id,
                protocol_version=selection.protocol_version,
                requested_capabilities=selection.requested_optional_capabilities,
            )
            mapped_request = map_standard_request(
                profile, standard_request, compatibility
            )
            product_raw = self._request(
                profile.retrieve_path,
                "POST",
                dict(mapped_request.as_mapping()),
            )
            mapped_response = map_product_response(
                profile,
                product_raw,
                top_k=top_k,
                compatibility=compatibility,
                expected_query_id=query.query_id,
            )
            return list(mapped_response.results)
        except RetrievalAdapterError:
            raise
        except Exception:
            raise RetrievalAdapterError("invalid_response") from None
        finally:
            self.close()

    def close(self) -> None:
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
        self._configuration = None
        self._registry = None
        self._transport = None
        self._closed = True

    def _request(
        self,
        path: str,
        method: str,
        payload: dict[str, object] | None = None,
    ):
        configuration = self._configuration
        transport = self._transport
        if configuration is None or configuration.http_endpoint is None or transport is None:
            raise RetrievalAdapterError("profile_not_configured")
        try:
            return transport.request_json(path, method, payload)
        except RetrievalAdapterError:
            raise
        except Exception:
            raise RetrievalAdapterError("invalid_response") from None
