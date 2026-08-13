# RAGGuard v0.17 Production-Equivalent Validation Evidence Boundary

> v0.18 integration: assessment, review, approval, criteria, and descriptor digests are exact-bound.
> Equivalence approval is a prerequisite claim, not runtime authorization or activation.

## Purpose and trust boundary

v0.17 defines how an already approved v0.16 manual-validation chain may be assessed as a
production-equivalent evidence candidate. It does not perform production validation and does not
connect to a product, endpoint, network, filesystem, database, registry, transport, or runtime.
The readiness enums and all environment descriptions are contract-fixture claims; they are not
real-world compatibility evidence by themselves.
Readiness metadata is not real-world compatibility evidence.

The boundary is fail closed:

`v0.16 approval -> assessment request -> criteria + descriptor -> pure assessment ->`
`independent review -> distinct approval`

Only the complete canonical chain can produce the `approved` equivalence state. An approved state
claim, manual-validation approval, or evidence-kind enum alone is insufficient. Equivalence
approval is not production approval, runtime authorization, activation, or persistence.
Equivalence approval is not production approval or runtime activation.

## Immutable contracts

- `ProductionEquivalenceAssessmentRequest` binds the exact v0.16 plan, fixture, environment,
  execution, evidence, and approval digests; exact profile/product/protocol versions; explicit
  request time; and the manual-validation and equivalence-assessor identities.
- `EquivalenceCriteria` is code-defined/test-fixture policy. It binds the required source kind,
  complete case set, environment/configuration/protocol/product contracts, expected behavior, and
  independent-review requirement. It is not a production profile.
- `EquivalenceEvidenceDescriptor` stores metadata only: typed source kind, provenance and contract
  digests, coverage digest, and creation time. It has no raw document, payload, endpoint, hostname,
  IP, port, path, username, credential, token, or cookie field.
- `EnvironmentEquivalenceContract` contains only runtime family/version and digest-covered policy
  metadata. It never stores a real connection target or performs environment access.
- `ConfigurationEquivalence` forbids hidden defaults and binds exact profile, product, protocol,
  feature-flag, limits, and compatibility-contract values.
- `ProductBehaviorEquivalence` requires the exact case set, equal observed/expected behavior
  digests, zero failed or skipped cases, and zero unresolved divergence.

All canonical timestamps are UTC with fixed six-digit microsecond precision. Equivalent instants
produce identical canonical values; distinct instants do not collide through truncation.

## Pure evaluator and deterministic priority

`evaluate_production_equivalence()` requires explicit `evaluation_time`; it has no hidden clock,
random UUID, I/O, transport, or mutation. Its priority is:

1. identity, digest, source-chain, role, unsafe-selection, or temporal failure -> `ineligible`
2. expired plan, stale evidence, or replay -> `ineligible`
3. environment gap -> `needs_environment_equivalence`
4. configuration gap -> `needs_configuration_equivalence`
5. protocol gap -> `needs_protocol_equivalence`
6. product behavior/coverage gap -> `needs_product_behavior_equivalence`
7. missing independent reviewer -> `needs_independent_review`
8. all assessment prerequisites -> `eligible_for_equivalence_review`

`eligible_for_equivalence_review` is not equivalent, approved, authorized, or active.

## Review, approval, roles, and replay

`EquivalenceReview` and `EquivalenceApproval` are distinct immutable attestations. The strict time
order is manual-validation approval <= assessment request <= assessment <= review < approval <=
evaluation time. Future metadata, stale evidence, and an expired plan fail closed.

The validation operator, validation reviewer, validation approver, equivalence assessor,
equivalence reviewer, and equivalence approver are six distinct actors. The boundary also rejects
collisions with protected registry/boundary/authorization roles.

The test-only attestation store builds all replay-set candidates before one state swap. It consumes
request ID, assessment/descriptor/review/approval IDs and digests, plus the source manual approval
digest only after a successful commit. Denial and commit fault leave every set unchanged, permit a
corrected retry, and keep write/mutation/persistence/filesystem/database/transport/HTTP/activation
counts at zero. A successful chain cannot be replayed.

## v0.14 and v0.15 integration

`ProductionBoundaryEvidence` carries the assessment, criteria, descriptor, review, and approval
digests plus `ProductionEquivalentState`. `approved` requires the complete digest set.
`ProductionAuthorizationRequest` may carry the source `EquivalenceAttestationChain`; the v0.14
evaluator recomputes and exact-matches each canonical digest. A self-declared enum or digest is not
trusted. `ProductionAuthorizationCandidate` retains the five equivalence-chain digests, so the
v0.15 persisted candidate digest covers them without changing persistence or activation behavior.

`ready_for_activation_commit != active`. v0.17 adds no Activation API, runtime switch, filesystem
or database persistence, production-registry write, product adapter, transport, HTTP integration,
credential handling, production profile, real document, or external/private-LAN access.
