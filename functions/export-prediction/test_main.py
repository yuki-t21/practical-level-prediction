import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import main

# Mock client globals early to avoid DefaultCredentialsError during import
main.bq_client = MagicMock()
main.storage_client = MagicMock()
from main import (
    flatten_shap_attributions,
    export_prediction,
    extract_service_id,
    fetch_service_name_mapping,
    run_explain_predict,
    upload_to_gcs,
)


class TestExportPrediction(unittest.TestCase):

    def test_flatten_shap_attributions(self):
        # Create dummy Row objects (simulating BigQuery row items)
        class MockRow:
            def __init__(self, data):
                self._data = data

            def items(self):
                return self._data.items()

        # Dummy result row with nested SHAP values and original feature values
        dummy_rows = [
            MockRow(
                {
                    "user_id": "user_A",
                    "predicted_is_practical_level": 1,
                    "probability": 0.85,
                    "gcp_certified_decay_score": 0.9,
                    "service_1": 1.0,
                    "top_feature_attributions": [
                        {"feature": "gcp_certified_decay_score", "attribution": 0.4},
                        {"feature": "service_1", "attribution": 0.3},
                    ],
                }
            ),
            MockRow(
                {
                    "user_id": "user_B",
                    "predicted_is_practical_level": 0,
                    "probability": 0.15,
                    "gcp_certified_decay_score": 0.1,
                    "service_1": 0.0,
                    "top_feature_attributions": [
                        {"feature": "gcp_certified_decay_score", "attribution": -0.2},
                        {"feature": "service_1", "attribution": -0.1},
                    ],
                }
            ),
        ]

        df_flat = flatten_shap_attributions(dummy_rows)

        # Basic shape check: 2 users, columns: user_id, predicted_is_practical_level, probability,
        # plus 5 * 3 (name, value, SHAP value) features = 3 + 15 = 18 columns.
        self.assertEqual(df_flat.shape[0], 2)
        self.assertEqual(df_flat.shape[1], 18)

        # Row A checks
        self.assertEqual(df_flat.loc[0, "user_id"], "user_A")
        self.assertEqual(df_flat.loc[0, "predicted_is_practical_level"], 1)
        self.assertEqual(df_flat.loc[0, "probability"], 0.85)
        self.assertEqual(df_flat.loc[0, "特徴量1_名前"], "gcp_certified_decay_score")
        self.assertEqual(df_flat.loc[0, "特徴量1_値"], 0.9)
        self.assertEqual(df_flat.loc[0, "特徴量1_SHAP値"], 0.4)

        # service_1 should remain "service_1" (remapping happens at target_service_name column instead)
        self.assertEqual(df_flat.loc[0, "特徴量2_名前"], "service_1")
        self.assertEqual(df_flat.loc[0, "特徴量2_値"], 1.0)
        self.assertEqual(df_flat.loc[0, "特徴量2_SHAP値"], 0.3)

        # Check that columns 3, 4, 5 are padded with None
        self.assertIsNone(df_flat.loc[0, "特徴量3_名前"])
        self.assertIsNone(df_flat.loc[0, "特徴量3_値"])
        self.assertIsNone(df_flat.loc[0, "特徴量3_SHAP値"])

    @patch("main.storage_client")
    @patch("main.bq_client")
    def test_export_prediction_non_csv(self, mock_bq, mock_storage):
        mock_event = MagicMock()
        mock_event.data = {"bucket": "my-bucket", "name": "data.xlsx"}

        export_prediction(mock_event)

        mock_storage.bucket.assert_not_called()

    @patch("main.storage_client")
    @patch("main.bq_client")
    @patch("main.OUTPUT_BUCKET_NAME", "dest-bucket")
    @patch("main.PROJECT_ID", "test-project")
    @patch("pandas.read_csv")
    @patch("main.flatten_shap_attributions")
    def test_export_prediction_flow_numeric_id(
        self, mock_flatten, mock_read_csv, mock_bq, mock_storage
    ):
        # Mock storage download
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_as_bytes.return_value = b"dummy csv"

        # Mock pandas read_csv
        mock_read_csv.return_value = pd.DataFrame({"user_id": ["user_1", "user_2"]})

        # Mock BQ query responses using side_effect
        def query_side_effect(query, job_config=None):
            job = MagicMock()
            if "service_master" in query:
                row = MagicMock()
                row.service_id = 1
                row.service_name = "AlloyDB"
                job.result.return_value = [row]
            else:
                mock_results = MagicMock()
                mock_results.total_rows = 2
                job.result.return_value = mock_results
            return job

        mock_bq.query.side_effect = query_side_effect

        # Mock flatten
        mock_df_flat = pd.DataFrame(
            {"user_id": ["user_1", "user_2"], "predicted_is_practical_level": [1, 0]}
        )
        mock_flatten.return_value = mock_df_flat

        # Mock Event with numeric service_id
        mock_event = MagicMock()
        mock_event.data = {"bucket": "my-bucket", "name": "targets_1_20260614.csv"}

        export_prediction(mock_event)

        # Assert correct methods were called
        mock_storage.bucket.assert_any_call("my-bucket")
        mock_bucket.blob.assert_any_call("targets_1_20260614.csv")
        mock_read_csv.assert_called_once()

        # BQ query should be called twice: once for service_master mapping and once for prediction
        self.assertEqual(mock_bq.query.call_count, 2)
        mock_flatten.assert_called_once()

        # Verify dynamic query compilation used the numeric service ID "1"
        called_args = [args[0] for args, _ in mock_bq.query.call_args_list]
        explain_query = [q for q in called_args if "ML.EXPLAIN_PREDICT" in q][0]
        self.assertIn("ml_models.engineer_skill_model_1", explain_query)
        self.assertIn("features.engineer_features_1", explain_query)

        # Verify it uploaded the results to destination bucket
        mock_storage.bucket.assert_any_call("dest-bucket")

    @patch("main.storage_client")
    @patch("main.bq_client")
    @patch("main.OUTPUT_BUCKET_NAME", "dest-bucket")
    @patch("main.PROJECT_ID", "test-project")
    @patch("pandas.read_csv")
    @patch("main.flatten_shap_attributions")
    def test_export_prediction_flow_legacy_id(
        self, mock_flatten, mock_read_csv, mock_bq, mock_storage
    ):
        # Mock storage download
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_as_bytes.return_value = b"dummy csv"

        # Mock pandas read_csv
        mock_read_csv.return_value = pd.DataFrame({"user_id": ["user_1", "user_2"]})

        # Mock BQ query responses using side_effect
        def query_side_effect(query, job_config=None):
            job = MagicMock()
            if "service_master" in query:
                job.result.return_value = []
            else:
                mock_results = MagicMock()
                mock_results.total_rows = 2
                job.result.return_value = mock_results
            return job

        mock_bq.query.side_effect = query_side_effect

        # Mock flatten to return dataframe we can insert target_service_name into
        mock_df_flat = pd.DataFrame(
            {"user_id": ["user_1", "user_2"], "predicted_is_practical_level": [1, 0]}
        )
        mock_flatten.return_value = mock_df_flat

        # Mock Event with legacy name-based ID (which will fallback to "1")
        mock_event = MagicMock()
        mock_event.data = {
            "bucket": "my-bucket",
            "name": "targets_cloud_run_20260614.csv",
        }

        export_prediction(mock_event)

        # Verify dynamic query compilation used "cloud_run" as service ID
        called_args = [args[0] for args, _ in mock_bq.query.call_args_list]
        explain_query = [q for q in called_args if "ML.EXPLAIN_PREDICT" in q][0]
        self.assertIn("ml_models.engineer_skill_model_cloud_run", explain_query)
        self.assertIn("features.engineer_features_cloud_run", explain_query)

    def test_extract_service_id(self):
        # Simple numeric ID
        self.assertEqual(extract_service_id("targets_123_20260614.csv"), "123")
        self.assertEqual(extract_service_id("targets_1_2026.csv"), "1")
        # Legacy named ID
        self.assertEqual(
            extract_service_id("targets_cloud_run_20260614.csv"), "cloud_run"
        )
        # Edge cases and fallback
        self.assertEqual(extract_service_id("invalid_name.csv"), "1")

    def test_fetch_service_name_mapping(self):
        mock_bq = MagicMock()
        mock_row_1 = MagicMock()
        mock_row_1.service_id = "1"
        mock_row_1.service_name = "App Engine"
        mock_row_2 = MagicMock()
        mock_row_2.service_id = 2
        mock_row_2.service_name = "Cloud Run"

        mock_job = MagicMock()
        mock_job.result.return_value = [mock_row_1, mock_row_2]
        mock_bq.query.return_value = mock_job

        mapping = fetch_service_name_mapping(mock_bq, "test-project")
        self.assertEqual(mapping, {1: "App Engine", 2: "Cloud Run"})

    def test_run_explain_predict(self):
        mock_bq = MagicMock()
        mock_job = MagicMock()
        mock_bq.query.return_value = mock_job
        mock_results = MagicMock()
        mock_job.result.return_value = mock_results

        results = run_explain_predict(
            mock_bq,
            project_id="test-project",
            model_dataset="ml_models",
            model_name="model_1",
            features_dataset="features",
            features_table="table_1",
            user_ids=["user_1", "user_2"],
        )
        self.assertEqual(results, mock_results)
        mock_bq.query.assert_called_once()

    def test_upload_to_gcs(self):
        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        upload_to_gcs(
            mock_storage,
            bucket_name="my-bucket",
            destination_file_name="output.xlsx",
            data_bytes=b"dummy-data",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        mock_storage.bucket.assert_called_once_with("my-bucket")
        mock_bucket.blob.assert_called_once_with("output.xlsx")
        mock_blob.upload_from_string.assert_called_once_with(
            b"dummy-data",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


if __name__ == "__main__":
    unittest.main()
