from __future__ import annotations

from dataclasses import replace

import pytest

from ragguard.real_persistence import (
    DurableCommitFault, DurablePersistenceReason, DurablePersistenceState,
    TestAtomicDurableStore,
)
from tests.test_real_persistence_contract import commit, context, evaluate


def zero_external(result):
    assert (result.filesystem_write_count, result.database_write_count,
            result.external_storage_count, result.registry_write_count,
            result.network_count, result.http_count, result.runtime_activation_count,
            result.credential_use_count, result.token_generation_count) == (0,) * 9


def test_security_paths_a_to_d_are_deterministic_and_side_effect_free():
    assert evaluate(request_changes={"runtime_authorization_record_digest": "sha256:" + "9" * 64}).state is DurablePersistenceState.INELIGIBLE
    assert evaluate(review=None, approval=None).state is DurablePersistenceState.NEEDS_PERSISTENCE_AUTHORIZATION
    assert evaluate(intent=None, plan=None).state is DurablePersistenceState.NEEDS_TRANSACTION_PLAN
    ready = evaluate()
    assert ready.state is DurablePersistenceState.READY_FOR_DURABLE_COMMIT
    zero_external(ready)


def test_successful_test_only_commit_and_recovery_never_touch_external_surfaces():
    store = TestAtomicDurableStore()
    result = commit(store)
    assert result.applied
    zero_external(result)


@pytest.mark.parametrize("fault", list(DurableCommitFault)[1:])
def test_fault_and_crash_injection_leave_every_count_zero(fault):
    store = TestAtomicDurableStore()
    result = commit(store, fault)
    assert not result.applied
    assert DurablePersistenceReason.COMMIT_FAILED in result.reasons
    assert (store.write_count, store.mutation_count, store.event_count) == (0, 0, 0)
    zero_external(result)


def test_forged_intent_and_plan_are_denied_before_commit():
    runtime, _, request, _, _, intent, plan, evaluation_time = context()
    store = TestAtomicDurableStore()
    forged_intent = replace(intent, content_digest="sha256:" + "8" * 64)
    result = store.commit(receipt_id="receipt-forged", decision=evaluate(), request=request,
        intent=forged_intent, plan=plan, runtime_record=runtime,
        committed_at=evaluation_time, committed_by="persistence-operator")
    assert not result.applied
    assert (store.write_count, store.mutation_count, store.event_count) == (0, 0, 0)
    zero_external(result)
