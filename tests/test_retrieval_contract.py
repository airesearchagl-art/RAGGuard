from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from ragguard.benchmark import (
    BenchmarkError,
    build_placeholder_result,
    load_corpus,
    load_queries,
    ranked_result_to_dict,
)
from ragguard.retrieval import (
    RankedResult,
    RetrievalAdapter,
    RetrievalAdapterError,
    RetrievalQuery,
    SyntheticRetrievalAdapter,
    retrieve_and_validate,
    validate_ranked_results,
)


BENCHMARK_FIXTURES = Path(__file__).parent / "fixtures" / "benchmark"


def make_result(**overrides: Any) -> RankedResult:
    values: dict[str, Any] = {
        "rank": 1,
        "document_id": "synthetic-doc-001",
        "score": 1,
        "matched_keywords": ["synthetic"],
        "title": "Synthetic Document",
        "source_path": "synthetic.md",
    }
    values.update(overrides)
    return RankedResult(**values)


class MockRetrievalAdapter:
    name = "mock"

    def __init__(
        self,
        results: list[RankedResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = list(results or [])
        self.error = error
        self.calls: list[tuple[RetrievalQuery, int]] = []

    def retrieve(self, query: RetrievalQuery, top_k: int) -> list[RankedResult]:
        self.calls.append((query, top_k))
        if self.error is not None:
            raise self.error
        return list(self.results)


def test_retrieval_adapter_contract_and_required_fields() -> None:
    adapter = MockRetrievalAdapter([make_result()])
    result = adapter.retrieve(object(), 1)  # type: ignore[arg-type]

    assert isinstance(adapter, RetrievalAdapter)
    assert {
        "rank",
        "document_id",
        "score",
        "matched_keywords",
        "title",
        "source_path",
    } <= asdict(result[0]).keys()
    assert validate_ranked_results(result, 1) == result


@pytest.mark.parametrize(
    "results",
    [
        [],
        [make_result()],
        [
            make_result(),
            make_result(rank=2, document_id="synthetic-doc-002", source_path="second.md"),
        ],
    ],
)
def test_mock_adapter_accepts_valid_empty_single_and_multiple_results(
    results: list[RankedResult],
) -> None:
    adapter = MockRetrievalAdapter(results)

    assert retrieve_and_validate(adapter, object(), max(1, len(results))) == results  # type: ignore[arg-type]


def test_mock_adapter_is_deterministic_and_receives_top_k() -> None:
    results = [make_result()]
    adapter = MockRetrievalAdapter(results)
    query = object()

    first = retrieve_and_validate(adapter, query, 1)  # type: ignore[arg-type]
    second = retrieve_and_validate(adapter, query, 1)  # type: ignore[arg-type]

    assert first == second == results
    assert adapter.calls == [(query, 1), (query, 1)]


def test_adapter_metadata_is_optional_and_omitted_from_legacy_report_shape() -> None:
    without_metadata = make_result()
    with_metadata = make_result(adapter_metadata={"strategy": "synthetic"})

    assert retrieve_and_validate(MockRetrievalAdapter([without_metadata]), object(), 1) == [  # type: ignore[arg-type]
        without_metadata
    ]
    assert retrieve_and_validate(MockRetrievalAdapter([with_metadata]), object(), 1) == [  # type: ignore[arg-type]
        with_metadata
    ]
    assert without_metadata.adapter_metadata is None
    assert "adapter_metadata" not in ranked_result_to_dict(without_metadata)
    assert ranked_result_to_dict(with_metadata)["adapter_metadata"] == {"strategy": "synthetic"}


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (make_result(rank=0), "rank"),
        (make_result(document_id=1), "document_id"),
        (make_result(score="high"), "score"),
        (make_result(score=True), "score"),
        (make_result(matched_keywords=["valid", 1]), "matched_keywords"),
        (make_result(title=None), "title"),
        (make_result(source_path=[]), "source_path"),
        (make_result(adapter_metadata=[]), "adapter_metadata"),
    ],
)
def test_invalid_ranked_result_fields_are_rejected(result: RankedResult, message: str) -> None:
    with pytest.raises(RetrievalAdapterError, match=message):
        validate_ranked_results([result], 1)


def test_ranked_results_require_contiguous_deterministic_order() -> None:
    out_of_order = [
        make_result(rank=1),
        make_result(rank=3, document_id="synthetic-doc-002", source_path="second.md"),
    ]

    with pytest.raises(RetrievalAdapterError, match="contiguous"):
        validate_ranked_results(out_of_order, 2)


def test_ranked_results_reject_duplicate_document_ids() -> None:
    duplicated = [make_result(), make_result(rank=2, source_path="second.md")]

    with pytest.raises(RetrievalAdapterError, match="duplicate document_id"):
        validate_ranked_results(duplicated, 2)


def test_mock_adapter_rejects_results_over_top_k() -> None:
    adapter = MockRetrievalAdapter(
        [make_result(), make_result(rank=2, document_id="synthetic-doc-002", source_path="second.md")]
    )

    with pytest.raises(RetrievalAdapterError, match="more results than top_k"):
        retrieve_and_validate(adapter, object(), 1)  # type: ignore[arg-type]


def test_synthetic_adapter_honors_top_k_and_keeps_stable_order() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")[0]
    adapter = SyntheticRetrievalAdapter(documents)

    first = adapter.retrieve(query, 1)
    second = adapter.retrieve(query, 1)

    assert first == second
    assert len(first) == 1
    assert first[0].rank == 1


def test_synthetic_adapter_returns_ranked_result_contract() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")[0]
    adapter = SyntheticRetrievalAdapter(documents)

    results = retrieve_and_validate(adapter, query, 1)

    assert isinstance(adapter, RetrievalAdapter)
    assert len(results) == 1
    assert isinstance(results[0], RankedResult)
    assert results[0].adapter_metadata is None


def test_synthetic_adapter_top_k_limits_results() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")[0]

    results = retrieve_and_validate(SyntheticRetrievalAdapter(documents), query, 1)

    assert [result.rank for result in results] == [1]


def test_ranked_result_model_does_not_include_evaluator_fields() -> None:
    fields = asdict(make_result()).keys()

    assert "evaluation_status" not in fields
    assert "hit_at_k" not in fields
    assert "source_match" not in fields
    assert "keyword_coverage_rate" not in fields


def test_invalid_adapter_result_becomes_benchmark_error() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    queries = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")

    class InvalidAdapter:
        name = "invalid"

        def retrieve(self, query: RetrievalQuery, top_k: int) -> list[RankedResult]:
            del query, top_k
            return [make_result(rank=2)]

    with pytest.raises(BenchmarkError, match="Invalid retrieval result from adapter invalid"):
        build_placeholder_result(documents, queries, InvalidAdapter())


def test_adapter_exception_becomes_bounded_benchmark_error() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    queries = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")
    adapter = MockRetrievalAdapter(error=RuntimeError("sensitive backend detail"))

    with pytest.raises(BenchmarkError, match="Invalid retrieval result from adapter mock") as exc_info:
        build_placeholder_result(documents, queries, adapter)

    assert "sensitive backend detail" not in str(exc_info.value)
