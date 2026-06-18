import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

import main

# Mock client globals early to avoid DefaultCredentialsError during import
main.bq_client = MagicMock()
main.storage_client = MagicMock()
from main import (
    import_skill_check,
    normalize_column_name,
    preprocess_dataframe,
)


class TestImportSkillCheck(unittest.TestCase):

    def test_normalize_column_name(self):
        self.assertEqual(normalize_column_name("User ID"), "user_id")
        self.assertEqual(normalize_column_name("Score-Value "), "score_value")
        self.assertEqual(
            normalize_column_name("  Is Practical Level!! "), "is_practical_level"
        )
        self.assertEqual(normalize_column_name("123_invalid_col"), "123_invalid_col")

    def test_preprocess_dataframe_valid(self):
        data = {
            "User ID": ["user_1", "user_2", "user_3"],
            "App Engine": [3, 2, 1],
            "Cloud Run": [2, 1, 3],
            "Google Kubernetes Engine": [1, 3, 2],
            "Cloud Storage": [3, None, 2],
            "Workflows": [3, 2, 1],
            "BigQuery": [2, 1, 3],
            "Cloud SQL": [1, 3, 2],
            "Cloud Spanner": [3, None, 2],
            "Firestore": [3, 2, 1],
            "AlloyDB": [2, 1, 3],
            "Bigtable": [1, 3, 2],
            "VPC Service Controls": [3, None, 2],
            "Secure Command Center": [3, 2, 1],
            "Cloud Pub/Sub": [2, 1, 3],
            "Gemini Enterprise Agent Platform": [1, 3, 2],
        }
        df = pd.DataFrame(data)
        df_clean, df_master = preprocess_dataframe(df)

        # Columns check
        self.assertEqual(
            list(df_clean.columns), ["user_id", "service_id", "is_practical_level"]
        )
        self.assertEqual(list(df_master.columns), ["service_id", "service_name"])

        # 3 users * 15 services = 45 rows
        self.assertEqual(len(df_clean), 45)
        self.assertEqual(len(df_master), 15)

        # Check master content (sorted alphabetically)
        self.assertEqual(df_master.iloc[0]["service_name"], "AlloyDB")
        self.assertEqual(df_master.iloc[0]["service_id"], 1)
        self.assertEqual(df_master.iloc[1]["service_name"], "App Engine")
        self.assertEqual(df_master.iloc[1]["service_id"], 2)

        # Helper to get prediction label
        def get_val(u_id, s_id):
            subset = df_clean[
                (df_clean["user_id"] == u_id) & (df_clean["service_id"] == s_id)
            ]
            return subset["is_practical_level"].values[0]

        # user_1 checks:
        # AlloyDB (service_id=1, value=2) -> 1
        # App Engine (service_id=2, value=3) -> 1
        # BigQuery (service_id=3, value=2) -> 1
        # Bigtable (service_id=4, value=1) -> 0
        # Cloud Pub/Sub (service_id=5, value=2) -> 1
        # Cloud Run (service_id=6, value=2) -> 1
        # Cloud SQL (service_id=7, value=1) -> 0
        # Cloud Spanner (service_id=8, value=3) -> 1
        # Cloud Storage (service_id=9, value=3) -> 1
        # Firestore (service_id=10, value=3) -> 1
        # Gemini Enterprise Agent Platform (service_id=11, value=1) -> 0
        # Google Kubernetes Engine (service_id=12, value=1) -> 0
        # Secure Command Center (service_id=13, value=3) -> 1
        # VPC Service Controls (service_id=14, value=3) -> 1
        # Workflows (service_id=15, value=3) -> 1
        self.assertEqual(get_val("user_1", 1), 1)  # AlloyDB
        self.assertEqual(get_val("user_1", 2), 1)  # App Engine
        self.assertEqual(get_val("user_1", 3), 1)  # BigQuery
        self.assertEqual(get_val("user_1", 4), 0)  # Bigtable
        self.assertEqual(get_val("user_1", 5), 1)  # Cloud Pub/Sub
        self.assertEqual(get_val("user_1", 6), 1)  # Cloud Run
        self.assertEqual(get_val("user_1", 7), 0)  # Cloud SQL
        self.assertEqual(get_val("user_1", 8), 1)  # Cloud Spanner
        self.assertEqual(get_val("user_1", 9), 1)  # Cloud Storage
        self.assertEqual(get_val("user_1", 10), 1)  # Firestore
        self.assertEqual(get_val("user_1", 11), 0)  # Gemini Enterprise Agent Platform
        self.assertEqual(get_val("user_1", 12), 0)  # Google Kubernetes Engine
        self.assertEqual(get_val("user_1", 13), 1)  # Secure Command Center
        self.assertEqual(get_val("user_1", 14), 1)  # VPC Service Controls
        self.assertEqual(get_val("user_1", 15), 1)  # Workflows

    def test_preprocess_dataframe_with_outliers(self):
        data = {
            "User ID": ["user_1", "user_2", "", None, "user_5"],
            "App Engine": [3, 99, 1, 3, 2],
            "Cloud Run": [2, 1, 1, 3, None],
            "Google Kubernetes Engine": [1, -5, 1, 3, 3],
            "Cloud Storage": [3, 2, 1, 3, 1],
            "Workflows": [3, 99, 1, 3, 2],
            "BigQuery": [2, 1, 1, 3, None],
            "Cloud SQL": [1, -5, 1, 3, 3],
            "Cloud Spanner": [3, 2, 1, 3, 1],
            "Firestore": [3, 99, 1, 3, 2],
            "AlloyDB": [2, 1, 1, 3, None],
            "Bigtable": [1, -5, 1, 3, 3],
            "VPC Service Controls": [3, 2, 1, 3, 1],
            "Secure Command Center": [3, 99, 1, 3, 2],
            "Cloud Pub/Sub": [2, 1, 1, 3, None],
            "Gemini Enterprise Agent Platform": [1, -5, 1, 3, 3],
        }
        df = pd.DataFrame(data)
        df_clean, df_master = preprocess_dataframe(df)

        # 3 valid users * 15 services = 45 rows
        self.assertEqual(len(df_clean), 45)

        # Helper to get prediction label
        def get_val(u_id, s_id):
            subset = df_clean[
                (df_clean["user_id"] == u_id) & (df_clean["service_id"] == s_id)
            ]
            return subset["is_practical_level"].values[0]

        # user_1 checks
        self.assertEqual(get_val("user_1", 1), 1)  # AlloyDB (2) -> 1
        self.assertEqual(get_val("user_1", 2), 1)  # App Engine (3) -> 1
        self.assertEqual(get_val("user_1", 6), 1)  # Cloud Run (2) -> 1
        self.assertEqual(get_val("user_1", 12), 0)  # GKE (1) -> 0

        # user_2 checks
        self.assertEqual(get_val("user_2", 1), 0)  # AlloyDB (1) -> 0
        self.assertEqual(get_val("user_2", 2), 0)  # App Engine (99) -> 0
        self.assertEqual(get_val("user_2", 6), 0)  # Cloud Run (1) -> 0
        self.assertEqual(get_val("user_2", 9), 1)  # Cloud Storage (2) -> 1

    def test_preprocess_dataframe_missing_user_id(self):
        data = {"Cloud Run": [3]}
        df = pd.DataFrame(data)
        with self.assertRaises(ValueError):
            preprocess_dataframe(df)

    @patch("main.storage_client")
    @patch("main.bq_client")
    def test_import_skill_check_non_excel(self, mock_bq, mock_storage):
        mock_event = MagicMock()
        mock_event.data = {"bucket": "my-bucket", "name": "data.csv"}

        import_skill_check(mock_event)

        # Should exit early and not call storage download
        mock_storage.bucket.assert_not_called()

    @patch("main.storage_client")
    @patch("main.bq_client")
    @patch("pandas.read_excel")
    def test_import_skill_check_excel_flow(
        self, mock_read_excel, mock_bq, mock_storage
    ):
        # Mock storage blob download
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_as_bytes.return_value = b"dummy bytes"

        # Mock pandas read_excel with multi-service schema (15 services)
        mock_df = pd.DataFrame(
            {
                "User ID": ["user_1"],
                "App Engine": [3],
                "Cloud Run": [3],
                "Google Kubernetes Engine": [2],
                "Cloud Storage": [1],
                "Workflows": [3],
                "BigQuery": [2],
                "Cloud SQL": [3],
                "Cloud Spanner": [3],
                "Firestore": [2],
                "AlloyDB": [1],
                "Bigtable": [3],
                "VPC Service Controls": [3],
                "Secure Command Center": [2],
                "Cloud Pub/Sub": [2],
                "Gemini Enterprise Agent Platform": [3],
            }
        )
        mock_read_excel.return_value = mock_df

        # Mock Cloud Event
        mock_event = MagicMock()
        mock_event.data = {"bucket": "my-bucket", "name": "data.xlsx"}

        # Mock BQ methods
        mock_bq.dataset.return_value = MagicMock()
        mock_bq.load_table_from_dataframe.return_value = MagicMock()
        mock_bq.get_table.return_value = MagicMock()
        mock_bq.query.return_value = MagicMock()

        import_skill_check(mock_event)

        # Assert flow was executed
        mock_storage.bucket.assert_called_with("my-bucket")
        mock_bucket.blob.assert_called_with("data.xlsx")
        mock_read_excel.assert_called_once()
        # load_table_from_dataframe should be called once (directly to skill_check_results)
        self.assertEqual(mock_bq.load_table_from_dataframe.call_count, 1)
        # query should be called once (for service_master CREATE OR REPLACE TABLE query)
        self.assertEqual(mock_bq.query.call_count, 1)
        mock_bq.delete_table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
