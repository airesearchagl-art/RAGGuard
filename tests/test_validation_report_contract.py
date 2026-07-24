from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    SemanticVersion,
)
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalMetadata,
    ProfileMaturity,
)
from ragguard.retrieval import RetrievalAdapterError
from ragguard.validation_report import (
    MAX_VALIDATION_DURATION_MS,
    MAX_VALIDATION_RESULT_COUNT,
    VALIDATION_REPORT_CASE_IDS,
    ValidationCaseOutcome,
    ValidationCaseResult,
    ValidationCheckResult,
    ValidationEnvironmentClass,
    ValidationOverallStatus,
    ValidationReport,
    ValidationType,
    evaluate_approval_decision,
    required_validation_case_ids,
    summarize_validation_report,
)


NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)
PROFILE_VERSION = SemanticVersion.parse("1.0.0")
REQUIRED_CAPABILITIES = sorted(
    {
        "retrieval",
        "bounded_top_k",
        "deterministic_result_schema",
        "safe_source_identifier",
        "response_size_compliance",
    }
)


def case_data(
    case_id: str,
    *,
    required: bool,
    outcome: str = "passed",
    safe_error_category: str | None = None,
    **overrides: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "case_id": case_id,
        "outcome": outcome,
        "safe_error_category": safe_error_category,
        "bounded_duration_ms": 10,
        "result_count": 1,
        "required": required,
        "notes_code": "none",
    }
    value.update(overrides)
    return value


def case_set(validation_type: str = "manual") -> list[dict[str, object]]:
    required_ids = required_validation_case_ids(validation_type)
    return [
        case_data(case_id, required=True)
        for case_id in sorted(required_ids)
    ]


def report_data(
    *, validation_type: str = "manual", **overrides: object
) -> dict[str, object]:
    environment = (
        "loopback_manual" if validation_type == "manual" else "synthetic_harness"
    )
    value: dict[str, object] = {
        "validation_record_id": "validation-report-001",
        "profile_id": "synthetic-profile",
        "profile_version": "1.0.0",
        "protocol_version": "1.0.0",
        "normalized_product_version": "1.3.2",
        "validation_type": validation_type,
        "started_at": "2026-07-24T00:00:00Z",
        "completed_at": "2026-07-24T00:01:00Z",
        "environment_class": environment,
        "case_results": case_set(validation_type),
        "required_capabilities_result": "passed",
        "optional_capabilities_result": "passed",
        "score_semantics_result": "passed",
        "source_policy_result": "passed",
        "transport_boundary_result": "passed",
        "non_disclosure_result": "passed",
        "overall_status": "passed",
        "revalidation_required": False,
        "safe_error_categories": [],
        "expires_at": "2026-10-24T00:00:00Z",
    }
    value.update(overrides)
    return value


def approval_data(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "approval_record_id": "approval-001",
        "reviewer_id": "reviewer-001",
        "approver_id": "approver-001",
        "decision": "approved",
        "approved_at": "2026-07-24T00:02:00Z",
        "validation_record_id": "validation-report-001",
        "supported_product_version_range": {
            "minimum_version": "1.2.0",
            "maximum_version": "1.4.9",
            "open_ended": False,
        },
        "approved_capabilities": REQUIRED_CAPABILITIES,
        "approved_score_semantics": "unscored",
        "approved_source_identifier_policy": "opaque_safe_id",
        "restrictions": None,
        "expires_at": "2027-07-24T00:00:00Z",
    }
    value.update(overrides)
    return value


def evaluate(
    report: ValidationReport,
    approval: ApprovalMetadata | None = None,
    **overrides: object,
) -> ApprovalDecision:
    values: dict[str, object] = {
        "profile_id": "synthetic-profile",
        "profile_version": PROFILE_VERSION,
        "maturity": ProfileMaturity.MANUALLY_VALIDATED,
        "validation_report": report,
        "approval_metadata": approval or ApprovalMetadata.from_mapping(approval_data()),
        "product_version": "1.3.2",
        "evaluation_time": NOW,
    }
    values.update(overrides)
    return evaluate_approval_decision(**values)  # type: ignore[arg-type]


def assert_safe_error(caught: pytest.ExceptionInfo[RetrievalAdapterError]) -> None:
    assert str(caught.value) == CompatibilityErrorCategory.APPROVAL_METADATA_INVALID.value
    assert "private" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_validation_case_result_is_typed_immutable_and_bounded() -> None:
    result = ValidationCaseResult.from_mapping(
        case_data("health_valid", required=True)
    )
    assert result.outcome is ValidationCaseOutcome.PASSED
    with pytest.raises(FrozenInstanceError):
        result.result_count = 2  # type: ignore[misc]
    assert "health_valid" not in repr(result)


@pytest.mark.parametrize(
    "mutation",
    [
        {"case_id": "unknown_case"},
        {"outcome": "warning"},
        {"bounded_duration_ms": -1},
        {"bounded_duration_ms": True},
        {"bounded_duration_ms": MAX_VALIDATION_DURATION_MS + 1},
        {"result_count": -1},
        {"result_count": True},
        {"result_count": MAX_VALIDATION_RESULT_COUNT + 1},
        {"required": 1},
        {"notes_code": "private free form"},
        {"endpoint": "private-endpoint"},
        {"query": "private-query"},
        {"path": "private-path"},
    ],
)
def test_invalid_case_result_fails_closed(mutation: dict[str, object]) -> None:
    raw = case_data("health_valid", required=True)
    raw.update(mutation)
    with pytest.raises(RetrievalAdapterError) as caught:
        ValidationCaseResult.from_mapping(raw)
    assert_safe_error(caught)


def test_failed_case_requires_one_safe_error_category() -> None:
    failed = ValidationCaseResult.from_mapping(
        case_data(
            "health_valid",
            required=True,
            outcome="failed",
            safe_error_category="health_invalid",
            notes_code="expected_rejection",
        )
    )
    assert failed.safe_error_category == "health_invalid"
    for raw in (
        case_data("health_valid", required=True, outcome="failed"),
        case_data(
            "health_valid",
            required=True,
            safe_error_category="health_invalid",
        ),
        case_data(
            "health_valid",
            required=True,
            outcome="failed",
            safe_error_category="private-error",
        ),
    ):
        with pytest.raises(RetrievalAdapterError):
            ValidationCaseResult.from_mapping(raw)


def test_required_case_sets_are_explicit_and_type_specific() -> None:
    synthetic = required_validation_case_ids(ValidationType.SYNTHETIC)
    manual = required_validation_case_ids("manual")
    assert synthetic == VALIDATION_REPORT_CASE_IDS
    assert manual < synthetic
    assert {
        "duplicate_id_rejected",
        "rank_gap_rejected",
        "query_id_echo_valid",
    }.isdisjoint(manual)
    with pytest.raises(RetrievalAdapterError):
        required_validation_case_ids("automatic")


@pytest.mark.parametrize("validation_type", ["synthetic", "manual"])
def test_valid_validation_report_is_immutable(validation_type: str) -> None:
    report = ValidationReport.from_mapping(
        report_data(validation_type=validation_type)
    )
    assert report.overall_status is ValidationOverallStatus.PASSED
    assert isinstance(report.case_results, tuple)
    with pytest.raises(FrozenInstanceError):
        report.revalidation_required = True  # type: ignore[misc]
    assert "1.3.2" not in repr(report)


def test_manual_and_synthetic_environments_cannot_be_relabelled() -> None:
    for raw in (
        report_data(environment_class="synthetic_harness"),
        report_data(
            validation_type="synthetic", environment_class="loopback_manual"
        ),
    ):
        with pytest.raises(RetrievalAdapterError):
            ValidationReport.from_mapping(raw)
    isolated = ValidationReport.from_mapping(
        report_data(environment_class="isolated_local")
    )
    assert isolated.environment_class is ValidationEnvironmentClass.ISOLATED_LOCAL


@pytest.mark.parametrize(
    "mutation",
    [
        {"started_at": "2026-07-24T00:01:00Z", "completed_at": "2026-07-24T00:00:00Z"},
        {"started_at": "2026-07-24T00:00:00"},
        {"completed_at": "not-a-time"},
        {"expires_at": "2026-07-23T00:00:00Z"},
        {"expires_at": "2026-10-24T00:00:00"},
        {"validation_type": "automatic"},
        {"environment_class": "private-lan"},
        {"revalidation_required": 1},
        {"safe_error_categories": ["private-error"]},
        {"raw_response": "private-response"},
        {"endpoint": "private-endpoint"},
    ],
)
def test_invalid_report_schema_fails_closed(mutation: dict[str, object]) -> None:
    raw = report_data()
    raw.update(mutation)
    with pytest.raises(RetrievalAdapterError) as caught:
        ValidationReport.from_mapping(raw)
    assert_safe_error(caught)


def test_duplicate_unknown_and_missing_cases_fail_closed() -> None:
    cases = case_set()
    for invalid_cases in (
        cases + [dict(cases[0])],
        cases + [case_data("unknown_case", required=False)],
        cases[1:],
    ):
        with pytest.raises(RetrievalAdapterError):
            ValidationReport.from_mapping(report_data(case_results=invalid_cases))


def test_required_flag_must_match_explicit_case_set() -> None:
    cases = case_set()
    cases[0] = dict(cases[0], required=False)
    with pytest.raises(RetrievalAdapterError):
        ValidationReport.from_mapping(report_data(case_results=cases))


def test_failed_or_skipped_required_case_cannot_be_reported_as_passed() -> None:
    for outcome in ("failed", "skipped", "not_applicable"):
        cases = case_set()
        error = "health_invalid" if outcome == "failed" else None
        cases[0] = dict(
            cases[0], outcome=outcome, safe_error_category=error
        )
        errors = [error] if error else []
        with pytest.raises(RetrievalAdapterError):
            ValidationReport.from_mapping(
                report_data(case_results=cases, safe_error_categories=errors)
            )


def test_failed_and_incomplete_reports_are_valid_but_rejected() -> None:
    failed_cases = case_set()
    failed_cases[0] = dict(
        failed_cases[0],
        outcome="failed",
        safe_error_category="health_invalid",
        notes_code="expected_rejection",
    )
    failed = ValidationReport.from_mapping(
        report_data(
            case_results=failed_cases,
            overall_status="failed",
            safe_error_categories=["health_invalid"],
        )
    )
    assert evaluate(failed) is ApprovalDecision.REJECTED

    incomplete_cases = case_set()
    incomplete_cases[0] = dict(
        incomplete_cases[0], outcome="skipped", notes_code="not_executed"
    )
    incomplete = ValidationReport.from_mapping(
        report_data(case_results=incomplete_cases, overall_status="incomplete")
    )
    assert evaluate(incomplete) is ApprovalDecision.REJECTED


def test_expired_report_returns_needs_revalidation_at_fixed_time() -> None:
    report = ValidationReport.from_mapping(
        report_data(overall_status="expired", revalidation_required=True)
    )
    assert evaluate(report) is ApprovalDecision.NEEDS_REVALIDATION
    with pytest.raises(RetrievalAdapterError):
        ValidationReport.from_mapping(report_data(overall_status="expired"))


def test_report_expiration_boundary_uses_explicit_evaluation_time() -> None:
    report = ValidationReport.from_mapping(
        report_data(expires_at="2026-07-24T12:00:00Z")
    )
    before = datetime(2026, 7, 24, 11, 59, 59, tzinfo=timezone.utc)
    boundary = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)
    assert evaluate(report, evaluation_time=before) is ApprovalDecision.APPROVED
    assert (
        evaluate(report, evaluation_time=boundary)
        is ApprovalDecision.NEEDS_REVALIDATION
    )


def test_all_manual_requirements_produce_approved_decision_deterministically() -> None:
    report = ValidationReport.from_mapping(report_data())
    first = evaluate(report)
    second = evaluate(report)
    assert first is ApprovalDecision.APPROVED
    assert second is first


def test_safe_optional_failure_with_restrictions_is_approved_with_restrictions() -> None:
    report = ValidationReport.from_mapping(
        report_data(optional_capabilities_result="failed")
    )
    approval = ApprovalMetadata.from_mapping(
        approval_data(
            decision="approved_with_restrictions",
            restrictions={"title_disabled": True},
        )
    )
    assert evaluate(report, approval) is ApprovalDecision.APPROVED_WITH_RESTRICTIONS
    assert evaluate(report) is ApprovalDecision.REJECTED


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
def test_unsafe_required_report_result_is_rejected(field: str) -> None:
    report = ValidationReport.from_mapping(
        report_data(overall_status="failed", **{field: "failed"})
    )
    assert evaluate(report) is ApprovalDecision.REJECTED


def test_report_must_match_approval_record_and_expected_profile() -> None:
    report = ValidationReport.from_mapping(report_data())
    wrong_record = ApprovalMetadata.from_mapping(
        approval_data(validation_record_id="other-validation")
    )
    with pytest.raises(RetrievalAdapterError) as caught:
        evaluate(report, wrong_record)
    assert_safe_error(caught)
    with pytest.raises(RetrievalAdapterError):
        evaluate(report, profile_id="other-profile")
    with pytest.raises(RetrievalAdapterError):
        evaluate(report, profile_version=SemanticVersion.parse("2.0.0"))


def test_unsupported_product_version_is_rejected_without_nearest_selection() -> None:
    report = ValidationReport.from_mapping(report_data())
    assert evaluate(report, product_version="1.5.0") is ApprovalDecision.REJECTED
    assert evaluate(report, product_version="private-version") is ApprovalDecision.REJECTED


@pytest.mark.parametrize(
    "maturity",
    [
        ProfileMaturity.DRAFT,
        ProfileMaturity.SYNTHETIC_VALIDATED,
        ProfileMaturity.DEPRECATED,
        ProfileMaturity.REVOKED,
    ],
)
def test_non_approvable_maturity_is_rejected(maturity: ProfileMaturity) -> None:
    report = ValidationReport.from_mapping(report_data())
    assert evaluate(report, maturity=maturity) is ApprovalDecision.REJECTED


def test_synthetic_report_cannot_be_used_as_manual_approval() -> None:
    report = ValidationReport.from_mapping(
        report_data(validation_type="synthetic")
    )
    assert evaluate(report) is ApprovalDecision.REJECTED


def test_expired_approval_or_restriction_is_never_approved() -> None:
    report = ValidationReport.from_mapping(report_data())
    expired = ApprovalMetadata.from_mapping(
        approval_data(expires_at="2026-07-23T00:00:00Z")
    )
    assert evaluate(report, expired) is ApprovalDecision.NEEDS_REVALIDATION
    restricted = ApprovalMetadata.from_mapping(
        approval_data(
            decision="approved_with_restrictions",
            restrictions={
                "maximum_top_k": 5,
                "expires_at": "2026-07-23T00:00:00Z",
            },
        )
    )
    assert evaluate(report, restricted) is ApprovalDecision.NEEDS_REVALIDATION


def test_validation_report_safe_summary_is_bounded() -> None:
    raw = report_data(validation_record_id="validation-record-long-001")
    report = ValidationReport.from_mapping(raw)
    summary = summarize_validation_report(
        report, approval_decision=ApprovalDecision.APPROVED
    )
    result = summary.as_mapping()
    assert result["validation_record_id"] == "validati-short"
    assert result["profile_id"] == "synthetic-profile"
    assert result["overall_status"] == "passed"
    assert result["required_failures_count"] == 0
    assert result["approval_decision"] == "approved"
    rendered = repr(summary) + str(summary)
    for marker in (
        "reviewer-001",
        "approver-001",
        "private-endpoint",
        "private-query",
        "private-response",
        "C:/private/path",
        "credential-value",
    ):
        assert marker not in rendered


def test_case_error_must_be_declared_by_report() -> None:
    cases = case_set()
    cases[0] = dict(
        cases[0],
        outcome="failed",
        safe_error_category="health_invalid",
        notes_code="expected_rejection",
    )
    with pytest.raises(RetrievalAdapterError):
        ValidationReport.from_mapping(
            report_data(case_results=cases, overall_status="failed")
        )
