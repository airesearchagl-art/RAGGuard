from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone

import pytest

from ragguard.authorization_activation import ActivationRequest, evaluate_activation_request
from ragguard.equivalence_attestation import EquivalenceAttestationChain
from ragguard.production_authorization import (
    ProductionAuthorizationRequest,
    ProductionAuthorizationResult,
    evaluate_production_authorization,
)
from ragguard.production_boundary import (
    CompatibilityEvidenceKind,
    PersistenceState,
    RuntimeAuthorizationState,
    SecurityReviewState,
)
from ragguard.production_equivalence import ProductionEquivalentState
from ragguard.production_persistence import (
    InMemoryPersistenceStore,
    PersistenceCommitRequest,
    create_persisted_authorization_record,
)
from ragguard.production_registry import RegistryStatus
from ragguard.runtime_authorization import (
    RuntimeApprovalResult,
    RuntimeAuthorizationApproval,
    RuntimeAuthorizationRequest,
    RuntimeAuthorizationResult,
    RuntimeAuthorizationReview,
    RuntimeReviewResult,
    evaluate_runtime_authorization,
)
from tests.test_equivalence_attestation import attestation_chain
from tests.test_production_authorization_evaluator import manually_ready
from tests.test_production_boundary_contract import source_decision, source_entry
from tests.test_production_persistence_contract import approved_policy


def digest(value: str) -> str:
    return "sha256:" + value * 64


def runtime_context():
    chain: EquivalenceAttestationChain = attestation_chain()
    decision = replace(source_decision(), approver_id="approver-v016")
    entry = replace(source_entry(), admission_decision_digest=decision.canonical_digest)
    values = manually_ready(
        compatibility_evidence_kind=CompatibilityEvidenceKind.PRODUCTION_EQUIVALENT,
        production_equivalent_state=ProductionEquivalentState.APPROVED,
        security_review_state=SecurityReviewState.APPROVED,
        persistence_state=PersistenceState.PRODUCTION_READY,
        runtime_authorization_state=RuntimeAuthorizationState.CANDIDATE_ONLY,
        manual_validation_approval_digest=chain.request.manual_validation_approval_digest,
        approver_id="approver-v016",
        evaluation_time=chain.approval.approved_at + timedelta(microseconds=1),
        evidence_expires_at=chain.approval.approved_at + timedelta(days=30),
        equivalence_assessment_digest=chain.assessment.canonical_digest,
        equivalence_review_digest=chain.review.canonical_digest,
        equivalence_approval_digest=chain.approval.canonical_digest,
        equivalence_criteria_digest=chain.criteria.canonical_digest,
        equivalence_evidence_descriptor_digest=chain.descriptor.canonical_digest,
        source_admission_entry_digest=entry.canonical_digest,
        registry_entry_digest=entry.canonical_digest,
        registry_state_digest=(
            __import__("ragguard.production_boundary", fromlist=["canonical_registry_state_digest"])
            .canonical_registry_state_digest((entry.canonical_digest,))
        ),
        admission_decision_digest=decision.canonical_digest,
    )
    from tests.test_production_boundary_contract import boundary_evidence
    evidence = boundary_evidence(**values)
    candidate = evaluate_production_authorization(ProductionAuthorizationRequest(
        request_id="authorization-candidate-v018", evidence=evidence,
        source_entry=entry, source_admission_decision=decision,
        registry_snapshot_digests=(entry.canonical_digest,),
        equivalence_chain=chain,
    ))
    assert candidate.result is ProductionAuthorizationResult.ELIGIBLE_FOR_AUTHORIZATION_REVIEW
    policy = approved_policy()
    persisted_at = evidence.evaluation_time + timedelta(microseconds=1)
    record = create_persisted_authorization_record(
        persisted_record_id="persisted-authorization-v018", source_candidate=candidate,
        source_evidence=evidence, policy=policy, persisted_at=persisted_at,
        persisted_by="persistence-operator-v018", persistence_generation=1,
        previous_record_digest=None,
    )
    store = InMemoryPersistenceStore()
    commit = store.commit(PersistenceCommitRequest(
        record=record, source_candidate=candidate, source_evidence=evidence,
        policy=policy, registry_snapshot_digests=(entry.canonical_digest,),
        evaluation_time=persisted_at + timedelta(microseconds=1),
    ))
    assert commit.applied and commit.receipt is not None
    receipt = commit.receipt
    activation_request = ActivationRequest(
        activation_request_id="activation-request-v018",
        persisted_record_digest=record.canonical_digest,
        expected_persistence_generation=1,
        activation_requested_at=receipt.committed_at + timedelta(microseconds=1),
        activation_requester_id="activation-requester-v018",
        activation_reviewer_id="activation-reviewer-v018",
        authorization_approver_id=evidence.authorization_approver_id,
        expected_profile_id=evidence.profile_id,
        expected_profile_version=evidence.profile_version,
        expected_product_id=evidence.product_id,
        expected_product_version=evidence.product_version,
        expected_protocol_version=evidence.protocol_version,
        expected_registry_state_digest=evidence.registry_state_digest,
        expected_lifecycle_status=RegistryStatus.ACTIVE,
        request_nonce_digest=digest("1"), activation_review_approved=True,
    )
    activation_evaluation = evaluate_activation_request(
        activation_request, record, receipt, policy, store.snapshot, candidate,
        evidence, (entry.canonical_digest,),
        activation_request.activation_requested_at + timedelta(microseconds=1),
    )
    assert activation_evaluation.commit_plan is not None
    plan = activation_evaluation.commit_plan
    request = RuntimeAuthorizationRequest(
        authorization_request_id="runtime-authorization-v018",
        production_authorization_candidate_digest=candidate.canonical_digest,
        production_boundary_evidence_digest=evidence.canonical_digest,
        equivalence_assessment_digest=chain.assessment.canonical_digest,
        equivalence_review_digest=chain.review.canonical_digest,
        equivalence_approval_digest=chain.approval.canonical_digest,
        equivalence_criteria_digest=chain.criteria.canonical_digest,
        equivalence_evidence_descriptor_digest=chain.descriptor.canonical_digest,
        persistence_record_digest=record.canonical_digest,
        persistence_receipt_digest=receipt.canonical_digest,
        persistence_snapshot_digest=store.snapshot.canonical_digest,
        activation_request_digest=activation_request.canonical_digest,
        activation_commit_plan_digest=plan.canonical_digest,
        expected_registry_state_digest=evidence.registry_state_digest,
        expected_lifecycle_status=RegistryStatus.ACTIVE,
        profile_id=evidence.profile_id, profile_version=evidence.profile_version,
        product_id=evidence.product_id, product_version=evidence.product_version,
        protocol_version=evidence.protocol_version,
        requested_at=plan.approved_at + timedelta(microseconds=1),
        requested_by="runtime-requester-v018",
        runtime_authorization_reviewer_id="runtime-reviewer-v018",
        runtime_authorization_approver_id="runtime-approver-v018",
    )
    review = RuntimeAuthorizationReview(
        review_id="runtime-review-v018", authorization_request_digest=request.canonical_digest,
        reviewed_at=request.requested_at + timedelta(microseconds=1),
        reviewer_id=request.runtime_authorization_reviewer_id,
        review_result=RuntimeReviewResult.APPROVED, findings_digest=digest("2"),
    )
    approval = RuntimeAuthorizationApproval(
        approval_id="runtime-approval-v018", authorization_request_digest=request.canonical_digest,
        review_digest=review.canonical_digest,
        approved_at=review.reviewed_at + timedelta(microseconds=1),
        approver_id=request.runtime_authorization_approver_id,
        approval_result=RuntimeApprovalResult.APPROVED,
    )
    evaluation_time = approval.approved_at + timedelta(microseconds=1)
    return (entry, evidence, candidate, chain, record, receipt, store.snapshot, policy,
            activation_request, plan, request, review, approval, evaluation_time)


def evaluate(*, request_changes=None, review_value="default", approval_value="default",
             chain_value="default", record_value="default", receipt_value="default",
             snapshot_value="default", policy_value="default", activation_request_value="default",
             plan_value="default", evidence_changes=None, used=None):
    (entry, evidence, candidate, chain, record, receipt, snapshot, policy,
     activation_request, plan, request, review, approval, evaluation_time) = runtime_context()
    if evidence_changes:
        evidence = replace(evidence, **evidence_changes)
    if request_changes:
        request = replace(request, **request_changes)
        if review_value == "default":
            review = replace(review, authorization_request_digest=request.canonical_digest)
        if approval_value == "default":
            approval = replace(approval, authorization_request_digest=request.canonical_digest,
                               review_digest=review.canonical_digest)
    values = {
        "equivalence_chain": chain if chain_value == "default" else chain_value,
        "record": record if record_value == "default" else record_value,
        "receipt": receipt if receipt_value == "default" else receipt_value,
        "snapshot": snapshot if snapshot_value == "default" else snapshot_value,
        "policy": policy if policy_value == "default" else policy_value,
        "activation_request": activation_request if activation_request_value == "default" else activation_request_value,
        "activation_plan": plan if plan_value == "default" else plan_value,
        "review": review if review_value == "default" else review_value,
        "approval": approval if approval_value == "default" else approval_value,
    }
    return evaluate_runtime_authorization(
        request, candidate, evidence, values["equivalence_chain"], values["record"],
        values["receipt"], values["snapshot"], values["policy"],
        values["activation_request"], values["activation_plan"], values["review"],
        values["approval"], (entry.canonical_digest,), evaluation_time, **(used or {}))


def assert_zero(result):
    assert (result.write_count, result.mutation_count, result.persistence_write_count,
            result.filesystem_write_count, result.database_write_count, result.network_count,
            result.transport_count, result.http_count, result.runtime_activation_count,
            result.token_count, result.credential_count) == (0,) * 11


def test_request_review_and_approval_are_immutable_and_deterministic():
    *_, request, review, approval, _ = runtime_context()
    assert request.canonical_digest == replace(request).canonical_digest
    assert review.canonical_digest == replace(review).canonical_digest
    assert approval.canonical_digest == replace(approval).canonical_digest
    with pytest.raises(FrozenInstanceError):
        request.requested_by = "changed"  # type: ignore[misc]


def test_microsecond_changes_digest_and_offset_is_canonical():
    *_, request, _, _, _ = runtime_context()
    assert replace(request, requested_at=request.requested_at + timedelta(microseconds=1)).canonical_digest != request.canonical_digest
    offset = timezone(timedelta(hours=9))
    assert replace(request, requested_at=request.requested_at.astimezone(offset)).canonical_digest == request.canonical_digest


@pytest.mark.parametrize("field", ["use_current_alias", "use_latest_alias", "allow_fallback", "infer_source"])
def test_unsafe_resolution_is_ineligible(field):
    assert evaluate(request_changes={field: True}).result is RuntimeAuthorizationResult.INELIGIBLE


@pytest.mark.parametrize("field", ["profile_id", "product_id"])
def test_identity_tampering_is_ineligible(field):
    assert evaluate(request_changes={field: "other-id"}).result is RuntimeAuthorizationResult.INELIGIBLE


def test_missing_equivalence_precedes_other_missing_gates():
    result = evaluate(chain_value=None, record_value=None, receipt_value=None, plan_value=None)
    assert result.result is RuntimeAuthorizationResult.NEEDS_EQUIVALENCE_APPROVAL


def test_missing_persistence_is_explicit():
    assert evaluate(record_value=None, receipt_value=None, snapshot_value=None, policy_value=None).result is RuntimeAuthorizationResult.NEEDS_PERSISTENCE_VERIFICATION


def test_missing_activation_plan_is_explicit():
    assert evaluate(plan_value=None).result is RuntimeAuthorizationResult.NEEDS_ACTIVATION_COMMIT_PLAN


def test_missing_review_is_explicit():
    assert evaluate(review_value=None, approval_value=None).result is RuntimeAuthorizationResult.NEEDS_RUNTIME_AUTHORIZATION_REVIEW


def test_full_chain_is_commit_ready_but_not_active():
    result = evaluate()
    assert result.result is RuntimeAuthorizationResult.READY_FOR_RUNTIME_AUTHORIZATION_COMMIT
    assert result.runtime_activation_count == 0
    assert_zero(result)


@pytest.mark.parametrize("field", ["equivalence_assessment_digest", "equivalence_review_digest",
                                    "equivalence_approval_digest", "equivalence_criteria_digest",
                                    "equivalence_evidence_descriptor_digest"])
def test_equivalence_digest_tampering_requires_approval(field):
    assert evaluate(request_changes={field: digest("9")}).result is RuntimeAuthorizationResult.NEEDS_EQUIVALENCE_APPROVAL


@pytest.mark.parametrize("field", ["persistence_record_digest", "persistence_receipt_digest", "persistence_snapshot_digest"])
def test_persistence_digest_tampering_requires_verification(field):
    assert evaluate(request_changes={field: digest("8")}).result is RuntimeAuthorizationResult.NEEDS_PERSISTENCE_VERIFICATION


@pytest.mark.parametrize("field", ["activation_request_digest", "activation_commit_plan_digest"])
def test_activation_digest_tampering_requires_plan(field):
    assert evaluate(request_changes={field: digest("7")}).result is RuntimeAuthorizationResult.NEEDS_ACTIVATION_COMMIT_PLAN


@pytest.mark.parametrize("status", [RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED, RegistryStatus.REVOKED])
def test_non_active_lifecycle_is_ineligible(status):
    assert evaluate(request_changes={"expected_lifecycle_status": status}).result is RuntimeAuthorizationResult.INELIGIBLE


def test_pending_revalidation_and_transition_are_ineligible():
    assert evaluate(evidence_changes={"unresolved_revalidation": True}).result is RuntimeAuthorizationResult.INELIGIBLE
    assert evaluate(evidence_changes={"pending_lifecycle_transition": True}).result is RuntimeAuthorizationResult.INELIGIBLE


@pytest.mark.parametrize("field", ["requested_by", "runtime_authorization_reviewer_id", "runtime_authorization_approver_id"])
def test_runtime_roles_are_distinct_from_source_roles(field):
    assert evaluate(request_changes={field: "equivalence-approver"}).result is RuntimeAuthorizationResult.INELIGIBLE


def test_reviewer_and_approver_are_distinct():
    assert evaluate(request_changes={"runtime_authorization_approver_id": "runtime-reviewer-v018"}).result is RuntimeAuthorizationResult.INELIGIBLE


def test_review_before_approval_is_strict():
    *_, request, review, approval, _ = runtime_context()
    changed = replace(approval, approved_at=review.reviewed_at)
    assert evaluate(approval_value=changed).result is RuntimeAuthorizationResult.NEEDS_RUNTIME_AUTHORIZATION_REVIEW


def test_replay_dimensions_are_ineligible():
    *_, candidate, chain, _, _, _, _, _, plan, request, _, approval, _ = runtime_context()
    result = evaluate(used={"used_request_ids": frozenset({request.authorization_request_id})})
    assert result.result is RuntimeAuthorizationResult.INELIGIBLE
    result = evaluate(used={"used_candidate_digests": frozenset({candidate.canonical_digest})})
    assert result.result is RuntimeAuthorizationResult.INELIGIBLE
    result = evaluate(used={"used_equivalence_approval_digests": frozenset({chain.approval.canonical_digest})})
    assert result.result is RuntimeAuthorizationResult.INELIGIBLE
    result = evaluate(used={"used_activation_plan_digests": frozenset({plan.canonical_digest})})
    assert result.result is RuntimeAuthorizationResult.INELIGIBLE
    result = evaluate(used={"used_runtime_approval_digests": frozenset({approval.canonical_digest})})
    assert result.result is RuntimeAuthorizationResult.INELIGIBLE


def test_denials_have_zero_side_effects():
    assert_zero(evaluate(request_changes={"allow_fallback": True}))
