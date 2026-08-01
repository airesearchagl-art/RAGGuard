# RAGGuard v0.11.0 Release Checklist

Use this checklist for the Phase F pull request and repeat the pre-tag gate after its normal merge
commit. Phase F prepares the release; it does not create a tag, publish a GitHub Release, update the
Vault, or expand production/runtime scope.

## Release boundary

- Synthetic safe fixtures only; no manual validation was performed.
- No production profile, real production-registry entry, registry persistence, or runtime
  production authorization.
- No runtime production authorization; test-registry admission grants no production use.
- No real-product compatibility evidence or connection, credentials, real documents, or
  external/private-LAN access.
- Phase D/E add no filesystem, network, subprocess, transport, or HTTP operation.
- Fail closed with exact identity, role, version, digest, and time binding.
- No fallback, nearest-version selection, schema inference, automatic approval, automatic
  recovery, or automatic rollback.
- Synthetic fixtures are not evidence of real-product compatibility. Test-only registry admission
  is not runtime production authorization.

## Phase F PR verification

- [ ] `python -m pytest` succeeds.
- [ ] Phase A-E suites succeed:
  - `tests/test_manual_validation_plan_contract.py`
  - `tests/test_manual_validation_evidence_contract.py`
  - `tests/test_production_admission_evaluator.py`
  - `tests/test_manual_evidence_import_boundary.py`
  - `tests/test_registry_admission_enforcement.py`
  - `tests/test_registry_admission_security_e2e.py`
- [ ] v0.10 approval suites succeed:
  - `tests/test_profile_approval_contract.py`
  - `tests/test_validation_report_contract.py`
  - `tests/test_production_registry_contract.py`
  - `tests/test_synthetic_approval_workflow.py`
  - `tests/test_approval_enforcement_security_e2e.py`
- [ ] Compatibility and security suites succeed:
  - `tests/test_compatibility_contract.py`
  - `tests/test_compatibility_profile_integration_e2e.py`
  - `tests/test_http_transport_security_e2e.py`
- [ ] `python -m ragguard check-mask --help` and `python -m ragguard benchmark --help` succeed.
- [ ] `python -m compileall -q src tests` and `git diff --check` succeed.
- [ ] Workflow YAML parses successfully.
- [ ] Bidi-control, CR-only, null-byte, secret/credential, URL/IP/absolute-path, and real-product
  scans succeed for the Phase F diff.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.
- [ ] Limitations and unchanged compatibility behavior are documented.

## Pre-tag gate after Phase F merge

- [ ] Fetch `origin` and fast-forward local `main`.
- [ ] Confirm `main == origin/main` and both point to the Phase F merge commit.
- [ ] Confirm `git status --short --untracked-files=no` is empty.
- [ ] Confirm the Phase F PR is merged and its Actions run succeeded.
- [ ] Rerun full pytest, targeted Phase A-E, security E2E, CLI help, and static checks.
- [ ] Record the exact Phase F merge commit as `<phase-f-merge-sha>`.
- [ ] Confirm no `v0.11.0` tag or GitHub Release was created by the Phase F PR.

## Separate annotated tag operation

The annotated tag must point directly to the Phase F merge commit:

```powershell
git switch main
git fetch origin main --tags
git merge --ff-only origin/main
git status --short --untracked-files=no
git tag -a v0.11.0 <phase-f-merge-sha> -m "RAGGuard v0.11.0"
git show --no-patch --format=fuller v0.11.0
git rev-parse v0.11.0^{}
git push origin v0.11.0
```

Verify the tag object and peeled target remotely before any Release operation. Do not move,
replace, or recreate the tag.

## Separate GitHub Release operation

Create title `RAGGuard v0.11.0` from the verified tag with `published=true`, `draft=false`,
`prerelease=false`, and `latest=true`. Tag push and GitHub Release publication are separate
explicit operations.

### Release notes draft

Highlights:

- Immutable manual-validation plan and evidence contracts with exact plan/evidence binding.
- Structural and temporal evidence validity with a maximum 90-day evidence lifetime.
- Pure deterministic production-admission evaluator and strict review-before-approval ordering.
- Offline inline safe-fixture import with structural allowlist priority and separate source/evidence
  digests.
- Test-only atomic registry admission, exact resolve, decision-bound identity/role chain, and
  denial-before-entry/write/event/transport/HTTP security E2E.

Limitations:

- No performed manual validation, production profile, real production-registry entry, persistence,
  real-product connection, credentials, real documents, or external/private-LAN access.
- Synthetic fixtures are not evidence of real-product compatibility.
- Registry admission success is not runtime production authorization.

## Separate post-release recording

Create a separate post-release Vault pull request. An optional Notion milestone may link the Phase
F PR, merge commit, tag, Release URL, checks, unchanged security boundary, and compatibility status
without copying raw logs, endpoints, paths, credentials, or real-product details.
