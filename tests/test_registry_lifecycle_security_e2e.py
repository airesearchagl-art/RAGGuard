from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

import test_registry_admission_security_e2e as phase_e
from ragguard.production_registry import RegistryKind, RegistryStatus, TrustedProductionRegistry
from ragguard.registry_admission import TestRegistryAdmissionStore, enforce_registry_admission
from ragguard.registry_lifecycle import (
    RegistryLifecycleReason,
    RegistryLifecycleRequest,
    TestRegistryLifecycleStore,
    enforce_registry_lifecycle,
)
from ragguard.revalidation import RevalidationTrigger, RevalidationTriggerKind
from test_revalidation_contract import SAFE_CONTEXT


def full_context():
    admission_request = phase_e.lifecycle_request()
    admission_registry = TestRegistryAdmissionStore()
    admission_result = enforce_registry_admission(
        admission_request,
        registry=admission_registry,
    )
    assert admission_result.admitted is True
    assert admission_result.entry is not None
    lifecycle_store = TestRegistryLifecycleStore(admission_registry)
    return admission_request, admission_result.entry, lifecycle_store


def lifecycle_request(
    admission_request,
    entry,
    *,
    kind: RevalidationTriggerKind = RevalidationTriggerKind.EVIDENCE_EXPIRED,
    requested_status: RegistryStatus = RegistryStatus.SUSPENDED,
    actor_id: str = "lifecycle-admin-e2e",
    lifecycle_request_id: str = "lifecycle-request-e2e",
) -> RegistryLifecycleRequest:
    evaluation_time = admission_request.evidence_expires_at
    trigger = RevalidationTrigger(
        trigger_id="revalidation-trigger-e2e",
        trigger_kind=kind,
        observed_at=evaluation_time,
        profile_id=entry.profile_id,
        profile_version=entry.profile_version,
        protocol_version=entry.protocol_version,
        product_id=entry.product_id,
        product_version=entry.product_version,
        registry_entry_digest=entry.canonical_digest,
        admission_decision_digest=entry.admission_decision_digest,
        evidence_digest=entry.evidence_digest,
        actor_id=actor_id,
        safe_context=SAFE_CONTEXT,
        evidence_expires_at=(
            admission_request.evidence_expires_at
            if kind is RevalidationTriggerKind.EVIDENCE_EXPIRED
            else None
        ),
    )
    return RegistryLifecycleRequest(
        lifecycle_request_id=lifecycle_request_id,
        evaluation_time=evaluation_time,
        trigger=trigger,
        expected_current_status=entry.registry_status,
        requested_status=requested_status,
        registry_administrator_id=actor_id,
        expected_entry_digest=entry.canonical_digest,
        expected_restrictions=entry.restrictions,
        safe_context=SAFE_CONTEXT,
    )


def assert_denied(result, store, entry, reason: RegistryLifecycleReason) -> None:
    assert result.applied is False
    assert reason in result.reason_categories
    assert result.event is None
    assert result.transitioned_at is None
    assert store.mutation_count == 0
    assert store.events == ()
    assert store.write_count == 0
    assert store.transport_count == 0
    assert store.http_count == 0
    current = store.resolve_status_exact(
        profile_id=entry.profile_id,
        profile_version=entry.profile_version,
        product_id=entry.product_id,
        product_version=entry.product_version,
        protocol_version=entry.protocol_version,
    )
    assert current.registry_status is entry.registry_status


def test_full_phase_a_to_v012_lifecycle_is_test_only_and_transport_free() -> None:
    admission_request, entry, store = full_context()
    request = lifecycle_request(admission_request, entry)
    result = enforce_registry_lifecycle(
        request,
        registry=store,
        admission_request=admission_request,
    )
    assert result.applied is True, result.reason_categories
    assert result.resulting_status is RegistryStatus.SUSPENDED
    assert store.mutation_count == store.write_count == 1
    assert len(store.events) == 1
    assert store.transport_count == store.http_count == 0
    current = store.resolve_status_exact(
        profile_id=entry.profile_id,
        profile_version=entry.profile_version,
        product_id=entry.product_id,
        product_version=entry.product_version,
        protocol_version=entry.protocol_version,
    )
    assert current.registry_status is RegistryStatus.SUSPENDED
    assert current.plan_digest == entry.plan_digest
    assert current.evidence_digest == entry.evidence_digest
    assert current.admission_decision_digest == entry.admission_decision_digest


def test_future_trigger_denial_has_zero_side_effects() -> None:
    admission_request, entry, store = full_context()
    request = lifecycle_request(admission_request, entry)
    future_trigger = replace(
        request.trigger,
        observed_at=request.evaluation_time + timedelta(microseconds=1),
    )
    denied = replace(request, trigger=future_trigger)
    result = enforce_registry_lifecycle(denied, registry=store, admission_request=admission_request)
    assert_denied(result, store, entry, RegistryLifecycleReason.TRIGGER_NOT_YET_VALID)


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("profile_id", "other-profile", RegistryLifecycleReason.IDENTITY_MISMATCH),
        (
            "registry_entry_digest",
            "sha256:" + "0" * 64,
            RegistryLifecycleReason.DIGEST_MISMATCH,
        ),
        (
            "admission_decision_digest",
            "sha256:" + "1" * 64,
            RegistryLifecycleReason.DIGEST_MISMATCH,
        ),
        (
            "evidence_digest",
            "sha256:" + "2" * 64,
            RegistryLifecycleReason.DIGEST_MISMATCH,
        ),
    ],
)
def test_identity_and_digest_tampering_is_atomic(field_name, value, reason) -> None:
    admission_request, entry, store = full_context()
    request = lifecycle_request(admission_request, entry)
    tampered_trigger = replace(request.trigger, **{field_name: value})
    denied = replace(request, trigger=tampered_trigger)
    result = enforce_registry_lifecycle(
        denied, registry=store, admission_request=admission_request
    )
    assert_denied(result, store, entry, reason)


@pytest.mark.parametrize("actor", ["operator-001", "reviewer-001", "approver-001"])
def test_actor_role_conflict_is_atomic(actor: str) -> None:
    admission_request, entry, store = full_context()
    decision = admission_request.production_admission_decision
    actual_actor = {
        "operator-001": decision.validation_operator_id,
        "reviewer-001": decision.evidence_reviewer_id,
        "approver-001": decision.approver_id,
    }[actor]
    request = lifecycle_request(admission_request, entry, actor_id=actual_actor)
    result = enforce_registry_lifecycle(
        request, registry=store, admission_request=admission_request
    )
    assert_denied(result, store, entry, RegistryLifecycleReason.ROLE_CONFLICT)


def test_expected_status_mismatch_is_atomic() -> None:
    admission_request, entry, store = full_context()
    request = replace(
        lifecycle_request(admission_request, entry),
        expected_current_status=RegistryStatus.DEPRECATED,
    )
    result = enforce_registry_lifecycle(
        request, registry=store, admission_request=admission_request
    )
    assert_denied(result, store, entry, RegistryLifecycleReason.STATUS_MISMATCH)


def test_production_registry_attempt_is_rejected_without_side_effects() -> None:
    admission_request, entry, store = full_context()
    request = lifecycle_request(admission_request, entry)
    production_registry = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    result = enforce_registry_lifecycle(
        request,
        registry=production_registry,
        admission_request=admission_request,
    )
    assert result.applied is False
    assert RegistryLifecycleReason.REGISTRY_WRITE_REJECTED in result.reason_categories
    assert store.mutation_count == store.write_count == 0
    assert store.events == ()


def test_duplicate_request_does_not_create_second_event_or_write() -> None:
    admission_request, entry, store = full_context()
    first = lifecycle_request(admission_request, entry)
    first_result = enforce_registry_lifecycle(
        first,
        registry=store,
        admission_request=admission_request,
    )
    assert first_result.applied, first_result.reason_categories
    current = store.resolve_status_exact(
        profile_id=entry.profile_id,
        profile_version=entry.profile_version,
        product_id=entry.product_id,
        product_version=entry.product_version,
        protocol_version=entry.protocol_version,
    )
    duplicate = lifecycle_request(
        admission_request,
        current,
        kind=RevalidationTriggerKind.ADMINISTRATOR_REVOCATION,
        requested_status=RegistryStatus.REVOKED,
        lifecycle_request_id=first.lifecycle_request_id,
    )
    result = enforce_registry_lifecycle(
        duplicate, registry=store, admission_request=admission_request
    )
    assert result.applied is False
    assert RegistryLifecycleReason.DUPLICATE_TRANSITION in result.reason_categories
    assert store.mutation_count == store.write_count == 1
    assert len(store.events) == 1


def test_result_and_error_do_not_disclose_unsafe_details() -> None:
    admission_request, entry, store = full_context()
    request = lifecycle_request(admission_request, entry)
    result = enforce_registry_lifecycle(
        request, registry=store, admission_request=admission_request
    )
    text = repr(result.safe_summary).lower()
    for forbidden in (
        "endpoint",
        "password",
        "token",
        "cookie",
        "api key",
        "hostname",
        "stack trace",
        "request body",
    ):
        assert forbidden not in text
