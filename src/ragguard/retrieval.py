from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

import yaml

if TYPE_CHECKING:
    from ragguard.http_contract import LocalHTTPEndpoint


class RetrievalAdapterError(ValueError):
    """Raised when an adapter violates the retrieval contract."""


LOCAL_TRANSPORT_TYPES = frozenset({"in_memory", "loopback_http"})
LOCAL_RESPONSE_METADATA_KEYS = frozenset(
    {"capability", "match_type", "result_type", "transport"}
)
IN_MEMORY_ERROR_MODES = frozenset(
    {"invalid_response", "oversized_response", "timeout", "transport_exception"}
)
MAX_LOCAL_TIMEOUT_SECONDS = 60.0
MAX_LOCAL_TOP_K = 100
MAX_LOCAL_RESPONSE_SIZE = 1_048_576
MAX_LOCAL_QUERY_LENGTH = 4_096
MAX_LOCAL_IDENTIFIER_LENGTH = 256
MAX_LOCAL_TITLE_LENGTH = 512
MAX_LOCAL_KEYWORDS = 100
MAX_LOCAL_KEYWORD_LENGTH = 128
MAX_LOCAL_METADATA_VALUE_LENGTH = 128
MAX_LOCAL_CONFIG_SIZE = 65_536
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_LOCAL_CONFIG_KEYS = frozenset(
    {
        "transport_type",
        "timeout_seconds",
        "default_top_k",
        "response_size_limit",
        "capabilities",
    }
)
_LOCAL_HTTP_CONFIG_KEYS = frozenset(
    {
        "transport_type",
        "endpoint",
        "connect_timeout",
        "read_timeout",
        "total_timeout",
        "default_top_k",
        "response_size_limit",
        "capabilities",
        "allowlisted_hostnames",
        "compatibility_profile",
    }
)
_LOCAL_CAPABILITY_KEYS = frozenset(
    {"ranked_results", "matched_keywords", "filters"}
)


@dataclass(frozen=True)
class LocalRetrievalCapabilities:
    """Allowlisted feature flags negotiated by a future local transport."""

    ranked_results: bool = True
    matched_keywords: bool = False
    filters: bool = False

    def __post_init__(self) -> None:
        if not all(
            type(value) is bool
            for value in (self.ranked_results, self.matched_keywords, self.filters)
        ):
            raise RetrievalAdapterError("local capability flags must be boolean")
        if not self.ranked_results:
            raise RetrievalAdapterError("local transport must support ranked results")


@dataclass(frozen=True)
class LocalRetrievalConfig:
    """Validated, value-safe configuration for a future local-only transport."""

    transport_type: str = "in_memory"
    timeout_seconds: int | float = 3.0
    default_top_k: int = 5
    response_size_limit: int = 262_144
    capabilities: LocalRetrievalCapabilities = field(
        default_factory=LocalRetrievalCapabilities
    )
    http_endpoint: LocalHTTPEndpoint | None = field(default=None, repr=False)
    compatibility_profile: Any | None = field(default=None, repr=False)
    configured: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.transport_type, str)
            or self.transport_type not in LOCAL_TRANSPORT_TYPES
        ):
            raise RetrievalAdapterError("unsupported local transport type")
        _validate_positive_finite_number(
            self.timeout_seconds,
            "timeout_seconds",
            MAX_LOCAL_TIMEOUT_SECONDS,
        )
        _validate_positive_integer(self.default_top_k, "default_top_k", MAX_LOCAL_TOP_K)
        _validate_positive_integer(
            self.response_size_limit,
            "response_size_limit",
            MAX_LOCAL_RESPONSE_SIZE,
        )
        if not isinstance(self.capabilities, LocalRetrievalCapabilities):
            raise RetrievalAdapterError("capabilities must use LocalRetrievalCapabilities")
        if self.transport_type == "in_memory" and self.http_endpoint is not None:
            raise RetrievalAdapterError("in-memory transport does not accept HTTP settings")
        if self.transport_type == "loopback_http":
            from ragguard.http_contract import LocalHTTPEndpoint

            if not isinstance(self.http_endpoint, LocalHTTPEndpoint):
                raise RetrievalAdapterError("loopback HTTP transport requires an endpoint")
            if self.compatibility_profile is not None:
                from ragguard.compatibility import CompatibilityProfileSelection

                if not isinstance(
                    self.compatibility_profile, CompatibilityProfileSelection
                ):
                    raise RetrievalAdapterError("compatibility profile is invalid")
        elif self.compatibility_profile is not None:
            raise RetrievalAdapterError("compatibility profile requires loopback HTTP")
        if type(self.configured) is not bool:
            raise RetrievalAdapterError("configured must be boolean")


def load_local_retrieval_config(path: Path) -> LocalRetrievalConfig:
    """Load a bounded JSON or YAML config without exposing its path or values."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_LOCAL_CONFIG_SIZE:
            raise RetrievalAdapterError("local retrieval config is unavailable or too large")
        raw_text = path.read_text(encoding="utf-8")
    except RetrievalAdapterError:
        raise
    except (OSError, UnicodeError) as exc:
        raise RetrievalAdapterError("local retrieval config could not be read") from exc

    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            raw_config = json.loads(raw_text)
        elif suffix in {".yaml", ".yml"}:
            raw_config = yaml.safe_load(raw_text)
        else:
            raise RetrievalAdapterError("local retrieval config must be JSON or YAML")
    except RetrievalAdapterError:
        raise
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise RetrievalAdapterError("local retrieval config is invalid") from exc

    if not isinstance(raw_config, Mapping):
        raise RetrievalAdapterError("local retrieval config must be a mapping")
    config_values = dict(raw_config)
    transport_type = config_values.get("transport_type")
    allowed_keys = (
        _LOCAL_HTTP_CONFIG_KEYS
        if transport_type == "loopback_http"
        else _LOCAL_CONFIG_KEYS
    )
    if not set(config_values).issubset(allowed_keys):
        raise RetrievalAdapterError("local retrieval config contains unsupported fields")
    if "transport_type" not in config_values:
        raise RetrievalAdapterError("local retrieval config requires transport_type")

    raw_capabilities = config_values.get("capabilities", {})
    if not isinstance(raw_capabilities, Mapping):
        raise RetrievalAdapterError("local retrieval capabilities must be a mapping")
    capability_values = dict(raw_capabilities)
    if not set(capability_values).issubset(_LOCAL_CAPABILITY_KEYS):
        raise RetrievalAdapterError("local retrieval capabilities contain unsupported fields")

    try:
        capabilities = LocalRetrievalCapabilities(**capability_values)
        if transport_type == "loopback_http":
            from ragguard.compatibility import CompatibilityProfileSelection
            from ragguard.http_contract import parse_local_http_endpoint

            required_fields = {
                "endpoint",
                "connect_timeout",
                "read_timeout",
                "total_timeout",
            }
            if not required_fields.issubset(config_values):
                raise RetrievalAdapterError("loopback HTTP config is incomplete")
            endpoint = parse_local_http_endpoint(
                config_values["endpoint"],
                connect_timeout=config_values["connect_timeout"],
                read_timeout=config_values["read_timeout"],
                total_timeout=config_values["total_timeout"],
                response_size_limit=config_values.get(
                    "response_size_limit", 262_144
                ),
                allowlisted_hostnames=config_values.get(
                    "allowlisted_hostnames", ()
                ),
            )
            raw_profile = config_values.get("compatibility_profile")
            profile_selection = (
                None
                if raw_profile is None
                else CompatibilityProfileSelection.from_mapping(raw_profile)
            )
            return LocalRetrievalConfig(
                transport_type=transport_type,
                timeout_seconds=config_values["total_timeout"],
                default_top_k=config_values.get("default_top_k", 5),
                response_size_limit=config_values.get(
                    "response_size_limit", 262_144
                ),
                capabilities=capabilities,
                http_endpoint=endpoint,
                compatibility_profile=profile_selection,
                configured=True,
            )
        return LocalRetrievalConfig(
            transport_type=config_values["transport_type"],
            timeout_seconds=config_values.get("timeout_seconds", 3.0),
            default_top_k=config_values.get("default_top_k", 5),
            response_size_limit=config_values.get("response_size_limit", 262_144),
            capabilities=capabilities,
            configured=True,
        )
    except TypeError as exc:
        raise RetrievalAdapterError("local retrieval config has invalid field types") from exc


@dataclass(frozen=True)
class LocalRetrievalRequest:
    """Bounded query request passed to a future local transport."""

    query: str
    top_k: int
    query_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise RetrievalAdapterError("local retrieval query must be a non-empty string")
        if len(self.query) > MAX_LOCAL_QUERY_LENGTH:
            raise RetrievalAdapterError("local retrieval query exceeds the size limit")
        _validate_positive_integer(self.top_k, "top_k", MAX_LOCAL_TOP_K)
        if self.query_id is not None:
            _validate_safe_identifier(self.query_id, "query_id")


@dataclass(frozen=True)
class LocalRetrievalResult:
    """Transport response item before normalization to RankedResult."""

    rank: int
    document_id: str
    score: int | float
    title: str
    source_id: str
    matched_keywords: Sequence[str] = ()
    metadata: Mapping[str, str | int | float | bool] | None = None

    def __post_init__(self) -> None:
        _validate_positive_integer(self.rank, "rank")
        _validate_safe_identifier(self.document_id, "document_id")
        _validate_positive_finite_number(self.score, "score", allow_zero=True)
        if not isinstance(self.title, str) or not self.title.strip():
            raise RetrievalAdapterError("title must be a non-empty string")
        if len(self.title) > MAX_LOCAL_TITLE_LENGTH:
            raise RetrievalAdapterError("title exceeds the size limit")
        _validate_safe_identifier(self.source_id, "source_id")

        if isinstance(self.matched_keywords, (str, bytes)) or not isinstance(
            self.matched_keywords, Sequence
        ):
            raise RetrievalAdapterError("matched_keywords must be a sequence of strings")
        keywords = tuple(self.matched_keywords)
        if len(keywords) > MAX_LOCAL_KEYWORDS or not all(
            isinstance(keyword, str)
            and bool(keyword.strip())
            and len(keyword) <= MAX_LOCAL_KEYWORD_LENGTH
            for keyword in keywords
        ):
            raise RetrievalAdapterError("matched_keywords contains invalid values")
        object.__setattr__(self, "matched_keywords", keywords)

        if self.metadata is not None:
            if not isinstance(self.metadata, Mapping):
                raise RetrievalAdapterError("local result metadata must be a mapping")
            metadata = dict(self.metadata)
            if not set(metadata).issubset(LOCAL_RESPONSE_METADATA_KEYS):
                raise RetrievalAdapterError("local result metadata contains unsupported keys")
            if not all(_is_safe_metadata_value(value) for value in metadata.values()):
                raise RetrievalAdapterError("local result metadata contains invalid values")
            object.__setattr__(self, "metadata", MappingProxyType(metadata))


@dataclass(frozen=True)
class LocalRetrievalResponse:
    """Bounded local transport response containing deterministic ranked items."""

    results: Sequence[LocalRetrievalResult]

    def __post_init__(self) -> None:
        if isinstance(self.results, (str, bytes)) or not isinstance(self.results, Sequence):
            raise RetrievalAdapterError("local response results must be a sequence")
        results = tuple(self.results)
        seen_document_ids: set[str] = set()
        for expected_rank, result in enumerate(results, start=1):
            if not isinstance(result, LocalRetrievalResult):
                raise RetrievalAdapterError("local response must use LocalRetrievalResult")
            if result.rank != expected_rank:
                raise RetrievalAdapterError("local response ranks must be contiguous")
            if result.document_id in seen_document_ids:
                raise RetrievalAdapterError("local response contains duplicate document_id values")
            seen_document_ids.add(result.document_id)
        object.__setattr__(self, "results", results)


@runtime_checkable
class LocalRetrievalTransport(Protocol):
    """Lifecycle contract for bounded local-only retrieval transports."""

    def initialize(self, config: LocalRetrievalConfig) -> None: ...

    def health_check(self) -> bool: ...

    def capabilities(self) -> LocalRetrievalCapabilities: ...

    def retrieve(self, request: LocalRetrievalRequest) -> LocalRetrievalResponse: ...

    def close(self) -> None: ...


class InMemoryLocalRetrievalTransport:
    """Deterministic no-I/O transport for local contract and error-boundary tests."""

    transport_type = "in_memory"

    def __init__(
        self,
        response: LocalRetrievalResponse | None = None,
        *,
        capabilities: LocalRetrievalCapabilities | None = None,
        health_failure: bool = False,
        error_mode: str | None = None,
    ) -> None:
        if response is not None and not isinstance(response, LocalRetrievalResponse):
            raise RetrievalAdapterError("in-memory response must use LocalRetrievalResponse")
        if capabilities is not None and not isinstance(
            capabilities, LocalRetrievalCapabilities
        ):
            raise RetrievalAdapterError(
                "in-memory capabilities must use LocalRetrievalCapabilities"
            )
        if type(health_failure) is not bool:
            raise RetrievalAdapterError("health_failure must be boolean")
        if error_mode is not None and error_mode not in IN_MEMORY_ERROR_MODES:
            raise RetrievalAdapterError("unsupported in-memory error mode")

        self._response = response or _default_in_memory_response()
        self._capabilities = capabilities or LocalRetrievalCapabilities(
            matched_keywords=True
        )
        self._health_failure = health_failure
        self._error_mode = error_mode
        self._state = "created"

    @property
    def state(self) -> str:
        """Expose only the bounded lifecycle state."""
        return self._state

    def initialize(self, config: LocalRetrievalConfig) -> None:
        if not isinstance(config, LocalRetrievalConfig):
            raise RetrievalAdapterError("in-memory transport requires LocalRetrievalConfig")
        if self._state == "initialized":
            raise RetrievalAdapterError("in-memory transport is already initialized")
        if self._state == "closed":
            raise RetrievalAdapterError("in-memory transport is closed")
        _validate_required_capabilities(config.capabilities, self._capabilities)
        self._state = "initialized"

    def health_check(self) -> bool:
        self._require_initialized()
        if self._health_failure:
            raise RetrievalAdapterError("in-memory transport health check failed")
        return True

    def capabilities(self) -> LocalRetrievalCapabilities:
        self._require_initialized()
        return self._capabilities

    def retrieve(self, request: LocalRetrievalRequest) -> LocalRetrievalResponse:
        self._require_initialized()
        if not isinstance(request, LocalRetrievalRequest):
            raise RetrievalAdapterError("in-memory transport requires LocalRetrievalRequest")
        if self._error_mode == "timeout":
            raise RetrievalAdapterError("in-memory transport timed out")
        if self._error_mode == "transport_exception":
            raise RuntimeError("simulated private transport detail")
        if self._error_mode == "invalid_response":
            return cast(LocalRetrievalResponse, object())
        if self._error_mode == "oversized_response":
            return _oversized_in_memory_response()

        return LocalRetrievalResponse(results=self._response.results[: request.top_k])

    def close(self) -> None:
        # Closing an unused or already closed fake transport is intentionally idempotent.
        self._state = "closed"

    def _require_initialized(self) -> None:
        if self._state == "created":
            raise RetrievalAdapterError("in-memory transport is not initialized")
        if self._state == "closed":
            raise RetrievalAdapterError("in-memory transport is closed")


@dataclass(frozen=True)
class RankedResult:
    rank: int
    document_id: str
    score: int | float
    matched_keywords: list[str]
    title: str
    source_path: str
    adapter_metadata: Mapping[str, Any] | None = None


class RetrievalQuery(Protocol):
    """Query fields that retrieval may use without benchmark expectations."""

    question: str
    expected_keywords: list[str]
    expected_answer_hint: str


class RetrievalDocument(Protocol):
    """Document fields used by deterministic synthetic retrieval."""

    document_id: str
    title: str
    tags: list[str]
    content: str
    expected_searchable_facts: list[str]
    file: str


@runtime_checkable
class RetrievalAdapter(Protocol):
    """Retrieval-only contract; benchmark evaluation remains outside adapters."""

    name: str

    def retrieve(self, query: RetrievalQuery, top_k: int) -> Sequence[RankedResult]:
        """Return deterministically ordered results with contiguous one-based ranks."""
        ...


class SyntheticRetrievalAdapter:
    """Deterministic keyword retrieval over synthetic benchmark documents."""

    name = "synthetic"

    def __init__(self, documents: Sequence[RetrievalDocument]) -> None:
        self._documents = tuple(documents)

    def retrieve(
        self,
        query: RetrievalQuery,
        top_k: int | None = None,
    ) -> list[RankedResult]:
        if top_k is not None and (
            isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1
        ):
            raise RetrievalAdapterError("top_k must be a positive integer")

        query_terms = query_search_terms(query)
        scored: list[tuple[int, str, str, RetrievalDocument, list[str]]] = []
        for document in self._documents:
            matched_keywords = matched_document_keywords(query_terms, document)
            if not matched_keywords:
                continue
            score = len(matched_keywords)
            scored.append((score, document.document_id, document.file, document, matched_keywords))

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        limited = scored if top_k is None else scored[:top_k]
        return [
            RankedResult(
                rank=index,
                document_id=document.document_id,
                score=score,
                matched_keywords=matched_keywords,
                title=document.title,
                source_path=document.file,
            )
            for index, (score, _document_id, _file, document, matched_keywords) in enumerate(
                limited, start=1
            )
        ]


class LocalRAGRetrievalAdapter:
    """One-shot local adapter client for explicitly configured bounded transports."""

    name = "local-rag"

    def __init__(
        self,
        configuration: LocalRetrievalConfig | Mapping[str, Any] | None = None,
        transport: LocalRetrievalTransport | None = None,
    ) -> None:
        if transport is not None and (
            not isinstance(transport, LocalRetrievalTransport)
            or getattr(transport, "transport_type", None) not in LOCAL_TRANSPORT_TYPES
        ):
            raise RetrievalAdapterError("unsupported local retrieval transport")

        # Legacy mappings remain presence-only for compatibility and are never retained.
        self._legacy_configured = isinstance(configuration, Mapping)
        self._configuration = (
            configuration if isinstance(configuration, LocalRetrievalConfig) else None
        )
        self._transport = transport
        self._closed = False

    def retrieve(self, query: RetrievalQuery, top_k: int) -> list[RankedResult]:
        if self._closed:
            raise RetrievalAdapterError("local retrieval adapter is closed")
        if self._configuration is None:
            if self._legacy_configured:
                self._release_state()
                raise RetrievalAdapterError("local retrieval adapter dependency is unavailable")
            self._release_state()
            raise RetrievalAdapterError("local retrieval adapter is not configured")
        if not self._configuration.configured:
            self._release_state()
            raise RetrievalAdapterError("local retrieval adapter is not configured")
        if self._transport is None:
            self._release_state()
            raise RetrievalAdapterError("local retrieval adapter dependency is unavailable")

        configuration = self._configuration
        transport = self._transport
        results: list[RankedResult] | None = None
        failure: RetrievalAdapterError | None = None
        close_failure: RetrievalAdapterError | None = None

        try:
            if getattr(transport, "transport_type", None) != configuration.transport_type:
                raise RetrievalAdapterError(
                    "local retrieval transport does not match config"
                )
            request = LocalRetrievalRequest(
                query=query.question,
                top_k=top_k,
                query_id=getattr(query, "query_id", None),
            )
            _initialize_local_transport(transport, configuration)
            _check_local_transport_health(transport)
            _check_local_transport_capabilities(transport, configuration.capabilities)
            results = retrieve_local_and_normalize(transport, request, configuration)
        except RetrievalAdapterError as exc:
            failure = exc
        except Exception:
            failure = RetrievalAdapterError("local retrieval adapter failed")

        try:
            transport.close()
        except Exception:
            close_failure = RetrievalAdapterError("local retrieval adapter close failed")
        finally:
            self._release_state()

        if failure is not None:
            raise failure
        if close_failure is not None:
            raise close_failure
        if results is None:
            raise RetrievalAdapterError("local retrieval adapter returned no result state")
        return results

    def _release_state(self) -> None:
        self._configuration = None
        self._transport = None
        self._legacy_configured = False
        self._closed = True


def normalize_local_response(
    response: LocalRetrievalResponse,
    *,
    top_k: int,
    response_size_limit: int,
) -> list[RankedResult]:
    """Validate a bounded local response and map safe fields to RankedResult."""
    if not isinstance(response, LocalRetrievalResponse):
        raise RetrievalAdapterError("local transport returned an invalid response")
    _validate_positive_integer(top_k, "top_k", MAX_LOCAL_TOP_K)
    _validate_positive_integer(
        response_size_limit,
        "response_size_limit",
        MAX_LOCAL_RESPONSE_SIZE,
    )
    if len(response.results) > top_k:
        raise RetrievalAdapterError("local response returned more results than top_k")
    if _local_response_size(response) > response_size_limit:
        raise RetrievalAdapterError("local response exceeds the size limit")

    ranked_results = [
        RankedResult(
            rank=result.rank,
            document_id=result.document_id,
            score=result.score,
            matched_keywords=list(result.matched_keywords),
            title=result.title,
            source_path=result.source_id,
            adapter_metadata=result.metadata,
        )
        for result in response.results
    ]
    return validate_ranked_results(ranked_results, top_k)


def retrieve_local_and_normalize(
    transport: LocalRetrievalTransport,
    request: LocalRetrievalRequest,
    config: LocalRetrievalConfig,
) -> list[RankedResult]:
    """Execute one local transport request through a bounded error and result boundary."""
    if not isinstance(transport, LocalRetrievalTransport):
        raise RetrievalAdapterError("invalid local retrieval transport")
    if not isinstance(request, LocalRetrievalRequest):
        raise RetrievalAdapterError("invalid local retrieval request")
    if not isinstance(config, LocalRetrievalConfig):
        raise RetrievalAdapterError("invalid local retrieval config")
    try:
        response = transport.retrieve(request)
    except RetrievalAdapterError:
        raise
    except Exception as exc:
        raise RetrievalAdapterError("local transport retrieval failed") from exc
    return normalize_local_response(
        response,
        top_k=request.top_k,
        response_size_limit=config.response_size_limit,
    )


def _initialize_local_transport(
    transport: LocalRetrievalTransport,
    config: LocalRetrievalConfig,
) -> None:
    try:
        transport.initialize(config)
    except RetrievalAdapterError:
        raise
    except Exception as exc:
        raise RetrievalAdapterError("local transport initialization failed") from exc


def _check_local_transport_health(transport: LocalRetrievalTransport) -> None:
    try:
        healthy = transport.health_check()
    except RetrievalAdapterError:
        raise
    except Exception as exc:
        raise RetrievalAdapterError("local transport health check failed") from exc
    if healthy is not True:
        raise RetrievalAdapterError("local transport health check failed")


def _check_local_transport_capabilities(
    transport: LocalRetrievalTransport,
    required: LocalRetrievalCapabilities,
) -> None:
    try:
        available = transport.capabilities()
    except RetrievalAdapterError:
        raise
    except Exception as exc:
        raise RetrievalAdapterError("local transport capability check failed") from exc
    if not isinstance(available, LocalRetrievalCapabilities):
        raise RetrievalAdapterError("local transport returned invalid capabilities")
    _validate_required_capabilities(required, available)


def retrieve_and_validate(
    adapter: RetrievalAdapter,
    query: RetrievalQuery,
    top_k: int,
) -> list[RankedResult]:
    """Run any adapter and validate its output before evaluation."""
    try:
        results = adapter.retrieve(query, top_k)
    except RetrievalAdapterError:
        raise
    except Exception as exc:
        raise RetrievalAdapterError("adapter retrieval failed") from exc
    return validate_ranked_results(results, top_k)


def validate_ranked_results(
    results: Sequence[RankedResult],
    top_k: int,
) -> list[RankedResult]:
    """Validate and normalize adapter output before benchmark evaluation."""
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise RetrievalAdapterError("top_k must be a positive integer")
    if isinstance(results, (str, bytes)) or not isinstance(results, Sequence):
        raise RetrievalAdapterError("adapter results must be a sequence")
    if len(results) > top_k:
        raise RetrievalAdapterError("adapter returned more results than top_k")

    validated = list(results)
    seen_document_ids: set[str] = set()
    for expected_rank, result in enumerate(validated, start=1):
        if not isinstance(result, RankedResult):
            raise RetrievalAdapterError("adapter result must use RankedResult")
        _validate_ranked_result(result, expected_rank)
        if result.document_id in seen_document_ids:
            raise RetrievalAdapterError("adapter results contain duplicate document_id values")
        seen_document_ids.add(result.document_id)
    return validated


def _validate_ranked_result(result: RankedResult, expected_rank: int) -> None:
    if isinstance(result.rank, bool) or not isinstance(result.rank, int) or result.rank < 1:
        raise RetrievalAdapterError("rank must be an integer greater than or equal to 1")
    if result.rank != expected_rank:
        raise RetrievalAdapterError("ranks must be contiguous and match result order")

    for field_name in ("document_id", "title", "source_path"):
        value = getattr(result, field_name)
        if not isinstance(value, str) or not value.strip():
            raise RetrievalAdapterError(f"{field_name} must be a non-empty string")

    if isinstance(result.score, bool) or not isinstance(result.score, (int, float)):
        raise RetrievalAdapterError("score must be numeric")
    if not math.isfinite(float(result.score)):
        raise RetrievalAdapterError("score must be finite")

    if not isinstance(result.matched_keywords, list) or not all(
        isinstance(keyword, str) for keyword in result.matched_keywords
    ):
        raise RetrievalAdapterError("matched_keywords must be a list of strings")

    if result.adapter_metadata is not None and not isinstance(result.adapter_metadata, Mapping):
        raise RetrievalAdapterError("adapter_metadata must be a mapping when provided")


def _validate_required_capabilities(
    required: LocalRetrievalCapabilities,
    available: LocalRetrievalCapabilities,
) -> None:
    if required.ranked_results and not available.ranked_results:
        raise RetrievalAdapterError("in-memory transport lacks a required capability")
    if required.matched_keywords and not available.matched_keywords:
        raise RetrievalAdapterError("in-memory transport lacks a required capability")
    if required.filters and not available.filters:
        raise RetrievalAdapterError("in-memory transport lacks a required capability")


def _validate_positive_integer(value: Any, field_name: str, maximum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RetrievalAdapterError(f"{field_name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise RetrievalAdapterError(f"{field_name} exceeds the allowed limit")


def _validate_positive_finite_number(
    value: Any,
    field_name: str,
    maximum: float | None = None,
    *,
    allow_zero: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RetrievalAdapterError(f"{field_name} must be numeric")
    numeric_value = float(value)
    minimum_valid = numeric_value >= 0 if allow_zero else numeric_value > 0
    if not math.isfinite(numeric_value) or not minimum_valid:
        raise RetrievalAdapterError(f"{field_name} must be a positive finite number")
    if maximum is not None and numeric_value > maximum:
        raise RetrievalAdapterError(f"{field_name} exceeds the allowed limit")


def _validate_safe_identifier(value: Any, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) > MAX_LOCAL_IDENTIFIER_LENGTH
        or not _SAFE_IDENTIFIER.fullmatch(value)
    ):
        raise RetrievalAdapterError(f"{field_name} must be a safe identifier")


def _is_safe_metadata_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return not isinstance(value, bool) and math.isfinite(float(value))
    return isinstance(value, str) and len(value) <= MAX_LOCAL_METADATA_VALUE_LENGTH


def _local_response_size(response: LocalRetrievalResponse) -> int:
    payload = [
        {
            "rank": result.rank,
            "document_id": result.document_id,
            "score": result.score,
            "title": result.title,
            "source_id": result.source_id,
            "matched_keywords": list(result.matched_keywords),
            "metadata": dict(result.metadata) if result.metadata is not None else None,
        }
        for result in response.results
    ]
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _default_in_memory_response() -> LocalRetrievalResponse:
    return LocalRetrievalResponse(
        results=(
            LocalRetrievalResult(
                rank=1,
                document_id="synthetic-local-doc-001",
                score=1.0,
                title="Synthetic Local Document",
                source_id="synthetic-local-source-001",
                matched_keywords=("synthetic",),
                metadata={"transport": "in_memory", "result_type": "synthetic"},
            ),
        )
    )


def _oversized_in_memory_response() -> LocalRetrievalResponse:
    return LocalRetrievalResponse(
        results=(
            LocalRetrievalResult(
                rank=1,
                document_id="synthetic-local-oversized-001",
                score=1.0,
                title="S" * MAX_LOCAL_TITLE_LENGTH,
                source_id="synthetic-local-source-oversized-001",
                matched_keywords=tuple(
                    f"synthetic-{index:03d}-" + "x" * 110
                    for index in range(MAX_LOCAL_KEYWORDS)
                ),
                metadata={"transport": "in_memory", "result_type": "synthetic"},
            ),
        )
    )


def query_search_terms(query: RetrievalQuery) -> list[str]:
    terms = tokenize(query.question)
    for keyword in query.expected_keywords:
        terms.extend(tokenize(keyword))
    if query.expected_answer_hint:
        terms.extend(tokenize(query.expected_answer_hint))
    return sorted(set(terms))


def matched_document_keywords(
    query_terms: list[str],
    document: RetrievalDocument,
) -> list[str]:
    searchable_text = " ".join(
        [
            document.document_id,
            document.title,
            " ".join(document.tags),
            " ".join(document.expected_searchable_facts),
            document.content,
        ]
    )
    document_terms = set(tokenize(searchable_text))
    return [term for term in query_terms if term in document_terms]


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", text)]
