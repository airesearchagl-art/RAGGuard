from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from ragguard.manual_validation_evidence import ManualValidationEvidence
from ragguard.manual_validation_plan import (
    ManualValidationPlan,
    SyntheticEvidenceReference,
)
from ragguard.production_registry import RegistryKind, RegistryStatus
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalMetadata,
    ApprovalRestrictions,
    ProfileMaturity,
    ValidationMetadata,
    ValidationStatus,
)


CANONICAL_ADMISSION_DIGEST_ALGORITHM = "sha256"
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SAFE_CONTEXT_VALUES = frozenset(
    {
        "manual_validation_not_executed",
        "no_credentials",
        "no_network",
        "no_real_documents",
        "no_registry_write",
        "product_neutral",
        "synthetic_only",
    }
)


class ReviewerAttestationOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVALIDATION = "needs_revalidation"


class RevalidationTrigger(str, Enum):
    PRODUCT_VERSION_CHANGED = "product_version_changed"
    PROFILE_VERSION_CHANGED = "profile_version_changed"
    PROTOCOL_VERSION_CHANGED = "protocol_version_changed"
    REQUEST_SCHEMA_CHANGED = "request_schema_changed"
    RESPONSE_SCHEMA_CHANGED = "response_schema_changed"
    CAPABILITY_CHANGED = "capability_changed"
    SCORE_SEMANTICS_CHANGED = "score_semantics_changed"
    SOURCE_POLICY_CHANGED = "source_policy_changed"
    SECURITY_BOUNDARY_CHANGED = "security_boundary_changed"
    TRANSPORT_CHANGED = "transport_changed"
    DEPENDENCY_CHANGED = "dependency_changed"
    INCIDENT_OR_VULNERABILITY = "incident_or_vulnerability"
    EXPIRATION = "expiration"
    EVIDENCE_INCONSISTENT = "evidence_inconsistent"
    REGISTRY_SUSPENSION = "registry_suspension"
    MANUAL_REVOCATION = "manual_revocation"


class ProductionAdmissionReason(str, Enum):
    IDENTITY_MISMATCH = "identity_mismatch"
    PLAN_BINDING_INVALID = "plan_binding_invalid"
    EVIDENCE_INVALID = "evidence_invalid"
    EVIDENCE_NOT_YET_VALID = "evidence_not_yet_valid"
    EVIDENCE_EXPIRED = "evidence_expired"
    REVIEWER_ATTESTATION_MISSING = "reviewer_attestation_missing"
    REVIEWER_ATTESTATION_INVALID = "reviewer_attestation_invalid"
    REVIEWER_REJECTED = "reviewer_rejected"
    ROLE_CONFLICT = "role_conflict"
    MATURITY_INELIGIBLE = "maturity_ineligible"
    VERSION_UNSUPPORTED = "version_unsupported"
    RESTRICTION_INVALID = "restriction_invalid"
    REVALIDATION_REQUIRED = "revalidation_required"
    REGISTRY_REQUEST_INVALID = "registry_request_invalid"
    SECURITY_BOUNDARY_VIOLATION = "security_boundary_violation"


_REASON_ORDER = tuple(ProductionAdmissionReason)
_REJECT_REASONS = frozenset(
    {
        ProductionAdmissionReason.IDENTITY_MISMATCH,
        ProductionAdmissionReason.PLAN_BINDING_INVALID,
        ProductionAdmissionReason.EVIDENCE_INVALID,
        ProductionAdmissionReason.REVIEWER_ATTESTATION_MISSING,
        ProductionAdmissionReason.REVIEWER_ATTESTATION_INVALID,
        ProductionAdmissionReason.REVIEWER_REJECTED,
        ProductionAdmissionReason.ROLE_CONFLICT,
        ProductionAdmissionReason.MATURITY_INELIGIBLE,
        ProductionAdmissionReason.RESTRICTION_INVALID,
        ProductionAdmissionReason.REGISTRY_REQUEST_INVALID,
        ProductionAdmissionReason.SECURITY_BOUNDARY_VIOLATION,
    }
)
_REVALIDATION_REASONS = frozenset(
    {
        ProductionAdmissionReason.EVIDENCE_NOT_YET_VALID,
        ProductionAdmissionReason.EVIDENCE_EXPIRED,
        ProductionAdmissionReason.VERSION_UNSUPPORTED,
        ProductionAdmissionReason.REVALIDATION_REQUIRED,
    }
)


class ProductionAdmissionErrorCategory(str, Enum):
    REQUEST_INVALID = "production_admission_request_invalid"
    ATTESTATION_INVALID = "reviewer_attestation_invalid"
    REGISTRY_REQUEST_INVALID = "registry_request_invalid"
    RESTRICTION_INVALID = "restriction_invalid"
    REVALIDATION_TRIGGER_INVALID = "revalidation_trigger_invalid"
    TEMPORAL_INPUT_INVALID = "temporal_input_invalid"
    SECURITY_BOUNDARY_VIOLATION = "security_boundary_violation"


class ProductionAdmissionError(ValueError):
    def __init__(self, category: ProductionAdmissionErrorCategory) -> None:
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True)
class ReviewerAttestationSafeSummary:
    attestation_id: str
    reviewer_id: str
    evidence_id: str
    evidence_digest: str
    plan_id: str
    plan_digest: str
    reviewed_at: str
    outcome: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ReviewerAttestation:
    attestation_id: str
    reviewer_id: str
    evidence_id: str
    evidence_digest: str
    plan_id: str
    plan_digest: str
    reviewed_at: datetime
    outcome: ReviewerAttestationOutcome
    safe_summary: ReviewerAttestationSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_ADMISSION_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            not all(
                _is_safe_identifier(value)
                for value in (
                    self.attestation_id,
                    self.reviewer_id,
                    self.evidence_id,
                    self.plan_id,
                )
            )
            or not _is_digest(self.evidence_digest)
            or not _is_digest(self.plan_digest)
            or not _is_aware_datetime(self.reviewed_at)
            or not isinstance(self.outcome, ReviewerAttestationOutcome)
        ):
            _raise(ProductionAdmissionErrorCategory.ATTESTATION_INVALID)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ReviewerAttestationSafeSummary(
                attestation_id=self.attestation_id,
                reviewer_id=self.reviewer_id,
                evidence_id=self.evidence_id,
                evidence_digest=self.evidence_digest,
                plan_id=self.plan_id,
                plan_digest=self.plan_digest,
                reviewed_at=_canonical_datetime(self.reviewed_at),
                outcome=self.outcome.value,
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "attestation_id": self.attestation_id,
                "evidence_digest": self.evidence_digest,
                "evidence_id": self.evidence_id,
                "outcome": self.outcome.value,
                "plan_digest": self.plan_digest,
                "plan_id": self.plan_id,
                "reviewed_at": _canonical_datetime(self.reviewed_at),
                "reviewer_id": self.reviewer_id,
            }
        )

    def __repr__(self) -> str:
        return "ReviewerAttestation(<safe>)"


@dataclass(frozen=True, repr=False)
class ProductionAdmissionRequest:
    request_id: str
    evaluation_time: datetime
    manual_validation_plan: ManualValidationPlan
    manual_validation_evidence: ManualValidationEvidence
    synthetic_validation_reference: SyntheticEvidenceReference
    profile_approval_metadata: ApprovalMetadata
    profile_validation_metadata: ValidationMetadata
    reviewer_attestation: ReviewerAttestation | None
    approver_identity: str
    requested_registry_kind: RegistryKind
    requested_initial_status: RegistryStatus
    requested_restrictions: ApprovalRestrictions | None
    safe_context: tuple[str, ...]
    profile_maturity: ProfileMaturity = ProfileMaturity.MANUALLY_VALIDATED
    validation_expires_at: datetime | None = None
    revalidation_triggers: tuple[RevalidationTrigger, ...] = ()

    def __post_init__(self) -> None:
        if (
            not _is_safe_identifier(self.request_id)
            or not _is_safe_identifier(self.approver_identity)
            or not _is_aware_datetime(self.evaluation_time)
            or not isinstance(self.manual_validation_plan, ManualValidationPlan)
            or not isinstance(
                self.manual_validation_evidence, ManualValidationEvidence
            )
            or not isinstance(
                self.synthetic_validation_reference, SyntheticEvidenceReference
            )
            or not isinstance(self.profile_approval_metadata, ApprovalMetadata)
            or not isinstance(self.profile_validation_metadata, ValidationMetadata)
            or (
                self.reviewer_attestation is not None
                and not isinstance(self.reviewer_attestation, ReviewerAttestation)
            )
            or not isinstance(self.profile_maturity, ProfileMaturity)
        ):
            _raise(ProductionAdmissionErrorCategory.REQUEST_INVALID)
        if (
            self.requested_registry_kind is not RegistryKind.PRODUCTION
            or self.requested_initial_status is not RegistryStatus.ACTIVE
        ):
            _raise(ProductionAdmissionErrorCategory.REGISTRY_REQUEST_INVALID)
        if (
            self.requested_restrictions is not None
            and not isinstance(self.requested_restrictions, ApprovalRestrictions)
        ):
            _raise(ProductionAdmissionErrorCategory.RESTRICTION_INVALID)
        if (
            not isinstance(self.safe_context, tuple)
            or any(
                not isinstance(value, str)
                or value not in _SAFE_CONTEXT_VALUES
                for value in self.safe_context
            )
        ):
            _raise(ProductionAdmissionErrorCategory.SECURITY_BOUNDARY_VIOLATION)
        canonical_context = tuple(sorted(set(self.safe_context)))
        if canonical_context != self.safe_context:
            _raise(ProductionAdmissionErrorCategory.SECURITY_BOUNDARY_VIOLATION)
        if (
            self.validation_expires_at is not None
            and not _is_aware_datetime(self.validation_expires_at)
        ):
            _raise(ProductionAdmissionErrorCategory.TEMPORAL_INPUT_INVALID)
        triggers = _canonical_triggers(self.revalidation_triggers)
        object.__setattr__(self, "revalidation_triggers", triggers)

    def __repr__(self) -> str:
        return "ProductionAdmissionRequest(<safe>)"


@dataclass(frozen=True)
class ProductionAdmissionSafeSummary:
    request_id: str
    decision: str
    eligible_for_registry_admission: bool
    profile_id: str
    profile_version: str
    protocol_version: str
    product_id: str
    product_version: str
    plan_digest: str
    evidence_digest: str
    reviewer_attestation_digest: str | None
    evidence_reviewer_id: str
    validation_operator_id: str
    approver_id: str
    reason_categories: tuple[str, ...]
    restriction_count: int
    evaluated_at: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ProductionAdmissionDecision:
    decision: ApprovalDecision
    eligible_for_registry_admission: bool
    effective_restrictions: ApprovalRestrictions | None
    reason_categories: tuple[ProductionAdmissionReason, ...]
    evaluated_at: datetime
    plan_id: str
    plan_digest: str
    evidence_id: str
    evidence_digest: str
    reviewer_attestation_id: str | None
    reviewer_attestation_digest: str | None
    evidence_reviewer_id: str
    validation_operator_id: str
    approver_id: str
    requested_registry_kind: RegistryKind
    requested_initial_status: RegistryStatus
    safe_summary: ProductionAdmissionSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)
    _request_id: str = field(repr=False, compare=True)
    _profile_id: str = field(repr=False, compare=True)
    _profile_version: str = field(repr=False, compare=True)
    _protocol_version: str = field(repr=False, compare=True)
    _product_id: str = field(repr=False, compare=True)
    _product_version: str = field(repr=False, compare=True)

    digest_algorithm: ClassVar[str] = CANONICAL_ADMISSION_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ProductionAdmissionSafeSummary(
                request_id=self._request_id,
                decision=self.decision.value,
                eligible_for_registry_admission=(
                    self.eligible_for_registry_admission
                ),
                profile_id=self._profile_id,
                profile_version=self._profile_version,
                protocol_version=self._protocol_version,
                product_id=self._product_id,
                product_version=self._product_version,
                plan_digest=self.plan_digest,
                evidence_digest=self.evidence_digest,
                reviewer_attestation_digest=self.reviewer_attestation_digest,
                evidence_reviewer_id=self.evidence_reviewer_id,
                validation_operator_id=self.validation_operator_id,
                approver_id=self.approver_id,
                reason_categories=tuple(
                    reason.value for reason in self.reason_categories
                ),
                restriction_count=_restriction_count(
                    self.effective_restrictions
                ),
                evaluated_at=_canonical_datetime(self.evaluated_at),
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "approver_id": self.approver_id,
                "decision": self.decision.value,
                "effective_restrictions": _canonical_restrictions(
                    self.effective_restrictions
                ),
                "eligible_for_registry_admission": (
                    self.eligible_for_registry_admission
                ),
                "evaluated_at": _canonical_datetime(self.evaluated_at),
                "evidence_digest": self.evidence_digest,
                "evidence_id": self.evidence_id,
                "evidence_reviewer_id": self.evidence_reviewer_id,
                "plan_digest": self.plan_digest,
                "plan_id": self.plan_id,
                "product_id": self._product_id,
                "product_version": self._product_version,
                "profile_id": self._profile_id,
                "profile_version": self._profile_version,
                "protocol_version": self._protocol_version,
                "reason_categories": [
                    reason.value for reason in self.reason_categories
                ],
                "request_id": self._request_id,
                "requested_initial_status": self.requested_initial_status.value,
                "requested_registry_kind": self.requested_registry_kind.value,
                "reviewer_attestation_digest": (
                    self.reviewer_attestation_digest
                ),
                "reviewer_attestation_id": self.reviewer_attestation_id,
                "validation_operator_id": self.validation_operator_id,
            }
        )

    @property
    def profile_id(self) -> str:
        return self._profile_id

    @property
    def profile_version(self) -> str:
        return self._profile_version

    @property
    def protocol_version(self) -> str:
        return self._protocol_version

    @property
    def product_id(self) -> str:
        return self._product_id

    @property
    def product_version(self) -> str:
        return self._product_version

    def __repr__(self) -> str:
        return "ProductionAdmissionDecision(<safe>)"


def evaluate_production_admission(
    request: ProductionAdmissionRequest,
) -> ProductionAdmissionDecision:
    if not isinstance(request, ProductionAdmissionRequest):
        _raise(ProductionAdmissionErrorCategory.REQUEST_INVALID)

    plan = request.manual_validation_plan
    evidence = request.manual_validation_evidence
    validation = request.profile_validation_metadata
    approval = request.profile_approval_metadata
    attestation = request.reviewer_attestation
    reasons: set[ProductionAdmissionReason] = set()

    if request.profile_maturity is not ProfileMaturity.MANUALLY_VALIDATED:
        reasons.add(ProductionAdmissionReason.MATURITY_INELIGIBLE)
    if not _plan_digest_valid(plan):
        reasons.add(ProductionAdmissionReason.PLAN_BINDING_INVALID)
    if not _evidence_digest_valid(evidence):
        reasons.add(ProductionAdmissionReason.EVIDENCE_INVALID)
    if not _exact_plan_evidence_binding(plan, evidence):
        reasons.add(ProductionAdmissionReason.PLAN_BINDING_INVALID)
    if request.synthetic_validation_reference != plan.synthetic_evidence_reference:
        reasons.add(ProductionAdmissionReason.IDENTITY_MISMATCH)
    if not _metadata_identity_valid(plan, evidence, validation, approval, request):
        reasons.add(ProductionAdmissionReason.IDENTITY_MISMATCH)
    if not _roles_separated(plan, request.approver_identity):
        reasons.add(ProductionAdmissionReason.ROLE_CONFLICT)

    if not evidence.is_valid:
        reasons.add(ProductionAdmissionReason.EVIDENCE_INVALID)
    elif request.evaluation_time < evidence.execution_completed_at:
        reasons.add(ProductionAdmissionReason.EVIDENCE_NOT_YET_VALID)
    elif request.evaluation_time >= evidence.expires_at:
        reasons.add(ProductionAdmissionReason.EVIDENCE_EXPIRED)
    elif not evidence.is_valid_at(request.evaluation_time):
        reasons.add(ProductionAdmissionReason.EVIDENCE_INVALID)

    if attestation is None:
        reasons.add(ProductionAdmissionReason.REVIEWER_ATTESTATION_MISSING)
    else:
        if not _attestation_valid(attestation, plan, evidence, request):
            reasons.add(ProductionAdmissionReason.REVIEWER_ATTESTATION_INVALID)
        elif attestation.outcome is ReviewerAttestationOutcome.REJECTED:
            reasons.add(ProductionAdmissionReason.REVIEWER_REJECTED)
        elif (
            attestation.outcome
            is ReviewerAttestationOutcome.NEEDS_REVALIDATION
        ):
            reasons.add(ProductionAdmissionReason.REVALIDATION_REQUIRED)
        if (
            approval.approved_at <= attestation.reviewed_at
            or approval.approved_at > request.evaluation_time
        ):
            reasons.add(ProductionAdmissionReason.REVIEWER_ATTESTATION_INVALID)

    if validation.validation_status is ValidationStatus.NEEDS_REVALIDATION:
        reasons.add(ProductionAdmissionReason.REVALIDATION_REQUIRED)
    elif (
        validation.validation_status is not ValidationStatus.PASSED
        or not validation.required_capabilities_result
        or "synthetic_compatibility" not in validation.validation_cases
    ):
        reasons.add(ProductionAdmissionReason.EVIDENCE_INVALID)
    if (
        request.validation_expires_at is not None
        and request.evaluation_time >= request.validation_expires_at
    ):
        reasons.add(ProductionAdmissionReason.REVALIDATION_REQUIRED)
    if validation.validated_at > request.evaluation_time:
        reasons.add(ProductionAdmissionReason.REVALIDATION_REQUIRED)
    if approval.is_expired(request.evaluation_time):
        reasons.add(ProductionAdmissionReason.REVALIDATION_REQUIRED)
    if approval.decision is ApprovalDecision.REJECTED:
        reasons.add(ProductionAdmissionReason.REVIEWER_REJECTED)
    elif approval.decision is ApprovalDecision.NEEDS_REVALIDATION:
        reasons.add(ProductionAdmissionReason.REVALIDATION_REQUIRED)

    if not approval.supported_product_version_range.contains(
        str(evidence.observed_product_version)
    ):
        reasons.add(ProductionAdmissionReason.VERSION_UNSUPPORTED)
    restrictions = request.requested_restrictions
    if not _restrictions_valid(restrictions, approval, evidence, request):
        reasons.add(ProductionAdmissionReason.RESTRICTION_INVALID)
    if request.revalidation_triggers:
        reasons.add(ProductionAdmissionReason.REVALIDATION_REQUIRED)

    ordered = tuple(reason for reason in _REASON_ORDER if reason in reasons)
    if reasons & _REJECT_REASONS:
        decision = ApprovalDecision.REJECTED
    elif reasons & _REVALIDATION_REASONS:
        decision = ApprovalDecision.NEEDS_REVALIDATION
    elif restrictions is not None and not restrictions.is_empty:
        decision = ApprovalDecision.APPROVED_WITH_RESTRICTIONS
    else:
        decision = ApprovalDecision.APPROVED
    eligible = decision in {
        ApprovalDecision.APPROVED,
        ApprovalDecision.APPROVED_WITH_RESTRICTIONS,
    }
    effective = restrictions if eligible and restrictions is not None else None
    return ProductionAdmissionDecision(
        decision=decision,
        eligible_for_registry_admission=eligible,
        effective_restrictions=effective,
        reason_categories=ordered,
        evaluated_at=request.evaluation_time,
        plan_id=plan.plan_id,
        plan_digest=plan.canonical_digest,
        evidence_id=evidence.evidence_id,
        evidence_digest=evidence.canonical_digest,
        reviewer_attestation_id=(
            None if attestation is None else attestation.attestation_id
        ),
        reviewer_attestation_digest=(
            None if attestation is None else attestation.canonical_digest
        ),
        evidence_reviewer_id=plan.evidence_reviewer_id,
        validation_operator_id=plan.validation_operator_id,
        approver_id=request.approver_identity,
        requested_registry_kind=request.requested_registry_kind,
        requested_initial_status=request.requested_initial_status,
        _request_id=request.request_id,
        _profile_id=plan.profile_id,
        _profile_version=str(plan.profile_version),
        _protocol_version=str(plan.protocol_version),
        _product_id=plan.product_id,
        _product_version=str(evidence.observed_product_version),
    )


def _exact_plan_evidence_binding(
    plan: ManualValidationPlan, evidence: ManualValidationEvidence
) -> bool:
    return (
        evidence.plan_id == plan.plan_id
        and evidence.plan_digest == plan.canonical_digest
        and evidence.profile_id == plan.profile_id
        and evidence.profile_version == plan.profile_version
        and evidence.protocol_version == plan.protocol_version
        and evidence.product_id == plan.product_id
        and evidence.planned_product_version == plan.product_version
        and evidence.observed_product_version == plan.product_version
        and evidence.validation_operator_id == plan.validation_operator_id
        and evidence.evidence_reviewer_id == plan.evidence_reviewer_id
    )


def _metadata_identity_valid(
    plan: ManualValidationPlan,
    evidence: ManualValidationEvidence,
    validation: ValidationMetadata,
    approval: ApprovalMetadata,
    request: ProductionAdmissionRequest,
) -> bool:
    return (
        validation.profile_id == plan.profile_id
        and validation.profile_version == plan.profile_version
        and validation.protocol_version == plan.protocol_version
        and validation.normalized_product_version
        == evidence.observed_product_version
        and approval.validation_record_id == validation.validation_record_id
        and approval.reviewer_id == plan.evidence_reviewer_id
        and approval.approver_id == request.approver_identity
        and plan.approver_id == request.approver_identity
    )


def _roles_separated(
    plan: ManualValidationPlan, approver_identity: str
) -> bool:
    return (
        plan.validation_operator_id != plan.evidence_reviewer_id
        and plan.evidence_reviewer_id != approver_identity
        and plan.profile_implementer_id != approver_identity
        and plan.approver_id == approver_identity
    )


def _attestation_valid(
    attestation: ReviewerAttestation,
    plan: ManualValidationPlan,
    evidence: ManualValidationEvidence,
    request: ProductionAdmissionRequest,
) -> bool:
    return (
        attestation.reviewer_id == plan.evidence_reviewer_id
        and attestation.reviewer_id == evidence.evidence_reviewer_id
        and attestation.reviewer_id != request.approver_identity
        and attestation.evidence_id == evidence.evidence_id
        and attestation.evidence_digest == evidence.canonical_digest
        and attestation.plan_id == plan.plan_id
        and attestation.plan_digest == plan.canonical_digest
        and evidence.execution_completed_at <= attestation.reviewed_at
        and attestation.reviewed_at < evidence.expires_at
        and attestation.reviewed_at <= request.evaluation_time
        and _digest(attestation.canonical_json())
        == attestation.canonical_digest
    )


def _restrictions_valid(
    restrictions: ApprovalRestrictions | None,
    approval: ApprovalMetadata,
    evidence: ManualValidationEvidence,
    request: ProductionAdmissionRequest,
) -> bool:
    if restrictions is None or restrictions.is_empty:
        return approval.restrictions is None
    if restrictions != approval.restrictions:
        return False
    minor = (
        f"{evidence.observed_product_version.major}."
        f"{evidence.observed_product_version.minor}"
    )
    if (
        restrictions.supported_minor_versions
        and minor not in restrictions.supported_minor_versions
    ):
        return False
    if (
        restrictions.query_id_echo_required
        and "query_id_echo" not in approval.approved_capabilities
    ):
        return False
    return True


def _canonical_restrictions(
    restrictions: ApprovalRestrictions | None,
) -> dict[str, object] | None:
    if restrictions is None:
        return None
    return {
        "expires_at": (
            None
            if restrictions.expires_at is None
            else _canonical_datetime(restrictions.expires_at)
        ),
        "matched_keywords_disabled": restrictions.matched_keywords_disabled,
        "maximum_top_k": restrictions.maximum_top_k,
        "query_id_echo_required": restrictions.query_id_echo_required,
        "score_disabled": restrictions.score_disabled,
        "supported_minor_versions": list(
            restrictions.supported_minor_versions
        ),
        "title_disabled": restrictions.title_disabled,
    }


def _restriction_count(restrictions: ApprovalRestrictions | None) -> int:
    if restrictions is None:
        return 0
    mapping = _canonical_restrictions(restrictions)
    assert mapping is not None
    return sum(
        value not in (None, False, [], ())
        for value in mapping.values()
    )


def _canonical_triggers(
    values: tuple[RevalidationTrigger, ...],
) -> tuple[RevalidationTrigger, ...]:
    if (
        not isinstance(values, tuple)
        or any(not isinstance(value, RevalidationTrigger) for value in values)
    ):
        _raise(ProductionAdmissionErrorCategory.REVALIDATION_TRIGGER_INVALID)
    canonical = tuple(sorted(set(values), key=lambda value: value.value))
    if canonical != values:
        _raise(ProductionAdmissionErrorCategory.REVALIDATION_TRIGGER_INVALID)
    return canonical


def _plan_digest_valid(plan: ManualValidationPlan) -> bool:
    return _digest(plan.canonical_json()) == plan.canonical_digest


def _evidence_digest_valid(evidence: ManualValidationEvidence) -> bool:
    return _digest(evidence.canonical_json()) == evidence.canonical_digest


def _is_safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_aware_datetime(value: object) -> bool:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return False
    try:
        return value.utcoffset() is not None
    except (OverflowError, ValueError):
        return False


def _canonical_datetime(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _raise(category: ProductionAdmissionErrorCategory) -> None:
    raise ProductionAdmissionError(category)


__all__ = [
    "CANONICAL_ADMISSION_DIGEST_ALGORITHM",
    "ProductionAdmissionDecision",
    "ProductionAdmissionError",
    "ProductionAdmissionErrorCategory",
    "ProductionAdmissionReason",
    "ProductionAdmissionRequest",
    "ProductionAdmissionSafeSummary",
    "ReviewerAttestation",
    "ReviewerAttestationOutcome",
    "ReviewerAttestationSafeSummary",
    "RevalidationTrigger",
    "evaluate_production_admission",
]
