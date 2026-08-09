from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.authorization_activation import (
    ActivationEvaluationResult,
    ActivationReason,
    evaluate_activation_request,
)
from ragguard.production_boundary import (
    CompatibilityEvidenceKind,
    ManualValidationState,
)
from ragguard.production_registry import RegistryStatus
from tests.test_authorization_activation_evaluator import activation_context


def evaluate_chain(*, request_changes=None, evidence_changes=None, snapshot=None):
    request_changes = {} if request_changes is None else request_changes
    evidence_changes = {} if evidence_changes is None else evidence_changes
    entry, evidence, candidate, record, request, evaluation_time = activation_context(
        **evidence_changes
    )
    request = replace(request, **request_changes)
    registry_snapshot = (
        (entry.canonical_digest,) if snapshot is None else snapshot
    )
    return evaluate_activation_request(
        request,
        record,
        candidate,
        evidence,
        registry_snapshot,
        evaluation_time,
    )


def assert_denial_has_no_side_effects(result) -> None:
    assert (
        result.write_count,
        result.mutation_count,
        result.transport_count,
        result.http_count,
        result.filesystem_write_count,
        result.database_write_count,
        result.persistence_write_count,
        result.runtime_activation_count,
    ) == (0, 0, 0, 0, 0, 0, 0, 0)


def test_valid_fixture_stops_at_activation_review() -> None:
    result = evaluate_chain()
    assert result.result is ActivationEvaluationResult.NEEDS_ACTIVATION_REVIEW
    assert_denial_has_no_side_effects(result)


def test_approved_review_stops_at_commit_plan() -> None:
    result = evaluate_chain(request_changes={"activation_review_approved": True})
    assert result.result is ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT
    assert result.commit_plan is not None
    assert result.runtime_activation_count == 0


def test_synthetic_fixture_never_reaches_commit_plan() -> None:
    result = evaluate_chain(
        evidence_changes={
            "compatibility_evidence_kind": CompatibilityEvidenceKind.SYNTHETIC_ONLY,
            "manual_validation_state": ManualValidationState.NOT_PERFORMED,
        },
        request_changes={"activation_review_approved": True},
    )
    assert result.result is ActivationEvaluationResult.NEEDS_MANUAL_VALIDATION
    assert result.commit_plan is None
    assert_denial_has_no_side_effects(result)


@pytest.mark.parametrize(
    "status",
    [RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED, RegistryStatus.REVOKED],
)
def test_inactive_lifecycle_fails_closed(status: RegistryStatus) -> None:
    result = evaluate_chain(
        request_changes={
            "expected_lifecycle_status": status,
            "activation_review_approved": True,
        }
    )
    assert result.result is ActivationEvaluationResult.INELIGIBLE
    assert_denial_has_no_side_effects(result)


def test_replaced_predecessor_fails_closed() -> None:
    result = evaluate_chain(snapshot=("sha256:" + "9" * 64,))
    assert result.result is ActivationEvaluationResult.INELIGIBLE
    assert ActivationReason.REPLACED_PREDECESSOR in result.reason_categories
    assert_denial_has_no_side_effects(result)


def test_future_metadata_fails_closed() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    future = replace(
        request,
        activation_requested_at=evaluation_time + timedelta(microseconds=1),
    )
    result = evaluate_activation_request(
        future,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )
    assert result.result is ActivationEvaluationResult.INELIGIBLE
    assert_denial_has_no_side_effects(result)


def test_digest_tampering_fails_closed() -> None:
    result = evaluate_chain(
        request_changes={"persisted_record_digest": "sha256:" + "8" * 64}
    )
    assert result.result is ActivationEvaluationResult.INELIGIBLE
    assert_denial_has_no_side_effects(result)


def test_role_conflict_fails_closed() -> None:
    result = evaluate_chain(
        request_changes={"activation_reviewer_id": "authorization-approver"}
    )
    assert result.result is ActivationEvaluationResult.INELIGIBLE
    assert_denial_has_no_side_effects(result)


def test_no_runtime_or_external_io_api_is_exposed() -> None:
    import ragguard.authorization_activation as module

    names = set(dir(module))
    assert "activate" not in names
    assert "open" not in names
    assert "connect" not in names
    assert "request" not in names
