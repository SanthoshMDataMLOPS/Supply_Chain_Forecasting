"""Champion / challenger comparison on an identical hold-out window."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .evaluate import wape
from .features import split_labeled, time_split, to_xy


def holdout_wape(bundle: dict, labeled_df: pd.DataFrame, valid_days: int = 56, test_days: int = 56) -> float:
    """WAPE of any bundle on the *same* chronological test window, whatever it was trained on."""
    labeled = split_labeled(labeled_df).dropna(subset=["container_count_lag_14"])
    _, _, test = time_split(labeled, valid_days, test_days)
    x, y = to_xy(test, bundle["dc_categories"])
    pred = np.clip(bundle["model"].predict(x[bundle["feature_cols"]]), 0, None)
    return wape(y, pred)
