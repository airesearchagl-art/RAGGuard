from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragguard.cli import main
from ragguard.http_contract import (
    HTTPRetrievalRequest,
    HTTPTransportErrorCategory,
    LocalHTTPEndpoint,
    http_transport_error,
)
from test_fake_loopback_http_contract import (
    _RecordingLoopbackHTTPTransport,
    _ScriptedResponse,
    _benchmark_cli_args,
    _benchmark_http_response,
    _response_body,
    _running_server,
    _write_loopback_config,
)


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


def _http_config(endpoint: str = "http://127.0.0.1:54321/retrieve") -> dict[str, object]:
    return {
        "transport_type": "loopback_http",
        "endpoint": endpoint,
        "connect_timeout": 0.25,
        "read_timeout": 0.25,
        "total_timeout": 0.5,
        "default_top_k": 5,
        "response_size_limit": 262_144,
        "capabilities": {
            "ranked_results": True,
            "matched_keywords": True,
            "filters": False,
        },
    }


def _run_config_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    content: str,
    *,
    suffix: str = ".json",
) -> tuple[int, str, Path]:
    config = tmp_path / f"private-http-config{suffix}"
    config.write_text(content, encoding="utf-8")
    output = tmp_path / "report"

    code = main(_benchmark_cli_args(output, config))
    captured = capsys.readouterr()

    assert captured.out == ""
    assert not (output / "benchmark_report.json").exists()
    assert not (output / "benchmark_report.md").exists()
    return code, captured.err, config


@pytest.mark.parametrize(
    "field",
    ["unknown", "auth", "token", "cookie", "proxy", "redirect", "retry", "credential"],
)
def test_http_cli_rejects_unknown_and_security_config_fields_without_disclosure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
) -> None:
    config = _http_config()
    config[field] = "private-credential-value"

    code, error, path = _run_config_error(tmp_path, capsys, json.dumps(config))

    assert code == 3
    assert str(path) not in error
    assert "private-credential-value" not in error
    assert "127.0.0.1:54321" not in error
    assert "Traceback" not in error


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://192.168.1.10:54321/retrieve",
        "http://203.0.113.10:54321/retrieve",
        "http://0.0.0.0:54321/retrieve",
        "http://[::]:54321/retrieve",
        "http://*:54321/retrieve",
        "http://user:private@127.0.0.1:54321/retrieve",
        "http://127.0.0.1:54321/retrieve?token=private",
        "http://127.0.0.1:54321/retrieve#private",
        "http://127.0.0.1:54321/../private",
        "http://127.0.0.1:54321/%2e%2e/private",
    ],
)
def test_http_cli_rejects_unsafe_endpoints_without_echoing_them(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    endpoint: str,
) -> None:
    config = _http_config(endpoint)

    code, error, path = _run_config_error(tmp_path, capsys, json.dumps(config))

    assert code == 3
    assert endpoint not in error
    assert str(path) not in error
    assert "private" not in error
    assert "Traceback" not in error


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("connect_timeout", 0),
        ("read_timeout", -1),
        ("total_timeout", True),
        ("default_top_k", 0),
        ("default_top_k", True),
        ("response_size_limit", 0),
        ("response_size_limit", 1_048_577),
    ],
)
def test_http_cli_rejects_invalid_bounded_config_values(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
) -> None:
    config = _http_config()
    config[field] = value

    code, error, path = _run_config_error(tmp_path, capsys, json.dumps(config))

    assert code == 3
    assert str(path) not in error
    assert "127.0.0.1:54321" not in error
    assert "Traceback" not in error


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        (".json", "[]"),
        (".yaml", "- not-a-mapping"),
        (".yaml", "!!python/object/apply:builtins.str [private-credential-value]"),
        (".json", '{"transport_type":"unknown_transport"}'),
    ],
)
def test_http_cli_rejects_unsafe_or_non_mapping_config_documents(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    suffix: str,
    content: str,
) -> None:
    code, error, path = _run_config_error(
        tmp_path, capsys, content, suffix=suffix
    )

    assert code == 3
    assert str(path) not in error
    assert "private-credential-value" not in error
    assert "Traceback" not in error


def test_http_cli_rejects_missing_and_oversized_config_without_path_disclosure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "private-missing.json"
    oversized = tmp_path / "private-oversized.yaml"
    oversized.write_text("a" * 65_537, encoding="utf-8")

    missing_code = main(_benchmark_cli_args(tmp_path / "missing-report", missing))
    missing_error = capsys.readouterr().err
    oversized_code = main(_benchmark_cli_args(tmp_path / "large-report", oversized))
    oversized_error = capsys.readouterr().err

    assert missing_code == oversized_code == 3
    assert str(missing) not in missing_error
    assert str(oversized) not in oversized_error
    assert "Traceback" not in missing_error + oversized_error


def _base_result(rank: int, document_id: str) -> dict[str, object]:
    return {
        "rank": rank,
        "document_id": document_id,
        "score": 1.0,
        "title": "Synthetic Result",
        "source_id": f"{document_id}-source",
        "matched_keywords": ["synthetic"],
        "adapter_metadata": {"transport": "loopback_http"},
    }


@pytest.mark.parametrize(
    ("body", "top_k"),
    [
        (b"\xffprivate-raw-response", 5),
        (b"private-invalid-json", 5),
        (_response_body(extra_top_level={"private_unknown": "private-raw-response"}), 5),
        (json.dumps({"results": [{"rank": 1}]}).encode("utf-8"), 5),
        (
            json.dumps(
                {"results": [_base_result(1, "synthetic-001"), _base_result(2, "synthetic-002")]}
            ).encode("utf-8"),
            1,
        ),
        (
            json.dumps(
                {
                    "results": [
                        _base_result(index, f"synthetic-{index:03d}")
                        for index in range(1, 102)
                    ]
                }
            ).encode("utf-8"),
            100,
        ),
    ],
)
def test_http_cli_rejects_invalid_response_boundaries_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    body: bytes,
    top_k: int,
) -> None:
    transports: list[_RecordingLoopbackHTTPTransport] = []

    def create_transport() -> _RecordingLoopbackHTTPTransport:
        transport = _RecordingLoopbackHTTPTransport()
        transports.append(transport)
        return transport

    monkeypatch.setattr(
        "ragguard.cli.LoopbackHTTPLocalRetrievalTransport", create_transport
    )
    with _running_server(_ScriptedResponse(body=body)) as server:
        config = _write_loopback_config(
            tmp_path / "private-response.json",
            server,
            default_top_k=top_k,
        )
        output = tmp_path / "report"
        code = main(_benchmark_cli_args(output, config))

    captured = capsys.readouterr()
    assert code == 3
    assert captured.out == ""
    assert "invalid_response" in captured.err
    assert str(config) not in captured.err
    assert str(server.server_address[1]) not in captured.err
    assert "private-raw-response" not in captured.err
    assert "Traceback" not in captured.err
    assert transports[0].events[-1] == "close"
    assert transports[0].state == "closed"
    assert not (output / "benchmark_report.json").exists()


@pytest.mark.parametrize(
    "category",
    [
        HTTPTransportErrorCategory.CONNECTION_REFUSED,
        HTTPTransportErrorCategory.TIMEOUT,
        HTTPTransportErrorCategory.EXTERNAL_HOST_REJECTED,
    ],
)
def test_http_cli_maps_connection_and_peer_failures_once_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    category: HTTPTransportErrorCategory,
) -> None:
    calls = 0
    transports: list[_RecordingLoopbackHTTPTransport] = []

    class FailingClient:
        def __init__(self, endpoint: LocalHTTPEndpoint) -> None:
            assert isinstance(endpoint, LocalHTTPEndpoint)

        def retrieve(self, request: HTTPRetrievalRequest):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            raise http_transport_error(category)

    def create_transport() -> _RecordingLoopbackHTTPTransport:
        transport = _RecordingLoopbackHTTPTransport()
        transports.append(transport)
        return transport

    monkeypatch.setattr("ragguard.http_transport.BoundedLoopbackHTTPClient", FailingClient)
    monkeypatch.setattr(
        "ragguard.cli.LoopbackHTTPLocalRetrievalTransport", create_transport
    )
    config = tmp_path / "private-peer.json"
    config.write_text(json.dumps(_http_config()), encoding="utf-8")

    code = main(_benchmark_cli_args(tmp_path / "report", config))
    captured = capsys.readouterr()

    assert code == 3
    assert calls == 1
    assert category.value in captured.err
    assert str(config) not in captured.err
    assert "127.0.0.1:54321" not in captured.err
    assert "Traceback" not in captured.err
    assert transports[0].events[-1] == "close"
    assert transports[0].state == "closed"


@pytest.mark.parametrize("suffix", [".json", ".yaml"])
def test_http_cli_success_is_deterministic_safe_and_report_compatible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
) -> None:
    transports: list[_RecordingLoopbackHTTPTransport] = []

    def create_transport() -> _RecordingLoopbackHTTPTransport:
        transport = _RecordingLoopbackHTTPTransport()
        transports.append(transport)
        return transport

    monkeypatch.setattr(
        "ragguard.cli.LoopbackHTTPLocalRetrievalTransport", create_transport
    )
    with _running_server(_benchmark_http_response) as server:
        config = _write_loopback_config(tmp_path / f"private-loopback{suffix}", server)
        output = tmp_path / "report"
        code = main(_benchmark_cli_args(output, config))

    report_text = (output / "benchmark_report.json").read_text(encoding="utf-8")
    markdown = (output / "benchmark_report.md").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert code == 0
    assert set(report) == REPORT_KEYS
    assert report["result"] == report["status"] == "PASS"
    assert report["metadata"]["retrieval_adapter"] == "local-rag"
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
    combined = report_text + markdown
    assert str(config) not in combined
    assert str(server.server_address[1]) not in combined
    assert "127.0.0.1" not in combined
    assert "credential" not in combined.lower()
    assert "Traceback" not in combined
