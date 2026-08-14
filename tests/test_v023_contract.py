from pathlib import Path

import ragguard
from ragguard.local_rag_environment import __all__ as environment_exports
from ragguard.local_rag_execution import __all__ as execution_exports


ROOT = Path(__file__).resolve().parents[1]


def test_v023_public_contract_is_exported_without_replacing_legacy_environment_class():
    required = {
        "LocalRAGEnvironmentManifest", "EnvironmentAttestationSuite",
        "EnvironmentAttestationDecision", "LocalRAGExecutionSessionRequest",
        "LocalRAGExecutionSessionReview", "LocalRAGExecutionSessionApproval",
        "ApprovedLocalRAGExecutionSession", "SessionExecutionReceipt",
        "ControlledLocalRAGExecutionAdapter", "evaluate_real_data_trial_readiness",
    }
    assert required.issubset(set(ragguard.__all__))
    assert all(hasattr(ragguard, name) for name in required)
    assert hasattr(ragguard, "LocalRAGEnvironmentClass")
    assert "EnvironmentClass" in ragguard.__all__
    assert required.intersection(set(environment_exports) | set(execution_exports)) == required


def test_v023_design_and_release_checklist_fix_the_authorization_boundaries():
    design = (ROOT / "docs" / "LOCAL_RAG_EXECUTION_SESSION_ATTESTATION_DESIGN_V0.23.md").read_text(
        encoding="utf-8")
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST_V0.23.0.md").read_text(encoding="utf-8")
    required = (
        "environment attested != production environment approved",
        "approved session != real-data use approved",
        "controlled execution passed != real-data approved",
        "real-data trial approval review eligible != real-data use authorized",
        "session approved != real-data approved",
        "execution approval != real-data use authorized",
        "eligible_for_explicit_real_data_trial_approval_review != real-data use authorized",
    )
    assert all(value in design for value in required)
    assert all(value in checklist for value in required)


def test_v023_documentation_updates_are_present():
    for name in ("README.md", "ROADMAP.md", "CHANGELOG.md", "docs/USAGE.md",
                 "docs/DESIGN_NOTES.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "v0.23" in text
    assert (ROOT / "docs" / "LOCAL_RAG_EXECUTION_SESSION_ATTESTATION_DESIGN_V0.23.md").is_file()
    assert (ROOT / "docs" / "RELEASE_CHECKLIST_V0.23.0.md").is_file()


def test_execution_modules_do_not_import_transport_or_persistence_clients():
    source = "\n".join((ROOT / "src" / "ragguard" / name).read_text(encoding="utf-8")
        for name in ("local_rag_environment.py", "local_rag_execution.py"))
    forbidden_imports = (
        "import requests", "import httpx", "import socket", "import sqlite3",
        "import subprocess", "urllib.request", "boto", "openai", "chromadb",
    )
    assert not any(value in source for value in forbidden_imports)


def test_v023_has_no_runtime_or_production_activation_function_surface():
    names = set(environment_exports) | set(execution_exports)
    forbidden = {"activate", "enable", "connect", "deploy", "persist", "write_production",
                 "switch_runtime", "authorize_real_data_use"}
    assert names.isdisjoint(forbidden)


def test_release_contract_keeps_cli_and_report_schema_out_of_scope():
    design = (ROOT / "docs" / "LOCAL_RAG_EXECUTION_SESSION_ATTESTATION_DESIGN_V0.23.md").read_text(
        encoding="utf-8")
    assert "No CLI command, CLI exit code, report schema" in design
    assert "No new CLI command is added" in (ROOT / "docs" / "USAGE.md").read_text(
        encoding="utf-8")
