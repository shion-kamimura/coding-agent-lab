# Tool Runnerのオフライン比較

2026-11-10、Python 3.15.2 / anthropic 2.3.0で確認。
目的は、単一addの反復において履歴・実行・停止をRunnerへ任せられる範囲の確認です。
仮説は「正常系の手動履歴は省けるが、アプリの成功・失敗方針までは一致しない」です。

## 導入・再現方法

既存の`anthropic>=2.3,<3`で使え、今回の環境では追加依存のインストールは不要でした。
公開APIは`anthropic.beta_tool`と`client.beta.messages.tool_runner()`で、Betaの入口です。
安定版APIと同じ互換性を仮定せず、更新時は比較を再実行します。Agent SDKとは別です。

[実行可能な小例](../tests/test_tool_runner_comparison.py) は、`@beta_tool`で整数2つを受けて
文字列を返すaddを定義し、以下の設定でRunnerを反復します。

```python
runner = client.beta.messages.tool_runner(
    model="claude-haiku-5-5",
    max_tokens=16_000,
    thinking={"type": "disabled"},
    messages=[{"role": "user", "content": "17と25を足し、その結果に8を足して"}],
    tools=[add],
    tool_choice={"type": "auto", "disable_parallel_tool_use": True},
    max_iterations=3,
    stream=False,
    thread=False,
)
for response in runner:
    # アプリで終了理由・本文を検査する必要がある。
    pass
```

`thread=False`で毎回全履歴を送る方式に揃えます。SDK 2.3.0の公開docstringでは、既定は
message threadで差分送信です。threadの実サーバー挙動は未検証です。

```bash
.venv/bin/python -m pytest tests/test_tool_runner_comparison.py -q
```

実モデルの代わりにMockTransportから2回のadd要求と最終本文を返します。
APIキー・外部通信・API料金なし。モデルIDは要求設定であり、実モデルは実行しません。

## 確認結果

| 項目 | 手動ループ | Runner 2.3.0 | 根拠 |
| --- | --- | --- | --- |
| 履歴・ID | assistant全体と結果をアプリが追加 | Runnerが追加 | 両方式の模擬要求で全履歴・ID・順序を確認 |
| 実行 | 単一addを検証して実行 | beta_toolを呼び結果へ変換 | 17+25→42、42+8→50を両方式で確認 |
| 上限 | 正のmax_steps、既定5。未完了は失敗終了 | max_iterationsで要求数を制限。既定は無制限 | 2回で要求停止し、最後はtool_useのまま返ることを確認。既定値はSDKコード確認のみ |
| 上限時の実行 | 最後のaddは実行、次の要求なし | 同様に最後のaddは実行、次の要求なし | 実行履歴と要求数を確認 |
| ツール例外 | 本文を隠し即停止 | is_error付き結果に例外本文を含め、次の要求へ進む | 合成ValueErrorを使い送信結果と継続を確認 |
| 終了の意味 | end_turn・空でない本文・ツールなしだけ成功 | max_tokensでも通常の反復終了 | max_tokensを1応答で返し、例外なしで終了することを確認 |
| 制御の入口 | 分岐を直接書く | 反復中の検査、generate_tool_call_response・append_messages等 | 公開docstring確認のみ。厳密な同条件への適応は未実装 |

RunnerのSDKコードには一般例外のログ出力とエラー結果変換があります。比較テストでは機密を
含まない合成例外だけを使用します。Runnerをそのまま本実行例へ置換すると、今回の
「例外本文を表示・送信しない」「不正要求や実行失敗で即停止」と一致しません。
またデコレーターの引数変換と手動の厳密な整数検査が同じとは仮定しません。
未知ツール・複数呼び出し・全ての不正引数・SDKエラーについてRunnerとの同条件試験は未実施です。

履歴・実行・反復の委任には利点がありますが、この小さな学習単位では手動ループを採用します。
Runnerの失敗制御を調整した本番実装や、2方式の恒久的な提供は今回の対象外です。
この結論は局所的な実行例の選択で、長期構成を固定するADRの追加は行いません。

## 出典と限界

- [Tool Runner公式資料](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner)：今回の本文再取得はプロキシ403で不可。
- [公式SDKのRunner](https://github.com/anthropics/anthropic-sdk-python/blob/v2.3.0/src/anthropic/lib/tools/_beta_runner.py)：インストール済み2.3.0の同ファイルで反復・上限・例外処理を確認。
- [公開API](https://github.com/anthropics/anthropic-sdk-python/blob/v2.3.0/src/anthropic/resources/beta/messages/messages.py)：tool_runnerの引数・threadのdocstringを確認。
- [関数ツール](https://github.com/anthropics/anthropic-sdk-python/blob/v2.3.0/src/anthropic/lib/tools/_beta_functions.py)：beta_toolの公開引数と入力検証を確認。

実APIの認証・モデル対応・手順選択・課題達成・費用・時間、Betaの将来の互換性は未検証です。
模擬応答による制御検証を、実モデルでの有用性・正解率の実証とは扱いません。
