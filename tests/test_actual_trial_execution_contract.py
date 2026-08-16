from dataclasses import fields, replace

import pytest

from actual_trial_v030_support import actual_execution_chain, execute_actual_chain
from ragguard.actual_trial_execution import (
    ActualOneShotTrialExecutor,
    ActualTrialExecutionError,
    ActualTrialExecutionState,
    ActualTrialFailureReason,
    HumanExecutionApproval,
    HumanExecutionApprovalResult,
)
from ragguard.actual_trial_root import (
    ActualTrialRootUse,
    provision_human_selected_actual_root,
)
from ragguard.real_data_access_authorization import (
    RealDataAccessAuthorizationLifecycle,
)
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_session_contract import NOW


def test_production_executor_completes_controlled_actual_path_once(tmp_path):
    call = actual_execution_chain(tmp_path)
    result = execute_actual_chain(call)
    assert result.succeeded
    assert result.state is ActualTrialExecutionState.COMPLETED
    assert result.reasons == ()
    assert result.side_effects.approved_file_open_count == 1
    assert result.side_effects.approved_file_read_count == 1
    assert result.side_effects.actual_local_rag_material_access_count == 0
    assert result.side_effects.prohibited_all_zero
    assert result.classification is not None
    assert result.classification.approved_internal_low
    assert result.masking is not None and result.masking.verified
    assert result.chunking is not None and result.chunking.chunk_count >= 1
    assert result.receipt is not None
    assert result.closure is not None and result.closure.state == "completed"
    assert result.post_read_evidence is not None
    assert result.usage_after is not None
    assert result.usage_after.remaining_read_count == 0
    assert result.authorization_after is not None
    assert result.authorization_after.lifecycle is (
        RealDataAccessAuthorizationLifecycle.EXHAUSTED
    )


def test_gate_revalidates_the_complete_v029_object_chain(tmp_path):
    call = actual_execution_chain(tmp_path)
    assert call["gate"].ready_for_explicit_execution
    assert call["gate"].packet_digest == call["packet"].canonical_digest
    assert call["gate"].object_chain_digest == call["chain"].canonical_digest
    assert call["gate"].reason_codes == ()
    assert canonical_object_valid(call["gate"])


def test_human_approval_is_packet_and_operator_exact_bound(tmp_path):
    call = actual_execution_chain(tmp_path)
    approval = call["human_approval"]
    assert approval.packet_digest == call["packet"].canonical_digest
    assert approval.operator_id == call["operator_id"]
    assert approval.approval_result is HumanExecutionApprovalResult.APPROVED
    assert canonical_object_valid(approval)
    assert repr(approval) == "HumanExecutionApproval(<safe>)"


def test_actual_root_capability_is_opaque_and_controlled_fixture_bound(tmp_path):
    call = actual_execution_chain(tmp_path)
    capability = call["provision"].capability
    assert capability.root_use is ActualTrialRootUse.CONTROLLED_FIXTURE
    assert canonical_object_valid(capability)
    assert repr(capability) == "ActualTrialRootCapability(<safe>)"
    assert "selected-note" not in capability.canonical_json()
    assert not hasattr(capability, "path")
    assert not hasattr(capability, "root_path")


def test_public_actual_root_provisioner_fixes_actual_use_without_caller_override(
    tmp_path,
):
    root = tmp_path / "explicit-root"
    root.mkdir()
    (root / "selected.txt").write_text("Synthetic selected note.", encoding="utf-8")
    provision = provision_human_selected_actual_root(
        root_path=root,
        relative_target="selected.txt",
        root_id="public-actual-root-030",
        target_reference_id="public-actual-reference-030",
        target_id="public-actual-target-030",
        selected_at=NOW,
        allowed_file_types=(".txt",),
    )
    try:
        assert provision.capability.root_use is (
            ActualTrialRootUse.HUMAN_SELECTED_ACTUAL
        )
        assert canonical_object_valid(provision.capability)
    finally:
        provision.capability.close()


def test_pre_read_target_identity_is_not_raw_content_digest(tmp_path):
    call = actual_execution_chain(tmp_path)
    pre_read_identity = call["provision"].target.target_identity_digest
    result = execute_actual_chain(call)
    assert result.receipt is not None
    assert pre_read_identity != result.receipt.raw_content_digest
    assert result.receipt.raw_content_digest == (
        result.classification.raw_content_digest
    )


def test_receipt_exact_binds_execution_evidence_and_operator(tmp_path):
    call = actual_execution_chain(tmp_path)
    result = execute_actual_chain(call)
    receipt = result.receipt
    assert receipt is not None
    assert receipt.packet_digest == call["packet"].canonical_digest
    assert receipt.human_approval_digest == call["human_approval"].canonical_digest
    assert receipt.operator_id == call["operator_id"]
    assert receipt.classification_digest == result.classification.canonical_digest
    assert receipt.masking_digest == result.masking.canonical_digest
    assert receipt.chunking_digest == result.chunking.canonical_digest
    assert receipt.usage_after_digest == result.usage_after.canonical_digest
    assert canonical_object_valid(receipt)


def test_ledger_commits_receipt_usage_authorization_and_closure_atomically(tmp_path):
    call = actual_execution_chain(tmp_path)
    before = call["ledger"].replay_snapshot()
    result = execute_actual_chain(call)
    ledger = call["ledger"]
    assert before == (frozenset(), frozenset(), frozenset(), frozenset())
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (1, 1, 1)
    assert ledger.receipts == (result.receipt,)
    assert ledger.closures == (result.closure,)
    assert ledger.post_read_evidence == (result.post_read_evidence,)


def test_ledger_mutation_requires_executor_authority():
    from ragguard.actual_trial_execution import ActualTrialExecutionLedger

    ledger = ActualTrialExecutionLedger()
    with pytest.raises(ActualTrialExecutionError, match="actual_ledger_authority_invalid"):
        ledger._record_failed_attempt(digest("approval"), marker=object())


def test_missing_human_approval_rejects_before_open_and_keeps_ledger(tmp_path):
    call = actual_execution_chain(tmp_path)
    before = call["ledger"].replay_snapshot()
    result = execute_actual_chain(call, human_approval=None)
    assert result.state is ActualTrialExecutionState.REJECTED_PRE_READ
    assert result.reasons == (ActualTrialFailureReason.HUMAN_APPROVAL_REQUIRED,)
    assert result.side_effects.approved_file_open_count == 0
    assert result.side_effects.approved_file_read_count == 0
    assert call["ledger"].replay_snapshot() == before


def test_rejected_human_approval_rejects_before_open(tmp_path):
    call = actual_execution_chain(tmp_path)
    rejected = replace(
        call["human_approval"],
        approval_result=HumanExecutionApprovalResult.REJECTED,
    )
    result = execute_actual_chain(call, human_approval=rejected)
    assert result.reasons == (ActualTrialFailureReason.HUMAN_APPROVAL_REJECTED,)
    assert result.side_effects.approved_file_open_count == 0


def test_operator_mismatch_rejects_before_open(tmp_path):
    call = actual_execution_chain(tmp_path)
    result = execute_actual_chain(call, operator_id="different-operator-030")
    assert result.reasons == (ActualTrialFailureReason.OPERATOR_MISMATCH,)
    assert result.side_effects.approved_file_open_count == 0


def test_packet_gate_mismatch_rejects_before_open(tmp_path):
    call = actual_execution_chain(tmp_path)
    changed = replace(call["packet"], packet_id="different-packet-030")
    result = execute_actual_chain(call, packet=changed)
    assert result.reasons == (ActualTrialFailureReason.INVALID_PACKET_CHAIN,)
    assert result.side_effects.approved_file_open_count == 0


def test_target_mismatch_rejects_before_open(tmp_path):
    call = actual_execution_chain(tmp_path)
    changed = replace(
        call["provision"].target,
        target_identity_digest=digest("different-target-identity-030"),
    )
    result = execute_actual_chain(call, target=changed)
    assert result.reasons == (ActualTrialFailureReason.TARGET_MISMATCH,)
    assert result.side_effects.approved_file_open_count == 0


def test_duplicate_success_is_rejected_without_second_open_or_read(tmp_path):
    call = actual_execution_chain(tmp_path)
    first = execute_actual_chain(call)
    second = execute_actual_chain(call)
    assert first.succeeded
    assert not second.succeeded
    assert second.reasons == (ActualTrialFailureReason.REPLAY,)
    assert second.side_effects.approved_file_open_count == 0
    assert second.side_effects.approved_file_read_count == 0
    assert (call["ledger"].write_count, call["ledger"].mutation_count) == (1, 1)


def test_public_metadata_results_have_no_raw_locator_or_payload_fields():
    forbidden = {
        "path",
        "filename",
        "directory",
        "root_path",
        "document_path",
        "payload",
        "contents",
        "raw_content",
    }
    contracts = (HumanExecutionApproval,)
    assert all(
        {item.name for item in fields(contract)}.isdisjoint(forbidden)
        for contract in contracts
    )


def test_executor_has_no_directory_scanner_or_automatic_selector_surface():
    names = set(dir(ActualOneShotTrialExecutor))
    assert names.isdisjoint({"scan", "walk", "glob", "discover", "select_target"})
