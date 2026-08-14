from pathlib import Path

import ragguard.local_rag_integration as integration


ROOT = Path(__file__).resolve().parents[1]


def test_docs_exist_and_preserve_release_contract():
    design = (ROOT / "docs" / "LOCAL_RAG_INTEGRATION_VALIDATION_DESIGN_V0.22.md")
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST_V0.22.0.md")
    assert design.is_file() and checklist.is_file()
    text = (design.read_text(encoding="utf-8") + checklist.read_text(encoding="utf-8")).lower()
    for phrase in ("controlled integration passed != real data approved",
                   "real-data trial review eligible != real-data use authorized",
                   "local rag integration != production runtime activation",
                   "no actual persistent vector db", "external network count = 0"):
        assert phrase in text


def test_public_api_has_no_external_execution_surface():
    forbidden = {"connect", "send_http", "call_embedding_api", "write_database",
                 "activate", "get_credential", "generate_token"}
    assert not forbidden.intersection(integration.__all__)
