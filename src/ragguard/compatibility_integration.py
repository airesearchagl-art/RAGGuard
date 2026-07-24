from __future__ import annotations

from collections.abc import Callable

from ragguard.approval_enforcement import (
    ApprovalEnforcementRequest,
    REQUIRED_RETRIEVAL_CAPABILITIES,
    require_approved_retrieval,
)
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
        transport_factory: Callable[
            [], CompatibilityLoopbackHTTPTransport
        ] | None = None,
        approval_request: ApprovalEnforcementRequest | None = None,
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
            or (transport_factory is not None and not callable(transport_factory))
            or (transport is not None and transport_factory is not None)
            or (
                approval_request is not None
                and not isinstance(
                    approval_request,
                    ApprovalEnforcementRequest,
                )
            )
            or (approval_request is not None and transport is not None)
        ):
            raise RetrievalAdapterError("profile_not_configured")
        self._configuration: LocalRetrievalConfig | None = configuration
        self._registry: CompatibilityProfileRegistry | None = registry
        self._transport = transport
        self._transport_factory = (
            transport_factory or CompatibilityLoopbackHTTPTransport
        )
        self._approval_request = approval_request
        self._lifecycle: tuple[str, ...] = ()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def lifecycle(self) -> tuple[str, ...]:
        return self._lifecycle

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
            self._record("compatibility_resolved")
            supported = self._registry.supported(profile.profile_id)
            if self._approval_request is not None:
                approval_request = self._approval_request
                expected_capabilities = tuple(
                    sorted(
                        REQUIRED_RETRIEVAL_CAPABILITIES
                        | set(selection.requested_optional_capabilities)
                    )
                )
                if (
                    approval_request.profile_id != profile.profile_id
                    or approval_request.profile_version
                    != profile.profile_version
                    or approval_request.requested_top_k != top_k
                    or approval_request.requested_capabilities
                    != expected_capabilities
                    or approval_request.requested_optional_fields
                    != tuple(
                        sorted(selection.requested_optional_capabilities)
                    )
                ):
                    raise RetrievalAdapterError("registry_metadata_invalid")
                enforcement = require_approved_retrieval(
                    approval_request
                )
                resolved = enforcement.resolved_approved_entry
                assert resolved is not None
                if (
                    resolved.protocol_version != profile.protocol_version
                    or resolved.approved_score_semantics
                    is not profile.score_semantics
                    or resolved.approved_source_identifier_policy
                    is not profile.source_identifier_policy
                ):
                    raise RetrievalAdapterError("registry_metadata_invalid")
                self._record("approval_enforced")
            if self._transport is None:
                created = self._transport_factory()
                if not isinstance(
                    created,
                    CompatibilityLoopbackHTTPTransport,
                ):
                    raise RetrievalAdapterError("profile_not_configured")
                self._transport = created
            self._transport.initialize(configuration)
            self._record("transport_initialized")
            health_raw = self._request(profile.health_path, "GET")
            health = HealthResponse.from_mapping(health_raw)
            self._record("health_validated")
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
            self._record("capabilities_negotiated")
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
            self._record("request_mapped")
            product_raw = self._request(
                profile.retrieve_path,
                "POST",
                dict(mapped_request.as_mapping()),
            )
            self._record("retrieval_completed")
            mapped_response = map_product_response(
                profile,
                product_raw,
                top_k=top_k,
                compatibility=compatibility,
                expected_query_id=query.query_id,
            )
            self._record("response_mapped")
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
                self._record("closed")
            except Exception:
                pass
        self._configuration = None
        self._registry = None
        self._transport = None
        self._approval_request = None
        self._closed = True

    def _record(self, stage: str) -> None:
        self._lifecycle = (*self._lifecycle, stage)

    def _request(
        self,
        path: str,
        method: str,
        payload: dict[str, object] | None = None,
    ):
        configuration = self._configuration
        transport = self._transport
        if (
            configuration is None
            or configuration.http_endpoint is None
            or transport is None
        ):
            raise RetrievalAdapterError("profile_not_configured")
        try:
            return transport.request_json(path, method, payload)
        except RetrievalAdapterError:
            raise
        except Exception:
            raise RetrievalAdapterError("invalid_response") from None
