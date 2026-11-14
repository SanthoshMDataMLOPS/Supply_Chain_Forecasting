# Turns the structured ERROR logs emitted by the monitoring component into an email alert.

resource "google_logging_metric" "forecast_alerts" {
  name   = "inbound_forecast_monitoring_alerts"
  filter = "severity>=ERROR AND textPayload:\"inbound_forecast_monitoring\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_notification_channel" "email" {
  display_name = "Inbound forecast on-call"
  type         = "email"
  labels       = { email_address = var.alert_email }
}

resource "google_monitoring_alert_policy" "forecast_degradation" {
  display_name = "Inbound container forecast: drift or accuracy degradation"
  combiner     = "OR"

  conditions {
    display_name = "Monitoring component raised an alert"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.forecast_alerts.name}\" AND resource.type=\"global\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "3600s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  documentation {
    content   = "See ml.model_monitoring in BigQuery and docs/runbook.md for next steps."
    mime_type = "text/markdown"
  }
}
