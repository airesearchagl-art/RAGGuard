# RAGGuard v0.15.0 Release Checklist

## Verification

- [ ] Full pytest succeeds on the merge commit.
- [ ] v0.15 persistence, activation evaluator, Security E2E, and release-contract suites succeed.
- [ ] v0.14, v0.13, v0.12, v0.11, and v0.10 targeted suites succeed.
- [ ] Compatibility, profile integration, and HTTP security suites succeed.
- [ ] `python -m ragguard check-mask --help` succeeds.
- [ ] `python -m ragguard benchmark --help` succeeds.
- [ ] `python -m compileall -q src tests` succeeds.
- [ ] Workflow YAML parses and Python 3.11 / 3.12 Actions succeed.
- [ ] `git diff --check` and bidi/CR-only/null-byte scans succeed.
- [ ] Secret, credential, URL, IP, absolute-path, and real-product scans find no unsafe additions.

## Boundary

- [x] `ready_for_activation_commit` is not active or runtime-authorized.
- [x] Persistence is a test-only in-memory semantic contract.
- [x] Activation requires an exact store-issued commit receipt, approved policy, persisted record,
  and current store snapshot; no self-declared persistence boolean is trusted.
- [x] Failed persistence commits issue no receipt and leave the atomic state bundle unchanged.
- [x] No runtime activation API, runtime switch, token, or credential generation exists.
- [x] No filesystem, database, external-storage, or production-registry write exists.
- [x] Synthetic-only evidence cannot reach the commit-plan result.
- [x] No manual validation or real-product compatibility validation was performed.
- [x] All evaluator side-effect counts remain zero.
- [x] CLI exit codes and report top-level schema remain unchanged.

## Post-merge operations

- [ ] Synchronize clean `main` with `origin/main`.
- [ ] Create an annotated `v0.15.0` tag pointing directly to the Phase merge commit.
- [ ] Push the tag and verify its peeled target.
- [ ] Publish the GitHub Release as a separate operation.
- [ ] Record the release in the Vault using a separate approved PR.
