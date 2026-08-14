# Local RAG Execution Session / Environment Attestation Design v0.23

## Purpose

v0.23 adds the approval boundary immediately before a controlled, synthetic-only Local RAG
execution. It attests an immutable environment, issues a short-lived execution session only from
the complete approved object chain, executes the existing v0.22 eleven-stage contract through a
test-only adapter, and collects metadata-only evidence for independent security review.

This boundary is not a production connector. It has no endpoint, address, path, user, credential,
token, raw content, customer identity, persistent database, registry mutation, or runtime switch
surface.

## Boundary sequence

1. Build a `LocalRAGEnvironmentManifest` from canonical build, dependency, configuration, policy,
   and protocol digests.
2. Execute all seven object-backed environment checks: build, dependency, configuration, network
   isolation, storage isolation, logging safety, and fixture safety.
3. Bind those concrete result objects into `EnvironmentAttestationSuite` and
   `EnvironmentAttestationEvidence`.
4. Evaluate the complete chain and obtain independent environment review and approval.
5. Create `LocalRAGExecutionSessionRequest` bound to the exact environment approval and exact
   v0.22 manifest, data-flow plan, fixture, and operator.
6. Obtain `LocalRAGExecutionSessionReview` and `LocalRAGExecutionSessionApproval` from the
   independent pre-execution reviewer and approver.
7. Commit one short-lived `ApprovedLocalRAGExecutionSession` through the test-only atomic registry.
8. Execute all eleven v0.22 stages through `ControlledLocalRAGExecutionAdapter` and emit only
   canonical stage digests, reason metadata, timestamps, and zero-valued side-effect accounting.
9. Obtain separate post-execution `SessionExecutionReview` and `SessionExecutionApproval` before
   evaluating eligibility for a separate, explicit real-data trial approval review.

## Environment hard gates

The manifest accepts only synthetic or controlled fixtures, disabled networking, no credentials,
and in-memory or ephemeral test-only storage. Every verification is an immutable concrete result;
a Boolean, enum, identifier, or caller-supplied digest cannot replace the actual object. The suite,
evidence, manifest, verifier identity, and UTC timestamps are exact-bound. Missing, failed,
incomplete, forged, future-dated, stale, or mismatched evidence fails closed.

Verifier, reviewer, and approver are pairwise distinct. Environment approval is metadata evidence
for controlled execution only:

- environment attested != production environment approved
- environment approved for controlled execution != production ready

## Approved execution session

The request carries only canonical digests, opaque identifiers, and aware timestamps. It cannot
directly create a session. Before registry admission, `LocalRAGExecutionSessionReview` exact-binds
the request, environment approval, integration manifest, fixture, reviewer, result, and time;
`LocalRAGExecutionSessionApproval` then exact-binds that request and review to a distinct approver.
The registry recomputes every canonical identity and validates the actual environment, v0.22, and
pre-approval objects before one successful state swap. Generation is monotonic and predecessor
binding is exact. Successful commits alone consume request, pre-review, pre-approval, and approved
session replay identities. Denial and injected commit faults consume none and do not change write,
mutation, or event counts.

Approved sessions are short-lived and operator-bound. Expired, revoked, and superseded sessions
are terminal for execution. A lifecycle enum or copied digest cannot mint an executable session;
the internal marker is available only to the registry after the complete chain passes.

- approved session != real-data use approved
- session approved != real-data approved
- approved session != production activation

## Controlled eleven-stage execution

The adapter accepts the exact approved session, request, environment manifest and approval, v0.22
integration manifest and data-flow plan, synthetic fixture, explicit operator, and explicit UTC
execution interval. It emits one `StageExecutionEvidence` object for each canonical `RAGStage`.
Stage evidence contains input/output/transformation/policy/sensitive-class digests and a result,
never raw fixture values.

Failure injection marks the selected stage failed and all following stages incomplete. A passed
receipt can be created only by the adapter. The receipt binds the session, environment, integration
manifest, fixture, operator, all eleven stage-result objects, interval, and side-effect accounting.
Changing any bound field invalidates its canonical chain.

The adapter performs no external operation. Its accounting fixes network, HTTP, cloud, real
filesystem writes, database writes, persistent vector writes, production-registry writes,
credential use, token use, runtime activation, runtime switching, and real-data access at zero.

- controlled execution passed != real-data approved

## Independent security review and readiness

Environment verification/review/approval and session requester/operator/pre-review/pre-approval
remain separate roles at the required boundaries. Post-execution `SessionExecutionReview` and
`SessionExecutionApproval` are separate objects used only by readiness and never substitute for
pre-execution authorization. The readiness evaluator requires the exact environment
decision, approved live session, eleven passed stage objects, zero side-effect object, passed
receipt, independent session review, distinct approval, and exact role context. Forged operator,
role context, stage evidence, receipt, review, approval, time, or lifecycle fails closed.

The maximum result is
`eligible_for_explicit_real_data_trial_approval_review`. It is a review-routing state only:

- real-data trial approval review eligible != real-data use authorized
- real-data trial approval review eligible != real-data approved
- execution approval != real-data use authorized
- eligible_for_explicit_real_data_trial_approval_review != real-data use authorized

All readiness decisions keep `real_data_approved`, `real_data_use_authorized`, and
`production_active` false and expose only zero side-effect counters.

## Compatibility and exclusions

No CLI command, CLI exit code, report schema, runtime profile, or production registry behavior is
changed. The v0.10-v0.22 governance chain remains intact. Tests use only synthetic confidential
fixtures and test-only in-memory components. No real customer data, real-material directory,
restricted directory, external API, cloud, private network, credential, token, persistent vector
database, production write, runtime activation, runtime switch, or knowledge-vault edit is part of
this release.
