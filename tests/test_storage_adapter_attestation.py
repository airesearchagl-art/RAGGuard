from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from ragguard.real_persistence import TestAtomicDurableStore
from ragguard.storage_adapter_attestation import (
    AdapterApprovalResult, AdapterConformanceState, AdapterLifecycleStatus,
    AdapterRegistryFault, AdapterRegistryReason, AdapterReviewResult,
    AdapterRoleContext, StorageAdapterApproval, StorageAdapterReview,
    TestApprovedStorageAdapterRegistry, WriteCompatibilityReason,
    WriteCompatibilityState, evaluate_adapter_conformance,
    evaluate_write_compatibility,
)
from tests.test_real_persistence_contract import (
    commit as persistence_commit, context as persistence_context,
)
from tests.test_storage_adapter_contract import (
    capability, digest, evidence, manifest, policy, result_objects, suite,
)


def chain():
    cap = capability()
    man = manifest(cap)
    pol = policy(cap)
    results = result_objects(man)
    conformance_suite = suite(man, cap, results)
    ev = evidence(man, cap, conformance_suite, results)
    conformance = evaluate_adapter_conformance(
        man, cap, conformance_suite, results, ev, pol,
        evaluation_time=ev.generated_at + timedelta(seconds=1))
    review = StorageAdapterReview(
        "adapter-review-v021", man.canonical_digest, ev.canonical_digest,
        conformance.canonical_digest, conformance.evaluated_at + timedelta(microseconds=1),
        "adapter-reviewer", AdapterReviewResult.APPROVED, digest("7"))
    approval = StorageAdapterApproval(
        "adapter-approval-v021", man.canonical_digest, ev.canonical_digest,
        review.canonical_digest, review.reviewed_at + timedelta(microseconds=1),
        "adapter-approver", AdapterApprovalResult.APPROVED, pol.canonical_digest)
    runtime, _, request, _, _, intent, plan, _ = persistence_context()
    roles = AdapterRoleContext(
        ev.generated_by, review.reviewer_id, approval.approver_id,
        request.requested_by, request.persistence_reviewer_id,
        request.persistence_approver_id, request.persistence_operator_id,
        runtime.runtime_authorization_approver_id)
    return cap, man, pol, ev, conformance, review, approval, roles


def register(store=None, *, fault=AdapterRegistryFault.NONE, **changes):
    store = store or TestApprovedStorageAdapterRegistry()
    cap, man, pol, ev, result, review, approval, roles = chain()
    results = result_objects(man)
    conformance_suite = suite(man, cap, results)
    values = dict(record_id="approved-adapter-v021", manifest=man, capability=cap,
                  suite=conformance_suite, capability_results=results,
                  evidence=ev, conformance=result, review=review, approval=approval,
                  policy=pol, roles=roles, adapter_generation=1,
                  predecessor_record_digest=None,
                  recorded_at=approval.approved_at + timedelta(microseconds=1), fault=fault)
    values.update(changes)
    return store, store.commit(**values)


def v19_objects():
    runtime, _, request, _, _, intent, plan, _ = persistence_context()
    receipt = persistence_commit(TestAtomicDurableStore()).receipt
    assert receipt is not None
    return runtime, request, intent, plan, receipt


def write_decision(*, record=None, **changes):
    _, committed = register()
    record = record or committed.record
    assert record is not None
    cap, man, pol, *_ = chain()
    runtime, request, intent, plan, receipt = v19_objects()
    values = dict(record=record, manifest=man, capability=cap, policy=pol,
                  persistence_request=request, intent=intent, plan=plan,
                  receipt=receipt, runtime_record=runtime,
                  evaluation_time=record.recorded_at + timedelta(seconds=1))
    values.update(changes)
    return evaluate_write_compatibility(**values)


def test_review_and_approval_are_immutable_and_digest_covered():
    *_, review, approval, _ = chain()
    assert replace(review).canonical_digest == review.canonical_digest
    assert replace(approval).canonical_digest == approval.canonical_digest
    with pytest.raises(FrozenInstanceError):
        approval.approver_id = "other"  # type: ignore[misc]


def test_independent_review_then_distinct_approval_commits_review_record_only():
    store, result = register()
    assert result.applied and result.record is not None
    assert result.record.state.value == "approved_for_write_authorization_review"
    assert result.record.lifecycle_status is AdapterLifecycleStatus.APPROVED
    assert (store.write_count, store.mutation_count, store.event_count) == (1, 1, 1)


@pytest.mark.parametrize("part", ["manifest", "evidence", "conformance", "review", "approval", "policy"])
def test_chain_tampering_is_rejected(part):
    cap, man, pol, ev, result, review, approval, roles = chain()
    if part == "manifest": man = replace(man, adapter_version="tampered")
    elif part == "evidence": ev = replace(ev, conformance_suite_digest=digest("8"))
    elif part == "conformance": result = replace(result, manifest_digest=digest("8"))
    elif part == "review": review = replace(review, findings_digest=digest("8"))
    elif part == "approval": approval = replace(approval, review_digest=digest("8"))
    else: pol = replace(pol, policy_version="tampered")
    store, committed = register(manifest=man, capability=cap, evidence=ev,
                                conformance=result, review=review, approval=approval,
                                policy=pol, roles=roles)
    assert not committed.applied
    assert AdapterRegistryReason.INVALID_CHAIN in committed.reasons
    assert store.records == ()


def test_rejected_review_or_approval_cannot_register():
    *_, review, approval, _ = chain()
    assert not register(review=replace(review, review_result=AdapterReviewResult.REJECTED))[1].applied
    assert not register(approval=replace(approval, approval_result=AdapterApprovalResult.REJECTED))[1].applied


def test_review_before_approval_is_strict():
    *_, review, approval, _ = chain()
    result = register(approval=replace(approval, approved_at=review.reviewed_at))[1]
    assert not result.applied and AdapterRegistryReason.TEMPORAL_INVALID in result.reasons


def test_stale_approval_is_rejected():
    *_, approval, _ = chain()
    result = register(recorded_at=approval.approved_at + timedelta(days=91))[1]
    assert not result.applied and AdapterRegistryReason.TEMPORAL_INVALID in result.reasons


def test_all_eight_roles_are_distinct():
    *_, roles = chain()
    with pytest.raises(Exception):
        replace(roles, adapter_approver_id=roles.adapter_reviewer_id)


@pytest.mark.parametrize("fault", [AdapterRegistryFault.CANDIDATE_STATE,
    AdapterRegistryFault.COUNTERS, AdapterRegistryFault.BEFORE_SWAP])
def test_commit_fault_single_swap_does_not_consume_and_retry_succeeds(fault):
    store = TestApprovedStorageAdapterRegistry()
    before = (store.records, store.used_digests, store.write_count,
              store.mutation_count, store.event_count)
    failed = register(store, fault=fault)[1]
    assert not failed.applied and failed.record is None
    assert before == (store.records, store.used_digests, store.write_count,
                      store.mutation_count, store.event_count)
    assert register(store)[1].applied


def test_successful_replay_is_rejected_without_mutation():
    store = TestApprovedStorageAdapterRegistry()
    assert register(store)[1].applied
    before = (store.records, store.used_digests, store.write_count,
              store.mutation_count, store.event_count)
    duplicate = register(store)[1]
    assert not duplicate.applied and AdapterRegistryReason.REPLAY in duplicate.reasons
    assert before == (store.records, store.used_digests, store.write_count,
                      store.mutation_count, store.event_count)


@pytest.mark.parametrize("changes,reason", [
    ({"adapter_generation": 2}, AdapterRegistryReason.GENERATION_MISMATCH),
    ({"predecessor_record_digest": digest("9")}, AdapterRegistryReason.PREDECESSOR_MISMATCH),
])
def test_stale_generation_and_predecessor_are_rejected(changes, reason):
    denied = register(**changes)[1]
    assert not denied.applied and reason in denied.reasons


@pytest.mark.parametrize("status", [AdapterLifecycleStatus.DEPRECATED,
    AdapterLifecycleStatus.REVOKED, AdapterLifecycleStatus.SUPERSEDED])
def test_one_way_lifecycle_transitions(status):
    store, committed = register()
    record = committed.record; assert record is not None
    transitioned = store.transition_status(
        source_record=record, new_record_id=f"adapter-{status.value}", new_status=status,
        transitioned_at=record.recorded_at + timedelta(seconds=1))
    assert transitioned.applied and transitioned.record.lifecycle_status is status


@pytest.mark.parametrize("status", [AdapterLifecycleStatus.REVOKED,
    AdapterLifecycleStatus.SUPERSEDED])
def test_revoked_and_superseded_are_terminal(status):
    store, committed = register(); record = committed.record; assert record
    terminal = store.transition_status(source_record=record, new_record_id="terminal-record",
        new_status=status, transitioned_at=record.recorded_at + timedelta(seconds=1)).record
    assert terminal
    denied = store.transition_status(source_record=terminal, new_record_id="reactivated-record",
        new_status=AdapterLifecycleStatus.DEPRECATED,
        transitioned_at=terminal.recorded_at + timedelta(seconds=1))
    assert not denied.applied and AdapterRegistryReason.STATUS_INVALID in denied.reasons


def test_deprecated_cannot_repeat_or_reactivate():
    store, committed = register(); record = committed.record; assert record
    deprecated = store.transition_status(source_record=record, new_record_id="deprecated-record",
        new_status=AdapterLifecycleStatus.DEPRECATED,
        transitioned_at=record.recorded_at + timedelta(seconds=1)).record
    assert deprecated
    assert not store.transition_status(source_record=deprecated, new_record_id="repeat-record",
        new_status=AdapterLifecycleStatus.DEPRECATED,
        transitioned_at=deprecated.recorded_at + timedelta(seconds=1)).applied


def test_v019_exact_object_chain_is_ready_for_review_not_write():
    decision = write_decision()
    assert decision.state is WriteCompatibilityState.READY_FOR_WRITE_AUTHORIZATION_REVIEW
    assert decision.state.value not in {"ready_for_write", "write_authorized", "committed"}


@pytest.mark.parametrize("part", ["runtime", "request", "intent", "plan", "receipt"])
def test_v019_object_tampering_fails_closed(part):
    runtime, request, intent, plan, receipt = v19_objects()
    if part == "runtime": runtime = replace(runtime, registry_state_digest=digest("8"))
    elif part == "request": request = replace(request, profile_version="tampered")
    elif part == "intent": intent = replace(intent, content_digest=digest("8"))
    elif part == "plan": plan = replace(plan, payload_digest=digest("8"))
    else: receipt = replace(receipt, committed_content_digest=digest("8"))
    decision = write_decision(runtime_record=runtime, persistence_request=request,
                              intent=intent, plan=plan, receipt=receipt)
    assert decision.state is WriteCompatibilityState.INCOMPATIBLE
    assert WriteCompatibilityReason.DIGEST_MISMATCH in decision.reasons


@pytest.mark.parametrize("field", ["generation", "predecessor"])
def test_generation_and_predecessor_are_exact_bound(field):
    runtime, request, intent, plan, receipt = v19_objects()
    if field == "generation": receipt = replace(receipt, generation=receipt.generation + 1)
    else: receipt = replace(receipt, predecessor_digest=digest("9"))
    decision = write_decision(runtime_record=runtime, persistence_request=request,
                              intent=intent, plan=plan, receipt=receipt)
    expected = (WriteCompatibilityReason.GENERATION_MISMATCH
                if field == "generation"
                else WriteCompatibilityReason.PREDECESSOR_MISMATCH)
    assert expected in decision.reasons


@pytest.mark.parametrize("status", [AdapterLifecycleStatus.REVOKED,
    AdapterLifecycleStatus.SUPERSEDED, AdapterLifecycleStatus.DEPRECATED])
def test_nonapproved_lifecycle_cannot_authorize_new_write_review(status):
    store, committed = register(); source = committed.record; assert source
    superseded = store.transition_status(source_record=source, new_record_id=f"{status.value}-record",
        new_status=status,
        transitioned_at=source.recorded_at + timedelta(seconds=1)).record
    assert superseded
    decision = write_decision(record=superseded,
                              evaluation_time=superseded.recorded_at + timedelta(seconds=1))
    assert decision.state is WriteCompatibilityState.NEEDS_ADAPTER_APPROVAL


def test_write_compatibility_is_pure_and_side_effect_free():
    result = write_decision()
    counters = [getattr(result, name) for name in result.__dataclass_fields__
                if name.endswith("_count")]
    assert counters and set(counters) == {0}
