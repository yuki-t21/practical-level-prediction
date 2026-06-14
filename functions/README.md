# functions/ — Cloud Run Functions

本ディレクトリには、実務レベル予測パイプラインを構成する 2 つの **Cloud Run Functions (第2世代)** が収録されています。

---

## 関数一覧

| 関数名 | ディレクトリ | トリガー | 役割 |
| :--- | :--- | :--- | :--- |
| `import-skill-check` | `import-skill-check/` | GCS オブジェクト作成 (`.xlsx`) | スキルチェック結果 Excel を BigQuery にインポート |
| `export-prediction` | `export-prediction/` | GCS オブジェクト作成 (`.csv`) | 推論対象ユーザーリストに対してバッチ予測を実行し、Excel レポートを出力 |

---

## 1. import-skill-check

スキルチェック結果の Excel ファイルが GCS バケットにアップロードされると自動的にトリガーされ、以下の処理を行います。

1. GCS から Excel ファイル (`.xlsx`) を取得
2. 横持ちのサービス評価データを縦持ち構造に変換（Unpivot）
3. 各サービス評価値（3/2/1）を実務レベルフラグ（1/0）に2値化
4. BigQuery の `raw_data.skill_check_results` テーブルへ `WRITE_TRUNCATE` でロード
5. BigQuery の `raw_data.service_master` テーブルを `CREATE OR REPLACE TABLE` で再作成

詳細は [`import-skill-check/README.md`](import-skill-check/README.md) を参照してください。

**主な環境変数**

| 変数名 | 説明 |
| :--- | :--- |
| `PROJECT_ID` | Google Cloud プロジェクト ID |

---

## 2. export-prediction

推論対象のユーザー ID リスト CSV が GCS バケットにアップロードされると自動的にトリガーされ、以下の処理を行います。

1. GCS から CSV ファイル (`targets_{service_id}[_suffix].csv`) を取得
2. ファイル名からサービス ID を抽出
3. BigQuery ML の `ML.EXPLAIN_PREDICT` を呼び出し、バッチ予測と SHAP 重要度を同時に取得
4. 上位 5 特徴量の SHAP 値を含む結果を Excel 形式にフラット化
5. タイムスタンプ付きの Excel ファイルを出力先 GCS バケットへアップロード

**CSVファイル命名規則**

トリガーとなる CSV ファイルは以下の命名規則に従う必要があります。

```
targets_{service_id}.csv
targets_{service_id}_{yyyymmdd}.csv   # 日付サフィックス付き
```

例: `targets_1.csv`, `targets_1_20260614.csv` → サービス ID `1` として処理

**主な環境変数**

| 変数名 | 説明 | デフォルト値 |
| :--- | :--- | :--- |
| `PROJECT_ID` | Google Cloud プロジェクト ID | (必須) |
| `MODEL_DATASET` | BQML モデルが格納されているデータセット ID | `ml_models` |
| `FEATURES_DATASET` | 特徴量テーブルが格納されているデータセット ID | `features` |
| `FEATURES_TABLE` | 特徴量テーブルのベース名（`_{service_id}` サフィックスが付与される） | `engineer_features` |
| `OUTPUT_BUCKET_NAME` | 予測結果 Excel の出力先 GCS バケット名 | (必須) |

---

## 共通事項

### 開発環境のセットアップ

本プロジェクトはパッケージ管理に [`uv`](https://docs.astral.sh/uv/) を使用しています。
各関数ディレクトリ配下で以下を実行してください。

```bash
uv sync
```

### 単体テストの実行

```bash
uv run pytest
```

### コード品質チェック

```bash
# フォーマット
uv run black .

# 静的解析
uv run flake8 .
```

> [!NOTE]
> 依存パッケージのバージョンは `pyproject.toml` で `==` を用いて厳密に固定しています。
> パッケージを追加・更新した場合は、必ず `==<バージョン>` に書き換え `uv sync` で同期してください。

### スキーマの二重管理について

`import-skill-check` が扱う `skill_check_results` および `service_master` の 2 テーブルのスキーマは、以下の 2 箇所で管理されています。
スキーマ変更時は**両方を必ず同時に更新**してください。

- `dataform/definitions/sources/` 配下の SQLX ファイル（Dataform 側）
- `import-skill-check/schemas/` 配下の JSON ファイル（Python インポーター側）

---

## アーキテクチャ上の位置づけ

```
[スキルチェック Excel] ──→ GCS ──→ import-skill-check ──→ BigQuery (raw_data)
                                                                    │
                                                              Dataform パイプライン
                                                                    │
                                                           BigQuery (features / ml_models)
                                                                    │
[推論対象ユーザー CSV] ──→ GCS ──→ export-prediction ────────────────→ Excel レポート ──→ GCS
```
