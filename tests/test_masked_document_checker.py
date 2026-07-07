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


def test_phase_a_money_rate_and_unit_price_rules_are_detected(tmp_path: Path) -> None:
    source = tmp_path / "phase_a_dummy.md"
    source.write_text(
        "\n".join(
            [
                "# Phase_A_Dummy",
                "金額は 税込 1,234.5万円、税別 2億円、3,000千円です。",
                "料率は 手数料率 2.75パーセント、利率 1.5％ です。",
                "単価は 坪単価 120.5万円、㎡単価 36,000円、45万円/坪 です。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    before = source.read_text(encoding="utf-8")

    result = check_path(source)
    rendered = json.dumps(result["findings"], ensure_ascii=False)
    rule_ids = {finding["rule_id"] for finding in result["findings"]}

    assert result["status"] == "FAIL"
    assert {"amount", "percentage_rate", "unit_price"} <= rule_ids
    assert "[REDACTED_AMOUNT]" in rendered
    assert "[REDACTED_RATE]" in rendered
    for sensitive_value in ["1,234.5万円", "2.75パーセント", "120.5万円", "36,000円", "45万円/坪"]:
        assert sensitive_value not in rendered
    assert source.read_text(encoding="utf-8") == before


def test_phase_b_address_candidate_rules_are_detected(tmp_path: Path) -> None:
    source = tmp_path / "phase_b_dummy.md"
    source.write_text(
        "\n".join(
            [
                "# Phase_B_Dummy",
                "郵便番号は 123-4567 です。",
                "所在地は サンプル県サンプル市1丁目2番地3号 です。",
                "物件所在地は サンプル建物A棟 です。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    before = source.read_text(encoding="utf-8")

    result = check_path(source)
    rendered = json.dumps(result["findings"], ensure_ascii=False)
    rule_ids = {finding["rule_id"] for finding in result["findings"]}

    assert result["status"] == "FAIL"
    assert {"address_postal_code", "address_like", "address_context"} <= rule_ids
    assert "[REDACTED_ADDRESS]" in rendered
    for sensitive_value in ["123-4567", "サンプル県サンプル市1丁目2番地3号", "サンプル建物A棟"]:
        assert sensitive_value not in rendered
    assert source.read_text(encoding="utf-8") == before


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


def test_config_not_specified_preserves_builtin_behavior(tmp_path: Path) -> None:
    code = main(["check-mask", "--input", str(FIXTURES / "warning"), "--output", str(tmp_path)])
    result = json.loads((tmp_path / "masked_check_report.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["status"] == "WARNING"
    assert {finding["rule_id"] for finding in result["findings"]} == {
        "budget_word",
        "person_name_like",
        "internal_context_word",
    }


def test_config_keyword_rule_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "input.md"
    source.write_text("公開前レビューでは設備更新を確認します。\n", encoding="utf-8")
    config = write_config(
        tmp_path,
        """
version: 1
mode: extend_builtin
rules:
  - rule_id: equipment_keyword_custom
    category: internal
    severity: WARNING
    type: keyword
    keywords:
      - "設備更新"
    recommendation: "文脈を確認してください。"
    redaction: keyword
""",
    )
    code = main(["check-mask", "--input", str(source), "--output", str(tmp_path / "out"), "--config", str(config)])
    result = json.loads((tmp_path / "out" / "masked_check_report.json").read_text(encoding="utf-8"))
    assert code == 1
    assert result["findings"][0]["rule_id"] == "equipment_keyword_custom"
    assert result["findings"][0]["matched_text"] == "[REDACTED_KEYWORD]"


def test_config_regex_rule_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "input.md"
    source.write_text("管理コードは ABC-1234 です。\n", encoding="utf-8")
    config = write_config(
        tmp_path,
        """
version: 1
mode: extend_builtin
rules:
  - rule_id: management_code_custom
    category: internal
    severity: FAIL
    type: regex
    pattern: "[A-Z]{3}-[0-9]{4}"
    recommendation: "管理コードを確認してください。"
    redaction: label
""",
    )
    code = main(["check-mask", "--input", str(source), "--output", str(tmp_path / "out"), "--config", str(config)])
    result = json.loads((tmp_path / "out" / "masked_check_report.json").read_text(encoding="utf-8"))
    assert code == 2
    assert result["findings"][0]["rule_id"] == "management_code_custom"
    assert result["findings"][0]["matched_text"] == "[REDACTED_VALUE]"


def test_config_findings_generate_json_and_markdown_reports(tmp_path: Path) -> None:
    source = tmp_path / "input.md"
    source.write_text("確認語: YAML_SAMPLE\n", encoding="utf-8")
    config = write_config(
        tmp_path,
        """
version: 1
mode: extend_builtin
rules:
  - rule_id: yaml_sample_custom
    category: internal
    severity: WARNING
    type: keyword
    keywords:
      - "YAML_SAMPLE"
    recommendation: "サンプル語を確認してください。"
    redaction: keyword
""",
    )
    out = tmp_path / "out"
    code = main(["check-mask", "--input", str(source), "--output", str(out), "--config", str(config)])
    assert code == 1
    assert (out / "masked_check_report.json").exists()
    assert (out / "masked_check_report.md").exists()


def test_config_extend_builtin_keeps_builtin_rules(tmp_path: Path) -> None:
    source = tmp_path / "input.md"
    source.write_text("dummy@example.invalid と YAML_SAMPLE を確認します。\n", encoding="utf-8")
    config = write_config(
        tmp_path,
        """
version: 1
mode: extend_builtin
rules:
  - rule_id: yaml_sample_custom
    category: internal
    severity: WARNING
    type: keyword
    keywords:
      - "YAML_SAMPLE"
    recommendation: "サンプル語を確認してください。"
    redaction: keyword
""",
    )
    code = main(["check-mask", "--input", str(source), "--output", str(tmp_path / "out"), "--config", str(config)])
    result = json.loads((tmp_path / "out" / "masked_check_report.json").read_text(encoding="utf-8"))
    rule_ids = {finding["rule_id"] for finding in result["findings"]}
    assert code == 2
    assert "email_address" in rule_ids
    assert "yaml_sample_custom" in rule_ids


def test_missing_config_file_returns_exit_3(tmp_path: Path) -> None:
    code = main([
        "check-mask",
        "--input",
        str(FIXTURES / "safe"),
        "--output",
        str(tmp_path / "out"),
        "--config",
        str(tmp_path / "missing.yaml"),
    ])
    assert code == 3


def test_invalid_yaml_returns_exit_3(tmp_path: Path) -> None:
    config = tmp_path / "rules.yaml"
    config.write_text("version: [\n", encoding="utf-8")
    code = run_with_config(tmp_path, config)
    assert code == 3


def test_invalid_mode_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(tmp_path, "version: 1\nmode: replace_builtin\nrules: []\n")
    assert run_with_config(tmp_path, config) == 3


def test_invalid_version_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(tmp_path, "version: 2\nmode: extend_builtin\nrules: []\n")
    assert run_with_config(tmp_path, config) == 3


def test_rules_not_list_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(tmp_path, "version: 1\nmode: extend_builtin\nrules: invalid\n")
    assert run_with_config(tmp_path, config) == 3


def test_invalid_category_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(tmp_path, base_config("category: unknown"))
    assert run_with_config(tmp_path, config) == 3


def test_invalid_severity_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(tmp_path, base_config("severity: INFO"))
    assert run_with_config(tmp_path, config) == 3


def test_invalid_type_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(tmp_path, base_config("type: glob"))
    assert run_with_config(tmp_path, config) == 3


def test_invalid_redaction_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(tmp_path, base_config("redaction: raw"))
    assert run_with_config(tmp_path, config) == 3


def test_duplicate_rule_id_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
version: 1
mode: extend_builtin
rules:
  - rule_id: email_address
    category: personal_info
    severity: FAIL
    type: regex
    pattern: "SAMPLE"
    recommendation: "確認してください。"
    redaction: label
""",
    )
    assert run_with_config(tmp_path, config) == 3


def test_duplicate_custom_rule_id_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        """
version: 1
mode: extend_builtin
rules:
  - rule_id: custom_duplicate
    category: internal
    severity: WARNING
    type: keyword
    keywords:
      - "ONE"
    recommendation: "確認してください。"
    redaction: keyword
  - rule_id: custom_duplicate
    category: internal
    severity: WARNING
    type: keyword
    keywords:
      - "TWO"
    recommendation: "確認してください。"
    redaction: keyword
""",
    )
    assert run_with_config(tmp_path, config) == 3


def test_invalid_regex_returns_exit_3(tmp_path: Path) -> None:
    config = write_config(tmp_path, base_config('pattern: "["'))
    assert run_with_config(tmp_path, config) == 3


def test_config_error_does_not_print_input_markdown(tmp_path: Path, capsys) -> None:
    source = tmp_path / "input.md"
    source.write_text("SECRET_SAMPLE_TEXT\n", encoding="utf-8")
    config = write_config(tmp_path, "version: 1\nmode: invalid\nrules: []\n")
    code = main(["check-mask", "--input", str(source), "--output", str(tmp_path / "out"), "--config", str(config)])
    captured = capsys.readouterr()
    assert code == 3
    assert "SECRET_SAMPLE_TEXT" not in captured.err
    assert "SECRET_SAMPLE_TEXT" not in captured.out


def test_config_matched_text_is_safely_redacted(tmp_path: Path) -> None:
    source = tmp_path / "input.md"
    source.write_text("token ABC-1234 and budget marker\n", encoding="utf-8")
    config = write_config(
        tmp_path,
        """
version: 1
mode: extend_builtin
rules:
  - rule_id: token_custom
    category: internal
    severity: FAIL
    type: regex
    pattern: "ABC-[0-9]{4}"
    recommendation: "確認してください。"
    redaction: label
""",
    )
    code = main(["check-mask", "--input", str(source), "--output", str(tmp_path / "out"), "--config", str(config)])
    rendered = (tmp_path / "out" / "masked_check_report.json").read_text(encoding="utf-8")
    assert code == 2
    assert "ABC-1234" not in rendered
    assert "[REDACTED_VALUE]" in rendered


def write_config(tmp_path: Path, content: str) -> Path:
    config = tmp_path / "rules.yaml"
    config.write_text(content.strip() + "\n", encoding="utf-8")
    return config


def run_with_config(tmp_path: Path, config: Path) -> int:
    return main([
        "check-mask",
        "--input",
        str(FIXTURES / "safe"),
        "--output",
        str(tmp_path / "out"),
        "--config",
        str(config),
    ])


def base_config(replacement: str) -> str:
    lines = [
        "version: 1",
        "mode: extend_builtin",
        "rules:",
        "  - rule_id: custom_rule",
        "    category: internal",
        "    severity: FAIL",
        "    type: regex",
        "    pattern: \"SAMPLE\"",
        "    recommendation: \"確認してください。\"",
        "    redaction: label",
    ]
    key = replacement.split(":", 1)[0].strip()
    return "\n".join(f"    {replacement}" if line.strip().startswith(f"{key}:") else line for line in lines)
