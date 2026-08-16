from dataclasses import replace
from datetime import timedelta
import os
import stat

import pytest

from ragguard.real_target_resolver import (
    RealTargetResolverError,
    _SMALL_DOCUMENT_MAX_BYTES,
)
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_session_contract import NOW
from test_one_shot_trial_execution import one_shot_call


def test_controlled_root_resolves_opaque_reference_without_path_metadata(tmp_path):
    _, call, _ = one_shot_call(tmp_path)
    resolved = call["resolver"].resolve(
        call["target_reference"], observed_at=NOW + timedelta(minutes=31)
    )
    assert canonical_object_valid(resolved)
    assert canonical_object_valid(resolved.pre_identity)
    assert resolved.pre_identity.content_identity_digest == call[
        "target_reference"
    ].expected_content_identity_digest
    assert "path" not in resolved.canonical_json().lower()
    assert "synthetic-fixture" not in resolved.canonical_json()
    assert "ragguard-v027-controlled-root" not in repr(resolved)


@pytest.mark.parametrize(
    "binding",
    (
        "../synthetic-fixture.txt",
        "nested/../../synthetic-fixture.txt",
        "Z:\\synthetic\\fixture.txt",
        "\\\\synthetic.invalid\\share\\fixture.txt",
        "\\\\?\\Z:\\synthetic\\fixture.txt",
        "synthetic-fixture.txt:alternate",
        "*.txt",
        "synthetic?.txt",
    ),
)
def test_traversal_absolute_unc_device_ads_and_glob_bindings_are_rejected(
    tmp_path, binding
):
    _, call, _ = one_shot_call(tmp_path)
    reference = call["target_reference"]
    call["resolver"]._capability.target_bindings[
        reference.relative_target_digest
    ] = binding
    with pytest.raises(RealTargetResolverError):
        call["resolver"].resolve(
            reference, observed_at=NOW + timedelta(minutes=31)
        )


def test_directory_target_is_rejected(tmp_path):
    _, call, root = one_shot_call(tmp_path)
    directory = root / "synthetic-directory"
    directory.mkdir()
    reference = call["target_reference"]
    call["resolver"]._capability.target_bindings[
        reference.relative_target_digest
    ] = directory.name
    with pytest.raises(RealTargetResolverError) as error:
        call["resolver"].resolve(
            reference, observed_at=NOW + timedelta(minutes=31)
        )
    assert error.value.category == "regular_file_required"


def test_wrong_extension_is_rejected(tmp_path):
    _, call, root = one_shot_call(tmp_path)
    candidate = root / "synthetic-fixture.bin"
    candidate.write_text("synthetic binary marker", encoding="utf-8")
    reference = call["target_reference"]
    call["resolver"]._capability.target_bindings[
        reference.relative_target_digest
    ] = candidate.name
    with pytest.raises(RealTargetResolverError) as error:
        call["resolver"].resolve(
            reference, observed_at=NOW + timedelta(minutes=31)
        )
    assert error.value.category == "file_type_rejected"


def test_oversized_target_is_rejected_without_read(tmp_path):
    _, call, root = one_shot_call(tmp_path)
    candidate = root / "synthetic-oversized.txt"
    candidate.write_bytes(b"s" * (_SMALL_DOCUMENT_MAX_BYTES + 1))
    reference = call["target_reference"]
    call["resolver"]._capability.target_bindings[
        reference.relative_target_digest
    ] = candidate.name
    with pytest.raises(RealTargetResolverError) as error:
        call["resolver"].resolve(
            reference, observed_at=NOW + timedelta(minutes=31)
        )
    assert error.value.category == "file_size_rejected"


def test_symlink_target_is_rejected_when_platform_allows_fixture_symlink(tmp_path):
    _, call, root = one_shot_call(tmp_path)
    link = root / "synthetic-link.txt"
    try:
        link.symlink_to(root / "synthetic-fixture.txt")
    except OSError:
        pytest.skip("fixture symlink creation is unavailable on this host")
    reference = call["target_reference"]
    call["resolver"]._capability.target_bindings[
        reference.relative_target_digest
    ] = link.name
    with pytest.raises(RealTargetResolverError) as error:
        call["resolver"].resolve(
            reference, observed_at=NOW + timedelta(minutes=31)
        )
    assert error.value.category == "link_or_reparse_target_rejected"


def test_forged_reference_and_root_mismatch_are_rejected(tmp_path):
    _, call, _ = one_shot_call(tmp_path)
    forged = call["target_reference"]
    object.__setattr__(forged, "target_reference_id", "forged-reference")
    with pytest.raises(RealTargetResolverError):
        call["resolver"].resolve(
            forged, observed_at=NOW + timedelta(minutes=31)
        )

    second = tmp_path / "second"
    second.mkdir()
    _, pristine, _ = one_shot_call(second)
    wrong_root = replace(
        pristine["target_reference"], root_digest=digest("wrong-root")
    )
    with pytest.raises(RealTargetResolverError):
        pristine["resolver"].resolve(
            wrong_root, observed_at=NOW + timedelta(minutes=31)
        )


def test_resolver_policy_is_fail_closed_for_all_link_and_path_classes(tmp_path):
    _, call, _ = one_shot_call(tmp_path)
    policy = call["resolver"].policy
    assert not policy.allow_symlink
    assert not policy.allow_junction
    assert not policy.allow_reparse_point
    assert not policy.allow_parent_traversal
    assert not policy.allow_absolute_user_input
    assert policy.require_regular_file
    assert policy.require_identity_stability


def test_resolved_read_authority_is_pinned_file_handle_not_path(tmp_path):
    _, call, _ = one_shot_call(tmp_path)
    resolver = call["resolver"]
    resolved = resolver.resolve(
        call["target_reference"], observed_at=NOW + timedelta(minutes=31)
    )
    handle = resolver._handle_for(resolved)
    assert not hasattr(handle, "path")
    assert not hasattr(handle, "root_path")
    assert handle.pinned_file_fd >= 0
    assert stat.S_ISREG(os.fstat(handle.pinned_file_fd).st_mode)
    assert resolver._capability.root_directory_fd >= 0
    assert stat.S_ISDIR(os.fstat(resolver._capability.root_directory_fd).st_mode)
    assert handle.component_metadata_digests
    resolver._release_resolved(resolved)
