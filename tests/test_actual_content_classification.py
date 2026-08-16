import pytest

from actual_trial_v030_support import actual_execution_chain
from ragguard.actual_content_classification import (
    ActualObservedDataClass,
    classify_actual_content,
)
from ragguard.real_data_trial import RealDataClass
from ragguard.storage_adapter import canonical_object_valid, digest


INTERNAL_LOW_TEXT = "Synthetic internal low calibration note for controlled verification."


@pytest.fixture
def positive_evidence(tmp_path):
    call = actual_execution_chain(tmp_path)
    try:
        yield call["positive_classification_evidence"]
    finally:
        call["provision"].capability.close()


def classify(text: str, positive_evidence):
    return classify_actual_content(
        text.encode("utf-8"),
        positive_evidence=positive_evidence,
    )


def test_internal_low_requires_positive_evidence_and_is_deterministic(
    positive_evidence,
):
    first = classify(INTERNAL_LOW_TEXT, positive_evidence)
    second = classify(INTERNAL_LOW_TEXT, positive_evidence)
    assert first == second
    assert first.observed_data_class is ActualObservedDataClass.INTERNAL_LOW
    assert first.expected_data_class is ActualObservedDataClass.INTERNAL_LOW
    assert first.positive_evidence_verified
    assert first.actual_content_verified
    assert first.approved_internal_low
    assert not first.sensitive_classes
    assert canonical_object_valid(first)


def test_arbitrary_ordinary_text_without_positive_attestation_is_rejected():
    result = classify_actual_content(
        b"An ordinary looking note with no positive classification attestation."
    )
    assert result.observed_data_class is ActualObservedDataClass.UNKNOWN
    assert "positive-evidence-required" in result.matched_rule_ids
    assert not result.positive_evidence_verified
    assert not result.approved_internal_low


def test_benign_looking_confidential_content_without_attestation_is_rejected():
    result = classify_actual_content(
        b"Quarterly strategy calibration note for the internal project team."
    )
    assert result.observed_data_class is ActualObservedDataClass.UNKNOWN
    assert result.ambiguous
    assert not result.approved_internal_low


@pytest.mark.parametrize(
    "text,expected",
    (
        ("synthetic.user@example.invalid", ActualObservedDataClass.PERSONAL_DATA),
        ("contractual confidential", ActualObservedDataClass.CONTRACTUAL_CONFIDENTIAL),
        ("api_key=synthetic-placeholder", ActualObservedDataClass.CREDENTIAL_LIKE),
        ("highly restricted", ActualObservedDataClass.HIGHLY_RESTRICTED),
    ),
)
def test_sensitive_classes_are_rejected(text, expected, positive_evidence):
    result = classify(text, positive_evidence)
    assert result.observed_data_class is expected
    assert expected in result.sensitive_classes
    assert result.positive_evidence_verified
    assert not result.actual_content_verified
    assert not result.approved_internal_low


@pytest.mark.parametrize(
    "content,rule_id",
    (
        (b"", "empty-content"),
        (b"classification_unknown", "unknown-classification-marker"),
        (b"synthetic\x00note", "unsupported-control-character"),
        (b"12345678901234567890", "numeric-only-candidate"),
        ("社外秘の新規案件情報です".encode("utf-8"), "unknown-sensitive-wording"),
        (b"ZXCVBNMASDFGHJKLQWER", "opaque-code-only-content"),
        (b"\xff\xfe", "non-utf8-content"),
    ),
)
def test_unknown_or_ambiguous_inputs_fail_closed(
    content, rule_id, positive_evidence
):
    result = classify_actual_content(
        content,
        positive_evidence=positive_evidence,
    )
    assert result.ambiguous
    assert rule_id in result.matched_rule_ids
    assert result.observed_data_class in {
        ActualObservedDataClass.UNKNOWN,
        ActualObservedDataClass.AMBIGUOUS,
    }
    assert not result.approved_internal_low


def test_new_credential_shape_not_limited_to_legacy_regex_is_rejected(
    positive_evidence,
):
    result = classify("widget_prod_8vN2Pq7Lm4Rx9Z", positive_evidence)
    assert result.observed_data_class is ActualObservedDataClass.CREDENTIAL_LIKE
    assert "generic-credential-token-shape" in result.matched_rule_ids
    assert not result.approved_internal_low


def test_multiple_sensitive_classes_are_ambiguous(positive_evidence):
    result = classify(
        "api_key=synthetic-placeholder personal_data",
        positive_evidence,
    )
    assert result.observed_data_class is ActualObservedDataClass.AMBIGUOUS
    assert result.ambiguous
    assert len(result.sensitive_classes) == 2


def test_positive_attestation_with_mismatched_actual_result_is_rejected(
    positive_evidence,
):
    result = classify(
        "Synthetic contact synthetic.user@example.invalid",
        positive_evidence,
    )
    assert result.expected_data_class is ActualObservedDataClass.INTERNAL_LOW
    assert result.observed_data_class is ActualObservedDataClass.PERSONAL_DATA
    assert "expected-classification-mismatch" in result.matched_rule_ids
    assert not result.approved_internal_low


def test_nested_forged_expected_classification_is_rejected(positive_evidence):
    object.__setattr__(
        positive_evidence.target_selection,
        "expected_classification_digest",
        digest("forged-expected-classification"),
    )
    result = classify(INTERNAL_LOW_TEXT, positive_evidence)
    assert not result.positive_evidence_verified
    assert result.observed_data_class is ActualObservedDataClass.UNKNOWN
    assert not result.approved_internal_low


def test_consistently_resealed_non_internal_low_policy_is_rejected(
    positive_evidence,
):
    policy = positive_evidence.classification_policy
    object.__setattr__(
        policy,
        "allowed_data_classes",
        (RealDataClass.INTERNAL_RESTRICTED,),
    )
    object.__setattr__(policy, "canonical_digest", digest(policy.canonical_json()))
    object.__setattr__(
        positive_evidence.selector,
        "classification_digest",
        policy.canonical_digest,
    )
    object.__setattr__(
        positive_evidence.selector,
        "canonical_digest",
        digest(positive_evidence.selector.canonical_json()),
    )
    object.__setattr__(
        positive_evidence.target_selection,
        "approved_selector_digest",
        positive_evidence.selector.canonical_digest,
    )
    object.__setattr__(
        positive_evidence.target_selection,
        "expected_classification_digest",
        policy.canonical_digest,
    )
    object.__setattr__(
        positive_evidence.target_selection,
        "canonical_digest",
        digest(positive_evidence.target_selection.canonical_json()),
    )
    object.__setattr__(
        positive_evidence.authorization_record,
        "selector_digest",
        positive_evidence.selector.canonical_digest,
    )
    object.__setattr__(
        positive_evidence.authorization_record,
        "canonical_digest",
        digest(positive_evidence.authorization_record.canonical_json()),
    )
    object.__setattr__(
        positive_evidence.approved_one_shot_trial,
        "access_authorization_record_digest",
        positive_evidence.authorization_record.canonical_digest,
    )
    object.__setattr__(
        positive_evidence.approved_one_shot_trial,
        "target_selection_digest",
        positive_evidence.target_selection.canonical_digest,
    )
    object.__setattr__(
        positive_evidence.approved_one_shot_trial,
        "canonical_digest",
        digest(positive_evidence.approved_one_shot_trial.canonical_json()),
    )
    object.__setattr__(
        positive_evidence,
        "canonical_digest",
        digest(positive_evidence.canonical_json()),
    )
    result = classify(INTERNAL_LOW_TEXT, positive_evidence)
    assert not result.positive_evidence_verified
    assert not result.approved_internal_low


def test_raw_text_is_absent_from_repr_and_canonical_metadata(positive_evidence):
    marker = "synthetic-marker-must-not-appear"
    result = classify(marker, positive_evidence)
    assert repr(result) == "ActualContentClassification(<safe>)"
    assert marker not in result.canonical_json()
    assert repr(positive_evidence) == "PositiveInternalLowEvidence(<safe>)"


def test_forged_classification_is_not_canonical(positive_evidence):
    result = classify(INTERNAL_LOW_TEXT, positive_evidence)
    object.__setattr__(
        result,
        "observed_data_class",
        ActualObservedDataClass.CREDENTIAL_LIKE,
    )
    assert not canonical_object_valid(result)


def test_caller_supplied_policy_digest_is_not_an_authority():
    with pytest.raises(TypeError):
        classify_actual_content(
            b"synthetic",
            policy_digest=digest("caller-supplied-policy"),
        )


def test_canonical_digest_changes_with_actual_content(positive_evidence):
    first = classify(INTERNAL_LOW_TEXT, positive_evidence)
    changed = classify(
        "Synthetic internal low alternate calibration note.",
        positive_evidence,
    )
    assert changed.canonical_digest != first.canonical_digest
    assert changed.content_verification_digest != first.content_verification_digest
