# RAGGuard v0.28.0 Release Checklist

## Source and compatibility

- [ ] Expected base is the reviewed v0.27 release head.
- [ ] Actual v0.25 authorization/operator/usage and v0.27 root-policy-target objects are bound.
- [ ] CLI exit codes and report schema are unchanged.
- [ ] v0.10-v0.27 governance contracts pass regression.

## Root provisioning and target hard gates

- [ ] Purpose is only `local_rag_confidentiality_trial` and closure is mandatory.
- [ ] Root request and identity expose opaque digests, not filesystem locators.
- [ ] Confinement, link/reparse, permission, write-prohibition, and network-isolation result
  objects are canonical, exact-bound, independently observed, and passed.
- [ ] Root descriptor identity and resolver policy match the opaque provisioned root identity.
- [ ] Resolver policy denies symlink, junction, reparse, traversal, and absolute user input.
- [ ] Target selection is exactly one opaque internal-low document candidate.
- [ ] No arbitrary root, directory scan, filename, wildcard, or raw document surface exists.

## Access, approval, replay, and lifecycle

- [ ] v0.25 authorization is live with allowed/remaining usage exactly one.
- [ ] Stage is capped at the chunking candidate and masking is required before it.
- [ ] Retention, logging, cache, persistence are none; export and network are prohibited.
- [ ] Security and governance reviews are independent and execution approval is distinct.
- [ ] Provisioner, verifier, requester, both reviewers, operator, execution approver, and access
  approver are pairwise distinct and exact-bound.
- [ ] Approval record contains root/review/approval/operator/generation/predecessor digests.
- [ ] Only successful approval consumes all nine replay identities in one atomic swap.
- [ ] Denial and injected faults leave registry/replay/counters unchanged and retryable.
- [ ] Expired, revoked, superseded, execution-pending, and closed lifecycle is fail closed.
- [ ] Closure requires receipt, usage exhaustion, classification, masking, evidence, and closure.

## Authority and side effects

- [ ] Trial approval is not an actual read or real-data-use authorization.
- [ ] Execution-review eligibility is not execution, embedding, or persistence approval.
- [ ] Actual and arbitrary file open/read counts are zero.
- [ ] Local RAG material, restricted material, and real-data access counts are zero.
- [ ] External network, HTTP, cloud, credential, and token counts are zero.
- [ ] Filesystem/database/persistent-vector/production-registry writes are zero.
- [ ] Runtime activation and switch counts are zero.

## Validation and publication

- [ ] v0.28 targeted root, contract, Security E2E, and release-contract suites pass.
- [ ] v0.27-v0.22, v0.21-v0.10, compatibility/profile/HTTP, and full pytest pass.
- [ ] CLI help, compileall, workflow YAML parse, and `git diff --check` pass.
- [ ] Bidi, CR-only, null-byte, secret/credential, URL/IP, and unsafe path scans pass or contain
  only reviewed documentation/test denial literals.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.
- [ ] Pull request remains Draft and is not merged.
- [ ] No tag or Release is created.
