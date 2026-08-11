from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar, Mapping

from ragguard.compatibility import SemanticVersion
from ragguard.manual_validation_plan import ManualValidationPlan


CANONICAL_MANUAL_VALIDATION_EXECUTION_DIGEST_ALGORITHM = "sha256"
MAX_EXECUTION_EVIDENCE_AGE = timedelta(days=90)

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ManualValidationExecutionErrorCategory(str, Enum):
    INVALID_CONTRACT = "manual_validation_execution_contract_invalid"
    INVALID_IDENTITY = "manual_validation_execution_identity_invalid"
    INVALID_DIGEST = "manual_validation_execution_digest_invalid"
    INVALID_VERSION = "manual_validation_execution_version_invalid"
    INVALID_TIME = "manual_validation_execution_time_invalid"
    PLAN_MISMATCH = "manual_validation_execution_plan_mismatch"
    FIXTURE_MISMATCH = "manual_validation_execution_fixture_mismatch"
    ENVIRONMENT_UNSAFE = "manual_validation_execution_environment_unsafe"
    TEST_CASE_SET_MISMATCH = "manual_validation_execution_test_case_set_mismatch"
    PARTIAL_EXECUTION = "manual_validation_execution_partial"
    ROLE_CONFLICT = "manual_validation_execution_role_conflict"
    CHAIN_MISMATCH = "manual_validation_execution_chain_mismatch"
    REPLAY = "manual_validation_execution_replay"
    STALE = "manual_validation_execution_stale"
    FUTURE_METADATA = "manual_validation_execution_future_metadata"
    COMMIT_FAILED = "manual_validation_execution_commit_failed"


class ManualValidationExecutionError(ValueError):
    def __init__(self, category: ManualValidationExecutionErrorCategory) -> None:
        self.category = category
        super().__init__(category.value)


class ValidationFixtureKind(str, Enum):
    SYNTHETIC = "synthetic"
    CONTROLLED = "controlled"


class ManualExecutionResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    REJECTED = "rejected"


class ManualEvidenceKind(str, Enum):
    SYNTHETIC_EXECUTION = "synthetic_execution"
    CONTROLLED_MANUAL_EXECUTION = "controlled_manual_execution"


class EvidenceCompleteness(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class ManualReviewResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_RERUN = "needs_rerun"


class ManualApprovalResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ManualValidationExecutionRequest:
    execution_request_id: str
    validation_plan_digest: str
    profile_id: str
    profile_version: SemanticVersion
    product_id: str
    product_version: SemanticVersion
    protocol_version: SemanticVersion
    requested_at: datetime
    requested_by: str
    execution_operator_id: str
    expected_fixture_manifest_digest: str
    expected_test_case_set_digest: str
    expected_environment_contract_digest: str
    use_current_alias: bool = False
    use_latest_alias: bool = False
    allow_fallback: bool = False
    allow_version_inference: bool = False
    allow_hidden_defaults: bool = False
    canonical_digest: str = field(init=False)

    digest_algorithm: ClassVar[str] = CANONICAL_MANUAL_VALIDATION_EXECUTION_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if not all(
            _is_identifier(value)
            for value in (
                self.execution_request_id,
                self.profile_id,
                self.product_id,
                self.requested_by,
                self.execution_operator_id,
            )
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_IDENTITY)
        if not all(
            _is_digest(value)
            for value in (
                self.validation_plan_digest,
                self.expected_fixture_manifest_digest,
                self.expected_test_case_set_digest,
                self.expected_environment_contract_digest,
            )
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_DIGEST)
        if not all(
            isinstance(value, SemanticVersion)
            for value in (self.profile_version, self.product_version, self.protocol_version)
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_VERSION)
        if not _is_aware(self.requested_at):
            _raise(ManualValidationExecutionErrorCategory.INVALID_TIME)
        flags = (
            self.use_current_alias,
            self.use_latest_alias,
            self.allow_fallback,
            self.allow_version_inference,
            self.allow_hidden_defaults,
        )
        if any(type(value) is not bool for value in flags) or any(flags):
            _raise(ManualValidationExecutionErrorCategory.INVALID_VERSION)
        if self.requested_by == self.execution_operator_id:
            _raise(ManualValidationExecutionErrorCategory.ROLE_CONFLICT)
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "allow_fallback": self.allow_fallback,
                "allow_hidden_defaults": self.allow_hidden_defaults,
                "allow_version_inference": self.allow_version_inference,
                "execution_operator_id": self.execution_operator_id,
                "execution_request_id": self.execution_request_id,
                "expected_environment_contract_digest": self.expected_environment_contract_digest,
                "expected_fixture_manifest_digest": self.expected_fixture_manifest_digest,
                "expected_test_case_set_digest": self.expected_test_case_set_digest,
                "product_id": self.product_id,
                "product_version": str(self.product_version),
                "profile_id": self.profile_id,
                "profile_version": str(self.profile_version),
                "protocol_version": str(self.protocol_version),
                "requested_at": _canonical_datetime(self.requested_at),
                "requested_by": self.requested_by,
                "use_current_alias": self.use_current_alias,
                "use_latest_alias": self.use_latest_alias,
                "validation_plan_digest": self.validation_plan_digest,
            }
        )


@dataclass(frozen=True)
class ValidationFixtureManifest:
    fixture_manifest_id: str
    fixture_kind: ValidationFixtureKind
    fixture_version: SemanticVersion
    test_case_ids: tuple[str, ...]
    synthetic_data_digest: str
    prohibited_real_data_assertion: bool
    prohibited_network_assertion: bool
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.fixture_manifest_id):
            _raise(ManualValidationExecutionErrorCategory.INVALID_IDENTITY)
        if not isinstance(self.fixture_kind, ValidationFixtureKind) or not isinstance(
            self.fixture_version, SemanticVersion
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_VERSION)
        if (
            not isinstance(self.test_case_ids, tuple)
            or not self.test_case_ids
            or tuple(sorted(set(self.test_case_ids))) != self.test_case_ids
            or not all(_is_identifier(value) for value in self.test_case_ids)
        ):
            _raise(ManualValidationExecutionErrorCategory.TEST_CASE_SET_MISMATCH)
        if not _is_digest(self.synthetic_data_digest):
            _raise(ManualValidationExecutionErrorCategory.INVALID_DIGEST)
        if (
            type(self.prohibited_real_data_assertion) is not bool
            or type(self.prohibited_network_assertion) is not bool
            or not self.prohibited_real_data_assertion
            or not self.prohibited_network_assertion
        ):
            _raise(ManualValidationExecutionErrorCategory.ENVIRONMENT_UNSAFE)
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    @property
    def test_case_set_digest(self) -> str:
        return _digest(_canonical_json({"test_case_ids": list(self.test_case_ids)}))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "fixture_kind": self.fixture_kind.value,
                "fixture_manifest_id": self.fixture_manifest_id,
                "fixture_version": str(self.fixture_version),
                "prohibited_network_assertion": self.prohibited_network_assertion,
                "prohibited_real_data_assertion": self.prohibited_real_data_assertion,
                "synthetic_data_digest": self.synthetic_data_digest,
                "test_case_ids": list(self.test_case_ids),
            }
        )


@dataclass(frozen=True)
class ValidationEnvironmentContract:
    environment_id: str
    environment_version: SemanticVersion
    offline_required: bool
    network_allowed: bool
    filesystem_write_allowed: bool
    subprocess_allowed: bool
    external_api_allowed: bool
    real_data_allowed: bool
    credential_allowed: bool
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.environment_id) or not isinstance(
            self.environment_version, SemanticVersion
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_CONTRACT)
        values = (
            self.offline_required,
            self.network_allowed,
            self.filesystem_write_allowed,
            self.subprocess_allowed,
            self.external_api_allowed,
            self.real_data_allowed,
            self.credential_allowed,
        )
        if any(type(value) is not bool for value in values):
            _raise(ManualValidationExecutionErrorCategory.INVALID_CONTRACT)
        if not self.is_v016_safe:
            _raise(ManualValidationExecutionErrorCategory.ENVIRONMENT_UNSAFE)
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    @property
    def is_v016_safe(self) -> bool:
        return self.offline_required and not any(
            (
                self.network_allowed,
                self.filesystem_write_allowed,
                self.subprocess_allowed,
                self.external_api_allowed,
                self.real_data_allowed,
                self.credential_allowed,
            )
        )

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "credential_allowed": self.credential_allowed,
                "environment_id": self.environment_id,
                "environment_version": str(self.environment_version),
                "external_api_allowed": self.external_api_allowed,
                "filesystem_write_allowed": self.filesystem_write_allowed,
                "network_allowed": self.network_allowed,
                "offline_required": self.offline_required,
                "real_data_allowed": self.real_data_allowed,
                "subprocess_allowed": self.subprocess_allowed,
            }
        )


@dataclass(frozen=True)
class ManualValidationExecutionRecord:
    execution_id: str
    request_digest: str
    validation_plan_digest: str
    fixture_manifest_digest: str
    environment_contract_digest: str
    started_at: datetime
    completed_at: datetime
    execution_operator_id: str
    executed_test_case_ids: tuple[str, ...]
    passed_test_case_ids: tuple[str, ...]
    failed_test_case_ids: tuple[str, ...]
    skipped_test_case_ids: tuple[str, ...]
    result: ManualExecutionResult
    execution_summary_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.execution_id) or not _is_identifier(
            self.execution_operator_id
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_IDENTITY)
        if not all(
            _is_digest(value)
            for value in (
                self.request_digest,
                self.validation_plan_digest,
                self.fixture_manifest_digest,
                self.environment_contract_digest,
                self.execution_summary_digest,
            )
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_DIGEST)
        if (
            not _is_aware(self.started_at)
            or not _is_aware(self.completed_at)
            or self.started_at > self.completed_at
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_TIME)
        groups = (
            self.executed_test_case_ids,
            self.passed_test_case_ids,
            self.failed_test_case_ids,
            self.skipped_test_case_ids,
        )
        if any(
            not isinstance(group, tuple)
            or tuple(sorted(set(group))) != group
            or not all(_is_identifier(value) for value in group)
            for group in groups
        ):
            _raise(ManualValidationExecutionErrorCategory.TEST_CASE_SET_MISMATCH)
        executed = set(self.executed_test_case_ids)
        passed = set(self.passed_test_case_ids)
        failed = set(self.failed_test_case_ids)
        skipped = set(self.skipped_test_case_ids)
        if passed & failed or passed & skipped or failed & skipped:
            _raise(ManualValidationExecutionErrorCategory.TEST_CASE_SET_MISMATCH)
        if executed != passed | failed or not skipped.isdisjoint(executed):
            _raise(ManualValidationExecutionErrorCategory.TEST_CASE_SET_MISMATCH)
        if not isinstance(self.result, ManualExecutionResult):
            _raise(ManualValidationExecutionErrorCategory.INVALID_CONTRACT)
        if self.result is ManualExecutionResult.PASSED and (failed or skipped):
            _raise(ManualValidationExecutionErrorCategory.PARTIAL_EXECUTION)
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "completed_at": _canonical_datetime(self.completed_at),
                "environment_contract_digest": self.environment_contract_digest,
                "executed_test_case_ids": list(self.executed_test_case_ids),
                "execution_id": self.execution_id,
                "execution_operator_id": self.execution_operator_id,
                "execution_summary_digest": self.execution_summary_digest,
                "failed_test_case_ids": list(self.failed_test_case_ids),
                "fixture_manifest_digest": self.fixture_manifest_digest,
                "passed_test_case_ids": list(self.passed_test_case_ids),
                "request_digest": self.request_digest,
                "result": self.result.value,
                "skipped_test_case_ids": list(self.skipped_test_case_ids),
                "started_at": _canonical_datetime(self.started_at),
                "validation_plan_digest": self.validation_plan_digest,
            }
        )


@dataclass(frozen=True)
class ManualValidationExecutionEvidence:
    evidence_id: str
    execution_record_digest: str
    validation_plan_digest: str
    fixture_manifest_digest: str
    environment_contract_digest: str
    evidence_created_at: datetime
    created_by: str
    result: ManualExecutionResult
    completeness_state: EvidenceCompleteness
    evidence_kind: ManualEvidenceKind
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.evidence_id) or not _is_identifier(self.created_by):
            _raise(ManualValidationExecutionErrorCategory.INVALID_IDENTITY)
        if not all(
            _is_digest(value)
            for value in (
                self.execution_record_digest,
                self.validation_plan_digest,
                self.fixture_manifest_digest,
                self.environment_contract_digest,
            )
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_DIGEST)
        if not _is_aware(self.evidence_created_at):
            _raise(ManualValidationExecutionErrorCategory.INVALID_TIME)
        if not isinstance(self.result, ManualExecutionResult) or not isinstance(
            self.completeness_state, EvidenceCompleteness
        ) or not isinstance(self.evidence_kind, ManualEvidenceKind):
            _raise(ManualValidationExecutionErrorCategory.INVALID_CONTRACT)
        if self.result is ManualExecutionResult.PASSED and (
            self.completeness_state is not EvidenceCompleteness.COMPLETE
        ):
            _raise(ManualValidationExecutionErrorCategory.PARTIAL_EXECUTION)
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "completeness_state": self.completeness_state.value,
                "created_by": self.created_by,
                "environment_contract_digest": self.environment_contract_digest,
                "evidence_created_at": _canonical_datetime(self.evidence_created_at),
                "evidence_id": self.evidence_id,
                "evidence_kind": self.evidence_kind.value,
                "execution_record_digest": self.execution_record_digest,
                "fixture_manifest_digest": self.fixture_manifest_digest,
                "result": self.result.value,
                "validation_plan_digest": self.validation_plan_digest,
            }
        )


@dataclass(frozen=True)
class ManualValidationReview:
    review_id: str
    evidence_digest: str
    reviewed_at: datetime
    reviewer_id: str
    review_result: ManualReviewResult
    findings_digest: str
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.review_id) or not _is_identifier(self.reviewer_id):
            _raise(ManualValidationExecutionErrorCategory.INVALID_IDENTITY)
        if not _is_digest(self.evidence_digest) or not _is_digest(self.findings_digest):
            _raise(ManualValidationExecutionErrorCategory.INVALID_DIGEST)
        if not _is_aware(self.reviewed_at) or not isinstance(
            self.review_result, ManualReviewResult
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_CONTRACT)
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "evidence_digest": self.evidence_digest,
                "findings_digest": self.findings_digest,
                "review_id": self.review_id,
                "review_result": self.review_result.value,
                "reviewed_at": _canonical_datetime(self.reviewed_at),
                "reviewer_id": self.reviewer_id,
            }
        )


@dataclass(frozen=True)
class ManualValidationApproval:
    approval_id: str
    evidence_digest: str
    review_digest: str
    approved_at: datetime
    approver_id: str
    approval_result: ManualApprovalResult
    canonical_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not _is_identifier(self.approval_id) or not _is_identifier(self.approver_id):
            _raise(ManualValidationExecutionErrorCategory.INVALID_IDENTITY)
        if not _is_digest(self.evidence_digest) or not _is_digest(self.review_digest):
            _raise(ManualValidationExecutionErrorCategory.INVALID_DIGEST)
        if not _is_aware(self.approved_at) or not isinstance(
            self.approval_result, ManualApprovalResult
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_CONTRACT)
        object.__setattr__(self, "canonical_digest", _digest(self.canonical_json()))

    def canonical_json(self) -> str:
        return _canonical_json(
            {
                "approval_id": self.approval_id,
                "approval_result": self.approval_result.value,
                "approved_at": _canonical_datetime(self.approved_at),
                "approver_id": self.approver_id,
                "evidence_digest": self.evidence_digest,
                "review_digest": self.review_digest,
            }
        )


@dataclass(frozen=True)
class ManualValidationChain:
    request: ManualValidationExecutionRequest
    fixture_manifest: ValidationFixtureManifest
    environment: ValidationEnvironmentContract
    execution_record: ManualValidationExecutionRecord
    evidence: ManualValidationExecutionEvidence
    review: ManualValidationReview | None
    approval: ManualValidationApproval | None

    def validate(self, *, plan: ManualValidationPlan, evaluation_time: datetime) -> None:
        if not _is_aware(evaluation_time):
            _raise(ManualValidationExecutionErrorCategory.INVALID_TIME)
        _validate_request_binding(self.request, plan, self.fixture_manifest, self.environment)
        record = self.execution_record
        evidence = self.evidence
        if (
            record.request_digest != self.request.canonical_digest
            or record.validation_plan_digest != plan.canonical_digest
            or record.fixture_manifest_digest != self.fixture_manifest.canonical_digest
            or record.environment_contract_digest != self.environment.canonical_digest
            or record.execution_operator_id != self.request.execution_operator_id
            or set(record.executed_test_case_ids) != set(self.fixture_manifest.test_case_ids)
            or record.completed_at < record.started_at
            or not (
                plan.execution_window_start <= record.started_at
                <= record.completed_at <= plan.execution_window_end
            )
            or evidence.execution_record_digest != record.canonical_digest
            or evidence.validation_plan_digest != plan.canonical_digest
            or evidence.fixture_manifest_digest != self.fixture_manifest.canonical_digest
            or evidence.environment_contract_digest != self.environment.canonical_digest
            or evidence.result is not record.result
            or evidence.evidence_created_at < record.completed_at
            or evidence.evidence_kind
            is not (
                ManualEvidenceKind.SYNTHETIC_EXECUTION
                if self.fixture_manifest.fixture_kind is ValidationFixtureKind.SYNTHETIC
                else ManualEvidenceKind.CONTROLLED_MANUAL_EXECUTION
            )
        ):
            _raise(ManualValidationExecutionErrorCategory.CHAIN_MISMATCH)
        actors = {
            self.request.requested_by,
            self.request.execution_operator_id,
            evidence.created_by,
        }
        if len(actors) != 3:
            _raise(ManualValidationExecutionErrorCategory.ROLE_CONFLICT)
        if self.review is None:
            if self.approval is not None:
                _raise(ManualValidationExecutionErrorCategory.CHAIN_MISMATCH)
            if evidence.evidence_created_at > evaluation_time:
                _raise(ManualValidationExecutionErrorCategory.FUTURE_METADATA)
            return
        review = self.review
        if (
            review.evidence_digest != evidence.canonical_digest
            or review.reviewed_at < evidence.evidence_created_at
            or review.reviewer_id != plan.evidence_reviewer_id
            or review.reviewer_id in actors
        ):
            _raise(ManualValidationExecutionErrorCategory.CHAIN_MISMATCH)
        actors.add(review.reviewer_id)
        if self.approval is None:
            if review.reviewed_at > evaluation_time:
                _raise(ManualValidationExecutionErrorCategory.FUTURE_METADATA)
            return
        approval = self.approval
        if (
            approval.evidence_digest != evidence.canonical_digest
            or approval.review_digest != review.canonical_digest
            or approval.approved_at <= review.reviewed_at
            or approval.approver_id != plan.approver_id
            or approval.approver_id in actors
            or approval.approval_result is ManualApprovalResult.APPROVED
            and review.review_result is not ManualReviewResult.APPROVED
        ):
            _raise(ManualValidationExecutionErrorCategory.CHAIN_MISMATCH)
        if not (
            self.request.requested_at <= record.started_at <= record.completed_at
            <= evidence.evidence_created_at <= review.reviewed_at
            < approval.approved_at <= evaluation_time
        ):
            _raise(ManualValidationExecutionErrorCategory.INVALID_TIME)
        if evaluation_time - evidence.evidence_created_at > MAX_EXECUTION_EVIDENCE_AGE:
            _raise(ManualValidationExecutionErrorCategory.STALE)

    @property
    def approved(self) -> bool:
        return bool(
            self.execution_record.result is ManualExecutionResult.PASSED
            and self.evidence.completeness_state is EvidenceCompleteness.COMPLETE
            and self.review is not None
            and self.review.review_result is ManualReviewResult.APPROVED
            and self.approval is not None
            and self.approval.approval_result is ManualApprovalResult.APPROVED
        )


@dataclass(frozen=True)
class ManualValidationExecutionSafeSummary:
    request_digest: str | None
    execution_id: str | None
    result: str
    executed_count: int
    passed_count: int
    failed_count: int
    skipped_count: int
    reason_categories: tuple[str, ...]


@dataclass(frozen=True)
class ManualValidationExecutionOutcome:
    applied: bool
    record: ManualValidationExecutionRecord | None
    reason_categories: tuple[ManualValidationExecutionErrorCategory, ...]
    registry_write_count: int = 0
    mutation_count: int = 0
    persistence_write_count: int = 0
    filesystem_write_count: int = 0
    database_write_count: int = 0
    network_count: int = 0
    http_count: int = 0
    activation_count: int = 0
    safe_summary: ManualValidationExecutionSafeSummary = field(init=False)

    def __post_init__(self) -> None:
        record = self.record
        object.__setattr__(
            self,
            "safe_summary",
            ManualValidationExecutionSafeSummary(
                request_digest=None if record is None else record.request_digest,
                execution_id=None if record is None else record.execution_id,
                result="rejected" if record is None else record.result.value,
                executed_count=0 if record is None else len(record.executed_test_case_ids),
                passed_count=0 if record is None else len(record.passed_test_case_ids),
                failed_count=0 if record is None else len(record.failed_test_case_ids),
                skipped_count=0 if record is None else len(record.skipped_test_case_ids),
                reason_categories=tuple(value.value for value in self.reason_categories),
            ),
        )


@dataclass(frozen=True)
class _HarnessState:
    records: tuple[ManualValidationExecutionRecord, ...] = ()
    used_request_ids: frozenset[str] = frozenset()
    used_execution_ids: frozenset[str] = frozenset()
    used_record_digests: frozenset[str] = frozenset()


class TestManualValidationExecutionHarness:
    __test__ = False

    def __init__(self) -> None:
        self._state = _HarnessState()

    @property
    def records(self) -> tuple[ManualValidationExecutionRecord, ...]:
        return self._state.records

    def execute(
        self,
        *,
        request: ManualValidationExecutionRequest,
        plan: ManualValidationPlan,
        fixture_manifest: ValidationFixtureManifest,
        environment: ValidationEnvironmentContract,
        execution_id: str,
        started_at: datetime,
        completed_at: datetime,
        case_results: Mapping[str, bool | None],
        execution_summary_digest: str,
        commit_fault: bool = False,
    ) -> ManualValidationExecutionOutcome:
        try:
            _validate_request_binding(request, plan, fixture_manifest, environment)
            if (
                request.execution_request_id in self._state.used_request_ids
                or execution_id in self._state.used_execution_ids
            ):
                _raise(ManualValidationExecutionErrorCategory.REPLAY)
            expected = set(fixture_manifest.test_case_ids)
            if set(case_results) != expected:
                _raise(ManualValidationExecutionErrorCategory.TEST_CASE_SET_MISMATCH)
            passed = tuple(sorted(key for key, value in case_results.items() if value is True))
            failed = tuple(sorted(key for key, value in case_results.items() if value is False))
            skipped = tuple(sorted(key for key, value in case_results.items() if value is None))
            executed = tuple(sorted((*passed, *failed)))
            result = (
                ManualExecutionResult.PASSED
                if not failed and not skipped
                else ManualExecutionResult.FAILED
                if failed
                else ManualExecutionResult.INCOMPLETE
            )
            record = ManualValidationExecutionRecord(
                execution_id=execution_id,
                request_digest=request.canonical_digest,
                validation_plan_digest=plan.canonical_digest,
                fixture_manifest_digest=fixture_manifest.canonical_digest,
                environment_contract_digest=environment.canonical_digest,
                started_at=started_at,
                completed_at=completed_at,
                execution_operator_id=request.execution_operator_id,
                executed_test_case_ids=executed,
                passed_test_case_ids=passed,
                failed_test_case_ids=failed,
                skipped_test_case_ids=skipped,
                result=result,
                execution_summary_digest=execution_summary_digest,
            )
            if record.canonical_digest in self._state.used_record_digests:
                _raise(ManualValidationExecutionErrorCategory.REPLAY)
            candidate = _HarnessState(
                records=(*self._state.records, record),
                used_request_ids=self._state.used_request_ids | {request.execution_request_id},
                used_execution_ids=self._state.used_execution_ids | {execution_id},
                used_record_digests=self._state.used_record_digests | {record.canonical_digest},
            )
            if commit_fault:
                _raise(ManualValidationExecutionErrorCategory.COMMIT_FAILED)
            self._state = candidate
            return ManualValidationExecutionOutcome(
                applied=True,
                record=record,
                reason_categories=(),
            )
        except ManualValidationExecutionError as error:
            return ManualValidationExecutionOutcome(
                applied=False,
                record=None,
                reason_categories=(error.category,),
            )


@dataclass(frozen=True)
class ManualValidationChainCommitResult:
    applied: bool
    reason_categories: tuple[ManualValidationExecutionErrorCategory, ...]
    registry_write_count: int = 0
    mutation_count: int = 0
    persistence_write_count: int = 0
    filesystem_write_count: int = 0
    database_write_count: int = 0
    network_count: int = 0
    http_count: int = 0
    activation_count: int = 0


@dataclass(frozen=True)
class _ChainState:
    used_execution_request_ids: frozenset[str] = frozenset()
    used_execution_ids: frozenset[str] = frozenset()
    used_evidence_ids: frozenset[str] = frozenset()
    used_review_ids: frozenset[str] = frozenset()
    used_approval_ids: frozenset[str] = frozenset()
    used_execution_record_digests: frozenset[str] = frozenset()
    used_evidence_digests: frozenset[str] = frozenset()
    used_review_digests: frozenset[str] = frozenset()
    committed_chain_digests: tuple[str, ...] = ()


class TestManualValidationChainStore:
    """Test-only replay ledger with candidate-state/single-swap semantics."""

    __test__ = False

    def __init__(self) -> None:
        self._state = _ChainState()

    @property
    def committed_chain_count(self) -> int:
        return len(self._state.committed_chain_digests)

    @property
    def snapshot(self) -> _ChainState:
        return self._state

    def commit(
        self,
        chain: ManualValidationChain,
        *,
        plan: ManualValidationPlan,
        evaluation_time: datetime,
        commit_fault: bool = False,
    ) -> ManualValidationChainCommitResult:
        try:
            chain.validate(plan=plan, evaluation_time=evaluation_time)
            if not chain.approved or chain.review is None or chain.approval is None:
                _raise(ManualValidationExecutionErrorCategory.CHAIN_MISMATCH)
            values = (
                chain.request.execution_request_id in self._state.used_execution_request_ids,
                chain.execution_record.execution_id in self._state.used_execution_ids,
                chain.evidence.evidence_id in self._state.used_evidence_ids,
                chain.review.review_id in self._state.used_review_ids,
                chain.approval.approval_id in self._state.used_approval_ids,
                chain.execution_record.canonical_digest
                in self._state.used_execution_record_digests,
                chain.evidence.canonical_digest in self._state.used_evidence_digests,
                chain.review.canonical_digest in self._state.used_review_digests,
            )
            if any(values):
                _raise(ManualValidationExecutionErrorCategory.REPLAY)
            chain_digest = _digest(
                _canonical_json(
                    {
                        "approval_digest": chain.approval.canonical_digest,
                        "evidence_digest": chain.evidence.canonical_digest,
                        "execution_record_digest": chain.execution_record.canonical_digest,
                        "review_digest": chain.review.canonical_digest,
                        "validation_plan_digest": plan.canonical_digest,
                    }
                )
            )
            candidate = _ChainState(
                used_execution_request_ids=self._state.used_execution_request_ids
                | {chain.request.execution_request_id},
                used_execution_ids=self._state.used_execution_ids
                | {chain.execution_record.execution_id},
                used_evidence_ids=self._state.used_evidence_ids | {chain.evidence.evidence_id},
                used_review_ids=self._state.used_review_ids | {chain.review.review_id},
                used_approval_ids=self._state.used_approval_ids | {chain.approval.approval_id},
                used_execution_record_digests=self._state.used_execution_record_digests
                | {chain.execution_record.canonical_digest},
                used_evidence_digests=self._state.used_evidence_digests
                | {chain.evidence.canonical_digest},
                used_review_digests=self._state.used_review_digests
                | {chain.review.canonical_digest},
                committed_chain_digests=(*self._state.committed_chain_digests, chain_digest),
            )
            if commit_fault:
                _raise(ManualValidationExecutionErrorCategory.COMMIT_FAILED)
            self._state = candidate
            return ManualValidationChainCommitResult(applied=True, reason_categories=())
        except ManualValidationExecutionError as error:
            return ManualValidationChainCommitResult(
                applied=False,
                reason_categories=(error.category,),
            )


def _validate_request_binding(
    request: ManualValidationExecutionRequest,
    plan: ManualValidationPlan,
    fixture_manifest: ValidationFixtureManifest,
    environment: ValidationEnvironmentContract,
) -> None:
    if not all(
        (
            isinstance(plan, ManualValidationPlan),
            request.validation_plan_digest == plan.canonical_digest,
            request.profile_id == plan.profile_id,
            request.profile_version == plan.profile_version,
            request.product_id == plan.product_id,
            request.product_version == plan.product_version,
            request.protocol_version == plan.protocol_version,
            request.execution_operator_id == plan.validation_operator_id,
        )
    ):
        _raise(ManualValidationExecutionErrorCategory.PLAN_MISMATCH)
    if (
        request.expected_fixture_manifest_digest != fixture_manifest.canonical_digest
        or request.expected_test_case_set_digest != fixture_manifest.test_case_set_digest
        or set(fixture_manifest.test_case_ids)
        != {value.value for value in plan.required_case_ids}
    ):
        _raise(ManualValidationExecutionErrorCategory.FIXTURE_MISMATCH)
    if request.expected_environment_contract_digest != environment.canonical_digest:
        _raise(ManualValidationExecutionErrorCategory.ENVIRONMENT_UNSAFE)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _raise(category: ManualValidationExecutionErrorCategory) -> None:
    raise ManualValidationExecutionError(category)
