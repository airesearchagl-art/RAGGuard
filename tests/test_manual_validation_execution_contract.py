from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.compatibility import SemanticVersion
from ragguard.manual_validation_execution import (
    EvidenceCompleteness,
    ManualApprovalResult,
    ManualEvidenceKind,
    ManualExecutionResult,
    ManualReviewResult,
    ManualValidationApproval,
    ManualValidationChain,
    ManualValidationExecutionError,
    ManualValidationExecutionErrorCategory,
    ManualValidationExecutionEvidence,
    ManualValidationExecutionRequest,
    ManualValidationReview,
    TestManualValidationExecutionHarness,
    ValidationEnvironmentContract,
    ValidationFixtureKind,
    ValidationFixtureManifest,
)
from ragguard.manual_validation_plan import (
    REQUIRED_ABORT_CONDITIONS,
    REQUIRED_CLEANUP_CONDITIONS,
    REQUIRED_MANUAL_VALIDATION_CASES,
    ManualValidationPlan,
)


UTC = timezone.utc
DIGEST = "sha256:" + "a" * 64


def plan() -> ManualValidationPlan:
    return ManualValidationPlan.from_mapping(
        {
            "plan_id": "manual-plan-v016",
            "profile_id": "synthetic-profile",
            "profile_version": "1.2.3",
            "protocol_version": "1.0.0",
            "product_id": "product-fixture-alpha",
            "product_version": "2.3.4",
            "created_at": "2026-08-09T00:00:00Z",
            "execution_window_start": "2026-08-10T00:00:00Z",
            "execution_window_end": "2026-08-12T00:00:00Z",
            "profile_implementer_id": "implementer-v016",
            "validation_operator_id": "operator-v016",
            "evidence_reviewer_id": "reviewer-v016",
            "approver_id": "approver-v016",
            "registry_administrator_id": "registry-admin-v016",
            "required_case_ids": [value.value for value in REQUIRED_MANUAL_VALIDATION_CASES],
            "endpoint_boundary": {
                "category": "loopback",
                "approved_boundary_marker": "boundary-approved-isolated",
                "opaque_endpoint_reference": "endpoint-ref-7f3a9c21",
            },
            "data_boundary": {
                "synthetic_only": True,
                "no_customer_data": True,
                "no_production_data": True,
                "no_real_documents": True,
                "no_raw_payload_retention": True,
                "safe_summary_only": True,
            },
            "credential_boundary": {"credentials_prohibited": True},
            "abort_conditions": [value.value for value in REQUIRED_ABORT_CONDITIONS],
            "cleanup_conditions": [value.value for value in REQUIRED_CLEANUP_CONDITIONS],
            "synthetic_evidence_reference": {
                "reference_id": "synthetic-evidence-a17c0e01",
                "profile_id": "synthetic-profile",
                "profile_version": "1.2.3",
            },
        }
    )


def manifest() -> ValidationFixtureManifest:
    return ValidationFixtureManifest(
        fixture_manifest_id="fixture-manifest-v016",
        fixture_kind=ValidationFixtureKind.SYNTHETIC,
        fixture_version=SemanticVersion(1, 0, 0),
        test_case_ids=tuple(sorted(value.value for value in REQUIRED_MANUAL_VALIDATION_CASES)),
        synthetic_data_digest=DIGEST,
        prohibited_real_data_assertion=True,
        prohibited_network_assertion=True,
    )


def environment(**changes: bool) -> ValidationEnvironmentContract:
    values = {
        "offline_required": True,
        "network_allowed": False,
        "filesystem_write_allowed": False,
        "subprocess_allowed": False,
        "external_api_allowed": False,
        "real_data_allowed": False,
        "credential_allowed": False,
    }
    values.update(changes)
    return ValidationEnvironmentContract(
        environment_id="environment-v016",
        environment_version=SemanticVersion(1, 0, 0),
        **values,
    )


def request(**changes: object) -> ManualValidationExecutionRequest:
    value: dict[str, object] = {
        "execution_request_id": "execution-request-v016",
        "validation_plan_digest": plan().canonical_digest,
        "profile_id": "synthetic-profile",
        "profile_version": SemanticVersion(1, 2, 3),
        "product_id": "product-fixture-alpha",
        "product_version": SemanticVersion(2, 3, 4),
        "protocol_version": SemanticVersion(1, 0, 0),
        "requested_at": datetime(2026, 8, 10, tzinfo=UTC),
        "requested_by": "requester-v016",
        "execution_operator_id": "operator-v016",
        "expected_fixture_manifest_digest": manifest().canonical_digest,
        "expected_test_case_set_digest": manifest().test_case_set_digest,
        "expected_environment_contract_digest": environment().canonical_digest,
    }
    value.update(changes)
    return ManualValidationExecutionRequest(**value)  # type: ignore[arg-type]


def execute(**changes: object):
    values: dict[str, object] = {
        "request": request(),
        "plan": plan(),
        "fixture_manifest": manifest(),
        "environment": environment(),
        "execution_id": "execution-v016",
        "started_at": datetime(2026, 8, 10, 1, tzinfo=UTC),
        "completed_at": datetime(2026, 8, 10, 2, tzinfo=UTC),
        "case_results": {value.value: True for value in REQUIRED_MANUAL_VALIDATION_CASES},
        "execution_summary_digest": "sha256:" + "b" * 64,
    }
    values.update(changes)
    harness = TestManualValidationExecutionHarness()
    return harness, harness.execute(**values)  # type: ignore[arg-type]


def chain() -> ManualValidationChain:
    _, outcome = execute()
    assert outcome.record is not None
    record = outcome.record
    evidence = ManualValidationExecutionEvidence(
        evidence_id="execution-evidence-v016",
        execution_record_digest=record.canonical_digest,
        validation_plan_digest=plan().canonical_digest,
        fixture_manifest_digest=manifest().canonical_digest,
        environment_contract_digest=environment().canonical_digest,
        evidence_created_at=record.completed_at + timedelta(microseconds=1),
        created_by="evidence-creator-v016",
        result=ManualExecutionResult.PASSED,
        completeness_state=EvidenceCompleteness.COMPLETE,
        evidence_kind=ManualEvidenceKind.SYNTHETIC_EXECUTION,
    )
    review = ManualValidationReview(
        review_id="review-v016",
        evidence_digest=evidence.canonical_digest,
        reviewed_at=evidence.evidence_created_at + timedelta(microseconds=1),
        reviewer_id="reviewer-v016",
        review_result=ManualReviewResult.APPROVED,
        findings_digest="sha256:" + "c" * 64,
    )
    approval = ManualValidationApproval(
        approval_id="approval-v016",
        evidence_digest=evidence.canonical_digest,
        review_digest=review.canonical_digest,
        approved_at=review.reviewed_at + timedelta(microseconds=1),
        approver_id="approver-v016",
        approval_result=ManualApprovalResult.APPROVED,
    )
    return ManualValidationChain(
        request(), manifest(), environment(), record, evidence, review, approval
    )


def test_contracts_are_immutable_and_digest_is_deterministic() -> None:
    value = request()
    assert value.canonical_digest == request().canonical_digest
    with pytest.raises(FrozenInstanceError):
        value.requested_by = "changed"  # type: ignore[misc]


def test_one_microsecond_changes_digest_and_offset_equivalence_does_not() -> None:
    value = request()
    changed = replace(
        value, requested_at=value.requested_at + timedelta(microseconds=1)
    )
    equivalent = replace(
        value,
        requested_at=value.requested_at.astimezone(timezone(timedelta(hours=9))),
    )
    assert changed.canonical_digest != value.canonical_digest
    assert equivalent.canonical_digest == value.canonical_digest


@pytest.mark.parametrize(
    "change",
    [
        {"use_current_alias": True},
        {"use_latest_alias": True},
        {"allow_fallback": True},
        {"allow_version_inference": True},
        {"allow_hidden_defaults": True},
    ],
)
def test_alias_fallback_inference_and_hidden_defaults_are_rejected(
    change: dict[str, object],
) -> None:
    with pytest.raises(ManualValidationExecutionError):
        request(**change)


@pytest.mark.parametrize(
    "change",
    [
        {"network_allowed": True},
        {"filesystem_write_allowed": True},
        {"subprocess_allowed": True},
        {"external_api_allowed": True},
        {"real_data_allowed": True},
        {"credential_allowed": True},
        {"offline_required": False},
    ],
)
def test_environment_is_strictly_offline(change: dict[str, bool]) -> None:
    with pytest.raises(ManualValidationExecutionError) as error:
        environment(**change)
    assert error.value.category is ManualValidationExecutionErrorCategory.ENVIRONMENT_UNSAFE


def test_complete_execution_passes_and_has_zero_external_side_effects() -> None:
    harness, outcome = execute()
    assert outcome.applied and outcome.record is not None
    assert outcome.record.result is ManualExecutionResult.PASSED
    assert len(harness.records) == 1
    assert (
        outcome.registry_write_count,
        outcome.persistence_write_count,
        outcome.filesystem_write_count,
        outcome.database_write_count,
        outcome.network_count,
        outcome.http_count,
        outcome.activation_count,
    ) == (0, 0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize("result", [False, None])
def test_failed_or_skipped_required_case_is_not_passed(result: bool | None) -> None:
    results = {value.value: True for value in REQUIRED_MANUAL_VALIDATION_CASES}
    results[next(iter(results))] = result
    _, outcome = execute(case_results=results)
    assert outcome.record is not None
    assert outcome.record.result is not ManualExecutionResult.PASSED


def test_missing_case_is_rejected_without_consuming_request() -> None:
    harness = TestManualValidationExecutionHarness()
    results = {value.value: True for value in REQUIRED_MANUAL_VALIDATION_CASES}
    results.pop(next(iter(results)))
    kwargs = dict(
        request=request(), plan=plan(), fixture_manifest=manifest(), environment=environment(),
        execution_id="execution-v016", started_at=datetime(2026, 8, 10, 1, tzinfo=UTC),
        completed_at=datetime(2026, 8, 10, 2, tzinfo=UTC), case_results=results,
        execution_summary_digest="sha256:" + "b" * 64,
    )
    failed = harness.execute(**kwargs)
    assert not failed.applied and not harness.records
    kwargs["case_results"] = {value.value: True for value in REQUIRED_MANUAL_VALIDATION_CASES}
    assert harness.execute(**kwargs).applied


def test_commit_fault_is_atomic_and_retryable() -> None:
    harness = TestManualValidationExecutionHarness()
    kwargs = dict(
        request=request(), plan=plan(), fixture_manifest=manifest(), environment=environment(),
        execution_id="execution-v016", started_at=datetime(2026, 8, 10, 1, tzinfo=UTC),
        completed_at=datetime(2026, 8, 10, 2, tzinfo=UTC),
        case_results={value.value: True for value in REQUIRED_MANUAL_VALIDATION_CASES},
        execution_summary_digest="sha256:" + "b" * 64,
    )
    assert not harness.execute(**kwargs, commit_fault=True).applied
    assert harness.records == ()
    assert harness.execute(**kwargs).applied
    assert not harness.execute(**kwargs).applied


def test_full_chain_exact_binding_and_role_separation() -> None:
    value = chain()
    assert value.approval is not None
    value.validate(plan=plan(), evaluation_time=value.approval.approved_at)
    assert value.approved


def test_review_or_approval_tampering_is_rejected() -> None:
    value = chain()
    assert value.review is not None and value.approval is not None
    forged_review = replace(value.review, evidence_digest=DIGEST)
    with pytest.raises(ManualValidationExecutionError):
        replace(value, review=forged_review).validate(
            plan=plan(), evaluation_time=value.approval.approved_at
        )
    conflicting = replace(value.approval, approver_id=value.review.reviewer_id)
    with pytest.raises(ManualValidationExecutionError):
        replace(value, approval=conflicting).validate(
            plan=plan(), evaluation_time=conflicting.approved_at
        )


def test_review_and_approval_roles_are_bound_to_plan() -> None:
    value = chain()
    assert value.review is not None and value.approval is not None
    wrong_reviewer = replace(value.review, reviewer_id="reviewer-v016-other")
    with pytest.raises(ManualValidationExecutionError):
        replace(value, review=wrong_reviewer).validate(
            plan=plan(), evaluation_time=value.approval.approved_at
        )
    wrong_approver = replace(value.approval, approver_id="approver-v016-other")
    with pytest.raises(ManualValidationExecutionError):
        replace(value, approval=wrong_approver).validate(
            plan=plan(), evaluation_time=wrong_approver.approved_at
        )


def test_approval_must_strictly_follow_review() -> None:
    value = chain()
    assert value.review is not None and value.approval is not None
    same_time = replace(value.approval, approved_at=value.review.reviewed_at)
    with pytest.raises(ManualValidationExecutionError):
        replace(value, approval=same_time).validate(
            plan=plan(), evaluation_time=same_time.approved_at
        )


def test_future_and_stale_evidence_are_rejected() -> None:
    value = chain()
    assert value.approval is not None
    with pytest.raises(ManualValidationExecutionError):
        value.validate(
            plan=plan(),
            evaluation_time=value.approval.approved_at - timedelta(microseconds=1),
        )
    with pytest.raises(ManualValidationExecutionError) as stale:
        value.validate(
            plan=plan(),
            evaluation_time=value.evidence.evidence_created_at + timedelta(days=91),
        )
    assert stale.value.category is ManualValidationExecutionErrorCategory.STALE


def test_safe_repr_does_not_expose_fixture_data() -> None:
    _, outcome = execute()
    text = repr(outcome.safe_summary).lower()
    assert all(
        term not in text
        for term in ("authorization:", "cookie", "endpoint", "payload")
    )
