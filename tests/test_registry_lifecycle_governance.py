from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import ragguard
from ragguard.production_registry import RegistryKind, RegistryStatus, TrustedProductionRegistry
from ragguard.registry_admission import TestRegistryAdmissionStore, enforce_registry_admission
from ragguard.registry_lifecycle import (
    CANONICAL_REGISTRY_LIFECYCLE_DIGEST_ALGORITHM,
    RegistryLifecycleError,
    RegistryLifecycleReason,
    RegistryLifecycleRequest,
    TestRegistryLifecycleStore,
    enforce_registry_lifecycle,
)
from ragguard.revalidation import RevalidationTriggerKind
from test_registry_admission_enforcement import request as admission_request_factory
from test_revalidation_contract import SAFE_CONTEXT, TRIGGER_TIME, trigger


MODULE = Path(__file__).parents[1] / "src" / "ragguard" / "registry_lifecycle.py"


def test_public_api_exports_v012_contracts() -> None:
    expected = {
        "CANONICAL_REGISTRY_LIFECYCLE_DIGEST_ALGORITHM",
        "CANONICAL_REVALIDATION_DIGEST_ALGORITHM",
        "RegistryLifecycleError",
        "RegistryLifecycleEvent",
        "RegistryLifecycleReason",
        "RegistryLifecycleRequest",
        "RegistryLifecycleResult",
        "RegistryRevalidationTrigger",
        "RevalidationAction",
        "RevalidationRequirement",
        "RevalidationTriggerKind",
        "TestRegistryLifecycleStore",
        "enforce_registry_lifecycle",
        "evaluate_revalidation_requirement",
    }
    assert expected.issubset(set(ragguard.__all__))
    assert all(hasattr(ragguard, name) for name in expected)


def context(*, fail_commit: bool = False):
    admission_request = admission_request_factory()
    admission_registry = TestRegistryAdmissionStore()
    admission_result = enforce_registry_admission(
        admission_request,
        registry=admission_registry,
    )
    assert admission_result.admitted is True
    assert admission_result.entry is not None
    lifecycle_store = TestRegistryLifecycleStore(
        admission_registry,
        fail_commit=fail_commit,
    )
    return admission_request, admission_result.entry, lifecycle_store


def lifecycle_request(
    admission_request,
    entry,
    *,
    kind: RevalidationTriggerKind = RevalidationTriggerKind.ADMINISTRATOR_SUSPENSION,
    requested_status: RegistryStatus = RegistryStatus.SUSPENDED,
    expected_status: RegistryStatus | None = None,
    lifecycle_request_id: str = "lifecycle-request-001",
    actor_id: str = "lifecycle-admin-001",
    evaluation_time: datetime = TRIGGER_TIME,
    **overrides: object,
) -> RegistryLifecycleRequest:
    observed_at = evaluation_time
    evidence_expires_at = None
    if kind is RevalidationTriggerKind.EVIDENCE_EXPIRED:
        observed_at = admission_request.evidence_expires_at
        evaluation_time = admission_request.evidence_expires_at
        evidence_expires_at = admission_request.evidence_expires_at
    item = trigger(
        entry,
        admission_request,
        trigger_kind=kind,
        observed_at=observed_at,
        actor_id=actor_id,
        evidence_expires_at=evidence_expires_at,
    )
    values: dict[str, object] = {
        "lifecycle_request_id": lifecycle_request_id,
        "evaluation_time": evaluation_time,
        "trigger": item,
        "expected_current_status": expected_status or entry.registry_status,
        "requested_status": requested_status,
        "registry_administrator_id": actor_id,
        "expected_entry_digest": entry.canonical_digest,
        "expected_restrictions": entry.restrictions,
        "safe_context": SAFE_CONTEXT,
    }
    values.update(overrides)
    return RegistryLifecycleRequest(**values)  # type: ignore[arg-type]


def apply(kind: RevalidationTriggerKind, target: RegistryStatus):
    admission_request, entry, store = context()
    request = lifecycle_request(
        admission_request,
        entry,
        kind=kind,
        requested_status=target,
    )
    result = enforce_registry_lifecycle(
        request,
        registry=store,
        admission_request=admission_request,
    )
    return admission_request, store, request, result


@pytest.mark.parametrize(
    ("kind", "target"),
    [
        (RevalidationTriggerKind.ADMINISTRATOR_SUSPENSION, RegistryStatus.SUSPENDED),
        (RevalidationTriggerKind.ADMINISTRATOR_DEPRECATION, RegistryStatus.DEPRECATED),
        (RevalidationTriggerKind.ADMINISTRATOR_REVOCATION, RegistryStatus.REVOKED),
    ],
)
def test_valid_active_transitions(kind, target) -> None:
    _, store, _, result = apply(kind, target)
    assert result.applied is True
    assert result.previous_status is RegistryStatus.ACTIVE
    assert result.resulting_status is target
    assert store.mutation_count == 1
    assert store.write_count == 1
    assert len(store.events) == 1
    assert store.transport_count == 0
    assert store.http_count == 0


@pytest.mark.parametrize(
    ("first_kind", "first_status", "second_kind", "second_status"),
    [
        (RevalidationTriggerKind.ADMINISTRATOR_SUSPENSION, RegistryStatus.SUSPENDED, RevalidationTriggerKind.ADMINISTRATOR_DEPRECATION, RegistryStatus.DEPRECATED),
        (RevalidationTriggerKind.ADMINISTRATOR_SUSPENSION, RegistryStatus.SUSPENDED, RevalidationTriggerKind.ADMINISTRATOR_REVOCATION, RegistryStatus.REVOKED),
        (RevalidationTriggerKind.ADMINISTRATOR_DEPRECATION, RegistryStatus.DEPRECATED, RevalidationTriggerKind.ADMINISTRATOR_REVOCATION, RegistryStatus.REVOKED),
    ],
)
def test_valid_non_active_forward_transitions(
    first_kind,
    first_status,
    second_kind,
    second_status,
) -> None:
    admission_request, original, store = context()
    first = lifecycle_request(
        admission_request,
        original,
        kind=first_kind,
        requested_status=first_status,
    )
    first_result = enforce_registry_lifecycle(
        first,
        registry=store,
        admission_request=admission_request,
    )
    assert first_result.applied is True
    current = store.resolve_status_exact(
        profile_id=original.profile_id,
        profile_version=original.profile_version,
        product_id=original.product_id,
        product_version=original.product_version,
        protocol_version=original.protocol_version,
    )
    second = lifecycle_request(
        admission_request,
        current,
        kind=second_kind,
        requested_status=second_status,
        lifecycle_request_id="lifecycle-request-002",
        evaluation_time=TRIGGER_TIME + timedelta(microseconds=1),
    )
    second_result = enforce_registry_lifecycle(
        second,
        registry=store,
        admission_request=admission_request,
    )
    assert second_result.applied is True
    assert second_result.previous_status is first_status
    assert second_result.resulting_status is second_status
    assert store.mutation_count == 2
    assert store.write_count == 2
    assert len(store.events) == 2


def test_active_requested_status_is_rejected_at_contract_boundary() -> None:
    admission_request, entry, store = context()
    with pytest.raises(RegistryLifecycleError) as raised:
        lifecycle_request(
            admission_request,
            entry,
            requested_status=RegistryStatus.ACTIVE,
        )
    assert raised.value.category is RegistryLifecycleReason.TRANSITION_FORBIDDEN
    assert store.mutation_count == 0


def test_same_status_write_is_rejected() -> None:
    admission_request, original, store = context()
    first = lifecycle_request(admission_request, original)
    assert enforce_registry_lifecycle(first, registry=store, admission_request=admission_request).applied
    current = store.resolve_status_exact(
        profile_id=original.profile_id,
        profile_version=original.profile_version,
        product_id=original.product_id,
        product_version=original.product_version,
        protocol_version=original.protocol_version,
    )
    second = lifecycle_request(
        admission_request,
        current,
        requested_status=RegistryStatus.SUSPENDED,
        lifecycle_request_id="lifecycle-request-002",
        evaluation_time=TRIGGER_TIME + timedelta(microseconds=1),
    )
    result = enforce_registry_lifecycle(second, registry=store, admission_request=admission_request)
    assert result.applied is False
    assert RegistryLifecycleReason.TRANSITION_FORBIDDEN in result.reason_categories
    assert store.mutation_count == 1


def test_deprecated_to_suspended_is_rejected() -> None:
    admission_request, original, store = context()
    first = lifecycle_request(
        admission_request,
        original,
        kind=RevalidationTriggerKind.ADMINISTRATOR_DEPRECATION,
        requested_status=RegistryStatus.DEPRECATED,
    )
    assert enforce_registry_lifecycle(first, registry=store, admission_request=admission_request).applied
    current = store.resolve_status_exact(
        profile_id=original.profile_id,
        profile_version=original.profile_version,
        product_id=original.product_id,
        product_version=original.product_version,
        protocol_version=original.protocol_version,
    )
    second = lifecycle_request(
        admission_request,
        current,
        requested_status=RegistryStatus.SUSPENDED,
        lifecycle_request_id="lifecycle-request-002",
        evaluation_time=TRIGGER_TIME + timedelta(microseconds=1),
    )
    result = enforce_registry_lifecycle(second, registry=store, admission_request=admission_request)
    assert result.applied is False
    assert RegistryLifecycleReason.TRANSITION_FORBIDDEN in result.reason_categories


@pytest.mark.parametrize("target", [RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED, RegistryStatus.REVOKED])
def test_revoked_is_terminal(target: RegistryStatus) -> None:
    admission_request, original, store = context()
    first = lifecycle_request(
        admission_request,
        original,
        kind=RevalidationTriggerKind.ADMINISTRATOR_REVOCATION,
        requested_status=RegistryStatus.REVOKED,
    )
    assert enforce_registry_lifecycle(first, registry=store, admission_request=admission_request).applied
    current = store.resolve_status_exact(
        profile_id=original.profile_id,
        profile_version=original.profile_version,
        product_id=original.product_id,
        product_version=original.product_version,
        protocol_version=original.protocol_version,
    )
    second_kind = {
        RegistryStatus.SUSPENDED: RevalidationTriggerKind.ADMINISTRATOR_SUSPENSION,
        RegistryStatus.DEPRECATED: RevalidationTriggerKind.ADMINISTRATOR_DEPRECATION,
        RegistryStatus.REVOKED: RevalidationTriggerKind.ADMINISTRATOR_REVOCATION,
    }[target]
    second = lifecycle_request(
        admission_request,
        current,
        kind=second_kind,
        requested_status=target,
        lifecycle_request_id="lifecycle-request-002",
        evaluation_time=TRIGGER_TIME + timedelta(microseconds=1),
    )
    result = enforce_registry_lifecycle(second, registry=store, admission_request=admission_request)
    assert result.applied is False
    assert RegistryLifecycleReason.ALREADY_TERMINAL in result.reason_categories
    assert store.mutation_count == 1


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"expected_current_status": RegistryStatus.DEPRECATED}, RegistryLifecycleReason.STATUS_MISMATCH),
        ({"expected_entry_digest": "sha256:" + "0" * 64}, RegistryLifecycleReason.DIGEST_MISMATCH),
        ({"registry_administrator_id": "other-admin"}, RegistryLifecycleReason.IDENTITY_MISMATCH),
        ({"registry_administrator_id": "approver-001"}, RegistryLifecycleReason.ROLE_CONFLICT),
    ],
)
def test_denied_bindings_leave_no_lifecycle_side_effects(override, reason) -> None:
    admission_request, entry, store = context()
    request = lifecycle_request(admission_request, entry, **override)
    before = store.resolve_status_exact(
        profile_id=entry.profile_id,
        profile_version=entry.profile_version,
        product_id=entry.product_id,
        product_version=entry.product_version,
        protocol_version=entry.protocol_version,
    )
    result = enforce_registry_lifecycle(request, registry=store, admission_request=admission_request)
    after = store.resolve_status_exact(
        profile_id=entry.profile_id,
        profile_version=entry.profile_version,
        product_id=entry.product_id,
        product_version=entry.product_version,
        protocol_version=entry.protocol_version,
    )
    assert result.applied is False
    assert reason in result.reason_categories
    assert before == after
    assert store.mutation_count == store.write_count == 0
    assert store.events == ()
    assert store.transport_count == store.http_count == 0


def test_commit_failure_is_atomic() -> None:
    admission_request, entry, store = context(fail_commit=True)
    request = lifecycle_request(admission_request, entry)
    result = enforce_registry_lifecycle(request, registry=store, admission_request=admission_request)
    assert result.applied is False
    assert result.reason_categories == (RegistryLifecycleReason.REGISTRY_COMMIT_FAILED,)
    assert store.mutation_count == store.write_count == 0
    assert store.events == ()
    current = store.resolve_status_exact(
        profile_id=entry.profile_id,
        profile_version=entry.profile_version,
        product_id=entry.product_id,
        product_version=entry.product_version,
        protocol_version=entry.protocol_version,
    )
    assert current.registry_status is RegistryStatus.ACTIVE


def test_production_registry_mutation_is_rejected() -> None:
    admission_request, entry, lifecycle_store = context()
    request = lifecycle_request(admission_request, entry)
    production_registry = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    result = enforce_registry_lifecycle(
        request,
        registry=production_registry,
        admission_request=admission_request,
    )
    assert result.applied is False
    assert RegistryLifecycleReason.REGISTRY_WRITE_REJECTED in result.reason_categories
    assert lifecycle_store.mutation_count == lifecycle_store.write_count == 0


@pytest.mark.parametrize("flag", ["fallback", "nearest_version", "infer_schema"])
def test_non_exact_resolution_is_rejected(flag: str) -> None:
    _, entry, store = context()
    kwargs = {flag: True}
    with pytest.raises(RegistryLifecycleError) as raised:
        store.resolve_status_exact(
            profile_id=entry.profile_id,
            profile_version=entry.profile_version,
            product_id=entry.product_id,
            product_version=entry.product_version,
            protocol_version=entry.protocol_version,
            **kwargs,
        )
    assert raised.value.category is RegistryLifecycleReason.SECURITY_BOUNDARY_VIOLATION


def test_lifecycle_contracts_are_immutable_and_deterministic() -> None:
    admission_request, entry, store = context()
    request = lifecycle_request(admission_request, entry)
    with pytest.raises(FrozenInstanceError):
        request.registry_administrator_id = "other"  # type: ignore[misc]
    result = enforce_registry_lifecycle(request, registry=store, admission_request=admission_request)
    assert result.applied is True
    assert result.digest_algorithm == CANONICAL_REGISTRY_LIFECYCLE_DIGEST_ALGORITHM
    assert repr(request) == "RegistryLifecycleRequest(<safe>)"
    assert repr(result) == "RegistryLifecycleResult(<safe>)"


def test_request_digest_preserves_microseconds_and_normalizes_offsets() -> None:
    admission_request, entry, _ = context()
    first = lifecycle_request(admission_request, entry)
    equivalent = replace(
        first,
        evaluation_time=first.evaluation_time.astimezone(
            first.evaluation_time.tzinfo
        ),
    )
    distinct = replace(
        first,
        evaluation_time=first.evaluation_time + timedelta(microseconds=1),
    )
    assert first.canonical_digest == equivalent.canonical_digest
    assert first.canonical_digest != distinct.canonical_digest


def test_module_has_no_io_clock_random_transport_or_persistence_imports() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint(
        {"os", "pathlib", "random", "socket", "sqlite3", "subprocess", "time", "urllib", "uuid"}
    )
