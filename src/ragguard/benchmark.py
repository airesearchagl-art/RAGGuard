from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from ragguard.retrieval import (
    RankedResult,
    RetrievalAdapter,
    RetrievalAdapterError,
    RetrievalQuery,
    validate_ranked_results,
)


JSON_REPORT_NAME = "benchmark_report.json"
MARKDOWN_REPORT_NAME = "benchmark_report.md"
DEFAULT_TOP_K = 5


class BenchmarkError(Exception):
    """Raised when benchmark inputs are invalid."""


@dataclass(frozen=True)
class BenchmarkDocument:
    document_id: str
    title: str
    tags: list[str]
    content: str
    expected_searchable_facts: list[str]
    file: str


@dataclass(frozen=True)
class BenchmarkQuery:
    query_id: str
    question: str
    expected_source_ids: list[str]
    expected_keywords: list[str]
    expected_answer_hint: str
    no_result_expected: bool
    unsafe_or_unknown_expected: bool


class SyntheticRetrievalAdapter:
    """Deterministic synthetic-only keyword retrieval."""

    name = "synthetic"

    def __init__(self, documents: list[BenchmarkDocument]) -> None:
        self._documents = documents

    def retrieve(self, query: RetrievalQuery, top_k: int | None = None) -> list[RankedResult]:
        if top_k is not None and (
            isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1
        ):
            raise RetrievalAdapterError("top_k must be a positive integer")
        query_terms = query_search_terms(query)
        scored: list[tuple[int, str, str, BenchmarkDocument, list[str]]] = []
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
            for index, (score, _document_id, _file, document, matched_keywords) in enumerate(limited, start=1)
        ]


def run_benchmark(corpus_dir: Path, queries_path: Path, output_dir: Path) -> tuple[dict, Path, Path]:
    documents = load_corpus(corpus_dir)
    queries = load_queries(queries_path)
    validate_query_sources(queries, documents)

    retrieval_adapter = SyntheticRetrievalAdapter(documents)
    result = build_placeholder_result(documents, queries, retrieval_adapter)
    json_path, markdown_path = write_benchmark_reports(result, output_dir)
    return result, json_path, markdown_path


def load_corpus(corpus_dir: Path) -> list[BenchmarkDocument]:
    if not corpus_dir.exists():
        raise BenchmarkError(f"Corpus directory does not exist: {corpus_dir}")
    if not corpus_dir.is_dir():
        raise BenchmarkError(f"Corpus path is not a directory: {corpus_dir}")

    markdown_files = sorted(path for path in corpus_dir.rglob("*.md") if path.is_file())
    if not markdown_files:
        raise BenchmarkError(f"Corpus directory has no Markdown files: {corpus_dir}")

    documents: list[BenchmarkDocument] = []
    seen_ids: set[str] = set()
    for markdown_file in markdown_files:
        document = load_corpus_document(markdown_file, corpus_dir)
        if document.document_id in seen_ids:
            raise BenchmarkError(f"Duplicate document_id: {document.document_id}")
        seen_ids.add(document.document_id)
        documents.append(document)
    return documents


def load_corpus_document(markdown_file: Path, base_dir: Path) -> BenchmarkDocument:
    metadata, content = split_front_matter(markdown_file)
    document_id = require_string(metadata, "document_id", markdown_file)
    title = require_string(metadata, "title", markdown_file)
    tags = require_string_list(metadata, "tags", markdown_file)
    expected_facts = require_string_list(metadata, "expected_searchable_facts", markdown_file)
    if not content.strip():
        raise BenchmarkError(f"Missing content: {markdown_file}")

    return BenchmarkDocument(
        document_id=document_id,
        title=title,
        tags=tags,
        content=content,
        expected_searchable_facts=expected_facts,
        file=str(markdown_file.resolve().relative_to(base_dir.resolve())),
    )


def split_front_matter(markdown_file: Path) -> tuple[dict[str, Any], str]:
    text = markdown_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise BenchmarkError(f"Missing front matter: {markdown_file}")

    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise BenchmarkError(f"Unclosed front matter: {markdown_file}")

    raw_metadata = "\n".join(lines[1:end_index])
    try:
        metadata = yaml.safe_load(raw_metadata) or {}
    except yaml.YAMLError as exc:
        raise BenchmarkError(f"Invalid front matter YAML: {markdown_file}") from exc
    if not isinstance(metadata, dict):
        raise BenchmarkError(f"Front matter must be a mapping: {markdown_file}")
    return metadata, "\n".join(lines[end_index + 1 :]).strip()


def load_queries(queries_path: Path) -> list[BenchmarkQuery]:
    if not queries_path.exists():
        raise BenchmarkError(f"Queries file does not exist: {queries_path}")
    if not queries_path.is_file():
        raise BenchmarkError(f"Queries path is not a file: {queries_path}")

    queries: list[BenchmarkQuery] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(queries_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw_query = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"Invalid JSONL at line {line_number}: {queries_path}") from exc
        if not isinstance(raw_query, dict):
            raise BenchmarkError(f"Query must be a JSON object at line {line_number}: {queries_path}")

        query = parse_query(raw_query, queries_path, line_number)
        if query.query_id in seen_ids:
            raise BenchmarkError(f"Duplicate query_id: {query.query_id}")
        seen_ids.add(query.query_id)
        queries.append(query)

    if not queries:
        raise BenchmarkError(f"Queries file has no queries: {queries_path}")
    return queries


def parse_query(raw_query: dict[str, Any], queries_path: Path, line_number: int) -> BenchmarkQuery:
    return BenchmarkQuery(
        query_id=require_string(raw_query, "query_id", queries_path, line_number),
        question=require_string(raw_query, "question", queries_path, line_number),
        expected_source_ids=require_string_list(raw_query, "expected_source_ids", queries_path, line_number),
        expected_keywords=require_string_list(raw_query, "expected_keywords", queries_path, line_number),
        expected_answer_hint=require_string(raw_query, "expected_answer_hint", queries_path, line_number, allow_empty=True),
        no_result_expected=require_bool(raw_query, "no_result_expected", queries_path, line_number),
        unsafe_or_unknown_expected=require_bool(raw_query, "unsafe_or_unknown_expected", queries_path, line_number),
    )


def validate_query_sources(queries: list[BenchmarkQuery], documents: list[BenchmarkDocument]) -> None:
    document_ids = {document.document_id for document in documents}
    for query in queries:
        missing = [source_id for source_id in query.expected_source_ids if source_id not in document_ids]
        if missing:
            raise BenchmarkError(f"Unknown expected_source_ids for query_id {query.query_id}: {', '.join(missing)}")


def build_placeholder_result(
    documents: list[BenchmarkDocument],
    queries: list[BenchmarkQuery],
    retrieval_adapter: RetrievalAdapter | None = None,
) -> dict:
    adapter = retrieval_adapter or SyntheticRetrievalAdapter(documents)
    try:
        per_query_results = [
            build_per_query_result(
                query,
                validate_ranked_results(adapter.retrieve(query, DEFAULT_TOP_K), DEFAULT_TOP_K),
            )
            for query in queries
        ]
    except RetrievalAdapterError as exc:
        adapter_name = getattr(adapter, "name", "unknown")
        raise BenchmarkError(f"Invalid retrieval result from adapter {adapter_name}: {exc}") from exc
    summary = build_benchmark_summary(len(documents), per_query_results)
    corpus_items = [
        {
            "document_id": document.document_id,
            "title": document.title,
            "tags": document.tags,
            "file": document.file,
            "expected_searchable_fact_count": len(document.expected_searchable_facts),
        }
        for document in documents
    ]
    return {
        "result": benchmark_status(summary),
        "status": benchmark_status(summary),
        "corpus_count": len(documents),
        "query_count": len(queries),
        "summary": summary,
        "corpus": corpus_items,
        "queries": [asdict(query) for query in queries],
        "per_query_results": per_query_results,
        "results": legacy_results(per_query_results),
        "warnings": [
            "Retrieval results are generated from synthetic keyword overlap only.",
            "LLM answer quality and external RAG behavior are not evaluated.",
        ],
        "errors": [],
        "metadata": {
            "schema_version": 1,
            "phase": "v0.5-phase-c",
            "top_k": DEFAULT_TOP_K,
            "uses_real_rag_connection": False,
            "uses_llm_evaluation": False,
            "uses_external_api": False,
        },
    }


def build_per_query_result(query: BenchmarkQuery, ranked_results: list[RankedResult]) -> dict:
    ranked_result_dicts = [ranked_result_to_dict(result) for result in ranked_results]
    top_k_results = ranked_results[:DEFAULT_TOP_K]
    top_k_ids = [result.document_id for result in top_k_results]
    matched_expected_source_ids = [
        source_id for source_id in query.expected_source_ids if source_id in top_k_ids
    ]
    hit_at_k = bool(matched_expected_source_ids) if query.expected_source_ids else None
    source_match = (
        len(matched_expected_source_ids) == len(query.expected_source_ids)
        if query.expected_source_ids
        else None
    )
    matched_keywords, missing_keywords = evaluate_expected_keywords(query.expected_keywords, top_k_results)
    keyword_coverage_rate = rate(len(matched_keywords), len(query.expected_keywords))
    no_result_pass = (not ranked_results) if query.no_result_expected else None
    unsafe_or_unknown_pass = (not ranked_results) if query.unsafe_or_unknown_expected else None

    if query.no_result_expected or query.unsafe_or_unknown_expected:
        evaluation_status = status_for_special_expectations(no_result_pass, unsafe_or_unknown_pass)
        notes = notes_for_special_expectations(no_result_pass, unsafe_or_unknown_pass)
        return {
            "query_id": query.query_id,
            "question": query.question,
            "expected_source_ids": query.expected_source_ids,
            "expected_keywords": query.expected_keywords,
            "expected_answer_hint": query.expected_answer_hint,
            "no_result_expected": query.no_result_expected,
            "unsafe_or_unknown_expected": query.unsafe_or_unknown_expected,
            "hit_at_k": hit_at_k,
            "source_match": source_match,
            "matched_expected_source_ids": matched_expected_source_ids,
            "matched_keywords": matched_keywords,
            "missing_keywords": missing_keywords,
            "keyword_coverage_rate": keyword_coverage_rate,
            "no_result_pass": no_result_pass,
            "unsafe_or_unknown_pass": unsafe_or_unknown_pass,
            "evaluation_status": evaluation_status,
            "ranked_results": ranked_result_dicts,
            "notes": notes,
        }

    if source_match and not missing_keywords:
        evaluation_status = "pass"
        notes = "All expected sources and expected keywords were found in the top-k ranked results."
    elif hit_at_k:
        evaluation_status = "warning"
        notes = "Some expected sources or keywords need review in the top-k ranked results."
    else:
        evaluation_status = "fail"
        notes = "No expected sources were found in the top-k ranked results."

    return {
        "query_id": query.query_id,
        "question": query.question,
        "expected_source_ids": query.expected_source_ids,
        "expected_keywords": query.expected_keywords,
        "expected_answer_hint": query.expected_answer_hint,
        "no_result_expected": query.no_result_expected,
        "unsafe_or_unknown_expected": query.unsafe_or_unknown_expected,
        "hit_at_k": hit_at_k,
        "source_match": source_match,
        "matched_expected_source_ids": matched_expected_source_ids,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "keyword_coverage_rate": keyword_coverage_rate,
        "no_result_pass": no_result_pass,
        "unsafe_or_unknown_pass": unsafe_or_unknown_pass,
        "evaluation_status": evaluation_status,
        "ranked_results": ranked_result_dicts,
        "notes": notes,
    }


def ranked_result_to_dict(result: RankedResult) -> dict[str, Any]:
    serialized: dict[str, Any] = {
        "rank": result.rank,
        "document_id": result.document_id,
        "score": result.score,
        "matched_keywords": result.matched_keywords,
        "title": result.title,
        "source_path": result.source_path,
    }
    if result.adapter_metadata is not None:
        serialized["adapter_metadata"] = dict(result.adapter_metadata)
    return serialized


def evaluate_expected_keywords(
    expected_keywords: list[str],
    ranked_results: list[RankedResult],
) -> tuple[list[str], list[str]]:
    if not expected_keywords:
        return [], []

    top_k_terms = {
        keyword
        for result in ranked_results[:DEFAULT_TOP_K]
        for keyword in result.matched_keywords
    }
    matched: list[str] = []
    missing: list[str] = []
    for expected_keyword in expected_keywords:
        expected_terms = tokenize(expected_keyword)
        if expected_terms and all(term in top_k_terms for term in expected_terms):
            matched.append(expected_keyword)
        else:
            missing.append(expected_keyword)
    return matched, missing


def status_for_special_expectations(no_result_pass: bool | None, unsafe_or_unknown_pass: bool | None) -> str:
    if no_result_pass is False:
        return "fail"
    if unsafe_or_unknown_pass is False:
        return "warning"
    return "pass"


def notes_for_special_expectations(no_result_pass: bool | None, unsafe_or_unknown_pass: bool | None) -> str:
    notes: list[str] = []
    if no_result_pass is True:
        notes.append("No-result expectation passed because no synthetic retrieval result was returned.")
    elif no_result_pass is False:
        notes.append("No-result expectation failed because synthetic retrieval returned at least one result.")

    if unsafe_or_unknown_pass is True:
        notes.append("Unsafe-or-unknown expectation passed without synthetic retrieval results.")
    elif unsafe_or_unknown_pass is False:
        notes.append("Unsafe-or-unknown expectation needs review because synthetic retrieval returned results.")

    return " ".join(notes) if notes else "Synthetic benchmark evaluation completed."


def build_benchmark_summary(corpus_count: int, per_query_results: list[dict]) -> dict:
    evaluated_results = [
        item for item in per_query_results if item["evaluation_status"] != "not_evaluated"
    ]
    evaluated_count = len(evaluated_results)
    source_results = [
        item for item in evaluated_results if item["hit_at_k"] is not None
    ]
    hit_at_k_count = sum(1 for item in source_results if item["hit_at_k"] is True)
    source_match_count = sum(1 for item in source_results if item["source_match"] is True)
    keyword_results = [
        item for item in evaluated_results if item["keyword_coverage_rate"] is not None
    ]
    no_result_results = [
        item for item in evaluated_results if item["no_result_pass"] is not None
    ]
    unsafe_or_unknown_results = [
        item for item in evaluated_results if item["unsafe_or_unknown_pass"] is not None
    ]
    keyword_coverage_sum = sum(item["keyword_coverage_rate"] for item in keyword_results)
    no_result_pass_count = sum(1 for item in no_result_results if item["no_result_pass"] is True)
    unsafe_or_unknown_pass_count = sum(
        1 for item in unsafe_or_unknown_results if item["unsafe_or_unknown_pass"] is True
    )
    passed = sum(1 for item in evaluated_results if item["evaluation_status"] == "pass")
    warned = sum(1 for item in evaluated_results if item["evaluation_status"] == "warning")
    failed = sum(1 for item in evaluated_results if item["evaluation_status"] == "fail")
    return {
        "corpus_count": corpus_count,
        "query_count": len(per_query_results),
        "validation_error_count": 0,
        "evaluated_query_count": evaluated_count,
        "evaluated_queries": evaluated_count,
        "not_evaluated_query_count": len(per_query_results) - evaluated_count,
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "hit_at_k_count": hit_at_k_count,
        "hit_at_k_rate": rate(hit_at_k_count, len(source_results)),
        "hit_at_k_evaluated_query_count": len(source_results),
        "source_match_count": source_match_count,
        "source_match_rate": rate(source_match_count, len(source_results)),
        "source_match_evaluated_query_count": len(source_results),
        "keyword_coverage_rate": rate_float(keyword_coverage_sum, len(keyword_results)),
        "keyword_evaluated_query_count": len(keyword_results),
        "no_result_pass_count": no_result_pass_count,
        "no_result_pass_rate": rate(no_result_pass_count, len(no_result_results)),
        "no_result_evaluated_query_count": len(no_result_results),
        "unsafe_or_unknown_pass_count": unsafe_or_unknown_pass_count,
        "unsafe_or_unknown_pass_rate": rate(unsafe_or_unknown_pass_count, len(unsafe_or_unknown_results)),
        "unsafe_or_unknown_evaluated_query_count": len(unsafe_or_unknown_results),
    }


def benchmark_status(summary: dict) -> str:
    if summary["failed"]:
        return "FAIL"
    if summary["warned"]:
        return "WARNING"
    return "PASS"


def rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def rate_float(numerator: float, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def legacy_results(per_query_results: list[dict]) -> list[dict]:
    return [
        {
            "query_id": item["query_id"],
            "status": item["evaluation_status"].upper(),
            "matched_sources": item["matched_expected_source_ids"],
            "matched_keywords": item["matched_keywords"],
            "missing_keywords": item["missing_keywords"],
            "keyword_coverage_rate": item["keyword_coverage_rate"],
            "no_result_pass": item["no_result_pass"],
            "unsafe_or_unknown_pass": item["unsafe_or_unknown_pass"],
            "ranked_results": item["ranked_results"],
            "notes": item["notes"],
        }
        for item in per_query_results
    ]


def write_benchmark_reports(result: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / JSON_REPORT_NAME
    markdown_path = output_dir / MARKDOWN_REPORT_NAME
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_benchmark_markdown(result), encoding="utf-8")
    return json_path, markdown_path


def render_benchmark_markdown(result: dict) -> str:
    summary = result.get("summary", {})
    metadata = result.get("metadata", {})
    lines = [
        "# RAG Benchmark Report",
        "",
        "## Summary",
        "",
        f"- Result: {result.get('result', result.get('status', 'UNKNOWN'))}",
        f"- Corpus documents: {result.get('corpus_count', summary.get('corpus_count', 0))}",
        f"- Queries: {result.get('query_count', summary.get('query_count', 0))}",
        f"- Validation errors: {summary.get('validation_error_count', 0)}",
        f"- Evaluated queries: {summary.get('evaluated_query_count', 0)}",
        f"- Not evaluated queries: {summary.get('not_evaluated_query_count', 0)}",
        f"- Passed queries: {summary.get('passed', 0)}",
        f"- Warning queries: {summary.get('warned', 0)}",
        f"- Failed queries: {summary.get('failed', 0)}",
        f"- Hit@k count: {summary.get('hit_at_k_count', 0)}",
        f"- Hit@k evaluated queries: {summary.get('hit_at_k_evaluated_query_count', 0)}",
        f"- Hit@k rate: {format_rate(summary.get('hit_at_k_rate'))}",
        f"- Source match count: {summary.get('source_match_count', 0)}",
        f"- Source match evaluated queries: {summary.get('source_match_evaluated_query_count', 0)}",
        f"- Source match rate: {format_rate(summary.get('source_match_rate'))}",
        f"- Keyword evaluated queries: {summary.get('keyword_evaluated_query_count', 0)}",
        f"- Keyword coverage rate: {format_rate(summary.get('keyword_coverage_rate'))}",
        f"- No-result pass count: {summary.get('no_result_pass_count', 0)}",
        f"- No-result evaluated queries: {summary.get('no_result_evaluated_query_count', 0)}",
        f"- No-result pass rate: {format_rate(summary.get('no_result_pass_rate'))}",
        f"- Unsafe-or-unknown pass count: {summary.get('unsafe_or_unknown_pass_count', 0)}",
        f"- Unsafe-or-unknown evaluated queries: {summary.get('unsafe_or_unknown_evaluated_query_count', 0)}",
        f"- Unsafe-or-unknown pass rate: {format_rate(summary.get('unsafe_or_unknown_pass_rate'))}",
        "",
        "## Inputs",
        "",
        f"- Schema version: {metadata.get('schema_version', 'unknown')}",
        f"- Phase: {metadata.get('phase', 'unknown')}",
        f"- Top-k: {metadata.get('top_k', 'unknown')}",
        f"- Real RAG connection: {metadata.get('uses_real_rag_connection', False)}",
        f"- LLM evaluation: {metadata.get('uses_llm_evaluation', False)}",
        f"- External API: {metadata.get('uses_external_api', False)}",
        "",
        "### Corpus",
        "",
    ]
    for document in result.get("corpus", []):
        lines.append(f"- `{document['document_id']}`: {document['title']} ({document['file']})")
    if not result.get("corpus"):
        lines.append("- No corpus documents loaded.")

    lines.extend(["", "## Per-query Results", ""])
    for query in result.get("per_query_results", []):
        lines.extend(
            [
                f"### {query['query_id']}",
                "",
                f"- Question: {query['question']}",
                f"- Expected source ids: {', '.join(query['expected_source_ids']) or '(none)'}",
                f"- Expected keywords: {', '.join(query['expected_keywords']) or '(none)'}",
                f"- Expected answer hint: {query['expected_answer_hint'] or '(none)'}",
                f"- No-result expected: {query['no_result_expected']}",
                f"- Unsafe or unknown expected: {query['unsafe_or_unknown_expected']}",
                f"- Hit@k: {format_optional_bool(query.get('hit_at_k'))}",
                f"- Source match: {format_optional_bool(query.get('source_match'))}",
                f"- Matched expected source ids: {', '.join(query.get('matched_expected_source_ids', [])) or '(none)'}",
                f"- Matched keywords: {', '.join(query.get('matched_keywords', [])) or '(none)'}",
                f"- Missing keywords: {', '.join(query.get('missing_keywords', [])) or '(none)'}",
                f"- Keyword coverage rate: {format_rate(query.get('keyword_coverage_rate'))}",
                f"- No-result pass: {format_optional_bool(query.get('no_result_pass'))}",
                f"- Unsafe-or-unknown pass: {format_optional_bool(query.get('unsafe_or_unknown_pass'))}",
                f"- Evaluation status: {query['evaluation_status']}",
                "- Ranked results:",
                *render_ranked_results(query.get("ranked_results", [])),
                f"- Notes: {query['notes']}",
                "",
            ]
        )
    if not result.get("per_query_results"):
        lines.append("- No queries loaded.")

    lines.extend(["", "## Warnings", ""])
    warnings = result.get("warnings", [])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None.")

    lines.extend(["", "## Errors", ""])
    errors = result.get("errors", [])
    if errors:
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("- None.")

    lines.append("")
    return "\n".join(lines)


def render_ranked_results(ranked_results: list[dict]) -> list[str]:
    if not ranked_results:
        return ["  - None."]
    return [
        (
            f"  - #{item['rank']} `{item['document_id']}` "
            f"score={item['score']} matched={', '.join(item['matched_keywords']) or '(none)'} "
            f"source={item['source_path']}"
        )
        for item in ranked_results
    ]


def format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "not_evaluated"
    return str(value)


def format_rate(value: float | None) -> str:
    if value is None:
        return "not_evaluated"
    return f"{value:.3f}"


def query_search_terms(query: RetrievalQuery) -> list[str]:
    terms = tokenize(query.question)
    for keyword in query.expected_keywords:
        terms.extend(tokenize(keyword))
    if query.expected_answer_hint:
        terms.extend(tokenize(query.expected_answer_hint))
    return sorted(set(terms))


def matched_document_keywords(query_terms: list[str], document: BenchmarkDocument) -> list[str]:
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


def require_string(
    data: dict[str, Any],
    key: str,
    source: Path,
    line_number: int | None = None,
    *,
    allow_empty: bool = False,
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise BenchmarkError(format_field_error(source, key, "non-empty string", line_number))
    return value


def require_string_list(data: dict[str, Any], key: str, source: Path, line_number: int | None = None) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise BenchmarkError(format_field_error(source, key, "list of non-empty strings", line_number))
    return value


def require_bool(data: dict[str, Any], key: str, source: Path, line_number: int | None = None) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise BenchmarkError(format_field_error(source, key, "boolean", line_number))
    return value


def format_field_error(source: Path, key: str, expected: str, line_number: int | None = None) -> str:
    location = f"{source}"
    if line_number is not None:
        location = f"{source}:{line_number}"
    return f"Invalid or missing {key}; expected {expected}: {location}"
