from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.local_rag_environment import *
from ragguard.storage_adapter import digest


NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)
D = digest("controlled-policy")


def environment_manifest(*, integration_manifest_digest=D, policy_digest=D):
    return LocalRAGEnvironmentManifest(
        "environment-001", EnvironmentClass.ISOLATED_LOCAL_TEST,
        D, D, integration_manifest_digest, policy_digest, policy_digest, policy_digest,
        policy_digest, policy_digest, policy_digest, policy_digest, D, D, "v0.23",
        EnvironmentDataClass.SYNTHETIC_ONLY, EnvironmentNetworkMode.DISABLED,
        EnvironmentStorageMode.IN_MEMORY_ONLY, EnvironmentCredentialMode.NONE, NOW)


def verification_results(manifest, result=VerificationResult.PASSED):
    classes = (
        BuildVerificationResult, DependencyVerificationResult,
        ConfigurationVerificationResult, NetworkIsolationVerificationResult,
        StorageIsolationVerificationResult, LoggingSafetyVerificationResult,
        FixtureSafetyVerificationResult,
    )
    return tuple(cls(f"result-{index}", manifest.canonical_digest, D, result, D,
                     NOW + timedelta(minutes=1), "environment-verifier")
                 for index, cls in enumerate(classes, 1))


def attestation_chain(result=VerificationResult.PASSED, *, integration_manifest_digest=D,
                      policy_digest=D):
    manifest = environment_manifest(integration_manifest_digest=integration_manifest_digest,
                                    policy_digest=policy_digest)
    results = verification_results(manifest, result)
    suite = EnvironmentAttestationSuite(manifest.canonical_digest,
        *(value.canonical_digest for value in results))
    evidence = EnvironmentAttestationEvidence(manifest.canonical_digest,
        *(value.canonical_digest for value in results), suite.canonical_digest,
        NOW + timedelta(minutes=2), "environment-verifier")
    roles = EnvironmentRoleContext("environment-verifier", "environment-reviewer",
                                   "environment-approver")
    decision = evaluate_environment_attestation(manifest, suite, results, evidence, roles,
        evaluation_time=NOW + timedelta(minutes=3))
    return manifest, results, suite, evidence, roles, decision


def approved_environment_chain(*, integration_manifest_digest=D, policy_digest=D):
    manifest, results, suite, evidence, roles, decision = attestation_chain(
        integration_manifest_digest=integration_manifest_digest, policy_digest=policy_digest)
    review = EnvironmentReview("environment-review-001", manifest.canonical_digest,
        suite.canonical_digest, NOW + timedelta(minutes=4), "environment-reviewer",
        EnvironmentReviewResult.APPROVED, D)
    approval = EnvironmentApproval("environment-approval-001", manifest.canonical_digest,
        suite.canonical_digest, review.canonical_digest, NOW + timedelta(minutes=5),
        "environment-approver", EnvironmentApprovalResult.APPROVED)
    return manifest, results, suite, evidence, roles, decision, review, approval


def test_environment_hard_gates_accept_exact_object_backed_chain():
    manifest, results, suite, evidence, roles, decision = attestation_chain()
    assert decision.state is EnvironmentAttestationState.ELIGIBLE_FOR_ENVIRONMENT_REVIEW
    assert decision.production_environment_approved is decision.production_ready is decision.active is False
    assert all(value.result is VerificationResult.PASSED for value in results)
    assert repr(manifest) == "LocalRAGEnvironmentManifest(<safe>)"


def test_review_eligible_decision_cannot_be_forged_by_public_constructor():
    manifest, _, suite, evidence, _, _ = attestation_chain()
    with pytest.raises(LocalRAGEnvironmentError, match="attestation_decision_invalid"):
        EnvironmentAttestationDecision(
            EnvironmentAttestationState.ELIGIBLE_FOR_ENVIRONMENT_REVIEW,
            manifest.canonical_digest, suite.canonical_digest, evidence.canonical_digest,
            ("environment_verified",), NOW + timedelta(minutes=3))
    valid = attestation_chain()[-1]
    with pytest.raises(LocalRAGEnvironmentError, match="attestation_decision_invalid"):
        replace(valid, evaluated_at=NOW + timedelta(minutes=4))


def test_environment_approval_is_independent_and_not_real_data_approval():
    manifest, _, suite, _, roles, decision, review, approval = approved_environment_chain()
    assert validate_environment_approval(manifest, suite, decision, review, approval, roles,
        evaluation_time=NOW + timedelta(minutes=6)) == ()
    assert approval.real_data_approved is False


@pytest.mark.parametrize("result", (VerificationResult.FAILED, VerificationResult.INCOMPLETE))
def test_failed_or_incomplete_verification_never_becomes_review_eligible(result):
    *_, decision = attestation_chain(result)
    assert decision.state is EnvironmentAttestationState.NEEDS_ENVIRONMENT_VERIFICATION
    assert "verification_not_passed" in decision.reason_codes


def test_caller_supplied_digest_strings_do_not_replace_actual_result_objects():
    manifest, results, suite, evidence, roles, _ = attestation_chain()
    forged = results[0]
    object.__setattr__(forged, "observed_state_digest", digest("forged"))
    decision = evaluate_environment_attestation(manifest, suite,
        (forged, *results[1:]), evidence, roles,
        evaluation_time=NOW + timedelta(minutes=3))
    assert decision.state is EnvironmentAttestationState.INELIGIBLE
    assert "forged_object" in decision.reason_codes


def test_suite_manifest_and_verifier_mismatches_fail_closed():
    manifest, results, suite, evidence, roles, _ = attestation_chain()
    wrong_suite = suite
    object.__setattr__(wrong_suite, "environment_manifest_digest", digest("other"))
    wrong_roles = EnvironmentRoleContext("other-verifier", "environment-reviewer",
                                         "environment-approver")
    decision = evaluate_environment_attestation(manifest, wrong_suite, results, evidence,
        wrong_roles, evaluation_time=NOW + timedelta(minutes=3))
    assert decision.state is EnvironmentAttestationState.INELIGIBLE
    assert {"forged_object", "digest_binding_mismatch", "verifier_mismatch"}.issubset(
        decision.reason_codes)


def test_future_and_stale_attestation_metadata_are_rejected():
    manifest, results, suite, evidence, roles, _ = attestation_chain()
    future = evaluate_environment_attestation(manifest, suite, results, evidence, roles,
        evaluation_time=NOW + timedelta(minutes=1))
    stale = evaluate_environment_attestation(manifest, suite, results, evidence, roles,
        evaluation_time=NOW + MAX_ENVIRONMENT_EVIDENCE_AGE + timedelta(days=1))
    assert future.state is stale.state is EnvironmentAttestationState.INELIGIBLE
    assert "temporal_invalid" in future.reason_codes
    assert "temporal_invalid" in stale.reason_codes


def test_environment_role_conflicts_are_rejected_at_construction():
    with pytest.raises(LocalRAGEnvironmentError, match="environment_role_conflict"):
        EnvironmentRoleContext("same", "same", "environment-approver")
    with pytest.raises(LocalRAGEnvironmentError, match="environment_role_conflict"):
        EnvironmentRoleContext("environment-verifier", "same", "same")
    with pytest.raises(LocalRAGEnvironmentError, match="environment_role_conflict"):
        EnvironmentRoleContext("same", "environment-reviewer", "same")


def test_environment_manifest_has_no_connection_or_identity_surface():
    names = {value.name for value in fields(LocalRAGEnvironmentManifest)}
    forbidden = {"hostname", "ip", "port", "absolute_path", "endpoint", "dsn",
                 "credential", "token", "username", "customer_id", "product_id"}
    assert not names.intersection(forbidden)
    manifest = environment_manifest()
    assert manifest.network_mode is EnvironmentNetworkMode.DISABLED
    assert manifest.credential_mode is EnvironmentCredentialMode.NONE
