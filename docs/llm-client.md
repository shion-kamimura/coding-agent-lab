# 公式SDKでテキスト生成する

独自のClient・メッセージ・応答・例外変換を介さず、Anthropic公式Python SDKの
`Anthropic`と`messages.create()`を直接使います。現在の実装は、固定の質問へ1回回答する
[学習用実行例](../src/coding_agent/llm.py) です。製品CLIやAgent Loopではありません。

## 実行方法

[開発手順](development.md#2-必要な環境を準備する) に従ってインストールします。
通常テストにAPIキーは不要です。実行例は実APIを呼び、API利用料が発生します。

`ANTHROPIC_API_KEY`を環境変数として設定してから実行してください。
秘密情報はコミットせず、[.env.example](../.env.example) は説明用に使います。
`.env`を作成するだけでは読み込まれません。

```bash
python -m coding_agent.llm
# 同じ実行例からSonnetを使う場合（Bash）
LLM_MODEL=claude-sonnet-5-5 python -m coding_agent.llm
```

`LLM_MODEL`はこの実行例が読む変数で、SDK自体の設定変数ではありません。
省略時は`claude-haiku-5-5`です。空文字・空白のみは通信前に失敗終了します。
回答本文を標準出力へ、モデル名・終了理由・SDKの使用量を標準エラー出力へ表示します。

## 公式資料と実装の対応

[Claude Platform 101](https://academy.claude.com/courses/claude-platform-101) の最初の3レッスンを
読み、[Python SDKのUsage](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python#usage)
と実行例を対応づけます。2026-11-01に公式本文を確認しました。
講座の最初のAPI例はTypeScriptですが、本リポジトリはPythonを使います。

```python
from anthropic import Anthropic

with Anthropic(timeout=30.0, max_retries=2) as client:
    response = client.messages.create(
        model="claude-haiku-5-5",
        max_tokens=16_000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": "PythonのProtocolを短く説明して"}],
        stream=False,
    )
```

これは実行例のAPI呼出し部分です。認証、通信、型、再試行、接続終了はSDKの公開APIを使います。
教材の最小例に、既存の推論・通信設定と、終了理由の判定・安全なエラー表示を加えています。

`response`はSDKの`anthropic.types.Message`です。`content`は本文だけの文字列ではなく
ブロックの列で、実行例では`text`ブロックを順に結合します。推論ブロックは本文に含めません。
会話履歴もSDKの`messages`へuser・assistantなどの辞書を渡し、独自の`Message`へ変換しません。
複数ターンの履歴管理は後続の教材で実装します。

## 設定と使用量

実行例は次の値をSDKへ直接渡します。通信・出力設定を変える場合はSDKの引数を変更します。
独自の設定クラスや、自動モデル選択はありません。

| SDK引数 | 値 | 意味 |
| --- | --- | --- |
| `model` | 環境変数または`claude-haiku-5-5` | 使用するモデルID |
| `max_tokens` | `16000` | 推論と回答本文を合わせた1要求の出力上限 |
| `thinking` / `output_config` | adaptive / medium | 推論・応答の設定 |
| `timeout` | `30.0` | 通信操作ごとのタイムアウト（秒） |
| `max_retries` | `2` | SDKの再試行回数。最初の要求を含め最大3回 |

出力上限とタイムアウトは#6の初期値を維持しており、実測した最適値ではありません。
上限まで生成しなければ、その全量が課金されるわけではありません。
30秒は待機・再試行を含む全体の時間上限ではなく、16,000トークンまでの生成完了を保証しません。
必要ならSDKの引数を調整します。全体の実行予算は後続の課題です。

使用量はSDKの`response.usage`をそのまま扱います。入力・出力、キャッシュ、取得できれば
推論の内訳をSDKのフィールドで確認します。推論は出力合計に含まれるため再加算しません。
実行例はSDKのUsageを表示するだけで、独自の使用量型・集計・料金計算は持ちません。

## 終了理由とエラー

HTTP通信の成功と、完成した回答の取得は別です。実行例は`response.stop_reason`が
`end_turn`で、空でないテキストがある場合だけ本文を表示します。
打ち切り（`max_tokens`・`model_context_window_exceeded`）、拒否（`refusal`）、
未対応のTool Callingなどでは、モデル名・終了理由・使用量を表示して失敗終了します。
部分的な本文は表示せず、自動継続・自動再生成・モデル変更は行いません。

再試行はSDKへ任せ、アプリ側では繰り返しません。ライブラリとしてSDKを呼ぶ際は、
`anthropic.AuthenticationError`、`RateLimitError`、`APITimeoutError`などを必要に応じて
直接扱います。この実行例では`AnthropicError`を捕捉して型名だけを表示し、失敗終了します。
SDKの例外本文・入力・推論・APIキーをエラーログへ表示しないための判断です。

[終了理由](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons) と
[Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python) を2026-11-01に確認しました。

## #6からの移行と検証範囲

`AnthropicClient`、`AnthropicConfig`、`LLMClient`、独自の`Message`・`LLMResponse`・`TokenUsage`・
`LLMError`系は削除しました。既存の呼び出しはSDKの公開API・型・例外へ移行してください。
互換ラッパーは提供しません。理由は [ADR 0003](adr/0003-sdk-first-learning.md) にあります。

オフラインテストは実際のSDKと模擬HTTP通信で、モデル選択、送信設定、本文と推論の分離、
使用量の表示、打ち切り・拒否・空本文での失敗、安全なエラー表示、SDKだけによる再試行、
接続終了を検証します。SDK内部の型・例外変換を再実装するテストは削除しました。
実APIの認証・モデル利用権限・回答品質、実応答での上限・時間設定の適切さは未検証です。
