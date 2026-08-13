from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone

import pytest

from ragguard.real_persistence import TestAtomicDurableStore
from ragguard.real_world_validation import (
    AuthorizationReviewResult, ControlledEnvironmentManifest,
    CredentialClass, DataClass, EnvironmentClass, RealWorldExecutionRequest,
    RealWorldValidationAuthorizationApproval, RealWorldValidationAuthorizationRequest,
    RealWorldValidationAuthorizationReview, RealWorldValidationError,
    RealWorldValidationPlan, SafeScenarioManifest, StorageMode,
    ValidationDecisionState, ValidationReason, evaluate_real_world_validation,
)
from tests.test_real_persistence_contract import commit as commit_persistence, context as persistence_context


def digest(char: str) -> str:
    return "sha256:" + char * 64


def context():
    runtime, *_ = persistence_context()
    store = TestAtomicDurableStore()
    persistence = commit_persistence(store).receipt
    assert persistence is not None
    now = runtime.committed_at + timedelta(hours=1)
    environment = ControlledEnvironmentManifest(
        "environment-v020", EnvironmentClass.ISOLATED_LOCAL, "disabled",
        DataClass.SYNTHETIC_ONLY, CredentialClass.NONE, StorageMode.IN_MEMORY_ONLY,
        "in_process", digest("1"), digest("2"), digest("3"), digest("4"), now)
    scenario = SafeScenarioManifest("scenario-v020", 3, "synthetic_contract",
                                    digest("5"), digest("6"), digest("7"))
    request = RealWorldValidationAuthorizationRequest(
        "authorization-v020", digest("8"), runtime.equivalence_approval_digest,
        runtime.canonical_digest, persistence.canonical_digest, digest("9"),
        environment.canonical_digest, digest("a"), "protocol-v020", "profile-v020",
        "version-v020", "product-v020", "product-version-v020", now + timedelta(seconds=2),
        "validation-requester", "validation-reviewer", "validation-approver")
    plan = RealWorldValidationPlan(
        "plan-v020", request.canonical_digest, environment.canonical_digest,
        request.validation_plan_digest, digest("b"), request.product_manifest_digest,
        environment.configuration_digest, environment.protocol_digest,
        scenario.canonical_digest, digest("c"), digest("d"), now + timedelta(seconds=1))
    review = RealWorldValidationAuthorizationReview(
        "authorization-review-v020", request.canonical_digest,
        request.requested_at + timedelta(microseconds=1), request.reviewer_id,
        AuthorizationReviewResult.APPROVED, digest("e"))
    approval = RealWorldValidationAuthorizationApproval(
        "authorization-approval-v020", request.canonical_digest, review.canonical_digest,
        review.reviewed_at + timedelta(microseconds=1), request.approver_id, True)
    evaluation_time = approval.approved_at + timedelta(microseconds=1)
    return runtime, persistence, environment, scenario, request, plan, review, approval, evaluation_time


def evaluate(**changes):
    runtime, receipt, environment, scenario, request, plan, review, approval, now = context()
    source_manual_approval_digest = request.manual_validation_approval_digest
    source_equivalence_approval_digest = request.equivalence_approval_digest
    source_product_manifest_digest = request.product_manifest_digest
    request = replace(request, **changes.pop("request_changes", {}))
    if request.canonical_digest != plan.authorization_request_digest:
        plan = replace(plan, authorization_request_digest=request.canonical_digest)
        review = replace(review, authorization_request_digest=request.canonical_digest)
        approval = replace(approval, authorization_request_digest=request.canonical_digest,
                           review_digest=review.canonical_digest)
    return evaluate_real_world_validation(
        request, changes.pop("environment", environment), changes.pop("plan", plan), scenario,
        changes.pop("runtime", runtime), changes.pop("persistence", receipt),
        changes.pop("review", review), changes.pop("approval", approval),
        manual_validation_approval_digest=changes.pop("manual", source_manual_approval_digest),
        equivalence_approval_digest=changes.pop("equivalence", source_equivalence_approval_digest),
        product_manifest_digest=changes.pop("product", source_product_manifest_digest),
        lifecycle_active=changes.pop("lifecycle_active", True),
        pending_revalidation=changes.pop("pending_revalidation", False),
        pending_transition=changes.pop("pending_transition", False),
        revoked_source=changes.pop("revoked_source", False),
        replaced_predecessor=changes.pop("replaced_predecessor", False),
        evaluation_time=changes.pop("evaluation_time", now),
        valid_until=changes.pop("valid_until", now + timedelta(days=30)), **changes)


def test_contracts_are_immutable_deterministic_and_canonical():
    *_, request, plan, _, _, _ = context()
    assert replace(request).canonical_digest == request.canonical_digest
    assert replace(plan).canonical_digest == plan.canonical_digest
    with pytest.raises(FrozenInstanceError):
        request.profile_id = "changed"  # type: ignore[misc]


def test_utc_offset_normalization_and_microseconds():
    *_, request, _, _, _, _ = context()
    offset = timezone(timedelta(hours=9))
    assert replace(request, requested_at=request.requested_at.astimezone(offset)).canonical_digest == request.canonical_digest
    assert replace(request, requested_at=request.requested_at + timedelta(microseconds=1)).canonical_digest != request.canonical_digest


@pytest.mark.parametrize("field", ["protocol_version", "profile_version", "product_version"])
@pytest.mark.parametrize("alias", ["current", "latest"])
def test_current_latest_aliases_are_rejected(field, alias):
    *_, request, _, _, _, _ = context()
    with pytest.raises(RealWorldValidationError):
        replace(request, **{field: alias})


def test_complete_chain_is_ready_for_controlled_execution_only():
    result = evaluate()
    assert result.state is ValidationDecisionState.READY_FOR_CONTROLLED_EXECUTION
    assert result.runtime_activation_count == result.network_count == result.filesystem_count == 0


def test_missing_review_or_approval_needs_authorization():
    assert evaluate(review=None).state is ValidationDecisionState.NEEDS_EXECUTION_AUTHORIZATION
    assert evaluate(approval=None).state is ValidationDecisionState.NEEDS_EXECUTION_AUTHORIZATION


@pytest.mark.parametrize("kwargs", [
    {"manual": digest("f")}, {"equivalence": digest("f")}, {"product": digest("f")},
    {"lifecycle_active": False}, {"pending_revalidation": True},
    {"pending_transition": True}, {"revoked_source": True}, {"replaced_predecessor": True},
])
def test_exact_chain_and_lifecycle_gates_fail_closed(kwargs):
    result = evaluate(**kwargs)
    assert result.state is ValidationDecisionState.INELIGIBLE
    assert result.reasons


def test_source_object_not_self_declared_digest_is_required():
    runtime, *_ = context()
    forged = replace(runtime, equivalence_approval_digest=digest("f"))
    assert ValidationReason.DIGEST_MISMATCH in evaluate(runtime=forged).reasons


def test_review_precedes_distinct_approval():
    *_, review, approval, _ = context()
    assert evaluate(approval=replace(approval, approved_at=review.reviewed_at)).state is ValidationDecisionState.INELIGIBLE
    assert evaluate(request_changes={"approver_id": "validation-reviewer"}).state is ValidationDecisionState.INELIGIBLE


def test_replay_future_stale_and_naive_times_rejected():
    *_, request, _, _, _, now = context()
    assert ValidationReason.REPLAY_DETECTED in evaluate(
        used_request_digests=frozenset({request.canonical_digest})).reasons
    assert ValidationReason.TEMPORAL_INVALID in evaluate(
        evaluation_time=request.requested_at - timedelta(microseconds=1)).reasons
    assert ValidationReason.STALE_REQUEST in evaluate(
        evaluation_time=now + timedelta(days=91), valid_until=now + timedelta(days=100)).reasons
    with pytest.raises(RealWorldValidationError):
        evaluate(evaluation_time=now.replace(tzinfo=None))


def test_request_surface_has_no_command_path_endpoint_or_credential_fields():
    assert not ({"command", "path", "endpoint", "credential", "token", "environment_variable"}
                & RealWorldExecutionRequest.__dataclass_fields__.keys())
