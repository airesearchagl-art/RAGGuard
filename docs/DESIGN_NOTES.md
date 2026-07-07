# Design Notes

## MVPの検出方針

Masked Document Checkerは、Markdown内の行を対象に正規表現とキーワードで検出します。誤検知を一定許容し、見逃しを減らす安全側の判定を優先します。

## 限界

正規表現ベースのため、文脈理解は限定的です。たとえば「契約」は単語単体ではWARNINGですが、「契約条件」「違約金」などはFAILとして扱います。

フルネーム推定は誤検知が多いため、MVPでは「担当者名: ...」のような明示ラベル付き表現のみWARNINGに留めます。

## 非破壊方針

入力ファイルは変更しません。自動修正、削除、移動、上書きは行いません。レポートは指定された出力フォルダにのみ作成します。

## 外部依存

MVPは標準ライブラリのみで動作します。外部API、クラウドサービス、外部MCPは使いません。

## Masked Document Checker v0.2 設定ファイル仕様案

v0.2では、`--config config/rules.yaml` によるルール読込を検討します。現行MVPでは `config/*.yaml` はサンプル扱いで、ランタイムでは読み込みません。

### 読込方針

config未指定時は、これまでどおり内蔵ルールのみを使用します。config指定時は、MVP v0.2では `mode: extend_builtin` を採用し、内蔵ルールにユーザー定義ルールを追加する方針とします。

内蔵ルールの完全置き換えは誤設定時の見逃しリスクが高いため、v0.2では採用しません。将来必要になった場合のみ、`mode: replace_builtin` のような明示モードとして検討します。

### ルール構造

`rules` 配下の各要素は、以下のキーを持つ想定です。

- `rule_id`: ルールの一意なID
- `category`: findingの分類
- `severity`: `WARNING` または `FAIL`
- `type`: `regex` または `keyword`
- `pattern`: `type: regex` の正規表現
- `keywords`: `type: keyword` の文字列配列
- `recommendation`: レポートに出す短い推奨対応
- `redaction`: `matched_text` の伏せ字方法

`category` は当面、以下の候補に寄せます。

- `personal_info`
- `money`
- `contract`
- `internal`
- `name_candidate`
- `address_candidate`

### regex / keyword の違い

`type: regex` はメールアドレス、電話番号、金額、料率など、形式で判定しやすい表現に使います。`pattern` はPython `re` 互換を前提にします。

`type: keyword` は「予算」「契約」「未公表」など、単語や短い語句の出現を検出します。`keywords` の各要素を安全側に検出し、文脈判断が必要なものは `WARNING` に留めます。

### 設定不備時の扱い

設定ファイル不備、未知の `severity`、未知の `type`、必須キー不足、正規表現コンパイル失敗はCLIエラーとし、exit code `3` で終了する方針です。

v0.2では `mode` は `extend_builtin` のみを許容します。それ以外の値、または未指定はCLIエラー exit code `3` とします。

`rule_id` が重複した場合は、内蔵ルールとの重複、ユーザー定義ルール同士の重複のどちらもCLIエラー exit code `3` とします。既存ルールの暗黙上書きは行いません。

`redaction` の許容値は `partial`、`label`、`keyword` とします。未知の値はCLIエラー exit code `3` とし、マスク方針が曖昧なルールは実行しません。

エラーメッセージには、設定ファイルのパス、`rule_id`、不足キー、原因の種類のみを含めます。入力Markdown内の機微情報や、検出対象文字列をエラーに再掲しません。

### レポート互換性

既存のJSON / Markdownレポート構造は維持します。`findings` の `file`、`line`、`category`、`severity`、`rule_id`、`matched_text`、`recommendation` は引き続き出力します。

ユーザー定義ルールを追加しても、既存利用者が `masked_check_report.json` と `masked_check_report.md` を読み続けられることを優先します。

### セキュリティ方針

`matched_text` は引き続き伏せ字化します。入力ファイルは変更せず、自動修正、削除、移動、上書きは行いません。

外部API、クラウドサービス、外部MCPは使いません。fixtureやサンプル設定には実資料、実案件名、実会社名、実個人名を使いません。
