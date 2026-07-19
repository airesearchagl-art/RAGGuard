# Design Notes

## RAG Benchmark Harness v0.8 secure Local RAG transport design

v0.8 introduces a design boundary for a future real Local RAG transport. This section is normative
for later implementation phases, but this PR adds no communication, endpoint loading, filesystem
access, or real Local RAG integration.

### Phase A implementation status

- Added a validated `LocalHTTPEndpoint` model for HTTP-only scheme, loopback literals or explicit
  hostname allowlists, bounded port/path/timeouts, and bounded response size.
- Added `LoopbackResolutionContract` so a later client must supply an immediately refreshed complete
  resolution set and verified peer address; the model performs no DNS lookup.
- Added deterministic bounded `HTTPRetrievalRequest` JSON serialization with fixed fields and safe
  optional identifiers.
- Added response status, content-type, byte-limit, JSON/schema, item-count, ranked-result, metadata,
  and unknown-field validation before normalization to `LocalRetrievalResponse`.
- Added the limit-plus-one read contract and bounded HTTP error categories without implementing a
  reader or client.
- Added contract tests for loopback IPv4/IPv6, explicit hostname allowlisting, unsafe endpoints,
  mixed resolution, timeout and size limits, schema rejection, and sensitive-value non-disclosure.
- Added no DNS lookup, HTTP client, socket connection, localhost traffic, redirect, proxy, or real
  Local RAG integration.

### Phase B implementation status

- Added a test-only standard-library HTTP server bound exclusively to ephemeral `127.0.0.1` or,
  where supported, `::1` ports. Every server is shut down, closed, and joined after its test.
- Exercised `POST` and fixed `application/json` request validation, successful response parsing, and
  normalization to the existing ranked-result boundary over actual loopback sockets.
- Fixed rejection behavior for redirects without following them, non-success status, invalid content
  type, non-UTF-8 and invalid JSON, unknown or incomplete fields, and top-k item overflow.
- Fixed configured-limit, exact-limit, limit-plus-one, and absolute-response-ceiling behavior using
  bounded reads before parsing; raw response bodies remain excluded from errors.
- Verified actual peer addresses, mixed or changed peer rejection, immediate-resolution proof,
  IPv4 and optional IPv6 loopback, safe refusal/timeout categories, and one attempt with no retry.
- Added no production HTTP client, DNS lookup implementation, proxy behavior, real Local RAG
  integration, external/private-LAN communication, fixture data, or workflow changes.

### Phase C implementation status

- Added `BoundedLoopbackHTTPClient` as a standard-library, one-request client independent of CLI,
  config loading, benchmark orchestration, and `LocalRAGRetrievalAdapter` integration.
- Resolve allowlisted hostnames immediately before each connection, reject empty, mixed, private, or
  external address sets, choose a deterministic loopback IP literal, and validate the actual peer.
- Send one bounded UTF-8 JSON `POST` with the Phase A request model and normalize the validated Phase
  A response through the existing `RankedResult` boundary.
- Enforce connect and read socket timeouts plus a total deadline across resolution, connection,
  request, bounded limit-plus-one response read, parsing, normalization, and cleanup checks.
- Use `http.client.HTTPConnection` directly, which does not consult environment or system proxy
  settings. Do not follow redirects, retry, pool, tunnel, persist raw traffic, or reuse connections.
- Map resolution, connection, timeout, HTTP, schema, size, and cleanup failures to bounded categories
  without endpoint, query, header, cookie, credential, raw body, socket, or stack-trace disclosure.
- Added production-client tests over test-only IPv4 and optional IPv6 loopback servers, plus injected
  resolution, peer, connect, timeout, and cleanup seams. No real Local RAG endpoint is contacted.

### Phase D implementation status

- Added `loopback_http` beside the existing `in_memory` transport type. Synthetic remains the CLI
  default, and HTTP is constructed only after explicit `--adapter local-rag --adapter-config` use.
- Extended bounded JSON/YAML loading with an HTTP endpoint, connect/read/total timeouts, default
  top-k, response-size limit, capability flags, and an optional explicit hostname allowlist.
- Reject unknown fields and all auth, token, cookie, proxy, redirect, retry, credential, non-HTTP,
  external, private-LAN, wildcard, user-info, query, fragment, encoded-path, and traversal values.
- Added `LoopbackHTTPLocalRetrievalTransport` as the lifecycle wrapper around the single production
  communication boundary, `BoundedLoopbackHTTPClient`. It performs initialize, local health and
  capability checks, one retrieve, normalization, and close through the existing one-shot adapter.
- Preserve PASS `0`, WARNING `1`, FAIL `2`, CLI error `3`, report top-level keys, and
  `metadata.retrieval_adapter`. No endpoint, port, config path, headers, raw body, or credential is
  added to reports or bounded errors.
- Added synthetic fake-loopback integration coverage for evaluation outcomes, invalid config,
  redirect/status/content-type/JSON rejection, response limit, timeout, refusal, mixed resolution,
  proxy isolation, no retry, safe error disclosure, and close after success or failure.
- Added no real Local RAG product integration, filesystem retrieval, external/private-LAN traffic,
  credential handling, fixture changes, or workflow changes. Phase E is completed below.

### Phase E implementation status

- Added a dedicated synthetic HTTP security E2E suite covering CLI selection, bounded JSON/YAML
  config loading, `LocalRAGRetrievalAdapter`, `LoopbackHTTPLocalRetrievalTransport`,
  `BoundedLoopbackHTTPClient`, test-only loopback servers, evaluator results, reports, and exit codes.
- Fixed PASS `0`, WARNING `1`, FAIL `2`, and CLI error `3` while preserving report top-level keys,
  `metadata.retrieval_adapter`, Synthetic default behavior, and the existing `in_memory` path.
- Added CLI-boundary rejection coverage for unknown or credential-related fields, unsafe endpoints,
  invalid bounds, unsafe YAML, non-mapping and oversized configs, malformed schemas, top-k and item
  limits, refusal, timeout, mixed or unverified peers, redirect/status/content-type failures, and
  limit-plus-one responses.
- Require one attempt, no pooling, and close after success or failure. Endpoint, port, config path,
  credentials, raw request/response data, internal exception details, and stack traces remain absent
  from reports and bounded errors.
- Verification remains synthetic-only over ephemeral `127.0.0.1` or supported `::1` test servers.
  No real Local RAG product, real document, external/private-LAN traffic, filesystem retrieval,
  credential loading, fixture change, or workflow change was added. Phase F is completed below.

### Phase F completion status

- Consolidated the Phase A-E endpoint, request/response, client, CLI/config, and synthetic security
  E2E boundaries into release-facing documentation without changing production logic.
- Added a named CI step for the HTTP security E2E suite while retaining full pytest, local-rag
  in-memory E2E, benchmark exit-code checks, and the Python 3.11/3.12 matrix.
- The endpoint is parsed before use, every hostname resolution result must be loopback, resolution is
  repeated immediately before connection, and the actual peer must match the loopback proof.
- Requests and responses remain bounded; connect, read, and total deadlines are mandatory.
  Redirects, proxy discovery, retry, pooling, credentials, and raw traffic persistence are disabled.
- The one-shot lifecycle remains initialize, health check, capability check, retrieve, and close.
  Close is required after success and failure, and errors map to bounded categories through
  `RetrievalAdapterError`, `BenchmarkError`, and CLI error `3`.
- Reports retain existing evaluation fields and the safe adapter identifier. The HTTP transport adds
  no endpoint, port, config path, headers, cookies, credentials, raw request/response, socket detail,
  internal exception, or raw HTTP query payload. The existing benchmark `question` field is retained
  for compatibility.
- Fake loopback servers and fixed synthetic responses verify transport behavior and security
  boundaries without claiming compatibility with a real Local RAG product or real documents.

### v0.8.0 release checklist

- Full pytest suite passes.
- HTTP security E2E and local-rag in-memory E2E suites pass independently.
- Synthetic default returns `0`; loopback HTTP covers `0`, `1`, `2`, and `3`.
- `check-mask --help` and `benchmark --help` succeed.
- Workflow YAML parses; `git diff --check`, bidi, CR-only, and fixture-marker scans are clean.
- GitHub Actions succeeds on Python 3.11 and 3.12.
- `main` is clean and synchronized before creating the annotated tag and GitHub Release.
- Tag and Release creation are separate from this Phase F PR.

### Transport selection and order

1. Loopback HTTP is the first implementation candidate because its request, response, timeout, and
   test boundaries can be made explicit with the Python standard library.
2. Unix domain sockets may be considered later on supported local platforms.
3. Windows named pipes may be considered later with a separately reviewed identifier and ACL model.

Every transport is local-only. External hosts, private LAN targets, wildcard or unspecified binds,
redirect following, and proxy use are forbidden. A response cannot change the destination. Adding a
new transport type or endpoint requires an explicit allowlist and a separate reviewed change.

### Loopback endpoint validation

- Accept literal `127.0.0.1` and `::1` only by default.
- A hostname such as `localhost` is accepted only if explicitly allowlisted and every resolved
  address is loopback. Mixed loopback/non-loopback resolution is rejected.
- Reject `0.0.0.0`, `::`, private LAN, link-local, multicast, public, wildcard, user-info, fragment,
  and non-allowlisted scheme or port values.
- Resolve immediately before each new connection and verify the actual peer destination when the
  client API exposes it. Do not reuse an earlier DNS decision across connections.
- Disable redirects, environment proxy discovery, explicit proxy config, and proxy authentication.
- Keep the validated scheme, host category, and allowlisted port internal. Do not emit the full
  endpoint in reports, logs, or user-facing errors.

These rules reduce DNS rebinding and time-of-check/time-of-use risk. Any inability to prove the peer
is loopback fails closed as `external_host_rejected` or `invalid_endpoint`.

### Authentication policy

v0.8 uses no authentication. This is conditional on the loopback-only endpoint policy. The config
schema does not accept API keys, bearer tokens, credential files, cookies, custom authorization
headers, or environment credential references. Unknown auth-related fields are rejected.

A future authentication design requires a separate security review. Credential values and
authentication failure details must never enter reports, logs, adapter metadata, errors, or stored
raw traffic.

### HTTP request contract

The request method is `POST`, the request content type is exactly `application/json`, and the
accepted response content type is `application/json` with an optional UTF-8 charset. The request
body contains only:

```json
{
  "query": "bounded query text",
  "top_k": 5,
  "query_id": "optional-safe-id",
  "capability_version": "optional-safe-version"
}
```

- `query` is required, non-empty, and limited to the existing 4,096-character boundary.
- `top_k` is required, positive, and limited to the existing maximum of 100.
- `query_id` and `capability_version` are optional bounded safe identifiers.
- Unknown fields are rejected. Filesystem paths, credentials, secrets, cookies, headers, report
  paths, and arbitrary filters are not part of the v0.8 request.
- The serialized UTF-8 JSON body has a proposed hard limit of 64 KiB and is measured before send.

### HTTP response contract

The response uses the existing ranked result boundary:

```json
{
  "results": [
    {
      "rank": 1,
      "document_id": "synthetic-doc-001",
      "score": 1.0,
      "title": "Synthetic document",
      "source_id": "safe-source-001",
      "matched_keywords": ["synthetic"],
      "adapter_metadata": {"transport": "loopback_http"}
    }
  ]
}
```

- The default response limit remains 256 KiB and the absolute configurable ceiling remains 1 MiB.
- Read at most the configured limit plus one byte, then fail before parsing if the limit is exceeded.
- Return no more than `top_k` items and never more than the existing maximum of 100.
- Require contiguous ranks, unique document IDs, finite scores, bounded titles, safe source IDs,
  bounded matched keywords, and allowlisted scalar adapter metadata.
- Reject unknown top-level and result fields. Do not ignore or forward backend-specific payloads.
- Reject long content, snippets, raw document bodies, real paths, credentials, headers, cookies,
  stack traces, and nested unbounded metadata.

### Timeout and retry policy

- Define separate positive bounded connect and read timeouts and enforce an overall total deadline.
- The total deadline is authoritative and includes endpoint resolution, connect, health, capability,
  response read, validation, and cleanup work.
- Do not retry by default. Connection failures, invalid responses, redirects, and timeouts fail once.
- A future retry policy requires an idempotent request contract, a strict attempt cap, the same
  validated loopback destination, and the same total deadline. It must not retry unsafe operations.
- Normalize every timeout without raw exception details to `RetrievalAdapterError("timeout")`.

### Transport lifecycle

1. `initialize`: validate explicit endpoint and construct a short-lived no-proxy client.
2. `health_check`: make a bounded loopback health request without query or secret data.
3. `capability_check`: verify protocol version and required ranked-result capabilities.
4. `retrieve`: send one bounded request and validate status, content type, size, and schema.
5. `close`: release client resources after success or every started failure path.

The adapter remains one-shot or short-lived. Connection pooling, background workers, persistent
sessions, and shared mutable clients are v0.8 non-goals. Retrieval failure takes precedence when
close also fails, while close failure is still mapped to a safe category when it is the only failure.

### Error mapping

| Condition | Safe category | Process result |
| --- | --- | --- |
| Missing config | `not_configured` | CLI error `3` |
| Invalid scheme, host, port, or endpoint | `invalid_endpoint` | CLI error `3` |
| Non-loopback or changed peer | `external_host_rejected` | CLI error `3` |
| Local connection refused | `connection_refused` | CLI error `3` |
| Connect, read, or total deadline exceeded | `timeout` | CLI error `3` |
| Non-success HTTP status | `invalid_status` | CLI error `3` |
| Unexpected content type | `invalid_content_type` | CLI error `3` |
| Response exceeds configured limit | `response_too_large` | CLI error `3` |
| JSON or schema violation | `invalid_response` | CLI error `3` |
| Required protocol capability absent | `unsupported_capability` | CLI error `3` |

Every category is represented by a bounded `RetrievalAdapterError`, then converted to
`BenchmarkError` and CLI error `3`. Messages expose only adapter name and safe category. Endpoint,
query text, headers, cookies, credentials, raw request, raw response, and underlying exception text
are excluded.

### Observability and non-disclosure

Allow only adapter name, bounded duration, result count, status, and safe error category. Do not log
or report the full endpoint, query text, expected answer, credentials, headers, cookies, environment
values, real source paths, request or response bodies, stack traces, or internal exception details.
Raw HTTP traffic is never persisted. A source is represented only by the existing bounded safe
identifier after response validation.

### Synthetic security verification

Phase B uses a fake loopback server with fixed synthetic responses only. Tests must cover endpoint
allowlisting, mixed/non-loopback resolution rejection, redirect rejection, proxy isolation, connect,
read, and total timeout, invalid status, invalid content type, invalid JSON, unknown fields,
oversized response, item overflow, deterministic normalization, lifecycle order, close on failure,
and non-disclosure. Tests do not contact a real Local RAG system or any external network and do not
use real documents.

### v0.8 implementation phases

- Phase A: endpoint and HTTP transport contract - completed.
- Phase B: fake loopback server tests with fixed synthetic responses - completed.
- Phase C: bounded loopback HTTP client - completed.
- Phase D: CLI and safe config integration - completed.
- Phase E: synthetic end-to-end and security tests - completed.
- Phase F: docs, CI, and release preparation - completed.

### v0.8 non-goals

Real Local RAG, Hermes, LM Studio, private-LAN or external-network communication, redirect following,
proxy use, credential loading, filesystem retrieval, embeddings, vector databases, LLM evaluation,
external APIs, cloud services, external MCP, and real-document access are not part of this design PR.

## RAG Benchmark Harness v0.7 Local RAG connection contract

Phase A implements the internal configuration, request, response, normalization, and transport
contracts described below. It does not enable Local RAG, localhost or socket
communication, filesystem retrieval, configuration loading, credentials, or a CLI adapter selector.

### Phase A implementation status

- Added immutable `LocalRetrievalConfig` and `LocalRetrievalCapabilities` models.
- Allowlisted only the no-network `in_memory` transport type for this phase.
- Added bounded `LocalRetrievalRequest`, `LocalRetrievalResult`, and `LocalRetrievalResponse` models.
- Added a runtime-checkable `LocalRetrievalTransport` Protocol covering initialize, health check,
  capability discovery, retrieve, and close lifecycle methods.
- Added response normalization to the existing `RankedResult` model with top-k and encoded-size
  enforcement.
- Rejected path-like source identifiers, unsupported metadata, booleans used as numbers, invalid
  ordering, duplicate documents, and unbounded values without replaying rejected values in errors.
- Kept the local adapter non-operational and retained no configuration or transport object.
- Kept Synthetic retrieval, evaluator ownership, reports, and exit codes unchanged.

### Phase B implementation status

- Added `InMemoryLocalRetrievalTransport` as a runtime Protocol-compatible no-I/O fake transport.
- Fixed lifecycle states to `created`, `initialized`, and `closed`.
- Rejected duplicate initialization; made close idempotent; rejected retrieve, health, and
  capability calls outside the initialized state.
- Returned deterministic fixed synthetic responses with safe identifiers and allowlisted metadata.
- Added a transport execution boundary that converts unexpected exceptions to bounded
  `RetrievalAdapterError` values before response validation and `RankedResult` normalization.
- Added controlled health, capability, timeout, invalid-response, oversized-response, and raw
  transport exception cases for contract tests.
- Verified transport failures reach `BenchmarkError` and CLI error `3` without exposing raw error
  details, paths, or credentials.
- Kept the production local adapter non-operational; Phase C client integration remains unimplemented.
- Added no filesystem access, localhost access, network communication, config loader, or CLI selector.

### Phase C implementation status

- Integrated `LocalRAGRetrievalAdapter` with validated `LocalRetrievalConfig` and
  `InMemoryLocalRetrievalTransport` instances.
- Restricted Phase C client execution to the in-memory transport class and its test subclasses.
- Converted benchmark queries to bounded `LocalRetrievalRequest` values and normalized transport
  responses through the existing `RankedResult` boundary.
- Enforced initialize, health check, capability check, retrieve, and close order inside the adapter.
- Stopped before retrieval when initialization, health, or capability checks fail.
- Closed after successful retrieval and every started failure path; retrieval errors take precedence
  when close also fails.
- Normalized unexpected initialize, health, capability, retrieve, and close exceptions without
  replaying raw details.
- Released config and transport references after each one-shot execution attempt and never retained
  raw responses.
- Kept the adapter internal: no CLI selector, config loader, filesystem access, localhost access,
  network communication, or real Local RAG connection was added.

### Phase D implementation status

- Added `--adapter` with the allowlisted values `synthetic` and `local-rag`; Synthetic remains the
  default and preserves its existing three-argument benchmark execution path.
- Added `--adapter-config` for bounded UTF-8 JSON or YAML files. Local configuration accepts only
  `transport_type`, timeout, default top-k, response-size limit, and capability flags.
- Centralized value validation in `LocalRetrievalConfig` and `LocalRetrievalCapabilities`; the loader
  rejects unsupported fields, formats, transports, booleans used as numbers, and oversized files.
- Restricted local-rag construction to `InMemoryLocalRetrievalTransport` and creates a fresh one-shot
  adapter for every benchmark query.
- Kept file paths, rejected values, credentials, and parser exception details out of CLI errors and
  reports.
- Added no filesystem retrieval, localhost or network communication, real Local RAG connection,
  credential loading, embeddings, vector database access, or LLM evaluation.

### Phase E implementation status

- Added end-to-end tests for CLI selection, bounded JSON and YAML config loading, per-query local
  adapter construction, in-memory lifecycle, evaluator output, JSON / Markdown reports, and exit
  codes `0`, `1`, `2`, and `3`.
- Fixed deterministic PASS, WARNING, and FAIL responses without changing benchmark fixtures or using
  filesystem retrieval, localhost, network communication, or real RAG data.
- Verified initialize, health check, capability check, retrieve, and close order for every successful
  query and verified close on invalid and oversized response failures.
- Covered missing config, non-mapping roots, unknown fields, unsupported transports, invalid bounded
  values, unsafe YAML tags, oversized config files, and invalid or oversized transport responses.
- Added the safe adapter name to existing report metadata and Markdown Inputs while keeping all
  top-level report keys unchanged.
- Verified config paths, timeout and response-size values, credentials, raw responses, exception
  details, and long corpus content are absent from reports and bounded errors. Effective top-k
  remains visible as existing evaluator metadata.
- Preserved Synthetic as the default and retained its fixture result, report shape, and exit code.

### Configuration schema

```yaml
transport_type: in_memory
timeout_seconds: 3.0
default_top_k: 5
response_size_limit: 262144
capabilities:
  ranked_results: true
  matched_keywords: false
  filters: false
```

- The CLI selector identifies `local-rag`; Synthetic remains the default when no selector is provided.
- `transport_type` is allowlisted and Phase D accepts only `in_memory`.
- `timeout_seconds` is positive, finite, and bounded by implementation limits.
- `default_top_k` and `response_size_limit` are positive bounded integers; booleans are rejected.
- Capability flags are booleans negotiated before retrieval. Unsupported required capabilities fail
  before a query is sent.
- Credentials are neither required nor loaded by the v0.7 contract. Configuration values are never
  copied into reports, adapter metadata, or error messages.

### Connection lifecycle

1. `initialize`: validate schema and construct an allowlisted transport without exposing values.
2. `health_check`: verify local availability within the configured timeout.
3. `capability_check`: confirm ranked-result support and any requested optional capability.
4. `retrieve`: send one bounded request and validate one bounded response.
5. `close`: release transport resources idempotently, including after failures.

Initialization, health, capability, retrieval, and close failures are normalized to safe categories.
Unavailable, refused, timed-out, malformed, or unsupported states must not expose underlying exception
text, paths, endpoints, environment values, credentials, response bodies, or stack traces.

### Request contract

```json
{
  "query": "bounded query text",
  "top_k": 5,
  "query_id": "optional-synthetic-id"
}
```

- `query` is a required non-empty string with a future length limit.
- `top_k` is required, positive, and bounded.
- `query_id` is optional and must be a safe identifier, not source content.
- `filters` are reserved for a future version and are rejected unless capability negotiation permits
  a defined safe schema.
- Requests never contain credentials, environment values, filesystem paths, or report destinations.

### Response contract

```json
{
  "results": [
    {
      "rank": 1,
      "document_id": "synthetic-doc-001",
      "score": 1.0,
      "title": "Synthetic document",
      "source_id": "synthetic-source-001",
      "matched_keywords": ["synthetic"],
      "adapter_metadata": {"transport": "in_memory"}
    }
  ]
}
```

Responses are size-bounded and normalized to the existing `RankedResult` contract. `source_id` is
preferred when a path is not safe to reveal; any mapped `source_path` must be an opaque or relative
safe identifier. Results must have contiguous ranks, finite scores, unique document IDs, bounded
strings, and at most `top_k` entries. Long document content, snippets, credentials, real paths, raw
backend metadata, and stack traces are rejected. `adapter_metadata` is allowlisted and bounded.

### Transport and safety boundary

- Prefer no-network in-memory transport for implementation and tests.
- Future network transport permits explicit loopback addresses only. Hostnames that may resolve
  externally, wildcard binds, redirects, proxies, and external targets are rejected.
- Unix sockets and Windows named pipes require an allowlisted local identifier; their concrete paths
  are never reported.
- Every operation has a required timeout and response byte limit.
- The adapter never reads `C:\\AI_Restricted` or real materials under `C:\\AI_Local_RAG` directly.
- Real data access, when separately approved in a later version, occurs only behind the retrieval API;
  no adapter-side filesystem crawl is permitted.

### Error mapping

| Condition | Safe adapter category | Process result |
| --- | --- | --- |
| Missing configuration | `not_configured` | CLI error `3` |
| Missing local dependency | `dependency_unavailable` | CLI error `3` |
| Local connection refused | `connection_refused` | CLI error `3` |
| Required timeout exceeded | `timeout` | CLI error `3` |
| Schema or result violation | `invalid_response` | CLI error `3` |
| Required capability absent | `unsupported_capability` | CLI error `3` |

Each condition becomes a bounded `RetrievalAdapterError`, then `BenchmarkError`, then CLI error `3`.
The user-facing message may include adapter name and safe category only.

### Synthetic connection verification

Contract tests use an in-memory transport by default and may use a fake local server only when a
later phase specifically requires transport behavior. Responses are fixed, synthetic, deterministic,
and body-bounded. Tests cover lifecycle ordering, request shape, response normalization, timeout,
connection refusal, malformed responses, unsupported capabilities, cleanup, and secret/path
non-disclosure. No real documents or external network are used.

### CLI selector

- `synthetic` remains the default and may be selected explicitly.
- `local-rag` is used only when explicitly requested with valid safe configuration.
- Missing or invalid local configuration returns CLI error `3` before retrieval.
- Unknown adapters and a local config supplied to Synthetic also return CLI error `3`.

### Observability

Allowed fields are adapter name, bounded duration, result count, status, and safe error category.
Query text, expected answer data, credentials, configuration values, endpoint/socket identifiers,
real source paths, document content, response bodies, and stack traces are never logged or reported.

### Implementation phases

- Phase A: configuration and transport contract - completed.
- Phase B: in-memory or fake transport - completed.
- Phase C: local adapter client skeleton - completed.
- Phase D: CLI selector and safe configuration loading - completed.
- Phase E: synthetic end-to-end connection tests - completed.
- Phase F: docs, CI, and release preparation - completed.

### v0.7 completed responsibility boundary

- Config loading parses bounded JSON or YAML and delegates field validation to
  `LocalRetrievalConfig`; it never reports rejected values or config paths.
- The transport owns initialize, health, capability, retrieve, and close operations only.
- `LocalRAGRetrievalAdapter` is a one-shot orchestrator that validates requests and responses,
  guarantees close after success or failure, and releases config and transport references.
- The evaluator owns hit@k, source match, keyword coverage, no-result, unsafe-or-unknown, reports,
  and PASS / WARNING / FAIL decisions.
- Safe failures are normalized through `RetrievalAdapterError`, `BenchmarkError`, and CLI error `3`.
- Reports identify the selected path only through the bounded `retrieval_adapter` value and do not
  expose config values, credentials, real paths, raw responses, stack traces, or long content.

### v0.7.0 release boundary

The release covers the no-I/O `in_memory` synthetic path only. Real Local RAG transport, HTTP,
socket, named pipe, filesystem retrieval, Hermes, LM Studio, embedding, vector database, LLM
evaluation, external API, cloud, and external MCP integrations remain unimplemented.

### Non-goals

Real RAG, Hermes, LM Studio, localhost HTTP implementation, filesystem retrieval, embeddings, vector
databases, LLM evaluation, external APIs, cloud services, external MCP, real-document access, and
credential loading are not part of this design PR.

## RAG Benchmark Harness v0.6 retrieval adapter interface design

Phase A implementation status:

- Added a runtime-checkable retrieval adapter protocol with adapter name and `retrieve(query, top_k)` contract.
- Extracted the common ranked-result model into `ragguard.retrieval`.
- Added validation for field types, positive contiguous ranks, finite numeric scores, duplicate sources, result limits, and optional adapter metadata.
- Validated adapter output before benchmark evaluation and converted contract violations to the existing benchmark error boundary.
- Kept absent `adapter_metadata` out of serialized reports to preserve existing report output.
- Kept the synthetic adapter's deterministic score, document-id, and source-path ordering.
- Did not add a real RAG connection or change benchmark result and exit-code semantics.

Phase B implementation status:

- Moved `SyntheticRetrievalAdapter` and retrieval-only matching helpers into `ragguard.retrieval`.
- Added a retrieval-document protocol for the synthetic corpus fields used by the adapter.
- Routed every adapter execution through `retrieve_and_validate` before evaluator input.
- Removed synthetic query-term construction, document matching, ranking, and tie-breaking from the benchmark evaluator module.
- Kept ranked-result dictionary conversion at the report boundary only.
- Preserved deterministic score-descending, document-id, and source-path ordering.
- Preserved existing benchmark JSON / Markdown output, evaluation results, and exit codes.

Phase C implementation status:

- Added a deterministic test-only mock adapter with injectable ranked results and failures.
- Fixed contract coverage for empty, single, and multiple results; optional metadata; contiguous
  ordering; field types; duplicate documents; and top-k limits.
- Normalized unexpected adapter exceptions to a bounded retrieval error before benchmark evaluation.
- Verified that invalid adapter output reaches benchmark CLI error `3` without moving hit@k, source
  match, keyword coverage, or exit-code decisions into adapters.

Phase D implementation status:

- Added `LocalRAGRetrievalAdapter` as a Protocol-compatible, local-only skeleton.
- Defined a constructor boundary that records configuration presence without reading or retaining
  endpoint, path, environment, credential, or other configuration values.
- Kept retrieval explicitly unavailable with bounded `not configured` and `dependency is unavailable`
  errors that contain no internal path, value, or underlying exception detail.
- Routed skeleton failures through `RetrievalAdapterError`, `BenchmarkError`, and CLI error `3`.
- Added no CLI selector, filesystem access, localhost communication, network connection, or report data.

Phase E completion status:

- Consolidated Phase A-D interface, model, migration, contract-test, and skeleton status in docs.
- Added explicit CI coverage for synthetic benchmark success and the local skeleton CLI error `3`
  boundary while retaining Python 3.11 / 3.12 and benchmark exit-code checks.
- Marked `LocalRAGRetrievalAdapter` as skeleton-only, not operational, and unavailable from the CLI.
- Preserved evaluator ownership of metrics, reports, status, and exit-code decisions.

### Goal and boundary

v0.6 defines a replaceable retrieval boundary. An adapter performs retrieval only: it receives a
validated query plus a requested `top_k`, and returns ranked results or a retrieval error. It does
not evaluate benchmark expectations, decide benchmark status, write reports, or map benchmark
results to process exit codes.

The benchmark evaluator remains responsible for hit@k, expected source match, keyword coverage,
no-result, unsafe-or-unknown expectations, summary counts and rates, JSON and Markdown reports,
and PASS `0` / WARNING `1` / FAIL `2` decisions. CLI or validation failures, including adapter
initialization, query execution, timeout-equivalent, unavailable dependency, and invalid-result
failures, remain CLI error `3` and must avoid exposing sensitive source content.

### Interface contract

The planned interface is equivalent to:

```text
adapter.name: str
adapter.retrieve(query, top_k) -> list[RankedResult]
```

`query` is the existing validated benchmark query model. `top_k` is a positive caller-supplied
limit. The adapter returns at most `top_k` results in deterministic order, with ranks beginning at
`1` and increasing without gaps. Implementations must document their tie-break rule; the synthetic
adapter continues to use deterministic score, `document_id`, then source-path ordering.

Every ranked result must provide:

- `rank`: one-based integer rank.
- `document_id`: stable source identifier.
- `score`: adapter-local numeric retrieval signal.
- `matched_keywords`: bounded labels that explain lexical matches when available.
- `title`: display-safe document title.
- `source_path`: stable source location relative to the adapter input boundary.

`adapter_metadata` is optional and namespaced by the adapter. It may contain bounded operational
metadata, but must not contain long document body text, unredacted sensitive content, or values
that the evaluator would treat as common metrics.

### Adapter candidates

- `SyntheticRetrievalAdapter`: current deterministic keyword/token-overlap implementation over synthetic corpus documents.
- `LocalRAGRetrievalAdapter`: future local-only skeleton; it is not connected to Local RAG in v0.6.
- `MockRetrievalAdapter`: test-only deterministic adapter for contract and evaluator tests.
- External API adapters are explicitly out of scope.

### Adapter and evaluator separation

The adapter owns corpus-specific initialization, query execution, retrieval ordering, and its local
score. The evaluator consumes normalized ranked results and owns all expectation comparisons. This
prevents score meaning from one retrieval method from leaking into cross-adapter evaluation. A
future adapter must therefore normalize required result fields before returning them and must not
emit hit@k, source-match, keyword-coverage, or benchmark status fields.

### Error and safety boundary

Adapter construction failures, unavailable dependencies, and invalid adapter configuration are
reported as CLI error `3`. Query execution failures, timeout-equivalent conditions, and malformed
or non-deterministically ordered results are likewise converted to bounded CLI errors. Reports may
state an adapter name and short error category, but never replay a query's source body or detailed
environment paths.

v0.6 reads neither `C:\\AI_Restricted` nor real materials under `C:\\AI_Local_RAG`. It uses
synthetic fixtures only and does not connect to Hermes, LM Studio, production Local RAG, embedding
providers, vector databases, LLM evaluators, external APIs, cloud services, or external MCP.

### Implementation phases

- Phase A: extract the interface and common ranked-result model.
- Phase B: migrate synthetic deterministic retrieval behind the interface.
- Phase C: add a mock adapter and adapter contract tests - completed.
- Phase D: add a local-only adapter skeleton without real RAG access - completed.
- Phase E: finalize docs, CI coverage, and release notes - completed.

### v0.6.0 release checklist

- Phase A-E are complete and merged through review before tagging.
- Python 3.11 and 3.12 workflow jobs pass.
- Full pytest, synthetic benchmark execution, benchmark exit codes, and local skeleton error `3` pass.
- `check-mask` and `benchmark` help remain unchanged.
- JSON / Markdown report top-level keys and Synthetic adapter output remain compatible.
- The local adapter remains skeleton-only with no CLI selector or filesystem, localhost, or network access.
- No configuration value, path, credential, real document, or internal exception detail is reported.
- Tag and GitHub Release creation occur only after the release-summary PR is merged.

### Non-goals

v0.6 does not implement Hermes or LM Studio connections, real RAG search, embedding generation,
vector database access, LLM evaluation, external API or cloud integration, external MCP use, or
real-document loading.

## RAG Benchmark Harness v0.5 synthetic retrieval design

Phase A-D implementation status:

- Added a synthetic-only retrieval adapter.
- Added deterministic keyword / token overlap retrieval.
- Added ranked results to benchmark JSON and Markdown reports.
- Added hit@k evaluation with default top-k `5`.
- Added expected source match evaluation against top-k ranked results.
- Added per-query `hit_at_k`, `source_match`, and `matched_expected_source_ids`.
- Added expected keyword coverage with `matched_keywords`, `missing_keywords`, and `keyword_coverage_rate`.
- Added no-result expected evaluation.
- Added unsafe-or-unknown expected evaluation without LLM judgment.
- Added summary counts and rates for evaluated queries, hit@k, source match, keyword coverage, no-result, and unsafe-or-unknown expectations.
- Stabilized the v0.5 JSON / Markdown report fields for benchmark metrics.
- Added CI checks for benchmark PASS / WARNING / FAIL / CLI error exit codes.
- Kept the implementation disconnected from real RAG systems, Hermes, LM Studio, embeddings, vector databases, LLM evaluation, cloud services, and external APIs.

v0.5 is a design step for synthetic-only retrieval and scoring. It must not connect to production
Local RAG, Hermes, LM Studio, real documents, embedding providers, vector databases, LLM evaluation,
cloud services, external APIs, or external MCP services.

### Retrieval adapter responsibility

The retrieval adapter should be a narrow boundary between benchmark input loading and benchmark
evaluation. Its responsibilities are:

- load validated synthetic corpus documents
- accept one benchmark query at a time
- return deterministic ranked results
- avoid deciding PASS / WARNING / FAIL by itself
- avoid writing benchmark reports directly

The benchmark evaluator consumes ranked results and query expectations. This separation keeps future
retrieval implementations replaceable without changing scoring and reporting contracts.

### Synthetic retrieval method

The v0.5 implementation should start with a simple keyword / token overlap search.

- Use synthetic corpus and synthetic queries only.
- Prefer Python standard library functionality where possible.
- Normalize text deterministically before matching.
- Compare query tokens and expected keywords against document title, tags, expected searchable facts, and content.
- Do not use embeddings, vector databases, LLM calls, external APIs, cloud services, or production RAG indexes.
- Tie-breaking must be deterministic, for example by score descending, then `document_id`, then `source_path`.

### Ranked result structure

Each ranked result should include:

- `rank`
- `document_id`
- `score`
- `matched_keywords`
- `title`
- `source_path`

Reports should not replay long document content. Short identifiers, titles, matched keyword labels,
and source paths are enough for the benchmark report.

### Evaluation specification

The evaluator should produce per-query status from ranked results and query expectations.

- `hit@k`: whether at least one expected source appears within the top-k results
- expected source match: whether expected source IDs are represented in ranked results
- expected keyword coverage: whether expected keywords are covered by matched keywords or retrieved metadata
- no-result expected: pass when no relevant result is returned for queries that expect no result
- unsafe-or-unknown expected: pass or warning when the harness can represent that no confident answer should be produced
- per-query status: `pass`, `warning`, `fail`, or `not_evaluated`

`not_evaluated` remains valid only for phases or query types where scoring is intentionally not yet implemented.

### Summary metrics

Benchmark summary should be deterministic and machine-readable.

- `total_queries`
- `evaluated_queries`
- `passed`
- `warned`
- `failed`
- `hit_at_k`
- `source_match_rate`
- `keyword_coverage_rate`

Rates should document their denominator. Queries that remain `not_evaluated` should not silently inflate
success rates.

### Exit code policy

The benchmark CLI should align with the existing PASS / WARNING / FAIL / CLI error model.

- PASS: exit `0`
- WARNING: exit `1`
- FAIL: exit `2`
- CLI / validation error: exit `3`

This does not change `check-mask` behavior or exit codes.

### v0.5 implementation order

- Phase A: retrieval adapter / deterministic keyword search - implemented
- Phase B: hit@k / expected source match - implemented
- Phase C: keyword coverage / no-result / unsafe-or-unknown evaluation - implemented
- Phase D: report / CI / docs cleanup - implemented

### v0.5 completion summary

v0.5 completes the synthetic-only benchmark loop from corpus/query loading through deterministic
retrieval, local scoring, JSON / Markdown reporting, and CI exit-code checks. It is intentionally
not a production RAG connector.

Delivered behavior:

- synthetic retrieval adapter
- deterministic keyword / token overlap retrieval
- ranked results
- hit@k
- expected source match
- keyword coverage
- no-result expectation evaluation
- unsafe-or-unknown expectation evaluation without LLM judgment
- PASS / WARNING / FAIL / CLI error exit code alignment

Not implemented in v0.5:

- production Local RAG connection
- Hermes / LM Studio connection
- embedding retrieval
- vector database retrieval
- LLM-based evaluation
- external API / cloud integration

### Safety constraints

- Use synthetic fixtures only.
- Do not add real documents, real project names, real company names, or real person names.
- Do not read `C:\AI_Restricted`.
- Do not use real materials under `C:\AI_Local_RAG`.
- Keep Local RAG integration loosely coupled and design-only until a later version.

## RAG Benchmark Harness v0.4 設計

v0.4では、RAG Benchmark Harnessを設計します。この機能はLocal RAG本線を直接操作せず、RAG品質を外部から検証する補助ツールとして扱います。最初の実装対象は、実資料を使わないsynthetic corpusとsynthetic query setのみです。

### 目的

- RAG検索結果が期待するsynthetic sourceに到達できるかを確認する
- 回答または検索結果に期待キーワードが含まれるかを確認する
- no-result queryやunknown扱いが必要なqueryを評価対象に含める
- 外部API、クラウドサービス、LLM-as-a-judgeを使わず、ローカルで再現できる評価に限定する

### CLI案

実装時のCLI案は以下です。v0.4設計PRでは実装しません。

```powershell
python -m ragguard benchmark --corpus "path\to\synthetic_corpus" --queries "queries.jsonl" --output "outputs\benchmark"
```

将来オプション候補:

- `--top-k 5`: hit@k判定に使う検索件数
- `--format both`: JSON / Markdown両方のreport出力
- `--strict`: WARNINGをFAIL相当に扱う運用モード

### 入力形式案

`--corpus` はsynthetic Markdownまたはtext corpusのディレクトリを想定します。実資料、実案件名、実会社名、実個人名は入れません。

`--queries` はJSON Linesを想定します。

```jsonl
{"query_id":"q001","question":"Sample policy text is stored where?","expected_sources":["policy_sample.md"],"expected_keywords":["Sample Policy"],"expected_answer_hints":["fictional policy"],"expect_result":true}
{"query_id":"q002","question":"Unknown sample item exists?","expected_sources":[],"expected_keywords":[],"expected_answer_hints":[],"expect_result":false}
```

主なフィールド:

- `query_id`: queryの安定ID
- `question`: synthetic question
- `expected_sources`: 期待するsource file名または相対path
- `expected_keywords`: 検索結果または回答に含まれるべき語
- `expected_answer_hints`: 回答の方向性を示す短いhint
- `expect_result`: no-result queryを明示するboolean

### 出力形式案

既存方針に合わせ、JSON reportとMarkdown reportを出力します。

JSON report候補:

- `status`
- `checked_query_count`
- `summary`
- `results`
- `config`

per-query result候補:

- `query_id`
- `status`: `PASS` / `WARNING` / `FAIL`
- `hit`
- `matched_sources`
- `missing_sources`
- `matched_keywords`
- `missing_keywords`
- `notes`

Markdown reportは、summaryを先頭に置き、queryごとのPASS / WARNING / FAILを短く確認できる形にします。

### 評価指標案

- `hit@k`: 期待sourceがtop-k内に含まれるか
- expected source match: `expected_sources`との一致
- expected keyword coverage: `expected_keywords`の充足率
- no-result query handling: `expect_result: false`のqueryで不要なhitが出ないか
- unsafe / unknown answer handling: unknown扱いが必要なqueryで断定しすぎないか

v0.4ではLLM評価や外部API評価は使いません。回答の自然言語品質ではなく、source / keyword / hintに基づく機械的な確認を優先します。

### exit code方針案

Masked Document Checkerと揃え、以下の考え方にします。

- `PASS` / exit `0`: 全queryが期待条件を満たす
- `WARNING` / exit `1`: 一部queryに確認対象があるが重大な欠落ではない
- `FAIL` / exit `2`: 期待source未hit、必須keyword不足、no-result queryの誤hitなど
- CLI error / exit `3`: 入力path不備、JSONL不備、必須キー不足など

### v0.4実装フェーズ案

- Phase A: synthetic benchmark fixture設計
- Phase B: benchmark CLI skeleton
- Phase C: JSON / Markdown report生成
- Phase D: CI / docs整理

## RAG Benchmark Harness v0.4 Phase A: synthetic benchmark fixture設計

Phase Aでは、Benchmark Harnessの実装に入る前に、synthetic corpusとsynthetic query setの形を固定します。ここで扱うデータはすべて架空データに限定し、実資料、実案件名、実会社名、実個人名は使いません。`C:\AI_Restricted` や `C:\AI_Local_RAG` 配下の実資料も参照しません。

### synthetic corpus構造案

配置案は将来の実装時に `tests/fixtures/benchmark/corpus/` とします。ただし、この設計PRではfixtureファイルを作成しません。

corpus文書はMarkdownを想定し、各文書の先頭にYAML front matter相当のmetadataを置く方針です。本文も架空の説明文のみを使います。

```markdown
---
document_id: sample-policy-001
title: Sample Policy Document
tags:
  - policy
  - synthetic
expected_searchable_facts:
  - "Sample policy documents are stored in the sample archive."
  - "Synthetic policies use placeholder department names."
---

# Sample Policy Document

This fictional document describes a synthetic policy for benchmark testing.
```

主な項目:

- `document_id`: query側から参照する安定ID。ファイル名変更に強くするため、source filenameとは分けます。
- `title`: reportで人間が確認しやすい短いタイトル。
- `tags`: corpusの分類や将来の絞り込み確認に使う任意のラベル。
- `content`: Markdown本文。架空の文章のみを入れます。
- `expected_searchable_facts`: RAG検索で拾えるべき事実を短文で列挙します。評価時の期待値整理に使います。

### synthetic query set構造案

配置案は将来の実装時に `tests/fixtures/benchmark/queries.jsonl` とします。ただし、この設計PRではJSONLファイルを作成しません。

1行1queryのJSON Linesを想定します。

```jsonl
{"query_id":"q001","question":"Where are sample policy documents stored?","expected_source_ids":["sample-policy-001"],"expected_keywords":["sample archive"],"expected_answer_hint":"sample archive","no_result_expected":false,"unsafe_or_unknown_expected":false}
{"query_id":"q002","question":"What is the private address of the sample owner?","expected_source_ids":[],"expected_keywords":[],"expected_answer_hint":"","no_result_expected":true,"unsafe_or_unknown_expected":true}
```

主な項目:

- `query_id`: queryの安定ID。reportとtestで参照します。
- `question`: synthetic corpusに対する架空の質問。
- `expected_source_ids`: hitすべき `document_id` の配列。
- `expected_keywords`: answerまたはretrieved textに含まれるべき短い語句。
- `expected_answer_hint`: 完全一致ではなく、人間と機械が期待回答を確認するための短いhint。
- `no_result_expected`: corpus内に答えがないことを期待するqueryかどうか。
- `unsafe_or_unknown_expected`: 不明・回答不可・安全側の回答を期待するqueryかどうか。

### fixture配置案

将来のPhase B以降で実ファイルを追加する場合の配置案は以下です。

```text
tests/fixtures/benchmark/
  corpus/
    sample-policy-001.md
    sample-faq-001.md
  queries.jsonl
```

corpusとqueriesは、RAG Benchmark HarnessのCLI skeleton実装後に最小件数から追加します。Phase A設計PRでは、実装コード、tests、fixture追加は行いません。

### 禁止データ方針

- 実資料をbenchmark fixtureに使いません。
- 実案件名、実会社名、実個人名をcorpusやqueryに入れません。
- `C:\AI_Restricted` は読みません。
- `C:\AI_Local_RAG` 配下の実資料は読みません。
- 外部API、クラウドサービス、LLM評価は使いません。

### Phase B以降の実装順

- Phase B: `benchmark` CLI skeletonを追加し、synthetic corpus / queriesの読み込みだけを確認します。
- Phase C: JSON / Markdown benchmark reportを生成します。
- Phase D: CI / docsを整理し、fixtureとCLIの最小運用例を固定します。

### Phase B実装範囲

Phase Bでは `python -m ragguard benchmark --corpus <dir> --queries <jsonl> --output <dir>` を追加します。対象はsynthetic corpus / queries JSONLの読み込みとvalidationまでです。

corpus validationでは、Markdown front matter由来の `document_id`、`title`、`tags`、`expected_searchable_facts` と、Markdown本文としての `content` を必須にします。query validationでは `query_id`、`question`、`expected_source_ids`、`expected_keywords`、`expected_answer_hint`、`no_result_expected`、`unsafe_or_unknown_expected` を必須にします。`expected_source_ids` はcorpus内の `document_id` と照合します。

Phase Bのreportはplaceholderです。corpus件数、query件数、validation error件数、未評価であることをJSON / Markdownに出力します。実RAG接続、retrieval実行、LLM評価、外部API評価はPhase Bでは行いません。

### Phase C実装範囲

Phase Cでは、実RAG接続や検索評価を追加せず、benchmark report skeletonを将来の評価に使いやすい形へ拡張します。JSON reportは `result`、`summary`、`corpus_count`、`query_count`、`per_query_results`、`warnings`、`errors`、`metadata` を持つ構造にします。

`per_query_results` はqueryごとに `query_id`、`question`、`expected_source_ids`、`expected_keywords`、`expected_answer_hint`、`no_result_expected`、`unsafe_or_unknown_expected`、`evaluation_status`、`notes` を保持します。Phase Cでは評価未実装であることを明示するため、`evaluation_status` は `not_evaluated` とします。

Markdown reportは `Summary`、`Inputs`、`Per-query Results`、`Warnings`、`Errors` の順で、人間が入力件数と未評価状態を確認しやすい構成にします。valid inputはexit code `0`、validation error / CLI errorはexit code `3` の方針を維持します。

### Phase D CI / docs整理

Phase Dでは、Phase A-Cで整備したbenchmark fixture、CLI skeleton、report skeletonをCIとdocsに接続します。GitHub Actions `Tests` workflowで `python -m ragguard benchmark --help` とsynthetic fixtureによるreport生成を確認し、既存のpytest、`check-mask --help`、`check-mask --config` 確認は維持します。

v0.4の現状は以下です。

- Phase A: synthetic corpus / queries JSONLのfixture構造を設計
- Phase B: `benchmark` CLI skeleton、input validation、placeholder report生成を追加
- Phase C: JSON / Markdown benchmark report skeletonを拡充
- Phase D: benchmark CLIをCI確認対象に追加し、README / USAGE / DESIGN_NOTES / CHANGELOGを整理

Phase Dでも、実RAG接続、検索評価、LLM評価、外部API利用は行いません。fixtureは架空データのみを使い、実資料、実案件名、実会社名、実個人名は追加しません。

## RAG Benchmark Harness v0.4 完了整理

v0.4では、Local RAG本線とは疎結合な補助ツールとして、RAG Benchmark Harnessの土台を整備しました。対象はsynthetic fixtureのみで、実資料、実案件名、実会社名、実個人名は使いません。

完了範囲:

- Phase A: synthetic corpus / queries JSONLのfixture構造を設計
- Phase B: `benchmark` CLI skeleton、input validation、placeholder report生成を追加
- Phase C: JSON / Markdown benchmark report skeletonを拡充
- Phase D: benchmark CLI確認をGitHub Actions `Tests` workflowに追加し、docsを整理

v0.4では、実RAG接続、検索評価、LLM評価、外部API利用は行いません。`per_query_results` の `evaluation_status` は `not_evaluated` とし、将来の評価実装に備えたreport skeletonとして扱います。

将来のPhase候補:

- benchmark retrieval adapterの設計
- hit@k、expected source match、expected keyword coverageのローカル評価実装
- no-result / unsafe-or-unknown queryの評価方針整理
- report schema互換性を維持したCI拡張
- Local RAG本線を直接変更しないadapter境界の設計

LLM評価や外部API評価は、別途安全方針を設計するまで導入しません。

## Masked Document Checker v0.3 完了整理

v0.3では、Phase A-Dとして検出範囲とレポートの扱いやすさを段階的に強化しました。Phase Aで金額・料率・坪単価 / 平米単価、Phase Bで住所候補、Phase Cで契約条件 / 内部情報キーワード、Phase Dで重複finding抑制とMarkdown summary改善を追加しました。

既存のexit code、JSONレポート既存キー、Markdownレポートの基本情報、`matched_text` 伏せ字方針は維持します。入力ファイルは変更せず、実資料や実案件由来のfixtureは使いません。

## Masked Document Checker v0.3 ルール拡張設計

v0.3では、v0.2で整備した `--config` / `mode: extend_builtin` の基盤を前提に、見逃しを減らす方向で検出ルールを拡張します。誤検知は一定許容し、RAG_OK投入前の人間レビューに回す安全側の判定を優先します。

### Phase A 実装範囲

Phase Aでは、金額・料率・単価の検出を小さく強化します。対象は、円 / 万円 / 億円 / 千円、カンマ付き数値、小数付き数値、税込 / 税別の周辺表現、% / ％ / パーセント表記、料率 / 利率 / 手数料率、坪単価 / 平米単価 / ㎡単価 / m2単価です。

検出時のseverityは既存の金額系ルールと同じく `FAIL` を維持します。`matched_text` は具体的な金額・料率・単価を長く再掲せず、`[REDACTED_AMOUNT]` または `[REDACTED_RATE]` として伏せ字化します。

### Phase B 実装範囲

Phase Bでは、住所候補の検出を小さく強化します。対象は郵便番号形式、都道府県 + 市区町村らしき表現、丁目 / 番地 / 号 / 建物名らしき表現、住所 / 所在地 / 現地 / 物件所在地の周辺キーワードです。

住所候補はRAG_OK投入前に確認すべき情報として `FAIL` を基本にします。`matched_text` は住所全文を長く再掲せず、`[REDACTED_ADDRESS]` として伏せ字化します。

### Phase C 実装範囲

Phase Cでは、契約条件と内部情報キーワードの検出を小さく強化します。対象は契約条件、特約、解約条項、違約金、秘密保持、NDA、優先交渉、専属専任、手付、支払条件、社内限り、内部資料、非公開、未公開、稟議、決裁、承認前、ドラフト、取扱注意です。

契約条件・内部情報はRAG_OK投入前に確認すべき情報として `FAIL` を基本にします。`matched_text` は具体的な契約文や内部情報文を長く再掲せず、`[REDACTED_KEYWORD]` として伏せ字化します。

### Phase D 実装範囲

Phase Dでは、同一ファイル、同一行、同一 `rule_id`、同一伏せ字後 `matched_text` のfindingを重複排除します。別の `rule_id` や別行のfindingは、レビュー対象として残します。

findingの出力順は、file path、line number、severity、rule_id、matched_text の順で安定化します。Markdownレポートは既存情報を維持しつつ、summaryでstatus、checked files、finding数、FAIL / WARNING件数を先に確認できる形にします。

### 検出拡張方針

- 住所表現は、都道府県、市区町村、丁目・番地・号、郵便番号、建物名らしき語を組み合わせて住所候補として検出します。単独の地名だけでは誤検知が多いため、Phase Bでは複数要素が同一行にある場合を優先します。
- 金額表現は、円、万円、億円、税込、税別、概算、見積、予算、上限、下限などを対象にします。数値だけでは検出せず、金額単位または金額文脈キーワードとの組み合わせを優先します。
- 坪単価 / 平米単価は、坪、平米、m2、㎡、単価、円/坪、円/㎡、万円/坪、万円/㎡などを組み合わせて検出します。建築・不動産系文書ではRAG投入前に確認すべき情報として `WARNING` から始めます。
- 契約条件キーワードは、契約、解除、違約、NDA、秘密保持、支払条件、納期、検収、瑕疵、保証、責任範囲などを候補にします。明示的な条件や条項に近い表現は `FAIL`、文脈確認が必要な単語単体は `WARNING` を基本にします。
- 内部情報キーワードは、未公開、社外秘、内部資料、暫定、稟議、承認前、原価、粗利、調整中、役員確認などを候補にします。外部共有前に確認すべき語として、初期は安全側に `WARNING` を多めにします。

### finding整理方針

- 重複findingは、同一ファイル・同一行・同一 `rule_id`・同一検出範囲が重なる場合に抑制する方針です。v0.3初期ではレポート互換性を優先し、dedupeは内部処理に留めます。
- 1行内に複数検出がある場合は、カテゴリや `rule_id` が異なるものは原則として別findingにします。同一カテゴリで過度に重なる場合のみ、後続Phaseで集約を検討します。
- レポートのJSON / Markdown構造は維持し、既存の `file`、`line`、`category`、`severity`、`rule_id`、`matched_text`、`recommendation` の互換性を壊しません。

### 安全方針

- `matched_text` は引き続き伏せ字化し、メールアドレス、電話番号、住所、金額、契約条件、内部情報の具体値をレポートへ露出しない方針を維持します。
- 入力ファイルは変更せず、自動削除、自動上書き、自動移動も行いません。
- fixtureには実資料、実案件名、実会社名、実個人名を使いません。追加テストは架空データのみで作成します。
- config YAMLにも実案件名、実会社名、実個人名を入れません。
- 外部API、クラウドサービス、外部MCPは使わず、ローカル処理のみで検出します。

### 実装優先順位

- Phase A: 金額・料率・単価の検出強化。建築・不動産文書で漏れた場合の影響が大きく、既存のmoneyカテゴリに自然に追加できます。
- Phase B: 住所らしき表現の検出強化。誤検知を抑えるため、複数要素の組み合わせを設計してから追加します。
- Phase C: 契約条件・内部情報キーワード拡張。キーワード追加で効果を出しやすい一方、文脈依存が強いため `WARNING` 中心で段階導入します。
- Phase D: 重複finding抑制とレポート見やすさ改善。検出対象を増やした後に、ノイズを整理してレビュー負荷を下げます。

## MVPの検出方針

Masked Document Checkerは、Markdown内の行を対象に正規表現とキーワードで検出します。誤検知を一定許容し、見逃しを減らす安全側の判定を優先します。

## 限界

正規表現ベースのため、文脈理解は限定的です。たとえば「契約」は単語単体ではWARNINGですが、「契約条件」「違約金」などはFAILとして扱います。

フルネーム推定は誤検知が多いため、MVPでは「担当者名: ...」のような明示ラベル付き表現のみWARNINGに留めます。

## 非破壊方針

入力ファイルは変更しません。自動修正、削除、移動、上書きは行いません。レポートは指定された出力フォルダにのみ作成します。

## 外部依存

v0.2では、ローカルYAML設定読込に `PyYAML` を使います。外部API、クラウドサービス、外部MCPは使いません。

## Masked Document Checker v0.2 設定ファイル仕様

v0.2では、`--config config/rules.yaml` によるルール読込に対応します。

### 読込方針

config未指定時は、これまでどおり内蔵ルールのみを使用します。config指定時は、MVP v0.2では `mode: extend_builtin` を採用し、内蔵ルールにユーザー定義ルールを追加します。

内蔵ルールの完全置き換えは誤設定時の見逃しリスクが高いため、v0.2では採用しません。`mode: extend_builtin` 以外はCLIエラー exit code `3` とします。

### ルール構造

`rules` 配下の各要素は、以下のキーを持つ想定です。

- `rule_id`: ルールの一意なID
- `category`: findingの分類
- `severity`: `WARNING` または `FAIL`
- `type`: `regex` または `keyword`
- `pattern`: `type: regex` の正規表現
- `keywords`: `type: keyword` の文字列配列
- `recommendation`: レポートに出す短い推奨対応
- `redaction`: `matched_text` の伏せ字方法

`category` は当面、以下の候補に寄せます。

- `personal_info`
- `money`
- `contract`
- `internal`
- `name_candidate`
- `address_candidate`

### regex / keyword の違い

`type: regex` はメールアドレス、電話番号、金額、料率など、形式で判定しやすい表現に使います。`pattern` はPython `re` 互換を前提にします。

`type: keyword` は「予算」「契約」「未公表」など、単語や短い語句の出現を検出します。`keywords` の各要素を安全側に検出し、文脈判断が必要なものは `WARNING` に留めます。

### 設定不備時の扱い

設定ファイル不備、未知の `severity`、未知の `type`、必須キー不足、正規表現コンパイル失敗はCLIエラーとし、exit code `3` で終了する方針です。

v0.2では `mode` は `extend_builtin` のみを許容します。それ以外の値、または未指定はCLIエラー exit code `3` とします。

`rule_id` が重複した場合は、内蔵ルールとの重複、ユーザー定義ルール同士の重複のどちらもCLIエラー exit code `3` とします。既存ルールの暗黙上書きは行いません。

`redaction` の許容値は `partial`、`label`、`keyword` とします。未知の値はCLIエラー exit code `3` とし、マスク方針が曖昧なルールは実行しません。

エラーメッセージには、設定ファイルのパス、`rule_id`、不足キー、原因の種類のみを含めます。入力Markdown内の機微情報や、検出対象文字列をエラーに再掲しません。

### レポート互換性

既存のJSON / Markdownレポート構造は維持します。`findings` の `file`、`line`、`category`、`severity`、`rule_id`、`matched_text`、`recommendation` は引き続き出力します。

ユーザー定義ルールを追加しても、既存利用者が `masked_check_report.json` と `masked_check_report.md` を読み続けられることを優先します。

### セキュリティ方針

`matched_text` は引き続き伏せ字化します。入力ファイルは変更せず、自動修正、削除、移動、上書きは行いません。

外部API、クラウドサービス、外部MCPは使いません。fixtureやサンプル設定には実資料、実案件名、実会社名、実個人名を使いません。
