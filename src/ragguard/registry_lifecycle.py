from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from ragguard.compatibility import SemanticVersion
from ragguard.production_registry import RegistryKind, RegistryStatus
from ragguard.profile_approval import ApprovalRestrictions
from ragguard.registry_admission import (
    RegistryAdmissionEntry,
    RegistryAdmissionRequest,
    TestRegistryAdmissionStore,
)
from ragguard.revalidation import (
    RevalidationAction,
    RevalidationReason,
    RevalidationRequirement,
    RevalidationTrigger,
    RevalidationTriggerKind,
    evaluate_revalidation_requirement,
)


CANONICAL_REGISTRY_LIFECYCLE_DIGEST_ALGORITHM = "sha256"
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
_REQUESTED_STATUSES = frozenset(
    {RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED, RegistryStatus.REVOKED}
)
_ALLOWED_TRANSITIONS = frozenset(
    {
        (RegistryStatus.ACTIVE, RegistryStatus.SUSPENDED),
        (RegistryStatus.ACTIVE, RegistryStatus.DEPRECATED),
        (RegistryStatus.ACTIVE, RegistryStatus.REVOKED),
        (RegistryStatus.SUSPENDED, RegistryStatus.DEPRECATED),
        (RegistryStatus.SUSPENDED, RegistryStatus.REVOKED),
        (RegistryStatus.DEPRECATED, RegistryStatus.REVOKED),
    }
)


class RegistryLifecycleReason(str, Enum):
    TRIGGER_INVALID = "trigger_invalid"
    TRIGGER_NOT_YET_VALID = "trigger_not_yet_valid"
    IDENTITY_MISMATCH = "identity_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    ROLE_CONFLICT = "role_conflict"
    STATUS_MISMATCH = "status_mismatch"
    TRANSITION_FORBIDDEN = "transition_forbidden"
    ALREADY_TERMINAL = "already_terminal"
    DUPLICATE_TRANSITION = "duplicate_transition"
    EVIDENCE_EXPIRED = "evidence_expired"
    EVIDENCE_REVOKED = "evidence_revoked"
    APPROVAL_REVOKED = "approval_revoked"
    SECURITY_POLICY_CHANGED = "security_policy_changed"
    REVALIDATION_REQUIRED = "revalidation_required"
    REGISTRY_KIND_INVALID = "registry_kind_invalid"
    SECURITY_BOUNDARY_VIOLATION = "security_boundary_violation"
    REGISTRY_WRITE_REJECTED = "registry_write_rejected"
    REGISTRY_COMMIT_FAILED = "registry_commit_failed"


class RegistryLifecycleCommitFault(str, Enum):
    ADMISSION_STATE_CANDIDATE = "admission_state_candidate"
    EVENT_CANDIDATE = "event_candidate"
    COUNTER_AND_REQUEST_CANDIDATE = "counter_and_request_candidate"
    BEFORE_COMMIT = "before_commit"


_REASON_ORDER = tuple(RegistryLifecycleReason)


class RegistryLifecycleError(ValueError):
    def __init__(self, category: RegistryLifecycleReason) -> None:
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True)
class RegistryLifecycleRequestSafeSummary:
    lifecycle_request_id: str
    evaluation_time: str
    trigger_id: str
    trigger_kind: str
    expected_current_status: str
    requested_status: str
    registry_administrator_id: str
    expected_entry_digest: str
    restriction_count: int
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class RegistryLifecycleRequest:
    lifecycle_request_id: str
    evaluation_time: datetime
    trigger: RevalidationTrigger
    expected_current_status: RegistryStatus
    requested_status: RegistryStatus
    registry_administrator_id: str
    expected_entry_digest: str
    expected_restrictions: ApprovalRestrictions | None
    safe_context: tuple[str, ...]
    safe_summary: RegistryLifecycleRequestSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_REGISTRY_LIFECYCLE_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            not _is_safe_identifier(self.lifecycle_request_id)
            or not _is_aware_datetime(self.evaluation_time)
            or not isinstance(self.trigger, RevalidationTrigger)
            or not isinstance(self.expected_current_status, RegistryStatus)
            or not isinstance(self.requested_status, RegistryStatus)
            or not _is_safe_identifier(self.registry_administrator_id)
            or not _is_digest(self.expected_entry_digest)
            or (
                self.expected_restrictions is not None
                and not isinstance(self.expected_restrictions, ApprovalRestrictions)
            )
            or not _is_safe_context(self.safe_context)
        ):
            _raise(RegistryLifecycleReason.SECURITY_BOUNDARY_VIOLATION)
        if self.requested_status not in _REQUESTED_STATUSES:
            _raise(RegistryLifecycleReason.TRANSITION_FORBIDDEN)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            RegistryLifecycleRequestSafeSummary(
                lifecycle_request_id=self.lifecycle_request_id,
                evaluation_time=_canonical_datetime(self.evaluation_time),
                trigger_id=self.trigger.trigger_id,
                trigger_kind=self.trigger.trigger_kind.value,
                expected_current_status=self.expected_current_status.value,
                requested_status=self.requested_status.value,
                registry_administrator_id=self.registry_administrator_id,
                expected_entry_digest=self.expected_entry_digest,
                restriction_count=_restriction_count(self.expected_restrictions),
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "evaluation_time": _canonical_datetime(self.evaluation_time),
                "expected_current_status": self.expected_current_status.value,
                "expected_entry_digest": self.expected_entry_digest,
                "expected_restrictions": _canonical_restrictions(self.expected_restrictions),
                "lifecycle_request_id": self.lifecycle_request_id,
                "registry_administrator_id": self.registry_administrator_id,
                "requested_status": self.requested_status.value,
                "safe_context": list(self.safe_context),
                "trigger_digest": self.trigger.canonical_digest,
                "trigger_id": self.trigger.trigger_id,
            }
        )

    def __repr__(self) -> str:
        return "RegistryLifecycleRequest(<safe>)"


@dataclass(frozen=True)
class RegistryLifecycleEvent:
    lifecycle_request_id: str
    admission_id: str
    profile_id: str
    profile_version: str
    product_id: str
    product_version: str
    protocol_version: str
    previous_status: str
    new_status: str
    trigger_kind: str
    trigger_digest: str
    lifecycle_request_digest: str
    transitioned_at: str
    actor_id: str
    plan_digest: str
    evidence_digest: str
    admission_decision_digest: str
    original_entry_digest: str
    resulting_entry_digest: str
    restriction_count: int
    safe_summary: str = "test_registry_lifecycle_transition"


@dataclass(frozen=True)
class _RegistryLifecycleCommitState:
    events: tuple[RegistryLifecycleEvent, ...]
    write_count: int
    mutation_count: int
    committed_request_ids: frozenset[str]


@dataclass(frozen=True)
class RegistryLifecycleSafeSummary:
    lifecycle_request_id: str
    applied: bool
    previous_status: str
    resulting_status: str
    trigger_kind: str
    profile_id: str
    profile_version: str
    protocol_version: str
    product_id: str
    product_version: str
    registry_entry_digest: str
    resulting_entry_digest: str | None
    admission_decision_digest: str
    evidence_digest: str
    reason_categories: tuple[str, ...]
    transitioned_at: str | None
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class RegistryLifecycleResult:
    lifecycle_request_id: str
    applied: bool
    previous_status: RegistryStatus
    resulting_status: RegistryStatus
    trigger_kind: RevalidationTriggerKind
    reason_categories: tuple[RegistryLifecycleReason, ...]
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    registry_entry_digest: str
    resulting_entry_digest: str | None
    plan_digest: str
    evidence_digest: str
    admission_decision_digest: str
    lifecycle_request_digest: str
    trigger_digest: str
    transitioned_at: datetime | None
    event: RegistryLifecycleEvent | None = field(repr=False)
    safe_summary: RegistryLifecycleSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_REGISTRY_LIFECYCLE_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            not _is_safe_identifier(self.lifecycle_request_id)
            or type(self.applied) is not bool
            or not isinstance(self.previous_status, RegistryStatus)
            or not isinstance(self.resulting_status, RegistryStatus)
            or not isinstance(self.trigger_kind, RevalidationTriggerKind)
            or tuple(reason for reason in _REASON_ORDER if reason in self.reason_categories)
            != self.reason_categories
            or not _is_safe_identifier(self.profile_id)
            or not _is_safe_identifier(self.product_id)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (self.profile_version, self.protocol_version, self.product_version)
            )
            or not all(
                _is_digest(value)
                for value in (
                    self.registry_entry_digest,
                    self.plan_digest,
                    self.evidence_digest,
                    self.admission_decision_digest,
                    self.lifecycle_request_digest,
                    self.trigger_digest,
                )
            )
        ):
            _raise(RegistryLifecycleReason.SECURITY_BOUNDARY_VIOLATION)
        if self.applied:
            if (
                self.event is None
                or self.transitioned_at is None
                or not _is_aware_datetime(self.transitioned_at)
                or self.resulting_entry_digest is None
                or not _is_digest(self.resulting_entry_digest)
                or self.reason_categories
            ):
                _raise(RegistryLifecycleReason.REGISTRY_COMMIT_FAILED)
        elif (
            self.event is not None
            or self.transitioned_at is not None
            or self.resulting_entry_digest is not None
            or not self.reason_categories
            or self.previous_status is not self.resulting_status
        ):
            _raise(RegistryLifecycleReason.REGISTRY_COMMIT_FAILED)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            RegistryLifecycleSafeSummary(
                lifecycle_request_id=self.lifecycle_request_id,
                applied=self.applied,
                previous_status=self.previous_status.value,
                resulting_status=self.resulting_status.value,
                trigger_kind=self.trigger_kind.value,
                profile_id=self.profile_id,
                profile_version=str(self.profile_version),
                protocol_version=str(self.protocol_version),
                product_id=self.product_id,
                product_version=str(self.product_version),
                registry_entry_digest=self.registry_entry_digest,
                resulting_entry_digest=self.resulting_entry_digest,
                admission_decision_digest=self.admission_decision_digest,
                evidence_digest=self.evidence_digest,
                reason_categories=tuple(reason.value for reason in self.reason_categories),
                transitioned_at=_optional_datetime(self.transitioned_at),
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "admission_decision_digest": self.admission_decision_digest,
                "applied": self.applied,
                "evidence_digest": self.evidence_digest,
                "lifecycle_request_digest": self.lifecycle_request_digest,
                "lifecycle_request_id": self.lifecycle_request_id,
                "plan_digest": self.plan_digest,
                "previous_status": self.previous_status.value,
                "product_id": self.product_id,
                "product_version": str(self.product_version),
                "profile_id": self.profile_id,
                "profile_version": str(self.profile_version),
                "protocol_version": str(self.protocol_version),
                "reason_categories": [reason.value for reason in self.reason_categories],
                "registry_entry_digest": self.registry_entry_digest,
                "resulting_entry_digest": self.resulting_entry_digest,
                "resulting_status": self.resulting_status.value,
                "transitioned_at": _optional_datetime(self.transitioned_at),
                "trigger_digest": self.trigger_digest,
                "trigger_kind": self.trigger_kind.value,
            }
        )

    def __repr__(self) -> str:
        return "RegistryLifecycleResult(<safe>)"


class TestRegistryLifecycleStore:
    __test__ = False

    def __init__(
        self,
        admission_registry: TestRegistryAdmissionStore,
        *,
        fail_commit: bool = False,
        failure_point: RegistryLifecycleCommitFault | None = None,
    ) -> None:
        if (
            not isinstance(admission_registry, TestRegistryAdmissionStore)
            or type(fail_commit) is not bool
            or (
                failure_point is not None
                and not isinstance(failure_point, RegistryLifecycleCommitFault)
            )
            or (fail_commit and failure_point is not None)
        ):
            _raise(RegistryLifecycleReason.REGISTRY_KIND_INVALID)
        self._admission_registry = admission_registry
        initial_state = _RegistryLifecycleCommitState(
            events=(),
            write_count=0,
            mutation_count=0,
            committed_request_ids=frozenset(),
        )
        extension_state = admission_registry._test_extension_state
        if extension_state is None:
            admission_state = admission_registry._build_test_state_bundle(
                entries=admission_registry.snapshot,
                extension_state=initial_state,
            )
            admission_registry._replace_test_state_bundle(admission_state)
        elif not isinstance(extension_state, _RegistryLifecycleCommitState):
            _raise(RegistryLifecycleReason.REGISTRY_KIND_INVALID)
        self._failure_point = (
            RegistryLifecycleCommitFault.BEFORE_COMMIT
            if fail_commit
            else failure_point
        )

    @property
    def _commit_state(self) -> _RegistryLifecycleCommitState:
        state = self._admission_registry._test_extension_state
        if not isinstance(state, _RegistryLifecycleCommitState):
            _raise(RegistryLifecycleReason.REGISTRY_COMMIT_FAILED)
        return state

    @property
    def kind(self) -> RegistryKind:
        return RegistryKind.TEST

    @property
    def events(self) -> tuple[RegistryLifecycleEvent, ...]:
        return self._commit_state.events

    @property
    def write_count(self) -> int:
        return self._commit_state.write_count

    @property
    def mutation_count(self) -> int:
        return self._commit_state.mutation_count

    @property
    def committed_request_ids(self) -> frozenset[str]:
        return self._commit_state.committed_request_ids

    @property
    def admission_snapshot(self) -> object:
        return self._admission_registry.snapshot

    @property
    def transport_count(self) -> int:
        return 0

    @property
    def http_count(self) -> int:
        return 0

    def resolve_status_exact(
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
            _raise(RegistryLifecycleReason.SECURITY_BOUNDARY_VIOLATION)
        if (
            not _is_safe_identifier(profile_id)
            or not _is_safe_identifier(product_id)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (profile_version, product_version, protocol_version)
            )
        ):
            _raise(RegistryLifecycleReason.IDENTITY_MISMATCH)
        entry = self._admission_registry.snapshot.get(
            (profile_id, profile_version, product_id, product_version, protocol_version)
        )
        if entry is None:
            _raise(RegistryLifecycleReason.IDENTITY_MISMATCH)
        return entry

    def _is_duplicate(self, lifecycle_request_id: str) -> bool:
        return lifecycle_request_id in self._commit_state.committed_request_ids

    def _disable_failure_injection(self) -> None:
        self._failure_point = None

    def _fail_if(self, point: RegistryLifecycleCommitFault) -> None:
        if self._failure_point is point:
            _raise(RegistryLifecycleReason.REGISTRY_COMMIT_FAILED)

    def _commit_transition(
        self,
        *,
        request: RegistryLifecycleRequest,
        event: RegistryLifecycleEvent,
        expected_entry: RegistryAdmissionEntry,
        replacement_entry: RegistryAdmissionEntry,
    ) -> None:
        current_state = self._commit_state

        self._fail_if(RegistryLifecycleCommitFault.ADMISSION_STATE_CANDIDATE)
        entries_candidate = (
            self._admission_registry._build_replacement_entries_candidate(
                expected_entry=expected_entry,
                replacement_entry=replacement_entry,
            )
        )

        self._fail_if(RegistryLifecycleCommitFault.EVENT_CANDIDATE)
        events_candidate = (*current_state.events, event)

        self._fail_if(
            RegistryLifecycleCommitFault.COUNTER_AND_REQUEST_CANDIDATE
        )
        commit_state_candidate = _RegistryLifecycleCommitState(
            events=events_candidate,
            write_count=current_state.write_count + 1,
            mutation_count=current_state.mutation_count + 1,
            committed_request_ids=current_state.committed_request_ids
            | {request.lifecycle_request_id},
        )
        state_bundle_candidate = self._admission_registry._build_test_state_bundle(
            entries=entries_candidate,
            extension_state=commit_state_candidate,
        )

        self._fail_if(RegistryLifecycleCommitFault.BEFORE_COMMIT)
        self._admission_registry._replace_test_state_bundle(
            state_bundle_candidate
        )

    def __repr__(self) -> str:
        return "TestRegistryLifecycleStore(<safe>)"


def enforce_registry_lifecycle(
    request: RegistryLifecycleRequest,
    *,
    registry: object,
    admission_request: RegistryAdmissionRequest,
) -> RegistryLifecycleResult:
    if not isinstance(request, RegistryLifecycleRequest):
        _raise(RegistryLifecycleReason.SECURITY_BOUNDARY_VIOLATION)
    reasons: set[RegistryLifecycleReason] = set()
    entry: RegistryAdmissionEntry | None = None
    if (
        not isinstance(registry, TestRegistryLifecycleStore)
        or registry.kind is not RegistryKind.TEST
    ):
        reasons.add(RegistryLifecycleReason.REGISTRY_WRITE_REJECTED)
    else:
        try:
            entry = registry.resolve_status_exact(
                profile_id=request.trigger.profile_id,
                profile_version=request.trigger.profile_version,
                product_id=request.trigger.product_id,
                product_version=request.trigger.product_version,
                protocol_version=request.trigger.protocol_version,
            )
        except RegistryLifecycleError as error:
            reasons.add(error.category)
    if not isinstance(admission_request, RegistryAdmissionRequest):
        reasons.add(RegistryLifecycleReason.SECURITY_BOUNDARY_VIOLATION)

    requirement: RevalidationRequirement | None = None
    if entry is not None and isinstance(admission_request, RegistryAdmissionRequest):
        requirement = evaluate_revalidation_requirement(
            request.trigger,
            entry=entry,
            admission_request=admission_request,
            evaluation_time=request.evaluation_time,
        )
        blocking_reasons = tuple(
            reason
            for reason in requirement.reason_categories
            if reason
            in {
                RevalidationReason.TRIGGER_INVALID,
                RevalidationReason.TRIGGER_NOT_YET_VALID,
                RevalidationReason.IDENTITY_MISMATCH,
                RevalidationReason.DIGEST_MISMATCH,
            }
        )
        reasons.update(_map_revalidation_reasons(blocking_reasons))
        decision = admission_request.production_admission_decision
        if request.registry_administrator_id != request.trigger.actor_id:
            reasons.add(RegistryLifecycleReason.IDENTITY_MISMATCH)
        if request.registry_administrator_id in {
            decision.approver_id,
            decision.evidence_reviewer_id,
            decision.validation_operator_id,
        }:
            reasons.add(RegistryLifecycleReason.ROLE_CONFLICT)
        if (
            request.expected_entry_digest != entry.canonical_digest
            or request.expected_entry_digest != request.trigger.registry_entry_digest
        ):
            reasons.add(RegistryLifecycleReason.DIGEST_MISMATCH)
        if request.expected_current_status is not entry.registry_status:
            reasons.add(RegistryLifecycleReason.STATUS_MISMATCH)
        if request.expected_restrictions != entry.restrictions:
            reasons.add(RegistryLifecycleReason.IDENTITY_MISMATCH)
        if entry.registry_kind is not RegistryKind.PRODUCTION:
            reasons.add(RegistryLifecycleReason.REGISTRY_KIND_INVALID)
        if entry.registry_status is RegistryStatus.REVOKED:
            reasons.add(RegistryLifecycleReason.ALREADY_TERMINAL)
        if (entry.registry_status, request.requested_status) not in _ALLOWED_TRANSITIONS:
            reasons.add(RegistryLifecycleReason.TRANSITION_FORBIDDEN)
        if requirement.target_status is None:
            reasons.add(RegistryLifecycleReason.REVALIDATION_REQUIRED)
        elif request.requested_status is not requirement.target_status:
            reasons.add(RegistryLifecycleReason.TRANSITION_FORBIDDEN)
        if isinstance(
            registry, TestRegistryLifecycleStore
        ) and registry._is_duplicate(request.lifecycle_request_id):
            reasons.add(RegistryLifecycleReason.DUPLICATE_TRANSITION)

    if (
        reasons
        or entry is None
        or requirement is None
        or not isinstance(registry, TestRegistryLifecycleStore)
    ):
        return _result(request, entry=entry, reasons=reasons)

    transitioned = replace(entry, registry_status=request.requested_status)
    event = _event(request, entry, transitioned)
    result = _result(request, entry=entry, transitioned=transitioned, event=event)
    try:
        registry._commit_transition(
            request=request,
            event=event,
            expected_entry=entry,
            replacement_entry=transitioned,
        )
    except Exception:
        return _result(
            request,
            entry=entry,
            reasons={RegistryLifecycleReason.REGISTRY_COMMIT_FAILED},
        )
    return result


def _event(
    request: RegistryLifecycleRequest,
    entry: RegistryAdmissionEntry,
    transitioned: RegistryAdmissionEntry,
) -> RegistryLifecycleEvent:
    return RegistryLifecycleEvent(
        lifecycle_request_id=request.lifecycle_request_id,
        admission_id=entry.admission_id,
        profile_id=entry.profile_id,
        profile_version=str(entry.profile_version),
        product_id=entry.product_id,
        product_version=str(entry.product_version),
        protocol_version=str(entry.protocol_version),
        previous_status=entry.registry_status.value,
        new_status=transitioned.registry_status.value,
        trigger_kind=request.trigger.trigger_kind.value,
        trigger_digest=request.trigger.canonical_digest,
        lifecycle_request_digest=request.canonical_digest,
        transitioned_at=_canonical_datetime(request.evaluation_time),
        actor_id=request.registry_administrator_id,
        plan_digest=entry.plan_digest,
        evidence_digest=entry.evidence_digest,
        admission_decision_digest=entry.admission_decision_digest,
        original_entry_digest=entry.canonical_digest,
        resulting_entry_digest=transitioned.canonical_digest,
        restriction_count=_restriction_count(entry.restrictions),
    )


def _result(
    request: RegistryLifecycleRequest,
    *,
    entry: RegistryAdmissionEntry | None,
    reasons: set[RegistryLifecycleReason] | None = None,
    transitioned: RegistryAdmissionEntry | None = None,
    event: RegistryLifecycleEvent | None = None,
) -> RegistryLifecycleResult:
    denial_reasons = reasons or set()
    applied = transitioned is not None and event is not None and not denial_reasons
    previous_status = (
        entry.registry_status
        if entry is not None
        else request.expected_current_status
    )
    return RegistryLifecycleResult(
        lifecycle_request_id=request.lifecycle_request_id,
        applied=applied,
        previous_status=previous_status,
        resulting_status=transitioned.registry_status if applied else previous_status,
        trigger_kind=request.trigger.trigger_kind,
        reason_categories=tuple(
            reason for reason in _REASON_ORDER if reason in denial_reasons
        ),
        profile_id=request.trigger.profile_id,
        profile_version=request.trigger.profile_version,
        protocol_version=request.trigger.protocol_version,
        product_id=request.trigger.product_id,
        product_version=request.trigger.product_version,
        registry_entry_digest=request.trigger.registry_entry_digest,
        resulting_entry_digest=(
            transitioned.canonical_digest if applied else None
        ),
        plan_digest=entry.plan_digest if entry is not None else _zero_digest(),
        evidence_digest=request.trigger.evidence_digest,
        admission_decision_digest=request.trigger.admission_decision_digest,
        lifecycle_request_digest=request.canonical_digest,
        trigger_digest=request.trigger.canonical_digest,
        transitioned_at=request.evaluation_time if applied else None,
        event=event if applied else None,
    )


def _map_revalidation_reasons(
    reasons: tuple[RevalidationReason, ...],
) -> set[RegistryLifecycleReason]:
    mapping = {
        RevalidationReason.TRIGGER_INVALID: RegistryLifecycleReason.TRIGGER_INVALID,
        RevalidationReason.TRIGGER_NOT_YET_VALID: RegistryLifecycleReason.TRIGGER_NOT_YET_VALID,
        RevalidationReason.IDENTITY_MISMATCH: RegistryLifecycleReason.IDENTITY_MISMATCH,
        RevalidationReason.DIGEST_MISMATCH: RegistryLifecycleReason.DIGEST_MISMATCH,
        RevalidationReason.EVIDENCE_EXPIRED: RegistryLifecycleReason.EVIDENCE_EXPIRED,
        RevalidationReason.EVIDENCE_REVOKED: RegistryLifecycleReason.EVIDENCE_REVOKED,
        RevalidationReason.APPROVAL_REVOKED: RegistryLifecycleReason.APPROVAL_REVOKED,
        RevalidationReason.SECURITY_POLICY_CHANGED: RegistryLifecycleReason.SECURITY_POLICY_CHANGED,
        RevalidationReason.REVALIDATION_REQUIRED: RegistryLifecycleReason.REVALIDATION_REQUIRED,
    }
    return {mapping[reason] for reason in reasons}


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
        "supported_minor_versions": list(restrictions.supported_minor_versions),
        "title_disabled": restrictions.title_disabled,
    }


def _restriction_count(restrictions: ApprovalRestrictions | None) -> int:
    mapping = _canonical_restrictions(restrictions)
    return (
        0
        if mapping is None
        else sum(value not in (None, False, [], ()) for value in mapping.values())
    )


def _is_safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_safe_context(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and tuple(sorted(set(value))) == value
        and all(
            isinstance(item, str) and item in _SAFE_CONTEXT_VALUES for item in value
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
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else _canonical_datetime(value)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _zero_digest() -> str:
    return _digest("unavailable")


def _raise(category: RegistryLifecycleReason) -> None:
    raise RegistryLifecycleError(category) from None


__all__ = [
    "CANONICAL_REGISTRY_LIFECYCLE_DIGEST_ALGORITHM",
    "RegistryLifecycleError",
    "RegistryLifecycleEvent",
    "RegistryLifecycleReason",
    "RegistryLifecycleRequest",
    "RegistryLifecycleRequestSafeSummary",
    "RegistryLifecycleResult",
    "RegistryLifecycleSafeSummary",
    "TestRegistryLifecycleStore",
    "enforce_registry_lifecycle",
]
