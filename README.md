# RAGGuard

v0.28 adds an Explicit One-Shot Real-Data Trial Approval / Root Provisioning Boundary. It
exact-binds the live v0.25 authorization and usage objects to the v0.27 root descriptor, resolver
policy, opaque target reference, an opaque provisioned-root identity, and five object-backed root
verification results. Independent security and data-governance reviews precede a distinct
execution approval, with eight-way role separation and successful-only replay consumption. The
maximum result is `eligible_for_explicit_one_shot_execution_review`; approval is not an executed
read, real-data-use authorization, embedding approval, persistence approval, or runtime
activation. The implementation performs no actual file open/read or real-material access. See
[the v0.28 design](docs/ONE_SHOT_REAL_DATA_TRIAL_APPROVAL_BOUNDARY_DESIGN_V0.28.md).

v0.27 adds an Explicit One-Shot Real-Data Trial Execution Boundary for controlled synthetic
filesystem targets only. An opaque reference is confined to one capability-bound root; traversal,
absolute/UNC/device paths, symlinks, junctions, reparse points, non-regular files, wrong types, and
oversized targets fail before read. The resolver pins a root directory capability and opens each
relative component with no-follow handle semantics; the adapter never reopens a raw path.
Pre/open/post identity snapshots protect the v0.26
classification and masking chain from TOCTOU changes. A successful verified read alone atomically
exhausts one-shot usage and creates a metadata-only receipt pending explicit closure. The receipt
grants no embedding, persistence, export, or runtime authority. No actual Local RAG material trial
is performed. See [the v0.27 design](docs/ONE_SHOT_REAL_DATA_TRIAL_EXECUTION_DESIGN_V0.27.md).

v0.26 adds a Limited Real-Data Read Execution Boundary. It exact-binds the actual v0.25
authorization, request, selector, policy, operator assignment, access approval, usage contract,
and complete v0.24 source chain before an immutable fixture-backed controlled read. Post-read
classification and masking must pass before a receipt, exhausted authorization, usage update, and
`verified_masked_content_candidate` commit atomically. Failures consume nothing. Automated tests
open no arbitrary file and access no actual real data; embedding, persistence, external network,
production registry, credential, and runtime authority remain denied. See
[the v0.26 design](docs/LIMITED_REAL_DATA_READ_EXECUTION_DESIGN_V0.26.md).

v0.25 adds a Real-Data Access Authorization Boundary. It exact-binds a live v0.24 approved trial
record and its actual source objects to a metadata-only selector, internal-low-only one-shot policy,
independent security and governance reviews, explicit future operator assignment, distinct access
approval, and a test-only atomic authorization record. The maximum readiness state is
`eligible_for_limited_real_data_read_execution`; no file is opened or read, and persistence,
external network, production registry, credential, and runtime counters remain zero. See
[the v0.25 design](docs/REAL_DATA_ACCESS_AUTHORIZATION_BOUNDARY_DESIGN_V0.25.md).

v0.24 adds an Explicit Real-Data Trial Approval Boundary. It exact-binds the complete v0.23
environment/session/execution/readiness chain to a metadata-only scope, safe classification,
stage, retention, logging, cache, export, and persistence policies, independent security and data
governance reviews, a distinct approval, and a test-only atomic record. The maximum result is
`eligible_for_real_data_access_authorization_review`; it does not authorize real-data use or read
any material. All external, storage, credential, runtime, and real-data counters remain zero. See
[the v0.24 design](docs/REAL_DATA_TRIAL_APPROVAL_BOUNDARY_DESIGN_V0.24.md).

v0.23 adds an Approved Local RAG Execution Session / Environment Attestation boundary. Seven
object-backed environment checks gate a short-lived, operator-bound test session; a controlled
adapter then records all eleven v0.22 stages as metadata-only evidence for independent security
review. Independent object-backed pre-execution session review and approval are mandatory before
registry admission and remain distinct from post-execution readiness review. All external,
credential, real-data, persistent-write, registry, and runtime counts remain zero. Review
eligibility does not authorize real-data use. See
[the v0.23 design](docs/LOCAL_RAG_EXECUTION_SESSION_ATTESTATION_DESIGN_V0.23.md).

v0.21 adds an Approved Actual Storage Adapter governance boundary. Object-backed capability
conformance, immutable metadata contracts, independent review/approval, a test-only atomic
registry, and a pure v0.19 compatibility evaluator
stop at `approved_for_write_authorization_review` or `ready_for_write_authorization_review`.
They perform no actual filesystem/DB/object-store operation, production-registry write, or runtime
activation. See [the v0.21 design](docs/APPROVED_STORAGE_ADAPTER_BOUNDARY_DESIGN_V0.21.md).

v0.20 adds a controlled-fixture Real-World Validation Execution Boundary with exact v0.16-v0.19
object-backed source-chain binding. It performs no real-product connection, real persistence,
registry write, or runtime activation. See
[the v0.20 design](docs/REAL_WORLD_VALIDATION_EXECUTION_DESIGN_V0.20.md).

[![Tests](https://github.com/airesearchagl-art/RAGGuard/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/airesearchagl-art/RAGGuard/actions/workflows/test.yml)

## v0.19 real persistence boundary

v0.19 adds immutable persistence authorization, intent, transaction-plan, commit-receipt, and
recovery contracts around an exact v0.18 authorization commit. A test-only atomic durable-store
simulator demonstrates compare-and-swap, monotonic generation, predecessor binding, crash-safe
retry, replay rejection, and corruption detection. It performs no filesystem, database, external
storage, registry, network, HTTP, credential, token, or runtime-activation operation.

See the [v0.19 Design](docs/REAL_PERSISTENCE_BOUNDARY_DESIGN_V0.19.md) and
[v0.19.0 Release Checklist](docs/RELEASE_CHECKLIST_V0.19.0.md).

## v0.18 runtime authorization activation boundary

v0.18 adds immutable runtime-authorization request, independent review, distinct approval, pure
evaluation, and a test-only atomic authorization-commit ledger. It exact-binds the v0.17
equivalence chain, v0.15 persistence receipt/snapshot and activation plan, current registry state,
lifecycle, identity, role, version, and explicit UTC-microsecond time.

The boundary stops at `ready_for_runtime_authorization_commit` or an immutable
`authorization_committed` audit record. Neither state is `active`, enabled, or production-running.
There is no activation API, runtime switch, token/credential generation, production-registry
write, real persistence, transport, HTTP, real-product connection, or real-world validation. See
the [v0.18 Design](docs/RUNTIME_AUTHORIZATION_ACTIVATION_DESIGN_V0.18.md) and
[v0.18.0 Release Checklist](docs/RELEASE_CHECKLIST_V0.18.0.md).

## v0.17 production-equivalent evidence boundary

v0.17 adds immutable production-equivalence assessment, criteria, metadata-only evidence,
environment/configuration/behavior, independent review, and approval contracts. The pure evaluator
exact-binds the complete v0.16 plan/execution/evidence/review/approval chain and deterministically
reports the first missing equivalence boundary. Synthetic or controlled manual evidence cannot be
promoted by an enum or approval claim.

The complete chain can reach only `eligible_for_equivalence_review`, followed by a distinct review
and approval attestation. Equivalence approval is not production approval, runtime authorization,
activation, registry admission, or persistence. The implementation performs no real-product
validation or connection and handles no real endpoint, document, credential, or token. See the
[v0.17 Production-Equivalent Evidence Design](docs/PRODUCTION_EQUIVALENT_EVIDENCE_DESIGN_V0.17.md)
and [v0.17.0 Release Checklist](docs/RELEASE_CHECKLIST_V0.17.0.md).

## v0.16 manual-validation execution boundary

v0.16 adds immutable execution-request, safe-fixture manifest, offline-environment, execution
record, evidence, independent review, and approval contracts. A deterministic test-only harness
requires the exact Phase A plan, fixture case set, and environment digests, and commits a passed
execution record only after complete validation. Missing, failed, or skipped required cases never
produce a passed record. Failed attempts and commit faults consume no replay identity.

The chain is `plan -> request -> execution -> evidence -> review -> approval`. Each edge uses the
canonical digest, explicit UTC microsecond timestamps, and distinct requester, operator, evidence
creator, reviewer, and approver identities. v0.14 accepts an approved manual-validation state only
when the four v0.16 execution/evidence/review/approval digests are present in its canonical
boundary evidence. An approved chain is not production-equivalent evidence and does not activate
runtime use.

The harness is synthetic/controlled, deterministic, offline, and communication-free. It performs
no real-product connection, production-registry write, filesystem/DB persistence, external API,
credential handling, transport/HTTP change, or runtime activation. See the
[v0.16 Manual Validation Execution Design](docs/MANUAL_VALIDATION_EXECUTION_DESIGN_V0.16.md) and
[v0.16.0 Release Checklist](docs/RELEASE_CHECKLIST_V0.16.0.md).

## v0.14 production authorization boundary

v0.14 adds immutable production-boundary evidence and a pure, fail-closed authorization-candidate
evaluator. It binds an exact active admission/replacement entry and registry snapshot to explicit
manual-validation, compatibility, security-review, persistence, and runtime-boundary states.
Synthetic-only evidence stops at `needs_manual_validation`; even complete typed fixtures stop at
`eligible_for_authorization_review`.

This is not production activation. There is no activation API, token, credential, runtime switch,
production-registry write, persistence, transport, HTTP, real-product connection, production
profile, or performed manual validation. See the
[v0.14 Production Boundary Design](docs/PRODUCTION_BOUNDARY_DESIGN_V0.14.md) and
[v0.14.0 Release Checklist](docs/RELEASE_CHECKLIST_V0.14.0.md).

## v0.15 persistence and activation-commit boundary

v0.15 adds immutable persistence-policy and persisted-authorization contracts, a test-only atomic
in-memory store, and a pure activation-request evaluator. The exact v0.14 candidate, boundary
evidence, registry entry/state, lifecycle, replacement chain, persistence generation, roles, and
timestamps remain digest-bound and fail closed.

`ready_for_activation_commit` is only a commit-plan contract. It is not active, activated,
production-enabled, or runtime-authorized. The repository still has no filesystem/DB persistence,
production-registry write, runtime activation API, token/credential generation, transport, HTTP,
manual-validation execution, or real-product connection. See the
[v0.15 Persistence / Activation Design](docs/PERSISTENCE_ACTIVATION_DESIGN_V0.15.md) and
[v0.15.0 Release Checklist](docs/RELEASE_CHECKLIST_V0.15.0.md).

## RAG Benchmark Harness v0.12 registry lifecycle governance

v0.12 adds fail-closed post-admission revalidation and one-way lifecycle governance for entries
that already exist in the test-only registry contract. Immutable trigger, requirement, request,
event, and result contracts bind exact profile/product/protocol identity, the current entry digest,
the admission-decision/evidence chain, explicit microsecond-precision time, restrictions, status,
and a lifecycle administrator distinct from the validation operator, evidence reviewer, and
approver.

Allowed transitions are `active -> suspended|deprecated|revoked`,
`suspended -> deprecated|revoked`, and `deprecated -> revoked`. `revoked` is terminal. Same-status
writes, fallback, nearest-version selection, schema inference, implicit transitions, automatic
rollback, recovery, or reactivation are rejected before mutation. A denied transition leaves
lifecycle mutation, event, write, transport, and HTTP counts at zero.

Revalidation required is not approval, suspension is not revocation, and successful revalidation
does not restore `active`. A replacement requires fresh evidence, a new review, approval,
admission decision, and registry admission. The implementation mutates only an in-memory test-only
store and adds no production registry write, persistence, runtime authorization, product
connection, credential, real document, external/private-LAN access, transport, HTTP, workflow, or
Node runtime maintenance. See the
[v0.12 Registry Lifecycle Design](docs/REGISTRY_LIFECYCLE_DESIGN_V0.12.md) and
[v0.12.0 Release Checklist](docs/RELEASE_CHECKLIST_V0.12.0.md).

## RAG Benchmark Harness v0.11.0 production admission

v0.11.0 adds immutable manual-validation plan and evidence contracts, exact plan/evidence binding,
structural and temporal evidence validity, a pure production-admission evaluator, offline
`inline_safe_fixture` import, and atomic admission to an explicitly test-only registry. Reviewer,
approver, validation-operator, and registry-administrator responsibilities remain distinct, and
review must precede approval strictly.

Admission is deterministic and fail-closed. Phase C binds exact profile, protocol, product,
version, reviewer, operator, evidence, and approval identities into its canonical digest chain.
Phase E compares those decision-bound identities exactly, treats safe summaries only as checked
advisory output, and leaves entry, write, event, transport, and HTTP counts at zero on denial.
Resolution never performs fallback, nearest-version selection, schema inference, automatic
approval, recovery, or rollback.

This is a synthetic-safe-fixture release boundary. No manual validation was performed, no
production profile or real production-registry entry exists, and no registry persistence or
runtime production authorization is provided. It includes no real-product compatibility evidence,
credentials, real documents, external/private-LAN access, or Phase D/E filesystem, network, or
subprocess path. Synthetic fixtures are not evidence of real-product compatibility, and test-only
registry admission is not runtime production authorization.

The public CLI remains `check-mask` and `benchmark`; exit codes `0` / `1` / `2` / `3`, report
top-level schemas, the v0.9 Compatibility Profile path, v0.10 approval enforcement, and existing
synthetic/in-memory/loopback paths remain compatible. See [Usage](docs/USAGE.md),
[Design Notes](docs/DESIGN_NOTES.md), the
[v0.11 Production Admission Design](docs/PRODUCTION_ADMISSION_DESIGN_V0.11.md), and the
[v0.11.0 Release Checklist](docs/RELEASE_CHECKLIST_V0.11.0.md).

## RAG Benchmark Harness v0.10.0 approval governance

v0.10.0 is prepared as a synthetic-only governance release. Phases A-E implement immutable profile
maturity and approval metadata, validation reports and decisions, an explicit test/production
registry contract, a deterministic synthetic approval workflow, and approval enforcement before
transport creation. Phase F documents those boundaries and prepares the release gate; no tag or
GitHub Release exists until separate post-merge operations complete.

The runtime is fail-closed. Profiles and versions resolve exactly, restrictions are enforced before
retrieval, and unapproved, expired, revalidation-required, suspended, deprecated, revoked, or
incompatible entries are rejected. There is no automatic fallback, nearest-version selection,
schema inference, implicit capability downgrade, or silent top-k reduction.

This release provides no production Compatibility Profile, real production-registry entry,
registry persistence, production approval CLI/config, manual validation result, real-product
connection, credential support, real document, or external/private-LAN access. Synthetic
validation is not evidence of real-product compatibility. Any future manual validation or
production admission requires a separate explicitly approved task and evidence review.

Document responsibilities:

- [Usage](docs/USAGE.md) describes the supported operational surface and safety limits.
- [Design Notes](docs/DESIGN_NOTES.md) define the Phase A-E contracts and lifecycle rationale.
- [v0.10.0 Release Checklist](docs/RELEASE_CHECKLIST_V0.10.0.md) defines the merge, tag, Release,
  and post-release gates.
- [Roadmap](ROADMAP.md) records delivery status and separately approved future work.

## RAG Benchmark Harness v0.9 compatibility contract

v0.8 completed the bounded loopback HTTP transport and synthetic security verification. v0.9
designs a product-neutral compatibility layer before any real Local RAG product is contacted.
Product-specific health, capability, request, and response differences are isolated in an explicit
Compatibility Profile instead of being mixed into the transport, adapter, evaluator, or report
contracts.

Profiles use safe identifiers and explicit versions. Unknown profiles, unknown major versions,
missing required capabilities, unsafe source identifiers, ambiguous score semantics, and invalid
field mappings fail closed as CLI error `3`. There is no best-effort profile selection or response
schema inference. Existing request limits, ranked-result validation, report top-level keys, and
PASS `0` / WARNING `1` / FAIL `2` / CLI error `3` remain unchanged.

Phase A implements a communication-free compatibility contract: strict three-component profile and
protocol versions, safe profile identifiers and relative HTTP paths, typed request/response field
mappings, allowlisted score semantics and source policy, explicit optional feature flags, and exact
profile selection. Unknown major versions and unallowlisted minor versions fail closed. Prerelease
and build version forms are not accepted, and no mapping is executed in this phase.

Phase B adds immutable product-neutral health and capabilities contracts. Health requires a valid
schema, compatible protocol version, `healthy` status, and explicit service availability before
capability negotiation. All five required retrieval capabilities must be true. Optional features
are enabled only when explicitly requested by the profile or caller and affirmed by the response;
they are never silently downgraded. The result retains only a safe profile ID, protocol/health
status, required-capability outcome, and enabled optional capability names.

Phase C adds internal, communication-free request and response mapping execution. Standard requests
are typed and bounded before explicit flat profile mappings produce a 64 KiB-limited payload.
Product responses retain only explicitly mapped fields, revalidate safe identifiers, rank order,
duplicates, top-k, metadata, and declared score semantics, then normalize to the existing
`RankedResult` boundary. Negotiated optional fields fail closed when required and are ignored when
not negotiated. Safe summaries contain only counts, score semantics, and enabled optional fields.

Phase D adds a deterministic no-I/O synthetic compatibility harness. It executes the Phase A-C
production contracts in order: profile/version resolution, health validation, capability
negotiation, request mapping, synthetic response mapping, and `RankedResult` normalization. The
immutable result retains only safe compatibility status, mapping/result counts, score semantics,
enabled optional capabilities, and normalized ranked results. Raw mappings, query text, routes,
credentials, endpoints, product identity, and internal exception details are not retained or
rendered.

Phase E integrates an explicit `compatibility_profile` selection with `loopback_http`. The CLI now
resolves the trusted synthetic profile, validates bounded health and capabilities responses, applies
the Phase C request/response mappings, and passes only normalized `RankedResult` values to the
evaluator. JSON/YAML config, PASS/WARNING/FAIL, compatibility error `3`, lifecycle ordering, and
non-disclosure are verified against an ephemeral fake loopback server.

This integration remains synthetic-only. There is one product-neutral built-in test profile, no
profile discovery or fallback, and no real product schema, endpoint, credential, or document. A real
product connection is not part of v0.9 delivery; it requires a separately approved manual session
using a loopback endpoint, synthetic queries, no credentials, no real documents, no fallback
connection, and safe summary output only.

Phase F completes the v0.9 documentation, changelog, release checklist, and explicit Python
3.11/3.12 CI coverage for compatibility profile integration E2E. The verified order is explicit
profile/version selection, health validation, capability negotiation, request mapping, bounded
retrieval, response mapping, ranked-result normalization, evaluation, report generation, and close.
Both successful and failed synthetic fake-loopback paths close safely.

No production profile or product configuration is provided. Real Local RAG product compatibility
remains unverified, and automatic profile fallback, nearest-version selection, and response-schema
inference remain unsupported.

### v0.9.0 release checklist

- Full pytest, compatibility contract/mapping/harness, profile integration E2E, HTTP security E2E,
  and local-rag E2E suites pass.
- Synthetic default returns `0`; profile integration covers PASS `0`, WARNING `1`, FAIL `2`, and
  CLI error `3`.
- `check-mask --help` and `benchmark --help` succeed.
- Workflow YAML, `git diff --check`, bidi controls, CR-only endings, and fixture markers pass.
- GitHub Actions succeeds on Python 3.11 and 3.12 from a clean synchronized `main`.
- Tag and GitHub Release creation remain separate post-merge operations.

## RAG Benchmark Harness v0.8 secure loopback transport

v0.8 designs a real Local RAG transport boundary before any production communication is implemented.
Phase A codes the endpoint, caller-supplied resolution proof, JSON request/response, size, and safe
error contracts without performing DNS lookup or I/O. Phase B verifies those contracts against a
test-only fake loopback server with fixed synthetic responses. The first production transport
candidate is loopback HTTP. Phase C adds a bounded one-request HTTP client that resolves immediately
before connecting, connects to a verified loopback IP literal, validates the actual peer, performs
one bounded POST, and always closes the connection.
Unix domain sockets and Windows named pipes remain future candidates. External hosts, private LAN
targets, wildcard addresses, redirects, proxies, filesystem retrieval, and credential loading are
excluded.

The HTTP contract permits only validated loopback destinations (`127.0.0.1`, `::1`, or an explicit
allowlist whose resolved addresses are all loopback). It requires fixed JSON content types, bounded
requests and responses, connect/read/total timeouts, no automatic retry, no connection pooling, and
a short-lived one-shot lifecycle with close after success or failure. Reports and logs retain only
adapter name, bounded duration, result count, status, and safe error category.

The Phase C client does not follow redirects, consult proxy configuration, retry, pool connections,
or permit non-loopback peers. Phase D integrates it with the existing explicit `local-rag` selector
and bounded JSON/YAML config loader through the `loopback_http` transport type. Synthetic retrieval
remains the default, and the existing no-I/O `in_memory` behavior is unchanged.

`loopback_http` is enabled only by explicit configuration. It accepts an HTTP loopback endpoint,
connect/read/total timeouts, response-size and top-k limits, capability flags, and an optional
hostname allowlist. Unknown fields and authentication, token, cookie, proxy, redirect, retry, or
credential fields are rejected. Verification uses only ephemeral synthetic loopback servers; no
real Local RAG product, real document, filesystem retrieval, or external/private-LAN connection is
used.

Phase E fixes the complete synthetic-only HTTP path from CLI and safe JSON/YAML config loading
through the local adapter, bounded loopback client, evaluator, reports, and exit codes. Security E2E
coverage rejects unsafe config, endpoints, peer/resolution outcomes, timeouts, redirects, malformed
or oversized responses, and sensitive-value disclosure while requiring one attempt and close after
success or failure. This remains fake-server verification only; real Local RAG products and real
documents are not connected.

Phase F completes the v0.8 documentation, explicit Python 3.11/3.12 CI gate for the HTTP security
E2E suite, changelog, and release checklist. The operational boundary remains unchanged:
`loopback_http` is enabled only by explicit local-rag config, Synthetic remains the default, and
`in_memory` remains compatible. Redirects, proxies, retries, credentials, external/private-LAN
destinations, and filesystem retrieval remain unsupported. A real Local RAG product has not been
connected or compatibility-tested.

```json
{
  "transport_type": "loopback_http",
  "endpoint": "http://127.0.0.1:8765/retrieve",
  "connect_timeout": 1.0,
  "read_timeout": 2.0,
  "total_timeout": 3.0,
  "default_top_k": 5,
  "response_size_limit": 262144,
  "capabilities": {
    "ranked_results": true,
    "matched_keywords": true,
    "filters": false
  }
}
```

Before a v0.8.0 tag or Release is created, the release checklist requires the complete pytest suite,
HTTP security E2E, local-rag in-memory E2E, Synthetic default exit `0`, loopback HTTP evaluation and
CLI-error exits `0` / `1` / `2` / `3`, both CLI help commands, diff/Unicode/line-ending/fixture
scans, Python 3.11/3.12 Actions success, and a clean synchronized `main`.

## RAG Benchmark Harness v0.7 local connection contract

v0.7 Phase A implements the internal contract for a future local-only connection without enabling
Local RAG access. It adds a validated `LocalRetrievalConfig`, bounded request and response models,
a runtime-checkable `LocalRetrievalTransport` Protocol, and a safe normalization boundary to the
existing `RankedResult` model. Phase B adds a deterministic `InMemoryLocalRetrievalTransport` for
contract tests only. Phase C integrates that transport with the internal
`LocalRAGRetrievalAdapter` client skeleton. Phase D adds an explicit CLI selector and bounded local
configuration loading. Phase E fixes the complete synthetic local-rag path in end-to-end tests.
Phase F completes the documentation, explicit CI coverage, and v0.7.0 release preparation.

Only `in_memory` is allowlisted at this phase. Timeout, top-k, response size, capability flags,
safe identifiers, metadata keys, and response ordering are validated without retaining or reporting
rejected values in errors. The local adapter does not retain config or transport objects, and
reports receive normalized safe fields only. Only JSON or YAML configuration and the no-I/O
`in_memory` transport are supported. Filesystem retrieval, localhost communication, network access,
and credential loading remain excluded.

The in-memory transport performs no I/O. It uses fixed synthetic responses, enforces explicit
`created`, `initialized`, and `closed` states, supports bounded error injection, and passes responses
through the Phase A validation and normalization boundary. It is selectable only through explicit
`--adapter local-rag --adapter-config <json-or-yaml>` arguments and does not make a real Local RAG
connection operational.

The Phase C local adapter is an internal one-shot client. It runs initialize, health, capability,
retrieve, and close in order; closes after success or failure; then releases config and transport
references. Only the in-memory transport is accepted. Raw transport failures are mapped to bounded
retrieval errors before benchmark and CLI error handling.

Synthetic retrieval remains the default. The Phase D `local-rag` path is a deterministic in-memory
integration path only. It must be selected explicitly, uses a fresh one-shot adapter per query, and
keeps query text, credentials, configuration values, real paths, long content, and stack traces out
of reports and operational logs.

Phase E covers JSON and YAML config loading, PASS / WARNING / FAIL / CLI error outcomes,
deterministic ranked results, adapter lifecycle cleanup, safe report output, invalid and oversized
responses, and Synthetic-default regression. Reports identify only the safe adapter name in existing
metadata and Markdown Inputs; they do not include config paths, timeout or response-size values,
credentials, raw responses, or long corpus content. The effective top-k remains visible as existing
benchmark evaluation metadata.

v0.7 Phase A-F now provides:

- validated `LocalRetrievalConfig` and `LocalRetrievalTransport` contracts
- deterministic `InMemoryLocalRetrievalTransport` with no filesystem or network I/O
- one-shot `LocalRAGRetrievalAdapter` lifecycle integration with guaranteed cleanup
- `--adapter synthetic|local-rag` and bounded `--adapter-config` JSON / YAML loading
- safe JSON / YAML parsing, validation, and error mapping to CLI error `3`
- synthetic end-to-end coverage for PASS `0`, WARNING `1`, FAIL `2`, and CLI error `3`
- explicit CI coverage for both the Synthetic default and local-rag in-memory path

The `local-rag` selector is synthetic-only and limited to `in_memory`. It is not a production Local
RAG connector and performs no filesystem retrieval, localhost access, or network communication.
Config values, credentials, real paths, raw responses, and long content are not reported.

```powershell
python -m ragguard benchmark --corpus tests/fixtures/benchmark/corpus --queries tests/fixtures/benchmark/queries.jsonl --output outputs/local-benchmark --adapter local-rag --adapter-config local-rag.json
```

### v0.7.0 release checklist

- Python 3.11 and 3.12 test jobs pass.
- Synthetic benchmark default execution returns PASS `0`.
- Local-rag JSON and YAML synthetic E2E cases pass.
- PASS `0`, WARNING `1`, FAIL `2`, and CLI error `3` remain stable.
- Unsafe YAML, oversized config, invalid response, lifecycle, and close boundaries pass.
- Reports expose only the safe `retrieval_adapter` identifier and existing bounded fields.
- Real Local RAG transports, filesystem retrieval, localhost/network communication, Hermes,
  LM Studio, embeddings, vector databases, LLM evaluation, external APIs, cloud, and external MCP
  remain unimplemented.

## RAG Benchmark Harness v0.6 retrieval adapter boundary

Phase A added a shared retrieval adapter contract, ranked-result model, and result validation so
synthetic retrieval and a future local-only implementation can share one narrow interface. It does not add a Local RAG connection,
Hermes or LM Studio connection, embedding generation, vector database access, LLM evaluation,
external APIs, cloud services, or real-document input.

The planned adapter contract accepts a query and `top_k`, then returns deterministic ranked results.
Each result carries `rank`, `document_id`, `score`, `matched_keywords`, `title`, and `source_path`;
adapter-specific details are optional `adapter_metadata`. Long content is never passed to reports.

Benchmark evaluation remains separate from retrieval. The evaluator owns hit@k, expected source
match, keyword coverage, no-result, unsafe-or-unknown, report generation, and benchmark exit-code
decisions. Adapter scores are retrieval-local signals and are not treated as a cross-adapter quality
metric.

Invalid adapter output is validated before evaluation and converted to the existing benchmark CLI
error path. The synthetic adapter keeps its deterministic ordering, report shape, and existing
direct-call behavior.

Phase B moves the deterministic Synthetic adapter and its retrieval-only helpers behind the shared
interface. The benchmark module now invokes retrieval through one validated adapter boundary and
retains only evaluation and report serialization responsibilities.

Phase C adds a deterministic test-only mock adapter and contract coverage for empty and ranked
results, optional metadata, stable ordering, invalid fields, duplicate documents, top-k limits,
adapter exceptions, and the CLI error boundary. Runtime behavior and report shapes remain unchanged.

Phase D adds an unconnected `LocalRAGRetrievalAdapter` skeleton. It records only whether constructor
configuration was supplied, does not read or retain configuration values, and performs no file,
environment, localhost, or network access. Retrieval fails through bounded `not configured` or
`dependency is unavailable` errors and the existing benchmark CLI error `3` boundary.

v0.6 Phase A-E now provides:

- a runtime-checkable `RetrievalAdapter` Protocol
- a validated `RankedResult` model with deterministic ordering requirements
- the existing Synthetic adapter behind the common contract
- mock adapter contract and error-boundary tests
- a skeleton-only, not operational `LocalRAGRetrievalAdapter`
- Python 3.11 / 3.12 CI checks for synthetic benchmark success, benchmark exit codes, and the local
  skeleton CLI error `3` boundary

Only the Synthetic adapter is operational. There is no local-rag CLI selector. The local skeleton
does not access filesystems, localhost, networks, configuration values, paths, or credentials.

## RAG Benchmark Harness v0.5 Phase D synthetic retrieval scoring

v0.5 adds synthetic-only retrieval and local benchmark scoring for the benchmark harness.
It remains local and detached from production Local RAG, Hermes, LM Studio, vector databases,
embedding services, LLM evaluation, cloud services, and external APIs.

Phase A-D scope:

- retrieval adapter boundary for corpus loading, query input, and ranked result output
- deterministic keyword / token overlap search using the Python standard library
- ranked results with `rank`, `document_id`, `score`, `matched_keywords`, `title`, and `source_path`
- ranked results included in benchmark JSON and Markdown reports
- hit@k evaluation with default top-k `5`
- expected source match evaluation against the top-k ranked results
- expected keyword coverage evaluation
- no-result expected evaluation
- unsafe-or-unknown expected evaluation without LLM judgment
- summary metrics for evaluated query count, hit@k, source match, keyword coverage, no-result, and unsafe-or-unknown expectations
- stable JSON and Markdown report fields for the v0.5 benchmark metrics
- CI checks for benchmark PASS / WARNING / FAIL / CLI error exit codes
- no long corpus content replay in JSON or Markdown reports

v0.5 marks synthetic benchmark queries as `pass`, `warning`, or `fail` from local deterministic
retrieval only, and maps the overall benchmark result to PASS `0`, WARNING `1`, FAIL `2`, or
CLI error `3`. No LLM answer judgment or production RAG behavior is evaluated.

Current v0.5 limitations:

- no production Local RAG connection
- no Hermes or LM Studio connection
- no embedding or vector database retrieval
- no LLM-as-a-judge evaluation
- no external API or cloud service integration

The existing `check-mask` behavior, exit codes, and report structures are not part of this v0.5 design change.

## Masked Document Checker v0.3

現時点のRAGGuardは、RAG投入前のマスク済みMarkdownをローカルで確認する `check-mask` CLIを提供します。

- `--config config/rules.yaml` によるローカルYAMLルール追加
- 金額 / 料率 / 坪単価 / 平米単価らしき表現の検出
- 郵便番号、所在地、住所候補らしき表現の検出
- 契約条件 / 内部情報キーワードの検出
- 同一file / line / rule_id / 伏せ字後matched_textの重複finding抑制
- Markdownレポート上部のsummary表示
- JSON / Markdownレポート出力
- `matched_text` の伏せ字化

## RAG Benchmark Harness v0.4

v0.4では、Local RAG本線を直接操作せず、RAG品質を外部から検証する補助ツールとしてRAG Benchmark Harnessを設計します。初期版は実資料を使わず、synthetic corpusとsynthetic query setだけを対象にします。

想定CLI:

```powershell
python -m ragguard benchmark --corpus "path\to\synthetic_corpus" --queries "queries.jsonl" --output "outputs\benchmark"
```

v0.4設計では、外部API、クラウドサービス、LLM評価は使わず、expected source / expected keyword / expected answer hintに基づくローカル評価を優先します。

Phase Aでは、`tests/fixtures/benchmark/corpus/` と `tests/fixtures/benchmark/queries.jsonl` を将来の配置案とし、架空Markdown文書とJSON Lines query setの形式を設計します。この段階ではfixtureファイルは追加しません。

Phase Bでは、`benchmark` CLI skeletonを追加します。synthetic corpusとqueries JSONLの読み込み、必須項目validation、placeholder JSON / Markdown report生成だけを行い、実RAG接続、検索評価、LLM評価、外部API利用は行いません。

```powershell
python -m ragguard benchmark --corpus "tests/fixtures/benchmark/corpus" --queries "tests/fixtures/benchmark/queries.jsonl" --output "outputs/test_benchmark_cli"
```

Phase Cでは、`benchmark_report.json` と `benchmark_report.md` の構造を拡充します。queryごとの `per_query_results`、`warnings`、`errors`、`metadata` を出力しますが、検索・評価はまだ行わず、`evaluation_status` は `not_evaluated` として扱います。

Phase Dでは、GitHub Actions `Tests` workflowでbenchmark CLIも確認します。`python -m ragguard benchmark --help` とsynthetic fixtureを使ったreport生成をCIで実行し、pytest、`check-mask`、`benchmark` の最小動作を同じPRゲートで確認します。

v0.4時点でできること:

- `benchmark` CLIでsynthetic corpus / queries JSONLを読み込む
- corpusとqueryの必須項目をvalidationする
- valid inputでplaceholder JSON / Markdown reportを生成する
- queryごとの `per_query_results` を `not_evaluated` として出力する
- GitHub Actionsでbenchmark CLI helpとsynthetic fixture実行を確認する
- 実RAG接続、検索評価、LLM評価、外部API利用はまだ行わない

RAGGuardは、RAG投入前のマスク済みMarkdown資料に、個人情報・金額情報・契約情報・内部事情が残っていないかをローカルで確認するためのPython CLIです。

初回MVPの対象は **Masked Document Checker** のみです。GUI、Dashboard、Citation Verifier、RAG Benchmark Harnessは今回の範囲外です。

## インストール

```powershell
python -m pip install -e .
```

実行時の外部依存は、ローカルYAML設定読込に使う `PyYAML` のみです。外部APIやクラウドサービスは使いません。

Windowsでは、editable install後に `ragguard` コマンドが配置されるPython `Scripts` ディレクトリが `PATH` に入っていない場合があります。その場合は `python -m ragguard ...` で実行するか、利用しているPython環境の `Scripts` ディレクトリを `PATH` に追加してください。

## CLI実行例

```powershell
python -m ragguard check-mask --input "tests/fixtures/safe" --output "outputs/test_safe"
ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail" --verbose
```

`ragguard` コマンドが見つからない場合は、同じ処理を以下の形式で実行できます。

```powershell
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail" --verbose
```

YAML設定を追加で読み込む場合は、`--config` を指定します。

```powershell
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail_config" --config "config/rules.yaml"
```

`--config` 未指定時は内蔵ルールのみを使います。`--config` 指定時は `mode: extend_builtin` のみ対応し、内蔵ルールにYAML定義ルールを追加します。YAML不備、未対応mode、重複 `rule_id`、不正な正規表現などはCLIエラーとして終了コード `3` になります。

運用確認では、内蔵ルールのみの実行と `--config` 付き実行を分けて確認できます。

```powershell
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail_builtin"
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail_config" --config "config/rules.yaml"
```

どちらもFAIL検出時の終了コードは `2` です。configファイルには実資料、実案件名、実会社名、実個人名を入れないでください。

## CI

GitHub Actionsの `Tests` workflowで、`main` へのpushおよび `main` 向けpull requestごとに `python -m pytest` と `--config config/rules.yaml` 付きCLI実行を確認します。検出ルールやドキュメントを変更する場合も、PRではpytestとconfig付きCLI確認が通る状態を維持してください。

Benchmark Harnessについても、CIで以下を確認します。

```powershell
python -m ragguard benchmark --help
python -m ragguard benchmark --corpus tests/fixtures/benchmark/corpus --queries tests/fixtures/benchmark/queries.jsonl --output outputs/ci_benchmark_report
```

The same workflow also checks benchmark exit code behavior for PASS `0`, WARNING `1`, FAIL `2`,
and CLI error `3` cases with synthetic query files.

## 判定

- PASS: 機微情報らしき検出なし
- WARNING: 文脈確認が必要な語句のみ検出
- FAIL: メール、電話、住所らしき表現、金額、料率、契約条件、内部事情などを検出

終了コード:

- PASS: `0`
- WARNING: `1`
- FAIL: `2`
- CLIエラー: `3`

## 出力ファイル

指定した出力フォルダに以下を生成します。

- `masked_check_report.json`
- `masked_check_report.md`

`matched_text` は安全のためマスクされます。メールアドレス、電話番号、金額、住所、契約条件の具体文を長く再掲しない設計です。

## 注意

- 実資料をテストデータに使わないでください。
- `C:\AI_Restricted` を読ませないでください。
- `C:\AI_Local_RAG` 配下の実資料をMVPテスト対象にしないでください。
- 外部API、クラウドサービス、外部MCPは使わない方針です。
- config YAMLもローカルファイルとして扱い、実資料・実案件名・実会社名・実個人名を含めないでください。
- 入力ファイルは変更しません。自動修正も行いません。

## v0.13 Replacement Admission Chain

v0.13 adds immutable replacement-admission contracts and a test-only atomic registry harness.
Replacement is not reactivation: a suspended or deprecated predecessor stays inactive and a new
active successor requires a fresh evidence, review, approval, and admission chain. Revoked remains
terminal. This does not provide production persistence or runtime production authorization. See
`docs/REPLACEMENT_ADMISSION_DESIGN_V0.13.md`.
