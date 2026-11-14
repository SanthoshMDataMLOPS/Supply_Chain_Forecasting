# Dataform repository connected to this GitHub repo. A release configuration compiles `main`
# on a schedule, and a workflow configuration runs the compiled DAG every morning.

resource "google_secret_manager_secret_iam_member" "dataform_git_token" {
  provider  = google-beta
  secret_id = regex("secrets/([^/]+)/versions", var.dataform_git_secret_version)[0]
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-dataform.iam.gserviceaccount.com"
}

resource "google_dataform_repository" "this" {
  provider        = google-beta
  name            = "inbound-container-forecasting"
  region          = var.region
  service_account = google_service_account.dataform.email

  git_remote_settings {
    url                                 = var.dataform_git_url
    default_branch                      = "main"
    authentication_token_secret_version = var.dataform_git_secret_version
  }

  workspace_compilation_overrides {
    default_database = var.project_id
  }

  depends_on = [
    google_project_service.apis,
    google_service_account_iam_member.dataform_agent_token_creator,
  ]
}

resource "google_dataform_repository_release_config" "prod" {
  provider   = google-beta
  project    = var.project_id
  region     = var.region
  repository = google_dataform_repository.this.name

  name          = "prod"
  git_commitish = "main"
  cron_schedule = "0 4 * * *"
  time_zone     = "UTC"

  code_compilation_config {
    default_database = var.project_id
    default_location = var.bq_location
    default_schema   = "staging"
    assertion_schema = "dataform_assertions"
    vars = {
      forecast_horizon_days    = "14"
      history_start_date       = "2023-01-01"
      detention_threshold_days = "4"
    }
  }
}

resource "google_dataform_repository_workflow_config" "daily" {
  provider   = google-beta
  project    = var.project_id
  region     = var.region
  repository = google_dataform_repository.this.name

  name           = "daily"
  release_config = google_dataform_repository_release_config.prod.id
  cron_schedule  = "0 5 * * *" # inference pipeline runs at 06:00 UTC
  time_zone      = "UTC"

  invocation_config {
    included_tags                            = ["daily"]
    transitive_dependencies_included         = true
    transitive_dependents_included           = false
    fully_refresh_incremental_tables_enabled = false
    service_account                          = google_service_account.dataform.email
  }
}
