from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from ragguard.manual_validation_plan import (
    CANONICAL_DIGEST_ALGORITHM,
    MAX_EXECUTION_WINDOW,
    ManualValidationPlan,
    ManualValidationPlanError,
    ManualValidationPlanErrorCategory,
    REQUIRED_ABORT_CONDITIONS,
    REQUIRED_CLEANUP_CONDITIONS,
    REQUIRED_MANUAL_VALIDATION_CASES,
)


MODULE = Path(__file__).parents[1] / "src" / "ragguard" / "manual_validation_plan.py"


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
            value.value for value in REQUIRED_MANUAL_VALIDATION_CASES
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
        "abort_conditions": [value.value for value in REQUIRED_ABORT_CONDITIONS],
        "cleanup_conditions": [
            value.value for value in REQUIRED_CLEANUP_CONDITIONS
        ],
        "synthetic_evidence_reference": {
            "reference_id": "synthetic-evidence-a17c0e01",
            "profile_id": "synthetic-profile",
            "profile_version": "1.2.3",
        },
    }
    value.update(overrides)
    return value


def assert_safe_error(
    caught: pytest.ExceptionInfo[ManualValidationPlanError],
    category: ManualValidationPlanErrorCategory,
) -> None:
    assert caught.value.category is category
    assert str(caught.value) == category.value
    assert repr(caught.value) == f"ManualValidationPlanError('{category.value}')"
    assert caught.value.__cause__ is None


def test_valid_plan_is_immutable_hashable_and_bounded() -> None:
    plan = ManualValidationPlan.from_mapping(plan_data())

    assert plan.plan_id == "manual-plan-001"
    assert str(plan.profile_version) == "1.2.3"
    assert str(plan.product_version) == "2.3.4"
    assert plan.digest_algorithm == CANONICAL_DIGEST_ALGORITHM
    assert plan.canonical_digest.startswith("sha256:")
    assert len(plan.required_case_ids) == 22
    assert hash(plan)
    assert MAX_EXECUTION_WINDOW.days == 30

    with pytest.raises(FrozenInstanceError):
        plan.plan_id = "manual-plan-002"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.endpoint_boundary.category = "unsafe"  # type: ignore[misc]


def test_plan_exposes_the_complete_phase_a_field_contract() -> None:
    assert tuple(field.name for field in fields(ManualValidationPlan)) == (
        "plan_id",
        "profile_id",
        "profile_version",
        "protocol_version",
        "product_id",
        "product_version",
        "created_at",
        "execution_window_start",
        "execution_window_end",
        "profile_implementer_id",
        "validation_operator_id",
        "evidence_reviewer_id",
        "approver_id",
        "registry_administrator_id",
        "required_case_ids",
        "endpoint_boundary",
        "data_boundary",
        "credential_boundary",
        "abort_conditions",
        "cleanup_conditions",
        "synthetic_evidence_reference",
        "safe_summary",
        "canonical_digest",
    )


def test_digest_and_canonical_serialization_are_deterministic() -> None:
    first = ManualValidationPlan.from_mapping(plan_data())
    reordered = dict(reversed(list(plan_data().items())))
    second = ManualValidationPlan.from_mapping(reordered)

    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_digest == second.canonical_digest
    assert first.safe_summary.canonical_digest == first.canonical_digest


def test_field_change_changes_digest() -> None:
    first = ManualValidationPlan.from_mapping(plan_data())
    second = ManualValidationPlan.from_mapping(
        plan_data(product_version="2.3.5")
    )
    assert first.canonical_digest != second.canonical_digest


@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("created_at", "2026-07-26T00:00:00.000001Z"),
        ("execution_window_start", "2026-07-27T00:00:00.000001Z"),
        ("execution_window_end", "2026-07-28T00:00:00.000001Z"),
    ],
)
def test_timestamp_microsecond_change_changes_digest(
    field: str, changed_value: str
) -> None:
    baseline = ManualValidationPlan.from_mapping(plan_data())
    changed = ManualValidationPlan.from_mapping(
        plan_data(**{field: changed_value})
    )
    assert baseline.canonical_digest != changed.canonical_digest


def test_equivalent_instants_with_different_offsets_have_same_digest() -> None:
    utc_plan = ManualValidationPlan.from_mapping(
        plan_data(
            created_at="2026-07-26T00:00:00.123456Z",
            execution_window_start="2026-07-27T00:00:00.234567Z",
            execution_window_end="2026-07-28T00:00:00.345678Z",
        )
    )
    offset_plan = ManualValidationPlan.from_mapping(
        plan_data(
            created_at="2026-07-26T09:00:00.123456+09:00",
            execution_window_start="2026-07-27T09:00:00.234567+09:00",
            execution_window_end="2026-07-28T09:00:00.345678+09:00",
        )
    )
    assert utc_plan.canonical_json() == offset_plan.canonical_json()
    assert utc_plan.canonical_digest == offset_plan.canonical_digest


def test_safe_summary_uses_canonical_utc_microsecond_timestamps() -> None:
    plan = ManualValidationPlan.from_mapping(
        plan_data(
            created_at="2026-07-26T09:00:00.123456+09:00",
            execution_window_start="2026-07-27T09:00:00.234567+09:00",
            execution_window_end="2026-07-28T09:00:00.345678+09:00",
        )
    )
    canonical = json.loads(plan.canonical_json())

    assert plan.safe_summary.execution_window_start == (
        "2026-07-27T00:00:00.234567Z"
    )
    assert plan.safe_summary.execution_window_end == (
        "2026-07-28T00:00:00.345678Z"
    )
    assert (
        plan.safe_summary.execution_window_start
        == canonical["execution_window_start"]
    )
    assert (
        plan.safe_summary.execution_window_end
        == canonical["execution_window_end"]
    )
    assert canonical["created_at"] == "2026-07-26T00:00:00.123456Z"


@pytest.mark.parametrize(
    ("field", "conflicting_field"),
    [
        ("evidence_reviewer_id", "approver_id"),
        ("validation_operator_id", "evidence_reviewer_id"),
        ("profile_implementer_id", "approver_id"),
    ],
)
def test_required_role_separation_is_fail_closed(
    field: str, conflicting_field: str
) -> None:
    data = plan_data()
    data[field] = data[conflicting_field]
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(data)
    assert_safe_error(
        caught, ManualValidationPlanErrorCategory.ROLE_SEPARATION_INVALID
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_implementer_id", ""),
        ("validation_operator_id", "person@example.test"),
        ("evidence_reviewer_id", "credential-owner"),
        ("approver_id", "Real Person"),
        ("registry_administrator_id", "token-holder"),
    ],
)
def test_roles_accept_only_safe_opaque_identifiers(field: str, value: object) -> None:
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(plan_data(**{field: value}))
    assert_safe_error(
        caught, ManualValidationPlanErrorCategory.ROLE_SEPARATION_INVALID
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_version", "1.2"),
        ("profile_version", "1.2.*"),
        ("protocol_version", ">=1.0.0"),
        ("product_version", "nearest"),
        ("product_version", True),
        ("product_version", 1),
    ],
)
def test_versions_require_exact_strict_semantic_version(
    field: str, value: object
) -> None:
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(plan_data(**{field: value}))
    assert_safe_error(caught, ManualValidationPlanErrorCategory.VERSION_INVALID)


@pytest.mark.parametrize(
    "overrides",
    [
        {"created_at": "2026-07-26T00:00:00"},
        {"execution_window_start": "2026-07-27T00:00:00"},
        {"execution_window_end": "2026-07-28T00:00:00"},
        {
            "created_at": "2026-07-28T00:00:00Z",
            "execution_window_start": "2026-07-27T00:00:00Z",
        },
        {
            "execution_window_start": "2026-07-28T00:00:00Z",
            "execution_window_end": "2026-07-28T00:00:00Z",
        },
        {
            "execution_window_start": "2026-07-27T00:00:00Z",
            "execution_window_end": "2026-08-27T00:00:01Z",
        },
    ],
)
def test_execution_window_requires_explicit_aware_consistent_timestamps(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(plan_data(**overrides))
    assert_safe_error(
        caught, ManualValidationPlanErrorCategory.EXECUTION_WINDOW_INVALID
    )


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown"])
def test_required_case_set_is_exact(mode: str) -> None:
    cases = [value.value for value in REQUIRED_MANUAL_VALIDATION_CASES]
    if mode == "missing":
        cases.pop()
    elif mode == "duplicate":
        cases[-1] = cases[0]
    else:
        cases[-1] = "optional_case"
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(plan_data(required_case_ids=cases))
    assert_safe_error(
        caught, ManualValidationPlanErrorCategory.REQUIRED_CASES_INVALID
    )


def test_required_case_order_is_canonical_and_input_is_defensively_copied() -> None:
    cases = [value.value for value in reversed(REQUIRED_MANUAL_VALIDATION_CASES)]
    data = plan_data(required_case_ids=cases)
    plan = ManualValidationPlan.from_mapping(data)
    cases.clear()

    assert plan.required_case_ids == REQUIRED_MANUAL_VALIDATION_CASES
    assert len(plan.required_case_ids) == 22


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("approved_boundary_marker", "localhost"),
        ("opaque_endpoint_reference", "127.0.0.1"),
        ("opaque_endpoint_reference", "endpoint-ref-alpha:8080"),
        ("opaque_endpoint_reference", "https://example.test/path"),
        ("opaque_endpoint_reference", "/private/path"),
        ("opaque_endpoint_reference", "endpoint-ref-alpha?query=value"),
        ("opaque_endpoint_reference", "endpoint-ref-token"),
    ],
)
def test_endpoint_boundary_cannot_represent_endpoint_details(
    field: str, value: object
) -> None:
    boundary = dict(plan_data()["endpoint_boundary"])  # type: ignore[arg-type]
    boundary[field] = value
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(plan_data(endpoint_boundary=boundary))
    assert_safe_error(
        caught, ManualValidationPlanErrorCategory.ENDPOINT_BOUNDARY_INVALID
    )


@pytest.mark.parametrize("field", ["synthetic_only", "safe_summary_only"])
def test_data_boundary_rejects_unsafe_or_non_boolean_declarations(field: str) -> None:
    boundary = dict(plan_data()["data_boundary"])  # type: ignore[arg-type]
    boundary[field] = False if field == "synthetic_only" else 1
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(plan_data(data_boundary=boundary))
    assert_safe_error(
        caught, ManualValidationPlanErrorCategory.DATA_BOUNDARY_INVALID
    )


@pytest.mark.parametrize("value", [False, 1, "true"])
def test_credentials_are_structurally_prohibited(value: object) -> None:
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(
            plan_data(credential_boundary={"credentials_prohibited": value})
        )
    assert_safe_error(
        caught, ManualValidationPlanErrorCategory.CREDENTIAL_BOUNDARY_INVALID
    )


def test_credential_reference_is_an_unknown_field() -> None:
    data = plan_data()
    data["credential_reference"] = "not-retained"
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(data)
    assert_safe_error(caught, ManualValidationPlanErrorCategory.FIELD_SET_INVALID)


@pytest.mark.parametrize(
    ("field", "required", "category"),
    [
        (
            "abort_conditions",
            REQUIRED_ABORT_CONDITIONS,
            ManualValidationPlanErrorCategory.ABORT_CONDITIONS_INVALID,
        ),
        (
            "cleanup_conditions",
            REQUIRED_CLEANUP_CONDITIONS,
            ManualValidationPlanErrorCategory.CLEANUP_CONDITIONS_INVALID,
        ),
    ],
)
@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown"])
def test_abort_and_cleanup_sets_are_exact(
    field: str,
    required: tuple,
    category: ManualValidationPlanErrorCategory,
    mode: str,
) -> None:
    values = [value.value for value in required]
    if mode == "missing":
        values.pop()
    elif mode == "duplicate":
        values[-1] = values[0]
    else:
        values[-1] = "unknown_condition"
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(plan_data(**{field: values}))
    assert_safe_error(caught, category)


@pytest.mark.parametrize(
    "reference_id",
    [
        "",
        "C:/reports/synthetic.json",
        "/reports/synthetic.json",
        "https://example.test/report",
        "synthetic-evidence-token",
    ],
)
def test_synthetic_evidence_reference_is_opaque_and_non_disclosing(
    reference_id: str,
) -> None:
    reference = dict(plan_data()["synthetic_evidence_reference"])  # type: ignore[arg-type]
    reference["reference_id"] = reference_id
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(
            plan_data(synthetic_evidence_reference=reference)
        )
    assert_safe_error(
        caught, ManualValidationPlanErrorCategory.SYNTHETIC_EVIDENCE_INVALID
    )
    if reference_id:
        assert reference_id not in str(caught.value)


def test_synthetic_evidence_requires_exact_profile_identity() -> None:
    reference = dict(plan_data()["synthetic_evidence_reference"])  # type: ignore[arg-type]
    reference["profile_version"] = "1.2.4"
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(
            plan_data(synthetic_evidence_reference=reference)
        )
    assert_safe_error(
        caught, ManualValidationPlanErrorCategory.SYNTHETIC_EVIDENCE_INVALID
    )


def test_safe_summary_and_repr_do_not_disclose_boundary_references_or_roles() -> None:
    plan = ManualValidationPlan.from_mapping(plan_data())
    rendered = f"{plan.safe_summary!r} {plan!r}"
    for excluded in (
        "boundary-approved-isolated",
        "endpoint-ref-7f3a9c21",
        "synthetic-evidence-a17c0e01",
        "operator-001",
        "reviewer-001",
        "approver-001",
        "registry-admin-001",
    ):
        assert excluded not in rendered
    assert plan.safe_summary.case_count == 22
    assert plan.safe_summary.role_separation_valid is True
    assert plan.safe_summary.boundary_category == "loopback"


def test_error_does_not_replay_unsafe_endpoint_or_credential_value() -> None:
    unsafe = "https://user:credential@example.test/private?token=value"
    boundary = dict(plan_data()["endpoint_boundary"])  # type: ignore[arg-type]
    boundary["opaque_endpoint_reference"] = unsafe
    with pytest.raises(ManualValidationPlanError) as caught:
        ManualValidationPlan.from_mapping(plan_data(endpoint_boundary=boundary))
    assert unsafe not in str(caught.value)
    assert "credential" not in str(caught.value)
    assert "token" not in str(caught.value)


def test_contract_has_no_hidden_clock_random_uuid_io_network_or_filesystem() -> None:
    source = MODULE.read_text(encoding="utf-8")
    forbidden = (
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
    )
    for marker in forbidden:
        assert marker not in source


def test_plan_creation_is_not_validation_approval_admission_or_transport() -> None:
    plan = ManualValidationPlan.from_mapping(plan_data())
    public_names = set(dir(plan))
    for operation in (
        "execute",
        "connect",
        "request",
        "approve",
        "admit",
        "register",
        "write",
    ):
        assert operation not in public_names


def test_dataclass_replace_recomputes_derived_fields() -> None:
    plan = ManualValidationPlan.from_mapping(plan_data())
    updated = replace(plan, plan_id="manual-plan-002")
    assert updated.canonical_digest != plan.canonical_digest
    assert updated.safe_summary.plan_id == "manual-plan-002"
