from dataclasses import replace
from datetime import timedelta

import pytest

from ragguard.local_rag_integration import RAGStage
from ragguard.one_shot_trial_preparation import (
    ExecutionPreparationReason,
    ExecutionPreparationState,
    TestOnlyExecutionPreparationRegistry,
    prepare_one_shot_trial,
)
from ragguard.real_data_access_authorization import (
    RealDataAccessAuthorizationLifecycle,
)
from ragguard.real_data_trial import RealDataClass
from ragguard.real_trial_root import RootProvisioningVerificationState
from ragguard.storage_adapter import digest
from test_one_shot_trial_preparation import preparation_chain


def _rebind_request(call):
    call["request"] = replace(
        call["request"], packet_digest=call["packet"].canonical_digest
    )


def _apply_case(call, case):
    access = call["source_context"].read_authorization_context
    if case == "forged_approved_trial":
        object.__setattr__(call["approved_trial"], "purpose_digest", digest("forged"))
    elif case == "forged_authorization":
        object.__setattr__(access.authorization_record, "operator_id", "forged-operator")
    elif case == "exhausted_authorization":
        object.__setattr__(
            access.authorization_record,
            "lifecycle",
            RealDataAccessAuthorizationLifecycle.EXHAUSTED,
        )
        object.__setattr__(access.authorization_record, "remaining_read_count", 0)
    elif case == "remaining_count_not_one":
        object.__setattr__(access.usage_contract, "remaining_read_count", 0)
    elif case == "forged_root_attestation":
        object.__setattr__(
            call["root_attestation"], "root_identity_digest", digest("forged-root")
        )
    elif case == "failed_root_verification":
        call["root_confinement"] = replace(
            call["root_confinement"],
            result=RootProvisioningVerificationState.FAILED,
        )
    elif case == "forged_target_selection":
        object.__setattr__(
            call["target_selection"], "target_identity_digest", digest("forged-target")
        )
    elif case == "target_count_gt_one":
        object.__setattr__(call["target_selection"], "max_documents", 2)
    elif case == "data_class_widening":
        object.__setattr__(
            call["target_selection"],
            "data_class",
            RealDataClass.INTERNAL_RESTRICTED,
        )
    elif case == "operator_mismatch":
        call["packet"] = replace(call["packet"], operator_id="different-operator")
        _rebind_request(call)
    elif case == "purpose_mismatch":
        call["packet"] = replace(
            call["packet"], purpose_digest=digest("different-purpose")
        )
        _rebind_request(call)
    elif case == "stage_widening":
        object.__setattr__(call["packet"], "stage_ceiling", RAGStage.EMBEDDING)
    elif case in {
        "raw_retention_allowed",
        "raw_logging_allowed",
        "raw_cache_allowed",
        "persistence_allowed",
        "export_allowed",
        "network_allowed",
    }:
        object.__setattr__(call["packet"], case, True)
    elif case == "missing_closure_requirement":
        call["closure_requirement"] = None
    elif case == "expired_trial":
        object.__setattr__(
            call["approved_trial"],
            "expires_at",
            call["request"].evaluation_time,
        )
    elif case == "expired_authorization":
        object.__setattr__(
            access.authorization_record,
            "expires_at",
            call["request"].evaluation_time,
        )
    elif case == "expired_packet":
        call["packet"] = replace(
            call["packet"], expires_at=call["request"].evaluation_time
        )
        _rebind_request(call)
    elif case == "role_conflict":
        object.__setattr__(
            call["roles"],
            "governance_reviewer_id",
            call["roles"].security_reviewer_id,
        )
    elif case == "forged_packet_digest":
        object.__setattr__(call["packet"], "canonical_digest", digest("forged-packet"))
    elif case == "forged_request":
        object.__setattr__(call["request"], "requested_by", "forged-requester")
    elif case == "consistent_forged_authorization_digest":
        call["packet"] = replace(
            call["packet"],
            access_authorization_digest=digest("forged-authorization"),
        )
        _rebind_request(call)
    else:
        raise AssertionError(case)


@pytest.mark.parametrize(
    "case,expected_state",
    (
        ("forged_approved_trial", ExecutionPreparationState.NEEDS_TRIAL_APPROVAL),
        ("forged_authorization", ExecutionPreparationState.NEEDS_ACCESS_AUTHORIZATION),
        ("exhausted_authorization", ExecutionPreparationState.NEEDS_ACCESS_AUTHORIZATION),
        ("remaining_count_not_one", ExecutionPreparationState.NEEDS_ACCESS_AUTHORIZATION),
        ("forged_root_attestation", ExecutionPreparationState.NEEDS_ROOT_PROVISIONING),
        ("failed_root_verification", ExecutionPreparationState.NEEDS_ROOT_PROVISIONING),
        ("forged_target_selection", ExecutionPreparationState.NEEDS_TARGET_BINDING),
        ("target_count_gt_one", ExecutionPreparationState.NEEDS_TARGET_BINDING),
        ("data_class_widening", ExecutionPreparationState.NEEDS_TARGET_BINDING),
        ("operator_mismatch", ExecutionPreparationState.NEEDS_OPERATOR_BINDING),
        ("purpose_mismatch", ExecutionPreparationState.INELIGIBLE),
        ("stage_widening", ExecutionPreparationState.INELIGIBLE),
        ("raw_retention_allowed", ExecutionPreparationState.INELIGIBLE),
        ("raw_logging_allowed", ExecutionPreparationState.INELIGIBLE),
        ("raw_cache_allowed", ExecutionPreparationState.INELIGIBLE),
        ("persistence_allowed", ExecutionPreparationState.INELIGIBLE),
        ("export_allowed", ExecutionPreparationState.INELIGIBLE),
        ("network_allowed", ExecutionPreparationState.INELIGIBLE),
        ("missing_closure_requirement", ExecutionPreparationState.NEEDS_CLOSURE_REQUIREMENTS),
        ("expired_trial", ExecutionPreparationState.NEEDS_TRIAL_APPROVAL),
        ("expired_authorization", ExecutionPreparationState.NEEDS_ACCESS_AUTHORIZATION),
        ("expired_packet", ExecutionPreparationState.INELIGIBLE),
        ("role_conflict", ExecutionPreparationState.NEEDS_OPERATOR_BINDING),
        ("forged_packet_digest", ExecutionPreparationState.INELIGIBLE),
        ("forged_request", ExecutionPreparationState.INELIGIBLE),
        ("consistent_forged_authorization_digest", ExecutionPreparationState.NEEDS_ACCESS_AUTHORIZATION),
    ),
)
def test_adversarial_preparation_is_fail_closed_and_side_effect_free(
    case, expected_state
):
    registry, _, call = preparation_chain(prepare=False)
    before = registry.replay_snapshot
    _apply_case(call, case)
    decision = prepare_one_shot_trial(registry=registry, **call)
    assert decision.state is expected_state
    assert not decision.ready_for_explicit_execution_approval
    assert not decision.execution_authorized
    assert not decision.file_read_executed
    assert decision.reasons
    assert decision.side_effects.all_zero
    assert registry.replay_snapshot == before == (frozenset(), frozenset())
    assert registry.preparation_count == 0


def test_successful_packet_and_request_replay_is_rejected_without_mutation():
    registry, ready, call = preparation_chain()
    before = registry.replay_snapshot
    replay = prepare_one_shot_trial(registry=registry, **call)
    assert ready.ready_for_explicit_execution_approval
    assert replay.state is ExecutionPreparationState.INELIGIBLE
    assert replay.reasons == (ExecutionPreparationReason.REPLAY,)
    assert replay.side_effects.all_zero
    assert registry.replay_snapshot == before
    assert registry.preparation_count == 1


def test_rejection_never_exposes_or_invokes_an_execution_surface(monkeypatch):
    registry, _, call = preparation_chain(prepare=False)
    calls = {
        "open": 0,
        "read": 0,
        "filesystem": 0,
        "network": 0,
        "credential": 0,
        "runtime": 0,
    }
    _apply_case(call, "forged_packet_digest")
    decision = prepare_one_shot_trial(registry=registry, **call)
    assert not decision.ready_for_explicit_execution_approval
    assert calls == {key: 0 for key in calls}
    assert decision.side_effects.all_zero


def test_all_accounted_external_and_real_data_side_effects_are_zero():
    _, decision, _ = preparation_chain()
    accounting = decision.side_effects
    assert accounting.actual_file_open_count == 0
    assert accounting.actual_file_read_count == 0
    assert accounting.actual_real_data_access_count == 0
    assert accounting.arbitrary_filesystem_read_count == 0
    assert accounting.directory_scan_count == 0
    assert accounting.local_rag_material_access_count == 0
    assert accounting.restricted_material_access_count == 0
    assert accounting.filesystem_write_count == 0
    assert accounting.database_write_count == 0
    assert accounting.persistent_vector_write_count == 0
    assert accounting.external_network_count == 0
    assert accounting.http_count == 0
    assert accounting.cloud_count == 0
    assert accounting.production_registry_write_count == 0
    assert accounting.credential_use_count == 0
    assert accounting.token_use_count == 0
    assert accounting.runtime_activation_count == 0
    assert accounting.runtime_switch_count == 0
