from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v010_release_documents_preserve_security_boundary() -> None:
    documents = "\n".join(
        _read(path)
        for path in (
            "README.md",
            "docs/USAGE.md",
            "docs/DESIGN_NOTES.md",
            "docs/RELEASE_CHECKLIST_V0.10.0.md",
            "CHANGELOG.md",
            "ROADMAP.md",
        )
    ).lower()
    for required in (
        "synthetic",
        "no production",
        "no registry persistence",
        "no real-product connection",
        "no credentials",
        "no real documents",
        "private-lan",
        "fail closed",
        "no fallback",
        "nearest-version",
        "schema inference",
        "not evidence of real-product compatibility",
    ):
        assert required in documents


def test_v010_release_checklist_keeps_tag_and_release_separate() -> None:
    checklist = _read("docs/RELEASE_CHECKLIST_V0.10.0.md")
    assert "Phase F merge commit" in checklist
    assert "git tag -a v0.10.0 <phase-f-merge-sha>" in checklist
    assert "git push origin v0.10.0" in checklist
    assert "GitHub Release" in checklist
    assert "separate post-release Vault pull request" in checklist


def test_ci_matrix_runs_full_suite_on_supported_python_versions() -> None:
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
    assert "tests/test_http_transport_security_e2e.py" in commands
    assert "tests/test_compatibility_profile_integration_e2e.py" in commands
    assert "python -m ragguard check-mask --help" in commands
    assert "python -m ragguard benchmark --help" in commands
