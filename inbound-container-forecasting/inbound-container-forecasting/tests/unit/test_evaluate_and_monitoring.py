import numpy as np
import pandas as pd

from inbound_forecast.evaluate import interval_coverage, metrics, passes_gate, wape
from inbound_forecast.monitoring import drift_report, psi, raise_alerts
from inbound_forecast.train import reference_distributions


def test_wape_basic():
    assert wape([10, 10], [8, 12]) == 0.2


def test_wape_handles_zero_days():
    assert wape([0, 10], [1, 10]) == 0.1


def test_metrics_with_interval():
    m = metrics([10, 20], [10, 20], [9, 19], [11, 21])
    assert m["wape"] == 0 and m["coverage"] == 1.0
    assert interval_coverage([5], [6], [7]) == 0.0


def test_gate_first_model_passes_if_reasonable():
    ok, _ = passes_gate(0.12, None)
    assert ok


def test_gate_rejects_regression_and_absolute_failures():
    assert not passes_gate(0.20, 0.10)[0]
    assert passes_gate(0.101, 0.10)[0]  # within 2% relative tolerance
    assert not passes_gate(0.50, None)[0]
    assert not passes_gate(float("nan"), 0.1)[0]


def test_psi_zero_for_same_distribution_and_high_for_shift():
    rng = np.random.default_rng(0)
    ref = pd.DataFrame({"x": rng.normal(0, 1, 5000)})
    reference = reference_distributions(ref)
    same = drift_report(reference, pd.DataFrame({"x": rng.normal(0, 1, 5000)}))["x"]
    shifted = drift_report(reference, pd.DataFrame({"x": rng.normal(2, 1, 5000)}))["x"]
    assert same < 0.05
    assert shifted > 0.25


def test_psi_empty_series_is_nan():
    assert np.isnan(psi([0.5, 0.5], [-np.inf, 0, np.inf], pd.Series([], dtype=float)))


def test_alerts_fire_on_drift_and_accuracy():
    alerts = raise_alerts({"x": 0.9, "y": 0.01}, {"live_wape": 0.5}, 0.25, 0.35)
    kinds = {a["type"] for a in alerts}
    assert kinds == {"feature_drift", "accuracy_degradation"}
    assert raise_alerts({"x": 0.01}, {"live_wape": 0.1}, 0.25, 0.35) == []
