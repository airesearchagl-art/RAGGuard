# RAGGuard v0.19 Real Persistence Boundary

## Scope

v0.19 defines the immutable authorization, intent, transaction, receipt, and recovery contracts
that must surround a future durable write. Despite its name, v0.19 does not implement real persistence.
A filesystem, database, cloud, or external-storage adapter requires separate design and approval.
Runtime activation and production-registry mutation remain separate phases.

The source is one exact `RuntimeAuthorizationCommitRecord` from v0.18. The contract recomputes and
binds its authorization request, review, approval, source candidate, equivalence approval, policy,
generation, predecessor, and current store-state digests. `current`/`latest` aliases, fallback,
inferred generation, omitted source digests, revoked sources, replacement predecessors, pending
revalidation, and pending lifecycle transitions fail closed.

## Contract sequence

1. `PersistenceAuthorizationRequest` binds the complete source and expected CAS state.
2. An independent `PersistenceAuthorizationReview` precedes a distinct approval.
3. `PersistenceIntent` declares an enum-only target store class and digest-only content.
4. `PersistenceTransactionPlan` fixes before/after state, generation, predecessor, payload, commit
   protocol, and recovery protocol without paths, DSNs, endpoints, credentials, or connections.
5. The pure evaluator returns only `ineligible`, `needs_persistence_authorization`,
   `needs_transaction_plan`, or `ready_for_durable_commit`.
6. The test-only in-memory simulator builds one immutable candidate state and performs one swap.
7. A successful swap alone produces `PersistenceCommitReceiptV2`.
8. Recovery classifies state as `no_commit_detected`, `committed_and_consistent`,
   `incomplete_or_ambiguous`, or `corruption_detected`.

Persistence authorization is not a completed write. A committed receipt is not runtime active and
does not mutate a registry. Recovery never reissues authorization, continues an ambiguous commit,
activates a runtime, or changes a registry entry to ACTIVE.

## Atomicity, replay, and recovery

The simulator uses compare-and-swap semantics with monotonic generation and exact predecessor
binding. Candidate content, receipt, counters, events, and successful-only replay sets are assembled
before one state replacement. Validation failure, receipt construction failure, counter failure,
and crash injection before swap leave the entire state unchanged and permit retry. A successful
request, intent, plan, or receipt cannot be replayed.

Recovery compares the receipt with the immutable snapshot. Content, before/after state,
predecessor, generation, receipt, authorization record, intent, and plan disagreement is corruption.
Missing one side is ambiguous and never triggers an automatic commit. Generation rollback,
impossible jumps, forged records, and forged recovery metadata fail closed.

## Roles, time, and side effects

The digest-covered runtime authorization approver identity, persistence requester, reviewer,
approver, and operator are distinct. Recovery operator and reviewer are also distinct. Safe
summaries contain only opaque IDs, canonical digests, enum state, generation, and canonical UTC
timestamps; they are not an alternative source of authority. All times are explicit timezone-aware
inputs, normalized to UTC with fixed six-digit microseconds; no hidden clock or random identifier is
used. Future metadata and authorization older than the configured maximum age are rejected.

All v0.19 decision, commit, recovery, and Security E2E paths report zero filesystem, database,
external-storage, registry, network, HTTP, runtime-activation, credential-use, and token-generation
side effects. `ready_for_durable_commit`, `committed`, and `committed_and_consistent` are contract
states only.
