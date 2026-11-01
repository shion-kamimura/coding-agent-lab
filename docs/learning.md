# 学習の進め方

Agent EngineeringとLLMOpsを学び、実装の仕組みと設計理由を理解するため、
「公式資料を読む → それに沿って実装する」の二段階を基本にします。
自作する量を学習の深さの基準にせず、公式SDKを使う前提で進めます。
開発・検証・PRの手順は [開発手順](development.md)、共通の境界は
[AGENTS.md](../AGENTS.md) に従います。製品のエージェントへの指示や権限設定ではありません。

## 一つの学習単位

1. **公式資料を読む。** 対象の講座・レッスン・ドキュメントと、今回扱う範囲を示します。
   必要なら日本語で要点を補足し、入出力、処理の流れ、SDKとアプリの責任を説明します。
   資料がカバーする範囲と、プロジェクト固有で補う範囲を区別します。
2. **資料に沿って実装する。** AIが小さな実装を作り、教材の説明とコードの対応、
   教材から変えた点と理由を示します。実行・テストで動作を確かめ、検証できたことと
   未検証事項を報告します。実装済みの機能も、公式例と照合して振り返れます。

質問による理解確認、クイズ、ユーザー自身による説明の提出は標準手順にしません。
補足や理解確認はユーザーが希望した場合に行います。教材にクイズが含まれていても、
本プロジェクトの作業を進める条件にはしません。資料を提示しただけで読了とせず、
AIがコードを作ったことやテストが通ったことだけでユーザーの理解を認定しません。

## SDKを使う方針

- Anthropic公式Client SDKの公開API・型・例外を直接使います。複数プロバイダー向けの
  共通Client・共通型・例外変換を先回りして追加しません。必要になった場合に理由を示します。
- ツールの中身、アプリ固有の分岐・停止・予算・権限は、その課題で必要な範囲を実装します。
  グラフのノードや分岐の設計と、SDKの入出力を独自の型へ変換することは別の判断です。
- Agent Loopは公式例の小さな実装で仕組みを確認し、Tool Runnerへ置き換える教材を使えます。
  自作ループの継続を前提にせず、必要な制御とTool Runnerの対応範囲を照合します。
- コーディングエージェントの組み込み機能が必要ならClaude Agent SDKも比較します。
  現在採用しているClient SDKとAgent SDKは別の製品で、Agent SDKへの移行は未実施です。
- SDKの信頼性と、変更の影響がないことは同義ではありません。バージョン範囲、公開仕様、
  Betaの状態を確認し、プロジェクト側の動作を検証します。

## 主教材と学習順序

以下は2026-11-01に確認した教材です。講座の目次・概要と、Platform 101の最初のAPI呼出し・
Agent Loopなどの主要レッスン本文・コード例、SDKの関連資料を確認しました。
全動画・全レッスンを通した検証は未実施です。所要時間は講座側の表示で、実装時間を含みません。

| 順序 | 読む公式資料 | 対応する実装・学習範囲 |
| --- | --- | --- |
| 1 | [Claude Platform 101](https://academy.claude.com/courses/claude-platform-101)（13レッスン・約1.5時間）の最初の3レッスン | API呼出し、応答の読み方、モデル選択。現在の [実行例](../src/coding_agent/llm.py) と照合する |
| 2 | 同講座のThe agent loop explained・What is tool use? と [ツール利用チュートリアル](https://platform.claude.com/docs/en/agents-and-tools/tool-use/build-a-tool-using-agent) | 単一ツールの往復から小さなループへ進み、公式 [Tool Runner](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner) への置換を試す |
| 3 | Platform 101のWhat is thinking?・Context management | 推論設定、使用量、履歴とコンテキスト管理。現在の設定値の適切さは実測で補う |
| 4 | [Building with the Claude API](https://academy.claude.com/courses/building-with-the-claude-api)（67レッスン・約9時間）の必要な章 | 会話管理、評価、Tool Calling、ルーティング・連鎖・並列化。RAG・MCPは必要になった段階で扱う |
| 5 | [Tool use with the Messages API](https://academy.claude.com/courses/tool-use-with-the-messages-api)（9レッスン・約1.5時間） | 基本のTool Callingが動いた後、入力の厳密化、並列実行、ストリーミング、費用改善を適用する |
| 必要時 | [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview) | ファイル操作・コマンド実行・セッション・権限などの組み込み機能を使う構成と比較する |

Platform 101はPython中心ですが、最初のAPI呼出しなど一部にTypeScriptを使います。
本リポジトリではPython SDKの現行仕様に照合して実装します。Tool use with the Messages APIは
最初のツール往復を教える講座ではなく、基本実装後の改善が対象です。

公式教材でAPI・ツール・履歴・ループ・評価の基本を学べます。一方、このプロジェクト固有の
ファイル操作制約、実行環境、評価課題と判定基準、実際の費用・品質・速度は、自分の要件と
実験で補います。PythonやOSの詳細は各公式資料を使います。

## 仕様の確認と補助教材

具体的なAPI・SDKの仕様は [Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python)
と [Messages API](https://platform.claude.com/docs/en/api/messages/create) を正本として、
[pyproject.toml](../pyproject.toml) のバージョン範囲と実際の使用版に照合します。
説明には出典URLと確認日を添え、本文未確認・接続不可・実験未実施を確認済みと書きません。
講座のサンプルと現行仕様が違う場合は、変更点と理由を示します。

技術ブログは設計上の疑問が出たときの補助教材とします。以下は2026-10-31に公式ページを
確認した出発点です。最新の探索には [Engineering一覧](https://www.anthropic.com/engineering)
を使い、新しさと今回の課題への有用性を分けて判断します。

| 学習対象 | 補助資料 |
| --- | --- |
| 構成とツール設計 | [Building effective agents](https://www.anthropic.com/research/building-effective-agents)、[Writing effective tools for agents](https://www.anthropic.com/research/writing-tools-for-agents) |
| 履歴と評価 | [Effective context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents)、[Demystifying evals](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) |
| 実行の制約 | [Claude Code sandboxing](https://www.anthropic.com/research/claude-code-sandboxing) |
| 長い作業と設計の見直し | [Effective harnesses](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents)、[Harness design](https://www.anthropic.com/research/harness-design-long-running-apps) |

記事の設計例やモデル依存の結果を、そのまま普遍的な推奨にしません。

## 現在地と記録先

2026-11-01時点で、公式Client SDKを直接使う同期テキスト生成の実行例があります。
Tool Calling、File Tools、Agent Loop、製品CLIは未実装です。#6の振り返りは最初の教材を読み、
公式SDKの要求・応答・終了理由を [実行例と利用ガイド](llm-client.md) に対応づけます。
方針変更は [ADR 0003](adr/0003-sdk-first-learning.md)、実装順序は
[アーキテクチャ](architecture.md) にあります。

課題ごとに使った教材と実装の対応、検証結果、疑問、次の作業は対応するIssue/PRへ残します。
書き込めない場合は回答に記載します。技術的な選択はADR、比較実験は
[experiments](../experiments/README.md) に置きます。この文書に進捗を複製したり、
専用の進捗管理ファイルを増やしたりしません。
