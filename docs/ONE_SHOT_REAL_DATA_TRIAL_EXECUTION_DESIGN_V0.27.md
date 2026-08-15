# Explicit One-Shot Real-Data Trial Execution Boundary Design v0.27

## Scope

v0.27 implements one controlled synthetic-filesystem execution after the v0.25 authorization and
v0.26 verification contracts. It validates the resolver, open, identity, post-read verification,
successful-only usage, atomic receipt, replay, and closure semantics without connecting to an
actual Local RAG material root. It is not a production reader or authorization for an actual
confidential-document trial.

Fixed statements:

- target resolved != read authorized
- file opened != read verified
- read completed != masking verified
- one-shot receipt != embedding authorized
- one-shot receipt != persistence authorized
- completed closure != downstream processing approved
- completed closure != persistent storage approved

## Root and opaque target contracts

`TrialRootDescriptor` identifies one `controlled_trial_root` by digest. It stores no raw path,
drive, home, share, or filename. `RealTargetResolverPolicy` binds that root and permits only an
explicit extension set and the small-document class. Symlink, junction, reparse, parent traversal,
and absolute user input are fixed false; regular-file and identity-stability requirements are
fixed true.

`ControlledTargetReference` contains an opaque relative-target digest rather than user path text.
Only a private synthetic-fixture capability maps that digest to a relative component sequence.
The public adapter accepts no path, filename, directory, glob, scanner, or recursive-walk input.

## Resolver and pre-open gate

`RealTargetResolver` validates the marked controlled root, resolves each mapped component with
`lstat`, rejects links/reparse points, canonicalizes the final target, proves root ancestry, and
requires a regular allowlisted small file. Invalid `..`, drive-qualified, absolute, UNC, device,
alternate-stream, wildcard, and empty components are rejected without target access.

The resolver creates a metadata-only `FileIdentitySnapshot`. `PreOpenVerification` then
revalidates the complete v0.25/v0.26 source chain, operator exact binding, one remaining read,
selector/classification/stage/policy constraints, root confinement, file class, and expected
identity. Failure consumes no usage and commits nothing.

## Controlled open and TOCTOU verification

`ControlledFilesystemReadAdapter` accepts only a resolver-issued internal handle. It performs one
bounded read of one controlled synthetic file. Opened-target identity comes from the open file
descriptor; post-read identity comes from the same confined target. Pre/open/post metadata,
content identity, and size class must agree. Replacement, rename/swap, content or metadata
mutation, and link/reparse swap evidence fail closed.

`OneShotTrialExecutionResult` and `IdentityChainEvidence` retain digests and timestamps, never raw
document text. The v0.26 `PostReadClassificationResult` and `PostReadMaskingVerification` remain
separate object-backed gates. The transformed digest must differ from the raw digest and the stage
ceiling remains the masking-complete chunking candidate.

## Receipt, usage, replay, and atomicity

Only a stable, classified, and masked read can create `OneShotTrialReceipt`. It exact-binds the
authorization, one-shot request, target reference, identity chain, classification, masking,
operator, transformed digest, and usage before/after. Its fixed authority flags deny embedding,
persistence, export, and runtime activation.

The test-only ledger creates the receipt, exhausted authorization, zero-remaining usage, eight
execution replay identities, and pending-closure state in one candidate and performs one final
state swap. Pre-open/open/read/identity/classification/masking failures, forged evidence, replay,
or an injected pre-swap fault leave authorization usage, ledger state, and replay sets unchanged.
A committed authorization is exhausted and cannot be refilled or reused.

Successful-only replay covers the execution request, target reference, pre-open verification,
execution result, identity chain, classification, masking, receipt, and closure. Failure does not
consume any replay identity.

## Closure and evidence

Explicit closure exact-binds the committed receipt, original authorization, approved trial, and
same operator. `TrialClosureRecord` is either `completed` or `failed_closed`. Closure creates only
`PostReadEvidence`: receipt, target identity, classification, masking, transformed-content,
usage-exhaustion, and closure digests. It stores no raw or transformed document text.

## Operational boundary

Automated tests use a controlled temporary root and synthetic marker content only. They do not
connect to an actual Local RAG root or restricted directory, open an arbitrary user path, use a
customer/company/person/project identifier, call an external API/cloud/private LAN, load a
credential/token, write a persistent Vector DB or production registry, or activate/switch a
runtime. An actual one-shot real-data trial requires separate explicit user approval and a
separately controlled execution procedure.
