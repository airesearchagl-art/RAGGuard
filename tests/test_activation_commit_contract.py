from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.activation_commit import (
    ActivationAuthorizationState,
    AuthorizationCommitFault,
    AuthorizationCommitReason,
    TestRuntimeAuthorizationLedger,
)
from ragguard.runtime_authorization import RuntimeAuthorizationResult
from tests.test_runtime_authorization_contract import runtime_context


def commit(store, *, fault=AuthorizationCommitFault.NONE, decision_changes=None):
    *_, request, review, approval, evaluation_time = runtime_context()
    from tests.test_runtime_authorization_contract import evaluate
    decision = evaluate()
    if decision_changes:
        decision = replace(decision, **decision_changes)
    return store.commit(record_id="runtime-record-v018", request=request,
                        decision=decision, review=review, approval=approval,
                        committed_at=evaluation_time + timedelta(microseconds=1),
                        committed_by="runtime-commit-operator", fault=fault)


def assert_no_external_effects(result):
    assert (result.persistence_write_count, result.filesystem_write_count,
            result.database_write_count, result.network_count, result.transport_count,
            result.http_count, result.runtime_activation_count, result.token_count,
            result.credential_count) == (0,) * 9


def test_successful_commit_is_authorization_committed_not_active():
    store = TestRuntimeAuthorizationLedger()
    result = commit(store)
    assert result.applied
    assert result.authorization_state is ActivationAuthorizationState.AUTHORIZATION_COMMITTED
    assert result.record is not None and result.record.authorization_generation == 1
    assert result.record.runtime_authorization_approver_id == "runtime-approver-v018"
    assert result.runtime_activation_count == 0
    assert_no_external_effects(result)


@pytest.mark.parametrize("fault", [AuthorizationCommitFault.CANDIDATE_STATE,
                                     AuthorizationCommitFault.COUNTERS,
                                     AuthorizationCommitFault.BEFORE_SWAP])
def test_commit_fault_is_atomic_and_retryable(fault):
    store = TestRuntimeAuthorizationLedger()
    failed = commit(store, fault=fault)
    assert not failed.applied
    assert store.records == ()
    assert (store.write_count, store.mutation_count, store.event_count) == (0, 0, 0)
    assert store.used_request_ids == frozenset()
    assert AuthorizationCommitReason.COMMIT_FAILED in failed.reasons
    assert_no_external_effects(failed)
    assert commit(store).applied


def test_successful_duplicate_is_rejected_without_mutation():
    store = TestRuntimeAuthorizationLedger()
    assert commit(store).applied
    before = (store.records, store.write_count, store.mutation_count, store.event_count)
    duplicate = commit(store, decision_changes={"authorization_generation": 2})
    assert not duplicate.applied
    assert AuthorizationCommitReason.REPLAY_DETECTED in duplicate.reasons
    assert before == (store.records, store.write_count, store.mutation_count, store.event_count)


def test_generation_is_monotonic_and_predecessor_is_digest_bound():
    store = TestRuntimeAuthorizationLedger()
    first = commit(store)
    assert first.record is not None
    *_, request, review, approval, evaluation_time = runtime_context()
    from tests.test_runtime_authorization_contract import digest, evaluate
    request = replace(
        request,
        authorization_request_id="runtime-authorization-v018-second",
        production_authorization_candidate_digest=digest("3"),
        equivalence_approval_digest=digest("4"),
        persistence_receipt_digest=digest("5"),
        activation_commit_plan_digest=digest("6"),
    )
    review = replace(
        review,
        review_id="runtime-review-v018-second",
        authorization_request_digest=request.canonical_digest,
        findings_digest=digest("7"),
    )
    approval = replace(
        approval,
        approval_id="runtime-approval-v018-second",
        authorization_request_digest=request.canonical_digest,
        review_digest=review.canonical_digest,
    )
    decision = replace(
        evaluate(),
        authorization_request_id=request.authorization_request_id,
        authorization_request_digest=request.canonical_digest,
        source_candidate_digest=request.production_authorization_candidate_digest,
        equivalence_approval_digest=request.equivalence_approval_digest,
        persistence_receipt_digest=request.persistence_receipt_digest,
        activation_commit_plan_digest=request.activation_commit_plan_digest,
        authorization_generation=2,
    )
    second = store.commit(
        record_id="runtime-record-v018-second",
        request=request,
        decision=decision,
        review=review,
        approval=approval,
        committed_at=evaluation_time + timedelta(microseconds=2),
        committed_by="runtime-commit-operator",
    )
    assert second.applied and second.record is not None
    assert second.record.authorization_generation == 2
    assert second.record.previous_authorization_record_digest == first.record.canonical_digest
    assert first.record.previous_authorization_record_digest is None


def test_ineligible_decision_cannot_commit():
    store = TestRuntimeAuthorizationLedger()
    result = commit(store, decision_changes={"result": RuntimeAuthorizationResult.INELIGIBLE})
    assert not result.applied
    assert AuthorizationCommitReason.DECISION_INELIGIBLE in result.reasons
    assert_no_external_effects(result)
