from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import ClassVar, Mapping

from ragguard.compatibility import SemanticVersion
from ragguard.production_admission import (
    ProductionAdmissionDecision,
    ProductionAdmissionReason,
)
from ragguard.production_registry import (
    RegistryKind,
    RegistryStatus,
)
from ragguard.profile_approval import (
    ApprovalDecision,
    ApprovalRestrictions,
    ProfileMaturity,
)


CANONICAL_REGISTRY_ADMISSION_DIGEST_ALGORITHM = "sha256"
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
_ALLOWED_DECISIONS = frozenset(
    {
        ApprovalDecision.APPROVED,
        ApprovalDecision.APPROVED_WITH_RESTRICTIONS,
    }
)
_TEST_STATUS_TRANSITIONS = frozenset(
    {
        (RegistryStatus.ACTIVE, RegistryStatus.SUSPENDED),
        (RegistryStatus.ACTIVE, RegistryStatus.DEPRECATED),
        (RegistryStatus.ACTIVE, RegistryStatus.REVOKED),
        (RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED),
        (RegistryStatus.SUSPENDED, RegistryStatus.REVOKED),
        (RegistryStatus.DEPRECATED, RegistryStatus.REVOKED),
    }
)


class RegistryAdmissionReason(str, Enum):
    DECISION_INELIGIBLE = "decision_ineligible"
    DECISION_INVALID = "decision_invalid"
    DECISION_NOT_YET_VALID = "decision_not_yet_valid"
    DECISION_EXPIRED = "decision_expired"
    IDENTITY_MISMATCH = "identity_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    ROLE_CONFLICT = "role_conflict"
    RESTRICTION_MISMATCH = "restriction_mismatch"
    REGISTRY_KIND_INVALID = "registry_kind_invalid"
    INITIAL_STATUS_INVALID = "initial_status_invalid"
    DUPLICATE_ENTRY = "duplicate_entry"
    STATUS_INELIGIBLE = "status_ineligible"
    REVALIDATION_REQUIRED = "revalidation_required"
    SECURITY_BOUNDARY_VIOLATION = "security_boundary_violation"
    REGISTRY_WRITE_REJECTED = "registry_write_rejected"
    REGISTRY_COMMIT_FAILED = "registry_commit_failed"


_REASON_ORDER = tuple(RegistryAdmissionReason)


class RegistryAdmissionError(ValueError):
    def __init__(self, category: RegistryAdmissionReason) -> None:
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True)
class RegistryAdmissionRequestSafeSummary:
    admission_id: str
    evaluation_time: str
    decision: str
    profile_id: str
    profile_version: str
    protocol_version: str
    product_id: str
    product_version: str
    registry_kind: str
    initial_status: str
    restriction_count: int
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class RegistryAdmissionRequest:
    admission_id: str
    evaluation_time: datetime
    production_admission_decision: ProductionAdmissionDecision
    expected_profile_id: str
    expected_profile_version: SemanticVersion
    expected_protocol_version: SemanticVersion
    expected_product_id: str
    expected_product_version: SemanticVersion
    requested_registry_kind: RegistryKind
    requested_initial_status: RegistryStatus
    expected_restrictions: ApprovalRestrictions | None
    registry_administrator_id: str
    approver_id: str
    evidence_reviewer_id: str
    validation_operator_id: str
    evidence_expires_at: datetime
    validation_expires_at: datetime | None
    approval_expires_at: datetime | None
    safe_context: tuple[str, ...]
    safe_summary: RegistryAdmissionRequestSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = (
        CANONICAL_REGISTRY_ADMISSION_DIGEST_ALGORITHM
    )

    def __post_init__(self) -> None:
        identifiers = (
            self.admission_id,
            self.expected_profile_id,
            self.expected_product_id,
            self.registry_administrator_id,
            self.approver_id,
            self.evidence_reviewer_id,
            self.validation_operator_id,
        )
        if (
            not all(_is_safe_identifier(value) for value in identifiers)
            or not _is_aware_datetime(self.evaluation_time)
            or not isinstance(
                self.production_admission_decision,
                ProductionAdmissionDecision,
            )
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.expected_profile_version,
                    self.expected_protocol_version,
                    self.expected_product_version,
                )
            )
            or not isinstance(self.requested_registry_kind, RegistryKind)
            or not isinstance(self.requested_initial_status, RegistryStatus)
            or (
                self.expected_restrictions is not None
                and not isinstance(
                    self.expected_restrictions, ApprovalRestrictions
                )
            )
        ):
            _raise(RegistryAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        if self.requested_registry_kind is not RegistryKind.PRODUCTION:
            _raise(RegistryAdmissionReason.REGISTRY_KIND_INVALID)
        if self.requested_initial_status is not RegistryStatus.ACTIVE:
            _raise(RegistryAdmissionReason.INITIAL_STATUS_INVALID)
        if not _is_aware_datetime(self.evidence_expires_at):
            _raise(RegistryAdmissionReason.DECISION_EXPIRED)
        for value in (
            self.validation_expires_at,
            self.approval_expires_at,
        ):
            if value is not None and not _is_aware_datetime(value):
                _raise(RegistryAdmissionReason.DECISION_EXPIRED)
        if (
            not isinstance(self.safe_context, tuple)
            or tuple(sorted(set(self.safe_context))) != self.safe_context
            or any(
                not isinstance(value, str)
                or value not in _SAFE_CONTEXT_VALUES
                for value in self.safe_context
            )
        ):
            _raise(RegistryAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            RegistryAdmissionRequestSafeSummary(
                admission_id=self.admission_id,
                evaluation_time=_canonical_datetime(self.evaluation_time),
                decision=self.production_admission_decision.decision.value,
                profile_id=self.expected_profile_id,
                profile_version=str(self.expected_profile_version),
                protocol_version=str(self.expected_protocol_version),
                product_id=self.expected_product_id,
                product_version=str(self.expected_product_version),
                registry_kind=self.requested_registry_kind.value,
                initial_status=self.requested_initial_status.value,
                restriction_count=_restriction_count(
                    self.expected_restrictions
                ),
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        decision = self.production_admission_decision
        return _canonical_json(
            {
                "admission_id": self.admission_id,
                "approval_expires_at": _optional_datetime(
                    self.approval_expires_at
                ),
                "approver_id": self.approver_id,
                "decision_digest": decision.canonical_digest,
                "evaluation_time": _canonical_datetime(self.evaluation_time),
                "evidence_expires_at": _canonical_datetime(
                    self.evidence_expires_at
                ),
                "evidence_reviewer_id": self.evidence_reviewer_id,
                "expected_product_id": self.expected_product_id,
                "expected_product_version": str(
                    self.expected_product_version
                ),
                "expected_profile_id": self.expected_profile_id,
                "expected_profile_version": str(
                    self.expected_profile_version
                ),
                "expected_protocol_version": str(
                    self.expected_protocol_version
                ),
                "expected_restrictions": _canonical_restrictions(
                    self.expected_restrictions
                ),
                "registry_administrator_id": (
                    self.registry_administrator_id
                ),
                "requested_initial_status": (
                    self.requested_initial_status.value
                ),
                "requested_registry_kind": (
                    self.requested_registry_kind.value
                ),
                "safe_context": list(self.safe_context),
                "validation_expires_at": _optional_datetime(
                    self.validation_expires_at
                ),
                "validation_operator_id": self.validation_operator_id,
            }
        )

    def __repr__(self) -> str:
        return "RegistryAdmissionRequest(<safe>)"


@dataclass(frozen=True)
class RegistryAdmissionEntrySafeSummary:
    admission_id: str
    profile_id: str
    profile_version: str
    protocol_version: str
    product_id: str
    product_version: str
    registry_status: str
    approval_decision: str
    approval_digest: str
    restriction_count: int
    admission_decision_digest: str
    admitted_at: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class RegistryAdmissionEntry:
    admission_id: str
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    maturity: ProfileMaturity
    approval_decision: ApprovalDecision
    approval_digest: str
    restrictions: ApprovalRestrictions | None
    plan_digest: str
    evidence_digest: str
    reviewer_attestation_digest: str
    admission_decision_digest: str
    admitted_at: datetime
    registry_administrator_id: str
    registry_status: RegistryStatus
    registry_kind: RegistryKind
    safe_summary: RegistryAdmissionEntrySafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = (
        CANONICAL_REGISTRY_ADMISSION_DIGEST_ALGORITHM
    )

    def __post_init__(self) -> None:
        if (
            not all(
                _is_safe_identifier(value)
                for value in (
                    self.admission_id,
                    self.profile_id,
                    self.product_id,
                    self.registry_administrator_id,
                )
            )
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.profile_version,
                    self.protocol_version,
                    self.product_version,
                )
            )
            or self.maturity is not ProfileMaturity.APPROVED
            or self.approval_decision not in _ALLOWED_DECISIONS
            or (
                self.restrictions is not None
                and not isinstance(self.restrictions, ApprovalRestrictions)
            )
            or not all(
                _is_digest(value)
                for value in (
                    self.approval_digest,
                    self.plan_digest,
                    self.evidence_digest,
                    self.reviewer_attestation_digest,
                    self.admission_decision_digest,
                )
            )
            or not _is_aware_datetime(self.admitted_at)
            or not isinstance(self.registry_status, RegistryStatus)
            or self.registry_kind is not RegistryKind.PRODUCTION
        ):
            _raise(RegistryAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        if (
            self.approval_decision
            is ApprovalDecision.APPROVED_WITH_RESTRICTIONS
        ):
            if (
                self.restrictions is None
                or self.restrictions.is_empty
            ):
                _raise(RegistryAdmissionReason.RESTRICTION_MISMATCH)
        elif self.restrictions is not None:
            _raise(RegistryAdmissionReason.RESTRICTION_MISMATCH)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            RegistryAdmissionEntrySafeSummary(
                admission_id=self.admission_id,
                profile_id=self.profile_id,
                profile_version=str(self.profile_version),
                protocol_version=str(self.protocol_version),
                product_id=self.product_id,
                product_version=str(self.product_version),
                registry_status=self.registry_status.value,
                approval_decision=self.approval_decision.value,
                approval_digest=self.approval_digest,
                restriction_count=_restriction_count(self.restrictions),
                admission_decision_digest=self.admission_decision_digest,
                admitted_at=_canonical_datetime(self.admitted_at),
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "approval_digest": self.approval_digest,
                "admission_decision_digest": (
                    self.admission_decision_digest
                ),
                "admission_id": self.admission_id,
                "admitted_at": _canonical_datetime(self.admitted_at),
                "approval_decision": self.approval_decision.value,
                "evidence_digest": self.evidence_digest,
                "maturity": self.maturity.value,
                "plan_digest": self.plan_digest,
                "product_id": self.product_id,
                "product_version": str(self.product_version),
                "profile_id": self.profile_id,
                "profile_version": str(self.profile_version),
                "protocol_version": str(self.protocol_version),
                "registry_administrator_id": (
                    self.registry_administrator_id
                ),
                "registry_kind": self.registry_kind.value,
                "registry_status": self.registry_status.value,
                "restrictions": _canonical_restrictions(self.restrictions),
                "reviewer_attestation_digest": (
                    self.reviewer_attestation_digest
                ),
            }
        )

    def __repr__(self) -> str:
        return "RegistryAdmissionEntry(<safe>)"


@dataclass(frozen=True)
class RegistryAdmissionSafeSummary:
    admission_id: str
    admitted: bool
    decision: str
    registry_kind: str
    initial_status: str
    profile_id: str
    profile_version: str
    protocol_version: str
    product_id: str
    product_version: str
    plan_digest: str
    evidence_digest: str
    reviewer_attestation_digest: str | None
    admission_decision_digest: str
    restriction_count: int
    reason_categories: tuple[str, ...]
    evaluation_time: str
    admitted_at: str | None
    admission_digest: str


@dataclass(frozen=True, repr=False)
class RegistryAdmissionResult:
    admission_id: str
    admitted: bool
    registry_kind: RegistryKind
    initial_status: RegistryStatus
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    decision: ApprovalDecision
    entry_identity: str | None
    plan_digest: str
    evidence_digest: str
    reviewer_attestation_digest: str | None
    admission_decision_digest: str
    effective_restrictions: ApprovalRestrictions | None
    reason_categories: tuple[RegistryAdmissionReason, ...]
    evaluation_time: datetime
    admitted_at: datetime | None
    entry: RegistryAdmissionEntry | None = field(repr=False)
    safe_summary: RegistryAdmissionSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = (
        CANONICAL_REGISTRY_ADMISSION_DIGEST_ALGORITHM
    )

    def __post_init__(self) -> None:
        if (
            not _is_safe_identifier(self.admission_id)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.profile_version,
                    self.protocol_version,
                    self.product_version,
                )
            )
            or not isinstance(self.registry_kind, RegistryKind)
            or not isinstance(self.initial_status, RegistryStatus)
            or not isinstance(self.decision, ApprovalDecision)
            or not _is_aware_datetime(self.evaluation_time)
            or tuple(
                reason
                for reason in _REASON_ORDER
                if reason in self.reason_categories
            )
            != self.reason_categories
        ):
            _raise(RegistryAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        if self.admitted:
            if (
                self.entry is None
                or self.entry_identity != self.entry.admission_id
                or self.admitted_at is None
                or not _is_aware_datetime(self.admitted_at)
                or self.reason_categories
            ):
                _raise(RegistryAdmissionReason.REGISTRY_COMMIT_FAILED)
        elif (
            self.entry is not None
            or self.entry_identity is not None
            or self.admitted_at is not None
            or not self.reason_categories
        ):
            _raise(RegistryAdmissionReason.REGISTRY_COMMIT_FAILED)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            RegistryAdmissionSafeSummary(
                admission_id=self.admission_id,
                admitted=self.admitted,
                decision=self.decision.value,
                registry_kind=self.registry_kind.value,
                initial_status=self.initial_status.value,
                profile_id=self.profile_id,
                profile_version=str(self.profile_version),
                protocol_version=str(self.protocol_version),
                product_id=self.product_id,
                product_version=str(self.product_version),
                plan_digest=self.plan_digest,
                evidence_digest=self.evidence_digest,
                reviewer_attestation_digest=(
                    self.reviewer_attestation_digest
                ),
                admission_decision_digest=(
                    self.admission_decision_digest
                ),
                restriction_count=_restriction_count(
                    self.effective_restrictions
                ),
                reason_categories=tuple(
                    reason.value for reason in self.reason_categories
                ),
                evaluation_time=_canonical_datetime(self.evaluation_time),
                admitted_at=_optional_datetime(self.admitted_at),
                admission_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "admission_decision_digest": (
                    self.admission_decision_digest
                ),
                "admission_id": self.admission_id,
                "admitted": self.admitted,
                "admitted_at": _optional_datetime(self.admitted_at),
                "decision": self.decision.value,
                "effective_restrictions": _canonical_restrictions(
                    self.effective_restrictions
                ),
                "entry_identity": self.entry_identity,
                "evaluation_time": _canonical_datetime(self.evaluation_time),
                "evidence_digest": self.evidence_digest,
                "initial_status": self.initial_status.value,
                "plan_digest": self.plan_digest,
                "product_id": self.product_id,
                "product_version": str(self.product_version),
                "profile_id": self.profile_id,
                "profile_version": str(self.profile_version),
                "protocol_version": str(self.protocol_version),
                "reason_categories": [
                    reason.value for reason in self.reason_categories
                ],
                "registry_kind": self.registry_kind.value,
                "reviewer_attestation_digest": (
                    self.reviewer_attestation_digest
                ),
            }
        )

    def __repr__(self) -> str:
        return "RegistryAdmissionResult(<safe>)"


@dataclass(frozen=True)
class RegistryAdmissionEvent:
    admission_id: str
    profile_id: str
    profile_version: str
    category: str = "test_registry_admitted"


_TestRegistryEntryKey = tuple[
    str,
    SemanticVersion,
    str,
    SemanticVersion,
    SemanticVersion,
]


@dataclass(frozen=True)
class _TestRegistryAdmissionState:
    entries: Mapping[_TestRegistryEntryKey, RegistryAdmissionEntry]
    events: tuple[RegistryAdmissionEvent, ...]
    write_count: int
    extension_state: object | None = None


class TestRegistryAdmissionStore:
    __test__ = False

    def __init__(self) -> None:
        self._state = _TestRegistryAdmissionState(
            entries=MappingProxyType({}),
            events=(),
            write_count=0,
        )

    @property
    def kind(self) -> RegistryKind:
        return RegistryKind.TEST

    @property
    def snapshot(
        self,
    ) -> Mapping[
        tuple[
            str,
            SemanticVersion,
            str,
            SemanticVersion,
            SemanticVersion,
        ],
        RegistryAdmissionEntry,
    ]:
        return MappingProxyType(dict(self._state.entries))

    @property
    def events(self) -> tuple[RegistryAdmissionEvent, ...]:
        return self._state.events

    @property
    def write_count(self) -> int:
        return self._state.write_count

    @property
    def transport_count(self) -> int:
        return 0

    @property
    def http_count(self) -> int:
        return 0

    def contains_profile_version(
        self,
        profile_id: str,
        profile_version: SemanticVersion,
    ) -> bool:
        return any(
            key[0] == profile_id and key[1] == profile_version
            for key in self._state.entries
        )

    def profile_version_status(
        self,
        profile_id: str,
        profile_version: SemanticVersion,
    ) -> RegistryStatus | None:
        for key, entry in self._state.entries.items():
            if key[0] == profile_id and key[1] == profile_version:
                return entry.registry_status
        return None

    def resolve_exact(
        self,
        *,
        profile_id: str,
        profile_version: SemanticVersion,
        product_id: str,
        product_version: SemanticVersion,
        protocol_version: SemanticVersion,
        fallback: bool = False,
        nearest_version: bool = False,
        infer_schema: bool = False,
    ) -> RegistryAdmissionEntry:
        if fallback or nearest_version or infer_schema:
            _raise(RegistryAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
        if (
            not _is_safe_identifier(profile_id)
            or not _is_safe_identifier(product_id)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    profile_version,
                    product_version,
                    protocol_version,
                )
            )
        ):
            _raise(RegistryAdmissionReason.IDENTITY_MISMATCH)
        entry = self._state.entries.get(
            (
                profile_id,
                profile_version,
                product_id,
                product_version,
                protocol_version,
            )
        )
        if entry is None:
            _raise(RegistryAdmissionReason.IDENTITY_MISMATCH)
        if entry.registry_status is not RegistryStatus.ACTIVE:
            _raise(RegistryAdmissionReason.STATUS_INELIGIBLE)
        return entry

    def transition_status(
        self,
        *,
        profile_id: str,
        profile_version: SemanticVersion,
        target: RegistryStatus,
    ) -> None:
        matches = [
            (key, entry)
            for key, entry in self._state.entries.items()
            if key[0] == profile_id and key[1] == profile_version
        ]
        if len(matches) != 1 or not isinstance(target, RegistryStatus):
            _raise(RegistryAdmissionReason.STATUS_INELIGIBLE)
        key, entry = matches[0]
        if (entry.registry_status, target) not in _TEST_STATUS_TRANSITIONS:
            _raise(RegistryAdmissionReason.STATUS_INELIGIBLE)
        self._state = _TestRegistryAdmissionState(
            entries=MappingProxyType(
                {
                    **self._state.entries,
                    key: replace(entry, registry_status=target),
                }
            ),
            events=self._state.events,
            write_count=self._state.write_count,
            extension_state=self._state.extension_state,
        )

    @property
    def _test_extension_state(self) -> object | None:
        return self._state.extension_state

    def _build_replacement_entries_candidate(
        self,
        *,
        expected_entry: RegistryAdmissionEntry,
        replacement_entry: RegistryAdmissionEntry,
    ) -> Mapping[_TestRegistryEntryKey, RegistryAdmissionEntry]:
        expected_key = _entry_key(expected_entry)
        if (
            _entry_key(replacement_entry) != expected_key
            or self._state.entries.get(expected_key) != expected_entry
        ):
            _raise(RegistryAdmissionReason.STATUS_INELIGIBLE)
        return MappingProxyType(
            {
                **self._state.entries,
                expected_key: replacement_entry,
            }
        )

    def _build_test_state_bundle(
        self,
        *,
        entries: Mapping[_TestRegistryEntryKey, RegistryAdmissionEntry],
        extension_state: object,
    ) -> _TestRegistryAdmissionState:
        return _TestRegistryAdmissionState(
            entries=MappingProxyType(dict(entries)),
            events=self._state.events,
            write_count=self._state.write_count,
            extension_state=extension_state,
        )

    def _replace_test_state_bundle(
        self,
        candidate: _TestRegistryAdmissionState,
    ) -> None:
        if not isinstance(candidate, _TestRegistryAdmissionState):
            _raise(RegistryAdmissionReason.STATUS_INELIGIBLE)
        self._state = candidate

    def _commit(self, entry: RegistryAdmissionEntry) -> None:
        key = _entry_key(entry)
        if key in self._state.entries or self.contains_profile_version(
            entry.profile_id, entry.profile_version
        ):
            _raise(RegistryAdmissionReason.DUPLICATE_ENTRY)
        event = RegistryAdmissionEvent(
            admission_id=entry.admission_id,
            profile_id=entry.profile_id,
            profile_version=str(entry.profile_version),
        )
        self._state = _TestRegistryAdmissionState(
            entries=MappingProxyType({**self._state.entries, key: entry}),
            events=(*self._state.events, event),
            write_count=self._state.write_count + 1,
            extension_state=self._state.extension_state,
        )

    def __repr__(self) -> str:
        return "TestRegistryAdmissionStore(<safe>)"


def enforce_registry_admission(
    request: RegistryAdmissionRequest,
    *,
    registry: object,
) -> RegistryAdmissionResult:
    if not isinstance(request, RegistryAdmissionRequest):
        _raise(RegistryAdmissionReason.SECURITY_BOUNDARY_VIOLATION)
    reasons = _validate(request, registry)
    if reasons:
        return _result(request, reasons=reasons)
    entry = _construct_entry(request)
    assert isinstance(registry, TestRegistryAdmissionStore)
    try:
        registry._commit(entry)
    except RegistryAdmissionError as error:
        reason = (
            error.category
            if error.category
            in {
                RegistryAdmissionReason.DUPLICATE_ENTRY,
                RegistryAdmissionReason.STATUS_INELIGIBLE,
            }
            else RegistryAdmissionReason.REGISTRY_COMMIT_FAILED
        )
        return _result(request, reasons=(reason,))
    except Exception:
        return _result(
            request,
            reasons=(RegistryAdmissionReason.REGISTRY_COMMIT_FAILED,),
        )
    return _result(request, entry=entry)


def _validate(
    request: RegistryAdmissionRequest,
    registry: object,
) -> tuple[RegistryAdmissionReason, ...]:
    decision = request.production_admission_decision
    reasons: set[RegistryAdmissionReason] = set()

    if not isinstance(registry, TestRegistryAdmissionStore):
        reasons.add(RegistryAdmissionReason.REGISTRY_WRITE_REJECTED)
    elif registry.kind is not RegistryKind.TEST:
        reasons.add(RegistryAdmissionReason.REGISTRY_WRITE_REJECTED)

    if (
        decision.requested_registry_kind is not RegistryKind.PRODUCTION
        or request.requested_registry_kind
        is not decision.requested_registry_kind
    ):
        reasons.add(RegistryAdmissionReason.REGISTRY_KIND_INVALID)
    if (
        decision.requested_initial_status is not RegistryStatus.ACTIVE
        or request.requested_initial_status
        is not decision.requested_initial_status
    ):
        reasons.add(RegistryAdmissionReason.INITIAL_STATUS_INVALID)
    if (
        decision.decision not in _ALLOWED_DECISIONS
        or not decision.eligible_for_registry_admission
    ):
        reasons.add(RegistryAdmissionReason.DECISION_INELIGIBLE)
    if decision.reason_categories:
        if (
            ProductionAdmissionReason.REVALIDATION_REQUIRED
            in decision.reason_categories
        ):
            reasons.add(RegistryAdmissionReason.REVALIDATION_REQUIRED)
        else:
            reasons.add(RegistryAdmissionReason.DECISION_INVALID)
    if (
        _digest(decision.canonical_json()) != decision.canonical_digest
        or not all(
            _is_digest(value)
            for value in (
                decision.plan_digest,
                decision.evidence_digest,
                decision.reviewer_attestation_digest,
                decision.canonical_digest,
            )
        )
    ):
        reasons.add(RegistryAdmissionReason.DIGEST_MISMATCH)
    summary = decision.safe_summary
    if (
        request.expected_profile_id != decision.profile_id
        or str(request.expected_profile_version) != decision.profile_version
        or str(request.expected_protocol_version)
        != decision.protocol_version
        or request.expected_product_id != decision.product_id
        or str(request.expected_product_version) != decision.product_version
        or request.evidence_reviewer_id != decision.evidence_reviewer_id
        or request.validation_operator_id != decision.validation_operator_id
        or request.approver_id != decision.approver_id
    ):
        reasons.add(RegistryAdmissionReason.IDENTITY_MISMATCH)
    if not _decision_summary_identity_valid(decision):
        reasons.add(RegistryAdmissionReason.IDENTITY_MISMATCH)
    request_roles = (
        request.registry_administrator_id,
        request.approver_id,
        request.evidence_reviewer_id,
        request.validation_operator_id,
    )
    if (
        len(set(request_roles)) != len(request_roles)
        or request.registry_administrator_id
        in {
            decision.approver_id,
            decision.evidence_reviewer_id,
            decision.validation_operator_id,
        }
    ):
        reasons.add(RegistryAdmissionReason.ROLE_CONFLICT)
    if request.expected_restrictions != decision.effective_restrictions:
        reasons.add(RegistryAdmissionReason.RESTRICTION_MISMATCH)
    if decision.decision is ApprovalDecision.APPROVED:
        if request.expected_restrictions is not None:
            reasons.add(RegistryAdmissionReason.RESTRICTION_MISMATCH)
    elif (
        request.expected_restrictions is None
        or request.expected_restrictions.is_empty
    ):
        reasons.add(RegistryAdmissionReason.RESTRICTION_MISMATCH)

    if decision.evaluated_at > request.evaluation_time:
        reasons.add(RegistryAdmissionReason.DECISION_NOT_YET_VALID)
    expirations = (
        request.evidence_expires_at,
        request.validation_expires_at,
        request.approval_expires_at,
        (
            request.expected_restrictions.expires_at
            if request.expected_restrictions is not None
            else None
        ),
    )
    if any(
        value is not None and request.evaluation_time >= value
        for value in expirations
    ):
        reasons.add(RegistryAdmissionReason.DECISION_EXPIRED)
    if decision.evaluated_at >= request.evidence_expires_at:
        reasons.add(RegistryAdmissionReason.DECISION_EXPIRED)

    if isinstance(registry, TestRegistryAdmissionStore):
        status = registry.profile_version_status(
            request.expected_profile_id,
            request.expected_profile_version,
        )
        if status is RegistryStatus.ACTIVE:
            reasons.add(RegistryAdmissionReason.DUPLICATE_ENTRY)
        elif status in {
            RegistryStatus.SUSPENDED,
            RegistryStatus.DEPRECATED,
            RegistryStatus.REVOKED,
        }:
            reasons.add(RegistryAdmissionReason.STATUS_INELIGIBLE)
    return tuple(reason for reason in _REASON_ORDER if reason in reasons)


def _decision_summary_identity_valid(
    decision: ProductionAdmissionDecision,
) -> bool:
    summary = decision.safe_summary
    return (
        summary.request_id == decision._request_id
        and summary.decision == decision.decision.value
        and summary.eligible_for_registry_admission
        == decision.eligible_for_registry_admission
        and summary.profile_id == decision.profile_id
        and summary.profile_version == decision.profile_version
        and summary.protocol_version == decision.protocol_version
        and summary.product_id == decision.product_id
        and summary.product_version == decision.product_version
        and summary.plan_digest == decision.plan_digest
        and summary.evidence_digest == decision.evidence_digest
        and summary.reviewer_attestation_digest
        == decision.reviewer_attestation_digest
        and summary.evidence_reviewer_id == decision.evidence_reviewer_id
        and summary.validation_operator_id == decision.validation_operator_id
        and summary.approver_id == decision.approver_id
        and summary.approval_digest == decision.approval_digest
        and summary.reason_categories
        == tuple(reason.value for reason in decision.reason_categories)
        and summary.restriction_count
        == _restriction_count(decision.effective_restrictions)
        and summary.evaluated_at == _canonical_datetime(decision.evaluated_at)
        and summary.canonical_digest == decision.canonical_digest
    )


def _construct_entry(
    request: RegistryAdmissionRequest,
) -> RegistryAdmissionEntry:
    decision = request.production_admission_decision
    assert decision.reviewer_attestation_digest is not None
    return RegistryAdmissionEntry(
        admission_id=request.admission_id,
        profile_id=request.expected_profile_id,
        profile_version=request.expected_profile_version,
        protocol_version=request.expected_protocol_version,
        product_id=request.expected_product_id,
        product_version=request.expected_product_version,
        maturity=ProfileMaturity.APPROVED,
        approval_decision=decision.decision,
        approval_digest=decision.approval_digest,
        restrictions=request.expected_restrictions,
        plan_digest=decision.plan_digest,
        evidence_digest=decision.evidence_digest,
        reviewer_attestation_digest=(
            decision.reviewer_attestation_digest
        ),
        admission_decision_digest=decision.canonical_digest,
        admitted_at=request.evaluation_time,
        registry_administrator_id=request.registry_administrator_id,
        registry_status=RegistryStatus.ACTIVE,
        registry_kind=RegistryKind.PRODUCTION,
    )


def _result(
    request: RegistryAdmissionRequest,
    *,
    reasons: tuple[RegistryAdmissionReason, ...] = (),
    entry: RegistryAdmissionEntry | None = None,
) -> RegistryAdmissionResult:
    decision = request.production_admission_decision
    admitted = entry is not None and not reasons
    return RegistryAdmissionResult(
        admission_id=request.admission_id,
        admitted=admitted,
        registry_kind=request.requested_registry_kind,
        initial_status=request.requested_initial_status,
        profile_id=request.expected_profile_id,
        profile_version=request.expected_profile_version,
        protocol_version=request.expected_protocol_version,
        product_id=request.expected_product_id,
        product_version=request.expected_product_version,
        decision=decision.decision,
        entry_identity=(entry.admission_id if admitted else None),
        plan_digest=decision.plan_digest,
        evidence_digest=decision.evidence_digest,
        reviewer_attestation_digest=(
            decision.reviewer_attestation_digest
        ),
        admission_decision_digest=decision.canonical_digest,
        effective_restrictions=(
            request.expected_restrictions if admitted else None
        ),
        reason_categories=reasons,
        evaluation_time=request.evaluation_time,
        admitted_at=(request.evaluation_time if admitted else None),
        entry=entry if admitted else None,
    )


def _entry_key(
    entry: RegistryAdmissionEntry,
) -> tuple[
    str,
    SemanticVersion,
    str,
    SemanticVersion,
    SemanticVersion,
]:
    return (
        entry.profile_id,
        entry.profile_version,
        entry.product_id,
        entry.product_version,
        entry.protocol_version,
    )


def _canonical_restrictions(
    restrictions: ApprovalRestrictions | None,
) -> dict[str, object] | None:
    if restrictions is None:
        return None
    return {
        "expires_at": _optional_datetime(restrictions.expires_at),
        "matched_keywords_disabled": (
            restrictions.matched_keywords_disabled
        ),
        "maximum_top_k": restrictions.maximum_top_k,
        "query_id_echo_required": restrictions.query_id_echo_required,
        "score_disabled": restrictions.score_disabled,
        "supported_minor_versions": list(
            restrictions.supported_minor_versions
        ),
        "title_disabled": restrictions.title_disabled,
    }


def _restriction_count(
    restrictions: ApprovalRestrictions | None,
) -> int:
    if restrictions is None:
        return 0
    mapping = _canonical_restrictions(restrictions)
    assert mapping is not None
    return sum(
        value not in (None, False, [], ())
        for value in mapping.values()
    )


def _is_safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and _SAFE_IDENTIFIER.fullmatch(value) is not None
    )


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


def _optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else _canonical_datetime(value)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _raise(category: RegistryAdmissionReason) -> None:
    raise RegistryAdmissionError(category) from None


__all__ = [
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
]
