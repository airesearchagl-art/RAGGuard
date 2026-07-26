from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ragguard.manual_validation_evidence import (
    EvidenceCaseOutcome,
    ManualValidationEvidence,
)
from ragguard.manual_validation_plan import (
    REQUIRED_ABORT_CONDITIONS,
    REQUIRED_CLEANUP_CONDITIONS,
    REQUIRED_MANUAL_VALIDATION_CASES,
    ManualValidationPlan,
)
from ragguard.production_admission import (
    ProductionAdmissionDecision,
    ProductionAdmissionError,
    ProductionAdmissionErrorCategory,
    ProductionAdmissionReason,
    ProductionAdmissionRequest,
    ReviewerAttestation,
    ReviewerAttestationOutcome,
    RevalidationTrigger,
    evaluate_production_admission,
)
from ragguard.production_registry import RegistryKind, RegistryStatus
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalMetadata,
    ApprovalRestrictions,
    ProfileMaturity,
    ValidationMetadata,
)


MODULE = (
    Path(__file__).parents[1] / "src" / "ragguard" / "production_admission.py"
)
EVALUATION_TIME = datetime(
    2026, 7, 27, 3, 0, 0, 345678, tzinfo=timezone.utc
)
VALIDATION_CASES = tuple(
    sorted(
        {
            "schema_validation",
            "synthetic_compatibility",
            "security_e2e",
            "capability_mapping",
            "request_response_mapping",
            "score_semantics",
            "source_identifier_policy",
            "timeout_boundary",
            "response_size_boundary",
            "error_non_disclosure",
            "manual_compatibility",
        }
    )
)
REQUIRED_CAPABILITIES = tuple(
    sorted(
        {
            "retrieval",
            "bounded_top_k",
            "deterministic_result_schema",
            "safe_source_identifier",
            "response_size_compliance",
        }
    )
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


def evidence_data(
    plan: ManualValidationPlan, **overrides: object
) -> dict[str, object]:
    value: dict[str, object] = {
        "evidence_id": "manual-evidence-a1b2c3d4",
        "plan_id": plan.plan_id,
        "plan_digest": plan.canonical_digest,
        "profile_id": plan.profile_id,
        "profile_version": str(plan.profile_version),
        "protocol_version": str(plan.protocol_version),
        "product_id": plan.product_id,
        "planned_product_version": str(plan.product_version),
        "observed_product_version": str(plan.product_version),
        "execution_started_at": "2026-07-27T01:00:00.123456Z",
        "execution_completed_at": "2026-07-27T02:00:00.234567Z",
        "validation_operator_id": plan.validation_operator_id,
        "evidence_reviewer_id": plan.evidence_reviewer_id,
        "environment_fingerprint": {
            "environment_id": "environment-ref-1a2b3c4d",
            "os_family": "windows",
            "architecture": "x86_64",
            "python_version": "3.12.13",
            "ragguard_version": "0.11.0",
            "adapter_id": "adapter-fixture-alpha",
            "profile_id": plan.profile_id,
        },
        "tool_version": "0.11.0",
        "case_results": [
            {
                "case_id": item.value,
                "outcome": "passed",
                "executed_at": "2026-07-27T01:30:00.123456Z",
                "safe_observation": "case_passed",
                "failure_category": None,
                "cleanup_confirmed": True,
            }
            for item in REQUIRED_MANUAL_VALIDATION_CASES
        ],
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


def validation_metadata(**overrides: object) -> ValidationMetadata:
    value: dict[str, object] = {
        "validation_record_id": "validation-001",
        "profile_id": "synthetic-profile",
        "profile_version": "1.2.3",
        "protocol_version": "1.0.0",
        "normalized_product_version": "2.3.4",
        "validation_status": "passed",
        "validated_at": "2026-07-26T12:00:00Z",
        "validation_cases": list(VALIDATION_CASES),
        "required_capabilities_result": True,
        "optional_capabilities_result": [],
        "safe_error_categories": [],
        "result_summary": "validation_passed",
    }
    value.update(overrides)
    return ValidationMetadata.from_mapping(value)


def approval_metadata(**overrides: object) -> ApprovalMetadata:
    value: dict[str, object] = {
        "approval_record_id": "approval-001",
        "reviewer_id": "reviewer-001",
        "approver_id": "approver-001",
        "decision": "approved",
        "approved_at": "2026-07-27T02:45:00.234567Z",
        "validation_record_id": "validation-001",
        "supported_product_version_range": {
            "minimum_version": "2.3.4",
            "maximum_version": "2.3.4",
            "open_ended": False,
        },
        "approved_capabilities": list(REQUIRED_CAPABILITIES),
        "approved_score_semantics": "unscored",
        "approved_source_identifier_policy": "opaque_safe_id",
        "restrictions": None,
        "expires_at": "2026-09-01T00:00:00Z",
    }
    value.update(overrides)
    return ApprovalMetadata.from_mapping(value)


def valid_contracts() -> tuple[ManualValidationPlan, ManualValidationEvidence]:
    plan = ManualValidationPlan.from_mapping(plan_data())
    evidence = ManualValidationEvidence.from_mapping(
        evidence_data(plan), plan=plan
    )
    return plan, evidence


def attestation(
    plan: ManualValidationPlan,
    evidence: ManualValidationEvidence,
    **overrides: object,
) -> ReviewerAttestation:
    values: dict[str, object] = {
        "attestation_id": "attestation-001",
        "reviewer_id": plan.evidence_reviewer_id,
        "evidence_id": evidence.evidence_id,
        "evidence_digest": evidence.canonical_digest,
        "plan_id": plan.plan_id,
        "plan_digest": plan.canonical_digest,
        "reviewed_at": datetime(
            2026, 7, 27, 2, 30, 0, 234567, tzinfo=timezone.utc
        ),
        "outcome": ReviewerAttestationOutcome.ACCEPTED,
    }
    values.update(overrides)
    return ReviewerAttestation(**values)  # type: ignore[arg-type]


def request(**overrides: object) -> ProductionAdmissionRequest:
    plan, evidence = valid_contracts()
    values: dict[str, object] = {
        "request_id": "admission-request-001",
        "evaluation_time": EVALUATION_TIME,
        "manual_validation_plan": plan,
        "manual_validation_evidence": evidence,
        "synthetic_validation_reference": plan.synthetic_evidence_reference,
        "profile_approval_metadata": approval_metadata(),
        "profile_validation_metadata": validation_metadata(),
        "reviewer_attestation": attestation(plan, evidence),
        "approver_identity": plan.approver_id,
        "requested_registry_kind": RegistryKind.PRODUCTION,
        "requested_initial_status": RegistryStatus.ACTIVE,
        "requested_restrictions": None,
        "safe_context": (
            "no_credentials",
            "no_real_documents",
            "synthetic_only",
        ),
        "profile_maturity": ProfileMaturity.MANUALLY_VALIDATED,
        "validation_expires_at": datetime(
            2026, 9, 1, tzinfo=timezone.utc
        ),
        "revalidation_triggers": (),
    }
    values.update(overrides)
    return ProductionAdmissionRequest(**values)  # type: ignore[arg-type]


def test_valid_request_returns_approved_eligible_decision() -> None:
    result = evaluate_production_admission(request())

    assert result.decision is ApprovalDecision.APPROVED
    assert result.eligible_for_registry_admission is True
    assert result.reason_categories == ()
    assert result.effective_restrictions is None
    assert result.canonical_digest.startswith("sha256:")
    assert result.safe_summary.canonical_digest == result.canonical_digest
    assert isinstance(result, ProductionAdmissionDecision)


def test_valid_explicit_restriction_returns_restricted_decision() -> None:
    restrictions = ApprovalRestrictions(maximum_top_k=5)
    result = evaluate_production_admission(
        request(
            requested_restrictions=restrictions,
            profile_approval_metadata=approval_metadata(
                decision="approved_with_restrictions",
                restrictions={"maximum_top_k": 5},
            ),
        )
    )

    assert result.decision is ApprovalDecision.APPROVED_WITH_RESTRICTIONS
    assert result.eligible_for_registry_admission is True
    assert result.effective_restrictions == restrictions
    assert result.safe_summary.restriction_count == 1


@pytest.mark.parametrize(
    ("outcome", "decision", "reason"),
    [
        (
            ReviewerAttestationOutcome.REJECTED,
            ApprovalDecision.REJECTED,
            ProductionAdmissionReason.REVIEWER_REJECTED,
        ),
        (
            ReviewerAttestationOutcome.NEEDS_REVALIDATION,
            ApprovalDecision.NEEDS_REVALIDATION,
            ProductionAdmissionReason.REVALIDATION_REQUIRED,
        ),
    ],
)
def test_reviewer_outcome_controls_fail_closed_decision(
    outcome: ReviewerAttestationOutcome,
    decision: ApprovalDecision,
    reason: ProductionAdmissionReason,
) -> None:
    base = request()
    record = attestation(
        base.manual_validation_plan,
        base.manual_validation_evidence,
        outcome=outcome,
    )
    result = evaluate_production_admission(
        replace(base, reviewer_attestation=record)
    )

    assert result.decision is decision
    assert result.eligible_for_registry_admission is False
    assert reason in result.reason_categories


def test_missing_attestation_is_rejected() -> None:
    result = evaluate_production_admission(
        request(reviewer_attestation=None)
    )
    assert result.decision is ApprovalDecision.REJECTED
    assert result.reason_categories == (
        ProductionAdmissionReason.REVIEWER_ATTESTATION_MISSING,
    )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("evidence_id", "manual-evidence-other"),
        ("evidence_digest", "sha256:" + "1" * 64),
        ("plan_id", "manual-plan-other"),
        ("plan_digest", "sha256:" + "2" * 64),
        ("reviewer_id", "reviewer-other"),
    ],
)
def test_attestation_exact_binding_mismatch_is_rejected(
    field_name: str, replacement: object
) -> None:
    base = request()
    record = replace(
        base.reviewer_attestation,
        **{field_name: replacement},
    )
    result = evaluate_production_admission(
        replace(base, reviewer_attestation=record)
    )
    assert result.decision is ApprovalDecision.REJECTED
    assert (
        ProductionAdmissionReason.REVIEWER_ATTESTATION_INVALID
        in result.reason_categories
    )


def test_attestation_digest_tampering_is_rejected() -> None:
    base = request()
    record = base.reviewer_attestation
    assert record is not None
    object.__setattr__(record, "canonical_digest", "sha256:" + "f" * 64)
    result = evaluate_production_admission(base)
    assert result.decision is ApprovalDecision.REJECTED
    assert (
        ProductionAdmissionReason.REVIEWER_ATTESTATION_INVALID
        in result.reason_categories
    )


@pytest.mark.parametrize(
    "reviewed_at",
    [
        datetime(2026, 7, 27, 1, 59, tzinfo=timezone.utc),
        EVALUATION_TIME + timedelta(microseconds=1),
        datetime(2026, 8, 26, 2, 0, 0, 234567, tzinfo=timezone.utc),
    ],
)
def test_invalid_attestation_time_is_rejected(reviewed_at: datetime) -> None:
    base = request()
    record = attestation(
        base.manual_validation_plan,
        base.manual_validation_evidence,
        reviewed_at=reviewed_at,
    )
    result = evaluate_production_admission(
        replace(base, reviewer_attestation=record)
    )
    assert result.decision is ApprovalDecision.REJECTED
    assert (
        ProductionAdmissionReason.REVIEWER_ATTESTATION_INVALID
        in result.reason_categories
    )


def test_evidence_completion_boundary_is_valid() -> None:
    base = request()
    evaluation = base.manual_validation_evidence.execution_completed_at
    record = attestation(
        base.manual_validation_plan,
        base.manual_validation_evidence,
        reviewed_at=evaluation,
    )
    result = evaluate_production_admission(
        replace(
            base,
            evaluation_time=evaluation,
            reviewer_attestation=record,
            profile_approval_metadata=approval_metadata(
                approved_at="2026-07-27T02:00:00.234567Z"
            ),
        )
    )
    assert result.decision is ApprovalDecision.APPROVED


def test_evidence_before_completion_needs_revalidation() -> None:
    base = request()
    evaluation = (
        base.manual_validation_evidence.execution_completed_at
        - timedelta(microseconds=1)
    )
    record = attestation(
        base.manual_validation_plan,
        base.manual_validation_evidence,
        reviewed_at=base.manual_validation_evidence.execution_completed_at,
    )
    result = evaluate_production_admission(
        replace(base, evaluation_time=evaluation, reviewer_attestation=record)
    )
    assert result.decision is ApprovalDecision.REJECTED
    assert (
        ProductionAdmissionReason.EVIDENCE_NOT_YET_VALID
        in result.reason_categories
    )
    assert (
        ProductionAdmissionReason.REVIEWER_ATTESTATION_INVALID
        in result.reason_categories
    )


def test_evidence_expiry_boundary_needs_revalidation() -> None:
    base = request()
    result = evaluate_production_admission(
        replace(
            base,
            evaluation_time=base.manual_validation_evidence.expires_at,
        )
    )
    assert result.decision is ApprovalDecision.NEEDS_REVALIDATION
    assert result.reason_categories == (
        ProductionAdmissionReason.EVIDENCE_EXPIRED,
    )


@pytest.mark.parametrize(
    "maturity",
    [
        ProfileMaturity.DRAFT,
        ProfileMaturity.SYNTHETIC_VALIDATED,
        ProfileMaturity.APPROVED,
        ProfileMaturity.DEPRECATED,
        ProfileMaturity.REVOKED,
    ],
)
def test_only_manually_validated_maturity_is_eligible(
    maturity: ProfileMaturity,
) -> None:
    result = evaluate_production_admission(
        request(profile_maturity=maturity)
    )
    assert result.decision is ApprovalDecision.REJECTED
    assert result.reason_categories == (
        ProductionAdmissionReason.MATURITY_INELIGIBLE,
    )


def test_revalidation_trigger_prevents_admission() -> None:
    result = evaluate_production_admission(
        request(
            revalidation_triggers=(
                RevalidationTrigger.PRODUCT_VERSION_CHANGED,
            )
        )
    )
    assert result.decision is ApprovalDecision.NEEDS_REVALIDATION
    assert result.eligible_for_registry_admission is False
    assert result.reason_categories == (
        ProductionAdmissionReason.REVALIDATION_REQUIRED,
    )


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        (RegistryKind.TEST, RegistryStatus.ACTIVE),
        (RegistryKind.PRODUCTION, RegistryStatus.SUSPENDED),
    ],
)
def test_registry_request_is_exact_and_pre_admission_only(
    kind: RegistryKind, status: RegistryStatus
) -> None:
    with pytest.raises(ProductionAdmissionError) as caught:
        request(
            requested_registry_kind=kind,
            requested_initial_status=status,
        )
    assert caught.value.category is (
        ProductionAdmissionErrorCategory.REGISTRY_REQUEST_INVALID
    )


def test_unknown_restriction_is_rejected_as_typed_safe_error() -> None:
    with pytest.raises(ProductionAdmissionError) as caught:
        request(requested_restrictions={"unknown": True})
    assert caught.value.category is ProductionAdmissionErrorCategory.RESTRICTION_INVALID
    assert str(caught.value) == "restriction_invalid"


def test_unknown_safe_context_is_rejected() -> None:
    with pytest.raises(ProductionAdmissionError) as caught:
        request(safe_context=("endpoint_detail",))
    assert caught.value.category is (
        ProductionAdmissionErrorCategory.SECURITY_BOUNDARY_VIOLATION
    )


def test_restriction_conflict_is_rejected() -> None:
    result = evaluate_production_admission(
        request(
            requested_restrictions=ApprovalRestrictions(
                supported_minor_versions=("9.9",)
            )
        )
    )
    assert result.decision is ApprovalDecision.REJECTED
    assert result.reason_categories == (
        ProductionAdmissionReason.RESTRICTION_INVALID,
    )


def test_approval_before_review_is_rejected() -> None:
    result = evaluate_production_admission(
        request(
            profile_approval_metadata=approval_metadata(
                approved_at="2026-07-27T02:00:00.234567Z"
            )
        )
    )
    assert result.decision is ApprovalDecision.REJECTED
    assert result.reason_categories == (
        ProductionAdmissionReason.REVIEWER_ATTESTATION_INVALID,
    )


def test_unsupported_product_version_needs_revalidation() -> None:
    unsupported = approval_metadata(
        supported_product_version_range={
            "minimum_version": "2.2.0",
            "maximum_version": "2.2.9",
            "open_ended": False,
        }
    )
    result = evaluate_production_admission(
        request(profile_approval_metadata=unsupported)
    )
    assert result.decision is ApprovalDecision.NEEDS_REVALIDATION
    assert result.reason_categories == (
        ProductionAdmissionReason.VERSION_UNSUPPORTED,
    )


def test_approval_and_validation_expiration_need_revalidation() -> None:
    expired_approval = approval_metadata(
        expires_at="2026-07-27T03:00:00.345678Z"
    )
    result = evaluate_production_admission(
        request(
            profile_approval_metadata=expired_approval,
            validation_expires_at=EVALUATION_TIME,
        )
    )
    assert result.decision is ApprovalDecision.NEEDS_REVALIDATION
    assert result.reason_categories == (
        ProductionAdmissionReason.REVALIDATION_REQUIRED,
    )


def test_restriction_expiration_needs_revalidation() -> None:
    restrictions = {
        "maximum_top_k": 5,
        "expires_at": "2026-07-27T03:00:00.345678Z",
    }
    metadata = approval_metadata(
        decision="approved_with_restrictions",
        restrictions=restrictions,
    )
    result = evaluate_production_admission(
        request(
            profile_approval_metadata=metadata,
            requested_restrictions=metadata.restrictions,
        )
    )
    assert result.decision is ApprovalDecision.NEEDS_REVALIDATION
    assert result.reason_categories == (
        ProductionAdmissionReason.REVALIDATION_REQUIRED,
    )


def test_identity_mismatch_is_rejected_before_freshness() -> None:
    mismatched = validation_metadata(profile_id="other-profile")
    result = evaluate_production_admission(
        request(
            profile_validation_metadata=mismatched,
            revalidation_triggers=(
                RevalidationTrigger.PRODUCT_VERSION_CHANGED,
            ),
        )
    )
    assert result.decision is ApprovalDecision.REJECTED
    assert result.reason_categories == (
        ProductionAdmissionReason.IDENTITY_MISMATCH,
        ProductionAdmissionReason.REVALIDATION_REQUIRED,
    )


@pytest.mark.parametrize(
    "mutation",
    ["failed_case", "cleanup", "non_disclosure", "product_version"],
)
def test_tampered_or_invalid_evidence_is_rejected(mutation: str) -> None:
    base = request()
    evidence = base.manual_validation_evidence
    if mutation == "failed_case":
        object.__setattr__(
            evidence.case_results[0],
            "outcome",
            EvidenceCaseOutcome.FAILED,
        )
    elif mutation == "cleanup":
        object.__setattr__(
            evidence.case_results[0],
            "cleanup_confirmed",
            False,
        )
    elif mutation == "non_disclosure":
        object.__setattr__(
            evidence.non_disclosure_evidence,
            "no_credential_disclosure",
            False,
        )
    else:
        object.__setattr__(
            evidence,
            "observed_product_version",
            evidence.profile_version,
        )
    result = evaluate_production_admission(base)
    assert result.decision is ApprovalDecision.REJECTED
    assert ProductionAdmissionReason.EVIDENCE_INVALID in result.reason_categories


def test_role_tampering_is_rejected() -> None:
    base = request()
    object.__setattr__(
        base.manual_validation_plan,
        "profile_implementer_id",
        base.approver_identity,
    )
    result = evaluate_production_admission(base)
    assert result.decision is ApprovalDecision.REJECTED
    assert ProductionAdmissionReason.ROLE_CONFLICT in result.reason_categories
    assert (
        ProductionAdmissionReason.PLAN_BINDING_INVALID
        in result.reason_categories
    )


def test_reason_order_and_digest_are_deterministic() -> None:
    first = evaluate_production_admission(
        request(
            profile_maturity=ProfileMaturity.DRAFT,
            revalidation_triggers=(
                RevalidationTrigger.PRODUCT_VERSION_CHANGED,
            ),
        )
    )
    second = evaluate_production_admission(
        request(
            profile_maturity=ProfileMaturity.DRAFT,
            revalidation_triggers=(
                RevalidationTrigger.PRODUCT_VERSION_CHANGED,
            ),
        )
    )
    assert first.reason_categories == second.reason_categories
    assert first.canonical_digest == second.canonical_digest


def test_equivalent_instant_has_same_digest() -> None:
    offset = timezone(timedelta(hours=9))
    first = evaluate_production_admission(request())
    second = evaluate_production_admission(
        request(evaluation_time=EVALUATION_TIME.astimezone(offset))
    )
    assert first.canonical_digest == second.canonical_digest


def test_microsecond_change_changes_digest() -> None:
    first = evaluate_production_admission(request())
    second = evaluate_production_admission(
        request(evaluation_time=EVALUATION_TIME + timedelta(microseconds=1))
    )
    assert first.canonical_digest != second.canonical_digest


def test_result_and_nested_inputs_are_immutable() -> None:
    base = request()
    result = evaluate_production_admission(base)
    with pytest.raises(FrozenInstanceError):
        result.decision = ApprovalDecision.REJECTED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        base.request_id = "changed"  # type: ignore[misc]


def test_safe_summary_and_errors_do_not_disclose_sensitive_details() -> None:
    result = evaluate_production_admission(request())
    rendered = repr(result.safe_summary).lower()
    for forbidden in (
        "endpoint",
        "credential",
        "token",
        "cookie",
        "api_key",
        "hostname",
        "username",
        "payload",
        "stack trace",
    ):
        assert forbidden not in rendered
    with pytest.raises(ProductionAdmissionError) as caught:
        request(evaluation_time=datetime(2026, 7, 27))
    assert str(caught.value) == "production_admission_request_invalid"


def test_attestation_and_result_represent_no_registry_authority() -> None:
    record = request().reviewer_attestation
    result = evaluate_production_admission(request())
    assert record is not None
    for value in (record, result):
        for forbidden in (
            "register",
            "write",
            "persist",
            "authorize",
            "transport",
            "connect",
        ):
            assert not hasattr(value, forbidden)


def test_module_has_no_io_network_clock_random_or_uuid_dependencies() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint(
        {
            "asyncio",
            "http",
            "os",
            "pathlib",
            "random",
            "requests",
            "secrets",
            "socket",
            "subprocess",
            "time",
            "urllib",
            "uuid",
        }
    )
    source = MODULE.read_text(encoding="utf-8")
    assert "datetime.now" not in source
    assert "datetime.utcnow" not in source
    assert "RegistryEntry(" not in source


def test_revalidation_trigger_input_is_explicit_and_canonical() -> None:
    with pytest.raises(ProductionAdmissionError) as caught:
        request(
            revalidation_triggers=(
                RevalidationTrigger.TRANSPORT_CHANGED,
                RevalidationTrigger.PRODUCT_VERSION_CHANGED,
            )
        )
    assert caught.value.category is (
        ProductionAdmissionErrorCategory.REVALIDATION_TRIGGER_INVALID
    )
