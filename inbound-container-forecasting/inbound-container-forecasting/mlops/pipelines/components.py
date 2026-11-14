"""KFP v2 components. Each one runs in the project image (see mlops/Dockerfile), so the
heavy lifting lives in the tested `inbound_forecast` package and components stay thin."""


import os
from typing import NamedTuple

from kfp import dsl
from kfp.dsl import Dataset, Input, Metrics, Model, Output

BASE_IMAGE = os.environ.get("PIPELINE_IMAGE", "us-central1-docker.pkg.dev/PROJECT/mlops/inbound-forecast:dev")
COMMON = dict(base_image=BASE_IMAGE, install_kfp_package=False)


# --------------------------------------------------------------------------------------
# Shared steps
# --------------------------------------------------------------------------------------
@dsl.component(**COMMON)
def validate_features(
    project_id: str,
    feature_table: str,
    max_staleness_days: int,
    min_rows: int,
    metrics: Output[Metrics],
):
    """Gate: refuse to train/score on a feature mart that is stale, tiny or has a broken target."""
    from inbound_forecast.bq import read_sql

    sql = f"""
      SELECT
        COUNT(*) AS n_rows,
        COUNT(DISTINCT dc_id) AS n_dcs,
        DATE_DIFF(CURRENT_DATE(), MAX(IF(NOT is_future, arrival_date, NULL)), DAY) AS staleness_days,
        COUNTIF(NOT is_future AND container_count IS NULL) AS null_targets,
        COUNTIF(is_future) AS future_rows
      FROM `{project_id}.{feature_table}`
    """
    r = read_sql(project_id, sql).iloc[0]
    for k in ["n_rows", "n_dcs", "staleness_days", "null_targets", "future_rows"]:
        metrics.log_metric(k, float(r[k]))

    problems = []
    if r["n_rows"] < min_rows:
        problems.append(f"only {r['n_rows']} rows (< {min_rows})")
    if r["staleness_days"] > max_staleness_days:
        problems.append(f"feature mart is {r['staleness_days']} days stale")
    if r["null_targets"] > 0:
        problems.append(f"{r['null_targets']} historical rows have a NULL target")
    if r["future_rows"] == 0:
        problems.append("no forecast-horizon rows in the mart")
    if problems:
        raise RuntimeError("Feature validation failed: " + "; ".join(problems))


# --------------------------------------------------------------------------------------
# Training pipeline
# --------------------------------------------------------------------------------------
@dsl.component(**COMMON)
def feature_engineering(project_id: str, feature_table: str, labeled: Output[Dataset]):
    """Pull model-ready rows (history + horizon) from the BigQuery feature mart.
    Feature logic itself is owned by Dataform; this step only snapshots it so a training
    run is reproducible even if the mart changes later."""
    from inbound_forecast.bq import feature_query, read_sql

    df = read_sql(project_id, feature_query(project_id, feature_table))
    df.to_parquet(labeled.path + ".parquet", index=False)
    labeled.metadata["rows"] = int(len(df))
    labeled.metadata["max_arrival_date"] = str(df.loc[~df["is_future"], "arrival_date"].max())


@dsl.component(**COMMON)
def sync_feature_store(project_id: str, region: str, online_store_id: str, feature_view_id: str):
    """Refresh the Vertex AI Feature Store online view from the BigQuery mart."""
    import vertexai
    from vertexai.resources.preview.feature_store import FeatureView

    vertexai.init(project=project_id, location=region)
    fv = FeatureView(name=feature_view_id, feature_online_store_id=online_store_id)
    sync = fv.sync()
    print("Feature view sync started:", sync.name)


@dsl.component(**COMMON)
def train_and_tune(
    dataset: Input[Dataset],
    n_trials: int,
    valid_days: int,
    test_days: int,
    model: Output[Model],
    metrics: Output[Metrics],
):
    import pandas as pd

    from inbound_forecast.registry import save_bundle
    from inbound_forecast.train import train_model

    df = pd.read_parquet(dataset.path + ".parquet")
    bundle = train_model(df, n_trials=n_trials, valid_days=valid_days, test_days=test_days)
    save_bundle(bundle, model.path)
    for k, v in bundle["metrics"].items():
        metrics.log_metric(k, float(v))
    model.metadata.update({"framework": "sklearn", "trained_at": bundle["trained_at"]})
    model.metadata["test_wape"] = float(bundle["metrics"]["test_wape"])


@dsl.component(**COMMON)
def evaluate_and_gate(
    project_id: str,
    region: str,
    model_display_name: str,
    max_regression: float,
    max_absolute: float,
    dataset: Input[Dataset],
    model: Input[Model],
    metrics: Output[Metrics],
) -> NamedTuple("Outputs", [("approved", bool), ("reason", str)]):
    """Champion / challenger: score BOTH models on the same hold-out window, then apply the gate."""
    import pandas as pd

    from inbound_forecast.evaluate import passes_gate
    from inbound_forecast.promotion import holdout_wape
    from inbound_forecast.registry import get_champion, load_bundle

    df = pd.read_parquet(dataset.path + ".parquet")
    candidate = holdout_wape(load_bundle(model.path), df)

    champion_wape = None
    champion = get_champion(model_display_name, project_id, region)
    if champion is not None:
        from inbound_forecast.registry import download_bundle

        champion_wape = holdout_wape(download_bundle(champion.uri), df)

    ok, reason = passes_gate(candidate, champion_wape, max_regression, max_absolute)
    metrics.log_metric("candidate_holdout_wape", candidate)
    if champion_wape is not None:
        metrics.log_metric("champion_holdout_wape", champion_wape)
    metrics.log_metric("approved", float(ok))
    print("Gate decision:", ok, reason)
    return (ok, reason)


@dsl.component(**COMMON)
def register_model(
    project_id: str, region: str, model_display_name: str, model: Input[Model]
) -> str:
    """Upload to Vertex AI Model Registry as a new version and promote it to champion."""
    from inbound_forecast.registry import promote, upload_candidate

    metrics = {"test_wape": model.metadata.get("test_wape", 0.0)}
    uploaded = upload_candidate(model.uri, model_display_name, project_id, region, metrics)
    promote(model_display_name, uploaded.version_id, project_id, region)
    return f"{uploaded.resource_name}@{uploaded.version_id}"


# --------------------------------------------------------------------------------------
# Inference pipeline
# --------------------------------------------------------------------------------------
@dsl.component(**COMMON)
def pull_registered_model(
    project_id: str, region: str, model_display_name: str
) -> NamedTuple("Outputs", [("artifact_uri", str), ("model_version", str)]):
    from inbound_forecast.registry import get_champion

    champion = get_champion(model_display_name, project_id, region)
    if champion is None:
        raise RuntimeError(f"No champion version registered for '{model_display_name}'. Run training first.")
    return (champion.uri, f"{champion.name}@{champion.version_id}")


@dsl.component(**COMMON)
def perform_batch_inference(
    project_id: str,
    feature_table: str,
    artifact_uri: str,
    model_version: str,
    forecasts: Output[Dataset],
    features: Output[Dataset],
):
    """Score the 14-day horizon for every DC in one batch pass."""
    from inbound_forecast.bq import read_sql
    from inbound_forecast.features import to_xy
    from inbound_forecast.predict import score
    from inbound_forecast.registry import download_bundle

    bundle = download_bundle(artifact_uri)
    future = read_sql(
        project_id,
        f"SELECT * FROM `{project_id}.{feature_table}` WHERE is_future AND arrival_date > CURRENT_DATE()",
    )
    out = score(bundle, future, model_version)
    out.to_parquet(forecasts.path + ".parquet", index=False)
    x, _ = to_xy(future, bundle["dc_categories"])
    x.to_parquet(features.path + ".parquet", index=False)
    forecasts.metadata["rows"] = int(len(out))


@dsl.component(**COMMON)
def generate_forecasts(project_id: str, forecast_table: str, forecasts: Input[Dataset]):
    """Publish forecasts to BigQuery (ml.container_volume_forecasts), the table dashboards read."""
    import pandas as pd

    from inbound_forecast.bq import write_df

    df = pd.read_parquet(forecasts.path + ".parquet")
    write_df(project_id, df, forecast_table, "WRITE_APPEND")
    print(f"Wrote {len(df)} forecast rows to {forecast_table}")


@dsl.component(**COMMON)
def monitor_model(
    project_id: str,
    monitoring_table: str,
    artifact_uri: str,
    model_version: str,
    psi_threshold: float,
    wape_limit: float,
    features: Input[Dataset],
    metrics: Output[Metrics],
):
    """Input drift (PSI vs training distribution) + live accuracy of past forecasts."""
    import pandas as pd

    from inbound_forecast.bq import read_sql, write_df
    from inbound_forecast.monitoring import (
        drift_report,
        evaluate_recent_accuracy,
        now_utc,
        raise_alerts,
        to_monitoring_rows,
    )
    from inbound_forecast.registry import download_bundle

    bundle = download_bundle(artifact_uri)
    current_x = pd.read_parquet(features.path + ".parquet")
    drift = drift_report(bundle["reference"], current_x)

    recent = read_sql(
        project_id,
        f"""SELECT predicted_containers, actual_containers
            FROM `{project_id}.serving.vw_forecast_accuracy`
            WHERE forecast_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 28 DAY)""",
    )
    accuracy = evaluate_recent_accuracy(recent)

    write_df(project_id, to_monitoring_rows(now_utc(), model_version, drift, accuracy), monitoring_table)
    for k, v in {**{f"psi_{c}": v for c, v in drift.items()}, **accuracy}.items():
        metrics.log_metric(k, float(v))
    raise_alerts(drift, accuracy, psi_threshold, wape_limit)
