import pytest

from ragguard.actual_content_classification import classify_actual_content
from ragguard.actual_content_masking import (
    ActualContentMaskingError,
    mask_actual_content,
)
from ragguard.storage_adapter import canonical_object_valid, digest


RAW = b"Synthetic internal low calibration note for controlled verification."
CLASSIFICATION_POLICY = digest("actual-classification-policy-v030")
MASKING_POLICY = digest("actual-masking-policy-v030")


def classification(raw=RAW):
    return classify_actual_content(raw, policy_digest=CLASSIFICATION_POLICY)


def test_actual_masking_is_derived_from_raw_content_and_verified():
    outcome = mask_actual_content(
        RAW,
        classification=classification(),
        masking_policy_digest=MASKING_POLICY,
    )
    evidence = outcome.evidence
    assert evidence.verified
    assert not evidence.prohibited_residue_detected
    assert evidence.raw_content_digest == classification().raw_content_digest
    assert evidence.transformed_content_digest == digest(outcome.transformed_content)
    assert evidence.raw_content_digest != evidence.transformed_content_digest
    assert canonical_object_valid(evidence)


def test_transformed_content_contains_no_raw_tokens():
    outcome = mask_actual_content(
        RAW,
        classification=classification(),
        masking_policy_digest=MASKING_POLICY,
    )
    transformed = outcome.transformed_content
    assert all(token not in transformed for token in RAW.decode().split())
    assert all(token.startswith("tok_") for token in transformed.split())


def test_masking_is_deterministic_for_the_same_raw_content_and_policy():
    first = mask_actual_content(
        RAW,
        classification=classification(),
        masking_policy_digest=MASKING_POLICY,
    )
    second = mask_actual_content(
        RAW,
        classification=classification(),
        masking_policy_digest=MASKING_POLICY,
    )
    assert first.evidence == second.evidence
    assert first.transformed_content == second.transformed_content


def test_masking_rejects_non_internal_low_classification():
    raw = b"api_key=synthetic-placeholder"
    with pytest.raises(ActualContentMaskingError, match="masking_input_invalid"):
        mask_actual_content(
            raw,
            classification=classification(raw),
            masking_policy_digest=MASKING_POLICY,
        )


def test_masking_rejects_raw_content_mismatch():
    with pytest.raises(
        ActualContentMaskingError, match="masking_raw_binding_mismatch"
    ):
        mask_actual_content(
            b"Different synthetic content.",
            classification=classification(),
            masking_policy_digest=MASKING_POLICY,
        )


def test_masking_rejects_empty_content():
    with pytest.raises(ActualContentMaskingError):
        mask_actual_content(
            b"",
            classification=classification(b""),
            masking_policy_digest=MASKING_POLICY,
        )


def test_masking_repr_never_exposes_transformed_or_raw_content():
    outcome = mask_actual_content(
        RAW,
        classification=classification(),
        masking_policy_digest=MASKING_POLICY,
    )
    assert repr(outcome) == "ActualMaskingOutcome(<safe>)"
    assert repr(outcome.evidence) == "ActualContentMasking(<safe>)"
    assert RAW.decode() not in outcome.evidence.canonical_json()


def test_masking_policy_is_canonical_bound():
    first = mask_actual_content(
        RAW,
        classification=classification(),
        masking_policy_digest=MASKING_POLICY,
    )
    second = mask_actual_content(
        RAW,
        classification=classification(),
        masking_policy_digest=digest("different-masking-policy"),
    )
    assert first.evidence.canonical_digest != second.evidence.canonical_digest
