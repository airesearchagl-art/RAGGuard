from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.profile_approval import SemanticVersion
from ragguard.production_registry import RegistryStatus
from ragguard.replacement_admission import (
    ReplacementAdmissionError,
    ReplacementAdmissionReason,
    ReplacementCommitFault,
    TestReplacementAdmissionStore,
    enforce_replacement_admission,
)
from test_replacement_admission_contract import (
    replacement_context,
    replacement_request,
)


def _counts(store: TestReplacementAdmissionStore) -> tuple[int, ...]:
    return (
        len(store.snapshot),
        len(store.events),
        store.write_count,
        store.mutation_count,
        len(store.committed_request_ids),
        store.transport_count,
        store.http_count,
    )


@pytest.mark.parametrize(
    "status", [RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED]
)
def test_replacement_is_atomic_and_keeps_predecessor_immutable(status) -> None:
    context, request = replacement_request(predecessor_status=status)
    store = context[4]
    before = context[3]
    result = enforce_replacement_admission(request, registry=store)

    assert result.applied is True
    assert result.successor_entry is not None
    assert store.snapshot[before.admission_id] == before
    assert store.snapshot[before.admission_id].registry_status is status
    assert result.successor_entry.registry_status is RegistryStatus.ACTIVE
    assert _counts(store) == (2, 1, 1, 1, 1, 0, 0)


@pytest.mark.parametrize("fault", tuple(ReplacementCommitFault))
def test_commit_fault_leaves_all_state_unchanged_and_allows_retry(fault) -> None:
    context, request = replacement_request()
    admission_store, lifecycle_store = context[1], context[2]
    store = TestReplacementAdmissionStore(
        admission_store, lifecycle_store, failure_point=fault
    )
    before = dict(store.snapshot)

    failed = enforce_replacement_admission(request, registry=store)
    assert failed.applied is False
    assert failed.reason_categories == (
        ReplacementAdmissionReason.REGISTRY_COMMIT_FAILED,
    )
    assert dict(store.snapshot) == before
    assert _counts(store) == (1, 0, 0, 0, 0, 0, 0)

    store._disable_failure_injection()
    retried = enforce_replacement_admission(request, registry=store)
    assert retried.applied is True
    assert _counts(store) == (2, 1, 1, 1, 1, 0, 0)


def test_successful_duplicate_retry_is_denied_without_side_effects() -> None:
    context, request = replacement_request()
    store = context[4]
    assert enforce_replacement_admission(request, registry=store).applied
    before = dict(store.snapshot), store.events, _counts(store)

    duplicate = enforce_replacement_admission(request, registry=store)
    assert duplicate.applied is False
    assert ReplacementAdmissionReason.DUPLICATE_REQUEST in duplicate.reason_categories
    assert (dict(store.snapshot), store.events, _counts(store)) == before


def test_exact_resolution_has_no_fallback_or_version_guessing() -> None:
    context, request = replacement_request()
    store = context[4]
    predecessor = context[3]
    result = enforce_replacement_admission(request, registry=store)
    assert result.successor_entry is not None
    entry = result.successor_entry
    resolved = store.resolve_exact(
        entry_id=entry.admission_id,
        profile_id=entry.profile_id,
        profile_version=entry.profile_version,
        product_id=entry.product_id,
        product_version=entry.product_version,
        protocol_version=entry.protocol_version,
        expected_status=RegistryStatus.ACTIVE,
    )
    assert resolved == entry
    assert store.resolve_exact(
        entry_id=predecessor.admission_id,
        profile_id=predecessor.profile_id,
        profile_version=predecessor.profile_version,
        product_id=predecessor.product_id,
        product_version=predecessor.product_version,
        protocol_version=predecessor.protocol_version,
        expected_status=predecessor.registry_status,
    ) == predecessor
    with pytest.raises(ReplacementAdmissionError):
        store.resolve_exact(
            entry_id=entry.admission_id,
            profile_id=entry.profile_id,
            profile_version=entry.profile_version,
            product_id=entry.product_id,
            product_version=SemanticVersion.parse("9.9.9"),
            protocol_version=entry.protocol_version,
            expected_status=RegistryStatus.ACTIVE,
            nearest_version=True,
        )


def test_non_test_store_is_fail_closed() -> None:
    _, request = replacement_request()
    result = enforce_replacement_admission(request, registry=object())
    assert result.applied is False
    assert result.reason_categories == (
        ReplacementAdmissionReason.REGISTRY_WRITE_REJECTED,
    )


def test_successor_id_reuse_is_denied() -> None:
    context, request = replacement_request()
    store = context[4]
    first = enforce_replacement_admission(request, registry=store)
    assert first.applied
    second = replace(request, replacement_request_id="replacement-request-002")
    denied = enforce_replacement_admission(second, registry=store)
    assert denied.applied is False
    assert ReplacementAdmissionReason.DUPLICATE_SUCCESSOR in denied.reason_categories
    assert _counts(store) == (2, 1, 1, 1, 1, 0, 0)


def test_predecessor_to_itself_loop_is_denied() -> None:
    context, request = replacement_request()
    loop = replace(request, replacement_entry_id=context[3].admission_id)
    result = enforce_replacement_admission(loop, registry=context[4])
    assert result.applied is False
    assert ReplacementAdmissionReason.REPLACEMENT_LOOP in result.reason_categories
    assert _counts(context[4]) == (1, 0, 0, 0, 0, 0, 0)


def test_replacement_before_new_admission_decision_is_denied() -> None:
    context, request = replacement_request()
    too_early = replace(
        request,
        evaluation_time=request.new_admission_decision.evaluated_at
        - timedelta(microseconds=1),
    )
    result = enforce_replacement_admission(too_early, registry=context[4])
    assert result.applied is False
    assert ReplacementAdmissionReason.TEMPORAL_INVALID in result.reason_categories
    assert _counts(context[4]) == (1, 0, 0, 0, 0, 0, 0)
