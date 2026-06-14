resource "random_id" "bucket_prefix" {
  byte_length = 4
}

locals {
  suffix = var.bucket_suffix != "" ? var.bucket_suffix : random_id.bucket_prefix.hex
}
