from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.local_rag_execution import *
from ragguard.local_rag_integration import *
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_environment_attestation import approved_environment_chain


NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)
D = digest("v0.23-controlled-policy")


def integration_chain(operator_id="session-operator"):
    manifest = LocalRAGIntegrationManifest(
        "controlled-rag", "v0.22", D, D, D, D, D, D, D, D, D,
        IntegrationDataClass.SYNTHETIC_ONLY)
    fixture = SyntheticConfidentialFixture("fixture-023", (
        (SensitiveClass.CUSTOMER_NAME, "Synthetic Customer Beta"),
        (SensitiveClass.PROJECT_NUMBER, "SYN-PROJECT-0023"),
        (SensitiveClass.CONTRACT, "Synthetic Contract Class"),
        (SensitiveClass.PERSONAL, "Synthetic Person Two"),
        (SensitiveClass.EMAIL, "fixture.two@example.invalid"),
        (SensitiveClass.PHONE, "+0-000-000-0023"),
        (SensitiveClass.INTERNAL_CODE, "SYN-INTERNAL-023"),
        (SensitiveClass.CREDENTIAL_LIKE, "api_key=SYNTHETIC-NOT-A-CREDENTIAL"),
    ), NOW, NOW + timedelta(days=1))
    contracts = tuple(DataFlowStageContract(stage, D, D,
        (IntegrationDataClass.SYNTHETIC_ONLY,), ("real_customer_data",),
        PersistenceClass.MEMORY_TEST_ONLY if stage is RAGStage.VECTOR_WRITE else PersistenceClass.NONE,
        LoggingClass.DIGEST_AND_REASON_ONLY, ExternalIOClass.PROHIBITED) for stage in RAGStage)
    plan = LocalRAGDataFlowPlan("plan-023", manifest.canonical_digest, contracts)
    masked, transformation = transform_fixture(fixture, D)
    chunk = ApprovedChunk("chunk-023", masked, transformation.canonical_digest)
    store = TestOnlyVectorStore()
    assert store.write(chunk, transformation)
    stage_results = tuple(evaluate_stage_gate(stage=stage, candidate_digest=D,
        detected_classes=tuple(kind for kind, _ in fixture.fields), transformed=True,
        blocked=False, evaluated_at=NOW + timedelta(minutes=6)) for stage in RAGStage)
    receipt = issue_passed_receipt(manifest=manifest, plan=plan, fixture=fixture,
        stage_results=stage_results, masking=transformation,
        embedding=evaluate_embedding_boundary(masked, transformation),
        retrieval=evaluate_retrieval_boundary(store.retrieve(chunk.chunk_id), transformation),
        prompt=evaluate_prompt_boundary((chunk,), {"state": "approved"}),
        logging=evaluate_logging_cache_boundary({"candidate_digest": chunk.canonical_digest,
                                                  "reason_code": "masked_only"}),
        counters=ExternalIOCounters(), operator_id=operator_id,
        executed_at=NOW + timedelta(minutes=6))
    roles = IntegrationRoleContext(operator_id, "integration-reviewer", "integration-approver")
    review = IntegrationReview(receipt.canonical_digest, "integration-reviewer",
        ReviewResult.APPROVED, NOW + timedelta(minutes=7))
    approval = IntegrationApproval(receipt.canonical_digest, review.canonical_digest,
        "integration-approver", ReviewResult.APPROVED, NOW + timedelta(minutes=8))
    return manifest, fixture, plan, receipt, review, approval, roles


def session_roles():
    return SessionRoleContext("environment-verifier", "environment-reviewer",
        "environment-approver", "session-requester", "session-operator",
        "session-reviewer", "session-approver")


def approved_session_chain(*, fault=SessionRegistryFault.NONE):
    integration = integration_chain()
    int_manifest, fixture, plan, int_receipt, int_review, int_approval, int_roles = integration
    env_manifest, _, env_suite, _, env_roles, env_decision, env_review, env_approval = (
        approved_environment_chain(integration_manifest_digest=int_manifest.canonical_digest,
                                   policy_digest=D))
    roles = session_roles()
    request = LocalRAGExecutionSessionRequest("session-request-023",
        env_manifest.canonical_digest, env_approval.canonical_digest,
        int_manifest.canonical_digest, plan.canonical_digest, fixture.canonical_digest,
        "session-requester", "session-operator", NOW + timedelta(minutes=9),
        NOW + timedelta(hours=20))
    session_review = LocalRAGExecutionSessionReview("session-pre-review-023",
        request.canonical_digest, env_approval.canonical_digest,
        int_manifest.canonical_digest, fixture.canonical_digest, "session-reviewer",
        NOW + timedelta(minutes=9, seconds=10), SessionReviewResult.APPROVED, D)
    session_approval = LocalRAGExecutionSessionApproval("session-pre-approval-023",
        request.canonical_digest, session_review.canonical_digest, "session-approver",
        NOW + timedelta(minutes=9, seconds=20), SessionApprovalResult.APPROVED)
    registry = TestOnlySessionRegistry()
    result = registry.approve(session_id="session-023", request=request,
        environment_manifest=env_manifest, environment_suite=env_suite,
        environment_decision=env_decision, environment_review=env_review,
        environment_approval=env_approval, environment_roles=env_roles,
        integration_manifest=int_manifest, data_flow_plan=plan, fixture=fixture,
        integration_receipt=int_receipt, integration_review=int_review,
        integration_approval=int_approval, integration_roles=int_roles,
        session_review=session_review, session_approval=session_approval,
        session_roles=roles, session_generation=1, predecessor_session_digest=None,
        approved_at=NOW + timedelta(minutes=10), fault=fault)
    return (registry, result, request, roles, env_manifest, env_suite, env_decision,
            env_review, env_approval, env_roles, *integration, session_review, session_approval)


def controlled_execution():
    chain = approved_session_chain()
    registry, result, request, roles, env_manifest, _, env_decision, _, env_approval, _, \
        int_manifest, fixture, plan, int_receipt, int_review, int_approval, int_roles, \
        session_review, session_approval = chain
    assert result.applied and result.session is not None
    evidence, accounting, receipt = ControlledLocalRAGExecutionAdapter().execute(
        execution_receipt_id="execution-receipt-023", session=result.session, request=request,
        environment_manifest=env_manifest, environment_approval=env_approval,
        integration_manifest=int_manifest, data_flow_plan=plan, fixture=fixture,
        operator_id="session-operator", started_at=NOW + timedelta(minutes=11),
        finished_at=NOW + timedelta(minutes=12))
    return chain, evidence, accounting, receipt


def registry_kwargs(chain):
    _, _, request, roles, env_manifest, env_suite, env_decision, env_review, \
        env_approval, env_roles, int_manifest, fixture, plan, int_receipt, int_review, \
        int_approval, int_roles, session_review, session_approval = chain
    return dict(session_id="session-candidate-023", request=request,
        environment_manifest=env_manifest, environment_suite=env_suite,
        environment_decision=env_decision, environment_review=env_review,
        environment_approval=env_approval, environment_roles=env_roles,
        integration_manifest=int_manifest, data_flow_plan=plan, fixture=fixture,
        integration_receipt=int_receipt, integration_review=int_review,
        integration_approval=int_approval, integration_roles=int_roles,
        session_review=session_review, session_approval=session_approval,
        session_roles=roles, session_generation=1, predecessor_session_digest=None,
        approved_at=NOW + timedelta(minutes=10))


def test_session_request_is_metadata_only_and_exactly_bound():
    chain = approved_session_chain()
    registry, result, request, *_, session_review, session_approval = chain
    assert result.applied and result.session.session_request_digest == request.canonical_digest
    assert result.session.session_review_digest == session_review.canonical_digest
    assert result.session.session_approval_digest == session_approval.canonical_digest
    assert registry.replay_snapshot == (
        frozenset({request.canonical_digest}),
        frozenset({session_review.canonical_digest}),
        frozenset({session_approval.canonical_digest}),
        frozenset({result.session.canonical_digest}),
    )
    names = {value.name for value in fields(LocalRAGExecutionSessionRequest)}
    assert not names.intersection({"hostname", "ip", "port", "path", "endpoint", "dsn",
                                   "credential", "token", "raw_data", "customer_id"})
    for contract in (LocalRAGExecutionSessionReview, LocalRAGExecutionSessionApproval):
        contract_names = {value.name for value in fields(contract)}
        assert not contract_names.intersection({"raw", "content", "path", "endpoint",
                                                "credential", "token", "customer_id"})
    assert result.session.real_data_approved is result.session.production_active is False
    with pytest.raises(LocalRAGExecutionError, match="approved_session_invalid"):
        replace(result.session, session_id="forged-session")


def test_preapproval_contracts_are_distinct_from_post_execution_review_and_approval():
    chain = approved_session_chain()
    *_, review, approval = chain
    assert isinstance(review, LocalRAGExecutionSessionReview)
    assert isinstance(approval, LocalRAGExecutionSessionApproval)
    assert not isinstance(review, SessionExecutionReview)
    assert not isinstance(approval, SessionExecutionApproval)
    assert approval.real_data_approved is approval.real_data_use_authorized is False


def test_session_roles_are_pairwise_separated_at_required_boundaries():
    for values in (
        ("same", "environment-reviewer", "same", "requester", "operator", "reviewer", "approver"),
        ("environment-verifier", "environment-reviewer", "environment-approver",
         "same", "same", "session-reviewer", "session-approver"),
        ("environment-verifier", "environment-reviewer", "environment-approver",
         "requester", "same", "same", "session-approver"),
        ("environment-verifier", "environment-reviewer", "environment-approver",
         "same", "session-operator", "same", "session-approver"),
        ("environment-verifier", "environment-reviewer", "environment-approver",
         "requester", "same", "session-reviewer", "same"),
        ("environment-verifier", "environment-reviewer", "same",
         "requester", "operator", "reviewer", "same"),
    ):
        with pytest.raises(LocalRAGExecutionError, match="session_role_conflict"):
            SessionRoleContext(*values)


@pytest.mark.parametrize("attack", (
    "missing_review", "missing_approval", "rejected_review", "rejected_approval",
    "forged_review", "forged_approval", "review_request_mismatch",
    "approval_review_mismatch", "reviewer_role_mismatch", "approver_role_mismatch",
    "same_forged_digest", "temporal_order",
))
def test_session_preapproval_adversarial_chains_leave_registry_and_replay_unchanged(attack):
    chain = approved_session_chain()
    kwargs = registry_kwargs(chain)
    review = kwargs["session_review"]
    approval = kwargs["session_approval"]
    if attack == "missing_review":
        kwargs["session_review"] = None
    elif attack == "missing_approval":
        kwargs["session_approval"] = None
    elif attack == "rejected_review":
        kwargs["session_review"] = replace(review, result=SessionReviewResult.REJECTED)
    elif attack == "rejected_approval":
        kwargs["session_approval"] = replace(approval, result=SessionApprovalResult.REJECTED)
    elif attack == "forged_review":
        object.__setattr__(review, "findings_digest", digest("forged-findings"))
    elif attack == "forged_approval":
        object.__setattr__(approval, "review_digest", digest("forged-review"))
    elif attack == "review_request_mismatch":
        wrong_review = replace(review, session_request_digest=digest("other-request"))
        kwargs["session_review"] = wrong_review
        kwargs["session_approval"] = replace(approval,
                                               review_digest=wrong_review.canonical_digest)
    elif attack == "approval_review_mismatch":
        kwargs["session_approval"] = replace(approval, review_digest=digest("other-review"))
    elif attack == "reviewer_role_mismatch":
        wrong_review = replace(review, reviewer_id="other-session-reviewer")
        kwargs["session_review"] = wrong_review
        kwargs["session_approval"] = replace(approval,
                                               review_digest=wrong_review.canonical_digest)
    elif attack == "approver_role_mismatch":
        kwargs["session_approval"] = replace(approval, approver_id="other-session-approver")
    elif attack == "same_forged_digest":
        forged_request_digest = digest("forged-request")
        wrong_review = replace(review, session_request_digest=forged_request_digest)
        kwargs["session_review"] = wrong_review
        kwargs["session_approval"] = replace(approval,
            session_request_digest=forged_request_digest,
            review_digest=wrong_review.canonical_digest)
    else:
        kwargs["session_review"] = replace(
            review, reviewed_at=approval.approved_at + timedelta(seconds=1))
    registry = TestOnlySessionRegistry()
    before = (registry.sessions, registry.write_count, registry.mutation_count,
              registry.event_count, registry.replay_snapshot)
    denied = registry.approve(**kwargs)
    assert not denied.applied
    expected_reason = (SessionRegistryReason.ROLE_CONFLICT
        if attack in {"reviewer_role_mismatch", "approver_role_mismatch"}
        else SessionRegistryReason.TEMPORAL_INVALID
        if attack == "temporal_order" else SessionRegistryReason.INVALID_CHAIN)
    assert expected_reason in denied.reasons
    assert before == (registry.sessions, registry.write_count, registry.mutation_count,
                      registry.event_count, registry.replay_snapshot)
    assert registry.replay_snapshot == (
        frozenset(), frozenset(), frozenset(), frozenset())
    assert ExecutionSideEffectAccounting().all_zero


@pytest.mark.parametrize("mutation,reason", (
    ("replay", SessionRegistryReason.REPLAY),
    ("generation", SessionRegistryReason.GENERATION_MISMATCH),
    ("predecessor", SessionRegistryReason.PREDECESSOR_MISMATCH),
))
def test_registry_replay_generation_and_predecessor_fail_closed(mutation, reason):
    chain = approved_session_chain()
    registry, result, request, roles, env_manifest, env_suite, env_decision, env_review, \
        env_approval, env_roles, int_manifest, fixture, plan, int_receipt, int_review, \
        int_approval, int_roles, session_review, session_approval = chain
    before = (registry.sessions, registry.write_count, registry.mutation_count,
              registry.event_count, registry.replay_snapshot)
    kwargs = dict(session_id="session-rejected", request=request,
        environment_manifest=env_manifest, environment_suite=env_suite,
        environment_decision=env_decision, environment_review=env_review,
        environment_approval=env_approval, environment_roles=env_roles,
        integration_manifest=int_manifest, data_flow_plan=plan, fixture=fixture,
        integration_receipt=int_receipt, integration_review=int_review,
        integration_approval=int_approval, integration_roles=int_roles,
        session_review=session_review, session_approval=session_approval,
        session_roles=roles,
        session_generation=2, predecessor_session_digest=result.session.canonical_digest,
        approved_at=NOW + timedelta(minutes=11))
    if mutation == "generation":
        kwargs["session_generation"] = 9
    elif mutation == "predecessor":
        kwargs["predecessor_session_digest"] = digest("wrong-predecessor")
    rejected = registry.approve(**kwargs)
    assert not rejected.applied and reason in rejected.reasons
    assert before == (registry.sessions, registry.write_count, registry.mutation_count,
                      registry.event_count, registry.replay_snapshot)


@pytest.mark.parametrize("fault", (SessionRegistryFault.CANDIDATE_STATE,
                                    SessionRegistryFault.BEFORE_SWAP))
def test_registry_fault_injection_leaves_state_and_replay_unchanged(fault):
    registry, result, *_ = approved_session_chain(fault=fault)
    assert not result.applied and result.reasons == (SessionRegistryReason.COMMIT_FAULT,)
    assert registry.sessions == ()
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (0, 0, 0)
    assert registry.replay_snapshot == (frozenset(), frozenset(), frozenset(), frozenset())


def test_registry_retry_after_commit_fault_succeeds_once():
    chain = approved_session_chain(fault=SessionRegistryFault.BEFORE_SWAP)
    registry, failed, request, roles, env_manifest, env_suite, env_decision, env_review, \
        env_approval, env_roles, int_manifest, fixture, plan, int_receipt, int_review, \
        int_approval, int_roles, session_review, session_approval = chain
    assert not failed.applied
    retried = registry.approve(session_id="session-023", request=request,
        environment_manifest=env_manifest, environment_suite=env_suite,
        environment_decision=env_decision, environment_review=env_review,
        environment_approval=env_approval, environment_roles=env_roles,
        integration_manifest=int_manifest, data_flow_plan=plan, fixture=fixture,
        integration_receipt=int_receipt, integration_review=int_review,
        integration_approval=int_approval, integration_roles=int_roles,
        session_review=session_review, session_approval=session_approval,
        session_roles=roles, session_generation=1, predecessor_session_digest=None,
        approved_at=NOW + timedelta(minutes=10))
    assert retried.applied
    assert (registry.write_count, registry.mutation_count, registry.event_count) == (1, 1, 1)


@pytest.mark.parametrize("lifecycle", (SessionLifecycle.EXPIRED, SessionLifecycle.REVOKED,
                                        SessionLifecycle.SUPERSEDED))
def test_terminal_sessions_cannot_execute(lifecycle):
    chain = approved_session_chain()
    registry, result, request, _, env_manifest, _, _, _, env_approval, _, \
        int_manifest, fixture, plan, *_ = chain
    transitioned = registry.transition(source_session=result.session,
        new_session_id=f"session-{lifecycle.value}", lifecycle=lifecycle,
        transitioned_at=NOW + timedelta(minutes=11))
    assert transitioned.applied
    with pytest.raises(LocalRAGExecutionError, match="execution_binding_invalid"):
        ControlledLocalRAGExecutionAdapter().execute(execution_receipt_id="denied-execution",
            session=transitioned.session, request=request, environment_manifest=env_manifest,
            environment_approval=env_approval, integration_manifest=int_manifest,
            data_flow_plan=plan, fixture=fixture, operator_id="session-operator",
            started_at=NOW + timedelta(minutes=12), finished_at=NOW + timedelta(minutes=13))


def test_controlled_execution_emits_all_eleven_metadata_only_stage_results():
    _, evidence, accounting, receipt = controlled_execution()
    assert tuple(value.stage for value in evidence) == tuple(RAGStage)
    assert all(value.result is StageExecutionResult.PASSED for value in evidence)
    assert receipt.result is SessionExecutionResult.PASSED and accounting.all_zero
    assert canonical_object_valid(receipt)
    assert repr(receipt) == "SessionExecutionReceipt(<safe>)"
    with pytest.raises(LocalRAGExecutionError, match="execution_receipt_invalid"):
        replace(receipt, operator_id="forged-operator")


def test_exact_v022_object_chain_rejects_forged_operator():
    chain = approved_session_chain()
    registry, _, request, roles, env_manifest, env_suite, env_decision, env_review, \
        env_approval, env_roles, int_manifest, fixture, plan, int_receipt, int_review, \
        int_approval, int_roles, session_review, session_approval = chain
    object.__setattr__(int_receipt, "operator_id", "forged-operator")
    rejected = TestOnlySessionRegistry().approve(session_id="forged-session", request=request,
        environment_manifest=env_manifest, environment_suite=env_suite,
        environment_decision=env_decision, environment_review=env_review,
        environment_approval=env_approval, environment_roles=env_roles,
        integration_manifest=int_manifest, data_flow_plan=plan, fixture=fixture,
        integration_receipt=int_receipt, integration_review=int_review,
        integration_approval=int_approval, integration_roles=int_roles,
        session_review=session_review, session_approval=session_approval,
        session_roles=roles,
        session_generation=1, predecessor_session_digest=None,
        approved_at=NOW + timedelta(minutes=10))
    assert not rejected.applied and SessionRegistryReason.INVALID_CHAIN in rejected.reasons


def test_operator_fixture_plan_and_environment_mismatches_are_denied():
    chain = approved_session_chain()
    _, result, request, _, env_manifest, _, _, _, env_approval, _, int_manifest, fixture, plan, *_ = chain
    adapter = ControlledLocalRAGExecutionAdapter()
    object.__setattr__(request, "operator_id", "different-operator")
    with pytest.raises(LocalRAGExecutionError, match="execution_binding_invalid"):
        adapter.execute(execution_receipt_id="mismatch", session=result.session, request=request,
            environment_manifest=env_manifest, environment_approval=env_approval,
            integration_manifest=int_manifest, data_flow_plan=plan, fixture=fixture,
            operator_id="session-operator", started_at=NOW + timedelta(minutes=11),
            finished_at=NOW + timedelta(minutes=12))


@pytest.mark.parametrize("target", ("environment", "integration", "plan", "fixture"))
def test_exact_execution_object_mismatches_are_denied(target):
    chain = approved_session_chain()
    _, result, request, _, env_manifest, _, _, _, env_approval, _, int_manifest, fixture, plan, *_ = chain
    values = {
        "environment_manifest": env_manifest,
        "integration_manifest": int_manifest,
        "data_flow_plan": plan,
        "fixture": fixture,
    }
    if target == "environment":
        values["environment_manifest"] = replace(env_manifest,
                                                   environment_id="other-environment")
    elif target == "integration":
        values["integration_manifest"] = replace(int_manifest,
                                                   integration_id="other-integration")
    elif target == "plan":
        values["data_flow_plan"] = replace(plan, plan_id="other-plan")
    else:
        values["fixture"] = replace(fixture, fixture_id="other-fixture")
    with pytest.raises(LocalRAGExecutionError, match="execution_binding_invalid"):
        ControlledLocalRAGExecutionAdapter().execute(execution_receipt_id="object-mismatch",
            session=result.session, request=request, environment_approval=env_approval,
            operator_id="session-operator", started_at=NOW + timedelta(minutes=11),
            finished_at=NOW + timedelta(minutes=12), **values)


def test_time_expired_session_and_future_receipt_are_rejected():
    chain, evidence, accounting, receipt = controlled_execution()
    _, result, request, roles, env_manifest, _, env_decision, _, env_approval, _, \
        int_manifest, fixture, plan, *_ = chain
    with pytest.raises(LocalRAGExecutionError, match="execution_binding_invalid"):
        ControlledLocalRAGExecutionAdapter().execute(execution_receipt_id="expired-execution",
            session=result.session, request=request, environment_manifest=env_manifest,
            environment_approval=env_approval, integration_manifest=int_manifest,
            data_flow_plan=plan, fixture=fixture, operator_id="session-operator",
            started_at=NOW + timedelta(hours=21), finished_at=NOW + timedelta(hours=21, seconds=1))
    decision = evaluate_real_data_trial_readiness(env_decision, result.session, evidence,
        receipt, accounting, None, None, roles, evaluation_time=NOW + timedelta(minutes=11))
    assert decision.state is RealDataTrialReadinessState.INELIGIBLE
    assert "session_temporal_or_lifecycle_invalid" in decision.reason_codes
