output "raw_skill_check_bucket_name" {
  description = "The name of the GCS bucket for raw skill check uploads"
  value       = google_storage_bucket.raw_skill_check.name
}

output "target_user_list_bucket_name" {
  description = "The name of the GCS bucket for target user CSV list uploads"
  value       = google_storage_bucket.target_user_list.name
}

output "prediction_results_bucket_name" {
  description = "The name of the GCS bucket where final prediction Excel results are saved"
  value       = google_storage_bucket.prediction_results.name
}

output "dataform_repository_id" {
  description = "The ID of the Dataform Repository"
  value       = google_dataform_repository.pipeline_repo.id
}

output "import_skill_check_function_uri" {
  description = "The URI of the import-skill-check Cloud Run Function"
  value       = google_cloudfunctions2_function.import_skill_check.service_config[0].uri
}

output "export_prediction_function_uri" {
  description = "The URI of the export-prediction Cloud Run Function"
  value       = google_cloudfunctions2_function.export_prediction.service_config[0].uri
}

output "workload_identity_provider" {
  description = "The Workload Identity Provider resource name"
  value       = google_iam_workload_identity_pool_provider.github_provider.name
}

output "github_deployer_service_account_email" {
  description = "The email of the GitHub Actions Deployer Service Account"
  value       = google_service_account.github_deployer_sa.email
}

