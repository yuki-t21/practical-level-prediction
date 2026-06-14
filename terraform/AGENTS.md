# Terraform 開発エージェント向け指示書 (AGENTS.md)

本ディレクトリ (`terraform/`) 配下の Terraform コードの変更・開発を行うエージェントは、以下のプラクティスを必ず遵守してください。

---

## 1. プロジェクト構成

本ディレクトリの Terraform コードは、実務レベル予測システムに必要な以下の Google Cloud リソースを一元管理しています。

- **`gcs.tf`**: GCS バケット（スキルチェック受信・推論対象リスト受信・予測結果出力・関数ソース格納）
- **`bigquery.tf`**: BigQuery データセット（`raw_data` / `features` / `ml_models`）
- **`functions.tf`**: Cloud Run Functions (第2世代) のデプロイ定義（ソース ZIP 生成を含む）
- **`dataform.tf`**: Dataform リポジトリおよび Dataform サービスエージェントへの権限付与
- **`iam.tf`**: サービスアカウント・IAM バインディング・Workload Identity Federation (WIF) 設定
- **`variables.tf`**: 入力変数の定義
- **`outputs.tf`**: 出力値の定義
- **`providers.tf`**: Terraform・プロバイダーのバージョン固定・GCS バックエンド設定
- **`main.tf`**: GCS バケット名サフィックスのローカル変数定義

---

## 2. プロジェクト ID のハードコード禁止 (最重要ルール)

Google Cloud のプロジェクト ID を `.tf` ファイル内にリテラル文字列として直接記述することは**絶対に禁止**です。

### 正しい参照方法

プロジェクト ID は常に **`var.project_id`** 変数経由で参照してください。

```hcl
# ✅ 正しい例
resource "google_bigquery_dataset" "example" {
  project    = var.project_id
  dataset_id = "example_dataset"
}

resource "google_project_iam_member" "example" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.example_sa.email}"
}
```

```hcl
# ❌ 禁止例
resource "google_bigquery_dataset" "example" {
  project    = "my-gcp-project-123"   # ハードコード禁止
  dataset_id = "example_dataset"
}
```

### プロジェクト番号が必要な場合

IAM ポリシーなどでプロジェクト**番号**（数値 ID）が必要な場合は、`data "google_project"` リソースを使用して動的に取得してください。

```hcl
# iam.tf にすでに定義済み
data "google_project" "project" {}

# プロジェクト番号の参照
member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-dataform.iam.gserviceaccount.com"
```

---

## 3. 変数・ローカル変数の活用

ハードコードを避けるため、リソース名・パラメータは変数またはローカル変数で管理してください。

### ① 入力変数 (`variables.tf`)
新たにパラメータ化が必要な値が生じた場合は、`variables.tf` に変数を追加し、必要に応じてデフォルト値を設定してください。

```hcl
variable "new_parameter" {
  description = "パラメータの説明"
  type        = string
  default     = "default-value"
}
```

### ② ローカル変数 (`main.tf`)
複数のリソース間で共通して使用する計算値（バケット名サフィックス等）はローカル変数 (`locals`) に集約してください。

```hcl
locals {
  suffix = var.bucket_suffix != "" ? var.bucket_suffix : random_id.bucket_prefix.hex
}
```

---

## 4. GCS バックエンドによる状態管理

Terraform の状態ファイル (`terraform.tfstate`) は GCS バケットで管理されています。

- **ローカルの `terraform.tfstate` / `terraform.tfstate.backup` はバージョン管理から除外されています**（`.gitignore` で設定済み）。
- 初期化時は必ず `-backend-config` でバケット名を指定してください。

```bash
terraform init -backend-config="bucket=<tfstate保存先バケット名>"
```

> [!CAUTION]
> `terraform.tfstate` にはリソースの設定情報（サービスアカウントのメールアドレス等）が含まれます。ローカルファイルをリポジトリにコミットしないでください。

---

## 5. Cloud Run Functions のソースコード管理

`functions.tf` では `data "archive_file"` を使用して `../functions/` 配下のソースコードを ZIP 化し、GCS 経由でデプロイしています。

- ZIP ファイルはビルド時に `files/` ディレクトリに生成されます。生成物であるため、`files/*.zip` はバージョン管理から除外してください。
- 関数のソースコードを変更した場合は、`terraform apply` を再実行することで ZIP が自動的に再生成・アップロードされ、関数がデプロイされます。
- テストコード (`test_main.py`)・仮想環境 (`.venv/`)・キャッシュ (`__pycache__/`, `.pytest_cache/`) は ZIP から除外されています。

```hcl
data "archive_file" "example_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/example"
  output_path = "${path.module}/files/example.zip"
  excludes    = ["venv", ".venv", "__pycache__", "test_main.py", ".pytest_cache", "uv.lock"]
}
```

---

## 6. IAM 設計の原則

IAM バインディングを追加・変更する際は、以下の原則を遵守してください。

### ① 最小権限の原則
サービスアカウントには、業務上必要な最小限の権限のみを付与してください。プロジェクトレベルの強力なロール（`roles/owner` 等）の使用は避け、データセット単位・バケット単位のスコープに絞ることを優先してください。

### ② サービスアカウントのハードコード禁止
サービスアカウントのメールアドレスは、`google_service_account` リソースの `email` 属性を参照してください。

```hcl
# ✅ 正しい例
member = "serviceAccount:${google_service_account.pipeline_sa.email}"

# ❌ 禁止例
member = "serviceAccount:ml-pipeline-sa@my-project.iam.gserviceaccount.com"
```

### ③ Workload Identity Federation (WIF) の活用
GitHub Actions からのデプロイにはサービスアカウントキーを使用せず、WIF による認証を使用してください。`iam.tf` に設定済みの `github_deployer_sa` を利用してください。

---

## 7. コマンドによる検証

変更を加えた際は、以下の手順で検証してください。

```bash
# 1. フォーマットチェック
terraform fmt -check

# 2. 自動フォーマット
terraform fmt

# 3. 構文バリデーション
terraform validate

# 4. 実行計画の確認 (必ず project_id を指定すること)
terraform plan -var="project_id=<your-project-id>"
```

> [!IMPORTANT]
> `terraform apply` の実行には実際の GCP リソースへのアクセス権が必要です。必ず `terraform plan` で差分を確認してから `apply` を行ってください。

---

## 8. 新しいリソースを追加する際のチェックリスト

1. **プロジェクト ID**: `var.project_id` を使用しているか
2. **プロジェクト番号**: `data.google_project.project.number` を使用しているか
3. **サービスアカウント**: メールアドレスをハードコードせず、リソース参照を使用しているか
4. **バケット名**: `local.suffix` を付与してグローバル一意性を確保しているか
5. **IAM**: 最小権限の原則に従った適切なロールスコープになっているか
6. **出力値**: 他のコンポーネント（GitHub Actions、手動手順等）で必要な値を `outputs.tf` に追記したか
7. **フォーマット**: `terraform fmt` でフォーマット済みか
8. **バリデーション**: `terraform validate` でエラーがないか
