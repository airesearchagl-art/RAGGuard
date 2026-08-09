from pathlib import Path

from ragguard.production_authorization import ProductionAuthorizationResult


ROOT = Path(__file__).parents[1]


def test_candidate_results_do_not_include_activation() -> None:
    values = {value.value for value in ProductionAuthorizationResult}
    assert not values.intersection({"authorized", "active", "production_enabled"})


def test_design_states_candidate_is_not_authorization() -> None:
    text = (ROOT / "docs" / "PRODUCTION_BOUNDARY_DESIGN_V0.14.md").read_text(encoding="utf-8")
    assert "eligible_for_authorization_review` is neither `authorized` nor `active`" in text
    assert "No `ProductionAuthorizationActivation` API exists" in text


def test_no_workflow_change_is_required_by_contract() -> None:
    text = (ROOT / "docs" / "PRODUCTION_BOUNDARY_DESIGN_V0.14.md").read_text(encoding="utf-8")
    assert "Workflow and Node runtime warning maintenance are out of scope" in text


def test_release_checklist_preserves_non_production_boundary() -> None:
    text = (ROOT / "docs" / "RELEASE_CHECKLIST_V0.14.0.md").read_text(encoding="utf-8")
    assert "No manual validation was performed" in text
    assert "No persistence, runtime activation, token, credential, transport, or HTTP path" in text


def test_public_docs_do_not_claim_activation() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "This is not production activation" in text
    assert "eligible_for_authorization_review" in text
