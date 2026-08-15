from dataclasses import fields, replace

import pytest

from ragguard.real_data_read_receipt import (
    PostReadClassificationResult,
    PostReadMaskingVerification,
    ReadExecutionResult,
    RealDataReadReceipt,
    RealDataReadReceiptError,
    VerifiedMaskedContentCandidate,
)
from ragguard.storage_adapter import canonical_object_valid, digest
from test_real_data_read_execution_contract import (
    CONTROLLED_FIXTURE,
    MASKED_FIXTURE,
    read_execution_chain,
)


def test_receipt_and_evidence_are_metadata_only_and_do_not_retain_raw_content():
    _, result, _, _ = read_execution_chain()
    contracts = (
        ReadExecutionResult,
        PostReadClassificationResult,
        PostReadMaskingVerification,
        RealDataReadReceipt,
        VerifiedMaskedContentCandidate,
    )
    forbidden = {
        "path",
        "filename",
        "directory",
        "raw",
        "raw_content",
        "content",
        "payload",
        "credential",
        "token",
    }
    for contract in contracts:
        names = {item.name for item in fields(contract)}
        assert "raw_content_digest" in names or names.isdisjoint({"raw_content"})
        assert names.isdisjoint(forbidden)
    serializations = (
        result.execution_result.canonical_json(),
        result.classification_result.canonical_json(),
        result.masking_verification.canonical_json(),
        result.receipt.canonical_json(),
        result.masked_candidate.canonical_json(),
    )
    assert all(CONTROLLED_FIXTURE not in item for item in serializations)
    assert all(MASKED_FIXTURE not in item for item in serializations)


def test_safe_repr_never_discloses_fixture_or_transformed_content():
    _, result, call, _ = read_execution_chain()
    values = (
        call["adapter"],
        result.execution_result,
        result.classification_result,
        result.masking_verification,
        result.receipt,
        result.masked_candidate,
    )
    for value in values:
        rendered = repr(value)
        assert "<safe>" in rendered
        assert CONTROLLED_FIXTURE not in rendered
        assert MASKED_FIXTURE not in rendered


def test_receipt_cannot_be_minted_or_replaced_through_public_constructor():
    _, result, _, _ = read_execution_chain()
    with pytest.raises(RealDataReadReceiptError, match="real_data_read_receipt_invalid"):
        replace(result.receipt)
    with pytest.raises(RealDataReadReceiptError, match="real_data_read_receipt_invalid"):
        RealDataReadReceipt(
            "forged-receipt",
            *(digest("forged") for _ in range(3)),
            "forged-operator",
            *(digest("forged") for _ in range(6)),
            result.receipt.issued_at,
            result.receipt.result,
        )


def test_operator_or_usage_digest_tampering_invalidates_canonical_receipt():
    _, result, _, _ = read_execution_chain()
    object.__setattr__(result.receipt, "operator_id", "forged-operator")
    assert not canonical_object_valid(result.receipt)

    _, second, _, _ = read_execution_chain()
    object.__setattr__(second.receipt, "usage_after_digest", digest("forged-usage"))
    assert not canonical_object_valid(second.receipt)


def test_receipt_and_masked_candidate_never_authorize_downstream_processing():
    _, result, _, _ = read_execution_chain()
    assert result.receipt.embedding_authorized is False
    assert result.receipt.persistence_authorized is False
    assert result.receipt.local_rag_full_processing_authorized is False
    candidate = result.masked_candidate
    assert candidate.embedding_authorized is False
    assert candidate.persistence_authorized is False
    assert candidate.unrestricted_retrieval_authorized is False
    assert candidate.prompt_input_authorized is False
    assert candidate.llm_input_authorized is False
    assert candidate.export_authorized is False


def test_raw_and_transformed_content_are_represented_only_by_distinct_digests():
    _, result, _, _ = read_execution_chain()
    assert result.execution_result.raw_content_digest == digest(CONTROLLED_FIXTURE)
    assert result.masking_verification.transformed_content_digest == digest(
        MASKED_FIXTURE
    )
    assert result.execution_result.raw_content_digest != (
        result.masking_verification.transformed_content_digest
    )
    assert result.receipt.transformed_content_digest == (
        result.masking_verification.transformed_content_digest
    )
