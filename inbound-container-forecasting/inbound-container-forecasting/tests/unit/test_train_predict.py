import numpy as np
import pandas as pd

from inbound_forecast.features import build_features, split_future
from inbound_forecast.predict import score
from inbound_forecast.promotion import holdout_wape
from inbound_forecast.registry import load_bundle, save_bundle
from inbound_forecast.synthetic import generate_daily
from inbound_forecast.train import train_model


def _features():
    daily = generate_daily(n_dcs=2, days=400 + 14, seed=3)
    cutoff = daily["arrival_date"].max() - pd.Timedelta(days=14)
    daily.loc[daily["arrival_date"] > cutoff, ["container_count", "teu_total", "avg_dwell_days"]] = np.nan
    return build_features(daily)


def test_train_score_roundtrip(tmp_path):
    feats = _features()
    bundle = train_model(feats, n_trials=2, valid_days=28, test_days=28)
    assert bundle["metrics"]["test_wape"] < 0.5
    assert 0 <= bundle["metrics"]["test_coverage"] <= 1

    save_bundle(bundle, str(tmp_path))
    assert (tmp_path / "model.joblib").exists()  # bare estimator for the prebuilt serving container
    loaded = load_bundle(str(tmp_path))

    out = score(loaded, split_future(feats), model_version="test@1")
    assert list(out.columns) == [
        "dc_id", "forecast_date", "predicted_containers", "lower_bound",
        "upper_bound", "model_version", "forecast_run_ts",
    ]
    assert len(out) == 28
    assert (out["lower_bound"] <= out["predicted_containers"]).all()
    assert (out["predicted_containers"] <= out["upper_bound"]).all()
    assert (out["predicted_containers"] >= 0).all()


def test_holdout_wape_matches_bundle_metric():
    feats = _features()
    bundle = train_model(feats, n_trials=2, valid_days=28, test_days=28)
    w = holdout_wape(bundle, feats, valid_days=28, test_days=28)
    assert abs(w - bundle["metrics"]["test_wape"]) < 1e-9
