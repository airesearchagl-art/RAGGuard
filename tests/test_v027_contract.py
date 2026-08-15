import inspect
from datetime import timedelta

import ragguard

from ragguard.one_shot_trial import (
    ControlledFilesystemReadAdapter,
    OneShotTrialLifecycle,
)
from ragguard.real_target_resolver import (
    ControlledTargetReference,
    FileIdentitySnapshot,
    RealTargetResolverPolicy,
    TrialRootDescriptor,
)
from ragguard.storage_adapter import canonical_object_valid
from ragguard.trial_closure import PostReadEvidence, TrialClosureRecord
from test_local_rag_execution_session_contract import NOW
from test_one_shot_trial_execution import one_shot_call
from test_real_data_read_execution_contract import read_execution_chain


def test_v027_public_metadata_contracts_are_exported():
    expected = {
        "TrialRootDescriptor": TrialRootDescriptor,
        "RealTargetResolverPolicy": RealTargetResolverPolicy,
        "ControlledTargetReference": ControlledTargetReference,
        "FileIdentitySnapshot": FileIdentitySnapshot,
        "ControlledFilesystemReadAdapter": ControlledFilesystemReadAdapter,
        "TrialClosureRecord": TrialClosureRecord,
        "PostReadEvidence": PostReadEvidence,
    }
    for name, value in expected.items():
        assert name in ragguard.__all__
        assert getattr(ragguard, name) is value


def test_no_public_arbitrary_path_reader_scanner_or_runtime_surface():
    forbidden = {
        "open",
        "read_path",
        "read_file",
        "scan_directory",
        "walk_directory",
        "local_rag_real_material_connector",
        "credential_loader",
        "persistent_writer",
        "runtime_activator",
        "_create_controlled_root_capability",
        "_controlled_root_identity_digest",
    }
    assert forbidden.isdisjoint(ragguard.__all__)
    adapter_parameters = inspect.signature(
        ControlledFilesystemReadAdapter.__init__
    ).parameters
    assert "path" not in adapter_parameters
    assert "root_path" not in adapter_parameters
    assert "filename" not in adapter_parameters


def test_public_root_reference_and_identity_metadata_contain_no_raw_path(tmp_path):
    _, call, _ = one_shot_call(tmp_path)
    resolved = call["resolver"].resolve(
        call["target_reference"], observed_at=NOW + timedelta(minutes=31)
    )
    public_objects = (
        call["resolver"].descriptor,
        call["resolver"].policy,
        call["target_reference"],
        resolved,
        resolved.pre_identity,
    )
    for item in public_objects:
        serialized = item.canonical_json().lower()
        assert "root_path" not in serialized
        assert "absolute_path" not in serialized
        assert "synthetic-fixture.txt" not in serialized
        assert "ragguard-v027-controlled-root" not in serialized
        assert "<safe>" in repr(item)


def test_target_resolved_does_not_equal_read_authorized(tmp_path):
    _, call, _ = one_shot_call(tmp_path)
    resolved = call["resolver"].resolve(
        call["target_reference"], observed_at=NOW + timedelta(minutes=31)
    )
    assert canonical_object_valid(resolved)
    assert not hasattr(resolved, "read_authorized")
    assert not hasattr(resolved, "read")


def test_file_opened_read_completed_and_masking_verified_are_distinct_objects(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    result = ledger.execute(**call)
    assert result.applied
    assert result.execution_result.canonical_digest != result.identity_chain.canonical_digest
    assert result.identity_chain.canonical_digest != result.masking_verification.canonical_digest
    assert result.execution_result.raw_content_digest != result.receipt.transformed_content_digest


def test_one_shot_receipt_never_authorizes_embedding_persistence_export_or_runtime(
    tmp_path,
):
    ledger, call, _ = one_shot_call(tmp_path)
    result = ledger.execute(**call)
    receipt = result.receipt
    assert receipt.actual_read_completed
    assert not receipt.embedding_authorized
    assert not receipt.persistence_authorized
    assert not receipt.export_authorized
    assert not receipt.runtime_activation_authorized


def test_success_consumes_once_and_exhausted_authorization_cannot_be_reused(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    result = ledger.execute(**call)
    assert result.usage_before.remaining_read_count == 1
    assert result.usage_after.remaining_read_count == 0
    assert result.applied
    replay = ledger.execute(**call)
    assert not replay.applied
    assert replay.usage_before.remaining_read_count == 1
    assert len(ledger.receipts) == 1


def test_closure_completed_does_not_approve_downstream_or_persistence(tmp_path):
    ledger, call, _ = one_shot_call(tmp_path)
    result = ledger.execute(**call)
    closed = ledger.close(
        closure_id="release-contract-closure-027",
        receipt=result.receipt,
        context=call["context"],
        closed_at=NOW + timedelta(minutes=38),
    )
    assert closed.applied
    assert closed.lifecycle is OneShotTrialLifecycle.CLOSED
    assert not closed.closure.downstream_processing_approved
    assert not closed.closure.persistent_storage_approved


def test_v026_fixture_only_execution_contract_remains_compatible():
    _, result, _, _ = read_execution_chain()
    assert result.applied
    assert result.side_effects.controlled_adapter_read_count == 1
    assert result.side_effects.external_all_zero


def test_v027_contract_adds_no_cli_or_report_schema_surface():
    assert "one-shot" not in ragguard.__all__
    assert not hasattr(ragguard, "one_shot_trial_command")
    assert not hasattr(ragguard, "one_shot_report_schema")
