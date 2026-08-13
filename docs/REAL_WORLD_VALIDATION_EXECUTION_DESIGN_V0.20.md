# Real-World Validation Execution Boundary v0.20

## Scope

v0.20 defines a fail-closed contract boundary for controlled validation execution. Despite the
name, this release is **controlled fixture only**: it does not connect to a real product, consume
real documents, use production credentials, or authorize a production runtime.

The boundary binds the complete source chain by canonical digest: the v0.16 manual-validation
approval, v0.17 equivalence approval, v0.18 `RuntimeAuthorizationCommitRecord`, and v0.19
`PersistenceCommitReceiptV2`. Source objects are supplied to the evaluator and checked; a
self-declared digest or Boolean claim cannot satisfy a gate.

## Contracts and states

- Authorization binds source approvals, runtime authorization, persistence receipt,
  profile/product/protocol versions, environment, product manifest, and plan.
- The environment permits only disabled networking, in-process transport, synthetic or controlled
  fixtures, and in-memory or controlled ephemeral storage.
- Scenario manifests contain opaque identifiers, counts, and digests only.
- Independent authorization review and approval precede controlled execution.
- The evaluator returns only `ineligible`, `needs_environment_verification`,
  `needs_execution_authorization`, or `ready_for_controlled_execution`.
- The deterministic test adapter returns `passed`, `failed`, or `incomplete`; it accepts no command,
  executable, path, endpoint, credential, environment variable, callback, or raw payload.
- Evidence is metadata-only and requires an independent reviewer and distinct approver.
- The test-only ledger builds candidate state and performs one atomic swap. Failure and injected
  faults consume no replay key; corrected retry remains possible. Successful replay is rejected.

Timestamps are timezone-aware, normalized to UTC with six-digit microsecond precision, and ordered
source → execution → evidence → review → approval → commit. `current`/`latest` aliases, fallback,
nearest-version selection, and schema inference are prohibited.

## Trust boundaries

- validation approved != production authorized
- execution passed != production-equivalent approved
- evidence approved != active
- a validation record may support later equivalence review but cannot self-approve it
- readiness/result enums are contract claims, not real-world compatibility evidence
- controlled fixture only
- no runtime activation
- no runtime switch, production registry write, or real persistence
- no network, transport, HTTP, credentials, tokens, real documents, or real-product connection

All decision/result objects expose zero counters for prohibited side effects.
