"""Runtime configuration, read from environment variables so the same image runs in dev and prod."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("PROJECT_ID", "")
    region: str = os.getenv("REGION", "us-central1")
    bq_location: str = os.getenv("BQ_LOCATION", "US")

    feature_table: str = os.getenv("FEATURE_TABLE", "marts.mart_container_volume_features")
    forecast_table: str = os.getenv("FORECAST_TABLE", "ml.container_volume_forecasts")
    monitoring_table: str = os.getenv("MONITORING_TABLE", "ml.model_monitoring")

    model_display_name: str = os.getenv("MODEL_DISPLAY_NAME", "inbound-container-volume")
    horizon_days: int = int(os.getenv("HORIZON_DAYS", "14"))

    # Promotion gate: candidate must not be worse than the champion by more than this (relative WAPE).
    max_wape_regression: float = float(os.getenv("MAX_WAPE_REGRESSION", "0.02"))
    max_wape_absolute: float = float(os.getenv("MAX_WAPE_ABSOLUTE", "0.35"))
    psi_alert_threshold: float = float(os.getenv("PSI_ALERT_THRESHOLD", "0.25"))


def get_settings() -> Settings:
    return Settings()
