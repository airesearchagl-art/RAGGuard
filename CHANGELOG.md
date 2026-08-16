# Changelog

## v0.29.0 - Unreleased

### Added

- Immutable metadata-only one-shot execution packet and preparation request/decision contracts.
- Exact object-backed revalidation across v0.25 authorization/operator/usage, v0.27
  root/resolver/target, and v0.28 purpose/provisioning/approval/closure objects.
- Safe summary with opaque IDs, digests, fixed policy metadata, expiry, readiness, and reason codes.
- Test-only successful-only packet/request replay protection with denial-state immutability.

### Security boundary

- Preparation stops at `ready_for_explicit_execution_approval`; it never grants execution
  authorization and never opens or reads a file.
- Forgery, exhaustion, widening, missing closure evidence, expiry, role conflict, and replay fail
  closed with every real-data and external side-effect count at zero.
- No raw root/target locator, payload, real identity, credential, or token enters the packet,
  summary, report, or repository.

## v0.28.0 - Unreleased

### Added

- Immutable purpose, root-provisioning request, opaque root identity, target selection, closure
  requirement, approval request, review, approval, and approved-trial contracts.
- Object-backed root confinement, link/reparse, permission, write-prohibition, and network-
  isolation verification with exact attestation binding.
- Exact live v0.25 authorization/operator/usage and v0.27 root descriptor/resolver/target binding.
- Independent security and governance review plus distinct execution approval and eight-role
  separation.
- Test-only atomic registry with generation, predecessor, successful-only replay, retry, expiry,
  revocation, supersession, execution-pending, and closed lifecycle contracts.

### Security boundary

- Approval stops at explicit one-shot execution review eligibility and performs no file open/read.
- Internal-low, one-document, one-read, chunking-candidate, no-retention/log/cache/persistence,
  prohibited export/network, and mandatory closure gates are fail closed.
- Actual Local RAG/restricted material, arbitrary filesystem access, external services,
  credentials, persistent storage, production registries, and runtime activation remain outside
  this boundary; all corresponding side-effect counts are zero.

## v0.27.0 - Unreleased

### Added

- Metadata-only controlled-root descriptor, resolver policy, opaque target reference, identity
  snapshots, one-shot request/result/receipt, closure, and post-read evidence contracts.
- Capability-bound resolver and filesystem adapter for controlled synthetic fixtures only.
- Root confinement, regular-file/type/size validation, and symlink/junction/reparse denial.
- Root-directory and pinned-file handle authority with component-by-component no-follow opens;
  the read adapter performs no path-based reopen.
- Pre/open/post identity comparison and fail-closed TOCTOU fault coverage.
- Test-only atomic ledger with nine successful-only replay identities and pending closure state.

### Security boundary

- Traversal, absolute/drive/UNC/device paths, alternate streams, wildcards, links, root escape,
  identity changes, verification failures, forgery, replay, and commit faults consume nothing.
- A stable read plus exact v0.26 classification and masking is required before usage changes from
  one to zero. Closure completion grants no downstream-processing or persistence authority.
- Automated tests use controlled synthetic filesystem targets only. Actual Local RAG material,
  restricted material, arbitrary files, external services, credentials, persistent storage,
  production registries, and runtime activation remain outside this boundary.

## v0.26.0 - Unreleased

### Added

- Immutable metadata-only read request and opaque controlled-target descriptor.
- Actual v0.25/v0.24 object-chain pre-read verification and exact operator/usage binding.
- Immutable fixture-backed controlled adapter with deterministic injected failure modes.
- Metadata-only execution, classification, masking, receipt, and masked-candidate contracts.
- Test-only atomic ledger with seven successful-only replay identities and one-shot exhaustion.
- Protocol-only future explicit one-shot real-data trial hook without an implementation.

### Security boundary

- Only a successfully classified and masked controlled read consumes usage from one to zero.
- Failure, forgery, replay, and commit fault consume nothing and leave ledger state unchanged.
- The maximum downstream state is `verified_masked_content_candidate`; embedding, persistent
  vector write, retrieval, prompt/LLM input, export, persistence, and runtime activation remain
  unauthorized.
- Automated execution performs no arbitrary-file or actual real-data read. All external,
  credential, storage, registry, and runtime side-effect counts remain zero.

## v0.25.0 - Unreleased

### Added

- Immutable metadata-only real-data selector and internal-low-only one-shot access policy capped
  at the chunking candidate stage.
- Exact v0.24 trial/source object verification with independent access security and governance
  reviews, explicit future operator assignment, and distinct access approval.
- Test-only atomic authorization registry with generation, predecessor, successful-only replay,
  retry, immutable usage-count, and terminal lifecycle contracts.
- Pure readiness evaluator that stops at limited real-data read execution eligibility.

### Security boundary

- Access authorization and operator assignment do not execute an actual file open/read or grant
  persistence, production registry, or runtime activation authority.
- Actual file open/read, real-data access, filesystem/database/persistent-vector writes, external
  network/HTTP/cloud, credential/token, production registry, and runtime counters remain zero.

## v0.24.0 - Unreleased

### Added

- Immutable metadata-only real-data trial scope and safe data-class, stage, retention, logging,
  cache, export, and persistence policy contracts.
- Exact v0.23 environment/session/execution/readiness object binding with independent security and
  data-governance reviews plus distinct trial approval.
- Test-only atomic approved-trial registry with generation, predecessor, replay, retry, fault, and
  one-way lifecycle protection.
- Pure readiness evaluator that stops at real-data access authorization review eligibility.

### Security boundary

- Trial approval does not authorize real-data access, real-data use, or an actual document read.
- No filesystem/database/persistent-vector write, external network/HTTP/cloud, credential/token,
  production registry write, runtime activation, or runtime switch.

## v0.23.0 - Unreleased

### Added

- Immutable environment manifest, seven concrete verification results, exact-bound attestation
  suite/evidence, independent review, and distinct approval.
- Metadata-only session request and test-only atomic registry with exact v0.22 object binding,
  monotonic generation, predecessor binding, replay protection, and terminal lifecycle states.
- Object-backed independent pre-execution session review/approval required before registry
  admission, with their canonical digests bound into every approved session.
- Controlled eleven-stage execution evidence, operator-bound receipt, zero-valued external-effect
  accounting, independent security review/approval, and explicit trial-review readiness.

### Security boundary

- Environment attestation is not production environment approval.
- Session pre-approval, controlled execution, and execution approval are not real-data approval
  or real-data-use authorization.
- No real data, external network/HTTP/cloud, credential/token, persistent vector database,
  production registry write, runtime activation, or runtime switch.

## v0.21.0 - Unreleased

### Added

- Immutable metadata-only storage-adapter manifest, capability, evidence, review, approval, policy,
  and approved-record contracts.
- Object-backed ten-result conformance suite; Boolean capability claims are never independently
  trusted, and attestation evidence exact-binds the verified suite and individual results.
- Pure fail-closed conformance and v0.19 object-backed write-compatibility evaluators.
- Test-only atomic adapter registry with successful-only replay consumption, fault retry, monotonic
  lifecycle, and Security E2E zero-side-effect coverage.

### Security boundary

- Approval stops at write-authorization review and never executes or authorizes a storage write.
- No filesystem/DB/external-storage operation, network/HTTP, credential/token use, production
  registry write, runtime activation/switch, or real-data access.

## v0.20.0 - Unreleased

### Added

- Immutable controlled validation authorization, environment, plan, scenario, execution receipt,
  evidence review/approval, and atomic test-ledger contracts.
- Exact v0.16-v0.19 object-backed approval-chain, plan/criteria, runtime-authorization, and
  persistence-receipt binding.
- Successful-only replay consumption with failure and commit-fault retry.

### Security boundary

- No real data/product connection, network, persistence, registry write, or runtime activation.

## v0.19.0 - Unreleased

### Added

- Immutable persistence authorization, independent review/approval, intent, and transaction-plan
  contracts exact-bound to the v0.18 runtime authorization commit.
- Pure fail-closed durable-persistence evaluator and test-only atomic compare-and-swap simulator.
- Successful-only `PersistenceCommitReceiptV2`, monotonic generation, predecessor binding, replay
  protection, retry after injected failure, and corruption-aware recovery classification.
- Security E2E side-effect accounting with filesystem/DB/external storage/registry/network/HTTP/
  activation/credential/token counts fixed at zero.

### Boundaries

- No actual filesystem, database, cloud, or external-storage persistence.
- No runtime activation, runtime switch, production registry write, credential, or token handling.

## v0.18.0 - Unreleased

### Added

- Immutable runtime-authorization request, review, approval, decision, and test-only commit record.
- Pure deterministic evaluator with exact v0.14–v0.17 source, v0.15 persistence/activation-plan,
  registry-state, lifecycle, role, replay, and UTC-microsecond temporal gates.
- Atomic append-only in-memory authorization ledger with monotonic generation, predecessor binding,
  failed-attempt retry, successful replay rejection, and Security E2E coverage.

### Security boundary

- `ready_for_runtime_authorization_commit` and `authorization_committed` are not runtime active.
- No activation API/switch, production-registry write, real persistence, transport/HTTP,
  credential/token generation, production profile, real product/data, external API/cloud/private LAN.
- CLI exit codes and report top-level schema remain unchanged.

## v0.17.0 - Unreleased

### Added

- Immutable production-equivalence assessment request, code-defined criteria, metadata-only
  evidence descriptor, environment/configuration/behavior contracts, review, and approval.
- Pure deterministic evaluator with exact v0.16 source binding, six-role separation, explicit UTC
  microsecond time, fail-closed gap priority, and zero external side effects.
- Test-only atomic attestation/replay ledger with failed-attempt retry and successful-chain replay
  rejection across request, assessment, descriptor, review, approval, and manual source approval.
- Digest-covered v0.14 boundary and v0.15 candidate propagation plus Security E2E and release
  contract coverage.

### Security boundary

- Synthetic/manual approval or a production-equivalent enum claim is never sufficient.
- Readiness metadata is a contract-fixture claim, not real-world product compatibility evidence.
- No real-product validation/connection, runtime activation, filesystem/DB persistence,
  production-registry write, transport/HTTP, external API, credential, token, or real document.
- CLI exit codes and the report top-level schema remain unchanged.

## v0.16.0 - Unreleased

### Added

- Immutable manual-validation execution request, safe-fixture manifest, offline environment,
  execution record, execution evidence, independent review, and approval contracts.
- Deterministic test-only execution harness with exact required-case enforcement, explicit time,
  atomic candidate-state commit, failed-attempt retry, and successful-chain replay protection.
- Digest-covered v0.16 execution/evidence/review/approval binding at the v0.14 production boundary.
- Security E2E and release-contract coverage for fail-closed denial and zero external side effects.

### Security boundary

- Synthetic or controlled offline execution is not production-equivalent or real-product evidence.
- An `approved` claim without the exact v0.16 digest chain does not satisfy manual validation.
- No runtime activation, filesystem/DB persistence, production-registry write, transport/HTTP,
  external API, credential, real document, or real-product connection was added or performed.
- CLI exit codes `0 / 1 / 2 / 3` and the report top-level schema remain unchanged.

## Unreleased

### v0.15.0 persistence / authorization activation boundary

- Added immutable persistence-policy and persisted-authorization record contracts.
- Added canonical integrity chaining across candidate, policy, generation, and predecessor digest.
- Added a test-only atomic in-memory persistence store with failure-safe retry, replay rejection,
  and store-issued immutable commit receipts bound to the resulting state digest.
- Added an immutable activation request, pure deterministic evaluator, replay ledger, and
  `ActivationCommitPlan` boundary; activation evaluation now requires exact record/receipt/approved
  policy/current-snapshot binding instead of a self-declared persistence-verification boolean.
- Added exact identity, digest, registry snapshot, lifecycle, replacement, temporal, role, and
  evidence-expiry checks with zero external/runtime side effects.
- Added v0.15 Security E2E, documentation, and release-contract coverage.
- CLI exit codes `0 / 1 / 2 / 3` remain unchanged; the report top-level schema remains unchanged.
- No runtime activation, filesystem/DB persistence, production-registry write, manual validation,
  token/credential generation, transport, HTTP, or real-product connection was added.

### v0.14.0 production authorization boundary

- Added immutable exact-source production-boundary evidence with explicit readiness, role,
  temporal, registry-snapshot, and digest-chain fields.
- Added a pure deterministic evaluator that returns only ineligible, missing-boundary, or
  authorization-review-candidate states; it cannot activate production.
- Added fail-closed gates for inactive sources, stale/expired evidence, reuse, unresolved
  revalidation, pending lifecycle actions, implicit resolution, role conflict, and tampering.
- Added typed persistence requirements without filesystem/database persistence and Security E2E
  requiring zero write/mutation/transport/HTTP/persistence/activation counts on every denial.
- Preserved CLI/report compatibility and added no workflow or Node runtime warning change.
- Bound canonical approval metadata and validation/review/approval identities through the
  admission decision, accepted entry, replacement successor, and v0.14 source evaluation.

### v0.13.0 replacement admission chain

- Added immutable replacement request, decision, successor-entry, link-event, and safe-result
  contracts with separate deterministic SHA-256 canonical digests.
- Added a pure fail-closed evaluator requiring an exact suspended/deprecated predecessor and a
  fresh evidence, review, approval, and admission chain. Revoked remains terminal.
- Added test-only atomic successor admission without predecessor mutation, plus duplicate, replay,
  chain-reuse, successor-collision, and loop protection.
- Added exact old/new resolution without current/latest aliases, fallback, nearest-version
  selection, schema inference, or automatic predecessor hiding.
- Added full-chain synthetic Security E2E and failure injection requiring unchanged state and zero
  write/mutation/event/transport/HTTP side effects on denial or commit failure.
- Added no production-registry write, persistence, runtime authorization, manual validation,
  real-product connection, credential, real document, transport, HTTP, workflow, or Node runtime
  warning change.

### v0.12.0 registry lifecycle governance

- Added immutable revalidation trigger/requirement and registry lifecycle request/result/event
  contracts with separate SHA-256 canonical digests and UTC six-digit-microsecond timestamps.
- Added a pure deterministic requirement evaluator for evidence/approval invalidation, security
  changes, version/restriction supersession, scheduled revalidation, and administrator actions.
- Added exact entry/admission/evidence identity and digest binding, explicit temporal gates, and
  lifecycle-administrator separation from validation operator, evidence reviewer, and approver.
- Added test-only atomic lifecycle transitions for the six allowed forward status changes. Revoked
  is terminal; active recovery, rollback, no-op writes, fallback, nearest-version selection, and
  schema inference are rejected.
- Added full-chain synthetic Security E2E and atomic denial checks requiring zero lifecycle
  mutation/event/write/transport/HTTP counts and unchanged entry state.
- Added no production registry write, persistence, runtime authorization, transport, HTTP,
  production profile, real entry, manual validation, real-product connection, credential, real
  document, external/private-LAN access, workflow, or Node runtime warning change.

### v0.11.0 production admission

The v0.11 production admission design and Phase A-E contracts are prepared for release as follows:

- Prepared the Phase F documentation, release checklist, release-note draft, and release contract
  tests without creating a tag or GitHub Release.
- Kept the existing Python 3.11/3.12 full-pytest workflow: it already includes every Phase A-E,
  approval, compatibility, profile-integration, and HTTP-security suite, so no duplicate targeted
  workflow step was added.
- Preserved public CLI exit codes `0` / `1` / `2` / `3`, report top-level schemas, the v0.9
  Compatibility Profile path, v0.10 approval enforcement, and synthetic/in-memory/loopback paths.
- Documented that synthetic safe fixtures are not real-product compatibility evidence and that
  successful test-registry admission is not a production entry or runtime authorization.

- Added Phase E immutable `RegistryAdmissionRequest`, `RegistryAdmissionEntry`,
  `RegistryAdmissionResult`, safe summaries, deterministic reason categories, and
  `enforce_registry_admission()` over the exact Phase C decision.
- Added fail-closed decision/digest/identity/time/role/restriction/status gates and atomic
  validate-construct-commit behavior. Every denial returns no entry and leaves write/event counts
  unchanged.
- Bound validated reviewer and validation-operator identities into the Phase C canonical decision
  digest. Phase E now compares request roles and exact profile/protocol/product identities directly
  with those decision-bound fields, rejects safe-summary divergence, and separates the registry
  administrator from the actual approver, reviewer, and operator.
- Added the explicit test-only `TestRegistryAdmissionStore` with exact profile, product, and
  protocol resolution. Production registry instances, duplicate/overwrite, inactive identities,
  fallback, nearest-version selection, and schema inference are rejected.
- Added Phase A-E synthetic security E2E without filesystem/network/subprocess, hidden clock,
  random/UUID generation, transport, HTTP, persistence, production profile/entry, credential,
  real document, manual-validation execution, or runtime integration.
- Added the Phase D immutable `ManualEvidenceImportRequest`,
  `ManualEvidenceImportResult`, typed safe errors, and pure
  `import_manual_validation_evidence()` boundary for explicitly supplied
  `inline_safe_fixture` mappings only.
- Added exact unknown/missing-field rejection, bounded input and field sizes, all 22 required case
  fixtures, structural safe-content allowlists, environment-digest verification, exact Phase A
  plan binding, and UTC six-digit-microsecond canonical source/result digests.
- Constructed imported evidence only through the public Phase B contract and regenerated its
  canonical evidence digest. Import success is neither manual-validation execution, evidence
  approval, registry admission, nor runtime authorization.
- Added no file/stdin/clipboard import, filesystem/network/subprocess/environment discovery,
  registry read/write, persistence, transport, product connection, credential, real document,
  production profile/entry, hidden clock, random value, UUID, CLI/config, or workflow path.
- Added the Phase C immutable `ReviewerAttestation`, `ProductionAdmissionRequest`, and
  `ProductionAdmissionDecision` contracts plus a deterministic pure admission evaluator.
- Added exact plan/evidence/synthetic-reference/approval/validation identity, explicit-time
  freshness, `manually_validated` maturity, role separation, restriction, supported-version, and
  revalidation gates with bounded safe reason categories and canonical SHA-256 results.
- Kept admission evaluation separate from registry mutation and runtime authorization. It creates
  no registry entry, persistence, transport, network/filesystem I/O, product connection, hidden
  clock, random value, UUID, credential, or real-data operation.
- Added the Phase B immutable `ManualValidationEvidence` contract with exact Phase A plan binding,
  strict planned/observed product identity, explicit execution/freshness times, and all 22 required
  case results.
- Added safe environment fingerprints, typed passed/failed/aborted outcomes, complete close/cleanup
  and non-disclosure evidence, bounded failure summaries, explicit expiry evaluation, canonical
  SHA-256 evidence identity, and non-disclosing summaries/errors.
- Kept evidence construction synthetic-fixture-only and communication-free. It performs no manual
  validation, approval, admission, runtime authorization, transport creation, registry write,
  I/O, network/filesystem access, credential handling, or real-product/data operation.
- Added the Phase A immutable `ManualValidationPlan` contract with strict exact SemanticVersion
  fields, explicit timezone-aware execution windows, role separation, and complete deterministic
  case, abort, and cleanup allowlists.
- Added safe loopback boundary declarations, synthetic-only data and credential-prohibited
  contracts, exact synthetic-evidence identity binding, SHA-256 canonical digests, bounded safe
  summaries, typed non-disclosing errors, and focused contract coverage.
- Kept plan creation communication-free: it performs no validation, approval, admission, registry
  write, transport creation, I/O, network/filesystem access, or real-product/data operation.
- Designed the explicit candidate, synthetic, manual-plan, manual-execution, evidence-review,
  approval-decision, production-admission, lifecycle, and revalidation states.
- Defined immutable manual-validation plan and evidence schemas, the complete required manual case
  allowlist, exact synthetic/manual evidence separation, bounded safe fingerprints, freshness and
  expiration, role separation, decision rules, restrictions, and minimum admission evidence.
- Defined fail-closed revalidation triggers, registry admission rules, failure handling, the Phase
  A-F implementation roadmap, unresolved questions, and the approval checklist required before any
  separately approved real-product validation session.
- Added design contract tests without runtime, transport, HTTP client, CLI/config, workflow,
  production profile/entry, persistence, product connection, credential, real document, fixture,
  tag, Release, or Vault changes.

### v0.10.0 production profile governance

- Prepared the Phase A-F documentation, CI verification contract, and post-merge release checklist
  without creating a tag, GitHub Release, or public version artifact.
- Documented the supported operational surface and separated README overview, usage guidance,
  design rationale, roadmap status, and release-operator responsibilities.
- Confirmed the existing Python 3.11/3.12 workflow runs the full suite, approval/security coverage,
  compatibility integration, HTTP security, CLI help, and benchmark exit-code gates; no duplicate
  workflow step was added.
- Preserved the synthetic-only, fail-closed boundary: no production profile or real registry entry,
  persistence, manual validation, real-product connection, credential, real document,
  external/private-LAN access, fallback, nearest-version selection, or schema inference.

- Completed Phase E with an immutable bounded approval-enforcement contract and safe result over
  exact profile/version, explicit evaluation time, explicit test registry, runtime capabilities,
  execution constraints, top-k, and optional fields.
- Integrated enforcement after compatibility-profile resolution and before transport creation,
  with denial-before-transport, zero HTTP requests on denial, and exactly one close after each
  post-transport success or failure.
- Added fail-closed enforcement for registry kind/status, maturity, decision, expiration,
  revalidation, supported product/minor versions, approved capabilities, protocol/score/source
  consistency, and restrictions without discovery, fallback, nearest-version choice, implicit
  top-k reduction, field removal, or capability downgrade.
- Added synthetic loopback security E2E covering exact and restricted approval, inactive/expired
  entries, safe errors, deterministic time, lifecycle order, report non-disclosure, and existing
  PASS/WARNING/FAIL/CLI-error behavior.
- Added no production profile/entry or registry write, persistence, manual validation,
  real-product connection, credential, public production CLI/config, fixture, report-schema,
  workflow, tag, Release, or Vault change.
- Completed Phase D with an immutable deterministic synthetic approval workflow spanning evidence
  generation, validation report/decision, approval metadata, eligibility, test-registry
  registration, exact resolution, safe result, and bounded events.
- Added an in-code all-pass builder for the full Phase B synthetic case allowlist with explicit
  timestamps and no hidden clock, UUID, randomness, sleep, I/O, network, filesystem, or raw data.
- Added fail-closed workflow coverage for stage ordering, partial results, required evidence,
  unsafe capability/policy results, role/identity consistency, expiration, revalidation,
  restrictions, registry separation, unsupported versions, and inactive states.
- Evaluated and rejected production admission for synthetic evidence while permitting exact
  resolution only in an explicit test registry; added no production profile/entry, production
  registry write, persistence, CLI/config, fixture, report format, workflow, tag, or Release.
- Completed Phase C with immutable trusted-registry entries, explicit production/test registry
  kinds, fail-closed registration eligibility, and exact profile/version resolution.
- Added explicit register, contains, bounded-summary, suspend, deprecate, and revoke operations
  with immutable snapshots and allowlisted safe lifecycle events.
- Added bounded registry error categories and contract coverage for approval/validation identity,
  maturity, decisions, capabilities, policies, expiration, revalidation, restrictions, registry
  separation, duplicate/overwrite rejection, exact resolution, and terminal revocation.
- Added no profile discovery, nearest-version selection, profile/version fallback, reactivation,
  rollback, automatic registry conversion, persistence, production profile/entry, CLI/config,
  manual validation, product connection, fixture, workflow, tag, or Release.
- Completed Phase B with immutable validation case/report models, explicit synthetic/manual
  required case sets, deterministic approval decision evaluation, and bounded safe summaries.
- Added fail-closed validation for case identity/outcomes, required evidence, timestamps,
  environments, profile/version and approval-record identity, capabilities, score/source policy,
  transport/cleanup/non-disclosure results, exact product versions, expiration, and revalidation.
- Added explicit approved, approved-with-restrictions, rejected, and needs-revalidation outcomes
  without automatic promotion, decision repair, nearest-version selection, or fallback.
- Kept production registry, registry admission, production profiles, report files, CLI/config,
  manual validation execution, product connectivity, fixtures, workflow, tag, and Release
  unimplemented.
- Completed Phase A with immutable profile maturity, approval decision, approval/validation
  metadata, supported product-version range, bounded restriction, and safe summary contracts.
- Added an explicit maturity transition allowlist and fail-closed approval consistency checks for
  identity, manual validation, required capabilities, score/source policy, expiration,
  revalidation, and exact supported versions.
- Added bounded governance error categories and contract tests without retaining raw endpoint,
  credential, query, response, path, reviewer, approver, or rejected values.
- Kept production profiles, trusted production registry/admission, real-product/manual validation
  execution, CLI/config integration, fixtures, workflow, tag, and Release unimplemented.
- Started a documentation-only governance design before any production Compatibility Profile is
  implemented or admitted to a trusted registry.
- Defined explicit maturity states from draft through synthetic/manual validation, approval,
  deprecation, and revocation, with no direct draft approval or automatic promotion.
- Separated profile author, reviewer, approver, validation operator, and release operator duties.
- Defined approval evidence for schema, synthetic harness, security E2E, capabilities, mappings,
  score/source policy, timeout/size limits, non-disclosure, and manual validation.
- Designed a separately approved, isolated, loopback-only, credential-free, synthetic-only manual
  product validation gate with immediate stop and bounded safe summaries.
- Defined approval decisions, explicit restrictions, revalidation triggers, revocation/rollback
  behavior, immutable production registry governance, CI boundaries, and safe CLI error categories.
- Planned v0.10 Phase A-F while keeping real-product validation outside the implementation phases.
- Added no production profile/config, real-product connection, credential, real endpoint, real
  document, source/test/fixture/config/workflow change, tag, or Release.

### v0.9 Local RAG compatibility design

- Completed Phase A with a typed Compatibility Profile and strict profile/protocol version
  contract.
- Added bounded ASCII profile identifiers, relative HTTP path validation, explicit immutable field
  mappings, allowlisted score semantics/source policy, and explicit boolean feature flags.
- Added exact profile resolution with no fallback, fail-closed major handling, explicit minor
  allowlists, patch compatibility within accepted minors, and no prerelease/build version support.
- Added safe compatibility error categories and contract coverage without endpoint, rejected value,
  path, credential, raw profile, communication, filesystem access, or product integration.
- Kept mapping execution and health/capability communication for later phases.
- Completed Phase B with immutable health, capabilities, and safe compatibility-result models.
- Added exact health schema, status, service-availability, and profile protocol compatibility
  validation with no fallback or raw-value disclosure.
- Added five required retrieval capabilities plus allowlisted optional capability negotiation tied
  to profile score semantics and feature flags, with no implicit downgrade.
- Added bounded health/capability error categories and contract tests while retaining no raw
  response, endpoint, path, product identity, credential, or protocol value in safe summaries.
- Kept HTTP communication, bounded-client integration, request/response mapping execution,
  CLI/config integration, fixtures, config, and workflow unchanged.
- Completed Phase C with typed bounded standard requests and explicit immutable flat request
  mapping execution.
- Added product-response mapping to existing ranked results with fail-closed required fields,
  safe identifiers, rank continuity, duplicate IDs, top-k, allowlisted metadata, and score
  semantics checks.
- Added negotiated optional-field enforcement, unscored handling without product score inference,
  and no score inversion or normalization.
- Added bounded request/response mapping error categories and safe mapping summaries without query,
  payload, endpoint, path, credential, product value, or raw exception disclosure.
- Kept synthetic harness execution, CLI/config and transport integration, HTTP communication,
  fixtures, config, workflow, real-product access, and real documents unimplemented.
- Completed Phase D with a deterministic no-I/O synthetic compatibility harness that directly
  composes the Phase A-C production contracts.
- Added immutable safe harness results containing compatibility status, enabled optional
  capabilities, mapping/result counts, score semantics, and normalized ranked results without raw
  input retention or sensitive-value rendering.
- Added complete-path and fail-closed harness coverage for profile/version, health, capabilities,
  request/response mappings, score semantics, identifiers, ranks, duplicates, top-k, malformed
  responses, and query-ID echo.
- Kept CLI/config and HTTP integration, product adapters, fixtures, config, workflow, network,
  filesystem, credentials, real products, and real documents unchanged and unimplemented.
- Completed Phase E by integrating explicit compatibility-profile selection with bounded
  `loopback_http` health, capabilities, request mapping, retrieval, and response mapping.
- Added one trusted product-neutral synthetic profile registry with exact selection and no
  discovery, nearest-version choice, schema inference, or fallback.
- Added synthetic fake-loopback security E2E coverage for JSON/YAML configuration, deterministic
  lifecycle order, PASS/WARNING/FAIL, CLI error `3`, and sensitive-value non-disclosure.
- Preserved the existing evaluator, report top-level keys, synthetic default, `in_memory` behavior,
  fixtures, workflow, and exit codes. Real-product compatibility remains unverified.
- Completed Phase F documentation, release preparation, and a dedicated compatibility profile
  integration E2E CI step while preserving the Python 3.11/3.12 matrix and existing checks.
- Documented that production profiles/configuration, real-product compatibility, credentials,
  automatic fallback, nearest-version selection, and schema inference remain unsupported.

Phase delivery:

- PR #45: designed the product-neutral v0.9 compatibility boundary.
- PR #46 / Phase A: added the compatibility profile and version contract.
- PR #47 / Phase B: added health and capabilities contracts.
- PR #48 / Phase C: added explicit request and response mapping contracts.
- PR #49 / Phase D: added the deterministic synthetic compatibility harness.
- PR #50 / Phase E: integrated explicit profiles with bounded loopback transport and security E2E.
- Phase F: finalized docs, CI coverage, changelog, and the v0.9.0 release checklist.

- Started a product-neutral compatibility design before any real Local RAG product connection.
- Isolated product-specific versions, health/capability shapes, field mappings, score semantics, and
  source-identifier policy in an explicit Compatibility Profile.
- Defined fail-closed profile and protocol version handling with no auto-discovery, schema guessing,
  best-effort downgrade, or fallback profile.
- Defined bounded health and capability negotiation before retrieval.
- Defined explicit standard request/response mapping while excluding document bodies, embeddings,
  real paths, credentials, raw metadata, and unsafe source identifiers.
- Defined compatibility error categories that preserve the existing adapter, benchmark, and CLI
  error `3` boundary without sensitive-value disclosure.
- Planned a synthetic compatibility harness for profile, version, capability, mapping, score,
  identifier, size, and malformed-response cases.
- Separated any future real-product validation into an explicitly approved loopback-only manual
  gate using synthetic queries, no credentials or real data, no raw-response persistence, and no
  fallback connection.
- Kept this change documentation-only. No source, tests, fixtures, config, workflow, communication,
  filesystem access, product adapter, tag, or Release was added.

### v0.8 secure Local RAG transport design

Phase delivery:

- PR #38: designed the loopback-only transport security boundary.
- PR #39 / Phase A: added endpoint, request, response, size, and error contracts.
- PR #40 / Phase B: added fake loopback server contract tests.
- PR #41 / Phase C: added the bounded one-request loopback HTTP client.
- PR #42 / Phase D: integrated explicit CLI/config selection for `loopback_http`.
- PR #43 / Phase E: added synthetic HTTP security E2E coverage.

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
- Completed Phase C with a bounded one-request loopback HTTP client using the Phase A contracts.
- Added immediate hostname re-resolution, complete loopback-set validation, deterministic IP-literal
  connection, actual peer verification, bounded POST/read, total deadline checks, and guaranteed
  connection cleanup.
- Added production-client coverage for IPv4 and optional IPv6, mixed/private/external resolution,
  peer mismatch, redirects, proxy isolation, refusal, connect/read/total timeout, exact and
  limit-plus-one sizes, invalid responses, no retry, cleanup, and sensitive-value non-disclosure.
- Kept HTTP selection unavailable from CLI/config and added no real Local RAG integration, redirect
  following, proxy use, retries, filesystem retrieval, fixture changes, or workflow changes.
- Completed Phase D by adding the explicit `loopback_http` local-rag transport selector and bounded
  endpoint/timeout/top-k/response-size/capability configuration mapping.
- Integrated `LocalRAGRetrievalAdapter` with a one-shot HTTP lifecycle wrapper that delegates all
  communication to `BoundedLoopbackHTTPClient` and closes after success or failure.
- Added synthetic loopback CLI/config coverage for PASS `0`, WARNING `1`, FAIL `2`, CLI error `3`,
  redirect and invalid-response rejection, refusal, timeout, size limits, mixed resolution, proxy
  isolation, no retry, safe reports, and non-disclosure.
- Preserved Synthetic as the default, the existing `in_memory` behavior, report top-level keys,
  benchmark exit codes, fixtures, and workflow. No real Local RAG or real-document connection was
  added.
- Completed Phase E with a dedicated synthetic HTTP security E2E suite from CLI and bounded
  JSON/YAML config through the local adapter, loopback transport/client, fake server, evaluator,
  reports, and exit codes.
- Added CLI-boundary coverage for PASS `0`, WARNING `1`, FAIL `2`, CLI error `3`, unsafe config and
  endpoints, redirect/refusal/timeout/peer failures, malformed or oversized responses, deterministic
  results, one attempt, guaranteed close, report compatibility, and sensitive-value non-disclosure.
- Kept all verification on ephemeral synthetic loopback servers with no fixture, workflow,
  production implementation, real Local RAG, real-document, filesystem, or external-network change.
- Completed Phase F documentation, a dedicated HTTP security E2E CI step, and the v0.8.0 release
  checklist while preserving the Python 3.11/3.12 matrix and existing checks.
- Kept real Local RAG products, real documents, external/private-LAN communication, redirects,
  proxies, retries, credentials, and filesystem retrieval unsupported and unverified.

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
