from __future__ import annotations

import math
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


@runtime_checkable
class RetrievalAdapter(Protocol):
    """Retrieval-only contract; benchmark evaluation remains outside adapters."""

    name: str

    def retrieve(self, query: RetrievalQuery, top_k: int) -> Sequence[RankedResult]:
        """Return deterministically ordered results with contiguous one-based ranks."""
        ...


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
