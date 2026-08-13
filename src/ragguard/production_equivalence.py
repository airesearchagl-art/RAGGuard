from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar

from ragguard.compatibility import SemanticVersion
from ragguard.manual_validation_execution import ManualValidationChain
from ragguard.manual_validation_plan import ManualValidationPlan


CANONICAL_PRODUCTION_EQUIVALENCE_DIGEST_ALGORITHM = "sha256"
MAX_EQUIVALENCE_EVIDENCE_AGE = timedelta(days=90)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class EquivalenceEvidenceSourceKind(str, Enum):
    SYNTHETIC = "synthetic"
    CONTROLLED_MANUAL = "controlled_manual"
    PRODUCTION_EQUIVALENT_CANDIDATE = "production_equivalent_candidate"


class ProductionEquivalentState(str, Enum):
    NOT_ASSESSED = "not_assessed"
    ASSESSMENT_INCOMPLETE = "assessment_incomplete"
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"


class EquivalenceAssessmentResult(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_ENVIRONMENT_EQUIVALENCE = "needs_environment_equivalence"
    NEEDS_CONFIGURATION_EQUIVALENCE = "needs_configuration_equivalence"
    NEEDS_PROTOCOL_EQUIVALENCE = "needs_protocol_equivalence"
    NEEDS_PRODUCT_BEHAVIOR_EQUIVALENCE = "needs_product_behavior_equivalence"
    NEEDS_INDEPENDENT_REVIEW = "needs_independent_review"
    ELIGIBLE_FOR_EQUIVALENCE_REVIEW = "eligible_for_equivalence_review"


class EquivalenceAssessmentReason(str, Enum):
    IDENTITY_MISMATCH = "identity_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    MANUAL_VALIDATION_INVALID = "manual_validation_invalid"
    TEMPORAL_INVALID = "temporal_invalid"
    STALE_EVIDENCE = "stale_evidence"
    EXPIRED_PLAN = "expired_plan"
    REPLAY = "replay"
    ROLE_CONFLICT = "role_conflict"
    UNSAFE_SELECTION = "unsafe_selection"
    ENVIRONMENT_EQUIVALENCE_REQUIRED = "environment_equivalence_required"
    CONFIGURATION_EQUIVALENCE_REQUIRED = "configuration_equivalence_required"
    PROTOCOL_EQUIVALENCE_REQUIRED = "protocol_equivalence_required"
    PRODUCT_BEHAVIOR_EQUIVALENCE_REQUIRED = "product_behavior_equivalence_required"
    INDEPENDENT_REVIEW_REQUIRED = "independent_review_required"


_REASON_ORDER = tuple(EquivalenceAssessmentReason)
_INELIGIBLE_REASONS = frozenset(_REASON_ORDER[:9])


class ProductionEquivalenceError(ValueError):
    def __init__(self, category: str = "production_equivalence_contract_invalid") -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, repr=False)
class ProductionEquivalenceAssessmentRequest:
    assessment_request_id: str
    manual_validation_approval_digest: str
    manual_validation_evidence_digest: str
    execution_record_digest: str
    validation_plan_digest: str
    fixture_manifest_digest: str
    environment_contract_digest: str
    profile_id: str
    profile_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    protocol_version: SemanticVersion
    requested_at: datetime
    requested_by: str
    assessor_id: str
    validation_operator_id: str
    validation_reviewer_id: str
    manual_validation_approver_id: str
    use_current_alias: bool = False
    use_latest_alias: bool = False
    allow_fallback: bool = False
    allow_nearest_version: bool = False
    allow_version_inference: bool = False
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_PRODUCTION_EQUIVALENCE_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if not all(
            _is_identifier(value)
            for value in (
                self.assessment_request_id,
                self.profile_id,
                self.product_id,
                self.requested_by,
                self.assessor_id,
                self.validation_operator_id,
                self.validation_reviewer_id,
                self.manual_validation_approver_id,
            )
        ):
            _raise("production_equivalence_identity_invalid")
        if self.requested_by == self.assessor_id:
            _raise("production_equivalence_role_conflict")
        if not all(
            _is_digest(value)
            for value in (
                self.manual_validation_approval_digest,
                self.manual_validation_evidence_digest,
                self.execution_record_digest,
                self.validation_plan_digest,
                self.fixture_manifest_digest,
                self.environment_contract_digest,
            )
        ):
            _raise("production_equivalence_digest_invalid")
        if not all(
            isinstance(value, SemanticVersion)
            for value in (self.profile_version, self.product_version, self.protocol_version)
        ) or not _is_aware(self.requested_at):
            _raise()
        flags = (
            self.use_current_alias,
            self.use_latest_alias,
            self.allow_fallback,
            self.allow_nearest_version,
            self.allow_version_inference,
        )
        if any(type(value) is not bool for value in flags):
            _raise()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "allow_fallback": self.allow_fallback,
                "allow_nearest_version": self.allow_nearest_version,
                "allow_version_inference": self.allow_version_inference,
                "assessment_request_id": self.assessment_request_id,
                "assessor_id": self.assessor_id,
                "environment_contract_digest": self.environment_contract_digest,
                "execution_record_digest": self.execution_record_digest,
                "fixture_manifest_digest": self.fixture_manifest_digest,
                "manual_validation_approval_digest": self.manual_validation_approval_digest,
                "manual_validation_evidence_digest": self.manual_validation_evidence_digest,
                "manual_validation_roles": {
                    "approver_id": self.manual_validation_approver_id,
                    "reviewer_id": self.validation_reviewer_id,
                    "validation_operator_id": self.validation_operator_id,
                },
                "product_id": self.product_id,
                "product_version": str(self.product_version),
                "profile_id": self.profile_id,
                "profile_version": str(self.profile_version),
                "protocol_version": str(self.protocol_version),
                "requested_at": _canonical_datetime(self.requested_at),
                "requested_by": self.requested_by,
                "use_current_alias": self.use_current_alias,
                "use_latest_alias": self.use_latest_alias,
                "validation_plan_digest": self.validation_plan_digest,
            }
        )

    def __repr__(self) -> str:
        return "ProductionEquivalenceAssessmentRequest(<safe>)"


@dataclass(frozen=True, repr=False)
class EquivalenceCriteria:
    criteria_id: str
    criteria_version: SemanticVersion
    required_evidence_kind: EquivalenceEvidenceSourceKind
    required_case_coverage: tuple[str, ...]
    required_environment_digest: str
    required_configuration_digest: str
    required_protocol_contract_digest: str
    required_product_contract_digest: str
    required_expected_behavior_digest: str
    environment_equivalence_required: bool = True
    configuration_equivalence_required: bool = True
    protocol_equivalence_required: bool = True
    product_behavior_equivalence_required: bool = True
    provenance_required: bool = True
    independent_review_required: bool = True
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.criteria_id) or not isinstance(
            self.criteria_version, SemanticVersion
        ) or not isinstance(self.required_evidence_kind, EquivalenceEvidenceSourceKind):
            _raise()
        if (
            not isinstance(self.required_case_coverage, tuple)
            or not self.required_case_coverage
            or tuple(sorted(set(self.required_case_coverage))) != self.required_case_coverage
            or not all(_is_identifier(value) for value in self.required_case_coverage)
        ):
            _raise("production_equivalence_coverage_invalid")
        if not all(
            _is_digest(value)
            for value in (
                self.required_environment_digest,
                self.required_configuration_digest,
                self.required_protocol_contract_digest,
                self.required_product_contract_digest,
                self.required_expected_behavior_digest,
            )
        ) or not all(
            type(value) is bool
            for value in (
                self.environment_equivalence_required,
                self.configuration_equivalence_required,
                self.protocol_equivalence_required,
                self.product_behavior_equivalence_required,
                self.provenance_required,
                self.independent_review_required,
            )
        ):
            _raise()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "configuration_equivalence_required": self.configuration_equivalence_required,
                "criteria_id": self.criteria_id,
                "criteria_version": str(self.criteria_version),
                "environment_equivalence_required": self.environment_equivalence_required,
                "independent_review_required": self.independent_review_required,
                "product_behavior_equivalence_required": self.product_behavior_equivalence_required,
                "protocol_equivalence_required": self.protocol_equivalence_required,
                "provenance_required": self.provenance_required,
                "required_case_coverage": list(self.required_case_coverage),
                "required_configuration_digest": self.required_configuration_digest,
                "required_environment_digest": self.required_environment_digest,
                "required_evidence_kind": self.required_evidence_kind.value,
                "required_expected_behavior_digest": self.required_expected_behavior_digest,
                "required_product_contract_digest": self.required_product_contract_digest,
                "required_protocol_contract_digest": self.required_protocol_contract_digest,
            }
        )

    def __repr__(self) -> str:
        return "EquivalenceCriteria(<safe>)"


@dataclass(frozen=True, repr=False)
class EquivalenceEvidenceDescriptor:
    descriptor_id: str
    source_kind: EquivalenceEvidenceSourceKind
    source_validation_digest: str
    product_contract_digest: str
    protocol_contract_digest: str
    environment_descriptor_digest: str
    configuration_descriptor_digest: str
    test_case_coverage_digest: str
    provenance_digest: str
    evidence_created_at: datetime
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.descriptor_id) or not isinstance(
            self.source_kind, EquivalenceEvidenceSourceKind
        ) or not all(
            _is_digest(value)
            for value in (
                self.source_validation_digest,
                self.product_contract_digest,
                self.protocol_contract_digest,
                self.environment_descriptor_digest,
                self.configuration_descriptor_digest,
                self.test_case_coverage_digest,
                self.provenance_digest,
            )
        ) or not _is_aware(self.evidence_created_at):
            _raise()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "configuration_descriptor_digest": self.configuration_descriptor_digest,
                "descriptor_id": self.descriptor_id,
                "environment_descriptor_digest": self.environment_descriptor_digest,
                "evidence_created_at": _canonical_datetime(self.evidence_created_at),
                "product_contract_digest": self.product_contract_digest,
                "protocol_contract_digest": self.protocol_contract_digest,
                "provenance_digest": self.provenance_digest,
                "source_kind": self.source_kind.value,
                "source_validation_digest": self.source_validation_digest,
                "test_case_coverage_digest": self.test_case_coverage_digest,
            }
        )

    def __repr__(self) -> str:
        return "EquivalenceEvidenceDescriptor(<safe>)"


@dataclass(frozen=True)
class EnvironmentEquivalenceContract:
    environment_equivalence_id: str
    runtime_family: str
    runtime_version: SemanticVersion
    dependency_manifest_digest: str
    configuration_digest: str
    capability_set_digest: str
    isolation_mode: str
    network_policy: str
    filesystem_policy: str
    external_dependency_policy: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        identifiers = (
            self.environment_equivalence_id,
            self.runtime_family,
            self.isolation_mode,
            self.network_policy,
            self.filesystem_policy,
            self.external_dependency_policy,
        )
        if not all(_is_identifier(value) for value in identifiers) or not isinstance(
            self.runtime_version, SemanticVersion
        ) or not all(
            _is_digest(value)
            for value in (
                self.dependency_manifest_digest,
                self.configuration_digest,
                self.capability_set_digest,
            )
        ):
            _raise()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "capability_set_digest": self.capability_set_digest,
                "configuration_digest": self.configuration_digest,
                "dependency_manifest_digest": self.dependency_manifest_digest,
                "environment_equivalence_id": self.environment_equivalence_id,
                "external_dependency_policy": self.external_dependency_policy,
                "filesystem_policy": self.filesystem_policy,
                "isolation_mode": self.isolation_mode,
                "network_policy": self.network_policy,
                "runtime_family": self.runtime_family,
                "runtime_version": str(self.runtime_version),
            }
        )


@dataclass(frozen=True)
class ConfigurationEquivalence:
    profile_id: str
    profile_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    protocol_version: SemanticVersion
    feature_flags_digest: str
    limits_digest: str
    compatibility_contract_digest: str
    hidden_defaults_used: bool = False
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.profile_id) or not _is_identifier(self.product_id) or not all(
            isinstance(value, SemanticVersion)
            for value in (self.profile_version, self.product_version, self.protocol_version)
        ) or not all(
            _is_digest(value)
            for value in (
                self.feature_flags_digest,
                self.limits_digest,
                self.compatibility_contract_digest,
            )
        ) or type(self.hidden_defaults_used) is not bool:
            _raise()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "compatibility_contract_digest": self.compatibility_contract_digest,
                "feature_flags_digest": self.feature_flags_digest,
                "hidden_defaults_used": self.hidden_defaults_used,
                "limits_digest": self.limits_digest,
                "product_id": self.product_id,
                "product_version": str(self.product_version),
                "profile_id": self.profile_id,
                "profile_version": str(self.profile_version),
                "protocol_version": str(self.protocol_version),
            }
        )


@dataclass(frozen=True)
class ProductBehaviorEquivalence:
    required_case_ids: tuple[str, ...]
    observed_behavior_digest: str
    expected_behavior_digest: str
    failed_case_ids: tuple[str, ...] = ()
    skipped_case_ids: tuple[str, ...] = ()
    unresolved_divergence_count: int = 0
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        groups = (self.required_case_ids, self.failed_case_ids, self.skipped_case_ids)
        if any(
            not isinstance(group, tuple)
            or tuple(sorted(set(group))) != group
            or not all(_is_identifier(value) for value in group)
            for group in groups
        ) or not self.required_case_ids or not all(
            _is_digest(value)
            for value in (self.observed_behavior_digest, self.expected_behavior_digest)
        ) or type(self.unresolved_divergence_count) is not int or (
            self.unresolved_divergence_count < 0
        ):
            _raise()
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    @property
    def complete(self) -> bool:
        return (
            not self.failed_case_ids
            and not self.skipped_case_ids
            and self.unresolved_divergence_count == 0
            and self.observed_behavior_digest == self.expected_behavior_digest
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "expected_behavior_digest": self.expected_behavior_digest,
                "failed_case_ids": list(self.failed_case_ids),
                "observed_behavior_digest": self.observed_behavior_digest,
                "required_case_ids": list(self.required_case_ids),
                "skipped_case_ids": list(self.skipped_case_ids),
                "unresolved_divergence_count": self.unresolved_divergence_count,
            }
        )


@dataclass(frozen=True)
class EquivalenceAssessmentSafeSummary:
    assessment_request_id: str
    result: str
    reason_categories: tuple[str, ...]
    criteria_digest: str
    evidence_descriptor_digest: str
    evaluated_at: str
    required_case_count: int
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class EquivalenceAssessment:
    assessment_request_id: str
    request_digest: str
    criteria_digest: str
    evidence_descriptor_digest: str
    result: EquivalenceAssessmentResult
    reason_categories: tuple[EquivalenceAssessmentReason, ...]
    assessor_id: str
    independent_reviewer_id: str | None
    evaluated_at: datetime
    required_case_count: int
    write_count: int = field(init=False, default=0)
    mutation_count: int = field(init=False, default=0)
    persistence_count: int = field(init=False, default=0)
    filesystem_count: int = field(init=False, default=0)
    database_count: int = field(init=False, default=0)
    transport_count: int = field(init=False, default=0)
    http_count: int = field(init=False, default=0)
    activation_count: int = field(init=False, default=0)
    safe_summary: EquivalenceAssessmentSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not _is_identifier(self.assessment_request_id)
            or not _is_identifier(self.assessor_id)
            or not all(
                _is_digest(value)
                for value in (
                    self.request_digest,
                    self.criteria_digest,
                    self.evidence_descriptor_digest,
                )
            )
            or not isinstance(self.result, EquivalenceAssessmentResult)
            or not isinstance(self.reason_categories, tuple)
            or any(
                not isinstance(value, EquivalenceAssessmentReason)
                for value in self.reason_categories
            )
            or tuple(
                value for value in _REASON_ORDER if value in self.reason_categories
            )
            != self.reason_categories
            or not _is_aware(self.evaluated_at)
            or (
                self.independent_reviewer_id is not None
                and not _is_identifier(self.independent_reviewer_id)
            )
            or type(self.required_case_count) is not int
            or self.required_case_count < 1
        ):
            _raise()
        canonical = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", canonical)
        object.__setattr__(
            self,
            "safe_summary",
            EquivalenceAssessmentSafeSummary(
                assessment_request_id=self.assessment_request_id,
                result=self.result.value,
                reason_categories=tuple(value.value for value in self.reason_categories),
                criteria_digest=self.criteria_digest,
                evidence_descriptor_digest=self.evidence_descriptor_digest,
                evaluated_at=_canonical_datetime(self.evaluated_at),
                required_case_count=self.required_case_count,
                canonical_digest=canonical,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "assessment_request_id": self.assessment_request_id,
                "assessor_id": self.assessor_id,
                "criteria_digest": self.criteria_digest,
                "evaluated_at": _canonical_datetime(self.evaluated_at),
                "evidence_descriptor_digest": self.evidence_descriptor_digest,
                "reason_categories": [value.value for value in self.reason_categories],
                "request_digest": self.request_digest,
                "independent_reviewer_id": self.independent_reviewer_id,
                "required_case_count": self.required_case_count,
                "result": self.result.value,
            }
        )

    def __repr__(self) -> str:
        return "EquivalenceAssessment(<safe>)"


def canonical_case_coverage_digest(case_ids: tuple[str, ...]) -> str:
    if (
        not isinstance(case_ids, tuple)
        or not case_ids
        or tuple(sorted(set(case_ids))) != case_ids
        or not all(_is_identifier(value) for value in case_ids)
    ):
        _raise("production_equivalence_coverage_invalid")
    return _digest(_canonical_json({"case_ids": list(case_ids)}))


def evaluate_production_equivalence(
    *,
    request: ProductionEquivalenceAssessmentRequest,
    criteria: EquivalenceCriteria,
    descriptor: EquivalenceEvidenceDescriptor,
    environment: EnvironmentEquivalenceContract,
    configuration: ConfigurationEquivalence,
    behavior: ProductBehaviorEquivalence,
    manual_validation_plan: ManualValidationPlan,
    manual_validation_chain: ManualValidationChain,
    evaluation_time: datetime,
    independent_reviewer_id: str | None = None,
    used_request_ids: frozenset[str] = frozenset(),
    used_assessment_digests: frozenset[str] = frozenset(),
    used_descriptor_digests: frozenset[str] = frozenset(),
) -> EquivalenceAssessment:
    values = (request, criteria, descriptor, environment, configuration, behavior)
    if not isinstance(request, ProductionEquivalenceAssessmentRequest) or not isinstance(
        criteria, EquivalenceCriteria
    ) or not isinstance(descriptor, EquivalenceEvidenceDescriptor) or not isinstance(
        environment, EnvironmentEquivalenceContract
    ) or not isinstance(configuration, ConfigurationEquivalence) or not isinstance(
        behavior, ProductBehaviorEquivalence
    ) or not isinstance(manual_validation_plan, ManualValidationPlan) or not isinstance(
        manual_validation_chain, ManualValidationChain
    ) or not _is_aware(evaluation_time) or any(
        not isinstance(value, frozenset) for value in (
            used_request_ids,
            used_assessment_digests,
            used_descriptor_digests,
        )
    ):
        _raise()
    del values
    reasons: set[EquivalenceAssessmentReason] = set()
    try:
        manual_validation_chain.validate(
            plan=manual_validation_plan, evaluation_time=evaluation_time
        )
    except ValueError:
        reasons.add(EquivalenceAssessmentReason.MANUAL_VALIDATION_INVALID)
    if not manual_validation_chain.approved:
        reasons.add(EquivalenceAssessmentReason.MANUAL_VALIDATION_INVALID)
    if not _manual_source_matches(request, manual_validation_plan, manual_validation_chain):
        reasons.add(EquivalenceAssessmentReason.DIGEST_MISMATCH)
    if not _identity_matches(request, manual_validation_plan, configuration):
        reasons.add(EquivalenceAssessmentReason.IDENTITY_MISMATCH)
    if any(
        (
            request.use_current_alias,
            request.use_latest_alias,
            request.allow_fallback,
            request.allow_nearest_version,
            request.allow_version_inference,
            configuration.hidden_defaults_used,
        )
    ):
        reasons.add(EquivalenceAssessmentReason.UNSAFE_SELECTION)
    if request.assessor_id in _manual_actors(manual_validation_chain):
        reasons.add(EquivalenceAssessmentReason.ROLE_CONFLICT)
    if not (
        manual_validation_chain.approval is not None
        and manual_validation_chain.approval.approved_at
        <= request.requested_at
        <= descriptor.evidence_created_at
        <= evaluation_time
    ):
        reasons.add(EquivalenceAssessmentReason.TEMPORAL_INVALID)
    if evaluation_time > manual_validation_plan.execution_window_end:
        reasons.add(EquivalenceAssessmentReason.EXPIRED_PLAN)
    if evaluation_time - descriptor.evidence_created_at > MAX_EQUIVALENCE_EVIDENCE_AGE:
        reasons.add(EquivalenceAssessmentReason.STALE_EVIDENCE)
    if request.assessment_request_id in used_request_ids or (
        descriptor.canonical_digest in used_descriptor_digests
    ):
        reasons.add(EquivalenceAssessmentReason.REPLAY)
    if descriptor.source_kind is not criteria.required_evidence_kind or (
        descriptor.source_kind
        is not EquivalenceEvidenceSourceKind.PRODUCTION_EQUIVALENT_CANDIDATE
    ):
        reasons.add(EquivalenceAssessmentReason.PRODUCT_BEHAVIOR_EQUIVALENCE_REQUIRED)
    if descriptor.source_validation_digest != request.manual_validation_approval_digest:
        reasons.add(EquivalenceAssessmentReason.DIGEST_MISMATCH)
    if descriptor.environment_descriptor_digest != environment.canonical_digest or (
        environment.canonical_digest != criteria.required_environment_digest
    ):
        reasons.add(EquivalenceAssessmentReason.ENVIRONMENT_EQUIVALENCE_REQUIRED)
    if descriptor.configuration_descriptor_digest != configuration.canonical_digest or (
        configuration.canonical_digest != criteria.required_configuration_digest
    ):
        reasons.add(EquivalenceAssessmentReason.CONFIGURATION_EQUIVALENCE_REQUIRED)
    if descriptor.protocol_contract_digest != criteria.required_protocol_contract_digest:
        reasons.add(EquivalenceAssessmentReason.PROTOCOL_EQUIVALENCE_REQUIRED)
    if descriptor.product_contract_digest != criteria.required_product_contract_digest:
        reasons.add(EquivalenceAssessmentReason.PRODUCT_BEHAVIOR_EQUIVALENCE_REQUIRED)
    if (
        descriptor.test_case_coverage_digest
        != canonical_case_coverage_digest(criteria.required_case_coverage)
        or behavior.required_case_ids != criteria.required_case_coverage
        or behavior.expected_behavior_digest
        != criteria.required_expected_behavior_digest
        or not behavior.complete
    ):
        reasons.add(EquivalenceAssessmentReason.PRODUCT_BEHAVIOR_EQUIVALENCE_REQUIRED)
    if not _is_digest(descriptor.provenance_digest):
        reasons.add(EquivalenceAssessmentReason.DIGEST_MISMATCH)
    if criteria.independent_review_required and independent_reviewer_id is None:
        reasons.add(EquivalenceAssessmentReason.INDEPENDENT_REVIEW_REQUIRED)
    elif independent_reviewer_id is not None and (
        not _is_identifier(independent_reviewer_id)
        or independent_reviewer_id == request.assessor_id
        or independent_reviewer_id in _manual_actors(manual_validation_chain)
    ):
        reasons.add(EquivalenceAssessmentReason.ROLE_CONFLICT)

    result = _assessment_result(reasons)
    ordered = tuple(value for value in _REASON_ORDER if value in reasons)
    assessment = EquivalenceAssessment(
        assessment_request_id=request.assessment_request_id,
        request_digest=request.canonical_digest,
        criteria_digest=criteria.canonical_digest,
        evidence_descriptor_digest=descriptor.canonical_digest,
        result=result,
        reason_categories=ordered,
        assessor_id=request.assessor_id,
        independent_reviewer_id=independent_reviewer_id,
        evaluated_at=evaluation_time,
        required_case_count=len(criteria.required_case_coverage),
    )
    if assessment.canonical_digest in used_assessment_digests:
        reasons.add(EquivalenceAssessmentReason.REPLAY)
        ordered = tuple(value for value in _REASON_ORDER if value in reasons)
        assessment = EquivalenceAssessment(
            assessment_request_id=request.assessment_request_id,
            request_digest=request.canonical_digest,
            criteria_digest=criteria.canonical_digest,
            evidence_descriptor_digest=descriptor.canonical_digest,
            result=EquivalenceAssessmentResult.INELIGIBLE,
            reason_categories=ordered,
            assessor_id=request.assessor_id,
            independent_reviewer_id=independent_reviewer_id,
            evaluated_at=evaluation_time,
            required_case_count=len(criteria.required_case_coverage),
        )
    return assessment


def _assessment_result(reasons: set[EquivalenceAssessmentReason]) -> EquivalenceAssessmentResult:
    if reasons & _INELIGIBLE_REASONS:
        return EquivalenceAssessmentResult.INELIGIBLE
    priority = (
        (
            EquivalenceAssessmentReason.ENVIRONMENT_EQUIVALENCE_REQUIRED,
            EquivalenceAssessmentResult.NEEDS_ENVIRONMENT_EQUIVALENCE,
        ),
        (
            EquivalenceAssessmentReason.CONFIGURATION_EQUIVALENCE_REQUIRED,
            EquivalenceAssessmentResult.NEEDS_CONFIGURATION_EQUIVALENCE,
        ),
        (
            EquivalenceAssessmentReason.PROTOCOL_EQUIVALENCE_REQUIRED,
            EquivalenceAssessmentResult.NEEDS_PROTOCOL_EQUIVALENCE,
        ),
        (
            EquivalenceAssessmentReason.PRODUCT_BEHAVIOR_EQUIVALENCE_REQUIRED,
            EquivalenceAssessmentResult.NEEDS_PRODUCT_BEHAVIOR_EQUIVALENCE,
        ),
        (
            EquivalenceAssessmentReason.INDEPENDENT_REVIEW_REQUIRED,
            EquivalenceAssessmentResult.NEEDS_INDEPENDENT_REVIEW,
        ),
    )
    for reason, result in priority:
        if reason in reasons:
            return result
    return EquivalenceAssessmentResult.ELIGIBLE_FOR_EQUIVALENCE_REVIEW


def _manual_source_matches(
    request: ProductionEquivalenceAssessmentRequest,
    plan: ManualValidationPlan,
    chain: ManualValidationChain,
) -> bool:
    return bool(
        chain.approval is not None
        and request.validation_plan_digest == plan.canonical_digest
        and request.execution_record_digest == chain.execution_record.canonical_digest
        and request.manual_validation_evidence_digest == chain.evidence.canonical_digest
        and request.manual_validation_approval_digest == chain.approval.canonical_digest
        and request.fixture_manifest_digest == chain.fixture_manifest.canonical_digest
        and request.environment_contract_digest == chain.environment.canonical_digest
        and request.validation_operator_id == chain.request.execution_operator_id
        and chain.review is not None
        and request.validation_reviewer_id == chain.review.reviewer_id
        and request.manual_validation_approver_id == chain.approval.approver_id
    )


def _identity_matches(
    request: ProductionEquivalenceAssessmentRequest,
    plan: ManualValidationPlan,
    configuration: ConfigurationEquivalence,
) -> bool:
    return all(
        (
            request.profile_id == plan.profile_id == configuration.profile_id,
            request.profile_version == plan.profile_version == configuration.profile_version,
            request.product_id == plan.product_id == configuration.product_id,
            request.product_version == plan.product_version == configuration.product_version,
            request.protocol_version == plan.protocol_version == configuration.protocol_version,
        )
    )


def _manual_actors(chain: ManualValidationChain) -> set[str]:
    values = {
        chain.request.requested_by,
        chain.request.execution_operator_id,
        chain.evidence.created_by,
    }
    if chain.review is not None:
        values.add(chain.review.reviewer_id)
    if chain.approval is not None:
        values.add(chain.approval.approver_id)
    return values


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _raise(category: str = "production_equivalence_contract_invalid") -> None:
    raise ProductionEquivalenceError(category)
