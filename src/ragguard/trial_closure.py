from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ragguard.storage_adapter import (
    canonical_datetime,
    canonical_json,
    digest,
    is_aware,
    is_digest,
    is_identifier,
)


_TRIAL_CLOSURE_MARKER = object()
_POST_READ_EVIDENCE_MARKER = object()


class TrialClosureError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class TrialClosureResult(str, Enum):
    COMPLETED = "completed"
    FAILED_CLOSED = "failed_closed"


@dataclass(frozen=True, repr=False)
class _Canonical:
    canonical_digest: str = field(init=False)

    def _seal(self, payload: object) -> None:
        object.__setattr__(self, "canonical_digest", digest(canonical_json(payload)))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<safe>)"


def _is_utc(value: object) -> bool:
    return is_aware(value) and value.utcoffset() == timedelta(0)


@dataclass(frozen=True, repr=False)
class TrialClosureRecord(_Canonical):
    closure_id: str
    one_shot_receipt_digest: str
    authorization_record_digest: str
    approved_trial_record_digest: str
    operator_id: str
    closed_at: datetime
    closure_result: TrialClosureResult
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        if (
            _marker is not _TRIAL_CLOSURE_MARKER
            or not is_identifier(self.closure_id)
            or not is_identifier(self.operator_id)
            or not all(
                is_digest(item)
                for item in (
                    self.one_shot_receipt_digest,
                    self.authorization_record_digest,
                    self.approved_trial_record_digest,
                )
            )
            or not _is_utc(self.closed_at)
            or not isinstance(self.closure_result, TrialClosureResult)
        ):
            raise TrialClosureError("trial_closure_record_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, object]:
        return {
            "approved_trial_record_digest": self.approved_trial_record_digest,
            "authorization_record_digest": self.authorization_record_digest,
            "closed_at": canonical_datetime(self.closed_at),
            "closure_id": self.closure_id,
            "closure_result": self.closure_result.value,
            "one_shot_receipt_digest": self.one_shot_receipt_digest,
            "operator_id": self.operator_id,
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())

    @property
    def downstream_processing_approved(self) -> bool:
        return False

    @property
    def persistent_storage_approved(self) -> bool:
        return False


@dataclass(frozen=True, repr=False)
class PostReadEvidence(_Canonical):
    receipt_digest: str
    target_identity_digest: str
    classification_digest: str
    masking_digest: str
    transformed_content_digest: str
    usage_exhaustion_digest: str
    closure_digest: str
    _marker: InitVar[object | None] = None

    def __post_init__(self, _marker: object | None) -> None:
        if _marker is not _POST_READ_EVIDENCE_MARKER or not all(
            is_digest(item)
            for item in (
                self.receipt_digest,
                self.target_identity_digest,
                self.classification_digest,
                self.masking_digest,
                self.transformed_content_digest,
                self.usage_exhaustion_digest,
                self.closure_digest,
            )
        ):
            raise TrialClosureError("post_read_evidence_invalid")
        self._seal(self._payload())

    def _payload(self) -> dict[str, str]:
        return {
            key: value
            for key, value in vars(self).items()
            if key != "canonical_digest"
        }

    def canonical_json(self) -> str:
        return canonical_json(self._payload())


__all__ = [
    "PostReadEvidence",
    "TrialClosureError",
    "TrialClosureRecord",
    "TrialClosureResult",
]
