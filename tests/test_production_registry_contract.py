from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone

import pytest

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    SemanticVersion,
)
from ragguard.production_registry import (
    RegistryEntry,
    RegistryEventCategory,
    RegistryKind,
    RegistryStatus,
    TrustedProductionRegistry,
    validate_registration_eligibility,
)
from ragguard.profile_approval import (
    ApprovalMetadata,
    ProfileMaturity,
)
from ragguard.retrieval import RetrievalAdapterError
from ragguard.validation_report import (
    ValidationReport,
    required_validation_case_ids,
)


NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)
PROFILE_VERSION = SemanticVersion.parse("1.0.0")
REQUIRED_CAPABILITIES = sorted(
    {
        "retrieval",
        "bounded_top_k",
        "deterministic_result_schema",
        "safe_source_identifier",
        "response_size_compliance",
    }
)


def case_set(validation_type: str = "manual") -> list[dict[str, object]]:
    return [
        {
            "case_id": case_id,
            "outcome": "passed",
            "safe_error_category": None,
            "bounded_duration_ms": 10,
            "result_count": 1,
            "required": True,
            "notes_code": "none",
        }
        for case_id in sorted(required_validation_case_ids(validation_type))
    ]


def report_data(
    *,
    validation_type: str = "manual",
    **overrides: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "validation_record_id": "validation-report-001",
        "profile_id": "approved-profile",
        "profile_version": "1.0.0",
        "protocol_version": "1.0.0",
        "normalized_product_version": "1.3.2",
        "validation_type": validation_type,
        "started_at": "2026-07-24T00:00:00Z",
        "completed_at": "2026-07-24T00:01:00Z",
        "environment_class": (
            "loopback_manual"
            if validation_type == "manual"
            else "synthetic_harness"
        ),
        "case_results": case_set(validation_type),
        "required_capabilities_result": "passed",
        "optional_capabilities_result": "passed",
        "score_semantics_result": "passed",
        "source_policy_result": "passed",
        "transport_boundary_result": "passed",
        "non_disclosure_result": "passed",
        "overall_status": "passed",
        "revalidation_required": False,
        "safe_error_categories": [],
        "expires_at": "2026-10-24T00:00:00Z",
    }
    value.update(overrides)
    return value


def approval_data(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "approval_record_id": "approval-001",
        "reviewer_id": "reviewer-001",
        "approver_id": "approver-001",
        "decision": "approved",
        "approved_at": "2026-07-24T00:02:00Z",
        "validation_record_id": "validation-report-001",
        "supported_product_version_range": {
            "minimum_version": "1.2.0",
            "maximum_version": "1.4.9",
            "open_ended": False,
        },
        "approved_capabilities": REQUIRED_CAPABILITIES,
        "approved_score_semantics": "unscored",
        "approved_source_identifier_policy": "opaque_safe_id",
        "restrictions": None,
        "expires_at": "2027-07-24T00:00:00Z",
    }
    value.update(overrides)
    return value


def evidence(
    *,
    validation_type: str = "manual",
    report_overrides: dict[str, object] | None = None,
    approval_overrides: dict[str, object] | None = None,
) -> tuple[ValidationReport, ApprovalMetadata]:
    report = ValidationReport.from_mapping(
        report_data(
            validation_type=validation_type,
            **(report_overrides or {}),
        )
    )
    approval = ApprovalMetadata.from_mapping(
        approval_data(**(approval_overrides or {}))
    )
    return report, approval


def entry_for(
    report: ValidationReport,
    approval: ApprovalMetadata,
    *,
    kind: RegistryKind = RegistryKind.PRODUCTION,
    maturity: ProfileMaturity = ProfileMaturity.APPROVED,
) -> RegistryEntry:
    return RegistryEntry.from_evidence(
        profile_id="approved-profile",
        profile_version=PROFILE_VERSION,
        maturity=maturity,
        approval_metadata=approval,
        validation_report=report,
        registry_kind=kind,
        registered_at=NOW,
    )


def populated_registry(
    *,
    report: ValidationReport | None = None,
    approval: ApprovalMetadata | None = None,
) -> tuple[TrustedProductionRegistry, RegistryEntry]:
    if report is None or approval is None:
        report, approval = evidence()
    entry = entry_for(report, approval)
    registry = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    registry.register(
        entry,
        approval_metadata=approval,
        validation_report=report,
        evaluation_time=NOW,
    )
    return registry, entry


def entry_mapping(entry: RegistryEntry) -> dict[str, object]:
    restrictions = None
    if entry.restrictions is not None:
        restrictions = {
            "maximum_top_k": entry.restrictions.maximum_top_k,
            "score_disabled": entry.restrictions.score_disabled,
            "title_disabled": entry.restrictions.title_disabled,
            "matched_keywords_disabled": (
                entry.restrictions.matched_keywords_disabled
            ),
            "query_id_echo_required": (
                entry.restrictions.query_id_echo_required
            ),
            "supported_minor_versions": list(
                entry.restrictions.supported_minor_versions
            ),
            "expires_at": (
                entry.restrictions.expires_at.isoformat()
                if entry.restrictions.expires_at
                else None
            ),
        }
    version_range = entry.supported_product_version_range
    return {
        "profile_id": entry.profile_id,
        "profile_version": str(entry.profile_version),
        "protocol_version": str(entry.protocol_version),
        "maturity": entry.maturity.value,
        "approval_record_id": entry.approval_record_id,
        "validation_record_id": entry.validation_record_id,
        "approval_decision": entry.approval_decision.value,
        "supported_product_version_range": {
            "minimum_version": str(version_range.minimum_version),
            "maximum_version": (
                str(version_range.maximum_version)
                if version_range.maximum_version
                else None
            ),
            "open_ended": version_range.open_ended,
        },
        "approved_capabilities": list(entry.approved_capabilities),
        "approved_score_semantics": entry.approved_score_semantics.value,
        "approved_source_identifier_policy": (
            entry.approved_source_identifier_policy.value
        ),
        "restrictions": restrictions,
        "registered_at": entry.registered_at.isoformat(),
        "expires_at": (
            entry.expires_at.isoformat() if entry.expires_at else None
        ),
        "registry_status": entry.registry_status.value,
        "registry_kind": entry.registry_kind.value,
        "validation_type": entry.validation_type.value,
        "validation_expires_at": (
            entry.validation_expires_at.isoformat()
            if entry.validation_expires_at
            else None
        ),
        "approval_expires_at": (
            entry.approval_expires_at.isoformat()
            if entry.approval_expires_at
            else None
        ),
        "revalidation_required": entry.revalidation_required,
    }


def assert_safe_error(
    caught: pytest.ExceptionInfo[RetrievalAdapterError],
    category: CompatibilityErrorCategory,
) -> None:
    assert str(caught.value) == category.value
    assert caught.value.__cause__ is None


def test_registry_entry_is_typed_immutable_and_safe() -> None:
    report, approval = evidence()
    entry = entry_for(report, approval)
    assert entry.registry_status is RegistryStatus.ACTIVE
    assert entry.expires_at == report.expires_at
    with pytest.raises(FrozenInstanceError):
        entry.profile_id = "changed"  # type: ignore[misc]
    rendered = repr(entry)
    assert rendered == "RegistryEntry(<safe>)"
    assert "approval-001" not in rendered
    assert "validation-report-001" not in rendered


def test_registry_entry_mapping_rejects_unknown_and_sensitive_fields() -> None:
    report, approval = evidence()
    raw = entry_mapping(entry_for(report, approval))
    restored = RegistryEntry.from_mapping(raw)
    assert restored.profile_id == "approved-profile"
    for field, secret in (
        ("endpoint", "private-endpoint"),
        ("path", "C:/private/path"),
        ("token", "credential-value"),
    ):
        invalid = dict(raw)
        invalid[field] = secret
        with pytest.raises(RetrievalAdapterError) as caught:
            RegistryEntry.from_mapping(invalid)
        assert_safe_error(
            caught, CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
        )
        assert secret not in str(caught.value)


def test_approved_entry_registers_and_resolves_exactly() -> None:
    registry, entry = populated_registry()
    assert registry.contains("approved-profile", "1.0.0")
    resolved = registry.resolve(
        profile_id="approved-profile",
        profile_version="1.0.0",
        normalized_product_version="1.3.2",
        evaluation_time=NOW,
    )
    assert resolved.profile_id == entry.profile_id
    assert resolved.profile_version == entry.profile_version
    assert resolved.approved_capabilities == entry.approved_capabilities
    assert "approval-001" not in repr(resolved)


def test_restricted_entry_registers_and_resolves() -> None:
    report, approval = evidence(
        approval_overrides={
            "decision": "approved_with_restrictions",
            "restrictions": {
                "maximum_top_k": 5,
                "supported_minor_versions": ["1.3"],
            },
        }
    )
    registry, _ = populated_registry(report=report, approval=approval)
    resolved = registry.resolve(
        profile_id="approved-profile",
        profile_version="1.0.0",
        normalized_product_version="1.3.2",
        evaluation_time=NOW,
    )
    assert resolved.restrictions is not None
    assert resolved.restrictions.maximum_top_k == 5


@pytest.mark.parametrize(
    ("maturity", "category"),
    [
        (
            ProfileMaturity.DRAFT,
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
        (
            ProfileMaturity.SYNTHETIC_VALIDATED,
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
        (
            ProfileMaturity.MANUALLY_VALIDATED,
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
        (
            ProfileMaturity.DEPRECATED,
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
        (
            ProfileMaturity.REVOKED,
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
    ],
)
def test_unapproved_maturity_is_rejected(
    maturity: ProfileMaturity,
    category: CompatibilityErrorCategory,
) -> None:
    report, approval = evidence()
    entry = entry_for(report, approval, maturity=maturity)
    registry = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.register(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=NOW,
        )
    assert_safe_error(caught, category)


@pytest.mark.parametrize("decision", ["rejected", "needs_revalidation"])
def test_unapproved_decision_is_rejected(decision: str) -> None:
    report, approval = evidence(
        approval_overrides={"decision": decision}
    )
    entry = entry_for(report, approval)
    registry = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.register(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=NOW,
        )
    assert_safe_error(caught, CompatibilityErrorCategory.PROFILE_UNAPPROVED)


def test_expired_report_and_approval_are_distinguished() -> None:
    later = datetime(2026, 11, 1, tzinfo=timezone.utc)
    report, approval = evidence()
    entry = entry_for(report, approval)
    with pytest.raises(RetrievalAdapterError) as report_error:
        validate_registration_eligibility(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=later,
        )
    assert_safe_error(
        report_error,
        CompatibilityErrorCategory.PROFILE_VALIDATION_EXPIRED,
    )

    report, approval = evidence(
        report_overrides={"expires_at": "2027-10-24T00:00:00Z"},
        approval_overrides={"expires_at": "2026-10-24T00:00:00Z"},
    )
    entry = entry_for(report, approval)
    with pytest.raises(RetrievalAdapterError) as approval_error:
        validate_registration_eligibility(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=later,
        )
    assert_safe_error(
        approval_error, CompatibilityErrorCategory.APPROVAL_EXPIRED
    )


@pytest.mark.parametrize(
    ("report_overrides", "category"),
    [
        (
            {"overall_status": "failed"},
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
        (
            {"overall_status": "incomplete"},
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
        (
            {
                "overall_status": "expired",
                "revalidation_required": True,
            },
            CompatibilityErrorCategory.REVALIDATION_REQUIRED,
        ),
        (
            {
                "overall_status": "failed",
                "required_capabilities_result": "failed",
            },
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
        (
            {
                "overall_status": "failed",
                "score_semantics_result": "failed",
            },
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
        (
            {
                "overall_status": "failed",
                "source_policy_result": "failed",
            },
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
        (
            {
                "overall_status": "failed",
                "non_disclosure_result": "failed",
            },
            CompatibilityErrorCategory.PROFILE_UNAPPROVED,
        ),
    ],
)
def test_unsafe_or_incomplete_validation_is_rejected(
    report_overrides: dict[str, object],
    category: CompatibilityErrorCategory,
) -> None:
    report, approval = evidence(report_overrides=report_overrides)
    entry = entry_for(report, approval)
    registry = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.register(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=NOW,
        )
    assert_safe_error(caught, category)


@pytest.mark.parametrize(
    "mutation",
    [
        {"approval_record_id": "other-approval"},
        {"validation_record_id": "other-validation"},
        {"profile_id": "other-profile"},
        {"profile_version": SemanticVersion.parse("2.0.0")},
        {"protocol_version": SemanticVersion.parse("2.0.0")},
        {"approved_capabilities": tuple(REQUIRED_CAPABILITIES[:-1])},
    ],
)
def test_registry_evidence_mismatch_fails_closed(
    mutation: dict[str, object],
) -> None:
    report, approval = evidence()
    entry = replace(entry_for(report, approval), **mutation)
    with pytest.raises(RetrievalAdapterError) as caught:
        validate_registration_eligibility(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=NOW,
        )
    assert_safe_error(
        caught, CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
    )


def test_synthetic_entry_is_rejected_by_production_registry() -> None:
    report, approval = evidence(validation_type="synthetic")
    entry = entry_for(report, approval)
    registry = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.register(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=NOW,
        )
    assert_safe_error(
        caught, CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
    )


def test_test_registry_accepts_explicit_test_entry_without_conversion() -> None:
    report, approval = evidence(validation_type="synthetic")
    entry = entry_for(report, approval, kind=RegistryKind.TEST)
    registry = TrustedProductionRegistry(kind=RegistryKind.TEST)
    registry.register(
        entry,
        approval_metadata=approval,
        validation_report=report,
        evaluation_time=NOW,
    )
    assert registry.contains("approved-profile", "1.0.0")
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.resolve(
            profile_id="approved-profile",
            profile_version="1.0.0",
            normalized_product_version="1.3.2",
            evaluation_time=NOW,
        )
    assert_safe_error(
        caught, CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
    )


def test_registry_kind_mismatch_is_rejected() -> None:
    report, approval = evidence()
    entry = entry_for(report, approval, kind=RegistryKind.TEST)
    registry = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.register(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=NOW,
        )
    assert_safe_error(
        caught, CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
    )


def test_duplicate_registration_and_overwrite_are_rejected() -> None:
    report, approval = evidence()
    registry, entry = populated_registry(report=report, approval=approval)
    for candidate in (
        entry,
        replace(entry, approval_record_id="different-approval"),
    ):
        with pytest.raises(RetrievalAdapterError) as caught:
            registry.register(
                candidate,
                approval_metadata=approval,
                validation_report=report,
                evaluation_time=NOW,
            )
        assert_safe_error(
            caught, CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
        )


def test_resolution_requires_exact_profile_and_version_without_fallback() -> None:
    registry, _ = populated_registry()
    requests = (
        (
            "unknown-profile",
            "1.0.0",
            CompatibilityErrorCategory.PROFILE_NOT_REGISTERED,
        ),
        (
            "approved-profile",
            "1.0.1",
            CompatibilityErrorCategory.PROFILE_VERSION_NOT_REGISTERED,
        ),
        (
            "approved-profile",
            "0.9.9",
            CompatibilityErrorCategory.PROFILE_VERSION_NOT_REGISTERED,
        ),
    )
    for profile_id, profile_version, category in requests:
        with pytest.raises(RetrievalAdapterError) as caught:
            registry.resolve(
                profile_id=profile_id,
                profile_version=profile_version,
                normalized_product_version="1.3.2",
                evaluation_time=NOW,
            )
        assert_safe_error(caught, category)


def test_unsupported_product_version_has_no_nearest_candidate() -> None:
    registry, _ = populated_registry()
    for product_version in ("1.5.0", "private-product-version"):
        with pytest.raises(RetrievalAdapterError) as caught:
            registry.resolve(
                profile_id="approved-profile",
                profile_version="1.0.0",
                normalized_product_version=product_version,
                evaluation_time=NOW,
            )
        assert_safe_error(
            caught,
            CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED,
        )
        assert product_version not in str(caught.value)


@pytest.mark.parametrize(
    ("operation", "expected_status", "event_category"),
    [
        ("suspend", RegistryStatus.SUSPENDED, RegistryEventCategory.SUSPENDED),
        (
            "deprecate",
            RegistryStatus.DEPRECATED,
            RegistryEventCategory.DEPRECATED,
        ),
        ("revoke", RegistryStatus.REVOKED, RegistryEventCategory.REVOKED),
    ],
)
def test_explicit_active_transitions_return_safe_events(
    operation: str,
    expected_status: RegistryStatus,
    event_category: RegistryEventCategory,
) -> None:
    registry, _ = populated_registry()
    event = getattr(registry, operation)("approved-profile", "1.0.0")
    assert event.category is event_category
    assert event.registry_status == expected_status.value
    assert registry.snapshot[
        ("approved-profile", PROFILE_VERSION)
    ].registry_status is expected_status


@pytest.mark.parametrize(
    ("operation", "category"),
    [
        ("suspend", CompatibilityErrorCategory.PROFILE_SUSPENDED),
        ("deprecate", CompatibilityErrorCategory.PROFILE_DEPRECATED),
        ("revoke", CompatibilityErrorCategory.PROFILE_REVOKED),
    ],
)
def test_inactive_entries_cannot_resolve(
    operation: str,
    category: CompatibilityErrorCategory,
) -> None:
    registry, _ = populated_registry()
    getattr(registry, operation)("approved-profile", "1.0.0")
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.resolve(
            profile_id="approved-profile",
            profile_version="1.0.0",
            normalized_product_version="1.3.2",
            evaluation_time=NOW,
        )
    assert_safe_error(caught, category)


def test_transition_allowlist_has_no_reactivation_or_rollback() -> None:
    registry, _ = populated_registry()
    registry.suspend("approved-profile", "1.0.0")
    with pytest.raises(RetrievalAdapterError) as caught:
        registry.suspend("approved-profile", "1.0.0")
    assert_safe_error(
        caught, CompatibilityErrorCategory.REGISTRY_METADATA_INVALID
    )
    registry.revoke("approved-profile", "1.0.0")
    for operation in (registry.suspend, registry.deprecate, registry.revoke):
        with pytest.raises(RetrievalAdapterError):
            operation("approved-profile", "1.0.0")


def test_safe_summaries_are_bounded_and_immutable() -> None:
    registry, _ = populated_registry()
    summaries = registry.list_safe_summaries(
        evaluation_time=NOW,
        normalized_product_version="1.3.2",
    )
    assert isinstance(summaries, tuple)
    assert summaries[0].supported_version_status == "supported"
    assert summaries[0].expiration_status == "active"
    mapping = summaries[0].as_mapping()
    with pytest.raises(TypeError):
        mapping["profile_id"] = "changed"  # type: ignore[index]
    rendered = repr(summaries) + repr(mapping)
    for secret in (
        "reviewer-001",
        "approver-001",
        "approval-001",
        "validation-report-001",
        "private-endpoint",
        "credential-value",
    ):
        assert secret not in rendered


def test_snapshot_and_history_cannot_mutate_registry() -> None:
    registry, entry = populated_registry()
    snapshot = registry.snapshot
    with pytest.raises(TypeError):
        snapshot[("other", PROFILE_VERSION)] = entry  # type: ignore[index]
    events = registry.events
    assert isinstance(events, tuple)
    assert events[0].category is RegistryEventCategory.REGISTERED
    registry.suspend("approved-profile", "1.0.0")
    assert entry.registry_status is RegistryStatus.ACTIVE
    assert snapshot[
        ("approved-profile", PROFILE_VERSION)
    ].registry_status is RegistryStatus.ACTIVE


def test_resolution_rejection_event_never_records_raw_secret() -> None:
    registry, _ = populated_registry()
    secret = "credential-value/private-path"
    with pytest.raises(RetrievalAdapterError):
        registry.resolve(
            profile_id="approved-profile",
            profile_version=secret,
            normalized_product_version="1.3.2",
            evaluation_time=NOW,
        )
    rendered = repr(registry.events)
    assert secret not in rendered
    assert "private-path" not in rendered
    assert registry.events[-1].category is (
        RegistryEventCategory.RESOLUTION_REJECTED
    )


def test_default_or_unknown_registry_kind_is_not_created() -> None:
    with pytest.raises(TypeError):
        TrustedProductionRegistry()  # type: ignore[call-arg]
    with pytest.raises(RetrievalAdapterError) as caught:
        TrustedProductionRegistry(kind="production")  # type: ignore[arg-type]
    assert_safe_error(
        caught, CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
    )
