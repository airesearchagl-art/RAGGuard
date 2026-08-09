from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone

import pytest

from ragguard.production_authorization import (
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
from ragguard.production_persistence import (
    DurabilityMode,
    InMemoryPersistenceStore,
    PersistenceCommitFault,
    PersistenceCommitReceipt,
    PersistenceCommitRequest,
    PersistencePolicy,
    PersistenceReason,
    PersistenceRetentionPolicy,
    PersistenceRollbackPolicy,
    create_persisted_authorization_record,
)
from tests.test_production_boundary_contract import (
    boundary_evidence,
    source_decision,
    source_entry,
)


def approved_policy(**changes: object) -> PersistencePolicy:
    values: dict[str, object] = {
        "policy_id": "persistence-policy-v015",
        "policy_version": "v1",
        "durability_mode": DurabilityMode.APPEND_ONLY,
        "append_only_required": True,
        "tamper_evidence_required": True,
        "backup_required": True,
        "restore_verification_required": True,
        "rollback_policy": PersistenceRollbackPolicy.NO_AUTOMATIC_ROLLBACK,
        "retention_policy": PersistenceRetentionPolicy.AUDIT_RETAINED,
        "secret_separation_required": True,
        "operator_separation_required": True,
    }
    values.update(changes)
    return PersistencePolicy(**values)  # type: ignore[arg-type]


def eligible_context():
    entry = source_entry()
    evidence = boundary_evidence(
        compatibility_evidence_kind=CompatibilityEvidenceKind.CONTROLLED_MANUAL,
        manual_validation_state=ManualValidationState.APPROVED,
        security_review_state=SecurityReviewState.APPROVED,
        persistence_state=PersistenceState.PRODUCTION_READY,
        runtime_authorization_state=RuntimeAuthorizationState.CANDIDATE_ONLY,
    )
    candidate = evaluate_production_authorization(
        ProductionAuthorizationRequest(
            request_id="authorization-candidate-v015",
            evidence=evidence,
            source_entry=entry,
            source_admission_decision=source_decision(),
            registry_snapshot_digests=(entry.canonical_digest,),
        )
    )
    assert candidate.result is ProductionAuthorizationResult.ELIGIBLE_FOR_AUTHORIZATION_REVIEW
    return entry, evidence, candidate


def commit_request(
    *,
    record_id: str = "persisted-record-v015",
    generation: int = 1,
    previous_record_digest: str | None = None,
    persisted_by: str = "persistence-operator",
    policy: PersistencePolicy | None = None,
    candidate=None,
) -> PersistenceCommitRequest:
    entry, evidence, default_candidate = eligible_context()
    selected_candidate = default_candidate if candidate is None else candidate
    selected_policy = approved_policy() if policy is None else policy
    persisted_at = evidence.evaluation_time + timedelta(microseconds=1)
    record = create_persisted_authorization_record(
        persisted_record_id=record_id,
        source_candidate=selected_candidate,
        source_evidence=evidence,
        policy=selected_policy,
        persisted_at=persisted_at,
        persisted_by=persisted_by,
        persistence_generation=generation,
        previous_record_digest=previous_record_digest,
    )
    return PersistenceCommitRequest(
        record=record,
        source_candidate=selected_candidate,
        source_evidence=evidence,
        policy=selected_policy,
        registry_snapshot_digests=(entry.canonical_digest,),
        evaluation_time=persisted_at + timedelta(microseconds=1),
    )


def assert_no_external_effects(result) -> None:
    assert (
        result.transport_count,
        result.http_count,
        result.filesystem_write_count,
        result.database_write_count,
        result.runtime_activation_count,
    ) == (0, 0, 0, 0, 0)


def test_policy_is_immutable_and_approved() -> None:
    policy = approved_policy()
    assert policy.is_approved
    with pytest.raises(FrozenInstanceError):
        policy.policy_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    [
        "append_only_required",
        "tamper_evidence_required",
        "backup_required",
        "restore_verification_required",
        "secret_separation_required",
        "operator_separation_required",
    ],
)
def test_policy_requires_all_controls(field: str) -> None:
    assert not approved_policy(**{field: False}).is_approved


def test_policy_digest_is_deterministic() -> None:
    assert approved_policy().canonical_digest == approved_policy().canonical_digest


def test_record_is_immutable() -> None:
    record = commit_request().record
    with pytest.raises(FrozenInstanceError):
        record.persisted_by = "changed"  # type: ignore[misc]


def test_record_digest_is_deterministic() -> None:
    assert commit_request().record.canonical_digest == commit_request().record.canonical_digest


def test_record_one_microsecond_changes_digest() -> None:
    record = commit_request().record
    changed = replace(
        record, persisted_at=record.persisted_at + timedelta(microseconds=1)
    )
    assert changed.canonical_digest != record.canonical_digest


def test_equivalent_instant_has_same_record_digest() -> None:
    record = commit_request().record
    changed = replace(record, persisted_at=record.persisted_at.astimezone(timezone.utc))
    assert changed.canonical_digest == record.canonical_digest


def test_integrity_digest_covers_generation_and_chain() -> None:
    record = commit_request().record
    changed = replace(
        record,
        persistence_generation=2,
        previous_record_digest="sha256:" + "1" * 64,
    )
    assert changed.integrity_digest != record.integrity_digest


def test_safe_summary_is_bounded() -> None:
    text = repr(commit_request().record.safe_summary).lower()
    assert all(value not in text for value in ("authorization:", "token=", "cookie"))


def test_successful_commit_is_single_atomic_update() -> None:
    store = InMemoryPersistenceStore()
    result = store.commit(commit_request())
    assert result.applied
    assert result.receipt is not None
    assert len(store.records) == 1
    assert store.receipts == (result.receipt,)
    assert result.receipt.persisted_record_digest == store.records[0].canonical_digest
    assert result.receipt.persistence_policy_digest == approved_policy().canonical_digest
    assert result.receipt.resulting_store_state_digest == store.state_digest
    assert store.snapshot.latest_receipt_digest == result.receipt.canonical_digest
    assert store.write_count == store.mutation_count == 1
    assert result.write_count == result.mutation_count == 1
    assert_no_external_effects(result)


@pytest.mark.parametrize(
    "fault",
    [
        PersistenceCommitFault.CANDIDATE_STATE,
        PersistenceCommitFault.RECORD_APPEND,
        PersistenceCommitFault.COUNTERS,
        PersistenceCommitFault.RECEIPT,
        PersistenceCommitFault.BEFORE_SWAP,
    ],
)
def test_commit_fault_leaves_all_state_unchanged(fault: PersistenceCommitFault) -> None:
    store = InMemoryPersistenceStore()
    before = (
        store.records,
        store.receipts,
        store.committed_record_ids,
        store.used_candidate_digests,
        store.write_count,
        store.mutation_count,
        store.state_digest,
    )
    result = store.commit(commit_request(), fault=fault)
    after = (
        store.records,
        store.receipts,
        store.committed_record_ids,
        store.used_candidate_digests,
        store.write_count,
        store.mutation_count,
        store.state_digest,
    )
    assert not result.applied
    assert result.receipt is None
    assert result.reason_categories == (PersistenceReason.COMMIT_FAILED,)
    assert before == after
    assert result.write_count == result.mutation_count == 0
    assert_no_external_effects(result)


def test_failed_request_can_be_retried() -> None:
    store = InMemoryPersistenceStore()
    request = commit_request()
    assert not store.commit(request, fault=PersistenceCommitFault.BEFORE_SWAP).applied
    result = store.commit(request)
    assert result.applied
    assert result.receipt is not None


def test_commit_receipt_cannot_be_self_issued() -> None:
    request = commit_request()
    with pytest.raises(ValueError):
        PersistenceCommitReceipt(
            persisted_record_id=request.record.persisted_record_id,
            persisted_record_digest=request.record.canonical_digest,
            persistence_policy_digest=request.policy.canonical_digest,
            source_candidate_digest=request.source_candidate.canonical_digest,
            persistence_generation=1,
            previous_record_digest=None,
            committed_at=request.evaluation_time,
            evaluated_at=request.evaluation_time,
            resulting_store_state_digest="sha256:" + "1" * 64,
        )


def test_successful_duplicate_record_id_is_rejected() -> None:
    store = InMemoryPersistenceStore()
    request = commit_request()
    assert store.commit(request).applied
    duplicate = replace(
        request,
        record=replace(
            request.record,
            persistence_generation=2,
            previous_record_digest=request.record.canonical_digest,
        ),
    )
    result = store.commit(duplicate)
    assert not result.applied
    assert PersistenceReason.DUPLICATE_RECORD_ID in result.reason_categories


def test_successful_candidate_replay_is_rejected() -> None:
    store = InMemoryPersistenceStore()
    first = commit_request()
    assert store.commit(first).applied
    second = commit_request(
        record_id="persisted-record-v015-b",
        generation=2,
        previous_record_digest=first.record.canonical_digest,
    )
    result = store.commit(second)
    assert not result.applied
    assert PersistenceReason.CANDIDATE_REPLAY in result.reason_categories


def test_generation_must_be_monotonic() -> None:
    result = InMemoryPersistenceStore().commit(
        commit_request(generation=2, previous_record_digest="sha256:" + "1" * 64)
    )
    assert PersistenceReason.GENERATION_MISMATCH in result.reason_categories


def test_previous_record_digest_must_be_exact() -> None:
    store = InMemoryPersistenceStore()
    first = commit_request()
    assert store.commit(first).applied
    second = commit_request(
        record_id="persisted-record-v015-b",
        generation=2,
        previous_record_digest="sha256:" + "2" * 64,
    )
    assert PersistenceReason.PREDECESSOR_MISMATCH in store.commit(
        second
    ).reason_categories


def test_policy_digest_mismatch_is_rejected() -> None:
    request = commit_request()
    result = InMemoryPersistenceStore().commit(
        replace(request, policy=replace(request.policy, policy_version="v2"))
    )
    assert PersistenceReason.POLICY_MISMATCH in result.reason_categories


def test_registry_snapshot_mismatch_is_rejected() -> None:
    request = commit_request()
    changed = replace(
        request,
        registry_snapshot_digests=("sha256:" + "9" * 64,),
    )
    assert PersistenceReason.DIGEST_MISMATCH in InMemoryPersistenceStore().commit(
        changed
    ).reason_categories


def test_persistence_operator_must_be_distinct() -> None:
    result = InMemoryPersistenceStore().commit(
        commit_request(persisted_by="boundary-reviewer")
    )
    assert PersistenceReason.ROLE_CONFLICT in result.reason_categories


def test_future_persistence_timestamp_is_rejected() -> None:
    request = commit_request()
    changed_record = replace(
        request.record,
        persisted_at=request.evaluation_time + timedelta(microseconds=1),
    )
    result = InMemoryPersistenceStore().commit(replace(request, record=changed_record))
    assert PersistenceReason.TEMPORAL_INVALID in result.reason_categories


@pytest.mark.parametrize(
    "field",
    ["unresolved_revalidation", "pending_lifecycle_transition"],
)
def test_stale_source_is_rejected(field: str) -> None:
    request = commit_request()
    evidence = replace(request.source_evidence, **{field: True})
    result = InMemoryPersistenceStore().commit(
        replace(request, source_evidence=evidence)
    )
    assert PersistenceReason.STALE_SOURCE in result.reason_categories


@pytest.mark.parametrize(
    "flag",
    [
        "use_current_alias",
        "use_latest_alias",
        "allow_fallback",
        "infer_predecessor",
        "infer_successor",
    ],
)
def test_implicit_resolution_is_rejected(flag: str) -> None:
    request = replace(commit_request(), **{flag: True})
    assert PersistenceReason.INVALID_REQUEST in InMemoryPersistenceStore().commit(
        request
    ).reason_categories


def test_canonical_tampering_is_rejected() -> None:
    request = commit_request()
    object.__setattr__(request.record, "source_candidate_digest", "sha256:" + "8" * 64)
    result = InMemoryPersistenceStore().commit(request)
    assert PersistenceReason.DIGEST_MISMATCH in result.reason_categories
