from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ragguard.manual_validation_evidence import (
    MAX_EVIDENCE_FRESHNESS,
    EvidenceCaseOutcome,
    ManualValidationEvidence,
    ManualValidationEvidenceError,
    ManualValidationEvidenceErrorCategory,
)
from ragguard.manual_validation_plan import (
    REQUIRED_ABORT_CONDITIONS,
    REQUIRED_CLEANUP_CONDITIONS,
    REQUIRED_MANUAL_VALIDATION_CASES,
    ManualValidationPlan,
)


MODULE = (
    Path(__file__).parents[1]
    / "src"
    / "ragguard"
    / "manual_validation_evidence.py"
)


def plan_data(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "plan_id": "manual-plan-001",
        "profile_id": "synthetic-profile",
        "profile_version": "1.2.3",
        "protocol_version": "1.0.0",
        "product_id": "product-fixture-alpha",
        "product_version": "2.3.4",
        "created_at": "2026-07-26T00:00:00Z",
        "execution_window_start": "2026-07-27T00:00:00Z",
        "execution_window_end": "2026-07-28T00:00:00Z",
        "profile_implementer_id": "implementer-001",
        "validation_operator_id": "operator-001",
        "evidence_reviewer_id": "reviewer-001",
        "approver_id": "approver-001",
        "registry_administrator_id": "registry-admin-001",
        "required_case_ids": [
            item.value for item in REQUIRED_MANUAL_VALIDATION_CASES
        ],
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
        "abort_conditions": [item.value for item in REQUIRED_ABORT_CONDITIONS],
        "cleanup_conditions": [
            item.value for item in REQUIRED_CLEANUP_CONDITIONS
        ],
        "synthetic_evidence_reference": {
            "reference_id": "synthetic-evidence-a17c0e01",
            "profile_id": "synthetic-profile",
            "profile_version": "1.2.3",
        },
    }
    value.update(overrides)
    return value


def plan() -> ManualValidationPlan:
    return ManualValidationPlan.from_mapping(plan_data())


def passed_case_results(
    *,
    executed_at: str = "2026-07-27T01:30:00.123456Z",
) -> list[dict[str, object]]:
    return [
        {
            "case_id": item.value,
            "outcome": "passed",
            "executed_at": executed_at,
            "safe_observation": "case_passed",
            "failure_category": None,
            "cleanup_confirmed": True,
        }
        for item in REQUIRED_MANUAL_VALIDATION_CASES
    ]


def evidence_data(
    bound_plan: ManualValidationPlan,
    **overrides: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "evidence_id": "manual-evidence-a1b2c3d4",
        "plan_id": bound_plan.plan_id,
        "plan_digest": bound_plan.canonical_digest,
        "profile_id": bound_plan.profile_id,
        "profile_version": str(bound_plan.profile_version),
        "protocol_version": str(bound_plan.protocol_version),
        "product_id": bound_plan.product_id,
        "planned_product_version": str(bound_plan.product_version),
        "observed_product_version": str(bound_plan.product_version),
        "execution_started_at": "2026-07-27T01:00:00.123456Z",
        "execution_completed_at": "2026-07-27T02:00:00.234567Z",
        "validation_operator_id": bound_plan.validation_operator_id,
        "evidence_reviewer_id": bound_plan.evidence_reviewer_id,
        "environment_fingerprint": {
            "environment_id": "environment-ref-1a2b3c4d",
            "os_family": "windows",
            "architecture": "x86_64",
            "python_version": "3.12.13",
            "ragguard_version": "0.11.0",
            "adapter_id": "adapter-fixture-alpha",
            "profile_id": bound_plan.profile_id,
        },
        "tool_version": "0.11.0",
        "case_results": passed_case_results(),
        "close_cleanup_evidence": {
            "transport_closed": True,
            "close_exactly_once": True,
            "temporary_safe_fixture_removed": True,
            "no_raw_payload_retained": True,
            "no_credential_retained": True,
            "no_endpoint_detail_retained": True,
            "safe_summary_produced": True,
        },
        "non_disclosure_evidence": {
            "no_credential_disclosure": True,
            "no_endpoint_disclosure": True,
            "no_path_disclosure": True,
            "no_raw_request_disclosure": True,
            "no_raw_response_disclosure": True,
            "no_real_document_disclosure": True,
            "no_stack_trace_disclosure": True,
            "safe_error_only": True,
        },
        "failure_summary": None,
        "expires_at": "2026-08-26T02:00:00.234567Z",
    }
    value.update(overrides)
    return value


def evidence(
    bound_plan: ManualValidationPlan | None = None,
    **overrides: object,
) -> ManualValidationEvidence:
    selected_plan = bound_plan or plan()
    return ManualValidationEvidence.from_mapping(
        evidence_data(selected_plan, **overrides),
        plan=selected_plan,
    )


def assert_safe_error(
    caught: pytest.ExceptionInfo[ManualValidationEvidenceError],
    category: ManualValidationEvidenceErrorCategory,
) -> None:
    assert caught.value.category is category
    assert str(caught.value) == category.value
    assert repr(caught.value) == f"ManualValidationEvidenceError('{category.value}')"
    assert caught.value.__cause__ is None


def test_valid_evidence_is_immutable_hashable_and_not_authority() -> None:
    record = evidence()

    assert record.is_valid is True
    assert record.canonical_digest.startswith("sha256:")
    assert record.safe_summary.canonical_digest == record.canonical_digest
    assert record.safe_summary.case_count == 22
    assert record.safe_summary.passed_count == 22
    assert hash(record)
    assert MAX_EVIDENCE_FRESHNESS.days == 90
    for forbidden in ("approve", "admit", "register", "connect", "execute"):
        assert forbidden not in dir(record)

    with pytest.raises(FrozenInstanceError):
        record.evidence_id = "manual-evidence-deadbeef"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        record.case_results[0].outcome = "failed"  # type: ignore[misc]


def test_evidence_exposes_complete_phase_b_field_contract() -> None:
    assert tuple(item.name for item in fields(ManualValidationEvidence)) == (
        "evidence_id",
        "plan_id",
        "plan_digest",
        "profile_id",
        "profile_version",
        "protocol_version",
        "product_id",
        "planned_product_version",
        "observed_product_version",
        "execution_started_at",
        "execution_completed_at",
        "validation_operator_id",
        "evidence_reviewer_id",
        "environment_fingerprint",
        "tool_version",
        "case_results",
        "close_cleanup_evidence",
        "non_disclosure_evidence",
        "failure_summary",
        "expires_at",
        "safe_summary",
        "canonical_digest",
    )


def test_digest_and_canonical_order_are_deterministic() -> None:
    bound_plan = plan()
    first = ManualValidationEvidence.from_mapping(
        evidence_data(bound_plan), plan=bound_plan
    )
    reordered = dict(reversed(list(evidence_data(bound_plan).items())))
    reordered["case_results"] = list(
        reversed(reordered["case_results"])  # type: ignore[arg-type]
    )
    second = ManualValidationEvidence.from_mapping(reordered, plan=bound_plan)

    assert first.case_results == second.case_results
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_digest == second.canonical_digest


def test_field_change_changes_digest() -> None:
    first = evidence()
    second = evidence(evidence_id="manual-evidence-deadbeef")
    assert first.canonical_digest != second.canonical_digest


def test_equivalent_timezone_instants_have_same_digest() -> None:
    utc_record = evidence()
    offset_record = evidence(
        execution_started_at="2026-07-27T10:00:00.123456+09:00",
        execution_completed_at="2026-07-27T11:00:00.234567+09:00",
        expires_at="2026-08-26T11:00:00.234567+09:00",
        case_results=passed_case_results(
            executed_at="2026-07-27T10:30:00.123456+09:00"
        ),
    )
    assert utc_record.canonical_json() == offset_record.canonical_json()
    assert utc_record.canonical_digest == offset_record.canonical_digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("execution_started_at", "2026-07-27T01:00:00.123457Z"),
        ("execution_completed_at", "2026-07-27T02:00:00.234568Z"),
        ("expires_at", "2026-08-26T02:00:00.234568Z"),
    ],
)
def test_microsecond_difference_changes_digest(field: str, value: str) -> None:
    assert evidence().canonical_digest != evidence(**{field: value}).canonical_digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("plan_id", "manual-plan-other"),
        ("plan_digest", "sha256:" + "0" * 64),
        ("profile_id", "other-profile"),
        ("profile_version", "1.2.4"),
        ("protocol_version", "1.0.1"),
        ("product_id", "product-fixture-other"),
        ("planned_product_version", "2.3.5"),
        ("observed_product_version", "2.3.5"),
    ],
)
def test_exact_plan_and_product_binding_is_required(
    field: str, value: object
) -> None:
    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(**{field: value})
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.PLAN_BINDING_INVALID
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_version", "1.2"),
        ("protocol_version", "1.*.0"),
        ("planned_product_version", ">=2.3.4"),
        ("observed_product_version", "nearest"),
        ("observed_product_version", True),
        ("observed_product_version", 1),
    ],
)
def test_versions_are_strict_and_exact(field: str, value: object) -> None:
    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(**{field: value})
    assert_safe_error(caught, ManualValidationEvidenceErrorCategory.VERSION_INVALID)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("validation_operator_id", "other-operator"),
        ("evidence_reviewer_id", "other-reviewer"),
        ("evidence_reviewer_id", "operator-001"),
    ],
)
def test_roles_bind_exactly_to_plan_and_remain_separate(
    field: str, value: str
) -> None:
    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(**{field: value})
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.ROLE_BINDING_INVALID
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"execution_started_at": "2026-07-27T01:00:00"},
        {"execution_completed_at": "2026-07-27T02:00:00"},
        {"expires_at": "2026-08-26T02:00:00"},
        {
            "execution_started_at": "2026-07-27T02:00:00Z",
            "execution_completed_at": "2026-07-27T02:00:00Z",
        },
        {"execution_started_at": "2026-07-26T23:59:59.999999Z"},
        {"execution_completed_at": "2026-07-28T00:00:00.000001Z"},
        {"expires_at": "2026-07-27T02:00:00.234567Z"},
        {"expires_at": "2026-10-25T02:00:00.234568Z"},
    ],
)
def test_execution_and_freshness_are_explicit_and_bounded(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(**overrides)
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.EXECUTION_TIME_INVALID
    )


def test_expiry_is_evaluated_only_at_explicit_time() -> None:
    record = evidence()
    before = datetime(2026, 8, 26, 2, 0, 0, 234566, tzinfo=timezone.utc)
    at_expiry = datetime(2026, 8, 26, 2, 0, 0, 234567, tzinfo=timezone.utc)
    assert record.is_expired(before) is False
    assert record.is_expired(at_expiry) is True
    assert record.is_valid_at(before) is True
    assert record.is_valid_at(at_expiry) is False
    with pytest.raises(ManualValidationEvidenceError):
        record.is_expired(datetime(2026, 8, 26, 2, 0, 0))


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown"])
def test_case_result_set_is_exact(mode: str) -> None:
    results = passed_case_results()
    if mode == "missing":
        results.pop()
    elif mode == "duplicate":
        results[-1]["case_id"] = results[0]["case_id"]
    else:
        results[-1]["case_id"] = "optional_case"
    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(case_results=results)
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID
    )


@pytest.mark.parametrize(
    ("outcome", "observation", "failure_category", "summary"),
    [
        (
            "failed",
            "case_failed",
            "case_assertion_failed",
            {
                "category": "failed_cases",
                "failed_case_count": 1,
                "aborted_case_count": 0,
            },
        ),
        (
            "aborted",
            "case_aborted",
            "execution_aborted",
            {
                "category": "aborted_cases",
                "failed_case_count": 0,
                "aborted_case_count": 1,
            },
        ),
    ],
)
def test_failed_or_aborted_case_prevents_valid_evidence(
    outcome: str,
    observation: str,
    failure_category: str,
    summary: dict[str, object],
) -> None:
    results = passed_case_results()
    results[0].update(
        {
            "outcome": outcome,
            "safe_observation": observation,
            "failure_category": failure_category,
            "cleanup_confirmed": False,
        }
    )
    record = evidence(case_results=results, failure_summary=summary)
    assert record.is_valid is False
    assert record.safe_summary.passed_count == 21


def test_failure_summary_is_required_only_for_failure() -> None:
    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(
            failure_summary={
                "category": "failed_cases",
                "failed_case_count": 1,
                "aborted_case_count": 0,
            }
        )
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID
    )


def test_failure_summary_rejects_unsafe_detail_and_boolean_counts() -> None:
    results = passed_case_results()
    results[0].update(
        {
            "outcome": "failed",
            "safe_observation": "case_failed",
            "failure_category": "case_assertion_failed",
        }
    )
    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(
            case_results=results,
            failure_summary={
                "category": "failed_cases",
                "failed_case_count": 1,
                "aborted_case_count": 0,
                "unsafe_detail": "raw query and endpoint",
            },
        )
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID
    )

    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(
            case_results=results,
            failure_summary={
                "category": "failed_cases",
                "failed_case_count": True,
                "aborted_case_count": 0,
            },
        )
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID
    )


@pytest.mark.parametrize(
    ("field", "category"),
    [
        (
            "close_cleanup_evidence",
            ManualValidationEvidenceErrorCategory.CLEANUP_EVIDENCE_INVALID,
        ),
        (
            "non_disclosure_evidence",
            ManualValidationEvidenceErrorCategory.NON_DISCLOSURE_EVIDENCE_INVALID,
        ),
    ],
)
def test_cleanup_and_non_disclosure_require_complete_true_contract(
    field: str,
    category: ManualValidationEvidenceErrorCategory,
) -> None:
    bound_plan = plan()
    data = evidence_data(bound_plan)
    nested = dict(data[field])  # type: ignore[arg-type]
    nested.pop(next(iter(nested)))
    with pytest.raises(ManualValidationEvidenceError) as caught:
        ManualValidationEvidence.from_mapping(
            {**data, field: nested}, plan=bound_plan
        )
    assert_safe_error(caught, category)


@pytest.mark.parametrize(
    ("field", "value", "category"),
    [
        (
            "transport_closed",
            False,
            ManualValidationEvidenceErrorCategory.CLEANUP_EVIDENCE_INVALID,
        ),
        (
            "close_exactly_once",
            1,
            ManualValidationEvidenceErrorCategory.CLEANUP_EVIDENCE_INVALID,
        ),
        (
            "no_endpoint_disclosure",
            False,
            ManualValidationEvidenceErrorCategory.NON_DISCLOSURE_EVIDENCE_INVALID,
        ),
        (
            "safe_error_only",
            1,
            ManualValidationEvidenceErrorCategory.NON_DISCLOSURE_EVIDENCE_INVALID,
        ),
    ],
)
def test_cleanup_and_non_disclosure_reject_false_and_integer_booleans(
    field: str,
    value: object,
    category: ManualValidationEvidenceErrorCategory,
) -> None:
    bound_plan = plan()
    data = evidence_data(bound_plan)
    nested_name = (
        "close_cleanup_evidence"
        if field in data["close_cleanup_evidence"]  # type: ignore[operator]
        else "non_disclosure_evidence"
    )
    nested = dict(data[nested_name])  # type: ignore[arg-type]
    nested[field] = value
    with pytest.raises(ManualValidationEvidenceError) as caught:
        ManualValidationEvidence.from_mapping(
            {**data, nested_name: nested}, plan=bound_plan
        )
    assert_safe_error(caught, category)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment_id", "hostname-fixture"),
        ("environment_id", "environment-ref-token"),
        ("adapter_id", "adapter-fixture-secret"),
        ("profile_id", "profile@example.test"),
        ("python_version", True),
        ("ragguard_version", "0.11"),
    ],
)
def test_environment_fingerprint_rejects_unsafe_identity(
    field: str, value: object
) -> None:
    bound_plan = plan()
    data = evidence_data(bound_plan)
    fingerprint = dict(data["environment_fingerprint"])  # type: ignore[arg-type]
    fingerprint[field] = value
    with pytest.raises(ManualValidationEvidenceError) as caught:
        ManualValidationEvidence.from_mapping(
            {**data, "environment_fingerprint": fingerprint},
            plan=bound_plan,
        )
    assert_safe_error(
        caught,
        ManualValidationEvidenceErrorCategory.ENVIRONMENT_FINGERPRINT_INVALID,
    )


@pytest.mark.parametrize(
    ("unsafe_field", "unsafe_value"),
    [
        ("hostname", "fixture-host"),
        ("ip_address", "127.0.0.1"),
        ("absolute_path", "C:/private/report.json"),
        ("endpoint", "https://example.test/private"),
        ("credential", "synthetic-token-value"),
        ("raw_payload", "raw request body"),
    ],
)
def test_environment_unknown_unsafe_fields_are_rejected(
    unsafe_field: str, unsafe_value: str
) -> None:
    bound_plan = plan()
    data = evidence_data(bound_plan)
    fingerprint = dict(data["environment_fingerprint"])  # type: ignore[arg-type]
    fingerprint[unsafe_field] = unsafe_value
    with pytest.raises(ManualValidationEvidenceError) as caught:
        ManualValidationEvidence.from_mapping(
            {**data, "environment_fingerprint": fingerprint},
            plan=bound_plan,
        )
    assert unsafe_value not in str(caught.value)


def test_raw_payload_and_unsafe_failure_detail_are_unknown_fields() -> None:
    bound_plan = plan()
    data = evidence_data(bound_plan)
    data["raw_response"] = "synthetic raw response"
    with pytest.raises(ManualValidationEvidenceError) as caught:
        ManualValidationEvidence.from_mapping(data, plan=bound_plan)
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.FIELD_SET_INVALID
    )

    results = passed_case_results()
    results[0]["raw_observation"] = "synthetic raw payload"
    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(case_results=results)
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID
    )


def test_safe_summary_and_repr_do_not_disclose_roles_or_environment_identity() -> None:
    record = evidence()
    rendered = f"{record.safe_summary!r} {record!r}"
    for excluded in (
        "operator-001",
        "reviewer-001",
        "environment-ref-1a2b3c4d",
        "adapter-fixture-alpha",
    ):
        assert excluded not in rendered
    canonical = json.loads(record.canonical_json())
    assert record.safe_summary.execution_started_at == (
        canonical["execution_started_at"]
    )
    assert record.safe_summary.execution_completed_at == (
        canonical["execution_completed_at"]
    )
    assert record.safe_summary.environment_digest.startswith("sha256:")


def test_error_does_not_replay_unsafe_input() -> None:
    unsafe = "https://user:credential@example.test/private?token=value"
    bound_plan = plan()
    data = evidence_data(bound_plan)
    fingerprint = dict(data["environment_fingerprint"])  # type: ignore[arg-type]
    fingerprint["endpoint"] = unsafe
    with pytest.raises(ManualValidationEvidenceError) as caught:
        ManualValidationEvidence.from_mapping(
            {**data, "environment_fingerprint": fingerprint},
            plan=bound_plan,
        )
    assert unsafe not in str(caught.value)


def test_external_case_result_mutation_does_not_change_evidence() -> None:
    results = passed_case_results()
    record = evidence(case_results=results)
    digest = record.canonical_digest
    results.clear()
    assert len(record.case_results) == 22
    assert record.canonical_digest == digest


def test_environment_or_tool_change_changes_digest_and_mismatch_fails() -> None:
    first = evidence()
    bound_plan = plan()
    data = evidence_data(bound_plan)
    fingerprint = dict(data["environment_fingerprint"])  # type: ignore[arg-type]
    fingerprint["python_version"] = "3.11.9"
    changed = ManualValidationEvidence.from_mapping(
        {**data, "environment_fingerprint": fingerprint},
        plan=bound_plan,
    )
    assert first.canonical_digest != changed.canonical_digest

    with pytest.raises(ManualValidationEvidenceError) as caught:
        evidence(tool_version="0.11.1")
    assert_safe_error(
        caught, ManualValidationEvidenceErrorCategory.TOOL_VERSION_INVALID
    )


def test_dataclass_replace_rebinds_and_recomputes_digest() -> None:
    bound_plan = plan()
    record = evidence(bound_plan)
    updated = replace(
        record,
        evidence_id="manual-evidence-deadbeef",
        plan=bound_plan,
    )
    assert updated.canonical_digest != record.canonical_digest
    assert updated.safe_summary.evidence_id == "manual-evidence-deadbeef"


def test_contract_has_no_hidden_clock_random_uuid_io_network_or_filesystem() -> None:
    source = MODULE.read_text(encoding="utf-8")
    for marker in (
        "datetime.now",
        "datetime.utcnow",
        "import random",
        "import uuid",
        "uuid4",
        "import socket",
        "import urllib",
        "import requests",
        "import http",
        "from pathlib",
        "open(",
        "Path(",
    ):
        assert marker not in source
