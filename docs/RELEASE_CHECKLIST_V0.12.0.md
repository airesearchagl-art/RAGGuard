# RAGGuard v0.12.0 Release Checklist

This checklist prepares v0.12.0 without creating a tag or GitHub Release. Tagging, Release
publication, and Vault recording remain separate post-merge operations.

## Release boundary

- Post-admission lifecycle governance applies only to the in-memory test-only registry contract.
- Revalidation required is not approval; suspension is not revocation; revoked is terminal.
- No automatic active recovery, rollback, replacement, fallback, nearest-version selection, or
  schema inference.
- Replacement requires fresh evidence, review, approval, admission decision, and admission.
- No production profile, real production-registry entry/write, persistence, runtime authorization,
  manual validation, real-product connection, credential, real document, or external/private-LAN
  access.
- No transport, HTTP, workflow, or Node runtime warning maintenance change.

## Required checks

- [ ] Full `python -m pytest` succeeds.
- [ ] v0.12 targeted suites succeed:
  - `tests/test_revalidation_contract.py`
  - `tests/test_registry_lifecycle_governance.py`
  - `tests/test_registry_lifecycle_security_e2e.py`
  - `tests/test_v012_contract.py`
- [ ] v0.11 Phase A-E suites succeed.
- [ ] v0.10 Phase A-E suites succeed.
- [ ] Compatibility, profile integration, and HTTP security suites succeed.
- [ ] `python -m ragguard check-mask --help` succeeds.
- [ ] `python -m ragguard benchmark --help` succeeds.
- [ ] `python -m compileall -q src tests` succeeds.
- [ ] Workflow YAML parses without workflow edits.
- [ ] `git diff --check` succeeds.
- [ ] Bidi-control, CR-only, null-byte, secret/credential, URL/IP/absolute-path, and real-product
  pattern scans succeed for the v0.12 diff.
- [ ] GitHub Actions Python 3.11 and 3.12 succeed.

## Pre-tag gate after merge

- [ ] Record the normal merge commit and synchronize clean local `main` with `origin/main`.
- [ ] Confirm tracked working tree is clean.
- [ ] Rerun full, targeted, regression, CLI, compile, workflow, diff, and security checks.
- [ ] Confirm no v0.12.0 tag or GitHub Release exists.
- [ ] Create an annotated tag pointing directly to the v0.12 merge commit only after a separate
  explicit request.

## Release notes draft

Highlights:

- Immutable exact-bound revalidation and lifecycle contracts.
- Deterministic fail-closed requirement priority and one-way transitions.
- Terminal revocation and no automatic active recovery.
- Atomic test-only lifecycle mutation with zero denial side effects.
- Full-chain synthetic Security E2E.

Limitations:

- No production operation, persistence, runtime authorization, manual validation, real-product
  evidence/connection, credentials, real documents, or external/private-LAN access.
- Test-only lifecycle mutation is not runtime production authorization.
