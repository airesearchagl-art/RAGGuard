# RAGGuard v0.11 Production Admission Design

## Status and scope

This document defines the product-neutral, fail-closed contract that must exist before a
Compatibility Profile can be admitted to a production registry. It extends the v0.10 approval
governance design without changing the runtime, transport, CLI/config, report schema, or registry
implementation.

v0.11 design work does not perform manual validation, connect to a product, create a production
profile or registry entry, persist a registry, use credentials or real documents, or authorize
external/private-LAN access. Synthetic evidence remains necessary but is never manual evidence or
proof of real-product compatibility.

## Production admission state transition

The admission process is explicit and monotonic:

1. `candidate_profile`
2. `synthetic_validation_complete`
3. `manual_validation_planned`
4. `manual_validation_executed`
5. `evidence_reviewed`
6. `approval_decided`
7. `production_registry_admitted`

The following lifecycle states may follow admission:

- `suspended`: temporarily unavailable pending an explicit review.
- `deprecated`: retained for audit but unavailable for new or resumed use.
- `revoked`: terminal and immediately unavailable for new or resumed use.
- `revalidation_required`: the existing evidence and admission decision are unusable until a new
  plan, new execution, new evidence review, and new approval decision complete.

| From | To | Required gate |
| --- | --- | --- |
| `candidate_profile` | `synthetic_validation_complete` | Complete v0.10 synthetic evidence |
| `synthetic_validation_complete` | `manual_validation_planned` | Approved immutable manual plan |
| `manual_validation_planned` | `manual_validation_executed` | All required manual cases attempted |
| `manual_validation_executed` | `evidence_reviewed` | Independent evidence reviewer validates the evidence and creates an immutable attestation |
| `evidence_reviewed` | `approval_decided` | A distinct approver explicitly selects one decision |
| `approval_decided` | `production_registry_admitted` | Decision is `approved` or `approved_with_restrictions` and every admission gate passes |
| `production_registry_admitted` | `suspended` / `deprecated` / `revoked` | Explicit administrative action |
| any non-terminal state | `revalidation_required` | A revalidation trigger is present |

No step may be skipped, inferred, repaired, or promoted automatically. Revalidation starts a new
plan and evidence chain; it does not mutate or relabel the old evidence. Suspension, deprecation,
and revocation never select a replacement profile, reactivate an entry, or roll back automatically.

`rejected` and `needs_revalidation` are valid decisions that complete the `approval_decided` state,
but they are ineligible for `production_registry_admitted`. They terminate the current admission
attempt or require a new evidence chain. Only `approved` and `approved_with_restrictions` make the
record an admission candidate, and neither decision bypasses any other admission gate.

## Component responsibility

| Role | Responsibility | Must not do for the same admission |
| --- | --- | --- |
| profile implementer | Prepare the candidate profile and mapping rationale | Review evidence or approve |
| validation operator | Execute only the approved plan and produce bounded evidence | Review or approve own run |
| evidence reviewer | Verify plan/evidence identity, completeness, freshness, and safety | Approve the same admission |
| approver | Select one bounded decision and explicit restrictions | Review own decision evidence |
| registry administrator | Perform the exact approved registry write | Change evidence or approval |
| release operator | Verify release gates and record immutable references | Repair or infer admission data |

The evidence reviewer and approver are always distinct. The profile implementer and validation
operator cannot review or approve the same admission. The registry administrator cannot approve
the write they execute. The only permitted small-team combination is registry administrator and
release operator, and only when the independent reviewer and approver are distinct, the decision
is already immutable, and the registry operation is an exact mechanical application. Exceptions
never combine reviewer and approver or permit self-approval.

## Manual validation plan schema

`ManualValidationPlan` is an immutable, versioned record with unknown-field rejection. It contains:

- `plan_id`: bounded opaque safe identifier supplied explicitly; never generated from product data.
- `plan_schema_version`: exact design-contract version.
- `profile_id`, `profile_version`, `protocol_version`: exact candidate identity.
- `product_family_id`: bounded product-neutral alias, not a vendor or customer name.
- `target_product_version`: exact normalized version expected during execution.
- `candidate_product_version_range`: reviewed range; it is never used for nearest selection.
- `environment_class`: allowlisted isolated-manual environment class.
- `environment_fingerprint_policy`: the allowlisted safe fingerprint fields.
- `operator_id`, `reviewer_id`, `approver_id`: bounded role identifiers.
- `approved_at`, `execute_not_before`, `execute_by`: timezone-aware timestamps. The execution
  window is at most 30 days.
- `required_case_ids`: exactly the required manual case allowlist.
- `expected_outcomes`: exact per-case outcomes; required safety cases must pass.
- `endpoint_boundary`: an allowlisted class such as `loopback_only`; no host, port, URL, address,
  path, or fallback endpoint is retained.
- `data_classification`: `synthetic_only`.
- `credential_policy`: `none` for v0.11. Credential-bearing validation requires a separate design
  and approval and cannot be represented by this contract.
- `evidence_retention_policy`: bounded safe evidence only; no raw traffic or real content.
- `abort_conditions`: fixed allowlist covering identity mismatch, boundary violation, unexpected
  authentication, redirect/proxy/retry, unsafe disclosure, case mismatch, and cleanup failure.
- `cleanup_conditions`: connection closed, temporary synthetic state removed, and no raw artifact
  retained.
- `synthetic_validation_record_id`: reference to completed synthetic evidence. It is a prerequisite
  only and does not satisfy a manual case.
- `plan_digest`: digest of the canonical safe plan fields for exact evidence binding.

The operator may not alter the plan during execution. Any required change creates a new plan ID,
digest, review, and approval.

## Required manual cases

Every manual evidence record contains exactly one result for each required case:

- `health`
- `capabilities`
- `required_capabilities`
- `request_mapping`
- `response_mapping`
- `pass_query`
- `warning_query`
- `fail_query`
- `malformed_response_rejection`
- `timeout_rejection`
- `oversized_response_rejection`
- `unsafe_source_rejection`
- `duplicate_id_rejection`
- `rank_gap_rejection`
- `query_id_echo`
- `close_cleanup`
- `report_non_disclosure`
- `product_version_exact_or_range_validation`
- `unsupported_product_version_rejection`
- `approval_denial_before_transport`
- `credential_non_disclosure`
- `endpoint_non_disclosure`

Unknown, duplicate, missing, skipped, or partially recorded required cases fail closed. Synthetic
case outcomes must not be copied, inherited, or relabelled as manual outcomes.

## Manual validation evidence schema

`ManualValidationEvidence` is immutable and contains only:

- `evidence_id`, `evidence_schema_version`, `plan_id`, and exact `plan_digest`.
- Exact product-family alias, observed product version, profile ID/version, and protocol version.
- `started_at`, `completed_at`, and `expires_at`, all timezone-aware.
- `environment_fingerprint`: canonical safe tuple containing only environment class, OS family,
  architecture, runtime major/minor, harness version, and contract version.
- `tool_version` and exact required-case result records.
- Required capability, score semantics, source policy, transport boundary, cleanup, and
  non-disclosure results.
- Bounded result counts, durations, safe error categories, and an allowlisted safe summary.
- `raw_payload_retained=false`, `secret_retained=false`, `real_content_retained=false`.
- Explicit failure evidence category when a case fails.
- Explicit close and cleanup evidence.

The fingerprint excludes hostname, username, device ID, MAC address, IP address, endpoint, port,
filesystem path, environment variable, customer identifier, and free-form text. Evidence expires
no later than 90 days after completion and becomes unusable immediately when any revalidation
trigger is present.

Observed product version is exact. It must equal the plan target and be contained in the reviewed
candidate range. Evidence proves only the observed version. A production admission range may not
exceed the reviewed range; patch/minor coverage requires an explicit compatibility rule, unchanged
schema/capabilities/security boundaries, and no revalidation trigger. Nearest-version selection is
never permitted.

Raw request/response payloads, query text, endpoint details, ports, paths, tokens, cookies, API
keys, credentials, headers, real document content, customer/production data, stack traces, and
internal exceptions are not evidence fields and are never retained in reports or fixtures.

## Synthetic and manual evidence separation

The v0.10 synthetic report remains a prerequisite and retains its existing identity. Manual
evidence references that record but has a different evidence ID, validation type, environment
class, timestamps, case results, reviewer attestation, and expiration. Neither record inherits,
converts, or repairs the other.

Production admission requires both records. A synthetic report cannot satisfy manual completeness,
advance maturity to `manually_validated`, or enter a production registry. Manual evidence cannot
replace the synthetic security and compatibility gates.

## Evidence review and approval decision

The evidence reviewer verifies exact plan/evidence identity, required-case completeness, safe
fingerprint shape, observed version, timestamps, freshness, cleanup, non-disclosure, and absence of
unknown fields. The reviewer produces an immutable attestation containing only safe IDs, digests,
review time, outcome, and bounded error categories.

Only creation of that immutable reviewer attestation establishes `evidence_reviewed`.
Approval is forbidden before `evidence_reviewed`. A distinct approver then explicitly selects
exactly one existing v0.10 decision and establishes `approval_decided`:

| Decision | Production admission result |
| --- | --- |
| `approved` | Eligible only when every admission condition passes |
| `approved_with_restrictions` | Eligible only when every restriction is explicit and enforceable |
| `rejected` | Completes `approval_decided`; ineligible and no registry write |
| `needs_revalidation` | Completes `approval_decided`; ineligible until a new evidence chain is approved |

An admission evaluator is pure and deterministic at an explicit timezone-aware evaluation time.
Admission requires:

- `manually_validated` maturity.
- Complete, passed, fresh manual evidence and completed synthetic evidence.
- Exact profile/version/protocol, plan, evidence, review, and approval identity.
- Observed product version inside the explicitly supported range.
- Restrictions that use known typed fields and can be enforced before transport creation.
- Unexpired plan, evidence, review, approval, and restrictions.
- No revalidation trigger.
- Distinct operator, reviewer, and approver responsibilities.
- Exact requested registry kind `production` and requested initial status `active`.

Before admission, no registry entry or registry status exists. The evaluator validates the
requested registry kind and initial status; it does not claim that an active entry already exists.
Only a successful explicit registry write creates the entry with status `active`.

Restrictions are valid only when bounded and machine-enforceable, such as maximum top-k, disabled
optional fields, required query-ID echo, allowed minor versions, or expiration. Free-form
exceptions, undocumented workarounds, silent downgrade, fallback, and indefinite approval fail
closed.

## Registry admission

Production registry admission is one explicit operation after the evaluator succeeds. The minimum
safe admission bundle is the exact profile/protocol identity, supported product-version range,
synthetic record ID, manual plan/evidence IDs and digests, reviewer attestation ID, approval record
ID and decision, enforceable restrictions, expirations, and registry status.

The registry administrator revalidates this bundle immediately before writing. Registration uses
only an exact profile ID/version, rejects duplicate or overwrite attempts, and records one bounded
event. There is no discovery, fallback, nearest-version selection, schema inference, automatic
recovery, automatic rollback, or automatic substitution.

Only `approved` and `approved_with_restrictions` decisions are eligible for this operation, and
only after every other admission condition succeeds. `rejected` and `needs_revalidation` remain
valid recorded decisions but cannot create an entry.

Suspended, deprecated, revoked, expired, or revalidation-required entries cannot resolve or pass
approval enforcement. Revocation is terminal. Suspension requires a new explicit review before
any new admission; it does not reactivate the old entry. Registry persistence and any real entry
are outside this design.

## Revalidation triggers

Any of the following invalidates the current admission evidence:

- Product version change outside the exact approved compatibility rule.
- Profile version or protocol version change.
- Request or response schema/mapping change.
- Required or optional capability change.
- Score semantics or source identifier policy change.
- Security boundary, transport, timeout, size, or cleanup behavior change.
- Material dependency or tool-version change.
- Incident, vulnerability, compatibility defect, or unsafe disclosure.
- Plan, evidence, review, approval, or restriction expiration.
- Evidence identity, digest, timestamp, fingerprint, or case inconsistency.
- Registry suspension, deprecation, or manual revocation.

Revalidation always produces a new plan and evidence chain. Existing evidence is retained only as
a bounded audit reference and cannot be refreshed by changing a timestamp.

## Failure matrix

| Failure | Decision / registry effect | Runtime effect |
| --- | --- | --- |
| Missing, unknown, duplicate, or partial case | `rejected` | No registry write |
| Expired evidence or approval | `needs_revalidation` | Deny before transport |
| Identity, digest, or observed-version mismatch | `rejected` | No registry write |
| Unsafe fingerprint or disclosure field | `rejected` | No registry write |
| Reviewer/approver collision or self-approval | `rejected` | No registry write |
| Restriction cannot be enforced | `rejected` | No registry write |
| Cleanup or close evidence fails | `rejected` | No registry write |
| Registry is suspended/deprecated/revoked | Ineligible | Exact resolution denied |
| Unknown field or unknown case | Invalid contract | Bounded safe error only |
| Incident or vulnerability | `needs_revalidation` or explicit revocation | New/resumed use denied |

All failures are fail-closed. A denial never performs a registry write, and a registry denial never
permits runtime use. Public output contains only allowlisted safe categories; it never exposes raw
values, endpoint details, paths, credentials, payloads, or internal exceptions.

## Security boundary

- No production profile or real production-registry entry.
- No registry persistence or production write in this design.
- No manual validation is executed or represented as completed.
- No real-product, localhost, external, private-LAN, or cloud connection.
- No credentials, authentication material, real documents, customer data, or production data.
- No external API, product-specific adapter, fixture containing real evidence, or automated
  validation session.
- Fail closed with exact identity and version matching.
- No discovery, fallback, nearest-version selection, schema inference, implicit downgrade,
  automatic approval, automatic recovery, or automatic rollback.

Any future real-product validation session is a separate explicitly approved task, performed
manually from an approved plan. Phase D may import only an explicitly supplied safe synthetic
fixture; the word “import” never authorizes external API access or automatic product connection.

## v0.11 Phase A-F roadmap

### Phase A: manual validation plan contract

- Purpose: immutable plan schema, role identity, exact target versions, case allowlist, safe
  boundaries, timestamps, abort/cleanup conditions, and canonical digest.
- Implementation: communication-free typed contract and safe synthetic fixtures only.
- Non-goals: evidence execution/import, product connection, registry operation.
- Tests: unknown/missing fields, role collisions, time window, case completeness, safe fingerprint
  policy, credential/data boundary, and immutability.
- Security: no endpoint value, credential, real product/data, network, filesystem, or hidden clock.
- Merge gate: focused contract suite and full regressions pass on Python 3.11/3.12.

### Phase B: manual validation evidence contract

- Purpose: immutable evidence, exact plan binding, required results, freshness, fingerprint, safe
  summary, failure and cleanup evidence.
- Implementation: typed evidence built only from explicit safe synthetic fixtures.
- Non-goals: manual session execution, real payload retention, approval or registry write.
- Tests: exact identity/digest, required cases, observed versions, 90-day maximum lifetime,
  non-disclosure, unknown fields, partial/failure outcomes, and deterministic validation.
- Security: raw payloads, credentials, endpoint/path details, real content, and internal exceptions
  are structurally unavailable.
- Merge gate: Phase A-B and full regressions pass on Python 3.11/3.12.

### Phase C: production admission evaluator

- Purpose: pure decision table over v0.10 approval plus v0.11 plan, evidence, review, restrictions,
  freshness, roles, and registry eligibility.
- Implementation: deterministic communication-free evaluator and bounded result.
- Non-goals: registry mutation, runtime integration, product connection, automatic approval.
- Tests: all four decisions, identity/freshness/role failures, restrictions, revalidation, and no
  mutation or fallback.
- Security: explicit evaluation time, bounded categories, no raw rejected values.
- Merge gate: Phase A-C and full regressions pass on Python 3.11/3.12.

### Phase D: offline manual-evidence import and validation boundary

- Purpose: parse and validate an explicitly supplied safe fixture against exact plan/evidence
  schemas.
- Implementation: offline parser boundary with unknown-field rejection and no automatic session.
- Non-goals: external API, product connection, credential loading, endpoint discovery, real
  evidence generation, or registry write.
- Tests: safe fixture parsing, malformed/unknown/sensitive fields, size bounds, exact digest, and
  deterministic validation.
- Security: import means offline validation only; it performs no network or product operation.
- Merge gate: Phase A-D and full regressions pass on Python 3.11/3.12.

### Phase E: registry admission enforcement and security E2E

- Purpose: require a successful Phase C result before an explicit exact registry admission and
  ensure denied/inactive entries cannot reach runtime.
- Implementation: synthetic-only admission boundary and security E2E using test-owned data.
- Non-goals: real production entry, persistence, product-specific adapter, manual validation.
- Tests: denial-before-write, exact admission, duplicate/overwrite rejection, suspension,
  deprecation, revocation, runtime denial, safe output, and no fallback/rollback.
- Security: no real registry data, product traffic, credential, or persistent backend.
- Merge gate: Phase A-E, compatibility/profile integration/HTTP security, and full regressions pass
  on Python 3.11/3.12.

### Phase F: documentation, CI, and release preparation

- Purpose: document the delivered contracts and prepare a separate release checklist.
- Implementation: docs and design/release contract tests; add CI only when existing full-suite
  coverage is insufficient.
- Non-goals: tag, GitHub Release, Vault update, product connection, production profile/entry.
- Tests: full and targeted suites, CLI help, compile, YAML parse, diff/bidi/CR/secret scans.
- Security: restate synthetic-only status and manual-validation non-completion.
- Merge gate: clean reviewed PR and Python 3.11/3.12 Actions success.

## Approval checklist before any real-product validation

- [ ] A separately approved task names the bounded validation objective without storing a vendor,
  customer, endpoint, credential, or real-data value in the repository.
- [ ] Candidate profile and protocol versions are exact and synthetic validation is complete.
- [ ] Immutable plan, case allowlist, role separation, execution window, abort conditions, cleanup
  conditions, and safe digest are independently reviewed.
- [ ] Environment is isolated and constrained to the separately approved connection boundary.
- [ ] Data classification is synthetic-only and credential policy is `none`.
- [ ] Evidence retention excludes raw traffic, query text, endpoint/path details, secrets, real
  content, and stack traces.
- [ ] Operator, evidence reviewer, approver, registry administrator, and release operator duties
  satisfy the separation rules.
- [ ] Stop, cleanup, non-disclosure, incident, and revalidation procedures are understood.
- [ ] The session will not create a production profile/entry, write a registry, or persist evidence
  without later separate approvals.

## Unresolved design questions

- Whether a future credential-bearing product can be supported safely; v0.11 answers “not yet” and
  requires a separate design.
- Whether production registry persistence is needed and which transactional/audit model it would
  require; persistence is excluded from v0.11.
- Whether an active transport must be terminated immediately on suspension versus at the next
  governance checkpoint; v0.11 requires denial for new/resumed use and defers active-session
  mechanics.
- Which product-neutral compatibility rule, if any, may extend exact observed evidence across
  patch versions; the default remains exact observed version only.
- Whether evidence signing or external attestation is required; v0.11 defines canonical safe
  digests but no key management or signing system.
