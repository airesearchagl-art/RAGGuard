# Replacement Admission Design v0.13

## Scope and boundary

v0.13 defines a deterministic replacement-admission chain for the in-memory test-only registry.
Replacement is not reactivation: a suspended or deprecated predecessor remains unchanged and a
freshly admitted active successor is created as a distinct entry. Revoked is terminal and active
entries are not replacement sources.

This contract performs no production-registry write, persistence, runtime production
authorization, transport, HTTP, manual validation, real-product connection, credential handling,
or real-document processing. Successful test-registry replacement is not runtime production
authorization.

It adds no CLI command. CLI exit codes `0` / `1` / `2` / `3` and report top-level schemas are
unchanged. Workflow and Node runtime warning maintenance remain a separate CI task.

## Fresh-chain and identity gates

A replacement request binds the exact predecessor entry and lifecycle event to a newly evaluated
production-admission request and decision. Fresh evidence is mandatory. The new plan, evidence,
reviewer attestation, and admission-decision digests must be distinct from the predecessor chain.
Evidence completion must postdate the predecessor admission, and the new chain must satisfy:

The predecessor production-admission request is re-evaluated and bound to the predecessor entry's
decision, plan, evidence, and attestation digests. Approval metadata receives a v0.13 canonical
digest so exact approval-record reuse is also rejected rather than inferred from a safe summary.

`evidence completion < review < approval <= admission decision <= replacement evaluation < expiry`

Profile continuity is exact. Product, protocol, version, or restriction changes require the
corresponding explicit enum reason. Aliases, fallback, latest/current selection, nearest-version
selection, schema inference, and silent identity or restriction migration are rejected.

Validation operator, evidence reviewer, approver, and registry administrator are compared using
decision-bound identities. The registry administrator must be distinct from every new-chain role.
Request-only safe summaries cannot substitute for canonical identity fields.

## Decision priority

The pure evaluator applies this deterministic priority:

1. security, identity, or digest violation: `rejected`;
2. ineligible predecessor status: `rejected`;
3. old/new chain reuse: `rejected`;
4. stale or expired evidence: `needs_revalidation`;
5. temporal or role violation: `rejected`;
6. restriction mismatch: `rejected`;
7. all gates satisfied: `eligible`.

All errors and results use bounded reason enums and safe summaries; raw input is not returned.

## Atomic replacement store

The test-only store constructs candidate successor entries, replacement events, counters, replay
sets, and committed request IDs before mutation. It then performs one immutable state-bundle
replacement. A failure at any candidate or pre-commit fault point leaves the predecessor,
snapshot, event list, counters, replay sets, and committed IDs unchanged. Failed requests can be
retried after the fault is removed; successfully committed requests cannot.

The predecessor remains exactly resolvable under its suspended or deprecated status. The active
successor is separately and exactly resolvable. The store never hides the predecessor or chooses a
current/latest entry automatically.

## Canonical identity

Requests, decisions, successor entries, events, and results use separate compact sorted-key JSON
SHA-256 digests in `sha256:<64 lowercase hex>` form. Timestamps normalize to UTC with fixed
six-digit microsecond precision. Equivalent instants produce the same canonical value and a
one-microsecond difference changes the digest. No hidden clock, random value, or UUID is used.
