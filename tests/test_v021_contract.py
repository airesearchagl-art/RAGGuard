from __future__ import annotations

from pathlib import Path

import ragguard.storage_adapter as adapter
import ragguard.storage_adapter_attestation as attestation


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "APPROVED_STORAGE_ADAPTER_BOUNDARY_DESIGN_V0.21.md"
CHECKLIST = ROOT / "docs" / "RELEASE_CHECKLIST_V0.21.0.md"


def test_public_contract_has_no_execution_or_connection_api():
    forbidden = {"connect", "open", "write", "persist", "execute_transaction",
                 "create_connection", "activate", "generate_token", "get_credential"}
    public = set(adapter.__all__) if hasattr(adapter, "__all__") else {
        name for name in vars(adapter) if not name.startswith("_")}
    public |= {name for name in vars(attestation) if not name.startswith("_")}
    assert not public.intersection(forbidden)


def test_design_and_release_checklist_exist():
    assert DESIGN.is_file()
    assert CHECKLIST.is_file()


def test_design_preserves_candidate_review_authorization_boundaries():
    text = " ".join(DESIGN.read_text(encoding="utf-8").split()).lower()
    for phrase in (
        "candidate ≠ approved",
        "approved_for_write_authorization_review ≠ write_authorized",
        "write_authorized ≠ write_executed",
        "durable_write_completed ≠ runtime_active",
        "no automatic fallback",
        "no nearest-version selection",
        "no schema inference",
    ):
        assert phrase.lower() in text


def test_release_checklist_names_all_prohibited_real_side_effects():
    text = CHECKLIST.read_text(encoding="utf-8").lower()
    for phrase in ("filesystem", "db", "external storage", "network", "http",
                   "credential", "token", "production registry", "runtime activation"):
        assert phrase in text


def test_docs_use_review_state_not_execution_authority():
    texts = "\n".join((DESIGN.read_text(encoding="utf-8"),
                        CHECKLIST.read_text(encoding="utf-8"))).lower()
    assert "ready_for_write_authorization_review" in texts
    assert "approved_for_write_authorization_review" in texts
    assert "actual adapter operation is not implemented" in texts


def test_docs_require_object_backed_capability_conformance():
    text = " ".join(DESIGN.read_text(encoding="utf-8").split()).lower()
    assert "boolean claims are not trusted independently" in text
    assert "exact-binds all ten actual result objects" in text
    assert "caller-supplied matching digest strings are not a trust anchor" in text


def test_cli_and_report_compatibility_statements_are_retained():
    checklist = CHECKLIST.read_text(encoding="utf-8").lower()
    assert "cli" in checklist
    assert "compatibility" in checklist
