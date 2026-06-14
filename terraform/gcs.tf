resource "google_storage_bucket" "raw_skill_check" {
  name                        = "raw-skill-check-bucket-${local.suffix}"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket" "target_user_list" {
  name                        = "target-user-list-bucket-${local.suffix}"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket" "prediction_results" {
  name                        = "prediction-results-bucket-${local.suffix}"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket" "function_source" {
  name                        = "gcf-source-bucket-${local.suffix}"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true
}
