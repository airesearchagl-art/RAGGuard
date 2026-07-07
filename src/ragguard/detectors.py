from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    severity: str
    pattern: re.Pattern[str]
    recommendation: str
    redaction: str


DEFAULT_RECOMMENDATION = "RAG_OK投入前に該当箇所をマスクしてください。"
WARNING_RECOMMENDATION = "RAG_OK投入前に文脈を確認し、必要に応じてマスクしてください。"


RULES: tuple[Rule, ...] = (
    Rule(
        "email_address",
        "personal_info",
        "FAIL",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        DEFAULT_RECOMMENDATION,
        "email",
    ),
    Rule(
        "phone_number",
        "personal_info",
        "FAIL",
        re.compile(r"\b(?:0\d{1,4}-\d{1,4}-\d{3,4}|0\d{9,10})\b"),
        DEFAULT_RECOMMENDATION,
        "phone",
    ),
    Rule(
        "mobile_number",
        "personal_info",
        "FAIL",
        re.compile(r"\b0[789]0-\d{4}-\d{4}\b"),
        DEFAULT_RECOMMENDATION,
        "phone",
    ),
    Rule(
        "address_like",
        "personal_info",
        "FAIL",
        re.compile(r"(?:(?:住所|所在地|現地|物件所在地).{0,20})?(?:都|道|府|県).{0,30}(?:市|区|町|村).{0,30}(?:\d+丁目|\d+(?:-\d+){1,3}|番地|号)"),
        DEFAULT_RECOMMENDATION,
        "address",
    ),
    Rule(
        "address_postal_code",
        "personal_info",
        "FAIL",
        re.compile(r"\b\d{3}-\d{4}\b"),
        DEFAULT_RECOMMENDATION,
        "address",
    ),
    Rule(
        "address_context",
        "personal_info",
        "FAIL",
        re.compile(r"(?:住所|所在地|現地|物件所在地).{0,30}(?:\d+丁目|\d+番地|\d+号|.{1,20}(?:ビル|建物|棟))"),
        DEFAULT_RECOMMENDATION,
        "address",
    ),
    Rule(
        "amount",
        "financial_info",
        "FAIL",
        re.compile(r"(?:税込|税別)?\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:円|万円|億円|千円)(?:\s*(?:税込|税別))?"),
        DEFAULT_RECOMMENDATION,
        "amount",
    ),
    Rule(
        "percentage_rate",
        "financial_info",
        "FAIL",
        re.compile(r"(?:(?:料率|利率|手数料率).{0,10})?\d+(?:\.\d+)?\s*(?:%|％|パーセント)"),
        DEFAULT_RECOMMENDATION,
        "percentage",
    ),
    Rule(
        "unit_price",
        "financial_info",
        "FAIL",
        re.compile(
            r"(?:(?:坪単価|平米単価|㎡単価|m2単価|m²単価)\s*(?:[:：=]\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)?(?:\.\d+)?\s*(?:円|万円|億円|千円)?|(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:円|万円|億円|千円)\s*/\s*(?:坪|㎡|m2|m²))"
        ),
        DEFAULT_RECOMMENDATION,
        "amount",
    ),
    Rule(
        "payment_terms",
        "contract_info",
        "FAIL",
        re.compile(r"(?:支払条件|月末締め|翌月末払い|着手金|出来高払い|精算条件|追加業務費)"),
        DEFAULT_RECOMMENDATION,
        "keyword",
    ),
    Rule(
        "contract_terms",
        "contract_info",
        "FAIL",
        re.compile(r"(?:違約金|責任範囲|契約条件|契約交渉|免責|約款)"),
        DEFAULT_RECOMMENDATION,
        "keyword",
    ),
    Rule(
        "internal_sensitive",
        "internal_info",
        "FAIL",
        re.compile(r"(?:未公表|紛争|クレーム|内部評価|経営判断)"),
        DEFAULT_RECOMMENDATION,
        "keyword",
    ),
    Rule(
        "budget_word",
        "business_context",
        "WARNING",
        re.compile(r"予算"),
        WARNING_RECOMMENDATION,
        "keyword",
    ),
    Rule(
        "contract_word",
        "business_context",
        "WARNING",
        re.compile(r"契約"),
        WARNING_RECOMMENDATION,
        "keyword",
    ),
    Rule(
        "estimate_word",
        "business_context",
        "WARNING",
        re.compile(r"見積|概算"),
        WARNING_RECOMMENDATION,
        "keyword",
    ),
    Rule(
        "person_name_like",
        "personal_info",
        "WARNING",
        re.compile(r"(?:担当者名|担当者|作成者)\s*[:：]\s*[A-Za-z0-9_ -]{3,40}"),
        WARNING_RECOMMENDATION,
        "person",
    ),
    Rule(
        "internal_context_word",
        "internal_info",
        "WARNING",
        re.compile(r"(?:人事|異動|組織再編)"),
        WARNING_RECOMMENDATION,
        "keyword",
    ),
)


def redact_match(value: str, redaction: str) -> str:
    if redaction == "partial":
        if "@" in value:
            return redact_match(value, "email")
        if re.search(r"\d", value):
            return redact_match(value, "phone")
        return "[REDACTED_VALUE]"
    if redaction == "label":
        return "[REDACTED_VALUE]"
    if redaction == "keyword":
        return "[REDACTED_KEYWORD]"
    if redaction == "email":
        local, _, domain = value.partition("@")
        return f"{local[:1]}***@{domain[:1]}***"
    if redaction == "phone":
        digits = re.sub(r"\D", "", value)
        if len(digits) <= 4:
            return "***"
        return f"{digits[:2]}***{digits[-2:]}"
    if redaction == "amount":
        return "[REDACTED_AMOUNT]"
    if redaction == "percentage":
        return "[REDACTED_RATE]"
    if redaction == "address":
        return "[REDACTED_ADDRESS]"
    if redaction == "person":
        return "[REDACTED_PERSON_LIKE]"
    return "[REDACTED_KEYWORD]"
