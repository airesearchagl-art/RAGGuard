from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from ragguard.compatibility import SemanticVersion
from ragguard.production_registry import RegistryStatus
from ragguard.registry_admission import (
    RegistryAdmissionEntry,
    RegistryAdmissionRequest,
)


CANONICAL_REVALIDATION_DIGEST_ALGORITHM = "sha256"
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


class RevalidationTriggerKind(str, Enum):
    EVIDENCE_EXPIRED = "evidence_expired"
    EVIDENCE_REVOKED = "evidence_revoked"
    APPROVAL_REVOKED = "approval_revoked"
    SECURITY_POLICY_CHANGED = "security_policy_changed"
    PRODUCT_VERSION_CHANGED = "product_version_changed"
    PROTOCOL_VERSION_CHANGED = "protocol_version_changed"
    RESTRICTION_CHANGED = "restriction_changed"
    SCHEDULED_REVALIDATION = "scheduled_revalidation"
    ADMINISTRATOR_SUSPENSION = "administrator_suspension"
    ADMINISTRATOR_DEPRECATION = "administrator_deprecation"
    ADMINISTRATOR_REVOCATION = "administrator_revocation"


class RevalidationAction(str, Enum):
    NO_ACTION = "no_action"
    SUSPEND = "suspend"
    DEPRECATE = "deprecate"
    REVOKE = "revoke"
    REVALIDATION_REQUIRED = "revalidation_required"


class RevalidationReason(str, Enum):
    TRIGGER_INVALID = "trigger_invalid"
    TRIGGER_NOT_YET_VALID = "trigger_not_yet_valid"
    IDENTITY_MISMATCH = "identity_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    EVIDENCE_EXPIRED = "evidence_expired"
    EVIDENCE_REVOKED = "evidence_revoked"
    APPROVAL_REVOKED = "approval_revoked"
    SECURITY_POLICY_CHANGED = "security_policy_changed"
    REVALIDATION_REQUIRED = "revalidation_required"


_REASON_ORDER = tuple(RevalidationReason)


class RevalidationError(ValueError):
    def __init__(self, category: RevalidationReason) -> None:
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True)
class RevalidationTriggerSafeSummary:
    trigger_id: str
    trigger_kind: str
    observed_at: str
    profile_id: str
    profile_version: str
    protocol_version: str
    product_id: str
    product_version: str
    registry_entry_digest: str
    admission_decision_digest: str
    evidence_digest: str
    actor_id: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class RevalidationTrigger:
    trigger_id: str
    trigger_kind: RevalidationTriggerKind
    observed_at: datetime
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    registry_entry_digest: str
    admission_decision_digest: str
    evidence_digest: str
    actor_id: str
    safe_context: tuple[str, ...]
    evidence_expires_at: datetime | None = None
    safe_summary: RevalidationTriggerSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_REVALIDATION_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            not all(
                _is_safe_identifier(value)
                for value in (self.trigger_id, self.profile_id, self.product_id, self.actor_id)
            )
            or not isinstance(self.trigger_kind, RevalidationTriggerKind)
            or not _is_aware_datetime(self.observed_at)
            or not all(
                isinstance(value, SemanticVersion)
                for value in (
                    self.profile_version,
                    self.protocol_version,
                    self.product_version,
                )
            )
            or not all(
                _is_digest(value)
                for value in (
                    self.registry_entry_digest,
                    self.admission_decision_digest,
                    self.evidence_digest,
                )
            )
            or (
                self.evidence_expires_at is not None
                and not _is_aware_datetime(self.evidence_expires_at)
            )
            or not _is_safe_context(self.safe_context)
        ):
            _raise(RevalidationReason.TRIGGER_INVALID)
        if (
            self.trigger_kind is RevalidationTriggerKind.EVIDENCE_EXPIRED
            and self.evidence_expires_at is None
        ):
            _raise(RevalidationReason.TRIGGER_INVALID)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            RevalidationTriggerSafeSummary(
                trigger_id=self.trigger_id,
                trigger_kind=self.trigger_kind.value,
                observed_at=_canonical_datetime(self.observed_at),
                profile_id=self.profile_id,
                profile_version=str(self.profile_version),
                protocol_version=str(self.protocol_version),
                product_id=self.product_id,
                product_version=str(self.product_version),
                registry_entry_digest=self.registry_entry_digest,
                admission_decision_digest=self.admission_decision_digest,
                evidence_digest=self.evidence_digest,
                actor_id=self.actor_id,
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "actor_id": self.actor_id,
                "admission_decision_digest": self.admission_decision_digest,
                "evidence_digest": self.evidence_digest,
                "evidence_expires_at": _optional_datetime(self.evidence_expires_at),
                "observed_at": _canonical_datetime(self.observed_at),
                "product_id": self.product_id,
                "product_version": str(self.product_version),
                "profile_id": self.profile_id,
                "profile_version": str(self.profile_version),
                "protocol_version": str(self.protocol_version),
                "registry_entry_digest": self.registry_entry_digest,
                "safe_context": list(self.safe_context),
                "trigger_id": self.trigger_id,
                "trigger_kind": self.trigger_kind.value,
            }
        )

    def __repr__(self) -> str:
        return "RevalidationTrigger(<safe>)"


@dataclass(frozen=True)
class RevalidationRequirementSafeSummary:
    trigger_id: str
    action: str
    target_status: str | None
    revalidation_required: bool
    reason_categories: tuple[str, ...]
    evaluated_at: str
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class RevalidationRequirement:
    trigger_id: str
    action: RevalidationAction
    target_status: RegistryStatus | None
    revalidation_required: bool
    reason_categories: tuple[RevalidationReason, ...]
    evaluated_at: datetime
    safe_summary: RevalidationRequirementSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_REVALIDATION_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            not _is_safe_identifier(self.trigger_id)
            or not isinstance(self.action, RevalidationAction)
            or (self.target_status is not None and not isinstance(self.target_status, RegistryStatus))
            or type(self.revalidation_required) is not bool
            or not _is_aware_datetime(self.evaluated_at)
            or tuple(reason for reason in _REASON_ORDER if reason in self.reason_categories)
            != self.reason_categories
        ):
            _raise(RevalidationReason.TRIGGER_INVALID)
        digest = _digest(self.canonical_json())
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            RevalidationRequirementSafeSummary(
                trigger_id=self.trigger_id,
                action=self.action.value,
                target_status=(self.target_status.value if self.target_status else None),
                revalidation_required=self.revalidation_required,
                reason_categories=tuple(reason.value for reason in self.reason_categories),
                evaluated_at=_canonical_datetime(self.evaluated_at),
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "action": self.action.value,
                "evaluated_at": _canonical_datetime(self.evaluated_at),
                "reason_categories": [reason.value for reason in self.reason_categories],
                "revalidation_required": self.revalidation_required,
                "target_status": self.target_status.value if self.target_status else None,
                "trigger_id": self.trigger_id,
            }
        )

    def __repr__(self) -> str:
        return "RevalidationRequirement(<safe>)"


def evaluate_revalidation_requirement(
    trigger: RevalidationTrigger,
    *,
    entry: RegistryAdmissionEntry,
    admission_request: RegistryAdmissionRequest,
    evaluation_time: datetime,
) -> RevalidationRequirement:
    if (
        not isinstance(trigger, RevalidationTrigger)
        or not isinstance(entry, RegistryAdmissionEntry)
        or not isinstance(admission_request, RegistryAdmissionRequest)
        or not _is_aware_datetime(evaluation_time)
    ):
        _raise(RevalidationReason.TRIGGER_INVALID)

    reasons: set[RevalidationReason] = set()
    decision = admission_request.production_admission_decision
    if (
        trigger.profile_id != entry.profile_id
        or trigger.profile_version != entry.profile_version
        or trigger.protocol_version != entry.protocol_version
        or trigger.product_id != entry.product_id
        or trigger.product_version != entry.product_version
        or admission_request.expected_profile_id != entry.profile_id
        or admission_request.expected_profile_version != entry.profile_version
        or admission_request.expected_protocol_version != entry.protocol_version
        or admission_request.expected_product_id != entry.product_id
        or admission_request.expected_product_version != entry.product_version
        or decision.profile_id != entry.profile_id
        or decision.profile_version != str(entry.profile_version)
        or decision.protocol_version != str(entry.protocol_version)
        or decision.product_id != entry.product_id
        or decision.product_version != str(entry.product_version)
    ):
        reasons.add(RevalidationReason.IDENTITY_MISMATCH)
    if (
        trigger.registry_entry_digest != entry.canonical_digest
        or trigger.admission_decision_digest != entry.admission_decision_digest
        or trigger.admission_decision_digest != decision.canonical_digest
        or trigger.evidence_digest != entry.evidence_digest
        or trigger.evidence_digest != decision.evidence_digest
        or _digest(decision.canonical_json()) != decision.canonical_digest
        or _digest(admission_request.canonical_json()) != admission_request.canonical_digest
    ):
        reasons.add(RevalidationReason.DIGEST_MISMATCH)
    if decision.evaluated_at > trigger.observed_at or trigger.observed_at > evaluation_time:
        reasons.add(RevalidationReason.TRIGGER_NOT_YET_VALID)
    if trigger.evidence_expires_at is not None and (
        trigger.evidence_expires_at != admission_request.evidence_expires_at
    ):
        reasons.add(RevalidationReason.DIGEST_MISMATCH)
    if trigger.trigger_kind is RevalidationTriggerKind.EVIDENCE_EXPIRED and (
        trigger.evidence_expires_at is None
        or evaluation_time < trigger.evidence_expires_at
    ):
        reasons.add(RevalidationReason.TRIGGER_NOT_YET_VALID)
    if reasons:
        return _requirement(
            trigger,
            action=RevalidationAction.NO_ACTION,
            target_status=None,
            required=False,
            reasons=reasons,
            evaluation_time=evaluation_time,
        )

    kind = trigger.trigger_kind
    if kind is RevalidationTriggerKind.SECURITY_POLICY_CHANGED:
        return _requirement(trigger, RevalidationAction.REVOKE, RegistryStatus.REVOKED, False, {RevalidationReason.SECURITY_POLICY_CHANGED}, evaluation_time)
    if kind is RevalidationTriggerKind.ADMINISTRATOR_REVOCATION:
        return _requirement(trigger, RevalidationAction.REVOKE, RegistryStatus.REVOKED, False, set(), evaluation_time)
    if kind in {RevalidationTriggerKind.EVIDENCE_EXPIRED, RevalidationTriggerKind.EVIDENCE_REVOKED, RevalidationTriggerKind.APPROVAL_REVOKED}:
        reason = {
            RevalidationTriggerKind.EVIDENCE_EXPIRED: RevalidationReason.EVIDENCE_EXPIRED,
            RevalidationTriggerKind.EVIDENCE_REVOKED: RevalidationReason.EVIDENCE_REVOKED,
            RevalidationTriggerKind.APPROVAL_REVOKED: RevalidationReason.APPROVAL_REVOKED,
        }[kind]
        return _requirement(trigger, RevalidationAction.SUSPEND, RegistryStatus.SUSPENDED, True, {reason, RevalidationReason.REVALIDATION_REQUIRED}, evaluation_time)
    if kind in {RevalidationTriggerKind.PRODUCT_VERSION_CHANGED, RevalidationTriggerKind.PROTOCOL_VERSION_CHANGED, RevalidationTriggerKind.RESTRICTION_CHANGED}:
        return _requirement(trigger, RevalidationAction.DEPRECATE, RegistryStatus.DEPRECATED, True, {RevalidationReason.REVALIDATION_REQUIRED}, evaluation_time)
    if kind is RevalidationTriggerKind.SCHEDULED_REVALIDATION:
        return _requirement(trigger, RevalidationAction.REVALIDATION_REQUIRED, None, True, {RevalidationReason.REVALIDATION_REQUIRED}, evaluation_time)
    if kind is RevalidationTriggerKind.ADMINISTRATOR_SUSPENSION:
        return _requirement(trigger, RevalidationAction.SUSPEND, RegistryStatus.SUSPENDED, False, set(), evaluation_time)
    if kind is RevalidationTriggerKind.ADMINISTRATOR_DEPRECATION:
        return _requirement(trigger, RevalidationAction.DEPRECATE, RegistryStatus.DEPRECATED, False, set(), evaluation_time)
    return _requirement(trigger, RevalidationAction.NO_ACTION, None, False, set(), evaluation_time)


def _requirement(
    trigger: RevalidationTrigger,
    action: RevalidationAction,
    target_status: RegistryStatus | None,
    required: bool,
    reasons: set[RevalidationReason],
    evaluation_time: datetime,
) -> RevalidationRequirement:
    return RevalidationRequirement(
        trigger_id=trigger.trigger_id,
        action=action,
        target_status=target_status,
        revalidation_required=required,
        reason_categories=tuple(reason for reason in _REASON_ORDER if reason in reasons),
        evaluated_at=evaluation_time,
    )


def _is_safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_safe_context(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and tuple(sorted(set(value))) == value
        and all(isinstance(item, str) and item in _SAFE_CONTEXT_VALUES for item in value)
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


def _raise(category: RevalidationReason) -> None:
    raise RevalidationError(category) from None


__all__ = [
    "CANONICAL_REVALIDATION_DIGEST_ALGORITHM",
    "RevalidationAction",
    "RevalidationError",
    "RevalidationReason",
    "RevalidationRequirement",
    "RevalidationRequirementSafeSummary",
    "RevalidationTrigger",
    "RevalidationTriggerKind",
    "RevalidationTriggerSafeSummary",
    "evaluate_revalidation_requirement",
]
