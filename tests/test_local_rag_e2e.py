from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ragguard.cli import main
from ragguard.retrieval import (
    InMemoryLocalRetrievalTransport,
    LocalRetrievalCapabilities,
    LocalRetrievalConfig,
    LocalRetrievalRequest,
    LocalRetrievalResponse,
    LocalRetrievalResult,
)


BENCHMARK_FIXTURES = Path(__file__).parent / "fixtures" / "benchmark"
REPORT_KEYS = {
    "result",
    "status",
    "corpus_count",
    "query_count",
    "summary",
    "corpus",
    "queries",
    "per_query_results",
    "results",
    "warnings",
    "errors",
    "metadata",
}


class RecordingE2ETransport(InMemoryLocalRetrievalTransport):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.events: list[str] = []

    def initialize(self, config: LocalRetrievalConfig) -> None:
        self.events.append("initialize")
        super().initialize(config)

    def health_check(self) -> bool:
        self.events.append("health_check")
        return super().health_check()

    def capabilities(self) -> LocalRetrievalCapabilities:
        self.events.append("capabilities")
        return super().capabilities()

    def retrieve(self, request: LocalRetrievalRequest) -> LocalRetrievalResponse:
        self.events.append("retrieve")
        return super().retrieve(request)

    def close(self) -> None:
        self.events.append("close")
        super().close()


def benchmark_args(output: Path, config: Path | None = None) -> list[str]:
    args = [
        "benchmark",
        "--corpus",
        str(BENCHMARK_FIXTURES / "corpus"),
        "--queries",
        str(BENCHMARK_FIXTURES / "queries.jsonl"),
        "--output",
        str(output),
    ]
    if config is not None:
        args.extend(["--adapter", "local-rag", "--adapter-config", str(config)])
    return args


def write_config(path: Path, *, response_size_limit: int = 12_345) -> Path:
    config = {
        "transport_type": "in_memory",
        "timeout_seconds": 7.25,
        "default_top_k": 5,
        "response_size_limit": response_size_limit,
        "capabilities": {
            "ranked_results": True,
            "matched_keywords": False,
            "filters": False,
        },
    }
    if path.suffix == ".json":
        path.write_text(json.dumps(config), encoding="utf-8")
    else:
        path.write_text(
            "\n".join(
                [
                    "transport_type: in_memory",
                    "timeout_seconds: 7.25",
                    "default_top_k: 5",
                    f"response_size_limit: {response_size_limit}",
                    "capabilities:",
                    "  ranked_results: true",
                    "  matched_keywords: false",
                    "  filters: false",
                ]
            ),
            encoding="utf-8",
        )
    return path


def local_result(
    document_id: str,
    title: str,
    matched_keywords: list[str],
) -> LocalRetrievalResult:
    return LocalRetrievalResult(
        rank=1,
        document_id=document_id,
        score=len(matched_keywords),
        title=title,
        source_id=f"{document_id}-source",
        matched_keywords=matched_keywords,
        metadata={"transport": "in_memory"},
    )


def pass_responses() -> list[LocalRetrievalResponse]:
    return [
        LocalRetrievalResponse(
            results=[
                local_result(
                    "sample-policy-001",
                    "Sample Policy Result",
                    ["sample", "archive"],
                )
            ]
        ),
        LocalRetrievalResponse(
            results=[
                local_result(
                    "sample-faq-001",
                    "Sample FAQ Result",
                    ["fictional", "support", "windows"],
                )
            ]
        ),
        LocalRetrievalResponse(results=[]),
    ]


def install_transport_sequence(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[LocalRetrievalResponse],
) -> list[RecordingE2ETransport]:
    remaining = iter(responses)
    transports: list[RecordingE2ETransport] = []

    def create_transport() -> RecordingE2ETransport:
        transport = RecordingE2ETransport(response=next(remaining))
        transports.append(transport)
        return transport

    monkeypatch.setattr("ragguard.cli.InMemoryLocalRetrievalTransport", create_transport)
    return transports


@pytest.mark.parametrize("suffix", [".json", ".yaml"])
def test_local_rag_e2e_pass_json_and_yaml_reports_are_safe_and_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
) -> None:
    config = write_config(tmp_path / f"private-local-config{suffix}")
    transports = install_transport_sequence(monkeypatch, pass_responses())
    output = tmp_path / "report"

    code = main(benchmark_args(output, config))

    report_text = (output / "benchmark_report.json").read_text(encoding="utf-8")
    markdown = (output / "benchmark_report.md").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert code == 0
    assert set(report) == REPORT_KEYS
    assert report["result"] == report["status"] == "PASS"
    assert report["metadata"]["retrieval_adapter"] == "local-rag"
    assert "- Retrieval adapter: local-rag" in markdown
    assert [
        item["ranked_results"][0]["document_id"]
        for item in report["per_query_results"][:2]
    ] == ["sample-policy-001", "sample-faq-001"]
    assert all(
        transport.events
        == ["initialize", "health_check", "capabilities", "retrieve", "close"]
        for transport in transports
    )
    assert all(transport.state == "closed" for transport in transports)

    combined_report = report_text + markdown
    assert str(config) not in combined_report
    assert "7.25" not in combined_report
    assert "12345" not in combined_report
    assert "Sample policy documents are stored in the sample archive." not in combined_report


@pytest.mark.parametrize(
    ("first_response", "expected_code", "expected_result", "expected_status"),
    [
        (
            LocalRetrievalResponse(
                results=[
                    local_result(
                        "sample-policy-001",
                        "Partial Policy Result",
                        ["sample"],
                    )
                ]
            ),
            1,
            "WARNING",
            "warning",
        ),
        (
            LocalRetrievalResponse(
                results=[
                    local_result(
                        "sample-faq-001",
                        "Wrong Policy Result",
                        ["fictional"],
                    )
                ]
            ),
            2,
            "FAIL",
            "fail",
        ),
    ],
)
def test_local_rag_e2e_warning_and_fail_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_response: LocalRetrievalResponse,
    expected_code: int,
    expected_result: str,
    expected_status: str,
) -> None:
    config = write_config(tmp_path / "local.json")
    responses = pass_responses()
    responses[0] = first_response
    install_transport_sequence(monkeypatch, responses)
    output = tmp_path / "report"

    code = main(benchmark_args(output, config))

    report = json.loads((output / "benchmark_report.json").read_text(encoding="utf-8"))
    assert code == expected_code
    assert report["result"] == expected_result
    assert report["per_query_results"][0]["evaluation_status"] == expected_status


def test_local_rag_e2e_failure_closes_transport_and_returns_cli_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = write_config(tmp_path / "private-local.json", response_size_limit=1_024)
    transports: list[RecordingE2ETransport] = []

    def create_transport() -> RecordingE2ETransport:
        transport = RecordingE2ETransport(error_mode="invalid_response")
        transports.append(transport)
        return transport

    monkeypatch.setattr("ragguard.cli.InMemoryLocalRetrievalTransport", create_transport)
    output = tmp_path / "report"

    code = main(benchmark_args(output, config))

    error = capsys.readouterr().err
    assert code == 3
    assert transports[0].events == [
        "initialize",
        "health_check",
        "capabilities",
        "retrieve",
        "close",
    ]
    assert transports[0].state == "closed"
    assert "invalid response" in error
    assert str(config) not in error
    assert not (output / "benchmark_report.json").exists()


@pytest.mark.parametrize("error_mode", ["invalid_response", "oversized_response"])
def test_local_rag_e2e_invalid_transport_responses_return_cli_error_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_mode: str,
) -> None:
    config = write_config(tmp_path / "local.json", response_size_limit=1_024)
    transports: list[RecordingE2ETransport] = []

    def create_transport() -> RecordingE2ETransport:
        transport = RecordingE2ETransport(error_mode=error_mode)
        transports.append(transport)
        return transport

    monkeypatch.setattr("ragguard.cli.InMemoryLocalRetrievalTransport", create_transport)
    output = tmp_path / "report"

    code = main(benchmark_args(output, config))

    assert code == 3
    assert transports[0].events[-1] == "close"
    assert transports[0].state == "closed"
    assert not (output / "benchmark_report.json").exists()


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        (".json", "[]"),
        (".yaml", "- not-a-mapping"),
        (".json", '{"transport_type":"in_memory","credential":"private-secret"}'),
        (".json", '{"transport_type":"http"}'),
        (".json", '{"transport_type":"in_memory","timeout_seconds":0}'),
        (".json", '{"transport_type":"in_memory","default_top_k":true}'),
        (".json", '{"transport_type":"in_memory","response_size_limit":0}'),
        (".yaml", "!!python/object/apply:builtins.str [private-secret]"),
    ],
)
def test_local_rag_e2e_unsafe_configs_return_cli_error_without_disclosure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    suffix: str,
    content: str,
) -> None:
    config = tmp_path / f"private-config{suffix}"
    config.write_text(content, encoding="utf-8")
    output = tmp_path / "report"

    code = main(benchmark_args(output, config))

    error = capsys.readouterr().err
    assert code == 3
    assert str(config) not in error
    assert "private-secret" not in error
    assert not (output / "benchmark_report.json").exists()


def test_local_rag_e2e_missing_and_oversized_configs_return_cli_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "private-missing.json"
    oversized = tmp_path / "private-oversized.yaml"
    oversized.write_text("a" * 65_537, encoding="utf-8")

    no_config_code = main(
        benchmark_args(tmp_path / "no-config-report") + ["--adapter", "local-rag"]
    )
    no_config_error = capsys.readouterr().err
    missing_code = main(benchmark_args(tmp_path / "missing-report", missing))
    missing_error = capsys.readouterr().err
    oversized_code = main(benchmark_args(tmp_path / "oversized-report", oversized))
    oversized_error = capsys.readouterr().err

    assert no_config_code == missing_code == oversized_code == 3
    assert "requires a config file" in no_config_error
    assert str(missing) not in missing_error
    assert str(oversized) not in oversized_error


def test_synthetic_default_e2e_remains_pass_and_report_compatible(tmp_path: Path) -> None:
    output = tmp_path / "synthetic"

    code = main(benchmark_args(output))

    report = json.loads((output / "benchmark_report.json").read_text(encoding="utf-8"))
    markdown = (output / "benchmark_report.md").read_text(encoding="utf-8")
    assert code == 0
    assert set(report) == REPORT_KEYS
    assert report["result"] == "PASS"
    assert report["metadata"]["retrieval_adapter"] == "synthetic"
    assert "- Retrieval adapter: synthetic" in markdown
