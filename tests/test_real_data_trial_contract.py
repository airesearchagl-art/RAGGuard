from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone

import pytest

from ragguard.local_rag_integration import RAGStage
from ragguard.real_data_trial import *
from ragguard.storage_adapter import canonical_object_valid, digest


NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)
D = digest("v0.24-policy")


def safe_trial_policies():
    classification = RealDataClassificationPolicy(
        (RealDataClass.INTERNAL_LOW,),
        (RealDataClass.PERSONAL_DATA, RealDataClass.CREDENTIAL_LIKE,
         RealDataClass.HIGHLY_RESTRICTED),
        (RealDataClass.INTERNAL_RESTRICTED, RealDataClass.PERSONAL_DATA,
         RealDataClass.CONTRACTUAL_CONFIDENTIAL),
        (RealDataClass.PERSONAL_DATA, RealDataClass.CREDENTIAL_LIKE,
         RealDataClass.HIGHLY_RESTRICTED),
        (RealDataClass.PERSONAL_DATA, RealDataClass.CREDENTIAL_LIKE,
         RealDataClass.HIGHLY_RESTRICTED),
        (RealDataClass.PERSONAL_DATA, RealDataClass.CREDENTIAL_LIKE,
         RealDataClass.HIGHLY_RESTRICTED),
        tuple(RealDataClass), "v0.24")
    stages = TrialStagePolicy(tuple(RAGStage)[:4], tuple(RAGStage)[4:],
        RAGStage.CHUNKING, RAGStage.INPUT_CANDIDATE, RAGStage.CHUNKING)
    retention = TrialRetentionPolicy(*(TrialRetentionClass.NONE for _ in range(8)))
    logging = TrialLoggingPolicy(TrialLoggingClass.DIGEST_AND_REASON_ONLY, False, "v0.24")
    cache = TrialCachePolicy(TrialCacheClass.NONE, False, "v0.24")
    export = TrialExportPolicy(TrialExportClass.PROHIBITED, False, "v0.24")
    persistence = TrialPersistencePolicy(TrialPersistenceClass.NONE, False, False, "v0.24")
    return classification, stages, retention, logging, cache, export, persistence


def trial_scope(*, approved_session_digest=D, environment_manifest_digest=D,
                environment_approval_digest=D, integration_manifest_digest=D,
                fixture_validation_receipt_digest=D):
    classification, stages, retention, logging, cache, export, persistence = safe_trial_policies()
    scope = RealDataTrialScope("trial-scope-024", approved_session_digest,
        environment_manifest_digest, environment_approval_digest, integration_manifest_digest,
        fixture_validation_receipt_digest, classification.canonical_digest,
        stages.canonical_digest, retention.canonical_digest, logging.canonical_digest,
        cache.canonical_digest, export.canonical_digest, persistence.canonical_digest,
        RealDataClass.INTERNAL_LOW, RAGStage.CHUNKING, TrialRetentionClass.NONE,
        TrialLoggingClass.DIGEST_AND_REASON_ONLY, TrialCacheClass.NONE,
        TrialExportClass.PROHIBITED, TrialPersistenceClass.NONE,
        NOW + timedelta(minutes=16), NOW + timedelta(hours=2))
    return scope, classification, stages, retention, logging, cache, export, persistence


def test_scope_and_policies_are_immutable_canonical_and_safe_to_repr():
    values = trial_scope()
    assert all(canonical_object_valid(value) for value in values)
    assert all(repr(value) == f"{type(value).__name__}(<safe>)" for value in values)
    with pytest.raises(Exception):
        values[0].trial_scope_id = "changed"
    forbidden = {"path", "filename", "document_id", "customer_name", "person_name",
                 "project_name", "hostname", "endpoint", "credential", "token", "raw_data"}
    assert {item.name for item in fields(RealDataTrialScope)}.isdisjoint(forbidden)


def test_safe_default_classification_prohibits_sensitive_classes_and_export():
    _, policy, *_, export, persistence = trial_scope()
    assert RealDataClass.CREDENTIAL_LIKE in policy.prohibited_data_classes
    assert RealDataClass.HIGHLY_RESTRICTED in policy.prohibited_data_classes
    assert RealDataClass.PERSONAL_DATA in policy.prohibited_data_classes
    assert set(policy.export_prohibited_classes) == set(RealDataClass)
    assert not export.export_allowed and not persistence.persistent_write_allowed


def test_stage_policy_caps_trial_before_embedding_and_requires_masking():
    _, _, stages, *_ = trial_scope()
    assert stages.max_stage is RAGStage.CHUNKING
    assert stages.masking_required_before_stage is RAGStage.CHUNKING
    assert RAGStage.EMBEDDING in stages.prohibited_stages
    assert RAGStage.VECTOR_WRITE in stages.prohibited_stages
    assert set(stages.allowed_stages) | set(stages.prohibited_stages) == set(RAGStage)


def test_retention_logging_cache_export_and_persistence_defaults_are_fail_closed():
    _, _, _, retention, logging, cache, export, persistence = trial_scope()
    assert all(value is TrialRetentionClass.NONE for key, value in vars(retention).items()
               if key != "canonical_digest")
    assert logging.logging_class is TrialLoggingClass.DIGEST_AND_REASON_ONLY
    assert not logging.raw_content_logging_allowed
    assert cache.cache_class is TrialCacheClass.NONE and not cache.raw_content_cache_allowed
    assert export.export_class is TrialExportClass.PROHIBITED and not export.export_allowed
    assert persistence.persistence_class is TrialPersistenceClass.NONE
    assert not persistence.raw_content_persistence_allowed


def test_exact_policy_chain_passes_without_authorizing_execution():
    values = trial_scope()
    assert validate_trial_scope_policies(*values) == ()
    assert not hasattr(values[0], "real_data_access_authorized")
    assert not hasattr(values[0], "execute")


@pytest.mark.parametrize("index,replacement,reason", (
    (1, lambda value: replace(value,
        allowed_data_classes=(RealDataClass.INTERNAL_RESTRICTED,)),
     "trial_data_class_prohibited"),
    (2, lambda value: replace(value, max_stage=RAGStage.EMBEDDING,
        allowed_stages=tuple(RAGStage)[:5], prohibited_stages=tuple(RAGStage)[5:]),
     "trial_stage_policy_unsafe"),
    (3, lambda value: replace(value,
        transformed_content_retention=TrialRetentionClass.TRANSFORMED_EPHEMERAL_ONLY),
     "trial_retention_policy_unsafe"),
    (4, lambda value: replace(value, raw_content_logging_allowed=True),
     "trial_logging_policy_unsafe"),
    (5, lambda value: replace(value, raw_content_cache_allowed=True),
     "trial_cache_policy_unsafe"),
    (6, lambda value: replace(value, export_allowed=True),
     "trial_export_policy_unsafe"),
    (7, lambda value: replace(value, persistent_write_allowed=True),
     "trial_persistence_policy_unsafe"),
))
def test_policy_downgrades_are_rejected(index, replacement, reason):
    values = list(trial_scope())
    values[index] = replacement(values[index])
    assert reason in validate_trial_scope_policies(*values)


@pytest.mark.parametrize("data_class", (
    RealDataClass.CREDENTIAL_LIKE, RealDataClass.HIGHLY_RESTRICTED,
    RealDataClass.PERSONAL_DATA,
))
def test_prohibited_requested_data_classes_fail_closed(data_class):
    values = list(trial_scope())
    values[0] = replace(values[0], requested_data_class=data_class)
    assert "trial_data_class_prohibited" in validate_trial_scope_policies(*values)


def test_policy_canonical_digest_detects_post_construction_forgery():
    values = list(trial_scope())
    object.__setattr__(values[1], "policy_version", "forged-version")
    assert not canonical_object_valid(values[1])
    assert "forged_trial_policy_chain" in validate_trial_scope_policies(*values)
