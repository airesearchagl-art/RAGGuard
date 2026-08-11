from __future__ import annotations

import ast
from pathlib import Path

from ragguard.manual_validation_execution import ManualEvidenceKind


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_approved_manual_validation_requires_full_evidence_chain() -> None:
    source = text("src/ragguard/production_authorization.py")
    assert "manual_validation_chain_complete" in source
    design = text("docs/MANUAL_VALIDATION_EXECUTION_DESIGN_V0.16.md")
    assert "A plain\n`manual_validation_state=approved` claim does not satisfy" in design


def test_synthetic_execution_is_not_production_equivalent() -> None:
    assert ManualEvidenceKind.SYNTHETIC_EXECUTION.value != "production_equivalent"
    assert "not production-equivalent evidence" in text(
        "docs/MANUAL_VALIDATION_EXECUTION_DESIGN_V0.16.md"
    )


def test_no_real_product_or_unsafe_io_implementation() -> None:
    source = text("src/ragguard/manual_validation_execution.py")
    tree = ast.parse(source)
    functions = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert not functions & {
        "connect", "request_http", "activate", "write_registry", "persist_to_disk"
    }


def test_no_runtime_activation_or_real_persistence() -> None:
    design = text("docs/MANUAL_VALIDATION_EXECUTION_DESIGN_V0.16.md")
    assert "ready_for_activation_commit != active" in design
    assert "adds no activation API" in design
    assert "real persistence" in design


def test_cli_and_report_compatibility_are_fixed() -> None:
    changelog = text("CHANGELOG.md")
    assert "CLI exit codes `0 / 1 / 2 / 3`" in changelog
    assert "report top-level schema remain unchanged" in changelog


def test_release_operations_remain_post_merge() -> None:
    checklist = text("docs/RELEASE_CHECKLIST_V0.16.0.md")
    assert "annotated `v0.16.0` tag" in checklist
    assert "GitHub Release as a separate operation" in checklist
    assert "separate approved Vault PR" in checklist


def test_node_warning_is_separate() -> None:
    assert "Node runtime warning maintenance is a separate PR" in text(
        "docs/MANUAL_VALIDATION_EXECUTION_DESIGN_V0.16.md"
    )
