# Explicit One-Shot Real-Data Trial Approval / Root Provisioning Boundary Design v0.28

## Scope

v0.28 defines the explicit approval and root-provisioning evidence required before one one-shot
trial can be considered for execution. It does not execute the v0.27 reader, provision a real
filesystem root, or access an actual Local RAG document. All contracts are metadata-only and all
automated tests use synthetic digest identities.

Fixed statements:

- root provisioned != target read authorized
- trial approved != actual read executed
- operator assigned != execution approved
- eligible for explicit one-shot execution review != real-data use authorized
- one-shot approval != embedding authorized
- one-shot approval != persistence authorized
- closure required != downstream processing approved

## Purpose, root request, and opaque identity

`RealTrialPurpose` fixes the purpose class to `local_rag_confidentiality_trial`, the maximum stage
to the masking-complete chunking candidate, retention to none, and closure to required.
`RealTrialRootProvisioningRequest` exact-binds that purpose to the live v0.24 approved trial,
v0.25 authorization, v0.27 root descriptor and target reference, root provisioner, operator, and
explicit UTC validity window.

`RealTrialRootIdentity` exposes only an opaque identity digest, root class, resolver-policy digest,
provisioner, and time. It contains no path, filename, directory, drive, UNC share, hostname, or
root capability. v0.28 neither discovers nor creates an operating-system root handle.

## Object-backed root hard gates

Five distinct canonical result objects are required:

1. `RootConfinementVerificationResult`
2. `LinkReparseVerificationResult`
3. `PermissionVerificationResult`
4. `WriteProhibitionVerificationResult`
5. `NetworkIsolationVerificationResult`

Each result binds the exact root identity and provisioning request to a protocol digest, observed
evidence digest, verifier, UTC time, and `passed`, `failed`, or `incomplete` result. The
`RootProvisioningAttestation` binds the five actual result digests. Approval requires every result
to be canonical and passed; copied Booleans, missing evidence, inconsistent digests, or a forged
root identity fail closed. The verifier is distinct from the provisioner and operator.

The actual v0.27 `TrialRootDescriptor`, `RealTargetResolverPolicy`, and
`ControlledTargetReference` are revalidated. The resolver policy must deny symlink, junction,
reparse, parent traversal, and absolute user input, while requiring a regular file and stable
identity. The opaque root identity must equal the descriptor identity digest.

## Selection, safe policy, and closure

`RealTrialTargetSelection` permits exactly one opaque `internal_low_document_candidate`, bound to
the v0.25 selector, v0.27 target reference, root identity, and operator. It has no filename, path,
directory, wildcard, or scanning surface.

The source-chain gate requires a live v0.25 authorization with one allowed and one remaining use,
the exact operator assignment and access approval, and the complete v0.24 source chain. The only
accepted policy is internal-low, one document, one read, small-document class, maximum chunking
candidate stage, masking before that stage, no retention, no logging, no cache, no persistence,
and prohibited export and network.

`RealTrialClosureRequirement` requires a one-shot receipt, usage exhaustion, classification,
masking, post-read evidence, and a closure record. It permanently denies downstream processing,
embedding, persistence, and export authority.

## Reviews, approval, and role separation

`RealTrialApprovalRequest` exact-binds the purpose, root request/attestation, target selection,
live access authorization/approval, v0.27 root objects, closure requirement, requester, operator,
and time. Independent `TrialSecurityReview` and `TrialDataGovernanceReview` objects precede a
distinct `TrialExecutionApproval`.

The root provisioner, root verifier, trial requester, security reviewer, governance reviewer,
operator, execution approver, and existing access approver must be pairwise distinct. Every role
is checked against the corresponding actual object; a forged role context cannot repair an object
mismatch.

## Registry, replay, and lifecycle

Only `TestOnlyRealTrialApprovalRegistry` can mint `ApprovedOneShotRealDataTrial`. The record binds
all source, root, target, review, approval, operator, generation, predecessor, approval time, and
expiry digests. It can only state `approved_for_one_shot_execution_review`.

The registry builds a complete candidate state and performs one final immutable swap. Only a
successful approval consumes the root request, root identity, root attestation, target selection,
approval request, both reviews, execution approval, and record replay identities. Denial,
incomplete evidence, forgery, downgrade, replay, or injected fault changes no state and remains
retryable.

Lifecycle is one-way: `approved` may become `execution_pending`, `expired`, `revoked`, or
`superseded`; `execution_pending` may become `closed`, `expired`, or `revoked`. Terminal records
cannot be reactivated. Every transition creates a new generation bound to its predecessor.

## Operational boundary

The approval registry and readiness evaluator have no filesystem, root capability, reader,
network, credential, persistent storage, production registry, or runtime activation surface.
Actual file open/read, arbitrary filesystem read, Local RAG material access, restricted material
access, real-data access, external network/HTTP/cloud, credential/token use, filesystem/database/
persistent-vector/production-registry writes, and runtime activation/switch counts are all zero.
