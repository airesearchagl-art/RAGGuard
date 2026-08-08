# RAGGuard v0.13.0 Release Checklist

This checklist prepares v0.13.0 without creating a tag or GitHub Release. Tagging, Release
publication, and Vault recording remain separate post-merge operations.

## Release boundary

- Replacement is not reactivation; the inactive predecessor remains unchanged.
- Only suspended or deprecated entries can produce a new active successor. Revoked is terminal.
- Fresh evidence, review, approval, and admission are required; chain reuse is fail-closed.
- No current/latest alias, fallback, nearest-version selection, schema inference, or silent
  identity/restriction migration.
- Test-only in-memory registry; no production write, persistence, or runtime authorization.
- No manual validation, real-product connection, credential, real document, external/private-LAN,
  transport, HTTP, workflow, or Node runtime warning change.
- CLI exit codes `0` / `1` / `2` / `3` and report top-level schemas remain unchanged; this feature
  adds no CLI command.

## Required checks

- [ ] Full `python -m pytest` succeeds.
- [ ] All v0.13 contract, enforcement, Security E2E, and release-contract suites succeed.
- [ ] v0.12 lifecycle and revalidation suites succeed.
- [ ] v0.11 Phase A-E suites succeed.
- [ ] v0.10 Phase A-E suites succeed.
- [ ] Compatibility, profile integration, and HTTP security suites succeed.
- [ ] `python -m ragguard check-mask --help` succeeds.
- [ ] `python -m ragguard benchmark --help` succeeds.
- [ ] `python -m compileall -q src tests` succeeds.
- [ ] Workflow YAML parses without workflow edits.
- [ ] `git diff --check` succeeds.
- [ ] Bidi-control, CR-only, null-byte, secret/credential, URL/IP/absolute-path, and real-product
  scans succeed for the v0.13 diff.
- [ ] GitHub Actions Python 3.11 and 3.12 succeed.

## Pre-tag gate after merge

- [ ] Record the normal merge commit and synchronize clean local `main` with `origin/main`.
- [ ] Confirm tracked working tree is clean and rerun all release checks.
- [ ] Confirm no v0.13.0 tag or GitHub Release exists.
- [ ] Create an annotated tag pointing directly to the merge commit only after a separate request.

## Release notes draft

Highlights:

- Immutable exact-bound replacement request, decision, entry, event, and result contracts.
- Fresh evidence/review/approval/admission chain with decision-bound role separation.
- New active successor while the suspended/deprecated predecessor remains immutable.
- Atomic test-only state-bundle commit, replay protection, and zero denial side effects.
- Full-chain synthetic Security E2E.

Limitations:

- No production operation, persistence, runtime authorization, manual validation, real-product
  evidence/connection, credentials, real documents, or external/private-LAN access.
- Test-only replacement admission is not runtime production authorization.
