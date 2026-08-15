# Real-Data Access Authorization Boundary v0.25

## Purpose

v0.25 converts an exact, live v0.24 `ApprovedRealDataTrialRecord` into a one-shot,
metadata-only real-data access authorization contract. It defines the final selector, policy,
review, operator-assignment, approval, generation, replay, usage-count, lifecycle, and readiness
gates needed before a future limited read executor can be reviewed. It does not locate, open, or
read a document. Actual read execution remains v0.26-or-later work.

The release boundary is explicit:

- trial approved != real-data access authorized
- access authorized != actual real-data read
- operator assigned != access authorized
- eligible_for_limited_real_data_read_execution != read executed
- read authorization != persistence authorization
- read authorization != runtime activation

There is no implicit production authority, fallback, or automatic activation.

## Metadata-only selector

`RealDataAccessSelector` contains only opaque identifiers, canonical digests, enums, and the
v0.24 trial binding. It has no path, filename, directory, host, endpoint, customer, company,
person, project, credential, token, raw identifier, or document content. The only accepted source
class is `approved_local_trial_source`; the safe document class is
`internal_low_document_candidate`.

The selector exact-binds the real v0.24 approved-trial record, classification policy, purpose,
safe stage ceiling, and access policy. Repeating caller-supplied digest claims does not substitute
for those objects.

## Access policy hard gates

`RealDataAccessPolicy` fixes the safe default to:

- data class: `internal_low` only;
- document class: `internal_low_document_candidate` only;
- maximum stage: `chunking_candidate`;
- maximum documents: one;
- maximum byte class: `small_document`;
- allowed read count: one;
- masking required before the chunking candidate stage;
- raw retention: none;
- raw logging: none;
- raw cache: none;
- persistence: none;
- export: prohibited;
- network: prohibited.

Embedding and every downstream stage remain prohibited. A wider data/document class, higher
stage, larger document count/byte class, additional read, or weaker retention/log/cache/export/
persistence/network rule fails closed.

## Object-backed source chain

Authorization revalidates the actual v0.24 objects:

1. `ApprovedRealDataTrialRecord`;
2. `RealDataTrialScope`;
3. classification, stage, retention, logging, cache, export, and persistence policies;
4. trial request, independent security review, independent governance review, and trial approval;
5. `EnvironmentApproval`;
6. `ApprovedLocalRAGExecutionSession`.

The approved trial must remain in
`approved_for_real_data_access_authorization_review` / `approved`, be canonical, unexpired,
unrevoked, and unsuperseded. All request, review, approval, environment, session, scope, and policy
digests are recomputed from their objects.

## Access authorization chain and roles

The v0.25 chain is:

1. metadata-only selector and safe access policy;
2. `RealDataAccessRequest`;
3. independent `RealDataAccessSecurityReview`;
4. separate `RealDataAccessGovernanceReview`;
5. explicit `RealDataOperatorAssignment`;
6. distinct `RealDataAccessApproval`;
7. test-only atomic `RealDataAccessAuthorizationRecord`;
8. immutable usage-count contract;
9. pure read-execution readiness evaluation.

Trial requester, trial approver, session operator, access requester, access security reviewer,
access governance reviewer, future real-data operator, and access approver are pairwise distinct.
Operator assignment is not access authorization. Self-review and self-approval fail closed.

## Registry, replay, generation, and usage

`TestOnlyRealDataAccessAuthorizationRegistry` is in-memory and test-only. It builds immutable
candidate state, verifies a monotonic generation and exact predecessor, and performs one atomic
swap. Only success consumes the access request, security review, governance review, operator
assignment, approval, and authorization-record replay identities. Review denial, approval denial,
validation failure, and injected faults consume nothing and permit retry.

Each successful authorization has `allowed_read_count = remaining_read_count = 1`. The associated
usage contract contains an opaque usage digest, not a caller token. v0.25 provides no decrement,
reset, refill, or consume method. Only a future v0.26-or-later executor contract may decrement the
counter after a successful actual read. Negative counts and arbitrary exhaustion claims are
invalid.

## Lifecycle and time

Lifecycle values are `authorized`, `expired`, `revoked`, `exhausted`, and `superseded`. Expired,
revoked, exhausted, and superseded records cannot be reused. There is no automatic reactivation,
refill, replacement fallback, or status-only bypass.

All time is caller-supplied, timezone-aware UTC and canonicalized with six microsecond digits. The
strict order is trial approval, approved trial record, access request, security review, governance
review, operator assignment, access approval, authorization record, readiness evaluation, and
evaluation time. Future metadata and expired trial, assignment, approval, or authorization
objects are rejected. No hidden clock or random identifier is used.

## Read execution readiness

The pure evaluator progresses through `needs_security_review`, `needs_governance_review`,
`needs_operator_assignment`, and `needs_access_approval`. Its maximum result is
`eligible_for_limited_real_data_read_execution`. That result routes metadata to a separate future
executor boundary; it is not evidence that a file was opened or read and is not persistence,
production-registry, or runtime-activation authority.

## Fixed zero-effects and compatibility contract

Every v0.25 Security E2E path keeps actual file opens, actual file reads, real-data access,
filesystem/database/persistent-vector writes, external network, HTTP, cloud, production-registry
writes, credential use, token use, runtime activation, and runtime switching at zero. No real
material root is scanned or accessed.

No CLI command or exit code changes. The report schema is unchanged. v0.10-v0.24 governance,
including the v0.23 execution-session/environment boundary and v0.24 trial-approval boundary,
remains intact.
