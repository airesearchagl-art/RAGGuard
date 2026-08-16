import ast
from dataclasses import fields
from pathlib import Path

import ragguard
import ragguard.one_shot_trial_preparation as preparation_module
from ragguard.one_shot_trial_preparation import (
    ExecutionPreparationDecision,
    ExecutionPreparationReason,
    ExecutionPreparationRequest,
    ExecutionPreparationSafeSummary,
    ExecutionPreparationSideEffectAccounting,
    ExecutionPreparationState,
    OneShotTrialExecutionPacket,
    OneShotTrialPreparationError,
    TestOnlyExecutionPreparationRegistry,
    prepare_one_shot_trial,
)
from ragguard.storage_adapter import canonical_object_valid
from test_one_shot_trial_preparation import preparation_chain


PUBLIC_NAMES = (
    "ExecutionPreparationDecision",
    "ExecutionPreparationReason",
    "ExecutionPreparationRequest",
    "ExecutionPreparationSafeSummary",
    "ExecutionPreparationSideEffectAccounting",
    "ExecutionPreparationState",
    "OneShotTrialExecutionPacket",
    "OneShotTrialPreparationError",
    "TestOnlyExecutionPreparationRegistry",
    "prepare_one_shot_trial",
)


def test_v029_public_exports_are_available():
    for name in PUBLIC_NAMES:
        assert getattr(ragguard, name) is getattr(preparation_module, name)
        assert name in preparation_module.__all__


def test_packet_request_decision_and_summary_are_canonical_metadata():
    _, decision, call = preparation_chain()
    assert canonical_object_valid(call["packet"])
    assert canonical_object_valid(call["request"])
    assert canonical_object_valid(decision)
    assert canonical_object_valid(decision.safe_summary)
    assert canonical_object_valid(decision.side_effects)


def test_execution_preparation_states_are_fixed():
    assert {item.value for item in ExecutionPreparationState} == {
        "ineligible",
        "needs_root_provisioning",
        "needs_target_binding",
        "needs_operator_binding",
        "needs_trial_approval",
        "needs_access_authorization",
        "needs_closure_requirements",
        "ready_for_explicit_execution_approval",
    }


def test_public_contract_fields_are_metadata_only():
    contracts = (
        OneShotTrialExecutionPacket,
        ExecutionPreparationRequest,
        ExecutionPreparationSafeSummary,
        ExecutionPreparationDecision,
    )
    forbidden = {
        "path",
        "filename",
        "directory",
        "root_path",
        "document_path",
        "payload",
        "contents",
        "credential",
        "token",
        "company",
        "customer",
        "person",
        "project",
    }
    assert all(
        {item.name for item in fields(contract)}.isdisjoint(forbidden)
        for contract in contracts
    )


def test_preparation_module_has_no_io_or_execution_dependency():
    source_path = Path("src/ragguard/one_shot_trial_preparation.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imported_roots.isdisjoint(
        {"os", "pathlib", "socket", "http", "urllib", "requests"}
    )
    forbidden_callables = {
        "execute",
        "read",
        "open",
        "run_trial",
        "auto_approve",
        "auto_execute",
    }
    public_callables = {
        name
        for name, value in vars(preparation_module).items()
        if callable(value) and not name.startswith("_")
    }
    assert public_callables.isdisjoint(forbidden_callables)


def test_repr_never_expands_packet_or_summary_fields():
    _, decision, call = preparation_chain()
    assert repr(call["packet"]) == "OneShotTrialExecutionPacket(<safe>)"
    assert repr(decision.safe_summary) == "ExecutionPreparationSafeSummary(<safe>)"


def test_release_boundary_statements_are_fixed():
    design = Path(
        "docs/ONE_SHOT_REAL_DATA_TRIAL_PREPARATION_V0.29.md"
    ).read_text(encoding="utf-8")
    checklist = Path("docs/RELEASE_CHECKLIST_V0.29.0.md").read_text(
        encoding="utf-8"
    )
    required = (
        "packet prepared != trial execution approved",
        "execution approval ready != execution authorized",
        "execution authorized != file read",
        "no actual real-data access",
        "no raw path in a public packet",
        "CLI exit codes and report schema remain unchanged",
    )
    assert all(item in design for item in required)
    assert "Pull request remains Draft and is not merged" in checklist
    assert "No tag or Release is created" in checklist


def test_ready_packet_still_grants_no_execution_or_file_read():
    _, decision, _ = preparation_chain()
    assert decision.state is (
        ExecutionPreparationState.READY_FOR_EXPLICIT_EXECUTION_APPROVAL
    )
    assert not decision.execution_authorized
    assert not decision.file_read_executed
    assert decision.side_effects.all_zero


def test_v029_keeps_cli_and_report_schema_unchanged():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    usage = Path("docs/USAGE.md").read_text(encoding="utf-8")
    assert "There is no new CLI" in usage
    assert "never opens or reads a file" in changelog
