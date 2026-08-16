# RAGGuard Roadmap

## Delivery candidate: v0.30 actual one-shot execution bridge and trial gate

- Exact object-backed execution binding to the complete v0.29 preparation packet.
- Separate expiring Human approval exact-bound to the packet and assigned operator.
- One Human-selected target under an opaque, no-scan, handle-backed root capability.
- Raw-derived local classification and masking followed by digest-only chunking evidence.
- Process-local atomic success commit; post-read failure spends approval but not usage.
- PR validation uses only controlled synthetic roots; actual trial is a separate post-merge gate.
- v0.30.0 tag and Release remain blocked until the Human-approved actual trial passes.

Authoritative design: [v0.30 Actual One-Shot Execution Bridge](docs/ACTUAL_ONE_SHOT_EXECUTION_DESIGN_V0.30.md).

## Delivery candidate: v0.29 one-shot real-data trial execution preparation

- One immutable metadata-only packet over the exact v0.25-v0.28 source objects.
- Dry-run revalidation of authorization, root, target, operator, purpose, expiry, and closure.
- Internal-low, one-document, one-read, chunking ceiling, and deny-by-default policy gates.
- Lightweight test-only successful-only packet/request replay protection.
- Safe review summary and mandatory stop at explicit human execution approval.
- No actual file open/read, real-data access, production write, external service, or activation.

Authoritative design: [v0.29 One-Shot Real-Data Trial Execution Preparation](docs/ONE_SHOT_REAL_DATA_TRIAL_PREPARATION_V0.29.md).

## Delivery candidate: v0.28 explicit one-shot trial approval and root provisioning

- Opaque root identity and five object-backed confinement/link/permission/write/network checks.
- Exact live v0.25 authorization/usage plus v0.27 root-policy/target object binding.
- Internal-low-only, one-document, one-read, chunking-candidate ceiling and explicit closure.
- Independent security/governance reviews and distinct execution approval with eight roles.
- Test-only atomic approval registry with generation, predecessor, lifecycle, and replay gates.
- Execution-review eligibility without an actual file open/read or real-material access.

Authoritative design: [v0.28 Explicit One-Shot Real-Data Trial Approval Boundary](docs/ONE_SHOT_REAL_DATA_TRIAL_APPROVAL_DESIGN_V0.28.md).

## Delivery candidate: v0.27 explicit one-shot real-data trial execution boundary

- Digest-only root descriptor, fail-closed resolver policy, and opaque target reference.
- Controlled-root confinement with traversal, absolute path, link/reparse, type, and size denial.
- Pre-open, opened-target, and post-read identity snapshots with TOCTOU fail-closed behavior.
- Exact reuse of v0.26 classification/masking and successful-only one-to-zero usage consumption.
- Atomic receipt/exhaustion/usage/replay/pending-closure commit and explicit completed closure.
- Controlled synthetic filesystem fixtures only; the actual Local RAG material trial is separate.

Authoritative design: [v0.27 Explicit One-Shot Real-Data Trial Execution Boundary](docs/ONE_SHOT_REAL_DATA_TRIAL_EXECUTION_DESIGN_V0.27.md).

## Delivery candidate: v0.26 limited real-data read execution boundary

- Exact v0.25 authorization, selector, policy, operator, approval, usage, and v0.24 source binding.
- Hard pre-read verification followed by an immutable fixture-backed controlled read only.
- Post-read classification and masking verification with metadata-only receipt evidence.
- Successful-only one-shot usage consumption and atomic test-ledger replay protection.
- Downstream stop at `verified_masked_content_candidate`; no embedding or persistence authority.
- A protocol-only future explicit trial hook; the actual one-shot real-data trial remains separate.

Authoritative design: [v0.26 Limited Real-Data Read Execution Boundary](docs/LIMITED_REAL_DATA_READ_EXECUTION_DESIGN_V0.26.md).

## Delivery candidate: v0.25 real-data access authorization boundary

- Metadata-only selector exact-bound to an actual, live v0.24 approved-trial object chain.
- Internal-low-only, one-document, one-read policy capped at the chunking candidate stage.
- Independent security and governance reviews, explicit future operator assignment, and distinct
  access approval with full role separation.
- Atomic test-only authorization registry with generation, predecessor, successful-only replay,
  one-way lifecycle, and immutable usage-count contracts.
- Limited-read execution eligibility without an actual file open/read, persistence authority, or
  runtime activation.

Authoritative design: [v0.25 Real-Data Access Authorization Boundary](docs/REAL_DATA_ACCESS_AUTHORIZATION_BOUNDARY_DESIGN_V0.25.md).

## Delivery candidate: v0.24 explicit real-data trial approval boundary

- Metadata-only trial scope and safe classification/stage/retention/log/cache/export/persistence
  policies exact-bound to the actual v0.23 environment, session, execution, and readiness objects.
- Independent security review, independent data-governance review, and distinct trial approval.
- Atomic test-only registry with generation, predecessor, successful-only replay consumption,
  retry, expiry, revocation, and supersession protection.
- Access-authorization review eligibility without actual real-data access authorization or read.
- Zero external network, credential, real-data, storage, registry, and runtime effects.

Authoritative design: [v0.24 Explicit Real-Data Trial Approval Boundary](docs/REAL_DATA_TRIAL_APPROVAL_BOUNDARY_DESIGN_V0.24.md).

## Delivery candidate: v0.23 approved Local RAG execution session attestation

- Seven object-backed environment hard gates with independent verifier, reviewer, and approver.
- Exact v0.22 chain-bound, independently pre-reviewed/pre-approved short-lived operator session.
- Successful-only request/review/approval/session replay consumption and lifecycle protection.
- Eleven-stage metadata-only controlled execution and independent security review.
- Explicit real-data trial approval review eligibility without real-data authorization.
- Zero external network, credential, real-data, persistent-write, registry, and runtime effects.

Authoritative design: [v0.23 Local RAG Execution Session Attestation](docs/LOCAL_RAG_EXECUTION_SESSION_ATTESTATION_DESIGN_V0.23.md).

## Delivery candidate: v0.21 approved actual storage adapter boundary

- Metadata-only adapter manifest, object-backed capability conformance suite, evidence, review,
  approval, and policy contracts.
- Eight-role separation, explicit time, successful-only replay consumption, and one-way lifecycle.
- Test-only atomic approved-adapter registry and pure v0.19 object-backed compatibility review.
- Actual storage execution, write authorization, production-registry mutation, and runtime
  activation remain separate future design-and-approval tasks.

Authoritative design: [v0.21 Approved Storage Adapter Boundary](docs/APPROVED_STORAGE_ADAPTER_BOUNDARY_DESIGN_V0.21.md).

## Delivery candidate: v0.20 controlled real-world validation boundary

- Controlled fixture authorization, execution, evidence, review, approval, and atomic ledger.
- Exact v0.16-v0.19 source-chain binding and successful-only replay consumption.
- Real production validation, runtime activation, real persistence, and registry writes remain
  separate future design-and-approval tasks.

Authoritative design: [v0.20 Real-World Validation Execution Boundary](docs/REAL_WORLD_VALIDATION_EXECUTION_DESIGN_V0.20.md).

## Delivery candidate: v0.19 real persistence boundary

- Exact v0.18 runtime-authorization commit and approved persistence-policy binding.
- Separate authorization, intent, transaction, receipt, and recovery stages.
- Test-only atomic compare-and-swap simulator with monotonic generation and predecessor binding.
- Crash/partial-state/replay/corruption detection with successful-only consumption and retry.
- No actual storage adapter, registry write, runtime activation, transport, credential, or token.

Authoritative design: [v0.19 Real Persistence Boundary](docs/REAL_PERSISTENCE_BOUNDARY_DESIGN_V0.19.md).

## Delivery candidate: v0.18 runtime authorization activation boundary

v0.18 is one design/contract/pure-evaluator/test-ledger/security/documentation unit.

- Exact v0.14–v0.17 source, equivalence, persistence, activation-plan, registry, and lifecycle binding.
- Independent runtime request, review, approval, and immutable authorization-commit record.
- Deterministic fail-closed priority, role separation, explicit time, and replay protection.
- Atomic successful-only ledger consumption with retry after denial or injected commit fault.

It does not implement runtime activation, a runtime switch, tokens, credentials, real persistence,
production-registry writes, transport, HTTP, real-product validation, or production profiles.
Those remain separate designs and approvals. Node runtime warning maintenance remains a separate PR.

Authoritative design:
[v0.18 Runtime Authorization Activation Design](docs/RUNTIME_AUTHORIZATION_ACTIVATION_DESIGN_V0.18.md).

## Delivery candidate: v0.17 production-equivalent evidence boundary

v0.17 is one design/contract/pure-evaluator/security/documentation unit.

- Exact v0.16 plan, execution, evidence, review, approval, identity, and time binding.
- Code-defined criteria and metadata-only environment/configuration/protocol/behavior evidence.
- Deterministic fail-closed assessment with independent review and distinct approval stages.
- Atomic successful-only replay consumption and zero side effects on denial or commit fault.
- Digest-covered v0.14 authorization boundary and v0.15 candidate propagation.

This release defines recognition contracts only. Real production validation, a product adapter,
production profiles, endpoints, credentials, production-registry writes, real persistence, and
runtime activation remain separate design and approval tasks. Node runtime warning maintenance
remains a separate CI PR.

Authoritative design:
[v0.17 Production-Equivalent Evidence Design](docs/PRODUCTION_EQUIVALENT_EVIDENCE_DESIGN_V0.17.md).

## Delivery candidate: v0.16 manual-validation execution boundary

v0.16 is delivered as one design/contract/test-only/security/documentation unit.

- Immutable execution request, safe fixture manifest, and offline environment contract.
- Deterministic exact-case-set execution with atomic record commit and replay protection.
- Immutable execution evidence, independent review, and distinct approval chain.
- Digest-covered v0.14 manual-validation integration without changing v0.15 activation behavior.
- Security E2E and release preparation while retaining all v0.10-v0.15 compatibility gates.

Production-equivalent evidence, a real-product adapter or connection, production profiles,
production-registry writes, real persistence, credentials, and runtime activation remain separate
design and approval tasks. Node runtime warning maintenance remains a separate CI PR.

## Delivery: RAG Benchmark Harness v0.12 registry lifecycle governance

v0.12 is delivered as one design/contract/implementation/security/docs unit rather than separate
phases. It governs post-admission revalidation and monotonic status changes only in the test-only
registry contract.

- Immutable revalidation trigger and pure deterministic requirement evaluator.
- Exact entry/admission/evidence identity, digest, role, restriction, status, and time binding.
- Allowed one-way suspension, deprecation, and revocation transitions with terminal revocation.
- Validate/construct/commit separation and zero lifecycle side effects on denial.
- Full-chain synthetic Security E2E with exact status resolution and zero transport/HTTP activity.
- Documentation and v0.12.0 release-preparation contract without tag or Release creation.

The next separately approved work is a future replacement-entry design requiring fresh evidence,
review, approval, admission decision, and admission. Real production registry operation,
persistence, runtime authorization, manual validation, and real-product connection remain outside
v0.12. Node runtime warning maintenance remains a separate CI task.

Authoritative design: [v0.12 Registry Lifecycle Design](docs/REGISTRY_LIFECYCLE_DESIGN_V0.12.md).

## Design: RAG Benchmark Harness v0.11 production admission

v0.11 designs the manual-validation and evidence-review boundary required before an immutable
Compatibility Profile can be explicitly admitted to a production registry. It builds on v0.10
approval governance but does not execute validation, connect to a product, add a production
profile/entry, persist a registry, or expand the runtime.

### Phase plan

- Phase A: manual validation plan contract. Completed and merged.
- Phase B: manual validation evidence contract. Completed and merged.
- Phase C: production admission evaluator. Completed and merged.
- Phase D: offline manual-evidence import and validation boundary. Completed and merged.
- Phase E: registry admission enforcement and security E2E. Completed and merged.
- Phase F: docs, CI, and release preparation. Implemented by the release-preparation PR; pending
  review and merge.

The authoritative state transition, role separation, plan/evidence schemas, decision table,
revalidation triggers, failure matrix, security boundary, phase merge gates, unresolved questions,
and pre-validation checklist are in
[v0.11 Production Admission Design](docs/PRODUCTION_ADMISSION_DESIGN_V0.11.md).

Every phase remains product-neutral and fail-closed. Synthetic evidence is never manual evidence.
Real-product validation, credentials, real data, external/private-LAN access, production profiles
and entries, persistence, fallback, nearest-version selection, schema inference, and automatic
approval remain separately approved non-goals.

### Phase A delivery

- Added an immutable, hashable manual-validation plan with exact profile, protocol, and opaque
  product-fixture versions, explicitly supplied timezone-aware timestamps, and a 30-day maximum
  execution window.
- Fixed the complete required-case, abort-condition, and cleanup-condition sets with deterministic
  ordering, defensive copying, unknown/duplicate/missing rejection, and SHA-256 canonical identity.
- Enforced operator/reviewer/approver separation and safe endpoint, synthetic-only data,
  credential-prohibited, non-disclosing summary, and bounded typed-error contracts.
- Kept plan construction separate from validation execution, approval, registry admission,
  transport generation, CLI/config, persistence, and any real-product operation.

### Phase B delivery

- Added immutable manual evidence bound to one exact Phase A plan ID/digest, profile/protocol,
  opaque product fixture, planned/observed product version, operator, reviewer, and required cases.
- Added canonical environment fingerprints, explicit execution/freshness timestamps, typed case
  outcomes, complete close/cleanup and non-disclosure evidence, and bounded failure summaries.
- Canonicalized safe evidence fields with UTC six-digit microsecond timestamps and SHA-256,
  preserving equivalent-instant identity while preventing timestamp truncation collisions.
- Kept evidence construction separate from manual execution, approval, production admission,
  runtime authorization, transport generation, registry write, persistence, and real-product use.

### Phase C delivery

- Added immutable reviewer-attestation, admission-request, decision-result, reason, restriction,
  and revalidation-trigger contracts with exact Phase A/B and v0.10 metadata identity binding.
- Added a deterministic pure evaluator with explicit UTC evaluation time, `manually_validated`
  maturity, reviewer/approver separation, evidence freshness, supported-version, restriction, and
  revalidation gates.
- Fixed decision priority to rejected identity/security failures, then revalidation/freshness
  failures, then explicit enforceable restrictions, then unrestricted approval.
- Returns registry eligibility only. It creates no registry entry, performs no registry read/write
  or persistence, grants no runtime authority, and generates no transport or product connection.

### Phase D delivery

- Added an immutable import request and safe result for one explicitly supplied
  `inline_safe_fixture`; file, URL, stream, stdin, clipboard, environment, cloud, database, and
  process sources are outside the contract.
- Added exact mapping schemas, total and field-size limits, structural allowlists, typed
  non-disclosing errors, all 22 required case fixtures, environment-digest verification, exact
  Phase A plan binding, and deterministic source/result digests.
- Normalized timezone-aware timestamps to UTC with fixed six-digit microseconds and constructs
  evidence only through the public Phase B contract, which regenerates the evidence digest.
- Import acceptance means only that a safe fixture was validated and evidence was constructed. It
  does not execute manual validation, approve evidence, grant registry eligibility, write a
  registry, authorize runtime use, generate transport, or connect to a product.

### Phase E delivery

- Added immutable registry-admission request, entry, result, safe-summary, event, and typed-reason
  contracts that accept only an exact eligible Phase C decision and explicit evaluation time.
- Revalidate the Phase C canonical digest, complete plan/evidence/attestation digest chain, exact
  profile/protocol/product versions, effective restrictions, expirations, and administrator role
  separation before constructing any entry.
- Split validation, entry construction, and commit so every denial leaves the test registry
  unchanged with zero writes, events, transports, and HTTP requests.
- Added a test-only in-memory registry with exact profile/product/protocol resolution, duplicate
  and overwrite rejection, monotonic inactive status handling, and no discovery, fallback,
  nearest-version selection, schema inference, persistence, or production-registry write.
- Admission success remains synthetic test-registry evidence only. It is not a real production
  entry, runtime authorization, manual validation, or evidence of real-product compatibility.

### Phase F delivery

- Consolidate the Phase A-E contracts, exact identity/role/digest chain, temporal ordering,
  structural allowlist priority, atomic denial behavior, and security limitations across README,
  Usage, Design Notes, changelog, and the authoritative v0.11 design.
- Add the v0.11.0 release checklist and contract tests that require all Phase A-E and compatibility
  suites to remain included in the Python 3.11/3.12 full-suite workflow.
- Retain the existing workflow without duplicate targeted steps because each matrix job already
  runs the complete pytest suite; require targeted local checks and Actions success as release
  evidence.
- Prepare release notes only. Tag creation, tag push, GitHub Release publication, and Vault update
  remain separate explicitly requested post-merge operations.

### Release and post-release sequence

1. Review and merge the Phase F PR with a normal merge commit.
2. Synchronize clean local `main` with `origin/main` and rerun the release checklist.
3. Create and push annotated tag `v0.11.0` pointing directly to the Phase F merge commit.
4. Publish a non-draft, non-prerelease latest GitHub Release as a separate operation.
5. Record the milestone through a separate post-release Vault PR; optional Notion recording remains
   separate.

Real-product manual validation, a production profile, a real production-registry entry,
persistence, and runtime production authorization remain separately approved future work.

## Release preparation: RAG Benchmark Harness v0.10.0 approval governance

v0.10 defines fail-closed governance around production Compatibility Profiles without adding a
production profile or connecting to a real product. Profile approval and registry admission remain
separate from transport configuration, benchmark evaluation, reports, and CI.

### Phase plan

- Phase A: profile approval metadata and maturity contract. Completed.
- Phase B: validation report and approval decision contract. Completed.
- Phase C: trusted production registry contract. Completed.
- Phase D: synthetic approval workflow harness. Completed.
- Phase E: approval enforcement and security E2E. Completed.
- Phase F: docs, CI, and release preparation. Completed by the release-preparation PR.

### Delivery boundary

- Maturity is explicit: `draft`, `synthetic_validated`, `manually_validated`, `approved`,
  `deprecated`, or `revoked`; no state is promoted automatically.
- Only approved immutable profile versions may enter a future production registry. Test and
  production registries remain separate, IDs may not collide, and versions may not be overwritten.
- Approval requires schema, synthetic harness, security E2E, capability, mapping, score/source,
  timeout/size, non-disclosure, and manual-validation evidence.
- Missing or expired approval, unsupported product versions, revoked profiles, and required
  revalidation fail closed through safe categories and CLI error `3`.

### Phase A delivery

- Added immutable maturity, approval decision, approval/validation metadata, supported product
  version range, bounded restriction, and safe summary contracts.
- Added an explicit transition allowlist with no direct draft approval, automatic promotion,
  reactivation of deprecated/revoked profiles, nearest-version selection, or fallback.
- Added fail-closed consistency checks for profile/version identity, manual validation evidence,
  required capabilities, score/source policy, expiration, revalidation, and supported versions.
- Kept the contract disconnected from CLI/config, transport, production profiles, and any trusted
  production registry. Phase B builds only the report/decision contract on this boundary.

### Phase B delivery

- Added immutable validation case results and validation reports with bounded counts/durations,
  explicit synthetic/manual environments, safe error categories, and no raw payload retention.
- Added product-neutral required case sets with explicit differences between synthetic and manual
  validation; missing, duplicate, unknown, failed, or skipped required cases fail closed.
- Added deterministic approval decision evaluation for report status, maturity, identity, version
  range, capability/policy results, restrictions, expiration, and revalidation.
- Added a bounded validation summary without reviewer/approver identity, endpoint, query, raw
  traffic, source path, credential, or internal exception disclosure.
- Kept Phase B contract-only. Production registry, CLI/config integration, report files, manual
  validation execution, product connectivity, fixtures, and workflow remain unimplemented.

### Phase C delivery

- Added immutable trusted-registry entries that bind exact profile, protocol, approval, validation,
  capability, score/source policy, version-range, restriction, expiration, and registry-kind
  metadata without retaining endpoints, paths, credentials, raw payloads, or free-form audit text.
- Added fail-closed registration eligibility for approved, unexpired, manually validated
  production entries and explicit separation from synthetic test-registry entries.
- Added explicit register, exact resolve, contains, bounded-summary, suspend, deprecate, and revoke
  operations with no discovery, overwrite, nearest-version selection, profile/version fallback,
  reactivation, rollback, or automatic registry conversion.
- Added immutable resolved views, snapshots, safe lifecycle events, and bounded error categories.
  Registry persistence, production profiles/entries, CLI/config integration, manual validation
  execution, product connectivity, fixtures, report files, and workflow remain unimplemented.

### Phase D delivery

- Added an immutable deterministic workflow input and safe result that connect synthetic evidence,
  validation reporting, approval decisions/metadata, registry eligibility, test-registry
  registration, exact resolution, bounded events, and case counts.
- Added an in-code product-neutral all-pass evidence builder for every Phase B synthetic case with
  an explicit evaluation time and no clock, UUID, randomness, sleep, I/O, network, or filesystem.
- Added strict stage ordering and fail-closed partial results for missing/duplicate/failed cases,
  unsafe capability/policy results, expiration, revalidation, role/identity mismatch, restrictions,
  registry-kind separation, unsupported versions, and inactive registry states.
- Kept successful and restricted synthetic approval flows in an explicit test registry. Production
  eligibility is evaluated and must reject synthetic evidence; no production-registry write,
  production profile/entry, persistence, CLI/config, fixture, report-file, or workflow change was
  added.

### Phase E delivery

- Added an immutable approval-enforcement request and bounded safe result that require an exact
  profile/version, normalized product version, explicit evaluation time, explicit test registry,
  required runtime capabilities, fixed execution constraints, top-k, and optional fields.
- Integrated enforcement after compatibility-profile resolution and before transport creation.
  Denial creates no transport, performs no health/capability/retrieval request, sends no HTTP
  request, and does not call close for a transport that never existed.
- Added fail-closed checks for registry kind/status, maturity, decision, validation/approval and
  restriction expiration, revalidation, supported product/minor version, approved capabilities,
  score/source policy consistency, and bounded restrictions without implicit top-k reduction,
  optional-field removal, capability downgrade, fallback, discovery, or nearest-version choice.
- Added synthetic loopback security E2E for exact approval, restrictions, lifecycle denials,
  deterministic evaluation time, safe errors, fixed stage order, single close after every
  post-transport outcome, report non-disclosure, and existing PASS/WARNING/FAIL/CLI-error behavior.
- Kept enforcement opt-in and test-registry-only. No public production CLI/config surface,
  production profile/entry, registry persistence/write, manual validation, real-product
  connection, credential, fixture, report-schema, workflow, tag, or Release was added.

### Phase F delivery

- Separated the public overview, usage boundary, design rationale, delivery status, changelog, and
  release-operator checklist so synthetic governance is not presented as product compatibility.
- Confirmed the existing Python 3.11/3.12 matrix runs the full Phase A-E suite and retains explicit
  compatibility integration, HTTP security, CLI, and benchmark exit-code gates. A duplicate
  approval-only workflow step was not added.
- Added a checked release-preparation contract for documentation boundaries, workflow matrix/full
  pytest coverage, and the required post-merge tag target.
- Prepared but did not create `v0.10.0`. The annotated tag must point to the Phase F merge commit;
  the tag, GitHub Release, and Vault record are separate post-merge operations.

### Release and post-release sequence

1. Merge the Phase F PR after Python 3.11/3.12 Actions succeeds.
2. Synchronize clean local `main` with `origin/main` and rerun the release checklist.
3. Create and push annotated tag `v0.10.0` at the Phase F merge commit.
4. Create the GitHub Release from that tag as a distinct operation.
5. Record the release in the Vault through a separate PR.

Possible later work remains separately approved: manual real-product validation, a production
profile proposal, production-registry admission and persistence design, and product-specific
operational integration. None is implied or authorized by the v0.10.0 release.

### Separate manual product gate

Real-product validation is outside the v0.10 phases and requires explicit user approval as a
separate task. It is manual, isolated, loopback-only, credential-free, and synthetic-only. CI must
not connect to a product, depend on an external localhost process, or access real documents.

Future candidates after the governance phases are complete:

- production profile approval procedures
- product-specific synthetic compatibility harnesses
- manual connection checklists
- safe observability for bounded status, counts, duration, and error category only

## Completed: RAG Benchmark Harness v0.9 Local RAG compatibility

v0.9 introduces a product-neutral compatibility boundary between the v0.8 loopback HTTP transport
and any future Local RAG product. Product-specific versions and field names belong to an explicit
Compatibility Profile. They must not alter transport security, evaluator behavior, report
top-level keys, or existing exit codes.

### Phase plan

- Phase A: compatibility profile and version contract. Completed.
- Phase B: health and capabilities contract. Completed.
- Phase C: request and response mapping contract. Completed.
- Phase D: synthetic compatibility harness. Completed.
- Phase E: profile integration and security E2E. Completed.
- Phase F: docs, CI, and release preparation. Completed.

### Compatibility boundary

- Unknown profile IDs, profile versions, and protocol major versions fail closed.
- Required capabilities are checked before retrieval; optional capabilities are omitted safely.
- Request and response mapping is explicit. Schema guessing, automatic fallback profiles, and
  implicit score normalization are forbidden.
- Only safe opaque source identifiers may reach existing reports. Filesystem paths, UNC values,
  drive-letter paths, home paths, and full URLs are rejected rather than rewritten.
- Product-neutral failures map through `RetrievalAdapterError` and `BenchmarkError` to CLI error
  `3` without product, endpoint, query, path, or raw payload disclosure.

### Phase A delivery

- Added typed `CompatibilityProfile`, strict `SemanticVersion`, explicit field mappings, optional
  feature flags, and allowlisted score/source policies.
- Added exact profile registry selection with no fallback. Major mismatches fail closed, and minor
  differences require an explicit allowlist; patch differences within an accepted minor are
  compatible.
- Added safe relative HTTP path validation and bounded compatibility error categories without
  rejected values in exceptions or profile representations.
- Added contract tests only. Profile mappings are not executed, and health/capability communication
  remains Phase B work.

### Phase B delivery

- Added immutable health, capabilities, and compatibility-result models that discard raw mappings
  after validation.
- Added exact health schema/status/service checks and fail-closed protocol major/minor validation
  using the selected profile contract.
- Added negotiation for five required capabilities and explicitly requested optional capabilities,
  including profile feature-flag alignment with no implicit downgrade or fallback.
- Added bounded health/capability error categories and safe summary representations without raw
  status, version, capability value, endpoint, path, product, or payload disclosure.
- Added contract tests only. HTTP communication, bounded-client integration, request/response
  mapping execution, and CLI/config integration remain unimplemented Phase C-or-later work.

### Phase C delivery

- Added typed bounded standard requests and explicit flat mapping execution with a 64 KiB encoded
  request limit and no raw mapping retention.
- Added product-response mapping to existing `RankedResult` values with required-field, safe source
  identifier, rank continuity, duplicate ID, top-k, metadata, and score-semantics validation.
- Tied score, title, matched-keyword, and query-ID behavior to the negotiated capability result;
  requested missing fields fail closed and unnegotiated optional fields are not retained.
- Added bounded mapping error categories and safe summaries containing only counts, declared score
  semantics, and enabled optional fields.
- Kept the work contract-only. Synthetic compatibility harness execution, CLI/config integration,
  health/capability HTTP communication, and real-product access remain unimplemented.

### Phase D delivery

- Added a deterministic test-oriented harness that directly composes the Phase A-C production
  profile, health, capability, request-mapping, response-mapping, and ranked-result contracts.
- Added an immutable safe result containing only profile/protocol/health status, enabled optional
  capabilities, mapped request and result counts, score semantics, and normalized ranked results.
- Added happy-path coverage for all score semantics and fail-closed coverage for profile/version,
  health, capabilities, mappings, identifiers, ranks, duplicates, top-k, malformed responses, and
  query-ID echo.
- Kept the harness free of network, filesystem, sleep, timeout, randomness, product schema,
  fixtures, CLI/config integration, and real-product access.

### Phase E delivery

- Added explicit bounded `compatibility_profile` selection for `loopback_http`, resolved only by the
  trusted registry with no auto-selection, nearest-version choice, or fallback.
- Integrated health, capabilities, negotiated request mapping, bounded HTTP retrieval, response
  mapping, ranked-result normalization, evaluator, report, and exit-code boundaries.
- Added fake-loopback synthetic E2E coverage for JSON/YAML, exits `0`/`1`/`2`/`3`, compatibility
  failures, deterministic lifecycle ordering, and sensitive-value non-disclosure.
- Kept real-product profiles, real endpoints, credentials, real documents, filesystem retrieval,
  external/private-LAN traffic, fixtures, config, and workflow unchanged and unsupported.

### Phase F delivery

- Consolidated the Phase A-E compatibility profile, health/capabilities, mapping, harness, and
  loopback integration boundaries in README, usage, design notes, and changelog.
- Added an explicit Python 3.11/3.12 CI step for compatibility profile integration E2E while
  preserving the full suite, HTTP security E2E, local-rag E2E, and benchmark exit-code checks.
- Added the v0.9.0 release checklist without creating a tag or Release.

### v0.9 endpoint

v0.9 provides an explicitly selected, fail-closed, product-neutral Compatibility Profile path that
has been verified only against deterministic synthetic fake-loopback responses. It does not provide
a production profile, product configuration, compatibility claim, credential path, or real-product
connection.

Next candidates are deliberately separate from v0.9 delivery:

- production profile approval procedure
- product-specific compatibility harnesses using synthetic values
- an explicitly approved manual connection checklist
- safe observability limited to bounded status, counts, duration, and error category

### Separate manual product gate

Real-product validation is not a v0.9 implementation phase and is never run from CI. A separately
approved manual task must identify the product, version, selected profile, synthetic query set, and
stop conditions before connecting. It is limited to loopback, uses no credentials or real data,
stores no raw response, emits only a safe summary, and stops immediately without fallback on any
unexpected result.

### Non-goals

- Real Local RAG or product-specific adapter integration.
- Product auto-discovery, fallback profile selection, or response-schema inference.
- Filesystem retrieval, external/private-LAN traffic, credentials, real documents, embeddings,
  vector databases, LLM evaluation, external APIs, cloud services, or external MCP.

## Completed: RAG Benchmark Harness v0.8 secure Local RAG transport

v0.8 defines and incrementally verifies a loopback-only HTTP transport without connecting to a real
Local RAG system during the design phase. Synthetic retrieval remains the default, and every
transport phase must preserve the existing adapter, evaluator, report, and exit-code boundaries.

### Phase plan

- Phase A: define endpoint validation and HTTP transport contracts - completed.
- Phase B: add fake loopback server contract tests with fixed synthetic responses - completed.
- Phase C: implement the bounded loopback HTTP client - completed.
- Phase D: integrate the transport with safe CLI and config selection - completed.
- Phase E: add synthetic end-to-end and transport security tests - completed.
- Phase F: finalize docs, CI coverage, and release notes - completed.

### v0.8 endpoint

- The explicit `loopback_http` path is integrated with bounded config loading, loopback-only
  resolution and peer checks, one-shot lifecycle, deterministic evaluation, safe reports, and
  PASS `0` / WARNING `1` / FAIL `2` / CLI error `3`.
- Synthetic remains the default and `in_memory` compatibility is preserved.
- Verification is limited to fixed synthetic responses from ephemeral fake loopback servers. No
  real Local RAG product, real document, external/private-LAN endpoint, or credential is used.

### Next candidates

- Pre-connection product validation: define a separately reviewed compatibility gate before any
  real Local RAG endpoint is contacted.
- Compatibility validation: version and capability negotiation, response-contract conformance, and
  upgrade/downgrade behavior using synthetic doubles first.
- Operational monitoring: bounded duration/result-count/status/error-category telemetry without
  query, endpoint, credential, raw traffic, or real-path disclosure.

### Security constraints and non-goals

- Allow only `127.0.0.1`, `::1`, or explicitly allowlisted names whose complete resolution set is
  loopback; reject external, private-LAN, wildcard, unspecified, and changed destinations.
- Disable redirects and proxy use. Validate the peer destination for every new connection to reduce
  DNS rebinding and time-of-check/time-of-use risk.
- Require bounded JSON requests and responses, connect/read/total timeouts, and safe error mapping.
- Do not load API keys, bearer tokens, credential files, cookies, environment secrets, or real paths.
- Do not implement real Local RAG, Hermes, LM Studio, filesystem retrieval, embeddings, vector
  databases, LLM evaluation, external APIs, cloud services, external MCP, or real-document access.

## Completed: RAG Benchmark Harness v0.7 local connection contract

v0.7 designs a local-only connection boundary before any Local RAG integration. Synthetic retrieval
remains the default operational retrieval path. The explicit `local-rag` path is limited to the
no-I/O in-memory synthetic transport and is not a real Local RAG connection.

### Phase plan

- Phase A: define configuration and transport contracts - completed.
- Phase B: implement an in-memory or fake transport with fixed synthetic responses - completed.
- Phase C: implement a local adapter client skeleton against the transport abstraction - completed.
- Phase D: add an explicit CLI selector and safe configuration loading - completed.
- Phase E: add synthetic end-to-end connection and error contract tests - completed.
- Phase F: finalize docs, CI coverage, and release notes - completed.

### Constraints and non-goals

- Approved transports remain local-only: in-memory first, with loopback HTTP, Unix socket, or Windows
  named pipe considered only in later implementation phases.
- External hosts, redirects, filesystem retrieval, credentials, embeddings, vector databases, LLM
  evaluation, cloud services, external APIs, and external MCP are out of scope.
- No direct access to `C:\\AI_Restricted` or real materials under `C:\\AI_Local_RAG` is allowed.
- The adapter may retrieve only through its future API boundary and must not expose configuration
  values, real paths, query text, source content, secrets, or stack traces.

## Completed: RAG Benchmark Harness v0.6 retrieval adapter interface

v0.6 establishes a stable retrieval interface so that the synthetic implementation and a future
local-only implementation can be selected without changing benchmark evaluation semantics.

### Phase plan

- Phase A: interface and ranked-result model extraction - completed.
- Phase B: migrate deterministic synthetic retrieval to the interface - completed.
- Phase C: add mock adapter and adapter contract tests - completed.
- Phase D: add a local-only adapter skeleton without a real RAG connection - completed.
- Phase E: document the interface, add CI coverage, and prepare release notes - completed.

### Constraints and non-goals

- Adapters receive a query and `top_k` and return deterministic ranked results or a typed retrieval error.
- The evaluator owns hit@k, source match, keyword coverage, no-result, unsafe-or-unknown, reporting, and result-to-exit-code mapping.
- Adapter-local scores must not be compared as universal quality scores across implementations.
- Reports keep identifiers and bounded metadata only; they never replay long document content.
- Synthetic fixtures remain the only data source during v0.6 implementation and testing.
- No Hermes, LM Studio, production Local RAG, embeddings, vector databases, LLM evaluation, external API, cloud, external MCP, `C:\\AI_Restricted`, or `C:\\AI_Local_RAG` real-document access is in scope.

## Completed: RAG Benchmark Harness v0.5 synthetic retrieval

v0.5 adds synthetic-only retrieval and scoring before any production RAG integration.
The benchmark harness remains loosely coupled from Local RAG and will not connect to Hermes, LM Studio,
real documents, embedding services, vector databases, LLM evaluators, cloud services, or external APIs.

### Phase plan

- Phase A: retrieval adapter / deterministic keyword search - completed
- Phase B: hit@k / expected source match - completed
- Phase C: expected keyword coverage / no-result / unsafe-or-unknown evaluation - completed
- Phase D: report / CI / docs cleanup - completed

### Design constraints

- Use synthetic fixtures only.
- Do not use real documents, real project names, real company names, or real person names.
- Keep the retrieval adapter separate from benchmark evaluation.
- Keep any future real RAG integration behind an adapter boundary and design it separately after v0.5.
- Preserve existing `check-mask` behavior and exit codes.

### v0.5 delivered capabilities

- Synthetic retrieval adapter.
- Deterministic keyword / token overlap retrieval.
- Ranked benchmark results.
- hit@k and expected source match scoring.
- Expected keyword coverage scoring.
- No-result and unsafe-or-unknown expectation scoring.
- PASS / WARNING / FAIL / CLI error exit code alignment.

### Still not implemented

- Production Local RAG integration.
- Hermes or LM Studio integration.
- Embedding or vector database retrieval.
- LLM-based answer evaluation.
- External API or cloud service integration.

## Completed: RAG Benchmark Harness v0.4

RAG Benchmark Harnessは、Local RAG本線を直接操作せず、RAG品質を外部から検証する補助ツールとして整備しました。v0.4では実資料を使わず、synthetic corpusとsynthetic query setだけで動くbenchmark CLI skeletonを追加しました。

- Phase A: synthetic benchmark fixture設計 完了
- Phase B: benchmark CLI skeleton 完了
- Phase C: benchmark report skeleton拡充 完了
- Phase D: CI / docs整理 完了

設計上の優先事項:

- 実資料、実案件名、実会社名、実個人名を使わない
- expected source / expected keyword / expected answer hintを使う
- 将来のhit@k、expected source match、expected keyword coverageに備えたreport skeletonを出力する
- no-result query、unsafe / unknown answerを扱う
- v0.4では実RAG接続、検索評価、LLM評価、外部API評価、クラウド評価を使わない

### Phase A: synthetic benchmark fixture設計

Phase Aでは、RAG Benchmark Harnessの最初の実装に入る前に、synthetic corpusとsynthetic query setの形式を固定します。実ファイル追加はPhase B以降とし、この段階では配置案とフィールド定義のみを決めます。

- corpus配置案: `tests/fixtures/benchmark/corpus/`
- query set配置案: `tests/fixtures/benchmark/queries.jsonl`
- corpus文書は架空Markdownのみを使う
- corpus metadataは `document_id`、`title`、`tags`、`expected_searchable_facts` を基本にする
- query setは `query_id`、`question`、`expected_source_ids`、`expected_keywords`、`expected_answer_hint`、`no_result_expected`、`unsafe_or_unknown_expected` を基本にする
- 実資料、実案件名、実会社名、実個人名は使わない
- `C:\AI_Restricted` と `C:\AI_Local_RAG` 配下の実資料は使わない

Phase B-Dで、benchmark CLI skeleton、JSON / Markdown benchmark report skeleton、CI / docs整理まで完了しました。

### v0.4以降の候補

- retrieval / scoringを実装する前に、評価入力とreport schemaの互換性を維持する
- hit@k、expected source match、expected keyword coverageの実装方針を別PRで設計する
- 実RAG接続を行う場合も、Local RAG本線を直接変更しない疎結合なadapterとして扱う
- LLM評価や外部API評価は、明示的な設計と安全方針が固まるまで使わない

## Completed: Masked Document Checker v0.3

- Phase A: 金額・料率・坪単価 / 平米単価検出の強化
- Phase B: 住所候補検出の強化
- Phase C: 契約条件 / 内部情報キーワード拡張
- Phase D: 重複finding抑制とMarkdown report summary改善
- `--config config/rules.yaml` による `extend_builtin` 方式のルール追加
- 既存JSON / Markdownレポート構造と `matched_text` 伏せ字方針の維持
- 実資料を使わない安全fixture方針の維持

## Masked Document Checker v0.3候補

- 金額・単価・料率検出の強化
- 住所候補検出の強化
- 契約条件 / 内部情報キーワード拡張
- 重複finding抑制
- 追加pytest
- 実資料を使わない安全fixture方針の維持

## 1. Masked Document Checker

Markdownファイルまたはフォルダを対象に、個人情報・金額情報・契約情報・内部事情を検出し、JSON + Markdownレポートを出力する。今回のMVP実装範囲。

### v0.2候補

- `--config` によるルール読込
- ルール定義の外部化
- YAML不備時のCLIエラー
- 既存レポート形式の維持
- ルール追加時のpytest拡充

## 2. RAG Benchmark Harness

RAG構成ごとの検索品質、回答品質、再現性を比較する検証基盤。

## 3. Citation Verifier

回答内の引用と根拠資料の整合性を検証するツール。

## 4. RAG Scope Gate

投入対象資料のスコープ、禁止領域、公開可否を事前判定するゲート。

## 5. Document Conversion QA Tool

PDF、Word、Markdownなどの変換結果を検査し、欠落や表崩れを確認するツール。

## 6. Project Index Manager

プロジェクト別のRAG投入対象、除外対象、履歴を管理するインデックス。

## 7. RAG Error Log Analyzer

RAG回答の失敗ログを分類し、改善候補を抽出する分析ツール。

## 8. Local RAG Dashboard

ローカル環境で検査結果や投入状況を一覧するDashboard。今回のMVP範囲外。

## v0.13 Replacement Admission Chain

- Complete: immutable replacement request, decision, successor, event, and safe result contracts.
- Complete: fresh-chain, exact identity/digest/role/restriction, and temporal gates.
- Complete: test-only atomic state-bundle commit, retry contract, replay protection, and Security
  E2E.
- Release preparation: documentation, release contract, regressions, and Python 3.11/3.12 CI.
- Later, separately approved work: production operation, persistence, runtime authorization, and
  Node action runtime maintenance.

## v0.14 Production Boundary / Authorization Contract

- Complete: immutable exact-source boundary evidence and explicit readiness states.
- Complete: pure deterministic authorization-candidate evaluator and fail-closed hard gates.
- Complete: role/temporal/digest/snapshot binding, safe summaries, Security E2E, and release
  contract documentation.
- Boundary: candidate review eligibility is not authorization or activation; synthetic-only
  evidence is insufficient.
- Later, separately approved work: performed manual validation, production persistence,
  production registry operation, and runtime authorization activation.

## v0.15 Persistence / Authorization Activation Boundary

- Complete: immutable persistence policy and authorization-record contracts.
- Complete: canonical tamper-evident generation and predecessor binding.
- Complete: test-only atomic in-memory persistence and replay semantics.
- Complete: pure activation-request evaluator and immutable commit-plan boundary.
- Complete: role, temporal, lifecycle, digest, stale-state, and replay gates.
- Complete: Security E2E, documentation, and a v0.15.0 release checklist.
- Pending: merge after review, followed by separate post-merge verification, tag, and Release.
- Later, separately approved work: production persistence, runtime activation, production-registry
  mutation, and operational manual validation.
