# Runtime Authorization Activation Boundary v0.18

> v0.19 handoff: an immutable `RuntimeAuthorizationCommitRecord` is the exact source for a future
> durable-persistence contract. It is not proof that a durable write occurred or a runtime is active.

## Scope

v0.18 defines the final authorization contract that may produce a test-only immutable
authorization commit record. It does not activate, enable, or start a production runtime.
`ready_for_runtime_authorization_commit` and `authorization_committed` are not `active`.

No runtime switch, transport, HTTP client, production-registry write, filesystem/DB/external
storage, credential/token generation, production profile, real-product connection, or real-world
validation is implemented.

## Exact source binding

`RuntimeAuthorizationRequest` is immutable and digest-covers the exact v0.14 candidate and boundary
evidence, all v0.17 assessment/review/approval digests, v0.15 persisted record/receipt/snapshot,
the v0.15 activation request and commit plan, registry-state digest, lifecycle status, exact
profile/product/protocol versions, explicit UTC-microsecond request time, and runtime actors.

Aliases (`current`/`latest`), fallback, nearest-version behavior, inferred source identity, omitted
source digests, and hidden defaults fail closed. Enum or approval-ID claims cannot substitute for
canonical evidence.

## Deterministic evaluator

The pure evaluator applies this fixed priority:

1. identity/digest/tampering, unsafe resolution, lifecycle/replacement/staleness, temporal,
   role-conflict, and replay failures: `ineligible`;
2. incomplete v0.17 chain: `needs_equivalence_approval`;
3. uncommitted, stale, forged, or unapproved persistence evidence:
   `needs_persistence_verification`;
4. missing or mismatched activation plan: `needs_activation_commit_plan`;
5. missing, rejected, or mismatched independent runtime review/approval:
   `needs_runtime_authorization_review`;
6. all contract prerequisites: `ready_for_runtime_authorization_commit`.

The result vocabulary intentionally excludes `authorized`, `active`, `enabled`, and
`production_running`.

## Review, approval, roles, and time

Runtime review and approval are distinct immutable contracts. Ordering is explicit and
UTC-normalized with fixed six-digit microsecond precision:

`source chain <= persistence commit <= activation request <= activation plan <= runtime request
<= runtime review < runtime approval <= evaluation/authorization commit`.

Future metadata, stale or expired evidence, and hidden clocks are rejected. The validation
operator/reviewer/approver, equivalence assessor/reviewer/approver, persistence operator,
activation requester/reviewer/authorization approver, runtime requester/reviewer/approver, and
commit operator are separated. Self-approval is prohibited.

## Test-only authorization ledger

The in-memory ledger constructs a complete immutable candidate bundle and swaps state once only
after validation. A successful commit appends one `RuntimeAuthorizationCommitRecord`, increments a
monotonic generation, and binds its predecessor digest. Only successful commits consume request,
review, approval, candidate, equivalence-approval, persistence-receipt, and activation-plan replay
dimensions. Validation denial or injected commit fault leaves records, used sets, generations,
write/mutation/event counts, and all external-effect counts unchanged, so a corrected request may
retry. A successful duplicate is rejected.

The word `authorization` in the record name is an audit-contract label, not a capability, token,
credential, runtime state, or production permission.

## Security boundary

Safe summaries contain only opaque identifiers, digests, enums, generations, timestamps, and
reason codes. They exclude endpoint, hostname, IP, port, path, credential, token, cookie, username,
environment secret, raw request/response, real document, and stack trace. Denial and success paths
keep production-registry, persistence, filesystem, DB, network, transport, HTTP, runtime activation,
token, and credential counts at zero.
