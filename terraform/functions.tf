# Archive functions source code, excluding venv, tests, and caches
data "archive_file" "import_skill_check_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/import-skill-check"
  output_path = "${path.module}/files/import_skill_check.zip"
  excludes    = ["venv", ".venv", "__pycache__", "test_main.py", ".pytest_cache", "uv.lock"]
}

data "archive_file" "export_prediction_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/export-prediction"
  output_path = "${path.module}/files/export_prediction.zip"
  excludes    = ["venv", ".venv", "__pycache__", "test_main.py", ".pytest_cache", "uv.lock"]
}

data "archive_file" "send_slack_notification_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/send-slack-notification"
  output_path = "${path.module}/files/send_slack_notification.zip"
  excludes    = ["venv", ".venv", "__pycache__", "test_main.py", ".pytest_cache", "uv.lock"]
}


# Upload zipped source codes to GCS source bucket
resource "google_storage_bucket_object" "import_skill_check_source" {
  name   = "import_skill_check_${data.archive_file.import_skill_check_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.import_skill_check_zip.output_path
}

resource "google_storage_bucket_object" "export_prediction_source" {
  name   = "export_prediction_${data.archive_file.export_prediction_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.export_prediction_zip.output_path
}

resource "google_storage_bucket_object" "send_slack_notification_source" {
  name   = "send_slack_notification_${data.archive_file.send_slack_notification_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.send_slack_notification_zip.output_path
}

# Cloud Run Function: import-skill-check
resource "google_cloudfunctions2_function" "import_skill_check" {
  name        = "import-skill-check"
  location    = var.region
  description = "Imports and cleans skill check Excel files to BigQuery"

  build_config {
    runtime     = "python314"
    entry_point = "import_skill_check"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.import_skill_check_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 3
    min_instance_count    = 0
    available_memory      = "512Mi"
    timeout_seconds       = 60
    service_account_email = google_service_account.pipeline_sa.email
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.storage.object.v1.finalized"
    retry_policy          = "RETRY_POLICY_DO_NOT_RETRY"
    service_account_email = google_service_account.pipeline_sa.email
    event_filters {
      attribute = "bucket"
      value     = google_storage_bucket.raw_skill_check.name
    }
  }

  depends_on = [
    google_project_iam_member.eventarc_event_receiver,
    google_project_iam_member.gcs_pubsub_publishing
  ]
}

# Cloud Run Function: export-prediction
resource "google_cloudfunctions2_function" "export_prediction" {
  name        = "export-prediction"
  location    = var.region
  description = "Executes BQML EXPLAIN_PREDICT and exports flat SHAP prediction result to GCS Excel"

  build_config {
    runtime     = "python314"
    entry_point = "export_prediction"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.export_prediction_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 3
    min_instance_count    = 0
    available_memory      = "1Gi" # Keep more memory for pandas flattening of large files
    timeout_seconds       = 120
    service_account_email = google_service_account.pipeline_sa.email

    environment_variables = {
      PROJECT_ID         = var.project_id
      MODEL_DATASET      = google_bigquery_dataset.ml_models.dataset_id
      FEATURES_DATASET   = google_bigquery_dataset.features.dataset_id
      FEATURES_TABLE     = "engineer_features"
      OUTPUT_BUCKET_NAME = google_storage_bucket.prediction_results.name
    }

  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.storage.object.v1.finalized"
    retry_policy          = "RETRY_POLICY_DO_NOT_RETRY"
    service_account_email = google_service_account.pipeline_sa.email
    event_filters {
      attribute = "bucket"
      value     = google_storage_bucket.target_user_list.name
    }
  }

  depends_on = [
    google_project_iam_member.eventarc_event_receiver,
    google_project_iam_member.gcs_pubsub_publishing
  ]
}

# Cloud Run Function: send-slack-notification
resource "google_cloudfunctions2_function" "send_slack_notification" {
  name        = "send-slack-notification"
  location    = var.region
  description = "Sends notification to Slack using Secret Manager token, exposed as BQ remote function"

  build_config {
    runtime     = "python314"
    entry_point = "send_slack_notification"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.send_slack_notification_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 3
    min_instance_count    = 0
    available_memory      = "256Mi"
    timeout_seconds       = 60
    service_account_email = google_service_account.pipeline_sa.email

    environment_variables = {
      SLACK_TOKEN_SECRET_NAME = "projects/${data.google_project.project.number}/secrets/SLACK_API_TOKEN/versions/latest"
    }
  }
}

# Archive scrape-gcp-certifications source code
data "archive_file" "scrape_gcp_certifications_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/scrape-gcp-certifications"
  output_path = "${path.module}/files/scrape_gcp_certifications.zip"
  excludes    = ["venv", ".venv", "__pycache__", "test_main.py", ".pytest_cache", "uv.lock"]
}

# Upload zipped source code to GCS source bucket
resource "google_storage_bucket_object" "scrape_gcp_certifications_source" {
  name   = "scrape_gcp_certifications_${data.archive_file.scrape_gcp_certifications_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.scrape_gcp_certifications_zip.output_path
}

# Cloud Run Service: scrape-gcp-certifications (using source GCS ZIP with build_config)
resource "google_cloud_run_v2_service" "scrape_gcp_certifications" {
  name     = "scrape-gcp-certifications"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.pipeline_sa.email
    timeout         = "120s"

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }

  build_config {
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.scrape_gcp_certifications_source.name
      }
    }
  }
}

