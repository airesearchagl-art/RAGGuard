from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping

from ragguard.storage_adapter import (
    canonical_datetime,
    canonical_json,
    canonical_object_valid,
    digest,
    is_aware,
    is_digest,
    is_identifier,
)


CANONICAL_LOCAL_RAG_INTEGRATION_DIGEST_ALGORITHM = "sha256"
_RECEIPT_MARKER = object()
_MASK = "[MASKED]"


class LocalRAGIntegrationError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class IntegrationDataClass(str, Enum):
    SYNTHETIC_ONLY = "synthetic_only"
    CONTROLLED_FIXTURE_ONLY = "controlled_fixture_only"


class SensitiveClass(str, Enum):
    CUSTOMER_NAME = "synthetic_customer_name"
    PROJECT_NUMBER = "synthetic_project_number"
    CONTRACT = "synthetic_contract_information"
    PERSONAL = "synthetic_personal_information"
    EMAIL = "synthetic_email"
    PHONE = "synthetic_phone_number"
    INTERNAL_CODE = "synthetic_internal_code"
    CREDENTIAL_LIKE = "synthetic_credential_like_string"


class RAGStage(str, Enum):
    INPUT_CANDIDATE = "input_candidate"
    POLICY_DECISION = "ragguard_policy_decision"
    MASKING = "masking_sanitization"
    CHUNKING = "chunking_candidate"
    EMBEDDING = "embedding_input_candidate"
    VECTOR_WRITE = "vector_store_write_candidate"
    RETRIEVAL = "retrieval_candidate"
    PROMPT = "prompt_construction_candidate"
    LLM_INPUT = "llm_input_candidate"
    RESPONSE = "response_candidate"
    LOGGING_CACHE = "logging_cache_candidate"


class PersistenceClass(str, Enum):
    NONE = "none"
    MEMORY_TEST_ONLY = "memory_test_only"


class LoggingClass(str, Enum):
    DIGEST_AND_REASON_ONLY = "digest_and_reason_only"


class ExternalIOClass(str, Enum):
    PROHIBITED = "prohibited"


class StageGateState(str, Enum):
    BLOCKED = "blocked"
    NEEDS_MASKING = "needs_masking"
    ELIGIBLE_FOR_NEXT_STAGE = "eligible_for_next_stage"
    ELIGIBLE_FOR_CONTROLLED_EMBEDDING = "eligible_for_controlled_embedding"
    ELIGIBLE_FOR_CONTROLLED_RETRIEVAL = "eligible_for_controlled_retrieval"


class IntegrationResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class ReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class TrialEligibilityState(str, Enum):
    INELIGIBLE = "ineligible"
    NEEDS_INTEGRATION_VALIDATION = "needs_integration_validation"
    NEEDS_SECURITY_REVIEW = "needs_security_review"
    ELIGIBLE_FOR_REAL_DATA_TRIAL_REVIEW = "eligible_for_real_data_trial_review"


class ChunkLifecycle(str, Enum):
    APPROVED = "approved"
    REPLACED = "replaced"
    REVOKED = "revoked"


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


@dataclass(frozen=True, repr=False)
class LocalRAGIntegrationManifest(_Canonical):
    integration_id: str
    integration_version: str
    ragguard_policy_digest: str
    masking_policy_digest: str
    chunking_policy_digest: str
    embedding_policy_digest: str
    retrieval_policy_digest: str
    prompt_policy_digest: str
    logging_policy_digest: str
    cache_policy_digest: str
    network_policy_digest: str
    data_class: IntegrationDataClass

    def __post_init__(self) -> None:
        values = vars(self)
        if (not is_identifier(self.integration_id)
                or not is_identifier(self.integration_version)
                or not isinstance(self.data_class, IntegrationDataClass)
                or not all(is_digest(v) for k, v in values.items() if k.endswith("_digest"))):
            raise LocalRAGIntegrationError("manifest_invalid")
        self._seal({k: (v.value if isinstance(v, Enum) else v)
                    for k, v in values.items() if k != "canonical_digest"})

    def canonical_json(self) -> str:
        return canonical_json({
            k: (v.value if isinstance(v, Enum) else v)
            for k, v in vars(self).items() if k != "canonical_digest"
        })


@dataclass(frozen=True, repr=False)
class DataFlowStageContract(_Canonical):
    stage: RAGStage
    input_digest: str
    output_digest: str
    allowed_data_classes: tuple[IntegrationDataClass, ...]
    prohibited_data_classes: tuple[str, ...]
    persistence_class: PersistenceClass
    logging_class: LoggingClass
    external_io_class: ExternalIOClass

    def __post_init__(self) -> None:
        if (not isinstance(self.stage, RAGStage)
                or not is_digest(self.input_digest) or not is_digest(self.output_digest)
                or not self.allowed_data_classes
                or not all(isinstance(v, IntegrationDataClass) for v in self.allowed_data_classes)
                or not self.prohibited_data_classes
                or not all(is_identifier(v) for v in self.prohibited_data_classes)
                or not isinstance(self.persistence_class, PersistenceClass)
                or not isinstance(self.logging_class, LoggingClass)
                or not isinstance(self.external_io_class, ExternalIOClass)):
            raise LocalRAGIntegrationError("data_flow_stage_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {
            "allowed_data_classes": sorted(v.value for v in self.allowed_data_classes),
            "external_io_class": self.external_io_class.value,
            "input_digest": self.input_digest,
            "logging_class": self.logging_class.value,
            "output_digest": self.output_digest,
            "persistence_class": self.persistence_class.value,
            "prohibited_data_classes": sorted(self.prohibited_data_classes),
            "stage": self.stage.value,
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class LocalRAGDataFlowPlan(_Canonical):
    plan_id: str
    integration_manifest_digest: str
    stages: tuple[DataFlowStageContract, ...]

    def __post_init__(self) -> None:
        if (not is_identifier(self.plan_id) or not is_digest(self.integration_manifest_digest)
                or tuple(v.stage for v in self.stages) != tuple(RAGStage)
                or not all(canonical_object_valid(v) for v in self.stages)):
            raise LocalRAGIntegrationError("data_flow_plan_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"integration_manifest_digest": self.integration_manifest_digest,
                "plan_id": self.plan_id,
                "stage_digests": [v.canonical_digest for v in self.stages]}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class SyntheticConfidentialFixture(_Canonical):
    fixture_id: str
    fields: tuple[tuple[SensitiveClass, str], ...]
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (not is_identifier(self.fixture_id) or not self.fields
                or not all(isinstance(k, SensitiveClass) and isinstance(v, str) and v
                            for k, v in self.fields)
                or len({k for k, _ in self.fields}) != len(self.fields)
                or not is_aware(self.created_at) or not is_aware(self.expires_at)
                or self.expires_at <= self.created_at):
            raise LocalRAGIntegrationError("fixture_invalid")
        self._seal({"created_at": canonical_datetime(self.created_at),
                    "expires_at": canonical_datetime(self.expires_at),
                    "field_digests": sorted((k.value, digest(v)) for k, v in self.fields),
                    "fixture_id": self.fixture_id})

    def canonical_json(self) -> str:
        return canonical_json({"created_at": canonical_datetime(self.created_at),
            "expires_at": canonical_datetime(self.expires_at),
            "field_digests": sorted((k.value, digest(v)) for k, v in self.fields),
            "fixture_id": self.fixture_id})


@dataclass(frozen=True, repr=False)
class ConfidentialityTransformationRecord(_Canonical):
    source_digest: str
    transformed_digest: str
    detected_sensitive_classes: tuple[SensitiveClass, ...]
    masked_classes: tuple[SensitiveClass, ...]
    blocked_classes: tuple[SensitiveClass, ...]
    retained_classes: tuple[str, ...]
    transformation_policy_digest: str

    def __post_init__(self) -> None:
        if (not is_digest(self.source_digest) or not is_digest(self.transformed_digest)
                or not is_digest(self.transformation_policy_digest)
                or not all(isinstance(v, SensitiveClass) for values in (
                    self.detected_sensitive_classes, self.masked_classes, self.blocked_classes)
                    for v in values)
                or not all(is_identifier(v) for v in self.retained_classes)
                or set(self.masked_classes) & set(self.blocked_classes)
                or set(self.detected_sensitive_classes) != set(self.masked_classes) | set(self.blocked_classes)):
            raise LocalRAGIntegrationError("transformation_record_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"blocked_classes": sorted(v.value for v in self.blocked_classes),
            "detected_sensitive_classes": sorted(v.value for v in self.detected_sensitive_classes),
            "masked_classes": sorted(v.value for v in self.masked_classes),
            "retained_classes": sorted(self.retained_classes), "source_digest": self.source_digest,
            "transformation_policy_digest": self.transformation_policy_digest,
            "transformed_digest": self.transformed_digest}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class ApprovedChunk(_Canonical):
    chunk_id: str
    content: str
    source_transformation_digest: str
    lifecycle: ChunkLifecycle = ChunkLifecycle.APPROVED

    def __post_init__(self) -> None:
        if (not is_identifier(self.chunk_id) or not self.content
                or not is_digest(self.source_transformation_digest)
                or not isinstance(self.lifecycle, ChunkLifecycle)
                or contains_credential_like(self.content)):
            raise LocalRAGIntegrationError("chunk_invalid")
        self._seal({"chunk_id": self.chunk_id, "content_digest": digest(self.content),
                    "lifecycle": self.lifecycle.value,
                    "source_transformation_digest": self.source_transformation_digest})

    def canonical_json(self) -> str:
        return canonical_json({"chunk_id": self.chunk_id, "content_digest": digest(self.content),
            "lifecycle": self.lifecycle.value,
            "source_transformation_digest": self.source_transformation_digest})


@dataclass(frozen=True, repr=False)
class StageGateDecision(_Canonical):
    stage: RAGStage
    state: StageGateState
    candidate_digest: str
    reason_codes: tuple[str, ...]
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if (not isinstance(self.stage, RAGStage) or not isinstance(self.state, StageGateState)
                or not is_digest(self.candidate_digest) or not self.reason_codes
                or not all(is_identifier(v) for v in self.reason_codes)
                or not is_aware(self.evaluated_at)):
            raise LocalRAGIntegrationError("stage_gate_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"candidate_digest": self.candidate_digest,
                "evaluated_at": canonical_datetime(self.evaluated_at),
                "reason_codes": list(self.reason_codes), "stage": self.stage.value,
                "state": self.state.value}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def production_safe(self) -> bool:
        return False

    @property
    def real_data_approved(self) -> bool:
        return False

    @property
    def production_authorized(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class BoundaryResult(_Canonical):
    boundary_id: str
    accepted: bool
    input_digest: str
    output_digest: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (not is_identifier(self.boundary_id) or type(self.accepted) is not bool
                or not is_digest(self.input_digest) or not is_digest(self.output_digest)
                or not self.reason_codes or not all(is_identifier(v) for v in self.reason_codes)):
            raise LocalRAGIntegrationError("boundary_result_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"accepted": self.accepted, "boundary_id": self.boundary_id,
                "input_digest": self.input_digest, "output_digest": self.output_digest,
                "reason_codes": list(self.reason_codes)}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True)
class ExternalIOCounters:
    external_network_count: int = 0
    http_count: int = 0
    cloud_count: int = 0
    external_api_count: int = 0
    credential_use_count: int = 0
    token_use_count: int = 0
    persistent_vector_write_count: int = 0
    production_registry_write_count: int = 0
    real_data_access_count: int = 0

    @property
    def all_zero(self) -> bool:
        return all(type(v) is int and v == 0 for v in vars(self).values())


@dataclass(frozen=True, repr=False)
class LocalRAGIntegrationReceipt(_Canonical):
    integration_manifest_digest: str
    data_flow_plan_digest: str
    fixture_manifest_digest: str
    stage_result_digests: tuple[str, ...]
    masking_result_digest: str
    embedding_boundary_digest: str
    retrieval_boundary_digest: str
    prompt_boundary_digest: str
    logging_boundary_digest: str
    executed_at: datetime
    result: IntegrationResult
    _marker: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        digest_values = (self.integration_manifest_digest, self.data_flow_plan_digest,
            self.fixture_manifest_digest, *self.stage_result_digests, self.masking_result_digest,
            self.embedding_boundary_digest, self.retrieval_boundary_digest,
            self.prompt_boundary_digest, self.logging_boundary_digest)
        if (not all(is_digest(v) for v in digest_values) or not self.stage_result_digests
                or not is_aware(self.executed_at) or not isinstance(self.result, IntegrationResult)
                or self.result is IntegrationResult.PASSED and self._marker is not _RECEIPT_MARKER):
            raise LocalRAGIntegrationError("integration_receipt_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"data_flow_plan_digest": self.data_flow_plan_digest,
            "embedding_boundary_digest": self.embedding_boundary_digest,
            "executed_at": canonical_datetime(self.executed_at),
            "fixture_manifest_digest": self.fixture_manifest_digest,
            "integration_manifest_digest": self.integration_manifest_digest,
            "logging_boundary_digest": self.logging_boundary_digest,
            "masking_result_digest": self.masking_result_digest,
            "prompt_boundary_digest": self.prompt_boundary_digest,
            "result": self.result.value, "retrieval_boundary_digest": self.retrieval_boundary_digest,
            "stage_result_digests": list(self.stage_result_digests)}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class IntegrationRoleContext(_Canonical):
    operator_id: str
    reviewer_id: str
    approver_id: str

    def __post_init__(self) -> None:
        if not all(is_identifier(v) for v in vars(self).values()) or len(set(vars(self).values())) != 3:
            raise LocalRAGIntegrationError("integration_role_conflict")
        self._seal({"approver_id": self.approver_id, "operator_id": self.operator_id,
                    "reviewer_id": self.reviewer_id})

    def canonical_json(self) -> str:
        return canonical_json({"approver_id": self.approver_id,
            "operator_id": self.operator_id, "reviewer_id": self.reviewer_id})


@dataclass(frozen=True, repr=False)
class IntegrationReview(_Canonical):
    receipt_digest: str
    reviewer_id: str
    result: ReviewResult
    reviewed_at: datetime

    def __post_init__(self) -> None:
        if (not is_digest(self.receipt_digest) or not is_identifier(self.reviewer_id)
                or not isinstance(self.result, ReviewResult) or not is_aware(self.reviewed_at)):
            raise LocalRAGIntegrationError("integration_review_invalid")
        self._seal(self._payload())

    def _payload(self):
        return {"receipt_digest": self.receipt_digest, "reviewed_at": canonical_datetime(self.reviewed_at),
                "reviewer_id": self.reviewer_id, "result": self.result.value}

    def canonical_json(self):
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class IntegrationApproval(_Canonical):
    receipt_digest: str
    review_digest: str
    approver_id: str
    result: ReviewResult
    approved_at: datetime

    def __post_init__(self) -> None:
        if (not is_digest(self.receipt_digest) or not is_digest(self.review_digest)
                or not is_identifier(self.approver_id) or not isinstance(self.result, ReviewResult)
                or not is_aware(self.approved_at)):
            raise LocalRAGIntegrationError("integration_approval_invalid")
        self._seal(self._payload())

    def _payload(self):
        return {"approved_at": canonical_datetime(self.approved_at), "approver_id": self.approver_id,
                "receipt_digest": self.receipt_digest, "result": self.result.value,
                "review_digest": self.review_digest}

    def canonical_json(self):
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataTrialEligibility(_Canonical):
    state: TrialEligibilityState
    receipt_digest: str
    review_digest: str
    approval_digest: str
    reason_codes: tuple[str, ...]
    evaluated_at: datetime
    real_data_approved: bool = field(init=False, default=False)
    real_data_use_authorized: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        if (not isinstance(self.state, TrialEligibilityState)
                or not all(is_digest(v) for v in (
                    self.receipt_digest, self.review_digest, self.approval_digest))
                or not self.reason_codes or not all(is_identifier(v) for v in self.reason_codes)
                or not is_aware(self.evaluated_at)):
            raise LocalRAGIntegrationError("trial_eligibility_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {"approval_digest": self.approval_digest,
            "evaluated_at": canonical_datetime(self.evaluated_at), "reason_codes": list(self.reason_codes),
            "receipt_digest": self.receipt_digest, "review_digest": self.review_digest,
            "state": self.state.value}

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


_CREDENTIAL = re.compile(r"(?i)(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+")


def contains_credential_like(text: str) -> bool:
    return bool(_CREDENTIAL.search(text))


def transform_fixture(fixture: SyntheticConfidentialFixture, policy_digest: str
                      ) -> tuple[str, ConfidentialityTransformationRecord]:
    if not canonical_object_valid(fixture) or not is_digest(policy_digest):
        raise LocalRAGIntegrationError("transformation_input_invalid")
    source = "\n".join(value for _, value in fixture.fields)
    transformed = "\n".join(f"{kind.value}={_MASK}" for kind, _ in fixture.fields)
    kinds = tuple(kind for kind, _ in fixture.fields)
    record = ConfidentialityTransformationRecord(
        digest(source), digest(transformed), kinds, kinds, (), ("public_structure",), policy_digest)
    return transformed, record


def evaluate_stage_gate(*, stage: RAGStage, candidate_digest: str,
        detected_classes: tuple[SensitiveClass, ...], transformed: bool,
        blocked: bool, evaluated_at: datetime) -> StageGateDecision:
    if blocked:
        state, reason = StageGateState.BLOCKED, "policy_blocked"
    elif detected_classes and not transformed:
        state, reason = StageGateState.NEEDS_MASKING, "sensitive_class_detected"
    elif stage is RAGStage.EMBEDDING:
        state, reason = StageGateState.ELIGIBLE_FOR_CONTROLLED_EMBEDDING, "masked_input_only"
    elif stage is RAGStage.RETRIEVAL:
        state, reason = StageGateState.ELIGIBLE_FOR_CONTROLLED_RETRIEVAL, "approved_source_only"
    else:
        state, reason = StageGateState.ELIGIBLE_FOR_NEXT_STAGE, "controlled_candidate"
    return StageGateDecision(stage, state, candidate_digest, (reason,), evaluated_at)


def evaluate_embedding_boundary(content: str,
        transformation: ConfidentialityTransformationRecord) -> BoundaryResult:
    accepted = (canonical_object_valid(transformation)
                and not transformation.blocked_classes
                and digest(content) == transformation.transformed_digest
                and not contains_credential_like(content))
    return BoundaryResult("embedding-boundary", accepted, digest(content), digest(content),
        ("approved_masked_only" if accepted else "raw_or_prohibited_embedding_input",))


def evaluate_retrieval_boundary(chunk: ApprovedChunk | None,
        transformation: ConfidentialityTransformationRecord) -> BoundaryResult:
    accepted = (chunk is not None and canonical_object_valid(chunk)
                and canonical_object_valid(transformation)
                and chunk.lifecycle is ChunkLifecycle.APPROVED
                and chunk.source_transformation_digest == transformation.canonical_digest
                and digest(chunk.content) == transformation.transformed_digest)
    input_digest = chunk.canonical_digest if chunk is not None else digest("missing")
    output_digest = digest(chunk.content) if accepted and chunk is not None else digest("blocked")
    return BoundaryResult("retrieval-boundary", accepted, input_digest, output_digest,
        ("approved_source_bound" if accepted else "blocked_stale_revoked_or_forged_source",))


def evaluate_prompt_boundary(chunks: tuple[ApprovedChunk, ...],
        metadata: Mapping[str, str]) -> BoundaryResult:
    forbidden_metadata = {"system", "system_prompt", "instruction", "credential", "token"}
    approved = (bool(chunks) and all(canonical_object_valid(v)
                and v.lifecycle is ChunkLifecycle.APPROVED for v in chunks))
    metadata_safe = (all(is_identifier(k) and isinstance(v, str) and is_identifier(v)
                         for k, v in metadata.items())
                     and not forbidden_metadata.intersection(k.lower() for k in metadata))
    raw = "\n".join(v.content for v in chunks)
    accepted = approved and metadata_safe and not contains_credential_like(raw)
    return BoundaryResult("prompt-boundary", accepted,
        digest(canonical_json([v.canonical_digest for v in chunks])),
        digest(raw) if accepted else digest("blocked"),
        ("approved_retrieval_only" if accepted else "unsafe_prompt_or_metadata",))


def evaluate_logging_cache_boundary(summary: Mapping[str, str]) -> BoundaryResult:
    safe_keys = {"candidate_digest", "result_digest", "reason_code", "state", "stage"}
    accepted = (bool(summary) and set(summary).issubset(safe_keys)
                and all(isinstance(v, str) and (is_digest(v) or is_identifier(v))
                        for v in summary.values())
                and not any(contains_credential_like(v) for v in summary.values()))
    candidate_digest = digest(canonical_json(dict(summary)))
    return BoundaryResult("logging-cache-boundary", accepted, candidate_digest,
        candidate_digest if accepted else digest("blocked"),
        ("digest_reason_only" if accepted else "unsafe_logging_or_cache",))


class TestOnlyVectorStore:
    __test__ = False

    def __init__(self) -> None:
        self._chunks: dict[str, ApprovedChunk] = {}
        self.write_count = 0
        self.rejected_write_count = 0

    @property
    def chunks(self) -> tuple[ApprovedChunk, ...]:
        return tuple(self._chunks.values())

    def write(self, chunk: ApprovedChunk, transformation: ConfidentialityTransformationRecord) -> bool:
        if (not canonical_object_valid(chunk) or not canonical_object_valid(transformation)
                or chunk.source_transformation_digest != transformation.canonical_digest
                or transformation.blocked_classes or digest(chunk.content) != transformation.transformed_digest
                or chunk.lifecycle is not ChunkLifecycle.APPROVED):
            self.rejected_write_count += 1
            return False
        self._chunks[chunk.chunk_id] = chunk
        self.write_count += 1
        return True

    def retrieve(self, chunk_id: str) -> ApprovedChunk | None:
        chunk = self._chunks.get(chunk_id)
        return chunk if chunk and chunk.lifecycle is ChunkLifecycle.APPROVED else None


def evaluate_trial_eligibility(receipt: LocalRAGIntegrationReceipt,
        review: IntegrationReview, approval: IntegrationApproval, roles: IntegrationRoleContext,
        *, evaluation_time: datetime) -> RealDataTrialEligibility:
    reasons: list[str] = []
    if not all(canonical_object_valid(v) for v in (receipt, review, approval, roles)):
        reasons.append("forged_chain")
    if (receipt.result is not IntegrationResult.PASSED
            or review.receipt_digest != receipt.canonical_digest
            or approval.receipt_digest != receipt.canonical_digest
            or approval.review_digest != review.canonical_digest):
        reasons.append("invalid_chain")
    if (review.reviewer_id != roles.reviewer_id or approval.approver_id != roles.approver_id):
        reasons.append("role_mismatch")
    if review.result is not ReviewResult.APPROVED or approval.result is not ReviewResult.APPROVED:
        reasons.append("not_approved_for_review")
    if not (receipt.executed_at < review.reviewed_at < approval.approved_at <= evaluation_time):
        reasons.append("temporal_invalid")
    state = (TrialEligibilityState.ELIGIBLE_FOR_REAL_DATA_TRIAL_REVIEW
             if not reasons else TrialEligibilityState.INELIGIBLE)
    return RealDataTrialEligibility(state, receipt.canonical_digest, review.canonical_digest,
        approval.canonical_digest, tuple(reasons or ["controlled_validation_approved"]), evaluation_time)


def issue_passed_receipt(*, manifest: LocalRAGIntegrationManifest, plan: LocalRAGDataFlowPlan,
        fixture: SyntheticConfidentialFixture, stage_results: tuple[StageGateDecision, ...],
        masking: ConfidentialityTransformationRecord, embedding: BoundaryResult,
        retrieval: BoundaryResult, prompt: BoundaryResult, logging: BoundaryResult,
        counters: ExternalIOCounters, executed_at: datetime) -> LocalRAGIntegrationReceipt:
    exact = (canonical_object_valid(manifest), canonical_object_valid(plan), canonical_object_valid(fixture),
        all(canonical_object_valid(v) for v in stage_results), canonical_object_valid(masking),
        all(canonical_object_valid(v) for v in (embedding, retrieval, prompt, logging)),
        plan.integration_manifest_digest == manifest.canonical_digest,
        masking.source_digest == digest("\n".join(value for _, value in fixture.fields)),
        masking.transformation_policy_digest == manifest.masking_policy_digest,
        tuple(v.stage for v in stage_results) == tuple(RAGStage),
        all(v.state not in {StageGateState.BLOCKED, StageGateState.NEEDS_MASKING}
            for v in stage_results),
        all(v.evaluated_at <= executed_at for v in stage_results),
        fixture.created_at <= executed_at < fixture.expires_at,
        embedding.boundary_id == "embedding-boundary",
        embedding.input_digest == masking.transformed_digest,
        embedding.output_digest == masking.transformed_digest,
        retrieval.boundary_id == "retrieval-boundary",
        prompt.boundary_id == "prompt-boundary",
        logging.boundary_id == "logging-cache-boundary",
        all(v.accepted for v in (embedding, retrieval, prompt, logging)), counters.all_zero)
    result = IntegrationResult.PASSED if all(exact) else IntegrationResult.FAILED
    return LocalRAGIntegrationReceipt(manifest.canonical_digest, plan.canonical_digest,
        fixture.canonical_digest, tuple(v.canonical_digest for v in stage_results),
        masking.canonical_digest, embedding.canonical_digest, retrieval.canonical_digest,
        prompt.canonical_digest, logging.canonical_digest, executed_at, result,
        _marker=_RECEIPT_MARKER if result is IntegrationResult.PASSED else None)


__all__ = [name for name in (
    "CANONICAL_LOCAL_RAG_INTEGRATION_DIGEST_ALGORITHM", "ApprovedChunk", "BoundaryResult",
    "ChunkLifecycle", "ConfidentialityTransformationRecord", "DataFlowStageContract",
    "ExternalIOClass", "ExternalIOCounters", "IntegrationApproval", "IntegrationDataClass",
    "IntegrationResult", "IntegrationReview", "IntegrationRoleContext", "LocalRAGDataFlowPlan",
    "LocalRAGIntegrationError", "LocalRAGIntegrationManifest", "LocalRAGIntegrationReceipt",
    "LoggingClass", "PersistenceClass", "RAGStage", "RealDataTrialEligibility", "ReviewResult",
    "SensitiveClass", "StageGateDecision", "StageGateState", "SyntheticConfidentialFixture",
    "TestOnlyVectorStore", "TrialEligibilityState", "contains_credential_like",
    "evaluate_embedding_boundary", "evaluate_logging_cache_boundary",
    "evaluate_prompt_boundary", "evaluate_retrieval_boundary", "evaluate_stage_gate",
    "evaluate_trial_eligibility", "issue_passed_receipt", "transform_fixture")]
