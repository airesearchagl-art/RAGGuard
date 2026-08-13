from pathlib import Path

from ragguard.real_world_evidence import ValidationRecordState
from ragguard.real_world_validation import ExecutionResult, ValidationDecisionState


ROOT = Path(__file__).parents[1]


def test_release_boundaries_are_explicit_in_design():
    text = (ROOT / "docs" / "REAL_WORLD_VALIDATION_EXECUTION_DESIGN_V0.20.md").read_text("utf-8")
    for phrase in (
        "validation approved != production authorized",
        "execution passed != production-equivalent approved",
        "evidence approved != active",
        "controlled fixture only",
        "no runtime activation",
    ):
        assert phrase in text


def test_state_enums_do_not_claim_runtime_or_production_authorization():
    values = {item.value for item in ValidationDecisionState} | {item.value for item in ValidationRecordState}
    assert not values & {"active", "production_authorized", "production_validated", "runtime_active"}
    assert ExecutionResult.PASSED.value == "passed"


def test_cli_and_report_contracts_are_not_redefined_by_v020_modules():
    validation = (ROOT / "src" / "ragguard" / "real_world_validation.py").read_text("utf-8")
    evidence = (ROOT / "src" / "ragguard" / "real_world_evidence.py").read_text("utf-8")
    assert "argparse" not in validation + evidence
    assert "click" not in validation + evidence
    assert "import requests" not in validation + evidence
    assert "from requests" not in validation + evidence


def test_release_checklist_preserves_no_side_effect_boundary():
    text = (ROOT / "docs" / "RELEASE_CHECKLIST_V0.20.0.md").read_text("utf-8")
    for phrase in ("filesystem", "database", "external storage", "production registry", "runtime activation"):
        assert phrase in text
