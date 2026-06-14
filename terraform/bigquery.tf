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
