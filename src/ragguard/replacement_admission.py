from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import ClassVar, Mapping

from ragguard.compatibility import SemanticVersion
from ragguard.production_admission import (
    ProductionAdmissionDecision,
    ProductionAdmissionReason,
    ProductionAdmissionRequest,
    evaluate_production_admission,
)
from ragguard.production_registry import RegistryKind, RegistryStatus
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalMetadata,
    ApprovalRestrictions,
)
from ragguard.registry_admission import (
    RegistryAdmissionEntry,
    TestRegistryAdmissionStore,
)
from ragguard.registry_lifecycle import (
    RegistryLifecycleEvent,
    TestRegistryLifecycleStore,
)


CANONICAL_REPLACEMENT_ADMISSION_DIGEST_ALGORITHM = "sha256"
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SAFE_CONTEXT_VALUES = frozenset(
    {
        "no_credentials",
        "no_network",
        "no_persistence",
        "no_production_registry_write",
        "no_real_documents",
        "no_transport",
        "synthetic_only",
        "test_registry_only",
    }
)
_ELIGIBLE_PREDECESSOR_STATUSES = frozenset(
    {RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED}
)
_VERSION_CHANGE_REASONS = frozenset(
    {
        "product_version_revalidated",
        "protocol_version_revalidated",
        "restriction_revalidated",
    }
)


class ReplacementReason(str, Enum):
    EVIDENCE_REFRESHED = "evidence_refreshed"
    APPROVAL_REFRESHED = "approval_refreshed"
    PRODUCT_VERSION_REVALIDATED = "product_version_revalidated"
    PROTOCOL_VERSION_REVALIDATED = "protocol_version_revalidated"
    RESTRICTION_REVALIDATED = "restriction_revalidated"
    SCHEDULED_REVALIDATION_COMPLETED = "scheduled_revalidation_completed"


class ReplacementDecisionStatus(str, Enum):
    ELIGIBLE = "eligible"
    REJECTED = "rejected"
    NEEDS_REVALIDATION = "needs_revalidation"


class ReplacementAdmissionReason(str, Enum):
    PREDECESSOR_NOT_FOUND = "predecessor_not_found"
    PREDECESSOR_STATUS_INELIGIBLE = "predecessor_status_ineligible"
    PREDECESSOR_ALREADY_REPLACED = "predecessor_already_replaced"
    IDENTITY_MISMATCH = "identity_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    STALE_CHAIN = "stale_chain"
    CHAIN_REUSE = "chain_reuse"
    EVIDENCE_EXPIRED = "evidence_expired"
    ROLE_CONFLICT = "role_conflict"
    TEMPORAL_INVALID = "temporal_invalid"
    RESTRICTION_MISMATCH = "restriction_mismatch"
    DUPLICATE_REQUEST = "duplicate_request"
    DUPLICATE_SUCCESSOR = "duplicate_successor"
    REPLACEMENT_LOOP = "replacement_loop"
    REVALIDATION_REQUIRED = "revalidation_required"
    SECURITY_BOUNDARY_VIOLATION = "security_boundary_violation"
    REGISTRY_WRITE_REJECTED = "registry_write_rejected"
    REGISTRY_COMMIT_FAILED = "registry_commit_failed"


class ReplacementCommitFault(str, Enum):
    ENTRY_CANDIDATE = "entry_candidate"
    EVENT_CANDIDATE = "event_candidate"
    COUNTER_AND_REQUEST_CANDIDATE = "counter_and_request_candidate"
    BEFORE_COMMIT = "before_commit"


_REASON_ORDER = tuple(ReplacementAdmissionReason)


class ReplacementAdmissionError(ValueError):
    def __init__(self, category: ReplacementAdmissionReason) -> None:
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True)
class ReplacementAdmissionRequestSafeSummary:
    replacement_request_id: str
    replacement_entry_id: str
    evaluation_time: str
    predecessor_entry_digest: str
    predecessor_status: str
    successor_profile_id: str
    successor_profile_version: str
    successor_product_id: str
    successor_product_version: str
    successor_protocol_version: str
    replacement_reason: str
    new_plan_digest: str
    new_evidence_digest: str
    new_attestation_digest: str
    new_admission_decision_digest: str
    registry_administrator_id: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ReplacementAdmissionRequest:
    replacement_request_id: str
    replacement_entry_id: str
    evaluation_time: datetime
    old_registry_entry_digest: str
    old_profile_id: str
    old_profile_version: SemanticVersion
    old_product_id: str
    old_product_version: SemanticVersion
    old_protocol_version: SemanticVersion
    expected_old_status: RegistryStatus
    predecessor_production_admission_request: ProductionAdmissionRequest = field(
        repr=False
    )
    new_admission_decision: ProductionAdmissionDecision
    new_production_admission_request: ProductionAdmissionRequest = field(
        repr=False
    )
    predecessor_lifecycle_event: RegistryLifecycleEvent = field(repr=False)
    new_plan_digest: str = ""
    new_evidence_digest: str = ""
    new_attestation_digest: str = ""
    new_admission_decision_digest: str = ""
    registry_administrator_id: str = ""
    replacement_reason: ReplacementReason = ReplacementReason.EVIDENCE_REFRESHED
    safe_context: tuple[str, ...] = ()
    safe_summary: ReplacementAdmissionRequestSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = (
        CANONICAL_REPLACEMENT_ADMISSION_DIGEST_ALGORITHM
    )

    def __post_init__(self) -> None:
        identifiers = (
            self.replacement_request_id,
            self.replacement_entry_id,
            self.old_profile_id,
            self.old_product_id,
            self.registry_administrator_id,
        )
        if (
            not all(_is_safe_identifier(value) for value in identifiers)
            or not _is_aware_datetime(self.evaluation_time)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.old_profile_version,
                    self.old_product_version,
                    self.old_protocol_version,
                )
            )
            or not isinstance(self.expected_old_status, RegistryStatus)
            or not isinstance(
                self.predecessor_production_admission_request,
                ProductionAdmissionRequest,
            )
            or not isinstance(
                self.new_admission_decision, ProductionAdmissionDecision
            )
            or not isinstance(
                self.new_production_admission_request,
                ProductionAdmissionRequest,
            )
            or not isinstance(
                self.predecessor_lifecycle_event, RegistryLifecycleEvent
            )
            or not isinstance(self.replacement_reason, ReplacementReason)
            or not all(
                _is_digest(value)
                for value in (
                    self.old_registry_entry_digest,
                    self.new_plan_digest,
                    self.new_evidence_digest,
                    self.new_attestation_digest,
                    self.new_admission_decision_digest,
                )
            )
            or not _is_safe_context(self.safe_context)
        ):
            _raise(ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        decision = self.new_admission_decision
        object.__setattr__(
            self,
            "safe_summary",
            ReplacementAdmissionRequestSafeSummary(
                replacement_request_id=self.replacement_request_id,
                replacement_entry_id=self.replacement_entry_id,
                evaluation_time=_canonical_datetime(self.evaluation_time),
                predecessor_entry_digest=self.old_registry_entry_digest,
                predecessor_status=self.expected_old_status.value,
                successor_profile_id=decision.profile_id,
                successor_profile_version=decision.profile_version,
                successor_product_id=decision.product_id,
                successor_product_version=decision.product_version,
                successor_protocol_version=decision.protocol_version,
                replacement_reason=self.replacement_reason.value,
                new_plan_digest=self.new_plan_digest,
                new_evidence_digest=self.new_evidence_digest,
                new_attestation_digest=self.new_attestation_digest,
                new_admission_decision_digest=(
                    self.new_admission_decision_digest
                ),
                registry_administrator_id=self.registry_administrator_id,
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        decision = self.new_admission_decision
        event = self.predecessor_lifecycle_event
        predecessor_request = self.predecessor_production_admission_request
        return _canonical_json(
            {
                "evaluation_time": _canonical_datetime(self.evaluation_time),
                "expected_old_status": self.expected_old_status.value,
                "new_admission_decision_digest": (
                    self.new_admission_decision_digest
                ),
                "new_attestation_digest": self.new_attestation_digest,
                "new_evidence_digest": self.new_evidence_digest,
                "new_plan_digest": self.new_plan_digest,
                "old_product_id": self.old_product_id,
                "old_product_version": str(self.old_product_version),
                "old_profile_id": self.old_profile_id,
                "old_profile_version": str(self.old_profile_version),
                "old_protocol_version": str(self.old_protocol_version),
                "old_registry_entry_digest": self.old_registry_entry_digest,
                "predecessor_chain": {
                    "admission_decision_digest": evaluate_production_admission(
                        predecessor_request
                    ).canonical_digest,
                    "approval_metadata_digest": (
                        _approval_digest(
                            predecessor_request.profile_approval_metadata
                        )
                    ),
                    "attestation_digest": (
                        predecessor_request.reviewer_attestation.canonical_digest
                        if predecessor_request.reviewer_attestation is not None
                        else None
                    ),
                    "evidence_digest": (
                        predecessor_request.manual_validation_evidence.canonical_digest
                    ),
                    "plan_digest": (
                        predecessor_request.manual_validation_plan.canonical_digest
                    ),
                },
                "predecessor_lifecycle": {
                    "admission_id": event.admission_id,
                    "lifecycle_request_digest": (
                        event.lifecycle_request_digest
                    ),
                    "new_status": event.new_status,
                    "resulting_entry_digest": event.resulting_entry_digest,
                    "transitioned_at": event.transitioned_at,
                },
                "registry_administrator_id": (
                    self.registry_administrator_id
                ),
                "replacement_entry_id": self.replacement_entry_id,
                "replacement_reason": self.replacement_reason.value,
                "replacement_request_id": self.replacement_request_id,
                "safe_context": list(self.safe_context),
                "successor_identity": {
                    "product_id": decision.product_id,
                    "product_version": decision.product_version,
                    "profile_id": decision.profile_id,
                    "profile_version": decision.profile_version,
                    "protocol_version": decision.protocol_version,
                },
            }
        )

    def __repr__(self) -> str:
        return "ReplacementAdmissionRequest(<safe>)"


@dataclass(frozen=True)
class ReplacementAdmissionDecisionSafeSummary:
    replacement_request_id: str
    decision: str
    predecessor_entry_id: str
    predecessor_entry_digest: str
    predecessor_status: str
    successor_entry_id: str
    successor_profile_id: str
    successor_profile_version: str
    successor_product_id: str
    successor_product_version: str
    successor_protocol_version: str
    reason_categories: tuple[str, ...]
    restriction_count: int
    evaluated_at: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ReplacementAdmissionDecision:
    replacement_request_id: str
    decision: ReplacementDecisionStatus
    predecessor_entry_id: str
    predecessor_entry_digest: str
    predecessor_status: RegistryStatus
    successor_entry_id: str
    successor_profile_id: str
    successor_profile_version: SemanticVersion
    successor_product_id: str
    successor_product_version: SemanticVersion
    successor_protocol_version: SemanticVersion
    new_plan_digest: str
    new_evidence_digest: str
    new_attestation_digest: str
    new_admission_decision_digest: str
    effective_restrictions: ApprovalRestrictions | None
    reason_categories: tuple[ReplacementAdmissionReason, ...]
    evaluated_at: datetime
    safe_summary: ReplacementAdmissionDecisionSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = (
        CANONICAL_REPLACEMENT_ADMISSION_DIGEST_ALGORITHM
    )

    def __post_init__(self) -> None:
        if (
            not all(
                _is_safe_identifier(value)
                for value in (
                    self.replacement_request_id,
                    self.predecessor_entry_id,
                    self.successor_entry_id,
                    self.successor_profile_id,
                    self.successor_product_id,
                )
            )
            or not isinstance(self.decision, ReplacementDecisionStatus)
            or not isinstance(self.predecessor_status, RegistryStatus)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.successor_profile_version,
                    self.successor_product_version,
                    self.successor_protocol_version,
                )
            )
            or not all(
                _is_digest(value)
                for value in (
                    self.predecessor_entry_digest,
                    self.new_plan_digest,
                    self.new_evidence_digest,
                    self.new_attestation_digest,
                    self.new_admission_decision_digest,
                )
            )
            or (
                self.effective_restrictions is not None
                and not isinstance(
                    self.effective_restrictions, ApprovalRestrictions
                )
            )
            or tuple(
                reason
                for reason in _REASON_ORDER
                if reason in self.reason_categories
            )
            != self.reason_categories
            or not _is_aware_datetime(self.evaluated_at)
        ):
            _raise(ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        if (
            self.decision is ReplacementDecisionStatus.ELIGIBLE
            and self.reason_categories
        ) or (
            self.decision is not ReplacementDecisionStatus.ELIGIBLE
            and not self.reason_categories
        ):
            _raise(ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ReplacementAdmissionDecisionSafeSummary(
                replacement_request_id=self.replacement_request_id,
                decision=self.decision.value,
                predecessor_entry_id=self.predecessor_entry_id,
                predecessor_entry_digest=self.predecessor_entry_digest,
                predecessor_status=self.predecessor_status.value,
                successor_entry_id=self.successor_entry_id,
                successor_profile_id=self.successor_profile_id,
                successor_profile_version=str(self.successor_profile_version),
                successor_product_id=self.successor_product_id,
                successor_product_version=str(self.successor_product_version),
                successor_protocol_version=str(self.successor_protocol_version),
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
                "decision": self.decision.value,
                "effective_restrictions": _canonical_restrictions(
                    self.effective_restrictions
                ),
                "evaluated_at": _canonical_datetime(self.evaluated_at),
                "new_admission_decision_digest": (
                    self.new_admission_decision_digest
                ),
                "new_attestation_digest": self.new_attestation_digest,
                "new_evidence_digest": self.new_evidence_digest,
                "new_plan_digest": self.new_plan_digest,
                "predecessor_entry_digest": self.predecessor_entry_digest,
                "predecessor_entry_id": self.predecessor_entry_id,
                "predecessor_status": self.predecessor_status.value,
                "reason_categories": [
                    reason.value for reason in self.reason_categories
                ],
                "replacement_request_id": self.replacement_request_id,
                "successor_entry_id": self.successor_entry_id,
                "successor_product_id": self.successor_product_id,
                "successor_product_version": str(
                    self.successor_product_version
                ),
                "successor_profile_id": self.successor_profile_id,
                "successor_profile_version": str(
                    self.successor_profile_version
                ),
                "successor_protocol_version": str(
                    self.successor_protocol_version
                ),
            }
        )

    def __repr__(self) -> str:
        return "ReplacementAdmissionDecision(<safe>)"


@dataclass(frozen=True)
class ReplacementRegistryEntrySafeSummary:
    replacement_entry_id: str
    predecessor_entry_digest: str
    predecessor_status: str
    replacement_request_digest: str
    profile_id: str
    profile_version: str
    product_id: str
    product_version: str
    protocol_version: str
    registry_status: str
    restriction_count: int
    admitted_at: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ReplacementRegistryEntry:
    replacement_entry_id: str
    predecessor_entry_digest: str
    predecessor_status: RegistryStatus
    replacement_request_digest: str
    profile_id: str
    profile_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    protocol_version: SemanticVersion
    plan_digest: str
    evidence_digest: str
    reviewer_attestation_digest: str
    admission_decision_digest: str
    admitted_at: datetime
    registry_administrator_id: str
    registry_status: RegistryStatus
    effective_restrictions: ApprovalRestrictions | None
    safe_summary: ReplacementRegistryEntrySafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = (
        CANONICAL_REPLACEMENT_ADMISSION_DIGEST_ALGORITHM
    )

    def __post_init__(self) -> None:
        if (
            not all(
                _is_safe_identifier(value)
                for value in (
                    self.replacement_entry_id,
                    self.profile_id,
                    self.product_id,
                    self.registry_administrator_id,
                )
            )
            or not all(
                _is_digest(value)
                for value in (
                    self.predecessor_entry_digest,
                    self.replacement_request_digest,
                    self.plan_digest,
                    self.evidence_digest,
                    self.reviewer_attestation_digest,
                    self.admission_decision_digest,
                )
            )
            or self.predecessor_status
            not in _ELIGIBLE_PREDECESSOR_STATUSES
            or self.registry_status is not RegistryStatus.ACTIVE
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.profile_version,
                    self.product_version,
                    self.protocol_version,
                )
            )
            or not _is_aware_datetime(self.admitted_at)
            or (
                self.effective_restrictions is not None
                and not isinstance(
                    self.effective_restrictions, ApprovalRestrictions
                )
            )
        ):
            _raise(ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ReplacementRegistryEntrySafeSummary(
                replacement_entry_id=self.replacement_entry_id,
                predecessor_entry_digest=self.predecessor_entry_digest,
                predecessor_status=self.predecessor_status.value,
                replacement_request_digest=self.replacement_request_digest,
                profile_id=self.profile_id,
                profile_version=str(self.profile_version),
                product_id=self.product_id,
                product_version=str(self.product_version),
                protocol_version=str(self.protocol_version),
                registry_status=self.registry_status.value,
                restriction_count=_restriction_count(
                    self.effective_restrictions
                ),
                admitted_at=_canonical_datetime(self.admitted_at),
                canonical_digest=digest,
            ),
        )

    @property
    def admission_id(self) -> str:
        return self.replacement_entry_id

    @property
    def restrictions(self) -> ApprovalRestrictions | None:
        return self.effective_restrictions

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "admission_decision_digest": self.admission_decision_digest,
                "admitted_at": _canonical_datetime(self.admitted_at),
                "effective_restrictions": _canonical_restrictions(
                    self.effective_restrictions
                ),
                "evidence_digest": self.evidence_digest,
                "plan_digest": self.plan_digest,
                "predecessor_entry_digest": self.predecessor_entry_digest,
                "predecessor_status": self.predecessor_status.value,
                "product_id": self.product_id,
                "product_version": str(self.product_version),
                "profile_id": self.profile_id,
                "profile_version": str(self.profile_version),
                "protocol_version": str(self.protocol_version),
                "registry_administrator_id": (
                    self.registry_administrator_id
                ),
                "registry_status": self.registry_status.value,
                "replacement_entry_id": self.replacement_entry_id,
                "replacement_request_digest": (
                    self.replacement_request_digest
                ),
                "reviewer_attestation_digest": (
                    self.reviewer_attestation_digest
                ),
            }
        )

    def __repr__(self) -> str:
        return "ReplacementRegistryEntry(<safe>)"


@dataclass(frozen=True)
class ReplacementAdmissionEvent:
    replacement_request_id: str
    predecessor_entry_id: str
    predecessor_entry_digest: str
    successor_entry_id: str
    successor_entry_digest: str
    predecessor_status: RegistryStatus
    successor_status: RegistryStatus
    replacement_reason: ReplacementReason
    transitioned_at: datetime
    actor_id: str
    replacement_request_digest: str
    plan_digest: str
    evidence_digest: str
    attestation_digest: str
    admission_decision_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not all(
                _is_safe_identifier(value)
                for value in (
                    self.replacement_request_id,
                    self.predecessor_entry_id,
                    self.successor_entry_id,
                    self.actor_id,
                )
            )
            or not all(
                _is_digest(value)
                for value in (
                    self.predecessor_entry_digest,
                    self.successor_entry_digest,
                    self.replacement_request_digest,
                    self.plan_digest,
                    self.evidence_digest,
                    self.attestation_digest,
                    self.admission_decision_digest,
                )
            )
            or self.predecessor_status
            not in _ELIGIBLE_PREDECESSOR_STATUSES
            or self.successor_status is not RegistryStatus.ACTIVE
            or not isinstance(self.replacement_reason, ReplacementReason)
            or not _is_aware_datetime(self.transitioned_at)
        ):
            _raise(ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "actor_id": self.actor_id,
                "admission_decision_digest": self.admission_decision_digest,
                "attestation_digest": self.attestation_digest,
                "evidence_digest": self.evidence_digest,
                "plan_digest": self.plan_digest,
                "predecessor_entry_digest": self.predecessor_entry_digest,
                "predecessor_entry_id": self.predecessor_entry_id,
                "predecessor_status": self.predecessor_status.value,
                "replacement_reason": self.replacement_reason.value,
                "replacement_request_digest": (
                    self.replacement_request_digest
                ),
                "replacement_request_id": self.replacement_request_id,
                "successor_entry_digest": self.successor_entry_digest,
                "successor_entry_id": self.successor_entry_id,
                "successor_status": self.successor_status.value,
                "transitioned_at": _canonical_datetime(self.transitioned_at),
            }
        )


@dataclass(frozen=True)
class ReplacementAdmissionResultSafeSummary:
    replacement_request_id: str
    applied: bool
    predecessor_entry_id: str
    predecessor_entry_digest: str
    predecessor_status: str
    successor_entry_id: str | None
    successor_entry_digest: str | None
    successor_status: str | None
    reason_categories: tuple[str, ...]
    replacement_request_digest: str
    replacement_event_digest: str | None
    evaluated_at: str
    applied_at: str | None
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ReplacementAdmissionResult:
    replacement_request_id: str
    applied: bool
    predecessor_entry_id: str
    predecessor_entry_digest: str
    predecessor_status: RegistryStatus
    successor_entry_id: str | None
    successor_entry_digest: str | None
    successor_status: RegistryStatus | None
    reason_categories: tuple[ReplacementAdmissionReason, ...]
    replacement_request_digest: str
    new_plan_digest: str
    new_evidence_digest: str
    new_attestation_digest: str
    new_admission_decision_digest: str
    replacement_event_digest: str | None
    evaluated_at: datetime
    applied_at: datetime | None
    successor_entry: ReplacementRegistryEntry | None = field(repr=False)
    event: ReplacementAdmissionEvent | None = field(repr=False)
    safe_summary: ReplacementAdmissionResultSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = (
        CANONICAL_REPLACEMENT_ADMISSION_DIGEST_ALGORITHM
    )

    def __post_init__(self) -> None:
        if (
            not _is_safe_identifier(self.replacement_request_id)
            or not _is_safe_identifier(self.predecessor_entry_id)
            or not _is_digest(self.predecessor_entry_digest)
            or not isinstance(self.predecessor_status, RegistryStatus)
            or tuple(
                reason
                for reason in _REASON_ORDER
                if reason in self.reason_categories
            )
            != self.reason_categories
            or not _is_digest(self.replacement_request_digest)
            or not all(
                _is_digest(value)
                for value in (
                    self.new_plan_digest,
                    self.new_evidence_digest,
                    self.new_attestation_digest,
                    self.new_admission_decision_digest,
                )
            )
            or not _is_aware_datetime(self.evaluated_at)
        ):
            _raise(ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        if self.applied:
            if (
                self.reason_categories
                or self.successor_entry is None
                or self.event is None
                or self.successor_entry_id
                != self.successor_entry.replacement_entry_id
                or self.successor_entry_digest
                != self.successor_entry.canonical_digest
                or self.successor_status is not RegistryStatus.ACTIVE
                or self.replacement_event_digest
                != self.event.canonical_digest
                or self.applied_at is None
                or not _is_aware_datetime(self.applied_at)
            ):
                _raise(ReplacementAdmissionReason.REGISTRY_COMMIT_FAILED)
        elif any(
            value is not None
            for value in (
                self.successor_entry_id,
                self.successor_entry_digest,
                self.successor_status,
                self.replacement_event_digest,
                self.applied_at,
                self.successor_entry,
                self.event,
            )
        ) or not self.reason_categories:
            _raise(ReplacementAdmissionReason.REGISTRY_COMMIT_FAILED)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ReplacementAdmissionResultSafeSummary(
                replacement_request_id=self.replacement_request_id,
                applied=self.applied,
                predecessor_entry_id=self.predecessor_entry_id,
                predecessor_entry_digest=self.predecessor_entry_digest,
                predecessor_status=self.predecessor_status.value,
                successor_entry_id=self.successor_entry_id,
                successor_entry_digest=self.successor_entry_digest,
                successor_status=(
                    self.successor_status.value
                    if self.successor_status is not None
                    else None
                ),
                reason_categories=tuple(
                    reason.value for reason in self.reason_categories
                ),
                replacement_request_digest=self.replacement_request_digest,
                replacement_event_digest=self.replacement_event_digest,
                evaluated_at=_canonical_datetime(self.evaluated_at),
                applied_at=_optional_datetime(self.applied_at),
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "applied": self.applied,
                "applied_at": _optional_datetime(self.applied_at),
                "evaluated_at": _canonical_datetime(self.evaluated_at),
                "new_admission_decision_digest": (
                    self.new_admission_decision_digest
                ),
                "new_attestation_digest": self.new_attestation_digest,
                "new_evidence_digest": self.new_evidence_digest,
                "new_plan_digest": self.new_plan_digest,
                "predecessor_entry_digest": self.predecessor_entry_digest,
                "predecessor_entry_id": self.predecessor_entry_id,
                "predecessor_status": self.predecessor_status.value,
                "reason_categories": [
                    reason.value for reason in self.reason_categories
                ],
                "replacement_event_digest": self.replacement_event_digest,
                "replacement_request_digest": (
                    self.replacement_request_digest
                ),
                "replacement_request_id": self.replacement_request_id,
                "successor_entry_digest": self.successor_entry_digest,
                "successor_entry_id": self.successor_entry_id,
                "successor_status": (
                    self.successor_status.value
                    if self.successor_status is not None
                    else None
                ),
            }
        )

    def __repr__(self) -> str:
        return "ReplacementAdmissionResult(<safe>)"


_StoredEntry = RegistryAdmissionEntry | ReplacementRegistryEntry


@dataclass(frozen=True)
class _ReplacementStoreState:
    entries: Mapping[str, _StoredEntry]
    events: tuple[ReplacementAdmissionEvent, ...]
    write_count: int
    mutation_count: int
    committed_request_ids: frozenset[str]
    replaced_predecessor_digests: frozenset[str]
    committed_pairs: frozenset[tuple[str, str]]
    used_approval_metadata_digests: frozenset[str]
    used_attestation_digests: frozenset[str]
    used_evidence_digests: frozenset[str]
    used_decision_digests: frozenset[str]


class TestReplacementAdmissionStore:
    __test__ = False

    def __init__(
        self,
        admission_registry: TestRegistryAdmissionStore,
        lifecycle_registry: TestRegistryLifecycleStore,
        *,
        failure_point: ReplacementCommitFault | None = None,
    ) -> None:
        if (
            not isinstance(admission_registry, TestRegistryAdmissionStore)
            or not isinstance(lifecycle_registry, TestRegistryLifecycleStore)
            or lifecycle_registry.kind is not RegistryKind.TEST
            or (
                failure_point is not None
                and not isinstance(failure_point, ReplacementCommitFault)
            )
            or lifecycle_registry.admission_snapshot
            != admission_registry.snapshot
        ):
            _raise(ReplacementAdmissionReason.REGISTRY_WRITE_REJECTED)
        entries = {
            entry.admission_id: entry
            for entry in admission_registry.snapshot.values()
        }
        self._state = _ReplacementStoreState(
            entries=MappingProxyType(entries),
            events=(),
            write_count=0,
            mutation_count=0,
            committed_request_ids=frozenset(),
            replaced_predecessor_digests=frozenset(),
            committed_pairs=frozenset(),
            used_approval_metadata_digests=frozenset(),
            used_attestation_digests=frozenset(),
            used_evidence_digests=frozenset(),
            used_decision_digests=frozenset(),
        )
        self._failure_point = failure_point

    @property
    def kind(self) -> RegistryKind:
        return RegistryKind.TEST

    @property
    def snapshot(self) -> Mapping[str, _StoredEntry]:
        return MappingProxyType(dict(self._state.entries))

    @property
    def events(self) -> tuple[ReplacementAdmissionEvent, ...]:
        return self._state.events

    @property
    def write_count(self) -> int:
        return self._state.write_count

    @property
    def mutation_count(self) -> int:
        return self._state.mutation_count

    @property
    def committed_request_ids(self) -> frozenset[str]:
        return self._state.committed_request_ids

    @property
    def used_approval_metadata_digests(self) -> frozenset[str]:
        return self._state.used_approval_metadata_digests

    @property
    def used_attestation_digests(self) -> frozenset[str]:
        return self._state.used_attestation_digests

    @property
    def transport_count(self) -> int:
        return 0

    @property
    def http_count(self) -> int:
        return 0

    def resolve_exact(
        self,
        *,
        entry_id: str,
        profile_id: str,
        profile_version: SemanticVersion,
        product_id: str,
        product_version: SemanticVersion,
        protocol_version: SemanticVersion,
        expected_status: RegistryStatus,
        fallback: bool = False,
        nearest_version: bool = False,
        infer_schema: bool = False,
        current_alias: bool = False,
        latest_alias: bool = False,
    ) -> _StoredEntry:
        if (
            fallback
            or nearest_version
            or infer_schema
            or current_alias
            or latest_alias
        ):
            _raise(ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        entry = self._state.entries.get(entry_id)
        if entry is None:
            _raise(ReplacementAdmissionReason.PREDECESSOR_NOT_FOUND)
        if (
            entry.profile_id != profile_id
            or entry.profile_version != profile_version
            or entry.product_id != product_id
            or entry.product_version != product_version
            or entry.protocol_version != protocol_version
            or entry.registry_status is not expected_status
        ):
            _raise(ReplacementAdmissionReason.IDENTITY_MISMATCH)
        return entry

    def find_by_digest(self, digest: str) -> _StoredEntry | None:
        matches = [
            entry
            for entry in self._state.entries.values()
            if entry.canonical_digest == digest
        ]
        return matches[0] if len(matches) == 1 else None

    def _disable_failure_injection(self) -> None:
        self._failure_point = None

    def _fail_if(self, point: ReplacementCommitFault) -> None:
        if self._failure_point is point:
            _raise(ReplacementAdmissionReason.REGISTRY_COMMIT_FAILED)

    def _duplicate_reasons(
        self, request: ReplacementAdmissionRequest
    ) -> set[ReplacementAdmissionReason]:
        reasons: set[ReplacementAdmissionReason] = set()
        if request.replacement_request_id in self._state.committed_request_ids:
            reasons.add(ReplacementAdmissionReason.DUPLICATE_REQUEST)
        if (
            request.old_registry_entry_digest
            in self._state.replaced_predecessor_digests
        ):
            reasons.add(
                ReplacementAdmissionReason.PREDECESSOR_ALREADY_REPLACED
            )
        if (
            request.old_registry_entry_digest,
            request.new_admission_decision_digest,
        ) in self._state.committed_pairs:
            reasons.add(ReplacementAdmissionReason.CHAIN_REUSE)
        if request.new_evidence_digest in self._state.used_evidence_digests:
            reasons.add(ReplacementAdmissionReason.CHAIN_REUSE)
        approval_digest = _approval_digest(
            request.new_production_admission_request.profile_approval_metadata
        )
        if approval_digest in self._state.used_approval_metadata_digests:
            reasons.add(ReplacementAdmissionReason.CHAIN_REUSE)
        if (
            request.new_attestation_digest
            in self._state.used_attestation_digests
        ):
            reasons.add(ReplacementAdmissionReason.CHAIN_REUSE)
        if (
            request.new_admission_decision_digest
            in self._state.used_decision_digests
        ):
            reasons.add(ReplacementAdmissionReason.CHAIN_REUSE)
        if request.replacement_entry_id in self._state.entries:
            reasons.add(ReplacementAdmissionReason.DUPLICATE_SUCCESSOR)
        if self._would_loop(request):
            reasons.add(ReplacementAdmissionReason.REPLACEMENT_LOOP)
        return reasons

    def _would_loop(self, request: ReplacementAdmissionRequest) -> bool:
        predecessor = self.find_by_digest(request.old_registry_entry_digest)
        if (
            predecessor is not None
            and request.replacement_entry_id == predecessor.admission_id
        ):
            return True
        ancestors: set[str] = {request.old_registry_entry_digest}
        current = request.old_registry_entry_digest
        links = {
            event.successor_entry_digest: event.predecessor_entry_digest
            for event in self._state.events
        }
        while current in links:
            current = links[current]
            if current in ancestors:
                return True
            ancestors.add(current)
        existing = self._state.entries.get(request.replacement_entry_id)
        return existing is not None and existing.canonical_digest in ancestors

    def _commit(
        self,
        request: ReplacementAdmissionRequest,
        successor: ReplacementRegistryEntry,
        event: ReplacementAdmissionEvent,
    ) -> None:
        current = self._state
        self._fail_if(ReplacementCommitFault.ENTRY_CANDIDATE)
        entries_candidate = MappingProxyType(
            {**current.entries, successor.replacement_entry_id: successor}
        )
        self._fail_if(ReplacementCommitFault.EVENT_CANDIDATE)
        events_candidate = (*current.events, event)
        approval_digest = _approval_digest(
            request.new_production_admission_request.profile_approval_metadata
        )
        self._fail_if(ReplacementCommitFault.COUNTER_AND_REQUEST_CANDIDATE)
        candidate = _ReplacementStoreState(
            entries=entries_candidate,
            events=events_candidate,
            write_count=current.write_count + 1,
            mutation_count=current.mutation_count + 1,
            committed_request_ids=current.committed_request_ids
            | {request.replacement_request_id},
            replaced_predecessor_digests=(
                current.replaced_predecessor_digests
                | {request.old_registry_entry_digest}
            ),
            committed_pairs=current.committed_pairs
            | {
                (
                    request.old_registry_entry_digest,
                    request.new_admission_decision_digest,
                )
            },
            used_approval_metadata_digests=(
                current.used_approval_metadata_digests
                | {approval_digest}
            ),
            used_attestation_digests=current.used_attestation_digests
            | {request.new_attestation_digest},
            used_evidence_digests=current.used_evidence_digests
            | {request.new_evidence_digest},
            used_decision_digests=current.used_decision_digests
            | {request.new_admission_decision_digest},
        )
        self._fail_if(ReplacementCommitFault.BEFORE_COMMIT)
        self._state = candidate

    def __repr__(self) -> str:
        return "TestReplacementAdmissionStore(<safe>)"


def evaluate_replacement_admission(
    request: ReplacementAdmissionRequest,
    *,
    predecessor_entry: RegistryAdmissionEntry | ReplacementRegistryEntry,
) -> ReplacementAdmissionDecision:
    if not isinstance(request, ReplacementAdmissionRequest) or not isinstance(
        predecessor_entry,
        (RegistryAdmissionEntry, ReplacementRegistryEntry),
    ):
        _raise(ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
    reasons: set[ReplacementAdmissionReason] = set()
    decision = request.new_admission_decision
    chain_request = request.new_production_admission_request
    plan = chain_request.manual_validation_plan
    evidence = chain_request.manual_validation_evidence
    attestation = chain_request.reviewer_attestation
    approval = chain_request.profile_approval_metadata
    predecessor_chain_request = (
        request.predecessor_production_admission_request
    )
    predecessor_chain_decision = evaluate_production_admission(
        predecessor_chain_request
    )
    predecessor_attestation = predecessor_chain_request.reviewer_attestation
    event = request.predecessor_lifecycle_event

    if (
        _digest(predecessor_entry.canonical_json())
        != predecessor_entry.canonical_digest
        or predecessor_entry.canonical_digest
        != request.old_registry_entry_digest
        or _digest(decision.canonical_json()) != decision.canonical_digest
        or predecessor_chain_decision.canonical_digest
        != predecessor_entry.admission_decision_digest
        or predecessor_chain_decision.plan_digest != predecessor_entry.plan_digest
        or predecessor_chain_decision.evidence_digest
        != predecessor_entry.evidence_digest
        or predecessor_attestation is None
        or predecessor_chain_decision.reviewer_attestation_digest
        != predecessor_entry.reviewer_attestation_digest
    ):
        reasons.add(ReplacementAdmissionReason.DIGEST_MISMATCH)
    if (
        request.old_profile_id != predecessor_entry.profile_id
        or request.old_profile_version != predecessor_entry.profile_version
        or request.old_product_id != predecessor_entry.product_id
        or request.old_product_version != predecessor_entry.product_version
        or request.old_protocol_version != predecessor_entry.protocol_version
        or request.expected_old_status is not predecessor_entry.registry_status
    ):
        reasons.add(ReplacementAdmissionReason.IDENTITY_MISMATCH)
    expected_decision = evaluate_production_admission(chain_request)
    if (
        expected_decision.canonical_digest != decision.canonical_digest
        or request.new_plan_digest != plan.canonical_digest
        or request.new_evidence_digest != evidence.canonical_digest
        or attestation is None
        or request.new_attestation_digest
        != (attestation.canonical_digest if attestation else None)
        or request.new_admission_decision_digest != decision.canonical_digest
        or decision.plan_digest != plan.canonical_digest
        or decision.evidence_digest != evidence.canonical_digest
        or decision.reviewer_attestation_digest
        != (attestation.canonical_digest if attestation else None)
    ):
        reasons.add(ReplacementAdmissionReason.DIGEST_MISMATCH)
    if (
        event.admission_id != predecessor_entry.admission_id
        or event.resulting_entry_digest != predecessor_entry.canonical_digest
        or event.new_status != predecessor_entry.registry_status.value
        or event.profile_id != predecessor_entry.profile_id
        or event.profile_version != str(predecessor_entry.profile_version)
        or event.product_id != predecessor_entry.product_id
        or event.product_version != str(predecessor_entry.product_version)
        or event.protocol_version != str(predecessor_entry.protocol_version)
    ):
        reasons.add(ReplacementAdmissionReason.IDENTITY_MISMATCH)
    if decision.profile_id != predecessor_entry.profile_id:
        reasons.add(ReplacementAdmissionReason.IDENTITY_MISMATCH)
    identity_changed = (
        decision.profile_version != str(predecessor_entry.profile_version)
        or decision.product_id != predecessor_entry.product_id
        or decision.product_version != str(predecessor_entry.product_version)
        or decision.protocol_version != str(predecessor_entry.protocol_version)
    )
    if identity_changed and request.replacement_reason.value not in (
        _VERSION_CHANGE_REASONS
    ):
        reasons.add(ReplacementAdmissionReason.IDENTITY_MISMATCH)

    if predecessor_entry.registry_status not in (
        _ELIGIBLE_PREDECESSOR_STATUSES
    ):
        reasons.add(ReplacementAdmissionReason.PREDECESSOR_STATUS_INELIGIBLE)
    if (
        request.new_plan_digest == predecessor_entry.plan_digest
        or request.new_evidence_digest == predecessor_entry.evidence_digest
        or request.new_attestation_digest
        == predecessor_entry.reviewer_attestation_digest
        or request.new_admission_decision_digest
        == predecessor_entry.admission_decision_digest
        or _approval_digest(approval)
        == _approval_digest(
            predecessor_chain_request.profile_approval_metadata
        )
    ):
        reasons.add(ReplacementAdmissionReason.CHAIN_REUSE)
    if evidence.execution_completed_at <= predecessor_entry.admitted_at:
        reasons.add(ReplacementAdmissionReason.STALE_CHAIN)
    if request.evaluation_time >= evidence.expires_at:
        reasons.add(ReplacementAdmissionReason.EVIDENCE_EXPIRED)
        reasons.add(ReplacementAdmissionReason.REVALIDATION_REQUIRED)
    if not decision.eligible_for_registry_admission or decision.reason_categories:
        if any(
            reason
            in {
                ProductionAdmissionReason.EVIDENCE_EXPIRED,
                ProductionAdmissionReason.REVALIDATION_REQUIRED,
            }
            for reason in decision.reason_categories
        ):
            reasons.add(ReplacementAdmissionReason.REVALIDATION_REQUIRED)
        else:
            reasons.add(
                ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION
            )
    if attestation is not None:
        roles = (
            plan.validation_operator_id,
            attestation.reviewer_id,
            approval.approver_id,
            request.registry_administrator_id,
        )
        if (
            len(set(roles)) != len(roles)
            or decision.validation_operator_id != roles[0]
            or decision.evidence_reviewer_id != roles[1]
            or decision.approver_id != roles[2]
        ):
            reasons.add(ReplacementAdmissionReason.ROLE_CONFLICT)
        event_time = _parse_datetime(event.transitioned_at)
        if not (
            evidence.execution_completed_at
            < attestation.reviewed_at
            < approval.approved_at
            <= decision.evaluated_at
            <= request.evaluation_time
        ) or event_time > request.evaluation_time:
            reasons.add(ReplacementAdmissionReason.TEMPORAL_INVALID)
    if decision.effective_restrictions != approval.restrictions:
        reasons.add(ReplacementAdmissionReason.RESTRICTION_MISMATCH)
    if (
        predecessor_entry.restrictions != decision.effective_restrictions
        and request.replacement_reason
        is not ReplacementReason.RESTRICTION_REVALIDATED
    ):
        reasons.add(ReplacementAdmissionReason.RESTRICTION_MISMATCH)
    return _decision(request, predecessor_entry, reasons)


def enforce_replacement_admission(
    request: ReplacementAdmissionRequest,
    *,
    registry: object,
) -> ReplacementAdmissionResult:
    if not isinstance(request, ReplacementAdmissionRequest):
        _raise(ReplacementAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
    if not isinstance(registry, TestReplacementAdmissionStore):
        return _denied_result(
            request,
            predecessor=None,
            reasons={ReplacementAdmissionReason.REGISTRY_WRITE_REJECTED},
        )
    predecessor = registry.find_by_digest(request.old_registry_entry_digest)
    if predecessor is None:
        return _denied_result(
            request,
            predecessor=None,
            reasons={ReplacementAdmissionReason.PREDECESSOR_NOT_FOUND},
        )
    decision = evaluate_replacement_admission(
        request, predecessor_entry=predecessor
    )
    reasons = set(decision.reason_categories)
    reasons.update(registry._duplicate_reasons(request))
    if reasons:
        return _denied_result(request, predecessor=predecessor, reasons=reasons)
    successor = _successor(request, predecessor)
    event = _event(request, predecessor, successor)
    result = _applied_result(request, predecessor, successor, event)
    try:
        registry._commit(request, successor, event)
    except Exception:
        return _denied_result(
            request,
            predecessor=predecessor,
            reasons={ReplacementAdmissionReason.REGISTRY_COMMIT_FAILED},
        )
    return result


def _decision(
    request: ReplacementAdmissionRequest,
    predecessor: RegistryAdmissionEntry | ReplacementRegistryEntry,
    reasons: set[ReplacementAdmissionReason],
) -> ReplacementAdmissionDecision:
    ordered = tuple(reason for reason in _REASON_ORDER if reason in reasons)
    revalidation_only = bool(ordered) and all(
        reason
        in {
            ReplacementAdmissionReason.STALE_CHAIN,
            ReplacementAdmissionReason.EVIDENCE_EXPIRED,
            ReplacementAdmissionReason.REVALIDATION_REQUIRED,
        }
        for reason in ordered
    )
    status = (
        ReplacementDecisionStatus.ELIGIBLE
        if not ordered
        else (
            ReplacementDecisionStatus.NEEDS_REVALIDATION
            if revalidation_only
            else ReplacementDecisionStatus.REJECTED
        )
    )
    decision = request.new_admission_decision
    return ReplacementAdmissionDecision(
        replacement_request_id=request.replacement_request_id,
        decision=status,
        predecessor_entry_id=predecessor.admission_id,
        predecessor_entry_digest=predecessor.canonical_digest,
        predecessor_status=predecessor.registry_status,
        successor_entry_id=request.replacement_entry_id,
        successor_profile_id=decision.profile_id,
        successor_profile_version=SemanticVersion.parse(
            decision.profile_version
        ),
        successor_product_id=decision.product_id,
        successor_product_version=SemanticVersion.parse(
            decision.product_version
        ),
        successor_protocol_version=SemanticVersion.parse(
            decision.protocol_version
        ),
        new_plan_digest=request.new_plan_digest,
        new_evidence_digest=request.new_evidence_digest,
        new_attestation_digest=request.new_attestation_digest,
        new_admission_decision_digest=(
            request.new_admission_decision_digest
        ),
        effective_restrictions=decision.effective_restrictions,
        reason_categories=ordered,
        evaluated_at=request.evaluation_time,
    )


def _successor(
    request: ReplacementAdmissionRequest,
    predecessor: RegistryAdmissionEntry | ReplacementRegistryEntry,
) -> ReplacementRegistryEntry:
    decision = request.new_admission_decision
    return ReplacementRegistryEntry(
        replacement_entry_id=request.replacement_entry_id,
        predecessor_entry_digest=predecessor.canonical_digest,
        predecessor_status=predecessor.registry_status,
        replacement_request_digest=request.canonical_digest,
        profile_id=decision.profile_id,
        profile_version=SemanticVersion.parse(decision.profile_version),
        product_id=decision.product_id,
        product_version=SemanticVersion.parse(decision.product_version),
        protocol_version=SemanticVersion.parse(decision.protocol_version),
        plan_digest=request.new_plan_digest,
        evidence_digest=request.new_evidence_digest,
        reviewer_attestation_digest=request.new_attestation_digest,
        admission_decision_digest=request.new_admission_decision_digest,
        admitted_at=request.evaluation_time,
        registry_administrator_id=request.registry_administrator_id,
        registry_status=RegistryStatus.ACTIVE,
        effective_restrictions=decision.effective_restrictions,
    )


def _event(
    request: ReplacementAdmissionRequest,
    predecessor: RegistryAdmissionEntry | ReplacementRegistryEntry,
    successor: ReplacementRegistryEntry,
) -> ReplacementAdmissionEvent:
    return ReplacementAdmissionEvent(
        replacement_request_id=request.replacement_request_id,
        predecessor_entry_id=predecessor.admission_id,
        predecessor_entry_digest=predecessor.canonical_digest,
        successor_entry_id=successor.replacement_entry_id,
        successor_entry_digest=successor.canonical_digest,
        predecessor_status=predecessor.registry_status,
        successor_status=RegistryStatus.ACTIVE,
        replacement_reason=request.replacement_reason,
        transitioned_at=request.evaluation_time,
        actor_id=request.registry_administrator_id,
        replacement_request_digest=request.canonical_digest,
        plan_digest=request.new_plan_digest,
        evidence_digest=request.new_evidence_digest,
        attestation_digest=request.new_attestation_digest,
        admission_decision_digest=request.new_admission_decision_digest,
    )


def _applied_result(
    request: ReplacementAdmissionRequest,
    predecessor: RegistryAdmissionEntry | ReplacementRegistryEntry,
    successor: ReplacementRegistryEntry,
    event: ReplacementAdmissionEvent,
) -> ReplacementAdmissionResult:
    return ReplacementAdmissionResult(
        replacement_request_id=request.replacement_request_id,
        applied=True,
        predecessor_entry_id=predecessor.admission_id,
        predecessor_entry_digest=predecessor.canonical_digest,
        predecessor_status=predecessor.registry_status,
        successor_entry_id=successor.replacement_entry_id,
        successor_entry_digest=successor.canonical_digest,
        successor_status=RegistryStatus.ACTIVE,
        reason_categories=(),
        replacement_request_digest=request.canonical_digest,
        new_plan_digest=request.new_plan_digest,
        new_evidence_digest=request.new_evidence_digest,
        new_attestation_digest=request.new_attestation_digest,
        new_admission_decision_digest=request.new_admission_decision_digest,
        replacement_event_digest=event.canonical_digest,
        evaluated_at=request.evaluation_time,
        applied_at=request.evaluation_time,
        successor_entry=successor,
        event=event,
    )


def _denied_result(
    request: ReplacementAdmissionRequest,
    *,
    predecessor: RegistryAdmissionEntry | ReplacementRegistryEntry | None,
    reasons: set[ReplacementAdmissionReason],
) -> ReplacementAdmissionResult:
    return ReplacementAdmissionResult(
        replacement_request_id=request.replacement_request_id,
        applied=False,
        predecessor_entry_id=(
            predecessor.admission_id
            if predecessor is not None
            else request.predecessor_lifecycle_event.admission_id
        ),
        predecessor_entry_digest=(
            predecessor.canonical_digest
            if predecessor is not None
            else request.old_registry_entry_digest
        ),
        predecessor_status=(
            predecessor.registry_status
            if predecessor is not None
            else request.expected_old_status
        ),
        successor_entry_id=None,
        successor_entry_digest=None,
        successor_status=None,
        reason_categories=tuple(
            reason for reason in _REASON_ORDER if reason in reasons
        ),
        replacement_request_digest=request.canonical_digest,
        new_plan_digest=request.new_plan_digest,
        new_evidence_digest=request.new_evidence_digest,
        new_attestation_digest=request.new_attestation_digest,
        new_admission_decision_digest=request.new_admission_decision_digest,
        replacement_event_digest=None,
        evaluated_at=request.evaluation_time,
        applied_at=None,
        successor_entry=None,
        event=None,
    )


def _canonical_restrictions(
    restrictions: ApprovalRestrictions | None,
) -> dict[str, object] | None:
    if restrictions is None:
        return None
    return {
        "expires_at": _optional_datetime(restrictions.expires_at),
        "matched_keywords_disabled": restrictions.matched_keywords_disabled,
        "maximum_top_k": restrictions.maximum_top_k,
        "query_id_echo_required": restrictions.query_id_echo_required,
        "score_disabled": restrictions.score_disabled,
        "supported_minor_versions": list(
            restrictions.supported_minor_versions
        ),
        "title_disabled": restrictions.title_disabled,
    }


def _approval_digest(approval: ApprovalMetadata) -> str:
    version_range = approval.supported_product_version_range
    return _digest(
        _canonical_json(
            {
                "approval_record_id": approval.approval_record_id,
                "approved_at": _canonical_datetime(approval.approved_at),
                "approved_capabilities": list(
                    approval.approved_capabilities
                ),
                "approved_score_semantics": (
                    approval.approved_score_semantics.value
                ),
                "approved_source_identifier_policy": (
                    approval.approved_source_identifier_policy.value
                ),
                "approver_id": approval.approver_id,
                "decision": approval.decision.value,
                "expires_at": _optional_datetime(approval.expires_at),
                "restrictions": _canonical_restrictions(
                    approval.restrictions
                ),
                "reviewer_id": approval.reviewer_id,
                "supported_product_version_range": {
                    "maximum_version": (
                        None
                        if version_range.maximum_version is None
                        else str(version_range.maximum_version)
                    ),
                    "minimum_version": str(version_range.minimum_version),
                    "open_ended": version_range.open_ended,
                },
                "validation_record_id": approval.validation_record_id,
            }
        )
    )


def _restriction_count(restrictions: ApprovalRestrictions | None) -> int:
    mapping = _canonical_restrictions(restrictions)
    if mapping is None:
        return 0
    return sum(value not in (None, False, [], ()) for value in mapping.values())


def _is_safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_safe_context(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and tuple(sorted(set(value))) == value
        and all(
            isinstance(item, str) and item in _SAFE_CONTEXT_VALUES
            for item in value
        )
    )


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


def _optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else _canonical_datetime(value)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not _is_aware_datetime(parsed):
        _raise(ReplacementAdmissionReason.TEMPORAL_INVALID)
    return parsed


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _raise(category: ReplacementAdmissionReason) -> None:
    raise ReplacementAdmissionError(category) from None


__all__ = [
    "CANONICAL_REPLACEMENT_ADMISSION_DIGEST_ALGORITHM",
    "ReplacementAdmissionDecision",
    "ReplacementAdmissionDecisionSafeSummary",
    "ReplacementAdmissionError",
    "ReplacementAdmissionEvent",
    "ReplacementAdmissionReason",
    "ReplacementAdmissionRequest",
    "ReplacementAdmissionRequestSafeSummary",
    "ReplacementAdmissionResult",
    "ReplacementAdmissionResultSafeSummary",
    "ReplacementCommitFault",
    "ReplacementDecisionStatus",
    "ReplacementReason",
    "ReplacementRegistryEntry",
    "ReplacementRegistryEntrySafeSummary",
    "TestReplacementAdmissionStore",
    "enforce_replacement_admission",
    "evaluate_replacement_admission",
]
