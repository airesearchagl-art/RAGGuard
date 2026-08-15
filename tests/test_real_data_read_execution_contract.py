from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.real_data_access import (
    RealDataByteClass,
    RealDataDocumentClass,
)
from ragguard.real_data_access_authorization import (
    RealDataAccessAuthorizationLifecycle,
)
from ragguard.real_data_read_execution import (
    ControlledReadAdapter,
    ControlledReadFailure,
    PreReadVerificationState,
    ReadExecutionLedgerFault,
    ReadExecutionLedgerReason,
    ReadExecutionLifecycle,
    ReadTargetDescriptor,
    RealDataReadAuthorizationContext,
    RealDataReadExecutionRequest,
    TestOnlyRealDataReadExecutionLedger,
)
from ragguard.real_data_read_receipt import (
    PostReadVerificationState,
    ReadDownstreamState,
    ReadExecutionResultState,
    RealDataReadReceiptResult,
)
from ragguard.real_data_trial import RealDataClass
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_session_contract import NOW
from test_real_data_access_authorization import authorized_access_chain


CONTROLLED_FIXTURE = "synthetic internal-low fixture marker alpha"
MASKED_FIXTURE = "[MASKED] internal-low fixture marker alpha"


def read_execution_chain(
    *,
    ledger: TestOnlyRealDataReadExecutionLedger | None = None,
    execute: bool = True,
    controlled_failure: ControlledReadFailure = ControlledReadFailure.NONE,
    fault: ReadExecutionLedgerFault = ReadExecutionLedgerFault.NONE,
    **time_overrides,
):
    _, access_result, kwargs, _ = authorized_access_chain()
    assert access_result.record is not None
    assert access_result.usage_contract is not None
    context = RealDataReadAuthorizationContext(
        selector=kwargs["selector"],
        access_policy=kwargs["access_policy"],
        access_request=kwargs["request"],
        access_security_review=kwargs["security_review"],
        access_governance_review=kwargs["governance_review"],
        operator_assignment=kwargs["operator_assignment"],
        access_approval=kwargs["approval"],
        authorization_record=access_result.record,
        usage_contract=access_result.usage_contract,
        access_roles=kwargs["roles"],
        approved_trial=kwargs["approved_trial"],
        trial_scope=kwargs["trial_scope"],
        classification_policy=kwargs["classification_policy"],
        stage_policy=kwargs["stage_policy"],
        retention_policy=kwargs["retention_policy"],
        logging_policy=kwargs["logging_policy"],
        cache_policy=kwargs["cache_policy"],
        export_policy=kwargs["export_policy"],
        persistence_policy=kwargs["persistence_policy"],
        trial_request=kwargs["trial_request"],
        trial_security_review=kwargs["trial_security_review"],
        trial_governance_review=kwargs["trial_governance_review"],
        trial_approval=kwargs["trial_approval"],
        environment_approval=kwargs["environment_approval"],
        approved_session=kwargs["approved_session"],
    )
    execution_request = RealDataReadExecutionRequest(
        execution_request_id="read-execution-request-026",
        authorization_record_digest=access_result.record.canonical_digest,
        selector_digest=kwargs["selector"].canonical_digest,
        access_policy_digest=kwargs["access_policy"].canonical_digest,
        approved_trial_record_digest=kwargs["approved_trial"].canonical_digest,
        operator_assignment_digest=kwargs["operator_assignment"].canonical_digest,
        operator_id=kwargs["operator_assignment"].operator_id,
        usage_state_digest=access_result.usage_contract.canonical_digest,
        requested_at=NOW + timedelta(minutes=29),
        expires_at=NOW + timedelta(minutes=75),
    )
    target = ReadTargetDescriptor(
        target_id="controlled-target-026",
        selector_digest=kwargs["selector"].canonical_digest,
        data_class=RealDataClass.INTERNAL_LOW,
        document_class=RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,
        content_identity_digest=digest(CONTROLLED_FIXTURE),
        expected_classification_digest=kwargs[
            "classification_policy"
        ].canonical_digest,
        expected_size_class=RealDataByteClass.SMALL_DOCUMENT,
    )
    adapter = ControlledReadAdapter(
        adapter_id="controlled-fixture-adapter-026",
        target_descriptor_digest=target.canonical_digest,
        fixture_payload=CONTROLLED_FIXTURE,
        transformed_payload=MASKED_FIXTURE,
        observed_classification_digest=target.expected_classification_digest,
        sensitive_class_digest=digest("synthetic-sensitive-class"),
        masked_class_digest=digest("synthetic-masked-class"),
        blocked_class_digest=digest("synthetic-blocked-class"),
    )
    times = {
        "pre_read_evaluated_at": NOW + timedelta(minutes=30),
        "started_at": NOW + timedelta(minutes=31),
        "finished_at": NOW + timedelta(minutes=32),
        "classification_evaluated_at": NOW + timedelta(minutes=33),
        "masking_evaluated_at": NOW + timedelta(minutes=34),
        "receipt_issued_at": NOW + timedelta(minutes=35),
        "evaluation_time": NOW + timedelta(minutes=36),
    }
    times.update(time_overrides)
    active_ledger = ledger or TestOnlyRealDataReadExecutionLedger()
    execute_kwargs = {
        "receipt_id": "real-data-read-receipt-026",
        "execution_id": "real-data-read-execution-026",
        "candidate_id": "verified-masked-candidate-026",
        "context": context,
        "execution_request": execution_request,
        "target": target,
        "adapter": adapter,
        **times,
        "controlled_failure": controlled_failure,
        "fault": fault,
    }
    result = active_ledger.execute(**execute_kwargs) if execute else None
    return active_ledger, result, execute_kwargs, kwargs


def test_verified_controlled_read_commits_exact_object_backed_chain_once():
    ledger, result, call, _ = read_execution_chain()
    assert result.applied
    assert result.lifecycle is ReadExecutionLifecycle.RECEIPT_COMMITTED
    assert result.pre_read.result is PreReadVerificationState.PASSED
    assert result.execution_result.result is ReadExecutionResultState.READ_SUCCEEDED
    assert result.classification_result.result is PostReadVerificationState.PASSED
    assert result.masking_verification.result is PostReadVerificationState.PASSED
    assert result.receipt.result is RealDataReadReceiptResult.VERIFIED_READ_COMPLETED
    assert result.masked_candidate.stage is (
        ReadDownstreamState.VERIFIED_MASKED_CONTENT_CANDIDATE
    )
    assert result.receipt.operator_id == call["execution_request"].operator_id
    assert result.receipt.execution_result_digest == (
        result.execution_result.canonical_digest
    )
    assert result.receipt.classification_result_digest == (
        result.classification_result.canonical_digest
    )
    assert result.receipt.masking_verification_digest == (
        result.masking_verification.canonical_digest
    )
    assert all(
        canonical_object_valid(item)
        for item in (
            result.pre_read,
            result.execution_result,
            result.classification_result,
            result.masking_verification,
            result.receipt,
            result.masked_candidate,
            result.usage_after,
            result.exhausted_authorization,
        )
    )
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (1, 1, 1)


def test_successful_verified_read_consumes_exactly_one_and_exhausts_record():
    ledger, result, _, _ = read_execution_chain()
    assert result.usage_before.remaining_read_count == 1
    assert result.usage_after.remaining_read_count == 0
    assert result.exhausted_authorization.remaining_read_count == 0
    assert result.exhausted_authorization.lifecycle is (
        RealDataAccessAuthorizationLifecycle.EXHAUSTED
    )
    assert result.exhausted_authorization.predecessor_authorization_digest == (
        result.pre_read.authorization_record_digest
    )
    assert result.usage_after.authorization_record_digest == (
        result.exhausted_authorization.canonical_digest
    )
    assert len(ledger.usage_states) == len(ledger.exhausted_authorizations) == 1
    assert all(len(items) == 1 for items in ledger.replay_snapshot)


@pytest.mark.parametrize(
    "failure,reason,controlled_count",
    (
        (ControlledReadFailure.OPEN_FAILED, ReadExecutionLedgerReason.OPEN_FAILED, 0),
        (ControlledReadFailure.READ_FAILED, ReadExecutionLedgerReason.READ_FAILED, 1),
        (ControlledReadFailure.INCOMPLETE, ReadExecutionLedgerReason.INCOMPLETE, 1),
        (
            ControlledReadFailure.CLASSIFICATION_FAILED,
            ReadExecutionLedgerReason.CLASSIFICATION_FAILED,
            1,
        ),
        (
            ControlledReadFailure.MASKING_FAILED,
            ReadExecutionLedgerReason.MASKING_FAILED,
            1,
        ),
    ),
)
def test_failed_read_or_verification_does_not_consume_usage(
    failure, reason, controlled_count
):
    ledger, result, _, _ = read_execution_chain(controlled_failure=failure)
    assert not result.applied and reason in result.reasons
    assert result.usage_before.remaining_read_count == 1
    assert result.usage_after is None and result.exhausted_authorization is None
    assert result.side_effects.controlled_adapter_read_count == controlled_count
    assert result.side_effects.external_all_zero
    assert ledger.replay_snapshot == (frozenset(),) * 7
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (0, 0, 0)


@pytest.mark.parametrize(
    "fault,reason",
    (
        (ReadExecutionLedgerFault.FORGED_EXECUTION_RESULT, ReadExecutionLedgerReason.INVALID_CHAIN),
        (ReadExecutionLedgerFault.FORGED_RECEIPT, ReadExecutionLedgerReason.INVALID_CHAIN),
        (ReadExecutionLedgerFault.CANDIDATE_STATE, ReadExecutionLedgerReason.COMMIT_FAULT),
        (ReadExecutionLedgerFault.BEFORE_SWAP, ReadExecutionLedgerReason.COMMIT_FAULT),
    ),
)
def test_forgery_and_commit_faults_leave_usage_and_replay_unchanged(fault, reason):
    ledger, result, _, _ = read_execution_chain(fault=fault)
    assert not result.applied and reason in result.reasons
    assert result.usage_after is None
    assert ledger.replay_snapshot == (frozenset(),) * 7
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (0, 0, 0)


def test_successful_duplicate_execution_is_rejected_without_second_consumption():
    ledger, first, call, _ = read_execution_chain()
    second = ledger.execute(**call)
    assert first.applied and not second.applied
    assert ReadExecutionLedgerReason.REPLAY in second.reasons
    assert len(ledger.receipts) == len(ledger.usage_states) == 1
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (1, 1, 1)


def test_operator_mismatch_fails_pre_read_before_controlled_adapter_read():
    ledger, _, call, _ = read_execution_chain()
    fresh_ledger = TestOnlyRealDataReadExecutionLedger()
    request = replace(call["execution_request"], operator_id="mismatched-operator")
    denied = fresh_ledger.execute(**{**call, "execution_request": request})
    assert not denied.applied
    assert ReadExecutionLedgerReason.ROLE_CONFLICT in denied.reasons
    assert ReadExecutionLedgerReason.PRE_READ_FAILED in denied.reasons
    assert denied.side_effects.controlled_adapter_read_count == 0
    assert fresh_ledger.replay_snapshot == (frozenset(),) * 7
    assert ledger.event_count == 1


def test_selector_mismatch_fails_pre_read_and_never_consumes_usage():
    _, _, call, _ = read_execution_chain()
    target = replace(call["target"], selector_digest=digest("wrong-selector"))
    denied_ledger = TestOnlyRealDataReadExecutionLedger()
    denied = denied_ledger.execute(**{**call, "target": target})
    assert not denied.applied
    assert ReadExecutionLedgerReason.TARGET_INVALID in denied.reasons
    assert denied.pre_read.result is PreReadVerificationState.FAILED
    assert denied.side_effects.controlled_adapter_read_count == 0
    assert denied_ledger.replay_snapshot == (frozenset(),) * 7


@pytest.mark.parametrize(
    "name,value",
    (
        ("started_at", NOW + timedelta(minutes=34)),
        ("finished_at", NOW + timedelta(minutes=30)),
        ("evaluation_time", NOW + timedelta(minutes=90)),
    ),
)
def test_invalid_temporal_order_or_expiry_is_rejected_without_consumption(name, value):
    ledger, result, _, _ = read_execution_chain(**{name: value})
    assert not result.applied
    assert ReadExecutionLedgerReason.TEMPORAL_INVALID in result.reasons
    assert result.usage_after is None
    assert ledger.replay_snapshot == (frozenset(),) * 7


def test_controlled_adapter_accounting_reports_only_fixture_read():
    _, result, _, _ = read_execution_chain()
    assert result.side_effects.controlled_adapter_read_count == 1
    assert result.side_effects.external_all_zero
