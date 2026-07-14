from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


class RetrievalAdapterError(ValueError):
    """Raised when an adapter violates the retrieval contract."""


LOCAL_TRANSPORT_TYPES = frozenset({"in_memory"})
LOCAL_RESPONSE_METADATA_KEYS = frozenset(
    {"capability", "match_type", "result_type", "transport"}
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
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


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
        if type(self.configured) is not bool:
            raise RetrievalAdapterError("configured must be boolean")


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
    """Lifecycle contract only; Phase A provides no transport implementation."""

    def initialize(self, config: LocalRetrievalConfig) -> None: ...

    def health_check(self) -> bool: ...

    def capabilities(self) -> LocalRetrievalCapabilities: ...

    def retrieve(self, request: LocalRetrievalRequest) -> LocalRetrievalResponse: ...

    def close(self) -> None: ...


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
    """Unconnected local-only adapter skeleton with a bounded error surface."""

    name = "local-rag"

    def __init__(
        self,
        configuration: LocalRetrievalConfig | Mapping[str, Any] | None = None,
        transport: LocalRetrievalTransport | None = None,
    ) -> None:
        # Phase A records boundary state only; values and transport objects are not retained.
        self._configured = (
            configuration.configured
            if isinstance(configuration, LocalRetrievalConfig)
            else configuration is not None
        )
        self._transport_provided = transport is not None

    def retrieve(self, query: RetrievalQuery, top_k: int) -> list[RankedResult]:
        del query, top_k
        if not self._configured:
            raise RetrievalAdapterError("local retrieval adapter is not configured")
        if not self._transport_provided:
            raise RetrievalAdapterError("local retrieval adapter dependency is unavailable")
        raise RetrievalAdapterError("local retrieval adapter is not operational")


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
