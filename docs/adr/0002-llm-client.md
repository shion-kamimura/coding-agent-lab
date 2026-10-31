# ADR 0002: Haikuから始めるLLM Client

- 状態: 採用（設計確認済み。実装はレビュー対象）
- 日付: 2026-10-31
- 対応: [Issue #5](https://github.com/shion-kamimura/coding-agent-lab/issues/5)

## 目的と今回の範囲

Agent EngineeringとLLMOpsの学習のため、会話履歴から1回分の完成したテキストを
受け取る同期Clientを実装します。Tool Calling、ファイル操作、コマンド実行、
Agent Loop、CLI、非同期処理、ストリーミングは後続の実装単位へ分けます。

## プロバイダーとモデル

Anthropic公式Python SDKとMessages APIを使います。既定のモデルはHaiku 5.5
（`claude-haiku-5-5`）、上位モデルの比較先はSonnet 5.5（`claude-sonnet-5-5`）です。
モデルIDを設定で指定できるようにし、呼び出し側の処理を変えずに手動で切り替えます。
自動振り分けや自動フォールバック、複数プロバイダーの同時実装は行いません。

SDKはPython 3.15.2で確認する`anthropic>=2.3,<3`を使います。SDK 2.xが既定で送る
APIバージョンは2026-10-21で、`messages`中の`system`メッセージもそのまま変換します。
SDKが使うHTTPライブラリはHTTPX2で、テストからも直接使うため開発依存へ明記します。

HaikuはClient設計の学習と小さな課題の検証の出発点です。将来の自律的なコード修正まで
Haikuだけで十分とは判断していません。Agent Loopの段階で近いコード課題を10〜20件程度
用意し、Sonnetと成功率・成功1件あたりの総費用・時間・反復回数・手直し量を比較します。
モデルの能力とツールや履歴管理の問題の切り分けに使い、評価基盤は今回追加しません。

## 型と接続の境界

`llm.py`はSDKへ依存せず、`Message`、`TokenUsage`、`LLMResponse`、`LLMClient`のProtocol、
共通例外を定義します。SDKとの変換は`anthropic_client.py`へ分離します。
SDKの型をAgent Loopの境界に露出させず、将来のTool Callingで必要な型はその段階で拡張します。

設定は変更できない`AnthropicConfig`へまとめ、Clientへ渡します。環境変数や`.env`を
Clientが自動で読む仕組みは追加しません。APIキーはSDKの認証設定に任せます。
SDKの生成・認証・接続終了は呼び出し元が担当し、`with`文で管理するSDKを注入します。
Clientは`with_options`で通信設定を指定し、呼び出し元の設定を変更しません。

入力はsystem・user・assistantのテキストです。systemを除いた会話がuserで始まりuserで
終わることを検証し、assistantの応答の先頭を指定するprefillは今回扱いません。
入力と設定の不正は通信前に`ValueError`で通知します。

## 出力上限と推論

推論はadaptive、effortはmedium、出力上限は16,000トークンを既定にします。
effortと上限は設定で変更できます。モデルの最大出力や各設定の対応範囲はAPI側の制約です。

`max_tokens`は推論と回答本文を合わせた上限です。4,096を汎用の既定値とする根拠は
不十分と判断し、推論と本文の余裕を取る初期値として16,000を選びました。公式資料に
16,000の利用例はありますが、この用途に対する公式の一律推奨値でも実測した最適値でも
ありません。実APIで打ち切り率・使用量・品質・費用を計測し、必要に応じて調整します。
上限まで生成しなければ、その全量を課金されるわけではありません。

SDKの応答から返す本文はtextブロックの結合だけとし、thinking・redacted_thinkingは
本文に含めません。使用量は未キャッシュ入力、キャッシュ作成・読み取り、推論を含む
出力合計、取得できれば推論の内訳を保持します。推論を出力合計へ再加算しません。
任意のキャッシュ数が省略・nullの場合は0、推論内訳が取得できない場合はNone、
使用量全体が取得できない場合は`LLMResponse.usage`をNoneとします。

## 失敗と通信設定

- 通信タイムアウトは30秒、SDKだけで最大2回再試行（最初の要求を含め最大3回）。
  いずれも設定で変更できます。SDKの通常方針は接続失敗、408、409、429、5xxを対象とし、
  再試行を指示するサーバーヘッダーがある場合はSDKがそれに従います。
- 通信タイムアウトは通信操作ごとで、待機・再試行を含む全体の時間上限ではありません。
  長い非ストリーミング応答で30秒が適切かは未検証です。16,000トークンまでの生成完了を
  保証せず、実APIでの確認時に必要に応じて時間を調整します。全体の予算はAgent Loopで扱います。
- `end_turn`かつ空でないテキストだけを成功として返します。Tool Callingなどの
  未対応の内容は成功として返しません。
- `max_tokens`・`model_context_window_exceeded`は`LLMTruncatedResponseError`、
  APIの`refusal`は`LLMRefusalError`へ変換し、モデル名・終了理由・取得できた使用量を保持します。
  部分的な本文は返さず、自動再生成・自動継続・モデル変更も行いません。
- 認証・権限、レート制限、タイムアウト、接続失敗、その他のAPIエラーを共通例外へ変換します。
  空応答、未対応の終了理由、不正なレスポンスも`LLMResponseError`で通知します。
- 例外メッセージは固定し、SDK例外の本文や元の例外を通常のトレースバックへ表示しません。
  アプリケーションはAPIキー、入力、応答、推論をログへ記録しません。

## 検証と完了範囲

実際のAnthropic SDKと`httpx2.MockTransport`で要求・応答・エラーを検証します。
モデル選択、履歴、出力上限、推論設定、使用量の区分、拒否・打ち切り、通信失敗、
再試行の上限と回復、接続の所有と終了を確認します。
Ruff・format・mypy・pytestと、wheelのビルド・インストール後の検証を行います。

通常のテストはAPIキー・外部通信・API料金なしで実行します。
実APIでの有料疎通確認は今回の完了条件に含めず、認証・利用権限・回答品質・
タイムアウト・出力上限の実用上の適切さは未検証として報告します。

## 参照

- [Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python)
- [Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [Haiku 5.5](https://platform.claude.com/docs/en/models/haiku-5-5/overview)
- [Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)
- [推論と費用](https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost)
- [推論を使う例](https://platform.claude.com/docs/en/claude_api_primer)
- [終了理由](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)
