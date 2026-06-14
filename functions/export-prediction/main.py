import io
import os
import re
import logging
import datetime
import functions_framework
from google.cloud import bigquery
from google.cloud import storage
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients lazily
bq_client = None
storage_client = None


def get_bq_client():
    """
    BigQuery クライアントを遅延初期化して返します。

    Returns
    -------
    google.cloud.bigquery.Client
        初期化済みの BigQuery クライアント。
    """
    global bq_client
    if bq_client is None:
        bq_client = bigquery.Client()
    return bq_client


def get_storage_client():
    """
    Cloud Storage クライアントを遅延初期化して返します。

    Returns
    -------
    google.cloud.storage.Client
        初期化済みの Cloud Storage クライアント。
    """
    global storage_client
    if storage_client is None:
        storage_client = storage.Client()
    return storage_client


# Read configurations from environment variables
PROJECT_ID = os.environ.get("PROJECT_ID")
MODEL_DATASET = os.environ.get("MODEL_DATASET", "ml_models")
FEATURES_DATASET = os.environ.get("FEATURES_DATASET", "features")
FEATURES_TABLE = os.environ.get("FEATURES_TABLE", "engineer_features")
OUTPUT_BUCKET_NAME = os.environ.get("OUTPUT_BUCKET_NAME")


def flatten_shap_attributions(rows) -> pd.DataFrame:
    """
    ML.EXPLAIN_PREDICT が返すネストされた top_feature_attributions をフラット化します。

    各行の上位 5 特徴量について、特徴量名・特徴量値・SHAP 値を個別のカラムに展開し、
    メモリ効率の良い方式で DataFrame に変換します。

    Parameters
    ----------
    rows : google.cloud.bigquery.table.RowIterator
        ML.EXPLAIN_PREDICT クエリの結果行イテレータ。各行は user_id,
        predicted_is_practical_level, probability, top_feature_attributions
        フィールドを含む。

    Returns
    -------
    pd.DataFrame
        フラット化された予測結果の DataFrame。
        カラム: user_id, predicted_is_practical_level, probability,
        特徴量1_名前, 特徴量1_値, 特徴量1_SHAP値, ...
        (上位 5 特徴量分、データが不足する場合は None で補完)
    """
    flat_data = []

    for row in rows:
        # Convert row to dict for easy access
        row_dict = dict(row.items())

        # Base columns
        flat_row = {
            "user_id": row_dict.get("user_id"),
            "predicted_is_practical_level": row_dict.get(
                "predicted_is_practical_level"
            ),
            "probability": row_dict.get("probability"),
        }

        # Get top feature attributions
        top_features = row_dict.get("top_feature_attributions", [])

        # Expand up to 5 top features
        for idx, attr in enumerate(top_features[:5]):
            feat_name = attr.get("feature")
            shap_value = attr.get("attribution")
            # Look up the actual feature value from the row
            feat_value = row_dict.get(feat_name, None)

            flat_row[f"特徴量{idx+1}_名前"] = feat_name
            flat_row[f"特徴量{idx+1}_値"] = feat_value
            flat_row[f"特徴量{idx+1}_SHAP値"] = shap_value

        # If there are fewer than 5 features, fill the rest with None
        for idx in range(len(top_features), 5):
            flat_row[f"特徴量{idx+1}_名前"] = None
            flat_row[f"特徴量{idx+1}_値"] = None
            flat_row[f"特徴量{idx+1}_SHAP値"] = None

        flat_data.append(flat_row)

    return pd.DataFrame(flat_data)


def extract_service_id(file_name: str) -> str:
    """
    ファイル名からサービス ID を抽出します。

    Parameters
    ----------
    file_name : str
        GCS のトリガーファイル名（例: "targets_1_20260614.csv"）。

    Returns
    -------
    str
        抽出されたサービス ID（例: "1" または "cloud_run"）。
    """
    base_name = os.path.splitext(os.path.basename(file_name))[0]
    match = re.match(r"targets_(\d+)", base_name)
    if match:
        return match.group(1)
    elif base_name.startswith("targets_"):
        tmp = base_name[len("targets_") :]
        parts = tmp.split("_")
        # Remove date/time like numeric parts from the end
        while parts and (
            parts[-1].isdigit() or len(parts[-1]) == 6 or len(parts[-1]) == 8
        ):
            parts.pop()
        return "_".join(parts)
    return "1"  # Fallback


def fetch_service_name_mapping(bq_client, project_id: str) -> dict:
    """
    BigQuery の raw_data.service_master テーブルから
    サービス ID とサービス名のマッピング情報を取得します。

    Parameters
    ----------
    bq_client : google.cloud.bigquery.Client
        BigQuery クライアント。
    project_id : str
        GCP プロジェクト ID。

    Returns
    -------
    dict
        サービス ID をキー、サービス名を値とする辞書。
    """
    service_mapping = {}
    try:
        mapping_query = f"SELECT service_id, service_name FROM `{project_id}.raw_data.service_master`"
        mapping_job = bq_client.query(mapping_query)
        mapping_rows = mapping_job.result()
        for r in mapping_rows:
            try:
                service_mapping[int(r.service_id)] = r.service_name
            except (ValueError, TypeError):
                service_mapping[r.service_id] = r.service_name
        logger.info(f"Loaded {len(service_mapping)} service names from service_master.")
    except Exception as me:
        logger.warning(f"Could not load service_master for mapping. Error: {str(me)}")
    return service_mapping


def run_explain_predict(
    bq_client,
    project_id: str,
    model_dataset: str,
    model_name: str,
    features_dataset: str,
    features_table: str,
    user_ids: list[str],
):
    """
    BigQuery ML の ML.EXPLAIN_PREDICT クエリを実行して、
    バッチ予測結果と SHAP 特徴量重要度を取得します。

    Parameters
    ----------
    bq_client : google.cloud.bigquery.Client
        BigQuery クライアント。
    project_id : str
        GCP プロジェクト ID。
    model_dataset : str
        予測モデルが配置されているデータセット名。
    model_name : str
        予測モデル名。
    features_dataset : str
        特徴量テーブルが配置されているデータセット名。
    features_table : str
        特徴量テーブル名。
    user_ids : list of str
        予測対象のユーザー ID リスト。

    Returns
    -------
    google.cloud.bigquery.table.RowIterator
        クエリ結果の行イテレータ。
    """
    query = f"""
    SELECT
      f.*,
      p.predicted_is_practical_level,
      p.probability,
      p.top_feature_attributions
    FROM
      ML.EXPLAIN_PREDICT(
        MODEL `{project_id}.{model_dataset}.{model_name}`,
        (
          SELECT * FROM `{project_id}.{features_dataset}.{features_table}`
          WHERE user_id IN UNNEST(@user_ids)
        ),
        STRUCT(5 AS top_k_features)
      ) AS p
    JOIN
      `{project_id}.{features_dataset}.{features_table}` AS f
    ON
      p.user_id = f.user_id
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("user_ids", "STRING", user_ids)]
    )

    logger.info("Executing ML.EXPLAIN_PREDICT query in BigQuery...")
    query_job = bq_client.query(query, job_config=job_config)
    return query_job.result()


def upload_to_gcs(
    storage_client,
    bucket_name: str,
    destination_file_name: str,
    data_bytes: bytes,
    content_type: str,
) -> None:
    """
    バイトデータを GCS バケットへアップロードします。

    Parameters
    ----------
    storage_client : google.cloud.storage.Client
        Cloud Storage クライアント。
    bucket_name : str
        アップロード先 GCS バケット名。
    destination_file_name : str
        アップロード先のオブジェクトキー（ファイル名）。
    data_bytes : bytes
        アップロードするバイトデータ。
    content_type : str
        アップロードデータの MIME タイプ。

    Returns
    -------
    None
    """
    dest_bucket = storage_client.bucket(bucket_name)
    dest_blob = dest_bucket.blob(destination_file_name)
    logger.info(f"Uploading file to gs://{bucket_name}/{destination_file_name}")
    dest_blob.upload_from_string(data_bytes, content_type=content_type)
    logger.info("Upload completed successfully.")


@functions_framework.cloud_event
def export_prediction(cloud_event):
    """
    CSV ファイルのアップロードをトリガーに実行されるイベント駆動型 Cloud Run Function。

    GCS バケットに推論対象ユーザーリスト CSV がアップロードされると自動的にトリガーされます。
    ファイル名からサービス ID を抽出し、BigQuery ML の ML.EXPLAIN_PREDICT を呼び出して
    バッチ推論と SHAP 重要度を取得します。結果を Excel 形式にフラット化した上で、
    出力先 GCS バケットへタイムスタンプ付きファイル名でアップロードします。

    Parameters
    ----------
    cloud_event : cloudevents.http.CloudEvent
        GCS オブジェクト作成イベントを表す Cloud Event オブジェクト。
        data フィールドに bucket 名と object 名 (name) を含む。

    Returns
    -------
    None

    Raises
    ------
    ValueError
        OUTPUT_BUCKET_NAME 環境変数が未設定の場合、または CSV に
        user_id カラムが存在しない場合。
    Exception
        BigQuery クエリ実行または GCS アップロード時にエラーが発生した場合。
    """
    data = cloud_event.data
    bucket_name = data.get("bucket")
    file_name = data.get("name")

    logger.info(f"Triggered by file: gs://{bucket_name}/{file_name}")

    # Process only .csv files
    if not file_name.endswith(".csv"):
        logger.info(f"Skipping non-CSV file: {file_name}")
        return

    if not OUTPUT_BUCKET_NAME:
        raise ValueError("OUTPUT_BUCKET_NAME environment variable is not set.")

    try:
        # 1. Download CSV from GCS
        bucket = get_storage_client().bucket(bucket_name)
        blob = bucket.blob(file_name)
        file_bytes = blob.download_as_bytes()

        # 2. Read user IDs from CSV
        df_users = pd.read_csv(io.BytesIO(file_bytes))
        logger.info(f"Successfully read CSV. Row count: {len(df_users)}")

        # Clean user_id list
        if "user_id" not in df_users.columns:
            raise ValueError("CSV is missing required 'user_id' column")

        user_ids = (
            df_users["user_id"].dropna().astype(str).str.strip().unique().tolist()
        )
        logger.info(f"Unique user IDs count to predict: {len(user_ids)}")

        if not user_ids:
            logger.warning("No valid user IDs found in CSV. Skipping prediction.")
            return

        # Extract service_id and map to service_name
        service_id = extract_service_id(file_name)
        logger.info(f"Extracted service_id: {service_id}")
        model_name = f"engineer_skill_model_{service_id}"

        service_mapping = fetch_service_name_mapping(get_bq_client(), PROJECT_ID)

        # Safely convert service_id to int key if possible
        try:
            service_id_key = int(service_id)
        except (ValueError, TypeError):
            service_id_key = service_id

        friendly_service_name = service_mapping.get(
            service_id_key, f"Service {service_id}"
        )

        # 3. Query ML.EXPLAIN_PREDICT
        features_table_with_suffix = f"{FEATURES_TABLE}_{service_id}"
        results = run_explain_predict(
            get_bq_client(),
            PROJECT_ID,
            MODEL_DATASET,
            model_name,
            FEATURES_DATASET,
            features_table_with_suffix,
            user_ids,
        )
        logger.info(
            f"Query completed. Total predictions retrieved: {results.total_rows}"
        )

        # 4. Flatten SHAP values
        logger.info("Flattening SHAP attributions...")
        df_flat = flatten_shap_attributions(results)

        # Insert target_service_name as the second column
        df_flat.insert(1, "target_service_name", friendly_service_name)
        logger.info(f"Flattening completed. Dataframe shape: {df_flat.shape}")

        # 5. Write results to Excel in memory
        output_buffer = io.BytesIO()
        with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
            df_flat.to_excel(writer, index=False, sheet_name="Predictions")
        output_bytes = output_buffer.getvalue()

        # 6. Upload Excel file to destination GCS bucket
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(file_name))[0]
        output_file_name = f"predictions_{base_name}_{timestamp}.xlsx"

        upload_to_gcs(
            get_storage_client(),
            OUTPUT_BUCKET_NAME,
            output_file_name,
            output_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        logger.error(f"Error during export prediction process: {str(e)}", exc_info=True)
        raise e
