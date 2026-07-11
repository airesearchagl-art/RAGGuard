from __future__ import annotations

import json
from pathlib import Path


JSON_REPORT_NAME = "masked_check_report.json"
MARKDOWN_REPORT_NAME = "masked_check_report.md"


def write_reports(result: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / JSON_REPORT_NAME
    markdown_path = output_dir / MARKDOWN_REPORT_NAME

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown_report(result), encoding="utf-8")
    return json_path, markdown_path


def render_markdown_report(result: dict) -> str:
    findings = result.get("findings", [])
    checked_files = result.get("checked_files", [])
    summary = result.get("summary", {})
    status = result.get("status", "UNKNOWN")

    lines = [
        "# Masked Document Check Report",
        "",
        "## Result",
        "",
        status,
        "",
        "## Summary",
        "",
        f"- Status: {status}",
        f"- Checked files: {result.get('checked_file_count', len(checked_files))}",
        f"- Findings: {result.get('finding_count', len(findings))}",
        f"- FAIL: {summary.get('fail', 0)}",
        f"- WARNING: {summary.get('warning', 0)}",
        f"- PASS: {summary.get('pass', 0)}",
        "",
        "## Checked Files",
        "",
    ]
    if checked_files:
        lines.extend(f"- {path}" for path in checked_files)
    else:
        lines.append("- No Markdown files checked.")

    lines.extend(["", "## Findings", ""])
    if findings:
        for index, finding in enumerate(findings, start=1):
            lines.extend(
                [
                    f"### Finding {index}",
                    "",
                    f"- file: {finding['file']}",
                    f"  line: {finding['line']}",
                    f"  category: {finding['category']}",
                    f"  severity: {finding['severity']}",
                    f"  rule_id: {finding['rule_id']}",
                    f"  matched_text: {finding['matched_text']}",
                    f"  recommendation: {finding['recommendation']}",
                    "",
                ]
            )
    else:
        lines.append("- No findings.")

    lines.extend(
        [
            "",
            "## Next Action",
            "",
            next_action(status),
            "",
        ]
    )
    return "\n".join(lines)


def next_action(status: str) -> str:
    if status == "FAIL":
        return "RAG_OK投入前に、FAIL箇所を修正してください。"
    if status == "WARNING":
        return "RAG_OK投入前に、WARNING箇所を確認し、必要に応じてマスクしてください。"
    if status == "PASS":
        return "検出結果はPASSです。投入前の通常レビューを継続してください。"
    return "CLI実行結果を確認してください。"
