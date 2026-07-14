# Changelog

## Unreleased

### v0.6 retrieval adapter interface design

- Defined the retrieval adapter contract for query input, top-k, deterministic ranked results, optional adapter metadata, and bounded error handling.
- Separated retrieval responsibilities from benchmark evaluation, reports, and benchmark exit-code decisions.
- Added the Phase A retrieval adapter protocol, common ranked-result model, contract validation, and synthetic adapter compatibility layer.
- Migrated the Phase B Synthetic adapter and deterministic matching helpers into the shared retrieval module.
- Routed adapter execution through one validation boundary before benchmark evaluation.
- Preserved existing report serialization when adapter metadata is omitted.
- Added the Phase C deterministic test-only mock adapter and expanded retrieval contract tests.
- Covered empty and ranked results, optional metadata, deterministic ordering, invalid fields,
  duplicate document IDs, top-k overflow, and adapter exception normalization.
- Verified invalid adapter results reach benchmark CLI error `3` without changing report keys or
  evaluator-owned status decisions.
- Added the Phase D unconnected `LocalRAGRetrievalAdapter` skeleton.
- Defined a configuration-presence-only constructor boundary without reading or retaining values.
- Added bounded not-configured and unavailable-dependency errors through the existing CLI error `3`
  path, without filesystem, localhost, network, or real RAG access.
- Planned synthetic migration, mock contract tests, and a local-only adapter skeleton without real RAG access.
- Explicitly excluded Hermes, LM Studio, production Local RAG, embeddings, vector databases, LLM evaluation, external APIs, cloud services, and real-document input.

RAG Benchmark Harness v0.5 completed Phase A-D.

- Designed RAG Benchmark Harness v0.5 synthetic-only retrieval and scoring direction.
- Planned a retrieval adapter boundary, deterministic keyword / token overlap search, ranked result structure, local evaluation metrics, and benchmark exit code policy.
- Added the v0.5 Phase A synthetic retrieval adapter and deterministic keyword / token overlap retrieval.
- Added ranked retrieval results to benchmark JSON and Markdown reports while keeping `evaluation_status` as `not_evaluated`.
- Added v0.5 Phase B hit@k and expected source match evaluation from synthetic ranked results.
- Added `hit_at_k`, `source_match`, `matched_expected_source_ids`, and source-match summary rates to benchmark reports.
- Added v0.5 Phase C keyword coverage, no-result, and unsafe-or-unknown expectation evaluation.
- Added `matched_keywords`, `missing_keywords`, `keyword_coverage_rate`, `no_result_pass`, and `unsafe_or_unknown_pass` to benchmark reports.
- Finalized v0.5 Phase D report, CI, and docs cleanup.
- Added benchmark CI checks for PASS `0`, WARNING `1`, FAIL `2`, and CLI error `3` cases.
- Kept the design free of real RAG connections, Hermes, LM Studio, embeddings, vector databases, LLM evaluation, external APIs, cloud services, and real documents.

PR summary:

- PR #19: Designed v0.5 synthetic retrieval and scoring.
- PR #20: Added the synthetic retrieval adapter.
- PR #21: Added hit@k and expected source match evaluation.
- PR #22: Added keyword coverage, no-result, and unsafe-or-unknown evaluation.
- PR #23: Finalized v0.5 benchmark reports, CI, and docs.

## v0.4

- Designed RAG Benchmark Harness v0.4.
- Planned synthetic corpus and synthetic query set inputs.
- Planned JSON / Markdown benchmark reports.
- Planned local metrics such as hit@k, expected source match, expected keyword coverage, no-result handling, and unsafe / unknown answer handling.
- Kept v0.4 design free of real documents, external API evaluation, cloud services, and LLM-as-a-judge.
- Designed synthetic benchmark fixture structure for corpus Markdown files and JSONL query sets.
- Planned benchmark fixture locations without adding fixture files: `tests/fixtures/benchmark/corpus/` and `tests/fixtures/benchmark/queries.jsonl`.
- Added RAG Benchmark Harness Phase B CLI skeleton for synthetic corpus / query validation.
- Added placeholder JSON / Markdown benchmark reports without connecting to real RAG systems or external evaluators.
- Expanded benchmark report structure with `per_query_results`, `warnings`, `errors`, and `metadata`.
- Kept benchmark query evaluation as `not_evaluated` without retrieval, LLM evaluation, or external API calls.
- Added benchmark CLI checks to the GitHub Actions Tests workflow.
- Documented the v0.4 Phase A-C benchmark harness status and Phase D CI / docs coverage.

PR summary:

- PR #13: Designed the v0.4 RAG Benchmark Harness direction.
- PR #14: Designed synthetic benchmark fixture structure.
- PR #15: Added the benchmark CLI skeleton.
- PR #16: Expanded the benchmark report skeleton.
- PR #17: Added benchmark CLI checks to CI and updated docs.

v0.4 remains synthetic-only. It does not connect to real RAG systems, implement retrieval scoring, use LLM evaluation, or call external APIs.

## v0.3

Masked Document Checker v0.3 completed the Phase A-D improvements.

- Added stronger money, rate, tsubo unit price, and square-meter unit price detection.
- Added address candidate detection for postal codes and address-like context.
- Added contract condition and internal information keyword coverage.
- Added duplicate finding suppression for identical file, line, rule_id, and redacted matched_text.
- Stabilized finding output order.
- Improved Markdown report readability with a summary near the top.
- Kept existing exit codes unchanged.
- Kept existing JSON report keys unchanged.
- Kept matched_text redaction policy.
- Kept fixtures fictional and did not use real documents, real project names, real company names, or real person names.

## v0.2

- Added `--config config/rules.yaml` support.
- Supported `mode: extend_builtin`.
- Preserved built-in rules when config rules are loaded.
- Treated invalid config as CLI error exit code `3`.
