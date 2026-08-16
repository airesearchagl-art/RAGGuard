from dataclasses import fields, replace
from datetime import timedelta

import pytest

from ragguard.real_data_access import (
    RealDataAccessRetentionClass,
    RealDataByteClass,
)
from ragguard.real_target_resolver import RealTargetResolverError, RealTargetResolverPolicy
from ragguard.real_trial_root import (
    LinkReparseVerificationResult,
    NetworkIsolationVerificationResult,
    PermissionVerificationResult,
    RealTrialPurpose,
    RealTrialRootError,
    RealTrialRootIdentity,
    RealTrialRootProvisioningRequest,
    RealTrialTargetSelection,
    RootConfinementVerificationResult,
    RootProvisioningAttestation,
    RootProvisioningAttestationState,
    RootProvisioningVerificationState,
    WriteProhibitionVerificationResult,
    fixed_real_trial_policy_summary,
    validate_real_trial_root_chain,
)
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_session_contract import NOW
from test_real_trial_approval_contract import approval_chain


RESULT_BINDINGS = (
    ("root_confinement", "root_confinement_result_digest"),
    ("link_reparse", "link_reparse_result_digest"),
    ("permission", "permission_result_digest"),
    ("write_prohibition", "write_prohibition_result_digest"),
    ("network_isolation", "network_isolation_result_digest"),
)


def root_validation_call(call):
    source = call["source_context"]
    return {
        "purpose": call["purpose"],
        "provisioning_request": call["provisioning_request"],
        "root_identity": call["root_identity"],
        "root_descriptor": source.root_descriptor,
        "resolver_policy": source.resolver_policy,
        "target_reference": source.controlled_target_reference,
        "root_confinement": call["root_confinement"],
        "link_reparse": call["link_reparse"],
        "permission": call["permission"],
        "write_prohibition": call["write_prohibition"],
        "network_isolation": call["network_isolation"],
        "attestation": call["root_attestation"],
        "target_selection": call["target_selection"],
        "root_provisioner_id": call["roles"].root_provisioner_id,
        "root_verifier_id": call["roles"].root_verifier_id,
        "operator_id": call["roles"].operator_id,
        "evaluation_time": call["approved_at"],
    }


def test_root_provisioning_chain_passes_all_five_object_backed_hard_gates():
    _, _, call = approval_chain(approve=False)
    validation = root_validation_call(call)
    assert validate_real_trial_root_chain(**validation) == ()
    assert all(
        canonical_object_valid(validation[name]) for name, _ in RESULT_BINDINGS
    )


@pytest.mark.parametrize("result_name,attestation_field", RESULT_BINDINGS)
@pytest.mark.parametrize(
    "state",
    (
        RootProvisioningVerificationState.FAILED,
        RootProvisioningVerificationState.INCOMPLETE,
    ),
)
def test_each_failed_or_incomplete_root_gate_is_rejected(
    result_name, attestation_field, state
):
    _, _, call = approval_chain(approve=False)
    validation = root_validation_call(call)
    changed = replace(validation[result_name], result=state)
    validation[result_name] = changed
    validation["attestation"] = replace(
        validation["attestation"], **{attestation_field: changed.canonical_digest}
    )
    assert "root_hard_gate_failed" in validate_real_trial_root_chain(**validation)


def test_rejected_or_incomplete_attestation_is_never_approval_evidence():
    _, _, call = approval_chain(approve=False)
    for state in (
        RootProvisioningAttestationState.REJECTED,
        RootProvisioningAttestationState.INCOMPLETE,
    ):
        validation = root_validation_call(call)
        validation["attestation"] = replace(validation["attestation"], result=state)
        assert "root_role_conflict" in validate_real_trial_root_chain(**validation)


@pytest.mark.parametrize(
    "field,value",
    (
        ("root_provisioner_id", "wrong-provisioner"),
        ("root_verifier_id", "wrong-verifier"),
        ("operator_id", "wrong-operator"),
    ),
)
def test_root_role_context_mismatch_fails_closed(field, value):
    _, _, call = approval_chain(approve=False)
    validation = root_validation_call(call)
    validation[field] = value
    reasons = validate_real_trial_root_chain(**validation)
    assert reasons
    assert "root_provisioning_binding_mismatch" in reasons or "root_hard_gate_failed" in reasons


def test_provisioner_verifier_operator_must_be_distinct():
    _, _, call = approval_chain(approve=False)
    validation = root_validation_call(call)
    validation["root_verifier_id"] = validation["root_provisioner_id"]
    reasons = validate_real_trial_root_chain(**validation)
    assert "root_role_conflict" in reasons


def test_target_selection_is_one_opaque_internal_low_document_only():
    _, _, call = approval_chain(approve=False)
    target = call["target_selection"]
    assert target.maximum_document_count == 1
    assert canonical_object_valid(target)
    with pytest.raises(RealTrialRootError, match="real_trial_target_selection_invalid"):
        replace(target, maximum_document_count=2)


def test_root_identity_and_public_contracts_have_no_locator_surface():
    contracts = (
        RealTrialPurpose,
        RealTrialRootProvisioningRequest,
        RealTrialRootIdentity,
        RootProvisioningAttestation,
        RealTrialTargetSelection,
    )
    forbidden = {
        "path",
        "filename",
        "directory",
        "drive",
        "unc",
        "hostname",
        "wildcard",
    }
    assert all(
        {item.name for item in fields(contract)}.isdisjoint(forbidden)
        for contract in contracts
    )
    _, _, call = approval_chain(approve=False)
    assert repr(call["root_identity"]) == "RealTrialRootIdentity(<safe>)"


def test_root_descriptor_and_identity_are_exactly_bound():
    _, _, call = approval_chain(approve=False)
    validation = root_validation_call(call)
    validation["root_identity"] = replace(
        validation["root_identity"], opaque_identity_digest=digest("different-root")
    )
    assert "root_provisioning_binding_mismatch" in validate_real_trial_root_chain(
        **validation
    )


def test_resolver_policy_rejects_link_traversal_and_absolute_input_downgrades():
    _, _, call = approval_chain(approve=False)
    policy = call["source_context"].resolver_policy
    for field in (
        "allow_symlink",
        "allow_junction",
        "allow_reparse_point",
        "allow_parent_traversal",
        "allow_absolute_user_input",
    ):
        with pytest.raises(RealTargetResolverError):
            replace(policy, **{field: True})


def test_expired_root_request_or_attestation_is_rejected():
    _, _, call = approval_chain(approve=False)
    validation = root_validation_call(call)
    validation["evaluation_time"] = call["root_attestation"].expires_at
    assert "root_temporal_invalid" in validate_real_trial_root_chain(**validation)


def test_forged_root_evidence_is_detected_even_when_values_look_passed():
    _, _, call = approval_chain(approve=False)
    validation = root_validation_call(call)
    object.__setattr__(validation["permission"], "protocol_digest", digest("forged"))
    assert "forged_root_provisioning_chain" in validate_real_trial_root_chain(
        **validation
    )


def test_fixed_policy_summary_is_safe_and_deny_by_default():
    summary = fixed_real_trial_policy_summary()
    assert summary == {
        "data_class": "internal_low",
        "document_count": 1,
        "stage_ceiling": "chunking_candidate",
        "retention": "none",
        "logging": "none",
        "cache": "none",
        "persistence": "none",
        "export": "prohibited",
        "network": "prohibited",
        "closure_required": True,
    }


def test_purpose_cannot_widen_retention_or_skip_closure():
    _, _, call = approval_chain(approve=False)
    purpose = call["purpose"]
    with pytest.raises(RealTrialRootError, match="real_trial_purpose_invalid"):
        replace(purpose, retention_class=RealDataAccessRetentionClass.RAW_EPHEMERAL)
    with pytest.raises(RealTrialRootError, match="real_trial_purpose_invalid"):
        replace(purpose, closure_required=False)


def test_root_temporal_order_cannot_be_reversed():
    _, _, call = approval_chain(approve=False)
    validation = root_validation_call(call)
    validation["root_identity"] = replace(
        validation["root_identity"],
        provisioned_at=NOW + timedelta(minutes=40),
    )
    assert "root_temporal_invalid" in validate_real_trial_root_chain(**validation)
