from dataclasses import fields
from pathlib import Path
from typing import get_type_hints

import pytest

import ragguard
from ragguard.real_data_access_authorization import __all__ as authorization_exports
from ragguard.real_data_read_execution import (
    ExplicitRealDataTrialExecutionHook,
    ExplicitRealDataTrialExecutionState,
    __all__ as execution_exports,
)
from ragguard.real_data_read_receipt import __all__ as receipt_exports
from test_real_data_read_execution_contract import read_execution_chain


ROOT = Path(__file__).resolve().parents[1]


def test_v026_public_contract_exports_only_controlled_boundary_types():
    required = {
        "RealDataReadExecutionRequest",
        "ReadTargetDescriptor",
        "PreReadVerificationResult",
        "ControlledReadAdapter",
        "ReadExecutionResult",
        "PostReadClassificationResult",
        "PostReadMaskingVerification",
        "RealDataReadReceipt",
        "VerifiedMaskedContentCandidate",
        "TestOnlyRealDataReadExecutionLedger",
        "ExplicitRealDataTrialExecutionHook",
    }
    names = set(execution_exports) | set(receipt_exports)
    assert required.issubset(names)
    assert required.issubset(set(ragguard.__all__))
    assert all(hasattr(ragguard, name) for name in required)
    forbidden = {
        "RealFileReader",
        "ProductionReadAdapter",
        "open_real_file",
        "read_real_document",
        "scan_real_data_directory",
        "consume_authorization_usage",
        "reset_authorization_usage",
        "refill_authorization_usage",
    }
    assert names.isdisjoint(forbidden)
    assert "_consume_authorization_usage_for_verified_read" not in (
        authorization_exports
    )


def test_v026_metadata_contracts_have_no_path_or_raw_content_fields():
    contracts = (
        ragguard.RealDataReadExecutionRequest,
        ragguard.ReadTargetDescriptor,
        ragguard.PreReadVerificationResult,
        ragguard.ReadExecutionResult,
        ragguard.PostReadClassificationResult,
        ragguard.PostReadMaskingVerification,
        ragguard.RealDataReadReceipt,
        ragguard.VerifiedMaskedContentCandidate,
    )
    forbidden = {
        "path",
        "filename",
        "directory",
        "raw_content",
        "payload",
        "customer_name",
        "company_name",
        "person_name",
        "project_name",
        "credential",
        "token",
    }
    assert all(
        {item.name for item in fields(contract)}.isdisjoint(forbidden)
        for contract in contracts
    )


def test_controlled_adapter_is_fixture_backed_immutable_and_has_no_path_surface():
    _, _, call, _ = read_execution_chain(execute=False)
    adapter = call["adapter"]
    assert not hasattr(adapter, "path")
    assert not hasattr(adapter, "open")
    assert not hasattr(adapter, "read")
    with pytest.raises(AttributeError, match="controlled_read_adapter_immutable"):
        adapter.adapter_id = "mutated-adapter"


def test_v026_modules_have_no_real_io_transport_persistence_or_hidden_clock_surface():
    source = "\n".join(
        (ROOT / "src" / "ragguard" / name).read_text(encoding="utf-8")
        for name in (
            "real_data_read_execution.py",
            "real_data_read_receipt.py",
        )
    )
    forbidden = (
        "open(",
        "Path(",
        "read_text(",
        "read_bytes(",
        "glob(",
        "rglob(",
        "walk(",
        "import requests",
        "import httpx",
        "import socket",
        "import sqlite3",
        "import subprocess",
        "urllib.request",
        "boto",
        "openai",
        "chromadb",
        "datetime.now",
        "utcnow",
        "uuid",
        "AI_Local_RAG",
        "AI_Restricted",
    )
    assert not any(value in source for value in forbidden)


def test_release_contract_keeps_non_equivalent_read_states_fail_closed():
    _, result, _, _ = read_execution_chain()
    assert result.applied
    assert result.exhausted_authorization.actual_real_data_read_executed is False
    assert result.receipt.embedding_authorized is False
    assert result.receipt.persistence_authorized is False
    assert result.receipt.local_rag_full_processing_authorized is False
    assert result.masked_candidate.embedding_authorized is False
    assert result.masked_candidate.persistence_authorized is False
    assert result.masked_candidate.llm_input_authorized is False


def test_explicit_trial_hook_is_interface_only_and_eligible_is_not_executed():
    assert getattr(ExplicitRealDataTrialExecutionHook, "_is_protocol", False)
    hints = get_type_hints(ExplicitRealDataTrialExecutionHook.evaluate)
    assert hints["return"] is ExplicitRealDataTrialExecutionState
    assert (
        ExplicitRealDataTrialExecutionState.ELIGIBLE_FOR_EXPLICIT_ONE_SHOT_TRIAL_EXECUTION
        != ExplicitRealDataTrialExecutionState.NEEDS_EXPLICIT_REAL_DATA_EXECUTION_APPROVAL
    )
    assert not any(
        name.startswith("execute")
        for name in ExplicitRealDataTrialExecutionHook.__dict__
    )


def test_v026_release_contract_phrases_are_fixed_in_design_and_checklist():
    design = (
        ROOT / "docs" / "LIMITED_REAL_DATA_READ_EXECUTION_DESIGN_V0.26.md"
    ).read_text(encoding="utf-8")
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST_V0.26.0.md").read_text(
        encoding="utf-8"
    )
    required = (
        "access authorized != actual read executed",
        "read started != read verified",
        "read succeeded != masking verified",
        "verified read != embedding authorized",
        "verified read != persistence authorized",
        "eligible_for_explicit_one_shot_trial_execution != executed",
    )
    assert all(value in design and value in checklist for value in required)


def test_v026_documentation_and_prior_governance_are_present():
    for name in (
        "README.md",
        "ROADMAP.md",
        "CHANGELOG.md",
        "docs/USAGE.md",
        "docs/DESIGN_NOTES.md",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "v0.26" in text and "v0.25" in text
    assert (ROOT / "docs" / "LIMITED_REAL_DATA_READ_EXECUTION_DESIGN_V0.26.md").is_file()
    assert (ROOT / "docs" / "RELEASE_CHECKLIST_V0.26.0.md").is_file()


def test_cli_exit_codes_report_schema_and_package_version_remain_unchanged():
    assert ragguard.__version__ == "0.1.0"
    assert hasattr(ragguard, "evaluate_real_data_read_execution_readiness")
    assert hasattr(ragguard, "ApprovedRealDataTrialRecord")
    assert hasattr(ragguard, "ApprovedLocalRAGExecutionSession")
    functions = {
        name
        for name in set(execution_exports) | set(receipt_exports)
        if name[:1].islower()
    }
    forbidden_fragments = (
        "open_real",
        "read_real",
        "scan_real",
        "persist",
        "write_production",
        "activate_runtime",
        "switch_runtime",
    )
    assert not any(
        any(fragment in name for fragment in forbidden_fragments)
        for name in functions
    )
