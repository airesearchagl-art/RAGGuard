from __future__ import annotations

from dataclasses import replace

import pytest

from ragguard.activation_commit import AuthorizationCommitFault, TestRuntimeAuthorizationLedger
from ragguard.production_registry import RegistryStatus
from ragguard.runtime_authorization import RuntimeAuthorizationResult
from tests.test_activation_commit_contract import assert_no_external_effects, commit
from tests.test_runtime_authorization_contract import assert_zero, evaluate, runtime_context


def test_a_missing_equivalence_stops_before_persistence():
    result = evaluate(chain_value=None)
    assert result.result is RuntimeAuthorizationResult.NEEDS_EQUIVALENCE_APPROVAL
    assert_zero(result)


def test_b_stale_persistence_stops_before_activation_plan():
    result = evaluate(receipt_value=None)
    assert result.result is RuntimeAuthorizationResult.NEEDS_PERSISTENCE_VERIFICATION
    assert_zero(result)


def test_c_missing_activation_plan_is_explicit():
    result = evaluate(plan_value=None)
    assert result.result is RuntimeAuthorizationResult.NEEDS_ACTIVATION_COMMIT_PLAN
    assert_zero(result)


def test_d_missing_runtime_review_is_explicit():
    result = evaluate(review_value=None, approval_value=None)
    assert result.result is RuntimeAuthorizationResult.NEEDS_RUNTIME_AUTHORIZATION_REVIEW
    assert_zero(result)


def test_e_full_fixture_is_commit_ready_not_active():
    result = evaluate()
    assert result.result is RuntimeAuthorizationResult.READY_FOR_RUNTIME_AUTHORIZATION_COMMIT
    assert_zero(result)


def test_f_commit_record_does_not_activate_runtime():
    result = commit(TestRuntimeAuthorizationLedger())
    assert result.applied and result.record is not None
    assert result.runtime_activation_count == 0
    assert_no_external_effects(result)


@pytest.mark.parametrize("change", [
    {"use_current_alias": True}, {"allow_fallback": True},
    {"expected_registry_state_digest": "sha256:" + "9" * 64},
    {"expected_lifecycle_status": RegistryStatus.REVOKED},
    {"runtime_authorization_reviewer_id": "equivalence-reviewer"},
])
def test_denial_matrix_is_fail_closed(change):
    result = evaluate(request_changes=change)
    assert result.result is RuntimeAuthorizationResult.INELIGIBLE
    assert_zero(result)


def test_commit_fault_leaves_all_counts_zero_and_retries():
    store = TestRuntimeAuthorizationLedger()
    failed = commit(store, fault=AuthorizationCommitFault.BEFORE_SWAP)
    assert not failed.applied
    assert (store.write_count, store.mutation_count, store.event_count) == (0, 0, 0)
    assert_no_external_effects(failed)
    assert commit(store).applied


def test_future_runtime_request_is_ineligible():
    *_, request, _, _, evaluation_time = runtime_context()
    result = evaluate(request_changes={"requested_at": evaluation_time.replace(year=evaluation_time.year + 1)})
    assert result.result is RuntimeAuthorizationResult.INELIGIBLE
    assert_zero(result)
