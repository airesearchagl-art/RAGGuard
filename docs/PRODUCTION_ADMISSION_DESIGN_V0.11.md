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

### Phase A implemented plan contract

Phase A provides a narrower communication-free typed contract before any evidence execution. Its
immutable fields are `plan_id`, `profile_id`, `profile_version`, `protocol_version`, `product_id`,
`product_version`, `created_at`, `execution_window_start`, `execution_window_end`,
`profile_implementer_id`, `validation_operator_id`, `evidence_reviewer_id`, `approver_id`,
`registry_administrator_id`, `required_case_ids`, `endpoint_boundary`, `data_boundary`,
`credential_boundary`, `abort_conditions`, `cleanup_conditions`,
`synthetic_evidence_reference`, `safe_summary`, and `canonical_digest`.

Versions are exact strict SemanticVersion values; wildcards, ranges, nearest-version selection,
and inference are structurally unavailable. Timestamps are explicit and timezone-aware,
`created_at <= execution_window_start < execution_window_end`, and the window is at most 30 days.
The contract uses no hidden clock, random value, or generated UUID.

The evidence reviewer differs from the approver, the validation operator cannot review their own
execution, and the profile implementer cannot approve their own profile. The registry
administrator/release-operator exception remains outside this plan because release operator is not
a plan field.

`endpoint_boundary` contains only the `loopback` category, an explicitly approved boundary marker,
and an opaque endpoint reference. Its identifiers cannot represent a hostname, address, port,
URL, path, query, credential, private-LAN destination, or external destination. This declaration
does not create a transport or determine connectivity. The data boundary requires
`synthetic_only`, `no_customer_data`, `no_production_data`, `no_real_documents`,
`no_raw_payload_retention`, and `safe_summary_only`. The credential boundary requires
`credentials_prohibited=true` and has no credential-reference field.

The exact Phase A case IDs are `health_valid`, `capabilities_valid`,
`required_capabilities_present`, `request_mapping_valid`, `response_mapping_valid`, `pass_query`,
`warning_query`, `fail_query`, `malformed_response_rejected`, `timeout_rejected`,
`oversized_response_rejected`, `unsafe_source_rejected`, `duplicate_id_rejected`,
`rank_gap_rejected`, `query_id_echo_valid`, `close_cleanup_valid`,
`report_non_disclosure_valid`, `product_version_valid`,
`unsupported_product_version_rejected`, `approval_denial_before_transport`,
`credential_non_disclosure_valid`, and `endpoint_non_disclosure_valid`. Missing, duplicate,
unknown, or partial sets fail closed and the stored order is canonical.

The exact abort set covers unexpected network destination, credential request, unsafe source
disclosure, raw-payload retention attempt, schema mismatch, unsupported product version, response
size violation, timeout, and cleanup failure. The exact cleanup set requires transport closed,
temporary safe fixture removed, no raw payload retained, no credential retained, no endpoint
detail retained, and safe summary produced.

The synthetic evidence reference is an opaque v0.10 record identity bound to the exact profile ID
and version. It cannot contain report text, a path, or a URL and is never manual evidence. The
canonical digest is `sha256:<hex>` over sorted-key compact JSON of the immutable safe plan fields.
The safe summary contains only the allowed identities and versions, execution window, case count,
role-separation result, boundary category, and digest. Validation errors expose only deterministic
typed categories and never rejected input.

A canonical timestamp is normalized to UTC and serialized with a `Z` suffix while preserving all
six digits of Python `datetime` microsecond precision. Equivalent instants expressed with different
UTC offsets therefore produce identical canonical timestamp values and identical plan digests.
Distinct instants must remain distinct: no timestamp is truncated to seconds, so a microsecond-only
difference changes the canonical value and digest. Safe-summary execution-window timestamps use
the same UTC normalization and microsecond-preserving serialization as canonical JSON.

A valid plan is not evidence, approval, or production admission. Plan creation performs no
validation execution, transport generation, registry write, I/O, network/filesystem access,
credential handling, or real-product/data operation.

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

### Phase B implemented evidence contract

Phase B implements immutable `ManualValidationEvidence` with `evidence_id`, `plan_id`,
`plan_digest`, `profile_id`, `profile_version`, `protocol_version`, `product_id`,
`planned_product_version`, `observed_product_version`, `execution_started_at`,
`execution_completed_at`, `validation_operator_id`, `evidence_reviewer_id`,
`environment_fingerprint`, `tool_version`, `case_results`, `close_cleanup_evidence`,
`non_disclosure_evidence`, `failure_summary`, `expires_at`, `safe_summary`, and
`canonical_digest`.

Construction accepts one `ManualValidationPlan` solely to verify exact identity and does not retain
the plan object or plan body. Plan ID/digest, profile ID/version, protocol version, opaque product
ID, planned version, operator, reviewer, and required case set must match exactly. The observed
product version is a strict exact SemanticVersion and must equal the planned version in Phase B.
Any wider supported-range decision belongs to Phase C; no range inference, nearest selection, or
fallback occurs here.

Execution start, completion, each case execution, and expiration are explicit timezone-aware
timestamps. Execution must remain inside the plan window, start precedes completion, completion
precedes expiration, and freshness is at most 90 days. Canonical timestamps normalize to UTC with
a `Z` suffix and fixed six-digit microsecond precision. Equivalent instants have identical
canonical values; distinct microsecond instants do not collide. Expiration is evaluated only
against an explicitly supplied timezone-aware evaluation time. Structural validity and freshness
combine through `is_valid_at(explicit_time)`: it is true only from `execution_completed_at`
inclusive until `expires_at` exclusive. `is_valid` reports structural validity only, while
`is_valid_at` reports temporal validity including completion and freshness. Future-dated evidence
is invalid, and no hidden clock decides evidence validity.

Every Phase A required case has one immutable result containing case ID, `passed`, `failed`, or
`aborted` outcome, execution time, allowlisted safe observation, bounded failure category, and
cleanup confirmation. Missing, duplicate, unknown, or out-of-window results fail closed and stored
results use the Phase A canonical order. Failed or aborted results may be retained with a bounded
typed failure summary, but make `is_valid=false`; they are never approved evidence.

The environment fingerprint contains only an opaque environment reference, allowlisted OS family
and architecture, strict Python/RAGGuard versions, a safe fixture adapter ID, exact profile ID, and
its deterministic digest. Hostname, username, address, MAC address, endpoint, port, path,
environment values, credentials, and customer/product-specific details are structurally absent.

Close/cleanup evidence requires transport closed exactly once, temporary safe fixture removal, no
raw payload, credential, or endpoint detail retained, and safe summary production. Non-disclosure
evidence explicitly requires no credential, endpoint, path, raw request/response, real document,
or stack-trace disclosure and safe errors only.

Canonical evidence identity is `sha256:<64 hex>` over sorted-key compact JSON of the immutable safe
fields, including the exact plan digest and environment digest. The safe summary contains only
allowlisted evidence/plan/profile/protocol/product versions, canonical execution and expiry times,
case outcome counts, role-separation result, environment digest, and evidence digest.

A valid evidence object is not reviewer attestation, approval, production admission, registry
write authority, or runtime authorization. Evidence construction performs no validation session,
transport generation, I/O, network/filesystem access, credential handling, or real-product/data
operation. Synthetic evidence is a plan prerequisite only and is never relabelled as manual
evidence.

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

The temporal order is strict and compares timezone-aware instants after UTC normalization:
`evidence.execution_completed_at <= attestation.reviewed_at < approval.approved_at
<= evaluation_time < evidence.expires_at`. Review and approval at the same instant are rejected;
approval one microsecond after review satisfies this ordering when every other gate passes.

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
- Implementation: delivered as immutable reviewer-attestation, request, decision, safe-summary,
  reason-category, and revalidation-trigger contracts plus a deterministic communication-free
  evaluator.
- Non-goals: registry mutation, runtime integration, product connection, automatic approval.
- Tests: all four decisions, identity/freshness/role failures, restrictions, revalidation, and no
  mutation or fallback.
- Security: explicit evaluation time, bounded categories, no raw rejected values.
- Merge gate: Phase A-C and full regressions pass on Python 3.11/3.12.

The evaluator accepts `manually_validated` maturity as the exact pre-approval state; it does not
require `approved` before producing the approval decision. Its deterministic priority is:

1. unsafe, identity, binding, role, or reviewer rejection -> `rejected`;
2. freshness, expiration, unsupported exact version, or explicit trigger -> `needs_revalidation`;
3. all gates pass with explicit enforceable restrictions -> `approved_with_restrictions`;
4. all gates pass without restrictions -> `approved`.

Only the last two outcomes are registry-admission eligible. Eligibility does not create an entry,
write or read a registry, persist state, grant runtime authorization, or create a transport.

`safe_context` is allowlisted advisory metadata. Its shape is validated at request construction,
but it is not evidence, does not satisfy any admission gate, and cannot override an identity,
temporal, maturity, restriction, reviewer, approver, or revalidation failure.

### Phase D: offline manual-evidence import and validation boundary

- Purpose: parse and validate an explicitly supplied safe fixture against exact plan/evidence
  schemas.
- Implementation: delivered as immutable `ManualEvidenceImportRequest` and
  `ManualEvidenceImportResult` contracts plus typed safe errors and a deterministic
  `import_manual_validation_evidence()` function. The only source kind is
  `inline_safe_fixture`; file paths, URLs, streams, stdin, clipboard, environment references,
  cloud objects, databases, and external processes are not inputs.
- Schema and size boundary: exact nested field sets, no defaults or implicit casts, a 64 KiB total
  input limit, 64-character identifiers/environment fields, bounded safe context/failure summary,
  and exactly 22 case fixtures. Unknown, missing, duplicate, nested-arbitrary, and oversized input
  fails closed without echoing values.
- Safety boundary: structural allowlists admit only opaque IDs, strict semantic versions,
  timezone-aware timestamps, enums, digests, bounded observations, and boolean declarations.
  These typed validators take precedence over heuristic substring scans. Opaque identifiers are
  validated by grammar and are not rejected merely because they contain words such as `token` or
  `secret`. The current schema has no free-description field, so it performs no root-wide heuristic
  scan; any future free-description field must receive a field-scoped scan. URL/IP/path,
  credential/token/cookie forms, PEM/header, raw HTTP, stack trace, control, bidi, CR-only, and
  null-byte values remain outside the typed field grammars and fail closed.
- Binding and construction: plan ID/digest, profile/protocol/product versions, roles, required
  cases, execution window, and a recomputed environment digest must match exactly. Source digest
  uses sorted-key compact JSON and UTC fixed six-digit microseconds; equivalent instants match and
  one-microsecond differences do not. Evidence is then reconstructed through the public Phase B
  contract, which independently regenerates its canonical evidence digest.
- Result boundary: acceptance means only safe fixture validation and evidence construction. It is
  not manual-validation execution, evidence approval, registry eligibility/admission, registry
  mutation, or runtime authorization. Rejected results contain no evidence or partial object.
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
