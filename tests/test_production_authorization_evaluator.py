from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.production_authorization import (
    ProductionAuthorizationReason,
    ProductionAuthorizationRequest,
    ProductionAuthorizationResult,
    evaluate_production_authorization,
)
from ragguard.production_boundary import (
    CompatibilityEvidenceKind,
    ManualValidationState,
    PersistenceState,
    RuntimeAuthorizationState,
    SecurityReviewState,
)
from ragguard.production_registry import RegistryStatus
from ragguard.replacement_admission import ReplacementRegistryEntry
from tests.test_production_boundary_contract import (
    DIGEST_A,
    DIGEST_B,
    DIGEST_C,
    DIGEST_D,
    boundary_evidence,
    source_decision,
    source_entry,
)


def request(**evidence_changes: object) -> ProductionAuthorizationRequest:
    entry = source_entry(evidence_changes.pop("entry_status", RegistryStatus.ACTIVE))
    evidence = boundary_evidence(**evidence_changes)
    if entry.registry_status is not RegistryStatus.ACTIVE:
        evidence = replace(
            evidence,
            source_lifecycle_status=entry.registry_status,
            source_admission_entry_digest=entry.canonical_digest,
            registry_entry_digest=entry.canonical_digest,
        )
        from ragguard.production_boundary import canonical_registry_state_digest
        evidence = replace(
            evidence,
            registry_state_digest=canonical_registry_state_digest(
                (entry.canonical_digest,)
            ),
        )
    return ProductionAuthorizationRequest(
        request_id="authorization-request",
        evidence=evidence,
        source_entry=entry,
        source_admission_decision=source_decision(),
        registry_snapshot_digests=(entry.canonical_digest,),
    )


def result(**changes: object):
    return evaluate_production_authorization(request(**changes))


def assert_no_effects(candidate) -> None:
    assert (
        candidate.write_count,
        candidate.mutation_count,
        candidate.transport_count,
        candidate.http_count,
        candidate.persistence_write_count,
        candidate.runtime_activation_count,
    ) == (0, 0, 0, 0, 0, 0)


def manually_ready(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "manual_validation_state": ManualValidationState.APPROVED,
        "compatibility_evidence_kind": CompatibilityEvidenceKind.CONTROLLED_MANUAL,
    }
    values.update(changes)
    return values


def test_synthetic_only_needs_manual_validation() -> None:
    assert result().result is ProductionAuthorizationResult.NEEDS_MANUAL_VALIDATION


def test_missing_security_review() -> None:
    assert result(**manually_ready()).result is ProductionAuthorizationResult.NEEDS_SECURITY_REVIEW


def test_missing_persistence_boundary() -> None:
    candidate = result(
        **manually_ready(security_review_state=SecurityReviewState.APPROVED)
    )
    assert candidate.result is ProductionAuthorizationResult.NEEDS_PERSISTENCE_BOUNDARY


def test_missing_runtime_boundary() -> None:
    candidate = result(
        **manually_ready(
            security_review_state=SecurityReviewState.APPROVED,
            persistence_state=PersistenceState.PRODUCTION_READY,
        )
    )
    assert (
        candidate.result
        is ProductionAuthorizationResult.NEEDS_RUNTIME_AUTHORIZATION_BOUNDARY
    )


def test_all_contract_prerequisites_are_review_candidate_only() -> None:
    candidate = result(
        **manually_ready(
            security_review_state=SecurityReviewState.APPROVED,
            persistence_state=PersistenceState.PRODUCTION_READY,
            runtime_authorization_state=RuntimeAuthorizationState.CANDIDATE_ONLY,
        )
    )
    assert candidate.result is ProductionAuthorizationResult.ELIGIBLE_FOR_AUTHORIZATION_REVIEW
    assert candidate.runtime_activation_count == 0


@pytest.mark.parametrize(
    "status",
    [RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED, RegistryStatus.REVOKED],
)
def test_non_active_source_is_ineligible(status: RegistryStatus) -> None:
    assert result(entry_status=status).result is ProductionAuthorizationResult.INELIGIBLE


def test_expired_evidence_is_ineligible() -> None:
    evidence = boundary_evidence()
    candidate = result(evidence_expires_at=evidence.evaluation_time)
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE


def test_unresolved_revalidation_is_ineligible() -> None:
    assert result(unresolved_revalidation=True).result is ProductionAuthorizationResult.INELIGIBLE


def test_pending_lifecycle_is_ineligible() -> None:
    candidate = result(pending_lifecycle_transition=True)
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE


def test_reused_chain_is_ineligible() -> None:
    candidate = result(chain_reuse_detected=True)
    assert ProductionAuthorizationReason.CHAIN_REUSE in candidate.reason_categories


def test_role_conflict_is_ineligible() -> None:
    candidate = result(boundary_reviewer_id="registry-admin")
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE


def test_active_runtime_state_is_rejected() -> None:
    candidate = result(
        **manually_ready(
            security_review_state=SecurityReviewState.APPROVED,
            persistence_state=PersistenceState.PRODUCTION_READY,
            runtime_authorization_state=RuntimeAuthorizationState.ACTIVE,
        )
    )
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE
    assert (
        ProductionAuthorizationReason.RUNTIME_ACTIVATION_PROHIBITED
        in candidate.reason_categories
    )


@pytest.mark.parametrize(
    "flag",
    [
        "use_current_alias",
        "use_latest_alias",
        "allow_fallback",
        "allow_nearest_version",
        "allow_schema_inference",
    ],
)
def test_implicit_resolution_is_rejected(flag: str) -> None:
    base = request()
    candidate = evaluate_production_authorization(replace(base, **{flag: True}))
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE


def test_denial_counts_are_zero() -> None:
    candidate = result(chain_reuse_detected=True)
    assert (
        candidate.write_count,
        candidate.mutation_count,
        candidate.transport_count,
        candidate.http_count,
        candidate.persistence_write_count,
        candidate.runtime_activation_count,
    ) == (0, 0, 0, 0, 0, 0)


def test_future_required_action_is_rejected() -> None:
    evidence = boundary_evidence()
    candidate = result(
        latest_required_action_at=(
            evidence.evaluation_time + timedelta(microseconds=1)
        )
    )
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE


def test_exact_replacement_successor_binding_is_accepted() -> None:
    predecessor = source_entry(RegistryStatus.SUSPENDED)
    base = boundary_evidence()
    replacement = ReplacementRegistryEntry(
        replacement_entry_id="replacement-v014",
        predecessor_entry_digest=predecessor.canonical_digest,
        predecessor_status=RegistryStatus.SUSPENDED,
        replacement_request_digest="sha256:" + "9" * 64,
        approval_digest=base.approval_digest,
        profile_id=base.profile_id,
        profile_version=base.profile_version,
        product_id=base.product_id,
        product_version=base.product_version,
        protocol_version=base.protocol_version,
        plan_digest=DIGEST_A,
        evidence_digest=DIGEST_B,
        reviewer_attestation_digest=DIGEST_C,
        admission_decision_digest=source_decision().canonical_digest,
        admitted_at=base.admission_evaluated_at,
        registry_administrator_id="registry-admin",
        registry_status=RegistryStatus.ACTIVE,
        effective_restrictions=None,
    )
    from ragguard.production_boundary import canonical_registry_state_digest

    evidence = replace(
        base,
        source_admission_entry_digest=predecessor.canonical_digest,
        source_replacement_entry_digest=replacement.canonical_digest,
        replacement_decision_digest=replacement.replacement_request_digest,
        registry_entry_digest=replacement.canonical_digest,
        registry_state_digest=canonical_registry_state_digest((replacement.canonical_digest,)),
        replacement_evaluated_at=base.admission_evaluated_at,
    )
    candidate = evaluate_production_authorization(
        ProductionAuthorizationRequest(
            request_id="replacement-authorization",
            evidence=evidence,
            source_entry=replacement,
            source_admission_decision=source_decision(),
            registry_snapshot_digests=(replacement.canonical_digest,),
        )
    )
    assert candidate.result is ProductionAuthorizationResult.NEEDS_MANUAL_VALIDATION


@pytest.mark.parametrize(
    ("field", "replacement_value"),
    [
        ("validation_operator_id", "other-operator"),
        ("evidence_reviewer_id", "other-reviewer"),
        ("approver_id", "other-approver"),
        ("registry_administrator_id", "other-registry-admin"),
    ],
)
def test_source_bound_role_substitution_is_rejected(
    field: str,
    replacement_value: str,
) -> None:
    original = request()
    tampered = replace(original.evidence, **{field: replacement_value})
    candidate = evaluate_production_authorization(
        replace(original, evidence=tampered)
    )
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE
    assert_no_effects(candidate)


def test_approval_digest_substitution_is_rejected() -> None:
    original = request()
    tampered = replace(
        original.evidence,
        approval_digest="sha256:" + "8" * 64,
    )
    candidate = evaluate_production_authorization(
        replace(original, evidence=tampered)
    )
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE
    assert_no_effects(candidate)


def test_source_decision_digest_mismatch_is_rejected() -> None:
    original = request()
    other = replace(
        original.source_admission_decision,
        plan_digest="sha256:" + "7" * 64,
    )
    candidate = evaluate_production_authorization(
        replace(original, source_admission_decision=other)
    )
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE
    assert_no_effects(candidate)


def test_source_decision_canonical_role_tampering_is_rejected() -> None:
    original = request()
    object.__setattr__(
        original.source_admission_decision,
        "validation_operator_id",
        "tampered-operator",
    )
    candidate = evaluate_production_authorization(original)
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE
    assert_no_effects(candidate)


def test_replacement_approval_digest_mismatch_is_rejected() -> None:
    predecessor = source_entry(RegistryStatus.SUSPENDED)
    base = boundary_evidence()
    decision = source_decision()
    replacement = ReplacementRegistryEntry(
        replacement_entry_id="replacement-mismatch-v014",
        predecessor_entry_digest=predecessor.canonical_digest,
        predecessor_status=RegistryStatus.SUSPENDED,
        replacement_request_digest="sha256:" + "6" * 64,
        approval_digest=decision.approval_digest,
        profile_id=base.profile_id,
        profile_version=base.profile_version,
        product_id=base.product_id,
        product_version=base.product_version,
        protocol_version=base.protocol_version,
        plan_digest=DIGEST_A,
        evidence_digest=DIGEST_B,
        reviewer_attestation_digest=DIGEST_C,
        admission_decision_digest=decision.canonical_digest,
        admitted_at=base.admission_evaluated_at,
        registry_administrator_id="registry-admin",
        registry_status=RegistryStatus.ACTIVE,
        effective_restrictions=None,
    )
    from ragguard.production_boundary import canonical_registry_state_digest

    evidence = replace(
        base,
        source_admission_entry_digest=predecessor.canonical_digest,
        source_replacement_entry_digest=replacement.canonical_digest,
        replacement_decision_digest=replacement.replacement_request_digest,
        approval_digest="sha256:" + "5" * 64,
        admission_decision_digest=decision.canonical_digest,
        registry_entry_digest=replacement.canonical_digest,
        registry_state_digest=canonical_registry_state_digest(
            (replacement.canonical_digest,)
        ),
        replacement_evaluated_at=base.admission_evaluated_at,
    )
    candidate = evaluate_production_authorization(
        ProductionAuthorizationRequest(
            request_id="replacement-approval-mismatch",
            evidence=evidence,
            source_entry=replacement,
            source_admission_decision=decision,
            registry_snapshot_digests=(replacement.canonical_digest,),
        )
    )
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE
    assert_no_effects(candidate)
