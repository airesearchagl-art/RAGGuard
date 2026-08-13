from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.persistence_recovery import (
    PersistenceRecoveryReason, PersistenceRecoveryRequest, PersistenceRecoveryState,
    evaluate_persistence_recovery,
)
from ragguard.real_persistence import TestAtomicDurableStore
from tests.test_real_persistence_contract import commit, context, digest


def recovery_context():
    store = TestAtomicDurableStore()
    result = commit(store)
    assert result.receipt is not None
    receipt = result.receipt
    *_, evaluation_time = context()
    request = PersistenceRecoveryRequest("recovery-request-v019",
        receipt.authorization_record_digest, receipt.intent_digest,
        receipt.transaction_plan_digest, receipt.canonical_digest,
        receipt.after_state_digest, receipt.generation, receipt.predecessor_digest,
        evaluation_time + timedelta(microseconds=2), "recovery-operator",
        "recovery-reviewer")
    return request, receipt, store.snapshot, request.requested_at + timedelta(microseconds=1)


def test_committed_receipt_and_snapshot_are_consistent():
    request, receipt, snapshot, now = recovery_context()
    result = evaluate_persistence_recovery(request, receipt, snapshot, evaluation_time=now)
    assert result.state is PersistenceRecoveryState.COMMITTED_AND_CONSISTENT
    assert result.record is not None
    assert result.runtime_activation_count == result.registry_write_count == 0


def test_no_commit_detected_is_explicit_and_does_not_recommit():
    request, _, _, now = recovery_context()
    request = replace(request, expected_receipt_digest=None, expected_generation=0,
                      expected_predecessor_digest=None)
    result = evaluate_persistence_recovery(request, None, None, evaluation_time=now)
    assert result.state is PersistenceRecoveryState.NO_COMMIT_DETECTED
    assert result.filesystem_write_count == 0


@pytest.mark.parametrize("drop", ["receipt", "snapshot"])
def test_partial_state_is_ambiguous(drop):
    request, receipt, snapshot, now = recovery_context()
    result = evaluate_persistence_recovery(request,
        None if drop == "receipt" else receipt,
        None if drop == "snapshot" else snapshot, evaluation_time=now)
    assert result.state is PersistenceRecoveryState.INCOMPLETE_OR_AMBIGUOUS
    assert PersistenceRecoveryReason.AMBIGUOUS_STATE in result.reasons


@pytest.mark.parametrize("field,value", [
    ("expected_authorization_record_digest", digest("4")),
    ("expected_intent_digest", digest("5")),
    ("expected_transaction_plan_digest", digest("6")),
    ("expected_receipt_digest", digest("7")),
    ("expected_store_state_digest", digest("8")),
])
def test_digest_corruption_is_fail_closed(field, value):
    request, receipt, snapshot, now = recovery_context()
    result = evaluate_persistence_recovery(replace(request, **{field: value}),
                                           receipt, snapshot, evaluation_time=now)
    assert result.state is PersistenceRecoveryState.CORRUPTION_DETECTED


def test_generation_rollback_jump_and_predecessor_mismatch_are_rejected():
    request, receipt, snapshot, now = recovery_context()
    assert PersistenceRecoveryReason.GENERATION_INVALID in evaluate_persistence_recovery(
        replace(request, expected_generation=0), receipt, snapshot,
        evaluation_time=now).reasons
    assert PersistenceRecoveryReason.GENERATION_INVALID in evaluate_persistence_recovery(
        replace(request, expected_generation=3), receipt, snapshot,
        evaluation_time=now).reasons
    assert PersistenceRecoveryReason.PREDECESSOR_INVALID in evaluate_persistence_recovery(
        replace(request, expected_predecessor_digest=digest("9")), receipt, snapshot,
        evaluation_time=now).reasons


def test_role_conflict_future_time_and_replay_are_rejected():
    request, receipt, snapshot, now = recovery_context()
    assert PersistenceRecoveryReason.ROLE_CONFLICT in evaluate_persistence_recovery(
        replace(request, recovery_reviewer_id="recovery-operator"), receipt, snapshot,
        evaluation_time=now).reasons
    assert PersistenceRecoveryReason.TEMPORAL_INVALID in evaluate_persistence_recovery(
        request, receipt, snapshot, evaluation_time=request.requested_at - timedelta(microseconds=1)).reasons
    assert PersistenceRecoveryReason.REPLAY_DETECTED in evaluate_persistence_recovery(
        request, receipt, snapshot, evaluation_time=now,
        used_recovery_request_digests=frozenset({request.canonical_digest})).reasons
