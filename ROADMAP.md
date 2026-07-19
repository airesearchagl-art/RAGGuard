# RAGGuard Roadmap

## In progress: RAG Benchmark Harness v0.9 Local RAG compatibility

v0.9 introduces a product-neutral compatibility boundary between the v0.8 loopback HTTP transport
and any future Local RAG product. Product-specific versions and field names belong to an explicit
Compatibility Profile. They must not alter transport security, evaluator behavior, report
top-level keys, or existing exit codes.

### Phase plan

- Phase A: compatibility profile and version contract. Completed.
- Phase B: health and capabilities contract. Completed.
- Phase C: request and response mapping contract. Completed.
- Phase D: synthetic compatibility harness. Completed.
- Phase E: profile integration and security E2E.
- Phase F: docs, CI, and release preparation.

### Compatibility boundary

- Unknown profile IDs, profile versions, and protocol major versions fail closed.
- Required capabilities are checked before retrieval; optional capabilities are omitted safely.
- Request and response mapping is explicit. Schema guessing, automatic fallback profiles, and
  implicit score normalization are forbidden.
- Only safe opaque source identifiers may reach existing reports. Filesystem paths, UNC values,
  drive-letter paths, home paths, and full URLs are rejected rather than rewritten.
- Product-neutral failures map through `RetrievalAdapterError` and `BenchmarkError` to CLI error
  `3` without product, endpoint, query, path, or raw payload disclosure.

### Phase A delivery

- Added typed `CompatibilityProfile`, strict `SemanticVersion`, explicit field mappings, optional
  feature flags, and allowlisted score/source policies.
- Added exact profile registry selection with no fallback. Major mismatches fail closed, and minor
  differences require an explicit allowlist; patch differences within an accepted minor are
  compatible.
- Added safe relative HTTP path validation and bounded compatibility error categories without
  rejected values in exceptions or profile representations.
- Added contract tests only. Profile mappings are not executed, and health/capability communication
  remains Phase B work.

### Phase B delivery

- Added immutable health, capabilities, and compatibility-result models that discard raw mappings
  after validation.
- Added exact health schema/status/service checks and fail-closed protocol major/minor validation
  using the selected profile contract.
- Added negotiation for five required capabilities and explicitly requested optional capabilities,
  including profile feature-flag alignment with no implicit downgrade or fallback.
- Added bounded health/capability error categories and safe summary representations without raw
  status, version, capability value, endpoint, path, product, or payload disclosure.
- Added contract tests only. HTTP communication, bounded-client integration, request/response
  mapping execution, and CLI/config integration remain unimplemented Phase C-or-later work.

### Phase C delivery

- Added typed bounded standard requests and explicit flat mapping execution with a 64 KiB encoded
  request limit and no raw mapping retention.
- Added product-response mapping to existing `RankedResult` values with required-field, safe source
  identifier, rank continuity, duplicate ID, top-k, metadata, and score-semantics validation.
- Tied score, title, matched-keyword, and query-ID behavior to the negotiated capability result;
  requested missing fields fail closed and unnegotiated optional fields are not retained.
- Added bounded mapping error categories and safe summaries containing only counts, declared score
  semantics, and enabled optional fields.
- Kept the work contract-only. Synthetic compatibility harness execution, CLI/config integration,
  health/capability HTTP communication, and real-product access remain unimplemented.

### Phase D delivery

- Added a deterministic test-oriented harness that directly composes the Phase A-C production
  profile, health, capability, request-mapping, response-mapping, and ranked-result contracts.
- Added an immutable safe result containing only profile/protocol/health status, enabled optional
  capabilities, mapped request and result counts, score semantics, and normalized ranked results.
- Added happy-path coverage for all score semantics and fail-closed coverage for profile/version,
  health, capabilities, mappings, identifiers, ranks, duplicates, top-k, malformed responses, and
  query-ID echo.
- Kept the harness free of network, filesystem, sleep, timeout, randomness, product schema,
  fixtures, CLI/config integration, and real-product access. Phase E remains unimplemented.

### Separate manual product gate

Real-product validation is not a v0.9 implementation phase and is never run from CI. A separately
approved manual task must identify the product, version, selected profile, synthetic query set, and
stop conditions before connecting. It is limited to loopback, uses no credentials or real data,
stores no raw response, emits only a safe summary, and stops immediately without fallback on any
unexpected result.

### Non-goals

- Real Local RAG or product-specific adapter integration.
- Product auto-discovery, fallback profile selection, or response-schema inference.
- Filesystem retrieval, external/private-LAN traffic, credentials, real documents, embeddings,
  vector databases, LLM evaluation, external APIs, cloud services, or external MCP.

## Completed: RAG Benchmark Harness v0.8 secure Local RAG transport

v0.8 defines and incrementally verifies a loopback-only HTTP transport without connecting to a real
Local RAG system during the design phase. Synthetic retrieval remains the default, and every
transport phase must preserve the existing adapter, evaluator, report, and exit-code boundaries.

### Phase plan

- Phase A: define endpoint validation and HTTP transport contracts - completed.
- Phase B: add fake loopback server contract tests with fixed synthetic responses - completed.
- Phase C: implement the bounded loopback HTTP client - completed.
- Phase D: integrate the transport with safe CLI and config selection - completed.
- Phase E: add synthetic end-to-end and transport security tests - completed.
- Phase F: finalize docs, CI coverage, and release notes - completed.

### v0.8 endpoint

- The explicit `loopback_http` path is integrated with bounded config loading, loopback-only
  resolution and peer checks, one-shot lifecycle, deterministic evaluation, safe reports, and
  PASS `0` / WARNING `1` / FAIL `2` / CLI error `3`.
- Synthetic remains the default and `in_memory` compatibility is preserved.
- Verification is limited to fixed synthetic responses from ephemeral fake loopback servers. No
  real Local RAG product, real document, external/private-LAN endpoint, or credential is used.

### Next candidates

- Pre-connection product validation: define a separately reviewed compatibility gate before any
  real Local RAG endpoint is contacted.
- Compatibility validation: version and capability negotiation, response-contract conformance, and
  upgrade/downgrade behavior using synthetic doubles first.
- Operational monitoring: bounded duration/result-count/status/error-category telemetry without
  query, endpoint, credential, raw traffic, or real-path disclosure.

### Security constraints and non-goals

- Allow only `127.0.0.1`, `::1`, or explicitly allowlisted names whose complete resolution set is
  loopback; reject external, private-LAN, wildcard, unspecified, and changed destinations.
- Disable redirects and proxy use. Validate the peer destination for every new connection to reduce
  DNS rebinding and time-of-check/time-of-use risk.
- Require bounded JSON requests and responses, connect/read/total timeouts, and safe error mapping.
- Do not load API keys, bearer tokens, credential files, cookies, environment secrets, or real paths.
- Do not implement real Local RAG, Hermes, LM Studio, filesystem retrieval, embeddings, vector
  databases, LLM evaluation, external APIs, cloud services, external MCP, or real-document access.

## Completed: RAG Benchmark Harness v0.7 local connection contract

v0.7 designs a local-only connection boundary before any Local RAG integration. Synthetic retrieval
remains the default operational retrieval path. The explicit `local-rag` path is limited to the
no-I/O in-memory synthetic transport and is not a real Local RAG connection.

### Phase plan

- Phase A: define configuration and transport contracts - completed.
- Phase B: implement an in-memory or fake transport with fixed synthetic responses - completed.
- Phase C: implement a local adapter client skeleton against the transport abstraction - completed.
- Phase D: add an explicit CLI selector and safe configuration loading - completed.
- Phase E: add synthetic end-to-end connection and error contract tests - completed.
- Phase F: finalize docs, CI coverage, and release notes - completed.

### Constraints and non-goals

- Approved transports remain local-only: in-memory first, with loopback HTTP, Unix socket, or Windows
  named pipe considered only in later implementation phases.
- External hosts, redirects, filesystem retrieval, credentials, embeddings, vector databases, LLM
  evaluation, cloud services, external APIs, and external MCP are out of scope.
- No direct access to `C:\\AI_Restricted` or real materials under `C:\\AI_Local_RAG` is allowed.
- The adapter may retrieve only through its future API boundary and must not expose configuration
  values, real paths, query text, source content, secrets, or stack traces.

## Completed: RAG Benchmark Harness v0.6 retrieval adapter interface

v0.6 establishes a stable retrieval interface so that the synthetic implementation and a future
local-only implementation can be selected without changing benchmark evaluation semantics.

### Phase plan

- Phase A: interface and ranked-result model extraction - completed.
- Phase B: migrate deterministic synthetic retrieval to the interface - completed.
- Phase C: add mock adapter and adapter contract tests - completed.
- Phase D: add a local-only adapter skeleton without a real RAG connection - completed.
- Phase E: document the interface, add CI coverage, and prepare release notes - completed.

### Constraints and non-goals

- Adapters receive a query and `top_k` and return deterministic ranked results or a typed retrieval error.
- The evaluator owns hit@k, source match, keyword coverage, no-result, unsafe-or-unknown, reporting, and result-to-exit-code mapping.
- Adapter-local scores must not be compared as universal quality scores across implementations.
- Reports keep identifiers and bounded metadata only; they never replay long document content.
- Synthetic fixtures remain the only data source during v0.6 implementation and testing.
- No Hermes, LM Studio, production Local RAG, embeddings, vector databases, LLM evaluation, external API, cloud, external MCP, `C:\\AI_Restricted`, or `C:\\AI_Local_RAG` real-document access is in scope.

## Completed: RAG Benchmark Harness v0.5 synthetic retrieval

v0.5 adds synthetic-only retrieval and scoring before any production RAG integration.
The benchmark harness remains loosely coupled from Local RAG and will not connect to Hermes, LM Studio,
real documents, embedding services, vector databases, LLM evaluators, cloud services, or external APIs.

### Phase plan

- Phase A: retrieval adapter / deterministic keyword search - completed
- Phase B: hit@k / expected source match - completed
- Phase C: expected keyword coverage / no-result / unsafe-or-unknown evaluation - completed
- Phase D: report / CI / docs cleanup - completed

### Design constraints

- Use synthetic fixtures only.
- Do not use real documents, real project names, real company names, or real person names.
- Keep the retrieval adapter separate from benchmark evaluation.
- Keep any future real RAG integration behind an adapter boundary and design it separately after v0.5.
- Preserve existing `check-mask` behavior and exit codes.

### v0.5 delivered capabilities

- Synthetic retrieval adapter.
- Deterministic keyword / token overlap retrieval.
- Ranked benchmark results.
- hit@k and expected source match scoring.
- Expected keyword coverage scoring.
- No-result and unsafe-or-unknown expectation scoring.
- PASS / WARNING / FAIL / CLI error exit code alignment.

### Still not implemented

- Production Local RAG integration.
- Hermes or LM Studio integration.
- Embedding or vector database retrieval.
- LLM-based answer evaluation.
- External API or cloud service integration.

## Completed: RAG Benchmark Harness v0.4

RAG Benchmark Harnessは、Local RAG本線を直接操作せず、RAG品質を外部から検証する補助ツールとして整備しました。v0.4では実資料を使わず、synthetic corpusとsynthetic query setだけで動くbenchmark CLI skeletonを追加しました。

- Phase A: synthetic benchmark fixture設計 完了
- Phase B: benchmark CLI skeleton 完了
- Phase C: benchmark report skeleton拡充 完了
- Phase D: CI / docs整理 完了

設計上の優先事項:

- 実資料、実案件名、実会社名、実個人名を使わない
- expected source / expected keyword / expected answer hintを使う
- 将来のhit@k、expected source match、expected keyword coverageに備えたreport skeletonを出力する
- no-result query、unsafe / unknown answerを扱う
- v0.4では実RAG接続、検索評価、LLM評価、外部API評価、クラウド評価を使わない

### Phase A: synthetic benchmark fixture設計

Phase Aでは、RAG Benchmark Harnessの最初の実装に入る前に、synthetic corpusとsynthetic query setの形式を固定します。実ファイル追加はPhase B以降とし、この段階では配置案とフィールド定義のみを決めます。

- corpus配置案: `tests/fixtures/benchmark/corpus/`
- query set配置案: `tests/fixtures/benchmark/queries.jsonl`
- corpus文書は架空Markdownのみを使う
- corpus metadataは `document_id`、`title`、`tags`、`expected_searchable_facts` を基本にする
- query setは `query_id`、`question`、`expected_source_ids`、`expected_keywords`、`expected_answer_hint`、`no_result_expected`、`unsafe_or_unknown_expected` を基本にする
- 実資料、実案件名、実会社名、実個人名は使わない
- `C:\AI_Restricted` と `C:\AI_Local_RAG` 配下の実資料は使わない

Phase B-Dで、benchmark CLI skeleton、JSON / Markdown benchmark report skeleton、CI / docs整理まで完了しました。

### v0.4以降の候補

- retrieval / scoringを実装する前に、評価入力とreport schemaの互換性を維持する
- hit@k、expected source match、expected keyword coverageの実装方針を別PRで設計する
- 実RAG接続を行う場合も、Local RAG本線を直接変更しない疎結合なadapterとして扱う
- LLM評価や外部API評価は、明示的な設計と安全方針が固まるまで使わない

## Completed: Masked Document Checker v0.3

- Phase A: 金額・料率・坪単価 / 平米単価検出の強化
- Phase B: 住所候補検出の強化
- Phase C: 契約条件 / 内部情報キーワード拡張
- Phase D: 重複finding抑制とMarkdown report summary改善
- `--config config/rules.yaml` による `extend_builtin` 方式のルール追加
- 既存JSON / Markdownレポート構造と `matched_text` 伏せ字方針の維持
- 実資料を使わない安全fixture方針の維持

## Masked Document Checker v0.3候補

- 金額・単価・料率検出の強化
- 住所候補検出の強化
- 契約条件 / 内部情報キーワード拡張
- 重複finding抑制
- 追加pytest
- 実資料を使わない安全fixture方針の維持

## 1. Masked Document Checker

Markdownファイルまたはフォルダを対象に、個人情報・金額情報・契約情報・内部事情を検出し、JSON + Markdownレポートを出力する。今回のMVP実装範囲。

### v0.2候補

- `--config` によるルール読込
- ルール定義の外部化
- YAML不備時のCLIエラー
- 既存レポート形式の維持
- ルール追加時のpytest拡充

## 2. RAG Benchmark Harness

RAG構成ごとの検索品質、回答品質、再現性を比較する検証基盤。

## 3. Citation Verifier

回答内の引用と根拠資料の整合性を検証するツール。

## 4. RAG Scope Gate

投入対象資料のスコープ、禁止領域、公開可否を事前判定するゲート。

## 5. Document Conversion QA Tool

PDF、Word、Markdownなどの変換結果を検査し、欠落や表崩れを確認するツール。

## 6. Project Index Manager

プロジェクト別のRAG投入対象、除外対象、履歴を管理するインデックス。

## 7. RAG Error Log Analyzer

RAG回答の失敗ログを分類し、改善候補を抽出する分析ツール。

## 8. Local RAG Dashboard

ローカル環境で検査結果や投入状況を一覧するDashboard。今回のMVP範囲外。
