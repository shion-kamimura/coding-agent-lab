# CIとマージ条件の設定

## CIの構成

[CIワークフロー](../.github/workflows/ci.yml) は、PR、mainへのpush、手動実行で起動します。
Python 3.15で次の5ジョブを並列に実行し、それぞれをPRのChecksに表示します。

| チェック名 | 検証内容 |
| --- | --- |
| `Lint` | `python -m ruff check .` |
| `Format` | `python -m ruff format --check .` |
| `Typecheck` | `python -m mypy` |
| `Tests` | editable installしたパッケージを `python -m pytest` で検証 |
| `Wheel` | wheelの作成、editable installの削除、wheelのインストール、pytestで再検証 |

共通の準備をmatrixで定義していますが、各ジョブは別のrunnerで実行します。
ジョブ間の依存はなく、`fail-fast: false` により1つの失敗で他のジョブを中止しません。
各ジョブで依存を準備するため、単一ジョブよりrunnerの合計利用時間は増える場合があります。
実行権限は `contents: read`、各ジョブの制限時間は10分です。

## main用ルールセットの設定手順

CIの起動条件はワークフロー、マージを許可する条件はGitHubのリポジトリ設定で管理します。
この文書やワークフローを追加するだけでは、ルールセットは有効になりません。
設定にはリポジトリの管理権限、またはルールを編集する権限が必要です。

1. このワークフローを含むPRでCIを実行し、Checksに上記5つが表示されることを確認します。
2. リポジトリの [Settings → Rules → Rulesets](https://github.com/shion-kamimura/coding-agent-lab/settings/rules) を開きます。
3. **New ruleset → New branch ruleset** を選び、名前を `Protect main` にします。
4. **Enforcement status** を **Active** にします。
5. **Bypass list** は空にします。管理者や開発用Appも通常のPR・CIを通す構成です。
6. **Target branches → Add target → Include by pattern** に `main` を指定します。
7. 次のルールを設定して **Create** を押します。

| 設定 | 推奨値 |
| --- | --- |
| Require a pull request before merging | 有効 |
| Required approvals | `0`（個人開発で他者の承認を必須にしない） |
| Require review from Code Owners / Require approval of the most recent reviewable push | 無効 |
| Require status checks to pass / before merging | 有効。下記5チェックを登録 |
| Require branches to be up to date before merging | 有効 |
| Restrict deletions | 有効 |
| Block force pushes | 有効 |

必須チェックには `Lint`、`Format`、`Typecheck`、`Tests`、`Wheel` を個別に追加します。
選択できる場合は送信元を **GitHub Actions** に指定します。
登録名は実際のChecksの表示と照合してください。ワークフロー名の `CI`、matrixのjob IDの
`checks`、旧ジョブ名の `Python 3.15` を代わりに登録しないでください。
候補が表示されない場合は、対象ワークフローを実行し、ページを開き直します。

**Restrict updates** は有効にしません。このルールは更新をbypass権限のある利用者に限定するため、
bypassを空にした今回の構成では通常のPRマージも妨げます。
署名・直線的な履歴・マージキューなどの追加ルールは、この手順では必須にしません。

既存のルールセットや従来のbranch protectionがある場合は、その条件も確認してください。
他の保護設定が追加のチェックや承認を要求していると、この設定だけでは条件を解除できません。

## 設定後の確認と保守

- PRのChecksに5つの結果が個別に表示され、必須チェックとして扱われることを確認します。
- CI実行中や失敗時はマージできず、全チェック成功かつmainに追従した状態でマージ可能になることを確認します。
- 他のPRがmainへ入って追従が必要になった場合は、作業ブランチへ最新mainを取り込み、再度CIを通します。
- 旧 `Python 3.15` が必須設定に残っている場合は、新しい5チェックへ置き換えます。
- チェック名を変更するときはルールセットも更新します。廃止したチェックを必須に残すとマージ待ちが解消しません。
- 必須チェックを起動するワークフローに安易なパスフィルターを付けないでください。起動しないPRでは必須チェックが待機状態になり得ます。

現行ワークフローはマージキューを使用しません。導入する場合は `merge_group` イベントでのCI起動も別途設計します。
CIの成功は自動マージを行う設定ではありません。マージ操作は別途行います。

## 公式資料

- [ルールセットの作成](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)
- [ルールの種類と必須ステータスチェック](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [必須チェックのトラブルシューティング](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/troubleshooting-rules/troubleshooting-required-status-checks)
