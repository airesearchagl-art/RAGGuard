from __future__ import annotations

import ast
import copy
import hashlib
import json
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import ragguard
from ragguard.manual_evidence_import import (
    MAX_CASE_RESULT_COUNT,
    MAX_ENVIRONMENT_FIELD_LENGTH,
    MAX_FAILURE_SUMMARY_LENGTH,
    MAX_IDENTIFIER_LENGTH,
    MAX_SAFE_CONTEXT_LENGTH,
    MAX_SAFE_OBSERVATION_LENGTH,
    MAX_TOTAL_FIXTURE_BYTES,
    ManualEvidenceImportError,
    ManualEvidenceImportErrorCategory,
    ManualEvidenceImportRequest,
    ManualEvidenceImportResult,
    ManualEvidenceSourceKind,
    import_manual_validation_evidence,
)
from ragguard.manual_validation_evidence import EvidenceEnvironmentFingerprint
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
    / "manual_evidence_import.py"
)
SAFE_CONTEXT = [
    "manual_validation_not_executed",
    "no_credentials",
    "no_filesystem",
    "no_network",
    "no_real_documents",
    "no_registry_write",
    "no_transport",
    "product_neutral",
    "synthetic_only",
]


def plan_data(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "plan_id": "manual-plan-001",
        "profile_id": "synthetic-profile",
        "profile_version": "1.2.3",
        "protocol_version": "1.0.0",
        "product_id": "product-fixture-alpha",
        "product_version": "2.3.4",
        "created_at": "2026-07-26T00:00:00.000000Z",
        "execution_window_start": "2026-07-27T00:00:00.000000Z",
        "execution_window_end": "2026-07-28T00:00:00.000000Z",
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


def environment_fixture(
    bound_plan: ManualValidationPlan,
    **overrides: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "environment_id": "environment-ref-1a2b3c4d",
        "os_family": "windows",
        "architecture": "x86_64",
        "python_version": "3.12.13",
        "ragguard_version": "0.11.0",
        "adapter_id": "adapter-fixture-alpha",
        "profile_id": bound_plan.profile_id,
    }
    value.update(overrides)
    typed = EvidenceEnvironmentFingerprint.from_mapping(value)
    return {**value, "declared_digest": typed.canonical_digest}


def passed_case_fixtures(
    *, executed_at: str = "2026-07-27T01:30:00.123456Z"
) -> list[dict[str, object]]:
    return [
        {
            "case_id": case_id.value,
            "outcome": "passed",
            "executed_at": executed_at,
            "safe_observation": "case_passed",
            "failure_category": None,
            "cleanup_confirmed": True,
        }
        for case_id in REQUIRED_MANUAL_VALIDATION_CASES
    ]


def import_data(
    bound_plan: ManualValidationPlan,
    **overrides: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "import_id": "manual-import-1a2b3c4d",
        "plan_reference": {
            "plan_id": bound_plan.plan_id,
            "plan_digest": bound_plan.canonical_digest,
        },
        "evidence_identity": {"evidence_id": "manual-evidence-a1b2c3d4"},
        "identity_binding": {
            "profile_id": bound_plan.profile_id,
            "profile_version": str(bound_plan.profile_version),
            "protocol_version": str(bound_plan.protocol_version),
            "product_id": bound_plan.product_id,
            "planned_product_version": str(bound_plan.product_version),
            "observed_product_version": str(bound_plan.product_version),
        },
        "execution_timestamps": {
            "execution_started_at": "2026-07-27T01:00:00.123456Z",
            "execution_completed_at": "2026-07-27T02:00:00.234567Z",
        },
        "role_identities": {
            "validation_operator_id": bound_plan.validation_operator_id,
            "evidence_reviewer_id": bound_plan.evidence_reviewer_id,
        },
        "environment_fixture": environment_fixture(bound_plan),
        "tool_version": "0.11.0",
        "case_result_fixtures": passed_case_fixtures(),
        "cleanup_declarations": {
            "transport_closed": True,
            "close_exactly_once": True,
            "temporary_safe_fixture_removed": True,
            "no_raw_payload_retained": True,
            "no_credential_retained": True,
            "no_endpoint_detail_retained": True,
            "safe_summary_produced": True,
        },
        "non_disclosure_declarations": {
            "no_credential_disclosure": True,
            "no_endpoint_disclosure": True,
            "no_path_disclosure": True,
            "no_raw_request_disclosure": True,
            "no_raw_response_disclosure": True,
            "no_real_document_disclosure": True,
            "no_stack_trace_disclosure": True,
            "safe_error_only": True,
        },
        "failure_summary_fixture": None,
        "expiry": "2026-08-26T02:00:00.234567Z",
        "source_kind": "inline_safe_fixture",
        "source_digest": "sha256:" + ("0" * 64),
        "safe_context": list(SAFE_CONTEXT),
    }
    value.update(overrides)
    value["source_digest"] = source_digest(value)
    return value


def _canonical_time(value: str) -> str:
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        .astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def source_digest(value: dict[str, object]) -> str:
    payload = copy.deepcopy(value)
    payload.pop("source_digest", None)
    execution = payload["execution_timestamps"]
    assert isinstance(execution, dict)
    execution["execution_started_at"] = _canonical_time(
        execution["execution_started_at"]  # type: ignore[arg-type]
    )
    execution["execution_completed_at"] = _canonical_time(
        execution["execution_completed_at"]  # type: ignore[arg-type]
    )
    payload["expiry"] = _canonical_time(payload["expiry"])  # type: ignore[arg-type]
    cases = payload["case_result_fixtures"]
    assert isinstance(cases, list)
    for case in cases:
        case["executed_at"] = _canonical_time(case["executed_at"])
    case_order = {
        case_id.value: index
        for index, case_id in enumerate(REQUIRED_MANUAL_VALIDATION_CASES)
    }
    cases.sort(key=lambda case: case_order.get(case["case_id"], 999))
    payload["safe_context"] = list(SAFE_CONTEXT)
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def request(
    bound_plan: ManualValidationPlan | None = None,
    **overrides: object,
) -> ManualEvidenceImportRequest:
    selected = bound_plan or plan()
    return ManualEvidenceImportRequest.from_mapping(
        import_data(selected, **overrides)
    )


def assert_safe_error(
    caught: pytest.ExceptionInfo[ManualEvidenceImportError],
    category: ManualEvidenceImportErrorCategory,
) -> None:
    assert caught.value.category is category
    assert str(caught.value) == category.value
    assert repr(caught.value) == f"ManualEvidenceImportError('{category.value}')"
    assert caught.value.__cause__ is None


def test_valid_safe_fixture_imports_phase_b_evidence() -> None:
    bound_plan = plan()
    result = import_manual_validation_evidence(
        request(bound_plan), plan=bound_plan
    )

    assert result.accepted is True
    assert result.reason_categories == ()
    assert result.evidence is not None
    assert result.evidence.is_valid is True
    assert result.evidence_digest == result.evidence.canonical_digest
    assert result.evidence.plan_digest == bound_plan.canonical_digest
    assert result.source_digest != result.evidence_digest
    assert result.safe_summary.case_count == 22
    assert result.safe_summary.passed_count == 22


def test_tokenizer_fixture_opaque_identifier_is_accepted() -> None:
    data = import_data(plan())
    role_identities = data["role_identities"]
    assert isinstance(role_identities, dict)
    role_identities["validation_operator_id"] = "tokenizer-fixture"
    data["source_digest"] = source_digest(data)
    parsed = ManualEvidenceImportRequest.from_mapping(data)
    assert parsed.role_identities.validation_operator_id == "tokenizer-fixture"


def test_secretariat_profile_opaque_identifier_is_accepted() -> None:
    data = import_data(plan())
    identity_binding = data["identity_binding"]
    assert isinstance(identity_binding, dict)
    identity_binding["profile_id"] = "secretariat-profile"
    data["source_digest"] = source_digest(data)
    parsed = ManualEvidenceImportRequest.from_mapping(data)
    assert parsed.identity_binding.profile_id == "secretariat-profile"


def test_request_and_result_are_immutable_hashable_and_bounded() -> None:
    bound_plan = plan()
    import_request = request(bound_plan)
    result = import_manual_validation_evidence(import_request, plan=bound_plan)

    assert hash(import_request)
    assert hash(result)
    with pytest.raises(FrozenInstanceError):
        import_request.import_id = "manual-import-deadbeef"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.accepted = False  # type: ignore[misc]
    assert MAX_TOTAL_FIXTURE_BYTES == 65_536
    assert MAX_IDENTIFIER_LENGTH == 64
    assert MAX_SAFE_CONTEXT_LENGTH == 512
    assert MAX_CASE_RESULT_COUNT == 22
    assert MAX_SAFE_OBSERVATION_LENGTH == 32
    assert MAX_FAILURE_SUMMARY_LENGTH == 256
    assert MAX_ENVIRONMENT_FIELD_LENGTH == 64


def test_request_exposes_complete_import_contract() -> None:
    assert tuple(item.name for item in fields(ManualEvidenceImportRequest)) == (
        "import_id",
        "plan_reference",
        "evidence_identity",
        "identity_binding",
        "execution_timestamps",
        "role_identities",
        "environment_fixture",
        "tool_version",
        "case_result_fixtures",
        "cleanup_declarations",
        "non_disclosure_declarations",
        "failure_summary_fixture",
        "expiry",
        "source_kind",
        "source_digest",
        "safe_context",
        "source_canonical_json",
        "canonical_digest",
    )


def test_result_exposes_complete_safe_contract() -> None:
    assert tuple(item.name for item in fields(ManualEvidenceImportResult)) == (
        "import_id",
        "accepted",
        "source_kind",
        "source_digest",
        "evidence_id",
        "evidence_digest",
        "plan_id",
        "plan_digest",
        "reason_categories",
        "evidence",
        "safe_summary",
        "canonical_digest",
    )


def test_source_and_result_digests_are_deterministic() -> None:
    bound_plan = plan()
    first_request = request(bound_plan)
    second_request = request(bound_plan)
    first = import_manual_validation_evidence(first_request, plan=bound_plan)
    second = import_manual_validation_evidence(second_request, plan=bound_plan)
    assert first_request.source_canonical_json == (
        second_request.source_canonical_json
    )
    assert first_request.source_digest == second_request.source_digest
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_digest == second.canonical_digest


def test_field_order_does_not_change_source_digest() -> None:
    bound_plan = plan()
    ordered = import_data(bound_plan)
    reordered = dict(reversed(list(ordered.items())))
    reordered["case_result_fixtures"] = list(
        reversed(reordered["case_result_fixtures"])  # type: ignore[arg-type]
    )
    first = ManualEvidenceImportRequest.from_mapping(ordered)
    second = ManualEvidenceImportRequest.from_mapping(reordered)
    assert first.source_canonical_json == second.source_canonical_json
    assert first.source_digest == second.source_digest


def test_safe_field_change_changes_source_digest() -> None:
    bound_plan = plan()
    first = request(bound_plan)
    second = request(
        bound_plan,
        import_id="manual-import-deadbeef",
    )
    assert first.source_digest != second.source_digest


def test_equivalent_timezone_instants_have_same_source_digest() -> None:
    bound_plan = plan()
    utc_request = request(bound_plan)
    offset_request = request(
        bound_plan,
        execution_timestamps={
            "execution_started_at": "2026-07-27T10:00:00.123456+09:00",
            "execution_completed_at": "2026-07-27T11:00:00.234567+09:00",
        },
        expiry="2026-08-26T11:00:00.234567+09:00",
        case_result_fixtures=passed_case_fixtures(
            executed_at="2026-07-27T10:30:00.123456+09:00"
        ),
    )
    assert utc_request.source_canonical_json == (
        offset_request.source_canonical_json
    )
    assert utc_request.source_digest == offset_request.source_digest


def test_one_microsecond_change_changes_source_digest() -> None:
    bound_plan = plan()
    baseline = request(bound_plan)
    changed = request(
        bound_plan,
        execution_timestamps={
            "execution_started_at": "2026-07-27T01:00:00.123456Z",
            "execution_completed_at": "2026-07-27T02:00:00.234568Z",
        },
    )
    assert baseline.source_digest != changed.source_digest


def test_source_digest_mismatch_is_rejected() -> None:
    data = import_data(plan())
    data["source_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(caught, ManualEvidenceImportErrorCategory.DIGEST_INVALID)


def test_only_inline_safe_fixture_source_kind_is_allowed() -> None:
    data = import_data(plan(), source_kind="file")
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(caught, ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
    assert tuple(ManualEvidenceSourceKind) == (
        ManualEvidenceSourceKind.INLINE_SAFE_FIXTURE,
    )


def test_non_mapping_input_is_rejected() -> None:
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping([])
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.INPUT_TYPE_INVALID
    )


def test_unknown_field_is_rejected() -> None:
    data = import_data(plan())
    data["unexpected"] = "opaque"
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(caught, ManualEvidenceImportErrorCategory.UNKNOWN_FIELD)


def test_missing_field_is_rejected_without_defaulting() -> None:
    data = import_data(plan())
    data.pop("expiry")
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.REQUIRED_FIELD_MISSING
    )


def test_null_is_not_implicitly_defaulted() -> None:
    data = import_data(plan())
    data["expiry"] = None
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID
    )


def test_bool_is_not_treated_as_int() -> None:
    bound_plan = plan()
    cases = passed_case_fixtures()
    cases[0].update(
        outcome="failed",
        safe_observation="case_failed",
        failure_category="case_assertion_failed",
    )
    data = import_data(
        bound_plan,
        case_result_fixtures=cases,
        failure_summary_fixture={
            "category": "failed_cases",
            "failed_case_count": True,
            "aborted_case_count": 0,
        },
    )
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID
    )


def test_oversized_total_input_is_rejected_before_schema_details() -> None:
    data = import_data(plan())
    data["unexpected"] = "x" * MAX_TOTAL_FIXTURE_BYTES
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED
    )


def test_oversized_bounded_field_is_rejected() -> None:
    data = import_data(plan())
    data["safe_context"] = ["x" * (MAX_SAFE_CONTEXT_LENGTH + 1)]
    data["source_digest"] = source_digest(data)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED
    )


@pytest.mark.parametrize("target", ["identifier", "observation"])
def test_oversized_identifier_or_observation_is_rejected(target: str) -> None:
    bound_plan = plan()
    data = import_data(bound_plan)
    if target == "identifier":
        data["import_id"] = "a" * (MAX_IDENTIFIER_LENGTH + 1)
    else:
        cases = passed_case_fixtures()
        cases[0]["safe_observation"] = "x" * (
            MAX_SAFE_OBSERVATION_LENGTH + 1
        )
        data["case_result_fixtures"] = cases
    data["source_digest"] = source_digest(data)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED
    )


def test_nested_arbitrary_mapping_is_rejected() -> None:
    data = import_data(plan())
    data["safe_context"] = [{"nested": "opaque"}]
    data["source_digest"] = source_digest(data)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(caught, ManualEvidenceImportErrorCategory.SCHEMA_INVALID)


@pytest.mark.parametrize("field", ["plan_id", "plan_digest"])
def test_plan_reference_mismatch_returns_safe_rejection(field: str) -> None:
    bound_plan = plan()
    plan_reference = {
        "plan_id": bound_plan.plan_id,
        "plan_digest": bound_plan.canonical_digest,
    }
    plan_reference[field] = (
        "manual-plan-999"
        if field == "plan_id"
        else "sha256:" + ("f" * 64)
    )
    result = import_manual_validation_evidence(
        request(bound_plan, plan_reference=plan_reference),
        plan=bound_plan,
    )
    assert result.accepted is False
    assert result.evidence is None
    assert result.evidence_digest is None
    assert result.reason_categories == (
        ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_id", "other-profile"),
        ("profile_version", "1.2.4"),
        ("protocol_version", "1.0.1"),
        ("product_id", "product-fixture-beta"),
        ("planned_product_version", "2.3.5"),
        ("observed_product_version", "2.3.5"),
    ],
)
def test_identity_or_version_mismatch_is_rejected(
    field: str, value: str
) -> None:
    bound_plan = plan()
    identity = import_data(bound_plan)["identity_binding"]
    assert isinstance(identity, dict)
    identity[field] = value
    result = import_manual_validation_evidence(
        request(bound_plan, identity_binding=identity), plan=bound_plan
    )
    assert result.accepted is False
    assert result.evidence is None
    assert result.reason_categories == (
        ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("validation_operator_id", "operator-999"),
        ("evidence_reviewer_id", "reviewer-999"),
    ],
)
def test_role_mismatch_is_rejected(field: str, value: str) -> None:
    bound_plan = plan()
    roles = import_data(bound_plan)["role_identities"]
    assert isinstance(roles, dict)
    roles[field] = value
    result = import_manual_validation_evidence(
        request(bound_plan, role_identities=roles), plan=bound_plan
    )
    assert result.accepted is False
    assert result.reason_categories == (
        ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID,
    )


def test_execution_outside_plan_window_is_rejected() -> None:
    bound_plan = plan()
    result = import_manual_validation_evidence(
        request(
            bound_plan,
            execution_timestamps={
                "execution_started_at": "2026-07-26T23:59:59.999999Z",
                "execution_completed_at": "2026-07-27T02:00:00.234567Z",
            },
        ),
        plan=bound_plan,
    )
    assert result.accepted is False
    assert result.reason_categories == (
        ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID,
    )


def test_missing_required_case_is_rejected() -> None:
    cases = passed_case_fixtures()[:-1]
    data = import_data(plan(), case_result_fixtures=cases)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.CASE_SET_INVALID
    )


def test_duplicate_case_is_rejected() -> None:
    cases = passed_case_fixtures()
    cases[-1] = copy.deepcopy(cases[0])
    data = import_data(plan(), case_result_fixtures=cases)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.CASE_SET_INVALID
    )


def test_unknown_case_is_rejected() -> None:
    cases = passed_case_fixtures()
    cases[-1]["case_id"] = "unknown_case"
    data = import_data(plan(), case_result_fixtures=cases)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID
    )


@pytest.mark.parametrize(
    ("outcome", "observation", "failure", "summary"),
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
def test_failed_or_aborted_case_imports_but_is_not_valid_evidence(
    outcome: str,
    observation: str,
    failure: str,
    summary: dict[str, object],
) -> None:
    bound_plan = plan()
    cases = passed_case_fixtures()
    cases[0].update(
        outcome=outcome,
        safe_observation=observation,
        failure_category=failure,
    )
    result = import_manual_validation_evidence(
        request(
            bound_plan,
            case_result_fixtures=cases,
            failure_summary_fixture=summary,
        ),
        plan=bound_plan,
    )
    assert result.accepted is True
    assert result.evidence is not None
    assert result.evidence.is_valid is False


def test_skipped_case_is_rejected() -> None:
    cases = passed_case_fixtures()
    cases[0]["outcome"] = "skipped"
    data = import_data(plan(), case_result_fixtures=cases)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID
    )


def test_environment_digest_mismatch_is_rejected() -> None:
    bound_plan = plan()
    environment = environment_fixture(bound_plan)
    environment["declared_digest"] = "sha256:" + ("f" * 64)
    data = import_data(bound_plan, environment_fixture=environment)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.ENVIRONMENT_INVALID
    )


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "https://fixture.invalid/resource",
        "192.0.2.1",
        "2001:db8::1",
        "C:\\private\\fixture.json",
        "/private/fixture.json",
        "Authorization: Bearer opaque",
        "api_key=opaque",
        "token=opaque",
        "cookie=session",
        "-----BEGIN PRIVATE KEY-----",
        "Traceback (most recent call last):",
        "GET /raw HTTP/1.1",
        "HTTP/1.1 200 OK",
        "opaque\x00value",
        "opaque\u202evalue",
        "opaque\nvalue",
        "opaque\rvalue",
    ],
)
def test_structurally_invalid_unsafe_identifier_is_rejected_without_disclosure(
    unsafe_value: str,
) -> None:
    data = import_data(plan())
    role_identities = data["role_identities"]
    assert isinstance(role_identities, dict)
    role_identities["validation_operator_id"] = unsafe_value
    data["source_digest"] = source_digest(data)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.IDENTIFIER_INVALID
    )
    assert unsafe_value not in str(caught.value)
    assert unsafe_value not in repr(caught.value)


def test_safe_summary_is_non_disclosing() -> None:
    bound_plan = plan()
    result = import_manual_validation_evidence(
        request(bound_plan), plan=bound_plan
    )
    serialized = json.dumps(
        result.safe_summary.__dict__,
        sort_keys=True,
        default=str,
    ).lower()
    for forbidden in (
        "authorization:",
        "http://",
        "https://",
        "traceback",
        "private key",
        "raw_request",
        "raw_response",
    ):
        assert forbidden not in serialized


def test_external_evidence_digest_field_is_not_trusted() -> None:
    data = import_data(plan())
    data["evidence_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(caught, ManualEvidenceImportErrorCategory.UNKNOWN_FIELD)


def test_phase_b_recomputes_evidence_digest() -> None:
    bound_plan = plan()
    result = import_manual_validation_evidence(
        request(bound_plan), plan=bound_plan
    )
    assert result.evidence is not None
    assert result.evidence_digest == result.evidence.canonical_digest
    assert result.safe_summary.evidence_digest == result.evidence.canonical_digest
    assert result.source_digest != result.evidence.canonical_digest


def test_rejected_result_contains_no_partial_evidence() -> None:
    bound_plan = plan()
    plan_reference = {
        "plan_id": bound_plan.plan_id,
        "plan_digest": "sha256:" + ("f" * 64),
    }
    result = import_manual_validation_evidence(
        request(bound_plan, plan_reference=plan_reference), plan=bound_plan
    )
    assert result.accepted is False
    assert result.evidence is None
    assert result.evidence_digest is None
    assert result.safe_summary.case_count == 0
    assert result.safe_summary.passed_count == 0


def test_importer_has_no_impure_or_runtime_dependencies() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imported_roots.isdisjoint(
        {
            "asyncio",
            "http",
            "os",
            "pathlib",
            "random",
            "requests",
            "socket",
            "subprocess",
            "time",
            "urllib",
            "uuid",
        }
    )
    source = MODULE.read_text(encoding="utf-8")
    for forbidden_call in (
        "open(",
        "getenv(",
        "urlopen(",
        "requests.",
        "socket.",
        "subprocess.",
        "registry.",
        "transport.",
    ):
        assert forbidden_call not in source


def test_importer_requires_explicit_plan_and_request_types() -> None:
    with pytest.raises(ManualEvidenceImportError) as caught:
        import_manual_validation_evidence({}, plan=plan())  # type: ignore[arg-type]
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.INPUT_TYPE_INVALID
    )
    with pytest.raises(ManualEvidenceImportError) as caught:
        import_manual_validation_evidence(
            request(), plan=None  # type: ignore[arg-type]
        )
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID
    )


def test_importer_uses_no_hidden_clock() -> None:
    bound_plan = plan()
    import_request = request(bound_plan)
    first = import_manual_validation_evidence(import_request, plan=bound_plan)
    second = import_manual_validation_evidence(import_request, plan=bound_plan)
    assert first == second
    assert first.canonical_digest == second.canonical_digest


def test_expiry_is_completion_exclusive_and_bounded_to_90_days() -> None:
    bound_plan = plan()
    at_completion = import_data(
        bound_plan, expiry="2026-07-27T02:00:00.234567Z"
    )
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(at_completion)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID
    )

    too_late = import_data(
        bound_plan, expiry="2026-10-25T02:00:00.234568Z"
    )
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(too_late)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID
    )


def test_naive_timestamps_are_rejected() -> None:
    data = import_data(
        plan(),
        execution_timestamps={
            "execution_started_at": "2026-07-27T01:00:00.123456",
            "execution_completed_at": "2026-07-27T02:00:00.234567Z",
        },
    )
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(
        caught, ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID
    )


def test_result_is_not_approval_or_registry_authority() -> None:
    result = import_manual_validation_evidence(request(), plan=plan())
    for forbidden in (
        "approve",
        "admit",
        "register",
        "connect",
        "write",
        "transport",
    ):
        assert forbidden not in dir(result)


def test_public_api_is_exported_from_package() -> None:
    for name in (
        "ManualEvidenceImportRequest",
        "ManualEvidenceImportResult",
        "ManualEvidenceImportError",
        "ManualEvidenceImportErrorCategory",
        "ManualEvidenceSourceKind",
        "import_manual_validation_evidence",
    ):
        assert name in ragguard.__all__
        assert getattr(ragguard, name)


def test_error_categories_are_complete_and_deterministic() -> None:
    assert tuple(item.value for item in ManualEvidenceImportErrorCategory) == (
        "input_type_invalid",
        "schema_invalid",
        "unknown_field",
        "required_field_missing",
        "size_limit_exceeded",
        "identifier_invalid",
        "version_invalid",
        "timestamp_invalid",
        "digest_invalid",
        "plan_binding_invalid",
        "case_set_invalid",
        "case_result_invalid",
        "environment_invalid",
        "cleanup_invalid",
        "non_disclosure_invalid",
        "unsafe_content",
        "evidence_construction_failed",
    )


@pytest.mark.parametrize(
    ("field", "category"),
    [
        ("cleanup_declarations", ManualEvidenceImportErrorCategory.CLEANUP_INVALID),
        (
            "non_disclosure_declarations",
            ManualEvidenceImportErrorCategory.NON_DISCLOSURE_INVALID,
        ),
    ],
)
def test_required_true_declarations_fail_closed(
    field: str,
    category: ManualEvidenceImportErrorCategory,
) -> None:
    data = import_data(plan())
    declarations = data[field]
    assert isinstance(declarations, dict)
    first_key = next(iter(declarations))
    declarations[first_key] = False
    data["source_digest"] = source_digest(data)
    with pytest.raises(ManualEvidenceImportError) as caught:
        ManualEvidenceImportRequest.from_mapping(data)
    assert_safe_error(caught, category)


def test_phase_d_design_and_status_are_documented() -> None:
    root = Path(__file__).parents[1]
    design = (
        root / "docs" / "PRODUCTION_ADMISSION_DESIGN_V0.11.md"
    ).read_text(encoding="utf-8")
    notes = (root / "docs" / "DESIGN_NOTES.md").read_text(encoding="utf-8")
    roadmap = (root / "ROADMAP.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    for required in (
        "`inline_safe_fixture`",
        "`ManualEvidenceImportRequest`",
        "`ManualEvidenceImportResult`",
        "`import_manual_validation_evidence()`",
        "one-microsecond differences do not",
        "not manual-validation execution",
    ):
        assert required in design
    assert "v0.11 Phase D implementation status" in notes
    assert "Phase D delivery" in roadmap
    assert "Phase D immutable `ManualEvidenceImportRequest`" in changelog
