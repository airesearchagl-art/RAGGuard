from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from ragguard.manual_validation_execution import (
    ManualApprovalResult,
    ManualReviewResult,
    ManualValidationExecutionErrorCategory,
    TestManualValidationChainStore,
)
from tests.test_manual_validation_execution_contract import chain, plan


def test_successful_chain_commit_consumes_all_replay_keys_once() -> None:
    value = chain()
    assert value.approval is not None
    store = TestManualValidationChainStore()
    first = store.commit(value, plan=plan(), evaluation_time=value.approval.approved_at)
    second = store.commit(value, plan=plan(), evaluation_time=value.approval.approved_at)
    assert first.applied
    assert not second.applied
    assert second.reason_categories == (ManualValidationExecutionErrorCategory.REPLAY,)
    assert store.committed_chain_count == 1


def test_commit_fault_consumes_nothing_and_retry_succeeds() -> None:
    value = chain()
    assert value.approval is not None
    store = TestManualValidationChainStore()
    before = store.snapshot
    failed = store.commit(
        value,
        plan=plan(),
        evaluation_time=value.approval.approved_at,
        commit_fault=True,
    )
    assert not failed.applied
    assert store.snapshot == before
    assert store.commit(
        value, plan=plan(), evaluation_time=value.approval.approved_at
    ).applied


def test_rejected_review_does_not_consume_chain() -> None:
    value = chain()
    assert value.review is not None and value.approval is not None
    rejected_review = replace(value.review, review_result=ManualReviewResult.REJECTED)
    rejected_approval = replace(
        value.approval,
        review_digest=rejected_review.canonical_digest,
        approval_result=ManualApprovalResult.REJECTED,
    )
    rejected = replace(value, review=rejected_review, approval=rejected_approval)
    store = TestManualValidationChainStore()
    result = store.commit(
        rejected,
        plan=plan(),
        evaluation_time=rejected_approval.approved_at,
    )
    assert not result.applied
    assert store.committed_chain_count == 0


def test_evidence_digest_reuse_is_rejected_across_successful_chains() -> None:
    first = chain()
    assert first.approval is not None
    store = TestManualValidationChainStore()
    assert store.commit(first, plan=plan(), evaluation_time=first.approval.approved_at).applied
    assert first.review is not None
    new_review = replace(
        first.review,
        review_id="review-v016-b",
        reviewed_at=first.review.reviewed_at + timedelta(seconds=1),
    )
    new_approval = replace(
        first.approval,
        approval_id="approval-v016-b",
        review_digest=new_review.canonical_digest,
        approved_at=new_review.reviewed_at + timedelta(microseconds=1),
    )
    replay = replace(first, review=new_review, approval=new_approval)
    result = store.commit(replay, plan=plan(), evaluation_time=new_approval.approved_at)
    assert not result.applied
    assert result.reason_categories == (ManualValidationExecutionErrorCategory.REPLAY,)


def test_denial_side_effect_counts_are_zero() -> None:
    value = chain()
    assert value.approval is not None
    store = TestManualValidationChainStore()
    forged = replace(
        value,
        approval=replace(value.approval, review_digest="sha256:" + "f" * 64),
    )
    result = store.commit(forged, plan=plan(), evaluation_time=value.approval.approved_at)
    assert not result.applied
    assert (
        result.registry_write_count,
        result.mutation_count,
        result.persistence_write_count,
        result.filesystem_write_count,
        result.database_write_count,
        result.network_count,
        result.http_count,
        result.activation_count,
    ) == (0, 0, 0, 0, 0, 0, 0, 0)
