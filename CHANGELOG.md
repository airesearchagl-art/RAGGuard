# Changelog

## Unreleased

### v0.8 secure Local RAG transport design

- Selected loopback HTTP as the first real transport candidate, with Unix domain sockets and Windows
  named pipes deferred for later review.
- Defined loopback-only endpoint validation, DNS resolution and peer checks, redirect rejection,
  proxy isolation, and explicit destination configuration.
- Defined a no-authentication v0.8 policy with no API keys, bearer tokens, credential files, cookies,
  or authorization headers.
- Defined bounded JSON request and ranked response contracts, unknown-field rejection, a proposed
  64 KiB request limit, a 256 KiB default response limit, and a 1 MiB hard response ceiling.
- Defined connect, read, and total deadlines, no retry by default, short-lived lifecycle, and close
  after success or failure.
- Defined safe transport error categories through `RetrievalAdapterError`, `BenchmarkError`, and CLI
  error `3` without endpoint, query, credential, raw traffic, path, or stack-trace disclosure.
- Planned fake loopback security tests before any real Local RAG connection or transport integration.
- Kept this change documentation-only with no localhost, network, socket, named-pipe, filesystem, or
  real-document access.
- Completed Phase A with loopback endpoint, caller-supplied resolution proof, bounded JSON request,
  bounded ranked response, limit-plus-one, and safe HTTP error contracts.
- Added contract tests for endpoint allowlisting, mixed resolution, timeouts, request/response size,
  unknown fields, content type, status, item count, and secret/path non-disclosure.
- Added no DNS lookup, HTTP client, socket connection, localhost traffic, redirect, proxy, or real
  Local RAG connection.
- Completed Phase B with test-only ephemeral IPv4 and optional IPv6 loopback servers using fixed
  synthetic responses and guaranteed shutdown.
- Added live loopback contract coverage for POST/JSON validation, deterministic normalization,
  redirect and invalid-response rejection, exact and limit-plus-one response sizes, peer proof,
  connection refusal, connect/read/total timeout boundaries, no retry, and safe error disclosure.
- Kept the production package free of an HTTP client, DNS lookup, proxy handling, real Local RAG
  access, external/private-LAN traffic, fixture changes, and workflow changes.

### v0.7 Local RAG connection contract design

- Designed a future local-only adapter configuration and transport contract without implementing a connection.
- Defined initialize, health, capability, retrieve, and close lifecycle stages.
- Defined bounded request and ranked-response schemas that exclude long content, real paths, and secrets.
- Restricted future transports to allowlisted local-only modes with timeout, response-size, and no-redirect requirements.
- Mapped local connection failures to bounded adapter categories, `RetrievalAdapterError`, `BenchmarkError`, and CLI error `3`.
- Planned in-memory synthetic contract testing and a future explicit CLI selector while preserving Synthetic as the default.
- Kept real RAG, Hermes, LM Studio, localhost communication, filesystem retrieval, credentials, embeddings, vector databases, LLM evaluation, external APIs, cloud services, and external MCP unimplemented.
- Completed Phase A with validated local retrieval configuration and capability models.
- Added bounded local request/response models and a runtime-checkable transport lifecycle Protocol.
- Added safe local response normalization to `RankedResult`, including top-k, response-size,
  deterministic ordering, identifier, and allowlisted metadata checks.
- Kept `in_memory` as the only allowed transport type and added no transport implementation,
  configuration loading, CLI selector, filesystem access, localhost access, or network access.
- Completed Phase B with a deterministic no-I/O `InMemoryLocalRetrievalTransport`.
- Added explicit lifecycle enforcement, idempotent close behavior, fixed synthetic responses, and
  safe normalization to the existing ranked-result contract.
- Added test-only health, capability, timeout, invalid-response, oversized-response, and transport
  exception injection with bounded `RetrievalAdapterError`, `BenchmarkError`, and CLI error `3` paths.
- Kept the local adapter non-operational and added no config loader, CLI selector, filesystem access,
  localhost access, network communication, real RAG connection, or credential loading.
- Completed Phase C by integrating the internal local adapter client with validated config and the
  in-memory transport.
- Added one-shot initialize, health, capability, retrieve, normalize, and close orchestration with
  guaranteed cleanup and config/transport reference release.
- Added bounded initialize, health, capability, retrieval, invalid/oversized response, and close
  failure handling through existing benchmark and CLI error `3` boundaries.
- Kept Synthetic retrieval as the only CLI behavior and added no config loader, adapter selector,
  filesystem access, localhost/network communication, or real Local RAG connection.
- Completed Phase D with an allowlisted `synthetic` / `local-rag` benchmark CLI selector.
- Added bounded JSON / YAML local config loading for the in-memory transport, timeout, default top-k,
  response-size limit, and capability flags.
- Added per-query one-shot local adapter construction while preserving Synthetic as the default and
  retaining benchmark report keys and exit-code semantics.
- Kept local-rag limited to deterministic in-memory responses with no filesystem retrieval,
  localhost/network communication, credentials, or real Local RAG connection.
- Completed Phase E with synthetic end-to-end tests from CLI and safe config loading through local
  adapter lifecycle, in-memory transport, evaluation, JSON / Markdown reports, and exit codes.
- Added JSON and YAML PASS coverage, WARNING / FAIL evaluation coverage, CLI error coverage, lifecycle
  cleanup assertions, unsafe config rejection, invalid/oversized response checks, and Synthetic
  default regression coverage.
- Added a bounded `retrieval_adapter` identifier to existing report metadata and Markdown Inputs
  without changing top-level report keys or exposing config values, paths, credentials, or content.
- Completed Phase F documentation, explicit local-rag synthetic E2E CI coverage, and v0.7.0 release
  preparation.
- Documented that local-rag remains `in_memory`-only, synthetic-only, and free of filesystem,
  localhost, and network communication.
- Documented the distinction between evaluation FAIL `2` and transport or configuration CLI error
  `3`, plus the one-shot lifecycle and guaranteed close boundary.

PR summary:

- PR #31: Designed the v0.7 Local RAG connection contract and safety boundary.
- PR #32: Added local retrieval configuration and transport contracts.
- PR #33: Added the deterministic in-memory local retrieval transport.
- PR #34: Integrated the local adapter with the in-memory transport lifecycle.
- PR #35: Added the CLI selector and bounded safe JSON / YAML config loading.
- PR #36: Added synthetic local-rag end-to-end tests and report safety coverage.

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
- Completed Phase E documentation, CI contract coverage, and v0.6.0 release preparation.
- Added an explicit CI step for the local-only skeleton CLI error `3` boundary while retaining
  synthetic benchmark success and PASS / WARNING / FAIL / CLI error checks on Python 3.11 and 3.12.
- Completed synthetic migration, mock contract tests, and a local-only adapter skeleton without real RAG access.
- Explicitly excluded Hermes, LM Studio, production Local RAG, embeddings, vector databases, LLM evaluation, external APIs, cloud services, and real-document input.

PR summary:

- PR #25: Designed the v0.6 retrieval adapter interface and safety boundary.
- PR #26: Added the common Protocol, ranked-result model, and runtime validation.
- PR #27: Migrated Synthetic retrieval behind the common adapter contract.
- PR #28: Added mock adapter contract and error-boundary tests.
- PR #29: Added the unconnected local-only adapter skeleton.

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
