from pathlib import Path


ROOT = Path(__file__).parents[1]
DESIGN = ROOT / "docs" / "PRODUCTION_ADMISSION_DESIGN_V0.11.md"


def _design() -> str:
    return DESIGN.read_text(encoding="utf-8")


def test_v011_design_contains_required_deliverables() -> None:
    design = _design()
    for heading in (
        "## Production admission state transition",
        "## Component responsibility",
        "## Manual validation plan schema",
        "## Required manual cases",
        "## Manual validation evidence schema",
        "## Evidence review and approval decision",
        "## Registry admission",
        "## Revalidation triggers",
        "## Failure matrix",
        "## Security boundary",
        "## v0.11 Phase A-F roadmap",
        "## Approval checklist before any real-product validation",
        "## Unresolved design questions",
    ):
        assert heading in design


def test_v011_design_requires_every_manual_case() -> None:
    design = _design()
    required_cases = (
        "health",
        "capabilities",
        "required_capabilities",
        "request_mapping",
        "response_mapping",
        "pass_query",
        "warning_query",
        "fail_query",
        "malformed_response_rejection",
        "timeout_rejection",
        "oversized_response_rejection",
        "unsafe_source_rejection",
        "duplicate_id_rejection",
        "rank_gap_rejection",
        "query_id_echo",
        "close_cleanup",
        "report_non_disclosure",
        "product_version_exact_or_range_validation",
        "unsupported_product_version_rejection",
        "approval_denial_before_transport",
        "credential_non_disclosure",
        "endpoint_non_disclosure",
    )
    for case_id in required_cases:
        assert f"`{case_id}`" in design


def test_v011_design_preserves_decision_and_registry_boundaries() -> None:
    design = _design()
    for required in (
        "`approved`",
        "`approved_with_restrictions`",
        "`rejected`",
        "`needs_revalidation`",
        "`manually_validated`",
        "No step may be skipped",
        "Synthetic evidence remains necessary but is never manual evidence",
        "reviewer and approver are always distinct",
        "No discovery, fallback, nearest-version selection, schema inference",
        "No production profile or real production-registry entry",
        "No manual validation is executed or represented as completed",
    ):
        assert required in design


def test_v011_transition_gates_separate_review_approval_and_admission() -> None:
    design = _design()
    normalized = " ".join(design.split())
    for transition in (
        "| `manual_validation_executed` | `evidence_reviewed` | "
        "Independent evidence reviewer validates the evidence and creates "
        "an immutable attestation |",
        "| `evidence_reviewed` | `approval_decided` | "
        "A distinct approver explicitly selects one decision |",
        "| `approval_decided` | `production_registry_admitted` | "
        "Decision is `approved` or `approved_with_restrictions` and every "
        "admission gate passes |",
    ):
        assert transition in design

    assert "Approval is forbidden before `evidence_reviewed`." in normalized
    assert (
        "`rejected` and `needs_revalidation` are valid decisions that complete "
        "the `approval_decided` state"
    ) in normalized
    assert (
        "Only `approved` and `approved_with_restrictions` make the record "
        "an admission candidate"
    ) in normalized


def test_v011_pre_admission_registry_status_is_requested_not_preexisting() -> None:
    design = _design()
    assert "Before admission, no registry entry or registry status exists." in design
    assert (
        "Exact requested registry kind `production` and requested initial "
        "status `active`."
    ) in design
    assert "Only a successful explicit registry write creates the entry" in design


def test_v011_design_defines_all_six_phases_without_runtime_expansion() -> None:
    design = _design()
    for phase in ("Phase A", "Phase B", "Phase C", "Phase D", "Phase E", "Phase F"):
        assert f"### {phase}:" in design
    for boundary in (
        "No real-product, localhost, external, private-LAN, or cloud connection.",
        "No credentials, authentication material, real documents, "
        "customer data, or production data.",
        "No external API, product-specific adapter",
        "No discovery, fallback, nearest-version selection, schema inference",
    ):
        assert boundary in design


def test_v011_design_is_linked_from_project_documents() -> None:
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    design_notes = (ROOT / "docs" / "DESIGN_NOTES.md").read_text(encoding="utf-8")
    assert "v0.11 production admission" in roadmap.lower()
    assert "v0.11 production admission design" in changelog.lower()
    assert "PRODUCTION_ADMISSION_DESIGN_V0.11.md" in design_notes
