from __future__ import annotations

import ast
from pathlib import Path

from ragguard.authorization_activation import ActivationEvaluationResult, ActivationRequest


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ready_for_commit_is_not_runtime_active() -> None:
    assert ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT.value not in {
        "active",
        "activated",
        "production_enabled",
        "authorized_runtime",
    }


def test_activation_request_has_no_self_declared_persistence_gate() -> None:
    assert "persistence_verified" not in ActivationRequest.__dataclass_fields__


def test_no_runtime_activation_api() -> None:
    source = _text("src/ragguard/authorization_activation.py")
    tree = ast.parse(source)
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert not function_names & {
        "activate",
        "activate_runtime",
        "enable_production",
        "authorize_runtime",
    }


def test_no_filesystem_database_network_or_subprocess_imports() -> None:
    forbidden = {
        "pathlib",
        "sqlite3",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "urllib",
        "tempfile",
    }
    for path in (
        "src/ragguard/production_persistence.py",
        "src/ragguard/authorization_activation.py",
    ):
        tree = ast.parse(_text(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not imported & forbidden


def test_no_random_uuid_token_or_credential_generation() -> None:
    combined = (
        _text("src/ragguard/production_persistence.py")
        + _text("src/ragguard/authorization_activation.py")
    ).lower()
    assert "import random" not in combined
    assert "import uuid" not in combined
    assert "secrets." not in combined
    assert "token_urlsafe" not in combined


def test_docs_fix_the_non_activation_boundary() -> None:
    design = _text("docs/PERSISTENCE_ACTIVATION_DESIGN_V0.15.md")
    assert "ready_for_activation_commit != active" in design
    assert "test-only in-memory" in design
    assert "No runtime activation" in design


def test_release_checklist_keeps_post_merge_operations_separate() -> None:
    checklist = _text("docs/RELEASE_CHECKLIST_V0.15.0.md")
    assert "annotated `v0.15.0` tag" in checklist
    assert "GitHub Release as a separate operation" in checklist
    assert "Vault" in checklist


def test_cli_exit_codes_and_report_schema_are_documented_unchanged() -> None:
    changelog = _text("CHANGELOG.md")
    assert "CLI exit codes `0 / 1 / 2 / 3` remain unchanged" in changelog
    assert "report top-level schema remains unchanged" in changelog


def test_node_warning_maintenance_is_out_of_scope() -> None:
    design = _text("docs/PERSISTENCE_ACTIVATION_DESIGN_V0.15.md")
    assert "Node runtime warning maintenance is a separate PR" in design
