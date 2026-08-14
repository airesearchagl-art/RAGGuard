from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.local_rag_integration import *
from ragguard.storage_adapter import digest


NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)
D = digest("policy")


def manifest():
    return LocalRAGIntegrationManifest("controlled-rag", "v0.22", D, D, D, D, D, D, D, D, D,
                                       IntegrationDataClass.SYNTHETIC_ONLY)


def fixture():
    return SyntheticConfidentialFixture("fixture-001", (
        (SensitiveClass.CUSTOMER_NAME, "Synthetic Customer Alpha"),
        (SensitiveClass.PROJECT_NUMBER, "SYN-PROJECT-0001"),
        (SensitiveClass.CONTRACT, "Synthetic Contract Tier"),
        (SensitiveClass.PERSONAL, "Synthetic Person One"),
        (SensitiveClass.EMAIL, "fixture.one@example.invalid"),
        (SensitiveClass.PHONE, "+0-000-000-0000"),
        (SensitiveClass.INTERNAL_CODE, "SYN-INTERNAL-001"),
        (SensitiveClass.CREDENTIAL_LIKE, "api_key=SYNTHETIC-NOT-A-CREDENTIAL"),
    ), NOW, NOW + timedelta(days=1))


def plan(m):
    stages = tuple(DataFlowStageContract(stage, D, D,
        (IntegrationDataClass.SYNTHETIC_ONLY,), ("real_customer_data",),
        PersistenceClass.MEMORY_TEST_ONLY if stage is RAGStage.VECTOR_WRITE else PersistenceClass.NONE,
        LoggingClass.DIGEST_AND_REASON_ONLY, ExternalIOClass.PROHIBITED) for stage in RAGStage)
    return LocalRAGDataFlowPlan("plan-001", m.canonical_digest, stages)


def passed_chain():
    m, f = manifest(), fixture()
    p = plan(m)
    text, tr = transform_fixture(f, D)
    chunk = ApprovedChunk("chunk-001", text, tr.canonical_digest)
    store = TestOnlyVectorStore()
    assert store.write(chunk, tr)
    gates = tuple(evaluate_stage_gate(stage=stage, candidate_digest=D,
        detected_classes=tuple(kind for kind, _ in f.fields), transformed=True,
        blocked=False, evaluated_at=NOW) for stage in RAGStage)
    embedding = evaluate_embedding_boundary(text, tr)
    retrieval = evaluate_retrieval_boundary(store.retrieve(chunk.chunk_id), tr)
    prompt = evaluate_prompt_boundary((chunk,), {"state": "approved"})
    logging = evaluate_logging_cache_boundary({"candidate_digest": chunk.canonical_digest,
                                                "reason_code": "approved_masked_only"})
    receipt = issue_passed_receipt(manifest=m, plan=p, fixture=f, stage_results=gates,
        masking=tr, embedding=embedding, retrieval=retrieval, prompt=prompt, logging=logging,
        counters=ExternalIOCounters(), executed_at=NOW)
    return m, f, p, tr, chunk, store, receipt


def test_full_safe_controlled_flow_passes_without_side_effects():
    _, f, _, tr, chunk, store, receipt = passed_chain()
    assert receipt.result is IntegrationResult.PASSED
    assert store.write_count == 1 and store.rejected_write_count == 0
    assert store.retrieve(chunk.chunk_id) == chunk
    combined = repr(tr) + repr(receipt) + tr.canonical_json() + receipt.canonical_json()
    assert all(value not in combined for _, value in f.fields)
    assert ExternalIOCounters().all_zero


def test_raw_or_blocked_content_never_reaches_vector_store():
    _, f, _, tr, _, store, _ = passed_chain()
    raw = "\n".join(value for _, value in f.fields)
    with pytest.raises(LocalRAGIntegrationError):
        ApprovedChunk("raw-chunk", raw, tr.canonical_digest)
    forged = ApprovedChunk("wrong-chunk", "safe transformed text", tr.canonical_digest)
    assert not store.write(forged, tr)
    assert store.rejected_write_count == 1


def test_blocked_replaced_revoked_and_credential_chunks_are_rejected():
    _, _, _, tr, chunk, store, _ = passed_chain()
    for lifecycle in (ChunkLifecycle.REPLACED, ChunkLifecycle.REVOKED):
        stale = replace(chunk, chunk_id=f"chunk-{lifecycle.value}", lifecycle=lifecycle)
        assert not store.write(stale, tr)
    with pytest.raises(LocalRAGIntegrationError):
        ApprovedChunk("credential", "token=not-allowed", tr.canonical_digest)


def test_passed_receipt_cannot_be_forged_by_public_constructor():
    _, f, p, tr, _, _, receipt = passed_chain()
    with pytest.raises(LocalRAGIntegrationError):
        LocalRAGIntegrationReceipt(receipt.integration_manifest_digest, p.canonical_digest,
            f.canonical_digest, receipt.stage_result_digests, tr.canonical_digest,
            receipt.embedding_boundary_digest, receipt.retrieval_boundary_digest,
            receipt.prompt_boundary_digest, receipt.logging_boundary_digest, NOW,
            IntegrationResult.PASSED)
    object.__setattr__(receipt, "logging_boundary_digest", D)
    roles = IntegrationRoleContext("operator", "reviewer", "approver")
    review = IntegrationReview(receipt.canonical_digest, "reviewer", ReviewResult.APPROVED,
                               NOW + timedelta(minutes=1))
    approval = IntegrationApproval(receipt.canonical_digest, review.canonical_digest, "approver",
        ReviewResult.APPROVED, NOW + timedelta(minutes=2))
    decision = evaluate_trial_eligibility(receipt, review, approval, roles,
                                           evaluation_time=NOW + timedelta(minutes=3))
    assert decision.state is TrialEligibilityState.INELIGIBLE
    assert not decision.real_data_approved and not decision.real_data_use_authorized


def test_independent_roles_and_review_eligibility_are_not_real_data_approval():
    *_, receipt = passed_chain()
    with pytest.raises(LocalRAGIntegrationError):
        IntegrationRoleContext("same", "same", "approver")
    roles = IntegrationRoleContext("operator", "reviewer", "approver")
    review = IntegrationReview(receipt.canonical_digest, "reviewer", ReviewResult.APPROVED,
                               NOW + timedelta(minutes=1))
    approval = IntegrationApproval(receipt.canonical_digest, review.canonical_digest, "approver",
        ReviewResult.APPROVED, NOW + timedelta(minutes=2))
    decision = evaluate_trial_eligibility(receipt, review, approval, roles,
                                           evaluation_time=NOW + timedelta(minutes=3))
    assert decision.state is TrialEligibilityState.ELIGIBLE_FOR_REAL_DATA_TRIAL_REVIEW
    assert decision.real_data_approved is decision.real_data_use_authorized is False


def test_failed_boundary_or_nonzero_external_io_prevents_passed_receipt():
    m, f = manifest(), fixture()
    p = plan(m)
    _, tr = transform_fixture(f, D)
    gates = (StageGateDecision(RAGStage.INPUT_CANDIDATE, StageGateState.BLOCKED, D,
                               ("raw_confidential",), NOW),)
    rejected = BoundaryResult("embedding", False, D, D, ("raw_prohibited_field",))
    accepted = BoundaryResult("safe-boundary", True, D, D, ("approved_masked_only",))
    receipt = issue_passed_receipt(manifest=m, plan=p, fixture=f, stage_results=gates,
        masking=tr, embedding=rejected, retrieval=accepted, prompt=accepted, logging=accepted,
        counters=ExternalIOCounters(http_count=1), executed_at=NOW)
    assert receipt.result is IntegrationResult.FAILED
    assert receipt.production_safe is False if hasattr(receipt, "production_safe") else True


def test_stage_prompt_logging_and_embedding_attacks_fail_closed():
    _, f, _, tr, chunk, _, _ = passed_chain()
    raw = "\n".join(value for _, value in f.fields)
    assert evaluate_stage_gate(stage=RAGStage.INPUT_CANDIDATE, candidate_digest=digest(raw),
        detected_classes=tuple(kind for kind, _ in f.fields), transformed=False,
        blocked=False, evaluated_at=NOW).state is StageGateState.NEEDS_MASKING
    assert not evaluate_embedding_boundary(raw, tr).accepted
    assert not evaluate_prompt_boundary((chunk,), {"instruction": "ignore_previous"}).accepted
    assert not evaluate_logging_cache_boundary({"reason_code": "token=unsafe"}).accepted


def test_stale_fixture_future_stage_and_forged_transformation_fail_receipt():
    m, f, p, tr, chunk, store, _ = passed_chain()
    gates = tuple(evaluate_stage_gate(stage=stage, candidate_digest=D,
        detected_classes=(), transformed=True, blocked=False,
        evaluated_at=NOW + timedelta(hours=2)) for stage in RAGStage)
    embedding = evaluate_embedding_boundary(chunk.content, tr)
    retrieval = evaluate_retrieval_boundary(store.retrieve(chunk.chunk_id), tr)
    prompt = evaluate_prompt_boundary((chunk,), {"state": "approved"})
    logging = evaluate_logging_cache_boundary({"candidate_digest": chunk.canonical_digest})
    object.__setattr__(tr, "source_digest", D)
    receipt = issue_passed_receipt(manifest=m, plan=p, fixture=f, stage_results=gates,
        masking=tr, embedding=embedding, retrieval=retrieval, prompt=prompt, logging=logging,
        counters=ExternalIOCounters(), executed_at=NOW + timedelta(hours=1))
    assert receipt.result is IntegrationResult.FAILED
