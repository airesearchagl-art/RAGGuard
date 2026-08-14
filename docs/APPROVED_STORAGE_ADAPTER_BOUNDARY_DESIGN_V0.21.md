# Approved Actual Storage Adapter Boundary v0.21

## Purpose

v0.21 defines the metadata and governance boundary between the v0.19 durable-persistence
contracts and any future actual storage implementation. It does not implement an adapter that
opens, connects to, reads, or writes a filesystem, database, object store, network, or runtime.

The boundary is intentionally staged:

- candidate ≠ approved
- approved_for_write_authorization_review ≠ write_authorized
- write_authorized ≠ write_executed
- durable_write_completed ≠ runtime_active

## Contract chain

1. `StorageAdapterManifest` describes an opaque adapter candidate and contains no path, host, IP,
   port, DSN, bucket, account, URL, credential, token, or connection value.
2. `StorageAdapterCapability` covers ten explicit capability claims with a canonical digest.
3. `StorageAdapterAttestationEvidence` contains only metadata digests and explicit UTC time.
4. The pure evaluator returns only `failed`, `needs_more_evidence`, or
   `eligible_for_adapter_review`.
5. An independent `StorageAdapterReview` precedes a decision by a distinct
   `StorageAdapterApproval` approver.
6. A successful test-only atomic registry commit creates an immutable
   `ApprovedStorageAdapterRecord` in `approved_for_write_authorization_review` state.
7. The pure v0.19 compatibility evaluator can return only `incompatible`,
   `needs_adapter_approval`, or `ready_for_write_authorization_review`.

An approval object alone cannot perform or authorize a write.

## Exact binding and policy

Manifest, capabilities, evidence, conformance result, review, approval, policy, role context, and
approved record are canonical-digest bound. The v0.19 compatibility evaluator receives and
revalidates the actual `PersistenceAuthorizationRequest`, `PersistenceIntent`,
`PersistenceTransactionPlan`, `PersistenceCommitReceiptV2`, and
`RuntimeAuthorizationCommitRecord`; caller-supplied digests are never the trust anchor.

The safe policy defaults are `credential_mode=none`, `network_mode=disabled`, and
`filesystem_mode=simulated_only`. Unsupported transaction, durability, atomicity, recovery,
idempotency, credential, network, and filesystem claims fail closed. There is no automatic
fallback, no nearest-version selection, and no schema inference.

## Identity, time, replay, and lifecycle

Evidence producer, adapter reviewer, adapter approver, persistence requester, persistence
reviewer, persistence approver, persistence operator, and runtime authorization approver are eight
distinct opaque identities. Every evaluation time is explicit and timezone-aware. Canonical time
is normalized to UTC with fixed six-digit microsecond precision. Future, expired, or older-than-
90-day evidence is rejected.

Only a successful single-swap commit consumes manifest, evidence, review, approval, and record
digests. Denial and injected commit faults consume nothing and may be retried. Successful replay
is rejected. Lifecycle is one-way: approved may become deprecated, revoked, or superseded;
deprecated may become revoked or superseded; revoked and superseded are terminal. A superseded
record cannot authorize a new write and never triggers fallback or reactivation.

## Side-effect boundary

All conformance, compatibility, denial, and fault paths keep filesystem, database, external
storage, production-registry, network, HTTP, credential, token, runtime activation, runtime
switch, and real-data counters at zero. The registry is test-only in-memory metadata. Actual
adapter operation is not implemented.
