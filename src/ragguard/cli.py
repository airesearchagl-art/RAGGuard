from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ragguard.masked_document_checker import check_path, exit_code_for_status
from ragguard.report import write_reports


class RagguardArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(3, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = RagguardArgumentParser(prog="ragguard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_mask = subparsers.add_parser(
        "check-mask",
        help="Check masked Markdown documents before RAG ingestion.",
    )
    check_mask.add_argument("--input", required=True, help="Markdown file or folder to check.")
    check_mask.add_argument("--output", required=True, help="Output folder for reports.")
    check_mask.add_argument(
        "--format",
        choices=["both"],
        default="both",
        help="Report format. MVP always writes JSON and Markdown.",
    )
    check_mask.add_argument("--verbose", action="store_true", help="Print report paths.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check-mask":
        try:
            result = check_path(Path(args.input))
            json_path, markdown_path = write_reports(result, Path(args.output))
        except Exception as exc:
            print(f"ragguard: error: {exc}", file=sys.stderr)
            return 3

        if args.verbose:
            print(f"JSON report: {json_path}")
            print(f"Markdown report: {markdown_path}")
            print(f"Status: {result['status']}")
        return exit_code_for_status(result["status"])

    parser.error(f"Unknown command: {args.command}")
    return 3
