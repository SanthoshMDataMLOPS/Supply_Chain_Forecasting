from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .features import to_xy


def score(bundle: dict, future_df: pd.DataFrame, model_version: str) -> pd.DataFrame:
    """Batch-score the forecast horizon rows. Returns the BigQuery forecast table schema."""
    if future_df.empty:
        raise ValueError("No future rows to score. Did the Dataform feature mart run today?")
    x, _ = to_xy(future_df, bundle["dc_categories"])
    x = x[bundle["feature_cols"]]
    pred = np.clip(bundle["model"].predict(x), 0, None)
    return pd.DataFrame(
        {
            "dc_id": future_df["dc_id"].to_numpy(),
            "forecast_date": pd.to_datetime(future_df["arrival_date"]).dt.date.to_numpy(),
            "predicted_containers": pred,
            "lower_bound": np.clip(pred + bundle["residual_q10"], 0, None),
            "upper_bound": pred + bundle["residual_q90"],
            "model_version": model_version,
            "forecast_run_ts": datetime.now(timezone.utc),
        }
    )
