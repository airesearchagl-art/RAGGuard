from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import ragguard
from ragguard.manual_validation_evidence import ManualValidationEvidence
from ragguard.manual_validation_plan import (
    REQUIRED_MANUAL_VALIDATION_CASES,
    ManualValidationPlan,
)
from ragguard.production_admission import (
    ProductionAdmissionRequest,
    ReviewerAttestation,
    ReviewerAttestationOutcome,
    evaluate_production_admission,
)
from ragguard.production_registry import RegistryStatus
from ragguard.replacement_admission import (
    CANONICAL_REPLACEMENT_ADMISSION_DIGEST_ALGORITHM,
    ReplacementAdmissionError,
    ReplacementAdmissionReason,
    ReplacementAdmissionRequest,
    ReplacementDecisionStatus,
    ReplacementReason,
    TestReplacementAdmissionStore,
    evaluate_replacement_admission,
)
from ragguard.registry_admission import (
    TestRegistryAdmissionStore,
    enforce_registry_admission,
)
from ragguard.registry_lifecycle import (
    TestRegistryLifecycleStore,
    enforce_registry_lifecycle,
)
from test_production_admission_evaluator import (
    approval_metadata,
    attestation,
    evidence_data,
    plan_data,
    request as production_request_factory,
    validation_metadata,
)
from test_registry_admission_enforcement import request as admission_request_factory
from test_registry_lifecycle_governance import lifecycle_request


MODULE = Path(__file__).parents[1] / "src" / "ragguard" / "replacement_admission.py"
FRESH_COMPLETION = datetime(2026, 7, 29, 2, 0, 0, 234567, tzinfo=timezone.utc)
FRESH_REVIEW = FRESH_COMPLETION + timedelta(minutes=30)
FRESH_APPROVAL = FRESH_REVIEW + timedelta(minutes=15)
FRESH_DECISION = FRESH_APPROVAL + timedelta(minutes=15)
REPLACEMENT_TIME = FRESH_DECISION + timedelta(minutes=30)
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


def fresh_production_request(
    *,
    plan_overrides: dict[str, object] | None = None,
    evidence_overrides: dict[str, object] | None = None,
    attestation_overrides: dict[str, object] | None = None,
    approval_overrides: dict[str, object] | None = None,
    request_overrides: dict[str, object] | None = None,
) -> ProductionAdmissionRequest:
    plan_values: dict[str, object] = {
        "plan_id": "manual-plan-002",
        "created_at": "2026-07-28T00:00:00.123456Z",
        "execution_window_start": "2026-07-29T00:00:00.123456Z",
        "execution_window_end": "2026-07-30T00:00:00.123456Z",
    }
    plan_values.update(plan_overrides or {})
    plan = ManualValidationPlan.from_mapping(plan_data(**plan_values))
    case_results = [
        {
            "case_id": item.value,
            "outcome": "passed",
            "executed_at": "2026-07-29T01:30:00.123456Z",
            "safe_observation": "case_passed",
            "failure_category": None,
            "cleanup_confirmed": True,
        }
        for item in REQUIRED_MANUAL_VALIDATION_CASES
    ]
    evidence_values: dict[str, object] = {
        "evidence_id": "manual-evidence-b2c3d4e5",
        "execution_started_at": "2026-07-29T01:00:00.123456Z",
        "execution_completed_at": "2026-07-29T02:00:00.234567Z",
        "expires_at": "2026-08-28T02:00:00.234567Z",
        "case_results": case_results,
        "environment_fingerprint": {
            "environment_id": "environment-ref-1a2b3c4e",
            "os_family": "windows",
            "architecture": "x86_64",
            "python_version": "3.12.13",
            "ragguard_version": "0.13.0",
            "adapter_id": "adapter-fixture-fresh",
            "profile_id": plan.profile_id,
        },
        "tool_version": "0.13.0",
    }
    evidence_values.update(evidence_overrides or {})
    evidence = ManualValidationEvidence.from_mapping(
        evidence_data(plan, **evidence_values), plan=plan
    )
    attestation_values: dict[str, object] = {
        "attestation_id": "attestation-002",
        "reviewed_at": FRESH_REVIEW,
    }
    attestation_values.update(attestation_overrides or {})
    reviewed = attestation(plan, evidence, **attestation_values)
    approval_values: dict[str, object] = {
        "approval_record_id": "approval-002",
        "validation_record_id": "validation-002",
        "approved_at": "2026-07-29T02:45:00.234567Z",
    }
    approval_values.update(approval_overrides or {})
    approved = approval_metadata(**approval_values)
    request_values: dict[str, object] = {
        "request_id": "admission-request-002",
        "evaluation_time": FRESH_DECISION,
        "manual_validation_plan": plan,
        "manual_validation_evidence": evidence,
        "synthetic_validation_reference": plan.synthetic_evidence_reference,
        "profile_approval_metadata": approved,
        "profile_validation_metadata": validation_metadata(
            validation_record_id="validation-002",
            validated_at="2026-07-28T12:00:00.123456Z",
        ),
        "reviewer_attestation": reviewed,
        "approver_identity": plan.approver_id,
        "requested_restrictions": approved.restrictions,
        "validation_expires_at": datetime(
            2026, 9, 1, tzinfo=timezone.utc
        ),
    }
    request_values.update(request_overrides or {})
    return production_request_factory(**request_values)


def replacement_context(
    *, predecessor_status: RegistryStatus = RegistryStatus.SUSPENDED
):
    original_chain_request = production_request_factory()
    original_request = admission_request_factory(
        production_admission_decision=evaluate_production_admission(
            original_chain_request
        )
    )
    admission_store = TestRegistryAdmissionStore()
    original_result = enforce_registry_admission(
        original_request, registry=admission_store
    )
    assert original_result.entry is not None
    lifecycle_store = TestRegistryLifecycleStore(admission_store)
    kind = {
        RegistryStatus.SUSPENDED: "administrator_suspension",
        RegistryStatus.DEPRECATED: "administrator_deprecation",
        RegistryStatus.REVOKED: "administrator_revocation",
    }[predecessor_status]
    from ragguard.revalidation import RevalidationTriggerKind

    lifecycle = lifecycle_request(
        original_request,
        original_result.entry,
        kind=RevalidationTriggerKind(kind),
        requested_status=predecessor_status,
    )
    lifecycle_result = enforce_registry_lifecycle(
        lifecycle,
        registry=lifecycle_store,
        admission_request=original_request,
    )
    assert lifecycle_result.applied is True
    predecessor = lifecycle_store.resolve_status_exact(
        profile_id=original_result.entry.profile_id,
        profile_version=original_result.entry.profile_version,
        product_id=original_result.entry.product_id,
        product_version=original_result.entry.product_version,
        protocol_version=original_result.entry.protocol_version,
    )
    replacement_store = TestReplacementAdmissionStore(
        admission_store, lifecycle_store
    )
    return (
        original_request,
        admission_store,
        lifecycle_store,
        predecessor,
        replacement_store,
        original_chain_request,
    )


def replacement_request(
    *,
    predecessor_status: RegistryStatus = RegistryStatus.SUSPENDED,
    fresh_request: ProductionAdmissionRequest | None = None,
    request_overrides: dict[str, object] | None = None,
    existing_context=None,
):
    context = existing_context or replacement_context(
        predecessor_status=predecessor_status
    )
    predecessor = context[3]
    lifecycle_store = context[2]
    new_request = fresh_request or fresh_production_request()
    decision = evaluate_production_admission(new_request)
    assert new_request.reviewer_attestation is not None
    values: dict[str, object] = {
        "replacement_request_id": "replacement-request-001",
        "replacement_entry_id": "replacement-entry-001",
        "evaluation_time": REPLACEMENT_TIME,
        "old_registry_entry_digest": predecessor.canonical_digest,
        "old_profile_id": predecessor.profile_id,
        "old_profile_version": predecessor.profile_version,
        "old_product_id": predecessor.product_id,
        "old_product_version": predecessor.product_version,
        "old_protocol_version": predecessor.protocol_version,
        "expected_old_status": predecessor.registry_status,
        "predecessor_production_admission_request": context[5],
        "new_admission_decision": decision,
        "new_production_admission_request": new_request,
        "predecessor_lifecycle_event": lifecycle_store.events[-1],
        "new_plan_digest": new_request.manual_validation_plan.canonical_digest,
        "new_evidence_digest": (
            new_request.manual_validation_evidence.canonical_digest
        ),
        "new_attestation_digest": (
            new_request.reviewer_attestation.canonical_digest
        ),
        "new_admission_decision_digest": decision.canonical_digest,
        "registry_administrator_id": "replacement-admin-001",
        "replacement_reason": ReplacementReason.EVIDENCE_REFRESHED,
        "safe_context": SAFE_CONTEXT,
    }
    values.update(request_overrides or {})
    return context, ReplacementAdmissionRequest(**values)  # type: ignore[arg-type]


def test_public_api_exports_v013_contracts() -> None:
    expected = {
        "CANONICAL_REPLACEMENT_ADMISSION_DIGEST_ALGORITHM",
        "ReplacementAdmissionDecision",
        "ReplacementAdmissionError",
        "ReplacementAdmissionEvent",
        "ReplacementAdmissionReason",
        "ReplacementAdmissionRequest",
        "ReplacementAdmissionResult",
        "ReplacementCommitFault",
        "ReplacementDecisionStatus",
        "ReplacementReason",
        "ReplacementRegistryEntry",
        "TestReplacementAdmissionStore",
        "enforce_replacement_admission",
        "evaluate_replacement_admission",
    }
    assert expected.issubset(set(ragguard.__all__))
    assert all(hasattr(ragguard, name) for name in expected)


def test_valid_fresh_chain_is_eligible() -> None:
    context, request = replacement_request()
    decision = evaluate_replacement_admission(
        request, predecessor_entry=context[3]
    )
    assert decision.decision is ReplacementDecisionStatus.ELIGIBLE
    assert decision.reason_categories == ()
    assert decision.predecessor_status is RegistryStatus.SUSPENDED
    assert decision.successor_entry_id == "replacement-entry-001"


@pytest.mark.parametrize(
    "status", [RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED]
)
def test_only_suspended_and_deprecated_are_eligible(status) -> None:
    context, request = replacement_request(predecessor_status=status)
    decision = evaluate_replacement_admission(
        request, predecessor_entry=context[3]
    )
    assert decision.decision is ReplacementDecisionStatus.ELIGIBLE


@pytest.mark.parametrize("status", [RegistryStatus.ACTIVE, RegistryStatus.REVOKED])
def test_active_and_revoked_predecessors_are_rejected(status) -> None:
    if status is RegistryStatus.ACTIVE:
        context, request = replacement_request()
        predecessor = replace(context[3], registry_status=status)
        request = replace(
            request,
            old_registry_entry_digest=predecessor.canonical_digest,
            expected_old_status=status,
        )
    else:
        context, request = replacement_request(predecessor_status=status)
        predecessor = context[3]
    decision = evaluate_replacement_admission(
        request, predecessor_entry=predecessor
    )
    assert decision.decision is ReplacementDecisionStatus.REJECTED
    assert (
        ReplacementAdmissionReason.PREDECESSOR_STATUS_INELIGIBLE
        in decision.reason_categories
    )


@pytest.mark.parametrize(
    ("field", "old_field"),
    [
        ("new_plan_digest", "plan_digest"),
        ("new_evidence_digest", "evidence_digest"),
        ("new_attestation_digest", "reviewer_attestation_digest"),
        ("new_admission_decision_digest", "admission_decision_digest"),
    ],
)
def test_old_chain_digest_reuse_is_rejected(field, old_field) -> None:
    context, request = replacement_request()
    reused = getattr(context[3], old_field)
    decision = evaluate_replacement_admission(
        replace(request, **{field: reused}),
        predecessor_entry=context[3],
    )
    assert decision.decision is ReplacementDecisionStatus.REJECTED
    assert ReplacementAdmissionReason.CHAIN_REUSE in decision.reason_categories


def test_old_approval_metadata_reuse_is_rejected() -> None:
    context = replacement_context()
    old_approval = context[5].profile_approval_metadata
    fresh = fresh_production_request(
        request_overrides={
            "profile_approval_metadata": old_approval,
            "approver_identity": old_approval.approver_id,
            "requested_restrictions": old_approval.restrictions,
        }
    )
    context, request = replacement_request(
        fresh_request=fresh, existing_context=context
    )
    decision = evaluate_replacement_admission(
        request, predecessor_entry=context[3]
    )
    assert ReplacementAdmissionReason.CHAIN_REUSE in decision.reason_categories


def test_expired_fresh_evidence_needs_revalidation() -> None:
    context, request = replacement_request()
    expired = replace(
        request,
        evaluation_time=(
            request.new_production_admission_request.manual_validation_evidence.expires_at
        ),
    )
    decision = evaluate_replacement_admission(
        expired, predecessor_entry=context[3]
    )
    assert decision.decision is ReplacementDecisionStatus.NEEDS_REVALIDATION
    assert ReplacementAdmissionReason.EVIDENCE_EXPIRED in decision.reason_categories


def test_role_conflict_is_rejected() -> None:
    context, request = replacement_request()
    conflict = replace(
        request,
        registry_administrator_id=(
            request.new_admission_decision.evidence_reviewer_id
        ),
    )
    decision = evaluate_replacement_admission(
        conflict, predecessor_entry=context[3]
    )
    assert ReplacementAdmissionReason.ROLE_CONFLICT in decision.reason_categories


def test_restriction_change_requires_explicit_reason() -> None:
    from ragguard.profile_approval import ApprovalRestrictions

    restrictions = ApprovalRestrictions(maximum_top_k=5)
    fresh = fresh_production_request(
        approval_overrides={
            "decision": "approved_with_restrictions",
            "restrictions": {"maximum_top_k": 5},
        },
        request_overrides={"requested_restrictions": restrictions},
    )
    context, request = replacement_request(fresh_request=fresh)
    denied = evaluate_replacement_admission(
        request, predecessor_entry=context[3]
    )
    assert ReplacementAdmissionReason.RESTRICTION_MISMATCH in denied.reason_categories
    allowed = evaluate_replacement_admission(
        replace(
            request,
            replacement_reason=ReplacementReason.RESTRICTION_REVALIDATED,
        ),
        predecessor_entry=context[3],
    )
    assert allowed.decision is ReplacementDecisionStatus.ELIGIBLE


def test_request_digest_is_deterministic_and_preserves_microseconds() -> None:
    _, request = replacement_request()
    same = replace(request)
    changed = replace(
        request, evaluation_time=request.evaluation_time + timedelta(microseconds=1)
    )
    offset = replace(
        request,
        evaluation_time=request.evaluation_time.astimezone(
            timezone(timedelta(hours=9))
        ),
    )
    assert request.canonical_digest == same.canonical_digest
    assert request.canonical_digest == offset.canonical_digest
    assert request.canonical_digest != changed.canonical_digest
    assert ".234567Z" in request.canonical_json()


def test_contracts_are_immutable_and_errors_are_typed_safe() -> None:
    _, request = replacement_request()
    with pytest.raises(FrozenInstanceError):
        request.replacement_request_id = "changed"  # type: ignore[misc]
    with pytest.raises(ReplacementAdmissionError) as raised:
        replace(request, safe_context=("unsafe-secret-value",))
    assert raised.value.category is ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION
    assert "unsafe-secret-value" not in str(raised.value)
    assert "unsafe-secret-value" not in repr(raised.value)


def test_module_has_no_io_clock_random_uuid_transport_or_subprocess_imports() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    forbidden = {
        "os",
        "pathlib",
        "random",
        "socket",
        "subprocess",
        "time",
        "urllib",
        "uuid",
    }
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports.isdisjoint(forbidden)
    source = MODULE.read_text(encoding="utf-8")
    assert "datetime.now" not in source
    assert "utcnow" not in source
    assert CANONICAL_REPLACEMENT_ADMISSION_DIGEST_ALGORITHM == "sha256"
