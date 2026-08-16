from __future__ import annotations

import os
import stat
from dataclasses import InitVar, dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum

from ragguard.real_data_access_authorization import (
    AuthorizationUsageCounterContract,
    RealDataAccessAuthorizationLifecycle,
    RealDataAccessAuthorizationRecord,
    _LIMITED_READ_EXECUTOR_MARKER,
    _consume_authorization_usage_for_verified_read,
)
from ragguard.real_data_read_execution import (
    PreReadVerificationState,
    ReadTargetDescriptor,
    RealDataReadAuthorizationContext,
    RealDataReadExecutionRequest,
    RealDataReadSideEffectAccounting,
    _masking_policy_digest,
    _pre_read_checks,
)
from ragguard.real_data_read_receipt import (
    PostReadClassificationResult,
    PostReadMaskingVerification,
    PostReadVerificationState,
)
from ragguard.real_target_resolver import (
    ControlledTargetReference,
    FileIdentitySnapshot,
    RealTargetResolver,
    RealTargetResolverError,
    ResolvedTarget,
    _is_reparse_point,
    _snapshot_from_stat,
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
from ragguard.trial_closure import (
    PostReadEvidence,
    TrialClosureRecord,
    TrialClosureResult,
    _POST_READ_EVIDENCE_MARKER,
    _TRIAL_CLOSURE_MARKER,
)


_PRE_OPEN_MARKER = object()
_ONE_SHOT_RECEIPT_MARKER = object()
_SMALL_DOCUMENT_MAX_BYTES = 64 * 1024


class OneShotTrialError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class PreOpenVerificationResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class OneShotTrialExecutionResultState(str, Enum):
    READ_SUCCEEDED = "read_succeeded"
    OPEN_FAILED = "open_failed"
    IDENTITY_CHANGED = "identity_changed"
    READ_FAILED = "read_failed"
    INCOMPLETE = "incomplete"


class OneShotTrialLifecycle(str, Enum):
    REQUESTED = "requested"
    PREVERIFIED = "preverified"
    READ_COMPLETED = "read_completed"
    POSTVERIFIED = "postverified"
    CLOSED = "closed"
    FAILED_CLOSED = "failed_closed"


class ControlledFilesystemReadFault(str, Enum):
    NONE = "none"
    OPEN_FAILED = "open_failed"
    READ_FAILED = "read_failed"
    INCOMPLETE = "incomplete"
    OPEN_IDENTITY_CHANGED = "open_identity_changed"
    POST_IDENTITY_CHANGED = "post_identity_changed"
    CONTENT_MUTATED = "content_mutated"
    SYMLINK_SWAPPED = "symlink_swapped"
    CLASSIFICATION_FAILED = "classification_failed"
    MASKING_FAILED = "masking_failed"


class OneShotTrialLedgerFault(str, Enum):
    NONE = "none"
    FORGED_RECEIPT = "forged_receipt"
    CANDIDATE_STATE = "candidate_state"
    BEFORE_SWAP = "before_swap"


class TrialClosureFault(str, Enum):
    NONE = "none"
    BEFORE_SWAP = "before_swap"


class OneShotTrialReason(str, Enum):
    INVALID_CHAIN = "invalid_chain"
    RESOLUTION_FAILED = "resolution_failed"
    ROOT_CONFINEMENT_FAILED = "root_confinement_failed"
    PRE_OPEN_FAILED = "pre_open_failed"
    POLICY_INVALID = "policy_invalid"
    ROLE_CONFLICT = "role_conflict"
    LIFECYCLE_INVALID = "lifecycle_invalid"
    TEMPORAL_INVALID = "temporal_invalid"
    OPEN_FAILED = "open_failed"
    READ_FAILED = "read_failed"
    INCOMPLETE = "incomplete"
    IDENTITY_CHANGED = "identity_changed"
    CLASSIFICATION_FAILED = "classification_failed"
    MASKING_FAILED = "masking_failed"
    USAGE_INVALID = "usage_invalid"
    REPLAY = "replay"
    COMMIT_FAULT = "commit_fault"
    CLOSURE_INVALID = "closure_invalid"


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
            else item
        )
        for key, item in vars(value).items()
        if key != "canonical_digest"
    }


@dataclass(frozen=True, repr=False)
class OneShotTrialExecutionRequest(_Canonical):
    trial_execution_request_id: str
    v0_26_execution_request_digest: str
    authorization_record_digest: str
    root_descriptor_digest: str
    target_reference_digest: str
    operator_id: str
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.trial_execution_request_id)
            or not is_identifier(self.operator_id)
            or not all(
                is_digest(item)
                for item in (
                    self.v0_26_execution_request_digest,
                    self.authorization_record_digest,
                    self.root_descriptor_digest,
                    self.target_reference_digest,
                )
            )
            or not _is_utc(self.requested_at)
            or not _is_utc(self.expires_at)
            or self.expires_at <= self.requested_at
        ):
            raise OneShotTrialError("one_shot_execution_request_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class PreOpenVerification(_Canonical):
    request_digest: str
    authorization_record_digest: str
    target_reference_digest: str
    target_descriptor_digest: str
    pre_identity_digest: str
    operator_id: str
    authorization_valid: bool
    operator_exact: bool
    remaining_read_exact: bool
    target_selector_exact: bool
    root_confined: bool
    non_symlink: bool
    non_junction: bool
    non_reparse_point: bool
    regular_file: bool
    type_and_size_valid: bool
    identity_snapshot_exact: bool
    result: PreOpenVerificationResult
    evaluated_at: datetime
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        checks = tuple(
            item
            for key, item in vars(self).items()
            if key
            in {
                "authorization_valid",
                "operator_exact",
                "remaining_read_exact",
                "target_selector_exact",
                "root_confined",
                "non_symlink",
                "non_junction",
                "non_reparse_point",
                "regular_file",
                "type_and_size_valid",
                "identity_snapshot_exact",
            }
        )
        if (
            _marker is not _PRE_OPEN_MARKER
            or not is_identifier(self.operator_id)
            or not all(
                is_digest(item)
                for item in (
                    self.request_digest,
                    self.authorization_record_digest,
                    self.target_reference_digest,
                    self.target_descriptor_digest,
                    self.pre_identity_digest,
                )
            )
            or not all(type(item) is bool for item in checks)
            or not isinstance(self.result, PreOpenVerificationResult)
            or not _is_utc(self.evaluated_at)
            or (
                self.result is PreOpenVerificationResult.PASSED
                and not all(checks)
            )
        ):
            raise OneShotTrialError("pre_open_verification_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class OneShotTrialExecutionResult(_Canonical):
    request_digest: str
    target_reference_digest: str
    pre_identity_digest: str
    opened_identity_digest: str
    post_identity_digest: str
    operator_id: str
    started_at: datetime
    finished_at: datetime
    result: OneShotTrialExecutionResultState
    raw_content_digest: str

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.operator_id)
            or not all(
                is_digest(item)
                for item in (
                    self.request_digest,
                    self.target_reference_digest,
                    self.pre_identity_digest,
                    self.opened_identity_digest,
                    self.post_identity_digest,
                    self.raw_content_digest,
                )
            )
            or not _is_utc(self.started_at)
            or not _is_utc(self.finished_at)
            or self.finished_at < self.started_at
            or not isinstance(self.result, OneShotTrialExecutionResultState)
        ):
            raise OneShotTrialError("one_shot_execution_result_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class IdentityChainEvidence(_Canonical):
    target_reference_digest: str
    pre_identity_digest: str
    opened_identity_digest: str
    post_identity_digest: str
    raw_content_digest: str
    identity_stable: bool

    def __post_init__(self) -> None:
        if (
            not all(
                is_digest(item)
                for item in (
                    self.target_reference_digest,
                    self.pre_identity_digest,
                    self.opened_identity_digest,
                    self.post_identity_digest,
                    self.raw_content_digest,
                )
            )
            or type(self.identity_stable) is not bool
        ):
            raise OneShotTrialError("identity_chain_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class OneShotTrialReceipt(_Canonical):
    one_shot_receipt_id: str
    authorization_record_digest: str
    execution_request_digest: str
    target_reference_digest: str
    identity_chain_digest: str
    classification_result_digest: str
    masking_result_digest: str
    transformed_content_digest: str
    operator_id: str
    usage_before_digest: str
    usage_after_digest: str
    issued_at: datetime
    actual_read_completed: bool = field(init=False, default=True)
    embedding_authorized: bool = field(init=False, default=False)
    persistence_authorized: bool = field(init=False, default=False)
    export_authorized: bool = field(init=False, default=False)
    runtime_activation_authorized: bool = field(init=False, default=False)
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        if (
            _marker is not _ONE_SHOT_RECEIPT_MARKER
            or not is_identifier(self.one_shot_receipt_id)
            or not is_identifier(self.operator_id)
            or not all(
                is_digest(item)
                for key, item in vars(self).items()
                if key.endswith("_digest")
            )
            or not _is_utc(self.issued_at)
            or not self.actual_read_completed
            or any(
                (
                    self.embedding_authorized,
                    self.persistence_authorized,
                    self.export_authorized,
                    self.runtime_activation_authorized,
                )
            )
        ):
            raise OneShotTrialError("one_shot_receipt_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True)
class _FilesystemReadOutcome:
    execution_result: OneShotTrialExecutionResult
    opened_identity: FileIdentitySnapshot
    post_identity: FileIdentitySnapshot
    raw_payload: str | None
    transformed_payload: str | None
    observed_classification_digest: str
    sensitive_class_digest: str
    masked_class_digest: str
    blocked_class_digest: str
    accounting: RealDataReadSideEffectAccounting


class ControlledFilesystemReadAdapter:
    """Controlled-root adapter. It never accepts a path or performs discovery."""

    __slots__ = (
        "adapter_id",
        "resolver",
        "transformed_content_digest",
        "observed_classification_digest",
        "sensitive_class_digest",
        "masked_class_digest",
        "blocked_class_digest",
        "canonical_digest",
        "_transformed_payload",
        "_before_read_test_hook",
    )

    def __init__(
        self,
        *,
        adapter_id: str,
        resolver: RealTargetResolver,
        transformed_payload: str,
        observed_classification_digest: str,
        sensitive_class_digest: str,
        masked_class_digest: str,
        blocked_class_digest: str,
    ) -> None:
        if (
            not is_identifier(adapter_id)
            or not isinstance(resolver, RealTargetResolver)
            or not isinstance(transformed_payload, str)
            or not transformed_payload
            or not all(
                is_digest(item)
                for item in (
                    observed_classification_digest,
                    sensitive_class_digest,
                    masked_class_digest,
                    blocked_class_digest,
                )
            )
        ):
            raise OneShotTrialError("controlled_filesystem_adapter_invalid")
        self.adapter_id = adapter_id
        self.resolver = resolver
        self._transformed_payload = transformed_payload
        self.transformed_content_digest = digest(transformed_payload)
        self.observed_classification_digest = observed_classification_digest
        self.sensitive_class_digest = sensitive_class_digest
        self.masked_class_digest = masked_class_digest
        self.blocked_class_digest = blocked_class_digest
        self._before_read_test_hook = None
        self.canonical_digest = digest(self.canonical_json())

    def __repr__(self) -> str:
        return "ControlledFilesystemReadAdapter(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "adapter_id": self.adapter_id,
                "blocked_class_digest": self.blocked_class_digest,
                "masked_class_digest": self.masked_class_digest,
                "observed_classification_digest": self.observed_classification_digest,
                "resolver_policy_digest": self.resolver.policy.canonical_digest,
                "root_descriptor_digest": self.resolver.descriptor.canonical_digest,
                "sensitive_class_digest": self.sensitive_class_digest,
                "transformed_content_digest": self.transformed_content_digest,
            }
        )

    def _execute(
        self,
        *,
        resolved: ResolvedTarget,
        request: OneShotTrialExecutionRequest,
        started_at: datetime,
        finished_at: datetime,
        fault: ControlledFilesystemReadFault,
    ) -> _FilesystemReadOutcome:
        handle = self.resolver._handle_for(resolved)
        if (
            not canonical_object_valid(resolved)
            or not canonical_object_valid(request)
            or not _is_utc(started_at)
            or not _is_utc(finished_at)
            or finished_at < started_at
            or not isinstance(fault, ControlledFilesystemReadFault)
        ):
            self.resolver._release_resolved(resolved)
            raise OneShotTrialError("controlled_filesystem_execution_invalid")
        pre = resolved.pre_identity
        unavailable_digest = digest("controlled-target-identity-unavailable")

        def unavailable_snapshot(at: datetime) -> FileIdentitySnapshot:
            return FileIdentitySnapshot(
                handle.target_reference_digest,
                unavailable_digest,
                pre.size_class,
                unavailable_digest,
                unavailable_digest,
                at,
            )

        if fault is ControlledFilesystemReadFault.OPEN_FAILED:
            missing = unavailable_snapshot(started_at)
            result = OneShotTrialExecutionResult(
                request.canonical_digest,
                handle.target_reference_digest,
                pre.canonical_digest,
                missing.canonical_digest,
                missing.canonical_digest,
                request.operator_id,
                started_at,
                finished_at,
                OneShotTrialExecutionResultState.OPEN_FAILED,
                unavailable_digest,
            )
            outcome = _FilesystemReadOutcome(
                result,
                missing,
                missing,
                None,
                None,
                self.observed_classification_digest,
                self.sensitive_class_digest,
                self.masked_class_digest,
                self.blocked_class_digest,
                RealDataReadSideEffectAccounting(),
            )
            self.resolver._release_resolved(resolved)
            return outcome

        descriptor: int | None = None
        try:
            before_read_hook = self._before_read_test_hook
            self._before_read_test_hook = None
            if before_read_hook is not None:
                before_read_hook()
            descriptor = self.resolver._acquire_read_descriptor(resolved)
            opened_stat = os.fstat(descriptor)
            if not stat.S_ISREG(opened_stat.st_mode) or _is_reparse_point(opened_stat):
                raise OSError("controlled_target_not_regular")
            opened = _snapshot_from_stat(
                target_reference_digest=handle.target_reference_digest,
                file_stat=opened_stat,
                content_identity_digest=pre.content_identity_digest,
                observed_at=started_at,
            )
            if fault is ControlledFilesystemReadFault.OPEN_IDENTITY_CHANGED:
                changed = digest("injected-open-identity-change")
                opened = FileIdentitySnapshot(
                    handle.target_reference_digest,
                    changed,
                    pre.size_class,
                    changed,
                    pre.content_identity_digest,
                    started_at,
                )
                result = OneShotTrialExecutionResult(
                    request.canonical_digest,
                    handle.target_reference_digest,
                    pre.canonical_digest,
                    opened.canonical_digest,
                    opened.canonical_digest,
                    request.operator_id,
                    started_at,
                    finished_at,
                    OneShotTrialExecutionResultState.IDENTITY_CHANGED,
                    unavailable_digest,
                )
                return _FilesystemReadOutcome(
                    result,
                    opened,
                    opened,
                    None,
                    None,
                    self.observed_classification_digest,
                    self.sensitive_class_digest,
                    self.masked_class_digest,
                    self.blocked_class_digest,
                    RealDataReadSideEffectAccounting(),
                )
            if opened.metadata_digest != pre.metadata_digest:
                result_state = OneShotTrialExecutionResultState.IDENTITY_CHANGED
                raw_text = None
                raw_digest = unavailable_digest
                controlled_count = 0
            elif fault is ControlledFilesystemReadFault.READ_FAILED:
                result_state = OneShotTrialExecutionResultState.READ_FAILED
                raw_text = None
                raw_digest = unavailable_digest
                controlled_count = 0
            else:
                raw_bytes = os.read(descriptor, _SMALL_DOCUMENT_MAX_BYTES + 1)
                controlled_count = 1
                if len(raw_bytes) > _SMALL_DOCUMENT_MAX_BYTES:
                    result_state = OneShotTrialExecutionResultState.INCOMPLETE
                    raw_text = None
                    raw_digest = unavailable_digest
                else:
                    try:
                        raw_text = raw_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        result_state = OneShotTrialExecutionResultState.READ_FAILED
                        raw_text = None
                        raw_digest = unavailable_digest
                    else:
                        raw_digest = digest(raw_text)
                        if fault is ControlledFilesystemReadFault.CONTENT_MUTATED:
                            raw_digest = digest("injected-content-mutation")
                        result_state = (
                            OneShotTrialExecutionResultState.INCOMPLETE
                            if fault is ControlledFilesystemReadFault.INCOMPLETE
                            else OneShotTrialExecutionResultState.READ_SUCCEEDED
                        )
            opened = _snapshot_from_stat(
                target_reference_digest=handle.target_reference_digest,
                file_stat=opened_stat,
                content_identity_digest=raw_digest,
                observed_at=started_at,
            )
            post_stat = os.fstat(descriptor)
            binding_stable = self.resolver._post_read_binding_valid(
                resolved, descriptor
            )
            post = _snapshot_from_stat(
                target_reference_digest=handle.target_reference_digest,
                file_stat=post_stat,
                content_identity_digest=raw_digest,
                observed_at=finished_at,
            )
            if fault in (
                ControlledFilesystemReadFault.POST_IDENTITY_CHANGED,
                ControlledFilesystemReadFault.SYMLINK_SWAPPED,
            ) or not binding_stable:
                changed = digest("injected-post-identity-change")
                post = FileIdentitySnapshot(
                    handle.target_reference_digest,
                    changed,
                    pre.size_class,
                    changed,
                    raw_digest,
                    finished_at,
                )
            if (
                result_state is OneShotTrialExecutionResultState.READ_SUCCEEDED
                and (
                    opened.metadata_digest != pre.metadata_digest
                    or post.metadata_digest != pre.metadata_digest
                    or raw_digest != pre.content_identity_digest
                )
            ):
                result_state = OneShotTrialExecutionResultState.IDENTITY_CHANGED
            result = OneShotTrialExecutionResult(
                request.canonical_digest,
                handle.target_reference_digest,
                pre.canonical_digest,
                opened.canonical_digest,
                post.canonical_digest,
                request.operator_id,
                started_at,
                finished_at,
                result_state,
                raw_digest,
            )
            return _FilesystemReadOutcome(
                result,
                opened,
                post,
                raw_text,
                self._transformed_payload if raw_text is not None else None,
                self.observed_classification_digest,
                self.sensitive_class_digest,
                self.masked_class_digest,
                self.blocked_class_digest,
                RealDataReadSideEffectAccounting(
                    controlled_adapter_read_count=controlled_count
                ),
            )
        except RealTargetResolverError:
            missing = unavailable_snapshot(finished_at)
            result = OneShotTrialExecutionResult(
                request.canonical_digest,
                handle.target_reference_digest,
                pre.canonical_digest,
                missing.canonical_digest,
                missing.canonical_digest,
                request.operator_id,
                started_at,
                finished_at,
                OneShotTrialExecutionResultState.IDENTITY_CHANGED,
                unavailable_digest,
            )
            return _FilesystemReadOutcome(
                result,
                missing,
                missing,
                None,
                None,
                self.observed_classification_digest,
                self.sensitive_class_digest,
                self.masked_class_digest,
                self.blocked_class_digest,
                RealDataReadSideEffectAccounting(),
            )
        except OSError:
            missing = unavailable_snapshot(finished_at)
            result = OneShotTrialExecutionResult(
                request.canonical_digest,
                handle.target_reference_digest,
                pre.canonical_digest,
                missing.canonical_digest,
                missing.canonical_digest,
                request.operator_id,
                started_at,
                finished_at,
                OneShotTrialExecutionResultState.OPEN_FAILED,
                unavailable_digest,
            )
            return _FilesystemReadOutcome(
                result,
                missing,
                missing,
                None,
                None,
                self.observed_classification_digest,
                self.sensitive_class_digest,
                self.masked_class_digest,
                self.blocked_class_digest,
                RealDataReadSideEffectAccounting(),
            )
        finally:
            if descriptor is not None:
                os.close(descriptor)
            self.resolver._release_resolved(resolved)


def _install_controlled_filesystem_test_hook(
    adapter: ControlledFilesystemReadAdapter,
    hook,
) -> None:
    """Private adversarial-test hook; absent from the package public API."""
    if not isinstance(adapter, ControlledFilesystemReadAdapter) or not callable(hook):
        raise OneShotTrialError("controlled_filesystem_test_hook_invalid")
    adapter._before_read_test_hook = hook


@dataclass(frozen=True)
class OneShotTrialLedgerResult:
    applied: bool
    reasons: tuple[OneShotTrialReason, ...]
    lifecycle: OneShotTrialLifecycle
    pre_open: PreOpenVerification | None
    execution_result: OneShotTrialExecutionResult | None
    identity_chain: IdentityChainEvidence | None
    classification_result: PostReadClassificationResult | None
    masking_verification: PostReadMaskingVerification | None
    receipt: OneShotTrialReceipt | None
    usage_before: AuthorizationUsageCounterContract
    usage_after: AuthorizationUsageCounterContract | None
    exhausted_authorization: RealDataAccessAuthorizationRecord | None
    side_effects: RealDataReadSideEffectAccounting
    write_count: int
    mutation_count: int
    event_count: int


@dataclass(frozen=True)
class TrialClosureLedgerResult:
    applied: bool
    reasons: tuple[OneShotTrialReason, ...]
    lifecycle: OneShotTrialLifecycle
    closure: TrialClosureRecord | None
    evidence: PostReadEvidence | None
    write_count: int
    mutation_count: int
    event_count: int


@dataclass(frozen=True)
class _OneShotTrialLedgerState:
    receipts: tuple[OneShotTrialReceipt, ...] = ()
    identity_chains: tuple[IdentityChainEvidence, ...] = ()
    classifications: tuple[PostReadClassificationResult, ...] = ()
    maskings: tuple[PostReadMaskingVerification, ...] = ()
    exhausted_authorizations: tuple[RealDataAccessAuthorizationRecord, ...] = ()
    usage_states: tuple[AuthorizationUsageCounterContract, ...] = ()
    pending_closure_receipt_digests: frozenset[str] = frozenset()
    closures: tuple[TrialClosureRecord, ...] = ()
    post_read_evidence: tuple[PostReadEvidence, ...] = ()
    used_execution_request_digests: frozenset[str] = frozenset()
    used_target_reference_digests: frozenset[str] = frozenset()
    used_pre_open_digests: frozenset[str] = frozenset()
    used_execution_result_digests: frozenset[str] = frozenset()
    used_identity_chain_digests: frozenset[str] = frozenset()
    used_classification_digests: frozenset[str] = frozenset()
    used_masking_digests: frozenset[str] = frozenset()
    used_receipt_digests: frozenset[str] = frozenset()
    used_closure_digests: frozenset[str] = frozenset()
    write_count: int = 0
    mutation_count: int = 0
    event_count: int = 0


class TestOnlyOneShotTrialLedger:
    __test__ = False

    def __init__(self) -> None:
        self._state = _OneShotTrialLedgerState()

    @property
    def receipts(self) -> tuple[OneShotTrialReceipt, ...]:
        return self._state.receipts

    @property
    def closures(self) -> tuple[TrialClosureRecord, ...]:
        return self._state.closures

    @property
    def post_read_evidence(self) -> tuple[PostReadEvidence, ...]:
        return self._state.post_read_evidence

    @property
    def pending_closure_receipt_digests(self) -> frozenset[str]:
        return self._state.pending_closure_receipt_digests

    @property
    def write_count(self) -> int:
        return self._state.write_count

    @property
    def mutation_count(self) -> int:
        return self._state.mutation_count

    @property
    def event_count(self) -> int:
        return self._state.event_count

    @property
    def replay_snapshot(self) -> tuple[frozenset[str], ...]:
        state = self._state
        return (
            state.used_execution_request_digests,
            state.used_target_reference_digests,
            state.used_pre_open_digests,
            state.used_execution_result_digests,
            state.used_identity_chain_digests,
            state.used_classification_digests,
            state.used_masking_digests,
            state.used_receipt_digests,
            state.used_closure_digests,
        )

    def _denied(
        self,
        *,
        reasons: tuple[OneShotTrialReason, ...],
        context: RealDataReadAuthorizationContext,
        lifecycle: OneShotTrialLifecycle = OneShotTrialLifecycle.FAILED_CLOSED,
        pre_open: PreOpenVerification | None = None,
        execution_result: OneShotTrialExecutionResult | None = None,
        identity_chain: IdentityChainEvidence | None = None,
        classification: PostReadClassificationResult | None = None,
        masking: PostReadMaskingVerification | None = None,
        side_effects: RealDataReadSideEffectAccounting | None = None,
    ) -> OneShotTrialLedgerResult:
        return OneShotTrialLedgerResult(
            False,
            tuple(dict.fromkeys(reasons)),
            lifecycle,
            pre_open,
            execution_result,
            identity_chain,
            classification,
            masking,
            None,
            context.usage_contract,
            None,
            None,
            side_effects or RealDataReadSideEffectAccounting(),
            self.write_count,
            self.mutation_count,
            self.event_count,
        )

    def execute(
        self,
        *,
        one_shot_receipt_id: str,
        context: RealDataReadAuthorizationContext,
        v0_26_execution_request: RealDataReadExecutionRequest,
        target_descriptor: ReadTargetDescriptor,
        target_reference: ControlledTargetReference,
        request: OneShotTrialExecutionRequest,
        resolver: RealTargetResolver,
        adapter: ControlledFilesystemReadAdapter,
        pre_open_evaluated_at: datetime,
        started_at: datetime,
        finished_at: datetime,
        classification_evaluated_at: datetime,
        masking_evaluated_at: datetime,
        receipt_issued_at: datetime,
        evaluation_time: datetime,
        read_fault: ControlledFilesystemReadFault = ControlledFilesystemReadFault.NONE,
        ledger_fault: OneShotTrialLedgerFault = OneShotTrialLedgerFault.NONE,
    ) -> OneShotTrialLedgerResult:
        zero = RealDataReadSideEffectAccounting()
        public_objects = (
            context,
            v0_26_execution_request,
            target_descriptor,
            target_reference,
            request,
            resolver.descriptor,
            resolver.policy,
            adapter,
        )
        if not all(canonical_object_valid(item) for item in public_objects):
            return self._denied(
                reasons=(OneShotTrialReason.INVALID_CHAIN,), context=context
            )
        exact = (
            request.v0_26_execution_request_digest
            == v0_26_execution_request.canonical_digest,
            request.authorization_record_digest
            == context.authorization_record.canonical_digest,
            request.root_descriptor_digest == resolver.descriptor.canonical_digest,
            request.target_reference_digest == target_reference.canonical_digest,
            target_reference.root_digest == resolver.descriptor.canonical_digest,
            target_reference.expected_content_identity_digest
            == target_descriptor.content_identity_digest,
            target_reference.expected_document_class
            is target_descriptor.document_class,
            request.operator_id == v0_26_execution_request.operator_id,
            request.operator_id == context.authorization_record.operator_id,
            request.operator_id == context.operator_assignment.operator_id,
            request.operator_id == context.access_roles.real_data_operator_id,
            request.operator_id != context.access_approval.approver_id,
            request.operator_id != context.trial_approval.approver_id,
            adapter.resolver is resolver,
        )
        if not all(exact):
            return self._denied(
                reasons=(
                    OneShotTrialReason.INVALID_CHAIN,
                    OneShotTrialReason.ROLE_CONFLICT,
                ),
                context=context,
            )
        if (
            request.canonical_digest in self._state.used_execution_request_digests
            or target_reference.canonical_digest
            in self._state.used_target_reference_digests
        ):
            return self._denied(
                reasons=(OneShotTrialReason.REPLAY,), context=context
            )
        try:
            resolved = resolver.resolve(
                target_reference, observed_at=pre_open_evaluated_at
            )
        except RealTargetResolverError:
            return self._denied(
                reasons=(
                    OneShotTrialReason.RESOLUTION_FAILED,
                    OneShotTrialReason.ROOT_CONFINEMENT_FAILED,
                ),
                context=context,
            )
        pre_reasons, matches = _pre_read_checks(
            context,
            v0_26_execution_request,
            target_descriptor,
            None,
            evaluated_at=pre_open_evaluated_at,
            target_descriptor_digest=target_descriptor.canonical_digest,
            content_identity_digest=target_reference.expected_content_identity_digest,
        )
        authorization_valid = not pre_reasons
        operator_exact = all(exact[7:13])
        remaining_exact = (
            context.authorization_record.lifecycle
            is RealDataAccessAuthorizationLifecycle.AUTHORIZED
            and context.authorization_record.remaining_read_count == 1
            and context.usage_contract.remaining_read_count == 1
        )
        selector_exact = matches["selector_match"]
        identity_exact = (
            resolved.pre_identity.content_identity_digest
            == target_reference.expected_content_identity_digest
        )
        checks = (
            authorization_valid,
            operator_exact,
            remaining_exact,
            selector_exact,
            identity_exact,
        )
        pre_open = PreOpenVerification(
            request.canonical_digest,
            context.authorization_record.canonical_digest,
            target_reference.canonical_digest,
            target_descriptor.canonical_digest,
            resolved.pre_identity.canonical_digest,
            request.operator_id,
            authorization_valid,
            operator_exact,
            remaining_exact,
            selector_exact,
            True,
            True,
            True,
            True,
            True,
            True,
            identity_exact,
            PreOpenVerificationResult.PASSED
            if all(checks)
            else PreOpenVerificationResult.FAILED,
            pre_open_evaluated_at,
            _marker=_PRE_OPEN_MARKER,
        )
        if not all(checks):
            reasons = [OneShotTrialReason.PRE_OPEN_FAILED]
            if pre_reasons:
                reasons.append(OneShotTrialReason.POLICY_INVALID)
            if not operator_exact:
                reasons.append(OneShotTrialReason.ROLE_CONFLICT)
            if not remaining_exact:
                reasons.append(OneShotTrialReason.LIFECYCLE_INVALID)
            return self._denied(
                reasons=tuple(reasons), context=context, pre_open=pre_open
            )
        temporal = (
            context.authorization_record.issued_at
            < v0_26_execution_request.requested_at
            < request.requested_at
            < pre_open_evaluated_at
            < started_at
            < finished_at
            < classification_evaluated_at
            < masking_evaluated_at
            < receipt_issued_at
            <= evaluation_time
            < request.expires_at
            <= v0_26_execution_request.expires_at
            <= context.authorization_record.expires_at
            and all(
                _is_utc(item)
                for item in (
                    pre_open_evaluated_at,
                    started_at,
                    finished_at,
                    classification_evaluated_at,
                    masking_evaluated_at,
                    receipt_issued_at,
                    evaluation_time,
                )
            )
        )
        if not temporal:
            return self._denied(
                reasons=(OneShotTrialReason.TEMPORAL_INVALID,),
                context=context,
                pre_open=pre_open,
            )
        outcome = adapter._execute(
            resolved=resolved,
            request=request,
            started_at=started_at,
            finished_at=finished_at,
            fault=read_fault,
        )
        state_reason = {
            OneShotTrialExecutionResultState.OPEN_FAILED: OneShotTrialReason.OPEN_FAILED,
            OneShotTrialExecutionResultState.READ_FAILED: OneShotTrialReason.READ_FAILED,
            OneShotTrialExecutionResultState.INCOMPLETE: OneShotTrialReason.INCOMPLETE,
            OneShotTrialExecutionResultState.IDENTITY_CHANGED: OneShotTrialReason.IDENTITY_CHANGED,
        }.get(outcome.execution_result.result)
        if state_reason is not None:
            return self._denied(
                reasons=(state_reason,),
                context=context,
                pre_open=pre_open,
                execution_result=outcome.execution_result,
                side_effects=outcome.accounting,
            )
        stable = (
            resolved.pre_identity.metadata_digest
            == outcome.opened_identity.metadata_digest
            == outcome.post_identity.metadata_digest
            and resolved.pre_identity.content_identity_digest
            == outcome.opened_identity.content_identity_digest
            == outcome.post_identity.content_identity_digest
            == outcome.execution_result.raw_content_digest
            and resolved.pre_identity.size_class
            is outcome.opened_identity.size_class
            is outcome.post_identity.size_class
        )
        identity_chain = IdentityChainEvidence(
            target_reference.canonical_digest,
            resolved.pre_identity.canonical_digest,
            outcome.opened_identity.canonical_digest,
            outcome.post_identity.canonical_digest,
            outcome.execution_result.raw_content_digest,
            stable,
        )
        if not stable:
            return self._denied(
                reasons=(OneShotTrialReason.IDENTITY_CHANGED,),
                context=context,
                pre_open=pre_open,
                execution_result=outcome.execution_result,
                identity_chain=identity_chain,
                side_effects=outcome.accounting,
            )
        classification_passed = (
            read_fault is not ControlledFilesystemReadFault.CLASSIFICATION_FAILED
            and outcome.observed_classification_digest
            == target_descriptor.expected_classification_digest
        )
        classification = PostReadClassificationResult(
            outcome.execution_result.canonical_digest,
            target_descriptor.expected_classification_digest,
            outcome.observed_classification_digest,
            outcome.sensitive_class_digest,
            PostReadVerificationState.PASSED
            if classification_passed
            else PostReadVerificationState.FAILED,
            classification_evaluated_at,
        )
        if not classification_passed:
            return self._denied(
                reasons=(OneShotTrialReason.CLASSIFICATION_FAILED,),
                context=context,
                pre_open=pre_open,
                execution_result=outcome.execution_result,
                identity_chain=identity_chain,
                classification=classification,
                side_effects=outcome.accounting,
            )
        if outcome.raw_payload is None or outcome.transformed_payload is None:
            return self._denied(
                reasons=(OneShotTrialReason.READ_FAILED,),
                context=context,
                pre_open=pre_open,
                execution_result=outcome.execution_result,
                identity_chain=identity_chain,
                classification=classification,
                side_effects=outcome.accounting,
            )
        transformed_digest = digest(outcome.transformed_payload)
        masking_passed = (
            read_fault is not ControlledFilesystemReadFault.MASKING_FAILED
            and digest(outcome.raw_payload) == outcome.execution_result.raw_content_digest
            and transformed_digest == adapter.transformed_content_digest
            and transformed_digest != outcome.execution_result.raw_content_digest
        )
        masking = PostReadMaskingVerification(
            outcome.execution_result.canonical_digest,
            classification.canonical_digest,
            _masking_policy_digest(context.access_policy),
            outcome.execution_result.raw_content_digest,
            transformed_digest,
            outcome.masked_class_digest,
            outcome.blocked_class_digest,
            PostReadVerificationState.PASSED
            if masking_passed
            else PostReadVerificationState.FAILED,
            masking_evaluated_at,
        )
        if not masking_passed:
            return self._denied(
                reasons=(OneShotTrialReason.MASKING_FAILED,),
                context=context,
                pre_open=pre_open,
                execution_result=outcome.execution_result,
                identity_chain=identity_chain,
                classification=classification,
                masking=masking,
                side_effects=outcome.accounting,
            )
        try:
            exhausted, usage_after = _consume_authorization_usage_for_verified_read(
                context.authorization_record,
                context.usage_contract,
                executor_marker=_LIMITED_READ_EXECUTOR_MARKER,
            )
        except ValueError:
            return self._denied(
                reasons=(OneShotTrialReason.USAGE_INVALID,),
                context=context,
                pre_open=pre_open,
                execution_result=outcome.execution_result,
                identity_chain=identity_chain,
                classification=classification,
                masking=masking,
                side_effects=outcome.accounting,
            )
        receipt = OneShotTrialReceipt(
            one_shot_receipt_id,
            context.authorization_record.canonical_digest,
            request.canonical_digest,
            target_reference.canonical_digest,
            identity_chain.canonical_digest,
            classification.canonical_digest,
            masking.canonical_digest,
            transformed_digest,
            request.operator_id,
            context.usage_contract.canonical_digest,
            usage_after.canonical_digest,
            receipt_issued_at,
            _marker=_ONE_SHOT_RECEIPT_MARKER,
        )
        if ledger_fault is OneShotTrialLedgerFault.FORGED_RECEIPT:
            object.__setattr__(receipt, "operator_id", "forged-operator")
        evidence_valid = (
            canonical_object_valid(outcome.execution_result)
            and canonical_object_valid(identity_chain)
            and canonical_object_valid(classification)
            and canonical_object_valid(masking)
            and canonical_object_valid(receipt)
            and canonical_object_valid(exhausted)
            and canonical_object_valid(usage_after)
            and receipt.execution_request_digest == request.canonical_digest
            and receipt.authorization_record_digest
            == context.authorization_record.canonical_digest
            and receipt.target_reference_digest == target_reference.canonical_digest
            and receipt.identity_chain_digest == identity_chain.canonical_digest
            and receipt.classification_result_digest == classification.canonical_digest
            and receipt.masking_result_digest == masking.canonical_digest
            and receipt.operator_id == request.operator_id
            and receipt.operator_id == context.authorization_record.operator_id
            and usage_after.remaining_read_count == 0
            and usage_after.authorization_record_digest == exhausted.canonical_digest
            and exhausted.lifecycle
            is RealDataAccessAuthorizationLifecycle.EXHAUSTED
            and exhausted.remaining_read_count == 0
        )
        if not evidence_valid:
            return self._denied(
                reasons=(OneShotTrialReason.INVALID_CHAIN,),
                context=context,
                pre_open=pre_open,
                execution_result=outcome.execution_result,
                identity_chain=identity_chain,
                classification=classification,
                masking=masking,
                side_effects=outcome.accounting,
            )
        replay = (
            (request.canonical_digest, self._state.used_execution_request_digests),
            (
                target_reference.canonical_digest,
                self._state.used_target_reference_digests,
            ),
            (pre_open.canonical_digest, self._state.used_pre_open_digests),
            (
                outcome.execution_result.canonical_digest,
                self._state.used_execution_result_digests,
            ),
            (
                identity_chain.canonical_digest,
                self._state.used_identity_chain_digests,
            ),
            (
                classification.canonical_digest,
                self._state.used_classification_digests,
            ),
            (masking.canonical_digest, self._state.used_masking_digests),
            (receipt.canonical_digest, self._state.used_receipt_digests),
        )
        if any(item in used for item, used in replay):
            return self._denied(
                reasons=(OneShotTrialReason.REPLAY,),
                context=context,
                pre_open=pre_open,
                execution_result=outcome.execution_result,
                identity_chain=identity_chain,
                classification=classification,
                masking=masking,
                side_effects=outcome.accounting,
            )
        try:
            if ledger_fault is OneShotTrialLedgerFault.CANDIDATE_STATE:
                raise RuntimeError
            state = self._state
            candidate = replace(
                state,
                receipts=state.receipts + (receipt,),
                identity_chains=state.identity_chains + (identity_chain,),
                classifications=state.classifications + (classification,),
                maskings=state.maskings + (masking,),
                exhausted_authorizations=state.exhausted_authorizations
                + (exhausted,),
                usage_states=state.usage_states + (usage_after,),
                pending_closure_receipt_digests=(
                    state.pending_closure_receipt_digests
                    | {receipt.canonical_digest}
                ),
                used_execution_request_digests=(
                    state.used_execution_request_digests
                    | {request.canonical_digest}
                ),
                used_target_reference_digests=(
                    state.used_target_reference_digests
                    | {target_reference.canonical_digest}
                ),
                used_pre_open_digests=state.used_pre_open_digests
                | {pre_open.canonical_digest},
                used_execution_result_digests=(
                    state.used_execution_result_digests
                    | {outcome.execution_result.canonical_digest}
                ),
                used_identity_chain_digests=(
                    state.used_identity_chain_digests
                    | {identity_chain.canonical_digest}
                ),
                used_classification_digests=(
                    state.used_classification_digests
                    | {classification.canonical_digest}
                ),
                used_masking_digests=state.used_masking_digests
                | {masking.canonical_digest},
                used_receipt_digests=state.used_receipt_digests
                | {receipt.canonical_digest},
                write_count=state.write_count + 1,
                mutation_count=state.mutation_count + 1,
                event_count=state.event_count + 1,
            )
            if ledger_fault is OneShotTrialLedgerFault.BEFORE_SWAP:
                raise RuntimeError
            self._state = candidate
        except RuntimeError:
            return self._denied(
                reasons=(OneShotTrialReason.COMMIT_FAULT,),
                context=context,
                lifecycle=OneShotTrialLifecycle.READ_COMPLETED,
                pre_open=pre_open,
                execution_result=outcome.execution_result,
                identity_chain=identity_chain,
                classification=classification,
                masking=masking,
                side_effects=outcome.accounting,
            )
        return OneShotTrialLedgerResult(
            True,
            (),
            OneShotTrialLifecycle.POSTVERIFIED,
            pre_open,
            outcome.execution_result,
            identity_chain,
            classification,
            masking,
            receipt,
            context.usage_contract,
            usage_after,
            exhausted,
            outcome.accounting,
            self.write_count,
            self.mutation_count,
            self.event_count,
        )

    def close(
        self,
        *,
        closure_id: str,
        receipt: OneShotTrialReceipt,
        context: RealDataReadAuthorizationContext,
        closed_at: datetime,
        fault: TrialClosureFault = TrialClosureFault.NONE,
    ) -> TrialClosureLedgerResult:
        valid = (
            canonical_object_valid(receipt)
            and canonical_object_valid(context)
            and receipt.canonical_digest
            in self._state.pending_closure_receipt_digests
            and receipt.canonical_digest not in self._state.used_closure_digests
            and receipt.authorization_record_digest
            == context.authorization_record.canonical_digest
            and receipt.operator_id == context.authorization_record.operator_id
            and receipt.operator_id == context.operator_assignment.operator_id
            and receipt.operator_id != context.access_approval.approver_id
            and receipt.operator_id != context.trial_approval.approver_id
            and _is_utc(closed_at)
            and closed_at > receipt.issued_at
        )
        if not valid:
            return TrialClosureLedgerResult(
                False,
                (OneShotTrialReason.CLOSURE_INVALID,),
                OneShotTrialLifecycle.FAILED_CLOSED,
                None,
                None,
                self.write_count,
                self.mutation_count,
                self.event_count,
            )
        closure = TrialClosureRecord(
            closure_id,
            receipt.canonical_digest,
            context.authorization_record.canonical_digest,
            context.approved_trial.canonical_digest,
            receipt.operator_id,
            closed_at,
            TrialClosureResult.COMPLETED,
            _marker=_TRIAL_CLOSURE_MARKER,
        )
        index = self._state.receipts.index(receipt)
        identity_chain = self._state.identity_chains[index]
        classification = self._state.classifications[index]
        masking = self._state.maskings[index]
        usage = self._state.usage_states[index]
        evidence = PostReadEvidence(
            receipt.canonical_digest,
            identity_chain.post_identity_digest,
            classification.canonical_digest,
            masking.canonical_digest,
            receipt.transformed_content_digest,
            usage.canonical_digest,
            closure.canonical_digest,
            _marker=_POST_READ_EVIDENCE_MARKER,
        )
        try:
            state = self._state
            candidate = replace(
                state,
                pending_closure_receipt_digests=(
                    state.pending_closure_receipt_digests
                    - {receipt.canonical_digest}
                ),
                closures=state.closures + (closure,),
                post_read_evidence=state.post_read_evidence + (evidence,),
                used_closure_digests=state.used_closure_digests
                | {closure.canonical_digest},
                write_count=state.write_count + 1,
                mutation_count=state.mutation_count + 1,
                event_count=state.event_count + 1,
            )
            if fault is TrialClosureFault.BEFORE_SWAP:
                raise RuntimeError
            self._state = candidate
        except RuntimeError:
            failed = TrialClosureRecord(
                closure_id,
                receipt.canonical_digest,
                context.authorization_record.canonical_digest,
                context.approved_trial.canonical_digest,
                receipt.operator_id,
                closed_at,
                TrialClosureResult.FAILED_CLOSED,
                _marker=_TRIAL_CLOSURE_MARKER,
            )
            return TrialClosureLedgerResult(
                False,
                (OneShotTrialReason.COMMIT_FAULT,),
                OneShotTrialLifecycle.FAILED_CLOSED,
                failed,
                None,
                self.write_count,
                self.mutation_count,
                self.event_count,
            )
        return TrialClosureLedgerResult(
            True,
            (),
            OneShotTrialLifecycle.CLOSED,
            closure,
            evidence,
            self.write_count,
            self.mutation_count,
            self.event_count,
        )


__all__ = [
    "ControlledFilesystemReadAdapter",
    "ControlledFilesystemReadFault",
    "IdentityChainEvidence",
    "OneShotTrialError",
    "OneShotTrialExecutionRequest",
    "OneShotTrialExecutionResult",
    "OneShotTrialExecutionResultState",
    "OneShotTrialLedgerFault",
    "OneShotTrialLedgerResult",
    "OneShotTrialLifecycle",
    "OneShotTrialReason",
    "OneShotTrialReceipt",
    "PreOpenVerification",
    "PreOpenVerificationResult",
    "TestOnlyOneShotTrialLedger",
    "TrialClosureFault",
    "TrialClosureLedgerResult",
]
