"""Synthetic inbound container data. Lets anyone run the project (and the test-suite) without
access to real logistics data. Not used in production pipelines."""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_daily(n_dcs: int = 5, days: int = 730, seed: int = 7, end: str = "2026-01-31") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=end, periods=days)
    rows = []
    for k in range(n_dcs):
        base = rng.uniform(25, 90)
        weekly = rng.uniform(0.1, 0.35)
        peak = rng.uniform(0.2, 0.5)
        trend = rng.uniform(0.0, 0.0006)
        for i, d in enumerate(dates):
            dow = d.dayofweek
            week_eff = 1 + weekly * (1 if dow in (1, 2, 3) else -0.8 if dow in (5, 6) else 0)
            peak_eff = 1 + peak * np.exp(-((d.dayofyear - 290) ** 2) / (2 * 25**2))  # pre-holiday peak
            lam = base * week_eff * peak_eff * (1 + trend * i)
            n = rng.poisson(lam)
            teu = n * rng.uniform(1.4, 1.9)
            rows.append(
                {
                    "dc_id": f"DC{k + 1:02d}",
                    "arrival_date": d,
                    "container_count": float(n),
                    "teu_total": float(teu),
                    "avg_dwell_days": float(np.clip(rng.normal(2.5 + n / 60, 0.6), 0.5, None)),
                    # ASN-based plan: noisy but informative view of what is coming
                    "planned_containers": float(round(n * rng.uniform(0.8, 1.1))),
                    "planned_teu": float(teu * rng.uniform(0.8, 1.1)),
                    "inventory_utilization": float(np.clip(rng.normal(0.72, 0.08), 0.2, 1.0)),
                    "on_order_units": float(rng.integers(50_000, 300_000)),
                }
            )
    return pd.DataFrame(rows)
