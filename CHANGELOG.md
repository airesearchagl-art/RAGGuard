# Changelog

## Unreleased

- Designed RAG Benchmark Harness v0.4.
- Planned synthetic corpus and synthetic query set inputs.
- Planned JSON / Markdown benchmark reports.
- Planned local metrics such as hit@k, expected source match, expected keyword coverage, no-result handling, and unsafe / unknown answer handling.
- Kept v0.4 design free of real documents, external API evaluation, cloud services, and LLM-as-a-judge.

## v0.3

Masked Document Checker v0.3 completed the Phase A-D improvements.

- Added stronger money, rate, tsubo unit price, and square-meter unit price detection.
- Added address candidate detection for postal codes and address-like context.
- Added contract condition and internal information keyword coverage.
- Added duplicate finding suppression for identical file, line, rule_id, and redacted matched_text.
- Stabilized finding output order.
- Improved Markdown report readability with a summary near the top.
- Kept existing exit codes unchanged.
- Kept existing JSON report keys unchanged.
- Kept matched_text redaction policy.
- Kept fixtures fictional and did not use real documents, real project names, real company names, or real person names.

## v0.2

- Added `--config config/rules.yaml` support.
- Supported `mode: extend_builtin`.
- Preserved built-in rules when config rules are loaded.
- Treated invalid config as CLI error exit code `3`.
