from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.equivalence_attestation import TestEquivalenceAttestationStore
from ragguard.production_authorization import (
    ProductionAuthorizationReason,
    ProductionAuthorizationRequest,
    ProductionAuthorizationResult,
    evaluate_production_authorization,
)
from ragguard.production_boundary import CompatibilityEvidenceKind
from ragguard.production_equivalence import (
    EquivalenceAssessmentResult,
    EquivalenceEvidenceSourceKind,
    ProductionEquivalentState,
)
from test_equivalence_attestation import attestation_chain, commit
from test_production_authorization_evaluator import (
    manually_ready,
    request as authorization_request,
)
from test_production_equivalence_contract import (
    EVALUATION_TIME,
    assess,
    assessment_request,
    behavior,
    configuration,
    criteria,
    descriptor,
    digest,
    environment_equivalence,
)


def assert_zero_side_effects(result: object) -> None:
    names = (
        "write_count",
        "mutation_count",
        "persistence_count",
        "filesystem_count",
        "database_count",
        "transport_count",
        "http_count",
        "activation_count",
    )
    assert all(getattr(result, name, 0) == 0 for name in names)


def test_synthetic_only_never_becomes_production_equivalent() -> None:
    result = assess(
        descriptor=descriptor(source_kind=EquivalenceEvidenceSourceKind.SYNTHETIC)
    )
    assert result.result is not EquivalenceAssessmentResult.ELIGIBLE_FOR_EQUIVALENCE_REVIEW
    assert_zero_side_effects(result)


def test_controlled_manual_chain_stops_at_environment_gap() -> None:
    result = assess(
        descriptor=descriptor(environment_descriptor_digest=digest("8"))
    )
    assert result.result is EquivalenceAssessmentResult.NEEDS_ENVIRONMENT_EQUIVALENCE
    assert_zero_side_effects(result)


def test_environment_configuration_and_protocol_precede_behavior() -> None:
    result = assess(
        behavior=behavior(skipped_case_ids=("case-alpha",)),
    )
    assert result.result is EquivalenceAssessmentResult.NEEDS_PRODUCT_BEHAVIOR_EQUIVALENCE
    assert_zero_side_effects(result)


def test_complete_metadata_before_review_needs_independent_review() -> None:
    result = assess(independent_reviewer_id=None)
    assert result.result is EquivalenceAssessmentResult.NEEDS_INDEPENDENT_REVIEW
    assert_zero_side_effects(result)


def test_full_contract_fixture_is_only_eligible_for_review() -> None:
    result = assess()
    assert result.result is EquivalenceAssessmentResult.ELIGIBLE_FOR_EQUIVALENCE_REVIEW
    assert_zero_side_effects(result)


@pytest.mark.parametrize(
    "change",
    [
        {"request": assessment_request(manual_validation_approval_digest=digest("9"))},
        {"criteria": criteria(required_product_contract_digest=digest("9"))},
        {"descriptor": descriptor(test_case_coverage_digest=digest("9"))},
        {"environment": environment_equivalence(runtime_family="different-runtime")},
        {"configuration": configuration(profile_id="different-profile")},
        {"evaluation_time": EVALUATION_TIME + timedelta(days=100)},
    ],
)
def test_denials_leave_every_external_effect_at_zero(change: dict[str, object]) -> None:
    result = assess(**change)
    assert result.result is not EquivalenceAssessmentResult.ELIGIBLE_FOR_EQUIVALENCE_REVIEW
    assert_zero_side_effects(result)


def test_commit_fault_is_atomic_and_retryable() -> None:
    store = TestEquivalenceAttestationStore()
    before = store.snapshot
    failed = commit(store, fail_commit=True)
    assert not failed.applied
    assert store.snapshot == before
    assert_zero_side_effects(failed)
    assert commit(store).applied


def test_approval_claim_without_digest_chain_is_rejected_by_boundary_contract() -> None:
    base = authorization_request().evidence
    with pytest.raises(ValueError):
        replace(
            base,
            compatibility_evidence_kind=CompatibilityEvidenceKind.PRODUCTION_EQUIVALENT,
            production_equivalent_state=ProductionEquivalentState.APPROVED,
        )


def test_production_equivalent_enum_claim_alone_needs_equivalence() -> None:
    request = authorization_request(
        **manually_ready(
            compatibility_evidence_kind=CompatibilityEvidenceKind.PRODUCTION_EQUIVALENT,
            production_equivalent_state=ProductionEquivalentState.REVIEW_PENDING,
        )
    )
    candidate = evaluate_production_authorization(request)
    assert candidate.result is ProductionAuthorizationResult.NEEDS_PRODUCTION_EQUIVALENCE
    assert candidate.runtime_activation_count == 0


def test_attestation_approval_does_not_activate_or_persist() -> None:
    store = TestEquivalenceAttestationStore()
    result = commit(store)
    assert result.applied
    assert attestation_chain().approved
    assert_zero_side_effects(result)


def test_v014_exact_equivalence_chain_is_digest_bound() -> None:
    chain_value = attestation_chain()
    values = manually_ready(
        compatibility_evidence_kind=CompatibilityEvidenceKind.PRODUCTION_EQUIVALENT,
        production_equivalent_state=ProductionEquivalentState.APPROVED,
        manual_validation_approval_digest=(
            chain_value.request.manual_validation_approval_digest
        ),
        approver_id="approver-v016",
        evaluation_time=chain_value.approval.approved_at + timedelta(microseconds=1),
        evidence_expires_at=chain_value.approval.approved_at + timedelta(days=30),
        equivalence_assessment_digest=chain_value.assessment.canonical_digest,
        equivalence_review_digest=chain_value.review.canonical_digest,
        equivalence_approval_digest=chain_value.approval.canonical_digest,
        equivalence_criteria_digest=chain_value.criteria.canonical_digest,
        equivalence_evidence_descriptor_digest=(
            chain_value.descriptor.canonical_digest
        ),
    )
    base = authorization_request(**values)
    request = replace(base, equivalence_chain=chain_value)
    candidate = evaluate_production_authorization(request)
    assert ProductionAuthorizationReason.DIGEST_MISMATCH not in candidate.reason_categories
    assert candidate.equivalence_approval_digest == chain_value.approval.canonical_digest
    assert candidate.runtime_activation_count == 0


def test_v014_equivalence_digest_tampering_is_ineligible() -> None:
    chain_value = attestation_chain()
    values = manually_ready(
        compatibility_evidence_kind=CompatibilityEvidenceKind.PRODUCTION_EQUIVALENT,
        production_equivalent_state=ProductionEquivalentState.APPROVED,
        manual_validation_approval_digest=(
            chain_value.request.manual_validation_approval_digest
        ),
        approver_id="approver-v016",
        evaluation_time=chain_value.approval.approved_at + timedelta(microseconds=1),
        evidence_expires_at=chain_value.approval.approved_at + timedelta(days=30),
        equivalence_assessment_digest=digest("9"),
        equivalence_review_digest=chain_value.review.canonical_digest,
        equivalence_approval_digest=chain_value.approval.canonical_digest,
        equivalence_criteria_digest=chain_value.criteria.canonical_digest,
        equivalence_evidence_descriptor_digest=(
            chain_value.descriptor.canonical_digest
        ),
    )
    base = authorization_request(**values)
    request = replace(base, equivalence_chain=chain_value)
    candidate = evaluate_production_authorization(request)
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE
    assert ProductionAuthorizationReason.DIGEST_MISMATCH in candidate.reason_categories
