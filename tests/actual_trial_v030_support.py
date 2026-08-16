from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from ragguard.actual_trial_execution import (
    ActualExecutionObjectChain,
    ActualOneShotTrialExecutor,
    ActualTrialExecutionLedger,
    HumanExecutionApproval,
    HumanExecutionApprovalResult,
    evaluate_actual_trial_gate,
)
from ragguard.actual_trial_root import _provision_controlled_fixture_actual_root
from ragguard.local_rag_integration import RAGStage
from ragguard.one_shot_trial_preparation import (
    ExecutionPreparationRequest,
    OneShotTrialExecutionPacket,
)
from ragguard.real_trial_approval import (
    RealTrialApprovalRequest,
    RealTrialApprovalSourceContext,
    TestOnlyRealTrialApprovalRegistry,
    TrialAuthorizationReviewResult,
    TrialDataGovernanceReview,
    TrialExecutionApproval,
    TrialExecutionApprovalResult,
    TrialSecurityReview,
)
from ragguard.real_trial_root import (
    LinkReparseVerificationResult,
    NetworkIsolationVerificationResult,
    PermissionVerificationResult,
    RealTrialRootIdentity,
    RealTrialRootProvisioningRequest,
    RealTrialTargetSelection,
    RootConfinementVerificationResult,
    RootProvisioningAttestation,
    RootProvisioningAttestationState,
    RootProvisioningVerificationState,
    WriteProhibitionVerificationResult,
    root_verification_suite_digest,
)
from ragguard.storage_adapter import digest
from test_local_rag_execution_session_contract import NOW
from test_real_trial_approval_contract import approval_chain


RESULT_TYPES = (
    RootConfinementVerificationResult,
    LinkReparseVerificationResult,
    PermissionVerificationResult,
    WriteProhibitionVerificationResult,
    NetworkIsolationVerificationResult,
)


def actual_execution_chain(
    tmp_path: Path,
    *,
    content: str = "Synthetic internal low calibration note for a controlled trial.",
):
    root = tmp_path / "controlled-v030-root"
    root.mkdir()
    target_path = root / "selected-note.txt"
    target_path.write_text(content, encoding="utf-8")
    provision = _provision_controlled_fixture_actual_root(
        root_path=root,
        relative_target="selected-note.txt",
        root_id="actual-controlled-root-030",
        target_reference_id="actual-target-reference-030",
        target_id="human-selected-target-030",
        selected_at=NOW + timedelta(minutes=28),
        allowed_file_types=(".txt",),
    )

    _, _, base = approval_chain(approve=False)
    access = base["source_context"].read_authorization_context
    purpose = base["purpose"]
    roles = base["roles"]
    source = RealTrialApprovalSourceContext(
        access,
        provision.root_descriptor,
        provision.resolver_policy,
        provision.target_reference,
    )
    provisioning_request = RealTrialRootProvisioningRequest(
        "actual-root-provisioning-request-030",
        access.approved_trial.canonical_digest,
        access.authorization_record.canonical_digest,
        purpose.canonical_digest,
        provision.root_descriptor.root_class,
        access.selector.document_class,
        provision.root_descriptor.canonical_digest,
        provision.target_reference.canonical_digest,
        roles.root_provisioner_id,
        access.operator_assignment.operator_id,
        NOW + timedelta(minutes=29),
        NOW + timedelta(minutes=79),
    )
    root_identity = RealTrialRootIdentity(
        "actual-opaque-root-identity-030",
        provisioning_request.canonical_digest,
        provision.root_descriptor.root_class,
        provision.capability.root_metadata_digest,
        provision.resolver_policy.canonical_digest,
        roles.root_provisioner_id,
        NOW + timedelta(minutes=30),
        NOW + timedelta(minutes=77),
    )
    verification_results = tuple(
        result_type(
            f"actual-{result_type.__name__.lower()}-030",
            root_identity.canonical_digest,
            provisioning_request.canonical_digest,
            digest(f"actual-{result_type.__name__}-protocol-v030"),
            digest(f"actual-{result_type.__name__}-observed-v030"),
            NOW + timedelta(minutes=31),
            roles.root_verifier_id,
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
        "actual-root-provisioning-attestation-030",
        provisioning_request.canonical_digest,
        root_identity.canonical_digest,
        root_confinement.canonical_digest,
        link_reparse.canonical_digest,
        permission.canonical_digest,
        write_prohibition.canonical_digest,
        network_isolation.canonical_digest,
        root_verification_suite_digest(*verification_results),
        roles.root_verifier_id,
        NOW + timedelta(minutes=32),
        NOW + timedelta(minutes=78),
        RootProvisioningAttestationState.APPROVED,
    )
    target_selection = RealTrialTargetSelection(
        "actual-target-selection-030",
        provisioning_request.canonical_digest,
        root_identity.canonical_digest,
        provision.target_reference.canonical_digest,
        access.selector.canonical_digest,
        provision.target.target_identity_digest,
        access.classification_policy.canonical_digest,
        access.selector.data_class,
        access.selector.document_class,
        1,
        access.operator_assignment.operator_id,
        NOW + timedelta(minutes=33),
    )
    closure_requirement = base["closure_requirement"]
    approval_request = RealTrialApprovalRequest(
        "actual-one-shot-trial-approval-request-030",
        purpose.canonical_digest,
        root_identity.canonical_digest,
        provisioning_request.canonical_digest,
        root_attestation.canonical_digest,
        target_selection.canonical_digest,
        access.authorization_record.canonical_digest,
        access.access_approval.canonical_digest,
        access.approved_trial.canonical_digest,
        provision.root_descriptor.canonical_digest,
        provision.resolver_policy.canonical_digest,
        provision.target_reference.canonical_digest,
        closure_requirement.canonical_digest,
        roles.trial_requester_id,
        access.operator_assignment.operator_id,
        NOW + timedelta(minutes=35),
        NOW + timedelta(minutes=77),
    )
    security_review = TrialSecurityReview(
        "actual-trial-security-review-030",
        approval_request.canonical_digest,
        root_attestation.canonical_digest,
        target_selection.canonical_digest,
        provision.resolver_policy.canonical_digest,
        roles.security_reviewer_id,
        NOW + timedelta(minutes=36),
        TrialAuthorizationReviewResult.APPROVED,
        digest("actual-trial-security-findings-v030"),
    )
    governance_review = TrialDataGovernanceReview(
        "actual-trial-governance-review-030",
        approval_request.canonical_digest,
        purpose.canonical_digest,
        target_selection.canonical_digest,
        closure_requirement.canonical_digest,
        access.classification_policy.canonical_digest,
        access.access_policy.retention_policy_digest,
        access.access_policy.logging_policy_digest,
        access.access_policy.persistence_policy_digest,
        roles.governance_reviewer_id,
        NOW + timedelta(minutes=37),
        TrialAuthorizationReviewResult.APPROVED,
        digest("actual-trial-governance-findings-v030"),
    )
    execution_approval = TrialExecutionApproval(
        "actual-trial-execution-approval-030",
        approval_request.canonical_digest,
        security_review.canonical_digest,
        governance_review.canonical_digest,
        access.operator_assignment.operator_id,
        roles.execution_approver_id,
        NOW + timedelta(minutes=38),
        NOW + timedelta(minutes=76),
        TrialExecutionApprovalResult.APPROVED,
    )
    approval_call = {
        "approved_trial_id": "actual-approved-one-shot-trial-030",
        "source_context": source,
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
    }
    approval_result = TestOnlyRealTrialApprovalRegistry().approve(**approval_call)
    assert approval_result.applied and approval_result.record is not None
    approved_trial = approval_result.record
    packet = OneShotTrialExecutionPacket(
        "actual-one-shot-execution-packet-030",
        approved_trial.canonical_digest,
        access.authorization_record.canonical_digest,
        root_identity.canonical_digest,
        root_attestation.canonical_digest,
        target_selection.canonical_digest,
        access.operator_assignment.canonical_digest,
        access.operator_assignment.operator_id,
        purpose.canonical_digest,
        purpose.purpose_class,
        provision.resolver_policy.canonical_digest,
        provision.resolver_policy.canonical_digest,
        closure_requirement.canonical_digest,
        1,
        RAGStage.CHUNKING,
        False,
        False,
        False,
        False,
        False,
        False,
        NOW + timedelta(minutes=40),
        NOW + timedelta(minutes=70),
    )
    preparation_request = ExecutionPreparationRequest(
        "actual-execution-preparation-request-030",
        packet.canonical_digest,
        "actual-execution-preparation-requester-030",
        NOW + timedelta(minutes=41),
        NOW + timedelta(minutes=42),
    )
    chain = ActualExecutionObjectChain(
        preparation_request,
        approved_trial,
        source,
        purpose,
        provisioning_request,
        root_identity,
        root_confinement,
        link_reparse,
        permission,
        write_prohibition,
        network_isolation,
        root_attestation,
        target_selection,
        closure_requirement,
        approval_request,
        security_review,
        governance_review,
        execution_approval,
        roles,
    )
    gate = evaluate_actual_trial_gate(packet=packet, object_chain=chain)
    human_approval = HumanExecutionApproval(
        "human-execution-approval-030",
        packet.canonical_digest,
        access.operator_assignment.operator_id,
        NOW + timedelta(minutes=43),
        NOW + timedelta(minutes=65),
        HumanExecutionApprovalResult.APPROVED,
    )
    return {
        "root": root,
        "target_path": target_path,
        "provision": provision,
        "packet": packet,
        "chain": chain,
        "gate": gate,
        "human_approval": human_approval,
        "authorization_context": access,
        "operator_id": access.operator_assignment.operator_id,
        "executed_at": NOW + timedelta(minutes=44),
        "executor": ActualOneShotTrialExecutor(),
        "ledger": ActualTrialExecutionLedger(),
    }


def execute_actual_chain(call, **overrides):
    values = {
        "receipt_id": "actual-one-shot-receipt-030",
        "closure_id": "actual-trial-closure-030",
        "packet": call["packet"],
        "gate": call["gate"],
        "human_approval": call["human_approval"],
        "root_capability": call["provision"].capability,
        "target": call["provision"].target,
        "object_chain": call["chain"],
        "authorization_context": call["authorization_context"],
        "operator_id": call["operator_id"],
        "executed_at": call["executed_at"],
        "ledger": call["ledger"],
    }
    values.update(overrides)
    return call["executor"].execute(**values)
