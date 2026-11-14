import numpy as np
import pandas as pd

from inbound_forecast.features import (
    FEATURES,
    build_features,
    split_future,
    split_labeled,
    time_split,
)
from inbound_forecast.synthetic import generate_daily


def _daily(days=120, dcs=2):
    daily = generate_daily(n_dcs=dcs, days=days + 14, seed=1)
    cutoff = daily["arrival_date"].max() - pd.Timedelta(days=14)
    daily.loc[daily["arrival_date"] > cutoff, ["container_count", "teu_total", "avg_dwell_days"]] = np.nan
    return daily


def test_horizon_rows_are_appended_and_unlabeled():
    feats = build_features(_daily())
    future = split_future(feats)
    assert len(future) == 14 * 2
    assert future["container_count"].isna().all()
    assert split_labeled(feats)["container_count"].notna().all()


def test_no_target_leakage_in_lags():
    """A feature for day t must only use targets from day <= t - 14."""
    feats = build_features(_daily()).sort_values(["dc_id", "arrival_date"])
    g = feats[feats["dc_id"] == "DC01"].reset_index(drop=True)
    for t in (60, 80, 100):
        assert g.loc[t, "container_count_lag_14"] == g.loc[t - 14, "container_count"]
        window = g.loc[t - 14 - 6 : t - 14, "container_count"]
        assert np.isclose(g.loc[t, "container_count_roll7_mean"], window.mean())


def test_future_rows_have_usable_lags():
    future = split_future(build_features(_daily()))
    assert future["container_count_lag_14"].notna().all()
    assert future["container_count_roll7_mean"].notna().all()


def test_all_feature_columns_exist():
    feats = build_features(_daily())
    from inbound_forecast.features import encode_dc

    enc = encode_dc(feats, ["DC01", "DC02"])
    assert set(FEATURES) <= set(enc.columns)


def test_time_split_is_chronological_and_disjoint():
    labeled = split_labeled(build_features(_daily(days=200))).dropna(subset=["container_count_lag_14"])
    tr, va, te = time_split(labeled, valid_days=28, test_days=28)
    assert tr["arrival_date"].max() < va["arrival_date"].min()
    assert va["arrival_date"].max() < te["arrival_date"].min()
    assert len(tr) + len(va) + len(te) == len(labeled)
