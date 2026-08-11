from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from ragguard.equivalence_attestation import (
    EquivalenceApproval,
    EquivalenceApprovalResult,
    EquivalenceAttestationChain,
    EquivalenceCommitReason,
    EquivalenceReview,
    EquivalenceReviewResult,
    TestEquivalenceAttestationStore,
)
from ragguard.production_equivalence import ProductionEquivalenceError
from test_production_equivalence_contract import (
    EVALUATION_TIME,
    assess,
    assessment_request,
    criteria,
    descriptor,
    digest,
)


def review(**changes: object) -> EquivalenceReview:
    assessment = assess()
    values: dict[str, object] = {
        "review_id": "equivalence-review-v017",
        "assessment_digest": assessment.canonical_digest,
        "evidence_descriptor_digest": descriptor().canonical_digest,
        "criteria_digest": criteria().canonical_digest,
        "reviewed_at": EVALUATION_TIME + timedelta(microseconds=1),
        "reviewer_id": "equivalence-reviewer",
        "review_result": EquivalenceReviewResult.APPROVED,
        "findings_digest": digest("a"),
    }
    values.update(changes)
    return EquivalenceReview(**values)  # type: ignore[arg-type]


def approval(**changes: object) -> EquivalenceApproval:
    values: dict[str, object] = {
        "approval_id": "equivalence-approval-v017",
        "assessment_digest": assess().canonical_digest,
        "review_digest": review().canonical_digest,
        "approved_at": EVALUATION_TIME + timedelta(microseconds=2),
        "approver_id": "equivalence-approver",
        "approval_result": EquivalenceApprovalResult.APPROVED,
    }
    values.update(changes)
    return EquivalenceApproval(**values)  # type: ignore[arg-type]


def attestation_chain(**changes: object) -> EquivalenceAttestationChain:
    values: dict[str, object] = {
        "request": assessment_request(),
        "criteria": criteria(),
        "descriptor": descriptor(),
        "assessment": assess(),
        "review": review(),
        "approval": approval(),
    }
    values.update(changes)
    return EquivalenceAttestationChain(**values)  # type: ignore[arg-type]


def commit(store: TestEquivalenceAttestationStore, **changes: object):
    values: dict[str, object] = {
        "chain": attestation_chain(),
        "evaluation_time": EVALUATION_TIME + timedelta(microseconds=3),
        "manual_validation_approver_id": "approver-v016",
        "protected_actor_ids": (
            "registry-admin-v016",
            "boundary-reviewer",
            "authorization-approver",
        ),
    }
    values.update(changes)
    return store.commit(**values)  # type: ignore[arg-type]


def test_review_and_approval_are_immutable_and_digest_covered() -> None:
    value = review()
    assert value.canonical_digest == review().canonical_digest
    assert replace(
        value, reviewed_at=value.reviewed_at + timedelta(microseconds=1)
    ).canonical_digest != value.canonical_digest
    with pytest.raises(FrozenInstanceError):
        value.reviewer_id = "changed"  # type: ignore[misc]


def test_complete_chain_validates_but_is_not_runtime_activation() -> None:
    value = attestation_chain()
    value.validate(
        evaluation_time=EVALUATION_TIME + timedelta(microseconds=3),
        manual_validation_approver_id="approver-v016",
    )
    assert value.approved


def test_review_and_approval_same_instant_is_rejected() -> None:
    changed = approval(approved_at=review().reviewed_at)
    value = attestation_chain(approval=changed)
    with pytest.raises(ProductionEquivalenceError, match="temporal"):
        value.validate(
            evaluation_time=EVALUATION_TIME + timedelta(microseconds=3),
            manual_validation_approver_id="approver-v016",
        )


@pytest.mark.parametrize(
    "role_change",
    [
        {"review": review(reviewer_id="equivalence-assessor")},
        {"approval": approval(approver_id="equivalence-reviewer")},
        {"approval": approval(approver_id="approver-v016")},
        {"approval": approval(approver_id="authorization-approver")},
    ],
)
def test_assessor_reviewer_approver_and_existing_roles_are_distinct(
    role_change: dict[str, object],
) -> None:
    value = attestation_chain(**role_change)
    with pytest.raises(ProductionEquivalenceError):
        value.validate(
            evaluation_time=EVALUATION_TIME + timedelta(microseconds=3),
            manual_validation_approver_id="approver-v016",
            protected_actor_ids=("authorization-approver",),
        )


def test_rejected_review_cannot_produce_approved_attestation() -> None:
    changed_review = review(review_result=EquivalenceReviewResult.REJECTED)
    changed_approval = approval(review_digest=changed_review.canonical_digest)
    value = attestation_chain(review=changed_review, approval=changed_approval)
    with pytest.raises(ProductionEquivalenceError, match="review_not_approved"):
        value.validate(
            evaluation_time=EVALUATION_TIME + timedelta(microseconds=3),
            manual_validation_approver_id="approver-v016",
        )


def test_successful_commit_consumes_all_replay_dimensions_atomically() -> None:
    store = TestEquivalenceAttestationStore()
    result = commit(store)
    snapshot = store.snapshot
    assert result.applied
    assert snapshot.committed_chain_count == 1
    assert attestation_chain().assessment.canonical_digest in snapshot.used_assessment_digests
    assert attestation_chain().review.canonical_digest in snapshot.used_review_digests
    assert attestation_chain().approval.canonical_digest in snapshot.used_approval_digests
    assert result.write_count == result.mutation_count == 0
    assert result.persistence_count == result.filesystem_count == result.database_count == 0
    assert result.transport_count == result.http_count == result.activation_count == 0


def test_successful_replay_is_rejected_without_state_change() -> None:
    store = TestEquivalenceAttestationStore()
    assert commit(store).applied
    before = store.snapshot
    result = commit(store)
    assert not result.applied
    assert result.reason_categories == (EquivalenceCommitReason.REPLAY,)
    assert store.snapshot == before


def test_commit_fault_consumes_no_used_state_and_retry_succeeds() -> None:
    store = TestEquivalenceAttestationStore()
    before = store.snapshot
    failed = commit(store, fail_commit=True)
    assert not failed.applied
    assert failed.reason_categories == (EquivalenceCommitReason.COMMIT_FAULT,)
    assert store.snapshot == before
    assert commit(store).applied


def test_old_manual_validation_approval_cannot_back_another_success() -> None:
    store = TestEquivalenceAttestationStore()
    assert commit(store).applied
    first = attestation_chain()
    second_request = replace(
        first.request,
        assessment_request_id="assessment-request-second",
    )
    second_assessment = replace(
        first.assessment,
        assessment_request_id=second_request.assessment_request_id,
        request_digest=second_request.canonical_digest,
    )
    second_review = replace(
        first.review,
        review_id="equivalence-review-second",
        assessment_digest=second_assessment.canonical_digest,
    )
    second_approval = replace(
        first.approval,
        approval_id="equivalence-approval-second",
        assessment_digest=second_assessment.canonical_digest,
        review_digest=second_review.canonical_digest,
    )
    second = replace(
        first,
        request=second_request,
        assessment=second_assessment,
        review=second_review,
        approval=second_approval,
    )
    result = commit(store, chain=second)
    assert not result.applied
    assert result.reason_categories == (EquivalenceCommitReason.REPLAY,)
