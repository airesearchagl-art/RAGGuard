from __future__ import annotations

import json
from pathlib import Path

from ragguard.cli import main
from ragguard.masked_document_checker import check_path, exit_code_for_status


FIXTURES = Path(__file__).parent / "fixtures"


def test_safe_fixture_passes(tmp_path: Path) -> None:
    code = main(["check-mask", "--input", str(FIXTURES / "safe"), "--output", str(tmp_path)])
    result = json.loads((tmp_path / "masked_check_report.json").read_text(encoding="utf-8"))
    assert code == 0
    assert result["status"] == "PASS"


def test_warning_fixture_warns(tmp_path: Path) -> None:
    code = main(["check-mask", "--input", str(FIXTURES / "warning"), "--output", str(tmp_path)])
    result = json.loads((tmp_path / "masked_check_report.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["status"] == "WARNING"


def test_fail_fixture_fails(tmp_path: Path) -> None:
    code = main(["check-mask", "--input", str(FIXTURES / "fail"), "--output", str(tmp_path)])
    result = json.loads((tmp_path / "masked_check_report.json").read_text(encoding="utf-8"))
    assert code == 2
    assert result["status"] == "FAIL"


def test_single_markdown_file_can_be_checked() -> None:
    result = check_path(FIXTURES / "fail" / "root.md")
    assert result["checked_file_count"] == 1
    assert result["status"] == "FAIL"


def test_markdown_folder_is_checked_recursively() -> None:
    result = check_path(FIXTURES / "fail")
    checked = set(result["checked_files"])
    assert "root.md" in checked
    assert str(Path("nested") / "details.md") in checked


def test_json_and_markdown_reports_are_generated(tmp_path: Path) -> None:
    code = main(["check-mask", "--input", str(FIXTURES / "safe"), "--output", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "masked_check_report.json").exists()
    assert (tmp_path / "masked_check_report.md").exists()


def test_fail_findings_include_required_categories() -> None:
    result = check_path(FIXTURES / "fail" / "root.md")
    rule_ids = {finding["rule_id"] for finding in result["findings"]}
    assert "email_address" in rule_ids
    assert "phone_number" in rule_ids
    assert "amount" in rule_ids
    assert "percentage_rate" in rule_ids


def test_matched_text_is_safely_redacted() -> None:
    result = check_path(FIXTURES / "fail" / "root.md")
    rendered = json.dumps(result["findings"], ensure_ascii=False)
    assert "dummy@example.invalid" not in rendered
    assert "03-0000-0000" not in rendered
    assert "1,200,000円" not in rendered
    assert "[REDACTED_AMOUNT]" in rendered


def test_input_file_is_not_modified(tmp_path: Path) -> None:
    source = FIXTURES / "fail" / "root.md"
    before = source.read_text(encoding="utf-8")
    code = main(["check-mask", "--input", str(source), "--output", str(tmp_path)])
    after = source.read_text(encoding="utf-8")
    assert code == 2
    assert after == before


def test_fixture_uses_only_dummy_names() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in FIXTURES.rglob("*.md"))
    assert "Project_Dummy" in text
    assert "Sample_Company" in text
    assert "Person_A" in text
    assert "dummy@example.invalid" in text


def test_exit_code_mapping() -> None:
    assert exit_code_for_status("PASS") == 0
    assert exit_code_for_status("WARNING") == 1
    assert exit_code_for_status("FAIL") == 2
    assert exit_code_for_status("UNKNOWN") == 3
