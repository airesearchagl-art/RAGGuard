from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from ragguard.cli import main
from ragguard.benchmark import (
    BenchmarkError,
    build_placeholder_result,
    load_corpus,
    load_queries,
    ranked_result_to_dict,
)
from ragguard.retrieval import (
    InMemoryLocalRetrievalTransport,
    LocalRetrievalCapabilities,
    LocalRetrievalConfig,
    LocalRetrievalRequest,
    LocalRetrievalResponse,
    LocalRetrievalResult,
    LocalRetrievalTransport,
    LocalRAGRetrievalAdapter,
    RankedResult,
    RetrievalAdapter,
    RetrievalAdapterError,
    RetrievalQuery,
    SyntheticRetrievalAdapter,
    normalize_local_response,
    retrieve_local_and_normalize,
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


class ContractOnlyLocalTransport:
    def initialize(self, config: LocalRetrievalConfig) -> None:
        self.configured = config.configured

    def health_check(self) -> bool:
        return True

    def capabilities(self) -> LocalRetrievalCapabilities:
        return LocalRetrievalCapabilities()

    def retrieve(self, request: LocalRetrievalRequest) -> LocalRetrievalResponse:
        del request
        return LocalRetrievalResponse(results=[])

    def close(self) -> None:
        return None


class InMemoryTransportBackedTestAdapter:
    name = "in-memory-test"

    def __init__(
        self,
        transport: InMemoryLocalRetrievalTransport,
        config: LocalRetrievalConfig,
    ) -> None:
        self.transport = transport
        self.config = config
        self.transport.initialize(config)

    def retrieve(self, query: RetrievalQuery, top_k: int) -> list[RankedResult]:
        request = LocalRetrievalRequest(
            query=query.question,
            top_k=top_k,
            query_id=getattr(query, "query_id", None),
        )
        return retrieve_local_and_normalize(self.transport, request, self.config)


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


def test_local_adapter_skeleton_conforms_to_protocol() -> None:
    assert isinstance(LocalRAGRetrievalAdapter(), RetrievalAdapter)
    assert LocalRAGRetrievalAdapter.name == "local-rag"


def test_local_adapter_skeleton_is_safely_not_configured() -> None:
    adapter = LocalRAGRetrievalAdapter()

    with pytest.raises(RetrievalAdapterError, match="not configured") as exc_info:
        retrieve_and_validate(adapter, object(), 1)  # type: ignore[arg-type]

    assert "path" not in str(exc_info.value).lower()
    assert "token" not in str(exc_info.value).lower()


def test_local_adapter_skeleton_does_not_retain_or_expose_configuration_values() -> None:
    private_path = "X:/private/synthetic-location"
    private_token = "synthetic-secret-value"
    adapter = LocalRAGRetrievalAdapter({"path": private_path, "token": private_token})

    assert not hasattr(adapter, "configuration")
    with pytest.raises(RetrievalAdapterError, match="dependency is unavailable") as exc_info:
        retrieve_and_validate(adapter, object(), 1)  # type: ignore[arg-type]

    message = str(exc_info.value)
    assert private_path not in message
    assert private_token not in message


def test_local_adapter_skeleton_error_becomes_benchmark_error() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    queries = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")

    with pytest.raises(
        BenchmarkError,
        match="Invalid retrieval result from adapter local-rag",
    ) as exc_info:
        build_placeholder_result(documents, queries, LocalRAGRetrievalAdapter())

    message = str(exc_info.value)
    assert "not configured" in message
    assert "synthetic-secret-value" not in message


def test_local_retrieval_config_accepts_safe_in_memory_contract() -> None:
    capabilities = LocalRetrievalCapabilities(
        ranked_results=True,
        matched_keywords=True,
        filters=False,
    )
    config = LocalRetrievalConfig(
        transport_type="in_memory",
        timeout_seconds=2.5,
        default_top_k=10,
        response_size_limit=65_536,
        capabilities=capabilities,
        configured=True,
    )

    assert config.transport_type == "in_memory"
    assert config.capabilities.matched_keywords is True
    assert config.configured is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"timeout_seconds": float("nan")}, "timeout_seconds"),
        ({"timeout_seconds": float("inf")}, "timeout_seconds"),
        ({"timeout_seconds": True}, "timeout_seconds"),
        ({"default_top_k": 0}, "default_top_k"),
        ({"default_top_k": True}, "default_top_k"),
        ({"response_size_limit": 0}, "response_size_limit"),
        ({"response_size_limit": True}, "response_size_limit"),
        ({"transport_type": "localhost_http"}, "unsupported local transport"),
        ({"transport_type": []}, "unsupported local transport"),
        ({"configured": 1}, "configured"),
    ],
)
def test_local_retrieval_config_rejects_unsafe_values(
    overrides: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(RetrievalAdapterError, match=message):
        LocalRetrievalConfig(**overrides)


def test_local_transport_protocol_contract_is_runtime_checkable() -> None:
    transport = ContractOnlyLocalTransport()

    assert isinstance(transport, LocalRetrievalTransport)
    assert transport.health_check() is True
    assert transport.capabilities().ranked_results is True


def test_local_request_and_response_normalize_to_ranked_result() -> None:
    request = LocalRetrievalRequest(query="synthetic question", top_k=1, query_id="q-001")
    response = LocalRetrievalResponse(
        results=[
            LocalRetrievalResult(
                rank=1,
                document_id="synthetic-doc-001",
                score=1.25,
                title="Synthetic Document",
                source_id="synthetic-source-001",
                matched_keywords=["synthetic"],
                metadata={"transport": "in_memory", "match_type": "keyword"},
            )
        ]
    )

    results = normalize_local_response(response, top_k=request.top_k, response_size_limit=4096)

    assert results == [
        RankedResult(
            rank=1,
            document_id="synthetic-doc-001",
            score=1.25,
            title="Synthetic Document",
            source_path="synthetic-source-001",
            matched_keywords=["synthetic"],
            adapter_metadata={"transport": "in_memory", "match_type": "keyword"},
        )
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": "", "top_k": 1},
        {"query": "synthetic", "top_k": True},
        {"query": "synthetic", "top_k": 0},
        {"query": "synthetic", "top_k": 1, "query_id": "../private"},
    ],
)
def test_local_request_rejects_invalid_or_path_like_values(kwargs: dict[str, Any]) -> None:
    with pytest.raises(RetrievalAdapterError):
        LocalRetrievalRequest(**kwargs)


def test_local_response_rejects_paths_and_unapproved_metadata() -> None:
    with pytest.raises(RetrievalAdapterError, match="source_id"):
        LocalRetrievalResult(
            rank=1,
            document_id="synthetic-doc-001",
            score=1,
            title="Synthetic Document",
            source_id="X:/private/source.md",
        )

    with pytest.raises(RetrievalAdapterError, match="unsupported keys"):
        LocalRetrievalResult(
            rank=1,
            document_id="synthetic-doc-001",
            score=1,
            title="Synthetic Document",
            source_id="synthetic-source-001",
            metadata={"credential": "synthetic-secret-value"},
        )


def test_local_response_size_and_top_k_are_enforced() -> None:
    single_response = LocalRetrievalResponse(
        results=[
            LocalRetrievalResult(
                rank=1,
                document_id="synthetic-doc-001",
                score=1,
                title="Synthetic Document",
                source_id="synthetic-source-001",
            )
        ]
    )
    oversized_response = LocalRetrievalResponse(
        results=[
            single_response.results[0],
            LocalRetrievalResult(
                rank=2,
                document_id="synthetic-doc-002",
                score=0.5,
                title="Second Synthetic Document",
                source_id="synthetic-source-002",
            ),
        ]
    )

    with pytest.raises(RetrievalAdapterError, match="size limit"):
        normalize_local_response(single_response, top_k=1, response_size_limit=1)
    with pytest.raises(RetrievalAdapterError, match="more results than top_k"):
        normalize_local_response(oversized_response, top_k=1, response_size_limit=4096)


def test_local_config_and_transport_errors_do_not_expose_values() -> None:
    unsafe_transport = "https://external.invalid/private"
    with pytest.raises(RetrievalAdapterError) as config_error:
        LocalRetrievalConfig(transport_type=unsafe_transport)

    configured = LocalRetrievalConfig(configured=True)
    with pytest.raises(RetrievalAdapterError, match="dependency is unavailable") as adapter_error:
        retrieve_and_validate(LocalRAGRetrievalAdapter(configured), object(), 1)  # type: ignore[arg-type]

    messages = f"{config_error.value} {adapter_error.value}"
    assert unsafe_transport not in messages
    assert "credential" not in messages.lower()
    assert "path" not in messages.lower()


def test_local_adapter_does_not_invoke_provided_transport_in_phase_a() -> None:
    transport = ContractOnlyLocalTransport()
    adapter = LocalRAGRetrievalAdapter(LocalRetrievalConfig(configured=True), transport)

    with pytest.raises(RetrievalAdapterError, match="not operational"):
        retrieve_and_validate(adapter, object(), 1)  # type: ignore[arg-type]

    assert not hasattr(transport, "configured")


def test_in_memory_transport_conforms_and_runs_normal_lifecycle() -> None:
    transport = InMemoryLocalRetrievalTransport()
    config = LocalRetrievalConfig(configured=True)
    request = LocalRetrievalRequest(query="synthetic question", top_k=1, query_id="q-001")

    assert isinstance(transport, LocalRetrievalTransport)
    assert transport.state == "created"

    transport.initialize(config)

    assert transport.state == "initialized"
    assert transport.health_check() is True
    assert transport.capabilities().ranked_results is True
    assert transport.capabilities().matched_keywords is True

    results = retrieve_local_and_normalize(transport, request, config)

    assert len(results) == 1
    assert results[0].document_id == "synthetic-local-doc-001"
    assert results[0].source_path == "synthetic-local-source-001"
    assert results[0].adapter_metadata == {
        "transport": "in_memory",
        "result_type": "synthetic",
    }

    transport.close()
    transport.close()
    assert transport.state == "closed"


def test_in_memory_transport_rejects_retrieve_before_initialize_and_after_close() -> None:
    transport = InMemoryLocalRetrievalTransport()
    request = LocalRetrievalRequest(query="synthetic question", top_k=1)

    with pytest.raises(RetrievalAdapterError, match="not initialized"):
        transport.retrieve(request)

    transport.initialize(LocalRetrievalConfig(configured=True))
    transport.close()

    with pytest.raises(RetrievalAdapterError, match="closed"):
        transport.retrieve(request)


def test_in_memory_transport_rejects_duplicate_initialize_and_initialize_after_close() -> None:
    config = LocalRetrievalConfig(configured=True)
    transport = InMemoryLocalRetrievalTransport()
    transport.initialize(config)

    with pytest.raises(RetrievalAdapterError, match="already initialized"):
        transport.initialize(config)

    transport.close()
    with pytest.raises(RetrievalAdapterError, match="closed"):
        transport.initialize(config)


def test_in_memory_transport_health_failure_is_bounded() -> None:
    transport = InMemoryLocalRetrievalTransport(health_failure=True)
    transport.initialize(LocalRetrievalConfig(configured=True))

    with pytest.raises(RetrievalAdapterError, match="health check failed"):
        transport.health_check()


def test_in_memory_transport_rejects_unsupported_required_capability() -> None:
    transport = InMemoryLocalRetrievalTransport(
        capabilities=LocalRetrievalCapabilities(
            ranked_results=True,
            matched_keywords=True,
            filters=False,
        )
    )
    config = LocalRetrievalConfig(
        capabilities=LocalRetrievalCapabilities(
            ranked_results=True,
            matched_keywords=True,
            filters=True,
        ),
        configured=True,
    )

    with pytest.raises(RetrievalAdapterError, match="required capability"):
        transport.initialize(config)

    assert transport.state == "created"


def test_in_memory_transport_timeout_is_bounded() -> None:
    config = LocalRetrievalConfig(configured=True)
    transport = InMemoryLocalRetrievalTransport(error_mode="timeout")
    transport.initialize(config)

    with pytest.raises(RetrievalAdapterError, match="timed out"):
        retrieve_local_and_normalize(
            transport,
            LocalRetrievalRequest(query="synthetic question", top_k=1),
            config,
        )


def test_in_memory_transport_invalid_response_is_rejected() -> None:
    config = LocalRetrievalConfig(configured=True)
    transport = InMemoryLocalRetrievalTransport(error_mode="invalid_response")
    transport.initialize(config)

    with pytest.raises(RetrievalAdapterError, match="invalid response"):
        retrieve_local_and_normalize(
            transport,
            LocalRetrievalRequest(query="synthetic question", top_k=1),
            config,
        )


def test_in_memory_transport_oversized_response_is_rejected() -> None:
    config = LocalRetrievalConfig(response_size_limit=1024, configured=True)
    transport = InMemoryLocalRetrievalTransport(error_mode="oversized_response")
    transport.initialize(config)

    with pytest.raises(RetrievalAdapterError, match="size limit"):
        retrieve_local_and_normalize(
            transport,
            LocalRetrievalRequest(query="synthetic question", top_k=1),
            config,
        )


def test_in_memory_transport_exception_hides_raw_details() -> None:
    config = LocalRetrievalConfig(configured=True)
    transport = InMemoryLocalRetrievalTransport(error_mode="transport_exception")
    transport.initialize(config)

    with pytest.raises(RetrievalAdapterError, match="local transport retrieval failed") as exc_info:
        retrieve_local_and_normalize(
            transport,
            LocalRetrievalRequest(query="synthetic question", top_k=1),
            config,
        )

    message = str(exc_info.value)
    assert "private transport detail" not in message
    assert "credential" not in message.lower()
    assert "path" not in message.lower()


def test_in_memory_transport_response_is_deterministic_and_top_k_bounded() -> None:
    response = LocalRetrievalResponse(
        results=[
            LocalRetrievalResult(
                rank=1,
                document_id="synthetic-local-doc-001",
                score=2,
                title="First Synthetic Document",
                source_id="synthetic-local-source-001",
                matched_keywords=["first"],
                metadata={"transport": "in_memory"},
            ),
            LocalRetrievalResult(
                rank=2,
                document_id="synthetic-local-doc-002",
                score=1,
                title="Second Synthetic Document",
                source_id="synthetic-local-source-002",
                matched_keywords=["second"],
            ),
        ]
    )
    config = LocalRetrievalConfig(configured=True)
    transport = InMemoryLocalRetrievalTransport(response=response)
    transport.initialize(config)
    request = LocalRetrievalRequest(query="synthetic question", top_k=1)

    first = retrieve_local_and_normalize(transport, request, config)
    second = retrieve_local_and_normalize(transport, request, config)

    assert first == second
    assert [result.rank for result in first] == [1]
    assert [result.document_id for result in first] == ["synthetic-local-doc-001"]


def test_in_memory_transport_error_reaches_benchmark_error_boundary() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    queries = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")
    adapter = InMemoryTransportBackedTestAdapter(
        InMemoryLocalRetrievalTransport(error_mode="transport_exception"),
        LocalRetrievalConfig(configured=True),
    )

    with pytest.raises(BenchmarkError, match="Invalid retrieval result") as exc_info:
        build_placeholder_result(documents, queries, adapter)

    assert "private transport detail" not in str(exc_info.value)


def test_in_memory_transport_error_reaches_cli_error_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = InMemoryTransportBackedTestAdapter(
        InMemoryLocalRetrievalTransport(error_mode="transport_exception"),
        LocalRetrievalConfig(configured=True),
    )
    monkeypatch.setattr("ragguard.benchmark.SyntheticRetrievalAdapter", lambda documents: adapter)

    code = main(
        [
            "benchmark",
            "--corpus",
            str(BENCHMARK_FIXTURES / "corpus"),
            "--queries",
            str(BENCHMARK_FIXTURES / "queries.jsonl"),
            "--output",
            str(tmp_path / "out"),
        ]
    )

    assert code == 3
    assert not (tmp_path / "out" / "benchmark_report.json").exists()


def test_in_memory_transport_keeps_synthetic_adapter_behavior_unchanged() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")[0]

    results = retrieve_and_validate(SyntheticRetrievalAdapter(documents), query, 1)

    assert results[0].document_id == "sample-policy-001"
    assert results[0].adapter_metadata is None
