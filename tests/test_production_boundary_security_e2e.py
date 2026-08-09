from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ragguard.production_authorization import (
    ProductionAuthorizationResult,
    evaluate_production_authorization,
)
from tests.test_production_authorization_evaluator import request


def test_digest_tampering_fails_closed() -> None:
    original = request()
    tampered = replace(original.evidence, registry_entry_digest="sha256:" + "f" * 64)
    candidate = evaluate_production_authorization(replace(original, evidence=tampered))
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE


def test_identity_tampering_fails_closed() -> None:
    original = request()
    candidate = evaluate_production_authorization(
        replace(
            original,
            evidence=replace(original.evidence, product_id="other-product"),
        )
    )
    assert candidate.result is ProductionAuthorizationResult.INELIGIBLE


def test_evaluator_has_no_side_effect_imports() -> None:
    root = Path(__file__).parents[1]
    text = (root / "src" / "ragguard" / "production_authorization.py").read_text(encoding="utf-8")
    for forbidden in (
        "import requests",
        "import httpx",
        "import socket",
        "import subprocess",
        "import pathlib",
        "import sqlite3",
        "import uuid",
        "import random",
    ):
        assert forbidden not in text


def test_no_activation_api_exists() -> None:
    import ragguard.production_authorization as module
    assert not hasattr(module, "ProductionAuthorizationActivation")
    assert not hasattr(module, "activate_production_authorization")


def test_safe_result_does_not_expose_source_entry() -> None:
    candidate = evaluate_production_authorization(request())
    assert "RegistryAdmissionEntry" not in repr(candidate)


def test_same_input_is_deterministic() -> None:
    first = evaluate_production_authorization(request())
    second = evaluate_production_authorization(request())
    assert first.canonical_digest == second.canonical_digest
