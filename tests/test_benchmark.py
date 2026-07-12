from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragguard.benchmark import (
    BenchmarkDocument,
    BenchmarkQuery,
    DEFAULT_TOP_K,
    SyntheticRetrievalAdapter,
    build_per_query_result,
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
    assert result["summary"]["evaluated_query_count"] == 3
    assert result["summary"]["evaluated_queries"] == 3
    assert result["summary"]["not_evaluated_query_count"] == 0
    assert result["summary"]["passed"] == 3
    assert result["summary"]["warned"] == 0
    assert result["summary"]["failed"] == 0
    assert result["summary"]["hit_at_k_count"] == 2
    assert result["summary"]["hit_at_k_evaluated_query_count"] == 2
    assert result["summary"]["hit_at_k_rate"] == 1.0
    assert result["summary"]["source_match_count"] == 2
    assert result["summary"]["source_match_evaluated_query_count"] == 2
    assert result["summary"]["source_match_rate"] == 1.0
    assert result["summary"]["keyword_evaluated_query_count"] == 2
    assert result["summary"]["keyword_coverage_rate"] == 1.0
    assert result["summary"]["no_result_pass_count"] == 1
    assert result["summary"]["no_result_pass_rate"] == 1.0
    assert result["summary"]["unsafe_or_unknown_pass_count"] == 1
    assert result["summary"]["unsafe_or_unknown_pass_rate"] == 1.0
    assert {document["document_id"] for document in result["corpus"]} == {
        "sample-faq-001",
        "sample-policy-001",
    }
    assert {query["query_id"] for query in result["queries"]} == {"q001", "q002", "q003"}
    assert {item["status"] for item in result["results"]} == {"PASS"}
    assert {item["evaluation_status"] for item in result["per_query_results"]} == {"pass"}
    assert result["warnings"]
    assert result["errors"] == []
    assert result["metadata"]["phase"] == "v0.5-phase-c"
    assert result["metadata"]["top_k"] == DEFAULT_TOP_K
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
            "hit_at_k",
            "source_match",
            "matched_expected_source_ids",
            "matched_keywords",
            "missing_keywords",
            "keyword_coverage_rate",
            "no_result_pass",
            "unsafe_or_unknown_pass",
            "ranked_results",
            "notes",
        } <= item.keys()
    assert {item["evaluation_status"] for item in result["per_query_results"]} == {"pass"}


def test_benchmark_summary_has_v05_phase_d_required_metrics(tmp_path: Path) -> None:
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
    summary = result["summary"]

    assert code == 0
    assert {
        "evaluated_queries",
        "not_evaluated_query_count",
        "passed",
        "warned",
        "failed",
        "hit_at_k_count",
        "hit_at_k_evaluated_query_count",
        "hit_at_k_rate",
        "source_match_count",
        "source_match_evaluated_query_count",
        "source_match_rate",
        "keyword_evaluated_query_count",
        "keyword_coverage_rate",
        "no_result_pass_count",
        "no_result_evaluated_query_count",
        "no_result_pass_rate",
        "unsafe_or_unknown_pass_count",
        "unsafe_or_unknown_evaluated_query_count",
        "unsafe_or_unknown_pass_rate",
    } <= summary.keys()
    assert summary["evaluated_queries"] == summary["passed"] + summary["warned"] + summary["failed"]
    assert summary["hit_at_k_rate"] == summary["hit_at_k_count"] / summary["hit_at_k_evaluated_query_count"]
    assert summary["source_match_rate"] == summary["source_match_count"] / summary["source_match_evaluated_query_count"]
    assert summary["keyword_coverage_rate"] == 1.0
    assert summary["no_result_pass_rate"] == 1.0
    assert summary["unsafe_or_unknown_pass_rate"] == 1.0


def test_benchmark_legacy_results_include_phase_c_metrics(tmp_path: Path) -> None:
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
    q001 = next(item for item in result["results"] if item["query_id"] == "q001")

    assert code == 0
    assert q001["status"] == "PASS"
    assert q001["matched_sources"] == ["sample-policy-001"]
    assert q001["matched_keywords"] == ["sample archive"]
    assert q001["missing_keywords"] == []
    assert q001["keyword_coverage_rate"] == 1.0
    assert q001["no_result_pass"] is None
    assert q001["unsafe_or_unknown_pass"] is None


def test_benchmark_keyword_coverage_full_match_passes() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")[0]

    result = build_per_query_result(query, SyntheticRetrievalAdapter(documents).retrieve(query))

    assert result["matched_keywords"] == ["sample archive"]
    assert result["missing_keywords"] == []
    assert result["keyword_coverage_rate"] == 1.0
    assert result["evaluation_status"] == "pass"


def test_benchmark_keyword_coverage_partial_match_warns() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = BenchmarkQuery(
        query_id="q_keyword_partial",
        question="Where are sample policy documents stored?",
        expected_source_ids=["sample-policy-001"],
        expected_keywords=["sample archive", "missing marker"],
        expected_answer_hint="",
        no_result_expected=False,
        unsafe_or_unknown_expected=False,
    )

    result = build_per_query_result(query, SyntheticRetrievalAdapter(documents).retrieve(query))

    assert result["matched_keywords"] == ["sample archive"]
    assert result["missing_keywords"] == ["missing marker"]
    assert result["keyword_coverage_rate"] == 0.5
    assert result["hit_at_k"] is True
    assert result["evaluation_status"] == "warning"


def test_benchmark_keyword_coverage_no_match_warns_when_source_hits() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = BenchmarkQuery(
        query_id="q_keyword_none",
        question="Where are sample policy documents stored?",
        expected_source_ids=["sample-policy-001"],
        expected_keywords=["missing marker"],
        expected_answer_hint="",
        no_result_expected=False,
        unsafe_or_unknown_expected=False,
    )

    result = build_per_query_result(query, SyntheticRetrievalAdapter(documents).retrieve(query))

    assert result["matched_keywords"] == []
    assert result["missing_keywords"] == ["missing marker"]
    assert result["keyword_coverage_rate"] == 0.0
    assert result["evaluation_status"] == "warning"


def test_benchmark_hit_at_k_and_source_match_pass_for_expected_top_k() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    queries = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")
    adapter = SyntheticRetrievalAdapter(documents)

    q001 = queries[0]
    result = build_per_query_result(q001, adapter.retrieve(q001))

    assert result["hit_at_k"] is True
    assert result["source_match"] is True
    assert result["matched_expected_source_ids"] == ["sample-policy-001"]
    assert result["evaluation_status"] == "pass"


def test_benchmark_hit_at_k_fails_when_expected_source_is_not_in_top_k() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = BenchmarkQuery(
        query_id="q_source_miss",
        question="zzzz qqqq yyyy",
        expected_source_ids=["sample-policy-001"],
        expected_keywords=[],
        expected_answer_hint="",
        no_result_expected=False,
        unsafe_or_unknown_expected=False,
    )

    result = build_per_query_result(query, SyntheticRetrievalAdapter(documents).retrieve(query))

    assert result["ranked_results"] == []
    assert result["hit_at_k"] is False
    assert result["source_match"] is False
    assert result["matched_expected_source_ids"] == []
    assert result["evaluation_status"] == "fail"


def test_benchmark_source_match_supports_multiple_expected_sources() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = BenchmarkQuery(
        query_id="q_multi_source",
        question="sample synthetic",
        expected_source_ids=["sample-faq-001", "sample-policy-001"],
        expected_keywords=[],
        expected_answer_hint="",
        no_result_expected=False,
        unsafe_or_unknown_expected=False,
    )

    result = build_per_query_result(query, SyntheticRetrievalAdapter(documents).retrieve(query))

    assert result["hit_at_k"] is True
    assert result["source_match"] is True
    assert result["matched_expected_source_ids"] == ["sample-faq-001", "sample-policy-001"]
    assert result["evaluation_status"] == "pass"


def test_benchmark_partial_source_match_warns() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = BenchmarkQuery(
        query_id="q_partial_source",
        question="policy archive",
        expected_source_ids=["sample-faq-001", "sample-policy-001"],
        expected_keywords=[],
        expected_answer_hint="",
        no_result_expected=False,
        unsafe_or_unknown_expected=False,
    )

    result = build_per_query_result(query, SyntheticRetrievalAdapter(documents).retrieve(query))

    assert result["hit_at_k"] is True
    assert result["source_match"] is False
    assert result["matched_expected_source_ids"] == ["sample-policy-001"]
    assert result["evaluation_status"] == "warning"


def test_benchmark_no_result_query_passes_when_no_results_are_returned() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = load_queries(BENCHMARK_FIXTURES / "queries.jsonl")[2]

    result = build_per_query_result(query, SyntheticRetrievalAdapter(documents).retrieve(query))

    assert result["hit_at_k"] is None
    assert result["source_match"] is None
    assert result["matched_expected_source_ids"] == []
    assert result["no_result_pass"] is True
    assert result["unsafe_or_unknown_pass"] is True
    assert result["evaluation_status"] == "pass"


def test_benchmark_no_result_expected_fails_when_results_are_returned() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = BenchmarkQuery(
        query_id="q_no_result_unexpected_hit",
        question="sample policy",
        expected_source_ids=[],
        expected_keywords=[],
        expected_answer_hint="",
        no_result_expected=True,
        unsafe_or_unknown_expected=False,
    )

    result = build_per_query_result(query, SyntheticRetrievalAdapter(documents).retrieve(query))

    assert result["ranked_results"]
    assert result["no_result_pass"] is False
    assert result["evaluation_status"] == "fail"


def test_benchmark_unsafe_or_unknown_warns_when_results_are_returned() -> None:
    documents = load_corpus(BENCHMARK_FIXTURES / "corpus")
    query = BenchmarkQuery(
        query_id="q_unknown_unexpected_hit",
        question="sample policy",
        expected_source_ids=[],
        expected_keywords=[],
        expected_answer_hint="",
        no_result_expected=False,
        unsafe_or_unknown_expected=True,
    )

    result = build_per_query_result(query, SyntheticRetrievalAdapter(documents).retrieve(query))

    assert result["ranked_results"]
    assert result["unsafe_or_unknown_pass"] is False
    assert result["evaluation_status"] == "warning"


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
    assert q001["evaluation_status"] == "pass"
    assert q001["hit_at_k"] is True
    assert q001["source_match"] is True
    assert q001["matched_expected_source_ids"] == ["sample-policy-001"]
    assert q001["matched_keywords"] == ["sample archive"]
    assert q001["missing_keywords"] == []
    assert q001["keyword_coverage_rate"] == 1.0
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
    assert "- Hit@k: True" in markdown
    assert "- Source match: True" in markdown
    assert "- Matched keywords: sample archive" in markdown
    assert "- Keyword coverage rate: 1.000" in markdown
    assert "- Hit@k evaluated queries: 2" in markdown
    assert "- Source match evaluated queries: 2" in markdown
    assert "- Keyword evaluated queries: 2" in markdown
    assert "- No-result evaluated queries: 1" in markdown
    assert "- Unsafe-or-unknown evaluated queries: 1" in markdown


def test_benchmark_cli_returns_fail_for_source_miss(tmp_path: Path) -> None:
    queries = tmp_path / "queries.jsonl"
    queries.write_text(
        json.dumps(
            {
                "query_id": "q_source_miss",
                "question": "zzzz qqqq yyyy",
                "expected_source_ids": ["sample-policy-001"],
                "expected_keywords": [],
                "expected_answer_hint": "",
                "no_result_expected": False,
                "unsafe_or_unknown_expected": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    code = main(
        [
            "benchmark",
            "--corpus",
            str(BENCHMARK_FIXTURES / "corpus"),
            "--queries",
            str(queries),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    result = json.loads((tmp_path / "out" / "benchmark_report.json").read_text(encoding="utf-8"))

    assert code == 2
    assert result["status"] == "FAIL"
    assert result["summary"]["failed"] == 1


def test_benchmark_cli_returns_warning_for_keyword_partial_match(tmp_path: Path) -> None:
    queries = tmp_path / "queries.jsonl"
    queries.write_text(
        json.dumps(
            {
                "query_id": "q_warning",
                "question": "Where are sample policy documents stored?",
                "expected_source_ids": ["sample-policy-001"],
                "expected_keywords": ["sample archive", "missing marker"],
                "expected_answer_hint": "",
                "no_result_expected": False,
                "unsafe_or_unknown_expected": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    code = main(
        [
            "benchmark",
            "--corpus",
            str(BENCHMARK_FIXTURES / "corpus"),
            "--queries",
            str(queries),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    result = json.loads((tmp_path / "out" / "benchmark_report.json").read_text(encoding="utf-8"))

    assert code == 1
    assert result["status"] == "WARNING"
    assert result["summary"]["warned"] == 1


def test_benchmark_cli_returns_pass_for_standard_fixture(tmp_path: Path) -> None:
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

    assert code == 0


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
