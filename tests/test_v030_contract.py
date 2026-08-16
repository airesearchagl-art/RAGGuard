import ast
from dataclasses import fields
from pathlib import Path

import ragguard
import ragguard.actual_trial_execution as execution_module
import ragguard.actual_trial_root as root_module
from actual_trial_v030_support import actual_execution_chain, execute_actual_chain
from ragguard.actual_trial_execution import (
    ActualOneShotTrialExecutor,
    ActualOneShotTrialReceipt,
    ActualPostReadEvidence,
    ActualTrialClosureRecord,
    ActualTrialExecutionLedger,
    ActualTrialExecutionResult,
    ActualTrialGateDecision,
    HumanExecutionApproval,
)
from ragguard.actual_trial_root import (
    ActualRootProvisioning,
    ActualTrialRootCapability,
    HumanSelectedOpaqueTarget,
    provision_human_selected_actual_root,
)
from ragguard.storage_adapter import canonical_object_valid


PUBLIC_NAMES = (
    "ActualRootProvisioning",
    "ActualTrialRootCapability",
    "HumanSelectedOpaqueTarget",
    "provision_human_selected_actual_root",
    "HumanExecutionApproval",
    "ActualTrialGateDecision",
    "ActualOneShotTrialExecutor",
    "ActualTrialExecutionLedger",
    "ActualTrialExecutionResult",
    "ActualOneShotTrialReceipt",
    "ActualPostReadEvidence",
    "ActualTrialClosureRecord",
)


def test_v030_public_execution_boundary_exports_are_available():
    for name in PUBLIC_NAMES:
        assert hasattr(ragguard, name)
    assert ragguard.ActualOneShotTrialExecutor is ActualOneShotTrialExecutor
    assert ragguard.provision_human_selected_actual_root is (
        provision_human_selected_actual_root
    )


def test_internal_controlled_fixture_provisioner_is_not_public():
    assert not hasattr(ragguard, "_provision_controlled_fixture_actual_root")
    assert "_provision_controlled_fixture_actual_root" not in root_module.__all__
    assert "_install_actual_execution_test_hook" not in execution_module.__all__


def test_public_result_contracts_are_metadata_only():
    forbidden = {
        "path",
        "filename",
        "directory",
        "root_path",
        "document_path",
        "payload",
        "contents",
        "raw_content",
        "transformed_content",
    }
    contracts = (
        HumanExecutionApproval,
        ActualTrialGateDecision,
        ActualTrialExecutionResult,
        ActualOneShotTrialReceipt,
        ActualPostReadEvidence,
        ActualTrialClosureRecord,
        HumanSelectedOpaqueTarget,
    )
    assert all(
        {item.name for item in fields(contract)}.isdisjoint(forbidden)
        for contract in contracts
    )


def test_root_module_has_no_discovery_or_scan_call(tmp_path):
    tree = ast.parse(Path(root_module.__file__).read_text(encoding="utf-8"))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } | {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert called.isdisjoint({"walk", "glob", "rglob", "listdir", "scandir"})


def test_execution_module_has_no_network_cloud_or_persistence_dependency():
    tree = ast.parse(Path(execution_module.__file__).read_text(encoding="utf-8"))
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
        {"socket", "http", "urllib", "requests", "sqlite3", "subprocess"}
    )


def test_success_objects_are_all_canonical_and_raw_free(tmp_path):
    call = actual_execution_chain(tmp_path)
    result = execute_actual_chain(call)
    objects = (
        result,
        result.classification,
        result.masking,
        result.chunking,
        result.receipt,
        result.post_read_evidence,
        result.closure,
        result.authorization_after,
        result.usage_after,
    )
    assert all(canonical_object_valid(item) for item in objects)
    marker = "Synthetic internal low calibration note"
    assert all(marker not in item.canonical_json() for item in objects)


def test_success_stops_at_chunking_and_grants_no_downstream_authority(tmp_path):
    call = actual_execution_chain(tmp_path)
    result = execute_actual_chain(call)
    effects = result.side_effects
    assert result.succeeded
    assert effects.embedding_count == 0
    assert effects.persistent_vector_db_write_count == 0
    assert effects.persistence_count == 0
    assert effects.export_count == 0
    assert effects.runtime_activation_switch_count == 0


def test_release_gate_statements_are_fixed():
    design = Path("docs/ACTUAL_ONE_SHOT_EXECUTION_DESIGN_V0.30.md").read_text(
        encoding="utf-8"
    )
    checklist = Path("docs/RELEASE_CHECKLIST_V0.30.0.md").read_text(
        encoding="utf-8"
    )
    required = (
        "packet prepared != execution approved",
        "Human execution approved != file read executed",
        "one-shot receipt != embedding authorization",
        "one-shot receipt != persistence authorization",
        "closure completed != downstream processing approval",
        "implementation merged != actual trial passed",
        "actual trial passed != unrestricted real-data processing",
    )
    assert all(item in design for item in required)
    assert "No actual material trial, tag, or Release" in checklist
    assert "If the actual trial fails, no tag or Release is created" in checklist


def test_v030_keeps_cli_and_report_schema_unchanged():
    usage = Path("docs/USAGE.md").read_text(encoding="utf-8")
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert "No CLI command or unrestricted path reader" in usage.replace("\n", " ")
    assert "v0.30.0 - Unreleased, trial-gated" in changelog


def test_pr_boundary_explicitly_retains_actual_material_zero():
    design = Path("docs/ACTUAL_ONE_SHOT_EXECUTION_DESIGN_V0.30.md").read_text(
        encoding="utf-8"
    )
    assert "controlled synthetic temporary files" in design
    assert "does not read actual Local RAG material or restricted material" in design
