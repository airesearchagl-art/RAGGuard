import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest

import ragguard.actual_trial_execution as execution_module
from actual_trial_v030_support import actual_execution_chain, execute_actual_chain
from ragguard.actual_trial_execution import (
    ActualTrialExecutionError,
    ActualTrialExecutionState,
    ActualTrialFailureReason,
    HumanExecutionApprovalResult,
    _install_actual_execution_test_hook,
)
from ragguard.actual_trial_root import (
    ActualTrialRootError,
    ActualTrialRootUse,
    _provision_controlled_fixture_actual_root,
)
from ragguard.storage_adapter import digest
from test_local_rag_execution_session_contract import NOW


def assert_no_prohibited_side_effects(result):
    effects = result.side_effects
    assert effects.prohibited_all_zero
    assert effects.actual_local_rag_material_access_count == 0
    assert effects.restricted_material_access_count == 0
    assert effects.arbitrary_filesystem_scan_count == 0
    assert effects.network_count == effects.http_count == effects.cloud_count == 0
    assert effects.persistent_vector_db_write_count == 0
    assert effects.filesystem_production_write_count == 0
    assert effects.database_write_count == 0
    assert effects.production_registry_write_count == 0
    assert effects.credential_token_use_count == 0
    assert effects.runtime_activation_switch_count == 0
    assert effects.embedding_count == effects.persistence_count == effects.export_count == 0
    assert effects.raw_retention_count == 0
    assert effects.raw_logging_count == 0
    assert effects.raw_cache_count == 0


def assert_usage_unconsumed(call, result):
    assert not result.succeeded
    assert result.usage_after is None
    assert result.authorization_after is None
    assert call["authorization_context"].usage_contract.remaining_read_count == 1
    assert call["authorization_context"].authorization_record.remaining_read_count == 1
    assert call["ledger"].write_count == 0
    assert call["ledger"].receipts == ()
    assert call["ledger"].closures == ()
    assert_no_prohibited_side_effects(result)


def test_human_approval_packet_mismatch_is_pre_read_fail_closed(tmp_path):
    call = actual_execution_chain(tmp_path)
    approval = replace(
        call["human_approval"], packet_digest=digest("different-packet-030")
    )
    result = execute_actual_chain(call, human_approval=approval)
    assert result.reasons == (ActualTrialFailureReason.HUMAN_APPROVAL_INVALID,)
    assert result.side_effects.approved_file_open_count == 0
    assert_usage_unconsumed(call, result)


def test_expired_human_approval_is_pre_read_fail_closed(tmp_path):
    call = actual_execution_chain(tmp_path)
    approval = replace(
        call["human_approval"], expires_at=call["executed_at"]
    )
    result = execute_actual_chain(call, human_approval=approval)
    assert result.reasons == (ActualTrialFailureReason.AUTHORIZATION_INVALID,)
    assert result.side_effects.approved_file_open_count == 0
    assert_usage_unconsumed(call, result)


def test_human_approval_before_preparation_evaluation_is_rejected(tmp_path):
    call = actual_execution_chain(tmp_path)
    approval = replace(
        call["human_approval"],
        approved_at=NOW + timedelta(minutes=41),
    )
    result = execute_actual_chain(call, human_approval=approval)
    assert result.reasons == (ActualTrialFailureReason.AUTHORIZATION_INVALID,)
    assert result.side_effects.approved_file_open_count == 0
    assert_usage_unconsumed(call, result)


def test_rejected_human_approval_cannot_open(tmp_path):
    call = actual_execution_chain(tmp_path)
    approval = replace(
        call["human_approval"],
        approval_result=HumanExecutionApprovalResult.REJECTED,
    )
    result = execute_actual_chain(call, human_approval=approval)
    assert result.side_effects.approved_file_open_count == 0
    assert_usage_unconsumed(call, result)


def test_root_mismatch_is_pre_read_fail_closed(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    call = actual_execution_chain(first_dir)
    other = actual_execution_chain(second_dir)
    result = execute_actual_chain(
        call,
        root_capability=other["provision"].capability,
        target=other["provision"].target,
    )
    assert result.reasons == (ActualTrialFailureReason.ROOT_MISMATCH,)
    assert result.side_effects.approved_file_open_count == 0
    assert_usage_unconsumed(call, result)


def test_target_mismatch_is_pre_read_fail_closed(tmp_path):
    call = actual_execution_chain(tmp_path)
    forged = replace(
        call["provision"].target,
        target_reference_digest=digest("forged-reference-030"),
    )
    result = execute_actual_chain(call, target=forged)
    assert result.reasons == (ActualTrialFailureReason.TARGET_MISMATCH,)
    assert result.side_effects.approved_file_open_count == 0
    assert_usage_unconsumed(call, result)


def test_forged_root_use_cannot_override_side_effect_accounting(tmp_path):
    call = actual_execution_chain(tmp_path)
    capability = call["provision"].capability
    capability.root_use = ActualTrialRootUse.HUMAN_SELECTED_ACTUAL
    with pytest.raises(ActualTrialExecutionError, match="actual_executor_input_invalid"):
        execute_actual_chain(call)
    assert call["ledger"].replay_snapshot() == (
        frozenset(),
        frozenset(),
        frozenset(),
        frozenset(),
    )


@pytest.mark.parametrize(
    "relative",
    ("../outside.txt", "..\\outside.txt", "*.txt", "nested/**/note.txt", ""),
)
def test_traversal_glob_and_empty_target_are_rejected_without_scan(tmp_path, relative):
    root = tmp_path / "root"
    root.mkdir()
    (root / "safe.txt").write_text("Synthetic safe note.", encoding="utf-8")
    with pytest.raises((ActualTrialRootError, ValueError)):
        _provision_controlled_fixture_actual_root(
            root_path=root,
            relative_target=relative,
            root_id="rejected-root-030",
            target_reference_id="rejected-reference-030",
            target_id="rejected-target-030",
            selected_at=NOW,
            allowed_file_types=(".txt",),
        )


def test_final_component_symlink_is_rejected_before_read(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("Synthetic outside payload.", encoding="utf-8")
    link = root / "selected.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ActualTrialRootError):
        _provision_controlled_fixture_actual_root(
            root_path=root,
            relative_target="selected.txt",
            root_id="symlink-root-030",
            target_reference_id="symlink-reference-030",
            target_id="symlink-target-030",
            selected_at=NOW,
            allowed_file_types=(".txt",),
        )


def test_content_mutation_before_open_fails_without_payload_read(tmp_path):
    call = actual_execution_chain(tmp_path)
    call["target_path"].write_text("Mutated synthetic content.", encoding="utf-8")
    result = execute_actual_chain(call)
    assert result.state is ActualTrialExecutionState.OPEN_FAILED
    assert result.side_effects.approved_file_open_count == 0
    assert result.side_effects.approved_file_read_count == 0
    assert_usage_unconsumed(call, result)


def test_toctou_content_mutation_after_read_fails_identity_and_prohibits_retry(
    tmp_path,
):
    call = actual_execution_chain(tmp_path)
    _install_actual_execution_test_hook(
        call["executor"],
        after_read=lambda: call["target_path"].write_text(
            "Changed synthetic content after read.", encoding="utf-8"
        ),
    )
    result = execute_actual_chain(call)
    assert result.state is ActualTrialExecutionState.IDENTITY_FAILED
    assert result.side_effects.approved_file_open_count == 1
    assert result.side_effects.approved_file_read_count == 1
    assert call["human_approval"].canonical_digest in call["ledger"].replay_snapshot()[3]
    assert_usage_unconsumed(call, result)


@pytest.mark.parametrize(
    "content,reason",
    (
        (
            "Synthetic contact synthetic.user@example.invalid",
            ActualTrialFailureReason.CLASSIFICATION_REJECTED,
        ),
        (
            "api_key=synthetic-placeholder",
            ActualTrialFailureReason.CLASSIFICATION_REJECTED,
        ),
        (
            "classification_unknown",
            ActualTrialFailureReason.CLASSIFICATION_AMBIGUOUS,
        ),
    ),
)
def test_disallowed_actual_classification_rejects_after_one_read(
    tmp_path, content, reason
):
    call = actual_execution_chain(tmp_path, content=content)
    result = execute_actual_chain(call)
    assert result.state is ActualTrialExecutionState.CLASSIFICATION_FAILED
    assert result.reasons == (reason,)
    assert result.side_effects.approved_file_open_count == 1
    assert result.side_effects.approved_file_read_count == 1
    assert call["human_approval"].canonical_digest in call["ledger"].replay_snapshot()[3]
    assert_usage_unconsumed(call, result)


def test_masking_residue_rejects_without_usage_consumption(tmp_path):
    call = actual_execution_chain(tmp_path)
    _install_actual_execution_test_hook(call["executor"], masking_residue=True)
    result = execute_actual_chain(call)
    assert result.state is ActualTrialExecutionState.MASKING_FAILED
    assert result.reasons == (ActualTrialFailureReason.MASKING_RESIDUE,)
    assert_usage_unconsumed(call, result)


def test_chunking_residue_rejects_without_usage_consumption(tmp_path):
    call = actual_execution_chain(tmp_path)
    _install_actual_execution_test_hook(call["executor"], chunking_residue=True)
    result = execute_actual_chain(call)
    assert result.state is ActualTrialExecutionState.CHUNKING_FAILED
    assert result.reasons == (ActualTrialFailureReason.CHUNKING_RESIDUE,)
    assert_usage_unconsumed(call, result)


def test_read_failure_does_not_consume_usage_and_spends_human_approval(
    tmp_path, monkeypatch
):
    call = actual_execution_chain(tmp_path)

    def fail_read(*_args, **_kwargs):
        raise OSError("synthetic read fault")

    monkeypatch.setattr(execution_module.os, "read", fail_read)
    result = execute_actual_chain(call)
    assert result.state is ActualTrialExecutionState.READ_FAILED
    assert result.side_effects.approved_file_open_count == 1
    assert result.side_effects.approved_file_read_count == 0
    assert call["human_approval"].canonical_digest in call["ledger"].replay_snapshot()[3]
    assert_usage_unconsumed(call, result)


def test_commit_fault_is_single_swap_safe_and_cannot_auto_retry(tmp_path):
    call = actual_execution_chain(tmp_path)
    before = call["ledger"].replay_snapshot()
    _install_actual_execution_test_hook(call["executor"], commit_fault=True)
    result = execute_actual_chain(call)
    after = call["ledger"].replay_snapshot()
    assert result.state is ActualTrialExecutionState.COMMIT_FAILED
    assert result.reasons == (ActualTrialFailureReason.COMMIT_FAULT,)
    assert call["ledger"].write_count == 0
    assert call["ledger"].receipts == ()
    assert after[:3] == before[:3]
    assert call["human_approval"].canonical_digest in after[3]
    assert_usage_unconsumed(call, result)


def test_second_execution_after_success_is_replay_rejected(tmp_path):
    call = actual_execution_chain(tmp_path)
    assert execute_actual_chain(call).succeeded
    replay = execute_actual_chain(call)
    assert replay.reasons == (ActualTrialFailureReason.REPLAY,)
    assert replay.side_effects.approved_file_open_count == 0
    assert replay.side_effects.approved_file_read_count == 0
    assert_no_prohibited_side_effects(replay)


def test_concurrent_duplicate_is_serialized_before_second_open(tmp_path):
    call = actual_execution_chain(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: execute_actual_chain(call), range(2)))
    assert sum(item.succeeded for item in results) == 1
    assert sum(item.side_effects.approved_file_open_count for item in results) == 1
    assert sum(item.side_effects.approved_file_read_count for item in results) == 1
    rejected = next(item for item in results if not item.succeeded)
    assert rejected.reasons == (ActualTrialFailureReason.REPLAY,)
    assert (call["ledger"].write_count, len(call["ledger"].receipts)) == (1, 1)


def test_controlled_success_has_exact_side_effect_counts(tmp_path):
    call = actual_execution_chain(tmp_path)
    result = execute_actual_chain(call)
    assert result.side_effects.approved_file_open_count == 1
    assert result.side_effects.approved_file_read_count == 1
    assert result.side_effects.actual_local_rag_material_access_count == 0
    assert_no_prohibited_side_effects(result)
