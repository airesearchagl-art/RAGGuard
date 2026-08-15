from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path, PureWindowsPath

from ragguard.real_data_access import RealDataByteClass, RealDataDocumentClass
from ragguard.storage_adapter import (
    canonical_datetime,
    canonical_json,
    canonical_object_valid,
    digest,
    is_aware,
    is_digest,
    is_identifier,
)


_CONTROLLED_ROOT_SENTINEL = ".ragguard-v027-controlled-root"
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SMALL_DOCUMENT_MAX_BYTES = 64 * 1024


class RealTargetResolverError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class TrialRootClass(str, Enum):
    CONTROLLED_TRIAL_ROOT = "controlled_trial_root"


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
class TrialRootDescriptor(_Canonical):
    root_id: str
    root_class: TrialRootClass
    root_identity_digest: str
    resolver_policy_digest: str
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.root_id)
            or self.root_class is not TrialRootClass.CONTROLLED_TRIAL_ROOT
            or not is_digest(self.root_identity_digest)
            or not is_digest(self.resolver_policy_digest)
            or not _is_utc(self.created_at)
        ):
            raise RealTargetResolverError("trial_root_descriptor_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealTargetResolverPolicy(_Canonical):
    allowed_root_digest: str
    allowed_file_types: tuple[str, ...]
    max_file_size_class: RealDataByteClass
    allow_symlink: bool = False
    allow_junction: bool = False
    allow_reparse_point: bool = False
    allow_parent_traversal: bool = False
    allow_absolute_user_input: bool = False
    require_regular_file: bool = True
    require_identity_stability: bool = True

    def __post_init__(self) -> None:
        flags = (
            self.allow_symlink,
            self.allow_junction,
            self.allow_reparse_point,
            self.allow_parent_traversal,
            self.allow_absolute_user_input,
            self.require_regular_file,
            self.require_identity_stability,
        )
        file_types = self.allowed_file_types
        if (
            not is_digest(self.allowed_root_digest)
            or not isinstance(file_types, tuple)
            or not file_types
            or len(set(file_types)) != len(file_types)
            or not all(
                isinstance(item, str)
                and re.fullmatch(r"\.[a-z0-9]{1,10}", item) is not None
                for item in file_types
            )
            or self.max_file_size_class is not RealDataByteClass.SMALL_DOCUMENT
            or not all(type(item) is bool for item in flags)
            or any(flags[:5])
            or not all(flags[5:])
        ):
            raise RealTargetResolverError("real_target_resolver_policy_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class ControlledTargetReference(_Canonical):
    target_reference_id: str
    root_digest: str
    relative_target_digest: str
    expected_document_class: RealDataDocumentClass
    expected_content_identity_digest: str

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.target_reference_id)
            or not is_digest(self.root_digest)
            or not is_digest(self.relative_target_digest)
            or self.expected_document_class
            is not RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE
            or not is_digest(self.expected_content_identity_digest)
        ):
            raise RealTargetResolverError("controlled_target_reference_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class FileIdentitySnapshot(_Canonical):
    target_reference_digest: str
    resolved_identity_digest: str
    size_class: RealDataByteClass
    metadata_digest: str
    content_identity_digest: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if (
            not all(
                is_digest(item)
                for item in (
                    self.target_reference_digest,
                    self.resolved_identity_digest,
                    self.metadata_digest,
                    self.content_identity_digest,
                )
            )
            or self.size_class is not RealDataByteClass.SMALL_DOCUMENT
            or not _is_utc(self.observed_at)
        ):
            raise RealTargetResolverError("file_identity_snapshot_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


class _ControlledRootCapability:
    __slots__ = (
        "root_path",
        "descriptor_digest",
        "policy_digest",
        "target_bindings",
        "token",
    )

    def __init__(
        self,
        root_path: Path,
        descriptor_digest: str,
        policy_digest: str,
        target_bindings: dict[str, str],
    ) -> None:
        self.root_path = root_path
        self.descriptor_digest = descriptor_digest
        self.policy_digest = policy_digest
        self.target_bindings = dict(target_bindings)
        self.token = object()


class _ResolvedTargetHandle:
    __slots__ = (
        "path",
        "root_path",
        "target_reference_digest",
        "pre_identity",
        "capability_token",
    )

    def __init__(
        self,
        *,
        path: Path,
        root_path: Path,
        target_reference_digest: str,
        pre_identity: FileIdentitySnapshot,
        capability_token: object,
    ) -> None:
        self.path = path
        self.root_path = root_path
        self.target_reference_digest = target_reference_digest
        self.pre_identity = pre_identity
        self.capability_token = capability_token


class ResolvedTarget:
    """Opaque resolver result. No raw path is represented in its public metadata."""

    __slots__ = (
        "target_reference_digest",
        "root_descriptor_digest",
        "pre_identity",
        "canonical_digest",
    )

    def __init__(
        self,
        target_reference_digest: str,
        root_descriptor_digest: str,
        pre_identity: FileIdentitySnapshot,
    ) -> None:
        self.target_reference_digest = target_reference_digest
        self.root_descriptor_digest = root_descriptor_digest
        self.pre_identity = pre_identity
        self.canonical_digest = digest(self.canonical_json())

    def __repr__(self) -> str:
        return "ResolvedTarget(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "pre_identity_digest": self.pre_identity.canonical_digest,
                "root_descriptor_digest": self.root_descriptor_digest,
                "target_reference_digest": self.target_reference_digest,
            }
        )


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _metadata_digest(file_stat: os.stat_result) -> str:
    return digest(
        canonical_json(
            {
                "device": int(file_stat.st_dev),
                "inode": int(file_stat.st_ino),
                "mode": int(file_stat.st_mode),
                "modified_ns": int(file_stat.st_mtime_ns),
                "size": int(file_stat.st_size),
            }
        )
    )


def _resolved_identity_digest(
    target_reference_digest: str,
    metadata_digest: str,
    content_identity_digest: str,
) -> str:
    return digest(
        canonical_json(
            {
                "content_identity_digest": content_identity_digest,
                "metadata_digest": metadata_digest,
                "target_reference_digest": target_reference_digest,
            }
        )
    )


def _snapshot_from_stat(
    *,
    target_reference_digest: str,
    file_stat: os.stat_result,
    content_identity_digest: str,
    observed_at: datetime,
) -> FileIdentitySnapshot:
    metadata = _metadata_digest(file_stat)
    return FileIdentitySnapshot(
        target_reference_digest,
        _resolved_identity_digest(
            target_reference_digest, metadata, content_identity_digest
        ),
        RealDataByteClass.SMALL_DOCUMENT,
        metadata,
        content_identity_digest,
        observed_at,
    )


def _controlled_root_identity_digest(root_path: Path) -> str:
    """Test-support helper; returns metadata digest only and never exposes the path."""
    candidate = Path(root_path)
    root_stat = candidate.lstat()
    return digest(
        canonical_json(
            {
                "device": int(root_stat.st_dev),
                "inode": int(root_stat.st_ino),
                "mode": int(root_stat.st_mode),
            }
        )
    )


def _create_controlled_root_capability(
    *,
    root_path: Path,
    descriptor: TrialRootDescriptor,
    policy: RealTargetResolverPolicy,
    target_bindings: dict[str, str],
) -> _ControlledRootCapability:
    """Private synthetic-fixture factory; it is intentionally absent from __all__."""
    candidate = Path(root_path)
    try:
        root_lstat = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        sentinel = resolved / _CONTROLLED_ROOT_SENTINEL
        sentinel_stat = sentinel.lstat()
    except OSError as exc:
        raise RealTargetResolverError("controlled_root_unavailable") from exc
    anchor = Path(resolved.anchor) if resolved.anchor else None
    if (
        PureWindowsPath(str(candidate)).drive.startswith("\\\\")
        or anchor is None
        or resolved == anchor
        or not stat.S_ISDIR(root_lstat.st_mode)
        or candidate.is_symlink()
        or _is_reparse_point(root_lstat)
        or not stat.S_ISREG(sentinel_stat.st_mode)
        or sentinel.is_symlink()
        or _is_reparse_point(sentinel_stat)
        or sentinel_stat.st_size != 0
        or descriptor.root_identity_digest != _controlled_root_identity_digest(resolved)
        or descriptor.resolver_policy_digest != policy.canonical_digest
        or policy.allowed_root_digest != descriptor.root_identity_digest
    ):
        raise RealTargetResolverError("controlled_root_invalid")
    if not isinstance(target_bindings, dict) or not all(
        is_digest(key) and isinstance(value, str)
        for key, value in target_bindings.items()
    ):
        raise RealTargetResolverError("controlled_target_bindings_invalid")
    return _ControlledRootCapability(
        resolved,
        descriptor.canonical_digest,
        policy.canonical_digest,
        target_bindings,
    )


def _validate_relative_binding(value: str) -> tuple[str, ...]:
    windows = PureWindowsPath(value)
    normalized = value.replace("\\", "/")
    parts = tuple(normalized.split("/"))
    if (
        not value
        or "\x00" in value
        or any(item in value for item in ("*", "?", "[", "]"))
        or ":" in value
        or windows.is_absolute()
        or bool(windows.drive)
        or value.startswith(("/", "\\"))
        or any(part in ("", ".", "..") for part in parts)
        or not all(_SAFE_COMPONENT.fullmatch(part) for part in parts)
    ):
        raise RealTargetResolverError("relative_target_invalid")
    return parts


class RealTargetResolver:
    """Capability-bound resolver for one controlled synthetic root only."""

    __slots__ = ("descriptor", "policy", "_capability", "_issued_handles")

    def __init__(
        self,
        descriptor: TrialRootDescriptor,
        policy: RealTargetResolverPolicy,
        capability: _ControlledRootCapability,
    ) -> None:
        if (
            descriptor.canonical_digest != capability.descriptor_digest
            or policy.canonical_digest != capability.policy_digest
            or descriptor.resolver_policy_digest != policy.canonical_digest
            or policy.allowed_root_digest != descriptor.root_identity_digest
        ):
            raise RealTargetResolverError("resolver_binding_invalid")
        self.descriptor = descriptor
        self.policy = policy
        self._capability = capability
        self._issued_handles: dict[str, _ResolvedTargetHandle] = {}

    def resolve(
        self,
        reference: ControlledTargetReference,
        *,
        observed_at: datetime,
    ) -> ResolvedTarget:
        if (
            not _is_utc(observed_at)
            or not canonical_object_valid(reference)
            or reference.root_digest != self.descriptor.canonical_digest
            or reference.relative_target_digest
            not in self._capability.target_bindings
        ):
            raise RealTargetResolverError("target_reference_binding_invalid")
        binding = self._capability.target_bindings[reference.relative_target_digest]
        parts = _validate_relative_binding(binding)
        root = self._capability.root_path
        candidate = root.joinpath(*parts)
        try:
            current = root
            for part in parts:
                current = current / part
                current_stat = current.lstat()
                if current.is_symlink() or _is_reparse_point(current_stat):
                    raise RealTargetResolverError("link_or_reparse_target_rejected")
            target_stat = candidate.lstat()
            resolved = candidate.resolve(strict=True)
        except RealTargetResolverError:
            raise
        except OSError as exc:
            raise RealTargetResolverError("target_unavailable") from exc
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise RealTargetResolverError("root_escape_rejected") from exc
        if not stat.S_ISREG(target_stat.st_mode):
            raise RealTargetResolverError("regular_file_required")
        if resolved.suffix.lower() not in self.policy.allowed_file_types:
            raise RealTargetResolverError("file_type_rejected")
        if target_stat.st_size > _SMALL_DOCUMENT_MAX_BYTES:
            raise RealTargetResolverError("file_size_rejected")
        pre_identity = _snapshot_from_stat(
            target_reference_digest=reference.canonical_digest,
            file_stat=target_stat,
            content_identity_digest=reference.expected_content_identity_digest,
            observed_at=observed_at,
        )
        handle = _ResolvedTargetHandle(
            path=resolved,
            root_path=root,
            target_reference_digest=reference.canonical_digest,
            pre_identity=pre_identity,
            capability_token=self._capability.token,
        )
        resolved_target = ResolvedTarget(
            reference.canonical_digest,
            self.descriptor.canonical_digest,
            pre_identity,
        )
        self._issued_handles[resolved_target.canonical_digest] = handle
        return resolved_target

    def _handle_for(self, resolved: ResolvedTarget) -> _ResolvedTargetHandle:
        if (
            not canonical_object_valid(resolved)
            or resolved.canonical_digest not in self._issued_handles
        ):
            raise RealTargetResolverError("resolved_target_invalid")
        handle = self._issued_handles[resolved.canonical_digest]
        self._validate_handle(handle)
        return handle

    def _validate_handle(self, handle: _ResolvedTargetHandle) -> None:
        if (
            not isinstance(handle, _ResolvedTargetHandle)
            or handle.capability_token is not self._capability.token
            or handle.root_path != self._capability.root_path
        ):
            raise RealTargetResolverError("resolved_handle_invalid")


__all__ = [
    "ControlledTargetReference",
    "FileIdentitySnapshot",
    "RealTargetResolver",
    "RealTargetResolverError",
    "RealTargetResolverPolicy",
    "ResolvedTarget",
    "TrialRootClass",
    "TrialRootDescriptor",
]
