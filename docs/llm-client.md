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

## 小さなAgent Loop

[agent_loop.py](../src/coding_agent/agent_loop.py) は「17と25を足し、その結果に8を足して」を
固定入力とする手動ループです。既存の単発生成・ツール1往復の実行例も引き続き使えます。

```bash
python -m coding_agent.agent_loop
# 上限を変える場合（Pythonのキーワード引数。製品CLIではない）
python -c 'from coding_agent.agent_loop import main; main(max_steps=3)'
```

認証・モデル切替は上記と同じです。実行は有料APIを呼びます。通常テストは実APIを呼びません。
`max_steps`は正の整数（bool不可）で、既定は5です。2回のツール要求と最終回答の3回に
少し余裕を持たせた学習用初期値で、品質・費用を実測した最適値ではありません。
不正値と空のモデル名はClient生成前に拒否します。環境変数による上限設定はありません。

処理は次の順に進みます。

1. 元の依頼とこれまでの履歴を`messages.create()`へ渡す。
2. 各応答のステップ番号、モデル名、終了理由、Usageをstderrへ表示する。
3. `tool_use`なら、addがちょうど1件で整数2個だけを受け取ることを確認して実行する。
4. assistant応答全体と、同じIDを持つtool_resultを順に履歴へ追加し、次の要求へ進む。
5. `end_turn`でtool_useがなく、空でない本文があればstdoutへ表示して終了する。

各要求は`tool_choice={"type": "auto", "disable_parallel_tool_use": True}`です。
#14の最初の強制・最後の禁止を外し、モデルが次の操作を選びます。ツールを使わない最終回答も
許可します。モデルに2回のadd実行を強制せず、`end_turn`を課題の正解保証とは扱いません。
推論設定は既存のツール例と同じdisabled、出力上限は16,000、通信設定も同じです。

1ステップはモデル呼び出し1回です。SDK内部の通信再試行はステップに数えず、SDKだけに任せます。
最後のステップがツール要求なら、そのaddと履歴追加まで行い、次のAPI要求を送らず未完了で
失敗終了します。最終回答が上限ちょうどで返れば成功です。厳密な費用・実時間の予算ではありません。

不正な名前・引数・呼び出し数、ツール実行失敗、想定外の終了理由、空の最終本文、SDKエラーは
停止し、途中の本文を成功として表示しません。ツール例外の本文・推論本文・秘密情報を表示せず、
エラー結果をモデルへ返して修復させる処理もありません。履歴はメモリ内のみです。

教材との対応は、[公式チュートリアル](https://platform.claude.com/docs/en/agents-and-tools/tool-use/build-a-tool-using-agent)
の「ツール要求→実行→結果→次のモデル要求」の反復です。2026-11-10の再確認ではPlatformの
本文がプロキシの403で取得できませんでした。取得できた公式SDKの
[tools.py](https://github.com/anthropics/anthropic-sdk-python/blob/main/examples/tools.py) の
assistant全体・tool_use_idを引き継ぐ構造と、インストール済みanthropic 2.3.0の公開型を
根拠にしています。教材からの追加は、有限な上限、厳密な単一add検証、安全な失敗表示です。
通信・型・例外・再試行はSDK、操作選択はモデル、実行・履歴・継続と成功判定はアプリの責務です。

### Tool Runnerとの比較と検証範囲

[オフライン比較](../experiments/tool-runner.md) に導入方法、Betaの状態、使用版、確認結果をまとめました。
今回の実行例は、失敗時の即停止と安全な表示を短いコードで明示できる手動ループを採用します。
Runnerへ任せられる履歴・実行・反復は確認済みですが、同じ失敗制御には追加の制御が必要です。
以後も手動方式を固定せず、エラー修復や操作が増える時点で再評価します。

[手動ループのテスト](../tests/test_agent_loop.py) は実SDKとMockTransportで、42・50、全履歴とID、
直接回答、上限境界・不正値、不正要求、ツール失敗、異常終了、空本文、各段階の401/429と
追加要求の有無、安全な表示を確認します。SDKの接続終了も共通fixtureで確認します。
実モデルの認証・モデル対応・手順選択・課題達成・回答品質・費用・時間は未検証です。
モックの答え「50」は実モデルの計算能力や説明能力を保証しません。
次はエラー修復の必要性と、ファイル操作へ進む際のSDK・操作境界を判断します。
