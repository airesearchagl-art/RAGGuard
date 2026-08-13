from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.compatibility import SemanticVersion
from ragguard.production_equivalence import (
    ConfigurationEquivalence,
    EnvironmentEquivalenceContract,
    EquivalenceAssessmentReason,
    EquivalenceAssessmentResult,
    EquivalenceCriteria,
    EquivalenceEvidenceDescriptor,
    EquivalenceEvidenceSourceKind,
    ProductBehaviorEquivalence,
    ProductionEquivalenceAssessmentRequest,
    canonical_case_coverage_digest,
    evaluate_production_equivalence,
)
from test_manual_validation_execution_contract import chain, plan


UTC = timezone.utc
EVALUATION_TIME = datetime(2026, 8, 11, tzinfo=UTC)
CASES = ("case-alpha", "case-beta")


def digest(character: str) -> str:
    return "sha256:" + character * 64


def environment_equivalence(**changes: object) -> EnvironmentEquivalenceContract:
    values: dict[str, object] = {
        "environment_equivalence_id": "environment-equivalence-v017",
        "runtime_family": "python-runtime",
        "runtime_version": SemanticVersion(3, 12, 0),
        "dependency_manifest_digest": digest("d"),
        "configuration_digest": digest("e"),
        "capability_set_digest": digest("f"),
        "isolation_mode": "controlled-isolation",
        "network_policy": "offline-only",
        "filesystem_policy": "no-write",
        "external_dependency_policy": "none",
    }
    values.update(changes)
    return EnvironmentEquivalenceContract(**values)  # type: ignore[arg-type]


def configuration(**changes: object) -> ConfigurationEquivalence:
    values: dict[str, object] = {
        "profile_id": "synthetic-profile",
        "profile_version": SemanticVersion(1, 2, 3),
        "product_id": "product-fixture-alpha",
        "product_version": SemanticVersion(2, 3, 4),
        "protocol_version": SemanticVersion(1, 0, 0),
        "feature_flags_digest": digest("1"),
        "limits_digest": digest("2"),
        "compatibility_contract_digest": digest("3"),
    }
    values.update(changes)
    return ConfigurationEquivalence(**values)  # type: ignore[arg-type]


def behavior(**changes: object) -> ProductBehaviorEquivalence:
    values: dict[str, object] = {
        "required_case_ids": CASES,
        "observed_behavior_digest": digest("4"),
        "expected_behavior_digest": digest("4"),
    }
    values.update(changes)
    return ProductBehaviorEquivalence(**values)  # type: ignore[arg-type]


def criteria(**changes: object) -> EquivalenceCriteria:
    values: dict[str, object] = {
        "criteria_id": "criteria-v017",
        "criteria_version": SemanticVersion(1, 0, 0),
        "required_evidence_kind": (
            EquivalenceEvidenceSourceKind.PRODUCTION_EQUIVALENT_CANDIDATE
        ),
        "required_case_coverage": CASES,
        "required_environment_digest": environment_equivalence().canonical_digest,
        "required_configuration_digest": configuration().canonical_digest,
        "required_protocol_contract_digest": digest("5"),
        "required_product_contract_digest": digest("6"),
        "required_expected_behavior_digest": digest("4"),
    }
    values.update(changes)
    return EquivalenceCriteria(**values)  # type: ignore[arg-type]


def assessment_request(**changes: object) -> ProductionEquivalenceAssessmentRequest:
    manual_chain = chain()
    assert manual_chain.approval is not None
    values: dict[str, object] = {
        "assessment_request_id": "assessment-request-v017",
        "manual_validation_approval_digest": manual_chain.approval.canonical_digest,
        "manual_validation_evidence_digest": manual_chain.evidence.canonical_digest,
        "execution_record_digest": manual_chain.execution_record.canonical_digest,
        "validation_plan_digest": plan().canonical_digest,
        "fixture_manifest_digest": manual_chain.fixture_manifest.canonical_digest,
        "environment_contract_digest": manual_chain.environment.canonical_digest,
        "profile_id": "synthetic-profile",
        "profile_version": SemanticVersion(1, 2, 3),
        "product_id": "product-fixture-alpha",
        "product_version": SemanticVersion(2, 3, 4),
        "protocol_version": SemanticVersion(1, 0, 0),
        "requested_at": datetime(2026, 8, 10, 3, tzinfo=UTC),
        "requested_by": "equivalence-requester",
        "assessor_id": "equivalence-assessor",
        "validation_operator_id": "operator-v016",
        "validation_reviewer_id": "reviewer-v016",
        "manual_validation_approver_id": "approver-v016",
    }
    values.update(changes)
    return ProductionEquivalenceAssessmentRequest(**values)  # type: ignore[arg-type]


def descriptor(**changes: object) -> EquivalenceEvidenceDescriptor:
    values: dict[str, object] = {
        "descriptor_id": "descriptor-v017",
        "source_kind": EquivalenceEvidenceSourceKind.PRODUCTION_EQUIVALENT_CANDIDATE,
        "source_validation_digest": assessment_request().manual_validation_approval_digest,
        "product_contract_digest": digest("6"),
        "protocol_contract_digest": digest("5"),
        "environment_descriptor_digest": environment_equivalence().canonical_digest,
        "configuration_descriptor_digest": configuration().canonical_digest,
        "test_case_coverage_digest": canonical_case_coverage_digest(CASES),
        "provenance_digest": digest("7"),
        "evidence_created_at": datetime(2026, 8, 10, 4, tzinfo=UTC),
    }
    values.update(changes)
    return EquivalenceEvidenceDescriptor(**values)  # type: ignore[arg-type]


def assess(**changes: object):
    values: dict[str, object] = {
        "request": assessment_request(),
        "criteria": criteria(),
        "descriptor": descriptor(),
        "environment": environment_equivalence(),
        "configuration": configuration(),
        "behavior": behavior(),
        "manual_validation_plan": plan(),
        "manual_validation_chain": chain(),
        "evaluation_time": EVALUATION_TIME,
        "independent_reviewer_id": "equivalence-reviewer",
    }
    values.update(changes)
    return evaluate_production_equivalence(**values)  # type: ignore[arg-type]


def test_contracts_are_immutable_and_digest_deterministic() -> None:
    value = assessment_request()
    assert value.canonical_digest == assessment_request().canonical_digest
    with pytest.raises(FrozenInstanceError):
        value.assessor_id = "changed"  # type: ignore[misc]


def test_microsecond_changes_digest_and_offset_does_not() -> None:
    value = assessment_request()
    changed = replace(value, requested_at=value.requested_at + timedelta(microseconds=1))
    equivalent = replace(
        value,
        requested_at=value.requested_at.astimezone(timezone(timedelta(hours=9))),
    )
    assert changed.canonical_digest != value.canonical_digest
    assert equivalent.canonical_digest == value.canonical_digest


@pytest.mark.parametrize(
    "change",
    [
        {"use_current_alias": True},
        {"use_latest_alias": True},
        {"allow_fallback": True},
        {"allow_nearest_version": True},
        {"allow_version_inference": True},
    ],
)
def test_alias_fallback_and_inference_are_ineligible(change: dict[str, bool]) -> None:
    result = assess(request=assessment_request(**change))
    assert result.result is EquivalenceAssessmentResult.INELIGIBLE
    assert EquivalenceAssessmentReason.UNSAFE_SELECTION in result.reason_categories


def test_synthetic_source_is_not_production_equivalent() -> None:
    result = assess(
        descriptor=descriptor(source_kind=EquivalenceEvidenceSourceKind.SYNTHETIC)
    )
    assert result.result is EquivalenceAssessmentResult.NEEDS_PRODUCT_BEHAVIOR_EQUIVALENCE


def test_environment_mismatch_has_first_metadata_priority() -> None:
    result = assess(descriptor=descriptor(environment_descriptor_digest=digest("8")))
    assert result.result is EquivalenceAssessmentResult.NEEDS_ENVIRONMENT_EQUIVALENCE


def test_configuration_mismatch_is_explicit() -> None:
    result = assess(descriptor=descriptor(configuration_descriptor_digest=digest("8")))
    assert result.result is EquivalenceAssessmentResult.NEEDS_CONFIGURATION_EQUIVALENCE


def test_protocol_mismatch_is_explicit() -> None:
    result = assess(descriptor=descriptor(protocol_contract_digest=digest("8")))
    assert result.result is EquivalenceAssessmentResult.NEEDS_PROTOCOL_EQUIVALENCE


@pytest.mark.parametrize(
    "changed_behavior",
    [
        behavior(failed_case_ids=("case-alpha",)),
        behavior(skipped_case_ids=("case-alpha",)),
        behavior(unresolved_divergence_count=1),
        behavior(observed_behavior_digest=digest("9")),
    ],
)
def test_incomplete_behavior_cannot_be_equivalent(
    changed_behavior: ProductBehaviorEquivalence,
) -> None:
    result = assess(behavior=changed_behavior)
    assert result.result is EquivalenceAssessmentResult.NEEDS_PRODUCT_BEHAVIOR_EQUIVALENCE


def test_independent_review_is_a_distinct_stage() -> None:
    result = assess(independent_reviewer_id=None)
    assert result.result is EquivalenceAssessmentResult.NEEDS_INDEPENDENT_REVIEW


def test_all_prerequisites_are_only_eligible_for_review() -> None:
    result = assess()
    assert result.result is EquivalenceAssessmentResult.ELIGIBLE_FOR_EQUIVALENCE_REVIEW
    assert result.write_count == result.mutation_count == result.persistence_count == 0
    assert result.filesystem_count == result.database_count == 0
    assert result.transport_count == result.http_count == result.activation_count == 0


def test_manual_approval_digest_is_exact_bound() -> None:
    result = assess(
        request=assessment_request(manual_validation_approval_digest=digest("9"))
    )
    assert result.result is EquivalenceAssessmentResult.INELIGIBLE
    assert EquivalenceAssessmentReason.DIGEST_MISMATCH in result.reason_categories


def test_profile_product_protocol_are_exact_bound() -> None:
    result = assess(
        configuration=configuration(product_version=SemanticVersion(2, 3, 5))
    )
    assert result.result is EquivalenceAssessmentResult.INELIGIBLE
    assert EquivalenceAssessmentReason.IDENTITY_MISMATCH in result.reason_categories


def test_future_metadata_is_ineligible() -> None:
    result = assess(
        descriptor=descriptor(evidence_created_at=EVALUATION_TIME + timedelta(microseconds=1))
    )
    assert result.result is EquivalenceAssessmentResult.INELIGIBLE
    assert EquivalenceAssessmentReason.TEMPORAL_INVALID in result.reason_categories


def test_expired_plan_and_stale_evidence_are_ineligible() -> None:
    late = EVALUATION_TIME + timedelta(days=100)
    result = assess(evaluation_time=late)
    assert result.result is EquivalenceAssessmentResult.INELIGIBLE
    assert EquivalenceAssessmentReason.EXPIRED_PLAN in result.reason_categories
    assert EquivalenceAssessmentReason.STALE_EVIDENCE in result.reason_categories


def test_replay_snapshot_rejects_request_and_descriptor() -> None:
    result = assess(
        used_request_ids=frozenset({assessment_request().assessment_request_id}),
        used_descriptor_digests=frozenset({descriptor().canonical_digest}),
    )
    assert result.result is EquivalenceAssessmentResult.INELIGIBLE
    assert EquivalenceAssessmentReason.REPLAY in result.reason_categories


def test_role_conflict_with_manual_chain_is_ineligible() -> None:
    result = assess(
        request=assessment_request(assessor_id="operator-v016")
    )
    assert result.result is EquivalenceAssessmentResult.INELIGIBLE
    assert EquivalenceAssessmentReason.ROLE_CONFLICT in result.reason_categories


def test_safe_contracts_expose_no_raw_connection_fields() -> None:
    forbidden = {"endpoint", "hostname", "ip", "port", "credential", "token", "username"}
    assert forbidden.isdisjoint(EquivalenceEvidenceDescriptor.__dataclass_fields__)
    assert forbidden.isdisjoint(EnvironmentEquivalenceContract.__dataclass_fields__)
    assert "evaluation_time" in inspect.signature(evaluate_production_equivalence).parameters
