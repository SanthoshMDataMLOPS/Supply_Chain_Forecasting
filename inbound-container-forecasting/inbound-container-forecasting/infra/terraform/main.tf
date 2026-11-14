data "google_project" "this" {}

locals {
  apis = [
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "bigquerystorage.googleapis.com",
    "dataform.googleapis.com",
    "dataproc.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iamcredentials.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
  ]

  datasets = {
    logistics_raw       = "Raw logistics events and parsed ASNs"
    inventory_raw       = "Raw inventory snapshots"
    staging             = "Dataform staging models"
    intermediate        = "Dataform intermediate models"
    marts               = "Dataform feature marts"
    serving             = "Dashboard-facing views and dimensions"
    ml                  = "Forecasts and model monitoring output"
    dataform_assertions = "Dataform data quality assertion results"
  }
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------- BigQuery
resource "google_bigquery_dataset" "ds" {
  for_each                   = local.datasets
  dataset_id                 = each.key
  description                = each.value
  location                   = var.bq_location
  delete_contents_on_destroy = false
  labels                     = { use_case = "inbound-container-volume" }
  depends_on                 = [google_project_service.apis]
}

resource "google_bigquery_table" "forecasts" {
  dataset_id          = google_bigquery_dataset.ds["ml"].dataset_id
  table_id            = "container_volume_forecasts"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "forecast_date"
  }
  clustering = ["dc_id"]

  schema = jsonencode([
    { name = "dc_id", type = "STRING", mode = "REQUIRED" },
    { name = "forecast_date", type = "DATE", mode = "REQUIRED" },
    { name = "predicted_containers", type = "FLOAT", mode = "REQUIRED" },
    { name = "lower_bound", type = "FLOAT", mode = "NULLABLE" },
    { name = "upper_bound", type = "FLOAT", mode = "NULLABLE" },
    { name = "model_version", type = "STRING", mode = "NULLABLE" },
    { name = "forecast_run_ts", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "model_monitoring" {
  dataset_id          = google_bigquery_dataset.ds["ml"].dataset_id
  table_id            = "model_monitoring"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "run_ts"
  }

  schema = jsonencode([
    { name = "run_ts", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "model_version", type = "STRING", mode = "NULLABLE" },
    { name = "metric", type = "STRING", mode = "NULLABLE" },
    { name = "dc_id", type = "STRING", mode = "NULLABLE" },
    { name = "value", type = "FLOAT", mode = "NULLABLE" },
  ])
}

# ---------------------------------------------------------------- Storage / registry
resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-mlops-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_artifact_registry_repository" "mlops" {
  repository_id = "mlops"
  location      = var.region
  format        = "DOCKER"
  description   = "Pipeline component images"
  depends_on    = [google_project_service.apis]
}
