# RAGGuard v0.16 Manual Validation Execution Boundary

## Scope

v0.16 defines how an exact immutable validation plan may produce reviewable execution evidence in
a deterministic test-only boundary. It does not perform production-equivalent validation, connect
to a real product, authorize runtime use, persist to filesystem/DB/external storage, or write a
production registry.

## Canonical chain

The only accepted order is:

`plan -> execution request -> fixture/environment -> execution record -> evidence -> review -> approval`

Every object is frozen and has sorted compact JSON, SHA-256 canonical identity, timezone-aware UTC
timestamps with fixed six-digit microsecond precision, and exact digest binding to its predecessor.
Equivalent instants have identical canonical values; distinct microsecond instants do not collide.
Current/latest aliases, fallback, nearest-version selection, inferred versions, hidden defaults,
and ID-only trust are prohibited.

## Fixture and environment boundary

The fixture manifest contains only opaque case IDs and digests. It asserts that real data and
network use are prohibited. The v0.16 environment requires `offline_required=true` and requires
network, filesystem writes, subprocess, external API, real data, and credentials to be disabled.
No raw fixture data, document, endpoint, hostname, IP, port, path, credential, token, cookie,
username, or stack trace is retained in a safe summary.

The readiness enums and safe fixture values are contract claims used to verify execution
semantics. They are not real-world or production-equivalent evidence.

## Execution and atomicity

The test-only harness requires an exact match between the plan required cases, manifest case set,
and supplied result set. A passed record requires every case to execute and pass. A missing,
failed, or skipped required case cannot be represented as passed.

The harness builds the complete candidate record and replay sets locally, then replaces one
immutable state bundle. Validation failure or an injected commit fault leaves records and used
request/execution/digest sets unchanged. A corrected failed request can be retried. A successful
request cannot be replayed.

## Evidence, review, approval, and roles

Execution evidence binds the exact record, plan, fixture, and environment digests. Review binds
the exact evidence digest. Approval binds both evidence and review digests. The required ordering
is:

`request <= start <= completion <= evidence <= review < approval <= evaluation_time`

Evidence freshness is at most 90 days. Future metadata, stale evidence, partial execution, digest
mismatch, and replay fail closed. Requester, execution operator, evidence creator, reviewer, and
approver are distinct. Operator/reviewer, reviewer/approver, operator/approver, evidence
creator/approver, and self-approval conflicts are rejected.

Only successfully validated and approved chains consume the test-only chain replay ledger.
Denial and commit failure keep registry write, mutation, persistence write, filesystem write, DB
write, network, HTTP, and activation counts at zero.

## v0.14 and v0.15 boundary

Production-boundary evidence canonically carries separate v0.16 execution-record, execution-
evidence, review, and approval digests. All four must be present together. A plain
`manual_validation_state=approved` claim does not satisfy the authorization-candidate evaluator.
A fully approved controlled chain may cross the manual-validation gate and proceed to the existing
security/persistence/runtime-boundary gates; it is still not production-equivalent evidence.

v0.15 remains unchanged: `ready_for_activation_commit != active`. v0.16 adds no activation API,
runtime switch, real persistence, production-registry write, transport, HTTP, credential/token,
production profile, real document, real-product connection, external API, cloud, or private-LAN
access. Node runtime warning maintenance is a separate PR.

## v0.17 handoff

An approved v0.16 chain remains controlled manual-validation evidence, not production-equivalent
evidence. v0.17 consumes the exact plan, fixture, environment, execution, evidence, review, and
approval digests as immutable source inputs to a separate assessment/review/approval boundary.
