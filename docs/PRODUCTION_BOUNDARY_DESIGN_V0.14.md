# Production Boundary and Authorization Contract v0.14

## Scope

v0.14 defines a pure, product-neutral boundary between successful test-only governance chains and
a candidate that may be reviewed for future production authorization. It does not activate
production, issue a token, enable transport, write a production registry, or persist state.

`eligible_for_authorization_review` is neither `authorized` nor `active`.
No `ProductionAuthorizationActivation` API exists in v0.14.

## Evidence and readiness states

`ProductionBoundaryEvidence` binds an explicit registry entry and snapshot to exact profile,
product, protocol, plan, evidence, reviewer-attestation, approval, admission-decision, optional
replacement, and lifecycle state digests. It records only opaque actor IDs, typed states,
timezone-aware times, safe flags, and allowlisted context.

Readiness enums are explicit:

- manual validation: `not_performed`, `performed_pending_review`, `reviewed`, `approved`;
- compatibility: `synthetic_only`, `controlled_manual`, `production_equivalent`;
- persistence: `none`, `test_only`, `production_ready`;
- runtime authorization: `disabled`, `candidate_only`, `active`;
- security review: `not_reviewed`, `reviewed`, `approved`.

The repository contains no factual production-equivalent evidence, production-ready persistence,
or active runtime authorization. Typed fixture states test decision behavior only and are not
real-world readiness evidence.

## Deterministic decision priority

1. identity, digest, structural, security, role, or temporal violation: `ineligible`;
2. revoked, suspended, deprecated, or otherwise non-active source: `ineligible`;
3. stale/expired evidence, unresolved revalidation, pending lifecycle action, or chain reuse:
   `ineligible`;
4. missing approved manual validation or synthetic-only compatibility:
   `needs_manual_validation`;
5. missing approved security review: `needs_security_review`;
6. missing approved persistence boundary: `needs_persistence_boundary`;
7. missing candidate-only runtime boundary: `needs_runtime_authorization_boundary`;
8. all prerequisites: `eligible_for_authorization_review`.

An `active` runtime state is rejected, not returned as success. Candidate evaluation has no write,
mutation, persistence, activation, transport, or HTTP side effect.

## Exact binding and resolution

The caller supplies the exact source entry and exact registry snapshot digest. Replacement sources
must identify their accepted successor explicitly. Current/latest aliases, fallback,
nearest-version selection, inferred predecessor/successor, omitted digests, and schema inference
are rejected.

The source must be active. A suspended, deprecated, or revoked entry cannot be revived through this
boundary. Replacement does not erase or reactivate its predecessor.

## Role and temporal boundary

Validation operator, evidence reviewer, approver, registry administrator, boundary reviewer, and
authorization approver are six distinct opaque identities. Request-only summaries never override
these digest-covered fields.

All timestamps are explicit and timezone-aware. The chain order is:

`evidence completion <= review < approval <= admission <= replacement/lifecycle action <= boundary evaluation < evidence expiry`

Optional actions must occur before evaluation. Future metadata and expired evidence fail closed.
Canonical timestamps normalize to UTC with fixed six-digit microsecond precision; equivalent
instants match and one-microsecond differences remain distinct. No hidden clock, random value, or
UUID is used.

## Persistence boundary metadata

The typed metadata records whether durability, append-only audit, tamper evidence, backup/restore,
secret separation, and explicit rollback semantics are required and approved. It performs no
filesystem or database operation. Rollback cannot silently reactivate or replace an entry.

## Safety and compatibility

Safe summaries and errors exclude endpoint, port, path, hostname, username, credential, token,
cookie, API key, raw request/response, real document, and stack trace values. Canonical identities
use compact sorted-key JSON and `sha256:<64 lowercase hex>`.

CLI exit codes `0 / 1 / 2 / 3`, report top-level schemas, the v0.9 Compatibility Profile, v0.10
approval enforcement, v0.11 admission governance, v0.12 lifecycle governance, and v0.13
replacement governance remain unchanged.
Workflow and Node runtime warning maintenance are out of scope.
