from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from ragguard.real_world_evidence import (
    EvidenceApprovalResult, EvidenceClass, EvidenceReviewResult,
    ExecutionEvidenceDescriptor, RealWorldEvidenceApproval, RealWorldEvidenceError,
    RealWorldEvidenceReview, TestRealWorldValidationLedger, ValidationCommitFault,
    ValidationCommitReason,
)
from ragguard.real_world_validation import (
    ControlledExecutionOutcome, RealWorldExecutionRequest,
    TestControlledRealWorldExecutionAdapter,
)
from tests.test_real_world_validation_contract import context, digest, evaluate


def evidence_context(outcome=ControlledExecutionOutcome.PASS):
    _, _, environment, scenario, authorization, plan, _, auth_approval, now = context()
    request = RealWorldExecutionRequest(
        "execution-v020", authorization.canonical_digest, auth_approval.canonical_digest,
        plan.canonical_digest, environment.canonical_digest, scenario.canonical_digest,
        now + timedelta(microseconds=1), "execution-operator")
    result = TestControlledRealWorldExecutionAdapter().execute(
        decision=evaluate(), request=request, authorization_request=authorization,
        authorization_approval=auth_approval, plan=plan, environment=environment,
        scenario=scenario, started_at=request.requested_at + timedelta(microseconds=1),
        completed_at=request.requested_at + timedelta(microseconds=2), outcome=outcome)
    if result.receipt is None:
        return authorization, result, None, None, None, now
    receipt = result.receipt
    descriptor = ExecutionEvidenceDescriptor(
        "evidence-v020", receipt.canonical_digest, receipt.behavior_digest,
        receipt.coverage_digest, receipt.failure_digest, receipt.environment_manifest_digest,
        authorization.product_manifest_digest, environment.configuration_digest,
        environment.protocol_digest, EvidenceClass.CONTROLLED_SYNTHETIC,
        receipt.completed_at + timedelta(microseconds=1), "evidence-creator")
    review = RealWorldEvidenceReview(
        "evidence-review-v020", descriptor.canonical_digest,
        descriptor.created_at + timedelta(microseconds=1), "evidence-reviewer",
        EvidenceReviewResult.APPROVED, digest("f"))
    approval = RealWorldEvidenceApproval(
        "evidence-approval-v020", descriptor.canonical_digest, review.canonical_digest,
        review.reviewed_at + timedelta(microseconds=1), "evidence-approver",
        EvidenceApprovalResult.APPROVED)
    return authorization, result, descriptor, review, approval, approval.approved_at + timedelta(microseconds=1)


def commit(store, *, outcome=ControlledExecutionOutcome.PASS,
           fault=ValidationCommitFault.NONE, changes=None):
    authorization, result, descriptor, review, approval, now = evidence_context(outcome)
    assert result.receipt is not None and descriptor and review and approval
    changes = changes or {}
    return store.commit(record_id="validation-record-v020", authorization_request=authorization,
        receipt=changes.get("receipt", result.receipt), descriptor=changes.get("descriptor", descriptor),
        review=changes.get("review", review), approval=changes.get("approval", approval),
        validated_at=changes.get("validated_at", now), generation=changes.get("generation", 1),
        predecessor_digest=changes.get("predecessor_digest"), fault=fault)


def test_evidence_contracts_are_immutable_and_safe():
    _, _, descriptor, review, approval, _ = evidence_context()
    assert descriptor and review and approval
    assert replace(descriptor).canonical_digest == descriptor.canonical_digest
    assert "payload" not in repr(descriptor).lower()
    with pytest.raises(FrozenInstanceError):
        descriptor.created_by = "changed"  # type: ignore[misc]


def test_successful_commit_is_atomic_and_not_runtime_activation():
    store = TestRealWorldValidationLedger()
    result = commit(store)
    assert result.applied and result.record is not None
    assert (result.write_count, result.mutation_count, result.event_count) == (1, 1, 1)
    assert result.runtime_activation_count == result.registry_write_count == result.filesystem_count == 0


@pytest.mark.parametrize("fault", [ValidationCommitFault.CANDIDATE_STATE,
                                    ValidationCommitFault.COUNTERS,
                                    ValidationCommitFault.BEFORE_SWAP])
def test_commit_fault_preserves_entire_state_and_allows_retry(fault):
    store = TestRealWorldValidationLedger()
    before = (store.records, store.used_digests, store.write_count, store.mutation_count, store.event_count)
    failed = commit(store, fault=fault)
    assert not failed.applied and failed.reasons == (ValidationCommitReason.COMMIT_FAULT,)
    assert before == (store.records, store.used_digests, store.write_count, store.mutation_count, store.event_count)
    assert commit(store).applied


def test_successful_replay_is_rejected_without_side_effects():
    store = TestRealWorldValidationLedger()
    assert commit(store).applied
    before = (store.records, store.used_digests, store.write_count)
    replay = commit(store, changes={"generation": 2,
        "predecessor_digest": store.records[-1].canonical_digest})
    assert not replay.applied and ValidationCommitReason.REPLAY_DETECTED in replay.reasons
    assert before == (store.records, store.used_digests, store.write_count)


@pytest.mark.parametrize("outcome", [ControlledExecutionOutcome.FAIL,
                                      ControlledExecutionOutcome.INCOMPLETE])
def test_failed_or_incomplete_execution_cannot_be_approved(outcome):
    authorization, result, descriptor, review, approval, now = evidence_context(outcome)
    assert result.receipt is not None and descriptor and review and approval
    ledger = TestRealWorldValidationLedger()
    denied = ledger.commit(record_id="denied-v020", authorization_request=authorization,
        receipt=result.receipt, descriptor=descriptor, review=review, approval=approval,
        validated_at=now, generation=1, predecessor_digest=None)
    assert not denied.applied and ValidationCommitReason.EXECUTION_NOT_PASSED in denied.reasons
    assert (denied.write_count, denied.mutation_count, denied.event_count,
            denied.network_count, denied.runtime_activation_count) == (0, 0, 0, 0, 0)


def test_review_and_approval_exact_binding_and_ordering():
    authorization, result, descriptor, review, approval, now = evidence_context()
    assert result.receipt and descriptor and review and approval
    ledger = TestRealWorldValidationLedger()
    bad = replace(approval, review_digest=digest("0"))
    denied = ledger.commit(record_id="denied-v020", authorization_request=authorization,
        receipt=result.receipt, descriptor=descriptor, review=review, approval=bad,
        validated_at=now, generation=1, predecessor_digest=None)
    assert ValidationCommitReason.INVALID_CHAIN in denied.reasons
    same_time = replace(approval, approved_at=review.reviewed_at)
    denied = ledger.commit(record_id="denied-v020", authorization_request=authorization,
        receipt=result.receipt, descriptor=descriptor, review=review, approval=same_time,
        validated_at=now, generation=1, predecessor_digest=None)
    assert ValidationCommitReason.TEMPORAL_INVALID in denied.reasons


def test_forged_receipt_cannot_be_constructed():
    _, result, *_ = evidence_context()
    assert result.receipt
    with pytest.raises(RealWorldEvidenceError):
        # evidence constructor still validates every digest and safe type
        ExecutionEvidenceDescriptor("bad", "forged", digest("1"), digest("2"), digest("3"),
            digest("4"), digest("5"), digest("6"), digest("7"),
            EvidenceClass.CONTROLLED_SYNTHETIC, result.receipt.completed_at, "creator")
