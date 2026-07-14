from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class RetrievalAdapterError(ValueError):
    """Raised when an adapter violates the retrieval contract."""


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

    def __init__(self, configuration: Mapping[str, Any] | None = None) -> None:
        # Phase D records configuration presence only; values are never read or retained.
        self._configured = configuration is not None

    def retrieve(self, query: RetrievalQuery, top_k: int) -> list[RankedResult]:
        del query, top_k
        if not self._configured:
            raise RetrievalAdapterError("local retrieval adapter is not configured")
        raise RetrievalAdapterError("local retrieval adapter dependency is unavailable")


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
