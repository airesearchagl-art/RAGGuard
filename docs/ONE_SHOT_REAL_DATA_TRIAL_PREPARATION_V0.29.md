# One-Shot Real-Data Trial Execution Preparation Boundary v0.29

## Scope

v0.29 packages the already-approved v0.25-v0.28 metadata chain for one final human review. It is
an execution-preparation boundary, not an execution API. The maximum decision is
`ready_for_explicit_execution_approval`; that state is not execution authorization and performs no
file open or read.

The implementation is deliberately thin. It reuses the v0.25 authorization and usage contract,
the v0.27 root/resolver/opaque-target contracts, and the v0.28 root provisioning and trial
approval. It adds no second governance hierarchy and no production registry.

## Metadata-only packet

`OneShotTrialExecutionPacket` binds:

- the approved one-shot trial;
- the live one-read access authorization;
- opaque root identity and exact root attestation;
- one opaque internal-low target selection;
- the operator assignment and opaque operator identifier;
- the fixed confidentiality-trial purpose;
- the resolver and reader policy;
- the complete post-trial closure requirement;
- one allowed read, a chunking-candidate stage ceiling, issue time, and expiry.

The packet hard-codes raw retention, raw logging, raw cache, persistence, export, and network to
false. Its public fields contain no root path, document path, filename, payload, credential,
token, or customer/project/person identity. Its canonical digest changes when any binding changes.

## Object-backed verification

Preparation accepts the actual objects, not caller assertions. It revalidates:

- `RealDataAccessAuthorizationRecord`, `RealDataOperatorAssignment`, and
  `AuthorizationUsageCounterContract` through the actual read-authorization context;
- `ApprovedOneShotRealDataTrial`, its approval request, security review, governance review, and
  distinct execution approval;
- `RealTrialPurpose`, root provisioning request and identity, all five concrete provisioning
  results, `RootProvisioningAttestation`, and `RealTrialTargetSelection`;
- `TrialRootDescriptor`, `RealTargetResolverPolicy`, and `ControlledTargetReference`;
- `RealTrialClosureRequirement` and all eight v0.28 roles.

The v0.25 and v0.28 canonical validators are called again at the explicit evaluation time. Exact
digest checks then bind every packet field to those objects. A consistently supplied forged digest
cannot replace a canonical source object.

## Hard gates

Preparation fails closed unless all of the following remain true:

- authorization lifecycle is authorized with allowed and remaining read count exactly one;
- the approved trial is canonical, approved, current, and neither revoked nor superseded;
- all five root verification results passed and the exact attestation is approved;
- the target is one opaque internal-low document candidate;
- purpose is `local_rag_confidentiality_trial` with a chunking-candidate ceiling;
- operator, requester, reviewers, execution approver, access approver, provisioner, and verifier
  remain exact-bound and pairwise separated as required by v0.28;
- raw retention/log/cache and persistence/export/network remain denied;
- receipt, usage exhaustion, classification, masking, post-read evidence, closure record, and
  closure review remain mandatory;
- packet, request, authorization, root, approval, and evaluation times remain ordered and live.

## Dry-run and replay boundary

`prepare_one_shot_trial()` requires an explicit `TestOnlyExecutionPreparationRegistry`. The
registry holds only packet and request digests in memory. It consumes those replay identities only
after a ready decision; denial leaves the immutable state unchanged. Replaying either identity is
ineligible.

The preparation path has no resolver invocation, file adapter, directory scanner, database,
vector store, transport, credential provider, runtime activator, or production writer. Its side-
effect accounting remains all zero.

## Safe summary and human stop gate

The safe summary contains only opaque IDs, canonical digests, enums, the one-read count, stage
ceiling, expiry, deny flags, closure digest, readiness state, and reason codes. It cannot contain a
path, filename, document body, real organization/project/person identity, credential, or token.

The only positive decision is `ready_for_explicit_execution_approval`. The packet must be reviewed
and a separate human authorization must occur in a later explicitly approved session. v0.29
provides no `execute`, `read`, `open`, `run_trial`, `auto_approve`, or `auto_execute` entrypoint.

## Fixed release boundary

- packet prepared != trial execution approved
- execution approval ready != execution authorized
- execution authorized != file read
- approved trial != read executed
- no actual real-data access
- no actual or arbitrary file open/read
- no raw path in a public packet or summary
- no persistent Vector DB or production storage/registry write
- no network, HTTP, cloud, credential, token, or runtime activation
- CLI exit codes and report schema remain unchanged
