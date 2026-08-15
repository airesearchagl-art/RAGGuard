from dataclasses import fields, replace
from datetime import timedelta

import pytest

from ragguard.local_rag_integration import RAGStage
from ragguard.real_data_access import *
from ragguard.real_data_trial import RealDataClass
from ragguard.storage_adapter import canonical_object_valid, digest
from test_local_rag_execution_session_contract import NOW
from test_real_data_trial_approval import approved_trial_chain


PURPOSE = digest("v0.25-limited-read-purpose")


def safe_access_policy() -> RealDataAccessPolicy:
    return RealDataAccessPolicy(
        (RealDataClass.INTERNAL_LOW,),
        (RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,),
        RAGStage.CHUNKING,
        1,
        RealDataByteClass.SMALL_DOCUMENT,
        1,
        RAGStage.CHUNKING,
        RealDataAccessRetentionClass.NONE,
        RealDataAccessLoggingClass.NONE,
        RealDataAccessCacheClass.NONE,
        RealDataAccessPersistenceClass.NONE,
        RealDataAccessExportClass.PROHIBITED,
        RealDataAccessNetworkClass.PROHIBITED,
    )


def access_selector_policy():
    _, trial_result, trial_kwargs, *_ = approved_trial_chain()
    policy = safe_access_policy()
    selector = RealDataAccessSelector(
        "selector-025", RealDataClass.INTERNAL_LOW,
        RealDataAccessSourceClass.APPROVED_LOCAL_TRIAL_SOURCE,
        RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,
        trial_kwargs["classification_policy"].canonical_digest,
        trial_result.record.canonical_digest, PURPOSE, RAGStage.CHUNKING,
        policy.canonical_digest)
    return selector, policy, trial_result.record, trial_kwargs


def test_selector_and_policy_are_immutable_canonical_and_safe_to_repr():
    selector, policy, *_ = access_selector_policy()
    assert canonical_object_valid(selector) and canonical_object_valid(policy)
    assert repr(selector) == "RealDataAccessSelector(<safe>)"
    assert repr(policy) == "RealDataAccessPolicy(<safe>)"
    with pytest.raises(Exception):
        selector.selector_id = "changed"


def test_selector_has_no_actual_location_identity_or_raw_identifier_fields():
    forbidden = {
        "path", "filename", "directory", "hostname", "customer_name",
        "project_name", "person_name", "raw_identifier", "raw_content",
        "credential", "token", "endpoint",
    }
    assert {item.name for item in fields(RealDataAccessSelector)}.isdisjoint(forbidden)


def test_safe_policy_is_internal_low_one_shot_chunking_candidate_only():
    _, policy, *_ = access_selector_policy()
    assert policy.allowed_data_classes == (RealDataClass.INTERNAL_LOW,)
    assert policy.allowed_document_classes == (
        RealDataDocumentClass.INTERNAL_LOW_DOCUMENT_CANDIDATE,)
    assert policy.max_stage is RAGStage.CHUNKING
    assert policy.max_documents == policy.allowed_read_count == 1
    assert policy.max_bytes_class is RealDataByteClass.SMALL_DOCUMENT
    assert policy.masking_required_before_stage is RAGStage.CHUNKING


def test_safe_policy_denies_retention_logging_cache_export_persistence_and_network():
    _, policy, *_ = access_selector_policy()
    assert policy.retention_class is RealDataAccessRetentionClass.NONE
    assert policy.logging_class is RealDataAccessLoggingClass.NONE
    assert policy.cache_class is RealDataAccessCacheClass.NONE
    assert policy.persistence_class is RealDataAccessPersistenceClass.NONE
    assert policy.export_class is RealDataAccessExportClass.PROHIBITED
    assert policy.network_class is RealDataAccessNetworkClass.PROHIBITED


def test_exact_v024_bound_selector_and_policy_pass_hard_gates():
    selector, policy, approved_trial, kwargs = access_selector_policy()
    assert validate_real_data_access_selector_policy(
        selector, policy, approved_trial, kwargs["scope"],
        kwargs["classification_policy"], kwargs["stage_policy"],
        kwargs["retention_policy"], kwargs["logging_policy"],
        kwargs["cache_policy"], kwargs["export_policy"],
        kwargs["persistence_policy"]) == ()


def test_stage_ceiling_may_narrow_but_never_widen_past_trial_ceiling():
    selector, policy, approved_trial, kwargs = access_selector_policy()
    policy = replace(policy, max_stage=RAGStage.MASKING)
    selector = replace(selector, allowed_stage_ceiling=RAGStage.MASKING,
                       selector_policy_digest=policy.canonical_digest)
    assert validate_real_data_access_selector_policy(
        selector, policy, approved_trial, kwargs["scope"],
        kwargs["classification_policy"], kwargs["stage_policy"],
        kwargs["retention_policy"], kwargs["logging_policy"],
        kwargs["cache_policy"], kwargs["export_policy"],
        kwargs["persistence_policy"]) == ()


@pytest.mark.parametrize("change,reason", (
    (lambda value: replace(value, allowed_data_classes=(RealDataClass.INTERNAL_RESTRICTED,)),
     "access_classification_scope_widened"),
    (lambda value: replace(value, allowed_document_classes=(
        RealDataDocumentClass.INTERNAL_RESTRICTED_DOCUMENT_CANDIDATE,)),
     "access_classification_scope_widened"),
    (lambda value: replace(value, max_stage=RAGStage.EMBEDDING),
     "access_stage_ceiling_widened"),
    (lambda value: replace(value, max_documents=2), "access_usage_scope_widened"),
    (lambda value: replace(value, max_bytes_class=RealDataByteClass.LARGE_DOCUMENT),
     "access_usage_scope_widened"),
    (lambda value: replace(value, allowed_read_count=2), "access_usage_scope_widened"),
    (lambda value: replace(value,
        retention_class=RealDataAccessRetentionClass.RAW_EPHEMERAL),
     "access_retention_logging_cache_downgrade"),
    (lambda value: replace(value, logging_class=RealDataAccessLoggingClass.RAW),
     "access_retention_logging_cache_downgrade"),
    (lambda value: replace(value, cache_class=RealDataAccessCacheClass.RAW),
     "access_retention_logging_cache_downgrade"),
    (lambda value: replace(value, persistence_class=RealDataAccessPersistenceClass.ALLOWED),
     "access_external_boundary_widened"),
    (lambda value: replace(value, export_class=RealDataAccessExportClass.ALLOWED),
     "access_external_boundary_widened"),
    (lambda value: replace(value, network_class=RealDataAccessNetworkClass.ALLOWED),
     "access_external_boundary_widened"),
))
def test_policy_widening_and_downgrade_fail_closed(change, reason):
    selector, policy, approved_trial, kwargs = access_selector_policy()
    policy = change(policy)
    selector = replace(selector, selector_policy_digest=policy.canonical_digest,
                       allowed_stage_ceiling=policy.max_stage)
    assert reason in validate_real_data_access_selector_policy(
        selector, policy, approved_trial, kwargs["scope"],
        kwargs["classification_policy"], kwargs["stage_policy"],
        kwargs["retention_policy"], kwargs["logging_policy"],
        kwargs["cache_policy"], kwargs["export_policy"],
        kwargs["persistence_policy"])


@pytest.mark.parametrize("attribute,value", (
    ("data_class", RealDataClass.INTERNAL_RESTRICTED),
    ("document_class", RealDataDocumentClass.INTERNAL_RESTRICTED_DOCUMENT_CANDIDATE),
    ("allowed_stage_ceiling", RAGStage.EMBEDDING),
    ("approved_trial_digest", digest("forged-approved-trial")),
    ("classification_digest", digest("forged-classification")),
))
def test_selector_scope_widening_and_forgery_fail_closed(attribute, value):
    selector, policy, approved_trial, kwargs = access_selector_policy()
    selector = replace(selector, **{attribute: value})
    reasons = validate_real_data_access_selector_policy(
        selector, policy, approved_trial, kwargs["scope"],
        kwargs["classification_policy"], kwargs["stage_policy"],
        kwargs["retention_policy"], kwargs["logging_policy"],
        kwargs["cache_policy"], kwargs["export_policy"],
        kwargs["persistence_policy"])
    assert reasons


def test_post_construction_forgery_breaks_canonical_selector_chain():
    selector, policy, approved_trial, kwargs = access_selector_policy()
    object.__setattr__(selector, "selector_id", "forged-selector")
    assert not canonical_object_valid(selector)
    assert "forged_access_selector_policy_chain" in validate_real_data_access_selector_policy(
        selector, policy, approved_trial, kwargs["scope"],
        kwargs["classification_policy"], kwargs["stage_policy"],
        kwargs["retention_policy"], kwargs["logging_policy"],
        kwargs["cache_policy"], kwargs["export_policy"],
        kwargs["persistence_policy"])


def test_policy_subdigests_are_stable_and_change_on_relevant_downgrade():
    policy = safe_access_policy()
    changed = replace(policy, logging_class=RealDataAccessLoggingClass.RAW)
    assert policy.retention_policy_digest == safe_access_policy().retention_policy_digest
    assert policy.logging_policy_digest != changed.logging_policy_digest
    assert policy.persistence_policy_digest == safe_access_policy().persistence_policy_digest


def test_contract_defines_no_execution_or_arbitrary_consume_method():
    selector, policy, *_ = access_selector_policy()
    forbidden = {"open", "read", "execute", "consume", "decrement", "reset", "refill"}
    assert forbidden.isdisjoint(set(dir(selector)))
    assert forbidden.isdisjoint(set(dir(policy)))
    assert selector.purpose_digest == PURPOSE
    assert NOW + timedelta(minutes=1) > NOW
