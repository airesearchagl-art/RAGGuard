from dataclasses import fields
from datetime import timedelta

import pytest

from ragguard.local_rag_execution import *
from ragguard.local_rag_environment import (
    EnvironmentAttestationDecision,
    EnvironmentAttestationState,
)
from ragguard.local_rag_integration import RAGStage
from ragguard.storage_adapter import digest
from test_local_rag_execution_session_contract import (
    NOW,
    approved_session_chain,
    controlled_execution,
)


def reviewed_execution():
    chain, evidence, accounting, receipt = controlled_execution()
    _, result, _, roles, _, _, env_decision, *_ = chain
    review = SessionExecutionReview("session-review-023", result.session.canonical_digest,
        receipt.canonical_digest, "session-reviewer", NOW + timedelta(minutes=13),
        SessionReviewResult.APPROVED, digest("security-review-findings"))
    approval = SessionExecutionApproval("session-approval-023", result.session.canonical_digest,
        receipt.canonical_digest, review.canonical_digest, "session-approver",
        NOW + timedelta(minutes=14), SessionApprovalResult.APPROVED)
    return chain, evidence, accounting, receipt, review, approval, roles, env_decision


def readiness_for(chain, evidence, accounting, receipt, review, approval, roles, env_decision):
    return evaluate_real_data_trial_readiness(env_decision, chain[1].session, evidence, receipt,
        accounting, review, approval, roles, evaluation_time=NOW + timedelta(minutes=15))


def test_readiness_progresses_through_environment_session_and_security_gates():
    chain, evidence, accounting, receipt, review, approval, roles, env_decision = reviewed_execution()
    no_session = evaluate_real_data_trial_readiness(env_decision, None, None, None, None,
        None, None, roles, evaluation_time=NOW + timedelta(minutes=15))
    no_execution = evaluate_real_data_trial_readiness(env_decision, chain[1].session,
        None, None, None, None, None, roles, evaluation_time=NOW + timedelta(minutes=15))
    no_security = readiness_for(chain, evidence, accounting, receipt, None, None,
                                roles, env_decision)
    eligible = readiness_for(chain, evidence, accounting, receipt, review, approval,
                             roles, env_decision)
    unverified_environment = EnvironmentAttestationDecision(
        EnvironmentAttestationState.INELIGIBLE, env_decision.manifest_digest,
        env_decision.suite_digest, env_decision.evidence_digest,
        ("verification_not_passed",), NOW + timedelta(minutes=3))
    no_environment = evaluate_real_data_trial_readiness(unverified_environment, None, None,
        None, None, None, None, roles, evaluation_time=NOW + timedelta(minutes=15))
    assert no_environment.state is RealDataTrialReadinessState.NEEDS_ENVIRONMENT_ATTESTATION
    assert no_session.state is RealDataTrialReadinessState.NEEDS_CONTROLLED_SESSION_EXECUTION
    assert no_execution.state is RealDataTrialReadinessState.NEEDS_CONTROLLED_SESSION_EXECUTION
    assert no_security.state is RealDataTrialReadinessState.NEEDS_SECURITY_REVIEW
    assert eligible.state is RealDataTrialReadinessState.ELIGIBLE_FOR_EXPLICIT_REAL_DATA_TRIAL_APPROVAL_REVIEW
    assert eligible.real_data_approved is eligible.real_data_use_authorized is False
    assert eligible.production_active is False
    assert approval.real_data_use_authorized is False


def test_eligible_decision_has_zero_external_side_effect_and_real_data_counts():
    values = reviewed_execution()
    decision = readiness_for(*values)
    assert all(value == 0 for name, value in vars(decision).items() if name.endswith("_count"))
    assert values[2].all_zero


def test_injected_stage_failure_is_ineligible_and_downstream_stages_are_incomplete():
    chain = approved_session_chain()
    _, result, request, roles, env_manifest, _, env_decision, _, env_approval, _, \
        int_manifest, fixture, plan, *_ = chain
    evidence, accounting, receipt = ControlledLocalRAGExecutionAdapter().execute(
        execution_receipt_id="failed-execution-023", session=result.session, request=request,
        environment_manifest=env_manifest, environment_approval=env_approval,
        integration_manifest=int_manifest, data_flow_plan=plan, fixture=fixture,
        operator_id="session-operator", started_at=NOW + timedelta(minutes=11),
        finished_at=NOW + timedelta(minutes=12), injected_failure_stage=RAGStage.EMBEDDING)
    decision = evaluate_real_data_trial_readiness(env_decision, result.session, evidence,
        receipt, accounting, None, None, roles, evaluation_time=NOW + timedelta(minutes=15))
    assert receipt.result is SessionExecutionResult.FAILED
    assert next(item for item in evidence if item.stage is RAGStage.EMBEDDING).result is StageExecutionResult.FAILED
    assert all(item.result is StageExecutionResult.INCOMPLETE
               for item in evidence[tuple(RAGStage).index(RAGStage.EMBEDDING) + 1:])
    assert decision.state is RealDataTrialReadinessState.INELIGIBLE
    assert accounting.all_zero and decision.real_data_access_count == 0
    assert (chain[0].write_count, chain[0].mutation_count, chain[0].event_count) == (1, 1, 1)
    assert all(value == 0 for name, value in vars(decision).items() if name.endswith("_count"))


@pytest.mark.parametrize("target,attribute,value", (
    ("receipt", "operator_id", "forged-operator"),
    ("role", "session_operator_id", "forged-operator"),
    ("evidence", "output_digest", digest("forged-stage-output")),
))
def test_forged_receipt_role_context_or_stage_evidence_fails_closed(target, attribute, value):
    chain, evidence, accounting, receipt, review, approval, roles, env_decision = reviewed_execution()
    subject = {"receipt": receipt, "role": roles, "evidence": evidence[0]}[target]
    object.__setattr__(subject, attribute, value)
    decision = readiness_for(chain, evidence, accounting, receipt, review, approval,
                             roles, env_decision)
    assert decision.state is RealDataTrialReadinessState.INELIGIBLE
    assert not decision.real_data_approved and not decision.real_data_use_authorized
    assert decision.real_data_access_count == 0


def test_valid_execution_with_forged_review_role_context_fails_closed():
    chain, evidence, accounting, receipt, _, _, roles, env_decision = reviewed_execution()
    wrong_review = SessionExecutionReview("wrong-review", chain[1].session.canonical_digest,
        receipt.canonical_digest, "other-reviewer", NOW + timedelta(minutes=13),
        SessionReviewResult.APPROVED, digest("findings"))
    wrong_approval = SessionExecutionApproval("wrong-approval",
        chain[1].session.canonical_digest, receipt.canonical_digest,
        wrong_review.canonical_digest, "session-approver", NOW + timedelta(minutes=14),
        SessionApprovalResult.APPROVED)
    decision = readiness_for(chain, evidence, accounting, receipt, wrong_review,
                             wrong_approval, roles, env_decision)
    assert decision.state is RealDataTrialReadinessState.INELIGIBLE
    assert "review_approval_invalid" in decision.reason_codes


def test_execution_evidence_and_receipt_have_no_raw_or_connection_surface():
    forbidden = {"raw", "raw_data", "content", "text", "hostname", "ip", "port", "path",
                 "absolute_path", "endpoint", "dsn", "credential", "token", "customer_id",
                 "project_id"}
    for cls in (StageExecutionEvidence, SessionExecutionReceipt):
        names = {item.name for item in fields(cls)}
        assert names.isdisjoint(forbidden)
    assert all(item.name.endswith("_count") or item.name == "canonical_digest"
               for item in fields(ExecutionSideEffectAccounting))
    _, evidence, _, receipt = controlled_execution()
    rendered = repr(evidence) + repr(receipt) + receipt.canonical_json()
    assert "Synthetic Customer" not in rendered
    assert "SYN-PROJECT" not in rendered
