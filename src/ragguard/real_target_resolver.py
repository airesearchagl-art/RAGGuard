from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path, PureWindowsPath

if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes

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


if os.name == "nt":
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _FILE_SHARE_DELETE = 0x00000004
    _FILE_OPEN = 0x00000001
    _FILE_DIRECTORY_FILE = 0x00000001
    _FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
    _FILE_OPEN_REPARSE_POINT = 0x00200000
    _FILE_LIST_DIRECTORY = 0x00000001
    _FILE_READ_DATA = 0x00000001
    _FILE_READ_ATTRIBUTES = 0x00000080
    _SYNCHRONIZE = 0x00100000
    _OBJ_CASE_INSENSITIVE = 0x00000040
    _OBJ_DONT_REPARSE = 0x00001000
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _OPEN_EXISTING = 3
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _UnicodeString(ctypes.Structure):
        _fields_ = (
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", wintypes.LPWSTR),
        )

    class _ObjectAttributes(ctypes.Structure):
        _fields_ = (
            ("Length", wintypes.ULONG),
            ("RootDirectory", wintypes.HANDLE),
            ("ObjectName", ctypes.POINTER(_UnicodeString)),
            ("Attributes", wintypes.ULONG),
            ("SecurityDescriptor", wintypes.LPVOID),
            ("SecurityQualityOfService", wintypes.LPVOID),
        )

    class _IoStatusBlock(ctypes.Structure):
        _fields_ = (
            ("Status", ctypes.c_void_p),
            ("Information", ctypes.c_size_t),
        )

    _nt_create_file = ctypes.WinDLL("ntdll", use_last_error=True).NtCreateFile
    _nt_create_file.argtypes = (
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.ULONG,
        ctypes.POINTER(_ObjectAttributes),
        ctypes.POINTER(_IoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
    )
    _nt_create_file.restype = ctypes.c_long

    _create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    _create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    _create_file.restype = wintypes.HANDLE
    _close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    _close_handle.argtypes = (wintypes.HANDLE,)
    _close_handle.restype = wintypes.BOOL


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
        "root_directory_fd",
        "root_metadata_digest",
        "descriptor_digest",
        "policy_digest",
        "target_bindings",
        "token",
        "closed",
    )

    def __init__(
        self,
        root_path: Path,
        root_directory_fd: int,
        root_metadata_digest: str,
        descriptor_digest: str,
        policy_digest: str,
        target_bindings: dict[str, str],
    ) -> None:
        self.root_path = root_path
        self.root_directory_fd = root_directory_fd
        self.root_metadata_digest = root_metadata_digest
        self.descriptor_digest = descriptor_digest
        self.policy_digest = policy_digest
        self.target_bindings = dict(target_bindings)
        self.token = object()
        self.closed = False

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            _close_fd(self.root_directory_fd)
            self.root_directory_fd = -1

    def __del__(self) -> None:
        self.close()


class _ResolvedTargetHandle:
    __slots__ = (
        "target_reference_digest",
        "pre_identity",
        "capability_token",
        "relative_components",
        "component_metadata_digests",
        "pinned_file_fd",
    )

    def __init__(
        self,
        *,
        target_reference_digest: str,
        pre_identity: FileIdentitySnapshot,
        capability_token: object,
        relative_components: tuple[str, ...],
        component_metadata_digests: tuple[str, ...],
        pinned_file_fd: int,
    ) -> None:
        self.target_reference_digest = target_reference_digest
        self.pre_identity = pre_identity
        self.capability_token = capability_token
        self.relative_components = relative_components
        self.component_metadata_digests = component_metadata_digests
        self.pinned_file_fd = pinned_file_fd


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


def _close_fd(file_descriptor: int) -> None:
    if isinstance(file_descriptor, int) and file_descriptor >= 0:
        try:
            os.close(file_descriptor)
        except OSError:
            pass


def _open_root_directory_fd(root_path: Path) -> int:
    if os.name == "nt":
        native_handle = _create_file(
            str(root_path),
            _FILE_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS | _FILE_OPEN_REPARSE_POINT,
            None,
        )
        if native_handle == _INVALID_HANDLE_VALUE:
            raise OSError(ctypes.get_last_error(), "controlled_root_open_failed")
        try:
            return msvcrt.open_osfhandle(
                int(native_handle), os.O_RDONLY | getattr(os, "O_BINARY", 0)
            )
        except OSError:
            _close_handle(native_handle)
            raise
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    return os.open(root_path, flags)


def _open_relative_component_fd(
    parent_fd: int,
    component: str,
    *,
    directory: bool,
) -> int:
    if os.name == "nt":
        name_buffer = ctypes.create_unicode_buffer(component)
        unicode_name = _UnicodeString(
            len(component.encode("utf-16-le")),
            len(component.encode("utf-16-le")) + 2,
            ctypes.cast(name_buffer, wintypes.LPWSTR),
        )
        attributes = _ObjectAttributes(
            ctypes.sizeof(_ObjectAttributes),
            wintypes.HANDLE(msvcrt.get_osfhandle(parent_fd)),
            ctypes.pointer(unicode_name),
            _OBJ_CASE_INSENSITIVE | _OBJ_DONT_REPARSE,
            None,
            None,
        )
        io_status = _IoStatusBlock()
        native_handle = wintypes.HANDLE()
        desired_access = _FILE_READ_ATTRIBUTES | _SYNCHRONIZE
        desired_access |= _FILE_LIST_DIRECTORY if directory else _FILE_READ_DATA
        create_options = _FILE_SYNCHRONOUS_IO_NONALERT | _FILE_OPEN_REPARSE_POINT
        if directory:
            create_options |= _FILE_DIRECTORY_FILE
        status_code = _nt_create_file(
            ctypes.byref(native_handle),
            desired_access,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            0,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
            _FILE_OPEN,
            create_options,
            None,
            0,
        )
        if status_code < 0 or not native_handle.value:
            raise OSError(
                int(status_code) & 0xFFFFFFFF,
                "relative_component_open_failed",
            )
        try:
            return msvcrt.open_osfhandle(
                int(native_handle.value),
                os.O_RDONLY | getattr(os, "O_BINARY", 0),
            )
        except OSError:
            _close_handle(native_handle)
            raise
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    return os.open(component, flags, dir_fd=parent_fd)


def _open_component_chain(
    capability: _ControlledRootCapability,
    parts: tuple[str, ...],
    *,
    expected_metadata_digests: tuple[str, ...] | None = None,
) -> tuple[int, tuple[str, ...]]:
    if capability.closed or capability.root_directory_fd < 0 or not parts:
        raise RealTargetResolverError("root_directory_capability_invalid")
    if expected_metadata_digests is not None and len(
        expected_metadata_digests
    ) != len(parts):
        raise RealTargetResolverError("component_identity_contract_invalid")
    try:
        current_fd = os.dup(capability.root_directory_fd)
    except OSError as exc:
        raise RealTargetResolverError("root_directory_capability_invalid") from exc
    metadata: list[str] = []
    try:
        root_stat = os.fstat(current_fd)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or _is_reparse_point(root_stat)
            or _root_identity_digest_from_stat(root_stat)
            != capability.root_metadata_digest
        ):
            raise RealTargetResolverError("root_directory_capability_changed")
        for index, component in enumerate(parts):
            directory = index < len(parts) - 1
            next_fd = _open_relative_component_fd(
                current_fd, component, directory=directory
            )
            next_stat = os.fstat(next_fd)
            if _is_reparse_point(next_stat):
                _close_fd(next_fd)
                raise RealTargetResolverError("link_or_reparse_target_rejected")
            if directory and not stat.S_ISDIR(next_stat.st_mode):
                _close_fd(next_fd)
                raise RealTargetResolverError("directory_component_required")
            if not directory and not stat.S_ISREG(next_stat.st_mode):
                _close_fd(next_fd)
                raise RealTargetResolverError("regular_file_required")
            component_metadata = _metadata_digest(next_stat)
            if (
                expected_metadata_digests is not None
                and component_metadata != expected_metadata_digests[index]
            ):
                _close_fd(next_fd)
                raise RealTargetResolverError("target_binding_changed_before_read")
            metadata.append(component_metadata)
            _close_fd(current_fd)
            current_fd = next_fd
        return current_fd, tuple(metadata)
    except (OSError, RealTargetResolverError) as exc:
        _close_fd(current_fd)
        if isinstance(exc, RealTargetResolverError):
            raise
        raise RealTargetResolverError("target_component_open_failed") from exc


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
    return _root_identity_digest_from_stat(root_stat)


def _root_identity_digest_from_stat(root_stat: os.stat_result) -> str:
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
    root_fd = -1
    sentinel_fd = -1
    try:
        root_lstat = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        root_fd = _open_root_directory_fd(resolved)
        opened_root_stat = os.fstat(root_fd)
        sentinel_fd = _open_relative_component_fd(
            root_fd, _CONTROLLED_ROOT_SENTINEL, directory=False
        )
        sentinel_stat = os.fstat(sentinel_fd)
    except OSError as exc:
        _close_fd(sentinel_fd)
        _close_fd(root_fd)
        raise RealTargetResolverError("controlled_root_unavailable") from exc
    finally:
        _close_fd(sentinel_fd)
    anchor = Path(resolved.anchor) if resolved.anchor else None
    if (
        PureWindowsPath(str(candidate)).drive.startswith("\\\\")
        or anchor is None
        or resolved == anchor
        or not stat.S_ISDIR(root_lstat.st_mode)
        or not stat.S_ISDIR(opened_root_stat.st_mode)
        or candidate.is_symlink()
        or _is_reparse_point(root_lstat)
        or _is_reparse_point(opened_root_stat)
        or not stat.S_ISREG(sentinel_stat.st_mode)
        or _is_reparse_point(sentinel_stat)
        or sentinel_stat.st_size != 0
        or descriptor.root_identity_digest
        != _root_identity_digest_from_stat(opened_root_stat)
        or descriptor.resolver_policy_digest != policy.canonical_digest
        or policy.allowed_root_digest != descriptor.root_identity_digest
    ):
        _close_fd(root_fd)
        raise RealTargetResolverError("controlled_root_invalid")
    if not isinstance(target_bindings, dict) or not all(
        is_digest(key) and isinstance(value, str)
        for key, value in target_bindings.items()
    ):
        _close_fd(root_fd)
        raise RealTargetResolverError("controlled_target_bindings_invalid")
    return _ControlledRootCapability(
        resolved,
        root_fd,
        _root_identity_digest_from_stat(opened_root_stat),
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
        pinned_file_fd = -1
        try:
            pinned_file_fd, component_metadata = _open_component_chain(
                self._capability, parts
            )
            target_stat = os.fstat(pinned_file_fd)
        except RealTargetResolverError:
            raise
        except OSError as exc:
            _close_fd(pinned_file_fd)
            raise RealTargetResolverError("target_unavailable") from exc
        if not stat.S_ISREG(target_stat.st_mode):
            _close_fd(pinned_file_fd)
            raise RealTargetResolverError("regular_file_required")
        if Path(parts[-1]).suffix.lower() not in self.policy.allowed_file_types:
            _close_fd(pinned_file_fd)
            raise RealTargetResolverError("file_type_rejected")
        if target_stat.st_size > _SMALL_DOCUMENT_MAX_BYTES:
            _close_fd(pinned_file_fd)
            raise RealTargetResolverError("file_size_rejected")
        pre_identity = _snapshot_from_stat(
            target_reference_digest=reference.canonical_digest,
            file_stat=target_stat,
            content_identity_digest=reference.expected_content_identity_digest,
            observed_at=observed_at,
        )
        handle = _ResolvedTargetHandle(
            target_reference_digest=reference.canonical_digest,
            pre_identity=pre_identity,
            capability_token=self._capability.token,
            relative_components=parts,
            component_metadata_digests=component_metadata,
            pinned_file_fd=pinned_file_fd,
        )
        resolved_target = ResolvedTarget(
            reference.canonical_digest,
            self.descriptor.canonical_digest,
            pre_identity,
        )
        previous = self._issued_handles.get(resolved_target.canonical_digest)
        if previous is not None:
            _close_fd(previous.pinned_file_fd)
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
            or self._capability.closed
            or not handle.relative_components
            or handle.pinned_file_fd < 0
        ):
            raise RealTargetResolverError("resolved_handle_invalid")
        try:
            pinned_stat = os.fstat(handle.pinned_file_fd)
        except OSError as exc:
            raise RealTargetResolverError("resolved_handle_invalid") from exc
        if (
            not stat.S_ISREG(pinned_stat.st_mode)
            or _is_reparse_point(pinned_stat)
            or _metadata_digest(pinned_stat) != handle.pre_identity.metadata_digest
        ):
            raise RealTargetResolverError("resolved_handle_identity_invalid")

    def _acquire_read_descriptor(self, resolved: ResolvedTarget) -> int:
        handle = self._handle_for(resolved)
        candidate_fd = -1
        try:
            candidate_fd, component_metadata = _open_component_chain(
                self._capability,
                handle.relative_components,
                expected_metadata_digests=handle.component_metadata_digests,
            )
            candidate_stat = os.fstat(candidate_fd)
            pinned_stat = os.fstat(handle.pinned_file_fd)
            if (
                component_metadata != handle.component_metadata_digests
                or _metadata_digest(candidate_stat)
                != handle.pre_identity.metadata_digest
                or _metadata_digest(pinned_stat)
                != handle.pre_identity.metadata_digest
                or not stat.S_ISREG(candidate_stat.st_mode)
                or _is_reparse_point(candidate_stat)
            ):
                raise RealTargetResolverError("target_binding_changed_before_read")
            return candidate_fd
        except (OSError, RealTargetResolverError):
            _close_fd(candidate_fd)
            raise

    def _post_read_binding_valid(
        self, resolved: ResolvedTarget, opened_file_fd: int
    ) -> bool:
        try:
            handle = self._handle_for(resolved)
            opened_stat = os.fstat(opened_file_fd)
            rebound_fd, component_metadata = _open_component_chain(
                self._capability,
                handle.relative_components,
                expected_metadata_digests=handle.component_metadata_digests,
            )
            try:
                rebound_stat = os.fstat(rebound_fd)
                return (
                    component_metadata == handle.component_metadata_digests
                    and _metadata_digest(opened_stat)
                    == handle.pre_identity.metadata_digest
                    and _metadata_digest(rebound_stat)
                    == handle.pre_identity.metadata_digest
                )
            finally:
                _close_fd(rebound_fd)
        except (OSError, RealTargetResolverError):
            return False

    def _release_resolved(self, resolved: ResolvedTarget) -> None:
        handle = self._issued_handles.pop(resolved.canonical_digest, None)
        if handle is not None:
            _close_fd(handle.pinned_file_fd)
            handle.pinned_file_fd = -1

    def __del__(self) -> None:
        handles = getattr(self, "_issued_handles", {})
        for handle in handles.values():
            _close_fd(handle.pinned_file_fd)
            handle.pinned_file_fd = -1
        handles.clear()


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
