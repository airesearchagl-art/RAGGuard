from dataclasses import fields, replace
from datetime import timedelta

import pytest

from ragguard.local_rag_execution import SessionLifecycle
from ragguard.real_data_trial import *
from ragguard.real_data_trial_approval import *
from ragguard.storage_adapter import digest
from test_local_rag_execution_session_contract import NOW
from test_real_data_trial_approval import approved_trial_chain


def readiness(kwargs, record, security=True, governance=True, approval=True, *, at=None,
              side_effects=None):
    return evaluate_real_data_access_authorization_readiness(
        kwargs["scope"], kwargs["request"],
        kwargs["security_review"] if security else None,
        kwargs["governance_review"] if governance else None,
        kwargs["approval"] if approval else None, record, kwargs["roles"],
        side_effects or TrialSideEffectAccounting(),
        evaluation_time=at or NOW + timedelta(minutes=22))


def test_readiness_progresses_only_through_separate_security_governance_and_approval_gates():
    _, result, kwargs, *_ = approved_trial_chain()
    needs_security = readiness(kwargs, None, security=False, governance=False, approval=False)
    needs_governance = readiness(kwargs, None, governance=False, approval=False)
    needs_approval = readiness(kwargs, None, approval=False)
    needs_record = readiness(kwargs, None)
    eligible = readiness(kwargs, result.record)
    assert needs_security.state is RealDataAccessAuthorizationReadinessState.NEEDS_TRIAL_SECURITY_REVIEW
    assert needs_governance.state is RealDataAccessAuthorizationReadinessState.NEEDS_TRIAL_GOVERNANCE_REVIEW
    assert needs_approval.state is RealDataAccessAuthorizationReadinessState.NEEDS_TRIAL_APPROVAL
    assert needs_record.state is RealDataAccessAuthorizationReadinessState.NEEDS_TRIAL_APPROVAL
    assert eligible.state is (
        RealDataAccessAuthorizationReadinessState.ELIGIBLE_FOR_REAL_DATA_ACCESS_AUTHORIZATION_REVIEW)
    assert not eligible.actual_real_data_access_authorized
    assert not eligible.real_data_use_authorized and not eligible.actual_real_data_read


def test_complete_e2e_keeps_every_external_and_real_data_side_effect_at_zero():
    _, result, kwargs, *_ = approved_trial_chain()
    accounting = TrialSideEffectAccounting()
    decision = readiness(kwargs, result.record, side_effects=accounting)
    assert accounting.all_zero
    assert all(value == 0 for name, value in vars(accounting).items()
               if name.endswith("_count"))
    assert all(value == 0 for name, value in vars(decision).items()
               if name.endswith("_count"))
    assert result.record.actual_real_data_read is False


def test_v023_source_objects_are_revalidated_not_replaced_by_digest_claims():
    _, _, kwargs, *_ = approved_trial_chain()
    assert validate_v023_trial_source_chain(
        kwargs["environment_manifest"], kwargs["environment_approval"],
        kwargs["approved_session"], kwargs["execution_receipt"],
        kwargs["execution_review"], kwargs["execution_approval"],
        kwargs["v0_23_readiness"], evaluation_time=kwargs["approved_at"]) == ()
    forged = replace(kwargs["scope"], environment_approval_digest=digest("forged-claim"))
    request = replace(kwargs["request"], trial_scope_digest=forged.canonical_digest)
    security = replace(kwargs["security_review"], trial_request_digest=request.canonical_digest,
        trial_scope_digest=forged.canonical_digest)
    governance = replace(kwargs["governance_review"],
        trial_request_digest=request.canonical_digest)
    approval = replace(kwargs["approval"], trial_request_digest=request.canonical_digest,
        security_review_digest=security.canonical_digest,
        governance_review_digest=governance.canonical_digest)
    kwargs.update(scope=forged, request=request, security_review=security,
                  governance_review=governance, approval=approval)
    registry = TestOnlyRealDataTrialRegistry()
    denied = registry.approve(**kwargs)
    assert not denied.applied and TrialRegistryReason.INVALID_CHAIN in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 5


@pytest.mark.parametrize("target,change,expected", (
    ("scope", lambda value: replace(value,
        requested_data_class=RealDataClass.CREDENTIAL_LIKE), TrialRegistryReason.POLICY_INVALID),
    ("scope", lambda value: replace(value,
        requested_data_class=RealDataClass.HIGHLY_RESTRICTED), TrialRegistryReason.POLICY_INVALID),
    ("retention_policy", lambda value: replace(value,
        raw_input_retention=TrialRetentionClass.TRANSFORMED_EPHEMERAL_ONLY),
     TrialRegistryReason.POLICY_INVALID),
    ("logging_policy", lambda value: replace(value, raw_content_logging_allowed=True),
     TrialRegistryReason.POLICY_INVALID),
    ("export_policy", lambda value: replace(value, export_allowed=True),
     TrialRegistryReason.POLICY_INVALID),
    ("persistence_policy", lambda value: replace(value, persistent_write_allowed=True),
     TrialRegistryReason.POLICY_INVALID),
))
def test_policy_downgrade_attacks_fail_closed_with_zero_state(target, change, expected):
    _, _, kwargs, *_ = approved_trial_chain()
    kwargs[target] = change(kwargs[target])
    registry = TestOnlyRealDataTrialRegistry()
    denied = registry.approve(**kwargs)
    assert not denied.applied and expected in denied.reasons
    assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 5
    assert TrialSideEffectAccounting().all_zero


@pytest.mark.parametrize("target,attribute,value", (
    ("execution_receipt", "operator_id", "forged-operator"),
    ("v0_23_readiness", "reason_codes", ("forged-readiness",)),
    ("approved_session", "lifecycle", SessionLifecycle.EXPIRED),
    ("environment_approval", "approver_id", "forged-environment-approver"),
))
def test_forged_or_expired_v023_source_chain_is_rejected(target, attribute, value):
    _, _, kwargs, *_ = approved_trial_chain()
    object.__setattr__(kwargs[target], attribute, value)
    registry = TestOnlyRealDataTrialRegistry()
    denied = registry.approve(**kwargs)
    assert not denied.applied and TrialRegistryReason.INVALID_CHAIN in denied.reasons
    assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 5


def test_review_role_context_forgery_fails_even_when_review_digests_are_consistent():
    _, _, kwargs, *_ = approved_trial_chain()
    security = replace(kwargs["security_review"], reviewer_id="trial-requester")
    approval = replace(kwargs["approval"], security_review_digest=security.canonical_digest)
    kwargs.update(security_review=security, approval=approval)
    registry = TestOnlyRealDataTrialRegistry()
    denied = registry.approve(**kwargs)
    assert not denied.applied and TrialRegistryReason.ROLE_CONFLICT in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 5


def test_stale_readiness_and_expired_session_are_denied_before_registry_swap():
    _, _, kwargs, *_ = approved_trial_chain()
    kwargs["approved_at"] = NOW + timedelta(hours=2)
    kwargs["record_expires_at"] = NOW + timedelta(hours=2, minutes=1)
    registry = TestOnlyRealDataTrialRegistry()
    denied = registry.approve(**kwargs)
    assert not denied.applied and TrialRegistryReason.INVALID_CHAIN in denied.reasons
    assert TrialRegistryReason.TEMPORAL_INVALID in denied.reasons
    assert registry.records == ()


def test_trial_public_objects_expose_no_raw_data_or_connection_surface():
    forbidden = {"path", "filename", "raw_document", "raw_content", "customer_name",
                 "person_name", "project_name", "hostname", "endpoint", "credential",
                 "token", "connection_string"}
    contracts = (RealDataTrialScope, TrialApprovalRequest, TrialSecurityReview,
                 TrialDataGovernanceReview, TrialApproval, ApprovedRealDataTrialRecord,
                 RealDataAccessAuthorizationReadinessDecision)
    assert all({item.name for item in fields(contract)}.isdisjoint(forbidden)
               for contract in contracts)
    assert TrialSideEffectAccounting().actual_file_read_count == 0
