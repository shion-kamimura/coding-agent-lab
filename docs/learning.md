# 学習の進め方

Agent EngineeringとLLMOpsを学び、ユーザーが実装の仕組みと設計理由を説明できる状態を
目指します。開発を支援するAIは、以下を設計・実装や理解の支援に適用します。
開発の手順・検証・PR・引き継ぎは [開発手順](development.md)、共通の境界は
[AGENTS.md](../AGENTS.md) に従います。この文書は学習支援と教材の正本であり、
製品のCoding Agentへのプロンプトや実行権限を定めるものではありません。

## 一つの実装課題の進め方

1. **目的と到達目標を決める。** 今回解決する問題と、ユーザーが説明できるようにする
   内容を絞ります。実装済みの機能は、既存コード・テスト・ADRから振り返れます。
2. **関連資料を確認する。** 公式ドキュメント・技術記事の該当箇所を読み、今回の設計に
   どう関係するかを示します。全資料の通読は前提にせず、必要な箇所から進めます。
3. **実装前に仕組みを説明する。** 入出力、処理の流れ、モジュールごとの責任、
   採用する方法と代替案、失敗時の扱いを説明します。図や具体例は必要に応じて使います。
4. **小さく実装して確かめる。** 一度に扱う責務や判断を絞り、期待する結果を検証します。
   比較実験が必要なら、仮説、変える条件、観測する結果を決めてから実行します。
5. **説明を更新する。** 実装前の想定と結果の違い、採用理由、未検証事項をまとめます。
   理解を確かめる問いを一、二点に絞り、ユーザーが自分の言葉で説明する機会を設けます。
   回答があれば、曖昧な点や誤解を具体例で補います。

理解確認は、ユーザーの希望や作業の大きさに合わせて行います。毎回の承認待ちや
クイズ合格を作業の条件にせず、実装を依頼された場合は許可された範囲を進めます。
ユーザーが理解確認のための停止を求めた場合は、その進め方を優先します。
回答がない場合は理解を未確認として扱い、実装の完了と学習の到達を区別します。
調査・文書修正・軽微な修正では、変更に関わる学習上の判断を必要な範囲で説明します。

## 説明できることの目安

コードの構文や処理を追うだけでなく、次の五点を自分の言葉で説明できることを目安にします。

| 観点 | 説明する内容 |
| --- | --- |
| 目的 | 何を解決し、何を今回の対象外にしたか |
| 流れ | 具体的な入力がどう処理され、どの出力や状態変更につながるか |
| 責任 | モデル、LLM Client、Agent Loop、ツールがそれぞれ何を判断・実行するか |
| 選択理由 | 他の方法と比べてなぜ選び、どんな費用・複雑さ・制約を引き受けたか |
| 根拠と限界 | 何をどう検証し、どの条件や挙動がまだ分かっていないか |

例えばAgent Loopでは、ツール要求を返すモデル、引数・権限を検証して実行するアプリ、
結果を履歴へ追加する処理、停止条件の役割を、一つのファイル読取の例で説明します。
正常な処理に加え、ツールの失敗や反復上限に達した場合も説明の対象にします。
この例は後続実装の学習目標であり、現在のLLM ClientがTool Calling対応済みという意味ではありません。

## 資料の選び方と更新

- 公式資料を優先し、設計原則は技術記事、具体的なAPI・SDKの仕様は現行ドキュメントで
  確認します。記事の実験条件やモデル依存の結果を、そのまま普遍的な推奨にしません。
- API・SDK・モデルなど変わりやすい仕様を判断するときは、その時点の公式資料と
  リポジトリが使うバージョンを照合します。最新記事も探し、既存の説明を補う内容や
  前提の変化がないか確認します。新しさと今回の課題への有用性を分けて判断します。
- 説明や判断には出典のURLと確認日を添え、事実、資料からの推測、このプロジェクトの
  選択を区別します。本文未確認・接続不可・実験未実施を確認済みとは書きません。
- ドキュメントは契約や制約、技術記事は設計の考え方を学ぶ材料です。自分の用途での
  品質・費用・速度は実験で確かめます。Pythonのファイル操作やプロセス管理などは
  Python・OS・使用ライブラリの公式資料も補います。

以下は2026-10-31に公式ページを確認した出発点です。API・SDKの仕様を将来にわたり
固定する一覧ではありません。公式講座は一覧・概要までの確認で、全レッスンは未確認です。

| 学習対象 | 資料 | 今回のプロジェクトで考える問い |
| --- | --- | --- |
| 基礎と全体像 | [Building effective agents](https://www.anthropic.com/research/building-effective-agents) | なぜ初期はFrameworkを使わず、小さな構成から始めるか |
| APIの基礎 | [Claude Academy](https://academy.claude.com/collections/build-with-claude) のClaude Platform 101・Building with the Claude API | APIの契約とアプリ側の責任をどう分けるか |
| Tool Calling | [How tool use works](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works) と [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls) | 誰がツールを実行し、結果をどう次の呼び出しへ渡すか |
| File Tools | [Writing effective tools for agents](https://www.anthropic.com/research/writing-tools-for-agents) | 名前・引数・説明・返す情報をどう設計するか |
| 履歴と情報取得 | [Effective context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents) | 必要な情報をどう取得し、履歴を残すか |
| 評価と改善 | [Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) | 成功をどう定義し、実行過程と最終成果をどう確かめるか |
| 実行の制約 | [Claude Code sandboxing](https://www.anthropic.com/research/claude-code-sandboxing) | モデルへの指示と実行環境による制約はどう違うか |
| 長い作業の継続 | [Effective harnesses for long-running agents](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) | 次のセッションへ何を残す必要があるか |
| 発展と設計の見直し | [Harness design for long-running application development](https://www.anthropic.com/research/harness-design-long-running-apps) | 評価役の分離はいつ有用か。モデルの進歩で不要になった仕組みをどう見つけるか |

2024年の基礎記事にはツール事情の変化について注記があります。長時間エージェントの
2025年の記事は、2026年3月24日の発展記事と合わせて読むと設計の変化を比較できます。
新しい記事の探索には [公式Engineering一覧](https://www.anthropic.com/engineering) を使います。

## 現在地と記録先

2026-10-31時点では、同期テキスト生成のLLM Clientまで実装済みで、Tool Calling、
File Tools、Agent Loop、CLIは未実装です。まず既存Clientの入出力、SDKとの境界、
再試行・打ち切り・拒否の扱い、オフラインテストの範囲を説明できるか振り返れます。
実装順序の正本は [アーキテクチャ](architecture.md)、既存Clientの判断は
[ADR 0002](adr/0002-llm-client.md)、利用方法は [LLM Client](llm-client.md) にあります。

技術的な選択と理由はADR、比較実験は [experiments](../experiments/README.md)、
課題ごとの到達目標・理解確認・疑問・検証結果・次の作業は対応するIssue/PRへ残します。
Issue/PRへ書き込めない場合は回答に記載します。ユーザーの回答や実際の検証に基づく
記録と、AIが説明・提案しただけの内容を区別し、理解済みや学習効果を推測で記録しません。
この文書へ課題ごとの進捗を複製したり、専用の進捗管理ファイルを増やしたりしません。
