from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.one_shot_trial import (
    ControlledFilesystemReadFault,
    OneShotTrialLedgerFault,
    OneShotTrialReason,
    TestOnlyOneShotTrialLedger,
    _install_controlled_filesystem_test_hook,
)
from ragguard.real_data_access_authorization import (
    RealDataAccessAuthorizationLifecycle,
)
from ragguard.storage_adapter import digest
from test_local_rag_execution_session_contract import NOW
from test_one_shot_trial_execution import one_shot_call


OUTSIDE_SYNTHETIC_PAYLOAD = "synthetic outside-root payload must never be read"


def deny(ledger, call, expected_reason):
    before = ledger.replay_snapshot
    result = ledger.execute(**call)
    assert not result.applied
    assert expected_reason in result.reasons
    assert result.receipt is None
    assert result.usage_before.remaining_read_count == 1
    assert result.usage_after is None
    assert result.exhausted_authorization is None
    assert ledger.replay_snapshot == before == (frozenset(),) * 9
    assert ledger.receipts == ()
    assert ledger.pending_closure_receipt_digests == frozenset()
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (0, 0, 0)
    assert result.side_effects.external_all_zero
    return result


def assert_parent_race_denied(ledger, call):
    before = ledger.replay_snapshot
    result = ledger.execute(**call)
    assert not result.applied
    assert any(
        reason in result.reasons
        for reason in (
            OneShotTrialReason.IDENTITY_CHANGED,
            OneShotTrialReason.OPEN_FAILED,
        )
    )
    assert result.execution_result.raw_content_digest != digest(
        OUTSIDE_SYNTHETIC_PAYLOAD
    )
    assert result.side_effects.controlled_adapter_read_count == 0
    assert result.side_effects.actual_arbitrary_file_open_count == 0
    assert result.side_effects.actual_arbitrary_file_read_count == 0
    assert result.side_effects.local_rag_material_access_count == 0
    assert result.side_effects.restricted_material_access_count == 0
    assert result.usage_before.remaining_read_count == 1
    assert result.usage_after is None
    assert result.receipt is None
    assert ledger.replay_snapshot == before == (frozenset(),) * 9
    assert ledger.receipts == ()
    assert ledger.pending_closure_receipt_digests == frozenset()
    return result


def test_security_e2e_controlled_stable_read_and_closure(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    result = ledger.execute(**call)
    assert result.applied
    assert result.side_effects.controlled_adapter_read_count == 1
    assert result.side_effects.actual_arbitrary_file_open_count == 0
    assert result.side_effects.actual_arbitrary_file_read_count == 0
    assert result.side_effects.local_rag_material_access_count == 0
    assert result.side_effects.restricted_material_access_count == 0
    assert result.side_effects.real_data_access_count == 0
    assert result.side_effects.external_all_zero
    closed = ledger.close(
        closure_id="security-e2e-closure-027",
        receipt=result.receipt,
        context=call["context"],
        closed_at=NOW + timedelta(minutes=38),
    )
    assert closed.applied
    assert len(ledger.receipts) == len(ledger.closures) == 1
    assert len(ledger.post_read_evidence) == 1


def test_operator_mismatch_fails_before_resolution_or_open(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    call["request"] = replace(call["request"], operator_id="mismatched-operator")
    result = deny(ledger, call, OneShotTrialReason.ROLE_CONFLICT)
    assert result.side_effects.controlled_adapter_read_count == 0


def test_selector_mismatch_fails_before_open(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    call["target_descriptor"] = replace(
        call["target_descriptor"], selector_digest=digest("selector-mismatch")
    )
    result = deny(ledger, call, OneShotTrialReason.PRE_OPEN_FAILED)
    assert result.side_effects.controlled_adapter_read_count == 0


@pytest.mark.parametrize(
    "lifecycle,remaining",
    (
        (RealDataAccessAuthorizationLifecycle.EXPIRED, 1),
        (RealDataAccessAuthorizationLifecycle.REVOKED, 1),
        (RealDataAccessAuthorizationLifecycle.EXHAUSTED, 0),
        (RealDataAccessAuthorizationLifecycle.SUPERSEDED, 1),
    ),
)
def test_non_authorized_lifecycle_fails_without_consumption(
    tmp_path, lifecycle, remaining
):
    ledger, call, _ = one_shot_call(tmp_path)
    record = call["context"].authorization_record
    object.__setattr__(record, "lifecycle", lifecycle)
    object.__setattr__(record, "remaining_read_count", remaining)
    result = deny(ledger, call, OneShotTrialReason.PRE_OPEN_FAILED)
    assert result.side_effects.controlled_adapter_read_count == 0


def test_future_and_expired_request_metadata_fail_closed(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    call["request"] = replace(
        call["request"], requested_at=NOW + timedelta(minutes=40)
    )
    deny(ledger, call, OneShotTrialReason.TEMPORAL_INVALID)

    second_root = tmp_path / "second"
    second_root.mkdir()
    ledger, call, _ = one_shot_call(second_root)
    call["request"] = replace(
        call["request"], expires_at=NOW + timedelta(minutes=30, seconds=30)
    )
    deny(ledger, call, OneShotTrialReason.TEMPORAL_INVALID)


def test_actual_controlled_fixture_content_mismatch_fails_identity_chain(tmp_path):
    ledger, call, root = one_shot_call(tmp_path)
    (root / "synthetic-fixture.txt").write_text(
        "synthetic changed marker", encoding="utf-8"
    )
    result = deny(ledger, call, OneShotTrialReason.IDENTITY_CHANGED)
    assert result.side_effects.controlled_adapter_read_count == 1


@pytest.mark.parametrize(
    "fault",
    (
        ControlledFilesystemReadFault.OPEN_IDENTITY_CHANGED,
        ControlledFilesystemReadFault.POST_IDENTITY_CHANGED,
        ControlledFilesystemReadFault.CONTENT_MUTATED,
        ControlledFilesystemReadFault.SYMLINK_SWAPPED,
    ),
)
def test_toctou_faults_are_fail_closed_and_do_not_consume(tmp_path, fault):
    ledger, call, _ = one_shot_call(tmp_path, read_fault=fault)
    deny(ledger, call, OneShotTrialReason.IDENTITY_CHANGED)


@pytest.mark.parametrize(
    "fault,reason",
    (
        (
            ControlledFilesystemReadFault.CLASSIFICATION_FAILED,
            OneShotTrialReason.CLASSIFICATION_FAILED,
        ),
        (
            ControlledFilesystemReadFault.MASKING_FAILED,
            OneShotTrialReason.MASKING_FAILED,
        ),
    ),
)
def test_post_read_verification_failure_does_not_consume(tmp_path, fault, reason):
    ledger, call, _ = one_shot_call(tmp_path, read_fault=fault)
    deny(ledger, call, reason)


def test_forged_receipt_and_commit_fault_leave_state_retryable(tmp_path):
    forged_ledger, forged_call, _ = one_shot_call(
        tmp_path, ledger_fault=OneShotTrialLedgerFault.FORGED_RECEIPT
    )
    deny(forged_ledger, forged_call, OneShotTrialReason.INVALID_CHAIN)

    second_root = tmp_path / "second"
    second_root.mkdir()
    fault_ledger, fault_call, _ = one_shot_call(
        second_root, ledger_fault=OneShotTrialLedgerFault.BEFORE_SWAP
    )
    deny(fault_ledger, fault_call, OneShotTrialReason.COMMIT_FAULT)
    fault_call["ledger_fault"] = OneShotTrialLedgerFault.NONE
    retried = fault_ledger.execute(**fault_call)
    assert retried.applied


def test_forged_target_reference_fails_before_controlled_read(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    object.__setattr__(call["target_reference"], "target_reference_id", "forged")
    result = deny(ledger, call, OneShotTrialReason.INVALID_CHAIN)
    assert result.side_effects.controlled_adapter_read_count == 0


def test_closure_operator_binding_is_exact_and_failed_closed(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    result = ledger.execute(**call)
    assert result.applied
    object.__setattr__(call["context"].authorization_record, "operator_id", "forged")
    closed = ledger.close(
        closure_id="forged-operator-closure-027",
        receipt=result.receipt,
        context=call["context"],
        closed_at=NOW + timedelta(minutes=38),
    )
    assert not closed.applied
    assert closed.reasons == (OneShotTrialReason.CLOSURE_INVALID,)
    assert ledger.closures == ()


def test_safe_resolve_then_parent_symlink_swap_never_reads_outside_payload(
    tmp_path,
):
    ledger, call, root = one_shot_call(
        tmp_path, relative_name="safe-parent/synthetic-fixture.txt"
    )
    outside = tmp_path / "outside-synthetic-parent"
    outside.mkdir()
    (outside / "synthetic-fixture.txt").write_text(
        OUTSIDE_SYNTHETIC_PAYLOAD, encoding="utf-8"
    )

    def swap_parent_to_symlink():
        assert call["resolver"]._issued_handles
        safe_parent = root / "safe-parent"
        safe_parent.rename(tmp_path / "pinned-safe-parent")
        try:
            safe_parent.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("controlled fixture directory symlink is unavailable")

    _install_controlled_filesystem_test_hook(call["adapter"], swap_parent_to_symlink)
    assert_parent_race_denied(ledger, call)


def test_safe_resolve_then_parent_directory_rename_swap_is_rejected_before_read(
    tmp_path,
):
    ledger, call, root = one_shot_call(
        tmp_path, relative_name="safe-parent/synthetic-fixture.txt"
    )
    replacement = tmp_path / "replacement-parent"
    replacement.mkdir()
    (replacement / "synthetic-fixture.txt").write_text(
        OUTSIDE_SYNTHETIC_PAYLOAD, encoding="utf-8"
    )

    def rename_swap_parent():
        (root / "safe-parent").rename(tmp_path / "pinned-original-parent")
        replacement.rename(root / "safe-parent")

    _install_controlled_filesystem_test_hook(call["adapter"], rename_swap_parent)
    assert_parent_race_denied(ledger, call)


def test_nested_parent_component_swap_is_rejected_before_raw_read(tmp_path):
    ledger, call, root = one_shot_call(
        tmp_path,
        relative_name="outer-parent/inner-parent/synthetic-fixture.txt",
    )
    replacement = tmp_path / "replacement-inner-parent"
    replacement.mkdir()
    (replacement / "synthetic-fixture.txt").write_text(
        OUTSIDE_SYNTHETIC_PAYLOAD, encoding="utf-8"
    )

    def swap_nested_parent():
        original = root / "outer-parent" / "inner-parent"
        original.rename(tmp_path / "pinned-original-inner-parent")
        replacement.rename(root / "outer-parent" / "inner-parent")

    _install_controlled_filesystem_test_hook(call["adapter"], swap_nested_parent)
    assert_parent_race_denied(ledger, call)


def test_final_component_symlink_swap_is_rejected_before_raw_read(tmp_path):
    ledger, call, root = one_shot_call(
        tmp_path, relative_name="safe-parent/synthetic-fixture.txt"
    )
    outside = tmp_path / "outside-final-synthetic.txt"
    outside.write_text(OUTSIDE_SYNTHETIC_PAYLOAD, encoding="utf-8")

    def swap_final_to_symlink():
        target = root / "safe-parent" / "synthetic-fixture.txt"
        target.rename(tmp_path / "pinned-original-final.txt")
        try:
            target.symlink_to(outside)
        except OSError:
            pytest.skip("controlled fixture file symlink is unavailable")

    _install_controlled_filesystem_test_hook(call["adapter"], swap_final_to_symlink)
    assert_parent_race_denied(ledger, call)


def test_resolver_safe_open_unsafe_root_escape_race_fails_closed(tmp_path):
    ledger, call, root = one_shot_call(
        tmp_path,
        relative_name="race-parent/nested/synthetic-fixture.txt",
    )
    outside = tmp_path / "outside-race-tree"
    (outside / "nested").mkdir(parents=True)
    (outside / "nested" / "synthetic-fixture.txt").write_text(
        OUTSIDE_SYNTHETIC_PAYLOAD, encoding="utf-8"
    )

    def introduce_reparse_race():
        parent = root / "race-parent"
        parent.rename(tmp_path / "pinned-race-parent")
        try:
            parent.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("controlled fixture reparse simulation is unavailable")

    _install_controlled_filesystem_test_hook(call["adapter"], introduce_reparse_race)
    assert_parent_race_denied(ledger, call)
