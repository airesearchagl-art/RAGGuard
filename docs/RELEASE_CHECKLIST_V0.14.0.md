# RAGGuard v0.14.0 Release Checklist

## Verification

- [ ] Full pytest succeeds.
- [ ] v0.14 contract, evaluator, Security E2E, and release-contract suites succeed.
- [ ] v0.13, v0.12, v0.11, and v0.10 targeted suites succeed.
- [ ] Compatibility, profile integration, and HTTP security suites succeed.
- [ ] `python -m ragguard check-mask --help` succeeds.
- [ ] `python -m ragguard benchmark --help` succeeds.
- [ ] `python -m compileall -q src tests` succeeds.
- [ ] Workflow YAML parses and Python 3.11 / 3.12 Actions succeed.
- [ ] `git diff --check` and bidi/CR-only/null-byte scans succeed.
- [ ] Secret, credential, URL, IP, absolute-path, and real-product scans find no added unsafe data.

## Boundary

- [x] Candidate is not authorized, active, or production-enabled.
- [x] Synthetic-only evidence is not production readiness evidence.
- [x] No manual validation was performed.
- [x] No production profile or real production-registry entry was added.
- [x] No persistence, runtime activation, token, credential, transport, or HTTP path was added.
- [x] Denials leave write, mutation, transport, HTTP, persistence, and activation counts at zero.
- [x] CLI exit codes and report top-level schema remain unchanged.

## Post-merge operations

- [ ] Synchronize clean `main` with `origin/main`.
- [ ] Create an annotated `v0.14.0` tag pointing directly to the Phase merge commit.
- [ ] Push the tag and verify its peeled target.
- [ ] Publish the GitHub Release as a separate operation.
- [ ] Record the release in the Vault using a separate approved PR.
