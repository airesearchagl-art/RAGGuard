# Usage

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
