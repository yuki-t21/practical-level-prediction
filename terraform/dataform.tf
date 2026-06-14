resource "google_dataform_repository" "pipeline_repo" {
  provider = google-beta
  name     = "practical-level-prediction-pipeline"
  region   = var.region
  project  = var.project_id

  # Simple repository creation. If Git integration is needed, it can be added here.
}

# Grant Dataform Service Agent BigQuery Admin permissions so it can manage tables and models
resource "google_project_iam_member" "dataform_bq_admin" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-dataform.iam.gserviceaccount.com"
}
