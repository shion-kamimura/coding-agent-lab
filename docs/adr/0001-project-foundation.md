# ADR 0001: Pythonプロジェクトの基盤

- 状態: 提案（初期化PRのレビュー対象）
- 日付: 2026-10-31

## 前提

Python、CLI、pytest、GitHub Actionsを使い、初期はAgent Frameworkを使わずに
Agent Loopの内部構造を学ぶ方針を引き継ぎます。既存のMITライセンスを維持します。

## 今回の選定

| 選定 | 理由と影響 |
| --- | --- |
| Python 3.12以上 | 基準バージョンを明確にする。3.11以前は対象外。CIは3.12、3.13、3.14を検証する |
| `venv` + `pip` | Python標準の手順から始める。uvやPoetryの導入を必須にしない |
| setuptools + `pyproject.toml` | 標準的なビルド・依存・ツール設定を一か所に置く |
| `src/coding_agent` | インストールしたパッケージをテストし、作業ディレクトリからの偶然のimportを避ける |
| Ruff | lint、import整列、formatをまとめる。E/F/I/UP/Bを有効にする |
| mypy strict | 新規コードから型の境界を明確にする。必要な例外は後続PRで理由を残す |
| pytest | APIに依存しないテストを基本とする |
| GitHub Actions | PRとmainへのpushで品質チェックとwheelのインストール検証を行う |

ランタイム依存はありません。開発依存はpyproject内のバージョン範囲で管理し、
現段階ではロックファイルを導入しません。そのため解決される依存の厳密な再現性は
保証しません。実験の再現性が必要となる段階で、uv等とロック方針を別ADRで検討します。
Actionsは確認済みのコミットSHAへ固定し、実行権限はcontentsの読み取りに限定します。

## 保留する選定

LLMプロバイダー、モデル、SDK、CLIライブラリ、実行隔離、トレース基盤は未選定です。
学習の目的と比較実験に必要な要件を確認してから、それぞれのIssueで決めます。

## 参照

- [Ruff設定](https://docs.astral.sh/ruff/configuration/)
- [mypy設定](https://mypy.readthedocs.io/en/stable/config_file.html)
- [pytest設定](https://docs.pytest.org/en/stable/reference/customize.html)
- [setup-python](https://github.com/actions/setup-python)
- [checkout](https://github.com/actions/checkout)
