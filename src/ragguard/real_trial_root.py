from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ragguard.local_rag_integration import RAGStage
from ragguard.real_data_access import (
    RealDataAccessCacheClass,
    RealDataAccessExportClass,
    RealDataAccessLoggingClass,
    RealDataAccessNetworkClass,
    RealDataAccessPersistenceClass,
    RealDataAccessRetentionClass,
    RealDataByteClass,
    RealDataDocumentClass,
)
from ragguard.real_data_trial import RealDataClass
from ragguard.real_target_resolver import (
    ControlledTargetReference,
    RealTargetResolverPolicy,
    TrialRootClass,
    TrialRootDescriptor,
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


class RealTrialRootError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class RealTrialPurposeClass(str, Enum):
    LOCAL_RAG_CONFIDENTIALITY_TRIAL = "local_rag_confidentiality_trial"


class RootProvisioningVerificationState(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class RootProvisioningAttestationState(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


def _is_utc(value: object) -> bool:
    return is_aware(value) and value.utcoffset() == timedelta(0)


def _payload(value: object) -> dict[str, object]:
    return {
        key: (
            canonical_datetime(item)
            if isinstance(item, datetime)
            else item.value
            if isinstance(item, Enum)
            else list(item)
            if isinstance(item, tuple)
            else item
        )
        for key, item in vars(value).items()
        if key != "canonical_digest"
    }


@dataclass(frozen=True, repr=False)
class RealTrialPurpose(_Canonical):
    purpose_id: str
    purpose_class: RealTrialPurposeClass
    maximum_stage: RAGStage
    expected_outcome_digest: str
    retention_class: RealDataAccessRetentionClass
    closure_required: bool
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.purpose_id)
            or self.purpose_class
            is not RealTrialPurposeClass.LOCAL_RAG_CONFIDENTIALITY_TRIAL
            or self.maximum_stage is not RAGStage.CHUNKING
            or not is_digest(self.expected_outcome_digest)
            or self.retention_class is not RealDataAccessRetentionClass.NONE
            or self.closure_required is not True
            or not _is_utc(self.created_at)
        ):
            raise RealTrialRootError("real_trial_purpose_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class RealTrialRootProvisioningRequest(_Canonical):
    provisioning_request_id: str
    approved_trial_record_digest: str
    access_authorization_record_digest: str
    purpose_digest: str
    root_descriptor_digest: str
    target_reference_digest: str
    root_provisioner_id: str
    operator_id: str
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        digest_values = tuple(
            item for key, item in vars(self).items() if key.endswith("_digest")
        )
        if (
            not is_identifier(self.provisioning_request_id)
            or not is_identifier(self.root_provisioner_id)
            or not is_identifier(self.operator_id)
            or not all(is_digest(item) for item in digest_values)
            or self.root_provisioner_id == self.operator_id
            or not _is_utc(self.requested_at)
            or not _is_utc(self.expires_at)
            or self.expires_at <= self.requested_at
        ):
            raise RealTrialRootError("root_provisioning_request_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class RealTrialRootIdentity(_Canonical):
    root_identity_id: str
    provisioning_request_digest: str
    root_class: TrialRootClass
    opaque_identity_digest: str
    resolver_policy_digest: str
    provisioned_by: str
    provisioned_at: datetime

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.root_identity_id)
            or not is_digest(self.provisioning_request_digest)
            or self.root_class is not TrialRootClass.CONTROLLED_TRIAL_ROOT
            or not is_digest(self.opaque_identity_digest)
            or not is_digest(self.resolver_policy_digest)
            or not is_identifier(self.provisioned_by)
            or not _is_utc(self.provisioned_at)
        ):
            raise RealTrialRootError("real_trial_root_identity_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class _RootVerificationResult(_Canonical):
    verification_id: str
    root_identity_digest: str
    provisioning_request_digest: str
    protocol_digest: str
    observed_evidence_digest: str
    executor_id: str
    evaluated_at: datetime
    result: RootProvisioningVerificationState

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.verification_id)
            or not all(
                is_digest(item)
                for item in (
                    self.root_identity_digest,
                    self.provisioning_request_digest,
                    self.protocol_digest,
                    self.observed_evidence_digest,
                )
            )
            or not is_identifier(self.executor_id)
            or not _is_utc(self.evaluated_at)
            or not isinstance(self.result, RootProvisioningVerificationState)
        ):
            raise RealTrialRootError("root_verification_result_invalid")
        self._seal(self._canonical_payload())

    def _canonical_payload(self) -> dict[str, object]:
        return {"verification_type": type(self).__name__, **_payload(self)}

    def canonical_json(self) -> str:
        return canonical_json(self._canonical_payload())


@dataclass(frozen=True, repr=False)
class RootConfinementVerificationResult(_RootVerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class LinkReparseVerificationResult(_RootVerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class PermissionVerificationResult(_RootVerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class WriteProhibitionVerificationResult(_RootVerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class NetworkIsolationVerificationResult(_RootVerificationResult):
    pass


@dataclass(frozen=True, repr=False)
class RootProvisioningAttestation(_Canonical):
    attestation_id: str
    provisioning_request_digest: str
    root_identity_digest: str
    root_confinement_result_digest: str
    link_reparse_result_digest: str
    permission_result_digest: str
    write_prohibition_result_digest: str
    network_isolation_result_digest: str
    generated_by: str
    generated_at: datetime
    expires_at: datetime
    result: RootProvisioningAttestationState

    def __post_init__(self) -> None:
        digest_values = tuple(
            item for key, item in vars(self).items() if key.endswith("_digest")
        )
        if (
            not is_identifier(self.attestation_id)
            or not all(is_digest(item) for item in digest_values)
            or not is_identifier(self.generated_by)
            or not _is_utc(self.generated_at)
            or not _is_utc(self.expires_at)
            or self.expires_at <= self.generated_at
            or not isinstance(self.result, RootProvisioningAttestationState)
        ):
            raise RealTrialRootError("root_provisioning_attestation_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class RealTrialTargetSelection(_Canonical):
    target_selection_id: str
    provisioning_request_digest: str
    root_identity_digest: str
    controlled_target_reference_digest: str
    selector_digest: str
    document_identity_digest: str
    data_class: RealDataClass
    document_class: RealDataDocumentClass
    maximum_document_count: int
    operator_id: str
    selected_at: datetime

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.target_selection_id)
            or not all(
                is_digest(item)
                for item in (
                    self.provisioning_request_digest,
                    self.root_identity_digest,
                    self.controlled_target_reference_digest,
                    self.selector_digest,
                    self.document_identity_digest,
                )
            )
            or self.data_class is not RealDataClass.INTERNAL_LOW
            or self.document_class
            is not RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE
            or self.maximum_document_count != 1
            or not is_identifier(self.operator_id)
            or not _is_utc(self.selected_at)
        ):
            raise RealTrialRootError("real_trial_target_selection_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


@dataclass(frozen=True, repr=False)
class RealTrialClosureRequirement(_Canonical):
    closure_requirement_id: str
    purpose_digest: str
    access_authorization_record_digest: str
    one_shot_receipt_required: bool
    usage_exhaustion_required: bool
    classification_evidence_required: bool
    masking_evidence_required: bool
    post_read_evidence_required: bool
    closure_record_required: bool
    downstream_processing_authorized: bool
    embedding_authorized: bool
    persistence_authorized: bool
    export_authorized: bool
    created_at: datetime

    def __post_init__(self) -> None:
        required = (
            self.one_shot_receipt_required,
            self.usage_exhaustion_required,
            self.classification_evidence_required,
            self.masking_evidence_required,
            self.post_read_evidence_required,
            self.closure_record_required,
        )
        prohibited = (
            self.downstream_processing_authorized,
            self.embedding_authorized,
            self.persistence_authorized,
            self.export_authorized,
        )
        if (
            not is_identifier(self.closure_requirement_id)
            or not is_digest(self.purpose_digest)
            or not is_digest(self.access_authorization_record_digest)
            or not all(item is True for item in required)
            or any(item is not False for item in prohibited)
            or not _is_utc(self.created_at)
        ):
            raise RealTrialRootError("real_trial_closure_requirement_invalid")
        self._seal(_payload(self))

    def canonical_json(self) -> str:
        return canonical_json(_payload(self))


def validate_real_trial_root_chain(
    *,
    purpose: RealTrialPurpose,
    provisioning_request: RealTrialRootProvisioningRequest,
    root_identity: RealTrialRootIdentity,
    root_descriptor: TrialRootDescriptor,
    resolver_policy: RealTargetResolverPolicy,
    target_reference: ControlledTargetReference,
    root_confinement: RootConfinementVerificationResult,
    link_reparse: LinkReparseVerificationResult,
    permission: PermissionVerificationResult,
    write_prohibition: WriteProhibitionVerificationResult,
    network_isolation: NetworkIsolationVerificationResult,
    attestation: RootProvisioningAttestation,
    target_selection: RealTrialTargetSelection,
    root_provisioner_id: str,
    root_verifier_id: str,
    operator_id: str,
    evaluation_time: datetime,
) -> tuple[str, ...]:
    reasons: list[str] = []
    results = (
        root_confinement,
        link_reparse,
        permission,
        write_prohibition,
        network_isolation,
    )
    objects = (
        purpose,
        provisioning_request,
        root_identity,
        root_descriptor,
        resolver_policy,
        target_reference,
        *results,
        attestation,
        target_selection,
    )
    if not all(canonical_object_valid(item) for item in objects):
        reasons.append("forged_root_provisioning_chain")
    exact = (
        provisioning_request.purpose_digest == purpose.canonical_digest,
        provisioning_request.root_descriptor_digest == root_descriptor.canonical_digest,
        provisioning_request.target_reference_digest
        == target_reference.canonical_digest,
        provisioning_request.root_provisioner_id == root_provisioner_id,
        provisioning_request.operator_id == operator_id,
        root_identity.provisioning_request_digest
        == provisioning_request.canonical_digest,
        root_identity.opaque_identity_digest == root_descriptor.root_identity_digest,
        root_identity.resolver_policy_digest == resolver_policy.canonical_digest,
        root_identity.provisioned_by == root_provisioner_id,
        root_descriptor.resolver_policy_digest == resolver_policy.canonical_digest,
        resolver_policy.allowed_root_digest == root_descriptor.root_identity_digest,
        target_reference.root_digest == root_descriptor.canonical_digest,
        attestation.provisioning_request_digest
        == provisioning_request.canonical_digest,
        attestation.root_identity_digest == root_identity.canonical_digest,
        attestation.root_confinement_result_digest
        == root_confinement.canonical_digest,
        attestation.link_reparse_result_digest == link_reparse.canonical_digest,
        attestation.permission_result_digest == permission.canonical_digest,
        attestation.write_prohibition_result_digest
        == write_prohibition.canonical_digest,
        attestation.network_isolation_result_digest
        == network_isolation.canonical_digest,
        attestation.generated_by == root_verifier_id,
        target_selection.provisioning_request_digest
        == provisioning_request.canonical_digest,
        target_selection.root_identity_digest == root_identity.canonical_digest,
        target_selection.controlled_target_reference_digest
        == target_reference.canonical_digest,
        target_selection.document_identity_digest
        == target_reference.expected_content_identity_digest,
        target_selection.operator_id == operator_id,
    )
    if not all(exact):
        reasons.append("root_provisioning_binding_mismatch")
    if any(
        result.root_identity_digest != root_identity.canonical_digest
        or result.provisioning_request_digest
        != provisioning_request.canonical_digest
        or result.executor_id != root_verifier_id
        or result.result is not RootProvisioningVerificationState.PASSED
        for result in results
    ):
        reasons.append("root_hard_gate_failed")
    policy_gates = (
        purpose.maximum_stage is RAGStage.CHUNKING,
        purpose.retention_class is RealDataAccessRetentionClass.NONE,
        resolver_policy.max_file_size_class is RealDataByteClass.SMALL_DOCUMENT,
        not resolver_policy.allow_symlink,
        not resolver_policy.allow_junction,
        not resolver_policy.allow_reparse_point,
        not resolver_policy.allow_parent_traversal,
        not resolver_policy.allow_absolute_user_input,
        resolver_policy.require_regular_file,
        resolver_policy.require_identity_stability,
        target_selection.maximum_document_count == 1,
        target_selection.data_class is RealDataClass.INTERNAL_LOW,
        target_selection.document_class
        is RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,
    )
    if not all(policy_gates):
        reasons.append("root_policy_invalid")
    if (
        attestation.result is not RootProvisioningAttestationState.APPROVED
        or root_provisioner_id == root_verifier_id
        or root_provisioner_id == operator_id
        or root_verifier_id == operator_id
    ):
        reasons.append("root_role_conflict")
    times = (
        purpose.created_at,
        provisioning_request.requested_at,
        provisioning_request.expires_at,
        root_identity.provisioned_at,
        *(item.evaluated_at for item in results),
        attestation.generated_at,
        attestation.expires_at,
        target_selection.selected_at,
        evaluation_time,
    )
    if (
        not all(_is_utc(item) for item in times)
        or not (
            purpose.created_at
            <= provisioning_request.requested_at
            < root_identity.provisioned_at
            <= min(item.evaluated_at for item in results)
            <= max(item.evaluated_at for item in results)
            <= attestation.generated_at
            <= target_selection.selected_at
            <= evaluation_time
            < attestation.expires_at
            <= provisioning_request.expires_at
        )
    ):
        reasons.append("root_temporal_invalid")
    return tuple(dict.fromkeys(reasons))


def fixed_real_trial_policy_summary() -> dict[str, str | int | bool]:
    """Safe fixed policy metadata; never contains a filesystem locator."""
    return {
        "data_class": RealDataClass.INTERNAL_LOW.value,
        "document_count": 1,
        "stage_ceiling": RAGStage.CHUNKING.value,
        "retention": RealDataAccessRetentionClass.NONE.value,
        "logging": RealDataAccessLoggingClass.NONE.value,
        "cache": RealDataAccessCacheClass.NONE.value,
        "persistence": RealDataAccessPersistenceClass.NONE.value,
        "export": RealDataAccessExportClass.PROHIBITED.value,
        "network": RealDataAccessNetworkClass.PROHIBITED.value,
        "closure_required": True,
    }


__all__ = [
    "LinkReparseVerificationResult",
    "NetworkIsolationVerificationResult",
    "PermissionVerificationResult",
    "RealTrialClosureRequirement",
    "RealTrialPurpose",
    "RealTrialPurposeClass",
    "RealTrialRootError",
    "RealTrialRootIdentity",
    "RealTrialRootProvisioningRequest",
    "RealTrialTargetSelection",
    "RootConfinementVerificationResult",
    "RootProvisioningAttestation",
    "RootProvisioningAttestationState",
    "RootProvisioningVerificationState",
    "WriteProhibitionVerificationResult",
    "fixed_real_trial_policy_summary",
    "validate_real_trial_root_chain",
]
