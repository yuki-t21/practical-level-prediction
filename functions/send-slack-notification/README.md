# send-slack-notification (Slack通知送信リモート関数)

この Cloud Run Function (第2世代) は、BigQuery リモート関数 (Remote Function) からの HTTP リクエストを受け取り、Secret Manager に保存された Slack Incoming Webhook URL を使用して Slack へメッセージを送信します。
BigQuery SQL のクエリ実行中に、結果行に応じた Slack 通知を動的かつバッチで安全に送信可能です。

---

## 1. 動作仕様

### リクエストフォーマット (BigQuery ➔ Function)
BigQuery はリモート関数を実行する際、処理対象のデータをバッチングして以下の JSON 構造で HTTP POST リクエストを送信します。

```json
{
  "requestId": "124ac-356d-e46g",
  "caller": "//bigquery.googleapis.com/projects/my-project/jobs/job_id",
  "userDefinedContext": {},
  "calls": [
    ["#alert-channel", "Alert: Prediction pipeline completed successfully."],
    ["#alert-channel", "Alert: User ID '10234' prediction score is 0.95."]
  ]
}
```

*   `calls`: 送信したいデータの多次元配列。本関数の引数設計（`channel`, `text`）に対応して、各要素は `[チャンネル名, メッセージ内容]` の順で配置されます。

### レスポンスフォーマット (Function ➔ BigQuery)
関数は `calls` の要素に対応する処理ステータスを格納した JSON を返却します。

#### 正常系レスポンス
```json
{
  "replies": [
    "success",
    "success"
  ]
}
```

*   `replies`: `calls` のインデックス順に一致した送信結果を文字列で格納します。送信成功時は `"success"`、何らかの理由で送信失敗した行（引数不足や Slack API エラーなど）は `"error: <エラー詳細>"` になります。

#### 異常系レスポンス (全体エラー)
トークンの取得失敗やリクエスト構文の不備など、処理自体が途中で崩壊した場合は以下のフォーマットを HTTP ステータス 400 または 500 で返却します。

```json
{
  "errorMessage": "Configuration error: SLACK_TOKEN_SECRET_NAME environment variable is not set."
}
```

---

## 2. Slack 側の準備 (Incoming Webhook)

本機能を利用するには、メッセージ送信先の Slack ワークスペースで **Incoming Webhooks** を作成し、Webhook URL を取得する必要があります。

1. Slack App の設定画面（または Slack のカスタムインテグレーション画面）に移動します。
2. **Incoming Webhooks** を有効化します。
3. 送信先のデフォルトチャンネルを選択し、**Webhook URL**（`https://hooks.slack.com/services/...`）を発行します。

---

## 3. Secret Manager での Webhook URL 管理

取得した Webhook URL は、GCP の Secret Manager を用いて安全に保管します。

### シークレット作成コマンド例
```bash
# シークレットの作成
gcloud secrets create SLACK_API_TOKEN \
  --replication-policy="automatic"

# Webhook URL 値の追加
echo -n "https://hooks.slack.com/services/T.../B.../X..." | \
  gcloud secrets versions add SLACK_API_TOKEN --data-file=-
```

---

## 4. BigQuery からの呼び出し例 (SQL)

リモート関数 `send_slack` を使用し、SQL の条件分岐（例: 実務レベル判定確率が 90% 以上の高評価ユーザー）に基づいて Slack 通知を送信するクエリの具体例です。

```sql
SELECT
  user_id,
  probability,
  -- 実務レベル判定確率が 0.90 以上のユーザーのときのみ Slack に通知を送信
  CASE
    WHEN probability >= 0.90 THEN
      ml_models.send_slack(
        '#predictions-alert',
        CONCAT('💡 高実務レベル候補検出: ユーザー ', user_id, ' (確率: ', ROUND(probability * 100, 1), '%)')
      )
    ELSE
      'skipped'
  END AS notification_status
FROM
  `ml_models.evaluation_1`
```

---

## 5. ローカル開発と検証

### 開発環境のセットアップ
```bash
uv sync
```

### ユニットテストの実行
```bash
uv run pytest
```

### 品質管理ツールの実行
```bash
# フォーマット
uv run black .

# リンター
uv run flake8 .

# 型チェック
uv run mypy .

# インポート順
uv run isort .

# 複雑度チェック
uv run radon cc . -e "test_*.py" -s -a
```
