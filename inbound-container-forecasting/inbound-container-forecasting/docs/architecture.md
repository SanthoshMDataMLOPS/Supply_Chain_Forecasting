# Architecture

## 1. Data preparation (Dataform + Spark)

| Layer | Dataset | Models | Purpose |
|---|---|---|---|
| Raw | `logistics_raw`, `inventory_raw` | declarations | Landed by upstream systems. Never modified. |
| Staging | `staging` | `stg_inbound_container_events`, `stg_asn_expected_arrivals`, `stg_inventory_snapshots` | Deduplicate, type, standardise ids. |
| Intermediate | `intermediate` | `int_container_daily_arrivals`, `int_expected_arrivals_daily` | Daily grain per DC (actual and planned arrivals, dwell). |
| Marts | `marts` | `mart_container_volume_features` | One row per DC per day for history **and** the next 14 days. |
| Serving | `serving` | `dim_dc_dock_capacity`, `vw_dock_planning`, `vw_forecast_accuracy` | Dashboard-facing. |

Spark (Dataproc Serverless) handles EDI 856 ASN documents (nested shipment → container → item) and writes
`logistics_raw.parsed_edi_asn`.

All tables are partitioned and clustered by `dc_id`. Non-view tables carry assertions
(`uniqueKey`, `nonNull`, `rowConditions`) which fail the run before bad data reaches the model.

### Leakage control

`mart_container_volume_features` builds a date spine through `CURRENT_DATE() + 14`. Every lag and rolling
window is shifted by at least the forecast horizon, so features for day *t+14* only use information
available on day *t*. Future rows have a NULL target and are what the inference pipeline scores.

## 2. Training pipeline (Vertex AI Pipelines)

```
validate_features → feature_engineering ─┬→ train_and_tune → evaluate_and_gate → [approved] register_model
                    sync_feature_store ──┘
```

* **validate_features**: stale mart, tiny table, NULL targets or missing horizon rows abort the run.
* **feature_engineering**: snapshots the mart so a run is reproducible.
* **sync_feature_store**: refreshes the Vertex AI Feature Store online view.
* **train_and_tune**: seeded random search (validation WAPE), Poisson gradient boosting, residual-based intervals, PSI reference distributions.
* **evaluate_and_gate**: scores candidate *and* current champion on the same hold-out window.
* **register_model**: new Model Registry version, alias `champion` moved to it.

## 3. Inference pipeline

```
validate_features → pull_registered_model → perform_batch_inference → generate_forecasts → monitor_model
```

Forecasts are appended to `ml.container_volume_forecasts` with a `forecast_run_ts`;
`serving.vw_dock_planning` always reads the latest run.

## 4. Environments & security

* Single GCP project in this reference. Use one project per environment for production (`GCP_PROJECT_ID` per GitHub environment).
* Least-privilege service accounts: pipeline runner, Dataform executor, GitHub deployer.
* No long-lived keys. GitHub → GCP via Workload Identity Federation restricted to this repository.
