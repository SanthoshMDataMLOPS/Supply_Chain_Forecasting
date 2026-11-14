output "artifact_bucket" {
  value = google_storage_bucket.artifacts.name
}

output "pipeline_service_account" {
  value = google_service_account.pipeline.email
}

output "deployer_service_account" {
  value = google_service_account.deployer.email
}

output "workload_identity_provider" {
  description = "Set as GitHub variable GCP_WIF_PROVIDER"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.mlops.repository_id}"
}
