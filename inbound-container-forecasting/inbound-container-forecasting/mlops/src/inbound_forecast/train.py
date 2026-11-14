"""Model training and tuning.

Global gradient boosting model across all DCs (Poisson loss, since the target is a count).
Everything returned is plain python / sklearn so artifacts can be loaded by the Vertex AI
prebuilt sklearn serving container without this package installed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from . import __version__
from .evaluate import metrics, wape
from .features import FEATURES, split_labeled, time_split, to_xy

log = logging.getLogger(__name__)

SEARCH_SPACE = {
    "learning_rate": (0.02, 0.2),
    "max_leaf_nodes": [15, 31, 63],
    "min_samples_leaf": [10, 20, 50],
    "l2_regularization": (0.0, 5.0),
    "max_iter": [300, 600, 900],
}


def _make_model(params: dict, seed: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="poisson",
        categorical_features=[FEATURES.index("dc_code")],
        early_stopping=False,
        random_state=seed,
        **params,
    )


def _sample_params(rng: np.random.Generator) -> dict:
    lo, hi = SEARCH_SPACE["learning_rate"]
    l2lo, l2hi = SEARCH_SPACE["l2_regularization"]
    return {
        "learning_rate": float(np.exp(rng.uniform(np.log(lo), np.log(hi)))),
        "max_leaf_nodes": int(rng.choice(SEARCH_SPACE["max_leaf_nodes"])),
        "min_samples_leaf": int(rng.choice(SEARCH_SPACE["min_samples_leaf"])),
        "l2_regularization": float(rng.uniform(l2lo, l2hi)),
        "max_iter": int(rng.choice(SEARCH_SPACE["max_iter"])),
    }


def tune(x_tr, y_tr, x_va, y_va, n_trials: int = 20, seed: int = 42) -> tuple[dict, list[dict]]:
    """Seeded random search on validation WAPE. Returns best params and the full trial log."""
    rng = np.random.default_rng(seed)
    trials = []
    for i in range(n_trials):
        params = _sample_params(rng)
        model = _make_model(params, seed).fit(x_tr, y_tr)
        score = wape(y_va, model.predict(x_va))
        trials.append({"trial": i, "valid_wape": score, **params})
        log.info("trial %d wape=%.4f params=%s", i, score, params)
    best = min(trials, key=lambda t: t["valid_wape"])
    return {k: best[k] for k in SEARCH_SPACE}, trials


def reference_distributions(x: pd.DataFrame, bins: int = 10) -> dict:
    """Quantile bin edges + proportions per feature, stored for PSI drift checks at inference."""
    ref = {}
    skip = {"dc_code", "day_of_week", "week_of_year", "month", "day_of_month", "is_weekend"}
    for col in x.columns:
        if col in skip:  # calendar features drift seasonally by construction
            continue
        s = x[col].dropna()
        if s.nunique() < 3:
            continue
        edges = np.unique(np.quantile(s, np.linspace(0, 1, bins + 1)))
        if len(edges) < 3:
            continue
        edges[0], edges[-1] = -np.inf, np.inf
        props = np.histogram(s, bins=edges)[0] / len(s)
        ref[col] = {"edges": edges.tolist(), "props": props.tolist()}
    return ref


def train_model(
    features_df: pd.DataFrame,
    n_trials: int = 20,
    valid_days: int = 56,
    test_days: int = 56,
    seed: int = 42,
) -> dict:
    """Train, tune and evaluate. Returns a plain dict bundle (see keys below)."""
    labeled = split_labeled(features_df)
    labeled = labeled.dropna(subset=["container_count_lag_14"])  # start of each series
    train, valid, test = time_split(labeled, valid_days, test_days)
    if min(len(train), len(valid), len(test)) == 0:
        raise ValueError("Not enough history for the requested train/valid/test split.")

    dc_categories = sorted(labeled["dc_id"].unique().tolist())
    x_tr, y_tr = to_xy(train, dc_categories)
    x_va, y_va = to_xy(valid, dc_categories)
    x_te, y_te = to_xy(test, dc_categories)

    best_params, trials = tune(x_tr, y_tr, x_va, y_va, n_trials=n_trials, seed=seed)
    model = _make_model(best_params, seed).fit(x_tr, y_tr)

    # Interval calibration from validation residuals (empirical 10th / 90th percentile).
    resid = y_va - model.predict(x_va)
    q_lo, q_hi = np.quantile(resid, [0.10, 0.90])

    pred_te = np.clip(model.predict(x_te), 0, None)
    lo = np.clip(pred_te + q_lo, 0, None)
    hi = pred_te + q_hi
    test_metrics = metrics(y_te, pred_te, lo, hi)
    log.info("test metrics: %s", test_metrics)

    return {
        "model": model,
        "feature_cols": FEATURES,
        "dc_categories": dc_categories,
        "residual_q10": float(q_lo),
        "residual_q90": float(q_hi),
        "horizon_days": 14,
        "best_params": best_params,
        "metrics": {f"test_{k}": v for k, v in test_metrics.items()}
        | {"valid_wape": min(t["valid_wape"] for t in trials)},
        "reference": reference_distributions(x_tr),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "train_rows": int(len(train)),
        "code_version": __version__,
    }
