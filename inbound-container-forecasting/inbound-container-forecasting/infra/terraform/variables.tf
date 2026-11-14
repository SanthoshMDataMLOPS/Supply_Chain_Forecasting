variable "project_id" {
  type        = string
  description = "GCP project that hosts the whole solution."
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "bq_location" {
  type    = string
  default = "US"
}

variable "github_repository" {
  type        = string
  description = "owner/repo allowed to deploy through Workload Identity Federation."
}

variable "dataform_git_url" {
  type        = string
  description = "HTTPS URL of the GitHub repo Dataform pulls from."
}

variable "dataform_git_secret_version" {
  type        = string
  description = "Secret Manager version holding a GitHub token for Dataform, e.g. projects/123/secrets/dataform-github-token/versions/latest."
}

variable "alert_email" {
  type        = string
  description = "Where model monitoring alerts are sent."
}

variable "enable_feature_store" {
  type        = bool
  default     = false
  description = "Create the Vertex AI Feature Store view. Enable AFTER the first Dataform run has created marts.mart_container_volume_features."
}
