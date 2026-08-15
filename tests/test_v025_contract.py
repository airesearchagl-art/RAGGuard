from dataclasses import fields
from pathlib import Path

import ragguard
from ragguard.real_data_access import __all__ as access_exports
from ragguard.real_data_access_authorization import __all__ as authorization_exports


ROOT = Path(__file__).resolve().parents[1]


def test_v025_public_contract_exports_only_metadata_authorization_boundaries():
    required = {
        "RealDataAccessSelector", "RealDataAccessPolicy", "RealDataAccessRequest",
        "RealDataAccessSecurityReview", "RealDataAccessGovernanceReview",
        "RealDataOperatorAssignment", "RealDataAccessApproval",
        "RealDataAccessAuthorizationRecord",
        "TestOnlyRealDataAccessAuthorizationRegistry",
        "AuthorizationUsageCounterContract",
        "evaluate_real_data_read_execution_readiness",
    }
    names = set(access_exports) | set(authorization_exports)
    assert required.issubset(names) and required.issubset(set(ragguard.__all__))
    assert all(hasattr(ragguard, name) for name in required)
    forbidden = {
        "open_real_file", "read_real_document", "execute_real_data_read",
        "consume_real_data", "scan_real_data_directory", "load_customer_data",
        "write_persistent_vector", "write_production_registry", "activate_runtime",
    }
    assert names.isdisjoint(forbidden)


def test_v025_release_contract_fixes_non_equivalent_authorization_states():
    design = (ROOT / "docs" /
              "REAL_DATA_ACCESS_AUTHORIZATION_BOUNDARY_DESIGN_V0.25.md").read_text(
                  encoding="utf-8")
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST_V0.25.0.md").read_text(
        encoding="utf-8")
    required = (
        "trial approved != real-data access authorized",
        "access authorized != actual real-data read",
        "operator assigned != access authorized",
        "eligible_for_limited_real_data_read_execution != read executed",
        "read authorization != persistence authorization",
        "read authorization != runtime activation",
    )
    assert all(value in design and value in checklist for value in required)


def test_v025_documentation_updates_and_authoritative_design_are_present():
    for name in ("README.md", "ROADMAP.md", "CHANGELOG.md", "docs/USAGE.md",
                 "docs/DESIGN_NOTES.md"):
        assert "v0.25" in (ROOT / name).read_text(encoding="utf-8")
    assert (ROOT / "docs" /
            "REAL_DATA_ACCESS_AUTHORIZATION_BOUNDARY_DESIGN_V0.25.md").is_file()
    assert (ROOT / "docs" / "RELEASE_CHECKLIST_V0.25.0.md").is_file()


def test_v025_modules_have_no_io_transport_persistence_or_hidden_clock_surface():
    source = "\n".join((ROOT / "src" / "ragguard" / name).read_text(encoding="utf-8")
        for name in ("real_data_access.py", "real_data_access_authorization.py"))
    forbidden = (
        "open(", "read_text(", "read_bytes(", "import requests", "import httpx",
        "import socket", "import sqlite3", "import subprocess", "urllib.request",
        "boto", "openai", "chromadb", "datetime.now", "utcnow", "uuid",
        "AI_Local_RAG", "AI_Restricted",
    )
    assert not any(value in source for value in forbidden)


def test_v025_contracts_have_no_actual_path_filename_identity_or_raw_content_fields():
    contracts = (
        ragguard.RealDataAccessSelector, ragguard.RealDataAccessPolicy,
        ragguard.RealDataAccessRequest, ragguard.RealDataAccessSecurityReview,
        ragguard.RealDataAccessGovernanceReview, ragguard.RealDataOperatorAssignment,
        ragguard.RealDataAccessApproval, ragguard.RealDataAccessAuthorizationRecord,
    )
    forbidden = {
        "path", "filename", "directory", "hostname", "customer_name",
        "company_name", "person_name", "project_name", "raw_identifier",
        "raw_content", "credential", "token",
    }
    assert all({item.name for item in fields(contract)}.isdisjoint(forbidden)
               for contract in contracts)


def test_v025_keeps_cli_report_and_prior_governance_contract_unchanged():
    assert ragguard.__version__ == "0.1.0"
    assert hasattr(ragguard, "ApprovedRealDataTrialRecord")
    assert hasattr(ragguard, "ApprovedLocalRAGExecutionSession")
    assert hasattr(ragguard, "evaluate_real_data_access_authorization_readiness")
    names = set(access_exports) | set(authorization_exports)
    functions = {name for name in names if name[:1].islower()}
    forbidden_fragments = (
        "open_real", "read_real", "execute_real", "consume_real",
        "scan_real", "load_customer", "persist", "write_production",
        "activate_runtime", "switch_runtime",
    )
    assert not any(any(fragment in name for fragment in forbidden_fragments)
                   for name in functions)
