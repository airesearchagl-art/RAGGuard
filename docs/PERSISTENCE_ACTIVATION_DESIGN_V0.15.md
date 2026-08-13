# RAGGuard v0.15 Persistence / Authorization Activation Boundary

## Scope

v0.15 defines the contract between a v0.14 `ProductionAuthorizationCandidate`, a durable
authorization record, and a future activation commit. It does not activate a runtime. Persistence
semantics are represented only by a test-only in-memory store; no filesystem, database, external
storage, production-registry write, transport, HTTP, credential, token, or runtime switch exists.

`ready_for_activation_commit != active`. An accepted request produces an immutable
`ActivationCommitPlan`; it does not produce `active`, `activated`, `production_enabled`, or
`authorized_runtime`. No runtime activation API is defined.

## Persistence contract

`PersistencePolicy` is immutable typed metadata. Approval requires append-only durability,
tamper evidence, backup, restore verification, audit retention, explicit no-automatic-rollback,
secret separation, and operator separation. Its canonical digest is part of the persisted chain.

`PersistedAuthorizationRecord` binds exactly to:

- the source v0.14 candidate digest;
- the source boundary-evidence digest;
- the admission-decision and accepted registry-entry digests;
- the exact registry-state digest and lifecycle status;
- an optional explicit replacement-decision digest;
- the persistence-policy digest;
- the generation and previous-record digest;
- the explicit UTC persistence time and opaque persistence operator.

There is no current/latest alias, fallback, predecessor inference, or successor inference.
Generation starts at one, increases monotonically, and binds to the exact previous record. A
record ID and source candidate may each be committed only once.

## Canonical integrity

Canonical JSON uses sorted keys, compact separators, ASCII-safe output, SHA-256, and
`sha256:<64 lowercase hex>`. Aware timestamps normalize to UTC with fixed six-digit microsecond
precision. Equivalent instants have identical canonical values; a one-microsecond change changes
the digest.

The integrity digest covers the previous record digest, generation, source candidate digest, and
persistence-policy digest. The record canonical digest additionally covers the complete exact
source binding and safe persistence metadata.

## Atomic test-only store

`InMemoryPersistenceStore` is a test-only in-memory semantic model. It never opens a file or uses a
database. It validates the complete request, creates candidate records, replay sets, counters,
store-state digest, and a store-issued immutable `PersistenceCommitReceipt`, then replaces one
immutable state bundle once. No lower-level mutation occurs before validation.

The receipt exists only after a successful commit and exactly binds the persisted record ID and
digest, approved policy digest, source-candidate digest, generation, predecessor digest, explicit
commit/evaluation time, and resulting store-state digest. Receipt construction and state update are
part of the same candidate-state/single-swap operation. Validation denial or injected commit failure
produces no receipt and leaves records, receipts, replay sets, counters, and state digest unchanged.

Candidate-state, record-append, counter, or pre-swap failure leaves records, generation, record
IDs, candidate digests, write count, and mutation count unchanged. A failed request does not
consume replay state and can be retried. A successful duplicate is rejected.

## Activation request and evaluator

`ActivationRequest` binds an opaque request ID and caller-supplied nonce digest to one exact
persisted-record digest and generation. It also binds the expected profile/product/protocol
versions, registry-state digest, active lifecycle status, explicit request time, requester,
reviewer, and source-bound authorization approver.

`evaluate_activation_request()` is pure. Its explicit inputs are the request, persisted record,
store-issued commit receipt, persistence policy, current store snapshot, source candidate, source
boundary evidence, exact registry snapshot, explicit evaluation time, and explicit replay sets. It
has no hidden clock and performs no I/O or mutation. A caller-supplied `persistence_verified`
boolean is neither accepted nor used as a decision gate.

The evaluator verifies:

- recomputed candidate, record, integrity, request, evidence, entry, and registry-state digests;
- exact identity, version, replacement-chain, generation, and lifecycle binding;
- active lifecycle, no pending revalidation or lifecycle transition, and unexpired evidence;
- `persisted_at <= receipt.committed_at == receipt.evaluated_at`;
- `receipt.evaluated_at <= activation_requested_at <= evaluation_time < evidence_expires_at`;
- exact record/receipt/policy/candidate, generation/predecessor, and current store-state binding;
- no current/latest alias, fallback, or inferred source;
- no request-ID, nonce, or persisted-record replay;
- manual-validation, approved persistence policy, security-review, and activation-review claims;
- requester/reviewer/approver separation and separation from the v0.14 source roles.

The caller-supplied nonce digest is never generated by RAGGuard. A readiness enum is a contract
fixture claim, not real-world evidence. Synthetic-only evidence cannot reach
`ready_for_activation_commit`.

## Deterministic priority

Results are ordered deterministically:

1. identity, digest, integrity, unsafe resolution, role, or temporal failure: `ineligible`;
2. inactive, stale, expired, replaced, or replayed source: `ineligible`;
3. missing real manual-validation approval: `needs_manual_validation`;
4. missing approved committed persistence evidence: `needs_persistence_verification`;
5. missing security/activation review: `needs_activation_review`;
6. every contract prerequisite satisfied: `ready_for_activation_commit`.

## Activation commit boundary

`ActivationCommitPlan` contains only the activation-request digest, persisted-record digest,
persistence-receipt digest, source-candidate digest, exact registry-state digest, expected
generation, explicit approval time, approver ID, and its canonical digest. There is no commit
executor and no side effect.

All evaluation paths keep registry write, mutation, transport, HTTP, filesystem, database,
persistence-write, and runtime-activation counts at zero. The in-memory replay ledger records only
a successful review-ready request; failed requests consume nothing and remain retryable.

## Security and disclosure boundary

Safe summaries contain only opaque IDs, digests, enums, generation, timestamps, reason categories,
and lifecycle status. They do not contain endpoints, hostnames, ports, paths, credentials, tokens,
cookies, API keys, usernames, raw HTTP, real documents, stack traces, or internal exceptions.

No manual validation was performed. No production profile, real production-registry entry,
filesystem/DB persistence, real-product compatibility evidence, real-product connection,
credential, real document, external/private-LAN access, or runtime authorization is added.
Node runtime warning maintenance is a separate PR.

## v0.17 equivalence integration

The v0.14 authorization candidate now includes the five v0.17 equivalence-chain digests when that
chain is present. The existing v0.15 source-candidate digest therefore covers equivalence evidence
without a new persistence field or write path. `ready_for_activation_commit` remains non-active,
and v0.17 adds no runtime activation or real persistence.
