from dataclasses import replace
from pathlib import Path

import pytest

import ragguard
from ragguard.local_rag_execution import LocalRAGExecutionError
from ragguard.real_data_trial import __all__ as trial_exports
from ragguard.real_data_trial_approval import __all__ as approval_exports
from test_local_rag_execution_security_e2e import readiness_for, reviewed_execution


ROOT = Path(__file__).resolve().parents[1]


def test_v024_public_contract_exports_only_metadata_and_review_boundaries():
    required = {
        "RealDataTrialScope", "RealDataClassificationPolicy", "TrialStagePolicy",
        "TrialRetentionPolicy", "TrialApprovalRequest", "TrialSecurityReview",
        "TrialDataGovernanceReview", "TrialApproval", "ApprovedRealDataTrialRecord",
        "TestOnlyRealDataTrialRegistry", "evaluate_real_data_access_authorization_readiness",
    }
    assert required.issubset(set(ragguard.__all__))
    assert all(hasattr(ragguard, name) for name in required)
    assert required.issubset(set(trial_exports) | set(approval_exports))
    forbidden = {"open_real_file", "read_real_document", "authorize_real_data_access",
                 "execute_real_data_trial", "load_customer_data", "connect_vector_db",
                 "write_registry", "activate_runtime"}
    assert (set(trial_exports) | set(approval_exports)).isdisjoint(forbidden)


def test_v024_design_and_release_contract_fix_authorization_boundaries():
    design = (ROOT / "docs" / "REAL_DATA_TRIAL_APPROVAL_BOUNDARY_DESIGN_V0.24.md").read_text(
        encoding="utf-8")
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST_V0.24.0.md").read_text(
        encoding="utf-8")
    required = (
        "trial review eligible != trial approved",
        "trial approved != real-data access authorized",
        "approved trial != actual real-data read",
        "real-data access review eligible != real-data use authorized",
    )
    assert all(value in design for value in required)
    assert all(value in checklist for value in required)
    assert "No CLI command, CLI exit code, report schema" in design


def test_v024_documentation_updates_are_present():
    for name in ("README.md", "ROADMAP.md", "CHANGELOG.md", "docs/USAGE.md",
                 "docs/DESIGN_NOTES.md"):
        assert "v0.24" in (ROOT / name).read_text(encoding="utf-8")
    assert (ROOT / "docs" / "REAL_DATA_TRIAL_APPROVAL_BOUNDARY_DESIGN_V0.24.md").is_file()
    assert (ROOT / "docs" / "RELEASE_CHECKLIST_V0.24.0.md").is_file()


def test_v024_modules_have_no_io_transport_persistence_or_hidden_clock_surface():
    source = "\n".join((ROOT / "src" / "ragguard" / name).read_text(encoding="utf-8")
        for name in ("real_data_trial.py", "real_data_trial_approval.py"))
    forbidden = (
        "open(", "read_text(", "read_bytes(", "import requests", "import httpx",
        "import socket", "import sqlite3", "import subprocess", "urllib.request",
        "boto", "openai", "chromadb", "datetime.now", "utcnow", "uuid",
        "AI_Local_RAG", "AI_Restricted",
    )
    assert not any(value in source for value in forbidden)


def test_v023_eligible_readiness_cannot_be_reissued_by_public_replace():
    values = reviewed_execution()
    decision = readiness_for(*values)
    with pytest.raises(LocalRAGExecutionError, match="readiness_decision_invalid"):
        replace(decision)


def test_release_boundary_has_no_real_read_write_or_activation_api():
    names = set(trial_exports) | set(approval_exports)
    fragments = ("open_real", "read_real", "execute_real", "connect", "persist",
                 "write_production", "activate", "switch_runtime", "authorize_real")
    functions = {name for name in names if name[:1].islower()}
    assert not any(any(fragment in name.lower() for fragment in fragments)
                   for name in functions)
