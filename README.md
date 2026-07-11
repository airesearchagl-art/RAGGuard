# RAGGuard

[![Tests](https://github.com/airesearchagl-art/RAGGuard/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/airesearchagl-art/RAGGuard/actions/workflows/test.yml)

## Masked Document Checker v0.3

現時点のRAGGuardは、RAG投入前のマスク済みMarkdownをローカルで確認する `check-mask` CLIを提供します。

- `--config config/rules.yaml` によるローカルYAMLルール追加
- 金額 / 料率 / 坪単価 / 平米単価らしき表現の検出
- 郵便番号、所在地、住所候補らしき表現の検出
- 契約条件 / 内部情報キーワードの検出
- 同一file / line / rule_id / 伏せ字後matched_textの重複finding抑制
- Markdownレポート上部のsummary表示
- JSON / Markdownレポート出力
- `matched_text` の伏せ字化

RAGGuardは、RAG投入前のマスク済みMarkdown資料に、個人情報・金額情報・契約情報・内部事情が残っていないかをローカルで確認するためのPython CLIです。

初回MVPの対象は **Masked Document Checker** のみです。GUI、Dashboard、Citation Verifier、RAG Benchmark Harnessは今回の範囲外です。

## インストール

```powershell
python -m pip install -e .
```

実行時の外部依存は、ローカルYAML設定読込に使う `PyYAML` のみです。外部APIやクラウドサービスは使いません。

Windowsでは、editable install後に `ragguard` コマンドが配置されるPython `Scripts` ディレクトリが `PATH` に入っていない場合があります。その場合は `python -m ragguard ...` で実行するか、利用しているPython環境の `Scripts` ディレクトリを `PATH` に追加してください。

## CLI実行例

```powershell
python -m ragguard check-mask --input "tests/fixtures/safe" --output "outputs/test_safe"
ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail" --verbose
```

`ragguard` コマンドが見つからない場合は、同じ処理を以下の形式で実行できます。

```powershell
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail" --verbose
```

YAML設定を追加で読み込む場合は、`--config` を指定します。

```powershell
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail_config" --config "config/rules.yaml"
```

`--config` 未指定時は内蔵ルールのみを使います。`--config` 指定時は `mode: extend_builtin` のみ対応し、内蔵ルールにYAML定義ルールを追加します。YAML不備、未対応mode、重複 `rule_id`、不正な正規表現などはCLIエラーとして終了コード `3` になります。

運用確認では、内蔵ルールのみの実行と `--config` 付き実行を分けて確認できます。

```powershell
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail_builtin"
python -m ragguard check-mask --input "tests/fixtures/fail" --output "outputs/test_fail_config" --config "config/rules.yaml"
```

どちらもFAIL検出時の終了コードは `2` です。configファイルには実資料、実案件名、実会社名、実個人名を入れないでください。

## CI

GitHub Actionsの `Tests` workflowで、`main` へのpushおよび `main` 向けpull requestごとに `python -m pytest` と `--config config/rules.yaml` 付きCLI実行を確認します。検出ルールやドキュメントを変更する場合も、PRではpytestとconfig付きCLI確認が通る状態を維持してください。

## 判定

- PASS: 機微情報らしき検出なし
- WARNING: 文脈確認が必要な語句のみ検出
- FAIL: メール、電話、住所らしき表現、金額、料率、契約条件、内部事情などを検出

終了コード:

- PASS: `0`
- WARNING: `1`
- FAIL: `2`
- CLIエラー: `3`

## 出力ファイル

指定した出力フォルダに以下を生成します。

- `masked_check_report.json`
- `masked_check_report.md`

`matched_text` は安全のためマスクされます。メールアドレス、電話番号、金額、住所、契約条件の具体文を長く再掲しない設計です。

## 注意

- 実資料をテストデータに使わないでください。
- `C:\AI_Restricted` を読ませないでください。
- `C:\AI_Local_RAG` 配下の実資料をMVPテスト対象にしないでください。
- 外部API、クラウドサービス、外部MCPは使わない方針です。
- config YAMLもローカルファイルとして扱い、実資料・実案件名・実会社名・実個人名を含めないでください。
- 入力ファイルは変更しません。自動修正も行いません。
