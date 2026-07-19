from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from ragguard.cli import main
from ragguard.compatibility import synthetic_compatibility_registry
from ragguard.compatibility_integration import CompatibilityProfileRetrievalAdapter
from ragguard.http_transport import CompatibilityLoopbackHTTPTransport
from ragguard.retrieval import RetrievalAdapterError, load_local_retrieval_config


FIXTURES = Path(__file__).parent / "fixtures" / "benchmark"
REPORT_KEYS = {
    "result", "status", "corpus_count", "query_count", "summary", "corpus",
    "queries", "per_query_results", "results", "warnings", "errors", "metadata",
}


class _CompatibilityServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, scenario: str = "pass") -> None:
        self.scenario = scenario
        self.requests: list[tuple[str, str]] = []
        super().__init__(("127.0.0.1", 0), _CompatibilityHandler)


class _CompatibilityHandler(BaseHTTPRequestHandler):
    server: _CompatibilityServer

    def do_GET(self) -> None:
        self.server.requests.append(("GET", self.path))
        if self.path == "/health":
            if self.server.scenario == "timeout":
                time.sleep(0.2)
            payload: object = {
                "status": "degraded" if self.server.scenario == "degraded" else "healthy",
                "protocol_version": "2.0.0" if self.server.scenario == "protocol" else "1.0.0",
                "service_available": self.server.scenario != "unavailable",
            }
            if self.server.scenario == "invalid_health":
                payload = {"status": "healthy"}
            elif self.server.scenario == "oversized_health":
                payload = {"padding": "x" * 2_048}
        elif self.path == "/capabilities":
            payload = _capabilities()
            if self.server.scenario == "missing_required":
                payload["retrieval"] = False
            elif self.server.scenario == "missing_optional":
                payload["title"] = False
            elif self.server.scenario == "invalid_capabilities":
                payload = {"retrieval": True}
        else:
            self._write(404, {})
            return
        self._write(200, payload)

    def do_POST(self) -> None:
        self.server.requests.append(("POST", self.path))
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._write(400, {})
            return
        if self.path != "/retrieve":
            self._write(404, {})
            return
        if self.server.scenario == "malformed_response":
            self._write(200, {"invalid": []})
            return
        self._write(200, _product_response(request, self.server.scenario))

    def _write(self, status: int, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format: str, *args: object) -> None:
        return


def _capabilities() -> dict[str, bool]:
    return {
        "retrieval": True,
        "bounded_top_k": True,
        "deterministic_result_schema": True,
        "safe_source_identifier": True,
        "response_size_compliance": True,
        "score": True,
        "title": True,
        "matched_keywords": True,
        "query_id_echo": True,
        "protocol_version_echo": True,
    }


def _product_response(request: dict[str, object], scenario: str) -> dict[str, object]:
    query = request["query_text"]
    if isinstance(query, str) and query.startswith("Where are sample policy"):
        document_id = "sample-faq-001" if scenario == "fail" else "sample-policy-001"
        keywords = ["sample"] if scenario == "warning" else ["sample", "archive"]
    elif isinstance(query, str) and query.startswith("What kind of support windows"):
        document_id = "sample-faq-001"
        keywords = ["fictional", "support", "windows"]
    else:
        return {"results": [], "echo_request_id": request["request_id"]}
    item: dict[str, object] = {
        "position": 1,
        "item_id": document_id,
        "relevance": 1.0,
        "display_title": "Synthetic Result",
        "safe_source": f"{document_id}-source",
        "matches": keywords,
    }
    if scenario == "unsafe_source":
        item["safe_source"] = "C:/private/source"
    if scenario == "duplicate":
        return {
            "results": [item, dict(item, position=2)],
            "echo_request_id": request["request_id"],
        }
    if scenario == "too_many":
        return {
            "results": [dict(item, position=index, item_id=f"synthetic-{index}", safe_source=f"source-{index}") for index in range(1, 7)],
            "echo_request_id": request["request_id"],
        }
    if scenario == "rank_gap":
        item["position"] = 2
    response: dict[str, object] = {
        "results": [item],
        "echo_request_id": request["request_id"],
    }
    if scenario == "echo_mismatch":
        response["echo_request_id"] = "other-query"
    return response


@contextmanager
def _server(scenario: str = "pass"):
    server = _CompatibilityServer(scenario)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def _config(server: _CompatibilityServer) -> dict[str, object]:
    return {
        "transport_type": "loopback_http",
        "endpoint": f"http://127.0.0.1:{server.server_address[1]}/retrieve",
        "connect_timeout": 0.5,
        "read_timeout": 0.5,
        "total_timeout": 1.0,
        "default_top_k": 5,
        "response_size_limit": 262_144,
        "capabilities": {"ranked_results": True, "matched_keywords": True, "filters": False},
        "compatibility_profile": {
            "profile_id": "synthetic_loopback_v1",
            "profile_version": "1.0.0",
            "protocol_version": "1.0.0",
            "requested_optional_capabilities": [],
        },
    }


def _write_config(path: Path, value: dict[str, object]) -> Path:
    if path.suffix == ".yaml":
        path.write_text(yaml.safe_dump(value, sort_keys=True), encoding="utf-8")
    else:
        path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _args(output: Path, config: Path) -> list[str]:
    return [
        "benchmark", "--corpus", str(FIXTURES / "corpus"), "--queries",
        str(FIXTURES / "queries.jsonl"), "--output", str(output),
        "--adapter", "local-rag", "--adapter-config", str(config),
    ]


@pytest.mark.parametrize(("suffix", "scenario", "exit_code", "status"), [
    (".json", "pass", 0, "PASS"),
    (".yaml", "pass", 0, "PASS"),
    (".json", "warning", 1, "WARNING"),
    (".json", "fail", 2, "FAIL"),
])
def test_profile_integration_e2e_results_and_report_are_stable(
    tmp_path: Path, suffix: str, scenario: str, exit_code: int, status: str
) -> None:
    with _server(scenario) as server:
        config = _write_config(tmp_path / f"private{suffix}", _config(server))
        output = tmp_path / "report"
        code = main(_args(output, config))
        requests = list(server.requests)
        private_port = str(server.server_address[1])
    report_text = (output / "benchmark_report.json").read_text(encoding="utf-8")
    markdown = (output / "benchmark_report.md").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert code == exit_code
    assert report["status"] == status
    assert set(report) == REPORT_KEYS
    assert report["metadata"]["retrieval_adapter"] == "local-rag"
    assert requests == [(method, path) for _ in range(3) for method, path in (
        ("GET", "/health"), ("GET", "/capabilities"), ("POST", "/retrieve")
    )]
    combined = report_text + markdown
    assert str(config) not in combined
    assert private_port not in combined
    assert "127.0.0.1" not in combined
    assert "query_text" not in combined
    assert "echo_request_id" not in combined


@pytest.mark.parametrize(
    ("scenario", "category"),
    [
        ("degraded", "health_unavailable"),
        ("unavailable", "health_unavailable"),
        ("protocol", "protocol_version_mismatch"),
        ("invalid_health", "health_invalid"),
        ("missing_required", "capability_mismatch"),
        ("missing_optional", "unsupported_capability"),
        ("invalid_capabilities", "invalid_capabilities_response"),
        ("unsafe_source", "unsafe_source_identifier"),
        ("duplicate", "invalid_mapped_response"),
        ("rank_gap", "invalid_mapped_response"),
        ("too_many", "invalid_mapped_response"),
        ("echo_mismatch", "capability_mismatch"),
        ("malformed_response", "product_response_invalid"),
    ],
)
def test_profile_integration_security_failures_are_safe_cli_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    scenario: str,
    category: str,
) -> None:
    with _server(scenario) as server:
        config = _write_config(tmp_path / "private.json", _config(server))
        code = main(_args(tmp_path / "report", config))
        private_port = str(server.server_address[1])
    captured = capsys.readouterr()
    assert code == 3
    assert category in captured.err
    assert captured.out == ""
    assert str(config) not in captured.err
    assert private_port not in captured.err
    assert "127.0.0.1" not in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("field", "value", "category"),
    [
        ("profile_id", "unknown_profile", "unknown_profile"),
        ("profile_version", "2.0.0", "unsupported_profile_version"),
        ("protocol_version", "2.0.0", "protocol_version_mismatch"),
    ],
)
def test_profile_selection_fails_closed_without_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: str,
    category: str,
) -> None:
    with _server() as server:
        raw = _config(server)
        profile = raw["compatibility_profile"]
        assert isinstance(profile, dict)
        profile[field] = value
        config = _write_config(tmp_path / "private.json", raw)
        code = main(_args(tmp_path / "report", config))
        assert server.requests == []
    captured = capsys.readouterr()
    assert code == 3
    assert category in captured.err
    if value != category:
        assert value not in captured.err


def test_profile_config_rejects_unknown_fields_and_does_not_disclose_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with _server() as server:
        raw = _config(server)
        profile = raw["compatibility_profile"]
        assert isinstance(profile, dict)
        profile["credential"] = "private-credential-value"
        config = _write_config(tmp_path / "private.json", raw)
        code = main(_args(tmp_path / "report", config))
    error = capsys.readouterr().err
    assert code == 3
    assert "private-credential-value" not in error
    assert str(config) not in error
    assert "Traceback" not in error


@pytest.mark.parametrize("scenario", ["pass", "malformed_response"])
def test_profile_transport_closes_after_success_and_failure(
    tmp_path: Path, scenario: str
) -> None:
    with _server(scenario) as server:
        path = _write_config(tmp_path / "private.json", _config(server))
        config = load_local_retrieval_config(path)
        transport = CompatibilityLoopbackHTTPTransport()
        adapter = CompatibilityProfileRetrievalAdapter(
            config, synthetic_compatibility_registry(), transport=transport
        )
        query = type(
            "Query",
            (),
            {
                "question": "Where are sample policy documents stored?",
                "query_id": "q001",
                "expected_keywords": [],
                "expected_answer_hint": "",
            },
        )()
        if scenario == "pass":
            assert adapter.retrieve(query, 5)[0].document_id == "sample-policy-001"
        else:
            with pytest.raises(RetrievalAdapterError, match="product_response_invalid"):
                adapter.retrieve(query, 5)
    assert adapter.closed is True
    assert transport.state == "closed"


@pytest.mark.parametrize(
    ("scenario", "category"),
    [("timeout", "timeout"), ("oversized_health", "response_too_large")],
)
def test_profile_transport_timeout_and_size_fail_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    scenario: str,
    category: str,
) -> None:
    with _server(scenario) as server:
        raw = _config(server)
        if scenario == "timeout":
            raw.update(connect_timeout=0.05, read_timeout=0.05, total_timeout=0.1)
        else:
            raw["response_size_limit"] = 1_024
        config = _write_config(tmp_path / "private.json", raw)
        code = main(_args(tmp_path / "report", config))
        requests = list(server.requests)
    error = capsys.readouterr().err
    assert code == 3
    assert category in error
    assert requests == [("GET", "/health")]


def test_profile_transport_unavailable_endpoint_is_safe_and_not_retried(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with _server() as server:
        raw = _config(server)
    config = _write_config(tmp_path / "private.json", raw)
    code = main(_args(tmp_path / "report", config))
    error = capsys.readouterr().err
    assert code == 3
    assert "connection_refused" in error or "timeout" in error
    assert str(config) not in error
    assert "Traceback" not in error
