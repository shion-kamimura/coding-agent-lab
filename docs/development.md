# 開発ガイド

## 開発の進め方

小さなIssueごとに実装・検証し、PRで設計理由を説明します。
着手時にIssueの目的・範囲・完了条件とGitの状態を確認し、変更後は差分と検証結果を確認してPRに記載します。

## 開発環境の準備

Python 3.15の最新パッチ版を開発に使用します。最低対応バージョンは3.15で、
CIも3.15を検証します。Python 3.14以前はサポート対象外です。

```bash
git clone https://github.com/shion-kamimura/coding-agent-lab.git
cd coding-agent-lab
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Windowsでは、インストールした対応版のPythonで `py -3.15 -m venv .venv` を実行し、
PowerShellで `.venv\Scripts\Activate.ps1` を使って有効化してください。

## 品質チェック

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest
```

自動整形は `python -m ruff format .`、修正可能なlintの適用は
`python -m ruff check --fix .` で行えます。変更内容を確認してコミットしてください。

CIの構成とマージ条件は [CIとマージ条件の設定](ci.md) を参照してください。

通常テストはAPIキー・外部通信・API料金なしで実行します。
実際のAPIへの接続やモデルの回答品質は、通常テストでは検証できません。

## APIキーと環境変数

APIキーなどの秘密情報はコミットしないでください。
[環境変数の例](../.env.example) は説明用で、`.env`の自動読み込みは未実装です。
実APIを利用するときは環境変数として設定してください。
API利用料が発生する呼び出しの例と設定方法は [LLM Clientの利用ガイド](llm-client.md) にまとめています。

開発環境や依存管理の選定理由は [ADR 0001](adr/0001-project-foundation.md) を参照してください。

## 文書の配置と更新

READMEへ追加する基準は「初めて訪れた人が、プロジェクトを理解して次へ進むために必要か」です。
READMEには短い説明とリンクを載せ、詳細は次の文書へ集約します。同じ手順を複数の文書に重複させないでください。

| 内容 | 配置先 |
| --- | --- |
| 概要、現在の状態、ドキュメントへの案内、ライセンス | [README](../README.md) |
| 環境構築、品質チェック、開発の進め方、秘密情報の扱い | この開発ガイド |
| LLM Clientの利用例、設定、使用量、エラー | [LLM Client](llm-client.md) |
| ディレクトリ構成、モジュールの責務、実装順序 | [アーキテクチャ](architecture.md) |
| 技術選定の理由、依存管理・ロックファイルの判断 | [ADR](adr/) |
| 実験の記録方法、評価結果、再現手順 | [実験の記録](../experiments/README.md) と各実験の記録 |
| CIジョブ、ルールセットの設定 | [CIとマージ条件の設定](ci.md) |
| 作業の計画・進捗、受け入れ確認、検証結果 | 対応するIssue・PR |

変更に合わせて関連文書を更新し、移動や分割を行うときは参照元のリンクも確認します。
文書のみの変更では、内容・リンク・差分の整合性を確認し、影響に応じて必要な検証を選びます。
CLIが利用可能になった段階で、READMEへの最小の利用例の追加を検討します。
