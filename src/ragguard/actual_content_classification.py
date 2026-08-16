from __future__ import annotations

import hashlib
import re
from dataclasses import InitVar, dataclass, field
from enum import Enum

from ragguard.real_data_access import RealDataAccessSelector, RealDataDocumentClass
from ragguard.real_data_access_authorization import RealDataAccessAuthorizationRecord
from ragguard.real_data_trial import RealDataClass, RealDataClassificationPolicy
from ragguard.real_data_trial_approval import ApprovedRealDataTrialRecord
from ragguard.real_trial_approval import ApprovedOneShotRealDataTrial
from ragguard.real_trial_root import RealTrialTargetSelection
from ragguard.storage_adapter import (
    canonical_json,
    canonical_object_valid,
    digest,
    is_digest,
)


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
        ActualObservedDataClass.CREDENTIAL_LIKE,
        "generic-credential-token-shape",
        re.compile(r"(?i)\b[a-z][a-z0-9]{2,15}_(?:live|prod)_[A-Za-z0-9_-]{12,}\b"),
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
_UNKNOWN_SENSITIVE_WORDING = re.compile(
    r"(?i)(?:\b(?:company confidential|business sensitive|not for distribution|"
    r"unreleased|need to know|customer record|authentication material)\b|"
    r"(?:社外秘|取扱注意|関係者限り|未公開|部外秘|認証情報|顧客情報|案件情報))"
)
_NUMERIC_ONLY = re.compile(r"^[\d\s.,:+\-/()]+$")
_OPAQUE_CODE_ONLY = re.compile(r"^(?=\S{12,}$)[A-Za-z0-9_\-+/=.:]+$")
_CLASSIFICATION_MARKER = object()


def _classification_policy_semantically_valid(
    policy: RealDataClassificationPolicy,
) -> bool:
    try:
        rebuilt = RealDataClassificationPolicy(
            policy.allowed_data_classes,
            policy.prohibited_data_classes,
            policy.masking_required_classes,
            policy.embedding_prohibited_classes,
            policy.logging_prohibited_classes,
            policy.persistence_prohibited_classes,
            policy.export_prohibited_classes,
            policy.policy_version,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return (
        canonical_object_valid(policy)
        and rebuilt.canonical_digest == policy.canonical_digest
    )


@dataclass(frozen=True, repr=False)
class PositiveInternalLowEvidence:
    """Object-backed expected classification chain; no caller digest is trusted alone."""

    classification_policy: RealDataClassificationPolicy
    selector: RealDataAccessSelector
    authorization_record: RealDataAccessAuthorizationRecord
    approved_source_trial: ApprovedRealDataTrialRecord
    approved_one_shot_trial: ApprovedOneShotRealDataTrial
    target_selection: RealTrialTargetSelection
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        objects = tuple(
            value for key, value in vars(self).items() if key != "canonical_digest"
        )
        expected_types = (
            RealDataClassificationPolicy,
            RealDataAccessSelector,
            RealDataAccessAuthorizationRecord,
            ApprovedRealDataTrialRecord,
            ApprovedOneShotRealDataTrial,
            RealTrialTargetSelection,
        )
        if (
            not all(
                isinstance(value, expected)
                for value, expected in zip(objects, expected_types, strict=True)
            )
            or not all(canonical_object_valid(value) for value in objects)
        ):
            raise ActualContentClassificationError("positive_evidence_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "PositiveInternalLowEvidence(<safe>)"

    def canonical_json(self) -> str:
        return canonical_json(
            {
                key: value.canonical_digest
                for key, value in vars(self).items()
                if key != "canonical_digest"
            }
        )

    @property
    def verified_internal_low(self) -> bool:
        policy = self.classification_policy
        selector = self.selector
        authorization = self.authorization_record
        source_trial = self.approved_source_trial
        approved_trial = self.approved_one_shot_trial
        target = self.target_selection
        return (
            _classification_policy_semantically_valid(policy)
            and all(
                canonical_object_valid(value)
                for value in (
                    selector,
                    authorization,
                    source_trial,
                    approved_trial,
                    target,
                )
            )
            and policy.allowed_data_classes == (RealDataClass.INTERNAL_LOW,)
            and RealDataClass.INTERNAL_LOW not in policy.prohibited_data_classes
            and selector.data_class is RealDataClass.INTERNAL_LOW
            and selector.document_class
            is RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE
            and selector.classification_digest == policy.canonical_digest
            and selector.approved_trial_digest == source_trial.canonical_digest
            and authorization.selector_digest == selector.canonical_digest
            and authorization.approved_trial_record_digest == source_trial.canonical_digest
            and approved_trial.access_authorization_record_digest
            == authorization.canonical_digest
            and approved_trial.target_selection_digest == target.canonical_digest
            and target.approved_selector_digest == selector.canonical_digest
            and target.expected_classification_digest == policy.canonical_digest
            and target.data_class is RealDataClass.INTERNAL_LOW
            and target.document_class
            is RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE
            and target.max_documents == 1
            and target.operator_id == approved_trial.operator_id
            and target.operator_id == authorization.operator_id
        )


@dataclass(frozen=True, repr=False)
class ActualContentClassification:
    policy_digest: str | None
    positive_evidence_digest: str | None
    raw_content_digest: str
    content_verification_digest: str
    expected_data_class: ActualObservedDataClass | None
    observed_data_class: ActualObservedDataClass
    sensitive_classes: tuple[ActualObservedDataClass, ...]
    matched_rule_ids: tuple[str, ...]
    positive_evidence_verified: bool
    actual_content_verified: bool
    ambiguous: bool
    _marker: InitVar[object | None] = None
    canonical_digest: str = field(init=False)

    def __post_init__(self, _marker: object | None) -> None:
        allowed_sensitive = {
            ActualObservedDataClass.PERSONAL_DATA,
            ActualObservedDataClass.CONTRACTUAL_CONFIDENTIAL,
            ActualObservedDataClass.CREDENTIAL_LIKE,
            ActualObservedDataClass.HIGHLY_RESTRICTED,
        }
        optional_digests = (self.policy_digest, self.positive_evidence_digest)
        if (
            _marker is not _CLASSIFICATION_MARKER
            or any(value is not None and not is_digest(value) for value in optional_digests)
            or not is_digest(self.raw_content_digest)
            or not is_digest(self.content_verification_digest)
            or (
                self.expected_data_class is not None
                and not isinstance(self.expected_data_class, ActualObservedDataClass)
            )
            or not isinstance(self.observed_data_class, ActualObservedDataClass)
            or not isinstance(self.sensitive_classes, tuple)
            or any(item not in allowed_sensitive for item in self.sensitive_classes)
            or tuple(sorted(set(self.sensitive_classes), key=lambda item: item.value))
            != self.sensitive_classes
            or not isinstance(self.matched_rule_ids, tuple)
            or len(set(self.matched_rule_ids)) != len(self.matched_rule_ids)
            or not all(
                re.fullmatch(r"[a-z][a-z0-9-]{2,63}", item)
                for item in self.matched_rule_ids
            )
            or type(self.positive_evidence_verified) is not bool
            or type(self.actual_content_verified) is not bool
            or type(self.ambiguous) is not bool
        ):
            raise ActualContentClassificationError("classification_evidence_invalid")
        object.__setattr__(self, "canonical_digest", digest(self.canonical_json()))

    def __repr__(self) -> str:
        return "ActualContentClassification(<safe>)"

    @property
    def approved_internal_low(self) -> bool:
        return (
            self.policy_digest is not None
            and self.positive_evidence_digest is not None
            and self.expected_data_class is ActualObservedDataClass.INTERNAL_LOW
            and self.observed_data_class is ActualObservedDataClass.INTERNAL_LOW
            and self.positive_evidence_verified
            and self.actual_content_verified
            and not self.sensitive_classes
            and not self.ambiguous
        )

    def canonical_json(self) -> str:
        return canonical_json(
            {
                "actual_content_verified": self.actual_content_verified,
                "ambiguous": self.ambiguous,
                "content_verification_digest": self.content_verification_digest,
                "expected_data_class": (
                    self.expected_data_class.value
                    if self.expected_data_class is not None
                    else None
                ),
                "matched_rule_ids": list(self.matched_rule_ids),
                "observed_data_class": self.observed_data_class.value,
                "policy_digest": self.policy_digest,
                "positive_evidence_digest": self.positive_evidence_digest,
                "positive_evidence_verified": self.positive_evidence_verified,
                "raw_content_digest": self.raw_content_digest,
                "sensitive_classes": [item.value for item in self.sensitive_classes],
            }
        )


@dataclass(frozen=True)
class _ContentSignals:
    raw_content_digest: str
    observed_data_class: ActualObservedDataClass
    sensitive_classes: tuple[ActualObservedDataClass, ...]
    matched_rule_ids: tuple[str, ...]
    actual_content_verified: bool
    ambiguous: bool


def _inspect_actual_content(
    raw_content: bytes | bytearray | memoryview,
) -> _ContentSignals:
    if not isinstance(raw_content, (bytes, bytearray, memoryview)):
        raise ActualContentClassificationError("classification_input_invalid")
    encoded = bytes(raw_content)
    raw_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    try:
        text = encoded.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _ContentSignals(
            raw_digest,
            ActualObservedDataClass.UNKNOWN,
            (),
            ("non-utf8-content",),
            False,
            True,
        )
    finally:
        del encoded

    matched: list[tuple[ActualObservedDataClass, str]] = []
    for data_class, rule_id, pattern in _RULES:
        if pattern.search(text):
            matched.append((data_class, rule_id))
    unknown_marker = bool(_UNKNOWN_MARKER.search(text))
    unknown_sensitive = bool(_UNKNOWN_SENSITIVE_WORDING.search(text))
    invalid_control = any(ord(char) < 32 and char not in "\r\n\t" for char in text)
    stripped = text.strip()
    empty = not stripped
    numeric_only = bool(
        stripped and not matched and _NUMERIC_ONLY.fullmatch(stripped)
    )
    opaque_code_only = bool(
        stripped and not matched and _OPAQUE_CODE_ONLY.fullmatch(stripped)
    )
    insufficient_language = bool(
        stripped
        and len(stripped) < 12
        and sum(char.isalpha() for char in stripped) < 6
    )
    classes = tuple(sorted({item[0] for item in matched}, key=lambda item: item.value))
    rule_ids = [item[1] for item in matched]
    for condition, rule_id in (
        (unknown_marker, "unknown-classification-marker"),
        (unknown_sensitive, "unknown-sensitive-wording"),
        (invalid_control, "unsupported-control-character"),
        (empty, "empty-content"),
        (numeric_only, "numeric-only-candidate"),
        (opaque_code_only, "opaque-code-only-content"),
        (insufficient_language, "insufficient-verifiable-language"),
    ):
        if condition:
            rule_ids.append(rule_id)
    ambiguous_signal = (
        unknown_marker
        or unknown_sensitive
        or invalid_control
        or empty
        or numeric_only
        or opaque_code_only
        or insufficient_language
        or len(classes) > 1
    )
    if len(classes) > 1:
        observed = ActualObservedDataClass.AMBIGUOUS
    elif classes:
        observed = classes[0]
    elif ambiguous_signal:
        observed = ActualObservedDataClass.UNKNOWN
    else:
        observed = ActualObservedDataClass.INTERNAL_LOW
    actual_verified = observed is ActualObservedDataClass.INTERNAL_LOW and not rule_ids
    del text
    return _ContentSignals(
        raw_digest,
        observed,
        classes,
        tuple(dict.fromkeys(rule_ids)),
        actual_verified,
        ambiguous_signal,
    )


def _has_prohibited_actual_content_signal(
    raw_content: bytes | bytearray | memoryview,
) -> bool:
    """Internal transformed-content residue check; never grants classification."""
    signals = _inspect_actual_content(raw_content)
    return bool(signals.sensitive_classes or signals.ambiguous)


def classify_actual_content(
    raw_content: bytes | bytearray | memoryview,
    *,
    positive_evidence: PositiveInternalLowEvidence | None = None,
) -> ActualContentClassification:
    """Classify in memory; INTERNAL_LOW requires a canonical object-backed chain."""
    signals = _inspect_actual_content(raw_content)
    try:
        evidence_valid = (
            isinstance(positive_evidence, PositiveInternalLowEvidence)
            and canonical_object_valid(positive_evidence)
            and positive_evidence.verified_internal_low
        )
    except (AttributeError, TypeError, ValueError):
        evidence_valid = False
    policy_digest = (
        positive_evidence.classification_policy.canonical_digest
        if evidence_valid and positive_evidence is not None
        else None
    )
    evidence_digest = (
        positive_evidence.canonical_digest
        if evidence_valid and positive_evidence is not None
        else None
    )
    expected = ActualObservedDataClass.INTERNAL_LOW if evidence_valid else None
    rule_ids = list(signals.matched_rule_ids)
    observed = signals.observed_data_class
    ambiguous = signals.ambiguous
    if not evidence_valid and not signals.sensitive_classes:
        rule_ids.append("positive-evidence-required")
        observed = ActualObservedDataClass.UNKNOWN
        ambiguous = True
    elif evidence_valid and observed is not ActualObservedDataClass.INTERNAL_LOW:
        rule_ids.append("expected-classification-mismatch")
    actual_verified = evidence_valid and signals.actual_content_verified
    verification_digest = digest(
        canonical_json(
            {
                "actual_content_verified": actual_verified,
                "expected_data_class": expected.value if expected else None,
                "observed_data_class": observed.value,
                "policy_digest": policy_digest,
                "positive_evidence_digest": evidence_digest,
                "raw_content_digest": signals.raw_content_digest,
                "rule_ids": list(dict.fromkeys(rule_ids)),
            }
        )
    )
    return ActualContentClassification(
        policy_digest,
        evidence_digest,
        signals.raw_content_digest,
        verification_digest,
        expected,
        observed,
        signals.sensitive_classes,
        tuple(dict.fromkeys(rule_ids)),
        evidence_valid,
        actual_verified,
        ambiguous,
        _marker=_CLASSIFICATION_MARKER,
    )


__all__ = [
    "ActualContentClassification",
    "ActualContentClassificationError",
    "ActualObservedDataClass",
    "PositiveInternalLowEvidence",
    "classify_actual_content",
]
