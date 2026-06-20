# import-skill-check (データインポート関数)

この Cloud Run Function (第2世代) は、Google Cloud Storage (GCS) にアップロードされたスキルチェック結果の Excel ファイル (`.xlsx`) を検知し、自動的にデータを抽出・前処理して BigQuery の `raw_data.skill_check_results` テーブルへ上書きロード (WRITE_TRUNCATE) するイベント駆動型サーバーレス関数です。

---

## 1. 役割とトリガー仕様

- **トリガー元**: Google Cloud Storage バケット (`raw-skill-check-bucket-[suffix]`)
- **トリガーイベント**: オブジェクト作成・更新イベント (`google.cloud.storage.object.v1.finalized`)
- **関数の役割**:
  1. GCS 上の Excel ファイルからデータを読み込み。
  2. カラム名のスネークケース化、ユーザーIDの欠損チェック、およびスコアや評価ラベルの正規化・マッピング前処理。
  3. BigQuery への上書きロード（WRITE_TRUNCATE）処理（冪等性の担保）。

---

## 2. 入力 Excel スキーマ仕様

アップロードする Excel ファイルの第1シートは、以下のカラムを含んでいる必要があります（大文字小文字やスペースは前処理で自動的にスネークケース化されます）。

| 元のカラム名例 | 前処理後カラム名 | データ型 | 説明 |
| :--- | :--- | :--- | :--- |
| `User ID` | `user_id` | `STRING` | 登録者のユニークID（空欄・None・"nan" は行全体が除外されます） |
| `App Engine` | `app_engine` | `INTEGER` | App Engine の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Cloud Run` | `cloud_run` | `INTEGER` | Cloud Run の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Google Kubernetes Engine` | `google_kubernetes_engine` | `INTEGER` | Google Kubernetes Engine の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Cloud Storage` | `cloud_storage` | `INTEGER` | Cloud Storage の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Workflows` | `workflows` | `INTEGER` | Workflows の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `BigQuery` | `bigquery` | `INTEGER` | BigQuery の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Cloud SQL` | `cloud_sql` | `INTEGER` | Cloud SQL の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Cloud Spanner` | `cloud_spanner` | `INTEGER` | Cloud Spanner の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Firestore` | `firestore` | `INTEGER` | Firestore の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `AlloyDB` | `alloydb` | `INTEGER` | AlloyDB の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Bigtable` | `bigtable` | `INTEGER` | Bigtable の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `VPC Service Controls` | `vpc_service_controls` | `INTEGER` | VPC Service Controls の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Secure Command Center` | `secure_command_center` | `INTEGER` | Secure Command Center の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Cloud Pub/Sub` | `cloud_pubsub` | `INTEGER` | Cloud Pub/Sub の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |
| `Gemini Enterprise Agent Platform` | `gemini_enterprise_agent_platform` | `INTEGER` | Gemini Enterprise Agent Platform の実務能力評価（3 / 2 / 1）。※後述のルールで 1/0 にマッピング。 |

※サンプルファイルが [samples/sample_skill_check.xlsx](../../samples/sample_skill_check.xlsx) に配置されています。



---

## 3. 実務レベル評価の2値化マッピングルール

本システムは2値分類モデル（BQML）を用いて「実務能力レベル（1/0）」を予測するため、Excel上の各インフラ・サービス評価値（3 / 2 / 1）を以下のルールで `1` または `0` に変換して BigQuery にロードします。

- **`3`（実務レベルである）** ➔ **`1`** (実務レベル)
- **`2`（実務レベルの可能性がある）** ➔ **`1`** (実務レベル)
- **`1`（実務レベルでない）** ➔ **`0`** (非実務レベル)
- **欠損値 (空欄) / 不正な数値 (例: 99)** ➔ **`0`** (非実務レベル)

> [!NOTE]
> 正解データが約5,000人と比較的限られているため、グレーゾーン（2）や不正値を含む行を除外してデータ量を減らすのではなく、**実務レベルである可能性（2以上）を正例（1）とし、それ以外（1や欠損値など）を負例（0）**として学習データに含める設計にしています。


---

## 4. 冪等性（Idempotency）の担保

本関数は何度実行してもデータベースの状態が破壊されず、同一のデータに収束するように設計されています。
- **`WRITE_TRUNCATE` による上書きロード**: BigQuery の `raw_data.skill_check_results` テーブルに対して、データフレームの内容を `WRITE_TRUNCATE`（上書き）モードで直接ロードします。これにより、同じ Excel ファイルから複数回インポートを実行しても、最終的なテーブル状態は常に同一になり、冪等性が担保されます。

---

## 5. ローカル開発とテスト

本プロジェクトはパッケージ管理に `uv` を使用しています。

### パッケージのインストールと同期
```bash
uv sync
```

### 単体テストの実行
モック（Mock）を使用した pytest による単体テストを同梱しています。以下のコマンドで実行できます。
```bash
uv run pytest test_main.py
```
テストコード (`test_main.py`) は以下を検証します：
- カラム名正規化ロジックの動作確認
- 有効なデータの変換（3, 2 ➔ 1 / 1, None ➔ 0）
- 外れ値スコア（120点など）が除外されず `0` 点に補正されること
- `user_id` が欠損しているレコードのみが正しく削除されること
- CSV などの非 Excel ファイルがアップロードされた際に早期リターンすること
