from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragguard.benchmark import (
    BenchmarkDocument,
    BenchmarkQuery,
    SyntheticRetrievalAdapter,
    load_corpus,
    load_queries,
)
from ragguard.cli import main


FIXTURES = Path(__file__).parent / "fixtures"
BENCHMARK_FIXTURES = FIXTURES / "benchmark"


def test_benchmark_help_is_available(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["benchmark", "--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "benchmark" in captured.out
    assert "--corpus" in captured.out
    assert "--queries" in captured.out


def test_benchmark_valid_fixture_generates_placeholder_reports(tmp_path: Path) -> None:
    code = main(
        [
            "benchmark",
            "--corpus",
            str(BENCHMARK_FIXTURES / "corpus"),
            "--queries",
            str(BENCHMARK_FIXTURES / "queries.jsonl"),
            "--output",
            str(tmp_path),
        ]
    )

    result = json.loads((tmp_path / "benchmark_report.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "benchmark_report.md").read_text(encoding="utf-8")

    assert code == 0
    assert result["result"] == "PASS"
    assert result["status"] == "PASS"
    assert result["corpus_count"] == 2
    assert result["query_count"] == 3
    assert result["summary"]["corpus_count"] == 2
    assert result["summary"]["query_count"] == 3
    assert result["summary"]["validation_error_count"] == 0
    assert result["summary"]["evaluated_query_count"] == 0
    assert result["summary"]["not_evaluated_query_count"] == 3
    assert {document["document_id"] for document in result["corpus"]} == {
        "sample-faq-001",
        "sample-policy-001",
    }
    assert {query["query_id"] for query in result["queries"]} == {"q001", "q002", "q003"}
    assert {item["status"] for item in result["results"]} == {"NOT_EVALUATED"}
    assert {item["evaluation_status"] for item in result["per_query_results"]} == {"not_evaluated"}
    assert result["warnings"]
    assert result["errors"] == []
    assert result["metadata"]["phase"] == "v0.5-phase-a"
    assert result["metadata"]["uses_real_rag_connection"] is False
    assert result["metadata"]["uses_llm_evaluation"] is False
    assert result["metadata"]["uses_external_api"] is False
    assert "## Summary" in markdown
    assert "## Inputs" in markdown
    assert "## Per-query Results" in markdown
    assert "## Warnings" in markdown
    assert "## Errors" in markdown


def test_benchmark_json_report_has_phase_c_required_keys(tmp_path: Path) -> None:
    code = main(
        [
            "benchmark",
            "--corpus",
            str(BENCHMARK_FIXTURES / "corpus"),
            "--queries",
            str(BENCHMARK_FIXTURES / "queries.jsonl"),
            "--output",
            str(tmp_path),
        ]
    )

    result = json.loads((tmp_path / "benchmark_report.json").read_text(encoding="utf-8"))

    assert code == 0
    assert {
        "result",
        "summary",
        "corpus_count",
        "query_count",
        "per_query_results",
        "warnings",
        "errors",
        "metadata",
    } <= result.keys()
    assert len(result["per_query_results"]) == result["query_count"]
    for item in result["per_query_results"]:
        assert {
            "query_id",
            "question",
            "expected_source_ids",
            "expected_keywords",
            "expected_answer_hint",
            "no_result_expected",
            "unsafe_or_unknown_expected",
            "evaluation_status",
            "ranked_results",
            "notes",
        } <= item.keys()
        assert item["evaluation_status"] == "not_evaluated"


def test_benchmark_retrieval_ranks_relevant_document_first() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    queries = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")
    adapter = SyntheticRetrievalAdapter(documents)

    policy_results = adapter.retrieve(queries[0])
    faq_results = adapter.retrieve(queries[1])

    assert policy_results[0].document_id == "sample-policy-001"
    assert policy_results[0].rank == 1
    assert policy_results[0].score > 0
    assert "sample" in policy_results[0].matched_keywords
    assert faq_results[0].document_id == "sample-faq-001"


def test_benchmark_retrieval_tie_break_is_stable() -> None:
    documents = [
        BenchmarkDocument(
            document_id="sample-beta-001",
            title="Shared Synthetic Document",
            tags=["shared"],
            content="Shared benchmark token.",
            expected_searchable_facts=["Shared benchmark token."],
            file="b.md",
        ),
        BenchmarkDocument(
            document_id="sample-alpha-001",
            title="Shared Synthetic Document",
            tags=["shared"],
            content="Shared benchmark token.",
            expected_searchable_facts=["Shared benchmark token."],
            file="a.md",
        ),
    ]
    query = BenchmarkQuery(
        query_id="q_tie",
        question="shared benchmark",
        expected_source_ids=[],
        expected_keywords=[],
        expected_answer_hint="",
        no_result_expected=False,
        unsafe_or_unknown_expected=False,
    )

    results = SyntheticRetrievalAdapter(documents).retrieve(query)

    assert [result.document_id for result in results] == ["sample-alpha-001", "sample-beta-001"]
    assert [result.rank for result in results] == [1, 2]


def test_benchmark_retrieval_no_match_returns_empty_results() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = BenchmarkQuery(
        query_id="q_no_match",
        question="zzzz qqqq yyyy",
        expected_source_ids=[],
        expected_keywords=[],
        expected_answer_hint="",
        no_result_expected=True,
        unsafe_or_unknown_expected=False,
    )

    results = SyntheticRetrievalAdapter(documents).retrieve(query)

    assert results == []


def test_benchmark_report_includes_ranked_results(tmp_path: Path) -> None:
    code = main(
        [
            "benchmark",
            "--corpus",
            str(BENCHMARK_FIXTURES / "corpus"),
            "--queries",
            str(BENCHMARK_FIXTURES / "queries.jsonl"),
            "--output",
            str(tmp_path),
        ]
    )

    result = json.loads((tmp_path / "benchmark_report.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "benchmark_report.md").read_text(encoding="utf-8")
    q001 = next(item for item in result["per_query_results"] if item["query_id"] == "q001")

    assert code == 0
    assert q001["evaluation_status"] == "not_evaluated"
    assert q001["ranked_results"][0]["document_id"] == "sample-policy-001"
    assert {
        "rank",
        "document_id",
        "score",
        "matched_keywords",
        "title",
        "source_path",
    } <= q001["ranked_results"][0].keys()
    assert "sample archive" not in q001["ranked_results"][0].get("content", "")
    assert "- Ranked results:" in markdown
    assert "`sample-policy-001`" in markdown


def test_benchmark_loaders_read_valid_fixture() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    queries = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")

    assert len(documents) == 2
    assert len(queries) == 3
    assert documents[0].document_id == "sample-faq-001"
    assert queries[0].query_id == "q001"


def test_benchmark_invalid_query_returns_cli_error(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "sample.md").write_text(
        "\n".join(
            [
                "---",
                "document_id: sample-doc-001",
                "title: Sample Document",
                "tags:",
                "  - synthetic",
                "expected_searchable_facts:",
                "  - Sample fact.",
                "---",
                "",
                "# Sample Document",
                "",
                "Sample fact.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    queries = tmp_path / "queries.jsonl"
    queries.write_text(
        json.dumps(
            {
                "query_id": "q_invalid",
                "question": "Which source is missing?",
                "expected_source_ids": ["missing-doc"],
                "expected_keywords": [],
                "expected_answer_hint": "",
                "no_result_expected": False,
                "unsafe_or_unknown_expected": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    code = main(["benchmark", "--corpus", str(corpus), "--queries", str(queries), "--output", str(tmp_path / "out")])

    assert code == 3
    assert not (tmp_path / "out" / "benchmark_report.json").exists()


def test_benchmark_invalid_corpus_returns_cli_error(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "missing_title.md").write_text(
        "\n".join(
            [
                "---",
                "document_id: sample-doc-001",
                "tags:",
                "  - synthetic",
                "expected_searchable_facts:",
                "  - Sample fact.",
                "---",
                "",
                "# Sample Document",
                "",
                "Sample fact.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    code = main(
        [
            "benchmark",
            "--corpus",
            str(corpus),
            "--queries",
            str(BENCHMARK_FIXTURES / "queries.jsonl"),
            "--output",
            str(tmp_path / "out"),
        ]
    )

    assert code == 3
    assert not (tmp_path / "out" / "benchmark_report.json").exists()


def test_benchmark_fixtures_do_not_include_real_data_markers() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in BENCHMARK_FIXTURES.rglob("*") if path.is_file())

    forbidden_markers = [
        "C:\\AI_Restricted",
        "C:\\AI_Local_RAG",
        "株式会社",
        "有限会社",
        "合同会社",
        "Inc.",
        "Ltd.",
    ]
    for marker in forbidden_markers:
        assert marker not in text
