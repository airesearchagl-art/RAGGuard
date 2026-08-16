from dataclasses import fields, replace
from datetime import timedelta

import pytest

from ragguard.local_rag_integration import RAGStage
from ragguard.real_data_access import RealDataByteClass
from ragguard.real_target_resolver import (
    ControlledTargetReference,
    RealTargetResolverPolicy,
    TrialRootClass,
    TrialRootDescriptor,
)
from ragguard.real_trial_approval import (
    ApprovedOneShotRealDataTrial,
    ApprovedOneShotRealDataTrialLifecycle,
    ApprovedOneShotRealDataTrialState,
    OneShotTrialApprovalReadinessState,
    RealTrialApprovalError,
    RealTrialApprovalRegistryFault,
    RealTrialApprovalRegistryReason,
    RealTrialApprovalRequest,
    RealTrialApprovalRoleContext,
    RealTrialApprovalSourceContext,
    TestOnlyRealTrialApprovalRegistry,
    TrialAuthorizationReviewResult,
    TrialDataGovernanceReview,
    TrialExecutionApproval,
    TrialExecutionApprovalResult,
    TrialSecurityReview,
    evaluate_one_shot_trial_approval_readiness,
    validate_real_trial_approval_source,
)
from ragguard.real_trial_root import (
    LinkReparseVerificationResult,
    NetworkIsolationVerificationResult,
    PermissionVerificationResult,
    RealTrialClosureRequirement,
    RealTrialPurpose,
    RealTrialPurposeClass,
    RealTrialRootIdentity,
    RealTrialRootProvisioningRequest,
    RealTrialTargetSelection,
    RootConfinementVerificationResult,
    RootProvisioningAttestation,
    RootProvisioningAttestationState,
    RootProvisioningVerificationState,
    WriteProhibitionVerificationResult,
)
from ragguard.real_data_access import RealDataAccessRetentionClass
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_session_contract import NOW
from test_real_data_read_execution_contract import read_execution_chain


RESULT_TYPES = (
    RootConfinementVerificationResult,
    LinkReparseVerificationResult,
    PermissionVerificationResult,
    WriteProhibitionVerificationResult,
    NetworkIsolationVerificationResult,
)


def approval_chain(
    *,
    registry: TestOnlyRealTrialApprovalRegistry | None = None,
    approve: bool = True,
    fault: RealTrialApprovalRegistryFault = RealTrialApprovalRegistryFault.NONE,
):
    _, _, v026_call, _ = read_execution_chain(execute=False)
    access = v026_call["context"]
    target = v026_call["target"]
    root_opaque_digest = digest("controlled-root-identity-v028")
    resolver_policy = RealTargetResolverPolicy(
        root_opaque_digest, (".txt",), RealDataByteClass.SMALL_DOCUMENT
    )
    root_descriptor = TrialRootDescriptor(
        "controlled-trial-root-028",
        TrialRootClass.CONTROLLED_TRIAL_ROOT,
        root_opaque_digest,
        resolver_policy.canonical_digest,
        NOW + timedelta(minutes=28),
    )
    target_reference = ControlledTargetReference(
        "controlled-target-reference-028",
        root_descriptor.canonical_digest,
        digest("opaque-relative-target-v028"),
        target.document_class,
        target.content_identity_digest,
    )
    source_context = RealTrialApprovalSourceContext(
        access, root_descriptor, resolver_policy, target_reference
    )
    purpose = RealTrialPurpose(
        "real-trial-purpose-028",
        RealTrialPurposeClass.LOCAL_RAG_CONFIDENTIALITY_TRIAL,
        RAGStage.CHUNKING,
        digest("expected-confidentiality-trial-outcome-v028"),
        RealDataAccessRetentionClass.NONE,
        True,
        NOW + timedelta(minutes=28),
    )
    provisioning_request = RealTrialRootProvisioningRequest(
        "root-provisioning-request-028",
        access.approved_trial.canonical_digest,
        access.authorization_record.canonical_digest,
        purpose.canonical_digest,
        root_descriptor.canonical_digest,
        target_reference.canonical_digest,
        "root-provisioner-028",
        access.operator_assignment.operator_id,
        NOW + timedelta(minutes=29),
        NOW + timedelta(minutes=79),
    )
    root_identity = RealTrialRootIdentity(
        "opaque-root-identity-028",
        provisioning_request.canonical_digest,
        TrialRootClass.CONTROLLED_TRIAL_ROOT,
        root_opaque_digest,
        resolver_policy.canonical_digest,
        "root-provisioner-028",
        NOW + timedelta(minutes=30),
    )
    verification_results = tuple(
        result_type(
            f"{result_type.__name__.lower()}-028",
            root_identity.canonical_digest,
            provisioning_request.canonical_digest,
            digest(f"{result_type.__name__}-protocol-v028"),
            digest(f"{result_type.__name__}-observed-v028"),
            "root-verifier-028",
            NOW + timedelta(minutes=31),
            RootProvisioningVerificationState.PASSED,
        )
        for result_type in RESULT_TYPES
    )
    (
        root_confinement,
        link_reparse,
        permission,
        write_prohibition,
        network_isolation,
    ) = verification_results
    root_attestation = RootProvisioningAttestation(
        "root-provisioning-attestation-028",
        provisioning_request.canonical_digest,
        root_identity.canonical_digest,
        root_confinement.canonical_digest,
        link_reparse.canonical_digest,
        permission.canonical_digest,
        write_prohibition.canonical_digest,
        network_isolation.canonical_digest,
        "root-verifier-028",
        NOW + timedelta(minutes=32),
        NOW + timedelta(minutes=78),
        RootProvisioningAttestationState.APPROVED,
    )
    target_selection = RealTrialTargetSelection(
        "target-selection-028",
        provisioning_request.canonical_digest,
        root_identity.canonical_digest,
        target_reference.canonical_digest,
        access.selector.canonical_digest,
        target_reference.expected_content_identity_digest,
        access.selector.data_class,
        access.selector.document_class,
        1,
        access.operator_assignment.operator_id,
        NOW + timedelta(minutes=33),
    )
    closure_requirement = RealTrialClosureRequirement(
        "closure-requirement-028",
        purpose.canonical_digest,
        access.authorization_record.canonical_digest,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        NOW + timedelta(minutes=34),
    )
    approval_request = RealTrialApprovalRequest(
        "one-shot-trial-approval-request-028",
        purpose.canonical_digest,
        provisioning_request.canonical_digest,
        root_attestation.canonical_digest,
        target_selection.canonical_digest,
        access.authorization_record.canonical_digest,
        access.access_approval.canonical_digest,
        access.approved_trial.canonical_digest,
        root_descriptor.canonical_digest,
        resolver_policy.canonical_digest,
        target_reference.canonical_digest,
        closure_requirement.canonical_digest,
        "trial-requester-028",
        access.operator_assignment.operator_id,
        NOW + timedelta(minutes=35),
        NOW + timedelta(minutes=77),
    )
    security_review = TrialSecurityReview(
        "trial-security-review-028",
        approval_request.canonical_digest,
        root_attestation.canonical_digest,
        resolver_policy.canonical_digest,
        "trial-security-reviewer-028",
        NOW + timedelta(minutes=36),
        TrialAuthorizationReviewResult.APPROVED,
        digest("trial-security-findings-v028"),
    )
    governance_review = TrialDataGovernanceReview(
        "trial-governance-review-028",
        approval_request.canonical_digest,
        purpose.canonical_digest,
        target_selection.canonical_digest,
        closure_requirement.canonical_digest,
        "trial-governance-reviewer-028",
        NOW + timedelta(minutes=37),
        TrialAuthorizationReviewResult.APPROVED,
        digest("trial-governance-findings-v028"),
    )
    execution_approval = TrialExecutionApproval(
        "trial-execution-approval-028",
        approval_request.canonical_digest,
        security_review.canonical_digest,
        governance_review.canonical_digest,
        access.operator_assignment.operator_id,
        "trial-execution-approver-028",
        NOW + timedelta(minutes=38),
        NOW + timedelta(minutes=76),
        TrialExecutionApprovalResult.APPROVED,
    )
    roles = RealTrialApprovalRoleContext(
        "root-provisioner-028",
        "root-verifier-028",
        "trial-requester-028",
        "trial-security-reviewer-028",
        "trial-governance-reviewer-028",
        access.operator_assignment.operator_id,
        "trial-execution-approver-028",
        access.access_approval.approver_id,
    )
    call = {
        "approved_trial_id": "approved-one-shot-real-data-trial-028",
        "source_context": source_context,
        "purpose": purpose,
        "provisioning_request": provisioning_request,
        "root_identity": root_identity,
        "root_confinement": root_confinement,
        "link_reparse": link_reparse,
        "permission": permission,
        "write_prohibition": write_prohibition,
        "network_isolation": network_isolation,
        "root_attestation": root_attestation,
        "target_selection": target_selection,
        "closure_requirement": closure_requirement,
        "approval_request": approval_request,
        "security_review": security_review,
        "governance_review": governance_review,
        "execution_approval": execution_approval,
        "roles": roles,
        "approval_generation": 1,
        "predecessor_approval_digest": None,
        "approved_at": NOW + timedelta(minutes=39),
        "expires_at": NOW + timedelta(minutes=75),
        "fault": fault,
    }
    active_registry = registry or TestOnlyRealTrialApprovalRegistry()
    result = active_registry.approve(**call) if approve else None
    return active_registry, result, call


def test_complete_chain_issues_metadata_only_one_shot_approval():
    registry, result, call = approval_chain()
    assert result.applied and result.record is not None
    record = result.record
    assert canonical_object_valid(record)
    assert record.state is (
        ApprovedOneShotRealDataTrialState.APPROVED_FOR_ONE_SHOT_EXECUTION_REVIEW
    )
    assert record.lifecycle is ApprovedOneShotRealDataTrialLifecycle.APPROVED
    assert record.operator_id == call["roles"].operator_id
    assert record.root_attestation_digest == call["root_attestation"].canonical_digest
    assert record.execution_approval_digest == call["execution_approval"].canonical_digest
    assert record.access_usage_contract_digest == (
        call["source_context"].read_authorization_context.usage_contract.canonical_digest
    )
    assert not record.actual_read_executed
    assert not record.real_data_use_authorized
    assert not record.embedding_authorized
    assert not record.persistence_authorized
    assert result.side_effects.all_zero
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (1, 1, 1)


def test_source_chain_uses_actual_v025_v027_objects_and_is_valid():
    _, _, call = approval_chain(approve=False)
    source = call["source_context"]
    assert validate_real_trial_approval_source(
        source, evaluation_time=call["approved_at"]
    ) == ()
    assert source.read_authorization_context.authorization_record is not None
    assert source.read_authorization_context.operator_assignment is not None
    assert source.read_authorization_context.usage_contract is not None
    assert source.root_descriptor is not None
    assert source.resolver_policy is not None
    assert source.controlled_target_reference is not None


def test_approved_record_cannot_be_constructed_or_replaced_publicly():
    _, result, _ = approval_chain()
    with pytest.raises(RealTrialApprovalError, match="approved_one_shot_trial_invalid"):
        replace(result.record)
    with pytest.raises(RealTrialApprovalError, match="approved_one_shot_trial_invalid"):
        ApprovedOneShotRealDataTrial(
            "forged-trial",
            *(digest("forged") for _ in range(17)),
            "operator",
            1,
            None,
            NOW,
            NOW + timedelta(minutes=2),
            NOW,
        )


@pytest.mark.parametrize(
    "missing", ("security_review", "governance_review", "execution_approval")
)
def test_missing_independent_review_or_approval_consumes_nothing(missing):
    registry, _, call = approval_chain(approve=False)
    call[missing] = None
    before = registry.replay_snapshot
    denied = registry.approve(**call)
    assert not denied.applied
    assert denied.reasons == (RealTrialApprovalRegistryReason.INVALID_CHAIN,)
    assert registry.records == ()
    assert registry.replay_snapshot == before == (frozenset(),) * 9
    assert denied.side_effects.all_zero


@pytest.mark.parametrize(
    "name,result_value",
    (
        ("security_review", TrialAuthorizationReviewResult.REJECTED),
        ("security_review", TrialAuthorizationReviewResult.NEEDS_MORE_EVIDENCE),
        ("governance_review", TrialAuthorizationReviewResult.REJECTED),
        ("governance_review", TrialAuthorizationReviewResult.NEEDS_MORE_EVIDENCE),
        ("execution_approval", TrialExecutionApprovalResult.REJECTED),
    ),
)
def test_rejected_or_incomplete_decisions_fail_closed(name, result_value):
    registry, _, call = approval_chain(approve=False)
    call[name] = replace(call[name], result=result_value)
    denied = registry.approve(**call)
    assert not denied.applied
    assert RealTrialApprovalRegistryReason.POLICY_INVALID in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 9


def test_roles_are_eight_way_distinct_and_access_approver_is_bound():
    _, _, call = approval_chain(approve=False)
    assert len(set(vars(call["roles"]).values()) - {call["roles"].canonical_digest}) == 8
    with pytest.raises(RealTrialApprovalError, match="real_trial_role_conflict"):
        replace(
            call["roles"],
            execution_approver_id=call["roles"].access_approver_id,
        )


def test_successful_only_replay_consumption_covers_entire_approval_chain():
    registry, result, call = approval_chain()
    assert all(len(item) == 1 for item in registry.replay_snapshot)
    replay_call = {
        **call,
        "approved_trial_id": "replayed-one-shot-trial-028",
        "approval_generation": 2,
        "predecessor_approval_digest": result.record.canonical_digest,
    }
    replay = registry.approve(**replay_call)
    assert not replay.applied
    assert RealTrialApprovalRegistryReason.REPLAY in replay.reasons
    assert len(registry.records) == 1


@pytest.mark.parametrize(
    "fault",
    (
        RealTrialApprovalRegistryFault.CANDIDATE_STATE,
        RealTrialApprovalRegistryFault.BEFORE_SWAP,
    ),
)
def test_registry_fault_is_atomic_retryable_and_consumes_nothing(fault):
    registry, failed, call = approval_chain(fault=fault)
    assert not failed.applied
    assert failed.reasons == (RealTrialApprovalRegistryReason.COMMIT_FAULT,)
    assert registry.records == ()
    assert registry.replay_snapshot == (frozenset(),) * 9
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (0, 0, 0)
    call["fault"] = RealTrialApprovalRegistryFault.NONE
    retried = registry.approve(**call)
    assert retried.applied


@pytest.mark.parametrize(
    "field,value,reason",
    (
        ("approval_generation", 0, RealTrialApprovalRegistryReason.GENERATION_MISMATCH),
        (
            "predecessor_approval_digest",
            digest("wrong-predecessor"),
            RealTrialApprovalRegistryReason.PREDECESSOR_MISMATCH,
        ),
    ),
)
def test_generation_and_predecessor_are_fail_closed(field, value, reason):
    registry, _, call = approval_chain(approve=False)
    call[field] = value
    denied = registry.approve(**call)
    assert not denied.applied and reason in denied.reasons
    assert registry.replay_snapshot == (frozenset(),) * 9


def test_readiness_is_review_only_and_never_claims_execution():
    _, result, call = approval_chain()
    decision = evaluate_one_shot_trial_approval_readiness(
        result.record, evaluation_time=call["approved_at"] + timedelta(minutes=1)
    )
    assert decision.state is (
        OneShotTrialApprovalReadinessState.
        ELIGIBLE_FOR_EXPLICIT_ONE_SHOT_EXECUTION_REVIEW
    )
    assert decision.eligible_for_explicit_one_shot_execution_review
    assert not decision.actual_read_executed
    assert not decision.real_data_use_authorized
    assert not decision.embedding_authorized
    assert not decision.persistence_authorized
    assert decision.external_side_effect_count == 0


def test_public_contracts_contain_no_locator_or_payload_fields():
    contracts = (
        RealTrialApprovalRequest,
        TrialSecurityReview,
        TrialDataGovernanceReview,
        TrialExecutionApproval,
        ApprovedOneShotRealDataTrial,
    )
    forbidden = {
        "path",
        "filename",
        "directory",
        "drive",
        "unc",
        "hostname",
        "payload",
        "credential",
        "token",
    }
    assert all(
        {item.name for item in fields(contract)}.isdisjoint(forbidden)
        for contract in contracts
    )
