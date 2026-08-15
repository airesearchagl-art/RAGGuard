# Explicit Real-Data Trial Approval Boundary v0.24

## Purpose

v0.24 converts the v0.23
`eligible_for_explicit_real_data_trial_approval_review` result into an explicit, independently
reviewed trial-approval record. It remains a metadata-only authorization-review boundary. It does
not open, locate, read, execute, export, persist, log, or cache real material.

- trial review eligible != trial approved
- trial approved != real-data access authorized
- approved trial != actual real-data read
- real-data access review eligible != real-data use authorized

Explicit real-data access authorization is a later boundary. Actual read and write authorization
remain separate later work.

## Scope and policy boundary

`RealDataTrialScope` exact-binds the v0.23 approved session, environment approval, controlled
execution receipt, integration manifest, and seven policy objects. It contains only opaque
identifiers, canonical digests, enums, and UTC timestamps. It has no path, filename, customer,
person, project, host, endpoint, credential, token, connection string, or raw-document field.

The classification policy permits only `internal_low` by default. `personal_data`,
`credential_like`, and `highly_restricted` are prohibited. Restricted and contractual classes
require masking policy evidence before any future expansion. Export is prohibited for every class.

The stage policy partitions all eleven v0.22 stages and caps the candidate at
`chunking_candidate`. Embedding, vector write, retrieval, prompt construction, LLM input,
response, and logging/cache are prohibited. This is a policy contract only; v0.24 has no execution
method.

Retention is `none` for raw input, transformed content, embedding, retrieval, prompt, response,
log, and cache. Logging is digest-and-reason only with raw content disabled. Cache, export, and
persistence are disabled. No persistent Vector DB or actual filesystem/database write exists.

## Approval chain

The chain is:

1. exact v0.23 readiness and its actual environment, session, execution receipt, post-execution
   review, and post-execution approval objects;
2. immutable trial scope and policies;
3. metadata-only `TrialApprovalRequest`;
4. independent `TrialSecurityReview`;
5. independent `TrialDataGovernanceReview`;
6. distinct `TrialApproval`;
7. test-only atomic `ApprovedRealDataTrialRecord`.

Caller-supplied digest strings do not replace actual v0.23 objects. Every canonical object and
binding is recomputed. Forged readiness, session, environment approval, execution evidence,
scope, review, approval, or role context fails closed.

The requester, session operator, environment approver, security reviewer, governance reviewer,
and trial approver are independent. The future real-data operator is intentionally absent.

## Registry, replay, and lifecycle

`TestOnlyRealDataTrialRegistry` is in-memory and test-only. It uses immutable candidate state,
monotonic generation, predecessor binding, and one successful state swap. Only a successful
approval consumes the request, security review, governance review, trial approval, and approved
record replay identities. Denial and injected faults consume nothing and permit a clean retry.

Lifecycle values are `approved`, `expired`, `revoked`, and `superseded`. Expired, revoked, and
superseded records cannot become access-authorization-review eligible. There is no reactivation,
fallback, or status-only bypass.

All timestamps are explicit, timezone-aware UTC values rendered with six microsecond digits.
There is no hidden clock or random identifier. The order is v0.23 execution, post-execution review,
post-execution approval, readiness, trial request, security review, governance review, trial
approval, approved record, and explicit evaluation time. Future, stale, expired, or reordered
metadata is rejected.

## Access-authorization readiness

The pure evaluator progresses through `needs_trial_security_review`,
`needs_trial_governance_review`, and `needs_trial_approval`. Its maximum result is
`eligible_for_real_data_access_authorization_review`. That state routes evidence to a separate
future approval process and does not authorize a file read, real-data use, persistence, export,
production registry mutation, or runtime activation.

## Fixed zero-effects contract

Every v0.24 Security E2E path keeps actual file reads, real-data access, filesystem writes,
database writes, persistent-vector writes, external network, HTTP, cloud, production-registry
writes, credential use, token use, runtime activation, and runtime switching at zero.

No CLI command, CLI exit code, report schema, production profile, storage adapter, or existing
v0.10-v0.23 governance behavior is changed.
