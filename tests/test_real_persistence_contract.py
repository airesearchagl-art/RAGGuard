from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone

import pytest

from ragguard.activation_commit import TestRuntimeAuthorizationLedger
from ragguard.real_persistence import (
    DurableCommitFault, DurablePersistenceReason, DurablePersistenceState,
    EMPTY_DURABLE_STORE_STATE_DIGEST, PersistenceAuthorizationApproval,
    PersistenceAuthorizationRequest, PersistenceAuthorizationResult,
    PersistenceAuthorizationReview, PersistenceIntent, PersistenceTransactionPlan,
    TargetStoreClass, TestAtomicDurableStore, canonical_after_state_digest,
    evaluate_durable_persistence,
)
from tests.test_activation_commit_contract import commit as commit_runtime
from tests.test_production_persistence_contract import approved_policy


def digest(char: str) -> str:
    return "sha256:" + char * 64


def context():
    ledger = TestRuntimeAuthorizationLedger()
    runtime = commit_runtime(ledger).record
    assert runtime is not None
    policy = approved_policy()
    request = PersistenceAuthorizationRequest(
        "persistence-auth-v019", runtime.canonical_digest,
        runtime.authorization_request_digest, runtime.runtime_review_digest,
        runtime.runtime_approval_digest, runtime.source_candidate_digest,
        runtime.equivalence_approval_digest, policy.canonical_digest,
        EMPTY_DURABLE_STORE_STATE_DIGEST, 1, None,
        "profile-v019", "version-v019", "product-v019", "product-version-v019",
        "protocol-v019", runtime.committed_at + timedelta(microseconds=1),
        "persistence-requester", "persistence-reviewer", "persistence-approver",
        "persistence-operator", runtime.runtime_authorization_approver_id)
    review = PersistenceAuthorizationReview(
        "persistence-review-v019", request.canonical_digest,
        request.requested_at + timedelta(microseconds=1), "persistence-reviewer",
        True, digest("1"))
    approval = PersistenceAuthorizationApproval(
        "persistence-approval-v019", request.canonical_digest, review.canonical_digest,
        review.reviewed_at + timedelta(microseconds=1), "persistence-approver",
        PersistenceAuthorizationResult.APPROVED)
    intent = PersistenceIntent(
        "persistence-intent-v019", request.canonical_digest, runtime.canonical_digest,
        TargetStoreClass.DURABLE_APPEND_ONLY, EMPTY_DURABLE_STORE_STATE_DIGEST, 1,
        None, digest("2"), digest("3"), approval.approved_at + timedelta(microseconds=1),
        "persistence-operator")
    after = canonical_after_state_digest(EMPTY_DURABLE_STORE_STATE_DIGEST,
                                         intent.content_digest, 1, None)
    plan = PersistenceTransactionPlan(intent.canonical_digest,
        EMPTY_DURABLE_STORE_STATE_DIGEST, after, 1, None, intent.content_digest,
        "commit-v019", "recovery-v019", intent.created_at + timedelta(microseconds=1),
        "persistence-operator")
    evaluation_time = plan.planned_at + timedelta(microseconds=1)
    return runtime, policy, request, review, approval, intent, plan, evaluation_time


def evaluate(**changes):
    runtime, policy, request, review, approval, intent, plan, evaluation_time = context()
    request = replace(request, **changes.pop("request_changes", {}))
    if request.canonical_digest != review.authorization_request_digest:
        review = replace(review, authorization_request_digest=request.canonical_digest)
        approval = replace(approval, authorization_request_digest=request.canonical_digest,
                           review_digest=review.canonical_digest)
        intent = replace(intent, authorization_request_digest=request.canonical_digest)
        plan = replace(plan, intent_digest=intent.canonical_digest)
    return evaluate_durable_persistence(request, runtime, policy,
        changes.pop("intent", intent), changes.pop("plan", plan),
        changes.pop("review", review), changes.pop("approval", approval),
        current_store_state_digest=changes.pop("state_digest", EMPTY_DURABLE_STORE_STATE_DIGEST),
        current_generation=changes.pop("generation", 0),
        current_predecessor_digest=changes.pop("predecessor", None),
        lifecycle_active=changes.pop("lifecycle_active", True),
        pending_revalidation=changes.pop("pending_revalidation", False),
        pending_lifecycle_transition=changes.pop("pending_transition", False),
        replacement_predecessor=changes.pop("replacement_predecessor", False),
        revoked_source=changes.pop("revoked_source", False),
        evaluation_time=changes.pop("evaluation_time", evaluation_time), **changes)


def test_contracts_are_immutable_and_deterministic():
    _, _, request, _, _, intent, plan, _ = context()
    assert replace(request).canonical_digest == request.canonical_digest
    assert replace(intent).canonical_digest == intent.canonical_digest
    assert replace(plan).canonical_digest == plan.canonical_digest
    with pytest.raises(FrozenInstanceError):
        request.requested_by = "other"  # type: ignore[misc]


def test_safe_summaries_use_canonical_identity_without_payload_or_location():
    _, _, request, _, _, intent, _, _ = context()
    assert request.safe_summary.canonical_digest == request.canonical_digest
    assert intent.safe_summary.canonical_digest == intent.canonical_digest
    assert "path" not in repr(request.safe_summary).lower()
    assert "credential" not in repr(intent.safe_summary).lower()


def test_utc_normalization_and_microseconds_are_canonical():
    *_, request, _, _, _, _, _ = context()
    offset = timezone(timedelta(hours=9))
    assert replace(request, requested_at=request.requested_at.astimezone(offset)).canonical_digest == request.canonical_digest
    assert replace(request, requested_at=request.requested_at + timedelta(microseconds=1)).canonical_digest != request.canonical_digest


def test_full_chain_is_ready_not_persisted_or_active():
    decision = evaluate()
    assert decision.state is DurablePersistenceState.READY_FOR_DURABLE_COMMIT
    assert (decision.filesystem_write_count, decision.database_write_count,
            decision.registry_write_count, decision.runtime_activation_count) == (0, 0, 0, 0)


def test_missing_authorization_and_plan_are_explicit():
    assert evaluate(review=None, approval=None).state is DurablePersistenceState.NEEDS_PERSISTENCE_AUTHORIZATION
    assert evaluate(intent=None, plan=None).state is DurablePersistenceState.NEEDS_TRANSACTION_PLAN


@pytest.mark.parametrize("field", ["use_current_alias", "use_latest_alias", "allow_fallback", "infer_generation"])
def test_alias_fallback_and_inference_are_ineligible(field):
    assert evaluate(request_changes={field: True}).state is DurablePersistenceState.INELIGIBLE


@pytest.mark.parametrize("kwargs,reason", [
    ({"lifecycle_active": False}, DurablePersistenceReason.LIFECYCLE_INVALID),
    ({"pending_revalidation": True}, DurablePersistenceReason.REVALIDATION_PENDING),
    ({"pending_transition": True}, DurablePersistenceReason.TRANSITION_PENDING),
    ({"replacement_predecessor": True}, DurablePersistenceReason.SOURCE_INELIGIBLE),
    ({"revoked_source": True}, DurablePersistenceReason.SOURCE_INELIGIBLE),
    ({"generation": 1}, DurablePersistenceReason.GENERATION_MISMATCH),
    ({"state_digest": digest("8")}, DurablePersistenceReason.STORE_STATE_MISMATCH),
    ({"predecessor": digest("9")}, DurablePersistenceReason.PREDECESSOR_MISMATCH),
])
def test_hard_gates_fail_closed(kwargs, reason):
    decision = evaluate(**kwargs)
    assert decision.state is DurablePersistenceState.INELIGIBLE
    assert reason in decision.reasons


def test_stale_and_future_authorization_are_rejected():
    *_, evaluation_time = context()
    assert DurablePersistenceReason.STALE_AUTHORIZATION in evaluate(
        evaluation_time=evaluation_time + timedelta(days=91)).reasons
    runtime, policy, request, review, approval, intent, plan, _ = context()
    future = request.requested_at - timedelta(microseconds=1)
    result = evaluate_durable_persistence(request, runtime, policy, intent, plan, review,
        approval, current_store_state_digest=EMPTY_DURABLE_STORE_STATE_DIGEST,
        current_generation=0, current_predecessor_digest=None, lifecycle_active=True,
        pending_revalidation=False, pending_lifecycle_transition=False,
        replacement_predecessor=False, revoked_source=False, evaluation_time=future)
    assert DurablePersistenceReason.TEMPORAL_INVALID in result.reasons


def test_role_conflict_and_replay_are_rejected():
    assert DurablePersistenceReason.ROLE_CONFLICT in evaluate(
        request_changes={"persistence_approver_id": "persistence-requester"}).reasons
    _, _, request, _, _, intent, plan, _ = context()
    assert DurablePersistenceReason.REPLAY_DETECTED in evaluate(
        used_request_digests=frozenset({request.canonical_digest})).reasons
    assert evaluate(used_intent_digests=frozenset({intent.canonical_digest})).state is DurablePersistenceState.NEEDS_TRANSACTION_PLAN
    assert evaluate(used_plan_digests=frozenset({plan.canonical_digest})).state is DurablePersistenceState.NEEDS_TRANSACTION_PLAN


def test_runtime_authorization_approver_identity_is_exact_bound_and_separated():
    assert DurablePersistenceReason.DIGEST_MISMATCH in evaluate(
        request_changes={"runtime_authorization_approver_id": "other-runtime-approver"}).reasons
    assert DurablePersistenceReason.ROLE_CONFLICT in evaluate(
        request_changes={"persistence_operator_id": "runtime-approver-v018"}).reasons


def commit(store, fault=DurableCommitFault.NONE):
    runtime, _, request, _, _, intent, plan, evaluation_time = context()
    return store.commit(receipt_id="durable-receipt-v019", decision=evaluate(),
        request=request, intent=intent, plan=plan, runtime_record=runtime,
        committed_at=evaluation_time + timedelta(microseconds=1),
        committed_by="persistence-operator", fault=fault)


def test_successful_commit_single_swaps_and_returns_receipt():
    store = TestAtomicDurableStore()
    result = commit(store)
    assert result.applied and result.receipt is not None
    assert result.receipt.commit_result == "committed"
    assert (store.write_count, store.mutation_count, store.event_count) == (1, 1, 1)
    assert result.runtime_activation_count == result.filesystem_write_count == 0


@pytest.mark.parametrize("fault", [DurableCommitFault.CANDIDATE_STATE,
    DurableCommitFault.RECEIPT, DurableCommitFault.COUNTERS,
    DurableCommitFault.BEFORE_SWAP])
def test_commit_fault_is_atomic_does_not_consume_and_is_retryable(fault):
    store = TestAtomicDurableStore()
    before = store.snapshot
    failed = commit(store, fault)
    assert not failed.applied and failed.receipt is None
    assert store.snapshot == before
    assert store.used_intents == frozenset()
    assert (store.write_count, store.mutation_count, store.event_count) == (0, 0, 0)
    assert commit(store).applied


def test_duplicate_success_is_rejected_without_state_change():
    store = TestAtomicDurableStore()
    assert commit(store).applied
    before = store.snapshot
    duplicate = commit(store)
    assert not duplicate.applied
    assert DurablePersistenceReason.REPLAY_DETECTED in duplicate.reasons
    assert store.snapshot == before
