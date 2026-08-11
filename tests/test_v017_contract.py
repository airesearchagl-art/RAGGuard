from __future__ import annotations

import ast
from pathlib import Path

import ragguard
from ragguard.production_authorization import ProductionAuthorizationResult
from ragguard.production_equivalence import (
    EquivalenceAssessmentResult,
    EquivalenceEvidenceSourceKind,
    ProductionEquivalentState,
)


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_contract_separates_all_states() -> None:
    assert EquivalenceEvidenceSourceKind.SYNTHETIC.value != "production_equivalent"
    assert ProductionEquivalentState.APPROVED.value == "approved"
    assert (
        EquivalenceAssessmentResult.ELIGIBLE_FOR_EQUIVALENCE_REVIEW.value
        != "approved_for_production"
    )
    assert ProductionAuthorizationResult.ELIGIBLE_FOR_AUTHORIZATION_REVIEW.value != "active"


def test_public_contract_exports_are_available() -> None:
    required = {
        "ProductionEquivalenceAssessmentRequest",
        "EquivalenceCriteria",
        "EquivalenceEvidenceDescriptor",
        "EnvironmentEquivalenceContract",
        "ConfigurationEquivalence",
        "ProductBehaviorEquivalence",
        "EquivalenceAssessment",
        "EquivalenceReview",
        "EquivalenceApproval",
        "TestEquivalenceAttestationStore",
        "evaluate_production_equivalence",
    }
    assert required <= set(ragguard.__all__)


def test_design_states_recognition_not_execution_or_activation() -> None:
    design = read("docs/PRODUCTION_EQUIVALENT_EVIDENCE_DESIGN_V0.17.md")
    for text in (
        "does not perform production validation",
        "not real-world compatibility evidence",
        "eligible_for_equivalence_review",
        "Equivalence approval is not production approval",
        "ready_for_activation_commit != active",
    ):
        assert text in design


def test_release_checklist_preserves_security_boundary() -> None:
    checklist = read("docs/RELEASE_CHECKLIST_V0.17.0.md")
    for text in (
        "Synthetic or controlled manual evidence is not production-equivalent",
        "No real product, endpoint, data, credential, persistence, registry write, or activation",
        "CLI exit codes and report top-level schema remain unchanged",
        "annotated `v0.17.0` tag",
    ):
        assert text in checklist


def test_docs_do_not_claim_real_validation_or_activation() -> None:
    combined = "\n".join(
        read(path)
        for path in (
            "README.md",
            "ROADMAP.md",
            "CHANGELOG.md",
            "docs/USAGE.md",
            "docs/DESIGN_NOTES.md",
        )
    )
    assert "real production validation was performed" not in combined
    assert "production runtime is active" not in combined
    assert "v0.17 adds runtime activation" not in combined


def test_v017_modules_import_no_io_or_transport_surfaces() -> None:
    forbidden = {
        "asyncio",
        "http",
        "os",
        "pathlib",
        "random",
        "requests",
        "socket",
        "sqlite3",
        "subprocess",
        "urllib",
        "uuid",
    }
    for path in (
        ROOT / "src/ragguard/production_equivalence.py",
        ROOT / "src/ragguard/equivalence_attestation.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert imports.isdisjoint(forbidden)


def test_no_workflow_or_runtime_surface_is_added() -> None:
    assert not (ROOT / "src/ragguard/production_activation.py").exists()
    assert not (ROOT / "src/ragguard/production_transport.py").exists()
    assert "node20" not in read("docs/RELEASE_CHECKLIST_V0.17.0.md").lower()
