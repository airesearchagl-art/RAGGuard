# RAGGuard v0.17.0 Release Checklist

## Verification

- [ ] Full pytest succeeds on the merge commit.
- [ ] v0.17 assessment, attestation, Security E2E, and release-contract suites succeed.
- [ ] v0.16, v0.15, v0.14, v0.13, v0.12, v0.11, and v0.10 targeted suites succeed.
- [ ] Compatibility, profile integration, and HTTP security suites succeed.
- [ ] `python -m ragguard check-mask --help` and `python -m ragguard benchmark --help` succeed.
- [ ] `python -m compileall -q src tests` and workflow YAML parsing succeed.
- [ ] Python 3.11 / 3.12 GitHub Actions succeed.
- [ ] `git diff --check`, bidi/CR-only/null-byte, secret, URL/IP/path, and real-product scans pass.

## Contract boundary

- [x] Synthetic or controlled manual evidence is not production-equivalent by declaration.
- [x] The complete v0.16 plan/execution/evidence/review/approval source is exact-bound.
- [x] Criteria, descriptor, environment, configuration, protocol, behavior, and provenance bind.
- [x] Required cases have no skip, failure, or unresolved divergence.
- [x] Assessment, independent review, and approval are distinct stages and actors.
- [x] Six manual/equivalence actors are separated from protected downstream roles.
- [x] Successful chains are replay-protected; failed attempts consume no replay state.
- [x] Explicit UTC microsecond time rejects future, stale, and expired inputs.
- [x] Denial has zero write/mutation/persistence/filesystem/DB/network/HTTP/activation effects.
- [x] Equivalence approval is not runtime authorization or activation.
- [x] No real product, endpoint, data, credential, persistence, registry write, or activation.
- [x] CLI exit codes and report top-level schema remain unchanged.

## Post-merge operations

- [ ] Synchronize clean `main` with `origin/main`.
- [ ] Create an annotated `v0.17.0` tag at the Phase merge commit.
- [ ] Push the tag and verify its peeled target.
- [ ] Publish GitHub Release as a separate operation.
- [ ] Record the release through a separate approved Vault PR.
