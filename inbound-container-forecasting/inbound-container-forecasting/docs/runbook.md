# Runbook

## Alert: `feature_drift`
1. Query `ml.model_monitoring` for `metric LIKE 'psi:%'` over the last 14 days. Which features, which direction?
2. PSI 0.1 to 0.25 is moderate. Above 0.25 is significant.
3. Check upstream first: schema change, late ASN feed, a DC onboarded or closed (Dataform assertions on `stg_*`).
4. If the shift is real (new trade lane, new DC), trigger the training pipeline manually (`run-pipeline.yml`).

## Alert: `accuracy_degradation`
1. Inspect `serving.vw_forecast_accuracy` by `dc_id` and `forecast_date`. Is it one DC or all?
2. Compare to the previous model version (`model_version` column).
3. Trigger retraining. The gate promotes only if the new model beats the champion on the same window.
4. If retraining does not help, check for events outside the feature set (port strikes, weather, carrier changes).

## Pipeline failed at `validate_features`
The mart is stale or malformed. Check the latest Dataform workflow invocation and assertion results in
`dataform_assertions`. Do **not** bypass the check.

## Roll back a model
Vertex AI → Model Registry → select an earlier version → add alias `champion`. The next inference run uses it.

## Backfill forecasts / re-run a day
Run the inference pipeline manually. Duplicates are fine: the serving view picks the latest `forecast_run_ts`.
