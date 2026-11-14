"""Feature definitions shared by training, inference and monitoring.

The SQL source of truth is dataform/definitions/marts/mart_container_volume_features.sqlx.
`build_features` below is a pandas mirror used for local runs and unit tests. CI checks that
every column in FEATURES appears in the compiled Dataform output (tests/contract).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TARGET = "container_count"
KEY_COLS = ["dc_id", "arrival_date"]
CATEGORICAL = ["dc_id"]

NUMERIC_FEATURES = [
    "day_of_week",
    "week_of_year",
    "month",
    "day_of_month",
    "is_weekend",
    "planned_containers",
    "planned_teu",
    "inventory_utilization",
    "on_order_units",
    "container_count_lag_14",
    "container_count_lag_21",
    "container_count_lag_28",
    "container_count_lag_42",
    "teu_total_lag_14",
    "teu_total_lag_21",
    "avg_dwell_days_lag_14",
    "container_count_roll7_mean",
    "container_count_roll28_mean",
]
FEATURES = ["dc_code", *NUMERIC_FEATURES]


def encode_dc(df: pd.DataFrame, dc_categories: list[str]) -> pd.DataFrame:
    """Map dc_id to a stable integer code. Unknown DCs become NaN (treated as missing)."""
    out = df.copy()
    mapping = {dc: i for i, dc in enumerate(dc_categories)}
    out["dc_code"] = out["dc_id"].map(mapping).astype("float64")
    return out


def build_features(daily: pd.DataFrame, horizon: int = 14) -> pd.DataFrame:
    """Pandas mirror of the Dataform feature mart.

    `daily` needs: dc_id, arrival_date, container_count, teu_total, avg_dwell_days,
    planned_containers, planned_teu, inventory_utilization, on_order_units.
    Rows for the forecast horizon (container_count NaN) are appended automatically if missing.
    """
    if horizon != 14:
        raise ValueError("Feature names are fixed for a 14 day horizon.")
    daily = daily.copy()
    daily["arrival_date"] = pd.to_datetime(daily["arrival_date"])
    # "today": the last day with an observed target. Later rows (e.g. ASN-based planned arrivals
    # for upcoming ETAs) are kept as the forecast horizon, their target stays NaN.
    last_actual = daily.loc[daily[TARGET].notna(), "arrival_date"].max()
    daily = daily[daily["arrival_date"] <= last_actual + pd.Timedelta(days=horizon)]

    frames = []
    for dc, g in daily.groupby("dc_id"):
        idx = pd.date_range(g["arrival_date"].min(), last_actual + pd.Timedelta(days=horizon))
        g = g.set_index("arrival_date").reindex(idx)
        g["dc_id"] = dc
        g.index.name = "arrival_date"
        frames.append(g.reset_index())
    df = pd.concat(frames, ignore_index=True).sort_values(KEY_COLS)

    df["is_future"] = df["arrival_date"] > last_actual
    for c in ["planned_containers", "planned_teu"]:
        df[c] = df[c].fillna(0)

    d = df["arrival_date"]
    df["day_of_week"] = (d.dt.dayofweek + 1) % 7 + 1  # BigQuery DAYOFWEEK: Sunday=1
    df["week_of_year"] = d.dt.strftime("%U").astype(int)  # BigQuery WEEK: Sunday-based
    df["month"] = d.dt.month
    df["day_of_month"] = d.dt.day
    df["is_weekend"] = df["day_of_week"].isin([1, 7]).astype(int)

    grp = df.groupby("dc_id", sort=False)
    for n in (14, 21, 28, 42):
        df[f"container_count_lag_{n}"] = grp["container_count"].shift(n)
    for n in (14, 21):
        df[f"teu_total_lag_{n}"] = grp["teu_total"].shift(n)
    df["avg_dwell_days_lag_14"] = grp["avg_dwell_days"].shift(14)

    shifted = grp["container_count"].shift(horizon)
    for size in (7, 28):
        df[f"container_count_roll{size}_mean"] = (
            shifted.groupby(df["dc_id"]).rolling(size, min_periods=1).mean().reset_index(level=0, drop=True)
        )
    return df


def split_labeled(df: pd.DataFrame) -> pd.DataFrame:
    """Rows with a known target (history)."""
    return df[(~df["is_future"]) & df[TARGET].notna()].copy()


def split_future(df: pd.DataFrame) -> pd.DataFrame:
    """Rows to forecast (the horizon)."""
    return df[df["is_future"]].copy()


def time_split(
    df: pd.DataFrame, valid_days: int = 56, test_days: int = 56
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Chronological train / validation / test split. Never shuffle time series."""
    last = df["arrival_date"].max()
    test_start = last - pd.Timedelta(days=test_days - 1)
    valid_start = test_start - pd.Timedelta(days=valid_days)
    train = df[df["arrival_date"] < valid_start]
    valid = df[(df["arrival_date"] >= valid_start) & (df["arrival_date"] < test_start)]
    test = df[df["arrival_date"] >= test_start]
    return train, valid, test


def to_xy(df: pd.DataFrame, dc_categories: list[str]) -> tuple[pd.DataFrame, np.ndarray]:
    enc = encode_dc(df, dc_categories)
    x = enc[FEATURES].astype("float64")
    y = enc[TARGET].to_numpy(dtype="float64") if TARGET in enc and enc[TARGET].notna().any() else None
    return x, y
