import pytest

from actual_trial_v030_support import actual_execution_chain
from ragguard.actual_content_classification import classify_actual_content
from ragguard.actual_content_masking import (
    ActualContentMaskingError,
    mask_actual_content,
)
from ragguard.storage_adapter import canonical_object_valid, digest


RAW = b"Synthetic internal low calibration note for controlled verification."
MASKING_POLICY = digest("actual-masking-policy-v030")


@pytest.fixture
def positive_evidence(tmp_path):
    call = actual_execution_chain(tmp_path)
    try:
        yield call["positive_classification_evidence"]
    finally:
        call["provision"].capability.close()


def classification(positive_evidence, raw=RAW):
    return classify_actual_content(
        raw,
        positive_evidence=positive_evidence,
    )


def test_actual_masking_is_derived_from_raw_content_and_verified(
    positive_evidence,
):
    content_classification = classification(positive_evidence)
    outcome = mask_actual_content(
        RAW,
        classification=content_classification,
        masking_policy_digest=MASKING_POLICY,
    )
    evidence = outcome.evidence
    assert evidence.verified
    assert not evidence.prohibited_residue_detected
    assert evidence.raw_content_digest == content_classification.raw_content_digest
    assert evidence.transformed_content_digest == digest(outcome.transformed_content)
    assert evidence.raw_content_digest != evidence.transformed_content_digest
    assert canonical_object_valid(evidence)


def test_transformed_content_contains_no_raw_tokens(positive_evidence):
    outcome = mask_actual_content(
        RAW,
        classification=classification(positive_evidence),
        masking_policy_digest=MASKING_POLICY,
    )
    transformed = outcome.transformed_content
    assert all(token not in transformed for token in RAW.decode().split())
    assert all(token.startswith("tok_") for token in transformed.split())


def test_masking_is_deterministic_for_the_same_raw_content_and_policy(
    positive_evidence,
):
    first = mask_actual_content(
        RAW,
        classification=classification(positive_evidence),
        masking_policy_digest=MASKING_POLICY,
    )
    second = mask_actual_content(
        RAW,
        classification=classification(positive_evidence),
        masking_policy_digest=MASKING_POLICY,
    )
    assert first.evidence == second.evidence
    assert first.transformed_content == second.transformed_content


def test_masking_rejects_non_internal_low_classification(positive_evidence):
    raw = b"api_key=synthetic-placeholder"
    with pytest.raises(ActualContentMaskingError, match="masking_input_invalid"):
        mask_actual_content(
            raw,
            classification=classification(positive_evidence, raw),
            masking_policy_digest=MASKING_POLICY,
        )


def test_masking_rejects_raw_content_mismatch(positive_evidence):
    with pytest.raises(
        ActualContentMaskingError, match="masking_raw_binding_mismatch"
    ):
        mask_actual_content(
            b"Different synthetic content.",
            classification=classification(positive_evidence),
            masking_policy_digest=MASKING_POLICY,
        )


def test_masking_rejects_empty_content(positive_evidence):
    with pytest.raises(ActualContentMaskingError):
        mask_actual_content(
            b"",
            classification=classification(positive_evidence, b""),
            masking_policy_digest=MASKING_POLICY,
        )


def test_masking_repr_never_exposes_transformed_or_raw_content(positive_evidence):
    outcome = mask_actual_content(
        RAW,
        classification=classification(positive_evidence),
        masking_policy_digest=MASKING_POLICY,
    )
    assert repr(outcome) == "ActualMaskingOutcome(<safe>)"
    assert repr(outcome.evidence) == "ActualContentMasking(<safe>)"
    assert RAW.decode() not in outcome.evidence.canonical_json()


def test_masking_policy_is_canonical_bound(positive_evidence):
    first = mask_actual_content(
        RAW,
        classification=classification(positive_evidence),
        masking_policy_digest=MASKING_POLICY,
    )
    second = mask_actual_content(
        RAW,
        classification=classification(positive_evidence),
        masking_policy_digest=digest("different-masking-policy"),
    )
    assert first.evidence.canonical_digest != second.evidence.canonical_digest
