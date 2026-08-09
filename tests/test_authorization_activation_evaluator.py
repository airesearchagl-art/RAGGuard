from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.authorization_activation import (
    ActivationEvaluationResult,
    ActivationReason,
    ActivationRequest,
    InMemoryActivationReplayStore,
    evaluate_activation_request,
)
from ragguard.production_authorization import (
    ProductionAuthorizationRequest,
    evaluate_production_authorization,
)
from ragguard.production_boundary import (
    CompatibilityEvidenceKind,
    ManualValidationState,
    PersistenceState,
    RuntimeAuthorizationState,
    SecurityReviewState,
    canonical_registry_state_digest,
)
from ragguard.production_persistence import create_persisted_authorization_record
from ragguard.production_registry import RegistryStatus
from ragguard.replacement_admission import ReplacementRegistryEntry
from tests.test_production_boundary_contract import (
    DIGEST_A,
    DIGEST_B,
    DIGEST_C,
    boundary_evidence,
    source_decision,
    source_entry,
)
from tests.test_production_persistence_contract import approved_policy


NONCE_A = "sha256:" + "1" * 64


def activation_context(**evidence_changes: object):
    entry = source_entry()
    values: dict[str, object] = {
        "compatibility_evidence_kind": CompatibilityEvidenceKind.CONTROLLED_MANUAL,
        "manual_validation_state": ManualValidationState.APPROVED,
        "security_review_state": SecurityReviewState.APPROVED,
        "persistence_state": PersistenceState.PRODUCTION_READY,
        "runtime_authorization_state": RuntimeAuthorizationState.CANDIDATE_ONLY,
    }
    values.update(evidence_changes)
    evidence = boundary_evidence(**values)
    candidate = evaluate_production_authorization(
        ProductionAuthorizationRequest(
            request_id="authorization-candidate-v015",
            evidence=evidence,
            source_entry=entry,
            source_admission_decision=source_decision(),
            registry_snapshot_digests=(entry.canonical_digest,),
        )
    )
    persisted_at = evidence.evaluation_time + timedelta(microseconds=1)
    record = create_persisted_authorization_record(
        persisted_record_id="persisted-authorization-v015",
        source_candidate=candidate,
        source_evidence=evidence,
        policy=approved_policy(),
        persisted_at=persisted_at,
        persisted_by="persistence-operator",
        persistence_generation=1,
        previous_record_digest=None,
    )
    request = ActivationRequest(
        activation_request_id="activation-request-v015",
        persisted_record_digest=record.canonical_digest,
        expected_persistence_generation=record.persistence_generation,
        activation_requested_at=persisted_at + timedelta(microseconds=1),
        activation_requester_id="activation-requester",
        activation_reviewer_id="activation-reviewer",
        authorization_approver_id=evidence.authorization_approver_id,
        expected_profile_id=evidence.profile_id,
        expected_profile_version=evidence.profile_version,
        expected_product_id=evidence.product_id,
        expected_product_version=evidence.product_version,
        expected_protocol_version=evidence.protocol_version,
        expected_registry_state_digest=evidence.registry_state_digest,
        expected_lifecycle_status=RegistryStatus.ACTIVE,
        request_nonce_digest=NONCE_A,
        persistence_verified=True,
        activation_review_approved=False,
    )
    evaluation_time = request.activation_requested_at + timedelta(microseconds=1)
    return entry, evidence, candidate, record, request, evaluation_time


def evaluate(**request_changes: object):
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    request = replace(request, **request_changes)
    return evaluate_activation_request(
        request,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )


def assert_zero_effects(result) -> None:
    assert (
        result.write_count,
        result.mutation_count,
        result.transport_count,
        result.http_count,
        result.filesystem_write_count,
        result.database_write_count,
        result.persistence_write_count,
        result.runtime_activation_count,
    ) == (0, 0, 0, 0, 0, 0, 0, 0)


def test_request_is_immutable() -> None:
    request = activation_context()[4]
    with pytest.raises(FrozenInstanceError):
        request.activation_request_id = "changed"  # type: ignore[misc]


def test_request_digest_is_deterministic() -> None:
    assert activation_context()[4].canonical_digest == activation_context()[4].canonical_digest


def test_one_microsecond_changes_request_digest() -> None:
    request = activation_context()[4]
    changed = replace(
        request,
        activation_requested_at=request.activation_requested_at
        + timedelta(microseconds=1),
    )
    assert changed.canonical_digest != request.canonical_digest


def test_equivalent_instant_has_same_digest() -> None:
    request = activation_context()[4]
    changed = replace(
        request,
        activation_requested_at=request.activation_requested_at.astimezone(
            timezone(timedelta(hours=9))
        ),
    )
    assert changed.canonical_digest == request.canonical_digest


def test_valid_persistence_needs_activation_review() -> None:
    result = evaluate()
    assert result.result is ActivationEvaluationResult.NEEDS_ACTIVATION_REVIEW
    assert ActivationReason.ACTIVATION_REVIEW_REQUIRED in result.reason_categories
    assert_zero_effects(result)


def test_all_contract_prerequisites_return_commit_plan_only() -> None:
    result = evaluate(activation_review_approved=True)
    assert result.result is ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT
    assert result.commit_plan is not None
    assert result.runtime_activation_count == 0
    assert_zero_effects(result)


def test_missing_persistence_verification() -> None:
    result = evaluate(persistence_verified=False)
    assert result.result is ActivationEvaluationResult.NEEDS_PERSISTENCE_VERIFICATION


def test_synthetic_only_needs_manual_validation() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context(
        compatibility_evidence_kind=CompatibilityEvidenceKind.SYNTHETIC_ONLY,
        manual_validation_state=ManualValidationState.NOT_PERFORMED,
    )
    result = evaluate_activation_request(
        request,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )
    assert result.result is ActivationEvaluationResult.NEEDS_MANUAL_VALIDATION
    assert_zero_effects(result)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_profile_id", "other-profile"),
        ("expected_product_id", "other-product"),
        ("authorization_approver_id", "other-approver"),
    ],
)
def test_exact_identity_binding(field: str, value: object) -> None:
    result = evaluate(**{field: value})
    assert result.result is ActivationEvaluationResult.INELIGIBLE
    assert ActivationReason.IDENTITY_MISMATCH in result.reason_categories
    assert_zero_effects(result)


def test_persisted_record_digest_mismatch() -> None:
    result = evaluate(persisted_record_digest="sha256:" + "8" * 64)
    assert ActivationReason.DIGEST_MISMATCH in result.reason_categories


def test_generation_mismatch() -> None:
    result = evaluate(expected_persistence_generation=2)
    assert result.result is ActivationEvaluationResult.INELIGIBLE


def test_registry_snapshot_mismatch() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    other = "sha256:" + "8" * 64
    result = evaluate_activation_request(
        replace(request, expected_registry_state_digest=other),
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )
    assert ActivationReason.DIGEST_MISMATCH in result.reason_categories


def test_fresh_replacement_successor_binding_is_accepted() -> None:
    predecessor = source_entry(RegistryStatus.SUSPENDED)
    evidence = boundary_evidence(
        compatibility_evidence_kind=CompatibilityEvidenceKind.CONTROLLED_MANUAL,
        manual_validation_state=ManualValidationState.APPROVED,
        security_review_state=SecurityReviewState.APPROVED,
        persistence_state=PersistenceState.PRODUCTION_READY,
        runtime_authorization_state=RuntimeAuthorizationState.CANDIDATE_ONLY,
    )
    decision = source_decision()
    replacement_entry = ReplacementRegistryEntry(
        replacement_entry_id="replacement-v015",
        predecessor_entry_digest=predecessor.canonical_digest,
        predecessor_status=RegistryStatus.SUSPENDED,
        replacement_request_digest="sha256:" + "9" * 64,
        approval_digest=decision.approval_digest,
        profile_id=evidence.profile_id,
        profile_version=evidence.profile_version,
        product_id=evidence.product_id,
        product_version=evidence.product_version,
        protocol_version=evidence.protocol_version,
        plan_digest=DIGEST_A,
        evidence_digest=DIGEST_B,
        reviewer_attestation_digest=DIGEST_C,
        admission_decision_digest=decision.canonical_digest,
        admitted_at=evidence.admission_evaluated_at,
        registry_administrator_id=evidence.registry_administrator_id,
        registry_status=RegistryStatus.ACTIVE,
        effective_restrictions=None,
    )
    evidence = replace(
        evidence,
        source_admission_entry_digest=predecessor.canonical_digest,
        source_replacement_entry_digest=replacement_entry.canonical_digest,
        replacement_decision_digest=replacement_entry.replacement_request_digest,
        registry_entry_digest=replacement_entry.canonical_digest,
        registry_state_digest=canonical_registry_state_digest(
            (replacement_entry.canonical_digest,)
        ),
        replacement_evaluated_at=evidence.admission_evaluated_at,
    )
    candidate = evaluate_production_authorization(
        ProductionAuthorizationRequest(
            request_id="replacement-candidate-v015",
            evidence=evidence,
            source_entry=replacement_entry,
            source_admission_decision=decision,
            registry_snapshot_digests=(replacement_entry.canonical_digest,),
        )
    )
    persisted_at = evidence.evaluation_time + timedelta(microseconds=1)
    record = create_persisted_authorization_record(
        persisted_record_id="replacement-record-v015",
        source_candidate=candidate,
        source_evidence=evidence,
        policy=approved_policy(),
        persisted_at=persisted_at,
        persisted_by="persistence-operator",
        persistence_generation=1,
        previous_record_digest=None,
    )
    request = ActivationRequest(
        activation_request_id="replacement-activation-v015",
        persisted_record_digest=record.canonical_digest,
        expected_persistence_generation=1,
        activation_requested_at=persisted_at + timedelta(microseconds=1),
        activation_requester_id="activation-requester",
        activation_reviewer_id="activation-reviewer",
        authorization_approver_id=evidence.authorization_approver_id,
        expected_profile_id=evidence.profile_id,
        expected_profile_version=evidence.profile_version,
        expected_product_id=evidence.product_id,
        expected_product_version=evidence.product_version,
        expected_protocol_version=evidence.protocol_version,
        expected_registry_state_digest=evidence.registry_state_digest,
        expected_lifecycle_status=RegistryStatus.ACTIVE,
        request_nonce_digest="sha256:" + "7" * 64,
        persistence_verified=True,
        activation_review_approved=True,
    )
    result = evaluate_activation_request(
        request,
        record,
        candidate,
        evidence,
        (replacement_entry.canonical_digest,),
        request.activation_requested_at + timedelta(microseconds=1),
    )
    assert result.result is ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT
    assert result.runtime_activation_count == 0


@pytest.mark.parametrize(
    "field",
    ["unresolved_revalidation", "pending_lifecycle_transition"],
)
def test_stale_source_state_is_ineligible(field: str) -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    stale_evidence = replace(evidence, **{field: True})
    result = evaluate_activation_request(
        request,
        record,
        candidate,
        stale_evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )
    assert result.result is ActivationEvaluationResult.INELIGIBLE
    assert ActivationReason.STALE_SOURCE in result.reason_categories


@pytest.mark.parametrize(
    "status",
    [RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED, RegistryStatus.REVOKED],
)
def test_inactive_lifecycle_is_ineligible(status: RegistryStatus) -> None:
    result = evaluate(expected_lifecycle_status=status)
    assert result.result is ActivationEvaluationResult.INELIGIBLE
    assert ActivationReason.LIFECYCLE_INACTIVE in result.reason_categories


def test_expired_evidence_is_ineligible() -> None:
    entry, evidence, candidate, record, request, _ = activation_context()
    result = evaluate_activation_request(
        request,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evidence.evidence_expires_at,
    )
    assert result.result is ActivationEvaluationResult.INELIGIBLE
    assert ActivationReason.EVIDENCE_EXPIRED in result.reason_categories


def test_future_activation_request_is_rejected() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    future = replace(
        request,
        activation_requested_at=evaluation_time + timedelta(microseconds=1),
    )
    result = evaluate_activation_request(
        future,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )
    assert ActivationReason.TEMPORAL_INVALID in result.reason_categories


@pytest.mark.parametrize(
    "field",
    ["activation_requester_id", "activation_reviewer_id"],
)
def test_source_role_collision_is_rejected(field: str) -> None:
    result = evaluate(**{field: "boundary-reviewer"})
    assert ActivationReason.ROLE_CONFLICT in result.reason_categories


def test_requester_self_approval_is_rejected() -> None:
    result = evaluate(activation_requester_id="authorization-approver")
    assert ActivationReason.ROLE_CONFLICT in result.reason_categories


def test_reviewer_self_approval_is_rejected() -> None:
    result = evaluate(activation_reviewer_id="authorization-approver")
    assert ActivationReason.ROLE_CONFLICT in result.reason_categories


@pytest.mark.parametrize(
    "flag",
    ["use_current_alias", "use_latest_alias", "allow_fallback", "infer_source"],
)
def test_implicit_resolution_is_rejected(flag: str) -> None:
    result = evaluate(**{flag: True})
    assert ActivationReason.UNSAFE_RESOLUTION in result.reason_categories


def test_request_id_replay_is_rejected() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    result = evaluate_activation_request(
        replace(request, activation_review_approved=True),
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
        used_request_ids=frozenset({request.activation_request_id}),
    )
    assert ActivationReason.REPLAY_DETECTED in result.reason_categories


def test_nonce_replay_is_rejected() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    result = evaluate_activation_request(
        replace(request, activation_review_approved=True),
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
        used_nonce_digests=frozenset({request.request_nonce_digest}),
    )
    assert ActivationReason.REPLAY_DETECTED in result.reason_categories


def test_record_replay_is_rejected() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    result = evaluate_activation_request(
        replace(request, activation_review_approved=True),
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
        used_record_digests=frozenset({record.canonical_digest}),
    )
    assert ActivationReason.REPLAY_DETECTED in result.reason_categories


def test_failed_review_does_not_consume_replay_state() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    store = InMemoryActivationReplayStore()
    result = store.evaluate(
        request,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )
    assert result.result is ActivationEvaluationResult.NEEDS_ACTIVATION_REVIEW
    assert store.committed_review_count == 0
    assert not store.used_request_ids


def test_failed_then_fixed_request_can_be_retried() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    store = InMemoryActivationReplayStore()
    assert store.evaluate(
        request,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    ).result is ActivationEvaluationResult.NEEDS_ACTIVATION_REVIEW
    approved = replace(request, activation_review_approved=True)
    assert store.evaluate(
        approved,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    ).result is ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT


def test_successful_duplicate_retry_is_rejected() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    store = InMemoryActivationReplayStore()
    approved = replace(request, activation_review_approved=True)
    first = store.evaluate(
        approved,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )
    second = store.evaluate(
        approved,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )
    assert first.result is ActivationEvaluationResult.READY_FOR_ACTIVATION_COMMIT
    assert second.result is ActivationEvaluationResult.INELIGIBLE
    assert store.committed_review_count == 1


def test_canonical_record_tampering_is_rejected() -> None:
    entry, evidence, candidate, record, request, evaluation_time = activation_context()
    object.__setattr__(record, "persisted_by", "tampered-operator")
    result = evaluate_activation_request(
        request,
        record,
        candidate,
        evidence,
        (entry.canonical_digest,),
        evaluation_time,
    )
    assert ActivationReason.INTEGRITY_MISMATCH in result.reason_categories


def test_safe_summary_does_not_disclose_sensitive_values() -> None:
    text = repr(evaluate().safe_summary).lower()
    assert all(
        value not in text
        for value in ("authorization:", "token=", "cookie", "stack trace")
    )
