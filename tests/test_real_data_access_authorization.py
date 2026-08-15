from dataclasses import fields, replace
from datetime import timedelta

import pytest

from ragguard.real_data_access import *
from ragguard.real_data_access_authorization import *
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_session_contract import NOW
from test_real_data_access_contract import PURPOSE, access_selector_policy


def authorized_access_chain(*, fault=RealDataAccessRegistryFault.NONE):
    selector, policy, approved_trial, trial_kwargs = access_selector_policy()
    request = RealDataAccessRequest(
        "access-request-025", approved_trial.canonical_digest,
        selector.canonical_digest, policy.canonical_digest,
        trial_kwargs["approved_session"].canonical_digest,
        trial_kwargs["environment_approval"].canonical_digest,
        "access-requester", NOW + timedelta(minutes=22),
        NOW + timedelta(minutes=85), PURPOSE)
    security_review = RealDataAccessSecurityReview(
        "access-security-review-025", request.canonical_digest,
        selector.canonical_digest, policy.canonical_digest,
        approved_trial.canonical_digest, NOW + timedelta(minutes=23),
        "access-security-reviewer", RealDataAccessReviewResult.APPROVED,
        digest("access-security-findings"))
    governance_review = RealDataAccessGovernanceReview(
        "access-governance-review-025", request.canonical_digest,
        approved_trial.canonical_digest,
        trial_kwargs["classification_policy"].canonical_digest,
        policy.retention_policy_digest, policy.logging_policy_digest,
        policy.persistence_policy_digest, NOW + timedelta(minutes=24),
        "access-governance-reviewer", RealDataAccessReviewResult.APPROVED,
        digest("access-governance-findings"))
    assignment = RealDataOperatorAssignment(
        "operator-assignment-025", request.canonical_digest, "real-data-operator",
        NOW + timedelta(minutes=25), NOW + timedelta(minutes=82),
        selector.canonical_digest)
    approval = RealDataAccessApproval(
        "access-approval-025", request.canonical_digest,
        security_review.canonical_digest, governance_review.canonical_digest,
        assignment.canonical_digest, "access-approver",
        NOW + timedelta(minutes=26), NOW + timedelta(minutes=81),
        RealDataAccessApprovalResult.APPROVED)
    roles = RealDataAccessRoleContext(
        trial_kwargs["request"].requested_by, trial_kwargs["approval"].approver_id,
        trial_kwargs["approved_session"].operator_id, request.requested_by,
        security_review.reviewer_id, governance_review.reviewer_id,
        assignment.operator_id, approval.approver_id)
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    kwargs = dict(
        authorization_record_id="authorization-record-025", selector=selector,
        access_policy=policy, request=request, security_review=security_review,
        governance_review=governance_review, operator_assignment=assignment,
        approval=approval, roles=roles, approved_trial=approved_trial,
        trial_scope=trial_kwargs["scope"],
        classification_policy=trial_kwargs["classification_policy"],
        stage_policy=trial_kwargs["stage_policy"],
        retention_policy=trial_kwargs["retention_policy"],
        logging_policy=trial_kwargs["logging_policy"],
        cache_policy=trial_kwargs["cache_policy"],
        export_policy=trial_kwargs["export_policy"],
        persistence_policy=trial_kwargs["persistence_policy"],
        trial_request=trial_kwargs["request"],
        trial_security_review=trial_kwargs["security_review"],
        trial_governance_review=trial_kwargs["governance_review"],
        trial_approval=trial_kwargs["approval"],
        environment_approval=trial_kwargs["environment_approval"],
        approved_session=trial_kwargs["approved_session"],
        authorization_generation=1, predecessor_authorization_digest=None,
        issued_at=NOW + timedelta(minutes=27),
        record_expires_at=NOW + timedelta(minutes=80), fault=fault)
    result = registry.authorize(**kwargs)
    return registry, result, kwargs, trial_kwargs


def test_complete_chain_issues_metadata_only_authorization_record_and_usage_contract():
    registry, result, kwargs, _ = authorized_access_chain()
    assert result.applied and result.record is not None and result.usage_contract is not None
    record = result.record
    usage = result.usage_contract
    assert canonical_object_valid(record) and canonical_object_valid(usage)
    assert record.access_request_digest == kwargs["request"].canonical_digest
    assert record.selector_digest == kwargs["selector"].canonical_digest
    assert record.policy_digest == kwargs["access_policy"].canonical_digest
    assert record.approved_trial_record_digest == kwargs["approved_trial"].canonical_digest
    assert record.operator_id == kwargs["operator_assignment"].operator_id
    assert record.state is (
        RealDataAccessAuthorizationState.AUTHORIZED_FOR_LIMITED_READ_EXECUTION_REVIEW)
    assert record.lifecycle is RealDataAccessAuthorizationLifecycle.AUTHORIZED
    assert record.allowed_read_count == record.remaining_read_count == 1
    assert usage.authorization_record_digest == record.canonical_digest
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (1, 1, 1)


def test_record_cannot_be_minted_or_reissued_through_public_constructor_or_replace():
    _, result, *_ = authorized_access_chain()
    with pytest.raises(RealDataAccessAuthorizationError,
                       match="authorization_record_invalid"):
        replace(result.record)
    with pytest.raises(RealDataAccessAuthorizationError,
                       match="authorization_record_invalid"):
        RealDataAccessAuthorizationRecord(
            "forged-record", *(digest("forged") for _ in range(8)), "operator", 1,
            None, 1, 1, NOW, NOW + timedelta(minutes=1))


def test_v024_source_chain_is_revalidated_from_actual_objects():
    _, _, kwargs, _ = authorized_access_chain()
    assert validate_v024_access_source_chain(
        kwargs["approved_trial"], kwargs["trial_scope"],
        kwargs["classification_policy"], kwargs["stage_policy"],
        kwargs["retention_policy"], kwargs["logging_policy"],
        kwargs["cache_policy"], kwargs["export_policy"],
        kwargs["persistence_policy"], kwargs["trial_request"],
        kwargs["trial_security_review"], kwargs["trial_governance_review"],
        kwargs["trial_approval"], kwargs["environment_approval"],
        kwargs["approved_session"], evaluation_time=kwargs["issued_at"]) == ()


def test_request_reviews_assignment_and_approval_are_distinct_metadata_contracts():
    _, _, kwargs, _ = authorized_access_chain()
    contracts = (
        RealDataAccessRequest, RealDataAccessSecurityReview,
        RealDataAccessGovernanceReview, RealDataOperatorAssignment,
        RealDataAccessApproval, RealDataAccessAuthorizationRecord,
        AuthorizationUsageCounterContract,
    )
    forbidden = {
        "path", "filename", "directory", "raw", "content", "customer",
        "project", "person", "hostname", "endpoint", "credential", "token",
    }
    assert all({item.name for item in fields(contract)}.isdisjoint(forbidden)
               for contract in contracts)
    assert kwargs["operator_assignment"].access_authorized is False
    assert type(kwargs["security_review"]) is not type(kwargs["governance_review"])


@pytest.mark.parametrize("missing", (
    "security_review", "governance_review", "operator_assignment", "approval",
))
def test_missing_review_assignment_or_approval_leaves_state_and_replay_unchanged(missing):
    _, _, kwargs, _ = authorized_access_chain()
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    kwargs[missing] = None
    denied = registry.authorize(**kwargs)
    assert not denied.applied
    assert RealDataAccessRegistryReason.INVALID_CHAIN in denied.reasons
    assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 6
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (0, 0, 0)


@pytest.mark.parametrize("target", (
    "security_review", "governance_review", "approval",
))
def test_rejected_reviews_and_approval_fail_closed(target):
    _, _, kwargs, _ = authorized_access_chain()
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    if target == "approval":
        kwargs[target] = replace(kwargs[target], result=RealDataAccessApprovalResult.REJECTED)
    else:
        kwargs[target] = replace(kwargs[target], result=RealDataAccessReviewResult.REJECTED)
    denied = registry.authorize(**kwargs)
    assert not denied.applied and RealDataAccessRegistryReason.INVALID_CHAIN in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 6


def test_successful_only_replay_consumption_covers_all_six_objects():
    registry, result, kwargs, _ = authorized_access_chain()
    assert registry.replay_snapshot == (
        frozenset({kwargs["request"].canonical_digest}),
        frozenset({kwargs["security_review"].canonical_digest}),
        frozenset({kwargs["governance_review"].canonical_digest}),
        frozenset({kwargs["operator_assignment"].canonical_digest}),
        frozenset({kwargs["approval"].canonical_digest}),
        frozenset({result.record.canonical_digest}),
    )
    replay = registry.authorize(**{
        **kwargs, "authorization_record_id": "duplicate-authorization-025",
        "authorization_generation": 2,
        "predecessor_authorization_digest": result.record.canonical_digest,
    })
    assert not replay.applied and RealDataAccessRegistryReason.REPLAY in replay.reasons
    assert len(registry.records) == 1


@pytest.mark.parametrize("mutation,reason", (
    ("generation", RealDataAccessRegistryReason.GENERATION_MISMATCH),
    ("predecessor", RealDataAccessRegistryReason.PREDECESSOR_MISMATCH),
))
def test_generation_rollback_and_predecessor_mismatch_are_rejected(mutation, reason):
    _, _, kwargs, _ = authorized_access_chain()
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    if mutation == "generation":
        kwargs["authorization_generation"] = 0
    else:
        kwargs["predecessor_authorization_digest"] = digest("wrong-predecessor")
    denied = registry.authorize(**kwargs)
    assert not denied.applied and reason in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 6


@pytest.mark.parametrize("fault", (
    RealDataAccessRegistryFault.CANDIDATE_STATE,
    RealDataAccessRegistryFault.BEFORE_SWAP,
))
def test_injected_registry_fault_is_atomic_retryable_and_consumes_nothing(fault):
    registry, failed, kwargs, _ = authorized_access_chain(fault=fault)
    assert not failed.applied and failed.reasons == (RealDataAccessRegistryReason.COMMIT_FAULT,)
    assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 6
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (0, 0, 0)
    kwargs["fault"] = RealDataAccessRegistryFault.NONE
    retried = registry.authorize(**kwargs)
    assert retried.applied and len(registry.records) == 1


@pytest.mark.parametrize("lifecycle", (
    RealDataAccessAuthorizationLifecycle.REVOKED,
    RealDataAccessAuthorizationLifecycle.SUPERSEDED,
))
def test_revoked_and_superseded_authorizations_are_terminal(lifecycle):
    registry, result, *_ = authorized_access_chain()
    transitioned = registry.transition(
        source_record=result.record, new_record_id=f"authorization-{lifecycle.value}",
        lifecycle=lifecycle, transitioned_at=NOW + timedelta(minutes=28))
    assert transitioned.applied and transitioned.record.lifecycle is lifecycle
    again = registry.transition(
        source_record=transitioned.record, new_record_id="automatic-reactivation",
        lifecycle=RealDataAccessAuthorizationLifecycle.REVOKED,
        transitioned_at=NOW + timedelta(minutes=29))
    assert not again.applied


def test_expired_authorization_is_terminal_and_cannot_be_reused():
    registry, result, *_ = authorized_access_chain()
    transitioned = registry.transition(
        source_record=result.record, new_record_id="authorization-expired",
        lifecycle=RealDataAccessAuthorizationLifecycle.EXPIRED,
        transitioned_at=result.record.expires_at)
    assert transitioned.applied
    assert transitioned.record.lifecycle is RealDataAccessAuthorizationLifecycle.EXPIRED


def test_exhaustion_cannot_be_claimed_by_arbitrary_transition_or_counter_reset():
    registry, result, *_ = authorized_access_chain()
    denied = registry.transition(
        source_record=result.record, new_record_id="authorization-exhausted",
        lifecycle=RealDataAccessAuthorizationLifecycle.EXHAUSTED,
        transitioned_at=NOW + timedelta(minutes=28))
    assert not denied.applied
    usage = result.usage_contract
    assert not hasattr(usage, "decrement") and not hasattr(usage, "reset")
    with pytest.raises(RealDataAccessAuthorizationError,
                       match="usage_counter_contract_invalid"):
        replace(usage, remaining_read_count=-1)


def test_temporal_contract_rejects_stale_assignment_expired_trial_and_future_metadata():
    _, _, kwargs, _ = authorized_access_chain()
    cases = []
    stale = dict(kwargs)
    stale["operator_assignment"] = replace(
        kwargs["operator_assignment"], expires_at=NOW + timedelta(minutes=26))
    stale["approval"] = replace(
        kwargs["approval"],
        operator_assignment_digest=stale["operator_assignment"].canonical_digest)
    cases.append(stale)
    expired = dict(kwargs)
    object.__setattr__(expired["approved_trial"], "expires_at", kwargs["issued_at"])
    cases.append(expired)
    for case in cases:
        registry = TestOnlyRealDataAccessAuthorizationRegistry()
        denied = registry.authorize(**case)
        assert not denied.applied
        assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 6
    with pytest.raises(RealDataAccessAuthorizationError, match="access_request_invalid"):
        replace(kwargs["request"], requested_at=kwargs["request"].requested_at.replace(tzinfo=None))


def test_roles_are_pairwise_distinct_and_self_approval_is_impossible():
    with pytest.raises(RealDataAccessAuthorizationError, match="access_role_conflict"):
        RealDataAccessRoleContext(
            "trial-requester", "trial-approver", "session-operator",
            "access-requester", "security-reviewer", "governance-reviewer",
            "real-data-operator", "access-requester")
    with pytest.raises(RealDataAccessAuthorizationError, match="access_role_conflict"):
        RealDataAccessRoleContext(
            "trial-requester", "same", "session-operator", "access-requester",
            "security-reviewer", "governance-reviewer", "real-data-operator", "same")


def test_record_is_read_authorization_review_only_not_execution_write_or_activation():
    _, result, *_ = authorized_access_chain()
    assert not result.record.actual_real_data_read_executed
    assert not result.record.persistence_authorized
    assert not result.record.runtime_activation_authorized
    assert not hasattr(result.record, "real_data_read_executed")
    assert not hasattr(result.record, "active")
    assert not hasattr(result.record, "production_authorized")
    assert result.record.remaining_read_count == result.record.allowed_read_count == 1
