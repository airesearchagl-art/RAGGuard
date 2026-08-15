from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.local_rag_integration import RAGStage
from ragguard.real_data_access import (
    RealDataAccessCacheClass,
    RealDataAccessExportClass,
    RealDataAccessLoggingClass,
    RealDataAccessNetworkClass,
    RealDataAccessPersistenceClass,
    RealDataAccessRetentionClass,
    RealDataDocumentClass,
)
from ragguard.real_data_access_authorization import (
    RealDataAccessAuthorizationLifecycle,
)
from ragguard.real_data_read_execution import (
    ControlledReadFailure,
    PreReadVerificationState,
    ReadExecutionLedgerFault,
    ReadExecutionLedgerReason,
    TestOnlyRealDataReadExecutionLedger,
)
from ragguard.real_data_trial import RealDataClass
from ragguard.storage_adapter import digest
from test_local_rag_execution_session_contract import NOW
from test_real_data_read_execution_contract import read_execution_chain


def pristine_call():
    _, result, call, _ = read_execution_chain(execute=False)
    assert result is None
    return call


def deny(call):
    ledger = TestOnlyRealDataReadExecutionLedger()
    before = ledger.replay_snapshot
    result = ledger.execute(**call)
    assert not result.applied
    assert ledger.replay_snapshot == before == (frozenset(),) * 7
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (0, 0, 0)
    assert result.usage_before.remaining_read_count == 1
    assert result.usage_after is None and result.exhausted_authorization is None
    assert result.side_effects.external_all_zero
    return result


@pytest.mark.parametrize(
    "attribute,value",
    (
        ("operator_id", "forged-authorization-operator"),
        ("selector_digest", digest("forged-authorization-selector")),
        ("policy_digest", digest("forged-authorization-policy")),
    ),
)
def test_forged_authorization_record_fails_closed_before_read(attribute, value):
    call = pristine_call()
    object.__setattr__(call["context"].authorization_record, attribute, value)
    result = deny(call)
    assert ReadExecutionLedgerReason.INVALID_CHAIN in result.reasons
    assert ReadExecutionLedgerReason.PRE_READ_FAILED in result.reasons
    assert result.side_effects.controlled_adapter_read_count == 0


def test_forged_operator_assignment_and_operator_mismatch_fail_closed():
    call = pristine_call()
    object.__setattr__(
        call["context"].operator_assignment, "operator_id", "forged-operator"
    )
    result = deny(call)
    assert ReadExecutionLedgerReason.INVALID_CHAIN in result.reasons
    assert ReadExecutionLedgerReason.ROLE_CONFLICT in result.reasons
    assert result.pre_read.result is PreReadVerificationState.FAILED


def test_forged_target_descriptor_fails_closed():
    call = pristine_call()
    object.__setattr__(call["target"], "target_id", "forged-target")
    result = deny(call)
    assert ReadExecutionLedgerReason.INVALID_CHAIN in result.reasons


@pytest.mark.parametrize(
    "changes",
    (
        {"data_class": RealDataClass.INTERNAL_RESTRICTED},
        {
            "document_class": (
                RealDataDocumentClass.INTERNAL_RESTRICTED_DOCUMENT_CANDIDATE
            )
        },
        {"selector_digest": digest("selector-mismatch")},
    ),
)
def test_target_scope_widening_or_selector_mismatch_is_rejected(changes):
    call = pristine_call()
    call["target"] = replace(call["target"], **changes)
    result = deny(call)
    assert ReadExecutionLedgerReason.TARGET_INVALID in result.reasons


@pytest.mark.parametrize(
    "changes",
    (
        {"max_stage": RAGStage.EMBEDDING},
        {"masking_required_before_stage": RAGStage.EMBEDDING},
        {"retention_class": RealDataAccessRetentionClass.RAW_EPHEMERAL},
        {"logging_class": RealDataAccessLoggingClass.RAW},
        {"cache_class": RealDataAccessCacheClass.RAW},
        {"persistence_class": RealDataAccessPersistenceClass.ALLOWED},
        {"export_class": RealDataAccessExportClass.ALLOWED},
        {"network_class": RealDataAccessNetworkClass.ALLOWED},
    ),
)
def test_policy_widening_or_downgrade_fails_closed_before_read(changes):
    call = pristine_call()
    widened = replace(call["context"].access_policy, **changes)
    call["context"] = replace(call["context"], access_policy=widened)
    result = deny(call)
    assert ReadExecutionLedgerReason.POLICY_INVALID in result.reasons
    assert result.side_effects.controlled_adapter_read_count == 0


@pytest.mark.parametrize(
    "lifecycle,remaining",
    (
        (RealDataAccessAuthorizationLifecycle.REVOKED, 1),
        (RealDataAccessAuthorizationLifecycle.SUPERSEDED, 1),
        (RealDataAccessAuthorizationLifecycle.EXHAUSTED, 0),
    ),
)
def test_revoked_superseded_or_exhausted_authorization_cannot_execute(
    lifecycle, remaining
):
    call = pristine_call()
    record = call["context"].authorization_record
    object.__setattr__(record, "lifecycle", lifecycle)
    object.__setattr__(record, "remaining_read_count", remaining)
    result = deny(call)
    assert ReadExecutionLedgerReason.LIFECYCLE_INVALID in result.reasons


def test_expired_authorization_and_future_execution_metadata_are_rejected():
    expired_call = pristine_call()
    object.__setattr__(
        expired_call["context"].authorization_record,
        "expires_at",
        NOW + timedelta(minutes=29),
    )
    expired = deny(expired_call)
    assert ReadExecutionLedgerReason.TEMPORAL_INVALID in expired.reasons

    future_call = pristine_call()
    future_call["execution_request"] = replace(
        future_call["execution_request"],
        requested_at=NOW + timedelta(minutes=40),
    )
    future = deny(future_call)
    assert ReadExecutionLedgerReason.TEMPORAL_INVALID in future.reasons


@pytest.mark.parametrize(
    "failure,reason",
    (
        (ControlledReadFailure.OPEN_FAILED, ReadExecutionLedgerReason.OPEN_FAILED),
        (ControlledReadFailure.READ_FAILED, ReadExecutionLedgerReason.READ_FAILED),
        (
            ControlledReadFailure.CLASSIFICATION_FAILED,
            ReadExecutionLedgerReason.CLASSIFICATION_FAILED,
        ),
        (
            ControlledReadFailure.MASKING_FAILED,
            ReadExecutionLedgerReason.MASKING_FAILED,
        ),
    ),
)
def test_controlled_failures_never_consume_authorization(failure, reason):
    call = pristine_call()
    call["controlled_failure"] = failure
    result = deny(call)
    assert reason in result.reasons


@pytest.mark.parametrize(
    "fault,reason",
    (
        (
            ReadExecutionLedgerFault.FORGED_EXECUTION_RESULT,
            ReadExecutionLedgerReason.INVALID_CHAIN,
        ),
        (
            ReadExecutionLedgerFault.FORGED_RECEIPT,
            ReadExecutionLedgerReason.INVALID_CHAIN,
        ),
        (
            ReadExecutionLedgerFault.CANDIDATE_STATE,
            ReadExecutionLedgerReason.COMMIT_FAULT,
        ),
        (
            ReadExecutionLedgerFault.BEFORE_SWAP,
            ReadExecutionLedgerReason.COMMIT_FAULT,
        ),
    ),
)
def test_forged_evidence_and_atomic_commit_faults_are_retryable(fault, reason):
    call = pristine_call()
    call["fault"] = fault
    failed_ledger = TestOnlyRealDataReadExecutionLedger()
    failed = failed_ledger.execute(**call)
    assert not failed.applied and reason in failed.reasons
    assert failed_ledger.replay_snapshot == (frozenset(),) * 7
    assert failed.usage_after is None

    call["fault"] = ReadExecutionLedgerFault.NONE
    retried = failed_ledger.execute(**call)
    assert retried.applied
    assert retried.usage_after.remaining_read_count == 0


def test_duplicate_verified_execution_is_rejected_after_single_atomic_commit():
    call = pristine_call()
    ledger = TestOnlyRealDataReadExecutionLedger()
    first = ledger.execute(**call)
    second = ledger.execute(**call)
    assert first.applied and not second.applied
    assert second.reasons == (ReadExecutionLedgerReason.REPLAY,)
    assert len(ledger.receipts) == len(ledger.masked_candidates) == 1
    assert len(ledger.usage_states) == len(ledger.exhausted_authorizations) == 1
    assert all(len(items) == 1 for items in ledger.replay_snapshot)


def test_success_side_effect_accounting_has_only_one_controlled_adapter_read():
    call = pristine_call()
    result = TestOnlyRealDataReadExecutionLedger().execute(**call)
    assert result.applied
    accounting = result.side_effects
    assert accounting.controlled_adapter_read_count == 1
    assert accounting.actual_arbitrary_file_open_count == 0
    assert accounting.actual_arbitrary_file_read_count == 0
    assert accounting.local_rag_material_access_count == 0
    assert accounting.restricted_material_access_count == 0
    assert accounting.real_data_access_count == 0
    assert accounting.external_network_count == 0
    assert accounting.http_count == 0
    assert accounting.cloud_count == 0
    assert accounting.filesystem_write_count == 0
    assert accounting.database_write_count == 0
    assert accounting.persistent_vector_write_count == 0
    assert accounting.production_registry_write_count == 0
    assert accounting.credential_use_count == 0
    assert accounting.token_use_count == 0
    assert accounting.runtime_activation_count == 0
    assert accounting.runtime_switch_count == 0
