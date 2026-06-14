# サンプルデータディレクトリ (samples/)

このディレクトリには、実務レベル予測システムにおける動作検証およびデータインポートのためのサンプルファイルが格納されています。

## 格納されているサンプルファイル一覧

| ファイル名 | ファイル形式 | 主な目的・用途 |
| :--- | :--- | :--- |
| **`sample_skill_check.xlsx`** | Excel (`.xlsx`) | インポーター（`import-skill-check`）の動作確認および初期データのロード |
| **`targets_1.csv`** | CSV (`.csv`) | 予測結果エクスポート（`export-prediction`）のトリガーおよび予測対象ユーザーIDリスト |

---

## 1. `sample_skill_check.xlsx` (スキルチェック結果のサンプル)

### 目的
GCSにファイルがアップロードされたことを検知して動き、BigQueryの `raw_data` データセットにスキルチェック結果およびサービスマスタをインポートする Cloud Run Function (`import-skill-check`) の検証用データです。

### 動作確認手順
1. このファイルを `raw-skill-check-bucket-[suffix]` バケットにアップロードします。
   ```bash
   gcloud storage cp samples/sample_skill_check.xlsx gs://raw-skill-check-bucket-[suffix]/
   ```
2. アップロードされると、`import-skill-check` 関数が自動で実行されます。
3. 成功すると、BigQueryの `raw_data` データセット内に以下の2つのテーブルが自動生成され、レコードが挿入されます。
   - `service_master` (サービスマスタ)
   - `skill_check_results` (スキルチェック評価データ)

---

## 2. `targets_1.csv` (予測対象者リストのサンプル)

### 目的
学習済みのMLモデルを用いて特定のサービスIDに対する予測を実行し、結果（予測値とSHAPによる要因分析結果）を Excel ファイルでエクスポートする Cloud Run Function (`export-prediction`) の検証用データです。
ファイル名に含まれる `_1` は、予測対象となるサービスID（例: AlloyDB = 1）を示しています。

### 動作確認手順
1. DataformでMLモデル（`ml_models.engineer_skill_model_1`）の学習が正常に完了していることを確認します。
2. このファイルを `target-user-list-bucket-[suffix]` バケットにアップロードします。
   ```bash
   gcloud storage cp samples/targets_1.csv gs://target-user-list-bucket-[suffix]/
   ```
3. アップロードされると、`export-prediction` 関数が自動で実行されます。
4. 成功すると、`prediction-results-bucket-[suffix]` バケットの中に、以下のような予測結果をまとめた Excel ファイルが自動で生成されます。
   - `predictions_targets_1_[タイムスタンプ].xlsx`
