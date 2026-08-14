# RAGGuard v0.21.0 Release Checklist

## Required verification

- [ ] Full pytest succeeds.
- [ ] v0.21 contract, attestation, Security E2E, and release-contract suites succeed.
- [ ] All ten capability claims are object-backed by exact manifest-bound conformance results.
- [ ] Boolean claims and caller-supplied matching digests cannot independently pass conformance.
- [ ] v0.20 through v0.10 regression suites succeed.
- [ ] Compatibility, profile integration, and HTTP security suites succeed.
- [ ] `python -m ragguard check-mask --help` succeeds.
- [ ] `python -m ragguard benchmark --help` succeeds.
- [ ] `python -m compileall -q src tests` succeeds.
- [ ] Workflow YAML parses.
- [ ] `git diff --check` succeeds.
- [ ] GitHub Actions Python 3.11 / 3.12 succeeds.
- [ ] Main and origin/main are synchronized and tracked status is clean before a tag.
- [ ] CLI exit codes remain unchanged.
- [ ] Report top-level schema remains unchanged and compatibility contracts pass.

## Contract boundaries

- [ ] candidate ≠ approved.
- [ ] approved_for_write_authorization_review ≠ write_authorized.
- [ ] write_authorized ≠ write_executed.
- [ ] durable_write_completed ≠ runtime_active.
- [ ] `ready_for_write_authorization_review` is not write authority.
- [ ] Actual adapter operation is not implemented.
- [ ] No filesystem, DB, external storage, network, HTTP, credential, or token operation.
- [ ] No production registry write, runtime activation, runtime switch, or real-data access.
- [ ] No fallback, nearest-version selection, schema inference, or automatic reactivation.

## Post-merge operations

- [ ] An annotated `v0.21.0` tag points directly to the merge commit.
- [ ] Tag push and GitHub Release publication are separate operations.
- [ ] The GitHub Release is published, non-draft, non-prerelease, and latest.
- [ ] Vault update is a separate post-release PR.
