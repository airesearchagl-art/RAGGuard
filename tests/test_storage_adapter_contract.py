from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone
from enum import Enum

import pytest

from ragguard.storage_adapter import (
    AdapterClass, AdapterDataClass, AtomicityModel, CredentialMode,
    DurabilityModel, FilesystemMode, IdempotencyModel, IsolationModel,
    NetworkMode, RecoveryModel, StorageAdapterCapability, StorageAdapterError,
    StorageAdapterManifest, StorageAdapterPolicy, TransactionModel,
)
from ragguard.storage_adapter_attestation import (
    AdapterConformanceReason, AdapterConformanceState, AdapterEvidenceClass,
    StorageAdapterAttestationEvidence, evaluate_adapter_conformance,
)
from tests.test_real_persistence_contract import context as persistence_context


def digest(char: str) -> str:
    return "sha256:" + char * 64


def capability(**changes) -> StorageAdapterCapability:
    values = {name: True for name in (
        "supports_atomic_commit", "supports_compare_and_swap",
        "supports_generation_check", "supports_predecessor_check",
        "supports_content_digest_verify", "supports_read_after_write_verify",
        "supports_recovery_probe", "supports_idempotency_key",
        "supports_corruption_detection", "supports_transaction_abort",
    )}
    values.update(changes)
    return StorageAdapterCapability(**values)


def manifest(cap: StorageAdapterCapability | None = None, **changes) -> StorageAdapterManifest:
    cap = cap or capability()
    base = persistence_context()[-1] + timedelta(seconds=1)
    values = dict(
        adapter_id="adapter-v021", adapter_class=AdapterClass.FILESYSTEM_CANDIDATE,
        adapter_version="version-v021", interface_version="interface-v021",
        capability_digest=cap.canonical_digest,
        transaction_model=TransactionModel.ATOMIC_COMPARE_AND_SWAP,
        durability_model=DurabilityModel.DURABLE_APPEND_ONLY,
        atomicity_model=AtomicityModel.CANDIDATE_STATE_SINGLE_SWAP,
        recovery_model=RecoveryModel.VERIFIED_RECOVERY_PROBE,
        idempotency_model=IdempotencyModel.SUCCESSFUL_ONLY_KEY_CONSUMPTION,
        isolation_model=IsolationModel.CONTROLLED_ISOLATED,
        data_class=AdapterDataClass.CONTROLLED_FIXTURE_ONLY,
        credential_mode=CredentialMode.NONE, network_mode=NetworkMode.DISABLED,
        filesystem_mode=FilesystemMode.SIMULATED_ONLY, created_at=base,
    )
    values.update(changes)
    return StorageAdapterManifest(**values)


def policy(cap: StorageAdapterCapability | None = None, **changes) -> StorageAdapterPolicy:
    cap = cap or capability()
    base = persistence_context()[-1]
    values = dict(
        policy_id="adapter-policy-v021",
        allowed_adapter_classes=tuple(AdapterClass),
        allowed_transaction_models=(TransactionModel.ATOMIC_COMPARE_AND_SWAP,),
        allowed_durability_models=(DurabilityModel.DURABLE_APPEND_ONLY,),
        allowed_network_modes=(NetworkMode.DISABLED,),
        allowed_filesystem_modes=(FilesystemMode.SIMULATED_ONLY,),
        allowed_credential_modes=(CredentialMode.NONE,),
        required_capability_digest=cap.canonical_digest,
        policy_version="policy-version-v021", is_approved=True,
        effective_at=base, expires_at=base + timedelta(days=30),
    )
    values.update(changes)
    return StorageAdapterPolicy(**values)


def evidence(man: StorageAdapterManifest | None = None,
             cap: StorageAdapterCapability | None = None,
             **changes) -> StorageAdapterAttestationEvidence:
    cap = cap or capability()
    man = man or manifest(cap)
    values = dict(
        evidence_id="adapter-evidence-v021",
        adapter_manifest_digest=man.canonical_digest,
        capability_digest=cap.canonical_digest,
        conformance_suite_digest=digest("1"), atomicity_test_digest=digest("2"),
        recovery_test_digest=digest("3"), corruption_test_digest=digest("4"),
        idempotency_test_digest=digest("5"), failure_injection_digest=digest("6"),
        evidence_class=AdapterEvidenceClass.CONTROLLED_CONFORMANCE,
        generated_at=man.created_at + timedelta(seconds=1),
        generated_by="adapter-evidence-producer",
    )
    values.update(changes)
    return StorageAdapterAttestationEvidence(**values)


def conformance(**changes):
    cap = changes.pop("capability", capability())
    man = changes.pop("manifest", manifest(cap))
    pol = changes.pop("policy", policy(cap))
    ev = changes.pop("evidence", evidence(man, cap))
    at = changes.pop("evaluation_time", ev.generated_at + timedelta(seconds=1))
    return evaluate_adapter_conformance(man, cap, ev, pol, evaluation_time=at)


def test_manifest_capability_policy_are_immutable_and_deterministic():
    cap = capability()
    man = manifest(cap)
    pol = policy(cap)
    assert replace(cap).canonical_digest == cap.canonical_digest
    assert replace(man).canonical_digest == man.canonical_digest
    assert replace(pol).canonical_digest == pol.canonical_digest
    with pytest.raises(FrozenInstanceError):
        man.adapter_id = "other"  # type: ignore[misc]
    assert repr(man.safe_summary) == "StorageAdapterSafeSummary(<safe>)"


def test_manifest_is_metadata_only_and_has_no_location_or_secret_fields():
    names = set(StorageAdapterManifest.__dataclass_fields__)
    forbidden = {"path", "host", "ip", "port", "dsn", "bucket", "account",
                 "credential", "token", "url", "connection", "secret"}
    assert not names.intersection(forbidden)


@pytest.mark.parametrize("adapter_class", list(AdapterClass))
def test_supported_adapter_candidate_classes(adapter_class):
    assert manifest(adapter_class=adapter_class).adapter_class is adapter_class


def test_candidate_manifest_is_not_approval():
    man = manifest()
    assert "approved" not in man.canonical_json().lower()


def test_all_ten_capability_claims_are_digest_covered():
    cap = capability()
    assert len(cap.values) == 10 and cap.all_required
    for name in [n for n in vars(cap) if n.startswith("supports_")]:
        assert replace(cap, **{name: False}).canonical_digest != cap.canonical_digest


def test_valid_controlled_contract_is_eligible_for_review_only():
    result = conformance()
    assert result.state is AdapterConformanceState.ELIGIBLE_FOR_ADAPTER_REVIEW
    assert "approved" not in result.state.value
    assert "production_ready" not in result.state.value
    assert "enabled" not in result.state.value


@pytest.mark.parametrize("field", [
    "supports_atomic_commit", "supports_compare_and_swap",
    "supports_generation_check", "supports_predecessor_check",
    "supports_content_digest_verify", "supports_read_after_write_verify",
    "supports_recovery_probe", "supports_idempotency_key",
    "supports_corruption_detection", "supports_transaction_abort",
])
def test_each_missing_capability_needs_more_evidence(field):
    cap = capability(**{field: False})
    result = conformance(capability=cap, manifest=manifest(cap), policy=policy(cap))
    assert result.state is AdapterConformanceState.NEEDS_MORE_EVIDENCE
    assert AdapterConformanceReason.CAPABILITY_MISSING in result.reasons


@pytest.mark.parametrize("changes", [
    {"credential_mode": CredentialMode.EXTERNAL_REQUIRED},
    {"network_mode": NetworkMode.EXTERNAL_REQUIRED},
    {"filesystem_mode": FilesystemMode.ACTUAL_REQUESTED},
])
def test_unsafe_modes_fail_closed(changes):
    cap = capability(); man = manifest(cap, **changes)
    result = conformance(capability=cap, manifest=man, policy=policy(cap), evidence=evidence(man, cap))
    assert result.state is AdapterConformanceState.FAILED
    assert AdapterConformanceReason.UNSAFE_MODE in result.reasons


@pytest.mark.parametrize("field,value", [
    ("transaction_model", TransactionModel.BEST_EFFORT),
    ("durability_model", DurabilityModel.MUTABLE_OVERWRITE),
    ("atomicity_model", AtomicityModel.MULTI_STEP),
    ("recovery_model", RecoveryModel.NONE),
    ("idempotency_model", IdempotencyModel.NONE),
])
def test_incompatible_models_fail_closed(field, value):
    cap = capability(); man = manifest(cap, **{field: value})
    result = conformance(capability=cap, manifest=man, policy=policy(cap), evidence=evidence(man, cap))
    assert result.state is AdapterConformanceState.FAILED
    assert (AdapterConformanceReason.MODEL_INCOMPATIBLE in result.reasons
            or AdapterConformanceReason.POLICY_REJECTED in result.reasons)


def test_policy_must_be_approved_and_exact_bound():
    cap = capability(); man = manifest(cap); ev = evidence(man, cap)
    assert conformance(capability=cap, manifest=man, evidence=ev,
                       policy=policy(cap, is_approved=False)).state is AdapterConformanceState.FAILED
    other = capability(supports_atomic_commit=False)
    assert AdapterConformanceReason.DIGEST_MISMATCH in conformance(
        capability=cap, manifest=man, evidence=ev, policy=policy(other)).reasons


def test_future_stale_expired_and_naive_times_are_rejected():
    cap = capability(); man = manifest(cap); pol = policy(cap); ev = evidence(man, cap)
    assert AdapterConformanceReason.TEMPORAL_INVALID in evaluate_adapter_conformance(
        man, cap, ev, pol, evaluation_time=ev.generated_at - timedelta(microseconds=1)).reasons
    assert AdapterConformanceReason.STALE_EVIDENCE in evaluate_adapter_conformance(
        man, cap, ev, replace(pol, expires_at=ev.generated_at + timedelta(days=100)),
        evaluation_time=ev.generated_at + timedelta(days=91)).reasons
    assert AdapterConformanceReason.TEMPORAL_INVALID in evaluate_adapter_conformance(
        man, cap, ev, pol, evaluation_time=pol.expires_at).reasons
    with pytest.raises(StorageAdapterError):
        evaluate_adapter_conformance(man, cap, ev, pol, evaluation_time=ev.generated_at.replace(tzinfo=None))


def test_utc_normalization_preserves_microseconds():
    man = manifest()
    offset = timezone(timedelta(hours=9))
    assert replace(man, created_at=man.created_at.astimezone(offset)).canonical_digest == man.canonical_digest
    assert replace(man, created_at=man.created_at + timedelta(microseconds=1)).canonical_digest != man.canonical_digest


def test_conformance_has_no_side_effects():
    result = conformance()
    counters = [getattr(result, name) for name in result.__dataclass_fields__
                if name.endswith("_count")]
    assert counters and set(counters) == {0}


def test_wrong_enum_type_and_naive_time_raise_safe_error():
    class Other(str, Enum):
        VALUE = "filesystem_candidate"
    with pytest.raises(StorageAdapterError) as error:
        manifest(adapter_class=Other.VALUE)  # type: ignore[arg-type]
    assert error.value.category == "storage_adapter_manifest_invalid"
