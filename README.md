# coding-agent-lab

Agent EngineeringとLLMOpsを学び、探究するためにゼロから開発するコーディングエージェント。

## 現在の状態

Claude Messages APIによる同期テキスト生成Clientを実装済みです。
既定のHaikuから設定でSonnetへ手動で切り替えられます。エージェント本体とCLIは今後実装します。

## ドキュメント

- [開発を始める](docs/development.md)：環境構築、検証、PR・結果報告、中断再開
- [AIの作業入口](AGENTS.md)：目的、関連資料、共通の作業境界
- [学習の進め方](docs/learning.md)：実装を説明できるための進め方、到達目標、関連資料
- [LLM Clientを使う](docs/llm-client.md)：APIの利用例、設定、使用量、エラー
- [設計と実装順序を知る](docs/architecture.md)：構成、責務、今後の実装範囲
- [技術選定の理由を読む](docs/adr/)：設計判断とその背景
- [比較実験を確認する](experiments/README.md)：実験の記録と再現方法

## ライセンス

[MIT License](LICENSE)
