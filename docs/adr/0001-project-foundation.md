# ADR 0001: Pythonプロジェクトの基盤

- 状態: 提案（初期化PRのレビュー対象）
- 日付: 2026-10-31

## 前提

以下の初期方針のうち、自作を学習の前提とする部分は2026-11-01の
[ADR 0003](0003-sdk-first-learning.md) で見直しました。Python・開発基盤の選定は維持します。

Python、CLI、pytest、GitHub Actionsを使い、初期はAgent Frameworkを使わずに
Agent Loopの内部構造を学ぶ方針を引き継ぎます。既存のMITライセンスを維持します。

## 今回の選定

| 選定 | 理由と影響 |
| --- | --- |
| Python 3.15以上 | 開発には3.15の最新パッチ版を使い、CIも3.15を検証する。3.14以前は対象外 |
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

## Python 3.15を基準にする理由

2026-10-31時点の最新安定系列である3.15を基準にします。新規の学習用プロジェクトで、
古いPythonを利用する既存ユーザーやランタイム依存がないため、3.12〜3.14への
互換性維持を現段階の要件にしません。3.15の機能を学習・実験に利用できるよう、
Ruffとmypyの対象バージョンも3.15に揃えます。

開発依存の下限はRuff 0.17、mypy 2.4、pytest 9.2に引き上げます。
今後導入するLLM SDK等は3.15上で検証し、具体的な互換性問題が見つかった場合に
3.14への対応を別の判断として検討します。`requires-python`は最低対応版の宣言であり、
将来のPython系列での動作確認を意味しません。対応を公表する前にCIへ追加します。

## 保留する選定

LLMプロバイダー、モデル、SDK、CLIライブラリ、実行隔離、トレース基盤は未選定です。
学習の目的と比較実験に必要な要件を確認してから、それぞれのIssueで決めます。

## 参照

- [Ruff設定](https://docs.astral.sh/ruff/configuration/)
- [mypy設定](https://mypy.readthedocs.io/en/stable/config_file.html)
- [pytest設定](https://docs.pytest.org/en/stable/reference/customize.html)
- [setup-python](https://github.com/actions/setup-python)
- [checkout](https://github.com/actions/checkout)

- [Python 3.15.2](https://www.python.org/downloads/release/python-3152/)
- [Python 3.15のリリース・サポート計画](https://peps.python.org/pep-0790/)
- [mypyの3.15対応](https://mypy.readthedocs.io/en/stable/changelog.html)
