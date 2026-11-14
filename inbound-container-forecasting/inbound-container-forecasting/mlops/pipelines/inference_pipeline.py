
from kfp import dsl

from . import components as c


@dsl.pipeline(
    name="inbound-container-inference",
    description="Pull champion model -> batch inference -> publish forecasts -> monitor",
)
def inference_pipeline(
    project_id: str,
    region: str = "us-central1",
    feature_table: str = "marts.mart_container_volume_features",
    forecast_table: str = "ml.container_volume_forecasts",
    monitoring_table: str = "ml.model_monitoring",
    model_display_name: str = "inbound-container-volume",
    psi_threshold: float = 0.25,
    wape_limit: float = 0.35,
):
    validate = c.validate_features(
        project_id=project_id, feature_table=feature_table, max_staleness_days=2, min_rows=5000
    ).set_display_name("Validate feature mart")

    model = c.pull_registered_model(
        project_id=project_id, region=region, model_display_name=model_display_name
    ).after(validate)
    model.set_display_name("Pull registered model")

    infer = c.perform_batch_inference(
        project_id=project_id,
        feature_table=feature_table,
        artifact_uri=model.outputs["artifact_uri"],
        model_version=model.outputs["model_version"],
    ).set_display_name("Perform batch inference")

    publish = c.generate_forecasts(
        project_id=project_id, forecast_table=forecast_table, forecasts=infer.outputs["forecasts"]
    ).set_display_name("Generate forecasts")

    c.monitor_model(
        project_id=project_id,
        monitoring_table=monitoring_table,
        artifact_uri=model.outputs["artifact_uri"],
        model_version=model.outputs["model_version"],
        psi_threshold=psi_threshold,
        wape_limit=wape_limit,
        features=infer.outputs["features"],
    ).after(publish).set_display_name("Model monitoring")
