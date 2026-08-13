# RAGGuard v0.18.0 Release Checklist

## Verification

- [ ] Full pytest succeeds on the merge commit.
- [ ] v0.18 runtime authorization, activation commit, Security E2E, and release-contract suites succeed.
- [ ] v0.17 through v0.10 targeted suites succeed.
- [ ] Compatibility, profile integration, and HTTP security suites succeed.
- [ ] CLI help, compileall, workflow YAML parsing, and `git diff --check` succeed.
- [ ] Python 3.11 / 3.12 GitHub Actions succeed.
- [ ] Bidi/CR-only/null-byte, secret/credential, URL/IP/path, and real-data scans pass.

## Contract boundary

- [x] Exact v0.14–v0.17 source-chain and v0.15 persistence/activation-plan binding.
- [x] Independent runtime request, review, approval, and commit stages.
- [x] Role separation, explicit UTC microseconds, fail-closed replay and lifecycle gates.
- [x] Successful-only replay consumption and atomic single-swap test ledger.
- [x] `ready_for_runtime_authorization_commit != active`.
- [x] `authorization_committed != active`.
- [x] No runtime switch, activation API, token, credential, real persistence, registry write,
  production profile, transport, HTTP, real product, real data, external API/cloud/private LAN.
- [x] CLI exit codes and report top-level schema remain unchanged.

## Post-merge operations

- [ ] Synchronize clean `main` with `origin/main`.
- [ ] Create an annotated `v0.18.0` tag at the Phase merge commit.
- [ ] Push the tag and verify its peeled target.
- [ ] Publish GitHub Release as a separate operation.
- [ ] Record the release through a separate approved Vault PR.
