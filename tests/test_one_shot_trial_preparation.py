from dataclasses import fields, replace
from datetime import timedelta

import pytest

from ragguard.local_rag_integration import RAGStage
from ragguard.one_shot_trial_preparation import (
    ExecutionPreparationRequest,
    ExecutionPreparationState,
    OneShotTrialExecutionPacket,
    OneShotTrialPreparationError,
    TestOnlyExecutionPreparationRegistry,
    prepare_one_shot_trial,
)
from ragguard.real_trial_approval import validate_real_trial_approval_source
from ragguard.real_trial_root import RealTrialPurposeClass
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_session_contract import NOW
from test_real_trial_approval_contract import approval_chain


def preparation_chain(
    *,
    registry: TestOnlyExecutionPreparationRegistry | None = None,
    prepare: bool = True,
):
    _, approval_result, approval_call = approval_chain()
    source = approval_call["source_context"]
    access = source.read_authorization_context
    packet = OneShotTrialExecutionPacket(
        "one-shot-execution-packet-029",
        approval_result.record.canonical_digest,
        access.authorization_record.canonical_digest,
        approval_call["root_identity"].canonical_digest,
        approval_call["root_attestation"].canonical_digest,
        approval_call["target_selection"].canonical_digest,
        access.operator_assignment.canonical_digest,
        access.operator_assignment.operator_id,
        approval_call["purpose"].canonical_digest,
        RealTrialPurposeClass.LOCAL_RAG_CONFIDENTIALITY_TRIAL,
        source.resolver_policy.canonical_digest,
        approval_call["approval_request"].v0_27_reader_policy_digest,
        approval_call["closure_requirement"].canonical_digest,
        1,
        RAGStage.CHUNKING,
        False,
        False,
        False,
        False,
        False,
        False,
        NOW + timedelta(minutes=40),
        NOW + timedelta(minutes=70),
    )
    request = ExecutionPreparationRequest(
        "execution-preparation-request-029",
        packet.canonical_digest,
        "execution-preparation-requester-029",
        NOW + timedelta(minutes=41),
        NOW + timedelta(minutes=42),
    )
    call = {
        "packet": packet,
        "request": request,
        "approved_trial": approval_result.record,
        "source_context": source,
        "purpose": approval_call["purpose"],
        "provisioning_request": approval_call["provisioning_request"],
        "root_identity": approval_call["root_identity"],
        "root_confinement": approval_call["root_confinement"],
        "link_reparse": approval_call["link_reparse"],
        "permission": approval_call["permission"],
        "write_prohibition": approval_call["write_prohibition"],
        "network_isolation": approval_call["network_isolation"],
        "root_attestation": approval_call["root_attestation"],
        "target_selection": approval_call["target_selection"],
        "closure_requirement": approval_call["closure_requirement"],
        "approval_request": approval_call["approval_request"],
        "security_review": approval_call["security_review"],
        "governance_review": approval_call["governance_review"],
        "execution_approval": approval_call["execution_approval"],
        "roles": approval_call["roles"],
    }
    active_registry = registry or TestOnlyExecutionPreparationRegistry()
    decision = (
        prepare_one_shot_trial(registry=active_registry, **call)
        if prepare
        else None
    )
    return active_registry, decision, call


def test_complete_object_chain_prepares_metadata_only_packet():
    registry, decision, call = preparation_chain()
    assert decision.state is (
        ExecutionPreparationState.READY_FOR_EXPLICIT_EXECUTION_APPROVAL
    )
    assert decision.ready_for_explicit_execution_approval
    assert not decision.execution_authorized
    assert not decision.file_read_executed
    assert decision.side_effects.all_zero
    assert canonical_object_valid(decision)
    assert canonical_object_valid(decision.safe_summary)
    assert registry.prepared_packet_digests == {
        call["packet"].canonical_digest
    }
    assert registry.used_request_digests == {
        call["request"].canonical_digest
    }
    assert registry.preparation_count == 1


def test_packet_exact_binds_v025_v028_objects_and_fixed_policy():
    _, _, call = preparation_chain(prepare=False)
    packet = call["packet"]
    source = call["source_context"]
    access = source.read_authorization_context
    assert packet.approved_trial_digest == call["approved_trial"].canonical_digest
    assert packet.access_authorization_digest == (
        access.authorization_record.canonical_digest
    )
    assert packet.root_identity_digest == call["root_identity"].canonical_digest
    assert packet.root_attestation_digest == (
        call["root_attestation"].canonical_digest
    )
    assert packet.target_selection_digest == (
        call["target_selection"].canonical_digest
    )
    assert packet.operator_assignment_digest == (
        access.operator_assignment.canonical_digest
    )
    assert packet.resolver_policy_digest == source.resolver_policy.canonical_digest
    assert packet.reader_policy_digest == source.resolver_policy.canonical_digest
    assert packet.closure_requirement_digest == (
        call["closure_requirement"].canonical_digest
    )
    assert packet.allowed_read_count == 1
    assert packet.stage_ceiling is RAGStage.CHUNKING
    assert not any(
        (
            packet.raw_retention_allowed,
            packet.raw_logging_allowed,
            packet.raw_cache_allowed,
            packet.persistence_allowed,
            packet.export_allowed,
            packet.network_allowed,
        )
    )


def test_object_backed_access_source_is_revalidated_at_evaluation_time():
    _, _, call = preparation_chain(prepare=False)
    assert validate_real_trial_approval_source(
        call["source_context"],
        evaluation_time=call["request"].evaluation_time,
    ) == ()
    access = call["source_context"].read_authorization_context
    assert access.authorization_record is not None
    assert access.operator_assignment is not None
    assert access.usage_contract is not None
    assert call["source_context"].root_descriptor is not None
    assert call["source_context"].resolver_policy is not None
    assert call["source_context"].controlled_target_reference is not None


def test_safe_summary_contains_only_reviewable_metadata():
    _, decision, call = preparation_chain()
    summary = decision.safe_summary
    assert summary.packet_id == call["packet"].packet_id
    assert summary.operator_id == call["roles"].operator_id
    assert summary.purpose_class is (
        RealTrialPurposeClass.LOCAL_RAG_CONFIDENTIALITY_TRIAL
    )
    assert summary.allowed_read_count == 1
    assert summary.stage_ceiling is RAGStage.CHUNKING
    assert summary.closure_requirement_digest == (
        call["closure_requirement"].canonical_digest
    )
    assert summary.readiness_decision is decision.state
    assert summary.reason_codes == ()


def test_public_packet_and_summary_have_no_locator_or_payload_surface():
    forbidden = {
        "path",
        "filename",
        "directory",
        "root_path",
        "document_path",
        "payload",
        "contents",
        "credential",
        "token",
        "customer",
        "company",
        "person",
        "project",
    }
    for contract in (OneShotTrialExecutionPacket, type(preparation_chain()[1].safe_summary)):
        assert {item.name for item in fields(contract)}.isdisjoint(forbidden)


def test_human_approval_stop_gate_is_explicit_and_final():
    _, decision, _ = preparation_chain()
    assert decision.ready_for_explicit_execution_approval
    assert decision.state.value == "ready_for_explicit_execution_approval"
    assert not decision.execution_authorized
    assert not decision.file_read_executed
    assert not hasattr(decision, "execute")
    assert not hasattr(decision, "read")
    assert not hasattr(decision, "open")


@pytest.mark.parametrize(
    "field",
    (
        "raw_retention_allowed",
        "raw_logging_allowed",
        "raw_cache_allowed",
        "persistence_allowed",
        "export_allowed",
        "network_allowed",
    ),
)
def test_packet_constructor_rejects_policy_widening(field):
    _, _, call = preparation_chain(prepare=False)
    with pytest.raises(OneShotTrialPreparationError, match="execution_packet_invalid"):
        replace(call["packet"], **{field: True})


@pytest.mark.parametrize(
    "field,value",
    (
        ("allowed_read_count", 0),
        ("allowed_read_count", 2),
        ("stage_ceiling", RAGStage.EMBEDDING),
    ),
)
def test_packet_constructor_rejects_read_or_stage_widening(field, value):
    _, _, call = preparation_chain(prepare=False)
    with pytest.raises(OneShotTrialPreparationError, match="execution_packet_invalid"):
        replace(call["packet"], **{field: value})


@pytest.mark.parametrize(
    "field",
    (
        "approved_trial_digest",
        "access_authorization_digest",
        "root_identity_digest",
        "root_attestation_digest",
        "target_selection_digest",
        "operator_assignment_digest",
        "purpose_digest",
        "resolver_policy_digest",
        "reader_policy_digest",
        "closure_requirement_digest",
    ),
)
def test_every_object_binding_is_in_packet_canonical_digest(field):
    _, _, call = preparation_chain(prepare=False)
    changed = replace(call["packet"], **{field: digest(f"changed-{field}")})
    assert changed.canonical_digest != call["packet"].canonical_digest


def test_request_exact_binds_packet_and_evaluation_time():
    _, _, call = preparation_chain(prepare=False)
    request = call["request"]
    assert request.packet_digest == call["packet"].canonical_digest
    assert request.requested_at <= request.evaluation_time
    assert canonical_object_valid(request)


def test_preparation_requires_explicit_test_only_replay_registry():
    _, _, call = preparation_chain(prepare=False)
    with pytest.raises(
        OneShotTrialPreparationError, match="test_only_registry_required"
    ):
        prepare_one_shot_trial(registry=None, **call)
