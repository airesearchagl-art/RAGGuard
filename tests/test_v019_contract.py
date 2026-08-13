from __future__ import annotations

import ast
from pathlib import Path

import ragguard


ROOT = Path(__file__).parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_contract_keeps_persistence_and_activation_separate():
    text = read("docs/RELEASE_CHECKLIST_V0.19.0.md")
    for boundary in ("persistence authorized != durable write completed",
                     "durable write completed != runtime active",
                     "recovery completed != runtime active",
                     "persisted record != production registry active"):
        assert boundary in text


def test_public_contract_exports_are_available():
    for name in ("PersistenceAuthorizationRequest", "PersistenceIntent",
                 "PersistenceTransactionPlan", "DurablePersistenceDecision",
                 "PersistenceCommitReceiptV2", "TestAtomicDurableStore",
                 "PersistenceRecoveryRequest", "evaluate_durable_persistence",
                 "evaluate_persistence_recovery"):
        assert hasattr(ragguard, name)


def test_v019_modules_import_no_real_io_or_random_surfaces():
    forbidden = {"socket", "requests", "httpx", "urllib", "sqlite3", "subprocess",
                 "secrets", "random", "uuid", "pathlib", "tempfile"}
    for path in ("src/ragguard/real_persistence.py",
                 "src/ragguard/persistence_recovery.py"):
        tree = ast.parse(read(path))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module}
        assert forbidden.isdisjoint(imported)


def test_no_storage_or_activation_public_api():
    forbidden = {"open", "connect", "persist_to_disk", "activate", "switch_runtime",
                 "write_registry", "generate_token"}
    assert forbidden.isdisjoint(set(ragguard.__all__))


def test_cli_and_report_contracts_are_unchanged():
    checklist = read("docs/RELEASE_CHECKLIST_V0.19.0.md")
    assert "CLI exit codes unchanged" in checklist
    assert "report top-level schema unchanged" in checklist


def test_docs_state_real_persistence_requires_separate_approval():
    design = read("docs/REAL_PERSISTENCE_BOUNDARY_DESIGN_V0.19.md")
    assert "does not implement real persistence" in design
    assert "separate design and approval" in design
