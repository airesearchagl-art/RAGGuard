from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.real_data_access import (
    RealDataAccessLoggingClass,
    RealDataAccessNetworkClass,
)
from ragguard.real_data_access_authorization import (
    AuthorizationUsageCounterContract,
    RealDataAccessAuthorizationLifecycle,
)
from ragguard.real_data_read_execution import RealDataReadAuthorizationContext
from ragguard.real_trial_approval import (
    RealTrialApprovalRegistryReason,
    RealTrialApprovalRoleContext,
    RealTrialApprovalSourceContext,
    TestOnlyRealTrialApprovalRegistry,
    TrialExecutionApprovalResult,
)
from ragguard.real_trial_root import (
    RootProvisioningAttestationState,
    RootProvisioningVerificationState,
)
from ragguard.storage_adapter import digest
from test_local_rag_execution_session_contract import NOW
from test_real_trial_approval_contract import approval_chain


def _rebuild_source(call, **access_changes):
    source = call["source_context"]
    access = replace(source.read_authorization_context, **access_changes)
    call["source_context"] = RealTrialApprovalSourceContext(
        access,
        source.root_descriptor,
        source.resolver_policy,
        source.controlled_target_reference,
    )


@pytest.mark.parametrize(
    "attack",
    (
        "forged_security_review",
        "forged_governance_review",
        "approval_request_mismatch",
        "security_request_mismatch",
        "governance_request_mismatch",
        "approval_security_mismatch",
        "approval_governance_mismatch",
        "operator_mismatch",
        "role_context_mismatch",
        "root_attestation_rejected",
        "root_gate_failed",
        "usage_exhausted",
        "authorization_revoked",
        "logging_policy_downgrade",
        "network_policy_downgrade",
        "stale_approval",
        "expired_request",
        "rejected_execution_approval",
    ),
)
def test_adversarial_chain_is_denied_with_zero_side_effects_and_unchanged_state(
    attack,
):
    registry, _, call = approval_chain(approve=False)
    if attack == "forged_security_review":
        object.__setattr__(
            call["security_review"], "findings_digest", digest("forged-findings")
        )
    elif attack == "forged_governance_review":
        object.__setattr__(
            call["governance_review"], "findings_digest", digest("forged-findings")
        )
    elif attack == "approval_request_mismatch":
        call["approval_request"] = replace(
            call["approval_request"], purpose_digest=digest("wrong-purpose")
        )
    elif attack == "security_request_mismatch":
        call["security_review"] = replace(
            call["security_review"], approval_request_digest=digest("wrong-request")
        )
    elif attack == "governance_request_mismatch":
        call["governance_review"] = replace(
            call["governance_review"], approval_request_digest=digest("wrong-request")
        )
    elif attack == "approval_security_mismatch":
        call["execution_approval"] = replace(
            call["execution_approval"], security_review_digest=digest("wrong-review")
        )
    elif attack == "approval_governance_mismatch":
        call["execution_approval"] = replace(
            call["execution_approval"], governance_review_digest=digest("wrong-review")
        )
    elif attack == "operator_mismatch":
        call["execution_approval"] = replace(
            call["execution_approval"], operator_id="forged-operator-028"
        )
    elif attack == "role_context_mismatch":
        roles = call["roles"]
        call["roles"] = RealTrialApprovalRoleContext(
            roles.root_provisioner_id,
            roles.root_verifier_id,
            roles.trial_requester_id,
            roles.security_reviewer_id,
            roles.governance_reviewer_id,
            "forged-role-operator-028",
            roles.execution_approver_id,
            roles.access_approver_id,
        )
    elif attack == "root_attestation_rejected":
        call["root_attestation"] = replace(
            call["root_attestation"],
            result=RootProvisioningAttestationState.REJECTED,
        )
    elif attack == "root_gate_failed":
        call["write_prohibition"] = replace(
            call["write_prohibition"],
            result=RootProvisioningVerificationState.FAILED,
        )
    elif attack == "usage_exhausted":
        access = call["source_context"].read_authorization_context
        exhausted_usage = AuthorizationUsageCounterContract(
            access.authorization_record.canonical_digest,
            1,
            0,
            digest("exhausted-usage-v028"),
            access.usage_contract.executor_contract_digest,
        )
        _rebuild_source(call, usage_contract=exhausted_usage)
    elif attack == "authorization_revoked":
        access = call["source_context"].read_authorization_context
        object.__setattr__(
            access.authorization_record,
            "lifecycle",
            RealDataAccessAuthorizationLifecycle.REVOKED,
        )
    elif attack == "logging_policy_downgrade":
        access = call["source_context"].read_authorization_context
        widened = replace(
            access.access_policy, logging_class=RealDataAccessLoggingClass.RAW
        )
        _rebuild_source(call, access_policy=widened)
    elif attack == "network_policy_downgrade":
        access = call["source_context"].read_authorization_context
        widened = replace(
            access.access_policy, network_class=RealDataAccessNetworkClass.ALLOWED
        )
        _rebuild_source(call, access_policy=widened)
    elif attack == "stale_approval":
        call["approved_at"] = call["approval_request"].requested_at + timedelta(hours=2)
    elif attack == "expired_request":
        call["approved_at"] = call["approval_request"].expires_at
    elif attack == "rejected_execution_approval":
        call["execution_approval"] = replace(
            call["execution_approval"], result=TrialExecutionApprovalResult.REJECTED
        )
    before = registry.replay_snapshot
    denied = registry.approve(**call)
    assert not denied.applied
    assert denied.reasons
    assert denied.side_effects.all_zero
    assert denied.side_effects.actual_file_open_count == 0
    assert denied.side_effects.actual_file_read_count == 0
    assert denied.side_effects.arbitrary_filesystem_read_count == 0
    assert denied.side_effects.local_rag_material_access_count == 0
    assert denied.side_effects.restricted_material_access_count == 0
    assert denied.side_effects.real_data_access_count == 0
    assert registry.records == ()
    assert registry.replay_snapshot == before == (frozenset(),) * 9
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (0, 0, 0)


def test_consistently_rebound_forged_root_identity_still_fails_against_descriptor():
    registry, _, call = approval_chain(approve=False)
    forged_identity = replace(
        call["root_identity"], opaque_identity_digest=digest("outside-root-identity")
    )
    call["root_identity"] = forged_identity
    result_names = (
        "root_confinement",
        "link_reparse",
        "permission",
        "write_prohibition",
        "network_isolation",
    )
    for name in result_names:
        call[name] = replace(
            call[name], root_identity_digest=forged_identity.canonical_digest
        )
    attestation = replace(
        call["root_attestation"],
        root_identity_digest=forged_identity.canonical_digest,
        root_confinement_result_digest=call["root_confinement"].canonical_digest,
        link_reparse_result_digest=call["link_reparse"].canonical_digest,
        permission_result_digest=call["permission"].canonical_digest,
        write_prohibition_result_digest=call["write_prohibition"].canonical_digest,
        network_isolation_result_digest=call["network_isolation"].canonical_digest,
    )
    call["root_attestation"] = attestation
    call["target_selection"] = replace(
        call["target_selection"], root_identity_digest=forged_identity.canonical_digest
    )
    request = replace(
        call["approval_request"],
        root_attestation_digest=attestation.canonical_digest,
        target_selection_digest=call["target_selection"].canonical_digest,
    )
    call["approval_request"] = request
    call["security_review"] = replace(
        call["security_review"],
        approval_request_digest=request.canonical_digest,
        root_attestation_digest=attestation.canonical_digest,
    )
    call["governance_review"] = replace(
        call["governance_review"],
        approval_request_digest=request.canonical_digest,
        target_selection_digest=call["target_selection"].canonical_digest,
    )
    call["execution_approval"] = replace(
        call["execution_approval"],
        approval_request_digest=request.canonical_digest,
        security_review_digest=call["security_review"].canonical_digest,
        governance_review_digest=call["governance_review"].canonical_digest,
    )
    denied = registry.approve(**call)
    assert not denied.applied
    assert RealTrialApprovalRegistryReason.ROOT_PROVISIONING_INVALID in denied.reasons
    assert denied.side_effects.all_zero
    assert registry.replay_snapshot == (frozenset(),) * 9


def test_approved_record_is_not_a_read_embedding_persistence_or_activation_capability():
    _, result, _ = approval_chain()
    record = result.record
    assert not record.actual_read_executed
    assert not record.real_data_use_authorized
    assert not record.embedding_authorized
    assert not record.persistence_authorized
    assert not record.export_authorized
    assert not record.runtime_activation_authorized
    assert not hasattr(record, "open")
    assert not hasattr(record, "read")
    assert not hasattr(record, "activate")


def test_duplicate_success_is_rejected_without_additional_mutation():
    registry, first, call = approval_chain()
    replay = registry.approve(
        **{
            **call,
            "approved_trial_id": "duplicate-approved-trial-028",
            "approval_generation": 2,
            "predecessor_approval_digest": first.record.canonical_digest,
        }
    )
    assert not replay.applied
    assert RealTrialApprovalRegistryReason.REPLAY in replay.reasons
    assert len(registry.records) == 1
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (1, 1, 1)
