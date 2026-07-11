# RAGGuard Roadmap

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
