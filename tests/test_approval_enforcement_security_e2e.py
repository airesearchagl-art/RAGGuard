from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ragguard.approval_enforcement import (
    ApprovalEnforcementRequest,
    REQUIRED_EXECUTION_CONSTRAINTS,
    REQUIRED_RETRIEVAL_CAPABILITIES,
    evaluate_approval_enforcement,
    require_approved_retrieval,
)
from ragguard.approval_workflow import (
    SyntheticApprovalWorkflowInput,
    build_all_pass_synthetic_input,
    build_synthetic_approval_metadata,
    build_synthetic_validation_report,
    evaluate_synthetic_approval_decision,
)
from ragguard.cli import main
from ragguard.compatibility import (
    ScoreSemantics,
    SemanticVersion,
    SourceIdentifierPolicy,
    synthetic_compatibility_registry,
)
from ragguard.compatibility_integration import (
    CompatibilityProfileRetrievalAdapter,
)
from ragguard.http_transport import CompatibilityLoopbackHTTPTransport
from ragguard.production_registry import (
    RegistryEntry,
    RegistryKind,
    TrustedProductionRegistry,
)
from ragguard.profile_approval import ApprovalRestrictions, ProfileMaturity
from ragguard.retrieval import RetrievalAdapterError, load_local_retrieval_config
from ragguard.validation_report import (
    ValidationCheckResult,
    ValidationOverallStatus,
)

from test_compatibility_profile_integration_e2e import (
    REPORT_KEYS,
    _args,
    _config,
    _server,
    _write_config,
)


NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
ALL_APPROVED_CAPABILITIES = tuple(
    sorted(
        REQUIRED_RETRIEVAL_CAPABILITIES
        | {
            "score",
            "title",
            "matched_keywords",
            "query_id_echo",
            "protocol_version_echo",
        }
    )
)


class _RecordingTransport(CompatibilityLoopbackHTTPTransport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    def initialize(self, config) -> None:
        self.events.append("initialize")
        super().initialize(config)

    def request_json(self, path, method, payload=None):
        self.events.append(
            {
                "/health": "health",
                "/capabilities": "capabilities",
                "/retrieve": "retrieve",
            }.get(path, "unknown")
        )
        return super().request_json(path, method, payload)

    def close(self) -> None:
        self.events.append("close")
        super().close()


def _workflow_input(
    *,
    restrictions: ApprovalRestrictions | None = None,
    **changes: object,
) -> SyntheticApprovalWorkflowInput:
    capabilities = set(ALL_APPROVED_CAPABILITIES)
    score_semantics = ScoreSemantics.HIGHER_IS_BETTER
    if restrictions is not None:
        if restrictions.score_disabled:
            capabilities.discard("score")
            score_semantics = ScoreSemantics.UNSCORED
        if restrictions.title_disabled:
            capabilities.discard("title")
        if restrictions.matched_keywords_disabled:
            capabilities.discard("matched_keywords")
    value = replace(
        build_all_pass_synthetic_input(evaluation_time=NOW),
        profile_id="synthetic_loopback_v1",
        approved_capabilities=tuple(sorted(capabilities)),
        approved_score_semantics=score_semantics,
        restrictions=restrictions,
    )
    return replace(value, **changes)


def _test_registry(
    value: SyntheticApprovalWorkflowInput | None = None,
) -> TrustedProductionRegistry:
    workflow_input = value or _workflow_input()
    report = build_synthetic_validation_report(workflow_input)
    decision = evaluate_synthetic_approval_decision(workflow_input, report)
    approval = build_synthetic_approval_metadata(
        workflow_input,
        report,
        decision,
    )
    entry = RegistryEntry.from_evidence(
        profile_id=workflow_input.profile_id,
        profile_version=workflow_input.profile_version,
        maturity=workflow_input.maturity,
        approval_metadata=approval,
        validation_report=report,
        registry_kind=workflow_input.registry_kind,
        registered_at=workflow_input.evaluation_time,
    )
    registry = TrustedProductionRegistry(kind=workflow_input.registry_kind)
    registry.register(
        entry,
        approval_metadata=approval,
        validation_report=report,
        evaluation_time=workflow_input.evaluation_time,
    )
    return registry


def _request(
    registry: TrustedProductionRegistry | None = None,
    *,
    optional: tuple[str, ...] = (),
    top_k: int = 5,
    product_version: str = "1.3.2",
    evaluation_time: datetime = NOW,
    **changes: object,
) -> ApprovalEnforcementRequest:
    value = ApprovalEnforcementRequest(
        profile_id="synthetic_loopback_v1",
        profile_version=SemanticVersion.parse("1.0.0"),
        normalized_product_version=SemanticVersion.parse(product_version),
        evaluation_time=evaluation_time,
        registry=registry or _test_registry(),
        requested_capabilities=tuple(
            sorted(REQUIRED_RETRIEVAL_CAPABILITIES | set(optional))
        ),
        requested_execution_constraints=tuple(
            sorted(REQUIRED_EXECUTION_CONSTRAINTS)
        ),
        requested_top_k=top_k,
        requested_optional_fields=tuple(sorted(optional)),
    )
    return replace(value, **changes)


def _query():
    return type(
        "Query",
        (),
        {
            "question": "Where are sample policy documents stored?",
            "query_id": "q001",
            "expected_keywords": [],
            "expected_answer_hint": "",
        },
    )()


def test_enforcement_allows_exact_test_entry_and_returns_safe_summary() -> None:
    result = require_approved_retrieval(_request())
    assert result.allowed
    assert result.safe_error_category is None
    assert result.approval_status_summary == "approved"
    assert result.registry_status_summary == "active_test"
    assert result.applied_restrictions == ()
    assert result.as_mapping() == {
        "allowed": True,
        "safe_error_category": None,
        "restriction_applied": False,
        "approval_status": "approved",
        "registry_status": "active_test",
    }
    rendered = repr(result) + repr(result.resolved_approved_entry)
    for hidden in (
        "synthetic-approval-001",
        "synthetic-validation-001",
        "synthetic-reviewer",
        "synthetic-approver",
    ):
        assert hidden not in rendered


def test_enforcement_is_deterministic_for_explicit_evaluation_time() -> None:
    request = _request()
    assert evaluate_approval_enforcement(request) == evaluate_approval_enforcement(
        request
    )


@pytest.mark.parametrize(
    ("mutation", "category"),
    [
        ({"profile_id": "unknown-profile"}, "profile_not_registered"),
        (
            {"profile_version": SemanticVersion.parse("1.0.1")},
            "profile_version_not_registered",
        ),
        (
            {"normalized_product_version": SemanticVersion.parse("2.0.0")},
            "product_version_unsupported",
        ),
    ],
)
def test_exact_resolution_has_no_discovery_fallback_or_nearest_version(
    mutation: dict[str, object],
    category: str,
) -> None:
    result = evaluate_approval_enforcement(_request(**mutation))
    assert not result.allowed
    assert result.safe_error_category == category
    assert result.resolved_approved_entry is None


def test_production_registry_kind_is_rejected_without_write() -> None:
    production = TrustedProductionRegistry(kind=RegistryKind.PRODUCTION)
    result = evaluate_approval_enforcement(_request(registry=production))
    assert not result.allowed
    assert result.safe_error_category == "registry_kind_mismatch"
    assert production.snapshot == {}


@pytest.mark.parametrize(
    ("changes", "category"),
    [
        ({"maturity": ProfileMaturity.DRAFT}, "profile_unapproved"),
        (
            {
                "validation_status": ValidationOverallStatus.EXPIRED,
                "revalidation_required": True,
            },
            "revalidation_required",
        ),
        (
            {
                "validation_status": ValidationOverallStatus.FAILED,
                "required_capabilities_result": ValidationCheckResult.FAILED,
            },
            "profile_unapproved",
        ),
        (
            {
                "validation_status": ValidationOverallStatus.FAILED,
                "score_semantics_result": ValidationCheckResult.FAILED,
            },
            "profile_unapproved",
        ),
        (
            {
                "validation_status": ValidationOverallStatus.FAILED,
                "source_policy_result": ValidationCheckResult.FAILED,
            },
            "profile_unapproved",
        ),
        (
            {
                "validation_status": ValidationOverallStatus.FAILED,
                "non_disclosure_result": ValidationCheckResult.FAILED,
            },
            "profile_unapproved",
        ),
        (
            {
                "validation_status": ValidationOverallStatus.FAILED,
                "transport_boundary_result": ValidationCheckResult.FAILED,
            },
            "profile_unapproved",
        ),
    ],
)
def test_unapproved_or_unsafe_evidence_cannot_enter_test_registry(
    changes: dict[str, object],
    category: str,
) -> None:
    with pytest.raises(RetrievalAdapterError, match=category):
        _test_registry(_workflow_input(**changes))


@pytest.mark.parametrize(
    ("transition", "category"),
    [
        ("suspend", "profile_suspended"),
        ("deprecate", "profile_deprecated"),
        ("revoke", "profile_revoked"),
    ],
)
def test_inactive_registry_entries_are_denied(
    transition: str,
    category: str,
) -> None:
    registry = _test_registry()
    getattr(registry, transition)("synthetic_loopback_v1", "1.0.0")
    result = evaluate_approval_enforcement(_request(registry))
    assert not result.allowed
    assert result.safe_error_category == category
    assert result.registry_status_summary == transition.replace(
        "deprecate",
        "deprecated",
    ).replace("suspend", "suspended").replace("revoke", "revoked")


@pytest.mark.parametrize(
    ("change", "later", "category"),
    [
        (
            {"validation_expires_at": NOW + timedelta(minutes=1)},
            NOW + timedelta(minutes=1),
            "profile_validation_expired",
        ),
        (
            {"approval_expires_at": NOW + timedelta(minutes=1)},
            NOW + timedelta(minutes=1),
            "approval_expired",
        ),
        (
            {
                "restrictions": ApprovalRestrictions(
                    expires_at=NOW + timedelta(minutes=1)
                )
            },
            NOW + timedelta(minutes=1),
            "approval_expired",
        ),
    ],
)
def test_validation_approval_and_restriction_expiration_are_denied(
    change: dict[str, object],
    later: datetime,
    category: str,
) -> None:
    value = _workflow_input(**change)
    result = evaluate_approval_enforcement(
        _request(_test_registry(value), evaluation_time=later)
    )
    assert not result.allowed
    assert result.safe_error_category == category


@pytest.mark.parametrize(
    ("restrictions", "optional", "top_k"),
    [
        (ApprovalRestrictions(maximum_top_k=4), (), 5),
        (ApprovalRestrictions(score_disabled=True), ("score",), 5),
        (ApprovalRestrictions(title_disabled=True), ("title",), 5),
        (
            ApprovalRestrictions(matched_keywords_disabled=True),
            ("matched_keywords",),
            5,
        ),
        (ApprovalRestrictions(query_id_echo_required=True), (), 5),
    ],
)
def test_restriction_violations_fail_without_implicit_downgrade(
    restrictions: ApprovalRestrictions,
    optional: tuple[str, ...],
    top_k: int,
) -> None:
    registry = _test_registry(_workflow_input(restrictions=restrictions))
    result = evaluate_approval_enforcement(
        _request(registry, optional=optional, top_k=top_k)
    )
    assert not result.allowed
    assert result.safe_error_category == "restriction_violation"


def test_allowed_restrictions_are_reported_without_raw_metadata() -> None:
    restrictions = ApprovalRestrictions(
        maximum_top_k=5,
        query_id_echo_required=True,
        supported_minor_versions=("1.3",),
    )
    registry = _test_registry(_workflow_input(restrictions=restrictions))
    result = require_approved_retrieval(
        _request(
            registry,
            optional=("query_id_echo",),
        )
    )
    assert result.approval_status_summary == "approved_with_restrictions"
    assert result.applied_restrictions == (
        "maximum_top_k",
        "query_id_echo_required",
        "supported_minor_versions",
    )


def test_supported_minor_version_restriction_is_enforced() -> None:
    restrictions = ApprovalRestrictions(
        supported_minor_versions=("1.2",),
    )
    registry = _test_registry(_workflow_input(restrictions=restrictions))
    result = evaluate_approval_enforcement(_request(registry))
    assert not result.allowed
    assert result.safe_error_category == "product_version_unsupported"


def test_denial_occurs_before_transport_creation_and_http_request(
    tmp_path: Path,
) -> None:
    with _server() as server:
        config = load_local_retrieval_config(
            _write_config(tmp_path / "synthetic.json", _config(server))
        )
        created: list[_RecordingTransport] = []

        def factory() -> _RecordingTransport:
            transport = _RecordingTransport()
            created.append(transport)
            return transport

        adapter = CompatibilityProfileRetrievalAdapter(
            config,
            synthetic_compatibility_registry(),
            transport_factory=factory,
            approval_request=_request(
                profile_version=SemanticVersion.parse("1.0.1")
            ),
        )
        with pytest.raises(
            RetrievalAdapterError,
            match="registry_metadata_invalid",
        ):
            adapter.retrieve(_query(), 5)
        assert server.requests == []
    assert created == []
    assert adapter.lifecycle == ("compatibility_resolved",)
    assert adapter.closed


def test_registry_denial_occurs_before_transport_creation_and_http_request(
    tmp_path: Path,
) -> None:
    registry = _test_registry()
    registry.revoke("synthetic_loopback_v1", "1.0.0")
    with _server() as server:
        config = load_local_retrieval_config(
            _write_config(tmp_path / "synthetic.json", _config(server))
        )
        created: list[_RecordingTransport] = []

        def factory() -> _RecordingTransport:
            transport = _RecordingTransport()
            created.append(transport)
            return transport

        adapter = CompatibilityProfileRetrievalAdapter(
            config,
            synthetic_compatibility_registry(),
            transport_factory=factory,
            approval_request=_request(registry),
        )
        with pytest.raises(RetrievalAdapterError, match="profile_revoked"):
            adapter.retrieve(_query(), 5)
        assert server.requests == []
    assert created == []
    assert adapter.lifecycle == ("compatibility_resolved",)


def test_approved_execution_uses_fixed_stage_order_and_closes_once(
    tmp_path: Path,
) -> None:
    with _server() as server:
        config = load_local_retrieval_config(
            _write_config(tmp_path / "synthetic.json", _config(server))
        )
        transports: list[_RecordingTransport] = []

        def factory() -> _RecordingTransport:
            transport = _RecordingTransport()
            transports.append(transport)
            return transport

        adapter = CompatibilityProfileRetrievalAdapter(
            config,
            synthetic_compatibility_registry(),
            transport_factory=factory,
            approval_request=_request(),
        )
        assert adapter.retrieve(_query(), 5)[0].document_id == (
            "sample-policy-001"
        )
        assert server.requests == [
            ("GET", "/health"),
            ("GET", "/capabilities"),
            ("POST", "/retrieve"),
        ]
    assert len(transports) == 1
    assert transports[0].events == [
        "initialize",
        "health",
        "capabilities",
        "retrieve",
        "close",
    ]
    assert adapter.lifecycle == (
        "compatibility_resolved",
        "approval_enforced",
        "transport_initialized",
        "health_validated",
        "capabilities_negotiated",
        "request_mapped",
        "retrieval_completed",
        "response_mapped",
        "closed",
    )
    adapter.close()
    assert transports[0].events.count("close") == 1


@pytest.mark.parametrize(
    ("scenario", "last_operation"),
    [
        ("invalid_health", "health"),
        ("missing_required", "capabilities"),
        ("malformed_response", "retrieve"),
    ],
)
def test_post_transport_failures_close_exactly_once(
    tmp_path: Path,
    scenario: str,
    last_operation: str,
) -> None:
    with _server(scenario) as server:
        config = load_local_retrieval_config(
            _write_config(tmp_path / "synthetic.json", _config(server))
        )
        transports: list[_RecordingTransport] = []

        def factory() -> _RecordingTransport:
            transport = _RecordingTransport()
            transports.append(transport)
            return transport

        adapter = CompatibilityProfileRetrievalAdapter(
            config,
            synthetic_compatibility_registry(),
            transport_factory=factory,
            approval_request=_request(),
        )
        with pytest.raises(RetrievalAdapterError):
            adapter.retrieve(_query(), 5)
    assert len(transports) == 1
    assert transports[0].events[-2:] == [last_operation, "close"]
    assert transports[0].events.count("close") == 1


def test_score_semantics_mismatch_is_denied_before_transport(
    tmp_path: Path,
) -> None:
    value = _workflow_input(
        approved_capabilities=tuple(
            sorted(REQUIRED_RETRIEVAL_CAPABILITIES)
        ),
        approved_score_semantics=ScoreSemantics.UNSCORED,
    )
    with _server() as server:
        config = load_local_retrieval_config(
            _write_config(tmp_path / "synthetic.json", _config(server))
        )
        adapter = CompatibilityProfileRetrievalAdapter(
            config,
            synthetic_compatibility_registry(),
            approval_request=_request(_test_registry(value)),
        )
        with pytest.raises(
            RetrievalAdapterError,
            match="registry_metadata_invalid",
        ):
            adapter.retrieve(_query(), 5)
        assert server.requests == []
    assert adapter.lifecycle == (
        "compatibility_resolved",
    )


def test_protocol_version_mismatch_is_denied_before_transport(
    tmp_path: Path,
) -> None:
    value = _workflow_input(
        protocol_version=SemanticVersion.parse("1.1.0"),
    )
    with _server() as server:
        config = load_local_retrieval_config(
            _write_config(tmp_path / "synthetic.json", _config(server))
        )
        adapter = CompatibilityProfileRetrievalAdapter(
            config,
            synthetic_compatibility_registry(),
            approval_request=_request(_test_registry(value)),
        )
        with pytest.raises(
            RetrievalAdapterError,
            match="registry_metadata_invalid",
        ):
            adapter.retrieve(_query(), 5)
        assert server.requests == []
    assert adapter.lifecycle == (
        "compatibility_resolved",
    )


@pytest.mark.parametrize(
    ("scenario", "exit_code", "status"),
    [
        ("pass", 0, "PASS"),
        ("warning", 1, "WARNING"),
        ("fail", 2, "FAIL"),
    ],
)
def test_existing_cli_result_contract_remains_compatible(
    tmp_path: Path,
    scenario: str,
    exit_code: int,
    status: str,
) -> None:
    with _server(scenario) as server:
        config = _write_config(
            tmp_path / f"{scenario}.json",
            _config(server),
        )
        output = tmp_path / f"report-{scenario}"
        code = main(_args(output, config))
    report_text = (output / "benchmark_report.json").read_text(
        encoding="utf-8"
    )
    markdown = (output / "benchmark_report.md").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert code == exit_code
    assert report["status"] == status
    assert set(report) == REPORT_KEYS
    for hidden in (
        "synthetic-approval-001",
        "synthetic-validation-001",
        "synthetic-reviewer",
        "synthetic-approver",
    ):
        assert hidden not in report_text + markdown


def test_existing_cli_error_is_safe_and_uses_exit_three(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with _server() as server:
        raw = _config(server)
        selection = raw["compatibility_profile"]
        assert isinstance(selection, dict)
        selection["profile_id"] = "private-product-value"
        config = _write_config(tmp_path / "synthetic.json", raw)
        code = main(_args(tmp_path / "report", config))
        assert server.requests == []
    captured = capsys.readouterr()
    assert code == 3
    assert captured.out == ""
    assert "unknown_profile" in captured.err
    assert "private-product-value" not in captured.err
    assert "Traceback" not in captured.err


def test_request_rejects_unknown_or_missing_security_constraints() -> None:
    with pytest.raises(
        RetrievalAdapterError,
        match="registry_metadata_invalid",
    ):
        replace(
            _request(),
            requested_execution_constraints=("loopback_only",),
        )


def test_result_and_request_repr_do_not_disclose_registry_or_records() -> None:
    request = _request()
    result = evaluate_approval_enforcement(request)
    rendered = repr(request) + repr(result) + repr(request.registry)
    assert rendered == (
        "ApprovalEnforcementRequest(<safe>)"
        "ApprovalEnforcementResult(<safe>)"
        "TrustedProductionRegistry(<safe>)"
    )
    assert "approval" not in rendered.lower().replace(
        "approvalenforcement",
        "",
    )
