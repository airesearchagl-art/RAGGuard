from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.compatibility import CompatibilityErrorCategory, RetrievalAdapterError
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalMetadata,
    ApprovalRestrictions,
    ProfileApprovalContract,
    ProfileMaturity,
    SupportedProductVersionRange,
    ValidationMetadata,
    ValidationStatus,
    validate_maturity_transition,
)


NOW = datetime(2026, 7, 19, tzinfo=timezone.utc)
REQUIRED_CAPABILITIES = tuple(
    sorted(
        {
            "retrieval",
            "bounded_top_k",
            "deterministic_result_schema",
            "safe_source_identifier",
            "response_size_compliance",
        }
    )
)
VALIDATION_CASES = tuple(
    sorted(
        {
            "schema_validation",
            "synthetic_compatibility",
            "security_e2e",
            "capability_mapping",
            "request_response_mapping",
            "score_semantics",
            "source_identifier_policy",
            "timeout_boundary",
            "response_size_boundary",
            "error_non_disclosure",
            "manual_compatibility",
        }
    )
)


def version_range(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "minimum_version": "1.2.0",
        "maximum_version": "1.4.9",
        "open_ended": False,
    }
    value.update(overrides)
    return value


def validation_data(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "validation_record_id": "validation-001",
        "profile_id": "synthetic-profile",
        "profile_version": "1.0.0",
        "protocol_version": "1.0.0",
        "normalized_product_version": "1.3.2",
        "validation_status": "passed",
        "validated_at": "2026-07-19T00:00:00Z",
        "validation_cases": list(VALIDATION_CASES),
        "required_capabilities_result": True,
        "optional_capabilities_result": ["score", "title"],
        "safe_error_categories": [],
        "result_summary": "validation_passed",
    }
    value.update(overrides)
    return value


def approval_data(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "approval_record_id": "approval-001",
        "reviewer_id": "reviewer-001",
        "approver_id": "approver-001",
        "decision": "approved",
        "approved_at": "2026-07-19T00:00:00Z",
        "validation_record_id": "validation-001",
        "supported_product_version_range": version_range(),
        "approved_capabilities": list(REQUIRED_CAPABILITIES),
        "approved_score_semantics": "unscored",
        "approved_source_identifier_policy": "opaque_safe_id",
        "restrictions": None,
        "expires_at": "2027-07-19T00:00:00Z",
    }
    value.update(overrides)
    return value


def approved_contract(**overrides: object) -> ProfileApprovalContract:
    values: dict[str, object] = {
        "profile_id": "synthetic-profile",
        "profile_version": ValidationMetadata.from_mapping(
            validation_data()
        ).profile_version,
        "maturity": ProfileMaturity.APPROVED,
        "validation_metadata": ValidationMetadata.from_mapping(validation_data()),
        "approval_metadata": ApprovalMetadata.from_mapping(approval_data()),
    }
    values.update(overrides)
    return ProfileApprovalContract(**values)  # type: ignore[arg-type]


def assert_safe_error(
    caught: pytest.ExceptionInfo[RetrievalAdapterError],
    category: CompatibilityErrorCategory,
) -> None:
    assert str(caught.value) == category.value
    assert repr(caught.value) == f"RetrievalAdapterError('{category.value}')"
    assert caught.value.__cause__ is None


def test_profile_maturity_and_approval_decision_are_strict() -> None:
    assert ProfileMaturity("synthetic_validated") is ProfileMaturity.SYNTHETIC_VALIDATED
    assert ApprovalDecision("needs_revalidation") is ApprovalDecision.NEEDS_REVALIDATION
    with pytest.raises(ValueError):
        ProfileMaturity("APPROVED")
    with pytest.raises(ValueError):
        ApprovalDecision("temporary")


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "synthetic_validated"),
        ("synthetic_validated", "manually_validated"),
        ("manually_validated", "approved"),
        ("approved", "deprecated"),
        ("approved", "revoked"),
        ("deprecated", "revoked"),
    ],
)
def test_allowlisted_maturity_transitions_are_valid(current: str, target: str) -> None:
    validate_maturity_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "approved"),
        ("revoked", "approved"),
        ("deprecated", "approved"),
        ("approved", "synthetic_validated"),
        ("draft", "draft"),
    ],
)
def test_illegal_maturity_transitions_fail_closed(current: str, target: str) -> None:
    with pytest.raises(RetrievalAdapterError) as caught:
        validate_maturity_transition(current, target)
    assert_safe_error(caught, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)


def test_version_range_is_strict_and_does_not_select_nearest_version() -> None:
    supported = SupportedProductVersionRange.from_mapping(version_range())
    assert supported.contains("1.2.0") is True
    assert supported.contains("1.4.9") is True
    assert supported.contains("1.5.0") is False
    assert "1.2.0" not in repr(supported)


def test_open_ended_version_range_requires_explicit_flag() -> None:
    supported = SupportedProductVersionRange.from_mapping(
        version_range(maximum_version=None, open_ended=True)
    )
    assert supported.contains("9.0.0") is True
    for invalid in (
        version_range(maximum_version=None),
        version_range(open_ended=True),
        version_range(minimum_version="2.0.0", maximum_version="1.0.0"),
        version_range(minimum_version="1.0"),
    ):
        with pytest.raises(RetrievalAdapterError):
            SupportedProductVersionRange.from_mapping(invalid)


def test_restrictions_are_flat_typed_and_immutable() -> None:
    restrictions = ApprovalRestrictions.from_mapping(
        {
            "maximum_top_k": 5,
            "score_disabled": True,
            "supported_minor_versions": ["1.2", "1.3"],
        }
    )
    assert restrictions.maximum_top_k == 5
    assert restrictions.supported_minor_versions == ("1.2", "1.3")
    with pytest.raises(FrozenInstanceError):
        restrictions.maximum_top_k = 6  # type: ignore[misc]


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"unknown": True},
        {"score_disabled": 1},
        {"maximum_top_k": True},
        {"maximum_top_k": 0},
        {"maximum_top_k": 101},
        {"supported_minor_versions": ["1.2", "1.2"]},
        {"supported_minor_versions": ["1.2.0"]},
    ],
)
def test_invalid_or_empty_restrictions_are_rejected(value: dict[str, object]) -> None:
    if value == {}:
        assert ApprovalRestrictions.from_mapping(value).is_empty is True
        with pytest.raises(RetrievalAdapterError):
            ApprovalMetadata.from_mapping(
                approval_data(
                    decision="approved_with_restrictions", restrictions=value
                )
            )
    else:
        with pytest.raises(RetrievalAdapterError):
            ApprovalRestrictions.from_mapping(value)


def test_valid_approval_and_validation_metadata_are_immutable() -> None:
    validation = ValidationMetadata.from_mapping(validation_data())
    approval = ApprovalMetadata.from_mapping(approval_data())
    assert validation.validation_cases == VALIDATION_CASES
    assert approval.approved_capabilities == REQUIRED_CAPABILITIES
    with pytest.raises(FrozenInstanceError):
        approval.approver_id = "other"  # type: ignore[misc]
    assert "reviewer-001" not in repr(approval)
    assert "1.3.2" not in repr(validation)


def test_approved_with_restrictions_is_valid_and_enforced() -> None:
    approval = ApprovalMetadata.from_mapping(
        approval_data(
            decision="approved_with_restrictions",
            restrictions={
                "maximum_top_k": 5,
                "supported_minor_versions": ["1.3"],
            },
        )
    )
    contract = approved_contract(approval_metadata=approval)
    assert contract.require_active_approval("1.3.8", now=NOW).approval_status == "active"
    with pytest.raises(RetrievalAdapterError) as caught:
        contract.require_active_approval("1.2.8", now=NOW)
    assert_safe_error(caught, CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED)


@pytest.mark.parametrize(
    "restrictions",
    [
        {"score_disabled": True},
        {"title_disabled": True},
        {"matched_keywords_disabled": True},
        {"query_id_echo_required": True},
    ],
)
def test_contradictory_restrictions_are_rejected(
    restrictions: dict[str, object],
) -> None:
    capabilities = list(REQUIRED_CAPABILITIES) + ["score", "title", "matched_keywords"]
    with pytest.raises(RetrievalAdapterError):
        ApprovalMetadata.from_mapping(
            approval_data(
                decision="approved_with_restrictions",
                restrictions=restrictions,
                approved_capabilities=sorted(capabilities),
            )
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"unknown": "private-value"},
        {"reviewer_id": "same", "approver_id": "same"},
        {"approval_record_id": ""},
        {"decision": "temporary"},
        {"approved_capabilities": ["retrieval"]},
        {"approved_score_semantics": "normalized"},
        {"approved_source_identifier_policy": "filesystem_path"},
        {"endpoint": "private-endpoint"},
        {"credential": "private-credential"},
        {"path": "private-path"},
    ],
)
def test_invalid_or_unsafe_approval_metadata_fails_closed(
    mutation: dict[str, object],
) -> None:
    raw = approval_data()
    raw.update(mutation)
    with pytest.raises(RetrievalAdapterError) as caught:
        ApprovalMetadata.from_mapping(raw)
    assert "private" not in str(caught.value)
    assert_safe_error(caught, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)


@pytest.mark.parametrize(
    "mutation",
    [
        {"validation_cases": list(VALIDATION_CASES) + ["manual_compatibility"]},
        {"validation_cases": ["unknown_case"]},
        {"normalized_product_version": "nearest"},
        {"required_capabilities_result": 1},
        {"safe_error_categories": ["raw-private-error"]},
        {"endpoint": "private-endpoint"},
        {"raw_response": "private-response"},
        {"query": "private-query"},
    ],
)
def test_invalid_or_unsafe_validation_metadata_fails_closed(
    mutation: dict[str, object],
) -> None:
    raw = validation_data()
    raw.update(mutation)
    with pytest.raises(RetrievalAdapterError) as caught:
        ValidationMetadata.from_mapping(raw)
    assert "private" not in str(caught.value)
    assert_safe_error(caught, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)


def test_validation_and_profile_identity_must_match() -> None:
    validation = ValidationMetadata.from_mapping(
        validation_data(profile_id="other-profile")
    )
    with pytest.raises(RetrievalAdapterError) as caught:
        approved_contract(validation_metadata=validation)
    assert_safe_error(caught, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)


def test_approved_optional_capability_must_be_validated() -> None:
    approval = ApprovalMetadata.from_mapping(
        approval_data(
            approved_capabilities=sorted(
                REQUIRED_CAPABILITIES + ("matched_keywords",)
            )
        )
    )
    with pytest.raises(RetrievalAdapterError) as caught:
        approved_contract(approval_metadata=approval)
    assert_safe_error(caught, CompatibilityErrorCategory.APPROVAL_METADATA_INVALID)


@pytest.mark.parametrize(
    ("status", "summary", "errors"),
    [
        ("passed", "validation_failed", []),
        ("failed", "validation_passed", ["capability_mismatch"]),
        ("failed", "validation_failed", []),
    ],
)
def test_validation_status_summary_and_safe_errors_must_agree(
    status: str, summary: str, errors: list[str]
) -> None:
    with pytest.raises(RetrievalAdapterError):
        ValidationMetadata.from_mapping(
            validation_data(
                validation_status=status,
                result_summary=summary,
                safe_error_categories=errors,
            )
        )


@pytest.mark.parametrize("decision", ["rejected", "needs_revalidation"])
def test_rejected_or_stale_decision_cannot_be_approved(decision: str) -> None:
    approval = ApprovalMetadata.from_mapping(approval_data(decision=decision))
    with pytest.raises(RetrievalAdapterError) as caught:
        approved_contract(approval_metadata=approval)
    assert_safe_error(caught, CompatibilityErrorCategory.PROFILE_UNAPPROVED)


def test_approval_requires_completed_manual_validation() -> None:
    validation = ValidationMetadata.from_mapping(
        validation_data(
            validation_cases=[
                case for case in VALIDATION_CASES if case != "manual_compatibility"
            ]
        )
    )
    with pytest.raises(RetrievalAdapterError) as caught:
        approved_contract(validation_metadata=validation)
    assert_safe_error(caught, CompatibilityErrorCategory.MANUAL_VALIDATION_REQUIRED)


def test_active_approval_rejects_expiration_revalidation_and_out_of_range() -> None:
    expired = ApprovalMetadata.from_mapping(
        approval_data(expires_at="2026-07-18T00:00:00Z")
    )
    with pytest.raises(RetrievalAdapterError) as caught:
        approved_contract(approval_metadata=expired).require_active_approval("1.3.0", now=NOW)
    assert_safe_error(caught, CompatibilityErrorCategory.PROFILE_VALIDATION_EXPIRED)

    with pytest.raises(RetrievalAdapterError) as caught:
        approved_contract(revalidation_required=True).require_active_approval("1.3.0", now=NOW)
    assert_safe_error(caught, CompatibilityErrorCategory.REVALIDATION_REQUIRED)

    with pytest.raises(RetrievalAdapterError) as caught:
        approved_contract().require_active_approval("2.0.0", now=NOW)
    assert_safe_error(caught, CompatibilityErrorCategory.PRODUCT_VERSION_UNSUPPORTED)


@pytest.mark.parametrize(
    ("maturity", "category"),
    [
        (ProfileMaturity.DEPRECATED, CompatibilityErrorCategory.PROFILE_UNAPPROVED),
        (ProfileMaturity.REVOKED, CompatibilityErrorCategory.PROFILE_REVOKED),
    ],
)
def test_deprecated_and_revoked_profiles_never_reactivate(
    maturity: ProfileMaturity, category: CompatibilityErrorCategory
) -> None:
    contract = approved_contract(maturity=maturity)
    with pytest.raises(RetrievalAdapterError) as caught:
        contract.require_active_approval("1.3.0", now=NOW)
    assert_safe_error(caught, category)


def test_safe_summary_contains_only_bounded_status() -> None:
    summary = approved_contract().require_active_approval("1.3.2", now=NOW)
    assert summary.as_mapping() == {
        "profile_id": "synthetic-profile",
        "profile_version": "1.0.0",
        "maturity": "approved",
        "approval_decision": "approved",
        "approval_status": "active",
        "supported_version_status": "supported",
        "restriction_summary": "none",
        "validation_status": "passed",
        "revalidation_required": False,
        "revoked": False,
        "deprecated": False,
    }
    rendered = repr(summary) + str(summary)
    for marker in (
        "reviewer-001",
        "approver-001",
        "validation-001",
        "private-endpoint",
        "private-credential",
        "C:/private/path",
    ):
        assert marker not in rendered


def test_direct_collections_cannot_remain_mutable() -> None:
    raw = approval_data()
    raw["approved_capabilities"] = REQUIRED_CAPABILITIES
    approval = ApprovalMetadata.from_mapping(raw)
    assert isinstance(approval.approved_capabilities, tuple)
    with pytest.raises(RetrievalAdapterError):
        ApprovalMetadata(
            **{
                **approval.__dict__,
                "approved_capabilities": list(REQUIRED_CAPABILITIES),
            }
        )


def test_datetime_must_be_timezone_aware_and_boolean_is_not_integer() -> None:
    with pytest.raises(RetrievalAdapterError):
        ApprovalMetadata.from_mapping(approval_data(approved_at="2026-07-19T00:00:00"))
    with pytest.raises(RetrievalAdapterError):
        ApprovalRestrictions(maximum_top_k=True)
    future = NOW + timedelta(days=1)
    summary = approved_contract().require_active_approval("1.3.0", now=future)
    assert summary.approval_status == "active"
