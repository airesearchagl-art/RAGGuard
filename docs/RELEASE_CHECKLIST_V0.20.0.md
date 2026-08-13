# RAGGuard v0.20.0 Release Checklist

## Verification

- [ ] Full pytest and v0.20 targeted suites succeed.
- [ ] v0.10-v0.19 regressions and compatibility/profile/HTTP security suites succeed.
- [ ] CLI help, compileall, workflow YAML parse, and `git diff --check` succeed.
- [ ] Bidi, CR-only, null-byte, secret, credential, unsafe URL/IP/path, and real-data scans pass.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.

## Boundary

- [ ] Controlled fixture only; no real-world production-validation claim.
- [ ] No filesystem or database persistence and no external storage.
- [ ] No production registry write.
- [ ] No runtime activation or runtime switch.
- [ ] No network, transport, or HTTP integration.
- [ ] No credentials, tokens, real documents, or real-product connection.
- [ ] `validation_completed` is not production authorization or an active runtime.

## Release operation

- [ ] Main and origin/main are synchronized and tracked files are clean.
- [ ] Annotated tag points directly to the Phase merge commit.
- [ ] Tag push and GitHub Release publication are separate post-merge operations.
- [ ] Vault update is a separate post-release PR.
