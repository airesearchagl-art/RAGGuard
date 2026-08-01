from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]

PHASE_A_E_SUITES = (
    "tests/test_manual_validation_plan_contract.py",
    "tests/test_manual_validation_evidence_contract.py",
    "tests/test_production_admission_evaluator.py",
    "tests/test_manual_evidence_import_boundary.py",
    "tests/test_registry_admission_enforcement.py",
    "tests/test_registry_admission_security_e2e.py",
)

V010_APPROVAL_SUITES = (
    "tests/test_profile_approval_contract.py",
    "tests/test_validation_report_contract.py",
    "tests/test_production_registry_contract.py",
    "tests/test_synthetic_approval_workflow.py",
    "tests/test_approval_enforcement_security_e2e.py",
)

COMPATIBILITY_SECURITY_SUITES = (
    "tests/test_compatibility_contract.py",
    "tests/test_compatibility_profile_integration_e2e.py",
    "tests/test_http_transport_security_e2e.py",
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v011_release_documents_preserve_security_boundary() -> None:
    documents = "\n".join(
        _read(path)
        for path in (
            "README.md",
            "docs/USAGE.md",
            "docs/DESIGN_NOTES.md",
            "docs/PRODUCTION_ADMISSION_DESIGN_V0.11.md",
            "docs/RELEASE_CHECKLIST_V0.11.0.md",
            "CHANGELOG.md",
            "ROADMAP.md",
        )
    ).lower()
    for required in (
        "synthetic safe fixture",
        "no manual validation",
        "no production profile",
        "no registry persistence",
        "no real-product compatibility evidence",
        "no runtime production authorization",
        "no credentials",
        "no real documents",
        "external/private-lan",
        "fail closed",
        "no fallback",
        "nearest-version selection",
        "schema inference",
        "automatic approval",
        "automatic recovery",
        "automatic rollback",
        "not evidence of real-product compatibility",
    ):
        assert required in documents


def test_v011_documents_fix_identity_atomicity_and_compatibility() -> None:
    documents = "\n".join(
        _read(path)
        for path in (
            "README.md",
            "docs/USAGE.md",
            "docs/DESIGN_NOTES.md",
            "docs/RELEASE_CHECKLIST_V0.11.0.md",
        )
    ).lower()
    for required in (
        "decision-bound",
        "review-before-approval",
        "structural validity",
        "temporal",
        "90-day",
        "source digest",
        "evidence digest",
        "test-only",
        "exact resolve",
        "entry, write, event, transport, and http counts at zero",
        "exit codes `0` / `1` / `2` / `3`",
        "report top-level schemas",
        "v0.9 compatibility profile",
        "v0.10 approval enforcement",
    ):
        assert required in documents


def test_v011_release_checklist_keeps_post_merge_operations_separate() -> None:
    checklist = _read("docs/RELEASE_CHECKLIST_V0.11.0.md")
    assert "Phase F merge commit" in checklist
    assert "git tag -a v0.11.0 <phase-f-merge-sha>" in checklist
    assert "git rev-parse v0.11.0^{}" in checklist
    assert "git push origin v0.11.0" in checklist
    assert "published=true" in checklist
    assert "draft=false" in checklist
    assert "prerelease=false" in checklist
    assert "latest=true" in checklist
    assert "separate post-release Vault pull request" in checklist


def test_ci_full_suite_covers_v011_and_existing_security_contracts() -> None:
    workflow = yaml.safe_load(_read(".github/workflows/test.yml"))
    pytest_job = workflow["jobs"]["pytest"]
    assert pytest_job["strategy"]["matrix"]["python-version"] == [
        "3.11",
        "3.12",
    ]
    commands = "\n".join(
        step.get("run", "") for step in pytest_job["steps"]
    )
    assert "python -m pytest" in commands
    assert "python -m ragguard check-mask --help" in commands
    assert "python -m ragguard benchmark --help" in commands
    for path in (
        *PHASE_A_E_SUITES,
        *V010_APPROVAL_SUITES,
        *COMPATIBILITY_SECURITY_SUITES,
    ):
        assert (ROOT / path).is_file()


def test_v011_release_preparation_does_not_define_runtime_artifacts() -> None:
    checklist = _read("docs/RELEASE_CHECKLIST_V0.11.0.md").lower()
    for excluded in (
        "no production profile",
        "real production-registry entry",
        "registry persistence",
        "runtime production authorization",
        "no manual validation was performed",
    ):
        assert excluded in checklist


def test_v011_usage_separates_plan_evidence_review_and_approval() -> None:
    usage = " ".join(_read("docs/USAGE.md").lower().split())
    assert "approved immutable manual-validation plan" not in usage
    assert (
        "immutable manual-validation plan that passes the phase a plan contract"
        in usage
    )
    assert "a valid plan is not approval" in usage
    assert "is not manual evidence" in usage
    assert "a reviewer attestation precedes a decision by a distinct approver" in usage
    assert "approval occurs only at that later decision stage" in usage
    assert "test-registry admission is not runtime production authorization" in usage
