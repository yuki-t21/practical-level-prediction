import io
import json
import logging
import os
import re
import functions_framework
from google.cloud import bigquery
from google.cloud import storage
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


def normalize_column_name(col_name: str) -> str:
    """
    列名をスネークケース（snake_case）に標準化します。

    大文字を小文字に変換し、空白やハイフンをアンダースコアに置換します。
    英数字とアンダースコア以外の文字を除外し、先頭および末尾のアンダースコアを削除します。

    Parameters
    ----------
    col_name : str
        標準化する元の列名。

    Returns
    -------
    str
        標準化されたスネークケースの列名。
    """
    name = str(col_name).strip().lower()
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"[^a-z0-9_]", "", name)
    name = re.sub(r"^_+|_+$", "", name)
    name = re.sub(r"_+", "_", name)
    return name


def detect_user_id_column(df: pd.DataFrame) -> str:
    """
    データフレームの列名から標準化された 'user_id' 列を検出し、その元の列名を返します。

    Parameters
    ----------
    df : pd.DataFrame
        対象のデータフレーム。

    Returns
    -------
    str
        'user_id' にマッピングされた元の列名。

    Raises
    ------
    ValueError
        'User ID' に該当する列が存在しない場合。
    """
    original_cols = list(df.columns)
    for col in original_cols:
        if normalize_column_name(col) == "user_id":
            return col
    raise ValueError("Excel is missing required 'User ID' column")


def create_service_master(
    df: pd.DataFrame, user_id_col: str
) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    評価対象のサービス列から、サービスIDマスタの DataFrame とIDマッピングを作成します。

    Parameters
    ----------
    df : pd.DataFrame
        Excelから読み込んだ生の DataFrame。
    user_id_col : str
        ユーザーIDの元の列名。

    Returns
    -------
    tuple
        - df_master (pd.DataFrame): サービスIDとサービス名からなるマスタ。
        - service_id_map (dict): サービス名から数値IDへのマッピング辞書。
    """
    original_cols = list(df.columns)
    original_service_cols = [col for col in original_cols if col != user_id_col]
    original_service_cols.sort()

    master_records = []
    service_id_map = {}

    for idx, orig_name in enumerate(original_service_cols, start=1):
        service_id = int(idx)
        service_id_map[orig_name] = service_id
        master_records.append({"service_id": service_id, "service_name": orig_name})

    df_master = pd.DataFrame(master_records)
    return df_master, service_id_map


def unpivot_ratings(
    df: pd.DataFrame, user_id_col: str, service_id_map: dict[str, int]
) -> pd.DataFrame:
    """
    横持ちのサービス評価データを縦持ち構造に変換（Unpivot）します。

    Parameters
    ----------
    df : pd.DataFrame
        元の DataFrame。
    user_id_col : str
        ユーザーIDの元の列名。
    service_id_map : dict
        サービス列名から数値IDへのマッピング辞書。

    Returns
    -------
    pd.DataFrame
        縦持ち変換されたデータフレーム。
    """
    service_cols = list(service_id_map.keys())
    melt_cols = [user_id_col] + service_cols
    df_subset = df[melt_cols].copy()

    df_melted = df_subset.melt(
        id_vars=[user_id_col],
        value_vars=service_cols,
        var_name="service_name",
        value_name="rating",
    )
    df_melted["service_id"] = df_melted["service_name"].map(service_id_map)
    return df_melted


def clean_skill_check_data(df_melted: pd.DataFrame, user_id_col: str) -> pd.DataFrame:
    """
    縦持ちデータに対してユーザーIDのクレンジング、評価値の2値化を行い、必要なカラムのみを抽出します。

    Parameters
    ----------
    df_melted : pd.DataFrame
        縦持ち変換された DataFrame。
    user_id_col : str
        ユーザーIDの元の列名。

    Returns
    -------
    pd.DataFrame
        クレンジングおよび2値化されたデータフレーム。
    """
    df_melted["user_id"] = df_melted[user_id_col].astype(str).str.strip()
    df_clean = df_melted[
        df_melted["user_id"].notna()
        & (df_melted["user_id"] != "")
        & (df_melted["user_id"].str.lower() != "nan")
    ].copy()

    df_clean["is_practical_level"] = pd.to_numeric(df_clean["rating"], errors="coerce")
    df_clean["is_practical_level"] = df_clean["is_practical_level"].apply(
        lambda x: 1 if x in [2, 3] else 0
    )
    df_clean["is_practical_level"] = df_clean["is_practical_level"].astype(int)

    return df_clean[["user_id", "service_id", "is_practical_level"]].copy()


def preprocess_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Excelからロードした DataFrame をクレンジングし、縦持ちのデータモデルおよびサービスマスタに整形します。

    Parameters
    ----------
    df : pd.DataFrame
        Excelファイルからロードした生の DataFrame。

    Returns
    -------
    tuple of pd.DataFrame
        - df_final (pd.DataFrame): 縦持ちに変換されたクレンジング済みのデータフレーム。
          カラム: `user_id` (STRING), `service_id` (INTEGER), `is_practical_level` (INTEGER)
        - df_master (pd.DataFrame): 自動生成されたサービスマスタのデータフレーム。
          カラム: `service_id` (INTEGER), `service_name` (STRING)

    Raises
    ------
    ValueError
        必須カラムである 'User ID' 列が存在しない場合に発生します。
    """
    user_id_col = detect_user_id_column(df)
    df_master, service_id_map = create_service_master(df, user_id_col)
    df_melted = unpivot_ratings(df, user_id_col, service_id_map)
    df_final = clean_skill_check_data(df_melted, user_id_col)
    return df_final, df_master


def download_from_gcs(bucket_name: str, file_name: str) -> bytes:
    """
    Cloud Storageからファイルをバイト形式でダウンロードします。

    Parameters
    ----------
    bucket_name : str
        バケット名。
    file_name : str
        ファイルパス/名。

    Returns
    -------
    bytes
        ダウンロードされたファイルデータ。
    """
    bucket = get_storage_client().bucket(bucket_name)
    blob = bucket.blob(file_name)
    return blob.download_as_bytes()


def load_schema_from_json(json_path: str) -> list[bigquery.SchemaField]:
    """
    JSON定義ファイルからBigQueryのスキーマ定義を読み込みます。

    Parameters
    ----------
    json_path : str
        JSONスキーマファイルの絶対パス。

    Returns
    -------
    list of bigquery.SchemaField
        BigQuery用のスキーマ定義リスト。
    """
    with open(json_path, "r", encoding="utf-8") as f:
        schema_data = json.load(f)

    schema = []
    for field in schema_data:
        schema.append(
            bigquery.SchemaField(
                name=field["name"],
                field_type=field["type"],
                mode=field.get("mode", "NULLABLE"),
                description=field.get("description"),
            )
        )
    return schema


def load_master_to_bigquery(
    df_master: pd.DataFrame,
    dataset_id: str,
    table_id: str,
    schema: list[bigquery.SchemaField],
) -> None:
    """
    サービスマスタデータをBigQueryにCREATE OR REPLACE TABLEクエリでロードします。

    Parameters
    ----------
    df_master : pd.DataFrame
        サービスマスタのデータフレーム。
    dataset_id : str
        データセットID。
    table_id : str
        テーブルID。
    schema : list of bigquery.SchemaField
        マスタテーブルのスキーマ定義。
    """
    structs = []
    for row in df_master.itertuples():
        escaped_name = str(row.service_name).replace("'", "\\'")
        structs.append(
            f"STRUCT({int(row.service_id)} AS service_id, '{escaped_name}' AS service_name, CURRENT_TIMESTAMP() AS created_at)"
        )

    structs_array = ",\n      ".join(structs)

    # スキーマ定義から型を解決して DDL カラム定義を作成 (例: "service_id INT64, service_name STRING")
    type_mapping = {"INTEGER": "INT64", "STRING": "STRING", "TIMESTAMP": "TIMESTAMP"}
    col_defs = ", ".join(
        [f"{f.name} {type_mapping.get(f.field_type, f.field_type)}" for f in schema]
    )

    bq = get_bq_client()
    query = f"""
    CREATE OR REPLACE TABLE `{bq.project}.{dataset_id}.{table_id}` (
      {col_defs}
    ) AS
    SELECT * FROM UNNEST([
      {structs_array}
    ])
    """

    logger.info(
        f"Re-creating service master table via DDL query: {dataset_id}.{table_id}"
    )
    query_job = bq.query(query)
    query_job.result()
    logger.info("Service master table re-creation completed.")


@functions_framework.cloud_event
def import_skill_check(cloud_event):
    """
    Cloud Storage への Excel ファイルアップロードによってトリガーされ、データを BigQuery に上書きロードする Cloud Run Function。

    イベントデータからアップロードされた Excel ファイルを取得し、Pandas で読み込みます。
    データを縦持ちデータフレームとサービスマスタデータフレームに前処理し、
    BigQuery の `service_master`（DDLクエリ）および `skill_check_results`（直接WRITE_TRUNCATEロード）にそれぞれロードします。

    Parameters
    ----------
    cloud_event : cloudevents.http.CloudEvent
        GCSアップロードイベントを表す Cloud Event オブジェクト。

    Returns
    -------
    None

    Raises
    ------
    Exception
        インポート処理中にエラーが発生した場合に発生し、ログ出力された後再スローされます。
    """
    data = cloud_event.data
    bucket_name = data.get("bucket")
    file_name = data.get("name")

    logger.info(f"Triggered by file: gs://{bucket_name}/{file_name}")

    # Process only .xlsx files
    if not file_name.endswith(".xlsx"):
        logger.info(f"Skipping non-Excel file: {file_name}")
        return

    try:
        # スキーマJSON定義ファイルのパス
        current_dir = os.path.dirname(__file__)
        master_schema_path = os.path.join(current_dir, "schemas", "service_master.json")
        results_schema_path = os.path.join(
            current_dir, "schemas", "skill_check_results.json"
        )

        # 共通JSONスキーマからBigQueryスキーマ定義を動的取得
        master_schema = load_schema_from_json(master_schema_path)
        results_schema = load_schema_from_json(results_schema_path)

        # 1. Download file from GCS
        file_bytes = download_from_gcs(bucket_name, file_name)

        # 2. Read excel with pandas
        df_raw = pd.read_excel(io.BytesIO(file_bytes))
        logger.info(f"Successfully read Excel. Row count: {len(df_raw)}")

        # 3. Preprocess (Dynamic parsing of columns and service IDs into vertical format)
        df_clean, df_master = preprocess_dataframe(df_raw)
        logger.info(
            f"Preprocessed dataframe (vertical). Row count: {len(df_clean)}. Detected services: {len(df_master)}"
        )

        if df_clean.empty:
            logger.warning("Dataframe is empty after preprocessing. Skipping insert.")
            return

        dataset_id = "raw_data"

        # 4. Re-create and Upload Service Master Table (CREATE OR REPLACE TABLE)
        load_master_to_bigquery(df_master, dataset_id, "service_master", master_schema)

        # 5. Overwrite Target Table Directly in BigQuery (WRITE_TRUNCATE)
        target_table_id = "skill_check_results"
        bq = get_bq_client()
        target_table_ref = bq.dataset(dataset_id).table(target_table_id)

        # タイムスタンプを追加
        df_clean_upload = df_clean.copy()
        df_clean_upload["updated_at"] = pd.Timestamp.now(tz="UTC")

        job_config = bigquery.LoadJobConfig(
            schema=results_schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )

        logger.info(
            f"Loading/Overwriting data to target table: {dataset_id}.{target_table_id}"
        )
        load_job = bq.load_table_from_dataframe(
            df_clean_upload, target_table_ref, job_config=job_config
        )
        load_job.result()  # Wait for the job to complete
        logger.info("Target table overwrite completed successfully.")

    except Exception as e:
        logger.error(f"Error during import process: {str(e)}", exc_info=True)
        raise e
