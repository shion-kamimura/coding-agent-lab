# ADR 0007 — 公式Client SDKの手動ループに一本化する

- 状態: 採用（[#25](https://github.com/shion-kamimura/coding-agent-lab/issues/25)）
- 置換対象: [ADR 0006](0006-client-sdk-primary.md)

## 背景と決定

将来はClaude、GPT、DeepSeekなどのモデルAPIを設定で切り替えられる構成を目指す。
公式Client SDKを使い、認証・通信・各APIの入出力をSDKに委ねる。
操作の許可、会話履歴、反復上限、テスト失敗からの再修正、停止と成功判定は
アプリの手動ループで管理する。

APIを追加する際はツール要求と結果の形式差を各APIとの接続部分で扱う。
共通化の範囲は2つ目のAPIを追加する際に具体化する。各APIへの接続と切替設定は後続Issueで扱う。

## 代替案と影響

Agent SDKやTool Runnerを比較用に維持すると、履歴管理やツール実行をSDKへ委任する
構成を試せる。比較結果を記録したため、今後は手動ループの制御を保つことを優先し、
比較用のコードとテスト、Agent SDK依存を削除する。操作・停止・完了の制御と
その検証はアプリが維持する。比較時の観測は[実験の記録](../../experiments/README.md)に残す。
