from __future__ import annotations

import re
from dataclasses import dataclass, field

from ragguard.actual_content_classification import (
    ActualContentClassification,
    classify_actual_content,
)
from ragguard.storage_adapter import (
    canonical_json,
    canonical_object_valid,
    digest,
    is_digest,
)


class ActualContentMaskingError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, repr=False)
class ActualContentMasking:
    classification_digest: str
    masking_policy_digest: str
    raw_content_digest: str
    transformed_content_digest: str
    masked_class_digest: str
    blocked_class_digest: str
    token_count: int
    prohibited_residue_detected: bool
    verified: bool
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        digests = (
            self.classification_digest,
            self.masking_policy_digest,
            self.raw_content_digest,
            self.transformed_content_digest,
            self.masked_class_digest,
            self.blocked_class_digest,
        )
        if (
            not all(is_digest(item) for item in digests)
            or not isinstance(self.token_count, int)
            or self.token_count < 1
            or type(self.prohibited_residue_detected) is not bool
            or type(self.verified) is not bool
            or self.raw_content_digest == self.transformed_content_digest
            or self.verified == self.prohibited_residue_detected
        ):
            raise ActualContentMaskingError("masking_evidence_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualContentMasking(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "blocked_class_digest": self.blocked_class_digest,
                "classification_digest": self.classification_digest,
                "masked_class_digest": self.masked_class_digest,
                "masking_policy_digest": self.masking_policy_digest,
                "prohibited_residue_detected": self.prohibited_residue_detected,
                "raw_content_digest": self.raw_content_digest,
                "token_count": self.token_count,
                "transformed_content_digest": self.transformed_content_digest,
                "verified": self.verified,
            }
        )


@dataclass(frozen=True, repr=False)
class ActualMaskingOutcome:
    evidence: ActualContentMasking
    transformed_content: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not canonical_object_valid(self.evidence)
            or not isinstance(self.transformed_content, str)
            or not self.transformed_content
            or digest(self.transformed_content)
            != self.evidence.transformed_content_digest
        ):
            raise ActualContentMaskingError("masking_outcome_invalid")

    def __repr__(self) -> str:
        return "ActualMaskingOutcome(<safe>)"


def mask_actual_content(
    raw_content: bytes | bytearray | memoryview,
    *,
    classification: ActualContentClassification,
    masking_policy_digest: str,
) -> ActualMaskingOutcome:
    """Irreversibly token-digest internal-low text; raw text never leaves this call."""
    if (
        not canonical_object_valid(classification)
        or not classification.approved_internal_low
        or not is_digest(masking_policy_digest)
        or not isinstance(raw_content, (bytes, bytearray, memoryview))
    ):
        raise ActualContentMaskingError("masking_input_invalid")
    encoded = bytes(raw_content)
    try:
        text = encoded.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ActualContentMaskingError("masking_decode_failed") from exc
    finally:
        del encoded
    if digest(text) != classification.raw_content_digest:
        del text
        raise ActualContentMaskingError("masking_raw_binding_mismatch")
    tokens = re.findall(r"\S+", text)
    del text
    if not tokens:
        raise ActualContentMaskingError("masking_empty_content")
    transformed_tokens = [
        "tok_" + digest(canonical_json({"index": index, "token": token}))[7:31]
        for index, token in enumerate(tokens)
    ]
    for index in range(len(tokens)):
        tokens[index] = ""
    del tokens
    transformed = " ".join(transformed_tokens)
    del transformed_tokens
    residue = classify_actual_content(
        transformed.encode("utf-8"), policy_digest=classification.policy_digest
    )
    prohibited = not residue.approved_internal_low
    evidence = ActualContentMasking(
        classification.canonical_digest,
        masking_policy_digest,
        classification.raw_content_digest,
        digest(transformed),
        digest(canonical_json({"masked": []})),
        digest(canonical_json({"blocked": []})),
        len(transformed.split()),
        prohibited,
        not prohibited,
    )
    return ActualMaskingOutcome(evidence, transformed)


__all__ = [
    "ActualContentMasking",
    "ActualContentMaskingError",
    "ActualMaskingOutcome",
    "mask_actual_content",
]
