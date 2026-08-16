from dataclasses import fields
from datetime import timedelta

import ragguard
import pytest

from ragguard.real_trial_approval import (
    ApprovedOneShotRealDataTrialLifecycle,
    OneShotTrialApprovalReadinessState,
    RealTrialApprovalRegistryReason,
    evaluate_one_shot_trial_approval_readiness,
)
from ragguard.real_trial_root import RealTrialClosureRequirement
from test_real_trial_approval_contract import approval_chain


def test_v028_public_exports_are_available_without_shadowing_v024_reviews():
    expected = (
        "ApprovedOneShotRealDataTrial",
        "RealTrialApprovalRequest",
        "RealTrialApprovalRoleContext",
        "RealTrialApprovalSourceContext",
        "TestOnlyRealTrialApprovalRegistry",
        "OneShotTrialSecurityReview",
        "OneShotTrialDataGovernanceReview",
        "TrialExecutionApproval",
        "RealTrialPurpose",
        "RealTrialRootIdentity",
        "RootProvisioningAttestation",
        "RealTrialClosureRequirement",
    )
    assert all(hasattr(ragguard, name) for name in expected)
    assert ragguard.TrialSecurityReview is not ragguard.OneShotTrialSecurityReview
    assert ragguard.TrialDataGovernanceReview is not (
        ragguard.OneShotTrialDataGovernanceReview
    )


def test_approved_to_execution_pending_to_closed_lifecycle_is_immutable():
    registry, approved, call = approval_chain()
    pending = registry.transition(
        source_record=approved.record,
        new_record_id="one-shot-trial-execution-pending-028",
        lifecycle=ApprovedOneShotRealDataTrialLifecycle.EXECUTION_PENDING,
        transitioned_at=call["approved_at"] + timedelta(minutes=1),
    )
    assert pending.applied
    assert pending.record.predecessor_approval_digest == approved.record.canonical_digest
    assert pending.record.approval_generation == 2
    closed = registry.transition(
        source_record=pending.record,
        new_record_id="one-shot-trial-closed-028",
        lifecycle=ApprovedOneShotRealDataTrialLifecycle.CLOSED,
        transitioned_at=call["approved_at"] + timedelta(minutes=2),
    )
    assert closed.applied
    assert closed.record.predecessor_approval_digest == pending.record.canonical_digest
    assert closed.record.approval_generation == 3
    assert len(registry.records) == 3


@pytest.mark.parametrize(
    "lifecycle",
    (
        ApprovedOneShotRealDataTrialLifecycle.REVOKED,
        ApprovedOneShotRealDataTrialLifecycle.SUPERSEDED,
    ),
)
def test_revoked_and_superseded_records_are_terminal(lifecycle):
    registry, approved, call = approval_chain()
    transitioned = registry.transition(
        source_record=approved.record,
        new_record_id=f"one-shot-trial-{lifecycle.value}-028",
        lifecycle=lifecycle,
        transitioned_at=call["approved_at"] + timedelta(minutes=1),
    )
    assert transitioned.applied
    denied = registry.transition(
        source_record=transitioned.record,
        new_record_id="one-shot-trial-illegal-reactivation-028",
        lifecycle=ApprovedOneShotRealDataTrialLifecycle.EXECUTION_PENDING,
        transitioned_at=call["approved_at"] + timedelta(minutes=2),
    )
    assert not denied.applied
    assert denied.reasons == (RealTrialApprovalRegistryReason.LIFECYCLE_INVALID,)


def test_expired_lifecycle_and_readiness_are_fail_closed():
    registry, approved, call = approval_chain()
    expired = registry.transition(
        source_record=approved.record,
        new_record_id="one-shot-trial-expired-028",
        lifecycle=ApprovedOneShotRealDataTrialLifecycle.EXPIRED,
        transitioned_at=approved.record.expires_at,
    )
    assert expired.applied
    decision = evaluate_one_shot_trial_approval_readiness(
        expired.record, evaluation_time=expired.record.expires_at
    )
    assert decision.state is OneShotTrialApprovalReadinessState.EXPIRED
    assert not decision.eligible_for_explicit_one_shot_execution_review
    assert not decision.actual_read_executed


@pytest.mark.parametrize(
    "lifecycle,expected",
    (
        (
            ApprovedOneShotRealDataTrialLifecycle.REVOKED,
            OneShotTrialApprovalReadinessState.REVOKED,
        ),
        (
            ApprovedOneShotRealDataTrialLifecycle.SUPERSEDED,
            OneShotTrialApprovalReadinessState.SUPERSEDED,
        ),
        (
            ApprovedOneShotRealDataTrialLifecycle.EXECUTION_PENDING,
            OneShotTrialApprovalReadinessState.EXECUTION_PENDING,
        ),
    ),
)
def test_non_approved_lifecycle_is_not_execution_review_eligible(lifecycle, expected):
    registry, approved, call = approval_chain()
    transitioned = registry.transition(
        source_record=approved.record,
        new_record_id=f"readiness-{lifecycle.value}-028",
        lifecycle=lifecycle,
        transitioned_at=call["approved_at"] + timedelta(minutes=1),
    )
    decision = evaluate_one_shot_trial_approval_readiness(
        transitioned.record,
        evaluation_time=call["approved_at"] + timedelta(minutes=2),
    )
    assert decision.state is expected
    assert not decision.eligible_for_explicit_one_shot_execution_review
    assert not decision.real_data_use_authorized


def test_closure_requirement_requires_post_read_evidence_but_grants_no_downstream_use():
    _, _, call = approval_chain(approve=False)
    closure = call["closure_requirement"]
    assert isinstance(closure, RealTrialClosureRequirement)
    assert closure.one_shot_receipt_required
    assert closure.usage_exhaustion_required
    assert closure.classification_evidence_required
    assert closure.masking_evidence_required
    assert closure.post_read_evidence_required
    assert closure.closure_record_required
    assert not closure.downstream_processing_authorized
    assert not closure.embedding_authorized
    assert not closure.persistence_authorized
    assert not closure.export_authorized


def test_record_canonical_digest_contains_every_root_and_approval_binding():
    _, result, call = approval_chain()
    record_fields = {item.name for item in fields(type(result.record))}
    required = {
        "root_provisioning_request_digest",
        "root_identity_digest",
        "root_attestation_digest",
        "target_selection_digest",
        "closure_requirement_digest",
        "security_review_digest",
        "governance_review_digest",
        "execution_approval_digest",
        "access_authorization_record_digest",
        "access_operator_assignment_digest",
        "access_usage_contract_digest",
        "root_descriptor_digest",
        "resolver_policy_digest",
        "controlled_target_reference_digest",
        "operator_id",
        "approval_generation",
        "predecessor_approval_digest",
    }
    assert required <= record_fields
    assert result.record.canonical_digest
    assert result.record.operator_id == call["roles"].operator_id


def test_release_boundary_statements_remain_distinct():
    _, result, call = approval_chain()
    readiness = evaluate_one_shot_trial_approval_readiness(
        result.record, evaluation_time=call["approved_at"] + timedelta(minutes=1)
    )
    assert result.record.lifecycle is ApprovedOneShotRealDataTrialLifecycle.APPROVED
    assert readiness.eligible_for_explicit_one_shot_execution_review
    assert not result.record.actual_read_executed
    assert not readiness.actual_read_executed
    assert not readiness.real_data_use_authorized
    assert not readiness.embedding_authorized
    assert not readiness.persistence_authorized


def test_v028_registry_is_test_only_and_has_no_runtime_activation_surface():
    registry, result, _ = approval_chain()
    assert result.side_effects.all_zero
    assert not hasattr(registry, "activate")
    assert not hasattr(registry, "open")
    assert not hasattr(registry, "read")
    assert not hasattr(registry, "write_production")
