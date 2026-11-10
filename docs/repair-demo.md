# 修正とテスト実行の最小例（#21）

## 目的と呼び出し方

Agent SDKにRead・Editと反復を任せ、アプリが固定テストと完了判定を担当します。
任意のリポジトリを扱う機能や製品CLIではなく、毎回生成する小さな算術課題です。
既存のClient SDKによる生成・加算・ファイル調査はそのまま使えます。

[開発手順](development.md)で依存を導入し、`ANTHROPIC_API_KEY`を環境変数に設定します。
Agent SDKの依存にはClaude Code CLIが同梱され、別途のCLIインストールは不要です。
Python 3.15、POSIX/Linuxで確認しています。実行は有料APIを呼びます。

```bash
python -m coding_agent.repair_demo
# 同じ課題でモデルを切り替える場合（今回Sonnetは未検証）
LLM_MODEL=claude-sonnet-5-5 python -m coding_agent.repair_demo
```

既定モデルは`claude-haiku-5-5`です。空モデルは通信前に拒否します。
作成した一時ディレクトリは成功・失敗のいずれでも終了時に削除します。
成功時は修正前後のテスト状態とunified diffを表示します。

## 教材と処理の対応

2026-11-10に以下の公式本文と使用版`claude-agent-sdk 0.2.180`の公開APIを確認しました。
同梱CLIは`2.1.321`です。講座全体の読了やユーザーの理解を認定するものではありません。

- [Python SDK reference](https://platform.claude.com/docs/en/agent-sdk/python)：
  `ClaudeSDKClient`、`ClaudeAgentOptions`、`ResultMessage`、SDK MCP server。
- [Hooks](https://platform.claude.com/docs/en/agent-sdk/hooks)：
  全ツールの実行前に`PreToolUse`で引数を検査し、allow/denyを返す。
- [公式README](https://github.com/anthropics/claude-agent-sdk-python/blob/main/README.md)：
  組み込みRead・Edit、独自ツールの`@tool`と`create_sdk_mcp_server`。

教材の一般的なツール例を、次の小さな課題へ変更しています。

1. アプリが`calculator.py`と固定の`test_calculator.py`を新しい一時ディレクトリへ作る。
2. `add(a, b)`が誤って`a - b`を返すことを、アプリ側のテストで確認する。
3. モデルがReadで調べ、Editで関数を修正する。
4. モデルが専用の`run_tests`を呼び、実際の終了コードとテスト出力を受け取る。
5. SDKの正常終了に加え、変更・テスト不変・最終編集に対するテスト成功をアプリが確認する。
6. アプリでもう一度固定テストを実行し、成功した場合だけ差分を返す。

モデルの操作選択・履歴・反復はAgent SDKへ任せます。SDKの完了メッセージだけでは
課題達成を保証しないため、テストと差分による完了判定はアプリへ残します。
比較と選定理由は [ADR 0005](adr/0005-repair-demo-agent-sdk.md) を参照してください。

## 操作境界と初期値

| 項目 | 今回の範囲 |
| --- | --- |
| 作業場所 | アプリが新規生成する一時ディレクトリ。既存プロジェクトのパスは受け取らない |
| Read | `calculator.py`と`test_calculator.py`のみ。外部パス、`..`、リンクを拒否 |
| Edit | `calculator.py`の一意な文字列置換のみ。新規作成、テスト編集、全件置換を拒否 |
| 実行可能な修正 | `def add(a, b)`が`a + b`・`a - b`・`a * b`のいずれかを返すだけ。UTF-8で4096バイト以内 |
| 構文検査 | 実ファイルのバイト列からASTを作り、許可した3つの構文木と比較。import・呼出し・ループ・デコレーター・既定引数等は実行前に拒否 |
| `run_tests` | 引数なし。モデルから最大4回。実行直前にも関数の構文とテスト本文の不変を確認 |
| 固定テスト | 標準ライブラリunittestの4件（正数・異符号・ゼロ・負数）。モデルは変更不可 |
| テストプロセス | 現在のPythonで`-I -B test_calculator.py`を実行。shellなし、環境変数の引継ぎなし、5秒で打切り |
| SDK | `max_turns=8`、`max_budget_usd=0.25`、推論disabled。ターンはAPI要求回数と同一と仮定しない |
| SDKセッション | asyncioの120秒タイムアウト。前後の固定テストとSDKのキャンセル・終了処理に要する時間は別で、厳密な実時間上限ではない |

`max_turns`はPython引数で1〜20の整数だけを受け付け、boolは拒否します。
費用上限はSDKの停止しきい値で、最後の要求を含む請求額が必ずその値以下になる保証ではありません。

`tools=["Read", "Edit"]`で組み込みツール集合を限定し、独自のテストツールだけを追加します。
`allowed_tools`は空にし、全操作を`PreToolUse`で検査して許可します。
`allowed_tools`や`cwd`だけをファイル隔離と扱いません。
`setting_sources=[]`、`skills=[]`、`strict_mcp_config=True`で追加設定・スキル・外部MCPを
取り込まない構成にします。CLIの設定保存先も課題とは別の一時ディレクトリです。

今回の構文制約は汎用的なPythonサンドボックスではありません。限定した算術課題だけを
実行するための契約です。任意コードへ拡張するときは別途OSの隔離を設計する必要があります。
作業ディレクトリはアプリ所有で、外部プロセスが同時に編集しない前提です。

## 停止と検証の限界

範囲外操作は拒否し、同じSDKのターン上限内でモデルが修正できます。
テストツールの失敗は固定文言で返し、例外本文はモデルへ渡しません。
SDK異常終了、未実行・不一致のテスト、テスト改変、最終確認失敗は成功扱いにしません。
途中のモデル本文・SDKの結果本文をアプリから表示せず、mainの失敗表示も固定文言です。
独自の通信再試行や自動モデル切替は追加していません。

[オフラインテスト](../tests/test_repair_demo.py)はAPIキー・外部通信なしで、
許可範囲、禁止構文、実テスト、差分、未テスト・古いテスト・SDK異常終了の拒否、
実行回数、環境変数とタイムアウト、SDKへの接続設定を検証します。
模擬SDKのテストだけではCLIとの統合やモデルの修正能力を保証しません。
実モデルの確認結果・対象SHA・CIは対応するIssue/PRへ記録します。
この1課題の成功から、一般的なコード修正能力や説明の十分性は判断しません。
