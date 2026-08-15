# RAGGuard v0.25.0 Release Checklist

## Fixed semantic boundaries

- [ ] trial approved != real-data access authorized
- [ ] access authorized != actual real-data read
- [ ] operator assigned != access authorized
- [ ] eligible_for_limited_real_data_read_execution != read executed
- [ ] read authorization != persistence authorization
- [ ] read authorization != runtime activation

## Selector and policy

- [ ] Selector is metadata-only and contains no actual location, identity, or raw identifier.
- [ ] Only `internal_low` / `internal_low_document_candidate` is accepted.
- [ ] Stage ceiling is `chunking_candidate`; embedding and downstream stages are prohibited.
- [ ] Document count, byte class, and allowed read count cannot widen beyond one safe candidate.
- [ ] Raw retention, raw logging, raw cache, persistence, export, and network remain prohibited.

## Source chain and independent authorization

- [ ] Actual v0.24 trial record, scope, policies, reviews, approval, environment approval, and
      approved session are canonical and exact-bound.
- [ ] Trial remains approved, live, unrevoked, and unsuperseded.
- [ ] Access security review and data-governance review are independent.
- [ ] Real-data operator assignment is explicit and distinct from access approval.
- [ ] Trial requester/approver, session operator, access requester/reviewers/operator/approver are
      pairwise distinct.

## Registry, usage, lifecycle, replay, and time

- [ ] Test-only registry uses immutable candidate state and successful-only atomic swap.
- [ ] Generation is monotonic and predecessor exact-bound.
- [ ] Request, reviews, operator assignment, approval, and record are consumed only on success.
- [ ] Denial and injected faults leave state and replay sets unchanged and remain retryable.
- [ ] Allowed and remaining read count start at one; no public decrement/reset/refill API exists.
- [ ] Expired, revoked, exhausted, and superseded authorizations are not reusable.
- [ ] Explicit UTC evaluation time and strict temporal ordering reject future or expired metadata.

## Zero-effects and compatibility

- [ ] Actual file open/read and real-data access counts are zero.
- [ ] Filesystem, DB, persistent-vector, production-registry write counts are zero.
- [ ] External network, HTTP, cloud, credential, and token counts are zero.
- [ ] Runtime activation and switch counts are zero.
- [ ] No persistent Vector DB or real-material directory access occurs.
- [ ] CLI exit codes and report schema are unchanged.
- [ ] v0.10-v0.24 regression and governance contracts pass.
- [ ] Full pytest, targeted suites, CLI help, compileall, workflow YAML, diff, and safety scans pass.

Actual read execution remains v0.26-or-later work. A v0.25 authorization record and eligible
readiness decision do not execute a read, authorize persistence, or activate a runtime.
