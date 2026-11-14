
from kfp import dsl

from . import components as c


@dsl.pipeline(
    name="inbound-container-training",
    description="Validate features -> sync Feature Store -> train/tune -> champion-challenger gate -> register",
)
def training_pipeline(
    project_id: str,
    region: str = "us-central1",
    feature_table: str = "marts.mart_container_volume_features",
    model_display_name: str = "inbound-container-volume",
    online_store_id: str = "inbound_container_store",
    feature_view_id: str = "container_volume_features",
    n_trials: int = 20,
    valid_days: int = 56,
    test_days: int = 56,
    max_regression: float = 0.02,
    max_absolute: float = 0.35,
):
    validate = c.validate_features(
        project_id=project_id, feature_table=feature_table, max_staleness_days=2, min_rows=5000
    ).set_display_name("Validate feature mart")

    prep = c.feature_engineering(project_id=project_id, feature_table=feature_table).after(validate)
    prep.set_display_name("Feature engineering")

    c.sync_feature_store(
        project_id=project_id,
        region=region,
        online_store_id=online_store_id,
        feature_view_id=feature_view_id,
    ).after(validate).set_display_name("Sync Vertex AI Feature Store")

    train = c.train_and_tune(
        dataset=prep.outputs["labeled"], n_trials=n_trials, valid_days=valid_days, test_days=test_days
    )
    train.set_display_name("Model training & tuning").set_cpu_limit("4").set_memory_limit("16G")

    gate = c.evaluate_and_gate(
        project_id=project_id,
        region=region,
        model_display_name=model_display_name,
        max_regression=max_regression,
        max_absolute=max_absolute,
        dataset=prep.outputs["labeled"],
        model=train.outputs["model"],
    ).set_display_name("Champion/challenger gate")

    with dsl.If(gate.outputs["approved"] == True, name="approved"):  # noqa: E712
        c.register_model(
            project_id=project_id,
            region=region,
            model_display_name=model_display_name,
            model=train.outputs["model"],
        ).set_display_name("Register & promote model")
