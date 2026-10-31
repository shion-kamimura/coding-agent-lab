# coding-agent-lab
Agent EngineeringとLLMOpsを学び、探究するためにゼロから開発するコーディングエージェント。

## 現在の状態

Pythonパッケージと開発環境を初期化した段階です。
エージェント本体、CLI、LLM API連携は今後実装します。
この段階ではAPIキーの設定や有料API呼び出しは不要です。

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
GitHub Actionsでも同じチェックを行い、wheelを作成してインストール後に再テストします。

## 構成

```text
src/coding_agent/       Pythonパッケージ（現在は骨組み）
tests/                 パッケージのインストール検証
docs/architecture.md   今後のアーキテクチャと実装順序
docs/adr/              技術選定と理由
experiments/           今後の比較実験
.github/               CI・Issue・PRテンプレート
pyproject.toml         パッケージ・開発依存・品質チェック設定
```

## 開発方針

小さなIssueごとに実装・検証し、PRで設計理由を説明します。
初期はAgent Frameworkを使わず、LLM Client、File Tools、Agent Loop、CLIの順で進めます。
技術選定は [ADR 0001](docs/adr/0001-project-foundation.md)、
詳細は [設計資料](docs/architecture.md) を参照してください。

開発依存はバージョン範囲で管理しており、ロックファイルはまだ導入していません。
APIキーなどの秘密情報はコミットしないでください。`.env.example`は説明用で、
`.env`の自動読み込みは未実装です。

## ライセンス

[MIT License](LICENSE)
