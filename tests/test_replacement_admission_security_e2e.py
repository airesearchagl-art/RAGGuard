from dataclasses import replace

import pytest

from ragguard.production_registry import RegistryStatus
from ragguard.replacement_admission import (
    ReplacementAdmissionReason,
    enforce_replacement_admission,
)
from test_replacement_admission_contract import replacement_request


def _assert_zero_side_effects(store) -> None:
    assert len(store.snapshot) == 1
    assert len(store.events) == 0
    assert store.write_count == 0
    assert store.mutation_count == 0
    assert len(store.committed_request_ids) == 0
    assert store.transport_count == 0
    assert store.http_count == 0


def test_full_chain_synthetic_security_e2e_succeeds_once() -> None:
    context, request = replacement_request()
    predecessor = context[3]
    store = context[4]

    result = enforce_replacement_admission(request, registry=store)

    assert result.applied is True
    assert result.successor_entry is not None
    assert result.successor_entry.predecessor_entry_digest == predecessor.canonical_digest
    assert result.event is not None
    assert result.event.predecessor_entry_digest == predecessor.canonical_digest
    assert result.event.successor_entry_digest == result.successor_entry.canonical_digest
    assert store.snapshot[predecessor.admission_id] == predecessor
    assert store.transport_count == store.http_count == 0


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("new_plan_digest", ReplacementAdmissionReason.DIGEST_MISMATCH),
        ("new_evidence_digest", ReplacementAdmissionReason.DIGEST_MISMATCH),
        ("new_attestation_digest", ReplacementAdmissionReason.DIGEST_MISMATCH),
        (
            "new_admission_decision_digest",
            ReplacementAdmissionReason.DIGEST_MISMATCH,
        ),
    ],
)
def test_digest_tampering_is_denied_with_zero_side_effects(field, reason) -> None:
    context, request = replacement_request()
    tampered = replace(request, **{field: "sha256:" + "f" * 64})
    result = enforce_replacement_admission(tampered, registry=context[4])
    assert result.applied is False
    assert reason in result.reason_categories
    _assert_zero_side_effects(context[4])


def test_registry_administrator_role_collision_is_denied() -> None:
    context, request = replacement_request()
    conflicting = replace(
        request,
        registry_administrator_id=(
            request.new_production_admission_request.approver_identity
        ),
    )
    result = enforce_replacement_admission(conflicting, registry=context[4])
    assert result.applied is False
    assert ReplacementAdmissionReason.ROLE_CONFLICT in result.reason_categories
    _assert_zero_side_effects(context[4])


def test_revoked_predecessor_is_terminal_and_denied() -> None:
    context, request = replacement_request(
        predecessor_status=RegistryStatus.REVOKED
    )
    result = enforce_replacement_admission(request, registry=context[4])
    assert result.applied is False
    assert (
        ReplacementAdmissionReason.PREDECESSOR_STATUS_INELIGIBLE
        in result.reason_categories
    )
    _assert_zero_side_effects(context[4])


def test_expired_evidence_is_denied_pending_a_new_fresh_chain() -> None:
    context, request = replacement_request()
    expired = replace(
        request,
        evaluation_time=(
            request.new_production_admission_request.manual_validation_evidence.expires_at
        ),
    )
    result = enforce_replacement_admission(expired, registry=context[4])
    assert result.applied is False
    assert ReplacementAdmissionReason.EVIDENCE_EXPIRED in result.reason_categories
    _assert_zero_side_effects(context[4])


def test_no_automatic_reactivation_or_predecessor_mutation() -> None:
    context, request = replacement_request()
    predecessor = context[3]
    store = context[4]
    result = enforce_replacement_admission(request, registry=store)
    assert result.applied is True
    assert store.snapshot[predecessor.admission_id].registry_status is RegistryStatus.SUSPENDED
    assert result.successor_entry is not None
    assert result.successor_entry.admission_id != predecessor.admission_id


def test_duplicate_replay_has_zero_additional_side_effects() -> None:
    context, request = replacement_request()
    store = context[4]
    assert enforce_replacement_admission(request, registry=store).applied
    before = (dict(store.snapshot), store.events, store.write_count, store.mutation_count)
    result = enforce_replacement_admission(request, registry=store)
    assert result.applied is False
    assert ReplacementAdmissionReason.DUPLICATE_REQUEST in result.reason_categories
    assert (dict(store.snapshot), store.events, store.write_count, store.mutation_count) == before
    assert store.transport_count == store.http_count == 0
