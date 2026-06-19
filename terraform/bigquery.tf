resource "google_bigquery_dataset" "raw_data" {
  dataset_id                 = "raw_data"
  friendly_name              = "Raw Data Dataset"
  description                = "Contains raw incoming data, including imported skill check results, resumes, certifications, and GitHub metrics"
  location                   = var.region
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "features" {
  dataset_id                 = "features"
  friendly_name              = "Features Dataset"
  description                = "Contains engineered features and integrated training tables"
  location                   = var.region
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "ml_models" {
  dataset_id                 = "ml_models"
  friendly_name              = "ML Models Dataset"
  description                = "Contains BigQuery ML models for skill level prediction"
  location                   = var.region
  delete_contents_on_destroy = true
}

# BigQuery Connection for Slack Notification Cloud Run Function
resource "google_bigquery_connection" "slack_notification_connection" {
  connection_id = "slack_notification_conn"
  location      = var.region
  friendly_name = "Slack Notification Connection"
  description   = "Connection to invoke Slack notification Cloud Run Function"
  cloud_resource {}
}

# BigQuery Remote Function for Slack notification
resource "google_bigquery_routine" "send_slack" {
  dataset_id      = google_bigquery_dataset.ml_models.dataset_id
  routine_id      = "send_slack"
  routine_type    = "SCALAR_FUNCTION"
  language        = "SQL"
  definition_body = ""

  arguments {
    name      = "channel"
    data_type = "{\"typeKind\" : \"STRING\"}"
  }
  arguments {
    name      = "text"
    data_type = "{\"typeKind\" : \"STRING\"}"
  }

  return_type = "{\"typeKind\" : \"STRING\"}"

  remote_function_options {
    endpoint          = google_cloudfunctions2_function.send_slack_notification.service_config[0].uri
    connection        = google_bigquery_connection.slack_notification_connection.name
    max_batching_rows = "10"
  }
}
