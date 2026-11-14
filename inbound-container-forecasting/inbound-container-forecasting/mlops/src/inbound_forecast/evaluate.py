from __future__ import annotations

import numpy as np


def wape(y_true, y_pred) -> float:
    """Weighted absolute percentage error: sum|e| / sum|y|. Robust to zero-volume days."""
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    denom = np.abs(y_true).sum()
    return float(np.abs(y_true - y_pred).sum() / denom) if denom else float("nan")


def bias(y_true, y_pred) -> float:
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    denom = y_true.sum()
    return float((y_pred - y_true).sum() / denom) if denom else float("nan")


def mape(y_true, y_pred) -> float:
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    m = y_true != 0
    return float(np.mean(np.abs((y_true[m] - y_pred[m]) / y_true[m]))) if m.any() else float("nan")


def interval_coverage(y_true, lower, upper) -> float:
    y_true = np.asarray(y_true, float)
    return float(np.mean((y_true >= np.asarray(lower)) & (y_true <= np.asarray(upper))))


def metrics(y_true, y_pred, lower=None, upper=None) -> dict[str, float]:
    out = {"wape": wape(y_true, y_pred), "mape": mape(y_true, y_pred), "bias": bias(y_true, y_pred)}
    if lower is not None and upper is not None:
        out["coverage"] = interval_coverage(y_true, lower, upper)
    return out


def passes_gate(
    candidate_wape: float,
    champion_wape: float | None,
    max_regression: float = 0.02,
    max_absolute: float = 0.35,
) -> tuple[bool, str]:
    """Decide whether a candidate may be promoted to champion."""
    if np.isnan(candidate_wape):
        return False, "candidate WAPE is NaN"
    if candidate_wape > max_absolute:
        return False, f"candidate WAPE {candidate_wape:.3f} above absolute limit {max_absolute:.3f}"
    if champion_wape is None:
        return True, "no champion registered yet"
    if candidate_wape <= champion_wape * (1 + max_regression):
        return True, f"candidate {candidate_wape:.3f} vs champion {champion_wape:.3f}"
    return False, f"candidate {candidate_wape:.3f} regresses vs champion {champion_wape:.3f}"
