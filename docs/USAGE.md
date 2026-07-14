# Usage

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
