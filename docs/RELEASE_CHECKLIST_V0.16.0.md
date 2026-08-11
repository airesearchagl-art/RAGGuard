# RAGGuard v0.16.0 Release Checklist

## Verification

- [ ] Full pytest succeeds on the merge commit.
- [ ] v0.16 execution, evidence/review, Security E2E, and release-contract suites succeed.
- [ ] v0.15, v0.14, v0.13, v0.12, v0.11, and v0.10 targeted suites succeed.
- [ ] Compatibility, profile integration, and HTTP security suites succeed.
- [ ] `python -m ragguard check-mask --help` and `python -m ragguard benchmark --help` succeed.
- [ ] `python -m compileall -q src tests` and workflow YAML parsing succeed.
- [ ] Python 3.11 / 3.12 GitHub Actions succeed.
- [ ] `git diff --check`, bidi/CR-only/null-byte, secret, URL/IP/path, and real-product scans pass.

## Contract boundary

- [x] Plan validity, execution, evidence, review, and approval are distinct stages.
- [x] Required case sets and all predecessor digests bind exactly.
- [x] Requester, operator, evidence creator, reviewer, and approver are distinct.
- [x] Execution and chain commits use candidate-state/single-swap semantics.
- [x] Failed attempts consume no replay state and remain retryable.
- [x] Successful request, record, evidence, review, and approval replay is rejected.
- [x] An approved claim without the complete digest chain is insufficient.
- [x] Controlled offline evidence is not production-equivalent evidence.
- [x] Denial leaves registry/write/mutation/persistence/filesystem/DB/network/HTTP/activation zero.
- [x] No real product, real data, credential, transport, persistence, registry write, or activation.
- [x] CLI exit codes and report top-level schema remain unchanged.

## Post-merge operations

- [ ] Synchronize clean `main` with `origin/main`.
- [ ] Create an annotated `v0.16.0` tag at the Phase merge commit.
- [ ] Push the tag and verify its peeled target.
- [ ] Publish GitHub Release as a separate operation.
- [ ] Record the release through a separate approved Vault PR.
