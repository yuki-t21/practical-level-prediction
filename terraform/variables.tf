variable "project_id" {
  description = "The GCP Project ID to deploy resources in"
  type        = string
}

variable "region" {
  description = "The GCP region to deploy resources in"
  type        = string
  default     = "asia-northeast1"
}

variable "environment" {
  description = "The deployment environment (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "bucket_suffix" {
  description = "An optional suffix to make GCS bucket names globally unique. If empty, a random ID will be generated."
  type        = string
  default     = ""
}
