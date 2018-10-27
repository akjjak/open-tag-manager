variable "aws_access_key" {}
variable "aws_secret_key" {}
variable "aws_region" {}
variable "aws_batch_timeout" {
  default = 1800
}

variable "google_project_id" {}
variable "google_region" {}

variable "aws_s3_bucket_prefix" {}

variable "google_bigquery_dataset_location" {}
variable "google_storage_location" {}