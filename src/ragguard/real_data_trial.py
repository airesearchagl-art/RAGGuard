from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ragguard.local_rag_integration import RAGStage
from ragguard.storage_adapter import (
    canonical_datetime,
    canonical_json,
    canonical_object_valid,
    digest,
    is_aware,
    is_digest,
    is_identifier,
)


class RealDataTrialError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class RealDataClass(str, Enum):
    INTERNAL_LOW = "internal_low"
    INTERNAL_RESTRICTED = "internal_restricted"
    PERSONAL_DATA = "personal_data"
    CONTRACTUAL_CONFIDENTIAL = "contractual_confidential"
    CREDENTIAL_LIKE = "credential_like"
    HIGHLY_RESTRICTED = "highly_restricted"


class TrialRetentionClass(str, Enum):
    NONE = "none"
    TRANSFORMED_EPHEMERAL_ONLY = "transformed_ephemeral_only"


class TrialLoggingClass(str, Enum):
    DIGEST_AND_REASON_ONLY = "digest_and_reason_only"


class TrialCacheClass(str, Enum):
    NONE = "none"


class TrialExportClass(str, Enum):
    PROHIBITED = "prohibited"


class TrialPersistenceClass(str, Enum):
    NONE = "none"


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


@dataclass(frozen=True, repr=False)
class RealDataClassificationPolicy(_Canonical):
    allowed_data_classes: tuple[RealDataClass, ...]
    prohibited_data_classes: tuple[RealDataClass, ...]
    masking_required_classes: tuple[RealDataClass, ...]
    embedding_prohibited_classes: tuple[RealDataClass, ...]
    logging_prohibited_classes: tuple[RealDataClass, ...]
    persistence_prohibited_classes: tuple[RealDataClass, ...]
    export_prohibited_classes: tuple[RealDataClass, ...]
    policy_version: str

    def __post_init__(self) -> None:
        collections = (
            self.allowed_data_classes,
            self.prohibited_data_classes,
            self.masking_required_classes,
            self.embedding_prohibited_classes,
            self.logging_prohibited_classes,
            self.persistence_prohibited_classes,
            self.export_prohibited_classes,
        )
        if (not is_identifier(self.policy_version)
                or not all(isinstance(values, tuple) and values for values in collections)
                or not all(all(isinstance(value, RealDataClass) for value in values)
                           for values in collections)
                or any(len(set(values)) != len(values) for values in collections)
                or set(self.allowed_data_classes) & set(self.prohibited_data_classes)
                or RealDataClass.CREDENTIAL_LIKE not in self.prohibited_data_classes
                or RealDataClass.HIGHLY_RESTRICTED not in self.prohibited_data_classes
                or (RealDataClass.PERSONAL_DATA not in self.prohibited_data_classes
                    and RealDataClass.PERSONAL_DATA not in self.masking_required_classes)):
            raise RealDataTrialError("classification_policy_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {
            "allowed_data_classes": sorted(value.value for value in self.allowed_data_classes),
            "embedding_prohibited_classes": sorted(
                value.value for value in self.embedding_prohibited_classes),
            "export_prohibited_classes": sorted(
                value.value for value in self.export_prohibited_classes),
            "logging_prohibited_classes": sorted(
                value.value for value in self.logging_prohibited_classes),
            "masking_required_classes": sorted(
                value.value for value in self.masking_required_classes),
            "persistence_prohibited_classes": sorted(
                value.value for value in self.persistence_prohibited_classes),
            "policy_version": self.policy_version,
            "prohibited_data_classes": sorted(
                value.value for value in self.prohibited_data_classes),
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialStagePolicy(_Canonical):
    allowed_stages: tuple[RAGStage, ...]
    prohibited_stages: tuple[RAGStage, ...]
    masking_required_before_stage: RAGStage
    approval_required_before_stage: RAGStage
    max_stage: RAGStage

    def __post_init__(self) -> None:
        all_stages = tuple(RAGStage)
        if (not self.allowed_stages or not self.prohibited_stages
                or not all(isinstance(value, RAGStage)
                           for value in (*self.allowed_stages, *self.prohibited_stages))
                or len(set(self.allowed_stages)) != len(self.allowed_stages)
                or len(set(self.prohibited_stages)) != len(self.prohibited_stages)
                or set(self.allowed_stages) & set(self.prohibited_stages)
                or set(self.allowed_stages) | set(self.prohibited_stages) != set(all_stages)
                or tuple(value for value in all_stages if value in self.allowed_stages)
                    != self.allowed_stages
                or not isinstance(self.masking_required_before_stage, RAGStage)
                or not isinstance(self.approval_required_before_stage, RAGStage)
                or not isinstance(self.max_stage, RAGStage)
                or self.max_stage != self.allowed_stages[-1]
                or self.approval_required_before_stage not in self.allowed_stages):
            raise RealDataTrialError("stage_policy_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {
            "allowed_stages": [value.value for value in self.allowed_stages],
            "approval_required_before_stage": self.approval_required_before_stage.value,
            "masking_required_before_stage": self.masking_required_before_stage.value,
            "max_stage": self.max_stage.value,
            "prohibited_stages": [value.value for value in self.prohibited_stages],
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialRetentionPolicy(_Canonical):
    raw_input_retention: TrialRetentionClass
    transformed_content_retention: TrialRetentionClass
    embedding_retention: TrialRetentionClass
    retrieval_retention: TrialRetentionClass
    prompt_retention: TrialRetentionClass
    response_retention: TrialRetentionClass
    log_retention: TrialRetentionClass
    cache_retention: TrialRetentionClass

    def __post_init__(self) -> None:
        if not all(isinstance(value, TrialRetentionClass) for value in vars(self).values()):
            raise RealDataTrialError("retention_policy_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {key: value.value for key, value in vars(self).items()
                if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialLoggingPolicy(_Canonical):
    logging_class: TrialLoggingClass
    raw_content_logging_allowed: bool
    policy_version: str

    def __post_init__(self) -> None:
        if (not isinstance(self.logging_class, TrialLoggingClass)
                or type(self.raw_content_logging_allowed) is not bool
                or not is_identifier(self.policy_version)):
            raise RealDataTrialError("logging_policy_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"logging_class": self.logging_class.value,
                "policy_version": self.policy_version,
                "raw_content_logging_allowed": self.raw_content_logging_allowed}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialCachePolicy(_Canonical):
    cache_class: TrialCacheClass
    raw_content_cache_allowed: bool
    policy_version: str

    def __post_init__(self) -> None:
        if (not isinstance(self.cache_class, TrialCacheClass)
                or type(self.raw_content_cache_allowed) is not bool
                or not is_identifier(self.policy_version)):
            raise RealDataTrialError("cache_policy_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"cache_class": self.cache_class.value,
                "policy_version": self.policy_version,
                "raw_content_cache_allowed": self.raw_content_cache_allowed}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialExportPolicy(_Canonical):
    export_class: TrialExportClass
    export_allowed: bool
    policy_version: str

    def __post_init__(self) -> None:
        if (not isinstance(self.export_class, TrialExportClass)
                or type(self.export_allowed) is not bool
                or not is_identifier(self.policy_version)):
            raise RealDataTrialError("export_policy_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"export_allowed": self.export_allowed,
                "export_class": self.export_class.value,
                "policy_version": self.policy_version}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class TrialPersistencePolicy(_Canonical):
    persistence_class: TrialPersistenceClass
    persistent_write_allowed: bool
    raw_content_persistence_allowed: bool
    policy_version: str

    def __post_init__(self) -> None:
        if (not isinstance(self.persistence_class, TrialPersistenceClass)
                or type(self.persistent_write_allowed) is not bool
                or type(self.raw_content_persistence_allowed) is not bool
                or not is_identifier(self.policy_version)):
            raise RealDataTrialError("persistence_policy_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"persistence_class": self.persistence_class.value,
                "persistent_write_allowed": self.persistent_write_allowed,
                "policy_version": self.policy_version,
                "raw_content_persistence_allowed": self.raw_content_persistence_allowed}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataTrialScope(_Canonical):
    trial_scope_id: str
    approved_session_digest: str
    environment_manifest_digest: str
    environment_approval_digest: str
    integration_manifest_digest: str
    fixture_validation_receipt_digest: str
    data_class_policy_digest: str
    allowed_stage_policy_digest: str
    retention_policy_digest: str
    logging_policy_digest: str
    cache_policy_digest: str
    export_policy_digest: str
    persistence_policy_digest: str
    requested_data_class: RealDataClass
    requested_stage_ceiling: RAGStage
    requested_retention_class: TrialRetentionClass
    requested_logging_class: TrialLoggingClass
    requested_cache_class: TrialCacheClass
    requested_export_class: TrialExportClass
    requested_persistence_class: TrialPersistenceClass
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        enum_values = (
            (self.requested_data_class, RealDataClass),
            (self.requested_stage_ceiling, RAGStage),
            (self.requested_retention_class, TrialRetentionClass),
            (self.requested_logging_class, TrialLoggingClass),
            (self.requested_cache_class, TrialCacheClass),
            (self.requested_export_class, TrialExportClass),
            (self.requested_persistence_class, TrialPersistenceClass),
        )
        if (not is_identifier(self.trial_scope_id)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))
                or not all(isinstance(value, expected) for value, expected in enum_values)
                or not is_aware(self.created_at) or not is_aware(self.expires_at)
                or self.expires_at <= self.created_at):
            raise RealDataTrialError("trial_scope_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {key: (canonical_datetime(value) if isinstance(value, datetime)
                      else value.value if isinstance(value, Enum) else value)
                for key, value in vars(self).items() if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


def validate_trial_scope_policies(
    scope: RealDataTrialScope,
    classification: RealDataClassificationPolicy,
    stages: TrialStagePolicy,
    retention: TrialRetentionPolicy,
    logging: TrialLoggingPolicy,
    cache: TrialCachePolicy,
    export: TrialExportPolicy,
    persistence: TrialPersistencePolicy,
) -> tuple[str, ...]:
    reasons: list[str] = []
    objects = (scope, classification, stages, retention, logging, cache, export, persistence)
    if not all(canonical_object_valid(value) for value in objects):
        reasons.append("forged_trial_policy_chain")
    if (scope.data_class_policy_digest != classification.canonical_digest
            or scope.allowed_stage_policy_digest != stages.canonical_digest
            or scope.retention_policy_digest != retention.canonical_digest
            or scope.logging_policy_digest != logging.canonical_digest
            or scope.cache_policy_digest != cache.canonical_digest
            or scope.export_policy_digest != export.canonical_digest
            or scope.persistence_policy_digest != persistence.canonical_digest):
        reasons.append("trial_policy_digest_mismatch")
    if (scope.requested_data_class not in classification.allowed_data_classes
            or scope.requested_data_class in classification.prohibited_data_classes
            or RealDataClass.CREDENTIAL_LIKE not in classification.prohibited_data_classes
            or RealDataClass.HIGHLY_RESTRICTED not in classification.prohibited_data_classes
            or set(classification.export_prohibited_classes) != set(RealDataClass)):
        reasons.append("trial_data_class_prohibited")
    if (scope.requested_stage_ceiling != stages.max_stage
            or scope.requested_stage_ceiling not in stages.allowed_stages
            or stages.allowed_stages != tuple(RAGStage)[:4]
            or stages.prohibited_stages != tuple(RAGStage)[4:]
            or stages.masking_required_before_stage is not RAGStage.CHUNKING
            or stages.approval_required_before_stage is not RAGStage.INPUT_CANDIDATE
            or stages.max_stage.value in {
                RAGStage.EMBEDDING.value, RAGStage.VECTOR_WRITE.value,
                RAGStage.RETRIEVAL.value, RAGStage.PROMPT.value,
                RAGStage.LLM_INPUT.value, RAGStage.RESPONSE.value,
                RAGStage.LOGGING_CACHE.value,
            }):
        reasons.append("trial_stage_policy_unsafe")
    retention_values = tuple(value for key, value in vars(retention).items()
                             if key != "canonical_digest")
    if (scope.requested_retention_class is not TrialRetentionClass.NONE
            or any(value is not TrialRetentionClass.NONE for value in retention_values)):
        reasons.append("trial_retention_policy_unsafe")
    if (scope.requested_logging_class is not TrialLoggingClass.DIGEST_AND_REASON_ONLY
            or logging.logging_class is not TrialLoggingClass.DIGEST_AND_REASON_ONLY
            or logging.raw_content_logging_allowed):
        reasons.append("trial_logging_policy_unsafe")
    if (scope.requested_cache_class is not TrialCacheClass.NONE
            or cache.cache_class is not TrialCacheClass.NONE
            or cache.raw_content_cache_allowed):
        reasons.append("trial_cache_policy_unsafe")
    if (scope.requested_export_class is not TrialExportClass.PROHIBITED
            or export.export_class is not TrialExportClass.PROHIBITED
            or export.export_allowed):
        reasons.append("trial_export_policy_unsafe")
    if (scope.requested_persistence_class is not TrialPersistenceClass.NONE
            or persistence.persistence_class is not TrialPersistenceClass.NONE
            or persistence.persistent_write_allowed
            or persistence.raw_content_persistence_allowed):
        reasons.append("trial_persistence_policy_unsafe")
    return tuple(dict.fromkeys(reasons))


__all__ = [
    "RealDataClass", "RealDataClassificationPolicy", "RealDataTrialError",
    "RealDataTrialScope", "TrialCacheClass", "TrialCachePolicy",
    "TrialExportClass", "TrialExportPolicy", "TrialLoggingClass",
    "TrialLoggingPolicy", "TrialPersistenceClass", "TrialPersistencePolicy",
    "TrialRetentionClass", "TrialRetentionPolicy", "TrialStagePolicy",
    "validate_trial_scope_policies",
]
