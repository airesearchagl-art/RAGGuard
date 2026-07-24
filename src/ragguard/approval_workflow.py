from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from ragguard.compatibility import (
    CompatibilityErrorCategory,
    ScoreSemantics,
    SemanticVersion,
    SourceIdentifierPolicy,
    compatibility_error,
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
    ApprovalDecision,
    ApprovalMetadata,
    ApprovalRestrictions,
    ProfileMaturity,
    SupportedProductVersionRange,
)
from ragguard.retrieval import RetrievalAdapterError
from ragguard.validation_report import (
    VALIDATION_REPORT_CASE_IDS,
    ValidationCaseOutcome,
    ValidationCaseResult,
    ValidationCheckResult,
    ValidationEnvironmentClass,
    ValidationOverallStatus,
    ValidationReport,
    ValidationType,
)


_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_SAFE_ERROR_CATEGORIES = frozenset(
    category.value for category in CompatibilityErrorCategory
)
_REQUIRED_CAPABILITIES = frozenset(
    {
        "retrieval",
        "bounded_top_k",
        "deterministic_result_schema",
        "safe_source_identifier",
        "response_size_compliance",
    }
)
_OPTIONAL_CAPABILITIES = frozenset(
    {"score", "title", "matched_keywords", "query_id_echo", "protocol_version_echo"}
)
_CAPABILITIES = _REQUIRED_CAPABILITIES | _OPTIONAL_CAPABILITIES


class ApprovalWorkflowStage(str, Enum):
    INPUT_VALIDATED = "input_validated"
    VALIDATION_REPORT_BUILT = "validation_report_built"
    VALIDATION_REPORT_VALIDATED = "validation_report_validated"
    APPROVAL_DECISION_EVALUATED = "approval_decision_evaluated"
    APPROVAL_METADATA_BUILT = "approval_metadata_built"
    REGISTRATION_ELIGIBILITY_EVALUATED = (
        "registration_eligibility_evaluated"
    )
    REGISTRY_REGISTERED = "registry_registered"
    REGISTRY_RESOLVED = "registry_resolved"
    RESULT_BUILT = "result_built"


@dataclass(frozen=True, repr=False)
class SyntheticCaseEvidence:
    case_id: str
    outcome: ValidationCaseOutcome
    safe_error_category: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.case_id, str)
            or self.case_id not in VALIDATION_REPORT_CASE_IDS
            or not isinstance(self.outcome, ValidationCaseOutcome)
            or (
                self.safe_error_category is not None
                and self.safe_error_category not in _SAFE_ERROR_CATEGORIES
            )
            or (
                self.outcome is ValidationCaseOutcome.FAILED
                and self.safe_error_category is None
            )
            or (
                self.outcome is not ValidationCaseOutcome.FAILED
                and self.safe_error_category is not None
            )
        ):
            _invalid()

    @classmethod
    def from_mapping(cls, value: object) -> SyntheticCaseEvidence:
        fields = {"case_id", "outcome", "safe_error_category"}
        if not isinstance(value, Mapping) or set(value) != fields:
            _invalid()
        return cls(
            case_id=value["case_id"],
            outcome=_enum(ValidationCaseOutcome, value["outcome"]),
            safe_error_category=value["safe_error_category"],
        )

    def __repr__(self) -> str:
        return "SyntheticCaseEvidence(<safe>)"


@dataclass(frozen=True, repr=False)
class SyntheticApprovalWorkflowInput:
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    normalized_product_version: SemanticVersion
    maturity: ProfileMaturity
    validation_record_id: str
    approval_record_id: str
    reviewer_id: str
    approver_id: str
    case_outcomes: tuple[SyntheticCaseEvidence, ...]
    required_capabilities_result: ValidationCheckResult
    optional_capabilities_result: ValidationCheckResult
    score_semantics_result: ValidationCheckResult
    source_policy_result: ValidationCheckResult
    transport_boundary_result: ValidationCheckResult
    non_disclosure_result: ValidationCheckResult
    approved_capabilities: tuple[str, ...]
    approved_score_semantics: ScoreSemantics
    approved_source_identifier_policy: SourceIdentifierPolicy
    supported_product_version_range: SupportedProductVersionRange
    restrictions: ApprovalRestrictions | None
    validation_started_at: datetime
    validation_completed_at: datetime
    validation_expires_at: datetime | None
    validation_status: ValidationOverallStatus
    revalidation_required: bool
    approval_at: datetime
    approval_expires_at: datetime | None
    evaluation_time: datetime
    registry_kind: RegistryKind
    registry_status_before_resolve: RegistryStatus

    def __post_init__(self) -> None:
        if (
            not all(
                _safe_identifier(value)
                for value in (
                    self.profile_id,
                    self.validation_record_id,
                    self.approval_record_id,
                    self.reviewer_id,
                    self.approver_id,
                )
            )
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.profile_version,
                    self.protocol_version,
                    self.normalized_product_version,
                )
            )
            or not isinstance(self.maturity, ProfileMaturity)
            or not isinstance(self.case_outcomes, tuple)
            or any(
                not isinstance(value, SyntheticCaseEvidence)
                for value in self.case_outcomes
            )
            or not all(
                isinstance(value, ValidationCheckResult)
                for value in (
                    self.required_capabilities_result,
                    self.optional_capabilities_result,
                    self.score_semantics_result,
                    self.source_policy_result,
                    self.transport_boundary_result,
                    self.non_disclosure_result,
                )
            )
            or not _canonical_capabilities(self.approved_capabilities)
            or not isinstance(self.approved_score_semantics, ScoreSemantics)
            or not isinstance(
                self.approved_source_identifier_policy,
                SourceIdentifierPolicy,
            )
            or not isinstance(
                self.supported_product_version_range,
                SupportedProductVersionRange,
            )
            or (
                self.restrictions is not None
                and not isinstance(self.restrictions, ApprovalRestrictions)
            )
            or not isinstance(self.validation_status, ValidationOverallStatus)
            or type(self.revalidation_required) is not bool
            or not isinstance(self.registry_kind, RegistryKind)
            or not isinstance(
                self.registry_status_before_resolve, RegistryStatus
            )
        ):
            _invalid()
        for value in (
            self.validation_started_at,
            self.validation_completed_at,
            self.validation_expires_at,
            self.approval_at,
            self.approval_expires_at,
            self.evaluation_time,
        ):
            _validate_datetime(value, optional=value is None)
        if (
            self.validation_completed_at < self.validation_started_at
            or self.approval_at < self.validation_completed_at
        ):
            _invalid()

    @classmethod
    def from_mapping(cls, value: object) -> SyntheticApprovalWorkflowInput:
        fields = {
            "profile_id",
            "profile_version",
            "protocol_version",
            "normalized_product_version",
            "maturity",
            "validation_record_id",
            "approval_record_id",
            "reviewer_id",
            "approver_id",
            "case_outcomes",
            "required_capabilities_result",
            "optional_capabilities_result",
            "score_semantics_result",
            "source_policy_result",
            "transport_boundary_result",
            "non_disclosure_result",
            "approved_capabilities",
            "approved_score_semantics",
            "approved_source_identifier_policy",
            "supported_product_version_range",
            "restrictions",
            "validation_started_at",
            "validation_completed_at",
            "validation_expires_at",
            "validation_status",
            "revalidation_required",
            "approval_at",
            "approval_expires_at",
            "evaluation_time",
            "registry_kind",
            "registry_status_before_resolve",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            _invalid()
        raw_cases = value["case_outcomes"]
        if not isinstance(raw_cases, (list, tuple)):
            _invalid()
        restrictions = value["restrictions"]
        try:
            return cls(
                profile_id=value["profile_id"],
                profile_version=_version(value["profile_version"]),
                protocol_version=_version(value["protocol_version"]),
                normalized_product_version=_version(
                    value["normalized_product_version"]
                ),
                maturity=_enum(ProfileMaturity, value["maturity"]),
                validation_record_id=value["validation_record_id"],
                approval_record_id=value["approval_record_id"],
                reviewer_id=value["reviewer_id"],
                approver_id=value["approver_id"],
                case_outcomes=tuple(
                    SyntheticCaseEvidence.from_mapping(case)
                    for case in raw_cases
                ),
                required_capabilities_result=_enum(
                    ValidationCheckResult,
                    value["required_capabilities_result"],
                ),
                optional_capabilities_result=_enum(
                    ValidationCheckResult,
                    value["optional_capabilities_result"],
                ),
                score_semantics_result=_enum(
                    ValidationCheckResult,
                    value["score_semantics_result"],
                ),
                source_policy_result=_enum(
                    ValidationCheckResult,
                    value["source_policy_result"],
                ),
                transport_boundary_result=_enum(
                    ValidationCheckResult,
                    value["transport_boundary_result"],
                ),
                non_disclosure_result=_enum(
                    ValidationCheckResult,
                    value["non_disclosure_result"],
                ),
                approved_capabilities=_tuple(
                    value["approved_capabilities"]
                ),
                approved_score_semantics=_enum(
                    ScoreSemantics, value["approved_score_semantics"]
                ),
                approved_source_identifier_policy=_enum(
                    SourceIdentifierPolicy,
                    value["approved_source_identifier_policy"],
                ),
                supported_product_version_range=(
                    SupportedProductVersionRange.from_mapping(
                        value["supported_product_version_range"]
                    )
                ),
                restrictions=(
                    None
                    if restrictions is None
                    else ApprovalRestrictions.from_mapping(restrictions)
                ),
                validation_started_at=_parse_datetime(
                    value["validation_started_at"]
                ),
                validation_completed_at=_parse_datetime(
                    value["validation_completed_at"]
                ),
                validation_expires_at=_parse_datetime(
                    value["validation_expires_at"], optional=True
                ),
                validation_status=_enum(
                    ValidationOverallStatus, value["validation_status"]
                ),
                revalidation_required=value["revalidation_required"],
                approval_at=_parse_datetime(value["approval_at"]),
                approval_expires_at=_parse_datetime(
                    value["approval_expires_at"], optional=True
                ),
                evaluation_time=_parse_datetime(value["evaluation_time"]),
                registry_kind=_enum(RegistryKind, value["registry_kind"]),
                registry_status_before_resolve=_enum(
                    RegistryStatus,
                    value["registry_status_before_resolve"],
                ),
            )
        except RetrievalAdapterError:
            _invalid()

    def __repr__(self) -> str:
        return "SyntheticApprovalWorkflowInput(<safe>)"


@dataclass(frozen=True)
class SyntheticApprovalWorkflowResult:
    profile_id: str
    profile_version: str
    validation_status: str
    approval_decision: str
    registration_eligible: bool
    registry_status: str
    exact_resolve_success: bool
    restriction_present: bool
    revalidation_required: bool
    safe_error_category: str | None
    completed_stage: str
    case_counts: tuple[tuple[str, int], ...]
    event_categories: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _safe_identifier(self.profile_id)
            or not isinstance(self.profile_version, str)
            or self.validation_status
            not in {status.value for status in ValidationOverallStatus}
            | {"unavailable"}
            or self.approval_decision
            not in {decision.value for decision in ApprovalDecision}
            | {"unavailable"}
            or type(self.registration_eligible) is not bool
            or self.registry_status
            not in {status.value for status in RegistryStatus}
            | {"unavailable"}
            or type(self.exact_resolve_success) is not bool
            or type(self.restriction_present) is not bool
            or type(self.revalidation_required) is not bool
            or (
                self.safe_error_category is not None
                and self.safe_error_category not in _SAFE_ERROR_CATEGORIES
            )
            or self.completed_stage
            not in {stage.value for stage in ApprovalWorkflowStage}
            or not _canonical_counts(self.case_counts)
            or not isinstance(self.event_categories, tuple)
            or any(
                value not in {event.value for event in RegistryEventCategory}
                for value in self.event_categories
            )
        ):
            _invalid()

    def as_mapping(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "profile_id": self.profile_id,
                "profile_version": self.profile_version,
                "validation_status": self.validation_status,
                "approval_decision": self.approval_decision,
                "registration_eligible": self.registration_eligible,
                "registry_status": self.registry_status,
                "exact_resolve_success": self.exact_resolve_success,
                "restriction_present": self.restriction_present,
                "revalidation_required": self.revalidation_required,
                "safe_error_category": self.safe_error_category,
                "completed_stage": self.completed_stage,
                "case_counts": dict(self.case_counts),
                "event_categories": self.event_categories,
            }
        )


def build_all_pass_synthetic_input(
    *,
    evaluation_time: datetime,
) -> SyntheticApprovalWorkflowInput:
    _validate_datetime(evaluation_time)
    started = evaluation_time - timedelta(minutes=10)
    completed = evaluation_time - timedelta(minutes=9)
    approval_at = evaluation_time - timedelta(minutes=8)
    return SyntheticApprovalWorkflowInput(
        profile_id="synthetic-approval-profile",
        profile_version=SemanticVersion.parse("1.0.0"),
        protocol_version=SemanticVersion.parse("1.0.0"),
        normalized_product_version=SemanticVersion.parse("1.3.2"),
        maturity=ProfileMaturity.APPROVED,
        validation_record_id="synthetic-validation-001",
        approval_record_id="synthetic-approval-001",
        reviewer_id="synthetic-reviewer",
        approver_id="synthetic-approver",
        case_outcomes=tuple(
            SyntheticCaseEvidence(
                case_id=case_id,
                outcome=ValidationCaseOutcome.PASSED,
            )
            for case_id in sorted(VALIDATION_REPORT_CASE_IDS)
        ),
        required_capabilities_result=ValidationCheckResult.PASSED,
        optional_capabilities_result=ValidationCheckResult.PASSED,
        score_semantics_result=ValidationCheckResult.PASSED,
        source_policy_result=ValidationCheckResult.PASSED,
        transport_boundary_result=ValidationCheckResult.PASSED,
        non_disclosure_result=ValidationCheckResult.PASSED,
        approved_capabilities=tuple(sorted(_REQUIRED_CAPABILITIES)),
        approved_score_semantics=ScoreSemantics.UNSCORED,
        approved_source_identifier_policy=(
            SourceIdentifierPolicy.OPAQUE_SAFE_ID
        ),
        supported_product_version_range=SupportedProductVersionRange(
            minimum_version=SemanticVersion.parse("1.2.0"),
            maximum_version=SemanticVersion.parse("1.4.9"),
            open_ended=False,
        ),
        restrictions=None,
        validation_started_at=started,
        validation_completed_at=completed,
        validation_expires_at=evaluation_time + timedelta(days=30),
        validation_status=ValidationOverallStatus.PASSED,
        revalidation_required=False,
        approval_at=approval_at,
        approval_expires_at=evaluation_time + timedelta(days=365),
        evaluation_time=evaluation_time,
        registry_kind=RegistryKind.TEST,
        registry_status_before_resolve=RegistryStatus.ACTIVE,
    )


def build_synthetic_validation_report(
    workflow_input: SyntheticApprovalWorkflowInput,
) -> ValidationReport:
    _require_input(workflow_input)
    cases = tuple(
        ValidationCaseResult(
            case_id=evidence.case_id,
            outcome=evidence.outcome,
            safe_error_category=evidence.safe_error_category,
            bounded_duration_ms=0,
            result_count=0,
            required=True,
            notes_code=(
                "expected_rejection"
                if evidence.outcome is ValidationCaseOutcome.FAILED
                else (
                    "not_executed"
                    if evidence.outcome
                    in {
                        ValidationCaseOutcome.SKIPPED,
                        ValidationCaseOutcome.NOT_APPLICABLE,
                    }
                    else "none"
                )
            ),
        )
        for evidence in workflow_input.case_outcomes
    )
    return ValidationReport(
        validation_record_id=workflow_input.validation_record_id,
        profile_id=workflow_input.profile_id,
        profile_version=workflow_input.profile_version,
        protocol_version=workflow_input.protocol_version,
        normalized_product_version=workflow_input.normalized_product_version,
        validation_type=ValidationType.SYNTHETIC,
        started_at=workflow_input.validation_started_at,
        completed_at=workflow_input.validation_completed_at,
        environment_class=ValidationEnvironmentClass.SYNTHETIC_HARNESS,
        case_results=cases,
        required_capabilities_result=(
            workflow_input.required_capabilities_result
        ),
        optional_capabilities_result=(
            workflow_input.optional_capabilities_result
        ),
        score_semantics_result=workflow_input.score_semantics_result,
        source_policy_result=workflow_input.source_policy_result,
        transport_boundary_result=workflow_input.transport_boundary_result,
        non_disclosure_result=workflow_input.non_disclosure_result,
        overall_status=workflow_input.validation_status,
        revalidation_required=workflow_input.revalidation_required,
        safe_error_categories=tuple(
            sorted(
                {
                    evidence.safe_error_category
                    for evidence in workflow_input.case_outcomes
                    if evidence.safe_error_category is not None
                }
            )
        ),
        expires_at=workflow_input.validation_expires_at,
    )


def validate_synthetic_validation_report(
    workflow_input: SyntheticApprovalWorkflowInput,
    report: ValidationReport,
) -> None:
    _require_input(workflow_input)
    expected = build_synthetic_validation_report(workflow_input)
    if (
        not isinstance(report, ValidationReport)
        or report != expected
        or report.validation_type is not ValidationType.SYNTHETIC
        or report.profile_id != workflow_input.profile_id
        or report.profile_version != workflow_input.profile_version
        or report.protocol_version != workflow_input.protocol_version
        or report.normalized_product_version
        != workflow_input.normalized_product_version
        or report.validation_record_id
        != workflow_input.validation_record_id
    ):
        _invalid()


def evaluate_synthetic_approval_decision(
    workflow_input: SyntheticApprovalWorkflowInput,
    report: ValidationReport,
) -> ApprovalDecision:
    validate_synthetic_validation_report(workflow_input, report)
    if (
        report.revalidation_required
        or report.overall_status is ValidationOverallStatus.EXPIRED
        or (
            report.expires_at is not None
            and workflow_input.evaluation_time >= report.expires_at
        )
    ):
        return ApprovalDecision.NEEDS_REVALIDATION
    if (
        workflow_input.maturity is not ProfileMaturity.APPROVED
        or report.overall_status is not ValidationOverallStatus.PASSED
        or report.required_capabilities_result
        is not ValidationCheckResult.PASSED
        or report.score_semantics_result is not ValidationCheckResult.PASSED
        or report.source_policy_result is not ValidationCheckResult.PASSED
        or report.transport_boundary_result
        is not ValidationCheckResult.PASSED
        or report.non_disclosure_result
        is not ValidationCheckResult.PASSED
    ):
        return ApprovalDecision.REJECTED
    if report.optional_capabilities_result is ValidationCheckResult.FAILED:
        return (
            ApprovalDecision.APPROVED_WITH_RESTRICTIONS
            if workflow_input.restrictions is not None
            else ApprovalDecision.REJECTED
        )
    if workflow_input.restrictions is not None:
        return ApprovalDecision.APPROVED_WITH_RESTRICTIONS
    return ApprovalDecision.APPROVED


def build_synthetic_approval_metadata(
    workflow_input: SyntheticApprovalWorkflowInput,
    report: ValidationReport,
    decision: ApprovalDecision,
) -> ApprovalMetadata:
    validate_synthetic_validation_report(workflow_input, report)
    if not isinstance(decision, ApprovalDecision):
        _invalid()
    if decision is not evaluate_synthetic_approval_decision(
        workflow_input, report
    ):
        _invalid()
    return ApprovalMetadata(
        approval_record_id=workflow_input.approval_record_id,
        reviewer_id=workflow_input.reviewer_id,
        approver_id=workflow_input.approver_id,
        decision=decision,
        approved_at=workflow_input.approval_at,
        validation_record_id=report.validation_record_id,
        supported_product_version_range=(
            workflow_input.supported_product_version_range
        ),
        approved_capabilities=workflow_input.approved_capabilities,
        approved_score_semantics=workflow_input.approved_score_semantics,
        approved_source_identifier_policy=(
            workflow_input.approved_source_identifier_policy
        ),
        restrictions=workflow_input.restrictions,
        expires_at=workflow_input.approval_expires_at,
    )


def run_synthetic_approval_workflow(
    workflow_input: SyntheticApprovalWorkflowInput,
) -> SyntheticApprovalWorkflowResult:
    _require_input(workflow_input)
    stage = ApprovalWorkflowStage.INPUT_VALIDATED
    report: ValidationReport | None = None
    decision: ApprovalDecision | None = None
    registration_eligible = False
    registry: TrustedProductionRegistry | None = None
    registry_status = "unavailable"
    try:
        report = build_synthetic_validation_report(workflow_input)
        stage = ApprovalWorkflowStage.VALIDATION_REPORT_BUILT
        validate_synthetic_validation_report(workflow_input, report)
        stage = ApprovalWorkflowStage.VALIDATION_REPORT_VALIDATED
        decision = evaluate_synthetic_approval_decision(
            workflow_input, report
        )
        stage = ApprovalWorkflowStage.APPROVAL_DECISION_EVALUATED
        approval = build_synthetic_approval_metadata(
            workflow_input, report, decision
        )
        stage = ApprovalWorkflowStage.APPROVAL_METADATA_BUILT
        entry = RegistryEntry.from_evidence(
            profile_id=workflow_input.profile_id,
            profile_version=workflow_input.profile_version,
            maturity=workflow_input.maturity,
            approval_metadata=approval,
            validation_report=report,
            registry_kind=workflow_input.registry_kind,
            registered_at=workflow_input.evaluation_time,
        )
        validate_registration_eligibility(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=workflow_input.evaluation_time,
        )
        _require_production_admission_rejected(
            workflow_input, approval, report
        )
        registration_eligible = True
        stage = ApprovalWorkflowStage.REGISTRATION_ELIGIBILITY_EVALUATED
        if workflow_input.registry_kind is not RegistryKind.TEST:
            raise compatibility_error(
                CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
            )
        registry = TrustedProductionRegistry(kind=RegistryKind.TEST)
        registry.register(
            entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=workflow_input.evaluation_time,
        )
        registry_status = RegistryStatus.ACTIVE.value
        stage = ApprovalWorkflowStage.REGISTRY_REGISTERED
        _apply_pre_resolution_status(
            registry,
            workflow_input.profile_id,
            workflow_input.profile_version,
            workflow_input.registry_status_before_resolve,
        )
        registry_status = workflow_input.registry_status_before_resolve.value
        registry.resolve(
            profile_id=workflow_input.profile_id,
            profile_version=workflow_input.profile_version,
            normalized_product_version=(
                workflow_input.normalized_product_version
            ),
            evaluation_time=workflow_input.evaluation_time,
        )
        stage = ApprovalWorkflowStage.REGISTRY_RESOLVED
    except RetrievalAdapterError as error:
        return _result(
            workflow_input,
            report=report,
            decision=decision,
            registration_eligible=registration_eligible,
            registry_status=registry_status,
            exact_resolve_success=False,
            safe_error_category=_safe_error(error),
            completed_stage=stage,
            registry=registry,
        )
    return _result(
        workflow_input,
        report=report,
        decision=decision,
        registration_eligible=True,
        registry_status=registry_status,
        exact_resolve_success=True,
        safe_error_category=None,
        completed_stage=ApprovalWorkflowStage.RESULT_BUILT,
        registry=registry,
    )


def _require_production_admission_rejected(
    workflow_input: SyntheticApprovalWorkflowInput,
    approval: ApprovalMetadata,
    report: ValidationReport,
) -> None:
    production_entry = RegistryEntry.from_evidence(
        profile_id=workflow_input.profile_id,
        profile_version=workflow_input.profile_version,
        maturity=workflow_input.maturity,
        approval_metadata=approval,
        validation_report=report,
        registry_kind=RegistryKind.PRODUCTION,
        registered_at=workflow_input.evaluation_time,
    )
    try:
        validate_registration_eligibility(
            production_entry,
            approval_metadata=approval,
            validation_report=report,
            evaluation_time=workflow_input.evaluation_time,
        )
    except RetrievalAdapterError as error:
        if str(error) != CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH.value:
            raise
        return
    raise compatibility_error(
        CompatibilityErrorCategory.REGISTRY_KIND_MISMATCH
    )


def _apply_pre_resolution_status(
    registry: TrustedProductionRegistry,
    profile_id: str,
    profile_version: SemanticVersion,
    status: RegistryStatus,
) -> None:
    if status is RegistryStatus.ACTIVE:
        return
    operation = {
        RegistryStatus.SUSPENDED: registry.suspend,
        RegistryStatus.DEPRECATED: registry.deprecate,
        RegistryStatus.REVOKED: registry.revoke,
    }[status]
    operation(profile_id, profile_version)


def _result(
    workflow_input: SyntheticApprovalWorkflowInput,
    *,
    report: ValidationReport | None,
    decision: ApprovalDecision | None,
    registration_eligible: bool,
    registry_status: str,
    exact_resolve_success: bool,
    safe_error_category: str | None,
    completed_stage: ApprovalWorkflowStage,
    registry: TrustedProductionRegistry | None,
) -> SyntheticApprovalWorkflowResult:
    case_counts = tuple(
        (
            outcome.value,
            sum(
                evidence.outcome is outcome
                for evidence in workflow_input.case_outcomes
            ),
        )
        for outcome in ValidationCaseOutcome
    )
    events = (
        tuple(event.category.value for event in registry.events)
        if registry is not None
        else ()
    )
    return SyntheticApprovalWorkflowResult(
        profile_id=workflow_input.profile_id,
        profile_version=str(workflow_input.profile_version),
        validation_status=(
            report.overall_status.value if report is not None else "unavailable"
        ),
        approval_decision=(
            decision.value if decision is not None else "unavailable"
        ),
        registration_eligible=registration_eligible,
        registry_status=registry_status,
        exact_resolve_success=exact_resolve_success,
        restriction_present=workflow_input.restrictions is not None,
        revalidation_required=workflow_input.revalidation_required,
        safe_error_category=safe_error_category,
        completed_stage=completed_stage.value,
        case_counts=case_counts,
        event_categories=events,
    )


def _safe_error(error: RetrievalAdapterError) -> str:
    category = str(error)
    return (
        category
        if category in _SAFE_ERROR_CATEGORIES
        else CompatibilityErrorCategory.REGISTRY_METADATA_INVALID.value
    )


def _require_input(value: object) -> None:
    if not isinstance(value, SyntheticApprovalWorkflowInput):
        _invalid()


def _safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) is not None


def _canonical_capabilities(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and all(
            isinstance(item, str) and item in _CAPABILITIES for item in value
        )
        and tuple(sorted(set(value))) == value
    )


def _canonical_counts(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and tuple(name for name, _ in value)
        == tuple(outcome.value for outcome in ValidationCaseOutcome)
        and all(type(count) is int and count >= 0 for _, count in value)
    )


def _validate_datetime(value: object, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        _invalid()


def _parse_datetime(value: object, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        _invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _invalid()
    _validate_datetime(parsed)
    return parsed


def _version(value: object) -> SemanticVersion:
    return SemanticVersion.parse(
        value,
        category=CompatibilityErrorCategory.REGISTRY_METADATA_INVALID,
    )


def _tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        value = tuple(value)
    if not isinstance(value, tuple):
        _invalid()
    return value


def _enum(enum_type: type[Enum], value: object):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        _invalid()


def _invalid() -> None:
    raise compatibility_error(CompatibilityErrorCategory.REGISTRY_METADATA_INVALID)
