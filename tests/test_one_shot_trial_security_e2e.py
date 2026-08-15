from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.one_shot_trial import (
    ControlledFilesystemReadFault,
    OneShotTrialLedgerFault,
    OneShotTrialReason,
    TestOnlyOneShotTrialLedger,
)
from ragguard.real_data_access_authorization import (
    RealDataAccessAuthorizationLifecycle,
)
from ragguard.storage_adapter import digest
from test_local_rag_execution_session_contract import NOW
from test_one_shot_trial_execution import one_shot_call


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
