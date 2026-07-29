from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar

from ragguard.compatibility import CompatibilityErrorCategory, SemanticVersion
from ragguard.manual_validation_evidence import (
    CloseCleanupEvidence,
    EnvironmentArchitecture,
    EnvironmentOSFamily,
    EvidenceCaseOutcome,
    EvidenceEnvironmentFingerprint,
    EvidenceFailureCategory,
    FailureSummaryCategory,
    ManualEvidenceFailureSummary,
    ManualValidationEvidence,
    ManualValidationEvidenceError,
    ManualValidationEvidenceErrorCategory,
    NonDisclosureEvidence,
    SafeCaseObservation,
)
from ragguard.manual_validation_plan import (
    ManualValidationCase,
    ManualValidationPlan,
    REQUIRED_MANUAL_VALIDATION_CASES,
)


MAX_TOTAL_FIXTURE_BYTES = 65_536
MAX_IDENTIFIER_LENGTH = 64
MAX_SAFE_CONTEXT_LENGTH = 512
MAX_CASE_RESULT_COUNT = len(REQUIRED_MANUAL_VALIDATION_CASES)
MAX_SAFE_OBSERVATION_LENGTH = 32
MAX_FAILURE_SUMMARY_LENGTH = 256
MAX_ENVIRONMENT_FIELD_LENGTH = 64
SHA256_DIGEST_LENGTH = 71
CANONICAL_IMPORT_DIGEST_ALGORITHM = "sha256"

_IMPORT_FIELDS = frozenset(
    {
        "import_id",
        "plan_reference",
        "evidence_identity",
        "identity_binding",
        "execution_timestamps",
        "role_identities",
        "environment_fixture",
        "tool_version",
        "case_result_fixtures",
        "cleanup_declarations",
        "non_disclosure_declarations",
        "failure_summary_fixture",
        "expiry",
        "source_kind",
        "source_digest",
        "safe_context",
    }
)
_PLAN_REFERENCE_FIELDS = frozenset({"plan_id", "plan_digest"})
_EVIDENCE_IDENTITY_FIELDS = frozenset({"evidence_id"})
_IDENTITY_BINDING_FIELDS = frozenset(
    {
        "profile_id",
        "profile_version",
        "protocol_version",
        "product_id",
        "planned_product_version",
        "observed_product_version",
    }
)
_EXECUTION_FIELDS = frozenset({"execution_started_at", "execution_completed_at"})
_ROLE_FIELDS = frozenset({"validation_operator_id", "evidence_reviewer_id"})
_ENVIRONMENT_FIELDS = frozenset(
    {
        "environment_id",
        "os_family",
        "architecture",
        "python_version",
        "ragguard_version",
        "adapter_id",
        "profile_id",
        "declared_digest",
    }
)
_CASE_FIELDS = frozenset(
    {
        "case_id",
        "outcome",
        "executed_at",
        "safe_observation",
        "failure_category",
        "cleanup_confirmed",
    }
)
_CLEANUP_FIELDS = frozenset(
    {
        "transport_closed",
        "close_exactly_once",
        "temporary_safe_fixture_removed",
        "no_raw_payload_retained",
        "no_credential_retained",
        "no_endpoint_detail_retained",
        "safe_summary_produced",
    }
)
_NON_DISCLOSURE_FIELDS = frozenset(
    {
        "no_credential_disclosure",
        "no_endpoint_disclosure",
        "no_path_disclosure",
        "no_raw_request_disclosure",
        "no_raw_response_disclosure",
        "no_real_document_disclosure",
        "no_stack_trace_disclosure",
        "safe_error_only",
    }
)
_FAILURE_SUMMARY_FIELDS = frozenset(
    {"category", "failed_case_count", "aborted_case_count"}
)
_REQUIRED_SAFE_CONTEXT = (
    "manual_validation_not_executed",
    "no_credentials",
    "no_filesystem",
    "no_network",
    "no_real_documents",
    "no_registry_write",
    "no_transport",
    "product_neutral",
    "synthetic_only",
)

_SAFE_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_IMPORT_IDENTIFIER = re.compile(r"manual-import-[a-f0-9]{8,48}\Z")
_EVIDENCE_IDENTIFIER = re.compile(r"manual-evidence-[a-f0-9]{8,48}\Z")
_DIGEST = re.compile(r"sha256:[a-f0-9]{64}\Z")
_SEMANTIC_VERSION = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z"
)
_URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/]")
_RAW_HTTP_HEADER = re.compile(
    r"(?:authorization|cookie|set-cookie|host|x-api-key|content-type)\s*:",
    re.IGNORECASE,
)
_RAW_HTTP_MESSAGE = re.compile(
    r"(?:\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+\S+\s+HTTP/"
    r"|HTTP/[0-9.]+\s+[0-9]{3}\b)",
    re.IGNORECASE,
)
_CREDENTIAL_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization|bearer|cookie|credential|password|secret|token)",
    re.IGNORECASE,
)
_BIDI_CONTROLS = frozenset(
    chr(codepoint)
    for codepoint in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))
)


class ManualEvidenceSourceKind(str, Enum):
    INLINE_SAFE_FIXTURE = "inline_safe_fixture"


_STRUCTURAL_SAFE_VALUES = frozenset(
    {
        *_REQUIRED_SAFE_CONTEXT,
        *(item.value for item in ManualValidationCase),
        *(item.value for item in EvidenceCaseOutcome),
        *(item.value for item in SafeCaseObservation),
        *(item.value for item in EvidenceFailureCategory),
        *(item.value for item in FailureSummaryCategory),
        *(item.value for item in EnvironmentOSFamily),
        *(item.value for item in EnvironmentArchitecture),
        *(item.value for item in ManualEvidenceSourceKind),
    }
)


class ManualEvidenceImportErrorCategory(str, Enum):
    INPUT_TYPE_INVALID = "input_type_invalid"
    SCHEMA_INVALID = "schema_invalid"
    UNKNOWN_FIELD = "unknown_field"
    REQUIRED_FIELD_MISSING = "required_field_missing"
    SIZE_LIMIT_EXCEEDED = "size_limit_exceeded"
    IDENTIFIER_INVALID = "identifier_invalid"
    VERSION_INVALID = "version_invalid"
    TIMESTAMP_INVALID = "timestamp_invalid"
    DIGEST_INVALID = "digest_invalid"
    PLAN_BINDING_INVALID = "plan_binding_invalid"
    CASE_SET_INVALID = "case_set_invalid"
    CASE_RESULT_INVALID = "case_result_invalid"
    ENVIRONMENT_INVALID = "environment_invalid"
    CLEANUP_INVALID = "cleanup_invalid"
    NON_DISCLOSURE_INVALID = "non_disclosure_invalid"
    UNSAFE_CONTENT = "unsafe_content"
    EVIDENCE_CONSTRUCTION_FAILED = "evidence_construction_failed"


_ERROR_ORDER = tuple(ManualEvidenceImportErrorCategory)


class ManualEvidenceImportError(ValueError):
    def __init__(self, category: ManualEvidenceImportErrorCategory) -> None:
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True)
class _PlanReference:
    plan_id: str
    plan_digest: str


@dataclass(frozen=True)
class _EvidenceIdentity:
    evidence_id: str


@dataclass(frozen=True)
class _IdentityBinding:
    profile_id: str
    profile_version: SemanticVersion
    protocol_version: SemanticVersion
    product_id: str
    planned_product_version: SemanticVersion
    observed_product_version: SemanticVersion


@dataclass(frozen=True)
class _ExecutionTimestamps:
    execution_started_at: datetime
    execution_completed_at: datetime


@dataclass(frozen=True)
class _RoleIdentities:
    validation_operator_id: str
    evidence_reviewer_id: str


@dataclass(frozen=True, repr=False)
class _EnvironmentFixture:
    environment_id: str
    os_family: EnvironmentOSFamily
    architecture: EnvironmentArchitecture
    python_version: SemanticVersion
    ragguard_version: SemanticVersion
    adapter_id: str
    profile_id: str
    declared_digest: str

    def phase_b_mapping(self) -> dict[str, str]:
        return {
            "environment_id": self.environment_id,
            "os_family": self.os_family.value,
            "architecture": self.architecture.value,
            "python_version": str(self.python_version),
            "ragguard_version": str(self.ragguard_version),
            "adapter_id": self.adapter_id,
            "profile_id": self.profile_id,
        }

    def canonical_mapping(self) -> dict[str, str]:
        return {**self.phase_b_mapping(), "declared_digest": self.declared_digest}

    def __repr__(self) -> str:
        return (
            "_EnvironmentFixture("
            f"os_family={self.os_family.value!r}, "
            f"architecture={self.architecture.value!r}, "
            f"declared_digest={self.declared_digest!r})"
        )


@dataclass(frozen=True, repr=False)
class _CaseResultFixture:
    case_id: ManualValidationCase
    outcome: EvidenceCaseOutcome
    executed_at: datetime
    safe_observation: SafeCaseObservation
    failure_category: EvidenceFailureCategory | None
    cleanup_confirmed: bool

    def canonical_mapping(self) -> dict[str, object]:
        return {
            "case_id": self.case_id.value,
            "outcome": self.outcome.value,
            "executed_at": _canonical_datetime(self.executed_at),
            "safe_observation": self.safe_observation.value,
            "failure_category": (
                None
                if self.failure_category is None
                else self.failure_category.value
            ),
            "cleanup_confirmed": self.cleanup_confirmed,
        }

    def __repr__(self) -> str:
        return (
            "_CaseResultFixture("
            f"case_id={self.case_id.value!r}, outcome={self.outcome.value!r})"
        )


@dataclass(frozen=True)
class ManualEvidenceImportSafeSummary:
    import_id: str
    accepted: bool
    source_kind: str
    source_digest: str
    evidence_id: str
    evidence_digest: str | None
    plan_id: str
    plan_digest: str
    case_count: int
    passed_count: int
    failed_count: int
    aborted_count: int
    reason_categories: tuple[str, ...]
    canonical_digest: str


@dataclass(frozen=True, repr=False)
class ManualEvidenceImportRequest:
    import_id: str
    plan_reference: _PlanReference
    evidence_identity: _EvidenceIdentity
    identity_binding: _IdentityBinding
    execution_timestamps: _ExecutionTimestamps
    role_identities: _RoleIdentities
    environment_fixture: _EnvironmentFixture = field(repr=False)
    tool_version: SemanticVersion
    case_result_fixtures: tuple[_CaseResultFixture, ...] = field(repr=False)
    cleanup_declarations: CloseCleanupEvidence
    non_disclosure_declarations: NonDisclosureEvidence
    failure_summary_fixture: ManualEvidenceFailureSummary | None
    expiry: datetime
    source_kind: ManualEvidenceSourceKind
    source_digest: str
    safe_context: tuple[str, ...]
    source_canonical_json: str = field(init=False, repr=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_IMPORT_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            not isinstance(self.import_id, str)
            or _IMPORT_IDENTIFIER.fullmatch(self.import_id) is None
        ):
            _raise(ManualEvidenceImportErrorCategory.IDENTIFIER_INVALID)
        if not isinstance(self.source_kind, ManualEvidenceSourceKind):
            _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
        if not _is_digest(self.source_digest):
            _raise(ManualEvidenceImportErrorCategory.DIGEST_INVALID)
        if (
            not isinstance(self.plan_reference, _PlanReference)
            or not isinstance(self.evidence_identity, _EvidenceIdentity)
            or not isinstance(self.identity_binding, _IdentityBinding)
            or not isinstance(self.execution_timestamps, _ExecutionTimestamps)
            or not isinstance(self.role_identities, _RoleIdentities)
            or not isinstance(self.environment_fixture, _EnvironmentFixture)
            or not isinstance(self.tool_version, SemanticVersion)
            or not isinstance(self.case_result_fixtures, tuple)
            or any(
                not isinstance(item, _CaseResultFixture)
                for item in self.case_result_fixtures
            )
            or not isinstance(self.cleanup_declarations, CloseCleanupEvidence)
            or not isinstance(
                self.non_disclosure_declarations, NonDisclosureEvidence
            )
            or (
                self.failure_summary_fixture is not None
                and not isinstance(
                    self.failure_summary_fixture,
                    ManualEvidenceFailureSummary,
                )
            )
        ):
            _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
        if self.safe_context != _REQUIRED_SAFE_CONTEXT:
            _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
        canonical_source = _canonical_json(self.source_mapping())
        calculated_source_digest = _digest(canonical_source)
        if calculated_source_digest != self.source_digest:
            _raise(ManualEvidenceImportErrorCategory.DIGEST_INVALID)
        object.__setattr__(self, "source_canonical_json", canonical_source)
        object.__setattr__(
            self,
            "canonical_digest",
            _digest(
                _canonical_json(
                    {
                        "source": json.loads(canonical_source),
                        "source_digest": self.source_digest,
                    }
                )
            ),
        )

    @classmethod
    def from_mapping(cls, value: object) -> ManualEvidenceImportRequest:
        raw = _require_root_mapping(value)
        _reject_unknown_or_missing(raw, _IMPORT_FIELDS)
        _reject_unsafe_content(raw)

        plan_reference_raw = _require_mapping(
            raw["plan_reference"], _PLAN_REFERENCE_FIELDS
        )
        evidence_identity_raw = _require_mapping(
            raw["evidence_identity"], _EVIDENCE_IDENTITY_FIELDS
        )
        identity_raw = _require_mapping(
            raw["identity_binding"], _IDENTITY_BINDING_FIELDS
        )
        execution_raw = _require_mapping(
            raw["execution_timestamps"], _EXECUTION_FIELDS
        )
        roles_raw = _require_mapping(raw["role_identities"], _ROLE_FIELDS)
        environment_raw = _require_mapping(
            raw["environment_fixture"], _ENVIRONMENT_FIELDS
        )
        cleanup_raw = _require_mapping(
            raw["cleanup_declarations"], _CLEANUP_FIELDS
        )
        non_disclosure_raw = _require_mapping(
            raw["non_disclosure_declarations"], _NON_DISCLOSURE_FIELDS
        )

        import_id = _identifier(
            raw["import_id"], pattern=_IMPORT_IDENTIFIER
        )
        plan_reference = _PlanReference(
            plan_id=_identifier(plan_reference_raw["plan_id"]),
            plan_digest=_digest_value(plan_reference_raw["plan_digest"]),
        )
        evidence_identity = _EvidenceIdentity(
            evidence_id=_identifier(
                evidence_identity_raw["evidence_id"],
                pattern=_EVIDENCE_IDENTIFIER,
            )
        )
        identity_binding = _IdentityBinding(
            profile_id=_identifier(identity_raw["profile_id"]),
            profile_version=_version(identity_raw["profile_version"]),
            protocol_version=_version(identity_raw["protocol_version"]),
            product_id=_identifier(identity_raw["product_id"]),
            planned_product_version=_version(
                identity_raw["planned_product_version"]
            ),
            observed_product_version=_version(
                identity_raw["observed_product_version"]
            ),
        )
        execution_timestamps = _ExecutionTimestamps(
            execution_started_at=_timestamp(
                execution_raw["execution_started_at"]
            ),
            execution_completed_at=_timestamp(
                execution_raw["execution_completed_at"]
            ),
        )
        if (
            execution_timestamps.execution_started_at
            >= execution_timestamps.execution_completed_at
        ):
            _raise(ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID)
        role_identities = _RoleIdentities(
            validation_operator_id=_identifier(
                roles_raw["validation_operator_id"]
            ),
            evidence_reviewer_id=_identifier(
                roles_raw["evidence_reviewer_id"]
            ),
        )
        if (
            role_identities.validation_operator_id
            == role_identities.evidence_reviewer_id
        ):
            _raise(ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID)

        environment_fixture = _environment_fixture(environment_raw)
        case_result_fixtures = _case_fixtures(raw["case_result_fixtures"])
        cleanup_declarations = _cleanup_declarations(cleanup_raw)
        non_disclosure_declarations = _non_disclosure_declarations(
            non_disclosure_raw
        )
        failure_summary = _failure_summary(raw["failure_summary_fixture"])
        expiry = _timestamp(raw["expiry"])
        if (
            execution_timestamps.execution_completed_at >= expiry
            or expiry - execution_timestamps.execution_completed_at
            > timedelta(days=90)
        ):
            _raise(ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID)

        try:
            source_kind = ManualEvidenceSourceKind(raw["source_kind"])
        except (TypeError, ValueError):
            _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
        source_digest = _digest_value(raw["source_digest"])
        safe_context = _safe_context(raw["safe_context"])

        return cls(
            import_id=import_id,
            plan_reference=plan_reference,
            evidence_identity=evidence_identity,
            identity_binding=identity_binding,
            execution_timestamps=execution_timestamps,
            role_identities=role_identities,
            environment_fixture=environment_fixture,
            tool_version=_version(raw["tool_version"]),
            case_result_fixtures=case_result_fixtures,
            cleanup_declarations=cleanup_declarations,
            non_disclosure_declarations=non_disclosure_declarations,
            failure_summary_fixture=failure_summary,
            expiry=expiry,
            source_kind=source_kind,
            source_digest=source_digest,
            safe_context=safe_context,
        )

    def source_mapping(self) -> dict[str, object]:
        return {
            "case_result_fixtures": [
                result.canonical_mapping()
                for result in self.case_result_fixtures
            ],
            "cleanup_declarations": {
                name: getattr(self.cleanup_declarations, name)
                for name in sorted(_CLEANUP_FIELDS)
            },
            "environment_fixture": self.environment_fixture.canonical_mapping(),
            "evidence_identity": {
                "evidence_id": self.evidence_identity.evidence_id
            },
            "execution_timestamps": {
                "execution_completed_at": _canonical_datetime(
                    self.execution_timestamps.execution_completed_at
                ),
                "execution_started_at": _canonical_datetime(
                    self.execution_timestamps.execution_started_at
                ),
            },
            "expiry": _canonical_datetime(self.expiry),
            "failure_summary_fixture": (
                None
                if self.failure_summary_fixture is None
                else {
                    "aborted_case_count": (
                        self.failure_summary_fixture.aborted_case_count
                    ),
                    "category": self.failure_summary_fixture.category.value,
                    "failed_case_count": (
                        self.failure_summary_fixture.failed_case_count
                    ),
                }
            ),
            "identity_binding": {
                "observed_product_version": str(
                    self.identity_binding.observed_product_version
                ),
                "planned_product_version": str(
                    self.identity_binding.planned_product_version
                ),
                "product_id": self.identity_binding.product_id,
                "profile_id": self.identity_binding.profile_id,
                "profile_version": str(self.identity_binding.profile_version),
                "protocol_version": str(self.identity_binding.protocol_version),
            },
            "import_id": self.import_id,
            "non_disclosure_declarations": {
                name: getattr(self.non_disclosure_declarations, name)
                for name in sorted(_NON_DISCLOSURE_FIELDS)
            },
            "plan_reference": {
                "plan_digest": self.plan_reference.plan_digest,
                "plan_id": self.plan_reference.plan_id,
            },
            "role_identities": {
                "evidence_reviewer_id": (
                    self.role_identities.evidence_reviewer_id
                ),
                "validation_operator_id": (
                    self.role_identities.validation_operator_id
                ),
            },
            "safe_context": list(self.safe_context),
            "source_kind": self.source_kind.value,
            "tool_version": str(self.tool_version),
        }

    def __repr__(self) -> str:
        digest = getattr(self, "canonical_digest", "<unavailable>")
        return (
            "ManualEvidenceImportRequest("
            f"import_id={self.import_id!r}, "
            f"source_kind={self.source_kind.value!r}, "
            f"canonical_digest={digest!r})"
        )


@dataclass(frozen=True, repr=False)
class ManualEvidenceImportResult:
    import_id: str
    accepted: bool
    source_kind: ManualEvidenceSourceKind
    source_digest: str
    evidence_id: str
    evidence_digest: str | None
    plan_id: str
    plan_digest: str
    reason_categories: tuple[ManualEvidenceImportErrorCategory, ...]
    evidence: ManualValidationEvidence | None = field(repr=False)
    safe_summary: ManualEvidenceImportSafeSummary = field(init=False)
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_IMPORT_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if (
            type(self.accepted) is not bool
            or not isinstance(self.source_kind, ManualEvidenceSourceKind)
            or not _is_digest(self.source_digest)
            or not _is_digest(self.plan_digest)
            or (
                self.evidence_digest is not None
                and not _is_digest(self.evidence_digest)
            )
        ):
            _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
        reasons = _canonical_reasons(self.reason_categories)
        object.__setattr__(self, "reason_categories", reasons)
        if self.accepted:
            if (
                not isinstance(self.evidence, ManualValidationEvidence)
                or self.evidence.canonical_digest != self.evidence_digest
                or reasons
            ):
                _raise(
                    ManualEvidenceImportErrorCategory.EVIDENCE_CONSTRUCTION_FAILED
                )
        elif (
            self.evidence is not None
            or self.evidence_digest is not None
            or not reasons
        ):
            _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)

        counts = _result_counts(self.evidence)
        payload = {
            "accepted": self.accepted,
            "evidence_digest": self.evidence_digest,
            "evidence_id": self.evidence_id,
            "import_id": self.import_id,
            "plan_digest": self.plan_digest,
            "plan_id": self.plan_id,
            "reason_categories": [reason.value for reason in reasons],
            "source_digest": self.source_digest,
            "source_kind": self.source_kind.value,
        }
        digest = _digest(_canonical_json(payload))
        object.__setattr__(self, "canonical_digest", digest)
        object.__setattr__(
            self,
            "safe_summary",
            ManualEvidenceImportSafeSummary(
                import_id=self.import_id,
                accepted=self.accepted,
                source_kind=self.source_kind.value,
                source_digest=self.source_digest,
                evidence_id=self.evidence_id,
                evidence_digest=self.evidence_digest,
                plan_id=self.plan_id,
                plan_digest=self.plan_digest,
                case_count=counts[0],
                passed_count=counts[1],
                failed_count=counts[2],
                aborted_count=counts[3],
                reason_categories=tuple(reason.value for reason in reasons),
                canonical_digest=digest,
            ),
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "accepted": self.accepted,
                "evidence_digest": self.evidence_digest,
                "evidence_id": self.evidence_id,
                "import_id": self.import_id,
                "plan_digest": self.plan_digest,
                "plan_id": self.plan_id,
                "reason_categories": [
                    reason.value for reason in self.reason_categories
                ],
                "source_digest": self.source_digest,
                "source_kind": self.source_kind.value,
            }
        )

    def __repr__(self) -> str:
        digest = getattr(self, "canonical_digest", "<unavailable>")
        return (
            "ManualEvidenceImportResult("
            f"import_id={self.import_id!r}, accepted={self.accepted!r}, "
            f"reason_categories="
            f"{tuple(reason.value for reason in self.reason_categories)!r}, "
            f"canonical_digest={digest!r})"
        )


def import_manual_validation_evidence(
    request: ManualEvidenceImportRequest,
    *,
    plan: ManualValidationPlan,
) -> ManualEvidenceImportResult:
    if not isinstance(request, ManualEvidenceImportRequest):
        _raise(ManualEvidenceImportErrorCategory.INPUT_TYPE_INVALID)
    if not isinstance(plan, ManualValidationPlan):
        _raise(ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID)

    binding_error = _plan_binding_error(request, plan)
    if binding_error is not None:
        return _rejected_result(request, binding_error)

    evidence_mapping = {
        "evidence_id": request.evidence_identity.evidence_id,
        "plan_id": request.plan_reference.plan_id,
        "plan_digest": request.plan_reference.plan_digest,
        "profile_id": request.identity_binding.profile_id,
        "profile_version": str(request.identity_binding.profile_version),
        "protocol_version": str(request.identity_binding.protocol_version),
        "product_id": request.identity_binding.product_id,
        "planned_product_version": str(
            request.identity_binding.planned_product_version
        ),
        "observed_product_version": str(
            request.identity_binding.observed_product_version
        ),
        "execution_started_at": _canonical_datetime(
            request.execution_timestamps.execution_started_at
        ),
        "execution_completed_at": _canonical_datetime(
            request.execution_timestamps.execution_completed_at
        ),
        "validation_operator_id": (
            request.role_identities.validation_operator_id
        ),
        "evidence_reviewer_id": request.role_identities.evidence_reviewer_id,
        "environment_fingerprint": request.environment_fixture.phase_b_mapping(),
        "tool_version": str(request.tool_version),
        "case_results": [
            result.canonical_mapping()
            for result in request.case_result_fixtures
        ],
        "close_cleanup_evidence": {
            name: getattr(request.cleanup_declarations, name)
            for name in _CLEANUP_FIELDS
        },
        "non_disclosure_evidence": {
            name: getattr(request.non_disclosure_declarations, name)
            for name in _NON_DISCLOSURE_FIELDS
        },
        "failure_summary": (
            None
            if request.failure_summary_fixture is None
            else {
                "category": request.failure_summary_fixture.category.value,
                "failed_case_count": (
                    request.failure_summary_fixture.failed_case_count
                ),
                "aborted_case_count": (
                    request.failure_summary_fixture.aborted_case_count
                ),
            }
        ),
        "expires_at": _canonical_datetime(request.expiry),
    }
    try:
        evidence = ManualValidationEvidence.from_mapping(
            evidence_mapping, plan=plan
        )
    except ManualValidationEvidenceError as exc:
        return _rejected_result(request, _map_evidence_error(exc.category))
    except Exception:
        return _rejected_result(
            request,
            ManualEvidenceImportErrorCategory.EVIDENCE_CONSTRUCTION_FAILED,
        )

    return ManualEvidenceImportResult(
        import_id=request.import_id,
        accepted=True,
        source_kind=request.source_kind,
        source_digest=request.source_digest,
        evidence_id=evidence.evidence_id,
        evidence_digest=evidence.canonical_digest,
        plan_id=evidence.plan_id,
        plan_digest=evidence.plan_digest,
        reason_categories=(),
        evidence=evidence,
    )


def _require_root_mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _raise(ManualEvidenceImportErrorCategory.INPUT_TYPE_INVALID)
    try:
        serialized = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    except (TypeError, ValueError, RecursionError):
        _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
    if len(serialized.encode("utf-8")) > MAX_TOTAL_FIXTURE_BYTES:
        _raise(ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED)
    return value


def _require_mapping(
    value: object, fields: frozenset[str]
) -> dict[str, object]:
    if type(value) is not dict:
        _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
    _reject_unknown_or_missing(value, fields)
    return value


def _reject_unknown_or_missing(
    value: dict[str, object], fields: frozenset[str]
) -> None:
    actual = set(value)
    if actual - fields:
        _raise(ManualEvidenceImportErrorCategory.UNKNOWN_FIELD)
    if fields - actual:
        _raise(ManualEvidenceImportErrorCategory.REQUIRED_FIELD_MISSING)


def _identifier(
    value: object, *, pattern: re.Pattern[str] = _SAFE_IDENTIFIER
) -> str:
    if isinstance(value, str) and len(value) > MAX_IDENTIFIER_LENGTH:
        _raise(ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED)
    if (
        not isinstance(value, str)
        or pattern.fullmatch(value) is None
    ):
        _raise(ManualEvidenceImportErrorCategory.IDENTIFIER_INVALID)
    return value


def _version(value: object) -> SemanticVersion:
    if isinstance(value, str) and len(value) > MAX_ENVIRONMENT_FIELD_LENGTH:
        _raise(ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED)
    if (
        not isinstance(value, str)
        or _SEMANTIC_VERSION.fullmatch(value) is None
    ):
        _raise(ManualEvidenceImportErrorCategory.VERSION_INVALID)
    try:
        return SemanticVersion.parse(
            value, category=CompatibilityErrorCategory.INVALID_PROFILE
        )
    except Exception:
        _raise(ManualEvidenceImportErrorCategory.VERSION_INVALID)


def _timestamp(value: object) -> datetime:
    if isinstance(value, str) and len(value) > MAX_ENVIRONMENT_FIELD_LENGTH:
        _raise(ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED)
    if not isinstance(value, str):
        _raise(ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _raise(ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID)
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        _raise(ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID)
    return parsed


def _digest_value(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != SHA256_DIGEST_LENGTH
        or _DIGEST.fullmatch(value) is None
    ):
        _raise(ManualEvidenceImportErrorCategory.DIGEST_INVALID)
    return value


def _environment_fixture(raw: dict[str, object]) -> _EnvironmentFixture:
    try:
        os_family = EnvironmentOSFamily(raw["os_family"])
        architecture = EnvironmentArchitecture(raw["architecture"])
    except (TypeError, ValueError):
        _raise(ManualEvidenceImportErrorCategory.ENVIRONMENT_INVALID)
    fixture = _EnvironmentFixture(
        environment_id=_identifier(raw["environment_id"]),
        os_family=os_family,
        architecture=architecture,
        python_version=_version(raw["python_version"]),
        ragguard_version=_version(raw["ragguard_version"]),
        adapter_id=_identifier(raw["adapter_id"]),
        profile_id=_identifier(raw["profile_id"]),
        declared_digest=_digest_value(raw["declared_digest"]),
    )
    if any(
        len(value) > MAX_ENVIRONMENT_FIELD_LENGTH
        for value in (
            fixture.environment_id,
            fixture.adapter_id,
            fixture.profile_id,
        )
    ):
        _raise(ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED)
    try:
        calculated = EvidenceEnvironmentFingerprint.from_mapping(
            fixture.phase_b_mapping()
        ).canonical_digest
    except Exception:
        _raise(ManualEvidenceImportErrorCategory.ENVIRONMENT_INVALID)
    if calculated != fixture.declared_digest:
        _raise(ManualEvidenceImportErrorCategory.ENVIRONMENT_INVALID)
    return fixture


def _case_fixtures(value: object) -> tuple[_CaseResultFixture, ...]:
    if type(value) is not list:
        _raise(ManualEvidenceImportErrorCategory.CASE_SET_INVALID)
    if len(value) > MAX_CASE_RESULT_COUNT:
        _raise(ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED)
    if len(value) != MAX_CASE_RESULT_COUNT:
        _raise(ManualEvidenceImportErrorCategory.CASE_SET_INVALID)
    parsed: list[_CaseResultFixture] = []
    for item in value:
        raw = _require_mapping(item, _CASE_FIELDS)
        observation_value = raw["safe_observation"]
        if (
            isinstance(observation_value, str)
            and len(observation_value) > MAX_SAFE_OBSERVATION_LENGTH
        ):
            _raise(ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED)
        try:
            case_id = ManualValidationCase(raw["case_id"])
            outcome = EvidenceCaseOutcome(raw["outcome"])
            observation = SafeCaseObservation(observation_value)
            failure = (
                None
                if raw["failure_category"] is None
                else EvidenceFailureCategory(raw["failure_category"])
            )
        except (TypeError, ValueError):
            _raise(ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID)
        cleanup_confirmed = raw["cleanup_confirmed"]
        if type(cleanup_confirmed) is not bool:
            _raise(ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID)
        expected_observation = {
            EvidenceCaseOutcome.PASSED: SafeCaseObservation.CASE_PASSED,
            EvidenceCaseOutcome.FAILED: SafeCaseObservation.CASE_FAILED,
            EvidenceCaseOutcome.ABORTED: SafeCaseObservation.CASE_ABORTED,
        }[outcome]
        if (
            observation is not expected_observation
            or (outcome is EvidenceCaseOutcome.PASSED and failure is not None)
            or (
                outcome is not EvidenceCaseOutcome.PASSED
                and failure is None
            )
        ):
            _raise(ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID)
        parsed.append(
            _CaseResultFixture(
                case_id=case_id,
                outcome=outcome,
                executed_at=_timestamp(raw["executed_at"]),
                safe_observation=observation,
                failure_category=failure,
                cleanup_confirmed=cleanup_confirmed,
            )
        )
    case_ids = tuple(item.case_id for item in parsed)
    if (
        len(case_ids) != len(set(case_ids))
        or set(case_ids) != set(REQUIRED_MANUAL_VALIDATION_CASES)
    ):
        _raise(ManualEvidenceImportErrorCategory.CASE_SET_INVALID)
    by_id = {item.case_id: item for item in parsed}
    return tuple(by_id[case_id] for case_id in REQUIRED_MANUAL_VALIDATION_CASES)


def _cleanup_declarations(raw: dict[str, object]) -> CloseCleanupEvidence:
    if any(type(raw[name]) is not bool for name in _CLEANUP_FIELDS):
        _raise(ManualEvidenceImportErrorCategory.CLEANUP_INVALID)
    try:
        return CloseCleanupEvidence.from_mapping(raw)
    except Exception:
        _raise(ManualEvidenceImportErrorCategory.CLEANUP_INVALID)


def _non_disclosure_declarations(
    raw: dict[str, object],
) -> NonDisclosureEvidence:
    if any(type(raw[name]) is not bool for name in _NON_DISCLOSURE_FIELDS):
        _raise(ManualEvidenceImportErrorCategory.NON_DISCLOSURE_INVALID)
    try:
        return NonDisclosureEvidence.from_mapping(raw)
    except Exception:
        _raise(ManualEvidenceImportErrorCategory.NON_DISCLOSURE_INVALID)


def _failure_summary(value: object) -> ManualEvidenceFailureSummary | None:
    if value is None:
        return None
    raw = _require_mapping(value, _FAILURE_SUMMARY_FIELDS)
    if len(_canonical_json(raw)) > MAX_FAILURE_SUMMARY_LENGTH:
        _raise(ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED)
    if (
        type(raw["failed_case_count"]) is not int
        or type(raw["aborted_case_count"]) is not int
    ):
        _raise(ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID)
    try:
        return ManualEvidenceFailureSummary(
            category=FailureSummaryCategory(raw["category"]),
            failed_case_count=raw["failed_case_count"],
            aborted_case_count=raw["aborted_case_count"],
        )
    except Exception:
        _raise(ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID)


def _safe_context(value: object) -> tuple[str, ...]:
    if type(value) is not list or any(not isinstance(item, str) for item in value):
        _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
    if sum(len(item) for item in value) > MAX_SAFE_CONTEXT_LENGTH:
        _raise(ManualEvidenceImportErrorCategory.SIZE_LIMIT_EXCEEDED)
    if len(value) != len(set(value)) or set(value) != set(_REQUIRED_SAFE_CONTEXT):
        _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
    return _REQUIRED_SAFE_CONTEXT


def _reject_unsafe_content(value: object) -> None:
    for text in _walk_strings(value):
        if _is_unsafe_string(text):
            _raise(ManualEvidenceImportErrorCategory.UNSAFE_CONTENT)


def _walk_strings(value: object, *, depth: int = 0):
    if depth > 6:
        _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
    if isinstance(value, str):
        yield value
    elif type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str):
                _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
            yield from _walk_strings(item, depth=depth + 1)
    elif type(value) is list:
        for item in value:
            yield from _walk_strings(item, depth=depth + 1)
    elif value is None or type(value) in (bool, int):
        return
    else:
        _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)


def _is_unsafe_string(value: str) -> bool:
    if value in _STRUCTURAL_SAFE_VALUES:
        return False
    if (
        "\x00" in value
        or any(character in _BIDI_CONTROLS for character in value)
        or any(ord(character) < 0x20 for character in value)
        or _URL_SCHEME.search(value)
        or _WINDOWS_PATH.search(value)
        or value.startswith("/")
        or "../" in value
        or "..\\" in value
        or _RAW_HTTP_HEADER.search(value)
        or _RAW_HTTP_MESSAGE.search(value)
        or _CREDENTIAL_PATTERN.search(value)
        or "-----BEGIN " in value
        or "Traceback (most recent call last):" in value
        or "\r" in value
    ):
        return True
    try:
        ipaddress.ip_address(value.strip("[]"))
    except ValueError:
        return False
    return True


def _plan_binding_error(
    request: ManualEvidenceImportRequest,
    plan: ManualValidationPlan,
) -> ManualEvidenceImportErrorCategory | None:
    if (
        request.plan_reference.plan_id != plan.plan_id
        or request.plan_reference.plan_digest != plan.canonical_digest
        or request.identity_binding.profile_id != plan.profile_id
        or request.identity_binding.profile_version != plan.profile_version
        or request.identity_binding.protocol_version != plan.protocol_version
        or request.identity_binding.product_id != plan.product_id
        or request.identity_binding.planned_product_version
        != plan.product_version
        or request.identity_binding.observed_product_version
        != plan.product_version
    ):
        return ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID
    if (
        request.role_identities.validation_operator_id
        != plan.validation_operator_id
        or request.role_identities.evidence_reviewer_id
        != plan.evidence_reviewer_id
    ):
        return ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID
    if (
        request.environment_fixture.profile_id != plan.profile_id
        or request.tool_version
        != request.environment_fixture.ragguard_version
    ):
        return ManualEvidenceImportErrorCategory.ENVIRONMENT_INVALID
    if (
        request.execution_timestamps.execution_started_at
        < plan.execution_window_start
        or request.execution_timestamps.execution_completed_at
        > plan.execution_window_end
    ):
        return ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID
    if tuple(item.case_id for item in request.case_result_fixtures) != tuple(
        plan.required_case_ids
    ):
        return ManualEvidenceImportErrorCategory.CASE_SET_INVALID
    return None


def _map_evidence_error(
    category: ManualValidationEvidenceErrorCategory,
) -> ManualEvidenceImportErrorCategory:
    mapping = {
        ManualValidationEvidenceErrorCategory.FIELD_SET_INVALID: (
            ManualEvidenceImportErrorCategory.SCHEMA_INVALID
        ),
        ManualValidationEvidenceErrorCategory.IDENTITY_INVALID: (
            ManualEvidenceImportErrorCategory.IDENTIFIER_INVALID
        ),
        ManualValidationEvidenceErrorCategory.VERSION_INVALID: (
            ManualEvidenceImportErrorCategory.VERSION_INVALID
        ),
        ManualValidationEvidenceErrorCategory.PLAN_BINDING_INVALID: (
            ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID
        ),
        ManualValidationEvidenceErrorCategory.ROLE_BINDING_INVALID: (
            ManualEvidenceImportErrorCategory.PLAN_BINDING_INVALID
        ),
        ManualValidationEvidenceErrorCategory.EXECUTION_TIME_INVALID: (
            ManualEvidenceImportErrorCategory.TIMESTAMP_INVALID
        ),
        ManualValidationEvidenceErrorCategory.CASE_RESULTS_INVALID: (
            ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID
        ),
        ManualValidationEvidenceErrorCategory.ENVIRONMENT_FINGERPRINT_INVALID: (
            ManualEvidenceImportErrorCategory.ENVIRONMENT_INVALID
        ),
        ManualValidationEvidenceErrorCategory.TOOL_VERSION_INVALID: (
            ManualEvidenceImportErrorCategory.VERSION_INVALID
        ),
        ManualValidationEvidenceErrorCategory.CLEANUP_EVIDENCE_INVALID: (
            ManualEvidenceImportErrorCategory.CLEANUP_INVALID
        ),
        ManualValidationEvidenceErrorCategory.NON_DISCLOSURE_EVIDENCE_INVALID: (
            ManualEvidenceImportErrorCategory.NON_DISCLOSURE_INVALID
        ),
        ManualValidationEvidenceErrorCategory.FAILURE_SUMMARY_INVALID: (
            ManualEvidenceImportErrorCategory.CASE_RESULT_INVALID
        ),
    }
    return mapping.get(
        category,
        ManualEvidenceImportErrorCategory.EVIDENCE_CONSTRUCTION_FAILED,
    )


def _rejected_result(
    request: ManualEvidenceImportRequest,
    reason: ManualEvidenceImportErrorCategory,
) -> ManualEvidenceImportResult:
    return ManualEvidenceImportResult(
        import_id=request.import_id,
        accepted=False,
        source_kind=request.source_kind,
        source_digest=request.source_digest,
        evidence_id=request.evidence_identity.evidence_id,
        evidence_digest=None,
        plan_id=request.plan_reference.plan_id,
        plan_digest=request.plan_reference.plan_digest,
        reason_categories=(reason,),
        evidence=None,
    )


def _canonical_reasons(
    reasons: object,
) -> tuple[ManualEvidenceImportErrorCategory, ...]:
    if not isinstance(reasons, tuple):
        _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
    if any(
        not isinstance(reason, ManualEvidenceImportErrorCategory)
        for reason in reasons
    ):
        _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
    if len(reasons) != len(set(reasons)):
        _raise(ManualEvidenceImportErrorCategory.SCHEMA_INVALID)
    reason_set = set(reasons)
    return tuple(reason for reason in _ERROR_ORDER if reason in reason_set)


def _result_counts(
    evidence: ManualValidationEvidence | None,
) -> tuple[int, int, int, int]:
    if evidence is None:
        return 0, 0, 0, 0
    passed = sum(
        item.outcome is EvidenceCaseOutcome.PASSED
        for item in evidence.case_results
    )
    failed = sum(
        item.outcome is EvidenceCaseOutcome.FAILED
        for item in evidence.case_results
    )
    aborted = sum(
        item.outcome is EvidenceCaseOutcome.ABORTED
        for item in evidence.case_results
    )
    return len(evidence.case_results), passed, failed, aborted


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_DIGEST_LENGTH
        and _DIGEST.fullmatch(value) is not None
    )


def _canonical_datetime(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def _digest(value: str) -> str:
    return (
        f"{CANONICAL_IMPORT_DIGEST_ALGORITHM}:"
        f"{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
    )


def _raise(category: ManualEvidenceImportErrorCategory) -> None:
    raise ManualEvidenceImportError(category) from None


__all__ = [
    "CANONICAL_IMPORT_DIGEST_ALGORITHM",
    "MAX_CASE_RESULT_COUNT",
    "MAX_ENVIRONMENT_FIELD_LENGTH",
    "MAX_FAILURE_SUMMARY_LENGTH",
    "MAX_IDENTIFIER_LENGTH",
    "MAX_SAFE_CONTEXT_LENGTH",
    "MAX_SAFE_OBSERVATION_LENGTH",
    "MAX_TOTAL_FIXTURE_BYTES",
    "ManualEvidenceImportError",
    "ManualEvidenceImportErrorCategory",
    "ManualEvidenceImportRequest",
    "ManualEvidenceImportResult",
    "ManualEvidenceImportSafeSummary",
    "ManualEvidenceSourceKind",
    "SHA256_DIGEST_LENGTH",
    "import_manual_validation_evidence",
]
