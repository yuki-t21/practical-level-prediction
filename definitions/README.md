# definitions/ — Dataform パイプライン

本ディレクトリには、エンジニアの実務レベル予測システムを構成する **Dataform (Core 3.0)** プロジェクトが収録されています。
BigQuery ML を用いた特徴量エンジニアリング・モデル学習・バッチ推論の一連のパイプラインを管理します。

---

## パイプライン全体像

```
[raw_data データセット]
  skill_check_results  ←── import-skill-check (Cloud Run Function)
  service_master       ←── import-skill-check (Cloud Run Function)

[other_team_dataset]
  user_certifications, google_cloud_certifications, certification_levels
  resumes, github_metrics, tech_blog_metrics, google_cloud_services 等

        │
        ▼ Dataform パイプライン (common_features_pipeline)
  level_weights          : 資格レベル難易度重みテーブル (固定値)
  service_mapping        : サービス名を AI.GENERATE_EMBEDDING で照合・マッピング
  common_features        : 全サービス共通の資格・活動実績特徴量テーブル

        │
        ▼ Dataform パイプライン (service_features_pipeline, service_id 毎に実行)
  service_features_{id}  : 特定サービスに依存する特徴量テーブル
  engineer_features_{id} : 共通特徴量 × サービス特徴量のマージテーブル
  train_model_operation  : BQML モデルの学習 (BOOSTED_TREE_CLASSIFIER)
  evaluate_model_operation : モデル評価結果テーブル
  explain_predictions_operation : ML.EXPLAIN_PREDICT によるバッチ推論と SHAP 値の出力
```

---

## ディレクトリ構成

```
├── workflow_settings.yaml        # プロジェクト設定、デフォルトデータセット、コンパイル変数
├── .sqlfluff                     # SQLFluff の Linter/Formatter 設定
├── .sqlfluffignore               # SQLFluff の対象外ファイル設定
└── definitions/                  # Dataform パイプライン定義ディレクトリ
    ├── AGENTS.md                 # 開発エージェント向けのコーディング規約・開発ルール
    ├── README.md                 # 本ドキュメント
    ├── sources/                  # ソーステーブル宣言 (type: declaration)
    │   ├── skill_check_results.sqlx
    │   ├── service_master.sqlx
    │   ├── user_certifications.sqlx
    │   ├── google_cloud_certifications.sqlx
    │   ├── certification_levels.sqlx
    │   ├── resumes.sqlx
    │   ├── github_metrics.sqlx
    │   ├── tech_blog_metrics.sqlx
    │   ├── tech_blog_master.sqlx
    │   └── google_cloud_services.sqlx
    ├── tests/                    # ユニットテスト定義
    │   ├── test_engineer_features.sqlx
    │   └── test_service_features.sqlx
    ├── level_weights.sqlx        # 資格レベル難易度重み (固定値テーブル)
    ├── service_mapping.sqlx      # サービス名マッピング (インクリメンタル)
    ├── common_features.sqlx      # 全サービス共通特徴量 (EXECUTE IMMEDIATE による動的 PIVOT)
    ├── service_features.sqlx     # サービス固有特徴量 (service_id 変数で動的切替)
    ├── engineer_features.sqlx    # 共通 + サービス特徴量のマージ (アサーション付き)
    ├── train_model.sqlx          # BQML モデル学習
    ├── evaluate_model.sqlx       # モデル評価
    └── explain_predictions.sqlx  # バッチ推論 + SHAP 重要度の出力
```

---

## パイプラインの実行

パイプラインは **タグ** によって 2 段階に分かれています。

### ステップ 1: 共通特徴量パイプライン (`common_features_pipeline`)

全サービス共通の特徴量テーブルを更新します。スキルチェックデータや他チームのマスターデータが更新された際に実行します。

```bash
npx @dataform/cli run --tags common_features_pipeline
```

**含まれる定義**:

| 定義名 | 説明 |
| :--- | :--- |
| `level_weights` | 資格レベル（Professional / Associate / Foundational）の難易度重みテーブル |
| `service_mapping` | `service_master` と `google_cloud_services` をサービス名の意味的類似度で照合したマッピングテーブル。テスト時はテキスト部分一致、本番時は `AI.GENERATE_EMBEDDING` を使用 |
| `common_features` | 全ユーザーの GCP 資格保有状況・加重スコア・GitHub 実績・技術ブログ実績・経歴情報をまとめた共通特徴量テーブル |

### ステップ 2: サービス固有パイプライン (`service_features_pipeline`)

特定サービスのモデル学習・評価・推論を行います。実行前に `workflow_settings.yaml` の `vars.service_id` を対象サービスの ID に設定してください。

```bash
# service_id=1 のサービスを対象に実行する場合
npx @dataform/cli run --tags service_features_pipeline --vars service_id=1
```

**含まれる定義**:

| 定義名 | 説明 |
| :--- | :--- |
| `service_features_{id}` | 対象サービスに関連するレジュメ・GitHub・技術ブログの特徴量テーブル |
| `engineer_features_{id}` | 共通特徴量とサービス固有特徴量をマージした最終特徴量テーブル（アサーション付き） |
| `train_model_operation` | `ML.BOOSTED_TREE_CLASSIFIER` によるモデル学習。出力先: `ml_models.engineer_skill_model_{id}` |
| `evaluate_model_operation` | `ML.EVALUATE` によるモデル評価。出力先: `ml_models.evaluation_{id}` |
| `explain_predictions_operation` | `ML.EXPLAIN_PREDICT` によるバッチ推論と SHAP 重要度の取得。出力先: `ml_models.explain_predictions_{id}` |

---

## コンパイル変数 (`vars`)

`workflow_settings.yaml` の `vars` セクション、または `--vars` オプションで以下の変数を制御できます。

| 変数名 | 説明 | デフォルト値 |
| :--- | :--- | :--- |
| `service_id` | 対象サービスの ID。`service_features_{id}`、`engineer_features_{id}`、各モデル名のサフィックスに使用される | `"1"` |
| `is_test` | `"true"` の場合、`service_mapping` でテキスト部分一致マッピングを使用（BigQuery AI 接続不要）。`"false"` の場合、`AI.GENERATE_EMBEDDING` による本番マッピングを使用 | `"true"` |

---

## 初期設定

1. **`workflow_settings.yaml` の編集**: `defaultProject` を実際の Google Cloud プロジェクト ID に変更してください。

   ```yaml
   defaultProject: your-actual-project-id
   ```

2. **認証設定**: Dataform CLI でのローカル実行には `.df-credentials.json` が必要です。
   Google Cloud の Application Default Credentials から自動生成されます。

   ```bash
   npx @dataform/cli init-creds
   ```

   > [!CAUTION]
   > `.df-credentials.json` には認証情報が含まれるため、`.gitignore` によってバージョン管理から除外されています。リポジトリにコミットしないでください。

3. **Strict Act-As モード対応 (2026年以降必須)**: ワークフロー実行時はカスタムサービスアカウントを設定し、Dataform サービスエージェントに「サービスアカウントユーザー」および「サービスアカウントトークン作成者」権限を付与してください。

---

## ローカル開発コマンド

各コマンドはリポジトリのルートディレクトリ内で実行してください。

```bash
# コンパイル確認 (構文・依存関係エラーの検出)
npx @dataform/cli compile

# ユニットテストの実行 (GCP 認証設定が必要)
npx @dataform/cli test

# ドライラン (実際には実行せず、実行計画を確認)
npx @dataform/cli run --dry-run

# SQL スタイルチェック (SQLFluff)
sqlfluff lint definitions/

# SQL 自動フォーマット (SQLFluff)
sqlfluff fix definitions/
```

---

## データセット構成

| データセット | 管理者 | 用途 |
| :--- | :--- | :--- |
| `raw_data` | 本プロジェクト | スキルチェック結果・サービスマスタ（`import-skill-check` でインポート） |
| `other_team_dataset` | 他チーム | 職務経歴・GCP 資格マスタ・GitHub 実績・技術ブログ実績 |
| `features` | 本プロジェクト | Dataform が生成する特徴量テーブル群 |
| `ml_models` | 本プロジェクト | BQML モデル・評価結果・推論結果テーブル |
| `dataform_assertions` | 本プロジェクト | Dataform が自動生成するアサーション結果 |

---

## スキーマの二重管理について

`import-skill-check` が扱う `raw_data.skill_check_results` および `raw_data.service_master` の 2 テーブルのスキーマは、以下の 2 箇所で管理されています。
スキーマ変更時は**両方を必ず同時に更新**してください。

- `definitions/sources/` 配下の `.sqlx` ファイル（Dataform 側）
- `../functions/import-skill-check/schemas/` 配下の JSON ファイル（Python インポーター側）
