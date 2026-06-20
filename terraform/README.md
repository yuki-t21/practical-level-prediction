# terraform/ — インフラストラクチャ管理

本ディレクトリには、実務レベル予測システムに必要な Google Cloud リソースを **Terraform** で管理する IaC (Infrastructure as Code) 定義が収録されています。

---

## 管理リソース一覧

### Google Cloud Storage (GCS) バケット

| リソース名 | バケット名 (suffix 付き) | 用途 |
| :--- | :--- | :--- |
| `raw_skill_check` | `raw-skill-check-bucket-{suffix}` | スキルチェック結果 Excel のアップロード先。`import-skill-check` をトリガー |
| `target_user_list` | `target-user-list-bucket-{suffix}` | 推論対象ユーザーリスト CSV のアップロード先。`export-prediction` をトリガー |
| `prediction_results` | `prediction-results-bucket-{suffix}` | 予測結果 Excel の出力先 |
| `function_source` | `gcf-source-bucket-{suffix}` | Cloud Run Functions のソースコード ZIP の格納先 |

> [!NOTE]
> バケット名はグローバルで一意である必要があるため、`bucket_suffix` 変数で任意のサフィックスを指定できます。省略した場合はランダムな ID が自動生成されます。

### BigQuery データセット

| データセット ID | 用途 |
| :--- | :--- |
| `raw_data` | スキルチェック結果・サービスマスタの生データ |
| `features` | Dataform が生成する特徴量テーブル群 |
| `ml_models` | BQML モデル・評価結果・推論結果テーブル |

### Cloud Run Functions (第2世代)

| 関数名 | エントリポイント | トリガーバケット | メモリ / タイムアウト |
| :--- | :--- | :--- | :--- |
| `import-skill-check` | `import_skill_check` | `raw-skill-check-bucket-{suffix}` | 512 MiB / 60 秒 |
| `export-prediction` | `export_prediction` | `target-user-list-bucket-{suffix}` | 1 GiB / 120 秒 |
| `send-slack-notification` | `send_slack_notification` | HTTP (BigQuery Remote Function 用) | 256 MiB / 60 秒 |

関数のソースコードは `../functions/` からビルド時に ZIP 化され、GCS 経由でデプロイされます。

### Dataform

| リソース | 値 |
| :--- | :--- |
| リポジトリ名 | `practical-level-prediction-pipeline` |
| リージョン | `var.region` (デフォルト: `asia-northeast1`) |

Dataform サービスエージェントには BigQuery Admin 権限が付与されています。

### IAM

| サービスアカウント | 用途 |
| :--- | :--- |
| `ml-pipeline-sa` | Cloud Run Functions の実行 SA。BigQuery ジョブ実行・各データセットへの読み書き・GCS 読み書き権限を保持 |
| `github-deployer-sa` | GitHub Actions からのデプロイ専用 SA。Editor 権限を保持 |

#### Workload Identity Federation (GitHub Actions)

GitHub Actions ワークフローがサービスアカウントキーなしで GCP にデプロイできるよう、WIF を設定しています。

- **Pool**: `github-actions-pool`
- **Provider**: `github-actions-provider`
- **対象リポジトリ**: `yuki-t21/practical-level-prediction`

---

## ファイル構成

```
terraform/
├── main.tf          # バケット名サフィックスのローカル変数定義
├── providers.tf     # Terraform・プロバイダーのバージョン固定・GCS バックエンド設定
├── variables.tf     # 入力変数の定義
├── outputs.tf       # 出力値の定義
├── gcs.tf           # GCS バケットリソース
├── bigquery.tf      # BigQuery データセットリソース
├── functions.tf     # Cloud Run Functions リソース (ソース ZIP 生成・デプロイ含む)
├── dataform.tf      # Dataform リポジトリ・権限設定
├── iam.tf           # サービスアカウント・IAM バインディング・WIF 設定
└── files/           # Terraform がビルドした関数ソース ZIP の一時格納ディレクトリ
```

---

## 入力変数

| 変数名 | 説明 | デフォルト値 |
| :--- | :--- | :--- |
| `project_id` | デプロイ先の Google Cloud プロジェクト ID | (必須) |
| `region` | デプロイ先のリージョン | `asia-northeast1` |
| `environment` | デプロイ環境 (`dev` / `prod` 等) | `dev` |
| `bucket_suffix` | GCS バケット名に付与するサフィックス。空の場合はランダム ID が自動生成される | `""` |

---

## 出力値

`terraform apply` 後に以下の値が出力されます。

| 出力変数名 | 説明 |
| :--- | :--- |
| `raw_skill_check_bucket_name` | スキルチェック Excel アップロード用バケット名 |
| `target_user_list_bucket_name` | 推論対象ユーザーリスト CSV アップロード用バケット名 |
| `prediction_results_bucket_name` | 予測結果 Excel 出力先バケット名 |
| `dataform_repository_id` | Dataform リポジトリ ID |
| `import_skill_check_function_uri` | `import-skill-check` 関数の URI |
| `export_prediction_function_uri` | `export-prediction` 関数の URI |
| `workload_identity_provider` | GitHub Actions 用 WIF プロバイダーのリソース名 |
| `github_deployer_service_account_email` | GitHub Actions デプロイ用 SA のメールアドレス |

---

## Terraform バックエンド

Terraform の状態ファイル (`tfstate`) は GCS バケットで管理されています。

```hcl
backend "gcs" {
  prefix = "terraform/state"
}
```

バックエンドのバケット名は初期化時に `-backend-config` オプションで指定する必要があります。

---

## 初回セットアップと実行手順

### 前提条件

- Terraform `>= 1.3.0`
- Google Cloud SDK (`gcloud`) がインストール・認証済みであること

### 1. 認証

```bash
gcloud auth application-default login
```

### 2. 初期化

```bash
terraform init -backend-config="bucket=<tfstate保存先バケット名>"
```

### 3. 実行計画の確認

```bash
terraform plan -var="project_id=<your-project-id>"
```

### 4. 適用

```bash
terraform apply -var="project_id=<your-project-id>"
```

### tfvars ファイルを使う場合

繰り返し実行する場合は `terraform.tfvars` ファイルを作成すると便利です。

```hcl
project_id    = "your-project-id"
region        = "asia-northeast1"
environment   = "dev"
bucket_suffix = "myteam"
```

> [!CAUTION]
> `terraform.tfstate` にはリソースの状態情報が含まれます。このファイルはバージョン管理から除外してください（`.gitignore` で設定済み）。

---

## GitHub Actions との連携

WIF のデプロイ後、GitHub Actions ワークフローで以下の値を使用して認証してください。

```yaml
- uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: ${{ secrets.WIF_PROVIDER }}  # outputs.workload_identity_provider の値
    service_account: ${{ secrets.DEPLOYER_SA_EMAIL }}        # outputs.github_deployer_service_account_email の値
```
