from __future__ import annotations

import ast
import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import ragguard
from ragguard.compatibility import SemanticVersion
from ragguard.production_admission import (
    ProductionAdmissionDecision,
    ProductionAdmissionReason,
)
from ragguard.production_registry import (
    RegistryKind,
    RegistryStatus,
    TrustedProductionRegistry,
)
from ragguard.profile_approval import ApprovalDecision, ApprovalRestrictions
from ragguard.registry_admission import (
    CANONICAL_REGISTRY_ADMISSION_DIGEST_ALGORITHM,
    RegistryAdmissionEntry,
    RegistryAdmissionError,
    RegistryAdmissionReason,
    RegistryAdmissionRequest,
    RegistryAdmissionResult,
    TestRegistryAdmissionStore,
    enforce_registry_admission,
)


MODULE = Path(__file__).parents[1] / "src" / "ragguard" / "registry_admission.py"
EVALUATION_TIME = datetime(
    2026, 7, 27, 3, 30, 0, 456789, tzinfo=timezone.utc
)
DECISION_TIME = datetime(
    2026, 7, 27, 3, 0, 0, 345678, tzinfo=timezone.utc
)
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


def version(value: str) -> SemanticVersion:
    return SemanticVersion.parse(value)


def digest(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def decision(**overrides: object) -> ProductionAdmissionDecision:
    values: dict[str, object] = {
        "decision": ApprovalDecision.APPROVED,
        "eligible_for_registry_admission": True,
        "effective_restrictions": None,
        "reason_categories": (),
        "evaluated_at": DECISION_TIME,
        "plan_id": "manual-plan-001",
        "plan_digest": digest("plan"),
        "evidence_id": "manual-evidence-a1b2c3d4",
        "evidence_digest": digest("evidence"),
        "reviewer_attestation_id": "attestation-001",
        "reviewer_attestation_digest": digest("attestation"),
        "evidence_reviewer_id": "reviewer-001",
        "validation_operator_id": "operator-001",
        "approver_id": "approver-001",
        "approval_digest": digest("approval"),
        "requested_registry_kind": RegistryKind.PRODUCTION,
        "requested_initial_status": RegistryStatus.ACTIVE,
        "_request_id": "admission-request-001",
        "_profile_id": "synthetic-profile",
        "_profile_version": "1.2.3",
        "_protocol_version": "1.0.0",
        "_product_id": "product-fixture-alpha",
        "_product_version": "2.3.4",
    }
    values.update(overrides)
    return ProductionAdmissionDecision(**values)  # type: ignore[arg-type]


def request(**overrides: object) -> RegistryAdmissionRequest:
    admission_decision = overrides.pop(
        "production_admission_decision", decision()
    )
    assert isinstance(admission_decision, ProductionAdmissionDecision)
    values: dict[str, object] = {
        "admission_id": "registry-admission-001",
        "evaluation_time": EVALUATION_TIME,
        "production_admission_decision": admission_decision,
        "expected_profile_id": "synthetic-profile",
        "expected_profile_version": version("1.2.3"),
        "expected_protocol_version": version("1.0.0"),
        "expected_product_id": "product-fixture-alpha",
        "expected_product_version": version("2.3.4"),
        "requested_registry_kind": RegistryKind.PRODUCTION,
        "requested_initial_status": RegistryStatus.ACTIVE,
        "expected_restrictions": admission_decision.effective_restrictions,
        "registry_administrator_id": "registry-admin-001",
        "approver_id": "approver-001",
        "evidence_reviewer_id": "reviewer-001",
        "validation_operator_id": "operator-001",
        "evidence_expires_at": EVALUATION_TIME + timedelta(days=30),
        "validation_expires_at": EVALUATION_TIME + timedelta(days=31),
        "approval_expires_at": EVALUATION_TIME + timedelta(days=32),
        "safe_context": SAFE_CONTEXT,
    }
    values.update(overrides)
    return RegistryAdmissionRequest(**values)  # type: ignore[arg-type]


def admit(
    admission_request: RegistryAdmissionRequest | None = None,
) -> tuple[TestRegistryAdmissionStore, RegistryAdmissionResult]:
    registry = TestRegistryAdmissionStore()
    result = enforce_registry_admission(
        admission_request or request(),
        registry=registry,
    )
    return registry, result


def assert_denied(
    result: RegistryAdmissionResult,
    registry: TestRegistryAdmissionStore,
    reason: RegistryAdmissionReason,
) -> None:
    assert result.admitted is False
    assert reason in result.reason_categories
    assert result.entry is None
    assert result.entry_identity is None
    assert result.admitted_at is None
    assert registry.write_count == 0
    assert len(registry.snapshot) == 0
    assert registry.events == ()
    assert registry.transport_count == 0
    assert registry.http_count == 0


def test_valid_approved_admission_is_committed_exactly_once() -> None:
    registry, result = admit()

    assert result.admitted is True
    assert isinstance(result.entry, RegistryAdmissionEntry)
    assert result.reason_categories == ()
    assert result.entry_identity == "registry-admission-001"
    assert registry.write_count == 1
    assert len(registry.snapshot) == 1
    assert len(registry.events) == 1
    assert result.entry is not None
    assert result.entry.registry_kind is RegistryKind.PRODUCTION
    assert result.entry.registry_status is RegistryStatus.ACTIVE
    assert result.entry.plan_digest == digest("plan")
    assert result.entry.evidence_digest == digest("evidence")
    assert (
        result.entry.reviewer_attestation_digest
        == digest("attestation")
    )
    assert result.entry.admission_decision_digest == decision().canonical_digest
    assert result.entry.approval_digest == decision().approval_digest


def test_public_api_exports_phase_e_contracts() -> None:
    expected = {
        "CANONICAL_REGISTRY_ADMISSION_DIGEST_ALGORITHM",
        "RegistryAdmissionEntry",
        "RegistryAdmissionEntrySafeSummary",
        "RegistryAdmissionError",
        "RegistryAdmissionEvent",
        "RegistryAdmissionReason",
        "RegistryAdmissionRequest",
        "RegistryAdmissionRequestSafeSummary",
        "RegistryAdmissionResult",
        "RegistryAdmissionSafeSummary",
        "TestRegistryAdmissionStore",
        "enforce_registry_admission",
    }
    assert expected.issubset(set(ragguard.__all__))
    assert all(hasattr(ragguard, name) for name in expected)


def test_valid_approved_with_restrictions_admission() -> None:
    restrictions = ApprovalRestrictions(
        maximum_top_k=5,
        query_id_echo_required=True,
        supported_minor_versions=("2.3",),
        expires_at=EVALUATION_TIME + timedelta(days=10),
    )
    restricted_decision = decision(
        decision=ApprovalDecision.APPROVED_WITH_RESTRICTIONS,
        effective_restrictions=restrictions,
    )
    registry, result = admit(
        request(
            production_admission_decision=restricted_decision,
            expected_restrictions=restrictions,
        )
    )

    assert result.admitted is True
    assert result.effective_restrictions == restrictions
    assert result.safe_summary.restriction_count == 4
    assert registry.write_count == 1


@pytest.mark.parametrize(
    "admission_decision",
    [
        decision(
            decision=ApprovalDecision.REJECTED,
            eligible_for_registry_admission=False,
            reason_categories=(
                ProductionAdmissionReason.REVIEWER_REJECTED,
            ),
        ),
        decision(
            decision=ApprovalDecision.NEEDS_REVALIDATION,
            eligible_for_registry_admission=False,
            reason_categories=(
                ProductionAdmissionReason.REVALIDATION_REQUIRED,
            ),
        ),
        decision(eligible_for_registry_admission=False),
    ],
)
def test_ineligible_decision_is_rejected(
    admission_decision: ProductionAdmissionDecision,
) -> None:
    registry, result = admit(
        request(production_admission_decision=admission_decision)
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.DECISION_INELIGIBLE,
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("expected_profile_id", "other-profile"),
        ("expected_profile_version", version("1.2.4")),
        ("expected_protocol_version", version("1.0.1")),
        ("expected_product_id", "other-product"),
        ("expected_product_version", version("2.3.5")),
        ("approver_id", "other-approver"),
        ("evidence_reviewer_id", "other-reviewer"),
        ("validation_operator_id", "other-operator"),
    ],
)
def test_exact_identity_mismatch_is_rejected(
    field_name: str, value: object
) -> None:
    registry, result = admit(request(**{field_name: value}))
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.IDENTITY_MISMATCH,
    )


def test_decision_digest_tampering_is_rejected() -> None:
    admission_decision = decision()
    object.__setattr__(
        admission_decision,
        "canonical_digest",
        digest("tampered-decision"),
    )
    registry, result = admit(
        request(production_admission_decision=admission_decision)
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.DIGEST_MISMATCH,
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("evidence_reviewer_id", "reviewer-002"),
        ("validation_operator_id", "operator-002"),
    ],
)
def test_decision_role_identity_changes_canonical_digest(
    field_name: str,
    value: str,
) -> None:
    assert decision().canonical_digest != decision(
        **{field_name: value}
    ).canonical_digest


@pytest.mark.parametrize(
    "field_name",
    [
        "_profile_id",
        "_profile_version",
        "_protocol_version",
        "_product_id",
        "_product_version",
        "evidence_reviewer_id",
        "validation_operator_id",
    ],
)
def test_canonical_identity_tampering_is_digest_mismatch(
    field_name: str,
) -> None:
    admission_decision = decision()
    object.__setattr__(admission_decision, field_name, "tampered-identity")
    registry, result = admit(
        request(production_admission_decision=admission_decision)
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.DIGEST_MISMATCH,
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("profile_id", "tampered-profile"),
        ("product_id", "tampered-product"),
        ("evidence_reviewer_id", "tampered-reviewer"),
        ("validation_operator_id", "tampered-operator"),
        ("approver_id", "tampered-approver"),
    ],
)
def test_safe_summary_identity_tampering_is_rejected(
    field_name: str,
    value: str,
) -> None:
    admission_decision = decision()
    object.__setattr__(admission_decision.safe_summary, field_name, value)
    registry, result = admit(
        request(production_admission_decision=admission_decision)
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.IDENTITY_MISMATCH,
    )


def test_safe_summary_cannot_replace_canonical_reviewer_identity() -> None:
    admission_decision = decision()
    object.__setattr__(
        admission_decision.safe_summary,
        "evidence_reviewer_id",
        "request-only-reviewer",
    )
    registry, result = admit(
        request(
            production_admission_decision=admission_decision,
            evidence_reviewer_id="request-only-reviewer",
        )
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.IDENTITY_MISMATCH,
    )


@pytest.mark.parametrize(
    "digest_field",
    [
        "plan_digest",
        "evidence_digest",
        "reviewer_attestation_digest",
    ],
)
def test_digest_chain_tampering_is_rejected(digest_field: str) -> None:
    admission_decision = decision()
    object.__setattr__(admission_decision, digest_field, "not-a-digest")
    registry, result = admit(
        request(production_admission_decision=admission_decision)
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.DIGEST_MISMATCH,
    )


def test_future_decision_is_rejected() -> None:
    future = decision(evaluated_at=EVALUATION_TIME + timedelta(microseconds=1))
    registry, result = admit(
        request(production_admission_decision=future)
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.DECISION_NOT_YET_VALID,
    )


@pytest.mark.parametrize(
    "expiry_field",
    [
        "evidence_expires_at",
        "validation_expires_at",
        "approval_expires_at",
    ],
)
def test_expiry_boundary_is_exclusive(expiry_field: str) -> None:
    registry, result = admit(
        request(**{expiry_field: EVALUATION_TIME})
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.DECISION_EXPIRED,
    )


def test_equivalent_offset_instant_has_same_request_digest() -> None:
    offset = timezone(timedelta(hours=9))
    equivalent = EVALUATION_TIME.astimezone(offset)
    assert request().canonical_digest == request(
        evaluation_time=equivalent
    ).canonical_digest


def test_microsecond_difference_changes_request_digest() -> None:
    assert request().canonical_digest != request(
        evaluation_time=EVALUATION_TIME + timedelta(microseconds=1)
    ).canonical_digest


@pytest.mark.parametrize(
    "administrator_id",
    [
        "approver-001",
        "reviewer-001",
        "operator-001",
    ],
)
def test_registry_administrator_role_conflict_is_rejected(
    administrator_id: str,
) -> None:
    registry, result = admit(
        request(registry_administrator_id=administrator_id)
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.ROLE_CONFLICT,
    )


def test_exact_decision_bound_reviewer_and_operator_are_admitted() -> None:
    registry, result = admit(
        request(
            evidence_reviewer_id="reviewer-001",
            validation_operator_id="operator-001",
        )
    )
    assert result.admitted is True
    assert registry.write_count == 1
    assert len(registry.snapshot) == 1
    assert len(registry.events) == 1
    assert registry.transport_count == 0
    assert registry.http_count == 0


def test_empty_role_identifier_is_rejected_safely() -> None:
    with pytest.raises(RegistryAdmissionError) as caught:
        request(registry_administrator_id="")
    assert caught.value.category is (
        RegistryAdmissionReason.SECURITY_BOUNDARY_VIOLATION
    )
    assert str(caught.value) == "security_boundary_violation"


def test_invalid_registry_kind_and_initial_status_are_rejected() -> None:
    with pytest.raises(RegistryAdmissionError) as kind_error:
        request(requested_registry_kind=RegistryKind.TEST)
    assert kind_error.value.category is (
        RegistryAdmissionReason.REGISTRY_KIND_INVALID
    )
    with pytest.raises(RegistryAdmissionError) as status_error:
        request(requested_initial_status=RegistryStatus.SUSPENDED)
    assert status_error.value.category is (
        RegistryAdmissionReason.INITIAL_STATUS_INVALID
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("requested_registry_kind", "production"),
        ("requested_initial_status", "active"),
        ("expected_restrictions", {"unknown_restriction": True}),
    ],
)
def test_untyped_or_unknown_admission_values_are_rejected(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(RegistryAdmissionError) as caught:
        request(**{field_name: value})
    assert caught.value.category is (
        RegistryAdmissionReason.SECURITY_BOUNDARY_VIOLATION
    )


def test_restriction_mismatch_is_rejected() -> None:
    admission_decision = decision()
    registry, result = admit(
        request(
            production_admission_decision=admission_decision,
            expected_restrictions=ApprovalRestrictions(maximum_top_k=4),
        )
    )
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.RESTRICTION_MISMATCH,
    )


def test_duplicate_exact_entry_does_not_overwrite() -> None:
    registry = TestRegistryAdmissionStore()
    first = enforce_registry_admission(request(), registry=registry)
    before = registry.snapshot
    second = enforce_registry_admission(
        request(admission_id="registry-admission-002"),
        registry=registry,
    )

    assert first.admitted is True
    assert second.admitted is False
    assert second.reason_categories == (
        RegistryAdmissionReason.DUPLICATE_ENTRY,
    )
    assert registry.write_count == 1
    assert registry.snapshot == before
    assert len(registry.events) == 1


@pytest.mark.parametrize(
    "status",
    [
        RegistryStatus.SUSPENDED,
        RegistryStatus.DEPRECATED,
        RegistryStatus.REVOKED,
    ],
)
def test_non_active_identity_cannot_be_readmitted(
    status: RegistryStatus,
) -> None:
    registry, first = admit()
    assert first.admitted is True
    registry.transition_status(
        profile_id="synthetic-profile",
        profile_version=version("1.2.3"),
        target=status,
    )
    before = registry.snapshot
    second = enforce_registry_admission(
        request(admission_id="registry-admission-002"),
        registry=registry,
    )
    assert second.admitted is False
    assert second.reason_categories == (
        RegistryAdmissionReason.STATUS_INELIGIBLE,
    )
    assert registry.write_count == 1
    assert registry.snapshot == before


def test_production_registry_instance_write_is_rejected() -> None:
    production_registry = TrustedProductionRegistry(
        kind=RegistryKind.PRODUCTION
    )
    result = enforce_registry_admission(
        request(), registry=production_registry
    )

    assert result.admitted is False
    assert result.reason_categories == (
        RegistryAdmissionReason.REGISTRY_WRITE_REJECTED,
    )
    assert production_registry.snapshot == {}
    assert production_registry.events == ()


def test_exact_resolve_succeeds_without_discovery() -> None:
    registry, result = admit()
    assert result.entry is not None
    resolved = registry.resolve_exact(
        profile_id="synthetic-profile",
        profile_version=version("1.2.3"),
        product_id="product-fixture-alpha",
        product_version=version("2.3.4"),
        protocol_version=version("1.0.0"),
    )
    assert resolved == result.entry


@pytest.mark.parametrize(
    "override",
    [
        {"profile_version": version("1.2.2")},
        {"product_version": version("2.3.3")},
        {"protocol_version": version("1.1.0")},
    ],
)
def test_exact_resolve_rejects_version_mismatch(
    override: dict[str, object],
) -> None:
    registry, _ = admit()
    values: dict[str, object] = {
        "profile_id": "synthetic-profile",
        "profile_version": version("1.2.3"),
        "product_id": "product-fixture-alpha",
        "product_version": version("2.3.4"),
        "protocol_version": version("1.0.0"),
    }
    values.update(override)
    with pytest.raises(RegistryAdmissionError) as caught:
        registry.resolve_exact(**values)  # type: ignore[arg-type]
    assert caught.value.category is RegistryAdmissionReason.IDENTITY_MISMATCH


@pytest.mark.parametrize(
    "flag",
    ["fallback", "nearest_version", "infer_schema"],
)
def test_exact_resolve_rejects_implicit_selection(flag: str) -> None:
    registry, _ = admit()
    values: dict[str, object] = {
        "profile_id": "synthetic-profile",
        "profile_version": version("1.2.3"),
        "product_id": "product-fixture-alpha",
        "product_version": version("2.3.4"),
        "protocol_version": version("1.0.0"),
        flag: True,
    }
    with pytest.raises(RegistryAdmissionError) as caught:
        registry.resolve_exact(**values)  # type: ignore[arg-type]
    assert caught.value.category is (
        RegistryAdmissionReason.SECURITY_BOUNDARY_VIOLATION
    )


def test_result_and_entry_digests_are_deterministic() -> None:
    registry_a, result_a = admit()
    registry_b, result_b = admit()
    assert result_a.canonical_digest == result_b.canonical_digest
    assert result_a.entry is not None
    assert result_b.entry is not None
    assert result_a.entry.canonical_digest == result_b.entry.canonical_digest
    assert registry_a.snapshot == registry_b.snapshot
    assert (
        CANONICAL_REGISTRY_ADMISSION_DIGEST_ALGORITHM
        == "sha256"
    )


def test_result_field_change_changes_digest() -> None:
    _, result = admit()
    assert result.admitted_at is not None
    changed = replace(
        result,
        evaluation_time=result.evaluation_time
        + timedelta(microseconds=1),
        admitted_at=result.admitted_at + timedelta(microseconds=1),
    )
    assert changed.canonical_digest != result.canonical_digest


def test_equivalent_offset_instant_has_same_result_digest() -> None:
    offset = timezone(timedelta(hours=-4))
    registry_a, result_a = admit()
    registry_b, result_b = admit(
        request(evaluation_time=EVALUATION_TIME.astimezone(offset))
    )
    assert result_a.canonical_digest == result_b.canonical_digest
    assert registry_a.snapshot == registry_b.snapshot


def test_safe_summary_and_errors_do_not_disclose_unsafe_detail() -> None:
    _, result = admit()
    rendered = repr(result.safe_summary).lower()
    for forbidden in (
        "authorization:",
        "api_key",
        "cookie=",
        "http://",
        "https://",
        "c:\\",
        "/private/",
        "traceback",
        "raw_request",
        "raw_response",
        "hostname",
        "username",
    ):
        assert forbidden not in rendered
    with pytest.raises(RegistryAdmissionError) as caught:
        request(registry_administrator_id="Authorization: Bearer opaque")
    assert "Authorization" not in str(caught.value)
    assert "Bearer" not in repr(caught.value)


def test_contracts_are_immutable_and_external_snapshot_is_read_only() -> None:
    admission_request = request()
    registry, result = admit(admission_request)
    with pytest.raises(FrozenInstanceError):
        admission_request.admission_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.admitted = False  # type: ignore[misc]
    assert result.entry is not None
    with pytest.raises(FrozenInstanceError):
        result.entry.profile_id = "changed"  # type: ignore[misc]
    snapshot = registry.snapshot
    with pytest.raises(TypeError):
        snapshot[next(iter(snapshot))] = result.entry  # type: ignore[index]


def test_request_entry_and_result_do_not_retain_raw_inputs() -> None:
    admission_request = request()
    _, result = admit(admission_request)
    assert result.entry is not None
    for contract in (admission_request, result.entry, result):
        names = set(contract.__dataclass_fields__)
        assert not names & {
            "endpoint",
            "path",
            "credential",
            "query",
            "raw_request",
            "raw_response",
            "manual_validation_plan",
            "manual_validation_evidence",
            "fixture",
            "stack_trace",
            "internal_exception",
        }


def test_atomic_commit_exception_leaves_store_unchanged() -> None:
    class FailingTestStore(TestRegistryAdmissionStore):
        def _commit(self, entry: RegistryAdmissionEntry) -> None:
            raise RuntimeError("synthetic commit failure")

    registry = FailingTestStore()
    result = enforce_registry_admission(request(), registry=registry)
    assert_denied(
        result,
        registry,
        RegistryAdmissionReason.REGISTRY_COMMIT_FAILED,
    )


def test_reason_category_contract_is_complete_and_ordered() -> None:
    assert tuple(reason.value for reason in RegistryAdmissionReason) == (
        "decision_ineligible",
        "decision_invalid",
        "decision_not_yet_valid",
        "decision_expired",
        "identity_mismatch",
        "digest_mismatch",
        "role_conflict",
        "restriction_mismatch",
        "registry_kind_invalid",
        "initial_status_invalid",
        "duplicate_entry",
        "status_ineligible",
        "revalidation_required",
        "security_boundary_violation",
        "registry_write_rejected",
        "registry_commit_failed",
    )


def test_module_has_no_io_clock_random_uuid_or_transport_imports() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    forbidden = {
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "socket",
        "subprocess",
        "time",
        "urllib",
        "uuid",
    }
    assert not any(
        name == item or name.startswith(f"{item}.")
        for name in imports
        for item in forbidden
    )
    source = MODULE.read_text(encoding="utf-8")
    for forbidden_call in (
        "datetime.now(",
        "datetime.utcnow(",
        "open(",
        "urlopen(",
        "requests.",
        "socket.",
        "subprocess.",
        "uuid.",
        "random.",
    ):
        assert forbidden_call not in source
