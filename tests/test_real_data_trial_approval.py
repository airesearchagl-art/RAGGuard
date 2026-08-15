from dataclasses import fields, replace
from datetime import timedelta

import pytest

from ragguard.real_data_trial import *
from ragguard.real_data_trial_approval import *
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_security_e2e import readiness_for, reviewed_execution
from test_local_rag_execution_session_contract import NOW
from test_real_data_trial_contract import safe_trial_policies


def approved_trial_chain(*, fault=TrialRegistryFault.NONE):
    chain, evidence, accounting, execution_receipt, execution_review, \
        execution_approval, _, environment_decision = reviewed_execution()
    _, session_result, _, _, environment_manifest, _, _, _, environment_approval, *_ = chain
    session = session_result.session
    v023_readiness = readiness_for(chain, evidence, accounting, execution_receipt,
        execution_review, execution_approval, chain[3], environment_decision)
    classification, stages, retention, logging, cache, export, persistence = safe_trial_policies()
    scope = RealDataTrialScope("trial-scope-024", session.canonical_digest,
        environment_manifest.canonical_digest, environment_approval.canonical_digest,
        execution_receipt.integration_manifest_digest, execution_receipt.canonical_digest,
        classification.canonical_digest, stages.canonical_digest, retention.canonical_digest,
        logging.canonical_digest, cache.canonical_digest, export.canonical_digest,
        persistence.canonical_digest, RealDataClass.INTERNAL_LOW, stages.max_stage,
        TrialRetentionClass.NONE, TrialLoggingClass.DIGEST_AND_REASON_ONLY,
        TrialCacheClass.NONE, TrialExportClass.PROHIBITED, TrialPersistenceClass.NONE,
        NOW + timedelta(minutes=16), NOW + timedelta(hours=2))
    request = TrialApprovalRequest("trial-request-024", scope.canonical_digest,
        v023_readiness.canonical_digest, session.canonical_digest,
        environment_approval.canonical_digest, "trial-requester",
        NOW + timedelta(minutes=17), NOW + timedelta(minutes=110))
    security_review = TrialSecurityReview("trial-security-review-024",
        request.canonical_digest, scope.canonical_digest, v023_readiness.canonical_digest,
        NOW + timedelta(minutes=18), "trial-security-reviewer", TrialReviewResult.APPROVED,
        digest("trial-security-findings"))
    governance_review = TrialDataGovernanceReview("trial-governance-review-024",
        request.canonical_digest, classification.canonical_digest,
        retention.canonical_digest, logging.canonical_digest, persistence.canonical_digest,
        NOW + timedelta(minutes=19), "trial-governance-reviewer",
        TrialReviewResult.APPROVED, digest("trial-governance-findings"))
    approval = TrialApproval("trial-approval-024", request.canonical_digest,
        security_review.canonical_digest, governance_review.canonical_digest,
        "trial-approver", NOW + timedelta(minutes=20), NOW + timedelta(minutes=100),
        TrialApprovalResult.APPROVED)
    roles = TrialRoleContext("trial-requester", session.operator_id,
        environment_approval.approver_id, "trial-security-reviewer",
        "trial-governance-reviewer", "trial-approver")
    registry = TestOnlyRealDataTrialRegistry()
    kwargs = dict(approved_trial_record_id="approved-trial-024", scope=scope,
        classification_policy=classification, stage_policy=stages,
        retention_policy=retention, logging_policy=logging, cache_policy=cache,
        export_policy=export, persistence_policy=persistence, request=request,
        security_review=security_review, governance_review=governance_review,
        approval=approval, roles=roles, environment_manifest=environment_manifest,
        environment_approval=environment_approval, approved_session=session,
        execution_receipt=execution_receipt, execution_review=execution_review,
        execution_approval=execution_approval, v0_23_readiness=v023_readiness,
        trial_generation=1, predecessor_trial_digest=None,
        approved_at=NOW + timedelta(minutes=21),
        record_expires_at=NOW + timedelta(minutes=90), fault=fault)
    result = registry.approve(**kwargs)
    return registry, result, kwargs, chain, evidence, accounting


def test_complete_object_backed_chain_creates_metadata_only_approved_record():
    registry, result, kwargs, *_ = approved_trial_chain()
    assert result.applied and result.record is not None
    record = result.record
    assert canonical_object_valid(record)
    assert record.trial_scope_digest == kwargs["scope"].canonical_digest
    assert record.trial_request_digest == kwargs["request"].canonical_digest
    assert record.security_review_digest == kwargs["security_review"].canonical_digest
    assert record.governance_review_digest == kwargs["governance_review"].canonical_digest
    assert record.approval_digest == kwargs["approval"].canonical_digest
    assert record.state is ApprovedTrialState.APPROVED_FOR_REAL_DATA_ACCESS_AUTHORIZATION_REVIEW
    assert not record.actual_real_data_read
    assert not hasattr(record, "real_data_access_authorized")
    assert not hasattr(record, "active") and not hasattr(record, "production_ready")
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (1, 1, 1)
    with pytest.raises(RealDataTrialApprovalError, match="approved_trial_record_invalid"):
        replace(record)


def test_successful_only_replay_consumption_binds_all_five_objects():
    registry, result, kwargs, *_ = approved_trial_chain()
    assert registry.replay_snapshot == (
        frozenset({kwargs["request"].canonical_digest}),
        frozenset({kwargs["security_review"].canonical_digest}),
        frozenset({kwargs["governance_review"].canonical_digest}),
        frozenset({kwargs["approval"].canonical_digest}),
        frozenset({result.record.canonical_digest}),
    )
    replay = registry.approve(**{**kwargs, "approved_trial_record_id": "duplicate-trial-024",
        "trial_generation": 2, "predecessor_trial_digest": result.record.canonical_digest})
    assert not replay.applied and TrialRegistryReason.REPLAY in replay.reasons
    assert len(registry.records) == 1


def test_request_reviews_and_approval_are_metadata_only_and_distinct():
    _, _, kwargs, *_ = approved_trial_chain()
    contracts = (TrialApprovalRequest, TrialSecurityReview,
                 TrialDataGovernanceReview, TrialApproval, ApprovedRealDataTrialRecord)
    forbidden = {"path", "filename", "raw", "content", "customer", "person", "project",
                 "hostname", "endpoint", "credential", "token", "connection_string"}
    assert all({item.name for item in fields(contract)}.isdisjoint(forbidden)
               for contract in contracts)
    assert type(kwargs["security_review"]) is not type(kwargs["governance_review"])
    assert kwargs["approval"].real_data_access_authorized is False


@pytest.mark.parametrize("missing", ("security_review", "governance_review", "approval"))
def test_missing_review_or_approval_leaves_registry_and_replay_unchanged(missing):
    _, _, kwargs, *_ = approved_trial_chain()
    registry = TestOnlyRealDataTrialRegistry()
    kwargs[missing] = None
    denied = registry.approve(**kwargs)
    assert not denied.applied and TrialRegistryReason.INVALID_CHAIN in denied.reasons
    assert registry.records == ()
    assert registry.replay_snapshot == (frozenset(),) * 5
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (0, 0, 0)


@pytest.mark.parametrize("target", ("security_review", "governance_review", "approval"))
def test_rejected_review_or_approval_fails_closed(target):
    _, _, kwargs, *_ = approved_trial_chain()
    registry = TestOnlyRealDataTrialRegistry()
    if target == "approval":
        kwargs[target] = replace(kwargs[target], result=TrialApprovalResult.REJECTED)
    else:
        kwargs[target] = replace(kwargs[target], result=TrialReviewResult.REJECTED)
    denied = registry.approve(**kwargs)
    assert not denied.applied and TrialRegistryReason.INVALID_CHAIN in denied.reasons
    assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 5


@pytest.mark.parametrize("target,attribute,value", (
    ("scope", "trial_scope_id", "forged-trial-scope"),
    ("approved_session", "session_id", "forged-session"),
    ("environment_approval", "approval_id", "forged-environment-approval"),
    ("v0_23_readiness", "reason_codes", ("forged-readiness",)),
    ("security_review", "review_id", "forged-security-review"),
    ("governance_review", "review_id", "forged-governance-review"),
    ("approval", "approval_id", "forged-trial-approval"),
))
def test_post_construction_forgery_is_rejected_without_consumption(target, attribute, value):
    _, _, kwargs, *_ = approved_trial_chain()
    registry = TestOnlyRealDataTrialRegistry()
    object.__setattr__(kwargs[target], attribute, value)
    denied = registry.approve(**kwargs)
    assert not denied.applied and TrialRegistryReason.INVALID_CHAIN in denied.reasons
    assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 5


@pytest.mark.parametrize("mutation,reason", (
    ("generation", TrialRegistryReason.GENERATION_MISMATCH),
    ("predecessor", TrialRegistryReason.PREDECESSOR_MISMATCH),
))
def test_generation_rollback_and_predecessor_mismatch_fail_closed(mutation, reason):
    _, _, kwargs, *_ = approved_trial_chain()
    registry = TestOnlyRealDataTrialRegistry()
    if mutation == "generation":
        kwargs["trial_generation"] = 0
    else:
        kwargs["predecessor_trial_digest"] = digest("wrong-predecessor")
    denied = registry.approve(**kwargs)
    assert not denied.applied and reason in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 5


@pytest.mark.parametrize("fault", (
    TrialRegistryFault.CANDIDATE_STATE, TrialRegistryFault.BEFORE_SWAP,
))
def test_injected_fault_is_atomic_and_retryable(fault):
    registry, failed, kwargs, *_ = approved_trial_chain(fault=fault)
    assert not failed.applied and failed.reasons == (TrialRegistryReason.COMMIT_FAULT,)
    assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 5
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (0, 0, 0)
    kwargs["fault"] = TrialRegistryFault.NONE
    retried = registry.approve(**kwargs)
    assert retried.applied and len(registry.records) == 1


@pytest.mark.parametrize("lifecycle", (
    TrialLifecycle.EXPIRED, TrialLifecycle.REVOKED, TrialLifecycle.SUPERSEDED,
))
def test_terminal_trial_lifecycle_cannot_be_used_for_access_readiness(lifecycle):
    registry, result, kwargs, *_ = approved_trial_chain()
    transitioned = registry.transition(source_record=result.record,
        new_record_id=f"trial-{lifecycle.value}", lifecycle=lifecycle,
        transitioned_at=NOW + timedelta(minutes=22))
    assert transitioned.applied and transitioned.record.lifecycle is lifecycle
    decision = evaluate_real_data_access_authorization_readiness(
        kwargs["scope"], kwargs["request"], kwargs["security_review"],
        kwargs["governance_review"], kwargs["approval"], transitioned.record,
        kwargs["roles"], TrialSideEffectAccounting(),
        evaluation_time=NOW + timedelta(minutes=23))
    assert decision.state is RealDataAccessAuthorizationReadinessState.INELIGIBLE
    assert not decision.actual_real_data_access_authorized and not decision.actual_real_data_read


def test_expired_trial_and_nonzero_side_effects_are_ineligible():
    _, result, kwargs, *_ = approved_trial_chain()
    expired = evaluate_real_data_access_authorization_readiness(
        kwargs["scope"], kwargs["request"], kwargs["security_review"],
        kwargs["governance_review"], kwargs["approval"], result.record,
        kwargs["roles"], TrialSideEffectAccounting(),
        evaluation_time=result.record.expires_at)
    nonzero = evaluate_real_data_access_authorization_readiness(
        kwargs["scope"], kwargs["request"], kwargs["security_review"],
        kwargs["governance_review"], kwargs["approval"], result.record,
        kwargs["roles"], TrialSideEffectAccounting(real_data_access_count=1),
        evaluation_time=NOW + timedelta(minutes=22))
    assert expired.state is nonzero.state is RealDataAccessAuthorizationReadinessState.INELIGIBLE
    assert expired.real_data_access_count == nonzero.real_data_access_count == 0


def test_roles_require_independent_requester_operator_reviewers_and_approver():
    with pytest.raises(RealDataTrialApprovalError, match="trial_role_conflict"):
        TrialRoleContext("same", "session-operator", "environment-approver", "same",
            "governance-reviewer", "trial-approver")
    with pytest.raises(RealDataTrialApprovalError, match="trial_role_conflict"):
        TrialRoleContext("requester", "session-operator", "same", "security-reviewer",
            "governance-reviewer", "same")


def test_non_utc_and_stale_metadata_are_rejected():
    _, _, kwargs, *_ = approved_trial_chain()
    registry = TestOnlyRealDataTrialRegistry()
    kwargs["approved_at"] = NOW + timedelta(hours=2)
    denied = registry.approve(**kwargs)
    assert not denied.applied and TrialRegistryReason.TEMPORAL_INVALID in denied.reasons
    with pytest.raises(RealDataTrialApprovalError, match="trial_request_invalid"):
        replace(kwargs["request"], requested_at=kwargs["request"].requested_at.replace(tzinfo=None))
