from __future__ import annotations

import ast
from pathlib import Path

import ragguard


ROOT = Path(__file__).parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_contract_separates_authorization_from_activation():
    text = read("docs/RELEASE_CHECKLIST_V0.18.0.md")
    assert "ready_for_runtime_authorization_commit != active" in text
    assert "authorization_committed != active" in text


def test_public_contract_exports_are_available():
    for name in (
        "RuntimeAuthorizationRequest", "RuntimeAuthorizationReview",
        "RuntimeAuthorizationApproval", "RuntimeAuthorizationDecision",
        "RuntimeAuthorizationCommitRecord", "TestRuntimeAuthorizationLedger",
        "evaluate_runtime_authorization",
    ):
        assert hasattr(ragguard, name)


def test_no_activation_api_or_runtime_switch_is_public():
    forbidden = {"activate", "enable_runtime", "start_transport", "switch_runtime"}
    assert forbidden.isdisjoint(set(ragguard.__all__))
    modules = read("src/ragguard/runtime_authorization.py") + read("src/ragguard/activation_commit.py")
    trees = [ast.parse(read("src/ragguard/runtime_authorization.py")),
             ast.parse(read("src/ragguard/activation_commit.py"))]
    public_functions = {node.name for tree in trees for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert forbidden.isdisjoint(public_functions)
    assert "subprocess" not in modules


def test_v018_modules_import_no_io_transport_or_random_surfaces():
    forbidden = {"socket", "requests", "httpx", "urllib", "sqlite3", "subprocess",
                 "secrets", "random", "uuid", "pathlib"}
    for path in ("src/ragguard/runtime_authorization.py", "src/ragguard/activation_commit.py"):
        tree = ast.parse(read(path))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module}
        assert forbidden.isdisjoint(imported)


def test_docs_do_not_claim_runtime_activation_or_real_persistence():
    text = read("docs/RUNTIME_AUTHORIZATION_ACTIVATION_DESIGN_V0.18.md")
    assert "does not activate" in text
    assert "No runtime switch" in text
    assert "filesystem/DB/external" in text


def test_workflow_and_cli_contracts_are_unchanged():
    checklist = read("docs/RELEASE_CHECKLIST_V0.18.0.md")
    assert "CLI exit codes and report top-level schema remain unchanged" in checklist
    workflows = tuple((ROOT / ".github" / "workflows").glob("*.yml"))
    assert len(workflows) == 1
    assert "3.11" in workflows[0].read_text(encoding="utf-8")
    assert "3.12" in workflows[0].read_text(encoding="utf-8")
