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
```

期待される終了コードは、safeが `0`、warningが `1`、failが `2` です。WARNING / FAIL の `1` / `2` は検査結果として正常な終了コードです。
