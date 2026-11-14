"""Run feature engineering -> training -> batch scoring -> monitoring locally on synthetic data.

    PYTHONPATH=mlops/src python mlops/scripts/local_demo.py

No GCP access needed. Useful to sanity check changes to the modelling code before pushing.
"""

from __future__ import annotations

import logging

import pandas as pd

from inbound_forecast.features import build_features, split_future, split_labeled, time_split, to_xy
from inbound_forecast.monitoring import drift_report
from inbound_forecast.predict import score
from inbound_forecast.synthetic import generate_daily
from inbound_forecast.train import train_model

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    daily = generate_daily(n_dcs=4, days=730 + 14)
    # last 14 days are the "future": ASN plans are known, actual volumes are not
    cutoff = daily["arrival_date"].max() - pd.Timedelta(days=14)
    daily.loc[daily["arrival_date"] > cutoff, ["container_count", "teu_total", "avg_dwell_days"]] = float("nan")

    feats = build_features(daily)
    bundle = train_model(feats, n_trials=6)
    print("\nTEST METRICS:", {k: round(v, 4) for k, v in bundle["metrics"].items()})

    future = split_future(feats)
    forecasts = score(bundle, future, model_version="local")
    print(forecasts.head(8).to_string(index=False))

    x_recent, _ = to_xy(split_labeled(feats).tail(500), bundle["dc_categories"])
    drift = drift_report(bundle["reference"], x_recent)
    print("\nmax PSI:", round(max(drift.values()), 3))


if __name__ == "__main__":
    main()
