from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock

from ragguard.actual_content_classification import (
    ActualContentClassification,
    classify_actual_content,
)
from ragguard.actual_content_masking import (
    ActualContentMasking,
    ActualMaskingOutcome,
    mask_actual_content,
)
from ragguard.actual_trial_root import (
    ActualTrialRootCapability,
    ActualTrialRootError,
    ActualTrialRootUse,
    HumanSelectedOpaqueTarget,
)
from ragguard.local_rag_integration import RAGStage
from ragguard.one_shot_trial_preparation import (
    ExecutionPreparationRequest,
    ExecutionPreparationState,
    OneShotTrialExecutionPacket,
    _evaluate_preparation,
)
from ragguard.real_data_access import RealDataClass
from ragguard.real_data_access_authorization import (
    AuthorizationUsageCounterContract,
    RealDataAccessAuthorizationLifecycle,
    RealDataAccessAuthorizationRecord,
    _consume_authorization_usage_for_verified_read,
)
from ragguard.real_data_read_execution import (
    RealDataReadAuthorizationContext,
    _LIMITED_READ_EXECUTOR_MARKER,
)
from ragguard.real_target_resolver import _close_fd, _metadata_digest
from ragguard.real_trial_approval import (
    ApprovedOneShotRealDataTrial,
    ApprovedOneShotRealDataTrialLifecycle,
    RealTrialApprovalRequest,
    RealTrialApprovalRoleContext,
    RealTrialApprovalSourceContext,
    TrialDataGovernanceReview,
    TrialExecutionApproval,
    TrialSecurityReview,
)
from ragguard.real_trial_root import (
    LinkReparseVerificationResult,
    NetworkIsolationVerificationResult,
    PermissionVerificationResult,
    RealTrialClosureRequirement,
    RealTrialPurpose,
    RealTrialRootIdentity,
    RealTrialRootProvisioningRequest,
    RealTrialTargetSelection,
    RootConfinementVerificationResult,
    RootProvisioningAttestation,
    WriteProhibitionVerificationResult,
)
from ragguard.storage_adapter import (
    canonical_datetime,
    canonical_json,
    canonical_object_valid,
    digest,
    is_aware,
    is_digest,
    is_identifier,
)


_ACTUAL_LEDGER_EXECUTOR_MARKER = object()
_SMALL_DOCUMENT_MAX_BYTES = 64 * 1024


class ActualTrialExecutionError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class HumanExecutionApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ActualTrialExecutionState(str, Enum):
    REJECTED_PRE_READ = "rejected_pre_read"
    OPEN_FAILED = "open_failed"
    READ_FAILED = "read_failed"
    IDENTITY_FAILED = "identity_failed"
    CLASSIFICATION_FAILED = "classification_failed"
    MASKING_FAILED = "masking_failed"
    CHUNKING_FAILED = "chunking_failed"
    COMMIT_FAILED = "commit_failed"
    COMPLETED = "completed"


class ActualTrialFailureReason(str, Enum):
    INVALID_PACKET_CHAIN = "invalid_packet_chain"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    HUMAN_APPROVAL_REJECTED = "human_approval_rejected"
    HUMAN_APPROVAL_INVALID = "human_approval_invalid"
    OPERATOR_MISMATCH = "operator_mismatch"
    AUTHORIZATION_INVALID = "authorization_invalid"
    ROOT_MISMATCH = "root_mismatch"
    TARGET_MISMATCH = "target_mismatch"
    REPLAY = "replay"
    OPEN_FAILED = "open_failed"
    READ_FAILED = "read_failed"
    IDENTITY_MISMATCH = "identity_mismatch"
    CLASSIFICATION_REJECTED = "classification_rejected"
    CLASSIFICATION_AMBIGUOUS = "classification_ambiguous"
    MASKING_FAILED = "masking_failed"
    MASKING_RESIDUE = "masking_residue"
    CHUNKING_FAILED = "chunking_failed"
    CHUNKING_RESIDUE = "chunking_residue"
    COMMIT_FAULT = "commit_fault"


def _is_utc(value: object) -> bool:
    return is_aware(value) and value.utcoffset() == timedelta(0)


@dataclass(frozen=True, repr=False)
class HumanExecutionApproval:
    approval_id: str
    packet_digest: str
    operator_id: str
    approved_at: datetime
    expires_at: datetime
    approval_result: HumanExecutionApprovalResult
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.approval_id)
            or not is_digest(self.packet_digest)
            or not is_identifier(self.operator_id)
            or not _is_utc(self.approved_at)
            or not _is_utc(self.expires_at)
            or self.expires_at <= self.approved_at
            or not isinstance(self.approval_result, HumanExecutionApprovalResult)
        ):
            raise ActualTrialExecutionError("human_execution_approval_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "HumanExecutionApproval(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "approval_id": self.approval_id,
                "approval_result": self.approval_result.value,
                "approved_at": canonical_datetime(self.approved_at),
                "expires_at": canonical_datetime(self.expires_at),
                "operator_id": self.operator_id,
                "packet_digest": self.packet_digest,
            }
        )


@dataclass(frozen=True, repr=False)
class ActualExecutionObjectChain:
    preparation_request: ExecutionPreparationRequest
    approved_trial: ApprovedOneShotRealDataTrial
    source_context: RealTrialApprovalSourceContext
    purpose: RealTrialPurpose
    provisioning_request: RealTrialRootProvisioningRequest
    root_identity: RealTrialRootIdentity
    root_confinement: RootConfinementVerificationResult
    link_reparse: LinkReparseVerificationResult
    permission: PermissionVerificationResult
    write_prohibition: WriteProhibitionVerificationResult
    network_isolation: NetworkIsolationVerificationResult
    root_attestation: RootProvisioningAttestation
    target_selection: RealTrialTargetSelection
    closure_requirement: RealTrialClosureRequirement
    approval_request: RealTrialApprovalRequest
    security_review: TrialSecurityReview
    governance_review: TrialDataGovernanceReview
    execution_approval: TrialExecutionApproval
    roles: RealTrialApprovalRoleContext
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        objects = tuple(
            value
            for key, value in vars(self).items()
            if key != "canonical_digest"
        )
        if not all(canonical_object_valid(item) for item in objects):
            raise ActualTrialExecutionError("actual_execution_object_chain_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualExecutionObjectChain(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                key: value.canonical_digest
                for key, value in vars(self).items()
                if key != "canonical_digest"
            }
        )


@dataclass(frozen=True, repr=False)
class ActualTrialGateDecision:
    packet_digest: str
    object_chain_digest: str
    evaluated_at: datetime
    ready_for_explicit_execution: bool
    reason_codes: tuple[str, ...]
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not is_digest(self.packet_digest)
            or not is_digest(self.object_chain_digest)
            or not _is_utc(self.evaluated_at)
            or type(self.ready_for_explicit_execution) is not bool
            or not isinstance(self.reason_codes, tuple)
            or not all(isinstance(item, str) and item for item in self.reason_codes)
            or self.ready_for_explicit_execution == bool(self.reason_codes)
        ):
            raise ActualTrialExecutionError("actual_trial_gate_decision_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualTrialGateDecision(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "evaluated_at": canonical_datetime(self.evaluated_at),
                "object_chain_digest": self.object_chain_digest,
                "packet_digest": self.packet_digest,
                "ready_for_explicit_execution": self.ready_for_explicit_execution,
                "reason_codes": list(self.reason_codes),
            }
        )


def evaluate_actual_trial_gate(
    *,
    packet: OneShotTrialExecutionPacket,
    object_chain: ActualExecutionObjectChain,
) -> ActualTrialGateDecision:
    if not canonical_object_valid(packet) or not canonical_object_valid(object_chain):
        raise ActualTrialExecutionError("actual_trial_gate_input_invalid")
    try:
        decision = _evaluate_preparation(
            replay_snapshot=(frozenset(), frozenset()),
            packet=packet,
            request=object_chain.preparation_request,
            approved_trial=object_chain.approved_trial,
            source_context=object_chain.source_context,
            purpose=object_chain.purpose,
            provisioning_request=object_chain.provisioning_request,
            root_identity=object_chain.root_identity,
            root_confinement=object_chain.root_confinement,
            link_reparse=object_chain.link_reparse,
            permission=object_chain.permission,
            write_prohibition=object_chain.write_prohibition,
            network_isolation=object_chain.network_isolation,
            root_attestation=object_chain.root_attestation,
            target_selection=object_chain.target_selection,
            closure_requirement=object_chain.closure_requirement,
            approval_request=object_chain.approval_request,
            security_review=object_chain.security_review,
            governance_review=object_chain.governance_review,
            execution_approval=object_chain.execution_approval,
            roles=object_chain.roles,
        )
    except (AttributeError, TypeError, ValueError):
        return ActualTrialGateDecision(
            packet.canonical_digest,
            object_chain.canonical_digest,
            object_chain.preparation_request.evaluation_time,
            False,
            (ActualTrialFailureReason.INVALID_PACKET_CHAIN.value,),
        )
    ready = (
        decision.state
        is ExecutionPreparationState.READY_FOR_EXPLICIT_EXECUTION_APPROVAL
        and decision.ready_for_explicit_execution_approval
        and not decision.execution_authorized
        and not decision.file_read_executed
        and decision.packet_digest == packet.canonical_digest
        and decision.side_effects.all_zero
    )
    reasons = () if ready else tuple(item.value for item in decision.reasons)
    if not reasons and not ready:
        reasons = (ActualTrialFailureReason.INVALID_PACKET_CHAIN.value,)
    return ActualTrialGateDecision(
        packet.canonical_digest,
        object_chain.canonical_digest,
        object_chain.preparation_request.evaluation_time,
        ready,
        reasons,
    )


@dataclass(frozen=True, repr=False)
class ActualChunkingCandidate:
    masking_digest: str
    transformed_content_digest: str
    chunking_policy_digest: str
    chunk_count: int
    chunk_digests: tuple[str, ...]
    sensitive_residue_detected: bool
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not all(
                is_digest(item)
                for item in (
                    self.masking_digest,
                    self.transformed_content_digest,
                    self.chunking_policy_digest,
                )
            )
            or not isinstance(self.chunk_count, int)
            or self.chunk_count < 1
            or not isinstance(self.chunk_digests, tuple)
            or self.chunk_count != len(self.chunk_digests)
            or not all(is_digest(item) for item in self.chunk_digests)
            or type(self.sensitive_residue_detected) is not bool
        ):
            raise ActualTrialExecutionError("chunking_candidate_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualChunkingCandidate(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "chunk_count": self.chunk_count,
                "chunk_digests": list(self.chunk_digests),
                "chunking_policy_digest": self.chunking_policy_digest,
                "masking_digest": self.masking_digest,
                "sensitive_residue_detected": self.sensitive_residue_detected,
                "transformed_content_digest": self.transformed_content_digest,
            }
        )


def create_actual_chunking_candidate(
    masking_outcome: ActualMaskingOutcome,
    *,
    chunking_policy_digest: str,
    max_tokens_per_chunk: int = 16,
) -> ActualChunkingCandidate:
    if (
        not isinstance(masking_outcome, ActualMaskingOutcome)
        or not canonical_object_valid(masking_outcome.evidence)
        or not masking_outcome.evidence.verified
        or not is_digest(chunking_policy_digest)
        or not isinstance(max_tokens_per_chunk, int)
        or not 1 <= max_tokens_per_chunk <= 64
    ):
        raise ActualTrialExecutionError("chunking_input_invalid")
    transformed = masking_outcome.transformed_content
    if digest(transformed) != masking_outcome.evidence.transformed_content_digest:
        raise ActualTrialExecutionError("chunking_masking_binding_mismatch")
    residue = classify_actual_content(
        transformed.encode("utf-8"),
        policy_digest=chunking_policy_digest,
    )
    sensitive = not residue.approved_internal_low
    tokens = transformed.split()
    chunks = [
        " ".join(tokens[index : index + max_tokens_per_chunk])
        for index in range(0, len(tokens), max_tokens_per_chunk)
    ]
    if not chunks:
        raise ActualTrialExecutionError("chunking_empty")
    chunk_digests = tuple(digest(item) for item in chunks)
    del chunks
    del tokens
    return ActualChunkingCandidate(
        masking_outcome.evidence.canonical_digest,
        masking_outcome.evidence.transformed_content_digest,
        chunking_policy_digest,
        len(chunk_digests),
        chunk_digests,
        sensitive,
    )


@dataclass(frozen=True, repr=False)
class ActualTrialSideEffects:
    approved_file_open_count: int = 0
    approved_file_read_count: int = 0
    actual_local_rag_material_access_count: int = 0
    restricted_material_access_count: int = 0
    arbitrary_filesystem_scan_count: int = 0
    network_count: int = 0
    http_count: int = 0
    cloud_count: int = 0
    persistent_vector_db_write_count: int = 0
    filesystem_production_write_count: int = 0
    database_write_count: int = 0
    production_registry_write_count: int = 0
    credential_token_use_count: int = 0
    runtime_activation_switch_count: int = 0
    embedding_count: int = 0
    persistence_count: int = 0
    export_count: int = 0
    raw_retention_count: int = 0
    raw_logging_count: int = 0
    raw_cache_count: int = 0
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        values = tuple(value for key, value in vars(self).items() if key != "canonical_digest")
        if not all(isinstance(item, int) and item >= 0 for item in values):
            raise ActualTrialExecutionError("actual_side_effect_accounting_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualTrialSideEffects(<safe>)"

    @property
    def prohibited_all_zero(self) -> bool:
        allowed = {"approved_file_open_count", "approved_file_read_count", "actual_local_rag_material_access_count"}
        return all(
            value == 0
            for key, value in vars(self).items()
            if key not in allowed and key != "canonical_digest"
        )

    def canonical_json(self) -> str:
        return canonical_json(
            {
                key: value
                for key, value in vars(self).items()
                if key != "canonical_digest"
            }
        )


@dataclass(frozen=True, repr=False)
class ActualOneShotTrialReceipt:
    receipt_id: str
    packet_digest: str
    human_approval_digest: str
    approved_trial_digest: str
    authorization_before_digest: str
    authorization_after_digest: str
    usage_before_digest: str
    usage_after_digest: str
    target_digest: str
    raw_content_digest: str
    classification_digest: str
    masking_digest: str
    chunking_digest: str
    operator_id: str
    issued_at: datetime
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        digests = tuple(
            value
            for key, value in vars(self).items()
            if key.endswith("_digest") and key != "canonical_digest"
        )
        if (
            not is_identifier(self.receipt_id)
            or not all(is_digest(item) for item in digests)
            or not is_identifier(self.operator_id)
            or not _is_utc(self.issued_at)
        ):
            raise ActualTrialExecutionError("actual_receipt_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualOneShotTrialReceipt(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                key: canonical_datetime(value) if isinstance(value, datetime) else value
                for key, value in vars(self).items()
                if key != "canonical_digest"
            }
        )


@dataclass(frozen=True, repr=False)
class ActualTrialClosureRecord:
    closure_id: str
    receipt_digest: str
    packet_digest: str
    approved_trial_digest: str
    exhausted_authorization_digest: str
    operator_id: str
    closed_at: datetime
    state: str = "completed"
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.closure_id)
            or not all(
                is_digest(item)
                for item in (
                    self.receipt_digest,
                    self.packet_digest,
                    self.approved_trial_digest,
                    self.exhausted_authorization_digest,
                )
            )
            or not is_identifier(self.operator_id)
            or not _is_utc(self.closed_at)
            or self.state != "completed"
        ):
            raise ActualTrialExecutionError("actual_closure_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualTrialClosureRecord(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "approved_trial_digest": self.approved_trial_digest,
                "closed_at": canonical_datetime(self.closed_at),
                "closure_id": self.closure_id,
                "exhausted_authorization_digest": self.exhausted_authorization_digest,
                "operator_id": self.operator_id,
                "packet_digest": self.packet_digest,
                "receipt_digest": self.receipt_digest,
                "state": self.state,
            }
        )


@dataclass(frozen=True, repr=False)
class ActualPostReadEvidence:
    receipt_digest: str
    classification_digest: str
    masking_digest: str
    chunking_digest: str
    usage_after_digest: str
    closure_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        values = tuple(value for key, value in vars(self).items() if key != "canonical_digest")
        if not all(is_digest(item) for item in values):
            raise ActualTrialExecutionError("actual_post_read_evidence_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualPostReadEvidence(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {key: value for key, value in vars(self).items() if key != "canonical_digest"}
        )


@dataclass(frozen=True, repr=False)
class ActualTrialExecutionResult:
    succeeded: bool
    state: ActualTrialExecutionState
    reasons: tuple[ActualTrialFailureReason, ...]
    gate_digest: str
    packet_digest: str
    human_approval_digest: str | None
    operator_id: str
    target_digest: str
    classification: ActualContentClassification | None
    masking: ActualContentMasking | None
    chunking: ActualChunkingCandidate | None
    receipt: ActualOneShotTrialReceipt | None
    closure: ActualTrialClosureRecord | None
    post_read_evidence: ActualPostReadEvidence | None
    authorization_after: RealDataAccessAuthorizationRecord | None
    usage_after: AuthorizationUsageCounterContract | None
    side_effects: ActualTrialSideEffects
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.succeeded) is not bool
            or not isinstance(self.state, ActualTrialExecutionState)
            or not isinstance(self.reasons, tuple)
            or not all(isinstance(item, ActualTrialFailureReason) for item in self.reasons)
            or not all(is_digest(item) for item in (self.gate_digest, self.packet_digest, self.target_digest))
            or (self.human_approval_digest is not None and not is_digest(self.human_approval_digest))
            or not is_identifier(self.operator_id)
            or not canonical_object_valid(self.side_effects)
            or self.succeeded != (self.state is ActualTrialExecutionState.COMPLETED)
            or self.succeeded == bool(self.reasons)
        ):
            raise ActualTrialExecutionError("actual_execution_result_invalid")
        evidence = (
            self.classification,
            self.masking,
            self.chunking,
            self.receipt,
            self.closure,
            self.post_read_evidence,
            self.authorization_after,
            self.usage_after,
        )
        if any(item is not None and not canonical_object_valid(item) for item in evidence):
            raise ActualTrialExecutionError("actual_execution_result_evidence_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualTrialExecutionResult(<safe>)"

    def canonical_json(self) -> str:
        def item_digest(value: object | None) -> str | None:
            return getattr(value, "canonical_digest", None) if value is not None else None

        return canonical_json(
            {
                "authorization_after_digest": item_digest(self.authorization_after),
                "chunking_digest": item_digest(self.chunking),
                "classification_digest": item_digest(self.classification),
                "closure_digest": item_digest(self.closure),
                "gate_digest": self.gate_digest,
                "human_approval_digest": self.human_approval_digest,
                "masking_digest": item_digest(self.masking),
                "operator_id": self.operator_id,
                "packet_digest": self.packet_digest,
                "post_read_evidence_digest": item_digest(self.post_read_evidence),
                "reasons": [item.value for item in self.reasons],
                "receipt_digest": item_digest(self.receipt),
                "side_effects_digest": self.side_effects.canonical_digest,
                "state": self.state.value,
                "succeeded": self.succeeded,
                "target_digest": self.target_digest,
                "usage_after_digest": item_digest(self.usage_after),
            }
        )


@dataclass(frozen=True)
class _ActualLedgerState:
    receipts: tuple[ActualOneShotTrialReceipt, ...] = ()
    closures: tuple[ActualTrialClosureRecord, ...] = ()
    post_read_evidence: tuple[ActualPostReadEvidence, ...] = ()
    exhausted_authorizations: tuple[RealDataAccessAuthorizationRecord, ...] = ()
    usage_states: tuple[AuthorizationUsageCounterContract, ...] = ()
    used_packet_digests: frozenset[str] = frozenset()
    used_approval_digests: frozenset[str] = frozenset()
    used_target_digests: frozenset[str] = frozenset()
    spent_failed_approval_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class ActualTrialExecutionLedger:
    """Process-local atomic ledger; it exposes no persistence interface."""

    __slots__ = ("_state", "_lock")

    def __init__(self) -> None:
        self._state = _ActualLedgerState()
        self._lock = RLock()

    @property
    def receipts(self) -> tuple[ActualOneShotTrialReceipt, ...]:
        with self._lock:
            return self._state.receipts

    @property
    def closures(self) -> tuple[ActualTrialClosureRecord, ...]:
        with self._lock:
            return self._state.closures

    @property
    def post_read_evidence(self) -> tuple[ActualPostReadEvidence, ...]:
        with self._lock:
            return self._state.post_read_evidence

    @property
    def write_count(self) -> int:
        with self._lock:
            return self._state.write_count

    @property
    def mutation_count(self) -> int:
        with self._lock:
            return self._state.mutation_count

    @property
    def event_count(self) -> int:
        with self._lock:
            return self._state.event_count

    def replay_snapshot(self) -> tuple[frozenset[str], ...]:
        with self._lock:
            return (
                self._state.used_packet_digests,
                self._state.used_approval_digests,
                self._state.used_target_digests,
                self._state.spent_failed_approval_digests,
            )

    def _approval_unavailable(self, approval_digest: str) -> bool:
        with self._lock:
            return approval_digest in (
                self._state.used_approval_digests
                | self._state.spent_failed_approval_digests
            )

    def _record_failed_attempt(self, approval_digest: str, *, marker: object) -> None:
        if marker is not _ACTUAL_LEDGER_EXECUTOR_MARKER:
            raise ActualTrialExecutionError("actual_ledger_authority_invalid")
        with self._lock:
            state = self._state
            if approval_digest in (
                state.used_approval_digests
                | state.spent_failed_approval_digests
            ):
                return
            self._state = replace(
                state,
                spent_failed_approval_digests=(
                    state.spent_failed_approval_digests | {approval_digest}
                ),
                mutation_count=state.mutation_count + 1,
                event_count=state.event_count + 1,
            )

    def _commit_success(
        self,
        *,
        packet_digest: str,
        approval_digest: str,
        target_digest: str,
        receipt: ActualOneShotTrialReceipt,
        closure: ActualTrialClosureRecord,
        evidence: ActualPostReadEvidence,
        exhausted: RealDataAccessAuthorizationRecord,
        usage_after: AuthorizationUsageCounterContract,
        marker: object,
        fault: bool,
    ) -> bool:
        if marker is not _ACTUAL_LEDGER_EXECUTOR_MARKER:
            raise ActualTrialExecutionError("actual_ledger_authority_invalid")
        with self._lock:
            state = self._state
            if (
                packet_digest in state.used_packet_digests
                or approval_digest in state.used_approval_digests
                or approval_digest in state.spent_failed_approval_digests
                or target_digest in state.used_target_digests
            ):
                return False
            candidate = replace(
                state,
                receipts=state.receipts + (receipt,),
                closures=state.closures + (closure,),
                post_read_evidence=state.post_read_evidence + (evidence,),
                exhausted_authorizations=(
                    state.exhausted_authorizations + (exhausted,)
                ),
                usage_states=state.usage_states + (usage_after,),
                used_packet_digests=state.used_packet_digests | {packet_digest},
                used_approval_digests=state.used_approval_digests | {approval_digest},
                used_target_digests=state.used_target_digests | {target_digest},
                write_count=state.write_count + 1,
                mutation_count=state.mutation_count + 1,
                event_count=state.event_count + 1,
            )
            if fault:
                return False
            self._state = candidate
            return True


class ActualOneShotTrialExecutor:
    __slots__ = (
        "_before_open_hook",
        "_after_read_hook",
        "_force_masking_residue",
        "_force_chunking_residue",
        "_commit_fault",
    )

    def __init__(self) -> None:
        self._before_open_hook = None
        self._after_read_hook = None
        self._force_masking_residue = False
        self._force_chunking_residue = False
        self._commit_fault = False

    def _failure(
        self,
        *,
        state: ActualTrialExecutionState,
        reasons: tuple[ActualTrialFailureReason, ...],
        gate: ActualTrialGateDecision,
        packet: OneShotTrialExecutionPacket,
        approval: HumanExecutionApproval | None,
        operator_id: str,
        target: HumanSelectedOpaqueTarget,
        side_effects: ActualTrialSideEffects,
        classification: ActualContentClassification | None = None,
        masking: ActualContentMasking | None = None,
        chunking: ActualChunkingCandidate | None = None,
    ) -> ActualTrialExecutionResult:
        return ActualTrialExecutionResult(
            False,
            state,
            reasons,
            gate.canonical_digest,
            packet.canonical_digest,
            approval.canonical_digest if approval is not None else None,
            operator_id,
            target.canonical_digest,
            classification,
            masking,
            chunking,
            None,
            None,
            None,
            None,
            None,
            side_effects,
        )

    def execute(
        self,
        *,
        receipt_id: str,
        closure_id: str,
        packet: OneShotTrialExecutionPacket,
        gate: ActualTrialGateDecision,
        human_approval: HumanExecutionApproval | None,
        root_capability: ActualTrialRootCapability,
        target: HumanSelectedOpaqueTarget,
        object_chain: ActualExecutionObjectChain,
        authorization_context: RealDataReadAuthorizationContext,
        operator_id: str,
        executed_at: datetime,
        ledger: ActualTrialExecutionLedger,
    ) -> ActualTrialExecutionResult:
        if not isinstance(ledger, ActualTrialExecutionLedger):
            raise ActualTrialExecutionError("actual_executor_input_invalid")
        with ledger._lock:
            return self._execute_serialized(
                receipt_id=receipt_id,
                closure_id=closure_id,
                packet=packet,
                gate=gate,
                human_approval=human_approval,
                root_capability=root_capability,
                target=target,
                object_chain=object_chain,
                authorization_context=authorization_context,
                operator_id=operator_id,
                executed_at=executed_at,
                ledger=ledger,
            )

    def _execute_serialized(
        self,
        *,
        receipt_id: str,
        closure_id: str,
        packet: OneShotTrialExecutionPacket,
        gate: ActualTrialGateDecision,
        human_approval: HumanExecutionApproval | None,
        root_capability: ActualTrialRootCapability,
        target: HumanSelectedOpaqueTarget,
        object_chain: ActualExecutionObjectChain,
        authorization_context: RealDataReadAuthorizationContext,
        operator_id: str,
        executed_at: datetime,
        ledger: ActualTrialExecutionLedger,
    ) -> ActualTrialExecutionResult:
        zero = ActualTrialSideEffects()
        if not all(
            (
                is_identifier(receipt_id),
                is_identifier(closure_id),
                canonical_object_valid(packet),
                canonical_object_valid(gate),
                canonical_object_valid(target),
                canonical_object_valid(object_chain),
                canonical_object_valid(authorization_context),
                canonical_object_valid(root_capability),
                is_identifier(operator_id),
                isinstance(root_capability, ActualTrialRootCapability),
                _is_utc(executed_at),
                isinstance(ledger, ActualTrialExecutionLedger),
            )
        ):
            raise ActualTrialExecutionError("actual_executor_input_invalid")
        expected_gate = evaluate_actual_trial_gate(packet=packet, object_chain=object_chain)
        if (
            not gate.ready_for_explicit_execution
            or gate.canonical_digest != expected_gate.canonical_digest
            or gate.packet_digest != packet.canonical_digest
            or gate.object_chain_digest != object_chain.canonical_digest
        ):
            return self._failure(
                state=ActualTrialExecutionState.REJECTED_PRE_READ,
                reasons=(ActualTrialFailureReason.INVALID_PACKET_CHAIN,),
                gate=gate,
                packet=packet,
                approval=human_approval,
                operator_id=operator_id,
                target=target,
                side_effects=zero,
            )
        if human_approval is None:
            return self._failure(
                state=ActualTrialExecutionState.REJECTED_PRE_READ,
                reasons=(ActualTrialFailureReason.HUMAN_APPROVAL_REQUIRED,),
                gate=gate,
                packet=packet,
                approval=None,
                operator_id=operator_id,
                target=target,
                side_effects=zero,
            )
        if not canonical_object_valid(human_approval):
            return self._failure(
                state=ActualTrialExecutionState.REJECTED_PRE_READ,
                reasons=(ActualTrialFailureReason.HUMAN_APPROVAL_INVALID,),
                gate=gate,
                packet=packet,
                approval=human_approval,
                operator_id=operator_id,
                target=target,
                side_effects=zero,
            )
        if human_approval.approval_result is not HumanExecutionApprovalResult.APPROVED:
            return self._failure(
                state=ActualTrialExecutionState.REJECTED_PRE_READ,
                reasons=(ActualTrialFailureReason.HUMAN_APPROVAL_REJECTED,),
                gate=gate,
                packet=packet,
                approval=human_approval,
                operator_id=operator_id,
                target=target,
                side_effects=zero,
            )
        access = object_chain.source_context.read_authorization_context
        source_exact = (
            authorization_context is access,
            packet.approved_trial_digest == object_chain.approved_trial.canonical_digest,
            packet.access_authorization_digest
            == authorization_context.authorization_record.canonical_digest,
            packet.operator_assignment_digest
            == authorization_context.operator_assignment.canonical_digest,
        )
        approval_exact = (
            human_approval.packet_digest == packet.canonical_digest,
        )
        operator_exact = (
            packet.operator_id == operator_id,
            human_approval.operator_id == operator_id,
            object_chain.approved_trial.operator_id == operator_id,
            object_chain.roles.operator_id == operator_id,
            object_chain.target_selection.operator_id == operator_id,
        )
        root_exact = (
            root_capability.root_descriptor_digest
            == object_chain.source_context.root_descriptor.canonical_digest,
            root_capability.resolver_policy_digest
            == object_chain.source_context.resolver_policy.canonical_digest,
            root_capability.target_reference_digest
            == object_chain.source_context.controlled_target_reference.canonical_digest,
            root_capability.root_metadata_digest
            == object_chain.root_identity.root_identity_digest,
        )
        target_exact = (
            root_capability.target_identity_digest
            == object_chain.target_selection.target_identity_digest,
            target.target_identity_digest
            == object_chain.target_selection.target_identity_digest,
            target.target_reference_digest
            == object_chain.target_selection.controlled_target_reference_digest,
            packet.target_selection_digest
            == object_chain.target_selection.canonical_digest,
            packet.root_identity_digest == object_chain.root_identity.canonical_digest,
            packet.root_attestation_digest
            == object_chain.root_attestation.canonical_digest,
            packet.purpose_digest == object_chain.purpose.canonical_digest,
            packet.closure_requirement_digest
            == object_chain.closure_requirement.canonical_digest,
            packet.stage_ceiling is RAGStage.CHUNKING,
            not any(
                (
                    packet.raw_retention_allowed,
                    packet.raw_logging_allowed,
                    packet.raw_cache_allowed,
                    packet.persistence_allowed,
                    packet.export_allowed,
                    packet.network_allowed,
                )
            ),
        )
        if not all(source_exact + approval_exact + operator_exact + root_exact + target_exact):
            reasons = (
                ActualTrialFailureReason.INVALID_PACKET_CHAIN
                if not all(source_exact)
                else ActualTrialFailureReason.HUMAN_APPROVAL_INVALID
                if not all(approval_exact)
                else ActualTrialFailureReason.OPERATOR_MISMATCH
                if not all(operator_exact)
                else ActualTrialFailureReason.ROOT_MISMATCH
                if not all(root_exact)
                else ActualTrialFailureReason.TARGET_MISMATCH
            )
            return self._failure(
                state=ActualTrialExecutionState.REJECTED_PRE_READ,
                reasons=(reasons,),
                gate=gate,
                packet=packet,
                approval=human_approval,
                operator_id=operator_id,
                target=target,
                side_effects=zero,
            )
        authorization = authorization_context.authorization_record
        usage_before = authorization_context.usage_contract
        temporal = (
            packet.issued_at
            <= object_chain.preparation_request.evaluation_time
            <= human_approval.approved_at
            <= executed_at
            < human_approval.expires_at
            and executed_at < packet.expires_at
            and executed_at < object_chain.approved_trial.expires_at
            and executed_at < authorization.expires_at
            and executed_at < object_chain.provisioning_request.expires_at
            and executed_at < object_chain.root_identity.expires_at
            and executed_at < object_chain.root_attestation.expires_at
            and executed_at < object_chain.approval_request.expires_at
            and executed_at < object_chain.execution_approval.expires_at
        )
        live = (
            authorization.lifecycle is RealDataAccessAuthorizationLifecycle.AUTHORIZED
            and authorization.remaining_read_count == 1
            and usage_before.remaining_read_count == 1
            and object_chain.approved_trial.lifecycle
            is ApprovedOneShotRealDataTrialLifecycle.APPROVED
        )
        if not temporal or not live:
            return self._failure(
                state=ActualTrialExecutionState.REJECTED_PRE_READ,
                reasons=(ActualTrialFailureReason.AUTHORIZATION_INVALID,),
                gate=gate,
                packet=packet,
                approval=human_approval,
                operator_id=operator_id,
                target=target,
                side_effects=zero,
            )
        replay = ledger.replay_snapshot()
        if (
            packet.canonical_digest in replay[0]
            or human_approval.canonical_digest in replay[1]
            or target.canonical_digest in replay[2]
            or human_approval.canonical_digest in replay[3]
        ):
            return self._failure(
                state=ActualTrialExecutionState.REJECTED_PRE_READ,
                reasons=(ActualTrialFailureReason.REPLAY,),
                gate=gate,
                packet=packet,
                approval=human_approval,
                operator_id=operator_id,
                target=target,
                side_effects=zero,
            )

        descriptor = -1
        raw_buffer: bytearray | None = None
        opened = False
        read = False
        classification: ActualContentClassification | None = None
        masking: ActualContentMasking | None = None
        chunking: ActualChunkingCandidate | None = None
        side_effects = zero

        def after_read_failure(
            state: ActualTrialExecutionState,
            reasons: tuple[ActualTrialFailureReason, ...],
        ) -> ActualTrialExecutionResult:
            ledger._record_failed_attempt(
                human_approval.canonical_digest,
                marker=_ACTUAL_LEDGER_EXECUTOR_MARKER,
            )
            return self._failure(
                state=state,
                reasons=reasons,
                gate=gate,
                packet=packet,
                approval=human_approval,
                operator_id=operator_id,
                target=target,
                side_effects=side_effects,
                classification=classification,
                masking=masking,
                chunking=chunking,
            )

        try:
            if self._before_open_hook is not None:
                self._before_open_hook()
                self._before_open_hook = None
            try:
                descriptor, pre_stat = root_capability._open_selected_target(target)
                opened = True
                side_effects = replace(
                    side_effects,
                    approved_file_open_count=1,
                )
            except ActualTrialRootError:
                ledger._record_failed_attempt(
                    human_approval.canonical_digest,
                    marker=_ACTUAL_LEDGER_EXECUTOR_MARKER,
                )
                return self._failure(
                    state=ActualTrialExecutionState.OPEN_FAILED,
                    reasons=(ActualTrialFailureReason.OPEN_FAILED,),
                    gate=gate,
                    packet=packet,
                    approval=human_approval,
                    operator_id=operator_id,
                    target=target,
                    side_effects=side_effects,
                )
            try:
                raw_buffer = bytearray(os.read(descriptor, _SMALL_DOCUMENT_MAX_BYTES + 1))
                read = True
                side_effects = replace(
                    side_effects,
                    approved_file_read_count=1,
                    actual_local_rag_material_access_count=(
                        1
                        if root_capability.root_use
                        is ActualTrialRootUse.HUMAN_SELECTED_ACTUAL
                        else 0
                    ),
                )
            except OSError:
                return after_read_failure(
                    ActualTrialExecutionState.READ_FAILED,
                    (ActualTrialFailureReason.READ_FAILED,),
                )
            if len(raw_buffer) != pre_stat.st_size or len(raw_buffer) > _SMALL_DOCUMENT_MAX_BYTES:
                return after_read_failure(
                    ActualTrialExecutionState.READ_FAILED,
                    (ActualTrialFailureReason.READ_FAILED,),
                )
            if self._after_read_hook is not None:
                self._after_read_hook()
                self._after_read_hook = None
            post_stat = os.fstat(descriptor)
            if _metadata_digest(pre_stat) != _metadata_digest(post_stat):
                return after_read_failure(
                    ActualTrialExecutionState.IDENTITY_FAILED,
                    (ActualTrialFailureReason.IDENTITY_MISMATCH,),
                )
            classification = classify_actual_content(
                raw_buffer,
                policy_digest=object_chain.target_selection.expected_classification_digest,
            )
            if classification.ambiguous:
                return after_read_failure(
                    ActualTrialExecutionState.CLASSIFICATION_FAILED,
                    (ActualTrialFailureReason.CLASSIFICATION_AMBIGUOUS,),
                )
            if (
                not classification.approved_internal_low
                or object_chain.target_selection.data_class is not RealDataClass.INTERNAL_LOW
            ):
                return after_read_failure(
                    ActualTrialExecutionState.CLASSIFICATION_FAILED,
                    (ActualTrialFailureReason.CLASSIFICATION_REJECTED,),
                )
            masking_policy_digest = digest(
                canonical_json(
                    {
                        "access_policy_digest": authorization_context.access_policy.canonical_digest,
                        "operation": "token-digest-mask-v030",
                    }
                )
            )
            try:
                masking_outcome = mask_actual_content(
                    raw_buffer,
                    classification=classification,
                    masking_policy_digest=masking_policy_digest,
                )
            except ValueError:
                return after_read_failure(
                    ActualTrialExecutionState.MASKING_FAILED,
                    (ActualTrialFailureReason.MASKING_FAILED,),
                )
            masking = masking_outcome.evidence
            if self._force_masking_residue:
                self._force_masking_residue = False
                masking = replace(
                    masking,
                    prohibited_residue_detected=True,
                    verified=False,
                )
            if not masking.verified or masking.prohibited_residue_detected:
                return after_read_failure(
                    ActualTrialExecutionState.MASKING_FAILED,
                    (ActualTrialFailureReason.MASKING_RESIDUE,),
                )
            chunking_policy_digest = digest(
                canonical_json(
                    {
                        "purpose_digest": object_chain.purpose.canonical_digest,
                        "stage": RAGStage.CHUNKING.value,
                        "tokens_per_chunk": 16,
                    }
                )
            )
            try:
                chunking = create_actual_chunking_candidate(
                    masking_outcome,
                    chunking_policy_digest=chunking_policy_digest,
                )
            except ValueError:
                return after_read_failure(
                    ActualTrialExecutionState.CHUNKING_FAILED,
                    (ActualTrialFailureReason.CHUNKING_FAILED,),
                )
            if self._force_chunking_residue:
                self._force_chunking_residue = False
                chunking = replace(chunking, sensitive_residue_detected=True)
            if chunking.sensitive_residue_detected:
                return after_read_failure(
                    ActualTrialExecutionState.CHUNKING_FAILED,
                    (ActualTrialFailureReason.CHUNKING_RESIDUE,),
                )
            exhausted, usage_after = _consume_authorization_usage_for_verified_read(
                authorization,
                usage_before,
                executor_marker=_LIMITED_READ_EXECUTOR_MARKER,
            )
            receipt = ActualOneShotTrialReceipt(
                receipt_id,
                packet.canonical_digest,
                human_approval.canonical_digest,
                object_chain.approved_trial.canonical_digest,
                authorization.canonical_digest,
                exhausted.canonical_digest,
                usage_before.canonical_digest,
                usage_after.canonical_digest,
                target.canonical_digest,
                classification.raw_content_digest,
                classification.canonical_digest,
                masking.canonical_digest,
                chunking.canonical_digest,
                operator_id,
                executed_at,
            )
            closure = ActualTrialClosureRecord(
                closure_id,
                receipt.canonical_digest,
                packet.canonical_digest,
                object_chain.approved_trial.canonical_digest,
                exhausted.canonical_digest,
                operator_id,
                executed_at,
            )
            evidence = ActualPostReadEvidence(
                receipt.canonical_digest,
                classification.canonical_digest,
                masking.canonical_digest,
                chunking.canonical_digest,
                usage_after.canonical_digest,
                closure.canonical_digest,
            )
            committed = ledger._commit_success(
                packet_digest=packet.canonical_digest,
                approval_digest=human_approval.canonical_digest,
                target_digest=target.canonical_digest,
                receipt=receipt,
                closure=closure,
                evidence=evidence,
                exhausted=exhausted,
                usage_after=usage_after,
                marker=_ACTUAL_LEDGER_EXECUTOR_MARKER,
                fault=self._commit_fault,
            )
            self._commit_fault = False
            if not committed:
                return after_read_failure(
                    ActualTrialExecutionState.COMMIT_FAILED,
                    (ActualTrialFailureReason.COMMIT_FAULT,),
                )
            return ActualTrialExecutionResult(
                True,
                ActualTrialExecutionState.COMPLETED,
                (),
                gate.canonical_digest,
                packet.canonical_digest,
                human_approval.canonical_digest,
                operator_id,
                target.canonical_digest,
                classification,
                masking,
                chunking,
                receipt,
                closure,
                evidence,
                exhausted,
                usage_after,
                side_effects,
            )
        finally:
            _close_fd(descriptor)
            root_capability.close()
            if raw_buffer is not None:
                for index in range(len(raw_buffer)):
                    raw_buffer[index] = 0
                raw_buffer.clear()
            if opened or read:
                pass


def _install_actual_execution_test_hook(
    executor: ActualOneShotTrialExecutor,
    *,
    before_open=None,
    after_read=None,
    masking_residue: bool = False,
    chunking_residue: bool = False,
    commit_fault: bool = False,
) -> None:
    """Private controlled-fixture hook; absent from the package public API."""
    if (
        not isinstance(executor, ActualOneShotTrialExecutor)
        or (before_open is not None and not callable(before_open))
        or (after_read is not None and not callable(after_read))
        or not all(
            type(item) is bool
            for item in (masking_residue, chunking_residue, commit_fault)
        )
    ):
        raise ActualTrialExecutionError("actual_execution_test_hook_invalid")
    executor._before_open_hook = before_open
    executor._after_read_hook = after_read
    executor._force_masking_residue = masking_residue
    executor._force_chunking_residue = chunking_residue
    executor._commit_fault = commit_fault


__all__ = [
    "ActualChunkingCandidate",
    "ActualExecutionObjectChain",
    "ActualOneShotTrialExecutor",
    "ActualOneShotTrialReceipt",
    "ActualPostReadEvidence",
    "ActualTrialClosureRecord",
    "ActualTrialExecutionError",
    "ActualTrialExecutionLedger",
    "ActualTrialExecutionResult",
    "ActualTrialExecutionState",
    "ActualTrialFailureReason",
    "ActualTrialGateDecision",
    "ActualTrialRootUse",
    "ActualTrialSideEffects",
    "HumanExecutionApproval",
    "HumanExecutionApprovalResult",
    "create_actual_chunking_candidate",
    "evaluate_actual_trial_gate",
]
