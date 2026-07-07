from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ragguard.detectors import RULES, Rule, redact_match
from ragguard.utils import collect_markdown_files, display_path


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    category: str
    severity: str
    rule_id: str
    matched_text: str
    recommendation: str


def check_path(input_path: Path, rules: tuple[Rule, ...] = RULES) -> dict:
    markdown_files = collect_markdown_files(input_path)
    base = input_path if input_path.is_dir() else input_path.parent
    findings: list[Finding] = []

    for markdown_file in markdown_files:
        text = markdown_file.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule in rules:
                for match in rule.pattern.finditer(line):
                    findings.append(
                        Finding(
                            file=display_path(markdown_file, base),
                            line=line_number,
                            category=rule.category,
                            severity=rule.severity,
                            rule_id=rule.rule_id,
                            matched_text=redact_match(match.group(0), rule.redaction),
                            recommendation=rule.recommendation,
                        )
                    )

    fail_count = sum(1 for finding in findings if finding.severity == "FAIL")
    warning_count = sum(1 for finding in findings if finding.severity == "WARNING")
    status = "FAIL" if fail_count else "WARNING" if warning_count else "PASS"

    return {
        "status": status,
        "checked_files": [display_path(path, base) for path in markdown_files],
        "checked_file_count": len(markdown_files),
        "finding_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
        "summary": {
            "pass": 0,
            "warning": warning_count,
            "fail": fail_count,
        },
    }


def exit_code_for_status(status: str) -> int:
    return {"PASS": 0, "WARNING": 1, "FAIL": 2}.get(status, 3)
