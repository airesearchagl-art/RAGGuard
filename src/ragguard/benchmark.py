from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


JSON_REPORT_NAME = "benchmark_report.json"
MARKDOWN_REPORT_NAME = "benchmark_report.md"


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


@dataclass(frozen=True)
class RankedResult:
    rank: int
    document_id: str
    score: int
    matched_keywords: list[str]
    title: str
    source_path: str


class SyntheticRetrievalAdapter:
    """Deterministic synthetic-only keyword retrieval."""

    def __init__(self, documents: list[BenchmarkDocument]) -> None:
        self._documents = documents

    def retrieve(self, query: BenchmarkQuery) -> list[RankedResult]:
        query_terms = query_search_terms(query)
        scored: list[tuple[int, str, str, BenchmarkDocument, list[str]]] = []
        for document in self._documents:
            matched_keywords = matched_document_keywords(query_terms, document)
            if not matched_keywords:
                continue
            score = len(matched_keywords)
            scored.append((score, document.document_id, document.file, document, matched_keywords))

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [
            RankedResult(
                rank=index,
                document_id=document.document_id,
                score=score,
                matched_keywords=matched_keywords,
                title=document.title,
                source_path=document.file,
            )
            for index, (score, _document_id, _file, document, matched_keywords) in enumerate(scored, start=1)
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
    retrieval_adapter: SyntheticRetrievalAdapter | None = None,
) -> dict:
    adapter = retrieval_adapter or SyntheticRetrievalAdapter(documents)
    per_query_results = [
        {
            "query_id": query.query_id,
            "question": query.question,
            "expected_source_ids": query.expected_source_ids,
            "expected_keywords": query.expected_keywords,
            "expected_answer_hint": query.expected_answer_hint,
            "no_result_expected": query.no_result_expected,
            "unsafe_or_unknown_expected": query.unsafe_or_unknown_expected,
            "evaluation_status": "not_evaluated",
            "ranked_results": [asdict(result) for result in adapter.retrieve(query)],
            "notes": "Synthetic retrieval is available in Phase A; scoring is not implemented yet.",
        }
        for query in queries
    ]
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
        "result": "PASS",
        "status": "PASS",
        "corpus_count": len(documents),
        "query_count": len(queries),
        "summary": {
            "corpus_count": len(documents),
            "query_count": len(queries),
            "validation_error_count": 0,
            "evaluated_query_count": 0,
            "not_evaluated_query_count": len(queries),
        },
        "corpus": corpus_items,
        "queries": [asdict(query) for query in queries],
        "per_query_results": per_query_results,
        "results": legacy_results(per_query_results),
        "warnings": [
            "Benchmark scoring is not implemented in Phase A.",
            "Retrieval results are generated from synthetic keyword overlap only.",
        ],
        "errors": [],
        "metadata": {
            "schema_version": 1,
            "phase": "v0.5-phase-a",
            "uses_real_rag_connection": False,
            "uses_llm_evaluation": False,
            "uses_external_api": False,
        },
    }


def legacy_results(per_query_results: list[dict]) -> list[dict]:
    return [
        {
            "query_id": item["query_id"],
            "status": "NOT_EVALUATED",
            "ranked_results": item["ranked_results"],
            "notes": "Synthetic retrieval is available in Phase A; scoring is not implemented yet.",
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
        "",
        "## Inputs",
        "",
        f"- Schema version: {metadata.get('schema_version', 'unknown')}",
        f"- Phase: {metadata.get('phase', 'unknown')}",
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


def query_search_terms(query: BenchmarkQuery) -> list[str]:
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
