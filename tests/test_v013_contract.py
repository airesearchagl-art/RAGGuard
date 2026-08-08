from pathlib import Path


ROOT = Path(__file__).parents[1]
DESIGN = ROOT / "docs" / "REPLACEMENT_ADMISSION_DESIGN_V0.13.md"
CHECKLIST = ROOT / "docs" / "RELEASE_CHECKLIST_V0.13.0.md"
README = ROOT / "README.md"
USAGE = ROOT / "docs" / "USAGE.md"
ROADMAP = ROOT / "ROADMAP.md"
CHANGELOG = ROOT / "CHANGELOG.md"
DESIGN_NOTES = ROOT / "docs" / "DESIGN_NOTES.md"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v013_design_and_release_checklist_exist() -> None:
    assert DESIGN.is_file()
    assert CHECKLIST.is_file()


def test_replacement_is_not_reactivation_and_revoked_is_terminal() -> None:
    content = text(DESIGN).lower()
    assert "replacement is not reactivation" in content
    assert "revoked is terminal" in content
    assert "predecessor remains unchanged" in content
    assert "active successor" in content


def test_fresh_chain_and_reuse_boundary_are_documented() -> None:
    content = text(DESIGN).lower()
    for phrase in (
        "fresh evidence",
        "review",
        "approval",
        "admission",
        "distinct from the predecessor chain",
        "chain reuse",
    ):
        assert phrase in content


def test_exact_resolution_has_no_automatic_selection() -> None:
    content = text(DESIGN).lower()
    for phrase in (
        "current/latest",
        "fallback",
        "nearest-version",
        "schema inference",
        "never hides the predecessor",
    ):
        assert phrase in content


def test_test_only_and_production_non_goals_are_fixed() -> None:
    combined = "\n".join((text(DESIGN), text(CHECKLIST))).lower()
    for phrase in (
        "test-only",
        "no production",
        "persistence",
        "runtime production authorization",
        "no manual validation",
        "real-product connection",
    ):
        assert phrase in combined


def test_cli_and_report_compatibility_are_unchanged() -> None:
    combined = "\n".join((text(DESIGN), text(CHECKLIST)))
    assert "`0` / `1` / `2` / `3`" in combined
    assert "report top-level schema" in combined.lower()
    assert "adds no CLI command" in combined


def test_node_warning_work_is_out_of_scope() -> None:
    combined = "\n".join((text(DESIGN), text(CHECKLIST), text(ROADMAP)))
    assert "Node runtime warning" in combined
    assert "separate CI task" in combined


def test_all_document_responsibilities_are_updated() -> None:
    for path in (README, USAGE, ROADMAP, CHANGELOG, DESIGN_NOTES):
        assert "v0.13" in text(path)
    assert "REPLACEMENT_ADMISSION_DESIGN_V0.13.md" in text(README)


def test_release_operations_remain_separate() -> None:
    content = " ".join(text(CHECKLIST).split())
    assert "without creating a tag or GitHub Release" in content
    assert "separate post-merge operations" in content
    assert "separate request" in content
