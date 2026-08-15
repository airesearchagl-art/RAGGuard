from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from ragguard.one_shot_trial import (
    ControlledFilesystemReadAdapter,
    ControlledFilesystemReadFault,
    OneShotTrialExecutionRequest,
    OneShotTrialExecutionResultState,
    OneShotTrialLedgerFault,
    OneShotTrialLifecycle,
    OneShotTrialReason,
    PreOpenVerificationResult,
    TestOnlyOneShotTrialLedger,
    TrialClosureFault,
)
from ragguard.real_data_access import RealDataByteClass
from ragguard.real_data_access_authorization import (
    RealDataAccessAuthorizationLifecycle,
)
from ragguard.real_target_resolver import (
    ControlledTargetReference,
    RealTargetResolver,
    RealTargetResolverPolicy,
    TrialRootClass,
    TrialRootDescriptor,
    _controlled_root_identity_digest,
    _create_controlled_root_capability,
)
from ragguard.storage_adapter import canonical_object_valid, digest
from ragguard.trial_closure import TrialClosureResult
from test_local_rag_execution_session_contract import NOW
from test_real_data_read_execution_contract import (
    CONTROLLED_FIXTURE,
    MASKED_FIXTURE,
    read_execution_chain,
)


def one_shot_call(tmp_path: Path, **execute_overrides):
    _, _, v026_call, _ = read_execution_chain(execute=False)
    root = tmp_path / "ragguard-v027-controlled-root"
    root.mkdir()
    (root / ".ragguard-v027-controlled-root").touch()
    relative_name = "synthetic-fixture.txt"
    (root / relative_name).write_text(CONTROLLED_FIXTURE, encoding="utf-8")
    root_identity = _controlled_root_identity_digest(root)
    policy = RealTargetResolverPolicy(
        root_identity,
        (".txt",),
        RealDataByteClass.SMALL_DOCUMENT,
    )
    descriptor = TrialRootDescriptor(
        "controlled-trial-root-027",
        TrialRootClass.CONTROLLED_TRIAL_ROOT,
        root_identity,
        policy.canonical_digest,
        NOW + timedelta(minutes=29),
    )
    relative_digest = digest(relative_name)
    capability = _create_controlled_root_capability(
        root_path=root,
        descriptor=descriptor,
        policy=policy,
        target_bindings={relative_digest: relative_name},
    )
    resolver = RealTargetResolver(descriptor, policy, capability)
    target = v026_call["target"]
    reference = ControlledTargetReference(
        "controlled-target-reference-027",
        descriptor.canonical_digest,
        relative_digest,
        target.document_class,
        target.content_identity_digest,
    )
    v026_request = v026_call["execution_request"]
    context = v026_call["context"]
    request = OneShotTrialExecutionRequest(
        "one-shot-trial-execution-request-027",
        v026_request.canonical_digest,
        context.authorization_record.canonical_digest,
        descriptor.canonical_digest,
        reference.canonical_digest,
        v026_request.operator_id,
        NOW + timedelta(minutes=30),
        NOW + timedelta(minutes=70),
    )
    adapter = ControlledFilesystemReadAdapter(
        adapter_id="controlled-filesystem-adapter-027",
        resolver=resolver,
        transformed_payload=MASKED_FIXTURE,
        observed_classification_digest=target.expected_classification_digest,
        sensitive_class_digest=digest("synthetic-sensitive-class-v027"),
        masked_class_digest=digest("synthetic-masked-class-v027"),
        blocked_class_digest=digest("synthetic-blocked-class-v027"),
    )
    times = {
        "pre_open_evaluated_at": NOW + timedelta(minutes=31),
        "started_at": NOW + timedelta(minutes=32),
        "finished_at": NOW + timedelta(minutes=33),
        "classification_evaluated_at": NOW + timedelta(minutes=34),
        "masking_evaluated_at": NOW + timedelta(minutes=35),
        "receipt_issued_at": NOW + timedelta(minutes=36),
        "evaluation_time": NOW + timedelta(minutes=37),
    }
    call = {
        "one_shot_receipt_id": "one-shot-trial-receipt-027",
        "context": context,
        "v0_26_execution_request": v026_request,
        "target_descriptor": target,
        "target_reference": reference,
        "request": request,
        "resolver": resolver,
        "adapter": adapter,
        **times,
        "read_fault": ControlledFilesystemReadFault.NONE,
        "ledger_fault": OneShotTrialLedgerFault.NONE,
    }
    call.update(execute_overrides)
    return TestOnlyOneShotTrialLedger(), call, root


def test_successful_one_shot_read_commits_exactly_once_then_closes(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    result = ledger.execute(**call)
    assert result.applied
    assert result.lifecycle is OneShotTrialLifecycle.POSTVERIFIED
    assert result.pre_open.result is PreOpenVerificationResult.PASSED
    assert result.execution_result.result is OneShotTrialExecutionResultState.READ_SUCCEEDED
    assert result.identity_chain.identity_stable
    assert result.usage_before.remaining_read_count == 1
    assert result.usage_after.remaining_read_count == 0
    assert result.exhausted_authorization.lifecycle is RealDataAccessAuthorizationLifecycle.EXHAUSTED
    assert result.receipt.actual_read_completed
    assert not result.receipt.embedding_authorized
    assert not result.receipt.persistence_authorized
    assert not result.receipt.export_authorized
    assert not result.receipt.runtime_activation_authorized
    assert result.side_effects.controlled_adapter_read_count == 1
    assert result.side_effects.external_all_zero
    assert result.receipt.canonical_digest in ledger.pending_closure_receipt_digests

    closed = ledger.close(
        closure_id="trial-closure-027",
        receipt=result.receipt,
        context=call["context"],
        closed_at=NOW + timedelta(minutes=38),
    )
    assert closed.applied
    assert closed.lifecycle is OneShotTrialLifecycle.CLOSED
    assert closed.closure.closure_result is TrialClosureResult.COMPLETED
    assert not closed.closure.downstream_processing_approved
    assert not closed.closure.persistent_storage_approved
    assert canonical_object_valid(closed.closure)
    assert canonical_object_valid(closed.evidence)
    assert ledger.pending_closure_receipt_digests == frozenset()
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (2, 2, 2)


@pytest.mark.parametrize(
    "fault,reason",
    (
        (ControlledFilesystemReadFault.OPEN_FAILED, OneShotTrialReason.OPEN_FAILED),
        (ControlledFilesystemReadFault.READ_FAILED, OneShotTrialReason.READ_FAILED),
        (ControlledFilesystemReadFault.INCOMPLETE, OneShotTrialReason.INCOMPLETE),
        (
            ControlledFilesystemReadFault.OPEN_IDENTITY_CHANGED,
            OneShotTrialReason.IDENTITY_CHANGED,
        ),
        (
            ControlledFilesystemReadFault.POST_IDENTITY_CHANGED,
            OneShotTrialReason.IDENTITY_CHANGED,
        ),
        (
            ControlledFilesystemReadFault.CONTENT_MUTATED,
            OneShotTrialReason.IDENTITY_CHANGED,
        ),
        (
            ControlledFilesystemReadFault.SYMLINK_SWAPPED,
            OneShotTrialReason.IDENTITY_CHANGED,
        ),
        (
            ControlledFilesystemReadFault.CLASSIFICATION_FAILED,
            OneShotTrialReason.CLASSIFICATION_FAILED,
        ),
        (
            ControlledFilesystemReadFault.MASKING_FAILED,
            OneShotTrialReason.MASKING_FAILED,
        ),
    ),
)
def test_failed_read_or_verification_never_consumes_authorization(
    tmp_path, fault, reason
):
    ledger, call, _ = one_shot_call(tmp_path, read_fault=fault)
    before = ledger.replay_snapshot
    result = ledger.execute(**call)
    assert not result.applied
    assert reason in result.reasons
    assert result.usage_before.remaining_read_count == 1
    assert result.usage_after is None
    assert result.exhausted_authorization is None
    assert result.receipt is None
    assert ledger.replay_snapshot == before == (frozenset(),) * 9
    assert ledger.pending_closure_receipt_digests == frozenset()
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (0, 0, 0)
    assert result.side_effects.external_all_zero


@pytest.mark.parametrize(
    "fault",
    (OneShotTrialLedgerFault.CANDIDATE_STATE, OneShotTrialLedgerFault.BEFORE_SWAP),
)
def test_atomic_commit_fault_keeps_usage_and_replay_state_unchanged(tmp_path, fault):
    ledger, call, _ = one_shot_call(tmp_path, ledger_fault=fault)
    result = ledger.execute(**call)
    assert not result.applied
    assert result.reasons == (OneShotTrialReason.COMMIT_FAULT,)
    assert result.usage_before.remaining_read_count == 1
    assert result.usage_after is None
    assert ledger.receipts == ()
    assert ledger.replay_snapshot == (frozenset(),) * 9
    assert (ledger.write_count, ledger.mutation_count, ledger.event_count) == (0, 0, 0)


def test_forged_receipt_is_rejected_before_atomic_swap(tmp_path):
    ledger, call, _ = one_shot_call(
        tmp_path, ledger_fault=OneShotTrialLedgerFault.FORGED_RECEIPT
    )
    result = ledger.execute(**call)
    assert not result.applied
    assert result.reasons == (OneShotTrialReason.INVALID_CHAIN,)
    assert ledger.receipts == ()
    assert ledger.replay_snapshot == (frozenset(),) * 9


def test_duplicate_execution_and_duplicate_closure_are_rejected(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    first = ledger.execute(**call)
    assert first.applied
    second = ledger.execute(**call)
    assert not second.applied
    assert OneShotTrialReason.REPLAY in second.reasons
    closed = ledger.close(
        closure_id="trial-closure-027",
        receipt=first.receipt,
        context=call["context"],
        closed_at=NOW + timedelta(minutes=38),
    )
    assert closed.applied
    replay = ledger.close(
        closure_id="trial-closure-replay-027",
        receipt=first.receipt,
        context=call["context"],
        closed_at=NOW + timedelta(minutes=39),
    )
    assert not replay.applied
    assert replay.reasons == (OneShotTrialReason.CLOSURE_INVALID,)


def test_closure_fault_is_failed_closed_and_retryable(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    result = ledger.execute(**call)
    before = ledger.replay_snapshot
    failed = ledger.close(
        closure_id="trial-closure-fault-027",
        receipt=result.receipt,
        context=call["context"],
        closed_at=NOW + timedelta(minutes=38),
        fault=TrialClosureFault.BEFORE_SWAP,
    )
    assert not failed.applied
    assert failed.closure.closure_result is TrialClosureResult.FAILED_CLOSED
    assert ledger.replay_snapshot == before
    assert result.receipt.canonical_digest in ledger.pending_closure_receipt_digests
    retried = ledger.close(
        closure_id="trial-closure-retry-027",
        receipt=result.receipt,
        context=call["context"],
        closed_at=NOW + timedelta(minutes=39),
    )
    assert retried.applied


@pytest.mark.parametrize(
    "field,value,reason",
    (
        ("operator_id", "forged-operator", OneShotTrialReason.INVALID_CHAIN),
        (
            "authorization_record_digest",
            digest("wrong-authorization"),
            OneShotTrialReason.INVALID_CHAIN,
        ),
        (
            "root_descriptor_digest",
            digest("wrong-root"),
            OneShotTrialReason.INVALID_CHAIN,
        ),
        (
            "target_reference_digest",
            digest("wrong-reference"),
            OneShotTrialReason.INVALID_CHAIN,
        ),
    ),
)
def test_request_binding_mismatch_fails_before_open(tmp_path, field, value, reason):
    ledger, call, _ = one_shot_call(tmp_path)
    call["request"] = replace(call["request"], **{field: value})
    result = ledger.execute(**call)
    assert not result.applied
    assert reason in result.reasons
    assert result.side_effects.controlled_adapter_read_count == 0
    assert ledger.replay_snapshot == (frozenset(),) * 9
