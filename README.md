# coding-agent-lab

Agent EngineeringとLLMOpsを学び、公式SDKで段階的に開発するコーディングエージェント。

## 現在の状態

Anthropic公式Python SDKを直接使う同期テキスト生成の実行例があります。
既定のHaikuから環境変数でSonnetへ手動で切り替えられます。エージェント本体とCLIは今後実装します。

## ドキュメント

- [開発を始める](docs/development.md)：環境構築、検証、PR・結果報告、中断再開
- [AIの作業入口](AGENTS.md)：目的、関連資料、共通の作業境界
- [学習の進め方](docs/learning.md)：公式資料を読む・実装する二段階の進め方、教材と学習順序
- [公式SDKでテキスト生成する](docs/llm-client.md)：実行方法、SDKの利用例、設定、使用量、エラー
- [設計と実装順序を知る](docs/architecture.md)：構成、責務、今後の実装範囲
- [技術選定の理由を読む](docs/adr/)：設計判断とその背景
- [比較実験を確認する](experiments/README.md)：実験の記録と再現方法

## ライセンス

[MIT License](LICENSE)
