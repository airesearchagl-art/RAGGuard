from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ragguard.storage_adapter import canonical_json, digest, is_digest


class ActualContentClassificationError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class ActualObservedDataClass(str, Enum):
    INTERNAL_LOW = "internal_low"
    PERSONAL_DATA = "personal_data"
    CONTRACTUAL_CONFIDENTIAL = "contractual_confidential"
    CREDENTIAL_LIKE = "credential_like"
    HIGHLY_RESTRICTED = "highly_restricted"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


_RULES: tuple[tuple[ActualObservedDataClass, str, re.Pattern[str]], ...] = (
    (
        ActualObservedDataClass.CREDENTIAL_LIKE,
        "credential-assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|api[_ -]?key|access[_ -]?token|"
            r"client[_ -]?secret)\b\s*[:=]"
        ),
    ),
    (
        ActualObservedDataClass.CREDENTIAL_LIKE,
        "credential-token-shape",
        re.compile(
            r"(?i)(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
            r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
            r"(?:AKIA|ASIA)[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,})"
        ),
    ),
    (
        ActualObservedDataClass.PERSONAL_DATA,
        "personal-identifier-shape",
        re.compile(
            r"(?i)(?:\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|"
            r"\b\d{3}[- ]\d{3,4}[- ]\d{4}\b|"
            r"\b(?:personal[_ -]?data|date[_ -]?of[_ -]?birth|home[_ -]?address)\b|"
            r"(?:氏名|住所|生年月日|個人情報))"
        ),
    ),
    (
        ActualObservedDataClass.CONTRACTUAL_CONFIDENTIAL,
        "contractual-confidential-marker",
        re.compile(
            r"(?i)(?:\b(?:contractual[_ -]?confidential|non[- ]disclosure|"
            r"nda|confidential under agreement)\b|(?:契約機密|秘密保持))"
        ),
    ),
    (
        ActualObservedDataClass.HIGHLY_RESTRICTED,
        "highly-restricted-marker",
        re.compile(
            r"(?i)(?:\b(?:highly[_ -]?restricted|top[_ -]?secret|"
            r"restricted[_ -]?enclave)\b|(?:極秘|最高機密))"
        ),
    ),
)

_UNKNOWN_MARKER = re.compile(
    r"(?i)(?:\b(?:classification[_ -]?unknown|unknown[_ -]?classification|"
    r"classification[_ -]?ambiguous)\b|(?:分類不明|分類曖昧))"
)


@dataclass(frozen=True, repr=False)
class ActualContentClassification:
    policy_digest: str
    raw_content_digest: str
    observed_data_class: ActualObservedDataClass
    sensitive_classes: tuple[ActualObservedDataClass, ...]
    matched_rule_ids: tuple[str, ...]
    ambiguous: bool
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        allowed_sensitive = {
            ActualObservedDataClass.PERSONAL_DATA,
            ActualObservedDataClass.CONTRACTUAL_CONFIDENTIAL,
            ActualObservedDataClass.CREDENTIAL_LIKE,
            ActualObservedDataClass.HIGHLY_RESTRICTED,
        }
        if (
            not is_digest(self.policy_digest)
            or not is_digest(self.raw_content_digest)
            or not isinstance(self.observed_data_class, ActualObservedDataClass)
            or not isinstance(self.sensitive_classes, tuple)
            or any(item not in allowed_sensitive for item in self.sensitive_classes)
            or tuple(sorted(set(self.sensitive_classes), key=lambda item: item.value))
            != self.sensitive_classes
            or not isinstance(self.matched_rule_ids, tuple)
            or len(set(self.matched_rule_ids)) != len(self.matched_rule_ids)
            or not all(re.fullmatch(r"[a-z][a-z0-9-]{2,63}", item) for item in self.matched_rule_ids)
            or type(self.ambiguous) is not bool
        ):
            raise ActualContentClassificationError("classification_evidence_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualContentClassification(<safe>)"

    @property
    def approved_internal_low(self) -> bool:
        return (
            self.observed_data_class is ActualObservedDataClass.INTERNAL_LOW
            and not self.sensitive_classes
            and not self.ambiguous
        )

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "ambiguous": self.ambiguous,
                "matched_rule_ids": list(self.matched_rule_ids),
                "observed_data_class": self.observed_data_class.value,
                "policy_digest": self.policy_digest,
                "raw_content_digest": self.raw_content_digest,
                "sensitive_classes": [item.value for item in self.sensitive_classes],
            }
        )


def classify_actual_content(
    raw_content: bytes | bytearray | memoryview,
    *,
    policy_digest: str,
) -> ActualContentClassification:
    """Classify in memory without logging, persistence, network, or external models."""
    if not is_digest(policy_digest) or not isinstance(
        raw_content, (bytes, bytearray, memoryview)
    ):
        raise ActualContentClassificationError("classification_input_invalid")
    encoded = bytes(raw_content)
    try:
        text = encoded.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raw_digest = "sha256:" + __import__("hashlib").sha256(encoded).hexdigest()
        return ActualContentClassification(
            policy_digest,
            raw_digest,
            ActualObservedDataClass.UNKNOWN,
            (),
            ("non-utf8-content",),
            True,
        )
    finally:
        del encoded

    raw_digest = digest(text)
    matched: list[tuple[ActualObservedDataClass, str]] = []
    for data_class, rule_id, pattern in _RULES:
        if pattern.search(text):
            matched.append((data_class, rule_id))
    unknown = bool(_UNKNOWN_MARKER.search(text))
    invalid_control = any(ord(char) < 32 and char not in "\r\n\t" for char in text)
    empty = not text.strip()
    classes = tuple(sorted({item[0] for item in matched}, key=lambda item: item.value))
    rule_ids = [item[1] for item in matched]
    if unknown:
        rule_ids.append("unknown-classification-marker")
    if invalid_control:
        rule_ids.append("unsupported-control-character")
    if empty:
        rule_ids.append("empty-content")
    ambiguous = unknown or invalid_control or empty or len(classes) > 1
    if ambiguous and classes:
        observed = ActualObservedDataClass.AMBIGUOUS
    elif unknown or invalid_control or empty:
        observed = ActualObservedDataClass.UNKNOWN
    elif classes:
        observed = classes[0]
    else:
        observed = ActualObservedDataClass.INTERNAL_LOW
    del text
    return ActualContentClassification(
        policy_digest,
        raw_digest,
        observed,
        classes,
        tuple(dict.fromkeys(rule_ids)),
        ambiguous,
    )


__all__ = [
    "ActualContentClassification",
    "ActualContentClassificationError",
    "ActualObservedDataClass",
    "classify_actual_content",
]
