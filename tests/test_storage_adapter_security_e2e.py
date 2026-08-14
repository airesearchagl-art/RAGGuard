from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.storage_adapter import CredentialMode, FilesystemMode, NetworkMode
from ragguard.storage_adapter_attestation import (
    AdapterApprovalResult, AdapterCapabilityName, AdapterCapabilityTestResult,
    AdapterLifecycleStatus, AdapterRegistryReason, AdapterReviewResult,
    StorageAdapterApproval, StorageAdapterReview,
    TestApprovedStorageAdapterRegistry, WriteCompatibilityState,
    evaluate_adapter_conformance,
)
from tests.test_storage_adapter_attestation import chain, register, v19_objects, write_decision
from tests.test_storage_adapter_contract import (
    capability, digest, evidence, manifest, policy, result_objects, suite,
)


def zero_side_effects(value) -> None:
    names = [name for name in value.__dataclass_fields__ if name.endswith("_count")]
    assert names and {getattr(value, name) for name in names} == {0}


@pytest.mark.parametrize("changes", [
    {"credential_mode": CredentialMode.EXTERNAL_REQUIRED},
    {"network_mode": NetworkMode.EXTERNAL_REQUIRED},
    {"filesystem_mode": FilesystemMode.ACTUAL_REQUESTED},
])
def test_unsafe_adapter_claims_fail_closed_without_side_effects(changes):
    cap = capability(); man = manifest(cap, **changes); ev = evidence(man, cap)
    *_, result, review, approval, roles = chain()
    denied = register(manifest=man, capability=cap, evidence=ev,
                      conformance=result, review=review, approval=approval,
                      policy=policy(cap), roles=roles)[1]
    assert not denied.applied
    zero_side_effects(denied)


@pytest.mark.parametrize("identity_field,source_field", [
    ("evidence_producer_id", "generated_by"),
    ("adapter_reviewer_id", "reviewer_id"),
    ("adapter_approver_id", "approver_id"),
])
def test_self_declared_role_substitution_cannot_cross_exact_binding(identity_field, source_field):
    cap, man, pol, ev, result, review, approval, roles = chain()
    forged = replace(roles, **{identity_field: "forged-identity"})
    denied = register(manifest=man, capability=cap, evidence=ev, conformance=result,
                      review=review, approval=approval, policy=pol, roles=forged)[1]
    assert not denied.applied and AdapterRegistryReason.INVALID_CHAIN in denied.reasons
    zero_side_effects(denied)


def test_approval_claim_without_approved_review_is_not_enough():
    *_, review, approval, _ = chain()
    denied = register(review=replace(review, review_result=AdapterReviewResult.NEEDS_MORE_EVIDENCE),
                      approval=replace(approval, approval_result=AdapterApprovalResult.APPROVED))[1]
    assert not denied.applied
    zero_side_effects(denied)


def test_forged_approved_record_digest_does_not_authorize_write_review():
    _, committed = register(); record = committed.record; assert record
    forged = replace(record, manifest_digest=digest("a"))
    decision = write_decision(record=forged)
    assert decision.state is WriteCompatibilityState.INCOMPATIBLE
    zero_side_effects(decision)


def test_superseded_record_cannot_fallback_to_previous_approval():
    store, committed = register(); record = committed.record; assert record
    superseded = store.transition_status(source_record=record,
        new_record_id="superseded-security", new_status=AdapterLifecycleStatus.SUPERSEDED,
        transitioned_at=record.recorded_at + timedelta(seconds=1)).record
    assert superseded
    decision = write_decision(record=superseded,
                              evaluation_time=superseded.recorded_at + timedelta(seconds=1))
    assert decision.state is not WriteCompatibilityState.READY_FOR_WRITE_AUTHORIZATION_REVIEW
    zero_side_effects(decision)


def test_v019_runtime_and_receipt_tampering_are_independently_rejected():
    runtime, request, intent, plan, receipt = v19_objects()
    runtime_result = write_decision(runtime_record=replace(
        runtime, runtime_approval_digest=digest("b")))
    receipt_result = write_decision(receipt=replace(
        receipt, authorization_record_digest=digest("c")))
    for result in (runtime_result, receipt_result):
        assert result.state is WriteCompatibilityState.INCOMPATIBLE
        zero_side_effects(result)


def test_denial_keeps_registry_snapshot_and_replay_sets_unchanged():
    store = TestApprovedStorageAdapterRegistry()
    before = (store.records, store.used_digests, store.write_count,
              store.mutation_count, store.event_count)
    *_, review, approval, _ = chain()
    denied = register(store, approval=replace(
        approval, review_digest=digest("d")))[1]
    assert not denied.applied
    assert before == (store.records, store.used_digests, store.write_count,
                      store.mutation_count, store.event_count)
    zero_side_effects(denied)


def test_safe_repr_does_not_expose_location_or_credentials():
    cap, man, pol, ev, _, review, approval, _ = chain()
    text = " ".join(map(repr, (cap, man, pol, ev, review, approval))).lower()
    assert not any(value in text for value in ("http://", "https://", "password", "bearer ", "c:\\"))


@pytest.mark.parametrize("attack", [
    "forged_capability", "forged_suite", "forged_individual",
    "missing", "failed", "incomplete",
])
def test_object_backed_capability_attacks_fail_closed_without_consumption(attack):
    cap = capability()
    if attack == "forged_capability":
        object.__setattr__(cap, "canonical_digest", digest("e"))
    man = manifest(cap)
    overrides = {}
    if attack == "failed":
        overrides[AdapterCapabilityName.ATOMIC_COMMIT] = AdapterCapabilityTestResult.FAILED
    if attack == "incomplete":
        overrides[AdapterCapabilityName.RECOVERY_PROBE] = AdapterCapabilityTestResult.INCOMPLETE
    results = result_objects(man, result_overrides=overrides)
    if attack == "missing":
        results = results[:-1]
    if attack == "forged_individual":
        object.__setattr__(results[0], "canonical_digest", digest("d"))
    conformance_suite = suite(man, cap, results)
    if attack == "forged_suite":
        object.__setattr__(conformance_suite, "canonical_digest", digest("c"))
    ev = evidence(man, cap, conformance_suite, results)
    pol = policy(cap)
    decision = evaluate_adapter_conformance(
        man, cap, conformance_suite, results, ev, pol,
        evaluation_time=ev.generated_at + timedelta(seconds=1),
    )
    review = StorageAdapterReview(
        f"review-{attack}", man.canonical_digest, ev.canonical_digest,
        decision.canonical_digest, decision.evaluated_at + timedelta(microseconds=1),
        "adapter-reviewer", AdapterReviewResult.APPROVED, digest("a"),
    )
    approval = StorageAdapterApproval(
        f"approval-{attack}", man.canonical_digest, ev.canonical_digest,
        review.canonical_digest, review.reviewed_at + timedelta(microseconds=1),
        "adapter-approver", AdapterApprovalResult.APPROVED, pol.canonical_digest,
    )
    *_, roles = chain()
    store = TestApprovedStorageAdapterRegistry()
    before = (store.records, store.used_digests, store.write_count,
              store.mutation_count, store.event_count)
    denied = register(
        store, manifest=man, capability=cap, suite=conformance_suite,
        capability_results=results, evidence=ev, conformance=decision,
        review=review, approval=approval, policy=pol, roles=roles,
        recorded_at=approval.approved_at + timedelta(microseconds=1),
    )[1]
    assert not denied.applied
    assert before == (store.records, store.used_digests, store.write_count,
                      store.mutation_count, store.event_count)
    zero_side_effects(denied)
