# coding-agent-lab
Agent EngineeringとLLMOpsを学び、探究するためにゼロから開発するコーディングエージェント。

## 現在の状態

Pythonパッケージと開発環境に加え、Claude Messages APIによる同期の
テキスト生成Clientを実装しています。既定のモデルはHaikuで、設定でSonnetへ
手動で切り替えられます。エージェント本体とCLIは今後実装します。
開発・テストにはAPIキーの設定や有料API呼び出しは不要です。

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
GitHub ActionsではLint・Format・Typecheck・Tests・Wheelを独立したジョブで実行します。
Wheelではwheelを作成し、editable installを置き換えて再テストします。
CI成功をマージ条件にするには、別途 [ルールセットの設定](docs/ci.md) が必要です。

## LLM Client

`LLMClient`は`Message`の履歴を受け取り、テキスト、モデル名、トークン使用量を
`LLMResponse`として返します。Claudeの具体的な実装は`AnthropicClient`です。
メッセージは`system`・`user`・`assistant`のテキストを扱い、`system`を除いた
会話は`user`で始まり`user`で終わる履歴を受け取ります。
未完了の応答、APIが示す拒否、空のテキストは成功として扱いません。
Tool Calling、ストリーミング、自動モデル切り替えは今回の対象外です。

テストでは`httpx2.MockTransport`がAPIの応答と通信エラーを再現します。
実際のSDKを通して変換や再試行を検証しますが、外部通信や課金は発生しません。
モデルの回答品質や実際のAPIへの接続は、このテストでは検証できません。

### 実際のAPIを利用する例

以下は実行するとAPI利用料が発生します。利用権限のある`ANTHROPIC_API_KEY`を
環境変数として設定してください。今回の検証にはこの実APIの疎通確認を含めません。
`.env`を作るだけでは読み込まれません。SDKの接続は呼び出し元で閉じます。

```python
import os

from anthropic import Anthropic

from coding_agent.anthropic_client import (
    DEFAULT_MODEL,
    AnthropicClient,
    AnthropicConfig,
)
from coding_agent.llm import Message

config = AnthropicConfig(model=os.environ.get("LLM_MODEL", DEFAULT_MODEL))
with Anthropic() as sdk:
    client = AnthropicClient(sdk, config=config)
    response = client.complete([Message("user", "PythonのProtocolを短く説明して")])
    print(response.text)
    print(response.usage)
```

`LLM_MODEL`を`claude-sonnet-5-5`へ変更すると、同じコードでSonnetを呼び出せます。
この変数は上の例が読み取るもので、Clientが環境変数を自動で読み込む仕組みはありません。
コードからは`AnthropicConfig(model="claude-sonnet-5-5")`でも指定できます。

### 設定と実行予算

`AnthropicConfig`は変更できない設定オブジェクトで、次の値を持ちます。

| 設定 | 既定値 | 意味 |
| --- | --- | --- |
| `model` | `claude-haiku-5-5` | 使用するモデルID |
| `max_output_tokens` | `16000` | 推論と回答本文を合わせた1要求の出力上限 |
| `effort` | `medium` | 推論・応答の強度。`low`・`medium`・`high`・`xhigh`・`max` |
| `timeout_seconds` | `30.0` | 通信操作ごとのタイムアウト（秒） |
| `max_retries` | `2` | SDKで行う再試行回数。最初の要求を含め最大3回 |

推論は`adaptive`で、モデルが必要な推論量を判断します。返す本文には推論ブロックを
含めません。出力上限は実測した最適値ではなく、推論と本文の余裕を確保する初期値です。
上限まで生成しなければ、その全量が課金されるわけではありません。

再試行はSDKだけに任せ、二重に行いません。SDKの通常方針は接続失敗、408、409、429、
5xxを対象とし、サーバーから再試行指示がある場合はそれに従います。
打ち切りや拒否、空応答を受けて自動で再生成・継続・モデル変更はしません。

タイムアウトは待機や再試行を含む全体の時間上限ではありません。
長い非ストリーミング応答では30秒が不足する可能性があるため、必要に応じて
`AnthropicConfig(timeout_seconds=120.0)`のように変更してください。
16,000トークンまでの生成完了を保証する設定ではなく、適切な時間は実APIで未検証です。
全体の実行時間・費用の予算管理は、後続のAgent Loopで扱います。

`TokenUsage`は未キャッシュの`input_tokens`、キャッシュ作成・読み取りの入力数、
推論を含む`output_tokens`を保持します。`total_input_tokens`は3種類の入力の合計です。
`thinking_tokens`は出力の内訳で、出力合計へ再加算しません。取得できなければ`None`、
使用量全体が取得できなければ`response.usage`が`None`になります。

### エラーの扱い

APIの失敗は`LLMError`の派生例外へ変換します。認証・権限、レート制限、
タイムアウト、接続失敗、その他のAPIエラー、利用できない応答を区別します。
例外メッセージにSDKのレスポンス本文は含めません。
入力や設定が不正な場合は通信前に`ValueError`を送出します。

上限到達は`LLMTruncatedResponseError`、APIが示す拒否は`LLMRefusalError`です。
どちらも`LLMResponseError`を継承し、本文を返さず、取得できた`model`・`stop_reason`・
`usage`を保持します。打ち切りを通常の通信失敗と区別して、使用量や発生率を調べられます。

## 構成

```text
src/coding_agent/       LLM Clientの型とAnthropic実装
tests/                 インストール・LLM Clientのオフライン検証
docs/architecture.md   今後のアーキテクチャと実装順序
docs/adr/              技術選定と理由
experiments/           今後の比較実験
.github/               CI・Issue・PRテンプレート
pyproject.toml         パッケージ・開発依存・品質チェック設定
```

## 開発方針

小さなIssueごとに実装・検証し、PRで設計理由を説明します。
初期はAgent Frameworkを使わず、LLM Client、File Tools、Agent Loop、CLIの順で進めます。
技術選定は [ADR 0001](docs/adr/0001-project-foundation.md) と
[ADR 0002](docs/adr/0002-llm-client.md)、
詳細は [設計資料](docs/architecture.md) を参照してください。

開発依存はバージョン範囲で管理しており、ロックファイルはまだ導入していません。
APIキーなどの秘密情報はコミットしないでください。`.env.example`は説明用で、
`.env`の自動読み込みは未実装です。

## ライセンス

[MIT License](LICENSE)
