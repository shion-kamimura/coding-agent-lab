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
単一ツール往復の履歴は下記の実行例で扱います。任意回数の会話管理は未実装です。

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


## addツールを1回実行する（#14）

[tool_use.py](../src/coding_agent/tool_use.py) は「17と25を足して」という固定入力に対し、
Pythonの `add` を1回実行し、その結果を返して最終回答を表示します。
既存の `python -m coding_agent.llm` も引き続き使えます。
APIキーの設定と料金の注意は上記の実行方法と同じです。

```bash
python -m coding_agent.tool_use
LLM_MODEL=claude-sonnet-5-5 python -m coding_agent.tool_use
```

### 教材と処理の対応

2026-11-10に公式Python SDKの
[tools.py](https://github.com/anthropics/anthropic-sdk-python/blob/main/examples/tools.py)
本文と、使用版 `anthropic 2.3.0` の公開型を確認しました。
[Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) と
[公式チュートリアル](https://platform.claude.com/docs/en/agents-and-tools/tool-use/build-a-tool-using-agent)
も関連資料です。ただし今回の環境では公式ドキュメントサイトへの接続が403となり、
その本文を再確認できていません。講座の全レッスンを確認したものではありません。

| 公式例の処理 | 今回の実装 |
| --- | --- |
| `tools` に名前・説明・入力スキーマを渡す | `ADD_TOOL` で整数2つを受け取る `add` を定義 |
| `stop_reason` と `tool_use` を調べる | 終了理由と呼び出し数1つを確認し、名前と引数も検証 |
| assistant応答を履歴へ追加する | `response.content` 全体を保持し、前置きの本文も落とさない |
| userの `tool_result` に同じIDを設定する | Pythonで加算した値を文字列化し、`call.id` とともに返す |
| 履歴を含む2回目の要求を送る | `end_turn` かつ空でない本文を確認し、最終回答のみ表示 |

モデルは実行したいツール名・引数を生成します。Pythonの関数を実行するのはアプリです。
SDKは通信・公開型・通信再試行を担当し、アプリは引数検証・加算・履歴・停止条件を担当します。
公式例の天気ツールと固定の結果を、副作用のない加算関数へ変更しています。

### 強制選択と制約

最初の要求では `tool_choice={"type": "tool", "name": "add",
"disable_parallel_tool_use": True}` を指定します。自動選択より再現性を優先し、
ツールを使わずに答える場合や並列呼び出しを今回の学習範囲から外すためです。
2回目は `tool_choice={"type": "none"}` で追加のツール要求を許可しません。
これらの引数は使用版SDKの `ToolChoiceToolParam`・`ToolChoiceNoneParam` に対応します。

既存のテキスト生成例のadaptive推論設定は継承せず、両要求で
`thinking={"type": "disabled"}` とします。強制ツール選択との組み合わせを単純にし、
推論設定の比較を今回の範囲へ混ぜないためです。`output_config` は指定しません。
モデル選択・出力上限・通信設定・SDKの再試行回数は既存例と同じです。
両応答のモデル名・終了理由・使用量を標準エラーへ表示します。使用量は要求ごとの値です。

引数はキーが `a`・`b` だけの整数2つに限り、bool・小数・文字列・欠落・余分なキーを
拒否します。未定義ツール、呼び出し数0または複数、想定外の終了理由、空の最終回答、
追加の `tool_use` は失敗終了し、部分回答は標準出力に表示しません。
エラーメッセージに引数や応答本文を含めず、SDK例外は型名のみを表示します。
独自再試行、エラーをモデルへ返す修復、任意回数のAgent Loop、Tool Runnerは未実装です。

### 検証と限界

[test_tool_use.py](../tests/test_tool_use.py) は実SDKと `httpx2.MockTransport` を使い、
2要求の設定、`add(17, 25)` の実行、42の返却、assistant応答の保持、IDの一致、
最終出力・メタデータ、不正入力・不正応答の停止、両段階でのSDKエラーの安全な表示と
SDK以外で再試行しないこと、空モデルの通信前停止を検証します。外部通信・APIキーは不要です。

モックの最終本文はテストが用意した値であり、実モデルの計算結果の説明能力を保証しません。
実APIの認証・モデル対応・強制ツール選択と推論設定の組み合わせ・回答品質・料金・速度は
未検証です。実API検証は別途行います。
