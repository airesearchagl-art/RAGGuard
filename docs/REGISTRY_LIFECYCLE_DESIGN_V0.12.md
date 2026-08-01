# RAGGuard v0.12 Registry Lifecycle Governance

## Scope

v0.12 is post-admission lifecycle governance for an already admitted entry in the
test-only registry contract. It generates deterministic revalidation requirements and applies
one-way lifecycle transitions without adding production operation, persistence, transport, HTTP,
credentials, real documents, or runtime production authorization.

The implementation is deliberately limited to safe synthetic fixtures and in-memory test-only
state. A successful lifecycle transition is not production operation and does not authorize a
runtime connection.

## Contracts

### RevalidationTrigger

`RevalidationTrigger` is immutable, typed, and caller-supplied. It contains an explicit opaque
trigger ID, kind, timezone-aware observed time, exact profile/product/protocol identity, current
entry digest, admission-decision digest, evidence digest, actor opaque ID, allowlisted safe context,
and an evidence expiry boundary when the trigger is `evidence_expired`.

No identifier, time, or digest is generated automatically. Free-form reasons, endpoints, paths,
credentials, raw requests/responses, stack traces, and hidden current time are not accepted.

Trigger kinds:

- `evidence_expired`
- `evidence_revoked`
- `approval_revoked`
- `security_policy_changed`
- `product_version_changed`
- `protocol_version_changed`
- `restriction_changed`
- `scheduled_revalidation`
- `administrator_suspension`
- `administrator_deprecation`
- `administrator_revocation`

### RevalidationRequirement

The requirement evaluator is pure. It performs no registry write, filesystem operation, network
operation, transport call, HTTP call, random generation, UUID generation, or clock read.

Deterministic priority:

1. Identity, digest, temporal, or structural violation: reject without mutation.
2. Valid security-policy change or explicit administrator revocation: `revoke`.
3. Evidence expiry/revocation or approval revocation: `suspend` and
   `revalidation_required`.
4. Product/protocol/restriction supersession: `deprecate` and
   `revalidation_required`.
5. Scheduled trigger: generate `revalidation_required` without an implicit status transition.
6. Explicit administrator suspension/deprecation: apply the requested one-way status.
7. Valid non-action input: `no_action`.

Ambiguity is fail-closed. A malformed or mismatched trigger cannot revoke or otherwise mutate an
entry merely because it claims a severe condition.

## Exact identity and digest binding

Lifecycle evaluation requires exact equality for:

- profile ID and version;
- protocol version;
- product ID and version;
- current registry-entry digest;
- admission-decision digest;
- evidence digest;
- active test-registry identity;
- expected current status and restrictions;
- trigger actor and lifecycle registry-administrator identity.

The evaluator recalculates the digest-covered admission decision and admission request before
using their identity and role chain. Request-only identity substitution is rejected. Fallback,
nearest-version selection, aliases, schema inference, version ranges, and digest omission are not
supported.

## Role separation

The lifecycle actor is the explicit registry administrator in the request and must exactly match
the trigger actor. It must be distinct from the digest-bound validation operator, evidence
reviewer, and approver. This also rejects self-issued evidence invalidation.

Safe summaries are disclosure-bounded metadata and are never used as a substitute for the
canonical decision/entry identity chain.

## Temporal boundary

Only the request's explicit timezone-aware `evaluation_time` is used:

```text
admission decision evaluated_at
<= trigger observed_at
<= lifecycle evaluation_time
```

An `evidence_expired` trigger additionally requires the exact admission-bound evidence expiry and
is valid only at or after that boundary. Future triggers are rejected. UTC normalization preserves
fixed six-digit microsecond precision; equivalent instants have identical canonical values and a
one-microsecond difference produces a different digest.

## Lifecycle request

`RegistryLifecycleRequest` is immutable and digest-covered. It contains:

- lifecycle request ID;
- explicit evaluation time;
- immutable trigger;
- expected current status;
- requested status;
- registry administrator opaque ID;
- expected current entry digest;
- expected restrictions;
- allowlisted safe context.

Only `suspended`, `deprecated`, and `revoked` are accepted as requested statuses. `active` is not a
valid target and no automatic recovery/reactivation API exists.

## Allowed transitions

Allowed:

| Current | Requested |
|---|---|
| `active` | `suspended` |
| `active` | `deprecated` |
| `active` | `revoked` |
| `suspended` | `deprecated` |
| `suspended` | `revoked` |
| `deprecated` | `revoked` |

Forbidden:

- `suspended -> active`;
- `deprecated -> active`;
- `deprecated -> suspended`;
- every transition from `revoked`;
- a second `revoked -> revoked` commit;
- same-status no-op writes;
- implicit transition, automatic recovery, automatic rollback, and automatic reactivation.

`revoked` is terminal. Suspension is not revocation.

## Atomic test-only transition

The operation is separated into:

1. validate all structural, identity, digest, role, temporal, status, and boundary gates;
2. construct the replacement immutable entry, event, and result;
3. commit exactly once to the test-only in-memory registry.

Commit occurs only after every validation succeeds. A denied transition or injected commit failure
leaves lifecycle mutation count, lifecycle event count, lifecycle write count, transport count,
and HTTP count at zero; the entry status is unchanged and no partial transition result is exposed.
Duplicate commits and overwrites are rejected.

The admission entry is replaced immutably only to update status. It preserves admission ID,
profile/product/protocol identity, plan digest, evidence digest, reviewer-attestation digest,
admission-decision digest, restrictions, admission administrator, maturity, and decision.

The lifecycle event records only bounded metadata: original admission identity, previous/new
status, trigger kind/digest, request digest, transition time, actor ID, digest chain, effective
restriction count, original entry digest, and resulting entry digest. Raw plan/evidence/fixture,
endpoint, path, credential, request/response, stack trace, and internal exception are excluded.

## Test-only registry boundary

Lifecycle mutation accepts only `TestRegistryLifecycleStore`, which wraps the existing
`TestRegistryAdmissionStore`. A `TrustedProductionRegistry` or other object is rejected before any
write. No production mutation API, persistent registry, filesystem-backed registry, database, or
runtime authorization path is added.

The statuses `suspended`, `deprecated`, and `revoked` are states of the test-only registry contract.
Reflecting them into a real production registry requires separate design and explicit approval.

## Revalidation completion boundary

v0.12 ends at requirement generation and one-way status transition. Revalidation required is not
approval, and successful revalidation does not automatically restore `active`.

A replacement requires fresh evidence, a new independent review, a new approval decision, a new
production-admission decision, and a new registry admission. A replacement entry through that new
admission chain is future work; it is not a status rollback.

## Canonical digest

Trigger, request, requirement, and result use separate SHA-256 digests over sorted-key compact JSON:

```text
sha256:<64 lowercase hex>
```

Canonical values include exact identity, status, digest chain, reason categories, and normalized
timestamps. The same input produces the same digest; a field change changes the digest;
timezone-equivalent instants match; and a one-microsecond difference does not collide.

## Safe summary and errors

Safe summaries may contain opaque IDs, trigger kind, applied state, previous/resulting status,
profile/product/protocol identity, digest chain, reason categories, explicit times, and canonical
digest.

They exclude endpoints, ports, paths, queries, hostnames, usernames, credentials, tokens, cookies,
API keys, raw requests/responses, real documents, stack traces, and internal exceptions. Typed error
messages contain only deterministic category values and never echo caller input.

Reason categories are ordered deterministically:

- `trigger_invalid`
- `trigger_not_yet_valid`
- `identity_mismatch`
- `digest_mismatch`
- `role_conflict`
- `status_mismatch`
- `transition_forbidden`
- `already_terminal`
- `duplicate_transition`
- `evidence_expired`
- `evidence_revoked`
- `approval_revoked`
- `security_policy_changed`
- `revalidation_required`
- `registry_kind_invalid`
- `security_boundary_violation`
- `registry_write_rejected`
- `registry_commit_failed`

## Security E2E

The success path builds the existing safe plan/evidence/decision/admission chain, admits it only to
the test registry, evaluates an exact trigger, atomically transitions status, and confirms the new
status by exact resolution with transport/HTTP counts remaining zero.

Denial coverage includes future trigger, identity mismatch, digest tampering, role conflict,
expected-status mismatch, forbidden/terminal/duplicate transition, production registry attempt,
fallback, nearest-version, schema inference, and automatic active recovery. Each denial preserves
entry status and produces zero lifecycle mutations, events, writes, transport calls, and HTTP calls.

## Unchanged compatibility and release boundary

- CLI exit codes `0 / 1 / 2 / 3` are unchanged.
- The report top-level schema is unchanged.
- v0.9 Compatibility Profile, v0.10 approval enforcement, and v0.11 admission contracts remain.
- No workflow or Node runtime warning maintenance is included.
- No manual validation was performed.
- No production profile or real production registry entry exists.
- No registry persistence or real-product compatibility evidence exists.
- No real-product connection, credentials, real documents, or external/private-LAN access occurs.
