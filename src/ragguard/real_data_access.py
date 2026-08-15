from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ragguard.local_rag_integration import RAGStage
from ragguard.real_data_trial import (
    RealDataClass,
    RealDataClassificationPolicy,
    RealDataTrialScope,
    TrialCacheClass,
    TrialCachePolicy,
    TrialExportClass,
    TrialExportPolicy,
    TrialLoggingClass,
    TrialLoggingPolicy,
    TrialPersistenceClass,
    TrialPersistencePolicy,
    TrialRetentionClass,
    TrialRetentionPolicy,
    TrialStagePolicy,
    validate_trial_scope_policies,
)
from ragguard.real_data_trial_approval import (
    ApprovedRealDataTrialRecord,
    ApprovedTrialState,
    TrialLifecycle,
)
from ragguard.storage_adapter import (
    canonical_json,
    canonical_object_valid,
    digest,
    is_digest,
    is_identifier,
)


class RealDataAccessError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class RealDataAccessSourceClass(str, Enum):
    APPROVED_LOCAL_TRIAL_SOURCE = "approved_local_trial_source"


class RealDataDocumentClass(str, Enum):
    INTERNAL_LOW_DOCUMENT_CANDIDATE = "internal_low_document_candidate"
    INTERNAL_RESTRICTED_DOCUMENT_CANDIDATE = "internal_restricted_document_candidate"


class RealDataByteClass(str, Enum):
    SMALL_DOCUMENT = "small_document"
    LARGE_DOCUMENT = "large_document"


class RealDataAccessRetentionClass(str, Enum):
    NONE = "none"
    RAW_EPHEMERAL = "raw_ephemeral"


class RealDataAccessLoggingClass(str, Enum):
    NONE = "none"
    RAW = "raw"


class RealDataAccessCacheClass(str, Enum):
    NONE = "none"
    RAW = "raw"


class RealDataAccessPersistenceClass(str, Enum):
    NONE = "none"
    ALLOWED = "allowed"


class RealDataAccessExportClass(str, Enum):
    PROHIBITED = "prohibited"
    ALLOWED = "allowed"


class RealDataAccessNetworkClass(str, Enum):
    PROHIBITED = "prohibited"
    ALLOWED = "allowed"


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


@dataclass(frozen=True, repr=False)
class RealDataAccessSelector(_Canonical):
    selector_id: str
    data_class: RealDataClass
    source_class: RealDataAccessSourceClass
    document_class: RealDataDocumentClass
    classification_digest: str
    approved_trial_digest: str
    purpose_digest: str
    allowed_stage_ceiling: RAGStage
    selector_policy_digest: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.selector_id)
                or not isinstance(self.data_class, RealDataClass)
                or not isinstance(self.source_class, RealDataAccessSourceClass)
                or not isinstance(self.document_class, RealDataDocumentClass)
                or not isinstance(self.allowed_stage_ceiling, RAGStage)
                or not all(is_digest(value) for key, value in vars(self).items()
                           if key.endswith("_digest"))):
            raise RealDataAccessError("selector_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {key: value.value if isinstance(value, Enum) else value
                for key, value in vars(self).items() if key != "canonical_digest"}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataAccessPolicy(_Canonical):
    allowed_data_classes: tuple[RealDataClass, ...]
    allowed_document_classes: tuple[RealDataDocumentClass, ...]
    max_stage: RAGStage
    max_documents: int
    max_bytes_class: RealDataByteClass
    allowed_read_count: int
    masking_required_before_stage: RAGStage
    retention_class: RealDataAccessRetentionClass
    logging_class: RealDataAccessLoggingClass
    cache_class: RealDataAccessCacheClass
    persistence_class: RealDataAccessPersistenceClass
    export_class: RealDataAccessExportClass
    network_class: RealDataAccessNetworkClass

    def __post_init__(self) -> None:
        enum_values = (
            (self.max_stage, RAGStage),
            (self.max_bytes_class, RealDataByteClass),
            (self.masking_required_before_stage, RAGStage),
            (self.retention_class, RealDataAccessRetentionClass),
            (self.logging_class, RealDataAccessLoggingClass),
            (self.cache_class, RealDataAccessCacheClass),
            (self.persistence_class, RealDataAccessPersistenceClass),
            (self.export_class, RealDataAccessExportClass),
            (self.network_class, RealDataAccessNetworkClass),
        )
        if (not isinstance(self.allowed_data_classes, tuple)
                or not self.allowed_data_classes
                or not all(isinstance(value, RealDataClass)
                           for value in self.allowed_data_classes)
                or len(set(self.allowed_data_classes)) != len(self.allowed_data_classes)
                or not isinstance(self.allowed_document_classes, tuple)
                or not self.allowed_document_classes
                or not all(isinstance(value, RealDataDocumentClass)
                           for value in self.allowed_document_classes)
                or len(set(self.allowed_document_classes)) != len(
                    self.allowed_document_classes)
                or not all(isinstance(value, expected) for value, expected in enum_values)
                or type(self.max_documents) is not int or self.max_documents < 1
                or type(self.allowed_read_count) is not int or self.allowed_read_count < 1):
            raise RealDataAccessError("access_policy_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {
            "allowed_data_classes": sorted(value.value for value in self.allowed_data_classes),
            "allowed_document_classes": sorted(
                value.value for value in self.allowed_document_classes),
            "allowed_read_count": self.allowed_read_count,
            "cache_class": self.cache_class.value,
            "export_class": self.export_class.value,
            "logging_class": self.logging_class.value,
            "masking_required_before_stage": self.masking_required_before_stage.value,
            "max_bytes_class": self.max_bytes_class.value,
            "max_documents": self.max_documents,
            "max_stage": self.max_stage.value,
            "network_class": self.network_class.value,
            "persistence_class": self.persistence_class.value,
            "retention_class": self.retention_class.value,
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def retention_policy_digest(self) -> str:
        return digest(canonical_json({"retention_class": self.retention_class.value}))

    @property
    def logging_policy_digest(self) -> str:
        return digest(canonical_json({"logging_class": self.logging_class.value}))

    @property
    def persistence_policy_digest(self) -> str:
        return digest(canonical_json({
            "export_class": self.export_class.value,
            "network_class": self.network_class.value,
            "persistence_class": self.persistence_class.value,
        }))


def validate_real_data_access_selector_policy(
    selector: RealDataAccessSelector,
    policy: RealDataAccessPolicy,
    approved_trial: ApprovedRealDataTrialRecord,
    trial_scope: RealDataTrialScope,
    classification: RealDataClassificationPolicy,
    stages: TrialStagePolicy,
    retention: TrialRetentionPolicy,
    logging: TrialLoggingPolicy,
    cache: TrialCachePolicy,
    export: TrialExportPolicy,
    persistence: TrialPersistencePolicy,
) -> tuple[str, ...]:
    reasons: list[str] = []
    objects = (selector, policy, approved_trial, trial_scope, classification, stages,
               retention, logging, cache, export, persistence)
    if not all(canonical_object_valid(value) for value in objects):
        reasons.append("forged_access_selector_policy_chain")
    if validate_trial_scope_policies(
            trial_scope, classification, stages, retention, logging, cache,
            export, persistence):
        reasons.append("approved_trial_policy_invalid")
    exact = (
        selector.classification_digest == classification.canonical_digest,
        selector.approved_trial_digest == approved_trial.canonical_digest,
        selector.selector_policy_digest == policy.canonical_digest,
        selector.data_class == trial_scope.requested_data_class,
        selector.allowed_stage_ceiling == policy.max_stage,
        approved_trial.trial_scope_digest == trial_scope.canonical_digest,
        approved_trial.state is (
            ApprovedTrialState.APPROVED_FOR_REAL_DATA_ACCESS_AUTHORIZATION_REVIEW),
        approved_trial.lifecycle is TrialLifecycle.APPROVED,
    )
    if not all(exact):
        reasons.append("access_selector_binding_mismatch")
    if (selector.data_class is not RealDataClass.INTERNAL_LOW
            or selector.data_class not in policy.allowed_data_classes
            or policy.allowed_data_classes != (RealDataClass.INTERNAL_LOW,)
            or selector.source_class is not (
                RealDataAccessSourceClass.APPROVED_LOCAL_TRIAL_SOURCE)
            or selector.document_class is not (
                RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE)
            or policy.allowed_document_classes != (
                RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,)):
        reasons.append("access_classification_scope_widened")
    trial_stage_index = tuple(RAGStage).index(trial_scope.requested_stage_ceiling)
    policy_stage_index = tuple(RAGStage).index(policy.max_stage)
    if (selector.allowed_stage_ceiling is not policy.max_stage
            or stages.max_stage is not RAGStage.CHUNKING
            or trial_scope.requested_stage_ceiling is not RAGStage.CHUNKING
            or policy.masking_required_before_stage is not RAGStage.CHUNKING
            or policy.max_stage not in stages.allowed_stages
            or policy_stage_index > trial_stage_index
            or policy.max_stage.value in {
                RAGStage.EMBEDDING.value, RAGStage.VECTOR_WRITE.value,
                RAGStage.RETRIEVAL.value, RAGStage.PROMPT.value,
                RAGStage.LLM_INPUT.value, RAGStage.RESPONSE.value,
                RAGStage.LOGGING_CACHE.value,
            }):
        reasons.append("access_stage_ceiling_widened")
    if (policy.max_documents != 1
            or policy.max_bytes_class is not RealDataByteClass.SMALL_DOCUMENT
            or policy.allowed_read_count != 1):
        reasons.append("access_usage_scope_widened")
    if (policy.retention_class is not RealDataAccessRetentionClass.NONE
            or trial_scope.requested_retention_class is not TrialRetentionClass.NONE
            or policy.logging_class is not RealDataAccessLoggingClass.NONE
            or logging.logging_class is not TrialLoggingClass.DIGEST_AND_REASON_ONLY
            or logging.raw_content_logging_allowed
            or policy.cache_class is not RealDataAccessCacheClass.NONE
            or cache.cache_class is not TrialCacheClass.NONE
            or cache.raw_content_cache_allowed):
        reasons.append("access_retention_logging_cache_downgrade")
    if (policy.persistence_class is not RealDataAccessPersistenceClass.NONE
            or policy.export_class is not RealDataAccessExportClass.PROHIBITED
            or policy.network_class is not RealDataAccessNetworkClass.PROHIBITED
            or persistence.persistence_class is not TrialPersistenceClass.NONE
            or persistence.persistent_write_allowed
            or persistence.raw_content_persistence_allowed
            or export.export_class is not TrialExportClass.PROHIBITED
            or export.export_allowed):
        reasons.append("access_external_boundary_widened")
    return tuple(dict.fromkeys(reasons))


__all__ = [
    "RealDataAccessCacheClass",
    "RealDataAccessError", "RealDataAccessExportClass",
    "RealDataAccessLoggingClass", "RealDataAccessNetworkClass",
    "RealDataAccessPersistenceClass", "RealDataAccessPolicy",
    "RealDataAccessRetentionClass", "RealDataAccessSelector",
    "RealDataAccessSourceClass", "RealDataByteClass", "RealDataDocumentClass",
    "validate_real_data_access_selector_policy",
]
