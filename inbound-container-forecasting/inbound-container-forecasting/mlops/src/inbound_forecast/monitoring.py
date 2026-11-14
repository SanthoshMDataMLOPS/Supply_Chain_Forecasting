"""Model monitoring: input drift (PSI) and forecast accuracy (WAPE vs actuals)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .evaluate import wape

log = logging.getLogger(__name__)


def psi(ref_props: list[float], ref_edges: list[float], current: pd.Series, eps: float = 1e-4) -> float:
    """Population Stability Index of `current` against the training-time distribution."""
    cur = current.dropna().to_numpy()
    if len(cur) == 0:
        return float("nan")
    cur_props = np.histogram(cur, bins=np.asarray(ref_edges))[0] / len(cur)
    e = np.clip(np.asarray(ref_props), eps, None)
    a = np.clip(cur_props, eps, None)
    return float(np.sum((a - e) * np.log(a / e)))


def drift_report(reference: dict, current_x: pd.DataFrame) -> dict[str, float]:
    out = {}
    for col, ref in reference.items():
        if col in current_x:
            out[col] = psi(ref["props"], ref["edges"], current_x[col])
    return out


def to_monitoring_rows(
    run_ts: datetime, model_version: str, drift: dict[str, float], accuracy: dict[str, float]
) -> pd.DataFrame:
    rows = [(run_ts, model_version, f"psi:{k}", None, v) for k, v in drift.items()]
    rows += [(run_ts, model_version, k, None, v) for k, v in accuracy.items()]
    return pd.DataFrame(rows, columns=["run_ts", "model_version", "metric", "dc_id", "value"])


def evaluate_recent_accuracy(forecast_vs_actual: pd.DataFrame) -> dict[str, float]:
    """Expects predicted_containers and actual_containers (see serving.vw_forecast_accuracy)."""
    if forecast_vs_actual.empty:
        return {}
    return {
        "live_wape": wape(
            forecast_vs_actual["actual_containers"], forecast_vs_actual["predicted_containers"]
        )
    }


def raise_alerts(
    drift: dict[str, float], accuracy: dict[str, float], psi_threshold: float, wape_limit: float
) -> list[dict]:
    """Emit structured ERROR logs. A Cloud Logging log-based metric and alert policy
    (infra/terraform/monitoring.tf) turn these into emails or pages."""
    alerts = []
    for feat, v in drift.items():
        if not np.isnan(v) and v > psi_threshold:
            alerts.append({"type": "feature_drift", "feature": feat, "psi": v})
    if accuracy.get("live_wape", 0) > wape_limit:
        alerts.append(
            {"type": "accuracy_degradation", "live_wape": accuracy["live_wape"], "limit": wape_limit}
        )
    for a in alerts:
        log.error(json.dumps({"alert": "inbound_forecast_monitoring", **a}))
    return alerts


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
