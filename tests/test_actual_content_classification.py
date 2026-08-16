from dataclasses import replace

import pytest

from ragguard.actual_content_classification import (
    ActualContentClassificationError,
    ActualObservedDataClass,
    classify_actual_content,
)
from ragguard.storage_adapter import canonical_object_valid, digest


POLICY = digest("actual-classification-policy-v030")


def classify(text: str):
    return classify_actual_content(text.encode("utf-8"), policy_digest=POLICY)


def test_internal_low_content_is_approved_and_deterministic():
    first = classify("Synthetic internal low calibration note.")
    second = classify("Synthetic internal low calibration note.")
    assert first == second
    assert first.observed_data_class is ActualObservedDataClass.INTERNAL_LOW
    assert first.approved_internal_low
    assert not first.sensitive_classes
    assert canonical_object_valid(first)


@pytest.mark.parametrize(
    "text,expected",
    (
        ("synthetic.user@example.invalid", ActualObservedDataClass.PERSONAL_DATA),
        ("contractual confidential", ActualObservedDataClass.CONTRACTUAL_CONFIDENTIAL),
        ("api_key=synthetic-placeholder", ActualObservedDataClass.CREDENTIAL_LIKE),
        ("highly restricted", ActualObservedDataClass.HIGHLY_RESTRICTED),
    ),
)
def test_sensitive_classes_are_rejected(text, expected):
    result = classify(text)
    assert result.observed_data_class is expected
    assert expected in result.sensitive_classes
    assert not result.approved_internal_low


@pytest.mark.parametrize(
    "content",
    (b"", b"classification_unknown", b"synthetic\x00note", b"\xff\xfe"),
)
def test_unknown_or_ambiguous_inputs_fail_closed(content):
    result = classify_actual_content(content, policy_digest=POLICY)
    assert result.ambiguous
    assert result.observed_data_class in {
        ActualObservedDataClass.UNKNOWN,
        ActualObservedDataClass.AMBIGUOUS,
    }
    assert not result.approved_internal_low


def test_multiple_sensitive_classes_are_ambiguous():
    result = classify("api_key=synthetic-placeholder personal_data")
    assert result.observed_data_class is ActualObservedDataClass.AMBIGUOUS
    assert result.ambiguous
    assert len(result.sensitive_classes) == 2


def test_raw_text_is_absent_from_repr_and_canonical_metadata():
    marker = "synthetic-marker-must-not-appear"
    result = classify(marker)
    assert repr(result) == "ActualContentClassification(<safe>)"
    assert marker not in result.canonical_json()


def test_forged_classification_is_not_canonical():
    result = classify("Synthetic internal low calibration note.")
    object.__setattr__(
        result,
        "observed_data_class",
        ActualObservedDataClass.CREDENTIAL_LIKE,
    )
    assert not canonical_object_valid(result)


def test_invalid_policy_digest_is_rejected():
    with pytest.raises(ActualContentClassificationError):
        classify_actual_content(b"synthetic", policy_digest="not-a-digest")


def test_canonical_digest_changes_with_policy():
    result = classify("Synthetic internal low calibration note.")
    changed = classify_actual_content(
        b"Synthetic internal low calibration note.",
        policy_digest=digest("changed-policy"),
    )
    assert changed.canonical_digest != result.canonical_digest
