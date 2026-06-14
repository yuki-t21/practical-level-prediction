data "google_project" "project" {}

# Custom Service Account for Cloud Run Functions
resource "google_service_account" "pipeline_sa" {
  account_id   = "ml-pipeline-sa"
  display_name = "ML Pipeline Service Account"
}

# Project-level role: BigQuery Job User (required to run queries/jobs)
resource "google_project_iam_member" "bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# BigQuery Dataset Editor roles for the service account
resource "google_bigquery_dataset_iam_member" "raw_data_editor" {
  dataset_id = google_bigquery_dataset.raw_data.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

resource "google_bigquery_dataset_iam_member" "features_editor" {
  dataset_id = google_bigquery_dataset.features.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

resource "google_bigquery_dataset_iam_member" "ml_models_editor" {
  dataset_id = google_bigquery_dataset.ml_models.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# GCS permissions for the service account
resource "google_storage_bucket_iam_member" "raw_skill_check_viewer" {
  bucket = google_storage_bucket.raw_skill_check.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

resource "google_storage_bucket_iam_member" "target_user_list_viewer" {
  bucket = google_storage_bucket.target_user_list.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

resource "google_storage_bucket_iam_member" "prediction_results_admin" {
  bucket = google_storage_bucket.prediction_results.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# Eventarc Trigger roles: Allow Eventarc to invoke Cloud Run Functions
# Usually, Eventarc uses the default compute service account or a custom SA. 
# We'll grant the Eventarc service agent permission to publish to Pub/Sub and 
# allow the pipeline SA to act as the runtime service account.
resource "google_project_iam_member" "eventarc_event_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# Allow the pipeline SA to invoke Cloud Run services (required for Eventarc to route events to Cloud Run Functions)
resource "google_project_iam_member" "run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# Grant GCS service agent permission to publish to Pub/Sub (needed for Eventarc GCS triggers)
resource "google_project_iam_member" "gcs_pubsub_publishing" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.project.number}@gs-project-accounts.iam.gserviceaccount.com"
}

# -----------------------------------------------------------------
# Workload Identity Federation (WIF) for GitHub Actions
# -----------------------------------------------------------------

resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Workload Identity Pool for GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github_provider" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions-provider"
  display_name                       = "GitHub Actions Provider"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == 'yuki-t21/practical-level-prediction'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Dedicated Service Account for GitHub Actions Deployments
resource "google_service_account" "github_deployer_sa" {
  account_id   = "github-deployer-sa"
  display_name = "GitHub Actions Deployer Service Account"
}

# Grant Editor permissions to the Deployer Service Account to allow creating resources
resource "google_project_iam_member" "deployer_editor" {
  project = var.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.github_deployer_sa.email}"
}

# Allow GitHub Actions (from the specific repository) to impersonate the Deployer Service Account
resource "google_service_account_iam_member" "github_deployer_wif" {
  service_account_id = google_service_account.github_deployer_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/yuki-t21/practical-level-prediction"
}

