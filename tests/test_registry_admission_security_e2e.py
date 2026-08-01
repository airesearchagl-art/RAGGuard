from __future__ import annotations

from datetime import timedelta

import pytest

import test_manual_evidence_import_boundary as phase_d
import test_production_admission_evaluator as phase_c
from test_registry_admission_enforcement import (
    EVALUATION_TIME,
    decision as enforcement_decision,
    request as enforcement_request,
    version,
)

from ragguard.manual_evidence_import import (
    import_manual_validation_evidence,
)
from ragguard.production_admission import (
    ProductionAdmissionReason,
    ProductionAdmissionRequest,
    evaluate_production_admission,
)
from ragguard.production_registry import (
    RegistryKind,
    RegistryStatus,
    TrustedProductionRegistry,
)
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalRestrictions,
    ProfileMaturity,
)
from ragguard.registry_admission import (
    RegistryAdmissionReason,
    RegistryAdmissionRequest,
    RegistryAdmissionResult,
    TestRegistryAdmissionStore,
    enforce_registry_admission,
)


def lifecycle_request() -> RegistryAdmissionRequest:
    plan = phase_d.plan()
    imported = import_manual_validation_evidence(
        phase_d.request(plan), plan=plan
    )
    assert imported.accepted is True
    assert imported.evidence is not None
    evidence = imported.evidence
    admission_input = ProductionAdmissionRequest(
        request_id="admission-request-e2e",
        evaluation_time=phase_c.EVALUATION_TIME,
        manual_validation_plan=plan,
        manual_validation_evidence=evidence,
        synthetic_validation_reference=plan.synthetic_evidence_reference,
        profile_approval_metadata=phase_c.approval_metadata(),
        profile_validation_metadata=phase_c.validation_metadata(),
        reviewer_attestation=phase_c.attestation(plan, evidence),
        approver_identity=plan.approver_id,
        requested_registry_kind=RegistryKind.PRODUCTION,
        requested_initial_status=RegistryStatus.ACTIVE,
        requested_restrictions=None,
        safe_context=(
            "no_credentials",
            "no_real_documents",
            "synthetic_only",
        ),
        profile_maturity=ProfileMaturity.MANUALLY_VALIDATED,
        validation_expires_at=phase_c.EVALUATION_TIME
        + timedelta(days=30),
        revalidation_triggers=(),
    )
    admission_decision = evaluate_production_admission(admission_input)
    assert admission_decision.eligible_for_registry_admission is True
    return RegistryAdmissionRequest(
        admission_id="registry-admission-e2e",
        evaluation_time=phase_c.EVALUATION_TIME
        + timedelta(microseconds=1),
        production_admission_decision=admission_decision,
        expected_profile_id=plan.profile_id,
        expected_profile_version=plan.profile_version,
        expected_protocol_version=plan.protocol_version,
        expected_product_id=plan.product_id,
        expected_product_version=evidence.observed_product_version,
        requested_registry_kind=RegistryKind.PRODUCTION,
        requested_initial_status=RegistryStatus.ACTIVE,
        expected_restrictions=admission_decision.effective_restrictions,
        registry_administrator_id=plan.registry_administrator_id,
        approver_id=plan.approver_id,
        evidence_reviewer_id=plan.evidence_reviewer_id,
        validation_operator_id=plan.validation_operator_id,
        evidence_expires_at=evidence.expires_at,
        validation_expires_at=phase_c.EVALUATION_TIME
        + timedelta(days=30),
        approval_expires_at=phase_c.approval_metadata().expires_at,
        safe_context=(
            "no_credentials",
            "no_network",
            "no_persistence",
            "no_production_registry_write",
            "no_real_documents",
            "no_transport",
            "synthetic_only",
            "test_registry_only",
        ),
    )


def assert_atomic_denial(
    result: RegistryAdmissionResult,
    registry: TestRegistryAdmissionStore,
    reason: RegistryAdmissionReason,
) -> None:
    assert result.admitted is False
    assert reason in result.reason_categories
    assert result.entry is None
    assert result.entry_identity is None
    assert registry.write_count == 0
    assert len(registry.snapshot) == 0
    assert registry.events == ()
    assert registry.transport_count == 0
    assert registry.http_count == 0


def test_full_phase_a_to_e_test_registry_lifecycle() -> None:
    registry = TestRegistryAdmissionStore()
    result = enforce_registry_admission(
        lifecycle_request(), registry=registry
    )

    assert result.admitted is True
    assert registry.write_count == 1
    assert registry.transport_count == 0
    assert registry.http_count == 0
    resolved = registry.resolve_exact(
        profile_id=result.profile_id,
        profile_version=result.profile_version,
        product_id=result.product_id,
        product_version=result.product_version,
        protocol_version=result.protocol_version,
    )
    assert result.entry == resolved
    assert result.safe_summary.admitted is True
    assert result.safe_summary.reason_categories == ()


@pytest.mark.parametrize(
    ("admission_decision", "reason"),
    [
        (
            enforcement_decision(
                decision=ApprovalDecision.REJECTED,
                eligible_for_registry_admission=False,
                reason_categories=(
                    ProductionAdmissionReason.REVIEWER_REJECTED,
                ),
            ),
            RegistryAdmissionReason.DECISION_INELIGIBLE,
        ),
        (
            enforcement_decision(
                decision=ApprovalDecision.NEEDS_REVALIDATION,
                eligible_for_registry_admission=False,
                reason_categories=(
                    ProductionAdmissionReason.REVALIDATION_REQUIRED,
                ),
            ),
            RegistryAdmissionReason.DECISION_INELIGIBLE,
        ),
        (
            enforcement_decision(eligible_for_registry_admission=False),
            RegistryAdmissionReason.DECISION_INELIGIBLE,
        ),
        (
            enforcement_decision(
                evaluated_at=EVALUATION_TIME + timedelta(microseconds=1)
            ),
            RegistryAdmissionReason.DECISION_NOT_YET_VALID,
        ),
    ],
)
def test_decision_denials_are_atomic(
    admission_decision,
    reason: RegistryAdmissionReason,
) -> None:
    registry = TestRegistryAdmissionStore()
    result = enforce_registry_admission(
        enforcement_request(
            production_admission_decision=admission_decision
        ),
        registry=registry,
    )
    assert_atomic_denial(result, registry, reason)


def test_expired_evidence_denial_is_atomic() -> None:
    registry = TestRegistryAdmissionStore()
    result = enforce_registry_admission(
        enforcement_request(evidence_expires_at=EVALUATION_TIME),
        registry=registry,
    )
    assert_atomic_denial(
        result,
        registry,
        RegistryAdmissionReason.DECISION_EXPIRED,
    )


def test_digest_tampering_denial_is_atomic() -> None:
    admission_decision = enforcement_decision()
    object.__setattr__(
        admission_decision,
        "evidence_digest",
        "sha256:" + ("0" * 64),
    )
    registry = TestRegistryAdmissionStore()
    result = enforce_registry_admission(
        enforcement_request(
            production_admission_decision=admission_decision
        ),
        registry=registry,
    )
    assert_atomic_denial(
        result,
        registry,
        RegistryAdmissionReason.DIGEST_MISMATCH,
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"expected_profile_version": version("1.2.4")},
            RegistryAdmissionReason.IDENTITY_MISMATCH,
        ),
        (
            {
                "expected_restrictions": ApprovalRestrictions(
                    maximum_top_k=3
                )
            },
            RegistryAdmissionReason.RESTRICTION_MISMATCH,
        ),
        (
            {"registry_administrator_id": "approver-001"},
            RegistryAdmissionReason.ROLE_CONFLICT,
        ),
    ],
)
def test_binding_denials_are_atomic(
    overrides: dict[str, object],
    reason: RegistryAdmissionReason,
) -> None:
    registry = TestRegistryAdmissionStore()
    result = enforce_registry_admission(
        enforcement_request(**overrides),
        registry=registry,
    )
    assert_atomic_denial(result, registry, reason)


def test_duplicate_and_revoked_identity_do_not_overwrite() -> None:
    registry = TestRegistryAdmissionStore()
    first = enforce_registry_admission(
        enforcement_request(), registry=registry
    )
    assert first.admitted is True
    registry.transition_status(
        profile_id=first.profile_id,
        profile_version=first.profile_version,
        target=RegistryStatus.REVOKED,
    )
    before = registry.snapshot
    second = enforce_registry_admission(
        enforcement_request(admission_id="registry-admission-002"),
        registry=registry,
    )
    assert second.admitted is False
    assert second.reason_categories == (
        RegistryAdmissionReason.STATUS_INELIGIBLE,
    )
    assert registry.write_count == 1
    assert registry.snapshot == before
    assert registry.transport_count == 0
    assert registry.http_count == 0


def test_production_registry_instance_is_not_a_phase_e_write_target() -> None:
    registry = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    result = enforce_registry_admission(
        enforcement_request(), registry=registry
    )
    assert result.admitted is False
    assert result.reason_categories == (
        RegistryAdmissionReason.REGISTRY_WRITE_REJECTED,
    )
    assert registry.snapshot == {}
    assert registry.events == ()


@pytest.mark.parametrize(
    "flag",
    ["fallback", "nearest_version", "infer_schema"],
)
def test_implicit_resolution_attempts_are_rejected(flag: str) -> None:
    registry = TestRegistryAdmissionStore()
    admitted = enforce_registry_admission(
        enforcement_request(), registry=registry
    )
    assert admitted.admitted is True
    values: dict[str, object] = {
        "profile_id": admitted.profile_id,
        "profile_version": admitted.profile_version,
        "product_id": admitted.product_id,
        "product_version": admitted.product_version,
        "protocol_version": admitted.protocol_version,
        flag: True,
    }
    before = registry.snapshot
    with pytest.raises(Exception) as caught:
        registry.resolve_exact(**values)  # type: ignore[arg-type]
    assert str(caught.value) == "security_boundary_violation"
    assert registry.snapshot == before
    assert registry.transport_count == 0
    assert registry.http_count == 0


def test_external_mutation_cannot_change_admitted_entry() -> None:
    registry = TestRegistryAdmissionStore()
    result = enforce_registry_admission(
        enforcement_request(), registry=registry
    )
    assert result.entry is not None
    external = dict(registry.snapshot)
    external.clear()
    assert len(registry.snapshot) == 1
    assert registry.write_count == 1
