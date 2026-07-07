from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ragguard.detectors import RULES, Rule


ALLOWED_SEVERITIES = {"WARNING", "FAIL"}
ALLOWED_TYPES = {"regex", "keyword"}
ALLOWED_CATEGORIES = {
    "personal_info",
    "money",
    "contract",
    "internal",
    "name_candidate",
    "address_candidate",
}
ALLOWED_REDACTIONS = {"partial", "label", "keyword"}


class ConfigError(ValueError):
    """Raised when a rules YAML file cannot be safely used."""


def load_rules_from_config(config_path: Path, builtin_rules: tuple[Rule, ...] = RULES) -> tuple[Rule, ...]:
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")
    if not config_path.is_file():
        raise ConfigError(f"config path is not a file: {config_path}")

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in config file: {config_path}") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read config file: {config_path}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"config root must be a mapping: {config_path}")
    if data.get("version") != 1:
        raise ConfigError(f"config version must be 1: {config_path}")
    if data.get("mode") != "extend_builtin":
        raise ConfigError(f"config mode must be extend_builtin: {config_path}")
    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list):
        raise ConfigError(f"config rules must be a list: {config_path}")

    known_rule_ids = {rule.rule_id for rule in builtin_rules}
    custom_rules: list[Rule] = []
    for index, raw_rule in enumerate(raw_rules, start=1):
        custom_rule = _parse_rule(raw_rule, index, config_path, known_rule_ids)
        known_rule_ids.add(custom_rule.rule_id)
        custom_rules.append(custom_rule)

    return tuple(custom_rules)


def _parse_rule(raw_rule: Any, index: int, config_path: Path, known_rule_ids: set[str]) -> Rule:
    if not isinstance(raw_rule, dict):
        raise ConfigError(f"rule #{index} must be a mapping: {config_path}")

    rule_id = _required_string(raw_rule, "rule_id", index, config_path)
    if rule_id in known_rule_ids:
        raise ConfigError(f"duplicate rule_id in config: {rule_id}")

    category = _required_string(raw_rule, "category", index, config_path)
    if category not in ALLOWED_CATEGORIES:
        raise ConfigError(f"invalid category for rule_id {rule_id}: {category}")

    severity = _required_string(raw_rule, "severity", index, config_path)
    if severity not in ALLOWED_SEVERITIES:
        raise ConfigError(f"invalid severity for rule_id {rule_id}: {severity}")

    rule_type = _required_string(raw_rule, "type", index, config_path)
    if rule_type not in ALLOWED_TYPES:
        raise ConfigError(f"invalid type for rule_id {rule_id}: {rule_type}")

    recommendation = _required_string(raw_rule, "recommendation", index, config_path)
    redaction = _required_string(raw_rule, "redaction", index, config_path)
    if redaction not in ALLOWED_REDACTIONS:
        raise ConfigError(f"invalid redaction for rule_id {rule_id}: {redaction}")

    if rule_type == "regex":
        pattern_text = _required_string(raw_rule, "pattern", index, config_path)
        try:
            pattern = re.compile(pattern_text)
        except re.error as exc:
            raise ConfigError(f"invalid regex pattern for rule_id {rule_id}") from exc
    else:
        keywords = raw_rule.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise ConfigError(f"keywords must be a non-empty list for rule_id {rule_id}")
        if not all(isinstance(keyword, str) and keyword for keyword in keywords):
            raise ConfigError(f"keywords must contain non-empty strings for rule_id {rule_id}")
        pattern = re.compile("|".join(re.escape(keyword) for keyword in keywords))

    return Rule(
        rule_id=rule_id,
        category=category,
        severity=severity,
        pattern=pattern,
        recommendation=recommendation,
        redaction=redaction,
    )


def _required_string(raw_rule: dict[str, Any], key: str, index: int, config_path: Path) -> str:
    value = raw_rule.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"missing or invalid {key} in rule #{index}: {config_path}")
    return value
