from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


CANONICAL_STORAGE_ADAPTER_DIGEST_ALGORITHM = "sha256"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CANONICAL_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")

__all__ = [
    "CANONICAL_STORAGE_ADAPTER_DIGEST_ALGORITHM", "AdapterClass",
    "AdapterDataClass", "AtomicityModel", "CredentialMode", "DurabilityModel",
    "FilesystemMode", "IdempotencyModel", "IsolationModel", "NetworkMode",
    "RecoveryModel", "StorageAdapterCapability", "StorageAdapterError",
    "StorageAdapterManifest", "StorageAdapterPolicy", "StorageAdapterSafeSummary",
    "TransactionModel",
]


class StorageAdapterError(ValueError):
    def __init__(self, category: str = "storage_adapter_contract_invalid") -> None:
        self.category = category
        super().__init__(category)


class AdapterClass(str, Enum):
    FILESYSTEM_CANDIDATE = "filesystem_candidate"
    RELATIONAL_DB_CANDIDATE = "relational_db_candidate"
    OBJECT_STORE_CANDIDATE = "object_store_candidate"


class TransactionModel(str, Enum):
    ATOMIC_COMPARE_AND_SWAP = "atomic_compare_and_swap"
    BEST_EFFORT = "best_effort"


class DurabilityModel(str, Enum):
    DURABLE_APPEND_ONLY = "durable_append_only"
    MUTABLE_OVERWRITE = "mutable_overwrite"


class AtomicityModel(str, Enum):
    CANDIDATE_STATE_SINGLE_SWAP = "candidate_state_single_swap"
    MULTI_STEP = "multi_step"


class RecoveryModel(str, Enum):
    VERIFIED_RECOVERY_PROBE = "verified_recovery_probe"
    NONE = "none"


class IdempotencyModel(str, Enum):
    SUCCESSFUL_ONLY_KEY_CONSUMPTION = "successful_only_key_consumption"
    NONE = "none"


class IsolationModel(str, Enum):
    CONTROLLED_ISOLATED = "controlled_isolated"
    SHARED = "shared"


class AdapterDataClass(str, Enum):
    SYNTHETIC_ONLY = "synthetic_only"
    CONTROLLED_FIXTURE_ONLY = "controlled_fixture_only"


class CredentialMode(str, Enum):
    NONE = "none"
    EXTERNAL_REQUIRED = "external_required"


class NetworkMode(str, Enum):
    DISABLED = "disabled"
    EXTERNAL_REQUIRED = "external_required"


class FilesystemMode(str, Enum):
    SIMULATED_ONLY = "simulated_only"
    ACTUAL_REQUESTED = "actual_requested"


@dataclass(frozen=True, repr=False)
class StorageAdapterSafeSummary:
    object_id: str
    source_digest: str
    state: str
    timestamp: str

    def __post_init__(self) -> None:
        if (not is_identifier(self.object_id) or not is_digest(self.source_digest)
                or not is_identifier(self.state)
                or not isinstance(self.timestamp, str)
                or not _CANONICAL_TIME.fullmatch(self.timestamp)):
            raise StorageAdapterError("storage_adapter_safe_summary_invalid")

    def __repr__(self) -> str:
        return "StorageAdapterSafeSummary(<safe>)"


@dataclass(frozen=True, repr=False)
class StorageAdapterCapability:
    supports_atomic_commit: bool
    supports_compare_and_swap: bool
    supports_generation_check: bool
    supports_predecessor_check: bool
    supports_content_digest_verify: bool
    supports_read_after_write_verify: bool
    supports_recovery_probe: bool
    supports_idempotency_key: bool
    supports_corruption_detection: bool
    supports_transaction_abort: bool
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not all(type(value) is bool for value in self.values):
            raise StorageAdapterError("storage_adapter_capability_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    @property
    def values(self) -> tuple[bool, ...]:
        return tuple(
            value
            for name, value in vars(self).items()
            if name.startswith("supports_")
        )

    @property
    def all_required(self) -> bool:
        return all(self.values)

    def canonical_json(self) -> str:
        return canonical_json(
            {
                name: value
                for name, value in vars(self).items()
                if name.startswith("supports_")
            }
        )

    def __repr__(self) -> str:
        return "StorageAdapterCapability(<safe>)"


@dataclass(frozen=True, repr=False)
class StorageAdapterManifest:
    adapter_id: str
    adapter_class: AdapterClass
    adapter_version: str
    interface_version: str
    capability_digest: str
    transaction_model: TransactionModel
    durability_model: DurabilityModel
    atomicity_model: AtomicityModel
    recovery_model: RecoveryModel
    idempotency_model: IdempotencyModel
    isolation_model: IsolationModel
    data_class: AdapterDataClass
    credential_mode: CredentialMode
    network_mode: NetworkMode
    filesystem_mode: FilesystemMode
    created_at: datetime
    canonical_digest: str = field(init=False)
    safe_summary: StorageAdapterSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        enum_values = (
            (self.adapter_class, AdapterClass),
            (self.transaction_model, TransactionModel),
            (self.durability_model, DurabilityModel),
            (self.atomicity_model, AtomicityModel),
            (self.recovery_model, RecoveryModel),
            (self.idempotency_model, IdempotencyModel),
            (self.isolation_model, IsolationModel),
            (self.data_class, AdapterDataClass),
            (self.credential_mode, CredentialMode),
            (self.network_mode, NetworkMode),
            (self.filesystem_mode, FilesystemMode),
        )
        if (
            not all(
                is_identifier(value)
                for value in (
                    self.adapter_id,
                    self.adapter_version,
                    self.interface_version,
                )
            )
            or not is_digest(self.capability_digest)
            or not all(isinstance(value, expected) for value, expected in enum_values)
            or not is_aware(self.created_at)
        ):
            raise StorageAdapterError("storage_adapter_manifest_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))
        object.__setattr__(self, "safe_summary", StorageAdapterSafeSummary(
            self.adapter_id, self.canonical_digest, "candidate",
            canonical_datetime(self.created_at)))

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "adapter_class": self.adapter_class.value,
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "atomicity_model": self.atomicity_model.value,
                "capability_digest": self.capability_digest,
                "created_at": canonical_datetime(self.created_at),
                "credential_mode": self.credential_mode.value,
                "data_class": self.data_class.value,
                "durability_model": self.durability_model.value,
                "filesystem_mode": self.filesystem_mode.value,
                "idempotency_model": self.idempotency_model.value,
                "interface_version": self.interface_version,
                "isolation_model": self.isolation_model.value,
                "network_mode": self.network_mode.value,
                "recovery_model": self.recovery_model.value,
                "transaction_model": self.transaction_model.value,
            }
        )

    def __repr__(self) -> str:
        return "StorageAdapterManifest(<safe>)"


@dataclass(frozen=True, repr=False)
class StorageAdapterPolicy:
    policy_id: str
    allowed_adapter_classes: tuple[AdapterClass, ...]
    allowed_transaction_models: tuple[TransactionModel, ...]
    allowed_durability_models: tuple[DurabilityModel, ...]
    allowed_network_modes: tuple[NetworkMode, ...]
    allowed_filesystem_modes: tuple[FilesystemMode, ...]
    allowed_credential_modes: tuple[CredentialMode, ...]
    required_capability_digest: str
    policy_version: str
    is_approved: bool
    effective_at: datetime
    expires_at: datetime
    canonical_digest: str = field(init=False)
    safe_summary: StorageAdapterSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        collections = (
            self.allowed_adapter_classes,
            self.allowed_transaction_models,
            self.allowed_durability_models,
            self.allowed_network_modes,
            self.allowed_filesystem_modes,
            self.allowed_credential_modes,
        )
        typed_collections = (
            (self.allowed_adapter_classes, AdapterClass),
            (self.allowed_transaction_models, TransactionModel),
            (self.allowed_durability_models, DurabilityModel),
            (self.allowed_network_modes, NetworkMode),
            (self.allowed_filesystem_modes, FilesystemMode),
            (self.allowed_credential_modes, CredentialMode),
        )
        if (
            not all(is_identifier(v) for v in (self.policy_id, self.policy_version))
            or not all(isinstance(value, tuple) and value for value in collections)
            or not all(all(isinstance(item, expected) for item in values)
                       for values, expected in typed_collections)
            or not is_digest(self.required_capability_digest)
            or type(self.is_approved) is not bool
            or not is_aware(self.effective_at)
            or not is_aware(self.expires_at)
            or self.expires_at <= self.effective_at
        ):
            raise StorageAdapterError("storage_adapter_policy_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))
        object.__setattr__(self, "safe_summary", StorageAdapterSafeSummary(
            self.policy_id, self.canonical_digest,
            "approved" if self.is_approved else "not_approved",
            canonical_datetime(self.effective_at)))

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "allowed_adapter_classes": sorted(v.value for v in self.allowed_adapter_classes),
                "allowed_credential_modes": sorted(v.value for v in self.allowed_credential_modes),
                "allowed_durability_models": sorted(v.value for v in self.allowed_durability_models),
                "allowed_filesystem_modes": sorted(v.value for v in self.allowed_filesystem_modes),
                "allowed_network_modes": sorted(v.value for v in self.allowed_network_modes),
                "allowed_transaction_models": sorted(v.value for v in self.allowed_transaction_models),
                "effective_at": canonical_datetime(self.effective_at),
                "expires_at": canonical_datetime(self.expires_at),
                "is_approved": self.is_approved,
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "required_capability_digest": self.required_capability_digest,
            }
        )

    def __repr__(self) -> str:
        return "StorageAdapterPolicy(<safe>)"


def canonical_object_valid(value: object) -> bool:
    method = getattr(value, "canonical_json", None)
    canonical_digest = getattr(value, "canonical_digest", None)
    return callable(method) and is_digest(canonical_digest) and digest(method()) == canonical_digest


def is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER.fullmatch(value))


def is_digest(value: object) -> bool:
    return isinstance(value, str) and bool(_DIGEST.fullmatch(value))


def is_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
