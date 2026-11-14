# Vertex AI Feature Store (BigQuery-backed). Enable after the first Dataform run has created the mart.

resource "google_vertex_ai_feature_online_store" "this" {
  count    = var.enable_feature_store ? 1 : 0
  provider = google-beta
  name     = "inbound_container_store"
  region   = var.region

  bigtable {
    auto_scaling {
      min_node_count         = 1
      max_node_count         = 1
      cpu_utilization_target = 70
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_vertex_ai_feature_online_store_featureview" "container_volume" {
  count                = var.enable_feature_store ? 1 : 0
  provider             = google-beta
  name                 = "container_volume_features"
  region               = var.region
  feature_online_store = google_vertex_ai_feature_online_store.this[0].name

  # Training pipeline triggers a sync; this cron is a safety net.
  sync_config {
    cron = "0 7 * * *"
  }

  big_query_source {
    uri               = "bq://${var.project_id}.marts.mart_container_volume_features"
    entity_id_columns = ["dc_id"]
  }
}
