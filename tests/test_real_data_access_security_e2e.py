from dataclasses import fields, replace
from datetime import timedelta

import pytest

from ragguard.local_rag_execution import SessionLifecycle
from ragguard.local_rag_integration import RAGStage
from ragguard.real_data_access import *
from ragguard.real_data_access_authorization import *
from ragguard.real_data_trial import RealDataClass
from ragguard.real_data_trial_approval import TrialLifecycle
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_session_contract import NOW
from test_real_data_access_authorization import authorized_access_chain


def readiness(kwargs, result, *, security=True, governance=True, assignment=True,
              approval=True, record=True, usage=True, at=None, side_effects=None):
    return evaluate_real_data_read_execution_readiness(
        kwargs["selector"], kwargs["access_policy"], kwargs["request"],
        kwargs["security_review"] if security else None,
        kwargs["governance_review"] if governance else None,
        kwargs["operator_assignment"] if assignment else None,
        kwargs["approval"] if approval else None,
        result.record if record else None,
        result.usage_contract if usage else None,
        kwargs["roles"], side_effects or RealDataAccessSideEffectAccounting(),
        evaluation_time=at or NOW + timedelta(minutes=28))


def test_readiness_progresses_through_every_independent_pre_execution_gate():
    _, result, kwargs, _ = authorized_access_chain()
    assert readiness(kwargs, result, security=False, governance=False,
                     assignment=False, approval=False, record=False, usage=False).state is (
        RealDataReadExecutionReadinessState.NEEDS_SECURITY_REVIEW)
    assert readiness(kwargs, result, governance=False, assignment=False,
                     approval=False, record=False, usage=False).state is (
        RealDataReadExecutionReadinessState.NEEDS_GOVERNANCE_REVIEW)
    assert readiness(kwargs, result, assignment=False, approval=False,
                     record=False, usage=False).state is (
        RealDataReadExecutionReadinessState.NEEDS_OPERATOR_ASSIGNMENT)
    assert readiness(kwargs, result, approval=False, record=False, usage=False).state is (
        RealDataReadExecutionReadinessState.NEEDS_ACCESS_APPROVAL)
    assert readiness(kwargs, result, record=False, usage=False).state is (
        RealDataReadExecutionReadinessState.NEEDS_ACCESS_APPROVAL)
    assert readiness(kwargs, result).state is (
        RealDataReadExecutionReadinessState.ELIGIBLE_FOR_LIMITED_REAL_DATA_READ_EXECUTION)


def test_eligible_readiness_is_not_actual_read_use_persistence_or_activation():
    _, result, kwargs, _ = authorized_access_chain()
    decision = readiness(kwargs, result)
    assert not decision.actual_real_data_read_executed
    assert not decision.real_data_use_authorized
    assert not decision.persistence_authorized
    assert not decision.runtime_activation_authorized
    assert not decision.production_active
    with pytest.raises(RealDataAccessAuthorizationError,
                       match="read_execution_readiness_invalid"):
        replace(decision)
    object.__setattr__(decision, "actual_real_data_read_executed", True)
    assert not canonical_object_valid(decision)


def test_complete_security_e2e_keeps_all_side_effect_counts_zero():
    _, result, kwargs, _ = authorized_access_chain()
    accounting = RealDataAccessSideEffectAccounting()
    decision = readiness(kwargs, result, side_effects=accounting)
    assert accounting.all_zero
    assert all(value == 0 for name, value in vars(accounting).items()
               if name.endswith("_count"))
    assert all(value == 0 for name, value in vars(decision).items()
               if name.endswith("_count"))
    assert accounting.actual_file_open_count == accounting.actual_file_read_count == 0
    assert accounting.real_data_access_count == 0


@pytest.mark.parametrize("target,attribute,value", (
    ("approved_trial", "approved_trial_record_id", "forged-approved-trial"),
    ("trial_scope", "trial_scope_id", "forged-trial-scope"),
    ("classification_policy", "policy_version", "forged-classification"),
    ("trial_approval", "approval_id", "forged-trial-approval"),
    ("environment_approval", "approval_id", "forged-environment-approval"),
    ("approved_session", "session_id", "forged-session"),
))
def test_forged_v024_actual_source_objects_fail_closed(target, attribute, value):
    _, _, kwargs, _ = authorized_access_chain()
    object.__setattr__(kwargs[target], attribute, value)
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    denied = registry.authorize(**kwargs)
    assert not denied.applied and RealDataAccessRegistryReason.INVALID_CHAIN in denied.reasons
    assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 6
    assert RealDataAccessSideEffectAccounting().all_zero


@pytest.mark.parametrize("target,change,expected", (
    ("selector", lambda value: replace(value, data_class=RealDataClass.INTERNAL_RESTRICTED),
     RealDataAccessRegistryReason.POLICY_INVALID),
    ("selector", lambda value: replace(value, allowed_stage_ceiling=RAGStage.EMBEDDING),
     RealDataAccessRegistryReason.POLICY_INVALID),
    ("access_policy", lambda value: replace(value, max_documents=2),
     RealDataAccessRegistryReason.POLICY_INVALID),
    ("access_policy", lambda value: replace(value, allowed_read_count=2),
     RealDataAccessRegistryReason.POLICY_INVALID),
    ("access_policy", lambda value: replace(value,
        retention_class=RealDataAccessRetentionClass.RAW_EPHEMERAL),
     RealDataAccessRegistryReason.POLICY_INVALID),
    ("access_policy", lambda value: replace(value,
        logging_class=RealDataAccessLoggingClass.RAW),
     RealDataAccessRegistryReason.POLICY_INVALID),
    ("access_policy", lambda value: replace(value,
        persistence_class=RealDataAccessPersistenceClass.ALLOWED),
     RealDataAccessRegistryReason.POLICY_INVALID),
    ("access_policy", lambda value: replace(value,
        export_class=RealDataAccessExportClass.ALLOWED),
     RealDataAccessRegistryReason.POLICY_INVALID),
    ("access_policy", lambda value: replace(value,
        network_class=RealDataAccessNetworkClass.ALLOWED),
     RealDataAccessRegistryReason.POLICY_INVALID),
))
def test_selector_and_policy_scope_widening_fail_closed(target, change, expected):
    _, _, kwargs, _ = authorized_access_chain()
    kwargs[target] = change(kwargs[target])
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    denied = registry.authorize(**kwargs)
    assert not denied.applied and expected in denied.reasons
    assert registry.records == () and registry.replay_snapshot == (frozenset(),) * 6


@pytest.mark.parametrize("target,attribute,value", (
    ("selector", "selector_id", "forged-selector"),
    ("request", "access_request_id", "forged-request"),
    ("security_review", "review_id", "forged-security-review"),
    ("governance_review", "review_id", "forged-governance-review"),
    ("operator_assignment", "assignment_id", "forged-assignment"),
    ("approval", "approval_id", "forged-access-approval"),
))
def test_forged_v025_chain_objects_fail_closed_without_replay_consumption(
        target, attribute, value):
    _, _, kwargs, _ = authorized_access_chain()
    object.__setattr__(kwargs[target], attribute, value)
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    denied = registry.authorize(**kwargs)
    assert not denied.applied and RealDataAccessRegistryReason.INVALID_CHAIN in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 6


def test_consistent_forged_selector_digest_cannot_replace_actual_trial_scope():
    _, _, kwargs, _ = authorized_access_chain()
    selector = replace(kwargs["selector"],
        approved_trial_digest=digest("forged-approved-trial"))
    request = replace(kwargs["request"], selector_digest=selector.canonical_digest)
    security = replace(kwargs["security_review"],
        access_request_digest=request.canonical_digest,
        selector_digest=selector.canonical_digest)
    governance = replace(kwargs["governance_review"],
        access_request_digest=request.canonical_digest)
    assignment = replace(kwargs["operator_assignment"],
        access_request_digest=request.canonical_digest,
        operator_scope_digest=selector.canonical_digest)
    approval = replace(kwargs["approval"],
        access_request_digest=request.canonical_digest,
        security_review_digest=security.canonical_digest,
        governance_review_digest=governance.canonical_digest,
        operator_assignment_digest=assignment.canonical_digest)
    kwargs.update(selector=selector, request=request, security_review=security,
                  governance_review=governance, operator_assignment=assignment,
                  approval=approval)
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    denied = registry.authorize(**kwargs)
    assert not denied.applied and RealDataAccessRegistryReason.POLICY_INVALID in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 6


def test_operator_mismatch_and_operator_approver_conflict_fail_closed():
    _, _, kwargs, _ = authorized_access_chain()
    assignment = replace(kwargs["operator_assignment"], operator_id="other-operator")
    approval = replace(kwargs["approval"],
                       operator_assignment_digest=assignment.canonical_digest)
    kwargs.update(operator_assignment=assignment, approval=approval)
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    denied = registry.authorize(**kwargs)
    assert not denied.applied and RealDataAccessRegistryReason.ROLE_CONFLICT in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 6
    with pytest.raises(RealDataAccessAuthorizationError, match="access_role_conflict"):
        replace(kwargs["roles"], real_data_operator_id=kwargs["roles"].access_approver_id)


def test_forged_role_context_fails_even_when_chain_digests_are_consistent():
    _, _, kwargs, _ = authorized_access_chain()
    security = replace(kwargs["security_review"], reviewer_id="access-requester")
    approval = replace(kwargs["approval"], security_review_digest=security.canonical_digest)
    kwargs.update(security_review=security, approval=approval)
    registry = TestOnlyRealDataAccessAuthorizationRegistry()
    denied = registry.authorize(**kwargs)
    assert not denied.applied and RealDataAccessRegistryReason.ROLE_CONFLICT in denied.reasons


@pytest.mark.parametrize("case", ("assignment", "trial", "authorization"))
def test_stale_or_expired_chain_is_ineligible_and_has_zero_effects(case):
    _, result, kwargs, _ = authorized_access_chain()
    if case == "assignment":
        decision = readiness(kwargs, result, at=kwargs["operator_assignment"].expires_at)
    elif case == "trial":
        object.__setattr__(kwargs["approved_trial"], "lifecycle", TrialLifecycle.EXPIRED)
        registry = TestOnlyRealDataAccessAuthorizationRegistry()
        denied = registry.authorize(**kwargs)
        assert not denied.applied
        return
    else:
        decision = readiness(kwargs, result, at=result.record.expires_at)
    assert decision.state is RealDataReadExecutionReadinessState.INELIGIBLE
    assert not decision.actual_real_data_read_executed
    assert decision.actual_file_open_count == decision.actual_file_read_count == 0


def test_nonzero_side_effect_input_is_ineligible_without_copying_nonzero_counts():
    _, result, kwargs, _ = authorized_access_chain()
    decision = readiness(
        kwargs, result,
        side_effects=RealDataAccessSideEffectAccounting(actual_file_open_count=1))
    assert decision.state is RealDataReadExecutionReadinessState.INELIGIBLE
    assert decision.actual_file_open_count == decision.actual_file_read_count == 0
    assert decision.real_data_access_count == 0


def test_terminal_authorization_lifecycle_never_falls_back_to_eligible():
    registry, result, kwargs, _ = authorized_access_chain()
    transitioned = registry.transition(
        source_record=result.record, new_record_id="authorization-revoked-e2e",
        lifecycle=RealDataAccessAuthorizationLifecycle.REVOKED,
        transitioned_at=NOW + timedelta(minutes=28))
    fake_result = replace(result, record=transitioned.record, usage_contract=None)
    decision = readiness(kwargs, fake_result, usage=False)
    assert decision.state is RealDataReadExecutionReadinessState.INELIGIBLE
    assert not decision.actual_real_data_read_executed


def test_public_contracts_expose_no_location_content_or_execution_surface():
    contracts = (
        RealDataAccessSelector, RealDataAccessPolicy, RealDataAccessRequest,
        RealDataAccessSecurityReview, RealDataAccessGovernanceReview,
        RealDataOperatorAssignment, RealDataAccessApproval,
        RealDataAccessAuthorizationRecord, RealDataReadExecutionReadinessDecision,
    )
    forbidden_fields = {
        "path", "filename", "directory", "raw_document", "raw_content",
        "customer_name", "company_name", "person_name", "project_name",
        "hostname", "credential", "token", "connection_string",
    }
    assert all({item.name for item in fields(contract)}.isdisjoint(forbidden_fields)
               for contract in contracts)
    forbidden_methods = {
        "open_real_file", "read_real_document", "execute_real_data_read",
        "consume_real_data", "scan_real_data_directory", "load_customer_data",
    }
    assert all(not hasattr(contract, name)
               for contract in contracts for name in forbidden_methods)
    assert RealDataAccessSideEffectAccounting().all_zero
