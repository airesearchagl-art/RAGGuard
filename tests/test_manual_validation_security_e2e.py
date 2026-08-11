from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

from ragguard.manual_validation_execution import (
    ManualValidationExecutionErrorCategory,
    TestManualValidationChainStore,
)
from ragguard.production_authorization import (
    ProductionAuthorizationResult,
    evaluate_production_authorization,
)
from ragguard.production_boundary import (
    CompatibilityEvidenceKind,
    ManualValidationState,
    PersistenceState,
    RuntimeAuthorizationState,
    SecurityReviewState,
)
from tests.test_manual_validation_execution_contract import chain, plan
from tests.test_production_authorization_evaluator import request


ROOT = Path(__file__).resolve().parents[1]


def chain_digests() -> dict[str, object]:
    value = chain()
    assert value.review is not None and value.approval is not None
    return {
        "manual_validation_state": ManualValidationState.APPROVED,
        "compatibility_evidence_kind": CompatibilityEvidenceKind.CONTROLLED_MANUAL,
        "manual_validation_execution_digest": value.execution_record.canonical_digest,
        "manual_validation_evidence_digest": value.evidence.canonical_digest,
        "manual_validation_review_digest": value.review.canonical_digest,
        "manual_validation_approval_digest": value.approval.canonical_digest,
    }


def test_full_offline_chain_crosses_only_manual_validation_gate() -> None:
    candidate = evaluate_production_authorization(request(**chain_digests()))
    assert candidate.result is ProductionAuthorizationResult.NEEDS_SECURITY_REVIEW
    assert candidate.runtime_activation_count == 0


def test_full_chain_can_reach_review_candidate_but_not_activation() -> None:
    values = chain_digests()
    values.update(
        security_review_state=SecurityReviewState.APPROVED,
        persistence_state=PersistenceState.PRODUCTION_READY,
        runtime_authorization_state=RuntimeAuthorizationState.CANDIDATE_ONLY,
    )
    candidate = evaluate_production_authorization(request(**values))
    assert candidate.result is ProductionAuthorizationResult.ELIGIBLE_FOR_AUTHORIZATION_REVIEW
    assert candidate.runtime_activation_count == 0


def test_approved_claim_without_chain_digests_is_not_sufficient() -> None:
    candidate = evaluate_production_authorization(
        request(
            manual_validation_state=ManualValidationState.APPROVED,
            compatibility_evidence_kind=CompatibilityEvidenceKind.CONTROLLED_MANUAL,
            manual_validation_execution_digest=None,
            manual_validation_evidence_digest=None,
            manual_validation_review_digest=None,
            manual_validation_approval_digest=None,
        )
    )
    assert candidate.result is ProductionAuthorizationResult.NEEDS_MANUAL_VALIDATION


def test_partial_chain_is_rejected_at_contract_construction() -> None:
    evidence = request().evidence
    from ragguard.production_boundary import ProductionBoundaryError
    try:
        replace(
            evidence,
            manual_validation_execution_digest="sha256:" + "1" * 64,
            manual_validation_evidence_digest=None,
            manual_validation_review_digest=None,
            manual_validation_approval_digest=None,
        )
    except ProductionBoundaryError:
        pass
    else:
        raise AssertionError("partial manual-validation digest chain was accepted")


def test_forged_approval_is_rejected_without_consuming_replay_state() -> None:
    value = chain()
    assert value.approval is not None
    store = TestManualValidationChainStore()
    forged = replace(
        value,
        approval=replace(value.approval, evidence_digest="sha256:" + "9" * 64),
    )
    denied = store.commit(forged, plan=plan(), evaluation_time=value.approval.approved_at)
    assert not denied.applied
    assert store.committed_chain_count == 0
    assert store.commit(value, plan=plan(), evaluation_time=value.approval.approved_at).applied


def test_successful_chain_replay_is_rejected() -> None:
    value = chain()
    assert value.approval is not None
    store = TestManualValidationChainStore()
    assert store.commit(value, plan=plan(), evaluation_time=value.approval.approved_at).applied
    replay = store.commit(value, plan=plan(), evaluation_time=value.approval.approved_at)
    assert replay.reason_categories == (ManualValidationExecutionErrorCategory.REPLAY,)


def test_module_has_no_network_filesystem_database_or_subprocess_imports() -> None:
    source = (ROOT / "src/ragguard/manual_validation_execution.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {
        "pathlib", "sqlite3", "subprocess", "socket", "requests", "httpx",
        "urllib", "tempfile", "random", "uuid", "secrets",
    }


def test_denial_paths_have_zero_external_counts() -> None:
    value = chain()
    assert value.approval is not None
    store = TestManualValidationChainStore()
    result = store.commit(
        replace(value, approval=replace(value.approval, review_digest="sha256:" + "0" * 64)),
        plan=plan(),
        evaluation_time=value.approval.approved_at,
    )
    assert not result.applied
    assert (
        result.registry_write_count, result.mutation_count,
        result.persistence_write_count, result.filesystem_write_count,
        result.database_write_count, result.network_count, result.http_count,
        result.activation_count,
    ) == (0, 0, 0, 0, 0, 0, 0, 0)
