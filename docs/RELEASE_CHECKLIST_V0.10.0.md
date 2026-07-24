# RAGGuard v0.10.0 Release Checklist

Use this checklist to verify the Phase F pull request, then execute its pre-tag gate again after
merge. Phase F prepares the release; it does not create a tag, GitHub Release, production profile,
or public production integration.

## Release boundary

- Synthetic evidence and fake loopback security tests only.
- No production Compatibility Profile or real production-registry entry.
- No registry persistence or performed manual validation.
- No real-product connection, credentials, real documents, external host, or private-LAN access.
- Fail closed with exact profile/version selection.
- No fallback, nearest-version selection, implicit downgrade, or schema inference.
- Synthetic validation is not evidence of real-product compatibility.

## Phase F PR verification

- [ ] `python -m pytest` succeeds.
- [ ] Phase A-E approval suites succeed:
  - `tests/test_profile_approval_contract.py`
  - `tests/test_validation_report_contract.py`
  - `tests/test_production_registry_contract.py`
  - `tests/test_synthetic_approval_workflow.py`
  - `tests/test_approval_enforcement_security_e2e.py`
- [ ] Compatibility and security suites succeed:
  - `tests/test_compatibility_contract.py`
  - `tests/test_compatibility_profile_integration_e2e.py`
  - `tests/test_http_transport_security_e2e.py`
- [ ] `python -m ragguard check-mask --help` succeeds.
- [ ] `python -m ragguard benchmark --help` succeeds.
- [ ] `python -m compileall src tests` succeeds.
- [ ] `git diff --check` succeeds.
- [ ] Workflow YAML parses successfully.
- [ ] Bidi-control, CR-only, fixture-marker, and sensitive-value scans succeed.
- [ ] GitHub Actions succeeds on Python 3.11 and 3.12.

## Pre-tag gate after Phase F merge

- [ ] Fetch `origin` and fast-forward local `main`.
- [ ] Confirm `main` and `origin/main` resolve to the same Phase F merge commit.
- [ ] Confirm `git status --short --untracked-files=no` is empty.
- [ ] Confirm the Phase F PR is merged and its Actions run succeeded.
- [ ] Rerun the full and targeted suites from the synchronized merge commit.
- [ ] Record the exact Phase F merge commit as `<phase-f-merge-sha>`.
- [ ] Confirm no tag or GitHub Release was created by the Phase F PR.

## Separate post-merge operations

The annotated tag must point directly to the Phase F merge commit:

```powershell
git switch main
git fetch origin main
git merge --ff-only origin/main
git status --short --untracked-files=no
git tag -a v0.10.0 <phase-f-merge-sha> -m "RAGGuard v0.10.0"
git show --no-patch --format=fuller v0.10.0
git push origin v0.10.0
```

After the tag push is verified, create the GitHub Release from `v0.10.0` as a separate explicit
operation. Use the v0.10.0 changelog section for release notes and restate the synthetic-only
security boundary.

Create a separate post-release Vault pull request. A Notion milestone entry is optional and must
link to the merged Phase F PR, merge commit, tag, GitHub Release, test evidence, and unchanged
security boundary without copying raw logs or sensitive values.
