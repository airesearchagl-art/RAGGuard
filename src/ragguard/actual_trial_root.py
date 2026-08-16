from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path, PureWindowsPath

from ragguard.real_data_access import RealDataByteClass, RealDataDocumentClass
from ragguard.real_target_resolver import (
    ControlledTargetReference,
    RealTargetResolverError,
    RealTargetResolverPolicy,
    TrialRootClass,
    TrialRootDescriptor,
    _close_fd,
    _is_reparse_point,
    _metadata_digest,
    _open_component_chain,
    _open_root_directory_fd,
    _root_identity_digest_from_stat,
    _validate_relative_binding,
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


_ACTUAL_ROOT_CAPABILITY_MARKER = object()
_SMALL_DOCUMENT_MAX_BYTES = 64 * 1024


class ActualTrialRootError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class ActualTrialRootUse(str, Enum):
    CONTROLLED_FIXTURE = "controlled_fixture"
    HUMAN_SELECTED_ACTUAL = "human_selected_actual"


def _is_utc(value: object) -> bool:
    return is_aware(value) and value.utcoffset() == timedelta(0)


@dataclass(frozen=True, repr=False)
class HumanSelectedOpaqueTarget:
    target_id: str
    root_descriptor_digest: str
    target_reference_digest: str
    relative_target_digest: str
    target_identity_digest: str
    expected_document_class: RealDataDocumentClass
    selected_at: datetime
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.target_id)
            or not all(
                is_digest(item)
                for item in (
                    self.root_descriptor_digest,
                    self.target_reference_digest,
                    self.relative_target_digest,
                    self.target_identity_digest,
                )
            )
            or self.expected_document_class
            is not RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE
            or not _is_utc(self.selected_at)
        ):
            raise ActualTrialRootError("human_selected_target_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "HumanSelectedOpaqueTarget(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "expected_document_class": self.expected_document_class.value,
                "relative_target_digest": self.relative_target_digest,
                "root_descriptor_digest": self.root_descriptor_digest,
                "selected_at": canonical_datetime(self.selected_at),
                "target_id": self.target_id,
                "target_identity_digest": self.target_identity_digest,
                "target_reference_digest": self.target_reference_digest,
            }
        )


class ActualTrialRootCapability:
    """Opaque, handle-backed authority for exactly one Human-selected target."""

    __slots__ = (
        "root_directory_fd",
        "root_metadata_digest",
        "root_descriptor_digest",
        "resolver_policy_digest",
        "target_reference_digest",
        "target_identity_digest",
        "root_use",
        "component_chain_digest",
        "canonical_digest",
        "closed",
        "_relative_components",
        "_component_metadata_digests",
        "_allowed_file_types",
        "_token",
    )

    def __init__(
        self,
        *,
        root_directory_fd: int,
        root_metadata_digest: str,
        root_descriptor_digest: str,
        resolver_policy_digest: str,
        target_reference_digest: str,
        target_identity_digest: str,
        root_use: ActualTrialRootUse,
        relative_components: tuple[str, ...],
        component_metadata_digests: tuple[str, ...],
        allowed_file_types: tuple[str, ...],
        _marker: object | None = None,
    ) -> None:
        if (
            _marker is not _ACTUAL_ROOT_CAPABILITY_MARKER
            or not isinstance(root_directory_fd, int)
            or root_directory_fd < 0
            or not all(
                is_digest(item)
                for item in (
                    root_metadata_digest,
                    root_descriptor_digest,
                    resolver_policy_digest,
                    target_reference_digest,
                    target_identity_digest,
                )
            )
            or not isinstance(root_use, ActualTrialRootUse)
            or not relative_components
            or len(relative_components) != len(component_metadata_digests)
            or not all(is_digest(item) for item in component_metadata_digests)
        ):
            raise ActualTrialRootError("actual_root_capability_invalid")
        self.root_directory_fd = root_directory_fd
        self.root_metadata_digest = root_metadata_digest
        self.root_descriptor_digest = root_descriptor_digest
        self.resolver_policy_digest = resolver_policy_digest
        self.target_reference_digest = target_reference_digest
        self.target_identity_digest = target_identity_digest
        self.root_use = root_use
        self._relative_components = relative_components
        self._component_metadata_digests = component_metadata_digests
        self._allowed_file_types = allowed_file_types
        self._token = object()
        self.closed = False
        self.component_chain_digest = digest(canonical_json(list(component_metadata_digests)))
        self.canonical_digest = digest(self.canonical_json())

    def __repr__(self) -> str:
        return "ActualTrialRootCapability(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "component_chain_digest": self.component_chain_digest,
                "resolver_policy_digest": self.resolver_policy_digest,
                "root_descriptor_digest": self.root_descriptor_digest,
                "root_metadata_digest": self.root_metadata_digest,
                "root_use": self.root_use.value,
                "target_identity_digest": self.target_identity_digest,
                "target_reference_digest": self.target_reference_digest,
            }
        )

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            _close_fd(self.root_directory_fd)
            self.root_directory_fd = -1

    def _open_selected_target(
        self, target: HumanSelectedOpaqueTarget
    ) -> tuple[int, os.stat_result]:
        if (
            self.closed
            or not canonical_object_valid(target)
            or target.root_descriptor_digest != self.root_descriptor_digest
            or target.target_reference_digest != self.target_reference_digest
            or target.target_identity_digest != self.target_identity_digest
            or target.relative_target_digest
            != digest(canonical_json(list(self._relative_components)))
        ):
            raise ActualTrialRootError("actual_target_binding_invalid")
        descriptor = -1
        try:
            descriptor, component_metadata = _open_component_chain(
                self,
                self._relative_components,
                expected_metadata_digests=self._component_metadata_digests,
            )
            opened_stat = os.fstat(descriptor)
            if (
                component_metadata != self._component_metadata_digests
                or not stat.S_ISREG(opened_stat.st_mode)
                or _is_reparse_point(opened_stat)
                or Path(self._relative_components[-1]).suffix.lower()
                not in self._allowed_file_types
                or opened_stat.st_size > _SMALL_DOCUMENT_MAX_BYTES
            ):
                raise ActualTrialRootError("actual_target_policy_rejected")
            return descriptor, opened_stat
        except (OSError, RealTargetResolverError):
            _close_fd(descriptor)
            raise ActualTrialRootError("actual_target_open_rejected") from None
        except ActualTrialRootError:
            _close_fd(descriptor)
            raise

    def __del__(self) -> None:
        self.close()


@dataclass(frozen=True, repr=False)
class ActualRootProvisioning:
    capability: ActualTrialRootCapability
    root_descriptor: TrialRootDescriptor
    resolver_policy: RealTargetResolverPolicy
    target_reference: ControlledTargetReference
    target: HumanSelectedOpaqueTarget

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capability, ActualTrialRootCapability)
            or not all(
                canonical_object_valid(item)
                for item in (
                    self.root_descriptor,
                    self.resolver_policy,
                    self.target_reference,
                    self.target,
                )
            )
            or self.capability.root_descriptor_digest
            != self.root_descriptor.canonical_digest
            or self.capability.resolver_policy_digest
            != self.resolver_policy.canonical_digest
            or self.capability.target_reference_digest
            != self.target_reference.canonical_digest
            or self.capability.target_identity_digest
            != self.target.target_identity_digest
        ):
            raise ActualTrialRootError("actual_root_provisioning_invalid")

    def __repr__(self) -> str:
        return "ActualRootProvisioning(<safe>)"


class _RootHandleView:
    __slots__ = ("root_directory_fd", "root_metadata_digest", "closed")

    def __init__(self, root_directory_fd: int, root_metadata_digest: str) -> None:
        self.root_directory_fd = root_directory_fd
        self.root_metadata_digest = root_metadata_digest
        self.closed = False


def _provision_selected_root(
    *,
    root_path: str | os.PathLike[str],
    relative_target: str,
    root_id: str,
    target_reference_id: str,
    target_id: str,
    selected_at: datetime,
    root_use: ActualTrialRootUse,
    allowed_file_types: tuple[str, ...] = (".md", ".txt"),
) -> ActualRootProvisioning:
    """Provision exactly one supplied root/target pair; never scans or discovers."""
    if (
        not isinstance(root_path, (str, os.PathLike))
        or not isinstance(relative_target, str)
        or not all(is_identifier(item) for item in (root_id, target_reference_id, target_id))
        or not _is_utc(selected_at)
        or not isinstance(root_use, ActualTrialRootUse)
    ):
        raise ActualTrialRootError("actual_root_input_invalid")
    parts = _validate_relative_binding(relative_target)
    candidate = Path(root_path)
    root_fd = -1
    verification_fd = -1
    try:
        root_lstat = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        anchor = Path(resolved.anchor) if resolved.anchor else None
        if (
            PureWindowsPath(str(candidate)).drive.startswith("\\\\")
            or anchor is None
            or resolved == anchor
            or candidate.is_symlink()
            or not stat.S_ISDIR(root_lstat.st_mode)
            or _is_reparse_point(root_lstat)
        ):
            raise ActualTrialRootError("actual_root_scope_rejected")
        root_fd = _open_root_directory_fd(resolved)
        root_stat = os.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode) or _is_reparse_point(root_stat):
            raise ActualTrialRootError("actual_root_handle_rejected")
        root_identity = _root_identity_digest_from_stat(root_stat)
        resolver_policy = RealTargetResolverPolicy(
            root_identity,
            allowed_file_types,
            RealDataByteClass.SMALL_DOCUMENT,
        )
        root_descriptor = TrialRootDescriptor(
            root_id,
            TrialRootClass.CONTROLLED_TRIAL_ROOT,
            root_identity,
            resolver_policy.canonical_digest,
            selected_at,
        )
        view = _RootHandleView(root_fd, root_identity)
        verification_fd, component_metadata = _open_component_chain(view, parts)
        target_stat = os.fstat(verification_fd)
        if (
            not stat.S_ISREG(target_stat.st_mode)
            or _is_reparse_point(target_stat)
            or Path(parts[-1]).suffix.lower() not in allowed_file_types
            or target_stat.st_size > _SMALL_DOCUMENT_MAX_BYTES
        ):
            raise ActualTrialRootError("actual_target_policy_rejected")
        relative_digest = digest(canonical_json(list(parts)))
        target_identity = digest(
            canonical_json(
                {
                    "component_metadata_digest": digest(
                        canonical_json(list(component_metadata))
                    ),
                    "relative_target_digest": relative_digest,
                    "root_identity_digest": root_identity,
                }
            )
        )
        target_reference = ControlledTargetReference(
            target_reference_id,
            root_descriptor.canonical_digest,
            relative_digest,
            RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,
            target_identity,
        )
        target = HumanSelectedOpaqueTarget(
            target_id,
            root_descriptor.canonical_digest,
            target_reference.canonical_digest,
            relative_digest,
            target_identity,
            RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,
            selected_at,
        )
        capability = ActualTrialRootCapability(
            root_directory_fd=root_fd,
            root_metadata_digest=root_identity,
            root_descriptor_digest=root_descriptor.canonical_digest,
            resolver_policy_digest=resolver_policy.canonical_digest,
            target_reference_digest=target_reference.canonical_digest,
            target_identity_digest=target_identity,
            root_use=root_use,
            relative_components=parts,
            component_metadata_digests=component_metadata,
            allowed_file_types=allowed_file_types,
            _marker=_ACTUAL_ROOT_CAPABILITY_MARKER,
        )
        root_fd = -1
        return ActualRootProvisioning(
            capability,
            root_descriptor,
            resolver_policy,
            target_reference,
            target,
        )
    except (OSError, RealTargetResolverError) as exc:
        raise ActualTrialRootError("actual_root_provisioning_failed") from exc
    finally:
        _close_fd(verification_fd)
        _close_fd(root_fd)


def provision_human_selected_actual_root(
    *,
    root_path: str | os.PathLike[str],
    relative_target: str,
    root_id: str,
    target_reference_id: str,
    target_id: str,
    selected_at: datetime,
    allowed_file_types: tuple[str, ...] = (".md", ".txt"),
) -> ActualRootProvisioning:
    """Provision one Human-selected actual root/target without discovery or scan."""
    return _provision_selected_root(
        root_path=root_path,
        relative_target=relative_target,
        root_id=root_id,
        target_reference_id=target_reference_id,
        target_id=target_id,
        selected_at=selected_at,
        root_use=ActualTrialRootUse.HUMAN_SELECTED_ACTUAL,
        allowed_file_types=allowed_file_types,
    )


def _provision_controlled_fixture_actual_root(
    *,
    root_path: str | os.PathLike[str],
    relative_target: str,
    root_id: str,
    target_reference_id: str,
    target_id: str,
    selected_at: datetime,
    allowed_file_types: tuple[str, ...] = (".md", ".txt"),
) -> ActualRootProvisioning:
    """Private test bridge using the identical root/target implementation."""
    return _provision_selected_root(
        root_path=root_path,
        relative_target=relative_target,
        root_id=root_id,
        target_reference_id=target_reference_id,
        target_id=target_id,
        selected_at=selected_at,
        root_use=ActualTrialRootUse.CONTROLLED_FIXTURE,
        allowed_file_types=allowed_file_types,
    )


__all__ = [
    "ActualRootProvisioning",
    "ActualTrialRootCapability",
    "ActualTrialRootError",
    "ActualTrialRootUse",
    "HumanSelectedOpaqueTarget",
    "provision_human_selected_actual_root",
]
