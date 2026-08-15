# Limited Real-Data Read Execution Boundary Design v0.26

## Scope

v0.26 models one limited, controlled read after a live v0.25 authorization. Automated
execution is fixture-backed: it exercises the authorization, verification, evidence, usage, and
atomic-ledger semantics without opening an arbitrary file or reading actual real data. An actual
one-shot real-data trial still requires a separate explicit user approval and a future executor.

The fixed release statements are:

- access authorized != actual read executed
- read started != read verified
- read succeeded != masking verified
- verified read != embedding authorized
- verified read != persistence authorized
- eligible_for_explicit_one_shot_trial_execution != executed

## Object-backed source chain

`RealDataReadAuthorizationContext` carries the actual v0.25 authorization record, request,
selector, policy, operator assignment, access approval, usage contract, and role context. It also
carries the actual v0.24 approved-trial object chain. The pre-read gate recomputes canonical
validity and re-runs the v0.24 and v0.25 validators. Caller-supplied digest equality alone is not
evidence.

`RealDataReadExecutionRequest` is immutable metadata. It binds the authorization, selector,
policy, approved trial, operator assignment, operator, usage state, and explicit UTC validity
window. `ReadTargetDescriptor` is an opaque controlled target identity, not a path, filename, or
directory.

## Pre-read hard gate

`PreReadVerificationResult` is issued before the controlled adapter is invoked. It verifies:

- live authorized lifecycle and exactly one remaining read;
- exact selector, access-policy, approved-trial, assignment, approval, role, and usage binding;
- internal-low-only classification and a small, single-document target;
- the chunking-candidate stage ceiling and masking requirement;
- no raw retention, logging, or cache;
- prohibited persistence, export, and network activity;
- operator equality across assignment, request, authorization, execution result, and receipt;
- operator separation from the access and trial approvers;
- explicit timezone-aware UTC temporal ordering and non-expiry.

Any failed check returns `failed` before a controlled read and consumes nothing.

## Controlled execution and evidence

`ControlledReadAdapter` contains an immutable synthetic fixture and transformed fixture. It has no
path or filesystem-reader surface. It produces deterministic success, open-failure, read-failure,
incomplete, classification-failure, and masking-failure outcomes.

`ReadExecutionResult` contains only metadata and a raw-content digest. Raw text is not retained in
the result. `PostReadClassificationResult` exact-binds expected and observed classification.
`PostReadMaskingVerification` binds raw and transformed digests plus masked and blocked classes.
A mismatch prevents downstream admission.

Only a successfully read, classified, and masked chain can mint `RealDataReadReceipt`. The receipt
binds the actual execution request, authorization, target, operator, execution result,
classification result, masking verification, transformed digest, and usage before/after states.
It grants neither embedding, persistence, nor full Local RAG processing authority.

The furthest downstream state is `verified_masked_content_candidate`. Embedding, vector writes,
unrestricted retrieval, prompt or LLM input, export, and persistent storage remain unauthorized.

## Usage, replay, lifecycle, and atomicity

The v0.25 usage contract exposes no public decrement, reset, or refill operation. A private
executor capability can create the exhausted successor only after all read and verification
evidence is valid. Successful verified read alone changes remaining usage from one to zero.
Open/read/incomplete/classification/masking failures, forged evidence, replay, and injected commit
faults consume zero.

The test-only ledger constructs the result, verifications, receipt, masked candidate, exhausted
authorization, usage successor, and seven replay identities in an immutable candidate state. One
final swap commits them together. A fault before that swap leaves state and replay sets unchanged
and permits retry. A committed request, target, result, classification, masking result, receipt,
or usage state cannot be replayed. An expired, revoked, superseded, or exhausted authorization
cannot execute.

Read execution lifecycle is `requested`, `verified`, `read_completed`,
`verification_failed`, or `receipt_committed`. `read_completed` alone never consumes usage.

## Side-effect boundary

The controlled adapter read count may be one. All actual arbitrary-file open/read, designated
real-material access, restricted-material access, real-data access, filesystem/database/vector
writes, external network/HTTP/cloud, production registry writes, credential/token use, and runtime
activation/switch counts remain zero. No persistent Vector DB is used.

## Future explicit trial hook

`ExplicitRealDataTrialExecutionHook` is a protocol only. v0.26 provides no implementation,
production reader, real path input, or runtime switch. Its states are
`needs_explicit_real_data_execution_approval` and
`eligible_for_explicit_one_shot_trial_execution`; eligibility is not execution.
