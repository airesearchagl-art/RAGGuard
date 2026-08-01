from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
DESIGN = ROOT / "docs" / "REGISTRY_LIFECYCLE_DESIGN_V0.12.md"
CHECKLIST = ROOT / "docs" / "RELEASE_CHECKLIST_V0.12.0.md"
README = ROOT / "README.md"
USAGE = ROOT / "docs" / "USAGE.md"
ROADMAP = ROOT / "ROADMAP.md"
CHANGELOG = ROOT / "CHANGELOG.md"
DESIGN_NOTES = ROOT / "docs" / "DESIGN_NOTES.md"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v012_design_and_release_checklist_exist() -> None:
    assert DESIGN.is_file()
    assert CHECKLIST.is_file()


def test_allowed_transitions_are_documented() -> None:
    content = text(DESIGN)
    for transition in (
        "`active` | `suspended`",
        "`active` | `deprecated`",
        "`active` | `revoked`",
        "`suspended` | `deprecated`",
        "`suspended` | `revoked`",
        "`deprecated` | `revoked`",
    ):
        assert transition in content


def test_forbidden_recovery_and_terminal_revocation_are_documented() -> None:
    content = text(DESIGN).lower()
    assert "`revoked` is terminal" in content
    assert "automatic recovery" in content
    assert "automatic rollback" in content
    assert "automatic reactivation" in content
    assert "`suspended -> active`" in content
    assert "`deprecated -> active`" in content


def test_test_only_registry_and_production_non_goals_are_documented() -> None:
    content = text(DESIGN).lower()
    for phrase in (
        "test-only registry contract",
        "no production mutation api",
        "persistent registry",
        "filesystem-backed registry",
        "runtime authorization",
        "separate design and explicit approval",
    ):
        assert phrase in content


def test_revalidation_completion_is_not_active_rollback() -> None:
    content = " ".join(text(DESIGN).lower().split())
    assert "revalidation required is not approval" in content
    assert "successful revalidation does not automatically restore `active`" in content
    for phrase in (
        "fresh evidence",
        "new independent review",
        "new approval decision",
        "new production-admission decision",
        "new registry admission",
    ):
        assert phrase in content


def test_atomic_denial_contract_is_documented() -> None:
    content = text(DESIGN).lower()
    assert "validate all structural" in content
    assert "construct the replacement immutable entry" in content
    assert "commit exactly once" in content
    assert "lifecycle mutation count" in content
    assert "transport count" in content
    assert "http count" in content


def test_cli_exit_codes_and_report_schema_are_unchanged() -> None:
    combined = "\n".join((text(README), text(USAGE), text(DESIGN), text(CHECKLIST)))
    assert "`0` / `1` / `2` / `3`" in combined
    assert "report top-level schema" in combined.lower()
    assert "adds no cli command" in combined.lower()


def test_node_runtime_warning_maintenance_is_explicitly_separate() -> None:
    combined = "\n".join((text(DESIGN), text(CHECKLIST), text(ROADMAP)))
    assert "Node runtime warning" in combined
    assert "separate CI task" in combined
    assert "No workflow or Node runtime warning maintenance is included" in combined


def test_all_document_responsibilities_are_updated() -> None:
    for path in (README, USAGE, ROADMAP, CHANGELOG, DESIGN_NOTES):
        assert "v0.12" in text(path)
    assert "REGISTRY_LIFECYCLE_DESIGN_V0.12.md" in text(README)
    assert "RELEASE_CHECKLIST_V0.12.0.md" in text(README)


def test_release_checklist_keeps_post_merge_operations_separate() -> None:
    content = " ".join(text(CHECKLIST).split())
    assert "without creating a tag or GitHub Release" in content
    assert "separate post-merge operations" in content
    assert "separate explicit request" in content
