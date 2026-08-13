from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.real_world_evidence import (
    EvidenceApprovalResult, EvidenceReviewResult, TestRealWorldValidationLedger,
    ValidationCommitReason,
)
from ragguard.real_world_validation import (
    ControlledExecutionOutcome, RealWorldExecutionRequest,
    TestControlledRealWorldExecutionAdapter, ValidationDecisionState,
)
from tests.test_real_world_evidence_contract import commit, evidence_context
from tests.test_real_world_validation_contract import context, digest, evaluate
from tests.test_real_world_validation_contract import upstream_objects


@pytest.mark.parametrize("field", [
    "manual_validation_approval_digest", "equivalence_approval_digest",
    "runtime_authorization_record_digest", "persistence_receipt_digest",
    "environment_manifest_digest", "product_manifest_digest",
])
def test_source_chain_tampering_is_fail_closed(field):
    assert evaluate(request_changes={field: digest("f")}).state is ValidationDecisionState.INELIGIBLE


def test_v016_manual_chain_tampering_is_independently_fail_closed():
    source_plan, source_chain, _ = upstream_objects()
    tampered_evidence = replace(
        source_chain.evidence,
        validation_plan_digest=digest("f"),
    )
    result = evaluate(
        manual_plan=source_plan,
        manual_chain=replace(source_chain, evidence=tampered_evidence),
    )
    assert result.state is ValidationDecisionState.INELIGIBLE
    assert result.network_count == result.runtime_activation_count == 0


def test_v017_equivalence_chain_tampering_is_independently_fail_closed():
    _, _, source_chain = upstream_objects()
    tampered_descriptor = replace(
        source_chain.descriptor,
        provenance_digest=digest("f"),
    )
    result = evaluate(
        equivalence_chain=replace(source_chain, descriptor=tampered_descriptor)
    )
    assert result.state is ValidationDecisionState.INELIGIBLE
    assert result.registry_write_count == result.http_count == 0


def test_v018_runtime_record_tampering_is_independently_fail_closed():
    runtime, *_ = context()
    result = evaluate(runtime=replace(runtime, committed_by="tampered-runtime-operator"))
    assert result.state is ValidationDecisionState.INELIGIBLE
    assert result.filesystem_count == result.transport_count == 0


def test_v019_persistence_receipt_tampering_is_independently_fail_closed():
    _, receipt, *_ = context()
    result = evaluate(
        persistence=replace(receipt, committed_by="tampered-persistence-operator")
    )
    assert result.state is ValidationDecisionState.INELIGIBLE
    assert result.database_count == result.runtime_activation_count == 0


def test_execution_request_exact_binding_and_zero_side_effect_denial():
    _, _, environment, scenario, authorization, plan, _, approval, now = context()
    request = RealWorldExecutionRequest("execution-v020", authorization.canonical_digest,
        approval.canonical_digest, digest("f"), environment.canonical_digest,
        scenario.canonical_digest, now, "execution-operator")
    result = TestControlledRealWorldExecutionAdapter().execute(decision=evaluate(), request=request,
        authorization_request=authorization, authorization_approval=approval, plan=plan,
        environment=environment, scenario=scenario, started_at=now + timedelta(microseconds=1),
        completed_at=now + timedelta(microseconds=2), outcome=ControlledExecutionOutcome.PASS)
    assert not result.applied and result.receipt is None
    assert (result.filesystem_count, result.database_count, result.network_count,
            result.transport_count, result.http_count, result.runtime_activation_count) == (0, 0, 0, 0, 0, 0)


def test_authorization_roles_cannot_operate_execution():
    _, _, environment, scenario, authorization, plan, _, approval, now = context()
    request = RealWorldExecutionRequest("execution-v020", authorization.canonical_digest,
        approval.canonical_digest, plan.canonical_digest, environment.canonical_digest,
        scenario.canonical_digest, now, authorization.approver_id)
    result = TestControlledRealWorldExecutionAdapter().execute(decision=evaluate(), request=request,
        authorization_request=authorization, authorization_approval=approval, plan=plan,
        environment=environment, scenario=scenario, started_at=now, completed_at=now,
        outcome=ControlledExecutionOutcome.PASS)
    assert not result.applied


@pytest.mark.parametrize("target", ["reviewer", "approver"])
def test_evidence_operator_review_approval_role_separation(target):
    authorization, result, descriptor, review, approval, now = evidence_context()
    assert result.receipt and descriptor and review and approval
    if target == "reviewer": review = replace(review, reviewer_id=result.receipt.operator_id)
    else: approval = replace(approval, approver_id=review.reviewer_id)
    denied = TestRealWorldValidationLedger().commit(record_id="denied-v020",
        authorization_request=authorization, receipt=result.receipt, descriptor=descriptor,
        review=review, approval=approval, validated_at=now, generation=1, predecessor_digest=None)
    assert ValidationCommitReason.ROLE_CONFLICT in denied.reasons
    assert (denied.write_count, denied.mutation_count, denied.event_count,
            denied.transport_count, denied.http_count) == (0, 0, 0, 0, 0)


def test_rejected_review_or_approval_never_commits():
    authorization, result, descriptor, review, approval, now = evidence_context()
    assert result.receipt and descriptor and review and approval
    for denied_review, denied_approval in (
        (replace(review, result=EvidenceReviewResult.REJECTED), approval),
        (review, replace(approval, result=EvidenceApprovalResult.REJECTED)),
    ):
        ledger = TestRealWorldValidationLedger()
        denied = ledger.commit(record_id="denied-v020", authorization_request=authorization,
            receipt=result.receipt, descriptor=descriptor, review=denied_review,
            approval=denied_approval, validated_at=now, generation=1, predecessor_digest=None)
        assert not denied.applied and ledger.write_count == 0


def test_validation_record_supports_review_but_is_not_activation():
    result = commit(TestRealWorldValidationLedger())
    assert result.record is not None
    assert result.record.equivalence_approval_digest
    assert result.runtime_activation_count == result.registry_write_count == 0
