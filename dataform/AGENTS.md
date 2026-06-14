# Dataform 開発エージェント向け指示書 (AGENTS.md)

本ディレクトリ (`dataform/`) における Dataform プロジェクトの変更・開発を行うエージェントは、以下のプラクティスを必ず遵守してください。

---

## 1. Dataform Core 3.0 への完全準拠と 2026 年最新仕様

本プロジェクトは **Dataform Core 3.0** に準拠して構成されています。

### ① 設定ファイルとパッケージ管理
- レガシーな `dataform.json` や Node.js の `package.json`, `package-lock.json` は使用しません。
- 設定や環境変数（コンパイル変数等）の定義は、すべてルートの **`workflow_settings.yaml`** で行います。
- 依存する Dataform Core のバージョン管理（`dataformCoreVersion`）も `workflow_settings.yaml` に定義されています。
- **重要**: ルートに `node_modules/` ディレクトリが存在すると、コンパイル時に `'node_modules' unexpected; remove it and try again` エラーが発生するため、絶対に `npm install` などを実行して `node_modules/` を生成しないでください。

### ② 1テーブル 1ファイルによるソース宣言
- 複数のソーステーブルを JavaScript (`sources.js` など) で一括定義する手法は非推奨です。
- ソース定義は、`definitions/sources/` ディレクトリ配下に、1テーブルにつき 1つの `.sqlx` ファイル（`type: "declaration"`）として個別に定義してください。

### ③ データセット分離
- 本プロジェクト（予測システム）側でインポート・管理するソースデータは `raw_data` データセットに属します。
- 他チームが管理している既存のマスターやトランザクションテーブル（職務経歴、資格マスター等）は `other_team_dataset` データセットに属します。
- それぞれ `schema` 設定を正確に割り当ててください。

### ④ セキュリティ：「Strict Act-As」モードへの対応 (2026 年必須仕様)
- 2026 年 4 月より強制されているセキュリティ仕様です。デフォルトのサービスエージェント権限でのパイプライン実行は機能しません。
- ワークフロー実行時には必ず**カスタムサービスアカウント**を設定し、そのサービスアカウントの「サービスアカウントユーザー (Service Account User)」および「サービスアカウントトークン作成者 (Service Account Token Creator)」権限を Dataform サービスエージェントに付与した環境で実行する必要があります。

### ⑤ 環境（Development / Production）の分離
- 開発用と本番用のデータを完全に分離するため、リポジトリや `workflow_settings.yaml` のコンパイル設定を活用します。
- 開発環境では個人用スキーマ/プロジェクトに書き出されるようにし、本番環境 (CI/CD) では明示的な Production 設定を適用して実行します。

### ⑥ インポート用ソーススキーマの二重管理について (重要)
- 本プロジェクトでインポートを担当する `skill_check_results` と `service_master` の 2 テーブルについては、以下の 2 箇所でスキーマ情報（カラム名、説明等）を定義しています。
  1. Dataform定義: `dataform/definitions/sources/` 配下の SQLX ファイル
  2. Pythonインポーター定義: `functions/import-skill-check/schemas/` 配下の JSON ファイル
- デプロイの疎結合性および Python 側ユニットテスト（`test_main.py`）のローカル実行時の独立性（外部ディレクトリへのパス依存排除）を維持するため、意図的にこの二重管理構成としています。スキーマ変更時（カラムの追加や説明文の更新等）は、**必ず双方のファイルを同時に更新してください。**

---

## 2. SQL スタイルガイド (予約語の大文字統一)

コードの可読性と保守性を維持するため、以下の SQL スタイルを厳格に適用してください。

- **予約語は大文字**: SQL のすべてのキーワードは大文字で記述してください。
  - 良い例: `SELECT`, `FROM`, `WHERE`, `JOIN`, `INNER JOIN`, `LEFT JOIN`, `ON`, `AND`, `OR`, `AS`, `GROUP BY`, `ORDER BY`, `WITH`, `UNION ALL`, `CASE`, `WHEN`, `THEN`, `ELSE`, `END`
- **関数名は大文字**: BigQuery 組み込み関数および集計関数は大文字で記述してください。
  - 良い例: `COUNTIF()`, `DATE_DIFF()`, `DATE_ADD()`, `LOWER()`, `EXP()`, `COALESCE()`, `CURRENT_DATE()`, `CURRENT_TIMESTAMP()`, `REGEXP_CONTAINS()`
- **テーブル名・カラム名・エイリアスは小文字**: スネークケース（`snake_case`）を使用し、すべて小文字で記述してください。
  - 良い例: `user_id AS uid`, `skill_check_results AS scr`

### ③ 文末のセミコロン `;` の使い分け
Dataform の SQLX ファイルでは、アクションのタイプ（`type`）に応じて、文末のセミコロン `;` の有無を厳格に使い分ける必要があります。

- **`type: "table"`, `type: "view"`, `type: "incremental"` の場合**:
  - **文末にセミコロン `;` は付加しないでください**。
  - Dataform はこれらのクエリを基に `CREATE TABLE AS SELECT ...` や `INSERT INTO ...` などの DDL/DML 構文を自動ラップして BigQuery に送信します。クエリ末尾に `;` があると二重の区切りとなり、BigQuery 側で構文エラー（Syntax Error）が発生します。
- **`type: "operations"` の場合**:
  - **文末にセミコロン `;` を必ず付加してください**。
  - `operations` は、記述された SQL をそのまま BigQuery のスクリプト（マルチステートメント）として直接実行します。そのため、変数の宣言（`DECLARE`）や代入（`SET`）、動的SQLの実行（`EXECUTE IMMEDIATE`）などの区切りおよび最終文の末尾には必ず `;` を記述する必要があります。

---

## 3. スキーマ定義 (columns) と アサーション (Assertions) の必須化

データカタログの充実とデータ品質の担保のため、SQLX ファイルにはスキーマ定義と検証用アサーションを記述してください。

### ① スキーマ・カラム定義 (columns) の記述ルール
静的にスキーマ（出力カラム）が確定しているテーブル、ビュー、およびソース宣言ファイル（`declaration`）の `config` ブロック内には、必ず **`columns`** プロパティを記述し、各カラムの説明を明記してください。
- **対象外**: クエリ内で PIVOT や動的 SQL（`EXECUTE IMMEDIATE` 等）を使用して動的にカラムを生成・マージするファイル（例: `common_features.sqlx`, `engineer_features.sqlx`, `explain_predictions.sqlx` など）は除きます。
- **記述例**:
  ```javascript
  config {
    type: "table",
    name: "example_table",
    columns: {
      user_id: "ユーザーID",
      status: "ステータス値 (0: 無効, 1: 有効)"
    }
  }
  ```

### ② アサーション項目
主要なテーブル定義（特に `type: "table"` や `type: "incremental"`）の `config` ブロック内には、以下の検証アサーションを明記してください。

- **`uniqueKey`**: 主キーとなるカラム（例: `user_id` など）の一意性担保。
- **`nonNull`**: `null` を許容しないカラムの Null チェック。
- **`rowConditions`**: ドメインルールや値の範囲チェック。

### ③ データ不具合の伝播防止
- 依存する親テーブルのアサーションが失敗した場合に、不完全なデータが子テーブルに伝播しないよう、子テーブルの `config` にてアサーション失敗時に実行を停止する制御を行ってください。

### 設定例 (`definitions/service_features.sqlx` 内)
```sql
config {
  type: "table",
  schema: "features",
  name: "service_features_1",
  description: "特定サービスに依存する縦持ち特徴量テーブル",
  columns: {
    user_id: "ユーザーID",
    is_practical_level: "実務レベル判定フラグ (0 or 1)",
    target_service_id: "予測対象のサービスID"
  },
  assertions: {
    uniqueKey: ["user_id"],
    nonNull: ["user_id", "is_practical_level", "target_service_id"]
  }
}
```

---

## 4. ユニットテスト (Unit Tests) の必須化

特徴量生成ロジックなど、データ変換や計算ロジックが複雑な SQLX ファイルについては、アサーションに加えて **`test` ブロックによるユニットテスト**を必須とします。

- テスト定義内の `input` では、必ずターゲットスキーマとテーブル名を一致させてください (例: `input "other_team_dataset", "user_certifications"`)。
- テストデータ（`input`）にはエッジケースを含め、変換後の期待値（`expect`）と一致することを確認します。

### 実装例 (`definitions/tests/test_engineer_features.sqlx`)
```sql
config {
  type: "test",
  dataset: "engineer_features"
}

input "raw_data", "skill_check_results" {
  SELECT "user_A" AS user_id, 1 AS service_id, 1 AS is_practical_level, CURRENT_TIMESTAMP() AS updated_at UNION ALL
  SELECT "user_B" AS user_id, 1 AS service_id, 0 AS is_practical_level, CURRENT_TIMESTAMP() AS updated_at
}

input "other_team_dataset", "user_certifications" {
  SELECT "user_A" AS user_id, "cert_01" AS certification_id, DATE("2024-01-01") AS first_acquisition_date, DATE("2025-01-01") AS latest_acquisition_date, CURRENT_TIMESTAMP() AS created_at, CURRENT_TIMESTAMP() AS updated_at
}

input "other_team_dataset", "google_cloud_certifications" {
  SELECT "cert_01" AS certification_id, "lvl_01" AS cert_level_id, "Professional Cloud Architect" AS certification_name, 2 AS validity_years, CURRENT_TIMESTAMP() AS created_at, CURRENT_TIMESTAMP() AS updated_at
}

input "other_team_dataset", "certification_levels" {
  SELECT "lvl_01" AS cert_level_id, "プロフェッショナル" AS level_name, CURRENT_TIMESTAMP() AS created_at, CURRENT_TIMESTAMP() AS updated_at
}

input "other_team_dataset", "resumes" {
  SELECT "user_A" AS user_id, "インフラの設計・構築経験あり" AS resume_text, CURRENT_TIMESTAMP() AS created_at, CURRENT_TIMESTAMP() AS updated_at UNION ALL
  SELECT "user_B" AS user_id, "テスト実施のみ" AS resume_text, CURRENT_TIMESTAMP() AS created_at, CURRENT_TIMESTAMP() AS updated_at
}

input "other_team_dataset", "github_metrics" {
  SELECT "user_A" AS user_id, 5 AS public_repos, 10 AS total_stars, 100 AS total_commits, CURRENT_TIMESTAMP() AS created_at, CURRENT_TIMESTAMP() AS updated_at UNION ALL
  SELECT "user_B" AS user_id, 0 AS public_repos, 0 AS total_stars, 0 AS total_commits, CURRENT_TIMESTAMP() AS created_at, CURRENT_TIMESTAMP() AS updated_at
}

expect {
  SELECT
    "user_A" AS user_id,
    1 AS is_practical_level,
    "1" AS target_service_id,
    1.0 AS gcp_experience_years,
    1 AS total_active_certs,
    1 AS num_professional_certs,
    0 AS num_associate_certs,
    0 AS num_foundational_certs,
    1.0 AS weighted_gcp_cert_score,
    1 AS has_ops_tuning_keywords,
    5 AS github_public_repos,
    10 AS github_stars,
    100 AS github_commits
  UNION ALL
  SELECT
    "user_B" AS user_id,
    0 AS is_practical_level,
    "1" AS target_service_id,
    0.0 AS gcp_experience_years,
    0 AS total_active_certs,
    0 AS num_professional_certs,
    0 AS num_associate_certs,
    0 AS num_foundational_certs,
    0.0 AS weighted_gcp_cert_score,
    0 AS has_ops_tuning_keywords,
    0 AS github_public_repos,
    0 AS github_stars,
    0 AS github_commits
}
```

## 5. SQLLinting / Formatting の実行

SQL の書き方（予約語の大文字統一など）を自動検証・修正するため、**SQLFluff** と **`sqlfluff-templater-dataform`** を導入しています。開発時はコミット前に必ず Linter を実行してください。

### ① インストール
ローカルの Python 環境にパッケージをインストールします。
```bash
pip install sqlfluff sqlfluff-templater-dataform
```

### ② コマンドによる検証・自動修正
`dataform` ディレクトリで以下のコマンドを実行します。
```bash
# 構文チェック (エラー検出)
sqlfluff lint definitions/

# 自動フォーマット (可能な限り自動で大文字化やインデント修正)
sqlfluff fix definitions/
```

---

## 6. コマンドラインによる検証

変更を行った際は、以下の手順でビルド・テスト・スタイルチェックが正常に通るかローカル環境で検証してください。

```bash
# 1. SQL のスタイル・フォーマットチェック (SQLFluff)
sqlfluff lint definitions/

# 2. コンパイル確認 (構文・依存関係・スキーマエラーの検出)
npx @dataform/cli compile

# 3. ユニットテストの実行 (テストケースの成否チェック)
# ※ 実行には GCP 認証設定 (.df-credentials.json 等) が必要です
npx @dataform/cli test

# 4. アサーションを含めた全体のドライラン/実行テスト (必要に応じて)
npx @dataform/cli run --dry-run
```
