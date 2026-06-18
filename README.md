# practical-level-prediction

エンジニアの **実務レベル予測モデル** — Google Cloud 上で動作する、スキルチェック結果・資格・GitHub 実績・技術ブログ実績・職務経歴をもとに BigQuery ML で実務レベルを予測するエンドツーエンドの機械学習パイプラインです。

---

## システム概要

```
[スキルチェック Excel]
        │
        ▼ GCS (raw-skill-check-bucket)
  import-skill-check (Cloud Run Function)
        │
        ▼ BigQuery: raw_data
  skill_check_results / service_master
        │
        ├─ Dataform: common_features_pipeline
        │     level_weights → service_mapping → common_features
        │
        └─ Dataform: service_features_pipeline (サービスID毎)
              service_features → engineer_features
              → train_model (BQML: BOOSTED_TREE_CLASSIFIER)
              → evaluate_model
              → explain_predictions (ML.EXPLAIN_PREDICT + SHAP)

[推論対象ユーザー CSV (targets_{id}.csv)]
        │
        ▼ GCS (target-user-list-bucket)
  export-prediction (Cloud Run Function)
        │
        ▼ GCS (prediction-results-bucket)
  predictions_{name}_{timestamp}.xlsx
```

---

## ディレクトリ構成

```
practical-level-prediction/
├── README.md                   # 本ファイル
├── AGENTS.md                   # リポジトリ全体の開発ルール
├── .github/
│   ├── pull_request_template.md
│   └── workflows/
│       └── deploy.yaml         # CI/CD: Lint・テスト・Terraform デプロイ
├── workflow_settings.yaml      # Dataform 設定ファイル
├── definitions/                # Dataform 定義 (特徴量エンジニアリング・BQML)
│   ├── AGENTS.md               # Dataform 開発ルール
│   ├── README.md               # Dataform 概要・仕様
│   ├── sources/            # ソーステーブル宣言 (type: declaration)
│   ├── tests/              # ユニットテスト定義
│   ├── common_features.sqlx
│   ├── service_mapping.sqlx
│   ├── engineer_features.sqlx
│   ├── train_model.sqlx
│   ├── evaluate_model.sqlx
│   └── explain_predictions.sqlx
├── functions/                  # Cloud Run Functions (第2世代)
│   ├── AGENTS.md
│   ├── README.md
│   ├── import-skill-check/     # Excel → BigQuery インポーター
│   └── export-prediction/      # BigQuery ML バッチ推論 → Excel エクスポーター
├── terraform/                  # インフラ管理 (IaC)
│   ├── AGENTS.md
│   ├── README.md
│   ├── main.tf
│   ├── providers.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── gcs.tf
│   ├── bigquery.tf
│   ├── functions.tf
│   ├── dataform.tf
│   └── iam.tf
└── samples/                    # 動作確認用サンプルデータ
    ├── README.md
    ├── sample_skill_check.xlsx  # import-skill-check 検証用 Excel
    └── targets_1.csv            # export-prediction 検証用 CSV
```

---

## 事前に有効化が必要な Google Cloud API

Terraform によるインフラ構築および各パイプラインの実行前に、以下の API を対象プロジェクトで有効化してください。

```bash
gcloud services enable \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  eventarc.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  bigquerymigration.googleapis.com \
  bigqueryconnection.googleapis.com \
  aiplatform.googleapis.com \
  dataform.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  pubsub.googleapis.com \
  artifactregistry.googleapis.com \
  --project=<your-project-id>
```

| API | 用途 |
| :--- | :--- |
| `cloudfunctions.googleapis.com` | Cloud Run Functions (第2世代) の管理 |
| `cloudbuild.googleapis.com` | 関数ビルド時に内部で使用 |
| `run.googleapis.com` | Cloud Run Functions の実行基盤 |
| `eventarc.googleapis.com` | GCS トリガー (Eventarc) |
| `storage.googleapis.com` | GCS バケットの操作 |
| `bigquery.googleapis.com` | BigQuery データセット・テーブル・ジョブ |
| `bigquerymigration.googleapis.com` | Dataform が内部で使用 |
| `bigqueryconnection.googleapis.com` | BigQuery 外部接続 (AI.GENERATE_EMBEDDING 用) |
| `aiplatform.googleapis.com` | Vertex AI (Gemini Embedding モデル) |
| `dataform.googleapis.com` | Dataform リポジトリ・ワークフロー |
| `iam.googleapis.com` | サービスアカウント・IAM バインディング |
| `iamcredentials.googleapis.com` | Workload Identity Federation |
| `cloudresourcemanager.googleapis.com` | プロジェクト情報の参照 (Terraform) |
| `pubsub.googleapis.com` | Eventarc の内部メッセージング |
| `artifactregistry.googleapis.com` | 関数コンテナイメージの保存 |

---

## セットアップ手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/yuki-t21/practical-level-prediction.git
cd practical-level-prediction
```

### 2. Terraform によるインフラ構築

```bash
cd terraform

# 初期化 (tfstate 保存先バケットを指定)
terraform init -backend-config="bucket=terraform-state-<your-project-id>"

# 実行計画の確認
terraform plan -var="project_id=<your-project-id>"

# 適用
terraform apply -var="project_id=<your-project-id>"
```

`terraform apply` が完了すると、GCS バケット名や関数 URI などが出力されます。

### 3. Dataform の設定

`workflow_settings.yaml` の `defaultProject` を実際のプロジェクト ID に変更してください。

```yaml
defaultProject: your-actual-project-id
```

Dataform CLI のローカル認証設定:

```bash
npx @dataform/cli init-creds
```

### 4. スキルチェックデータのインポート

```bash
# サンプルデータを GCS にアップロード (バケット名は terraform output で確認)
gcloud storage cp samples/sample_skill_check.xlsx \
  gs://$(terraform -chdir=terraform output -raw raw_skill_check_bucket_name)/
```

アップロードすると `import-skill-check` 関数が自動実行され、BigQuery の `raw_data` データセットに以下のテーブルが作成されます。

- `raw_data.skill_check_results`
- `raw_data.service_master`

### 5. Dataform パイプラインの実行

```bash
# ステップ 1: 共通特徴量パイプライン (全サービス共通)
npx @dataform/cli run --tags common_features_pipeline

# ステップ 2: サービス固有パイプライン (サービス ID を指定)
npx @dataform/cli run --tags service_features_pipeline --vars service_id=1
```

### 6. 予測の実行

```bash
# 推論対象ユーザーリスト CSV をアップロード
gcloud storage cp samples/targets_1.csv \
  gs://$(terraform -chdir=terraform output -raw target_user_list_bucket_name)/
```

アップロードすると `export-prediction` 関数が自動実行され、予測結果 Excel が出力バケットに保存されます。

---

## CI/CD (GitHub Actions)

`main` ブランチへの Push 時に自動デプロイが実行されます。Pull Request 時は Lint・テストのみ実行されます。

### ワークフロー: `.github/workflows/deploy.yaml`

| ジョブ | トリガー | 内容 |
| :--- | :--- | :--- |
| `validate` | PR・Push | 関数の Lint (black/flake8/mypy/isort/radon)・pytest、Terraform fmt/validate、cSpell、SQLFluff、Dataform コンパイル |
| `deploy` | `main` への Push のみ | Terraform apply による GCP リソースの自動デプロイ |

### 必要な GitHub Secrets

| シークレット名 | 説明 |
| :--- | :--- |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Workload Identity プロバイダーのリソース名 (`terraform output workload_identity_provider` で取得) |
| `GCP_SERVICE_ACCOUNT` | デプロイ用 SA のメールアドレス (`terraform output github_deployer_service_account_email` で取得) |
| `GCP_PROJECT_ID` | Google Cloud プロジェクト ID |

---

## ローカル開発

### 関数のテスト

```bash
# import-skill-check
cd functions/import-skill-check
uv sync --group dev
uv run pytest

# export-prediction
cd functions/export-prediction
uv sync --group dev
uv run pytest
```

### Dataform のコンパイル・テスト

```bash
npx @dataform/cli compile
npx @dataform/cli test
```

### Terraform の検証

```bash
cd terraform
terraform fmt -check
terraform validate
terraform plan -var="project_id=<your-project-id>"
```

---

## 各ディレクトリの詳細ドキュメント

| ディレクトリ | README | AGENTS.md |
| :--- | :--- | :--- |
| (ルート) | [README.md](README.md) | [AGENTS.md](AGENTS.md) |
| `definitions/` | [definitions/README.md](definitions/README.md) | [definitions/AGENTS.md](definitions/AGENTS.md) |
| `functions/` | [functions/README.md](functions/README.md) | [functions/AGENTS.md](functions/AGENTS.md) |
| `terraform/` | [terraform/README.md](terraform/README.md) | [terraform/AGENTS.md](terraform/AGENTS.md) |
| `samples/` | [samples/README.md](samples/README.md) | — |
