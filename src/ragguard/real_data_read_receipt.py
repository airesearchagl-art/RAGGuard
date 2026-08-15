from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ragguard.real_data_access import RealDataByteClass
from ragguard.storage_adapter import (
    canonical_datetime,
    canonical_json,
    digest,
    is_aware,
    is_digest,
    is_identifier,
)


_READ_RECEIPT_MARKER = object()
_MASKED_CANDIDATE_MARKER = object()


class RealDataReadReceiptError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class ReadExecutionResultState(str, Enum):
    READ_SUCCEEDED = "read_succeeded"
    OPEN_FAILED = "open_failed"
    READ_FAILED = "read_failed"
    INCOMPLETE = "incomplete"


class PostReadVerificationState(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class RealDataReadReceiptResult(str, Enum):
    VERIFIED_READ_COMPLETED = "verified_read_completed"


class ReadDownstreamState(str, Enum):
    VERIFIED_MASKED_CONTENT_CANDIDATE = "verified_masked_content_candidate"


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


def _is_utc(value: object) -> bool:
    return is_aware(value) and value.utcoffset() == timedelta(0)


def _payload(value: object, *, excluded: tuple[str, ...] = ()) -> dict[str, object]:
    return {
        key: (
            canonical_datetime(item)
            if isinstance(item, datetime)
            else item.value
            if isinstance(item, Enum)
            else item
        )
        for key, item in vars(value).items()
        if key != "canonical_digest" and key not in excluded
    }


@dataclass(frozen=True, repr=False)
class ReadExecutionResult(_Canonical):
    execution_id: str
    execution_request_digest: str
    target_descriptor_digest: str
    operator_id: str
    started_at: datetime
    finished_at: datetime
    result: ReadExecutionResultState
    bytes_class: RealDataByteClass
    raw_content_digest: str

    def __post_init__(self) -> None:
        if (
            not is_identifier(self.execution_id)
            or not is_identifier(self.operator_id)
            or not is_digest(self.execution_request_digest)
            or not is_digest(self.target_descriptor_digest)
            or not is_digest(self.raw_content_digest)
            or not _is_utc(self.started_at)
            or not _is_utc(self.finished_at)
            or self.finished_at < self.started_at
            or not isinstance(self.result, ReadExecutionResultState)
            or not isinstance(self.bytes_class, RealDataByteClass)
        ):
            raise RealDataReadReceiptError("read_execution_result_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class PostReadClassificationResult(_Canonical):
    execution_result_digest: str
    expected_classification_digest: str
    observed_classification_digest: str
    sensitive_class_digest: str
    result: PostReadVerificationState
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if (
            not all(
                is_digest(item)
                for item in (
                    self.execution_result_digest,
                    self.expected_classification_digest,
                    self.observed_classification_digest,
                    self.sensitive_class_digest,
                )
            )
            or not isinstance(self.result, PostReadVerificationState)
            or not _is_utc(self.evaluated_at)
        ):
            raise RealDataReadReceiptError("post_read_classification_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class PostReadMaskingVerification(_Canonical):
    execution_result_digest: str
    classification_result_digest: str
    masking_policy_digest: str
    raw_content_digest: str
    transformed_content_digest: str
    masked_class_digest: str
    blocked_class_digest: str
    result: PostReadVerificationState
    evaluated_at: datetime

    def __post_init__(self) -> None:
        digest_values = (
            self.execution_result_digest,
            self.classification_result_digest,
            self.masking_policy_digest,
            self.raw_content_digest,
            self.transformed_content_digest,
            self.masked_class_digest,
            self.blocked_class_digest,
        )
        if (
            not all(is_digest(item) for item in digest_values)
            or not isinstance(self.result, PostReadVerificationState)
            or not _is_utc(self.evaluated_at)
        ):
            raise RealDataReadReceiptError("post_read_masking_verification_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


@dataclass(frozen=True, repr=False)
class RealDataReadReceipt(_Canonical):
    receipt_id: str
    execution_request_digest: str
    authorization_record_digest: str
    target_descriptor_digest: str
    operator_id: str
    execution_result_digest: str
    classification_result_digest: str
    masking_verification_digest: str
    transformed_content_digest: str
    usage_before_digest: str
    usage_after_digest: str
    issued_at: datetime
    result: RealDataReadReceiptResult
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        digest_values = tuple(
            item for key, item in vars(self).items() if key.endswith("_digest")
        )
        if (
            _marker is not _READ_RECEIPT_MARKER
            or not is_identifier(self.receipt_id)
            or not is_identifier(self.operator_id)
            or not all(is_digest(item) for item in digest_values)
            or not _is_utc(self.issued_at)
            or self.result is not RealDataReadReceiptResult.VERIFIED_READ_COMPLETED
        ):
            raise RealDataReadReceiptError("real_data_read_receipt_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def embedding_authorized(self) -> bool:
        return False

    @property
    def persistence_authorized(self) -> bool:
        return False

    @property
    def local_rag_full_processing_authorized(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class VerifiedMaskedContentCandidate(_Canonical):
    candidate_id: str
    receipt_digest: str
    transformed_content_digest: str
    stage: ReadDownstreamState
    created_at: datetime
    embedding_authorized: bool = field(init=False, default=False)
    persistence_authorized: bool = field(init=False, default=False)
    unrestricted_retrieval_authorized: bool = field(init=False, default=False)
    prompt_input_authorized: bool = field(init=False, default=False)
    llm_input_authorized: bool = field(init=False, default=False)
    export_authorized: bool = field(init=False, default=False)
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        if (
            _marker is not _MASKED_CANDIDATE_MARKER
            or not is_identifier(self.candidate_id)
            or not is_digest(self.receipt_digest)
            or not is_digest(self.transformed_content_digest)
            or self.stage is not ReadDownstreamState.VERIFIED_MASKED_CONTENT_CANDIDATE
            or not _is_utc(self.created_at)
        ):
            raise RealDataReadReceiptError("verified_masked_candidate_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return _payload(self)

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


__all__ = [
    "PostReadClassificationResult",
    "PostReadMaskingVerification",
    "PostReadVerificationState",
    "ReadDownstreamState",
    "ReadExecutionResult",
    "ReadExecutionResultState",
    "RealDataReadReceipt",
    "RealDataReadReceiptError",
    "RealDataReadReceiptResult",
    "VerifiedMaskedContentCandidate",
]
