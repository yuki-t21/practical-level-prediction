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
    global bq_client
    if bq_client is None:
        bq_client = bigquery.Client()
    return bq_client


def get_storage_client():
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
    Flatten nested top_feature_attributions from ML.EXPLAIN_PREDICT in a memory-efficient way.
    Converts list of rows into a flat DataFrame containing features, values, and SHAP values.
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


@functions_framework.cloud_event
def export_prediction(cloud_event):
    """Event-driven Cloud Run Function triggered by CSV target list upload."""
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

        # Extract service_id from file_name (e.g. targets_1_20260614.csv -> 1)
        base_name = os.path.splitext(os.path.basename(file_name))[0]
        match = re.match(r"targets_(\d+)", base_name)
        if match:
            service_id = match.group(1)
        elif base_name.startswith("targets_"):
            tmp = base_name[len("targets_") :]
            parts = tmp.split("_")
            # Remove date/time like numeric parts from the end
            while parts and (
                parts[-1].isdigit() or len(parts[-1]) == 6 or len(parts[-1]) == 8
            ):
                parts.pop()
            service_id = "_".join(parts)
        else:
            service_id = "1"  # Fallback

        logger.info(f"Extracted service_id: {service_id}")
        model_name = f"engineer_skill_model_{service_id}"

        # 2.5 Retrieve service_master table to map service_id to service_name
        service_mapping = {}
        try:
            mapping_query = f"SELECT service_id, service_name FROM `{PROJECT_ID}.raw_data.service_master`"
            mapping_job = get_bq_client().query(mapping_query)
            mapping_rows = mapping_job.result()
            for r in mapping_rows:
                try:
                    service_mapping[int(r.service_id)] = r.service_name
                except (ValueError, TypeError):
                    service_mapping[r.service_id] = r.service_name
            logger.info(
                f"Loaded {len(service_mapping)} service names from service_master."
            )
        except Exception as me:
            logger.warning(
                f"Could not load service_master for mapping. Error: {str(me)}"
            )

        # Safely convert service_id to int key if possible
        try:
            service_id_key = int(service_id)
        except (ValueError, TypeError):
            service_id_key = service_id

        friendly_service_name = service_mapping.get(
            service_id_key, f"Service {service_id}"
        )

        # 3. Query ML.EXPLAIN_PREDICT
        # Note: BQ ML.EXPLAIN_PREDICT returns probability and top_feature_attributions.
        # We join back to the features table to get all feature columns for value lookup.
        features_table_with_suffix = f"{FEATURES_TABLE}_{service_id}"
        query = f"""
        SELECT
          f.*,
          p.predicted_is_practical_level,
          p.probability,
          p.top_feature_attributions
        FROM
          ML.EXPLAIN_PREDICT(
            MODEL `{PROJECT_ID}.{MODEL_DATASET}.{model_name}`,
            (
              SELECT * FROM `{PROJECT_ID}.{FEATURES_DATASET}.{features_table_with_suffix}`
              WHERE user_id IN UNNEST(@user_ids)
            ),
            STRUCT(5 AS top_k_features)
          ) AS p
        JOIN
          `{PROJECT_ID}.{FEATURES_DATASET}.{features_table_with_suffix}` AS f
        ON
          p.user_id = f.user_id
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("user_ids", "STRING", user_ids)
            ]
        )

        logger.info("Executing ML.EXPLAIN_PREDICT query in BigQuery...")
        query_job = get_bq_client().query(query, job_config=job_config)
        results = query_job.result()  # Wait for query to complete
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
        output_buffer.seek(0)

        # 6. Upload Excel file to destination GCS bucket
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(file_name))[0]
        output_file_name = f"predictions_{base_name}_{timestamp}.xlsx"

        dest_bucket = get_storage_client().bucket(OUTPUT_BUCKET_NAME)
        dest_blob = dest_bucket.blob(output_file_name)

        logger.info(
            f"Uploading output Excel to gs://{OUTPUT_BUCKET_NAME}/{output_file_name}"
        )
        dest_blob.upload_from_file(
            output_buffer,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        logger.info("Upload completed successfully.")

    except Exception as e:
        logger.error(f"Error during export prediction process: {str(e)}", exc_info=True)
        raise e
