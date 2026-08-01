from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ragguard.production_registry import RegistryStatus
from ragguard.registry_admission import (
    RegistryAdmissionEntry,
    RegistryAdmissionRequest,
    TestRegistryAdmissionStore,
    enforce_registry_admission,
)
from ragguard.revalidation import (
    CANONICAL_REVALIDATION_DIGEST_ALGORITHM,
    RevalidationAction,
    RevalidationError,
    RevalidationReason,
    RevalidationRequirement,
    RevalidationTrigger,
    RevalidationTriggerKind,
    evaluate_revalidation_requirement,
)
from test_registry_admission_enforcement import (
    EVALUATION_TIME,
    request as admission_request_factory,
)


MODULE = Path(__file__).parents[1] / "src" / "ragguard" / "revalidation.py"
TRIGGER_TIME = EVALUATION_TIME + timedelta(days=1, microseconds=123456)
SAFE_CONTEXT = (
    "no_credentials",
    "no_network",
    "no_persistence",
    "no_production_registry_write",
    "no_real_documents",
    "no_transport",
    "synthetic_only",
    "test_registry_only",
)


def admitted() -> tuple[
    TestRegistryAdmissionStore,
    RegistryAdmissionRequest,
    RegistryAdmissionEntry,
]:
    admission_request = admission_request_factory()
    registry = TestRegistryAdmissionStore()
    result = enforce_registry_admission(admission_request, registry=registry)
    assert result.admitted is True
    assert result.entry is not None
    return registry, admission_request, result.entry


def trigger(
    entry: RegistryAdmissionEntry,
    admission_request: RegistryAdmissionRequest,
    **overrides: object,
) -> RevalidationTrigger:
    values: dict[str, object] = {
        "trigger_id": "revalidation-trigger-001",
        "trigger_kind": RevalidationTriggerKind.ADMINISTRATOR_SUSPENSION,
        "observed_at": TRIGGER_TIME,
        "profile_id": entry.profile_id,
        "profile_version": entry.profile_version,
        "protocol_version": entry.protocol_version,
        "product_id": entry.product_id,
        "product_version": entry.product_version,
        "registry_entry_digest": entry.canonical_digest,
        "admission_decision_digest": entry.admission_decision_digest,
        "evidence_digest": entry.evidence_digest,
        "actor_id": "lifecycle-admin-001",
        "safe_context": SAFE_CONTEXT,
        "evidence_expires_at": None,
    }
    values.update(overrides)
    return RevalidationTrigger(**values)  # type: ignore[arg-type]


def requirement(
    kind: RevalidationTriggerKind,
    *,
    evaluation_time: datetime | None = None,
) -> RevalidationRequirement:
    _, admission_request, entry = admitted()
    evidence_expires_at = (
        admission_request.evidence_expires_at
        if kind is RevalidationTriggerKind.EVIDENCE_EXPIRED
        else None
    )
    observed_at = evidence_expires_at or TRIGGER_TIME
    item = trigger(
        entry,
        admission_request,
        trigger_kind=kind,
        observed_at=observed_at,
        evidence_expires_at=evidence_expires_at,
    )
    return evaluate_revalidation_requirement(
        item,
        entry=entry,
        admission_request=admission_request,
        evaluation_time=evaluation_time or observed_at,
    )


def test_trigger_contract_is_immutable_and_typed() -> None:
    _, admission_request, entry = admitted()
    item = trigger(entry, admission_request)
    with pytest.raises(FrozenInstanceError):
        item.actor_id = "other"  # type: ignore[misc]
    assert item.digest_algorithm == CANONICAL_REVALIDATION_DIGEST_ALGORITHM
    assert repr(item) == "RevalidationTrigger(<safe>)"


def test_all_required_trigger_kinds_are_explicit() -> None:
    assert {kind.value for kind in RevalidationTriggerKind} == {
        "evidence_expired",
        "evidence_revoked",
        "approval_revoked",
        "security_policy_changed",
        "product_version_changed",
        "protocol_version_changed",
        "restriction_changed",
        "scheduled_revalidation",
        "administrator_suspension",
        "administrator_deprecation",
        "administrator_revocation",
    }


@pytest.mark.parametrize(
    ("kind", "action", "status", "required"),
    [
        (RevalidationTriggerKind.EVIDENCE_EXPIRED, RevalidationAction.SUSPEND, RegistryStatus.SUSPENDED, True),
        (RevalidationTriggerKind.EVIDENCE_REVOKED, RevalidationAction.SUSPEND, RegistryStatus.SUSPENDED, True),
        (RevalidationTriggerKind.APPROVAL_REVOKED, RevalidationAction.SUSPEND, RegistryStatus.SUSPENDED, True),
        (RevalidationTriggerKind.SECURITY_POLICY_CHANGED, RevalidationAction.REVOKE, RegistryStatus.REVOKED, False),
        (RevalidationTriggerKind.PRODUCT_VERSION_CHANGED, RevalidationAction.DEPRECATE, RegistryStatus.DEPRECATED, True),
        (RevalidationTriggerKind.PROTOCOL_VERSION_CHANGED, RevalidationAction.DEPRECATE, RegistryStatus.DEPRECATED, True),
        (RevalidationTriggerKind.RESTRICTION_CHANGED, RevalidationAction.DEPRECATE, RegistryStatus.DEPRECATED, True),
        (RevalidationTriggerKind.SCHEDULED_REVALIDATION, RevalidationAction.REVALIDATION_REQUIRED, None, True),
        (RevalidationTriggerKind.ADMINISTRATOR_SUSPENSION, RevalidationAction.SUSPEND, RegistryStatus.SUSPENDED, False),
        (RevalidationTriggerKind.ADMINISTRATOR_DEPRECATION, RevalidationAction.DEPRECATE, RegistryStatus.DEPRECATED, False),
        (RevalidationTriggerKind.ADMINISTRATOR_REVOCATION, RevalidationAction.REVOKE, RegistryStatus.REVOKED, False),
    ],
)
def test_deterministic_trigger_priority(
    kind: RevalidationTriggerKind,
    action: RevalidationAction,
    status: RegistryStatus | None,
    required: bool,
) -> None:
    result = requirement(kind)
    assert result.action is action
    assert result.target_status is status
    assert result.revalidation_required is required


def test_future_trigger_is_rejected_without_action() -> None:
    _, admission_request, entry = admitted()
    item = trigger(entry, admission_request)
    result = evaluate_revalidation_requirement(
        item,
        entry=entry,
        admission_request=admission_request,
        evaluation_time=TRIGGER_TIME - timedelta(microseconds=1),
    )
    assert result.action is RevalidationAction.NO_ACTION
    assert result.reason_categories == (RevalidationReason.TRIGGER_NOT_YET_VALID,)


def test_evidence_expiry_boundary_is_inclusive() -> None:
    result = requirement(RevalidationTriggerKind.EVIDENCE_EXPIRED)
    assert result.action is RevalidationAction.SUSPEND
    assert RevalidationReason.EVIDENCE_EXPIRED in result.reason_categories


def test_evidence_expiry_before_boundary_is_rejected() -> None:
    _, admission_request, entry = admitted()
    item = trigger(
        entry,
        admission_request,
        trigger_kind=RevalidationTriggerKind.EVIDENCE_EXPIRED,
        observed_at=admission_request.evidence_expires_at,
        evidence_expires_at=admission_request.evidence_expires_at,
    )
    result = evaluate_revalidation_requirement(
        item,
        entry=entry,
        admission_request=admission_request,
        evaluation_time=admission_request.evidence_expires_at - timedelta(microseconds=1),
    )
    assert RevalidationReason.TRIGGER_NOT_YET_VALID in result.reason_categories


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("profile_id", "other-profile", RevalidationReason.IDENTITY_MISMATCH),
        ("registry_entry_digest", "sha256:" + "0" * 64, RevalidationReason.DIGEST_MISMATCH),
        ("admission_decision_digest", "sha256:" + "1" * 64, RevalidationReason.DIGEST_MISMATCH),
        ("evidence_digest", "sha256:" + "2" * 64, RevalidationReason.DIGEST_MISMATCH),
    ],
)
def test_exact_identity_and_digest_binding(
    field_name: str,
    value: object,
    reason: RevalidationReason,
) -> None:
    _, admission_request, entry = admitted()
    item = trigger(entry, admission_request, **{field_name: value})
    result = evaluate_revalidation_requirement(
        item,
        entry=entry,
        admission_request=admission_request,
        evaluation_time=TRIGGER_TIME,
    )
    assert reason in result.reason_categories
    assert result.action is RevalidationAction.NO_ACTION


def test_equivalent_instants_have_identical_trigger_digest() -> None:
    _, admission_request, entry = admitted()
    utc_item = trigger(entry, admission_request)
    offset_item = trigger(
        entry,
        admission_request,
        observed_at=TRIGGER_TIME.astimezone(timezone(timedelta(hours=9))),
    )
    assert utc_item.canonical_digest == offset_item.canonical_digest


def test_one_microsecond_difference_changes_trigger_digest() -> None:
    _, admission_request, entry = admitted()
    first = trigger(entry, admission_request)
    second = trigger(
        entry,
        admission_request,
        observed_at=TRIGGER_TIME + timedelta(microseconds=1),
    )
    assert first.canonical_digest != second.canonical_digest


def test_field_change_changes_trigger_digest() -> None:
    _, admission_request, entry = admitted()
    first = trigger(entry, admission_request)
    second = replace(first, trigger_id="revalidation-trigger-002")
    assert first.canonical_digest != second.canonical_digest


def test_safe_summary_uses_canonical_values_only() -> None:
    _, admission_request, entry = admitted()
    item = trigger(entry, admission_request)
    text = repr(item.safe_summary)
    assert item.safe_summary.observed_at.endswith("Z")
    for forbidden in ("endpoint", "password", "token", "cookie", "stack trace"):
        assert forbidden not in text.lower()


@pytest.mark.parametrize(
    "overrides",
    [
        {"observed_at": datetime(2026, 1, 1)},
        {"safe_context": ("credentials",)},
        {"trigger_id": "https://invalid.example"},
        {"actor_id": "C:\\secret"},
    ],
)
def test_unsafe_or_untyped_trigger_is_rejected(overrides: dict[str, object]) -> None:
    _, admission_request, entry = admitted()
    with pytest.raises(RevalidationError) as raised:
        trigger(entry, admission_request, **overrides)
    assert str(raised.value) == raised.value.category.value


def test_module_has_no_hidden_clock_random_io_or_transport_imports() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint(
        {"os", "pathlib", "random", "socket", "subprocess", "time", "urllib", "uuid"}
    )
