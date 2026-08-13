# RAGGuard v0.19.0 Release Checklist

## Verification

- [ ] Full pytest succeeds on the merge commit.
- [ ] v0.19 contract, recovery, Security E2E, and release-contract suites succeed.
- [ ] v0.18 through v0.10 targeted suites succeed.
- [ ] Compatibility, profile integration, and HTTP security suites succeed.
- [ ] CLI help, compileall, workflow YAML parsing, and `git diff --check` succeed.
- [ ] Python 3.11 / 3.12 GitHub Actions succeed.
- [ ] Bidi/CR-only/null-byte, secret/credential, URL/IP/path, and real-data scans pass.

## Boundary

- [x] persistence authorized != durable write completed
- [x] durable write completed != runtime active
- [x] recovery completed != runtime active
- [x] persisted record != production registry active
- [x] Exact v0.18 source, policy, generation, predecessor, and store-state binding.
- [x] Successful-only replay consumption and atomic single-swap test simulator.
- [x] No filesystem/DB/external storage API, runtime switch, registry write, credential, or token.
- [x] CLI exit codes unchanged.
- [x] report top-level schema unchanged.

## Post-merge operations

- [ ] Synchronize clean `main` with `origin/main`.
- [ ] Create an annotated `v0.19.0` tag at the merge commit.
- [ ] Push and verify the peeled target.
- [ ] Publish GitHub Release as a separate operation.
- [ ] Record the release through a separate approved Vault PR.
