# Usage

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
