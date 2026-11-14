"""Vertex AI Model Registry helpers.

Versioning: every successful training run uploads a new version of one registered model.
The version carrying the alias "champion" is what inference uses; promotion means moving that
alias. Each version stores two files: model.joblib (bare estimator, servable by the prebuilt
sklearn container) and bundle.joblib (estimator + feature list + calibration + drift reference).
"""

from __future__ import annotations

import logging
import os
import tempfile

import joblib

log = logging.getLogger(__name__)

SKLEARN_SERVING_IMAGE = "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-5:latest"


def save_bundle(bundle: dict, directory: str) -> None:
    os.makedirs(directory, exist_ok=True)
    joblib.dump(bundle["model"], os.path.join(directory, "model.joblib"))
    joblib.dump(bundle, os.path.join(directory, "bundle.joblib"))


def load_bundle(directory: str) -> dict:
    return joblib.load(os.path.join(directory, "bundle.joblib"))


def _find_model(display_name: str, project: str, region: str):
    from google.cloud import aiplatform

    aiplatform.init(project=project, location=region)
    found = aiplatform.Model.list(filter=f'display_name="{display_name}"')
    return found[0] if found else None


def upload_candidate(
    artifact_uri: str, display_name: str, project: str, region: str, metrics: dict
):
    """Upload as a new version (or first version) with alias "candidate"."""
    from google.cloud import aiplatform

    parent = _find_model(display_name, project, region)
    description = " ".join(f"{k}={v:.4f}" for k, v in metrics.items() if isinstance(v, float))
    model = aiplatform.Model.upload(
        display_name=display_name,
        artifact_uri=artifact_uri,
        serving_container_image_uri=SKLEARN_SERVING_IMAGE,
        parent_model=parent.resource_name if parent else None,
        is_default_version=parent is None,
        version_aliases=["candidate"],
        version_description=description[:500],
        labels={"framework": "sklearn", "use_case": "inbound-container-volume"},
        project=project,
        location=region,
    )
    log.info("uploaded %s version %s", model.resource_name, model.version_id)
    return model


def get_champion(display_name: str, project: str, region: str):
    """Return the model version aliased "champion", or None if nothing has been promoted yet."""
    from google.cloud import aiplatform

    parent = _find_model(display_name, project, region)
    if parent is None:
        return None
    try:
        return aiplatform.Model(
            model_name=f"{parent.resource_name}@champion", project=project, location=region
        )
    except Exception:  # alias does not exist yet
        return None


def promote(display_name: str, version_id: str, project: str, region: str) -> None:
    """Move the "champion" alias to `version_id` (an alias lives on at most one version)."""
    from google.cloud import aiplatform

    parent = _find_model(display_name, project, region)
    registry = aiplatform.models.ModelRegistry(
        model=parent.resource_name, project=project, location=region
    )
    registry.add_version_aliases(["champion"], version=version_id)
    registry.remove_version_aliases(["candidate"], version=version_id)


def download_bundle(artifact_uri: str) -> dict:
    """Download bundle.joblib from a GCS model artifact directory."""
    from google.cloud import storage

    assert artifact_uri.startswith("gs://"), artifact_uri
    bucket_name, _, prefix = artifact_uri[5:].partition("/")
    blob = storage.Client().bucket(bucket_name).blob(f"{prefix.rstrip('/')}/bundle.joblib")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bundle.joblib")
        blob.download_to_filename(path)
        return joblib.load(path)
