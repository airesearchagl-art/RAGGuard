from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.approval_workflow import (
    ApprovalWorkflowStage,
    SyntheticApprovalWorkflowInput,
    SyntheticApprovalWorkflowResult,
    SyntheticCaseEvidence,
    build_all_pass_synthetic_input,
    build_synthetic_approval_metadata,
    build_synthetic_validation_report,
    evaluate_synthetic_approval_decision,
    run_synthetic_approval_workflow,
    validate_synthetic_validation_report,
)
from ragguard.compatibility import (
    CompatibilityErrorCategory,
    SemanticVersion,
)
from ragguard.production_registry import (
    RegistryEventCategory,
    RegistryKind,
    RegistryStatus,
)
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalRestrictions,
    ProfileMaturity,
    SupportedProductVersionRange,
)
from ragguard.retrieval import RetrievalAdapterError
from ragguard.validation_report import (
    VALIDATION_REPORT_CASE_IDS,
    ValidationCaseOutcome,
    ValidationCheckResult,
    ValidationOverallStatus,
)


NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


def valid_input() -> SyntheticApprovalWorkflowInput:
    return build_all_pass_synthetic_input(evaluation_time=NOW)


def failed_case(
    case: SyntheticCaseEvidence,
    *,
    category: str = "health_invalid",
) -> SyntheticCaseEvidence:
    return replace(
        case,
        outcome=ValidationCaseOutcome.FAILED,
        safe_error_category=category,
    )


def input_mapping(
    value: SyntheticApprovalWorkflowInput,
) -> dict[str, object]:
    restriction = None
    if value.restrictions is not None:
        restriction = {
            "maximum_top_k": value.restrictions.maximum_top_k,
            "score_disabled": value.restrictions.score_disabled,
            "title_disabled": value.restrictions.title_disabled,
            "matched_keywords_disabled": (
                value.restrictions.matched_keywords_disabled
            ),
            "query_id_echo_required": (
                value.restrictions.query_id_echo_required
            ),
            "supported_minor_versions": list(
                value.restrictions.supported_minor_versions
            ),
            "expires_at": (
                value.restrictions.expires_at.isoformat()
                if value.restrictions.expires_at is not None
                else None
            ),
        }
    version_range = value.supported_product_version_range
    return {
        "profile_id": value.profile_id,
        "profile_version": str(value.profile_version),
        "protocol_version": str(value.protocol_version),
        "normalized_product_version": str(
            value.normalized_product_version
        ),
        "maturity": value.maturity.value,
        "validation_record_id": value.validation_record_id,
        "approval_record_id": value.approval_record_id,
        "reviewer_id": value.reviewer_id,
        "approver_id": value.approver_id,
        "case_outcomes": [
            {
                "case_id": case.case_id,
                "outcome": case.outcome.value,
                "safe_error_category": case.safe_error_category,
            }
            for case in value.case_outcomes
        ],
        "required_capabilities_result": (
            value.required_capabilities_result.value
        ),
        "optional_capabilities_result": (
            value.optional_capabilities_result.value
        ),
        "score_semantics_result": value.score_semantics_result.value,
        "source_policy_result": value.source_policy_result.value,
        "transport_boundary_result": (
            value.transport_boundary_result.value
        ),
        "non_disclosure_result": value.non_disclosure_result.value,
        "approved_capabilities": list(value.approved_capabilities),
        "approved_score_semantics": value.approved_score_semantics.value,
        "approved_source_identifier_policy": (
            value.approved_source_identifier_policy.value
        ),
        "supported_product_version_range": {
            "minimum_version": str(version_range.minimum_version),
            "maximum_version": (
                str(version_range.maximum_version)
                if version_range.maximum_version is not None
                else None
            ),
            "open_ended": version_range.open_ended,
        },
        "restrictions": restriction,
        "validation_started_at": value.validation_started_at.isoformat(),
        "validation_completed_at": (
            value.validation_completed_at.isoformat()
        ),
        "validation_expires_at": (
            value.validation_expires_at.isoformat()
            if value.validation_expires_at is not None
            else None
        ),
        "validation_status": value.validation_status.value,
        "revalidation_required": value.revalidation_required,
        "approval_at": value.approval_at.isoformat(),
        "approval_expires_at": (
            value.approval_expires_at.isoformat()
            if value.approval_expires_at is not None
            else None
        ),
        "evaluation_time": value.evaluation_time.isoformat(),
        "registry_kind": value.registry_kind.value,
        "registry_status_before_resolve": (
            value.registry_status_before_resolve.value
        ),
    }


def assert_failure(
    result: SyntheticApprovalWorkflowResult,
    category: CompatibilityErrorCategory,
) -> None:
    assert result.safe_error_category == category.value
    assert not result.exact_resolve_success
    assert RegistryEventCategory.RESOLUTION_SUCCEEDED.value not in (
        result.event_categories
    )


def test_all_pass_builder_is_product_neutral_and_complete() -> None:
    value = valid_input()
    assert value.registry_kind is RegistryKind.TEST
    assert value.maturity is ProfileMaturity.APPROVED
    assert tuple(case.case_id for case in value.case_outcomes) == tuple(
        sorted(VALIDATION_REPORT_CASE_IDS)
    )
    assert all(
        case.outcome is ValidationCaseOutcome.PASSED
        for case in value.case_outcomes
    )
    assert value.evaluation_time is NOW
    assert "endpoint" not in repr(value).lower()
    assert "query" not in repr(value).lower()


def test_full_successful_workflow_runs_every_stage() -> None:
    result = run_synthetic_approval_workflow(valid_input())
    assert result.validation_status == "passed"
    assert result.approval_decision == "approved"
    assert result.registration_eligible
    assert result.registry_status == "active"
    assert result.exact_resolve_success
    assert not result.restriction_present
    assert not result.revalidation_required
    assert result.safe_error_category is None
    assert result.completed_stage == ApprovalWorkflowStage.RESULT_BUILT.value
    assert result.case_counts == (
        ("passed", 17),
        ("failed", 0),
        ("skipped", 0),
        ("not_applicable", 0),
    )
    assert result.event_categories == (
        RegistryEventCategory.REGISTERED.value,
        RegistryEventCategory.RESOLUTION_SUCCEEDED.value,
    )


def test_approved_with_restrictions_workflow() -> None:
    value = replace(
        valid_input(),
        restrictions=ApprovalRestrictions(
            maximum_top_k=5,
            supported_minor_versions=("1.3",),
        ),
    )
    result = run_synthetic_approval_workflow(value)
    assert result.approval_decision == "approved_with_restrictions"
    assert result.restriction_present
    assert result.exact_resolve_success
    assert result.safe_error_category is None


def test_each_stage_is_explicit_and_composable() -> None:
    value = valid_input()
    report = build_synthetic_validation_report(value)
    validate_synthetic_validation_report(value, report)
    decision = evaluate_synthetic_approval_decision(value, report)
    approval = build_synthetic_approval_metadata(value, report, decision)
    assert report.overall_status is ValidationOverallStatus.PASSED
    assert decision is ApprovalDecision.APPROVED
    assert approval.validation_record_id == report.validation_record_id


def test_deterministic_replay_is_identical() -> None:
    value = valid_input()
    first = run_synthetic_approval_workflow(value)
    second = run_synthetic_approval_workflow(value)
    assert first == second
    assert first.as_mapping() == second.as_mapping()
    assert first.event_categories == second.event_categories
    assert first.case_counts == second.case_counts


def test_input_and_result_are_immutable_and_bounded() -> None:
    value = valid_input()
    result = run_synthetic_approval_workflow(value)
    with pytest.raises(FrozenInstanceError):
        value.profile_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.registry_status = "changed"  # type: ignore[misc]
    mapping = result.as_mapping()
    with pytest.raises(TypeError):
        mapping["profile_id"] = "changed"  # type: ignore[index]
    rendered = repr(value) + repr(result) + repr(mapping)
    for secret in (
        value.reviewer_id,
        value.approver_id,
        value.approval_record_id,
        value.validation_record_id,
        "private-endpoint",
        "private-query",
        "C:/private/path",
        "credential-value",
    ):
        assert secret not in rendered


def test_input_mapping_round_trip_and_unknown_field_rejection() -> None:
    raw = input_mapping(valid_input())
    restored = SyntheticApprovalWorkflowInput.from_mapping(raw)
    assert restored == valid_input()
    for field, secret in (
        ("endpoint", "private-endpoint"),
        ("query", "private-query"),
        ("path", "C:/private/path"),
        ("token", "credential-value"),
    ):
        invalid = dict(raw)
        invalid[field] = secret
        with pytest.raises(RetrievalAdapterError) as caught:
            SyntheticApprovalWorkflowInput.from_mapping(invalid)
        assert str(caught.value) == "registry_metadata_invalid"
        assert secret not in str(caught.value)


def test_unknown_case_and_unknown_error_category_fail_closed() -> None:
    for raw in (
        {
            "case_id": "unknown_case",
            "outcome": "passed",
            "safe_error_category": None,
        },
        {
            "case_id": "health_valid",
            "outcome": "failed",
            "safe_error_category": "private_error",
        },
    ):
        with pytest.raises(RetrievalAdapterError) as caught:
            SyntheticCaseEvidence.from_mapping(raw)
        assert str(caught.value) == "registry_metadata_invalid"

    success = run_synthetic_approval_workflow(valid_input())
    with pytest.raises(RetrievalAdapterError) as caught:
        replace(success, safe_error_category="private_error")
    assert str(caught.value) == "registry_metadata_invalid"


def test_decision_cannot_be_forged_by_skipping_evaluation() -> None:
    value = valid_input()
    cases = (failed_case(value.case_outcomes[0]), *value.case_outcomes[1:])
    failed_input = replace(
        value,
        case_outcomes=cases,
        validation_status=ValidationOverallStatus.FAILED,
    )
    report = build_synthetic_validation_report(failed_input)
    with pytest.raises(RetrievalAdapterError) as caught:
        build_synthetic_approval_metadata(
            failed_input,
            report,
            ApprovalDecision.APPROVED,
        )
    assert str(caught.value) == "registry_metadata_invalid"


@pytest.mark.parametrize("kind", ["missing", "duplicate"])
def test_missing_or_duplicate_required_case_stops_before_decision(
    kind: str,
) -> None:
    value = valid_input()
    cases = (
        value.case_outcomes[:-1]
        if kind == "missing"
        else (*value.case_outcomes, value.case_outcomes[-1])
    )
    result = run_synthetic_approval_workflow(
        replace(value, case_outcomes=cases)
    )
    assert_failure(
        result, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
    )
    assert result.completed_stage == ApprovalWorkflowStage.INPUT_VALIDATED.value
    assert result.approval_decision == "unavailable"
    assert not result.registration_eligible
    assert result.event_categories == ()


def test_failed_required_case_is_never_approved() -> None:
    value = valid_input()
    cases = (failed_case(value.case_outcomes[0]), *value.case_outcomes[1:])
    result = run_synthetic_approval_workflow(
        replace(
            value,
            case_outcomes=cases,
            validation_status=ValidationOverallStatus.FAILED,
        )
    )
    assert_failure(result, CompatibilityErrorCategory.PROFILE_UNAPPROVED)
    assert result.validation_status == "failed"
    assert result.approval_decision == "rejected"
    assert not result.registration_eligible


@pytest.mark.parametrize(
    "field",
    [
        "required_capabilities_result",
        "score_semantics_result",
        "source_policy_result",
        "transport_boundary_result",
        "non_disclosure_result",
    ],
)
def test_unsafe_required_result_fails_closed(field: str) -> None:
    value = replace(
        valid_input(),
        validation_status=ValidationOverallStatus.FAILED,
        **{field: ValidationCheckResult.FAILED},
    )
    result = run_synthetic_approval_workflow(value)
    assert_failure(result, CompatibilityErrorCategory.PROFILE_UNAPPROVED)
    assert result.approval_decision == "rejected"


def test_cleanup_failure_fails_closed() -> None:
    value = valid_input()
    cases = tuple(
        (
            failed_case(case, category="response_mapping_error")
            if case.case_id == "close_cleanup_valid"
            else case
        )
        for case in value.case_outcomes
    )
    result = run_synthetic_approval_workflow(
        replace(
            value,
            case_outcomes=cases,
            validation_status=ValidationOverallStatus.FAILED,
        )
    )
    assert_failure(result, CompatibilityErrorCategory.PROFILE_UNAPPROVED)


def test_expired_validation_returns_needs_revalidation() -> None:
    value = valid_input()
    result = run_synthetic_approval_workflow(
        replace(value, validation_expires_at=NOW)
    )
    assert_failure(
        result, CompatibilityErrorCategory.PROFILE_VALIDATION_EXPIRED
    )
    assert result.approval_decision == "needs_revalidation"
    assert not result.registration_eligible


def test_explicit_revalidation_stops_before_registration() -> None:
    value = valid_input()
    result = run_synthetic_approval_workflow(
        replace(
            value,
            validation_status=ValidationOverallStatus.EXPIRED,
            revalidation_required=True,
        )
    )
    assert_failure(result, CompatibilityErrorCategory.REVALIDATION_REQUIRED)
    assert result.approval_decision == "needs_revalidation"


def test_expired_approval_is_rejected() -> None:
    result = run_synthetic_approval_workflow(
        replace(valid_input(), approval_expires_at=NOW)
    )
    assert_failure(result, CompatibilityErrorCategory.APPROVAL_EXPIRED)
    assert result.approval_decision == "approved"


@pytest.mark.parametrize(
    "maturity",
    [
        ProfileMaturity.DRAFT,
        ProfileMaturity.SYNTHETIC_VALIDATED,
        ProfileMaturity.MANUALLY_VALIDATED,
        ProfileMaturity.DEPRECATED,
        ProfileMaturity.REVOKED,
    ],
)
def test_nonapproved_maturity_never_registers(
    maturity: ProfileMaturity,
) -> None:
    result = run_synthetic_approval_workflow(
        replace(valid_input(), maturity=maturity)
    )
    assert_failure(result, CompatibilityErrorCategory.PROFILE_UNAPPROVED)
    assert result.approval_decision == "rejected"


def test_reviewer_approver_role_collision_stops_metadata_build() -> None:
    value = valid_input()
    result = run_synthetic_approval_workflow(
        replace(value, approver_id=value.reviewer_id)
    )
    assert_failure(
        result, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
    )
    assert result.completed_stage == (
        ApprovalWorkflowStage.APPROVAL_DECISION_EVALUATED.value
    )
    assert not result.registration_eligible


def test_profile_version_and_record_identity_mismatch_fail_closed() -> None:
    value = valid_input()
    report = build_synthetic_validation_report(value)
    mismatches = (
        replace(report, profile_id="other-profile"),
        replace(report, profile_version=SemanticVersion.parse("2.0.0")),
        replace(report, protocol_version=SemanticVersion.parse("2.0.0")),
        replace(report, validation_record_id="other-validation"),
    )
    for mismatch in mismatches:
        with pytest.raises(RetrievalAdapterError) as caught:
            validate_synthetic_validation_report(value, mismatch)
        assert str(caught.value) == "registry_metadata_invalid"


def test_unsupported_product_version_rejects_exact_resolution() -> None:
    value = replace(
        valid_input(),
        supported_product_version_range=SupportedProductVersionRange(
            minimum_version=SemanticVersion.parse("1.0.0"),
            maximum_version=SemanticVersion.parse("1.2.9"),
            open_ended=False,
        ),
    )
    result = run_synthetic_approval_workflow(value)
    assert_failure(
        result, CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED
    )
    assert result.registration_eligible
    assert result.completed_stage == (
        ApprovalWorkflowStage.REGISTRY_REGISTERED.value
    )


def test_restriction_contradiction_stops_metadata_build() -> None:
    value = valid_input()
    result = run_synthetic_approval_workflow(
        replace(
            value,
            approved_capabilities=tuple(
                sorted((*value.approved_capabilities, "score"))
            ),
            restrictions=ApprovalRestrictions(score_disabled=True),
        )
    )
    assert_failure(
        result, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID
    )
    assert result.completed_stage == (
        ApprovalWorkflowStage.APPROVAL_DECISION_EVALUATED.value
    )


def test_production_registry_kind_is_rejected_before_write() -> None:
    result = run_synthetic_approval_workflow(
        replace(valid_input(), registry_kind=RegistryKind.PRODUCTION)
    )
    assert_failure(
        result, CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
    )
    assert not result.registration_eligible
    assert result.registry_status == "unavailable"
    assert result.event_categories == ()


@pytest.mark.parametrize(
    ("status", "category", "event"),
    [
        (
            RegistryStatus.SUSPENDED,
            CompatibilityErrorCategory.PROFILE_SUSPENDED,
            RegistryEventCategory.SUSPENDED,
        ),
        (
            RegistryStatus.DEPRECATED,
            CompatibilityErrorCategory.PROFILE_DEPRECATED,
            RegistryEventCategory.DEPRECATED,
        ),
        (
            RegistryStatus.REVOKED,
            CompatibilityErrorCategory.PROFILE_REVOKED,
            RegistryEventCategory.REVOKED,
        ),
    ],
)
def test_inactive_registry_status_rejects_resolution(
    status: RegistryStatus,
    category: CompatibilityErrorCategory,
    event: RegistryEventCategory,
) -> None:
    result = run_synthetic_approval_workflow(
        replace(valid_input(), registry_status_before_resolve=status)
    )
    assert_failure(result, category)
    assert result.registration_eligible
    assert result.registry_status == status.value
    assert result.event_categories == (
        RegistryEventCategory.REGISTERED.value,
        event.value,
        RegistryEventCategory.RESOLUTION_REJECTED.value,
    )


def test_partial_success_is_not_reported_as_approved_completion() -> None:
    value = valid_input()
    result = run_synthetic_approval_workflow(
        replace(
            value,
            case_outcomes=(
                failed_case(value.case_outcomes[0]),
                *value.case_outcomes[1:],
            ),
            validation_status=ValidationOverallStatus.FAILED,
        )
    )
    assert result.approval_decision == "rejected"
    assert not result.registration_eligible
    assert not result.exact_resolve_success
    assert result.completed_stage != ApprovalWorkflowStage.RESULT_BUILT.value


def test_no_hidden_clock_changes_result() -> None:
    value = valid_input()
    first = run_synthetic_approval_workflow(value)
    shifted = replace(
        value,
        evaluation_time=value.evaluation_time + timedelta(days=31),
    )
    second = run_synthetic_approval_workflow(shifted)
    assert first.exact_resolve_success
    assert second.approval_decision == "needs_revalidation"
    assert second.safe_error_category == "profile_validation_expired"
