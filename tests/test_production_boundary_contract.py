from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.compatibility import SemanticVersion
from ragguard.production_boundary import (
    CompatibilityEvidenceKind,
    ManualValidationState,
    PersistenceBoundaryMetadata,
    PersistenceState,
    ProductionBoundaryError,
    ProductionBoundaryEvidence,
    RollbackSemantics,
    RuntimeAuthorizationState,
    SecurityReviewState,
    canonical_registry_state_digest,
)
from ragguard.production_admission import ProductionAdmissionDecision
from ragguard.production_registry import RegistryKind, RegistryStatus
from ragguard.profile_approval import ApprovalDecision, ProfileMaturity
from ragguard.registry_admission import RegistryAdmissionEntry


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64


def source_decision() -> ProductionAdmissionDecision:
    return ProductionAdmissionDecision(
        decision=ApprovalDecision.APPROVED,
        eligible_for_registry_admission=True,
        effective_restrictions=None,
        reason_categories=(),
        evaluated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        plan_id="manual-plan-v014",
        plan_digest=DIGEST_A,
        evidence_id="manual-evidence-v014",
        evidence_digest=DIGEST_B,
        reviewer_attestation_id="attestation-v014",
        reviewer_attestation_digest=DIGEST_C,
        evidence_reviewer_id="evidence-reviewer",
        validation_operator_id="validation-operator",
        approver_id="admission-approver",
        approval_digest=DIGEST_E,
        requested_registry_kind=RegistryKind.PRODUCTION,
        requested_initial_status=RegistryStatus.ACTIVE,
        _request_id="admission-request-v014",
        _profile_id="profile-v014",
        _profile_version="1.0.0",
        _protocol_version="1.0.0",
        _product_id="product-v014",
        _product_version="1.0.0",
    )


def source_entry(status: RegistryStatus = RegistryStatus.ACTIVE) -> RegistryAdmissionEntry:
    decision = source_decision()
    return RegistryAdmissionEntry(
        admission_id="admission-v014",
        profile_id="profile-v014",
        profile_version=SemanticVersion(1, 0, 0),
        protocol_version=SemanticVersion(1, 0, 0),
        product_id="product-v014",
        product_version=SemanticVersion(1, 0, 0),
        maturity=ProfileMaturity.APPROVED,
        approval_decision=ApprovalDecision.APPROVED,
        approval_digest=decision.approval_digest,
        restrictions=None,
        plan_digest=DIGEST_A,
        evidence_digest=DIGEST_B,
        reviewer_attestation_digest=DIGEST_C,
        admission_decision_digest=decision.canonical_digest,
        admitted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        registry_administrator_id="registry-admin",
        registry_status=status,
        registry_kind=RegistryKind.PRODUCTION,
    )


def approved_persistence() -> PersistenceBoundaryMetadata:
    return PersistenceBoundaryMetadata(
        durability_required=True,
        append_only_audit_required=True,
        tamper_evidence_required=True,
        backup_restore_required=True,
        secret_separation_required=True,
        rollback_semantics=RollbackSemantics.EXPLICIT_NO_REACTIVATION,
        boundary_approved=True,
    )


def boundary_evidence(**changes: object) -> ProductionBoundaryEvidence:
    entry = source_entry()
    completed = datetime(2026, 8, 2, 10, 0, 0, 1, timezone.utc)
    reviewed = completed + timedelta(microseconds=1)
    approved = reviewed + timedelta(microseconds=1)
    admitted = approved + timedelta(microseconds=1)
    evaluated = admitted + timedelta(microseconds=1)
    values: dict[str, object] = {
        "boundary_evidence_id": "boundary-v014",
        "evaluation_time": evaluated,
        "source_admission_entry_digest": entry.canonical_digest,
        "source_replacement_entry_digest": None,
        "source_lifecycle_status": RegistryStatus.ACTIVE,
        "profile_id": entry.profile_id,
        "profile_version": entry.profile_version,
        "protocol_version": entry.protocol_version,
        "product_id": entry.product_id,
        "product_version": entry.product_version,
        "plan_digest": entry.plan_digest,
        "evidence_digest": entry.evidence_digest,
        "reviewer_attestation_digest": entry.reviewer_attestation_digest,
        "approval_digest": DIGEST_E,
        "admission_decision_digest": entry.admission_decision_digest,
        "replacement_decision_digest": None,
        "registry_entry_digest": entry.canonical_digest,
        "registry_state_digest": canonical_registry_state_digest((entry.canonical_digest,)),
        "compatibility_evidence_kind": CompatibilityEvidenceKind.SYNTHETIC_ONLY,
        "manual_validation_state": ManualValidationState.NOT_PERFORMED,
        "persistence_state": PersistenceState.NONE,
        "runtime_authorization_state": RuntimeAuthorizationState.DISABLED,
        "security_review_state": SecurityReviewState.NOT_REVIEWED,
        "validation_operator_id": "validation-operator",
        "evidence_reviewer_id": "evidence-reviewer",
        "approver_id": "admission-approver",
        "registry_administrator_id": "registry-admin",
        "boundary_reviewer_id": "boundary-reviewer",
        "authorization_approver_id": "authorization-approver",
        "evidence_completed_at": completed,
        "reviewed_at": reviewed,
        "approved_at": approved,
        "admission_evaluated_at": admitted,
        "evidence_expires_at": evaluated + timedelta(days=30),
        "latest_required_action_at": admitted,
        "persistence_metadata": approved_persistence(),
        "safe_context": ("no_credentials", "no_network", "synthetic_only"),
        "manual_validation_execution_digest": DIGEST_A,
        "manual_validation_evidence_digest": DIGEST_B,
        "manual_validation_review_digest": DIGEST_C,
        "manual_validation_approval_digest": DIGEST_D,
    }
    values.update(changes)
    return ProductionBoundaryEvidence(**values)  # type: ignore[arg-type]


def test_evidence_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        boundary_evidence().profile_id = "changed"  # type: ignore[misc]


def test_digest_is_deterministic() -> None:
    assert boundary_evidence().canonical_digest == boundary_evidence().canonical_digest


def test_one_microsecond_changes_digest() -> None:
    evidence = boundary_evidence()
    changed = replace(
        evidence,
        evaluation_time=evidence.evaluation_time + timedelta(microseconds=1),
    )
    assert changed.canonical_digest != evidence.canonical_digest


def test_equivalent_timezone_instant_has_same_digest() -> None:
    evidence = boundary_evidence()
    offset = timezone(timedelta(hours=9))
    changed = replace(evidence, evaluation_time=evidence.evaluation_time.astimezone(offset))
    assert changed.canonical_digest == evidence.canonical_digest


def test_naive_time_is_typed_safe_error() -> None:
    with pytest.raises(ProductionBoundaryError) as error:
        boundary_evidence(evaluation_time=datetime(2026, 8, 2))
    assert "2026" not in str(error.value)


def test_safe_summary_is_allowlisted() -> None:
    summary = repr(boundary_evidence().safe_summary).lower()
    assert all(value not in summary for value in ("token=", "cookie", "authorization:"))


def test_persistence_metadata_requires_all_controls() -> None:
    metadata = replace(approved_persistence(), tamper_evidence_required=False)
    assert not metadata.is_approved


def test_registry_state_requires_sorted_unique_digests() -> None:
    with pytest.raises(ProductionBoundaryError):
        canonical_registry_state_digest((DIGEST_B, DIGEST_A))


def test_repr_is_safe() -> None:
    assert repr(boundary_evidence()) == "ProductionBoundaryEvidence(<safe>)"
