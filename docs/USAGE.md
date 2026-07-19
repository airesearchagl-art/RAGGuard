# Usage

## v0.10 production profile approval design

No production Compatibility Profile is currently provided. Do not add a real product name,
endpoint, port, credential, customer identifier, project identifier, person name, or real document
path to RAGGuard configuration or documentation. Existing synthetic profiles are not production
compatibility claims.

A future manual compatibility validation requires a separately approved task that records only the
safe profile ID/version, normalized product version, operator and approver IDs, validation time,
approved test cases, and stop conditions. Before connecting, confirm an isolated local environment,
a loopback-only endpoint, no authentication requirement, synthetic corpus and queries only, no
external/private-LAN route, no proxy/redirect/retry/fallback, and no raw-response persistence.

The standard manual sequence is:

1. Confirm the selected profile/version and normalized target product version.
2. Confirm the loopback destination and synthetic-only corpus/query inputs.
3. Validate health and negotiate required and optional capabilities.
4. Run synthetic PASS, WARNING, and FAIL cases.
5. Check malformed, timeout, and oversized responses.
6. Confirm close/cleanup and report non-disclosure.
7. Stop the connection immediately and create a bounded safe summary.

The operator must not search real documents or perform exploratory retrieval. The safe summary may
contain protocol/health status, capability summary, per-case outcomes, bounded duration, result
count, safe error category, pass/fail decision, reviewer/approver IDs, and validation date. It must
not contain endpoints, ports, query text, raw requests/responses, source paths, document content,
credentials, headers, cookies, stack traces, or internal exception text.

Approval outcomes are `approved`, `approved_with_restrictions`, `rejected`, or
`needs_revalidation`. Restrictions must be explicit, such as an approved minor-version range,
disabled optional capability, unscored-only operation, or reduced top-k. Ambiguous temporary
approval, undocumented workarounds, indefinite exceptions, and automatic fallback are forbidden.
Unapproved, revoked, expired, unsupported, or revalidation-required profiles fail closed as CLI
error `3`; normal evaluated results remain PASS `0`, WARNING `1`, and FAIL `2`.

## v0.9 Phase A compatibility profile contract

v0.9 does not add a real-product command or configuration example. It defines an intermediate
Compatibility Profile that maps a product-neutral RAGGuard request and response contract to fixed
synthetic product shapes. Phase A implements the typed contract but does not add a CLI profile
loader. A synthetic profile mapping accepted by the internal constructor has this shape:

```yaml
profile_id: synthetic-compat-v1
profile_version: "1.0.0"
protocol_version: "1.0.0"
health_path: /health
capabilities_path: /capabilities
retrieve_path: /retrieve
request_field_mapping:
  query: query_text
  top_k: result_limit
  query_id: request_id
response_field_mapping:
  rank: position
  document_id: item_id
  score: relevance_score
  title: display_title
  source_id: safe_source_id
  matched_keywords: keyword_matches
score_semantics: higher_is_better
source_identifier_policy: opaque_safe_id
optional_feature_flags:
  keyword_metadata: true
  title: true
  query_id_echo: false
```

This is a contract example, not a loadable production config. Endpoint, port, real path,
credential, product name, and environment value are intentionally absent. Profile and protocol
versions use exactly `major.minor.patch`; prerelease/build forms are rejected. Unknown fields,
unknown profiles, major mismatches, unallowlisted minor versions, unsafe paths, duplicate mapping
targets, unsupported score semantics, and unsafe source policies fail closed without echoing the
rejected value. Patch differences inside an accepted minor are compatible.

The standard request remains bounded to `query`, `top_k`, optional `query_id`, and explicit
protocol/capability version. The 64 KiB body limit, 4,096-character query limit, and maximum top-k of
100 remain in force. Standard responses remain ranked results with safe opaque source identifiers;
document bodies, embeddings, filesystem paths, raw metadata, and full URLs are not accepted or
reported.

Phase A stores mappings as typed immutable entries but does not execute them. Health/capability
communication starts no earlier than Phase B. Compatibility verification will use synthetic
health, capabilities, and retrieve responses only.
There is no real product config or automatic product connection. Any future real-product check is a
separate, explicitly approved manual session using loopback, synthetic queries, no credentials, no
real documents, no raw-response persistence, safe summary output, and immediate stop without
fallback on error.

### Phase B health and capabilities contract

Phase B accepts only already bounded synthetic mappings at an internal validation boundary. A
health mapping must contain exactly `status`, `protocol_version`, and `service_available`.
`status` is one of `healthy`, `degraded`, `unavailable`, or `incompatible`; only `healthy` with
boolean `service_available: true` may proceed. The protocol major must match the selected profile,
and a minor difference requires the profile's explicit allowlist.

A capabilities mapping must include boolean `retrieval`, `bounded_top_k`,
`deterministic_result_schema`, `safe_source_identifier`, and `response_size_compliance`. Optional
boolean fields are `score`, `title`, `matched_keywords`, `query_id_echo`, and
`protocol_version_echo`. Missing optional fields are false and safely omitted unless the profile or
caller explicitly requested them; a requested but unsupported feature fails closed.

The resulting summary contains only the safe profile ID, protocol status, health status, required
capability outcome, and enabled optional capability names. Raw mappings, protocol values, endpoint,
port, product name, path, query, and payload are not retained or displayed. Existing HTTP response
size limits apply before this boundary. Phase B adds no CLI loader, HTTP communication, real
product connection, or request/response mapping execution.

### Phase C request and response mapping contract

Phase C executes the selected profile's internal flat field mapping only after compatibility
negotiation. A standard request accepts `query`, `top_k`, optional `query_id`, optional strict
`protocol_version`, and explicitly requested capabilities. It rejects unknown fields, booleans as
top-k, unsafe query IDs, unmapped requested fields, and encoded product payloads over 64 KiB.

The response boundary requires a root `results` list and explicit mappings for `rank`,
`document_id`, and safe opaque `source_id`. Declared scored profiles also require finite numeric
scores; higher/lower ordering is checked without inversion or normalization. `unscored` profiles do
not require or accept a product score. Negotiated title and matched-keyword fields must be present;
unnegotiated optional values are not copied. Unknown fields, duplicate IDs, rank gaps, unsafe source
identifiers, invalid metadata, and top-k overflow fail closed.

Mapping results expose only bounded summaries. Query text, product field values, endpoint, path,
credential, raw request/response, and internal exception details are not displayed. This is an
internal contract only: Phase C adds no CLI profile loader, transport integration, communication,
fixture, or real-product connection. Phase D remains the synthetic compatibility harness.

### Phase D synthetic compatibility harness

Phase D provides an internal test-only harness for fixed synthetic values. It resolves an explicit
profile/version, validates typed synthetic health and capabilities, negotiates optional features,
maps a bounded standard request, maps a fixed product-shaped response, and returns normalized
ranked results. It uses the production Phase A-C contracts directly and adds no separate mapping or
fallback logic.

The returned safe result exposes only the profile ID, protocol and health status, enabled optional
capabilities, mapped request field count, result count, score semantics, and normalized
`RankedResult` values. It does not retain raw health/capability/product mappings, query text,
profile routes, endpoints, paths, credentials, product names, or internal exception details.

The Phase D harness itself has no CLI command or I/O. Phase E reuses those contracts through the
existing benchmark CLI only when `--adapter local-rag` selects a bounded `loopback_http` config
containing an explicit `compatibility_profile` selection:

```yaml
compatibility_profile:
  profile_id: synthetic_loopback_v1
  profile_version: "1.0.0"
  protocol_version: "1.0.0"
  requested_optional_capabilities: []
```

This selection is added to the existing fictional loopback config. Unknown fields, profiles,
versions, protocol mismatches, health/capability failures, and mapping failures return CLI error
`3`. Valid evaluation remains PASS `0`, WARNING `1`, or FAIL `2`. The profile stores no endpoint,
port, credential, or product schema, and reports add no raw config or HTTP values. Phase E is
verified only with an ephemeral fake loopback server and synthetic responses; it is not a real
Local RAG product configuration or compatibility claim.

The selection is always explicit. Omitting it, selecting an unknown profile, requesting an
unsupported profile or protocol version, or encountering a health, capability, request-mapping, or
response-mapping error fails closed with CLI error `3`. There is no automatic fallback, nearest
version choice, schema inference, or product discovery.

For valid retrieval and evaluation, exit codes remain PASS `0`, WARNING `1`, and FAIL `2`; config,
transport, and compatibility failures remain CLI error `3`. Reports do not add the endpoint, config
path, query text, raw mapping, raw response, credential, or internal exception. The only supported
profile example is synthetic and product-neutral. No production profile, real product name, real
endpoint, or credential example is provided.

The v0.9 release gate requires the full suite plus compatibility contract/mapping/harness, profile
integration E2E, HTTP security E2E, local-rag E2E, synthetic default exit `0`, profile integration
exits `0`/`1`/`2`/`3`, both CLI help commands, repository hygiene scans, and Python 3.11/3.12 CI.
Tag and Release creation are separate from the documentation PR.

## v0.8 secure transport design status

v0.8 Phase A provides endpoint, resolution-proof, request, response, size, and safe error models for
a future loopback HTTP transport. Phase B verifies these models through test-only ephemeral loopback
servers with fixed synthetic responses. The fake servers bind only to `127.0.0.1` or `::1`, do not
contact a real Local RAG system, and are always shut down after each test. No production HTTP client,
redirect following, proxy use, or filesystem retrieval is available in Phase B. Phase C adds the
internal bounded loopback HTTP client. Phase D makes that client selectable only through explicit
`local-rag` configuration while preserving the Synthetic default and existing `in_memory` path.

The Phase C client performs one short-lived request. It resolves an allowlisted hostname immediately
before connection, requires every resolved address and the actual peer to be loopback, connects to a
validated IP literal, sends bounded UTF-8 JSON, reads only the configured limit plus one byte, and
always closes. Redirects, environment or system proxies, retries, connection pooling, external or
private-LAN destinations, and raw traffic persistence are not supported.

HTTP use requires an explicit local-rag selection and explicit safe endpoint config.
Only `127.0.0.1`, `::1`, or a separately reviewed allowlisted name resolving exclusively to
loopback addresses may be accepted. Private LAN addresses, external addresses, `0.0.0.0`, wildcard
binds, redirects, and proxy routing are rejected. Endpoint changes must come from explicit config;
responses cannot redirect or otherwise replace the destination.

v0.8 authentication is intentionally absent. No API key, bearer token, credential file, cookie, or
environment credential is loaded. This is safe only under the loopback-only boundary. A future
authentication design must keep all credential material out of reports, logs, errors, and persisted
raw requests or responses.

Planned requests use fixed JSON content type and contain only bounded `query`, `top_k`, optional
`query_id`, and optional capability version. Query text remains bounded to 4,096 characters and
top-k to 100; the encoded HTTP body will also have an explicit byte limit before transmission.
Planned responses keep the existing ranked-result fields, default to a 256 KiB limit, have a hard
1 MiB ceiling, contain no more than top-k items, reject unknown fields, and never include long body
text or real paths.

Transport failures are operational CLI errors, not benchmark quality results. Invalid endpoint,
external host, refusal, timeout, status, content type, response size, response schema, or capability
maps through a bounded `RetrievalAdapterError` and `BenchmarkError` to CLI error `3`. Valid retrieval
continues to use PASS `0`, WARNING `1`, and FAIL `2` for evaluator outcomes.

Phase D loopback HTTP example:

```json
{
  "transport_type": "loopback_http",
  "endpoint": "http://127.0.0.1:8765/retrieve",
  "connect_timeout": 1.0,
  "read_timeout": 2.0,
  "total_timeout": 3.0,
  "default_top_k": 5,
  "response_size_limit": 262144,
  "capabilities": {
    "ranked_results": true,
    "matched_keywords": true,
    "filters": false
  }
}
```

Equivalent YAML using only a fictional loopback endpoint:

```yaml
transport_type: loopback_http
endpoint: http://127.0.0.1:8765/retrieve
connect_timeout: 1.0
read_timeout: 2.0
total_timeout: 3.0
default_top_k: 5
response_size_limit: 262144
capabilities:
  ranked_results: true
  matched_keywords: true
  filters: false
```

The config remains bounded to 64 KiB and is loaded with JSON parsing or `yaml.safe_load`. HTTP uses
`http` only, literal `127.0.0.1` / `::1`, or an explicitly allowlisted hostname whose complete
resolution set is loopback. Unknown fields are rejected. API keys, bearer tokens, credentials,
cookies, custom headers, proxy, redirect, and retry settings are not accepted.

The HTTP path performs initialize, local health/capability checks, one bounded request, response
normalization, and close for every query. PASS `0`, WARNING `1`, and FAIL `2` remain evaluator
outcomes. Config, endpoint, lifecycle, or transport failures return CLI error `3` without writing a
normal report. Existing JSON/Markdown top-level fields and `metadata.retrieval_adapter` remain
unchanged; endpoint, port, config path, headers, raw bodies, and credentials are not added.

Phase E verifies the complete `loopback_http` path with test-only ephemeral loopback servers and
synthetic fixed responses. JSON and YAML config, PASS `0`, WARNING `1`, FAIL `2`, CLI error `3`,
deterministic reports, one-shot lifecycle, failure cleanup, bounded reads, unsafe config, redirects,
timeouts, peer/resolution rejection, malformed responses, no retry, and sensitive-value
non-disclosure are fixed by E2E tests. A real Local RAG product and real documents remain
unsupported. Phase F completes documentation, CI, and release preparation without enabling them.

Phase F adds an explicit CI step for `tests/test_http_transport_security_e2e.py` on Python 3.11 and
3.12. It does not enable a real endpoint. Use of `auth`, `token`, `cookie`, custom authorization
headers, `proxy`, `redirect`, `retry`, or credential settings is rejected. The transport does not add
the endpoint, port, config path, headers, cookies, credentials, raw traffic, or raw HTTP query payload
to reports. The existing benchmark `question` field remains unchanged for report compatibility.

### v0.8 exit codes

- `0`: valid retrieval and PASS evaluation.
- `1`: valid retrieval and WARNING evaluation.
- `2`: valid retrieval and FAIL evaluation.
- `3`: CLI, config, endpoint, lifecycle, transport, timeout, size, status, content-type, or response
  contract error.

No real Local RAG connection example is provided. All v0.8 HTTP examples and tests use fictional
loopback endpoints and fixed synthetic data.

## v0.7 Phase A-F Local RAG contract

Phase A adds internal models and Protocols only. The current command continues to use Synthetic
retrieval:

```powershell
python -m ragguard benchmark --corpus tests/fixtures/benchmark/corpus --queries tests/fixtures/benchmark/queries.jsonl --output outputs/benchmark
```

The benchmark CLI keeps `synthetic` as the default. Phase D adds an explicit `local-rag` selector
that requires a bounded JSON or YAML configuration file:

```powershell
python -m ragguard benchmark --corpus tests/fixtures/benchmark/corpus --queries tests/fixtures/benchmark/queries.jsonl --output outputs/local-benchmark --adapter local-rag --adapter-config local-rag.json
```

Minimal JSON configuration:

```json
{
  "transport_type": "in_memory",
  "timeout_seconds": 3.0,
  "default_top_k": 5,
  "response_size_limit": 262144,
  "capabilities": {
    "ranked_results": true,
    "matched_keywords": false,
    "filters": false
  }
}
```

Only `in_memory` is accepted. Missing configuration, invalid values, unsupported fields or
transports, and unknown adapter values return CLI error `3`. A config supplied with the default
Synthetic adapter is rejected instead of being silently ignored.

Phase E end-to-end tests cover the full bounded path from CLI selection through config loading,
one-shot adapter and in-memory transport lifecycle, benchmark evaluation, report generation, and
process exit code. JSON and YAML configs are covered. Local synthetic responses exercise PASS `0`,
WARNING `1`, FAIL `2`, and CLI error `3`; Synthetic remains the default and its fixture remains PASS.

The JSON `metadata.retrieval_adapter` field and Markdown Inputs identify `synthetic` or `local-rag`.
No config path, timeout, response-size setting, credential, raw response, or long corpus content is
added to reports. The effective top-k remains visible as existing benchmark evaluation metadata.

### Exit-code interpretation

- PASS `0`, WARNING `1`, and FAIL `2` describe benchmark evaluation outcomes from valid bounded
  synthetic retrieval results.
- CLI error `3` describes adapter selection, config parsing or validation, lifecycle, transport,
  or response-contract failure. It is not a retrieval-quality FAIL.
- A local-rag evaluation FAIL therefore means the in-memory transport completed successfully but
  the synthetic result missed the benchmark expectation. A transport failure returns CLI error `3`
  and does not produce a normal evaluation result.

The only usable v0.7 local-rag transport is `in_memory`. It is synthetic-only and performs no
filesystem retrieval, localhost access, network communication, credential loading, or real Local
RAG access. JSON and YAML are loaded through bounded safe parsing and validated before adapter use.

The internal Phase A contract currently allows only `in_memory` as a transport type. It validates
positive bounded timeout, top-k, and response-size values; boolean capability flags; bounded query
requests; deterministic ranked responses; safe source identifiers; and allowlisted metadata.
These types are not loaded from a user config file and are not selectable from the CLI.

Phase B adds `InMemoryLocalRetrievalTransport` as a test-only no-I/O implementation. It returns
fixed synthetic responses and supports lifecycle and bounded failure testing. It does not read a
filesystem, open localhost or network connections, load credentials, or expose a CLI selector.
Normal use of `benchmark` remains on the existing Synthetic adapter.

The in-memory lifecycle is deterministic:

- `initialize` moves `created` to `initialized`; duplicate initialization is rejected.
- `retrieve`, `health_check`, and `capabilities` require the initialized state.
- `close` moves any state to `closed` and is idempotent.
- retrieval before initialization or after close returns a bounded retrieval error.
- injected health, capability, timeout, invalid-response, oversized-response, and transport failures
  are for contract tests only and do not expose raw details.

Phase C integrates the in-memory transport with the internal `LocalRAGRetrievalAdapter`. The client
is one-shot: it validates the request, initializes the transport, checks health and capabilities,
retrieves and normalizes one response, and closes in a cleanup path. It releases config and transport
references after success or failure. Unsupported transports are rejected before lifecycle execution.

This integration is available from `python -m ragguard benchmark` only through explicit
`--adapter local-rag`. Synthetic retrieval remains the CLI default. The local-rag option creates a
fresh one-shot in-memory adapter for each query. Filesystem retrieval, localhost communication,
network communication, credentials, and real Local RAG retrieval remain unimplemented.

Future local configuration must never be included in benchmark reports. Query text, credentials,
real paths, source bodies, and stack traces must also remain outside logs and reports. Contract tests
will use only fixed synthetic responses through an in-memory or fake transport.

## v0.6 Phase D local-only adapter skeleton

The benchmark CLI still uses the synthetic deterministic retrieval implementation from v0.5.
Phase A adds the internal adapter contract and validates ranked results before evaluation; it does
not add a new CLI option or connect to Local RAG. Adapters receive the validated query and requested
top-k, return bounded ranked-result metadata, and leave benchmark scoring and exit-code decisions
to the evaluator. Invalid adapter results use the existing CLI error `3` boundary.

Phase B moves the current Synthetic adapter behind this contract. The command, fixture inputs,
ranked results, reports, evaluation statuses, and exit codes remain unchanged.

Phase C adds test-only mock coverage for empty and ranked results, optional metadata, deterministic
ordering, invalid fields, duplicate documents, top-k limits, and adapter failures. Invalid adapter
output uses the existing benchmark CLI error boundary (exit code `3`); valid benchmark exit codes
and report keys do not change.

Phase D adds an internal local-only adapter skeleton but does not add a CLI selector or connection.
Without configuration it reports `not configured`; with configuration presence it reports an
unavailable dependency. Configuration values, paths, environment values, and internal exception
details are not read or reported. The synthetic benchmark command remains the only working adapter.

### Adapter availability in v0.6

| Adapter | Availability | CLI behavior |
| --- | --- | --- |
| `synthetic` | Operational for synthetic fixtures | Existing `benchmark` command and exit codes |
| `mock` | Tests only | No CLI selector |
| `local-rag` | Skeleton only; not operational | No selector; contract tests confirm CLI error `3` |

The local-rag skeleton performs no filesystem, localhost, or network access and retains no endpoint,
path, environment, or credential value. It must not be treated as a production Local RAG connector.

## v0.5 Phase D synthetic retrieval usage notes

v0.5 Phase A-D adds retrieval, local scoring, report cleanup, and CI checks for the benchmark CLI, but only against synthetic benchmark fixtures.
It does not connect to production Local RAG, Hermes, LM Studio,
embedding services, vector databases, LLM evaluation, cloud services, or external APIs.

The existing v0.4 command shape remains the starting point:

```powershell
python -m ragguard benchmark --corpus "tests/fixtures/benchmark/corpus" --queries "tests/fixtures/benchmark/queries.jsonl" --output "outputs/test_benchmark"
```

Phase A-D behavior:

- load the synthetic corpus through a retrieval adapter
- run deterministic keyword / token overlap retrieval
- produce ranked results with `rank`, `document_id`, `score`, `matched_keywords`, `title`, and `source_path`
- include ranked results in `benchmark_report.json` and `benchmark_report.md`
- evaluate hit@k using default top-k `5`
- set `hit_at_k` to true when any `expected_source_ids` entry appears in the top-k results
- set `source_match` to true only when all `expected_source_ids` entries appear in the top-k results
- output `matched_expected_source_ids`, per-query `evaluation_status`, and summary rates
- evaluate `expected_keywords` as keyword phrases covered by top-k matched tokens
- output `matched_keywords`, `missing_keywords`, and `keyword_coverage_rate`
- pass no-result queries when no synthetic retrieval results are returned
- mark unsafe-or-unknown queries as pass when no synthetic retrieval results are returned, or warning when retrieval returns results
- include stable summary counts and rates in JSON / Markdown reports
- check PASS / WARNING / FAIL / CLI error benchmark exit codes in CI
- avoid replaying long document content in reports

This is still synthetic scoring only. It does not evaluate answer wording, LLM behavior, or production Local RAG behavior.

Benchmark exit codes:

- PASS: `0`
- WARNING: `1`
- FAIL: `2`
- CLI / validation error: `3`

The `check-mask` command keeps its existing behavior and exit codes. Benchmark fixtures must remain
synthetic and must not include real documents, real project names, real company names, or real person names.

CI verifies these benchmark cases with synthetic query files:

- PASS: expected sources and keywords match, exit `0`
- WARNING: source matches but keyword coverage is partial, exit `1`
- FAIL: expected source is not retrieved, exit `2`
- CLI error: invalid JSONL, exit `3`

Benchmark reports:

- `benchmark_report.json`
- `benchmark_report.md`

The report summary includes evaluated query counts, PASS / WARNING / FAIL counts, hit@k rate,
source match rate, keyword coverage rate, no-result pass rate, and unsafe-or-unknown pass rate.
`ranked_results` include identifiers and matched keyword labels, but do not replay long corpus content.

v0.5 does not connect to production Local RAG, Hermes, LM Studio, embedding providers, vector
databases, LLM evaluators, external APIs, or cloud services.

## v0.4 RAG Benchmark Harness設計メモ

v0.4では、RAG Benchmark Harnessを追加する方針です。これはLocal RAG本線を直接操作せず、synthetic corpusとsynthetic query setを使ってRAG品質を外部から確認する補助ツールです。

想定CLI:

```powershell
python -m ragguard benchmark --corpus "path\to\synthetic_corpus" --queries "queries.jsonl" --output "outputs\benchmark"
```

v0.4では実資料、実案件名、実会社名、実個人名を使いません。評価はexpected source、expected keyword、expected answer hint、no-result query handlingを中心に行い、LLM評価や外部API評価は使わない方針です。

### synthetic benchmark fixture案

将来のv0.4実装では、benchmark用fixtureを以下のように配置する想定です。この設計段階ではファイルはまだ作成しません。

```text
tests/fixtures/benchmark/
  corpus/
    sample-policy-001.md
    sample-faq-001.md
  queries.jsonl
```

corpusは架空Markdown文書のみを使い、各文書に `document_id`、`title`、`tags`、`expected_searchable_facts` を持たせる方針です。query setはJSON Lines形式とし、`query_id`、`question`、`expected_source_ids`、`expected_keywords`、`expected_answer_hint`、`no_result_expected`、`unsafe_or_unknown_expected` を基本項目にします。

benchmark fixtureにも、実資料、実案件名、実会社名、実個人名は入れません。`C:\AI_Restricted` と `C:\AI_Local_RAG` 配下の実資料も使いません。

### Phase B CLI skeleton

Phase Bでは、synthetic corpusとqueries JSONLを読み込み、必須項目のvalidation結果をplaceholder reportとして出力します。実RAG接続、検索評価、LLM評価、外部API利用はまだ行いません。

```powershell
python -m ragguard benchmark --corpus "tests/fixtures/benchmark/corpus" --queries "tests/fixtures/benchmark/queries.jsonl" --output "outputs/test_benchmark_cli"
```

成功時は `benchmark_report.json` と `benchmark_report.md` を出力し、exit code `0` を返します。corpusまたはqueriesの必須項目不足、JSONL不備、存在しない `expected_source_ids` などはCLI errorとしてexit code `3` を返します。

### Phase C report structure

Phase Cでは、benchmark reportの構造を将来の評価実装に備えて拡充します。`benchmark_report.json` には `result`、`summary`、`corpus_count`、`query_count`、`per_query_results`、`warnings`、`errors`、`metadata` を出力します。

`per_query_results` には `query_id`、`question`、`expected_source_ids`、`expected_keywords`、`expected_answer_hint`、`no_result_expected`、`unsafe_or_unknown_expected`、`evaluation_status`、`notes` を含めます。Phase C時点では検索・評価は行わないため、`evaluation_status` は `not_evaluated` です。

Markdown reportは `Summary`、`Inputs`、`Per-query Results`、`Warnings`、`Errors` を確認しやすい順序で出力します。valid inputはexit code `0`、validation errorやCLI errorはexit code `3` の方針を維持します。

### Phase D CI / docs

Phase Dでは、GitHub Actions `Tests` workflowでbenchmark CLIの最小動作も確認します。既存のpytest、`check-mask --help`、`check-mask --config` 確認に加えて、以下をCIで実行します。

```powershell
python -m ragguard benchmark --help
python -m ragguard benchmark --corpus tests/fixtures/benchmark/corpus --queries tests/fixtures/benchmark/queries.jsonl --output outputs/ci_benchmark_report
```

この確認もsynthetic fixtureのみを使います。実RAG接続、検索評価、LLM評価、外部API利用は行いません。

### v0.4時点のbenchmark CLI運用メモ

v0.4時点のbenchmark CLIは、synthetic corpus / queries JSONLの読み込みとvalidation、report skeleton生成までを対象にします。

```powershell
python -m ragguard benchmark --corpus "tests/fixtures/benchmark/corpus" --queries "tests/fixtures/benchmark/queries.jsonl" --output "outputs/test_benchmark"
```

入力:

- corpus: `tests/fixtures/benchmark/corpus/` 配下の架空Markdown文書
- queries: `tests/fixtures/benchmark/queries.jsonl`
- corpus metadata: `document_id`、`title`、`tags`、`expected_searchable_facts`
- query fields: `query_id`、`question`、`expected_source_ids`、`expected_keywords`、`expected_answer_hint`、`no_result_expected`、`unsafe_or_unknown_expected`

出力:

- `benchmark_report.json`
- `benchmark_report.md`

まだ検索・評価は行いません。`per_query_results` の `evaluation_status` は `not_evaluated` です。実資料、実案件名、実会社名、実個人名はbenchmark fixtureに入れません。

## v0.3 運用メモ

v0.3時点では、`python -m ragguard check-mask ...` を推奨実行方法とします。`--config config/rules.yaml` を指定すると、内蔵ルールにYAML定義ルールを追加して確認できます。

主な確認対象は、金額 / 料率 / 単価、住所候補、契約条件、内部情報キーワードです。Markdownレポートではsummaryでstatus、finding数、FAIL / WARNING件数を先に確認できます。

fixtureやconfig YAMLには、実資料、実案件名、実会社名、実個人名を入れないでください。`FAIL` はRAG_OK投入前の修正対象、`WARNING` は文脈確認対象です。

## ルール拡張時の運用方針

今後 `config/rules.yaml` や内蔵ルールを拡張する場合も、config YAMLには実案件名、実会社名、実個人名を入れません。fixtureは架空データのみを使い、実資料や実案件由来の文面は追加しません。

Masked Document CheckerはRAG投入前の補助チェックです。最終判断は人間が行います。`FAIL` はRAG_OK投入前に修正対象とし、`WARNING` は文脈確認対象として扱います。

Phase Aでは、金額、料率、坪単価 / 平米単価らしき表現の検出を強化しています。円 / 万円 / 億円 / 千円、税込 / 税別、% / ％ / パーセント、坪単価 / 平米単価 / ㎡単価 / m2単価が見つかった場合は、RAG_OK投入前に確認してください。

Phase Bでは、住所候補の検出を強化しています。郵便番号、都道府県 + 市区町村、丁目 / 番地 / 号、住所 / 所在地 / 現地 / 物件所在地の周辺表現が見つかった場合は、RAG_OK投入前に確認してください。

Phase Cでは、契約条件と内部情報キーワードの検出を強化しています。契約条件、特約、解約条項、違約金、秘密保持、NDA、優先交渉、専属専任、手付、支払条件、社内限り、内部資料、非公開、未公開、稟議、決裁、承認前、ドラフト、取扱注意が見つかった場合は、RAG_OK投入前に確認してください。

Phase Dでは、同一ファイル・同一行・同一ルール・同一伏せ字結果の重複findingを抑制し、Markdownレポートのsummaryでstatus、finding数、FAIL / WARNING件数を先に確認できるようにしています。

## 推奨実行方法

ローカル確認では、環境差が少ない以下の形式を推奨します。

```powershell
python -m ragguard check-mask --input "path\to\folder" --output "outputs\folder"
```

editable install後に `ragguard` コマンドが使える環境では、以下でも同じ処理を実行できます。

```powershell
ragguard check-mask --input "path\to\folder" --output "outputs\folder"
```

Windowsで `ragguard` が見つからない場合は、Pythonの `Scripts` ディレクトリが `PATH` 外にある可能性があります。まずは `python -m ragguard ...` を使い、必要に応じて利用中のPython環境の `Scripts` ディレクトリを `PATH` に追加してください。

## Markdownファイルを検査

```powershell
python -m ragguard check-mask --input "path\to\document.md" --output "outputs\single"
```

## Markdownフォルダを再帰検査

```powershell
python -m ragguard check-mask --input "path\to\folder" --output "outputs\folder"
```

`.md` 以外のファイルは無視します。出力先フォルダが存在しない場合は作成します。

## レポート

JSONとMarkdownの2種類を出力します。

- `masked_check_report.json`
- `masked_check_report.md`

FAILがある場合はRAG_OK投入前に修正してください。WARNINGのみの場合は文脈確認を行い、必要に応じてマスクしてください。

## fixtureでの確認例

```powershell
python -m ragguard check-mask --input "tests/fixtures/safe" --output "outputs/test_safe"
python -m ragguard check-mask --input "tests/fixtures/warning" --output "outputs/test_warning"
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail"
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail_config" --config "config/rules.yaml"
```

期待される終了コードは、safeが `0`、warningが `1`、failが `2`、fail + `--config` が `2` です。WARNING / FAIL の `1` / `2` は検査結果として正常な終了コードです。

## v0.2予定: 設定ファイル

v0.2では、`--config config/rules.yaml` によるルール読込に対応しています。YAML読込には `PyYAML` を使い、設定ファイルはローカルファイルとして扱います。外部APIやクラウドサービスは使いません。

```powershell
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail_config" --config "config/rules.yaml"
```

config未指定時は内蔵ルールのみを使います。config指定時は `mode: extend_builtin` のみ対応し、内蔵ルールにYAML定義ルールを追加します。

YAML不備、未対応mode、未対応version、必須キー不足、重複 `rule_id`、不正な正規表現などはCLIエラーとして終了コード `3` になります。既存のPASS / WARNING / FAILの終了コードとレポート形式は変わりません。

configやfixtureには、実資料・実案件名・実会社名・実個人名を含めないでください。

Windowsで `ragguard` がPATH上にない場合は、上記のように `python -m ragguard` を使ってください。
